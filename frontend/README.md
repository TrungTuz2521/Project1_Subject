# Bộ frontend dùng chung

React + TypeScript + Vite cho hệ thống đặt sân bóng, ghép đội và tìm trận. Đã tích hợp module **tài khoản và khung ứng dụng** theo `docs/api/API_MODELS_CONTRACT_PROJECT1.md`: đăng nhập/đăng ký, hồ sơ GET/PATCH, điều hướng theo hash, đăng xuất, phiên access token trong bộ nhớ tối đa 60 phút và trở về đăng nhập khi token hết hạn/được API trả 401. Phân hệ **Quản lý đội bóng & Ghép trận** được triển khai theo module: quản lý đội/thành viên, bài đăng, đề xuất, xác nhận hai phía, thông báo và lịch thi đấu. Giao diện kế thừa shell, CSS, API Client, session và DTO hiện tại.

## Chạy trên máy

Cần Node.js 24 LTS (hoặc bản Node tương thích với phiên bản Vite trong `package.json`) và npm. Mở Terminal trong thư mục `frontend`:

```powershell
npm ci
npm run dev
```

Mở URL terminal hiển thị, thường là http://localhost:5173. Chế độ dev mặc định dùng mock, không cần backend hoặc TiDB. Tại màn hình đăng nhập, dùng **Đăng nhập nhanh bằng tài khoản mẫu** (`demo@example.test` / `mock-only`) hoặc **Thử tài khoản đội trưởng mẫu** (`captain@example.test` / `mock-only`). Có thể đăng ký tài khoản demo mới để thử vai trò ứng viên. Mock hỗ trợ nhiều session cùng lúc để kiểm tra xác nhận của hai người dùng. Dữ liệu mock chỉ lưu trong bộ nhớ, được đặt lại khi tải lại trang; cần đăng nhập lại sau reload.

```powershell
npm test
npm run build
```

Build production luôn tắt mock, kể cả khi VITE_USE_MOCKS=true. `npm run preview` kiểm tra build production, vì vậy cần backend thật; dùng `npm run dev` để xem mẫu.

## Chuyển sang Flask thật

Xem [hướng dẫn test frontend/backend từng bước](../docs/setup/FRONTEND_BACKEND_TESTING.md), bao gồm tạo .env.local, chạy hai server, tài khoản test và cách xử lý lỗi.


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
| `src/services/teams.ts` | Đội, chi tiết/thành viên, yêu cầu tham gia, phản hồi, rời đội/xóa thành viên |
| `src/services/matchPosts.ts` | Bảng tin, bài của tôi, tạo/sửa/hủy, đăng ký tham gia |
| `src/services/proposals.ts` | Danh sách/chi tiết đề xuất và phản hồi ACCEPTED/DECLINED |
| `src/services/matches.ts` | Danh sách và chi tiết trận đấu |
| `src/services/notifications.ts` | Thông báo và đánh dấu đã đọc |
| `src/types/api.ts` | DTO, ENUM, request/response của các module |
| `src/mocks/fixtures.ts` | Dữ liệu tổng hợp: user, đội, sân, bài, đề xuất, booking, payment, thông báo, doanh thu |
| `src/mocks/server.ts` | Mock handler theo DTO/envelope, session đa tài khoản, phân trang, phân quyền và lỗi 4xx/5xx |
| `src/App.tsx` | Form đăng nhập/đăng ký, shell điều hướng, dashboard, hồ sơ, đội bóng, ghép trận, thông báo và lịch |
| `src/features/matchmaking/TeamsPage.tsx` | Danh sách, chi tiết, tạo/sửa đội, roster, yêu cầu tuyển và thao tác Captain |
| `src/features/matchmaking/MatchmakingPage.tsx` | 4 loại bài đăng, bộ lọc, CRUD bài, đề xuất, xác nhận, trận và thông báo |
| `src/features/matchmaking/SchedulePage.tsx` | Lịch ngày/tuần/tháng; CONFIRMED và SUGGESTED được tách riêng |

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

Mock hiện hỗ trợ các endpoint của phân hệ này:

- Auth/profile: POST /auth/register, POST /auth/login, GET/PATCH /users/me.
- Đội: GET/POST /teams, GET/PATCH /teams/{team_id}, POST/PATCH join-requests, DELETE members/me và members/{user_id}.
- Bài đăng: GET /match-posts, GET /match-posts/my, POST/GET/PATCH /match-posts/{post_id}, POST cancel, GET/POST participants.
- Ghép trận: GET /match-proposals, GET /match-proposals/{proposal_id}, POST respond, GET /matches, GET /matches/{match_id}.
- Thông báo: GET /notifications, PATCH /notifications/{notification_id}/read.
- Dữ liệu hỗ trợ demo: GET /pitches, GET /bookings/my.

