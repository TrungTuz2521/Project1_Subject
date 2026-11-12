from decimal import Decimal
from sqlalchemy import select
from app.models import Booking, Match, MatchPost, Team
from app.contracts.errors import DomainError
from app.services.notification_service import notify

def booking_teams(ctx, booking_id):
    """The two teams of a paired game, for display only: never infers a winner or who owes what."""
    match = ctx.session.scalar(select(Match).where(Match.booking_id == booking_id).order_by(Match.match_id.desc()))
    if not match:
        return None
    def party(post_id):
        post = ctx.session.get(MatchPost, post_id) if post_id else None
        team = ctx.session.get(Team, post.team_id) if post and post.team_id else None
        return dict(team_id=post.team_id if post else None, team_name=team.team_name if team else None,
                    representative_user_id=post.creator_id if post else None)
    return {'source': party(match.post_id), 'opponent': party(match.opponent_post_id)}

def confirm_after_deposit(ctx, *, booking_id, is_demo=False):
    match = ctx.session.scalar(select(Match).where(Match.booking_id == booking_id).order_by(Match.match_id.desc()))
    if not match:
        return None
    if match.status == 'CONFIRMED':
        return match
    if match.status != 'SUGGESTED':
        raise DomainError('STATE_CONFLICT', 'Trận không ở trạng thái chờ cọc.')
    booking = ctx.session.get(Booking, booking_id)
    if booking.status != 'CONFIRMED' or not booking.hold_expires_at or ctx.now() >= booking.hold_expires_at:
        raise DomainError('HOLD_EXPIRED', 'Booking chưa đủ điều kiện xác nhận.')
    posts = [ctx.session.get(MatchPost, pid) for pid in (match.post_id, match.opponent_post_id)]
    parties = {p.creator_id for p in posts}
    plan = booking.payer_plan or []
    if len(plan) != 2 or {p['user_id'] for p in plan} != parties:
        raise DomainError('STATE_CONFLICT', 'Kế hoạch cọc không khớp hai đại diện.')
    from app.services.booking_service import paid_deposit_by_user, payments_of
    paid = paid_deposit_by_user(payments_of(ctx, booking_id))
    for payer in plan:
        if paid.get(payer['user_id'], Decimal('0')) < Decimal(payer['amount']):
            raise DomainError('STATE_CONFLICT', 'Chưa đủ từng phần cọc.')
    match.status, match.confirmed_at = 'CONFIRMED', ctx.now()
    for post in posts:
        post.status = 'MATCHED'
    from app.services.match_requests import label
    notify(ctx, parties, 'MATCH_CONFIRMED', 'Trận DEMO đã xác nhận' if is_demo else 'Hai đội đã đặt đủ cọc',
        'Đã đủ cọc mô phỏng; không phải khoản thu ngân hàng.' if is_demo else
        f'Kèo lúc {label(match.match_time)} đã chốt. Phần tiền sân còn lại trả tại quầy theo thể thức hai đội đã chọn.', match_id=match.match_id)
    return match

def cancel_for_booking(ctx, *, booking_id, cause, actor_id):
    """Called after booking/refund planning, under the same ordered locks."""
    match = ctx.session.scalar(select(Match).where(Match.booking_id == booking_id).order_by(Match.match_id.desc()))
    if not match or match.status in ('CANCELLED', 'COMPLETED'):
        return match
    if cause not in ('HOLD_TIMEOUT', 'USER_CANCEL', 'ADMIN_INCIDENT', 'LATE_PAYMENT'):
        raise DomainError('STATE_CONFLICT', 'Nguyên nhân hủy không hợp lệ.')
    booking = ctx.session.get(Booking, booking_id).status
    if booking not in ('EXPIRED', 'CANCELLED') or (cause == 'HOLD_TIMEOUT' and booking != 'EXPIRED'):
        raise DomainError('STATE_CONFLICT', 'Booking chưa được hủy/hết hạn bởi orchestration.')
    from app.services.match_requests import release_match
    posts = [ctx.session.get(MatchPost, pid) for pid in (match.post_id, match.opponent_post_id) if pid]
    if cause == 'USER_CANCEL' and not any(p.creator_id == actor_id for p in posts):
        raise DomainError('FORBIDDEN', 'Người hủy không phải đại diện kèo.', 403)
    match.status = 'CANCELLED'
    ctx.session.flush()
    release_match(ctx, match, cause=cause, actor_id=actor_id)
    return match

def can_view(ctx, match, actor, admin=True):
    if admin and actor.role == 'ADMIN':
        return True
    for pid in (match.post_id, match.opponent_post_id):
        post = ctx.session.get(MatchPost, pid) if pid else None
        if post and post.creator_id == actor.user_id:
            return True
    return False

def match_data(match):
    return {k: getattr(match, k) for k in ('match_id', 'post_id', 'opponent_post_id', 'proposal_id', 'booking_id', 'match_time', 'status', 'confirmed_at')}

def complete_finished_matches():
    """Worker: a CONFIRMED match whose confirmed booking has ended becomes COMPLETED, which also frees
    its players for membership changes and keeps availability checks small."""
    from app.infrastructure.unit_of_work import UnitOfWork
    from app.models import Booking
    with UnitOfWork() as ctx:
        ids = list(ctx.session.scalars(select(Match.match_id).join(Booking, Booking.booking_id == Match.booking_id).where(
            Match.status == 'CONFIRMED', Booking.status == 'CONFIRMED', Booking.end_time <= ctx.now())))
    completed = 0
    for match_id in ids:
        with UnitOfWork() as ctx:
            match = ctx.locks.lock(Match, [match_id])[0]
            booking = ctx.session.get(Booking, match.booking_id)
            if match.status == 'CONFIRMED' and booking.status == 'CONFIRMED' and booking.end_time <= ctx.now():
                match.status = 'COMPLETED'
                completed += 1
    return completed
