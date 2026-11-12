# Backend Flask — bản tích hợp nhóm

## Chạy local

Từ thư mục `backend`, tạo virtualenv, cài `python -m pip install -r requirements.txt`.
Sao chép `.env.example` sang `.env`, cấu hình TiDB và `JWT_SECRET_KEY` ngẫu nhiên ít nhất 32 byte.
Không commit `.env`. TiDB test nhóm đã áp dụng V3 và 004 (attendance_plan); không chạy lại các migration này trên database chung. Database khác chưa có cột cần theo [hướng dẫn 004](../database/schema/004_session_attendance_README.md) trước khi chạy code mới.

```powershell
python -m flask --app app:create_app check-db
python run.py
```

`check-db` chỉ đọc kết nối/cột ORM, không sửa schema hoặc tài khoản mẫu. Khi khởi động không gọi create_all.
Kết nối TiDB xác minh TLS và đặt session SQL sang UTC. Server local: `http://localhost:5000/api/v1`.
Transaction dùng READ COMMITTED để đọc lại roster sau khi chờ khóa; conflict/deadlock đã xác định retry tối đa 3 lần
ở ranh giới command, không retry callback/gateway mạng. Auth giới hạn 20 yêu cầu/phút/IP trong process local;
khi chạy nhiều process, cấu hình limiter dùng chung tại reverse proxy.
Frontend: `VITE_API_BASE_URL=http://localhost:5000/api/v1`, `VITE_USE_MOCKS=false`; restart Vite.

## Kiểm thử riêng, không ghi TiDB

```powershell
python -m unittest discover -s tests -v
```

Tests dùng SQLite tạm, tạo schema riêng chỉ trong fixture. SQLite không chứng minh được khóa cạnh tranh TiDB;
cần kiểm thử hai request đồng thời trên database staging trước khi merge tích hợp booking.

## Việc chạy nền

Mọi việc định kỳ (đóng yêu cầu tìm kèo quá hạn, hết hạn giữ sân, đối soát thanh toán, hoàn tiền, quét ghép kèo, gửi email) do **một** tiến trình scheduler chạy, xem mục scheduler bên dưới. Chạy riêng từng việc một lượt để thử:

```powershell
python -m flask --app app:create_app scan-requests     # quét ghép kèo một lượt
python -m flask --app app:create_app close-requests    # đóng yêu cầu đã quá hạn (24 giờ trước giờ đá)
```

Mỗi yêu cầu mới cũng được quét ngay lúc gửi. Mỗi cặp được ghép trong transaction riêng; thông báo IN_APP và EMAIL/PENDING ghi cùng transaction, email gửi sau bởi scheduler `--with-email`. Trang Hôm nay của admin cảnh báo khi việc nền bị trễ (scheduler không chạy).

## Ghép với Tú

Tú import `db` từ `app.extensions`, `Actor`, `BookingHold` từ `app.contracts.dto`, `DomainError`/
`SlotUnavailable` từ `app.contracts.errors`. Không tạo User/Team/Match thứ hai.
Models của Tú đăng ký cùng metadata trước khi phục vụ request.

```python
app.extensions['booking_service'] = booking_service
app.extensions['cancel_match'] = cancel_match_use_case
app.extensions['booking_reader'] = get_booking_for_actor
```

`booking_service.find_match_pitch(ctx, *, pitch_type, start_time, end_time)` đọc tìm một pitch_id hoặc None;
không khóa/ghi dữ liệu. Use case khóa Pitch trước Post theo hợp đồng. `create_match_hold` dùng đúng chữ ký
trong BACKEND_SERVICE_CONTRACT, phải kiểm tra lại overlap/giá/deadline sau khóa và không tự commit.
`SlotUnavailable` phải phát sinh trước khi insert booking. Không thêm transaction/gọi mạng trong adapter này.

Callback của Tú gọi `match_service.confirm_after_deposit(ctx, booking_id=...)` sau khi booking CONFIRMED;
service kiểm tra lại từng phần cọc thực thu, không xác nhận chỉ nhờ tổng tiền hoặc proposal ACCEPTED.
Hủy/hết hold gọi `cancel_for_booking(ctx, booking_id=..., cause=..., actor_id=...)` sau cập nhật booking/refund,
trong cùng transaction và tập khóa. Hàm này không tự xử lý tiền.
Đọc tên hai đội/đại diện để hiển thị dùng `get_booking_parties(ctx, booking_id=...)`; không suy ra nghĩa vụ sau trận.

