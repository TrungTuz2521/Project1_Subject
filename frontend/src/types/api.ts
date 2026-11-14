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
export type TeamPaymentRule = 'SPLIT_EQUAL' | 'LOSER_PAYS_REMAINDER';
export type BookingPaymentRule = TeamPaymentRule | 'DIRECT_BOOKING';
export interface ChangePasswordRequest { current_password: string; new_password: string; confirm_password: string }
export interface UserSelf {
  has_password?: boolean;
  user_id: number; full_name: string; email: string; phone: string | null;
  role: 'PLAYER' | 'ADMIN'; skill_level: SkillLevel; status: 'ACTIVE' | 'BANNED' | 'INACTIVE';
  /** Where the venue sends a bank refund. */
  refund_bank_name?: string | null; refund_account_no?: string | null; refund_account_name?: string | null;
}
export interface LoginRequest { email: string; password: string }
export interface RegisterRequest extends LoginRequest { full_name: string; phone?: string; skill_level?: SkillLevel }
export interface LoginData { access_token: string; expires_in: number; user: UserSelf }
export type ProfileUpdate = Partial<Pick<UserSelf, 'full_name' | 'phone' | 'skill_level' | 'refund_bank_name' | 'refund_account_no' | 'refund_account_name'>>;
export interface Team {
  team_id: number; team_name: string; created_by: number | null;
  creation_type: 'USER_CREATED' | 'AI_RANDOM'; status: 'ACTIVE' | 'INACTIVE';
  /** Head count of the team's latest opponent request; players are not on record. */
  last_player_count: number | null;
}
export interface TeamCreate { team_name: string }
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
  /** Price inside the complex's peak hours; null = same price all day. */
  peak_price_per_slot?: Money | null;
}
export interface FieldComplex {
  complex_id: number; name: string; phone: string; address: string;
  policy: { hold_seconds: number; slot_duration_minutes: number; deposit_mode: 'PERCENT' | 'FIXED';
    deposit_value: Money; opening_time: string; closing_time: string };
}
export interface Availability {
  pitch_id: number; date: string; slot_duration_minutes: number;
  slots: { start_time: ISODateTime; end_time: ISODateTime; status: 'AVAILABLE' | 'HELD' | 'BOOKED' | 'MAINTENANCE'; price?: Money; is_peak?: boolean }[];
}
export type BookingStatus = 'PENDING_HOLD' | 'CONFIRMED' | 'CANCELLED' | 'EXPIRED' | 'MAINTENANCE';
export interface PayerProgress {
  user_id: number; required_amount: Money; paid_amount: Money; status: 'UNPAID' | 'PARTIAL' | 'PAID';
  /** Admin views only. */
  full_name?: string | null; phone?: string | null;
}
export interface Booking {
  is_demo?: boolean;
  booking_id: number; pitch_id: number; user_id: number; start_time: ISODateTime; end_time: ISODateTime;
  total_amount: Money; deposit_amount: Money; booking_type: 'ONLINE' | 'MANUAL_ADMIN' | 'MAINTENANCE_LOCK';
  status: BookingStatus; hold_expires_at: ISODateTime | null; payment_rule: BookingPaymentRule | null;
  payer_progress: PayerProgress[]; created_at: ISODateTime;
  /** Paid so far (net of refunds), still due at the pitch, and the pitch name. */
  paid_amount?: Money; outstanding_amount?: Money; pitch_name?: string | null;
}
export interface BookingCreate { pitch_id: number; start_time: ISODateTime; end_time: ISODateTime }
export type PaymentMethod = 'VNPAY' | 'MOMO' | 'CASH' | 'BANK_TRANSFER';
export type PaymentType = 'BOOKING_DEPOSIT' | 'BOOKING_REMAINING_PAYMENT' | 'REFUND' | 'MATCH_HOST_DEPOSIT' | 'MATCH_JOIN_DEPOSIT';
export type PaymentStatus = 'PENDING' | 'SUCCESS' | 'FAILED' | 'REFUND_PROCESSING' | 'REFUNDED';
export interface Payment {
  is_demo?: boolean;
  payment_id: number; booking_id: number | null; post_id: number | null; amount: Money;
  payment_type: PaymentType; payment_method: PaymentMethod; status: PaymentStatus;
  transaction_code: string | null; refund_for_payment_id: number | null; paid_at: ISODateTime | null;
}
export interface BankDepositPayer extends PayerProgress {
  due_amount: Money; transfer_reference: string; qr_payload: string | null;
  unavailable_reason: string | null; can_confirm: boolean; full_name?: string;
  /** SePay: this payer may ask for a 60-second QR code that confirms itself when the bank reports the money. */
  can_open_qr?: boolean; qr_session?: QrPaymentSession | null;
}
/** One short-lived QR code; amount and transfer content are pre-filled and owned by the server. */
export interface QrPaymentSession {
  payment_id: number; booking_id: number; status: PaymentStatus; amount: Money; transfer_reference: string;
  qr_payload: string; qr_expires_at: ISODateTime; hold_expires_at: ISODateTime;
  bank_name: string; account_no: string; account_name: string;
}
export interface DemoDepositResult { demo: true; payment: Payment; booking: Booking }
export interface BankDepositInstructions {
  demo_payment_enabled?: boolean; qr_auto_confirm?: boolean; qr_ttl_seconds?: number;
  booking_id: number; status: BookingStatus; expires_at: ISODateTime | null; payment_method: 'BANK_TRANSFER';
  bank_bin: string | null; bank_name: string; account_no: string | null; account_name: string | null;
  payers: BankDepositPayer[];
}
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

