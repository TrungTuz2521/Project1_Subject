# Football Field Management

Hệ thống quản lý sân bóng đá, đặt sân trực tuyến, tìm đối thủ, ghép trận và thanh toán.

**Dự án:** Project1_Subject  
**Nhóm phát triển:** 5 thành viên  
**Trạng thái:** Đang thiết lập môi trường và phát triển hệ thống.

## 1. Công nghệ sử dụng

### Frontend
- React + Vite + TypeScript
- Tailwind CSS, shadcn/ui
- Lucide React
- TanStack Query, Zustand
- Recharts

### Backend
- Python + Flask
- Flask-SQLAlchemy, SQLAlchemy
- Flask-Migrate, Alembic
- PyMySQL
- JWT, bcrypt
- Flask-CORS

### Database
- TiDB Cloud (tương thích giao thức MySQL)
- Database `test` trên TiDB Serverless v8.5.3
- 15 bảng nghiệp vụ và 3 view đã được kiểm tra
- Database dùng chung đã cập nhật migration V3 ngày 27/10/2026

### Công nghệ dự kiến tích hợp
- Google OAuth
- Flask-SocketIO
- VNPay / MoMo
- Celery + Redis
- Firebase Admin SDK
- Pandas / OpenPyXL

Các công nghệ dự kiến tích hợp chưa được cài đặt đầy đủ trong `requirements.txt`.

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
git clone https://github.com/ntrung-duc/Project1_Subject.git
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

Khi backend đã được lập trình và cấu hình hoàn chỉnh, chạy:

```powershell
.\.venv\Scripts\python.exe run.py
```

**Lưu ý:** Hiện tại backend mới ở giai đoạn khởi tạo. Lệnh chạy server có thể chưa hiển thị gì nếu `run.py` chưa có nội dung.

## 6. Cài đặt Frontend

Đã có bộ React + Vite + TypeScript và màn hình mẫu **Đội bóng của tôi**. Dùng Node 24 LTS; trong thư mục dự án chạy:

```powershell
cd frontend
npm ci
npm run dev
```

Mở URL terminal hiển thị, thường là http://localhost:5173. Dev mặc định dùng dữ liệu mẫu, bấm **Đăng nhập bằng tài khoản mẫu** để xem danh sách và tạo đội. Không cần backend hoặc TiDB cho phần demo này.

```powershell
npm test
npm run build
```

Bộ dùng chung gồm `services/api.ts` xử lý JSON, Bearer token, lỗi, timeout/abort; `types/api.ts` cho DTO; `mocks` cho dữ liệu tổng hợp và handler; `features/matchmaking/TeamsPage.tsx` cho luồng tải danh sách/gửi form/báo lỗi.

Để gọi Flask thật, tạo `frontend/.env.local` theo `frontend/.env.example`, đặt `VITE_USE_MOCKS=false` và `VITE_API_BASE_URL` đúng backend rồi khởi động lại Vite. Token giữ trong bộ nhớ, hết hạn sau tối đa 60 phút hoặc reload thì cần đăng nhập lại; không refresh token. Form đăng nhập thật và các chức năng backend chưa được triển khai trong bộ mẫu.

Build production luôn tắt mock. Không đưa credential TiDB/gateway vào frontend hoặc VITE_*.

Xem [hướng dẫn frontend và cách chia việc](frontend/README.md) để thêm service, DTO, mock và xử lý lỗi theo mẫu.

## 7. Database TiDB và cấu hình kết nối

### Trạng thái database dùng chung

Database `test` trên TiDB Serverless v8.5.3 đã chạy migration V2 và **V3 ngày 27/10/2026**. Kết nối TLS và cấu trúc đã được kiểm tra; kết quả V3 do người quản lý dự án chạy và xác minh. Đây là trạng thái database, không có nghĩa Models hoặc API đã được lập trình.

**Thành viên pull code về chỉ cấu hình kết nối, không chạy lại schema gốc, V2 hoặc V3 trên database dùng chung; không dùng `db.create_all()` để tự thay schema.**

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

Các tệp trong repository:

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
| Lượt đá | 90 phút |
| Giờ mở cửa | 06:00–23:00 giờ Việt Nam |
| Đặt trước | Tối đa 10 ngày |
| Người dùng tự hủy sau cọc | Mất phần cọc của chính mình |
| Admin hủy do sự cố hoặc ghép thất bại vì hết hạn | Hoàn các khoản đủ điều kiện theo luồng đã thống nhất |
| Token đăng nhập | Hết hạn sau 60 phút từ lúc cấp, đăng nhập lại; không dùng refresh token |

Luồng ghép trận: đăng bài → AI đề xuất → hai bên xác nhận → giữ sân 5 phút → thu đủ cọc → xác nhận trận. Các quy tắc này cần được triển khai trong backend; migration không tự thực thi chúng.

Quyết toán sau trận tại quầy: Admin đối chiếu với hai đội và chọn đội thắng hoặc hòa đối với thể thức đội thua trả phần còn lại; backend tính tiền, frontend hiện khoản phải trả rồi QR cho đúng người trả. Hòa chia 50–50; không hoàn cọc đội thắng. Thu tiền mặt có nút Admin xác nhận riêng. Không có bước hai đội xác nhận trên ứng dụng hoặc chờ 30 phút. API/schema/frontend quyết toán chưa triển khai; V3 không chứa phần này, cần bổ sung riêng theo mục 15.1 của hợp đồng.

Đọc [hợp đồng API và Models](docs/api/API_MODELS_CONTRACT_PROJECT1.md) trước khi bắt đầu code; dùng chung tên cột, ENUM, endpoint và dữ liệu gửi/nhận theo tài liệu.

## 8. Quy trình làm việc nhóm

Mỗi thành viên tạo nhánh riêng trước khi lập trình:

```bash
git checkout -b feature/ten-chuc-nang
```

Sau khi hoàn thành:

```bash
git add .
git commit -m "Add feature"
git push -u origin feature/ten-chuc-nang
```

Tạo Pull Request trên GitHub để nhóm kiểm tra trước khi gộp vào nhánh chính.

## 9. Trạng thái triển khai

- [x] Tạo cấu trúc thư mục
- [x] Tạo `requirements.txt` cho backend
- [x] Cài đặt thư viện backend trên máy khởi tạo
- [x] Tạo cơ sở dữ liệu TiDB Cloud
- [x] Cập nhật database dùng chung đến V3 và kiểm tra cấu trúc
- [x] Thống nhất tài liệu API/Models và quy tắc nghiệp vụ
- [ ] Khởi tạo Flask API
- [ ] Kết nối Flask với TiDB Cloud
- [x] Khởi tạo React + Vite + TypeScript và bộ frontend mẫu dùng chung
- [x] Frontend đăng nhập/đăng ký/hồ sơ, khung điều hướng và xử lý token hết hạn (mock API)
- [ ] Tích hợp frontend tài khoản với Flask API thật sau khi backend hoàn thành
- [ ] Phát triển các chức năng nghiệp vụ
- [ ] Kiểm thử và triển khai
