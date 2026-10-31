import { afterEach, describe, expect, it } from 'vitest';
import { createApiClient } from '../services/api';
import { createSessionStore } from '../stores/session';
import { createMockServer } from './server';
import type { ApiResponse, LoginData, Match, MatchPost, ProposalDetail, TeamDetail, TeamJoinRequest } from '../types/api';

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
    expect(feed.meta.total).toBe(4);
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

    const edited = await api.request<ApiResponse<MatchPost>>('/match-posts/' + created.data.post_id, {
      method: 'PATCH', body: { title: 'FC Test đã cập nhật', description: 'Mô tả mới' },
    });
    expect(edited.data.title).toBe('FC Test đã cập nhật');

    const cancelled = await api.request<ApiResponse<MatchPost>>('/match-posts/' + created.data.post_id + '/cancel', {
      method: 'POST', body: { reason: 'Test cancel' },
    });
    expect(cancelled.data.status).toBe('CANCELLED');
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
  });

  it('returns team detail and protects captain leave rules', async () => {
    const { api } = await setup();
    const team = await api.request<ApiResponse<TeamDetail>>('/teams/1');
    expect(team.data.members.some(member => member.role === 'CAPTAIN' && member.user_id === 2)).toBe(true);
    await expect(api.request('/teams/1/members/me', { method: 'DELETE' }))
      .rejects.toMatchObject({ status: 409, code: 'CAPTAIN_TRANSFER_REQUIRED' });
  });

  it('marks a notification read without inventing a payment or a confirmed booking', async () => {
    const { api } = await setup();
    const read = await api.request<ApiResponse<{ is_read: boolean }>>('/notifications/1/read', { method: 'PATCH', body: {} });
    expect(read.data.is_read).toBe(true);
    const list = await api.request<{ data: { is_read: boolean }[] }>('/notifications');
    expect(list.data[0].is_read).toBe(true);
    const matches = await api.request<{ data: Match[] }>('/matches');
    expect(matches.data.every(match => match.status !== 'CONFIRMED')).toBe(true);
  });
});
