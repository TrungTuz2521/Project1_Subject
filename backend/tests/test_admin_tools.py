from booking_fixtures import BookingCase
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import User


class AdminToolsTests(BookingCase):
    def setUp(self):
        super().setUp()
        with UnitOfWork() as ctx:
            user = ctx.session.get(User, self.ua)
            user.full_name, user.phone = 'Nguyễn Văn An', '0912345678'

    def search(self, q, header=None, **args):
        return self.client.get('/api/v1/admin/users', headers=header or self.admin, query_string={'q': q, **args})

    def test_search_customer_by_name_email_or_phone(self):
        for q in ('văn an', 'U1@EXAMPLE', '0912345'):
            r = self.search(q)
            self.assertEqual(r.status_code, 200, r.json)
            self.assertEqual([u['user_id'] for u in r.json['data']], [self.ua], q)
        self.assertEqual(self.search('a').status_code, 422)
        self.assertEqual(self.search('example', header=self.a).status_code, 403)
        self.assertEqual(self.search('%_').json['data'], [])  # LIKE wildcards are matched literally.
        self.assertNotIn(self.uadmin, [u['user_id'] for u in self.search('example', role='PLAYER').json['data']])

    def test_admin_rows_show_customer_and_payer_names(self):
        bid = self.hold()['booking_id']
        [row] = self.client.get('/api/v1/admin/bookings', headers=self.admin).json['data']
        self.assertEqual(row['booking_id'], bid)
        self.assertEqual((row['customer']['full_name'], row['customer']['phone']), ('Nguyễn Văn An', '0912345678'))
        self.assertEqual(row['payer_progress'][0]['full_name'], 'Nguyễn Văn An')

    def test_dashboard_counts_what_needs_attention(self):
        self.hold(index=0)
        bid = self.hold(index=1)['booking_id']
        r = self.client.post('/api/v1/admin/payments/record', headers=self.admin, json=dict(
            booking_id=bid, user_id=self.ua, amount='120000.00', payment_type='BOOKING_DEPOSIT', payment_method='CASH', reference='R1'))
        self.assertEqual(r.status_code, 201, r.json)
        data = self.client.get('/api/v1/admin/dashboard', headers=self.admin).json['data']
        self.assertEqual(data['pending_holds']['count'], 1)
        self.assertEqual(data['pending_refunds']['count'], 0)
        self.assertEqual(data['ended_unpaid']['count'], 0)
        self.go_after(self.booking(bid).end_time)
        data = self.client.get('/api/v1/admin/dashboard', headers=self.admin).json['data']
        self.assertEqual((data['ended_unpaid']['count'], data['ended_unpaid']['outstanding_amount']), (1, '480000.00'))
        self.assertEqual(data['ended_unpaid']['items'][0]['customer']['full_name'], 'Nguyễn Văn An')
        self.assertIn('net_receipts', data['revenue_today'])
        self.assertEqual(self.client.get('/api/v1/admin/dashboard', headers=self.a).status_code, 403)

    def test_phase_filter_finds_old_unpaid_bookings(self):
        bid = self.hold(index=0)['booking_id']
        self.client.post('/api/v1/admin/payments/record', headers=self.admin, json=dict(
            booking_id=bid, user_id=self.ua, amount='120000.00', payment_type='BOOKING_DEPOSIT', payment_method='CASH', reference='R1'))
        self.go_after(self.booking(bid).end_time)
        r = self.client.get('/api/v1/admin/bookings', headers=self.admin, query_string={'phase': 'ENDED_UNPAID', 'page_size': 1})
        self.assertEqual(([b['booking_id'] for b in r.json['data']], r.json['meta']['total']), ([bid], 1))


class CreateAdminCommandTests(BookingCase):
    def run_cli(self, *args, password='AdminPass123!'):
        return self.app.test_cli_runner().invoke(args=['create-admin', *args], input=f'{password}\n{password}\n')

    def test_creates_admin_who_can_log_in_and_use_admin_api(self):
        result = self.run_cli('--email', 'Boss@Example.com', '--name', 'Chủ sân')
        self.assertEqual(result.exit_code, 0, result.output)
        login = self.client.post('/api/v1/auth/login', json={'email': 'boss@example.com', 'password': 'AdminPass123!'})
        self.assertEqual(login.status_code, 200, login.json)
        self.assertEqual(login.json['data']['user']['role'], 'ADMIN')
        token = {'Authorization': 'Bearer ' + login.json['data']['access_token']}
        self.assertEqual(self.client.get('/api/v1/admin/dashboard', headers=token).status_code, 200)

    def test_promotes_existing_player_and_revokes_old_token(self):
        result = self.run_cli('--email', 'u3@example.test')
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.client.get('/api/v1/users/me', headers=self.c).status_code, 401)
        login = self.client.post('/api/v1/auth/login', json={'email': 'u3@example.test', 'password': 'AdminPass123!'})
        self.assertEqual(login.json['data']['user']['role'], 'ADMIN')

    def test_rejects_short_password(self):
        result = self.run_cli('--email', 'x@example.com', password='short')
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('8-72', result.output)


