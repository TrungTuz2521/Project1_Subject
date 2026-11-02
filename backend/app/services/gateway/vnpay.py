"""VNPay 2.1.0 adapter, per sandbox.vnpayment.vn/apis/docs (pay, IPN, querydr, refund).

Not yet exercised against a real VNPay sandbox: needs a merchant TmnCode/HashSecret.
"""
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from secrets import token_hex
from urllib.parse import urlencode
from app.contracts.dto import GatewayResult
from app.services.gateway import InvalidCallback
from app.utils.time import VIETNAM

VERSION = '2.1.0'
SERVER_IP = '127.0.0.1'

def _stamp(moment):
    return moment.astimezone(VIETNAM).strftime('%Y%m%d%H%M%S')

def _parse_stamp(value):
    try:
        return datetime.strptime(value, '%Y%m%d%H%M%S').replace(tzinfo=VIETNAM).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None

def _minor(amount):
    return str(int(Decimal(amount) * 100))

class VnpayGateway:
    def __init__(self, tmn_code, hash_secret, pay_url, api_url):
        self.tmn_code, self.secret, self.pay_url, self.api_url = tmn_code, hash_secret, pay_url, api_url

    def _sign(self, data):
        return hmac.new(self.secret.encode(), data.encode(), hashlib.sha512).hexdigest()

    def create_payment(self, merchant_reference, amount, expires_at, callback_url, *, created_at, client_ip=SERVER_IP):
        """Signed locally without network, so a reused session rebuilds the same URL after a restart."""
        params = {'vnp_Version': VERSION, 'vnp_Command': 'pay', 'vnp_TmnCode': self.tmn_code, 'vnp_Amount': _minor(amount),
                  'vnp_CreateDate': _stamp(created_at), 'vnp_ExpireDate': _stamp(expires_at), 'vnp_CurrCode': 'VND',
                  'vnp_IpAddr': client_ip, 'vnp_Locale': 'vn', 'vnp_OrderInfo': f'Coc san {merchant_reference}',
                  'vnp_OrderType': 'other', 'vnp_ReturnUrl': callback_url, 'vnp_TxnRef': merchant_reference}
        query = urlencode(sorted(params.items()))
        return GatewayResult('PENDING', merchant_reference, Decimal(amount), expires_at=expires_at,
                             payment_url=f'{self.pay_url}?{query}&vnp_SecureHash={self._sign(query)}')

    def verify_callback(self, raw_body, headers_or_query):
        params = {k: v for k, v in headers_or_query.items() if k.startswith('vnp_') and k not in ('vnp_SecureHash', 'vnp_SecureHashType')}
        expected = self._sign(urlencode(sorted(params.items())))
        if not hmac.compare_digest(expected, str(headers_or_query.get('vnp_SecureHash', '')).lower()):
            raise InvalidCallback('signature')
        if params.get('vnp_TmnCode') != self.tmn_code or not params.get('vnp_TxnRef'):
            raise InvalidCallback('merchant')
        try:
            amount = Decimal(params['vnp_Amount']) / 100
        except (KeyError, ArithmeticError):
            raise InvalidCallback('amount')
        paid = params.get('vnp_ResponseCode') == '00' and params.get('vnp_TransactionStatus') == '00'
        return GatewayResult('SUCCESS' if paid else 'FAILED', params['vnp_TxnRef'], amount,
                             provider_reference=params.get('vnp_TransactionNo') or None,
                             paid_at=_parse_stamp(params.get('vnp_PayDate')) if paid else None)

    def _post(self, payload, response_fields):
        """Returns the verified response, or None when the outcome is unknown (timeout, bad checksum)."""
        request = urllib.request.Request(self.api_url, json.dumps(payload).encode(), {'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=15) as reply:
                body = json.loads(reply.read().decode())
        except (OSError, ValueError):
            return None
        data = '|'.join(str(body.get(field) or '') for field in response_fields)
        if not hmac.compare_digest(self._sign(data), str(body.get('vnp_SecureHash', '')).lower()):
            return None
        return body

    def _request_base(self, command, now):
        return {'vnp_RequestId': token_hex(16), 'vnp_Version': VERSION, 'vnp_Command': command, 'vnp_TmnCode': self.tmn_code,
                'vnp_CreateDate': _stamp(now), 'vnp_IpAddr': SERVER_IP}

    def _query(self, merchant_reference, transaction_date):
        payload = self._request_base('querydr', datetime.now(timezone.utc))
        payload.update(vnp_TxnRef=merchant_reference, vnp_OrderInfo=f'Tra cuu {merchant_reference}', vnp_TransactionDate=_stamp(transaction_date))
        order = ('vnp_RequestId', 'vnp_Version', 'vnp_Command', 'vnp_TmnCode', 'vnp_TxnRef', 'vnp_TransactionDate', 'vnp_CreateDate', 'vnp_IpAddr', 'vnp_OrderInfo')
        payload['vnp_SecureHash'] = self._sign('|'.join(payload[k] for k in order))
        return self._post(payload, ('vnp_ResponseId', 'vnp_Command', 'vnp_ResponseCode', 'vnp_Message', 'vnp_TmnCode', 'vnp_TxnRef',
                                    'vnp_Amount', 'vnp_BankCode', 'vnp_PayDate', 'vnp_TransactionNo', 'vnp_TransactionType',
                                    'vnp_TransactionStatus', 'vnp_OrderInfo', 'vnp_PromotionCode', 'vnp_PromotionAmount'))

    def query_payment(self, merchant_reference, *, amount, transaction_date):
        body = self._query(merchant_reference, transaction_date)
        if body is None:
            return GatewayResult('UNKNOWN', merchant_reference, Decimal(amount))
        if body.get('vnp_ResponseCode') == '91':
            return GatewayResult('NOT_FOUND', merchant_reference, Decimal(amount))
        if body.get('vnp_ResponseCode') != '00':
            return GatewayResult('UNKNOWN', merchant_reference, Decimal(amount))
        status = body.get('vnp_TransactionStatus')
        state = 'SUCCESS' if status == '00' else 'PENDING' if status == '01' else 'FAILED' if status == '02' else 'UNKNOWN'
        paid = Decimal(str(body.get('vnp_Amount') or 0)) / 100 if state == 'SUCCESS' else Decimal(amount)
        return GatewayResult(state, merchant_reference, paid, provider_reference=body.get('vnp_TransactionNo') or None,
                             paid_at=_parse_stamp(body.get('vnp_PayDate')) if state == 'SUCCESS' else None)

    def request_refund(self, merchant_reference, refund_reference, amount, *, transaction_date):
        payload = self._request_base('refund', datetime.now(timezone.utc))
        payload.update(vnp_TransactionType='02', vnp_TxnRef=merchant_reference, vnp_Amount=_minor(amount), vnp_TransactionNo='',
                       vnp_TransactionDate=_stamp(transaction_date), vnp_CreateBy='system', vnp_OrderInfo=f'Hoan {refund_reference}')
        order = ('vnp_RequestId', 'vnp_Version', 'vnp_Command', 'vnp_TmnCode', 'vnp_TransactionType', 'vnp_TxnRef', 'vnp_Amount', 'vnp_TransactionNo',
                 'vnp_TransactionDate', 'vnp_CreateBy', 'vnp_CreateDate', 'vnp_IpAddr', 'vnp_OrderInfo')
        payload['vnp_SecureHash'] = self._sign('|'.join(payload[k] for k in order))
        body = self._post(payload, ('vnp_ResponseId', 'vnp_Command', 'vnp_ResponseCode', 'vnp_Message', 'vnp_TmnCode', 'vnp_TxnRef', 'vnp_Amount',
                                    'vnp_BankCode', 'vnp_PayDate', 'vnp_TransactionNo', 'vnp_TransactionType', 'vnp_TransactionStatus', 'vnp_OrderInfo'))
        if body is None:
            return GatewayResult('UNKNOWN', refund_reference, Decimal(amount))
        code = body.get('vnp_ResponseCode')
        if code == '00':
            return self._refund_state(body, refund_reference, amount)
        if code == '94':
            return GatewayResult('PENDING', refund_reference, Decimal(amount))
        return GatewayResult('FAILED' if code in ('91', '95') else 'UNKNOWN', refund_reference, Decimal(amount))

    def query_refund(self, refund_reference, *, merchant_reference, amount, transaction_date):
        body = self._query(merchant_reference, transaction_date)
        if body is None or body.get('vnp_ResponseCode') != '00':
            return GatewayResult('UNKNOWN', refund_reference, Decimal(amount))
        if body.get('vnp_TransactionType') not in ('02', '03'):
            return GatewayResult('NOT_FOUND', refund_reference, Decimal(amount))
        return self._refund_state(body, refund_reference, amount)

    @staticmethod
    def _refund_state(body, refund_reference, amount):
        status = body.get('vnp_TransactionStatus')
        state = 'SUCCESS' if status == '00' else 'PENDING' if status in ('05', '06') else 'FAILED' if status == '09' else 'UNKNOWN'
        return GatewayResult(state, refund_reference, Decimal(amount), provider_reference=body.get('vnp_TransactionNo') or None,
                             paid_at=_parse_stamp(body.get('vnp_PayDate')) if state == 'SUCCESS' else None)

    def cancel_payment(self, merchant_reference):
        return 'UNSUPPORTED'
