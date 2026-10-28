# Backend Flask — phần Đức

## Chạy local

Từ thư mục `backend`, tạo virtualenv, cài `python -m pip install -r requirements.txt`.
Sao chép `.env.example` sang `.env`, cấu hình TiDB và `JWT_SECRET_KEY` ngẫu nhiên ít nhất 32 byte.
Không commit `.env`. Không chạy lại migration V3 trên database chung.

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

## Worker

```powershell
python -m flask --app app:create_app scan-matchmaking
python -m flask --app app:create_app expire-proposals
```

Đây là lệnh chạy một lượt; scheduler gọi mỗi 15 giây. Không tự chạy thread worker trong web server.
Quét mỗi cặp trong transaction riêng, lọc điều kiện cứng rồi chấm 40/20/40, ngưỡng 80.
Thông báo IN_APP ghi cùng transaction. Email chưa tích hợp, không đánh dấu đã gửi email.

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

Khi chưa gắn booking_service, xác nhận cuối OPPONENT trả 503, rollback phản hồi cuối để thử lại khi tích hợp.
Không tạo hold giả. Route hủy trận cũng trả 503 khi chưa có orchestration tiền của Tú.
Booking/Payment/balance/QR chung/xác nhận thu đủ/gateway cọc thuộc Tú; các migration sau V3, outbox/audit/email cần triển khai chung
trước khi đưa thanh toán thật vào sử dụng. Không giả định các bảng sau V3 đã tồn tại.

## Luồng thu tiền mới — 29/10/2026

Đức đã bỏ booking_settlements khỏi LOCK_ORDER và bổ sung BookingBalance, ManualReceipt, BookingBalancePort.
Tú triển khai get_booking_balance và confirm_booking_paid theo protocol; Huy dùng GET balance/POST confirm-paid
trong hợp đồng API 1.8. Một QR ngân hàng cho tổng thiếu; hai đội tự chia, Admin kiểm tra tiền vào rồi xác nhận.
Không có winner/outcome/phân bổ từng đội hoặc payment session quyết toán. Cọc 20%/hai payer trước trận giữ nguyên.
Không tạo bảng/cột mới cho thu gộp; recorded_by_admin_id, paid_at, note, transaction_code trong payments V3 đủ dùng.
Thu gộp dùng booking.user_id làm tài khoản quy chiếu, không đại diện cho người thực chuyển; không áp dụng cho cọc.
Protocol/DTO chỉ mô tả điểm nối; code Đức không giả thành công các endpoint tài chính của Tú.
