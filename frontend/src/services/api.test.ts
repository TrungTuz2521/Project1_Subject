import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, createApiClient } from './api';
import { createSessionStore } from '../stores/session';
import { demoUser } from '../mocks/fixtures';
import { createMockServer } from '../mocks/server';

const stores: ReturnType<typeof createSessionStore>[] = [];
const makeStore = () => { const store = createSessionStore(); stores.push(store); return store; };
const loginStore = (store: ReturnType<typeof createSessionStore>, token = 'test-token') => store.set({ access_token: token, expires_in: 3600, user: demoUser });
afterEach(() => { stores.forEach((store) => store.clear()); stores.length = 0; vi.useRealTimers(); });

describe('API client session and error boundaries', () => {
  it('sends query/body and bearer only to relative API paths', async () => {
    const store = makeStore(); loginStore(store);
    const transport = vi.fn(async () => new Response(JSON.stringify({ data: {}, meta: { server_time: new Date().toISOString() } })));
    const api = createApiClient({ baseUrl: 'http://localhost:5000/api/v1/', store, transport });
    await api.request('/teams', { method: 'POST', query: { my: true, page: 1, omit: undefined }, body: { team_name: 'FC Mẫu' } });
    const [url, init] = transport.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('http://localhost:5000/api/v1/teams?my=true&page=1');
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer test-token');
    expect(JSON.parse(String(init.body))).toEqual({ team_name: 'FC Mẫu' });
    await expect(api.request('//another-host/teams')).rejects.toMatchObject({ code: 'INVALID_PATH' });
    expect(transport).toHaveBeenCalledTimes(1);
  });
  it('does not call the transport for expired local sessions', async () => {
    vi.useFakeTimers();
    const store = makeStore(); loginStore(store);
    const transport = vi.fn();
    const api = createApiClient({ baseUrl: '/api/v1', store, transport });
    vi.advanceTimersByTime(3600000);
    await expect(api.request('/teams')).rejects.toMatchObject({ status: 401 });
    expect(store.getSnapshot()).toBeNull(); expect(transport).not.toHaveBeenCalled();
  });
  it('never attaches bearer tokens to public login calls', async () => {
    const store = makeStore(); loginStore(store);
    const transport = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      expect(new Headers(init?.headers).has('Authorization')).toBe(false);
      return new Response(JSON.stringify({ data: {}, meta: {} }));
    });
    await createApiClient({ baseUrl: '/api/v1', store, transport }).request('/auth/login', { auth: false });
  });
  it('preserves field errors for a 422 without logging out', async () => {
    const store = makeStore(); loginStore(store);
    const api = createApiClient({ baseUrl: '/api/v1', store, transport: async () => new Response(JSON.stringify({
      error: { code: 'VALIDATION_ERROR', message: 'Sai dữ liệu', fields: { team_name: ['Tên bắt buộc'] } },
    }), { status: 422 }) });
    await expect(api.request('/teams')).rejects.toMatchObject({ status: 422, fields: { team_name: ['Tên bắt buộc'] } });
    expect(store.getSnapshot()).not.toBeNull();
  });
  it('clears a rejected session even if a 401 response is HTML', async () => {
    const store = makeStore(); loginStore(store);
    const api = createApiClient({ baseUrl: '/api/v1', store, transport: async () => new Response('<html>Unauthorized</html>', { status: 401 }) });
    await expect(api.request('/teams')).rejects.toBeInstanceOf(ApiError);
    expect(store.getSnapshot()).toBeNull();
  });
  it('does not clear a new session when an old request returns 401 late', async () => {
    const store = makeStore(); loginStore(store, 'old');
    let respond!: (value: Response) => void;
    const transport = () => new Promise<Response>((resolve) => { respond = resolve; });
    const request = createApiClient({ baseUrl: '/api/v1', store, transport }).request('/teams');
    loginStore(store, 'new');
    respond(new Response(JSON.stringify({ error: { code: 'TOKEN_EXPIRED', message: 'Expired' } }), { status: 401 }));
    await expect(request).rejects.toMatchObject({ status: 401 });
    expect(store.token()).toBe('new');
  });
  it('distinguishes a caller abort from timeout and connectivity errors', async () => {
    const transport = (_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      const abort = () => reject(new DOMException('Aborted', 'AbortError'));
      if (init?.signal?.aborted) abort(); else init?.signal?.addEventListener('abort', abort, { once: true });
    });
    const api = createApiClient({ baseUrl: '/api/v1', transport });
    const controller = new AbortController();
    const cancelled = api.request('/pitches', { auth: false, signal: controller.signal });
    controller.abort();
    await expect(cancelled).rejects.toMatchObject({ name: 'AbortError' });
    await expect(api.request('/pitches', { auth: false, timeoutMs: 5 })).rejects.toMatchObject({ code: 'TIMEOUT' });
    const offline = createApiClient({ baseUrl: '/api/v1', transport: async () => { throw new TypeError('offline'); } });
    await expect(offline.request('/pitches', { auth: false })).rejects.toMatchObject({ code: 'NETWORK_ERROR' });
  });
});

it('mock supports login → load → create → reload and rejects expired sessions', async () => {
  const store = makeStore();
  const mock = createMockServer(0);
  const api = createApiClient({ baseUrl: '/api/v1', store, transport: mock.transport });
  const result = await api.request<{ data: { access_token: string; expires_in: number; user: typeof demoUser } }>('/auth/login', { auth: false, method: 'POST', body: {} });
  store.set(result.data);
  const first = await api.request<{ data: unknown[]; meta: { total: number } }>('/teams');
  expect(first.meta.total).toBe(3);
  await api.request('/teams', { method: 'POST', body: { team_name: 'FC Kiểm Thử' } });
  const next = await api.request<{ data: { team_name: string }[]; meta: { total: number } }>('/teams');
  expect(next.meta.total).toBe(4); expect(next.data[0].team_name).toBe('FC Kiểm Thử');
  await expect(api.request('/teams', { method: 'POST', body: { team_name: '' } })).rejects.toMatchObject({ status: 422 });
  mock.expireSession();
  await expect(api.request('/teams')).rejects.toMatchObject({ status: 401 });
  expect(store.getSnapshot()).toBeNull();
});
