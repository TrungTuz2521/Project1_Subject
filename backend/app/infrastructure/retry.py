from functools import wraps
from sqlalchemy.exc import OperationalError

def retry_conflicts(fn):
    """Retry only known rolled-back DB conflicts, never unknown connection/commit errors."""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        for attempt in range(3):
            try:
                return fn(*args, **kwargs)
            except OperationalError as error:
                code = getattr(error.orig, 'args', (None,))[0]
                if code not in (1205, 1213, 9007) or attempt == 2:
                    raise
    return wrapped
