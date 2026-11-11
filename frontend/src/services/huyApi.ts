/**
 * HUY — Pitch / Booking / Admin frontend adapter.
 * API routes follow docs/api/API_MODELS_CONTRACT_PROJECT1.md booking-wide balance/confirm-paid contract.
 * Local development uses explicit, in-memory DEMO data (NOT payments).
 */
import { api, useMocks } from './client';
import type {
  ApiResponse, Availability, Booking, BookingCreate, Payment, PaymentSession,
  Pitch, RevenueReport, BookingStatistics, PaginatedResponse, BookingBalance, ConfirmBookingPaid, AdminBooking, BookingPhase,
  PendingRefund, ManualDepositInput,
} from '../types/api';

export const huyDemo = useMocks;
export interface Transaction extends Payment {
  payer_name?: string; pitch_name?: string;
}
export interface TransactionList { data: Transaction[]; meta: { page: number; page_size: number; total: number; server_time: string } }
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
export function syncClock(serverTime: string) { const timestamp = Date.parse(serverTime); if (Number.isFinite(timestamp)) serverClockOffset = timestamp - Date.now(); }
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
const demoReceipts = new Map<string, { payload: string; balance: BookingBalance }>();
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
  const paid = demoTransactions.filter(t => t.booking_id === b.booking_id && t.payment_type !== 'REFUND' && ['SUCCESS', 'REFUNDED'].includes(t.status))
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
function demoBalance(id: number): BookingBalance {
  const b = findBooking(id);
  const { paid, remaining } = outstanding(b);
  const gross = (kind: string) => demoTransactions.filter(t => t.booking_id === id && t.payment_type === kind && ['SUCCESS', 'REFUNDED'].includes(t.status)).reduce((sum, t) => sum + integer(t.amount), 0n);
  return { booking_id: id, payment_rule: b.payment_rule, total_amount: b.total_amount,
    deposit_collected_amount: asMoney(gross('BOOKING_DEPOSIT')), remaining_collected_amount: asMoney(gross('BOOKING_REMAINING_PAYMENT')),
    collected_amount: asMoney(paid), outstanding_amount: asMoney(remaining > 0n ? remaining : 0n),
    payment_status: remaining <= 0n ? 'PAID' : paid > 0n ? 'PARTIAL' : 'UNPAID',
    qr_payload: null, transfer_reference: null, qr_unavailable_reason: 'Chế độ demo không tạo QR chuyển tiền.' };
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
export async function getAdminBookings(phase?: BookingPhase): Promise<AdminBooking[]> {
  if (!huyDemo) return (await api.request<PaginatedResponse<AdminBooking>>('/admin/bookings', { query: { page: 1, page_size: 100, phase } })).data;
  await pause(); normalizeExpired();
  const rows = demoBookings.map(b => ({ ...structuredClone(b), balance: b.booking_type === 'MAINTENANCE_LOCK' ? null : demoBalance(b.booking_id) }));
  return rows.filter(b => !phase || (b.status === 'CONFIRMED' && (
    phase === 'UPCOMING' ? Date.parse(b.start_time) > Date.now() :
    phase === 'IN_PROGRESS' ? Date.parse(b.start_time) <= Date.now() && Date.now() < Date.parse(b.end_time) :
    phase === 'ENDED_UNPAID' ? Date.parse(b.end_time) <= Date.now() && b.balance?.payment_status !== 'PAID' : b.balance?.payment_status === 'PAID')));
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
export async function getBookingBalance(id: number): Promise<BookingBalance> {
  if (!huyDemo) return (await api.request<ApiResponse<BookingBalance>>(`/admin/bookings/${id}/balance`)).data;
  await pause(); return demoBalance(id);
}
export async function confirmBookingPaid(id: number, input: ConfirmBookingPaid): Promise<BookingBalance> {
  if (!huyDemo) return (await api.request<ApiResponse<BookingBalance>>(`/admin/bookings/${id}/confirm-paid`, { method: 'POST', body: input })).data;
  await pause();
  const key = `${id}:${input.idempotency_key}`;
  const previous = demoReceipts.get(key);
  if (previous) {
    if (previous.payload !== JSON.stringify(input)) throw err('STATE_CONFLICT', 'Mã xác nhận đã dùng cho nội dung khác.');
    return structuredClone(previous.balance);
  }
  const b = findBooking(id), balance = demoBalance(id);
  if (b.status !== 'CONFIRMED' || Date.parse(b.end_time) > Date.now()) throw err('STATE_CONFLICT', 'Chỉ thu đủ sau giờ kết thúc của booking đã xác nhận.');
  if (integer(balance.outstanding_amount) <= 0n || integer(input.expected_outstanding) !== integer(balance.outstanding_amount)) throw err('STATE_CONFLICT', 'Số dư đã thay đổi. Hãy tải lại.');
  if (!input.receipts.length || input.receipts.some(r => !/^[1-9]\d*(?:\.00)?$/.test(r.amount) || !['CASH', 'BANK_TRANSFER'].includes(r.payment_method)) || input.receipts.reduce((sum, r) => sum + integer(r.amount), 0n) !== integer(balance.outstanding_amount)) throw err('VALIDATION_ERROR', 'Tổng khoản thực nhận phải bằng số còn thiếu.');
  input.receipts.forEach((r, index) => demoTransactions.unshift({ payment_id: nextPaymentId++, booking_id: id, post_id: null, amount: r.amount,
    payment_type: 'BOOKING_REMAINING_PAYMENT', payment_method: r.payment_method, status: 'SUCCESS',
    transaction_code: `DEMO-${key}-${index}`, refund_for_payment_id: null, paid_at: new Date().toISOString() }));
  const result = demoBalance(id);
  demoReceipts.set(key, { payload: JSON.stringify(input), balance: structuredClone(result) });
  return result;
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

/** Admin refund queue. DEMO data has no real money, so there is nothing to hand back. */
export async function getPendingRefunds(): Promise<PendingRefund[]> {
  if (huyDemo) return [];
  return (await api.request<PaginatedResponse<PendingRefund>>('/admin/refunds/pending', { query: { page: 1, page_size: 100 } })).data;
}
/** Confirms the Admin has handed the money back; takes the ORIGINAL payment id. */
export async function completeManualRefund(originalPaymentId: number, reason: string): Promise<Payment> {
  if (huyDemo) throw new Error('Chế độ demo không có khoản hoàn thật.');
  return (await api.request<ApiResponse<Payment>>(`/admin/payments/${originalPaymentId}/refund`, { method: 'POST', body: { reason } })).data;
}
/** Records a real deposit the Admin has received; the server checks the due share and the hold. */
export async function recordManualDeposit(input: ManualDepositInput): Promise<Payment> {
  if (huyDemo) throw new Error('Chế độ demo không ghi nhận tiền thật.');
  return (await api.request<ApiResponse<Payment>>('/admin/payments/record', { method: 'POST', body: input })).data;
}
