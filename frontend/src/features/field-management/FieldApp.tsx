import { useState } from 'react';
import { bookingHash } from '../../services/bookingNavigation';
import { PitchesPage } from '../pitches/PitchesPage';
import { BookingsPage } from '../bookings/BookingsPage';
import { AdminBookingsPage } from '../../pages/admin/AdminBookingsPage';
import { AdminPitchesPage } from '../../pages/admin/AdminPitchesPage';
import { AdminSettlementPage } from '../../pages/admin/AdminSettlementPage';
import { AdminRevenuePage } from '../../pages/admin/AdminRevenuePage';
import { AdminDashboardPage } from '../../pages/admin/AdminDashboardPage';
import { AdminStatisticsPage } from '../../pages/admin/AdminStatisticsPage';
import { AdminMatchRequestsPage } from '../../pages/admin/AdminMatchRequestsPage';
import './field.css';

type Tab = 'pitches' | 'bookings' | 'adminDashboard' | 'adminBookings' | 'adminPitches' | 'settlement' | 'revenue' | 'statistics' | 'matchRequests';
/** Embedded in the shared authenticated shell; no separate user or session. */
export function FieldApp({ tab, selectedBookingId = null }: { tab: Tab; selectedBookingId?: number | null }) {
  const [bookingId, setBookingId] = useState<number | null>(null);
  const [balanceId, setBalanceId] = useState<number | null>(null);
  const openBalance = (id: number) => { setBalanceId(id); window.location.hash = '/admin/balance'; };
  return <div className="huy-module">
    {tab === 'pitches' && <PitchesPage onBooked={(id) => { setBookingId(id); window.location.hash = `${bookingHash(id)}&pay=1`; }} />}
    {tab === 'bookings' && <BookingsPage selectedId={selectedBookingId ?? bookingId} />}
    {tab === 'adminDashboard' && <AdminDashboardPage settlement={openBalance} />}
    {tab === 'adminBookings' && <AdminBookingsPage settlement={openBalance} />}
    {tab === 'adminPitches' && <AdminPitchesPage />}
    {tab === 'settlement' && <AdminSettlementPage selectedId={balanceId} />}
    {tab === 'revenue' && <AdminRevenuePage />}
    {tab === 'statistics' && <AdminStatisticsPage />}
    {tab === 'matchRequests' && <AdminMatchRequestsPage />}
  </div>;
}
