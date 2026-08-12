import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type ReceivableCustomerRow,
  type ReceivablesDetail,
  type ReceivablesSummary,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import type { NavigateFn } from "../components/AppShell";
import { Button } from "../components/Button";
import { CodeLink } from "../components/CodeLink";
import { DetailModal } from "../components/DetailModal";
import { Icon } from "../components/Icons";
import { fmtDate, fmtDateTime, money } from "../utils/format";
import "./accounting.css";
import "./payables.css";
import "./purchase.css";

type ListFilter = "all" | "overdue" | "chua_han" | "vuot_han_muc";

const LIST_FILTERS: { id: ListFilter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "overdue", label: "Quá hạn" },
  { id: "chua_han", label: "Chưa tới hạn" },
  { id: "vuot_han_muc", label: "Vượt hạn mức" },
];

function kpi(value: number | undefined, known: boolean): string {
  return known && value != null ? money(value) : "—";
}

function methodText(value: string): string {
  return value === "bank_transfer" ? "Chuyển khoản" : "Tiền mặt";
}

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
  const [q, setQ] = useState("");
  const [sentQ, setSentQ] = useState("");
  const [open, setOpen] = useState<ReceivableCustomerRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.accounting
      .receivables(token, sentQ)
      .then(setSummary)
      .catch((err) => {
        setSummary(null);
        setError(
          err instanceof ApiError
            ? err.message
            : "Không tải được công nợ phải thu.",
        );
      })
      .finally(() => setLoading(false));
  }, [token, sentQ]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (eventTick <= 0) return;
    load();
  }, [eventTick, load]);

  useEffect(() => {
    const t = setTimeout(() => setSentQ(q), 350);
    return () => clearTimeout(t);
  }, [q]);

  const known = !loading && !error && summary != null;
  const rows = useMemo(() => {
    const items = summary?.items ?? [];
    return items.filter((row) => {
      if (filter === "overdue") return row.overdue_amount > 0;
      if (filter === "chua_han") return row.no_han_amount > 0;
      if (filter === "vuot_han_muc") return row.vuot_han_muc;
      return true;
    });
  }, [summary, filter]);

  const months = summary?.period_months ?? 3;

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kế toán</p>
        <h1 className="md-page__title">Công nợ phải thu</h1>
        <p className="md-page__sub">
          Theo dõi số tiền khách còn phải thanh toán từ đơn bán đã chốt và phiếu thu đã ghi nhận.
        </p>
      </header>

      {error && (
        <div className="banner banner--error" role="alert">
          {error} — các con số bên dưới đang để trống, không phải bằng 0.
        </div>
      )}

      <section className="pay-kpibar" aria-label="Tổng quan công nợ phải thu">
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--steel">
            <Icon name="calculator" size={14} />
          </span>
          <b className="pay-kpibar__val">{kpi(summary?.total_due, known)}</b>
          <span className="pay-kpibar__label">Tổng phải thu</span>
        </div>
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--danger">
            <Icon name="alert" size={14} />
          </span>
          <b className="pay-kpibar__val pay-kpibar__val--danger">
            {kpi(summary?.overdue_amount, known)}
          </b>
          <span className="pay-kpibar__label">Quá hạn</span>
        </div>
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--ok">
            <Icon name="fileCheck" size={14} />
          </span>
          <b className="pay-kpibar__val">{kpi(summary?.received_in_period, known)}</b>
          <span className="pay-kpibar__label">Đã thu ({months} tháng)</span>
        </div>
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--warn">
            <Icon name="shield" size={14} />
          </span>
          <b className="pay-kpibar__val">
            {known ? summary?.vuot_han_muc_count ?? 0 : "—"}
          </b>
          <span className="pay-kpibar__label">Khách vượt hạn mức</span>
        </div>
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__label">
            {known ? `chốt ${fmtDateTime(summary?.as_of)}` : "chưa chốt được"}
          </span>
        </div>
      </section>

      <section className="acct-toolbar">
        <form className="md-page__search" onSubmit={(event) => event.preventDefault()}>
          <input
            className="input"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Tìm khách hàng..."
          />
        </form>
        <div className="pay-pills">
          {LIST_FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`pay-pill${filter === item.id ? " pay-pill--on" : ""}`}
              onClick={() => setFilter(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      <section className="card md-page__tablewrap pay-card">
        <table className="md-page__table pay-table">
          <thead>
            <tr>
              <th>Khách hàng</th>
              <th>Đơn còn nợ</th>
              <th>Tổng phải thu</th>
              <th>Quá hạn</th>
              <th>Đã thu</th>
              <th>Hạn mức</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7}>Đang tải...</td>
              </tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={7}>Chưa có khách hàng còn công nợ phải thu phù hợp.</td>
              </tr>
            )}
            {!loading &&
              rows.map((row) => (
                <tr key={row.customer_id ?? `none-${row.customer_name}`}>
                  <td>
                    <strong>{row.customer_name}</strong>
                    {row.payment_term_days == null ? (
                      <small>Chưa đặt số ngày công nợ</small>
                    ) : (
                      <small>Hạn {row.payment_term_days} ngày</small>
                    )}
                  </td>
                  <td>{row.order_count}</td>
                  <td><strong>{money(row.total_due)}</strong></td>
                  <td className={row.overdue_amount > 0 ? "pay-cell--danger" : ""}>
                    {money(row.overdue_amount)}
                  </td>
                  <td>{money(row.received_in_period)}</td>
                  <td>
                    {row.credit_limit > 0 ? money(row.credit_limit) : "—"}
                    {row.vuot_han_muc && (
                      <small className="pay-cell--danger">Vượt {money(row.vuot_bao_nhieu)}</small>
                    )}
                  </td>
                  <td>
                    <Button
                      variant="ghost"
                      disabled={row.customer_id == null}
                      onClick={() => setOpen(row)}
                    >
                      Chi tiết
                    </Button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </section>

      {open?.customer_id != null && (
        <ReceivablesDrawer
          row={open}
          token={token}
          navigate={navigate}
          onClose={() => setOpen(null)}
        />
      )}
    </main>
  );
}

function ReceivablesDrawer({
  row,
  token,
  navigate,
  onClose,
}: {
  row: ReceivableCustomerRow;
  token: string | null;
  navigate: NavigateFn;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<ReceivablesDetail | null>(null);
  const [allHistory, setAllHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || row.customer_id == null) return;
    setError(null);
    api.accounting
      .receivablesDetail(token, row.customer_id, allHistory)
      .then(setDetail)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Không tải được chi tiết công nợ."),
      );
  }, [token, row.customer_id, allHistory]);

  return (
    <DetailModal
      kicker="Công nợ phải thu"
      title={row.customer_name}
      subtitle={detail ? `Còn phải thu ${money(detail.total_due)}` : undefined}
      badge={
        detail?.vuot_han_muc ? (
          <span className="acct-voucher-status acct-voucher-status--waiting">
            Vượt hạn mức
          </span>
        ) : undefined
      }
      onClose={onClose}
    >
      {error && <div className="banner banner--error">{error}</div>}
      {!detail && !error && <p>Đang tải chi tiết...</p>}
      {detail && (
        <>
          <dl className="purchase__facts">
            <div>
              <dt>Tổng còn phải thu</dt>
              <dd>{money(detail.total_due)}</dd>
            </div>
            <div>
              <dt>Quá hạn</dt>
              <dd>{money(detail.overdue_amount)}</dd>
            </div>
            <div>
              <dt>Đã thu ({detail.period_months} tháng)</dt>
              <dd>{money(detail.received_in_period)}</dd>
            </div>
            <div>
              <dt>Hạn mức</dt>
              <dd>{detail.credit_limit > 0 ? money(detail.credit_limit) : "—"}</dd>
            </div>
          </dl>

          <section className="pay-block">
            <div className="pay-block__head">
              <h3>Đơn còn phải thu</h3>
              <strong>{money(detail.total_due)}</strong>
            </div>
            <table className="pay-table">
              <thead>
                <tr>
                  <th>Đơn</th>
                  <th>Hạn thu</th>
                  <th>Giá trị</th>
                  <th>Đã thu</th>
                  <th>Còn phải thu</th>
                </tr>
              </thead>
              <tbody>
                {detail.items.length === 0 && (
                  <tr>
                    <td colSpan={5}>Khách hàng này không còn đơn phải thu.</td>
                  </tr>
                )}
                {detail.items.map((item) => (
                  <tr key={item.order_id}>
                    <td>
                      <CodeLink
                        code={item.order_code}
                        onOpen={() => navigate("don-hang-ban", { openOrderId: item.order_id })}
                      />
                      {item.chua_dat_han && <small>Chưa đặt hạn</small>}
                    </td>
                    <td>
                      {item.due_date ? fmtDate(item.due_date) : "—"}
                      {item.overdue_days > 0 && (
                        <small className="pay-cell--danger">Quá {item.overdue_days} ngày</small>
                      )}
                    </td>
                    <td>{money(item.total_amount)}</td>
                    <td>{money(item.received_amount)}</td>
                    <td><strong>{money(item.remaining_amount)}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="pay-block pay-block--ok">
            <div className="pay-block__head">
              <h3>Phiếu thu đã ghi nhận</h3>
              <strong>{money(detail.received_in_period)}</strong>
            </div>
            <table className="pay-table">
            <thead>
              <tr>
                <th>Phiếu thu</th>
                <th>Đơn</th>
                <th>Ngày thu</th>
                <th>Hình thức</th>
                <th>Số tiền</th>
              </tr>
            </thead>
            <tbody>
              {detail.paid.length === 0 && (
                <tr>
                  <td colSpan={5}>Chưa có phiếu thu trong kỳ đang xem.</td>
                </tr>
              )}
              {detail.paid.map((receipt) => (
                <tr key={receipt.receipt_id}>
                  <td>
                    <CodeLink
                      code={receipt.code}
                      onOpen={() => navigate("ke-toan-phieu-thu", { focusReceiptQuery: receipt.code })}
                    />
                    {receipt.doc_no && <small>Số {receipt.doc_no}</small>}
                  </td>
                  <td>{receipt.order_code ?? "—"}</td>
                  <td>{fmtDate(receipt.receipt_date)}</td>
                  <td>{methodText(receipt.receipt_method)}</td>
                  <td><strong>{money(receipt.amount)}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!detail.all_history && (
            <Button variant="ghost" onClick={() => setAllHistory(true)}>
              Xem lịch sử thu cũ hơn
            </Button>
          )}
          </section>
        </>
      )}
    </DetailModal>
  );
}
