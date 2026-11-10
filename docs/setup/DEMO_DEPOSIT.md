# Demo cọc bằng QR, xác nhận lưu vào database

Cập nhật 10/11/2026. Đây là **mô phỏng thanh toán**, không tích hợp đối soát MoMo/VNPay/ngân hàng.
Người dùng đã chọn lưu giao dịch demo trực tiếp vào database cấu hình hiện tại (TiDB nhóm), thay vì tạo database demo riêng.
Không cần migration. Không có màn Admin xác nhận cọc mới; nguyên mẫu đó đã được hoàn tác.

## Cấu hình trên máy chạy app

Trong `backend/.env` riêng:

```dotenv
DEMO_PAYMENT_ENABLED=true
BANK_BIN=970418
BANK_NAME=BIDV
BANK_ACCOUNT_NO=<tai-khoan-nhan>
BANK_ACCOUNT_NAME=<ten-chu-tai-khoan>
```

Trong `frontend/.env.local` riêng:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:5000/api/v1
VITE_USE_MOCKS=false
VITE_DEMO_DEPOSIT=true
```

Thông tin ngân hàng nhận đã được lưu local trên máy chủ dự án; thành viên khác lấy cấu hình qua kênh riêng.
Không đưa secret hoặc toàn bộ `.env` lên Git. Khởi động lại backend/Vite và các worker sau khi cập nhật code/env.
Frontend chỉ hiện nút khi Vite DEV và bật flag; backend yêu cầu bật flag và endpoint chỉ cho request local.
Khi triển khai thanh toán thật, bắt buộc đặt `DEMO_PAYMENT_ENABLED=false`, `VITE_DEMO_DEPOSIT=false` và tích hợp xác minh giao dịch thực tế.
Không bật backend demo sau reverse proxy production; remote_addr của proxy có thể là loopback.

## Cách demo

1. Chạy backend, frontend; giữ email-worker/matchmaking-worker nếu demo cả ghép trận và email.
2. Tạo booking hoặc để hai đội chấp nhận ghép. Hạn giữ sân vẫn 5 phút từ server tạo hold.
3. Vào **Booking của tôi → chọn đơn → Đóng cọc bằng chuyển khoản**.
4. Web hiển thị tài khoản nhận, QR, số tiền của chính đại diện đang đăng nhập và nội dung `COC{booking_id}U{user_id}`.
5. **Không chuyển tiền thật trong demo.** Bấm **Xác nhận thanh toán cọc (demo)** dưới QR.
6. Backend tự lấy user từ JWT và tính phần cọc còn thiếu; client chỉ gửi booking_id, không tự gửi amount/status/user_id.
7. Đặt trực tiếp: đủ 20% thì booking CONFIRMED. Ghép hai đội: mỗi đại diện xác nhận 10%; sau người đầu booking vẫn chờ, sau người thứ hai mới CONFIRMED và Match CONFIRMED.
8. Bấm lại không nhân đôi Payment hoặc thông báo. Reload/đăng nhập lại vẫn đọc được kết quả từ DB. Booking có nhãn DEMO.

Nút không gia hạn hold. Hết hạn hoặc còn phiên online chưa rõ trạng thái thì không xác nhận demo.
Không trộn giao dịch thật và demo trong cùng booking. Booking DEMO vẫn chiếm slot và xuất hiện trong lịch/statistics vì trạng thái đã lưu thật;
sau buổi demo, dùng luồng hủy booking để nhả sân, không sửa/xóa SQL tùy ý.

## Dữ liệu và giới hạn

- `POST /api/v1/payments/deposit/demo-confirm` (Bearer PLAYER, local), JSON `{ "booking_id": 123 }`.
- Trả `{data:{demo:true,payment,booking},meta}`; Payment/Booking có `is_demo=true`.
- Payment ghi SUCCESS để chạy luồng booking, `transaction_code=DEMO-DEP-{booking_id}-{user_id}`, note bắt đầu DEMO_ONLY.
- Không ghi `recorded_by_admin_id`: đây là thao tác mô phỏng của người chơi, không giả là Admin đã kiểm tra tiền.
- Email/thông báo cọc/trận của luồng này có chữ DEMO. Chỉ gửi email nếu worker và email config đang bật.
- Báo cáo doanh thu API và bảng tổng tiền trong Excel bỏ giao dịch DEMO; lịch sử giao dịch/Excel vẫn có mã DEMO và ghi chú để truy vết.
- Không lập hoàn tiền thật hoặc nhận khoản thu thật/QR quyết toán cho booking có cọc DEMO.
- Các view doanh thu SQL legacy chưa sửa để lọc DEMO; không dùng view đó làm sổ tiền thật trong giai đoạn demo.
- `GET /api/v1/bookings/{id}/deposit-instructions` chỉ đọc; payer chỉ xem phần cọc của mình, Admin xem được các payer.
- Tắt flag không tự xóa dòng demo đã lưu. Chưa có chức năng dọn dữ liệu demo hàng loạt hoặc thu tiền phần còn lại bằng mô phỏng.

Đã kiểm thử SQLite riêng và build; chưa thực hiện chuyển tiền hoặc tự tạo giao dịch demo trong TiDB nhóm bằng công cụ.
Người dùng có thể kiểm chứng end-to-end bằng app sau khi khởi động lại backend.
