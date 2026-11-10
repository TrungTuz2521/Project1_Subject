import { expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { PostParticipationAction } from './PostParticipationAction';
import type { PostSummary } from '../../types/api';

const recruitment: PostSummary = {
  post_id: 1, title: 'Team needs players', post_type: 'RECRUIT_MEMBERS', team_id: 1,
  pitch_id: null, pitch_type: 'PITCH_7', match_time: null, end_time: null,
  skill_level: 'AMATEUR', payment_rule: 'SPLIT_EQUAL', required_players: 2,
  current_players: 5, expiry_time: new Date(Date.now() + 3600000).toISOString(), status: 'OPEN',
};
const render = (patch: Partial<PostSummary> = {}, isOwner = false, isPlayer = true) => renderToStaticMarkup(
  <PostParticipationAction post={{ ...recruitment, ...patch }} isPlayer={isPlayer} isOwner={isOwner} busy={null} onApply={vi.fn()} />,
);

it('shows apply only for an open recruitment post with room for another player', () => {
  expect(render()).toContain('Đăng ký tham gia');
  for (const patch of [{ post_type: 'FIND_OPPONENT' }, { post_type: 'RANDOM_SQUAD' },
    { required_players: 0 }, { team_id: null }, { status: 'LOCKED' },
    { expiry_time: '2020-01-01T00:00:00Z' }] as Partial<PostSummary>[]) {
    expect(render(patch)).not.toContain('Đăng ký tham gia');
  }
  expect(render({}, true)).not.toContain('Đăng ký tham gia');
  expect(render({}, false, false)).not.toContain('Đăng ký tham gia');
});

it('explains that LOOK_FOR_TEAM is a player seeking a team, rather than a recruiting team', () => {
  const html = render({ post_type: 'LOOK_FOR_TEAM', team_id: null, required_players: null });
  expect(html).not.toContain('Đăng ký tham gia');
  expect(html).toContain('Người chơi đang tìm đội');
  expect(html).toContain('Tuyển thành viên');
});