Bổ sung giao thức khóa: `ctx.locks.users(all_participant_ids)` trước Team/Pitch để chống một người
thuộc nhiều đội nhận hai kèo cùng giờ. Discovery roster rồi khóa và đọc lại roster; roster thay đổi trả
STATE_CONFLICT để retry từ đầu. Các lệnh đổi thành viên phải dùng cùng khóa user → team.

Phần Tú đăng ký booking_service, booking_reader, cancel_match qua `app/booking_module.py`, xem mục Booking và thanh toán bên dưới.
Khi chưa gắn booking_service, xác nhận cuối OPPONENT trả 503, rollback phản hồi cuối để thử lại khi tích hợp.
Không tạo hold giả. Route hủy trận cũng trả 503 khi chưa có orchestration tiền của Tú.
Booking/Payment/balance/QR chung/xác nhận thu đủ/gateway cọc thuộc Tú và đã nối qua booking_module. Email dùng bảng notifications hiện có, không thêm migration. Outbox có lease/retry và audit đầy đủ vẫn cần thiết kế riêng trước khi vận hành lớn; không giả định các bảng mở rộng đã tồn tại.

## Luồng thu tiền mới — 29/10/2026

Đức đã bỏ booking_settlements khỏi LOCK_ORDER và bổ sung BookingBalance, ManualReceipt, BookingBalancePort.
Tú triển khai get_booking_balance và confirm_booking_paid theo protocol; Huy dùng GET balance/POST confirm-paid
trong hợp đồng API 1.8. Một QR ngân hàng cho tổng thiếu; hai đội tự chia, Admin kiểm tra tiền vào rồi xác nhận.
Không có winner/outcome/phân bổ từng đội hoặc payment session quyết toán. Cọc 20%/hai payer trước trận giữ nguyên.
Không tạo bảng/cột mới cho thu gộp; recorded_by_admin_id, paid_at, note, transaction_code trong payments V3 đủ dùng.
Thu gộp dùng booking.user_id làm tài khoản quy chiếu, không đại diện cho người thực chuyển; không áp dụng cho cọc.
Protocol/DTO chỉ mô tả điểm nối; code Đức không giả thành công các endpoint tài chính của Tú.

## Migration 005 — vận hành tại quầy (bắt buộc trước khi chạy bản này)

Chạy **một lần** file [`database/schema/005_operations.sql`](../database/schema/005_operations.sql) trên database đang dùng (TiDB của nhóm). File chỉ `ADD COLUMN IF NOT EXISTS`, không xóa hay sửa dữ liệu cũ; câu `SELECT` cuối phải trả về 7 dòng. Chưa chạy migration thì backend báo lỗi thiếu cột; `flask check-db` liệt kê cột còn thiếu.

Các nghiệp vụ dùng cột mới:

- **Giá cao điểm**: `pitches.peak_price_per_slot`; khung giờ ở `field_complexes.peak_start_time/peak_end_time/weekend_is_peak` (`PATCH /admin/field-complex`). Giá chốt vào booking lúc đặt.
- **Khách cố định**: `POST /admin/bookings` nhận `repeat_weeks` (2–12), các buổi chung `bookings.series_id`; tuần đã có người đặt được bỏ qua và báo lại. Hủy cả chuỗi: `POST /admin/bookings/series/{series_id}/cancel`.
- **Đón khách**: `POST /admin/bookings/{id}/arrival` với `ARRIVED` (từ 2 giờ trước giờ đá), `NO_SHOW` (sau giờ đá) hoặc `null`; lưu `bookings.arrival_status/arrived_at`. Số lần bùng hiện cạnh tên khách.
- **Hủy tại quầy**: `POST /admin/bookings/{id}/cancel` nhận `cause`: `CUSTOMER` (khách hủy, giữ cọc, hoàn phần trả thêm) hoặc `VENUE` (sân có sự cố, hoàn đủ).
- **Thu tiền khi khách đến**: xác nhận thu đủ không còn chờ hết giờ đá; bộ lọc `phase=DUE` là các booking hôm nay trở về trước còn thiếu tiền.
- **Phiên đăng nhập**: `POST /auth/refresh` đổi token còn hạn lấy token mới; frontend giữ phiên khi F5 và khi chọn "Ghi nhớ đăng nhập".

## Tạo tài khoản admin

```powershell
python -m flask --app app:create_app create-admin --email admin@sanbong.vn --name "Quản trị viên"
```

