# Quân số theo buổi đá

Cập nhật tài liệu ngày 08/11/2026 theo phần triển khai ngày 06/11/2026 trên nhánh `integration/team`.

## Quy tắc đã thống nhất

Danh sách thành viên đội là lâu dài. Đội trưởng không cần xóa/thêm thành viên chỉ vì một người nghỉ buổi đá. Khi tạo bài, chọn các thành viên có tài khoản thực sự tham gia và khai báo số người đi cùng ngoài ứng dụng. Người đại diện đăng bài luôn được tính một lần.

| Thông tin | Ý nghĩa |
| --- | --- |
| Thành viên có tài khoản | Tài khoản ACTIVE thuộc đội; hiển thị ở trang Đội bóng |
| Người có tài khoản tham gia buổi đá | Các ID được chọn khi tạo bài, gồm người đăng; sau đó có thể thêm người tuyển được |
| Người ngoài ứng dụng | Số người đi cùng, không tạo tài khoản/TeamMember giả và không tính lại người đã chọn bằng tài khoản |
| Quân số buổi đá | Số tài khoản được chọn + số người ngoài ứng dụng; dùng để xét đủ sân 5/7 |
| Số còn thiếu | Số người của loại sân trừ quân số buổi đá; backend tính cho bài tuyển/ghép nhóm mới |

Ví dụ một đội có thể có 8 tài khoản nhưng hôm nay chỉ 5 người đi đá. Chọn đúng người tham gia hôm nay. Ngày mai có 4 người thì khai báo trong bài ngày mai; danh sách đội lâu dài vẫn giữ nguyên.

## Ví dụ 7 người nhưng chỉ có 3 tài khoản

| Thời điểm | Tài khoản trong buổi | Người ngoài ứng dụng | Tổng buổi đá | Còn thiếu sân 7 |
| --- | ---: | ---: | ---: | ---: |
| Tạo bài tuyển | 1 đội trưởng | 4 | 5 | 2 |
| Ứng viên thứ nhất và đội trưởng cùng xác nhận | 2 | 4 | 6 | 1 |
| Ứng viên thứ hai và đội trưởng cùng xác nhận | 3 | 4 | 7 | 0 |

Danh sách đội lúc cuối có 3 tài khoản là đúng. Bài đăng phải hiển thị 7/7 người, gồm 3 người có tài khoản và 4 người ngoài ứng dụng. Gọi lại xác nhận không cộng lần nữa. Người đã có trong quân số buổi đá không thể đăng ký lại. Thành viên lâu dài chưa được chọn đi buổi này vẫn có thể xin tham gia và xác nhận, không tạo trùng TeamMember.

Nhận người không giữ sân, không thu cọc và không tạo booking. Điều kiện đủ người của bài tìm đối thủ dùng tổng 7 người; tiền cọc sau ghép trận vẫn do hai đại diện đóng theo quy tắc 20% đã chốt.

## Sau khi tuyển đủ

- Đội thường: bài tuyển chuyển MATCHED. Chủ bài mở chi tiết, bấm **Tạo bài tìm đối thủ với quân số này**, kiểm tra lại lịch/hạn nhận yêu cầu rồi bấm **Đăng bài**. Nút chỉ điền form; chưa tạo bài hoặc giữ sân khi chưa gửi.
- Nhóm AI_RANDOM: giữ cơ chế tự tạo bài FIND_OPPONENT khi đủ người và chưa có booking, sao chép cả tài khoản và số người ngoài ứng dụng.
- Quét ghép trận vẫn theo worker/CLI đã có. Đăng bài không đồng nghĩa lập tức có đề xuất, booking hoặc trận CONFIRMED.

Quân số có sẵn được chốt khi tạo bài. Muốn thay người có sẵn hoặc thay số khách, hủy bài còn mở rồi tạo bài mới; không sửa TeamMember mỗi buổi. Sau khi tuyển, backend cập nhật snapshot qua luồng hai xác nhận. Người ngoài ứng dụng đăng ký tài khoản sau này không tự động được chuyển thành một tài khoản trong snapshot cũ; tạo bài mới và bỏ phần khách tương ứng để tránh tính hai lần. Chức năng mời trực tiếp bằng email chưa có trong code hiện tại.

## API và Models

`POST /api/v1/match-posts` bổ sung hai trường:

| Trường | Quy tắc |
| --- | --- |
| `attendance_user_ids` | Mảng ID nguyên dương, không trùng, luôn gồm người đăng. Nếu có đội, chỉ chọn tài khoản PLAYER ACTIVE là thành viên ACTIVE của đội. Chưa có đội thì chỉ chọn chính mình. |
| `guest_players` | Số nguyên từ 0 đến 6; tổng tài khoản + khách không vượt sức chứa sân 5/7. Không gồm lại các tài khoản đã chọn. |
| `required_players` | Bài tuyển/ghép nhóm mới: backend tự tính số còn thiếu; nếu gửi thì phải đúng số tính được. |
| `current_players` | Trường backend tính, client không được gửi để ghi trực tiếp. |

FIND_OPPONENT cần đủ số người của loại sân. RECRUIT_MEMBERS/RANDOM_SQUAD cần còn thiếu người. LOOK_FOR_TEAM là bài của một người: chỉ ID của chính người đăng và 0 khách.

