"""Tú's HTTP surface: pitches, bookings, payments, Admin money and reports (contract sections 6.4, 6.5, 15.1)."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from flask import Blueprint, current_app, g, jsonify, request, send_file
from sqlalchemy import and_, case, func, or_, select
from app.contracts.dto import ManualReceipt
from app.contracts.errors import DomainError, invalid
from app.infrastructure.unit_of_work import UnitOfWork
from app.middleware import authenticated
from app.models import Booking, FieldComplex, Payment, Pitch
from app.routes.api import body, found, paginated, response
from app.services import auth_service as auth, booking_balance_service, booking_policy as policy, booking_service, match_service, payment_service, revenue_service
from app.services.gateway import InvalidCallback, gateway_or_none
from app.use_cases import cancel_booking as cancelling, manage_booking as manage, process_payment, settle_booking
from app.utils import validation as v
from app.utils.time import VIETNAM

booking_api = Blueprint('booking_api', __name__)

BOOKING_STATUSES = ('PENDING_HOLD', 'CONFIRMED', 'CANCELLED', 'EXPIRED', 'MAINTENANCE')
PHASES = ('UPCOMING', 'IN_PROGRESS', 'ENDED_UNPAID', 'PAID')
PITCH_TYPES = ('PITCH_5', 'PITCH_7', 'PITCH_11')
PAYMENT_TYPES = ('BOOKING_DEPOSIT', 'BOOKING_REMAINING_PAYMENT', 'REFUND', 'MATCH_HOST_DEPOSIT', 'MATCH_JOIN_DEPOSIT')
PAYMENT_STATUSES = ('PENDING', 'SUCCESS', 'FAILED', 'REFUND_PROCESSING', 'REFUNDED')
MANUAL_METHODS = ('CASH', 'BANK_TRANSFER')

def _reason(data):
    return v.text(data['reason'], 'reason', 200)

def _interval(data):
    return v.timestamp(data['start_time'], 'start_time'), v.timestamp(data['end_time'], 'end_time')

def _int_arg(key):
    if key not in request.args:
        return None
    try:
        return v.integer(int(request.args[key]), key)
    except ValueError:
        invalid(key)

def _price_arg(key):
    if key not in request.args:
        return None
    try:
        value = Decimal(request.args[key])
    except InvalidOperation:
        invalid(key)
    if not value.is_finite() or value < 0:
        invalid(key)
    return value

def _enum_arg(key, values):
    return v.enum(request.args[key], key, values) if key in request.args else None

# ---- Public catalogue ----

@booking_api.get('/field-complex')
def field_complex():
    with UnitOfWork() as ctx:
        row = ctx.session.scalar(select(FieldComplex).order_by(FieldComplex.complex_id).limit(1))
        if row is None:
            raise DomainError('NOT_FOUND', 'Chưa có cụm sân.', 404)
        return response({'complex_id': row.complex_id, 'name': row.name, 'phone': row.phone, 'address': row.address,
                         'policy': {'hold_seconds': policy.HOLD_SECONDS, 'slot_duration_minutes': policy.SLOT_MINUTES, 'deposit_mode': 'PERCENT',
                                    'deposit_value': policy.money(policy.DEPOSIT_PERCENT), 'opening_time': f'{policy.OPENING_HOUR:02d}:00',
                                    'closing_time': f'{policy.CLOSING_HOUR:02d}:00'}})

@booking_api.get('/pitches')
def pitches():
    kind, low, high = _enum_arg('pitch_type', PITCH_TYPES), _price_arg('min_price'), _price_arg('max_price')
    if low is not None and high is not None and low > high:
        invalid('min_price', 'min_price không được lớn hơn max_price.')
    query = select(Pitch)
    if kind:
        query = query.where(Pitch.pitch_type == kind)
    if low is not None:
        query = query.where(Pitch.price_per_slot >= low)
    if high is not None:
        query = query.where(Pitch.price_per_slot <= high)
    with UnitOfWork() as ctx:
        return paginated(ctx, query.order_by(Pitch.pitch_id), manage.pitch_data)

@booking_api.get('/pitches/<int:pitch_id>')
def pitch_item(pitch_id):
    with UnitOfWork() as ctx:
        return response(manage.pitch_data(found(ctx, Pitch, pitch_id)))

@booking_api.get('/pitches/<int:pitch_id>/availability')
def availability(pitch_id):
    try:
        day = date.fromisoformat(request.args.get('date', ''))
    except ValueError:
        invalid('date', 'date là ngày địa phương YYYY-MM-DD.')
    with UnitOfWork() as ctx:
        pitch = found(ctx, Pitch, pitch_id)
        now = ctx.now()
        today = now.astimezone(VIETNAM).date()
        if not today <= day <= today + timedelta(days=policy.MAX_ADVANCE_DAYS):
            invalid('date', 'Chỉ xem lịch trong 10 ngày tới.')
        slots = list(policy.day_slots(day))
        rows = ctx.session.scalars(select(Booking).where(Booking.pitch_id == pitch_id, Booking.start_time < slots[-1][1], Booking.end_time > slots[0][0],
                                                         Booking.status.in_(('PENDING_HOLD', 'CONFIRMED', 'MAINTENANCE')))).all()
        result = []
        for start, end in slots:
            if start <= now:
                continue  # A slot that has started can no longer be booked.
            status = 'MAINTENANCE' if pitch.status != 'ACTIVE' else 'AVAILABLE'  # POST /bookings rejects non-ACTIVE pitches.
            for row in rows:
                if not (row.start_time < end and row.end_time > start):
                    continue
                if row.status == 'MAINTENANCE':
                    status = 'MAINTENANCE'
                elif row.status == 'CONFIRMED' and status != 'MAINTENANCE':
                    status = 'BOOKED'
                elif row.status == 'PENDING_HOLD' and row.hold_expires_at > now and status == 'AVAILABLE':
                    status = 'HELD'
            result.append({'start_time': start, 'end_time': end, 'status': status})
        return response({'pitch_id': pitch_id, 'date': day.isoformat(), 'slot_duration_minutes': policy.SLOT_MINUTES, 'slots': result})

# ---- Player bookings ----

@booking_api.post('/bookings')
@authenticated
def create_booking():
    data = body(('pitch_id', 'start_time', 'end_time'), ('pitch_id', 'start_time', 'end_time'))
    start, end = _interval(data)
    return response(manage.create_booking(g.actor, pitch_id=v.integer(data['pitch_id'], 'pitch_id'), start_time=start, end_time=end), 201)

@booking_api.get('/bookings/my')
@authenticated
def my_bookings():
    status = _enum_arg('status', BOOKING_STATUSES)
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        payer_ids = select(Payment.booking_id).where(Payment.user_id == g.actor.user_id, Payment.booking_id.is_not(None))
        # Opponent representatives appear in payer_plan JSON, resolved through their match post.
        from app.models import Match, MatchPost
        rep_posts = select(MatchPost.post_id).where(MatchPost.creator_id == g.actor.user_id)
        rep_bookings = select(Match.booking_id).where(Match.booking_id.is_not(None), or_(Match.post_id.in_(rep_posts), Match.opponent_post_id.in_(rep_posts)))
        query = select(Booking).where(or_(Booking.user_id == g.actor.user_id, Booking.booking_id.in_(payer_ids), Booking.booking_id.in_(rep_bookings)))
        if status:
            query = query.where(Booking.status == status)
        return paginated(ctx, query.order_by(Booking.booking_id.desc()), lambda b: booking_service.booking_data(ctx, b))

@booking_api.get('/bookings/<int:booking_id>')
@authenticated
def booking_item(booking_id):
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        booking = ctx.session.get(Booking, booking_id)
        if booking is None or (g.actor.role != 'ADMIN' and not booking_service.is_party(booking, g.actor.user_id)):
            raise DomainError('NOT_FOUND', 'Không tìm thấy booking.', 404)
        return response(booking_service.booking_data(ctx, booking, admin=g.actor.role == 'ADMIN'))

@booking_api.post('/bookings/<int:booking_id>/cancel')
@authenticated
def cancel_booking(booking_id):
    reason = _reason(body(('reason',), ('reason',)))
    return response(cancelling.cancel_booking(g.actor, booking_id=booking_id, reason=reason))

# ---- Payments ----

@booking_api.post('/payments/deposit')
@authenticated
def deposit():
    data = body(('booking_id', 'payment_method'), ('booking_id', 'payment_method'))
    method = v.enum(data['payment_method'], 'payment_method', ('VNPAY', 'MOMO', *MANUAL_METHODS))
    session, created = process_payment.create_deposit_session(g.actor, booking_id=v.integer(data['booking_id'], 'booking_id'),
                                                              payment_method=method, client_ip=request.remote_addr)
    return response(session, 201 if created else 200)

@booking_api.get('/payments/my')
@authenticated
def my_payments():
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        return paginated(ctx, select(Payment).where(Payment.user_id == g.actor.user_id).order_by(Payment.payment_id.desc()), payment_service.payment_data)

@booking_api.get('/payments/<int:payment_id>')
@authenticated
def payment_item(payment_id):
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        payment = ctx.session.get(Payment, payment_id)
        if payment is None or (g.actor.role != 'ADMIN' and payment.user_id != g.actor.user_id):
            raise DomainError('NOT_FOUND', 'Không tìm thấy giao dịch.', 404)
        return response(payment_service.payment_data(payment, admin=g.actor.role == 'ADMIN'))

@booking_api.get('/payments/vnpay/ipn')
def vnpay_ipn():
    """ACK follows VNPay's own format; VNPay retries everything except 00 and 02."""
    def ack(code, message):
        return jsonify({'RspCode': code, 'Message': message})
    gateway = gateway_or_none('VNPAY')
    if gateway is None:
        return ack('99', 'Unknown error')
    try:
        verified = gateway.verify_callback(request.query_string, request.args)
    except InvalidCallback:
        return ack('97', 'Invalid signature')
    try:
        outcome = process_payment.process_gateway_callback('VNPAY', verified).outcome
    except Exception as error:
        current_app.logger.error('VNPay IPN failed (%s)', type(error).__name__)
        return ack('99', 'Unknown error')
    return {'OK': ack('00', 'Confirm Success'), 'DUPLICATE': ack('02', 'Order already confirmed'),
            'NOT_FOUND': ack('01', 'Order not found'), 'AMOUNT_MISMATCH': ack('04', 'Invalid amount')}[outcome]

