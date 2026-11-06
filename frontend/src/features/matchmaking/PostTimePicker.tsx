import { useEffect, useState } from 'react';
import { advanceDate, postEnd, postStartOptions, vietnamDate } from './postSchedule';

export function PostTimePicker({ value, onChange }: { value: string; onChange: (start: string, end: string) => void }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, []);
  const day = value.slice(0, 10);
  const options = postStartOptions(day, now);
  const time = value.slice(11, 16);
  const selected = options.includes(time) ? time : '';
  function chooseDate(nextDay: string) {
    const latest = new Date();
    setNow(latest);
    const available = postStartOptions(nextDay, latest);
    const nextTime = available.includes(time) ? time : available[0] ?? '';
    const start = nextDay ? `${nextDay}T${nextTime}` : '';
    onChange(start, nextTime ? postEnd(start) : '');
  }
  return <>
    <div className="form-row"><div className="form-field"><label htmlFor="post-day">Ngày đá (giờ Việt Nam)</label>
      <input id="post-day" type="date" min={vietnamDate(now)} max={advanceDate(vietnamDate(now), 10)} value={day} onChange={e => chooseDate(e.target.value)} required />
    </div><div className="form-field"><label htmlFor="post-start">Giờ bắt đầu (giờ Việt Nam)</label>
      <select id="post-start" value={selected} onChange={e => { const start = `${day}T${e.target.value}`; onChange(start, postEnd(start)); }} required>
        <option value="" disabled>{options.length ? 'Chọn giờ bắt đầu' : 'Không còn khung giờ hợp lệ trong ngày'}</option>
        {options.map(time => <option key={time} value={time}>{time}</option>)}
      </select>
    </div></div>
    <div className="form-field"><label htmlFor="post-end">Giờ kết thúc (tự tính sau 90 phút)</label>
      <input id="post-end" type="text" value={selected ? postEnd(value).slice(11, 16) : ''} readOnly placeholder="Chọn giờ bắt đầu" />
      <small>Chọn ngày trong 10 ngày tới. Mỗi trận kéo dài 90 phút; giờ đã qua không xuất hiện trong danh sách.</small>
    </div>
  </>;
}
