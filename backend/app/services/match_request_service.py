"""Matchmaking by request.

Nobody browses other people's posts. A captain or a player states when and how they can play, the
system records it, scans every open request and pairs the best fits, then tells both sides by email
and in the app. Requests are rows of match_posts:

    FIND_OPPONENT    a full team looks for another team, with or without a pitch already booked
    RECRUIT_MEMBERS  a team with a booked game needs N more players
    LOOK_FOR_TEAM    a player (alone or with up to two friends) wants to join a game ("đá ké")

Status reuses the existing ENUM: OPEN = searching, MATCHED = paired, EXPIRED = nothing found before
the cut-off, CANCELLED = withdrawn. Searching stops one day before kick-off.
"""
from datetime import date, timedelta, timezone
from decimal import Decimal
from sqlalchemy import select, or_, func
from app.contracts.enums import SKILLS, PAYMENT_RULES
from app.contracts.errors import DomainError, invalid
from app.models import Booking, Match, MatchParticipant, MatchPost, Payment, Pitch, Team, TeamMember, User
from app.services import booking_policy as policy, booking_service, notification_service, team_service
from app.utils import validation as v
from app.utils.time import VIETNAM

OPPONENT, RECRUIT, JOIN = 'FIND_OPPONENT', 'RECRUIT_MEMBERS', 'LOOK_FOR_TEAM'
TYPES = (OPPONENT, RECRUIT, JOIN)
CUTOFF = timedelta(hours=24)          # searching (and self-service cancelling) stops one day before kick-off
OPPONENT_LEAD_DAYS = 2                # an opponent is requested at least two days ahead
MAX_DAYS = policy.MAX_ADVANCE_DAYS
MATCH_HOLD_SECONDS = 12 * 3600        # both teams pay their half within twelve hours when the system books
TOLERANCES = (0, 1, 4)                # same level, one level apart, any level
SIZE = {'PITCH_5': 5, 'PITCH_7': 7}
MAX_OPEN_PER_USER = 5
# A team that already booked prefers an opponent without a pitch. Two booked teams are paired only after
# both waited this long for such an opponent, or when the search is about to close.
BOOKED_PAIR_WAIT = timedelta(hours=6)
BOOKED_PAIR_LAST_CALL = timedelta(hours=12)
ACTIVE_MATCH = ('SUGGESTED', 'CONFIRMED')
SKILL_NAMES = {'BEGINNER': 'Mới chơi', 'AMATEUR': 'Phong trào', 'INTERMEDIATE': 'Trung bình', 'SEMI_PRO': 'Bán chuyên', 'PRO': 'Chuyên nghiệp'}

CREATE_FIELDS = ('post_type', 'team_id', 'booking_id', 'pitch_type', 'preferred_dates', 'window_start', 'window_end',
                 'skill_level', 'skill_tolerance', 'payment_rule', 'attendance_user_ids', 'guest_players',
                 'required_players', 'party_size', 'fee_per_player', 'note')
EDIT_FIELDS = ('preferred_dates', 'window_start', 'window_end', 'skill_tolerance', 'required_players', 'fee_per_player', 'note')


# ---------------------------------------------------------------- time helpers

def local_day(moment):
    return moment.astimezone(VIETNAM).date()

def hhmm(moment):
    return moment.astimezone(VIETNAM).strftime('%H:%M')

def label(moment):
    local = moment.astimezone(VIETNAM)
    weekday = ('T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN')[local.weekday()]
    return f'{local:%H:%M} {weekday} {local:%d/%m}'

def fixed(post):
    """A request tied to one game (a booked pitch or a recruit) has no list of dates."""
    return post.preferred_dates is None

def slots(post, now):
    """(start, end) in UTC this request can still be matched on: at least one day ahead."""
    if fixed(post):
        found = [(post.match_time, post.end_time)] if post.match_time else []
    else:
        found = []
        for text in post.preferred_dates or []:
            for start, end in policy.day_slots(date.fromisoformat(text)):
                if hhmm(start) >= post.window_start and hhmm(end) <= post.window_end:
                    found.append((start.astimezone(timezone.utc), end.astimezone(timezone.utc)))
    return [(s, e) for s, e in found if s - now >= CUTOFF]

