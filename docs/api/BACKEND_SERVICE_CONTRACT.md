# Hợp đồng service backend giữa Đức và Tú

Phiên bản 1.1 — cập nhật ngày 29/10/2026: thu phần còn lại theo booking, QR chung và Admin xác nhận thực thu. Đức và Tú dùng tệp này khi triển khai và review backend. Đây là hợp đồng nội bộ giữa các service, chưa phải mã đã có hoặc kết quả kiểm thử. Hợp đồng HTTP/JSON nằm tại [API và Models](API_MODELS_CONTRACT_PROJECT1.md); tài liệu này chốt trách nhiệm, dữ liệu nội bộ, transaction và các điểm tích hợp còn thiếu.

## 1. Phân công và nguồn dữ liệu

| Người | Sở hữu |
| --- | --- |
| Đức | App factory, config/TLS/UTC, JWT, lỗi/response chung, Unit of Work; User, Team, TeamMember, MatchPost, MatchParticipant, MatchProposal, ProposalConfirmation, Match, Notification; AI và NotificationService |
| Tú | FieldComplex, Pitch, Booking, Payment; BookingService, PaymentService, SettlementService, RevenueService, gateway adapter và các worker tiền/booking |
| Cả hai review | Models dùng chung, thứ tự khóa, migration bổ sung, luồng cọc xác nhận trận, hủy/hoàn và quyết toán |

Đức điều phối tệp models/__init__.py và constants; Tú viết các Model mình sở hữu rồi export dùng chung. Một bảng chỉ có một ORM Model. Không sao chép User/Match/Booking sang module khác. Controller không tự cập nhật trạng thái hay tiền bằng ORM ngoài service đã phân công.

Database test dùng chung đã áp dụng V3: không chạy lại schema gốc/V2/V3, không create_all khi khởi động. Không tự sửa database để vừa với code; tạo migration riêng và review trước. Backend hiện là khung; các hàm và module được mô tả dưới đây là phần phải triển khai.

## 2. Quy tắc nghiệp vụ dùng chung

- Slot 90 phút, mở 06:00–23:00 giờ Việt Nam, đặt trước tối đa 10 ngày.
- Giữ sân 300 giây tính từ server; hết hạn khi now >= hold_expires_at. Không gia hạn qua refresh/tạo QR lại.
- Tổng cọc 20% tiền sân; hai đại diện mỗi người cọc một nửa tổng cọc. Lượt đặt trực tiếp do một người cọc 20%.
- SPLIT_EQUAL: mỗi đội chịu 50%; LOSER_PAYS_REMAINDER: hai bên giữ nguyên cọc đã đóng, đội thua trả phần còn thiếu của cả hai đội; hòa tính như SPLIT_EQUAL. DIRECT_BOOKING: người đặt trả toàn bộ.
- Sau trận, hai thể thức chỉ để hai đội tự chia tiền. Hệ thống không ghi đội thắng/hòa hoặc tính nghĩa vụ từng đội. Ví dụ sân 600000 đã cọc tổng 120000: hiển thị còn thiếu 480000 và một QR chung cho booking; có thể chuyển nhiều lần hoặc trả tiền mặt. Admin kiểm tra tổng tiền thực nhận rồi xác nhận đã thu đủ.
- Người dùng chủ động hủy mất phần cọc của mình. Admin hủy do sự cố hoặc hệ thống không hoàn tất kèo vì hết hạn/thiếu cọc: hoàn các khoản đủ điều kiện. Không gộp các nguyên nhân này thành một chính sách.
- Tuyển người lẻ không tự thu cọc tham gia và không tạo booking chỉ vì nhận thành viên. Chi phí nội bộ của thành viên chưa có hợp đồng riêng.
- JWT hết hạn 3600 giây, không refresh token. Google Login và cổng thanh toán đầu tiên chưa được chốt triển khai.

## 3. Cấu trúc module và hướng gọi

```text
app/
  contracts/       dto.py, enums.py, errors.py             Đức
  infrastructure/ unit_of_work.py, lock_manager.py         Đức + Tú review
  services/
    auth_service.py, team_service.py, post_service.py       Đức
    matchmaking_service.py, match_service.py               Đức
    notification_service.py                               Đức
    booking_service.py, payment_service.py                 Tú
    booking_balance_service.py, revenue_service.py         Tú
    gateway/                                               Tú
  use_cases/
    respond_proposal.py                                    Đức
    process_payment.py, expire_hold.py, cancel_booking.py   Tú
    settle_booking.py                                     Tú
  jobs/                                                    Theo module sở hữu
```

