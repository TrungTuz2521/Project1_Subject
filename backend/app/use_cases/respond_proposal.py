from sqlalchemy import select
from datetime import timedelta
from flask import current_app
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Team, MatchPost, MatchProposal, ProposalConfirmation, Match, TeamMember, MatchParticipant
from app.contracts.errors import DomainError, SlotUnavailable
from app.contracts.dto import CommandResult
from app.services import auth_service, matchmaking_service as mm, post_service, team_service, notification_service

def respond_proposal(proposal_id, actor, decision):
    with UnitOfWork() as ctx:
        auth_service.require_player(ctx, actor)
        proposal = ctx.session.get(MatchProposal, proposal_id)
        if not proposal:
            raise DomainError('NOT_FOUND', 'Không tìm thấy đề xuất.', 404)
        posts = [ctx.session.get(MatchPost, pid) for pid in (proposal.source_post_id, proposal.target_post_id) if pid]
        roster = set().union(*(post_service.party_users(ctx, p) for p in posts))
        if proposal.candidate_user_id:
            roster.add(proposal.candidate_user_id)
        ctx.locks.users(roster)
        ctx.locks.lock(Team, [p.team_id for p in posts])
        # The adapter must discover a slot before Pitch → Post locks are acquired.
        booking = current_app.extensions.get('booking_service')
        pitch_id = next((p.pitch_id for p in posts if p.pitch_id), None)
        if proposal.proposal_type == 'OPPONENT' and booking and not pitch_id:
            # Read-only slot discovery; create_match_hold rechecks after locking Pitch.
            pitch_id = booking.find_match_pitch(ctx, pitch_type=posts[0].pitch_type,
                start_time=max(p.match_time for p in posts), end_time=min(p.end_time for p in posts))
        if pitch_id:
            from app.infrastructure.external_tables import lock_pitch
            lock_pitch(ctx, pitch_id)
        ctx.locks.lock(MatchPost, [p.post_id for p in posts])
        actual_roster = set().union(*(post_service.party_users(ctx, p) for p in posts))
        if proposal.candidate_user_id:
            actual_roster.add(proposal.candidate_user_id)
        if roster != actual_roster:
            raise DomainError('STATE_CONFLICT', 'Danh sách đội vừa thay đổi. Vui lòng thử lại.')
        ctx.locks.lock(MatchProposal, [proposal_id])
        confirmations = list(ctx.session.scalars(select(ProposalConfirmation).where(ProposalConfirmation.proposal_id == proposal_id)))
        ctx.locks.lock(ProposalConfirmation, [c.confirmation_id for c in confirmations])
        auth_service.require_player(ctx, actor)
        confirmation = next((c for c in confirmations if c.user_id == actor.user_id), None)
        if not confirmation:
            raise DomainError('NOT_FOUND', 'Không tìm thấy đề xuất.', 404)
        if confirmation.decision != 'PENDING':
            if confirmation.decision != decision:
                raise DomainError('ALREADY_RESPONDED', 'Không thể đổi phản hồi đã chốt.')
            return CommandResult(data=mm.proposal_data(ctx, proposal))
        if proposal.status != 'PENDING_CONFIRMATION':
            raise DomainError('STATE_CONFLICT', 'Đề xuất đã kết thúc.')
        now = ctx.now()
        if proposal.expires_at <= now:
            proposal.status = 'EXPIRED'
            mm.reopen(ctx, posts)
            notification_service.notify(ctx, [c.user_id for c in confirmations], 'PROPOSAL_EXPIRED', 'Đề xuất hết hạn',
                                        'Đề xuất đã hết thời gian phản hồi.', proposal_id=proposal_id)
            return CommandResult('HOLD_EXPIRED', error={'code': 'HOLD_EXPIRED', 'message': 'Đề xuất đã hết hạn.', 'fields': {}}, http_status=409)
        if any(p.status != 'LOCKED' or p.expiry_time <= now for p in posts):
            raise DomainError('STATE_CONFLICT', 'Bài không còn hợp lệ.')
        confirmation.decision, confirmation.responded_at = decision, now
        if decision == 'DECLINED':
            proposal.status = 'REJECTED'
            mm.reopen(ctx, posts)
            if proposal.candidate_user_id:
                participant = ctx.session.scalar(select(MatchParticipant).where(MatchParticipant.post_id == posts[0].post_id,
                    MatchParticipant.user_id == proposal.candidate_user_id))
                if participant and participant.status == 'PENDING':
                    participant.status = 'REJECTED'
            notification_service.notify(ctx, [c.user_id for c in confirmations], 'PROPOSAL_REJECTED', 'Đề xuất bị từ chối',
                                        'Một bên đã từ chối đề xuất.', proposal_id=proposal_id)
        elif all(c.decision == 'ACCEPTED' for c in confirmations):
            for p in posts:
                if p.team_id:
                    team_service.captain(ctx, p.team_id, next_actor(ctx, p.creator_id))
            users = set().union(*(post_service.party_users(ctx, p) for p in posts))
            users.update(c.user_id for c in confirmations)
            from app.models import User
            if any(ctx.session.get(User, uid).status != 'ACTIVE' for uid in users):
                raise DomainError('STATE_CONFLICT', 'Thành viên không còn hoạt động.')
            post_service.assert_available(ctx, users, posts[0].match_time, posts[0].end_time, [p.post_id for p in posts])
            if proposal.proposal_type == 'TEAM_MEMBER':
                team_service.accept_member_proposal(ctx, proposal_id=proposal_id)
                proposal.status, proposal.confirmed_at = 'ACCEPTED', ctx.now()
            else:
                if not booking:
                    raise DomainError('BOOKING_SERVICE_UNAVAILABLE', 'Dịch vụ booking chưa được tích hợp.', 503)
                if posts[0].payment_rule != posts[1].payment_rule:
                    raise DomainError('STATE_CONFLICT', 'Thể thức hai bên không khớp.')
                proposal.status, proposal.confirmed_at = 'ACCEPTED', ctx.now()
                match = Match(post_id=posts[0].post_id, opponent_post_id=posts[1].post_id, proposal_id=proposal_id,
                    match_time=max(p.match_time for p in posts), compatibility_score=float(proposal.compatibility_score), status='SUGGESTED')
                ctx.session.add(match)
                ctx.session.flush()
                try:
                    if not pitch_id:
                        raise SlotUnavailable()
                    hold = booking.create_match_hold(ctx, match_id=match.match_id, pitch_id=pitch_id,
                        start_time=match.match_time, end_time=match.match_time + timedelta(minutes=90),
                        source_user_id=posts[0].creator_id, opponent_user_id=posts[1].creator_id,
                        payment_rule=posts[0].payment_rule)
                except SlotUnavailable:
                    match.status = 'CANCELLED'
                    mm.reopen(ctx, posts)
                    notification_service.notify(ctx, users, 'MATCH_CANCELLED', 'Không còn sân', 'Kèo chưa được giữ sân.', match_id=match.match_id)
                    return CommandResult('SLOT_UNAVAILABLE', error={'code': 'SLOT_UNAVAILABLE', 'message': 'Không còn sân phù hợp.', 'fields': {}}, http_status=409)
                match.booking_id = hold.booking_id
                for p in posts:
                    p.booking_id = hold.booking_id
                notification_service.notify(ctx, [c.user_id for c in confirmations], 'BOOKING_HOLD', 'Đã giữ sân',
                    'Thanh toán cọc trong thời hạn server trả về.', proposal_id=proposal_id, match_id=match.match_id)
        ctx.session.flush()
        return CommandResult(data=mm.proposal_data(ctx, proposal))

