import re
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
    required = _required_for(booking, payment.user_id) or Decimal('0')
    paid = booking_service.paid_deposit_by_user(booking_service.payments_of(ctx, booking.booking_id)).get(payment.user_id, Decimal('0'))
    if not demo and paid < required:
        deadline = booking.hold_expires_at.astimezone(VIETNAM)
        notification_service.notify(ctx, [payment.user_id], 'PAYMENT_SUCCESS', 'Đã nhận một phần tiền cọc',
            f'Đã nhận {_vnd(payment.amount)} (mã {payment.transaction_code}), còn thiếu {_vnd(required - paid)} tiền cọc. '
            f'Mở Lịch đã đặt và quét mã mới cho phần còn thiếu trước {deadline:%H:%M} ngày {deadline:%d/%m}; '
            f'quá hạn thì sân không được giữ và số đã chuyển sẽ được hoàn. {summary}')
        return
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

def process_gateway_callback(provider, verified, *, bank_transfer=False):
    """verified has passed the adapter's signature/merchant checks. Same path for IPN and reconciliation.

    A card/wallet gateway charges exactly the amount it was given, so any other amount is an error. A bank
    transfer (bank_transfer=True) carries whatever the customer typed: the real amount is recorded, a short
    deposit stays a partial share, and money beyond the share pays the booking or goes back to the customer."""
    with UnitOfWork() as ctx:
        payment = ctx.session.scalar(select(Payment).where(Payment.transaction_code == verified.merchant_reference))
        if (payment is None or payment.payment_method != provider or payment.booking_id is None
                or payment.payment_type not in payment_service.COLLECTED_TYPES):
            return CommandResult('NOT_FOUND', http_status=404)
        booking, _ = booking_service.lock_booking_graph(ctx, payment.booking_id)
        amount = Decimal(verified.amount)
        if verified.currency != 'VND' or (not bank_transfer and amount != Decimal(payment.amount)):
            payment.note = policy.add_note(payment.note, 'Callback sai so tien, can doi soat')
            return CommandResult('AMOUNT_MISMATCH', http_status=422)
        if payment.status in ('SUCCESS', 'REFUNDED'):
            # The code was paid before. A retry of the same notification changes nothing; a new transfer is real money.
            if bank_transfer and verified.provider_reference and not _seen(ctx, payment, verified.provider_reference):
                row = _extra_row(ctx, booking, payment, amount, verified.provider_reference)
                _place_extra(ctx, booking, row, 'Chuyển khoản thêm cho mã đã thanh toán')
                return CommandResult('EXTRA_RECORDED')
            return CommandResult('DUPLICATE', data=payment_service.apply_verified_payment(ctx, verified))
        if amount != Decimal(payment.amount):
            payment.note = policy.add_note(payment.note, f'Khach chuyen {int(amount)}d, ma yeu cau {int(Decimal(payment.amount))}d')
            payment.amount = policy.money(amount)
        result = payment_service.apply_verified_payment(ctx, verified)
        if result.late:
            _handle_late(ctx, booking, payment)
        elif result.applied:
            _after_deposit_recorded(ctx, booking, payment)
            if bank_transfer:
                _split_surplus(ctx, booking, payment, verified.provider_reference)
        return CommandResult(data=result)

EXTRA_NOTE = 'Tien chuyen them'

def _tag(provider_reference):
    return (provider_reference or 'x').split(':')[-1][:40]

def _seen(ctx, payment, provider_reference):
    """This bank transaction is already recorded, on the payment itself or as money split off it."""
    if f'gw={provider_reference}' in (payment.note or ''):
        return True
    return bool(ctx.session.scalar(select(Payment.payment_id).where(
        Payment.transaction_code.like(f'{payment.transaction_code}-{_tag(provider_reference)}%'))))

def _extra_row(ctx, booking, source, amount, provider_reference, suffix=''):
    """Money a payer sent beyond their deposit share, kept as its own receipt next to the deposit."""
    row = Payment(user_id=source.user_id, booking_id=booking.booking_id, amount=policy.money(amount),
                  payment_type='BOOKING_REMAINING_PAYMENT', payment_method=source.payment_method,
                  transaction_code=f'{source.transaction_code}-{_tag(provider_reference)}{suffix}'[:100], status='SUCCESS',
                  paid_at=ctx.now(), note=f'{EXTRA_NOTE} (ma {source.transaction_code}) | gw={provider_reference}'[:255])
    ctx.session.add(row)
    ctx.session.flush()
    return row

