import { useEffect, useState } from 'react';
import type { Booking, UserSelf } from '../../types/api';
import { getMyBookings, moneyVN, timeVN } from '../../services/huyApi';
import { dayLabel } from '../pitches/PitchesPage';
import { bookingHash } from '../../services/bookingNavigation';
import { VenueContact, useVenue } from './venue';

const upcoming = (b: Booking) => ['CONFIRMED', 'PENDING_HOLD'].includes(b.status) && Date.parse(b.end_time) > Date.now();

/** What a customer wants on arrival: book a pitch, see the next game and what is still owed, reach the venue. */
export function PlayerHome({ user }: { user: UserSelf }) {
  const venue = useVenue();
  const [next, setNext] = useState<Booking[] | null>(null);
  useEffect(() => {
    let live = true;
    getMyBookings().then(rows => { if (live) setNext(rows.filter(upcoming).sort((a, b) => Date.parse(a.start_time) - Date.parse(b.start_time)).slice(0, 3)); })
      .catch(() => { if (live) setNext([]); });
    return () => { live = false; };
  }, []);
  const firstName = user.full_name.trim().split(/\s+/).slice(-1)[0];
  return <>
    <section className="home-hero">
      <div>
        <h1>Xin chào, {firstName}</h1>
        <p>{venue ? `${venue.name} mở cửa ${venue.opening_time ?? '06:00'}–${venue.closing_time ?? '23:00'}. Chọn giờ trống và đặt cọc bằng QR trong vài bước.` : 'Chọn giờ trống và đặt cọc bằng QR trong vài bước.'}</p>
      </div>
      <a className="home-cta" href="#/bookings">Đặt sân ngay →</a>
    </section>

    <section className="home-section">
      <div className="home-section-head"><h2>Trận sắp tới của bạn</h2><a href="#/my-bookings">Xem tất cả</a></div>
      {next === null ? <p className="home-muted">Đang tải…</p> : next.length === 0
        ? <div className="home-empty"><p>Bạn chưa có lịch đá nào sắp tới.</p><a className="account-primary-button" href="#/bookings">Tìm giờ trống</a></div>
        : <div className="home-games">{next.map(b => {
          const hold = b.status === 'PENDING_HOLD';
          const due = hold ? b.deposit_amount : b.outstanding_amount;
          return <a key={b.booking_id} className={`home-game${hold ? ' is-hold' : ''}`} href={bookingHash(b.booking_id)}>
            <div className="home-game-time"><strong>{timeVN(b.start_time)}</strong><small>{dayLabel(b.start_time)}</small></div>
            <div className="home-game-info"><strong>{b.pitch_name ?? `Sân #${b.pitch_id}`}</strong>
              <small>{hold ? 'Đang giữ sân, cần đặt cọc' : b.outstanding_amount === '0.00' ? 'Đã thanh toán đủ' : 'Đã xác nhận'}</small></div>
            <div className="home-game-money">{due && due !== '0.00' ? <><small>{hold ? 'Cọc cần trả' : 'Trả tại sân'}</small><strong>{moneyVN(due)}</strong></> : null}</div>
            <span className="home-game-go">{hold ? 'Đặt cọc →' : 'Xem →'}</span>
          </a>;
        })}</div>}
    </section>

    <VenueContact venue={venue} />

    <section className="home-links">
      <a href="#/my-bookings"><strong>Lịch đã đặt</strong><span>Trạng thái, tiền đã trả và còn phải trả.</span></a>
      <a href="#/matchmaking"><strong>Đá cùng đội</strong><span>Tìm đối thủ, tuyển thêm người cho đội.</span></a>
      <a href="#/teams"><strong>Đội bóng của tôi</strong><span>Thành viên và yêu cầu tham gia đội.</span></a>
      <a href="#/profile"><strong>Hồ sơ cá nhân</strong><span>Tên, số điện thoại, mật khẩu.</span></a>
    </section>
  </>;
}