class WalkInBookingTests(BookingCase):
    def counter(self, index=0, **who):
        start, end = self.slot(index=index)
        return self.client.post('/api/v1/admin/bookings', headers=self.admin, json=dict(
            pitch_id=1, start_time=start.isoformat(), end_time=end.isoformat(), note='Tai quay', **who))

    def test_walk_in_needs_only_name_and_phone_and_is_reused(self):
        r = self.counter(guest={'full_name': 'Lê Văn Khách', 'phone': '0987 654 321'})
        self.assertEqual(r.status_code, 201, r.json)
        guest_id = r.json['data']['user_id']
        self.assertIn('0987654321', r.json['data']['note'])
        again = self.counter(index=1, guest={'full_name': 'Lê Văn Khách (A)', 'phone': '0987654321'})
        self.assertEqual(again.json['data']['user_id'], guest_id)
        row = next(b for b in self.client.get('/api/v1/admin/bookings', headers=self.admin).json['data'] if b['booking_id'] == r.json['data']['booking_id'])
        self.assertEqual((row['customer']['walk_in'], row['customer']['phone'], row['customer']['email']), (True, '0987654321', None))
        found = self.client.get('/api/v1/admin/users', headers=self.admin, query_string={'q': '0987654'}).json['data']
        self.assertEqual([(u['user_id'], u['walk_in']) for u in found], [(guest_id, True)])

    def test_walk_in_cannot_log_in(self):
        guest_id = self.counter(guest={'full_name': 'Khách', 'phone': '0911222333'}).json['data']['user_id']
        from app.models import User
        with UnitOfWork() as ctx:
            email = ctx.session.get(User, guest_id).email
        self.assertTrue(email.endswith('@walkin.invalid'))
        self.assertEqual(self.client.post('/api/v1/auth/login', json={'email': email, 'password': 'whatever123'}).status_code, 401)

    def test_phone_of_a_real_account_points_admin_to_that_account(self):
        with UnitOfWork() as ctx:
            ctx.session.get(User, self.ua).phone = '0900000001'
        r = self.counter(guest={'full_name': 'Ai đó', 'phone': '0900000001'})
        self.assertEqual((r.status_code, r.json['error']['code']), (409, 'PHONE_BELONGS_TO_ACCOUNT'))
        self.assertIn('u1@example.test', r.json['error']['fields']['guest.phone'])

    def test_choose_exactly_one_kind_of_customer_and_valid_phone(self):
        self.assertEqual(self.counter().status_code, 422)
        self.assertEqual(self.counter(user_id=self.ua, guest={'full_name': 'X Y', 'phone': '0911222333'}).status_code, 422)
        self.assertEqual(self.counter(guest={'full_name': 'X Y', 'phone': '12ab'}).status_code, 422)
        self.assertEqual(self.counter(user_id=self.uadmin).status_code, 422)
        self.assertEqual(self.counter(user_id=self.ub).status_code, 201)

    def test_walk_in_who_registers_later_takes_the_phone(self):
        guest_id = self.counter(guest={'full_name': 'Khách', 'phone': '0911222333'}).json['data']['user_id']
        r = self.client.post('/api/v1/auth/register', json={'full_name': 'Khách Thật', 'email': 'khach@example.com',
                                                            'password': 'Password123!', 'phone': '0911222333'})
        self.assertEqual(r.status_code, 201, r.json)
        with UnitOfWork() as ctx:
            self.assertIsNone(ctx.session.get(User, guest_id).phone)
        # A real owner still blocks a second registration with the same phone.
        r = self.client.post('/api/v1/auth/register', json={'full_name': 'Người Khác', 'email': 'other@example.com',
                                                            'password': 'Password123!', 'phone': '0911222333'})
        self.assertEqual(r.json['error']['code'], 'PHONE_EXISTS')
