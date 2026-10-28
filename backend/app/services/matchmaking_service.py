from datetime import timedelta
from sqlalchemy import select, or_
from app.models import MatchPost, MatchProposal, ProposalConfirmation, Team, TeamMember, User, MatchParticipant
from app.contracts.enums import SKILLS
from app.contracts.errors import DomainError
from app.services import post_service, team_service, notification_service

def score(ctx, source, target):
    if source.skill_level not in SKILLS or target.skill_level not in SKILLS:
        return 0
    if source.creator_id == target.creator_id or (source.team_id and source.team_id == target.team_id):
        return 0
    if any(p.status != 'OPEN' or p.expiry_time <= ctx.now() or p.booking_id or not p.match_time or not p.end_time or not p.pitch_type for p in (source, target)):
        return 0
    if source.pitch_type != target.pitch_type or (source.pitch_id and target.pitch_id and source.pitch_id != target.pitch_id):
        return 0
    if max(source.match_time, target.match_time) + timedelta(minutes=90) > min(source.end_time, target.end_time):
        return 0
    types = (source.post_type, target.post_type)
    opponent = types == ('FIND_OPPONENT', 'FIND_OPPONENT')
    recruitment = source.post_type in ('RECRUIT_MEMBERS', 'RANDOM_SQUAD') and target.post_type in ('LOOK_FOR_TEAM', 'RANDOM_SQUAD')
    if not (opponent or recruitment) or (opponent and source.payment_rule != target.payment_rule):
        return 0
    source_users, target_users = post_service.party_users(ctx, source), post_service.party_users(ctx, target)
    if source_users & target_users:
        return 0
    users = source_users | target_users
    active = set(ctx.session.scalars(select(User.user_id).where(User.user_id.in_(users), User.status == 'ACTIVE')))
    if active != users:
        return 0
    size = 5 if source.pitch_type == 'PITCH_5' else 7
    if opponent and (len(source_users) < size or len(target_users) < size):
        return 0
    if recruitment and len(target_users) > (source.required_players or 0):
        return 0
    try:
        post_service.assert_available(ctx, users, source.match_time, source.end_time, [source.post_id, target.post_id])
    except DomainError:
        return 0
    difference = abs(SKILLS.index(source.skill_level) - SKILLS.index(target.skill_level))
    return 60 + (40 if difference == 0 else 20 if difference == 1 else 0)

def create_proposal(ctx, source, target=None, candidate_user_id=None, points=100):
    if source.booking_id or (target and target.booking_id):
        raise DomainError('LEGACY_BOOKING_REQUIRES_REVIEW', 'Booking cũ cần đối soát trước khi ghép.')
    now = ctx.now()
    posts = [source] + ([target] if target else [])
    if any(p.status != 'OPEN' or p.expiry_time <= now for p in posts):
        raise DomainError('STATE_CONFLICT', 'Bài không còn mở.')
    other_id = target.creator_id if target else candidate_user_id
    if not other_id or other_id == source.creator_id:
        raise DomainError('FORBIDDEN', 'Hai phía phải khác người.', 403)
    deadlines = [now + timedelta(minutes=15)] + [p.expiry_time for p in posts] + [p.match_time for p in posts if p.match_time]
    proposal = MatchProposal(source_post_id=source.post_id, target_post_id=target.post_id if target else None,
        candidate_user_id=candidate_user_id, proposal_type='OPPONENT' if source.post_type == 'FIND_OPPONENT' else 'TEAM_MEMBER',
        compatibility_score=points, expires_at=min(deadlines))
    ctx.session.add(proposal)
    ctx.session.flush()
    for p in posts:
        p.status = 'LOCKED'
    for uid in (source.creator_id, other_id):
        ctx.session.add(ProposalConfirmation(proposal_id=proposal.proposal_id, user_id=uid))
    notification_service.notify(ctx, (source.creator_id, other_id), 'MATCH_PROPOSAL', 'Đề xuất ghép mới',
                                'Có đề xuất mới. Vui lòng phản hồi trước thời hạn.', proposal_id=proposal.proposal_id)
    return proposal

def scan_pair(ctx, source_id, target_id):
    posts = [ctx.session.get(MatchPost, i) for i in (source_id, target_id)]
    if any(p is None for p in posts):
        return None
    roster = set().union(*(post_service.party_users(ctx, p) for p in posts))
    ctx.locks.users(roster)
    ctx.locks.lock(Team, [p.team_id for p in posts])
    ctx.locks.lock(MatchPost, [source_id, target_id])
    if roster != set().union(*(post_service.party_users(ctx, p) for p in posts)):
        return None
    if posts[0].post_type == posts[1].post_type == 'RANDOM_SQUAD':
        posts.sort(key=lambda p: (p.created_at, p.post_id))
    points = score(ctx, *posts)
    if points < 80:
        return None
    return create_proposal(ctx, *posts, points=points)

def reopen(ctx, posts):
    for post in posts:
        if post and post.status == 'LOCKED':
            if post.expiry_time <= ctx.now():
                post.status = 'EXPIRED'
            else:
                post.status = 'OPEN' if post.required_players is None or post.required_players > 0 else 'MATCHED'

def proposal_data(ctx, proposal):
    result = {k: getattr(proposal, k) for k in ('proposal_id', 'source_post_id', 'target_post_id', 'candidate_user_id',
        'proposal_type', 'compatibility_score', 'status', 'expires_at', 'confirmed_at')}
    result['confirmations'] = [dict(user_id=c.user_id, decision=c.decision, responded_at=c.responded_at)
        for c in ctx.session.scalars(select(ProposalConfirmation).where(ProposalConfirmation.proposal_id == proposal.proposal_id))]
    from app.models import Match
    match = ctx.session.scalar(select(Match).where(Match.proposal_id == proposal.proposal_id))
    result.update(match_id=match.match_id if match else None, booking_id=match.booking_id if match else None)
    return result
