import { api } from './client';
import type { ApiResponse, MatchPost, PostCreate, PostSummary, PaginatedResponse, PostType, PostStatus, PitchType, SkillLevel } from '../types/api';

export interface MatchPostFilters {
  post_type?: PostType;
  pitch_type?: PitchType;
  skill_level?: SkillLevel;
  from?: string;
  to?: string;
  page?: number;
  page_size?: number;
  status?: PostStatus;
}
export const matchPostsService = {
  list: (filters: MatchPostFilters = {}, signal?: AbortSignal) =>
    api.request<PaginatedResponse<PostSummary>>('/match-posts', { query: { page_size: 100, ...filters }, auth: false, signal }),
  mine: (page = 1, status?: PostStatus, signal?: AbortSignal) =>
    api.request<PaginatedResponse<MatchPost>>('/match-posts/my', { query: { page, page_size: 100, status }, signal }),
  get: (postId: number, signal?: AbortSignal) =>
    api.request<ApiResponse<MatchPost>>('/match-posts/' + postId, { auth: false, signal }),
  create: (body: PostCreate) => api.request<ApiResponse<MatchPost>>('/match-posts', { method: 'POST', body }),
  update: (postId: number, body: Partial<PostCreate>) =>
    api.request<ApiResponse<MatchPost>>('/match-posts/' + postId, { method: 'PATCH', body }),
  cancel: (postId: number, reason?: string) =>
    api.request<ApiResponse<MatchPost>>('/match-posts/' + postId + '/cancel', { method: 'POST', body: reason ? { reason } : {} }),
  requestParticipant: (postId: number) =>
    api.request<ApiResponse<{ participant_id: number; post_id: number; user_id: number; status: string; proposal_id: number }>>(
      '/match-posts/' + postId + '/participants', { method: 'POST', body: {} },
    ),
};