Controller → use_case → các service → ORM. Use case là hàm điều phối ngoài cùng của một nghiệp vụ. Service con không gọi controller, không gọi HTTP vòng về backend. Đức gọi BookingService; Tú gọi MatchService qua dependency injection ở use case, tránh hai module import vòng nhau.

## 4. Kiểu dữ liệu nội bộ và quyền

- Actor: `{user_id: int, role: PLAYER|ADMIN}` lấy từ JWT đã xác minh chữ ký/exp; không lấy từ request body. ACTIVE/quyền tài nguyên được kiểm tra lại trong command transaction.
- Money: Decimal theo đơn vị VND; lượng thu VND nguyên đồng. Cọc tổng = ceil(total_amount * 0.20) tới 1 VND; chia phần nguồn floor(deposit_total/2), phần đích nhận số dư. Không dùng float.
- Thời gian nội bộ dùng datetime có timezone UTC. Ở ranh giới ORM DATETIME, serialize/deserialize nhất quán UTC. Khoảng sân nửa mở [start,end).
- SOURCE là chủ source_post_id; OPPONENT là chủ opponent/target_post_id. Thứ tự không thay đổi theo người gửi request hoặc người thắng.
- booking.user_id là người đứng tên; Payment.user_id của cọc/hoàn vẫn là người thực trả. Riêng thu gộp BOOKING_REMAINING_PAYMENT tại quầy: user_id dùng booking.user_id làm tài khoản quy chiếu vì cột hiện NOT NULL, không khẳng định người đó thực chuyển toàn bộ tiền. note phải ghi thu gộp theo booking; UI/báo cáo không diễn giải thành nghĩa vụ/người chuyển của từng đội. Hoàn khoản thu gộp cần Admin đối chiếu chứng từ/người nhận, không tự hoàn về tài khoản quy chiếu. Không áp dụng ngoại lệ này cho cọc.
- Service trả dataclass/DTO Python; controller mới đổi Decimal thành chuỗi, datetime thành ISO và bọc data/meta. Service không trả Flask Response.
- Giá, số tiền phải trả, số thành viên, hạn giữ chỗ và Matching Score do backend tính. Frontend không có quyền ghi trực tiếp.

Các DTO nội bộ bắt buộc, định nghĩa chung tại contracts/dto.py:

| DTO | Trường tối thiểu |
| --- | --- |
| CommandResult | outcome:OK hoặc mã thất bại nghiệp vụ đã xử lý; data; error nullable; http_status |
| BookingHold | booking_id, status, hold_expires_at, total_amount, deposit_amount, payer_plan |
| MatchParties | match_id, booking_id, source/opponent:{team_id, team_name, representative_user_id}; chỉ phục vụ hiển thị |
| BookingBalance | booking_id, payment_rule, total_amount, deposit_collected_amount, remaining_collected_amount, collected_amount, outstanding_amount, payment_status, qr_payload?, transfer_reference?, qr_unavailable_reason? |
| ManualReceipt | payment_method:CASH/BANK_TRANSFER, amount:Decimal, reference?; khoản Admin đã xác minh thực nhận |
| MembershipResult | team_id, user_id, participant_id, remaining_players, post_status |
| PaymentApplyResult | payment_id, booking_id, applied:bool, duplicate:bool, late:bool |
| GatewayResult | state:SUCCESS/FAILED/PENDING/UNKNOWN; merchant_reference; provider_reference nullable; amount; currency; paid_at nullable; payment_url/qr_payload/expires_at nullable |
| RefundPlan | booking_id, cause, items:[{original_payment_id, payer_user_id, amount}], forfeited_payment_ids |

Một người không thể là cả hai đại diện phải trả cọc trong cùng kèo. Không nhập None/0 để giả đại diện còn thiếu. DTO không chứa ORM entity để controller vô tình đọc thêm dữ liệu riêng tư ngoài quyền cho phép; các service con có thể dùng ORM entity trong cùng ctx nhưng phải chuyển sang DTO trước khi rời use case.

## 5. Transaction và khóa — bắt buộc cho cả hai

### 5.1 Ai mở và commit

Đức cung cấp UnitOfWork và LockManager dùng SQLAlchemy Session. Một command use case sở hữu một transaction ở giai đoạn ghi DB; nhận Actor, kiểm tra ACTIVE/quyền, gọi các service rồi commit một lần. Khi lỗi không được xử lý để tạo kết quả nghiệp vụ có chủ đích thì rollback toàn bộ transaction đó.

