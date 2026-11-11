"""Shared fixture for Tú's tests. FakeGateway exists only here: runtime never registers it."""
import unittest
from datetime import timedelta
from decimal import Decimal
import bcrypt
import jwt
from sqlalchemy import select
from app import create_app
from app.contracts.dto import GatewayResult
from app.extensions import db
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Booking, FieldComplex, Payment, Pitch, TeamMember, User
from app.jobs.commands import scan_open_posts
from app.services.booking_policy import day_slots
from app.use_cases.process_payment import process_gateway_callback
from app.utils.time import VIETNAM, utcnow

SECRET = 'test-only-secret-do-not-use-in-production-123456789'
HASH = bcrypt.hashpw(b'Password123!', bcrypt.gensalt(rounds=4)).decode()

class FakeGateway:
    """Test double, clearly not a real gateway. Records calls so tests can prove nothing is sent twice."""
    def __init__(self):
        self.created, self.refund_requests = [], []
        self.payment_state = 'PENDING'
        self.refund_state = 'SUCCESS'
        self.seen_refunds = set()
        self.raise_on_create = False
    def create_payment(self, reference, amount, expires_at, callback_url, *, created_at, client_ip='127.0.0.1'):
        if self.raise_on_create:
            raise TimeoutError()
        self.created.append(reference)
        return GatewayResult('PENDING', reference, Decimal(amount), payment_url=f'https://fake.test/pay/{reference}', expires_at=expires_at)
    def query_payment(self, reference, *, amount, transaction_date):
        return GatewayResult(self.payment_state, reference, Decimal(amount), provider_reference='GWQ')
    def request_refund(self, merchant_reference, refund_reference, amount, *, transaction_date):
        self.refund_requests.append(refund_reference)
        self.seen_refunds.add(refund_reference)
        return GatewayResult(self.refund_state, refund_reference, Decimal(amount))
    def query_refund(self, refund_reference, *, merchant_reference, amount, transaction_date):
        state = self.refund_state if refund_reference in self.seen_refunds else 'NOT_FOUND'
        return GatewayResult(state, refund_reference, Decimal(amount))
    def cancel_payment(self, reference):
        return 'UNSUPPORTED'

