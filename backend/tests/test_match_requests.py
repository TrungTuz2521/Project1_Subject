"""Matchmaking by request: no public posts, the system pairs the best fits and tells both sides."""
from datetime import timedelta
from sqlalchemy import func, select
from booking_fixtures import BookingCase
from app.infrastructure.unit_of_work import UnitOfWork
from app.jobs.commands import close_requests, scan_requests
from app.models import Booking, MatchPost, Notification, Payment
from app.utils.time import VIETNAM


class MatchRequestTests(BookingCase):
    def day(self, days):
        return (self.now.astimezone(VIETNAM).date() + timedelta(days=days)).isoformat()

    def send(self, header, **data):
        return self.client.post('/api/v1/match-requests', headers=header, json=data)

    def view(self, header, rid):
        r = self.client.get(f'/api/v1/match-requests/{rid}', headers=header)
        self.assertEqual(r.status_code, 200, r.json)
        return r.json['data']

    def post(self, rid):
        with UnitOfWork() as ctx:
            return ctx.session.get(MatchPost, rid)

    def notices(self, uid, kind):
        with UnitOfWork() as ctx:
            return list(ctx.session.scalars(select(Notification).where(Notification.user_id == uid, Notification.notification_type == kind,
                                                                         Notification.delivery_channel == 'IN_APP')))

    def count(self, model, *where):
        with UnitOfWork() as ctx:
            return ctx.session.scalar(select(func.count()).select_from(model).where(*where))

    def cancel(self, header, rid):
        return self.client.post(f'/api/v1/match-requests/{rid}/cancel', headers=header, json={})

    # ---- creating a request

    def test_opponent_request_needs_two_days_a_full_team_and_the_captain(self):
        tid = self.team(self.a)
        base = dict(post_type='FIND_OPPONENT', team_id=tid, skill_level='INTERMEDIATE', payment_rule='SPLIT_EQUAL',
                    pitch_type='PITCH_5', window_start='17:00', window_end='21:00', player_count=5)
        r = self.send(self.a, **base, preferred_dates=[self.day(1)])
        self.assertEqual((r.status_code, list(r.json['error']['fields'])), (422, ['preferred_dates']))
        r = self.send(self.a, **{**base, 'player_count': 4}, preferred_dates=[self.day(2)])
        self.assertEqual((r.status_code, list(r.json['error']['fields'])), (422, ['player_count']))
        self.assertEqual(self.send(self.b, **base, preferred_dates=[self.day(2)]).status_code, 403)
        r = self.send(self.a, **base, preferred_dates=[self.day(2), self.day(3)])
        self.assertEqual((r.status_code, list(r.json['error']['fields'])), (422, ['preferred_dates']))  # one match day
        r = self.send(self.a, **base, preferred_dates=[self.day(3)])
        self.assertEqual(r.status_code, 201, r.json)
        data = r.json['data']
        self.assertEqual((data['status'], data['players'], data['skill_tolerance']), ('OPEN', 5, 1))
        # Slots inside 17:00-21:00 are 18:00 and 19:30; searching stops one day before the last one.
        last = self.slot(3, 9)[0]
        self.assertEqual(self.post(data['request_id']).expiry_time, last - timedelta(hours=24))

    def test_requests_are_not_listed_publicly(self):
        self.request_opponent(self.a)
        self.assertEqual(self.client.get('/api/v1/match-posts').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/match-requests/my', headers=self.b).json['meta']['total'], 0)

    def test_options_offer_captain_teams_and_eligible_bookings(self):
        tid = self.team(self.a)
        booking_id = self.confirmed(self.a, days=3)['booking_id']
        options = self.client.get('/api/v1/match-requests/options', headers=self.a).json['data']
        self.assertEqual([t['team_id'] for t in options['teams']], [tid])
        self.assertIsNone(options['teams'][0]['last_player_count'])
        self.assertEqual([b['booking_id'] for b in options['opponent_bookings']], [booking_id])
        self.assertEqual([b['booking_id'] for b in options['recruit_games']], [booking_id])
        self.request_opponent(self.a, booking_id=booking_id)
        options = self.client.get('/api/v1/match-requests/options', headers=self.a).json['data']
        self.assertEqual(options['opponent_bookings'], [])

    # ---- pairing

    def test_two_teams_without_a_pitch_get_one_held_and_pay_halves(self):
        booking_id, match_id = self.match_booking()
        rid = self.post_of(self.ua)
        data = self.view(self.a, rid)
        self.assertEqual(data['status'], 'MATCHED')
        match = data['match']
        self.assertEqual((match['match_id'], match['booking_id'], match['status']), (match_id, booking_id, 'SUGGESTED'))
        self.assertEqual((match['needs_deposit'], match['my_deposit'], match['opponent_deposit_paid']), (True, '60000.00', False))
        self.assertEqual(match['opponent']['captain']['user_id'], self.ub)
        self.assertEqual(match['pitch_name'], 'Sân 5A')
        self.assertEqual(len(self.notices(self.ua, 'BOOKING_HOLD')), 1)
        self.assertEqual(len(self.notices(self.ub, 'BOOKING_HOLD')), 1)
        self.assertIn('60.000 ₫', self.notices(self.ub, 'BOOKING_HOLD')[0].content)

    def post_of(self, uid):
        with UnitOfWork() as ctx:
            return ctx.session.scalar(select(MatchPost.post_id).where(MatchPost.creator_id == uid).order_by(MatchPost.post_id.desc()))

    def test_overlapping_windows_meet_on_a_common_slot(self):
        for header, window in ((self.a, ('17:00', '21:00')), (self.b, ('19:00', '23:00'))):
            r = self.send(header, post_type='FIND_OPPONENT', team_id=self.team(header), skill_level='INTERMEDIATE', payment_rule='SPLIT_EQUAL',
                          pitch_type='PITCH_5', preferred_dates=[self.day(2)], window_start=window[0], window_end=window[1], player_count=5)
            self.assertEqual(r.status_code, 201, r.json)
        match = self.latest_match()
        self.assertEqual(match.match_time.astimezone(VIETNAM).strftime('%H:%M'), '19:30')

    def test_skill_gap_and_payment_rule_must_fit_both_sides(self):
        ud = self.seed_user('u4@example.test')
        d = self.header(ud)
        strict = self.request_opponent(self.a, tolerance=0)
        self.request_opponent(self.b, skill='AMATEUR')
        self.request_opponent(self.c, rule='LOSER_PAYS_REMAINDER')
        self.assertIsNone(self.latest_match())
        self.request_opponent(d)
        match = self.latest_match()
        self.assertEqual({match.post_id, match.opponent_post_id}, {strict, self.post_of(ud)})

    def test_deposit_hold_lasts_twelve_hours(self):
        booking_id, _ = self.match_booking()
        with UnitOfWork() as ctx:
            booking = ctx.session.get(Booking, booking_id)
            self.assertLess(abs(booking.hold_expires_at - self.now - timedelta(hours=12)), timedelta(minutes=1))

    def test_no_payment_preference_takes_the_other_teams_rule(self):
        self.request_opponent(self.a, rule='ANY')
        self.request_opponent(self.b, rule='LOSER_PAYS_REMAINDER')
        match = self.latest_match()
        self.assertIsNotNone(match)
        with UnitOfWork() as ctx:
            self.assertEqual(ctx.session.get(Booking, match.booking_id).payment_rule, 'LOSER_PAYS_REMAINDER')
        self.assertIn('đội thua trả phần còn lại', self.notices(self.ua, 'BOOKING_HOLD')[0].content)

    def test_best_fit_is_paired_first(self):
        # Both A (one level apart) and C (same level) fit B; the scan pairs the closer level.
        ra = self.request_opponent(self.a, skill='AMATEUR')
        with UnitOfWork() as ctx:
            ctx.session.get(MatchPost, ra).status = 'LOCKED'  # keep A out of the instant scan when B arrives
        rb = self.request_opponent(self.b, tolerance=4)
        rc = self.request_opponent(self.c, tolerance=4)
        self.assertEqual({self.latest_match().post_id, self.latest_match().opponent_post_id}, {rb, rc})

    def test_booked_team_prefers_a_team_without_a_pitch_and_plays_on_its_booking(self):
        first = self.confirmed(self.a, days=3)['booking_id']
        second = self.confirmed(self.b, days=3, pitch_id=2)['booking_id']
        ra = self.request_opponent(self.a, booking_id=first)
        rb = self.request_opponent(self.b, booking_id=second)
        self.assertIsNone(self.latest_match())  # two booked teams wait for a team without a pitch first
        rc = self.request_opponent(self.c, days=3)
        match = self.latest_match()
        self.assertEqual((match.post_id, match.opponent_post_id, match.booking_id, match.status), (ra, rc, first, 'CONFIRMED'))
        self.assertEqual(self.count(Booking), 2)
        self.assertEqual(self.post(rb).status, 'OPEN')
        visitor = self.view(self.c, rc)['match']
        self.assertEqual((visitor['needs_deposit'], visitor['pitch_name']), (False, 'Sân 5A'))
        self.assertIn('Không cần đặt cọc thêm', self.notices(self.uc, 'MATCH_CONFIRMED')[0].content)

    def booked_pair(self):
        first = self.confirmed(self.a, days=3)['booking_id']
        second = self.confirmed(self.b, days=3, pitch_id=2)['booking_id']
        ra = self.request_opponent(self.a, booking_id=first)
        rb = self.request_opponent(self.b, booking_id=second)
        self.advance(hours=7)
        self.assertEqual(len(scan_requests()['matches']), 1)
        return first, second, ra, rb

    def test_two_booked_teams_merge_and_the_deposit_counts_towards_the_fee(self):
        first, second, ra, rb = self.booked_pair()
        match = self.latest_match()
        self.assertEqual((match.booking_id, match.status), (first, 'CONFIRMED'))
        self.assertEqual(self.booking(second).status, 'CANCELLED')
        moved = [p for p in self.payments(first) if p.user_id == self.ub]
        self.assertEqual([(p.payment_type, p.status, str(p.amount)) for p in moved], [('BOOKING_DEPOSIT', 'SUCCESS', '120000.00')])
        self.assertEqual(self.count(Payment, Payment.payment_type == 'REFUND'), 0)
        balance = self.client.get(f'/api/v1/bookings/{first}', headers=self.a).json['data']
        self.assertEqual((balance['paid_amount'], balance['outstanding_amount']), ('240000.00', '360000.00'))

    def test_owner_withdrawing_from_a_merged_game_refunds_the_other_team(self):
        first, second, ra, rb = self.booked_pair()
        self.assertEqual(self.cancel(self.a, ra).status_code, 200)
        self.assertEqual(self.post(ra).status, 'CANCELLED')
        reopened = self.post(rb)
        self.assertEqual((reopened.status, reopened.booking_id), ('OPEN', None))
        # booked_pair moves the clock 7 hours, which may cross midnight: compare with the booking's own day.
        self.assertEqual(reopened.preferred_dates, [self.booking(second).start_time.astimezone(VIETNAM).date().isoformat()])
        refund = [p for p in self.payments(first) if p.payment_type == 'REFUND']
        self.assertEqual([(p.user_id, p.status) for p in refund], [(self.ub, 'REFUND_PROCESSING')])
        self.assertEqual(self.booking(first).status, 'CONFIRMED')

    def test_visiting_team_withdrawing_from_a_merged_game_forfeits_its_deposit(self):
        first, second, ra, rb = self.booked_pair()
        self.assertEqual(self.cancel(self.b, rb).status_code, 200)
        self.assertEqual(self.post(ra).status, 'OPEN')
        self.assertEqual([p.user_id for p in self.payments(first) if p.payment_type == 'BOOKING_DEPOSIT'], [self.ua])
        self.assertEqual([p.user_id for p in self.payments(second)], [self.ub])
        self.assertEqual(self.count(Payment, Payment.payment_type == 'REFUND'), 0)

    # ---- cut-off and cancelling

    def test_search_stops_one_day_before_and_the_booking_is_kept(self):
        booking_id = self.confirmed(self.a, days=3)['booking_id']
        rid = self.request_opponent(self.a, booking_id=booking_id)
        self.go_after(self.post(rid).expiry_time)
        self.assertEqual(close_requests(), 1)
        self.assertEqual(close_requests(), 0)
        self.assertEqual(self.post(rid).status, 'EXPIRED')
        notice = self.notices(self.ua, 'POST_EXPIRED')
        self.assertEqual(len(notice), 1)
        self.assertIn('vẫn giữ', notice[0].content)
        self.assertEqual(self.booking(booking_id).status, 'CONFIRMED')

    def test_visiting_team_withdraws_and_the_pitch_owner_searches_again(self):
        booking_id = self.confirmed(self.a, days=3)['booking_id']
        ra = self.request_opponent(self.a, booking_id=booking_id)
        rc = self.request_opponent(self.c, days=3)
        self.assertEqual(self.cancel(self.c, rc).status_code, 200)
        self.assertEqual((self.post(rc).status, self.post(ra).status, self.latest_match().status), ('CANCELLED', 'OPEN', 'CANCELLED'))
        self.assertEqual(self.booking(booking_id).status, 'CONFIRMED')
        self.assertTrue(self.notices(self.ua, 'MATCH_CANCELLED'))
        # Another team can now take the same game.
        rb = self.request_opponent(self.b, days=3)
        match = self.latest_match()
        self.assertEqual((match.post_id, match.opponent_post_id, match.status), (ra, rb, 'CONFIRMED'))

    def test_withdrawing_less_than_a_day_before_goes_through_the_counter(self):
        booking_id = self.confirmed(self.a, days=3)['booking_id']
        self.request_opponent(self.a, booking_id=booking_id)
        rc = self.request_opponent(self.c, days=3)
        self.go_after(self.booking(booking_id).start_time - timedelta(hours=23))
        r = self.cancel(self.c, rc)
        self.assertEqual((r.status_code, r.json['error']['code']), (409, 'TOO_LATE'))

    def test_cancelling_the_booking_releases_the_opponent(self):
        booking_id = self.confirmed(self.a, days=3)['booking_id']
        ra = self.request_opponent(self.a, booking_id=booking_id)
        rc = self.request_opponent(self.c, days=3)
        r = self.client.post(f'/api/v1/bookings/{booking_id}/cancel', headers=self.a, json={'reason': 'Bận'})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual((self.post(ra).status, self.post(rc).status), ('CANCELLED', 'OPEN'))
        self.assertIsNone(self.post(rc).match_time)

    def test_open_request_can_be_widened_and_then_matches(self):
        ra = self.request_opponent(self.a, days=2)
        rb = self.request_opponent(self.b, days=3)
        self.assertIsNone(self.latest_match())
        r = self.client.patch(f'/api/v1/match-requests/{ra}', headers=self.a, json={'preferred_dates': [self.day(3)]})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json['data']['status'], 'MATCHED')
        self.assertEqual({self.latest_match().post_id, self.latest_match().opponent_post_id}, {ra, rb})

    # ---- extra players

    def recruit(self, header, booking_id, needed=3, **extra):
        r = self.send(header, post_type='RECRUIT_MEMBERS', booking_id=booking_id, required_players=needed, skill_level='INTERMEDIATE', **extra)
        self.assertEqual(r.status_code, 201, r.json)
        return r.json['data']['request_id']

    def join(self, header, size=1, days=2):
        r = self.send(header, post_type='LOOK_FOR_TEAM', party_size=size, skill_level='INTERMEDIATE', pitch_type='PITCH_5',
                      preferred_dates=[self.day(days)], window_start='17:00', window_end='21:00')
        self.assertEqual(r.status_code, 201, r.json)
        return r.json['data']['request_id']

    def test_players_join_a_game_that_needs_people(self):
        booking_id = self.confirmed(self.a, days=2)['booking_id']
        rr = self.recruit(self.a, booking_id, fee_per_player='50000')
        rb = self.join(self.b, size=2)
        self.assertEqual((self.post(rb).status, self.post(rr).status, self.post(rr).required_players), ('MATCHED', 'OPEN', 1))
        joined = self.view(self.b, rb)['joined_game']
        self.assertEqual((joined['captain']['user_id'], joined['fee_per_player'], joined['pitch_name']), (self.ua, '50000.00', 'Sân 5A'))
        self.assertEqual(self.view(self.a, rr)['joiners'][0]['party_size'], 2)
        self.assertEqual(len(self.notices(self.ua, 'TEAM_JOINED')), 1)
        rc = self.join(self.c, size=2)
        self.assertEqual(self.post(rc).status, 'OPEN')  # only one place left
        self.assertEqual(self.cancel(self.b, rb).status_code, 200)
        self.assertEqual(self.post(rr).required_players, 3)
        scan_requests()
        self.assertEqual((self.post(rc).status, self.post(rr).required_players), ('MATCHED', 1))

    def test_filling_every_place_closes_the_recruit_request(self):
        booking_id = self.confirmed(self.a, days=2)['booking_id']
        rr = self.recruit(self.a, booking_id, needed=1)
        self.join(self.b)
        self.assertEqual(self.post(rr).status, 'MATCHED')

    def test_join_needs_a_slot_more_than_a_day_ahead(self):
        r = self.send(self.b, post_type='LOOK_FOR_TEAM', party_size=1, skill_level='INTERMEDIATE',
                      preferred_dates=[self.day(0)], window_start='06:00', window_end='23:00')
        self.assertEqual((r.status_code, list(r.json['error']['fields'])), (422, ['preferred_dates']))

    def test_only_a_player_of_the_game_can_recruit_for_it(self):
        booking_id = self.confirmed(self.a, days=2)['booking_id']
        r = self.send(self.b, post_type='RECRUIT_MEMBERS', booking_id=booking_id, required_players=2, skill_level='INTERMEDIATE')
        self.assertEqual((r.status_code, list(r.json['error']['fields'])), (422, ['booking_id']))

    def test_admin_lists_every_request_with_the_requester(self):
        self.request_opponent(self.a)
        r = self.client.get('/api/v1/admin/match-requests', headers=self.admin)
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json['data'][0]['requester']['user_id'], self.ua)
        self.assertEqual(self.client.get('/api/v1/admin/match-requests', headers=self.a).status_code, 403)


class TeamTests(BookingCase):
    def test_a_team_is_only_its_captain_and_remembers_the_last_head_count(self):
        rid = self.request_opponent(self.a)
        with UnitOfWork() as ctx:
            tid = ctx.session.get(MatchPost, rid).team_id
        teams = self.client.get('/api/v1/teams', headers=self.a).json['data']
        self.assertEqual([(t['team_id'], t['last_player_count']) for t in teams], [(tid, 5)])
        options = self.client.get('/api/v1/match-requests/options', headers=self.a).json['data']
        self.assertEqual(options['teams'][0]['last_player_count'], 5)
        self.assertNotIn('members', self.client.get(f'/api/v1/teams/{tid}', headers=self.a).json['data'])
        self.assertEqual(self.client.get(f'/api/v1/teams/{tid}', headers=self.b).status_code, 404)
