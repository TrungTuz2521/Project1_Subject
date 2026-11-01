import unittest
from datetime import timedelta, timezone
from decimal import Decimal
import bcrypt
import jwt
from sqlalchemy import select, text
from app import create_app
from app.extensions import db
from app.models import User, Team, TeamMember, MatchPost, MatchProposal, ProposalConfirmation, Match, Notification
from app.utils.time import utcnow, VIETNAM
from app.infrastructure.unit_of_work import UnitOfWork
from app.contracts.dto import Actor, BookingHold
from app.contracts.errors import SlotUnavailable, DomainError
from app.services import match_service, matchmaking_service as mm
from app.jobs.commands import scan_open_posts, expire_proposals

SECRET = 'test-only-secret-do-not-use-in-production-123456789'
HASH = bcrypt.hashpw(b'Password123!', bcrypt.gensalt(rounds=4)).decode()

class FakeBooking:
    def __init__(self, unavailable=False):
        self.calls = 0
        self.unavailable = unavailable
    def find_match_pitch(self, ctx, **kwargs):
        return 1
    def create_match_hold(self, ctx, **kwargs):
        self.calls += 1
        if self.unavailable:
            raise SlotUnavailable()
        import json
        deadline = ctx.now() + timedelta(minutes=5)
        plan = [dict(user_id=kwargs['source_user_id'], amount='60000.00'),
                dict(user_id=kwargs['opponent_user_id'], amount='60000.00')]
        ctx.session.execute(text('INSERT INTO bookings (booking_id,status,hold_expires_at,payer_plan) VALUES (1,:status,:deadline,:plan)'),
                            dict(status='PENDING_HOLD', deadline=deadline.replace(tzinfo=None).isoformat(), plan=json.dumps(plan)))
        return BookingHold(1, 'PENDING_HOLD', deadline, Decimal('600000'), Decimal('120000'), plan)

class BackendTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'JWT_SECRET_KEY': SECRET})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()  # ONLY isolated test DB; never application startup.
        with db.engine.begin() as conn:
            conn.execute(text('CREATE TABLE pitches (pitch_id INTEGER PRIMARY KEY, pitch_type TEXT, status TEXT)'))
            conn.execute(text("INSERT INTO pitches VALUES (1,'PITCH_5','ACTIVE')"))
            conn.execute(text('CREATE TABLE bookings (booking_id INTEGER PRIMARY KEY, status TEXT, hold_expires_at TEXT, payer_plan TEXT)'))
            conn.execute(text('CREATE TABLE payments (payment_id INTEGER PRIMARY KEY,booking_id INTEGER,user_id INTEGER,payment_type TEXT,status TEXT,amount NUMERIC)'))
        self.client = self.app.test_client()
        self.users = [self.seed_user(f'u{i}@example.test') for i in range(1, 4)]
        self.a, self.b, self.c = [self.header(u) for u in self.users]
        local = utcnow().astimezone(VIETNAM) + timedelta(days=1)
        self.start = local.replace(hour=18, minute=0, second=0, microsecond=0)
        self.deadline = utcnow() + timedelta(hours=1)

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()

    def seed_user(self, email, role='PLAYER'):
        with UnitOfWork() as ctx:
            user = User(full_name='Test User', email=email, password_hash=HASH, role=role)
            ctx.session.add(user)
            ctx.session.flush()
            return user.user_id

    def header(self, uid, expired=False):
        with UnitOfWork() as ctx:
            user = ctx.session.get(User, uid)
            now = utcnow()
            token = jwt.encode(dict(sub=str(uid), role=user.role, iat=now-timedelta(hours=2) if expired else now,
                                    exp=now-timedelta(hours=1) if expired else now+timedelta(hours=1),
                                    iss='football-field-api', aud='football-field-web'), SECRET, algorithm='HS256')
        return {'Authorization': 'Bearer ' + token}

    def team(self, header, full=False):
        r = self.client.post('/api/v1/teams', headers=header, json={'team_name': 'FC Test'})
        self.assertEqual(r.status_code, 201, r.json)
        tid = r.json['data']['team_id']
        if full:
            with UnitOfWork() as ctx:
                for i in range(4):
                    u = User(full_name='Member', email=f'{tid}-{i}@example.test', password_hash=HASH)
                    ctx.session.add(u)
                    ctx.session.flush()
                    ctx.session.add(TeamMember(team_id=tid, user_id=u.user_id))
        return tid

    def post(self, header, kind='FIND_OPPONENT', tid=None, skill='INTERMEDIATE', **extra):
        data = dict(post_type=kind, title='Test match', skill_level=skill, pitch_type='PITCH_5',
                    match_time=self.start.isoformat(), expiry_time=self.deadline.isoformat(), payment_rule='SPLIT_EQUAL')
        if tid:
            data['team_id'] = tid
        data.update(extra)
        r = self.client.post('/api/v1/match-posts', headers=header, json=data)
        self.assertEqual(r.status_code, 201, r.json)
        return r.json['data']['post_id']

    def pair(self):
        source = self.post(self.a, tid=self.team(self.a, full=True))
        target = self.post(self.b, tid=self.team(self.b, full=True))
        result = scan_open_posts()
        self.assertEqual(len(result['created_proposal_ids']), 1)
        return source, target, result['created_proposal_ids'][0]

    def respond(self, pid, header, decision='ACCEPTED'):
        return self.client.post(f'/api/v1/match-proposals/{pid}/respond', headers=header, json={'decision': decision})

    def test_register_login_profile_contract_and_hash(self):
        r = self.client.post('/api/v1/auth/register', json=dict(full_name='New Player', email=' NEW@example.test ', password='Password123!'))
        self.assertEqual(r.status_code, 201)
        self.assertNotIn('password_hash', r.json['data'])
        self.assertIn('server_time', r.json['meta'])
        with UnitOfWork() as ctx:
            user = ctx.session.scalar(select(User).where(User.email == 'new@example.test'))
            self.assertTrue(bcrypt.checkpw(b'Password123!', user.password_hash.encode()))
        r = self.client.post('/api/v1/auth/login', json=dict(email='NEW@example.test', password='Password123!'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json['data']['expires_in'], 3600)
        h = {'Authorization': 'Bearer '+r.json['data']['access_token']}
        r = self.client.patch('/api/v1/users/me', headers=h, json={'phone': '0912345678', 'full_name': 'Updated'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get('/api/v1/users/me', headers=h).json['data']['full_name'], 'Updated')

    def test_auth_rejects_role_injection_duplicate_and_long_password(self):
        payload = dict(full_name='New Player', email='new@example.test', password='Password123!', role='ADMIN')
        self.assertEqual(self.client.post('/api/v1/auth/register', json=payload).status_code, 422)
        payload.pop('role')
        payload['email'] = 'u1@example.test'
        self.assertEqual(self.client.post('/api/v1/auth/register', json=payload).status_code, 409)
        payload['password'] = 'é'*37
        self.assertEqual(self.client.post('/api/v1/auth/register', json=payload).status_code, 422)

    def test_plaintext_seed_never_authenticates(self):
        with UnitOfWork() as ctx:
            ctx.session.get(User, self.users[0]).password_hash = 'demo123@'
        r = self.client.post('/api/v1/auth/login', json=dict(email='u1@example.test', password='demo123@'))
        self.assertEqual(r.status_code, 401)

    def test_expired_token_disabled_account_and_profile_protected_fields(self):
        self.assertEqual(self.client.get('/api/v1/users/me', headers=self.header(self.users[0], True)).json['error']['code'], 'TOKEN_EXPIRED')
        self.assertEqual(self.client.patch('/api/v1/users/me', headers=self.a, json={'role': 'ADMIN'}).status_code, 422)
        with UnitOfWork() as ctx:
            ctx.session.get(User, self.users[0]).status = 'BANNED'
        self.assertEqual(self.client.get('/api/v1/users/me', headers=self.a).status_code, 403)

    def test_team_permissions_and_pagination(self):
        tid = self.team(self.a)
        r = self.client.get('/api/v1/teams?page=1&page_size=6', headers=self.a)
        self.assertEqual(r.json['meta']['total'], 1)
        self.assertEqual(r.json['data'][0]['active_member_count'], 1)
        self.assertEqual(self.client.get(f'/api/v1/teams/{tid}', headers=self.b).status_code, 404)
        self.assertEqual(self.client.patch(f'/api/v1/teams/{tid}', headers=self.b, json={'team_name': 'Hijack'}).status_code, 403)
        self.assertEqual(self.client.delete(f'/api/v1/teams/{tid}/members/me', headers=self.a).json['error']['code'], 'CAPTAIN_TRANSFER_REQUIRED')

    def test_post_validation_and_public_privacy(self):
        tid = self.team(self.a)
        r = self.client.post('/api/v1/match-posts', headers=self.a, json=dict(post_type='FIND_OPPONENT', title='Short team', team_id=tid,
             skill_level='INTERMEDIATE', pitch_type='PITCH_5', match_time=self.start.isoformat(), expiry_time=self.deadline.isoformat(), payment_rule='SPLIT_EQUAL'))
        self.assertEqual(r.status_code, 422)
        pid = self.post(self.a, kind='LOOK_FOR_TEAM')
        payload = self.client.get(f'/api/v1/match-posts/{pid}').json['data']
        self.assertNotIn('email', payload)
        self.assertEqual(payload['end_time'], (self.start+timedelta(minutes=90)).astimezone(timezone.utc).isoformat().replace('+00:00','Z'))
        self.assertEqual(self.client.patch(f'/api/v1/match-posts/{pid}', headers=self.b, json={'title': 'Hijack'}).status_code, 403)
        self.assertEqual(self.client.patch(f'/api/v1/match-posts/{pid}', headers=self.a, json={'required_deposit': '1'}).status_code, 422)

    def test_ai_filters_skill_payment_rule_and_duplicate_scan(self):
        a = self.post(self.a, tid=self.team(self.a, True))
        b = self.post(self.b, tid=self.team(self.b, True), skill='PRO')
        self.assertEqual(scan_open_posts()['created_proposal_ids'], [])
        with UnitOfWork() as ctx:
            ctx.session.get(MatchPost, b).skill_level = 'AMATEUR'
        result = scan_open_posts()
        self.assertEqual(len(result['created_proposal_ids']), 1)
        self.assertEqual(scan_open_posts()['created_proposal_ids'], [])
        self.assertEqual(self.client.get(f"/api/v1/match-proposals/{result['created_proposal_ids'][0]}", headers=self.c).status_code, 404)

    def test_decline_reopens_posts_and_is_idempotent(self):
        a, b, pid = self.pair()
        self.assertEqual(self.respond(pid, self.a, 'DECLINED').status_code, 200)
        self.assertEqual(self.respond(pid, self.a, 'DECLINED').status_code, 200)
        self.assertEqual(self.respond(pid, self.a, 'ACCEPTED').status_code, 409)
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.get(MatchPost, a).status, 'OPEN')
            self.assertEqual(ctx.session.get(MatchPost, b).status, 'OPEN')

    def test_missing_booking_adapter_rolls_back_second_confirmation(self):
        a, b, pid = self.pair()
        self.assertEqual(self.respond(pid, self.a).status_code, 200)
        self.assertEqual(self.respond(pid, self.b).status_code, 503)
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.scalar(select(func_count(Match))), 0)
            c = ctx.session.scalar(select(ProposalConfirmation).where(ProposalConfirmation.proposal_id == pid, ProposalConfirmation.user_id == self.users[1]))
            self.assertEqual(c.decision, 'PENDING')

    def test_opponent_hold_once_and_no_early_confirmation(self):
        adapter = FakeBooking()
        self.app.extensions['booking_service'] = adapter
        a, b, pid = self.pair()
        self.respond(pid, self.a)
        r = self.respond(pid, self.b)
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(self.respond(pid, self.b).status_code, 200)
        self.assertEqual(adapter.calls, 1)
        with UnitOfWork() as ctx:
            match = ctx.session.scalar(select(Match))
            self.assertEqual(match.status, 'SUGGESTED')
            self.assertEqual(ctx.session.get(MatchPost, a).status, 'LOCKED')
            with self.assertRaises(DomainError):
                match_service.confirm_after_deposit(ctx, booking_id=1)

    def test_slot_unavailable_commits_failure_and_reopens(self):
        self.app.extensions['booking_service'] = FakeBooking(True)
        a, b, pid = self.pair()
        self.respond(pid, self.a)
        r = self.respond(pid, self.b)
        self.assertEqual(r.status_code, 409, r.json)
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.scalar(select(Match)).status, 'CANCELLED')
            self.assertEqual(ctx.session.get(MatchPost, a).status, 'OPEN')
            self.assertEqual(ctx.session.get(MatchProposal, pid).status, 'ACCEPTED')

    def test_deposit_confirmation_requires_each_payer_and_is_idempotent(self):
        self.app.extensions['booking_service'] = FakeBooking()
        a, b, pid = self.pair()
        self.respond(pid, self.a)
        self.respond(pid, self.b)
        with UnitOfWork() as ctx:
            ctx.session.execute(text("UPDATE bookings SET status='CONFIRMED'"))
            ctx.session.execute(text("INSERT INTO payments VALUES(1,1,:uid,'BOOKING_DEPOSIT','SUCCESS',120000)"), {'uid': self.users[0]})
        with UnitOfWork() as ctx:
            with self.assertRaises(DomainError):
                match_service.confirm_after_deposit(ctx, booking_id=1)
        with UnitOfWork() as ctx:
            ctx.session.execute(text("INSERT INTO payments VALUES(2,1,:uid,'BOOKING_DEPOSIT','SUCCESS',60000)"), {'uid': self.users[1]})
            match = match_service.confirm_after_deposit(ctx, booking_id=1)
            self.assertEqual(match.status, 'CONFIRMED')
            match_service.confirm_after_deposit(ctx, booking_id=1)
            self.assertEqual(ctx.session.get(MatchPost, a).status, 'MATCHED')

    def test_recruitment_accepts_only_after_both_and_no_booking(self):
        tid = self.team(self.a)
        post_id = self.post(self.a, kind='RECRUIT_MEMBERS', tid=tid, required_players=1)
        r = self.client.post(f'/api/v1/match-posts/{post_id}/participants', headers=self.b, json={})
        self.assertEqual(r.status_code, 201, r.json)
        pid = r.json['data']['proposal_id']
        self.respond(pid, self.a)
        self.assertEqual(self.client.get(f'/api/v1/teams/{tid}', headers=self.a).json['data']['active_member_count'], 1)
        self.assertEqual(self.respond(pid, self.b).status_code, 200)
        self.assertEqual(self.respond(pid, self.b).status_code, 200)
        self.assertEqual(self.client.get(f'/api/v1/teams/{tid}', headers=self.a).json['data']['active_member_count'], 2)
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.scalar(select(func_count(Match))), 0)
            self.assertEqual(ctx.session.execute(text('SELECT COUNT(*) FROM bookings')).scalar(), 0)

    def test_expiry_reopens_and_notifications_are_private(self):
        a, b, pid = self.pair()
        with UnitOfWork() as ctx:
            ctx.session.get(MatchProposal, pid).expires_at = utcnow()-timedelta(seconds=1)
        self.assertEqual(expire_proposals(), 1)
        self.assertEqual(expire_proposals(), 0)
        r = self.client.get('/api/v1/notifications', headers=self.a)
        nid = r.json['data'][0]['notification_id']
        self.assertEqual(self.client.patch(f'/api/v1/notifications/{nid}/read', headers=self.b).status_code, 404)
        self.assertEqual(self.client.patch(f'/api/v1/notifications/{nid}/read', headers=self.a).status_code, 200)

    def test_scan_requires_admin(self):
        self.assertEqual(self.client.post('/api/v1/matchmaking/scan', headers=self.a, json={}).status_code, 403)

    def test_invalid_json_null_expiry_and_naive_time_return_422(self):
        self.assertEqual(self.client.post('/api/v1/auth/login', json=[]).status_code, 422)
        self.assertEqual(self.client.post('/api/v1/match-posts', headers=self.a, json=dict(post_type='LOOK_FOR_TEAM',
            title='Bad expiry', skill_level='AMATEUR', expiry_time=None)).status_code, 422)
        self.assertEqual(self.client.post('/api/v1/match-posts', headers=self.a, json=dict(post_type='LOOK_FOR_TEAM',
            title='Bad time', skill_level='AMATEUR', expiry_time=self.deadline.isoformat(), match_time='2026-10-29T18:00:00')).status_code, 422)

    def test_auth_rate_limit_and_cors(self):
        self.app.config['AUTH_RATE_LIMIT'] = 1
        self.client.post('/api/v1/auth/login', json={'email':'nobody@example.test', 'password':'bad'})
        self.assertEqual(self.client.post('/api/v1/auth/login', json={'email':'nobody@example.test', 'password':'bad'}).status_code, 429)
        r = self.client.options('/api/v1/users/me', headers={'Origin':'http://localhost:5173',
            'Access-Control-Request-Method':'PATCH', 'Access-Control-Request-Headers':'Authorization,Content-Type'})
        self.assertEqual(r.headers.get('Access-Control-Allow-Origin'), 'http://localhost:5173')

    def test_random_squad_creates_temporary_team_without_booking(self):
        first = self.post(self.a, kind='RANDOM_SQUAD')
        second = self.post(self.b, kind='RANDOM_SQUAD')
        pid = scan_open_posts()['created_proposal_ids'][0]
        self.assertEqual(self.respond(pid, self.a).status_code, 200)
        r = self.respond(pid, self.b)
        self.assertEqual(r.status_code, 200, r.json)
        with UnitOfWork() as ctx:
            source = ctx.session.get(MatchPost, first)
            self.assertEqual(source.post_type, 'RECRUIT_MEMBERS')
            self.assertEqual(source.required_players, 3)
            self.assertEqual(ctx.session.get(Team, source.team_id).creation_type, 'AI_RANDOM')
            self.assertEqual(ctx.session.get(MatchPost, second).status, 'MATCHED')
            self.assertEqual(ctx.session.execute(text('SELECT COUNT(*) FROM bookings')).scalar(), 0)

    def test_captain_join_response_contract_and_withdrawal(self):
        tid = self.team(self.a)
        post_id = self.post(self.a, kind='RECRUIT_MEMBERS', tid=tid, required_players=2)
        r = self.client.post(f'/api/v1/teams/{tid}/join-requests', headers=self.b, json={})
        self.assertEqual(r.status_code, 201)
        r = self.client.patch(f'/api/v1/teams/{tid}/join-requests/{post_id}/respond', headers=self.a, json={'decision':'ACCEPTED'})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json['data']['status'], 'PENDING')
        self.assertIn('participant_id', r.json['data'])
        r = self.client.delete(f'/api/v1/match-posts/{post_id}/participants/me', headers=self.b)
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json['data']['status'], 'CANCELLED')

    def test_mismatched_payment_rule_not_matched_and_overlap_blocked(self):
        first = self.post(self.a, tid=self.team(self.a, True))
        second = self.post(self.b, tid=self.team(self.b, True), payment_rule='LOSER_PAYS_REMAINDER')
        self.assertEqual(scan_open_posts()['created_proposal_ids'], [])
        with UnitOfWork() as ctx:
            ctx.session.get(MatchPost, second).payment_rule = 'SPLIT_EQUAL'
        self.app.extensions['booking_service'] = FakeBooking()
        pid = scan_open_posts()['created_proposal_ids'][0]
        self.respond(pid, self.a)
        self.respond(pid, self.b)
        r = self.client.post('/api/v1/match-posts', headers=self.a, json=dict(post_type='LOOK_FOR_TEAM', title='Overlap',
            skill_level='AMATEUR', expiry_time=self.deadline.isoformat(), match_time=self.start.isoformat(), pitch_type='PITCH_5'))
        self.assertEqual(r.status_code, 409, r.json)

    def test_expired_deposit_cannot_revive_and_cancellation_reopens(self):
        self.app.extensions['booking_service'] = FakeBooking()
        a, b, pid = self.pair()
        self.respond(pid, self.a)
        self.respond(pid, self.b)
        with UnitOfWork() as ctx:
            ctx.session.execute(text("UPDATE bookings SET status='CONFIRMED',hold_expires_at=:deadline"),
                                {'deadline': (utcnow()-timedelta(seconds=1)).replace(tzinfo=None).isoformat()})
        with UnitOfWork() as ctx:
            with self.assertRaises(DomainError):
                match_service.confirm_after_deposit(ctx, booking_id=1)
        with UnitOfWork() as ctx:
            ctx.session.execute(text("UPDATE bookings SET status='EXPIRED'"))
            result = match_service.cancel_after_booking_change(ctx, booking_id=1, cause='HOLD_TIMEOUT')
            self.assertEqual(result.status, 'CANCELLED')
            self.assertEqual(ctx.session.get(MatchPost, a).status, 'OPEN')
            self.assertIsNone(ctx.session.get(MatchPost, a).booking_id)
            match_service.cancel_after_booking_change(ctx, booking_id=1, cause='HOLD_TIMEOUT')

    def test_confirmation_at_deadline_persists_expiry(self):
        a, b, pid = self.pair()
        with UnitOfWork() as ctx:
            deadline = utcnow()-timedelta(seconds=1)
            ctx.session.get(MatchProposal, pid).expires_at = deadline
        self.assertEqual(self.respond(pid, self.a).status_code, 409)
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.get(MatchProposal, pid).status, 'EXPIRED')
            self.assertEqual(ctx.session.get(MatchPost, b).status, 'OPEN')

    def test_booking_parties_are_display_context_not_payment_allocation(self):
        self.app.extensions['booking_service'] = FakeBooking()
        a, b, pid = self.pair()
        self.respond(pid, self.a)
        self.respond(pid, self.b)
        with UnitOfWork() as ctx:
            parties = match_service.get_booking_parties(ctx, booking_id=1)
            self.assertEqual(parties.booking_id, 1)
            self.assertEqual(parties.source['representative_user_id'], self.users[0])
            self.assertEqual(parties.opponent['representative_user_id'], self.users[1])
            self.assertEqual(parties.source['team_id'], ctx.session.get(MatchPost, a).team_id)
            self.assertEqual(parties.opponent['team_id'], ctx.session.get(MatchPost, b).team_id)
            from app.utils.serialization import encode
            payload = encode(parties)
            self.assertEqual(set(payload['source']), {'team_id', 'team_name', 'representative_user_id'})
            self.assertNotIn('outcome', payload)
            self.assertNotIn('remaining_amount', payload['source'])

    def test_direct_booking_has_no_artificial_match_parties(self):
        with UnitOfWork() as ctx:
            self.assertIsNone(match_service.get_booking_parties(ctx, booking_id=999))

    def test_booking_balance_dto_uses_one_total_for_both_rules(self):
        from app.contracts.dto import BookingBalance, ManualReceipt
        from app.utils.serialization import encode
        for rule in ('SPLIT_EQUAL', 'LOSER_PAYS_REMAINDER'):
            balance = BookingBalance(booking_id=21, payment_rule=rule, total_amount=Decimal('600000'),
                deposit_collected_amount=Decimal('120000'), remaining_collected_amount=Decimal('0'),
                collected_amount=Decimal('120000'), outstanding_amount=Decimal('480000'),
                payment_status='PARTIAL', qr_payload='test-only-qr', transfer_reference='BOOKING-21')
            payload = encode(balance)
            self.assertEqual(payload['outstanding_amount'], '480000.00')
            self.assertEqual(payload['transfer_reference'], 'BOOKING-21')
            self.assertNotIn('payers', payload)
            self.assertNotIn('outcome', payload)
        # Receipts can represent split cash/bank collections without assigning teams.
        receipts = [ManualReceipt('CASH', Decimal('180000')),
                    ManualReceipt('BANK_TRANSFER', Decimal('300000'), 'statement-test-1')]
        self.assertEqual(sum(r.amount for r in receipts), Decimal('480000'))
        self.assertEqual(encode(receipts)[1]['amount'], '300000.00')

def func_count(model):
    from sqlalchemy import func
    return func.count(model.__table__.primary_key.columns.values()[0])

if __name__ == '__main__':
    unittest.main()
