import { ApiError, errorMessage } from './api';

const labels: Record<string, string> = {
  current_password: 'Mật khẩu hiện tại', new_password: 'Mật khẩu mới', confirm_password: 'Nhập lại mật khẩu',
  attendance_user_ids: 'Người có tài khoản tham gia', guest_players: 'Người ngoài ứng dụng',
  team_id: 'Đội bóng', match_time: 'Giờ bắt đầu', end_time: 'Giờ kết thúc',
  expiry_time: 'Hạn nhận yêu cầu', pitch_type: 'Loại sân', pitch_id: 'Sân',
  title: 'Tiêu đề', skill_level: 'Trình độ', payment_rule: 'Quy tắc chia tiền',
  required_players: 'Số người cần tuyển', description: 'Mô tả', post_type: 'Loại bài đăng',
};

/** Preserve field reasons returned by the backend rather than only its generic 422 message. */
export function formErrorMessage(error: unknown): string {
  const summary = errorMessage(error);
  if (!(error instanceof ApiError)) return summary;
  const details = Object.entries(error.fields).flatMap(([key, value]) =>
    (Array.isArray(value) ? value : [value]).filter(Boolean).map(reason => `${labels[key] ?? key}: ${reason}`));
  return details.length ? `${summary} ${details.join(' ')}` : summary;
}
