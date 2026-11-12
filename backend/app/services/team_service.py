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
        if post.status == 'OPEN' and post.attendance_plan is not None:
            ids = set(post.attendance_plan['user_ids'])
            if user_id not in ids:
                continue
            ids.remove(user_id)
            post.attendance_plan = {**post.attendance_plan, 'user_ids': sorted(ids)}
            post.current_players = len(ids) + post.attendance_plan['guest_players']
            if post.post_type == 'FIND_OPPONENT' and post.current_players < (5 if post.pitch_type == 'PITCH_5' else 7):
                post.status = 'CANCELLED'  # Not a full team any more; the captain sends a new request.
                from app.services.notification_service import notify
                notify(ctx, [post.creator_id], 'POST_EXPIRED', 'Đã dừng tìm đối',
                       'Một thành viên rời đội nên đội không còn đủ người. Hãy gửi lại yêu cầu khi đủ quân số.')
    return {'team_id': team_id, 'user_id': user_id, 'status': membership.status}

def add_member(ctx, team_id, actor, contact):
    """The captain adds a player by the exact email or phone they registered with."""
    contact = text(contact, 'contact', 150).strip()
    ctx.locks.users([actor.user_id])
    ctx.locks.lock(Team, [team_id])
    team = captain(ctx, team_id, actor)
    if '@' in contact:
        lookup = User.email == contact.lower()
    else:
        from app.services.auth_service import normalize_phone
        try:
            lookup = User.phone == normalize_phone(contact, 'contact')
        except DomainError:
            lookup = None
    user = ctx.session.scalar(select(User).where(lookup)) if lookup is not None else None
    if user is None or user.status != 'ACTIVE' or user.role != 'PLAYER' or user.email.endswith('@walkin.invalid'):
        raise DomainError('NOT_FOUND', 'Không tìm thấy người chơi với email hoặc số điện thoại này.', 404, {'contact': 'Kiểm tra lại email hoặc số điện thoại họ đã đăng ký.'})
    membership = ctx.session.scalar(select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user.user_id))
    if membership and membership.status == 'ACTIVE':
        raise DomainError('STATE_CONFLICT', 'Người này đã ở trong đội.')
    if membership:
        membership.status, membership.role = 'ACTIVE', 'MEMBER'
    else:
        ctx.session.add(TeamMember(team_id=team_id, user_id=user.user_id, role='MEMBER'))
    from app.services.notification_service import notify
    notify(ctx, [user.user_id], 'TEAM_JOINED', 'Bạn được thêm vào đội', f'Đội trưởng đã thêm bạn vào đội “{team.team_name}”.')
    ctx.session.flush()
    return team_data(ctx, team, detail=True)
