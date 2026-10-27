# Hợp đồng API và Models Project1

Phiên bản 1.7 — ngày 27/10/2026. Dùng chung cho 5 thành viên khi lập trình Flask, React và TiDB. Đây là hợp đồng triển khai, không phải danh sách chức năng đã có trong mã nguồn.

## 1. Cơ sở và quyết định thống nhất

Đã đối chiếu báo cáo `bài tập lớn Project1(updated diagrams).docx`, schema gốc, migration TiDB V2 và khung `Project1_Subject-main.zip` do chủ dự án cung cấp. ZIP hiện chứa khung thư mục; các tệp Flask chính còn rỗng, frontend chưa có `package.json`, thư mục database chưa có SQL. Không suy ra database đang chạy thực tế chỉ từ ZIP hoặc hai tệp SQL.

Thứ tự áp dụng: yêu cầu trực tiếp của chủ dự án → quyết định nghiệp vụ trong tài liệu này → tên bảng/cột của schema sau migration. Điểm lệch được liệt kê tại mục 13; cần cập nhật migration và sơ đồ tương ứng trước khi tích hợp.

| Nội dung | Quyết định | Căn cứ |
| --- | --- | --- |
| Phạm vi | Một cụm sân, một tài khoản Admin được cấp sẵn | Báo cáo 2.1 |
| Giữ sân | **300 giây**, từ lúc backend tạo hold thành công | Chủ dự án và báo cáo 2.1.1 |
| Đăng bài | Không giữ sân, không thu cọc, trạng thái OPEN | Báo cáo 2.1.2 và SD06 |
| Chốt trận | Hai bên đồng ý, giữ sân, thu đủ các phần cọc bắt buộc rồi mới CONFIRMED | SD06 |
| Ghép thành viên | Đồng ý tham gia → cập nhật đội; không tự tạo trận hoặc tự thu cọc | SD05 |
| Tiền cọc | **20% tổng tiền sân** | Chủ dự án đã chốt |
| Điểm ghép | Từ 80 điểm trên thang 100 | Chủ dự án đồng ý đề xuất |
| Hạn phản hồi đề xuất | 15 phút, tối đa đến hạn bài đăng hoặc giờ đá | Chủ dự án đồng ý; độc lập hold 5 phút |
| Thời lượng một slot | **90 phút** | Chủ dự án đã chốt |
| Loại sân MVP | PITCH_5, PITCH_7; giữ PITCH_11 cho dữ liệu cũ | Báo cáo và schema |
| Chi phí hai đội | SPLIT_EQUAL (50–50) hoặc LOSER_PAYS_REMAINDER (đội thua trả toàn bộ phần còn thiếu, không hoàn cọc); hòa chia 50–50 | Chủ dự án đã chốt |

Chủ dự án đã chốt các thay đổi đến phiên bản 1.7: cọc 20%, hai thể thức 50–50 hoặc đội thua trả phần còn lại, hòa chia 50–50, đá 90 phút, mở 06:00–23:00, đặt trước tối đa 10 ngày, người dùng tự hủy sau khi cọc thì mất cọc; các đề xuất khác giữ theo lựa chọn đã đồng ý. Đăng nhập đã chốt: access token hết hạn sau 60 phút từ lúc cấp, hết hạn phải đăng nhập lại; không dùng refresh token. Hai thể thức chia tiền được chốt tại mục 15.1; không hoàn cọc chỉ vì một đội thắng. Google Login đang được trao đổi, chưa nằm trong phạm vi đã chốt. Không tự đổi endpoint hoặc tên trường khi điều chỉnh cấu hình.

## 2. Quy ước API

- Base URL: `/api/v1`; JSON dùng `snake_case`, ENUM viết hoa.
- JWT qua `Authorization: Bearer <access_token>`. Kiểm tra tài khoản ACTIVE ở API riêng tư; đăng ký luôn tạo PLAYER, không nhận role từ client.
- ID là số nguyên dương; tiền là chuỗi thập phân VND, ví dụ `"180000.00"`; backend dùng Decimal, không dùng float để tính tiền.
- Nhận và trả ISO 8601 có múi giờ; lưu DATETIME theo UTC. Frontend hiển thị Asia/Ho_Chi_Minh. Không nhận datetime thiếu offset.
- Với khoảng thời gian, dùng nửa mở `[start_time, end_time)`. Hai lịch chạm đầu/cuối không trùng nhau.
- POST tạo mới trả 201; đọc/cập nhật/hủy trả 200; DELETE nghiệp vụ dùng soft state và trả 200. Không xóa lịch sử booking/payment.
- Pagination: `page=1`, `page_size=20`, tối đa 100. Lọc không hợp lệ trả 422, không lặng lẽ bỏ qua.
- Trường không có quyền sửa như status, creator_id, tiền và điểm AI do server thiết lập. Request có trường bảo vệ trái phép trả 422.
- Access token có hạn cố định **60 phút từ lúc cấp** (expires_in=3600), hết hạn phải đăng nhập lại. Không tự gia hạn theo hoạt động, không dùng refresh token. API trả 401 TOKEN_EXPIRED khi token hết hạn; frontend xóa token và chuyển về đăng nhập, không đánh dấu hủy booking chỉ vì phiên đăng nhập hết hạn. Không giả định có thư viện Flask-JWT-Extended trong khung.

Response thành công:

```json
{"data":{"booking_id":21,"status":"PENDING_HOLD"},"meta":{"server_time":"2026-10-27T10:00:00Z"}}
```

Danh sách:

```json
{"data":[],"meta":{"page":1,"page_size":20,"total":0,"server_time":"2026-10-27T10:00:00Z"}}
```

Lỗi:

```json
{"error":{"code":"SLOT_UNAVAILABLE","message":"Khung giờ đã được đặt hoặc đang giữ chỗ.","fields":{}}}
```

| HTTP | code chính | Ý nghĩa |
| --- | --- | --- |
| 401 | UNAUTHORIZED, TOKEN_EXPIRED | Chưa đăng nhập hoặc token hết hạn |
| 403 | FORBIDDEN, ACCOUNT_DISABLED | Không đủ quyền hoặc tài khoản bị khóa |
| 404 | NOT_FOUND | Không tồn tại hoặc không được phép biết tài nguyên riêng tư |
| 409 | SLOT_UNAVAILABLE, HOLD_EXPIRED, ALREADY_RESPONDED, STATE_CONFLICT, DEPOSIT_ALREADY_PAID | Xung đột dữ liệu/trạng thái |
| 422 | VALIDATION_ERROR | Sai dữ liệu, ENUM, ngày giờ hoặc quy tắc |
| 429 | RATE_LIMITED | Vượt giới hạn thao tác |
| 503 | PAYMENT_PROVIDER_UNAVAILABLE | Chưa tạo được giao dịch với nhà cung cấp |

GET công khai chỉ trả tên hiển thị, loại sân, giá, thời gian và trạng thái cần thiết. Không trả password_hash, google_id, email hay số điện thoại của người khác. Thông tin liên hệ đối thủ chỉ mở cho các bên của trận CONFIRMED qua endpoint riêng.

## 3. Models và ranh giới dữ liệu

ORM ánh xạ đúng tên bảng/cột SQL. Tên Python PascalCase không đổi tên cột. Các cột thời gian `created_at`, `updated_at` chỉ có nếu thực sự hiện diện trong schema; xem bảng từ điển chi tiết ở phụ lục A.

| Model | Bảng | Khóa và thuộc tính nghiệp vụ chính | Chủ sở hữu |
| --- | --- | --- | --- |
| User | users | user_id, full_name, email, phone, password_hash, google_id, role, skill_level, status | Người 1 |
| FieldComplex | field_complexes | complex_id, name, phone, address | Người 4 |
| Pitch | pitches | pitch_id, complex_id, pitch_name, pitch_type, price_per_slot, status | Người 4 |
| Booking | bookings | booking_id, pitch_id, user_id, start_time, end_time, total_amount, deposit_amount, booking_type, status, hold_expires_at, note | Người 4 |
| Payment | payments | payment_id, user_id, booking_id, post_id, amount, payment_type, payment_method, transaction_code, refund_for_payment_id, recorded_by_admin_id, status, paid_at, note | Người 4 |
| Team | teams | team_id, team_name, created_by, creation_type, status | Người 2 |
| TeamMember | team_members | team_member_id, team_id, user_id, role, status, joined_at | Người 2 |
| MatchPost | match_posts | post_id, creator_id, team_id, pitch_id, booking_id, post_type, title, description, match_time, skill_level, payment_rule, required_players, current_players, required_deposit, expiry_time, status | Người 2 |
| MatchParticipant | match_participants | participant_id, post_id, user_id, status, joined_at, updated_at | Người 2 |
| MatchProposal | match_proposals | proposal_id, source_post_id, target_post_id, candidate_user_id, proposal_type, compatibility_score, status, expires_at, confirmed_at | Người 3 |
| ProposalConfirmation | proposal_confirmations | confirmation_id, proposal_id, user_id, decision, responded_at | Người 3 |
| Match | matches | match_id, post_id, opponent_post_id, booking_id, proposal_id, match_time, compatibility_score, status, confirmed_at | Người 3 |
| Notification | notifications | notification_id, user_id, proposal_id, match_id, notification_type, title, content, delivery_channel, delivery_status, is_read, sent_at, read_at | Người 3 |

`Admin` là vai trò của User; không tạo bảng admins. MatchmakingService, BookingService, PaymentService, NotificationService, RevenueService là lớp xử lý, không phải bảng. Người 5 import lại ORM đã có, không tạo Booking/Payment phiên bản khác.

Quan hệ: FieldComplex có nhiều Pitch; Pitch có nhiều Booking; Booking có nhiều Payment; User có nhiều TeamMember và MatchPost; Team có nhiều TeamMember; MatchPost có nhiều MatchParticipant; MatchProposal có hai ProposalConfirmation; một proposal OPPONENT tối đa sinh một Match nhờ unique(proposal_id). Match dùng post_id và opponent_post_id để trỏ hai bài, không dùng tên team_id thay cho cột hiện có.