Service con nhận `ctx` chứa cùng Session và đồng hồ UTC; được flush để lấy ID nhưng không commit/rollback, không mở Session khác. Lấy thời gian kiểm tra hạn sau khi đã lấy đủ khóa, không dùng thời gian cũ trước lúc chờ khóa; sát thời điểm xác nhận phải bảo đảm hold vẫn còn hạn. Controller không mở transaction thứ hai bao quanh use case. Không dùng db.session.begin tùy tiện sau khi middleware đã đọc ORM và tạo autobegin: transaction command phải được quản lý thống nhất; xác minh JWT có thể diễn ra trước nhưng kiểm tra user/ORM thuộc UnitOfWork.

Mỗi callback, job hoặc command HTTP đi qua cùng use case, không có đường tắt cập nhật một bảng. Job xử lý từng booking/proposal trong transaction riêng, không khóa cả batch rồi gọi gateway/email.

### 5.2 Thứ tự khóa

Mọi luồng lấy khóa cần thiết theo thứ tự bảng dưới đây, trong một bảng theo ID tăng dần:

0. users — bổ sung khi triển khai: khóa toàn bộ người tham gia trước các bảng bên dưới nếu command tạo/đổi ràng buộc lịch hoặc thành viên. Hai đội khác nhau có thể dùng chung một người; chỉ khóa Team không ngăn được người đó đồng thời nhận hai kèo. Đọc trước roster, khóa users rồi Team và đọc lại roster; nếu roster đổi, rollback/thử lại toàn command. Booking callback/hủy cũng dùng thứ tự này nếu cần khóa User; không được khóa User sau Booking/Payment.

1. teams
2. pitches
3. match_posts
4. match_proposals
5. proposal_confirmations
6. matches
7. bookings
8. payments
9. team_members
10. match_participants

Thông báo/audit/outbox mới được insert sau các thay đổi chính; worker cập nhật chúng trong transaction riêng, không giữ khóa outbox rồi quay lại khóa booking. Không bắt buộc khóa bảng không liên quan, ví dụ đặt trực tiếp thường chỉ cần Pitch → Booking → Payment.

LockManager được phép đọc không khóa trước để tìm toàn bộ ID liên quan, sau đó khóa đúng thứ tự và đọc/kiểm tra lại quan hệ. Nếu phát hiện cần thêm khóa ở vị trí đã đi qua, rollback và khởi động lại command; không tiếp tục lấy khóa ngược thứ tự. Row mới tạo trong cùng transaction chưa công khai nên không cần khóa cạnh tranh, nhưng vẫn tuân thủ giao thức khóa các parent đã tồn tại.

Ví dụ callback có booking_id: tìm trước Pitch và các liên kết trận/bài; khóa tập bản ghi theo thứ tự trên, kiểm tra lại booking và Payment. Không khóa Payment trước rồi mới khóa Pitch. Mọi lệnh đổi lịch, hủy, hết hạn, thanh toán của Admin cũng dùng cùng giao thức.

BookingService kiểm tra overlap sau khi khóa Pitch: existing.start_time < requested.end_time AND existing.end_time > requested.start_time. Chặn CONFIRMED, MAINTENANCE, PENDING_HOLD còn hạn. Không chỉ khóa các booking tìm thấy vì khi sân trống sẽ không có hàng booking để khóa.

### 5.3 Không gọi mạng trong transaction

Tạo ý định thanh toán/refund và outbox trong transaction → commit → gọi adapter → transaction ngắn khác ghi kết quả. Không giữ khóa DB trong lúc gọi VNPay/MoMo/email. Callback dùng use case riêng.

Deadlock/write conflict chỉ được retry có giới hạn tại ranh giới toàn command DB (đề xuất triển khai mặc định 3 lần). Không tự lặp gọi gateway. Mã giao dịch và yêu cầu nhà cung cấp phải được giữ ổn định để retry không tạo thu/hoàn trùng.

## 6. Điểm nối Auth

Đức cung cấp:

```python
auth_service.register(ctx, full_name, email, password, phone=None, skill_level=None)
auth_service.login(ctx, email, password)
auth_service.require_active_actor(ctx, actor)
auth_service.require_admin(ctx, actor)
```

login trả access_token, expires_in=3600, user; không refresh_token. Dùng bcrypt thật, không so sánh password plaintext với password_hash. Ba tài khoản mẫu hiện cần rà soát/đặt hash hợp lệ riêng, không tự đổi mật khẩu khi triển khai hợp đồng này.

Tú dùng middleware JWT của Đức ở route và cùng auth_service trong command. require_active_actor không thay cho kiểm tra quyền chủ booking, người trong payer_plan hoặc đại diện đội. Admin không được đồng ý proposal thay người chơi.

