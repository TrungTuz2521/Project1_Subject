import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Notification } from '../types/api';
const { matchGet, proposalGet } = vi.hoisted(() => ({ matchGet: vi.fn(), proposalGet: vi.fn() }));
vi.mock('./matches', () => ({ matchesService: { get: matchGet } }));
vi.mock('./proposals', () => ({ proposalsService: { get: proposalGet } }));
import { bookingForNotification, bookingHash, selectedBookingFromHash } from './bookingNavigation';
beforeEach(() => { matchGet.mockReset(); proposalGet.mockReset(); });
describe('deposit notification links', () => {
  it('opens the booking returned by the match, rather than using the match or notification ID', async () => {
    matchGet.mockResolvedValue({ data: { match_id: 12, booking_id: 30002 } });
    const id = await bookingForNotification({ notification_id: 90, notification_type: 'BOOKING_HOLD', match_id: 12, proposal_id: 5 } as Notification);
    expect(matchGet).toHaveBeenCalledWith(12);
    expect(proposalGet).not.toHaveBeenCalled();
    expect(selectedBookingFromHash(bookingHash(id))).toBe(30002);
  });
  it('resolves an older notification with only a proposal and rejects missing bookings', async () => {
    proposalGet.mockResolvedValueOnce({ data: { booking_id: 41 } }).mockResolvedValueOnce({ data: {} });
    const notification = { match_id: null, proposal_id: 5 } as Notification;
    expect(await bookingForNotification(notification)).toBe(41);
    await expect(bookingForNotification(notification)).rejects.toThrow('Chưa tìm thấy booking');
  });
  it('rejects malformed IDs and ignores booking parameters on other routes', () => {
    for (const value of ['0', '-1', '1.5', '1e3', '9007199254740993', 'abc']) {
      expect(selectedBookingFromHash(`#/my-bookings?booking_id=${value}`)).toBeNull();
    }
    expect(selectedBookingFromHash('#/admin/bookings?booking_id=3')).toBeNull();
    expect(() => bookingHash(-1)).toThrow();
  });
});
