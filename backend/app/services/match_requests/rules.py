"""Constants, time helpers, reading request rows, and wording shared by every part of matchmaking."""
from datetime import date, timedelta, timezone
from sqlalchemy import select, or_, func
from app.models import Booking, Match, MatchParticipant, MatchPost, Team, User
from app.services import booking_policy as policy
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


def can_recruit_for(ctx, user_id, booking):
    if user_id in booking_parties(booking):
        return True
    match = ctx.session.scalar(select(Match).where(Match.booking_id == booking.booking_id, Match.status.in_(ACTIVE_MATCH)))
    if match is None:
        return False
    return any(ctx.session.get(MatchPost, pid).creator_id == user_id for pid in (match.post_id, match.opponent_post_id) if pid)


def agreed_rule(a, b):
    return a.payment_rule or b.payment_rule or 'SPLIT_EQUAL'


RULE_NAMES = {'SPLIT_EQUAL': 'chia đều tiền sân', 'LOSER_PAYS_REMAINDER': 'đội thua trả phần còn lại'}


def team_line(ctx, post):
    team = ctx.session.get(Team, post.team_id) if post.team_id else None
    return f'Đội {team.team_name} ({SKILL_NAMES[post.skill_level]})' if team else 'Một đội'


def contact_line(ctx, user_id):
    user = ctx.session.get(User, user_id)
    return f'{user.full_name}, {user.phone}' if user.phone else user.full_name


def team_ref(ctx, team_id):
    team = ctx.session.get(Team, team_id) if team_id else None
    return {'team_id': team.team_id, 'team_name': team.team_name} if team else None


def person_ref(ctx, user_id):
    user = ctx.session.get(User, user_id)
    return {'user_id': user.user_id, 'full_name': user.full_name, 'phone': user.phone}
