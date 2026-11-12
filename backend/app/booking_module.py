"""Booking, payment and pitch settings plus their routes and CLI commands, installed by the app factory."""
import os
from app.jobs.booking_jobs import register_booking_commands
from app.routes.admin_api import admin_api
from app.routes.booking_api import booking_api

SETTINGS = {'VNPAY_TMN_CODE': '', 'VNPAY_HASH_SECRET': '', 'VNPAY_RETURN_URL': '',
            'VNPAY_PAY_URL': 'https://sandbox.vnpayment.vn/paymentv2/vpcpay.html',
            'VNPAY_API_URL': 'https://sandbox.vnpayment.vn/merchant_webapi/api/transaction',
            'BANK_BIN': '', 'BANK_ACCOUNT_NO': '', 'BANK_NAME': '', 'BANK_ACCOUNT_NAME': '',
            # SePay webhook "API Key". Empty = QR auto-confirmation off and the webhook answers 503.
            'SEPAY_WEBHOOK_KEY': ''}
# QR lifetime shown to the payer, and how long after it a slow bank notification still confirms the hold.
INT_SETTINGS = {'SEPAY_QR_TTL_SECONDS': 60, 'SEPAY_CONFIRM_GRACE_SECONDS': 120}

def install(app):
    for key, default in SETTINGS.items():
        app.config.setdefault(key, (os.getenv(key) or default).strip())
    for key, default in INT_SETTINGS.items():
        app.config.setdefault(key, int(os.getenv(key) or default))
    app.register_blueprint(booking_api, url_prefix='/api/v1')
    app.register_blueprint(admin_api, url_prefix='/api/v1')
    register_booking_commands(app)
