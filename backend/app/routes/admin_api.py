"""HTTP routes for the Admin: pitches and schedule, counter bookings, customers, money and reports."""
from datetime import timedelta
from decimal import Decimal
from flask import Blueprint, g, request, send_file
from sqlalchemy import and_, case, func, or_, select
from app.contracts.dto import ManualReceipt
from app.contracts.errors import invalid
from app.infrastructure.unit_of_work import UnitOfWork
from app.middleware import authenticated
from app.models import Booking, Payment, Pitch
from app.routes.api import body, paginated, response
from app.services import auth_service as auth, booking_balance_service, booking_policy as policy, booking_service, match_service, payment_service, pricing, revenue_service
from app.use_cases import cancel_booking as cancelling, manage_booking as manage, process_payment, settle_booking
from app.utils import validation as v
from app.utils.time import VIETNAM
from app.routes.params import BOOKING_STATUSES, CANCEL_CAUSES, MANUAL_METHODS, PAYMENT_STATUSES, PAYMENT_TYPES, PHASES, enum_arg, int_arg, interval_arg, reason_arg

admin_api = Blueprint('admin_api', __name__)

# ---- Admin: pitches and schedule ----

@admin_api.post('/admin/pitches')
@authenticated
def admin_create_pitch():
    data = body(('pitch_name', 'pitch_type', 'price_per_slot', 'peak_price_per_slot'), ('pitch_name', 'pitch_type', 'price_per_slot'))
    return response(manage.create_pitch(g.actor, pitch_name=v.text(data['pitch_name'], 'pitch_name', 100),
                                        pitch_type=v.enum(data['pitch_type'], 'pitch_type', ('PITCH_5', 'PITCH_7')),
                                        price_per_slot=policy.parse_whole_vnd(data['price_per_slot'], 'price_per_slot'),
                                        peak_price_per_slot=_optional_price(data.get('peak_price_per_slot'))), 201)

def _optional_price(value):
    """Empty or null peak price = the pitch costs the same at every hour."""
    return None if value in (None, '') else policy.parse_whole_vnd(value, 'peak_price_per_slot')

@admin_api.patch('/admin/pitches/<int:pitch_id>')
@authenticated
def admin_update_pitch(pitch_id):
    data = body(('pitch_name', 'price_per_slot', 'peak_price_per_slot', 'status', 'confirm'))
    changes = {}
    if 'peak_price_per_slot' in data:
        changes['peak_price_per_slot'] = _optional_price(data['peak_price_per_slot'])
    if 'pitch_name' in data:
        changes['pitch_name'] = v.text(data['pitch_name'], 'pitch_name', 100)
    if 'price_per_slot' in data:
        changes['price_per_slot'] = policy.parse_whole_vnd(data['price_per_slot'], 'price_per_slot')
    if 'status' in data:
        changes['status'] = v.enum(data['status'], 'status', ('ACTIVE', 'MAINTENANCE', 'INACTIVE'))
    return response(manage.update_pitch(g.actor, pitch_id=pitch_id, changes=changes, confirm=data.get('confirm') is True))

@admin_api.patch('/admin/field-complex')
@authenticated
def admin_peak_hours():
    """Peak window for the whole complex; each pitch decides its own peak price."""
    data = body(('peak_start_time', 'peak_end_time', 'weekend_is_peak'), ('peak_start_time', 'peak_end_time', 'weekend_is_peak'))
    start, end = pricing.validate_window(data['peak_start_time'], data['peak_end_time'])
    if not isinstance(data['weekend_is_peak'], bool):
        invalid('weekend_is_peak')
    return response(manage.update_peak_hours(g.actor, peak_start_time=start, peak_end_time=end, weekend_is_peak=data['weekend_is_peak']))

