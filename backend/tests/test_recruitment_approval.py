import unittest
from datetime import timedelta
from sqlalchemy import select, func
import test_backend
from app.models import MatchPost, MatchProposal, ProposalConfirmation, TeamMember, Notification
from app.infrastructure.unit_of_work import UnitOfWork
from app.jobs.commands import scan_open_posts
from app.utils.time import utcnow


class RecruitmentApprovalTests(unittest.TestCase):
    setUp = test_backend.BackendTests.setUp
    tearDown = test_backend.BackendTests.tearDown
    seed_user = test_backend.BackendTests.seed_user
    header = test_backend.BackendTests.header
    team = test_backend.BackendTests.team
    post = test_backend.BackendTests.post
    respond = test_backend.BackendTests.respond

    def request(self):
        tid = self.team(self.a)
        post_id = self.post(self.a, kind='RECRUIT_MEMBERS', tid=tid, required_players=1)
        r = self.client.post(f'/api/v1/match-posts/{post_id}/participants', headers=self.b, json={})
        self.assertEqual(r.status_code, 201, r.json)
        return tid, post_id, r.json['data']['proposal_id']

    def test_existing_application_needs_only_captain_approval_without_migration(self):
        tid, _, pid = self.request()
        with UnitOfWork() as ctx:
            applicant = ctx.session.scalar(select(ProposalConfirmation).where(
                ProposalConfirmation.proposal_id == pid, ProposalConfirmation.user_id == self.users[1]))
            applicant.decision, applicant.responded_at = 'PENDING', None
        r = self.respond(pid, self.a)
        self.assertEqual(r.json['data']['status'], 'ACCEPTED', r.json)
        self.assertEqual(self.client.get(f'/api/v1/teams/{tid}', headers=self.a).json['data']['active_member_count'], 2)

    def test_team_page_can_finish_legacy_captain_already_accepted_without_candidate_click(self):
        self.app.config['EMAIL_ENABLED'] = True
        tid, post_id, pid = self.request()
        with UnitOfWork() as ctx:
            for c in ctx.session.scalars(select(ProposalConfirmation).where(ProposalConfirmation.proposal_id == pid)):
                c.decision = 'ACCEPTED' if c.user_id == self.users[0] else 'PENDING'
                c.responded_at = ctx.now() if c.decision == 'ACCEPTED' else None
        for _ in range(2):
            r = self.client.patch(f'/api/v1/teams/{tid}/join-requests/{post_id}/respond',headers=self.a,json={'decision':'ACCEPTED'})
            self.assertEqual(r.status_code,200,r.json)
            self.assertEqual(r.json['data']['status'],'ACCEPTED')
        self.assertEqual(self.client.get(f'/api/v1/teams/{tid}',headers=self.a).json['data']['active_member_count'],2)
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.scalar(select(func.count()).select_from(Notification).where(
                Notification.proposal_id == pid,Notification.user_id == self.users[1],
                Notification.notification_type == 'TEAM_JOINED',Notification.delivery_channel == 'EMAIL')),1)

    def test_legacy_already_approved_request_still_expires_without_adding_member(self):
        tid, _, pid = self.request()
        with UnitOfWork() as ctx:
            owner=ctx.session.scalar(select(ProposalConfirmation).where(ProposalConfirmation.proposal_id == pid,
                ProposalConfirmation.user_id == self.users[0]))
            owner.decision,owner.responded_at='ACCEPTED',ctx.now()
            ctx.session.get(MatchProposal,pid).expires_at=utcnow()-timedelta(seconds=1)
        self.assertEqual(self.respond(pid,self.a).status_code,409)
        self.assertEqual(self.client.get(f'/api/v1/teams/{tid}',headers=self.a).json['data']['active_member_count'],1)

    def test_rejection_and_expiry_do_not_add_member_or_emit_success_email(self):
        self.app.config['EMAIL_ENABLED'] = True
        tid, _, pid = self.request()
        self.assertEqual(self.respond(pid, self.a, 'DECLINED').json['data']['status'], 'REJECTED')
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.scalar(select(func.count()).select_from(TeamMember).where(TeamMember.team_id == tid)), 1)
            self.assertEqual(ctx.session.scalar(select(func.count()).select_from(Notification).where(
                Notification.proposal_id == pid, Notification.notification_type == 'TEAM_JOINED')), 0)
        tid, _, pid = self.request()
        with UnitOfWork() as ctx:
            ctx.session.get(MatchProposal, pid).expires_at = utcnow() - timedelta(seconds=1)
        self.assertEqual(self.respond(pid, self.a).status_code, 409)
        self.assertEqual(self.client.get(f'/api/v1/teams/{tid}', headers=self.a).json['data']['active_member_count'], 1)

    def test_outsider_cannot_approve_and_applicant_can_withdraw_before_approval(self):
        tid, post_id, pid = self.request()
        self.assertEqual(self.respond(pid, self.c).status_code, 404)
        r = self.client.delete(f'/api/v1/match-posts/{post_id}/participants/me', headers=self.b)
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(self.respond(pid, self.a).status_code, 409)
        self.assertEqual(self.client.get(f'/api/v1/teams/{tid}', headers=self.a).json['data']['active_member_count'], 1)

    def test_ai_suggestion_still_requires_both_parties_to_accept(self):
        tid = self.team(self.a)
        self.post(self.a, kind='RECRUIT_MEMBERS', tid=tid, required_players=1)
        with UnitOfWork() as ctx:
            ctx.session.add(MatchPost(creator_id=self.users[1], post_type='LOOK_FOR_TEAM', title='Player looking for team',
                pitch_type='PITCH_5', match_time=self.start, end_time=self.start + timedelta(minutes=90),
                skill_level='INTERMEDIATE', expiry_time=self.deadline, current_players=1))
        ids = scan_open_posts()['created_proposal_ids']
        self.assertEqual(len(ids), 1)
        pid = ids[0]
        self.assertEqual(self.respond(pid, self.a).json['data']['status'], 'PENDING_CONFIRMATION')
        self.assertEqual(self.client.get(f'/api/v1/teams/{tid}', headers=self.a).json['data']['active_member_count'], 1)
        self.assertEqual(self.respond(pid, self.b).json['data']['status'], 'ACCEPTED')