Unique có sẵn: users.email/phone/google_id; team_members(team_id,user_id); match_participants(post_id,user_id); proposal_confirmations(proposal_id,user_id); matches.proposal_id; payments.transaction_code. Tham gia lại đội thì cập nhật hàng cũ, không chèn trùng khóa.

### 3.1 ENUM dùng chung

| Nhóm | Giá trị |
| --- | --- |
| User.role | PLAYER, ADMIN |
| User.status | ACTIVE, BANNED, INACTIVE |
| skill_level | BEGINNER, AMATEUR, INTERMEDIATE, SEMI_PRO, PRO |
| Pitch.status | ACTIVE, MAINTENANCE, INACTIVE |
| Pitch.pitch_type | PITCH_5, PITCH_7, PITCH_11; API mới MVP chỉ 5/7 |
| Booking.booking_type | ONLINE, MANUAL_ADMIN, MAINTENANCE_LOCK |
| Booking.status | PENDING_HOLD, CONFIRMED, CANCELLED, EXPIRED, MAINTENANCE |
| Team.creation_type | USER_CREATED, AI_RANDOM |
| Team.status | ACTIVE, INACTIVE |
| TeamMember.role/status | CAPTAIN, MEMBER / ACTIVE, LEFT, REMOVED |
| MatchPost.post_type | FIND_OPPONENT, RECRUIT_MEMBERS, LOOK_FOR_TEAM, RANDOM_SQUAD |
| MatchPost.status | OPEN, LOCKED, MATCHED, EXPIRED, CANCELLED; PENDING_DEPOSIT chỉ dữ liệu cũ |
| MatchParticipant.status | PENDING, ACCEPTED, REJECTED, CANCELLED |
| MatchProposal.proposal_type | TEAM_MEMBER, OPPONENT |
| MatchProposal.status | PENDING_CONFIRMATION, ACCEPTED, REJECTED, EXPIRED |
| ProposalConfirmation.decision | PENDING, ACCEPTED, DECLINED |
| Match.status | SUGGESTED, CONFIRMED, COMPLETED, CANCELLED |
| Payment.payment_type | BOOKING_DEPOSIT, BOOKING_REMAINING_PAYMENT, REFUND; hai loại MATCH_*_DEPOSIT chỉ dữ liệu cũ |
| Payment.payment_method | VNPAY, MOMO, CASH, BANK_TRANSFER |
| Payment.status | PENDING, SUCCESS, FAILED, REFUND_PROCESSING, REFUNDED |
| Notification.delivery_channel/status | IN_APP, EMAIL / PENDING, SENT, FAILED |

`RANDOM_SQUAD` là giá trị mới được hợp đồng này phục hồi trong VARCHAR post_type để khớp báo cáo, khác `LEGACY_RANDOM_SQUAD` của dữ liệu lịch sử. Không gửi match_mode vì migration V2 đã bỏ cột này.

Không ghi `PAID`, `REFUND_PENDING`, `WAITING_CONFIRMATION` vào ENUM hiện tại. UI có thể dịch trạng thái sang tiếng Việt nhưng gửi nguyên mã chuẩn.

### 3.2 Bổ sung schema cần có trước khi lập trình đầy đủ

Các bổ sung trong bảng này đã được migration V3 áp dụng trên TiDB dùng chung ngày 27/10/2026 và người quản lý dự án đã gửi kết quả xác minh. Riêng notification_type giữ ENUM mở rộng thay vì chuyển VARCHAR. Không chạy lại migration V2 từ đầu, không sửa âm thầm database của các thành viên.

| Bảng | Thay đổi đích | Lý do |
| --- | --- | --- |
| match_posts | Thêm pitch_type VARCHAR(16) NULL và end_time DATETIME NULL | Bài chưa chọn sân vẫn cần loại sân và khoảng thời gian để AI ghép |
| match_posts | Chấp nhận RANDOM_SQUAD trong validator post_type | Giữ chế độ gom nhóm của báo cáo; VARCHAR hiện có không cần thêm ENUM |
| bookings | Thêm payment_rule VARCHAR(32) NULL, payer_plan JSON NULL | Chốt danh sách người phải trả và số tiền từng phần ngay khi tạo hold, tránh đổi quy tắc sau xác nhận |
| notifications | Giữ ENUM notification_type, nối thêm các loại thông báo mới; giữ nguyên thứ tự giá trị cũ | Bổ sung POST_EXPIRED, PROPOSAL_EXPIRED, MATCH_CONFIRMED, MATCH_CANCELLED, BOOKING_EXPIRED, REFUND_PROCESSING, REFUND_SUCCESS, REFUND_FAILED |

Migration V3 tại database/schema/003_contract_v3.sql đã được áp dụng trên TiDB dùng chung; không chạy lại. DDL phải được kiểm thử với phiên bản TiDB đích trước khi áp dụng; không chuyển ENUM thông báo sang VARCHAR trong V3. Backfill pitch_type từ pitches; end_time từ booking liên kết nếu có, các hàng còn lại phải rà soát thay vì tự đoán giờ kết thúc. Không cho bài lịch sử thiếu lịch tham gia tự động ghép.

`payer_plan` ví dụ: `[{"user_id":2,"amount":"60000.00"},{"user_id":3,"amount":"60000.00"}]`. Sau khi tạo không được sửa kế hoạch trong cùng booking. Trạng thái từng phần tính từ Payment, không lưu lặp trong JSON.

## 4. Luồng đặt sân và chống trùng

1. Client chọn sân/slot, gửi POST /bookings. Backend khóa bản ghi Pitch theo pitch_id trong transaction, rồi kiểm tra lịch chồng lấn. Mọi đường ghi lịch, kể cả Admin và worker, phải dùng cùng giao thức khóa.
2. Chặn nếu có CONFIRMED, MAINTENANCE hoặc PENDING_HOLD với hold_expires_at lớn hơn thời gian server. Điều kiện overlap: old.start_time < new.end_time AND old.end_time > new.start_time. Không chỉ khóa các booking tìm được: khi chưa có booking sẽ không có hàng để khóa.
3. Tính giá từ price_per_slot và slot_duration_minutes. MVP đặt đúng một slot 90 phút, giờ bắt đầu trên lưới cấu hình, trong giờ mở cửa. Tạo PENDING_HOLD, deadline = UTC_now + 300 giây; lưu total_amount, deposit_amount, payer_plan. Commit xong mới gọi cổng thanh toán.
4. Frontend đếm ngược theo hold_expires_at và server_time; việc tải lại trang hoặc tạo lại QR không gia hạn hold.
5. Payment callback hợp lệ, booking còn hạn và đủ phần cọc → CONFIRMED. Chỉ một phần trả thành công thì vẫn PENDING_HOLD.
6. Worker kiểm tra mỗi 15 giây để đánh dấu EXPIRED và hoàn các phần đã thu của booking không hoàn tất. GET availability và mọi lệnh đặt lịch vẫn coi hold quá hạn là hết hiệu lực ngay, không chờ worker.
7. Deadline áp dụng chặt: khi server xử lý, UTC_now >= hold_expires_at thì không xác nhận booking. Callback tới muộn vẫn phải ghi nhận tiền thực tế và mở hoàn tiền; không chiếm lại slot đã nhả. Phải đối soát callback chậm và thông báo đúng trạng thái.

Thao tác đổi lịch đã CONFIRMED: Admin khóa các Pitch theo thứ tự ID tăng dần, kiểm tra xung đột, giữ nguyên giá và số tiền nếu chỉ đổi sang slot cùng giá. Đổi sang slot khác giá trả 409 PRICE_CHANGE_REQUIRES_REBOOK; phải hủy/hoàn và tạo booking mới. Lý do bắt buộc, không gia hạn hold cũ.

MANUAL_ADMIN vẫn phải có cọc thực tế: có thể tạo hold rồi thu CASH/BANK_TRANSFER được Admin xác nhận. MAINTENANCE_LOCK không phải đặt sân của khách, tiền bằng 0 và trạng thái MAINTENANCE, không yêu cầu cọc. Tạo khóa bảo trì trùng booking khách phải xử lý hủy và hoàn trước, không ghi đè.

## 5. Luồng ghép đội và ghép trận

### 5.1 Các chế độ

| Nhu cầu trong báo cáo | post_type | Điều kiện |
| --- | --- | --- |
| TEAM_VS_TEAM | FIND_OPPONENT | team_id, pitch_type, match_time, end_time, payment_rule; đội đủ số người ACTIVE |
| RECRUITMENT tuyển người | RECRUIT_MEMBERS | team_id, required_players, pitch_type, thời gian, payment_rule |
| RECRUITMENT cá nhân tìm đội | LOOK_FOR_TEAM | creator là người chơi; team_id=null; thời gian/loại sân có thể bỏ trống khi đăng, nhưng phải bổ sung trước khi AI tự ghép |
| RANDOM_SQUAD | RANDOM_SQUAD | Cá nhân hoặc nhóm nhỏ đăng ký gom thành đội tạm; cần loại sân và thời gian cụ thể |

Mỗi bài có title 1–150 ký tự, description tối đa 3000, skill_level, expiry_time ở tương lai và trước hoặc bằng match_time nếu có. `current_players` tính từ đội/nhóm đăng ký, không tin số client tự khai. `required_players` là số người còn thiếu, backend cập nhật sau mỗi lần nhận người. Đủ đội là ít nhất 5/7 người ACTIVE tương ứng loại sân; số dự bị không tự làm tăng tiền sân.

Nhóm nhỏ RANDOM_SQUAD dùng team_id và các thành viên ACTIVE đã tự nguyện tham gia nhóm qua TeamMember. Không nhận danh sách ID tùy ý để tự thêm người vào nhóm. Mỗi người chỉ được nằm trong một yêu cầu gom nhóm còn hiệu lực cho cùng khoảng giờ. Khi ghép nhóm, hai đại diện đồng ý, chuyển thành viên sang đội đích AI_RANDOM trong transaction; giữ nhóm nguồn INACTIVE nếu đã hợp nhất toàn bộ, không xóa lịch sử. Kiểm tra lại khả năng tham gia từng người trước khi commit.

