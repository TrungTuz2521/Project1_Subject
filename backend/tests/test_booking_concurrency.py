"""Row-lock races. SQLite cannot prove these, so they need a real server through TEST_DATABASE_URL.

These tests CREATE and DROP every table, so the URL must be a throwaway local database: the host must
be local and the database name must end in _test. The shared TiDB database can never qualify.
"""
import os
import threading
import unittest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from booking_fixtures import BookingCase
from app.extensions import db
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Booking, Match, Notification, Payment
from app.use_cases.expire_hold import expire_booking_hold

def _usable_url():
    raw = os.getenv('TEST_DATABASE_URL')
    if not raw:
        return None
    url = make_url(raw)
    return raw if url.host in ('127.0.0.1', 'localhost', '::1') and (url.database or '').endswith('_test') else None

URL = _usable_url()

@unittest.skipUnless(URL, 'Set TEST_DATABASE_URL to a throwaway local database named *_test')
class Races(BookingCase):
    URI = URL or 'sqlite://'
    EXTRA_CONFIG = {'TESTING': False, 'SQLALCHEMY_ENGINE_OPTIONS': {
        'isolation_level': 'READ COMMITTED', 'pool_size': 20, 'connect_args': {'init_command': "SET time_zone = '+00:00'"}}}

    def setUp(self):
        super().setUp()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        super().tearDown()

    def race(self, *calls):
        """Run calls at the same instant. Any unexpected exception fails the test instead of vanishing."""
        barrier = threading.Barrier(len(calls))
        results, errors = [None] * len(calls), []
        def run(index, call):
            with self.app.app_context():
                barrier.wait()
                try:
                    results[index] = call()
                except Exception as error:
                    errors.append(error)
        threads = [threading.Thread(target=run, args=(i, c)) for i, c in enumerate(calls)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertEqual(errors, [])
        return results

    def post_hold(self, header, index=8, pitch_id=1):
        start, end = self.slot(index=index)
        client = self.app.test_client()
        return lambda: client.post('/api/v1/bookings', headers=header, json=dict(pitch_id=pitch_id, start_time=start.isoformat(), end_time=end.isoformat())).status_code

    def count(self, model, *where):
        with UnitOfWork() as ctx:
            return ctx.session.scalar(select(func.count()).select_from(model).where(*where))

    def test_many_requests_for_an_empty_slot_produce_one_hold(self):
        headers = [self.a, self.b, self.c] * 4
        codes = self.race(*[self.post_hold(h) for h in headers])
        self.assertEqual(sorted(codes), [201] + [409] * 11)
        self.assertEqual(self.count(Booking), 1)

    def test_touching_slots_are_both_allowed_under_race(self):
        codes = self.race(self.post_hold(self.a, 3), self.post_hold(self.b, 4))
        self.assertEqual(codes, [201, 201])

    def test_two_deposit_requests_create_one_session(self):
        data = self.hold()
        clients = [self.app.test_client() for _ in range(4)]
        body = {'booking_id': data['booking_id'], 'payment_method': 'VNPAY'}
        codes = self.race(*[lambda c=c: c.post('/api/v1/payments/deposit', headers=self.a, json=body).status_code for c in clients])
        self.assertEqual(sorted(codes), [200, 200, 200, 201])
        self.assertEqual(len(self.payments(data['booking_id'])), 1)

    def test_repeated_callbacks_apply_once(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        outcomes = self.race(*[lambda: self.callback(session).outcome for _ in range(4)])
        self.assertEqual(sorted(outcomes), ['DUPLICATE', 'DUPLICATE', 'DUPLICATE', 'OK'])
        self.assertEqual(self.count(Notification, Notification.notification_type == 'PAYMENT_SUCCESS'), 1)
        self.assertEqual(self.booking(data['booking_id']).status, 'CONFIRMED')

    def test_callback_before_deadline_beats_the_worker(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.race(lambda: self.callback(session), lambda: expire_booking_hold(data['booking_id']))
        self.assertEqual(self.booking(data['booking_id']).status, 'CONFIRMED')
        self.assertEqual(len(self.payments(data['booking_id'])), 1)

    def test_callback_racing_timeout_never_revives_and_refunds_once(self):
        for index in range(5):
            data = self.hold(index=index)
            session = self.open_deposit(data['booking_id'])
            self.advance(seconds=300)
            self.race(lambda: self.callback(session), lambda: expire_booking_hold(data['booking_id']))
            self.assertEqual(self.booking(data['booking_id']).status, 'EXPIRED')
            self.assertEqual(sorted(p.payment_type for p in self.payments(data['booking_id'])), ['BOOKING_DEPOSIT', 'REFUND'])

    def test_callback_racing_cancel_keeps_money_consistent(self):
        for index in range(5):
            data = self.hold(index=index)
            session = self.open_deposit(data['booking_id'])
            client = self.app.test_client()
            cancel = lambda: client.post(f"/api/v1/bookings/{data['booking_id']}/cancel", headers=self.a, json={'reason': 'Bận'}).status_code
            self.race(lambda: self.callback(session), cancel)
            booking, rows = self.booking(data['booking_id']), self.payments(data['booking_id'])
            self.assertEqual(booking.status, 'CANCELLED')
            original = rows[0]
            self.assertEqual(original.status, 'SUCCESS')
            refunds = [p for p in rows if p.payment_type == 'REFUND']
            # Callback first: the user cancelled a paid deposit and forfeits it. Cancel first: late money is refunded.
            if refunds:
                self.assertEqual(len(refunds), 1)
            else:
                self.assertIn('MAT_COC', original.note)

    def test_two_admin_cancels_create_one_refund(self):
        data = self.confirmed()
        clients = [self.app.test_client() for _ in range(3)]
        url = f"/api/v1/admin/bookings/{data['booking_id']}/cancel"
        codes = self.race(*[lambda c=c: c.post(url, headers=self.admin, json={'reason': 'Sự cố'}).status_code for c in clients])
        self.assertEqual(codes, [200, 200, 200])
        self.assertEqual(self.count(Payment, Payment.payment_type == 'REFUND'), 1)

    def confirm_call(self, booking_id, key):
        client = self.app.test_client()
        body = dict(expected_outstanding='480000', idempotency_key=key, receipts=[{'payment_method': 'CASH', 'amount': '480000'}])
        return lambda: client.post(f'/api/v1/admin/bookings/{booking_id}/confirm-paid', headers=self.admin, json=body).status_code

    def test_two_admin_tabs_collect_once(self):
        data = self.confirmed()
        self.go_after(self.booking(data['booking_id']).end_time)
        codes = self.race(self.confirm_call(data['booking_id'], 'tab-one-1'), self.confirm_call(data['booking_id'], 'tab-two-2'))
        self.assertEqual(sorted(codes), [200, 409])
        self.assertEqual(self.count(Payment, Payment.payment_type == 'BOOKING_REMAINING_PAYMENT'), 1)

    def test_same_confirmation_key_collects_once(self):
        data = self.confirmed()
        self.go_after(self.booking(data['booking_id']).end_time)
        codes = self.race(*[self.confirm_call(data['booking_id'], 'same-key-1') for _ in range(3)])
        self.assertEqual(codes, [200, 200, 200])
        self.assertEqual(self.count(Payment, Payment.payment_type == 'BOOKING_REMAINING_PAYMENT'), 1)

    def test_two_scans_racing_create_one_match_and_one_hold(self):
        from unittest import mock
        from app.services.match_request_service import scan
        self.request_opponent(self.a)
        # Second request without its immediate scan, so two scheduler passes can race for the pair.
        with mock.patch('app.services.match_request_service.scan', return_value={}):
            self.request_opponent(self.b)
        self.race(lambda: scan(), lambda: scan())
        self.assertEqual(self.count(Match), 1)
        self.assertEqual(self.count(Booking), 1)

    def test_both_deposits_racing_confirm_the_match_once(self):
        booking_id, match_id = self.match_booking()
        first, second = self.open_deposit(booking_id, self.a), self.open_deposit(booking_id, self.b)
        self.race(lambda: self.callback(first), lambda: self.callback(second))
        self.assertEqual(self.booking(booking_id).status, 'CONFIRMED')
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.get(Match, match_id).status, 'CONFIRMED')
        self.assertEqual(self.count(Notification, Notification.notification_type == 'MATCH_CONFIRMED'), 2)

    def test_maintenance_lock_racing_a_customer_leaves_one_winner(self):
        start, end = self.slot()
        client = self.app.test_client()
        lock = lambda: client.post('/api/v1/admin/maintenance-locks', headers=self.admin, json=dict(pitch_id=1, start_time=start.isoformat(), end_time=end.isoformat(), reason='Sửa')).status_code
        codes = self.race(lock, self.post_hold(self.a))
        self.assertEqual(sorted(codes), [201, 409])

    def test_schema_columns_and_utc_round_trip(self):
        data = self.hold()
        booking = self.booking(data['booking_id'])
        self.assertEqual(booking.start_time, self.slot()[0])
        self.assertEqual(booking.payer_plan, [{'user_id': self.ua, 'amount': '120000.00'}])
