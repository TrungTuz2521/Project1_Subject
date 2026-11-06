import { useEffect, useState } from 'react';
import { toDataURL } from 'qrcode';
import { Banner } from '../field-management/ui';

/** Encode the server's payload locally, without sending bank data to a QR service. */
export function BankQR({ payload }: { payload: string }) {
  const [url, setUrl] = useState('');
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    setUrl(''); setFailed(false);
    toDataURL(payload, { width: 320, margin: 4, errorCorrectionLevel: 'M' })
      .then(value => { if (alive) setUrl(value); })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [payload]);
  return failed ? <Banner>Không thể hiển thị QR. Hãy tải lại hoặc đối chiếu tại quầy.</Banner>
    : url ? <img className="huy-bank-qr" src={url} alt="QR chuyển khoản cho booking" /> : <p>Đang tạo ảnh QR…</p>;
}