Đội đích gom ngẫu nhiên do server tạo với creation_type=AI_RANDOM; đại diện đầu tiên theo (created_at,post_id) làm CAPTAIN. Sinh bài RECRUIT_MEMBERS để nhận thêm cá nhân/nhóm qua các proposal TEAM_MEMBER. Khi đủ người: đóng bài tuyển và tạo FIND_OPPONENT nếu chưa có đối thủ. Nếu đã gắn vào trận hiện hữu thì chỉ cập nhật đội, không tạo thêm trận và không thu thêm cọc sân.

### 5.2 Thuật toán đề xuất

Đây là bộ chấm điểm theo quy tắc cho MVP, chưa phải mô hình machine learning được huấn luyện. Không khẳng định độ chính xác khi chưa đánh giá.

Điều kiện cứng: khác người tạo/khác đội; tài khoản ACTIVE; bài OPEN, chưa hết hạn; nhu cầu bổ sung được cho nhau; không trùng lịch tham gia đã chốt; cùng loại sân; nếu cả hai đã chọn sân thì phải cùng pitch_id; khoảng giờ giao nhau đủ 90 phút. Thiếu thông tin bắt buộc thì trả về yêu cầu bổ sung, không coi thiếu thông tin là khớp hoàn toàn.

Sau lọc: thời gian khớp slot 40 điểm; cùng loại nhu cầu tương thích 20; cùng skill_level 40, lệch 1 mức 20, lệch từ 2 mức 0. Ngưỡng mặc định >=80. Đây là công thức đề xuất, phải đặt chung trong MatchmakingService. Hòa điểm: created_at cũ hơn rồi post_id nhỏ hơn. Không dùng fair_play_score hoặc match_priority để tự giảm cơ hội người chơi khi chưa có quy tắc đánh giá thống nhất.

Khi sinh proposal, khóa các bài theo post_id tăng dần, kiểm tra lại trạng thái, tạo hai confirmation PENDING và chuyển các bài liên quan sang LOCKED trong cùng transaction. Hai phía xác nhận là chủ bài nguồn và chủ bài đích/người được mời; không được cùng một user. Không chỉ dựa vào unique confirmation để ngăn sinh proposal trùng: cần giao thức khóa và kiểm tra proposal đang tồn tại trước khi insert.

Hạn đề xuất = min(created_at+15 phút, các expiry_time, giờ bắt đầu đá). Một bên DECLINED → proposal REJECTED. Quá hạn → EXPIRED. Mở lại các bài chưa hết hạn và còn nhu cầu; bài hết hạn → EXPIRED. Không tiếp tục loop tìm kiếm khi bài đã LOCKED.

### 5.3 Hai bên đồng ý

- TEAM_MEMBER: proposal ACCEPTED; cập nhật TeamMember, MatchParticipant và số chỗ trong transaction. Bài cá nhân/nhóm đã được nhận → MATCHED; bài tuyển OPEN nếu còn thiếu, MATCHED khi đã đủ. Không tạo Match hoặc Booking mới chỉ vì nhận thành viên.
- OPPONENT: proposal ACCEPTED nghĩa là đã đồng ý đề xuất. Hai bài tiếp tục LOCKED trong giai đoạn cọc; tạo Match **SUGGESTED** một lần, confirmed_at=null. Không dùng mặc định CONFIRMED trong bảng matches.
- Hai bên phải cùng slot và cùng payment_rule (SPLIT_EQUAL hoặc LOSER_PAYS_REMAINDER). Tạo booking hold duy nhất bằng BookingService; link booking_id vào Match và hai bài. Nếu không còn sân phù hợp, không thu tiền, Match CANCELLED, mở lại bài còn hạn và báo lỗi SLOT_UNAVAILABLE.
- Tổng cọc hai thể thức đều là **20% tổng tiền sân**, mỗi đội ứng một nửa cọc (10% tổng tiền sân). SPLIT_EQUAL: mỗi đội chịu 50% tổng tiền sân, trừ cọc đã trả. LOSER_PAYS_REMAINDER: không hoàn cọc; sau khi chốt kết quả, đội thua trả toàn bộ tiền sân còn thiếu của cả hai đội. Nếu hòa, quyết toán như SPLIT_EQUAL. Hai khoản cọc dùng BOOKING_DEPOSIT cùng booking_id, user_id khác nhau. Làm tròn phần nguồn xuống 1 VND, phần đích nhận số dư để khớp tổng.
- Mỗi bên trả đúng phần payer_plan; chỉ khi đủ các phần và chưa hết hold: Booking CONFIRMED, Match CONFIRMED, matches.confirmed_at=UTC_now, hai bài MATCHED; gửi thông báo trận và liên hệ được phép.
- Hết hold, thiếu cọc: Booking EXPIRED, Match CANCELLED; hoàn các phần đã thu. Bài còn hạn được OPEN lại sau khi xử lý trạng thái kèo; bài hết hạn EXPIRED. Không lấy proposal ACCEPTED làm bằng chứng đã thanh toán.

Để tránh thu trùng, API mới không nhận booking_id khi tạo bài. Bài lịch sử có booking_id chỉ được ghép sau khi dịch vụ đã đối soát kế hoạch cọc hiện có; phiên bản đầu trả 409 LEGACY_BOOKING_REQUIRES_REVIEW nếu cố ghép tự động trường hợp này. Không tự hủy hoặc thu thêm tiền của booking đã xác nhận trước đó.

## 6. Danh mục endpoint

Các path dưới đây đều sau `/api/v1`. `Me` nghĩa là chỉ chính người đăng nhập; `Captain` nghĩa là CAPTAIN ACTIVE đúng đội; `Party` nghĩa là một trong hai người xác nhận hoặc thành viên được phép xem trận. Admin không được giả mạo quyết định đồng ý thay người chơi.

### 6.1 Auth và tài khoản — Người 1

| Method và path | Quyền | Request hoặc query | data trả về |
| --- | --- | --- | --- |
| POST /auth/register | Public | full_name, email, password, phone?, skill_level? | UserSelf; 201 |
| POST /auth/login | Public | email, password | access_token, expires_in, user:UserSelf |
| GET /users/me | Me | — | UserSelf |
| PATCH /users/me | Me | full_name?, phone?, skill_level? | UserSelf |

UserSelf: user_id, full_name, email, phone, role, skill_level, status. Email chuẩn hóa trim/lowercase; mật khẩu 8–72 byte UTF-8 do bcrypt; đăng nhập sai trả lỗi chung, không tiết lộ tài khoản có tồn tại. Hash mật khẩu thật, không dùng chuỗi demo trong seed làm hash. Google OAuth và đổi mật khẩu nằm ngoài API v1 cơ bản.

### 6.2 Đội và bài đăng — Người 2

| Method và path | Quyền | Request hoặc query | data trả về |
| --- | --- | --- | --- |
| GET /teams | Player | my=true mặc định | Team[] |
| POST /teams | Player | team_name | Team; tạo người lập làm CAPTAIN; 201 |
| GET /teams/{team_id} | Thành viên/Admin | — | Team + members |
| PATCH /teams/{team_id} | Captain | team_name | Team |
| POST /teams/{team_id}/join-requests | Player | — | TeamJoinRequest; 201 |
| PATCH /teams/{team_id}/join-requests/{post_id}/respond | Captain | decision: ACCEPTED/DECLINED | TeamJoinRequest |
| DELETE /teams/{team_id}/members/me | Thành viên | — | team_id, status:LEFT |
| DELETE /teams/{team_id}/members/{user_id} | Captain | reason | team_id, user_id, status:REMOVED |
| GET /match-posts | Public | post_type?, pitch_type?, skill_level?, from?, to?, page? | PostSummary[] |
| GET /match-posts/my | Player | status?, page? | MatchPost[] |
| POST /match-posts | Player/Captain | PostCreate | MatchPost; 201 |
| GET /match-posts/{post_id} | Public/chủ bài | — | MatchPost đã ẩn dữ liệu riêng |
| PATCH /match-posts/{post_id} | Chủ bài | title?, description?, lịch/tiêu chí khi OPEN | MatchPost |
| POST /match-posts/{post_id}/cancel | Chủ bài | reason | MatchPost |
| GET /match-posts/{post_id}/participants | Chủ bài/Admin | page? | Participant[] |
| POST /match-posts/{post_id}/participants | Player | — | Participant + proposal_id; 201 |
| DELETE /match-posts/{post_id}/participants/me | Người đăng ký | — | Participant |

Team: team_id, team_name, created_by, creation_type, status, active_member_count. Member: user_id, full_name, role, status, joined_at. Participant: participant_id, post_id, user_id, status, joined_at. PostSummary: post_id, title, post_type, team_id, pitch_id, pitch_type, match_time, end_time, skill_level, payment_rule, required_players, current_players, expiry_time, status. MatchPost thêm description và thông tin của chính chủ bài, không thêm email/phone của người khác.

Đăng ký vào đội không tạo bảng join_requests mới trong bản này: TeamJoinRequest ánh xạ một bài RECRUIT_MEMBERS của đội và MatchParticipant PENDING. `POST /teams/{id}/join-requests` chỉ hoạt động khi đội có đúng một bài tuyển OPEN phù hợp; không có trả 409 RECRUITMENT_NOT_OPEN, nhiều bài yêu cầu dùng endpoint post cụ thể. Response gồm post_id, participant_id, proposal_id, status. Captain ACCEPTED tương đương confirmation của chủ bài; người xin vào đã bày tỏ đồng ý bằng yêu cầu nhưng vẫn phải xác nhận proposal qua mục 6.3 trước khi ACTIVE. Không thêm thành viên chỉ nhờ Captain đồng ý. Captain muốn rời đội phải chuyển vai trò trước; v1 chưa có endpoint chuyển quyền nên trả 409 CAPTAIN_TRANSFER_REQUIRED.

