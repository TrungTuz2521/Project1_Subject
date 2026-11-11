import { useEffect, useRef, useState } from 'react';
import type { AdminBooking, AdminUser, Availability, BookingPhase, BookingStatus, CancelCause, Pitch } from '../../types/api';
import {
  getAdminBookingsPage, getAvailability, getPitches, addAdminBooking, createMaintenance,
  cancelAdminBooking, cancelSeries, moveAdminBooking, removeMaintenance, dateVN, moneyVN,
} from '../../services/huyApi';
import { Banner, Button, Card, Empty, Field, Head, Status, Warning, dateAfter } from '../../features/field-management/ui';
import { AdminRefundQueue } from './AdminRefundQueue';
import { CustomerPicker } from './CustomerPicker';
import { DayBoard } from './DayBoard';
import { ReasonDialog } from './Dialog';
import type { Choice } from './Dialog';
import { Pager } from './Pager';
import { SlotPicker, slotTime } from './SlotPicker';

const PAGE_SIZE = 20;
type Mode = 'counter' | 'maintenance' | 'move';
type PayChoice = 'later' | 'deposit' | 'full' | 'other';
type Pending = { kind: 'booking' | 'series' | 'unlock'; booking: AdminBooking } | null;
const DEPOSIT_PERCENT = 20;
const ddmm = (iso: string) => new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit' }).format(new Date(iso));

function PayerCell({ booking }: { booking: AdminBooking }) {
  if (booking.booking_type === 'MAINTENANCE_LOCK') return <small className="huy-muted">—</small>;
  const b = booking.balance;
  if (b && !['CONFIRMED', 'PENDING_HOLD'].includes(booking.status)) {
    return b.collected_amount === '0.00' ? <small className="huy-muted">Không phát sinh</small>
      : <><span className="adm-nowrap">Còn giữ <strong>{moneyVN(b.collected_amount)}</strong></span><small className="huy-block">Phần phải trả lại nằm ở "Khoản cần hoàn"</small></>;
  }
  if (b) return <><span className="adm-nowrap"><strong>{moneyVN(b.collected_amount)}</strong> / {moneyVN(b.total_amount)}</span>
    <small className="huy-block">{b.outstanding_amount === '0.00' ? 'Đã trả đủ' : `Còn ${moneyVN(b.outstanding_amount)}`}</small></>;
  return <>{booking.payer_progress.map(p => <span key={p.user_id} className="adm-nowrap huy-block">{moneyVN(p.paid_amount)} / {moneyVN(p.required_amount)}</span>)}</>;
}

/** What each cancel choice does to this booking's money, so the counter can tell the customer. */
function cancelChoices(b: AdminBooking): Choice<CancelCause>[] {
  const deposit = Number(b.balance?.deposit_collected_amount ?? 0);
  const rest = Number(b.balance?.remaining_collected_amount ?? 0);
  const venue: Choice<CancelCause> = { value: 'VENUE', label: 'Sân có sự cố', detail: deposit + rest ? `Hoàn toàn bộ ${moneyVN(String(deposit + rest))} cho khách.` : 'Khách chưa trả tiền, không phải hoàn.' };
  if (b.teams) return [venue];  // A two-team match cannot be cancelled on behalf of one side.
  return [{ value: 'CUSTOMER', label: 'Khách hủy', tone: 'danger',
    detail: deposit ? `Giữ cọc ${moneyVN(String(deposit))}${rest ? `, hoàn ${moneyVN(String(rest))} khách trả thêm` : ''}.` : rest ? `Hoàn ${moneyVN(String(rest))} khách đã trả.` : 'Khách chưa trả tiền.' }, venue];
}

