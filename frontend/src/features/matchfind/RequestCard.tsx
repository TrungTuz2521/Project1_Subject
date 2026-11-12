import { useState } from 'react';
import { bookingHash } from '../../services/bookingNavigation';
import { matchRequests, pitchNames, ruleNames, skillNames, slotEnd, slotStarts, toleranceNames, typeNames } from '../../services/matchRequests';
import type { MatchRequest, Person } from '../../services/matchRequests';
import { Warning } from '../field-management/ui';
import { dayChip, money, slotLabel, tel, time, timeLeft } from './format';

const statusNames = { OPEN: 'Đang tìm', MATCHED: 'Đã ghép', EXPIRED: 'Không tìm được', CANCELLED: 'Đã hủy' } as const;
const DAY = 24 * 3600 * 1000;

function Contact({ person, label }: { person: Person; label: string }) {
  return <p className="mf-contact"><span>{label}</span><strong>{person.full_name}</strong>
    {person.phone ? <a href={tel(person.phone)}>{person.phone}</a> : <small>chưa có số điện thoại</small>}</p>;
}

/** Sent, searching, paired, played: where this request is, at a glance. */
function Rail({ request }: { request: MatchRequest }) {
  const played = request.match?.status === 'COMPLETED';
  const step = request.status === 'OPEN' ? 1 : request.status === 'MATCHED' ? (played ? 3 : 2) : -1;
  if (step < 0) return null;
  return <ol className="mf-rail" aria-label="Tiến trình">
    {['Đã gửi', 'Đang tìm', 'Đã ghép', 'Đã đá'].map((label, i) =>
      <li key={label} className={i < step ? 'is-done' : i === step ? 'is-now' : ''} aria-current={i === step ? 'step' : undefined}>{label}</li>)}
  </ol>;
}

function when(r: MatchRequest) {
  if (r.preferred_dates && r.status !== 'MATCHED') return `${r.preferred_dates.map(dayChip).join(', ')} · ${r.window_start}–${r.window_end}`;
  return r.match_time ? slotLabel(r.match_time, r.end_time) : '';
}

function Widen({ request, onSaved }: { request: MatchRequest; onSaved: (r: MatchRequest) => void }) {
  const flexible = Boolean(request.preferred_dates);
  const [start, setStart] = useState(request.window_start ?? '16:30');
  const [end, setEnd] = useState(request.window_end ?? '21:00');
  const [tolerance, setTolerance] = useState(request.skill_tolerance ?? 1);
  const [needed, setNeeded] = useState(request.required_players ?? 1);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true); setError(null);
    try {
      const body = { skill_tolerance: tolerance, ...(flexible ? { window_start: start, window_end: end } : {}),
        ...(request.request_type === 'RECRUIT_MEMBERS' ? { required_players: needed } : {}) };
      onSaved((await matchRequests.edit(request.request_id, body)).data);
    } catch (reason) { setError(reason); } finally { setBusy(false); }
  }
  return <div className="mf-widen">
    {flexible && <label>Khung giờ <select value={start} onChange={e => setStart(e.target.value)}>{slotStarts.map(s => <option key={s}>{s}</option>)}</select>
      – <select value={end} onChange={e => setEnd(e.target.value)}>{slotStarts.map(slotEnd).map(s => <option key={s}>{s}</option>)}</select></label>}
    <label>Trình độ <select value={tolerance} onChange={e => setTolerance(Number(e.target.value))}>{[0, 1, 4].map(t => <option key={t} value={t}>{toleranceNames[t]}</option>)}</select></label>
    {request.request_type === 'RECRUIT_MEMBERS' && <label>Cần thêm <input type="number" min={1} max={10} value={needed} onChange={e => setNeeded(Math.max(1, Number(e.target.value) || 1))} /> người</label>}
    <button type="button" className="mf-btn" disabled={busy} onClick={() => void save()}>{busy ? 'Đang lưu…' : 'Lưu và tìm lại'}</button>
    <Warning error={error} />
  </div>;
}