def _phase_filter(query, phase, now):
    """PAID is computed from net receipts and is independent of the kick-off time."""
    collected = case((and_(Payment.payment_type.in_(payment_service.COLLECTED_TYPES), Payment.status.in_(('SUCCESS', 'REFUNDED'))), Payment.amount),
                     (and_(Payment.payment_type == 'REFUND', Payment.status == 'SUCCESS'), -Payment.amount), else_=0)
    net = select(func.coalesce(func.sum(collected), 0)).where(Payment.booking_id == Booking.booking_id).scalar_subquery()
    query = query.where(Booking.status == 'CONFIRMED')
    if phase == 'UPCOMING':
        return query.where(Booking.start_time > now)
    if phase == 'IN_PROGRESS':
        return query.where(Booking.start_time <= now, Booking.end_time > now)
    if phase == 'ENDED_UNPAID':
        return query.where(Booking.end_time <= now, net < Booking.total_amount)
    if phase == 'DUE':
        today = now.astimezone(VIETNAM).date()
        _, end_of_today = revenue_service.utc_bounds(today, today)
        return query.where(Booking.start_time < end_of_today, net < Booking.total_amount, Booking.booking_type != 'MAINTENANCE_LOCK')
    return query.where(net >= Booking.total_amount)

def _no_show_counts(ctx, user_ids):
    if not user_ids:
        return {}
    return dict(ctx.session.execute(select(Booking.user_id, func.count()).where(
        Booking.user_id.in_(user_ids), Booking.arrival_status == 'NO_SHOW').group_by(Booking.user_id)).all())

def _admin_booking_rows(ctx, rows):
    """Payments and pitches for the whole page in two queries; parties only for match bookings."""
    from app.models import Match
    payments = booking_service.payments_by_booking(ctx, rows)
    ids, pitch_ids = [b.booking_id for b in rows], {b.pitch_id for b in rows}
    pitches = {p.pitch_id: p for p in ctx.session.scalars(select(Pitch).where(Pitch.pitch_id.in_(pitch_ids)))} if pitch_ids else {}
    with_match = set(ctx.session.scalars(select(Match.booking_id).where(Match.booking_id.in_(ids)))) if ids else set()
    from app.models import User
    user_ids = {b.user_id for b in rows} | {p['user_id'] for b in rows for p in (b.payer_plan or [])}
    users = {u.user_id: u for u in ctx.session.scalars(select(User).where(User.user_id.in_(user_ids)))} if user_ids else {}
    no_shows = _no_show_counts(ctx, user_ids)
    def contact(uid):
        user = users.get(uid)
        walk_in = auth.is_walk_in(user)
        return dict(user_id=uid, full_name=user.full_name if user else None, phone=user.phone if user else None,
                    email=None if walk_in or not user else user.email, walk_in=walk_in, no_show_count=no_shows.get(uid, 0))
    def row(booking):
        mine = payments[booking.booking_id]
        result = booking_service.booking_data(ctx, booking, admin=True, payments=mine,
                                              pitch_names={pid: p.pitch_name for pid, p in pitches.items()})
        result['pitch_name'] = pitches[booking.pitch_id].pitch_name
        result['customer'] = contact(booking.user_id)
        for payer in result['payer_progress']:
            info = contact(payer['user_id'])
            payer.update(full_name=info['full_name'], phone=info['phone'])
        result['teams'] = match_service.booking_teams(ctx, booking.booking_id) if booking.booking_id in with_match else None
        result['balance'] = None if booking.booking_type == 'MAINTENANCE_LOCK' else booking_balance_service.compute(ctx, booking, mine, with_qr=False)
        return result
    return row

