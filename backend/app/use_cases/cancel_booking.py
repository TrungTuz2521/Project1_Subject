from sqlalchemy import select
from app.contracts.errors import DomainError
from app.infrastructure.retry import retry_conflicts
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Match, Payment
from app.services import auth_service, booking_policy as policy, booking_service, match_service, notification_service, payment_service

MANUAL_METHODS = ('CASH', 'BANK_TRANSFER')

def close_booking(ctx, booking, *, status, cause, actor_id, reason, cancelling_user_id=None):
    """Shared orchestration for timeout/cancel. Caller holds lock_booking_graph."""
    booking.status = status
    actor = f'user {actor_id}' if actor_id else 'he thong'
    booking.note = policy.add_note(booking.note, f'{cause} boi {actor}: {reason}')
    ctx.session.flush()
    plan = payment_service.plan_refunds(ctx, booking_id=booking.booking_id, cause=cause, cancelling_user_id=cancelling_user_id)
    payment_service.execute_refund_plan(ctx, plan, note=cause)
    match_service.cancel_for_booking(ctx, booking_id=booking.booking_id, cause=cause, actor_id=actor_id)
    payers = {p['user_id'] for p in booking.payer_plan or []} | {booking.user_id}
    if status == 'EXPIRED':
        notification_service.notify(ctx, payers, 'BOOKING_EXPIRED', 'Hết hạn giữ sân', 'Lượt giữ sân đã hết hạn do chưa đủ cọc.')
    ctx.session.flush()
    return plan

def _close_for_actor(ctx, actor, booking, reason, customer_cancel=False):
    """Cause comes from role and time, never from the request. Repeated calls create no new refund."""
    if booking.status == 'CANCELLED':
        return None
    if booking.status not in ('PENDING_HOLD', 'CONFIRMED'):
        raise DomainError('STATE_CONFLICT', 'Không thể hủy booking ở trạng thái hiện tại.')
    if booking.status == 'PENDING_HOLD' and ctx.now() >= booking.hold_expires_at:
        return close_booking(ctx, booking, status='EXPIRED', cause='HOLD_TIMEOUT', actor_id=None, reason='Hết hạn trước khi hủy')
    if actor.role == 'ADMIN' and customer_cancel:
        # The customer called the counter to cancel: same rule as cancelling online, the deposit is kept.
        if ctx.session.scalar(select(Match.match_id).where(Match.booking_id == booking.booking_id)):
            raise DomainError('STATE_CONFLICT', 'Trận ghép hai đội không hủy thay một bên được; hãy để đội đó tự hủy hoặc chọn "Sân có sự cố".')
        return close_booking(ctx, booking, status='CANCELLED', cause='USER_CANCEL', actor_id=actor.user_id,
                             reason=f'Khach huy qua quay: {reason}', cancelling_user_id=booking.user_id)
    if actor.role == 'ADMIN':
        return close_booking(ctx, booking, status='CANCELLED', cause='ADMIN_INCIDENT', actor_id=actor.user_id, reason=reason)
    if ctx.now() >= booking.start_time:
        raise DomainError('STATE_CONFLICT', 'Đã đến giờ đá, không thể tự hủy.')
    return close_booking(ctx, booking, status='CANCELLED', cause='USER_CANCEL', actor_id=actor.user_id, reason=reason,
                         cancelling_user_id=actor.user_id)

@retry_conflicts
def cancel_booking(actor, *, booking_id, reason, admin_route=False, customer_cancel=False):
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor) if admin_route else auth_service.require_active_actor(ctx, actor)
        booking, _ = booking_service.lock_booking_graph(ctx, booking_id)
        if actor.role != 'ADMIN' and not booking_service.is_party(booking, actor.user_id):
            raise DomainError('NOT_FOUND', 'Không tìm thấy booking.', 404)
        plan = _close_for_actor(ctx, actor, booking, reason, customer_cancel=customer_cancel and admin_route)
        result = booking_service.booking_data(ctx, booking, admin=actor.role == 'ADMIN')
        result['refund_summary'] = payment_service.refund_summary(ctx, booking_id, plan.cause if plan else None)
        return result

