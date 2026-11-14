"""Validating, creating and editing requests."""
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import select, func
from app.contracts.enums import SKILLS, PAYMENT_RULES
from app.contracts.errors import DomainError, invalid
from app.models import Booking, Match, MatchPost, Pitch, Team
from app.services import booking_policy as policy, team_service
from app.utils import validation as v
from app.services.match_requests.rules import (
    ACTIVE_MATCH, JOIN, MAX_DAYS, MAX_OPEN_PER_USER, OPPONENT, OPPONENT_LEAD_DAYS, RECRUIT, SIZE, TOLERANCES,
    TYPES, can_recruit_for, fixed, label, local_day, search_until)

CREATE_FIELDS = ('post_type', 'team_id', 'booking_id', 'pitch_type', 'preferred_dates', 'window_start', 'window_end',
                 'skill_level', 'skill_tolerance', 'payment_rule', 'player_count',
                 'required_players', 'party_size', 'fee_per_player', 'note')
EDIT_FIELDS = ('preferred_dates', 'window_start', 'window_end', 'skill_tolerance', 'required_players', 'fee_per_player', 'note')


def _hhmm(value, key):
    if not isinstance(value, str) or len(value) != 5 or value[2] != ':' or not (value[:2] + value[3:]).isdigit():
        invalid(key, 'Giờ dạng HH:MM.')
    if not 0 <= int(value[:2]) <= 23 or not 0 <= int(value[3:]) <= 59:
        invalid(key, 'Giờ dạng HH:MM.')
    return value

def _dates(ctx, value, earliest_offset):
    if not isinstance(value, list) or len(value) != 1:
        invalid('preferred_dates', 'Chọn một ngày đá.')
    today = local_day(ctx.now())
    result = []
    for item in value:
        try:
            day = date.fromisoformat(item) if isinstance(item, str) else None
        except ValueError:
            day = None
        if day is None:
            invalid('preferred_dates', 'Ngày dạng YYYY-MM-DD.')
        if day < today + timedelta(days=earliest_offset):
            invalid('preferred_dates', 'Tìm đối phải gửi trước ngày đá ít nhất 2 ngày.' if earliest_offset == OPPONENT_LEAD_DAYS
                    else 'Ngày đá phải ở tương lai.')
        if day > today + timedelta(days=MAX_DAYS):
            invalid('preferred_dates', f'Chỉ tìm trước tối đa {MAX_DAYS} ngày.')
        result.append(day.isoformat())
    if len(set(result)) != len(result):
        invalid('preferred_dates', 'Các ngày không được trùng nhau.')
    return sorted(result)

def _window(post, data):
    start, end = _hhmm(data.get('window_start'), 'window_start'), _hhmm(data.get('window_end'), 'window_end')
    if start >= end:
        invalid('window_end', 'Giờ kết thúc phải sau giờ bắt đầu.')
    post.window_start, post.window_end = start, end

def _skill(post, data, edit=False):
    if not edit:
        post.skill_level = v.enum(data.get('skill_level'), 'skill_level', SKILLS)
    if 'skill_tolerance' in data or not edit:
        value = data.get('skill_tolerance', 1)
        if type(value) is not int or value not in TOLERANCES:
            invalid('skill_tolerance', 'Chọn ngang trình độ, chênh 1 bậc hoặc bất kỳ.')
        post.skill_tolerance = value

def _note(post, data):
    if 'note' in data:
        post.description = v.text(data['note'], 'note', 500, minimum=0, nullable=True) or None

def _fee(post, data):
    if 'fee_per_player' in data:
        value = data['fee_per_player']
        post.required_deposit = Decimal('0') if value in (None, '', '0') else policy.parse_whole_vnd(value, 'fee_per_player')

def _require_usable(ctx, post, message):
    until = search_until(post, ctx.now())
    if until is None:
        invalid('preferred_dates' if not fixed(post) else 'booking_id', message)
    post.expiry_time = until

