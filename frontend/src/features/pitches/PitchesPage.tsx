import { useEffect, useMemo, useState } from 'react';
import { createBooking, getAvailability, getPitches, moneyVN, timeVN } from '../../services/fieldApi';
import type { Availability, Pitch } from '../../types/api';
import { Banner, Button, Empty, Field, Head, Warning, dateAfter } from '../field-management/ui';

const DEPOSIT_PERCENT = 20;
const INTENT_KEY = 'ffm.booking-intent';
type Slot = Availability['slots'][number];
type Row = { pitch: Pitch; slots: Slot[] };
type Pick = { pitchId: number; start: string };
const typeName = (t: Pitch['pitch_type']) => t === 'PITCH_5' ? 'Sân 5 người' : t === 'PITCH_7' ? 'Sân 7 người' : 'Sân 11 người';
const hhmm = (iso: string) => timeVN(iso);
const shortMoney = (v: string) => `${Math.round(Number(v) / 1000)}k`;
/** "T5, 12/11": weekday and date, what people say when they book. */
export const dayLabel = (iso: string) => new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', weekday: 'short', day: '2-digit', month: '2-digit' }).format(new Date(iso));

/** Remember what a visitor picked so login brings them back to the same pitch and time. */
export function saveIntent(pick: Pick, date: string) { try { sessionStorage.setItem(INTENT_KEY, JSON.stringify({ ...pick, date })); } catch { /* storage blocked */ } }
function takeIntent(): (Pick & { date: string }) | null {
  try { const raw = sessionStorage.getItem(INTENT_KEY); sessionStorage.removeItem(INTENT_KEY); return raw ? JSON.parse(raw) : null; } catch { return null; }
}