Lệnh hỏi mật khẩu (nhập ẩn, 2 lần). Email chưa có thì tạo tài khoản ADMIN mới; email đã có thì nâng quyền ADMIN và đặt lại mật khẩu (các phiên đăng nhập cũ của tài khoản đó bị đăng xuất). Lệnh ghi vào database đang cấu hình trong `.env`. Tài khoản ADMIN không dùng được các chức năng người chơi (lập đội, đặt sân online), nên dùng email riêng.

## Booking và thanh toán — phần Tú

Điền `VNPAY_*` và `BANK_*` trong `.env` theo `.env.example`. Thiếu `VNPAY_*` thì tạo phiên cọc trả 503; thiếu `BANK_*` thì số dư trả `qr_unavailable_reason`. Không có chế độ giả thành công; `FakeGateway` chỉ nằm trong `tests/`.

```powershell
python -m flask --app app:create_app expire-booking-holds
python -m flask --app app:create_app process-refunds
python -m flask --app app:create_app reconcile-payments
```

Đây là lệnh chạy một lượt. Để các job tự chạy, mở **một** terminal riêng:

```powershell
python -m flask --app app:create_app scheduler --with-matchmaking --with-email
```

`scheduler` chạy mỗi 15 giây: đóng yêu cầu tìm kèo quá hạn (24 giờ trước giờ đá), hết hạn giữ sân, đối soát thanh toán + dọn mã QR SePay, hoàn tiền qua cổng, chuyển trận đã đá xong sang `COMPLETED`. `--with-matchmaking` quét ghép kèo, `--with-email` gửi email (không chạy thêm `email-worker` song song). `--once` chạy một lượt rồi thoát. Chỉ chạy **một** scheduler, vì `process-refunds` chưa có outbox/lease.

Hoàn tiền mặt/chuyển khoản (kể cả QR SePay) không tự chạy: Admin xem mục **Khoản cần hoàn** ở trang Quản lý lịch đặt, trả tiền cho khách rồi bấm "Đã trả tiền" (`GET /admin/refunds/pending`, `POST /admin/payments/{id gốc}/refund`).

IPN VNPay là `GET /api/v1/payments/vnpay/ipn`, phải khai báo URL HTTPS công khai trong tài khoản merchant.

### Test bằng Postman

Import `postman/football_booking.postman_collection.json`, rồi chạy server thử từ thư mục `backend`:

```powershell
python postman/run_local.py
```

Server này luôn dùng SQLite tạm và secret thử, kể cả khi có `.env`, nên không chạm TiDB. Chạy cả collection bằng **Run collection** theo đúng thứ tự. Muốn chạy lại thì khởi động lại server để có dữ liệu mới. Collection tự bỏ qua request nếu `base_url` không phải localhost.

IPN trong collection do script tự ký bằng secret thử, không phải VNPay gọi thật. Collection chỉ gồm route phần Tú; luồng hai đội nằm ở `tests/test_booking_payment.py`.

### Test đồng thời

SQLite không kiểm chứng được khóa. Các ca trong `tests/test_booking_concurrency.py` cần database thật và tự bỏ qua nếu không có `TEST_DATABASE_URL`:

```powershell
$env:TEST_DATABASE_URL = 'mysql+pymysql://USER:PASSWORD@127.0.0.1:3306/project1_test?charset=utf8mb4'
python -m unittest discover -s tests -p 'test_booking_concurrency.py'
```

Test **tạo và xóa toàn bộ bảng**, nên chỉ chạy khi host là local và tên database kết thúc bằng `_test`. Tài khoản MySQL có mật khẩu dùng `caching_sha2_password` có thể cần thêm gói `cryptography`.

## Quân số buổi đá

Đội chỉ có tên và đội trưởng (người đại diện đặt sân, nhận thông báo); không lưu danh sách thành viên. Mỗi yêu cầu tìm đối khai báo `player_count` (tính cả đội trưởng, tối thiểu 5 với sân 5, 7 với sân 7); form điền sẵn số của lần trước (`last_player_count` của đội). `MatchPost.attendance_plan` vẫn lưu `{user_ids: [đội trưởng], guest_players: số còn lại}` để dùng chung cột của migration 004.

Hướng dẫn điền env, đăng ký IPN và thử cọc: [VNPay sandbox](../docs/setup/VNPAY_SANDBOX.md).

## Google Login và email

