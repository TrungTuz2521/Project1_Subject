import { describe, expect, it } from 'vitest';
import { createApiClient } from './api';
import { formErrorMessage } from './formErrors';

describe('post validation errors', () => {
  it('shows the backend team-size reason instead of losing it behind the generic 422 summary', async () => {
    const api = createApiClient({ baseUrl: '/api/v1', transport: async () => new Response(JSON.stringify({
      error: { code: 'VALIDATION_ERROR', message: 'Dữ liệu không hợp lệ.', fields: { team_id: 'Đội chưa đủ người.' } },
    }), { status: 422 }) });
    try {
      await api.request('/match-posts', { method: 'POST', auth: false, body: {} });
      throw new Error('Expected a validation error');
    } catch (error) {
      expect(formErrorMessage(error)).toBe('Dữ liệu không hợp lệ. Đội bóng: Đội chưa đủ người.');
    }
  });
});