export function PitchesPage({ onBooked, signedIn = true }: { onBooked: (bookingId: number) => void; signedIn?: boolean }) {
  const intent = useMemo(() => (signedIn ? takeIntent() : null), [signedIn]);
  const [filter, setFilter] = useState('ALL');
  const [minPrice, setMinPrice] = useState('');
  const [maxPrice, setMaxPrice] = useState('');
  const [date, setDate] = useState(intent?.date ?? dateAfter(0));
  const [pitches, setPitches] = useState<Pitch[]>([]);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [pick, setPick] = useState<Pick | null>(intent ? { pitchId: intent.pitchId, start: intent.start } : null);
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let valid = true;
    getPitches().then(items => { if (valid) setPitches(items); }).catch(e => { if (valid) setError(e); });
    return () => { valid = false; };
  }, []);
  const inRange = (value: string | null | undefined) => value != null && (!minPrice || Number(value) >= Number(minPrice)) && (!maxPrice || Number(value) <= Number(maxPrice));
  const shown = pitches.filter(p => p.status === 'ACTIVE' && (filter === 'ALL' || p.pitch_type === filter) && (inRange(p.price_per_slot) || inRange(p.peak_price_per_slot)));
  const key = shown.map(p => p.pitch_id).join(',');
  // Every shown pitch's free slots for the day at once: "what is free tonight" is one look, not one click per pitch.
  useEffect(() => {
    if (!shown.length) { setRows([]); return; }
    let valid = true; setRows(null);
    Promise.all(shown.map(p => getAvailability(p.pitch_id, date).then(a => ({ pitch: p, slots: a.slots }))))
      .then(r => { if (valid) setRows(r); }).catch(e => { if (valid) { setError(e); setRows([]); } });
    return () => { valid = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, date, revision]);
  useEffect(() => { if (!intent) setPick(null); }, [date]); // eslint-disable-line react-hooks/exhaustive-deps

  const times = [...new Set((rows ?? []).flatMap(r => r.slots.map(s => hhmm(s.start_time))))].sort();
  const selected = rows?.find(r => r.pitch.pitch_id === pick?.pitchId);
  const slot = selected?.slots.find(s => s.start_time === pick?.start && s.status === 'AVAILABLE');
  const price = slot?.price ?? selected?.pitch.price_per_slot ?? '0';
  const deposit = String(Math.ceil(Number(price) * DEPOSIT_PERCENT / 100));
  const free = (rows ?? []).reduce((n, r) => n + r.slots.filter(s => s.status === 'AVAILABLE').length, 0);

  async function book() {
    if (!selected || !slot || saving) return;
    if (!signedIn) { saveIntent({ pitchId: selected.pitch.pitch_id, start: slot.start_time }, date); window.location.hash = '/login'; return; }
    setSaving(true); setError(null);
    try {
      const result = await createBooking({ pitch_id: selected.pitch.pitch_id, start_time: slot.start_time, end_time: slot.end_time });
      onBooked(result.booking_id);
    } catch (e) { setError(e); setRevision(n => n + 1); }
    finally { setSaving(false); }
  }
  const choose = (pitchId: number, s: Slot) => s.status === 'AVAILABLE' && setPick({ pitchId, start: s.start_time });
  const isPicked = (pitchId: number, s: Slot) => pick?.pitchId === pitchId && pick.start === s.start_time;

  return <div className="book-page">
    <Head title="Đặt sân" description="Chọn ngày, bấm vào giờ còn trống của sân bạn muốn. Giá là giá cả lượt 90 phút." />
    {intent && signedIn && <Banner tone="success">Bạn đã đăng nhập. Lượt bạn chọn trước đó vẫn được giữ bên dưới, bấm "Giữ sân" để tiếp tục.</Banner>}
    <Warning error={error} />
    <div className="book-filters">
      <div className="book-days" role="group" aria-label="Chọn nhanh ngày">
        <button type="button" className={date === dateAfter(0) ? 'is-on' : ''} onClick={() => setDate(dateAfter(0))}>Hôm nay</button>
        <button type="button" className={date === dateAfter(1) ? 'is-on' : ''} onClick={() => setDate(dateAfter(1))}>Ngày mai</button>
      </div>
      <Field label="Ngày đá"><input type="date" value={date} min={dateAfter(0)} max={dateAfter(10)} onChange={e => e.target.value && setDate(e.target.value)} /></Field>
      <Field label="Loại sân"><select value={filter} onChange={e => setFilter(e.target.value)}><option value="ALL">Tất cả</option><option value="PITCH_5">Sân 5 người</option><option value="PITCH_7">Sân 7 người</option></select></Field>
      <span className="book-price-filter"><Field label="Giá từ"><input type="number" min="0" step="50000" placeholder="VND" value={minPrice} onChange={e => setMinPrice(e.target.value)} /></Field>
      <Field label="Giá đến"><input type="number" min="0" step="50000" placeholder="VND" value={maxPrice} onChange={e => setMaxPrice(e.target.value)} /></Field></span>
    </div>

    <p className="book-hint">{rows === null ? 'Đang tải giờ trống…' : `${dayLabel(`${date}T12:00:00+07:00`)}: còn ${free} lượt trống.`}
      {rows?.some(r => r.slots.some(s => s.is_peak)) && <> Giờ có viền cam là <span className="huy-peak-badge">Cao điểm</span>.</>}</p>
    {rows && shown.length === 0 && <Empty>Không có sân phù hợp. Thử bỏ bớt điều kiện giá hoặc loại sân.</Empty>}
    {rows && shown.length > 0 && (times.length === 0 || free === 0) && <div className="book-none">
      <p>{times.length === 0 ? 'Hôm nay đã hết giờ có thể đặt.' : 'Ngày này các sân đã kín lịch.'}</p>
      <Button onClick={() => setDate(date === dateAfter(0) ? dateAfter(1) : dateAfter(0))}>{date === dateAfter(0) ? 'Xem giờ trống ngày mai' : 'Xem giờ trống hôm nay'}</Button>
    </div>}

    {rows && times.length > 0 && <>
      {/* Desktop: one table, pitches down and times across. */}
      <div className="book-matrix-wrap"><table className="book-matrix">
        <thead><tr><th scope="col">Sân</th>{times.map(t => <th key={t} scope="col">{t}</th>)}</tr></thead>
        <tbody>{rows.map(({ pitch, slots }) => <tr key={pitch.pitch_id}>
          <th scope="row"><strong>{pitch.pitch_name}</strong><small>{typeName(pitch.pitch_type)}</small>
            <small className="book-row-price">{moneyVN(pitch.price_per_slot)}{pitch.peak_price_per_slot && pitch.peak_price_per_slot !== pitch.price_per_slot ? ` · cao điểm ${moneyVN(pitch.peak_price_per_slot)}` : ''}</small></th>
          {times.map(t => {
            const s = slots.find(x => hhmm(x.start_time) === t);
            if (!s) return <td key={t} className="is-past" aria-label="Đã qua" />;
            return <td key={t}><button type="button" disabled={s.status !== 'AVAILABLE'} onClick={() => choose(pitch.pitch_id, s)}
              className={`book-cell${isPicked(pitch.pitch_id, s) ? ' is-picked' : ''}${s.is_peak ? ' is-peak' : ''}`} aria-pressed={isPicked(pitch.pitch_id, s)}
              title={s.status === 'AVAILABLE' ? `${pitch.pitch_name} ${t}, ${s.price ? moneyVN(s.price) : ''}` : 'Đã có người đặt'}>
              {s.status === 'AVAILABLE' ? <>{s.price ? shortMoney(s.price) : 'Trống'}</> : <span>Hết</span>}</button></td>;
          })}
        </tr>)}</tbody>
      </table></div>
      {/* Phone: one block per pitch, free times as large buttons. */}
      <div className="book-stack">{rows.map(({ pitch, slots }) => {
        const open = slots.filter(s => s.status === 'AVAILABLE');
        return <section key={pitch.pitch_id} className="book-stack-pitch">
          <header><strong>{pitch.pitch_name}</strong><small>{typeName(pitch.pitch_type)} · {moneyVN(pitch.price_per_slot)}{pitch.peak_price_per_slot && pitch.peak_price_per_slot !== pitch.price_per_slot ? ` · cao điểm ${moneyVN(pitch.peak_price_per_slot)}` : ''}</small></header>
          {open.length === 0 ? <p className="home-muted">Hết giờ trống ngày này.</p> : <div className="book-chips">{open.map(s =>
            <button key={s.start_time} type="button" onClick={() => choose(pitch.pitch_id, s)} aria-pressed={isPicked(pitch.pitch_id, s)}
              className={`book-chip${isPicked(pitch.pitch_id, s) ? ' is-picked' : ''}${s.is_peak ? ' is-peak' : ''}`}>
              <strong>{hhmm(s.start_time)}</strong><small>{s.price ? shortMoney(s.price) : ''}</small></button>)}</div>}
        </section>;
      })}</div>
    </>}

    <div className={`book-bar${slot ? ' is-ready' : ''}`}>
      {slot && selected ? <div className="book-bar-info">
        <strong>{selected.pitch.pitch_name} · {hhmm(slot.start_time)}–{hhmm(slot.end_time)} · {moneyVN(price)}{slot.is_peak ? ' (cao điểm)' : ''}</strong>
        <small>Cọc {DEPOSIT_PERCENT}%: <b>{moneyVN(deposit)}</b> bằng QR trong 5 phút<span className="book-bar-more">, phần còn lại trả tại sân. Hủy sau khi cọc sẽ mất tiền cọc</span>.</small>
      </div> : <div className="book-bar-info"><strong>Chưa chọn giờ</strong><small>Bấm vào một giờ còn trống ở bảng trên.</small></div>}
      <Button disabled={!slot || saving} onClick={() => void book()}>{saving ? 'Đang giữ sân…' : signedIn ? 'Giữ sân và đặt cọc' : 'Đăng nhập để đặt'}</Button>
    </div>
  </div>;
}
