import { api } from './client';
import type { ApiResponse, ISODateTime, Money, PaginatedResponse, SkillLevel, TeamPaymentRule } from '../types/api';

export type RequestType = 'FIND_OPPONENT' | 'RECRUIT_MEMBERS' | 'LOOK_FOR_TEAM';
export type RequestStatus = 'OPEN' | 'MATCHED' | 'EXPIRED' | 'CANCELLED';
export type GamePitchType = 'PITCH_5' | 'PITCH_7';
export interface Person { user_id: number; full_name: string; phone: string | null }
export interface TeamRef { team_id: number; team_name: string }

export interface PairedGame {
  match_id: number; status: 'SUGGESTED' | 'CONFIRMED' | 'COMPLETED' | 'CANCELLED';
  start_time: ISODateTime; end_time: ISODateTime; booking_id: number | null; pitch_name?: string | null;
  opponent: { team: TeamRef | null; skill_level: SkillLevel; players: number; captain: Person };
  /** Only when the system booked the pitch for both teams: each team pays its half. */
  needs_deposit: boolean; my_deposit: Money | null; my_deposit_paid: boolean | null;
  opponent_deposit_paid: boolean | null; hold_expires_at: ISODateTime | null;
}
export interface MatchRequest {
  request_id: number; request_type: RequestType; status: RequestStatus; title: string;
  team: TeamRef | null; booking_id: number | null; pitch_type: GamePitchType | null; pitch_name?: string | null;
  preferred_dates: string[] | null; window_start: string | null; window_end: string | null;
  match_time: ISODateTime | null; end_time: ISODateTime | null;
  skill_level: SkillLevel; skill_tolerance: number | null; payment_rule: TeamPaymentRule | null;
  players: number; required_players: number | null; fee_per_player: Money; note: string | null;
  search_until: ISODateTime | null; created_at: ISODateTime;
  match: PairedGame | null;
  joined_game: { start_time: ISODateTime; end_time: ISODateTime; pitch_name: string | null; team: TeamRef | null; captain: Person; fee_per_player: Money } | null;
  joiners: (Person & { party_size: number; skill_level: SkillLevel | null })[];
  requester?: Person;
}
export interface GameSlot { booking_id: number; pitch_name: string; pitch_type: GamePitchType; start_time: ISODateTime; end_time: ISODateTime }
export interface RequestOptions {
  teams: { team_id: number; team_name: string; last_player_count: number | null }[];
  opponent_bookings: GameSlot[]; recruit_games: GameSlot[]; today: string;
  rules: { opponent_lead_days: number; cutoff_hours: number; max_days: number; deposit_hold_hours: number; max_open_requests: number };
}
export interface RequestCreate {
  post_type: RequestType; skill_level: SkillLevel; skill_tolerance?: number; note?: string;
  team_id?: number; booking_id?: number; pitch_type?: GamePitchType; preferred_dates?: string[];
  window_start?: string; window_end?: string; payment_rule?: TeamPaymentRule | 'ANY';
  player_count?: number; required_players?: number; party_size?: number; fee_per_player?: string;
}
export type RequestEdit = Partial<Pick<RequestCreate, 'preferred_dates' | 'window_start' | 'window_end' | 'skill_tolerance' | 'required_players' | 'fee_per_player' | 'note'>>;

export const matchRequests = {
  options: (signal?: AbortSignal) => api.request<ApiResponse<RequestOptions>>('/match-requests/options', { signal }),
  mine: (signal?: AbortSignal) => api.request<PaginatedResponse<MatchRequest>>('/match-requests/my', { query: { page_size: 100 }, signal }),
  create: (body: RequestCreate) => api.request<ApiResponse<MatchRequest>>('/match-requests', { method: 'POST', body }),
  edit: (id: number, body: RequestEdit) => api.request<ApiResponse<MatchRequest>>('/match-requests/' + id, { method: 'PATCH', body }),
  cancel: (id: number) => api.request<ApiResponse<MatchRequest>>('/match-requests/' + id + '/cancel', { method: 'POST', body: {} }),
  adminList: (query: { status?: RequestStatus; request_type?: RequestType; page?: number }, signal?: AbortSignal) =>
    api.request<PaginatedResponse<MatchRequest>>('/admin/match-requests', { query: { page_size: 50, ...query }, signal }),
  adminScan: () => api.request<ApiResponse<{ scanned_count: number; matches: number[]; joined_requests: number[] }>>('/matchmaking/scan', { method: 'POST', body: {} }),
};

export const skillNames: Record<SkillLevel, string> = {
  BEGINNER: 'Mới chơi', AMATEUR: 'Phong trào', INTERMEDIATE: 'Trung bình', SEMI_PRO: 'Bán chuyên', PRO: 'Chuyên nghiệp',
};
export const toleranceNames: Record<number, string> = { 0: 'Ngang trình độ', 1: 'Chênh tối đa 1 bậc', 4: 'Trình độ nào cũng được' };
export const typeNames: Record<RequestType, string> = { FIND_OPPONENT: 'Tìm đối', RECRUIT_MEMBERS: 'Tìm thêm người', LOOK_FOR_TEAM: 'Đá ké' };
export const pitchNames: Record<GamePitchType, string> = { PITCH_5: 'Sân 5', PITCH_7: 'Sân 7' };
export const ruleNames: Record<TeamPaymentRule, string> = { SPLIT_EQUAL: 'Chia đều tiền sân', LOSER_PAYS_REMAINDER: 'Đội thua trả phần còn lại' };
/** Kick-off times of the 90-minute grid, 06:00 to 21:30. */
export const slotStarts = Array.from({ length: 11 }, (_, i) => {
  const minutes = 360 + i * 90;
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
});
export const slotEnd = (start: string) => {
  const [h, m] = start.split(':').map(Number);
  const minutes = h * 60 + m + 90;
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
};
