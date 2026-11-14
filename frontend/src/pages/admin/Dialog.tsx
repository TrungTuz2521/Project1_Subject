import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Button, Warning } from '../../features/field-management/ui';

/** Accessible modal: Esc and the backdrop close it, focus moves into it, page behind is inert. */
export function Dialog({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    box.current?.querySelector<HTMLElement>('input,textarea,select,button')?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); previous?.focus?.(); };
  }, [onClose]);
  return <div className="adm-dialog-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
    <div ref={box} className={`adm-dialog${wide ? ' is-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
      <div className="adm-dialog-head"><h2>{title}</h2><button type="button" className="adm-dialog-x" aria-label="Đóng" onClick={onClose}>×</button></div>
      {children}
    </div>
  </div>;
}

export interface Choice<T extends string> { value: T; label: string; detail?: ReactNode; tone?: 'danger' | 'default' }

/** Ask for a reason (and optionally one of a few choices) before an action that cannot be undone. */
export function ReasonDialog<T extends string>({ title, message, reasonLabel = 'Lý do', placeholder, choices, initialChoice, confirmLabel, danger = false, onConfirm, onClose }: {
  title: string; message?: ReactNode; reasonLabel?: string; placeholder?: string;
  choices?: Choice<T>[]; initialChoice?: T; confirmLabel: (choice: T | undefined) => string; danger?: boolean;
  onConfirm: (reason: string, choice: T | undefined) => Promise<void>; onClose: () => void;
}) {
  const [reason, setReason] = useState('');
  const [choice, setChoice] = useState<T | undefined>(initialChoice ?? choices?.[0]?.value);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!reason.trim() || busy) return;
    setBusy(true); setError(null);
    try { await onConfirm(reason.trim().slice(0, 200), choice); onClose(); }
    catch (err) { setError(err); setBusy(false); }
  }
  return <Dialog title={title} onClose={busy ? () => {} : onClose}>
    <form className="adm-dialog-body" onSubmit={e => void submit(e)}>
      {message && <div className="adm-dialog-message">{message}</div>}
      {choices && <div className="adm-choice-cards" role="radiogroup">
        {choices.map(c => <button key={c.value} type="button" role="radio" aria-checked={choice === c.value}
          className={`${choice === c.value ? 'is-on' : ''}${c.tone === 'danger' ? ' is-danger' : ''}`} onClick={() => setChoice(c.value)}>
          <strong>{c.label}</strong>{c.detail && <small>{c.detail}</small>}</button>)}
      </div>}
      <label className="huy-field"><span>{reasonLabel}</span>
        <textarea rows={2} maxLength={200} required value={reason} onChange={e => setReason(e.target.value)} placeholder={placeholder} /></label>
      <Warning error={error} />
      <div className="adm-dialog-actions">
        <Button variant="outline" onClick={onClose} disabled={busy}>Quay lại</Button>
        <Button type="submit" variant={danger ? 'danger' : 'primary'} disabled={busy || !reason.trim()}>{busy ? 'Đang xử lý…' : confirmLabel(choice)}</Button>
      </div>
    </form>
  </Dialog>;
}
