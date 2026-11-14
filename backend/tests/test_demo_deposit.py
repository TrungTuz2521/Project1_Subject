from sqlalchemy import select
from booking_fixtures import BookingCase
from app.models import Match, Notification
from app.infrastructure.unit_of_work import UnitOfWork
from app.services.revenue_service import revenue_report
from app.utils.time import VIETNAM


class PersistedDemoDepositTests(BookingCase):
    def setUp(self):
        super().setUp()
        self.app.config['DEMO_PAYMENT_ENABLED'] = True

    def confirm(self,bid,header=None,**extra):
        return self.client.post('/api/v1/payments/deposit/demo-confirm',headers=header or self.a,json={'booking_id':bid,**extra})

    def test_direct_demo_persists_labelled_payment_and_retry_is_idempotent(self):
        bid=self.hold()['booking_id']
        first=self.confirm(bid)
        self.assertEqual(first.status_code,200,first.json)
        self.assertTrue(first.json['data']['demo'])
        self.assertTrue(first.json['data']['payment']['is_demo'])
        self.assertTrue(first.json['data']['booking']['is_demo'])
        self.assertEqual(first.json['data']['booking']['status'],'CONFIRMED')
        self.assertEqual(first.json['data']['payment']['amount'],'120000.00')
        self.advance(seconds=400)
        again=self.confirm(bid)
        self.assertEqual(again.status_code,200,again.json)
        self.assertEqual(first.json['data']['payment']['payment_id'],again.json['data']['payment']['payment_id'])
        self.assertEqual(len(self.payments(bid)),1)
        self.assertTrue(self.payments(bid)[0].note.startswith('DEMO_ONLY'))
        self.assertEqual(self.gateway.created,[])

    def test_two_captains_confirm_only_own_share_before_match_is_confirmed(self):
        bid,mid=self.match_booking()
        a=self.confirm(bid,self.a)
        self.assertEqual(a.json['data']['payment']['amount'],'60000.00')
        self.assertEqual(self.booking(bid).status,'PENDING_HOLD')
        with UnitOfWork() as ctx:self.assertEqual(ctx.session.get(Match,mid).status,'SUGGESTED')
        b=self.confirm(bid,self.b)
        self.assertEqual(b.json['data']['payment']['amount'],'60000.00')
        self.assertEqual(self.booking(bid).status,'CONFIRMED')
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.get(Match,mid).status,'CONFIRMED')
            notices=list(ctx.session.scalars(select(Notification).where(Notification.notification_type.in_(('PAYMENT_SUCCESS','MATCH_CONFIRMED')))))
            self.assertTrue(all('DEMO' in n.title for n in notices))

    def test_disabled_nonlocal_outsider_and_forged_fields_cannot_confirm(self):
        bid=self.hold()['booking_id']
        self.assertEqual(self.confirm(bid,self.b).status_code,404)
        self.assertEqual(self.confirm(bid,self.admin).status_code,403)
        self.assertEqual(self.confirm(bid,user_id=self.ub,amount='1').status_code,422)
        self.app.config['DEMO_PAYMENT_ENABLED']=False
        self.assertEqual(self.confirm(bid).status_code,403)
        self.app.config['DEMO_PAYMENT_ENABLED']=True
        self.assertEqual(self.client.post('/api/v1/payments/deposit/demo-confirm',headers=self.a,
            json={'booking_id':bid},environ_overrides={'REMOTE_ADDR':'10.0.0.5'}).status_code,403)
        self.assertEqual(self.payments(bid),[])

    def test_expired_and_unresolved_online_or_actual_receipts_are_not_mixed(self):
        bid=self.hold()['booking_id']
        self.advance(seconds=300)
        self.assertEqual(self.confirm(bid).json['error']['code'],'HOLD_EXPIRED')
        another=self.hold(index=7)['booking_id'];self.open_deposit(another)
        self.assertEqual(self.confirm(another).json['error']['code'],'PAYMENT_RECONCILIATION_REQUIRED')
        third=self.hold(index=6)['booking_id']
        paid=self.client.post('/api/v1/admin/payments/record',headers=self.admin,json=dict(booking_id=third,user_id=self.ua,
            amount='60000.00',payment_type='BOOKING_DEPOSIT',payment_method='BANK_TRANSFER',reference='TEST-REAL-RECEIPT'))
        self.assertEqual(paid.status_code,201,paid.json)
        self.assertEqual(self.confirm(third).status_code,409)

    def test_demo_is_excluded_from_actual_revenue_refunds_and_further_real_collection(self):
        bid=self.hold()['booking_id'];self.assertEqual(self.confirm(bid).status_code,200)
        day=self.now.astimezone(VIETNAM).date()
        with UnitOfWork() as ctx:
            self.assertEqual(str(revenue_report(ctx,day,day,'day')['totals']['gross_receipts']),'0.00')
        real=self.client.post('/api/v1/admin/payments/record',headers=self.admin,json=dict(booking_id=bid,user_id=self.ua,
            amount='1.00',payment_type='BOOKING_REMAINING_PAYMENT',payment_method='CASH',reference='NOT-REAL'))
        self.assertEqual(real.json['error']['code'],'DEMO_ONLY')
        self.assertEqual(self.client.post('/api/v1/payments/deposit',headers=self.a,
            json={'booking_id':bid,'payment_method':'VNPAY'}).json['error']['code'],'DEMO_ONLY')
        balance=self.client.get(f'/api/v1/admin/bookings/{bid}/balance',headers=self.admin).json['data']
        self.assertIsNone(balance['qr_payload'])
        cancelled=self.client.post(f'/api/v1/admin/bookings/{bid}/cancel',headers=self.admin,json={'reason':'Cancel DEMO'})
        self.assertEqual(cancelled.status_code,200,cancelled.json)
        self.assertFalse(any(p.payment_type=='REFUND' for p in self.payments(bid)))
