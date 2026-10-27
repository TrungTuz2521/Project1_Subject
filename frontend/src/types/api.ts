/** DTO conventions: money remains decimal strings; timestamps include an offset. */
export type Money = string;
export type ISODateTime = string;
export interface Meta { server_time: ISODateTime }
export interface PaginationMeta extends Meta { page: number; page_size: number; total: number }
export interface ApiResponse<T> { data: T; meta: Meta }
export interface PaginatedResponse<T> { data: T[]; meta: PaginationMeta }
export type FieldErrors = Record<string, string | string[]>;
export interface ApiErrorBody { error: { code: string; message: string; fields?: FieldErrors } }
export type SkillLevel = 'BEGINNER' | 'AMATEUR' | 'INTERMEDIATE' | 'SEMI_PRO' | 'PRO';
export type PitchType = 'PITCH_5' | 'PITCH_7' | 'PITCH_11';
export type MvpPitchType = Exclude<PitchType, 'PITCH_11'>;
export type TeamPaymentRule = 'SPLIT_EQUAL' | 'LOSER_PAYS_REMAINDER';
export type BookingPaymentRule = TeamPaymentRule | 'DIRECT_BOOKING';
export interface UserSelf {
  user_id: number; full_name: string; email: string; phone: string | null;
  role: 'PLAYER' | 'ADMIN'; skill_level: SkillLevel; status: 'ACTIVE' | 'BANNED' | 'INACTIVE';
}
export interface LoginRequest { email: string; password: string }
export interface RegisterRequest extends LoginRequest { full_name: string; phone?: string; skill_level?: SkillLevel }
export interface LoginData { access_token: string; expires_in: number; user: UserSelf }
export type ProfileUpdate = Partial<Pick<UserSelf, 'full_name' | 'phone' | 'skill_level'>>;
export interface Team {
  team_id: number; team_name: string; created_by: number | null;
  creation_type: 'USER_CREATED' | 'AI_RANDOM'; status: 'ACTIVE' | 'INACTIVE'; active_member_count: number;
}
export interface TeamMember {
  user_id: number; full_name: string; role: 'CAPTAIN' | 'MEMBER';
  status: 'ACTIVE' | 'LEFT' | 'REMOVED'; joined_at: ISODateTime;
}
export interface TeamDetail extends Team { members: TeamMember[] }
export interface TeamCreate { team_name: string }
export type PostType = 'FIND_OPPONENT' | 'RECRUIT_MEMBERS' | 'LOOK_FOR_TEAM' | 'RANDOM_SQUAD';
export type PostStatus = 'OPEN' | 'LOCKED' | 'MATCHED' | 'EXPIRED' | 'CANCELLED' | 'PENDING_DEPOSIT';
export interface PostSummary {
  post_id: number; title: string; post_type: PostType; team_id: number | null;
  pitch_id: number | null; pitch_type: PitchType | null; match_time: ISODateTime | null;
  end_time: ISODateTime | null; skill_level: SkillLevel; payment_rule: TeamPaymentRule | null;
  required_players: number | null; current_players: number; expiry_time: ISODateTime; status: PostStatus;
}
export interface MatchPost extends PostSummary { description: string | null; matching_ready: boolean }
export interface PostCreate {
  post_type: PostType; title: string; skill_level: SkillLevel; expiry_time: ISODateTime;
  description?: string; team_id?: number | null; pitch_id?: number | null; pitch_type?: MvpPitchType;
  match_time?: ISODateTime; end_time?: ISODateTime; payment_rule?: TeamPaymentRule; required_players?: number;
}
export interface Participant {
  participant_id: number; post_id: number; user_id: number;
  status: 'PENDING' | 'ACCEPTED' | 'REJECTED' | 'CANCELLED'; joined_at: ISODateTime;
}
export interface TeamJoinRequest extends Participant { proposal_id: number }
export type Decision = 'ACCEPTED' | 'DECLINED';
export interface Confirmation { user_id: number; decision: 'PENDING' | Decision; responded_at: ISODateTime | null }
export interface Proposal {
  proposal_id: number; source_post_id: number; target_post_id: number | null;
  candidate_user_id: number | null; proposal_type: 'TEAM_MEMBER' | 'OPPONENT';
  compatibility_score: Money; status: 'PENDING_CONFIRMATION' | 'ACCEPTED' | 'REJECTED' | 'EXPIRED';
  expires_at: ISODateTime; confirmed_at: ISODateTime | null;
}
export interface ProposalDetail extends Proposal { confirmations: Confirmation[]; match_id?: number; booking_id?: number }
export interface Match {
  match_id: number; post_id: number; opponent_post_id: number | null; proposal_id: number | null;
  booking_id: number | null; match_time: ISODateTime; status: 'SUGGESTED' | 'CONFIRMED' | 'COMPLETED' | 'CANCELLED';
  confirmed_at: ISODateTime | null;
}
export type NotificationType = 'MATCH_PROPOSAL' | 'PROPOSAL_ACCEPTED' | 'PROPOSAL_REJECTED'
  | 'BOOKING_HOLD' | 'BOOKING_CONFIRMED' | 'PAYMENT_SUCCESS' | 'TEAM_JOINED' | 'POST_EXPIRED'
  | 'PROPOSAL_EXPIRED' | 'MATCH_CONFIRMED' | 'MATCH_CANCELLED' | 'BOOKING_EXPIRED'
  | 'REFUND_PROCESSING' | 'REFUND_SUCCESS' | 'REFUND_FAILED';
