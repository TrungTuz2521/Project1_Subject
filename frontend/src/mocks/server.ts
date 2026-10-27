import { demoUser, initialTeams, pitches, createFixtures } from './fixtures';
import type { Transport } from '../services/api';
import type { Team } from '../types/api';

export type MockScenario = 'normal' | 'empty' | 'server-error' | 'network-error' | 'validation-error';
export function createMockServer(delayMs = 450) {
  let teams = structuredClone(initialTeams);
  let nextId = 4;
  let validToken: string | null = null;
  let tokenDeadline = 0;
  let loginCount = 0;
  let scenario: MockScenario = 'normal';
  const fixtures = createFixtures();
  const reply = (data: unknown, status = 200, meta = {}) => new Response(JSON.stringify({ data,
    meta: { server_time: new Date().toISOString(), ...meta } }), { status, headers: { 'Content-Type': 'application/json' } });
  const fail = (status: number, code: string, message: string, fields = {}) => new Response(JSON.stringify({ error: { code, message, fields } }),
    { status, headers: { 'Content-Type': 'application/json' } });
  const transport: Transport = async (input, init) => {
    await new Promise<void>((resolve, reject) => {
      const signal = init?.signal;
      const aborted = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
      const timer = setTimeout(() => { signal?.removeEventListener('abort', aborted); resolve(); }, delayMs);
      if (signal?.aborted) aborted(); else signal?.addEventListener('abort', aborted, { once: true });
    });
    const url = new URL(String(input), 'http://mock.local');
    const path = url.pathname.replace(/^\/api\/v1/, '');
    const method = init?.method ?? 'GET';
    const publicPath = path === '/auth/login' || path === '/pitches' || path === '/match-posts';
    if (path === '/auth/login' && method === 'POST') {
      validToken = `mock-session-${++loginCount}`;
      tokenDeadline = Date.now() + 3600000;
      return reply({ access_token: validToken, expires_in: 3600, user: demoUser });
    }
    if (!publicPath && (new Headers(init?.headers).get('Authorization') !== `Bearer ${validToken}` || !validToken || Date.now() >= tokenDeadline)) {
      return fail(401, 'TOKEN_EXPIRED', 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.');
    }
    if (scenario === 'network-error') throw new TypeError('Simulated offline');
    if (scenario === 'server-error') return fail(500, 'INTERNAL_ERROR', 'Không tải được dữ liệu mẫu. Hãy chọn chế độ bình thường rồi thử lại.');
    if (path === '/users/me') return reply(demoUser);
    if (path === '/teams' && method === 'GET') {
      const page = Number(url.searchParams.get('page') ?? 1);
      const size = Number(url.searchParams.get('page_size') ?? 6);
      if (!Number.isInteger(page) || page < 1 || !Number.isInteger(size) || size < 1 || size > 100) return fail(422, 'VALIDATION_ERROR', 'Phân trang không hợp lệ.');
      const visible = scenario === 'empty' ? [] : teams;
      return reply(visible.slice((page - 1) * size, page * size), 200, { page, page_size: size, total: visible.length });
    }
    if (path === '/teams' && method === 'POST') {
      let body: unknown;
      try { body = JSON.parse(String(init?.body)); } catch { return fail(422, 'VALIDATION_ERROR', 'JSON không hợp lệ.'); }
      const name = (body as { team_name?: unknown } | null)?.team_name;
      if (typeof name !== 'string' || !name.trim() || name.trim().length > 100 || scenario === 'validation-error') {
        return fail(422, 'VALIDATION_ERROR', 'Kiểm tra lại thông tin đội bóng.', { team_name: 'Tên đội cần từ 1 đến 100 ký tự.' });
      }
      if (teams.some((team) => team.team_name.toLocaleLowerCase() === name.trim().toLocaleLowerCase())) {
        return fail(409, 'STATE_CONFLICT', 'Bạn đã có một đội mẫu dùng tên này.', { team_name: 'Hãy chọn một tên khác.' });
      }
      const team: Team = { team_id: nextId++, team_name: name.trim(), created_by: demoUser.user_id,
        creation_type: 'USER_CREATED', status: 'ACTIVE', active_member_count: 1 };
      teams.unshift(team); return reply(team, 201);
    }
    if (path === '/pitches' && method === 'GET') return reply(pitches, 200, { page: 1, page_size: 20, total: pitches.length });
    if (path === '/match-posts' && method === 'GET') return reply(fixtures.posts, 200, { page: 1, page_size: 20, total: fixtures.posts.length });
    if (path === '/bookings/my' && method === 'GET') return reply([fixtures.booking], 200, { page: 1, page_size: 20, total: 1 });
    if (path === '/notifications' && method === 'GET') return reply(fixtures.notifications, 200, { page: 1, page_size: 20, total: 1 });
    // Unknown endpoints fail explicitly: never pretend a payment or AI action succeeded.
    return fail(501, 'MOCK_NOT_IMPLEMENTED', `Mock chưa hỗ trợ ${method} ${path}. Bổ sung handler trước khi dùng.`);
  };
  return {
    transport, setScenario: (value: MockScenario) => { scenario = value; },
    expireSession: () => { tokenDeadline = 0; },
    reset: () => { teams = structuredClone(initialTeams); nextId = 4; scenario = 'normal'; },
  };
}
