from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from sqlalchemy import and_, or_, select
from app.contracts.errors import invalid
from app.models import Booking, Payment, Pitch, User
from app.services import booking_policy as policy
from app.services.payment_service import COLLECTED_TYPES
from app.utils.time import VIETNAM

MAX_DAYS = 366
TIME_ZONE = 'Asia/Ho_Chi_Minh'

def parse_range(start_text, end_text):
    try:
        first, last = date.fromisoformat(start_text or ''), date.fromisoformat(end_text or '')
    except ValueError:
        invalid('from', 'from/to là ngày địa phương YYYY-MM-DD.')
    if last < first or (last - first).days >= MAX_DAYS:
        invalid('to', 'Khoảng ngày hợp lệ tối đa 366 ngày.')
    return first, last

def local_midnight(day):
    return datetime(day.year, day.month, day.day, tzinfo=VIETNAM).astimezone(timezone.utc)

def utc_bounds(first, last):
    return local_midnight(first), local_midnight(last + timedelta(days=1))

def _bucket(moment, period):
    local = moment.astimezone(VIETNAM).date()
    if period == 'year':
        return local.replace(month=1, day=1)
    return local.replace(day=1) if period == 'month' else local

def revenue_report(ctx, first, last, period):
    """Cash basis on paid_at: originals SUCCESS/REFUNDED, minus REFUND SUCCESS on the day it was refunded."""
    start, end = utc_bounds(first, last)
    rows = ctx.session.scalars(select(Payment).where(Payment.paid_at >= start, Payment.paid_at < end, or_(
        and_(Payment.payment_type.in_(COLLECTED_TYPES), Payment.status.in_(('SUCCESS', 'REFUNDED'))),
        and_(Payment.payment_type == 'REFUND', Payment.status == 'SUCCESS'))))
    gross, refunds = defaultdict(lambda: Decimal('0')), defaultdict(lambda: Decimal('0'))
    for payment in rows:
        target = refunds if payment.payment_type == 'REFUND' else gross
        target[_bucket(payment.paid_at, period)] += Decimal(payment.amount)
    def amounts(g, r):
        return {'gross_receipts': policy.money(g), 'refunds': policy.money(r), 'net_receipts': policy.money(g - r)}
    items = [dict(period_start=key.isoformat(), **amounts(gross[key], refunds[key])) for key in sorted(set(gross) | set(refunds))]
    return {'currency': 'VND', 'period': period, 'from': first.isoformat(), 'to': last.isoformat(), 'time_zone': TIME_ZONE,
            'date_basis': 'paid_at', 'items': items, 'totals': amounts(sum(gross.values(), Decimal('0')), sum(refunds.values(), Decimal('0')))}

def transactions_query(first, last, pitch_id=None, payment_type=None, status=None):
    start, end = utc_bounds(first, last)
    query = select(Payment).outerjoin(Booking, Booking.booking_id == Payment.booking_id).where(or_(
        and_(Payment.paid_at.is_not(None), Payment.paid_at >= start, Payment.paid_at < end),
        and_(Payment.paid_at.is_(None), Payment.created_at >= start, Payment.created_at < end)))
    if pitch_id:
        query = query.where(Booking.pitch_id == pitch_id)
    if payment_type:
        query = query.where(Payment.payment_type == payment_type)
    if status:
        query = query.where(Payment.status == status)
    return query.order_by(Payment.payment_id.desc())

def transaction_data(ctx, payment):
    from app.services.payment_service import payment_data
    result = payment_data(payment, admin=True)
    booking = ctx.session.get(Booking, payment.booking_id) if payment.booking_id else None
    pitch = ctx.session.get(Pitch, booking.pitch_id) if booking else None
    payer = ctx.session.get(User, payment.user_id)
    result.update(payer_name=payer.full_name if payer else None, pitch_id=pitch.pitch_id if pitch else None,
                  pitch_name=pitch.pitch_name if pitch else None, booking_start_time=booking.start_time if booking else None)
    return result

def _overlap_seconds(start, end, other_start, other_end):
    return max((min(end, other_end) - max(start, other_start)).total_seconds(), 0)

def _utilization(ctx, pitch_id, first, last, confirmed):
    """Used hours of CONFIRMED slots that have started / opening hours elapsed minus maintenance."""
    now = ctx.now()
    locks = ctx.session.scalars(select(Booking).where(Booking.pitch_id == pitch_id, Booking.status == 'MAINTENANCE')).all()
    available, day = 0.0, first
    while day <= last:
        opening = datetime(day.year, day.month, day.day, policy.OPENING_HOUR, tzinfo=VIETNAM).astimezone(timezone.utc)
        closing = min(opening + timedelta(hours=policy.CLOSING_HOUR - policy.OPENING_HOUR), now)
        if closing > opening:
            blocked = sum(_overlap_seconds(opening, closing, b.start_time, b.end_time) for b in locks)
            available += max((closing - opening).total_seconds() - blocked, 0)
        day += timedelta(days=1)
    used = sum(_overlap_seconds(b.start_time, min(b.end_time, now), b.start_time, b.end_time) for b in confirmed if b.start_time < now)
    return round(used / available, 4) if available else 0.0