def _eligible_booking(ctx, actor, booking_id, *, purpose):
    booking = ctx.session.get(Booking, v.integer(booking_id, 'booking_id'))
    if booking is None or booking.status != 'CONFIRMED' or booking.booking_type == 'MAINTENANCE_LOCK':
        invalid('booking_id', 'Chọn một lượt đã đặt và đã cọc.')
    if purpose == OPPONENT:
        if booking.user_id != actor.user_id:
            invalid('booking_id', 'Chỉ dùng lượt sân do chính bạn đặt.')
        if ctx.session.scalar(select(Match.match_id).where(Match.booking_id == booking.booking_id, Match.status.in_(ACTIVE_MATCH))):
            invalid('booking_id', 'Lượt sân này đã có kèo.')
        if ctx.session.scalar(select(MatchPost.post_id).where(MatchPost.booking_id == booking.booking_id, MatchPost.post_type == OPPONENT,
                                                              MatchPost.status.in_(('OPEN', 'MATCHED')))):
            invalid('booking_id', 'Lượt sân này đang được dùng để tìm đối.')
        if local_day(booking.start_time) < local_day(ctx.now()) + timedelta(days=OPPONENT_LEAD_DAYS):
            invalid('booking_id', 'Tìm đối phải gửi trước ngày đá ít nhất 2 ngày.')
    elif not can_recruit_for(ctx, actor.user_id, booking):
        invalid('booking_id', 'Chỉ tìm thêm người cho lượt đá của bạn.')
    return booking

def create_request(ctx, actor, data):
    v.fields(data, CREATE_FIELDS, ('post_type', 'skill_level'))
    kind = v.enum(data['post_type'], 'post_type', TYPES)
    open_count = ctx.session.scalar(select(func.count()).select_from(MatchPost).where(MatchPost.creator_id == actor.user_id, MatchPost.status == 'OPEN'))
    if open_count >= MAX_OPEN_PER_USER:
        raise DomainError('TOO_MANY_REQUESTS', f'Bạn đang có {open_count} yêu cầu đang tìm. Hủy bớt trước khi gửi thêm.')
    post = MatchPost(creator_id=actor.user_id, post_type=kind, title='Yêu cầu', current_players=1, status='OPEN',
                     expiry_time=ctx.now(), required_deposit=Decimal('0'))
    _skill(post, data)
    _note(post, data)
    if kind == OPPONENT:
        _opponent(ctx, actor, post, data)
    elif kind == RECRUIT:
        _recruit(ctx, actor, post, data)
    else:
        _join(ctx, actor, post, data)
    post.title = title(ctx, post)[:150]
    ctx.session.add(post)
    ctx.session.flush()
    return post

def _opponent(ctx, actor, post, data):
    team_id = v.integer(data.get('team_id'), 'team_id')
    ctx.locks.users([actor.user_id])
    ctx.locks.lock(Team, [team_id])
    team_service.captain(ctx, team_id, actor)
    post.team_id = team_id
    # NULL = no preference: the other team's rule is used, equal split when neither cares.
    rule = data.get('payment_rule')
    post.payment_rule = None if rule in (None, 'ANY') else v.enum(rule, 'payment_rule', PAYMENT_RULES)
    if data.get('booking_id') is not None:
        booking = _eligible_booking(ctx, actor, data['booking_id'], purpose=OPPONENT)
        pitch = ctx.session.get(Pitch, booking.pitch_id)
        post.booking_id, post.pitch_id, post.pitch_type = booking.booking_id, pitch.pitch_id, pitch.pitch_type
        post.match_time, post.end_time = booking.start_time, booking.end_time
    else:
        post.pitch_type = v.enum(data.get('pitch_type'), 'pitch_type', tuple(SIZE))
        post.preferred_dates = _dates(ctx, data.get('preferred_dates'), OPPONENT_LEAD_DAYS)
        _window(post, data)
    # The captain is the only one on record; the rest of the squad is just a number.
    size = SIZE[post.pitch_type]
    count = v.integer(data.get('player_count'), 'player_count', minimum=1, maximum=99)
    if count < size:
        invalid('player_count', f'Đội cần đủ {size} người để tìm đối (hiện {count}). Hãy tìm thêm người trước.')
    if count > size * 2:
        invalid('player_count', 'Quân số quá đông cho loại sân này.')
    post.current_players = count
    post.attendance_plan = {'user_ids': [actor.user_id], 'guest_players': count - 1}
    _require_usable(ctx, post, 'Không còn khung giờ nào cách lúc này hơn 1 ngày.')