@admin_api.route('/admin/bookings', methods=['GET', 'POST'])
@authenticated
def admin_bookings():
    if request.method == 'POST':
        data = body(('user_id', 'guest', 'pitch_id', 'start_time', 'end_time', 'note', 'payment', 'repeat_weeks'), ('pitch_id', 'start_time', 'end_time', 'note'))
        repeat_weeks = v.integer(data.get('repeat_weeks', 1), 'repeat_weeks', 1, policy.MAX_REPEAT_WEEKS)
        if ('user_id' in data) == ('guest' in data):
            invalid('user_id', 'Chọn tài khoản khách hoặc nhập khách vãng lai (tên và số điện thoại).')
        guest = None
        if 'guest' in data:
            guest = v.fields(data['guest'], ('full_name', 'phone'), ('full_name', 'phone'))
        payment = None
        if data.get('payment') is not None:
            raw = v.fields(data['payment'], ('amount', 'payment_method', 'reference'), ('amount', 'payment_method'))
            payment = {'amount': policy.parse_whole_vnd(raw['amount'], 'payment.amount', allow_zero=True),
                       'method': v.enum(raw['payment_method'], 'payment.payment_method', MANUAL_METHODS),
                       'reference': v.text(raw.get('reference'), 'payment.reference', 100, minimum=0, nullable=True)}
            if payment['amount'] == 0:
                payment = None
        start, end = interval_arg(data)
        return response(manage.admin_create_booking(g.actor, user_id=v.integer(data['user_id'], 'user_id') if guest is None else None, guest=guest,
                                                    pitch_id=v.integer(data['pitch_id'], 'pitch_id'), start_time=start, end_time=end,
                                                    note=v.text(data['note'], 'note', 200), payment=payment, repeat_weeks=repeat_weeks), 201)
    status, phase, pitch_id = enum_arg('status', BOOKING_STATUSES), enum_arg('phase', PHASES), int_arg('pitch_id')
    series_id = request.args.get('series_id')
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        query = select(Booking)
        if 'from' in request.args or 'to' in request.args:
            first, last = revenue_service.parse_range(request.args.get('from'), request.args.get('to'))
            start, end = revenue_service.utc_bounds(first, last)
            query = query.where(Booking.start_time >= start, Booking.start_time < end)
        if pitch_id:
            query = query.where(Booking.pitch_id == pitch_id)
        if series_id:
            query = query.where(Booking.series_id == v.text(series_id, 'series_id', 36))
        if status:
            query = query.where(Booking.status == status)
        if phase:
            query = _phase_filter(query, phase, ctx.now())
        return paginated(ctx, query.order_by(Booking.start_time.desc(), Booking.booking_id.desc()), None,
                         lambda rows: _admin_booking_rows(ctx, rows))

@admin_api.patch('/admin/bookings/<int:booking_id>')
@authenticated
def admin_reschedule(booking_id):
    data = body(('start_time', 'end_time', 'pitch_id', 'reason'), ('start_time', 'end_time', 'reason'))
    start, end = interval_arg(data)
    pitch_id = v.integer(data['pitch_id'], 'pitch_id') if data.get('pitch_id') is not None else None
    return response(manage.reschedule_booking(g.actor, booking_id=booking_id, start_time=start, end_time=end, pitch_id=pitch_id, reason=reason_arg(data)))

@admin_api.post('/admin/bookings/<int:booking_id>/cancel')
@authenticated
def admin_cancel(booking_id):
    data = body(('reason', 'cause'), ('reason',))
    cause = v.enum(data.get('cause', 'VENUE'), 'cause', CANCEL_CAUSES)
    return response(cancelling.cancel_booking(g.actor, booking_id=booking_id, reason=reason_arg(data), admin_route=True,
                                              customer_cancel=cause == 'CUSTOMER'))

@admin_api.post('/admin/bookings/series/<series_id>/cancel')
@authenticated
def admin_cancel_series(series_id):
    """Stop a regular customer's weekly slot: every future session of the series."""
    data = body(('reason', 'cause'), ('reason',))
    cause = v.enum(data.get('cause', 'CUSTOMER'), 'cause', CANCEL_CAUSES)
    v.text(series_id, 'series_id', 36)
    return response(cancelling.cancel_series(g.actor, series_id=series_id, reason=reason_arg(data), customer_cancel=cause == 'CUSTOMER'))