def _split_surplus(ctx, booking, payment, provider_reference):
    """A transfer larger than the payer's remaining share: the deposit row keeps the share, the rest is extra."""
    if payment.payment_type != 'BOOKING_DEPOSIT':
        return
    required = _required_for(booking, payment.user_id) or Decimal('0')
    paid = booking_service.paid_deposit_by_user(booking_service.payments_of(ctx, booking.booking_id)).get(payment.user_id, Decimal('0'))
    surplus = min(paid - required, Decimal(payment.amount))
    if surplus <= 0:
        return
    if surplus == Decimal(payment.amount):
        # The share was already paid by another transfer: this whole transfer is extra.
        payment.payment_type = 'BOOKING_REMAINING_PAYMENT'
        payment.note = policy.add_note(payment.note, EXTRA_NOTE)
        ctx.session.flush()
        _place_extra(ctx, booking, payment, 'Chuyển dư so với phần cọc')
        return
    payment.amount = policy.money(Decimal(payment.amount) - surplus)
    ctx.session.flush()
    _place_extra(ctx, booking, _extra_row(ctx, booking, payment, surplus, provider_reference, '-S'), 'Chuyển dư so với phần cọc')

BALANCE_REFERENCE = re.compile(r'SAN(\d{1,10})TT')

def find_balance_booking(payload):
    """Booking id from a pitch-fee transfer content (SAN<id>TT), after banks upper-case it and drop spaces."""
    for field in ('code', 'content', 'description'):
        found = BALANCE_REFERENCE.search(str(payload.get(field) or '').upper().replace(' ', ''))
        if found:
            return int(found.group(1))
    return None

@retry_conflicts
def record_balance_transfer(booking_id, amount, provider_reference, paid_at=None):
    """A bank credit for a booking's pitch-fee QR: recorded as the remaining payment without the Admin
    typing it in. Money above what is still owed, or for a booking no longer confirmed, is queued for refund."""
    from app.models import Booking
    code = f'SEPAY-{_tag(provider_reference)}'
    with UnitOfWork() as ctx:
        found = ctx.session.get(Booking, booking_id)
        if found is None or found.booking_type == 'MAINTENANCE_LOCK':
            return 'NO_REFERENCE'
        booking, payments = booking_service.lock_booking_graph(ctx, booking_id)
        if ctx.session.scalar(select(Payment.payment_id).where(Payment.transaction_code == code)):
            return 'DUPLICATE'
        row = Payment(user_id=booking.user_id, booking_id=booking_id, amount=policy.money(amount), payment_type='BOOKING_REMAINING_PAYMENT',
                      payment_method='BANK_TRANSFER', transaction_code=code, status='SUCCESS', paid_at=paid_at or ctx.now(),
                      note=f'QR tien san {compute_reference(booking_id)} | gw={provider_reference}'[:255])
        ctx.session.add(row)
        ctx.session.flush()
        if booking.status == 'CONFIRMED':
            left = compute(ctx, booking, with_qr=False).outstanding_amount
            notification_service.notify(ctx, [booking.user_id], 'PAYMENT_SUCCESS', 'Đã nhận tiền sân',
                f'Đã nhận {_vnd(amount)} chuyển khoản tiền sân. '
                + (f'Còn {_vnd(left)} trả tại sân. ' if left > 0 else 'Đã thanh toán đủ. ') + _booking_summary(ctx, booking))
        _place_extra(ctx, booking, row, 'Chuyển khoản tiền sân', tell_kept=False)
        return 'BALANCE_RECORDED'

def compute_reference(booking_id):
    from app.services.booking_balance_service import transfer_reference
    return transfer_reference(booking_id)

def _place_extra(ctx, booking, row, why, tell_kept=True):
    """Extra money first pays what the booking still owes at the pitch. Anything beyond the pitch fee, or any
    money for a booking that is no longer confirmed, goes back to the payer through the refund queue."""
    if booking.status == 'CONFIRMED':
        collected = compute(ctx, booking, with_qr=False).collected_amount
        excess = min(max(Decimal(collected) - Decimal(booking.total_amount), Decimal('0')), Decimal(row.amount))
    else:
        excess = Decimal(row.amount)
    kept = Decimal(row.amount) - excess
    if kept > 0 and tell_kept:
        notification_service.notify(ctx, [row.user_id], 'PAYMENT_SUCCESS', 'Đã trừ tiền chuyển dư vào tiền sân',
            f'{why}: {_vnd(kept)} được tính vào tiền sân còn lại. {_booking_summary(ctx, booking)}')
    if excess <= 0:
        return
    if kept > 0:
        row.amount = policy.money(kept)
        ctx.session.flush()
        row = Payment(user_id=row.user_id, booking_id=booking.booking_id, amount=policy.money(excess), payment_type=row.payment_type,
                      payment_method=row.payment_method, transaction_code=f'{row.transaction_code}-H'[:100], status='SUCCESS',
                      paid_at=row.paid_at, note=policy.add_note(row.note, 'Phan vuot gia san, hoan lai'))
        ctx.session.add(row)
        ctx.session.flush()
    refund = payment_service.create_refund(ctx, row, note=f'{why}, hoan lai'[:255])
    payment_service.notify_refund(ctx, refund, f'{why}: {_vnd(excess)} sẽ được hoàn cho bạn.')

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
