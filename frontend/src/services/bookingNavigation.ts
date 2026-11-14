
export function bookingHash(bookingId: number): string {
  if (!Number.isSafeInteger(bookingId) || bookingId <= 0) throw new Error('Mã booking không hợp lệ.');
  return `#/my-bookings?booking_id=${bookingId}`;
}
export function selectedBookingFromHash(hash: string): number | null {
  const [path, query = ''] = hash.replace(/^#/, '').split('?');
  if (path !== '/my-bookings') return null;
  const value = new URLSearchParams(query).get('booking_id') ?? '';
  const id = Number(value);
  return /^[1-9]\d*$/.test(value) && Number.isSafeInteger(id) ? id : null;
}
