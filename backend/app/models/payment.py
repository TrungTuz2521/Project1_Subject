from app.extensions import db
from app.utils.time import UTCDateTime, utcnow

class Payment(db.Model):
    __tablename__ = 'payments'
    payment_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.booking_id'))
    post_id = db.Column(db.Integer, db.ForeignKey('match_posts.post_id'))
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_type = db.Column(db.String(32), nullable=False)
    payment_method = db.Column(db.String(16), nullable=False)
    transaction_code = db.Column(db.String(100), unique=True)
    refund_for_payment_id = db.Column(db.Integer, db.ForeignKey('payments.payment_id'))
    recorded_by_admin_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    status = db.Column(db.String(32), nullable=False, default='PENDING')
    paid_at = db.Column(UTCDateTime())
    note = db.Column(db.String(255))
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at = db.Column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)
