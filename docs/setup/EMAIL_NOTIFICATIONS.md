# Thông báo email bằng Gmail SMTP

## Cấu hình

Backend gửi bằng một tài khoản Gmail của dự án; Google login của người chơi không cấp quyền gửi thư.
Bật xác minh 2 bước, tạo App Password ở https://myaccount.google.com/apppasswords.
Lưu riêng trong `backend/.env`, không commit và không đưa vào frontend:

```dotenv
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<gmail-gui-thong-bao>
SMTP_PASSWORD=<app-password-16-ky-tu>
PUBLIC_WEB_URL=http://localhost:5173
```

Khởi động lại backend sau khi đổi env. SMTP luôn dùng STARTTLS và xác minh certificate.
PUBLIC_WEB_URL là địa chỉ frontend dùng trong email; khi deploy phải đổi thành origin HTTPS công khai.
Địa chỉ localhost chỉ mở được app trên máy người bấm, phù hợp demo cùng máy.
App Password có thể bị Google thu hồi khi thay mật khẩu chính. Không dùng mật khẩu Gmail thông thường.
Gmail có giới hạn gửi; phù hợp demo ít người, không phải dịch vụ gửi email hàng loạt.

## Kiểm tra và chạy

Từ thư mục `backend`, kiểm tra kết nối và đăng nhập SMTP, **không gửi thư**:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app check-email
```

Mở terminal thứ ba, ngoài terminal backend và frontend, để chạy email worker:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app email-worker
```

Worker kiểm tra hàng đợi mỗi 10 giây, Ctrl+C để dừng. Khi deploy cần service/scheduler duy trì worker.
Chạy một batch nếu cần: `python -m flask --app app:create_app send-pending-emails --limit 50` (dùng Python của venv).
Không cần chạy migration: đã kiểm tra schema TiDB có EMAIL và PENDING/SENT/FAILED.
Không phát lại toàn bộ thông báo cũ; chỉ sự kiện mới sau khi EMAIL_ENABLED=true mới có EMAIL row.

## Sự kiện và giao dịch

Email gồm đề xuất/phản hồi ghép, ghép thành viên, giữ sân, nhận cọc, xác nhận/hủy/hết hạn booking hoặc trận,
và xử lý/hoàn tiền thành công/thất bại nếu luồng hiện có phát sinh notification tương ứng.
Không gửi email POST_EXPIRED để giảm thư ít quan trọng.
notify ghi IN_APP/SENT và EMAIL/PENDING trong cùng transaction; rollback thì cả hai bị bỏ.
API danh sách thông báo chỉ đọc IN_APP nên không hiện trùng. Không gửi SMTP trong transaction đặt sân.
Worker lấy email hiện tại của user ACTIVE; bỏ qua địa chỉ demo .test/.invalid và lời mời/hold đã hết hạn.

Vì schema hiện có chỉ có PENDING/SENT/FAILED, worker claim bằng cập nhật nguyên tử PENDING→FAILED và commit
trước SMTP; chỉ chuyển SENT/sent_at sau khi SMTP chấp nhận. Worker khác không claim lại hàng đó.
FAILED có thể là thất bại, đang xử lý, hoặc kết quả chưa rõ sau crash. Không tự retry FAILED:
nếu SMTP nhận rồi nhưng kết nối bị đứt, gửi lại mù có thể gây trùng email.
Đây là giới hạn bản demo không thêm migration; triển khai lớn cần outbox riêng với lease, attempts và backoff.
SENT chỉ là SMTP đã chấp nhận, không chứng minh đã vào inbox; người nhận nên kiểm tra Spam.
Log chỉ ghi notification ID và loại lỗi, không in mật khẩu/nội dung thư/địa chỉ người nhận.

Thông báo trong app là kênh chính cho hạn đóng cọc 5 phút. Email không đổi deadline hoặc xác nhận thanh toán.
Mở link email khi chưa có session sẽ yêu cầu đăng nhập lại theo quy tắc JWT 60 phút hiện tại.

## Demo

1. Cấu hình Gmail + `check-email` thành công.
2. Khởi động backend và worker.
3. Dùng người chơi có email thật tạo hai bài phù hợp; chạy scan-matchmaking để sinh đề xuất mới.
4. Người chơi nhận thông báo trên app và email đề xuất; email mở app để xem trạng thái mới nhất.
5. Hai bên chấp nhận → nhận email giữ sân; đủ cọc → nhận xác nhận tương ứng.
6. Nếu SMTP lỗi, thông báo trong app và dữ liệu đặt sân vẫn được lưu; EMAIL row là FAILED, không báo SENT giả.

Unit tests chỉ dùng isolated SQLite và SMTP giả. `check-email` xác minh tài khoản thật nhưng không gửi email.

Nguồn chính thức:
- https://support.google.com/accounts/answer/185833
- https://support.google.com/mail/answer/22839


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
