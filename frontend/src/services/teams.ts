import { api } from './client';
import type { ApiResponse, PaginatedResponse, Team, TeamCreate } from '../types/api';

export const teamsService = {
  list: (page = 1, signal?: AbortSignal) => api.request<PaginatedResponse<Team>>('/teams', {
    query: { my: true, page, page_size: 6 }, signal,
  }),
  create: (body: TeamCreate) => api.request<ApiResponse<Team>>('/teams', { method: 'POST', body }),
};
