import type { PaymentSession } from '../../types/api';
import { huyDemo, moneyVN, dateVN } from '../../services/huyApi';
import { Banner, Card, Status } from '../field-management/ui';

export function PaymentBox({ payment }: { payment: PaymentSession }) {
  // The payment provider supplies either a URL or QR payload. Never mark SUCCESS from this component.
  const link = !huyDemo && payment.payment_url && /^https:\/\//.test(payment.payment_url) ? payment.payment_url : null;
  return <Card className="huy-payment-box"><div className="huy-flex"><h3>Thông tin thanh toán</h3><Status state={payment.status}/></div>
    <div className="huy-info-grid"><div><small>Mã giao dịch</small><strong>#{payment.payment_id}</strong></div><div><small>Số tiền</small><strong>{moneyVN(payment.amount)}</strong></div>
      <div><small>Phương thức</small><strong>{payment.payment_method}</strong></div><div><small>Hạn thanh toán</small><strong>{dateVN(payment.expires_at)}</strong></div></div>
    {huyDemo ? <div className="huy-demo-qr"><span>▦</span><strong>QR DEMO</strong><small>KHÔNG THỂ THANH TOÁN</small></div> : payment.qr_payload ? <div className="huy-qr-text"><b>QR payload từ cổng thanh toán</b><code>{payment.qr_payload}</code><small>Cần renderer QR đã kiểm thử với adapter cổng thực tế; chuỗi này không phải ảnh QR.</small></div> : null}
    {link && <a className="huy-btn huy-btn-primary" href={link} target="_blank" rel="noopener noreferrer">Mở cổng thanh toán an toàn ↗</a>}
    {!huyDemo && !link && !payment.qr_payload && <Banner>Chưa có URL/QR từ cổng thanh toán. Không chuyển khoản theo thông tin tự tạo.</Banner>}
    <Banner>Chỉ backend xác nhận trạng thái thanh toán sau khi xác minh callback. Giao diện không tự ghi SUCCESS.</Banner>
  </Card>;
}
