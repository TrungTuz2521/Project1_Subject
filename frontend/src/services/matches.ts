import { api } from './client';
import type { ApiResponse, Match, MatchDetail, PaginatedResponse } from '../types/api';

export const matchesService = {
  list: (page = 1, status?: Match['status'], signal?: AbortSignal) =>
    api.request<PaginatedResponse<Match>>('/matches', { query: { page, page_size: 100, status }, signal }),
  get: (matchId: number, signal?: AbortSignal) =>
    api.request<ApiResponse<MatchDetail>>('/matches/' + matchId, { signal }),
};
