from datetime import timedelta
from decimal import Decimal
from sqlalchemy import and_, or_, select
from app.contracts.dto import BookingHold
from app.contracts.enums import PAYMENT_RULES
from app.contracts.errors import DomainError, SlotUnavailable
from app.models import Booking, Match, MatchPost, Payment, Pitch
from app.services import booking_policy as policy
from app.utils.serialization import columns

def _blocking(now):
    # An expired hold stops blocking immediately, without waiting for the worker.
    return or_(Booking.status.in_(('CONFIRMED', 'MAINTENANCE')),
               and_(Booking.status == 'PENDING_HOLD', Booking.hold_expires_at > now))

def find_conflict(ctx, pitch_id, start, end, exclude_booking_id=None):
    query = select(Booking).where(Booking.pitch_id == pitch_id, Booking.start_time < end, Booking.end_time > start,
                                  _blocking(ctx.now()))
    if exclude_booking_id:
        query = query.where(Booking.booking_id != exclude_booking_id)
    return ctx.session.scalars(query.limit(1)).first()

def find_match_pitch(ctx, *, pitch_type, start_time, end_time):
    """Read-only discovery before locks; create_match_hold rechecks after locking the Pitch."""
    query = select(Pitch.pitch_id).where(Pitch.pitch_type == pitch_type, Pitch.status == 'ACTIVE').order_by(Pitch.pitch_id)
    for pitch_id in ctx.session.scalars(query):
        if not find_conflict(ctx, pitch_id, start_time, end_time):
            return pitch_id
    return None

def _locked_active_pitch(ctx, pitch_id):
    rows = ctx.locks.lock(Pitch, [pitch_id])
    if not rows or rows[0].status != 'ACTIVE':
        raise SlotUnavailable()
    return rows[0]

def _insert_hold(ctx, *, pitch, user_id, start, end, payment_rule, payer_ids, booking_type='ONLINE', note=None, hold_seconds=None):
    from app.services.pricing import slot_price
    total, _ = slot_price(ctx, pitch, start)  # Peak or normal price, fixed onto the booking now.
    deposit = policy.deposit_total(total)
    amounts = policy.split_deposit(deposit) if len(payer_ids) == 2 else (deposit,)
    plan = [{'user_id': uid, 'amount': format(amount, '.2f')} for uid, amount in zip(payer_ids, amounts)]
    now = ctx.now().replace(microsecond=0)
    booking = Booking(pitch_id=pitch.pitch_id, user_id=user_id, start_time=start, end_time=end, total_amount=total,
                      deposit_amount=deposit, booking_type=booking_type, status='PENDING_HOLD',
                      hold_expires_at=now + timedelta(seconds=hold_seconds or policy.HOLD_SECONDS), payment_rule=payment_rule,
                      payer_plan=plan, note=note)
    ctx.session.add(booking)
    ctx.session.flush()
    return booking

def _hold(booking):
    return BookingHold(booking.booking_id, booking.status, booking.hold_expires_at, policy.money(booking.total_amount),
                       policy.money(booking.deposit_amount), booking.payer_plan)

def create_direct_hold(ctx, *, pitch_id, user_id, start_time, end_time, booking_type='ONLINE', note=None,
                       max_advance_days=policy.MAX_ADVANCE_DAYS):
    pitch = _locked_active_pitch(ctx, pitch_id)
    policy.validate_slot(ctx.now(), start_time, end_time, max_advance_days)
    if find_conflict(ctx, pitch_id, start_time, end_time):
        raise SlotUnavailable()
    return _insert_hold(ctx, pitch=pitch, user_id=user_id, start=start_time, end=end_time,
                        payment_rule='DIRECT_BOOKING', payer_ids=[user_id], booking_type=booking_type, note=note)

