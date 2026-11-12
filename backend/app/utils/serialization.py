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

def post_data(post, private=False):
    result = columns(post, 'post_id title post_type team_id pitch_id pitch_type match_time end_time '
                     'skill_level payment_rule required_players current_players expiry_time status')
    plan = post.attendance_plan
    result['guest_players'] = plan['guest_players'] if plan is not None else 0
    result['registered_players'] = len(plan['user_ids']) if plan is not None else post.current_players
    result['attendance_mode'] = 'SESSION' if plan is not None else 'LEGACY_TEAM'
    if private:
        result['attendance_user_ids'] = list(plan['user_ids']) if plan is not None else None
        result['description'] = post.description
        result['matching_ready'] = bool(post.pitch_type and post.match_time and post.end_time and not post.booking_id)
    return result
