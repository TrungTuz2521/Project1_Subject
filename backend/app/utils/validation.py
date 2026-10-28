import re
from datetime import datetime, timezone
from app.contracts.errors import invalid

def fields(data, allowed, required=()):
    if not isinstance(data, dict):
        invalid('body', 'Cần JSON object.')
    for key in set(data) - set(allowed):
        invalid(key, 'Trường không được phép ghi.')
    for key in required:
        if key not in data:
            invalid(key, 'Trường bắt buộc.')
    return data

def text(value, key, maximum, minimum=1, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        invalid(key, f'Độ dài từ {minimum} đến {maximum} ký tự.')
    return value.strip()

def enum(value, key, values):
    if not isinstance(value, str) or value not in values:
        invalid(key)
    return value

def integer(value, key, minimum=1, maximum=2147483647):
    if type(value) is not int or not minimum <= value <= maximum:
        invalid(key)
    return value

def email(value):
    value = text(value, 'email', 150).lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        invalid('email')
    return value

def timestamp(value, key):
    if not isinstance(value, str):
        invalid(key, 'Cần ISO 8601 kèm múi giờ.')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except ValueError:
        invalid(key, 'Cần ISO 8601 kèm múi giờ.')