## 7. Điểm nối ghép đối thủ và giữ sân

### 7.1 Public use case do Đức viết

```python
respond_proposal(proposal_id: int, actor: Actor, decision: ACCEPTED | DECLINED)
```

Use case tự lập UnitOfWork, tìm/khóa các bản ghi cần thiết, kiểm tra hạn proposal và quyền người phản hồi. Cùng decision đã ghi trả lại kết quả hiện tại; đổi decision đã chốt trả ALREADY_RESPONDED.

- Một bên ACCEPTED: lưu confirmation, chưa tạo Booking/Match chốt.
- Một bên DECLINED: proposal REJECTED, mở lại bài còn hạn/còn nhu cầu; không thu tiền.
- Cả hai ACCEPTED, loại TEAM_MEMBER: thực hiện mục 8.
- Cả hai ACCEPTED, loại OPPONENT: chọn trước một slot và tập khóa cần thiết; tạo một Match SUGGESTED theo unique(proposal_id), gọi BookingService trong cùng transaction. Không commit Match rồi mới tạo hold ở transaction khác.

### 7.2 Service do Tú viết

Điểm discovery bổ sung khi triển khai: `booking_service.find_match_pitch(ctx, *, pitch_type, start_time, end_time) -> int | None` chỉ đọc để tìm Pitch trước khi khóa; `create_match_hold` kiểm tra lại availability sau khóa. Nếu bài đã chọn pitch_id thì dùng ID đã chọn. Đăng ký instance tại `app.extensions['booking_service']`; không tạo adapter thành công giả trong runtime. Route đọc chi tiết dùng callable `app.extensions['booking_reader'](ctx, booking_id=..., actor=...)`; hủy trận dùng `app.extensions['cancel_match'](actor, match_id=..., reason=...)` là use case ngoài cùng của Tú.

```python
booking_service.create_match_hold(
    ctx, *, match_id: int, pitch_id: int,
    start_time: datetime, end_time: datetime,
    source_user_id: int, opponent_user_id: int,
    payment_rule: SPLIT_EQUAL | LOSER_PAYS_REMAINDER,
) -> BookingHold
```

Preconditions: use case đã khóa đầy đủ parent theo mục 5; match_id thuộc đúng hai bài/đại diện đã đồng ý. BookingService tự kiểm tra lại sân/giờ/giá và tính tiền. Không nhận total_amount/deposit_amount từ Đức hoặc frontend.

BookingHold nội bộ:

```python
{
    "booking_id": 21,
    "status": "PENDING_HOLD",
    "hold_expires_at": utc_datetime,
    "total_amount": Decimal("600000.00"),
    "deposit_amount": Decimal("120000.00"),
    "payer_plan": [
        {"user_id": 2, "amount": "60000.00"},
        {"user_id": 3, "amount": "60000.00"},
    ],
}
```

Đức liên kết booking_id vào Match và hai bài. Hai bài ở LOCKED trong lúc cọc; proposal ACCEPTED chỉ biểu thị đã đồng ý. payer_plan chỉ ghi phần cọc, bất biến sau khi tạo. Tạo lại cùng proposal trả lại liên kết đã có, không tạo hold mới/gia hạn.

### 7.3 Không còn sân khi hai bên đồng ý

create_match_hold phát sinh SlotUnavailable trước khi insert Booking. respond_proposal bắt lỗi này bên trong transaction để lưu một kết quả thất bại có chủ đích: giữ hai quyết định đã nhận, proposal ACCEPTED, Match CANCELLED (hoặc không insert Match nếu chưa tạo), mở lại bài còn hạn và tạo thông báo. Không để Match SUGGESTED thiếu booking tồn tại như một kèo đang thu tiền.

Use case commit các thay đổi thất bại đã xử lý rồi trả outcome SLOT_UNAVAILABLE cho controller ánh xạ 409. Không ném exception rollback sau khi vừa định lưu việc mở lại bài. Lỗi DB không dự kiến vẫn rollback toàn bộ. Kèo muốn ghép lại phải có proposal mới; không hồi sinh proposal đã xử lý.

## 8. Điểm nối tuyển người lẻ và gom nhóm

Đức sở hữu toàn bộ:

```python
team_service.accept_member_proposal(ctx, *, proposal_id: int) -> MembershipResult
```

Chỉ gọi khi TEAM_MEMBER có đủ hai confirmation ACCEPTED và còn hạn; khóa Team, bài/proposal rồi các hàng thành viên/đăng ký theo thứ tự chung. Kiểm tra còn chỗ, khả năng tham gia và không trùng người. Cập nhật TeamMember/MatchParticipant cùng số người còn thiếu một lần; unique hiện có và transaction bảo vệ gọi lặp.

