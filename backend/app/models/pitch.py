from app.extensions import db
from app.utils.time import UTCDateTime, utcnow

class Pitch(db.Model):
    __tablename__ = 'pitches'
    pitch_id = db.Column(db.Integer, primary_key=True)
    complex_id = db.Column(db.Integer, db.ForeignKey('field_complexes.complex_id'), nullable=False)
    pitch_name = db.Column(db.String(100), nullable=False)
    pitch_type = db.Column(db.String(16), nullable=False)
    price_per_slot = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(16), nullable=False, default='ACTIVE')
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)
