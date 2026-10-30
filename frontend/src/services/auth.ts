import { api } from './client';
import { session } from '../stores/session';
import type { ApiResponse, LoginData, LoginRequest, ProfileUpdate, RegisterRequest, UserSelf } from '../types/api';

/** Public endpoint: create a PLAYER account. Registration does not issue a session. */
export async function register(input: RegisterRequest): Promise<UserSelf> {
  const result = await api.request<ApiResponse<UserSelf>>('/auth/register', {
    method: 'POST', body: input, auth: false,
  });
  return result.data;
}

/** Login stores the short-lived access token in memory only. */
export async function login(input: LoginRequest): Promise<UserSelf> {
  const result = await api.request<ApiResponse<LoginData>>('/auth/login', {
    method: 'POST', body: input, auth: false,
  });
  session.set(result.data);
  return result.data.user;
}

export async function getCurrentUser(signal?: AbortSignal): Promise<UserSelf> {
  const result = await api.request<ApiResponse<UserSelf>>('/users/me', { signal });
  return result.data;
}

export async function updateCurrentUser(input: ProfileUpdate): Promise<UserSelf> {
  const result = await api.request<ApiResponse<UserSelf>>('/users/me', { method: 'PATCH', body: input });
  // Keep the in-memory session's public user data in sync without changing the token expiry.
  const current = session.getSnapshot();
  if (current) session.updateUser(result.data);
  return result.data;
}

export const logout = () => session.clear();