@admin_api.post('/admin/bookings/<int:booking_id>/arrival')
@authenticated
def admin_arrival(booking_id):
    """Counter check-in: ARRIVED, NO_SHOW, or null to undo."""
    data = body(('status',), ('status',))
    status = None if data['status'] is None else v.enum(data['status'], 'status', ('ARRIVED', 'NO_SHOW'))
    return response(manage.mark_arrival(g.actor, booking_id=booking_id, status=status))

@admin_api.post('/admin/maintenance-locks')
@authenticated
def admin_lock():
    data = body(('pitch_id', 'start_time', 'end_time', 'reason'), ('pitch_id', 'start_time', 'end_time', 'reason'))
    start, end = interval_arg(data)
    return response(manage.create_maintenance_lock(g.actor, pitch_id=v.integer(data['pitch_id'], 'pitch_id'), start_time=start, end_time=end, reason=reason_arg(data)), 201)

@admin_api.post('/admin/maintenance-locks/<int:booking_id>/cancel')
@authenticated
def admin_unlock(booking_id):
    reason = reason_arg(body(('reason',), ('reason',)))
    return response(manage.cancel_maintenance_lock(g.actor, booking_id=booking_id, reason=reason))

# ---- Admin: customers and overview ----

@admin_api.get('/admin/users')
@authenticated
def admin_users():
    """Find a customer for a counter booking by name, email or phone (at least 2 characters)."""
    from app.models import User
    q = (request.args.get('q') or '').strip()
    if not 2 <= len(q) <= 100:
        invalid('q', 'Nhập từ 2 đến 100 ký tự để tìm.')
    role = enum_arg('role', ('PLAYER', 'ADMIN'))
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        # LIKE wildcards typed by the admin are matched literally.
        pattern = '%' + q.lower().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        matches = [func.lower(User.full_name).like(pattern, escape='\\'), func.lower(User.email).like(pattern, escape='\\'),
                   User.phone.like(pattern, escape='\\')]
        digits = ''.join(ch for ch in q if ch.isdigit())
        if len(digits) >= 3 and len(digits) >= len(q.replace(' ', '').replace('.', '').replace('-', '').lstrip('+')):
            matches.append(User.phone.like(f'%{digits}%'))  # "0912 345" finds 0912345678 as stored
        query = select(User).where(or_(*matches))
        if role:
            query = query.where(User.role == role)
        def preload(rows):
            counts = _no_show_counts(ctx, {u.user_id for u in rows})
            return lambda u: {'user_id': u.user_id, 'full_name': u.full_name, 'email': None if auth.is_walk_in(u) else u.email,
                              'phone': u.phone, 'role': u.role, 'status': u.status, 'walk_in': auth.is_walk_in(u),
                              'no_show_count': counts.get(u.user_id, 0)}
        return paginated(ctx, query.order_by(User.full_name, User.user_id), None, preload)

