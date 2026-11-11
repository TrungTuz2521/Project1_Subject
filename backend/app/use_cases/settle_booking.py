from decimal import Decimal
from hashlib import sha256
from app.contracts.errors import DomainError, invalid
from app.infrastructure.retry import retry_conflicts
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Booking, Payment
from app.services import auth_service, booking_balance_service, booking_service, payment_service

def get_booking_balance(actor, *, booking_id):
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        booking = ctx.session.get(Booking, booking_id)
        if booking is None or booking.booking_type == 'MAINTENANCE_LOCK':
            raise DomainError('NOT_FOUND', 'Không tìm thấy booking.', 404)
        return booking_balance_service.compute(ctx, booking)

def _receipt_note(reference):
    return (payment_service.CONSOLIDATED_NOTE + (f'; ref={reference}' if reference else ''))[:255]

def _same_receipts(previous, receipts):
    if len(previous) != len(receipts):
        return False
    return all((p.payment_method, Decimal(p.amount), p.note) == (r.payment_method, Decimal(r.amount), _receipt_note(r.reference))
               for p, r in zip(previous, receipts))

@retry_conflicts
def confirm_booking_paid(actor, *, booking_id, expected_outstanding, idempotency_key, receipts):
    """Admin has checked the money actually received. No per-team allocation or outcome."""
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        booking, payments = booking_service.lock_booking_graph(ctx, booking_id)
        key = sha256(idempotency_key.encode()).hexdigest()[:40]
        prefix = f'RCPT-{booking_id}-{key}-'
        # Idempotency comes first: a retry must return the old result even with a zero balance now.
        previous = sorted((p for p in payments if (p.transaction_code or '').startswith(prefix)),
                          key=lambda p: int(p.transaction_code.rsplit('-', 1)[1]))
        if previous:
            if not _same_receipts(previous, receipts):
                raise DomainError('STATE_CONFLICT', 'Mã xác nhận đã dùng cho một nội dung khác.')
            return booking_balance_service.compute(ctx, booking, payments)
        if any(payment_service.is_demo_payment(p) for p in payments):
            raise DomainError('DEMO_ONLY', 'Booking DEMO không nhận khoản thu thật.', 409)
        now = ctx.now()
        if booking.status != 'CONFIRMED':
            raise DomainError('STATE_CONFLICT', 'Chỉ xác nhận thu đủ cho booking đã xác nhận.')
        payment_service.require_no_pending(payments, 'BOOKING_REMAINING_PAYMENT')
        outstanding = booking_balance_service.compute(ctx, booking, payments, with_qr=False).outstanding_amount
        if outstanding == 0 or Decimal(expected_outstanding) != outstanding:
            raise DomainError('STATE_CONFLICT', 'Số dư đã thay đổi. Vui lòng tải lại.')
        if sum((Decimal(r.amount) for r in receipts), Decimal('0')) != outstanding:
            invalid('receipts', 'Tổng các khoản phải bằng đúng số còn thiếu.')
        for index, receipt in enumerate(receipts):
            # user_id is only a reference account (column is NOT NULL), not the person who transferred.
            ctx.session.add(Payment(user_id=booking.user_id, booking_id=booking_id, amount=receipt.amount,
                                    payment_type='BOOKING_REMAINING_PAYMENT', payment_method=receipt.payment_method,
                                    transaction_code=f'{prefix}{index}', recorded_by_admin_id=actor.user_id, status='SUCCESS',
                                    paid_at=now, note=_receipt_note(receipt.reference)))
        ctx.session.flush()
        return booking_balance_service.compute(ctx, booking)