Ví dụ bài tuyển sân 7 đang có 5 người (đổi ID theo dữ liệu thực tế và chọn ngày tương lai trong 10 ngày khi thử):

```json
{
  "post_type": "RECRUIT_MEMBERS",
  "title": "FC A tuyển thêm 2 người",
  "team_id": 1,
  "pitch_type": "PITCH_7",
  "skill_level": "INTERMEDIATE",
  "match_time": "2026-11-09T18:00:00+07:00",
  "end_time": "2026-11-09T19:30:00+07:00",
  "expiry_time": "2026-11-09T16:00:00+07:00",
  "payment_rule": "SPLIT_EQUAL",
  "attendance_user_ids": [2],
  "guest_players": 4,
  "required_players": 2
}
```

Phần quân số trong response sau khi nhận đủ hai người có tài khoản:

```json
{
  "current_players": 7,
  "registered_players": 3,
  "guest_players": 4,
  "required_players": 0,
  "attendance_mode": "SESSION",
  "attendance_user_ids": [2, 3, 4],
  "status": "MATCHED"
}
```

Đây là trích đoạn DTO; response thực vẫn có envelope `data/meta` và các trường bài đăng khác. `attendance_user_ids` nằm ở chi tiết bài, các số đếm nằm ở PostSummary. `Team.active_member_count` vẫn chỉ đếm tài khoản lâu dài.

SQL lưu `match_posts.attendance_plan JSON NULL`, ví dụ `{"user_ids":[2,3,4],"guest_players":4}`. `PostService.party_users` dùng ID trong snapshot để khóa bản ghi, kiểm tra lịch và thông báo; số khách không có danh tính tài khoản để tự kiểm tra lịch. Đội trưởng chịu trách nhiệm khai báo quân số thực tế.

## Dữ liệu cũ và migration

TiDB database `test` dùng chung đã thêm cột qua migration 004 ngày 06/11/2026, giữ nguyên các dòng dữ liệu. Thành viên cùng dùng DB này **không chạy lại V1/V2/V3/004**, chỉ cập nhật code/cấu hình và khởi động lại backend khi đổi code.

Bài có `attendance_plan=NULL` hoặc API client không gửi cả hai trường quân số dùng cách xử lý legacy. `attendance_mode=LEGACY_TEAM` phân biệt với snapshot SESSION của frontend hiện tại. Không tự suy diễn số khách của bài cũ hoặc backfill quân số lịch sử. Tạo bài mới để thử tính năng.

SQL cho môi trường khác chưa cập nhật và cách xác minh: [migration 004](../../database/schema/004_session_attendance_README.md). Mock frontend chưa hỗ trợ payload quân số mới và trả 501; demo tính năng này dùng backend thật với `VITE_USE_MOCKS=false`.

## Demo từng bước

Mỗi bước cần người demo xác nhận kết quả trước khi chuyển bước tiếp. Dùng database thử nghiệm cho các bước tạo/cập nhật dữ liệu.

1. Đội trưởng đăng nhập, xem Đội bóng: đọc số **thành viên có tài khoản**.
2. Mở Ghép đội & tìm trận → Tạo bài đăng → Tuyển thành viên → chọn đội và sân 7. Chọn người đại diện, khai báo 4 người ngoài ứng dụng. Xác nhận màn hình hiển thị **5/7, còn thiếu 2**; chưa gửi form ở bước này.
3. Điền tiêu đề, giờ 18:00–19:30 ở ngày tương lai trong 10 ngày và hạn bài sau hiện tại, trước hoặc bằng giờ đá. Đăng bài, đọc lại chi tiết: 5 người, 1 tài khoản, 4 khách, thiếu 2.
4. Dùng tài khoản ứng viên ở trình duyệt/phiên riêng, đăng ký bài. Đội trưởng và ứng viên đều xác nhận proposal. Đọc lại: 6 người, 2 tài khoản, 4 khách, thiếu 1.
5. Lặp với ứng viên thứ hai. Xác nhận: 7 người, 3 tài khoản, 4 khách, thiếu 0, bài MATCHED; danh sách đội có 3 tài khoản nếu ban đầu chỉ có đội trưởng.
6. Đội trưởng bấm **Tạo bài tìm đối thủ với quân số này**, kiểm tra form giữ đúng 3 tài khoản + 4 khách. Gửi bài FIND_OPPONENT; không phải thêm tài khoản giả để vượt điều kiện đủ đội.
7. Thử ngày khác chỉ có 4 người: tạo bài mới với 1 tài khoản + 3 khách và chọn Tuyển thành viên sân 5; màn hình thiếu 1. Danh sách đội lâu dài không bị giảm vì người khác nghỉ.

Kiểm thử đã ghi nhận ngày 06/11: 131 backend đạt, 14 ca concurrency chưa chạy vì chưa cấu hình DB thử nghiệm có row locking; frontend 26 đạt và build thành công. Giao diện đã xác minh 1+4=5/7, thiếu 2. Ca nhận thêm hai tài khoản và chống cộng trùng được kiểm thử trên SQLite cô lập, không tạo booking/thu tiền thử trong TiDB nhóm.
