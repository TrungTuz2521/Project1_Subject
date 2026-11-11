import { useEffect, useState } from 'react';
import type { PendingRefund } from '../../types/api';
import { completeManualRefund, dateVN, getPendingRefunds, moneyVN } from '../../services/huyApi';
import { Banner, Card, Warning } from '../../features/field-management/ui';
import { ReasonDialog } from './Dialog';

/** Refunds still owed. Cash/bank-transfer ones wait for the Admin to pay back by hand, then confirm here. */
export function AdminRefundQueue({ revision = 0 }: { revision?: number }) {
  const [items, setItems] = useState<PendingRefund[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState<number | null>(null);
  const [reload, setReload] = useState(0);
  const [confirming, setConfirming] = useState<PendingRefund | null>(null);
  useEffect(() => {
    let live = true;
    getPendingRefunds().then(rows => { if (live) setItems(rows); }).catch(e => { if (live) setError(e); });
    return () => { live = false; };
  }, [revision, reload]);

  async function complete(item: PendingRefund, how: string) {
    if (!item.original) return;
    const who = item.payer.full_name ?? `#${item.payer.user_id}`;
    setBusy(item.payment_id); setError(null); setNotice('');
    try {
      await completeManualRefund(item.original.payment_id, how);
      setNotice(`Đã ghi nhận hoàn ${moneyVN(item.amount)} cho ${who}.`); setReload(n => n + 1);
    } finally { setBusy(null); }
  }

  if (items.length === 0 && !error && !notice) return null;
  return <Card><h2>Khoản cần hoàn ({items.length})</h2>
    <Warning error={error} />{notice && <Banner tone="success">{notice}</Banner>}
    <Banner>Khoản tiền mặt/chuyển khoản (kể cả QR SePay) không tự hoàn. Hãy liên hệ người nhận, chuyển trả, rồi bấm "Đã trả tiền".</Banner>
    {items.length > 0 && <div className="huy-table-wrap"><table><thead><tr><th>Booking</th><th>Người nhận</th><th>Số tiền</th><th>Khoản gốc</th><th>Thao tác</th></tr></thead><tbody>
      {items.map(item => <tr key={item.payment_id}>
        <td><strong>#{item.booking_id ?? '—'}</strong><small className="huy-block">{item.note ?? ''}</small></td>
        <td><strong>{item.payer.full_name ?? `#${item.payer.user_id}`}</strong><small className="huy-block">{item.payer.phone ?? 'Không có SĐT'}</small><small className="huy-block">{item.payer.email ?? ''}</small></td>
        <td><strong>{moneyVN(item.amount)}</strong><small className="huy-block">{item.payment_method}</small></td>
        <td><small className="huy-block">{item.original?.transaction_code ?? '—'}</small><small className="huy-block">{item.original?.paid_at ? dateVN(item.original.paid_at) : ''}</small></td>
        <td><div className="huy-table-actions">{item.manual
          ? <button type="button" disabled={busy !== null} onClick={() => setConfirming(item)}>{busy === item.payment_id ? 'Đang lưu…' : 'Đã trả tiền'}</button>
          : <small>Cổng thanh toán tự hoàn</small>}</div></td>
      </tr>)}
    </tbody></table></div>}
    {confirming && <ReasonDialog title="Xác nhận đã trả tiền cho khách"
      message={<>Bạn đã trả <strong>{moneyVN(confirming.amount)}</strong> cho <strong>{confirming.payer.full_name ?? `#${confirming.payer.user_id}`}</strong>{confirming.payer.phone ? ` (${confirming.payer.phone})` : ''}? Thao tác này không hoàn tác được.</>}
      reasonLabel="Cách trả" placeholder="Chuyển khoản Vietcombank FT123 / tiền mặt tại quầy"
      confirmLabel={() => 'Đã trả tiền'} onConfirm={how => complete(confirming, how)} onClose={() => setConfirming(null)} />}
  </Card>;
}
