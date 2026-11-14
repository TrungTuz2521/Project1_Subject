import { useState } from 'react';
import type { DemoDepositResult } from '../../types/api';
import { confirmDemoDeposit } from '../../services/depositBank';
import { formErrorMessage } from '../../services/formErrors';
import { Banner, Button } from '../field-management/ui';

export const demoDepositEnabled = import.meta.env.DEV && import.meta.env.VITE_DEMO_DEPOSIT === 'true';

export function DemoDepositConfirmation({ bookingId, enabled, canConfirm, alreadyPaid = false, onConfirmed }: {
  bookingId: number; enabled: boolean; canConfirm: boolean; alreadyPaid?: boolean;
  onConfirmed?: (result: DemoDepositResult) => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!enabled) return null;
  async function confirm() {
    if (!canConfirm || busy) return;
    setBusy(true);setError('');
    try {
      const result = await confirmDemoDeposit(bookingId);
      setConfirmed(true);onConfirmed?.(result);
    } catch (reason) { setError(formErrorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <div>
    {error&&<Banner tone="danger">{error}</Banner>}
    {confirmed || alreadyPaid ? <Banner tone="success">Đã lưu xác nhận cọc DEMO vào database. Chưa xác minh tiền ngân hàng.</Banner> :
      <Button disabled={!canConfirm || busy} onClick={() => void confirm()}>{busy?'Đang xác nhận…':'Xác nhận thanh toán cọc (demo)'}</Button>}
  </div>;
}
