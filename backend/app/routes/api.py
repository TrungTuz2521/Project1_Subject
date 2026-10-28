from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy import select, func, or_
from app.infrastructure.unit_of_work import UnitOfWork
from app.middleware import authenticated
from app.contracts.errors import DomainError, invalid
from app.models import User, Team, TeamMember, MatchPost, MatchParticipant, MatchProposal, ProposalConfirmation, Match, Notification
from app.services import auth_service as auth, team_service as teams, post_service as posts, matchmaking_service as mm, match_service
from app.utils import validation as v
from app.utils.serialization import encode, user_self, post_data, columns
from app.utils.time import utcnow

api = Blueprint('api', __name__)

def body(allowed=None, required=()):
    data = request.get_json(silent=True)
    return v.fields(data, allowed if allowed is not None else (data or {}), required)

def response(data, status=200, **meta):
    now = current_app.config.get('CLOCK', utcnow)()
    return jsonify(encode({'data': data, 'meta': {'server_time': now, **meta}})), status

def page_args():
    try:
        page, size = int(request.args.get('page', 1)), int(request.args.get('page_size', 20))
        if not 1 <= page <= 100000 or not 1 <= size <= 100:
            raise ValueError()
        return page, size
    except ValueError:
        invalid('page', 'page >= 1, page_size từ 1 đến 100.')

def paginated(ctx, query, mapper):
    page, size = page_args()
    total = ctx.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = ctx.session.scalars(query.offset((page-1)*size).limit(size)).all()
    return response([mapper(row) for row in rows], page=page, page_size=size, total=total)

def found(ctx, model, pk):
    result = ctx.session.get(model, pk)
    if not result:
        raise DomainError('NOT_FOUND', 'Không tìm thấy tài nguyên.', 404)
    return result

@api.get('/health')
def health():
    return response({'status': 'ok'})

@api.post('/auth/register')
def register():
    data = body(('full_name', 'email', 'password', 'phone', 'skill_level'), ('full_name', 'email', 'password'))
    with UnitOfWork() as ctx:
        result = auth.register(ctx, **data)
    return response(result, 201)

@api.post('/auth/login')
def login():
    data = body(('email', 'password'), ('email', 'password'))
    with UnitOfWork() as ctx:
        result = auth.login(ctx, **data)
    return response(result)

@api.route('/users/me', methods=['GET', 'PATCH'])
@authenticated
def me():
    with UnitOfWork() as ctx:
        user = auth.require_active_actor(ctx, g.actor)
        result = user_self(user) if request.method == 'GET' else auth.update_profile(ctx, g.actor, body())
    return response(result)

@api.route('/teams', methods=['GET', 'POST'])
@authenticated
def team_collection():
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor)
        if request.method == 'POST':
            result = teams.create_team(ctx, g.actor, body(('team_name',), ('team_name',))['team_name'])
        else:
            if request.args.get('my', 'true') != 'true':
                invalid('my', 'Endpoint danh sách chỉ trả các đội của bạn.')
            query = select(Team).join(TeamMember, TeamMember.team_id == Team.team_id).where(
                TeamMember.user_id == g.actor.user_id, TeamMember.status == 'ACTIVE', Team.status == 'ACTIVE').order_by(Team.team_id)
            return paginated(ctx, query, lambda t: teams.team_data(ctx, t))
    return response(result, 201)

@api.route('/teams/<int:team_id>', methods=['GET', 'PATCH'])
@authenticated
def team_item(team_id):
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        if request.method == 'PATCH':
            ctx.locks.lock(Team, [team_id])
            team = teams.captain(ctx, team_id, g.actor)
            team.team_name = v.text(body(('team_name',), ('team_name',))['team_name'], 'team_name', 100)
        else:
            team = found(ctx, Team, team_id)
            if not teams.member(ctx, team_id, g.actor.user_id) and g.actor.role != 'ADMIN':
                raise DomainError('NOT_FOUND', 'Không tìm thấy đội.', 404)
        result = teams.team_data(ctx, team, detail=True)
    return response(result)

@api.delete('/teams/<int:team_id>/members/me')
@api.delete('/teams/<int:team_id>/members/<int:user_id>')
@authenticated
def remove_member(team_id, user_id=None):
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor)
        reason = body(('reason',), ('reason',))['reason'] if user_id is not None else None
        result = teams.remove_member(ctx, team_id, g.actor, user_id or g.actor.user_id, reason)
    return response(result)

