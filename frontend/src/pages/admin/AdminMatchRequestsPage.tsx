import { useEffect, useState } from 'react';
import { matchRequests, pitchNames, skillNames, toleranceNames, typeNames } from '../../services/matchRequests';
import type { MatchRequest, RequestStatus, RequestType } from '../../services/matchRequests';
import { Banner, Button, Card, Head, Warning } from '../../features/field-management/ui';
import { dayChip, slotLabel } from '../../features/matchfind/format';
import { Pager } from './Pager';

const statusNames: Record<RequestStatus, string> = { OPEN: 'Đang tìm', MATCHED: 'Đã ghép', EXPIRED: 'Không tìm được', CANCELLED: 'Đã hủy' };
const PAGE = 50;

function when(r: MatchRequest) {
  const game = r.match?.start_time ?? r.joined_game?.start_time ?? null;
  if (game) return slotLabel(game);
  if (r.preferred_dates) return `${r.preferred_dates.map(dayChip).join(', ')} · ${r.window_start}–${r.window_end}`;
  return r.match_time ? slotLabel(r.match_time, r.end_time) : '—';
}

function outcome(r: MatchRequest) {
  if (r.match) return `Gặp ${r.match.opponent.team?.team_name ?? 'đối thủ'}${r.match.pitch_name ? ' · ' + r.match.pitch_name : ''}${r.match.needs_deposit ? ' · chờ cọc' : ''}`;
  if (r.joined_game) return `Đá cùng ${r.joined_game.captain.full_name}`;
  if (r.request_type === 'RECRUIT_MEMBERS') return `${r.joiners.length} nhóm đã vào, còn thiếu ${r.required_players ?? 0}`;
  return r.status === 'OPEN' && r.search_until ? `Dừng tìm ${slotLabel(r.search_until)}` : '';
}

/** Every request customers sent, what came of it, and a button to run the matcher now. */
export function AdminMatchRequestsPage() {
  const [status, setStatus] = useState<RequestStatus | ''>('OPEN');
  const [type, setType] = useState<RequestType | ''>('');
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<MatchRequest[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setRows(null);
    matchRequests.adminList({ ...(status ? { status } : {}), ...(type ? { request_type: type } : {}), page }, controller.signal)
      .then(r => { setRows(r.data); setTotal(r.meta.total); setError(null); })
      .catch(e => { if (!controller.signal.aborted) { setError(e); setRows([]); } });
    return () => controller.abort();
  }, [status, type, page, reload]);

  async function scanNow() {
    setBusy(true); setNotice(''); setError(null);
    try {
      const r = (await matchRequests.adminScan()).data;
      setNotice(`Đã quét ${r.scanned_count} yêu cầu: ghép được ${r.matches.length} kèo đối, ${r.joined_requests.length} người đá ké.`);
      setReload(n => n + 1);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }

  return <>
    <Head title="Kèo ghép" description="Yêu cầu tìm đối, tìm thêm người và đá ké của khách. Hệ thống tự ghép mỗi 15 giây khi bộ lập lịch đang chạy."
      aside={<Button disabled={busy} onClick={() => void scanNow()}>{busy ? 'Đang quét…' : 'Quét ngay'}</Button>} />
    {notice && <Banner tone="success">{notice}</Banner>}
    <Warning error={error} />
    <Card>
      <div className="huy-flex">
        <label className="huy-field"><span>Trạng thái</span><select value={status} onChange={e => { setStatus(e.target.value as RequestStatus | ''); setPage(1); }}>
          <option value="">Tất cả</option>{(Object.keys(statusNames) as RequestStatus[]).map(s => <option key={s} value={s}>{statusNames[s]}</option>)}</select></label>
        <label className="huy-field"><span>Loại</span><select value={type} onChange={e => { setType(e.target.value as RequestType | ''); setPage(1); }}>
          <option value="">Tất cả</option>{(Object.keys(typeNames) as RequestType[]).map(t => <option key={t} value={t}>{typeNames[t]}</option>)}</select></label>
      </div>
      {rows === null ? <p className="huy-muted">Đang tải…</p> : rows.length === 0 ? <p className="huy-muted">Không có yêu cầu nào.</p> :
        <div className="huy-table-wrap"><table><thead><tr><th>Khách</th><th>Loại</th><th>Thời gian</th><th>Tiêu chí</th><th>Trạng thái</th><th>Kết quả</th></tr></thead><tbody>
          {rows.map(r => <tr key={r.request_id}>
            <td><strong>{r.requester?.full_name ?? '—'}</strong><small className="huy-block">{r.requester?.phone ?? 'Không có SĐT'}</small>{r.team && <small className="huy-block">{r.team.team_name}</small>}</td>
            <td>{typeNames[r.request_type]}{r.booking_id && r.request_type !== 'LOOK_FOR_TEAM' ? <small className="huy-block">Có sân #{r.booking_id}</small> : null}</td>
            <td>{when(r)}</td>
            <td>{r.pitch_type ? pitchNames[r.pitch_type] : 'Sân bất kỳ'} · {skillNames[r.skill_level]}<small className="huy-block">{r.skill_tolerance != null ? toleranceNames[r.skill_tolerance] : ''}</small></td>
            <td>{statusNames[r.status]}</td>
            <td>{outcome(r)}</td>
          </tr>)}
        </tbody></table></div>}
      <Pager page={page} pageSize={PAGE} total={total} onPage={setPage} disabled={rows === null} />
    </Card>
  </>;
}
