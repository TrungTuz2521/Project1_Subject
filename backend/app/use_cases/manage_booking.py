from decimal import Decimal
from sqlalchemy import select
from app.contracts.errors import DomainError, SlotUnavailable, invalid
from app.infrastructure.retry import retry_conflicts
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Booking, FieldComplex, Match, MatchPost, Pitch, User
from app.services import auth_service, booking_policy as policy, booking_service, notification_service

@retry_conflicts
def create_booking(actor, *, pitch_id, start_time, end_time):
    with UnitOfWork() as ctx:
        auth_service.require_player(ctx, actor)
        booking = booking_service.create_direct_hold(ctx, pitch_id=pitch_id, user_id=actor.user_id, start_time=start_time, end_time=end_time)
        return booking_service.booking_data(ctx, booking, payments=[])

@retry_conflicts
def admin_create_booking(actor, *, user_id, pitch_id, start_time, end_time, note=None):
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        customer = ctx.session.get(User, user_id)
        if customer is None or customer.status != 'ACTIVE':
            invalid('user_id', 'Người đặt phải là tài khoản đang hoạt động.')
        booking = booking_service.create_direct_hold(ctx, pitch_id=pitch_id, user_id=user_id, start_time=start_time, end_time=end_time,
                                                     booking_type='MANUAL_ADMIN', note=note)
        return booking_service.booking_data(ctx, booking, admin=True, payments=[])

@retry_conflicts
def reschedule_booking(actor, *, booking_id, start_time, end_time, pitch_id=None, reason):
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        found = ctx.session.get(Booking, booking_id)
        if found is None:
            raise DomainError('NOT_FOUND', 'Không tìm thấy booking.', 404)
        target_id = pitch_id or found.pitch_id
        booking, _ = booking_service.lock_booking_graph(ctx, booking_id, extra_pitch_ids=[target_id])
        if booking.status != 'CONFIRMED':
            raise DomainError('STATE_CONFLICT', 'Chỉ đổi lịch booking đã xác nhận.')
        target = ctx.session.get(Pitch, target_id)
        if target is None or target.status != 'ACTIVE':
            raise SlotUnavailable()
        if Decimal(target.price_per_slot) != Decimal(booking.total_amount):
            raise DomainError('PRICE_CHANGE_REQUIRES_REBOOK', 'Slot khác giá: cần hủy, hoàn và tạo booking mới.')
        policy.validate_slot(ctx.now(), start_time, end_time)
        if booking_service.find_conflict(ctx, target_id, start_time, end_time, exclude_booking_id=booking_id):
            raise SlotUnavailable()
        match = ctx.session.scalar(select(Match).where(Match.booking_id == booking_id))
        if match:
            posts = [ctx.session.get(MatchPost, pid) for pid in (match.post_id, match.opponent_post_id)]
            if target.pitch_type != ctx.session.get(Pitch, booking.pitch_id).pitch_type:
                raise DomainError('STATE_CONFLICT', 'Kèo hai đội không được đổi sang loại sân khác.')
            match.match_time = start_time
            for post in posts:
                post.match_time, post.end_time = start_time, end_time
                post.pitch_id = target_id
        booking.pitch_id, booking.start_time, booking.end_time = target_id, start_time, end_time
        booking.note = policy.add_note(booking.note, f'Doi lich boi admin {actor.user_id}: {reason}')
        payers = {p['user_id'] for p in booking.payer_plan or []} | {booking.user_id}
        notification_service.notify(ctx, payers, 'BOOKING_CONFIRMED', 'Lịch sân đã thay đổi', 'Admin đã đổi lịch booking của bạn. Vui lòng xem giờ mới.')
        ctx.session.flush()
        return booking_service.booking_data(ctx, booking, admin=True)

@retry_conflicts
def create_maintenance_lock(actor, *, pitch_id, start_time, end_time, reason):
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        if end_time <= start_time or start_time < ctx.now():
            invalid('start_time', 'Khoảng bảo trì phải ở tương lai và kết thúc sau khi bắt đầu.')
        if not ctx.locks.lock(Pitch, [pitch_id]):
            raise DomainError('NOT_FOUND', 'Không tìm thấy sân.', 404)
        # Customer bookings must be cancelled and refunded first, never overwritten.
        if booking_service.find_conflict(ctx, pitch_id, start_time, end_time):
            raise SlotUnavailable()
        booking = Booking(pitch_id=pitch_id, user_id=actor.user_id, start_time=start_time, end_time=end_time, total_amount=policy.money(0), deposit_amount=policy.money(0),
                          booking_type='MAINTENANCE_LOCK', status='MAINTENANCE', note=reason)
        ctx.session.add(booking)
        ctx.session.flush()
        return booking_service.booking_data(ctx, booking, admin=True, payments=[])

@retry_conflicts
def cancel_maintenance_lock(actor, *, booking_id, reason):
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        booking, _ = booking_service.lock_booking_graph(ctx, booking_id)
        if booking.booking_type != 'MAINTENANCE_LOCK':
            raise DomainError('NOT_FOUND', 'Không tìm thấy khóa bảo trì.', 404)
        if booking.status == 'MAINTENANCE':
            booking.status = 'CANCELLED'
            booking.note = policy.add_note(booking.note, f'Huy bao tri: {reason}')
        return booking_service.booking_data(ctx, booking, admin=True, payments=[])

def pitch_data(pitch):
    return {'pitch_id': pitch.pitch_id, 'complex_id': pitch.complex_id, 'pitch_name': pitch.pitch_name, 'pitch_type': pitch.pitch_type,
            'price_per_slot': policy.money(pitch.price_per_slot), 'status': pitch.status}

@retry_conflicts
def create_pitch(actor, *, pitch_name, pitch_type, price_per_slot):
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        complex_id = ctx.session.scalar(select(FieldComplex.complex_id).order_by(FieldComplex.complex_id).limit(1))
        if complex_id is None:
            raise DomainError('STATE_CONFLICT', 'Chưa có cụm sân.')
        pitch = Pitch(complex_id=complex_id, pitch_name=pitch_name, pitch_type=pitch_type, price_per_slot=price_per_slot, status='ACTIVE')
        ctx.session.add(pitch)
        ctx.session.flush()
        return pitch_data(pitch)

@retry_conflicts
def update_pitch(actor, *, pitch_id, changes):
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        rows = ctx.locks.lock(Pitch, [pitch_id])
        if not rows:
            raise DomainError('NOT_FOUND', 'Không tìm thấy sân.', 404)
        # Existing bookings keep the amounts stored on them when the price changes.
        for key, value in changes.items():
            setattr(rows[0], key, value)
        ctx.session.flush()
        return pitch_data(rows[0])