Bài tìm đội của người được nhận đóng MATCHED. Bài tuyển OPEN nếu còn thiếu, MATCHED khi đủ. Nhóm AI_RANDOM tiếp tục theo luồng đã có trong hợp đồng API. Không gọi BookingService/PaymentService trong thao tác nhận người; không tự thu khoản cọc tham gia mới.

## 9. Điểm nối thanh toán cọc

Tú sở hữu public use case tạo session cọc và callback:

```python
create_deposit_session(actor, *, booking_id, payment_method)
process_gateway_callback(provider, verified_callback)
```

Adapter xác minh chữ ký, merchant, mã giao dịch, số tiền và loại tiền; không coi dữ liệu callback chưa xác minh là lệnh nghiệp vụ. Tạo session phải lấy user từ Actor và payer_plan, kiểm tra ACTIVE/quyền/hạn hold. Bảo đảm một payer không có hai phiên cọc đang hiệu lực; request lặp tái dùng phiên đã có. Không tự retry POST mạng để thu thêm.

GatewayPort do Tú cung cấp, Đức không gọi SDK trực tiếp:

```python
gateway.create_payment(merchant_reference, amount, expires_at, callback_url)
gateway.query_payment(merchant_reference)
gateway.request_refund(merchant_reference, refund_reference, amount)
gateway.query_refund(refund_reference)
gateway.cancel_payment(merchant_reference)  # có thể trả UNSUPPORTED
gateway.verify_callback(raw_body, headers_or_query)
```

Kết quả adapter phân biệt SUCCESS / FAILED / PENDING / UNKNOWN. Timeout mạng không chứng minh giao dịch thất bại. Merchant reference dùng mã đã lưu trước khi gọi mạng; không tạo mã mới chỉ vì timeout. Cổng chưa tích hợp trả UNSUPPORTED_PAYMENT_METHOD, không giả thành công.

Trong command ghi nhận callback, Tú khóa các bản ghi đúng mục 5 và gọi:

```python
payment_service.apply_verified_payment(ctx, verified_callback) -> PaymentApplyResult
booking_service.confirm_if_deposit_complete(ctx, *, booking_id) -> bool
match_service.confirm_after_deposit(ctx, *, booking_id) -> Match | None
```

confirm_if_deposit_complete tính số thực thu đúng từng payer, không chỉ cộng tổng của hai người. Đủ cọc và còn hạn mới đổi Booking CONFIRMED. Nếu trả True và booking có Match thì gọi hàm Đức confirm_after_deposit trong cùng transaction. Hàm Đức đọc lại trạng thái Booking/cọc, cập nhật Match CONFIRMED, confirmed_at và hai bài MATCHED, tạo thông báo. Đặt trực tiếp trả Match=None, không tạo trận giả.

Callback lặp khi đã áp dụng trả kết quả hiện tại. Không chấp nhận callback thất bại cũ ghi đè SUCCESS. Mới một bên trả không xác nhận trận. Tiền tới muộn sau deadline vẫn được ghi nhận là tiền thực thu nhưng không hồi sinh hold/trận; lập công việc hoàn đủ điều kiện và đối soát.

## 10. Điểm nối hết hạn, hủy và hoàn tiền

Public use case do Tú điều phối:

```python
expire_booking_hold(booking_id: int)  # worker; không nhận actor giả từ HTTP
cancel_booking(actor, *, booking_id: int, reason: str)
cancel_match(actor, *, match_id: int, reason: str)  # Đức route tới cùng orchestration hủy
```

Nguyên nhân nội bộ do backend suy ra từ route/quyền/thời gian: HOLD_TIMEOUT, USER_CANCEL, ADMIN_INCIDENT, LATE_PAYMENT. Người dùng không được gửi ADMIN_INCIDENT để tự lấy quyền hoàn tiền. Actor có quyền và lý do phải được ghi audit.

Service Đức được gọi trong cùng ctx khi booking có trận:

```python
match_service.cancel_for_booking(ctx, *, booking_id, cause, actor_id) -> Match | None
post_service.release_after_cancel(ctx, *, match_id, cause)
```

- HOLD_TIMEOUT: chỉ xử lý PENDING_HOLD đã hết hạn, chuyển Booking EXPIRED, Match CANCELLED; bài còn nhu cầu/còn hạn mở lại, bài quá hạn EXPIRED.
- USER_CANCEL: người hủy mất phần cọc của chính mình; phần bên không hủy được hoàn nếu kèo không thể tiếp tục. Mở/đóng bài theo nhu cầu thực tế, không tự mở lại bài của người vừa chủ động hủy.
- ADMIN_INCIDENT: Booking CANCELLED, trận liên quan CANCELLED; lập danh sách hoàn đủ điều kiện.
- Booking CONFIRMED không bị worker hold-timeout hủy. Gọi hủy lặp không tạo refund mới.

