"""Slot price: the pitch's normal price, or its peak price when the slot starts inside the complex's peak hours.

The price is fixed onto the booking when it is created (booking.total_amount), so later price changes never
alter what an existing customer owes.
"""
import re
from app.contracts.errors import invalid
from app.models import FieldComplex
from app.services import booking_policy as policy
from app.utils.time import VIETNAM

HHMM = re.compile(r'([01]\d|2[0-3]):[0-5]\d')


def minutes(text):
    hours, mins = text.split(':')
    return int(hours) * 60 + int(mins)


def is_peak(complex_row, start):
    if complex_row is None:
        return False
    local = start.astimezone(VIETNAM)
    if complex_row.weekend_is_peak and local.weekday() >= 5:
        return True
    if complex_row.peak_start_time and complex_row.peak_end_time:
        return minutes(complex_row.peak_start_time) <= local.hour * 60 + local.minute < minutes(complex_row.peak_end_time)
    return False


def slot_price(ctx, pitch, start):
    """Returns (price, is_peak) for a slot of this pitch starting at `start`."""
    complex_row = ctx.session.get(FieldComplex, pitch.complex_id)
    peak = pitch.peak_price_per_slot is not None and is_peak(complex_row, start)
    return policy.money(pitch.peak_price_per_slot if peak else pitch.price_per_slot), peak


def peak_config(complex_row):
    return {'peak_start_time': complex_row.peak_start_time, 'peak_end_time': complex_row.peak_end_time,
            'weekend_is_peak': bool(complex_row.weekend_is_peak)}


def validate_window(start, end):
    """Both empty = no daily peak window; otherwise HH:MM inside opening hours, start before end."""
    if not start and not end:
        return None, None
    if not (isinstance(start, str) and HHMM.fullmatch(start)):
        invalid('peak_start_time', 'Giờ bắt đầu cao điểm dạng HH:MM, ví dụ 17:00.')
    if not (isinstance(end, str) and HHMM.fullmatch(end)):
        invalid('peak_end_time', 'Giờ kết thúc cao điểm dạng HH:MM, ví dụ 21:00.')
    if not policy.OPENING_HOUR * 60 <= minutes(start) < minutes(end) <= policy.CLOSING_HOUR * 60:
        invalid('peak_end_time', f'Khung cao điểm phải nằm trong {policy.OPENING_HOUR:02d}:00–{policy.CLOSING_HOUR:02d}:00 và bắt đầu trước khi kết thúc.')
    return start, end
