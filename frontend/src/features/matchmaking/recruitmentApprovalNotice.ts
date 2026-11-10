import type { Participant } from '../../types/api';

export function recruitmentApprovalNotice(decision: 'ACCEPTED' | 'DECLINED', status: Participant['status']) {
  if (decision === 'DECLINED') return { error: false, text: 'Đã từ chối yêu cầu tham gia.' };
  if (status === 'ACCEPTED') return { error: false, text: 'Đã chấp thuận và thêm người chơi vào đội.' };
  return { error: true, text: 'Người chơi chưa được thêm vào đội. Hãy khởi động lại backend để nạp luồng tuyển thành viên mới rồi thử duyệt lại.' };
}
