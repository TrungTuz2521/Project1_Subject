"""What the API returns for a request, and what the request form offers."""
from datetime import timedelta
from sqlalchemy import select, or_
from app.models import Booking, Match, MatchParticipant, MatchPost, Pitch, Team
from app.services import booking_policy as policy, booking_service, team_service
from app.services.match_requests.rules import (
    ACTIVE_MATCH, CUTOFF, JOIN, MATCH_HOLD_SECONDS, MAX_DAYS, MAX_OPEN_PER_USER, OPPONENT,
    OPPONENT_LEAD_DAYS, RECRUIT, active_match, booking_parties, can_recruit_for, local_day, person_ref, team_ref)

def request_data(ctx, post):
    result = {
        'request_id': post.post_id, 'request_type': post.post_type, 'status': post.status, 'title': post.title,
        'team': team_ref(ctx, post.team_id), 'booking_id': post.booking_id, 'pitch_type': post.pitch_type,
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
                                 'team': team_ref(ctx, recruit.team_id), 'captain': person_ref(ctx, recruit.creator_id),
                                 'fee_per_player': policy.money(recruit.required_deposit or 0)}
    elif post.post_type == RECRUIT:
        for participant in ctx.session.scalars(select(MatchParticipant).where(MatchParticipant.post_id == post.post_id, MatchParticipant.status == 'ACCEPTED')):
            joiner = ctx.session.scalar(select(MatchPost).where(MatchPost.matched_post_id == post.post_id, MatchPost.creator_id == participant.user_id,
                                                                MatchPost.status == 'MATCHED'))
            person = person_ref(ctx, participant.user_id)
            person.update(party_size=joiner.current_players if joiner else 1, skill_level=joiner.skill_level if joiner else None)
            result['joiners'].append(person)
    return result

def _match_view(ctx, post, match):
    other_id = match.opponent_post_id if match.post_id == post.post_id else match.post_id
    other = ctx.session.get(MatchPost, other_id)
    booking = ctx.session.get(Booking, match.booking_id) if match.booking_id else None
    view = {'match_id': match.match_id, 'status': match.status, 'start_time': match.match_time,
            'end_time': match.match_time + timedelta(minutes=policy.SLOT_MINUTES), 'booking_id': match.booking_id,
            'opponent': {'team': team_ref(ctx, other.team_id), 'skill_level': other.skill_level, 'players': other.current_players,
                         'captain': person_ref(ctx, other.creator_id)},
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

def options(ctx, actor):
    """What the request form offers this user: their teams, bookings that can find an opponent, games to fill."""
    now = ctx.now()
    teams = []
    for team in ctx.session.scalars(team_service.captained(actor.user_id).order_by(Team.team_id)):
        teams.append({'team_id': team.team_id, 'team_name': team.team_name,
                      'last_player_count': team_service.last_player_count(ctx, team.team_id)})
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
