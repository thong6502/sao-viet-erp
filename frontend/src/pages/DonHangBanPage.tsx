// Đơn hàng bán (Order) — spec-10, feat-047 (F1/F2 làm-ngay) + F3/F8 scaffold, F4/F6/F7 SEAM-treo.
// Danh sách đơn (order_no, khách, loại đơn, trạng thái, tổng dự kiến, cờ ③→④) + Tạo đơn từ MỘT
// báo giá đã duyệt còn hạn (SEAM-04 quotation_ref — Báo giá LIVE): ghim quotation_id+version+
// effective_from, đổ dòng đơn SNAPSHOT copy-on-write giá; khách kéo từ báo giá read-only; chọn
// order_type/order_kind, đơn bổ sung → BẮT BUỘC đơn gốc; TUYỆT ĐỐI KHÔNG hiển thị field vật lý
// (khổ/màu/kẽm/imposition/PrintForm) ở mọi view Sale (§29 P0). Chi tiết: dòng đơn read-only +
// khối Cổng ③→④ (cọc TREO SEAM-04 Payment) + Cổng ⑤→⑥/Tiến độ SX/Giao hàng "chờ phân hệ …"
// (SEAM-05/06/01/02, F4/F6/F7 treo) + nút Chốt/Đổi/Hủy.
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type ApprovedQuotationRow,
  type EnumOption,
  type OrderDetail,
  type OrderEnumsOut,
  type OrderRow,
  type PinnedCustomer,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./don-hang-ban.css";

const PAGE_SIZE = 10;

function labelOf(options: EnumOption[], value: string | null): string {
  if (!value) return "—";
  return options.find((o) => o.value === value)?.label ?? value;
}

function fmtVnd(v: number | null | undefined): string {
  if (v == null) return "—";
  return v.toLocaleString("vi-VN") + " đ";
}

function fmtDate(v: string | null): string {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleDateString("vi-VN");
  } catch {
    return v;
  }
}

