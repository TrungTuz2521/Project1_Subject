import { afterEach, describe, expect, it } from 'vitest';
import { createApiClient } from '../services/api';
import { createSessionStore } from '../stores/session';
import { createMockServer } from './server';
import type { ApiResponse, LoginData, Match, MatchPost, ProposalDetail, TeamDetail, TeamJoinRequest, Notification } from '../types/api';

describe('matchmaking mock API', () => {
  const stores: ReturnType<typeof createSessionStore>[] = [];
  afterEach(() => { stores.forEach(store => store.clear()); stores.length = 0; });

  async function setup() {
    const store = createSessionStore();
    stores.push(store);
    const mock = createMockServer(0);
    const api = createApiClient({ baseUrl: '/api/v1', store, transport: mock.transport });
    const loggedIn = await api.request<ApiResponse<LoginData>>('/auth/login', {
      auth: false, method: 'POST', body: { email: 'demo@example.test', password: 'mock-only' },
    });
    store.set(loggedIn.data);
    return { api, store, mock };
  }

  it('lists all four post types and supports create, edit and cancel', async () => {
    const { api } = await setup();
    const feed = await api.request<{ data: MatchPost[]; meta: { total: number } }>('/match-posts', { auth: false });
    expect(feed.meta.total).toBe(5);
    expect(new Set(feed.data.map(post => post.post_type))).toEqual(new Set([
      'FIND_OPPONENT', 'RECRUIT_MEMBERS', 'LOOK_FOR_TEAM', 'RANDOM_SQUAD',
    ]));

    const start = new Date(Date.now() + 24 * 60 * 60 * 1000);
    const end = new Date(start.getTime() + 90 * 60 * 1000);
    const expiry = new Date(start.getTime() - 2 * 60 * 60 * 1000);
    const created = await api.request<ApiResponse<MatchPost>>('/match-posts', {
      method: 'POST',
      body: {
        post_type: 'FIND_OPPONENT', title: 'FC Test tìm đối thủ', team_id: 1,
        pitch_type: 'PITCH_7', match_time: start.toISOString(), end_time: end.toISOString(),
        skill_level: 'INTERMEDIATE', payment_rule: 'SPLIT_EQUAL', expiry_time: expiry.toISOString(),
      },
    });
    expect(created.data.post_id).toBeGreaterThan(4);
    expect(created.data.status).toBe('OPEN');

    const updatedStart = new Date(start.getTime() + 60 * 60 * 1000);
    const updatedEnd = new Date(updatedStart.getTime() + 90 * 60 * 1000);
    const edited = await api.request<ApiResponse<MatchPost>>('/match-posts/' + created.data.post_id, {
      method: 'PATCH', body: {
        title: 'FC Test đã cập nhật', description: 'Mô tả mới',
        skill_level: 'AMATEUR', pitch_type: 'PITCH_5',
        match_time: updatedStart.toISOString(), end_time: updatedEnd.toISOString(),
      },
    });
    expect(edited.data.title).toBe('FC Test đã cập nhật');
    expect(edited.data.skill_level).toBe('AMATEUR');
    expect(edited.data.pitch_type).toBe('PITCH_5');
    expect(edited.data.match_time).toBe(updatedStart.toISOString());
    await expect(api.request('/match-posts/' + created.data.post_id, {
      method: 'PATCH', body: { match_time: updatedStart.toISOString(), end_time: updatedStart.toISOString() },
    })).rejects.toMatchObject({ status: 422, code: 'VALIDATION_ERROR' });

    const cancelled = await api.request<ApiResponse<MatchPost>>('/match-posts/' + created.data.post_id + '/cancel', {
      method: 'POST', body: { reason: 'Test cancel' },
    });
    expect(cancelled.data.status).toBe('CANCELLED');
  });

  it('allows LOOK_FOR_TEAM to start without an assigned team, pitch or time', async () => {
    const { api } = await setup();
    const expiry = new Date(Date.now() + 48 * 60 * 60 * 1000).toISOString();
    const created = await api.request<ApiResponse<MatchPost>>('/match-posts', {
      method: 'POST', body: {
        post_type: 'LOOK_FOR_TEAM', title: 'Cá nhân tìm đội', skill_level: 'AMATEUR', expiry_time: expiry,
        team_id: null,
      },
    });
    expect(created.data.team_id).toBeNull();
    expect(created.data.pitch_type).toBeNull();
    expect(created.data.match_time).toBeNull();
    expect(created.data.matching_ready).toBe(false);
  });

  it('does not treat one ACCEPTED confirmation as an accepted proposal or confirmed match', async () => {
    const { api } = await setup();
    const response = await api.request<ApiResponse<ProposalDetail>>('/match-proposals/11/respond', {
      method: 'POST', body: { decision: 'ACCEPTED' },
    });
    expect(response.data.confirmations.some(item => item.decision === 'ACCEPTED')).toBe(true);
    expect(response.data.status).toBe('PENDING_CONFIRMATION');
    const matches = await api.request<{ data: Match[]; meta: { total: number } }>('/matches');
    expect(matches.meta.total).toBe(0);
  });

  it('registers a new player and creates a team recruitment join request', async () => {
    const { api, store } = await setup();
    await api.request('/auth/register', {
      auth: false, method: 'POST',
      body: { full_name: 'Người chơi thử', email: 'player@example.test', password: 'password123' },
    });
    const loggedIn = await api.request<ApiResponse<LoginData>>('/auth/login', {
      auth: false, method: 'POST', body: { email: 'player@example.test', password: 'password123' },
    });
    store.set(loggedIn.data);
    const result = await api.request<ApiResponse<TeamJoinRequest>>('/teams/2/join-requests', { method: 'POST', body: {} });
    expect(result.data.post_id).toBe(2);
    expect(result.data.status).toBe('PENDING');
    expect(result.data.proposal_id).toBeGreaterThan(0);
    const proposals = await api.request<{ data: ProposalDetail[] }>('/match-proposals');
    expect(proposals.data.some(item => item.proposal_id === result.data.proposal_id)).toBe(true);

    const captainLogin = await api.request<ApiResponse<LoginData>>('/auth/login', {
      auth: false, method: 'POST', body: { email: 'captain@example.test', password: 'mock-only' },
    });
    store.set(captainLogin.data);
    const captainNotifications = await api.request<{ data: Notification[] }>('/notifications');
    expect(captainNotifications.data.some(item => item.notification_type === 'TEAM_JOINED' && item.proposal_id === result.data.proposal_id)).toBe(true);
  });

  it('returns team detail and protects captain leave rules', async () => {
    const { api } = await setup();
    const team = await api.request<ApiResponse<TeamDetail>>('/teams/1');
    expect(team.data.members.some(member => member.role === 'CAPTAIN' && member.user_id === 2)).toBe(true);
    await expect(api.request('/teams/1/members/me', { method: 'DELETE' }))
      .rejects.toMatchObject({ status: 409, code: 'CAPTAIN_TRANSFER_REQUIRED' });
  });

  it('does not expose another player\'s proposals or matches', async () => {
    const { api, store } = await setup();
    await api.request('/auth/register', {
      auth: false, method: 'POST',
      body: { full_name: 'Người ngoài', email: 'outsider@example.test', password: 'password123' },
    });
    const login = await api.request<ApiResponse<LoginData>>('/auth/login', {
      auth: false, method: 'POST', body: { email: 'outsider@example.test', password: 'password123' },
    });
    store.set(login.data);
    const proposals = await api.request<{ data: ProposalDetail[] }>('/match-proposals');
    const matches = await api.request<{ data: Match[] }>('/matches');
    expect(proposals.data).toHaveLength(0);
    expect(matches.data).toHaveLength(0);
    await expect(api.request('/match-proposals/11')).rejects.toMatchObject({ status: 404, code: 'NOT_FOUND' });
  });

  it('marks a notification read without inventing a payment or a confirmed booking', async () => {
    const { api, store } = await setup();
    const read = await api.request<ApiResponse<{ is_read: boolean }>>('/notifications/1/read', { method: 'PATCH', body: {} });
    expect(read.data.is_read).toBe(true);
    const list = await api.request<{ data: { is_read: boolean }[] }>('/notifications');
    expect(list.data[0].is_read).toBe(true);
    const matches = await api.request<{ data: Match[] }>('/matches');
    expect(matches.data.every(match => match.status !== 'CONFIRMED')).toBe(true);

    const captainLogin = await api.request<ApiResponse<LoginData>>('/auth/login', {
      auth: false, method: 'POST', body: { email: 'captain@example.test', password: 'mock-only' },
    });
    store.set(captainLogin.data);
    const otherUserNotifications = await api.request<{ data: Notification[] }>('/notifications');
    expect(otherUserNotifications.data).toHaveLength(0);
    await expect(api.request('/notifications/1/read', { method: 'PATCH' }))
      .rejects.toMatchObject({ status: 404, code: 'NOT_FOUND' });
  });
  it('creates only a SUGGESTED match after both opponent confirmations', async () => {
    const { api, store } = await setup();
    await api.request('/match-proposals/11/respond', { method: 'POST', body: { decision: 'ACCEPTED' } });
    const captainLogin = await api.request<ApiResponse<LoginData>>('/auth/login', {
      auth: false, method: 'POST', body: { email: 'captain@example.test', password: 'mock-only' },
    });
    store.set(captainLogin.data);
    const accepted = await api.request<ApiResponse<ProposalDetail>>('/match-proposals/11/respond', {
      method: 'POST', body: { decision: 'ACCEPTED' },
    });
    expect(accepted.data.status).toBe('ACCEPTED');
    const list = await api.request<{ data: Match[] }>('/matches');
    expect(list.data).toHaveLength(1);
    expect(list.data[0].status).toBe('SUGGESTED');
    expect(list.data[0].confirmed_at).toBeNull();
    expect(list.data[0].booking_id).toBeNull();

    const demoLogin = await api.request<ApiResponse<LoginData>>('/auth/login', {
      auth: false, method: 'POST', body: { email: 'demo@example.test', password: 'mock-only' },
    });
    store.set(demoLogin.data);
    await expect(api.request('/teams/1/members/4', { method: 'DELETE', body: { reason: 'Vi phạm nội quy đội' } }))
      .rejects.toMatchObject({ status: 409, code: 'ACTIVE_MATCH_MEMBERSHIP' });
    await expect(api.request('/match-posts/1/cancel', { method: 'POST', body: { reason: 'test' } }))
      .rejects.toMatchObject({ status: 409, code: 'MATCH_CANCELLATION_REQUIRED' });
  });

  it('activates a team member only after captain and candidate both accept without creating a match', async () => {
    const { api, store } = await setup();
    const team = await api.request<ApiResponse<{ team_id: number }>>('/teams', {
      method: 'POST', body: { team_name: 'FC Membership Test' },
    });
    const start = new Date(Date.now() + 24 * 60 * 60 * 1000);
    const post = await api.request<ApiResponse<MatchPost>>('/match-posts', {
      method: 'POST',
      body: {
        post_type: 'RECRUIT_MEMBERS', title: 'FC Membership Test tuyển người', team_id: team.data.team_id,
        pitch_type: 'PITCH_7', match_time: start.toISOString(),
        end_time: new Date(start.getTime() + 90 * 60 * 1000).toISOString(),
        skill_level: 'INTERMEDIATE', payment_rule: 'SPLIT_EQUAL', required_players: 1,
        expiry_time: new Date(start.getTime() - 2 * 60 * 60 * 1000).toISOString(),
      },
    });
    await api.request('/auth/register', {
      auth: false, method: 'POST',
      body: { full_name: 'Ứng viên Test', email: 'candidate@example.test', password: 'password123' },
    });
    const candidateLogin = await api.request<ApiResponse<LoginData>>('/auth/login', {
      auth: false, method: 'POST', body: { email: 'candidate@example.test', password: 'password123' },
    });
    store.set(candidateLogin.data);
    const request = await api.request<ApiResponse<TeamJoinRequest>>('/teams/' + team.data.team_id + '/join-requests', {
      method: 'POST', body: {},
    });

    const captainLogin = await api.request<ApiResponse<LoginData>>('/auth/login', {
      auth: false, method: 'POST', body: { email: 'demo@example.test', password: 'mock-only' },
    });
    store.set(captainLogin.data);
    await api.request('/teams/' + team.data.team_id + '/join-requests/' + post.data.post_id + '/respond', {
      method: 'PATCH', body: { decision: 'ACCEPTED' },
    });

    store.set(candidateLogin.data);
    const accepted = await api.request<ApiResponse<ProposalDetail>>('/match-proposals/' + request.data.proposal_id + '/respond', {
      method: 'POST', body: { decision: 'ACCEPTED' },
    });
    expect(accepted.data.status).toBe('ACCEPTED');
    const detail = await api.request<ApiResponse<TeamDetail>>('/teams/' + team.data.team_id);
    expect(detail.data.members.some(member => member.user_id === candidateLogin.data.user.user_id && member.status === 'ACTIVE')).toBe(true);
    const matches = await api.request<{ data: Match[] }>('/matches');
    expect(matches.data).toHaveLength(0);
    const finalPost = await api.request<ApiResponse<MatchPost>>('/match-posts/' + post.data.post_id, { auth: false });
    expect(finalPost.data.status).toBe('MATCHED');
    expect(finalPost.data.required_players).toBe(0);
  });

  it('also finalizes membership when the candidate accepts before the captain', async () => {
    const { api, store } = await setup();
    const team = await api.request<ApiResponse<{ team_id: number }>>('/teams', {
      method: 'POST', body: { team_name: 'FC Candidate First' },
    });
    const start = new Date(Date.now() + 24 * 60 * 60 * 1000);
    const post = await api.request<ApiResponse<MatchPost>>('/match-posts', {
      method: 'POST',
      body: {
        post_type: 'RECRUIT_MEMBERS', title: 'FC Candidate First tuyển người', team_id: team.data.team_id,
        pitch_type: 'PITCH_7', match_time: start.toISOString(),
        end_time: new Date(start.getTime() + 90 * 60 * 1000).toISOString(),
        skill_level: 'INTERMEDIATE', payment_rule: 'SPLIT_EQUAL', required_players: 1,
        expiry_time: new Date(start.getTime() - 2 * 60 * 60 * 1000).toISOString(),
      },
    });
    await api.request('/auth/register', {
      auth: false, method: 'POST',
      body: { full_name: 'Ứng viên phản hồi trước', email: 'candidate-first@example.test', password: 'password123' },
    });
    const candidateLogin = await api.request<ApiResponse<LoginData>>('/auth/login', {
      auth: false, method: 'POST', body: { email: 'candidate-first@example.test', password: 'password123' },
    });
    store.set(candidateLogin.data);
    const request = await api.request<ApiResponse<TeamJoinRequest>>('/teams/' + team.data.team_id + '/join-requests', { method: 'POST' });
    const candidateAccepted = await api.request<ApiResponse<ProposalDetail>>('/match-proposals/' + request.data.proposal_id + '/respond', {
      method: 'POST', body: { decision: 'ACCEPTED' },
    });
    expect(candidateAccepted.data.status).toBe('PENDING_CONFIRMATION');

    const captainLogin = await api.request<ApiResponse<LoginData>>('/auth/login', {
      auth: false, method: 'POST', body: { email: 'demo@example.test', password: 'mock-only' },
    });
    store.set(captainLogin.data);
    const captainAccepted = await api.request<ApiResponse<TeamJoinRequest>>('/teams/' + team.data.team_id + '/join-requests/' + post.data.post_id + '/respond', {
      method: 'PATCH', body: { decision: 'ACCEPTED' },
    });
    expect(captainAccepted.data.status).toBe('ACCEPTED');
    const detail = await api.request<ApiResponse<TeamDetail>>('/teams/' + team.data.team_id);
    expect(detail.data.members.some(member => member.user_id === candidateLogin.data.user.user_id && member.status === 'ACTIVE')).toBe(true);
    const finalPost = await api.request<ApiResponse<MatchPost>>('/match-posts/' + post.data.post_id, { auth: false });
    expect(finalPost.data.status).toBe('MATCHED');
    expect(finalPost.data.required_players).toBe(0);
  });

});