/** Booking-wide amounts for the Admin's settlement. Money is serialized as strings. */
export interface BookingBalance {
  booking_id: number; payment_rule: BookingPaymentRule | null; total_amount: Money;
  deposit_collected_amount: Money; remaining_collected_amount: Money;
  collected_amount: Money; outstanding_amount: Money;
  payment_status: 'UNPAID' | 'PARTIAL' | 'PAID';
  qr_payload: string | null; transfer_reference: string | null; qr_unavailable_reason: string | null;
}
export interface ManualReceipt {
  payment_method: 'CASH' | 'BANK_TRANSFER'; amount: Money; reference?: string;
}
export interface ConfirmBookingPaid {
  expected_outstanding: Money; idempotency_key: string; receipts: ManualReceipt[];
}
export type BookingPhase = 'UPCOMING' | 'IN_PROGRESS' | 'ENDED_UNPAID' | 'PAID';
export type ArrivalStatus = 'ARRIVED' | 'NO_SHOW';
export interface AdminBooking extends Booking {
  customer?: AdminContact;
  /** Shared by a regular customer's weekly sessions. */
  series_id?: string | null; arrival_status?: ArrivalStatus | null; arrived_at?: ISODateTime | null;
  teams?: { source: { team_name?: string }; opponent: { team_name?: string } } | null;
  balance?: BookingBalance | null;
}

/** Admin: a refund still owed. manual = CASH/BANK_TRANSFER (incl. SePay); the Admin pays it back by hand. */
export interface PendingRefund extends Payment {
  manual: boolean; note?: string | null;
  payer: { user_id: number; full_name: string | null; email: string | null; phone: string | null;
    refund_account?: { bank_name: string; account_no: string; account_name: string } | null };
  original: { payment_id: number; transaction_code: string | null; payment_type: PaymentType; paid_at: ISODateTime | null; note: string | null } | null;
}

/** Admin: contact details of a customer. */
export interface AdminContact { user_id: number; full_name: string | null; phone: string | null; email: string | null; walk_in?: boolean; no_show_count?: number }
export interface AdminUser { user_id: number; full_name: string; email: string | null; phone: string | null; role: 'PLAYER' | 'ADMIN'; status: string; walk_in?: boolean; no_show_count?: number }
/** Counter customer without an account: only a name and a phone number. */
export interface WalkInGuest { full_name: string; phone: string }
export interface AdminBookingQuery {
  phase?: BookingPhase | 'DUE'; status?: BookingStatus; from?: string; to?: string; page?: number; page_size?: number; series_id?: string;
}
export interface PeakHours { peak_start_time: string | null; peak_end_time: string | null; weekend_is_peak: boolean }
export interface SeriesResult {
  series_id: string; requested_weeks: number;
  created: { booking_id: number; start_time: ISODateTime; total_amount: Money }[];
  skipped: { start_time: ISODateTime; reason: string }[];
}
/** VENUE: the pitch could not be used, refund everything. CUSTOMER: the customer cancelled, the deposit is kept. */
export type CancelCause = 'VENUE' | 'CUSTOMER';
export interface AdminDashboard {
  today: string;
  revenue_today: { gross_receipts: Money; refunds: Money; net_receipts: Money };
  pending_holds: { count: number; items: AdminBooking[] };
  pending_refunds: { count: number; amount: Money };
  ended_unpaid: { count: number; outstanding_amount: Money; items: AdminBooking[] };
  today_games: { count: number; items: AdminBooking[] };
  /** Work the scheduler should already have done; lagging = it is probably not running. */
  background_jobs?: { lagging: boolean; expired_holds: number; expired_requests: number; unsent_emails: number };
}
