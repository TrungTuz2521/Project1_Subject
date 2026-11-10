# Đăng nhập Google (Google Identity Services)

## Cấu hình local

Google Auth Platform → Clients → Web application → Authorized JavaScript origins:

```text
http://localhost
http://localhost:5173
```

Đây là popup GIS JavaScript callback; không cần Client Secret hoặc redirect URI.
Client ID là cấu hình công khai, phải giống nhau ở hai nơi:

```dotenv
# backend/.env
GOOGLE_CLIENT_ID=<client-id>.apps.googleusercontent.com
```

```dotenv
# frontend/.env.local
VITE_GOOGLE_CLIENT_ID=<client-id>.apps.googleusercontent.com
VITE_API_BASE_URL=http://127.0.0.1:5000/api/v1
VITE_USE_MOCKS=false
```

Không commit hai file env local. Các file `.env.example` chỉ chứa placeholder.
Cài backend dependencies bằng `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` từ `backend`.
Khởi động lại backend và Vite sau khi đổi env. Mở frontend tại **http://localhost:5173**.
Nếu localhost không truy cập được với cấu hình Vite bind 127.0.0.1, chạy `npm run dev -- --host localhost`.
Backend `CORS_ORIGINS` cần chứa chính xác `http://localhost:5173` (mặc định đã có).
Khi deploy, thêm origin HTTPS thật vào Google Console và CORS; cấu hình lại frontend API URL.
Nếu Google Console yêu cầu Test users khi đang Testing, thêm email thành viên cần thử.

## API và tài khoản

- `POST /api/v1/auth/google/challenge`, JSON `{}` → `{data:{nonce,challenge},meta}`.
- `POST /api/v1/auth/google`, JSON `{credential,challenge,password?}` → cùng LoginData với `/auth/login`.
- Hai endpoint cần header Origin thuộc CORS_ORIGINS; challenge/token không được ghi log.
- Backend xác minh chữ ký Google, issuer, audience, expiry, verified email và nonce.
  Challenge ký bằng server secret, hết hạn sau 10 phút; frontend làm mới trước hạn.
- Định danh bằng Google `sub` lưu ở `users.google_id`, không dùng email làm định danh Google.
- Email mới: tạo PLAYER/ACTIVE, skill AMATEUR; người chơi cập nhật hồ sơ sau đăng nhập.
- Google ID đã liên kết: đăng nhập tài khoản đó, giữ nguyên role và dữ liệu.
- Email đã có nhưng chưa liên kết: trả `ACCOUNT_LINK_REQUIRED`. Người dùng nhập **mật khẩu web hiện tại**
  ở ô Mật khẩu rồi bấm Google lại. Chỉ mật khẩu đúng mới liên kết; không tự nối qua email.
- Email đã gắn Google ID khác: từ chối. Tài khoản bị khóa: từ chối.
- JWT của ứng dụng có hạn 60 phút, giữ trong bộ nhớ; không refresh token, reload cần đăng nhập lại.
- Google verification qua mạng diễn ra trước transaction DB; timeout 10 giây, rate limit chung auth.
- Không chạy migration: schema hiện có đã có `google_id` và nullable `password_hash`.
- Trong mock mode ẩn Google button; chỉ kiểm thử Google bằng backend thật.

## Kiểm thử thủ công

1. Mở localhost:5173 → Đăng nhập → nút Google → chọn Gmail chưa có trên web.
2. Kiểm tra vào Tổng quan, quyền PLAYER; mở Hồ sơ, cập nhật trình độ.
3. Đăng xuất, đăng nhập Google lại: vẫn cùng user, đội/bài đăng giữ nguyên.
4. Thử email đã đăng ký bằng mật khẩu: phải yêu cầu mật khẩu web để liên kết lần đầu.
5. Sau liên kết, cả mật khẩu web và Google vẫn đăng nhập được.
6. User đã bị khóa phải không đăng nhập được; không tạo admin mới qua Google.

Các unit test dùng isolated SQLite và mock Google verifier, không chứng minh OAuth Console đã cấu hình đúng.
Cần hoàn tất bước chọn tài khoản Google thật trong trình duyệt để kiểm chứng end-to-end.

Tài liệu chính thức:
- https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid
- https://developers.google.com/identity/gsi/web/guides/verify-google-id-token
