"""Throwaway API for the Postman collection: fresh SQLite in a temp folder, never TiDB, even when .env exists.

Usage, from backend: python postman/run_local.py [port]
All secrets below are test-only. Restart to reset the data.
"""
import shutil
import sys
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
import bcrypt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Booking, FieldComplex, Payment, Pitch, User
from app.services.booking_policy import day_slots
from app.utils.time import VIETNAM, utcnow

PASSWORD = b'Password123!'
USERS = (('admin@example.test', 'ADMIN'), ('player1@example.test', 'PLAYER'), ('player2@example.test', 'PLAYER'))

def seed():
    password_hash = bcrypt.hashpw(PASSWORD, bcrypt.gensalt(rounds=4)).decode()
    with UnitOfWork() as ctx:
        ctx.session.add(FieldComplex(complex_id=1, name='Cụm sân Postman', phone='0900000000', address='Hà Nội'))
        ctx.session.flush()
        ctx.session.add_all([
            Pitch(pitch_id=1, complex_id=1, pitch_name='Sân 5A', pitch_type='PITCH_5', price_per_slot=Decimal('600000')),
            Pitch(pitch_id=2, complex_id=1, pitch_name='Sân 7A', pitch_type='PITCH_7', price_per_slot=Decimal('900000')),
            Pitch(pitch_id=3, complex_id=1, pitch_name='Sân tạm dừng', pitch_type='PITCH_7', price_per_slot=Decimal('600000'), status='INACTIVE'),
        ])
        users = [User(full_name=email.split('@')[0], email=email, password_hash=password_hash, role=role) for email, role in USERS]
        ctx.session.add_all(users)
        ctx.session.flush()
        # An API call cannot create a booking in the past, and confirm-paid needs one that has ended.
        now = utcnow().replace(microsecond=0)
        start, end = list(day_slots(now.astimezone(VIETNAM).date() - timedelta(days=1)))[8]
        player = users[1].user_id
        ended = Booking(pitch_id=1, user_id=player, start_time=start, end_time=end, total_amount=Decimal('600000'), deposit_amount=Decimal('120000'),
                        booking_type='ONLINE', status='CONFIRMED', payment_rule='DIRECT_BOOKING', payer_plan=[{'user_id': player, 'amount': '120000.00'}])
        ctx.session.add(ended)
        ctx.session.flush()
        ctx.session.add(Payment(user_id=player, booking_id=ended.booking_id, amount=Decimal('120000'), payment_type='BOOKING_DEPOSIT', payment_method='VNPAY',
                                transaction_code='SEED-ENDED-DEPOSIT', status='SUCCESS', paid_at=start - timedelta(hours=1)))

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    folder = tempfile.mkdtemp(prefix='postman-api-')
    try:
        app = create_app({'SQLALCHEMY_DATABASE_URI': f'sqlite:///{Path(folder, "postman.db").as_posix()}', 'SQLALCHEMY_ENGINE_OPTIONS': {},
                          'JWT_SECRET_KEY': 'postman-local-only-secret-not-for-production',
                          'VNPAY_TMN_CODE': 'POSTMAN1', 'VNPAY_HASH_SECRET': 'postman-local-only-hash-secret', 'VNPAY_RETURN_URL': 'http://localhost:5173/bookings',
                          'BANK_BIN': '970436', 'BANK_ACCOUNT_NO': '0011001234567', 'AUTH_RATE_LIMIT': 100000})
        with app.app_context():
            db.create_all()
            seed()
        print(f'Postman API: http://127.0.0.1:{port}/api/v1 (SQLite tam, tat la mat du lieu)')
        app.run(host='127.0.0.1', port=port, threaded=True)
    finally:
        shutil.rmtree(folder, ignore_errors=True)

if __name__ == '__main__':
    main()
