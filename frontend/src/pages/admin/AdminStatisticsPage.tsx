import { useEffect, useState } from 'react';
import type { BookingStatistics } from '../../types/api';
import { getBookingStatistics, todayVN } from '../../services/fieldApi';
import { Banner, Button, Card, Empty, Field, Head, Warning, dateAfter } from '../../features/field-management/ui';

const percent = (part: number, whole: number) => whole ? `${Math.round(part / whole * 1000) / 10}%` : '0%';

/** Booking activity by kick-off date: fill rate per pitch, peak hours and how many bookings fall through. */
export function AdminStatisticsPage() {
  const [from, setFrom] = useState(dateAfter(-30));
  const [to, setTo] = useState(todayVN());
  const [range, setRange] = useState({ from, to });
  const [stats, setStats] = useState<BookingStatistics | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true; setBusy(true); setError(null);
    getBookingStatistics(range.from, range.to).then(s => { if (alive) setStats(s); })
      .catch(e => { if (alive) setError(e); }).finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [range]);
  const total = stats?.total_bookings ?? 0;
  const lost = (stats?.cancelled_bookings ?? 0) + (stats?.expired_bookings ?? 0);
  const peak = stats?.peak_hours.slice(0, 8) ?? [];
  const peakMax = Math.max(1, ...peak.map(h => h.booking_count));

  return <>
    <Head title="Thống kê đặt sân" description="Tỉ lệ lấp đầy từng sân, giờ cao điểm và tỉ lệ hủy theo ngày đá." />
    <Warning error={error} />
    <Card><form className="huy-filter-form" onSubmit={e => { e.preventDefault(); if (from > to) { setError(new Error('Ngày bắt đầu phải không sau ngày kết thúc.')); return; } setRange({ from, to }); }}>
      <Field label="Từ ngày"><input type="date" value={from} max={to} onChange={e => setFrom(e.target.value)} /></Field>
      <Field label="Đến ngày"><input type="date" value={to} min={from} onChange={e => setTo(e.target.value)} /></Field>
      <Button type="submit" disabled={busy}>{busy ? 'Đang tải…' : 'Xem thống kê'}</Button>
    </form></Card>
    {stats && <>
      <div className="huy-metric-grid">
        <Card><small>Tổng booking</small><strong>{total}</strong><p>{stats.confirmed_bookings} đã xác nhận ({percent(stats.confirmed_bookings, total)})</p></Card>
        <Card><small>Hủy hoặc hết hạn</small><strong>{percent(lost, total)}</strong><p>{stats.cancelled_bookings} hủy · {stats.expired_bookings} hết hạn giữ sân</p></Card>
        <Card className="huy-metric-highlight"><small>Có hoàn tiền</small><strong>{stats.refunded_booking_count}</strong><p>Booking đã hoàn tiền thành công</p></Card>
      </div>
      <div className="huy-two-col">
        <Card><h2>Tỉ lệ lấp đầy theo sân</h2>{stats.by_pitch.length === 0 ? <Empty>Chưa có sân.</Empty> : <div className="huy-chart">
          {stats.by_pitch.map(p => <div key={p.pitch_id} className="huy-chart-row"><span>{p.pitch_name}</span>
            <div className="huy-chart-track"><div className="huy-chart-fill" style={{ width: `${Math.min(100, p.utilization_rate * 100)}%` }} /></div>
            <strong>{Math.round(p.utilization_rate * 1000) / 10}% · {p.total_bookings} lượt</strong></div>)}
        </div>}<p className="huy-muted">Giờ đã đá của booking xác nhận / giờ mở cửa đã qua (06:00–23:00), trừ giờ bảo trì. Lịch tương lai chưa tính.</p></Card>
        <Card><h2>Giờ cao điểm</h2>{peak.length === 0 ? <Empty>Chưa có booking xác nhận.</Empty> : <div className="huy-chart">
          {peak.map(h => <div key={h.hour} className="huy-chart-row"><span>{String(h.hour).padStart(2, '0')}:00</span>
            <div className="huy-chart-track"><div className="huy-chart-fill" style={{ width: `${h.booking_count / peakMax * 100}%` }} /></div>
            <strong>{h.booking_count} lượt</strong></div>)}
        </div>}<p className="huy-muted">Theo giờ bắt đầu (giờ Việt Nam) của booking đã xác nhận.</p></Card>
      </div>
    </>}
    <Banner>Thống kê theo ngày đá ({range.from} → {range.to}), không phải ngày đặt. Lịch bảo trì không tính là booking.</Banner>
  </>;
}
