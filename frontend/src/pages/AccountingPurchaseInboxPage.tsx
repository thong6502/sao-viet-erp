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
  eventTick = 0,
  focusRequestCode,
}: {
  navigate: NavigateFn;
  eventTick?: number;
  /** Mã PMH cần mở sẵn — màn Công nợ phải trả nhảy sang đây để lập phiếu chi cho đúng đơn đó.
      Không có nó thì bấm "Lập phiếu chi" chỉ đổ ra danh sách trắng, người dùng phải tự đi tìm. */
  focusRequestCode?: string | null;
}) {
  const { token } = useAuth();
  const can = useCan();
  // DUYỆT đơn mua = quyết định CHI TIỀN ⇒ gác bằng `thu_mua:approve`, KHÔNG phải `ke_toan:approve`.
  // Sáng 04/08/2026 đã gỡ ô này khỏi bộ phận Mua hàng nên giờ chỉ giám đốc và người được trao
  // quyền còn. Để `ke_toan:approve` thì kế toán tự duyệt khoản chi rồi tự viết phiếu chi — đúng
  // lỗi tách vai vừa vá bên thu mua.
  const canApprove = can("thu_mua", "approve");
  // LẬP PHIẾU CHI là việc của kế toán — quyền khác hẳn quyền duyệt. Kế toán không có quyền duyệt
  // vẫn thấy đủ danh sách và trạng thái, chỉ không thấy nút Duyệt.
  const canCreateVoucher = can("ke_toan", "approve");
  const openYcmh = (code: string) =>
    navigate("yeu-cau-mua-hang", { focusRequestCode: code });
  const [rows, setRows] = useState<PurchaseRequestRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState(focusRequestCode ?? "");
  // Mới vào hiện TẤT CẢ (chủ 04/08/2026). Trước đây mặc định lọc "chờ duyệt" nên mở màn ra là
  // giấu mất đơn đã duyệt, đã mua, đã nhận — kế toán tưởng chưa có gì để lập phiếu chi.
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [voucherMode, setVoucherMode] = useState<null | {
    purchase: PurchaseRequestRow;
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

  useEffect(() => {
    if (eventTick <= 0) return;
    load();
  }, [eventTick, load]);

  // Sang màn này từ nơi khác kèm mã PMH ⇒ nhét luôn vào ô tìm và về trang 1.
  useEffect(() => {
    if (!focusRequestCode) return;
    setQ(focusRequestCode);
    setPage(1);
  }, [focusRequestCode]);

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

  /** DUYỆT đơn mua — một bước riêng, không kèm lập phiếu chi.
   *
   * Gọi thẳng API của Thu mua (`/purchase-requests/{id}/approve`) chứ không đẻ endpoint kế toán
   * riêng: thứ đang duyệt là PHIẾU MUA, chỉ khác chỗ đứng bấm. Nhờ vậy chốt chống tự duyệt ở
   * service (người lập không duyệt phiếu của chính mình) vẫn chạy nguyên. */
  async function approve(row: PurchaseRequestRow) {
    if (!token) return;
    setBusy(`approve-${row.id}`);
    setError(null);
    try {
      await api.purchaseRequests.approve(token, row.id);
      load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không duyệt được đơn mua hàng.",
      );
    } finally {
      setBusy(null);
    }
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
            {/* HAI BƯỚC RỜI (chủ 04/08/2026): giám đốc duyệt trước, kế toán lập phiếu chi sau —
                hai chữ ký, hai người. Nút "Duyệt & lập chứng từ" gộp cả hai vào một cú bấm đã bỏ. */}
            <Button
              type="button"
              variant="primary"
              loading={busy === `approve-${row.id}`}
              onClick={() => closeDetailThen(() => approve(row))}
            >
              Duyệt
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
        {/* Chỉ đơn ĐÃ DUYỆT mới lập được phiếu chi — và người lập là KẾ TOÁN, không cần quyền
            duyệt. Backend cũng đã chặn (`accounting_service` chỉ nhận PMH từ approved trở lên),
            đây là lớp hiển thị cho khớp. */}
        {canCreateVoucher &&
          ["approved", "purchased", "received"].includes(row.status) &&
          row.available_amount > 0 && (
            <Button
              type="button"
              variant="primary"
              onClick={() =>
                closeDetailThen(() =>
                  setVoucherMode({ purchase: row }),
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
        <p className="eyebrow">Kế toán thu mua</p>
        {/* Tên cũ "Yêu cầu mua hàng" SAI: màn này hiển thị PHIẾU MUA HÀNG (PMH), không phải YCMH. */}
        <h1 className="md-page__title">Đơn mua hàng</h1>
        <p className="md-page__sub">
          Giám đốc duyệt đơn Thu mua gửi đến; đơn đã duyệt thì Kế toán lập Phiếu chi
          {UNC_ENABLED ? " hoặc Ủy nhiệm chi" : ""}. Hai bước, hai người.
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
          {/* <Button type="submit" variant="ghost">
            Tìm
          </Button> */}
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
          {/* Bỏ "Nháp": đơn nháp là thu mua còn đang sửa, CHƯA gửi duyệt — kế toán không có việc
              gì với nó. Backend cũng đã loại hẳn khỏi hộp thư này, để đây chỉ là cho khớp. */}
          {Object.entries(STATUS_META)
            .filter(([value]) => value !== "draft")
            .map(([value, meta]) => (
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
                      {/* NCC giao thiếu thì trần lập phiếu chi tụt theo giá trị THỰC NHẬN. Không
                          nói ra ở đây thì kế toán viết phiếu bằng số trên đơn rồi bị chặn mà không
                          hiểu vì sao. */}
                      {row.received_total < row.total_estimate && (
                        <small>Thực nhận {money(row.received_total)}</small>
                      )}
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
