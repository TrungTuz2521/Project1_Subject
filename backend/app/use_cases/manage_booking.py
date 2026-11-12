from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
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
def admin_create_booking(actor, *, pitch_id, start_time, end_time, note=None, user_id=None, guest=None, payment=None, repeat_weeks=1):
    """Counter booking for an existing account (user_id) or a walk-in known only by name and phone (guest).

    The customer is standing at the counter, so there is no payment hold: the slot is CONFIRMED at once.
    payment = {amount, method, reference} records money taken now on the first session; the deposit share
    first, any extra as remaining payment. Whatever is still owed is collected when the customer arrives.
    repeat_weeks > 1 books the same pitch and time every week for a regular customer: weeks already taken
    are skipped and reported, all created sessions share one series_id."""
    from app.models import Payment
    from app.services import payment_service
    from app.use_cases.process_payment import _booking_summary, _vnd
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        if guest is not None:
            customer = auth_service.walk_in_customer(ctx, guest['full_name'], guest['phone'])
            note = policy.add_note(note, f'Khach vang lai: {customer.full_name} - {customer.phone}')
        else:
            customer = ctx.session.get(User, user_id)
            if customer is None or customer.status != 'ACTIVE' or customer.role != 'PLAYER':
                invalid('user_id', 'Người đặt phải là tài khoản người chơi đang hoạt động.')
        series_id = uuid4().hex if repeat_weeks > 1 else None
        if series_id:
            note = policy.add_note(note, f'Khach co dinh {repeat_weeks} tuan')
        created, skipped = [], []
        for week in range(repeat_weeks):
            start, end = start_time + timedelta(weeks=week), end_time + timedelta(weeks=week)
            try:
                item = booking_service.create_direct_hold(ctx, pitch_id=pitch_id, user_id=customer.user_id, start_time=start, end_time=end,
                                                          booking_type='MANUAL_ADMIN', note=note, max_advance_days=policy.ADMIN_MAX_ADVANCE_DAYS)
            except DomainError as error:
                if week == 0:
                    raise  # The session the customer asked for must exist; later weeks are best effort.
                skipped.append({'start_time': start, 'reason': error.message if error.code != 'VALIDATION_ERROR' else next(iter(error.fields.values()), error.message)})
                continue
            item.status, item.hold_expires_at, item.series_id = 'CONFIRMED', None, series_id
            created.append(item)
        booking = created[0]
        paid = Decimal(payment['amount']) if payment else Decimal('0')
        if paid > Decimal(booking.total_amount):
            invalid('payment.amount', f'Không thu quá giá sân {_vnd(booking.total_amount)}.')
        now = ctx.now()
        rows = []
        deposit_part = min(paid, Decimal(booking.deposit_amount))
        for kind, amount, suffix in (('BOOKING_DEPOSIT', deposit_part, 'D'), ('BOOKING_REMAINING_PAYMENT', paid - deposit_part, 'R')):
            if amount > 0:
                reference = (payment.get('reference') or '').strip()
                rows.append(Payment(user_id=customer.user_id, booking_id=booking.booking_id, amount=policy.money(amount), payment_type=kind,
                                    payment_method=payment['method'], transaction_code=f'CTR-{booking.booking_id}-{suffix}',
                                    recorded_by_admin_id=actor.user_id, status='SUCCESS', paid_at=now,
                                    note=(f'Thu tai quay' + (f'; ref={reference}' if reference else ''))[:255]))
        ctx.session.add_all(rows)
        ctx.session.flush()
        owed = Decimal(booking.total_amount) - paid
        regular = f' Khách cố định: đã giữ {len(created)} buổi hằng tuần.' if series_id else ''
        notification_service.notify(ctx, [customer.user_id], 'BOOKING_CONFIRMED', 'Đặt sân thành công',
            f'{_booking_summary(ctx, booking)} Đã thanh toán {_vnd(paid)}' + (f', còn {_vnd(owed)} trả khi đến sân.' if owed > 0 else ', đã trả đủ.') + regular)
        result = booking_service.booking_data(ctx, booking, admin=True, payments=rows)
        if series_id:
            result['series'] = {'series_id': series_id, 'requested_weeks': repeat_weeks,
                                'created': [{'booking_id': b.booking_id, 'start_time': b.start_time, 'total_amount': policy.money(b.total_amount)} for b in created],
                                'skipped': skipped}
        return result

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
        from app.services.pricing import slot_price
        if slot_price(ctx, target, start_time)[0] != Decimal(booking.total_amount):
            raise DomainError('PRICE_CHANGE_REQUIRES_REBOOK', 'Lượt mới khác giá (giờ thường/cao điểm hoặc sân khác giá): cần hủy và đặt lại.')
        policy.validate_slot(ctx.now(), start_time, end_time)
        if booking_service.find_conflict(ctx, target_id, start_time, end_time, exclude_booking_id=booking_id):
            raise SlotUnavailable()
        match = ctx.session.scalar(select(Match).where(Match.booking_id == booking_id).order_by(Match.match_id.desc()))
        if match:
            posts = [ctx.session.get(MatchPost, pid) for pid in (match.post_id, match.opponent_post_id)]
            if target.pitch_type != ctx.session.get(Pitch, booking.pitch_id).pitch_type:
                raise DomainError('STATE_CONFLICT', 'Kèo hai đội không được đổi sang loại sân khác.')
            match.match_time = start_time
            for post in posts:
                post.match_time, post.end_time = start_time, end_time
                post.pitch_id = target_id
        # Requests built on this booking (find an opponent, find more players) and players who joined follow the new time.
        tied = list(ctx.session.scalars(select(MatchPost).where(MatchPost.booking_id == booking_id, MatchPost.status.in_(('OPEN', 'MATCHED')))))
        tied += list(ctx.session.scalars(select(MatchPost).where(MatchPost.matched_post_id.in_([p.post_id for p in tied] or [0]), MatchPost.status == 'MATCHED')))
        for post in tied:
            if post.preferred_dates is None or post.status == 'MATCHED':
                post.match_time, post.end_time, post.pitch_id = start_time, end_time, target_id
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
            'price_per_slot': policy.money(pitch.price_per_slot),
            'peak_price_per_slot': policy.money(pitch.peak_price_per_slot) if pitch.peak_price_per_slot is not None else None,
            'status': pitch.status}

