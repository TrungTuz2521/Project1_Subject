from functools import wraps
import jwt
from flask import request, current_app, g
from app.contracts.dto import Actor
from app.contracts.errors import DomainError

def authenticated(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        header = request.headers.get('Authorization', '')
        try:
            if not header.startswith('Bearer '):
                raise ValueError()
            claims = jwt.decode(header[7:], current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'],
                                issuer=current_app.config['JWT_ISSUER'], audience=current_app.config['JWT_AUDIENCE'],
                                options={'require': ['sub', 'role', 'iat', 'exp', 'iss', 'aud']})
            uid = int(claims['sub'])
            if uid <= 0 or claims['role'] not in ('PLAYER', 'ADMIN'):
                raise ValueError()
            g.actor = Actor(uid, claims['role'])
        except jwt.ExpiredSignatureError:
            raise DomainError('TOKEN_EXPIRED', 'Phiên đăng nhập đã hết hạn.', 401)
        except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
            raise DomainError('UNAUTHORIZED', 'Phiên đăng nhập không hợp lệ.', 401)
        return fn(*args, **kwargs)
    return wrapped