def create_match_hold(ctx, *, match_id, pitch_id, start_time, end_time, source_user_id, opponent_user_id, payment_rule, hold_seconds=None):
    """Caller already holds parent locks. Raises SlotUnavailable before any Booking is inserted."""
    if payment_rule not in PAYMENT_RULES or source_user_id == opponent_user_id:
        raise DomainError('STATE_CONFLICT', 'Thể thức hoặc đại diện hai bên không hợp lệ.')
    match = ctx.session.get(Match, match_id)
    if match is None:
        raise DomainError('NOT_FOUND', 'Không tìm thấy trận.', 404)
    if match.booking_id:
        return _hold(ctx.session.get(Booking, match.booking_id))
    pitch = _locked_active_pitch(ctx, pitch_id)
    policy.validate_slot(ctx.now(), start_time, end_time)
    if find_conflict(ctx, pitch_id, start_time, end_time):
        raise SlotUnavailable()
    return _hold(_insert_hold(ctx, pitch=pitch, user_id=source_user_id, start=start_time, end=end_time,
                              payment_rule=payment_rule, payer_ids=[source_user_id, opponent_user_id],
                              hold_seconds=hold_seconds))

def payments_of(ctx, booking_id):
    return list(ctx.session.scalars(select(Payment).where(Payment.booking_id == booking_id).order_by(Payment.payment_id)))

def lock_booking_graph(ctx, booking_id, extra_pitch_ids=()):
    """Discover without locks, then lock Pitch -> Post -> Match -> Booking -> Payment and re-read."""
    found = ctx.session.get(Booking, booking_id)
    if found is None:
        raise DomainError('NOT_FOUND', 'Không tìm thấy booking.', 404)
    pitch_id = found.pitch_id
    match = ctx.session.scalar(select(Match).where(Match.booking_id == booking_id).order_by(Match.match_id.desc()))
    ctx.locks.lock(Pitch, [pitch_id, *extra_pitch_ids])
    if match:
        ctx.locks.lock(MatchPost, [match.post_id, match.opponent_post_id])
        ctx.locks.lock(Match, [match.match_id])
    booking = ctx.locks.lock(Booking, [booking_id])[0]
    if booking.pitch_id != pitch_id:
        raise DomainError('STATE_CONFLICT', 'Booking vừa được đổi lịch. Vui lòng thử lại.')
    ids = ctx.session.scalars(select(Payment.payment_id).where(Payment.booking_id == booking_id)).all()
    return booking, ctx.locks.lock(Payment, ids)

def paid_deposit_by_user(payments):
    paid = {}
    for payment in payments:
        if payment.payment_type == 'BOOKING_DEPOSIT' and payment.status == 'SUCCESS':
            paid[payment.user_id] = paid.get(payment.user_id, Decimal('0')) + Decimal(payment.amount)
    return paid

def payer_progress(ctx, booking, payments=None):
    paid = paid_deposit_by_user(payments if payments is not None else payments_of(ctx, booking.booking_id))
    result = []
    for item in booking.payer_plan or []:
        required, got = Decimal(item['amount']), paid.get(item['user_id'], Decimal('0'))
        status = 'PAID' if got >= required else 'PARTIAL' if got > 0 else 'UNPAID'
        result.append({'user_id': item['user_id'], 'required_amount': policy.money(required),
                       'paid_amount': policy.money(got), 'status': status})
    return result

def confirm_if_deposit_complete(ctx, *, booking_id):
    """Every payer must have paid their own share, in time. Caller holds the booking locks."""
    booking = ctx.session.get(Booking, booking_id)
    if booking.status == 'CONFIRMED':
        return True
    if booking.status != 'PENDING_HOLD' or ctx.now() >= booking.hold_expires_at or not booking.payer_plan:
        return False
    ctx.session.flush()
    if any(item['status'] != 'PAID' for item in payer_progress(ctx, booking)):
        return False
    booking.status = 'CONFIRMED'
    ctx.session.flush()
    return True

def required_share(booking, user_id):
    """The deposit this payer owes for the booking, or None when they are not a payer."""
    item = next((p for p in booking.payer_plan or [] if p['user_id'] == user_id), None)
    return Decimal(item['amount']) if item else None

