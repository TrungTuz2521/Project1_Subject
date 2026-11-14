# Những phần còn cần hoàn thiện

Cập nhật ngày 10/11/2026 trên bản tích hợp `integration/team`, sau khi thêm đổi mật khẩu.
Đối chiếu các endpoint, worker, adapter, giao diện, workflow CI và trạng thái kiểm thử hiện có.
Đây là danh sách việc còn lại từ lượt kiểm tra mã/tài liệu, không phải chứng nhận đã kiểm thử mọi màn hình thực tế.

## Đã có và vừa được bổ sung

- Đăng ký/đăng nhập mật khẩu, Google Login, hồ sơ và JWT 60 phút.
- **Hồ sơ cá nhân → Đổi mật khẩu**: yêu cầu mật khẩu hiện tại, mật khẩu mới và nhập lại; bcrypt 8–72 byte UTF-8; đăng xuất phiên hiện tại sau thành công. Google-only không có mật khẩu web thì hiện hướng dẫn Google.
- Quân số từng buổi, khách không có tài khoản, tuyển người trực tiếp B đăng ký/A duyệt một lần, ghép đối thủ, thông báo và link email đến đề xuất.
- Worker quét bài 15 giây, email worker 10 giây; các job tiền/hết hạn chạy một lượt.
- Booking/hold, adapter VNPay, balance/QR chung và Admin xác nhận thu đủ đã có code; không suy ra đã thanh toán gateway thật thành công.

## Ưu tiên cho demo nghiệp vụ đầy đủ

| Việc còn lại | Trạng thái thực tế | Điều kiện hoàn thành |
| --- | --- | --- |
| VNPay sandbox end-to-end | Thiếu thông tin merchant đã được cấp/cấu hình, link đăng ký người dùng thử báo 404. Adapter có unit test nhưng chưa xác minh giao dịch thật ở sandbox. | Có TmnCode/HashSecret, Return URL và IPN HTTPS công khai; thử đủ cọc, lỗi/hủy, callback lặp, quá hạn và đối soát/hoàn nếu sử dụng. |
| Job hết hạn/đối soát tự chạy | `close-requests`, `expire-booking-holds`, `process-refunds`, `reconcile-payments` có CLI một lượt; chưa có scheduler chung được cấu hình để luôn chạy. Matchmaking/email worker không thay các job này. | Lập lịch và giám sát job; thử proposal/hold tự hết hạn và không hồi sinh khoản đã hết hạn. |
| Kiểm thử giao dịch đồng thời | 14 test đang skip khi thiếu DB kiểm thử riêng đủ điều kiện. SQLite không chứng minh được FOR UPDATE/TiDB cạnh tranh. | Database staging riêng; kiểm tra giành sân, nhiều đội dùng cùng người, callback đối đầu timeout/hủy và double-submit. Không dùng DB nhóm cho test tạo/xóa bảng. |
| Demo A/B sau thay đổi mới | Logic đã qua test tách biệt; cần người dùng thao tác lại trên trình duyệt chạy backend thật. | B đăng ký/A duyệt/B vào đội ngay, đúng quân số, đúng quyền, đúng email; hai đội vẫn cần hai xác nhận khi ghép đối thủ. |
| Google Login thực tế | Có code và test verifier giả; đã hướng dẫn sửa origin_mismatch, chưa có bằng chứng kiểm đủ các tình huống OAuth thật. | Thử tài khoản Google mới, đăng nhập lại, liên kết email đã có, tài khoản khóa và origin triển khai. |

## Tài khoản và thành viên chưa có

- **Quên mật khẩu/đặt lại bằng email**: chưa có endpoint, token hết hạn dùng một lần hoặc màn hình reset. Đổi mật khẩu hiện tại cần biết mật khẩu cũ.
- **Thu hồi JWT ở các thiết bị khác**: chưa có token version/denylist/revocation. Sau đổi mật khẩu, UI đăng xuất phiên hiện tại; JWT đã cấp ở nơi khác vẫn có thể dùng đến hết hạn 60 phút từ lúc cấp. Không tuyên bố đã đăng xuất toàn bộ thiết bị.
- **Tạo mật khẩu web cho tài khoản Google-only**: chưa có luồng xác minh Google lại để đặt mật khẩu đầu tiên. Hiện tiếp tục dùng Google Login.
- **Chuyển đội trưởng**: chưa có endpoint/UI chuyển quyền. Captain muốn rời đội vẫn bị chặn thay vì tự bỏ quyền.
- **Mời thành viên trực tiếp bằng email/link**: chưa có; hiện tham gia qua bài tuyển, hoặc khai báo khách ngoài ứng dụng.

