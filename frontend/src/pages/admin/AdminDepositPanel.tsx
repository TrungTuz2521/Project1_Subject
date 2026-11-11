import { useState } from 'react';
import type { AdminBooking } from '../../types/api';
import { moneyVN, recordManualDeposit } from '../../services/huyApi';
import { Banner, Button, Card, Field, Warning, countdown, useNow } from '../../features/field-management/ui';

const whole = (value: string) => String(Math.max(0, Math.round(Number(value))));

/** Counter/statement deposit for a held booking. The server rechecks the due share and the hold deadline. */
export function AdminDepositPanel({ booking, onDone, onClose }: { booking: AdminBooking; onDone: (message: string) => void; onClose: () => void }) {
  const unpaid = booking.payer_progress.filter(p => p.status !== 'PAID');
  const now = useNow();
  const [userId, setUserId] = useState(unpaid[0]?.user_id ?? 0);
  const payer = unpaid.find(p => p.user_id === userId);
  const due = payer ? whole(String(Number(payer.required_amount) - Number(payer.paid_amount))) : '0';
  const [amount, setAmount] = useState(due);
  const [method, setMethod] = useState<'CASH' | 'BANK_TRANSFER'>('CASH');
  const [reference, setReference] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const expired = !booking.hold_expires_at || Date.parse(booking.hold_expires_at) <= now;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy || !payer) return;
    setBusy(true); setError(null);
    try {
      await recordManualDeposit({ booking_id: booking.booking_id, user_id: payer.user_id, amount: `${whole(amount)}.00`,
        payment_type: 'BOOKING_DEPOSIT', payment_method: method, reference: reference.trim() });
      onDone(`Đã ghi nhận cọc ${moneyVN(whole(amount))} cho booking #${booking.booking_id}.`);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }

  return <Card><h2>Ghi nhận cọc · Booking #{booking.booking_id}</h2>
    <Warning error={error} />
    <p>Hạn giữ sân còn <strong className={expired ? 'huy-danger' : 'huy-timer'}>⏱ {countdown(booking.hold_expires_at, now)}</strong></p>
    {expired ? <Banner tone="danger">Đã hết hạn giữ sân: không nhận cọc nữa, khách cần đặt lại.</Banner>
      : unpaid.length === 0 ? <Banner tone="success">Tất cả người trả đã đủ cọc.</Banner>
      : <form className="huy-form" onSubmit={e => void submit(e)}>
        <Field label="Người trả"><select value={userId} onChange={e => { const id = Number(e.target.value); setUserId(id);
          const next = unpaid.find(p => p.user_id === id); if (next) setAmount(whole(String(Number(next.required_amount) - Number(next.paid_amount)))); }}>
          {unpaid.map(p => <option key={p.user_id} value={p.user_id}>Người #{p.user_id} · đã trả {moneyVN(p.paid_amount)} / {moneyVN(p.required_amount)}</option>)}
        </select></Field>
        <Field label={`Số tiền nhận (tối đa ${moneyVN(due)})`}><input type="number" min="1" max={due} step="1" required value={amount} onChange={e => setAmount(e.target.value)} /></Field>
        <Field label="Hình thức"><select value={method} onChange={e => setMethod(e.target.value as 'CASH' | 'BANK_TRANSFER')}>
          <option value="CASH">Tiền mặt tại quầy</option><option value="BANK_TRANSFER">Chuyển khoản (đã thấy trên sao kê)</option></select></Field>
        <Field label="Mã chứng từ (số phiếu thu / mã giao dịch ngân hàng)"><input required maxLength={100} value={reference} onChange={e => setReference(e.target.value)} placeholder="vd. PT-0012 hoặc FT26315123" /></Field>
        <p className="huy-muted">Cùng mã chứng từ gửi lại sẽ không bị ghi trùng. Đủ cọc thì booking tự chuyển "Đã xác nhận" và gửi email cho khách.</p>
        <div className="huy-actions"><Button type="submit" disabled={busy || !reference.trim()}>{busy ? 'Đang lưu…' : 'Ghi nhận cọc'}</Button>
          <Button variant="outline" onClick={onClose}>Đóng</Button></div>
      </form>}
    {(expired || unpaid.length === 0) && <div className="huy-actions"><Button variant="outline" onClick={onClose}>Đóng</Button></div>}
  </Card>;
}