def next_actor(ctx, uid):
    from app.contracts.dto import Actor
    return Actor(uid, 'PLAYER')

def accept_member_proposal(ctx, proposal, posts):
    source = posts[0]
    target = posts[1] if len(posts) > 1 else None
    candidate_ids = post_service.party_users(ctx, target) if target else {proposal.candidate_user_id}
    if not candidate_ids or None in candidate_ids or len(candidate_ids) > (source.required_players or 0):
        raise DomainError('STATE_CONFLICT', 'Không đủ chỗ nhận thành viên.')
    if not source.team_id:
        team = Team(team_name=source.title[:100], created_by=source.creator_id, creation_type='AI_RANDOM')
        ctx.session.add(team)
        ctx.session.flush()
        source.team_id = team.team_id
        ctx.session.add(TeamMember(team_id=team.team_id, user_id=source.creator_id, role='CAPTAIN'))
        source.post_type = 'RECRUIT_MEMBERS'
    team_id = source.team_id
    # Parent Team/Post locks protect insert races for these unique memberships.
    existing = list(ctx.session.scalars(select(TeamMember).where(TeamMember.team_id.in_([team_id, target.team_id if target else team_id]))))
    ctx.locks.lock(TeamMember, [m.team_member_id for m in existing])
    participants = list(ctx.session.scalars(select(MatchParticipant).where(MatchParticipant.post_id == source.post_id)))
    ctx.locks.lock(MatchParticipant, [p.participant_id for p in participants])
    for uid in sorted(candidate_ids):
        membership = next((m for m in existing if m.team_id == team_id and m.user_id == uid), None)
        if membership and membership.status == 'ACTIVE':
            raise DomainError('STATE_CONFLICT', 'Thành viên đã ở trong đội.')
        if membership:
            membership.status, membership.role = 'ACTIVE', 'MEMBER'
        else:
            ctx.session.add(TeamMember(team_id=team_id, user_id=uid, role='MEMBER'))
        participant = next((p for p in participants if p.user_id == uid), None)
        if not participant:
            participant = MatchParticipant(post_id=source.post_id, user_id=uid)
            ctx.session.add(participant)
        participant.status = 'ACCEPTED'
        if target and target.team_id:
            for m in existing:
                if m.team_id == target.team_id and m.user_id == uid:
                    m.status = 'LEFT'
    if target:
        target.status = 'MATCHED'
        if target.team_id:
            ctx.session.get(Team, target.team_id).status = 'INACTIVE'
    ctx.session.flush()
    source.current_players = team_service.count_members(ctx, team_id)
    source.required_players -= len(candidate_ids)
    source.status = 'OPEN' if source.required_players else 'MATCHED'
    notification_service.notify(ctx, candidate_ids | {source.creator_id}, 'TEAM_JOINED', 'Đã ghép thành viên',
                                'Thành viên đã được cập nhật vào đội.', proposal_id=proposal.proposal_id)
    team = ctx.session.get(Team, team_id)
    if team.creation_type == 'AI_RANDOM' and not source.required_players and not source.booking_id:
        ctx.session.add(MatchPost(creator_id=source.creator_id, team_id=team_id, post_type='FIND_OPPONENT',
            title=source.title, pitch_id=source.pitch_id, pitch_type=source.pitch_type, match_time=source.match_time,
            end_time=source.end_time, skill_level=source.skill_level, payment_rule=source.payment_rule or 'SPLIT_EQUAL',
            current_players=source.current_players, expiry_time=source.expiry_time))
    from app.contracts.dto import MembershipResult
    ctx.session.flush()
    first = ctx.session.scalar(select(MatchParticipant).where(MatchParticipant.post_id == source.post_id,
        MatchParticipant.user_id == min(candidate_ids)))
    return MembershipResult(team_id, min(candidate_ids), first.participant_id, source.required_players, source.status)