def search_until(post, now):
    found = slots(post, now)
    return max(s for s, _ in found) - CUTOFF if found else None


# ---------------------------------------------------------------- reading rows

def party_users(post):
    if post.attendance_plan is not None:
        return set(post.attendance_plan.get('user_ids') or [])
    return {post.creator_id}

def head_count(post):
    plan = post.attendance_plan or {}
    return len(plan.get('user_ids') or [post.creator_id]) + int(plan.get('guest_players') or 0)

def active_match(ctx, post_id):
    return ctx.session.scalar(select(Match).where(or_(Match.post_id == post_id, Match.opponent_post_id == post_id),
                                                  Match.status.in_(ACTIVE_MATCH)).order_by(Match.match_id.desc()))

def busy(ctx, user_ids, start, end, ignore_post_ids=()):
    """Someone in user_ids already plays at that time: in a paired game or as an accepted extra player."""
    user_ids = set(user_ids)
    if not user_ids:
        return False
    rows = ctx.session.scalars(select(MatchPost).join(Match, or_(Match.post_id == MatchPost.post_id, Match.opponent_post_id == MatchPost.post_id))
                               .where(Match.status.in_(ACTIVE_MATCH), Match.match_time < end, Match.match_time > start - timedelta(minutes=policy.SLOT_MINUTES)))
    for post in {p.post_id: p for p in rows}.values():
        if post.post_id not in ignore_post_ids and party_users(post) & user_ids:
            return True
    joined = ctx.session.scalar(select(func.count()).select_from(MatchParticipant).join(MatchPost, MatchPost.post_id == MatchParticipant.post_id).where(
        MatchParticipant.user_id.in_(user_ids), MatchParticipant.status == 'ACCEPTED', MatchPost.post_type == RECRUIT,
        MatchPost.match_time < end, MatchPost.end_time > start, MatchPost.post_id.notin_(list(ignore_post_ids) or [0])))
    return bool(joined)

def no_shows(ctx, user_id):
    return ctx.session.scalar(select(func.count()).select_from(Booking).where(Booking.user_id == user_id, Booking.arrival_status == 'NO_SHOW')) or 0

def booking_parties(booking):
    return {booking.user_id} | {p['user_id'] for p in booking.payer_plan or []}


# ---------------------------------------------------------------- validation

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

def can_recruit_for(ctx, user_id, booking):
    if user_id in booking_parties(booking):
        return True
    match = ctx.session.scalar(select(Match).where(Match.booking_id == booking.booking_id, Match.status.in_(ACTIVE_MATCH)))
    if match is None:
        return False
    return any(ctx.session.get(MatchPost, pid).creator_id == user_id for pid in (match.post_id, match.opponent_post_id) if pid)


# ---------------------------------------------------------------- create / edit

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
    ids = data.get('attendance_user_ids', [actor.user_id])
    if not isinstance(ids, list) or not ids or any(type(i) is not int for i in ids) or len(set(ids)) != len(ids) or actor.user_id not in ids:
        invalid('attendance_user_ids', 'Chọn người đi đá, gồm cả bạn, không trùng.')
    members = set(ctx.session.scalars(select(TeamMember.user_id).join(User, User.user_id == TeamMember.user_id).where(
        TeamMember.team_id == team_id, TeamMember.status == 'ACTIVE', User.status == 'ACTIVE', User.role == 'PLAYER')))
    if not set(ids) <= members:
        invalid('attendance_user_ids', 'Chỉ chọn thành viên đang hoạt động của đội.')
    guests = v.integer(data.get('guest_players', 0), 'guest_players', minimum=0, maximum=10)
    post.attendance_plan = {'user_ids': sorted(ids), 'guest_players': guests}
    post.current_players = len(ids) + guests
    size = SIZE[post.pitch_type]
    if post.current_players < size:
        invalid('guest_players', f'Đội cần đủ {size} người để tìm đối (hiện {post.current_players}). Hãy tìm thêm người trước.')
    if post.current_players > size * 2:
        invalid('guest_players', 'Quân số quá đông cho loại sân này.')
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


