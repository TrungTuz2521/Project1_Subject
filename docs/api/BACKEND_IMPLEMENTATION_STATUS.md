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

## Phần Tú — cập nhật ngày 01/11/2026 (nhánh feature/tu-booking-payment, chưa merge)

Đã triển khai theo API 1.8 và service contract 1.1: Models FieldComplex/Pitch/Booking/Payment; danh sách sân, availability, giữ sân; cọc qua VNPay, IPN; hết hạn, hủy, hoàn tiền; số dư, QR chung, xác nhận thu đủ, ghi thu tại quầy; Admin sân/lịch/khóa bảo trì/giao dịch; doanh thu, thống kê, Excel. Điểm nối `booking_service`, `booking_reader`, `cancel_match` đã đăng ký thật, nên luồng hai xác nhận và hủy trận không còn trả 503. Không tạo bảng, cột hay migration; không có `booking_settlements`.

### Kết quả xác minh

`python -m unittest discover -s tests` từ thư mục backend: **139 ca đạt**, gồm 25 ca của Đức, 100 ca nghiệp vụ tiền/booking trên SQLite và 14 ca đồng thời. Không đặt `TEST_DATABASE_URL` thì 14 ca đồng thời được bỏ qua.

14 ca đồng thời đã chạy trên một MySQL 8.4 tạm tại máy, READ COMMITTED. Khi tắt `FOR UPDATE` trong tiến trình test, 7/14 ca đỏ, nên các ca này có kiểm chứng được khóa. Test tạo và xóa toàn bộ bảng, vì vậy chỉ chạy khi host là local và tên database kết thúc bằng `_test`; database dùng chung không bao giờ thỏa điều kiện này.

### Chưa kiểm chứng

- **TiDB:** chưa chạy trên TiDB staging, chưa chạy `check-db` với các Model mới. Bảng test do `create_all` tạo dùng VARCHAR thay cho ENUM, nên chưa so khớp được với ENUM thật. Mục 14 của hợp đồng yêu cầu staging trước khi merge.
- **VNPay thật:** adapter viết theo tài liệu sandbox, mới kiểm tra chữ ký/URL/IPN bằng secret giả và lỗi mạng. querydr/refund chưa gọi thật. Tài liệu VNPay thiếu một dấu `|` trong chuỗi checksum response của querydr; code dùng dấu `|` đầy đủ, cần xác nhận khi có tài khoản sandbox.
- **MoMo:** chưa tích hợp, trả 422 UNSUPPORTED_PAYMENT_METHOD.

### Giới hạn cần biết

- **Một worker hoàn tiền:** `process-refunds` chỉ chạy một tiến trình. Chưa có outbox/lease nên hai tiến trình song song có thể cùng gửi một yêu cầu hoàn; VNPay được mô tả sẽ từ chối yêu cầu trùng (mã 94) nhưng chưa kiểm chứng.
- **Audit:** chưa có bảng `audit_events`. Nguyên nhân, người thao tác và lý do hủy tạm ghi vào `bookings.note`/`payments.note` (VARCHAR 255, quá dài thì giữ phần mới nhất). Mã giao dịch của cổng cũng ghi ở `payments.note`.
- **Hoàn thất bại:** hàng REFUND FAILED không tự gửi lại, Admin đối soát rồi gọi lại `POST /admin/payments/{id}/refund`.

### Hành vi hợp đồng chưa nói rõ, cần Đức/Huy xem

| Nội dung | Cách đã làm |
| --- | --- |
| Hoàn CASH/BANK_TRANSFER | Không có cổng để hoàn. `POST /admin/payments/{id}/refund` trên giao dịch gốc nghĩa là Admin đã trả tiền, hoàn tất ngay và trả 200; cổng online trả 202 |
| Lưới giờ | Lượt cuối 21:00–22:30, vì lưới 90 phút từ 06:00 không có lượt nào kết thúc đúng 23:00 |
| Người chơi tự hủy | Chặn sau giờ bắt đầu đá (409); Admin vẫn hủy được |
| GET /pitches | Trả cả sân INACTIVE để màn hình Admin mở lại được; đặt sân vẫn từ chối, availability hiện MAINTENANCE |
| Availability | Chỉ nhận từ hôm nay đến 10 ngày tới, không trả slot đã bắt đầu |
| QR chung | Chỉ hiện khi booking CONFIRMED và đã hết giờ đá |
| Phase Admin | UPCOMING/IN_PROGRESS/PAID có thể trùng nhau: booking đã trả đủ trước giờ đá thuộc cả UPCOMING và PAID |

### Việc của thành viên khác

- **Đức:** review `app/__init__.py`, `models/__init__.py` và fixture `tests/test_backend.py` (bỏ bảng tự tạo, dùng Model thật; logic các ca giữ nguyên). `reschedule_booking` có cập nhật giờ trên Match và MatchPost trong cùng transaction, cần xem có muốn chuyển sang match_service không.
- **Huy:** `frontend/src/services/huyApi.ts` vẫn gọi `/settlement*` đã bỏ từ bản 1.8, các route này trả 404. Cần đổi sang `GET /admin/bookings/{id}/balance` và `POST /admin/bookings/{id}/confirm-paid`. Bản demo cho bước 30 phút, backend chỉ nhận lưới 90 phút.
