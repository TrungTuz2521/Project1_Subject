"""Read-only VietQR deposit instructions; only Admin receipt recording changes payment status."""
import re
from decimal import Decimal
from flask import current_app
from app.contracts.errors import DomainError
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Booking, User
from app.services import auth_service, booking_service, payment_service
from app.services.booking_balance_service import bank_qr_payload
from app.services.booking_policy import money


def instructions(actor, booking_id):
    with UnitOfWork() as ctx:
        auth_service.require_active_actor(ctx, actor)
        booking = ctx.session.get(Booking, booking_id)
        if not booking or (actor.role != 'ADMIN' and not booking_service.is_party(booking, actor.user_id)):
            raise DomainError('NOT_FOUND', 'Không tìm thấy booking.', 404)
        payments = booking_service.payments_of(ctx, booking_id)
        config = current_app.config
        bank_bin, account = config.get('BANK_BIN', '').strip(), config.get('BANK_ACCOUNT_NO', '').strip()
        account_name = config.get('BANK_ACCOUNT_NAME', '').strip()
        configured = bool(re.fullmatch(r'\d{6}', bank_bin) and re.fullmatch(r'\d{3,30}', account) and account_name)
        active = bool(booking.status == 'PENDING_HOLD' and booking.hold_expires_at and ctx.now() < booking.hold_expires_at)
        progress = booking_service.payer_progress(ctx, booking, payments)
        payers = []
        for item in progress:
            uid = item['user_id']
            if actor.role != 'ADMIN' and uid != actor.user_id:
                continue
            due = max(Decimal(item['required_amount']) - Decimal(item['paid_amount']), Decimal('0'))
            pending = payment_service.find_active_deposit(payments, uid)
            reason = None
            if due == 0:
                reason = 'Đã nhận đủ phần cọc này.'
            elif not active:
                reason = 'Booking không còn trong thời hạn nhận cọc. Không chuyển thêm tiền.'
            elif pending:
                reason = 'Còn phiên cọc online cần đối soát trước khi chuyển khoản trực tiếp.'
            elif not configured:
                reason = 'Chưa cấu hình đầy đủ ngân hàng, số tài khoản và tên chủ tài khoản nhận cọc.'
            reference = f'COC{booking_id}U{uid}'
            payer = dict(item, due_amount=money(due), transfer_reference=reference,
                         qr_payload=bank_qr_payload(bank_bin, account, due, reference) if reason is None else None,
                         unavailable_reason=reason, can_confirm=active and due > 0 and pending is None)
            if actor.role == 'ADMIN':
                user = ctx.session.get(User, uid)
                payer['full_name'] = user.full_name if user else f'Người trả #{uid}'
            payers.append(payer)
        return dict(booking_id=booking_id, status=booking.status, expires_at=booking.hold_expires_at,
                    demo_payment_enabled=bool(config.get('DEMO_PAYMENT_ENABLED')),
                    payment_method='BANK_TRANSFER', bank_bin=bank_bin if configured else None,
                    bank_name=config.get('BANK_NAME', '') or bank_bin, account_no=account if configured else None,
                    account_name=account_name if configured else None, payers=payers)
