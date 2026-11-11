from datetime import timedelta
from sqlalchemy import select, or_
from app.models import MatchPost, Team, TeamMember, User, Match, MatchParticipant
from app.contracts.errors import DomainError, invalid
from app.contracts.enums import SKILLS, POST_TYPES, PAYMENT_RULES
from app.utils import validation as v
from app.utils.time import VIETNAM
from app.services import team_service

CREATE_FIELDS = ('post_type', 'title', 'description', 'team_id', 'pitch_id', 'pitch_type', 'match_time',
                 'end_time', 'skill_level', 'payment_rule', 'required_players', 'expiry_time', 'attendance_user_ids', 'guest_players')
EDIT_FIELDS = ('title', 'description', 'pitch_id', 'pitch_type', 'match_time', 'end_time',
               'skill_level', 'payment_rule', 'expiry_time', 'required_players')

def validate_schedule(ctx, post):
    now = ctx.now()
    if not post.expiry_time or post.expiry_time <= now:
        invalid('expiry_time', 'Hạn bài phải ở tương lai.')
    if post.match_time is None:
        if post.post_type != 'LOOK_FOR_TEAM' or post.end_time is not None:
            invalid('match_time')
        return
    if post.end_time is None:
        post.end_time = post.match_time + timedelta(minutes=90)
    if post.end_time - post.match_time != timedelta(minutes=90):
        invalid('end_time', 'Mỗi lượt đúng 90 phút.')
    start, end = post.match_time.astimezone(VIETNAM), post.end_time.astimezone(VIETNAM)
    if post.match_time <= now or post.expiry_time > post.match_time:
        invalid('match_time', 'Giờ đá ở tương lai và không trước hạn bài.')
    if start.date() > now.astimezone(VIETNAM).date() + timedelta(days=10):
        invalid('match_time', 'Chỉ đặt trước tối đa 10 ngày.')
    if start.date() != end.date() or start.hour < 6 or end.hour > 23 or (end.hour == 23 and (end.minute or end.second)):
        invalid('match_time', 'Lượt đá phải nằm trong 06:00–23:00 giờ Việt Nam.')
    if start.second or start.microsecond or ((start.hour * 60 + start.minute) - 360) % 90:
        invalid('match_time', 'Giờ bắt đầu theo lưới 90 phút từ 06:00.')

def apply_fields(ctx, post, data):
    for key, value in data.items():
        if key in ('attendance_user_ids', 'guest_players'):
            continue
        if key in ('match_time', 'end_time', 'expiry_time'):
            value = v.timestamp(value, key) if value is not None else None
        elif key == 'title':
            value = v.text(value, key, 150)
        elif key == 'description':
            value = v.text(value, key, 3000, minimum=0, nullable=True)
        elif key == 'skill_level':
            value = v.enum(value, key, SKILLS)
        elif key == 'pitch_type':
            value = v.enum(value, key, ('PITCH_5', 'PITCH_7')) if value is not None else None
        elif key == 'payment_rule':
            value = v.enum(value, key, PAYMENT_RULES) if value is not None else None
        elif key in ('team_id', 'pitch_id', 'required_players'):
            value = v.integer(value, key, maximum=255 if key == 'required_players' else 2147483647) if value is not None else None
        elif key == 'post_type':
            value = v.enum(value, key, POST_TYPES)
        setattr(post, key, value)
    if post.pitch_id is not None:
        # Read Tú's table without inventing another Pitch ORM.
        from sqlalchemy import text
        row = ctx.session.execute(text('SELECT pitch_type, status FROM pitches WHERE pitch_id=:id'), {'id': post.pitch_id}).mappings().first()
        if not row or row['status'] != 'ACTIVE' or row['pitch_type'] != post.pitch_type:
            invalid('pitch_id', 'Sân phải hoạt động và khớp loại sân.')
    if post.post_type != 'LOOK_FOR_TEAM' and not post.pitch_type:
        invalid('pitch_type')
    if post.post_type in ('FIND_OPPONENT', 'RECRUIT_MEMBERS') and not post.payment_rule:
        invalid('payment_rule')
    validate_schedule(ctx, post)

