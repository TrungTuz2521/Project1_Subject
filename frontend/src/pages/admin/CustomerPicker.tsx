import { useEffect, useState } from 'react';
import type { AdminUser } from '../../types/api';
import { searchUsers } from '../../services/fieldApi';
import { Button, Field } from '../../features/field-management/ui';

/** Search a customer by name, email or phone and pick one; the parent only ever receives a real user. */
export function CustomerPicker({ value, onChange }: { value: AdminUser | null; onChange: (user: AdminUser | null) => void }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState<AdminUser[]>([]);
  const [state, setState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');
  useEffect(() => {
    const text = q.trim();
    if (text.length < 2) { setResults([]); setState('idle'); return; }
    const controller = new AbortController();
    setState('loading');
    const timer = window.setTimeout(() => {
      searchUsers(text, controller.signal).then(rows => { setResults(rows); setState('done'); })
        .catch(() => { if (!controller.signal.aborted) setState('error'); });
    }, 300);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [q]);

  if (value) {
    return <Field label="Khách đặt sân"><div className="huy-payer-panel huy-flex">
      <span><strong>{value.full_name}</strong><small className="huy-block">{value.phone ?? 'Chưa có số điện thoại'}{value.walk_in ? ', khách vãng lai' : value.email ? `, ${value.email}` : ''}</small></span>
      <Button variant="outline" onClick={() => { onChange(null); setQ(''); }}>Đổi khách</Button>
    </div></Field>;
  }
  return <Field label="Khách đặt sân (tìm theo tên, email hoặc SĐT)">
    <input value={q} onChange={e => setQ(e.target.value)} placeholder="vd. Nguyễn Văn A, 0912…, a@gmail.com" maxLength={100} />
    {state === 'loading' && <small className="huy-muted">Đang tìm…</small>}
    {state === 'error' && <small className="huy-danger">Không tìm được, thử lại.</small>}
    {state === 'done' && results.length === 0 && <small className="huy-muted">Không tìm thấy. Nếu khách chưa có tài khoản, chọn "Khách vãng lai" và nhập tên, số điện thoại.</small>}
    {results.length > 0 && <div className="huy-booking-list">{results.map(user =>
      <button type="button" key={user.user_id} className="huy-booking-item" disabled={user.status !== 'ACTIVE'} onClick={() => onChange(user)}>
        <span><b>{user.full_name}</b><small>{user.phone ?? 'Chưa có số điện thoại'}{user.walk_in ? ', khách vãng lai' : user.email ? `, ${user.email}` : ''}</small></span>
        <small>{user.status === 'ACTIVE' ? 'Chọn' : 'Bị khóa'}</small>
      </button>)}</div>}
  </Field>;
}
