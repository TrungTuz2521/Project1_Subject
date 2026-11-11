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
        self.assertIn('120.000 VND', mail.content)
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
        r = self.webhook(code, 100000, sepay_id=2)
        self.assertEqual(r.json['outcome'], 'AMOUNT_MISMATCH')
        [payment] = self.payments(bid)
        self.assertEqual(payment.status, 'PENDING')
        self.assertIn('sai so tien', payment.note)
        self.assertEqual(self.booking(bid).status, 'PENDING_HOLD')

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

    def test_second_transfer_for_paid_code_is_flagged_for_refund(self):
        bid = self.hold()['booking_id']
        code = self.open_qr(bid).json['data']['transfer_reference']
        self.webhook(code, 120000, sepay_id=1)
        self.assertEqual(self.webhook(code, 120000, sepay_id=2).json['outcome'], 'DUPLICATE')
        self.assertIn('Nhan them sepay:2', self.payments(bid)[0].note)

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
