from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from flask import request
from app.contracts.errors import DomainError

def install_auth_limit(app):
    """Local development limiter. Deployments can supply a shared limiter at the proxy."""
    buckets, lock = defaultdict(deque), Lock()
    @app.before_request
    def limit_auth():
        if request.path not in ('/api/v1/auth/login', '/api/v1/auth/register') or request.method != 'POST':
            return
        limit = app.config.get('AUTH_RATE_LIMIT', 20)
        if not limit:
            return
        now, key = monotonic(), request.remote_addr
        with lock:
            # Drop stale IP buckets as well as timestamps to bound memory growth.
            if len(buckets) > 10000:
                for ip in list(buckets):
                    if not buckets[ip] or buckets[ip][-1] <= now - 60:
                        del buckets[ip]
                if key not in buckets and len(buckets) > 10000:
                    raise DomainError('RATE_LIMITED', 'Quá nhiều yêu cầu. Thử lại sau.', 429)
            queue = buckets[key]
            while queue and queue[0] <= now - 60:
                queue.popleft()
            if len(queue) >= limit:
                raise DomainError('RATE_LIMITED', 'Quá nhiều yêu cầu. Thử lại sau một phút.', 429)
            queue.append(now)
