/**
 * HUY — Pitch / Booking / Admin frontend adapter.
 * API routes follow docs/api/API_MODELS_CONTRACT_PROJECT1.md v1.7.
 * Local development uses explicit, in-memory DEMO data (NOT payments).
 */
import { api } from './client';
import type {
  ApiResponse, Availability, Booking, BookingCreate, Payment, PaymentSession,
  Pitch, RevenueReport, BookingStatistics, PaginatedResponse,
} from '../types/api';

export const huyDemo = import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS !== 'false';
export type MatchOutcome = 'SOURCE_WIN' | 'OPPONENT_WIN' | 'DRAW';
export interface SettlementPayer {
  user_id: number; team_id: number | null; display_name: string; remaining_amount: string;
}
export interface Settlement {
  booking_id: number; payment_rule: string | null; outcome: MatchOutcome | null;
  version: number; total_amount: string; collected_amount: string;
  outstanding_amount: string; payers: SettlementPayer[];
}
export interface Transaction extends Payment {
  payer_name?: string; pitch_name?: string;
}
export interface TransactionList { data: Transaction[]; meta: { page: number; page_size: number; total: number; server_time: string } }
export interface ReceiptInput {
  booking_id: number; user_id: number; amount: string;
  payment_type: 'BOOKING_DEPOSIT' | 'BOOKING_REMAINING_PAYMENT';
  payment_method: 'CASH' | 'BANK_TRANSFER'; reference?: string; note?: string;
}
export interface PitchQuery { pitch_type?: string; min_price?: string; max_price?: string }
const todayVN = () => {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const get = (type: string) => parts.find(p => p.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
};
export { todayVN };
const localDate = (date: Date) => {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(date);
  const pick = (type: string) => parts.find(p => p.type === type)?.value ?? '';
  return `${pick('year')}-${pick('month')}-${pick('day')}`;
};
let serverClockOffset = 0;
export const serverNow = () => Date.now() + serverClockOffset;
function syncClock(serverTime: string) { const timestamp = Date.parse(serverTime); if (Number.isFinite(timestamp)) serverClockOffset = timestamp - Date.now(); }
export const dateVN = (d: Date | string) => new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(d));
export const timeVN = (d: Date | string) => new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' }).format(new Date(d));
export const moneyVN = (value: string) => new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 }).format(Number(value)) + ' ₫';
const integer = (s: string) => BigInt(s.split('.')[0] || '0');
const asMoney = (v: bigint) => `${v.toString()}.00`;
const dayOffset = (offset: number) => {
  const d = new Date(`${todayVN()}T00:00:00+07:00`);
  d.setUTCDate(d.getUTCDate() + offset);
  return localDate(d);
};
const isoAt = (day: string, hour: number, minute = 0) => new Date(`${day}T00:00:00+07:00`).getTime() + (hour * 60 + minute) * 60000;
const durationISO = (day: string, hour: number, minute = 0) => new Date(isoAt(day, hour, minute)).toISOString();
const endISO = (start: string) => new Date(Date.parse(start) + 90 * 60000).toISOString();
const pause = () => new Promise<void>(resolve => setTimeout(resolve, 160));
const err = (code: string, message: string) => Object.assign(new Error(message), { code });
const page = <T>(list: T[], current = 1, pageSize = 20): PaginatedResponse<T> => ({
  data: list.slice((current - 1) * pageSize, current * pageSize),
  meta: { server_time: new Date().toISOString(), page: current, page_size: pageSize, total: list.length },
});
const DEMO_PITCHES: Pitch[] = [
  { pitch_id: 1, complex_id: 1, pitch_name: 'Sân 5A', pitch_type: 'PITCH_5', price_per_slot: '300000.00', status: 'ACTIVE' },
  { pitch_id: 2, complex_id: 1, pitch_name: 'Sân 7A', pitch_type: 'PITCH_7', price_per_slot: '600000.00', status: 'ACTIVE' },
  { pitch_id: 3, complex_id: 1, pitch_name: 'Sân 7B', pitch_type: 'PITCH_7', price_per_slot: '600000.00', status: 'MAINTENANCE' },
];
let demoPitches: Pitch[] = structuredClone(DEMO_PITCHES);
let nextBookingId = 120;
let nextPaymentId = 320;
let demoBookings: Booking[] = [
  {
    booking_id: 101, pitch_id: 1, user_id: 2, start_time: durationISO(dayOffset(1), 18),
    end_time: endISO(durationISO(dayOffset(1), 18)), total_amount: '300000.00',
    deposit_amount: '60000.00', booking_type: 'ONLINE', status: 'CONFIRMED',
    hold_expires_at: null, payment_rule: 'DIRECT_BOOKING', created_at: new Date().toISOString(),
    payer_progress: [{ user_id: 2, required_amount: '60000.00', paid_amount: '60000.00', status: 'PAID' }],
  },
  {
    booking_id: 102, pitch_id: 2, user_id: 2, start_time: durationISO(dayOffset(-1), 19),
    end_time: endISO(durationISO(dayOffset(-1), 19)), total_amount: '600000.00',
    deposit_amount: '120000.00', booking_type: 'ONLINE', status: 'CONFIRMED',
    hold_expires_at: null, payment_rule: 'LOSER_PAYS_REMAINDER', created_at: new Date().toISOString(),
    payer_progress: [
      { user_id: 2, required_amount: '60000.00', paid_amount: '60000.00', status: 'PAID' },
      { user_id: 3, required_amount: '60000.00', paid_amount: '60000.00', status: 'PAID' },
    ],
  },
];
let demoTransactions: Transaction[] = [
  { payment_id: 301, booking_id: 101, post_id: null, amount: '60000.00', payment_type: 'BOOKING_DEPOSIT', payment_method: 'VNPAY', status: 'SUCCESS', transaction_code: 'DEMO-301', refund_for_payment_id: null, paid_at: new Date().toISOString(), payer_name: 'Tài khoản mẫu', pitch_name: 'Sân 5A' },
  { payment_id: 302, booking_id: 102, post_id: null, amount: '60000.00', payment_type: 'BOOKING_DEPOSIT', payment_method: 'VNPAY', status: 'SUCCESS', transaction_code: 'DEMO-302', refund_for_payment_id: null, paid_at: new Date().toISOString(), payer_name: 'FC Bình Minh', pitch_name: 'Sân 7A' },
  { payment_id: 303, booking_id: 102, post_id: null, amount: '60000.00', payment_type: 'BOOKING_DEPOSIT', payment_method: 'MOMO', status: 'SUCCESS', transaction_code: 'DEMO-303', refund_for_payment_id: null, paid_at: new Date().toISOString(), payer_name: 'FC Sao Mai', pitch_name: 'Sân 7A' },
];
let demoOutcome = new Map<number, { outcome: MatchOutcome; version: number }>();
const findPitch = (id: number) => {
  const p = demoPitches.find(p => p.pitch_id === id);
  if (!p) throw err('NOT_FOUND', 'Không tìm thấy sân.');
  return p;
};
const findBooking = (id: number) => {
  normalizeExpired();
  const b = demoBookings.find(b => b.booking_id === id);
  if (!b) throw err('NOT_FOUND', 'Không tìm thấy booking.');
  return b;
};
const isOverlap = (a: string, b: string, c: string, d: string) => Date.parse(a) < Date.parse(d) && Date.parse(b) > Date.parse(c);
const holdActive = (b: Booking) => b.status === 'PENDING_HOLD' && !!b.hold_expires_at && Date.parse(b.hold_expires_at) > Date.now();
const blocks = (b: Booking) => ['CONFIRMED', 'MAINTENANCE'].includes(b.status) || holdActive(b);
function normalizeExpired() {
  for (const b of demoBookings) {
    if (b.status === 'PENDING_HOLD' && b.hold_expires_at && Date.parse(b.hold_expires_at) <= Date.now()) {
      b.status = 'EXPIRED';
    }
  }
}
const outstanding = (b: Booking) => {
  const paid = demoTransactions.filter(t => t.booking_id === b.booking_id && t.payment_type !== 'REFUND' && t.status === 'SUCCESS')
    .reduce((sum, t) => sum + integer(t.amount), 0n);
  const refund = demoTransactions.filter(t => t.booking_id === b.booking_id && t.payment_type === 'REFUND' && t.status === 'SUCCESS')
    .reduce((sum, t) => sum + integer(t.amount), 0n);
  return { paid: paid - refund, remaining: integer(b.total_amount) - paid + refund };
};
function checkSlot(pitchId: number, start: string, end: string, exempt?: number) {
  if (demoBookings.some(b => b.booking_id !== exempt && b.pitch_id === pitchId && blocks(b) && isOverlap(b.start_time, b.end_time, start, end))) {
    throw err('SLOT_UNAVAILABLE', 'Khung giờ vừa được đặt/giữ, hãy chọn giờ khác.');
  }
}
function validateSlot(pitchId: number, start: string, end: string, exempt?: number) {
  const pitch = findPitch(pitchId);
  if (pitch.status !== 'ACTIVE') throw err('SLOT_UNAVAILABLE', 'Sân không hoạt động.');
  const st = Date.parse(start); const en = Date.parse(end);
  const min = Date.parse(`${todayVN()}T00:00:00+07:00`);
  const max = min + 11 * 86400000;
  if (!Number.isFinite(st) || en - st !== 90 * 60000 || st <= Date.now() || st >= max) throw err('VALIDATION_ERROR', 'Chỉ được đặt slot 90 phút trong 10 ngày tới.');
  const local = new Date(st + 7 * 3600000);
  const mins = local.getUTCHours() * 60 + local.getUTCMinutes();
  if (mins < 360 || mins + 90 > 1380 || mins % 30 !== 0) throw err('VALIDATION_ERROR', 'Khung giờ phải nằm trong 06:00–23:00, bước 30 phút.');
  checkSlot(pitchId, start, end, exempt);
}
function demoSettlement(id: number): Settlement {
  const b = findBooking(id);
  if (b.status !== 'CONFIRMED') throw err('STATE_CONFLICT', 'Chỉ quyết toán booking đã xác nhận.');
  if (Date.parse(b.end_time) > Date.now()) throw err('STATE_CONFLICT', 'Chỉ quyết toán sau khi trận kết thúc.');
  const outcomeState = demoOutcome.get(id);
  const rule = b.payment_rule;
  const { paid, remaining } = outstanding(b);
  const isTeam = rule === 'LOSER_PAYS_REMAINDER' || rule === 'SPLIT_EQUAL';
  const p1 = demoTransactions.filter(t => t.booking_id === id && t.payment_type !== 'REFUND' && t.status === 'SUCCESS' && t.payer_name === 'FC Bình Minh').reduce((x, p) => x + integer(p.amount), 0n);
  const p2 = demoTransactions.filter(t => t.booking_id === id && t.payment_type !== 'REFUND' && t.status === 'SUCCESS' && t.payer_name === 'FC Sao Mai').reduce((x, p) => x + integer(p.amount), 0n);
  let payers: SettlementPayer[] = [];
  if (isTeam) {
    const total = integer(b.total_amount);
    if (rule === 'SPLIT_EQUAL' || outcomeState?.outcome === 'DRAW') {
      payers = [
        { user_id: 2, team_id: 1, display_name: 'FC Bình Minh', remaining_amount: asMoney(total / 2n - p1) },
        { user_id: 3, team_id: 2, display_name: 'FC Sao Mai', remaining_amount: asMoney(total - total / 2n - p2) },
      ];
    } else if (outcomeState?.outcome === 'SOURCE_WIN') {
      payers = [
        { user_id: 2, team_id: 1, display_name: 'FC Bình Minh', remaining_amount: '0.00' },
        { user_id: 3, team_id: 2, display_name: 'FC Sao Mai', remaining_amount: asMoney(remaining) },
      ];
    } else if (outcomeState?.outcome === 'OPPONENT_WIN') {
      payers = [
        { user_id: 2, team_id: 1, display_name: 'FC Bình Minh', remaining_amount: asMoney(remaining) },
        { user_id: 3, team_id: 2, display_name: 'FC Sao Mai', remaining_amount: '0.00' },
      ];
    }
  } else {
    payers = [{ user_id: b.user_id, team_id: null, display_name: 'Người đặt sân', remaining_amount: asMoney(remaining) }];
  }
  return { booking_id: id, payment_rule: rule, outcome: outcomeState?.outcome ?? null, version: outcomeState?.version ?? 1,
    total_amount: b.total_amount, collected_amount: asMoney(paid), outstanding_amount: asMoney(remaining), payers };
}

