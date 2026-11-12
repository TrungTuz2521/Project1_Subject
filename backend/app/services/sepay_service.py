"""SePay QR deposit: a 60-second VietQR code per payer, confirmed only by SePay's bank-credit webhook.

The QR pre-fills the receiving account, the exact amount still due and the transfer content (a code
stored on a PENDING payment). The browser never reports a payment; only an authenticated webhook does,
and it goes through the same process_gateway_callback path as VNPay (locks, amount check, late money).
"""
import hmac
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from flask import current_app
from sqlalchemy import select
from app.contracts.dto import GatewayResult
from app.contracts.errors import DomainError
from app.infrastructure.retry import retry_conflicts
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Payment
from app.services import auth_service, booking_policy as policy, booking_service, payment_service
from app.services.booking_balance_service import bank_qr_payload
from app.services.gateway import InvalidCallback
from app.utils.time import VIETNAM

METHOD = 'BANK_TRANSFER'
# Overlapping search: bank apps may glue the code to other text or upper-case it.
CODE_PATTERN = re.compile(r'(?=(%s[0-9A-F]{%d}))' % (payment_service.QR_PREFIX,
                                                     payment_service.QR_CODE_LENGTH - len(payment_service.QR_PREFIX)))


def bank_account():
    config = current_app.config
    bank_bin, account = config.get('BANK_BIN', '').strip(), config.get('BANK_ACCOUNT_NO', '').strip()
    name = config.get('BANK_ACCOUNT_NAME', '').strip()
    if re.fullmatch(r'\d{6}', bank_bin) and re.fullmatch(r'\d{3,30}', account) and name:
        return bank_bin, account, name
    return None


def enabled():
    return bool(current_app.config.get('SEPAY_WEBHOOK_KEY')) and bank_account() is not None


def session_data(payment, booking):
    bank_bin, account, name = bank_account()
    amount = Decimal(payment.amount)
    return dict(payment_id=payment.payment_id, booking_id=payment.booking_id, status=payment.status,
                amount=policy.money(amount), transfer_reference=payment.transaction_code,
                qr_payload=bank_qr_payload(bank_bin, account, amount, payment.transaction_code),
                qr_expires_at=payment_service.qr_expires_at(payment), hold_expires_at=booking.hold_expires_at,
                bank_name=current_app.config.get('BANK_NAME') or bank_bin, account_no=account, account_name=name)


def _keep_hold_for_qr(ctx, booking):
    """The slot stays held while the code is shown plus the bank-notification grace, extended at most once:
    the deadline never passes the original hold plus one QR window, so new codes cannot hold a slot forever."""
    window = payment_service.qr_ttl() + payment_service.qr_grace()
    cap = booking.created_at + timedelta(seconds=policy.HOLD_SECONDS) + window
    target = min(ctx.now() + window, cap)
    if target > booking.hold_expires_at:
        booking.hold_expires_at = target.replace(microsecond=0)


@retry_conflicts
def open_qr_session(actor, booking_id):
    """Returns (session, created). Reuses the payer's code while it is still shown; afterwards a new one."""
    if not enabled():
        raise DomainError('PAYMENT_PROVIDER_UNAVAILABLE', 'Chưa cấu hình thanh toán QR tự động.', 503)
    with UnitOfWork() as ctx:
        auth_service.require_active_actor(ctx, actor)
        booking, payments = booking_service.lock_booking_graph(ctx, booking_id)
        required = booking_service.required_share(booking, actor.user_id)
        if required is None:
            raise DomainError('NOT_FOUND', 'Không tìm thấy booking.', 404)
        if any(payment_service.is_demo_payment(p) for p in payments):
            raise DomainError('DEMO_ONLY', 'Booking DEMO không nhận chuyển khoản thật.', 409)
        if booking.status != 'PENDING_HOLD':
            raise DomainError('STATE_CONFLICT', 'Booking không còn chờ cọc.')
        if ctx.now() >= booking.hold_expires_at:
            raise DomainError('HOLD_EXPIRED', 'Đã hết thời gian giữ sân.')
        payment_service.expire_stale_qr_sessions(ctx, [p for p in payments if p.user_id == actor.user_id], ttl_only=True)
        due = required - booking_service.paid_deposit_by_user(payments).get(actor.user_id, Decimal('0'))
        if due <= 0:
            raise DomainError('DEPOSIT_ALREADY_PAID', 'Bạn đã trả đủ phần cọc.')
        payment = payment_service.find_active_deposit(payments, actor.user_id)
        if payment is not None and not payment_service.is_qr_session(payment):
            raise DomainError('PAYMENT_RECONCILIATION_REQUIRED', 'Còn phiên cọc online khác chưa rõ trạng thái.')
        created = payment is None
        if created:
            payment = payment_service.create_pending_deposit(ctx, booking=booking, user_id=actor.user_id, method=METHOD,
                                                             amount=policy.money(due), code=payment_service.new_qr_code())
            _keep_hold_for_qr(ctx, booking)
            ctx.session.flush()
        return session_data(payment, booking), created