export function AdminBookingsPage({ settlement }: { settlement: (id: number) => void }) {
  // ---- list ----
  const [rows, setRows] = useState<AdminBooking[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<BookingStatus | ''>('');
  const [phase, setPhase] = useState<BookingPhase | ''>('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [seriesFilter, setSeriesFilter] = useState<AdminBooking | null>(null);
  // ---- create ----
  const [pitches, setPitches] = useState<Pitch[]>([]);
  const [mode, setMode] = useState<Mode>('counter');
  const [moveTarget, setMoveTarget] = useState<AdminBooking | null>(null);
  const [pitchId, setPitchId] = useState(0);
  const [date, setDate] = useState(dateAfter(0));
  const [time, setTime] = useState('');
  const [slots, setSlots] = useState<Availability['slots'] | null>(null);
  const [slotError, setSlotError] = useState('');
  const [customerKind, setCustomerKind] = useState<'walkin' | 'account'>('walkin');
  const [customer, setCustomer] = useState<AdminUser | null>(null);
  const [guestName, setGuestName] = useState('');
  const [guestPhone, setGuestPhone] = useState('');
  const [regular, setRegular] = useState(false);
  const [weeks, setWeeks] = useState(4);
  const [pay, setPay] = useState<PayChoice>('deposit');
  const [otherAmount, setOtherAmount] = useState('');
  const [method, setMethod] = useState<'CASH' | 'BANK_TRANSFER'>('CASH');
  const [reference, setReference] = useState('');
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  // ---- page ----
  const [error, setError] = useState<unknown>(null);
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [pending, setPending] = useState<Pending>(null);
  const formRef = useRef<HTMLDivElement>(null);
  const refresh = () => setRevision(n => n + 1);

  useEffect(() => {
    getPitches().then(ps => { setPitches(ps); setPitchId(id => ps.some(p => p.pitch_id === id) ? id : ps.find(p => p.status === 'ACTIVE')?.pitch_id ?? ps[0]?.pitch_id ?? 0); })
      .catch(setError);
  }, []);
  useEffect(() => {
    let live = true; setLoading(true);
    getAdminBookingsPage({ page, page_size: PAGE_SIZE, phase: phase || undefined, status: status || undefined, series_id: seriesFilter?.series_id ?? undefined,
      from: from && to ? from : undefined, to: from && to ? to : undefined })
      .then(result => { if (live) { setRows(result.data); setTotal(result.meta.total); } })
      .catch(e => { if (live) setError(e); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [revision, page, phase, status, from, to, seriesFilter]);
  useEffect(() => {
    if (!pitchId || !date) return;
    let live = true; setSlots(null); setSlotError('');
    getAvailability(pitchId, date).then(result => {
      if (!live) return;
      setSlots(result.slots);
      const free = result.slots.filter(s => s.status === 'AVAILABLE').map(s => slotTime(s.start_time));
      setTime(current => free.includes(current) ? current : free[0] ?? '');
    }).catch(e => { if (live) { setSlots([]); setSlotError(e instanceof Error ? e.message : 'Không tải được lịch sân.'); } });
    return () => { live = false; };
  }, [pitchId, date, revision]);

  const pitch = pitches.find(p => p.pitch_id === pitchId);
  const slot = slots?.find(s => slotTime(s.start_time) === time);
  const price = Number(slot?.price ?? pitch?.price_per_slot ?? 0);
  const depositAmount = Math.ceil(price * DEPOSIT_PERCENT / 100);
  const payAmount = pay === 'later' ? 0 : pay === 'deposit' ? depositAmount : pay === 'full' ? price : Math.max(0, Math.round(Number(otherAmount) || 0));
  const filter = <T,>(setter: (value: T) => void) => (value: T) => { setter(value); setPage(1); };
  const pitchName = (b: AdminBooking) => b.pitch_name ?? pitches.find(p => p.pitch_id === b.pitch_id)?.pitch_name ?? `Sân #${b.pitch_id}`;

  function switchMode(next: Mode) { setMode(next); setReason(''); setError(null); if (next !== 'move') setMoveTarget(null); }
  function toForm() { formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
  function startMove(b: AdminBooking) { switchMode('move'); setMoveTarget(b); setPitchId(b.pitch_id); setSuccess(''); toForm(); }
  /** A free cell on the day board fills the form (booking, maintenance or the move in progress keep their tab). */
  function pickFromBoard(id: number, t: string) { setPitchId(id); setTime(t); setSuccess(''); toForm(); }

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (busy) return;
    setBusy(true); setError(null); setSuccess('');
    try {
      if (!time) throw new Error('Chọn một lượt đá còn trống.');
      const start = new Date(`${date}T${time}:00+07:00`);
      const slotBody = { pitch_id: pitchId, start_time: start.toISOString(), end_time: new Date(start.getTime() + 90 * 60000).toISOString() };
      const when = `${pitch?.pitch_name ?? 'sân'} lúc ${time} ngày ${date.split('-').reverse().join('/')}`;
      if (mode === 'counter') {
        const name = customerKind === 'account' ? customer?.full_name : guestName.trim();
        if (customerKind === 'account' && !customer) throw new Error('Tìm và chọn tài khoản của khách.');
        if (customerKind === 'walkin' && (!guestName.trim() || !guestPhone.trim())) throw new Error('Nhập tên và số điện thoại của khách.');
        if (pay === 'other' && payAmount > price) throw new Error(`Số tiền thu không được vượt giá sân ${moneyVN(String(price))}.`);
        const created = await addAdminBooking({ ...slotBody, note: note.trim() || 'Đặt sân tại quầy', ...(regular ? { repeat_weeks: weeks } : {}),
          ...(customerKind === 'account' ? { user_id: customer!.user_id } : { guest: { full_name: guestName.trim(), phone: guestPhone.trim() } }),
          ...(payAmount > 0 ? { payment: { amount: `${payAmount}.00`, payment_method: method, ...(reference.trim() ? { reference: reference.trim() } : {}) } } : {}) });
        const owed = price - payAmount;
        let text = `Đã đặt ${when} cho ${name}. ` + (payAmount ? `Đã thu ${moneyVN(String(payAmount))}` : 'Chưa thu tiền')
          + (owed > 0 ? `, còn ${moneyVN(String(owed))} thu khi khách đến.` : ', khách đã trả đủ.');
        if (created.series) {
          text += ` Khách cố định: đã giữ ${created.series.created.length}/${created.series.requested_weeks} tuần.`;
          if (created.series.skipped.length) text += ` Bỏ qua ${created.series.skipped.map(s => `${ddmm(s.start_time)} (${s.reason})`).join(', ')}.`;
        }
        setSuccess(text);
        setCustomer(null); setGuestName(''); setGuestPhone(''); setReference(''); setNote(''); setOtherAmount(''); setRegular(false);
      }
      if (mode === 'maintenance') { await createMaintenance({ ...slotBody, reason: reason.trim() }); setSuccess(`Đã khóa ${when} để bảo trì.`); }
      if (mode === 'move') {
        if (!moveTarget) throw new Error('Chọn "Đổi lịch" ở một booking trong danh sách.');
        await moveAdminBooking(moveTarget.booking_id, { ...slotBody, reason: reason.trim() });
        setSuccess(`Đã chuyển booking #${moveTarget.booking_id} sang ${when}.`); switchMode('counter');
      }
      refresh();
    } catch (e) { setError(e); } finally { setBusy(false); }
  }

  async function confirmPending(text: string, cause: CancelCause | undefined) {
    if (!pending) return;
    const b = pending.booking;
    if (pending.kind === 'unlock') { await removeMaintenance(b.booking_id, text); setSuccess('Đã mở khóa lượt bảo trì.'); }
    if (pending.kind === 'booking') {
      const r = await cancelAdminBooking(b.booking_id, text, cause ?? 'VENUE');
      const s = r.refund_summary;
      setSuccess(`Đã hủy booking #${b.booking_id}.` + (s && Number(s.forfeited_amount) ? ` Giữ cọc ${moneyVN(s.forfeited_amount)}.` : '')
        + (s && Number(s.refund_amount) ? ` Cần hoàn ${moneyVN(s.refund_amount)} cho khách (xem "Khoản cần hoàn").` : ''));
    }
    if (pending.kind === 'series' && b.series_id) {
      const r = await cancelSeries(b.series_id, text, cause ?? 'CUSTOMER');
      setSuccess(`Đã hủy ${r.cancelled.length} buổi sắp tới của khách cố định.` + (Number(r.forfeited_amount) ? ` Giữ cọc ${moneyVN(r.forfeited_amount)}.` : '')
        + (Number(r.refund_amount) ? ` Cần hoàn ${moneyVN(r.refund_amount)}.` : ''));
      setSeriesFilter(null);
    }
    refresh();
  }

  const submitLabel = mode === 'counter'
    ? (regular ? `Giữ ${weeks} tuần` : 'Đặt sân') + (payAmount ? ` và thu ${moneyVN(String(payAmount))}` : ', thu tiền sau')
    : mode === 'maintenance' ? 'Khóa lượt này' : 'Đổi sang lượt này';
  const canSubmit = !busy && !!pitch && !!time && (mode !== 'counter' || customerKind === 'walkin' || !!customer) && (mode !== 'move' || !!moveTarget)
    && !(mode === 'counter' && pay === 'other' && (payAmount <= 0 || payAmount > price));

  return <>
    <Head title="Lịch sân" description="Xem lịch cả ngày, đặt sân cho khách tại quầy, giữ lượt cho khách cố định, khóa bảo trì và theo dõi tiền." aside={<Button variant="outline" onClick={refresh}>Làm mới</Button>} />
    <Warning error={error} />{success && <Banner tone="success">{success}</Banner>}
    <AdminRefundQueue revision={revision} />

    <DayBoard pitches={pitches} date={date} onDate={setDate} onPick={pickFromBoard} revision={revision} />

    <div ref={formRef} className="adm-anchor" />
    <Card className="adm-create">
      <div className="adm-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={mode === 'counter'} className={mode === 'counter' ? 'is-on' : ''} onClick={() => switchMode('counter')}>Đặt sân tại quầy</button>
        <button type="button" role="tab" aria-selected={mode === 'maintenance'} className={mode === 'maintenance' ? 'is-on' : ''} onClick={() => switchMode('maintenance')}>Khóa bảo trì</button>
        {mode === 'move' && moveTarget && <button type="button" role="tab" aria-selected className="is-on">Đổi lịch booking #{moveTarget.booking_id}</button>}
      </div>
      <form className="adm-create-grid" onSubmit={e => void submit(e)}>
        <section className="adm-step">
          <h3><span>1</span>{mode === 'counter' ? 'Khách' : mode === 'maintenance' ? 'Lý do khóa' : 'Booking cần đổi'}</h3>
          {mode === 'counter' && <>
            <div className="adm-segment" role="radiogroup" aria-label="Loại khách">
              <button type="button" role="radio" aria-checked={customerKind === 'walkin'} className={customerKind === 'walkin' ? 'is-on' : ''} onClick={() => setCustomerKind('walkin')}>Khách vãng lai</button>
              <button type="button" role="radio" aria-checked={customerKind === 'account'} className={customerKind === 'account' ? 'is-on' : ''} onClick={() => setCustomerKind('account')}>Có tài khoản</button>
            </div>
            {customerKind === 'walkin' ? <>
              <Field label="Tên khách"><input required minLength={2} maxLength={100} autoComplete="off" value={guestName} onChange={e => setGuestName(e.target.value)} placeholder="Anh Minh" /></Field>
              <Field label="Số điện thoại"><input required inputMode="tel" maxLength={20} autoComplete="off" value={guestPhone} onChange={e => setGuestPhone(e.target.value)} placeholder="0912 345 678" /></Field>
              <p className="huy-muted">Khách quay lại với cùng số điện thoại sẽ dùng lại hồ sơ cũ.</p>
            </> : <CustomerPicker value={customer} onChange={setCustomer} />}
          </>}
          {mode === 'maintenance' && <Field label="Lý do"><input required maxLength={200} value={reason} onChange={e => setReason(e.target.value)} placeholder="Thay lưới khung thành" /></Field>}
          {mode === 'move' && moveTarget && <>
            <div className="adm-move-card"><strong>#{moveTarget.booking_id}, {moveTarget.customer?.full_name ?? `Khách #${moveTarget.user_id}`}</strong>
              <small>Đang ở {pitchName(moveTarget)}, {dateVN(moveTarget.start_time)}</small></div>
            <Field label="Lý do đổi"><input required maxLength={200} value={reason} onChange={e => setReason(e.target.value)} placeholder="Khách xin đổi giờ" /></Field>
            <Button variant="outline" onClick={() => switchMode('counter')}>Thôi, không đổi</Button>
          </>}
        </section>

        <section className="adm-step">
          <h3><span>2</span>Sân và giờ</h3>
          <div className="adm-pitch-row">
            <Field label="Sân"><select value={pitchId} onChange={e => setPitchId(Number(e.target.value))}>
              {pitches.map(p => <option key={p.pitch_id} value={p.pitch_id} disabled={p.status !== 'ACTIVE'}>{p.pitch_name} ({p.pitch_type === 'PITCH_7' ? 'sân 7' : 'sân 5'}){p.status !== 'ACTIVE' ? ', tạm ngưng' : ''}</option>)}
            </select></Field>
            <Field label="Ngày"><input type="date" required min={dateAfter(0)} max={dateAfter(100)} value={date} onChange={e => setDate(e.target.value)} /></Field>
          </div>
          <SlotPicker slots={slots} value={time} onChange={setTime} error={slotError} />
          {mode === 'counter' && <div className={`adm-regular${regular ? ' is-on' : ''}`}>
            <label><input type="checkbox" checked={regular} onChange={e => setRegular(e.target.checked)} /> Khách cố định: giữ lượt này mỗi tuần</label>
            {regular && <Field label="Số tuần (gồm tuần này)"><select value={weeks} onChange={e => setWeeks(Number(e.target.value))}>
              {Array.from({ length: 11 }, (_, i) => i + 2).map(n => <option key={n} value={n}>{n} tuần{n === 4 ? ' (1 tháng)' : n === 12 ? ' (3 tháng)' : ''}</option>)}
            </select></Field>}
            {regular && <small>Tuần nào đã có người đặt sẽ được bỏ qua và báo lại. Tiền thu bây giờ chỉ tính cho buổi đầu tiên.</small>}
          </div>}
        </section>

        <section className="adm-step">
          <h3><span>3</span>{mode === 'counter' ? 'Thanh toán' : 'Xác nhận'}</h3>
          {mode === 'counter' && <>
            <div className="adm-pay" role="radiogroup" aria-label="Khách trả lúc đặt">
              {([['later', 'Thu khi đến', 0], ['deposit', `Cọc ${DEPOSIT_PERCENT}%`, depositAmount], ['full', 'Trả đủ', price], ['other', 'Số khác', null]] as const).map(([key, label, amount]) =>
                <button key={key} type="button" role="radio" aria-checked={pay === key} className={pay === key ? 'is-on' : ''} onClick={() => setPay(key)}>
                  <span>{label}</span><strong>{amount === null ? 'Tự nhập' : moneyVN(String(amount))}</strong></button>)}
            </div>
            {pay === 'other' && <Field label="Số tiền khách trả (VND)"><input type="number" min={1} step={1000} value={otherAmount} onChange={e => setOtherAmount(e.target.value)} aria-invalid={payAmount > price} /></Field>}
            {pay === 'other' && payAmount > price && <p className="huy-danger">Số tiền không được vượt giá sân {moneyVN(String(price))}.</p>}
            {payAmount > 0 && <div className="adm-pitch-row">
              <Field label="Hình thức"><select value={method} onChange={e => setMethod(e.target.value as typeof method)}><option value="CASH">Tiền mặt</option><option value="BANK_TRANSFER">Chuyển khoản</option></select></Field>
              <Field label="Mã phiếu (nếu có)"><input maxLength={100} value={reference} onChange={e => setReference(e.target.value)} placeholder="PT-0012" /></Field>
            </div>}
            <Field label="Ghi chú (nếu có)"><input maxLength={150} value={note} onChange={e => setNote(e.target.value)} placeholder="Đội áo xanh, cần thêm bóng" /></Field>
          </>}
          <div className="adm-summary">
            <span>{pitch ? `${pitch.pitch_name}, ${time || 'chưa chọn giờ'}, ngày ${date.split('-').reverse().join('/')}` : 'Chưa chọn sân'}</span>
            {mode === 'counter' && pitch && <span>Giá lượt này <strong>{moneyVN(String(price))}</strong>{slot?.is_peak ? ' (giờ cao điểm)' : ''}{payAmount ? <>, thu ngay <strong>{moneyVN(String(payAmount))}</strong></> : null}</span>}
            {mode === 'counter' && <small>Đặt tại quầy được xác nhận ngay. Khách hủy thì giữ tiền cọc.</small>}
          </div>
          <Button type="submit" disabled={!canSubmit}>{busy ? 'Đang lưu…' : submitLabel}</Button>
        </section>
      </form>
    </Card>

    <Card>
      <div className="adm-list-head">
        <h2>Danh sách booking</h2>
        <div className="adm-filters">
          <Field label="Trạng thái"><select value={status} onChange={e => filter(setStatus)(e.target.value as BookingStatus | '')}><option value="">Tất cả</option><option value="PENDING_HOLD">Chờ khách chuyển khoản (online)</option><option value="CONFIRMED">Đã xác nhận</option><option value="MAINTENANCE">Bảo trì</option><option value="CANCELLED">Đã hủy</option><option value="EXPIRED">Hết hạn</option></select></Field>
          <Field label="Tiến độ"><select value={phase} onChange={e => filter(setPhase)(e.target.value as BookingPhase | '')}><option value="">Tất cả</option><option value="UPCOMING">Sắp đá</option><option value="IN_PROGRESS">Đang đá</option><option value="ENDED_UNPAID">Đá xong, chưa thu đủ</option><option value="PAID">Đã thu đủ</option></select></Field>
          <Field label="Từ ngày"><input type="date" value={from} max={to || undefined} onChange={e => filter(setFrom)(e.target.value)} /></Field>
          <Field label="Đến ngày"><input type="date" value={to} min={from || undefined} onChange={e => filter(setTo)(e.target.value)} /></Field>
          {(from || to) && <Button variant="outline" onClick={() => { setFrom(''); setTo(''); setPage(1); }}>Bỏ lọc ngày</Button>}
        </div>
      </div>
      {seriesFilter && <div className="adm-filter-chip">Đang xem các buổi của khách cố định <strong>{seriesFilter.customer?.full_name ?? ''}</strong>
        <button type="button" onClick={() => { setSeriesFilter(null); setPage(1); }}>Bỏ lọc ×</button></div>}
      {(from && !to) || (!from && to) ? <p className="huy-muted">Chọn đủ cả hai ngày để lọc theo khoảng.</p> : null}
      {rows.length === 0 ? <Empty>{loading ? 'Đang tải…' : 'Chưa có booking phù hợp với bộ lọc.'}</Empty> : <div className="huy-table-wrap"><table>
        <thead><tr><th>Booking</th><th>Sân và giờ</th><th>Khách</th><th>Đã thu / giá sân</th><th>Trạng thái</th><th aria-label="Thao tác" /></tr></thead>
        <tbody>{rows.map(b => <tr key={b.booking_id}>
          <td><strong>#{b.booking_id}</strong><small className="huy-block">{b.booking_type === 'MANUAL_ADMIN' ? 'Tại quầy' : b.booking_type === 'MAINTENANCE_LOCK' ? 'Bảo trì' : 'Online'}</small>
            {b.series_id && <button type="button" className="adm-tag" title="Xem các buổi khác của khách cố định" onClick={() => { setSeriesFilter(b); setPage(1); }}>Cố định</button>}</td>
          <td><strong>{pitchName(b)}</strong><small className="huy-block">{dateVN(b.start_time)}</small></td>
          <td>{b.booking_type === 'MAINTENANCE_LOCK' ? <small className="huy-muted">—</small> : <>
            <strong>{b.customer?.full_name ?? `Khách #${b.user_id}`}</strong>
            <small className="huy-block">{b.customer?.phone ?? 'Chưa có số điện thoại'}{b.customer?.walk_in ? ', vãng lai' : ''}</small>
            {!!b.customer?.no_show_count && <span className="adm-flag">Đã bùng {b.customer.no_show_count} lần</span>}
            {b.teams && <small className="huy-block">{b.teams.source.team_name ?? '?'} gặp {b.teams.opponent.team_name ?? '?'}</small>}
          </>}</td>
          <td><PayerCell booking={b} /></td>
          <td><Status state={b.status}/>{b.balance && b.status === 'CONFIRMED' && <small className="huy-block"><Status state={b.balance.payment_status}/></small>}
            {b.arrival_status && <small className="huy-block">{b.arrival_status === 'ARRIVED' ? 'Khách đã đến' : 'Khách không đến'}</small>}
            {b.status === 'PENDING_HOLD' && <small className="huy-block">Tự xác nhận khi tiền về</small>}</td>
          <td><div className="adm-row-actions">
            {b.status === 'CONFIRMED' && b.balance && b.balance.payment_status !== 'PAID' && Date.parse(b.start_time) < Date.now() + 86400000 && <Button variant="light" onClick={() => settlement(b.booking_id)}>Thu tiền</Button>}
            {b.status === 'CONFIRMED' && Date.parse(b.start_time) > Date.now() && <Button variant="outline" disabled={busy} onClick={() => startMove(b)}>Đổi lịch</Button>}
            {['CONFIRMED', 'PENDING_HOLD'].includes(b.status) && <button type="button" className="adm-link-danger" disabled={busy} onClick={() => setPending({ kind: 'booking', booking: b })}>Hủy</button>}
            {b.series_id && b.status === 'CONFIRMED' && <button type="button" className="adm-link-danger" disabled={busy} onClick={() => setPending({ kind: 'series', booking: b })}>Hủy cả chuỗi</button>}
            {b.status === 'MAINTENANCE' && <button type="button" className="adm-link-danger" disabled={busy} onClick={() => setPending({ kind: 'unlock', booking: b })}>Mở khóa</button>}
          </div></td>
        </tr>)}</tbody></table></div>}
      <Pager page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} disabled={loading} />
    </Card>

    {pending?.kind === 'booking' && <ReasonDialog title={`Hủy booking #${pending.booking.booking_id}`}
      message={<>{pending.booking.customer?.full_name ?? 'Khách'}, {pitchName(pending.booking)} {dateVN(pending.booking.start_time)}. Ai hủy sân?</>}
      choices={cancelChoices(pending.booking)} reasonLabel="Lý do (khách sẽ thấy)" placeholder="Khách báo bận đột xuất" danger
      confirmLabel={c => c === 'CUSTOMER' ? 'Hủy, giữ cọc' : 'Hủy và hoàn tiền'} onConfirm={confirmPending} onClose={() => setPending(null)} />}
    {pending?.kind === 'series' && <ReasonDialog title="Hủy các buổi sắp tới của khách cố định"
      message={<>Hủy mọi buổi chưa đá của <strong>{pending.booking.customer?.full_name ?? 'khách'}</strong> (cùng giờ hằng tuần). Các buổi đã đá giữ nguyên.</>}
      choices={[{ value: 'CUSTOMER', label: 'Khách thôi đặt', detail: 'Giữ cọc các buổi đã đóng cọc.', tone: 'danger' }, { value: 'VENUE', label: 'Sân ngừng phục vụ', detail: 'Hoàn toàn bộ tiền đã thu.' }]}
      placeholder="Đội nghỉ giải" danger confirmLabel={() => 'Hủy các buổi sắp tới'} onConfirm={confirmPending} onClose={() => setPending(null)} />}
    {pending?.kind === 'unlock' && <ReasonDialog title="Mở khóa bảo trì" message={<>{pitchName(pending.booking)}, {dateVN(pending.booking.start_time)} sẽ nhận đặt sân trở lại.</>}
      placeholder="Đã sửa xong" confirmLabel={() => 'Mở khóa'} onConfirm={confirmPending} onClose={() => setPending(null)} />}
  </>;
}
