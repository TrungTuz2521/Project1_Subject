import { useEffect, useRef, useState } from 'react';
import type { BankDepositPayer, QrPaymentSession } from '../../types/api';
import { getPaymentStatus, openQrPayment } from '../../services/depositBank';
import { formErrorMessage } from '../../services/formErrors';
import { moneyVN, serverNow } from '../../services/huyApi';
import { Banner, Button, countdown, useNow } from '../field-management/ui';
import { BankQR } from './BankQR';

const POLL_MS = 3000;

/** One payer's short-lived QR. The browser only shows and polls; the bank webhook on the server marks it paid. */
export function QrPaymentPanel({ bookingId, payer, validHold, ttlSeconds = 60, onPaid }: {
  bookingId: number; payer: BankDepositPayer; validHold: boolean; ttlSeconds?: number; onPaid?: () => void;
}) {
  const [session, setSession] = useState<QrPaymentSession | null>(payer.qr_session ?? null);
  const [paid, setPaid] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const now = useNow();
  const paidCallback = useRef(onPaid);
  paidCallback.current = onPaid;
  const serverSession = payer.qr_session ?? null;
  useEffect(() => { if (serverSession) setSession(old => old?.payment_id === serverSession.payment_id ? old : serverSession); }, [serverSession]);

  const paymentId = session?.payment_id;
  const watchUntil = session ? Date.parse(session.hold_expires_at) : 0;
  useEffect(() => {
    if (!paymentId || paid) return;
    let alive = true;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      // Money sent just before the code vanished may be reported later, so keep asking until the hold ends.
      if (serverNow() > watchUntil + 5000) { window.clearInterval(timer); return; }
      if (document.visibilityState === 'hidden') return;
      getPaymentStatus(paymentId, controller.signal).then(payment => {
        if (alive && payment.status === 'SUCCESS') { setPaid(true); paidCallback.current?.(); }
      }).catch(() => {});
    }, POLL_MS);
    return () => { alive = false; controller.abort(); window.clearInterval(timer); };
  }, [paymentId, paid, watchUntil]);

  async function open() {
    if (busy) return;
    setBusy(true); setError('');
    try { setSession(await openQrPayment(bookingId)); }
    catch (reason) { setError(formErrorMessage(reason)); }
    finally { setBusy(false); }
  }

  if (paid || payer.status === 'PAID') {
    return <Banner tone="success">Đã thanh toán phần cọc {moneyVN(payer.required_amount)}. Email xác nhận đặt sân sẽ được gửi tới bạn.</Banner>;
  }
  const showing = !!session && Date.parse(session.qr_expires_at) > now;
  return <div className="huy-payer-panel">
    {error && <Banner tone="danger">{error}</Banner>}
    {showing && session ? <>
      <div className="huy-flex"><span>Mã QR hết hiệu lực sau</span><strong className="huy-timer">⏱ {countdown(session.qr_expires_at, now)}</strong></div>
      <BankQR payload={session.qr_payload} />
      <div className="huy-info-grid">
        <div><small>Số tiền (đã điền sẵn)</small><strong>{moneyVN(session.amount)}</strong></div>
        <div><small>Nội dung chuyển khoản (đã điền sẵn)</small><strong>{session.transfer_reference}</strong></div>
        <div><small>Ngân hàng</small><strong>{session.bank_name}</strong></div>
        <div><small>Tài khoản nhận</small><strong>{session.account_no} · {session.account_name}</strong></div>
      </div>
      <p className="huy-muted">Quét bằng app ngân hàng, giữ nguyên số tiền và nội dung. Sân đang được giữ cho bạn; trang tự cập nhật khi ngân hàng báo đã nhận tiền.</p>
    </> : <>
      {session && <Banner>Mã QR đã hết hiệu lực. Nếu bạn đã chuyển khoản, đừng chuyển lại: hệ thống vẫn ghi nhận khi ngân hàng báo về.</Banner>}
      {!payer.can_open_qr && payer.unavailable_reason && <Banner>{payer.unavailable_reason}</Banner>}
      <p>Phần cọc cần trả: <strong>{moneyVN(payer.due_amount)}</strong></p>
      <Button disabled={!validHold || !payer.can_open_qr || busy} onClick={() => void open()}>
        {busy ? 'Đang tạo mã…' : session ? 'Tạo mã QR mới' : `Tạo mã QR thanh toán (${ttlSeconds} giây)`}
      </Button>
    </>}
  </div>;
}