@admin_api.get('/admin/dashboard')
@authenticated
def admin_dashboard():
    """What needs the Admin now: live holds, refunds owed, ended-but-unpaid bookings, today's money and games."""
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        now = ctx.now()
        today = now.astimezone(VIETNAM).date()
        day_start, day_end = revenue_service.utc_bounds(today, today)
        holds = ctx.session.scalars(select(Booking).where(Booking.status == 'PENDING_HOLD', Booking.hold_expires_at > now)
                                    .order_by(Booking.hold_expires_at)).all()
        refunds = ctx.session.scalars(select(Payment).where(Payment.payment_type == 'REFUND', Payment.status == 'REFUND_PROCESSING')).all()
        unpaid = ctx.session.scalars(_phase_filter(select(Booking), 'ENDED_UNPAID', now).order_by(Booking.end_time)).all()
        games = ctx.session.scalars(select(Booking).where(Booking.status == 'CONFIRMED', Booking.start_time >= day_start,
                                                          Booking.start_time < day_end).order_by(Booking.start_time)).all()
        rows = _admin_booking_rows(ctx, [*holds[:5], *unpaid, *games[:40]])
        unpaid_rows = [rows(b) for b in unpaid]
        outstanding = sum((Decimal(r['balance'].outstanding_amount) for r in unpaid_rows if r['balance']), Decimal('0'))
        return response({
            'today': today.isoformat(),
            'revenue_today': revenue_service.revenue_report(ctx, today, today, 'day')['totals'],
            'pending_holds': {'count': len(holds), 'items': [rows(b) for b in holds[:5]]},
            'pending_refunds': {'count': len(refunds), 'amount': policy.money(sum((Decimal(p.amount) for p in refunds), Decimal('0')))},
            'ended_unpaid': {'count': len(unpaid), 'outstanding_amount': policy.money(outstanding), 'items': unpaid_rows[:5]},
            'today_games': {'count': len(games), 'items': [rows(b) for b in games[:40]]},
            'background_jobs': _job_lag(ctx, now),
        })

JOB_GRACE = timedelta(minutes=3)

def _job_lag(ctx, now):
    """Work the scheduler should already have done. Anything overdue by minutes means it is not running."""
    from app.models import MatchPost, Notification
    count = lambda query: ctx.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    overdue = {
        'expired_holds': count(select(Booking.booking_id).where(Booking.status == 'PENDING_HOLD', Booking.hold_expires_at < now - JOB_GRACE)),
        'expired_requests': count(select(MatchPost.post_id).where(MatchPost.status == 'OPEN', MatchPost.expiry_time < now - JOB_GRACE)),
        'unsent_emails': count(select(Notification.notification_id).where(
            Notification.delivery_channel == 'EMAIL', Notification.delivery_status == 'PENDING', Notification.created_at < now - JOB_GRACE)),
    }
    return dict(overdue, lagging=any(overdue.values()))

# ---- Admin: money ----

@admin_api.get('/admin/bookings/<int:booking_id>/balance')
@authenticated
def admin_balance(booking_id):
    return response(settle_booking.get_booking_balance(g.actor, booking_id=booking_id))

@admin_api.post('/admin/bookings/<int:booking_id>/confirm-paid')
@authenticated
def admin_confirm_paid(booking_id):
    data = body(('expected_outstanding', 'idempotency_key', 'receipts'), ('expected_outstanding', 'idempotency_key', 'receipts'))
    if not isinstance(data['receipts'], list) or not 1 <= len(data['receipts']) <= 50:
        invalid('receipts', 'Cần ít nhất một khoản.')
    receipts = []
    for item in data['receipts']:
        v.fields(item, ('payment_method', 'amount', 'reference'), ('payment_method', 'amount'))
        reference = v.text(item.get('reference'), 'reference', 100, nullable=True)
        receipts.append(ManualReceipt(v.enum(item['payment_method'], 'payment_method', MANUAL_METHODS), policy.parse_whole_vnd(item['amount'], 'amount'), reference))
    return response(settle_booking.confirm_booking_paid(g.actor, booking_id=booking_id,
                                                        expected_outstanding=policy.parse_whole_vnd(data['expected_outstanding'], 'expected_outstanding', allow_zero=True),
                                                        idempotency_key=v.text(data['idempotency_key'], 'idempotency_key', 100, 8), receipts=receipts))

@admin_api.post('/admin/payments/record')
@authenticated
def admin_record_payment():
    keys = ('booking_id', 'user_id', 'amount', 'payment_type', 'payment_method', 'reference', 'note')
    data = body(keys, keys[:-1])
    result, created = process_payment.record_manual_payment(
        g.actor, booking_id=v.integer(data['booking_id'], 'booking_id'), user_id=v.integer(data['user_id'], 'user_id'),
        payment_type=v.enum(data['payment_type'], 'payment_type', payment_service.COLLECTED_TYPES),
        amount=policy.parse_whole_vnd(data['amount'], 'amount'), method=v.enum(data['payment_method'], 'payment_method', MANUAL_METHODS),
        reference=v.text(data['reference'], 'reference', 100), note=v.text(data.get('note'), 'note', 150, nullable=True))
    return response(result, 201 if created else 200)

