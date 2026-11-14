from app.extensions import db
from app.utils.time import UTCDateTime, utcnow

class FieldComplex(db.Model):
    __tablename__ = 'field_complexes'
    complex_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    peak_start_time = db.Column(db.String(5))  # 'HH:MM' local, inclusive (migration 005)
    peak_end_time = db.Column(db.String(5))  # 'HH:MM' local, exclusive
    weekend_is_peak = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)
