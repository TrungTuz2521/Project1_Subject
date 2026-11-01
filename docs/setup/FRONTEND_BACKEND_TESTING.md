# Hướng dẫn test frontend với backend thật

Dành cho các thành viên trên nhánh `integration/duc-dminh`. Cập nhật ngày 31/10/2026. Mỗi máy phải tự tạo cấu hình local; pull code không tự tạo các tệp chứa cấu hình riêng.

## 1. Phân biệt các tệp cấu hình

| Tệp | Vai trò | Đưa lên GitHub? |
| --- | --- | --- |
| frontend/.env.example | Mẫu công khai để biết tên biến; Vite không tự nạp tệp này | Có, chỉ chứa cấu hình công khai |
| frontend/.env.local | Cấu hình Vite thật trên máy thành viên | Không; đang được .gitignore bỏ qua |
| backend/.env.example | Mẫu tên biến backend, không chứa credential thật | Có |
| backend/.env | Kết nối TiDB và secret của môi trường riêng | Không |

`.env.local` không được push nhưng cách tạo và dùng nó phải được ghi trong repo. Không dùng `git add -f` để đẩy cấu hình local. Mọi biến VITE_* có thể xuất hiện trong trình duyệt, tuyệt đối không đặt mật khẩu TiDB/JWT secret trong đó. Không lấy `.env.example` ở thư mục gốc làm cấu hình frontend.

## 2. Lấy nhánh tích hợp

Ví dụ remote `team` trỏ tới `TrungTuz2521/Project1_Subject`. Máy khác có thể gọi remote này là `origin`; kiểm tra bằng `git remote -v` và dùng đúng tên.

```powershell
git status
git fetch team
git switch integration/duc-dminh
git pull --ff-only team integration/duc-dminh
```

Nếu chưa có nhánh local, thay lệnh switch bằng `git switch --track team/integration/duc-dminh`. Không bỏ thay đổi đang làm hoặc commit `.env` chỉ để chuyển nhánh.

## 3. Cấu hình backend trên từng máy

Từ thư mục gốc, trong Terminal thứ nhất:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Mở backend/.env và điền các TIDB_* được người quản lý cấp qua kênh riêng. JWT_SECRET_KEY cần ít nhất 32 byte; mỗi môi trường dùng secret của mình. Có thể tạo secret local bằng lệnh dưới, rồi tự dán kết quả vào backend/.env, không gửi vào chat/commit:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Giữ xác minh TLS/hostname, cấu hình TIDB_CA_PATH nếu môi trường cần CA riêng. CORS_ORIGINS phải có đúng origin frontend, ví dụ `http://localhost:5173,http://127.0.0.1:5173`. Nếu Vite dùng cổng 5174 thì thêm origin có cổng 5174 và chạy lại backend. `localhost` và `127.0.0.1` là hai origin khác nhau.

```powershell
.\.venv\Scripts\python.exe run.py
```

Giữ Terminal mở. Truy cập http://127.0.0.1:5000/api/v1/health: mong đợi HTTP 200 và data.status=ok. Health thành công chỉ chứng minh Flask đang chạy, không tự chứng minh đăng nhập hoặc mọi truy vấn database đều thành công.

Không chạy lại schema gốc/V2/V3 trên TiDB dùng chung. Đăng ký, sửa hồ sơ, tạo đội và đặt sân đều có thể ghi dữ liệu thật khi tắt mock. Dùng database thử nghiệm riêng cho các thao tác đó, được cấu hình bằng các TIDB_* tương ứng. Không thay TIDB_DATABASE tùy ý rồi chạy migration để tự dựng schema thiếu căn cứ.

## 4. Tạo cấu hình frontend thật

Mở Terminal thứ hai tại thư mục gốc:

```powershell
cd frontend
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
```

