class DomainError(Exception):
    def __init__(self, code, message, status=409, fields=None, *, http_status=None):
        super().__init__(message)
        self.code, self.message = code, message
        self.status = http_status if http_status is not None else status
        self.http_status, self.fields = self.status, fields or {}

class SlotUnavailable(DomainError):
    def __init__(self):
        super().__init__('SLOT_UNAVAILABLE', 'Khung giờ không còn khả dụng.')

def invalid(field, message='Giá trị không hợp lệ.'):
    raise DomainError('VALIDATION_ERROR', 'Dữ liệu không hợp lệ.', 422, {field: message})
