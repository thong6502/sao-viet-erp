// Màn CÔNG NỢ PHẢI THU — shell (tách từ pages/AccountingReceivablesPage.tsx).
// Giữ ở đây: state + `load()` + dải KPI + toolbar lọc + bảng khách hàng + chỗ mount drawer.
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type ReceivableCustomerRow,
  type ReceivablesSummary,
} from "../../../api/client";
import { useAuth } from "../../../auth/useAuth";
import type { NavigateFn } from "../../../components/AppShell";
import { Button } from "../../../components/Button";
import { Icon } from "../../../components/Icons";
import { money } from "../../../utils/format";
import { AgingStrip } from "../components/AgingStrip";
import { ReceivablesDrawer } from "./components/ReceivablesDrawer";
import { LIST_FILTERS, PAGE_SIZE } from "./shared/constants";
import { kpi } from "./shared/helpers";
import type { ListFilter } from "./shared/types";
import "../../accounting.css";
import "../../payables.css";
import "../../purchase.css";

export function AccountingReceivablesPage({
  navigate,
  eventTick = 0,
}: {
  navigate: NavigateFn;
  eventTick?: number;
}) {
  const { token } = useAuth();
  const [summary, setSummary] = useState<ReceivablesSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ListFilter>("all");
  // Rổ tuổi đang lọc — xem chú thích cùng tên ở màn Công nợ phải trả, hai màn một luật.
  const [roTuoi, setRoTuoi] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [sentQ, setSentQ] = useState("");
  const [open, setOpen] = useState<ReceivableCustomerRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.accounting
      .receivables(token, { q: sentQ, filter, aging: roTuoi, page, size: PAGE_SIZE })
      .then((data) => {
        setSummary(data);
        if (data.page !== page) setPage(data.page);
      })
      .catch((cause) => {
        setSummary(null);
        setError(cause instanceof ApiError ? cause.message : "Không tải được công nợ phải thu.");
      })
      .finally(() => setLoading(false));
  }, [token, sentQ, filter, roTuoi, page]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (eventTick <= 0) return;
    load();
  }, [eventTick, load]);

  useEffect(() => {
    const timer = setTimeout(() => setSentQ(q), 350);
    return () => clearTimeout(timer);
  }, [q]);

  const known = !loading && !error && summary != null;
  const rows = summary?.items ?? [];

  const months = summary?.period_months ?? 3;

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kế toán</p>
        <h1 className="md-page__title">Công nợ phải thu</h1>
        <p className="md-page__sub">
          Theo dõi công nợ phát sinh từ hóa đơn bán đã ghi nhận và phiếu thu.
        </p>
      </header>

      {error && (
        <div className="banner banner--error" role="alert">
          {error} — các con số bên dưới đang để trống, không phải bằng 0.
        </div>
      )}

      <section className="pay-kpibar" aria-label="Tổng quan công nợ phải thu">
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--steel"><Icon name="calculator" size={14} /></span>
          <b className="pay-kpibar__val">{kpi(summary?.total_due, known)}</b>
          <span className="pay-kpibar__label">Tổng phải thu</span>
        </div>
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--danger"><Icon name="alert" size={14} /></span>
          <b className="pay-kpibar__val pay-kpibar__val--danger">{kpi(summary?.overdue_amount, known)}</b>
          <span className="pay-kpibar__label">Quá hạn</span>
        </div>
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--ok"><Icon name="fileCheck" size={14} /></span>
          <b className="pay-kpibar__val">{kpi(summary?.received_in_period, known)}</b>
          <span className="pay-kpibar__label">Đã thu ({months} tháng)</span>
        </div>
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--warn"><Icon name="shield" size={14} /></span>
          <b className="pay-kpibar__val">{known ? summary?.vuot_han_muc_count ?? 0 : "—"}</b>
          <span className="pay-kpibar__label">Khách vượt hạn mức</span>
        </div>
      </section>
      {/* DẢI PHÂN TUỔI NỢ — server gom rổ từ lâu nhưng tới 29/08/2026 chưa màn nào vẽ ra, nên
          khoản trễ 3 ngày và khoản trễ 90 ngày cùng nằm trong một ô "Quá hạn". Đặt DƯỚI dải KPI
          và TRÊN thanh công cụ: KPI trả lời "tổng bao nhiêu", dải này trả lời "nặng tới đâu",
          rồi mới tới chỗ lọc/tìm. */}
      <AgingStrip
        buckets={summary?.aging ?? []}
        dangChon={roTuoi}
        onChon={(khoa) => {
          setRoTuoi(khoa);
          setPage(1);
        }}
      />


      <section className="acct-toolbar">
        <form className="md-page__search" onSubmit={(event) => event.preventDefault()}>
          <input
            className="input"
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
            placeholder="Tìm khách hàng..."
          />
        </form>
        <div className="pay-pills">
          {LIST_FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`pay-pill${filter === item.id ? " pay-pill--on" : ""}`}
              onClick={() => {
                setFilter(item.id);
                setPage(1);
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      <section className="card md-page__tablewrap pay-card ar-summary-table">
        <table className="md-page__table pay-table">
          <thead>
            <tr>
              {/* KHÔNG còn cột "Xem": bấm vào DÒNG mở drawer công nợ, mọi thao tác (Thu tiền từng
                  hóa đơn) nằm TRONG drawer (24/08/2026 — gộp thao tác vào bản ghi). */}
              <th>Khách hàng</th>
              <th className="acct-count-cell">HĐ còn nợ</th>
              <th className="acct-amount-cell">Tổng phải thu</th>
              <th className="acct-amount-cell">Quá hạn</th>
              <th className="acct-amount-cell">Đã thu</th>
              <th className="acct-amount-cell">Hạn mức</th>
              <th>Vượt hạn mức</th>
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="purchase__skeleton-row">
                  <td><div className="purchase__skeleton-bar" style={{ width: "150px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "70px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "110px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "80px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "100px" }} /></td>
                </tr>
              ))}
            {!loading && rows.length === 0 && <tr><td colSpan={7}>Chưa có khách hàng còn công nợ phải thu phù hợp.</td></tr>}
            {!loading && rows.map((row) => (
              <tr
                key={row.customer_id ?? `none-${row.customer_name}`}
                onClick={() => row.customer_id != null && setOpen(row)}
              >
                {/* CỐ Ý KHÔNG hiện "Đã ghi hóa đơn" ở đây (chủ 21/08/2026: "để làm gì, nó có
                    tác dụng gì cả"). Nó LUÔN bằng "Đã thu" + "Tổng phải thu" — hai cột đã nằm
                    ngay cạnh: mỗi hoá đơn có `remaining = amount − received`, cộng theo khách là
                    ra đẳng thức đó, không ngoại lệ. Bày thêm một số suy được là bắt người ta đọc
                    ba số để hiểu hai. */}
                <td><strong>{row.customer_name}</strong></td>
                <td className="acct-count-cell">{row.invoice_count}</td>
                <td className="acct-amount-cell"><strong>{money(row.total_due)}</strong></td>
                <td className={`acct-amount-cell${row.overdue_amount > 0 ? " pay-cell--danger" : ""}`}>{money(row.overdue_amount)}</td>
                <td className="acct-amount-cell">{money(row.received_amount)}</td>
                <td className="acct-amount-cell">{row.credit_limit > 0 ? money(row.credit_limit) : "—"}</td>
                <td>
                  {row.vuot_han_muc ? (
                    <span className="pay-badge pay-badge--danger">
                      <i className="pay-badge__dot" />
                      {money(row.vuot_bao_nhieu)}
                    </span>
                  ) : (
                    <span className="pay-cell--zero">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && (
          <div className="md-page__pager">
            <span className="md-page__muted">
              Tổng {summary?.total ?? 0} khách hàng
              {(summary?.pages ?? 1) > 1 ? ` · Trang ${summary?.page}/${summary?.pages}` : ""}
            </span>
            {(summary?.pages ?? 1) > 1 && (
              <div className="md-page__pager-btns">
                <Button variant="ghost" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
                  Trước
                </Button>
                <Button
                  variant="ghost"
                  disabled={page >= (summary?.pages ?? 1) || loading}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Sau
                </Button>
              </div>
            )}
          </div>
        )}
      </section>

      {open?.customer_id != null && (
        <ReceivablesDrawer
          row={open}
          token={token}
          navigate={navigate}
          eventTick={eventTick}
          onChanged={load}
          onClose={() => setOpen(null)}
        />
      )}
    </main>
  );
}
