import hashlib
import hmac
from app.services.match_requests import MATCH_HOLD_SECONDS
from datetime import timedelta, timezone
from decimal import Decimal
from io import BytesIO
from urllib.parse import parse_qs, urlencode, urlparse
from openpyxl import load_workbook
from sqlalchemy import func, select
from booking_fixtures import BookingCase
from app.contracts.dto import GatewayResult
from app.infrastructure.unit_of_work import UnitOfWork
from app.jobs.booking_jobs import expire_holds, process_refunds, reconcile_payments
from app.jobs.commands import scan_requests
from app.models import Booking, Match, MatchPost, Notification, Payment
from app.services import booking_policy as policy
from app.services.booking_balance_service import bank_qr_payload, crc16
from app.services.gateway.vnpay import VnpayGateway
from app.utils.time import VIETNAM

class MoneyRules(BookingCase):
    def test_deposit_is_ceil_20_percent_and_split_keeps_the_total(self):
        self.assertEqual(policy.deposit_total(Decimal('600000')), Decimal('120000.00'))
        self.assertEqual(policy.deposit_total(Decimal('300001')), Decimal('60001.00'))
        self.assertEqual(policy.split_deposit(Decimal('60001')), (Decimal('30000.00'), Decimal('30001.00')))

    def test_slot_grid_is_90_minutes_from_0600_and_fits_before_2300(self):
        slots = list(policy.day_slots(self.now.astimezone(VIETNAM).date()))
        self.assertEqual(len(slots), 11)
        self.assertEqual((slots[0][0].hour, slots[0][0].minute), (6, 0))
        self.assertEqual((slots[-1][1].hour, slots[-1][1].minute), (22, 30))  # A 12th slot would end at 24:00.

class CatalogueAndAvailability(BookingCase):
    def test_field_complex_policy(self):
        data = self.client.get('/api/v1/field-complex').json['data']
        self.assertEqual(data['policy']['hold_seconds'], 300)
        self.assertEqual(data['policy']['slot_duration_minutes'], 90)
        self.assertEqual(data['policy']['deposit_value'], '20.00')
        self.assertEqual((data['policy']['opening_time'], data['policy']['closing_time']), ('06:00', '23:00'))

    def test_pitch_filters_and_invalid_filters_return_422(self):
        r = self.client.get('/api/v1/pitches?pitch_type=PITCH_7&max_price=500000')
        self.assertEqual([p['pitch_id'] for p in r.json['data']], [4])
        self.assertEqual(r.json['data'][0]['price_per_slot'], '300001.00')
        self.assertEqual(r.json['meta']['total'], 1)
        self.assertEqual(self.client.get('/api/v1/pitches?pitch_type=X').status_code, 422)
        self.assertEqual(self.client.get('/api/v1/pitches?min_price=abc').status_code, 422)
        self.assertEqual(self.client.get('/api/v1/pitches?min_price=9&max_price=1').status_code, 422)
        self.assertEqual(self.client.get('/api/v1/pitches/999').status_code, 404)

    def test_availability_statuses_hide_private_data(self):
        day = self.slot()[0].astimezone(VIETNAM).date().isoformat()
        self.hold(index=0)
        self.confirmed(self.b, index=1)
        start, end = self.slot(index=2)
        self.client.post('/api/v1/admin/maintenance-locks', headers=self.admin, json=dict(pitch_id=1, start_time=start.isoformat(), end_time=end.isoformat(), reason='Sửa'))
        r = self.client.get(f'/api/v1/pitches/1/availability?date={day}')
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual([s['status'] for s in r.json['data']['slots'][:4]], ['HELD', 'BOOKED', 'MAINTENANCE', 'AVAILABLE'])
        self.assertNotIn('booking_id', r.json['data']['slots'][0])
        self.assertNotIn('user_id', r.json['data']['slots'][0])

    def test_expired_hold_frees_availability_before_the_worker_runs(self):
        day = self.slot()[0].astimezone(VIETNAM).date().isoformat()
        data = self.hold(index=0)
        self.advance(seconds=300)
        self.assertEqual(self.client.get(f'/api/v1/pitches/1/availability?date={day}').json['data']['slots'][0]['status'], 'AVAILABLE')
        self.assertEqual(self.booking(data['booking_id']).status, 'PENDING_HOLD')

    def test_inactive_pitch_never_shows_bookable_slots(self):
        day = self.slot()[0].astimezone(VIETNAM).date().isoformat()
        slots = self.client.get(f'/api/v1/pitches/5/availability?date={day}').json['data']['slots']
        self.assertEqual({s['status'] for s in slots}, {'MAINTENANCE'})

    def test_availability_rejects_bad_dates(self):
        self.assertEqual(self.client.get('/api/v1/pitches/1/availability').status_code, 422)
        far = (self.now.astimezone(VIETNAM).date() + timedelta(days=11)).isoformat()
        self.assertEqual(self.client.get(f'/api/v1/pitches/1/availability?date={far}').status_code, 422)

class DirectHold(BookingCase):
    def post_slot(self, start, end, pitch_id=1, header=None, **extra):
        return self.client.post('/api/v1/bookings', headers=header or self.a, json=dict(pitch_id=pitch_id, start_time=start.isoformat(), end_time=end.isoformat(), **extra))

    def test_hold_contract_for_600000(self):
        data = self.hold()
        self.assertEqual((data['total_amount'], data['deposit_amount']), ('600000.00', '120000.00'))
        self.assertEqual((data['status'], data['booking_type'], data['payment_rule']), ('PENDING_HOLD', 'ONLINE', 'DIRECT_BOOKING'))
        self.assertEqual(data['hold_expires_at'], (self.now + timedelta(seconds=300)).isoformat().replace('+00:00', 'Z'))
        self.assertEqual(data['payer_progress'], [{'user_id': self.ua, 'required_amount': '120000.00', 'paid_amount': '0.00', 'status': 'UNPAID'}])

    def test_same_slot_blocked_touching_slot_allowed(self):
        self.hold(index=3)
        start, end = self.slot(index=3)
        r = self.post_slot(start, end, header=self.b)
        self.assertEqual((r.status_code, r.json['error']['code']), (409, 'SLOT_UNAVAILABLE'))
        self.hold(self.b, index=2)
        self.hold(self.b, index=4)
        self.hold(self.b, pitch_id=2, index=3)

    def test_hold_expires_at_exactly_300_seconds(self):
        self.hold(index=3)
        start, end = self.slot(index=3)
        self.advance(seconds=299)
        self.assertEqual(self.post_slot(start, end, header=self.b).status_code, 409)
        self.advance(seconds=1)
        self.assertEqual(self.post_slot(start, end, header=self.b).status_code, 201)

    def test_invalid_slots_return_422(self):
        start, end = self.slot()
        self.assertEqual(self.post_slot(start, start + timedelta(minutes=60)).status_code, 422)
        self.assertEqual(self.post_slot(start + timedelta(minutes=30), end + timedelta(minutes=30)).status_code, 422)
        past = list(policy.day_slots(self.now.astimezone(VIETNAM).date() - timedelta(days=1)))[0]
        self.assertEqual(self.post_slot(*past).status_code, 422)
        self.assertEqual(self.post_slot(*self.slot(days=11)).status_code, 422)
        self.assertEqual(self.post_slot(*self.slot(days=10)).status_code, 201)

    def test_protected_fields_naive_time_and_roles(self):
        start, end = self.slot()
        self.assertEqual(self.post_slot(start, end, total_amount='1').status_code, 422)
        naive = self.client.post('/api/v1/bookings', headers=self.a, json=dict(pitch_id=1, start_time='2030-01-01T06:00:00', end_time='2030-01-01T07:30:00'))
        self.assertEqual(naive.status_code, 422)
        self.assertEqual(self.client.post('/api/v1/bookings', json=dict(pitch_id=1, start_time=start.isoformat(), end_time=end.isoformat())).status_code, 401)
        self.assertEqual(self.post_slot(start, end, header=self.admin).status_code, 403)

    def test_inactive_pitch_unavailable(self):
        self.assertEqual(self.post_slot(*self.slot(), pitch_id=5).status_code, 409)
        self.assertEqual(self.post_slot(*self.slot(), pitch_id=999).status_code, 409)

    def test_privacy_of_booking_and_payment(self):
        data = self.confirmed()
        bid = data['booking_id']
        self.assertEqual(self.client.get(f'/api/v1/bookings/{bid}', headers=self.b).status_code, 404)
        self.assertEqual(self.client.get(f'/api/v1/bookings/{bid}', headers=self.admin).status_code, 200)
        pay = self.payments(bid)[0].payment_id
        self.assertEqual(self.client.get(f'/api/v1/payments/{pay}', headers=self.b).status_code, 404)
        own = self.client.get(f'/api/v1/payments/{pay}', headers=self.a).json['data']
        self.assertNotIn('note', own)
        self.assertEqual(self.client.get('/api/v1/payments/my', headers=self.a).json['meta']['total'], 1)
        self.assertEqual(self.client.get('/api/v1/payments/my', headers=self.b).json['meta']['total'], 0)
        self.assertEqual(self.client.get('/api/v1/bookings/my', headers=self.b).json['meta']['total'], 0)

