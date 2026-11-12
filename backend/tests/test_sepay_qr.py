from datetime import timedelta
from sqlalchemy import select
from booking_fixtures import BookingCase
from app.infrastructure.unit_of_work import UnitOfWork
from app.jobs.booking_jobs import reconcile_payments
from app.models import Match, Notification
from app.services.booking_balance_service import crc16

KEY = 'sepay-test-key'


class SepayQrTests(BookingCase):
    def setUp(self):
        super().setUp()
        self.app.config.update(BANK_NAME='Test Bank', BANK_ACCOUNT_NAME='TEST RECEIVER', SEPAY_WEBHOOK_KEY=KEY,
                               SEPAY_QR_TTL_SECONDS=60, SEPAY_CONFIRM_GRACE_SECONDS=120, EMAIL_ENABLED=True)

    def open_qr(self, bid, header=None):
        return self.client.post('/api/v1/payments/deposit/qr', headers=header or self.a, json={'booking_id': bid})

    def webhook(self, code, amount, *, key=KEY, sepay_id=1, account=None, transfer_type='in', content=None):
        payload = dict(id=sepay_id, gateway='MBBank', transactionDate='2026-11-11 10:00:00',
                       accountNumber=account or self.app.config['BANK_ACCOUNT_NO'], code=None,
                       content=content if content is not None else f'MBVCB.123 {code} chuyen tien', transferType=transfer_type,
                       transferAmount=amount, referenceCode='FT26315', description='')
        return self.client.post('/api/v1/payments/sepay/webhook', json=payload, headers={'Authorization': f'Apikey {key}'})

    def emails(self, uid):
        with UnitOfWork() as ctx:
            return list(ctx.session.scalars(select(Notification).where(
                Notification.user_id == uid, Notification.delivery_channel == 'EMAIL').order_by(Notification.notification_id)))

    def test_qr_prefills_bank_amount_and_code_and_lasts_sixty_seconds(self):
        bid = self.hold()['booking_id']
        r = self.open_qr(bid)
        self.assertEqual(r.status_code, 201, r.json)
        data = r.json['data']
        code, payload = data['transfer_reference'], data['qr_payload']
        self.assertRegex(code, r'^SP[0-9A-F]{10}$')
        self.assertEqual(data['amount'], '120000.00')
        self.assertTrue(payload.endswith(crc16(payload[:-4])))
        for part in (self.app.config['BANK_ACCOUNT_NO'], '5406120000', code):
            self.assertIn(part, payload)
        self.assertEqual(data['qr_expires_at'], (self.now + timedelta(seconds=60)).isoformat().replace('+00:00', 'Z'))
        [payment] = self.payments(bid)
        self.assertEqual((payment.status, payment.payment_method, payment.transaction_code), ('PENDING', 'BANK_TRANSFER', code))
        # Same code while it is still shown; a new code only after 60 seconds.
        self.advance(seconds=59)
        self.assertEqual(self.open_qr(bid).json['data']['transfer_reference'], code)
        self.advance(seconds=1)
        again = self.open_qr(bid)
        self.assertEqual(again.status_code, 201)
        self.assertNotEqual(again.json['data']['transfer_reference'], code)
        self.assertEqual([p.status for p in self.payments(bid)], ['FAILED', 'PENDING'])

    def test_instructions_show_live_session_and_no_static_qr(self):
        bid = self.hold()['booking_id']
        data = self.client.get(f'/api/v1/bookings/{bid}/deposit-instructions', headers=self.a).json['data']
        self.assertTrue(data['qr_auto_confirm'])
        self.assertEqual(data['qr_ttl_seconds'], 60)
        self.assertIsNone(data['payers'][0]['qr_payload'])
        self.assertTrue(data['payers'][0]['can_open_qr'])
        code = self.open_qr(bid).json['data']['transfer_reference']
        payer = self.client.get(f'/api/v1/bookings/{bid}/deposit-instructions', headers=self.a).json['data']['payers'][0]
        self.assertEqual(payer['qr_session']['transfer_reference'], code)
        self.advance(seconds=60)
        payer = self.client.get(f'/api/v1/bookings/{bid}/deposit-instructions', headers=self.a).json['data']['payers'][0]
        self.assertIsNone(payer['qr_session'])
        self.assertTrue(payer['can_open_qr'])

    def test_hold_covers_the_code_window_once_and_never_grows_without_limit(self):
        bid = self.hold()['booking_id']
        original = self.booking(bid).hold_expires_at
        self.advance(seconds=290)
        self.open_qr(bid)  # 10 s left: the hold now covers the 60 s code plus 120 s for the bank to report.
        self.assertEqual(self.booking(bid).hold_expires_at, self.now + timedelta(seconds=180))
        for _ in range(3):  # Asking for new codes again and again never holds the slot past one extra window.
            self.advance(seconds=61)
            if self.open_qr(bid).status_code >= 400:
                break
        self.assertLessEqual(self.booking(bid).hold_expires_at, original + timedelta(seconds=181))

    def test_webhook_confirms_booking_and_queues_paid_email(self):
        bid = self.hold()['booking_id']
        code = self.open_qr(bid).json['data']['transfer_reference']
        r = self.webhook(code, 120000)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json, {'success': True, 'outcome': 'OK'})
        [payment] = self.payments(bid)
        self.assertEqual(payment.status, 'SUCCESS')
        self.assertIn('gw=sepay:1', payment.note)
        self.assertEqual(self.booking(bid).status, 'CONFIRMED')
        types = [(n.notification_type, n.delivery_status) for n in self.emails(self.ua)]
        self.assertIn(('PAYMENT_SUCCESS', 'PENDING'), types)
        self.assertIn(('BOOKING_CONFIRMED', 'PENDING'), types)
        mail = next(n for n in self.emails(self.ua) if n.notification_type == 'PAYMENT_SUCCESS')
        self.assertIn('120.000 ₫', mail.content)
        self.assertIn(f'#{bid}', mail.content)
        # SePay retries the same notification: nothing changes, no second email.
        self.assertEqual(self.webhook(code, 120000).json['outcome'], 'DUPLICATE')
        self.assertEqual(len(self.emails(self.ua)), len(types))

    def test_code_glued_to_lowercase_bank_text_is_found(self):
        bid = self.hold()['booking_id']
        code = self.open_qr(bid).json['data']['transfer_reference']
        self.assertEqual(self.webhook(code, 120000, content=f'ib{code.lower()}ft26315xyz').json['outcome'], 'OK')

    def test_wrong_key_account_direction_or_amount_never_confirms(self):
        bid = self.hold()['booking_id']
        code = self.open_qr(bid).json['data']['transfer_reference']
        self.assertEqual(self.webhook(code, 120000, key='wrong').status_code, 401)
        self.assertEqual(self.webhook(code, 120000, account='999999').json['outcome'], 'OTHER_ACCOUNT')
        self.assertEqual(self.webhook(code, 120000, transfer_type='out').json['outcome'], 'NOT_INCOMING')
        self.assertEqual(self.webhook('SPFFFFFFFFFF', 120000).json['outcome'], 'NO_REFERENCE')
        [payment] = self.payments(bid)
        self.assertEqual(payment.status, 'PENDING')
        self.assertEqual(self.booking(bid).status, 'PENDING_HOLD')

    # ---- whatever amount really arrives is recorded

    def notices(self, uid, kind):
        with UnitOfWork() as ctx:
            return [n.content for n in ctx.session.scalars(select(Notification).where(
                Notification.user_id == uid, Notification.notification_type == kind, Notification.delivery_channel == 'IN_APP'))]

    def refunds(self, bid):
        return [p for p in self.payments(bid) if p.payment_type == 'REFUND']

    def test_short_transfer_is_a_partial_deposit_and_a_new_code_asks_for_the_rest(self):
        bid = self.hold()['booking_id']
        code = self.open_qr(bid).json['data']['transfer_reference']
        self.assertEqual(self.webhook(code, 100000).json['outcome'], 'OK')
        [payment] = self.payments(bid)
        self.assertEqual((payment.status, str(payment.amount)), ('SUCCESS', '100000.00'))
        self.assertEqual(self.booking(bid).status, 'PENDING_HOLD')
        self.assertTrue(any('còn thiếu 20.000 ₫' in n for n in self.notices(self.ua, 'PAYMENT_SUCCESS')))
        rest = self.open_qr(bid).json['data']
        self.assertEqual(rest['amount'], '20000.00')
        self.assertEqual(self.webhook(rest['transfer_reference'], 20000, sepay_id=2).json['outcome'], 'OK')
        self.assertEqual(self.booking(bid).status, 'CONFIRMED')

    def test_short_transfer_never_completed_is_refunded_when_the_hold_ends(self):
        from app.jobs.booking_jobs import expire_holds
        bid = self.hold()['booking_id']
        self.webhook(self.open_qr(bid).json['data']['transfer_reference'], 50000)
        self.advance(seconds=600)
        self.assertEqual(expire_holds(), 1)
        [refund] = self.refunds(bid)
        self.assertEqual((refund.status, str(refund.amount)), ('REFUND_PROCESSING', '50000.00'))

    def test_extra_money_pays_the_pitch_fee_and_only_the_part_above_it_is_refunded(self):
        bid = self.hold()['booking_id']  # pitch fee 600.000, deposit 120.000
        code = self.open_qr(bid).json['data']['transfer_reference']
        self.assertEqual(self.webhook(code, 700000).json['outcome'], 'OK')
        self.assertEqual(self.booking(bid).status, 'CONFIRMED')
        kinds = sorted((p.payment_type, str(p.amount), p.status) for p in self.payments(bid))
        self.assertEqual(kinds, [('BOOKING_DEPOSIT', '120000.00', 'SUCCESS'), ('BOOKING_REMAINING_PAYMENT', '100000.00', 'SUCCESS'),
                                 ('BOOKING_REMAINING_PAYMENT', '480000.00', 'SUCCESS'), ('REFUND', '100000.00', 'REFUND_PROCESSING')])
        data = self.client.get(f'/api/v1/bookings/{bid}', headers=self.a).json['data']
        self.assertEqual(data['outstanding_amount'], '0.00')
        self.assertTrue(any('Hồ sơ' in n for n in self.notices(self.ua, 'REFUND_PROCESSING')))

    def test_second_transfer_for_a_paid_code_goes_towards_the_pitch_fee(self):
        bid = self.hold()['booking_id']
        code = self.open_qr(bid).json['data']['transfer_reference']
        self.webhook(code, 120000, sepay_id=1)
        self.assertEqual(self.webhook(code, 120000, sepay_id=2).json['outcome'], 'EXTRA_RECORDED')
        # SePay retries both notifications: nothing is recorded twice.
        self.assertEqual(self.webhook(code, 120000, sepay_id=2).json['outcome'], 'DUPLICATE')
        self.assertEqual(self.webhook(code, 120000, sepay_id=1).json['outcome'], 'DUPLICATE')
        self.assertEqual(len(self.payments(bid)), 2)
        self.assertEqual(self.refunds(bid), [])
        data = self.client.get(f'/api/v1/bookings/{bid}', headers=self.a).json['data']
        self.assertEqual((data['paid_amount'], data['outstanding_amount']), ('240000.00', '360000.00'))

    def test_money_for_a_booking_that_is_no_longer_held_is_refunded_in_full(self):
        bid = self.hold()['booking_id']
        code = self.open_qr(bid).json['data']['transfer_reference']
        self.webhook(code, 120000, sepay_id=1)
        self.client.post(f'/api/v1/bookings/{bid}/cancel', headers=self.a, json={'reason': 'Ban viec'})
        self.assertEqual(self.webhook(code, 120000, sepay_id=2).json['outcome'], 'EXTRA_RECORDED')
        [refund] = self.refunds(bid)
        self.assertEqual(str(refund.amount), '120000.00')  # the forfeited deposit stays, the second transfer goes back

    def test_refund_account_is_shown_to_the_customer_and_the_admin(self):
        r = self.client.patch('/api/v1/users/me', headers=self.a, json={'refund_bank_name': 'MB', 'refund_account_no': '12 3456 789',
                                                                        'refund_account_name': 'Nguyen Van A'})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual((r.json['data']['refund_account_no'], r.json['data']['refund_account_name']), ('123456789', 'NGUYEN VAN A'))
        bad = self.client.patch('/api/v1/users/me', headers=self.a, json={'refund_bank_name': 'MB', 'refund_account_no': 'abc12',
                                                                          'refund_account_name': 'A B'})
        self.assertEqual(list(bad.json['error']['fields']), ['refund_account_no'])
        bid = self.hold()['booking_id']
        self.webhook(self.open_qr(bid).json['data']['transfer_reference'], 700000)
        self.assertTrue(any('MB 123456789 (NGUYEN VAN A)' in n for n in self.notices(self.ua, 'REFUND_PROCESSING')))
        rows = self.client.get('/api/v1/admin/refunds/pending', headers=self.admin).json['data']
        self.assertEqual(rows[0]['payer']['refund_account'], {'bank_name': 'MB', 'account_no': '123456789', 'account_name': 'NGUYEN VAN A'})
        cleared = self.client.patch('/api/v1/users/me', headers=self.a, json={'refund_bank_name': '', 'refund_account_no': '', 'refund_account_name': ''})
        self.assertIsNone(cleared.json['data']['refund_account_no'])

    def test_demo_confirmation_is_off_next_to_real_payments_and_behind_a_proxy(self):
        self.app.config['DEMO_PAYMENT_ENABLED'] = True
        bid = self.hold()['booking_id']
        r = self.client.post('/api/v1/payments/deposit/demo-confirm', headers=self.a, json={'booking_id': bid})
        self.assertEqual(r.status_code, 403)
        self.app.config['SEPAY_WEBHOOK_KEY'] = ''
        tunnelled = dict(self.a, **{'CF-Connecting-IP': '203.0.113.9'})
        self.assertEqual(self.client.post('/api/v1/payments/deposit/demo-confirm', headers=tunnelled, json={'booking_id': bid}).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/payments/deposit/demo-confirm', headers=self.a, json={'booking_id': bid}).status_code, 200)

    def test_money_for_an_expired_code_inside_the_grace_still_confirms(self):
        bid = self.hold()['booking_id']
        code = self.open_qr(bid).json['data']['transfer_reference']
        self.advance(seconds=90)
        self.assertEqual(reconcile_payments()['expired_qr_sessions'], 0)
        self.assertEqual(self.webhook(code, 120000).json['outcome'], 'OK')
        self.assertEqual(self.booking(bid).status, 'CONFIRMED')

    def test_worker_expires_unpaid_code_after_grace(self):
        bid = self.hold()['booking_id']
        self.open_qr(bid)
        self.advance(seconds=181)
        self.assertEqual(reconcile_payments()['expired_qr_sessions'], 1)
        self.assertEqual(self.payments(bid)[0].status, 'FAILED')

    def test_two_teams_each_scan_their_own_share(self):
        bid, mid = self.match_booking()
        a = self.open_qr(bid, self.a).json['data']
        b = self.open_qr(bid, self.b).json['data']
        self.assertEqual((a['amount'], b['amount']), ('60000.00', '60000.00'))
        self.webhook(a['transfer_reference'], 60000, sepay_id=1)
        self.assertEqual(self.booking(bid).status, 'PENDING_HOLD')
        self.webhook(b['transfer_reference'], 60000, sepay_id=2)
        self.assertEqual(self.booking(bid).status, 'CONFIRMED')
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.get(Match, mid).status, 'CONFIRMED')

    def test_disabled_without_key_and_expired_hold_rejected(self):
        bid = self.hold()['booking_id']
        self.app.config['SEPAY_WEBHOOK_KEY'] = ''
        self.assertEqual(self.open_qr(bid).status_code, 503)
        self.assertEqual(self.webhook('SP0000000000', 1).status_code, 503)
        self.app.config['SEPAY_WEBHOOK_KEY'] = KEY
        self.advance(seconds=300)
        self.assertEqual(self.open_qr(bid).json['error']['code'], 'HOLD_EXPIRED')
        self.assertEqual(self.open_qr(bid, self.b).status_code, 404)
