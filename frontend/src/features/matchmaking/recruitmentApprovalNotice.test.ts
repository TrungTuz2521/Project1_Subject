import { expect, it } from 'vitest';
import { recruitmentApprovalNotice } from './recruitmentApprovalNotice';

it('reports immediate membership only when the backend returns an accepted participant', () => {
  expect(recruitmentApprovalNotice('ACCEPTED', 'ACCEPTED')).toEqual({ error: false, text: 'Đã chấp thuận và thêm người chơi vào đội.' });
  expect(recruitmentApprovalNotice('ACCEPTED', 'PENDING').error).toBe(true);
  expect(recruitmentApprovalNotice('ACCEPTED', 'PENDING').text).toContain('khởi động lại backend');
  expect(recruitmentApprovalNotice('DECLINED', 'REJECTED')).toEqual({ error: false, text: 'Đã từ chối yêu cầu tham gia.' });
});