PATCH lịch/tiêu chí chỉ khi OPEN và chưa có đề xuất hoạt động; không sửa số tiền hoặc status trực tiếp. Hủy bài liên quan Match đang thu cọc phải đi qua luồng hủy Match, không cập nhật một bảng riêng lẻ. Quyền DELETE thành viên chỉ áp dụng trước khi người đó bị ràng buộc vào trận sắp diễn ra; nếu có ràng buộc trả 409 ACTIVE_MATCH_MEMBERSHIP.

PostCreate ví dụ:

```json
{
  "post_type":"FIND_OPPONENT",
  "title":"FC A tìm đối thủ sân 7",
  "description":"Giao hữu tối thứ sáu",
  "team_id":1,
  "pitch_id":2,
  "pitch_type":"PITCH_7",
  "match_time":"2026-10-30T19:00:00+07:00",
  "end_time":"2026-10-30T20:30:00+07:00",
  "skill_level":"INTERMEDIATE",
  "payment_rule":"SPLIT_EQUAL",
  "expiry_time":"2026-10-30T17:00:00+07:00"
}
```

pitch_id có thể null để AI chọn sân trong cụm, nhưng pitch_type và giờ phải đủ trước khi tự ghép. LOOK_FOR_TEAM chỉ cần title, skill_level, expiry_time lúc đăng; API trả `matching_ready=false` nếu thiếu pitch_type/match_time/end_time. Đây là trường tính toán, không phải cột SQL. Đội/người chơi không được tạo nhiều bài cạnh tranh trùng giờ để vượt khóa ghép.

### 6.3 AI, đề xuất và trận đấu — Người 3

| Method và path | Quyền | Request hoặc query | data trả về |
| --- | --- | --- | --- |
| POST /matchmaking/scan | Admin | post_id? | scanned_count, created_proposal_ids |
| GET /match-proposals | Party | status?, page? | Proposal[] |
| GET /match-proposals/{proposal_id} | Party | — | Proposal + confirmations |
| POST /match-proposals/{proposal_id}/respond | Đúng người xác nhận | decision:ACCEPTED/DECLINED | Proposal + confirmations + match_id? + booking_id? |
| GET /matches | Party | status?, page? | Match[] |
| GET /matches/{match_id} | Party/Admin | — | MatchDetail |
| GET /matches/{match_id}/contacts | Đại diện hai bên | — | contacts; chỉ khi CONFIRMED |
| POST /matches/{match_id}/cancel | Đại diện/Admin | reason | Match + refund_summary |
| GET /notifications | Me | is_read?, page? | Notification[] |
| PATCH /notifications/{notification_id}/read | Chủ thông báo | — | Notification |

Worker gọi service nội bộ để scan; không mở endpoint scan công khai. Response lặp cùng decision trả bản ghi hiện tại, không tạo thêm booking; đổi decision đã chốt trả 409 ALREADY_RESPONDED.

Proposal: proposal_id, source_post_id, target_post_id, candidate_user_id, proposal_type, compatibility_score, status, expires_at, confirmed_at. Confirmation: user_id, decision, responded_at. Với OPPONENT bắt buộc target_post_id và candidate_user_id=null; với cá nhân TEAM_MEMBER dùng candidate_user_id, target_post_id có thể là bài LOOK_FOR_TEAM của chính người đó. Với nhóm dùng target_post_id của RANDOM_SQUAD, candidate_user_id=null; hai confirmation là hai đại diện.

Match: match_id, post_id, opponent_post_id, proposal_id, booking_id, match_time, status, confirmed_at. MatchDetail thêm end_time từ booking/bài, proposal, hai đội, booking trạng thái/hold_expires_at và payer_progress. Các phần cọc người khác chỉ trả tổng/trạng thái cần thiết; mã giao dịch chỉ chủ giao dịch/Admin được xem.

Notification: notification_id, notification_type, title, content, is_read, created_at, read_at, proposal_id, match_id. Nội dung email không chứa token hoặc dữ liệu thanh toán bí mật. Hai hàng IN_APP/EMAIL có thể cùng sự kiện; GET notifications chỉ lấy IN_APP để tránh lặp.

### 6.4 Sân, booking và thanh toán — Người 4

| Method và path | Quyền | Request hoặc query | data trả về |
| --- | --- | --- | --- |
| GET /field-complex | Public | — | FieldComplex + policy công khai |
| GET /pitches | Public | pitch_type?, min_price?, max_price? | Pitch[] |
| GET /pitches/{pitch_id} | Public | — | Pitch |
| GET /pitches/{pitch_id}/availability | Public | date YYYY-MM-DD theo giờ địa phương | Availability |
| POST /bookings | Player | pitch_id, start_time, end_time | Booking; 201 |
| GET /bookings/my | Me | status?, page? | Booking[] |
| GET /bookings/{booking_id} | Chủ/đại diện kèo/Admin | — | Booking + payer_progress |
| POST /bookings/{booking_id}/cancel | Chủ/Admin | reason | Booking + refund_summary |
| POST /payments/deposit | Người có phần phải trả | booking_id, payment_method | PaymentSession; 201 hoặc 200 nếu tái dùng |
| GET /payments/{payment_id} | Chủ/Admin | — | Payment |
| GET /payments/my | Me | page? | Payment[] |
| GET /payments/vnpay/ipn | Chữ ký nhà cung cấp | tham số theo adapter VNPay | ACK theo nhà cung cấp |
| POST /payments/momo/ipn | Chữ ký nhà cung cấp | payload theo adapter MoMo | ACK theo nhà cung cấp |

Các route IPN dùng hợp đồng xác thực/chữ ký và ACK của nhà cung cấp, không dùng JWT hay envelope JSON chung. Định dạng cụ thể phải lấy từ tài liệu merchant đã chọn khi triển khai, không coi sơ đồ UML là thông số giao thức. MVP triển khai một cổng trước; cổng chưa tích hợp trả 422 UNSUPPORTED_PAYMENT_METHOD. CASH/BANK_TRANSFER chỉ đi qua Admin, không cho player tự báo đã trả.

FieldComplex: complex_id, name, phone, address, policy:{hold_seconds, slot_duration_minutes, deposit_mode, deposit_value, opening_time, closing_time}. Giờ mở cửa đã chốt **06:00–23:00** giờ địa phương; giới hạn đặt trước **10 ngày**. Ngày đặt là ngày địa phương, chỉ nhận lịch bắt đầu ở tương lai và không vượt quá ngày hiện tại cộng 10 ngày; end_time không vượt giờ đóng cửa. Cấu hình chính sách do backend đọc, không có API cho player sửa.

Pitch: pitch_id, complex_id, pitch_name, pitch_type, price_per_slot, status. Availability: pitch_id, date, slot_duration_minutes, slots:[{start_time,end_time,status}], status slot là AVAILABLE/HELD/BOOKED/MAINTENANCE (DTO tính toán, không phải ENUM Booking). Không trả tên người đặt hay booking_id của người khác.

Booking: booking_id, pitch_id, user_id, start_time, end_time, total_amount, deposit_amount, booking_type, status, hold_expires_at, payment_rule, payer_progress, created_at. payer_progress:[{user_id,required_amount,paid_amount,status}], status UNPAID/PARTIAL/PAID tính từ giao dịch. `deposit_amount` là số phải cọc, không phải số đã thu.

Payment: payment_id, booking_id, post_id, amount, payment_type, payment_method, status, transaction_code, refund_for_payment_id, paid_at. PaymentSession thêm payment_url/qr_payload tùy adapter và expires_at bằng hạn hold. Không nhận amount, paid_at, status hoặc transaction_code do client gửi.

Booking trực tiếp không ghép đối thủ dùng mã nội bộ DIRECT_BOOKING (người đặt trả toàn bộ), không phải lựa chọn thể thức hai đội. Ví dụ booking trực tiếp giá 600.000 VND, cọc 20% là 120.000 VND:

```json
{
  "data":{
    "booking_id":21,"pitch_id":2,"user_id":2,
    "start_time":"2026-10-30T12:00:00Z","end_time":"2026-10-30T13:30:00Z",
    "total_amount":"600000.00","deposit_amount":"120000.00",
    "booking_type":"ONLINE","status":"PENDING_HOLD",
    "hold_expires_at":"2026-10-27T10:05:00Z","payment_rule":"DIRECT_BOOKING",
    "payer_progress":[{"user_id":2,"required_amount":"120000.00","paid_amount":"0.00","status":"UNPAID"}]
  },
  "meta":{"server_time":"2026-10-27T10:00:00Z"}
}
```

### 6.5 Admin và báo cáo — Người 5

Tất cả route dưới đây cần role ADMIN và tài khoản ACTIVE.

| Method và path | Request hoặc query | data trả về |
| --- | --- | --- |
| POST /admin/pitches | pitch_name, pitch_type, price_per_slot | Pitch; complex_id do server xác định; 201 |
| PATCH /admin/pitches/{pitch_id} | pitch_name?, price_per_slot?, status? | Pitch |
| GET /admin/bookings | from?, to?, pitch_id?, status?, page? | Booking[] |
| POST /admin/bookings | user_id, pitch_id, start_time, end_time, note | Booking MANUAL_ADMIN đang hold; 201 |
| PATCH /admin/bookings/{booking_id} | start_time, end_time, pitch_id?, reason | Booking |
| POST /admin/bookings/{booking_id}/cancel | reason | Booking + refund_summary |
| POST /admin/maintenance-locks | pitch_id, start_time, end_time, reason | Booking MAINTENANCE_LOCK; 201 |
| POST /admin/maintenance-locks/{booking_id}/cancel | reason | Booking CANCELLED |
| POST /admin/payments/record | booking_id, user_id, amount, payment_type, payment_method:CASH/BANK_TRANSFER, reference, note | Payment; 201 |
| POST /admin/payments/{payment_id}/refund | reason | Refund Payment; 202 khi đang xử lý |
| GET /admin/revenue | from, to, period:day/month/year | RevenueReport |
| GET /admin/revenue/daily | from, to | RevenueReport period=day |
| GET /admin/revenue/monthly | from, to | RevenueReport period=month |
| GET /admin/transactions | from, to, pitch_id?, payment_type?, status?, page? | Payment[] + thông tin booking/người trả |
| GET /admin/booking-statistics | from, to, pitch_id? | BookingStatistics |
| GET /admin/revenue/export | from, to, period? | File .xlsx |

