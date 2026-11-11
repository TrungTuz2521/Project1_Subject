from datetime import timedelta
from decimal import Decimal
from secrets import token_hex
from flask import current_app
from sqlalchemy import select
from app.contracts.dto import PaymentApplyResult, RefundPlan
from app.contracts.errors import DomainError
from app.models import Booking, Payment
from app.services import booking_policy as policy, booking_service, notification_service
from app.utils.serialization import columns

COLLECTED_TYPES = ('BOOKING_DEPOSIT', 'BOOKING_REMAINING_PAYMENT')
CONSOLIDATED_NOTE = 'THU_GOP theo booking'
FORFEITED_NOTE = 'MAT_COC do tu huy'
ACTIVE_REFUND = ('REFUND_PROCESSING', 'SUCCESS')
# SePay QR deposits are stored as BANK_TRANSFER (no ENUM migration) and told apart by this fixed-length code.
QR_PREFIX = 'SP'
QR_CODE_LENGTH = 12
QR_EXPIRED_NOTE = 'QR het han'

def is_demo_payment(payment):
    return (payment.transaction_code or '').startswith('DEMO-')


def payment_data(payment, admin=False):
    result = columns(payment, 'payment_id booking_id post_id amount payment_type payment_method status '
                     'transaction_code refund_for_payment_id paid_at')
    result['is_demo'] = is_demo_payment(payment)
    if admin:
        result.update(columns(payment, 'user_id recorded_by_admin_id note created_at'))
    return result

def is_consolidated(payment):
    return bool(payment.note) and payment.note.startswith(CONSOLIDATED_NOTE)

def is_qr_session(payment):
    code = payment.transaction_code or ''
    return payment.payment_method == 'BANK_TRANSFER' and code.startswith(QR_PREFIX) and len(code) == QR_CODE_LENGTH