@booking_api.post('/payments/momo/ipn')
def momo_ipn():
    raise DomainError('UNSUPPORTED_PAYMENT_METHOD', 'Cổng MoMo chưa được tích hợp.', 422)

# ---- Admin: pitches and schedule ----

@booking_api.post('/admin/pitches')
@authenticated
def admin_create_pitch():
    data = body(('pitch_name', 'pitch_type', 'price_per_slot'), ('pitch_name', 'pitch_type', 'price_per_slot'))
    return response(manage.create_pitch(g.actor, pitch_name=v.text(data['pitch_name'], 'pitch_name', 100),
                                        pitch_type=v.enum(data['pitch_type'], 'pitch_type', ('PITCH_5', 'PITCH_7')),
                                        price_per_slot=policy.parse_whole_vnd(data['price_per_slot'], 'price_per_slot')), 201)

@booking_api.patch('/admin/pitches/<int:pitch_id>')
@authenticated
def admin_update_pitch(pitch_id):
    data = body(('pitch_name', 'price_per_slot', 'status'))
    changes = {}
    if 'pitch_name' in data:
        changes['pitch_name'] = v.text(data['pitch_name'], 'pitch_name', 100)
    if 'price_per_slot' in data:
        changes['price_per_slot'] = policy.parse_whole_vnd(data['price_per_slot'], 'price_per_slot')
    if 'status' in data:
        changes['status'] = v.enum(data['status'], 'status', ('ACTIVE', 'MAINTENANCE', 'INACTIVE'))
    return response(manage.update_pitch(g.actor, pitch_id=pitch_id, changes=changes))

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
    return query.where(net >= Booking.total_amount)

