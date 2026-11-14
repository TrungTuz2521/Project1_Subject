"""HTTP routes for customers: the pitch catalogue, bookings, deposits and payment notifications."""
from datetime import date, timedelta
from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import or_, select
from app.contracts.errors import DomainError, invalid
from app.infrastructure.unit_of_work import UnitOfWork
from app.middleware import authenticated
from app.models import Booking, FieldComplex, Payment, Pitch
from app.routes.api import body, found, paginated, response
from app.services import auth_service as auth, booking_policy as policy, booking_service, payment_service, pricing
from app.services.gateway import InvalidCallback, gateway_or_none
from app.use_cases import cancel_booking as cancelling, manage_booking as manage, process_payment
from app.utils import validation as v
from app.utils.time import VIETNAM
from app.routes.params import BOOKING_STATUSES, MANUAL_METHODS, PITCH_TYPES, enum_arg, interval_arg, price_arg, reason_arg

booking_api = Blueprint('booking_api', __name__)

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
                                    'closing_time': f'{policy.CLOSING_HOUR:02d}:00', **pricing.peak_config(row)}})

@booking_api.get('/pitches')
def pitches():
    kind, low, high = enum_arg('pitch_type', PITCH_TYPES), price_arg('min_price'), price_arg('max_price')
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
        complex_row = ctx.session.get(FieldComplex, pitch.complex_id)
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
            peak = pitch.peak_price_per_slot is not None and pricing.is_peak(complex_row, start)
            result.append({'start_time': start, 'end_time': end, 'status': status, 'is_peak': peak,
                           'price': policy.money(pitch.peak_price_per_slot if peak else pitch.price_per_slot)})
        return response({'pitch_id': pitch_id, 'date': day.isoformat(), 'slot_duration_minutes': policy.SLOT_MINUTES, 'slots': result})

# ---- Player bookings ----

@booking_api.post('/bookings')
@authenticated
def create_booking():
    data = body(('pitch_id', 'start_time', 'end_time'), ('pitch_id', 'start_time', 'end_time'))
    start, end = interval_arg(data)
    return response(manage.create_booking(g.actor, pitch_id=v.integer(data['pitch_id'], 'pitch_id'), start_time=start, end_time=end), 201)

@booking_api.get('/bookings/my')
@authenticated
def my_bookings():
    status = enum_arg('status', BOOKING_STATUSES)
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
        def preload(rows):
            payments, names = booking_service.payments_by_booking(ctx, rows), booking_service.pitch_names(ctx, rows)
            return lambda b: booking_service.booking_data(ctx, b, payments=payments[b.booking_id], pitch_names=names)
        return paginated(ctx, query.order_by(Booking.booking_id.desc()), None, preload)

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
    reason = reason_arg(body(('reason',), ('reason',)))
    return response(cancelling.cancel_booking(g.actor, booking_id=booking_id, reason=reason))

# ---- Payments ----

@booking_api.get('/bookings/<int:booking_id>/deposit-instructions')
@authenticated
def deposit_instructions(booking_id):
    from app.services.bank_deposit_service import instructions
    return response(instructions(g.actor, booking_id))

@booking_api.post('/payments/deposit/demo-confirm')
@authenticated
def demo_confirm_deposit():
    # Simulated money only on a developer machine: never next to real SePay payments, and never through a
    # tunnel or reverse proxy (those reach Flask from 127.0.0.1 too, but add forwarding headers).
    from app.services.sepay_service import enabled as sepay_enabled
    forwarded = any(request.headers.get(h) for h in ('X-Forwarded-For', 'Forwarded', 'CF-Connecting-IP', 'X-Real-IP'))
    if forwarded or sepay_enabled() or request.remote_addr not in ('127.0.0.1', '::1'):
        raise DomainError('DEMO_DISABLED', 'Chỉ dùng xác nhận demo trên máy phát triển local, khi chưa bật SePay.', 403)
    from app.services.demo_deposit_service import confirm_demo_deposit
    data = body(('booking_id',), ('booking_id',))
    return response(confirm_demo_deposit(g.actor, v.integer(data['booking_id'], 'booking_id')))

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

@booking_api.post('/payments/deposit/qr')
@authenticated
def deposit_qr():
    """60-second VietQR with amount and transfer content pre-filled; only the SePay webhook confirms it."""
    from app.services.sepay_service import open_qr_session
    data = body(('booking_id',), ('booking_id',))
    session, created = open_qr_session(g.actor, v.integer(data['booking_id'], 'booking_id'))
    return response(session, 201 if created else 200)

@booking_api.post('/payments/sepay/webhook')
def sepay_webhook():
    """SePay retries anything that is not 2xx: answer 200 once the notification is authentic and handled."""
    from app.services.sepay_service import handle_webhook
    try:
        outcome = handle_webhook(request.headers.get('Authorization', ''), request.get_json(silent=True))
    except InvalidCallback:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    except DomainError:
        raise
    except Exception as error:
        current_app.logger.error('SePay webhook failed (%s)', type(error).__name__)
        return jsonify({'success': False, 'message': 'Retry later'}), 500
    return jsonify({'success': True, 'outcome': outcome}), 200

@booking_api.post('/payments/momo/ipn')
def momo_ipn():
    raise DomainError('UNSUPPORTED_PAYMENT_METHOD', 'Cổng MoMo chưa được tích hợp.', 422)
