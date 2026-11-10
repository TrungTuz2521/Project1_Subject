import unittest
from unittest.mock import patch
from datetime import timedelta
import bcrypt
import jwt
from sqlalchemy import select, func
from google.auth.exceptions import TransportError
from app import create_app
from app.extensions import db
from app.models import User
from app.infrastructure.unit_of_work import UnitOfWork
from app.utils.time import utcnow

CLIENT = 'test.apps.googleusercontent.com'
SECRET = 'google-tests-only-secret-at-least-32-bytes'


class GoogleAuthTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                               'JWT_SECRET_KEY': SECRET, 'GOOGLE_CLIENT_ID': CLIENT, 'AUTH_RATE_LIMIT': 0})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        self.headers = {'Origin': 'http://localhost:5173'}
        r = self.client.post('/api/v1/auth/google/challenge', headers=self.headers, json={})
        self.challenge = r.json['data']
        self.claims = dict(sub='google-sub-1', aud=CLIENT, iss='https://accounts.google.com',
                           nonce=self.challenge['nonce'], email='google@example.test', email_verified=True,
                           name='Google Player')

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()

    def post(self, **extra):
        return self.client.post('/api/v1/auth/google', headers=self.headers,
                                json=dict(credential='signed-google-token', challenge=self.challenge['challenge'], **extra))

    def seed(self, **extra):
        with UnitOfWork() as ctx:
            user = User(email=self.claims['email'], full_name='Existing',
                        password_hash=bcrypt.hashpw(b'Password123!', bcrypt.gensalt(rounds=4)).decode(), **extra)
            ctx.session.add(user)
            ctx.session.flush()
            return user.user_id

    @patch('app.services.google_auth_service.id_token.verify_oauth2_token')
    def test_new_and_returning_user_keep_identity_and_sixty_minute_jwt(self, verify):
        verify.return_value = self.claims
        r = self.post()
        self.assertEqual(r.status_code, 200, r.json)
        first = r.json['data']
        self.assertEqual(first['expires_in'], 3600)
        self.assertEqual(first['user']['role'], 'PLAYER')
        token = jwt.decode(first['access_token'], SECRET, algorithms=['HS256'],
                           audience='football-field-web', issuer='football-field-api')
        self.assertEqual(token['exp'] - token['iat'], 3600)
        verify.assert_called_with('signed-google-token', unittest.mock.ANY, CLIENT)
        self.claims['email'] = 'changed@example.test'
        r = self.post()
        self.assertEqual(r.json['data']['user']['user_id'], first['user']['user_id'])
        self.assertEqual(db.session.scalar(select(func.count()).select_from(User)), 1)

    @patch('app.services.google_auth_service.id_token.verify_oauth2_token')
    def test_existing_email_requires_password_and_preserves_role(self, verify):
        uid = self.seed(role='ADMIN')
        verify.return_value = self.claims
        self.assertEqual(self.post().json['error']['code'], 'ACCOUNT_LINK_REQUIRED')
        self.assertEqual(self.post(password='wrong').status_code, 409)
        r = self.post(password='Password123!')
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json['data']['user']['user_id'], uid)
        self.assertEqual(r.json['data']['user']['role'], 'ADMIN')
        self.assertEqual(self.post().status_code, 200)

    @patch('app.services.google_auth_service.id_token.verify_oauth2_token')
    def test_disabled_and_conflicting_accounts_cannot_login(self, verify):
        uid = self.seed(status='BANNED', google_id=self.claims['sub'])
        verify.return_value = self.claims
        self.assertEqual(self.post().status_code, 403)
        with UnitOfWork() as ctx:
            user = ctx.session.get(User, uid)
            user.status = 'ACTIVE'
            user.google_id = 'different-google-sub'
        self.assertEqual(self.post(password='Password123!').json['error']['code'], 'GOOGLE_ACCOUNT_CONFLICT')

    @patch('app.services.google_auth_service.id_token.verify_oauth2_token')
    def test_invalid_signature_expiry_audience_nonce_and_email_fail_closed(self, verify):
        verify.side_effect = ValueError('Invalid signature or expired token')
        self.assertEqual(self.post().status_code, 401)
        verify.side_effect = None
        for field, value in [('aud', 'another-client'), ('nonce', 'wrong'), ('iss', 'attacker'),
                             ('email_verified', False), ('sub', '')]:
            verify.return_value = {**self.claims, field: value}
            self.assertEqual(self.post().status_code, 401, field)
        self.assertEqual(db.session.scalar(select(func.count()).select_from(User)), 0)

    @patch('app.services.google_auth_service.id_token.verify_oauth2_token')
    def test_challenge_origin_and_network_errors(self, verify):
        r = self.client.post('/api/v1/auth/google', json={'credential': 'x', 'challenge': 'x'})
        self.assertEqual(r.status_code, 403)
        signed = self.challenge['challenge']
        self.challenge['challenge'] = 'tampered'
        self.assertEqual(self.post().status_code, 401)
        self.challenge['challenge'] = signed
        verify.side_effect = TransportError('network')
        self.assertEqual(self.post().status_code, 503)
        self.app.config['GOOGLE_CLIENT_ID'] = ''
        self.assertEqual(self.post().status_code, 503)


if __name__ == '__main__':
    unittest.main()
