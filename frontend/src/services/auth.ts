import { api } from './client';
import { session } from '../stores/session';
import type { ApiResponse, LoginData, LoginRequest } from '../types/api';

export async function login(input: LoginRequest) {
  const result = await api.request<ApiResponse<LoginData>>('/auth/login', { method: 'POST', body: input, auth: false });
  session.set(result.data);
  return result.data.user;
}
export const logout = () => session.clear();
