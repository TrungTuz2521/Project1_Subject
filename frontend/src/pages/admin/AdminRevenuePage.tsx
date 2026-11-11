import { useEffect, useState } from 'react';
import type { RevenueReport } from '../../types/api';
import type { TransactionList } from '../../services/huyApi';
import { exportRevenue, getRevenue, getTransactions, dateVN, moneyVN, todayVN } from '../../services/huyApi';
import { Pager } from './Pager';

const PAGE_SIZE = 20;
const methodNames: Record<string, string> = { CASH: 'Tiền mặt', BANK_TRANSFER: 'Chuyển khoản', VNPAY: 'VNPay', MOMO: 'MoMo' };
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
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState(false);
  // Report and table use the range last submitted, so paging never mixes two ranges.
  const [range, setRange] = useState({ from, to, period });
  useEffect(() => {
    let alive = true; setBusy(true); setError(null);
    getRevenue(range.from, range.to, range.period).then(r => { if (alive) setReport(r); })
      .catch(e => { if (alive) setError(e); }).finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [rev, range]);
  useEffect(() => {
    let alive = true;
    getTransactions(range.from, range.to, page, PAGE_SIZE).then(t => { if (alive) setTransactions(t); }).catch(e => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [rev, range, page]);
  async function download() {
    setExporting(true); setError(null);
    try { await exportRevenue(range.from, range.to, range.period); } catch (e) { setError(e); } finally { setExporting(false); }
  }
  const highest = Math.max(1, ...(report?.items.map(x => Number(x.net_receipts)) ?? []));
  return <>
    <Head title="Doanh thu & giao dịch" description="Doanh thu là tiền thực thu trừ tiền đã hoàn thành công; không cộng giá booking chưa thu." />
    <Warning error={error}/>
    <Card><form className="huy-filter-form" onSubmit={e => { e.preventDefault(); if (from > to) { setError(new Error('Ngày bắt đầu phải không sau ngày kết thúc.')); return; } setPage(1); setRange({ from, to, period }); setRev(n => n + 1); }}>
      <Field label="Từ ngày"><input type="date" value={from} max={to} onChange={e => setFrom(e.target.value)}/></Field>
      <Field label="Đến ngày"><input type="date" value={to} min={from} onChange={e => setTo(e.target.value)}/></Field>
      <Field label="Phân nhóm"><select value={period} onChange={e => setPeriod(e.target.value as typeof period)}><option value="day">Theo ngày</option><option value="month">Theo tháng</option><option value="year">Theo năm</option></select></Field>
      <Button type="submit" disabled={busy}>{busy ? 'Đang tải…' : 'Xem báo cáo'}</Button>
      <Button variant="outline" disabled={exporting || busy} onClick={() => void download()}>{exporting ? 'Đang xuất…' : '⬇ Xuất Excel'}</Button>
    </form><p className="huy-muted">File Excel dùng khoảng {range.from} → {range.to} của báo cáo đang xem.</p></Card>
    {report && <><div className="huy-metric-grid"><Card><small>Tổng thực thu</small><strong>{moneyVN(report.totals.gross_receipts)}</strong><p>Tiền đã xác nhận thu</p></Card><Card><small>Đã hoàn cho khách</small><strong>{moneyVN(report.totals.refunds)}</strong><p>Khoản hoàn thực tế</p></Card><Card className="huy-metric-highlight"><small>Doanh thu ròng</small><strong>{moneyVN(report.totals.net_receipts)}</strong><p>Thực thu − hoàn tiền</p></Card></div>
      <Card><h2>Biểu đồ doanh thu ròng</h2>{report.items.length === 0 ? <Empty>Chưa có giao dịch được xác nhận trong khoảng này.</Empty> : <div className="huy-chart">{report.items.map(item => <div key={item.period_start} className="huy-chart-row"><span>{item.period_start}</span><div className="huy-chart-track"><div className="huy-chart-fill" style={{ width: `${Math.max(0, Math.min(100, Number(item.net_receipts) / highest * 100))}%` }}/></div><strong>{moneyVN(item.net_receipts)}</strong></div>)}</div>}</Card>
    </>}
    <Card><div className="huy-flex"><h2>Lịch sử giao dịch</h2><small className="huy-muted">{range.from} → {range.to}</small></div>
      {!transactions || transactions.data.length === 0 ? <Empty>Chưa có giao dịch.</Empty> : <div className="huy-table-wrap"><table><thead><tr><th>Mã</th><th>Booking</th><th>Phương thức</th><th>Loại giao dịch</th><th>Số tiền</th><th>Trạng thái</th><th>Thời điểm thu</th></tr></thead><tbody>{transactions.data.map(t => <tr key={t.payment_id}><td>#{t.payment_id}</td><td>{t.booking_id ? `#${t.booking_id}` : '—'}</td><td>{methodNames[t.payment_method] ?? t.payment_method}{t.transaction_code?.startsWith('SP') && t.transaction_code.length === 12 && <small className="huy-block">QR SePay</small>}</td><td>{t.payment_type === 'REFUND' ? 'Hoàn tiền' : t.payment_type === 'BOOKING_DEPOSIT' ? 'Tiền cọc' : 'Tiền còn lại'}</td><td><strong>{moneyVN(t.amount)}</strong></td><td><Status state={t.status}/>{t.is_demo&&<small className="huy-block">DEMO — không tính doanh thu</small>}</td><td>{t.paid_at ? dateVN(t.paid_at) : '—'}</td></tr>)}</tbody></table></div>}
      {transactions && <Pager page={page} pageSize={PAGE_SIZE} total={transactions.meta.total} onPage={setPage} />}
    </Card>
    <Banner>Ngày trên biểu đồ dựa trên thời điểm thực thu (paid_at), không phải ngày thi đấu. Dữ liệu demo không phản ánh doanh thu thực tế.</Banner>
  </>;
}
