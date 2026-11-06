import { useState } from 'react';
import { PitchesPage } from '../pitches/PitchesPage';
import { BookingsPage } from '../bookings/BookingsPage';
import { AdminBookingsPage } from '../../pages/admin/AdminBookingsPage';
import { AdminPitchesPage } from '../../pages/admin/AdminPitchesPage';
import { AdminSettlementPage } from '../../pages/admin/AdminSettlementPage';
import { AdminRevenuePage } from '../../pages/admin/AdminRevenuePage';
import { DemoNote } from './ui';
import './field.css';

type Tab = 'pitches' | 'bookings' | 'adminBookings' | 'adminPitches' | 'settlement' | 'revenue';
/** Embedded in the shared authenticated shell; no separate user or session. */
export function FieldApp({ tab }: { tab: Tab }) {
  const [bookingId, setBookingId] = useState<number | null>(null);
  const [balanceId, setBalanceId] = useState<number | null>(null);
  return <div className="huy-module"><DemoNote />
    {tab === 'pitches' && <PitchesPage onBooked={(id) => { setBookingId(id); window.location.hash = '/my-bookings'; }} />}
    {tab === 'bookings' && <BookingsPage selectedId={bookingId} />}
    {tab === 'adminBookings' && <AdminBookingsPage settlement={(id) => { setBalanceId(id); window.location.hash = '/admin/balance'; }} />}
    {tab === 'adminPitches' && <AdminPitchesPage />}
    {tab === 'settlement' && <AdminSettlementPage selectedId={balanceId} />}
    {tab === 'revenue' && <AdminRevenuePage />}
  </div>;
}
