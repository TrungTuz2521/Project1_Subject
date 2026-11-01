from decimal import Decimal
from flask import current_app
from app.contracts.dto import BookingBalance
from app.services import booking_policy as policy, booking_service

def crc16(text):
    """CRC-16/CCITT-FALSE required by EMVCo QR."""
    crc = 0xFFFF
    for byte in text.encode('utf-8'):
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f'{crc:04X}'

def _tlv(tag, value):
    return f'{tag}{len(value):02d}{value}'

def bank_qr_payload(bin_code, account_no, amount, reference):
    """Plain VietQR content. It only suggests a transfer; scanning it never records a payment."""
    beneficiary = _tlv('00', bin_code) + _tlv('01', account_no)
    merchant = _tlv('00', 'A000000727') + _tlv('01', beneficiary) + _tlv('02', 'QRIBFTTA')
    body = (_tlv('00', '01') + _tlv('01', '12') + _tlv('38', merchant) + _tlv('53', '704')
            + _tlv('54', str(int(amount))) + _tlv('58', 'VN') + _tlv('62', _tlv('08', reference)) + '6304')
    return body + crc16(body)

def transfer_reference(booking_id):
    return f'BOOKING-{booking_id}'

def compute(ctx, booking, payments=None, with_qr=True):
    rows = payments if payments is not None else booking_service.payments_of(ctx, booking.booking_id)
    def gross(kind):
        return sum((Decimal(p.amount) for p in rows if p.payment_type == kind and p.status in ('SUCCESS', 'REFUNDED')), Decimal('0'))
    deposit, remaining = gross('BOOKING_DEPOSIT'), gross('BOOKING_REMAINING_PAYMENT')
    refunds = sum((Decimal(p.amount) for p in rows if p.payment_type == 'REFUND' and p.status == 'SUCCESS'), Decimal('0'))
    total, collected = Decimal(booking.total_amount), deposit + remaining - refunds
    outstanding = max(total - collected, Decimal('0'))
    status = 'PAID' if total > 0 and outstanding == 0 else 'PARTIAL' if collected > 0 else 'UNPAID'
    qr, reference, reason = None, None, None
    if with_qr:
        qr, reference, reason = _qr(ctx, booking, outstanding, collected)
    return BookingBalance(booking.booking_id, booking.payment_rule, policy.money(total), policy.money(deposit),
                          policy.money(remaining), policy.money(collected), policy.money(outstanding), status,
                          qr, reference, reason)

def _qr(ctx, booking, outstanding, collected):
    if collected > Decimal(booking.total_amount):
        return None, None, 'Đã thu vượt giá sân, cần đối soát.'
    if outstanding == 0:
        return None, None, None
    if booking.status != 'CONFIRMED':
        return None, None, 'Booking chưa xác nhận hoặc đã kết thúc.'
    if ctx.now() < booking.end_time:
        return None, None, 'Chưa hết giờ đá.'
    reference = transfer_reference(booking.booking_id)
    bin_code, account = current_app.config.get('BANK_BIN'), current_app.config.get('BANK_ACCOUNT_NO')
    if not bin_code or not account:
        return None, reference, 'Chưa cấu hình tài khoản ngân hàng nhận tiền.'
    return bank_qr_payload(bin_code, account, outstanding, reference), reference, None
