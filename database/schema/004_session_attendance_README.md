# Quân số theo buổi đá — migration 004

TiDB database test dùng chung đã áp dụng thành công ngày 06/11/2026: attendance_plan JSON nullable, số dòng match_posts được giữ nguyên. Thành viên cùng dùng DB này không cần chạy lại. Các bước bên dưới dành cho database khác chưa có cột.

Chỉ bổ sung `match_posts.attendance_plan JSON NULL`; không cập nhật/xóa dữ liệu cũ, không chạy lại V1/V2/V3. Chọn đúng database, chạy `004_session_attendance.sql` trước khi khởi động backend mới. Kết quả xác minh cần `attendance_plan | json | YES`.

`attendance_plan` là snapshot quân số của từng bài đăng: `{"user_ids":[2,3,4],"guest_players":4}`. Không lưu người ngoài ứng dụng thành tài khoản giả hoặc TeamMember giả. `current_players` là tổng người tham gia buổi đá; `required_players` là số còn thiếu. Danh sách thành viên lâu dài của đội chỉ đếm tài khoản ACTIVE và không đổi khi người chơi nghỉ một buổi.

PostCreate mới nhận `attendance_user_ids` (ID tài khoản có tham gia, luôn gồm người đăng) và `guest_players` (người ngoài ứng dụng, không tính lại các tài khoản đã chọn). Backend kiểm tra ID không trùng, thuộc thành viên ACTIVE của đội, tổng quân số đúng loại sân. Bài Tìm đội của cá nhân chỉ có chính người đăng và không có khách. Không tin `current_players` từ client.

Ví dụ sân 7: `[đội trưởng] + guest_players=4` => có 5 người, tuyển thêm 2. Sau khi cả hai bên đồng ý mỗi đề xuất, thêm tài khoản ứng viên vào snapshot đúng một lần, giữ 4 khách: tổng 7 người, 3 tài khoản. Danh sách đội có 3 tài khoản là đúng. Nhận người không tạo booking/thu cọc.

Khi bài tuyển thường đủ người, đóng bài và cho đội trưởng bấm **Tạo bài tìm đối thủ với quân số này**; không tự đăng thay đội trưởng. Nhóm AI_RANDOM giữ cơ chế tự tạo FIND_OPPONENT, sao chép cả quân số/tài khoản/khách. Ghép đối thủ dựa trên tổng `current_players`; kiểm tra trùng lịch và thông báo chỉ làm được với các tài khoản được chọn. Đội trưởng tự bảo đảm quân số/người ngoài ứng dụng không bị tính trùng hoặc trùng lịch.

Snapshot cố định khi tạo; muốn thay người có sẵn thì tạo bài mới (hủy bài cũ trước nếu còn mở). Tuyển thêm chỉ cộng người sau đồng thuận. Người đã có trong snapshot không thể đăng ký lại; thành viên lâu dài chưa được chọn cho buổi này vẫn có thể đăng ký. Không cộng lại số khách vào đội lâu dài và không tự biến khách thành tài khoản khi họ đăng ký sau này.

`attendance_plan=NULL` giữ cách đọc legacy của bài cũ; không suy diễn lịch sử khách. API trả `attendance_mode=LEGACY_TEAM` cho những bài đó. Bài gửi từ frontend hiện tại có snapshot trả SESSION; API client cũ bỏ cả hai trường quân số vẫn dùng legacy. Các số đếm gồm `registered_players`, `guest_players`; chi tiết bài thêm `attendance_user_ids`. Dùng bài mới để thử tính năng, tránh sửa trực tiếp lịch sử.

Kiểm thử: SQLite trong bộ nhớ, không dùng TiDB để tạo/hủy booking thử. Bao gồm 1+4 khách tìm đối, tuyển thêm 2 thành 7 nhưng đội có 3 tài khoản, retry không đếm trùng, cùng đội hai ngày khác quân số, từ chối ID ngoài đội/trùng/thiếu người đại diện, thành viên có sẵn đăng ký thêm cho buổi, nhóm random sao chép khách. Các bài test đồng thời vẫn cần database thử nghiệm riêng có row locking.

Hoàn tác tính năng: quay lại code trước đó; để cột nullable tồn tại. Không DROP cột nếu đã có snapshot được ghi.

Hiện chỉ đội trưởng có trong `user_ids`; số người còn lại nằm ở `guest_players` (xem backend/README.md, mục Quân số buổi đá). Cập nhật tài liệu ngày 08/11/2026 không chạy thêm migration hoặc backfill nào.
