import { useEffect, useState } from 'react';
import type { Booking, PaymentSession } from '../../types/api';
import { cancelMyBooking, createDepositSession, getBooking, getMyBookings, huyDemo, moneyVN, dateVN, serverNow } from '../../services/huyApi';
import { Banner, Button, Card, Empty, Head, Status, Warning, countdown, useNow } from '../field-management/ui';
import { PaymentBox } from '../payments/PaymentBox';

export function BookingsPage({ selectedId, onRefresh }: { selectedId: number | null; onRefresh?: () => void }) {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [activeId, setActiveId] = useState<number | null>(selectedId);
  const [payment, setPayment] = useState<PaymentSession | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const now = useNow();
  const [refreshCounter, setRefreshCounter] = useState(0);
  useEffect(() => { if (selectedId !== null) setActiveId(selectedId); }, [selectedId]);
  useEffect(() => {
    let valid = true;
    getMyBookings().then(data => { if (valid) setBookings(data); }).catch(e => { if (valid) setError(e); });
    return () => { valid = false; };
  }, [refreshCounter]);
  const active = bookings.find(b => b.booking_id === activeId) ?? null;
  const validHold = !!active?.hold_expires_at && Date.parse(active.hold_expires_at) > now && active.status === 'PENDING_HOLD';
  async function reload() {
    setError(null); setPayment(null);
    try {
      if (activeId) await getBooking(activeId);
      setRefreshCounter(n => n + 1); onRefresh?.();
    } catch (e) { setError(e); }
  }
  async function pay(method: 'VNPAY' | 'MOMO') {
    if (!active || busy) return;
    setBusy(true); setError(null); setNotice(''); setPayment(null);
    try {
      const p = await createDepositSession(active.booking_id, method);
      setPayment(p);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function cancel() {
    if (!active || busy || !window.confirm('Xác nhận hủy? Theo quy định, người dùng tự hủy sau cọc có thể mất khoản cọc của mình.')) return;
    setBusy(true); setError(null);
    try { await cancelMyBooking(active.booking_id, 'Người dùng chủ động hủy'); setNotice('Đã xử lý yêu cầu hủy' + (huyDemo ? ' (demo)' : '') + '.'); await reload(); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <>
    <Head kicker="PLAYER / 02" title="Booking của tôi" description="Theo dõi trạng thái giữ sân, khoản cọc và lịch đã đặt." aside={<Button variant="outline" onClick={() => void reload()}>↻ Làm mới</Button>} />
    <Warning error={error} />{notice && <Banner tone="success">{notice}</Banner>}
    <div className="huy-two-col"><Card><h2>Danh sách đặt sân</h2>{bookings.length === 0 ? <Empty>Chưa có booking nào.</Empty> : <div className="huy-booking-list">{bookings.map(b => <button type="button" className={`huy-booking-item ${activeId === b.booking_id ? 'active' : ''}`} key={b.booking_id} onClick={() => { setActiveId(b.booking_id); setPayment(null); setError(null); }}>
      <span><b>Đơn #{b.booking_id}</b><small>{dateVN(b.start_time)}</small><small>{moneyVN(b.total_amount)}</small></span><Status state={b.status}/></button>)}</div>}</Card>
      <Card><h2>Chi tiết booking</h2>{active ? <>
        <div className="huy-info-grid"><div><small>Mã đơn</small><strong>#{active.booking_id}</strong></div><div><small>Loại đặt</small><strong>{active.booking_type}</strong></div>
          <div><small>Bắt đầu</small><strong>{dateVN(active.start_time)}</strong></div><div><small>Kết thúc</small><strong>{dateVN(active.end_time)}</strong></div>
          <div><small>Giá sân</small><strong>{moneyVN(active.total_amount)}</strong></div><div><small>Tiền cọc</small><strong>{moneyVN(active.deposit_amount)}</strong></div></div>
        <div className="huy-flex huy-gap"><Status state={active.status}/>{active.status === 'PENDING_HOLD' && <strong className={validHold ? 'huy-timer' : 'huy-danger'}>⏱ {countdown(active.hold_expires_at, now)}</strong>}</div>
        {active.payer_progress.map(p => <div key={p.user_id} className="huy-payer">Người trả #{p.user_id}<span>{moneyVN(p.paid_amount)} / {moneyVN(p.required_amount)} · {p.status}</span></div>)}
        {active.status === 'PENDING_HOLD' && <><Banner>{validHold ? 'Thời hạn giữ sân tính theo đồng hồ server, không gia hạn khi tải lại trang.' : 'Giữ sân đã hết hạn. Phải chọn lại giờ, không tiếp tục thanh toán.'}</Banner>
          <div className="huy-actions"><Button onClick={() => void pay('VNPAY')} disabled={!validHold || busy}>Thanh toán cọc VNPay</Button><Button variant="outline" onClick={() => void pay('MOMO')} disabled={!validHold || busy}>MoMo</Button></div></>}
        {payment && <PaymentBox payment={payment} />}
        {(active.status === 'PENDING_HOLD' || active.status === 'CONFIRMED') && <div className="huy-actions"><Button variant="danger" disabled={busy} onClick={() => void cancel()}>Hủy booking</Button></div>}
        {active.status === 'PENDING_HOLD' && !validHold && <Button variant="outline" onClick={() => void reload()}>Kiểm tra trạng thái với server</Button>}
      </> : <Empty>Chọn một booking ở cột bên trái để xem chi tiết.</Empty>}</Card></div>
    {huyDemo && <Banner>Phiên demo chỉ minh họa giữ chỗ, không xác nhận giao dịch online. Booking mẫu đã xác nhận là dữ liệu giả lập ban đầu.</Banner>}
  </>;
}
