import { useEffect, useState } from 'react';
import type { RevenueReport } from '../../types/api';
import type { TransactionList } from '../../services/huyApi';
import { getRevenue, getTransactions, dateVN, moneyVN, todayVN } from '../../services/huyApi';
import { Banner, Button, Card, Empty, Field, Head, Status, Warning, dateAfter } from '../../features/field-management/ui';

export function AdminRevenuePage() {
  const [from, setFrom] = useState(dateAfter(-7));
  const [to, setTo] = useState(todayVN());
  const [period, setPeriod] = useState<'day' | 'month' | 'year'>('day');
  const [report, setReport] = useState<RevenueReport | null>(null);
  const [transactions, setTransactions] = useState<TransactionList | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [rev, setRev] = useState(0);
  useEffect(() => {
    let alive = true; setBusy(true); setError(null);
    Promise.all([getRevenue(from, to, period), getTransactions(from, to)]).then(([r, t]) => { if (alive) { setReport(r); setTransactions(t); } })
      .catch(e => { if (alive) setError(e); }).finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [rev]);
  const highest = Math.max(1, ...(report?.items.map(x => Number(x.net_receipts)) ?? []));
  return <>
    <Head kicker="ADMIN / 04" title="Doanh thu & giao dịch" description="Doanh thu là tiền thực thu trừ tiền đã hoàn thành công; không cộng giá booking chưa thu." />
    <Warning error={error}/>
    <Card><form className="huy-filter-form" onSubmit={e => { e.preventDefault(); if (from > to) { setError(new Error('Ngày bắt đầu phải không sau ngày kết thúc.')); return; } setRev(n => n + 1); }}>
      <Field label="Từ ngày"><input type="date" value={from} max={to} onChange={e => setFrom(e.target.value)}/></Field>
      <Field label="Đến ngày"><input type="date" value={to} min={from} onChange={e => setTo(e.target.value)}/></Field>
      <Field label="Phân nhóm"><select value={period} onChange={e => setPeriod(e.target.value as typeof period)}><option value="day">Theo ngày</option><option value="month">Theo tháng</option><option value="year">Theo năm</option></select></Field>
      <Button type="submit" disabled={busy}>{busy ? 'Đang tải…' : 'Xem báo cáo'}</Button>
    </form></Card>
    {report && <><div className="huy-metric-grid"><Card><small>TỔNG THỰC THU</small><strong>{moneyVN(report.totals.gross_receipts)}</strong><p>Tiền đã xác nhận thu</p></Card><Card><small>HOÀN THÀNH CÔNG</small><strong>{moneyVN(report.totals.refunds)}</strong><p>Khoản hoàn thực tế</p></Card><Card className="huy-metric-highlight"><small>DOANH THU RÒNG</small><strong>{moneyVN(report.totals.net_receipts)}</strong><p>Thực thu − hoàn tiền</p></Card></div>
      <Card><h2>Biểu đồ doanh thu ròng</h2>{report.items.length === 0 ? <Empty>Chưa có giao dịch được xác nhận trong khoảng này.</Empty> : <div className="huy-chart">{report.items.map(item => <div key={item.period_start} className="huy-chart-row"><span>{item.period_start}</span><div className="huy-chart-track"><div className="huy-chart-fill" style={{ width: `${Math.max(0, Math.min(100, Number(item.net_receipts) / highest * 100))}%` }}/></div><strong>{moneyVN(item.net_receipts)}</strong></div>)}</div>}</Card>
    </>}
    <Card><div className="huy-flex"><h2>Lịch sử giao dịch</h2><small className="huy-muted">Dữ liệu gần đây; có thể phân trang khi API sẵn sàng</small></div>
      {!transactions || transactions.data.length === 0 ? <Empty>Chưa có giao dịch.</Empty> : <div className="huy-table-wrap"><table><thead><tr><th>Mã</th><th>Booking</th><th>Phương thức</th><th>Loại giao dịch</th><th>Số tiền</th><th>Trạng thái</th><th>Thời điểm thu</th></tr></thead><tbody>{transactions.data.map(t => <tr key={t.payment_id}><td>#{t.payment_id}</td><td>{t.booking_id ? `#${t.booking_id}` : '—'}</td><td>{t.payment_method}</td><td>{t.payment_type === 'REFUND' ? 'Hoàn tiền' : t.payment_type === 'BOOKING_DEPOSIT' ? 'Tiền cọc' : 'Tiền còn lại'}</td><td><strong>{moneyVN(t.amount)}</strong></td><td><Status state={t.status}/></td><td>{t.paid_at ? dateVN(t.paid_at) : '—'}</td></tr>)}</tbody></table></div>}
    </Card>
    <Banner>Ngày trên biểu đồ dựa trên thời điểm thực thu (paid_at), không phải ngày thi đấu. Dữ liệu demo không phản ánh doanh thu thực tế.</Banner>
  </>;
}