@admin_api.get('/admin/refunds/pending')
@authenticated
def admin_pending_refunds():
    """Refunds still owed to someone, oldest first. CASH/BANK_TRANSFER ones (SePay included) need the Admin
    to hand the money back and then confirm via POST /admin/payments/{refund_for_payment_id}/refund."""
    from app.models import User
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        query = select(Payment).where(Payment.payment_type == 'REFUND', Payment.status == 'REFUND_PROCESSING').order_by(Payment.payment_id)
        def preload(rows):
            users = {u.user_id: u for u in ctx.session.scalars(select(User).where(User.user_id.in_({r.user_id for r in rows})))} if rows else {}
            originals = {p.payment_id: p for p in ctx.session.scalars(select(Payment).where(
                Payment.payment_id.in_({r.refund_for_payment_id for r in rows})))} if rows else {}
            def item(refund):
                payer, original = users.get(refund.user_id), originals.get(refund.refund_for_payment_id)
                return dict(payment_service.payment_data(refund, admin=True),
                            manual=refund.payment_method in MANUAL_METHODS,
                            payer=dict(user_id=refund.user_id, full_name=payer.full_name if payer else None,
                                       email=payer.email if payer else None, phone=payer.phone if payer else None,
                                       refund_account=payment_service.refund_account(payer)),
                            original=dict(payment_id=original.payment_id, transaction_code=original.transaction_code,
                                          payment_type=original.payment_type, paid_at=original.paid_at,
                                          note=original.note) if original else None)
            return item
        return paginated(ctx, query, None, preload)

@admin_api.post('/admin/payments/<int:payment_id>/refund')
@authenticated
def admin_refund(payment_id):
    reason = reason_arg(body(('reason',), ('reason',)))
    result, status = cancelling.refund_payment(g.actor, payment_id=payment_id, reason=reason)
    return response(result, status)

# ---- Admin: reports ----

def _report_range():
    return revenue_service.parse_range(request.args.get('from'), request.args.get('to'))

def _revenue(period):
    first, last = _report_range()
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        return response(revenue_service.revenue_report(ctx, first, last, period))

@admin_api.get('/admin/revenue')
@authenticated
def admin_revenue():
    return _revenue(v.enum(request.args.get('period', 'day'), 'period', ('day', 'month', 'year')))

@admin_api.get('/admin/revenue/daily')
@authenticated
def admin_revenue_daily():
    return _revenue('day')

@admin_api.get('/admin/revenue/monthly')
@authenticated
def admin_revenue_monthly():
    return _revenue('month')

@admin_api.get('/admin/transactions')
@authenticated
def admin_transactions():
    first, last = _report_range()
    query = revenue_service.transactions_query(first, last, int_arg('pitch_id'), enum_arg('payment_type', PAYMENT_TYPES), enum_arg('status', PAYMENT_STATUSES))
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        return paginated(ctx, query, lambda p: revenue_service.transaction_data(ctx, p))

@admin_api.get('/admin/booking-statistics')
@authenticated
def admin_statistics():
    first, last = _report_range()
    pitch_id = int_arg('pitch_id')
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        return response(revenue_service.booking_statistics(ctx, first, last, pitch_id))

@admin_api.get('/admin/revenue/export')
@authenticated
def admin_export():
    first, last = _report_range()
    period = v.enum(request.args.get('period', 'day'), 'period', ('day', 'month', 'year'))
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        output = revenue_service.export_workbook(ctx, first, last, period)
    return send_file(output, as_attachment=True, download_name=f'doanh-thu-{first}-{last}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
