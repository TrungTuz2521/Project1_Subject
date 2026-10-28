import { useEffect, useState } from 'react';
import type { Booking, PaymentSession } from '../../types/api';
import { createSettlementSession, getAdminBookings, getSettlement, huyDemo, moneyVN, dateVN, recordCash, setSettlementResult } from '../../services/huyApi';
import type { MatchOutcome, Settlement } from '../../services/huyApi';
import { Banner, Button, Card, Empty, Field, Head, Status, Warning } from '../../features/field-management/ui';
import { PaymentBox } from '../../features/payments/PaymentBox';

export function AdminSettlementPage({ selectedId }: { selectedId: number | null }) {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [id, setId] = useState<number>(selectedId ?? 0);
  const [settlement, setSettlement] = useState<Settlement | null>(null);
  const [outcome, setOutcome] = useState<MatchOutcome>('DRAW');
  const [payment, setPayment] = useState<PaymentSession | null>(null);
  const [method, setMethod] = useState<'VNPAY' | 'MOMO'>('VNPAY');
  const [receiptMethod, setReceiptMethod] = useState<'CASH' | 'BANK_TRANSFER'>('CASH');
  const [error, setError] = useState<unknown>(null);
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const [rev, setRev] = useState(0);
  useEffect(() => { if (selectedId) setId(selectedId); }, [selectedId]);
  useEffect(() => {
    let alive = true;
    getAdminBookings().then(items => {
      if (!alive) return;
      const finished = items.filter(b => b.status === 'CONFIRMED' && Date.parse(b.end_time) <= Date.now());
      setBookings(finished);
      if (!id && finished.length) setId(finished[0].booking_id);
    }).catch(e => { if (alive) setError(e); });
    return () => { alive = false; };
    // update list when rev changes
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rev]);
  useEffect(() => {
    if (!id) return;
    let alive = true;
    setPayment(null); setError(null); setSettlement(null);
    getSettlement(id).then(s => {
      if (alive) { setSettlement(s); setOutcome(s.outcome ?? 'DRAW'); }
    }).catch(e => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [id, rev]);
  const booking = bookings.find(b => b.booking_id === id);
  const requiresOutcome = settlement?.payment_rule === 'LOSER_PAYS_REMAINDER';
  async function saveOutcome() {
    if (!settlement) return;
    setBusy(true); setError(null); setSuccess('');
    try {
      const s = await setSettlementResult(id, outcome, settlement.version);
      setSettlement(s); setPayment(null); setSuccess('Đã lưu kết quả và cập nhật số tiền còn phải trả.');
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function createQR(payerId: number) {
    if (!settlement) return;
    setBusy(true); setError(null); setPayment(null);
    try { setPayment(await createSettlementSession(id, payerId, method, settlement.version)); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function cash(payerId: number, amount: string) {
    if (!settlement || busy) return;
    if (!window.confirm(`${huyDemo ? '[DEMO] ' : ''}Xác nhận đã thực nhận ${moneyVN(amount)} tại quầy?`)) return;
    setBusy(true); setError(null); setSuccess('');
    try {
      await recordCash({ booking_id: id, user_id: payerId, amount, payment_type: 'BOOKING_REMAINING_PAYMENT', payment_method: receiptMethod,
        note: 'Admin xác nhận thu tiền sau trận' });
      setPayment(null); setSettlement(await getSettlement(id));
      setRev(n => n + 1);
      setSuccess(huyDemo ? 'Đã ghi nhận thu tiền giả lập, không tạo giao dịch thật.' : 'Backend đã ghi nhận giao dịch tại quầy.');
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <>
    <Head kicker="ADMIN / 03" title="Quyết toán tại quầy" description="Đối chiếu kết quả với hai đội; backend tính khoản còn thu trước khi tạo QR." />
    <Warning error={error} />{success && <Banner tone="success">{success}</Banner>}
    <div className="huy-two-col"><Card><h2>Chọn trận đã kết thúc</h2><Field label="Booking"><select value={id} onChange={e => setId(Number(e.target.value))}><option value={0}>— Chọn booking —</option>{bookings.map(b => <option key={b.booking_id} value={b.booking_id}>#{b.booking_id} · {dateVN(b.start_time)}</option>)}</select></Field>
      {booking && <div className="huy-info-grid"><div><small>Loại chia tiền</small><strong>{booking.payment_rule}</strong></div><div><small>Trạng thái</small><Status state={booking.status}/></div><div><small>Tổng tiền sân</small><strong>{moneyVN(booking.total_amount)}</strong></div><div><small>Tiền cọc yêu cầu</small><strong>{moneyVN(booking.deposit_amount)}</strong></div></div>}
      <Banner>Chỉ mở quyết toán sau giờ kết thúc. Không có bước hai đội xác nhận trên ứng dụng.</Banner>
    </Card>
      <Card><h2>Bảng tính quyết toán</h2>{!settlement ? <Empty>Chọn trận để xem khoản tiền cần thu (API quyết toán cần Tú triển khai).</Empty> : <>
        <div className="huy-info-grid"><div><small>Tiền đã thu</small><strong>{moneyVN(settlement.collected_amount)}</strong></div><div><small>Còn thiếu</small><strong>{moneyVN(settlement.outstanding_amount)}</strong></div><div><small>Phiên quyết toán</small><strong>v{settlement.version}</strong></div><div><small>Kết quả</small><strong>{settlement.outcome ?? 'Chưa chốt'}</strong></div></div>
        {requiresOutcome && <div className="huy-outcome"><Field label="Chọn kết quả sau khi đã đối chiếu với hai đội"><select value={outcome} onChange={e => setOutcome(e.target.value as MatchOutcome)}>
          <option value="SOURCE_WIN">Đội đăng bài thắng</option><option value="OPPONENT_WIN">Đội đối thủ thắng</option><option value="DRAW">Hòa</option></select></Field>
          <Button disabled={busy || settlement.outcome === outcome} onClick={() => void saveOutcome()}>Lưu kết quả</Button></div>}
        {requiresOutcome && !settlement.outcome ? <Banner>Chưa chốt kết quả. Chưa thể tạo giao dịch thu phần còn lại.</Banner> : <><div className="huy-toolbar"><Field label="Cổng thanh toán"><select value={method} onChange={e => setMethod(e.target.value as typeof method)}><option value="VNPAY">VNPay</option><option value="MOMO">MoMo</option></select></Field><Field label="Phương thức nhận tại quầy"><select value={receiptMethod} onChange={e => setReceiptMethod(e.target.value as typeof receiptMethod)}><option value="CASH">Tiền mặt</option><option value="BANK_TRANSFER">Chuyển khoản</option></select></Field></div>
          {settlement.payers.map(p => <div key={p.user_id} className="huy-payer-panel"><div className="huy-flex"><div><strong>{p.display_name}</strong><small className="huy-block">Đại diện #{p.user_id}</small></div><b>{moneyVN(p.remaining_amount)}</b></div>
            {Number(p.remaining_amount) > 0 ? <div className="huy-actions"><Button variant="outline" disabled={busy} onClick={() => void createQR(p.user_id)}>Tạo QR</Button><Button disabled={busy} onClick={() => void cash(p.user_id, p.remaining_amount)}>Xác nhận đã thu</Button></div> : <small className="huy-muted">Không còn tiền phải trả.</small>}</div>)}
        </>}
        {payment && <PaymentBox payment={payment}/>}
      </>}
      </Card></div>
    <Banner>Không tự đánh dấu thanh toán online thành công. Khi đã tạo QR, việc đổi kết quả cần backend kiểm soát phiên bản và trạng thái giao dịch.</Banner>
  </>;
}
