import { useState } from 'react';
import { PitchesPage } from '../pitches/PitchesPage';
import { BookingsPage } from '../bookings/BookingsPage';
import { AdminBookingsPage } from '../../pages/admin/AdminBookingsPage';
import { AdminPitchesPage } from '../../pages/admin/AdminPitchesPage';
import { AdminSettlementPage } from '../../pages/admin/AdminSettlementPage';
import { AdminRevenuePage } from '../../pages/admin/AdminRevenuePage';
import { DemoNote } from './ui';
import { huyDemo } from '../../services/huyApi';
import './field.css';

type Tab = 'pitches' | 'bookings' | 'adminBookings' | 'adminPitches' | 'settlement' | 'revenue';
const nav: { title: string; items: { tab: Tab; icon: string; label: string }[] }[] = [
  { title: 'NGƯỜI CHƠI', items: [{ tab: 'pitches', icon: '⌕', label: 'Tìm sân' }, { tab: 'bookings', icon: '▤', label: 'Booking của tôi' }] },
  { title: 'QUẢN TRỊ SÂN', items: [{ tab: 'adminBookings', icon: '▦', label: 'Lịch đặt sân' }, { tab: 'adminPitches', icon: '⚽', label: 'Quản lý sân' }, { tab: 'settlement', icon: '◈', label: 'Quyết toán' }, { tab: 'revenue', icon: '▥', label: 'Doanh thu' }] },
];

export function FieldApp() {
  const [tab, setTab] = useState<Tab>('pitches');
  const [bookingId, setBookingId] = useState<number | null>(null);
  const [settlementId, setSettlementId] = useState<number | null>(null);
  const [mobileMenu, setMobileMenu] = useState(false);
  const go = (t: Tab) => { setTab(t); setMobileMenu(false); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  return <div className="huy-shell"><aside className={`huy-sidebar ${mobileMenu ? 'huy-sidebar-open' : ''}`}><div className="huy-brand"><span className="huy-brand-mark">⚽</span><span><b>FIELD<span>HUB</span></b><small>PROJECT 1 · FOOTBALL</small></span></div>
      {nav.map(section => <div key={section.title} className="huy-sidebar-group"><div className="huy-nav-caption">{section.title}</div>{section.items.map(item => <button key={item.tab} type="button" className={`huy-nav ${item.tab === tab ? 'is-active' : ''}`} onClick={() => go(item.tab)}><span>{item.icon}</span>{item.label}<i>›</i></button>)}</div>)}
      <div className="huy-sidebar-foot"><div className="huy-foot-line">● {huyDemo ? 'Chế độ DEMO' : 'Kết nối backend'}</div><small>	Hệ thống quản lý sân bóng</small></div>
    </aside><div className="huy-content"><div className="huy-topbar"><button type="button" className="huy-mobile-toggle" onClick={() => setMobileMenu(!mobileMenu)} aria-label="Mở menu">☰</button><div><span className="huy-top-muted">PROJECT1_SUBJECT</span><span className="huy-top-sep">/</span><strong>{nav.flatMap(s => s.items).find(i => i.tab === tab)?.label}</strong></div><span className="huy-user">H <span>QUẢN TRỊ HỆ THỐNG</span></span></div>
      <main className="huy-main"><DemoNote/>
        {tab === 'pitches' && <PitchesPage onBooked={(id) => { setBookingId(id); go('bookings'); }}/ >}
        {tab === 'bookings' && <BookingsPage selectedId={bookingId} />}
        {tab === 'adminBookings' && <AdminBookingsPage settlement={(id) => { setSettlementId(id); go('settlement'); }} />}
        {tab === 'adminPitches' && <AdminPitchesPage/>}
        {tab === 'settlement' && <AdminSettlementPage selectedId={settlementId} />}
        {tab === 'revenue' && <AdminRevenuePage/>}
      </main><footer className="huy-footer">PROJECT 1 — FOOTBALL FIELD MANAGEMENT <span>FIELDHUB · V1.0</span></footer>
    </div></div>;
}
