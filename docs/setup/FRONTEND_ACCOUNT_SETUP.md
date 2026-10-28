# Frontend tài khoản và khung ứng dụng — Setup & kiểm thử

## Phạm vi đã triển khai

- Form đăng nhập và đăng ký với xác thực dữ liệu phía giao diện.
- Hồ sơ cá nhân: GET `/users/me`, PATCH `/users/me` theo API contract.
- Khung ứng dụng có sidebar, thanh tài khoản, dashboard và điều hướng giữa tổng quan, đội bóng, đặt sân, ghép đội/tìm trận, thông báo, hồ sơ.
- Token chỉ được giữ trong bộ nhớ thông qua `src/stores/session.ts`, thời hạn tối đa 3600 giây; không dùng localStorage, sessionStorage hoặc refresh token.
- API 401 trên endpoint bảo vệ xóa đúng session hiện tại; giao diện quay về đăng nhập và thông báo phiên không còn hợp lệ.
- Mock đăng ký/đăng nhập/hồ sơ để thử giao diện mà không cần chạy Flask/TiDB.

## Khởi chạy trên Windows / PowerShell

Mở terminal trong thư mục `Project1_Subject-dminh\frontend`:

```powershell
npm ci
npm run dev
```

Mở URL Vite in trong terminal, thường `http://localhost:5173`.

Kiểm tra chất lượng mã nguồn:

```powershell
npm test
npm run build
```

## Tài khoản demo

- Email: `demo@example.test`
- Mật khẩu mock: `mock-only`

Đây là credential giả lập trong trình duyệt, không phải tài khoản backend. Tài khoản đăng ký mới cũng chỉ được giữ trong bộ nhớ mock và mất khi tải lại trang.

## Kiểm thử thủ công

1. Đăng nhập bằng tài khoản demo.
2. Mở Hồ sơ cá nhân, sửa họ tên hoặc trình độ, lưu, rồi xác nhận thông báo thành công.
3. Đăng xuất và đăng ký email mới với mật khẩu từ 8 đến 72 byte UTF-8; sau đó đăng nhập bằng email đã đăng ký.
4. Thử đăng ký lại email vừa dùng để xem lỗi trùng email.
5. Mở Đội bóng của tôi; trong thanh tình huống chọn **Thử lỗi token 401**. Yêu cầu dữ liệu đội tiếp theo phải khiến app trở về màn hình đăng nhập.
6. Điều hướng đến Đặt sân, Ghép đội & tìm trận, Thông báo. Các trang này hiện là placeholder; chúng không giả vờ rằng luồng nghiệp vụ đã hoàn thành.

## Nối vào Flask API thật

Tạo `frontend/.env.local` từ `.env.example` và sửa:

```dotenv
VITE_API_BASE_URL=http://localhost:5000/api/v1
VITE_USE_MOCKS=false
```

Khởi động lại Vite sau khi thay đổi biến môi trường. Backend phải triển khai đúng hợp đồng:

- `POST /auth/register`: `full_name`, `email`, `password`, `phone?`, `skill_level?` → `UserSelf` (201)
- `POST /auth/login`: `email`, `password` → `access_token`, `expires_in`, `user`
- `GET /users/me` → `UserSelf`
- `PATCH /users/me`: `full_name?`, `phone?`, `skill_level?` → `UserSelf`

Response chuẩn có envelope `{ data, meta }`; lỗi dùng `{ error: { code, message, fields? } }`. Backend phải áp dụng quyền và trạng thái tài khoản, lưu mật khẩu bằng hash và phát token hết hạn theo hợp đồng. Frontend không kết nối database trực tiếp và không đưa secret vào `VITE_*`.

## Tệp chính

- `frontend/src/App.tsx`: giao diện login/register, dashboard, profile, khung điều hướng và trang module giữ chỗ.
- `frontend/src/services/auth.ts`: service gọi endpoint auth/profile.
- `frontend/src/services/api.ts`: Bearer header, timeout, lỗi API, xử lý 401.
- `frontend/src/stores/session.ts`: session in-memory và timeout 60 phút.
- `frontend/src/mocks/server.ts`: handler mock phục vụ phát triển UI.
- `frontend/src/features/matchmaking/TeamsPage.tsx`: màn hình đội bóng mẫu và liên kết điều hướng.

## Giới hạn cần biết

- Backend hiện trong repository vẫn là khung khởi tạo; cần kiểm thử tích hợp khi Flask endpoints sẵn sàng.
- Không có refresh token. Reload trang xóa phiên do token không được lưu bền vững.
- Trang đặt sân/ghép đội/thông báo mới là placeholder trong phần việc tài khoản; không bao gồm các nghiệp vụ đặt sân, AI, thanh toán hoặc gửi email.
- Tính năng “thử lỗi 401” hoạt động trong mock dev; để kiểm thử token thật, backend cần phát trả 401 theo đúng hợp đồng.