Đặt `GOOGLE_CLIENT_ID` trong backend env; frontend dùng cùng Client ID và origin đã đăng ký. Xem [Google Login](../docs/setup/GOOGLE_LOGIN.md). Không cần Client Secret hoặc migration; email trùng cần mật khẩu web để liên kết, JWT vẫn 60 phút.

Email cần `EMAIL_ENABLED=true`, `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USERNAME`, `SMTP_PASSWORD` (App Password), `PUBLIC_WEB_URL` trong `.env` riêng. Không commit credential. Máy không test email giữ `EMAIL_ENABLED=false`.

Từ thư mục `backend`, dùng Python của venv:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app check-email
.\.venv\Scripts\python.exe -m flask --app app:create_app email-worker
```

`check-email` chỉ kiểm tra kết nối/đăng nhập SMTP, không gửi thư. `email-worker` là lệnh chạy liên tục ở terminal riêng, kiểm tra mỗi 10 giây. Flask không tự chạy worker. Khởi động lại backend/worker sau khi thay env.
Email mới được xếp hàng cùng giao dịch; worker gọi SMTP sau commit. Không phát lại thông báo cũ, không tự retry FAILED, không coi SMTP chấp nhận là chắc chắn đã vào inbox. Chi tiết claim/failure, giới hạn Gmail và demo: [Email notifications](../docs/setup/EMAIL_NOTIFICATIONS.md).


## Đổi mật khẩu — 10/11/2026

Trong app: **Hồ sơ cá nhân → Đổi mật khẩu**. Nhập mật khẩu hiện tại, mật khẩu mới và nhập lại;
mật khẩu mới dài 8–72 byte UTF-8, khác mật khẩu cũ. Thành công sẽ đăng xuất phiên trên trình duyệt hiện tại
và yêu cầu đăng nhập lại. Sai mật khẩu cũ/nhập lại không khớp không làm đổi dữ liệu.
Tài khoản chỉ dùng Google và chưa có mật khẩu web thì hiện hướng dẫn đổi ở Google; chưa hỗ trợ đặt mật khẩu web đầu tiên.

API: `POST /api/v1/users/me/password`, cần Bearer JWT của chính người dùng.
JSON: `{current_password,new_password,confirm_password}`; trả `{data:{changed:true},meta}`.
Không nhận user_id/role/password_hash; sai dữ liệu trả 422, Google-only trả 409 PASSWORD_NOT_SET,
không có phiên/hết hạn trả 401, tài khoản khóa trả 403. Endpoint có rate limit auth dùng chung.
UserSelf bổ sung boolean `has_password`, không trả hash hay Google ID.
Không có refresh token/revocation: JWT ở thiết bị khác vẫn có thể còn hiệu lực tới exp (tối đa 60 phút từ lúc cấp).
Đây là đổi mật khẩu khi đã biết mật khẩu cũ; chưa phải chức năng Quên mật khẩu/Reset email.
Không cần migration hoặc thay mật khẩu thật khi cài code.


## Cọc QR và nút xác nhận demo lưu TiDB — 10/11/2026

Đã có **Booking của tôi → Đóng cọc bằng chuyển khoản → Xác nhận thanh toán cọc (demo)**.
QR hiển thị đúng người nhận, số tiền còn thiếu của người đang đăng nhập và nội dung riêng theo booking/người trả.
Nút demo gọi backend ghi Payment SUCCESS có mã/ghi chú DEMO, rồi đổi trạng thái booking/trận khi đủ cọc.
Đặt trực tiếp cọc 20%; hai đội mỗi đội 10%, chỉ đủ cả hai mới xác nhận trận. Không cần Admin duyệt cọc mới.
Đây là mô phỏng, không chứng minh chuyển khoản ngân hàng. Khoản DEMO không tính doanh thu API, không hoàn/thu tiền thật.
Giữ nguyên hạn 5 phút; không trộn với phiên thanh toán/giao dịch thật. Khi demo xong cần hủy booking nếu muốn nhả slot.

Backend bật `DEMO_PAYMENT_ENABLED=true`; frontend dev bật `VITE_DEMO_DEPOSIT=true` và `VITE_USE_MOCKS=false`.
Sau pull code phải cấu hình env local, khởi động lại backend/Vite. Mặc định env.example tắt demo; production phải tắt cả hai flag.
Chi tiết cách chạy, API, flag và giới hạn dữ liệu: [Demo cọc lưu DB](../docs/setup/DEMO_DEPOSIT.md).
