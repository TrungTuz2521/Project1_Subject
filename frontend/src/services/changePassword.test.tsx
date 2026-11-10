import { afterEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('./client', () => ({ api: { request } }));
import { changePassword } from './auth';
import { ChangePasswordForm } from '../features/auth/ChangePasswordForm';
afterEach(() => request.mockReset());

it('renders current and confirmed new password fields, but Google-only accounts get Google guidance', () => {
  const form = renderToStaticMarkup(<ChangePasswordForm hasPassword onSuccess={vi.fn()} />);
  expect(form).toContain('password-current');expect(form).toContain('password-confirm');
  expect(form).toContain('current-password');expect(form).toContain('new-password');
  const google = renderToStaticMarkup(<ChangePasswordForm hasPassword={false} onSuccess={vi.fn()} />);
  expect(google).toContain('myaccount.google.com/security');expect(google).not.toContain('<input');
});

it('calls the authenticated own-password endpoint and propagates failures', async () => {
  const input = {current_password:'old-password',new_password:'new-password',confirm_password:'new-password'};
  request.mockResolvedValueOnce({data:{changed:true}});
  expect(await changePassword(input)).toEqual({changed:true});
  expect(request).toHaveBeenCalledWith('/users/me/password',{method:'POST',body:input});
  request.mockRejectedValueOnce(new Error('current password incorrect'));
  await expect(changePassword(input)).rejects.toThrow('current password incorrect');
});