class BookingCase(unittest.TestCase):
    URI = 'sqlite://'
    EXTRA_CONFIG = {'TESTING': True}

    def setUp(self):
        self.now = utcnow().replace(microsecond=0)
        self.app = create_app({**self.EXTRA_CONFIG, 'SQLALCHEMY_DATABASE_URI': self.URI, 'JWT_SECRET_KEY': SECRET,
                               'CLOCK': lambda: self.now, 'BANK_BIN': '970436', 'BANK_ACCOUNT_NO': '0011001234567',
                               'AUTH_RATE_LIMIT': 100000})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()  # ONLY isolated test DB; never application startup.
        self.gateway = FakeGateway()
        self.app.extensions['payment_gateways'] = {'VNPAY': self.gateway}
        with UnitOfWork() as ctx:
            ctx.session.add(FieldComplex(complex_id=1, name='Cụm test', phone='0900000000', address='Hà Nội'))
            ctx.session.flush()
            ctx.session.add_all([
                Pitch(pitch_id=1, complex_id=1, pitch_name='Sân 5A', pitch_type='PITCH_5', price_per_slot=Decimal('600000')),
                Pitch(pitch_id=2, complex_id=1, pitch_name='Sân 5B', pitch_type='PITCH_5', price_per_slot=Decimal('600000')),
                Pitch(pitch_id=3, complex_id=1, pitch_name='Sân 7A', pitch_type='PITCH_7', price_per_slot=Decimal('900000')),
                Pitch(pitch_id=4, complex_id=1, pitch_name='Sân lẻ', pitch_type='PITCH_7', price_per_slot=Decimal('300001')),
                Pitch(pitch_id=5, complex_id=1, pitch_name='Sân tạm dừng', pitch_type='PITCH_7', price_per_slot=Decimal('600000'), status='INACTIVE'),
            ])
        self.client = self.app.test_client()
        self.ua, self.ub, self.uc = [self.seed_user(f'u{i}@example.test') for i in range(1, 4)]
        self.uadmin = self.seed_user('admin@example.test', 'ADMIN')
        self.a, self.b, self.c, self.admin = [self.header(u) for u in (self.ua, self.ub, self.uc, self.uadmin)]

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()

    def seed_user(self, email, role='PLAYER'):
        with UnitOfWork() as ctx:
            user = User(full_name='Người ' + email[:2], email=email, password_hash=HASH, role=role)
            ctx.session.add(user)
            ctx.session.flush()
            return user.user_id

    def header(self, uid):
        from app.services.auth_service import session_key
        with UnitOfWork() as ctx:
            user = ctx.session.get(User, uid)
            role, skey = user.role, session_key(user)
        real = utcnow()
        token = jwt.encode(dict(sub=str(uid), role=role, skey=skey, iat=real, exp=real + timedelta(hours=1), iss='football-field-api', aud='football-field-web'),
                           SECRET, algorithm='HS256')
        return {'Authorization': 'Bearer ' + token}

    def slot(self, days=1, index=8):
        day = self.now.astimezone(VIETNAM).date() + timedelta(days=days)
        return list(day_slots(day))[index]

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)

    def go_after(self, moment, seconds=60):
        self.now = moment + timedelta(seconds=seconds)

    def hold(self, header=None, pitch_id=1, days=1, index=8):
        start, end = self.slot(days, index)
        r = self.client.post('/api/v1/bookings', headers=header or self.a, json={'pitch_id': pitch_id, 'start_time': start.isoformat(), 'end_time': end.isoformat()})
        self.assertEqual(r.status_code, 201, r.json)
        return r.json['data']

    def open_deposit(self, booking_id, header=None):
        r = self.client.post('/api/v1/payments/deposit', headers=header or self.a, json={'booking_id': booking_id, 'payment_method': 'VNPAY'})
        self.assertIn(r.status_code, (200, 201), r.json)
        return r.json['data']

    def callback(self, session, state='SUCCESS', amount=None):
        return process_gateway_callback('VNPAY', GatewayResult(state, session['transaction_code'], Decimal(amount or session['amount']), provider_reference='GW1'))

    def confirmed(self, header=None, **kwargs):
        data = self.hold(header, **kwargs)
        self.callback(self.open_deposit(data['booking_id'], header))
        return data

    def booking(self, booking_id):
        with UnitOfWork() as ctx:
            return ctx.session.get(Booking, booking_id)

    def payments(self, booking_id):
        with UnitOfWork() as ctx:
            return list(ctx.session.scalars(select(Payment).where(Payment.booking_id == booking_id).order_by(Payment.payment_id)))

    def team(self, header):
        r = self.client.post('/api/v1/teams', headers=header, json={'team_name': 'FC Test'})
        self.assertEqual(r.status_code, 201, r.json)
        tid = r.json['data']['team_id']
        with UnitOfWork() as ctx:
            for i in range(4):
                user = User(full_name='Member', email=f'{tid}-{i}@example.test', password_hash=HASH)
                ctx.session.add(user)
                ctx.session.flush()
                ctx.session.add(TeamMember(team_id=tid, user_id=user.user_id))
        return tid

    def post(self, header, rule='SPLIT_EQUAL'):
        start, _ = self.slot()
        data = dict(post_type='FIND_OPPONENT', title='Test match', skill_level='INTERMEDIATE', pitch_type='PITCH_5', match_time=start.isoformat(),
                    expiry_time=(self.now + timedelta(hours=1)).isoformat(), payment_rule=rule, team_id=self.team(header))
        r = self.client.post('/api/v1/match-posts', headers=header, json=data)
        self.assertEqual(r.status_code, 201, r.json)
        return r.json['data']['post_id']

    def respond(self, proposal_id, header):
        return self.client.post(f'/api/v1/match-proposals/{proposal_id}/respond', headers=header, json={'decision': 'ACCEPTED'})

    def agreed_match(self, rule='SPLIT_EQUAL'):
        """Runs Đức's real flow through two acceptances. Returns (source post, target post, proposal, response)."""
        first, second = self.post(self.a, rule), self.post(self.b, rule)
        proposal = scan_open_posts()['created_proposal_ids'][0]
        self.assertEqual(self.respond(proposal, self.a).status_code, 200)
        return first, second, proposal, self.respond(proposal, self.b)

    def match_booking(self, rule='SPLIT_EQUAL'):
        _, _, _, response = self.agreed_match(rule)
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['data']['booking_id'], response.json['data']['match_id']