def booking_statistics(ctx, first, last, pitch_id=None):
    """Activity basis on start_time; maintenance locks are not customer bookings."""
    start, end = utc_bounds(first, last)
    query = select(Booking).where(Booking.start_time >= start, Booking.start_time < end, Booking.booking_type != 'MAINTENANCE_LOCK')
    if pitch_id:
        query = query.where(Booking.pitch_id == pitch_id)
    rows = ctx.session.scalars(query).all()
    counts = Counter(b.status for b in rows)
    ids = [b.booking_id for b in rows]
    refunded = set(ctx.session.scalars(select(Payment.booking_id).where(Payment.booking_id.in_(ids), Payment.payment_type == 'REFUND',
                                                                        Payment.status == 'SUCCESS'))) if ids else set()
    pitches = ctx.session.scalars(select(Pitch).where(Pitch.pitch_id == pitch_id) if pitch_id else select(Pitch).order_by(Pitch.pitch_id)).all()
    by_pitch = []
    for pitch in pitches:
        own = [b for b in rows if b.pitch_id == pitch.pitch_id]
        confirmed = [b for b in own if b.status == 'CONFIRMED']
        by_pitch.append({'pitch_id': pitch.pitch_id, 'pitch_name': pitch.pitch_name, 'total_bookings': len(own),
                         'confirmed_bookings': len(confirmed), 'utilization_rate': _utilization(ctx, pitch.pitch_id, first, last, confirmed)})
    hours = Counter(b.start_time.astimezone(VIETNAM).hour for b in rows if b.status == 'CONFIRMED')
    return {'from': first.isoformat(), 'to': last.isoformat(), 'time_zone': TIME_ZONE, 'date_basis': 'start_time',
            'total_bookings': len(rows), 'confirmed_bookings': counts['CONFIRMED'], 'cancelled_bookings': counts['CANCELLED'],
            'expired_bookings': counts['EXPIRED'], 'refunded_booking_count': len(refunded), 'by_pitch': by_pitch,
            'peak_hours': [{'hour': h, 'booking_count': c} for h, c in sorted(hours.items(), key=lambda x: (-x[1], x[0]))]}

def _local_naive(moment):
    return moment.astimezone(VIETNAM).replace(tzinfo=None) if moment else None

def _write_rows(sheet, header, rows, money_columns=(), date_columns=()):
    sheet.append(header)
    for row in rows:
        sheet.append([None] * len(row))
        index = sheet.max_row
        for column, value in enumerate(row, 1):
            cell = sheet.cell(index, column)
            if isinstance(value, str):
                # User text beginning with a formula character must stay plain text.
                cell.value = value
                cell.data_type = 's'
            else:
                cell.value = value
            if column in money_columns:
                cell.number_format = '#,##0'
            elif column in date_columns:
                cell.number_format = 'yyyy-mm-dd hh:mm'

def export_workbook(ctx, first, last, period):
    from openpyxl import Workbook
    report = revenue_report(ctx, first, last, period)
    book = Workbook()
    summary = book.active
    summary.title = 'TongHop'
    _write_rows(summary, ['Kỳ', 'Tổng thu', 'Hoàn tiền', 'Thực thu ròng'],
                [[i['period_start'], i['gross_receipts'], i['refunds'], i['net_receipts']] for i in report['items']]
                + [['Tổng', report['totals']['gross_receipts'], report['totals']['refunds'], report['totals']['net_receipts']]], money_columns=(2, 3, 4))
    start, end = utc_bounds(first, last)
    payments = ctx.session.scalars(select(Payment).where(Payment.paid_at >= start, Payment.paid_at < end).order_by(Payment.paid_at, Payment.payment_id)).all()
    rows = []
    for p in payments:
        item = transaction_data(ctx, p)
        rows.append([p.payment_id, p.booking_id, item['payer_name'], item['pitch_name'], p.payment_type, p.payment_method, p.status,
                     Decimal(p.amount), _local_naive(p.paid_at), p.transaction_code, p.note])
    _write_rows(book.create_sheet('GiaoDich'), ['Mã GD', 'Booking', 'Người trả/tài khoản quy chiếu', 'Sân', 'Loại', 'Phương thức', 'Trạng thái',
                                                'Số tiền', 'Thời điểm', 'Mã giao dịch', 'Ghi chú'], rows, money_columns=(8,), date_columns=(9,))
    bookings = ctx.session.scalars(select(Booking).where(Booking.start_time >= start, Booking.start_time < end, Booking.booking_type != 'MAINTENANCE_LOCK')
                                   .order_by(Booking.start_time, Booking.booking_id)).all()
    rows = [[b.booking_id, ctx.session.get(Pitch, b.pitch_id).pitch_name, _local_naive(b.start_time), _local_naive(b.end_time), b.booking_type, b.status,
             b.payment_rule, Decimal(b.total_amount), Decimal(b.deposit_amount), b.note] for b in bookings]
    _write_rows(book.create_sheet('DatSan'), ['Booking', 'Sân', 'Bắt đầu', 'Kết thúc', 'Loại', 'Trạng thái', 'Thể thức', 'Tổng tiền', 'Cọc', 'Ghi chú'],
                rows, money_columns=(8, 9), date_columns=(3, 4))
    output = BytesIO()
    book.save(output)
    output.seek(0)
    return output
