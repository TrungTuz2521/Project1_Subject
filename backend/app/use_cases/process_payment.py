from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from flask import current_app
from sqlalchemy import select
from app.contracts.dto import CommandResult
from app.contracts.errors import DomainError, invalid
from app.infrastructure.retry import retry_conflicts
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Payment, Pitch, User
from app.utils.time import VIETNAM
from app.services import auth_service, booking_policy as policy, booking_service, match_service, notification_service, payment_service
from app.services.gateway import get_gateway
from app.use_cases.cancel_booking import close_booking
from app.services.booking_balance_service import compute

@dataclass(frozen=True)
class _OpenSession:
    data: dict
    reference: str
    amount: Decimal
    expires_at: object
    created_at: object
    created: bool

def _required_for(booking, user_id):
    item = next((p for p in booking.payer_plan or [] if p['user_id'] == user_id), None)
    return Decimal(item['amount']) if item else None

@retry_conflicts
def _open_deposit(actor, booking_id, method):
    with UnitOfWork() as ctx:
        auth_service.require_active_actor(ctx, actor)
        booking, payments = booking_service.lock_booking_graph(ctx, booking_id)
        if any(payment_service.is_demo_payment(p) for p in payments):
            raise DomainError('DEMO_ONLY', 'Booking DEMO không mở phiên thanh toán thật.', 409)
        required = _required_for(booking, actor.user_id)
        if required is None:
            raise DomainError('NOT_FOUND', 'Không tìm thấy booking.', 404)
        if booking.status != 'PENDING_HOLD':
            raise DomainError('STATE_CONFLICT', 'Booking không còn chờ cọc.')
        if ctx.now() >= booking.hold_expires_at:
            raise DomainError('HOLD_EXPIRED', 'Đã hết thời gian giữ sân.')
        due = required - booking_service.paid_deposit_by_user(payments).get(actor.user_id, Decimal('0'))
        if due <= 0:
            raise DomainError('DEPOSIT_ALREADY_PAID', 'Bạn đã trả đủ phần cọc.')
        payment = payment_service.find_active_deposit(payments, actor.user_id)
        created = payment is None
        if payment is not None and payment.payment_method != method:
            raise DomainError('STATE_CONFLICT', 'Đang có phiên cọc bằng phương thức khác còn hiệu lực.')
        if created:
            payment = payment_service.create_pending_deposit(ctx, booking=booking, user_id=actor.user_id, method=method, amount=policy.money(due))
        return _OpenSession(payment_service.payment_data(payment), payment.transaction_code, Decimal(payment.amount),
                            booking.hold_expires_at, payment.created_at, created)

def create_deposit_session(actor, *, booking_id, payment_method, client_ip=None):
    """Intent commits first; the adapter runs outside any transaction. Returns (session, created)."""
    gateway = get_gateway(payment_method)
    opened = _open_deposit(actor, booking_id, payment_method)
    try:
        # A failure leaves the PENDING row and reference in place, so a retry reuses them.
        result = gateway.create_payment(opened.reference, opened.amount, opened.expires_at,
                                        current_app.config.get('VNPAY_RETURN_URL', ''), created_at=opened.created_at,
                                        client_ip=client_ip or '127.0.0.1')
    except Exception as error:
        current_app.logger.warning('Payment adapter failed (%s)', type(error).__name__)
        raise DomainError('PAYMENT_PROVIDER_UNAVAILABLE', 'Chưa tạo được giao dịch với nhà cung cấp.', 503)
    if result.state not in ('PENDING', 'SUCCESS'):
        raise DomainError('PAYMENT_PROVIDER_UNAVAILABLE', 'Chưa tạo được giao dịch với nhà cung cấp.', 503)
    session = dict(opened.data, payment_url=result.payment_url, qr_payload=result.qr_payload, expires_at=opened.expires_at)
    return session, opened.created

def _booking_summary(ctx, booking):
    pitch = ctx.session.get(Pitch, booking.pitch_id)
    start, end = booking.start_time.astimezone(VIETNAM), booking.end_time.astimezone(VIETNAM)
    return (f'Booking #{booking.booking_id} - {pitch.pitch_name if pitch else f"sân #{booking.pitch_id}"}, '
            f'{start:%H:%M}-{end:%H:%M} ngày {start:%d/%m/%Y}.')

def _vnd(amount):
    return f'{int(Decimal(amount)):,}'.replace(',', '.') + ' VND'

def _after_deposit_recorded(ctx, booking, payment):
    demo = payment_service.is_demo_payment(payment)
    summary = _booking_summary(ctx, booking)
    notification_service.notify(ctx, [payment.user_id], 'PAYMENT_SUCCESS',
        'Đã xác nhận cọc DEMO' if demo else 'Đã thanh toán tiền cọc đặt sân',
        'Cọc mô phỏng đã được lưu; chưa xác minh tiền ngân hàng.' if demo else
        f'Đã nhận {_vnd(payment.amount)} tiền cọc của bạn (mã giao dịch {payment.transaction_code}). {summary}')
    if booking_service.confirm_if_deposit_complete(ctx, booking_id=booking.booking_id):
        match = match_service.confirm_after_deposit(ctx, booking_id=booking.booking_id, **({'is_demo': True} if demo else {}))
        if match is None:
            notification_service.notify(ctx, [booking.user_id], 'BOOKING_CONFIRMED',
                'Đặt sân DEMO thành công' if demo else 'Đặt sân thành công - đã thanh toán đủ cọc',
                'Đã đủ cọc mô phỏng; không phải khoản thu ngân hàng.' if demo else
                f'Đã nhận đủ {_vnd(booking.deposit_amount)} tiền cọc, sân đã được giữ cho bạn. {summary}')

