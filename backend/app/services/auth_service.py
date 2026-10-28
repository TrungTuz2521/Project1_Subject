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

def require_active_actor(ctx, actor):
    user = ctx.session.get(User, actor.user_id, populate_existing=True)
    if not user:
        raise DomainError('UNAUTHORIZED', 'Phiên đăng nhập không hợp lệ.', 401)
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
    if phone and ctx.session.scalar(select(User.user_id).where(User.phone == phone)):
        raise DomainError('PHONE_EXISTS', 'Số điện thoại đã được sử dụng.', 409)
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
    now = ctx.now()
    token = jwt.encode({'sub': str(user.user_id), 'role': user.role, 'iat': now,
                        'exp': now + timedelta(seconds=3600), 'iss': current_app.config['JWT_ISSUER'],
                        'aud': current_app.config['JWT_AUDIENCE']}, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')
    return {'access_token': token, 'expires_in': 3600, 'user': user_self(user)}

def update_profile(ctx, actor, data):
    user = require_active_actor(ctx, actor)
    v.fields(data, ('full_name', 'phone', 'skill_level'))
    if 'full_name' in data:
        user.full_name = v.text(data['full_name'], 'full_name', 100, 2)
    if 'phone' in data:
        phone = v.text(data['phone'], 'phone', 20, nullable=True)
        if phone and ctx.session.scalar(select(User.user_id).where(User.phone == phone, User.user_id != user.user_id)):
            raise DomainError('PHONE_EXISTS', 'Số điện thoại đã được sử dụng.')
        user.phone = phone
    if 'skill_level' in data:
        user.skill_level = v.enum(data['skill_level'], 'skill_level', SKILLS)
    return user_self(user)
