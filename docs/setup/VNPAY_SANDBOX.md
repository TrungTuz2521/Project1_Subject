# Cấu hình VNPay sandbox và mở booking từ thông báo

## 1. Chuẩn bị thông tin VNPay

Đăng ký môi trường thử nghiệm tại https://sandbox.vnpayment.vn/devreg/ và lấy mã website `vnp_TmnCode`, khóa ký `vnp_HashSecret` được cấp cho merchant sandbox. Ảnh QR MoMo/ngân hàng cá nhân không thay thế các thông tin này. Không dùng khóa demo công khai làm cấu hình thanh toán của nhóm.

Backend dự án đã có adapter VNPay; chưa xác minh giao dịch end-to-end trên tài khoản sandbox thật vì chưa có thông tin merchant. MoMo hiện chưa tích hợp. Tài liệu chính thức: [VNPay Payment](https://sandbox.vnpayment.vn/apis/docs/thanh-toan-pay/pay.html).

## 2. File backend/.env riêng trên máy

Giữ nguyên cấu hình database/JWT đang chạy. Bổ sung hoặc cập nhật các biến sau trong `backend/.env`, không phải `.env.example` và không phải frontend:

```dotenv
VNPAY_TMN_CODE=<ma_website_sandbox_duoc_cap>
VNPAY_HASH_SECRET=<khoa_ky_sandbox_duoc_cap>
VNPAY_RETURN_URL=http://127.0.0.1:5173/
VNPAY_PAY_URL=https://sandbox.vnpayment.vn/paymentv2/vpcpay.html
VNPAY_API_URL=https://sandbox.vnpayment.vn/merchant_webapi/api/transaction
```

Thay các phần trong dấu <> bằng giá trị merchant được cấp; không chép nguyên placeholder. Nếu Vite dùng cổng khác, sửa RETURN_URL theo cổng đó. Sau khi lưu `.env`, dừng backend bằng Ctrl+C và chạy lại `.\.venv\Scripts\python.exe run.py`. Không đưa `.env` hoặc HashSecret lên GitHub/frontend/ảnh chụp công khai.

## 3. URL nhận kết quả IPN

Return URL là trang trình duyệt trở về; IPN là callback server-to-server xác minh trạng thái thanh toán. Trong cấu hình merchant VNPay, khai báo IPN HTTPS công khai có đường dẫn:

```text
https://<domain-backend-cong-khai>/api/v1/payments/vnpay/ipn
```

Không dùng 127.0.0.1 làm IPN: từ máy VNPay, địa chỉ đó không trỏ tới máy của bạn. Có thể dùng backend đã deploy hoặc tunnel tới cổng 5000 khi thử nghiệm. Nếu dùng ngrok, sau khi cài và đăng nhập theo tài liệu nhà cung cấp, lệnh `ngrok http 5000` cung cấp URL HTTPS chuyển tiếp; dùng URL đó cộng đường dẫn IPN phía trên. Tunnel tạo đường truy cập từ Internet vào backend local, chỉ bật trong phiên thử nghiệm và tắt khi xong. Nếu URL tunnel đổi thì cập nhật cấu hình merchant. Thông tin chính thức: [ngrok HTTP endpoint](https://ngrok.com/docs/using-ngrok-with/flask).

URL IPN được đăng ký phía VNPay; code hiện không có biến `VNPAY_IPN_URL` cần tự thêm vào env. Adapter kiểm tra chữ ký, merchant, số tiền và trạng thái trước khi ghi nhận; Return URL hoặc ảnh báo thành công không thay thế IPN đã xác minh. Đối soát dùng `reconcile-payments` khi cần, không tự sửa Payment thành SUCCESS.

## 4. Thao tác trên app

1. Đăng nhập hai tài khoản ở hai cửa sổ/phiên riêng.
2. Tạo hai bài tìm đối thủ hợp lệ, chạy quét ghép trận nếu chưa có worker; cả hai đại diện đồng ý đề xuất.
3. Ngay khi bên thứ hai đồng ý và có sân, backend tạo booking PENDING_HOLD. **Hai đội dùng chung một hạn giữ sân 300 giây**, không phải mỗi đội 5 phút và không đợi cả hai cùng mở trang thanh toán.
4. Trong thông báo **Đã giữ sân**, bấm **Thanh toán tiền cọc**. App đọc booking liên kết qua API, mở `#/my-bookings?booking_id=<id>` và chọn đúng đơn trong phần chi tiết. Bấm thông báo không tạo phiên thanh toán, không gia hạn hold.
5. Xem thời gian còn lại, tổng tiền sân, tổng cọc và payer_progress. Bấm **Thanh toán cọc VNPay**, rồi **Mở cổng thanh toán an toàn**. Dùng phương tiện thử nghiệm do VNPay cung cấp, không dùng chuyển khoản cá nhân để giả kết quả sandbox.
6. Mỗi đại diện thanh toán phần cọc của mình. Ví dụ sân 600000: tổng cọc 120000, mỗi đội 60000. Sau IPN đầu tiên booking vẫn chờ cọc; đủ hai phần trong hạn mới CONFIRMED.
7. Trở lại tab Booking ban đầu và bấm **Làm mới** để đọc trạng thái từ backend. Hiện frontend giữ token trong bộ nhớ: tab mới trở về Return URL/reload có thể yêu cầu đăng nhập lại; đăng nhập lại đúng tài khoản rồi mở Booking của tôi. Không tự xác nhận SUCCESS chỉ từ query trên Return URL.

Hết 5 phút thì không tiếp tục thanh toán; tải lại trạng thái và xử lý lượt giữ sân mới theo luồng booking. Thông báo cũ vẫn có thể mở booking để xem trạng thái, không hồi sinh hoặc gia hạn đơn hết hạn. Worker cần được chạy/schedule để cập nhật EXPIRED và nhả các bài/trận liên quan:

```powershell
# Terminal tại backend, chạy một lượt khi demo
.\.venv\Scripts\python.exe -m flask --app app:create_app expire-booking-holds
```

Các lệnh quét/timeout hiện chạy một lượt; web server Flask không tự chạy scheduler nền. Khi triển khai, cấu hình scheduler ngoài theo hướng dẫn backend.

## 5. Lỗi thường gặp

| Hiện tượng | Kiểm tra |
| --- | --- |
| 503 PAYMENT_PROVIDER_UNAVAILABLE | TmnCode/HashSecret đã điền trong backend/.env và đã restart backend chưa |
| VNPay báo cấu hình/chữ ký không hợp lệ | Dùng đúng cặp khóa sandbox của cùng merchant, RETURN_URL đúng môi trường và URL thanh toán sandbox |
| VNPay báo xong nhưng booking vẫn chờ | IPN công khai đã được đăng ký, tunnel/backend còn chạy, kiểm tra log đã nhận IPN và bấm Làm mới |
| Vừa đổi tài khoản đã hết giờ | Hạn bắt đầu khi giữ sân, không theo lúc đăng nhập; mở hai phiên trước khi xác nhận |
| Booking hết hạn vẫn thấy thông báo giữ sân cũ | Thông báo là lịch sử; xem hold_expires_at/trạng thái booking, không tạo QR mới cho đơn đã hết hạn |
| Chỉ một đội đã trả | Chờ phần còn lại trong cùng hạn; không đánh dấu trận CONFIRMED sớm |

Chưa chạy giao dịch sandbox thật thì chưa kết luận tích hợp VNPay end-to-end đã đạt. Không có migration SQL mới cho phần điều hướng hoặc cấu hình này.