@api.route('/match-posts', methods=['GET', 'POST'])
def post_collection():
    if request.method == 'POST':
        return create_post()
    with UnitOfWork() as ctx:
        query = select(MatchPost).where(MatchPost.status == 'OPEN', MatchPost.expiry_time > ctx.now())
        for key, choices in [('post_type', ('FIND_OPPONENT', 'RECRUIT_MEMBERS', 'LOOK_FOR_TEAM', 'RANDOM_SQUAD')),
                             ('pitch_type', ('PITCH_5', 'PITCH_7')), ('skill_level', ('BEGINNER', 'AMATEUR', 'INTERMEDIATE', 'SEMI_PRO', 'PRO'))]:
            if key in request.args:
                query = query.where(getattr(MatchPost, key) == v.enum(request.args[key], key, choices))
        if request.args.get('from'):
            query = query.where(MatchPost.match_time >= v.timestamp(request.args['from'], 'from'))
        if request.args.get('to'):
            query = query.where(MatchPost.match_time < v.timestamp(request.args['to'], 'to'))
        return paginated(ctx, query.order_by(MatchPost.created_at, MatchPost.post_id), post_data)

@authenticated
def create_post():
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor)
        post = posts.create_post(ctx, g.actor, body())
        result = post_data(post, True)
    return response(result, 201)

@api.get('/match-posts/my')
@authenticated
def my_posts():
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        query = select(MatchPost).where(MatchPost.creator_id == g.actor.user_id)
        if request.args.get('status'):
            query = query.where(MatchPost.status == request.args['status'])
        return paginated(ctx, query.order_by(MatchPost.post_id.desc()), lambda p: post_data(p, True))

@api.route('/match-posts/<int:post_id>', methods=['GET', 'PATCH'])
def post_item(post_id):
    if request.method == 'PATCH':
        return edit_post(post_id)
    with UnitOfWork() as ctx:
        post = found(ctx, MatchPost, post_id)
        return response(post_data(post, True))

@authenticated
def edit_post(post_id):
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor)
        post = found(ctx, MatchPost, post_id)
        ctx.locks.users(posts.party_users(ctx, post) | {g.actor.user_id})
        ctx.locks.lock(Team, [post.team_id])
        ctx.locks.lock(MatchPost, [post_id])
        result = post_data(posts.edit_post(ctx, g.actor, post, body()), True)
    return response(result)

@api.post('/match-posts/<int:post_id>/cancel')
@authenticated
def cancel_post(post_id):
    v.text(body(('reason',), ('reason',))['reason'], 'reason', 255)
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor)
        post = found(ctx, MatchPost, post_id)
        ctx.locks.lock(Team, [post.team_id])
        ctx.locks.lock(MatchPost, [post_id])
        if post.creator_id != g.actor.user_id:
            raise DomainError('FORBIDDEN', 'Chỉ chủ bài được hủy.', 403)
        if post.booking_id or post.status == 'MATCHED':
            raise DomainError('STATE_CONFLICT', 'Kèo có booking phải đi qua luồng hủy trận.')
        if post.status == 'LOCKED':
            raise DomainError('STATE_CONFLICT', 'Hãy từ chối đề xuất trước khi hủy bài.')
        post.status = 'CANCELLED'
        result = post_data(post, True)
    return response(result)

@api.post('/teams/<int:team_id>/join-requests')
@authenticated
def request_team_join(team_id):
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor)
        options = list(ctx.session.scalars(select(MatchPost).where(MatchPost.team_id == team_id,
            MatchPost.post_type == 'RECRUIT_MEMBERS', MatchPost.status == 'OPEN', MatchPost.expiry_time > ctx.now())))
        if len(options) != 1:
            raise DomainError('RECRUITMENT_NOT_OPEN', 'Cần đúng một bài tuyển mở; nếu nhiều bài hãy chọn bài cụ thể.')
        post_id = options[0].post_id
    return create_participant(post_id)

@api.route('/match-posts/<int:post_id>/participants', methods=['GET', 'POST'])
@authenticated
def participants(post_id):
    if request.method == 'POST':
        return create_participant(post_id)
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        post = found(ctx, MatchPost, post_id)
        if post.creator_id != g.actor.user_id and g.actor.role != 'ADMIN':
            raise DomainError('NOT_FOUND', 'Không tìm thấy bài.', 404)
        return paginated(ctx, select(MatchParticipant).where(MatchParticipant.post_id == post_id).order_by(MatchParticipant.participant_id),
            lambda p: columns(p, 'participant_id post_id user_id status joined_at'))

