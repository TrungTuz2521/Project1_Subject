const MINUTE = 60_000;
export function vietnamDate(now = new Date()): string {
  return new Date(now.getTime() + 7 * 60 * MINUTE).toISOString().slice(0, 10);
}
export function advanceDate(day: string, days: number): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
/** Match PostService: 90-minute starts from 06:00, ending by 23:00 Vietnam time. */
export function postStartOptions(day: string, now = new Date()): string[] {
  const today = vietnamDate(now);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || day < today || day > advanceDate(today, 10)) return [];
  const result: string[] = [];
  for (let minute = 360; minute + 90 <= 1380; minute += 90) {
    const time = `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`;
    if (Date.parse(`${day}T${time}:00+07:00`) > now.getTime()) result.push(time);
  }
  return result;
}
export function postEnd(start: string): string {
  const timestamp = Date.parse(`${start}:00+07:00`);
  return Number.isFinite(timestamp) ? new Date(timestamp + (90 + 7 * 60) * MINUTE).toISOString().slice(0, 16) : '';
}
