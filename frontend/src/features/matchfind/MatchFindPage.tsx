import { useCallback, useEffect, useState } from 'react';
import type { UserSelf } from '../../types/api';
import { matchRequests } from '../../services/matchRequests';
import type { MatchRequest, RequestOptions, RequestType } from '../../services/matchRequests';
import { Banner, Warning } from '../field-management/ui';
import { RequestCard } from './RequestCard';
import { RequestComposer } from './RequestComposer';
import '../../styles/matchfind.css';

type Tab = 'OPEN' | 'MATCHED' | 'DONE';
const tabs: { key: Tab; label: string }[] = [{ key: 'OPEN', label: 'Đang tìm' }, { key: 'MATCHED', label: 'Đã ghép' }, { key: 'DONE', label: 'Đã kết thúc' }];
const inTab = (tab: Tab, r: MatchRequest) => tab === 'DONE' ? r.status === 'EXPIRED' || r.status === 'CANCELLED' : r.status === tab;

/** Send criteria, the system finds the match: no browsing other people's posts. */
export function MatchFindPage({ user }: { user: UserSelf }) {
  const [requests, setRequests] = useState<MatchRequest[] | null>(null);
  const [options, setOptions] = useState<RequestOptions | null>(null);
  const [tab, setTab] = useState<Tab>('OPEN');
  const [composer, setComposer] = useState<{ type?: RequestType } | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const [mine, opts] = await Promise.all([matchRequests.mine(signal), matchRequests.options(signal)]);
      setRequests(mine.data); setOptions(opts.data); setError(null);
    } catch (reason) { if (!signal?.aborted) setError(reason); }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    // Matches are made in the background: refresh while the page is open.
    const timer = window.setInterval(() => { if (document.visibilityState !== 'hidden') void load(); }, 20_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [load]);

  const replace = (next: MatchRequest) => setRequests(rows => rows ? [next, ...rows.filter(r => r.request_id !== next.request_id)] : [next]);
  function created(next: MatchRequest) {
    replace(next); setComposer(null);
    setTab(next.status === 'MATCHED' ? 'MATCHED' : 'OPEN');
    setNotice(next.status === 'MATCHED' ? 'Đã tìm được ngay! Xem kết quả bên dưới, email cũng đã được gửi.' : 'Đã gửi yêu cầu. Hệ thống đang tìm và sẽ báo bạn qua email khi có kết quả.');
    void load();
  }
  const counts = Object.fromEntries(tabs.map(t => [t.key, (requests ?? []).filter(r => inTab(t.key, r)).length])) as Record<Tab, number>;
  const shown = (requests ?? []).filter(r => inTab(tab, r));

  return <section className="mf-page">
    <header className="mf-head">
      <div><h1>Tìm kèo</h1><p>Gửi ngày, giờ và trình độ bạn muốn. Hệ thống tự tìm đội hoặc người phù hợp nhất và báo bạn qua email.</p></div>
      {!composer && <button type="button" className="mf-submit" disabled={!options} onClick={() => { setComposer({}); setNotice(''); }}>Gửi yêu cầu</button>}
    </header>
    {notice && <Banner tone="success">{notice}</Banner>}
    <Warning error={error} />

    {composer && options && <RequestComposer options={options} me={user} initialType={composer.type} onDone={created} onClose={() => setComposer(null)} />}

    <div className="mf-tabs" role="tablist">{tabs.map(t =>
      <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={tab === t.key ? 'is-on' : ''} onClick={() => setTab(t.key)}>
        {t.label}{counts[t.key] ? <span>{counts[t.key]}</span> : null}</button>)}
    </div>

    {requests === null ? <p className="mf-muted">Đang tải…</p> : shown.length === 0
      ? <div className="mf-empty">
          {tab === 'OPEN' ? <><p>Bạn chưa có yêu cầu nào đang tìm.</p>
            <div className="mf-empty-actions">
              <button type="button" className="mf-btn" onClick={() => setComposer({ type: 'FIND_OPPONENT' })}>Tìm đối</button>
              <button type="button" className="mf-btn mf-btn-light" onClick={() => setComposer({ type: 'RECRUIT_MEMBERS' })}>Tìm thêm người</button>
              <button type="button" className="mf-btn mf-btn-light" onClick={() => setComposer({ type: 'LOOK_FOR_TEAM' })}>Đá ké</button>
            </div></>
            : <p>{tab === 'MATCHED' ? 'Chưa có kèo nào được ghép.' : 'Chưa có yêu cầu nào kết thúc.'}</p>}
        </div>
      : <div className="mf-list">{shown.map(r => <RequestCard key={r.request_id} request={r}
          onChanged={next => { replace(next); void load(); }}
          onResend={prev => { setComposer({ type: prev.request_type }); window.scrollTo({ top: 0, behavior: 'smooth' }); }} />)}</div>}
  </section>;
}