Mock kiểm tra Bearer/session, quyền thành viên/đội trưởng, party của proposal, chủ thông báo, response envelope, phân trang, validation và các xung đột nghiệp vụ cơ bản. Mock không lưu dữ liệu bền vững và không xác thực người dùng thật.

**Giới hạn không giả lập:** không chạy thuật toán AI, không giữ sân thật, không gọi VNPay/MoMo, không thu/hoàn tiền, không tự tạo Booking đã thanh toán, không giả báo email gửi thành công. Khi hai bên đồng ý proposal OPPONENT, mock chỉ tạo Match SUGGESTED; không đổi sang CONFIRMED. Proposal TEAM_MEMBER chỉ thêm thành viên sau khi cả đội trưởng và ứng viên cùng xác nhận. Các chức năng booking/payment/hoàn tiền phụ thuộc Backend.

Ngày trận fixture được tạo tương đối theo thời điểm khởi tạo. Dữ liệu và session mẫu chỉ tồn tại trong bộ nhớ; không dùng mock làm bằng chứng nghiệp vụ thanh toán/booking ở Backend đã đúng.

Thanh tình huống lỗi chỉ xuất hiện trong dev mock. Chế độ danh sách trống luôn ẩn danh sách kể cả sau POST; chuyển về Bình thường để xem các đội đã tạo. Chế độ 422 cho phép thử lỗi do server trả về dù input hợp lệ. Nút thử 401 làm phiên mẫu bị server từ chối ở GET kế tiếp.

Để thêm endpoint mock: tạo fixture theo DTO → thêm handler có method/path chính xác → kiểm tra quyền và dữ liệu đầu vào → trả đúng envelope và HTTP status → kiểm tra màn hình bằng cả mock lẫn API thật khi có.

## Chia phần cho nhóm

- **Duy Minh:** module tài khoản/khung ứng dụng đã được tích hợp tại `src/App.tsx`; tiếp tục đồng bộ giao diện với backend theo `services/auth.ts` và `stores/session.ts`. Không tự lưu token ở localStorage/sessionStorage hoặc tạo một luồng refresh token riêng.
- **Quang:** phụ trách phân hệ frontend đội bóng/ghép trận/thông báo/lịch trên nhánh `feature/quang-team-matchmaking`; các thay đổi chờ review/PR, không commit vào `main`.
- **Huy:** dùng fixtures sân/booking/doanh thu để dựng màn hình; không giả báo đã thanh toán thành công.
- **Đức/Tú:** triển khai backend theo cùng hợp đồng, review service/DTO và nối API thật. Google Login đã được bổ sung cho backend thật; không giả lập trong mock.

Đối chiếu nguồn chính tại [API và Models](../docs/api/API_MODELS_CONTRACT_PROJECT1.md). DTO BookingStatistics.by_pitch trong bản mẫu là cấu trúc đề xuất cho mảng thống kê hoạt động; hợp đồng hiện mới chốt tên trường, cần đồng bộ với backend khi triển khai. Không có báo cáo doanh thu theo mặt sân.


## Module tài khoản — cách kiểm tra nhanh

1. Mở `#/login`, thử tài khoản mẫu: `demo@example.test` / `mock-only`.
2. Vào **Hồ sơ cá nhân**, cập nhật họ tên/số điện thoại/trình độ rồi lưu; UI gọi `GET /users/me` và `PATCH /users/me`.
3. Đăng xuất, mở **Đăng ký ngay**, điền tên/email/mật khẩu (8–72 byte UTF-8), sau đó đăng nhập bằng tài khoản vừa đăng ký. Email trùng trả về lỗi 409.
4. Để thử hết hạn phiên, trên trang Đội bóng của tôi chọn **Thử lỗi token 401** ở thanh tình huống; yêu cầu API tiếp theo bị từ chối và app đưa người dùng về đăng nhập.
5. Mở `#/teams` để quản lý đội, `#/matchmaking` để tạo/lọc bài và xem proposal, `#/notifications` để xem thông báo, `#/schedule` để xem lịch ngày/tuần/tháng.
6. Tài khoản đội trưởng mẫu: `captain@example.test` / `mock-only`. Tạo tài khoản mới (PLAYER) để thử luồng ứng viên, rồi dùng tài khoản đội trưởng để chấp thuận và quay lại ứng viên để xác nhận proposal.
7. GitHub Actions workflow `Frontend checks` chạy `npm ci`, `npm test` và `npm run build` khi push lên nhánh tính năng hoặc pull request.

