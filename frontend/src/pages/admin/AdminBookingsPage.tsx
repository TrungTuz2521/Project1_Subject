import { useEffect, useState } from 'react';
import type { Booking, Pitch } from '../../types/api';
import {
  getAdminBookings, getPitches, addAdminBooking, createMaintenance,
  cancelAdminBooking, moveAdminBooking, removeMaintenance, dateVN, moneyVN,
} from '../../services/huyApi';
import { Banner, Button, Card, Empty, Field, Head, Status, Warning, dateAfter } from '../../features/field-management/ui';

const times = Array.from({ length: 32 }, (_, n) => { const m = 360 + n * 30; return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`; });
export function AdminBookingsPage({ settlement }: { settlement: (id: number) => void }) {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [pitches, setPitches] = useState<Pitch[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState('ALL');
  const [date, setDate] = useState(dateAfter(1));
  const [time, setTime] = useState('18:00');
  const [pitchId, setPitchId] = useState(1);
  const [userId, setUserId] = useState(2);
  const [reason, setReason] = useState('Đặt sân tại quầy');
  const [mode, setMode] = useState<'manual' | 'maintenance' | 'move'>('manual');
  const [moveId, setMoveId] = useState(0);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    Promise.all([getAdminBookings(), getPitches()]).then(([bs, ps]) => {
      if (live) { setBookings(bs); setPitches(ps); if (ps.length && !ps.some(p => p.pitch_id === pitchId)) setPitchId(ps[0].pitch_id); }
    }).catch(e => { if (live) setError(e); });
    return () => { live = false; };
  // pitchId intentionally excluded: we only normalize it on refresh when invalid.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revision]);
  const visible = bookings.filter(b => filter === 'ALL' || b.status === filter).sort((a, b) => Date.parse(b.start_time) - Date.parse(a.start_time));
  const validPitch = pitches.find(p => p.pitch_id === pitchId);
  async function refresh() { setRevision(n => n + 1); }
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (busy) return;
    setBusy(true); setError(null); setSuccess('');
    try {
      const start = new Date(`${date}T${time}:00+07:00`);
      if (Number.isNaN(start.getTime())) throw new Error('Ngày giờ không hợp lệ.');
      const args = { pitch_id: pitchId, start_time: start.toISOString(), end_time: new Date(start.getTime() + 90 * 60000).toISOString(), reason };
      if (mode === 'manual') await addAdminBooking({ ...args, user_id: userId, note: reason });
      if (mode === 'maintenance') await createMaintenance(args);
      if (mode === 'move') { if (!moveId) throw new Error('Chọn booking cần đổi lịch.'); await moveAdminBooking(moveId, args); }
      setSuccess(`${mode === 'manual' ? 'Tạo lịch tại quầy' : mode === 'maintenance' ? 'Khóa bảo trì' : 'Đổi lịch'} thành công.`);
      await refresh();
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function cancel(b: Booking) {
    const reason = window.prompt(b.status === 'MAINTENANCE' ? 'Nhập lý do mở khóa bảo trì:' : 'Nhập lý do hủy (bắt buộc):');
    if (!reason?.trim() || busy) return;
    setBusy(true); setError(null); setSuccess('');
    try {
      if (b.status === 'MAINTENANCE') await removeMaintenance(b.booking_id, reason);
      else await cancelAdminBooking(b.booking_id, reason);
      setSuccess('Đã cập nhật trạng thái lịch đặt.'); await refresh();
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <>
    <Head kicker="ADMIN / 01" title="Quản lý lịch đặt sân" description="Tạo lịch tại quầy, khóa bảo trì, đổi lịch hoặc hủy có lý do." aside={<Button variant="outline" onClick={() => void refresh()}>↻ Làm mới</Button>} />
    <Warning error={error} />{success && <Banner tone="success">{success}</Banner>}
    <div className="huy-two-col huy-admin-layout"><Card><h2>Danh sách booking</h2><div className="huy-toolbar"><Field label="Trạng thái"><select value={filter} onChange={e => setFilter(e.target.value)}><option value="ALL">Tất cả</option><option value="PENDING_HOLD">Chờ cọc</option><option value="CONFIRMED">Đã xác nhận</option><option value="MAINTENANCE">Bảo trì</option><option value="CANCELLED">Đã hủy</option><option value="EXPIRED">Hết hạn</option></select></Field></div>
      {visible.length === 0 ? <Empty>Chưa có lịch đặt phù hợp.</Empty> : <div className="huy-table-wrap"><table><thead><tr><th>Booking</th><th>Sân</th><th>Thời gian</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{visible.map(b => <tr key={b.booking_id}><td><strong>#{b.booking_id}</strong><small className="huy-block">{b.booking_type}</small></td><td>{pitches.find(p => p.pitch_id === b.pitch_id)?.pitch_name ?? `#${b.pitch_id}`}</td><td>{dateVN(b.start_time)}</td><td><Status state={b.status}/></td><td><div className="huy-table-actions">{b.status === 'CONFIRMED' && Date.parse(b.end_time) <= Date.now() && <button type="button" onClick={() => settlement(b.booking_id)}>Quyết toán</button>}{['CONFIRMED', 'PENDING_HOLD', 'MAINTENANCE'].includes(b.status) && <button type="button" className="huy-link-danger" disabled={busy} onClick={() => void cancel(b)}>{b.status === 'MAINTENANCE' ? 'Mở khóa' : 'Hủy'}</button>}</div><small className="huy-block">{moneyVN(b.total_amount)}</small></td></tr>)}</tbody></table></div>}
    </Card>
      <Card><h2>Cập nhật lịch</h2><form onSubmit={e => void submit(e)} className="huy-form"><Field label="Nghiệp vụ"><select value={mode} onChange={e => setMode(e.target.value as typeof mode)}><option value="manual">Đặt sân tại quầy</option><option value="maintenance">Khóa lịch bảo trì</option><option value="move">Đổi lịch booking</option></select></Field>
        {mode === 'move' && <Field label="Booking cần đổi lịch"><select value={moveId} onChange={e => setMoveId(Number(e.target.value))}><option value={0}>Chọn booking</option>{bookings.filter(b => ['CONFIRMED', 'PENDING_HOLD'].includes(b.status)).map(b => <option key={b.booking_id} value={b.booking_id}>#{b.booking_id} — {dateVN(b.start_time)}</option>)}</select></Field>}
        {mode === 'manual' && <Field label="ID người đặt (phải tồn tại)"><input type="number" min="1" required value={userId} onChange={e => setUserId(Number(e.target.value))}/></Field>}
        <Field label="Sân"><select value={pitchId} onChange={e => setPitchId(Number(e.target.value))}>{pitches.map(p => <option key={p.pitch_id} value={p.pitch_id}>{p.pitch_name} · {moneyVN(p.price_per_slot)}</option>)}</select></Field>
        <Field label="Ngày"><input type="date" required min={dateAfter(0)} max={dateAfter(10)} value={date} onChange={e => setDate(e.target.value)} /></Field>
        <Field label="Giờ bắt đầu"><select value={time} onChange={e => setTime(e.target.value)}>{times.map(x => <option key={x} value={x}>{x}</option>)}</select></Field>
        <Field label="{mode === 'manual' ? 'Ghi chú' : 'Lý do (bắt buộc)'}"><input required maxLength={255} value={reason} onChange={e => setReason(e.target.value)} /></Field>
        {validPitch && <p className="huy-muted">Thời lượng cố định 90 phút. Xung đột lịch được backend kiểm tra trước khi tạo.</p>}
        <Button type="submit" disabled={busy || !validPitch}>{busy ? 'Đang xử lý…' : 'Xác nhận thao tác'}</Button></form></Card></div>
    <Banner>Lịch bảo trì không tính là booking khách. Đổi sang sân khác giá phải hủy và đặt lại, không âm thầm thay tiền.</Banner>
  </>;
}
