import { useEffect, useRef, useState } from 'react';
import type { AdminBooking, BookingBalance, ConfirmBookingPaid, ManualReceipt } from '../../types/api';
import { confirmBookingPaid, getAdminBookings, getBooking, getBookingBalance, huyDemo, moneyVN, dateVN } from '../../services/huyApi';
import { Banner, Button, Card, Empty, Field, Head, Status, Warning } from '../../features/field-management/ui';
import { BankQR } from '../../features/payments/BankQR';

export function AdminBalancePage({ selectedId }: { selectedId: number | null }) {
  const [bookings, setBookings] = useState<AdminBooking[]>([]);
  const [id, setId] = useState(selectedId ?? 0);
  const [error, setError] = useState<unknown>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (selectedId) setId(selectedId); }, [selectedId]);
  useEffect(() => {
    let alive = true;
    getAdminBookings().then(items => {
      if (!alive) return;
      setBookings(items.filter(b => b.status === 'CONFIRMED' && Date.parse(b.end_time) <= Date.now()));
    }).catch(e => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [revision]);
  return <>
    <Head kicker="ADMIN / 03" title="Thu tiền sau trận" description="Đối chiếu tiền thực nhận và xác nhận thu đủ theo booking. Hai đội tự chia tiền theo thể thức đã chọn."
      aside={<Button variant="outline" disabled={busy} onClick={() => { setError(null); setRevision(n => n + 1); }}>Làm mới</Button>} />
    <Warning error={error} />
    <Card><Field label="Booking đã kết thúc"><select disabled={busy} value={id} onChange={e => setId(Number(e.target.value))}>
      <option value={0}>— Chọn booking —</option>
      {id > 0 && !bookings.some(b => b.booking_id === id) && <option value={id}>#{id}</option>}
      {bookings.map(b => <option key={b.booking_id} value={b.booking_id}>#{b.booking_id} · {b.pitch_name ?? `Sân #${b.pitch_id}`} · {dateVN(b.start_time)}{b.balance?.payment_status === 'PAID' ? ' · Đã thu đủ' : ''}</option>)}
    </select></Field><p className="huy-muted">Danh sách hiển thị tối đa 100 booking gần nhất. Chọn “Thu tiền sau trận” tại lịch sân để mở một booking cụ thể.</p></Card>
    {id ? <BalancePanel key={`${id}:${revision}`} id={id} booking={bookings.find(b => b.booking_id === id)} onBusy={setBusy} /> : <Empty>Chọn booking để xem cọc thực thu, số còn thiếu và QR chung.</Empty>}
  </>;
}

function BalancePanel({ id, booking, onBusy }: { id: number; booking?: AdminBooking; onBusy: (busy: boolean) => void }) {
  const [balance, setBalance] = useState<BookingBalance | null>(null);
  const [receipts, setReceipts] = useState<ManualReceipt[]>([{ payment_method: 'BANK_TRANSFER', amount: '', reference: '' }]);
  const [error, setError] = useState<unknown>(null);
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [detail, setDetail] = useState<AdminBooking | undefined>(booking);
  // Keep the exact body/key after a timeout so retry cannot create another receipt.
  const pending = useRef<ConfirmBookingPaid | null>(null);
  useEffect(() => {
    let alive = true;
    Promise.all([getBookingBalance(id), booking ? Promise.resolve(booking) : getBooking(id)])
      .then(([b, item]) => { if (alive) { setBalance(b); setDetail(item); } })
      .catch(e => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [id]);
  const canCollect = balance && balance.payment_status !== 'PAID' && detail?.status === 'CONFIRMED' && Date.parse(detail.end_time) <= Date.now();
  const total = receipts.reduce((sum, r) => sum + (/^[1-9]\d*$/.test(r.amount) ? BigInt(r.amount) : 0n), 0n);
  function update(index: number, patch: Partial<ManualReceipt>) {
    setReceipts(rows => rows.map((r, n) => n === index ? { ...r, ...patch } : r));
  }
  async function confirm() {
    if (!balance || busy || !canCollect) return;
    setError(null); setSuccess('');
    if (!pending.current) {
      const outstanding = BigInt(balance.outstanding_amount.split('.')[0]);
      if (receipts.some(r => !/^[1-9]\d*$/.test(r.amount)) || total !== outstanding) {
        setError(new Error('Mỗi khoản phải là VND nguyên đồng lớn hơn 0; tổng phải bằng đúng số còn thiếu.')); return;
      }
      if (!window.confirm(`Bạn đã đối chiếu và thực nhận đủ ${moneyVN(balance.outstanding_amount)}?`)) return;
      pending.current = { expected_outstanding: balance.outstanding_amount, idempotency_key: crypto.randomUUID(),
        receipts: receipts.map(r => ({ payment_method: r.payment_method, amount: `${r.amount}.00`, ...(r.reference?.trim() ? { reference: r.reference.trim() } : {}) })) };
    }
    setBusy(true); onBusy(true);
    try {
      setBalance(await confirmBookingPaid(id, pending.current));
      pending.current = null; setUncertain(false);
      setSuccess(huyDemo ? 'Đã ghi nhận trong dữ liệu demo; không có giao dịch thật.' : 'Đã ghi nhận các khoản thực thu.');
    } catch (e) { setError(e); setUncertain(true); }
    finally { setBusy(false); onBusy(false); }
  }
  return <><Warning error={error} />{success && <Banner tone="success">{success}</Banner>}
    {!balance ? <Empty>{error ? 'Chưa tải được số dư. Hãy bấm Làm mới để thử lại.' : 'Đang tải số dư booking…'}</Empty> : <div className="huy-two-col">
      <Card><h2>Số tiền theo booking #{id}</h2>
        <div className="huy-info-grid">
          <div><small>Tổng tiền sân</small><strong>{moneyVN(balance.total_amount)}</strong></div>
          <div><small>Cọc thực thu</small><strong>{moneyVN(balance.deposit_collected_amount)}</strong></div>
          <div><small>Phần còn lại đã thu (trước hoàn)</small><strong>{moneyVN(balance.remaining_collected_amount)}</strong></div>
          <div><small>Đã thu ròng sau hoàn</small><strong>{moneyVN(balance.collected_amount)}</strong></div>
          <div><small>Còn thiếu</small><strong>{moneyVN(balance.outstanding_amount)}</strong></div>
          <div><small>Thanh toán</small><Status state={balance.payment_status} /></div>
          <div><small>Thể thức hai đội tự chia</small><strong>{balance.payment_rule === 'LOSER_PAYS_REMAINDER' ? 'Đội thua trả phần còn lại' : balance.payment_rule === 'SPLIT_EQUAL' ? 'Chia 50–50' : balance.payment_rule === 'DIRECT_BOOKING' ? 'Đặt sân trực tiếp' : 'Chưa xác định (dữ liệu cũ)'}</strong></div>
        </div>
        {booking?.teams && <p>{booking.teams.source.team_name} — {booking.teams.opponent.team_name}</p>}
        {balance.qr_payload && !huyDemo && <BankQR payload={balance.qr_payload} />}
        {balance.transfer_reference && <p>Nội dung chuyển khoản: <strong>{balance.transfer_reference}</strong></p>}
        {balance.qr_unavailable_reason && <Banner>{balance.qr_unavailable_reason}</Banner>}
        <Banner>QR chung gợi ý số còn thiếu. Hai đội có thể chuyển nhiều khoản hoặc trả tiền mặt. Quét QR không xác nhận đã thanh toán.</Banner>
      </Card>
      <Card><h2>Xác nhận tiền thực nhận</h2>
        {balance.payment_status === 'PAID' ? <Banner tone="success">Booking đã thu đủ.</Banner> : !canCollect ? <Banner>Chỉ xác nhận thu đủ sau giờ kết thúc của booking đã xác nhận. Nếu thiếu thông tin, hãy mở lại từ lịch sân.</Banner> : <>
          {receipts.map((r, i) => <div className="huy-payer-panel" key={i}><div className="huy-form">
            <Field label={`Khoản ${i + 1} · Phương thức`}><select disabled={busy || uncertain} value={r.payment_method} onChange={e => update(i, { payment_method: e.target.value as ManualReceipt['payment_method'] })}><option value="BANK_TRANSFER">Chuyển khoản</option><option value="CASH">Tiền mặt</option></select></Field>
            <Field label="Số tiền thực nhận (VND)"><input disabled={busy || uncertain} inputMode="numeric" value={r.amount} onChange={e => update(i, { amount: e.target.value })} /></Field>
            <Field label="Mã chứng từ / tham chiếu (nếu có)"><input disabled={busy || uncertain} maxLength={100} value={r.reference ?? ''} onChange={e => update(i, { reference: e.target.value })} /></Field>
            {receipts.length > 1 && <Button variant="outline" disabled={busy || uncertain} onClick={() => setReceipts(rows => rows.filter((_, n) => n !== i))}>Xóa khoản này</Button>}
          </div></div>)}
          <Button variant="outline" disabled={busy || uncertain || receipts.length >= 50} onClick={() => setReceipts(rows => [...rows, { payment_method: 'BANK_TRANSFER', amount: '', reference: '' }])}>Thêm khoản thực nhận</Button>
          <p>Tổng khoản đang nhập: <strong>{moneyVN(total.toString())}</strong></p>
          {uncertain && <Banner>Chưa xác nhận được kết quả. Thử lại sẽ gửi đúng yêu cầu cũ để tránh ghi thu trùng; hoặc bấm Làm mới để kiểm tra số dư trước khi nhập lại.</Banner>}
          <Button disabled={busy} onClick={() => void confirm()}>{busy ? 'Đang ghi nhận…' : uncertain ? 'Thử lại yêu cầu cũ' : 'Xác nhận đã thu đủ'}</Button>
        </>}
      </Card>
    </div>}
  </>;
}