from/to là ngày địa phương inclusive; backend đổi sang UTC `[đầu ngày from, đầu ngày sau to)`, mặc định tối đa 366 ngày mỗi lần. Không dùng cùng khoảng ngày để lẫn thời điểm thu tiền với ngày diễn ra booking. API doanh thu lọc paid_at; thống kê hoạt động lọc start_time, có nhãn rõ trong response.

RevenueReport: currency:VND, period, from, to, time_zone, items:[{period_start,gross_receipts,refunds,net_receipts}], totals cùng ba chỉ tiêu. Gross receipts gồm BOOKING_DEPOSIT và BOOKING_REMAINING_PAYMENT đã thực thu; net=gross-refunds. Không cộng total_amount của booking vào tiền đã thu và không cộng tiền cọc hai lần.

BookingStatistics: total_bookings, confirmed_bookings, cancelled_bookings, expired_bookings, refunded_booking_count, by_pitch, peak_hours. Không tính MAINTENANCE_LOCK là lượt đặt của khách; refunded_booking_count là distinct booking có REFUND thành công, có thể đồng thời thuộc cancelled_bookings nên không cộng các chỉ tiêu thành tổng. Tần suất sử dụng dựa giờ của booking CONFIRMED đã đến thời gian sử dụng; mẫu số là giờ mở cửa trừ lịch bảo trì trong kỳ.

Excel có các sheet TongHop, GiaoDich, DatSan; bộ lọc như API, định dạng tiền/ngày đúng kiểu, Content-Type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, Content-Disposition attachment. Ô nội dung do người dùng nhập bắt đầu bằng ký tự công thức phải xuất dạng văn bản.

## 7. Thanh toán, hoàn tiền và tính lặp an toàn

1. Backend sinh transaction_code duy nhất trước khi gọi gateway và lưu Payment PENDING; retry giao dịch còn hiệu lực trả lại session hiện có của cùng payer/booking. Khóa booking khi kiểm tra/tạo payment để hai request không tạo hai phần cọc cho cùng người. Không giữ transaction DB mở trong lúc gọi mạng.
2. Xác minh chữ ký, merchant, mã giao dịch, số tiền và kết quả từ gateway; đối chiếu Payment đã lưu. Redirect về frontend không có quyền ghi SUCCESS.
3. Callback xử lý trong transaction, khóa Pitch rồi Booking rồi Payment theo cùng thứ tự với worker. Lặp callback không cộng tiền, tạo trận hoặc gửi thông báo lặp. Trạng thái terminal không bị callback cũ ghi đè.
4. Call gateway lỗi/timeout không đồng nghĩa FAILED: giữ trạng thái chưa xác định, đối soát bằng transaction_code trước khi retry. Chỉ FAILED khi có bằng chứng thất bại từ gateway hoặc đã xác minh giao dịch không được tạo.
5. Admin hủy do sự cố, ghép kèo không hoàn tất vì hết hạn/không đủ cọc, hoặc tiền đến muộn sau khi hold hết hạn: tạo REFUND cho từng giao dịch thực thu đủ điều kiện. Người dùng tự hủy thì loại phần cọc bị mất của chính người hủy khỏi danh sách hoàn; không áp dụng hoàn toàn bộ một cách máy móc. Hoàn về người trả/công cụ thanh toán gốc, không theo user_id của chủ booking nếu khác người trả.
6. Bản v1 chỉ hoàn toàn bộ từng giao dịch gốc. Khóa payment gốc; nếu đã có refund đang xử lý/thành công thì tái dùng, không tạo thêm. `refund_for_payment_id` bắt buộc. Tạo mã hoàn duy nhất từ ID refund trước khi gọi gateway để retry cùng mã.
7. Payment gốc giữ SUCCESS trong lúc chờ hoàn. Hàng REFUND dùng REFUND_PROCESSING, sau xác nhận thành công dùng SUCCESS và paid_at là lúc hoàn thành; lúc đó payment gốc chuyển REFUNDED. Nếu gateway xác nhận thất bại, hàng refund FAILED, gốc vẫn SUCCESS. Nếu chưa rõ, giữ REFUND_PROCESSING và đối soát; không báo đã hoàn.
8. Worker tiếp tục đối soát các PENDING/REFUND_PROCESSING và tác vụ hoàn còn thiếu sau crash. Booking đã hủy/hết hạn nhưng còn tiền chưa hoàn là bằng chứng để tái tạo công việc an toàn. Email lỗi không rollback payment hoặc booking.

Người dùng được hủy hold chưa thu tiền. **Người dùng chủ động hủy sau khi đã cọc thì mất khoản cọc của chính mình**, kể cả rút khỏi kèo trong giai đoạn thu cọc; không tự hoàn khoản đó. Cọc bị giữ vẫn là giao dịch đã thu SUCCESS, không tạo REFUND và phải ghi rõ lý do hủy trong booking.note/payment.note. Nếu chỉ một bên chủ động hủy kèo, phần cọc của bên không hủy được hoàn khi kèo không thể tiếp tục; không phạt mất cọc của cả hai bên vì hành động của một bên. Admin hủy do sự cố hoặc hệ thống ghép thất bại vì quá hạn/không thu đủ cọc mà không có yêu cầu tự hủy: hoàn các khoản đã thu theo quy định. Không đánh đồng tự hủy, timeout và Admin hủy; service phải nhận diện nguyên nhân trước khi lập danh sách hoàn. Hủy không xóa lịch sử tiền hoặc thông tin người thao tác.

`POST /admin/payments/record` dùng reference để sinh transaction_code ổn định, ngăn ghi trùng. Cọc không được vượt phần còn phải trả của payer_plan; thanh toán phần còn lại không vượt total_amount trừ các khoản thu hợp lệ đã có. Chỉ cho phép giao dịch thực thu, không dùng endpoint này để giả callback online.

## 8. Doanh thu và thời gian

Chủ dự án đã bỏ chức năng doanh thu theo từng mặt sân. Báo cáo doanh thu và Excel chỉ tổng hợp toàn cụm theo ngày/tháng/năm hoặc khoảng thời gian, không nhóm hay lọc doanh thu theo pitch_id. View v_admin_revenue_by_pitch đã có trên TiDB được giữ nguyên và không dùng trong chức năng mới; không cần chạy DROP VIEW. Việc tra cứu giao dịch và thống kê hoạt động đặt sân theo mặt sân vẫn được giữ. Hai view v_admin_revenue_daily và v_admin_revenue_monthly là nguồn tham khảo truy vấn; daily hiện nhóm DATE(paid_at) trực tiếp, trong khi database lưu UTC. Vì vậy API báo cáo theo ngày Việt Nam phải chuyển múi giờ đúng trước khi nhóm; không dùng view ngày UTC rồi đổi nhãn ngày.

Tiền gốc status SUCCESS hoặc REFUNDED đều là khoản đã thu. Trừ đúng một lần hàng REFUND status SUCCESS theo paid_at của lần hoàn; REFUND_PROCESSING/FAILED chưa trừ. Các khoản MATCH_HOST_DEPOSIT và MATCH_JOIN_DEPOSIT cũ không được tự cộng vào doanh thu booking nếu chưa đối soát liên kết. Cọc bị giữ do người dùng tự hủy vẫn nằm trong khoản thực thu; không ghi giao dịch hoàn giả để giảm số thu. Doanh thu ở đây là dòng tiền thực thu ròng, không khẳng định là doanh thu kế toán đã ghi nhận theo ngày sử dụng.

## 9. Phân công tệp và tích hợp

| Thành viên | Backend chính | Frontend chính |
| --- | --- | --- |
| 1 Auth và nền tảng | models/user.py; auth routes/controller/service; JWT middleware; phối hợp app factory, config, extensions | features/auth; stores/auth; routes bảo vệ; services/api |
| 2 Đội và bài đăng | models/team.py, team_member.py, match_post.py, match_participant.py; team/post services | features/matchmaking phần đội và bài; types/team, post |
| 3 AI và thông báo | models/match_proposal.py, proposal_confirmation.py, match.py, notification.py; matchmaking/notification services, jobs | features/matchmaking phần đề xuất/trận; features/notifications |
| 4 Đặt sân và tiền | models/field_complex.py, pitch.py, booking.py, payment.py; booking/payment services, gateway adapter, jobs | features/pitches, bookings, payments |
| 5 Admin và thống kê | admin routes/controller; revenue_service.py; Excel exporter; import model chung | features/dashboard; pages/admin; biểu đồ và giao dịch |

Người 1 điều phối tệp dùng chung __init__.py, extensions.py, registry blueprint, constants/enums.py và response helpers. Người 2–4 cùng review migration bổ sung mục 3.2 trước khi một người tạo file. Không cho mỗi thành viên tự chạy create_all lên database dùng chung. Route → Controller → Service → ORM; logic transaction nằm ở service. Service AI gọi BookingService/PaymentService, không tự viết một bản chống trùng khác.

Khung hiện có PyJWT và bcrypt; không mặc định mã dùng Flask-JWT-Extended, Celery, Redis, Flask-SocketIO, OpenPyXL đã chạy được. Khi chọn dependency mới phải cập nhật requirements và hướng dẫn môi trường chung. ZIP requirements.txt có mã hóa UTF-16; chuyển về UTF-8 có kiểm tra trước khi chuẩn hóa môi trường.

