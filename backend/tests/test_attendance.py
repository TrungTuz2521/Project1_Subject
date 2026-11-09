import unittest
from datetime import timedelta
from sqlalchemy import select, func
import test_backend
from app.models import MatchPost, TeamMember, Booking
from app.infrastructure.unit_of_work import UnitOfWork
from app.services import post_service
from app.jobs.commands import scan_open_posts


class AttendanceTests(unittest.TestCase):
    setUp = test_backend.BackendTests.setUp
    tearDown = test_backend.BackendTests.tearDown
    seed_user = test_backend.BackendTests.seed_user
    header = test_backend.BackendTests.header
    team = test_backend.BackendTests.team
    post = test_backend.BackendTests.post
    respond = test_backend.BackendTests.respond

    def test_captain_and_four_guests_can_find_opponent_without_fake_accounts(self):
        tid = self.team(self.a)
        pid = self.post(self.a, tid=tid, attendance_user_ids=[self.users[0]], guest_players=4)
        data = self.client.get(f'/api/v1/match-posts/{pid}').json['data']
        self.assertEqual((data['current_players'], data['registered_players'], data['guest_players']), (5, 1, 4))
        self.assertEqual(self.client.get(f'/api/v1/teams/{tid}', headers=self.a).json['data']['active_member_count'], 1)
        self.post(self.b, tid=self.team(self.b), attendance_user_ids=[self.users[1]], guest_players=4)
        self.assertEqual(len(scan_open_posts()['created_proposal_ids']), 1)

    def test_recruit_two_people_counts_seven_with_only_three_accounts_and_retry_is_safe(self):
        tid = self.team(self.a)
        pid = self.post(self.a, kind='RECRUIT_MEMBERS', tid=tid, pitch_type='PITCH_7',
                        attendance_user_ids=[self.users[0]], guest_players=4, required_players=2)
        for expected, header in ((6, self.b), (7, self.c)):
            response = self.client.post(f'/api/v1/match-posts/{pid}/participants', headers=header, json={})
            self.assertEqual(response.status_code, 201, response.json)
            proposal = response.json['data']['proposal_id']
            self.assertEqual(self.respond(proposal, self.a).status_code, 200)
            self.assertEqual(self.respond(proposal, header).status_code, 200)
            self.assertEqual(self.respond(proposal, header).status_code, 200)
            data = self.client.get(f'/api/v1/match-posts/{pid}').json['data']
            self.assertEqual(data['current_players'], expected)
        self.assertEqual((data['registered_players'], data['guest_players'], data['required_players'], data['status']), (3, 4, 0, 'MATCHED'))
        self.assertEqual(self.client.get(f'/api/v1/teams/{tid}', headers=self.a).json['data']['active_member_count'], 3)
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.scalar(select(func.count()).select_from(Booking)), 0)
        # Captain publishes the filled session, preserving all seven people.
        self.post(self.a, tid=tid, pitch_type='PITCH_7', attendance_user_ids=self.users, guest_players=4)
        uid = self.seed_user('opponent@example.test')
        h = self.header(uid)
        self.post(h, tid=self.team(h), pitch_type='PITCH_7', attendance_user_ids=[uid], guest_players=6)
        self.assertEqual(len(scan_open_posts()['created_proposal_ids']), 1)

    def test_each_date_has_its_own_roster_without_changing_permanent_members(self):
        tid = self.team(self.a, full=True)
        first = self.post(self.a, tid=tid, attendance_user_ids=[self.users[0]], guest_players=4)
        second = self.post(self.a, kind='RECRUIT_MEMBERS', tid=tid, match_time=(self.start+timedelta(days=1)).isoformat(),
                           attendance_user_ids=[self.users[0]], guest_players=3, required_players=1)
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.get(MatchPost, first).current_players, 5)
            later = ctx.session.get(MatchPost, second)
            self.assertEqual((later.current_players, later.required_players), (4, 1))
            self.assertEqual(post_service.party_users(ctx, later), {self.users[0]})
            self.assertEqual(ctx.session.scalar(select(func.count()).select_from(TeamMember).where(TeamMember.team_id==tid)), 5)

    def test_rejects_duplicate_foreign_missing_captain_and_overflow_attendance(self):
        tid = self.team(self.a)
        base = dict(post_type='FIND_OPPONENT', title='Invalid roster', skill_level='INTERMEDIATE', team_id=tid,
                    pitch_type='PITCH_5', match_time=self.start.isoformat(), expiry_time=self.deadline.isoformat(), payment_rule='SPLIT_EQUAL')
        for ids, guests in (([self.users[0], self.users[0]], 3), ([self.users[0],self.users[1]], 3), ([self.users[1]],4), ([self.users[0]],5), ([self.users[0]],-1)):
            response = self.client.post('/api/v1/match-posts', headers=self.a, json={**base, 'attendance_user_ids':ids,'guest_players':guests})
            self.assertEqual(response.status_code, 422, response.json)
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.scalar(select(func.count()).select_from(MatchPost)), 0)

    def test_existing_teammate_not_in_session_can_join_once(self):
        tid = self.team(self.a)
        with UnitOfWork() as ctx:
            ctx.session.add(TeamMember(team_id=tid, user_id=self.users[1]))
        pid = self.post(self.a, kind='RECRUIT_MEMBERS', tid=tid, attendance_user_ids=[self.users[0]], guest_players=3, required_players=1)
        r = self.client.post(f'/api/v1/match-posts/{pid}/participants', headers=self.b, json={})
        self.assertEqual(r.status_code, 201, r.json)
        self.respond(r.json['data']['proposal_id'], self.a)
        self.assertEqual(self.respond(r.json['data']['proposal_id'], self.b).status_code, 200)
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.get(MatchPost,pid).current_players,5)
            self.assertEqual(ctx.session.scalar(select(func.count()).select_from(TeamMember).where(TeamMember.team_id==tid)),2)

    def test_random_groups_preserve_guest_counts_in_generated_opponent_post(self):
        self.post(self.a, kind='RANDOM_SQUAD', attendance_user_ids=[self.users[0]],guest_players=2)
        self.post(self.b, kind='RANDOM_SQUAD', attendance_user_ids=[self.users[1]],guest_players=1)
        proposal = scan_open_posts()['created_proposal_ids'][0]
        self.respond(proposal,self.a)
        self.assertEqual(self.respond(proposal,self.b).status_code,200)
        with UnitOfWork() as ctx:
            generated = ctx.session.scalar(select(MatchPost).where(MatchPost.post_type=='FIND_OPPONENT'))
            self.assertEqual(generated.current_players,5)
            self.assertEqual(generated.attendance_plan,{'user_ids':sorted(self.users[:2]),'guest_players':3})
