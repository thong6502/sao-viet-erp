import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type PaymentVoucherRow,
  type PurchaseRequestRow,
  type PurchaseRequestStatus,
  type SupplierCredit,
  type SupplierRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import type { NavigateFn } from "../components/AppShell";
import { Button } from "../components/Button";
import { CodeLink } from "../components/CodeLink";
import { PurchaseActivityTimeline } from "../components/PurchaseActivityTimeline";
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
  purchased: { label: "Đang mua", tone: "purchased" },
  partially_received: { label: "Giao một phần", tone: "partial" },
  received: { label: "Đã nhận", tone: "received" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

const PAYMENT_META = {
  unpaid: { label: "Chưa thanh toán", tone: "unpaid" },
  partial: { label: "Thanh toán một phần", tone: "partial" },
  paid: { label: "Đã thanh toán", tone: "paid" },
} as const;

const VOUCHER_TYPE_LABEL: Record<PaymentVoucherRow["voucher_type"], string> = {
  cash: "Phiếu chi",
  bank_transfer: "UNC",
};

const PAYMENT_STAGE_LABEL: Record<PaymentVoucherRow["payment_stage"], string> = {
  advance: "Đặt cọc",
  partial: "Thanh toán một phần",
  final: "Thanh toán cuối",
  other: "Khác",
};

const VOUCHER_STATUS_LABEL: Record<PaymentVoucherRow["status"], string> = {
  paid: "Đã chi",
  cancelled: "Đã hủy",
};

type DepositFilter = "all" | "none" | "unpaid" | "partial" | "enough";

function DepositCell({ row }: { row: PurchaseRequestRow }) {
  if ((row.deposit_expected ?? 0) <= 0) {
    return <span className="md-page__muted">-</span>;
  }
  const paid = row.coc_da_chi ?? 0;
  const expected = row.deposit_expected ?? 0;
  const tone = paid >= expected ? "ok" : paid > 0 ? "warn" : "empty";
  return (
    <div className={`purchase__deposit purchase__deposit--${tone}`}>
      <strong>{money(paid)}</strong>
      <span>/ {money(expected)}</span>
    </div>
  );
}

export function AccountingPurchaseInboxPage({
  navigate,
  eventTick = 0,
  focusRequestCode,
  onDataRefreshed,
}: {
  navigate: NavigateFn;
  eventTick?: number;
  /** Mã PMH cần mở sẵn — màn Công nợ phải trả nhảy sang đây để lập phiếu chi cho đúng đơn đó.
      Không có nó thì bấm "Lập phiếu chi" chỉ đổ ra danh sách trắng, người dùng phải tự đi tìm. */
  focusRequestCode?: string | null;
  onDataRefreshed?: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  // DUYỆT đơn mua = quyết định CHI TIỀN ⇒ gác bằng `thu_mua:approve`, KHÔNG phải `ke_toan:approve`.
  // Sáng 04/08/2026 đã gỡ ô này khỏi bộ phận Mua hàng nên giờ chỉ giám đốc và người được trao
  // quyền còn. Để `ke_toan:approve` thì kế toán tự duyệt khoản chi rồi tự viết phiếu chi — đúng
  // lỗi tách vai vừa vá bên thu mua.
  // Ô này DỜI sang khoá `ke_toan` ngày 11/08/2026 (nút Duyệt / Từ chối chỉ có ở màn này nên ô
  // quyền cũng về đây). Lần dời trước sửa máy chủ mà QUÊN dòng này ⇒ quản trị tick ô mới, giao
  // diện vẫn hỏi ô cũ, nút không hiện — "cấp quyền rồi mà không thấy nút".
  const canApprove = can("ke_toan", "approve");
  // LẬP PHIẾU CHI là việc của kế toán — quyền khác hẳn quyền duyệt. Kế toán không có quyền duyệt
  // vẫn thấy đủ danh sách và trạng thái, chỉ không thấy nút Duyệt.
  // Nút "Lập phiếu chi" ⇒ quyền LẬP trên màn Phiếu chi. Trước đây hỏi `ke_toan:approve` —
  // cùng một ô với "gán chứng từ" và "lập phiếu thu", bật một cái là mở cả ba.
  const canCreateVoucher = can("phieu_chi", "create");
  const openYcmh = (code: string) =>
    navigate("yeu-cau-mua-hang", { focusRequestCode: code });
  const [rows, setRows] = useState<PurchaseRequestRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState(focusRequestCode ?? "");
  // Mới vào hiện TẤT CẢ (chủ 04/08/2026). Trước đây mặc định lọc "chờ duyệt" nên mở màn ra là
  // giấu mất đơn đã duyệt, đã mua, đã nhận — kế toán tưởng chưa có gì để lập phiếu chi.
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [supplierFilter, setSupplierFilter] = useState<number | "all">("all");
  const [depositFilter, setDepositFilter] = useState<DepositFilter>("all");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [neededFrom, setNeededFrom] = useState("");
  const [neededTo, setNeededTo] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
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
        supplier_id: supplierFilter === "all" ? null : supplierFilter,
        deposit_status: depositFilter === "all" ? null : depositFilter,
        created_from: createdFrom || null,
        created_to: createdTo || null,
        needed_from: neededFrom || null,
        needed_to: neededTo || null,
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
        onDataRefreshed?.();
      })
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "Không tải được yêu cầu Kế toán.",
        ),
      )
      .finally(() => setLoading(false));
  }, [
    token,
    q,
    statusFilter,
    supplierFilter,
    depositFilter,
    createdFrom,
    createdTo,
    neededFrom,
    neededTo,
    page,
    onDataRefreshed,
  ]);

  const loadSuppliers = useCallback(() => {
    if (!token) return;
    api.suppliers
      .list(token, { status: "active", sort: "name", page: 1, size: 200 })
      .then((res) => setSuppliers(res.items))
      .catch(() => setSuppliers([]));
  }, [token]);

  useEffect(() => {
    loadSuppliers();
  }, [loadSuppliers]);

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

  // Drawer chi tiết đơn: Esc để đóng (trước đây do DetailModal lo, nay drawer tự nghe).
  useEffect(() => {
    if (selectedId == null) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setSelectedId(null);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selectedId]);

  const [vouchers, setVouchers] = useState<PaymentVoucherRow[]>([]);
  const [vouchersLoading, setVouchersLoading] = useState(false);

  useEffect(() => {
    if (!token || selected == null) {
      setVouchers([]);
      setVouchersLoading(false);
      return;
    }
    let ignore = false;
    setVouchersLoading(true);
    api.accounting
      .vouchers(token, {
        purchase_request_id: selected.id,
        sort: "-created_at",
        page: 1,
        size: 50,
      })
      .then((data) => {
        if (!ignore) setVouchers(data.items);
      })
      .catch(() => {
        if (!ignore) setVouchers([]);
      })
      .finally(() => {
        if (!ignore) setVouchersLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [token, selected, eventTick]);

  // HẠN MỨC CÔNG NỢ của NCC trên đơn đang mở — CẢNH BÁO MỀM (Đ6): chỉ nhắc, KHÔNG chặn duyệt.
  // Chặn cứng ở đây là đúng lúc gấp nhất (hết giấy, phải mua ngay) thì hệ khoá đường mua.
  // Gọi riêng chứ không nhét vào danh sách: một lần một đơn, chỉ khi người ta thật sự mở ra xem.
  const [credit, setCredit] = useState<SupplierCredit | null>(null);
  useEffect(() => {
    if (!token || selected == null) {
      setCredit(null);
      return;
    }
    let bo = false;
    api.purchaseRequests
      .supplierCredit(token, selected.id)
      .then((data) => {
        if (!bo) setCredit(data);
      })
      // Nuốt lỗi có chủ đích: đây là cảnh báo phụ, hỏng nó không được chặn màn chi tiết.
      .catch(() => {
        if (!bo) setCredit(null);
      });
    return () => {
      bo = true;
    };
  }, [token, selected]);

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
          : "Không từ chối được đơn mua hàng.",
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
        {/* Trần lập phiếu nay có HAI mức khác nhau (Đ1/§5.4): `tran_dat_coc` cho phiếu đặt cọc
            (theo giá trị đơn đặt — cọc là chi khi hàng chưa về) và `outstanding_amount` = CÔNG NỢ
            cho phiếu thanh toán. Còn chỗ ở một trong hai là còn lập được, nên nút hiện khi tổng
            hai đường còn > 0; hộp thoại mới là chỗ chốt trần theo loại phiếu đã chọn. */}
        {canCreateVoucher &&
          ["approved", "purchased", "partially_received", "received"].includes(
            row.status,
          ) &&
          Math.max(row.tran_dat_coc, row.outstanding_amount) > 0 && (
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
            placeholder="Tìm mã đơn, YCMH, nhà cung cấp..."
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
        <select
          className="input acct-toolbar__select"
          value={supplierFilter}
          onChange={(event) => {
            setSupplierFilter(event.target.value === "all" ? "all" : Number(event.target.value));
            setPage(1);
          }}
        >
          <option value="all">Tất cả nhà cung cấp</option>
          {suppliers.map((supplier) => (
            <option key={supplier.id} value={supplier.id}>
              {supplier.name}
            </option>
          ))}
        </select>
        <select
          className="input acct-toolbar__select"
          value={depositFilter}
          onChange={(event) => {
            setDepositFilter(event.target.value as DepositFilter);
            setPage(1);
          }}
        >
          <option value="all">Tất cả tiền cọc</option>
          <option value="none">Không yêu cầu cọc</option>
          <option value="unpaid">Chưa cọc</option>
          <option value="partial">Cọc thiếu</option>
          <option value="enough">Cọc đủ</option>
        </select>
        <div className="acct-toolbar__date-group">
          <span>Ngày tạo</span>
          <input
            className="input acct-toolbar__date"
            type="date"
            title="Ngày tạo từ"
            value={createdFrom}
            onChange={(event) => {
              setCreatedFrom(event.target.value);
              setPage(1);
            }}
          />
          <input
            className="input acct-toolbar__date"
            type="date"
            title="Ngày tạo đến"
            value={createdTo}
            onChange={(event) => {
              setCreatedTo(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="acct-toolbar__date-group">
          <span>Ngày cần hàng</span>
          <input
            className="input acct-toolbar__date"
            type="date"
            title="Ngày cần từ"
            value={neededFrom}
            onChange={(event) => {
              setNeededFrom(event.target.value);
              setPage(1);
            }}
          />
          <input
            className="input acct-toolbar__date"
            type="date"
            title="Ngày cần đến"
            value={neededTo}
            onChange={(event) => {
              setNeededTo(event.target.value);
              setPage(1);
            }}
          />
        </div>
      </section>

      <section className="card md-page__tablewrap acct-list">
        <table className="md-page__table">
          <thead>
            <tr>
              {/* HAI cột trạng thái (đơn + thanh toán) đứng cạnh nhau ở cuối. KHÔNG còn cột
                  "Thao tác": bấm vào DÒNG mở drawer chi tiết, mọi thao tác nằm ở chân drawer
                  (24/08/2026 — gộp thao tác vào bản ghi). */}
              <th>Mã đơn</th>
              <th>Nhà cung cấp</th>
              <th>Ngày tạo</th>
              <th className="acct-amount-cell">Tổng đơn</th>
              <th className="acct-amount-cell">Tiền cọc</th>
              <th>Ngày cần</th>
              <th>Trạng thái</th>
              <th>Thanh toán</th>
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="purchase__skeleton-row">
                  <td><div className="purchase__skeleton-bar" style={{ width: "120px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "150px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "80px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "110px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "110px" }} /></td>
                </tr>
              ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={8}>Không có đơn mua hàng phù hợp.</td>
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
                    <td
                      className="acct-supplier-cell"
                      title={row.supplier_name ?? undefined}
                    >
                      {row.supplier_name || "—"}
                    </td>
                    <td className="acct-code-cell">{fmtDate(row.created_at)}</td>
                    <td className="acct-amount-cell">
                      <strong>{money(row.total_estimate)}</strong>
                    </td>
                    <td className="acct-amount-cell">
                      <DepositCell row={row} />
                    </td>
                    <td className="acct-code-cell">
                      {fmtDate(row.needed_date)}
                    </td>
                    <td>
                      <span
                        className={`purchase__status purchase__status--${status.tone}`}
                      >
                        {status.label}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`acct-payment-status acct-payment-status--${payment.tone}`}
                      >
                        {payment.label}
                      </span>
                      <small>{money(row.outstanding_amount)} còn lại</small>
                    </td>
                  </tr>
                );
              })}
          </tbody>
        </table>
        {!loading && (
          <div className="md-page__pager">
            <span>{total} đơn</span>
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
        )}
      </section>

      {selected && (
        <div className="rc-drawer__scrim" onClick={() => setSelectedId(null)}>
          <aside
            className="rc-drawer purchase__drawer-780"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label={selected.code}
          >
            <div className="purchase__hero-banner">
              <div className="purchase__hero-top">
                <div>
                  <span className="purchase__hero-kicker">Chi tiết đơn</span>
                  <div className="purchase__hero-title-row">
                    <h2 className="purchase__hero-code">{selected.code}</h2>
                    <span
                      className={`purchase__status purchase__status--${STATUS_META[selected.status].tone}`}
                    >
                      {STATUS_META[selected.status].label}
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  className="purchase__hero-x"
                  onClick={() => setSelectedId(null)}
                  aria-label="Đóng"
                >
                  ✕
                </button>
              </div>
              <div className="purchase__hero-meta">
                <span>{selected.supplier_name}</span>
                <span className="purchase__hero-dot">•</span>
                <span>Người lập {selected.created_by_name || "—"}</span>
                <span className="purchase__hero-dot">•</span>
                <span className="purchase__hero-date">
                  Cần {fmtDate(selected.needed_date)}
                </span>
                <span className="purchase__hero-dot">•</span>
                <span>{selected.lines.length} mặt hàng</span>
              </div>
            </div>
            <div className="rc-drawer__body">
          {/* Nhắc TRƯỚC khi bấm Duyệt, nhưng không khoá nút — người duyệt cầm số liệu rồi tự
              quyết. Chỉ hiện khi NCC thật sự đã vượt: bày cả lúc bình thường là nhiễu. */}
          {credit?.vuot_han_muc && (
            <div className="banner banner--warn" role="status">
              Đang nợ nhà cung cấp {money(credit.no_hien_tai)} — vượt hạn
              mức {money(credit.credit_limit)} là{" "}
              <strong>{money(credit.vuot_bao_nhieu)}</strong>. Đây là cảnh báo,
              không chặn duyệt.
            </div>
          )}
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
            <span>Nội dung / mục đích</span>
            <strong>
              {selected.content?.trim() ||
                [selected.purpose, selected.note]
                  .map((x) => (x ?? "").trim())
                  .filter(Boolean)
                  .join(" — ") ||
                "—"}
            </strong>
          </div>
          {selected.reject_reason && (
            <div className="purchase__note purchase__note--reject">
              <strong>Lý do từ chối / huỷ:</strong> {selected.reject_reason}
            </div>
          )}
          <table className="md-page__table purchase__lines-table">
            <thead>
              <tr>
                <th>Vật tư</th>
                <th className="num">Số lượng</th>
                <th className="num">VAT</th>
                <th className="num">Thành tiền</th>
              </tr>
            </thead>
            <tbody>
              {selected.lines.map((line) => (
                <tr key={line.id}>
                  <td>
                    <strong>{line.item_name}</strong>
                  </td>
                  <td className="num">
                    {line.quantity.toLocaleString("vi-VN")} {line.unit}
                  </td>
                  <td className="num">{line.vat_percent}%</td>
                  <td className="num">
                    <strong>{money(line.line_total)}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* Bốn con số theo đúng công thức mới: nợ = HÀNG ĐÃ VỀ − đã chi ròng. "Đang chờ chi" đã
              bỏ (không còn phiếu chờ chi), thay bằng "Hàng đã giao" — số thật sự đẻ ra công nợ. */}
          <div className="acct-payment-grid">
            <div>
              <span>Tổng đơn</span>
              <strong>{money(selected.total_estimate)}</strong>
            </div>
            <div>
              <span>Hàng đã giao</span>
              <strong>{money(selected.gia_tri_da_giao)}</strong>
            </div>
            <div>
              <span>Đã chi ròng</span>
              <strong>{money(selected.net_paid)}</strong>
            </div>
            <div>
              <span>Còn nợ</span>
              <strong>{money(selected.outstanding_amount)}</strong>
            </div>
          </div>
          {/* Hợp đồng + CỌC DỰ KIẾN — kế toán phải thấy ở đây, vì đây là màn họ lập phiếu chi.
              Thiếu nó thì thu mua khai cọc bên Mua hàng mà kế toán không hề biết, rồi lập phiếu
              cọc bằng một số tự nghĩ ra. Chỉ ĐỌC: cọc là con số người duyệt đã đồng ý. */}
          {(selected.contract_number || selected.deposit_expected > 0) && (
            <dl className="purchase__facts acct-contract-facts">
              {selected.contract_number && (
                <div>
                  <dt>Số hợp đồng</dt>
                  <dd>{selected.contract_number}</dd>
                </div>
              )}
              {selected.deposit_expected > 0 && (
                <div>
                  <dt>Cọc dự kiến</dt>
                  <dd>
                    <strong>{money(selected.deposit_expected)}</strong>
                    <small> — điền sẵn khi lập phiếu Đặt cọc</small>
                  </dd>
                </div>
              )}
            </dl>
          )}
          <section className="acct-deliveries">
            <p className="eyebrow">Đợt giao hàng</p>
            {selected.deliveries.length === 0 ? (
              <div className="md-page__muted">Chưa có đợt giao nào.</div>
            ) : (
              <table className="md-page__table acct-deliveries__table">
                <thead>
                  <tr>
                    <th>Đợt</th>
                    <th>Ngày giao</th>
                    <th>Hàng đã nhận</th>
                    <th>Hạn thanh toán</th>
                    <th>Giá trị</th>
                    <th>Đã chi</th>
                    <th>Còn nợ</th>
                    <th>Người ghi</th>
                  </tr>
                </thead>
                <tbody>
                  {selected.deliveries.map((dot) => (
                    <tr key={dot.id}>
                      <td>Đợt {dot.seq_no}</td>
                      <td>{fmtDate(dot.delivery_date)}</td>
                      <td>
                        <div className="acct-deliveries__lines">
                          {dot.lines.map((line) => (
                            <span key={line.id}>
                              <strong>{line.item_name}</strong>
                              {": "}
                              {line.quantity.toLocaleString("vi-VN")} {line.unit}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td>{dot.chua_dat_han ? "Chưa đặt hạn" : fmtDate(dot.due_date)}</td>
                      <td className="acct-amount-cell">{money(dot.amount)}</td>
                      <td className="acct-amount-cell">{money(dot.paid_amount)}</td>
                      <td className="acct-amount-cell">{money(dot.con_no)}</td>
                      <td>
                        {dot.created_by_name || "—"}
                        {dot.created_at && (
                          <small>{fmtDate(dot.created_at)}</small>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
          <section className="acct-vouchers">
            <p className="eyebrow">Chứng từ chi / UNC</p>
            {vouchersLoading ? (
              <div className="md-page__muted">Đang tải chứng từ...</div>
            ) : vouchers.length === 0 ? (
              <div className="md-page__muted">Chưa lập chứng từ chi nào.</div>
            ) : (
              <table className="md-page__table acct-vouchers__table">
                <thead>
                  <tr>
                    <th>Mã chứng từ</th>
                    <th>Loại</th>
                    <th>Đợt thanh toán</th>
                    <th>Ngày chứng từ</th>
                    <th>Số tiền</th>
                    <th>Trạng thái</th>
                    <th>Người lập / chi</th>
                  </tr>
                </thead>
                <tbody>
                  {vouchers.map((voucher) => (
                    <tr key={voucher.id}>
                      <td className="acct-code-cell">
                        <strong>{voucher.doc_no || voucher.code}</strong>
                        {voucher.delivery_seq_no && (
                          <small>Đợt giao {voucher.delivery_seq_no}</small>
                        )}
                      </td>
                      <td>{VOUCHER_TYPE_LABEL[voucher.voucher_type]}</td>
                      <td>{PAYMENT_STAGE_LABEL[voucher.payment_stage]}</td>
                      <td>{fmtDate(voucher.voucher_date)}</td>
                      <td className="acct-amount-cell">
                        {money(voucher.amount_vnd)}
                      </td>
                      <td>
                        <span
                          className={`acct-payment-status acct-payment-status--${voucher.status}`}
                        >
                          {VOUCHER_STATUS_LABEL[voucher.status]}
                        </span>
                      </td>
                      <td>
                        {voucher.created_by_name || "—"}
                        <small>
                          {fmtDate(voucher.created_at)}
                          {voucher.paid_by_name
                            ? ` · Chi bởi ${voucher.paid_by_name}`
                            : ""}
                        </small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
          <section className="acct-history">
            <p className="eyebrow">Lịch sử đơn mua hàng</p>
            <PurchaseActivityTimeline items={selected.activity_history} />
          </section>
            </div>
            <div className="purchase__drawer-footer">{actions(selected)}</div>
          </aside>
        </div>
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
                Từ chối đơn
              </Button>
            </footer>
          </div>
        </div>
      )}
    </main>
  );
}
