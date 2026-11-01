import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { errorMessage } from '../../services/api';
import { huyDemo, serverNow, todayVN } from '../../services/huyApi';

export function Banner({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'danger' | 'success' }) {
  return <div className={`huy-banner huy-banner-${tone}`} role={tone === 'danger' ? 'alert' : undefined}>{children}</div>;
}
export function Warning({ error }: { error: unknown }) {
  if (!error) return null;
  return <Banner tone="danger">{errorMessage(error)}</Banner>;
}
export function Head({ kicker, title, description, aside }: { kicker: string; title: string; description: string; aside?: ReactNode }) {
  return <header className="huy-head"><div><div className="huy-kicker">{kicker}</div><h1>{title}<span>.</span></h1><p>{description}</p></div>{aside}</header>;
}
export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`huy-card ${className}`}>{children}</div>;
}
export function Button({ children, type = 'button', variant = 'primary', disabled = false, onClick }: {
  children: ReactNode; type?: 'button' | 'submit'; variant?: 'primary' | 'light' | 'danger' | 'outline';
  disabled?: boolean; onClick?: () => void;
}) { return <button className={`huy-btn huy-btn-${variant}`} type={type} onClick={onClick} disabled={disabled}>{children}</button>; }
export function Status({ state }: { state: string }) {
  const labels: Record<string, string> = { AVAILABLE: 'Còn trống', HELD: 'Đang giữ', BOOKED: 'Đã đặt', MAINTENANCE: 'Bảo trì', ACTIVE: 'Hoạt động', INACTIVE: 'Ngừng hoạt động',
    PENDING_HOLD: 'Chờ cọc', CONFIRMED: 'Đã xác nhận', CANCELLED: 'Đã hủy', EXPIRED: 'Hết hạn', SUCCESS: 'Đã thu', PENDING: 'Đang chờ', FAILED: 'Thất bại', REFUND_PROCESSING: 'Đang hoàn', REFUNDED: 'Đã hoàn' };
  return <span className={`huy-pill huy-pill-${state.toLowerCase()}`}>{labels[state] ?? state}</span>;
}
export const showDate = (date: string) => new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(`${date}T00:00:00+07:00`));
export function dateAfter(days: number): string {
  const d = new Date(`${todayVN()}T00:00:00+07:00`);
  d.setUTCDate(d.getUTCDate() + days);
  const p = new Intl.DateTimeFormat('en-US', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' }).formatToParts(d);
  const g = (name: string) => p.find(x => x.type === name)?.value ?? '';
  return `${g('year')}-${g('month')}-${g('day')}`;
}
export function useNow() {
  const [now, setNow] = useState(serverNow());
  useEffect(() => { const timer = setInterval(() => setNow(serverNow()), 1000); return () => clearInterval(timer); }, []);
  return now;
}
export function countdown(expires: string | null, now: number) {
  if (!expires) return '—';
  const seconds = Math.max(0, Math.ceil((Date.parse(expires) - now) / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}
export function DemoNote() { return huyDemo ? <Banner><strong>CHẾ ĐỘ DEMO:</strong> dữ liệu thử trên trình duyệt, không đặt sân/thu tiền thật. QR ở đây chỉ là bản minh họa.</Banner> : null; }
export function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="huy-field"><span>{label}</span>{children}</label>; }
export function Empty({ children }: { children: ReactNode }) { return <div className="huy-empty">{children}</div>; }