# ---------------------------------------------------------------- scoring

def skill_gap(a, b):
    return abs(SKILLS.index(a.skill_level) - SKILLS.index(b.skill_level))

def _skill_points(gap):
    return 40 if gap == 0 else 20 if gap == 1 else 0

def opponent_fit(ctx, a, b, now):
    """None, or (tier, points, common slots). Tier 0 = one side already booked (preferred), 1 = neither,
    2 = both booked (one booking is merged into the other)."""
    if a.creator_id == b.creator_id or a.team_id == b.team_id:
        return None
    if a.pitch_type != b.pitch_type or (a.payment_rule and b.payment_rule and a.payment_rule != b.payment_rule):
        return None
    gap = skill_gap(a, b)
    if gap > min(a.skill_tolerance if a.skill_tolerance is not None else 1, b.skill_tolerance if b.skill_tolerance is not None else 1):
        return None
    if party_users(a) & party_users(b):
        return None
    theirs = {s for s, _ in slots(b, now)}
    common = [(s, e) for s, e in slots(a, now) if s in theirs]
    if not common:
        return None
    booked = sum(1 for p in (a, b) if p.booking_id)
    if booked == 2 and now - max(a.created_at, b.created_at) < BOOKED_PAIR_WAIT and min(a.expiry_time, b.expiry_time) - now > BOOKED_PAIR_LAST_CALL:
        return None
    tier = {1: 0, 0: 1, 2: 2}[booked]
    points = 60 + _skill_points(gap) - 10 * min(3, no_shows(ctx, a.creator_id) + no_shows(ctx, b.creator_id))
    return tier, points, common

def join_fit(ctx, recruit, joiner, now, room=None):
    if recruit.creator_id == joiner.creator_id or not recruit.match_time:
        return None
    room = recruit.required_players if room is None else room
    if joiner.current_players > (room or 0):
        return None
    if joiner.pitch_type and joiner.pitch_type != recruit.pitch_type:
        return None
    gap = skill_gap(recruit, joiner)
    if gap > min(recruit.skill_tolerance if recruit.skill_tolerance is not None else 1, joiner.skill_tolerance if joiner.skill_tolerance is not None else 1):
        return None
    if recruit.match_time - now < CUTOFF or recruit.match_time not in {s for s, _ in slots(joiner, now)}:
        return None
    booking = ctx.session.get(Booking, recruit.booking_id) if recruit.booking_id else None
    if booking is None or booking.status != 'CONFIRMED' or joiner.creator_id in booking_parties(booking) | party_users(recruit):
        return None
    return 60 + _skill_points(gap) + (10 if joiner.current_players == room else 0)


# ---------------------------------------------------------------- scanning

def scan(only_post_id=None):
    """One pass: plan every candidate pair without locks, best first, then pair each in its own transaction."""
    from app.infrastructure.unit_of_work import UnitOfWork
    with UnitOfWork() as ctx:
        now = ctx.now()
        rows = list(ctx.session.scalars(select(MatchPost).where(MatchPost.status == 'OPEN', MatchPost.expiry_time > now,
                                                                MatchPost.post_type.in_(TYPES)).order_by(MatchPost.created_at, MatchPost.post_id)))
        teams = [p for p in rows if p.post_type == OPPONENT]
        opponent_pairs = []
        for i, a in enumerate(teams):
            for b in teams[i + 1:]:
                if only_post_id not in (None, a.post_id, b.post_id):
                    continue
                fit = opponent_fit(ctx, a, b, now)
                if fit:
                    tier, points, _ = fit
                    first, second = sorted((a, b), key=lambda p: (p.created_at, p.post_id))
                    # Best fit first; among equal fits prefer using a pitch already booked, then whoever asked first.
                    opponent_pairs.append(((-points, tier, first.created_at, second.created_at, first.post_id, second.post_id), first.post_id, second.post_id))
        recruits = [p for p in rows if p.post_type == RECRUIT]
        joiners = [p for p in rows if p.post_type == JOIN]
        join_pairs = []
        for r in recruits:
            for j in joiners:
                if only_post_id not in (None, r.post_id, j.post_id):
                    continue
                points = join_fit(ctx, r, j, now)
                if points:
                    join_pairs.append(((-points, j.created_at, r.created_at, j.post_id, r.post_id), r.post_id, j.post_id))
    used, made = set(), []
    for _, first, second in sorted(opponent_pairs):
        if first in used or second in used:
            continue
        match_id = pair_opponents(first, second)
        if match_id:
            used.update((first, second))
            made.append(match_id)
    joined = []
    for _, recruit_id, joiner_id in sorted(join_pairs):
        if joiner_id in used:
            continue
        if pair_join(recruit_id, joiner_id):
            used.add(joiner_id)
            joined.append(joiner_id)
    return {'scanned_count': len(rows), 'matches': made, 'joined_requests': joined}

