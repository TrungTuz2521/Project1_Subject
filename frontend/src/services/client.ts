import { createApiClient } from './api';

export const useMocks = import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS !== 'false';
// Dynamic DEV import keeps mock credentials/handlers out of the production entry.
export const mockServer = useMocks ? (await import('../mocks/server')).createMockServer() : undefined;
export const api = createApiClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  transport: mockServer?.transport,
});
