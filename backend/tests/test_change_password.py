import unittest
from sqlalchemy import select
import bcrypt
import test_backend
from app.models import User
from app.infrastructure.unit_of_work import UnitOfWork


class ChangePasswordTests(unittest.TestCase):
    setUp = test_backend.BackendTests.setUp
    tearDown = test_backend.BackendTests.tearDown
    seed_user = test_backend.BackendTests.seed_user
    header = test_backend.BackendTests.header

    def change(self, **patch):
        body = dict(current_password='Password123!', new_password='NewPassword456!', confirm_password='NewPassword456!')
        body.update(patch)
        return self.client.post('/api/v1/users/me/password', headers=self.a, json=body)

    def test_change_hashes_new_password_and_old_password_no_longer_logs_in(self):
        before = self.client.get('/api/v1/users/me', headers=self.a).json['data']
        self.assertTrue(before['has_password'])
        r = self.change()
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json['data'], {'changed': True})
        with UnitOfWork() as ctx:
            user = ctx.session.get(User, self.users[0])
            self.assertNotEqual(user.password_hash, 'NewPassword456!')
            self.assertTrue(bcrypt.checkpw(b'NewPassword456!', user.password_hash.encode()))
            # Another user is unaffected.
            self.assertTrue(bcrypt.checkpw(b'Password123!', ctx.session.get(User, self.users[1]).password_hash.encode()))
        self.assertEqual(self.client.post('/api/v1/auth/login', json={'email':before['email'],'password':'Password123!'}).status_code, 401)
        self.assertEqual(self.client.post('/api/v1/auth/login', json={'email':before['email'],'password':'NewPassword456!'}).status_code, 200)

    def test_wrong_old_password_bad_confirmation_same_and_utf8_bounds_leave_hash_unchanged(self):
        with UnitOfWork() as ctx:
            before = ctx.session.get(User, self.users[0]).password_hash
        for body in [dict(current_password='wrong'), dict(confirm_password='mismatch'),
                     dict(new_password='short',confirm_password='short'),
                     dict(new_password='ấ'*25,confirm_password='ấ'*25),
                     dict(new_password='Password123!',confirm_password='Password123!')]:
            self.assertEqual(self.change(**body).status_code, 422, body.keys())
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.get(User,self.users[0]).password_hash,before)
        self.assertEqual(self.client.get('/api/v1/users/me',headers=self.a).status_code,200)

    def test_authentication_and_strict_own_account_body(self):
        self.assertEqual(self.client.post('/api/v1/users/me/password',json={}).status_code,401)
        self.assertEqual(self.change(user_id=self.users[1]).status_code,422)
        self.assertEqual(self.client.post('/api/v1/users/me/password',headers=self.a,json={'current_password':'Password123!'}).status_code,422)
        with UnitOfWork() as ctx:
            ctx.session.get(User,self.users[0]).status='BANNED'
        self.assertEqual(self.change().status_code,403)

    def test_google_only_account_has_no_password_change_action(self):
        with UnitOfWork() as ctx:
            user=ctx.session.get(User,self.users[0]);user.password_hash=None;user.google_id='google-only-test'
        self.a=self.header(self.users[0])  # Credentials changed: the earlier token is revoked by design.
        self.assertFalse(self.client.get('/api/v1/users/me',headers=self.a).json['data']['has_password'])
        self.assertEqual(self.change().json['error']['code'],'PASSWORD_NOT_SET')

    def test_password_change_attempts_are_rate_limited(self):
        self.app.config['AUTH_RATE_LIMIT']=1
        self.assertEqual(self.change(current_password='wrong').status_code,422)
        self.assertEqual(self.change(current_password='wrong').status_code,429)