Frontend chưa có package.json nên cần khởi tạo Vite trước khi chạy npm install. Thiết lập API base qua VITE_API_BASE_URL; credential database/gateway chỉ ở backend. Database URL và cổng thanh toán lấy từ env, không đặt trong tài liệu nhóm.

## 10. Các kiểm tra bắt buộc trước khi ghép code

1. Hai yêu cầu song song cùng slot: chỉ một hold thành công; slot chạm biên được phép. Admin tạo lịch và worker hết hạn phải tham gia cùng kiểm tra.
2. Hold hết sau đúng 300 giây theo server; refresh/tạo QR lại không gia hạn; GET lịch bỏ hold hết hạn dù worker chưa chạy.
3. Hai đội chia cọc: mới một bên trả không CONFIRMED; hai phần đúng hạn mới xác nhận một lần; thiếu một phần thì hoàn phần đã thu.
4. Callback giả, sai số tiền, gửi lặp, gửi muộn và timeout gateway đều không tạo lịch trùng hoặc báo thanh toán/hoàn tiền sai.
5. Hai bên phản hồi đồng thời chỉ sinh một Match/Booking. Chỉ một bên ACCEPTED chưa đủ chốt. Từ chối/hết hạn mở lại đúng bài còn nhu cầu.
6. Tuyển người/gom nhóm không vượt sức chứa, không thêm cùng user hai lần, không tạo trận chỉ vì đội vừa có thêm thành viên. RANDOM_SQUAD tạo AI_RANDOM và tiếp tục tìm đối thủ khi đủ người.
7. Người lạ không đọc payment, notification, danh sách đăng ký riêng hoặc liên hệ đối thủ. Đăng ký không được tạo ADMIN; Captain không sửa đội khác.
8. Admin hủy sau khi thu cọc tạo đúng một refund cho mỗi payment; lỗi hoàn tiền không báo thành công. Restart worker khôi phục được công việc dang dở.
9. Báo cáo đối soát thu 180.000 rồi hoàn 180.000 cho net=0; khoản hoàn ở ngày khác hiện đúng ngày hoàn; chuyển ngày UTC/giờ Việt Nam không lệch dữ liệu; Excel khớp bộ lọc JSON.
10. Model khớp schema hậu migration, seed mật khẩu là bcrypt hợp lệ. Kiểm tra thư viện thực cài và chạy được app, không coi danh sách package là bằng chứng đã tích hợp.

Mục tiêu 5.000 kết nối, phản hồi dưới 2 giây và uptime 99,9% trong báo cáo là yêu cầu cần đo/thiết kế vận hành. Không ghi đạt các mục tiêu đó chỉ sau unit test hoặc demo local.

## 11. Kế hoạch 7 ngày

| Ngày | Kết quả tích hợp |
| --- | --- |
| 1 | Chốt hợp đồng, migration bổ sung, ORM chung, Flask app và React chạy; đăng nhập thử |
| 2 | Đội/bài đăng, danh sách sân và availability; dữ liệu mẫu hợp lệ |
| 3 | Giữ sân 5 phút và kiểm tra song song; proposal/confirmation hai phía |
| 4 | Ghép thành viên và gom nhóm; callback cọc một cổng sandbox; đủ cọc mới chốt trận |
| 5 | Hủy/hết hạn/hoàn tiền; job đối soát; thông báo in-app và email |
| 6 | Admin lịch/bảo trì/doanh thu/giao dịch/Excel; kiểm thử luồng kết hợp |
| 7 | Sửa lỗi tích hợp, chạy kịch bản demo, đối chiếu sơ đồ và tài liệu triển khai |

Nếu phải cắt phạm vi, ghi rõ với nhóm: Google OAuth, chat WebSocket, đánh giá/tố cáo, radar/Fair-play và bản đồ GPS không nằm trong hợp đồng endpoint cơ bản này. Báo cáo vẫn có các đoạn nhắc chúng nên cần chỉnh phạm vi hoặc bổ sung hợp đồng sau; không tự xóa bảng ratings/reports hoặc các trường lịch sử.

## 12. Mermaid thay SD04

Thay Hình 2.9 bằng sơ đồ dưới đây. Khi đã LOCKED thì dừng quét cho bài đó; các worker tiếp tục xử lý qua SD05/SD06/SD07.

```mermaid
sequenceDiagram
    autonumber
    actor U as Người chơi / Đội trưởng
    participant UI as Giao diện Web
    participant API as MatchmakingService
    participant DB as Database
    participant AI as Bộ chấm điểm ghép
    participant N as Thông báo và Email
    U->>UI: Tạo bài đăng
    UI->>API: Gửi dữ liệu bài đăng
    API->>API: Kiểm tra đăng nhập, quyền và dữ liệu
    alt Không hợp lệ
        API-->>UI: 422 và các trường cần sửa
    else Hợp lệ
        API->>DB: Lưu bài OPEN
        API-->>UI: 201 và thông tin bài đăng
        Note over U,DB: Không thu cọc và không giữ sân khi đăng bài
        loop Khi bài còn OPEN và chưa hết hạn
            API->>DB: Lấy các yêu cầu còn hiệu lực
            DB-->>API: Dữ liệu ứng viên
            API->>AI: Lọc điều kiện và tính điểm
            AI-->>API: Danh sách ứng viên
            alt Có ứng viên đạt ngưỡng và còn khả dụng
                API->>DB: Khóa, kiểm tra lại và tạo proposal PENDING_CONFIRMATION
                API->>DB: Tạo hai confirmation PENDING và chuyển bài sang LOCKED
                API->>N: Thông báo đề xuất và hạn phản hồi cho hai bên
                N-->>U: Xem đề xuất và xác nhận
                Note over API,DB: Dừng quét bài LOCKED; tiếp tục SD05 hoặc SD06
            else Chưa có ứng viên phù hợp
                API->>DB: Giữ OPEN đến lần quét tiếp theo
            end
        end
        opt Hết hạn khi chưa ghép thành công
            API->>DB: Cập nhật bài EXPIRED
            API->>N: Thông báo hết hạn
            Note over API,N: Chưa thu tiền nên không phát sinh hoàn cọc
        end
    end
```

SD06 phải thể hiện đủ: hai ACCEPTED → tạo một Booking PENDING_HOLD 5 phút và Match SUGGESTED → thu đủ các phần payer_plan → Booking/Match CONFIRMED. SD07 xử lý tiền đã thu nhưng kèo không hoàn tất.

## 13. Danh sách sửa báo cáo và schema

| Vị trí | Điểm lệch | Cách sửa |
| --- | --- | --- |
| Hình 2.9 SD04 | Thu cọc trước AI; hoàn tiền sau 3 giờ tìm không được | Bỏ thanh toán khỏi SD04; hết bài dựa expiry_time; thanh toán tại SD06 |
| SD06 và migration V2 | Migration chú thích CONFIRMED khi mới đồng ý; matches có default CONFIRMED | Hợp đồng dùng SUGGESTED trước cọc, set status tường minh; sửa chú thích và cân nhắc migration đổi default sau kiểm thử |
| SD07 | Dùng Payment PAID và REFUND_PENDING | Dùng SUCCESS; hàng hoàn REFUND_PROCESSING; gốc REFUNDED sau hoàn đủ thành công |
| Bảng/diagram MatchPost | Còn matchMode | Thay bằng post_type và ánh xạ bốn giá trị ở mục 5 |
| Migration V2 | Chỉ nhận ba loại bài mới, không có RANDOM_SQUAD | Bổ sung validator và luồng gom nhóm; giữ LEGACY_RANDOM_SQUAD chỉ cho lịch sử |
| Class diagram | Thiếu MatchProposal, ProposalConfirmation, Notification | Bổ sung các lớp/bảng theo schema; Admin là role của User |
| Bài đăng | Thiếu end_time và loại sân khi chưa có pitch_id | Migration bổ sung mục 3.2; loại dữ liệu thiếu khỏi scan |
| Thanh toán | Không lưu kế hoạch hai người trả | Bổ sung payer_plan bất biến; Payment liên kết cùng booking |
| Thông báo | ENUM hiện không chứa hết hạn/hoàn tiền | Migration loại thông báo mục 3.2 |
| View doanh thu | Nhóm ngày UTC, không có mọi bộ lọc yêu cầu | Query service theo ngày Việt Nam và transaction chi tiết |
| Công nghệ | Nhắc Flask-JWT-Extended nhưng khung có PyJWT; SDK gửi email cần chọn thật | Đồng nhất thư viện với mã triển khai, tách adapter gửi email khỏi Firebase nếu chưa có dịch vụ gửi mail |
| Số mục và danh mục hình | Trùng 2.4/2.5 và Hình 2.13; danh mục hình cũ chưa đủ SD01–SD08 | Đánh lại số, cập nhật mục lục và caption tự động trong Word |
| Khảo sát | Đoạn nhận xét đưa 74%, 63%, 61–62%, 60% không giải thích nguồn và có thể không khớp bảng minh họa | Đối soát với dữ liệu khảo sát gốc; ghi rõ minh họa, không dùng làm kết quả khảo sát thật |

## 14. Quy định chia sẻ trong nhóm

Đặt tài liệu tại `docs/api/API_MODELS_CONTRACT_PROJECT1.md`. Mọi người dùng chung prefix, ENUM, DTO và service đã phân công. Thay đổi tên trường/endpoint hoặc nghiệp vụ phải sửa tài liệu và frontend/backend liên quan trong cùng PR. Chỉ một migration được review cho mỗi thay đổi schema. Không tự chạy SQL cleanup hay migration cũ lên database chung.

Migration V3 đã được áp dụng và xác minh trên TiDB dùng chung. Tài liệu này không chứng nhận backend/gateway đã được triển khai hoặc thể thức LOSER_PAYS_REMAINDER đã có luồng quyết toán. Điều kiện bắt đầu ghép code là kiểm tra mục 3.2, triển khai các endpoint theo phân công và vượt qua các kịch bản mục 10.

## Phụ lục A Từ điển cột sau migration V2