// ---------- Public + Player APIs ----------
export async function getPitches(query: PitchQuery = {}): Promise<Pitch[]> {
  
if (!huyDemo) return (await api.request<ApiResponse<Pitch[]>>('/pitches', {
  query: {
    pitch_type: query.pitch_type,
    min_price: query.min_price,
    max_price: query.max_price,
  },
  auth: false,
})).data;

  await pause();
  return demoPitches.filter(p => (!query.pitch_type || p.pitch_type === query.pitch_type) && (!query.min_price || integer(p.price_per_slot) >= integer(query.min_price)) && (!query.max_price || integer(p.price_per_slot) <= integer(query.max_price)));
}
export async function getAvailability(pitchId: number, date: string): Promise<Availability> {
  if (!huyDemo) return (await api.request<ApiResponse<Availability>>(`/pitches/${pitchId}/availability`, { query: { date }, auth: false })).data;
  await pause(); normalizeExpired(); findPitch(pitchId);
  const slots: Availability['slots'] = [];
  for (let minutes = 360; minutes + 90 <= 1380; minutes += 30) {
    const start = new Date(isoAt(date, Math.floor(minutes / 60), minutes % 60)).toISOString();
    const end = endISO(start);
    let status: Availability['slots'][number]['status'] = 'AVAILABLE';
    if (findPitch(pitchId).status !== 'ACTIVE') status = 'MAINTENANCE';
    else if (demoBookings.some(b => b.pitch_id === pitchId && blocks(b) && isOverlap(b.start_time, b.end_time, start, end))) {
      status = demoBookings.some(b => b.pitch_id === pitchId && holdActive(b) && isOverlap(b.start_time, b.end_time, start, end)) ? 'HELD' : 'BOOKED';
    }
    if (Date.parse(start) <= Date.now() || Date.parse(start) >= Date.parse(`${todayVN()}T00:00:00+07:00`) + 11 * 86400000) status = 'BOOKED';
    slots.push({ start_time: start, end_time: end, status });
  }
  return { pitch_id: pitchId, date, slot_duration_minutes: 90, slots };
}
export async function createBooking(data: BookingCreate): Promise<Booking> {
  if (!huyDemo) { const res = await api.request<ApiResponse<Booking>>('/bookings', { method: 'POST', body: data }); syncClock(res.meta.server_time); return res.data; }
  await pause(); validateSlot(data.pitch_id, data.start_time, data.end_time);
  const pitch = findPitch(data.pitch_id);
  const deposit = integer(pitch.price_per_slot) / 5n;
  const b: Booking = { booking_id: nextBookingId++, pitch_id: data.pitch_id, user_id: 2, start_time: data.start_time, end_time: data.end_time,
    total_amount: pitch.price_per_slot, deposit_amount: asMoney(deposit), booking_type: 'ONLINE', status: 'PENDING_HOLD',
    hold_expires_at: new Date(Date.now() + 300000).toISOString(), payment_rule: 'DIRECT_BOOKING',
    payer_progress: [{ user_id: 2, required_amount: asMoney(deposit), paid_amount: '0.00', status: 'UNPAID' }], created_at: new Date().toISOString() };
  demoBookings.unshift(b); return structuredClone(b);
}
export async function getMyBookings(): Promise<Booking[]> {
  if (!huyDemo) { const res = await api.request<PaginatedResponse<Booking>>('/bookings/my', { query: { page: 1, page_size: 100 } }); syncClock(res.meta.server_time); return res.data; }
  await pause(); normalizeExpired(); return structuredClone(demoBookings.filter(b => b.user_id === 2 && b.booking_type !== 'MAINTENANCE_LOCK'));
}
export async function getBooking(id: number): Promise<Booking> {
  if (!huyDemo) { const res = await api.request<ApiResponse<Booking>>(`/bookings/${id}`); syncClock(res.meta.server_time); return res.data; }
  await pause(); return structuredClone(findBooking(id));
}
export async function cancelMyBooking(id: number, reason: string) {
  if (!huyDemo) return (await api.request<ApiResponse<Booking>>(`/bookings/${id}/cancel`, { method: 'POST', body: { reason } })).data;
  await pause(); const b = findBooking(id);
  if (b.user_id !== 2 || b.status === 'MAINTENANCE') throw err('FORBIDDEN', 'Không thể hủy booking này.');
  if (b.status !== 'PENDING_HOLD' && b.status !== 'CONFIRMED') throw err('STATE_CONFLICT', 'Booking không còn có thể hủy.');
  b.status = 'CANCELLED'; b.hold_expires_at = null; return structuredClone(b);
}
export async function createDepositSession(bookingId: number, method: 'VNPAY' | 'MOMO'): Promise<PaymentSession> {
  if (!huyDemo) return (await api.request<ApiResponse<PaymentSession>>('/payments/deposit', { method: 'POST', body: { booking_id: bookingId, payment_method: method } })).data;
  await pause(); const b = findBooking(bookingId);
  if (!holdActive(b)) throw err('HOLD_EXPIRED', 'Giữ sân đã hết hạn, cần chọn lại khung giờ.');
  // Intentionally NO real QR, payment_url or SUCCESS; this is a UI demo only.
  const pending = demoTransactions.find(p => p.booking_id === bookingId && p.payment_type === 'BOOKING_DEPOSIT' && p.status === 'PENDING');
  if (pending) return { ...pending, qr_payload: 'DEMO ONLY - NO PAYMENT', expires_at: b.hold_expires_at! };
  const data: PaymentSession = { payment_id: nextPaymentId++, booking_id: b.booking_id, post_id: null, amount: b.deposit_amount,
    payment_type: 'BOOKING_DEPOSIT', payment_method: method, status: 'PENDING',
    transaction_code: 'DEMO-NOT-PAYABLE', refund_for_payment_id: null, paid_at: null,
    qr_payload: 'DEMO ONLY - NO PAYMENT', expires_at: b.hold_expires_at! };
  demoTransactions.unshift({ ...data, payer_name: 'Người đặt sân', pitch_name: findPitch(b.pitch_id).pitch_name });
  return data;
}
// ---------- Admin APIs ----------
export async function getAdminBookings(): Promise<Booking[]> {
  if (!huyDemo) return (await api.request<PaginatedResponse<Booking>>('/admin/bookings', { query: { page: 1, page_size: 100 } })).data;
  await pause(); normalizeExpired(); return structuredClone(demoBookings);
}
export async function addAdminBooking(input: { user_id: number; pitch_id: number; start_time: string; end_time: string; note: string }): Promise<Booking> {
  if (!huyDemo) return (await api.request<ApiResponse<Booking>>('/admin/bookings', { method: 'POST', body: input })).data;
  await pause(); validateSlot(input.pitch_id, input.start_time, input.end_time);
  const pitch = findPitch(input.pitch_id); const deposit = integer(pitch.price_per_slot) / 5n;
  const b: Booking = { booking_id: nextBookingId++, pitch_id: input.pitch_id, user_id: input.user_id,
    start_time: input.start_time, end_time: input.end_time, total_amount: pitch.price_per_slot, deposit_amount: asMoney(deposit),
    booking_type: 'MANUAL_ADMIN', status: 'PENDING_HOLD', hold_expires_at: new Date(Date.now() + 300000).toISOString(),
    payment_rule: 'DIRECT_BOOKING', payer_progress: [{ user_id: input.user_id, required_amount: asMoney(deposit), paid_amount: '0.00', status: 'UNPAID' }],
    created_at: new Date().toISOString() };
  demoBookings.unshift(b); return structuredClone(b);
}
export async function moveAdminBooking(id: number, input: { pitch_id: number; start_time: string; end_time: string; reason: string }): Promise<Booking> {
  if (!huyDemo) return (await api.request<ApiResponse<Booking>>(`/admin/bookings/${id}`, { method: 'PATCH', body: input })).data;
  await pause(); const b = findBooking(id);
  if (b.status !== 'CONFIRMED' && b.status !== 'PENDING_HOLD') throw err('STATE_CONFLICT', 'Không thể đổi lịch ở trạng thái này.');
  validateSlot(input.pitch_id, input.start_time, input.end_time, b.booking_id);
  if (findPitch(b.pitch_id).price_per_slot !== findPitch(input.pitch_id).price_per_slot) throw err('PRICE_CHANGE_REQUIRES_REBOOK', 'Khác giá: cần hủy/hoàn và tạo booking mới.');
  Object.assign(b, { pitch_id: input.pitch_id, start_time: input.start_time, end_time: input.end_time }); return structuredClone(b);
}
export async function cancelAdminBooking(id: number, reason: string): Promise<Booking> {
  if (!huyDemo) return (await api.request<ApiResponse<Booking>>(`/admin/bookings/${id}/cancel`, { method: 'POST', body: { reason } })).data;
  await pause(); const b = findBooking(id);
  if (b.status === 'MAINTENANCE') throw err('STATE_CONFLICT', 'Dùng chức năng mở khóa bảo trì.');
  b.status = 'CANCELLED'; b.hold_expires_at = null; return structuredClone(b);
}
export async function createMaintenance(input: { pitch_id: number; start_time: string; end_time: string; reason: string }): Promise<Booking> {
  if (!huyDemo) return (await api.request<ApiResponse<Booking>>('/admin/maintenance-locks', { method: 'POST', body: input })).data;
  await pause(); validateSlot(input.pitch_id, input.start_time, input.end_time);
  const b: Booking = { booking_id: nextBookingId++, pitch_id: input.pitch_id, user_id: 2,
    start_time: input.start_time, end_time: input.end_time, booking_type: 'MAINTENANCE_LOCK', status: 'MAINTENANCE',
    total_amount: '0.00', deposit_amount: '0.00', payment_rule: null, hold_expires_at: null,
    payer_progress: [], created_at: new Date().toISOString() };
  demoBookings.unshift(b); return structuredClone(b);
}
export async function removeMaintenance(id: number, reason: string): Promise<Booking> {
  if (!huyDemo) return (await api.request<ApiResponse<Booking>>(`/admin/maintenance-locks/${id}/cancel`, { method: 'POST', body: { reason } })).data;
  await pause(); const b = findBooking(id);
  if (b.status !== 'MAINTENANCE') throw err('STATE_CONFLICT', 'Không phải lịch bảo trì.');
  b.status = 'CANCELLED'; return structuredClone(b);
}
export async function addPitch(input: { pitch_name: string; pitch_type: 'PITCH_5' | 'PITCH_7'; price_per_slot: string }): Promise<Pitch> {
  if (!huyDemo) return (await api.request<ApiResponse<Pitch>>('/admin/pitches', { method: 'POST', body: input })).data;
  await pause(); const p: Pitch = { ...input, complex_id: 1, pitch_id: Math.max(...demoPitches.map(p => p.pitch_id), 0) + 1, status: 'ACTIVE' };
  demoPitches.push(p); return structuredClone(p);
}
export async function changePitch(id: number, patch: { pitch_name?: string; price_per_slot?: string; status?: Pitch['status'] }): Promise<Pitch> {
  if (!huyDemo) return (await api.request<ApiResponse<Pitch>>(`/admin/pitches/${id}`, { method: 'PATCH', body: patch })).data;
  await pause(); const p = findPitch(id); Object.assign(p, patch); return structuredClone(p);
}
export async function getSettlement(id: number): Promise<Settlement> {
  if (!huyDemo) return (await api.request<ApiResponse<Settlement>>(`/admin/bookings/${id}/settlement`)).data;
  await pause(); return demoSettlement(id);
}
export async function setSettlementResult(id: number, outcome: MatchOutcome, expectedVersion: number): Promise<Settlement> {
  if (!huyDemo) return (await api.request<ApiResponse<Settlement>>(`/admin/bookings/${id}/settlement/result`, { method: 'PATCH', body: { outcome, expected_version: expectedVersion } })).data;
  await pause(); const b = findBooking(id); const s = demoSettlement(id);
  if (b.payment_rule !== 'LOSER_PAYS_REMAINDER') throw err('VALIDATION_ERROR', 'Booking này không cần chốt kết quả.');
  if (Date.parse(b.end_time) > Date.now()) throw err('STATE_CONFLICT', 'Trận chưa kết thúc.');
  if (s.version !== expectedVersion) throw err('STATE_CONFLICT', 'Thông tin đã đổi; hãy tải lại.');
  if (demoTransactions.some(t => t.booking_id === id && t.payment_type === 'BOOKING_REMAINING_PAYMENT')) throw err('STATE_CONFLICT', 'Đã tạo giao dịch quyết toán; không thể đổi kết quả.');
  demoOutcome.set(id, { outcome, version: s.version + 1 }); return demoSettlement(id);
}
export async function createSettlementSession(id: number, payerId: number, method: 'VNPAY' | 'MOMO', expectedVersion: number): Promise<PaymentSession> {
  if (!huyDemo) return (await api.request<ApiResponse<PaymentSession>>(`/admin/bookings/${id}/settlement/payment-sessions`, { method: 'POST', body: { payer_user_id: payerId, payment_method: method, expected_version: expectedVersion } })).data;
  await pause(); const s = demoSettlement(id);
  if (s.version !== expectedVersion) throw err('STATE_CONFLICT', 'Phiên quyết toán đã thay đổi.');
  const payer = s.payers.find(p => p.user_id === payerId);
  if (!payer || integer(payer.remaining_amount) <= 0n) throw err('VALIDATION_ERROR', 'Không có khoản cần thu.');
  if (s.payment_rule === 'LOSER_PAYS_REMAINDER' && !s.outcome) throw err('STATE_CONFLICT', 'Cần chốt kết quả trước khi tạo mã thanh toán.');
  const pending = demoTransactions.find(p => p.booking_id === id && p.payment_type === 'BOOKING_REMAINING_PAYMENT' && p.status === 'PENDING' && (p as Transaction & { payer_id?: number }).payer_id === payerId);
  if (pending) return { ...pending, qr_payload: 'DEMO ONLY - NO PAYMENT', expires_at: new Date(Date.now() + 300000).toISOString() };
  const data: PaymentSession = { payment_id: nextPaymentId++, booking_id: id, post_id: null, amount: payer.remaining_amount,
    payment_type: 'BOOKING_REMAINING_PAYMENT', payment_method: method, status: 'PENDING',
    transaction_code: 'DEMO-NOT-PAYABLE', refund_for_payment_id: null, paid_at: null,
    qr_payload: 'DEMO ONLY - NO PAYMENT', expires_at: new Date(Date.now() + 300000).toISOString() };
  demoTransactions.unshift({ ...data, payer_name: payer.display_name, pitch_name: findPitch(findBooking(id).pitch_id).pitch_name, payer_id: payerId } as Transaction & { payer_id: number });
  return data;
}
export async function recordCash(input: ReceiptInput): Promise<Payment> {
  if (!huyDemo) return (await api.request<ApiResponse<Payment>>('/admin/payments/record', { method: 'POST', body: input })).data;
  await pause();
  if (!['CASH', 'BANK_TRANSFER'].includes(input.payment_method)) throw err('VALIDATION_ERROR', 'Chỉ hỗ trợ tiền mặt/chuyển khoản tại quầy.');
  const b = findBooking(input.booking_id);
  if (b.status !== 'CONFIRMED' && b.status !== 'PENDING_HOLD') throw err('STATE_CONFLICT', 'Booking không thể ghi thu.');
  if (integer(input.amount) <= 0n) throw err('VALIDATION_ERROR', 'Số tiền phải lớn hơn 0.');
  if (input.payment_type === 'BOOKING_REMAINING_PAYMENT' && demoTransactions.some(t => t.booking_id === b.booking_id && t.payment_type === 'BOOKING_REMAINING_PAYMENT' && t.status === 'PENDING')) {
    throw err('STATE_CONFLICT', 'Đã có phiên QR chưa đối soát; không thể thu thêm trong demo để tránh trùng.');
  }
  const s = b.status === 'CONFIRMED' ? demoSettlement(b.booking_id) : null;
  const payer = s?.payers.find(p => p.user_id === input.user_id);
  if (input.payment_type === 'BOOKING_REMAINING_PAYMENT' && (!payer || (s?.payment_rule === 'LOSER_PAYS_REMAINDER' && !s.outcome) || integer(input.amount) > integer(payer.remaining_amount))) {
    throw err('VALIDATION_ERROR', 'Khoản thu không khớp kế hoạch quyết toán.');
  }
  const t: Transaction = { payment_id: nextPaymentId++, booking_id: b.booking_id, post_id: null,
    amount: input.amount, payment_type: input.payment_type, payment_method: input.payment_method,
    status: 'SUCCESS', transaction_code: `DEMO-CASH-${nextPaymentId}`, refund_for_payment_id: null,
    paid_at: new Date().toISOString(), payer_name: payer?.display_name ?? 'Người đặt sân', pitch_name: findPitch(b.pitch_id).pitch_name };
  demoTransactions.unshift(t);
  // Demo status is NOT a real gateway or persisted backend payment.
  if (b.status === 'PENDING_HOLD' && input.payment_type === 'BOOKING_DEPOSIT' && integer(input.amount) >= integer(b.deposit_amount)) {
    b.status = 'CONFIRMED'; b.hold_expires_at = null;
    b.payer_progress = [{ user_id: input.user_id, required_amount: b.deposit_amount, paid_amount: input.amount, status: 'PAID' }];
  }
  return structuredClone(t);
}
export async function getTransactions(from?: string, to?: string): Promise<TransactionList> {
  if (!huyDemo) return await api.request<TransactionList>('/admin/transactions', { query: { page: 1, page_size: 100, from, to } });
  await pause();
  const data = demoTransactions.filter(t => {
    if (!t.paid_at) return true; // show pending for reconciliation
    const d = localDate(new Date(t.paid_at));
    return (!from || d >= from) && (!to || d <= to);
  });
  return page(structuredClone(data)) as TransactionList;
}
export async function getRevenue(from: string, to: string, period: 'day' | 'month' | 'year'): Promise<RevenueReport> {
  if (!huyDemo) return (await api.request<ApiResponse<RevenueReport>>('/admin/revenue', { query: { from, to, period } })).data;
  await pause();
  const groups = new Map<string, { gross_receipts: bigint; refunds: bigint }>();
  for (const p of demoTransactions) {
    if (p.status !== 'SUCCESS' || !p.paid_at) continue;
    const day = localDate(new Date(p.paid_at));
    if (day < from || day > to) continue;
    const group = period === 'day' ? day : period === 'month' ? day.slice(0, 7) : day.slice(0, 4);
    const v = groups.get(group) ?? { gross_receipts: 0n, refunds: 0n };
    if (p.payment_type === 'REFUND') v.refunds += integer(p.amount); else v.gross_receipts += integer(p.amount);
    groups.set(group, v);
  }
  const items = [...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([period_start, v]) => ({
    period_start, gross_receipts: asMoney(v.gross_receipts), refunds: asMoney(v.refunds), net_receipts: asMoney(v.gross_receipts - v.refunds),
  }));
  const totals = items.reduce((v, item) => ({
    gross_receipts: asMoney(integer(v.gross_receipts) + integer(item.gross_receipts)),
    refunds: asMoney(integer(v.refunds) + integer(item.refunds)),
    net_receipts: asMoney(integer(v.net_receipts) + integer(item.net_receipts)),
  }), { gross_receipts: '0.00', refunds: '0.00', net_receipts: '0.00' });
  return { currency: 'VND', period, from, to, time_zone: 'Asia/Ho_Chi_Minh', items, totals };
}
export async function getBookingStatistics(from: string, to: string): Promise<BookingStatistics> {
  if (!huyDemo) return (await api.request<ApiResponse<BookingStatistics>>('/admin/booking-statistics', { query: { from, to } })).data;
  await pause();
  const bookings = demoBookings.filter(b => b.booking_type !== 'MAINTENANCE_LOCK' && localDate(new Date(b.start_time)) >= from && localDate(new Date(b.start_time)) <= to);
  return { total_bookings: bookings.length, confirmed_bookings: bookings.filter(b => b.status === 'CONFIRMED').length,
    cancelled_bookings: bookings.filter(b => b.status === 'CANCELLED').length, expired_bookings: bookings.filter(b => b.status === 'EXPIRED').length,
    refunded_booking_count: 0, by_pitch: [], peak_hours: [] };
}
