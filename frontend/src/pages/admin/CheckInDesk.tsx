import { useState } from 'react';
import type { AdminBooking, ArrivalStatus } from '../../types/api';
import { markArrival, moneyVN, timeVN } from '../../services/fieldApi';
import { Button, Card, Empty, Status, Warning, useNow } from '../../features/field-management/ui';

const EARLY_MS = 2 * 3600_000;

/**
 * Today's games as the counter sees them: who is coming, have they arrived, what is still owed.
 * Arrival opens 2 hours before kick-off; "Không đến" only once the slot has started (same rules as the API).
 */
export function CheckInDesk({ items, total, onChanged, settlement }: {
  items: AdminBooking[]; total: number; onChanged: () => void; settlement: (id: number) => void;
}) {
  const now = useNow();
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  async function mark(b: AdminBooking, status: ArrivalStatus | null) {
    setBusy(b.booking_id); setError(null);
    try { await markArrival(b.booking_id, status); onChanged(); } catch (e) { setError(e); } finally { setBusy(null); }
  }
  const arrived = items.filter(b => b.arrival_status === 'ARRIVED').length;
  return <Card className="adm-desk">
    <div className="adm-queue-head"><div><h2>Đón khách hôm nay</h2>
      <p className="huy-muted">{items.length ? `${arrived}/${items.length} đội đã đến${total > items.length ? `, đang hiện ${items.length}/${total} trận` : ''}.` : 'Khách đến quầy: đánh dấu đã đến và thu phần tiền còn lại.'}</p></div></div>
    <Warning error={error} />
    {items.length === 0 ? <Empty>Hôm nay chưa có trận nào được xác nhận.</Empty> : <div className="adm-desk-list">
      {items.map(b => {
        const start = Date.parse(b.start_time), end = Date.parse(b.end_time);
        const canArrive = now >= start - EARLY_MS && now < end;
        const canNoShow = now >= start;
        const owed = b.balance && b.balance.outstanding_amount !== '0.00' ? b.balance.outstanding_amount : null;
        const state = b.arrival_status === 'ARRIVED' ? 'arrived' : b.arrival_status === 'NO_SHOW' ? 'noshow' : now >= start ? 'late' : 'waiting';
        return <div key={b.booking_id} className={`adm-desk-row is-${state}`}>
          <div className="adm-desk-time"><strong>{timeVN(b.start_time)}</strong><small>{timeVN(b.end_time)}</small></div>
          <div className="adm-desk-who">
            <strong>{b.customer?.full_name ?? `Khách #${b.user_id}`}</strong>
            <small>{b.pitch_name ?? `Sân #${b.pitch_id}`}{b.customer?.phone ? `, ${b.customer.phone}` : ''}{b.series_id ? ', khách cố định' : ''}</small>
            {b.teams && <small>{b.teams.source.team_name ?? '?'} gặp {b.teams.opponent.team_name ?? '?'}</small>}
            {!!b.customer?.no_show_count && <span className="adm-flag">Đã bùng {b.customer.no_show_count} lần</span>}
          </div>
          <div className="adm-desk-money">{owed ? <><small>Còn thu</small><strong>{moneyVN(owed)}</strong></> : b.balance ? <Status state="PAID" /> : null}</div>
          <div className="adm-desk-state">
            {state === 'arrived' && <span className="adm-state ok">Đã đến {b.arrived_at ? timeVN(b.arrived_at) : ''}</span>}
            {state === 'noshow' && <span className="adm-state bad">Không đến</span>}
            {state === 'late' && <span className="adm-state warn">Đã tới giờ, chưa thấy khách</span>}
            {state === 'waiting' && <span className="adm-state">Chưa đến</span>}
          </div>
          <div className="adm-row-actions">
            {!b.arrival_status && <Button variant="light" disabled={!canArrive || busy !== null} onClick={() => void mark(b, 'ARRIVED')}>{canArrive ? 'Đã đến' : 'Chưa tới giờ nhận'}</Button>}
            {owed && b.arrival_status !== 'NO_SHOW' && <Button variant="outline" onClick={() => settlement(b.booking_id)}>Thu {moneyVN(owed)}</Button>}
            {!b.arrival_status && canNoShow && <button type="button" className="adm-link-danger" disabled={busy !== null} onClick={() => void mark(b, 'NO_SHOW')}>Không đến</button>}
            {b.arrival_status && <button type="button" className="adm-textlink" disabled={busy !== null} onClick={() => void mark(b, null)}>Hoàn tác</button>}
          </div>
        </div>;
      })}
    </div>}
  </Card>;
}
