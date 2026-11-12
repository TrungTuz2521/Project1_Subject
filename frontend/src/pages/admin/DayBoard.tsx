import { useEffect, useState } from 'react';
import type { AdminBooking, Availability, Pitch } from '../../types/api';
import { getAdminBookingsPage, getAvailability, moneyVN } from '../../services/fieldApi';
import { Card, Field, dateAfter } from '../../features/field-management/ui';
import { slotTime } from './SlotPicker';

type Row = { pitch: Pitch; slots: Availability['slots'] };
const label: Record<string, string> = { HELD: 'Đang giữ', BOOKED: 'Đã đặt', MAINTENANCE: 'Bảo trì' };

/** The whole day at a glance: pitches down, 90-minute slots across. Free cells start a booking. */
export function DayBoard({ pitches, date, onDate, onPick, revision }: {
  pitches: Pitch[]; date: string; onDate: (date: string) => void; onPick: (pitchId: number, time: string) => void; revision: number;
}) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [bookings, setBookings] = useState<AdminBooking[]>([]);
  const [error, setError] = useState('');
  const active = pitches.filter(p => p.status === 'ACTIVE');
  const key = active.map(p => p.pitch_id).join(',');
  useEffect(() => {
    if (!active.length) { setRows([]); return; }
    let live = true; setRows(null); setError('');
    Promise.all([Promise.all(active.map(p => getAvailability(p.pitch_id, date).then(a => ({ pitch: p, slots: a.slots })))),
      getAdminBookingsPage({ from: date, to: date, page: 1, page_size: 100 })])
      .then(([board, list]) => { if (live) { setRows(board); setBookings(list.data); } })
      .catch(e => { if (live) { setRows([]); setError(e instanceof Error ? e.message : 'Không tải được lịch.'); } });
    return () => { live = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, date, revision]);

  const times = [...new Set((rows ?? []).flatMap(r => r.slots.map(s => slotTime(s.start_time))))].sort();
  const who = (pitchId: number, start: string) => bookings.find(b => b.pitch_id === pitchId && slotTime(b.start_time) === start
    && ['CONFIRMED', 'PENDING_HOLD', 'MAINTENANCE'].includes(b.status));
  const free = (rows ?? []).reduce((n, r) => n + r.slots.filter(s => s.status === 'AVAILABLE').length, 0);

  return <Card className="adm-board-day">
    <div className="adm-list-head">
      <div><h2>Lịch trong ngày</h2><p className="huy-muted">{rows ? `${free} lượt còn trống. Bấm ô trống để đặt sân cho khách.` : 'Đang tải…'}</p></div>
      <div className="adm-filters">
        <div className="adm-day-nav">
          <button type="button" onClick={() => onDate(dateAfter(0))} className={date === dateAfter(0) ? 'is-on' : ''}>Hôm nay</button>
          <button type="button" onClick={() => onDate(dateAfter(1))} className={date === dateAfter(1) ? 'is-on' : ''}>Ngày mai</button>
        </div>
        <Field label="Ngày"><input type="date" min={dateAfter(0)} max={dateAfter(100)} value={date} onChange={e => e.target.value && onDate(e.target.value)} /></Field>
      </div>
    </div>
    {error && <p className="huy-danger">{error}</p>}
    {rows && rows.length > 0 && times.length === 0 && <p className="huy-muted">Ngày này không còn lượt nào (các lượt đã qua giờ).</p>}
    {rows && times.length > 0 && <div className="adm-grid-wrap"><table className="adm-grid">
      <thead><tr><th scope="col">Sân</th>{times.map(t => <th key={t} scope="col">{t}</th>)}</tr></thead>
      <tbody>{rows.map(({ pitch, slots }) => <tr key={pitch.pitch_id}>
        <th scope="row"><strong>{pitch.pitch_name}</strong><small>{pitch.pitch_type === 'PITCH_7' ? 'Sân 7' : 'Sân 5'}</small></th>
        {times.map(t => {
          const slot = slots.find(s => slotTime(s.start_time) === t);
          if (!slot) return <td key={t} className="is-past" />;
          if (slot.status === 'AVAILABLE') return <td key={t}><button type="button" className={`adm-cell is-free${slot.is_peak ? ' is-peak' : ''}`} onClick={() => onPick(pitch.pitch_id, t)}
            title={`Đặt ${pitch.pitch_name} lúc ${t}`}><span>Trống</span>{slot.price && <small>{moneyVN(slot.price)}{slot.is_peak ? ' · cao điểm' : ''}</small>}</button></td>;
          const b = who(pitch.pitch_id, t);
          const name = b?.booking_type === 'MAINTENANCE_LOCK' ? 'Bảo trì' : b?.customer?.full_name ?? label[slot.status];
          return <td key={t}><div className={`adm-cell is-${slot.status.toLowerCase()}${b?.arrival_status === 'ARRIVED' ? ' is-arrived' : ''}`}
            title={b ? `#${b.booking_id} ${name}${b.customer?.phone ? `, ${b.customer.phone}` : ''}` : label[slot.status]}>
            <span>{name}</span><small>{b?.series_id ? 'Cố định' : b?.arrival_status === 'ARRIVED' ? 'Đã đến' : label[slot.status]}</small></div></td>;
        })}
      </tr>)}</tbody>
    </table></div>}
  </Card>;
}