def _free_pitch(ctx, pitch_type, common):
    for start, end in common:
        pitch_id = booking_service.find_match_pitch(ctx, pitch_type=pitch_type, start_time=start, end_time=end)
        if pitch_id:
            return pitch_id, start, end
    return None

def pair_opponents(first_id, second_id):
    from app.infrastructure.unit_of_work import UnitOfWork
    with UnitOfWork() as ctx:
        a, b = ctx.session.get(MatchPost, first_id), ctx.session.get(MatchPost, second_id)
        if a is None or b is None:
            return None
        now = ctx.now()
        fit = opponent_fit(ctx, a, b, now)
        if not fit:
            return None
        bookings = [ctx.session.get(Booking, p.booking_id) for p in (a, b) if p.booking_id]
        choice = None if bookings else _free_pitch(ctx, a.pitch_type, fit[2])
        if not bookings and choice is None:
            return None
        # Lock order: users, teams, pitches, posts, matches, bookings, payments.
        ctx.locks.users(party_users(a) | party_users(b))
        ctx.locks.lock(Team, [a.team_id, b.team_id])
        ctx.locks.lock(Pitch, [bk.pitch_id for bk in bookings] + ([choice[0]] if choice else []))
        ctx.locks.lock(MatchPost, [a.post_id, b.post_id])
        bookings = ctx.locks.lock(Booking, [bk.booking_id for bk in bookings])
        ctx.locks.lock(Payment, [p.payment_id for bk in bookings for p in booking_service.payments_of(ctx, bk.booking_id)])
        if a.status != 'OPEN' or b.status != 'OPEN' or any(bk.status != 'CONFIRMED' for bk in bookings):
            return None
        fit = opponent_fit(ctx, a, b, now)
        if not fit:
            return None
        tier, points, common = fit
        if len(bookings) == 0:
            start, end = choice[1], choice[2]
        else:
            start, end = bookings[0].start_time, bookings[0].end_time
            if (start, end) not in common or any((bk.start_time, bk.end_time) != (start, end) for bk in bookings):
                return None
        if busy(ctx, party_users(a) | party_users(b), start, end, ignore_post_ids=(a.post_id, b.post_id)):
            return None
        if len(bookings) == 0:
            return _pair_new_booking(ctx, a, b, choice[0], start, end, points)
        if len(bookings) == 2:
            keep, drop = sorted(bookings, key=lambda bk: (bk.created_at, bk.booking_id))
            _merge_bookings(ctx, keep, drop)
            booking = keep
        else:
            booking = bookings[0]
        return _pair_on_booking(ctx, a, b, booking, points)

def agreed_rule(a, b):
    return a.payment_rule or b.payment_rule or 'SPLIT_EQUAL'

RULE_NAMES = {'SPLIT_EQUAL': 'chia đều tiền sân', 'LOSER_PAYS_REMAINDER': 'đội thua trả phần còn lại'}

def _owner_post(a, b, booking):
    return (a, b) if a.booking_id == booking.booking_id else (b, a)

