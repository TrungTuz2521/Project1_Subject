"""Closing requests at the cut-off, reopening them after a cancelled game, and withdrawals."""
from datetime import timedelta
from sqlalchemy import select
from app.contracts.errors import DomainError
from app.models import Booking, Match, MatchParticipant, MatchPost, Payment, Pitch, Team, User
from app.services import booking_policy as policy, booking_service, notification_service
from app.services.match_requests.rules import (
    CUTOFF, JOIN, OPPONENT, RECRUIT, TYPES, active_match, fixed, hhmm, label, local_day, search_until)

def close_expired():
    """Stop searching one day before kick-off and tell the requester nothing was found."""
    from app.infrastructure.unit_of_work import UnitOfWork
    with UnitOfWork() as ctx:
        ids = list(ctx.session.scalars(select(MatchPost.post_id).where(MatchPost.status == 'OPEN', MatchPost.expiry_time <= ctx.now())))
    closed = 0
    for post_id in ids:
        with UnitOfWork() as ctx:
            post = ctx.session.get(MatchPost, post_id)
            ctx.locks.lock(Team, [post.team_id])
            post = ctx.locks.lock(MatchPost, [post_id])[0]
            if post.status != 'OPEN' or post.expiry_time > ctx.now():
                continue
            post.status = 'EXPIRED'
            closed += 1
            if post.post_type in TYPES:
                notification_service.notify(ctx, [post.creator_id], 'POST_EXPIRED', not_found_title(post), _not_found_text(post))
    return closed

def not_found_title(post):
    return {OPPONENT: 'Chưa tìm được đối', RECRUIT: 'Chưa tìm đủ người', JOIN: 'Chưa tìm được trận để đá ké'}[post.post_type]

def _not_found_text(post):
    if post.post_type == OPPONENT and post.booking_id:
        return f'Đến hạn 1 ngày trước giờ đá vẫn chưa có đội phù hợp. Lượt sân {label(post.match_time)} vẫn giữ cho đội bạn như lượt đặt bình thường.'
    if post.post_type == RECRUIT:
        missing = f' Vẫn còn thiếu {post.required_players} người.' if post.required_players else ''
        return f'Hệ thống đã dừng tìm người cho trận {label(post.match_time)}.{missing}'
    return 'Đến hạn 1 ngày trước giờ đá vẫn chưa tìm được kèo phù hợp. Bạn có thể gửi lại yêu cầu với khung giờ hoặc trình độ rộng hơn.'

def reopen(ctx, post, reason):
    """Back to searching when there is still time, otherwise closed with a notice."""
    if post.status not in ('MATCHED', 'OPEN'):
        return
    booking = ctx.session.get(Booking, post.booking_id) if post.booking_id else None
    if post.post_type == OPPONENT and post.booking_id and (booking is None or booking.status != 'CONFIRMED'):
        # The pitch this request came with is gone: keep looking for the same time without a booking.
        start = post.match_time or booking.start_time
        post.booking_id = None
        post.preferred_dates = [local_day(start).isoformat()]
        post.window_start, post.window_end = hhmm(start), hhmm(start + timedelta(minutes=policy.SLOT_MINUTES))
    if not fixed(post):
        post.match_time = post.end_time = post.pitch_id = None
    post.matched_post_id = None
    until = search_until(post, ctx.now())
    if until is None:
        post.status = 'EXPIRED'
        notification_service.notify(ctx, [post.creator_id], 'POST_EXPIRED', not_found_title(post), f'{reason} Đã quá hạn tìm lại (1 ngày trước giờ đá).')
        return
    post.status, post.expiry_time = 'OPEN', until
    notification_service.notify(ctx, [post.creator_id], 'MATCH_CANCELLED', 'Kèo đã hủy, hệ thống tìm lại', f'{reason} Hệ thống đang tìm đối khác cho bạn.')