def _parse_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount.is_finite() and amount > 0 and amount == amount.to_integral_value() else None


def _parse_time(value):
    try:
        return datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S').replace(tzinfo=VIETNAM).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def find_codes(payload):
    """SePay's own extracted `code` first, then every candidate in the transfer text."""
    found = []
    for field in ('code', 'content', 'description'):
        text = str(payload.get(field) or '').upper().replace(' ', '')
        for code in CODE_PATTERN.findall(text):
            if code not in found:
                found.append(code)
    return found


def verify_webhook(authorization, payload):
    """Returns a verified SUCCESS GatewayResult, or (None, reason) for a genuine notification that is not ours."""
    key = current_app.config.get('SEPAY_WEBHOOK_KEY', '')
    if not key or bank_account() is None:
        raise DomainError('PAYMENT_PROVIDER_UNAVAILABLE', 'Chưa cấu hình thanh toán QR tự động.', 503)
    scheme, _, token = (authorization or '').strip().partition(' ')
    if scheme.lower() != 'apikey' or not hmac.compare_digest(token.strip().encode(), key.encode()):
        raise InvalidCallback()
    if not isinstance(payload, dict):
        return None, 'INVALID_PAYLOAD'
    if payload.get('transferType') != 'in':
        return None, 'NOT_INCOMING'
    _, account, _ = bank_account()
    if str(payload.get('accountNumber') or '').strip() != account:
        return None, 'OTHER_ACCOUNT'
    amount = _parse_amount(payload.get('transferAmount'))
    if amount is None:
        return None, 'INVALID_AMOUNT'
    codes = find_codes(payload)
    if not codes:
        return None, 'NO_REFERENCE'
    with UnitOfWork() as ctx:
        known = set(ctx.session.scalars(select(Payment.transaction_code).where(Payment.transaction_code.in_(codes))))
    code = next((c for c in codes if c in known), None)
    if code is None:
        return None, 'NO_REFERENCE'
    return GatewayResult('SUCCESS', code, policy.money(amount), 'VND', provider_reference=f"sepay:{payload.get('id')}",
                         paid_at=_parse_time(payload.get('transactionDate'))), None


def handle_webhook(authorization, payload):
    """Every authenticated notification is answered 200 so SePay stops retrying; the outcome is for logs/tests."""
    from app.use_cases.process_payment import process_gateway_callback
    verified, ignored = verify_webhook(authorization, payload)
    if verified is None and ignored == 'NO_REFERENCE':
        # Not a deposit code: maybe the pitch fee paid with the booking's balance QR (content SAN<id>TT).
        from app.use_cases.process_payment import find_balance_booking, record_balance_transfer
        booking_id = find_balance_booking(payload)
        if booking_id is not None:
            outcome = record_balance_transfer(booking_id, _parse_amount(payload.get('transferAmount')),
                                              f"sepay:{payload.get('id')}", _parse_time(payload.get('transactionDate')))
            if outcome == 'NO_REFERENCE':
                current_app.logger.warning('SePay pitch-fee transfer for an unknown booking needs review')
            return outcome
    if verified is None:
        current_app.logger.info('SePay notification ignored (%s)', ignored)
        return ignored
    # Bank transfer: whatever amount arrived is recorded; a short share stays partial, extra money pays the
    # booking or is queued for refund. Nothing real is ever left only in a note.
    outcome = process_gateway_callback(METHOD, verified, bank_transfer=True).outcome
    if outcome == 'DUPLICATE':
        current_app.logger.info('SePay notification already recorded (retry)')
    elif outcome not in ('OK', 'EXTRA_RECORDED'):
        current_app.logger.warning('SePay notification needs review (%s)', outcome)
    return outcome


def expire_stale_sessions():
    """Worker: codes past their window plus the grace stop blocking Admin receipts and demo confirmation."""
    with UnitOfWork() as ctx:
        rows = ctx.session.execute(select(Payment.booking_id, Payment.transaction_code).where(
            Payment.status == 'PENDING', Payment.payment_method == METHOD,
            Payment.transaction_code.like(payment_service.QR_PREFIX + '%'))).all()
    booking_ids = sorted({booking_id for booking_id, code in rows if len(code) == payment_service.QR_CODE_LENGTH})
    expired = 0
    for booking_id in booking_ids:
        with UnitOfWork() as ctx:
            _, payments = booking_service.lock_booking_graph(ctx, booking_id)
            expired += len(payment_service.expire_stale_qr_sessions(ctx, payments))
    return expired
