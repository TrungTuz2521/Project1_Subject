import { api } from './client';
import { syncClock } from './huyApi';
import type { ApiResponse, DemoDepositResult, BankDepositInstructions } from '../types/api';

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
