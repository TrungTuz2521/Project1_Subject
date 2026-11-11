import { api } from './client';
import { session } from '../stores/session';
import type { ApiResponse, ChangePasswordRequest, LoginData, LoginRequest, ProfileUpdate, RegisterRequest, UserSelf } from '../types/api';

/** Public endpoint: create a PLAYER account. Registration does not issue a session. */
export async function register(input: RegisterRequest): Promise<UserSelf> {
  const result = await api.request<ApiResponse<UserSelf>>('/auth/register', {
    method: 'POST', body: input, auth: false,
  });
  return result.data;
}

/** Login keeps the session in this tab (survives F5); remember=true also keeps it after the browser closes. */
export async function login(input: LoginRequest, remember = false): Promise<UserSelf> {
  const result = await api.request<ApiResponse<LoginData>>('/auth/login', {
    method: 'POST', body: input, auth: false,
  });
  session.set(result.data, remember);
  return result.data.user;
}

/** Exchanges a still-valid token for a fresh 60-minute one. */
export async function refreshSession(): Promise<void> {
  const result = await api.request<ApiResponse<LoginData>>('/auth/refresh', { method: 'POST', body: {} });
  session.set(result.data, session.remembered());
}

/**
 * While the app is open, renew the token when fewer than 15 minutes remain, so counter staff are not signed
 * out mid-shift. A closed laptop lets the token expire normally. Returns a stop function.
 */
export function keepSessionAlive(intervalMs = 60_000, marginMs = 15 * 60_000): () => void {
  let busy = false;
  const tick = () => {
    const current = session.getSnapshot();
    if (!current || busy || current.expires_at - Date.now() > marginMs) return;
    busy = true;
    refreshSession().catch(() => { /* A revoked or expired session is cleared by the API client. */ }).finally(() => { busy = false; });
  };
  const timer = setInterval(tick, intervalMs);
  const onVisible = () => { if (document.visibilityState === 'visible') tick(); };
  document.addEventListener('visibilitychange', onVisible);
  tick();
  return () => { clearInterval(timer); document.removeEventListener('visibilitychange', onVisible); };
}

export async function loginWithGoogle(credential: string, challenge: string, password?: string): Promise<UserSelf> {
  const result = await api.request<ApiResponse<LoginData>>('/auth/google', {
    method: 'POST', auth: false, body: { credential, challenge, ...(password ? { password } : {}) },
  });
  session.set(result.data);
  return result.data.user;
}

export async function googleChallenge(): Promise<{ nonce: string; challenge: string }> {
  const result = await api.request<ApiResponse<{ nonce: string; challenge: string }>>('/auth/google/challenge', {
    method: 'POST', auth: false, body: {},
  });
  return result.data;
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

export async function changePassword(input: ChangePasswordRequest): Promise<{ changed: boolean }> {
  const result = await api.request<ApiResponse<{ changed: boolean }>>('/users/me/password', { method: 'POST', body: input });
  return result.data;
}

export const logout = () => session.clear();
