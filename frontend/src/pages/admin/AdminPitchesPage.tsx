import { useEffect, useState } from 'react';
import type { PeakHours, Pitch } from '../../types/api';
import { addPitch, changePitch, getPeakHours, getPitches, moneyVN, setPeakHours } from '../../services/huyApi';
import { ApiError } from '../../services/api';
import { Banner, Button, Card, Field, Head, Status, Warning } from '../../features/field-management/ui';
import { Dialog } from './Dialog';

const typeName = (t: Pitch['pitch_type']) => t === 'PITCH_7' ? 'Sân 7 người' : 'Sân 5 người';
const statusName: Record<Pitch['status'], string> = { ACTIVE: 'Đang hoạt động', MAINTENANCE: 'Bảo trì', INACTIVE: 'Ngừng hoạt động' };
const whole = (value: string) => /^\d+$/.test(value.trim()) && Number(value) > 0;

function PeakHoursCard() {
  const [form, setForm] = useState<PeakHours | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { getPeakHours().then(setForm).catch(setError); }, []);
  if (!form) return <Card><h2>Giờ cao điểm</h2><Warning error={error} />{!error && <p className="huy-muted">Đang tải…</p>}</Card>;
  const daily = Boolean(form.peak_start_time && form.peak_end_time);
  async function save(e: React.FormEvent) {
    e.preventDefault(); if (!form) return;
    setBusy(true); setError(null); setSaved('');
    try { setForm(await setPeakHours(form)); setSaved('Đã lưu giờ cao điểm. Giá mới áp dụng cho các lượt đặt từ bây giờ.'); }
    catch (err) { setError(err); } finally { setBusy(false); }
  }
  return <Card className="adm-peak"><h2>Giờ cao điểm</h2>
    <p className="huy-muted">Lượt bắt đầu trong khung này tính theo <strong>giá cao điểm</strong> của từng sân. Booking đã đặt giữ nguyên giá cũ.</p>
    <Warning error={error} />{saved && <Banner tone="success">{saved}</Banner>}
    <form className="adm-peak-form" onSubmit={e => void save(e)}>
      <label className="adm-check"><input type="checkbox" checked={daily} onChange={e => setForm({ ...form, peak_start_time: e.target.checked ? '17:00' : null, peak_end_time: e.target.checked ? '21:00' : null })} /> Có khung cao điểm hằng ngày</label>
      {daily && <div className="adm-pitch-row">
        <Field label="Từ"><input type="time" step={1800} required value={form.peak_start_time ?? ''} onChange={e => setForm({ ...form, peak_start_time: e.target.value })} /></Field>
        <Field label="Đến (không tính)"><input type="time" step={1800} required value={form.peak_end_time ?? ''} onChange={e => setForm({ ...form, peak_end_time: e.target.value })} /></Field>
      </div>}
      <label className="adm-check"><input type="checkbox" checked={form.weekend_is_peak} onChange={e => setForm({ ...form, weekend_is_peak: e.target.checked })} /> Thứ Bảy, Chủ Nhật tính cao điểm cả ngày</label>
      <Button type="submit" disabled={busy}>{busy ? 'Đang lưu…' : 'Lưu giờ cao điểm'}</Button>
    </form>
  </Card>;
}

function EditPitchDialog({ pitch, onClose, onSaved }: { pitch: Pitch; onClose: () => void; onSaved: (message: string) => void }) {
  const [name, setName] = useState(pitch.pitch_name);
  const [price, setPrice] = useState(pitch.price_per_slot.split('.')[0]);
  const [peak, setPeak] = useState(pitch.peak_price_per_slot ? pitch.peak_price_per_slot.split('.')[0] : '');
  const [status, setStatus] = useState<Pitch['status']>(pitch.status);
  const [warning, setWarning] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function save(confirm = false) {
    setError(null);
    if (!name.trim() || !whole(price) || (peak.trim() && !whole(peak))) { setError(new Error('Nhập tên sân và giá là số tiền nguyên, lớn hơn 0.')); return; }
    setBusy(true);
    try {
      await changePitch(pitch.pitch_id, { pitch_name: name.trim(), price_per_slot: `${price.trim()}.00`, peak_price_per_slot: peak.trim() ? `${peak.trim()}.00` : null, status, ...(confirm ? { confirm: true } : {}) });
      onSaved(`Đã cập nhật ${name.trim()}.`); onClose();
    } catch (err) {
      // Taking a pitch with upcoming bookings out of service needs an explicit second confirmation.
      if (err instanceof ApiError && err.code === 'PITCH_HAS_BOOKINGS') setWarning(`${err.message} ${Object.values(err.fields).join(' ')}`);
      else setError(err);
    } finally { setBusy(false); }
  }
  return <Dialog title={`Sửa ${pitch.pitch_name}`} onClose={busy ? () => {} : onClose}>
    <form className="adm-dialog-body" onSubmit={e => { e.preventDefault(); void save(); }}>
      <Field label="Tên sân"><input required maxLength={100} value={name} onChange={e => setName(e.target.value)} /></Field>
      <div className="adm-pitch-row">
        <Field label="Giá thường / lượt 90 phút (VND)"><input inputMode="numeric" required value={price} onChange={e => setPrice(e.target.value)} /></Field>
        <Field label="Giá cao điểm (để trống = như giá thường)"><input inputMode="numeric" value={peak} onChange={e => setPeak(e.target.value)} placeholder="vd. 450000" /></Field>
      </div>
      <Field label="Trạng thái"><select value={status} onChange={e => { setStatus(e.target.value as Pitch['status']); setWarning(''); }}>
        {(['ACTIVE', 'MAINTENANCE', 'INACTIVE'] as const).map(s => <option key={s} value={s}>{statusName[s]}</option>)}</select></Field>
      {warning && <Banner tone="danger"><strong>Sân còn khách đã đặt.</strong> {warning} Bạn vẫn muốn đổi trạng thái?</Banner>}
      <Warning error={error} />
      <div className="adm-dialog-actions">
        <Button variant="outline" onClick={onClose} disabled={busy}>Hủy</Button>
        {warning ? <Button variant="danger" disabled={busy} onClick={() => void save(true)}>Vẫn đổi trạng thái</Button>
          : <Button type="submit" disabled={busy}>{busy ? 'Đang lưu…' : 'Lưu thay đổi'}</Button>}
      </div>
    </form>
  </Dialog>;
}

