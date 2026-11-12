import { describe, expect, it } from 'vitest';
import { createSessionStore } from './session';
import { demoUser } from '../services/testUser';

const memory = () => { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => { m.set(k, v); }, removeItem: (k: string) => { m.delete(k); }, size: () => m.size }; };
const login = { access_token: 'tok', expires_in: 3600, user: demoUser };

describe('session persistence', () => {
  it('survives a reload in the same tab, but not a closed browser, unless remembered', () => {
    const local = memory(), tab = memory();
    createSessionStore(() => 1000, { local, tab }).set(login);
    expect(createSessionStore(() => 2000, { local, tab }).token()).toBe('tok');      // F5
    expect(createSessionStore(() => 2000, { local, tab: memory() }).token()).toBeNull(); // new browser session
    createSessionStore(() => 1000, { local, tab }).set(login, true);
    const reopened = createSessionStore(() => 2000, { local, tab: memory() });
    expect(reopened.token()).toBe('tok');
    expect(reopened.remembered()).toBe(true);
  });

  it('drops an expired stored token and clears both stores on logout', () => {
    const local = memory(), tab = memory();
    const store = createSessionStore(() => 0, { local, tab });
    store.set(login, true);
    expect(createSessionStore(() => 3_600_001, { local, tab }).token()).toBeNull();
    store.set(login, true);
    store.clear();
    expect(local.size() + tab.size()).toBe(0);
  });

  it('a refresh keeps the remember choice', () => {
    const local = memory(), tab = memory();
    const store = createSessionStore(() => 0, { local, tab });
    store.set(login, true);
    store.set({ ...login, access_token: 'tok2' });
    expect(store.remembered()).toBe(true);
    expect(createSessionStore(() => 10, { local, tab: memory() }).token()).toBe('tok2');
  });
});
