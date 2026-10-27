# Migration bổ sung V3

Bản này được soạn từ metadata TiDB `test` đã đọc ngày 27/10/2026 và hợp đồng API/Models của dự án. **Chưa chạy migration hoặc kiểm thử thực thi DDL trên TiDB.** Không dùng thay cho V1/V2 và không chạy lại các migration cũ.

## Nội dung

1. Thêm `match_posts.pitch_type` VARCHAR(16) và `end_time` DATETIME.
2. Thêm `bookings.payment_rule` VARCHAR(32) và `payer_plan` JSON.
3. Đổi default `matches.status` sang `SUGGESTED` cho dữ liệu tạo mới.
4. Giữ ENUM `notifications.notification_type`, thêm tám loại sự kiện vào cuối danh sách; không đổi ENUM sang VARCHAR.
5. Điền loại sân từ mặt sân đã liên kết; điền end_time từ booking khi giờ bắt đầu và sân khớp. Để NULL những hàng không đủ bằng chứng.

`UPDATE` backfill có thể làm `match_posts.updated_at` tự đổi theo định nghĩa bảng. Không sửa số tiền, lịch sử thanh toán hoặc trạng thái trận cũ. Không tạo bảng mới hoặc xóa view doanh thu theo sân. Chức năng doanh thu theo sân đã bỏ khỏi phạm vi ứng dụng; giữ view cũ không ảnh hưởng các báo cáo khác.

## Thứ tự áp dụng

- Sao lưu schema và dữ liệu liên quan; thử toàn bộ quy trình trên database thử nghiệm trước.
- Chọn đúng database. `003_contract_v3.sql` ghi rõ `USE test`; nếu dùng staging tên khác phải đổi sang tên staging trong bản sao của script trước khi chạy.
- Chạy `003_contract_v3_preflight.sql` chỉ đọc. Cần có đủ các bảng hậu V2; bảy thành viên ENUM cũ phải đúng thứ tự trong script. Nếu đã có cột V3, kiểm tra kiểu, null/default thay vì chỉ dựa vào IF NOT EXISTS.
- Dừng ghi từ app/worker trong lúc thay đổi và xác minh. Chạy từng bước trong `003_contract_v3.sql`, công cụ phải dừng khi có lỗi. Nếu lỗi, không chạy tiếp và không chạy lại toàn bộ theo thói quen; đối chiếu những bước đã thành công.
- Bước 4 gồm hai UPDATE trong transaction. Nếu một UPDATE lỗi trước COMMIT, ROLLBACK transaction đó; các ALTER trước đó vẫn đã áp dụng. Không gọi ROLLBACK với kỳ vọng hoàn tác DDL.
- Chạy `003_contract_v3_verify.sql`. Kiểm tra tất cả cột hiện diện, default SUGGESTED, ENUM có đủ 15 loại. Các hàng lịch sử thiếu lịch hoặc payer_plan cần rà soát, không nhất thiết phải về 0 ngay.
- Chỉ bật luồng tự ghép cho bài có loại sân và khoảng giờ hợp lệ. Triển khai backend hiểu cột mới rồi mới cho tạo booking theo hợp đồng mới.

Không cung cấp script DROP COLUMN rollback tự động vì có thể mất dữ liệu mới đã ghi. Khi cần quay về code cũ, tạm dừng ghi và giữ cột bổ sung; review tương thích thông báo mới, không thu hẹp ENUM khi đã có sự kiện mới.

## Quy tắc backend vẫn phải triển khai

- Giữ sân 300 giây bằng hold_expires_at do server tính; không dùng SQL trigger/event để thay nghiệp vụ.
- Cọc 20% tổng tiền sân; hai đội chia 50–50, mỗi đội ứng trước 10% tổng tiền sân.
- Đặt trực tiếp: payment_rule=DIRECT_BOOKING và một người trả 20%. Kèo hai đội: SPLIT_EQUAL và hai người trả.
- Ví dụ tiền sân 600.000 VND: payer_plan hai đội là `[{"user_id":2,"amount":"60000.00"},{"user_id":3,"amount":"60000.00"}]`. user_id phải được xác minh, tiền là chuỗi Decimal; tổng kế hoạch bằng deposit_amount; kế hoạch bất biến sau khi bắt đầu cọc.
- Slot 90 phút, 06:00–23:00, đặt trước tối đa 10 ngày; chặn overlap trong transaction khóa Pitch.
- Khi tạo bài mới có match_time: backend tính end_time=match_time+90 phút; không tự áp thời lượng mới lên dữ liệu cũ thiếu bằng chứng.
- Mỗi bên đồng ý chưa đồng nghĩa đã chốt trận. Đủ cọc trong hạn mới chuyển Booking và Match sang CONFIRMED.
- Người dùng tự hủy mất cọc của mình; Admin hủy do sự cố hoặc ghép không hoàn tất vì timeout thì hoàn các khoản đủ điều kiện. Không sửa lịch sử tiền bằng migration này.
- Token 60 phút rồi đăng nhập lại; không thêm refresh token.
- RANDOM_SQUAD dùng post_type VARCHAR hiện có và validator/backend mới; không cần sửa ENUM loại bài.
- Các trường mới nullable để giữ dữ liệu cũ; ứng dụng phải kiểm tra điều kiện chặt cho dữ liệu mới. Schema không thay thế kiểm tra payer_plan, thời gian và quyền truy cập.

## Đồng bộ tài liệu

Hợp đồng trước đây đề xuất chuyển notification_type sang VARCHAR(40). V3 chọn giữ ENUM và nối thêm giá trị để tránh chuyển kiểu. ORM phải ánh xạ ENUM mở rộng hoặc String với validator thống nhất; không giữ giả định cột đã là VARCHAR. Phụ lục schema hậu V2 vẫn là bản mô tả trước V3.

## Căn cứ cú pháp

- [TiDB ADD COLUMN](https://docs.pingcap.com/tidb/stable/sql-statement-add-column/)
- [TiDB ALTER TABLE](https://docs.pingcap.com/tidb/stable/sql-statement-alter-table/)
- [TiDB MODIFY COLUMN và giới hạn chuyển kiểu](https://docs.pingcap.com/tidb/stable/sql-statement-modify-column/)

Đã đối chiếu tài liệu cú pháp và cấu trúc hậu V2; chưa có bằng chứng thực thi migration trên staging. Các tệp kiểm tra chỉ đọc không tự ngăn người vận hành bỏ qua kết quả preflight.