export interface Notification {
  notification_id: number; notification_type: NotificationType; title: string; content: string;
  is_read: boolean; created_at: ISODateTime; read_at: ISODateTime | null;
  proposal_id: number | null; match_id: number | null;
}
export interface Pitch {
  pitch_id: number; complex_id: number; pitch_name: string; pitch_type: PitchType;
  price_per_slot: Money; status: 'ACTIVE' | 'MAINTENANCE' | 'INACTIVE';
}
export interface FieldComplex {
  complex_id: number; name: string; phone: string; address: string;
  policy: { hold_seconds: number; slot_duration_minutes: number; deposit_mode: 'PERCENT' | 'FIXED';
    deposit_value: Money; opening_time: string; closing_time: string };
}
export interface Availability {
  pitch_id: number; date: string; slot_duration_minutes: number;
  slots: { start_time: ISODateTime; end_time: ISODateTime; status: 'AVAILABLE' | 'HELD' | 'BOOKED' | 'MAINTENANCE' }[];
}
export type BookingStatus = 'PENDING_HOLD' | 'CONFIRMED' | 'CANCELLED' | 'EXPIRED' | 'MAINTENANCE';
export interface PayerProgress {
  user_id: number; required_amount: Money; paid_amount: Money; status: 'UNPAID' | 'PARTIAL' | 'PAID';
}
export interface Booking {
  booking_id: number; pitch_id: number; user_id: number; start_time: ISODateTime; end_time: ISODateTime;
  total_amount: Money; deposit_amount: Money; booking_type: 'ONLINE' | 'MANUAL_ADMIN' | 'MAINTENANCE_LOCK';
  status: BookingStatus; hold_expires_at: ISODateTime | null; payment_rule: BookingPaymentRule | null;
  payer_progress: PayerProgress[]; created_at: ISODateTime;
}
export interface BookingCreate { pitch_id: number; start_time: ISODateTime; end_time: ISODateTime }
export interface MatchDetail extends Match {
  end_time: ISODateTime; proposal: Proposal; teams: Team[]; booking: Booking | null; payer_progress: PayerProgress[];
}
export type PaymentMethod = 'VNPAY' | 'MOMO' | 'CASH' | 'BANK_TRANSFER';
export type PaymentType = 'BOOKING_DEPOSIT' | 'BOOKING_REMAINING_PAYMENT' | 'REFUND' | 'MATCH_HOST_DEPOSIT' | 'MATCH_JOIN_DEPOSIT';
export type PaymentStatus = 'PENDING' | 'SUCCESS' | 'FAILED' | 'REFUND_PROCESSING' | 'REFUNDED';
export interface Payment {
  payment_id: number; booking_id: number | null; post_id: number | null; amount: Money;
  payment_type: PaymentType; payment_method: PaymentMethod; status: PaymentStatus;
  transaction_code: string | null; refund_for_payment_id: number | null; paid_at: ISODateTime | null;
}
export interface DepositRequest { booking_id: number; payment_method: 'VNPAY' | 'MOMO' }
export interface PaymentSession extends Payment { payment_url?: string; qr_payload?: string; expires_at: ISODateTime }
export interface RevenueAmounts { gross_receipts: Money; refunds: Money; net_receipts: Money }
export interface RevenueReport {
  currency: 'VND'; period: 'day' | 'month' | 'year'; from: string; to: string; time_zone: string;
  items: (RevenueAmounts & { period_start: string })[]; totals: RevenueAmounts;
}
export interface BookingStatistics {
  total_bookings: number; confirmed_bookings: number; cancelled_bookings: number; expired_bookings: number;
  refunded_booking_count: number;
  by_pitch: { pitch_id: number; pitch_name: string; total_bookings: number; utilization_rate: number }[];
  peak_hours: { hour: number; booking_count: number }[];
}
