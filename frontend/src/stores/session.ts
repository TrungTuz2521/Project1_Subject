import type { LoginData, UserSelf } from '../types/api';

export interface Session { access_token: string; expires_at: number; user: UserSelf }
export interface SessionStore {
  getSnapshot: () => Session | null;
  subscribe: (listener: () => void) => () => void;
  /** remember=true keeps the session after the browser is closed; otherwise only this tab keeps it (F5 is fine). */
  set: (data: LoginData, remember?: boolean) => void;
  clear: () => void;
  updateUser: (user: UserSelf) => void;
  token: () => string | null;
  remembered: () => boolean;
}
type KeyValue = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
const KEY = 'ffm.session.v1';

function browserStorage(name: 'localStorage' | 'sessionStorage'): KeyValue | null {
  try { return typeof window === 'undefined' ? null : window[name]; } catch { return null; }
}

/**
 * The access token lives for 60 minutes and is refreshed while the app is in use (services/auth keepSessionAlive).
 * It is kept in sessionStorage so reloading the page does not sign the counter out, and in localStorage only when
 * the person ticks "Ghi nhớ đăng nhập". A password change revokes every stored token on the server.
 */
export function createSessionStore(now = () => Date.now(),
  storages: { local: KeyValue | null; tab: KeyValue | null } = { local: browserStorage('localStorage'), tab: browserStorage('sessionStorage') }): SessionStore {
  let current: Session | null = null;
  let remember = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const listeners = new Set<() => void>();
  const emit = () => listeners.forEach((listener) => listener());
  const write = () => {
    const value = current ? JSON.stringify(current) : null;
    for (const [store, keep] of [[storages.tab, true], [storages.local, remember]] as const) {
      try { if (value && keep) store?.setItem(KEY, value); else store?.removeItem(KEY); } catch { /* storage full or blocked */ }
    }
  };
  const clear = () => {
    if (timer) clearTimeout(timer);
    timer = undefined;
    const had = current !== null;
    current = null; remember = false; write();
    if (had) emit();
  };
  const activate = (session: Session) => {
    if (timer) clearTimeout(timer);
    current = session;
    timer = setTimeout(clear, Math.max(0, session.expires_at - now()));
  };
  // Restore a still-valid session left by a reload (tab) or a remembered login (local).
  for (const [store, isLocal] of [[storages.tab, false], [storages.local, true]] as const) {
    if (current) break;
    try {
      const raw = store?.getItem(KEY);
      const saved = raw ? JSON.parse(raw) as Session : null;
      if (saved && typeof saved.access_token === 'string' && saved.user && saved.expires_at > now()) {
        remember = isLocal || Boolean(storages.local?.getItem(KEY));
        activate(saved);
      } else if (raw) store?.removeItem(KEY);
    } catch { try { store?.removeItem(KEY); } catch { /* ignore */ } }
  }
  return {
    getSnapshot: () => current,
    subscribe: (listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    set: (data, keep = remember) => {
      if (!data.access_token || !Number.isFinite(data.expires_in) || data.expires_in <= 0) {
        throw new Error('Phiên đăng nhập không hợp lệ.');
      }
      // expires_in comes from the server; never extend beyond the agreed 60 minutes per token.
      const ttl = Math.min(data.expires_in, 3600) * 1000;
      remember = keep;
      activate({ access_token: data.access_token, expires_at: now() + ttl, user: data.user });
      write();
      emit();
    },
    clear,
    updateUser: (user) => {
      if (!current) return;
      current = { ...current, user };
      write();
      emit();
    },
    token: () => {
      if (current && current.expires_at <= now()) clear();
      return current?.access_token ?? null;
    },
    remembered: () => remember,
  };
}
export const session = createSessionStore();
