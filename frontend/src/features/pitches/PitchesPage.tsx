import { useEffect, useState } from 'react';
import { createBooking, getAvailability, getPitches, moneyVN, dateVN, timeVN } from '../../services/huyApi';
import type { Availability, Pitch } from '../../types/api';
import { Banner, Button, Card, Empty, Field, Head, Status, Warning, dateAfter } from '../field-management/ui';

export function PitchesPage({ onBooked }: { onBooked: (bookingId: number) => void }) {
  const [filter, setFilter] = useState('ALL');
  const [minPrice, setMinPrice] = useState('');
  const [maxPrice, setMaxPrice] = useState('');
  const [date, setDate] = useState(dateAfter(1));
  const [pitches, setPitches] = useState<Pitch[]>([]);
  const [pitch, setPitch] = useState<number | null>(null);
  const [slots, setSlots] = useState<Availability | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let valid = true;
    setError(null);
    getPitches().then(items => { if (valid) setPitches(items); }).catch(e => { if (valid) setError(e); });
    return () => { valid = false; };
  }, []);
  useEffect(() => {
    setChosen(null);
    if (pitch === null) { setSlots(null); return; }
    let valid = true;
    setLoading(true); setSlots(null); setError(null);
    getAvailability(pitch, date).then(value => { if (valid) setSlots(value); }).catch(e => { if (valid) setError(e); }).finally(() => { if (valid) setLoading(false); });
    return () => { valid = false; };
  }, [pitch, date]);
  const shown = pitches.filter(p => (filter === 'ALL' || p.pitch_type === filter)
    && (!minPrice || Number(p.price_per_slot) >= Number(minPrice))
    && (!maxPrice || Number(p.price_per_slot) <= Number(maxPrice)));
  const selectedPitch = pitches.find(p => p.pitch_id === pitch);
  const selectedSlot = slots?.slots.find(slot => slot.start_time === chosen);
  async function book() {
    if (!selectedPitch || !selectedSlot || saving) return;
    setSaving(true); setError(null);
    try {
      const result = await createBooking({ pitch_id: selectedPitch.pitch_id, start_time: selectedSlot.start_time, end_time: selectedSlot.end_time });
      onBooked(result.booking_id);
    } catch (e) {
      setError(e);
      const newer = await getAvailability(selectedPitch.pitch_id, date).catch(() => null);
      if (newer) setSlots(newer);
    } finally { setSaving(false); }
  }
  return <>
    <Head kicker="PLAYER / 01" title="Tìm sân & lịch trống" description="Chọn sân 5 hoặc sân 7, xem giá và giữ khung giờ 90 phút." />
    <Warning error={error} />
    <div className="huy-toolbar"><Field label="Loại sân"><select value={filter} onChange={e => setFilter(e.target.value)}><option value="ALL">Tất cả loại sân</option><option value="PITCH_5">Sân 5 người</option><option value="PITCH_7">Sân 7 người</option></select></Field>
      <Field label="Giá từ (VND)"><input type="number" min="0" step="10000" placeholder="Không giới hạn" value={minPrice} onChange={e => setMinPrice(e.target.value)} /></Field>
      <Field label="Giá đến (VND)"><input type="number" min="0" step="10000" placeholder="Không giới hạn" value={maxPrice} onChange={e => setMaxPrice(e.target.value)} /></Field>
      <Field label="Ngày đá (tối đa 10 ngày)"><input type="date" value={date} min={dateAfter(0)} max={dateAfter(10)} onChange={e => setDate(e.target.value)} /></Field>
    </div>
    <div className="huy-pitch-list">{shown.map(p => <button key={p.pitch_id} className={`huy-pitch-card ${pitch === p.pitch_id ? 'is-selected' : ''}`} type="button" onClick={() => setPitch(p.pitch_id)}>
      <span className="huy-pitch-icon">⚽</span><span><strong>{p.pitch_name}</strong><small>{p.pitch_type === 'PITCH_5' ? 'Sân 5 người' : p.pitch_type === 'PITCH_7' ? 'Sân 7 người' : 'Sân 11'}</small></span>
      <span className="huy-pitch-end"><b>{moneyVN(p.price_per_slot)}</b><Status state={p.status}/></span>
    </button>)}</div>
    {shown.length === 0 && <Empty>Không tìm thấy sân phù hợp.</Empty>}
    {selectedPitch && <Card className="huy-slot-panel"><div className="huy-flex"><div><h2>Lịch trống · {selectedPitch.pitch_name}</h2><p className="huy-muted">Ngày {date} · Bấm vào khung giờ còn trống</p></div><Status state={selectedPitch.status}/></div>
      {loading ? <p>Đang tải lịch trống…</p> : slots ? <div className="huy-slot-grid">{slots.slots.map(s => <button key={s.start_time} type="button" className={`huy-slot ${s.status !== 'AVAILABLE' ? 'unavailable' : ''} ${chosen === s.start_time ? 'chosen' : ''}`} disabled={s.status !== 'AVAILABLE'} onClick={() => setChosen(s.start_time)} title={s.status}>
        <strong>{timeVN(s.start_time)} – {timeVN(s.end_time)}</strong><Status state={s.status}/></button>)}</div> : <Empty>Chọn sân để xem lịch.</Empty>}
      <div className="huy-book-footer">{selectedSlot ? <div><strong>{dateVN(selectedSlot.start_time)}</strong><p className="huy-muted">90 phút · Giá sân {moneyVN(selectedPitch.price_per_slot)} · Cọc 20% do backend tính khi giữ sân</p></div> : <p className="huy-muted">Chưa chọn khung giờ</p>}
        <Button disabled={!selectedSlot || saving} onClick={book}>{saving ? 'Đang giữ sân…' : 'Giữ sân 5 phút →'}</Button>
      </div>
    </Card>}
    <Banner>Thời hạn giữ sân được backend tạo và kiểm tra. Chọn giờ trên giao diện không đồng nghĩa đã đặt thành công.</Banner>
  </>;
}
