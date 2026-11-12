import { useEffect, useState } from 'react';
import { api } from '../../services/client';
import type { ApiResponse, FieldComplex } from '../../types/api';

type Venue = Pick<FieldComplex, 'name' | 'phone' | 'address'> & { opening_time?: string; closing_time?: string };

let cached: Promise<Venue | null> | null = null;

/** Name, address and phone of the complex: public, loaded once per page load. */
function loadVenue(): Promise<Venue | null> {
  cached ??= api.request<ApiResponse<FieldComplex>>('/field-complex', { auth: false })
    .then(r => ({ name: r.data.name, phone: r.data.phone, address: r.data.address, opening_time: r.data.policy.opening_time, closing_time: r.data.policy.closing_time }))
    .catch(() => { cached = null; return null; });
  return cached;
}

export function useVenue(): Venue | null {
  const [venue, setVenue] = useState<Venue | null>(null);
  useEffect(() => { let live = true; void loadVenue().then(v => { if (live) setVenue(v); }); return () => { live = false; }; }, []);
  return venue;
}

const telHref = (phone: string) => `tel:${phone.replace(/[^\d+]/g, '')}`;
const mapHref = (address: string) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`;

/** Call / directions for the venue. `compact` for the top bar, full card elsewhere. */
export function VenueContact({ venue, compact = false }: { venue: Venue | null; compact?: boolean }) {
  if (!venue) return null;
  if (compact) return <a className="venue-call" href={telHref(venue.phone)} title={`Gọi ${venue.name}`}><span aria-hidden="true">☎</span><span>{venue.phone}</span></a>;
  return <section className="venue-card" aria-label="Liên hệ sân">
    <div><strong>{venue.name}</strong><small>{venue.address}</small>
      {venue.opening_time && <small>Mở cửa {venue.opening_time}–{venue.closing_time} hằng ngày</small>}</div>
    <div className="venue-actions">
      <a className="account-primary-button" href={telHref(venue.phone)}>☎ Gọi {venue.phone}</a>
      <a className="account-secondary-button" href={mapHref(venue.address)} target="_blank" rel="noreferrer">Chỉ đường</a>
    </div>
  </section>;
}
