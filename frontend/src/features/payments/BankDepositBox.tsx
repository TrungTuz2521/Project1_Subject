import type { BankDepositInstructions, DemoDepositResult } from '../../types/api';
import { moneyVN, dateVN } from '../../services/fieldApi';
import { BankQR } from './BankQR';
import { DemoDepositConfirmation, demoDepositEnabled } from './DemoDepositConfirmation';
import { QrPaymentPanel } from './QrPaymentPanel';
import { Banner } from '../field-management/ui';

export function BankDepositBox({ instructions, validHold, demo = demoDepositEnabled, onConfirmed, onPaid, autoStart = false }: { instructions: BankDepositInstructions; validHold: boolean; demo?: boolean; onConfirmed?: (result: DemoDepositResult) => void; onPaid?: () => void; autoStart?: boolean }) {
  const auto = instructions.qr_auto_confirm === true;
  return <section className="huy-payment-box"><h3>Chuyển khoản tiền cọc{demo ? " — Demo" : ""}</h3>
    {demo && <Banner>Chế độ demo: chỉ minh họa thao tác, không chuyển tiền thật.</Banner>}
    {instructions.account_no && <div className="huy-info-grid">
      <div><small>Ngân hàng</small><strong>{instructions.bank_name}</strong></div>
      <div><small>Số tài khoản</small><strong>{instructions.account_no}</strong></div>
      <div><small>Chủ tài khoản</small><strong>{instructions.account_name}</strong></div>
      <div><small>Hạn xác nhận cọc</small><strong>{instructions.expires_at ? dateVN(instructions.expires_at) : 'Đã kết thúc'}</strong></div>
    </div>}
    {instructions.payers.map(payer => auto ?
      <QrPaymentPanel key={payer.user_id} bookingId={instructions.booking_id} payer={payer} validHold={validHold}
        ttlSeconds={instructions.qr_ttl_seconds} onPaid={onPaid} autoStart={autoStart} /> :
      <div key={payer.user_id}>
        <p>Phần cọc còn phải trả của bạn: <strong>{moneyVN(payer.due_amount)}</strong></p>
        <p>Nội dung chuyển khoản: <strong>{payer.transfer_reference}</strong></p>
        {validHold && payer.qr_payload ? <BankQR payload={payer.qr_payload} /> : <Banner>{payer.status==='PAID'?'Đã xác nhận đủ phần cọc.':validHold ? payer.unavailable_reason : 'Đã hết hạn nhận cọc. Không chuyển thêm tiền.'}</Banner>}
        <DemoDepositConfirmation key={`${instructions.booking_id}-${payer.user_id}-${payer.due_amount}`} bookingId={instructions.booking_id} enabled={demo && instructions.demo_payment_enabled === true} alreadyPaid={payer.status==='PAID'} canConfirm={validHold && !!payer.qr_payload} onConfirmed={onConfirmed} />
      </div>)}
    {auto ? <p className="huy-muted">Hệ thống tự xác nhận khi ngân hàng báo đã nhận tiền và gửi email thông báo.</p>
      : !demo && <p>Chưa tích hợp tự động đối soát tiền chuyển khoản.</p>}
  </section>;
}