**Bảo mật:** token chỉ ở bộ nhớ, bị xóa sau 60 phút hoặc khi API bảo vệ trả 401. Tải lại trang cần đăng nhập lại theo hợp đồng hiện tại; chưa có refresh token hoặc API thu hồi JWT. Chế độ mock chỉ để phát triển giao diện và không thay thế xác thực/kiểm tra quyền của backend.


## Tích hợp frontend Huy vào ứng dụng chung

Chạy `npm ci`, `npm run dev`; dùng `index.html` (địa chỉ gốc Vite). `san-bong.html` cũng dùng cùng App và đăng nhập, không có phiên Admin riêng.
Trong `.env.local`: `VITE_API_BASE_URL=http://127.0.0.1:5000/api/v1` và `VITE_USE_MOCKS=false`; khởi động lại Vite sau khi đổi env. Không commit env riêng.

- Sau đăng nhập: `#/bookings` tìm sân, `#/my-bookings` theo dõi hold/cọc. Tạo booking sẽ mở chi tiết trong cùng phiên; hold 300 giây từ server, không gia hạn do tải lại/tạo thanh toán.
- Chỉ ADMIN thấy và mở được `#/admin/bookings`, `#/admin/pitches`, `#/admin/balance`, `#/admin/revenue`. Backend vẫn là nơi kiểm tra quyền; không coi ẩn menu là bảo mật API.
- Lịch Admin lọc `UPCOMING`, `IN_PROGRESS`, `ENDED_UNPAID`, `PAID` qua API; đã thu đủ lấy từ balance, độc lập giờ đá. Danh sách Admin hiện lấy tối đa 100 mục/lần.
- Thu tiền dùng `GET /admin/bookings/{id}/balance` và `POST /admin/bookings/{id}/confirm-paid`. Không gọi endpoint settlement/result hoặc tạo QR riêng từng đội. Thể thức chỉ để hai đội tự chia.
- QR được tạo cục bộ từ payload server bằng thư viện qrcode. Không gửi dữ liệu ngân hàng ra dịch vụ tạo QR. Nếu backend chưa cấu hình BANK_BIN/BANK_ACCOUNT_NO thì hiển thị lý do thiếu QR.
- Admin chọn một/nhiều khoản thực nhận CASH/BANK_TRANSFER, tổng đúng số còn thiếu; gửi expected_outstanding + idempotency_key. Retry sau lỗi giữ nguyên payload/key; form khóa đến khi thử lại hoặc tải lại số dư. Backend xử lý chống trùng và số dư thay đổi.
- Luồng cọc hiện dùng QR và nút xác nhận DEMO gọi backend khi bật hai flag; adapter VNPay giữ để tích hợp thật sau. Frontend không tự ghi SUCCESS.

Kiểm tra trên DB thử nghiệm: PLAYER đăng nhập, mở sân/giữ 90 phút, xem hạn giữ; PLAYER mở URL Admin phải bị chặn. ADMIN mở lịch, lọc giai đoạn, mở booking đã kết thúc và đối chiếu balance; nhập tổng receipts sai phải bị chặn, thu đủ một/multiple khoản phải về PAID, gọi lại cùng key không thêm Payment. Hai tab số dư cũ phải báo conflict. Không thử thu/hoàn tiền thật hoặc chạy migration trên DB nhóm.

Mock chỉ là dữ liệu trong bộ nhớ riêng cho giao diện sân và không đại diện cho luồng ghép trận/tiền thật. Khi đánh giá tích hợp cần `VITE_USE_MOCKS=false`.

### Cấu hình tài khoản nhận QR sau trận

Trong `backend/.env` riêng của máy chạy server, điền `BANK_BIN` (mã BIN của ngân hàng nhận) và `BANK_ACCOUNT_NO` (số tài khoản nhận), rồi khởi động lại backend. Không đặt trong frontend, không commit `.env`, không cần tải ảnh QR cá nhân. Payload VietQR do backend tạo theo tài khoản đã cấu hình + outstanding_amount + BOOKING-{id}; frontend chỉ mã hóa payload thành ảnh QR. Kiểm tra tên người nhận, số tài khoản, số tiền và nội dung trên ứng dụng ngân hàng trước khi dùng. QR ngân hàng này dành cho phần còn lại sau trận; cọc VNPay dùng cấu hình gateway riêng. Không nhập mật khẩu ngân hàng hoặc OTP vào dự án.

