import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import type { UserSelf } from '../../types/api';
import { NOTIFICATIONS_CHANGED, notificationsService } from '../../services/notifications';
import { AccountMenu, BellLink, badgeText } from '../shell/HeaderMenus';
import { VenueContact, useVenue } from './venue';
import '../../styles/player.css';

type Item = { path: string; icon: string; label: string; short?: string };
/** Booking first: that is why most customers open the site. Team play is grouped, not mixed in. */
const groups: { title: string; items: Item[] }[] = [
  { title: 'Đặt sân', items: [
    { path: '/dashboard', icon: '⌂', label: 'Trang chủ', short: 'Trang chủ' },
    { path: '/bookings', icon: '▦', label: 'Đặt sân', short: 'Đặt sân' },
    { path: '/my-bookings', icon: '▤', label: 'Lịch đã đặt', short: 'Đã đặt' },
    { path: '/notifications', icon: '◔', label: 'Thông báo' },
  ] },
  { title: 'Đá cùng đội', items: [
    { path: '/matchmaking', icon: '⇄', label: 'Tìm kèo', short: 'Tìm kèo' },
    { path: '/teams', icon: '♧', label: 'Đội bóng của tôi' },
  ] },
  { title: 'Tài khoản', items: [{ path: '/profile', icon: '◎', label: 'Hồ sơ cá nhân', short: 'Tài khoản' }] },
];
const all = groups.flatMap(g => g.items);
/** Phone tab bar: five places a customer goes; notifications sit in the top bar. */
const tabs = ['/dashboard', '/bookings', '/my-bookings', '/matchmaking', '/profile'].map(p => all.find(i => i.path === p)!);
const teamPaths = ['/teams', '/matchmaking'];

/** Unread in-app notices, refreshed on navigation, every 30 s while the tab is visible, and right after one is read. */
function useUnreadCount(route: string) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const load = () => notificationsService.unreadCount(controller.signal).then(setCount).catch(() => { /* a hint only */ });
    void load();
    const timer = window.setInterval(() => { if (document.visibilityState !== 'hidden') void load(); }, 30_000);
    window.addEventListener(NOTIFICATIONS_CHANGED, load);
    return () => { controller.abort(); window.clearInterval(timer); window.removeEventListener(NOTIFICATIONS_CHANGED, load); };
  }, [route]);
  return count;
}

function initials(name: string) {
  return name.trim().split(/\s+/).slice(-2).map(part => part[0]?.toLocaleUpperCase() ?? '').join('') || 'U';
}

function Footer() {
  const venue = useVenue();
  return <footer className="player-footer">
    {venue ? <><strong>{venue.name}</strong><span>{venue.address}</span><a href={`tel:${venue.phone.replace(/[^\d+]/g, '')}`}>☎ {venue.phone}</a></>
      : <strong>Đặt sân bóng trực tuyến</strong>}
  </footer>;
}

export function PlayerShell({ current, route, onLogout, children }: { current: UserSelf; route: string; onLogout: () => void; children: ReactNode }) {
  const venue = useVenue();
  const title = all.find(item => item.path === route)?.label ?? 'Trang chủ';
  const activeTab = (path: string) => route === path || (path === '/matchmaking' && teamPaths.includes(route));
  const unread = useUnreadCount(route);
  return <div className="account-shell player-shell">
    <aside className="account-sidebar">
      <a href="#/dashboard" className="account-brand"><span className="account-brand-mark">F</span><span>{venue?.name ?? 'FOOTBALL'}<small>ĐẶT SÂN TRỰC TUYẾN</small></span></a>
      <nav className="account-nav player-nav" aria-label="Điều hướng chính">{groups.map(group => <div key={group.title} className="player-nav-group">
        <p className="player-nav-title">{group.title}</p>
        {group.items.map(item => <a key={item.path} href={`#${item.path}`} className={route === item.path ? 'account-nav-item active' : 'account-nav-item'} aria-current={route === item.path ? 'page' : undefined}>
          <span className="account-nav-icon">{item.icon}</span><span>{item.label}</span>
          {item.path === '/notifications' && unread > 0 && <span className="player-nav-badge" aria-label={`${unread} chưa đọc`}>{badgeText(unread)}</span>}</a>)}
      </div>)}</nav>
      <div className="player-side-contact"><VenueContact venue={venue} compact /></div>
    </aside>
    <div className="account-workspace">
      <header className="account-topbar">
        <div className="account-breadcrumb"><strong>{title}</strong></div>
        <div className="account-user">
          <VenueContact venue={venue} compact />
          <BellLink href="#/notifications" count={unread} active={route === '/notifications'} label="Thông báo" />
          <AccountMenu name={current.full_name} avatar={initials(current.full_name)} profileHref="#/profile" onLogout={onLogout} />
        </div>
      </header>
      <main className="account-main">{children}<Footer /></main>
    </div>
    <nav className="player-tabbar" aria-label="Điều hướng nhanh">
      {tabs.map(item => <a key={item.path} href={`#${item.path}`} className={activeTab(item.path) ? 'is-active' : ''} aria-current={route === item.path ? 'page' : undefined}>
        <span aria-hidden="true">{item.icon}</span><small>{item.short ?? item.label}</small></a>)}
    </nav>
  </div>;
}

/** For visitors who have not signed in: they can browse pitches, prices and free slots. */
export function PublicShell({ children }: { children: ReactNode }) {
  const venue = useVenue();
  return <div className="player-public">
    <header className="player-public-top">
      <a href="#/bookings" className="player-public-brand"><span className="account-brand-mark">F</span><span>{venue?.name ?? 'Đặt sân bóng'}<small>{venue?.address ?? 'Xem giá và giờ trống, đặt sân trong vài bước'}</small></span></a>
      <div className="player-public-actions">
        <VenueContact venue={venue} compact />
        <a className="account-secondary-button" href="#/login">Đăng nhập</a>
        <a className="account-primary-button" href="#/register">Đăng ký</a>
      </div>
    </header>
    <main className="player-public-main">{children}<Footer /></main>
  </div>;
}
