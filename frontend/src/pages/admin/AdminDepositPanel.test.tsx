import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AdminDepositPanel } from './AdminDepositPanel';
import type { AdminBooking } from '../../types/api';

const booking = (patch: Partial<AdminBooking> = {}): AdminBooking => ({
  booking_id: 7, pitch_id: 1, user_id: 2, start_time: '2030-01-01T11:00:00Z', end_time: '2030-01-01T12:30:00Z',
  total_amount: '600000.00', deposit_amount: '120000.00', booking_type: 'MANUAL_ADMIN', status: 'PENDING_HOLD',
  payment_rule: 'DIRECT_BOOKING', created_at: '2030-01-01T00:00:00Z', hold_expires_at: new Date(Date.now() + 200_000).toISOString(),
  payer_progress: [{ user_id: 2, required_amount: '120000.00', paid_amount: '20000.00', status: 'PARTIAL' }], ...patch,
} as AdminBooking);

it('pre-fills the remaining share and needs a receipt reference', () => {
  const html = renderToStaticMarkup(<AdminDepositPanel booking={booking()} onDone={() => {}} onClose={() => {}} />);
  expect(html).toContain('value="100000"');
  expect(html).toContain('Tiền mặt tại quầy');
  expect(html).toContain('Mã chứng từ');
});

it('refuses once the hold has expired', () => {
  const html = renderToStaticMarkup(<AdminDepositPanel booking={booking({ hold_expires_at: new Date(Date.now() - 1000).toISOString() })} onDone={() => {}} onClose={() => {}} />);
  expect(html).toContain('Đã hết hạn giữ sân');
  expect(html).not.toContain('Ghi nhận cọc</button>');
});