### Quân số buổi đá

Đội chỉ có tên và đội trưởng (người đại diện đặt sân, nhận thông báo); không lưu danh sách thành viên. Mỗi yêu cầu tìm đối khai báo `player_count` (tính cả đội trưởng, tối thiểu 5 với sân 5, 7 với sân 7); form điền sẵn số của lần trước (`last_player_count` của đội). Trang Đội chỉ để tạo đội và đổi tên.

Bộ chọn giờ đá áp dụng cho tạo và sửa bài tìm đối thủ, tuyển thành viên và ghép nhóm: chọn ngày rồi chọn giờ trong danh sách hợp lệ, tự tính kết thúc sau 90 phút. Khi sửa bài cá nhân tìm đội, lịch vẫn có thể bỏ trống; nếu bổ sung lịch thì chọn từ cùng danh sách. Hạn nhận yêu cầu là thời hạn riêng, vẫn cho chọn phút tùy ý trước hoặc bằng giờ đá.

Thông báo Đã giữ sân có nút Thanh toán tiền cọc, mở Booking của tôi và chọn đúng booking theo booking_id trên hash URL. Đây là chuyển trang; người dùng vẫn phải bấm Thanh toán cọc VNPay trong chi tiết. Xem [thiết lập và demo VNPay](../docs/setup/VNPAY_SANDBOX.md).

## Google Login và thông báo email

Trong `frontend/.env.local`, đặt `VITE_USE_MOCKS=false`, API base thật và `VITE_GOOGLE_CLIENT_ID=<Client ID trùng backend GOOGLE_CLIENT_ID>`, sau đó khởi động lại Vite. Dùng `http://localhost:5173` đã đăng ký trên Google Console; nếu cần chạy `npm run dev -- --host localhost`.
Form đăng nhập hiển thị nút Google. Email mới tạo PLAYER; email đã có tài khoản cần mật khẩu web để liên kết lần đầu. Giữ session trong bộ nhớ 60 phút, không refresh token. Xem [hướng dẫn Google](../docs/setup/GOOGLE_LOGIN.md).

Email được backend/worker gửi, frontend không giữ mật khẩu SMTP và không gọi Gmail trực tiếp. Mỗi thành viên chỉ cấu hình Gmail ở backend nếu cần thử gửi thật; mặc định EMAIL_ENABLED=false vẫn dùng được thông báo trên web. Không thấy email thì kiểm tra worker, email thật của user và Spam; không coi email là điều kiện để booking thành công. Xem [Gmail SMTP và worker](../docs/setup/EMAIL_NOTIFICATIONS.md).
Thông báo trong app vẫn là chính cho hạn cọc 5 phút; mở link email không gia hạn hold.


## Thông báo đăng ký tuyển thành viên — 10/11/2026

Khi B đăng ký bài RECRUIT_MEMBERS của A, backend ghi cho A thông báo **Có người đăng ký tham gia**,
kèm tên B và tên bài. Nếu EMAIL_ENABLED=true, A có EMAIL/PENDING trong cùng transaction.
B nhận IN_APP **Đã gửi đăng ký tham gia**, không gửi thêm email yêu cầu B xác nhận lại.
B bấm đăng ký là đã ghi consent ACCEPTED; A duyệt là thêm B vào đội và cập nhật quân số ngay.
Khi duyệt thành công, B nhận IN_APP và EMAIL/PENDING **Bạn đã được thêm vào đội**; email worker gửi sau commit.
Luồng này chỉ áp dụng đăng ký trực tiếp vào bài RECRUIT_MEMBERS. Đề xuất AI và ghép đối thủ vẫn cần cả hai bên tự xác nhận.
Email mới có link `/#/notifications?proposal_id=<id>`; sau đăng nhập mở đúng chi tiết đề xuất.
Backend vẫn kiểm tra người xem thuộc đề xuất, không mở dữ liệu cho tài khoản khác.

Trang Ghép đội/Thông báo tự cập nhật thông báo và danh sách đề xuất mỗi 10 giây khi tab trình duyệt đang hiện,
và khi quay lại cửa sổ; có nút Làm mới. Không tải lại toàn trang hoặc xóa form đang nhập.
Chọn mục Thông báo ở sidebar cũng đổi đúng tab khi đang ở trang Ghép đội.

