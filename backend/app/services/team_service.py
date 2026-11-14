"""A team is a name and the captain who books and gets the notifications. Players are not on record: the captain
says how many are coming each time they ask for an opponent."""
from sqlalchemy import select
from app.models import Team, TeamMember, MatchPost
from app.contracts.errors import DomainError
from app.utils.validation import text


def captain(ctx, team_id, actor):
    team = ctx.session.get(Team, team_id)
    row = ctx.session.scalar(select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == actor.user_id,
                                                      TeamMember.status == 'ACTIVE', TeamMember.role == 'CAPTAIN'))
    if not team or team.status != 'ACTIVE' or not row:
        raise DomainError('FORBIDDEN', 'Cần đội trưởng đang hoạt động của đội.', 403)
    return team


def captained(actor_id):
    """Query for the active teams this user captains."""
    return select(Team).join(TeamMember, TeamMember.team_id == Team.team_id).where(
        TeamMember.user_id == actor_id, TeamMember.role == 'CAPTAIN', TeamMember.status == 'ACTIVE', Team.status == 'ACTIVE')


def last_player_count(ctx, team_id):
    """How many players the team brought last time, to fill in the next request."""
    return ctx.session.scalar(select(MatchPost.current_players).where(MatchPost.team_id == team_id, MatchPost.post_type == 'FIND_OPPONENT')
                              .order_by(MatchPost.post_id.desc()).limit(1))


def team_data(ctx, team):
    result = {k: getattr(team, k) for k in ('team_id', 'team_name', 'created_by', 'creation_type', 'status')}
    result['last_player_count'] = last_player_count(ctx, team.team_id)
    return result


def create_team(ctx, actor, name):
    team = Team(team_name=text(name, 'team_name', 100), created_by=actor.user_id)
    ctx.session.add(team)
    ctx.session.flush()
    ctx.session.add(TeamMember(team_id=team.team_id, user_id=actor.user_id, role='CAPTAIN'))
    ctx.session.flush()
    return team_data(ctx, team)
