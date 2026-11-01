from sqlalchemy.orm import Session
from flask import current_app
from app.extensions import db
from app.utils.time import utcnow
from app.infrastructure.lock_manager import LockManager

class UnitOfWork:
    """Independent Session per command; nested services must never commit."""
    def __enter__(self):
        self.session = Session(db.engine, expire_on_commit=False)
        self.now = current_app.config.get('CLOCK', utcnow)
        self.locks = LockManager(self.session)
        return self
    def __exit__(self, kind, value, traceback):
        try:
            if kind is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()