@retry_conflicts
def create_pitch(actor, *, pitch_name, pitch_type, price_per_slot, peak_price_per_slot=None):
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        complex_id = ctx.session.scalar(select(FieldComplex.complex_id).order_by(FieldComplex.complex_id).limit(1))
        if complex_id is None:
            raise DomainError('STATE_CONFLICT', 'Chưa có cụm sân.')
        pitch = Pitch(complex_id=complex_id, pitch_name=pitch_name, pitch_type=pitch_type, price_per_slot=price_per_slot,
                      peak_price_per_slot=peak_price_per_slot, status='ACTIVE')
        ctx.session.add(pitch)
        ctx.session.flush()
        return pitch_data(pitch)

@retry_conflicts
def update_pitch(actor, *, pitch_id, changes, confirm=False):
    """Taking a pitch out of service does not touch its bookings, so the Admin must see them first."""
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        rows = ctx.locks.lock(Pitch, [pitch_id])
        if not rows:
            raise DomainError('NOT_FOUND', 'Không tìm thấy sân.', 404)
        if changes.get('status', 'ACTIVE') != 'ACTIVE' and rows[0].status == 'ACTIVE' and not confirm:
            upcoming = ctx.session.scalars(select(Booking).where(Booking.pitch_id == pitch_id, Booking.end_time > ctx.now(),
                Booking.status.in_(('CONFIRMED', 'PENDING_HOLD'))).order_by(Booking.start_time)).all()
            if upcoming:
                from app.utils.time import VIETNAM
                listed = ', '.join(f'#{b.booking_id} {b.start_time.astimezone(VIETNAM):%H:%M %d/%m}' for b in upcoming[:10])
                raise DomainError('PITCH_HAS_BOOKINGS', f'Sân còn {len(upcoming)} booking sắp tới.', 409,
                                  {'status': f'Các booking vẫn giữ nguyên, hãy đổi lịch hoặc hủy từng booking: {listed}' + (' …' if len(upcoming) > 10 else '')})
        # Existing bookings keep the amounts stored on them when the price changes.
        for key, value in changes.items():
            setattr(rows[0], key, value)
        ctx.session.flush()
        return pitch_data(rows[0])

@retry_conflicts
def update_peak_hours(actor, *, peak_start_time, peak_end_time, weekend_is_peak):
    from app.services.pricing import peak_config
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        complex_row = ctx.session.scalar(select(FieldComplex).order_by(FieldComplex.complex_id).limit(1).with_for_update())
        if complex_row is None:
            raise DomainError('STATE_CONFLICT', 'Chưa có cụm sân.')
        complex_row.peak_start_time, complex_row.peak_end_time = peak_start_time, peak_end_time
        complex_row.weekend_is_peak = weekend_is_peak
        ctx.session.flush()
        return peak_config(complex_row)

ARRIVAL_EARLY = timedelta(hours=2)

@retry_conflicts
def mark_arrival(actor, *, booking_id, status):
    """Counter check-in. ARRIVED from 2 hours before kick-off until the slot ends; NO_SHOW once it has started;
    None undoes a mistake. Money is untouched: the deposit rule only applies when a booking is cancelled."""
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        booking, _ = booking_service.lock_booking_graph(ctx, booking_id)
        if booking.booking_type == 'MAINTENANCE_LOCK' or booking.status != 'CONFIRMED':
            raise DomainError('STATE_CONFLICT', 'Chỉ đánh dấu khách cho booking đã xác nhận.')
        now = ctx.now()
        if status == 'ARRIVED' and not booking.start_time - ARRIVAL_EARLY <= now < booking.end_time:
            raise DomainError('STATE_CONFLICT', 'Chỉ nhận khách từ 2 giờ trước giờ đá đến hết lượt.')
        if status == 'NO_SHOW' and now < booking.start_time:
            raise DomainError('STATE_CONFLICT', 'Chưa tới giờ đá, chưa thể đánh dấu không đến.')
        booking.arrival_status, booking.arrived_at = status, now if status == 'ARRIVED' else None
        ctx.session.flush()
        return booking_service.booking_data(ctx, booking, admin=True)
