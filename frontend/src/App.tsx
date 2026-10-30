import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { TeamsPage } from './features/matchmaking/TeamsPage';
import { getCurrentUser, login, logout, register, updateCurrentUser } from './services/auth';
import { errorMessage, ApiError } from './services/api';
import { useMocks } from './services/client';
import { session } from './stores/session';
import type { ProfileUpdate, RegisterRequest, SkillLevel, UserSelf } from './types/api';

const routes = ['/login', '/register', '/dashboard', '/profile', '/teams', '/bookings', '/matchmaking', '/notifications'] as const;
type Route = typeof routes[number];
const skillLabels: Record<SkillLevel, string> = {
  BEGINNER: 'Mới chơi', AMATEUR: 'Phong trào', INTERMEDIATE: 'Trung bình', SEMI_PRO: 'Bán chuyên', PRO: 'Chuyên nghiệp',
};
function readRoute(): Route {
  const value = window.location.hash.replace(/^#/, '') || '/login';
  return routes.includes(value as Route) ? value as Route : '/login';
}
function go(path: Route) {
  if (window.location.hash === `#${path}`) window.dispatchEvent(new HashChangeEvent('hashchange'));
  else window.location.hash = path;
}
function initials(name: string) {
  return name.trim().split(/\s+/).slice(-2).map((part) => part[0]?.toLocaleUpperCase() ?? '').join('') || 'U';
}
function fieldError(error: unknown, field: string) {
  if (!(error instanceof ApiError)) return '';
  const value = error.fields[field];
  return Array.isArray(value) ? value.join(' ') : value ?? '';
}

export default function App() {
  const current = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  const [route, setRoute] = useState<Route>(readRoute);
  const [notice, setNotice] = useState('');
  const previousSession = useRef(Boolean(session.getSnapshot()));
  const manualLogout = useRef(false);

  useEffect(() => {
    const onHashChange = () => setRoute(readRoute());
    const onManualLogout = () => { manualLogout.current = true; setNotice('Bạn đã đăng xuất khỏi hệ thống.'); };
    window.addEventListener('hashchange', onHashChange);
    window.addEventListener('app:manual-logout', onManualLogout);
    return () => {
      window.removeEventListener('hashchange', onHashChange);
      window.removeEventListener('app:manual-logout', onManualLogout);
    };
  }, []);

  useEffect(() => {
    if (previousSession.current && !current) {
      if (!manualLogout.current) setNotice('Phiên đăng nhập đã hết hạn hoặc không còn hợp lệ. Vui lòng đăng nhập lại.');
      manualLogout.current = false;
      if (window.location.hash !== '#/login') window.location.hash = '/login';
      else setRoute('/login');
    }
    previousSession.current = Boolean(current);
  }, [current]);

  const onLogout = () => {
    manualLogout.current = true;
    setNotice('Bạn đã đăng xuất khỏi hệ thống.');
    logout();
    go('/login');
  };

  if (!current) {
    return <AuthPage mode={route === '/register' ? 'register' : 'login'} notice={notice} clearNotice={() => setNotice('')}
      onNavigate={go} onSuccess={(message) => { setNotice(message); go('/login'); }} onLogin={() => { setNotice(''); go('/dashboard'); }} />;
  }

  // Public auth URLs should never display an authenticated user a login form.
  const activeRoute: Route = route === '/login' || route === '/register' ? '/dashboard' : route;
  if (activeRoute === '/teams') return <TeamsPage />;
  if (activeRoute === '/profile') return <AppShell current={current.user} route={activeRoute} onLogout={onLogout}><ProfilePage currentUser={current.user} /></AppShell>;
  if (activeRoute === '/bookings' || activeRoute === '/matchmaking' || activeRoute === '/notifications') {
    const pages = {
      '/bookings': { title: 'Đặt sân', number: '03', description: 'Tìm sân phù hợp và quản lý lịch đặt sân của bạn.' },
      '/matchmaking': { title: 'Ghép đội và tìm trận', number: '04', description: 'Tìm đối thủ, tìm đồng đội và theo dõi đề xuất ghép trận.' },
      '/notifications': { title: 'Thông báo', number: '05', description: 'Theo dõi xác nhận trận đấu, lịch sân và trạng thái thanh toán.' },
    } as const;
    return <AppShell current={current.user} route={activeRoute} onLogout={onLogout}><ComingSoonPage {...pages[activeRoute]} /></AppShell>;
  }
  return <AppShell current={current.user} route="/dashboard" onLogout={onLogout}><DashboardPage user={current.user} /></AppShell>;
}

function AuthPage({ mode, notice, clearNotice, onNavigate, onSuccess, onLogin }: {
  mode: 'login' | 'register'; notice: string; clearNotice: () => void;
  onNavigate: (path: Route) => void; onSuccess: (message: string) => void; onLogin: () => void;
}) {
  const isRegister = mode === 'register';
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [skillLevel, setSkillLevel] = useState<SkillLevel>('INTERMEDIATE');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => { setError(''); setErrors({}); }, [mode]);

  async function submit(event: FormEvent) {
    event.preventDefault(); clearNotice(); setError(''); setErrors({});
    const nextErrors: Record<string, string> = {};
    const normalizedEmail = email.trim().toLocaleLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) nextErrors.email = 'Vui lòng nhập email hợp lệ.';
    if (!password) nextErrors.password = 'Vui lòng nhập mật khẩu.';
    if (isRegister) {
      if (fullName.trim().length < 2 || fullName.trim().length > 100) nextErrors.full_name = 'Họ tên cần từ 2 đến 100 ký tự.';
      const passwordBytes = new TextEncoder().encode(password).length;
      if (passwordBytes < 8 || passwordBytes > 72) nextErrors.password = 'Mật khẩu phải dài từ 8 đến 72 byte UTF-8.';
      if (confirmPassword !== password) nextErrors.confirm_password = 'Mật khẩu nhập lại chưa khớp.';
      if (phone.trim().length > 30) nextErrors.phone = 'Số điện thoại quá dài.';
    }
    if (Object.keys(nextErrors).length) { setErrors(nextErrors); return; }
    setBusy(true);
    try {
      if (isRegister) {
        const payload: RegisterRequest = { full_name: fullName.trim(), email: normalizedEmail, password,
          ...(phone.trim() ? { phone: phone.trim() } : {}), skill_level: skillLevel };
        await register(payload);
        setFullName(''); setPhone(''); setPassword(''); setConfirmPassword('');
        onSuccess('Đăng ký thành công! Hãy đăng nhập bằng tài khoản bạn vừa tạo.');
      } else {
        await login({ email: normalizedEmail, password });
        onLogin();
      }
    } catch (reason) {
      setError(errorMessage(reason));
      const names = isRegister ? ['full_name', 'email', 'password', 'phone', 'skill_level'] : ['email', 'password'];
      setErrors(Object.fromEntries(names.map((name) => [name, fieldError(reason, name)]).filter(([, value]) => value)));
    } finally { setBusy(false); }
  }

  async function demoLogin() {
    setEmail('demo@example.test'); setPassword('mock-only'); setError(''); setBusy(true);
    try { await login({ email: 'demo@example.test', password: 'mock-only' }); onLogin(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }

  return <div className="auth-screen">
    <aside className="auth-visual">
      <a className="auth-brand" href="#/login"><span className="auth-brand-mark">F</span><span>FOOTBALL<small>FIELD MANAGEMENT</small></span></a>
      <div className="auth-visual-copy"><span className="auth-eyebrow">CÙNG ĐỘI · CÙNG ĐAM MÊ</span><h1>Mỗi trận đấu hay bắt đầu từ <em>một kết nối.</em></h1><p>Đặt sân, tìm đồng đội và kết nối với những trận cầu phù hợp với bạn.</p></div>
      <div className="auth-pitch" aria-hidden="true"><div /><span /></div>
      <p className="auth-visual-footer">FOOTBALL FIELD MANAGEMENT <span>•</span> ỨNG DỤNG KẾT NỐI SÂN CỎ</p>
    </aside>
    <main className="auth-main">
      <div className="auth-top-note">{isRegister ? 'BẮT ĐẦU HÀNH TRÌNH' : 'CHÀO MỪNG BẠN TRỞ LẠI'}</div>
      <section className="auth-card">
        <div className="auth-card-title"><span className="auth-icon">{isRegister ? '＋' : '↗'}</span><div><h2>{isRegister ? 'Tạo tài khoản' : 'Đăng nhập'}</h2><p>{isRegister ? 'Tham gia cộng đồng bóng đá phong trào.' : 'Đăng nhập để tiếp tục hành trình trên sân cỏ.'}</p></div></div>
        {notice && <div className="notice-success" role="status">{notice}<button type="button" aria-label="Đóng thông báo" onClick={clearNotice}>×</button></div>}
        {useMocks && <div className="demo-hint"><span className="status-dot" /> Chế độ demo · Chưa cần kết nối backend</div>}
        <form className="auth-form" onSubmit={submit} noValidate>
          {isRegister && <div className="form-field"><label htmlFor="auth-name">Họ và tên <span>*</span></label><input id="auth-name" autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Nguyễn Văn An" aria-invalid={!!errors.full_name} />{errors.full_name && <small className="field-error">{errors.full_name}</small>}</div>}
          <div className="form-field"><label htmlFor="auth-email">Email <span>*</span></label><input id="auth-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ban@example.com" aria-invalid={!!errors.email} />{errors.email && <small className="field-error">{errors.email}</small>}</div>
          {isRegister && <div className="form-row">
            <div className="form-field"><label htmlFor="auth-phone">Số điện thoại</label><input id="auth-phone" type="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="09xx xxx xxx" aria-invalid={!!errors.phone} />{errors.phone && <small className="field-error">{errors.phone}</small>}</div>
            <div className="form-field"><label htmlFor="auth-skill">Trình độ</label><select id="auth-skill" value={skillLevel} onChange={(e) => setSkillLevel(e.target.value as SkillLevel)}>{Object.entries(skillLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
          </div>}
          <div className="form-field"><label htmlFor="auth-password">Mật khẩu <span>*</span></label><div className="password-wrap"><input id="auth-password" type={showPassword ? 'text' : 'password'} autoComplete={isRegister ? 'new-password' : 'current-password'} value={password} onChange={(e) => setPassword(e.target.value)} placeholder={isRegister ? 'Tối thiểu 8 ký tự' : 'Nhập mật khẩu'} aria-invalid={!!errors.password} /><button type="button" className="show-password" onClick={() => setShowPassword((value) => !value)}>{showPassword ? 'Ẩn' : 'Hiện'}</button></div>{errors.password && <small className="field-error">{errors.password}</small>}</div>
          {isRegister && <div className="form-field"><label htmlFor="auth-confirm">Nhập lại mật khẩu <span>*</span></label><input id="auth-confirm" type={showPassword ? 'text' : 'password'} autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Nhập lại mật khẩu" aria-invalid={!!errors.confirm_password} />{errors.confirm_password && <small className="field-error">{errors.confirm_password}</small>}</div>}
          {error && <div className="notice-error" role="alert">{error}</div>}
          <button className="auth-submit" type="submit" disabled={busy}>{busy ? 'Đang xử lý…' : isRegister ? 'Tạo tài khoản' : 'Đăng nhập'}<span aria-hidden="true">↗</span></button>
        </form>
        {useMocks && !isRegister && <button type="button" className="demo-login-button" disabled={busy} onClick={demoLogin}>Đăng nhập nhanh bằng tài khoản mẫu</button>}
        <p className="auth-switch">{isRegister ? 'Đã có tài khoản?' : 'Chưa có tài khoản?'} <button type="button" onClick={() => { clearNotice(); setError(''); onNavigate(isRegister ? '/login' : '/register'); }}>{isRegister ? 'Đăng nhập' : 'Đăng ký ngay'}</button></p>
        <p className="auth-terms">Bằng việc tiếp tục, bạn đồng ý tuân thủ các quy định sử dụng của hệ thống.</p>
      </section>
      <footer className="auth-footer">© FOOTBALL FIELD MANAGEMENT <span>•</span> KẾT NỐI ĐAM MÊ BÓNG ĐÁ</footer>
    </main>
  </div>;
}

function AppShell({ current, route, onLogout, children }: { current: UserSelf; route: Route; onLogout: () => void; children: ReactNode }) {
  const navItems: { path: Route; icon: string; label: string }[] = [
    { path: '/dashboard', icon: '⌂', label: 'Tổng quan' }, { path: '/teams', icon: '♧', label: 'Đội bóng của tôi' },
    { path: '/bookings', icon: '▦', label: 'Đặt sân' }, { path: '/matchmaking', icon: '⇄', label: 'Ghép đội & tìm trận' },
    { path: '/notifications', icon: '♧', label: 'Thông báo' }, { path: '/profile', icon: '◎', label: 'Hồ sơ cá nhân' },
  ];
  const title = navItems.find((item) => item.path === route)?.label ?? 'Tổng quan';
  return <div className="account-shell">
    <aside className="account-sidebar">
      <a href="#/dashboard" className="account-brand"><span className="account-brand-mark">F</span><span>FOOTBALL<small>FIELD MANAGEMENT</small></span></a>
      <div className="account-side-label">KHÔNG GIAN CỦA BẠN</div>
      <nav className="account-nav" aria-label="Điều hướng chính">{navItems.map((item) => <a key={item.path} href={`#${item.path}`} className={route === item.path ? 'account-nav-item active' : 'account-nav-item'} aria-current={route === item.path ? 'page' : undefined}><span className="account-nav-icon">{item.icon}</span><span>{item.label}</span>{route === item.path && <span className="account-nav-arrow">↗</span>}</a>)}</nav>
      <div className="account-sidebar-bottom"><div className="account-mini-pitch"><span /></div><p><i /> Cùng đội. Cùng đam mê.</p><small>Chọn đội, tìm kèo, ra sân.</small></div>
    </aside>
    <div className="account-workspace">
      <header className="account-topbar"><div className="account-breadcrumb">Không gian cá nhân <span>/</span> <strong>{title}</strong></div><div className="account-user"><span className="account-avatar">{initials(current.full_name)}</span><span className="account-user-name">{current.full_name}</span><button onClick={onLogout}>Đăng xuất ↗</button></div></header>
      <main className="account-main">{children}<footer className="account-footer"><span>FOOTBALL FIELD MANAGEMENT</span><span>Đồng đội hôm nay. Kỷ niệm ngày mai.</span></footer></main>
    </div>
  </div>;
}

function DashboardPage({ user }: { user: UserSelf }) {
  return <>
    <div className="account-eyebrow">KẾT NỐI TỪ SÂN CỎ</div>
    <div className="account-page-heading"><div><h1>Xin chào, {user.full_name.split(/\s+/).slice(-1)[0]}<span>.</span></h1><p>Quản lý hoạt động bóng đá của bạn tại một nơi.</p></div><span className="account-page-index">01 / TỔNG QUAN</span></div>
    <section className="welcome-panel"><div><span className="welcome-kicker">SẴN SÀNG RA SÂN?</span><h2>Mỗi trận đấu hay bắt đầu từ một kết nối.</h2><p>Hoàn thiện hồ sơ, tạo đội bóng hoặc tìm trận phù hợp với trình độ của bạn.</p><div className="welcome-actions"><a className="account-primary-button" href="#/teams">Đến đội bóng của tôi ↗</a><a className="account-secondary-button" href="#/profile">Hoàn thiện hồ sơ</a></div></div><div className="welcome-decoration" aria-hidden="true"><div className="welcome-ball">F</div><span>PLAY TOGETHER</span></div></section>
    <div className="account-section-heading"><div><h2>Lối tắt của bạn</h2><p>Truy cập nhanh các chức năng chính trong hệ thống.</p></div></div>
    <section className="shortcut-grid">
      <a href="#/profile" className="shortcut-card"><span className="shortcut-icon">◎</span><span className="shortcut-label">TÀI KHOẢN</span><strong>Hồ sơ cá nhân</strong><p>Cập nhật tên, số điện thoại và trình độ thi đấu.</p><span className="shortcut-arrow">↗</span></a>
      <a href="#/teams" className="shortcut-card"><span className="shortcut-icon">♧</span><span className="shortcut-label">ĐỒNG ĐỘI</span><strong>Đội bóng của tôi</strong><p>Xem đội hiện có hoặc tạo đội bóng mới.</p><span className="shortcut-arrow">↗</span></a>
      <a href="#/bookings" className="shortcut-card"><span className="shortcut-icon">▦</span><span className="shortcut-label">LỊCH SÂN</span><strong>Đặt sân</strong><p>Khu vực dành cho luồng tìm sân và đặt lịch.</p><span className="shortcut-arrow">↗</span></a>
      <a href="#/matchmaking" className="shortcut-card"><span className="shortcut-icon">⇄</span><span className="shortcut-label">GHÉP TRẬN</span><strong>Ghép đội & tìm trận</strong><p>Tìm đối thủ hoặc người chơi phù hợp.</p><span className="shortcut-arrow">↗</span></a>
    </section>
    <div className="account-notice"><span>i</span><div><strong>Thông tin phiên làm việc</strong><p>Tài khoản hiện tại có quyền <b>{currentRoleLabel(user.role)}</b>. Vì lý do bảo mật, phiên đăng nhập có thời hạn tối đa 60 phút; sau khi hết hạn, bạn cần đăng nhập lại.</p></div></div>
  </>;
}
function currentRoleLabel(role: UserSelf['role']) { return role === 'ADMIN' ? 'Quản trị viên' : 'Người chơi'; }

function ProfilePage({ currentUser }: { currentUser: UserSelf }) {
  const [profile, setProfile] = useState<UserSelf>(currentUser);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const token = session.getSnapshot()?.access_token;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    getCurrentUser(controller.signal).then(setProfile).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(errorMessage(reason));
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [token]);

  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setSuccess(''); setErrors({});
    const nextErrors: Record<string, string> = {};
    if (profile.full_name.trim().length < 2 || profile.full_name.trim().length > 100) nextErrors.full_name = 'Họ tên cần từ 2 đến 100 ký tự.';
    if ((profile.phone ?? '').trim().length > 30) nextErrors.phone = 'Số điện thoại quá dài.';
    if (Object.keys(nextErrors).length) { setErrors(nextErrors); return; }
    const payload: ProfileUpdate = { full_name: profile.full_name.trim(), phone: profile.phone?.trim() || null, skill_level: profile.skill_level };
    setSaving(true);
    try {
      const updated = await updateCurrentUser(payload); setProfile(updated); setSuccess('Đã lưu thay đổi hồ sơ.');
    } catch (reason) {
      setError(errorMessage(reason));
      setErrors(Object.fromEntries(['full_name', 'phone', 'skill_level'].map((name) => [name, fieldError(reason, name)]).filter(([, value]) => value)));
    } finally { setSaving(false); }
  }

  return <>
    <div className="account-eyebrow">TÀI KHOẢN CỦA BẠN</div>
    <div className="account-page-heading"><div><h1>Hồ sơ cá nhân<span>.</span></h1><p>Thông tin được sử dụng để kết nối với đội bóng và trận đấu.</p></div><span className="account-page-index">02 / TÀI KHOẢN</span></div>
    {loading ? <div className="account-panel account-loading"><span className="spinner" /> Đang tải thông tin hồ sơ…</div> : <div className="profile-layout">
      <section className="profile-summary"><div className="profile-avatar">{initials(profile.full_name)}</div><h2>{profile.full_name}</h2><p>{profile.email}</p><span className="profile-role">{currentRoleLabel(profile.role)}</span><div className="profile-summary-divider" /><div className="profile-summary-line"><span>Trạng thái</span><strong><i /> {profile.status === 'ACTIVE' ? 'Đang hoạt động' : profile.status === 'BANNED' ? 'Bị khóa' : 'Ngừng hoạt động'}</strong></div><div className="profile-summary-line"><span>Trình độ</span><strong>{skillLabels[profile.skill_level]}</strong></div></section>
      <section className="profile-form-card"><div className="profile-form-heading"><div><h2>Thông tin tài khoản</h2><p>Chỉ chỉnh sửa các trường được phép theo API.</p></div><span>✎</span></div>
        {error && <div className="notice-error" role="alert">{error}</div>}{success && <div className="notice-success" role="status">{success}</div>}
        <form className="profile-form" onSubmit={submit} noValidate>
          <div className="form-field"><label htmlFor="profile-name">Họ và tên <span>*</span></label><input id="profile-name" value={profile.full_name} onChange={(e) => setProfile((value) => ({ ...value, full_name: e.target.value }))} aria-invalid={!!errors.full_name} />{errors.full_name && <small className="field-error">{errors.full_name}</small>}</div>
          <div className="form-field"><label htmlFor="profile-email">Email</label><input id="profile-email" value={profile.email} disabled /><small className="input-caption">Email không thể thay đổi bằng API hồ sơ hiện tại.</small></div>
          <div className="form-row"><div className="form-field"><label htmlFor="profile-phone">Số điện thoại</label><input id="profile-phone" type="tel" value={profile.phone ?? ''} onChange={(e) => setProfile((value) => ({ ...value, phone: e.target.value }))} placeholder="Chưa cập nhật" aria-invalid={!!errors.phone} />{errors.phone && <small className="field-error">{errors.phone}</small>}</div><div className="form-field"><label htmlFor="profile-skill">Trình độ thi đấu</label><select id="profile-skill" value={profile.skill_level} onChange={(e) => setProfile((value) => ({ ...value, skill_level: e.target.value as SkillLevel }))}>{Object.entries(skillLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div></div>
          <div className="profile-actions"><button className="account-secondary-button" type="button" onClick={() => { setProfile(currentUser); setError(''); setSuccess(''); setErrors({}); }}>Khôi phục ban đầu</button><button className="account-primary-button" type="submit" disabled={saving}>{saving ? 'Đang lưu…' : 'Lưu thay đổi ↗'}</button></div>
        </form>
      </section>
    </div>}
  </>;
}

function ComingSoonPage({ title, number, description }: { title: string; number: string; description: string }) {
  return <>
    <div className="account-eyebrow">MỞ RỘNG HỆ THỐNG</div>
    <div className="account-page-heading"><div><h1>{title}<span>.</span></h1><p>{description}</p></div><span className="account-page-index">{number} / MODULE</span></div>
    <section className="account-panel coming-soon"><span className="coming-soon-icon">⌁</span><span className="welcome-kicker">ĐANG CHỜ TÍCH HỢP</span><h2>Khung điều hướng đã sẵn sàng.</h2><p>Module nghiệp vụ này chưa được kết nối ở bản hiện tại. Màn hình không tạo dữ liệu giả và không hiển thị giao dịch giả thành công.</p><a className="account-primary-button" href="#/dashboard">Quay về tổng quan ↗</a></section>
  </>;
}
