"""Booking rules fixed by the contract: 90-minute slots, 06:00-23:00 local, 10 days, 20% deposit."""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from app.contracts.errors import invalid
from app.utils.time import VIETNAM

HOLD_SECONDS = 300
SLOT_MINUTES = 90
OPENING_HOUR = 6
CLOSING_HOUR = 23
MAX_ADVANCE_DAYS = 10
# The counter books regulars weeks ahead (up to 12 weekly sessions).
ADMIN_MAX_ADVANCE_DAYS = 100
MAX_REPEAT_WEEKS = 12
DEPOSIT_PERCENT = 20

def money(value):
    return Decimal(str(value)).quantize(Decimal('0.01'))

def vnd(value):
    """Money in customer messages: 120.000 ₫"""
    return f'{int(Decimal(str(value))):,}'.replace(',', '.') + ' ₫'

def deposit_total(total_amount):
    return money((Decimal(total_amount) * DEPOSIT_PERCENT / 100).to_integral_value(ROUND_CEILING))

def split_deposit(deposit):
    """Source floors to 1 VND; opponent takes the remainder so the plan always sums to the deposit."""
    source = (Decimal(deposit) / 2).to_integral_value(ROUND_FLOOR)
    return money(source), money(Decimal(deposit) - source)

def parse_whole_vnd(value, key, allow_zero=False):
    if not isinstance(value, str):
        invalid(key, 'Tiền là chuỗi thập phân VND.')
    try:
        amount = Decimal(value)
    except InvalidOperation:
        invalid(key, 'Tiền là chuỗi thập phân VND.')
    if not amount.is_finite() or amount != amount.to_integral_value() or amount < 0 or (amount == 0 and not allow_zero):
        invalid(key, 'Số tiền phải là VND nguyên đồng và dương.')
    if amount >= Decimal('10000000000'):
        invalid(key, 'Số tiền vượt giới hạn.')
    return money(amount)

def day_slots(local_date):
    start = datetime(local_date.year, local_date.month, local_date.day, OPENING_HOUR, tzinfo=VIETNAM)
    closing = datetime(local_date.year, local_date.month, local_date.day, CLOSING_HOUR, tzinfo=VIETNAM)
    step = timedelta(minutes=SLOT_MINUTES)
    while start + step <= closing:
        yield start, start + step
        start += step

def validate_slot(now, start, end, max_days=MAX_ADVANCE_DAYS):
    if end - start != timedelta(minutes=SLOT_MINUTES):
        invalid('end_time', 'Mỗi lượt đúng 90 phút.')
    if start <= now:
        invalid('start_time', 'Giờ bắt đầu phải ở tương lai.')
    local = start.astimezone(VIETNAM)
    if local.date() > now.astimezone(VIETNAM).date() + timedelta(days=max_days):
        invalid('start_time', f'Chỉ đặt trước tối đa {max_days} ngày.')
    if (local, end.astimezone(VIETNAM)) not in list(day_slots(local.date())):
        invalid('start_time', 'Giờ phải theo lưới 90 phút từ 06:00 đến 23:00 giờ Việt Nam.')

NOTE_LIMIT = 255
# Markers the code reads back from a note (consolidated receipt, forfeited deposit, bank transaction id,
# merged deposit, demo money). Shortening a note must never drop one of them.
NOTE_MARKERS = ('THU_GOP', 'MAT_COC', 'gw=', 'MERGED_FROM', 'DEMO_ONLY')

def add_note(current, text):
    """payments.note and bookings.note are VARCHAR(255). When full, the oldest plain remarks go first;
    marker segments and the newest remark stay, in order."""
    if current and text in current:
        return current
    parts = (current.split(' | ') if current else []) + [text]
    while len(' | '.join(parts)) > NOTE_LIMIT:
        plain = next((i for i, part in enumerate(parts[:-1]) if not any(m in part for m in NOTE_MARKERS)), None)
        if plain is None:
            break
        del parts[plain]
    return ' | '.join(parts)[:NOTE_LIMIT]
