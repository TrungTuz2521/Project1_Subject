import unittest
from unittest.mock import patch
from sqlalchemy import select, func
from app import create_app
from app.extensions import db
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import User, Notification
from app.services.notification_service import notify
from app.services.email_service import process_emails, claim_email, check_connection, send_email


class EmailTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'JWT_SECRET_KEY': 'email-test-only-secret-at-least-32-bytes', 'EMAIL_ENABLED': True,
            'SMTP_USERNAME': 'sender@gmail.com', 'SMTP_PASSWORD': 'test-not-real',
            'SMTP_HOST': 'smtp.gmail.com', 'SMTP_PORT': 587, 'PUBLIC_WEB_URL': 'http://localhost:5173'})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        with UnitOfWork() as ctx:
            user = User(full_name='Recipient', email='recipient@gmail.com', status='ACTIVE')
            ctx.session.add(user)
            ctx.session.flush()
            self.uid = user.user_id

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()

    def enqueue(self, kind='MATCH_CONFIRMED'):
        with UnitOfWork() as ctx:
            notify(ctx, [self.uid, self.uid], kind, 'Thông báo', 'Kiểm tra trạng thái trong app.')
        return db.session.scalar(select(Notification.notification_id).where(Notification.delivery_channel == 'EMAIL'))

    def row(self, nid):
        db.session.expire_all()
        return db.session.get(Notification, nid)

    @patch('app.services.email_service.send_email')
    def test_queue_same_transaction_and_no_inline_network(self, smtp):
        nid = self.enqueue()
        self.assertEqual(db.session.scalar(select(func.count()).select_from(Notification)), 2)
        self.assertEqual(self.row(nid).delivery_status, 'PENDING')
        self.assertIsNone(self.row(nid).sent_at)
        smtp.assert_not_called()
        with self.assertRaises(RuntimeError):
            with UnitOfWork() as ctx:
                notify(ctx, [self.uid], 'PAYMENT_SUCCESS', 'Rollback', 'Never send')
                raise RuntimeError('rollback')
        self.assertEqual(db.session.scalar(select(func.count()).select_from(Notification)), 2)

    @patch('app.services.email_service.send_email')
    def test_send_after_commit_claim_once_and_no_resend(self, smtp):
        nid = self.enqueue()
        def check_claim(*args):
            with UnitOfWork() as ctx:
                self.assertEqual(ctx.session.get(Notification, nid).delivery_status, 'FAILED')
            self.assertIsNone(claim_email(nid))
        smtp.side_effect = check_claim
        self.assertEqual(process_emails(), {'sent': 1, 'failed': 0, 'skipped': 0})
        self.assertEqual(self.row(nid).delivery_status, 'SENT')
        self.assertIsNotNone(self.row(nid).sent_at)
        self.assertEqual(process_emails()['sent'], 0)
        smtp.assert_called_once()

    @patch('app.services.email_service.send_email', side_effect=TimeoutError)
    def test_failed_delivery_never_claims_sent_or_automatically_retries(self, smtp):
        nid = self.enqueue()
        self.assertEqual(process_emails()['failed'], 1)
        self.assertEqual(self.row(nid).delivery_status, 'FAILED')
        self.assertIsNone(self.row(nid).sent_at)
        process_emails()
        smtp.assert_called_once()

    @patch('app.services.email_service.send_email')
    def test_disabled_config_does_not_queue_or_consume(self, smtp):
        self.app.config['EMAIL_ENABLED'] = False
        self.enqueue()
        self.assertEqual(db.session.scalar(select(func.count()).select_from(Notification)), 1)
        self.app.config['EMAIL_ENABLED'] = True
        nid = self.enqueue()
        self.app.config['SMTP_PASSWORD'] = ''
        with self.assertRaises(Exception):
            process_emails()
        self.assertEqual(self.row(nid).delivery_status, 'PENDING')
        smtp.assert_not_called()

    @patch('app.services.email_service.send_email')
    def test_stale_proposal_and_disabled_recipient_are_not_emailed(self, smtp):
        # An email left in the queue by the removed proposal flow is never sent.
        with UnitOfWork() as ctx:
            row = Notification(user_id=self.uid, notification_type='MATCH_PROPOSAL', title='Cũ', content='Đề xuất cũ',
                               delivery_channel='EMAIL', delivery_status='PENDING', sent_at=None)
            ctx.session.add(row)
            ctx.session.flush()
            nid = row.notification_id
        self.assertEqual(process_emails()['skipped'], 1)
        self.assertEqual(self.row(nid).delivery_status, 'FAILED')
        self.enqueue()
        with UnitOfWork() as ctx:
            ctx.session.get(User, self.uid).status = 'BANNED'
        self.assertEqual(process_emails()['skipped'], 1)
        smtp.assert_not_called()

    @patch('app.services.email_service.smtplib.SMTP')
    def test_smtp_uses_verified_tls_and_check_sends_no_email(self, smtp):
        connection = smtp.return_value
        connection.noop.return_value = (250, b'ok')
        check_connection()
        connection.starttls.assert_called_once()
        connection.login.assert_called_once_with('sender@gmail.com', 'test-not-real')
        connection.send_message.assert_not_called()
        connection.close.assert_called_once()

    @patch('app.services.email_service.smtplib.SMTP')
    def test_smtp_message_headers_and_accepted_connection_close(self, smtp):
        connection = smtp.return_value
        connection.send_message.return_value = {}
        send_email('recipient@gmail.com', 'Title\r\nNo injected header', 'Body', 42, 'http://localhost:5173/#/notifications')
        message = connection.send_message.call_args.args[0]
        self.assertEqual(message['To'], 'recipient@gmail.com')
        self.assertIn('sender@gmail.com', message['From'])
        self.assertNotIn('\n', str(message['Subject']))
        self.assertIn('/#/notifications', message.get_content())


if __name__ == '__main__':
    unittest.main()