export function RequestCard({ request, onChanged, onResend }: {
  request: MatchRequest; onChanged: (r: MatchRequest) => void; onResend: (r: MatchRequest) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const r = request;
  const game = r.match;
  const kickOff = game?.start_time ?? r.joined_game?.start_time ?? r.match_time;
  const tooLate = r.status === 'MATCHED' && kickOff ? Date.parse(kickOff) - Date.now() < DAY : false;

  async function cancel() {
    const warning = r.status === 'OPEN' ? 'Hủy yêu cầu này? Hệ thống sẽ ngừng tìm.'
      : r.request_type === 'FIND_OPPONENT' ? 'Hủy kèo đã ghép? Đội kia sẽ được tìm đối khác. Tiền cọc đội bạn đã trả cho kèo này sẽ không được hoàn.'
      : r.request_type === 'LOOK_FOR_TEAM' ? 'Rút khỏi trận này? Đội trưởng sẽ được báo và hệ thống tìm người khác.'
      : 'Hủy tìm người? Những người đã được ghép vào trận sẽ được báo.';
    if (!window.confirm(warning)) return;
    setBusy(true); setError(null);
    try { onChanged((await matchRequests.cancel(r.request_id)).data); } catch (reason) { setError(reason); } finally { setBusy(false); }
  }

  return <article className={`mf-card is-${r.status.toLowerCase()}`}>
    <header className="mf-card-head">
      <span className="mf-type">{typeNames[r.request_type]}{r.team ? ` · ${r.team.team_name}` : ''}</span>
      <span className={`mf-status is-${r.status.toLowerCase()}`}>{statusNames[r.status]}</span>
    </header>
    <p className="mf-when">{when(r)}</p>
    <p className="mf-facts">
      {r.pitch_name ? r.pitch_name : r.pitch_type ? pitchNames[r.pitch_type] : 'Sân nào cũng được'}
      {' · '}{skillNames[r.skill_level]}{r.skill_tolerance != null ? `, ${toleranceNames[r.skill_tolerance].toLowerCase()}` : ''}
      {r.request_type === 'FIND_OPPONENT' ? ` · ${r.payment_rule ? ruleNames[r.payment_rule] : 'chia tiền theo đội kia'}` : ''}
      {r.request_type === 'RECRUIT_MEMBERS' ? ` · còn thiếu ${r.required_players ?? 0} người` : ''}
      {r.request_type === 'LOOK_FOR_TEAM' ? ` · ${r.players} người` : ''}
      {r.request_type === 'FIND_OPPONENT' ? ` · ${r.players} người đi đá` : ''}
    </p>
    {r.booking_id && r.request_type === 'FIND_OPPONENT' && r.status === 'OPEN' && <p className="mf-note">Đã có sân, ưu tiên đội chưa đặt sân.</p>}
    <Rail request={r} />

    {r.status === 'OPEN' && r.search_until && <p className="mf-note">Dừng tìm lúc {slotLabel(r.search_until)} ({timeLeft(r.search_until) || 'sắp dừng'}).</p>}

    {game && <div className="mf-result">
      <p className="mf-versus"><strong>{r.team?.team_name ?? 'Đội bạn'}</strong><span>gặp</span><strong>{game.opponent.team?.team_name ?? 'Đối thủ'}</strong></p>
      <p>Đối thủ trình độ {skillNames[game.opponent.skill_level].toLowerCase()}, {game.opponent.players} người đi đá</p>
      <Contact person={game.opponent.captain} label="Đội trưởng đối thủ" />
      {game.my_deposit && <div className={`mf-deposit${game.needs_deposit ? ' is-due' : ''}`}>
        {game.needs_deposit
          ? <><p><strong>Đội bạn cần cọc {money(game.my_deposit)}</strong>{game.hold_expires_at ? ` trước ${time(game.hold_expires_at)} (${timeLeft(game.hold_expires_at) || 'đã hết hạn'})` : ''}.</p>
              <p>Quá hạn mà một đội chưa cọc thì kèo bị hủy. Đối thủ: {game.opponent_deposit_paid ? 'đã cọc' : 'chưa cọc'}.</p>
              {game.booking_id && <a className="mf-btn" href={`${bookingHash(game.booking_id)}&pay=1`}>Đặt cọc ngay</a>}</>
          : <p>Đội bạn đã cọc {money(game.my_deposit)}. Đối thủ: {game.opponent_deposit_paid ? 'đã cọc' : 'chưa cọc'}.{game.status === 'CONFIRMED' ? ' Kèo đã chốt.' : ''}</p>}
      </div>}
      {!game.my_deposit && game.status === 'CONFIRMED' && <p className="mf-note">Kèo đã chốt. Phần tiền sân còn lại trả tại quầy.</p>}
    </div>}

    {r.joined_game && <div className="mf-result">
      <p>{slotLabel(r.joined_game.start_time, r.joined_game.end_time)}{r.joined_game.pitch_name ? ` tại ${r.joined_game.pitch_name}` : ''}{r.joined_game.team ? ` · đá cùng ${r.joined_game.team.team_name}` : ''}</p>
      <Contact person={r.joined_game.captain} label="Đội trưởng" />
      {Number(r.joined_game.fee_per_player) > 0 && <p className="mf-note">Chi phí mỗi người {money(r.joined_game.fee_per_player)}, trả cho đội trưởng.</p>}
    </div>}

    {r.request_type === 'RECRUIT_MEMBERS' && r.joiners.length > 0 && <div className="mf-result">
      <p><strong>Người sẽ đá cùng</strong></p>
      {r.joiners.map(j => <Contact key={j.user_id} person={j} label={`${j.party_size} người${j.skill_level ? ' · ' + skillNames[j.skill_level].toLowerCase() : ''}`} />)}
    </div>}

    {r.status === 'EXPIRED' && <p className="mf-note">Đến hạn 1 ngày trước giờ đá vẫn chưa tìm được. Thử gửi lại với khung giờ hoặc trình độ rộng hơn.</p>}

    {editing && r.status === 'OPEN' && <Widen request={r} onSaved={next => { setEditing(false); onChanged(next); }} />}
    <Warning error={error} />
    <footer className="mf-actions">
      {r.status === 'OPEN' && !editing && <button type="button" className="mf-btn mf-btn-light" onClick={() => setEditing(true)}>Nới tiêu chí</button>}
      {game?.opponent.captain.phone && <a className="mf-btn mf-btn-light" href={tel(game.opponent.captain.phone)}>Gọi đối thủ</a>}
      {r.status === 'OPEN' || (r.status === 'MATCHED' && !tooLate)
        ? <button type="button" className="mf-btn mf-btn-quiet" disabled={busy} onClick={() => void cancel()}>{r.status === 'OPEN' ? 'Hủy yêu cầu' : r.request_type === 'LOOK_FOR_TEAM' ? 'Rút khỏi trận' : 'Hủy kèo'}</button>
        : r.status === 'MATCHED' && game?.status !== 'COMPLETED' ? <small className="mf-note">Còn dưới 1 ngày: muốn hủy hãy gọi quầy.</small> : null}
      {(r.status === 'EXPIRED' || r.status === 'CANCELLED') && <button type="button" className="mf-btn mf-btn-light" onClick={() => onResend(r)}>Gửi lại</button>}
    </footer>
  </article>;
}
