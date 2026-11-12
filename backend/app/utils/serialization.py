from dataclasses import is_dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal

def encode(value):
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [encode(v) for v in value]
    if isinstance(value, Decimal):
        return format(value, '.2f')
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    return value

def columns(row, names):
    return {key: getattr(row, key) for key in names.split()}

def user_self(user):
    return {**columns(user, 'user_id full_name email phone role skill_level status refund_bank_name refund_account_no refund_account_name'),
            'has_password': bool(user.password_hash)}
