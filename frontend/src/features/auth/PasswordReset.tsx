import { useState } from 'react';
import type { FormEvent } from 'react';
import { requestPasswordReset, resetPassword } from '../../services/auth';
import { ApiError, errorMessage } from '../../services/api';

const fieldError = (error: unknown, field: string) => {
  if (!(error instanceof ApiError)) return '';
  const value = error.fields[field];
  return Array.isArray(value) ? value.join(' ') : value ?? '';
};

function ResetCard({ title, lead, children }: { title: string; lead: string; children: React.ReactNode }) {
  return <main className="reset-screen">
    <div className="auth-card reset-card">
      <div className="auth-card-title"><span className="auth-icon" aria-hidden="true">⟲</span><div><h2>{title}</h2><p>{lead}</p></div></div>
      {children}
      <p className="auth-switch"><a href="#/login">Quay lại đăng nhập</a></p>
    </div>
  </main>;
}

/** Step 1: the email. The answer is the same whether or not an account exists. */
export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('');
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) { setError('Nhập email bạn đã dùng để đăng ký.'); return; }
    setBusy(true);
    try { setSent((await requestPasswordReset(email.trim())).message); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <ResetCard title="Quên mật khẩu" lead="Nhập email tài khoản, chúng tôi gửi link để đặt mật khẩu mới.">
    {sent ? <div className="notice-success" role="status">{sent} Link có hiệu lực 30 phút; nhớ xem cả thư mục Spam.</div>
      : <form className="auth-form" onSubmit={submit} noValidate>
        {error && <div className="notice-error" role="alert">{error}</div>}
        <div className="form-field"><label htmlFor="forgot-email">Email <span>*</span></label>
          <input id="forgot-email" type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="ban@example.com" /></div>
        <button className="auth-submit" type="submit" disabled={busy}>{busy ? 'Đang gửi…' : 'Gửi link đặt lại'}<span aria-hidden="true">↗</span></button>
      </form>}
  </ResetCard>;
}

/** Step 2: the link from the email (#/reset-password?token=…). */
export function ResetPasswordPage({ onDone }: { onDone: (message: string) => void }) {
  const token = new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('token') ?? '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setErrors({});
    if (password.length < 8) { setErrors({ new_password: 'Mật khẩu mới tối thiểu 8 ký tự.' }); return; }
    if (password !== confirm) { setErrors({ confirm_password: 'Mật khẩu nhập lại chưa khớp.' }); return; }
    setBusy(true);
    try { await resetPassword(token, password, confirm); onDone('Đã đặt mật khẩu mới. Hãy đăng nhập lại bằng mật khẩu này.'); }
    catch (reason) {
      setError(errorMessage(reason));
      setErrors(Object.fromEntries(['new_password', 'confirm_password'].map(n => [n, fieldError(reason, n)]).filter(([, v]) => v)));
    } finally { setBusy(false); }
  }
  if (!token) return <ResetCard title="Link không hợp lệ" lead="Link đặt lại mật khẩu thiếu mã xác thực.">
    <p className="auth-switch"><a href="#/forgot-password">Gửi lại link đặt mật khẩu</a></p></ResetCard>;
  return <ResetCard title="Đặt mật khẩu mới" lead="Mật khẩu mới thay mật khẩu cũ và đăng xuất các máy đang đăng nhập.">
    <form className="auth-form" onSubmit={submit} noValidate>
      {error && <div className="notice-error" role="alert">{error}{error.includes('hết hạn') && <> <a href="#/forgot-password">Gửi lại link</a></>}</div>}
      <div className="form-field"><label htmlFor="reset-password">Mật khẩu mới <span>*</span></label>
        <input id="reset-password" type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} aria-invalid={!!errors.new_password} />
        {errors.new_password && <small className="field-error">{errors.new_password}</small>}</div>
      <div className="form-field"><label htmlFor="reset-confirm">Nhập lại mật khẩu mới <span>*</span></label>
        <input id="reset-confirm" type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} aria-invalid={!!errors.confirm_password} />
        {errors.confirm_password && <small className="field-error">{errors.confirm_password}</small>}</div>
      <button className="auth-submit" type="submit" disabled={busy}>{busy ? 'Đang lưu…' : 'Lưu mật khẩu mới'}<span aria-hidden="true">↗</span></button>
    </form>
  </ResetCard>;
}
