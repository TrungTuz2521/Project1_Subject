from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy import select, func, or_
from app.infrastructure.unit_of_work import UnitOfWork
from app.middleware import authenticated
from app.contracts.errors import DomainError, invalid
from app.models import User, Team, MatchPost, Match, Notification
from app.services import auth_service as auth, team_service as teams, match_service, match_requests as requests_service
from app.utils import validation as v
from app.utils.serialization import encode, user_self, columns
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

def paginated(ctx, query, mapper, preload=None):
    """preload(rows) -> mapper lets a page fetch related rows in one query instead of one per item."""
    page, size = page_args()
    total = ctx.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = ctx.session.scalars(query.offset((page-1)*size).limit(size)).all()
    if preload is not None:
        mapper = preload(rows)
    return response([mapper(row) for row in rows], page=page, page_size=size, total=total)

MATCH_STATUSES = ('SUGGESTED', 'CONFIRMED', 'COMPLETED', 'CANCELLED')

def status_arg(values):
    """A mistyped filter is a 422, not a silently empty list."""
    value = request.args.get('status')
    return v.enum(value, 'status', values) if value else None

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

@api.post('/auth/password/forgot')
def forgot_password():
    """Always the same answer, so the form never reveals which emails have an account."""
    data = body(('email',), ('email',))
    with UnitOfWork() as ctx:
        user = auth.reset_candidate(ctx, data['email'])
        mail = (user.email, user.full_name, auth.password_reset_token(ctx, user)) if user else None
    if mail and current_app.config.get('EMAIL_ENABLED'):
        from urllib.parse import quote
        from app.services.email_service import send_password_reset
        link = f"{current_app.config['PUBLIC_WEB_URL'].rstrip('/')}/#/reset-password?token={quote(mail[2])}"
        try:
            send_password_reset(mail[0], mail[1], link, auth.RESET_MINUTES)
        except Exception as error:  # Never reveal the account through a different answer.
            current_app.logger.error('Password reset email failed (%s)', type(error).__name__)
    elif mail:
        current_app.logger.warning('Password reset requested but EMAIL_ENABLED is off')
    return response({'sent': True, 'message': 'Nếu email đã đăng ký, bạn sẽ nhận được link đặt lại mật khẩu trong vài phút.'})

@api.post('/auth/password/reset')
def reset_password():
    data = body(('token', 'new_password', 'confirm_password'), ('token', 'new_password', 'confirm_password'))
    with UnitOfWork() as ctx:
        result = auth.reset_password(ctx, data['token'], data['new_password'], data['confirm_password'])
    return response(result)

@api.post('/auth/refresh')
@authenticated
def refresh_session():
    """Keeps an active user signed in. Needs a still-valid token whose password fingerprint matches, so a
    password change or a locked account ends the session here too."""
    with UnitOfWork() as ctx:
        user = auth.require_active_actor(ctx, g.actor)
        result = auth.issue_session(ctx, user)
    return response(result)

@api.post('/auth/google/challenge')
def google_challenge():
    from app.services.google_auth_service import challenge, require_web_origin
    require_web_origin()
    return response(challenge())

@api.post('/auth/google')
def google_login():
    from app.services.google_auth_service import require_web_origin, verify_credential, sign_in
    require_web_origin()
    data = body(('credential', 'challenge', 'password'), ('credential', 'challenge'))
    # Fetch Google's signing certificates before opening a database transaction.
    identity = verify_credential(data['credential'], data['challenge'])
    with UnitOfWork() as ctx:
        result = sign_in(ctx, identity, data.get('password'))
    return response(result)

@api.route('/users/me', methods=['GET', 'PATCH'])
@authenticated
def me():
    with UnitOfWork() as ctx:
        user = auth.require_active_actor(ctx, g.actor)
        result = user_self(user) if request.method == 'GET' else auth.update_profile(ctx, g.actor, body())
    return response(result)

@api.post('/users/me/password')
@authenticated
def change_password():
    data = body(('current_password', 'new_password', 'confirm_password'),
                ('current_password', 'new_password', 'confirm_password'))
    with UnitOfWork() as ctx:
        result = auth.change_password(ctx, g.actor, **data)
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
            query = teams.captained(g.actor.user_id).order_by(Team.team_id)
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
            if g.actor.role != 'ADMIN' and ctx.session.scalar(teams.captained(g.actor.user_id).where(Team.team_id == team_id)) is None:
                raise DomainError('NOT_FOUND', 'Không tìm thấy đội.', 404)
        result = teams.team_data(ctx, team)
    return response(result)

# ---- Match requests: players state when and how they can play; the system pairs them ----

REQUEST_STATUSES = ('OPEN', 'MATCHED', 'EXPIRED', 'CANCELLED')

@api.get('/match-requests/options')
@authenticated
def request_options():
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor)
        return response(requests_service.options(ctx, g.actor))

