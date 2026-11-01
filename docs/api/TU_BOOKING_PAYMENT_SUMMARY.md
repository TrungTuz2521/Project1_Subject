
Cập nhật ngày 02/11/2026. Nhánh `Tu` trên GitHub, commit chính `f086bf8`, chưa merge.

## Tình trạng

Code đã xong theo hợp đồng API 1.8 và hợp đồng service 1.1, test đạt trên SQLite và MySQL local. **Chưa nên merge**, vì chưa chạy trên TiDB staging (mục 14 của hợp đồng yêu cầu) và chưa thử với VNPay thật.

## Đã làm

| Nhóm | Nội dung |
| --- | --- |
| Sân và lịch | Thông tin cụm sân, danh sách và lọc sân, lịch trống theo ngày, lưới 90 phút từ 06:00, đặt trước tối đa 10 ngày |
| Giữ sân | Giữ 300 giây, chống đặt trùng slot, hold hết hạn thì không còn chặn slot |
| Cọc | Cọc 20% qua VNPay (tạo URL đã ký, nhận IPN, đối soát), phiên cọc dùng lại khi gọi lặp; MoMo trả 422 vì chưa tích hợp |
| Hủy và hoàn tiền | Người chơi tự hủy thì mất cọc, Admin hủy thì hoàn cọc, hold hết hạn và tiền đến muộn được xử lý riêng; hoàn tiền mặt thủ công |
| Thu sau trận | Số dư, một QR VietQR chung, Admin xác nhận thu đủ, chống ghi trùng bằng mã xác nhận |
| Admin | Tạo và sửa sân, booking cho khách, đổi lịch, khóa bảo trì, ghi thu tại quầy, danh sách giao dịch |
| Báo cáo | Doanh thu theo ngày, tháng, năm; thống kê booking; xuất Excel |
| Worker | `expire-booking-holds`, `process-refunds`, `reconcile-payments` |
| Ghép với Đức | Đăng ký `booking_service`, `booking_reader`, `cancel_match`, nên luồng hai đội đồng ý → giữ sân → đủ cọc → xác nhận trận và luồng hủy trận đã chạy bằng service thật |

Tổng cộng 30 route (31 cặp method và đường dẫn). Không tạo bảng, cột hay migration mới.

## File chính

| Vị trí trong `backend/` | Nội dung |
| --- | --- |
| `app/routes/booking_api.py` | Toàn bộ route |
| `app/models/` | `field_complex`, `pitch`, `booking`, `payment` |
| `app/services/` | `booking_policy`, `booking_service`, `payment_service`, `booking_balance_service`, `revenue_service`, `gateway/vnpay` |
| `app/use_cases/` | `process_payment`, `cancel_booking`, `expire_hold`, `settle_booking`, `manage_booking` |
| `app/jobs/booking_jobs.py` | Các lệnh worker |
| `app/booking_module.py` | Gắn module vào app |
| `tests/` | `test_booking_payment.py`, `test_booking_concurrency.py`, `booking_fixtures.py` |
| `postman/` | Collection Postman và server thử `run_local.py` |

Ba file của Đức có sửa tối thiểu: `app/__init__.py`, `app/models/__init__.py`, `tests/test_backend.py`.

## Kết quả kiểm thử

| Kiểm tra | Kết quả |
| --- | --- |
| Unittest toàn bộ | 139 ca đạt: 25 của Đức, 100 nghiệp vụ trên SQLite, 14 đồng thời trên MySQL 8.4 local |
| Tắt khóa `FOR UPDATE` để thử độ nhạy | 7/14 ca đồng thời đỏ, tức các ca này phát hiện được lỗi thiếu khóa |
| Postman, chạy bằng newman trên SQLite | 100 request, 206 kiểm tra đều đạt |

Không đặt `TEST_DATABASE_URL` thì 14 ca đồng thời bị bỏ qua. Collection Postman chưa được mở thử trong ứng dụng Postman. Cách chạy nằm trong `backend/README.md`.

## Chưa kiểm chứng

- **TiDB:** chưa chạy `check-db` với các model mới và chưa test staging. Bảng test dùng `VARCHAR`, chưa so với `ENUM` thật.
- **VNPay thật:** mới kiểm tra chữ ký, URL và IPN bằng secret thử. API tra cứu và hoàn tiền chưa gọi thật. Cần tài khoản sandbox và URL HTTPS công khai cho IPN. Tài liệu VNPay thiếu một dấu `|` trong checksum phản hồi của querydr, cần xác nhận khi có sandbox.

## Giới hạn hiện tại

- `process-refunds` chỉ được chạy một tiến trình, vì chưa có outbox.
- Chưa có bảng audit: nguyên nhân, người thao tác và lý do hủy ghi tạm vào cột `note` (tối đa 255 ký tự, quá dài thì giữ phần mới nhất).
- Khoản hoàn thất bại không tự gửi lại, Admin phải đối soát rồi gọi lại route hoàn tiền.

## Việc còn lại

| Người | Việc |
| --- | --- |
| Tú | Test TiDB staging và VNPay sandbox trước khi merge |
| Đức | Review 3 file đã sửa; xem việc `reschedule_booking` cập nhật giờ trực tiếp trên `Match`/`MatchPost` có cần chuyển sang `match_service` không |
| Huy | `frontend/src/services/huyApi.ts` còn gọi `/settlement*` đã bỏ (404), cần đổi sang `balance` và `confirm-paid`; bản demo dùng bước 30 phút trong khi backend chỉ nhận lưới 90 phút |

Các hành vi tự chốt khi hợp đồng chưa nói rõ được liệt kê trong `docs/api/BACKEND_IMPLEMENTATION_STATUS.md` để nhóm xem lại.