def create_post(ctx, actor, data):
    v.fields(data, CREATE_FIELDS, ('post_type', 'title', 'skill_level', 'expiry_time'))
    post = MatchPost(creator_id=actor.user_id, current_players=1)
    apply_fields(ctx, post, data)
    if 'attendance_user_ids' in data or 'guest_players' in data:
        ids = data.get('attendance_user_ids', [actor.user_id])
        if not isinstance(ids, list) or not ids or len(ids) > 7:
            invalid('attendance_user_ids', 'Chọn từ 1 đến 7 tài khoản tham gia buổi đá.')
        for uid in ids:
            v.integer(uid, 'attendance_user_ids')
        if len(set(ids)) != len(ids) or actor.user_id not in ids:
            invalid('attendance_user_ids', 'Không được trùng người và phải có người đại diện đăng bài.')
        guests = v.integer(data.get('guest_players', 0), 'guest_players', minimum=0, maximum=6)
        if post.post_type == 'LOOK_FOR_TEAM' and (set(ids) != {actor.user_id} or guests):
            invalid('attendance_user_ids', 'Bài tìm đội chỉ đại diện một người chơi.')
        if not post.team_id and set(ids) != {actor.user_id}:
            invalid('attendance_user_ids', 'Chưa có đội thì chỉ chọn tài khoản của mình.')
        post.attendance_plan = {'user_ids': sorted(ids), 'guest_players': guests}
    roster = party_users(ctx, post)
    ctx.locks.users(roster | {actor.user_id})
    if post.team_id:
        ctx.locks.lock(Team, [post.team_id])
        team_service.captain(ctx, post.team_id, actor)
        if post.attendance_plan is not None:
            eligible = set(ctx.session.scalars(select(TeamMember.user_id).join(User, User.user_id == TeamMember.user_id).where(
                TeamMember.team_id == post.team_id, TeamMember.status == 'ACTIVE', User.status == 'ACTIVE', User.role == 'PLAYER')))
            if not roster <= eligible:
                invalid('attendance_user_ids', 'Chỉ chọn thành viên ACTIVE của đội tham gia buổi đá.')
        else:
            post.current_players = team_service.count_members(ctx, post.team_id)
    if roster != party_users(ctx, post):
        raise DomainError('STATE_CONFLICT', 'Danh sách đội vừa thay đổi. Vui lòng thử lại.')
    if post.post_type in ('FIND_OPPONENT', 'RECRUIT_MEMBERS') and not post.team_id:
        invalid('team_id')
    if post.post_type == 'LOOK_FOR_TEAM' and post.team_id is not None:
        invalid('team_id', 'Bài cá nhân không gắn đội.')
    if post.post_type == 'RANDOM_SQUAD' and not post.payment_rule:
        invalid('payment_rule', 'Gom nhóm cần thống nhất thể thức trước khi ghép.')
    size = 5 if post.pitch_type == 'PITCH_5' else 7
    if post.attendance_plan is not None:
        post.current_players = len(roster) + guest_players(post)
        if post.current_players > size:
            invalid('guest_players', 'Tổng người tham gia vượt số người của loại sân.')
        if post.post_type in ('RECRUIT_MEMBERS', 'RANDOM_SQUAD'):
            missing = size - post.current_players
            if missing <= 0:
                invalid('post_type', 'Buổi đá đã đủ người; hãy đăng bài Tìm đối thủ.')
            if 'required_players' in data and data['required_players'] != missing:
                invalid('required_players', f'Buổi đá còn thiếu {missing} người.')
            post.required_players = missing
    if post.post_type == 'FIND_OPPONENT' and post.current_players < size:
        invalid('team_id', 'Đội chưa đủ người.')
    if post.post_type == 'RECRUIT_MEMBERS' and post.attendance_plan is None:
        post.required_players = v.integer(data.get('required_players'), 'required_players', maximum=255)
    if post.post_type == 'RANDOM_SQUAD':
        if post.current_players >= size:
            invalid('post_type', 'Đội đủ người dùng FIND_OPPONENT.')
        if post.team_id:
            team = ctx.session.get(Team, post.team_id)
            if team.creation_type != 'AI_RANDOM':
                # Conversion is explicit and preserves source membership history during merge.
                team.creation_type = 'AI_RANDOM'
        post.required_players = size - post.current_players
    elif post.post_type != 'RECRUIT_MEMBERS':
        post.required_players = None
    assert_available(ctx, party_users(ctx, post), post.match_time, post.end_time)
    ctx.session.add(post)
    ctx.session.flush()
    return post