def release_match(ctx, match, *, cause, actor_id=None):
    """Called after a paired game is cancelled (booking cancelled, hold timed out, or a captain withdrew)."""
    posts = [ctx.session.get(MatchPost, pid) for pid in (match.post_id, match.opponent_post_id) if pid]
    paid = set()
    if cause == 'HOLD_TIMEOUT' and match.booking_id:
        paid = set(booking_service.paid_deposit_by_user(booking_service.payments_of(ctx, match.booking_id)))
    for post in posts:
        if post.post_type not in TYPES or post.status not in ('MATCHED', 'OPEN', 'LOCKED'):
            continue
        if post.status == 'LOCKED':
            post.status = 'MATCHED'
        if cause == 'USER_CANCEL' and post.creator_id == actor_id:
            post.status = 'CANCELLED'
        elif cause == 'HOLD_TIMEOUT' and post.creator_id not in paid:
            post.status = 'CANCELLED'
            notification_service.notify(ctx, [post.creator_id], 'MATCH_CANCELLED', 'Kèo đã hủy vì chưa đặt cọc',
                                        'Đội bạn chưa trả phần cọc đúng hạn nên kèo đã hủy và yêu cầu tìm đối đã đóng.', match_id=match.match_id)
        else:
            why = {'HOLD_TIMEOUT': 'Đội kia chưa đặt cọc đúng hạn, phần cọc của bạn sẽ được hoàn.',
                   'USER_CANCEL': 'Đội kia đã hủy kèo.',
                   'ADMIN_INCIDENT': 'Sân báo sự cố nên kèo đã hủy.'}.get(cause, 'Kèo đã hủy.')
            reopen(ctx, post, why)

def booking_closed(ctx, booking_id):
    """A booking was cancelled or expired: requests that depended on it stop."""
    for post in ctx.session.scalars(select(MatchPost).where(MatchPost.booking_id == booking_id, MatchPost.status.in_(('OPEN', 'MATCHED')))):
        if post.post_type == RECRUIT:
            _close_recruit(ctx, post, 'Lượt sân của trận đã bị hủy.')
        elif post.post_type == OPPONENT and post.status == 'OPEN':
            post.status = 'CANCELLED'
            notification_service.notify(ctx, [post.creator_id], 'POST_EXPIRED', 'Đã dừng tìm đối', 'Lượt sân gắn với yêu cầu tìm đối đã bị hủy.')

def _close_recruit(ctx, recruit, reason):
    recruit.status = 'CANCELLED'
    for participant in ctx.session.scalars(select(MatchParticipant).where(MatchParticipant.post_id == recruit.post_id, MatchParticipant.status == 'ACCEPTED')):
        participant.status = 'CANCELLED'
    for joiner in ctx.session.scalars(select(MatchPost).where(MatchPost.matched_post_id == recruit.post_id, MatchPost.status == 'MATCHED')):
        reopen(ctx, joiner, f'Trận bạn định đá ké lúc {label(recruit.match_time)} đã hủy. {reason}')

def cancel_request(actor, post_id):
    """The requester withdraws. A paired game can be withdrawn only more than a day before kick-off."""
    from app.infrastructure.unit_of_work import UnitOfWork
    with UnitOfWork() as ctx:
        post = ctx.session.get(MatchPost, post_id)
        if post is None or post.creator_id != actor.user_id or post.post_type not in TYPES:
            raise DomainError('NOT_FOUND', 'Không tìm thấy yêu cầu.', 404)
        match = active_match(ctx, post_id) if post.post_type == OPPONENT and post.status == 'MATCHED' else None
        booking = ctx.session.get(Booking, match.booking_id) if match and match.booking_id else None
    if booking is not None and booking.payment_rule not in (None, 'DIRECT_BOOKING'):
        # The system booked this pitch for both teams: cancelling the game is cancelling that booking.
        guard_cutoff(post, ctx.now())
        from app.use_cases.cancel_booking import cancel_match
        cancel_match(actor, match_id=match.match_id, reason='Đội trưởng hủy kèo')
        with UnitOfWork() as ctx:
            return ctx.session.get(MatchPost, post_id)
    with UnitOfWork() as ctx:
        post = ctx.session.get(MatchPost, post_id)
        if post.status in ('CANCELLED', 'EXPIRED'):
            return post
        if post.status == 'OPEN' and post.post_type != RECRUIT:
            ctx.locks.lock(MatchPost, [post_id])
            post.status = 'CANCELLED'
            return post
        guard_cutoff(post, ctx.now())
        if post.post_type == RECRUIT:
            ctx.locks.lock(MatchPost, [post_id])
            _close_recruit(ctx, post, 'Đội trưởng đã hủy yêu cầu tìm người.')
            return post
        if post.post_type == JOIN:
            _withdraw_join(ctx, post)
            return post
        _withdraw_from_match(ctx, actor, post)
        return post