export function DonHangBanPage({
  pinnedCustomer = null,
  openOrderId = null,
}: {
  pinnedCustomer?: PinnedCustomer | null;
  openOrderId?: number | null;
} = {}) {
  const { token } = useAuth();

  const [rows, setRows] = useState<OrderRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("-created_at");
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [enums, setEnums] = useState<OrderEnumsOut | null>(null);

  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [creating, setCreating] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);
  // Customer pinned by a CRM drill-through ("+ Tạo đơn hàng"). The create dialog scopes its
  // approved-quotation picker to this customer so the order lands on the right account.
  const [pinned, setPinned] = useState<PinnedCustomer | null>(null);

  useEffect(() => {
    if (pinnedCustomer) {
      setPinned(pinnedCustomer);
      setCreating(true);
    }
  }, [pinnedCustomer]);

  useEffect(() => {
    if (openOrderId != null) setDetailId(openOrderId);
  }, [openOrderId]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setListError(null);
    api.orders
      .list(token, {
        q: q.trim() || undefined,
        status: statusFilter || null,
        sort,
        page,
        size: PAGE_SIZE,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setListError("Không tải được danh sách đơn hàng.");
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, q, statusFilter, sort, page]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, sort, page, statusFilter]);

  useEffect(() => {
    if (!token) return;
    api.orders
      .enums(token)
      .then(setEnums)
      .catch(() => setEnums(null));
  }, [token]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    load();
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const statuses = enums?.statuses ?? [];
  const kinds = enums?.order_kinds ?? [];
  const types = enums?.order_types ?? [];

  if (forbidden) {
    return (
      <main className="dh">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Đơn hàng bán (403).
        </div>
      </main>
    );
  }

  return (
    <main className="dh">
      <header className="dh__head">
        <p className="eyebrow">Kinh doanh</p>
        <h1 className="dh__title">Đơn hàng bán</h1>
        <p className="dh__sub">
          Chốt đơn từ báo giá đã duyệt (bước ④): ghim đúng version báo giá, snapshot giá
          copy-on-write, cổng cứng ③→④ (đã duyệt + cọc đạt ngưỡng). Không tính lại giá, không
          kéo từ Tính giá; field vật lý ẩn khỏi màn bán.
        </p>
      </header>

      <div className="dh__toolbar">
        <form className="dh__search" onSubmit={onSearch} role="search">
          <input
            className="input"
            placeholder="Tìm theo mã đơn / khách…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Tìm đơn hàng"
          />
          <Button type="submit" variant="ghost">
            Tìm
          </Button>
        </form>

        <select
          className="input dh__statusfilter"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          aria-label="Lọc theo trạng thái"
        >
          <option value="">Tất cả trạng thái</option>
          {statuses.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        <div className="dh__toolbar-spacer" />

        <Button variant="primary" onClick={() => setCreating(true)}>
          + Tạo đơn hàng
        </Button>
      </div>

      <div className="card dh__tablewrap">
        <table className="dh__table">
          <thead>
            <tr>
              <th>
                <SortBtn label="Mã đơn" col="order_no" sort={sort} onSort={setSort} />
              </th>
              <th>Khách hàng</th>
              <th>
                <SortBtn label="Loại đơn" col="order_kind" sort={sort} onSort={setSort} />
              </th>
              <th className="dh__num">Tổng dự kiến</th>
              <th>Cổng ③→④</th>
              <th>
                <SortBtn label="Trạng thái" col="status" sort={sort} onSort={setSort} />
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="dh__status" role="status">
                  Đang tải…
                </td>
              </tr>
            ) : listError ? (
              <tr>
                <td colSpan={6} className="dh__status">
                  <div className="banner banner--error" role="alert">
                    <span>{listError}</span>
                    <button type="button" className="btn btn--ghost" onClick={() => load()}>
                      Thử lại
                    </button>
                  </div>
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="dh__empty">
                  <p>Chưa có đơn hàng nào.</p>
                  <Button variant="primary" onClick={() => setCreating(true)}>
                    + Tạo đơn hàng
                  </Button>
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} className="dh__row" onClick={() => setDetailId(r.id)}>
                  <td className="dh__mono">{r.order_no}</td>
                  <td>
                    {r.customer_name ?? (
                      <span className="dh__muted">
                        {r.customer_id != null ? `KH #${r.customer_id}` : "—"}
                      </span>
                    )}
                  </td>
                  <td>
                    <span className="dh__kindtag">{labelOf(kinds, r.order_kind)}</span>
                    <span className="dh__muted"> · {labelOf(types, r.order_type)}</span>
                  </td>
                  <td className="dh__num">{fmtVnd(r.total_estimate)}</td>
                  <td>
                    <GateBadge ok={r.gate_ordered_ok} />
                  </td>
                  <td>
                    <StatusBadge status={r.status} statuses={statuses} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {!loading && !listError && rows.length > 0 && (
        <div className="dh__pager">
          <span className="dh__muted">
            {total} đơn · trang {page}/{totalPages}
          </span>
          <div className="dh__pager-btns">
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ‹ Trước
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Sau ›
            </button>
          </div>
        </div>
      )}

      {creating && enums && (
        <OrderCreateDialog
          enums={enums}
          pinnedCustomer={pinned}
          onClose={() => {
            setCreating(false);
            setPinned(null);
          }}
          onSaved={() => {
            setCreating(false);
            setPinned(null);
            setPage(1);
            load();
          }}
        />
      )}

      {detailId != null && (
        <OrderDetailDialog
          orderId={detailId}
          statuses={statuses}
          types={types}
          kinds={kinds}
          onClose={() => setDetailId(null)}
          onChanged={() => load()}
        />
      )}
    </main>
  );
}

// --- Sort header button -------------------------------------------------------

function SortBtn({
  label,
  col,
  sort,
  onSort,
}: {
  label: string;
  col: string;
  sort: string;
  onSort: (s: string) => void;
}) {
  const active = sort === col || sort === `-${col}`;
  const desc = sort === `-${col}`;
  return (
    <button
      type="button"
      className={`dh__sortbtn${active ? " is-active" : ""}`}
      onClick={() => onSort(desc ? col : active ? `-${col}` : col)}
    >
      {label}
      {active && <span aria-hidden="true">{desc ? " ↓" : " ↑"}</span>}
    </button>
  );
}

function StatusBadge({ status, statuses }: { status: string; statuses: EnumOption[] }) {
  const tone =
    status === "ordered"
      ? " dh__badge--ok"
      : status === "cancelled"
        ? " dh__badge--off"
        : status === "change_order"
          ? " dh__badge--sent"
          : "";
  return <span className={`dh__badge${tone}`}>{labelOf(statuses, status)}</span>;
}