def _pair_on_booking(ctx, a, b, booking, points):
    owner, other = _owner_post(a, b, booking)
    now = ctx.now()
    match = Match(post_id=owner.post_id, opponent_post_id=other.post_id, booking_id=booking.booking_id, match_time=booking.start_time,
                  compatibility_score=float(points), status='CONFIRMED', confirmed_at=now)
    ctx.session.add(match)
    ctx.session.flush()
    for post in (owner, other):
        post.status = 'MATCHED'
        post.match_time, post.end_time, post.pitch_id = booking.start_time, booking.end_time, booking.pitch_id
    pitch = ctx.session.get(Pitch, booking.pitch_id)
    for me, them in ((owner, other), (other, owner)):
        merged = me.booking_id and me.booking_id != booking.booking_id
        extra = (' Lượt sân bạn đặt cùng giờ đã được gộp, tiền cọc của bạn được tính vào tiền sân này, phần còn lại trả tại quầy.'
                 if merged else ' Không cần đặt cọc thêm.')
        notification_service.notify(ctx, [me.creator_id], 'MATCH_CONFIRMED', 'Đã tìm được đối',
            f'{_team_line(ctx, them)} sẽ đá với đội bạn lúc {label(booking.start_time)} tại {pitch.pitch_name}.{extra} '
            f'Cách chia tiền: {RULE_NAMES[agreed_rule(a, b)]}. Liên hệ đội trưởng: {_contact(ctx, them.creator_id)}.', match_id=match.match_id)
    ctx.session.flush()
    return match.match_id

def _merge_bookings(ctx, keep, drop):
    """Both teams booked the same time: play on the earlier booking. The other booking closes and its
    deposits move onto the kept one, so they count towards the pitch fee instead of being refunded."""
    for payment in booking_service.payments_of(ctx, drop.booking_id):
        if payment.payment_type == 'BOOKING_DEPOSIT' and payment.status == 'SUCCESS':
            payment.booking_id = keep.booking_id
            payment.note = policy.add_note(payment.note, f'MERGED_FROM #{drop.booking_id} (ghep keo)')
        elif payment.status == 'PENDING':
            payment.status = 'FAILED'
            payment.note = policy.add_note(payment.note, 'Booking gop vao keo')
    drop.status = 'CANCELLED'
    drop.note = policy.add_note(drop.note, f'Gop vao booking #{keep.booking_id} khi ghep keo; coc chuyen sang booking do')
    keep.note = policy.add_note(keep.note, f'Ghep keo: nhan coc tu booking #{drop.booking_id}')
    ctx.session.flush()

def _pair_new_booking(ctx, a, b, pitch_id, start, end, points):
    """Neither team booked: the system holds a pitch and each team pays half the deposit within twelve hours."""
    from app.contracts.errors import SlotUnavailable
    match = Match(post_id=a.post_id, opponent_post_id=b.post_id, match_time=start, compatibility_score=float(points), status='SUGGESTED')
    ctx.session.add(match)
    ctx.session.flush()
    try:
        hold = booking_service.create_match_hold(ctx, match_id=match.match_id, pitch_id=pitch_id, start_time=start, end_time=end,
                                                 source_user_id=a.creator_id, opponent_user_id=b.creator_id, payment_rule=agreed_rule(a, b),
                                                 hold_seconds=MATCH_HOLD_SECONDS)
    except SlotUnavailable:
        ctx.session.rollback()
        return None
    match.booking_id = hold.booking_id
    for post in (a, b):
        post.status = 'MATCHED'
        post.match_time, post.end_time, post.pitch_id = start, end, pitch_id
    pitch = ctx.session.get(Pitch, pitch_id)
    shares = {item['user_id']: item['amount'] for item in hold.payer_plan}
    for me, them in ((a, b), (b, a)):
        notification_service.notify(ctx, [me.creator_id], 'BOOKING_HOLD', 'Đã tìm được đối, cần đặt cọc',
            f'{_team_line(ctx, them)} sẽ đá với đội bạn lúc {label(start)} tại {pitch.pitch_name}. Hệ thống đã giữ sân. '
            f'Phần cọc của đội bạn là {_money(shares[me.creator_id])}, cần trả trước {label(hold.hold_expires_at)} '
            f'trong Lịch đã đặt. Cách chia tiền: {RULE_NAMES[agreed_rule(a, b)]}. Quá hạn mà một đội chưa cọc thì kèo bị hủy.', match_id=match.match_id)
    ctx.session.flush()
    return match.match_id