@api.route('/match-requests', methods=['POST'])
@authenticated
def create_request():
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor)
        post = requests_service.create_request(ctx, g.actor, body())
        post_id = post.post_id
    # Look for a partner straight away; the scheduler keeps scanning afterwards.
    try:
        requests_service.scan(post_id)
    except Exception as error:  # A failed scan never fails the request itself.
        current_app.logger.warning('Immediate scan failed (%s)', type(error).__name__)
    with UnitOfWork() as ctx:
        return response(requests_service.request_data(ctx, ctx.session.get(MatchPost, post_id)), 201)

@api.get('/match-requests/my')
@authenticated
def my_requests():
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        query = select(MatchPost).where(MatchPost.creator_id == g.actor.user_id, MatchPost.post_type.in_(requests_service.TYPES))
        status = status_arg(REQUEST_STATUSES)
        if status:
            query = query.where(MatchPost.status == status)
        return paginated(ctx, query.order_by(MatchPost.post_id.desc()), lambda p: requests_service.request_data(ctx, p))

@api.route('/match-requests/<int:post_id>', methods=['GET', 'PATCH'])
@authenticated
def request_item(post_id):
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor) if request.method == 'PATCH' else auth.require_active_actor(ctx, g.actor)
        post = ctx.session.get(MatchPost, post_id)
        if post is None or post.post_type not in requests_service.TYPES or (post.creator_id != g.actor.user_id and g.actor.role != 'ADMIN'):
            raise DomainError('NOT_FOUND', 'Không tìm thấy yêu cầu.', 404)
        if request.method == 'PATCH':
            ctx.locks.lock(Team, [post.team_id])
            post = ctx.locks.lock(MatchPost, [post_id])[0]
            requests_service.edit_request(ctx, g.actor, post, body())
        result = requests_service.request_data(ctx, post)
    if request.method == 'PATCH':
        requests_service.scan(post_id)
        with UnitOfWork() as ctx:
            result = requests_service.request_data(ctx, ctx.session.get(MatchPost, post_id))
    return response(result)

@api.post('/match-requests/<int:post_id>/cancel')
@authenticated
def cancel_request(post_id):
    with UnitOfWork() as ctx:
        auth.require_player(ctx, g.actor)
    requests_service.cancel_request(g.actor, post_id)
    with UnitOfWork() as ctx:
        return response(requests_service.request_data(ctx, ctx.session.get(MatchPost, post_id)))

@api.get('/admin/match-requests')
@authenticated
def admin_requests():
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
        query = select(MatchPost).where(MatchPost.post_type.in_(requests_service.TYPES))
        status = status_arg(REQUEST_STATUSES)
        if status:
            query = query.where(MatchPost.status == status)
        if request.args.get('request_type'):
            query = query.where(MatchPost.post_type == v.enum(request.args['request_type'], 'request_type', requests_service.TYPES))
        def row(post):
            data = requests_service.request_data(ctx, post)
            data['requester'] = columns(ctx.session.get(User, post.creator_id), 'user_id full_name phone')
            return data
        return paginated(ctx, query.order_by(MatchPost.post_id.desc()), row)

@api.post('/matchmaking/scan')
@authenticated
def scan():
    data = body(('post_id',))
    if data.get('post_id') is not None:
        v.integer(data['post_id'], 'post_id')
    with UnitOfWork() as ctx:
        auth.require_admin(ctx, g.actor)
    return response(requests_service.scan(data.get('post_id')))

@api.get('/matches')
@authenticated
def matches():
    with UnitOfWork() as ctx:
        auth.require_active_actor(ctx, g.actor)
        # Only the representatives' own games, filtered before pagination.
        post_ids = select(MatchPost.post_id).where(MatchPost.creator_id == g.actor.user_id)
        query = select(Match).where(or_(Match.post_id.in_(post_ids), Match.opponent_post_id.in_(post_ids)))
        status = status_arg(MATCH_STATUSES)
        if status:
            query = query.where(Match.status == status)
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
            if match.status not in ('CONFIRMED', 'COMPLETED') or g.actor.user_id not in {p.creator_id for p in match_posts}:
                raise DomainError('FORBIDDEN', 'Chỉ đại diện được xem liên hệ khi trận đã xác nhận.', 403)
            return response({'contacts': [columns(ctx.session.get(User, p.creator_id), 'user_id full_name phone email') for p in match_posts]})
        result = match_service.match_data(match)
        result['end_time'] = match_posts[0].end_time
        result['teams'] = [teams.team_data(ctx, ctx.session.get(Team, p.team_id)) for p in match_posts if p.team_id]
        # Privacy-filtered: a representative sees the other side's deposit progress, not the amount they paid.
        from app.services.booking_service import read_for_actor
        result['booking'] = read_for_actor(ctx, booking_id=match.booking_id, actor=g.actor) if match.booking_id else None
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
    from app.use_cases.cancel_booking import cancel_match as cancel
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
