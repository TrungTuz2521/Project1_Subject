"""Explicit local-development simulation, persisted and labelled separately from real receipts."""
from decimal import Decimal
from flask import current_app
from app.contracts.errors import DomainError
from app.infrastructure.retry import retry_conflicts
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Payment
from app.services import auth_service, booking_policy as policy, booking_service, payment_service
from app.use_cases.process_payment import _required_for, _after_deposit_recorded


@retry_conflicts
def confirm_demo_deposit(actor, booking_id):
    if not current_app.config.get('DEMO_PAYMENT_ENABLED'):
        raise DomainError('DEMO_DISABLED', 'Xác nhận cọc demo đang tắt.', 403)
    with UnitOfWork() as ctx:
        auth_service.require_player(ctx, actor)
        booking, payments = booking_service.lock_booking_graph(ctx, booking_id)
        required = _required_for(booking, actor.user_id)
        if required is None:
            raise DomainError('NOT_FOUND', 'Không tìm thấy booking.', 404)
        code = f'DEMO-DEP-{booking_id}-{actor.user_id}'
        previous = next((p for p in payments if p.transaction_code == code), None)
        if previous:
            return dict(demo=True, payment=payment_service.payment_data(previous), booking=booking_service.booking_data(ctx, booking))
        if booking.status != 'PENDING_HOLD' or not booking.hold_expires_at or ctx.now() >= booking.hold_expires_at:
            raise DomainError('HOLD_EXPIRED', 'Booking không còn trong thời hạn xác nhận cọc.')
        payment_service.expire_stale_qr_sessions(ctx, payments)
        if any(p.status == 'PENDING' and p.payment_type == 'BOOKING_DEPOSIT' for p in payments):
            raise DomainError('PAYMENT_RECONCILIATION_REQUIRED', 'Còn giao dịch online cần đối soát; không trộn với cọc demo.')
        if any(p.status in ('SUCCESS', 'REFUNDED') and not payment_service.is_demo_payment(p) for p in payments):
            raise DomainError('STATE_CONFLICT', 'Booking đã có giao dịch thật; không trộn với cọc demo.')
        due = required - booking_service.paid_deposit_by_user(payments).get(actor.user_id, Decimal('0'))
        if due <= 0:
            raise DomainError('DEPOSIT_ALREADY_PAID', 'Đã đủ phần cọc của bạn.')
        payment = Payment(user_id=actor.user_id, booking_id=booking_id, amount=due,
            payment_type='BOOKING_DEPOSIT', payment_method='BANK_TRANSFER', transaction_code=code,
            status='SUCCESS', paid_at=ctx.now(), note='DEMO_ONLY: user simulation; no verified bank transfer')
        booking.note = policy.add_note(booking.note, 'DEMO_ONLY: simulated deposit')
        ctx.session.add(payment);ctx.session.flush()
        _after_deposit_recorded(ctx, booking, payment)
        return dict(demo=True, payment=payment_service.payment_data(payment), booking=booking_service.booking_data(ctx, booking))
