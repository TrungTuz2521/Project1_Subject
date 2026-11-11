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
from app.services import auth_service as auth, booking_balance_service, booking_policy as policy, booking_service, match_service, payment_service, pricing, revenue_service
from app.services.gateway import InvalidCallback, gateway_or_none
from app.use_cases import cancel_booking as cancelling, manage_booking as manage, process_payment, settle_booking
from app.utils import validation as v
from app.utils.time import VIETNAM

booking_api = Blueprint('booking_api', __name__)

BOOKING_STATUSES = ('PENDING_HOLD', 'CONFIRMED', 'CANCELLED', 'EXPIRED', 'MAINTENANCE')
PHASES = ('UPCOMING', 'IN_PROGRESS', 'ENDED_UNPAID', 'PAID', 'DUE')
PITCH_TYPES = ('PITCH_5', 'PITCH_7', 'PITCH_11')
PAYMENT_TYPES = ('BOOKING_DEPOSIT', 'BOOKING_REMAINING_PAYMENT', 'REFUND', 'MATCH_HOST_DEPOSIT', 'MATCH_JOIN_DEPOSIT')
PAYMENT_STATUSES = ('PENDING', 'SUCCESS', 'FAILED', 'REFUND_PROCESSING', 'REFUNDED')
MANUAL_METHODS = ('CASH', 'BANK_TRANSFER')
# VENUE: the pitch could not be used, everything is refunded. CUSTOMER: the customer cancelled, the deposit is kept.
CANCEL_CAUSES = ('VENUE', 'CUSTOMER')

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
                                    'closing_time': f'{policy.CLOSING_HOUR:02d}:00', **pricing.peak_config(row)}})

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
        def preload(rows):
            payments = booking_service.payments_by_booking(ctx, rows)
            return lambda b: booking_service.booking_data(ctx, b, payments=payments[b.booking_id])
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
    reason = _reason(body(('reason',), ('reason',)))
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
    if request.remote_addr not in ('127.0.0.1', '::1'):
        raise DomainError('DEMO_DISABLED', 'Chỉ dùng xác nhận demo trên máy phát triển local.', 403)
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

# ---- Admin: pitches and schedule ----

@booking_api.post('/admin/pitches')
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

@booking_api.patch('/admin/pitches/<int:pitch_id>')
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

@booking_api.patch('/admin/field-complex')
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
        result = booking_service.booking_data(ctx, booking, admin=True, payments=mine)
        result['pitch_name'] = pitches[booking.pitch_id].pitch_name
        result['customer'] = contact(booking.user_id)
        for payer in result['payer_progress']:
            info = contact(payer['user_id'])
            payer.update(full_name=info['full_name'], phone=info['phone'])
        parties = match_service.get_booking_parties(ctx, booking_id=booking.booking_id) if booking.booking_id in with_match else None
        result['teams'] = {'source': parties.source, 'opponent': parties.opponent} if parties else None
        result['balance'] = None if booking.booking_type == 'MAINTENANCE_LOCK' else booking_balance_service.compute(ctx, booking, mine, with_qr=False)
        return result
    return row

@booking_api.route('/admin/bookings', methods=['GET', 'POST'])
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
        start, end = _interval(data)
        return response(manage.admin_create_booking(g.actor, user_id=v.integer(data['user_id'], 'user_id') if guest is None else None, guest=guest,
                                                    pitch_id=v.integer(data['pitch_id'], 'pitch_id'), start_time=start, end_time=end,
                                                    note=v.text(data['note'], 'note', 200), payment=payment, repeat_weeks=repeat_weeks), 201)
    status, phase, pitch_id = _enum_arg('status', BOOKING_STATUSES), _enum_arg('phase', PHASES), _int_arg('pitch_id')
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
    data = body(('reason', 'cause'), ('reason',))
    cause = v.enum(data.get('cause', 'VENUE'), 'cause', CANCEL_CAUSES)
    return response(cancelling.cancel_booking(g.actor, booking_id=booking_id, reason=_reason(data), admin_route=True,
                                              customer_cancel=cause == 'CUSTOMER'))

@booking_api.post('/admin/bookings/series/<series_id>/cancel')
@authenticated
def admin_cancel_series(series_id):
    """Stop a regular customer's weekly slot: every future session of the series."""
    data = body(('reason', 'cause'), ('reason',))
    cause = v.enum(data.get('cause', 'CUSTOMER'), 'cause', CANCEL_CAUSES)
    v.text(series_id, 'series_id', 36)
    return response(cancelling.cancel_series(g.actor, series_id=series_id, reason=_reason(data), customer_cancel=cause == 'CUSTOMER'))

@booking_api.post('/admin/bookings/<int:booking_id>/arrival')
@authenticated
def admin_arrival(booking_id):
    """Counter check-in: ARRIVED, NO_SHOW, or null to undo."""
    data = body(('status',), ('status',))
    status = None if data['status'] is None else v.enum(data['status'], 'status', ('ARRIVED', 'NO_SHOW'))
    return response(manage.mark_arrival(g.actor, booking_id=booking_id, status=status))

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

# ---- Admin: customers and overview ----

@booking_api.get('/admin/users')
@authenticated
def admin_users():
    """Find a customer for a counter booking by name, email or phone (at least 2 characters)."""
    from app.models import User
    q = (request.args.get('q') or '').strip()
    if not 2 <= len(q) <= 100:
        invalid('q', 'Nhập từ 2 đến 100 ký tự để tìm.')
    role = _enum_arg('role', ('PLAYER', 'ADMIN'))
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        # LIKE wildcards typed by the admin are matched literally.
        pattern = '%' + q.lower().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = select(User).where(or_(func.lower(User.full_name).like(pattern, escape='\\'),
                                       func.lower(User.email).like(pattern, escape='\\'),
                                       User.phone.like(pattern, escape='\\')))
        if role:
            query = query.where(User.role == role)
        def preload(rows):
            counts = _no_show_counts(ctx, {u.user_id for u in rows})
            return lambda u: {'user_id': u.user_id, 'full_name': u.full_name, 'email': None if auth.is_walk_in(u) else u.email,
                              'phone': u.phone, 'role': u.role, 'status': u.status, 'walk_in': auth.is_walk_in(u),
                              'no_show_count': counts.get(u.user_id, 0)}
        return paginated(ctx, query.order_by(User.full_name, User.user_id), None, preload)

@booking_api.get('/admin/dashboard')
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
        })

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

@booking_api.get('/admin/refunds/pending')
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
                                       email=payer.email if payer else None, phone=payer.phone if payer else None),
                            original=dict(payment_id=original.payment_id, transaction_code=original.transaction_code,
                                          payment_type=original.payment_type, paid_at=original.paid_at,
                                          note=original.note) if original else None)
            return item
        return paginated(ctx, query, None, preload)

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