class DepositSession(BookingCase):
    def test_session_created_then_reused_without_extending_hold(self):
        data = self.hold()
        first = self.client.post('/api/v1/payments/deposit', headers=self.a, json={'booking_id': data['booking_id'], 'payment_method': 'VNPAY'})
        self.assertEqual(first.status_code, 201, first.json)
        self.assertEqual(first.json['data']['amount'], '120000.00')
        self.assertEqual(first.json['data']['expires_at'], data['hold_expires_at'])
        self.assertEqual(first.json['data']['status'], 'PENDING')
        self.advance(seconds=100)
        again = self.client.post('/api/v1/payments/deposit', headers=self.a, json={'booking_id': data['booking_id'], 'payment_method': 'VNPAY'})
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json['data']['transaction_code'], first.json['data']['transaction_code'])
        self.assertEqual(again.json['data']['expires_at'], data['hold_expires_at'])
        self.assertEqual(len(self.payments(data['booking_id'])), 1)

    def test_client_cannot_set_amount_or_status(self):
        data = self.hold()
        r = self.client.post('/api/v1/payments/deposit', headers=self.a, json={'booking_id': data['booking_id'], 'payment_method': 'VNPAY', 'amount': '1'})
        self.assertEqual(r.status_code, 422)

    def test_only_payers_may_open_a_session(self):
        data = self.hold()
        r = self.client.post('/api/v1/payments/deposit', headers=self.b, json={'booking_id': data['booking_id'], 'payment_method': 'VNPAY'})
        self.assertEqual(r.status_code, 404)

    def test_unsupported_methods_never_fake_success(self):
        data = self.hold()
        for method in ('MOMO', 'CASH', 'BANK_TRANSFER'):
            r = self.client.post('/api/v1/payments/deposit', headers=self.a, json={'booking_id': data['booking_id'], 'payment_method': method})
            self.assertEqual((r.status_code, r.json['error']['code']), (422, 'UNSUPPORTED_PAYMENT_METHOD'))
        self.assertEqual(self.payments(data['booking_id']), [])
        self.assertEqual(self.client.post('/api/v1/payments/momo/ipn', json={}).status_code, 422)

    def test_unconfigured_gateway_is_503(self):
        self.app.extensions['payment_gateways'] = {}
        data = self.hold()
        r = self.client.post('/api/v1/payments/deposit', headers=self.a, json={'booking_id': data['booking_id'], 'payment_method': 'VNPAY'})
        self.assertEqual((r.status_code, r.json['error']['code']), (503, 'PAYMENT_PROVIDER_UNAVAILABLE'))

    def test_adapter_timeout_keeps_reference_for_retry(self):
        data = self.hold()
        self.gateway.raise_on_create = True
        r = self.client.post('/api/v1/payments/deposit', headers=self.a, json={'booking_id': data['booking_id'], 'payment_method': 'VNPAY'})
        self.assertEqual(r.status_code, 503)
        kept = self.payments(data['booking_id'])
        self.assertEqual([p.status for p in kept], ['PENDING'])
        self.gateway.raise_on_create = False
        self.assertEqual(self.open_deposit(data['booking_id'])['transaction_code'], kept[0].transaction_code)
        self.assertEqual(len(self.payments(data['booking_id'])), 1)

    def test_expired_hold_and_paid_deposit_are_conflicts(self):
        data = self.hold()
        self.advance(seconds=300)
        r = self.client.post('/api/v1/payments/deposit', headers=self.a, json={'booking_id': data['booking_id'], 'payment_method': 'VNPAY'})
        self.assertEqual((r.status_code, r.json['error']['code']), (409, 'HOLD_EXPIRED'))
        paid = self.confirmed(self.b, index=2)
        r = self.client.post('/api/v1/payments/deposit', headers=self.b, json={'booking_id': paid['booking_id'], 'payment_method': 'VNPAY'})
        self.assertEqual(r.status_code, 409)

