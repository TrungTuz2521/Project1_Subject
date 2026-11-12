/**
 * Pitches, bookings and the Admin's counter, money and reports.
 * Routes follow docs/api/API_MODELS_CONTRACT_PROJECT1.md.
 */
import { api } from './client';
import type {
  ApiResponse, Availability, Booking, BookingCreate, Payment,
  Pitch, RevenueReport, BookingStatistics, PaginatedResponse, BookingBalance, ConfirmBookingPaid, AdminBooking,
  PendingRefund, AdminUser, AdminBookingQuery, AdminDashboard, WalkInGuest, PeakHours, SeriesResult, CancelCause, ArrivalStatus,
} from '../types/api';

export interface Transaction extends Payment { payer_name?: string; pitch_name?: string }
export interface TransactionList { data: Transaction[]; meta: { page: number; page_size: number; total: number; server_time: string } }

// ---------- Time and money in Vietnam time ----------
export const todayVN = () => {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const get = (type: string) => parts.find(p => p.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
};
let serverClockOffset = 0;
/** The server's clock, so hold countdowns are right even when the device clock is off. */
export const serverNow = () => Date.now() + serverClockOffset;
export function syncClock(serverTime: string) { const timestamp = Date.parse(serverTime); if (Number.isFinite(timestamp)) serverClockOffset = timestamp - Date.now(); }
export const dateVN = (d: Date | string) => new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(d));
export const timeVN = (d: Date | string) => new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' }).format(new Date(d));
export const moneyVN = (value: string) => new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 }).format(Number(value)) + ' ₫'; // No-break space: the sign never wraps away from its amount.

// ---------- Public + Player ----------
export async function getPitches(query: { pitch_type?: string; min_price?: string; max_price?: string } = {}): Promise<Pitch[]> {
  return (await api.request<ApiResponse<Pitch[]>>('/pitches', { query, auth: false })).data;
}
export async function getAvailability(pitchId: number, date: string): Promise<Availability> {
  return (await api.request<ApiResponse<Availability>>(`/pitches/${pitchId}/availability`, { query: { date }, auth: false })).data;
}
export async function createBooking(data: BookingCreate): Promise<Booking> {
  const res = await api.request<ApiResponse<Booking>>('/bookings', { method: 'POST', body: data });
  syncClock(res.meta.server_time);
  return res.data;
}
export async function getMyBookings(): Promise<Booking[]> {
  const res = await api.request<PaginatedResponse<Booking>>('/bookings/my', { query: { page: 1, page_size: 100 } });
  syncClock(res.meta.server_time);
  return res.data;
}
export async function getBooking(id: number): Promise<Booking> {
  const res = await api.request<ApiResponse<Booking>>(`/bookings/${id}`);
  syncClock(res.meta.server_time);
  return res.data;
}
export async function cancelMyBooking(id: number, reason: string): Promise<Booking> {
  return (await api.request<ApiResponse<Booking>>(`/bookings/${id}/cancel`, { method: 'POST', body: { reason } })).data;
}

// ---------- Admin: counter bookings ----------
/** Money taken at the counter when booking; the rest is collected after the match. */
interface CounterPayment { amount: string; payment_method: 'CASH' | 'BANK_TRANSFER'; reference?: string }
export async function addAdminBooking(input: { pitch_id: number; start_time: string; end_time: string; note: string; payment?: CounterPayment; repeat_weeks?: number } & ({ user_id: number } | { guest: WalkInGuest })): Promise<Booking & { series?: SeriesResult }> {
  return (await api.request<ApiResponse<Booking & { series?: SeriesResult }>>('/admin/bookings', { method: 'POST', body: input })).data;
}
export async function moveAdminBooking(id: number, input: { pitch_id: number; start_time: string; end_time: string; reason: string }): Promise<Booking> {
  return (await api.request<ApiResponse<Booking>>(`/admin/bookings/${id}`, { method: 'PATCH', body: input })).data;
}
type CancelResult = Booking & { refund_summary?: { refund_amount: string; forfeited_amount: string } };
export async function cancelAdminBooking(id: number, reason: string, cause: CancelCause = 'VENUE'): Promise<CancelResult> {
  return (await api.request<ApiResponse<CancelResult>>(`/admin/bookings/${id}/cancel`, { method: 'POST', body: { reason, cause } })).data;
}
/** Stops a regular customer's weekly slot: every future session of the series. */
export async function cancelSeries(seriesId: string, reason: string, cause: CancelCause): Promise<{ cancelled: number[]; refund_amount: string; forfeited_amount: string }> {
  return (await api.request<ApiResponse<{ cancelled: number[]; refund_amount: string; forfeited_amount: string }>>(`/admin/bookings/series/${encodeURIComponent(seriesId)}/cancel`, { method: 'POST', body: { reason, cause } })).data;
}
/** Counter check-in: ARRIVED, NO_SHOW, or null to undo. */
export async function markArrival(bookingId: number, status: ArrivalStatus | null): Promise<AdminBooking> {
  return (await api.request<ApiResponse<AdminBooking>>(`/admin/bookings/${bookingId}/arrival`, { method: 'POST', body: { status } })).data;
}
/** Server-side filtered, paginated admin booking list. */
export async function getAdminBookingsPage(query: AdminBookingQuery = {}): Promise<PaginatedResponse<AdminBooking>> {
  const { page = 1, page_size = 20, ...filters } = query;
  return api.request<PaginatedResponse<AdminBooking>>('/admin/bookings', { query: { page, page_size, ...filters } });
}
/** Customer lookup for counter bookings (name, email or phone). */
export async function searchUsers(q: string, signal?: AbortSignal): Promise<AdminUser[]> {
  return (await api.request<PaginatedResponse<AdminUser>>('/admin/users', { query: { q, role: 'PLAYER', page: 1, page_size: 10 }, signal })).data;
}
export async function getAdminDashboard(): Promise<AdminDashboard> {
  return (await api.request<ApiResponse<AdminDashboard>>('/admin/dashboard')).data;
}

