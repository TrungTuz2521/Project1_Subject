import { useEffect, useState } from 'react';
import type { Notification } from '../../types/api';
import { NOTIFICATIONS_CHANGED, notificationsService } from '../../services/notifications';
import { Warning } from '../field-management/ui';
import '../../styles/matchfind.css';

const MATCH_TYPES = new Set(['MATCH_CONFIRMED', 'MATCH_CANCELLED', 'TEAM_JOINED', 'POST_EXPIRED', 'BOOKING_HOLD']);
const stamp = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' });
/** Where a notice leads: the game page for matchmaking news, the bookings page for money and pitch news. */
const target = (n: Notification) => MATCH_TYPES.has(n.notification_type) && (n.match_id || n.notification_type !== 'BOOKING_HOLD') ? '#/matchmaking' : '#/my-bookings';

export function NotificationsPage() {
  const [rows, setRows] = useState<Notification[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    const controller = new AbortController();
    const load = () => notificationsService.list(1, undefined, controller.signal).then(r => { setRows(r.data); setError(null); })
      .catch(reason => { if (!controller.signal.aborted) setError(reason); });
    void load();
    const timer = window.setInterval(() => { if (document.visibilityState !== 'hidden') void load(); }, 20_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, []);
  async function open(n: Notification) {
    if (!n.is_read) {
      setRows(list => list?.map(x => x.notification_id === n.notification_id ? { ...x, is_read: true } : x) ?? null);
      try { await notificationsService.markRead(n.notification_id); window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED)); } catch { /* reading is best effort */ }
    }
    window.location.hash = target(n).slice(1);
  }
  const unread = (rows ?? []).filter(n => !n.is_read).length;
  return <section className="mf-page">
    <header className="mf-head"><div><h1>Thông báo</h1><p>{unread ? `${unread} thông báo chưa đọc.` : 'Bạn đã đọc hết thông báo.'} Các thông báo quan trọng cũng được gửi qua email.</p></div></header>
    <Warning error={error} />
    {rows === null ? <p className="mf-muted">Đang tải…</p> : rows.length === 0 ? <div className="mf-empty"><p>Chưa có thông báo nào.</p></div>
      : <ul className="mf-inbox">{rows.map(n => <li key={n.notification_id}>
          <button type="button" className={n.is_read ? '' : 'is-unread'} onClick={() => void open(n)}>
            <span className="mf-inbox-top"><strong>{n.title}</strong><small>{stamp.format(new Date(n.created_at))}</small></span>
            <span className="mf-inbox-text">{n.content}</span>
          </button></li>)}</ul>}
  </section>;
}
