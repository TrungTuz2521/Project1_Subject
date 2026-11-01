from datetime import datetime, timezone, timedelta
from sqlalchemy.types import TypeDecorator, DateTime
VIETNAM = timezone(timedelta(hours=7))

def utcnow():
    return datetime.now(timezone.utc)

class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True
    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError('Datetime must include timezone')
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None
