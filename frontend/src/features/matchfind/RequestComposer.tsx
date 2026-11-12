import { useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import type { SkillLevel, TeamPaymentRule } from '../../types/api';
import { matchRequests, pitchNames, ruleNames, skillNames, slotEnd, slotStarts, toleranceNames, typeNames } from '../../services/matchRequests';
import type { GamePitchType, GameSlot, MatchRequest, RequestCreate, RequestOptions, RequestType } from '../../services/matchRequests';
import { Warning } from '../field-management/ui';
import { dayChip, slotLabel } from './format';

const typeHelp: Record<RequestType, string> = {
  FIND_OPPONENT: 'Đội đủ người, cần một đội khác đá cùng.',
  RECRUIT_MEMBERS: 'Đã có lượt đá, còn thiếu vài người.',
  LOOK_FOR_TEAM: 'Bạn (và tối đa 2 bạn đi cùng) muốn vào đá với một đội đang thiếu người.',
};
const SIZE: Record<GamePitchType, number> = { PITCH_5: 5, PITCH_7: 7 };
const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T12:00:00+07:00`); d.setUTCDate(d.getUTCDate() + n);
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(d);
};

function Segmented<T extends string | number>({ label, value, options, onChange }: {
  label: string; value: T; options: { value: T; label: string }[]; onChange: (value: T) => void;
}) {
  return <fieldset className="mf-seg"><legend>{label}</legend><div>{options.map(o =>
    <button key={String(o.value)} type="button" aria-pressed={value === o.value} className={value === o.value ? 'is-on' : ''} onClick={() => onChange(o.value)}>{o.label}</button>)}
  </div></fieldset>;
}

/** One match day as chips, from the first allowed day. */
function DayPicker({ first, last, value, onChange }: { first: string; last: string; value: string[]; onChange: (days: string[]) => void }) {
  const days: string[] = [];
  for (let d = first; d <= last; d = addDays(d, 1)) days.push(d);
  return <fieldset className="mf-days"><legend>Ngày đá</legend><div role="radiogroup">{days.map(d => {
    const on = value[0] === d;
    return <button key={d} type="button" role="radio" aria-checked={on} className={on ? 'is-on' : ''} onClick={() => onChange([d])}>{dayChip(d)}</button>;
  })}</div></fieldset>;
}

function WindowPicker({ start, end, onStart, onEnd }: { start: string; end: string; onStart: (v: string) => void; onEnd: (v: string) => void }) {
  const count = slotStarts.filter(s => s >= start && slotEnd(s) <= end).length;
  return <fieldset className="mf-window"><legend>Khung giờ có thể đá</legend>
    <div className="mf-window-row">
      <label>Từ <select value={start} onChange={e => onStart(e.target.value)}>{slotStarts.map(s => <option key={s} value={s}>{s}</option>)}</select></label>
      <label>đến <select value={end} onChange={e => onEnd(e.target.value)}>{slotStarts.map(s => slotEnd(s)).map(s => <option key={s} value={s}>{s}</option>)}</select></label>
    </div>
    <small className={count ? '' : 'mf-warn'}>{count ? `Mỗi ngày có ${count} lượt 90 phút nằm trong khung này.` : 'Khung giờ chưa chứa trọn một lượt 90 phút.'}</small>
  </fieldset>;
}

export function RequestComposer({ options, me, initialType, onDone, onClose }: {
  options: RequestOptions; me: { user_id: number; full_name: string; skill_level: SkillLevel };
  initialType?: RequestType; onDone: (created: MatchRequest) => void; onClose: () => void;
}) {
  const [type, setType] = useState<RequestType>(initialType ?? 'FIND_OPPONENT');
  const [teamId, setTeamId] = useState<number | null>(options.teams[0]?.team_id ?? null);
  // Only the captain is on record and gets the emails; the squad is a head count, filled in from last time.
  const lastCount = (id: number | null) => options.teams.find(t => t.team_id === id)?.last_player_count ?? 7;
  const [players, setPlayers] = useState(() => lastCount(options.teams[0]?.team_id ?? null));
  const [booked, setBooked] = useState(false);
  const [bookingId, setBookingId] = useState<number | null>(null);
  const [pitchType, setPitchType] = useState<GamePitchType>('PITCH_7');
  const [joinPitch, setJoinPitch] = useState<GamePitchType | ''>('');
  const [dates, setDates] = useState<string[]>([]);
  const [start, setStart] = useState('16:30');
  const [end, setEnd] = useState('21:00');
  const [skill, setSkill] = useState<SkillLevel>(me.skill_level);
  const [tolerance, setTolerance] = useState(1);
  const [rule, setRule] = useState<TeamPaymentRule | 'ANY'>('ANY');
  const [needed, setNeeded] = useState(2);
  const [fee, setFee] = useState('');
  const [party, setParty] = useState(1);
  const [note, setNote] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [problem, setProblem] = useState('');
  const [saving, setSaving] = useState(false);

  // A message about an earlier attempt goes away as soon as the form changes.
  useEffect(() => setProblem(''), [type, teamId, players, booked, bookingId, pitchType, dates, start, end, needed, fee, party]);
  const team = options.teams.find(t => t.team_id === teamId) ?? null;
  const games: GameSlot[] = type === 'RECRUIT_MEMBERS' ? options.recruit_games : options.opponent_bookings;
  const game = games.find(g => g.booking_id === bookingId) ?? null;
  const firstDay = addDays(options.today, type === 'FIND_OPPONENT' ? options.rules.opponent_lead_days : 1);
  const lastDay = addDays(options.today, options.rules.max_days);
  const size = SIZE[type === 'FIND_OPPONENT' && booked && game ? game.pitch_type : pitchType];
  const pick = (next: RequestType) => { setType(next); setBookingId(null); setDates([]); setProblem(''); setError(null); };

  const summary = useMemo(() => {
    const when = (type !== 'LOOK_FOR_TEAM' && (booked || type === 'RECRUIT_MEMBERS'))
      ? (game ? slotLabel(game.start_time, game.end_time) + ' tại ' + game.pitch_name : 'lượt đá bạn chọn')
      : (dates.length ? dayChip(dates[0]) : 'ngày bạn chọn') + `, ${start}–${end}`;
    if (type === 'FIND_OPPONENT') return `Tìm đối cho ${team?.team_name ?? 'đội của bạn'} vào ${when}.`;
    if (type === 'RECRUIT_MEMBERS') return `Tìm thêm ${needed} người cho ${when}.`;
    return `Tìm trận để ${party > 1 ? `bạn và ${party - 1} người đi cùng` : 'bạn'} đá ké vào ${when}.`;
  }, [type, booked, game, dates, start, end, team, needed, party]);

  function validate(): string {
    if (type === 'FIND_OPPONENT') {
      if (!team) return 'Bạn cần là đội trưởng của một đội để tìm đối.';
      if (players < size) return `Đội cần ít nhất ${size} người đi đá.`;
      if (booked && !game) return 'Chọn lượt sân đã đặt.';
    }
    if (type === 'RECRUIT_MEMBERS' && !game) return 'Chọn lượt đá cần thêm người.';
    const flexible = type === 'LOOK_FOR_TEAM' || (type === 'FIND_OPPONENT' && !booked);
    if (flexible && dates.length === 0) return 'Chọn ngày đá.';
    if (flexible && !slotStarts.some(s => s >= start && slotEnd(s) <= end)) return 'Khung giờ phải chứa trọn một lượt 90 phút.';
    if (fee && !/^\d+$/.test(fee)) return 'Chi phí mỗi người là số tiền nguyên (VND).';
    return '';
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const message = validate(); setProblem(message); setError(null);
    if (message) return;
    const body: RequestCreate = { post_type: type, skill_level: skill, skill_tolerance: tolerance, ...(note.trim() ? { note: note.trim() } : {}) };
    if (type === 'FIND_OPPONENT') {
      Object.assign(body, { team_id: team!.team_id, player_count: players, payment_rule: rule });
      if (booked) body.booking_id = game!.booking_id;
      else Object.assign(body, { pitch_type: pitchType, preferred_dates: dates, window_start: start, window_end: end });
    } else if (type === 'RECRUIT_MEMBERS') {
      Object.assign(body, { booking_id: game!.booking_id, required_players: needed, ...(fee ? { fee_per_player: fee } : {}) });
    } else {
      Object.assign(body, { party_size: party, preferred_dates: dates, window_start: start, window_end: end, ...(joinPitch ? { pitch_type: joinPitch } : {}) });
    }
    setSaving(true);
    try { onDone((await matchRequests.create(body)).data); }
    catch (reason) { setError(reason); }
    finally { setSaving(false); }
  }

  return <form className="mf-composer" onSubmit={submit} noValidate>
    <div className="mf-composer-main">
      <div className="mf-composer-head"><h2>Gửi yêu cầu</h2><button type="button" className="mf-link" onClick={onClose}>Đóng</button></div>
      <div className="mf-types" role="radiogroup" aria-label="Loại yêu cầu">{(Object.keys(typeNames) as RequestType[]).map(t =>
        <button key={t} type="button" role="radio" aria-checked={type === t} className={type === t ? 'is-on' : ''} onClick={() => pick(t)}>
          <strong>{typeNames[t]}</strong><span>{typeHelp[t]}</span></button>)}
      </div>

      {type === 'FIND_OPPONENT' && <>
        {options.teams.length === 0 ? <p className="mf-hint">Bạn chưa làm đội trưởng đội nào. <a href="#/teams">Tạo đội</a> trước, rồi quay lại tìm đối.</p> : <>
          <label className="mf-field"><span>Đội</span><select value={teamId ?? ''} onChange={e => { const id = Number(e.target.value); setTeamId(id); setPlayers(lastCount(id)); }}>
            {options.teams.map(t => <option key={t.team_id} value={t.team_id}>{t.team_name}</option>)}</select></label>
          <label className="mf-field"><span>Số người đi đá <small>tính cả bạn, sân {size} người cần ít nhất {size}</small></span>
            <input type="number" min={size} max={11} value={players} onChange={e => setPlayers(Math.max(1, Math.min(11, Number(e.target.value) || 1)))} /></label>
          <Segmented label="Sân" value={booked ? 'yes' : 'no'} onChange={v => { setBooked(v === 'yes'); setBookingId(null); }}
            options={[{ value: 'no', label: 'Chưa đặt sân' }, { value: 'yes', label: 'Đã đặt sân' }]} />
        </>}
      </>}

      {((type === 'FIND_OPPONENT' && booked && options.teams.length > 0) || type === 'RECRUIT_MEMBERS') && (games.length === 0
        ? <p className="mf-hint">{type === 'RECRUIT_MEMBERS' ? 'Bạn chưa có lượt đá đã cọc nào còn hơn 1 ngày nữa mới đến giờ.' : 'Chưa có lượt sân đã cọc nào cách hôm nay từ 2 ngày trở lên.'} <a href="#/bookings">Đặt sân</a></p>
        : <label className="mf-field"><span>{type === 'RECRUIT_MEMBERS' ? 'Lượt đá cần thêm người' : 'Lượt sân đã đặt'}</span>
          <select value={bookingId ?? ''} onChange={e => setBookingId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">Chọn lượt…</option>
            {games.map(g => <option key={g.booking_id} value={g.booking_id}>{g.pitch_name} · {slotLabel(g.start_time, g.end_time)}</option>)}
          </select></label>)}

      {((type === 'FIND_OPPONENT' && !booked && options.teams.length > 0) || type === 'LOOK_FOR_TEAM') && <>
        {type === 'FIND_OPPONENT'
          ? <Segmented label="Loại sân" value={pitchType} onChange={setPitchType} options={[{ value: 'PITCH_5', label: pitchNames.PITCH_5 }, { value: 'PITCH_7', label: pitchNames.PITCH_7 }]} />
          : <Segmented<GamePitchType | ''> label="Loại sân" value={joinPitch} onChange={setJoinPitch} options={[{ value: '', label: 'Sân nào cũng được' }, { value: 'PITCH_5', label: pitchNames.PITCH_5 }, { value: 'PITCH_7', label: pitchNames.PITCH_7 }]} />}
        <DayPicker first={firstDay} last={lastDay} value={dates} onChange={setDates} />
        <WindowPicker start={start} end={end} onStart={setStart} onEnd={setEnd} />
      </>}

      {type === 'RECRUIT_MEMBERS' && <div className="mf-pair">
        <label className="mf-field"><span>Cần thêm mấy người</span><input type="number" min={1} max={10} value={needed} onChange={e => setNeeded(Math.max(1, Math.min(10, Number(e.target.value) || 1)))} /></label>
        <label className="mf-field"><span>Chi phí mỗi người (không bắt buộc)</span><input inputMode="numeric" placeholder="VD: 50000" value={fee} onChange={e => setFee(e.target.value.replace(/\D/g, ''))} /></label>
      </div>}
      {type === 'LOOK_FOR_TEAM' && <Segmented label="Đi mấy người" value={party} onChange={setParty} options={[1, 2, 3].map(n => ({ value: n, label: n === 1 ? 'Một mình' : `${n} người` }))} />}

      <div className="mf-pair">
        <label className="mf-field"><span>{type === 'LOOK_FOR_TEAM' ? 'Trình độ của bạn' : type === 'RECRUIT_MEMBERS' ? 'Trình độ trận đấu' : 'Trình độ đội bạn'}</span>
          <select value={skill} onChange={e => setSkill(e.target.value as SkillLevel)}>{(Object.keys(skillNames) as SkillLevel[]).map(s => <option key={s} value={s}>{skillNames[s]}</option>)}</select></label>
        <label className="mf-field"><span>{type === 'FIND_OPPONENT' ? 'Nhận đối thủ' : 'Nhận người chơi'}</span>
          <select value={tolerance} onChange={e => setTolerance(Number(e.target.value))}>{[1, 0, 4].map(t => <option key={t} value={t}>{toleranceNames[t]}</option>)}</select></label>
      </div>
      {type === 'FIND_OPPONENT' && options.teams.length > 0 && <Segmented label="Chia tiền sân" value={rule} onChange={setRule}
        options={[{ value: 'ANY', label: 'Không yêu cầu' }, { value: 'SPLIT_EQUAL', label: ruleNames.SPLIT_EQUAL }, { value: 'LOSER_PAYS_REMAINDER', label: ruleNames.LOSER_PAYS_REMAINDER }]} />}
      <label className="mf-field"><span>Ghi chú (không bắt buộc)</span><textarea rows={2} maxLength={500} value={note} onChange={e => setNote(e.target.value)}
        placeholder={type === 'RECRUIT_MEMBERS' ? 'VD: cần 1 thủ môn, đội mặc áo xanh' : type === 'LOOK_FOR_TEAM' ? 'VD: hay đá hậu vệ' : 'VD: đội mặc áo đỏ'} /></label>
    </div>

    <aside className="mf-summary" aria-live="polite">
      <h3>Hệ thống sẽ</h3>
      <p className="mf-summary-main">{summary}</p>
      <ul>
        {type === 'FIND_OPPONENT' && <li>{booked ? 'Ưu tiên đội chưa có sân để đá trên sân của bạn, không cần cọc thêm.' : `Nếu đối thủ cũng chưa có sân, hệ thống giữ sân và mỗi đội cọc một nửa trong ${options.rules.deposit_hold_hours} giờ.`}</li>}
        {type === 'RECRUIT_MEMBERS' && <li>Người chơi phù hợp được thêm thẳng vào trận, bạn nhận tên và số điện thoại.</li>}
        {type === 'LOOK_FOR_TEAM' && <li>Bạn được ghép vào trận đang thiếu người và nhận số điện thoại đội trưởng.</li>}
        <li>Ghép là chốt, không cần xác nhận lại. {type === 'FIND_OPPONENT' ? 'Chỉ đội trưởng nhận email và thông báo, bạn tự báo lại cho các thành viên.' : 'Bạn nhận email và thông báo ngay khi có kết quả.'}</li>
        <li>Dừng tìm {options.rules.cutoff_hours} giờ trước giờ đá. Không tìm được thì bạn cũng được báo.</li>
      </ul>
      {problem && <p className="mf-problem" role="alert">{problem}</p>}
      <Warning error={error} />
      <button className="mf-submit" type="submit" disabled={saving || (type === 'FIND_OPPONENT' && options.teams.length === 0)}>{saving ? 'Đang gửi…' : 'Gửi yêu cầu'}</button>
    </aside>
  </form>;
}
