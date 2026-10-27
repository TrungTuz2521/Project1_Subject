import { session } from '../stores/session';
import type { SessionStore } from '../stores/session';
import type { ApiErrorBody, FieldErrors } from '../types/api';

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public fields: FieldErrors = {}) {
    super(message); this.name = 'ApiError';
  }
}
export const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Đã xảy ra lỗi. Vui lòng thử lại.';
export type Query = Record<string, string | number | boolean | null | undefined>;
export type Transport = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'; body?: unknown; query?: Query;
  auth?: boolean; signal?: AbortSignal; timeoutMs?: number;
}
export function createApiClient(config: { baseUrl: string; transport?: Transport; store?: SessionStore }) {
  const store = config.store ?? session;
  const transport = config.transport ?? ((input, init) => fetch(input, init));
  const base = config.baseUrl.replace(/\/+$/, '');
  if (!/^https?:\/\//.test(base) && !/^\/(?!\/)/.test(base)) throw new Error('API base URL phải là HTTP(S) hoặc đường dẫn cùng origin.');

  return {
    async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
      // Keep tokens on the configured API origin; never accept absolute endpoint URLs.
      if (!/^\/(?!\/)/.test(path) || path.includes('..') || /[?#\\]/.test(path)) {
        throw new ApiError(0, 'INVALID_PATH', 'Endpoint phải là đường dẫn tương đối, ví dụ /teams.');
      }
      const params = new URLSearchParams();
      Object.entries(options.query ?? {}).forEach(([key, value]) => {
        if (value !== null && value !== undefined) params.set(key, String(value));
      });
      const query = params.toString();
      const url = `${base}${path}${query ? `?${query}` : ''}`;
      const auth = options.auth ?? true;
      const token = auth ? store.token() : null;
      if (auth && !token) throw new ApiError(401, 'UNAUTHORIZED', 'Phiên đã hết hạn hoặc bạn chưa đăng nhập. Vui lòng đăng nhập lại.');
      const headers = new Headers({ Accept: 'application/json' });
      if (token) headers.set('Authorization', `Bearer ${token}`);
      if (options.body !== undefined) headers.set('Content-Type', 'application/json');
      const controller = new AbortController();
      let timedOut = false;
      const abort = () => controller.abort();
      if (options.signal?.aborted) controller.abort();
      options.signal?.addEventListener('abort', abort, { once: true });
      const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, options.timeoutMs ?? 15000);
      // A late 401 from an older session must not sign out a newly logged-in user.
      const invalidate = () => { if (token && store.getSnapshot()?.access_token === token) store.clear(); };
      try {
        const response = await transport(url, {
          method: options.method ?? 'GET', headers, signal: controller.signal,
          credentials: 'omit', redirect: 'error',
          body: options.body === undefined ? undefined : JSON.stringify(options.body),
        });
        if (auth && response.status === 401) invalidate();
        const text = await response.text();
        let payload: unknown;
        try { payload = text ? JSON.parse(text) : undefined; }
        catch {
          throw new ApiError(response.status, 'INVALID_RESPONSE', 'API trả về dữ liệu không hợp lệ. Kiểm tra địa chỉ backend.');
        }
        if (!response.ok) {
          const error = (payload as Partial<ApiErrorBody> | undefined)?.error;
          throw new ApiError(response.status, error?.code ?? 'HTTP_ERROR',
            error?.message ?? `Yêu cầu thất bại (${response.status}).`, error?.fields ?? {});
        }
        if (response.status === 204) return undefined as T;
        if (!payload || typeof payload !== 'object' || !('data' in payload) || !('meta' in payload)) {
          throw new ApiError(response.status, 'INVALID_RESPONSE', 'Response chưa đúng định dạng data/meta của hợp đồng.');
        }
        return payload as T;
      } catch (error) {
        if (error instanceof ApiError) throw error;
        if (controller.signal.aborted) {
          if (timedOut) throw new ApiError(0, 'TIMEOUT', 'Máy chủ phản hồi quá lâu. Vui lòng thử lại.');
          throw new DOMException('Yêu cầu đã hủy.', 'AbortError');
        }
        throw new ApiError(0, 'NETWORK_ERROR', 'Không kết nối được máy chủ. Kiểm tra mạng, backend và cấu hình CORS.');
      } finally {
        clearTimeout(timeout);
        options.signal?.removeEventListener('abort', abort);
      }
    },
  };
}
