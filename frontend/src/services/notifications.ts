import { api } from './client';
import type { ApiResponse, Notification, PaginatedResponse } from '../types/api';

export const notificationsService = {
  list: (page = 1, isRead?: boolean, signal?: AbortSignal) =>
    api.request<PaginatedResponse<Notification>>('/notifications', { query: { page, page_size: 100, is_read: isRead }, signal }),
  markRead: (notificationId: number) =>
    api.request<ApiResponse<Notification>>('/notifications/' + notificationId + '/read', { method: 'PATCH', body: {} }),
};
