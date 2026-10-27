# Bộ frontend dùng chung

React + TypeScript + Vite. Màn hình mẫu là **Đội bóng của tôi**: đăng nhập mẫu, GET danh sách có phân trang, POST tạo đội, thông báo thành công, lỗi từng trường và lỗi toàn màn hình.

## Chạy trên máy

Trong thư mục `frontend`, dùng Node 24 LTS và npm:

```powershell
npm ci
npm run dev
```

Mở URL terminal hiển thị, thường là http://localhost:5173. Chế độ dev mặc định dùng mock, không cần backend hoặc TiDB. Bấm **Đăng nhập bằng tài khoản mẫu**, rồi thử tạo đội và các tình huống lỗi trong thanh công cụ. Reload trang đặt lại dữ liệu và cần đăng nhập mẫu lại.

```powershell
npm test
npm run build
```

Build production luôn tắt mock, kể cả khi VITE_USE_MOCKS=true. `npm run preview` kiểm tra build production, vì vậy cần backend thật; dùng `npm run dev` để xem mẫu.

## Chuyển sang Flask thật

Tạo `frontend/.env.local` từ `.env.example`:

```dotenv
VITE_API_BASE_URL=http://localhost:5000/api/v1
VITE_USE_MOCKS=false
```

Khởi động lại Vite sau khi đổi cấu hình. Backend cần cho phép CORS từ frontend và header Authorization/Content-Type. Không dùng cổng frontend làm API base nếu chưa có reverse proxy. Production dùng HTTPS hoặc đường dẫn `/api/v1` cùng origin.

Frontend KHÔNG kết nối TiDB và không chứa mật khẩu database. Mọi VITE_* đều là cấu hình công khai trong trình duyệt. Không sao chép backend/.env vào frontend.

## Các tệp cần dùng

| Tệp | Cách dùng |
| --- | --- |
| `src/services/api.ts` | `createApiClient`, `ApiError`, timeout, abort, query, envelope, token |
| `src/services/client.ts` | Instance `api` chung; chọn mock/Flask bằng cấu hình |
| `src/stores/session.ts` | Lưu phiên trong bộ nhớ, tự xóa khi hết hạn, không refresh token |
| `src/services/auth.ts` | `login()` cấp phiên; `logout()` xóa phiên phía client |
| `src/services/teams.ts` | Ví dụ service endpoint GET/POST của một module |
| `src/types/api.ts` | DTO, ENUM, request/response của các module |
| `src/mocks/fixtures.ts` | Dữ liệu tổng hợp: user, đội, sân, bài, đề xuất, booking, payment, thông báo, doanh thu |
| `src/mocks/server.ts` | Handler mock có kiểm tra Bearer, phân trang, tạo đội, lỗi 422/409/401 |
| `src/features/matchmaking/TeamsPage.tsx` | Màn hình hoàn chỉnh để các bạn làm mẫu |

## Quy ước gọi API

Ví dụ service mới:

```ts
import { api } from './client';
import type { PaginatedResponse, Booking } from '../types/api';

export function getMyBookings(signal?: AbortSignal) {
  return api.request<PaginatedResponse<Booking>>('/bookings/my', {
    query: { page: 1, page_size: 20 }, signal,
  });
}
```

- Truyền path `/teams`, không lặp `/api/v1`, không truyền URL ngoài. Client chỉ gửi token đến base API đã cấu hình, không theo redirect.
- Mặc định cần đăng nhập. Endpoint công khai truyền `auth:false` và không gửi token.
- Request JSON dùng `body:{...}`; không tự JSON.stringify ở màn hình.
- Kết quả giữ nguyên envelope: dùng `result.data` và `result.meta`, không trả thẳng mảng từ mock.
- Token giữ trong bộ nhớ: access token có hạn tối đa 60 phút; reload hoặc hết hạn cần đăng nhập lại. Không localStorage, không refresh token.
- `logout()` chỉ xóa phiên trên máy; hợp đồng backend chưa có endpoint thu hồi JWT, token đã phát có thể còn hợp lệ đến exp. Backend luôn kiểm tra trạng thái tài khoản.
- HTTP 401 ở API bảo vệ xóa đúng phiên đã gửi request; React quay lại trạng thái đăng nhập. HTTP 403/422/409 không tự xóa phiên.
- AbortSignal hủy GET khi unmount/đổi trang để kết quả cũ không ghi đè. Không tự retry POST tạo đội/thanh toán, tránh tạo trùng dữ liệu.
- Dùng `ApiError.fields` để hiển thị lỗi form; `errorMessage(error)` cho lỗi chung. Không ghi token hoặc payload nhạy cảm vào console.
- TypeScript kiểm tra lúc build; client chỉ kiểm tra envelope cơ bản ở runtime, không phải bộ validator đầy đủ cho từng DTO. Backend vẫn phải xác thực mọi dữ liệu.
- Tiền là chuỗi thập phân, không đổi sang float để tính cọc. Thời gian gửi ISO có offset; hiển thị dùng timeZone Asia/Ho_Chi_Minh.

## Dữ liệu mẫu và phạm vi mock

Mock hiện hỗ trợ:

- POST /auth/login (tài khoản mẫu, không xác thực người dùng thật).
- GET /users/me; GET/POST /teams.
- GET /pitches, /match-posts, /bookings/my, /notifications.

Booking/payment/proposal/revenue fixture giúp dựng màn hình nhưng không đồng nghĩa đã có toàn bộ handler. Endpoint chưa làm trả 501 MOCK_NOT_IMPLEMENTED. Không có thu tiền, tạo QR thật, xác nhận trận, email hoặc quyền Admin thật.

Ngày trận tự dịch sang ngày mai để mẫu không hết hạn theo lịch. Hold mẫu 5 phút tính từ lúc khởi tạo mock; fixture không mô phỏng đầy đủ worker hết hạn/hoàn tiền. Không dùng mock làm bằng chứng nghiệp vụ thanh toán đã đúng.

Thanh tình huống lỗi chỉ xuất hiện trong dev mock. Chế độ danh sách trống luôn ẩn danh sách kể cả sau POST; chuyển về Bình thường để xem các đội đã tạo. Chế độ 422 cho phép thử lỗi do server trả về dù input hợp lệ. Nút thử 401 làm phiên mẫu bị server từ chối ở GET kế tiếp.

Để thêm endpoint mock: tạo fixture theo DTO → thêm handler có method/path chính xác → kiểm tra quyền và dữ liệu đầu vào → trả đúng envelope và HTTP status → kiểm tra màn hình bằng cả mock lẫn API thật khi có.

## Chia phần cho nhóm

- **Duy Minh:** dùng services/auth.ts và session để xây form đăng nhập/đăng ký và khung điều hướng; không tự lưu token theo cách khác.
- **Quang:** phát triển tiếp màn hình đội/bài/đề xuất từ TeamsPage, dùng DTO chung.
- **Huy:** dùng fixtures sân/booking/doanh thu để dựng màn hình; không giả báo đã thanh toán thành công.
- **Đức/Tú:** triển khai backend theo cùng hợp đồng, review service/DTO và nối API thật. Google Login chưa nằm trong bộ mẫu này.

Đối chiếu nguồn chính tại [API và Models](../docs/api/API_MODELS_CONTRACT_PROJECT1.md). DTO BookingStatistics.by_pitch trong bản mẫu là cấu trúc đề xuất cho mảng thống kê hoạt động; hợp đồng hiện mới chốt tên trường, cần đồng bộ với backend khi triển khai. Không có báo cáo doanh thu theo mặt sân.
