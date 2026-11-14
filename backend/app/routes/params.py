"""Constants and query/body parsing shared by the booking routes."""
from decimal import Decimal, InvalidOperation
from flask import request
from app.contracts.errors import invalid
from app.utils import validation as v

BOOKING_STATUSES = ('PENDING_HOLD', 'CONFIRMED', 'CANCELLED', 'EXPIRED', 'MAINTENANCE')
PHASES = ('UPCOMING', 'IN_PROGRESS', 'ENDED_UNPAID', 'PAID', 'DUE')
PITCH_TYPES = ('PITCH_5', 'PITCH_7', 'PITCH_11')
PAYMENT_TYPES = ('BOOKING_DEPOSIT', 'BOOKING_REMAINING_PAYMENT', 'REFUND', 'MATCH_HOST_DEPOSIT', 'MATCH_JOIN_DEPOSIT')
PAYMENT_STATUSES = ('PENDING', 'SUCCESS', 'FAILED', 'REFUND_PROCESSING', 'REFUNDED')
MANUAL_METHODS = ('CASH', 'BANK_TRANSFER')
# VENUE: the pitch could not be used, everything is refunded. CUSTOMER: the customer cancelled, the deposit is kept.
CANCEL_CAUSES = ('VENUE', 'CUSTOMER')

def reason_arg(data):
    return v.text(data['reason'], 'reason', 200)

def interval_arg(data):
    return v.timestamp(data['start_time'], 'start_time'), v.timestamp(data['end_time'], 'end_time')

def int_arg(key):
    if key not in request.args:
        return None
    try:
        return v.integer(int(request.args[key]), key)
    except ValueError:
        invalid(key)

def price_arg(key):
    if key not in request.args:
        return None
    try:
        value = Decimal(request.args[key])
    except InvalidOperation:
        invalid(key)
    if not value.is_finite() or value < 0:
        invalid(key)
    return value

def enum_arg(key, values):
    return v.enum(request.args[key], key, values) if key in request.args else None