Sau cập nhật cần khởi động lại backend và email worker. Thay đổi áp dụng cho đăng ký mới;
không sửa hoặc gửi lại email đã SENT. SENT là SMTP chấp nhận, chưa đảm bảo inbox: kiểm tra email trong hồ sơ
của A và mục Spam. Mock/unit test không gửi thư thật; việc kiểm tra TiDB thực tế chỉ đọc trạng thái.


## Đổi mật khẩu — 10/11/2026

Trong app: **Hồ sơ cá nhân → Đổi mật khẩu**. Nhập mật khẩu hiện tại, mật khẩu mới và nhập lại;
mật khẩu mới dài 8–72 byte UTF-8, khác mật khẩu cũ. Thành công sẽ đăng xuất phiên trên trình duyệt hiện tại
và yêu cầu đăng nhập lại. Sai mật khẩu cũ/nhập lại không khớp không làm đổi dữ liệu.
Tài khoản chỉ dùng Google và chưa có mật khẩu web thì hiện hướng dẫn đổi ở Google; chưa hỗ trợ đặt mật khẩu web đầu tiên.

API: `POST /api/v1/users/me/password`, cần Bearer JWT của chính người dùng.
JSON: `{current_password,new_password,confirm_password}`; trả `{data:{changed:true},meta}`.
Không nhận user_id/role/password_hash; sai dữ liệu trả 422, Google-only trả 409 PASSWORD_NOT_SET,
không có phiên/hết hạn trả 401, tài khoản khóa trả 403. Endpoint có rate limit auth dùng chung.
UserSelf bổ sung boolean `has_password`, không trả hash hay Google ID.
Không có refresh token/revocation: JWT ở thiết bị khác vẫn có thể còn hiệu lực tới exp (tối đa 60 phút từ lúc cấp).
Đây là đổi mật khẩu khi đã biết mật khẩu cũ; chưa phải chức năng Quên mật khẩu/Reset email.
Không cần migration hoặc thay mật khẩu thật khi cài code.


### Sửa đồng bộ duyệt tại trang Đội bóng — 10/11/2026

Trang Đội bóng không còn thông báo ứng viên phải xác nhận lần hai. Chỉ báo thêm thành viên thành công
khi backend trả participant ACCEPTED, đồng thời tải lại roster và số thành viên trong danh sách.
Nếu backend cũ còn trả PENDING, giao diện chỉ rõ chưa thêm được và cần khởi động lại backend.
Yêu cầu trực tiếp cũ có A ACCEPTED/B PENDING được A duyệt lại để hoàn tất, chỉ khi còn hạn và hợp lệ;
không hồi sinh yêu cầu hết hạn, không thêm trùng thành viên/email khi gọi lặp.
Kiểm thử tách biệt: backend 172 test (158 đạt, 14 skip), frontend 42 test và build thành công.
Không chỉnh trực tiếp hàng dữ liệu trên TiDB; người dùng cần khởi động lại backend để nạp code.


## Cọc QR và nút xác nhận demo lưu TiDB — 10/11/2026

Đã có **Booking của tôi → Đóng cọc bằng chuyển khoản → Xác nhận thanh toán cọc (demo)**.
QR hiển thị đúng người nhận, số tiền còn thiếu của người đang đăng nhập và nội dung riêng theo booking/người trả.
Nút demo gọi backend ghi Payment SUCCESS có mã/ghi chú DEMO, rồi đổi trạng thái booking/trận khi đủ cọc.
Đặt trực tiếp cọc 20%; hai đội mỗi đội 10%, chỉ đủ cả hai mới xác nhận trận. Không cần Admin duyệt cọc mới.
Đây là mô phỏng, không chứng minh chuyển khoản ngân hàng. Khoản DEMO không tính doanh thu API, không hoàn/thu tiền thật.
Giữ nguyên hạn 5 phút; không trộn với phiên thanh toán/giao dịch thật. Khi demo xong cần hủy booking nếu muốn nhả slot.

Backend bật `DEMO_PAYMENT_ENABLED=true`; frontend dev bật `VITE_DEMO_DEPOSIT=true` và `VITE_USE_MOCKS=false`.
Sau pull code phải cấu hình env local, khởi động lại backend/Vite. Mặc định env.example tắt demo; production phải tắt cả hai flag.
Chi tiết cách chạy, API, flag và giới hạn dữ liệu: [Demo cọc lưu DB](../docs/setup/DEMO_DEPOSIT.md).
