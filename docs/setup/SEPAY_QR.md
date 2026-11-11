# Thanh toán cọc bằng QR ngân hàng (SePay)

Người chơi bấm **Đóng cọc bằng mã QR → Tạo mã QR thanh toán**. Backend tạo một mã VietQR riêng cho phần cọc của người đó:

- **Số tiền** = phần cọc còn phải trả, **nội dung** = mã `SPxxxxxxxxxx`, cả hai được điền sẵn khi quét bằng app ngân hàng.
- Mã **hiện 60 giây** (`SEPAY_QR_TTL_SECONDS`), hết giờ thì QR tự ẩn và có nút **Tạo mã QR mới**.
- Trong thời gian mã còn hiện, sân luôn ở `PENDING_HOLD`. Nếu thời hạn giữ sân còn lại ngắn hơn 60 giây + `SEPAY_CONFIRM_GRACE_SECONDS`, hold được kéo dài đủ khoảng đó, **tối đa một lần** (không vượt hạn ban đầu + 180 giây), nên tạo mã liên tục không giữ sân mãi được.
- Khi tiền vào tài khoản, SePay gọi `POST /api/v1/payments/sepay/webhook`. Backend kiểm tra API key, số tài khoản nhận, chiều tiền vào, mã và **số tiền khớp chính xác**, rồi đánh dấu payment `SUCCESS`. Đủ cọc thì booking `CONFIRMED`, đồng thời tạo thông báo `PAYMENT_SUCCESS` và `BOOKING_CONFIRMED` (kèm email).
- Trình duyệt chỉ hỏi trạng thái 3 giây/lần, **không bao giờ tự báo đã thanh toán**.

## Cấu hình

1. Đăng ký <https://sepay.vn>, liên kết tài khoản ngân hàng nhận tiền (xem danh sách ngân hàng SePay hỗ trợ).
2. `backend/.env`:
   ```
   BANK_BIN=970422            # mã BIN 6 số của ngân hàng (vd. 970422 = MB)
   BANK_ACCOUNT_NO=...        # đúng số tài khoản đã liên kết với SePay
   BANK_ACCOUNT_NAME=NGUYEN VAN A
   BANK_NAME=MB Bank
   SEPAY_WEBHOOK_KEY=<chuỗi ngẫu nhiên dài>
   EMAIL_ENABLED=true         # cùng các biến SMTP_*, xem EMAIL_NOTIFICATIONS.md
   ```
3. Webhook cần URL **HTTPS công khai**. Khi chạy local: `cloudflared tunnel --url http://localhost:5000` (hoặc `ngrok http 5000`).
4. Trong SePay → **Tích hợp WebHooks → Thêm**:
   - Sự kiện: **Có tiền vào**
   - URL: `https://<tunnel>/api/v1/payments/sepay/webhook`
   - Kiểu chứng thực: **API Key**, giá trị = `SEPAY_WEBHOOK_KEY`
   - Bỏ qua nếu không có code thanh toán: **Không** (backend tự tìm mã trong nội dung)
5. Chạy song song với backend **một** tiến trình: `flask scheduler --with-matchmaking --with-email`. Lệnh này gửi email, và cho các mã QR quá 60 + 120 giây chưa có tiền về sang `FAILED` để không chặn Admin ghi nhận thủ công.

Thiếu `SEPAY_WEBHOOK_KEY` hoặc thông tin ngân hàng: tạo QR trả 503 và giao diện quay về QR tĩnh + Admin xác nhận như trước.

## Lưu trữ

Không cần migration: giao dịch lưu `payment_method='BANK_TRANSFER'`, `transaction_code='SP…'` (12 ký tự). Hoàn tiền vẫn do Admin chuyển trả thủ công giống chuyển khoản thường.

## Trường hợp cần Admin đối soát (ghi vào `payments.note`)

| Tình huống | Kết quả |
| --- | --- |
| Chuyển sai số tiền | Payment giữ `PENDING`, note `Callback sai so tien` |
| Chuyển 2 lần cho cùng mã | Lần 2 note `Nhan them sepay:<id> ... can hoan` |
| Trả mã cũ đã hết hạn và cả mã mới | Note `Thu vuot coc ... can hoan` |
| Tiền về sau khi hết giữ sân | Booking `EXPIRED`, tạo yêu cầu hoàn `REFUND_PROCESSING` |
| Thiếu mã trong nội dung | Bỏ qua, Admin đối chiếu sao kê |

## Thử webhook bằng tay

```bash
curl -X POST http://localhost:5000/api/v1/payments/sepay/webhook \
  -H "Authorization: Apikey $SEPAY_WEBHOOK_KEY" -H "Content-Type: application/json" \
  -d '{"id":1,"gateway":"MBBank","transactionDate":"2026-11-11 10:00:00","accountNumber":"<BANK_ACCOUNT_NO>",
       "content":"<MA_SP_TREN_MAN_HINH> chuyen tien","transferType":"in","transferAmount":<SO_TIEN>}'
```

Kiểm thử tự động: `python -m unittest discover -s tests -p test_sepay_qr.py -v` (SQLite trong bộ nhớ).