def new_qr_code():
    return QR_PREFIX + token_hex((QR_CODE_LENGTH - len(QR_PREFIX)) // 2).upper()

def qr_ttl():
    return timedelta(seconds=int(current_app.config.get('SEPAY_QR_TTL_SECONDS', 60)))

def qr_grace():
    return timedelta(seconds=int(current_app.config.get('SEPAY_CONFIRM_GRACE_SECONDS', 120)))

def qr_expires_at(payment):
    return payment.created_at + qr_ttl()

def expire_stale_qr_sessions(ctx, payments, *, ttl_only=False):
    """PENDING QR rows stop blocking once their code is no longer shown (ttl_only, a new code was asked for)
    or once a slow bank notification can no longer be expected. FAILED is not terminal: real money that
    still arrives for the code is recorded by apply_verified_payment. Caller holds the booking locks."""
    now, limit = ctx.now(), qr_ttl() + (timedelta(0) if ttl_only else qr_grace())
    expired = []
    for payment in payments:
        if is_qr_session(payment) and payment.status == 'PENDING' and now >= payment.created_at + limit:
            payment.status = 'FAILED'
            payment.note = policy.add_note(payment.note, QR_EXPIRED_NOTE)
            expired.append(payment)
    if expired:
        ctx.session.flush()
    return expired

def find_active_deposit(payments, user_id):
    return next((p for p in payments if p.user_id == user_id and p.payment_type == 'BOOKING_DEPOSIT'
                 and p.status == 'PENDING'), None)

def create_pending_deposit(ctx, *, booking, user_id, method, amount, code=None):
    """The merchant reference is stored before any network call and never regenerated on timeout."""
    code = code or f'B{booking.booking_id}U{user_id}{token_hex(6).upper()}'
    payment = Payment(user_id=user_id, booking_id=booking.booking_id, amount=amount, payment_type='BOOKING_DEPOSIT',
                      payment_method=method, transaction_code=code, status='PENDING',
                      created_at=ctx.now().replace(microsecond=0))
    ctx.session.add(payment)
    ctx.session.flush()
    return payment

def apply_verified_payment(ctx, verified):
    """Caller holds the locks. A terminal SUCCESS is never overwritten; real money is always recorded."""
    payment = ctx.session.scalar(select(Payment).where(Payment.transaction_code == verified.merchant_reference))
    booking = ctx.session.get(Booking, payment.booking_id)
    if payment.status in ('SUCCESS', 'REFUNDED'):
        return PaymentApplyResult(payment.payment_id, booking.booking_id, False, True, False)
    if verified.state != 'SUCCESS':
        if verified.state == 'FAILED' and payment.status == 'PENDING':
            payment.status = 'FAILED'
        return PaymentApplyResult(payment.payment_id, booking.booking_id, False, False, False)
    now = ctx.now()
    payment.status, payment.paid_at = 'SUCCESS', verified.paid_at or now
    if verified.provider_reference:
        payment.note = policy.add_note(payment.note, f'gw={verified.provider_reference}')
    late = payment.payment_type == 'BOOKING_DEPOSIT' and (booking.status != 'PENDING_HOLD' or now >= booking.hold_expires_at)
    ctx.session.flush()
    return PaymentApplyResult(payment.payment_id, booking.booking_id, True, False, late)

def plan_refunds(ctx, *, booking_id, cause, cancelling_user_id=None, payment_ids=None):
    """The single refund policy. Pure calculation over real receipts and who actually paid."""
    payments = booking_service.payments_of(ctx, booking_id)
    refunded = {p.refund_for_payment_id for p in payments if p.payment_type == 'REFUND' and p.status in ACTIVE_REFUND}
    items, forfeited = [], []
    for payment in payments:
        if is_demo_payment(payment):
            continue  # Simulated deposits never trigger a real refund.
        if payment.payment_type not in COLLECTED_TYPES or payment.status != 'SUCCESS':
            continue
        if payment.payment_id in refunded or (payment_ids is not None and payment.payment_id not in payment_ids):
            continue
        if is_consolidated(payment):
            continue  # Reference account is not the sender: Admin must verify the recipient first.
        if cause == 'USER_CANCEL' and payment.user_id == cancelling_user_id:
            forfeited.append(payment.payment_id)
            continue
        items.append({'original_payment_id': payment.payment_id, 'payer_user_id': payment.user_id, 'amount': policy.money(payment.amount)})
    return RefundPlan(booking_id, cause, items, forfeited)

def create_refund(ctx, original, note=None):
    """One logical refund per original: reuse a processing/successful one. Caller locks the original."""
    existing = ctx.session.scalars(select(Payment).where(Payment.refund_for_payment_id == original.payment_id,
                                                         Payment.payment_type == 'REFUND')).all()
    active = next((p for p in existing if p.status in ACTIVE_REFUND), None)
    if active:
        return active
    refund = Payment(user_id=original.user_id, booking_id=original.booking_id, post_id=original.post_id,
                     amount=original.amount, payment_type='REFUND', payment_method=original.payment_method,
                     refund_for_payment_id=original.payment_id, status='REFUND_PROCESSING', note=note)
    ctx.session.add(refund)
    ctx.session.flush()
    refund.transaction_code = f'RF{refund.payment_id}'
    ctx.session.flush()
    return refund

def execute_refund_plan(ctx, plan, note=None):
    refunds = []
    for item in plan.items:
        refund = create_refund(ctx, ctx.session.get(Payment, item['original_payment_id']), note=note)
        refunds.append(refund)
        notification_service.notify(ctx, [refund.user_id], 'REFUND_PROCESSING', 'Đang hoàn tiền',
                                    'Khoản hoàn của bạn đang được xử lý.')
    for payment_id in plan.forfeited_payment_ids:
        payment = ctx.session.get(Payment, payment_id)
        payment.note = policy.add_note(payment.note, FORFEITED_NOTE)
    return refunds

def apply_verified_refund(ctx, verified):
    """SUCCESS moves the original to REFUNDED; FAILED leaves it SUCCESS; anything else stays processing."""
    refund = ctx.session.scalar(select(Payment).where(Payment.transaction_code == verified.merchant_reference,
                                                      Payment.payment_type == 'REFUND'))
    if refund is None or refund.status != 'REFUND_PROCESSING':
        return refund
    if verified.state == 'SUCCESS':
        refund.status, refund.paid_at = 'SUCCESS', verified.paid_at or ctx.now()
        ctx.session.get(Payment, refund.refund_for_payment_id).status = 'REFUNDED'
        notification_service.notify(ctx, [refund.user_id], 'REFUND_SUCCESS', 'Hoàn tiền thành công', 'Khoản hoàn đã hoàn tất.')
    elif verified.state == 'FAILED':
        refund.status = 'FAILED'
        notification_service.notify(ctx, [refund.user_id], 'REFUND_FAILED', 'Hoàn tiền thất bại', 'Khoản hoàn chưa thành công, cửa hàng sẽ đối soát.')
    ctx.session.flush()
    return refund

def refund_summary(ctx, booking_id, cause=None):
    payments = booking_service.payments_of(ctx, booking_id)
    refunds = [p for p in payments if p.payment_type == 'REFUND' and p.status != 'FAILED']
    forfeited = [p for p in payments if p.note and FORFEITED_NOTE in p.note]
    return {'cause': cause, 'refund_count': len(refunds), 'refund_amount': sum((Decimal(p.amount) for p in refunds), Decimal('0')),
            'forfeited_amount': sum((Decimal(p.amount) for p in forfeited), Decimal('0')),
            'forfeited_payment_ids': [p.payment_id for p in forfeited],
            'refunds': [{'payment_id': p.payment_id, 'refund_for_payment_id': p.refund_for_payment_id,
                         'amount': p.amount, 'status': p.status} for p in refunds]}

def require_no_pending(payments, *types):
    if any(p.status == 'PENDING' and p.payment_type in types for p in payments):
        raise DomainError('PAYMENT_RECONCILIATION_REQUIRED', 'Còn giao dịch online chưa rõ trạng thái, cần đối soát trước.')
