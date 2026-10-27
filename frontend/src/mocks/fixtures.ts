import type { Booking, MatchPost, Notification, Payment, Pitch, ProposalDetail, RevenueReport, Team, UserSelf } from '../types/api';

/** Synthetic fixtures. Never copy production credentials or personal data here. */
export const demoUser: UserSelf = { user_id: 2, full_name: 'Đức · Tài khoản mẫu', email: 'demo@example.test',
  phone: null, role: 'PLAYER', skill_level: 'INTERMEDIATE', status: 'ACTIVE' };
export const initialTeams: Team[] = [
  { team_id: 1, team_name: 'FC Bình Minh', created_by: 2, creation_type: 'USER_CREATED', status: 'ACTIVE', active_member_count: 7 },
  { team_id: 2, team_name: 'Những người bạn', created_by: 2, creation_type: 'USER_CREATED', status: 'ACTIVE', active_member_count: 5 },
  { team_id: 3, team_name: 'Đội chiều thứ Bảy', created_by: 2, creation_type: 'AI_RANDOM', status: 'ACTIVE', active_member_count: 4 },
];
export const pitches: Pitch[] = [
  { pitch_id: 1, complex_id: 1, pitch_name: 'Sân 5A', pitch_type: 'PITCH_5', price_per_slot: '300000.00', status: 'ACTIVE' },
  { pitch_id: 2, complex_id: 1, pitch_name: 'Sân 7A', pitch_type: 'PITCH_7', price_per_slot: '600000.00', status: 'ACTIVE' },
  { pitch_id: 3, complex_id: 1, pitch_name: 'Sân 7B', pitch_type: 'PITCH_7', price_per_slot: '600000.00', status: 'MAINTENANCE' },
];
export function createFixtures(now = Date.now()) {
  // Next local day at 19:00 Vietnam time, independent of the machine timezone.
  const day = new Date(now + 7 * 3600000).toISOString().slice(0, 10);
  const tomorrow = new Date(`${day}T00:00:00+07:00`).getTime() + 86400000;
  const start = new Date(tomorrow + 19 * 3600000).toISOString();
  const end = new Date(Date.parse(start) + 90 * 60000).toISOString();
  const created = new Date(now).toISOString();
  const posts: MatchPost[] = [{ post_id: 1, title: 'FC Bình Minh tìm đối thủ sân 7', description: 'Giao hữu, chia đều tiền sân.',
    post_type: 'FIND_OPPONENT', team_id: 1, pitch_id: 2, pitch_type: 'PITCH_7', match_time: start,
    end_time: end, skill_level: 'INTERMEDIATE', payment_rule: 'SPLIT_EQUAL', required_players: null,
    current_players: 7, expiry_time: new Date(Date.parse(start) - 2 * 3600000).toISOString(), status: 'OPEN', matching_ready: true }];
  const booking: Booking = { booking_id: 21, pitch_id: 2, user_id: 2, start_time: start, end_time: end,
    total_amount: '600000.00', deposit_amount: '120000.00', booking_type: 'ONLINE', status: 'PENDING_HOLD',
    hold_expires_at: new Date(now + 300000).toISOString(), payment_rule: 'SPLIT_EQUAL', created_at: created,
    payer_progress: [{ user_id: 2, required_amount: '60000.00', paid_amount: '0.00', status: 'UNPAID' },
      { user_id: 3, required_amount: '60000.00', paid_amount: '0.00', status: 'UNPAID' }] };
  const payment: Payment = { payment_id: 31, booking_id: 21, post_id: 1, amount: '60000.00',
    payment_type: 'BOOKING_DEPOSIT', payment_method: 'VNPAY', status: 'PENDING', transaction_code: 'DEMO-ONLY-31',
    refund_for_payment_id: null, paid_at: null };
  const proposal: ProposalDetail = { proposal_id: 11, source_post_id: 1, target_post_id: 2, candidate_user_id: null,
    proposal_type: 'OPPONENT', compatibility_score: '100.00', status: 'PENDING_CONFIRMATION',
    expires_at: new Date(now + 900000).toISOString(), confirmed_at: null,
    confirmations: [{ user_id: 2, decision: 'PENDING', responded_at: null }, { user_id: 3, decision: 'PENDING', responded_at: null }] };
  const notifications: Notification[] = [{ notification_id: 1, notification_type: 'MATCH_PROPOSAL', title: 'Có đối thủ phù hợp',
    content: 'Dữ liệu minh họa để xây dựng giao diện.', is_read: false, created_at: created, read_at: null, proposal_id: 11, match_id: null }];
  const revenue: RevenueReport = { currency: 'VND', period: 'day', from: day, to: day, time_zone: 'Asia/Ho_Chi_Minh',
    items: [{ period_start: day, gross_receipts: '120000.00', refunds: '0.00', net_receipts: '120000.00' }],
    totals: { gross_receipts: '120000.00', refunds: '0.00', net_receipts: '120000.00' } };
  return { posts, booking, payment, proposal, notifications, revenue };
}
