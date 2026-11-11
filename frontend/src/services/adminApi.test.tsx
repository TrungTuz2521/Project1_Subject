import { afterEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
const { request, download } = vi.hoisted(() => ({ request: vi.fn(), download: vi.fn() }));
vi.mock('./client', () => ({ useMocks: false, api: { request, download } }));
import { getAdminBookingsPage, getTransactions, searchUsers, exportRevenue } from './huyApi';
import { createApiClient } from './api';
import { createSessionStore } from '../stores/session';
import { demoUser } from '../mocks/fixtures';
import { CustomerPicker } from '../pages/admin/CustomerPicker';
import { Pager } from '../pages/admin/Pager';

const meta = { server_time: new Date().toISOString(), page: 1, page_size: 20, total: 0 };
afterEach(() => { request.mockReset(); download.mockReset(); });

it('filters, dates and pages admin bookings on the server', async () => {
  request.mockResolvedValueOnce({ data: [], meta });
  await getAdminBookingsPage({ phase: 'ENDED_UNPAID', status: 'CONFIRMED', from: '2026-11-01', to: '2026-11-30', page: 3, page_size: 20 });
  expect(request).toHaveBeenCalledWith('/admin/bookings', { query: { page: 3, page_size: 20, phase: 'ENDED_UNPAID', status: 'CONFIRMED', from: '2026-11-01', to: '2026-11-30' } });
  request.mockResolvedValueOnce({ data: [], meta });
  await getTransactions('2026-11-01', '2026-11-30', 2, 20);
  expect(request).toHaveBeenLastCalledWith('/admin/transactions', { query: { page: 2, page_size: 20, from: '2026-11-01', to: '2026-11-30' } });
});

it('searches players only and exports through an authenticated download', async () => {
  request.mockResolvedValueOnce({ data: [{ user_id: 5 }], meta });
  expect(await searchUsers('0912')).toEqual([{ user_id: 5 }]);
  expect(request).toHaveBeenCalledWith('/admin/users', { query: { q: '0912', role: 'PLAYER', page: 1, page_size: 10 }, signal: undefined });
  download.mockResolvedValueOnce({ blob: new Blob(['x']), filename: 'doanh-thu.xlsx' });
  const create = vi.fn(() => ({ href: '', download: '', click: vi.fn(), remove: vi.fn() }));
  vi.stubGlobal('document', { createElement: create, body: { appendChild: vi.fn() } });
  vi.stubGlobal('URL', { createObjectURL: () => 'blob:1', revokeObjectURL: vi.fn() });
  await exportRevenue('2026-11-01', '2026-11-30', 'month');
  expect(download).toHaveBeenCalledWith('/admin/revenue/export', { from: '2026-11-01', to: '2026-11-30', period: 'month' });
  vi.unstubAllGlobals();
});

it('download sends the bearer token and reads the file name', async () => {
  const store = createSessionStore(); store.set({ access_token: 'tok', expires_in: 3600, user: demoUser });
  const transport = vi.fn(async () => new Response('xlsx', { headers: { 'Content-Disposition': 'attachment; filename=doanh-thu-2026.xlsx' } }));
  const result = await createApiClient({ baseUrl: '/api/v1', store, transport }).download('/admin/revenue/export', { from: 'a' });
  const [url, init] = transport.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe('/api/v1/admin/revenue/export?from=a');
  expect(new Headers(init.headers).get('Authorization')).toBe('Bearer tok');
  expect(result.filename).toBe('doanh-thu-2026.xlsx');
  store.clear();
});

it('shows the picked customer and a pager only when needed', () => {
  const picked = renderToStaticMarkup(<CustomerPicker value={{ user_id: 5, full_name: 'Nguyễn Văn An', email: 'an@x.vn', phone: '0912', role: 'PLAYER', status: 'ACTIVE' }} onChange={() => {}} />);
  expect(picked).toContain('Nguyễn Văn An'); expect(picked).toContain('Đổi khách');
  expect(renderToStaticMarkup(<CustomerPicker value={null} onChange={() => {}} />)).toContain('tìm theo tên, email hoặc SĐT');
  expect(renderToStaticMarkup(<Pager page={1} pageSize={20} total={5} onPage={() => {}} />)).toContain('5 kết quả');
  const pager = renderToStaticMarkup(<Pager page={2} pageSize={20} total={45} onPage={() => {}} />);
  expect(pager).toContain('21–40 / 45'); expect(pager).toContain('Trang 2/3');
});

it('books a walk-in with only a name and phone, or an account by id', async () => {
  const { addAdminBooking } = await import('./huyApi');
  request.mockResolvedValue({ data: { booking_id: 1 }, meta });
  const slot = { pitch_id: 1, start_time: 'a', end_time: 'b', note: 'Tại quầy' };
  await addAdminBooking({ ...slot, guest: { full_name: 'Anh Minh', phone: '0912345678' } });
  expect(request).toHaveBeenLastCalledWith('/admin/bookings', { method: 'POST', body: { ...slot, guest: { full_name: 'Anh Minh', phone: '0912345678' } } });
  await addAdminBooking({ ...slot, user_id: 7 });
  expect(request).toHaveBeenLastCalledWith('/admin/bookings', { method: 'POST', body: { ...slot, user_id: 7 } });
});

it('error banner lists what is wrong per field', async () => {
  const { Warning } = await import('../features/field-management/ui');
  const { ApiError } = await import('./api');
  const html = renderToStaticMarkup(<Warning error={new ApiError(409, 'PHONE_BELONGS_TO_ACCOUNT', 'Số điện thoại đã có tài khoản.',
    { 'guest.phone': 'Số này thuộc tài khoản An (an@x.vn).', reason: 'Trường bắt buộc.' })} />);
  expect(html).toContain('Số này thuộc tài khoản An (an@x.vn).');
  expect(html).toContain('Lý do: Trường bắt buộc.');
});
