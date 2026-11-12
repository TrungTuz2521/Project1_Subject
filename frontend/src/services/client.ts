import { createApiClient } from './api';

export const api = createApiClient({ baseUrl: import.meta.env.VITE_API_BASE_URL || '/api/v1' });
