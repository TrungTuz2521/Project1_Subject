import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { FormEvent } from 'react';
import { session } from '../../stores/session';
import { login, logout } from '../../services/auth';
import { teamsService } from '../../services/teams';
import { ApiError, errorMessage } from '../../services/api';
import { mockServer, useMocks } from '../../services/client';
import type { MockScenario } from '../../mocks/server';
import type { Team } from '../../types/api';

/** Reference flow: session → GET → render → POST → refresh → field/global errors. */
export function TeamsPage() {
  const current = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  const [teams, setTeams] = useState<Team[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState('');
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [fieldError, setFieldError] = useState('');
  const [formError, setFormError] = useState('');
  const [success, setSuccess] = useState('');
  const [signingIn, setSigningIn] = useState(false);
  const [scenario, setScenario] = useState<MockScenario>('normal');
  const busy = useRef(false);
  const requestSequence = useRef(0);
  const nameInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!current) { setTeams([]); setTotal(0); setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true); setListError(''); setTeams([]);
    teamsService.list(page, controller.signal).then((result) => {
      if (!controller.signal.aborted) { setTeams(result.data); setTotal(result.meta.total); }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setListError(errorMessage(error));
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [current, page, revision]);

  useEffect(() => {
    ++requestSequence.current; busy.current = false;
    setSaving(false); setName(''); setFieldError(''); setFormError(''); setSuccess('');
  }, [current]);

  async function signIn() {
    setSigningIn(true); setFormError('');
    try { await login({ email: 'demo@example.test', password: 'mock-only' }); }
    catch (error) { setFormError(errorMessage(error)); }
    finally { setSigningIn(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy.current || !current) return;
    const teamName = name.trim();
    setFieldError(''); setFormError(''); setSuccess('');
    if (!teamName || teamName.length > 100) { setFieldError('Nhập tên đội từ 1 đến 100 ký tự.'); nameInput.current?.focus(); return; }
    busy.current = true; setSaving(true);
    const sequence = requestSequence.current;
    const token = current.access_token;
    const stillCurrent = () => sequence === requestSequence.current && session.getSnapshot()?.access_token === token;
    try {
      const result = await teamsService.create({ team_name: teamName });
      if (stillCurrent()) {
        setName(''); setSuccess(`Đã tạo đội “${result.data.team_name}”. Bạn là đội trưởng.`);
        setPage(1); setRevision((value) => value + 1);
      }
    } catch (error) {
      if (stillCurrent()) {
        if (error instanceof ApiError && error.fields.team_name) {
          const field = error.fields.team_name;
          setFieldError(Array.isArray(field) ? field.join(' ') : field); nameInput.current?.focus();
        } else setFormError(errorMessage(error));
      }
    } finally {
      if (sequence === requestSequence.current) { busy.current = false; setSaving(false); }
    }
  }
  function changeScenario(value: MockScenario) {
    mockServer?.setScenario(value); setScenario(value); setSuccess(''); setFormError(''); setFieldError('');
    setPage(1); setRevision((revision) => revision + 1);
  }
  const refresh = () => setRevision((value) => value + 1);

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#main"><span className="brand-icon">F</span><span>FOOTBALL<span className="brand-sub">FIELD MANAGEMENT</span></span></a>
      <p className="nav-label">KHÔNG GIAN CỦA BẠN</p>
      <nav aria-label="Điều hướng chính">
        <a className="nav-item" href="#/dashboard"><span>⌂</span> Tổng quan</a>
        <a className="nav-item selected" href="#/teams" aria-current="page"><span>◉</span> Đội bóng của tôi <span className="nav-arrow">↗</span></a>
        <a className="nav-item" href="#/bookings"><span>▦</span> Đặt sân</a>
        <a className="nav-item" href="#/matchmaking"><span>⇄</span> Ghép đội & tìm trận</a>
        <a className="nav-item" href="#/notifications"><span>♧</span> Thông báo</a>
        <a className="nav-item" href="#/profile"><span>◎</span> Hồ sơ cá nhân</a>
      </nav>
      <div className="pitch-art" aria-hidden="true"><div className="center-line" /><div className="center-circle" /><div className="goal goal-top" /><div className="goal goal-bottom" /></div>
      <div className="sidebar-footer"><span className="status-dot" /> Cùng đội. Cùng đam mê.<small>Chọn đội, tìm kèo, ra sân.</small></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><span>Không gian cá nhân <span className="separator">/</span> <strong>Đội bóng</strong></span>
        <div className="identity"><span className="avatar">{current ? current.user.full_name.trim().split(/\s+/).slice(-2).map((word) => word[0]).join('').toLocaleUpperCase() : '•'}</span><span>{current?.user.full_name ?? 'Chưa đăng nhập'}</span>{current && <button className="text-button" onClick={() => { window.dispatchEvent(new Event('app:manual-logout')); logout(); window.location.hash = '/login'; }}>Đăng xuất</button>}</div>
      </header>
      <main id="main">
        <div className="eyebrow">KẾT NỐI TỪ SÂN CỎ</div>
        <div className="page-heading"><div><h1>Đội bóng của tôi<span>.</span></h1><p>Mỗi trận đấu hay bắt đầu từ một đội bóng của riêng bạn.</p></div><span className="page-index">01 / ĐỘI BÓNG</span></div>
        {useMocks && <section className="demo-panel" aria-label="Công cụ dữ liệu mẫu">
          <div><strong><span className="status-dot" /> Chế độ dữ liệu mẫu</strong><p>Chạy độc lập với backend · Dữ liệu được đặt lại khi tải lại trang.</p></div>
          <div className="demo-actions"><label htmlFor="scenario">Tình huống</label><select id="scenario" value={scenario} onChange={(event) => changeScenario(event.target.value as MockScenario)}>
            <option value="normal">Bình thường</option><option value="empty">Danh sách trống</option><option value="server-error">Lỗi máy chủ 500</option><option value="network-error">Mất kết nối</option><option value="validation-error">Lỗi form 422</option>
          </select><button className="small-button" disabled={!current} onClick={() => { mockServer?.expireSession(); refresh(); }}>Thử lỗi token 401</button></div>
        </section>}
        {!current ? <section className="login-state"><span className="large-icon">↗</span><h2>Sẵn sàng trở lại sân?</h2><p>Đăng nhập để xem đội bóng và tạo đội mới.</p>
          {useMocks ? <button className="primary-button" disabled={signingIn} onClick={signIn}>{signingIn ? 'Đang đăng nhập…' : 'Đăng nhập bằng tài khoản mẫu →'}</button>
            : <p className="integration-note">Kết nối màn hình đăng nhập thật với hàm <code>login()</code> trong <code>services/auth.ts</code>. Backend hiện chưa được triển khai.</p>}
          {formError && <p className="error" role="alert">{formError}</p>}
        </section> : <div className="content-grid">
          <section className="teams-section" aria-labelledby="teams-heading" aria-busy={loading}>
            <div className="section-heading"><div><h2 id="teams-heading">Đồng đội của bạn <span className="count-badge">{total}</span></h2><p>Những đội bóng bạn đang đồng hành.</p></div><button className="small-button" onClick={refresh} disabled={loading}>↻ Làm mới</button></div>
            {loading ? <div className="loading-state" role="status"><span className="spinner" /> Đang tải đội bóng…<div className="skeleton" /><div className="skeleton" /></div>
              : listError ? <div className="empty-state error-state" role="alert"><h3>Chưa tải được danh sách</h3><p>{listError}</p><button className="small-button" onClick={refresh}>Thử lại</button></div>
              : teams.length === 0 ? <div className="empty-state"><span className="large-icon">◎</span><h3>{total ? 'Trang này chưa có đội' : 'Đội bóng đầu tiên đang chờ bạn'}</h3><p>Đặt một cái tên, rủ đồng đội và bắt đầu hành trình.</p><button className="small-button" onClick={() => nameInput.current?.focus()}>Tạo đội mới →</button></div>
              : <div className="team-list">{teams.map((team, index) => <article className="team-card" key={team.team_id}>
                <div className={`team-crest crest-${index % 3}`} aria-hidden="true">{team.team_name.split(' ').slice(0, 2).map((word) => word[0]).join('')}</div>
                <div className="team-info"><div className="team-kicker">{team.creation_type === 'AI_RANDOM' ? 'ĐỘI GHÉP TỰ ĐỘNG' : 'ĐỘI CỦA BẠN'}</div><h3>{team.team_name}</h3><p>{team.active_member_count} thành viên <span>·</span> {team.created_by === current.user.user_id ? 'Bạn tạo đội' : 'Đội AI tập hợp'}</p></div>
                <span className={`badge ${team.status === 'ACTIVE' ? '' : 'inactive'}`}>{team.status === 'ACTIVE' ? 'Đang hoạt động' : 'Ngừng hoạt động'}</span>
              </article>)}</div>}
            {!listError && total > 6 && <div className="pagination"><button className="small-button" disabled={loading || page === 1} onClick={() => setPage(page - 1)}>← Trước</button><span>Trang {page} / {Math.ceil(total / 6)}</span><button className="small-button" disabled={loading || page * 6 >= total} onClick={() => setPage(page + 1)}>Sau →</button></div>}
            <div className="field-note"><span>↳</span> Đội do bạn tạo sẽ có bạn làm đội trưởng. Việc tìm đối thủ được thực hiện qua bài đăng riêng.</div>
          </section>
          <aside className="create-panel"><div className="form-symbol" aria-hidden="true">+</div><div className="eyebrow">THÊM MỘT KHỞI ĐẦU</div><h2>Tạo đội bóng mới</h2><p>Một cái tên để cùng nhau ra sân.</p>
            <form onSubmit={submit} noValidate><label htmlFor="team-name">Tên đội bóng <span aria-hidden="true">*</span></label><input ref={nameInput} id="team-name" name="team_name" placeholder="Ví dụ: FC Chiều Thứ Bảy" value={name} maxLength={100} disabled={saving} aria-invalid={!!fieldError} aria-describedby={fieldError ? 'name-error' : 'name-help'} onChange={(event) => { setName(event.target.value); setFieldError(''); }} />
              <div className="input-help" id="name-help"><span>Tên dễ nhớ, tinh thần dễ gắn kết.</span><span>{name.length}/100</span></div>
              {fieldError && <p id="name-error" className="error" role="alert">{fieldError}</p>}
              {formError && <p className="error" role="alert">{formError}</p>}
              {success && <p className="success" role="status">✓ {success}</p>}
              <button className="primary-button create-button" type="submit" disabled={saving}>{saving ? 'Đang tạo đội…' : 'Tạo đội bóng'}<span aria-hidden="true">↗</span></button>
            </form><div className="form-footer">Bạn sẽ trở thành đội trưởng.<br />Có thể tuyển thêm thành viên sau khi tạo đội.</div>
          </aside>
        </div>}
        <footer className="page-footer"><span>FOOTBALL FIELD MANAGEMENT</span><span>Đồng đội hôm nay. Kỷ niệm ngày mai.</span></footer>
      </main>
    </div>
  </div>;
}