@retry_conflicts
def cancel_match(actor, *, match_id, reason):
    """Registered as app.extensions['cancel_match']; Đức's route has checked the viewer may act."""
    with UnitOfWork() as ctx:
        auth_service.require_active_actor(ctx, actor)
        match = ctx.session.get(Match, match_id)
        if match is None:
            raise DomainError('NOT_FOUND', 'Không tìm thấy trận.', 404)
        if match.status == 'COMPLETED':
            raise DomainError('STATE_CONFLICT', 'Trận đã kết thúc.')
        if not match.booking_id:
            if match.status != 'CANCELLED':
                raise DomainError('STATE_CONFLICT', 'Trận chưa có booking để hủy.')
            return dict(match_service.match_data(match), refund_summary=None)
        booking, _ = booking_service.lock_booking_graph(ctx, match.booking_id)
        if actor.role != 'ADMIN' and not booking_service.is_party(booking, actor.user_id):
            raise DomainError('NOT_FOUND', 'Không tìm thấy trận.', 404)
        plan = _close_for_actor(ctx, actor, booking, reason)
        result = match_service.match_data(ctx.session.get(Match, match_id))
        result['refund_summary'] = payment_service.refund_summary(ctx, booking.booking_id, plan.cause if plan else None)
        return result

@retry_conflicts
def refund_payment(actor, *, payment_id, reason):
    """Admin refund of one original. Gateway methods wait for the worker; CASH/BANK_TRANSFER means
    the Admin has handed the money back, so this call completes that refund. Returns (data, http_status)."""
    from app.contracts.dto import GatewayResult
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        original = ctx.session.get(Payment, payment_id)
        if original is None:
            raise DomainError('NOT_FOUND', 'Không tìm thấy giao dịch.', 404)
        if original.booking_id:
            booking_service.lock_booking_graph(ctx, original.booking_id)
        else:
            ctx.locks.lock(Payment, [payment_id])
        if original.payment_type not in payment_service.COLLECTED_TYPES or original.status != 'SUCCESS':
            existing = ctx.session.scalar(select(Payment).where(Payment.refund_for_payment_id == payment_id, Payment.status == 'SUCCESS'))
            if existing:
                return payment_service.payment_data(existing, admin=True), 200
            raise DomainError('STATE_CONFLICT', 'Chỉ hoàn giao dịch gốc đã thu thành công.')
        refund = payment_service.create_refund(ctx, original, note=policy.add_note(None, f'Admin {actor.user_id}: {reason}'))
        if original.payment_method in MANUAL_METHODS:
            payment_service.apply_verified_refund(ctx, GatewayResult('SUCCESS', refund.transaction_code, refund.amount))
            return payment_service.payment_data(refund, admin=True), 200
        return payment_service.payment_data(refund, admin=True), 202

def cancel_series(actor, *, series_id, reason, customer_cancel=False):
    """Cancels every future session of a regular customer's weekly series, one booking per transaction."""
    from app.models import Booking
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        ids = list(ctx.session.scalars(select(Booking.booking_id).where(Booking.series_id == series_id, Booking.status == 'CONFIRMED',
                                                                      Booking.start_time > ctx.now()).order_by(Booking.start_time)))
    if not ids:
        raise DomainError('NOT_FOUND', 'Không còn buổi nào sắp tới trong chuỗi này.', 404)
    results = [cancel_booking(actor, booking_id=booking_id, reason=reason, admin_route=True, customer_cancel=customer_cancel) for booking_id in ids]
    return {'series_id': series_id, 'cancelled': [r['booking_id'] for r in results],
            'refund_amount': policy.money(sum((r['refund_summary']['refund_amount'] for r in results), 0)),
            'forfeited_amount': policy.money(sum((r['refund_summary']['forfeited_amount'] for r in results), 0))}
