import { useEffect, useState } from 'react';
import type { Booking, BankDepositInstructions } from '../../types/api';
import { cancelMyBooking, getBooking, getMyBookings, huyDemo, moneyVN, dateVN } from '../../services/huyApi';
import { Banner, Button, Card, Empty, Head, Status, Warning, countdown, useNow } from '../field-management/ui';
import { BankDepositBox } from '../payments/BankDepositBox';
import { getDepositInstructions } from '../../services/depositBank';
import { bookingHash } from '../../services/bookingNavigation';

export function BookingsPage({ selectedId, onRefresh }: { selectedId: number | null; onRefresh?: () => void }) {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [activeId, setActiveId] = useState<number | null>(selectedId);
  const [transfer, setTransfer] = useState<BankDepositInstructions | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const now = useNow();
  const [refreshCounter, setRefreshCounter] = useState(0);
  useEffect(() => { if (selectedId !== null) setActiveId(selectedId); }, [selectedId]);
  useEffect(() => {
    let valid = true;
    Promise.all([getMyBookings(), selectedId ? getBooking(selectedId) : Promise.resolve(null)]).then(([data, selected]) => {
      if (valid) setBookings(selected && !data.some(b => b.booking_id === selected.booking_id) ? [selected, ...data] : data);
    }).catch(e => { if (valid) setError(e); });
    return () => { valid = false; };
  }, [refreshCounter, selectedId]);
  useEffect(()=>{
    if(!activeId)return;
    let valid=true;
    const timer=window.setInterval(()=>{
      if(document.visibilityState==='hidden')return;
      Promise.all([getBooking(activeId),transfer?.booking_id===activeId?getDepositInstructions(activeId):Promise.resolve(null)])
        .then(([booking,instructions])=>{if(valid){setBookings(old=>old.map(b=>b.booking_id===booking.booking_id?booking:b));if(instructions)setTransfer(instructions);}})
        .catch(()=>{});
    },10_000);
    return ()=>{valid=false;window.clearInterval(timer);};
  },[activeId,transfer?.booking_id]);
  const active = bookings.find(b => b.booking_id === activeId) ?? null;
  const validHold = !!active?.hold_expires_at && Date.parse(active.hold_expires_at) > now && active.status === 'PENDING_HOLD';
  async function reload() {
    setError(null); setTransfer(null);
    try {
      if (activeId) await getBooking(activeId);
      setRefreshCounter(n => n + 1); onRefresh?.();
    } catch (e) { setError(e); }
  }
  async function pay() {
    if (!active || busy) return;
    setBusy(true); setError(null); setNotice(''); setTransfer(null);
    try {
      const p = await getDepositInstructions(active.booking_id);
      setTransfer(p);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function cancel() {
    if (!active || busy || !window.confirm('Xác nhận hủy? Theo quy định, người dùng tự hủy sau cọc sẽ mất khoản cọc của mình.')) return;
    setBusy(true); setError(null);
    try { await cancelMyBooking(active.booking_id, 'Người dùng chủ động hủy'); setNotice('Đã xử lý yêu cầu hủy' + (huyDemo ? ' (demo)' : '') + '.'); await reload(); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <>
    <Head kicker="PLAYER / 02" title="Booking của tôi" description="Theo dõi trạng thái giữ sân, khoản cọc và lịch đã đặt." aside={<Button variant="outline" onClick={() => void reload()}>↻ Làm mới</Button>} />
    <Warning error={error} />{notice && <Banner tone="success">{notice}</Banner>}
    <div className="huy-two-col"><Card><h2>Danh sách đặt sân</h2>{bookings.length === 0 ? <Empty>Chưa có booking nào.</Empty> : <div className="huy-booking-list">{bookings.map(b => <button type="button" className={`huy-booking-item ${activeId === b.booking_id ? 'active' : ''}`} key={b.booking_id} onClick={() => { setActiveId(b.booking_id); setTransfer(null); setError(null); window.location.hash = bookingHash(b.booking_id); }}>
      <span><b>Đơn #{b.booking_id}</b><small>{dateVN(b.start_time)}</small><small>{moneyVN(b.total_amount)}</small></span><span><Status state={b.status}/>{b.is_demo&&<small>DEMO</small>}</span></button>)}</div>}</Card>
      <Card><h2>Chi tiết booking</h2>{active ? <>
        {active.is_demo&&<Banner>Booking DEMO — cọc mô phỏng đã lưu, không phải tiền ngân hàng thực nhận.</Banner>}
        <div className="huy-info-grid"><div><small>Mã đơn</small><strong>#{active.booking_id}</strong></div><div><small>Loại đặt</small><strong>{active.booking_type}</strong></div>
          <div><small>Bắt đầu</small><strong>{dateVN(active.start_time)}</strong></div><div><small>Kết thúc</small><strong>{dateVN(active.end_time)}</strong></div>
          <div><small>Giá sân</small><strong>{moneyVN(active.total_amount)}</strong></div><div><small>Tiền cọc</small><strong>{moneyVN(active.deposit_amount)}</strong></div></div>
        <div className="huy-flex huy-gap"><Status state={active.status}/>{active.status === 'PENDING_HOLD' && <strong className={validHold ? 'huy-timer' : 'huy-danger'}>⏱ {countdown(active.hold_expires_at, now)}</strong>}</div>
        {active.payer_progress.map(p => <div key={p.user_id} className="huy-payer">Người trả #{p.user_id}<span>{moneyVN(p.paid_amount)} / {moneyVN(p.required_amount)} · {p.status}</span></div>)}
        {active.status === 'PENDING_HOLD' && <><Banner>{validHold ? 'Thời hạn giữ sân tính theo đồng hồ server, không gia hạn khi tải lại trang.' : 'Giữ sân đã hết hạn. Phải chọn lại giờ, không tiếp tục thanh toán.'}</Banner>
          <div className="huy-actions"><Button onClick={() => void pay()} disabled={!validHold || busy}>Đóng cọc bằng chuyển khoản</Button></div></>}
        {transfer && active && transfer.booking_id===active.booking_id && <BankDepositBox instructions={transfer} validHold={validHold} onConfirmed={result=>{setBookings(old=>old.map(b=>b.booking_id===result.booking.booking_id?result.booking:b));setNotice('Đã lưu cọc DEMO vào database.');void getDepositInstructions(result.booking.booking_id).then(setTransfer).catch(setError);}} />}
        {(active.status === 'PENDING_HOLD' || active.status === 'CONFIRMED') && <div className="huy-actions"><Button variant="danger" disabled={busy} onClick={() => void cancel()}>Hủy booking</Button></div>}
        {active.status === 'PENDING_HOLD' && !validHold && <Button variant="outline" onClick={() => void reload()}>Kiểm tra trạng thái với server</Button>}
      </> : <Empty>Chọn một booking ở cột bên trái để xem chi tiết.</Empty>}</Card></div>
    {huyDemo && <Banner>Phiên demo chỉ minh họa giữ chỗ, không xác nhận giao dịch online. Booking mẫu đã xác nhận là dữ liệu giả lập ban đầu.</Banner>}
  </>;
}
