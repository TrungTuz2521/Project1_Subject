"""Wires Tú's module into the app factory, using the extension points in BACKEND_SERVICE_CONTRACT 7.1."""
import os
from app.jobs.booking_jobs import register_booking_commands
from app.routes.booking_api import booking_api
from app.services import booking_service
from app.use_cases.cancel_booking import cancel_match

SETTINGS = {'VNPAY_TMN_CODE': '', 'VNPAY_HASH_SECRET': '', 'VNPAY_RETURN_URL': '',
            'VNPAY_PAY_URL': 'https://sandbox.vnpayment.vn/paymentv2/vpcpay.html',
            'VNPAY_API_URL': 'https://sandbox.vnpayment.vn/merchant_webapi/api/transaction',
            'BANK_BIN': '', 'BANK_ACCOUNT_NO': ''}

def install(app):
    for key, default in SETTINGS.items():
        app.config.setdefault(key, os.getenv(key) or default)
    app.register_blueprint(booking_api, url_prefix='/api/v1')
    app.extensions['booking_service'] = booking_service
    app.extensions['booking_reader'] = booking_service.read_for_actor
    app.extensions['cancel_match'] = cancel_match
    register_booking_commands(app)
