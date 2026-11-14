import { useEffect, useState } from 'react';
import type { Booking, BankDepositInstructions } from '../../types/api';
import { cancelMyBooking, getBooking, getMyBookings, moneyVN, dateVN, serverNow } from '../../services/fieldApi';
import { Banner, Button, Card, Empty, Head, Status, Warning, countdown, useNow } from '../field-management/ui';
import { BankDepositBox } from '../payments/BankDepositBox';
import { getDepositInstructions } from '../../services/depositBank';
import { bookingHash } from '../../services/bookingNavigation';
import { VenueContact, useVenue } from '../player/venue';

const isUpcoming = (b: Booking) => ['PENDING_HOLD', 'CONFIRMED'].includes(b.status) && Date.parse(b.end_time) > serverNow();

export function BookingsPage({ selectedId, onRefresh }: { selectedId: number | null; onRefresh?: () => void }) {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [activeId, setActiveId] = useState<number | null>(selectedId);
  const [transfer, setTransfer] = useState<BankDepositInstructions | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const now = useNow();
  const [refreshCounter, setRefreshCounter] = useState(0);
  const [view, setView] = useState<'upcoming' | 'past'>('upcoming');
  const venue = useVenue();
  // Arriving straight from "Giữ sân" (#...&pay=1): open the QR at once, the 5-minute hold is already running.
  const [autoPay, setAutoPay] = useState(() => window.location.hash.includes('pay=1'));
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
  useEffect(() => {
    if (!autoPay || !active || active.booking_id !== selectedId || transfer || busy) return;
    if (validHold) void pay(); else setAutoPay(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPay, active?.booking_id, validHold]);
  const upcoming = bookings.filter(isUpcoming).sort((a, b) => Date.parse(a.start_time) - Date.parse(b.start_time));
  const past = bookings.filter(b => !isUpcoming(b)).sort((a, b) => Date.parse(b.start_time) - Date.parse(a.start_time));
  const listed = view === 'upcoming' ? upcoming : past;
  async function cancel() {
    if (!active || busy || !window.confirm('Hủy booking này? Nếu đã đặt cọc, bạn sẽ mất tiền cọc; khoản trả thêm ngoài cọc (nếu có) được hoàn lại.')) return;
    setBusy(true); setError(null);
    try { await cancelMyBooking(active.booking_id, 'Người dùng chủ động hủy'); setNotice('Đã xử lý yêu cầu hủy.'); await reload(); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <>
    <Head title="Booking của tôi" description="Lịch đã đặt, tiền đã trả và số còn lại phải trả tại sân." aside={<Button variant="outline" onClick={() => void reload()}>↻ Làm mới</Button>} />
    <Warning error={error} />{notice && <Banner tone="success">{notice}</Banner>}
    <div className="huy-two-col"><Card><h2>Lịch đã đặt</h2><div className="book-days list-tabs" role="tablist"><button type="button" role="tab" aria-selected={view === 'upcoming'} className={view === 'upcoming' ? 'is-on' : ''} onClick={() => setView('upcoming')}>Sắp tới ({upcoming.length})</button><button type="button" role="tab" aria-selected={view === 'past'} className={view === 'past' ? 'is-on' : ''} onClick={() => setView('past')}>Đã qua / đã hủy ({past.length})</button></div>{listed.length === 0 ? <Empty>{view === 'upcoming' ? <>Bạn chưa có lịch đá nào sắp tới. <a href="#/bookings">Đặt sân ngay</a></> : 'Chưa có lịch nào đã qua.'}</Empty> : <div className="huy-booking-list">{listed.map(b => <button type="button" className={`huy-booking-item ${activeId === b.booking_id ? 'active' : ''}`} key={b.booking_id} onClick={() => { setActiveId(b.booking_id); setTransfer(null); setError(null); window.location.hash = bookingHash(b.booking_id); }}>
      <span><b>{b.pitch_name ?? `Đơn #${b.booking_id}`}</b><small>{dateVN(b.start_time)}</small><small>{moneyVN(b.total_amount)} · Đơn #{b.booking_id}</small></span><span><Status state={b.status}/>{b.is_demo&&<small>DEMO</small>}</span></button>)}</div>}</Card>
      <Card><h2>Chi tiết</h2>{active ? <>
        {active.is_demo&&<Banner>Booking DEMO — cọc mô phỏng đã lưu, không phải tiền ngân hàng thực nhận.</Banner>}
        <div className="huy-info-grid"><div><small>Mã đơn</small><strong>#{active.booking_id}</strong></div><div><small>Sân</small><strong>{active.pitch_name ?? `#${active.pitch_id}`}</strong></div><div><small>Đặt qua</small><strong>{active.booking_type === 'MANUAL_ADMIN' ? 'Quầy của sân' : 'Website'}</strong></div>
          <div><small>Bắt đầu</small><strong>{dateVN(active.start_time)}</strong></div><div><small>Kết thúc</small><strong>{dateVN(active.end_time)}</strong></div>
          <div><small>Giá sân</small><strong>{moneyVN(active.total_amount)}</strong></div><div><small>Tiền cọc</small><strong>{moneyVN(active.deposit_amount)}</strong></div></div>
        <div className="huy-flex huy-gap"><Status state={active.status}/>{active.status === 'PENDING_HOLD' && <strong className={validHold ? 'huy-timer' : 'huy-danger'}>⏱ {countdown(active.hold_expires_at, now)}</strong>}</div>
        {active.status === 'PENDING_HOLD'
          ? active.payer_progress.map(p => <div key={p.user_id} className="huy-payer">Tiền cọc cần trả<span>{moneyVN(p.paid_amount)} / {moneyVN(p.required_amount)}{p.status === 'PAID' ? ' · Đã đủ' : ''}</span></div>)
          : active.paid_amount !== undefined && <div className="huy-money-summary">
            <div><small>Đã trả</small><strong>{moneyVN(active.paid_amount)}</strong></div>
            {active.status === 'CONFIRMED' && <div><small>{active.outstanding_amount === '0.00' ? 'Thanh toán' : 'Còn trả tại sân'}</small><strong>{active.outstanding_amount === '0.00' ? 'Đã trả đủ' : moneyVN(active.outstanding_amount ?? '0')}</strong></div>}
          </div>}
        {active.status === 'PENDING_HOLD' && <><Banner>{validHold ? 'Thời hạn giữ sân tính theo đồng hồ server, không gia hạn khi tải lại trang.' : 'Giữ sân đã hết hạn. Phải chọn lại giờ, không tiếp tục thanh toán.'}</Banner>
          <div className="huy-actions"><Button onClick={() => void pay()} disabled={!validHold || busy}>Đóng cọc bằng mã QR</Button></div></>}
        {transfer && active && transfer.booking_id===active.booking_id && <BankDepositBox instructions={transfer} validHold={validHold} autoStart={autoPay} onConfirmed={result=>{setBookings(old=>old.map(b=>b.booking_id===result.booking.booking_id?result.booking:b));setNotice('Đã lưu cọc DEMO vào database.');void getDepositInstructions(result.booking.booking_id).then(setTransfer).catch(setError);}}
          onPaid={()=>{const id=active.booking_id;setNotice('Đã nhận tiền cọc từ ngân hàng. Email xác nhận đặt sân sẽ được gửi tới bạn.');
            void Promise.all([getBooking(id),getDepositInstructions(id)]).then(([booking,instructions])=>{setBookings(old=>old.map(b=>b.booking_id===id?booking:b));setTransfer(instructions);}).catch(setError);}} />}
        {(active.status === 'PENDING_HOLD' || active.status === 'CONFIRMED') && Date.parse(active.start_time) > now && <div className="huy-actions"><Button variant="danger" disabled={busy} onClick={() => void cancel()}>Hủy booking</Button></div>}
        {active.status === 'PENDING_HOLD' && !validHold && <Button variant="outline" onClick={() => void reload()}>Kiểm tra trạng thái với server</Button>}
        <VenueContact venue={venue} />
      </> : <Empty>Chọn một lịch ở cột bên trái để xem chi tiết.</Empty>}</Card></div>
  </>;
}
