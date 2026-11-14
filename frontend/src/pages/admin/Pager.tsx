import { Button } from '../../features/field-management/ui';

/** Previous / next pager over the API's page, page_size and total. */
export function Pager({ page, pageSize, total, onPage, disabled = false }: {
  page: number; pageSize: number; total: number; onPage: (page: number) => void; disabled?: boolean;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return total ? <p className="huy-muted">{total} kết quả</p> : null;
  const first = (page - 1) * pageSize + 1;
  return <div className="huy-flex huy-pager">
    <span className="huy-muted">{first}–{Math.min(page * pageSize, total)} / {total} · Trang {page}/{pages}</span>
    <span className="huy-actions">
      <Button variant="outline" disabled={disabled || page <= 1} onClick={() => onPage(page - 1)}>‹ Trước</Button>
      <Button variant="outline" disabled={disabled || page >= pages} onClick={() => onPage(page + 1)}>Sau ›</Button>
    </span>
  </div>;
}
