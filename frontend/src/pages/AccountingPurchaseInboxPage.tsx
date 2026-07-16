import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type PurchaseRequestRow,
  type PurchaseRequestStatus,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import type { NavigateFn } from "../components/AppShell";
import { Button } from "../components/Button";
import { CodeLink } from "../components/CodeLink";
import { DetailModal } from "../components/DetailModal";
import { Icon } from "../components/Icons";
import { UNC_ENABLED } from "../constants/features";
import { fmtDate, money } from "../utils/format";
import { PaymentVoucherDialog } from "./PaymentVoucherDialog";
import "./accounting.css";
import "./purchase.css";

const PAGE_SIZE = 20;

const STATUS_META: Record<
  PurchaseRequestStatus,
  { label: string; tone: string }
> = {
  draft: { label: "Nháp", tone: "draft" },
  pending_approval: { label: "Chờ duyệt", tone: "pending" },
  approved: { label: "Đã duyệt", tone: "approved" },
  rejected: { label: "Từ chối", tone: "rejected" },
  purchased: { label: "Đã mua", tone: "purchased" },
  received: { label: "Đã nhận", tone: "received" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

const PAYMENT_META = {
  unpaid: { label: "Chưa thanh toán", tone: "unpaid" },
  partial: { label: "Thanh toán một phần", tone: "partial" },
  paid: { label: "Đã thanh toán", tone: "paid" },
} as const;

export function AccountingPurchaseInboxPage({
  navigate,
}: {
  navigate: NavigateFn;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canApprove = can("ke_toan", "approve");
  const openYcmh = (code: string) =>
    navigate("yeu-cau-mua-hang", { focusRequestCode: code });
  const [rows, setRows] = useState<PurchaseRequestRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("pending_approval");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [voucherMode, setVoucherMode] = useState<null | {
    purchase: PurchaseRequestRow;
    combined: boolean;
  }>(null);
  const [rejecting, setRejecting] = useState<PurchaseRequestRow | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.accounting
      .inbox(token, {
        q: q.trim() || undefined,
        status: statusFilter === "all" ? null : statusFilter,
        sort: "-created_at",
        page,
        size: PAGE_SIZE,
      })
      .then((response) => {
        setRows(response.items);
        setTotal(response.total);
        setSelectedId((current) =>
          current != null && response.items.some((row) => row.id === current)
            ? current
            : null,
        );
      })
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "Không tải được yêu cầu Kế toán.",
        ),
      )
      .finally(() => setLoading(false));
  }, [token, q, statusFilter, page]);

  useEffect(() => {
    load();
  }, [load]);

  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  );
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  /** Đóng popup rồi mới mở form — không chồng hai lớp cửa sổ. */
  function closeDetailThen(action: () => void) {
    setSelectedId(null);
    action();
  }

  async function reject() {
    if (!token || !rejecting) return;
    if (!rejectReason.trim()) {
      setError("Vui lòng nhập lý do từ chối.");
      return;
    }
    setBusy(`reject:${rejecting.id}`);
    try {
      await api.purchaseRequests.reject(
        token,
        rejecting.id,
        rejectReason.trim(),
      );
      setRejecting(null);
      setRejectReason("");
      load();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Không từ chối được phiếu mua hàng.",
      );
    } finally {
      setBusy(null);
    }
  }

  function actions(row: PurchaseRequestRow, compact = false) {
    return (
      <div className={`acct-actions${compact ? " acct-actions--compact" : ""}`}>
        {canApprove && row.status === "pending_approval" && (
          <>
            <Button
              type="button"
              variant="primary"
              onClick={() =>
                closeDetailThen(() =>
                  setVoucherMode({ purchase: row, combined: true }),
                )
              }
            >
              Duyệt & lập chứng từ
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() =>
                closeDetailThen(() => {
                  setRejecting(row);
                  setRejectReason("");
                })
              }
            >
              Từ chối
            </Button>
          </>
        )}
        {canApprove &&
          ["approved", "purchased", "received"].includes(row.status) &&
          row.available_amount > 0 && (
            <Button
              type="button"
              variant="primary"
              onClick={() =>
                closeDetailThen(() =>
                  setVoucherMode({ purchase: row, combined: false }),
                )
              }
            >
              Lập Phiếu chi
            </Button>
          )}
      </div>
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kế toán</p>
        <h1 className="md-page__title">Yêu cầu mua hàng</h1>
        <p className="md-page__sub">
          {UNC_ENABLED
            ? "Duyệt PMH Thu mua gửi đến và lập Phiếu chi hoặc Ủy nhiệm chi từ cùng một chứng từ nguồn."
            : "Duyệt PMH Thu mua gửi đến và lập Phiếu chi từ cùng một chứng từ nguồn."}
        </p>
      </header>

      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}

      <section className="acct-toolbar">
        <form
          className="md-page__search"
          onSubmit={(event) => {
            event.preventDefault();
            setPage(1);
            load();
          }}
        >
          <input
            className="input"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Tìm PMH, YCMH, nhà cung cấp..."
          />
          <Button type="submit" variant="ghost">
            Tìm
          </Button>
        </form>
        <select
          className="input acct-toolbar__select"
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
            setPage(1);
          }}
        >
          <option value="all">Tất cả trạng thái</option>
          {Object.entries(STATUS_META).map(([value, meta]) => (
            <option key={value} value={value}>
              {meta.label}
            </option>
          ))}
        </select>
      </section>

      <section className="card md-page__tablewrap acct-list">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã phiếu</th>
              <th>Trạng thái</th>
              <th>Nhà cung cấp</th>
              <th className="acct-amount-cell">Tổng PMH</th>
              <th>Thanh toán</th>
              <th>Ngày cần</th>
              <th className="acct-action-cell">Thao tác</th>
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
                <td colSpan={7}>Không có phiếu mua hàng phù hợp.</td>
              </tr>
            )}
            {!loading &&
              rows.map((row) => {
                const status = STATUS_META[row.status];
                const payment = PAYMENT_META[row.payment_status];
                return (
                  <tr
                    key={row.id}
                    className={
                      row.id === selected?.id ? "purchase__row--selected" : ""
                    }
                    onClick={() => setSelectedId(row.id)}
                  >
                    <td className="acct-code-cell">
                      <strong>{row.code}</strong>
                      <div className="purchase__source-codes">
                        {row.sources.map((source, index) => (
                          <span key={source.id}>
                            {index > 0 && ", "}
                            <CodeLink code={source.code} onOpen={openYcmh} />
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>
                      <span
                        className={`purchase__status purchase__status--${status.tone}`}
                      >
                        {status.label}
                      </span>
                    </td>
                    <td
                      className="acct-supplier-cell"
                      title={row.supplier_name ?? undefined}
                    >
                      {row.supplier_name || "—"}
                    </td>
                    <td className="acct-amount-cell">
                      <strong>{money(row.total_estimate)}</strong>
                    </td>
                    <td>
                      <span
                        className={`acct-payment-status acct-payment-status--${payment.tone}`}
                      >
                        {payment.label}
                      </span>
                      <small>{money(row.outstanding_amount)} còn lại</small>
                    </td>
                    <td className="acct-code-cell">
                      {fmtDate(row.needed_date)}
                    </td>
                    <td className="acct-action-cell">
                      <button
                        type="button"
                        className="acct-eye"
                        aria-label={`Xem chi tiết ${row.code}`}
                        title="Xem chi tiết"
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedId(row.id);
                        }}
                      >
                        <Icon name="eye" size={17} />
                      </button>
                    </td>
                  </tr>
                );
              })}
          </tbody>
        </table>
        <div className="md-page__pager">
          <span>{total} phiếu</span>
          <div>
            <Button
              variant="ghost"
              disabled={page <= 1}
              onClick={() => setPage((value) => value - 1)}
            >
              Trước
            </Button>
            <span>
              {page}/{totalPages}
            </span>
            <Button
              variant="ghost"
              disabled={page >= totalPages}
              onClick={() => setPage((value) => value + 1)}
            >
              Sau
            </Button>
          </div>
        </div>
      </section>

      {selected && (
        <DetailModal
          kicker="Chi tiết PMH"
          title={selected.code}
          badge={
            <span
              className={`purchase__status purchase__status--${STATUS_META[selected.status].tone}`}
            >
              {STATUS_META[selected.status].label}
            </span>
          }
          footer={actions(selected)}
          onClose={() => setSelectedId(null)}
        >
          <dl className="purchase__facts">
            <div>
              <dt>Nhà cung cấp</dt>
              <dd>{selected.supplier_name}</dd>
            </div>
            <div>
              <dt>Ngày cần hàng</dt>
              <dd>{fmtDate(selected.needed_date)}</dd>
            </div>
            <div>
              <dt>Người lập</dt>
              <dd>{selected.created_by_name || "—"}</dd>
            </div>
            <div>
              <dt>Gửi duyệt</dt>
              <dd>{fmtDate(selected.submitted_at)}</dd>
            </div>
            <div>
              <dt>Yêu cầu nguồn</dt>
              <dd>
                {selected.sources.map((source, index) => (
                  <span key={source.id}>
                    {index > 0 && ", "}
                    <CodeLink code={source.code} onOpen={openYcmh} />
                  </span>
                ))}
              </dd>
            </div>
            <div>
              <dt>Phòng ban nguồn</dt>
              <dd>
                {[
                  ...new Set(
                    selected.sources
                      .map((source) => source.requesting_department_name)
                      .filter(Boolean),
                  ),
                ].join(", ") || "—"}
              </dd>
            </div>
          </dl>
          <div className="acct-purpose">
            <span>Mục đích</span>
            <strong>{selected.purpose}</strong>
          </div>
          <div className="purchase__lines">
            {selected.lines.map((line) => (
              <div className="purchase__line" key={line.id}>
                <span>
                  <strong>{line.item_name}</strong>
                  <br />
                  <small>
                    {line.quantity.toLocaleString("vi-VN")} {line.unit} ·
                    VAT {line.vat_percent}%
                  </small>
                </span>
                <strong>{money(line.line_total)}</strong>
              </div>
            ))}
          </div>
          <div className="acct-payment-grid">
            <div>
              <span>Tổng PMH</span>
              <strong>{money(selected.total_estimate)}</strong>
            </div>
            <div>
              <span>Đang chờ chi</span>
              <strong>{money(selected.pending_amount)}</strong>
            </div>
            <div>
              <span>Đã chi</span>
              <strong>{money(selected.paid_amount)}</strong>
            </div>
            <div>
              <span>Còn được lập</span>
              <strong>{money(selected.available_amount)}</strong>
            </div>
          </div>
        </DetailModal>
      )}

      {voucherMode && (
        <PaymentVoucherDialog
          purchase={voucherMode.purchase}
          combined={voucherMode.combined}
          onClose={() => setVoucherMode(null)}
          onSaved={() => {
            setVoucherMode(null);
            load();
          }}
        />
      )}

      {rejecting && (
        <div className="acct-modal" role="dialog" aria-modal="true">
          <div className="acct-modal__box">
            <header className="acct-modal__head">
              <h2>Từ chối {rejecting.code}</h2>
              <button
                type="button"
                className="acct-modal__x"
                onClick={() => setRejecting(null)}
              >
                ×
              </button>
            </header>
            <div className="acct-modal__body">
              <label className="acct-field">
                <span>
                  Lý do từ chối <b>*</b>
                </span>
                <textarea
                  autoFocus
                  className="input acct-textarea"
                  value={rejectReason}
                  onChange={(event) => setRejectReason(event.target.value)}
                />
              </label>
            </div>
            <footer className="acct-modal__foot">
              <Button variant="ghost" onClick={() => setRejecting(null)}>
                Hủy
              </Button>
              <Button
                variant="danger"
                loading={busy === `reject:${rejecting.id}`}
                onClick={reject}
              >
                Từ chối phiếu
              </Button>
            </footer>
          </div>
        </div>
      )}
    </main>
  );
}