Danh sách dưới đây được đối chiếu từ schema gốc và các thay đổi trong migration V2, chưa bao gồm thay đổi đích ở mục 3.2. Các default của database được giữ nguyên để dễ phát hiện chỗ service phải gán tường minh, nhất là matches.status. COLLATE/COMMENT được lược bỏ cho dễ đọc; PK/FK/UNIQUE áp dụng theo hai tệp SQL nguồn.

### users

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| user_id | `int unsigned NOT NULL AUTO_INCREMENT` |
| full_name | `varchar(100) NOT NULL` |
| phone | `varchar(20) DEFAULT NULL` |
| email | `varchar(150) NOT NULL` |
| password_hash | `varchar(255) DEFAULT NULL` |
| google_id | `varchar(100) DEFAULT NULL` |
| role | `enum('PLAYER','ADMIN') NOT NULL DEFAULT 'PLAYER'` |
| skill_level | `enum('BEGINNER','AMATEUR','INTERMEDIATE','SEMI_PRO','PRO') NOT NULL DEFAULT 'AMATEUR'` |
| fair_play_score | `float NOT NULL DEFAULT '100'` |
| match_priority | `int NOT NULL DEFAULT '100'` |
| radar_stats | `json DEFAULT NULL` |
| status | `enum('ACTIVE','BANNED','INACTIVE') NOT NULL DEFAULT 'ACTIVE'` |
| created_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP` |
| updated_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` |

### field_complexes

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| complex_id | `int unsigned NOT NULL AUTO_INCREMENT` |
| name | `varchar(150) NOT NULL` |
| phone | `varchar(20) NOT NULL` |
| address | `varchar(255) NOT NULL` |
| created_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP` |

### teams

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| team_id | `INT UNSIGNED NOT NULL AUTO_INCREMENT` |
| team_name | `VARCHAR(100) NOT NULL` |
| created_by | `INT UNSIGNED DEFAULT NULL` |
| creation_type | `ENUM('USER_CREATED','AI_RANDOM') NOT NULL DEFAULT 'USER_CREATED'` |
| status | `ENUM('ACTIVE','INACTIVE') NOT NULL DEFAULT 'ACTIVE'` |
| created_at | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` |
| updated_at | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` |

### pitches

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| pitch_id | `int unsigned NOT NULL AUTO_INCREMENT` |
| complex_id | `int unsigned NOT NULL` |
| pitch_name | `varchar(100) NOT NULL` |
| pitch_type | `enum('PITCH_5','PITCH_7','PITCH_11') NOT NULL` |
| price_per_slot | `decimal(12,2) NOT NULL` |
| status | `enum('ACTIVE','MAINTENANCE','INACTIVE') NOT NULL DEFAULT 'ACTIVE'` |
| created_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP` |

### bookings

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| booking_id | `int unsigned NOT NULL AUTO_INCREMENT` |
| pitch_id | `int unsigned NOT NULL` |
| user_id | `int unsigned NOT NULL` |
| start_time | `datetime NOT NULL` |
| end_time | `datetime NOT NULL` |
| total_amount | `decimal(12,2) NOT NULL DEFAULT '0.00'` |
| deposit_amount | `decimal(12,2) NOT NULL DEFAULT '0.00'` |
| booking_type | `enum('ONLINE','MANUAL_ADMIN','MAINTENANCE_LOCK') NOT NULL DEFAULT 'ONLINE'` |
| status | `enum('PENDING_HOLD','CONFIRMED','CANCELLED','EXPIRED','MAINTENANCE') NOT NULL DEFAULT 'PENDING_HOLD'` |
| hold_expires_at | `datetime DEFAULT NULL` |
| note | `varchar(255) DEFAULT NULL` |
| created_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP` |
| updated_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` |

### match_posts

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| post_id | `int unsigned NOT NULL AUTO_INCREMENT` |
| creator_id | `int unsigned NOT NULL` |
| pitch_id | `INT UNSIGNED NULL` |
| booking_id | `int unsigned DEFAULT NULL` |
| team_id | `int unsigned DEFAULT NULL` |
| match_time | `DATETIME NULL` |
| skill_level | `enum('BEGINNER','AMATEUR','INTERMEDIATE','SEMI_PRO','PRO') NOT NULL` |
| payment_rule | `VARCHAR(100) NULL` |
| required_deposit | `decimal(12,2) NOT NULL DEFAULT '0.00'` |
| expiry_time | `datetime NOT NULL` |
| is_fallback_scanned | `tinyint(1) NOT NULL DEFAULT '0'` |
| current_players | `tinyint unsigned NOT NULL DEFAULT 1` |
| status | `ENUM('PENDING_DEPOSIT','OPEN','LOCKED','MATCHED','EXPIRED','CANCELLED') NOT NULL DEFAULT 'OPEN'` |
| created_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP` |
| updated_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` |
| post_type | `VARCHAR(32) NOT NULL` |
| title | `VARCHAR(150) NOT NULL` |
| description | `TEXT NULL` |
| required_players | `TINYINT UNSIGNED NULL` |

### match_participants

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| participant_id | `INT UNSIGNED NOT NULL AUTO_INCREMENT` |
| post_id | `INT UNSIGNED NOT NULL` |
| user_id | `INT UNSIGNED NOT NULL` |
| status | `ENUM('PENDING','ACCEPTED','REJECTED','CANCELLED') NOT NULL DEFAULT 'PENDING'` |
| joined_at | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` |
| updated_at | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` |

### team_members

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| team_member_id | `INT UNSIGNED NOT NULL AUTO_INCREMENT` |
| team_id | `INT UNSIGNED NOT NULL` |
| user_id | `INT UNSIGNED NOT NULL` |
| role | `ENUM('CAPTAIN', 'MEMBER') NOT NULL DEFAULT 'MEMBER'` |
| status | `ENUM('ACTIVE', 'LEFT', 'REMOVED') NOT NULL DEFAULT 'ACTIVE'` |
| joined_at | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` |

### matches

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| match_id | `int unsigned NOT NULL AUTO_INCREMENT` |
| post_id | `int unsigned NOT NULL` |
| booking_id | `int unsigned DEFAULT NULL` |
| opponent_post_id | `int unsigned DEFAULT NULL` |
| match_time | `datetime NOT NULL` |
| compatibility_score | `float NOT NULL DEFAULT '0'` |
| status | `enum('SUGGESTED','CONFIRMED','COMPLETED','CANCELLED') NOT NULL DEFAULT 'CONFIRMED'` |
| created_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP` |
| updated_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` |
| proposal_id | `INT UNSIGNED NULL; UNIQUE; FK match_proposals` |
| confirmed_at | `DATETIME NULL` |

### payments

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| payment_id | `int unsigned NOT NULL AUTO_INCREMENT` |
| user_id | `int unsigned NOT NULL` |
| booking_id | `int unsigned DEFAULT NULL` |
| post_id | `int unsigned DEFAULT NULL` |
| amount | `decimal(12,2) NOT NULL` |
| payment_type | `enum('BOOKING_DEPOSIT','BOOKING_REMAINING_PAYMENT','MATCH_HOST_DEPOSIT','MATCH_JOIN_DEPOSIT','REFUND') NOT NULL` |
| payment_method | `enum('VNPAY','MOMO','CASH','BANK_TRANSFER') NOT NULL` |
| transaction_code | `varchar(100) DEFAULT NULL` |
| refund_for_payment_id | `int unsigned DEFAULT NULL` |
| recorded_by_admin_id | `int unsigned DEFAULT NULL` |
| status | `enum('PENDING','SUCCESS','FAILED','REFUND_PROCESSING','REFUNDED') NOT NULL DEFAULT 'PENDING'` |
| paid_at | `datetime DEFAULT NULL` |
| note | `varchar(255) DEFAULT NULL` |
| created_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP` |
| updated_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` |

### ratings — dữ liệu lịch sử, ngoài API cơ bản

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| rating_id | `int unsigned NOT NULL AUTO_INCREMENT` |
| match_id | `int unsigned NOT NULL` |
| rater_id | `int unsigned NOT NULL` |
| rated_user_id | `int unsigned NOT NULL` |
| fair_play_score | `int NOT NULL` |
| skill_details | `json DEFAULT NULL` |
| comment | `text` |
| created_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP` |

### reports — dữ liệu lịch sử, ngoài API cơ bản

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| report_id | `int unsigned NOT NULL AUTO_INCREMENT` |
| match_id | `int unsigned DEFAULT NULL` |
| reporter_id | `int unsigned NOT NULL` |
| reported_user_id | `int unsigned NOT NULL` |
| processed_by_admin_id | `int unsigned DEFAULT NULL` |
| report_type | `varchar(100) NOT NULL` |
| description | `text NOT NULL` |
| status | `enum('PENDING','RESOLVED','REJECTED') NOT NULL DEFAULT 'PENDING'` |
| resolution | `text` |
| created_at | `datetime NOT NULL DEFAULT CURRENT_TIMESTAMP` |
| resolved_at | `datetime DEFAULT NULL` |

### match_proposals

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| proposal_id | `INT UNSIGNED NOT NULL AUTO_INCREMENT` |
| source_post_id | `INT UNSIGNED NOT NULL` |
| target_post_id | `INT UNSIGNED NULL` |
| candidate_user_id | `INT UNSIGNED NULL` |
| proposal_type | `ENUM('TEAM_MEMBER','OPPONENT') NOT NULL` |
| compatibility_score | `DECIMAL(5,2) NOT NULL DEFAULT 0.00` |
| status | `ENUM('PENDING_CONFIRMATION','ACCEPTED','REJECTED','EXPIRED') NOT NULL DEFAULT 'PENDING_CONFIRMATION'` |
| expires_at | `DATETIME NOT NULL` |
| confirmed_at | `DATETIME NULL` |
| created_at | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` |
| updated_at | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` |

