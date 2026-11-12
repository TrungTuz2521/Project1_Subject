import { describe, expect, it } from 'vitest';
import { bookingHash, selectedBookingFromHash } from './bookingNavigation';
describe('booking links', () => {
  it('round-trips a booking id through the hash', () => {
    expect(selectedBookingFromHash(bookingHash(30002))).toBe(30002);
  });
  it('rejects malformed IDs and ignores booking parameters on other routes', () => {
    for (const value of ['0', '-1', '1.5', '1e3', '9007199254740993', 'abc']) {
      expect(selectedBookingFromHash(`#/my-bookings?booking_id=${value}`)).toBeNull();
    }
    expect(selectedBookingFromHash('#/admin/bookings?booking_id=3')).toBeNull();
    expect(() => bookingHash(-1)).toThrow();
  });
});
