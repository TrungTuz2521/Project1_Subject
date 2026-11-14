"""Google Identity Services: verify external identity, then issue our own 60-minute JWT."""
import secrets
import bcrypt
import requests
from flask import current_app, request
from google.oauth2 import id_token
from google.auth.transport.requests import Request
from google.auth.exceptions import GoogleAuthError, TransportError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import select
from app.contracts.errors import DomainError
from app.models import User
from app.services.auth_service import issue_session
from app.utils import validation as v


def require_web_origin():
    # JSON + explicit origin allowlist prevent login CSRF; bearer sessions use no cookies.
    if request.headers.get('Origin') not in current_app.config['CORS_ORIGINS']:
        raise DomainError('FORBIDDEN_ORIGIN', 'Hãy đăng nhập từ trang web của dự án.', 403)


def configured_client():
    value = current_app.config.get('GOOGLE_CLIENT_ID', '').strip()
    if not value:
        raise DomainError('GOOGLE_NOT_CONFIGURED', 'Đăng nhập Google chưa được cấu hình.', 503)
    return value


def signer():
    return URLSafeTimedSerializer(current_app.config['JWT_SECRET_KEY'], salt='google-login-nonce-v1')


def challenge():
    configured_client()
    nonce = secrets.token_urlsafe(32)
    return {'nonce': nonce, 'challenge': signer().dumps(nonce)}


class TimedRequest(Request):
    def __call__(self, *args, **kwargs):
        kwargs['timeout'] = 10
        return super().__call__(*args, **kwargs)


def verify_credential(credential, signed_challenge):
    client_id = configured_client()
    if not isinstance(credential, str) or not 1 <= len(credential) <= 16384:
        raise DomainError('INVALID_GOOGLE_TOKEN', 'Thông tin đăng nhập Google không hợp lệ.', 401)
    if not isinstance(signed_challenge, str) or len(signed_challenge) > 1024:
        raise DomainError('INVALID_GOOGLE_TOKEN', 'Vui lòng thử đăng nhập Google lại.', 401)
    try:
        nonce = signer().loads(signed_challenge, max_age=600)
    except (BadSignature, SignatureExpired):
        raise DomainError('INVALID_GOOGLE_TOKEN', 'Phiên đăng nhập Google hết hạn. Vui lòng thử lại.', 401)
    try:
        with requests.Session() as transport:
            claims = id_token.verify_oauth2_token(credential, TimedRequest(session=transport), client_id)
    except TransportError:
        raise DomainError('GOOGLE_UNAVAILABLE', 'Chưa kết nối được Google. Vui lòng thử lại.', 503)
    except (ValueError, GoogleAuthError):
        raise DomainError('INVALID_GOOGLE_TOKEN', 'Thông tin đăng nhập Google không hợp lệ hoặc đã hết hạn.', 401)
    if (claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com')
            or claims.get('aud') != client_id or claims.get('nonce') != nonce
            or claims.get('email_verified') is not True
            or not isinstance(claims.get('sub'), str) or not 1 <= len(claims['sub']) <= 100):
        raise DomainError('INVALID_GOOGLE_TOKEN', 'Không xác minh được tài khoản Google.', 401)
    return claims


def sign_in(ctx, identity, password=None):
    subject = identity['sub']
    user = ctx.session.scalar(select(User).where(User.google_id == subject).with_for_update())
    if not user:
        email = v.email(identity.get('email'))
        user = ctx.session.scalar(select(User).where(User.email == email).with_for_update())
        if user:
            if user.status != 'ACTIVE':
                raise DomainError('ACCOUNT_DISABLED', 'Tài khoản không hoạt động.', 403)
            if user.google_id and user.google_id != subject:
                raise DomainError('GOOGLE_ACCOUNT_CONFLICT', 'Email đã liên kết với tài khoản Google khác.', 409)
            correct = False
            if isinstance(password, str) and 1 <= len(password.encode()) <= 72 and user.password_hash:
                try:
                    correct = bcrypt.checkpw(password.encode(), user.password_hash.encode())
                except ValueError:
                    pass
            if not correct:
                raise DomainError('ACCOUNT_LINK_REQUIRED', 'Email đã có tài khoản. Nhập mật khẩu hiện tại của web ở ô Mật khẩu, rồi bấm Google lại để liên kết.', 409)
            user.google_id = subject
        else:
            name = identity.get('name')
            name = name.strip()[:100] if isinstance(name, str) else ''
            user = User(full_name=name or email.split('@')[0], email=email, google_id=subject,
                        role='PLAYER', status='ACTIVE', skill_level='AMATEUR')
            ctx.session.add(user)
    if user.status != 'ACTIVE':
        raise DomainError('ACCOUNT_DISABLED', 'Tài khoản không hoạt động.', 403)
    ctx.session.flush()
    return issue_session(ctx, user)
