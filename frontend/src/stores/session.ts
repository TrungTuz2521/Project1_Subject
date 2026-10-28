import type { LoginData, UserSelf } from '../types/api';

export interface Session { access_token: string; expires_at: number; user: UserSelf }
export interface SessionStore {
  getSnapshot: () => Session | null;
  subscribe: (listener: () => void) => () => void;
  set: (data: LoginData) => void;
  clear: () => void;
  updateUser: (user: UserSelf) => void;
  token: () => string | null;
}
/** In-memory only: reload requires login again. No JWT in localStorage. */
export function createSessionStore(now = () => Date.now()): SessionStore {
  let current: Session | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const listeners = new Set<() => void>();
  const emit = () => listeners.forEach((listener) => listener());
  const clear = () => {
    if (timer) clearTimeout(timer);
    timer = undefined;
    if (current) { current = null; emit(); }
  };
  return {
    getSnapshot: () => current,
    subscribe: (listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    set: (data) => {
      if (!data.access_token || !Number.isFinite(data.expires_in) || data.expires_in <= 0) {
        throw new Error('Phiên đăng nhập không hợp lệ.');
      }
      if (timer) clearTimeout(timer);
      // expires_in comes from the server; never extend beyond the agreed 60 minutes.
      const ttl = Math.min(data.expires_in, 3600) * 1000;
      current = { access_token: data.access_token, expires_at: now() + ttl, user: data.user };
      timer = setTimeout(clear, ttl);
      emit();
    },
    clear,
    updateUser: (user) => {
      if (!current) return;
      current = { ...current, user };
      emit();
    },
    token: () => {
      if (current && current.expires_at <= now()) clear();
      return current?.access_token ?? null;
    },
  };
}
export const session = createSessionStore();