def pair_join(recruit_id, joiner_id):
    from app.infrastructure.unit_of_work import UnitOfWork
    with UnitOfWork() as ctx:
        recruit, joiner = ctx.session.get(MatchPost, recruit_id), ctx.session.get(MatchPost, joiner_id)
        if recruit is None or joiner is None:
            return False
        ctx.locks.users(party_users(recruit) | party_users(joiner))
        ctx.locks.lock(Team, [recruit.team_id])
        ctx.locks.lock(MatchPost, [recruit_id, joiner_id])
        if recruit.status != 'OPEN' or joiner.status != 'OPEN':
            return False
        now = ctx.now()
        if not join_fit(ctx, recruit, joiner, now):
            return False
        if busy(ctx, party_users(joiner), recruit.match_time, recruit.end_time, ignore_post_ids=(joiner.post_id,)):
            return False
        participant = ctx.session.scalar(select(MatchParticipant).where(MatchParticipant.post_id == recruit_id,
                                                                        MatchParticipant.user_id == joiner.creator_id))
        if participant is None:
            participant = MatchParticipant(post_id=recruit_id, user_id=joiner.creator_id)
            ctx.session.add(participant)
        participant.status, participant.joined_at = 'ACCEPTED', now
        recruit.required_players -= joiner.current_players
        if recruit.required_players <= 0:
            recruit.required_players, recruit.status = 0, 'MATCHED'
        joiner.status, joiner.matched_post_id = 'MATCHED', recruit_id
        joiner.match_time, joiner.end_time, joiner.pitch_id = recruit.match_time, recruit.end_time, recruit.pitch_id
        pitch = ctx.session.get(Pitch, recruit.pitch_id)
        fee = f' Chi phí mỗi người: {_money(recruit.required_deposit)}, trả cho đội trưởng.' if recruit.required_deposit else ''
        who = ctx.session.get(User, joiner.creator_id)
        notification_service.notify(ctx, [joiner.creator_id], 'TEAM_JOINED', 'Đã tìm được trận để đá ké',
            f'Bạn{" và " + str(joiner.current_players - 1) + " bạn đi cùng" if joiner.current_players > 1 else ""} được ghép vào '
            f'trận lúc {label(recruit.match_time)} tại {pitch.pitch_name}.{fee} Liên hệ đội trưởng: {_contact(ctx, recruit.creator_id)}.')
        left = f'Còn thiếu {recruit.required_players} người.' if recruit.required_players else 'Đã đủ người.'
        notification_service.notify(ctx, [recruit.creator_id], 'TEAM_JOINED', 'Có người đá cùng',
            f'{who.full_name} ({SKILL_NAMES[joiner.skill_level]}, {joiner.current_players} người) sẽ đá cùng đội bạn lúc '
            f'{label(recruit.match_time)}. Số điện thoại: {who.phone or "chưa cập nhật"}. {left}')
        ctx.session.flush()
        return True

def _team_line(ctx, post):
    team = ctx.session.get(Team, post.team_id) if post.team_id else None
    return f'Đội {team.team_name} ({SKILL_NAMES[post.skill_level]})' if team else 'Một đội'

def _contact(ctx, user_id):
    user = ctx.session.get(User, user_id)
    return f'{user.full_name}, {user.phone}' if user.phone else user.full_name

def _money(value):
    return f'{int(Decimal(str(value))):,}'.replace(',', '.') + ' ₫'


# ---------------------------------------------------------------- closing and cancelling

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
                notification_service.notify(ctx, [post.creator_id], 'POST_EXPIRED', _not_found_title(post), _not_found_text(post))
    return closed

