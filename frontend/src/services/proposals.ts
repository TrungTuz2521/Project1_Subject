import { api } from './client';
import type { ApiResponse, PaginatedResponse, Proposal, ProposalDetail, Decision } from '../types/api';

export const proposalsService = {
  list: (page = 1, status?: Proposal['status'], signal?: AbortSignal) =>
    api.request<PaginatedResponse<Proposal>>('/match-proposals', { query: { page, page_size: 100, status }, signal }),
  get: (proposalId: number, signal?: AbortSignal) =>
    api.request<ApiResponse<ProposalDetail>>('/match-proposals/' + proposalId, { signal }),
  respond: (proposalId: number, decision: Decision) =>
    api.request<ApiResponse<ProposalDetail>>('/match-proposals/' + proposalId + '/respond', { method: 'POST', body: { decision } }),
};