function GateBadge({ ok }: { ok: boolean }) {
  return (
    <span className={`dh__gate${ok ? " dh__gate--ok" : " dh__gate--off"}`}>
      {ok ? "Đã đạt" : "Chưa đạt"}
    </span>
  );
}

// --- Create dialog (F1/F2) ----------------------------------------------------

function OrderCreateDialog({
  enums,
  pinnedCustomer,
  onClose,
  onSaved,
}: {
  enums: OrderEnumsOut;
  pinnedCustomer: PinnedCustomer | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();

  const [approvedAll, setApprovedAll] = useState<ApprovedQuotationRow[] | null>(null);
  const [quotationId, setQuotationId] = useState<string>("");
  const [orderType, setOrderType] = useState("theo_yc");
  const [orderKind, setOrderKind] = useState("moi");
  const [parentOrderNo, setParentOrderNo] = useState<string>("");
  const [hasCustomerPaper, setHasCustomerPaper] = useState(false);
  const [vatPct, setVatPct] = useState("8");

  const [fieldErr, setFieldErr] = useState<Record<string, string>>({});
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!token) return;
    api.orders
      .approvedQuotations(token)
      .then((res) => setApprovedAll(res.items))
      .catch(() => setApprovedAll([]));
  }, [token]);

  // When pinned from CRM, only offer this customer's approved quotations so the order lands
  // on the right account (the customer itself is carried by the quotation, read-only).
  const approved =
    approvedAll == null
      ? null
      : pinnedCustomer
        ? approvedAll.filter((a) => a.customer_id === pinnedCustomer.id)
        : approvedAll;

  const selected = approved?.find((a) => String(a.id) === quotationId) ?? null;

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!quotationId) errs.quotation = "Chọn một báo giá đã duyệt còn hạn.";
    if (orderKind === "bo_sung" && !parentOrderNo.trim())
      errs.parent = "Đơn bổ sung bắt buộc chọn đơn/job gốc.";
    setFieldErr(errs);
    return Object.keys(errs).length === 0;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    if (!validate()) return;
    setSaving(true);
    setSaveErr(null);
    try {
      await api.orders.create(token, {
        quotation_id: Number(quotationId),
        order_type: orderType,
        order_kind: orderKind,
        // Đơn bổ sung: người dùng nhập mã đơn gốc (DH###) — ở P0 dùng chính id đơn gốc.
        // Ở đây parentOrderNo là id đơn gốc (số); validate đã chặn rỗng khi bổ sung.
        parent_order_id:
          orderKind === "bo_sung" && parentOrderNo.trim()
            ? Number(parentOrderNo.trim())
            : null,
        has_customer_paper: hasCustomerPaper,
        vat_pct_estimate: Number(vatPct) || 0,
      });
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setSaveErr(err.message);
      else setSaveErr("Tạo đơn không thành công. Vui lòng thử lại.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dh__overlay" onClick={onClose}>
      <div
        className="card dh__dialog"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dh__dialog-head">
          <h2>Tạo đơn hàng bán</h2>
          <button type="button" className="dh__close" onClick={onClose} aria-label="Đóng">
            ✕
          </button>
        </div>

        <form className="dh__dialog-body" onSubmit={submit} noValidate>
          {pinnedCustomer && (
            <div className="dh__ref">
              <span className="dh__muted">Đơn cho khách (ghim từ CRM): </span>
              <strong>{pinnedCustomer.name}</strong>
              <span className="dh__muted">
                {" "}
                · {pinnedCustomer.code}
                {pinnedCustomer.tax_code ? ` · MST ${pinnedCustomer.tax_code}` : ""}
              </span>
              <div className="dh__muted">
                Chỉ hiện báo giá đã duyệt của khách này — chọn để chốt đơn đúng account.
              </div>
            </div>
          )}
          <div>
            <p className="dh__section-title">Nguồn: Báo giá đã duyệt (SEAM-04)</p>
            {approved == null ? (
              <p className="dh__muted" role="status">
                Đang tải báo giá…
              </p>
            ) : approved.length === 0 ? (
              <div className="dh__seam-tag">
                {pinnedCustomer
                  ? `Khách ${pinnedCustomer.name} chưa có báo giá đã duyệt còn hạn. Hãy tạo & duyệt báo giá trước, rồi chốt đơn từ báo giá đó.`
                  : "Chưa có báo giá đã duyệt còn hạn để chọn — hoặc phân hệ Báo giá chưa sẵn sàng. Đơn hàng chỉ tham chiếu báo giá đã duyệt (không kéo từ Tính giá)."}
              </div>
            ) : (
              <label className="field">
                <span className="field__label">Chọn báo giá đã duyệt còn hạn *</span>
                <select
                  className="input"
                  value={quotationId}
                  onChange={(e) => setQuotationId(e.target.value)}
                >
                  <option value="">— Chọn báo giá —</option>
                  {approved.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.code} v{a.version} · {fmtVnd(a.total)}
                      {a.valid_until ? ` · HL ${fmtDate(a.valid_until)}` : ""}
                    </option>
                  ))}
                </select>
                {fieldErr.quotation && <span className="dh__err">{fieldErr.quotation}</span>}
              </label>
            )}

            {selected && (
              <div className="dh__ref">
                <div>
                  <span className="dh__muted">Khách hàng (kéo từ báo giá): </span>
                  <strong>
                    {selected.customer_name ??
                      (selected.customer_id != null
                        ? `KH #${selected.customer_id}`
                        : "Chưa gán khách")}
                  </strong>
                </div>
                <div className="dh__muted">
                  Ghim {selected.code} v{selected.version} — giá bán được snapshot copy-on-write
                  vào dòng đơn (đổi giá gốc sau không đổi số trên đơn).
                </div>
              </div>
            )}
          </div>

          <div>
            <p className="dh__section-title">Loại đơn</p>
            <div className="dh__form-grid">
              <label className="field">
                <span className="field__label">Nguồn đơn</span>
                <select
                  className="input"
                  value={orderType}
                  onChange={(e) => setOrderType(e.target.value)}
                >
                  {enums.order_types.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Loại đơn</span>
                <select
                  className="input"
                  value={orderKind}
                  onChange={(e) => setOrderKind(e.target.value)}
                >
                  {enums.order_kinds.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              {orderKind === "bo_sung" && (
                <label className="field">
                  <span className="field__label">Đơn/job gốc (ID) *</span>
                  <input
                    className="input"
                    value={parentOrderNo}
                    onChange={(e) => setParentOrderNo(e.target.value)}
                    inputMode="numeric"
                    placeholder="ID đơn gốc"
                  />
                  {fieldErr.parent && <span className="dh__err">{fieldErr.parent}</span>}
                  <span className="dh__hint">
                    Đơn bổ sung mang giá bán riêng, giữ kẽm cũ nên rẻ hơn (khác In bù nội bộ).
                  </span>
                </label>
              )}
              <label className="field">
                <span className="field__label">VAT dự kiến (%)</span>
                <input
                  className="input"
                  value={vatPct}
                  onChange={(e) => setVatPct(e.target.value)}
                  inputMode="numeric"
                />
                <span className="dh__hint">
                  Chỉ để ước tổng — chân lý VAT ở Hóa đơn (⑬), không chốt ở đây.
                </span>
              </label>
            </div>

            <label className="dh__check">
              <input
                type="checkbox"
                checked={hasCustomerPaper}
                onChange={(e) => setHasCustomerPaper(e.target.checked)}
              />
              <span>
                Ứng giấy khách (chi tiết lô giấy sống ở Kho — SEAM-06, liên kết đọc, chưa nhập
                tồn ở màn này)
              </span>
            </label>
          </div>

          {saveErr && (
            <div className="banner banner--error" role="alert">
              {saveErr}
            </div>
          )}

          <div className="dh__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>
              Hủy
            </Button>
            <Button type="submit" variant="primary" disabled={saving || approved?.length === 0}>
              {saving ? "Đang tạo…" : "Tạo đơn (nháp)"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// --- Detail dialog (F1 read-only snapshot + F3 gate + F4/F6/F7 SEAM + F8) ------

const TRANSITION_LABELS: Record<string, string> = {
  ordered: "Chốt đơn",
  on_hold: "Tạm giữ",
  change_order: "Đổi đơn (re-quote)",
  cancelled: "Hủy đơn",
  draft: "Mở lại (nháp)",
};

function OrderDetailDialog({
  orderId,
  statuses,
  types,
  kinds,
  onClose,
  onChanged,
}: {
  orderId: number;
  statuses: EnumOption[];
  types: EnumOption[];
  kinds: EnumOption[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const { token } = useAuth();
  const [d, setD] = useState<OrderDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [askCancel, setAskCancel] = useState(false);

  const reload = useCallback(async () => {
    if (!token) return;
    try {
      setD(await api.orders.get(token, orderId));
    } catch {
      setErr("Không tải được chi tiết đơn hàng.");
    }
  }, [token, orderId]);

  useEffect(() => {
    reload();
  }, [reload]);

  async function doTransition(to: string) {
    if (!token || !d) return;
    if (to === "cancelled" && !askCancel) {
      setAskCancel(true);
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.orders.transition(token, d.id, {
        to_status: to,
        cancel_reason: to === "cancelled" ? cancelReason : null,
      });
      setAskCancel(false);
      setCancelReason("");
      await reload();
      onChanged();
    } catch (e) {
      if (e instanceof ApiError) setErr(e.message);
      else setErr("Thao tác không thành công.");
    } finally {
      setBusy(false);
    }
  }

  if (!d) {
    return (
      <div className="dh__overlay" onClick={onClose}>
        <div className="card dh__dialog dh__dialog--sm" onClick={(e) => e.stopPropagation()}>
          <div className="dh__dialog-body" role="status">
            Đang tải…
          </div>
        </div>
      </div>
    );
  }

  const locked = d.status !== "draft"; // snapshot khóa sau chốt/đổi/hủy
  const gate = d.gate;

  return (
    <div className="dh__overlay" onClick={onClose}>
      <div className="card dh__dialog" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="dh__dialog-head">
          <h2>{d.order_no}</h2>
          <button type="button" className="dh__close" onClick={onClose} aria-label="Đóng">
            ✕
          </button>
        </div>

        <div className="dh__dialog-body">
          <div className="dh__detail-top">
            <StatusBadge status={d.status} statuses={statuses} />
            <span className="dh__kindtag">{labelOf(kinds, d.order_kind)}</span>
            <span className="dh__muted">{labelOf(types, d.order_type)}</span>
            {locked && <span className="dh__lock">Snapshot đã khóa (chỉ-đọc)</span>}
          </div>

          {d.customer && (
            <div className="dh__customer">
              <strong>{d.customer.name}</strong>
              {d.customer.tax_code && <span className="dh__muted"> · MST {d.customer.tax_code}</span>}
              <div className="dh__muted">{d.customer.credit_status_display}</div>
            </div>
          )}

          <div className="dh__ref">
            <span className="dh__muted">Nguồn báo giá đã ghim: </span>
            <strong>
              BG #{d.quotation_id ?? "—"} v{d.quotation_version ?? "—"}
            </strong>
            {d.quotation_effective_from && (
              <span className="dh__muted"> · hiệu lực từ {fmtDate(d.quotation_effective_from)}</span>
            )}
            {d.parent_order_id != null && (
              <span className="dh__muted"> · đơn bổ sung của #{d.parent_order_id}</span>
            )}
          </div>

          {/* Dòng đơn: mô tả SP thương mại + snapshot giá — KHÔNG field vật lý (§29 P0). */}
          <div>
            <p className="dh__section-title">Dòng đơn (snapshot giá — read-only)</p>
            <table className="dh__linetable">
              <thead>
                <tr>
                  <th>Mô tả</th>
                  <th className="dh__num">SL</th>
                  <th className="dh__num">Đơn giá (snapshot)</th>
                  <th className="dh__num">Thành tiền</th>
                </tr>
              </thead>
              <tbody>
                {d.lines.map((ln) => (
                  <tr key={ln.id}>
                    <td>{ln.description}</td>
                    <td className="dh__num">{ln.qty}</td>
                    <td className="dh__num">{fmtVnd(ln.unit_price_snapshot)}</td>
                    <td className="dh__num">{fmtVnd(ln.line_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="dh__hint">
              VAT dự kiến {d.vat_pct_estimate}% (ước tổng). Copy-on-write: đổi giá gốc sau không
              làm đổi số trên đơn.
            </p>
          </div>

          {/* F3 Cổng ③→④: gate cứng approved + cọc ≥ ngưỡng; ghi cọc TREO SEAM-04 Payment. */}
          {gate && (
            <div className="dh__gatepanel">
              <p className="dh__section-title">Cổng ③→④ (chốt đơn)</p>
              <div className="dh__gategrid">
                <div>
                  <span className="dh__muted">Tổng dự kiến</span>
                  <strong>{fmtVnd(gate.total)}</strong>
                </div>
                <div>
                  <span className="dh__muted">Ngưỡng cọc ({gate.min_deposit_pct}%)</span>
                  <strong>{fmtVnd(gate.deposit_required)}</strong>
                </div>
                <div>
                  <span className="dh__muted">Đã duyệt giá</span>
                  <strong>{gate.quotation_approved ? "Có" : "Chưa"}</strong>
                </div>
                <div>
                  <span className="dh__muted">Cọc đã thu</span>
                  {gate.deposit_available ? (
                    <strong>{fmtVnd(gate.deposit_paid)}</strong>
                  ) : (
                    <span className="dh__seam-inline">chờ phân hệ Tài chính (Payment)</span>
                  )}
                </div>
              </div>
              {!gate.deposit_available ? (
                <div className="dh__seam-tag">
                  Chưa ghi được cọc — phân hệ Tài chính (Payment) chưa sẵn sàng (SEAM-04). Chưa
                  thể chốt đơn. Ngưỡng/còn thiếu tính theo tổng, không bịa số đã thu.
                </div>
              ) : gate.can_confirm ? (
                <div className="dh__ok-tag">Đủ điều kiện chốt đơn.</div>
              ) : (
                <div className="dh__warn-tag">
                  Còn thiếu {fmtVnd(gate.deposit_shortfall)} để đạt ngưỡng chốt.
                </div>
              )}
            </div>
          )}

          {/* F6/F7 TREO: chỉ-báo cổng ⑤→⑥ + tiến độ SX + giao hàng — chờ phân hệ. */}
          <div className="dh__seams">
            <div className="dh__seam-row">
              <span className="dh__seam-label">Cổng ⑤→⑥ (duyệt mẫu)</span>
              <span className="dh__seam-inline">chờ phân hệ Chế bản (SEAM-05)</span>
            </div>
            <div className="dh__seam-row">
              <span className="dh__seam-label">Tiến độ sản xuất</span>
              <span className="dh__seam-inline">chờ phân hệ Sản xuất (SEAM-01)</span>
            </div>
            <div className="dh__seam-row">
              <span className="dh__seam-label">Trạng thái giao hàng</span>
              <span className="dh__seam-inline">chờ phân hệ Giao hàng (SEAM-02)</span>
            </div>
            {d.has_customer_paper && (
              <div className="dh__seam-row">
                <span className="dh__seam-label">Ứng giấy khách</span>
                <span className="dh__seam-inline">chi tiết lô ở Kho (SEAM-06)</span>
              </div>
            )}
          </div>

          {d.cancelled_at_state && (
            <div className="dh__muted">
              Đã hủy (từ trạng thái {labelOf(statuses, d.cancelled_at_state)})
              {d.cancel_reason && ` — ${d.cancel_reason}`}
            </div>
          )}

          {err && (
            <div className="banner banner--error" role="alert">
              {err}
            </div>
          )}

          {askCancel && (
            <label className="field">
              <span className="field__label">Lý do hủy (bắt buộc)</span>
              <input
                className="input"
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                autoFocus
              />
            </label>
          )}

          <div className="dh__dialog-actions dh__dialog-actions--wrap">
            {d.allowed_transitions.map((t) => {
              const isConfirm = t === "ordered";
              const disabled =
                busy || (isConfirm && !(gate?.can_confirm ?? false));
              return (
                <Button
                  key={t}
                  type="button"
                  variant={isConfirm ? "primary" : "ghost"}
                  disabled={disabled}
                  onClick={() => doTransition(t)}
                  title={
                    isConfirm && !(gate?.can_confirm ?? false)
                      ? "Cần đã duyệt giá và cọc đạt ngưỡng (cọc chờ phân hệ Tài chính)"
                      : undefined
                  }
                >
                  {TRANSITION_LABELS[t] ?? t}
                </Button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