def _not_found_title(post):
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
        notification_service.notify(ctx, [post.creator_id], 'POST_EXPIRED', _not_found_title(post), f'{reason} Đã quá hạn tìm lại (1 ngày trước giờ đá).')
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
        _guard_cutoff(post, ctx.now())
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
        _guard_cutoff(post, ctx.now())
        if post.post_type == RECRUIT:
            ctx.locks.lock(MatchPost, [post_id])
            _close_recruit(ctx, post, 'Đội trưởng đã hủy yêu cầu tìm người.')
            return post
        if post.post_type == JOIN:
            _withdraw_join(ctx, post)
            return post
        _withdraw_from_match(ctx, actor, post)
        return post

def _guard_cutoff(post, now):
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


# ---------------------------------------------------------------- views

def request_data(ctx, post):
    result = {
        'request_id': post.post_id, 'request_type': post.post_type, 'status': post.status, 'title': post.title,
        'team': _team(ctx, post.team_id), 'booking_id': post.booking_id, 'pitch_type': post.pitch_type,
        'preferred_dates': post.preferred_dates, 'window_start': post.window_start, 'window_end': post.window_end,
        'match_time': post.match_time, 'end_time': post.end_time, 'skill_level': post.skill_level,
        'skill_tolerance': post.skill_tolerance, 'payment_rule': post.payment_rule, 'players': post.current_players,
        'required_players': post.required_players, 'fee_per_player': policy.money(post.required_deposit or 0),
        'note': post.description, 'search_until': post.expiry_time if post.status == 'OPEN' else None,
        'created_at': post.created_at, 'match': None, 'joined_game': None, 'joiners': [],
    }
    if post.pitch_id:
        pitch = ctx.session.get(Pitch, post.pitch_id)
        result['pitch_name'] = pitch.pitch_name if pitch else None
    if post.post_type == OPPONENT:
        match = active_match(ctx, post.post_id) or ctx.session.scalar(select(Match).where(
            or_(Match.post_id == post.post_id, Match.opponent_post_id == post.post_id)).order_by(Match.match_id.desc()))
        if match is not None and (match.status in ACTIVE_MATCH or post.status == 'MATCHED'):
            result['match'] = _match_view(ctx, post, match)
    elif post.post_type == JOIN and post.matched_post_id:
        recruit = ctx.session.get(MatchPost, post.matched_post_id)
        pitch = ctx.session.get(Pitch, recruit.pitch_id) if recruit.pitch_id else None
        result['joined_game'] = {'start_time': recruit.match_time, 'end_time': recruit.end_time, 'pitch_name': pitch.pitch_name if pitch else None,
                                 'team': _team(ctx, recruit.team_id), 'captain': _person(ctx, recruit.creator_id),
                                 'fee_per_player': policy.money(recruit.required_deposit or 0)}
    elif post.post_type == RECRUIT:
        for participant in ctx.session.scalars(select(MatchParticipant).where(MatchParticipant.post_id == post.post_id, MatchParticipant.status == 'ACCEPTED')):
            joiner = ctx.session.scalar(select(MatchPost).where(MatchPost.matched_post_id == post.post_id, MatchPost.creator_id == participant.user_id,
                                                                MatchPost.status == 'MATCHED'))
            person = _person(ctx, participant.user_id)
            person.update(party_size=joiner.current_players if joiner else 1, skill_level=joiner.skill_level if joiner else None)
            result['joiners'].append(person)
    return result

