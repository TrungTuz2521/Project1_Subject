import { useEffect, useState } from 'react';
import type { Pitch } from '../../types/api';
import { addPitch, changePitch, getPitches, moneyVN } from '../../services/huyApi';
import { Banner, Button, Card, Field, Head, Status, Warning } from '../../features/field-management/ui';

export function AdminPitchesPage() {
  const [pitches, setPitches] = useState<Pitch[]>([]);
  const [name, setName] = useState('');
  const [type, setType] = useState<'PITCH_5' | 'PITCH_7'>('PITCH_5');
  const [price, setPrice] = useState('300000');
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [rev, setRev] = useState(0);
  useEffect(() => { let alive = true; getPitches().then(x => { if (alive) setPitches(x); }).catch(e => { if (alive) setError(e); }); return () => { alive = false; }; }, [rev]);
  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setError(null); setNotice('');
    try { if (!name.trim() || !/^\d+$/.test(price) || Number(price) <= 0) throw new Error('Điền tên và giá sân hợp lệ.');
      await addPitch({ pitch_name: name.trim(), pitch_type: type, price_per_slot: `${price}.00` }); setName(''); setRev(n => n + 1); setNotice('Đã thêm sân.'); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function modify(p: Pitch) {
    const name = window.prompt('Tên sân mới:', p.pitch_name);
    if (name === null || !name.trim()) return;
    const price = window.prompt('Giá mới cho slot 90 phút (VND):', p.price_per_slot.split('.')[0]);
    if (price === null || !/^\d+$/.test(price) || Number(price) <= 0) return;
    const status = window.prompt('Trạng thái: ACTIVE / MAINTENANCE / INACTIVE', p.status);
    if (!status || !['ACTIVE','MAINTENANCE','INACTIVE'].includes(status)) return;
    setBusy(true); setError(null); setNotice('');
    try { await changePitch(p.pitch_id, { pitch_name: name.trim(), price_per_slot: `${price}.00`, status: status as Pitch['status'] }); setRev(n => n + 1); setNotice('Đã cập nhật sân.'); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <>
    <Head kicker="ADMIN / 02" title="Quản lý sân bóng" description="Thêm sân, sửa tên/giá và thay đổi trạng thái khai thác." />
    <Warning error={error} />{notice && <Banner tone="success">{notice}</Banner>}
    <div className="huy-two-col"><Card><h2>Danh sách sân</h2><div className="huy-pitch-list">{pitches.map(p => <div className="huy-pitch-card" key={p.pitch_id}><span className="huy-pitch-icon">⚽</span><span><strong>{p.pitch_name}</strong><small>{p.pitch_type} · {moneyVN(p.price_per_slot)}</small></span><span className="huy-pitch-end"><Status state={p.status}/><Button variant="outline" disabled={busy} onClick={() => void modify(p)}>Sửa</Button></span></div>)}</div></Card>
      <Card><h2>Thêm sân mới</h2><form className="huy-form" onSubmit={e => void create(e)}><Field label="Tên sân"><input required maxLength={100} placeholder="Ví dụ: Sân 5B" value={name} onChange={e => setName(e.target.value)}/></Field>
        <Field label="Loại sân"><select value={type} onChange={e => setType(e.target.value as typeof type)}><option value="PITCH_5">Sân 5</option><option value="PITCH_7">Sân 7</option></select></Field>
        <Field label="Giá mỗi slot 90 phút (VND)"><input required min={1} type="number" step="1" value={price} onChange={e => setPrice(e.target.value)}/></Field>
        <Button type="submit" disabled={busy}>{busy ? 'Đang tạo…' : 'Thêm sân +'}</Button></form></Card></div>
  </>;
}
