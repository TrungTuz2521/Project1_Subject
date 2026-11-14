from booking_fixtures import BookingCase
from app.models import Match
from app.infrastructure.unit_of_work import UnitOfWork
from app.services.booking_balance_service import crc16


class BankDepositTests(BookingCase):
    def setUp(self):
        super().setUp()
        self.app.config.update(BANK_NAME='Test Bank', BANK_ACCOUNT_NAME='TEST RECEIVER')

    def instructions(self, bid, header=None):
        return self.client.get(f'/api/v1/bookings/{bid}/deposit-instructions',headers=header or self.a)

    def record(self,bid,uid,amount,ref='TX-1',header=None):
        return self.client.post('/api/v1/admin/payments/record',headers=header or self.admin,json=dict(
            booking_id=bid,user_id=uid,amount=amount,payment_type='BOOKING_DEPOSIT',payment_method='BANK_TRANSFER',reference=ref))

    def test_qr_uses_own_amount_bank_and_reference_without_creating_payment_or_extending_hold(self):
        booking=self.hold();bid=booking['booking_id']
        data=self.instructions(bid).json['data'];payer=data['payers'][0]
        self.assertEqual(payer['due_amount'],'120000.00')
        self.assertEqual(data['account_no'],self.app.config['BANK_ACCOUNT_NO'])
        self.assertEqual(payer['transfer_reference'],f'COC{bid}U{self.ua}')
        self.assertTrue(payer['qr_payload'].endswith(crc16(payer['qr_payload'][:-4])))
        self.assertIn(self.app.config['BANK_ACCOUNT_NO'],payer['qr_payload'])
        self.assertIn('120000',payer['qr_payload'])
        self.assertEqual(self.payments(bid),[])
        self.advance(seconds=30)
        self.assertEqual(self.instructions(bid).json['data']['expires_at'],booking['hold_expires_at'])

    def test_only_payer_or_admin_sees_instructions_and_only_admin_records_receipt(self):
        bid=self.hold()['booking_id']
        self.assertEqual(self.instructions(bid,self.b).status_code,404)
        self.assertEqual(self.record(bid,self.ua,'120000.00',header=self.a).status_code,403)
        self.assertEqual(self.record(bid,self.ub,'120000.00').status_code,422)
        self.assertEqual(self.payments(bid),[])

    def test_two_teams_pay_own_ten_percent_then_match_confirms(self):
        bid,mid=self.match_booking()
        a=self.instructions(bid,self.a).json['data'];b=self.instructions(bid,self.b).json['data']
        self.assertEqual([p['user_id'] for p in a['payers']],[self.ua])
        self.assertEqual([p['user_id'] for p in b['payers']],[self.ub])
        self.assertEqual(a['payers'][0]['due_amount'],'60000.00')
        self.assertEqual(b['payers'][0]['due_amount'],'60000.00')
        self.assertEqual(len(self.instructions(bid,self.admin).json['data']['payers']),2)
        self.assertEqual(self.record(bid,self.ua,'60000.00','BANK-A').status_code,201)
        self.assertEqual(self.booking(bid).status,'PENDING_HOLD')
        with UnitOfWork() as ctx:self.assertEqual(ctx.session.get(Match,mid).status,'SUGGESTED')
        self.assertEqual(self.record(bid,self.ub,'60000.00','BANK-B').status_code,201)
        self.assertEqual(self.booking(bid).status,'CONFIRMED')
        with UnitOfWork() as ctx:self.assertEqual(ctx.session.get(Match,mid).status,'CONFIRMED')

    def test_partial_deposit_reduces_qr_and_overpayment_or_expiry_is_rejected(self):
        bid=self.hold()['booking_id']
        self.assertEqual(self.record(bid,self.ua,'60000.00').status_code,201)
        self.assertEqual(self.instructions(bid).json['data']['payers'][0]['due_amount'],'60000.00')
        self.assertEqual(self.record(bid,self.ua,'60001.00','TX-2').status_code,422)
        self.advance(seconds=300)
        self.assertIsNone(self.instructions(bid).json['data']['payers'][0]['qr_payload'])
        self.assertEqual(self.record(bid,self.ua,'60000.00','TX-3').json['error']['code'],'HOLD_EXPIRED')
        self.assertEqual(len(self.payments(bid)),1)

    def test_missing_config_and_unresolved_online_session_never_show_a_payable_qr(self):
        bid=self.hold()['booking_id']
        self.app.config['BANK_ACCOUNT_NAME']=''
        self.assertIsNone(self.instructions(bid).json['data']['payers'][0]['qr_payload'])
        self.app.config['BANK_ACCOUNT_NAME']='TEST RECEIVER'
        self.open_deposit(bid)
        item=self.instructions(bid).json['data']['payers'][0]
        self.assertIsNone(item['qr_payload']);self.assertFalse(item['can_confirm'])
        self.assertEqual(self.record(bid,self.ua,'120000.00').json['error']['code'],'PAYMENT_RECONCILIATION_REQUIRED')