def create_participant(post_id):
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor)
        post = found(ctx, MatchPost, post_id)
        ctx.locks.users(posts.party_users(ctx, post) | {g.actor.user_id})
        ctx.locks.lock(Team, [post.team_id])
        ctx.locks.lock(MatchPost, [post_id])
        if post.post_type != 'RECRUIT_MEMBERS' or not post.team_id or not post.required_players:
            raise DomainError('RECRUITMENT_NOT_OPEN', 'Bài không tuyển thành viên.')
        if teams.member(ctx, post.team_id, g.actor.user_id):
            raise DomainError('STATE_CONFLICT', 'Đã là thành viên đội.')
        posts.assert_available(ctx, {g.actor.user_id}, post.match_time, post.end_time)
        proposal = mm.create_proposal(ctx, post, candidate_user_id=g.actor.user_id)
        participant = ctx.session.scalar(select(MatchParticipant).where(MatchParticipant.post_id == post_id, MatchParticipant.user_id == g.actor.user_id))
        if not participant:
            participant = MatchParticipant(post_id=post_id, user_id=g.actor.user_id)
            ctx.session.add(participant)
        participant.status = 'PENDING'
        ctx.session.flush()
        result = columns(participant, 'participant_id post_id user_id status joined_at')
        result['proposal_id'] = proposal.proposal_id
    return response(result, 201)

@api.delete('/match-posts/<int:post_id>/participants/me')
@authenticated
def withdraw_participant(post_id):
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor)
        participant = ctx.session.scalar(select(MatchParticipant).where(MatchParticipant.post_id == post_id,
            MatchParticipant.user_id == g.actor.user_id))
        if not participant:
            raise DomainError('NOT_FOUND', 'Không tìm thấy đăng ký.', 404)
        if participant.status == 'ACCEPTED':
            raise DomainError('STATE_CONFLICT', 'Đã vào đội; dùng chức năng rời đội.')
        proposal = ctx.session.scalar(select(MatchProposal).where(MatchProposal.source_post_id == post_id,
            MatchProposal.candidate_user_id == g.actor.user_id, MatchProposal.status == 'PENDING_CONFIRMATION'))
        pid = proposal.proposal_id if proposal else None
    if pid:
        result = respond_result(pid, 'DECLINED')
        if result[1] != 200:
            return result
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor)
        participant = ctx.session.scalar(select(MatchParticipant).where(MatchParticipant.post_id == post_id,
            MatchParticipant.user_id == g.actor.user_id).with_for_update())
        if participant.status == 'ACCEPTED':
            raise DomainError('STATE_CONFLICT', 'Đã vào đội; dùng chức năng rời đội.')
        participant.status = 'CANCELLED'
        result = columns(participant, 'participant_id post_id user_id status joined_at')
    return response(result)

@api.patch('/teams/<int:team_id>/join-requests/<int:post_id>/respond')
@authenticated
def respond_join(team_id, post_id):
    data = body(('decision',), ('decision',))
    decision = v.enum(data['decision'], 'decision', ('ACCEPTED', 'DECLINED'))
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor)
        teams.captain(ctx, team_id, g.actor)
        post = found(ctx, MatchPost, post_id)
        if post.team_id != team_id:
            raise DomainError('NOT_FOUND', 'Không tìm thấy bài.', 404)
        proposal = ctx.session.scalar(select(MatchProposal).where(MatchProposal.source_post_id == post_id,
            MatchProposal.candidate_user_id.is_not(None)).order_by(MatchProposal.proposal_id.desc()))
        if not proposal:
            raise DomainError('STATE_CONFLICT', 'Không có đề xuất đang chờ.')
        pid = proposal.proposal_id
    from app.use_cases.respond_proposal import respond_proposal
    outcome = respond_proposal(pid, g.actor, decision)
    if outcome.outcome != 'OK':
        return jsonify(encode({'error': outcome.error})), outcome.http_status
    with UnitOfWork() as ctx:
        proposal = ctx.session.get(MatchProposal, pid)
        participant = ctx.session.scalar(select(MatchParticipant).where(MatchParticipant.post_id == post_id,
            MatchParticipant.user_id == proposal.candidate_user_id))
        if not participant:
            raise DomainError('STATE_CONFLICT', 'Đề xuất nhóm cần phản hồi qua endpoint proposal.')
        result = columns(participant, 'participant_id post_id user_id status joined_at')
        result['proposal_id'] = pid
    return response(result)

@api.post('/match-proposals/<int:proposal_id>/respond')
@authenticated
def proposal_respond(proposal_id):
    decision = v.enum(body(('decision',), ('decision',))['decision'], 'decision', ('ACCEPTED', 'DECLINED'))
    return respond_result(proposal_id, decision)

def respond_result(proposal_id, decision):
    from app.use_cases.respond_proposal import respond_proposal
    result = respond_proposal(proposal_id, g.actor, decision)
    if result.outcome != 'OK':
        return jsonify(encode({'error': result.error})), result.http_status
    return response(result.data)

@api.get('/match-proposals')
@authenticated
def proposal_collection():
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        query = select(MatchProposal).join(ProposalConfirmation).where(ProposalConfirmation.user_id == g.actor.user_id)
        if request.args.get('status'):
            query = query.where(MatchProposal.status == request.args['status'])
        return paginated(ctx, query.order_by(MatchProposal.proposal_id.desc()), lambda p: mm.proposal_data(ctx, p))

