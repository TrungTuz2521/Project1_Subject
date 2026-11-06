"""GatewayPort. Adapters report SUCCESS/FAILED/PENDING/UNKNOWN; a timeout never proves failure.

NOT_FOUND is an extra query-only state: the provider answered that the transaction does not exist.
"""
from flask import current_app
from app.contracts.errors import DomainError

class InvalidCallback(Exception):
    """Signature or merchant check failed; the payload must not be treated as a business command."""

def get_gateway(method):
    overrides = current_app.extensions.get('payment_gateways') or {}
    if method in overrides:
        return overrides[method]
    if method == 'VNPAY':
        config = current_app.config
        if not config.get('VNPAY_TMN_CODE') or not config.get('VNPAY_HASH_SECRET'):
            raise DomainError('PAYMENT_PROVIDER_UNAVAILABLE', 'Cổng thanh toán chưa được cấu hình.', 503)
        from app.services.gateway.vnpay import VnpayGateway
        return VnpayGateway(config['VNPAY_TMN_CODE'], config['VNPAY_HASH_SECRET'], config['VNPAY_PAY_URL'], config['VNPAY_API_URL'])
    raise DomainError('UNSUPPORTED_PAYMENT_METHOD', 'Phương thức thanh toán chưa được hỗ trợ.', 422)

def gateway_or_none(method):
    try:
        return get_gateway(method)
    except DomainError:
        return None
