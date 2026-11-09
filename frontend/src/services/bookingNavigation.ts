import type { Notification } from '../types/api';
import { matchesService } from './matches';
import { proposalsService } from './proposals';

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
/** Resolve through authenticated APIs: notification IDs alone never authorize a booking. */
export async function bookingForNotification(notification: Notification): Promise<number> {
  let id: number | null | undefined;
  if (notification.match_id) {
    const match = (await matchesService.get(notification.match_id)).data;
    id = match.booking_id ?? match.booking?.booking_id;
  } else if (notification.proposal_id) {
    id = (await proposalsService.get(notification.proposal_id)).data.booking_id;
  }
  if (!id) throw new Error('Chưa tìm thấy booking của thông báo. Hãy tải lại thông tin trận.');
  bookingHash(id); // validate the returned identifier before routing
  return id;
}