def guard_cutoff(post, now):
    if post.match_time and post.match_time - now < CUTOFF:
        raise DomainError('TOO_LATE', 'Còn dưới 1 ngày trước giờ đá, vui lòng gọi quầy để hủy.')

def _withdraw_join(ctx, post):
    recruit = ctx.session.get(MatchPost, post.matched_post_id) if post.matched_post_id else None
    ctx.locks.lock(MatchPost, [post.post_id, recruit.post_id if recruit else None])
    post.status = 'CANCELLED'
    if recruit is None:
        return
    participant = ctx.session.scalar(select(MatchParticipant).where(MatchParticipant.post_id == recruit.post_id, MatchParticipant.user_id == post.creator_id))
    if participant:
        participant.status = 'CANCELLED'
    if recruit.status in ('OPEN', 'MATCHED'):
        recruit.required_players = (recruit.required_players or 0) + post.current_players
        if recruit.status == 'MATCHED':
            recruit.status = 'OPEN'
            recruit.expiry_time = recruit.match_time - CUTOFF
    who = ctx.session.get(User, post.creator_id)
    notification_service.notify(ctx, [recruit.creator_id], 'MATCH_CANCELLED', 'Người đá ké đã rút',
        f'{who.full_name} không đá cùng trận {label(recruit.match_time)} nữa. Hệ thống tiếp tục tìm thêm người.')

def _withdraw_from_match(ctx, actor, post):
    """Pairing on a booking one team made itself (no shared deposit plan)."""
    match = active_match(ctx, post.post_id)
    if match is None:
        post.status = 'CANCELLED'
        return
    posts = [ctx.session.get(MatchPost, pid) for pid in (match.post_id, match.opponent_post_id)]
    other = next(p for p in posts if p.post_id != post.post_id)
    booking_ids = [match.booking_id] + [p.booking_id for p in posts if p.booking_id and p.booking_id != match.booking_id]
    ctx.locks.lock(Pitch, [ctx.session.get(Booking, bid).pitch_id for bid in booking_ids])
    ctx.locks.lock(MatchPost, [p.post_id for p in posts])
    ctx.locks.lock(Match, [match.match_id])
    ctx.locks.lock(Booking, booking_ids)
    kept = ctx.session.get(Booking, match.booking_id)
    payments = booking_service.payments_of(ctx, kept.booking_id)
    ctx.locks.lock(Payment, [p.payment_id for p in payments])
    moved = lambda user_id: [p for p in payments if p.user_id == user_id and p.status == 'SUCCESS'
                             and p.payment_type == 'BOOKING_DEPOSIT' and 'MERGED_FROM' in (p.note or '')]
    refunded = False
    if post.booking_id == kept.booking_id:
        # The pitch owner withdraws and keeps the pitch. A team whose booking was merged in gets its deposit back
        # and searches again without a pitch (reopen sees its own booking is closed).
        if other.booking_id and other.booking_id != kept.booking_id:
            from app.services import payment_service
            for payment in moved(other.creator_id):
                payment_service.create_refund(ctx, payment, note='Doi chu san huy keo da gop')
                refunded = True
        tail = ' Lượt sân vẫn giữ cho bạn; muốn hủy sân hãy vào Lịch đã đặt.'
    else:
        # The visiting team withdraws: a deposit it merged in goes back to its own cancelled booking, so it is forfeited.
        if post.booking_id:
            for payment in moved(post.creator_id):
                payment.booking_id = post.booking_id
                payment.note = policy.add_note(payment.note, 'Huy keo: tra ve booking goc, mat coc')
        tail = ''
    match.status = 'CANCELLED'
    post.status = 'CANCELLED'
    ctx.session.flush()
    reopen(ctx, other, 'Đội kia đã hủy kèo.' + (' Tiền cọc đội bạn đã gộp sẽ được hoàn.' if refunded else ''))
    notification_service.notify(ctx, [post.creator_id], 'MATCH_CANCELLED', 'Bạn đã hủy kèo', f'Kèo lúc {label(match.match_time)} đã hủy.{tail}', match_id=match.match_id)
