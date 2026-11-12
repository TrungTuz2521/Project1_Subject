import { useEffect, useState } from 'react';
import type { AdminBooking, AdminDashboard } from '../../types/api';
import { getAdminDashboard, dateVN, moneyVN } from '../../services/huyApi';
import { Button, Card, Empty, Head, Warning, countdown, useNow } from '../../features/field-management/ui';
import { CheckInDesk } from './CheckInDesk';

const who = (b: AdminBooking) => b.customer?.full_name ?? `Khách #${b.user_id}`;
const where = (b: AdminBooking) => b.pitch_name ?? `Sân #${b.pitch_id}`;
/** Scoreboard figures drop the currency sign; the label says it is money. */
const amount = (value: string) => new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 }).format(Number(value));

/** The counter's to-do list: the scoreboard says how much is waiting, the queues say who. */
export function AdminDashboardPage({ settlement }: { settlement: (id: number) => void }) {
  const [data, setData] = useState<AdminDashboard | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [revision, setRevision] = useState(0);
  const now = useNow();
  useEffect(() => {
    let alive = true;
    const load = () => getAdminDashboard().then(d => { if (alive) { setData(d); setError(null); } }).catch(e => { if (alive) setError(e); });
    void load();
    const timer = window.setInterval(() => { if (document.visibilityState !== 'hidden') void load(); }, 30_000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [revision]);

  return <>
    <Head title="Hôm nay" description="Đón khách, thu tiền và các việc đang chờ trong ngày. Trang tự cập nhật mỗi 30 giây."
      aside={<Button variant="outline" onClick={() => setRevision(n => n + 1)}>Làm mới</Button>} />
    <Warning error={error} />
    {data?.background_jobs?.lagging && <div className="adm-job-alert" role="alert">
      <strong>Tiến trình nền (scheduler) có vẻ chưa chạy.</strong>
      <span>Đang tồn {[data.background_jobs.expired_holds && `${data.background_jobs.expired_holds} lượt giữ sân quá hạn`,
        data.background_jobs.expired_requests && `${data.background_jobs.expired_requests} yêu cầu tìm kèo quá hạn`,
        data.background_jobs.unsent_emails && `${data.background_jobs.unsent_emails} email chưa gửi`].filter(Boolean).join(', ')}.
        Khi scheduler không chạy thì sân giữ quá hạn không được mở lại, không hoàn tiền tự động và không gửi email. Chạy: <code>python -m flask --app app:create_app scheduler --with-matchmaking --with-email</code></span>
    </div>}
    {!data ? <Empty>{error ? 'Chưa tải được dữ liệu. Bấm Làm mới để thử lại.' : 'Đang tải…'}</Empty> : <>
      <section className="adm-board" aria-label="Tóm tắt hôm nay">
        <div className="adm-board-cell">
          <span className="adm-board-label">Doanh thu ròng hôm nay (VND)</span>
          <span className="adm-board-value">{amount(data.revenue_today.net_receipts)}</span>
          <span className="adm-board-sub">Thu {moneyVN(data.revenue_today.gross_receipts)}, hoàn {moneyVN(data.revenue_today.refunds)}</span>
        </div>
        <a className={`adm-board-cell${data.pending_holds.count ? ' yellow' : ''}`} href="#/admin/bookings">
          <span className="adm-board-label">Chờ cọc online</span>
          <span className="adm-board-value">{data.pending_holds.count}</span>
          <span className="adm-board-sub">Khách online đang thanh toán</span>
        </a>
        <a className={`adm-board-cell${data.pending_refunds.count ? ' red' : ''}`} href="#/admin/bookings">
          <span className="adm-board-label">Cần hoàn tiền</span>
          <span className="adm-board-value">{data.pending_refunds.count}</span>
          <span className="adm-board-sub">{moneyVN(data.pending_refunds.amount)}</span>
        </a>
        <a className={`adm-board-cell${data.ended_unpaid.count ? ' yellow' : ''}`} href="#/admin/balance">
          <span className="adm-board-label">Đá xong, chưa thu đủ</span>
          <span className="adm-board-value">{data.ended_unpaid.count}</span>
          <span className="adm-board-sub">Thiếu {moneyVN(data.ended_unpaid.outstanding_amount)}</span>
        </a>
        <div className="adm-board-cell">
          <span className="adm-board-label">Trận hôm nay</span>
          <span className="adm-board-value">{data.today_games.count}</span>
          <span className="adm-board-sub">Đã xác nhận</span>
        </div>
      </section>

      <CheckInDesk items={data.today_games.items} total={data.today_games.count} onChanged={() => setRevision(n => n + 1)} settlement={settlement} />

      <div className="huy-two-col">
        <Card><div className="adm-queue-head"><h2>Khách online đang chờ cọc</h2><Button variant="outline" onClick={() => { window.location.hash = '/admin/bookings'; }}>Mở lịch sân</Button></div>
          {data.pending_holds.items.length === 0 ? <Empty>Không có booking online nào đang chờ cọc.</Empty> : <div className="huy-booking-list">
            {data.pending_holds.items.map(b => <div key={b.booking_id} className="huy-booking-item">
              <span><b>{who(b)}</b><small>{where(b)}, {dateVN(b.start_time)}</small><small>{b.customer?.phone ?? 'Chưa có số điện thoại'}</small></span>
              <strong className="huy-timer" title="Thời gian giữ sân còn lại">{countdown(b.hold_expires_at, now)}</strong></div>)}</div>}
        </Card>
        <Card><div className="adm-queue-head"><h2>Đá xong, chưa thu đủ</h2><Button variant="outline" onClick={() => { window.location.hash = '/admin/balance'; }}>Thu tiền</Button></div>
          {data.ended_unpaid.items.length === 0 ? <Empty>Các trận đã đá đều đã thu đủ tiền.</Empty> : <div className="huy-booking-list">
            {data.ended_unpaid.items.map(b => <button type="button" key={b.booking_id} className="huy-booking-item" onClick={() => settlement(b.booking_id)}>
              <span><b>{who(b)}</b><small>{where(b)}, {dateVN(b.start_time)}</small></span>
              <span><small>Còn thiếu</small><b>{moneyVN(b.balance?.outstanding_amount ?? '0')}</b></span></button>)}</div>}
        </Card>
      </div>

    </>}
  </>;
}
