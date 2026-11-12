import { api } from './client';
import { syncClock } from './fieldApi';
import type { ApiResponse, DemoDepositResult, BankDepositInstructions, Payment, QrPaymentSession } from '../types/api';

export async function getDepositInstructions(bookingId: number, signal?: AbortSignal) {
  const result = await api.request<ApiResponse<BankDepositInstructions>>(`/bookings/${bookingId}/deposit-instructions`, { signal });
  syncClock(result.meta.server_time);
  return result.data;
}

export async function confirmDemoDeposit(bookingId: number) {
  const result = await api.request<ApiResponse<DemoDepositResult>>('/payments/deposit/demo-confirm', {
    method: 'POST', body: { booking_id: bookingId },
  });
  syncClock(result.meta.server_time);
  return result.data;
}

/** Opens (or reuses while still shown) the payer's 60-second QR code. Amount and content come from the server. */
export async function openQrPayment(bookingId: number) {
  const result = await api.request<ApiResponse<QrPaymentSession>>('/payments/deposit/qr', {
    method: 'POST', body: { booking_id: bookingId },
  });
  syncClock(result.meta.server_time);
  return result.data;
}

/** Read-only status poll; only the bank webhook on the server can turn it into SUCCESS. */
export async function getPaymentStatus(paymentId: number, signal?: AbortSignal) {
  const result = await api.request<ApiResponse<Payment>>(`/payments/${paymentId}`, { signal });
  syncClock(result.meta.server_time);
  return result.data;
}
