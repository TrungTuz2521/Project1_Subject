from sqlalchemy import select, inspect
from app.contracts.enums import LOCK_ORDER

class LockManager:
    def __init__(self, session):
        self.session, self.last, self.held = session, (-1, -1), set()
    def lock(self, model, ids):
        pk = inspect(model).primary_key[0]
        rows = []
        for value in sorted(set(i for i in ids if i is not None)):
            key = (LOCK_ORDER.index(model.__tablename__), value)
            if key not in self.held:
                if key < self.last:
                    raise RuntimeError('Lock order changed; restart the entire command.')
                self.last = key
                self.held.add(key)
            row = self.session.scalar(select(model).where(pk == value).with_for_update()
                                      .execution_options(populate_existing=True))
            if row is not None:
                rows.append(row)
        return rows

    def users(self, user_ids):
        """Serialize availability across different teams sharing the same player."""
        from app.models import User
        return self.lock(User, user_ids)