def guest_players(post):
    return (post.attendance_plan or {}).get('guest_players', 0)


def party_users(ctx, post):
    if post.attendance_plan is not None:
        return set(post.attendance_plan['user_ids'])
    if post.team_id:
        return set(ctx.session.scalars(select(TeamMember.user_id).where(
            TeamMember.team_id == post.team_id, TeamMember.status == 'ACTIVE')))
    return {post.creator_id}

def assert_available(ctx, user_ids, start, end, exclude_post_ids=()):
    if not start or not end:
        return
    # A confirmed or pending-deposit match reserves participant availability. The time overlap is filtered
    # in SQL so the cost depends on matches in this slot, not on every match ever played.
    overlapping = select(MatchPost).join(Match, or_(Match.post_id == MatchPost.post_id, Match.opponent_post_id == MatchPost.post_id)).where(
        Match.status.in_(['SUGGESTED', 'CONFIRMED']), MatchPost.match_time < end, MatchPost.end_time > start)
    for post in {p.post_id: p for p in ctx.session.scalars(overlapping)}.values():
        if post.post_id not in exclude_post_ids and party_users(ctx, post) & set(user_ids):
            raise DomainError('ACTIVE_MATCH_MEMBERSHIP', 'Người chơi đã có kèo trong khoảng giờ này.')
    # A user cannot have simultaneous live RANDOM_SQUAD applications.
    for post in ctx.session.scalars(select(MatchPost).where(MatchPost.post_type == 'RANDOM_SQUAD',
            MatchPost.status.in_(['OPEN', 'LOCKED']), MatchPost.expiry_time > ctx.now(),
            MatchPost.match_time < end, MatchPost.end_time > start)):
        if post.post_id not in exclude_post_ids:
            if party_users(ctx, post) & set(user_ids):
                raise DomainError('ACTIVE_GROUP_REQUEST', 'Đã có yêu cầu gom nhóm cùng giờ.')

def edit_post(ctx, actor, post, data):
    v.fields(data, EDIT_FIELDS)
    if post.creator_id != actor.user_id:
        raise DomainError('FORBIDDEN', 'Chỉ chủ bài được sửa.', 403)
    if post.status != 'OPEN' or post.expiry_time <= ctx.now():
        raise DomainError('STATE_CONFLICT', 'Chỉ sửa bài đang OPEN còn hạn.')
    if 'match_time' in data and 'end_time' not in data:
        post.end_time = None
    apply_fields(ctx, post, data)
    if post.attendance_plan is not None:
        size = 5 if post.pitch_type == 'PITCH_5' else 7
        if post.current_players > size or (post.post_type == 'FIND_OPPONENT' and post.current_players < size):
            invalid('pitch_type', 'Loại sân không khớp quân số buổi đá. Hãy tạo bài mới để thay quân số.')
        if post.post_type in ('RECRUIT_MEMBERS', 'RANDOM_SQUAD'):
            missing = size - post.current_players
            if missing <= 0 or ('required_players' in data and data['required_players'] != missing):
                invalid('required_players', 'Số còn thiếu được tính từ quân số buổi đá.')
            post.required_players = missing
    assert_available(ctx, party_users(ctx, post), post.match_time, post.end_time, [post.post_id])
    return post

def release_after_cancel(ctx, *, match_id, cause):
    match = ctx.session.get(Match, match_id)
    if not match or match.status != 'CANCELLED':
        raise DomainError('STATE_CONFLICT', 'Chỉ mở lại bài sau khi trận đã hủy.')
    from app.services.matchmaking_service import reopen
    related = [ctx.session.get(MatchPost, pid) for pid in (match.post_id, match.opponent_post_id) if pid]
    for post in related:
        if post.booking_id == match.booking_id:
            post.booking_id = None
        if post.status == 'MATCHED':
            post.status = 'LOCKED'
    reopen(ctx, related)
