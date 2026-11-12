# Football Field Management

Hệ thống quản lý sân bóng đá, đặt sân trực tuyến, tìm đối thủ, ghép trận và thanh toán.

**Dự án:** Project1_Subject  
**Nhóm phát triển:** 5 thành viên  
**Trạng thái:** Đã tích hợp backend và frontend trên nhánh `integration/team`; đang kiểm thử luồng thực tế.
**Cập nhật:** 10/11/2026 — bổ sung Google Login và thông báo email Gmail.

## 1. Công nghệ sử dụng

### Frontend
- React + Vite + TypeScript
- CSS của các phân hệ, React hooks và session trong bộ nhớ
- Thư viện `qrcode` hiển thị QR từ payload backend

### Backend
- Python + Flask
- Flask-SQLAlchemy, SQLAlchemy
- Flask-Migrate, Alembic
- PyMySQL
- JWT, bcrypt
- Flask-CORS
- Google Identity Services + `google-auth` xác minh ID token
- Gmail SMTP qua STARTTLS, hàng đợi email và worker riêng
- OpenPyXL cho xuất dữ liệu
- Adapter VNPay sandbox cho cọc; cần cấu hình merchant để thử gateway thật

### Database
- TiDB Cloud (tương thích giao thức MySQL)
- Database `test` trên TiDB Serverless v8.5.3
- 15 bảng nghiệp vụ và 3 view đã được kiểm tra
- Database dùng chung đã cập nhật V3 ngày 27/10/2026 và 004 ngày 06/11/2026
- Google Login và email dùng cột/kênh sẵn có; không cần migration mới

## 2. Cấu trúc dự án

```text
Project1_Subject/
├── .github/             # GitHub Actions
├── backend/
│   ├── app/
│   │   ├── config/
│   │   ├── constants/
│   │   ├── controllers/
│   │   ├── middleware/
│   │   ├── models/
│   │   ├── routes/
│   │   ├── services/
│   │   └── utils/
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── public/
│   └── src/
│       ├── assets/
│       ├── components/
│       ├── features/
│       ├── hooks/
│       ├── lib/
│       ├── pages/
│       ├── routes/
│       ├── services/
│       ├── stores/
│       ├── styles/
│       └── types/
├── database/
│   ├── schema/
│   ├── seeds/
│   └── queries/
├── docs/
├── .env.example
├── .gitignore
└── README.md
```

## 3. Yêu cầu môi trường

Các thành viên cần cài đặt:

- Git
- Visual Studio Code
- Python (máy khởi tạo dự án đang sử dụng Python 3.14.6)
- Node.js LTS và npm
- Quyền truy cập TiDB Cloud khi làm việc với database

## 4. Tải dự án

Mở Terminal:

```bash
git clone --branch integration/team https://github.com/TrungTuz2521/Project1_Subject.git
cd Project1_Subject
```

## 5. Cài đặt Backend

Mở Terminal tại thư mục dự án:

```powershell
cd backend
python -m venv .venv
```

Trên Windows PowerShell, cài đặt thư viện bằng Python trong môi trường ảo:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Kiểm tra:

```powershell
.\.venv\Scripts\python.exe -m pip check
```

Tạo `backend/.env` từ `backend/.env.example` **nếu chưa có**, rồi điền TiDB và `JWT_SECRET_KEY` riêng theo mục 7. Không ghi đè `.env` đã cấu hình. Chạy backend bằng môi trường ảo:

```powershell
.\.venv\Scripts\python.exe run.py
```

