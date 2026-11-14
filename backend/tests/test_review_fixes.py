"""Business-rule fixes from the backend review: matched-game cancel cut-off, one phone format, password reset,
counter rescheduling far ahead, nothing owed on a closed booking, and the pitch-fee QR recorded by SePay."""
from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlsplit
from sqlalchemy import select
from booking_fixtures import BookingCase
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Payment, User

KEY = 'sepay-test-key'


class ReviewFixTests(BookingCase):
    # ---- 5. a matched game follows the 24-hour rule wherever it is cancelled

    def test_matched_booking_cannot_be_cancelled_from_my_bookings_within_a_day(self):
        booking_id = self.confirmed(self.a, days=3)['booking_id']
        self.request_opponent(self.a, booking_id=booking_id)
        self.request_opponent(self.c, days=3)
        self.assertEqual(self.latest_match().status, 'CONFIRMED')
        own = self.confirmed(self.b, days=3, pitch_id=2)['booking_id']
        self.go_after(self.booking(booking_id).start_time - timedelta(hours=23))
        r = self.client.post(f'/api/v1/bookings/{booking_id}/cancel', headers=self.a, json={'reason': 'Ban viec'})
        self.assertEqual((r.status_code, r.json['error']['code']), (409, 'TOO_LATE'))
        self.assertEqual(self.booking(booking_id).status, 'CONFIRMED')
        # A booking that is not a matched game keeps the usual rule.
        self.assertEqual(self.client.post(f'/api/v1/bookings/{own}/cancel', headers=self.b, json={'reason': 'Ban viec'}).status_code, 200)

    # ---- 7. one phone format

    def register(self, email, phone):
        return self.client.post('/api/v1/auth/register', json={'full_name': 'Nguyen Van Phone', 'email': email,
                                                                'password': 'Password123!', 'phone': phone})

    def test_phone_is_stored_in_one_format_and_found_however_it_is_typed(self):
        r = self.register('p1@example.test', '0912 345.678')
        self.assertEqual((r.status_code, r.json['data']['phone']), (201, '0912345678'))
        self.assertEqual(self.register('p2@example.test', '0912-345-678').json['error']['code'], 'PHONE_EXISTS')
        self.assertEqual(list(self.register('p3@example.test', 'abc').json['error']['fields']), ['phone'])
        self.assertEqual(self.register('p4@example.test', '  ').status_code, 201)  # empty = no phone
        r = self.client.patch('/api/v1/users/me', headers=self.a, json={'phone': '0987 654 321'})
        self.assertEqual(r.json['data']['phone'], '0987654321')
        found = self.client.get('/api/v1/admin/users', headers=self.admin, query_string={'q': '0912 345'}).json['data']
        self.assertEqual([u['email'] for u in found], ['p1@example.test'])

    # ---- 8. forgotten password

    def forgot(self, email):
        sent = []
        with mock.patch('app.services.email_service.send_password_reset', side_effect=lambda *args: sent.append(args)):
            r = self.client.post('/api/v1/auth/password/forgot', json={'email': email})
        self.assertEqual(r.status_code, 200)
        return r.json['data'], sent

    def test_password_reset_link_works_once_and_signs_out_other_sessions(self):
        self.app.config['EMAIL_ENABLED'] = True
        unknown, none_sent = self.forgot('nobody@example.test')
        known, sent = self.forgot('U1@example.test')
        self.assertEqual(unknown, known)  # the answer never reveals whether an account exists
        self.assertEqual(none_sent, [])
        [(recipient, _, link, minutes)] = sent
        self.assertEqual((recipient, minutes), ('u1@example.test', 30))
        token = parse_qs(urlsplit(link.replace('#/', '')).query)['token'][0]
        bad = self.client.post('/api/v1/auth/password/reset', json={'token': token, 'new_password': 'NewPass123!', 'confirm_password': 'Other123!'})
        self.assertEqual(list(bad.json['error']['fields']), ['confirm_password'])
        r = self.client.post('/api/v1/auth/password/reset', json={'token': token, 'new_password': 'NewPass123!', 'confirm_password': 'NewPass123!'})
        self.assertEqual(r.status_code, 200, r.json)
        login = self.client.post('/api/v1/auth/login', json={'email': 'u1@example.test', 'password': 'NewPass123!'})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.get('/api/v1/users/me', headers=self.a).status_code, 401)  # old session revoked
        again = self.client.post('/api/v1/auth/password/reset', json={'token': token, 'new_password': 'Again123!!', 'confirm_password': 'Again123!!'})
        self.assertEqual(again.json['error']['code'], 'RESET_LINK_INVALID')

    def test_reset_link_expires_and_walk_in_profiles_get_no_email(self):
        self.app.config['EMAIL_ENABLED'] = True
        _, sent = self.forgot('u1@example.test')
        token = parse_qs(urlsplit(sent[0][2].replace('#/', '')).query)['token'][0]
        self.advance(minutes=31)
        r = self.client.post('/api/v1/auth/password/reset', json={'token': token, 'new_password': 'NewPass123!', 'confirm_password': 'NewPass123!'})
        self.assertEqual(r.json['error']['code'], 'RESET_LINK_INVALID')
        with UnitOfWork() as ctx:
            ctx.session.add(User(full_name='Khach quay', email='walkin-abc@walkin.invalid', phone='0911000111'))
        self.assertEqual(self.forgot('walkin-abc@walkin.invalid')[1], [])

    # ---- 9. the counter moves a regular's session booked weeks ahead

    def test_admin_reschedules_a_session_more_than_ten_days_ahead(self):
        start, end = self.slot(30, 8)
        created = self.client.post('/api/v1/admin/bookings', headers=self.admin, json=dict(
            pitch_id=1, start_time=start.isoformat(), end_time=end.isoformat(), user_id=self.ua, note='Khach co dinh'))
        self.assertEqual(created.status_code, 201, created.json)
        start, end = self.slot(31, 8)
        r = self.client.patch(f"/api/v1/admin/bookings/{created.json['data']['booking_id']}", headers=self.admin,
                              json=dict(start_time=start.isoformat(), end_time=end.isoformat(), reason='Khach doi ngay'))
        self.assertEqual(r.status_code, 200, r.json)

    # ---- 10. a closed booking owes nothing

    def test_cancelled_or_expired_booking_owes_nothing(self):
        held = self.hold()['booking_id']
        self.assertEqual(self.client.get(f'/api/v1/bookings/{held}', headers=self.a).json['data']['outstanding_amount'], '600000.00')
        self.client.post(f'/api/v1/bookings/{held}/cancel', headers=self.a, json={'reason': 'Doi y'})
        self.assertEqual(self.client.get(f'/api/v1/bookings/{held}', headers=self.a).json['data']['outstanding_amount'], '0.00')


