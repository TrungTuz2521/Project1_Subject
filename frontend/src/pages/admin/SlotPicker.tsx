import type { Availability } from '../../types/api';

type Slot = Availability['slots'][number];
const statusText: Record<Slot['status'], string> = { AVAILABLE: 'Còn trống', HELD: 'Đang giữ', BOOKED: 'Đã đặt', MAINTENANCE: 'Bảo trì' };
export const slotTime = (iso: string) => new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
const shortMoney = (value: string) => `${Math.round(Number(value) / 1000)}k`;

/** The day's 90-minute slots as buttons with their price; only free ones can be picked. */
export function SlotPicker({ slots, value, onChange, error }: { slots: Slot[] | null; value: string; onChange: (time: string) => void; error?: string }) {
  if (error) return <p className="huy-danger">{error}</p>;
  if (!slots) return <p className="huy-muted">Đang tải lịch sân…</p>;
  if (slots.length === 0) return <p className="huy-muted">Ngày này không còn lượt nào (các lượt đã qua giờ).</p>;
  const free = slots.filter(s => s.status === 'AVAILABLE').length;
  const hasPeak = slots.some(s => s.is_peak);
  return <div>
    <div className="adm-slots" role="radiogroup" aria-label="Chọn lượt đá">
      {slots.map(s => {
        const start = slotTime(s.start_time);
        const picked = value === start && s.status === 'AVAILABLE';
        return <button key={s.start_time} type="button" role="radio" aria-checked={picked} disabled={s.status !== 'AVAILABLE'}
          className={`adm-slot is-${s.status.toLowerCase()}${picked ? ' is-picked' : ''}${s.is_peak ? ' is-peak' : ''}`} onClick={() => onChange(start)}>
          <strong>{start}</strong>
          <small>{s.status !== 'AVAILABLE' ? statusText[s.status] : s.price ? shortMoney(s.price) : picked ? 'Đã chọn' : statusText[s.status]}</small>
        </button>;
      })}
    </div>
    <p className="huy-muted">{free ? `${free} lượt còn trống, mỗi lượt 90 phút.` : 'Sân đã kín lịch ngày này. Chọn sân hoặc ngày khác.'}
      {hasPeak && <span className="adm-peak-note"> Lượt có viền cam là giờ cao điểm.</span>}</p>
  </div>;
}