def _admin_booking_row(ctx, booking):
    result = booking_service.booking_data(ctx, booking, admin=True)
    result['pitch_name'] = ctx.session.get(Pitch, booking.pitch_id).pitch_name
    parties = match_service.get_booking_parties(ctx, booking_id=booking.booking_id)
    result['teams'] = {'source': parties.source, 'opponent': parties.opponent} if parties else None
    result['balance'] = None if booking.booking_type == 'MAINTENANCE_LOCK' else booking_balance_service.compute(ctx, booking, with_qr=False)
    return result

@booking_api.route('/admin/bookings', methods=['GET', 'POST'])
@authenticated
def admin_bookings():
    if request.method == 'POST':
        data = body(('user_id', 'pitch_id', 'start_time', 'end_time', 'note'), ('user_id', 'pitch_id', 'start_time', 'end_time', 'note'))
        start, end = _interval(data)
        return response(manage.admin_create_booking(g.actor, user_id=v.integer(data['user_id'], 'user_id'), pitch_id=v.integer(data['pitch_id'], 'pitch_id'),
                                                    start_time=start, end_time=end, note=v.text(data['note'], 'note', 255)), 201)
    status, phase, pitch_id = _enum_arg('status', BOOKING_STATUSES), _enum_arg('phase', PHASES), _int_arg('pitch_id')
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        query = select(Booking)
        if 'from' in request.args or 'to' in request.args:
            first, last = revenue_service.parse_range(request.args.get('from'), request.args.get('to'))
            start, end = revenue_service.utc_bounds(first, last)
            query = query.where(Booking.start_time >= start, Booking.start_time < end)
        if pitch_id:
            query = query.where(Booking.pitch_id == pitch_id)
        if status:
            query = query.where(Booking.status == status)
        if phase:
            query = _phase_filter(query, phase, ctx.now())
        return paginated(ctx, query.order_by(Booking.start_time.desc(), Booking.booking_id.desc()), lambda b: _admin_booking_row(ctx, b))