Kiểm tra server tại [health API](http://127.0.0.1:5000/api/v1/health), trả `data.status = "ok"`. Địa chỉ gốc `/` không có route, có thể trả 404 dù backend vẫn hoạt động. Health chỉ kiểm tra server; dùng `check-db` trong [hướng dẫn backend](backend/README.md) để kiểm tra kết nối và cột database.

## 6. Cài đặt Frontend

Frontend đã nối tài khoản, đội bóng/ghép trận, sân/booking và trang Admin với backend. Dùng Node 24 LTS; mở terminal thứ hai từ thư mục dự án:

```powershell
cd frontend
npm ci
npm run dev
```

Để test tích hợp, tạo `frontend/.env.local` (file `.env.example` chỉ là mẫu, Vite không tự dùng giá trị trong file đó):

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:5000/api/v1
VITE_USE_MOCKS=false
VITE_GOOGLE_CLIENT_ID=<Google OAuth Web Client ID dùng chung với backend>
```

Khởi động lại Vite sau khi sửa env. Mở [http://localhost:5173](http://localhost:5173) khi dùng Google Login, khớp Authorized JavaScript origins đã đăng ký. Nếu cần, chạy `npm run dev -- --host localhost`.

Chỉ dùng mock để dựng giao diện: đặt `VITE_USE_MOCKS=true`, đăng nhập bằng tài khoản mẫu. Mock không gửi email, không đăng nhập Google và không chứng minh luồng giữ sân/thanh toán thật.

```powershell
npm test
npm run build
```

Bộ dùng chung gồm `services/api.ts` xử lý JSON, Bearer token, lỗi, timeout/abort; `types/api.ts` cho DTO; `mocks` cho dữ liệu tổng hợp và handler; `features/matchmaking/TeamsPage.tsx` cho luồng tải danh sách/gửi form/báo lỗi.

Để gọi Flask thật, tạo `frontend/.env.local` theo `frontend/.env.example`, đặt `VITE_USE_MOCKS=false` và `VITE_API_BASE_URL` đúng backend rồi khởi động lại Vite. Token giữ trong bộ nhớ, hết hạn sau tối đa 60 phút hoặc reload thì cần đăng nhập lại; không refresh token. Auth và backend nghiệp vụ đã được tích hợp trên nhánh `integration/team`; xem [trạng thái triển khai và kiểm thử](docs/api/BACKEND_IMPLEMENTATION_STATUS.md) cho phạm vi đã xác minh.

Build production luôn tắt mock. Không đưa credential TiDB/gateway vào frontend hoặc VITE_*.

Xem [hướng dẫn frontend và cách chia việc](frontend/README.md) để thêm service, DTO, mock và xử lý lỗi theo mẫu.

### Google Login

Tạo OAuth Client loại **Web application** trên Google Auth Platform. Authorized JavaScript origins local:

```text
http://localhost
http://localhost:5173
```

Đặt `GOOGLE_CLIENT_ID` trong `backend/.env` và cùng giá trị ở `VITE_GOOGLE_CLIENT_ID` trong `frontend/.env.local`. Đây là Client ID công khai; luồng popup này không cần Client Secret. Không sao chép backend env sang frontend.

- Tài khoản Google mới tạo PLAYER; Google ID đã liên kết đăng nhập đúng tài khoản cũ.
- Nếu email đã có tài khoản web, nhập mật khẩu web hiện tại rồi bấm Google lại để liên kết lần đầu.
- Tài khoản không ACTIVE không được đăng nhập. JWT ứng dụng vẫn hạn 60 phút, không refresh token; reload cần đăng nhập lại.
- Đã kiểm thử bằng Google verifier giả; cần chọn tài khoản Google thật trong trình duyệt để xác minh end-to-end.

Xem [cấu hình và kịch bản thử Google Login](docs/setup/GOOGLE_LOGIN.md).

### Email thông báo qua Gmail

Gmail gửi thông báo là tài khoản cấu hình ở backend; đăng nhập Google của người chơi không tự cấp quyền gửi thư. Bật xác minh 2 bước cho Gmail gửi, tạo **mật khẩu ứng dụng**, rồi cấu hình riêng trong `backend/.env`:

```dotenv
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<gmail-gui-thong-bao>
SMTP_PASSWORD=<mat-khau-ung-dung>
PUBLIC_WEB_URL=http://localhost:5173
```

Không dùng mật khẩu Gmail thông thường. Không lưu mật khẩu SMTP trong README, `.env.example` hoặc `VITE_*`. Thành viên chưa cần test email có thể giữ `EMAIL_ENABLED=false` và vẫn dùng thông báo trên web. Khi deploy, đổi `PUBLIC_WEB_URL` thành origin HTTPS công khai; link localhost chỉ phù hợp demo trên máy đang chạy app.

Sau khi sửa env, khởi động lại backend. Từ thư mục `backend`, kiểm tra SMTP **không gửi thư**:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app check-email
```

Mở **terminal thứ ba**, tại `backend`, giữ worker chạy để gửi email cho sự kiện mới:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app email-worker
```

Worker kiểm tra mỗi 10 giây; Ctrl+C để dừng. Chỉ chạy Flask không tự chạy email worker. Khi deploy, cần service/scheduler duy trì worker.

Email gồm đề xuất/phản hồi ghép, ghép thành viên, giữ sân, nhận cọc, xác nhận/hủy/hết hạn và hoàn tiền khi luồng phát sinh thông báo tương ứng. Người nhận cần email thật; bỏ qua tài khoản mẫu `.test`/`.invalid`. Không gửi lại toàn bộ thông báo lịch sử.

Hàng đợi EMAIL được ghi cùng transaction với IN_APP; SMTP chạy sau commit, không giữ khóa đặt sân. `SENT` chỉ nghĩa là SMTP đã chấp nhận, không bảo đảm vào inbox. Với schema hiện có, worker reserve bằng chuyển `PENDING` sang `FAILED` trước khi gửi, rồi sang `SENT` khi được chấp nhận; `FAILED` có thể là lỗi/đang xử lý/kết quả chưa rõ sau crash và không tự retry. Xem [giới hạn và cách kiểm thử email](docs/setup/EMAIL_NOTIFICATIONS.md).

Thông báo trên web vẫn là kênh chính cho hạn đóng cọc **5 phút từ lúc server tạo hold**; mở email hoặc bấm chuyển trang thanh toán không gia hạn. Email không tự xác nhận thanh toán.

## 7. Database TiDB và cấu hình kết nối

### Trạng thái database dùng chung

Database `test` trên TiDB Serverless v8.5.3 đã chạy migration V2, **V3 ngày 27/10/2026** và **004 ngày 06/11/2026**. Migration 004 thêm `match_posts.attendance_plan JSON NULL` để lưu quân số riêng cho từng buổi đá; giữ nguyên các dòng dữ liệu cũ. Kết nối TLS và cấu trúc đã được kiểm tra; kết quả V3 do người quản lý dự án chạy và xác minh. Đây là trạng thái database, không có nghĩa Models hoặc API đã được lập trình.

**Thành viên pull code về chỉ cấu hình kết nối, không chạy lại schema gốc, V2, V3 hoặc 004 trên database dùng chung đã cập nhật; không dùng `db.create_all()` để tự thay schema.**

### Các bảng hiện có

| Nhóm | Bảng |
| --- | --- |
| Tài khoản | `users` |
| Sân và đặt sân | `field_complexes`, `pitches`, `bookings` |
| Thanh toán và hoàn tiền | `payments` |
| Đội bóng | `teams`, `team_members` |
| Bài đăng và đăng ký | `match_posts`, `match_participants` |
| Ghép đội và trận đấu | `match_proposals`, `proposal_confirmations`, `matches` |
| Thông báo | `notifications` |
| Dữ liệu đánh giá và tố cáo được giữ lại | `ratings`, `reports` |

Tổng cộng **15 bảng**. Ngoài ra có 3 view:

- `v_admin_revenue_daily`: tổng hợp tiền thực thu ròng theo ngày.
- `v_admin_revenue_monthly`: tổng hợp tiền thực thu ròng theo tháng.
- `v_admin_revenue_by_pitch`: view cũ được giữ nguyên; chức năng doanh thu theo mặt sân đã bỏ khỏi phạm vi ứng dụng và không dùng view này.

Báo cáo doanh thu của ứng dụng tổng hợp toàn cụm theo ngày/tháng/năm hoặc khoảng thời gian, dựa trên tiền đã thu trừ tiền đã hoàn thành công.

### Nội dung V3 đã áp dụng

- Thêm `match_posts.pitch_type` và `match_posts.end_time`.
- Thêm `bookings.payment_rule` và `bookings.payer_plan`.
- Đổi mặc định `matches.status` sang `SUGGESTED` cho trận tạo mới; giữ nguyên trạng thái trận cũ.
- Mở rộng `notifications.notification_type` thành 15 loại, giữ nguyên ENUM.
- Bổ sung thông tin cho bài cũ khi có sân/booking liên kết đủ căn cứ; không tự đoán kế hoạch cọc của booking lịch sử.

Kết quả kiểm tra sau V3: còn 1 bài đăng thiếu thông tin phục vụ ghép và 1 booking lịch sử chưa có kế hoạch cọc. Backend cần nhận diện dữ liệu này; không tự đưa bài thiếu thông tin vào AI ghép hoặc thu thêm tiền lịch sử.

### Migration 004: quân số từng buổi — đã áp dụng

- Một đội có thể có 3 tài khoản nhưng buổi đá đủ 7 người: 3 tài khoản tham gia + 4 người ngoài ứng dụng.
- Đội trưởng khai báo quân số trong bài đăng, không phải thay danh sách đội mỗi ngày. Nhận thêm người chỉ được cộng sau đủ hai xác nhận.
- Đội thường tuyển đủ có nút **Tạo bài tìm đối thủ với quân số này**; AI_RANDOM giữ luồng tự tạo bài tìm đối thủ khi đủ người.
- [Quy tắc, API và hướng dẫn demo](docs/api/SESSION_ATTENDANCE_GUIDE.md).
- [SQL 004](database/schema/004_session_attendance.sql) và [trạng thái/hướng dẫn migration](database/schema/004_session_attendance_README.md). File SQL phục vụ môi trường khác chưa cập nhật; thành viên dùng TiDB nhóm không chạy lại.

Các tệp V3 trong repository:

- [Kiểm tra trước V3](database/schema/003_contract_v3_preflight.sql)
- [Migration V3](database/schema/003_contract_v3.sql)
- [Kiểm tra sau V3](database/schema/003_contract_v3_verify.sql)
- [Hướng dẫn và giới hạn của V3](database/schema/003_contract_v3_README.md)

Các tệp được lưu để theo dõi thay đổi và dựng môi trường mới có kiểm soát. File V3 là migration bổ sung sau V2, không phải schema đầy đủ để import vào database rỗng. Với database mới hoặc môi trường thử nghiệm, cần schema nền/V2 và kế hoạch migration riêng. Không dùng các tệp này để chạy lại trên database nhóm đã cập nhật.

### Cấu hình cho mỗi thành viên

Tạo `backend/.env` trên máy riêng, lấy thông tin kết nối được cấp qua kênh riêng:

```dotenv
TIDB_HOST=<host trong TiDB Connect>
TIDB_PORT=4000
TIDB_DATABASE=test
TIDB_USERNAME=<username được cấp>
TIDB_PASSWORD=<password được cấp>
SECRET_KEY=<secret riêng của môi trường>
JWT_SECRET_KEY=<secret riêng của môi trường>
```

Backend phải dùng TLS, xác minh chứng chỉ và hostname; nếu môi trường cần CA riêng thì cấu hình đường dẫn CA thích hợp. Lưu datetime theo UTC và hiển thị giờ Việt Nam. Đọc `.env` khi khởi động ứng dụng; việc tạo file chưa tự kết nối Flask với TiDB.

Không đưa `.env`, mật khẩu, JWT secret hoặc chuỗi kết nối có mật khẩu lên GitHub. `.env.example` chỉ chứa mẫu, không chứa credential thật.

### Quy tắc nghiệp vụ đã chốt

| Nội dung | Quy định |
| --- | --- |
| Giữ sân | 5 phút từ lúc server tạo hold |
| Cọc | 20% tổng tiền sân |
| Hai đội chia tiền | Chọn 50–50 hoặc đội thua trả toàn bộ phần còn thiếu của cả hai đội, không hoàn cọc; hòa tính như 50–50. Mỗi đội đều cọc 10% tổng tiền sân |
| Quân số buổi đá | Tài khoản được chọn tham gia + người ngoài ứng dụng; đủ 5/7 theo loại sân, độc lập danh sách đội lâu dài |
| Lượt đá | 90 phút |
| Giờ mở cửa | 06:00–23:00 giờ Việt Nam |
| Đặt trước | Tối đa 10 ngày |
| Người dùng tự hủy sau cọc | Mất phần cọc của chính mình |
| Admin hủy do sự cố hoặc ghép thất bại vì hết hạn | Hoàn các khoản đủ điều kiện theo luồng đã thống nhất |
| Token đăng nhập | Hết hạn sau 60 phút từ lúc cấp, đăng nhập lại; không dùng refresh token |

Luồng ghép trận: đăng bài → AI đề xuất → hai bên xác nhận → giữ sân 5 phút → thu đủ cọc → xác nhận trận. Các quy tắc này cần được triển khai trong backend; migration không tự thực thi chúng.

Thu phần còn lại sau trận (chốt 29/10/2026): Admin xem tổng tiền, cọc thực thu và tổng còn thiếu; hiển thị một QR chuyển khoản chung theo booking. Hai đội tự chia tiền theo thể thức đã chọn, có thể chuyển nhiều lần hoặc trả trực tiếp. Admin kiểm tra thực nhận và bấm Xác nhận đã thu đủ; backend ghi Payment theo từng khoản/phương thức, chống trùng và lưu Admin/thời gian. Không chọn đội thắng/hòa, không chia nghĩa vụ từng đội, không cần bảng booking_settlements hay cột kết quả. Cọc trước trận giữ nguyên. Hợp đồng API mới tại mục 15.1; Tú triển khai balance/xác nhận thu, Huy dựng UI; backend balance/xác nhận thu của Tú và giao diện Huy đã được nối trên `integration/team`; kiểm thử ghi thu tiền phải dùng database thử nghiệm riêng.

Đọc [hợp đồng API và Models](docs/api/API_MODELS_CONTRACT_PROJECT1.md) trước khi bắt đầu code; dùng chung tên cột, ENUM, endpoint và dữ liệu gửi/nhận theo tài liệu.

## 8. Quy trình làm việc nhóm

Mỗi thành viên tạo nhánh riêng trước khi lập trình:

```bash
git checkout -b feature/ten-chuc-nang
```

Sau khi hoàn thành:

```bash
git add README.md
git commit -m "Add feature"
git push -u origin feature/ten-chuc-nang
```

Kiểm tra `git status` và `git diff --cached` trước khi commit; không stage file chứa credential hoặc thư mục kết quả riêng. Tạo Pull Request vào `integration/team` để kiểm thử chung, rồi mới đề nghị gộp vào `main`.

## 9. Trạng thái triển khai và kiểm thử

- [x] Flask API và kết nối TiDB/TLS; schema nhóm đến V3 + 004.
- [x] Frontend/backend tài khoản, hồ sơ và phiên JWT 60 phút.
- [x] Đội bóng, quân số theo buổi, bài đăng, đề xuất/xác nhận, thông báo và lịch.
- [x] Tích hợp booking/cọc và giao diện sân/Admin; balance/QR chung/xác nhận thu đủ sau trận.
- [x] Google Login: đã viết code, cấu hình local và kiểm thử tách biệt.
- [x] Email Gmail: hàng đợi, SMTP và worker; kết nối/xác thực SMTP local đã thành công.
- [ ] Hoàn tất demo đăng nhập Google bằng tài khoản thật và kiểm tra email vào hộp thư người nhận.
- [ ] Kiểm thử gateway VNPay merchant thật ở sandbox và cạnh tranh DB trên môi trường thử riêng.
- [ ] Triển khai hosting, scheduler/worker và cấu hình production.

Kết quả ngày **10/11/2026**: backend chạy 182 test, **168 đạt và 14 bỏ qua** (kiểm thử đồng thời cần MySQL/TiDB thử nghiệm riêng); frontend **45 test đạt**, build thành công. Auth Google dùng verifier giả, email dùng SMTP giả trong unit test; `check-email` thực tế chỉ xác minh kết nối/đăng nhập Gmail và không gửi thư. Các kết quả này chưa thay thế demo end-to-end hoặc kiểm thử khóa TiDB.

### Tìm kèo: ghép tự động theo yêu cầu

Người chơi không xem bài của nhau. Họ gửi **yêu cầu** ở trang **Tìm kèo** (`#/matchmaking`), hệ thống tự ghép rồi báo qua email và thông báo trên web:

| Loại | Ai gửi | Ghép với |
|---|---|---|
| Tìm đối | Đội trưởng, chỉ nhập số người đi đá (đủ 5/7) | Một đội khác cùng loại sân, cùng ngày, khung giờ giao nhau, trình độ trong mức chấp nhận, cách chia tiền khớp (hoặc một bên "không yêu cầu") |
| Tìm thêm người | Người có lượt sân đã cọc | Người chơi đá ké phù hợp, thêm thẳng vào trận |
| Đá ké | Một người (đi cùng tối đa 2 bạn) | Trận đang thiếu người |

Quy tắc:
- Tìm đối gửi trước ngày đá ít nhất 2 ngày; tìm thêm người và đá ké chỉ cần còn hơn 1 ngày.
- Hệ thống dừng tìm 24 giờ trước giờ đá và báo "không tìm được".
- Tìm đối chọn **1 ngày** và một khung giờ (vd 17:00–21:00).
- Cặp phù hợp nhất được ghép trước (gần trình độ nhất, ít vắng mặt nhất).
- Ghép là chốt, không cần xác nhận lại. Chỉ **đội trưởng** nhận email và thông báo, đội trưởng tự báo cho thành viên.
- Đội đã đặt sân được ưu tiên ghép với đội chưa có sân, đá luôn trên sân đó và không cọc thêm.
- Hai đội cùng đã đặt sân (cùng giờ) chỉ được ghép sau khi đã chờ 6 giờ hoặc khi sắp hết hạn tìm. Khi đó hệ thống giữ lượt sân đặt sớm hơn, hủy lượt kia, và **chuyển tiền cọc** của lượt kia sang lượt được giữ (không hoàn).
- Hai đội đều chưa có sân: hệ thống tự giữ một sân trống, mỗi đội cọc một nửa trong 12 giờ. Quá hạn thì đội chưa cọc bị hủy yêu cầu, đội đã cọc được hoàn cọc và tìm tiếp.
- Hủy kèo đã ghép chỉ được khi còn hơn 24 giờ; sau đó phải gọi quầy.

**Phải chạy bộ lập lịch** thì việc ghép, đóng yêu cầu quá hạn, hết hạn giữ sân và gửi email mới diễn ra. Mở thêm một terminal tại thư mục `backend`:

```powershell
python -m flask --app app:create_app scheduler --with-matchmaking --with-email
```

Mỗi yêu cầu mới cũng được quét ngay khi gửi. Admin xem mọi yêu cầu và bấm "Quét ngay" ở trang **Kèo ghép**. Trước khi chạy code này trên TiDB phải chạy migration `database/schema/006_match_requests.sql` (chỉ thêm cột).


Thanh toán QR SePay: [cài đặt](docs/setup/SEPAY_QR.md), [đưa lên cloud](docs/setup/DEPLOY_CLOUD.md) (chạy migration `007_refund_account.sql`).

Danh sách việc còn lại, ưu tiên demo và giới hạn thực tế: [Những phần cần hoàn thiện](docs/api/REMAINING_WORK.md).


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


## Cọc QR và nút xác nhận demo lưu TiDB — 10/11/2026

Đã có **Booking của tôi → Đóng cọc bằng chuyển khoản → Xác nhận thanh toán cọc (demo)**.
QR hiển thị đúng người nhận, số tiền còn thiếu của người đang đăng nhập và nội dung riêng theo booking/người trả.
Nút demo gọi backend ghi Payment SUCCESS có mã/ghi chú DEMO, rồi đổi trạng thái booking/trận khi đủ cọc.
Đặt trực tiếp cọc 20%; hai đội mỗi đội 10%, chỉ đủ cả hai mới xác nhận trận. Không cần Admin duyệt cọc mới.
Đây là mô phỏng, không chứng minh chuyển khoản ngân hàng. Khoản DEMO không tính doanh thu API, không hoàn/thu tiền thật.
Giữ nguyên hạn 5 phút; không trộn với phiên thanh toán/giao dịch thật. Khi demo xong cần hủy booking nếu muốn nhả slot.

Backend bật `DEMO_PAYMENT_ENABLED=true`; frontend dev bật `VITE_DEMO_DEPOSIT=true` và `VITE_USE_MOCKS=false`.
Sau pull code phải cấu hình env local, khởi động lại backend/Vite. Mặc định env.example tắt demo; production phải tắt cả hai flag.
Chi tiết cách chạy, API, flag và giới hạn dữ liệu: [Demo cọc lưu DB](docs/setup/DEMO_DEPOSIT.md).
