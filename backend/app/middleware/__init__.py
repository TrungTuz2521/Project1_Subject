from functools import wraps
import jwt
from flask import request, current_app, g
from app.contracts.dto import Actor
from app.contracts.errors import DomainError

def decode_actor(header):
    """Bearer header -> Actor. Raises DomainError 401 for a missing, expired or malformed token."""
    try:
        if not header.startswith('Bearer '):
            raise ValueError()
        claims = jwt.decode(header[7:], current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'],
                            issuer=current_app.config['JWT_ISSUER'], audience=current_app.config['JWT_AUDIENCE'],
                            options={'require': ['sub', 'role', 'skey', 'iat', 'exp', 'iss', 'aud']})
        uid = int(claims['sub'])
        if uid <= 0 or claims['role'] not in ('PLAYER', 'ADMIN') or not isinstance(claims['skey'], str):
            raise ValueError()
        return Actor(uid, claims['role'], claims['skey'])
    except jwt.ExpiredSignatureError:
        raise DomainError('TOKEN_EXPIRED', 'Phiên đăng nhập đã hết hạn.', 401)
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise DomainError('UNAUTHORIZED', 'Phiên đăng nhập không hợp lệ.', 401)

def authenticated(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        g.actor = decode_actor(request.headers.get('Authorization', ''))
        return fn(*args, **kwargs)
    return wrapped

def optional_actor():
    """Public endpoints that show more to the owner: an absent or unusable token means anonymous."""
    header = request.headers.get('Authorization', '')
    if not header:
        return None
    try:
        return decode_actor(header)
    except DomainError:
        return None
