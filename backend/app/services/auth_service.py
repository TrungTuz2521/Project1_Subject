import hashlib
import hmac
import re
import bcrypt
import jwt
from datetime import timedelta
from flask import current_app
from sqlalchemy import select
from app.contracts.errors import DomainError, invalid
from app.contracts.enums import SKILLS
from app.models import User
from app.utils import validation as v
from app.utils.serialization import user_self

def session_key(user):
    """Changes whenever the password hash changes, so a new password revokes every JWT issued before it,
    on every device, without a new column or a token denylist."""
    secret = current_app.config['JWT_SECRET_KEY'].encode()
    material = f'{user.user_id}:{user.password_hash or ""}'.encode()
    return hmac.new(secret, material, hashlib.sha256).hexdigest()[:32]

# Walk-in customers booked at the counter: a users row (bookings need one) that can never sign in.
# The reserved .invalid domain is skipped by the email worker and is never a Google/registered address.
WALK_IN_DOMAIN = 'walkin.invalid'

def is_walk_in(user):
    return bool(user and user.email and user.email.endswith('@' + WALK_IN_DOMAIN) and not user.password_hash and not user.google_id)

def normalize_phone(value, key='phone'):
    phone = v.text(value, key, 20).replace(' ', '').replace('.', '').replace('-', '')
    if not re.fullmatch(r'\+?\d{9,15}', phone):
        invalid(key, 'Số điện thoại gồm 9-15 chữ số.')
    return phone

def walk_in_customer(ctx, full_name, phone):
    """Reuse the walk-in profile with this phone, or create one. A phone owned by a real account is
    refused, so the Admin picks that account instead of creating a duplicate person."""
    from secrets import token_hex
    name, phone = v.text(full_name, 'guest.full_name', 100, 2), normalize_phone(phone, 'guest.phone')
    owner = ctx.session.scalar(select(User).where(User.phone == phone))
    if owner is not None and not is_walk_in(owner):
        raise DomainError('PHONE_BELONGS_TO_ACCOUNT', 'Số điện thoại đã có tài khoản.', 409,
                          {'guest.phone': f'Số này thuộc tài khoản {owner.full_name} ({owner.email}). Chọn "Khách có tài khoản" và tìm theo số điện thoại.'})
    if owner is not None:
        if owner.status != 'ACTIVE':
            raise DomainError('ACCOUNT_DISABLED', 'Khách này đang bị khóa.', 403)
        owner.full_name = name  # Latest name given at the counter wins.
        return owner
    guest = User(full_name=name, phone=phone, email=f'walkin-{token_hex(8)}@{WALK_IN_DOMAIN}', password_hash=None,
                 role='PLAYER', status='ACTIVE')
    ctx.session.add(guest)
    ctx.session.flush()
    return guest

def _claim_phone(ctx, phone, user_id=None):
    """A phone held only by a walk-in profile moves to the person registering it; a real owner still blocks."""
    owner = ctx.session.scalar(select(User).where(User.phone == phone, *( [User.user_id != user_id] if user_id else [])))
    if owner is None:
        return
    if not is_walk_in(owner):
        raise DomainError('PHONE_EXISTS', 'Số điện thoại đã được sử dụng.', 409)
    owner.phone = None  # Its bookings keep the phone in their note.
    ctx.session.flush()

def require_active_actor(ctx, actor):
    user = ctx.session.get(User, actor.user_id, populate_existing=True)
    if not user:
        raise DomainError('UNAUTHORIZED', 'Phiên đăng nhập không hợp lệ.', 401)
    if actor.session_key is not None and not hmac.compare_digest(actor.session_key, session_key(user)):
        raise DomainError('SESSION_REVOKED', 'Mật khẩu đã thay đổi. Vui lòng đăng nhập lại.', 401)
    if user.status != 'ACTIVE':
        raise DomainError('ACCOUNT_DISABLED', 'Tài khoản không hoạt động.', 403)
    if user.role != actor.role:
        raise DomainError('UNAUTHORIZED', 'Quyền tài khoản đã thay đổi. Đăng nhập lại.', 401)
    return user

def require_admin(ctx, actor):
    user = require_active_actor(ctx, actor)
    if user.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Cần quyền Admin.', 403)
    return user

