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
- 12 bảng dữ liệu đã được thiết kế

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

Frontend hiện mới có cấu trúc thư mục, chưa khởi tạo đầy đủ dự án Vite và chưa có `package.json`.

Sau khi frontend được khởi tạo, thành viên sẽ sử dụng:

```bash
cd frontend
npm install
npm run dev
```

Không chạy `npm install` trước khi có `package.json`.

## 7. Cấu hình TiDB Cloud

Mỗi thành viên sử dụng file `.env` riêng trong thư mục `backend`, dựa trên mẫu cấu hình của nhóm.

Thông tin cần cấu hình gồm:

- Database host
- Database port
- Database username
- Database password
- Database name
- SSL/TLS theo yêu cầu TiDB Cloud

Không đưa mật khẩu hoặc file `.env` lên GitHub.

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
- [ ] Khởi tạo Flask API
- [ ] Kết nối Flask với TiDB Cloud
- [ ] Khởi tạo React + Vite + TypeScript
- [ ] Phát triển các chức năng nghiệp vụ
- [ ] Kiểm thử và triển khai
