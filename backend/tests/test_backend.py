import unittest
from datetime import timedelta, timezone
from decimal import Decimal
import bcrypt
import jwt
from sqlalchemy import select, text
from app import create_app
from app.extensions import db
from app.models import User, TeamMember, Notification, FieldComplex, Pitch
from app.utils.time import utcnow, VIETNAM
from app.infrastructure.unit_of_work import UnitOfWork
from app.services import match_service

SECRET = 'test-only-secret-do-not-use-in-production-123456789'
HASH = bcrypt.hashpw(b'Password123!', bcrypt.gensalt(rounds=4)).decode()


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'JWT_SECRET_KEY': SECRET})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()  # ONLY isolated test DB; never application startup.
        with UnitOfWork() as ctx:
            ctx.session.add(FieldComplex(complex_id=1, name='Cụm test', phone='0900000000', address='Hà Nội'))
            ctx.session.add(Pitch(pitch_id=1, complex_id=1, pitch_name='Sân 1', pitch_type='PITCH_5', price_per_slot=600000))
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
            from app.services.auth_service import session_key
            token = jwt.encode(dict(sub=str(uid), role=user.role, skey=session_key(user), iat=now-timedelta(hours=2) if expired else now,
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

    def test_notifications_are_private(self):
        with UnitOfWork() as ctx:
            ctx.session.add(Notification(user_id=self.users[0], notification_type='POST_EXPIRED', title='t', content='c'))
        nid = self.client.get('/api/v1/notifications', headers=self.a).json['data'][0]['notification_id']
        self.assertEqual(self.client.patch(f'/api/v1/notifications/{nid}/read', headers=self.b).status_code, 404)
        self.assertEqual(self.client.patch(f'/api/v1/notifications/{nid}/read', headers=self.a).status_code, 200)

    def test_scan_requires_admin(self):
        self.assertEqual(self.client.post('/api/v1/matchmaking/scan', headers=self.a, json={}).status_code, 403)

    def test_invalid_json_null_expiry_and_naive_time_return_422(self):
        self.assertEqual(self.client.post('/api/v1/auth/login', json=[]).status_code, 422)
        self.assertEqual(self.client.post('/api/v1/match-requests', headers=self.a, json=dict(post_type='LOOK_FOR_TEAM',
            skill_level='AMATEUR', preferred_dates=None)).status_code, 422)
        self.assertEqual(self.client.post('/api/v1/match-requests', headers=self.a, json=dict(post_type='LOOK_FOR_TEAM',
            skill_level='AMATEUR', preferred_dates=['2026-13-40'], window_start='18:00', window_end='21:00')).status_code, 422)

    def test_auth_rate_limit_and_cors(self):
        self.app.config['AUTH_RATE_LIMIT'] = 1
        self.client.post('/api/v1/auth/login', json={'email':'nobody@example.test', 'password':'bad'})
        self.assertEqual(self.client.post('/api/v1/auth/login', json={'email':'nobody@example.test', 'password':'bad'}).status_code, 429)
        r = self.client.options('/api/v1/users/me', headers={'Origin':'http://localhost:5173',
            'Access-Control-Request-Method':'PATCH', 'Access-Control-Request-Headers':'Authorization,Content-Type'})
        self.assertEqual(r.headers.get('Access-Control-Allow-Origin'), 'http://localhost:5173')

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
