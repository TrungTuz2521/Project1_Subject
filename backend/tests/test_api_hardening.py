from datetime import timedelta
import jwt
from sqlalchemy import event
from booking_fixtures import BookingCase, SECRET
from app.extensions import db
from app.infrastructure.unit_of_work import UnitOfWork
from app.jobs.scheduler import run_once
from app.models import Match, MatchPost
from app.services.match_service import complete_finished_matches
from app.utils.time import utcnow


class ApiHardeningTests(BookingCase):
    def login(self, email, password='Password123!'):
        return self.client.post('/api/v1/auth/login', json={'email': email, 'password': password})

    def record(self, bid, uid, amount, ref):
        r = self.client.post('/api/v1/admin/payments/record', headers=self.admin, json=dict(
            booking_id=bid, user_id=uid, amount=amount, payment_type='BOOKING_DEPOSIT', payment_method='CASH', reference=ref))
        self.assertEqual(r.status_code, 201, r.json)

    # 7. Password change revokes every earlier JWT.
    def test_password_change_revokes_tokens_on_every_device(self):
        phone = {'Authorization': 'Bearer ' + self.login('u1@example.test').json['data']['access_token']}
        laptop = {'Authorization': 'Bearer ' + self.login('u1@example.test').json['data']['access_token']}
        self.assertEqual(self.client.get('/api/v1/users/me', headers=phone).status_code, 200)
        r = self.client.post('/api/v1/users/me/password', headers=laptop, json=dict(
            current_password='Password123!', new_password='NewPassword456!', confirm_password='NewPassword456!'))
        self.assertEqual(r.status_code, 200, r.json)
        for header in (phone, laptop):
            r = self.client.get('/api/v1/users/me', headers=header)
            self.assertEqual((r.status_code, r.json['error']['code']), (401, 'SESSION_REVOKED'))
        fresh = {'Authorization': 'Bearer ' + self.login('u1@example.test', 'NewPassword456!').json['data']['access_token']}
        self.assertEqual(self.client.get('/api/v1/users/me', headers=fresh).status_code, 200)

    def test_token_without_session_key_is_rejected(self):
        now = utcnow()
        token = jwt.encode(dict(sub=str(self.ua), role='PLAYER', iat=now, exp=now + timedelta(hours=1),
                                iss='football-field-api', aud='football-field-web'), SECRET, algorithm='HS256')
        self.assertEqual(self.client.get('/api/v1/users/me', headers={'Authorization': 'Bearer ' + token}).status_code, 401)

    # 5. Public post detail hides attendance and non-listed posts.
    def test_post_detail_shows_private_fields_only_to_insiders(self):
        pid = self.post(self.a)
        public = self.client.get(f'/api/v1/match-posts/{pid}').json['data']
        self.assertNotIn('attendance_user_ids', public)
        self.assertIn('description', public)
        self.assertNotIn('attendance_user_ids', self.client.get(f'/api/v1/match-posts/{pid}', headers=self.c).json['data'])
        self.assertIn('attendance_user_ids', self.client.get(f'/api/v1/match-posts/{pid}', headers=self.a).json['data'])
        self.assertIn('attendance_user_ids', self.client.get(f'/api/v1/match-posts/{pid}', headers=self.admin).json['data'])
        with UnitOfWork() as ctx:
            ctx.session.get(MatchPost, pid).status = 'CANCELLED'
        self.assertEqual(self.client.get(f'/api/v1/match-posts/{pid}').status_code, 404)
        self.assertEqual(self.client.get(f'/api/v1/match-posts/{pid}', headers=self.c).status_code, 404)
        self.assertEqual(self.client.get(f'/api/v1/match-posts/{pid}', headers=self.a).status_code, 200)
        # A broken token is treated as anonymous, not as an error, on this public endpoint.
        self.assertEqual(self.client.get(f'/api/v1/match-posts/{pid}', headers={'Authorization': 'Bearer junk'}).status_code, 404)

    # 8. Mistyped status filters are rejected.
    def test_unknown_status_filters_are_422(self):
        for path in ('/api/v1/match-posts/my', '/api/v1/match-proposals', '/api/v1/matches'):
            r = self.client.get(path, headers=self.a, query_string={'status': 'BOGUS'})
            self.assertEqual(r.status_code, 422, path)
        self.assertEqual(self.client.get('/api/v1/matches', headers=self.a, query_string={'status': 'COMPLETED'}).status_code, 200)

    # 3. Finished matches complete and stop reserving players.
    def test_finished_match_becomes_completed(self):
        bid, mid = self.match_booking()
        self.record(bid, self.ua, '60000.00', 'A')
        self.record(bid, self.ub, '60000.00', 'B')
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.get(Match, mid).status, 'CONFIRMED')
        self.assertEqual(complete_finished_matches(), 0)
        self.go_after(self.booking(bid).end_time)
        self.assertEqual(complete_finished_matches(), 1)
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.get(Match, mid).status, 'COMPLETED')
        self.assertEqual(complete_finished_matches(), 0)

    # 4. Scheduler runs every job and survives one failing.
    def test_scheduler_runs_every_job_once(self):
        result = run_once()
        self.assertEqual(set(result), {'expire_proposals', 'expire_holds', 'reconcile_payments', 'process_refunds', 'complete_matches'})
        self.assertFalse(any(str(v).startswith('ERROR') for v in result.values()), result)
        self.assertIn('matchmaking', run_once(with_matchmaking=True))

    # 9. Booking lists cost the same number of queries for 1 or 4 bookings.
    def count_queries(self, path, header):
        statements = []
        listener = lambda *args: statements.append(1)
        event.listen(db.engine, 'before_cursor_execute', listener)
        try:
            r = self.client.get(path, headers=header)
        finally:
            event.remove(db.engine, 'before_cursor_execute', listener)
        self.assertEqual(r.status_code, 200, r.json)
        return len(statements)

    def test_booking_lists_do_not_query_per_row(self):
        self.hold(index=0)
        one_admin, one_mine = self.count_queries('/api/v1/admin/bookings', self.admin), self.count_queries('/api/v1/bookings/my', self.a)
        for index in (1, 2, 3):
            self.hold(index=index)
        self.assertEqual(self.count_queries('/api/v1/admin/bookings', self.admin), one_admin)
        self.assertEqual(self.count_queries('/api/v1/bookings/my', self.a), one_mine)

    # 1. Refunds owed for manual money are listed and can be completed by the Admin.
    def test_pending_refund_queue_and_admin_completes_it(self):
        bid = self.hold()['booking_id']
        self.record(bid, self.ua, '120000.00', 'CASH-1')
        self.assertEqual(self.booking(bid).status, 'CONFIRMED')
        r = self.client.post(f'/api/v1/admin/bookings/{bid}/cancel', headers=self.admin, json={'reason': 'Sân hỏng'})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(self.client.get('/api/v1/admin/refunds/pending', headers=self.a).status_code, 403)
        [item] = self.client.get('/api/v1/admin/refunds/pending', headers=self.admin).json['data']
        self.assertTrue(item['manual'])
        self.assertEqual((item['amount'], item['payer']['email']), ('120000.00', 'u1@example.test'))
        original = item['original']['payment_id']
        r = self.client.post(f'/api/v1/admin/payments/{original}/refund', headers=self.admin, json={'reason': 'Đã trả tiền mặt'})
        self.assertEqual((r.status_code, r.json['data']['status']), (200, 'SUCCESS'))
        self.assertEqual(self.client.get('/api/v1/admin/refunds/pending', headers=self.admin).json['data'], [])
