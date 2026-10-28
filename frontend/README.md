# Bộ frontend dùng chung

React + TypeScript + Vite cho hệ thống đặt sân bóng, ghép đội và tìm trận. Đã tích hợp module **tài khoản và khung ứng dụng** theo `docs/api/API_MODELS_CONTRACT_PROJECT1.md`: đăng nhập/đăng ký, hồ sơ GET/PATCH, điều hướng theo hash, đăng xuất, phiên access token trong bộ nhớ tối đa 60 phút và trở về đăng nhập khi token hết hạn/được API trả 401. Màn hình **Đội bóng của tôi** tiếp tục được giữ làm ví dụ CRUD theo hợp đồng API.

## Chạy trên máy

Cần Node.js 24 LTS (hoặc bản Node tương thích với phiên bản Vite trong `package.json`) và npm. Mở Terminal trong thư mục `frontend`:

```powershell
npm ci
npm run dev
```

Mở URL terminal hiển thị, thường là http://localhost:5173. Chế độ dev mặc định dùng mock, không cần backend hoặc TiDB. Tại màn hình đăng nhập, dùng nút **Đăng nhập nhanh bằng tài khoản mẫu** (email `demo@example.test`, mật khẩu `mock-only`), hoặc tạo tài khoản demo mới. Sau đăng nhập, thử cập nhật hồ sơ, điều hướng và tạo đội. Dữ liệu mock chỉ lưu trong bộ nhớ và được đặt lại khi tải lại trang; cần đăng nhập lại sau reload.

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
| `src/stores/session.ts` | Lưu phiên trong bộ nhớ, cập nhật user không gia hạn token, tự xóa khi hết hạn, không refresh token |
| `src/services/auth.ts` | `register()`, `login()`, `getCurrentUser()`, `updateCurrentUser()`, `logout()` |
| `src/services/teams.ts` | Ví dụ service endpoint GET/POST của một module |
| `src/types/api.ts` | DTO, ENUM, request/response của các module |
| `src/mocks/fixtures.ts` | Dữ liệu tổng hợp: user, đội, sân, bài, đề xuất, booking, payment, thông báo, doanh thu |
| `src/mocks/server.ts` | Handler mock có kiểm tra Bearer, phân trang, tạo đội, lỗi 422/409/401 |
| `src/App.tsx` | Form đăng nhập/đăng ký, shell điều hướng, dashboard, hồ sơ, trang khung các module |
| `src/features/matchmaking/TeamsPage.tsx` | Màn hình đội bóng mẫu; điều hướng trở lại các khu vực tài khoản |

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

- POST /auth/register và POST /auth/login (tài khoản demo và tài khoản được đăng ký trong bộ nhớ; không xác thực người dùng thật).
- GET/PATCH /users/me; GET/POST /teams.
- GET /pitches, /match-posts, /bookings/my, /notifications.

Booking/payment/proposal/revenue fixture giúp dựng màn hình nhưng không đồng nghĩa đã có toàn bộ handler. Endpoint chưa làm trả 501 MOCK_NOT_IMPLEMENTED. Không có thu tiền, tạo QR thật, xác nhận trận, email hoặc quyền Admin thật.

Ngày trận tự dịch sang ngày mai để mẫu không hết hạn theo lịch. Hold mẫu 5 phút tính từ lúc khởi tạo mock; fixture không mô phỏng đầy đủ worker hết hạn/hoàn tiền. Không dùng mock làm bằng chứng nghiệp vụ thanh toán đã đúng.

Thanh tình huống lỗi chỉ xuất hiện trong dev mock. Chế độ danh sách trống luôn ẩn danh sách kể cả sau POST; chuyển về Bình thường để xem các đội đã tạo. Chế độ 422 cho phép thử lỗi do server trả về dù input hợp lệ. Nút thử 401 làm phiên mẫu bị server từ chối ở GET kế tiếp.

Để thêm endpoint mock: tạo fixture theo DTO → thêm handler có method/path chính xác → kiểm tra quyền và dữ liệu đầu vào → trả đúng envelope và HTTP status → kiểm tra màn hình bằng cả mock lẫn API thật khi có.

## Chia phần cho nhóm

- **Duy Minh:** module tài khoản/khung ứng dụng đã được tích hợp tại `src/App.tsx`; tiếp tục đồng bộ giao diện với backend theo `services/auth.ts` và `stores/session.ts`. Không tự lưu token ở localStorage/sessionStorage hoặc tạo một luồng refresh token riêng.
- **Quang:** phát triển tiếp màn hình đội/bài/đề xuất từ TeamsPage, dùng DTO chung.
- **Huy:** dùng fixtures sân/booking/doanh thu để dựng màn hình; không giả báo đã thanh toán thành công.
- **Đức/Tú:** triển khai backend theo cùng hợp đồng, review service/DTO và nối API thật. Google Login chưa nằm trong bộ mẫu này.

Đối chiếu nguồn chính tại [API và Models](../docs/api/API_MODELS_CONTRACT_PROJECT1.md). DTO BookingStatistics.by_pitch trong bản mẫu là cấu trúc đề xuất cho mảng thống kê hoạt động; hợp đồng hiện mới chốt tên trường, cần đồng bộ với backend khi triển khai. Không có báo cáo doanh thu theo mặt sân.


## Module tài khoản — cách kiểm tra nhanh

1. Mở `#/login`, thử tài khoản mẫu: `demo@example.test` / `mock-only`.
2. Vào **Hồ sơ cá nhân**, cập nhật họ tên/số điện thoại/trình độ rồi lưu; UI gọi `GET /users/me` và `PATCH /users/me`.
3. Đăng xuất, mở **Đăng ký ngay**, điền tên/email/mật khẩu (8–72 byte UTF-8), sau đó đăng nhập bằng tài khoản vừa đăng ký. Email trùng trả về lỗi 409.
4. Để thử hết hạn phiên, trên trang Đội bóng của tôi chọn **Thử lỗi token 401** ở thanh tình huống; yêu cầu API tiếp theo bị từ chối và app đưa người dùng về đăng nhập.
5. Các đường dẫn đặt sân/ghép đội/thông báo trong khung hiện là trang giữ chỗ; không giả lập thành công nghiệp vụ chưa được triển khai.

**Bảo mật:** token chỉ ở bộ nhớ, bị xóa sau 60 phút hoặc khi API bảo vệ trả 401. Tải lại trang cần đăng nhập lại theo hợp đồng hiện tại; chưa có refresh token hoặc API thu hồi JWT. Chế độ mock chỉ để phát triển giao diện và không thay thế xác thực/kiểm tra quyền của backend.
