import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import type { UserSelf } from '../../types/api';
import { getAdminDashboard } from '../../services/fieldApi';
import { useNow } from '../field-management/ui';
import '../../styles/admin.css';

export type AdminRoute = '/dashboard' | '/admin/bookings' | '/admin/balance' | '/admin/match-requests' | '/admin/revenue' | '/admin/statistics' | '/admin/pitches' | '/profile';
type Counts = { holds: number; refunds: number; unpaid: number };
type Badge = { n: number; tone: 'amber' | 'red'; title: string } | null;
type Item = { path: AdminRoute; label: string; icon: ReactNode; badge?: (c: Counts) => Badge };

/** Simple line icons (24px grid, stroke follows the text colour). */
const icon = (d: string) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>;
const icons = {
  today: icon('M3 11l9-7 9 7M5 10v10h14V10M10 20v-6h4v6'),
  calendar: icon('M4 6h16v14H4zM4 10h16M9 3v4M15 3v4M8 14h3M13 14h3M8 17h3'),
  cash: icon('M3 7h18v10H3zM7 7v10M17 7v10M12 10.5a1.5 1.5 0 100 3 1.5 1.5 0 000-3'),
  revenue: icon('M4 19V5M4 19h16M8 15l3-4 3 2 5-6'),
  stats: icon('M6 19V11M12 19V5M18 19v-6'),
  pitch: icon('M3 5h18v14H3zM12 5v14M12 9.5a2.5 2.5 0 100 5 2.5 2.5 0 000-5M3 9h3v6H3M21 9h-3v6h3'),
  user: icon('M12 12a4 4 0 100-8 4 4 0 000 8M4 21a8 8 0 0116 0'),
  pair: icon('M4 8h12l-3-3M20 16H8l3 3'),
};

/** Grouped by the job the counter staff is doing, not by the module that implements it. */
const groups: { title: string; items: Item[] }[] = [
  { title: 'Vận hành', items: [
    { path: '/dashboard', label: 'Hôm nay', icon: icons.today },
    { path: '/admin/bookings', label: 'Lịch sân', icon: icons.calendar,
      badge: c => c.refunds ? { n: c.refunds, tone: 'red', title: 'Khoản cần hoàn cho khách' } : c.holds ? { n: c.holds, tone: 'amber', title: 'Booking online đang chờ cọc' } : null },
    { path: '/admin/balance', label: 'Thu tiền', icon: icons.cash,
      badge: c => c.unpaid ? { n: c.unpaid, tone: 'amber', title: 'Trận đá xong chưa thu đủ' } : null },
    { path: '/admin/match-requests', label: 'Kèo ghép', icon: icons.pair },
  ] },
  { title: 'Báo cáo', items: [{ path: '/admin/revenue', label: 'Doanh thu', icon: icons.revenue }, { path: '/admin/statistics', label: 'Thống kê', icon: icons.stats }] },
  { title: 'Thiết lập', items: [{ path: '/admin/pitches', label: 'Sân bóng', icon: icons.pitch }, { path: '/profile', label: 'Tài khoản của tôi', icon: icons.user }] },
];

const clock = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' });
const day = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', weekday: 'long', day: 'numeric', month: 'numeric' });

export function AdminShell({ current, route, onLogout, children }: { current: UserSelf; route: AdminRoute; onLogout: () => void; children: ReactNode }) {
  const now = useNow();
  const [counts, setCounts] = useState<Counts>({ holds: 0, refunds: 0, unpaid: 0 });
  useEffect(() => {
    let alive = true;
    const load = () => getAdminDashboard().then(d => {
      if (alive) setCounts({ holds: d.pending_holds.count, refunds: d.pending_refunds.count, unpaid: d.ended_unpaid.count });
    }).catch(() => { /* Badges are a hint; the pages show their own errors. */ });
    void load();
    const timer = window.setInterval(() => { if (document.visibilityState !== 'hidden') void load(); }, 60_000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [route]);
  const title = groups.flatMap(g => g.items).find(i => i.path === route)?.label ?? 'Hôm nay';

  return <div className="adm">
    <aside className="adm-side">
      <a className="adm-brand" href="#/dashboard"><span className="adm-brand-mark" aria-hidden="true" /><span>Quầy điều hành<small>Quản lý cụm sân</small></span></a>
      <nav aria-label="Điều hướng quản trị">{groups.map(group => <div key={group.title} className="adm-group">
        <p className="adm-group-title">{group.title}</p>
        {group.items.map(item => {
          const badge = item.badge?.(counts);
          const active = route === item.path;
          return <a key={item.path} href={`#${item.path}`} className={active ? 'adm-link is-active' : 'adm-link'} aria-current={active ? 'page' : undefined}>
            {item.icon}<span>{item.label}</span>
            {badge && <span className={`adm-count ${badge.tone}`} title={badge.title}>{badge.n}</span>}
          </a>;
        })}
      </div>)}</nav>
      <div className="adm-side-note">
        <span><i style={{ background: '#fcd98a' }} />Việc đang chờ xử lý</span>
        <span><i style={{ background: '#fbc4c4' }} />Tiền cần hoàn cho khách</span>
      </div>
    </aside>
    <div className="adm-work">
      <header className="adm-top">
        <div className="adm-crumb"><span>Quản trị</span><strong>{title}</strong></div>
        <div className="adm-clock" aria-label="Giờ hiện tại"><span className="adm-score">{clock.format(now)}</span><small>{day.format(now)}</small></div>
        <div className="adm-user"><span className="adm-avatar" aria-hidden="true">{current.full_name.trim().charAt(0).toLocaleUpperCase()}</span>
          <span className="adm-user-name">{current.full_name}</span><button type="button" onClick={onLogout}>Đăng xuất</button></div>
      </header>
      <main className="adm-main">{children}</main>
    </div>
  </div>;
}
