import { useEffect, useRef, useState } from 'react';
import { googleChallenge, loginWithGoogle } from '../../services/auth';
import { errorMessage } from '../../services/api';

type IdentityAPI = { initialize: (options: { client_id: string; nonce: string; auto_select: boolean; callback: (r: { credential: string }) => void }) => void;
  renderButton: (element: HTMLElement, options: { type: string; theme: string; size: string; text: string; locale: string }) => void };
declare global { interface Window { google?: { accounts: { id: IdentityAPI } } } }
let sdk: Promise<void> | undefined;
function loadGoogle() {
  if (window.google?.accounts.id) return Promise.resolve();
  if (!sdk) sdk = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client'; script.async = true;
    script.onload = () => resolve();
    script.onerror = () => { script.remove(); sdk = undefined; reject(new Error('Không tải được Google. Kiểm tra kết nối rồi thử lại.')); };
    document.head.appendChild(script);
  });
  return sdk;
}

export function GoogleSignIn({ password, disabled, onSuccess }: { password: string; disabled: boolean; onSuccess: () => void }) {
  const container = useRef<HTMLDivElement>(null);
  const latest = useRef({ password, disabled, onSuccess });
  latest.current = { password, disabled, onSuccess };
  const working = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
  useEffect(() => {
    if (!clientId) return;
    let active = true;
    setError('');
    async function setup() {
      try {
        const [, challenge] = await Promise.all([loadGoogle(), googleChallenge()]);
        if (!active || !container.current) return;
        const google = window.google!.accounts.id;
        google.initialize({ client_id: clientId!, nonce: challenge.nonce, auto_select: false, callback: async ({ credential }) => {
          if (!active || working.current || latest.current.disabled) return;
          working.current = true; setBusy(true); setError('');
          try { await loginWithGoogle(credential, challenge.challenge, latest.current.password); if (active) latest.current.onSuccess(); }
          catch (reason) { if (active) setError(errorMessage(reason)); }
          finally { working.current = false; if (active) setBusy(false); }
        } });
        container.current.replaceChildren();
        google.renderButton(container.current, { type: 'standard', theme: 'outline', size: 'large', text: 'signin_with', locale: 'vi' });
      } catch (reason) { if (active) setError(errorMessage(reason)); }
    }
    void setup();
    // Renew the nonce before its ten-minute lifetime expires.
    const renewal = window.setTimeout(() => setAttempt(n => n + 1), 8 * 60 * 1000);
    return () => { active = false; window.clearTimeout(renewal); container.current?.replaceChildren(); };
  }, [clientId, attempt]);
  if (!clientId) return null;
  return <div style={{ marginTop: 18 }}>
    <div ref={container} aria-label="Đăng nhập bằng Google" inert={disabled || busy} style={{ opacity: disabled || busy ? 0.5 : 1 }} />
    {busy && <p role="status">Đang xác minh tài khoản Google…</p>}
    {error && <div className="notice-error" role="alert">{error} <button type="button" onClick={() => setAttempt(n => n + 1)}>Thử lại</button></div>}
  </div>;
}
