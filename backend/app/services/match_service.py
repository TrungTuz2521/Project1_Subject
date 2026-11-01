from decimal import Decimal
from sqlalchemy import select, text
from app.models import Match, MatchPost, Team, User, TeamMember
from app.contracts.dto import MatchParties
from app.contracts.errors import DomainError
from app.services.notification_service import notify

def get_booking_parties(ctx, *, booking_id):
    """Display teams/representatives only; never infer a winner or payment obligation."""
    match = ctx.session.scalar(select(Match).where(Match.booking_id == booking_id))
    if not match:
        return None
    def party(pid):
        post = ctx.session.get(MatchPost, pid)
        team = ctx.session.get(Team, post.team_id)
        return dict(team_id=post.team_id, team_name=team.team_name, representative_user_id=post.creator_id)
    return MatchParties(match.match_id, booking_id, party(match.post_id), party(match.opponent_post_id))

def confirm_after_deposit(ctx, *, booking_id):
    match = ctx.session.scalar(select(Match).where(Match.booking_id == booking_id))
    if not match:
        return None
    if match.status == 'CONFIRMED':
        return match
    if match.status != 'SUGGESTED':
        raise DomainError('STATE_CONFLICT', 'Trận không ở trạng thái chờ cọc.')
    booking = ctx.session.execute(text('SELECT status, hold_expires_at, payer_plan FROM bookings WHERE booking_id=:id'), {'id': booking_id}).mappings().one()
    from datetime import datetime, timezone
    deadline = booking['hold_expires_at']
    if isinstance(deadline, str):
        deadline = datetime.fromisoformat(deadline)
    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if booking['status'] != 'CONFIRMED' or not deadline or ctx.now() >= deadline:
        raise DomainError('HOLD_EXPIRED', 'Booking chưa đủ điều kiện xác nhận.')
    import json
    plan = booking['payer_plan']
    if isinstance(plan, str):
        plan = json.loads(plan)
    posts = [ctx.session.get(MatchPost, pid) for pid in (match.post_id, match.opponent_post_id)]
    parties = {p.creator_id for p in posts}
    if not isinstance(plan, list) or len(plan) != 2 or {p['user_id'] for p in plan} != parties:
        raise DomainError('STATE_CONFLICT', 'Kế hoạch cọc không khớp hai đại diện.')
    for payer in plan:
        paid = ctx.session.execute(text("SELECT COALESCE(SUM(amount),0) FROM payments WHERE booking_id=:id AND user_id=:uid AND payment_type='BOOKING_DEPOSIT' AND status='SUCCESS'"), {'id': booking_id, 'uid': payer['user_id']}).scalar()
        if Decimal(str(paid)) < Decimal(payer['amount']):
            raise DomainError('STATE_CONFLICT', 'Chưa đủ từng phần cọc.')
    match.status, match.confirmed_at = 'CONFIRMED', ctx.now()
    for post in posts:
        post.status = 'MATCHED'
    notify(ctx, parties, 'MATCH_CONFIRMED', 'Trận đã xác nhận', 'Đã nhận đủ cọc.', match_id=match.match_id)
    return match

def cancel_for_booking(ctx, *, booking_id, cause, actor_id):
    """Called by Tú after booking/refund planning, under the same ordered locks."""
    match = ctx.session.scalar(select(Match).where(Match.booking_id == booking_id))
    if not match or match.status == 'CANCELLED':
        return match
    if cause not in ('HOLD_TIMEOUT', 'USER_CANCEL', 'ADMIN_INCIDENT', 'LATE_PAYMENT'):
        raise DomainError('STATE_CONFLICT', 'Nguyên nhân hủy không hợp lệ.')
    booking = ctx.session.execute(text('SELECT status FROM bookings WHERE booking_id=:id'), {'id': booking_id}).scalar()
    if booking not in ('EXPIRED', 'CANCELLED') or (cause == 'HOLD_TIMEOUT' and booking != 'EXPIRED'):
        raise DomainError('STATE_CONFLICT', 'Booking chưa được hủy/hết hạn bởi orchestration.')
    from app.services.post_service import release_after_cancel
    posts = [ctx.session.get(MatchPost, pid) for pid in (match.post_id, match.opponent_post_id)]
    if cause == 'USER_CANCEL':
        cancelling_post = next((p for p in posts if p.creator_id == actor_id), None)
        if not cancelling_post:
            raise DomainError('FORBIDDEN', 'Người hủy không phải đại diện kèo.', 403)
        cancelling_post.status = 'CANCELLED'
    match.status = 'CANCELLED'
    release_after_cancel(ctx, match_id=match.match_id, cause=cause)
    notify(ctx, [p.creator_id for p in posts], 'MATCH_CANCELLED', 'Trận đã hủy', cause, match_id=match.match_id)
    return match

def cancel_after_booking_change(ctx, *, booking_id, cause, actor_id=None):
    return cancel_for_booking(ctx, booking_id=booking_id, cause=cause, actor_id=actor_id)

def can_view(ctx, match, actor, admin=True):
    if admin and actor.role == 'ADMIN':
        return True
    for pid in (match.post_id, match.opponent_post_id):
        post = ctx.session.get(MatchPost, pid) if pid else None
        if post and (post.creator_id == actor.user_id or (post.team_id and ctx.session.scalar(select(TeamMember.team_member_id).where(
            TeamMember.team_id == post.team_id, TeamMember.user_id == actor.user_id, TeamMember.status == 'ACTIVE')))):
            return True
    return False

def match_data(match):
    return {k: getattr(match, k) for k in ('match_id', 'post_id', 'opponent_post_id', 'proposal_id', 'booking_id', 'match_time', 'status', 'confirmed_at')}
