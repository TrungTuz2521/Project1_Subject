import { api } from './client';
import type { ApiResponse, Notification, PaginatedResponse } from '../types/api';

export const notificationsService = {
  list: (page = 1, isRead?: boolean, signal?: AbortSignal) =>
    api.request<PaginatedResponse<Notification>>('/notifications', { query: { page, page_size: 100, is_read: isRead }, signal }),
  markRead: (notificationId: number) =>
    api.request<ApiResponse<Notification>>('/notifications/' + notificationId + '/read', { method: 'PATCH' }),
  /** Marks every unread in-app notice read; answers how many changed. */
  markAllRead: () =>
    api.request<ApiResponse<{ updated: number }>>('/notifications/read-all', { method: 'PATCH' }),
  /** Only the count matters, so ask for one row and read meta.total. */
  unreadCount: (signal?: AbortSignal) =>
    api.request<PaginatedResponse<Notification>>('/notifications', { query: { page: 1, page_size: 1, is_read: false }, signal }).then(r => r.meta.total),
};

/** Fired after a notice is marked read, so the header badge updates without waiting for its next poll. */
export const NOTIFICATIONS_CHANGED = 'notifications:changed';
