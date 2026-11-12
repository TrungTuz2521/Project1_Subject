from datetime import timedelta
from decimal import Decimal
from booking_fixtures import BookingCase
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Booking, Pitch
from app.utils.time import VIETNAM


class CounterOperationsTests(BookingCase):
    """Counter work the venue owner asked for: peak prices, regulars, cancellations, check-in, pitch warnings, sessions."""

    def counter(self, index=8, days=1, **extra):
        start, end = self.slot(days, index)
        body = dict(pitch_id=1, start_time=start.isoformat(), end_time=end.isoformat(), note='Tai quay', **extra)
        body.setdefault('guest', {'full_name': 'Anh Minh', 'phone': '0988111222'})
        if body['guest'] is None:
            body.pop('guest')
        return self.client.post('/api/v1/admin/bookings', headers=self.admin, json=body)

    def set_peak(self, start='17:00', end='21:00', weekend=False):
        return self.client.patch('/api/v1/admin/field-complex', headers=self.admin,
                                 json=dict(peak_start_time=start, peak_end_time=end, weekend_is_peak=weekend))

    def cancel(self, booking_id, cause):
        return self.client.post(f'/api/v1/admin/bookings/{booking_id}/cancel', headers=self.admin, json={'reason': 'Khách báo bận', 'cause': cause})

    # ---- b. Peak prices ----
    def test_peak_price_is_shown_per_slot_and_fixed_on_the_booking(self):
        self.assertEqual(self.set_peak().status_code, 200)
        self.assertEqual(self.client.patch('/api/v1/admin/pitches/1', headers=self.admin, json={'peak_price_per_slot': '800000'}).status_code, 200)
        day = self.slot(1, 0)[0].astimezone(VIETNAM).date().isoformat()
        slots = self.client.get('/api/v1/pitches/1/availability', query_string={'date': day}).json['data']['slots']
        by_time = {s['start_time'][11:16]: (s['price'], s['is_peak']) for s in slots}
        # 18:00 local = 11:00Z is peak; 06:00 local = 23:00Z of the day before is normal.
        self.assertEqual(by_time['11:00'], ('800000.00', True))
        self.assertEqual(by_time['23:00'], ('600000.00', False))
        peak = self.counter(index=8)   # 18:00
        normal = self.counter(index=0) # 06:00
        self.assertEqual((peak.json['data']['total_amount'], peak.json['data']['deposit_amount']), ('800000.00', '160000.00'))
        self.assertEqual(normal.json['data']['total_amount'], '600000.00')
        # Raising the price later never changes what an existing booking owes.
        self.client.patch('/api/v1/admin/pitches/1', headers=self.admin, json={'peak_price_per_slot': '900000'})
        self.assertEqual(self.booking(peak.json['data']['booking_id']).total_amount, Decimal('800000.00'))

    def test_weekend_all_day_peak_and_invalid_windows(self):
        self.client.patch('/api/v1/admin/pitches/1', headers=self.admin, json={'peak_price_per_slot': '700000'})
        self.assertEqual(self.set_peak(None, None, True).status_code, 200)
        with UnitOfWork() as ctx:
            from app.services.pricing import slot_price
            pitch = ctx.session.get(Pitch, 1)
            base = self.now.astimezone(VIETNAM)
            saturday = (base + timedelta(days=(5 - base.weekday()) % 7 or 7)).replace(hour=8, minute=0, second=0, microsecond=0)
            self.assertEqual(slot_price(ctx, pitch, saturday), (Decimal('700000.00'), True))
            self.assertEqual(slot_price(ctx, pitch, saturday - timedelta(days=2)), (Decimal('600000.00'), False))
        self.assertEqual(self.set_peak('21:00', '17:00').status_code, 422)
        self.assertEqual(self.set_peak('5:00', '9:00').status_code, 422)
        self.assertEqual(self.set_peak('05:00', '09:00').status_code, 422)  # before opening
        self.assertEqual(self.client.patch('/api/v1/admin/field-complex', headers=self.a, json=dict(peak_start_time=None, peak_end_time=None, weekend_is_peak=False)).status_code, 403)
        policy = self.client.get('/api/v1/field-complex').json['data']['policy']
        self.assertEqual((policy['peak_start_time'], policy['weekend_is_peak']), (None, True))

    def test_reschedule_into_a_different_price_is_refused(self):
        self.set_peak()
        self.client.patch('/api/v1/admin/pitches/1', headers=self.admin, json={'peak_price_per_slot': '800000'})
        bid = self.counter(index=0).json['data']['booking_id']  # normal price
        start, end = self.slot(1, 8)  # peak
        r = self.client.patch(f'/api/v1/admin/bookings/{bid}', headers=self.admin, json=dict(start_time=start.isoformat(), end_time=end.isoformat(), reason='Đổi giờ'))
        self.assertEqual(r.json['error']['code'], 'PRICE_CHANGE_REQUIRES_REBOOK')

    # ---- a. Regular customers ----
    def test_weekly_regular_books_ahead_skips_taken_weeks_and_cancels_together(self):
        first = self.counter(index=8, days=2, repeat_weeks=6)
        self.assertEqual(first.status_code, 201, first.json)
        series = first.json['data']['series']
        self.assertEqual((len(series['created']), series['skipped']), (6, []))
        # Weeks 5 and 6 are ~5 weeks ahead: beyond the 10-day online limit, allowed at the counter.
        self.assertGreater(series['created'][-1]['start_time'], (self.now + timedelta(days=30)).isoformat())
        # The first requested session must exist: another regular cannot start on a taken slot.
        with UnitOfWork() as ctx:
            ctx.session.get(Booking, series['created'][2]['booking_id']).status = 'CANCELLED'
        second = self.counter(index=8, days=2, repeat_weeks=3, guest={'full_name': 'Đội B', 'phone': '0911000222'})
        self.assertEqual(second.status_code, 409)
        listed = self.client.get('/api/v1/admin/bookings', headers=self.admin, query_string={'series_id': series['series_id']}).json['data']
        self.assertEqual(len(listed), 6)
        self.assertTrue(all(b['series_id'] == series['series_id'] and b['status'] in ('CONFIRMED', 'CANCELLED') for b in listed))
        r = self.client.post(f"/api/v1/admin/bookings/series/{series['series_id']}/cancel", headers=self.admin, json={'reason': 'Đội nghỉ giải'})
        self.assertEqual((r.status_code, len(r.json['data']['cancelled'])), (200, 5), r.json)
        self.assertEqual(self.client.post(f"/api/v1/admin/bookings/series/{series['series_id']}/cancel", headers=self.admin, json={'reason': 'x lần 2'}).status_code, 404)

    def test_series_reports_weeks_already_taken(self):
        start, end = self.slot(2, 8)
        week3 = start + timedelta(weeks=2)
        with UnitOfWork() as ctx:
            ctx.session.add(Booking(pitch_id=1, user_id=self.ub, start_time=week3, end_time=week3 + timedelta(minutes=90), total_amount=600000,
                                    deposit_amount=120000, booking_type='MANUAL_ADMIN', status='CONFIRMED', payer_plan=[]))
        r = self.counter(index=8, days=2, repeat_weeks=4)
        series = r.json['data']['series']
        self.assertEqual((len(series['created']), len(series['skipped'])), (3, 1))
        self.assertEqual(series['skipped'][0]['start_time'][:10], week3.isoformat()[:10])
        self.assertEqual(self.counter(index=6, repeat_weeks=13).status_code, 422)

    # ---- d. Customer cancels: deposit kept ----
    def test_customer_cancel_keeps_the_deposit_and_refunds_the_rest(self):
        bid = self.counter(payment={'amount': '600000', 'payment_method': 'CASH'}).json['data']['booking_id']
        r = self.cancel(bid, 'CUSTOMER')
        self.assertEqual(r.status_code, 200, r.json)
        summary = r.json['data']['refund_summary']
        self.assertEqual((summary['cause'], summary['forfeited_amount'], summary['refund_amount']), ('USER_CANCEL', '120000.00', '480000.00'))
        pending = self.client.get('/api/v1/admin/refunds/pending', headers=self.admin).json['data']
        self.assertEqual([p['amount'] for p in pending], ['480000.00'])

    def test_venue_cancel_refunds_everything(self):
        bid = self.counter(payment={'amount': '120000', 'payment_method': 'CASH'}).json['data']['booking_id']
        summary = self.cancel(bid, 'VENUE').json['data']['refund_summary']
        self.assertEqual((summary['cause'], summary['refund_amount'], summary['forfeited_amount']), ('ADMIN_INCIDENT', '120000.00', '0.00'))
        self.assertEqual(self.cancel(self.counter(index=7).json['data']['booking_id'], 'OTHER').status_code, 422)

    def test_customer_cancel_is_refused_for_a_two_team_match(self):
        bid, _ = self.match_booking()
        self.assertEqual(self.cancel(bid, 'CUSTOMER').status_code, 409)

    # ---- g. Counter check-in ----
    def test_check_in_window_no_show_and_history(self):
        bid = self.counter().json['data']['booking_id']
        start = self.booking(bid).start_time
        arrive = lambda status: self.client.post(f'/api/v1/admin/bookings/{bid}/arrival', headers=self.admin, json={'status': status})
        self.assertEqual(arrive('ARRIVED').status_code, 409)  # a day early
        self.now = start - timedelta(minutes=30)
        self.assertEqual(arrive('NO_SHOW').status_code, 409)  # not started yet
        r = arrive('ARRIVED')
        self.assertEqual((r.status_code, r.json['data']['arrival_status']), (200, 'ARRIVED'))
        self.assertIsNotNone(r.json['data']['arrived_at'])
        self.assertEqual(arrive(None).json['data']['arrival_status'], None)
        self.now = start + timedelta(minutes=20)
        self.assertEqual(arrive('NO_SHOW').json['data']['arrival_status'], 'NO_SHOW')
        row = next(b for b in self.client.get('/api/v1/admin/bookings', headers=self.admin).json['data'] if b['booking_id'] == bid)
        self.assertEqual(row['customer']['no_show_count'], 1)
        found = self.client.get('/api/v1/admin/users', headers=self.admin, query_string={'q': '0988111'}).json['data']
        self.assertEqual(found[0]['no_show_count'], 1)
        self.assertEqual(self.client.post(f'/api/v1/admin/bookings/{bid}/arrival', headers=self.a, json={'status': 'ARRIVED'}).status_code, 403)

    def test_due_today_lists_what_the_counter_must_collect(self):
        # Pin the clock to 05:00 local so today's evening slots are still ahead whenever the suite runs.
        self.now = self.now.astimezone(VIETNAM).replace(hour=5, minute=0, second=0, microsecond=0).astimezone(self.now.tzinfo)
        today = self.counter(days=0, index=10).json['data']['booking_id']   # 21:00 today
        tomorrow = self.counter(days=1).json['data']['booking_id']
        paid = self.counter(days=0, index=9, payment={'amount': '600000', 'payment_method': 'CASH'}).json['data']['booking_id']
        due = [b['booking_id'] for b in self.client.get('/api/v1/admin/bookings', headers=self.admin, query_string={'phase': 'DUE'}).json['data']]
        self.assertIn(today, due)
        self.assertNotIn(tomorrow, due)
        self.assertNotIn(paid, due)

    # ---- i. Taking a pitch out of service ----
    def test_pitch_out_of_service_warns_about_upcoming_bookings(self):
        bid = self.counter().json['data']['booking_id']
        r = self.client.patch('/api/v1/admin/pitches/1', headers=self.admin, json={'status': 'MAINTENANCE'})
        self.assertEqual((r.status_code, r.json['error']['code']), (409, 'PITCH_HAS_BOOKINGS'))
        self.assertIn(f'#{bid}', r.json['error']['fields']['status'])
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.get(Pitch, 1).status, 'ACTIVE')
        r = self.client.patch('/api/v1/admin/pitches/1', headers=self.admin, json={'status': 'MAINTENANCE', 'confirm': True})
        self.assertEqual(r.json['data']['status'], 'MAINTENANCE')
        self.assertEqual(self.booking(bid).status, 'CONFIRMED')  # bookings are never silently changed

    # ---- e. Sessions stay alive while in use ----
    def test_refresh_issues_a_new_token_and_respects_revocation(self):
        r = self.client.post('/api/v1/auth/refresh', headers=self.admin)
        self.assertEqual(r.status_code, 200, r.json)
        token = {'Authorization': 'Bearer ' + r.json['data']['access_token']}
        self.assertEqual(self.client.get('/api/v1/users/me', headers=token).status_code, 200)
        self.assertEqual(self.client.post('/api/v1/auth/refresh').status_code, 401)
        with UnitOfWork() as ctx:
            from app.models import User
            ctx.session.get(User, self.uadmin).password_hash = 'changed'
        self.assertEqual(self.client.post('/api/v1/auth/refresh', headers=token).json['error']['code'], 'SESSION_REVOKED')

    # Client sync: a customer with an account sees counter bookings with the money already paid.
    def test_customer_sees_counter_booking_paid_and_due(self):
        r = self.counter(guest=None, user_id=self.ua, payment={'amount': '120000', 'payment_method': 'CASH'})
        mine = self.client.get('/api/v1/bookings/my', headers=self.a).json['data']
        row = next(b for b in mine if b['booking_id'] == r.json['data']['booking_id'])
        self.assertEqual((row['status'], row['paid_amount'], row['outstanding_amount'], row['pitch_name']),
                         ('CONFIRMED', '120000.00', '480000.00', 'Sân 5A'))