@api.get('/match-proposals/<int:proposal_id>')
@authenticated
def proposal_item(proposal_id):
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        proposal = found(ctx, MatchProposal, proposal_id)
        if not ctx.session.scalar(select(ProposalConfirmation.confirmation_id).where(
            ProposalConfirmation.proposal_id == proposal_id, ProposalConfirmation.user_id == g.actor.user_id)):
            raise DomainError('NOT_FOUND', 'Không tìm thấy đề xuất.', 404)
        return response(mm.proposal_data(ctx, proposal))

@api.post('/matchmaking/scan')
@authenticated
def scan():
    data = body(('post_id',))
    if data.get('post_id') is not None:
        v.integer(data['post_id'], 'post_id')
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
    from app.jobs.commands import scan_open_posts
    return response(scan_open_posts(data.get('post_id')))

@api.get('/matches')
@authenticated
def matches():
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        # Membership filter is applied before pagination, without exposing strangers' matches.
        post_ids = select(MatchPost.post_id).where(or_(MatchPost.creator_id == g.actor.user_id,
            MatchPost.team_id.in_(select(TeamMember.team_id).where(TeamMember.user_id == g.actor.user_id, TeamMember.status == 'ACTIVE'))))
        query = select(Match).where(or_(Match.post_id.in_(post_ids), Match.opponent_post_id.in_(post_ids)))
        if request.args.get('status'):
            query = query.where(Match.status == request.args['status'])
        return paginated(ctx, query.order_by(Match.match_id.desc()), match_service.match_data)

@api.get('/matches/<int:match_id>')
@api.get('/matches/<int:match_id>/contacts')
@authenticated
def match_item(match_id):
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        match = found(ctx, Match, match_id)
        if not match_service.can_view(ctx, match, g.actor):
            raise DomainError('NOT_FOUND', 'Không tìm thấy trận.', 404)
        match_posts = [ctx.session.get(MatchPost, pid) for pid in (match.post_id, match.opponent_post_id) if pid]
        if request.path.endswith('/contacts'):
            if match.status != 'CONFIRMED' or g.actor.user_id not in {p.creator_id for p in match_posts}:
                raise DomainError('FORBIDDEN', 'Chỉ đại diện được xem liên hệ khi trận CONFIRMED.', 403)
            return response({'contacts': [columns(ctx.session.get(User, p.creator_id), 'user_id full_name phone email') for p in match_posts]})
        result = match_service.match_data(match)
        result['end_time'] = match_posts[0].end_time
        result['teams'] = [teams.team_data(ctx, ctx.session.get(Team, p.team_id)) for p in match_posts if p.team_id]
        result['proposal'] = mm.proposal_data(ctx, ctx.session.get(MatchProposal, match.proposal_id)) if match.proposal_id else None
        # Tú supplies a privacy-filtered booking view in the same context.
        reader = current_app.extensions.get('booking_reader')
        result['booking'] = reader(ctx, booking_id=match.booking_id, actor=g.actor) if reader and match.booking_id else None
        return response(result)

@api.post('/matches/<int:match_id>/cancel')
@authenticated
def cancel_match(match_id):
    reason = v.text(body(('reason',), ('reason',))['reason'], 'reason', 255)
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        match = found(ctx, Match, match_id)
        parties = [ctx.session.get(MatchPost, pid).creator_id for pid in (match.post_id, match.opponent_post_id) if pid]
        if g.actor.role != 'ADMIN' and g.actor.user_id not in parties:
            raise DomainError('NOT_FOUND', 'Không tìm thấy trận.', 404)
    cancel = current_app.extensions.get('cancel_match')
    if not cancel:
        raise DomainError('BOOKING_SERVICE_UNAVAILABLE', 'Chưa tích hợp luồng hủy/hoàn của Tú.', 503)
    return response(cancel(g.actor, match_id=match_id, reason=reason))

@api.get('/notifications')
@authenticated
def notifications():
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        query = select(Notification).where(Notification.user_id == g.actor.user_id, Notification.delivery_channel == 'IN_APP')
        if 'is_read' in request.args:
            query = query.where(Notification.is_read == (v.enum(request.args['is_read'], 'is_read', ('true', 'false')) == 'true'))
        return paginated(ctx, query.order_by(Notification.notification_id.desc()), notification_data)

def notification_data(n):
    return columns(n, 'notification_id notification_type title content is_read created_at read_at proposal_id match_id')

@api.patch('/notifications/<int:notification_id>/read')
@authenticated
def read_notification(notification_id):
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        n = found(ctx, Notification, notification_id)
        if n.user_id != g.actor.user_id or n.delivery_channel != 'IN_APP':
            raise DomainError('NOT_FOUND', 'Không tìm thấy thông báo.', 404)
        if not n.is_read:
            n.is_read, n.read_at = True, ctx.now()
        result = notification_data(n)
    return response(result)
