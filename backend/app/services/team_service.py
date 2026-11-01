from sqlalchemy import select, func
from app.models import Team, TeamMember, User, MatchPost, Match, MatchParticipant
from app.contracts.errors import DomainError
from app.utils.validation import text

def member(ctx, team_id, user_id):
    return ctx.session.scalar(select(TeamMember).where(TeamMember.team_id == team_id,
        TeamMember.user_id == user_id, TeamMember.status == 'ACTIVE'))

def captain(ctx, team_id, actor):
    team = ctx.session.get(Team, team_id)
    membership = member(ctx, team_id, actor.user_id)
    if not team or team.status != 'ACTIVE' or not membership or membership.role != 'CAPTAIN':
        raise DomainError('FORBIDDEN', 'Cần đội trưởng đang hoạt động của đội.', 403)
    return team

def count_members(ctx, team_id):
    return ctx.session.scalar(select(func.count()).select_from(TeamMember).where(
        TeamMember.team_id == team_id, TeamMember.status == 'ACTIVE'))

def team_data(ctx, team, detail=False):
    result = {k: getattr(team, k) for k in ('team_id', 'team_name', 'created_by', 'creation_type', 'status')}
    result['active_member_count'] = count_members(ctx, team.team_id)
    if detail:
        result['members'] = [dict(user_id=u.user_id, full_name=u.full_name, role=m.role, status=m.status, joined_at=m.joined_at)
            for m, u in ctx.session.execute(select(TeamMember, User).join(User, TeamMember.user_id == User.user_id)
            .where(TeamMember.team_id == team.team_id, TeamMember.status == 'ACTIVE'))]
    return result

def create_team(ctx, actor, name):
    team = Team(team_name=text(name, 'team_name', 100), created_by=actor.user_id)
    ctx.session.add(team)
    ctx.session.flush()
    ctx.session.add(TeamMember(team_id=team.team_id, user_id=actor.user_id, role='CAPTAIN'))
    ctx.session.flush()
    return team_data(ctx, team)

def remove_member(ctx, team_id, actor, user_id, reason=None):
    ctx.locks.users([actor.user_id, user_id])
    ctx.locks.lock(Team, [team_id])
    team = ctx.session.get(Team, team_id)
    if not team:
        raise DomainError('NOT_FOUND', 'Không tìm thấy đội.', 404)
    if user_id != actor.user_id:
        captain(ctx, team_id, actor)
        text(reason, 'reason', 255)
    membership = member(ctx, team_id, user_id)
    if not membership:
        raise DomainError('NOT_FOUND', 'Không tìm thấy thành viên.', 404)
    if membership.role == 'CAPTAIN':
        raise DomainError('CAPTAIN_TRANSFER_REQUIRED', 'Đội trưởng phải chuyển quyền trước khi rời đội.')
    # Team is the serialization parent for membership and matchmaking writes.
    posts = list(ctx.session.scalars(select(MatchPost).where(MatchPost.team_id == team_id)))
    post_ids = [p.post_id for p in posts]
    from sqlalchemy import or_
    active = ctx.session.scalar(select(Match.match_id).where(
        or_(Match.post_id.in_(post_ids), Match.opponent_post_id.in_(post_ids)),
        Match.status.in_(['SUGGESTED', 'CONFIRMED'])))
    if active or any(p.status == 'LOCKED' for p in posts):
        raise DomainError('ACTIVE_MATCH_MEMBERSHIP', 'Thành viên đang ràng buộc trong kèo.')
    membership.status = 'LEFT' if user_id == actor.user_id else 'REMOVED'
    ctx.session.flush()
    for post in posts:
        if post.status == 'OPEN':
            post.current_players = count_members(ctx, team_id)
            if post.post_type == 'RECRUIT_MEMBERS':
                post.required_players = (post.required_players or 0) + 1
    return {'team_id': team_id, 'user_id': user_id, 'status': membership.status}

def accept_member_proposal(ctx, *, proposal_id):
    from app.models import MatchProposal, ProposalConfirmation
    from app.use_cases.respond_proposal import accept_member_proposal as apply_membership
    proposal = ctx.session.get(MatchProposal, proposal_id)
    if not proposal or proposal.proposal_type != 'TEAM_MEMBER' or proposal.expires_at <= ctx.now():
        raise DomainError('STATE_CONFLICT', 'Đề xuất thành viên không hợp lệ.')
    confirmations = list(ctx.session.scalars(select(ProposalConfirmation).where(ProposalConfirmation.proposal_id == proposal_id)))
    if len(confirmations) != 2 or any(c.decision != 'ACCEPTED' for c in confirmations):
        raise DomainError('STATE_CONFLICT', 'Cần đủ hai xác nhận.')
    posts = [ctx.session.get(MatchPost, pid) for pid in (proposal.source_post_id, proposal.target_post_id) if pid]
    return apply_membership(ctx, proposal, posts)
