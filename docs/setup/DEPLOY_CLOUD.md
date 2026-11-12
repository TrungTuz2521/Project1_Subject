# Đưa backend lên cloud cùng thanh toán SePay

Bản demo miễn phí: backend trên **Render** (gói free, vùng Singapore), frontend trên **Vercel**, database TiDB đã có (Tokyo). Code thanh toán SePay không đổi; chỉ đổi cấu hình và URL webhook.

Các file deploy: `render.yaml` ở gốc repo (cấu hình Render), `backend/Dockerfile` (Python 3.14, giống bản local), `backend/.dockerignore` (không đưa `.env` và test vào image). `backend/fly.toml` và `backend/Procfile` để dành khi chuyển sang gói trả phí có worker riêng (mục 8).

## 1. Database

Production dùng database TiDB hiện có. Trước mỗi lần deploy có migration mới, chạy file SQL đó trên database rồi kiểm tra (chỉ đọc):

```
python -m flask --app app:create_app check-db
```

## 2. Web và việc nền

Backend có hai phần việc:

- **web**: nhận request và webhook SePay (`gunicorn wsgi:app`).
- **scheduler**: mỗi 15 giây hết hạn giữ sân, hủy mã QR quá hạn, hoàn tiền, ghép kèo, gửi email. Phải chạy **đúng một** bản.

Render free không có worker miễn phí, nên `render.yaml` bật `RUN_SCHEDULER_IN_WEB=true`: scheduler chạy trên một luồng nền trong chính tiến trình web, và gunicorn chỉ chạy 1 tiến trình (`WEB_CONCURRENCY=1`, 4 luồng). Đừng tăng `WEB_CONCURRENCY` khi đang bật biến này, nếu không mỗi tiến trình chạy một scheduler.

Thiếu scheduler thì khách vẫn trả tiền được, nhưng sân giữ quá hạn không được mở lại đúng lúc, tiền đến muộn không vào hàng hoàn và email không được gửi. Trang **Hôm nay** của admin báo đỏ khi việc nền bị trễ.

## 3. Deploy backend lên Render (miễn phí)

1. Đẩy code lên GitHub (repo có `render.yaml` ở gốc).
2. Đăng ký render.com bằng tài khoản GitHub (không cần thẻ). Chọn **New → Blueprint**, chọn repo. Render đọc `render.yaml` và tạo service `football-field-api`.
3. Render hỏi giá trị các biến `sync: false`. Điền giống `backend/.env`, trừ:
   - `CORS_ORIGINS`, `PUBLIC_WEB_URL`: tên miền Vercel (mục 4), ví dụ `https://ten-app.vercel.app`. Chưa có thì điền tạm `http://localhost:5173`, sửa sau.
   - `SEPAY_WEBHOOK_KEY`: nên tạo key mới, không dùng lại key đã lộ ở máy cá nhân.
   - Biến không dùng (Google, SMTP) để trống.
   - `JWT_SECRET_KEY` Render tự sinh. Muốn gửi email thì đổi `EMAIL_ENABLED` thành `true` và điền SMTP.
4. Bấm **Apply**. Lần build đầu mất vài phút. Xem tiến trình ở tab **Logs**; dòng `Scheduler running every 15s` nghĩa là việc nền đã chạy.
5. Kiểm tra: mở `https://<tên service>.onrender.com/api/v1/health` phải thấy `{"data":{"status":"ok"}...}`.

Mỗi lần push lên nhánh chính, Render tự build và deploy lại. Sửa biến môi trường ở tab **Environment** của service.

### Giữ server không ngủ

Gói free tắt server sau 15 phút không có request; request đầu tiên sau đó chờ khoảng 1 phút, và lúc ngủ scheduler cũng dừng. Để demo ổn định, tạo một monitor miễn phí trên uptimerobot.com (hoặc cron-job.org):

- Loại HTTP(s), URL `https://<tên service>.onrender.com/api/v1/health`, chu kỳ 5 phút.

Gói free có 750 giờ chạy mỗi tháng, đủ cho đúng một service chạy cả tháng. Đừng tạo thêm service free thứ hai trong cùng tài khoản nếu cần chạy liên tục.

Database ở Tokyo, server ở Singapore: mỗi truy vấn thêm khoảng 70 ms, chấp nhận được cho demo.

## 4. Deploy frontend lên Vercel

Đăng ký vercel.com bằng GitHub (gói Hobby miễn phí), **Add New → Project**, import repo, **Root Directory** `frontend`, framework Vite (build `npm run build`, output `dist`). Biến môi trường (biến `VITE_*` được gắn vào lúc build, đổi giá trị thì phải **Redeploy**):

