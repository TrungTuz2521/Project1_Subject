# Backend Đức — cập nhật ngày 29/10/2026

## Đã triển khai

- Flask app factory, cấu hình TiDB/TLS/UTC, CORS, error envelope/data/meta, kiểm tra JSON và phân trang.
- SQLAlchemy Models phần Đức ánh xạ schema V3. Không tạo bảng/migration khi khởi động.
- UnitOfWork, khóa thứ tự users → teams → pitches → posts → proposal → confirmation → match → booking → payment → membership; retry conflict DB xác định tối đa 3 lần.
- Đăng ký PLAYER bằng bcrypt; đăng nhập JWT HS256 hạn 3600 giây; kiểm tra issuer/audience/exp, tài khoản ACTIVE và vai trò hiện tại; GET/PATCH hồ sơ.
- Tạo/sửa/xem đội, Captain/member permissions, rời/xóa thành viên; không rời đội khi có trận hoạt động.
- Tạo/sửa/tìm bài, kiểm tra lịch UTC/giờ Việt Nam, lưới 90 phút từ 06:00, tối đa 10 ngày, không nhận tiền/status/số người tự khai.
- Chấm điểm AI theo quy tắc, ngưỡng 80, lọc loại sân/slot/trình độ/thể thức/người chơi khả dụng; không dùng mô hình huấn luyện.
- Proposal hai xác nhận; từ chối/hết hạn mở lại bài; nhận người/gom nhóm AI_RANDOM không tạo booking; đủ nhóm sinh bài tìm đối thủ.
- Thông báo IN_APP; CLI quét và hết hạn để scheduler gọi.
- Điểm nối giữ sân/đủ cọc/hủy và đọc hai đội cho Tú; từ chối 503 khi chưa có booking/cancellation implementation thật.

## Kết quả xác minh

`backend/.venv/Scripts/python.exe -m unittest discover -s tests -v` từ thư mục backend:
**25 ca kiểm thử đạt** ở lần chạy ngày 29/10/2026 (22 ca cũ và 3 ca điểm nối/DTO mới). Tests dùng SQLite riêng, không ghi database dùng chung.
Lần kiểm tra `check-db` ngày 28/10/2026 trên TiDB: TLS kết nối thành công, toàn bộ cột Models Đức hiện có trong database.
Chỉ đọc metadata, không chạy migration, không đổi dữ liệu hoặc mật khẩu mẫu.

| Nhóm | Các ca đã kiểm tra |
| --- | --- |
| Auth | Hash bcrypt, đăng nhập, cập nhật hồ sơ, email chuẩn hóa; trùng email, gán role trái phép, mật khẩu UTF-8 quá dài, seed plaintext bị từ chối |
| Phiên/quyền | JWT hết hạn, user BANNED, trường hồ sơ bị cấm, giới hạn Auth, CORS preflight |
| Đội/bài | Captain và quyền riêng tư, phân trang, đội chưa đủ người, protected fields, JSON/null/date sai |
| AI | Ngưỡng skill, khác thể thức không ghép, không tạo proposal trùng khi scan lại, chặn lịch tham gia chồng lấn |
| Xác nhận | Từ chối/gọi lặp/đổi phản hồi; hết hạn được lưu; thiếu adapter rollback xác nhận cuối |
| Tích hợp booking | Test adapter giả tạo một hold và Match SUGGESTED; hết sân lưu Match CANCELLED/mở lại bài; chỉ tổng cọc một người không đủ; hết hold không hồi sinh; hủy gọi lặp |
| Tuyển/gom nhóm | Phải đủ hai xác nhận, không thêm trùng, không tạo booking; RANDOM_SQUAD tạo AI_RANDOM; join response và rút đăng ký |
| Thông báo | Người lạ không đọc/đánh dấu thông báo của người khác; worker hết hạn chạy lặp không lặp sự kiện |

## Ghép code tiếp theo

Tú gắn adapter theo `backend/README.md`; phải kiểm thử lại cùng Booking/Payment thật trên database staging.
SQLite không kiểm chứng được FOR UPDATE/deadlock/concurrent TiDB. Các ca hai request đồng thời,
callback đối đầu timeout/hủy và xử lý gateway thật vẫn phải chạy sau khi ghép phần Tú.

Dminh dùng các route Auth hiện có trong hợp đồng, chuyển `VITE_USE_MOCKS=false` và cấu hình API URL.
Số điện thoại tối đa **20 ký tự** theo cột TiDB; frontend nên đồng bộ validator 20 (bản ZIP đang kiểm tra 30).
Không cần đổi endpoint hoặc response Auth.

Email, audit/outbox và hạ tầng thanh toán sau V3 cần bộ migration chung được review trước khi dùng.
Bản này chỉ gửi IN_APP, không giả trạng thái email SENT. Chưa triển khai Booking/Payment/balance/QR chung/xác nhận thu đủ của Tú,
không sửa seed plaintext để lách bcrypt, không nhận Google Login hoặc refresh token ngoài phạm vi đã chốt.

## Thay đổi luồng sau trận ngày 29/10/2026

- Bỏ booking_settlements khỏi giao thức khóa, không tạo bảng/cột mới hoặc chạy migration.
- Đổi điểm đọc thông tin đội thành get_booking_parties; chỉ trả tên/đại diện, không chia tiền hoặc chọn kết quả.
- Bổ sung BookingBalance, ManualReceipt và BookingBalancePort làm hợp đồng cho Tú; chưa triển khai service tiền của Tú.
- Cập nhật README và hợp đồng API/service: QR chung, hai đội tự chia tiền, Admin xác nhận thu đủ; có kiểm tra số dư cũ,
  mã chống trùng, khoản thu nhiều lần/trộn phương thức và tài khoản quy chiếu của thu gộp.
- Các test cọc trước trận vẫn áp dụng; 3 test mới kiểm tra điểm đọc hai đội không phân bổ tiền, đặt trực tiếp không tạo đội giả và serialization DTO số dư/receipt. Tổng 25/25 test đạt; chưa kiểm chứng phép tính tiền/service thu của Tú.
- File Excel ngày 28/10 là báo cáo lịch sử 22 ca. Ca kế hoạch INT-06 theo thắng/thua trong file đó đã được thay thế:
  kiểm thử mới cần tổng thiếu 480000 cho cả hai thể thức, QR chung, nhiều khoản CASH/BANK_TRANSFER, xác nhận lặp/hai tab.
- Cần kiểm thử staging phần Tú: số dư giảm sau khoản đã ghi; QR không tự ghi SUCCESS; tổng receipt sai bị chặn;
  đủ tiền không ghi thêm, key cũ không đổi payload; PLAYER/booking chưa hết giờ không xác nhận được.
