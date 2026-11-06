from app.extensions import db
from app.utils.time import UTCDateTime, utcnow

class Booking(db.Model):
    __tablename__ = 'bookings'
    booking_id = db.Column(db.Integer, primary_key=True)
    pitch_id = db.Column(db.Integer, db.ForeignKey('pitches.pitch_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    start_time = db.Column(UTCDateTime(), nullable=False)
    end_time = db.Column(UTCDateTime(), nullable=False)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    deposit_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    booking_type = db.Column(db.String(16), nullable=False, default='ONLINE')
    status = db.Column(db.String(16), nullable=False, default='PENDING_HOLD')
    hold_expires_at = db.Column(UTCDateTime())
    note = db.Column(db.String(255))
    payment_rule = db.Column(db.String(32))
    payer_plan = db.Column(db.JSON)
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at = db.Column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)