def _handle_late(ctx, booking, payment):
    """Money is real but never revives the hold: refund it and keep the slot released."""
    if booking.status == 'PENDING_HOLD':
        close_booking(ctx, booking, status='EXPIRED', cause='HOLD_TIMEOUT', actor_id=None, reason='Hết hạn khi tiền đến muộn')
    else:
        plan = payment_service.plan_refunds(ctx, booking_id=booking.booking_id, cause='LATE_PAYMENT', payment_ids=[payment.payment_id])
        payment_service.execute_refund_plan(ctx, plan, note='LATE_PAYMENT')
    payment.note = policy.add_note(payment.note, 'Tien den muon, can doi soat')

def process_gateway_callback(provider, verified):
    """verified has passed the adapter's signature/merchant checks. Same path for IPN and reconciliation."""
    with UnitOfWork() as ctx:
        payment = ctx.session.scalar(select(Payment).where(Payment.transaction_code == verified.merchant_reference))
        if (payment is None or payment.payment_method != provider or payment.booking_id is None
                or payment.payment_type not in payment_service.COLLECTED_TYPES):
            return CommandResult('NOT_FOUND', http_status=404)
        booking, _ = booking_service.lock_booking_graph(ctx, payment.booking_id)
        if Decimal(verified.amount) != Decimal(payment.amount) or verified.currency != 'VND':
            payment.note = policy.add_note(payment.note, 'Callback sai so tien, can doi soat')
            return CommandResult('AMOUNT_MISMATCH', http_status=422)
        result = payment_service.apply_verified_payment(ctx, verified)
        if result.duplicate:
            return CommandResult('DUPLICATE', data=result)
        if result.late:
            _handle_late(ctx, booking, payment)
        elif result.applied:
            _after_deposit_recorded(ctx, booking, payment)
        return CommandResult(data=result)

@retry_conflicts
def record_manual_payment(actor, *, booking_id, user_id, payment_type, amount, method, reference, note=None):
    """Real cash/bank receipt verified by Admin. Returns (payment data, created)."""
    with UnitOfWork() as ctx:
        auth_service.require_admin(ctx, actor)
        booking, payments = booking_service.lock_booking_graph(ctx, booking_id)
        code = f'MAN-{booking_id}-{sha256(reference.encode()).hexdigest()[:32]}'
        existing = next((p for p in payments if p.transaction_code == code), None)
        if existing:
            same = (existing.user_id, existing.payment_type, Decimal(existing.amount), existing.payment_method) == (user_id, payment_type, amount, method)
            if not same:
                raise DomainError('STATE_CONFLICT', 'Mã chứng từ đã dùng cho một khoản khác.')
            return payment_service.payment_data(existing, admin=True), False
        if any(payment_service.is_demo_payment(p) for p in payments):
            raise DomainError('DEMO_ONLY', 'Booking DEMO không nhận khoản thu thật.', 409)
        now = ctx.now()
        if payment_type == 'BOOKING_DEPOSIT':
            required = _required_for(booking, user_id)
            if required is None:
                invalid('user_id', 'Người này không có phần cọc trong booking.')
            if booking.status != 'PENDING_HOLD':
                raise DomainError('STATE_CONFLICT', 'Booking không còn chờ cọc.')
            if now >= booking.hold_expires_at:
                raise DomainError('HOLD_EXPIRED', 'Đã hết thời gian giữ sân.')
            payment_service.expire_stale_qr_sessions(ctx, payments)
            if payment_service.find_active_deposit(payments, user_id):
                raise DomainError('PAYMENT_RECONCILIATION_REQUIRED', 'Người này còn phiên cọc online chưa rõ trạng thái.')
            due = required - booking_service.paid_deposit_by_user(payments).get(user_id, Decimal('0'))
            if due <= 0:
                raise DomainError('DEPOSIT_ALREADY_PAID', 'Người này đã trả đủ phần cọc.')
            if amount > due:
                invalid('amount', 'Vượt phần cọc còn phải trả.')
        else:
            if booking.status != 'CONFIRMED':
                raise DomainError('STATE_CONFLICT', 'Chỉ thu phần còn lại của booking đã xác nhận.')
            payment_service.require_no_pending(payments, 'BOOKING_REMAINING_PAYMENT')
            if ctx.session.get(User, user_id) is None:
                invalid('user_id')
            if amount > compute(ctx, booking, payments, with_qr=False).outstanding_amount:
                invalid('amount', 'Vượt số tiền còn thiếu.')
        payment = Payment(user_id=user_id, booking_id=booking_id, amount=amount, payment_type=payment_type, payment_method=method,
                          transaction_code=code, recorded_by_admin_id=actor.user_id, status='SUCCESS', paid_at=now,
                          note=(f'ref={reference}' + (f'; {note}' if note else ''))[:255])
        ctx.session.add(payment)
        ctx.session.flush()
        if payment_type == 'BOOKING_DEPOSIT':
            _after_deposit_recorded(ctx, booking, payment)
        return payment_service.payment_data(payment, admin=True), True