PaymentService của Tú tính refund plan từ giao dịch thực thu, người thực trả và nguyên nhân. Đội thắng không được hoàn cọc chỉ vì thắng trận. Service/worker không hoàn tiền đồng thời từ hai cách gọi khác nhau; mọi đường gọi chung một hàm.

```python
payment_service.plan_refunds(ctx, *, booking_id, cause, cancelling_user_id=None)
payment_service.apply_verified_refund(ctx, verified_refund)
```

Một refund logic cho mỗi giao dịch gốc trong bản hoàn toàn bộ. Khóa payment gốc và tra refund đã có trước khi tạo. Gốc giữ SUCCESS khi hàng REFUND đang REFUND_PROCESSING; refund SUCCESS mới đổi gốc REFUNDED. Hoàn thất bại đã xác minh dùng FAILED; kết quả chưa biết giữ đang xử lý và đối soát, không báo thành công. Không log mật khẩu/token hoặc payload nhạy cảm.

## 11. Thu phần còn lại tại quầy — luồng chốt 29/10/2026

Đức cung cấp `match_service.get_booking_parties(ctx, *, booking_id) -> MatchParties | None`: đọc tên hai đội và đại diện để hiển thị, không chọn người phải trả. Đặt sân trực tiếp trả None. DTO BookingBalance/ManualReceipt và Protocol BookingBalancePort nằm trong contracts/dto.py; chỉ là điểm nối, chưa có service tiền thật của Tú.

Tú triển khai các public use case sở hữu transaction:

```python
get_booking_balance(actor, *, booking_id) -> BookingBalance
confirm_booking_paid(actor, *, booking_id, expected_outstanding,
                     idempotency_key, receipts: list[ManualReceipt]) -> BookingBalance
```

Chỉ ADMIN ACTIVE được xác nhận. Booking phải CONFIRMED, đã đến end_time, không bị hủy; kết thúc giờ đá không chứng minh đã trả tiền. payment_rule lưu trên booking chỉ hiển thị để hai đội tự chia. Không có outcome, kế hoạch từng đội, phiên bản kết quả hoặc thao tác chọn người thắng.

Backend tính tiền thực thu ròng: cộng BOOKING_DEPOSIT/BOOKING_REMAINING_PAYMENT gốc có status SUCCESS hoặc REFUNDED, trừ các hàng REFUND SUCCESS đúng một lần. PENDING/FAILED không tính. outstanding_amount=max(total_amount-collected_amount,0); thu vượt giá phải báo đối soát, không tạo thêm khoản thu. deposit_collected_amount và remaining_collected_amount là tổng thu gốc của từng loại; collected_amount là số ròng sau hoàn. payment_status UNPAID/PARTIAL/PAID là DTO tính toán, không thêm vào ENUM Booking.

Một QR chuyển khoản ngân hàng thông thường cho phần thiếu của booking, kèm transfer_reference ổn định (ví dụ BOOKING-21) và tên ngân hàng/số tài khoản do server cấu hình. qr_payload không có thì trả qr_unavailable_reason để Huy hiển thị thiếu cấu hình, không giả QR thành công. QR gợi ý tổng còn thiếu nhưng hai đội có thể chuyển từng phần hoặc trả tiền mặt; Admin kiểm tra số tiền thực nhận. Hiển thị/quét QR không tạo Payment SUCCESS và không tự callback như VNPay/MoMo. Cổng cọc trước trận giữ nguyên.

Nút xác nhận thu đủ gửi expected_outstanding là số dư vừa xem, idempotency_key giữ nguyên khi retry và receipts là các khoản đã đối chiếu: CASH/BANK_TRANSFER, amount dương theo VND nguyên đồng, reference chứng từ nếu có. Có thể một hoặc nhiều khoản, hoặc trộn tiền mặt/chuyển khoản; không phân bổ cho từng đội. Backend khóa Booking/Payment theo thứ tự chung, kiểm tra lại quyền/giờ/số dư; tổng receipts phải bằng đúng số dư hiện tại và expected_outstanding phải khớp. Khác số dư trả STATE_CONFLICT để tải lại. Không ghi khoản đã có trong payments thêm lần nữa.

