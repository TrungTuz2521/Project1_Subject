import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { session } from '../stores/session';
import type { BookingBalance, ConfirmBookingPaid, UserSelf } from '../types/api';

const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('./client', () => ({ api: { request } }));
import { confirmBookingPaid, getBookingBalance, getAdminBookingsPage } from './fieldApi';
import App from '../App';

const balance: BookingBalance = { booking_id: 21, payment_rule: 'LOSER_PAYS_REMAINDER',
  total_amount: '600000.00', deposit_collected_amount: '120000.00', remaining_collected_amount: '0.00',
  collected_amount: '120000.00', outstanding_amount: '480000.00', payment_status: 'PARTIAL',
  qr_payload: null, transfer_reference: 'BOOKING-21', qr_unavailable_reason: 'Chưa cấu hình ngân hàng' };
const envelope = (data: unknown) => ({ data, meta: { server_time: '2026-11-02T06:00:00Z' } });
function signedIn(role: 'ADMIN' | 'PLAYER') {
  session.set({ access_token: 'test-only-token', expires_in: 3600,
    user: { user_id: 2, full_name: 'Người kiểm thử', role, email: 'test@example.test', status: 'ACTIVE' } as UserSelf });
}
beforeEach(() => { request.mockReset(); vi.stubGlobal('window', { location: { hash: '#/bookings' } }); });
afterEach(() => { session.clear(); vi.unstubAllGlobals(); });

describe('field pages and the booking money contract', () => {
  it('reads one booking-wide balance and sends mixed receipts without outcome or payer allocation', async () => {
    request.mockResolvedValueOnce(envelope(balance));
    expect(await getBookingBalance(21)).toEqual(balance);
    expect(request).toHaveBeenLastCalledWith('/admin/bookings/21/balance');
    const body: ConfirmBookingPaid = { expected_outstanding: '480000.00', idempotency_key: 'stable-retry-key', receipts: [
      { payment_method: 'CASH', amount: '180000.00' },
      { payment_method: 'BANK_TRANSFER', amount: '300000.00', reference: 'receipt-1' },
    ] };
    const paid = { ...balance, payment_status: 'PAID', outstanding_amount: '0.00' };
    request.mockResolvedValueOnce(envelope(paid));
    expect(await confirmBookingPaid(21, body)).toEqual(paid);
    expect(request).toHaveBeenLastCalledWith('/admin/bookings/21/confirm-paid', { method: 'POST', body });
  });
  it('passes server-side booking phase for the paid/unpaid admin lists', async () => {
    request.mockResolvedValue(envelope([]));
    await getAdminBookingsPage({ phase: 'ENDED_UNPAID' });
    expect(request).toHaveBeenCalledWith('/admin/bookings', { query: { page: 1, page_size: 20, phase: 'ENDED_UNPAID' } });
  });
  it('blocks a direct admin URL for players and does not call admin APIs', () => {
    signedIn('PLAYER'); window.location.hash = '#/admin/balance';
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain('Bạn không có quyền truy cập');
    expect(html).not.toContain('href="#/admin/revenue"');
    expect(request).not.toHaveBeenCalled();
  });
  it('requires login on direct field URLs and exposes real field pages in the shared shell', () => {
    // Visitors can browse pitches and free slots; booking asks them to sign in.
    window.location.hash = '#/bookings';
    const visitor = renderToStaticMarkup(<App />);
    expect(visitor).toContain('Đăng nhập để đặt');
    window.location.hash = '#/my-bookings';
    expect(renderToStaticMarkup(<App />)).toContain('Đăng nhập');
    signedIn('PLAYER'); window.location.hash = '#/bookings';
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain('Giữ sân và đặt cọc');
    expect(html).toContain('player-tabbar');
    expect(html).toContain('href="#/my-bookings"');
    expect(html).not.toContain('ĐANG CHỜ TÍCH HỢP');
    signedIn('ADMIN'); window.location.hash = '#/admin/balance';
    const admin = renderToStaticMarkup(<App />);
    expect(admin).toContain('Cần thu');
    expect(admin).toContain('href="#/admin/revenue"');
    expect(admin).not.toContain('Chọn kết quả');
  });
});
