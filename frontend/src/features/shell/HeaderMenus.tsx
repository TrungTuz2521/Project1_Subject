import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import '../../styles/header-menus.css';

/** Header pieces shared by the player and admin shells: a bell with a count, and the account menu. */

export const badgeText = (n: number) => (n > 99 ? '99+' : String(n));

const BellIcon = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
  <path d="M6 9a6 6 0 1112 0c0 5 2 6.5 2 6.5H4S6 14 6 9M10 19a2 2 0 004 0" /></svg>;

/** Open/close state for a header popover: closes on outside click, Escape (focus back to the trigger) and navigation. */
function usePopover() {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { setOpen(false); trigger.current?.focus(); } };
    const navigate = () => setOpen(false);
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', key);
    window.addEventListener('hashchange', navigate);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', key);
      window.removeEventListener('hashchange', navigate);
    };
  }, [open]);
  return { open, setOpen, root, trigger };
}

/** A bell that is a plain link (player: goes to the notifications page). */
export function BellLink({ href, count, active, label }: { href: string; count: number; active?: boolean; label: string }) {
  const full = count ? `${label}, ${count} chưa đọc` : label;
  return <a className={active ? 'hm-bell is-active' : 'hm-bell'} href={href} aria-label={full} title={full} aria-current={active ? 'page' : undefined}>
    <BellIcon />{count > 0 && <span className="hm-badge" aria-hidden="true">{badgeText(count)}</span>}
  </a>;
}

export type BellItem = { href: string; text: string; count: number; tone: 'amber' | 'red' };

/** A bell that opens a short list of things waiting (admin: work to do, each linking to its page). */
export function BellMenu({ items, label, empty }: { items: BellItem[]; label: string; empty: string }) {
  const { open, setOpen, root, trigger } = usePopover();
  const waiting = items.filter(i => i.count > 0);
  const total = waiting.reduce((sum, i) => sum + i.count, 0);
  const full = total ? `${label}, ${total} việc` : label;
  return <div className="hm-wrap" ref={root}>
    <button ref={trigger} type="button" className={open ? 'hm-bell is-active' : 'hm-bell'} aria-label={full} title={full} aria-expanded={open} aria-haspopup="true" onClick={() => setOpen(o => !o)}>
      <BellIcon />{total > 0 && <span className="hm-badge" aria-hidden="true">{badgeText(total)}</span>}
    </button>
    {open && <div className="hm-panel hm-panel-wide" role="menu">
      <p className="hm-panel-title">{label}</p>
      {waiting.length === 0 ? <p className="hm-empty">{empty}</p>
        : waiting.map(i => <a key={i.text} role="menuitem" className="hm-item" href={i.href}>
            <span className={`hm-dot ${i.tone}`} aria-hidden="true" /><span>{i.text}</span><strong>{badgeText(i.count)}</strong></a>)}
    </div>}
  </div>;
}

/** Avatar + name; the menu holds Profile and Log out so logging out is never a stray click. */
export function AccountMenu({ name, avatar, profileHref, onLogout, extra }: { name: string; avatar: string; profileHref: string; onLogout: () => void; extra?: ReactNode }) {
  const { open, setOpen, root, trigger } = usePopover();
  return <div className="hm-wrap" ref={root}>
    <button ref={trigger} type="button" className={open ? 'hm-account is-open' : 'hm-account'} aria-expanded={open} aria-haspopup="true" onClick={() => setOpen(o => !o)}>
      <span className="hm-avatar" aria-hidden="true">{avatar}</span>
      <span className="hm-name">{name}</span>
      <svg className="hm-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
    </button>
    {open && <div className="hm-panel" role="menu">
      <p className="hm-panel-title hm-panel-name">{name}</p>
      {extra}
      <a role="menuitem" className="hm-item" href={profileHref}>Hồ sơ cá nhân</a>
      <div className="hm-sep" />
      <button role="menuitem" type="button" className="hm-item hm-danger" onClick={() => { setOpen(false); onLogout(); }}>Đăng xuất</button>
    </div>}
  </div>;
}
