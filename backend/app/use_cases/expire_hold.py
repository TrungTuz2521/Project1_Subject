from app.infrastructure.unit_of_work import UnitOfWork
from app.services import booking_service
from app.use_cases.cancel_booking import close_booking

def expire_booking_hold(booking_id):
    """Worker only. Time is read after the locks, so a confirmed booking is never timed out."""
    with UnitOfWork() as ctx:
        booking, _ = booking_service.lock_booking_graph(ctx, booking_id)
        if booking.status != 'PENDING_HOLD' or ctx.now() < booking.hold_expires_at:
            return False
        close_booking(ctx, booking, status='EXPIRED', cause='HOLD_TIMEOUT', actor_id=None, reason='Hết hạn giữ sân')
        return True