Mở **frontend/.env.local**, đặt đúng hai dòng sau và lưu Ctrl+S:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:5000/api/v1
VITE_USE_MOCKS=false
```

Tệp nằm cùng cấp package.json, không ở src và không mang tên `.env.local.txt`. Nếu đã có `.env.local`, phải sửa tệp đó, vì lệnh Copy có điều kiện không ghi đè cấu hình hiện có. Các tệp `.env.development.local` hoặc biến môi trường đã đặt ở Terminal có thể ghi đè giá trị; cần kiểm tra nếu vẫn thấy demo.

```powershell
npm ci
npm run dev
```

Nếu frontend đang chạy, Ctrl+C rồi `npm run dev` lại sau khi sửa env. Mở đúng URL terminal hiện ra, thường là http://127.0.0.1:5173 hoặc http://localhost:5173. Máy thành viên phải chạy Flask của chính máy đó; 127.0.0.1 không trỏ tới máy Đức từ máy người khác.

## 5. Xác nhận đã tắt mock

1. Tải lại trang, có thể dùng Ctrl+Shift+R.
2. Không còn dòng “Chế độ demo · Chưa cần kết nối backend” và nút đăng nhập nhanh bằng mock.
3. F12 → Network → Fetch/XHR, gửi form đăng nhập.
4. Phải thấy POST http://127.0.0.1:5000/api/v1/auth/login. Không thấy request API trong chế độ mock là bình thường, nhưng không phải đang test backend thật.
5. Login hợp lệ trả 200, data có access_token, expires_in=3600 và user. Không chụp/chia sẻ token ở ảnh kết quả.

Tài khoản mock `demo@example.test` / `mock-only` không dùng để đăng nhập TiDB. Tài khoản test database và mật khẩu được cấp riêng. Không đưa tài khoản quản trị/mật khẩu vào tài liệu công khai.

## 6. Checklist test tích hợp Auth

| Thao tác | Kết quả |
| --- | --- |
| Sai mật khẩu | 401 INVALID_CREDENTIALS và thông báo lỗi, không vào ứng dụng |
| Đăng nhập đúng | 200, có phiên thật; hiển thị đúng người dùng |
| GET /users/me | 200, request có Authorization: Bearer token; không trả password_hash |
| PATCH /users/me trên database test | 200, đọc lại bằng GET thấy dữ liệu cập nhật |
| POST /auth/register trên database test | 201; sau đó đăng nhập được, role luôn PLAYER |
| Đăng xuất | Xóa phiên frontend, quay về đăng nhập; không có refresh token |
| Reload | Phiên trong bộ nhớ mất, đăng nhập lại; đây là hành vi đã chọn |
| Token hết hạn | API bảo vệ trả 401 TOKEN_EXPIRED; không tự gia hạn hold sân |

Không cần sửa thời gian máy hoặc token thật để kiểm tra hết hạn. Backend có test tự động cho các tình huống Auth, chạy cô lập SQLite trong bộ nhớ:

```powershell
# Terminal tại backend
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Test tự động không thay thế việc thử frontend thật. Booking/thanh toán/QR chưa có nghĩa đã nối đủ chỉ vì Auth hoạt động.

## 7. Lỗi thường gặp

| Dấu hiệu | Kiểm tra |
| --- | --- |
| Vẫn hiện demo | Có đúng frontend/.env.local chưa, đã Ctrl+S/restart chưa; có chạy nhầm thư mục/cổng hoặc env ưu tiên cao hơn không |
| Sai mật khẩu nhưng backend trực tiếp đăng nhập được | Frontend có còn mock không; Network có gọi đúng cổng 5000 không |
| ERR_CONNECTION_REFUSED | Backend chưa chạy, sai cổng hoặc backend đã thoát; xem Terminal backend |
| CORS error | CORS_ORIGINS có đúng scheme/host/port trang đang mở; restart backend sau khi đổi |
| 503 DATABASE_UNAVAILABLE | Kiểm tra kết nối TLS, IP allowlist, credential, database và mạng; không tắt xác minh TLS để chữa lỗi |
| 401 với tài khoản mẫu | Dùng đúng tài khoản database và chữ hoa/thường; backend yêu cầu bcrypt hợp lệ, không phải plaintext seed |
| JWT_SECRET_KEY quá ngắn | Điền secret tối thiểu 32 byte vào backend/.env rồi chạy lại backend |
| 404 hoặc response HTML | Base URL có /api/v1 đúng một lần, không gọi API sang cổng frontend khi chưa có proxy |
| Vite chuyển sang 5174 | Mở đúng URL mới và thêm origin tương ứng cho backend |

Khi báo lỗi, gửi nhánh/commit, URL trang, HTTP status và error.code, nội dung Terminal đã che secret. Không gửi `.env`, Authorization header, JWT hoặc ảnh chứa mật khẩu.

## 8. Chạy lại vào những lần sau

Giữ các file local trên máy. Khi pull có đổi package-lock, chạy npm ci; khi requirements đổi thì cài lại thư viện backend. Khởi động backend và frontend ở hai Terminal như trên. Chuyển nhánh không có nghĩa cấu hình local tự đổi theo: kiểm tra lại mock/API URL nếu chuyển giữa nhánh demo và nhánh tích hợp.