Tạo một Payment BOOKING_REMAINING_PAYMENT SUCCESS cho mỗi receipt, ghi recorded_by_admin_id, paid_at (UTC), payment_method, booking_id và note thu gộp. transaction_code sinh ổn định từ booking_id + idempotency_key + chỉ số receipt; kiểm tra các code đã có TRƯỚC so sánh số dư, retry cùng payload trả kết quả cũ; cùng key khác payload trả STATE_CONFLICT. Ghi mọi receipt trong một transaction, gọi lặp/hai tab không thu trùng. Khi đã PAID, không thêm khoản thu; correction/refund phải đối chiếu riêng. Ghi nhận thực thu và khép giờ đá là hai trạng thái độc lập; không sửa Match chỉ vì bấm nút thu đủ.

Không cần bảng booking_settlements hoặc cột outcome/settlement_version. Với luồng thu gộp hiện tại, các cột Payment V3 đủ ghi số tiền, phương thức, Admin, thời gian, mã chống trùng và note; danh sách PAID tính từ giao dịch. Không cần thêm cột bookings chỉ để lưu trùng cờ đã trả.

## 11.1 Phân công màn hình Admin

Huy dựng danh sách Sắp đá / Đang đá / Đã hết giờ chưa thu đủ / Đã thu đủ. Đang đá: start_time <= now < end_time và booking CONFIRMED; nhóm đã thu đủ phải tính từ balance, không từ giờ kết thúc. Hiển thị tên sân/hai đội, start_time/end_time, thể thức, cọc thực thu, tổng còn thiếu, QR chung và nút xác nhận. Tú cung cấp danh sách/balance và thao tác ghi tiền; Đức cung cấp thông tin trận/đội cùng Auth/DTO. Dminh không đổi Auth, Quang giữ lựa chọn thể thức. Phần danh sách/thu tiền thật của Tú và UI Huy chưa nằm trong code Đức.

## 12. Dữ liệu bổ sung cần triển khai sau V3

Chốt ranh giới dữ liệu dưới đây để Đức/Tú soạn migration tiếp theo. Chưa có DDL được tạo hoặc chạy từ tài liệu này; chưa được code ORM giả định các bảng/cột đã tồn tại.

| Phần | Thiết kế đích tối thiểu |
| --- | --- |
| Thu phần còn lại | Dùng Booking/Payment V3; không tạo booking_settlements, không thêm outcome/settlement_id/settlement_version. Giữ transaction_code UNIQUE hiện có. |
| payment_sessions | session_id PK; payment_id UNIQUE/FK; merchant_reference UNIQUE; provider; payment_url/qr_payload nullable; expires_at; provider_state; created_at/updated_at; lưu session/expiry để trả lại QR đúng sau restart và đối soát, không chứa credential gateway |
| audit_events | event_id PK; actor_user_id nullable cho job; event_type; entity_type/entity_id; before/after JSON đã lọc bí mật; reason; created_at; ghi thao tác đối soát/điều chỉnh thu tiền và nguyên nhân hủy |
| outbox_events | event_id PK; unique dedup_key; event_type; aggregate_type/id; payload nội bộ; status PENDING/PROCESSING/SENT/FAILED; attempts; available_at; lease_until; created_at/processed_at |

Audit/outbox và payment_sessions cho gateway cọc/hoàn là phạm vi hạ tầng riêng cần review chung, không phải yêu cầu tạo bảng mới để thu phần còn lại. Tú viết Payment/gateway; Đức review tích hợp và phần audit/outbox chung. Dùng một bộ migration được review chung, không mỗi người tự ADD COLUMN. Không thu hẹp ENUM hay xóa view/bảng lịch sử trong migration này.

Outbox ghi cùng transaction nghiệp vụ; worker claim bằng lease trong transaction ngắn rồi commit trước khi gọi mạng. Worker crash được lấy lại sau lease. Gateway operation dùng dedup/merchant reference bền vững; queue phát lại không có nghĩa được thu/hoàn lần nữa. Email có thể bị gửi lặp khi lỗi giữa gửi và ACK; không hứa exactly-once email, nhưng không được ghi nhận tiền hoặc tạo trận lặp.

## 13. Lỗi dùng chung

Đức định nghĩa DomainError(code, message, fields, http_status) và error handler. Không trả stack trace/SQL/credential cho frontend.