### proposal_confirmations

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| confirmation_id | `INT UNSIGNED NOT NULL AUTO_INCREMENT` |
| proposal_id | `INT UNSIGNED NOT NULL` |
| user_id | `INT UNSIGNED NOT NULL` |
| decision | `ENUM('PENDING','ACCEPTED','DECLINED') NOT NULL DEFAULT 'PENDING'` |
| responded_at | `DATETIME NULL` |
| created_at | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` |

### notifications

| Cột | Kiểu và ràng buộc cột |
| --- | --- |
| notification_id | `INT UNSIGNED NOT NULL AUTO_INCREMENT` |
| user_id | `INT UNSIGNED NOT NULL` |
| proposal_id | `INT UNSIGNED NULL` |
| match_id | `INT UNSIGNED NULL` |
| notification_type | `ENUM('MATCH_PROPOSAL','PROPOSAL_ACCEPTED','PROPOSAL_REJECTED','BOOKING_HOLD','BOOKING_CONFIRMED','PAYMENT_SUCCESS','TEAM_JOINED') NOT NULL` |
| title | `VARCHAR(150) NOT NULL` |
| content | `TEXT NOT NULL` |
| delivery_channel | `ENUM('IN_APP','EMAIL') NOT NULL DEFAULT 'IN_APP'` |
| delivery_status | `ENUM('PENDING','SENT','FAILED') NOT NULL DEFAULT 'PENDING'` |
| is_read | `TINYINT(1) NOT NULL DEFAULT 0` |
| created_at | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` |
| sent_at | `DATETIME NULL` |
| read_at | `DATETIME NULL` |

Lưu ý khi dùng SQL nguồn: tệp gốc có SET FOREIGN_KEY_CHECKS=0 nhưng dòng bật lại ở cuối nằm trong comment; không chạy tệp này lên database đang có dữ liệu. Khi chuẩn hóa script import phải khôi phục kiểm tra khóa ngoại và xác minh quan hệ. Các seed password_hash đang có chuỗi minh họa, cần tạo bcrypt thật. Chỉ kiểm tra mật khẩu bằng thư viện, không dùng chuỗi seed như mật khẩu đã băm.

## 15. Quyết định bổ sung và nội dung còn trao đổi

### 15.1 Chia tiền hai đội đã chốt

Hai đội chọn thể thức khi đăng bài và thống nhất trước xác nhận kèo. Không đổi thể thức sau khi đã đồng ý hoặc bắt đầu thu cọc. DIRECT_BOOKING vẫn dành cho một người đặt trực tiếp.

| Thể thức | Tiền cọc | Quyết toán sau trận |
| --- | --- | --- |
| SPLIT_EQUAL | Tổng 20%, hai đội cọc mỗi đội 10% tổng tiền sân | Mỗi đội chịu 50% tổng tiền sân, trừ tiền đội đó đã trả |
| LOSER_PAYS_REMAINDER có đội thua | Cọc như SPLIT_EQUAL, không hoàn cọc đội thắng | Đội thua trả toàn bộ số tiền sân còn thiếu của hai đội; đội thắng không trả thêm |
| LOSER_PAYS_REMAINDER nhưng hòa | Cọc như SPLIT_EQUAL | Tính như chia 50–50 |

Ví dụ sân 600.000 VND, mỗi đội đã cọc 60.000 VND: chia 50–50 hoặc hòa thì mỗi đội trả thêm 240.000 VND; có đội thua thì đội thua trả thêm 480.000 VND, đội thắng không trả thêm. Tổng thực trả là 540.000 VND của đội thua và 60.000 VND của đội thắng. Cọc vẫn là khoản tiền sân đã thu, không bị bỏ khỏi sổ giao dịch.

Khoản trả thêm dùng BOOKING_REMAINING_PAYMENT, ghi đúng user_id người thực trả và booking_id; không ghi khoản do đội thua trả hộ thành giao dịch của đội thắng. Khi tính tiền còn thiếu phải trừ mọi khoản thực thu hợp lệ đã có, không chỉ trừ cọc và không tạo giao dịch trùng. payer_plan là kế hoạch cọc, không sửa lại nó để giả lập kế hoạch quyết toán sau trận.

**Luồng tại quầy đã chốt:** sau giờ kết thúc trận, Admin trực sân mở booking, đối chiếu với hai đội rồi chọn kết quả. Với LOSER_PAYS_REMAINDER, có ba nút SOURCE_WIN / OPPONENT_WIN / DRAW; giao diện hiển thị tên đội cụ thể thay cho mã. Với SPLIT_EQUAL hoặc DIRECT_BOOKING không cần chọn kết quả để tính tiền. Bỏ luồng hai đội xác nhận qua ứng dụng và không có hạn chờ phản hồi 30 phút.

Backend tính số tiền còn phải thu từ giá booking, thể thức và các giao dịch thực thu. Frontend hiển thị số tiền và người phải trả; sau khi Admin bấm Tạo QR, QR xuất hiện bên dưới. Chia 50–50/hòa tạo giao dịch riêng từng người trả; có đội thua thì một giao dịch cho đại diện đội thua, gồm cả phần còn thiếu của đội thắng. Không gửi amount tự nhập từ frontend để quyết định số tiền online.

Mỗi QR phải gắn payment_id, booking_id, user_id, BOOKING_REMAINING_PAYMENT, số tiền và phiên bản quyết toán. Mã người trả lấy từ đại diện hai đội đã gắn vào trận, không chọn user_id tùy ý. Khi chưa thống nhất kết quả tại quầy, Admin chưa tạo QR theo thắng/thua. Không suy ra đã thanh toán chỉ vì đã chọn kết quả, tạo QR hoặc quay lại từ trang thanh toán.

Admin được sửa lựa chọn khi chưa có giao dịch quyết toán. Khi đã có QR còn hiệu lực, chặn thay kết quả cho đến khi giao dịch được hủy/đối soát theo khả năng cổng thanh toán; nếu gateway không hỗ trợ hủy tức thời thì chờ hết hạn và đối soát trước. Không coi việc ẩn QR ở frontend là vô hiệu hóa giao dịch. Tiền đến muộn của phiên quyết toán cũ phải được đối soát để không thu thừa hoặc chốt theo kế hoạch cũ.

Sau khi đã thu thành công, không tự sửa kết quả/số tiền kế hoạch; điều chỉnh phải ghi lý do, lịch sử và giao dịch bù/hoàn riêng nếu cần. Callback online xác minh đủ chữ ký, số tiền và trạng thái như luồng cọc. Tiền mặt/chuyển khoản tại quầy dùng API Admin xác nhận thực thu riêng, không đánh dấu giao dịch online thành công bằng nút thu tiền mặt. Khóa booking khi tạo/ghi giao dịch để chống trùng QR và vượt số tiền còn thiếu, kể cả khi có hai tab Admin.

**API Admin bổ sung — hợp đồng triển khai, chưa có backend:**

| Method và path | Request | data |
| --- | --- | --- |
| GET /admin/bookings/{booking_id}/settlement | — | booking_id, payment_rule, outcome, version, total_amount, collected_amount, outstanding_amount, payers |
| PATCH /admin/bookings/{booking_id}/settlement/result | outcome:SOURCE_WIN/OPPONENT_WIN/DRAW, expected_version, reason? | Quyết toán cập nhật; chỉ LOSER_PAYS_REMAINDER, sau giờ kết thúc |
| POST /admin/bookings/{booking_id}/settlement/payment-sessions | payer_user_id, payment_method:VNPAY/MOMO, expected_version | PaymentSession cho phần còn phải trả do backend tính |

Tất cả endpoint trên cần ADMIN ACTIVE. expected_version chống ghi đè từ màn hình cũ; sai phiên bản trả 409 STATE_CONFLICT. `payers` gồm user_id, team_id (có thể null cho đặt trực tiếp), display_name, remaining_amount; tiền là chuỗi thập phân. Thu trực tiếp tiếp tục dùng POST /admin/payments/record với payment_type=BOOKING_REMAINING_PAYMENT và kiểm tra cùng kế hoạch quyết toán. Không có kết quả cho đặt trực tiếp. Không thêm endpoint xác nhận kết quả của người chơi vào luồng này.

Cần migration bổ sung sau V3 để lưu bền vững kết quả, phiên bản/kế hoạch quyết toán, Admin thao tác, thời điểm và lịch sử điều chỉnh; Payment mới phải liên kết được phiên quyết toán. Chưa tạo/chạy migration đó trong lần cập nhật tài liệu này. Cần cập nhật DTO/service/mock khi triển khai màn hình Admin. Migration V3 đã chạy không chứa các cấu trúc này, không chạy lại V3. Huy phụ trách giao diện chọn kết quả/tiền/QR; Tú phụ trách service/API tính tiền, tạo giao dịch và xác nhận thu; Đức hỗ trợ schema và tích hợp.

### 15.2 Đăng nhập đã chốt

Access token hết hạn sau 60 phút từ lúc cấp; người dùng đăng nhập lại để lấy token mới. Không cấp refresh token, không thêm bảng refresh session hoặc endpoint tự gia hạn. Backend kiểm tra exp ở mọi API bảo vệ; tài khoản không ACTIVE vẫn bị từ chối dù token còn hạn. Việc token hết hạn không gia hạn hoặc tự hủy hold; booking tiếp tục theo deadline 5 phút của server.

### 15.3 Google Login

Chủ dự án đang hỏi độ khó, chưa yêu cầu đưa vào phạm vi triển khai. Hướng triển khai: Google Identity Services trên React; backend nhận ID token, kiểm tra chữ ký/aud/iss/exp qua thư viện google-auth, ánh xạ sub sang users.google_id rồi cấp phiên của ứng dụng. Không tin email hoặc user_id do frontend tự khai, không tự cấp ADMIN; liên kết tài khoản đã có phải xác minh quyền sở hữu. users.google_id đã có trong schema, vì vậy thường không cần cột mới chỉ để nhận dạng Google, nhưng vẫn cần Client ID, cấu hình origin, dependency và kiểm thử. Tài liệu chính thức: https://developers.google.com/identity/gsi/web/guides/verify-google-id-token
