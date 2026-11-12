const tz = 'Asia/Ho_Chi_Minh';
const parts = new Intl.DateTimeFormat('en-GB', { timeZone: tz, weekday: 'short', day: '2-digit', month: '2-digit' });
const hm = new Intl.DateTimeFormat('vi-VN', { timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false });
const days: Record<string, string> = { Sun: 'CN', Mon: 'T2', Tue: 'T3', Wed: 'T4', Thu: 'T5', Fri: 'T6', Sat: 'T7' };
/** "T7 15/11" in Vietnam time, the way people say a playing day. */
function dayOf(d: Date) {
  const p = Object.fromEntries(parts.formatToParts(d).map(x => [x.type, x.value]));
  return `${days[p.weekday] ?? p.weekday} ${p.day}/${p.month}`;
}
export const dayChip = (isoDate: string) => dayOf(new Date(`${isoDate}T12:00:00+07:00`));
export const time = (iso: string) => hm.format(new Date(iso));
/** "18:00–19:30, T7 15/11". */
export function slotLabel(start: string, end?: string | null) {
  return `${time(start)}${end ? '–' + time(end) : ''}, ${dayOf(new Date(start))}`;
}
/** "còn 5 giờ 20 phút" until a moment, or "" once it passed. */
export function timeLeft(iso: string, now = Date.now()) {
  const minutes = Math.floor((Date.parse(iso) - now) / 60000);
  if (minutes <= 0) return '';
  const days = Math.floor(minutes / 1440), hours = Math.floor((minutes % 1440) / 60), mins = minutes % 60;
  if (days) return `còn ${days} ngày ${hours} giờ`;
  if (hours) return `còn ${hours} giờ ${mins} phút`;
  return `còn ${mins} phút`;
}
export const money = (value: string | number) => `${Math.round(Number(value)).toLocaleString('vi-VN')} ₫`;
export const tel = (phone: string) => `tel:${phone.replace(/[^\d+]/g, '')}`;