| Biến | Giá trị |
|---|---|
| `VITE_API_BASE_URL` | `https://<tên service>.onrender.com/api/v1` |
| `VITE_GOOGLE_CLIENT_ID` | Như backend, nếu dùng Google |
| `VITE_DEMO_DEPOSIT` | `false` |

App dùng đường dẫn dạng `#/...` nên không cần cấu hình rewrite. Sau khi có tên miền frontend, cập nhật `CORS_ORIGINS` và `PUBLIC_WEB_URL` của backend (Render → Environment, lưu xong Render tự khởi động lại), và thêm tên miền đó vào Authorized JavaScript origins của Google nếu dùng đăng nhập Google.

## 5. Cấu hình webhook trên SePay

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

## 6. Hệ thống xử lý số tiền khách chuyển thế nào

| Trường hợp | Kết quả |
|---|---|
| Chuyển đúng số | Ghi nhận cọc, sân được xác nhận, khách nhận email. |
| Chuyển thiếu | Ghi nhận số đã nhận là cọc một phần. Khách được báo số còn thiếu và quét mã mới cho phần đó. Hết giờ giữ sân mà vẫn chưa đủ thì số đã chuyển vào hàng hoàn tiền. |
| Chuyển dư, hoặc chuyển 2 lần cùng một mã | Phần dư được trừ vào tiền sân còn lại. Phần vượt giá sân vào hàng hoàn tiền. |
| Tiền đến khi lượt sân đã hết hạn hoặc đã hủy | Toàn bộ khoản đó vào hàng hoàn tiền. |
| SePay gửi lại cùng một thông báo | Bỏ qua, không ghi nhận hai lần. |

Tiền chuyển khoản không tự hoàn được: admin xem mục **Khoản cần hoàn** ở trang **Lịch sân** của admin. Mỗi dòng ghi tài khoản nhận hoàn khách đã khai trong Hồ sơ. Admin chuyển trả rồi bấm "Đã trả tiền". Khách chưa khai tài khoản thì gọi điện hoặc trả tiền mặt khi họ đến quầy.

## 7. Bảo mật đã bật sẵn

- Xác nhận cọc demo bị từ chối khi SePay đang bật, và với mọi request đi qua proxy hoặc tunnel.
- Webhook so key bằng phép so sánh an toàn thời gian, chỉ nhận tiền vào đúng số tài khoản đã khai và chỉ nhận mã do hệ thống tạo.
- `TRUSTED_PROXY_HOPS` để giới hạn số lần đăng nhập theo IP thật của khách. Đừng đặt số lớn hơn số proxy thật, nếu không khách có thể giả IP.

## 8. Phương án trả phí: Fly.io

Khi cần máy chạy liên tục ở Tokyo, cạnh database, và worker riêng. Cài `flyctl` (https://fly.io/docs/flyctl/install/), đăng nhập `fly auth login` (cần thẻ thanh toán; 2 máy nhỏ khoảng 4–6 USD/tháng). Trong thư mục `backend`:

```powershell
fly launch --no-deploy --copy-config      # chọn tên app; giữ vùng nrt (Tokyo)
```

Khai bí mật (không commit, không đưa vào `fly.toml`). Mỗi biến một cặp `TÊN=giá trị`:

```powershell
fly secrets set TIDB_HOST=... TIDB_PORT=4000 TIDB_DATABASE=... TIDB_USERNAME=... TIDB_PASSWORD=...
fly secrets set JWT_SECRET_KEY=<chuỗi ngẫu nhiên mới, ít nhất 32 ký tự>
fly secrets set CORS_ORIGINS=https://<tên miền frontend> PUBLIC_WEB_URL=https://<tên miền frontend>
fly secrets set BANK_BIN=970422 BANK_ACCOUNT_NO=... BANK_ACCOUNT_NAME=... BANK_NAME=MB
fly secrets set SEPAY_WEBHOOK_KEY=<key mới> SEPAY_QR_TTL_SECONDS=60 SEPAY_CONFIRM_GRACE_SECONDS=120
fly secrets set GOOGLE_CLIENT_ID=...                                            # nếu dùng đăng nhập Google
fly secrets set EMAIL_ENABLED=true SMTP_USERNAME=... SMTP_PASSWORD=...           # nếu gửi email
```

`fly.toml` đã đặt sẵn `TRUSTED_PROXY_HOPS=1` (proxy của Fly) và `DEMO_PAYMENT_ENABLED=false`. Tạo chuỗi ngẫu nhiên: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

Deploy và đặt số máy (web 1, worker đúng 1):

```powershell
fly deploy
fly scale count web=1 worker=1
fly status                     # hai máy: web và worker đều started
fly logs                       # xem log khi có lỗi
```

Kiểm tra: mở `https://<tên app>.fly.dev/api/v1/health` phải thấy `{"data":{"status":"ok"}...}`.

Lần sau cập nhật code chỉ cần `fly deploy` trong thư mục `backend`.