class PitchFeeQrTests(BookingCase):
    """11. The balance QR shown at the counter is recorded by the SePay webhook, no Admin typing."""

    def setUp(self):
        super().setUp()
        self.app.config.update(BANK_NAME='Test Bank', BANK_ACCOUNT_NAME='TEST RECEIVER', SEPAY_WEBHOOK_KEY=KEY)

    def webhook(self, content, amount, sepay_id=7):
        payload = dict(id=sepay_id, gateway='MBBank', transactionDate='2026-11-11 10:00:00', accountNumber=self.app.config['BANK_ACCOUNT_NO'],
                       code=None, content=content, transferType='in', transferAmount=amount, referenceCode='FT1', description='')
        return self.client.post('/api/v1/payments/sepay/webhook', json=payload, headers={'Authorization': f'Apikey {KEY}'}).json['outcome']

    def balance(self, bid):
        return self.client.get(f'/api/v1/admin/bookings/{bid}/balance', headers=self.admin).json['data']

    def test_pitch_fee_transfer_is_recorded_once_even_with_digits_glued_after_it(self):
        bid = self.confirmed()['booking_id']  # 600.000, deposit 120.000 paid
        reference = self.balance(bid)['transfer_reference']
        self.assertEqual(reference, f'SAN{bid}TT')
        self.assertEqual(self.webhook(f'MBVCB.1 {reference.lower()}0123456 chuyen', 480000), 'BALANCE_RECORDED')
        self.assertEqual(self.balance(bid)['outstanding_amount'], '0.00')
        self.assertEqual(self.webhook(f'{reference}', 480000), 'DUPLICATE')  # SePay retry
        with UnitOfWork() as ctx:
            rows = list(ctx.session.scalars(select(Payment).where(Payment.booking_id == bid, Payment.payment_type == 'BOOKING_REMAINING_PAYMENT')))
        self.assertEqual([(str(p.amount), p.status) for p in rows], [('480000.00', 'SUCCESS')])

    def test_part_payment_and_overpayment_by_pitch_fee_qr(self):
        bid = self.confirmed()['booking_id']
        reference = f'SAN{bid}TT'
        self.assertEqual(self.webhook(reference, 200000, sepay_id=1), 'BALANCE_RECORDED')
        self.assertEqual(self.balance(bid)['outstanding_amount'], '280000.00')
        self.assertEqual(self.webhook(reference, 300000, sepay_id=2), 'BALANCE_RECORDED')
        self.assertEqual(self.balance(bid)['outstanding_amount'], '0.00')
        with UnitOfWork() as ctx:
            [refund] = ctx.session.scalars(select(Payment).where(Payment.booking_id == bid, Payment.payment_type == 'REFUND')).all()
        self.assertEqual((str(refund.amount), refund.status), ('20000.00', 'REFUND_PROCESSING'))

    def test_unknown_booking_reference_is_not_recorded(self):
        self.assertEqual(self.webhook('SAN999999TT', 100000), 'NO_REFERENCE')


class NotesTeamsAndJobsTests(BookingCase):
    # ---- a long note never loses the markers the code reads back

    def test_note_keeps_markers_when_it_is_full(self):
        from app.services.booking_policy import add_note
        note = 'THU_GOP theo booking; ref=abc'
        note = add_note(note, 'gw=sepay:42')
        for i in range(30):
            note = add_note(note, f'ghi chu cu so {i} rat dai de day cot')
        note = add_note(note, 'MAT_COC do tu huy')
        self.assertLessEqual(len(note), 255)
        self.assertTrue(note.startswith('THU_GOP theo booking'))
        self.assertIn('gw=sepay:42', note)
        self.assertTrue(note.endswith('MAT_COC do tu huy'))

    # ---- the dashboard tells when the scheduler is not running

    def test_dashboard_flags_overdue_background_work(self):
        self.hold()
        jobs = self.client.get('/api/v1/admin/dashboard', headers=self.admin).json['data']['background_jobs']
        self.assertFalse(jobs['lagging'])
        self.advance(minutes=10)  # hold ended 5 minutes ago and nobody expired it
        jobs = self.client.get('/api/v1/admin/dashboard', headers=self.admin).json['data']['background_jobs']
        self.assertEqual((jobs['lagging'], jobs['expired_holds']), (True, 1))
