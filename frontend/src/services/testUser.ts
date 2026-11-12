import type { UserSelf } from '../types/api';

/** A synthetic signed-in player for tests. Never put real credentials or personal data here. */
export const demoUser: UserSelf = { user_id: 2, full_name: 'Tài khoản kiểm thử', email: 'demo@example.test',
  phone: null, role: 'PLAYER', skill_level: 'INTERMEDIATE', status: 'ACTIVE' };