def require_player(ctx, actor):
    user = require_active_actor(ctx, actor)
    if user.role != 'PLAYER':
        raise DomainError('FORBIDDEN', 'Thao tác dành cho người chơi.', 403)
    return user

def register(ctx, full_name, email, password, phone=None, skill_level=None):
    name = v.text(full_name, 'full_name', 100, 2)
    address = v.email(email)
    if not isinstance(password, str) or not 8 <= len(password.encode('utf-8')) <= 72:
        invalid('password', 'Mật khẩu phải dài 8–72 byte UTF-8.')
    phone = v.text(phone, 'phone', 20, nullable=True)
    skill = v.enum('AMATEUR' if skill_level is None else skill_level, 'skill_level', SKILLS)
    if ctx.session.scalar(select(User.user_id).where(User.email == address)):
        raise DomainError('EMAIL_EXISTS', 'Email đã được đăng ký.', 409)
    if phone:
        _claim_phone(ctx, phone)
    user = User(full_name=name, email=address, phone=phone, skill_level=skill,
                password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(), role='PLAYER', status='ACTIVE')
    ctx.session.add(user)
    ctx.session.flush()
    return user_self(user)

_DUMMY = bcrypt.hashpw(b'dummy-password', bcrypt.gensalt())

def login(ctx, email, password):
    address = v.email(email)
    if not isinstance(password, str) or not 1 <= len(password.encode()) <= 72:
        raise DomainError('INVALID_CREDENTIALS', 'Email hoặc mật khẩu không chính xác.', 401)
    user = ctx.session.scalar(select(User).where(User.email == address))
    hashed = user.password_hash.encode() if user and user.password_hash else _DUMMY
    try:
        correct = bcrypt.checkpw(password.encode(), hashed)
    except ValueError:
        correct = False  # Legacy plaintext seed is never accepted as a hash.
    if not correct or not user:
        raise DomainError('INVALID_CREDENTIALS', 'Email hoặc mật khẩu không chính xác.', 401)
    if user.status != 'ACTIVE':
        raise DomainError('ACCOUNT_DISABLED', 'Tài khoản không hoạt động.', 403)
    return issue_session(ctx, user)

def issue_session(ctx, user):
    now = ctx.now()
    token = jwt.encode({'sub': str(user.user_id), 'role': user.role, 'skey': session_key(user), 'iat': now,
                        'exp': now + timedelta(seconds=3600), 'iss': current_app.config['JWT_ISSUER'],
                        'aud': current_app.config['JWT_AUDIENCE']}, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')
    return {'access_token': token, 'expires_in': 3600, 'user': user_self(user)}

def change_password(ctx, actor, current_password, new_password, confirm_password):
    ctx.locks.users([actor.user_id])
    user = require_active_actor(ctx, actor)
    if not user.password_hash:
        raise DomainError('PASSWORD_NOT_SET', 'Tài khoản này chỉ dùng Google và chưa có mật khẩu web.', 409)
    correct = False
    if isinstance(current_password, str) and 1 <= len(current_password.encode('utf-8')) <= 72:
        try:
            correct = bcrypt.checkpw(current_password.encode('utf-8'), user.password_hash.encode('utf-8'))
        except ValueError:
            pass
    if not correct:
        invalid('current_password', 'Mật khẩu hiện tại không chính xác.')
    if not isinstance(new_password, str) or not 8 <= len(new_password.encode('utf-8')) <= 72:
        invalid('new_password', 'Mật khẩu mới phải dài 8–72 byte UTF-8.')
    if new_password != confirm_password:
        invalid('confirm_password', 'Mật khẩu nhập lại chưa khớp.')
    if new_password == current_password:
        invalid('new_password', 'Mật khẩu mới phải khác mật khẩu hiện tại.')
    user.password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    ctx.session.flush()
    return {'changed': True}


def update_profile(ctx, actor, data):
    user = require_active_actor(ctx, actor)
    v.fields(data, ('full_name', 'phone', 'skill_level'))
    if 'full_name' in data:
        user.full_name = v.text(data['full_name'], 'full_name', 100, 2)
    if 'phone' in data:
        phone = v.text(data['phone'], 'phone', 20, nullable=True)
        if phone:
            _claim_phone(ctx, phone, user.user_id)
        user.phone = phone
    if 'skill_level' in data:
        user.skill_level = v.enum(data['skill_level'], 'skill_level', SKILLS)
    return user_self(user)
