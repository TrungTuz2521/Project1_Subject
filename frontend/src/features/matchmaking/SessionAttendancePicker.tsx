import { useEffect, useState } from 'react';
import { teamsService } from '../../services/teams';
import { formErrorMessage } from '../../services/formErrors';
import type { TeamMember } from '../../types/api';

export function SessionAttendancePicker({ teamId, userId, userName, capacity, userIds, guests, onUsers, onGuests }: {
  teamId: string; userId: number; userName: string; capacity: number; userIds: number[]; guests: string;
  onUsers: (ids: number[]) => void; onGuests: (count: string) => void;
}) {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    setMembers([]); setError('');
    if (!teamId) { setLoading(false); return; }
    setLoading(true);
    teamsService.get(Number(teamId)).then(result => { if (alive) setMembers(result.data.members.filter(m => m.status === 'ACTIVE')); })
      .catch(reason => { if (alive) setError(formErrorMessage(reason)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [teamId]);
  const guestCount = /^\d+$/.test(guests) ? Number(guests) : 0;
  const total = userIds.length + guestCount;
  return <fieldset className="account-panel">
    <legend>Người tham gia buổi đá này</legend>
    <p>Chọn đồng đội có tài khoản sẽ đi đá và khai báo người ngoài ứng dụng. Danh sách thành viên lâu dài của đội được giữ riêng.</p>
    <label className="mm-checkbox"><input type="checkbox" checked disabled /> {userName} (đại diện, đã tính 1 người)</label>
    {loading && <p>Đang tải thành viên của đội…</p>}
    {error && <p role="alert">{error}</p>}
    {members.filter(m => m.user_id !== userId).map(m => <label className="mm-checkbox" key={m.user_id}>
      <input type="checkbox" checked={userIds.includes(m.user_id)} disabled={!userIds.includes(m.user_id) && total >= capacity}
        onChange={e => onUsers(e.target.checked ? [...userIds, m.user_id] : userIds.filter(id => id !== m.user_id))} /> {m.full_name}
    </label>)}
    <div className="form-field"><label htmlFor="post-guests">Số người đi cùng ngoài ứng dụng (không tính các tài khoản đã chọn)</label>
      <input id="post-guests" type="number" min={0} max={Math.max(0, capacity-userIds.length)} step={1} value={guests} onChange={e => onGuests(e.target.value)} required />
    </div>
    <p role="status"><strong>Quân số buổi đá: {total}/{capacity} người</strong> — {userIds.length} người có tài khoản + {guestCount} người ngoài ứng dụng.
      {total < capacity ? ` Còn thiếu ${capacity-total} người.` : total === capacity ? ' Đã đủ người.' : ' Vượt số người của loại sân.'}</p>
  </fieldset>;
}