def summary_text(ctx, booking):
    """One line that names the booking in messages: number, pitch, time and day."""
    from app.utils.time import VIETNAM
    pitch = ctx.session.get(Pitch, booking.pitch_id)
    start, end = booking.start_time.astimezone(VIETNAM), booking.end_time.astimezone(VIETNAM)
    return (f'Booking #{booking.booking_id} - {pitch.pitch_name if pitch else f"sân #{booking.pitch_id}"}, '
            f'{start:%H:%M}-{end:%H:%M} ngày {start:%d/%m/%Y}.')

def is_party(booking, user_id):
    return booking.user_id == user_id or any(p['user_id'] == user_id for p in booking.payer_plan or [])

def booking_data(ctx, booking, admin=False, payments=None, pitch_names=None):
    result = columns(booking, 'booking_id pitch_id user_id start_time end_time total_amount deposit_amount '
                     'booking_type status payment_rule created_at')
    result['hold_expires_at'] = booking.hold_expires_at if booking.status == 'PENDING_HOLD' else None
    rows = payments if payments is not None else payments_of(ctx, booking.booking_id)
    result['payer_progress'] = payer_progress(ctx, booking, rows)
    from app.services.payment_service import is_demo_payment
    result['is_demo'] = any(is_demo_payment(p) for p in rows)
    # What the customer has paid so far for this booking (net of refunds) and what is still due at the pitch.
    collected = sum((Decimal(p.amount) for p in rows if p.payment_type in ('BOOKING_DEPOSIT', 'BOOKING_REMAINING_PAYMENT')
                     and p.status in ('SUCCESS', 'REFUNDED')), Decimal('0'))
    collected -= sum((Decimal(p.amount) for p in rows if p.payment_type == 'REFUND' and p.status == 'SUCCESS'), Decimal('0'))
    result['paid_amount'] = policy.money(collected)
    owed = Decimal(booking.total_amount) - collected if booking.status in ('CONFIRMED', 'PENDING_HOLD') else Decimal('0')
    result['outstanding_amount'] = policy.money(max(owed, Decimal('0')))
    if pitch_names is not None and booking.pitch_id in pitch_names:
        result['pitch_name'] = pitch_names[booking.pitch_id]
    else:
        pitch = ctx.session.get(Pitch, booking.pitch_id)
        result['pitch_name'] = pitch.pitch_name if pitch else None
    if admin:
        result['note'] = booking.note
        result.update(series_id=booking.series_id, arrival_status=booking.arrival_status, arrived_at=booking.arrived_at)
    return result

def read_for_actor(ctx, *, booking_id, actor):
    """Booking view inside match details: the route has already checked the viewer may see this match."""
    booking = ctx.session.get(Booking, booking_id)
    if booking is None:
        return None
    result = booking_data(ctx, booking, admin=actor.role == 'ADMIN')
    if actor.role != 'ADMIN' and not is_party(booking, actor.user_id):
        # Team members see progress only, not the amounts other people paid.
        result['payer_progress'] = [{'user_id': p['user_id'], 'status': p['status']} for p in result['payer_progress']]
        result.pop('paid_amount', None)
        result.pop('outstanding_amount', None)
    return result

def payments_by_booking(ctx, bookings):
    """One query for a whole page of bookings, grouped by booking_id."""
    ids = [b.booking_id for b in bookings]
    grouped = {booking_id: [] for booking_id in ids}
    if ids:
        for payment in ctx.session.scalars(select(Payment).where(Payment.booking_id.in_(ids)).order_by(Payment.payment_id)):
            grouped[payment.booking_id].append(payment)
    return grouped

def pitch_names(ctx, bookings):
    """One query for the pitch names of a page of bookings."""
    ids = {b.pitch_id for b in bookings}
    return dict(ctx.session.execute(select(Pitch.pitch_id, Pitch.pitch_name).where(Pitch.pitch_id.in_(ids))).all()) if ids else {}
