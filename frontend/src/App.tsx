import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { ChangePasswordForm } from './features/auth/ChangePasswordForm';
import { GoogleSignIn } from './features/auth/GoogleSignIn';
import { TeamsPage } from './features/matchmaking/TeamsPage';
import { MatchFindPage } from './features/matchfind/MatchFindPage';
import { NotificationsPage } from './features/matchfind/NotificationsPage';
import { FieldApp } from './features/field-management/FieldApp';
import { AdminShell } from './features/admin/AdminShell';
import { PlayerShell, PublicShell } from './features/player/PlayerShell';
import { PlayerHome } from './features/player/PlayerHome';
import { PitchesPage } from './features/pitches/PitchesPage';
import { ForgotPasswordPage, ResetPasswordPage } from './features/auth/PasswordReset';
import type { AdminRoute } from './features/admin/AdminShell';
import { getCurrentUser, keepSessionAlive, login, logout, register, updateCurrentUser } from './services/auth';
import { errorMessage, ApiError } from './services/api';
import { useMocks } from './services/client';
import { session } from './stores/session';
import { selectedBookingFromHash } from './services/bookingNavigation';
import type { ProfileUpdate, RegisterRequest, SkillLevel, UserSelf } from './types/api';

const routes = ['/login', '/register', '/forgot-password', '/reset-password', '/dashboard', '/profile', '/teams', '/bookings', '/my-bookings', '/admin/bookings', '/admin/pitches', '/admin/balance', '/admin/revenue', '/admin/statistics', '/admin/match-requests', '/matchmaking', '/notifications'] as const;
type Route = typeof routes[number];
const skillLabels: Record<SkillLevel, string> = {
  BEGINNER: 'Mới chơi', AMATEUR: 'Phong trào', INTERMEDIATE: 'Trung bình', SEMI_PRO: 'Bán chuyên', PRO: 'Chuyên nghiệp',
};
function readRoute(): Route {
  const value = window.location.hash.replace(/^#/, '').split('?')[0] || '/bookings';
  return routes.includes(value as Route) ? value as Route : '/bookings';
}
function go(path: Route) {
  if (window.location.hash === `#${path}`) window.dispatchEvent(new HashChangeEvent('hashchange'));
  else window.location.hash = path;
}
function hasBookingIntent() { try { return Boolean(sessionStorage.getItem('ffm.booking-intent')); } catch { return false; } }
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
  const [bookingTarget, setBookingTarget] = useState(() => selectedBookingFromHash(window.location.hash));
  const [notice, setNotice] = useState('');
  const previousSession = useRef(Boolean(session.getSnapshot()));
  const manualLogout = useRef(false);

  useEffect(() => {
    const onHashChange = () => { setRoute(readRoute()); setBookingTarget(selectedBookingFromHash(window.location.hash)); };
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

  // Renew the token while someone is signed in, so a shift is not interrupted every hour.
  const signedIn = Boolean(current);
  useEffect(() => (signedIn && !useMocks ? keepSessionAlive() : undefined), [signedIn]);

  // Admin accounts cannot use player features (the API answers 403), so they never land on them.
  const isAdmin = current?.user.role === 'ADMIN';
  useEffect(() => {
    if (isAdmin && !(route === '/dashboard' || route === '/profile' || route.startsWith('/admin/') || route === '/login' || route === '/register')) go('/dashboard');
  }, [isAdmin, route]);

  const onLogout = () => {
    manualLogout.current = true;
    setNotice('Bạn đã đăng xuất khỏi hệ thống.');
    logout();
    go('/login');
  };

  // Password recovery works signed in or not: the email link may be opened anywhere.
  if (route === '/forgot-password') return <ForgotPasswordPage />;
  if (route === '/reset-password') {
    return <ResetPasswordPage onDone={(message) => { manualLogout.current = true; logout(); setNotice(message); go('/login'); }} />;
  }
  if (!current && route === '/bookings') {
    return <PublicShell><div className="huy-module"><PitchesPage signedIn={false} onBooked={() => {}} /></div></PublicShell>;
  }
  if (!current) {
    return <AuthPage mode={route === '/register' ? 'register' : 'login'} notice={notice} clearNotice={() => setNotice('')}
      onNavigate={go} onSuccess={(message) => { setNotice(message); go('/login'); }} onLogin={() => { setNotice(''); if (hasBookingIntent()) go('/bookings'); else if(route!=='/my-bookings' && route!=='/notifications' && route!=='/matchmaking') go('/dashboard'); }} />;
  }

  // Public auth URLs should never display an authenticated user a login form.
  const activeRoute: Route = route === '/login' || route === '/register' ? '/dashboard' : route;
  if (current.user.role === 'ADMIN') {
    const adminTabs = {
      '/dashboard': 'adminDashboard', '/admin/bookings': 'adminBookings', '/admin/pitches': 'adminPitches',
      '/admin/balance': 'settlement', '/admin/revenue': 'revenue', '/admin/statistics': 'statistics', '/admin/match-requests': 'matchRequests',
    } as const;
    const adminRoute = (activeRoute in adminTabs || activeRoute === '/profile' ? activeRoute : '/dashboard') as AdminRoute;
    return <AdminShell current={current.user} route={adminRoute} onLogout={onLogout}>
      {adminRoute === '/profile'
        ? <ProfilePage currentUser={current.user} onPasswordChanged={() => {
            manualLogout.current = true; setNotice('Đổi mật khẩu thành công. Vui lòng đăng nhập lại bằng mật khẩu mới.'); logout(); go('/login');
          }} />
        : <FieldApp key={current.user.user_id} tab={adminTabs[adminRoute as keyof typeof adminTabs]} selectedBookingId={bookingTarget} />}
    </AdminShell>;
  }
  if (activeRoute === '/teams') return <AppShell current={current.user} route={activeRoute} onLogout={onLogout}><TeamsPage /></AppShell>;
  if (activeRoute === '/matchmaking') return <AppShell current={current.user} route={activeRoute} onLogout={onLogout}><MatchFindPage user={current.user} /></AppShell>;
  if (activeRoute === '/notifications') return <AppShell current={current.user} route={activeRoute} onLogout={onLogout}><NotificationsPage /></AppShell>;
  if (activeRoute === '/profile') return <AppShell current={current.user} route={activeRoute} onLogout={onLogout}><ProfilePage currentUser={current.user} onPasswordChanged={()=>{
    manualLogout.current=true;setNotice('Đổi mật khẩu thành công. Vui lòng đăng nhập lại bằng mật khẩu mới.');logout();go('/login');
  }} /></AppShell>;
  const fieldTabs = {
    '/bookings': 'pitches', '/my-bookings': 'bookings', '/admin/bookings': 'adminBookings',
    '/admin/pitches': 'adminPitches', '/admin/balance': 'settlement', '/admin/revenue': 'revenue',
    '/admin/statistics': 'statistics',
  } as const;
  if (activeRoute in fieldTabs) {
    const allowed = !activeRoute.startsWith('/admin/'); // Admins were routed to AdminShell above.
    return <AppShell current={current.user} route={activeRoute} onLogout={onLogout}>
      {allowed ? <FieldApp key={current.user.user_id} tab={fieldTabs[activeRoute as keyof typeof fieldTabs]} selectedBookingId={bookingTarget} />
        : <section role="alert" className="notice-error">Bạn không có quyền truy cập chức năng quản trị.</section>}
    </AppShell>;
  }
  return <AppShell current={current.user} route="/dashboard" onLogout={onLogout}><PlayerHome user={current.user} /></AppShell>;
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
  const [remember, setRemember] = useState(false);
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
        await login({ email: normalizedEmail, password }, remember);
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
  async function demoCaptainLogin() {
    setEmail('captain@example.test'); setPassword('mock-only'); setError(''); setBusy(true);
    try { await login({ email: 'captain@example.test', password: 'mock-only' }); onLogin(); }
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
          {!isRegister && <p className="forgot-link"><a href="#/forgot-password">Quên mật khẩu?</a></p>}
          {!isRegister && <label className="remember-me"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> Ghi nhớ đăng nhập trên máy này<small>Chỉ chọn trên máy riêng hoặc máy quầy của sân.</small></label>}
          {error && <div className="notice-error" role="alert">{error}</div>}
          <button className="auth-submit" type="submit" disabled={busy}>{busy ? 'Đang xử lý…' : isRegister ? 'Tạo tài khoản' : 'Đăng nhập'}<span aria-hidden="true">↗</span></button>
        </form>
        {!useMocks && !isRegister && <GoogleSignIn password={password} disabled={busy} onSuccess={onLogin} />}
        {useMocks && !isRegister && <><button type="button" className="demo-login-button" disabled={busy} onClick={demoLogin}>Đăng nhập nhanh bằng tài khoản mẫu</button><button type="button" className="demo-login-button" disabled={busy} onClick={demoCaptainLogin}>Thử tài khoản đội trưởng mẫu</button></>}
        <p className="auth-switch"><a href="#/bookings">Xem sân, giá và giờ trống không cần đăng nhập →</a></p>
        <p className="auth-switch">{isRegister ? 'Đã có tài khoản?' : 'Chưa có tài khoản?'} <button type="button" onClick={() => { clearNotice(); setError(''); onNavigate(isRegister ? '/login' : '/register'); }}>{isRegister ? 'Đăng nhập' : 'Đăng ký ngay'}</button></p>
        <p className="auth-terms">Bằng việc tiếp tục, bạn đồng ý tuân thủ các quy định sử dụng của hệ thống.</p>
      </section>
      <footer className="auth-footer">© FOOTBALL FIELD MANAGEMENT <span>•</span> KẾT NỐI ĐAM MÊ BÓNG ĐÁ</footer>
    </main>
  </div>;
}

/** Player pages share one shell: grouped navigation, venue phone, and a tab bar on phones. */
function AppShell({ current, route, onLogout, children }: { current: UserSelf; route: Route; onLogout: () => void; children: ReactNode }) {
  return <PlayerShell current={current} route={route} onLogout={onLogout}>{children}</PlayerShell>;
}

function currentRoleLabel(role: UserSelf['role']) { return role === 'ADMIN' ? 'Quản trị viên' : 'Người chơi'; }

function ProfilePage({ currentUser, onPasswordChanged }: { currentUser: UserSelf; onPasswordChanged: () => void }) {
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
    if ((profile.phone ?? '').trim().length > 20) nextErrors.phone = 'Số điện thoại quá dài.';
    if (Object.keys(nextErrors).length) { setErrors(nextErrors); return; }
    const refund = [profile.refund_bank_name, profile.refund_account_no, profile.refund_account_name].map(v => (v ?? '').trim());
    if (refund.some(Boolean) && !refund.every(Boolean)) { setErrors({ refund_account_no: 'Điền đủ ngân hàng, số tài khoản và tên chủ tài khoản, hoặc để trống cả ba.' }); return; }
    const payload: ProfileUpdate = { full_name: profile.full_name.trim(), phone: profile.phone?.trim() || null, skill_level: profile.skill_level,
      refund_bank_name: refund[0], refund_account_no: refund[1], refund_account_name: refund[2] };
    setSaving(true);
    try {
      const updated = await updateCurrentUser(payload); setProfile(updated); setSuccess('Đã lưu thay đổi hồ sơ.');
    } catch (reason) {
      setError(errorMessage(reason));
      setErrors(Object.fromEntries(['full_name', 'phone', 'skill_level', 'refund_bank_name', 'refund_account_no', 'refund_account_name'].map((name) => [name, fieldError(reason, name)]).filter(([, value]) => value)));
    } finally { setSaving(false); }
  }

  return <>
    <div className="account-eyebrow">TÀI KHOẢN CỦA BẠN</div>
    <div className="account-page-heading"><div><h1>Hồ sơ cá nhân<span>.</span></h1><p>Thông tin được sử dụng để kết nối với đội bóng và trận đấu.</p></div><span className="account-page-index">02 / TÀI KHOẢN</span></div>
    {loading ? <div className="account-panel account-loading"><span className="spinner" /> Đang tải thông tin hồ sơ…</div> : <div className="profile-layout">
      <section className="profile-summary"><div className="profile-avatar">{initials(profile.full_name)}</div><h2>{profile.full_name}</h2><p>{profile.email}</p><span className="profile-role">{currentRoleLabel(profile.role)}</span><div className="profile-summary-divider" /><div className="profile-summary-line"><span>Trạng thái</span><strong><i /> {profile.status === 'ACTIVE' ? 'Đang hoạt động' : profile.status === 'BANNED' ? 'Bị khóa' : 'Ngừng hoạt động'}</strong></div><div className="profile-summary-line"><span>Trình độ</span><strong>{skillLabels[profile.skill_level]}</strong></div></section>
      <section className="profile-form-card"><div className="profile-form-heading"><div><h2>Thông tin tài khoản</h2></div><span>✎</span></div>
        {error && <div className="notice-error" role="alert">{error}</div>}{success && <div className="notice-success" role="status">{success}</div>}
        <form className="profile-form" onSubmit={submit} noValidate>
          <div className="form-field"><label htmlFor="profile-name">Họ và tên <span>*</span></label><input id="profile-name" value={profile.full_name} onChange={(e) => setProfile((value) => ({ ...value, full_name: e.target.value }))} aria-invalid={!!errors.full_name} />{errors.full_name && <small className="field-error">{errors.full_name}</small>}</div>
          <div className="form-field"><label htmlFor="profile-email">Email</label><input id="profile-email" value={profile.email} disabled /></div>
          <div className="form-row"><div className="form-field"><label htmlFor="profile-phone">Số điện thoại</label><input id="profile-phone" type="tel" value={profile.phone ?? ''} onChange={(e) => setProfile((value) => ({ ...value, phone: e.target.value }))} placeholder="Chưa cập nhật" aria-invalid={!!errors.phone} />{errors.phone && <small className="field-error">{errors.phone}</small>}</div><div className="form-field"><label htmlFor="profile-skill">Trình độ thi đấu</label><select id="profile-skill" value={profile.skill_level} onChange={(e) => setProfile((value) => ({ ...value, skill_level: e.target.value as SkillLevel }))}>{Object.entries(skillLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div></div>
          {profile.role === 'PLAYER' && <fieldset className="profile-refund">
            <legend>Tài khoản nhận hoàn tiền</legend>
            <p className="profile-refund-help">Khi sân hủy lượt hoặc bạn chuyển dư, cửa hàng chuyển lại tiền vào tài khoản này. Để trống thì nhận tiền mặt tại quầy.</p>
            <div className="form-row">
              <div className="form-field"><label htmlFor="refund-bank">Ngân hàng</label><input id="refund-bank" value={profile.refund_bank_name ?? ''} placeholder="VD: MB, Vietcombank" onChange={(e) => setProfile((value) => ({ ...value, refund_bank_name: e.target.value }))} aria-invalid={!!errors.refund_bank_name} />{errors.refund_bank_name && <small className="field-error">{errors.refund_bank_name}</small>}</div>
              <div className="form-field"><label htmlFor="refund-number">Số tài khoản</label><input id="refund-number" inputMode="numeric" value={profile.refund_account_no ?? ''} onChange={(e) => setProfile((value) => ({ ...value, refund_account_no: e.target.value }))} aria-invalid={!!errors.refund_account_no} />{errors.refund_account_no && <small className="field-error">{errors.refund_account_no}</small>}</div>
            </div>
            <div className="form-field"><label htmlFor="refund-name">Tên chủ tài khoản</label><input id="refund-name" value={profile.refund_account_name ?? ''} placeholder="Viết không dấu, đúng như trên ngân hàng" onChange={(e) => setProfile((value) => ({ ...value, refund_account_name: e.target.value }))} aria-invalid={!!errors.refund_account_name} />{errors.refund_account_name && <small className="field-error">{errors.refund_account_name}</small>}</div>
          </fieldset>}
          <div className="profile-actions"><button className="account-secondary-button" type="button" onClick={() => { setProfile(currentUser); setError(''); setSuccess(''); setErrors({}); }}>Khôi phục ban đầu</button><button className="account-primary-button" type="submit" disabled={saving}>{saving ? 'Đang lưu…' : 'Lưu thay đổi ↗'}</button></div>
        </form>
      </section>
    </div>}
    {!loading && <ChangePasswordForm hasPassword={profile.has_password !== false} onSuccess={onPasswordChanged} />}
  </>;
}
