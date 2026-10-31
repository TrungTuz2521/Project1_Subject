import { api } from './client';
import type { ApiResponse, PaginatedResponse, Team, TeamCreate, TeamDetail, TeamJoinRequest, TeamMember, Participant } from '../types/api';

export const teamsService = {
  list: (page = 1, signal?: AbortSignal) => api.request<PaginatedResponse<Team>>('/teams', {
    query: { my: true, page, page_size: 20 }, signal,
  }),
  create: (body: TeamCreate) => api.request<ApiResponse<Team>>('/teams', { method: 'POST', body }),
  get: (teamId: number, signal?: AbortSignal) => api.request<ApiResponse<TeamDetail>>('/teams/' + teamId, { signal }),
  update: (teamId: number, body: Partial<TeamCreate>) => api.request<ApiResponse<Team>>('/teams/' + teamId, { method: 'PATCH', body }),
  requestJoin: (teamId: number) => api.request<ApiResponse<TeamJoinRequest>>('/teams/' + teamId + '/join-requests', { method: 'POST' }),
  respondJoinRequest: (teamId: number, postId: number, decision: 'ACCEPTED' | 'DECLINED') =>
    api.request<ApiResponse<TeamJoinRequest>>('/teams/' + teamId + '/join-requests/' + postId + '/respond', { method: 'PATCH', body: { decision } }),
  leave: (teamId: number) => api.request<ApiResponse<{ team_id: number; status: 'LEFT' }>>('/teams/' + teamId + '/members/me', { method: 'DELETE' }),
  removeMember: (teamId: number, userId: number, reason?: string) =>
    api.request<ApiResponse<{ team_id: number; user_id: number; status: 'REMOVED' }>>('/teams/' + teamId + '/members/' + userId, {
      method: 'DELETE', body: reason ? { reason } : undefined,
    }),
  listRecruitmentParticipants: (postId: number, signal?: AbortSignal) =>
    api.request<PaginatedResponse<Participant>>('/match-posts/' + postId + '/participants', { query: { page: 1, page_size: 100 }, signal }),
};
