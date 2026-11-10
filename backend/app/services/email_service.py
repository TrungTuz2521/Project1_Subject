"""SMTP delivery outside business transactions, using existing EMAIL notification rows."""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import urlsplit
from flask import current_app
from sqlalchemy import select, update
from app.contracts.errors import DomainError
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Notification, User, Match, MatchProposal, Booking

EMAIL_TYPES = frozenset({
    'MATCH_PROPOSAL', 'PROPOSAL_ACCEPTED', 'PROPOSAL_REJECTED', 'PROPOSAL_EXPIRED',
    'BOOKING_HOLD', 'BOOKING_CONFIRMED', 'BOOKING_EXPIRED', 'PAYMENT_SUCCESS',
    'MATCH_CONFIRMED', 'MATCH_CANCELLED', 'TEAM_JOINED',
    'REFUND_PROCESSING', 'REFUND_SUCCESS', 'REFUND_FAILED',
})


def smtp_settings():
    config = current_app.config
    if not config.get('EMAIL_ENABLED'):
        raise DomainError('EMAIL_DISABLED', 'Gửi email đang tắt.', 503)
    username = config.get('SMTP_USERNAME', '')
    password = config.get('SMTP_PASSWORD', '')
    if not username or not password:
        raise DomainError('EMAIL_NOT_CONFIGURED', 'Chưa cấu hình tài khoản gửi email.', 503)
    return username, password


def smtp_connection():
    username, password = smtp_settings()
    client = smtplib.SMTP(current_app.config['SMTP_HOST'], current_app.config['SMTP_PORT'], timeout=15)
    try:
        client.ehlo()
        client.starttls(context=ssl.create_default_context())
        client.ehlo()
        client.login(username, password)
    except Exception:
        client.close()
        raise
    return client


def check_connection():
    # Authenticate without sending any email.
    client = smtp_connection()
    try:
        code, _ = client.noop()
        if code != 250:
            raise RuntimeError('SMTP check failed')
    finally:
        client.close()


def send_email(recipient, title, content, notification_id, link):
    username, _ = smtp_settings()
    message = EmailMessage()
    message['From'] = formataddr(('Football Booking', username))
    message['To'] = recipient
    message['Subject'] = '[Football Booking] ' + title.replace('\r', ' ').replace('\n', ' ')
    # Stable ID aids diagnosis; SMTP itself does not guarantee deduplication or delivery to inbox.
    domain = username.rsplit('@', 1)[-1]
    message['Message-ID'] = f'<football-notification-{notification_id}@{domain}>'
    message.set_content(f'{content}\n\nMở ứng dụng để xem trạng thái mới nhất:\n{link}\n\n'
                        'Thời hạn giữ sân tính theo server, không gia hạn khi mở email.\n'
                        'Email tự động từ Football Booking. Không trả lời email để xác nhận thanh toán.')
    client = smtp_connection()
    try:
        refused = client.send_message(message)
        if refused:
            raise RuntimeError('SMTP recipient refused')
    finally:
        # close() avoids a QUIT connection error turning an accepted email into a failed send.
        client.close()


def claim_email(notification_id):
    """Conservative claim with the existing enum: reserve as FAILED before SMTP.

    A crash/ambiguous SMTP response leaves FAILED for operator review, never automatic resend.
    This bounds duplicate sends across concurrent workers without a new DB migration.
    """
    with UnitOfWork() as ctx:
        changed = ctx.session.execute(update(Notification).where(
            Notification.notification_id == notification_id, Notification.delivery_channel == 'EMAIL',
            Notification.delivery_status == 'PENDING').values(delivery_status='FAILED', sent_at=None))
        if changed.rowcount != 1:
            return None
        row = ctx.session.get(Notification, notification_id)
        user = ctx.session.get(User, row.user_id)
        if not user or user.status != 'ACTIVE' or not user.email or user.email.rsplit('@', 1)[-1].endswith(('.test', '.invalid')):
            return None
        match = ctx.session.get(Match, row.match_id) if row.match_id else None
        booking = ctx.session.get(Booking, match.booking_id) if match and match.booking_id else None
        if row.notification_type == 'BOOKING_HOLD' and (not booking or booking.status != 'PENDING_HOLD'
                or not booking.hold_expires_at or booking.hold_expires_at <= ctx.now()):
            return None  # Never send an obsolete request to pay a deposit.
        if row.notification_type == 'MATCH_PROPOSAL':
            proposal = ctx.session.get(MatchProposal, row.proposal_id) if row.proposal_id else None
            if not proposal or proposal.status != 'PENDING_CONFIRMATION' or proposal.expires_at <= ctx.now():
                return None
        base = current_app.config['PUBLIC_WEB_URL'].rstrip('/')
        parsed = urlsplit(base)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.fragment or parsed.query:
            raise DomainError('EMAIL_NOT_CONFIGURED', 'PUBLIC_WEB_URL cần là origin của frontend.', 503)
        link = (f'{base}/#/my-bookings?booking_id={booking.booking_id}' if booking else
                f'{base}/#/notifications?proposal_id={row.proposal_id}' if row.proposal_id else f'{base}/#/notifications')
        return (user.email, row.title, row.content, row.notification_id, link)


def process_emails(limit=50):
    smtp_settings()  # Missing config must not consume the queue.
    with UnitOfWork() as ctx:
        ids = list(ctx.session.scalars(select(Notification.notification_id).where(
            Notification.delivery_channel == 'EMAIL', Notification.delivery_status == 'PENDING'
        ).order_by(Notification.notification_id).limit(limit)))
    stats = {'sent': 0, 'failed': 0, 'skipped': 0}
    for notification_id in ids:
        work = claim_email(notification_id)
        if not work:
            stats['skipped'] += 1
            continue
        try:
            send_email(*work)  # Claim transaction already committed and closed.
        except Exception as error:
            current_app.logger.warning('Email notification %s failed (%s)', notification_id, type(error).__name__)
            stats['failed'] += 1
            continue
        with UnitOfWork() as ctx:
            ctx.session.execute(update(Notification).where(Notification.notification_id == notification_id,
                Notification.delivery_channel == 'EMAIL', Notification.delivery_status == 'FAILED'
            ).values(delivery_status='SENT', sent_at=ctx.now()))
        stats['sent'] += 1
    return stats