def _match_view(ctx, post, match):
    other_id = match.opponent_post_id if match.post_id == post.post_id else match.post_id
    other = ctx.session.get(MatchPost, other_id)
    booking = ctx.session.get(Booking, match.booking_id) if match.booking_id else None
    view = {'match_id': match.match_id, 'status': match.status, 'start_time': match.match_time,
            'end_time': match.match_time + timedelta(minutes=policy.SLOT_MINUTES), 'booking_id': match.booking_id,
            'opponent': {'team': _team(ctx, other.team_id), 'skill_level': other.skill_level, 'players': other.current_players,
                         'captain': _person(ctx, other.creator_id)},
            'needs_deposit': False, 'my_deposit': None, 'my_deposit_paid': None, 'opponent_deposit_paid': None, 'hold_expires_at': None}
    if booking is not None:
        pitch = ctx.session.get(Pitch, booking.pitch_id)
        view['pitch_name'] = pitch.pitch_name if pitch else None
        if booking.payment_rule not in (None, 'DIRECT_BOOKING'):
            progress = {p['user_id']: p for p in booking_service.payer_progress(ctx, booking)}
            mine, theirs = progress.get(post.creator_id), progress.get(other.creator_id)
            view.update(my_deposit=mine['required_amount'] if mine else None, my_deposit_paid=bool(mine and mine['status'] == 'PAID'),
                        opponent_deposit_paid=bool(theirs and theirs['status'] == 'PAID'),
                        needs_deposit=booking.status == 'PENDING_HOLD' and bool(mine) and mine['status'] != 'PAID',
                        hold_expires_at=booking.hold_expires_at if booking.status == 'PENDING_HOLD' else None)
    return view

def _team(ctx, team_id):
    team = ctx.session.get(Team, team_id) if team_id else None
    return {'team_id': team.team_id, 'team_name': team.team_name} if team else None

def _person(ctx, user_id):
    user = ctx.session.get(User, user_id)
    return {'user_id': user.user_id, 'full_name': user.full_name, 'phone': user.phone}

def options(ctx, actor):
    """What the request form offers this user: their teams, bookings that can find an opponent, games to fill."""
    now = ctx.now()
    teams = []
    for team in ctx.session.scalars(select(Team).join(TeamMember, TeamMember.team_id == Team.team_id).where(
            TeamMember.user_id == actor.user_id, TeamMember.role == 'CAPTAIN', TeamMember.status == 'ACTIVE', Team.status == 'ACTIVE')):
        members = [{'user_id': u.user_id, 'full_name': u.full_name} for u in ctx.session.scalars(select(User).join(TeamMember, TeamMember.user_id == User.user_id).where(
            TeamMember.team_id == team.team_id, TeamMember.status == 'ACTIVE', User.status == 'ACTIVE', User.role == 'PLAYER'))]
        teams.append({'team_id': team.team_id, 'team_name': team.team_name, 'members': members})
    upcoming = list(ctx.session.scalars(select(Booking).where(Booking.status == 'CONFIRMED', Booking.start_time > now + CUTOFF,
                                                              Booking.booking_type != 'MAINTENANCE_LOCK').order_by(Booking.start_time)))
    opponent_bookings, games = [], []
    taken = set(ctx.session.scalars(select(MatchPost.booking_id).where(MatchPost.post_type == OPPONENT, MatchPost.status.in_(('OPEN', 'MATCHED')),
                                                                         MatchPost.booking_id.is_not(None))))
    matched = set(ctx.session.scalars(select(Match.booking_id).where(Match.status.in_(ACTIVE_MATCH), Match.booking_id.is_not(None))))
    lead = local_day(now) + timedelta(days=OPPONENT_LEAD_DAYS)
    for booking in upcoming:
        mine = actor.user_id in booking_parties(booking)
        if not mine and booking.booking_id not in matched:
            continue
        pitch = ctx.session.get(Pitch, booking.pitch_id)
        row = {'booking_id': booking.booking_id, 'pitch_name': pitch.pitch_name, 'pitch_type': pitch.pitch_type,
               'start_time': booking.start_time, 'end_time': booking.end_time}
        if booking.user_id == actor.user_id and booking.booking_id not in taken and booking.booking_id not in matched and local_day(booking.start_time) >= lead:
            opponent_bookings.append(row)
        if can_recruit_for(ctx, actor.user_id, booking):
            games.append(row)
    return {'teams': teams, 'opponent_bookings': opponent_bookings, 'recruit_games': games,
            'rules': {'opponent_lead_days': OPPONENT_LEAD_DAYS, 'cutoff_hours': 24, 'max_days': MAX_DAYS,
                      'deposit_hold_hours': MATCH_HOLD_SECONDS // 3600, 'max_open_requests': MAX_OPEN_PER_USER},
            'today': local_day(now).isoformat()}