def _recruit(ctx, actor, post, data):
    booking = _eligible_booking(ctx, actor, data.get('booking_id'), purpose=RECRUIT)
    pitch = ctx.session.get(Pitch, booking.pitch_id)
    post.booking_id, post.pitch_id, post.pitch_type = booking.booking_id, pitch.pitch_id, pitch.pitch_type
    post.match_time, post.end_time = booking.start_time, booking.end_time
    post.required_players = v.integer(data.get('required_players'), 'required_players', minimum=1, maximum=10)
    _fee(post, data)
    if data.get('team_id') is not None:
        team_service.captain(ctx, v.integer(data['team_id'], 'team_id'), actor)
        post.team_id = data['team_id']
    if ctx.session.scalar(select(MatchPost.post_id).where(MatchPost.booking_id == booking.booking_id, MatchPost.post_type == RECRUIT,
                                                          MatchPost.creator_id == actor.user_id, MatchPost.status == 'OPEN')):
        invalid('booking_id', 'Lượt đá này đã có yêu cầu tìm thêm người đang mở.')
    _require_usable(ctx, post, 'Chỉ tìm thêm người khi còn hơn 1 ngày trước giờ đá.')

def _join(ctx, actor, post, data):
    post.pitch_type = v.enum(data['pitch_type'], 'pitch_type', tuple(SIZE)) if data.get('pitch_type') else None
    post.preferred_dates = _dates(ctx, data.get('preferred_dates'), 1)
    _window(post, data)
    size = v.integer(data.get('party_size', 1), 'party_size', minimum=1, maximum=3)
    post.current_players = size
    post.attendance_plan = {'user_ids': [actor.user_id], 'guest_players': size - 1}
    _require_usable(ctx, post, 'Không còn khung giờ nào cách lúc này hơn 1 ngày.')

def edit_request(ctx, actor, post, data):
    v.fields(data, EDIT_FIELDS)
    if post.creator_id != actor.user_id:
        raise DomainError('NOT_FOUND', 'Không tìm thấy yêu cầu.', 404)
    if post.status != 'OPEN':
        raise DomainError('STATE_CONFLICT', 'Chỉ sửa được yêu cầu đang tìm.')
    if fixed(post) and ({'preferred_dates', 'window_start', 'window_end'} & set(data)):
        invalid('preferred_dates', 'Yêu cầu gắn với lượt sân đã đặt không đổi được ngày giờ.')
    if 'preferred_dates' in data:
        post.preferred_dates = _dates(ctx, data['preferred_dates'], OPPONENT_LEAD_DAYS if post.post_type == OPPONENT else 1)
    if 'window_start' in data or 'window_end' in data:
        _window(post, {'window_start': data.get('window_start', post.window_start), 'window_end': data.get('window_end', post.window_end)})
    _skill(post, data, edit=True)
    _note(post, data)
    if post.post_type == RECRUIT:
        if 'required_players' in data:
            post.required_players = v.integer(data['required_players'], 'required_players', minimum=1, maximum=10)
        _fee(post, data)
    elif 'required_players' in data or 'fee_per_player' in data:
        invalid('required_players', 'Chỉ yêu cầu tìm thêm người có trường này.')
    _require_usable(ctx, post, 'Không còn khung giờ nào cách lúc này hơn 1 ngày.')
    post.title = title(ctx, post)[:150]
    return post

def title(ctx, post):
    team = ctx.session.get(Team, post.team_id) if post.team_id else None
    when = label(post.match_time) if fixed(post) and post.match_time else ', '.join(
        date.fromisoformat(d).strftime('%d/%m') for d in post.preferred_dates or [])
    name = {OPPONENT: 'Tìm đối', RECRUIT: 'Tìm thêm người', JOIN: 'Đá ké'}[post.post_type]
    return f'{name}{" · " + team.team_name if team else ""} · {when}'
