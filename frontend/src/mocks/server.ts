import { demoUser, initialTeams, pitches, createFixtures } from './fixtures';
import type { Transport } from '../services/api';
import type { RegisterRequest, SkillLevel, Team, UserSelf } from '../types/api';

export type MockScenario = 'normal' | 'empty' | 'server-error' | 'network-error' | 'validation-error';
type MockAccount = { user: UserSelf; password: string };
const skillLevels: SkillLevel[] = ['BEGINNER', 'AMATEUR', 'INTERMEDIATE', 'SEMI_PRO', 'PRO'];

/** In-memory mock API for local development only. It does not authenticate real users. */
export function createMockServer(delayMs = 250) {
  let teams = structuredClone(initialTeams);
  let nextTeamId = 4;
  let nextUserId = 3;
  let validToken: string | null = null;
  let tokenDeadline = 0;
  let loginCount = 0;
  let currentUser: UserSelf = { ...demoUser };
  let scenario: MockScenario = 'normal';
  const accounts = new Map<string, MockAccount>();
  const seedAccounts = () => {
    accounts.clear();
    accounts.set(demoUser.email, { user: { ...demoUser }, password: 'mock-only' });
  };
  seedAccounts();
  const fixtures = createFixtures();
  const reply = (data: unknown, status = 200, meta: Record<string, unknown> = {}) => new Response(JSON.stringify({
    data, meta: { server_time: new Date().toISOString(), ...meta },
  }), { status, headers: { 'Content-Type': 'application/json' } });
  const fail = (status: number, code: string, message: string, fields: Record<string, string | string[]> = {}) => new Response(JSON.stringify({
    error: { code, message, ...(Object.keys(fields).length ? { fields } : {}) },
  }), { status, headers: { 'Content-Type': 'application/json' } });
  const parseBody = (init?: RequestInit): Record<string, unknown> | null => {
    try {
      const body: unknown = JSON.parse(String(init?.body ?? ''));
      return body && typeof body === 'object' && !Array.isArray(body) ? body as Record<string, unknown> : null;
    } catch { return null; }
  };

  const transport: Transport = async (input, init) => {
    await new Promise<void>((resolve, reject) => {
      const signal = init?.signal;
      const timer = setTimeout(() => { signal?.removeEventListener('abort', aborted); resolve(); }, delayMs);
      const aborted = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
      if (signal?.aborted) aborted(); else signal?.addEventListener('abort', aborted, { once: true });
    });
    const url = new URL(String(input), 'http://mock.local');
    const path = url.pathname.replace(/^\/api\/v1/, '');
    const method = init?.method ?? 'GET';
    const publicPath = path === '/auth/login' || path === '/auth/register' || path === '/pitches' || path === '/match-posts';

    if (path === '/auth/register' && method === 'POST') {
      const body = parseBody(init) as Partial<RegisterRequest> | null;
      if (!body) return fail(422, 'VALIDATION_ERROR', 'Dữ liệu đăng ký không hợp lệ.');
      const fullName = typeof body.full_name === 'string' ? body.full_name.trim() : '';
      const email = typeof body.email === 'string' ? body.email.trim().toLocaleLowerCase() : '';
      const password = typeof body.password === 'string' ? body.password : '';
      const passwordBytes = new TextEncoder().encode(password).length;
      const fields: Record<string, string> = {};
      if (fullName.length < 2 || fullName.length > 100) fields.full_name = 'Họ tên phải từ 2 đến 100 ký tự.';
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254) fields.email = 'Email không hợp lệ.';
      if (passwordBytes < 8 || passwordBytes > 72) fields.password = 'Mật khẩu phải dài từ 8 đến 72 byte UTF-8.';
      if (body.phone !== undefined && body.phone !== '' && (typeof body.phone !== 'string' || body.phone.trim().length > 30)) fields.phone = 'Số điện thoại không hợp lệ.';
      if (body.skill_level !== undefined && !skillLevels.includes(body.skill_level as SkillLevel)) fields.skill_level = 'Trình độ không hợp lệ.';
      if (Object.keys(fields).length) return fail(422, 'VALIDATION_ERROR', 'Vui lòng kiểm tra lại thông tin đăng ký.', fields);
      if (accounts.has(email)) return fail(409, 'EMAIL_ALREADY_EXISTS', 'Email đã được sử dụng.', { email: 'Email này đã có tài khoản.' });
      const user: UserSelf = {
        user_id: nextUserId++, full_name: fullName, email, phone: typeof body.phone === 'string' && body.phone.trim() ? body.phone.trim() : null,
        role: 'PLAYER', skill_level: (body.skill_level as SkillLevel | undefined) ?? 'INTERMEDIATE', status: 'ACTIVE',
      };
      accounts.set(email, { user, password });
      return reply(user, 201);
    }

    if (path === '/auth/login' && method === 'POST') {
      const body = parseBody(init);
      const email = typeof body?.email === 'string' ? body.email.trim().toLocaleLowerCase() : '';
      const password = typeof body?.password === 'string' ? body.password : '';
      const account = accounts.get(email);
      // Keep one generic error so the UI does not reveal whether an email exists.
      if (!account || account.password !== password || account.user.status !== 'ACTIVE') {
        return fail(401, 'INVALID_CREDENTIALS', 'Email hoặc mật khẩu không chính xác.');
      }
      validToken = `mock-session-${++loginCount}`;
      tokenDeadline = Date.now() + 3600000;
      currentUser = { ...account.user };
      return reply({ access_token: validToken, expires_in: 3600, user: currentUser });
    }

    if (!publicPath && (new Headers(init?.headers).get('Authorization') !== `Bearer ${validToken}` || !validToken || Date.now() >= tokenDeadline)) {
      return fail(401, 'TOKEN_EXPIRED', 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.');
    }
    if (scenario === 'network-error') throw new TypeError('Simulated offline');
    if (scenario === 'server-error') return fail(500, 'INTERNAL_ERROR', 'Không tải được dữ liệu mẫu. Hãy chọn chế độ bình thường rồi thử lại.');

    if (path === '/users/me' && method === 'GET') return reply(currentUser);
    if (path === '/users/me' && method === 'PATCH') {
      const body = parseBody(init);
      if (!body) return fail(422, 'VALIDATION_ERROR', 'Dữ liệu hồ sơ không hợp lệ.');
      const fields: Record<string, string> = {};
      if (body.full_name !== undefined && (typeof body.full_name !== 'string' || body.full_name.trim().length < 2 || body.full_name.trim().length > 100)) fields.full_name = 'Họ tên phải từ 2 đến 100 ký tự.';
      if (body.phone !== undefined && body.phone !== null && (typeof body.phone !== 'string' || body.phone.trim().length > 30)) fields.phone = 'Số điện thoại không hợp lệ.';
      if (body.skill_level !== undefined && !skillLevels.includes(body.skill_level as SkillLevel)) fields.skill_level = 'Trình độ không hợp lệ.';
      if (Object.keys(fields).length) return fail(422, 'VALIDATION_ERROR', 'Vui lòng kiểm tra lại hồ sơ.', fields);
      currentUser = {
        ...currentUser,
        ...(typeof body.full_name === 'string' ? { full_name: body.full_name.trim() } : {}),
        ...(body.phone !== undefined ? { phone: typeof body.phone === 'string' && body.phone.trim() ? body.phone.trim() : null } : {}),
        ...(typeof body.skill_level === 'string' ? { skill_level: body.skill_level as SkillLevel } : {}),
      };
      const account = accounts.get(currentUser.email);
      if (account) accounts.set(currentUser.email, { ...account, user: { ...currentUser } });
      return reply(currentUser);
    }

    if (path === '/teams' && method === 'GET') {
      const page = Number(url.searchParams.get('page') ?? 1);
      const size = Number(url.searchParams.get('page_size') ?? 6);
      if (!Number.isInteger(page) || page < 1 || !Number.isInteger(size) || size < 1 || size > 100) return fail(422, 'VALIDATION_ERROR', 'Phân trang không hợp lệ.');
      const visible = scenario === 'empty' ? [] : teams;
      return reply(visible.slice((page - 1) * size, page * size), 200, { page, page_size: size, total: visible.length });
    }
    if (path === '/teams' && method === 'POST') {
      const body = parseBody(init);
      const name = body?.team_name;
      if (typeof name !== 'string' || !name.trim() || name.trim().length > 100 || scenario === 'validation-error') {
        return fail(422, 'VALIDATION_ERROR', 'Kiểm tra lại thông tin đội bóng.', { team_name: 'Tên đội cần từ 1 đến 100 ký tự.' });
      }
      if (teams.some((team) => team.team_name.toLocaleLowerCase() === name.trim().toLocaleLowerCase())) {
        return fail(409, 'STATE_CONFLICT', 'Bạn đã có một đội mẫu dùng tên này.', { team_name: 'Hãy chọn một tên khác.' });
      }
      const team: Team = { team_id: nextTeamId++, team_name: name.trim(), created_by: currentUser.user_id,
        creation_type: 'USER_CREATED', status: 'ACTIVE', active_member_count: 1 };
      teams.unshift(team); return reply(team, 201);
    }
    if (path === '/pitches' && method === 'GET') return reply(pitches, 200, { page: 1, page_size: 20, total: pitches.length });
    if (path === '/match-posts' && method === 'GET') return reply(fixtures.posts, 200, { page: 1, page_size: 20, total: fixtures.posts.length });
    if (path === '/bookings/my' && method === 'GET') return reply([fixtures.booking], 200, { page: 1, page_size: 20, total: 1 });
    if (path === '/notifications' && method === 'GET') return reply(fixtures.notifications, 200, { page: 1, page_size: 20, total: 1 });
    // Unknown endpoints fail explicitly; no mock flow pretends a payment or AI action succeeded.
    return fail(501, 'MOCK_NOT_IMPLEMENTED', `Mock chưa hỗ trợ ${method} ${path}. Bổ sung handler trước khi dùng.`);
  };

  return {
    transport,
    setScenario: (value: MockScenario) => { scenario = value; },
    expireSession: () => { tokenDeadline = 0; },
    reset: () => {
      teams = structuredClone(initialTeams); nextTeamId = 4; nextUserId = 3; scenario = 'normal';
      validToken = null; tokenDeadline = 0; currentUser = { ...demoUser }; seedAccounts();
    },
  };
}
