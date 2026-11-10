import unittest
from unittest.mock import patch
from datetime import timedelta
from sqlalchemy import select, func
from app import create_app
from app.extensions import db
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import User, MatchPost, MatchProposal, Booking, Match
from app.utils.time import utcnow


class MatchmakingWorkerTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                              'JWT_SECRET_KEY': 'worker-test-only-secret-at-least-32-bytes'})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()

    def test_real_repeated_ticks_create_one_proposal_without_booking_or_match(self):
        with UnitOfWork() as ctx:
            for i in range(2):
                user = User(full_name=f'Captain {i}', email=f'worker{i}@example.test')
                ctx.session.add(user)
                ctx.session.flush()
                ctx.session.add(MatchPost(creator_id=user.user_id, post_type='FIND_OPPONENT',
                    title='Find opponent', skill_level='INTERMEDIATE', pitch_type='PITCH_5',
                    payment_rule='SPLIT_EQUAL', match_time=utcnow().replace(hour=11, minute=0, second=0, microsecond=0) + timedelta(days=1),
                    end_time=utcnow().replace(hour=12, minute=30, second=0, microsecond=0) + timedelta(days=1),
                    expiry_time=utcnow() + timedelta(hours=1), current_players=5,
                    attendance_plan={'user_ids': [user.user_id], 'guest_players': 4}))
        with patch('app.jobs.matchmaking_worker.sleep', side_effect=[None, KeyboardInterrupt]):
            result = self.app.test_cli_runner().invoke(args=['matchmaking-worker'])
        self.assertEqual(result.exit_code, 1)  # Ctrl+C exits the continuous command.
        self.assertIn('every 15s', result.output)
        self.assertEqual(db.session.scalar(select(func.count()).select_from(MatchProposal)), 1)
        self.assertEqual(db.session.scalar(select(func.count()).select_from(Booking)), 0)
        self.assertEqual(db.session.scalar(select(func.count()).select_from(Match)), 0)

    def test_failed_tick_recovers_and_does_not_print_exception_details(self):
        with patch('app.jobs.matchmaking_worker.scan_open_posts', side_effect=[
                RuntimeError('SECRET-MUST-NOT-BE-LOGGED'), {'scanned_count': 0, 'created_proposal_ids': []}]) as scan, \
             patch('app.jobs.matchmaking_worker.monotonic', side_effect=[0, 2, 15, 18]), \
             patch('app.jobs.matchmaking_worker.sleep', side_effect=[None, KeyboardInterrupt]) as sleep, \
             self.assertLogs(self.app.logger, level='WARNING') as logs:
            self.app.test_cli_runner().invoke(args=['matchmaking-worker'])
        self.assertEqual(scan.call_count, 2)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [13, 12])
        self.assertNotIn('SECRET-MUST-NOT-BE-LOGGED', str(logs.output))

    def test_slow_scan_never_requests_negative_sleep(self):
        with patch('app.jobs.matchmaking_worker.scan_open_posts', return_value={'scanned_count': 0, 'created_proposal_ids': []}), \
             patch('app.jobs.matchmaking_worker.monotonic', side_effect=[0, 20]), \
             patch('app.jobs.matchmaking_worker.sleep', side_effect=KeyboardInterrupt) as sleep:
            self.app.test_cli_runner().invoke(args=['matchmaking-worker'])
        sleep.assert_called_once_with(0)

    def test_interval_validation_precedes_any_scan(self):
        with patch('app.jobs.matchmaking_worker.scan_open_posts') as scan:
            result = self.app.test_cli_runner().invoke(args=['matchmaking-worker', '--interval', '0'])
        self.assertEqual(result.exit_code, 2)
        scan.assert_not_called()
