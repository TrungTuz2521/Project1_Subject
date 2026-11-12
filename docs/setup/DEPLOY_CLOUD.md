# Đưa backend lên cloud cùng thanh toán SePay

Code thanh toán SePay không phụ thuộc chạy local hay cloud. Khi deploy chỉ cần đổi cấu hình, đổi URL webhook trên SePay và chạy thêm một tiến trình nền.

## 1. Chạy migration trước

Trên database mà bản cloud dùng, chạy lần lượt các file chưa chạy trong `database/schema/`, gồm `006_match_requests.sql` và `007_refund_account.sql`. Cả hai chỉ thêm cột. Kiểm tra bằng:

```
python -m flask --app app:create_app check-db
```

## 2. Hai tiến trình

| Tiến trình | Lệnh | Ghi chú |
|---|---|---|
| web | `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60` | Nhận request và webhook SePay. |
| worker | `python -m flask --app app:create_app scheduler --with-matchmaking --with-email` | Chạy **đúng một** bản: hết hạn giữ sân, hủy mã QR quá hạn, hoàn tiền, ghép kèo, gửi email. |

`backend/Procfile` đã khai sẵn hai tiến trình này cho các nền tảng đọc Procfile (Render, Railway, Heroku...). Nếu thiếu worker, khách vẫn trả tiền được nhưng sân giữ quá hạn không được mở lại đúng lúc, tiền đến muộn không vào hàng hoàn và email không được gửi.

## 3. Biến môi trường trên cloud

Khai trong phần Environment của nền tảng, **không** commit file `.env`:

| Biến | Giá trị |
|---|---|
| `TIDB_*` hoặc `DATABASE_URL` | Database production |
| `JWT_SECRET_KEY` | Chuỗi ngẫu nhiên mới, ít nhất 32 ký tự (không dùng lại bản local) |
| `CORS_ORIGINS`, `PUBLIC_WEB_URL` | `https://<tên miền frontend>` |
| `TRUSTED_PROXY_HOPS` | `1` nếu nền tảng có một load balancer phía trước (hầu hết các nền tảng), `2` nếu thêm Cloudflare proxy |
| `BANK_BIN`, `BANK_ACCOUNT_NO`, `BANK_ACCOUNT_NAME`, `BANK_NAME` | Tài khoản nhận tiền, giống bản local (MB: BIN `970422`) |
| `SEPAY_WEBHOOK_KEY` | Nên tạo key mới cho production |
| `SEPAY_QR_TTL_SECONDS`, `SEPAY_CONFIRM_GRACE_SECONDS` | `60`, `120` |
| `DEMO_PAYMENT_ENABLED` | `false` |
| `EMAIL_ENABLED`, `SMTP_*` | Như bản local nếu muốn gửi email |

Frontend: `VITE_API_BASE_URL=https://<tên miền backend>/api/v1`, `VITE_USE_MOCKS=false`, `VITE_DEMO_DEPOSIT=false`.

## 4. Cấu hình webhook trên SePay

my.sepay.vn → Tích hợp WebHooks → sửa webhook đang dùng (hoặc tạo mới):

- Sự kiện: **Có tiền vào**, tài khoản MB nhận tiền.
- URL: `https://<tên miền backend>/api/v1/payments/sepay/webhook`. Không cần cloudflared nữa.
- Kiểu chứng thực: **API Key**, giá trị đúng bằng `SEPAY_WEBHOOK_KEY` trên cloud.
- Tắt hoặc xóa webhook trỏ về địa chỉ `trycloudflare.com` cũ, để một khoản tiền không bị gửi tới hai nơi.

Kiểm tra nhanh: gọi webhook với key sai phải trả `401`:

```
curl -X POST -H "Authorization: Apikey sai" -H "Content-Type: application/json" -d "{}" https://<tên miền backend>/api/v1/payments/sepay/webhook
```

Sau đó tạo một lượt đặt sân thật, quét QR, chuyển tiền và xem lượt đó chuyển sang "Đã xác nhận".

## 5. Hệ thống xử lý số tiền khách chuyển thế nào

| Trường hợp | Kết quả |
|---|---|
| Chuyển đúng số | Ghi nhận cọc, sân được xác nhận, khách nhận email. |
| Chuyển thiếu | Ghi nhận số đã nhận là cọc một phần. Khách được báo số còn thiếu và quét mã mới cho phần đó. Hết giờ giữ sân mà vẫn chưa đủ thì số đã chuyển vào hàng hoàn tiền. |
| Chuyển dư, hoặc chuyển 2 lần cùng một mã | Phần dư được trừ vào tiền sân còn lại. Phần vượt giá sân vào hàng hoàn tiền. |
| Tiền đến khi lượt sân đã hết hạn hoặc đã hủy | Toàn bộ khoản đó vào hàng hoàn tiền. |
| SePay gửi lại cùng một thông báo | Bỏ qua, không ghi nhận hai lần. |

Tiền chuyển khoản không tự hoàn được: admin xem mục **Khoản cần hoàn** ở trang **Lịch sân** của admin. Mỗi dòng ghi tài khoản nhận hoàn khách đã khai trong Hồ sơ. Admin chuyển trả rồi bấm "Đã trả tiền". Khách chưa khai tài khoản thì gọi điện hoặc trả tiền mặt khi họ đến quầy.

## 6. Bảo mật đã bật sẵn

- Xác nhận cọc demo bị từ chối khi SePay đang bật, và với mọi request đi qua proxy hoặc tunnel.
- Webhook so key bằng phép so sánh an toàn thời gian, chỉ nhận tiền vào đúng số tài khoản đã khai và chỉ nhận mã do hệ thống tạo.
- `TRUSTED_PROXY_HOPS` để giới hạn số lần đăng nhập theo IP thật của khách. Đừng đặt số lớn hơn số proxy thật, nếu không khách có thể giả IP.
