import { useState } from 'react';
import type { FormEvent } from 'react';
import { changePassword } from '../../services/auth';
import { formErrorMessage as errorMessage } from '../../services/formErrors';

export function ChangePasswordForm({ hasPassword, onSuccess }: { hasPassword: boolean; onSuccess: () => void }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return; setError('');
    if (!current) { setError('Nhập mật khẩu hiện tại.'); return; }
    const bytes = new TextEncoder().encode(next).length;
    if (bytes < 8 || bytes > 72) { setError('Mật khẩu mới phải dài 8–72 byte UTF-8.'); return; }
    if (next !== confirm) { setError('Mật khẩu nhập lại chưa khớp.'); return; }
    if (next === current) { setError('Mật khẩu mới phải khác mật khẩu hiện tại.'); return; }
    setBusy(true);
    try {
      await changePassword({ current_password: current, new_password: next, confirm_password: confirm });
      setCurrent(''); setNext(''); setConfirm(''); onSuccess();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <section className="profile-form-card" style={{ marginTop: 24 }}>
    <div className="profile-form-heading"><div><h2>Đổi mật khẩu</h2><p>Đổi mật khẩu đăng nhập web. Sau khi thành công, hãy đăng nhập lại.</p></div></div>
    {!hasPassword ? <p>Tài khoản này đăng nhập bằng Google và chưa có mật khẩu web. Bạn tiếp tục dùng nút Google; để đổi mật khẩu Google, mở <a href="https://myaccount.google.com/security" target="_blank" rel="noreferrer">Bảo mật tài khoản Google</a>.</p> :
      <form className="profile-form" onSubmit={submit} noValidate>
        <div className="form-field"><label htmlFor="password-current">Mật khẩu hiện tại</label><input id="password-current" type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} disabled={busy} required /></div>
        <div className="form-field"><label htmlFor="password-new">Mật khẩu mới</label><input id="password-new" type="password" autoComplete="new-password" value={next} onChange={e => setNext(e.target.value)} disabled={busy} required /><small className="input-caption">Từ 8 đến 72 byte UTF-8; ký tự tiếng Việt có thể chiếm nhiều byte.</small></div>
        <div className="form-field"><label htmlFor="password-confirm">Nhập lại mật khẩu mới</label><input id="password-confirm" type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} disabled={busy} required /></div>
        {error && <div className="notice-error" role="alert">{error}</div>}
        <div className="profile-actions"><button className="account-primary-button" type="submit" disabled={busy}>{busy ? 'Đang đổi…' : 'Đổi mật khẩu'}</button></div>
      </form>}
  </section>;
}