| Nhóm | Mã / HTTP |
| --- | --- |
| Xác thực/quyền | UNAUTHORIZED, TOKEN_EXPIRED / 401; FORBIDDEN, ACCOUNT_DISABLED / 403 |
| Tài nguyên | NOT_FOUND / 404 |
| Dữ liệu | VALIDATION_ERROR / 422 |
| Trạng thái | SLOT_UNAVAILABLE, HOLD_EXPIRED, STATE_CONFLICT, ALREADY_RESPONDED, DEPOSIT_ALREADY_PAID / 409 |
| Thu đủ | STATE_CONFLICT, PAYMENT_RECONCILIATION_REQUIRED / 409; VALIDATION_ERROR / 422 cho tổng receipts không khớp |
| Gateway | UNSUPPORTED_PAYMENT_METHOD / 422; PAYMENT_PROVIDER_UNAVAILABLE / 503 |

Lỗi nghiệp vụ dự kiến trong mục 7.3 trả CommandResult sau commit; controller ánh xạ cùng envelope lỗi, không ném exception làm rollback thay đổi đã chủ đích lưu. Callback dùng ACK của gateway, không ép dùng envelope HTTP JSON của app.

## 14. Kiểm thử để được ghép code

| Tình huống | Kết quả bắt buộc | Người chính |
| --- | --- | --- |
| Hai request cùng slot, cả khi chưa có booking | Chỉ một hold; lịch chạm biên được phép | Tú |
| Hai confirmation đồng thời/gọi lặp | Một proposal result, tối đa một Match và một hold | Đức + Tú |
| Hết sân sau khi hai bên đồng ý | Kết thúc có căn cứ, không giữ Match SUGGESTED dở, không thu tiền | Đức + Tú |
| Một đội cọc | Vẫn PENDING_HOLD, chưa CONFIRMED | Tú |
| Đủ cọc đúng hạn | Booking/Match/bài/thông báo cập nhật cùng transaction | Đức + Tú |
| Callback lặp, muộn, giả, sai tiền | Không thu/hoàn/chốt trùng; đối soát tiền đến muộn | Tú |
| Callback và timeout/hủy đồng thời | Cùng thứ tự khóa, không hồi sinh booking đã nhả | Đức + Tú |
| Nhận thành viên lặp/đầy đội | Không trùng người/vượt chỗ, không tạo booking | Đức |
| USER_CANCEL so với ADMIN_INCIDENT | Mất/hoàn đúng người, có nguyên nhân/audit | Tú + Đức |
| Worker crash sau commit hoặc gọi gateway | Khôi phục công việc, không tạo giao dịch trùng | Tú |
| 600000, cọc 60000/đội: cả hai thể thức | Cùng hiển thị tổng thiếu 480000, QR chung; không chọn kết quả | Tú + Huy |
| Trả nhiều lần hoặc trộn CASH/BANK_TRANSFER | Tổng receipts khớp số dư, ghi đúng phương thức, chỉ tính thu một lần | Tú |
| Hai tab Admin/xác nhận lặp | Kiểm tra expected_outstanding và transaction_code ổn định; không thu trùng | Tú |
| Đã thu một phần tiền còn lại | Chỉ tạo giao dịch cho phần thực sự còn thiếu | Tú |
| PLAYER gọi xác nhận thu đủ | 403, không thay đổi DB | Đức + Tú |
| Hết token | 401, không gia hạn/hủy hold chỉ vì logout | Đức |

Các ca concurrency/payment phải được kiểm thử tích hợp trên database thử nghiệm, không chỉ mock hoặc unit test cộng tiền. Không dùng database nhóm để test hủy/thu tiền thử.

## 15. Thứ tự bàn giao

1. Đức: app factory, UnitOfWork/LockManager, Actor/lỗi/DTO, Model registry, Auth; Tú: Models sân/booking/payment và availability.
2. Đức: đội/bài/proposal và respond_proposal; Tú: create_match_hold và tạo session cọc.
3. Cùng nhau: một luồng hai confirmation → một hold → callback đủ cọc → CONFIRMED, rồi timeout/hủy/hoàn.
4. Tú viết balance/QR chung/xác nhận thu đủ dựa trên Booking/Payment V3; Huy dựng màn hình. Đức bàn giao get_booking_parties và DTO; audit/outbox/gateway là hạng mục riêng, không chặn thiết kế thu gộp.
5. Ghép frontend thật theo hợp đồng; chỉ chọn một gateway để triển khai trước. Backend mock gateway dùng trong test phải được phân biệt rõ với gateway thật.

Mỗi PR thay một điểm nối phải cập nhật hợp đồng, service caller/callee và test liên quan. Không đổi tên hàm/ENUM/DTO riêng lẻ rồi yêu cầu bên kia tự đoán. Không có endpoint/hàm giả báo thành công cho phần chưa triển khai. Trước khi merge, Đức và Tú cùng xác nhận checklist mục 14 của luồng đó đã đạt.