// ---------- Admin: pitches, maintenance, peak hours ----------
export async function createMaintenance(input: { pitch_id: number; start_time: string; end_time: string; reason: string }): Promise<Booking> {
  return (await api.request<ApiResponse<Booking>>('/admin/maintenance-locks', { method: 'POST', body: input })).data;
}
export async function removeMaintenance(id: number, reason: string): Promise<Booking> {
  return (await api.request<ApiResponse<Booking>>(`/admin/maintenance-locks/${id}/cancel`, { method: 'POST', body: { reason } })).data;
}
export async function addPitch(input: { pitch_name: string; pitch_type: 'PITCH_5' | 'PITCH_7'; price_per_slot: string; peak_price_per_slot?: string | null }): Promise<Pitch> {
  return (await api.request<ApiResponse<Pitch>>('/admin/pitches', { method: 'POST', body: input })).data;
}
export async function changePitch(id: number, patch: { pitch_name?: string; price_per_slot?: string; peak_price_per_slot?: string | null; status?: Pitch['status']; confirm?: boolean }): Promise<Pitch> {
  return (await api.request<ApiResponse<Pitch>>(`/admin/pitches/${id}`, { method: 'PATCH', body: patch })).data;
}
/** Peak window of the complex (null start/end = no daily peak). */
export async function getPeakHours(): Promise<PeakHours> {
  const policy = (await api.request<ApiResponse<{ policy: PeakHours }>>('/field-complex', { auth: false })).data.policy;
  return { peak_start_time: policy.peak_start_time, peak_end_time: policy.peak_end_time, weekend_is_peak: policy.weekend_is_peak };
}
export async function setPeakHours(input: PeakHours): Promise<PeakHours> {
  return (await api.request<ApiResponse<PeakHours>>('/admin/field-complex', { method: 'PATCH', body: input })).data;
}

// ---------- Admin: money ----------
export async function getBookingBalance(id: number): Promise<BookingBalance> {
  return (await api.request<ApiResponse<BookingBalance>>(`/admin/bookings/${id}/balance`)).data;
}
export async function confirmBookingPaid(id: number, input: ConfirmBookingPaid): Promise<BookingBalance> {
  return (await api.request<ApiResponse<BookingBalance>>(`/admin/bookings/${id}/confirm-paid`, { method: 'POST', body: input })).data;
}
export async function getPendingRefunds(): Promise<PendingRefund[]> {
  return (await api.request<PaginatedResponse<PendingRefund>>('/admin/refunds/pending', { query: { page: 1, page_size: 100 } })).data;
}
/** Confirms the Admin has handed the money back; takes the ORIGINAL payment id. */
export async function completeManualRefund(originalPaymentId: number, reason: string): Promise<Payment> {
  return (await api.request<ApiResponse<Payment>>(`/admin/payments/${originalPaymentId}/refund`, { method: 'POST', body: { reason } })).data;
}
export async function getTransactions(from?: string, to?: string, page = 1, pageSize = 20): Promise<TransactionList> {
  return api.request<TransactionList>('/admin/transactions', { query: { page, page_size: pageSize, from, to } });
}

// ---------- Admin: reports ----------
export async function getRevenue(from: string, to: string, period: 'day' | 'month' | 'year'): Promise<RevenueReport> {
  return (await api.request<ApiResponse<RevenueReport>>('/admin/revenue', { query: { from, to, period } })).data;
}
export async function getBookingStatistics(from: string, to: string): Promise<BookingStatistics> {
  return (await api.request<ApiResponse<BookingStatistics>>('/admin/booking-statistics', { query: { from, to } })).data;
}
/** Downloads the revenue workbook and saves it through the browser. */
export async function exportRevenue(from: string, to: string, period: 'day' | 'month' | 'year'): Promise<void> {
  const { blob, filename } = await api.download('/admin/revenue/export', { from, to, period });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = filename === 'download' ? `doanh-thu-${from}-${to}.xlsx` : filename;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