class Callbacks(BookingCase):
    def notifications(self, kind):
        with UnitOfWork() as ctx:
            return ctx.session.scalar(select(func.count()).select_from(Notification).where(Notification.notification_type == kind))

    def test_success_confirms_direct_booking_once(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.assertEqual(self.callback(session).outcome, 'OK')
        self.assertEqual(self.booking(data['booking_id']).status, 'CONFIRMED')
        self.assertEqual(self.notifications('BOOKING_CONFIRMED'), 1)
        self.assertEqual(self.callback(session).outcome, 'DUPLICATE')
        self.assertEqual(self.notifications('PAYMENT_SUCCESS'), 1)
        self.assertEqual(len(self.payments(data['booking_id'])), 1)

    def test_old_failure_never_overwrites_success(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.callback(session)
        self.assertEqual(self.callback(session, 'FAILED').outcome, 'DUPLICATE')
        self.assertEqual(self.payments(data['booking_id'])[0].status, 'SUCCESS')

    def test_failure_then_real_money_is_still_recorded(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.callback(session, 'FAILED')
        self.assertEqual(self.payments(data['booking_id'])[0].status, 'FAILED')
        self.assertEqual(self.booking(data['booking_id']).status, 'PENDING_HOLD')
        self.callback(session)
        self.assertEqual(self.payments(data['booking_id'])[0].status, 'SUCCESS')
        self.assertEqual(self.booking(data['booking_id']).status, 'CONFIRMED')

    def test_wrong_amount_changes_no_money(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.assertEqual(self.callback(session, amount='1000').outcome, 'AMOUNT_MISMATCH')
        payment = self.payments(data['booking_id'])[0]
        self.assertEqual(payment.status, 'PENDING')
        self.assertIn('sai so tien', payment.note)
        self.assertEqual(self.booking(data['booking_id']).status, 'PENDING_HOLD')

    def test_unknown_reference_and_wrong_provider(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.assertEqual(self.callback(dict(session, transaction_code='NOPE')).outcome, 'NOT_FOUND')
        from app.use_cases.process_payment import process_gateway_callback
        wrong = process_gateway_callback('MOMO', GatewayResult('SUCCESS', session['transaction_code'], Decimal(session['amount'])))
        self.assertEqual(wrong.outcome, 'NOT_FOUND')

    def test_late_callback_records_money_refunds_and_never_revives(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.advance(seconds=300)
        self.assertEqual(self.callback(session).outcome, 'OK')
        self.assertEqual(self.booking(data['booking_id']).status, 'EXPIRED')
        original, refund = self.payments(data['booking_id'])
        self.assertEqual((original.status, refund.payment_type, refund.status), ('SUCCESS', 'REFUND', 'REFUND_PROCESSING'))
        self.assertEqual(refund.refund_for_payment_id, original.payment_id)
        self.assertEqual(self.callback(session).outcome, 'DUPLICATE')
        self.assertEqual(len(self.payments(data['booking_id'])), 2)

    def test_late_callback_after_worker_does_not_take_back_a_rebooked_slot(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.advance(seconds=300)
        self.assertEqual(expire_holds(), 1)
        other = self.hold(self.b)
        self.callback(session)
        self.assertEqual(self.booking(data['booking_id']).status, 'EXPIRED')
        self.assertEqual(self.booking(other['booking_id']).status, 'PENDING_HOLD')
        self.assertEqual([p.payment_type for p in self.payments(data['booking_id'])], ['BOOKING_DEPOSIT', 'REFUND'])

class VnpayAdapter(BookingCase):
    """Real adapter with a test secret and no network; not evidence of a working merchant account."""
    SECRET = 'vnpay-test-secret'

    def setUp(self):
        super().setUp()
        self.app.config.update(VNPAY_TMN_CODE='TESTTMN', VNPAY_HASH_SECRET=self.SECRET, VNPAY_RETURN_URL='http://localhost:5173/bookings')
        self.app.extensions['payment_gateways'] = {}

    def sign(self, params):
        query = urlencode(sorted(params.items()))
        return hmac.new(self.SECRET.encode(), query.encode(), hashlib.sha512).hexdigest()

    def ipn(self, session, **overrides):
        params = dict(vnp_TmnCode='TESTTMN', vnp_Amount=str(int(Decimal(session['amount']) * 100)), vnp_TxnRef=session['transaction_code'], vnp_ResponseCode='00',
                      vnp_TransactionStatus='00', vnp_TransactionNo='14000001', vnp_PayDate=self.now.astimezone(VIETNAM).strftime('%Y%m%d%H%M%S'),
                      vnp_OrderInfo='Coc san ' + session['transaction_code'], vnp_BankCode='NCB')
        params.update(overrides)
        params['vnp_SecureHash'] = overrides.get('vnp_SecureHash') or self.sign(params)
        return self.client.get('/api/v1/payments/vnpay/ipn?' + urlencode(params)).json['RspCode']

    def test_payment_url_is_signed_stable_and_in_vietnam_time(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        url = urlparse(session['payment_url'])
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        given = params.pop('vnp_SecureHash')
        self.assertEqual(given, self.sign(params))
        self.assertEqual(params['vnp_Amount'], '12000000')
        self.assertEqual(params['vnp_Version'], '2.1.0')
        self.assertEqual(params['vnp_TxnRef'], session['transaction_code'])
        deadline = self.now + timedelta(seconds=300)
        self.assertEqual(params['vnp_ExpireDate'], deadline.astimezone(VIETNAM).strftime('%Y%m%d%H%M%S'))
        self.advance(seconds=30)
        self.assertEqual(self.open_deposit(data['booking_id'])['payment_url'], session['payment_url'])

    def test_ipn_success_then_repeat_acks(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.assertEqual(self.ipn(session), '00')
        self.assertEqual(self.booking(data['booking_id']).status, 'CONFIRMED')
        payment = self.payments(data['booking_id'])[0]
        self.assertEqual(payment.status, 'SUCCESS')
        self.assertIn('gw=14000001', payment.note)
        self.assertEqual(self.ipn(session), '02')

    def test_forged_signature_changes_nothing(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.assertEqual(self.ipn(session, vnp_SecureHash='0' * 128), '97')
        self.assertEqual(self.payments(data['booking_id'])[0].status, 'PENDING')

    def test_other_merchant_wrong_amount_and_unknown_order(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.assertEqual(self.ipn(session, vnp_TmnCode='OTHER'), '97')
        self.assertEqual(self.ipn(session, vnp_Amount='100'), '04')
        self.assertEqual(self.ipn(session, vnp_TxnRef='NOPE'), '01')
        self.assertEqual(self.payments(data['booking_id'])[0].status, 'PENDING')

    def test_declined_payment_marks_failed_and_requires_both_codes(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.assertEqual(self.ipn(session, vnp_ResponseCode='24', vnp_TransactionStatus='02'), '00')
        self.assertEqual(self.payments(data['booking_id'])[0].status, 'FAILED')
        gateway = VnpayGateway('TESTTMN', self.SECRET, 'https://x.test', 'https://y.test')
        params = dict(vnp_TmnCode='TESTTMN', vnp_Amount='100', vnp_TxnRef='R', vnp_ResponseCode='00', vnp_TransactionStatus='02')
        params['vnp_SecureHash'] = self.sign(params)
        self.assertEqual(gateway.verify_callback(b'', params).state, 'FAILED')

    def test_network_failure_is_unknown_not_failed(self):
        gateway = VnpayGateway('TESTTMN', self.SECRET, 'https://x.test', 'http://127.0.0.1:9/none')
        self.assertEqual(gateway.request_refund('REF', 'RF1', Decimal('100'), transaction_date=self.now).state, 'UNKNOWN')
        self.assertEqual(gateway.query_payment('REF', amount=Decimal('100'), transaction_date=self.now).state, 'UNKNOWN')
        self.assertEqual(gateway.cancel_payment('REF'), 'UNSUPPORTED')

    def test_missing_config_acks_retry(self):
        self.app.config.update(VNPAY_TMN_CODE='')
        self.assertEqual(self.client.get('/api/v1/payments/vnpay/ipn?vnp_TxnRef=X').json['RspCode'], '99')

class MatchFlowWithRealServices(BookingCase):
    """Đức's respond_proposal and match_service, Tú's booking and payment: no adapter double."""
    def pay(self, booking_id, header):
        return self.callback(self.open_deposit(booking_id, header))

    def statuses(self, booking_id, match_id):
        with UnitOfWork() as ctx:
            match = ctx.session.get(Match, match_id)
            posts = [ctx.session.get(MatchPost, match.post_id).status, ctx.session.get(MatchPost, match.opponent_post_id).status]
            return ctx.session.get(Booking, booking_id).status, match.status, posts

    def test_paired_requests_create_one_hold_with_two_payers(self):
        booking_id, match_id = self.match_booking()
        booking = self.booking(booking_id)
        self.assertEqual(booking.payer_plan, [{'user_id': self.ua, 'amount': '60000.00'}, {'user_id': self.ub, 'amount': '60000.00'}])
        self.assertEqual((booking.user_id, booking.payment_rule, booking.pitch_id), (self.ua, 'SPLIT_EQUAL', 1))
        # Two teams that never booked get six hours to pay their halves.
        self.assertEqual(booking.hold_expires_at, self.now + timedelta(seconds=MATCH_HOLD_SECONDS))
        self.assertEqual(scan_requests()['matches'], [])
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.scalar(select(func.count()).select_from(Booking)), 1)
            self.assertEqual(ctx.session.scalar(select(func.count()).select_from(Match)), 1)
        self.assertEqual(self.statuses(booking_id, match_id), ('PENDING_HOLD', 'SUGGESTED', ['MATCHED', 'MATCHED']))

    def test_no_pitch_left_pairs_nobody_and_keeps_searching(self):
        self.hold(self.c, pitch_id=1, days=2)
        self.hold(self.c, pitch_id=2, days=2)
        first, second, match = self.agreed_match()
        self.assertIsNone(match)
        with UnitOfWork() as ctx:
            self.assertEqual([ctx.session.get(MatchPost, i).status for i in (first, second)], ['OPEN', 'OPEN'])
            self.assertEqual(ctx.session.scalar(select(func.count()).select_from(Payment)), 0)

    def test_second_pitch_used_when_first_is_taken(self):
        self.hold(self.c, pitch_id=1, days=2)
        booking_id, _ = self.match_booking()
        self.assertEqual(self.booking(booking_id).pitch_id, 2)

    def test_one_team_paying_does_not_confirm(self):
        booking_id, match_id = self.match_booking()
        self.pay(booking_id, self.a)
        self.assertEqual(self.statuses(booking_id, match_id), ('PENDING_HOLD', 'SUGGESTED', ['MATCHED', 'MATCHED']))

    def test_both_deposits_confirm_everything_in_one_transaction(self):
        booking_id, match_id = self.match_booking()
        self.pay(booking_id, self.a)
        self.pay(booking_id, self.b)
        self.assertEqual(self.statuses(booking_id, match_id), ('CONFIRMED', 'CONFIRMED', ['MATCHED', 'MATCHED']))
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.scalar(select(func.count()).select_from(Notification).where(Notification.notification_type == 'MATCH_CONFIRMED')), 2)
            self.assertIsNotNone(ctx.session.get(Match, match_id).confirmed_at)

    def test_opponent_sees_booking_and_stranger_does_not(self):
        booking_id, match_id = self.match_booking()
        self.assertEqual(self.client.get(f'/api/v1/bookings/{booking_id}', headers=self.b).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/bookings/my', headers=self.b).json['meta']['total'], 1)
        self.assertEqual(self.client.get(f'/api/v1/bookings/{booking_id}', headers=self.c).status_code, 404)
        detail = self.client.get(f'/api/v1/matches/{match_id}', headers=self.b).json['data']
        self.assertEqual(detail['booking']['booking_id'], booking_id)

    def test_timeout_with_one_deposit_refunds_it_and_reopens_only_the_payer(self):
        booking_id, match_id = self.match_booking()
        self.pay(booking_id, self.a)
        self.advance(seconds=MATCH_HOLD_SECONDS)
        self.assertEqual(expire_holds(), 1)
        self.assertEqual(expire_holds(), 0)
        # The team that paid searches again; the team that did not pay is dropped.
        self.assertEqual(self.statuses(booking_id, match_id), ('EXPIRED', 'CANCELLED', ['OPEN', 'CANCELLED']))
        rows = self.payments(booking_id)
        self.assertEqual([(p.payment_type, p.user_id) for p in rows], [('BOOKING_DEPOSIT', self.ua), ('REFUND', self.ua)])

    def test_second_deposit_after_deadline_never_confirms(self):
        booking_id, match_id = self.match_booking()
        self.pay(booking_id, self.a)
        session = self.open_deposit(booking_id, self.b)
        self.advance(seconds=MATCH_HOLD_SECONDS)
        self.callback(session)
        self.assertEqual(self.statuses(booking_id, match_id)[:2], ('EXPIRED', 'CANCELLED'))
        refunded = [p.user_id for p in self.payments(booking_id) if p.payment_type == 'REFUND']
        self.assertEqual(sorted(refunded), sorted([self.ua, self.ub]))

    def test_user_cancel_forfeits_own_deposit_and_refunds_the_other_side(self):
        booking_id, match_id = self.match_booking()
        self.pay(booking_id, self.a)
        self.pay(booking_id, self.b)
        r = self.client.post(f'/api/v1/matches/{match_id}/cancel', headers=self.a, json={'reason': 'Bận việc'})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json['data']['status'], 'CANCELLED')
        summary = r.json['data']['refund_summary']
        self.assertEqual((summary['cause'], summary['refund_count'], summary['refund_amount'], summary['forfeited_amount']), ('USER_CANCEL', 1, '60000.00', '60000.00'))
        rows = self.payments(booking_id)
        refund = next(p for p in rows if p.payment_type == 'REFUND')
        self.assertEqual(refund.user_id, self.ub)
        forfeited = next(p for p in rows if p.user_id == self.ua)
        self.assertEqual(forfeited.status, 'SUCCESS')
        self.assertIn(self.booking(booking_id).status, ('CANCELLED',))
        self.assertIn('USER_CANCEL', self.booking(booking_id).note)
        with UnitOfWork() as ctx:
            match = ctx.session.get(Match, match_id)
            self.assertEqual(ctx.session.get(MatchPost, match.post_id).status, 'CANCELLED')
            self.assertEqual(ctx.session.get(MatchPost, match.opponent_post_id).status, 'OPEN')
        again = self.client.post(f'/api/v1/matches/{match_id}/cancel', headers=self.a, json={'reason': 'Lặp'})
        self.assertEqual(again.status_code, 200)
        self.assertEqual(len([p for p in self.payments(booking_id) if p.payment_type == 'REFUND']), 1)

    def test_admin_incident_refunds_each_payer_once(self):
        booking_id, match_id = self.match_booking()
        self.pay(booking_id, self.a)
        self.pay(booking_id, self.b)
        r = self.client.post(f'/api/v1/admin/bookings/{booking_id}/cancel', headers=self.admin, json={'reason': 'Mất điện'})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json['data']['refund_summary']['cause'], 'ADMIN_INCIDENT')
        self.assertEqual(self.statuses(booking_id, match_id)[:2], ('CANCELLED', 'CANCELLED'))
        self.client.post(f'/api/v1/admin/bookings/{booking_id}/cancel', headers=self.admin, json={'reason': 'Lặp'})
        refunds = [p for p in self.payments(booking_id) if p.payment_type == 'REFUND']
        self.assertEqual(sorted(p.user_id for p in refunds), sorted([self.ua, self.ub]))

    def test_winning_or_either_rule_gets_no_refund_and_same_balance(self):
        for index, rule in enumerate(('SPLIT_EQUAL', 'LOSER_PAYS_REMAINDER')):
            with self.subTest(rule=rule):
                self.tearDown()
                self.setUp()
                booking_id, _ = self.match_booking(rule)
                self.pay(booking_id, self.a)
                self.pay(booking_id, self.b)
                self.go_after(self.booking(booking_id).end_time)
                data = self.client.get(f'/api/v1/admin/bookings/{booking_id}/balance', headers=self.admin).json['data']
                self.assertEqual((data['payment_rule'], data['outstanding_amount'], data['deposit_collected_amount']), (rule, '480000.00', '120000.00'))
                self.assertNotIn('outcome', data)
                self.assertNotIn('payers', data)
                self.assertIsNotNone(data['qr_payload'])
                self.assertEqual([p for p in self.payments(booking_id) if p.payment_type == 'REFUND'], [])

class DirectCancelAndRefundWorkers(BookingCase):
    def cancel(self, booking_id, header=None, **body):
        return self.client.post(f'/api/v1/bookings/{booking_id}/cancel', headers=header or self.a, json=dict(reason='Bận', **body))

    def test_cancel_unpaid_hold_frees_the_slot(self):
        data = self.hold()
        r = self.cancel(data['booking_id'])
        self.assertEqual((r.status_code, r.json['data']['status'], r.json['data']['refund_summary']['refund_count']), (200, 'CANCELLED', 0))
        self.hold(self.b)

    def test_user_cancel_after_deposit_forfeits_with_no_refund(self):
        data = self.confirmed()
        r = self.cancel(data['booking_id'])
        self.assertEqual(r.json['data']['refund_summary']['forfeited_amount'], '120000.00')
        rows = self.payments(data['booking_id'])
        self.assertEqual([(p.payment_type, p.status) for p in rows], [('BOOKING_DEPOSIT', 'SUCCESS')])
        self.assertIn('MAT_COC', rows[0].note)
        self.assertEqual(self.cancel(data['booking_id']).status_code, 200)
        self.assertEqual(len(self.payments(data['booking_id'])), 1)

    def test_client_cannot_choose_the_cause(self):
        data = self.confirmed()
        self.assertEqual(self.cancel(data['booking_id'], cause='ADMIN_INCIDENT').status_code, 422)
        self.assertEqual(self.booking(data['booking_id']).status, 'CONFIRMED')

    def test_stranger_cannot_cancel_and_player_cannot_after_kickoff(self):
        data = self.confirmed()
        self.assertEqual(self.cancel(data['booking_id'], self.b).status_code, 404)
        self.go_after(self.booking(data['booking_id']).start_time)
        self.assertEqual(self.cancel(data['booking_id']).status_code, 409)
        self.assertEqual(self.client.post(f"/api/v1/admin/bookings/{data['booking_id']}/cancel", headers=self.a, json={'reason': 'x'}).status_code, 403)

    def test_cancel_after_deadline_is_a_timeout_not_a_forfeit(self):
        data = self.hold()
        self.advance(seconds=301)
        r = self.cancel(data['booking_id'])
        self.assertEqual(r.json['data']['status'], 'EXPIRED')

    def test_payment_arriving_after_user_cancel_is_refunded(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.cancel(data['booking_id'])
        self.callback(session)
        self.assertEqual(self.booking(data['booking_id']).status, 'CANCELLED')
        self.assertEqual([p.payment_type for p in self.payments(data['booking_id'])], ['BOOKING_DEPOSIT', 'REFUND'])

    def test_worker_never_expires_confirmed_booking(self):
        data = self.confirmed()
        self.advance(seconds=1000)
        self.assertEqual(expire_holds(), 0)
        self.assertEqual(self.booking(data['booking_id']).status, 'CONFIRMED')

    def refund_case(self):
        data = self.confirmed()
        self.client.post(f"/api/v1/admin/bookings/{data['booking_id']}/cancel", headers=self.admin, json={'reason': 'Sự cố'})
        return data['booking_id']

    def test_refund_stays_processing_until_gateway_confirms(self):
        booking_id = self.refund_case()
        original, refund = self.payments(booking_id)
        self.assertEqual((original.status, refund.status, refund.paid_at), ('SUCCESS', 'REFUND_PROCESSING', None))
        self.assertEqual(refund.transaction_code, f'RF{refund.payment_id}')

    def test_refund_success_moves_original_to_refunded(self):
        booking_id = self.refund_case()
        self.assertEqual(process_refunds(), 1)
        original, refund = self.payments(booking_id)
        self.assertEqual((original.status, refund.status), ('REFUNDED', 'SUCCESS'))
        self.assertIsNotNone(refund.paid_at)
        self.assertEqual(process_refunds(), 0)
        self.assertEqual(len(self.gateway.refund_requests), 1)

    def test_refund_failed_keeps_original_success(self):
        booking_id = self.refund_case()
        self.gateway.refund_state = 'FAILED'
        process_refunds()
        original, refund = self.payments(booking_id)
        self.assertEqual((original.status, refund.status), ('SUCCESS', 'FAILED'))

    def test_unknown_result_is_never_reported_as_refunded(self):
        booking_id = self.refund_case()
        self.gateway.refund_state = 'UNKNOWN'
        self.assertEqual(process_refunds(), 0)
        original, refund = self.payments(booking_id)
        self.assertEqual((original.status, refund.status), ('SUCCESS', 'REFUND_PROCESSING'))

    def test_crash_after_gateway_call_does_not_send_a_second_refund(self):
        booking_id = self.refund_case()
        self.gateway.refund_state = 'PENDING'
        process_refunds()
        self.assertEqual(len(self.gateway.refund_requests), 1)
        self.gateway.refund_state = 'SUCCESS'
        self.assertEqual(process_refunds(), 1)
        self.assertEqual(len(self.gateway.refund_requests), 1)
        self.assertEqual(self.payments(booking_id)[1].status, 'SUCCESS')

    def test_admin_refund_reuses_processing_row(self):
        data = self.confirmed()
        pay = self.payments(data['booking_id'])[0].payment_id
        for _ in range(2):
            r = self.client.post(f'/api/v1/admin/payments/{pay}/refund', headers=self.admin, json={'reason': 'Đối soát'})
            self.assertEqual(r.status_code, 202, r.json)
        self.assertEqual(len(self.payments(data['booking_id'])), 2)
        self.assertEqual(self.client.post(f'/api/v1/admin/payments/{pay}/refund', headers=self.a, json={'reason': 'x'}).status_code, 403)

    def test_reconcile_resolves_expired_sessions_only(self):
        data = self.hold()
        self.open_deposit(data['booking_id'])
        self.gateway.payment_state = 'SUCCESS'
        self.assertEqual(reconcile_payments()['resolved_payments'], 0)
        self.assertEqual(self.payments(data['booking_id'])[0].status, 'PENDING')
        self.advance(seconds=300)
        self.assertEqual(reconcile_payments()['resolved_payments'], 1)
        self.assertEqual(self.booking(data['booking_id']).status, 'EXPIRED')
        self.assertEqual([p.payment_type for p in self.payments(data['booking_id'])], ['BOOKING_DEPOSIT', 'REFUND'])

    def test_reconcile_not_found_after_expiry_is_failed_and_timeout_stays_pending(self):
        data = self.hold()
        self.open_deposit(data['booking_id'])
        self.advance(seconds=300)
        self.gateway.payment_state = 'UNKNOWN'
        reconcile_payments()
        self.assertEqual(self.payments(data['booking_id'])[0].status, 'PENDING')
        self.gateway.payment_state = 'NOT_FOUND'
        reconcile_payments()
        self.assertEqual(self.payments(data['booking_id'])[0].status, 'FAILED')

    def test_verified_failed_refund_is_not_resent_by_the_recovery_sweep(self):
        data = self.hold()
        session = self.open_deposit(data['booking_id'])
        self.advance(seconds=300)
        self.callback(session)
        self.gateway.refund_state = 'FAILED'
        process_refunds()
        self.assertEqual(reconcile_payments()['recovered_refunds'], 0)
        self.assertEqual(process_refunds(), 0)
        self.assertEqual(len(self.gateway.refund_requests), 1)
        self.assertEqual([p.status for p in self.payments(data['booking_id'])], ['SUCCESS', 'FAILED'])

    def test_crash_recovery_recreates_a_missing_refund_once(self):
        data = self.confirmed()
        with UnitOfWork() as ctx:
            ctx.session.get(Booking, data['booking_id']).status = 'EXPIRED'
        self.assertEqual(reconcile_payments()['recovered_refunds'], 1)
        self.assertEqual(reconcile_payments()['recovered_refunds'], 0)
        self.assertEqual(len(self.payments(data['booking_id'])), 2)

class BalanceAndConfirmPaid(BookingCase):
    def ended(self):
        data = self.confirmed()
        self.go_after(self.booking(data['booking_id']).end_time)
        return data['booking_id']

    def confirm(self, booking_id, expected='480000', key='key-00001', receipts=None, header=None):
        receipts = receipts if receipts is not None else [{'payment_method': 'CASH', 'amount': '480000'}]
        return self.client.post(f'/api/v1/admin/bookings/{booking_id}/confirm-paid', headers=header or self.admin,
                                json=dict(expected_outstanding=expected, idempotency_key=key, receipts=receipts))

    def balance(self, booking_id):
        return self.client.get(f'/api/v1/admin/bookings/{booking_id}/balance', headers=self.admin)

    def test_crc_and_qr_payload(self):
        self.assertEqual(crc16('123456789'), '29B1')
        payload = bank_qr_payload('970436', '0011001234567', Decimal('480000.00'), 'BOOKING-21')
        self.assertTrue(payload.startswith('000201010212'))
        self.assertIn('5406480000', payload)
        self.assertIn('BOOKING-21', payload)
        self.assertEqual(payload[-4:], crc16(payload[:-4]))

    def test_balance_after_game(self):
        booking_id = self.ended()
        data = self.balance(booking_id).json['data']
        self.assertEqual((data['total_amount'], data['deposit_collected_amount'], data['remaining_collected_amount'], data['collected_amount'], data['outstanding_amount'], data['payment_status']),
                         ('600000.00', '120000.00', '0.00', '120000.00', '480000.00', 'PARTIAL'))
        self.assertEqual(data['transfer_reference'], f'SAN{booking_id}TT')
        self.assertIn(f'SAN{booking_id}TT', data['qr_payload'])
        self.assertIsNone(data['qr_unavailable_reason'])

    def test_viewing_qr_records_nothing(self):
        booking_id = self.ended()
        before = len(self.payments(booking_id))
        self.balance(booking_id)
        self.assertEqual(len(self.payments(booking_id)), before)

    def test_missing_bank_config_explains_instead_of_faking(self):
        self.app.config.update(BANK_BIN='', BANK_ACCOUNT_NO='')
        data = self.balance(self.ended()).json['data']
        self.assertIsNone(data['qr_payload'])
        self.assertIn('ngân hàng', data['qr_unavailable_reason'])

    def test_qr_for_the_rest_is_ready_as_soon_as_confirmed(self):
        # The customer pays the rest at the counter on arrival, not only after the match.
        data = self.confirmed()
        self.assertIsNotNone(self.balance(data['booking_id']).json['data']['qr_payload'])

    def test_mixed_receipts_close_the_booking(self):
        booking_id = self.ended()
        r = self.confirm(booking_id, receipts=[{'payment_method': 'CASH', 'amount': '180000'}, {'payment_method': 'BANK_TRANSFER', 'amount': '300000', 'reference': 'SK-1'}])
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual((r.json['data']['outstanding_amount'], r.json['data']['payment_status'], r.json['data']['collected_amount']), ('0.00', 'PAID', '600000.00'))
        self.assertIsNone(r.json['data']['qr_payload'])
        rows = [p for p in self.payments(booking_id) if p.payment_type == 'BOOKING_REMAINING_PAYMENT']
        self.assertEqual([(p.payment_method, p.amount, p.status) for p in rows], [('CASH', Decimal('180000.00'), 'SUCCESS'), ('BANK_TRANSFER', Decimal('300000.00'), 'SUCCESS')])
        self.assertTrue(all(p.recorded_by_admin_id == self.uadmin and p.user_id == self.ua and p.paid_at and p.note.startswith('THU_GOP') for p in rows))

    def test_retry_is_idempotent_and_changed_payload_conflicts(self):
        booking_id = self.ended()
        self.assertEqual(self.confirm(booking_id).status_code, 200)
        retry = self.confirm(booking_id)
        self.assertEqual((retry.status_code, retry.json['data']['outstanding_amount']), (200, '0.00'))
        self.assertEqual(len(self.payments(booking_id)), 2)
        changed = self.confirm(booking_id, receipts=[{'payment_method': 'BANK_TRANSFER', 'amount': '480000'}])
        self.assertEqual((changed.status_code, changed.json['error']['code']), (409, 'STATE_CONFLICT'))

    def test_second_tab_with_stale_balance_is_rejected(self):
        booking_id = self.ended()
        self.assertEqual(self.confirm(booking_id).status_code, 200)
        other = self.confirm(booking_id, key='key-00002')
        self.assertEqual(other.status_code, 409)
        self.assertEqual(len(self.payments(booking_id)), 2)

    def test_partial_payment_lowers_only_the_real_balance(self):
        booking_id = self.ended()
        r = self.client.post('/api/v1/admin/payments/record', headers=self.admin, json=dict(booking_id=booking_id, user_id=self.ua, amount='100000', payment_type='BOOKING_REMAINING_PAYMENT', payment_method='CASH', reference='PT-1'))
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual(self.balance(booking_id).json['data']['outstanding_amount'], '380000.00')
        self.assertEqual(self.confirm(booking_id, expected='480000').status_code, 409)
        self.assertEqual(self.confirm(booking_id, expected='380000', receipts=[{'payment_method': 'CASH', 'amount': '380000'}]).status_code, 200)

    def test_wrong_totals_and_bad_amounts_are_422(self):
        booking_id = self.ended()
        self.assertEqual(self.confirm(booking_id, receipts=[{'payment_method': 'CASH', 'amount': '100'}]).status_code, 422)
        self.assertEqual(self.confirm(booking_id, receipts=[{'payment_method': 'CASH', 'amount': '480000.50'}]).status_code, 422)
        self.assertEqual(self.confirm(booking_id, receipts=[{'payment_method': 'VNPAY', 'amount': '480000'}]).status_code, 422)
        self.assertEqual(self.confirm(booking_id, receipts=[{'payment_method': 'CASH', 'amount': 480000}]).status_code, 422)
        self.assertEqual(self.confirm(booking_id, receipts=[{'payment_method': 'CASH', 'amount': '480000', 'user_id': 1}]).status_code, 422)
        self.assertEqual(self.confirm(booking_id, receipts=[]).status_code, 422)
        self.assertEqual(len(self.payments(booking_id)), 1)

    def test_player_is_rejected_and_admin_collects_before_kick_off(self):
        booking_id = self.confirmed()['booking_id']
        self.assertEqual(self.confirm(booking_id, header=self.a).status_code, 403)
        self.assertEqual(self.client.get(f'/api/v1/admin/bookings/{booking_id}/balance', headers=self.a).status_code, 403)
        self.assertEqual(len(self.payments(booking_id)), 1)
        r = self.confirm(booking_id)
        self.assertEqual((r.status_code, r.json['data']['payment_status']), (200, 'PAID'), r.json)

    def test_pending_online_remaining_blocks_confirmation(self):
        booking_id = self.ended()
        with UnitOfWork() as ctx:
            ctx.session.add(Payment(user_id=self.ua, booking_id=booking_id, amount=480000, payment_type='BOOKING_REMAINING_PAYMENT', payment_method='VNPAY', status='PENDING', transaction_code='OLD-1'))
        r = self.confirm(booking_id)
        self.assertEqual((r.status_code, r.json['error']['code']), (409, 'PAYMENT_RECONCILIATION_REQUIRED'))

    def test_refund_raises_outstanding_exactly_once(self):
        booking_id = self.ended()
        pay = self.payments(booking_id)[0].payment_id
        self.client.post(f'/api/v1/admin/payments/{pay}/refund', headers=self.admin, json={'reason': 'x'})
        self.assertEqual(self.balance(booking_id).json['data']['collected_amount'], '120000.00')
        process_refunds()
        data = self.balance(booking_id).json['data']
        self.assertEqual((data['deposit_collected_amount'], data['collected_amount'], data['outstanding_amount']), ('120000.00', '0.00', '600000.00'))

    def test_consolidated_receipts_are_not_auto_refunded_to_reference_account(self):
        booking_id = self.ended()
        self.confirm(booking_id)
        self.client.post(f'/api/v1/admin/bookings/{booking_id}/cancel', headers=self.admin, json={'reason': 'Sự cố'})
        refunds = [p for p in self.payments(booking_id) if p.payment_type == 'REFUND']
        self.assertEqual(len(refunds), 1)
        self.assertEqual(refunds[0].amount, Decimal('120000.00'))

class AdminOperations(BookingCase):
    def test_pitch_management(self):
        r = self.client.post('/api/v1/admin/pitches', headers=self.admin, json=dict(pitch_name='Sân mới', pitch_type='PITCH_5', price_per_slot='250000'))
        self.assertEqual((r.status_code, r.json['data']['complex_id'], r.json['data']['price_per_slot']), (201, 1, '250000.00'))
        pid = r.json['data']['pitch_id']
        r = self.client.patch(f'/api/v1/admin/pitches/{pid}', headers=self.admin, json=dict(status='MAINTENANCE', price_per_slot='260000'))
        self.assertEqual((r.status_code, r.json['data']['status'], r.json['data']['price_per_slot']), (200, 'MAINTENANCE', '260000.00'))
        self.assertEqual(self.client.post('/api/v1/admin/pitches', headers=self.a, json=dict(pitch_name='x', pitch_type='PITCH_5', price_per_slot='1')).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/admin/pitches', headers=self.admin, json=dict(pitch_name='x', pitch_type='PITCH_11', price_per_slot='1')).status_code, 422)
        self.assertEqual(self.client.patch(f'/api/v1/admin/pitches/{pid}', headers=self.admin, json=dict(complex_id=9)).status_code, 422)
        self.assertEqual(self.client.patch('/api/v1/admin/pitches/999', headers=self.admin, json=dict(status='ACTIVE')).status_code, 404)

    def test_price_change_keeps_existing_booking_amount(self):
        data = self.hold()
        self.client.patch('/api/v1/admin/pitches/1', headers=self.admin, json=dict(price_per_slot='700000'))
        self.assertEqual(self.booking(data['booking_id']).total_amount, Decimal('600000.00'))

    def manual(self, index=8):
        """A player's online hold: the only booking that still waits for a deposit."""
        start, end = self.slot(index=index)
        r = self.client.post('/api/v1/bookings', headers=self.b, json=dict(pitch_id=1, start_time=start.isoformat(), end_time=end.isoformat()))
        return r

    def counter(self, index=8, **extra):
        start, end = self.slot(index=index)
        return self.client.post('/api/v1/admin/bookings', headers=self.admin, json=dict(user_id=self.ub, pitch_id=1, start_time=start.isoformat(), end_time=end.isoformat(), note='Khách gọi điện', **extra))

    def record(self, booking_id, amount='120000', reference='PT-1', kind='BOOKING_DEPOSIT', user=None, method='CASH'):
        return self.client.post('/api/v1/admin/payments/record', headers=self.admin, json=dict(booking_id=booking_id, user_id=user or self.ub, amount=amount, payment_type=kind, payment_method=method, reference=reference))

    def test_counter_booking_is_confirmed_at_once_and_records_money_taken(self):
        r = self.counter()
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual((r.json['data']['booking_type'], r.json['data']['status'], r.json['data']['hold_expires_at']), ('MANUAL_ADMIN', 'CONFIRMED', None))
        self.assertEqual(self.payments(r.json['data']['booking_id']), [])
        paid = self.counter(index=7, payment={'amount': '200000', 'payment_method': 'CASH', 'reference': 'PT-9'})
        self.assertEqual(paid.status_code, 201, paid.json)
        rows = sorted((p.payment_type, p.amount, p.status) for p in self.payments(paid.json['data']['booking_id']))
        self.assertEqual(rows, [('BOOKING_DEPOSIT', Decimal('120000.00'), 'SUCCESS'), ('BOOKING_REMAINING_PAYMENT', Decimal('80000.00'), 'SUCCESS')])
        self.assertEqual(paid.json['data']['payer_progress'][0]['status'], 'PAID')
        self.assertEqual(self.counter(index=6, payment={'amount': '600001', 'payment_method': 'CASH'}).status_code, 422)
        self.assertEqual(self.counter(index=6, payment={'amount': '100', 'payment_method': 'VNPAY'}).status_code, 422)
        # The slot is taken immediately, with no expiry.
        self.go_after(self.now, seconds=3600)
        self.assertEqual(self.counter().json['error']['code'], 'SLOT_UNAVAILABLE')

    def test_manual_booking_needs_a_real_deposit(self):
        r = self.manual()
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual(r.json['data']['status'], 'PENDING_HOLD')
        bid = r.json['data']['booking_id']
        self.assertEqual(self.record(bid, amount='50000').status_code, 201)
        self.assertEqual(self.booking(bid).status, 'PENDING_HOLD')
        self.assertEqual(self.record(bid, amount='70000', reference='PT-2').status_code, 201)
        self.assertEqual(self.booking(bid).status, 'CONFIRMED')

    def test_record_is_idempotent_by_reference_and_capped(self):
        bid = self.manual().json['data']['booking_id']
        self.assertEqual(self.record(bid, amount='130000').status_code, 422)
        self.assertEqual(self.record(bid, user=self.uc).status_code, 422)
        self.assertEqual(self.record(bid, amount='50000').status_code, 201)
        self.assertEqual(self.record(bid, amount='50000').status_code, 200)
        self.assertEqual(self.record(bid, amount='60000').status_code, 409)
        self.assertEqual(len(self.payments(bid)), 1)

    def test_record_rules(self):
        bid = self.manual().json['data']['booking_id']
        self.assertEqual(self.record(bid, method='VNPAY').status_code, 422)
        self.assertEqual(self.record(bid, kind='BOOKING_REMAINING_PAYMENT').status_code, 409)
        self.advance(seconds=300)
        self.assertEqual(self.record(bid).json['error']['code'], 'HOLD_EXPIRED')

    def test_cash_blocked_while_online_session_is_unresolved(self):
        data = self.hold()
        self.open_deposit(data['booking_id'])
        r = self.record(data['booking_id'], user=self.ua)
        self.assertEqual((r.status_code, r.json['error']['code']), (409, 'PAYMENT_RECONCILIATION_REQUIRED'))

    def test_remaining_cannot_exceed_outstanding(self):
        data = self.confirmed()
        self.assertEqual(self.record(data['booking_id'], amount='480001', kind='BOOKING_REMAINING_PAYMENT', user=self.ua).status_code, 422)
        self.assertEqual(self.record(data['booking_id'], amount='480000', kind='BOOKING_REMAINING_PAYMENT', user=self.ua).status_code, 201)

    def test_manual_cash_refund_completes_when_admin_hands_money_back(self):
        bid = self.manual().json['data']['booking_id']
        self.record(bid)
        pay = self.payments(bid)[0].payment_id
        self.client.post(f'/api/v1/admin/bookings/{bid}/cancel', headers=self.admin, json={'reason': 'Sự cố'})
        self.assertEqual(process_refunds(), 0)
        self.assertEqual(self.payments(bid)[1].status, 'REFUND_PROCESSING')
        r = self.client.post(f'/api/v1/admin/payments/{pay}/refund', headers=self.admin, json={'reason': 'Đã trả tiền mặt'})
        self.assertEqual((r.status_code, r.json['data']['status']), (200, 'SUCCESS'))
        self.assertEqual(self.payments(bid)[0].status, 'REFUNDED')
        self.assertEqual(self.client.post(f'/api/v1/admin/payments/{pay}/refund', headers=self.admin, json={'reason': 'Lặp'}).status_code, 200)
        self.assertEqual(len(self.payments(bid)), 2)

    def lock(self, index=8):
        start, end = self.slot(index=index)
        return self.client.post('/api/v1/admin/maintenance-locks', headers=self.admin, json=dict(pitch_id=1, start_time=start.isoformat(), end_time=end.isoformat(), reason='Bảo trì'))

    def test_maintenance_lock_blocks_then_releases(self):
        r = self.lock()
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual((r.json['data']['status'], r.json['data']['total_amount'], r.json['data']['booking_type']), ('MAINTENANCE', '0.00', 'MAINTENANCE_LOCK'))
        start, end = self.slot()
        attempt = lambda: self.client.post('/api/v1/bookings', headers=self.a, json=dict(pitch_id=1, start_time=start.isoformat(), end_time=end.isoformat()))
        self.assertEqual(attempt().status_code, 409)
        bid = r.json['data']['booking_id']
        self.assertEqual(self.client.get(f'/api/v1/admin/bookings/{bid}/balance', headers=self.admin).status_code, 404)
        self.assertEqual(self.client.post(f'/api/v1/bookings/{bid}/cancel', headers=self.admin, json={'reason': 'x'}).status_code, 409)
        r = self.client.post(f'/api/v1/admin/maintenance-locks/{bid}/cancel', headers=self.admin, json={'reason': 'Xong'})
        self.assertEqual(r.json['data']['status'], 'CANCELLED')
        self.assertEqual(attempt().status_code, 201)

    def test_maintenance_cannot_overwrite_a_customer(self):
        self.hold()
        self.assertEqual(self.lock().status_code, 409)
        customer = self.confirmed(self.b, index=2)['booking_id']
        self.assertEqual(self.client.post(f'/api/v1/admin/maintenance-locks/{customer}/cancel', headers=self.admin, json={'reason': 'x'}).status_code, 404)

    def reschedule(self, booking_id, index=9, **extra):
        start, end = self.slot(index=index)
        return self.client.patch(f'/api/v1/admin/bookings/{booking_id}', headers=self.admin, json=dict(start_time=start.isoformat(), end_time=end.isoformat(), reason='Khách đổi giờ', **extra))

    def test_reschedule_rules(self):
        data = self.confirmed()
        bid = data['booking_id']
        r = self.reschedule(bid)
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(self.booking(bid).start_time, self.slot(index=9)[0])
        self.assertEqual(self.booking(bid).total_amount, Decimal('600000.00'))
        self.assertEqual(self.reschedule(bid, pitch_id=2).status_code, 200)
        self.assertEqual(self.booking(bid).pitch_id, 2)
        r = self.reschedule(bid, pitch_id=3)
        self.assertEqual((r.status_code, r.json['error']['code']), (409, 'PRICE_CHANGE_REQUIRES_REBOOK'))
        self.confirmed(self.b, pitch_id=2, index=3)
        self.assertEqual(self.reschedule(bid, index=3).json['error']['code'], 'SLOT_UNAVAILABLE')
        self.assertEqual(self.reschedule(self.hold(self.c, index=5)['booking_id']).status_code, 409)
        start, end = self.slot(index=9)
        no_reason = self.client.patch(f'/api/v1/admin/bookings/{bid}', headers=self.admin, json=dict(start_time=start.isoformat(), end_time=end.isoformat()))
        self.assertEqual(no_reason.status_code, 422)

    def test_reschedule_moves_the_match_with_it(self):
        booking_id, match_id = self.match_booking()
        self.callback(self.open_deposit(booking_id, self.a))
        self.callback(self.open_deposit(booking_id, self.b))
        self.assertEqual(self.reschedule(booking_id, index=9).status_code, 200)
        with UnitOfWork() as ctx:
            match = ctx.session.get(Match, match_id)
            self.assertEqual(match.match_time, self.slot(index=9)[0])
            self.assertEqual(ctx.session.get(MatchPost, match.post_id).end_time, self.slot(index=9)[1])
        self.assertEqual(self.reschedule(booking_id, index=10, pitch_id=3).json['error']['code'], 'PRICE_CHANGE_REQUIRES_REBOOK')

    def phase(self, name):
        r = self.client.get(f'/api/v1/admin/bookings?phase={name}', headers=self.admin)
        self.assertEqual(r.status_code, 200, r.json)
        return [b['booking_id'] for b in r.json['data']]

    def test_phase_lists(self):
        data = self.confirmed(index=8)['booking_id']
        self.assertEqual(self.phase('UPCOMING'), [data])
        self.assertEqual(self.phase('IN_PROGRESS'), [])
        self.go_after(self.booking(data).start_time)
        self.assertEqual(self.phase('IN_PROGRESS'), [data])
        self.go_after(self.booking(data).end_time)
        self.assertEqual(self.phase('ENDED_UNPAID'), [data])
        self.assertEqual(self.phase('PAID'), [])
        self.client.post(f'/api/v1/admin/bookings/{data}/confirm-paid', headers=self.admin, json=dict(expected_outstanding='480000', idempotency_key='key-00001', receipts=[{'payment_method': 'CASH', 'amount': '480000'}]))
        self.assertEqual(self.phase('ENDED_UNPAID'), [])
        self.assertEqual(self.phase('PAID'), [data])

    def test_admin_list_row_and_filters(self):
        direct = self.confirmed()['booking_id']
        rows = self.client.get('/api/v1/admin/bookings?page_size=5', headers=self.admin).json
        self.assertEqual(rows['meta']['total'], 1)
        row = rows['data'][0]
        self.assertEqual((row['booking_id'], row['pitch_name'], row['teams']), (direct, 'Sân 5A', None))
        self.assertEqual(row['balance']['outstanding_amount'], '480000.00')
        self.assertEqual(self.client.get('/api/v1/admin/bookings?phase=WRONG', headers=self.admin).status_code, 422)
        self.assertEqual(self.client.get('/api/v1/admin/bookings?status=PAID', headers=self.admin).status_code, 422)
        self.assertEqual(self.client.get('/api/v1/admin/bookings?pitch_id=2', headers=self.admin).json['meta']['total'], 0)
        self.assertEqual(self.client.get('/api/v1/admin/bookings', headers=self.a).status_code, 403)

    def test_admin_list_shows_both_teams(self):
        self.match_booking()
        row = self.client.get('/api/v1/admin/bookings', headers=self.admin).json['data'][0]
        self.assertEqual(row['teams']['source']['representative_user_id'], self.ua)
        self.assertEqual(row['teams']['opponent']['representative_user_id'], self.ub)

class Reports(BookingCase):
    def day(self, offset=0):
        return (self.now.astimezone(VIETNAM).date() + timedelta(days=offset)).isoformat()

    def get(self, path, **query):
        query = {'from': self.day(-1), 'to': self.day(3), **query}
        return self.client.get(f'/api/v1/admin/{path}?' + urlencode(query), headers=self.admin)

    def test_receipt_then_refund_nets_zero_on_the_refund_day(self):
        data = self.confirmed()
        pay = self.payments(data['booking_id'])[0].payment_id
        paid_day = self.now.astimezone(VIETNAM).date().isoformat()
        self.client.post(f'/api/v1/admin/bookings/{data["booking_id"]}/cancel', headers=self.admin, json={'reason': 'Sự cố'})
        self.advance(days=2)
        process_refunds()
        report = self.client.get('/api/v1/admin/revenue?' + urlencode({'from': paid_day, 'to': self.day()}), headers=self.admin).json['data']
        self.assertEqual(report['totals'], {'gross_receipts': '120000.00', 'refunds': '120000.00', 'net_receipts': '0.00'})
        by_day = {i['period_start']: i for i in report['items']}
        self.assertEqual(by_day[paid_day]['net_receipts'], '120000.00')
        self.assertEqual(by_day[self.day()]['net_receipts'], '-120000.00')
        self.assertEqual(self.payments(data['booking_id'])[0].payment_id, pay)

    def test_vietnam_day_boundary_not_utc(self):
        with UnitOfWork() as ctx:
            from datetime import datetime
            late_utc = datetime(2026, 10, 30, 18, 30, tzinfo=timezone.utc)  # 01:30 on the 31st in Vietnam.
            ctx.session.add(Payment(user_id=self.ua, amount=100000, payment_type='BOOKING_DEPOSIT', payment_method='CASH', status='SUCCESS', paid_at=late_utc))
        report = self.client.get('/api/v1/admin/revenue/daily?from=2026-10-31&to=2026-10-31', headers=self.admin).json['data']
        self.assertEqual([i['period_start'] for i in report['items']], ['2026-10-31'])
        self.assertEqual(report['time_zone'], 'Asia/Ho_Chi_Minh')
        self.assertEqual(self.client.get('/api/v1/admin/revenue/daily?from=2026-10-30&to=2026-10-30', headers=self.admin).json['data']['items'], [])
        monthly = self.client.get('/api/v1/admin/revenue/monthly?from=2026-10-01&to=2026-10-31', headers=self.admin).json['data']
        self.assertEqual(monthly['items'][0]['period_start'], '2026-10-01')
        yearly = self.client.get('/api/v1/admin/revenue?period=year&from=2026-01-01&to=2026-12-31', headers=self.admin).json['data']
        self.assertEqual(yearly['items'][0]['period_start'], '2026-01-01')

    def test_forfeit_stays_in_receipts_and_pending_or_legacy_do_not_count(self):
        data = self.confirmed()
        self.client.post(f'/api/v1/bookings/{data["booking_id"]}/cancel', headers=self.a, json={'reason': 'Bận'})
        pending = self.hold(self.b, index=3)
        self.open_deposit(pending['booking_id'], self.b)
        with UnitOfWork() as ctx:
            ctx.session.add(Payment(user_id=self.ua, amount=999, payment_type='MATCH_HOST_DEPOSIT', payment_method='CASH', status='SUCCESS', paid_at=self.now))
        self.assertEqual(self.get('revenue').json['data']['totals']['net_receipts'], '120000.00')

    def test_range_validation_and_roles(self):
        self.assertEqual(self.client.get('/api/v1/admin/revenue', headers=self.admin).status_code, 422)
        self.assertEqual(self.client.get('/api/v1/admin/revenue?from=2026-02-01&to=2026-01-01', headers=self.admin).status_code, 422)
        self.assertEqual(self.client.get('/api/v1/admin/revenue?from=2024-01-01&to=2026-01-01', headers=self.admin).status_code, 422)
        self.assertEqual(self.client.get('/api/v1/admin/revenue?from=2026-01-01&to=2026-01-02&period=week', headers=self.admin).status_code, 422)
        self.assertEqual(self.client.get('/api/v1/admin/revenue?from=2026-01-01&to=2026-01-02', headers=self.a).status_code, 403)

    def test_transactions_filters_and_names(self):
        data = self.confirmed()
        r = self.get('transactions').json
        self.assertEqual(r['meta']['total'], 1)
        self.assertEqual((r['data'][0]['pitch_name'], r['data'][0]['booking_id']), ('Sân 5A', data['booking_id']))
        self.assertTrue(r['data'][0]['payer_name'])
        self.assertEqual(self.get('transactions', pitch_id=2).json['meta']['total'], 0)
        self.assertEqual(self.get('transactions', payment_type='REFUND').json['meta']['total'], 0)
        self.assertEqual(self.get('transactions', status='WRONG').status_code, 422)

    def test_statistics(self):
        confirmed = self.confirmed(index=4)['booking_id']
        self.hold(self.b, index=5)
        cancelled = self.confirmed(self.b, index=6)['booking_id']
        self.client.post(f'/api/v1/admin/bookings/{cancelled}/cancel', headers=self.admin, json={'reason': 'Sự cố'})
        process_refunds()
        start, end = self.slot(index=9)
        self.client.post('/api/v1/admin/maintenance-locks', headers=self.admin, json=dict(pitch_id=1, start_time=start.isoformat(), end_time=end.isoformat(), reason='x'))
        stats = self.get('booking-statistics').json['data']
        self.assertEqual((stats['total_bookings'], stats['confirmed_bookings'], stats['cancelled_bookings'], stats['refunded_booking_count']), (3, 1, 1, 1))
        self.assertEqual(stats['date_basis'], 'start_time')
        first = next(p for p in stats['by_pitch'] if p['pitch_id'] == 1)
        self.assertEqual(first['total_bookings'], 3)
        self.assertEqual(first['utilization_rate'], 0.0)
        hour = self.booking(confirmed).start_time.astimezone(VIETNAM).hour
        self.assertEqual(stats['peak_hours'], [{'hour': hour, 'booking_count': 1}])
        self.go_after(self.booking(confirmed).end_time)
        stats = self.client.get('/api/v1/admin/booking-statistics?' + urlencode({'from': self.day(), 'to': self.day(), 'pitch_id': 1}), headers=self.admin).json['data']
        self.assertGreater(stats['by_pitch'][0]['utilization_rate'], 0)

    def test_excel_matches_json_and_neutralises_formulas(self):
        data = self.hold()
        start_note = '=HYPERLINK("http://evil")'
        session = self.open_deposit(data['booking_id'])
        self.callback(session)
        with UnitOfWork() as ctx:
            ctx.session.get(Booking, data['booking_id']).note = start_note
        r = self.get('revenue/export')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('attachment', r.headers['Content-Disposition'])
        book = load_workbook(BytesIO(r.data))
        self.assertEqual(book.sheetnames, ['TongHop', 'GiaoDich', 'DatSan'])
        self.assertEqual(book['TongHop'].cell(book['TongHop'].max_row, 4).value, 120000)
        self.assertEqual(self.get('revenue').json['data']['totals']['net_receipts'], '120000.00')
        cell = book['DatSan'].cell(2, 10)
        self.assertEqual(cell.value, start_note)
        self.assertEqual(cell.data_type, 's')
        self.assertEqual(self.client.get('/api/v1/admin/revenue/export?from=2026-01-01&to=2026-01-02', headers=self.a).status_code, 403)
