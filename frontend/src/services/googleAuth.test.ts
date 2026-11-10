import { afterEach, expect, it, vi } from 'vitest';
import { session } from '../stores/session';
import { demoUser } from '../mocks/fixtures';
const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('./client', () => ({ api: { request } }));
import { googleChallenge, loginWithGoogle } from './auth';
afterEach(() => { session.clear(); request.mockReset(); });
it('uses public JSON endpoints and only stores the app session after successful verification', async () => {
  request.mockResolvedValueOnce({ data: { nonce: 'n', challenge: 'signed' } });
  expect(await googleChallenge()).toEqual({ nonce: 'n', challenge: 'signed' });
  expect(request).toHaveBeenLastCalledWith('/auth/google/challenge', { method: 'POST', auth: false, body: {} });
  request.mockRejectedValueOnce(new Error('link required'));
  await expect(loginWithGoogle('id-token', 'signed')).rejects.toThrow('link required');
  expect(session.getSnapshot()).toBeNull();
  request.mockResolvedValueOnce({ data: { access_token: 'app-token', expires_in: 3600, user: demoUser } });
  expect(await loginWithGoogle('id-token', 'signed', 'web-password')).toEqual(demoUser);
  expect(request).toHaveBeenLastCalledWith('/auth/google', { method: 'POST', auth: false,
    body: { credential: 'id-token', challenge: 'signed', password: 'web-password' } });
  expect(session.getSnapshot()?.access_token).toBe('app-token');
});