## Vận hành và độ tin cậy

- **Email retry có kiểm soát**: bản hiện tại dùng trạng thái có sẵn và không tự retry FAILED. FAILED có thể gồm gửi lỗi hoặc kết quả chưa rõ sau crash. Muốn vận hành lớn cần outbox có lease/attempt/backoff, theo dõi lỗi và cơ chế gửi lại có kiểm soát. SMTP SENT không đảm bảo inbox.
- **Hoàn tiền nhiều worker/audit**: process-refunds hiện chỉ nên chạy một tiến trình; chưa có lease/outbox đa worker. Audit chưa có bảng sự kiện đầy đủ, một phần thông tin đang ghi note. Cần kiểm chứng query/refund với merchant thật.
- **Hosting và worker production**: chưa cấu hình hoàn chỉnh HTTPS, domain, origin/CORS, URL trong email, IPN, quản lý process tự khởi động lại và giám sát/backup. `localhost` chỉ là môi trường máy cá nhân.
- **CI backend**: repo hiện chỉ có workflow `frontend-checks.yml`, không chạy bộ Python test. Trigger push hiện chỉ nêu `feature/quang-team-matchmaking`; cần bổ sung backend CI và chính sách cho nhánh tích hợp/main.
- **Review, commit, push**: các thay đổi Auth/tuyển người/worker/cọc DEMO đã push lên `integration/team` trong commit `9e15d19`. Các thay đổi tiếp theo vẫn cần review trước khi gộp main. Không stage `.env`/credential hoặc `outputs/`; cần kiểm tra bản `.env.example` gốc đang có thay đổi riêng trước khi đưa lên Git.
- **Dữ liệu nhiều/trải nghiệm UI**: cần demo và rà soát phân trang/lỗi mạng ở các màn hình đang lấy trang đầu tối đa 100 mục; chưa có kiểm thử trình duyệt toàn bộ app.

## Phần mở rộng cần chốt phạm vi trước khi làm

MoMo/ZaloPay tự động, chat realtime, giao diện đánh giá/tố cáo, radar/Fair-play nâng cao, GPS/bản đồ hoặc lời mời trực tiếp không tự được tính là đã hoàn thành chỉ vì schema có bảng/cột. Nếu báo cáo môn học yêu cầu các mục này thì cần triển khai thêm hoặc sửa phạm vi báo cáo.

Đề xuất đổi thời điểm bắt đầu giữ sân sang khi người đầu tiên bấm thanh toán vẫn chưa triển khai. Quy tắc hiện tại: 5 phút từ lúc server tạo hold khi hai đội đồng ý. Doanh thu theo mặt sân đã bỏ khỏi phạm vi; không đưa lại vào danh sách bắt buộc.

## Kết quả kiểm tra lượt này

- Backend: **182 test, 168 đạt / 14 skip**.
- Frontend: **45 test đạt**, TypeScript/Vite build thành công.
- Đổi mật khẩu được thử trên SQLite tách biệt: mật khẩu cũ sai, xác nhận sai, độ dài UTF-8, mật khẩu mới trùng cũ, không có phiên/tài khoản khóa, Google-only, rate limit, đăng nhập bằng mật khẩu cũ/mới và không đổi nhầm người khác.
- Chưa đổi mật khẩu bất kỳ tài khoản thật nào hoặc chạy migration. Các điểm end-to-end chưa chứng minh được vẫn được liệt kê ở trên.

Cập nhật: đã có cọc QR và tự xác nhận DEMO lưu DB theo [hướng dẫn](../setup/DEMO_DEPOSIT.md); chưa phải thanh toán tự động thật. Nguyên mẫu Admin duyệt cọc mới đã bỏ theo yêu cầu.