export function AdminPitchesPage() {
  const [pitches, setPitches] = useState<Pitch[]>([]);
  const [name, setName] = useState('');
  const [type, setType] = useState<'PITCH_5' | 'PITCH_7'>('PITCH_5');
  const [price, setPrice] = useState('300000');
  const [peak, setPeak] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Pitch | null>(null);
  const [rev, setRev] = useState(0);
  useEffect(() => { let alive = true; getPitches().then(x => { if (alive) setPitches(x); }).catch(e => { if (alive) setError(e); }); return () => { alive = false; }; }, [rev]);
  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setError(null); setNotice('');
    try {
      if (!name.trim() || !whole(price) || (peak.trim() && !whole(peak))) throw new Error('Điền tên sân và giá là số tiền nguyên, lớn hơn 0.');
      await addPitch({ pitch_name: name.trim(), pitch_type: type, price_per_slot: `${price}.00`, ...(peak.trim() ? { peak_price_per_slot: `${peak.trim()}.00` } : {}) });
      setName(''); setPeak(''); setRev(n => n + 1); setNotice('Đã thêm sân.');
    } catch (err) { setError(err); } finally { setBusy(false); }
  }
  return <>
    <Head title="Sân bóng" description="Giá thuê theo giờ thường và giờ cao điểm, trạng thái khai thác của từng sân." />
    <Warning error={error} />{notice && <Banner tone="success">{notice}</Banner>}
    <div className="huy-two-col huy-admin-layout">
      <Card><h2>Danh sách sân</h2>
        <div className="huy-table-wrap"><table>
          <thead><tr><th>Sân</th><th>Giá thường</th><th>Giá cao điểm</th><th>Trạng thái</th><th aria-label="Thao tác" /></tr></thead>
          <tbody>{pitches.map(p => <tr key={p.pitch_id}>
            <td><strong>{p.pitch_name}</strong><small className="huy-block">{typeName(p.pitch_type)}</small></td>
            <td><strong>{moneyVN(p.price_per_slot)}</strong></td>
            <td>{p.peak_price_per_slot ? <strong>{moneyVN(p.peak_price_per_slot)}</strong> : <small className="huy-muted">Như giá thường</small>}</td>
            <td><Status state={p.status} /></td>
            <td><div className="adm-row-actions"><Button variant="outline" disabled={busy} onClick={() => setEditing(p)}>Sửa</Button></div></td>
          </tr>)}</tbody></table></div>
      </Card>
      <div>
        <PeakHoursCard />
        <Card><h2>Thêm sân mới</h2><form className="huy-form" onSubmit={e => void create(e)}>
          <Field label="Tên sân"><input required maxLength={100} placeholder="Ví dụ: Sân 5B" value={name} onChange={e => setName(e.target.value)} /></Field>
          <Field label="Loại sân"><select value={type} onChange={e => setType(e.target.value as typeof type)}><option value="PITCH_5">Sân 5 người</option><option value="PITCH_7">Sân 7 người</option></select></Field>
          <div className="adm-pitch-row">
            <Field label="Giá thường (VND)"><input required inputMode="numeric" value={price} onChange={e => setPrice(e.target.value)} /></Field>
            <Field label="Giá cao điểm (nếu có)"><input inputMode="numeric" value={peak} onChange={e => setPeak(e.target.value)} placeholder="vd. 450000" /></Field>
          </div>
          <Button type="submit" disabled={busy}>{busy ? 'Đang tạo…' : 'Thêm sân'}</Button></form></Card>
      </div>
    </div>
    {editing && <EditPitchDialog pitch={editing} onClose={() => setEditing(null)} onSaved={message => { setNotice(message); setRev(n => n + 1); }} />}
  </>;
}