@booking_api.patch('/admin/bookings/<int:booking_id>')
@authenticated
def admin_reschedule(booking_id):
    data = body(('start_time', 'end_time', 'pitch_id', 'reason'), ('start_time', 'end_time', 'reason'))
    start, end = _interval(data)
    pitch_id = v.integer(data['pitch_id'], 'pitch_id') if data.get('pitch_id') is not None else None
    return response(manage.reschedule_booking(g.actor, booking_id=booking_id, start_time=start, end_time=end, pitch_id=pitch_id, reason=_reason(data)))

@booking_api.post('/admin/bookings/<int:booking_id>/cancel')
@authenticated
def admin_cancel(booking_id):
    reason = _reason(body(('reason',), ('reason',)))
    return response(cancelling.cancel_booking(g.actor, booking_id=booking_id, reason=reason, admin_route=True))

@booking_api.post('/admin/maintenance-locks')
@authenticated
def admin_lock():
    data = body(('pitch_id', 'start_time', 'end_time', 'reason'), ('pitch_id', 'start_time', 'end_time', 'reason'))
    start, end = _interval(data)
    return response(manage.create_maintenance_lock(g.actor, pitch_id=v.integer(data['pitch_id'], 'pitch_id'), start_time=start, end_time=end, reason=_reason(data)), 201)

@booking_api.post('/admin/maintenance-locks/<int:booking_id>/cancel')
@authenticated
def admin_unlock(booking_id):
    reason = _reason(body(('reason',), ('reason',)))
    return response(manage.cancel_maintenance_lock(g.actor, booking_id=booking_id, reason=reason))

# ---- Admin: money ----

@booking_api.get('/admin/bookings/<int:booking_id>/balance')
@authenticated
def admin_balance(booking_id):
    return response(settle_booking.get_booking_balance(g.actor, booking_id=booking_id))

@booking_api.post('/admin/bookings/<int:booking_id>/confirm-paid')
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

@booking_api.post('/admin/payments/record')
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

@booking_api.post('/admin/payments/<int:payment_id>/refund')
@authenticated
def admin_refund(payment_id):
    reason = _reason(body(('reason',), ('reason',)))
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

@booking_api.get('/admin/revenue')
@authenticated
def admin_revenue():
    return _revenue(v.enum(request.args.get('period', 'day'), 'period', ('day', 'month', 'year')))

@booking_api.get('/admin/revenue/daily')
@authenticated
def admin_revenue_daily():
    return _revenue('day')

@booking_api.get('/admin/revenue/monthly')
@authenticated
def admin_revenue_monthly():
    return _revenue('month')

@booking_api.get('/admin/transactions')
@authenticated
def admin_transactions():
    first, last = _report_range()
    query = revenue_service.transactions_query(first, last, _int_arg('pitch_id'), _enum_arg('payment_type', PAYMENT_TYPES), _enum_arg('status', PAYMENT_STATUSES))
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        return paginated(ctx, query, lambda p: revenue_service.transaction_data(ctx, p))

@booking_api.get('/admin/booking-statistics')
@authenticated
def admin_statistics():
    first, last = _report_range()
    pitch_id = _int_arg('pitch_id')
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        return response(revenue_service.booking_statistics(ctx, first, last, pitch_id))

@booking_api.get('/admin/revenue/export')
@authenticated
def admin_export():
    first, last = _report_range()
    period = v.enum(request.args.get('period', 'day'), 'period', ('day', 'month', 'year'))
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        output = revenue_service.export_workbook(ctx, first, last, period)
    return send_file(output, as_attachment=True, download_name=f'doanh-thu-{first}-{last}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
