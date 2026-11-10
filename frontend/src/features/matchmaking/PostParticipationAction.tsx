import type { PostSummary } from '../../types/api';

export function acceptsParticipant(post: PostSummary) {
  return post.post_type === 'RECRUIT_MEMBERS' && post.status === 'OPEN'
    && post.team_id !== null && (post.required_players ?? 0) > 0
    && Date.parse(post.expiry_time) > Date.now();
}

export function PostParticipationAction({ post, isPlayer, isOwner, busy, onApply }: {
  post: PostSummary; isPlayer: boolean; isOwner: boolean; busy: number | null;
  onApply: (post: PostSummary) => void;
}) {
  if (!isPlayer || isOwner || post.status !== 'OPEN') return null;
  if (post.post_type === 'LOOK_FOR_TEAM') {
    return <small>Người chơi đang tìm đội để tham gia. Đội cần người hãy tạo bài Tuyển thành viên.</small>;
  }
  if (!acceptsParticipant(post)) return null;
  return <button className="secondary" disabled={busy !== null} onClick={() => onApply(post)}>
    {busy === post.post_id ? 'Đang gửi…' : 'Đăng ký tham gia'}
  </button>;
}
