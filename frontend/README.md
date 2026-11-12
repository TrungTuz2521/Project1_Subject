# Frontend

React + TypeScript + Vite cho hệ thống đặt sân bóng và tìm kèo. Frontend luôn gọi backend Flask; không có chế độ dữ liệu giả.

## Chạy trên máy

Cần Node.js 24 và npm. Chạy backend trước (xem [backend/README.md](../backend/README.md)), rồi trong thư mục `frontend`:

```powershell
copy .env.example .env.local   # lần đầu
npm ci
npm run dev
```

Mở http://localhost:5173. Sửa `.env.local` thì khởi động lại Vite.

| Biến | Ý nghĩa |
| --- | --- |
| `VITE_API_BASE_URL` | Địa chỉ API, ví dụ `http://localhost:5000/api/v1` |
| `VITE_GOOGLE_CLIENT_ID` | Client ID Google, trùng `GOOGLE_CLIENT_ID` của backend; để trống thì ẩn nút Google |
| `VITE_DEMO_DEPOSIT` | `true` hiện nút xác nhận cọc demo (backend cũng phải bật `DEMO_PAYMENT_ENABLED`); production để `false` |

Mọi biến `VITE_*` lộ ra trình duyệt: không đặt mật khẩu database, khóa SePay hay thông tin ngân hàng ở đây.

Kiểm tra trước khi đẩy code (CI chạy cùng hai lệnh này):

```powershell
npm test
npm run build
```

## Màn hình

| Đường dẫn | Ai dùng | Nội dung |
| --- | --- | --- |
| `#/bookings` | Mọi người | Xem sân, giờ trống và giá; đăng nhập để giữ sân |
| `#/my-bookings` | Người chơi | Lịch đã đặt, đóng cọc bằng QR (SePay), hủy |
| `#/matchmaking` | Người chơi | Tìm kèo: gửi yêu cầu tìm đối / tìm thêm người / đá ké, xem kết quả ghép |
| `#/teams` | Người chơi | Tạo và đổi tên đội. Đội chỉ có tên và đội trưởng; số người đi đá khai báo khi tìm đối |
| `#/notifications` | Người chơi | Thông báo trong app |
| `#/profile` | Mọi tài khoản | Hồ sơ, tài khoản nhận hoàn tiền, đổi mật khẩu |
| `#/dashboard` | Admin | Hôm nay: giữ sân chờ cọc, trận hôm nay, chưa thu đủ, hoàn tiền, cảnh báo việc nền trễ |
| `#/admin/bookings` | Admin | Lịch sân, đặt tại quầy, khách quen hằng tuần, bảo trì, check-in |
| `#/admin/balance` | Admin | Thu phần còn lại sau trận |
| `#/admin/pitches` | Admin | Sân, giá, giờ cao điểm |
| `#/admin/revenue`, `#/admin/statistics` | Admin | Doanh thu, xuất Excel, thống kê |
| `#/admin/match-requests` | Admin | Các yêu cầu tìm kèo |

Tài khoản Admin chỉ thấy màn hình Admin. Ẩn menu không phải bảo mật: backend vẫn kiểm tra quyền mọi API.

## Cấu trúc

| Thư mục / tệp | Nội dung |
| --- | --- |
| `src/App.tsx` | Điều hướng theo hash, đăng nhập/đăng ký, hồ sơ, chọn shell Player/Admin |
| `src/services/api.ts`, `client.ts` | API client: envelope `{data, meta}`, Bearer token, lỗi `ApiError`, timeout/abort |
| `src/services/auth.ts`, `src/stores/session.ts` | Đăng nhập, gia hạn token khi app đang mở, phiên trong bộ nhớ |
| `src/services/fieldApi.ts` | Sân, đặt sân, các API Admin (lịch, thu tiền, hoàn tiền, doanh thu) và định dạng giờ/tiền Việt Nam |
| `src/services/depositBank.ts` | Hướng dẫn cọc, QR SePay, xác nhận cọc demo |
| `src/services/matchRequests.ts`, `teams.ts`, `notifications.ts` | Tìm kèo, đội, thông báo |
| `src/types/api.ts` | Kiểu dữ liệu dùng chung với backend |
| `src/features/` | Màn hình người chơi: `pitches`, `bookings`, `payments`, `matchfind`, `matchmaking` (đội), `auth`, `player`, `admin` (khung Admin) |
| `src/pages/admin/` | Màn hình Admin |
| `src/styles/` | CSS |

## Quy ước gọi API

```ts
import { api } from './client';
import type { PaginatedResponse, Booking } from '../types/api';

export function getMyBookings(signal?: AbortSignal) {
  return api.request<PaginatedResponse<Booking>>('/bookings/my', { query: { page: 1, page_size: 20 }, signal });
}
```

- Truyền path như `/teams`, không lặp `/api/v1`. Mặc định có gửi token; API công khai truyền `auth: false`.
- Gửi JSON bằng `body: {...}`; đọc kết quả qua `result.data` và `result.meta`.
- HTTP 401 xóa phiên và đưa về đăng nhập; 403/409/422 không xóa phiên. Hiện lỗi form bằng `ApiError.fields`, lỗi chung bằng `errorMessage(error)`.
- Truyền `AbortSignal` cho GET để kết quả cũ không ghi đè khi đổi trang. Không tự gửi lại POST tạo đơn/thanh toán.
- Tiền là chuỗi thập phân (`"120000.00"`), không tính bằng số thực. Giờ gửi dạng ISO có múi giờ, hiển thị theo `Asia/Ho_Chi_Minh`.
- Phiên lưu trong `sessionStorage` (tải lại trang không mất), và cả `localStorage` khi chọn "Ghi nhớ đăng nhập"; app tự gia hạn token khi còn dưới 15 phút.

## Tài liệu liên quan

- [Hợp đồng API](../docs/api/API_MODELS_CONTRACT_PROJECT1.md)
- [Test frontend với backend](../docs/setup/FRONTEND_BACKEND_TESTING.md)
- [Cọc QR SePay](../docs/setup/SEPAY_QR.md), [Demo cọc](../docs/setup/DEMO_DEPOSIT.md)
- [Đăng nhập Google](../docs/setup/GOOGLE_LOGIN.md), [Email thông báo](../docs/setup/EMAIL_NOTIFICATIONS.md)
