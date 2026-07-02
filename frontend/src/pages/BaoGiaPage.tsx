// Báo giá (Quotation) — spec-09, feat-044 (F1/F2) + feat-045 (F3..F6).
// Danh sách phiếu (mã+version, khách, tổng giá bán, trạng thái, hạn hiệu lực) + Tạo/Sửa
// (tham chiếu 1 Tính giá qua SEAM-13, chọn khách qua SEAM-14, nhập lãi + chiết khấu → tổng
// giá bán tính lại; KHÔNG buildup/số con-tờ-kẽm/bù hao) + Chi tiết (vòng đời, snapshot nội
// bộ, lịch sử version, Gửi/Duyệt/Từ chối/Re-quote/Hủy/Tạm giữ/Xuất PDF) đối ngoại.
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type CostingPickerOut,
  type EnumOption,
  type PinnedCustomer,
  type QuotationDetail,
  type QuotationEnumsOut,
  type QuotationInput,
  type QuotationRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./bao-gia.css";

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

export function BaoGiaPage({
  pinnedCustomer = null,
  openQuoteId = null,
}: {
  pinnedCustomer?: PinnedCustomer | null;
  openQuoteId?: number | null;
} = {}) {
  const { token } = useAuth();

  const [rows, setRows] = useState<QuotationRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("-created_at");
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [enums, setEnums] = useState<QuotationEnumsOut | null>(null);

  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [editing, setEditing] = useState<QuotationDetail | null>(null);
  const [detail, setDetail] = useState<QuotationDetail | null>(null);
  // A customer pinned by a CRM drill-through (CRM → "+ Tạo báo giá"). Kept so the create
  // dialog opens with the customer already bound (never a hand-typed id). Cleared on save/close.
  const [pinned, setPinned] = useState<PinnedCustomer | null>(null);

  // Arriving from CRM with a customer to pre-pin → open the create dialog bound to them.
  useEffect(() => {
    if (pinnedCustomer) {
      setPinned(pinnedCustomer);
      setEditing(null);
      setMode("create");
    }
  }, [pinnedCustomer]);

  // Arriving from CRM history/audit drill-through → open that quotation's detail.
  useEffect(() => {
    if (!token || openQuoteId == null) return;
    api.quotations
      .get(token, openQuoteId)
      .then(setDetail)
      .catch(() => setListError("Không mở được chi tiết báo giá."));
  }, [token, openQuoteId]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setListError(null);
    api.quotations
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
        else setListError("Không tải được danh sách báo giá.");
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
    api.quotations
      .enums(token)
      .then(setEnums)
      .catch(() => setEnums(null));
  }, [token]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    load();
  }

  async function openDetail(row: QuotationRow) {
    if (!token) return;
    try {
      setDetail(await api.quotations.get(token, row.id));
    } catch {
      setListError("Không tải được chi tiết báo giá.");
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const statuses = enums?.statuses ?? [];

  if (forbidden) {
    return (
      <main className="bg">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Báo giá (403).
        </div>
      </main>
    );
  }

  return (
    <main className="bg">
      <header className="bg__head">
        <p className="eyebrow">Kinh doanh</p>
        <h1 className="bg__title">Báo giá</h1>
        <p className="bg__sub">
          Phiếu chào giá đối ngoại: tham chiếu 1 kết quả Tính giá (giá vốn) + lãi + chiết
          khấu → giá bán; chốt giá bằng snapshot copy-on-write để giá đã gửi không đổi theo
          bảng giá sống.
        </p>
      </header>

      <div className="bg__toolbar">
        <form className="bg__search" onSubmit={onSearch} role="search">
          <input
            className="input"
            placeholder="Tìm theo mã / khách…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Tìm báo giá"
          />
          <Button type="submit" variant="ghost">
            Tìm
          </Button>
        </form>

        <select
          className="input bg__statusfilter"
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

        <div className="bg__toolbar-spacer" />

        <Button
          variant="primary"
          onClick={() => {
            setEditing(null);
            setMode("create");
          }}
        >
          + Tạo báo giá
        </Button>
      </div>

      <div className="card bg__tablewrap">
        <table className="bg__table">
          <thead>
            <tr>
              <th>
                <SortBtn label="Mã" col="code" sort={sort} onSort={setSort} />
              </th>
              <th>Khách hàng</th>
              <th className="bg__num">
                <SortBtn label="Tổng giá bán" col="total" sort={sort} onSort={setSort} />
              </th>
              <th>
                <SortBtn label="Trạng thái" col="status" sort={sort} onSort={setSort} />
              </th>
              <th>
                <SortBtn label="Hạn hiệu lực" col="valid_until" sort={sort} onSort={setSort} />
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="bg__status" role="status">
                  Đang tải…
                </td>
              </tr>
            ) : listError ? (
              <tr>
                <td colSpan={5} className="bg__status">
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
                <td colSpan={5} className="bg__empty">
                  <p>Chưa có báo giá nào.</p>
                  <Button
                    variant="primary"
                    onClick={() => {
                      setEditing(null);
                      setMode("create");
                    }}
                  >
                    + Tạo báo giá
                  </Button>
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} className="bg__row" onClick={() => openDetail(r)}>
                  <td className="bg__mono">
                    {r.code}
                    <span className="bg__ver">v{r.version}</span>
                  </td>
                  <td>
                    {r.customer_name ?? (
                      <span className="bg__muted">
                        {r.customer_id != null ? `KH #${r.customer_id}` : "Chưa chọn khách"}
                      </span>
                    )}
                  </td>
                  <td className="bg__num">
                    {r.total != null ? (
                      fmtVnd(r.total)
                    ) : (
                      <span className="bg__muted" title="Chưa nạp giá vốn (Tính giá)">
                        —
                      </span>
                    )}
                  </td>
                  <td>
                    <StatusBadge status={r.status} statuses={statuses} />
                  </td>
                  <td>{fmtDate(r.valid_until)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {!loading && !listError && rows.length > 0 && (
        <div className="bg__pager">
          <span className="bg__muted">
            {total} phiếu · trang {page}/{totalPages}
          </span>
          <div className="bg__pager-btns">
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

      {mode && (
        <QuotationFormDialog
          existing={mode === "edit" ? editing : null}
          pinnedCustomer={mode === "create" ? pinned : null}
          onClose={() => {
            setMode(null);
            setEditing(null);
            setPinned(null);
          }}
          onSaved={() => {
            setMode(null);
            setEditing(null);
            setPinned(null);
            if (mode === "create") setPage(1);
            load();
          }}
        />
      )}

      {detail && (
        <QuotationDetailDialog
          quotationId={detail.id}
          statuses={statuses}
          onClose={() => setDetail(null)}
          onEdit={(d) => {
            setDetail(null);
            setEditing(d);
            setMode("edit");
          }}
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
      className={`bg__sortbtn${active ? " is-active" : ""}`}
      onClick={() => onSort(desc ? col : active ? `-${col}` : col)}
    >
      {label}
      {active && <span aria-hidden="true">{desc ? " ↓" : " ↑"}</span>}
    </button>
  );
}

function StatusBadge({ status, statuses }: { status: string; statuses: EnumOption[] }) {
  const tone =
    status === "approved"
      ? " bg__badge--ok"
      : status === "rejected" || status === "expired" || status === "cancelled"
        ? " bg__badge--off"
        : status === "sent"
          ? " bg__badge--sent"
          : "";
  return <span className={`bg__badge${tone}`}>{labelOf(statuses, status)}</span>;
}

// --- Create / Edit dialog (F2) ------------------------------------------------

function QuotationFormDialog({
  existing,
  pinnedCustomer,
  onClose,
  onSaved,
}: {
  existing: QuotationDetail | null;
  pinnedCustomer: PinnedCustomer | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const isEdit = existing != null;

  const [customerId, setCustomerId] = useState<string>(
    existing?.customer_id != null
      ? String(existing.customer_id)
      : pinnedCustomer
        ? String(pinnedCustomer.id)
        : "",
  );
  const [costingId, setCostingId] = useState<string>(
    existing?.costing_id != null ? String(existing.costing_id) : "",
  );
  const [costVon, setCostVon] = useState<string>(
    existing?.cost_von_total != null ? String(existing.cost_von_total) : "",
  );
  const [margin, setMargin] = useState<string>(String(existing?.margin ?? 0));
  const [discount, setDiscount] = useState<string>(String(existing?.discount ?? 0));
  const [validUntil, setValidUntil] = useState<string>(existing?.valid_until ?? "");

  const [costingState, setCostingState] = useState<CostingPickerOut | null>(null);
  const [fieldErr, setFieldErr] = useState<Record<string, string>>({});
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const num = (s: string): number | null => {
    if (s.trim() === "") return null;
    const n = Number(s);
    return Number.isFinite(n) ? Math.trunc(n) : null;
  };

  const cost = num(costVon);
  const marginN = num(margin) ?? 0;
  const discountN = num(discount) ?? 0;
  const total = cost == null ? null : cost + marginN - discountN;

  async function checkCosting() {
    if (!token) return;
    const id = num(costingId);
    if (id == null) {
      setCostingState(null);
      return;
    }
    try {
      const state = await api.quotations.costing(token, id);
      setCostingState(state);
      if (state.available && state.cost_von_total != null) {
        setCostVon(String(state.cost_von_total));
      }
    } catch {
      setCostingState(null);
    }
  }

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (cost != null && cost < 0) errs.cost = "Giá vốn không được âm.";
    if (marginN < 0) errs.margin = "Lãi không được âm.";
    if (discountN < 0) errs.discount = "Chiết khấu không được âm.";
    if (cost != null && discountN > cost + marginN)
      errs.discount = "Chiết khấu không được vượt quá giá vốn cộng lãi.";
    if (validUntil) {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      if (new Date(validUntil) < today) errs.validUntil = "Hạn hiệu lực không được ở quá khứ.";
    }
    setFieldErr(errs);
    return Object.keys(errs).length === 0;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    if (!validate()) return;
    setSaving(true);
    setSaveErr(null);
    const input: QuotationInput = {
      customer_id: num(customerId),
      costing_id: num(costingId),
      cost_von_total: cost,
      margin: marginN,
      discount: discountN,
      valid_until: validUntil || null,
    };
    try {
      if (isEdit && existing) {
        await api.quotations.update(token, existing.id, {
          ...input,
          row_version: existing.row_version,
        });
      } else {
        await api.quotations.create(token, input);
      }
      onSaved();
    } catch (err) {
      if (err instanceof ApiError && err.isConflict)
        setSaveErr("Phiếu vừa được thay đổi, vui lòng tải lại.");
      else if (err instanceof ApiError) setSaveErr(err.message);
      else setSaveErr("Lưu không thành công. Vui lòng thử lại.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="bg__overlay" onClick={onClose}>
      <div
        className="card bg__dialog"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bg__dialog-head">
          <h2>{isEdit ? `Sửa báo giá ${existing?.code}` : "Tạo báo giá"}</h2>
          <button type="button" className="bg__close" onClick={onClose} aria-label="Đóng">
            ✕
          </button>
        </div>

        <form className="bg__dialog-body" onSubmit={submit} noValidate>
          <div>
            <p className="bg__section-title">Tham chiếu</p>
            <div className="bg__form-grid">
              {pinnedCustomer ? (
                <label className="field">
                  <span className="field__label">Khách hàng (ghim từ CRM)</span>
                  <div className="bg__pinned">
                    <strong>{pinnedCustomer.name}</strong>
                    <span className="bg__muted">
                      {pinnedCustomer.code}
                      {pinnedCustomer.tax_code ? ` · MST ${pinnedCustomer.tax_code}` : ""}
                    </span>
                  </div>
                  <span className="bg__hint">
                    Đã ghim từ hồ sơ khách hàng — báo giá này gắn đúng khách (không nhập ID tay).
                  </span>
                </label>
              ) : (
                <label className="field">
                  <span className="field__label">Khách hàng (ID) — SEAM-14 (CRM)</span>
                  <input
                    className="input"
                    value={customerId}
                    onChange={(e) => setCustomerId(e.target.value)}
                    inputMode="numeric"
                    placeholder="ID khách hàng"
                  />
                  <span className="bg__hint">
                    Đọc tên + trạng thái công nợ (chỉ hiển thị, không chặn).
                  </span>
                </label>
              )}
              <label className="field">
                <span className="field__label">Kết quả Tính giá (ID) — SEAM-13</span>
                <div className="bg__inline">
                  <input
                    className="input"
                    value={costingId}
                    onChange={(e) => setCostingId(e.target.value)}
                    onBlur={checkCosting}
                    inputMode="numeric"
                    placeholder="ID Tính giá"
                  />
                  <Button type="button" variant="ghost" onClick={checkCosting}>
                    Nạp giá vốn
                  </Button>
                </div>
                {costingState && !costingState.available && (
                  <span className="bg__seam-tag">{costingState.message}</span>
                )}
              </label>
            </div>
          </div>

          <div>
            <p className="bg__section-title">Giá bán (giá vốn + lãi − chiết khấu)</p>
            <div className="bg__form-grid">
              <label className="field">
                <span className="field__label">Giá vốn (1 số)</span>
                <input
                  className="input"
                  value={costVon}
                  onChange={(e) => setCostVon(e.target.value)}
                  inputMode="numeric"
                  placeholder="Nhập từ màn Tính giá"
                />
                {fieldErr.cost && <span className="bg__err">{fieldErr.cost}</span>}
                <span className="bg__hint">
                  Chỉ 1 số — KHÔNG số con/khổ, số tờ, số bản kẽm, bù hao (tài liệu đối ngoại).
                </span>
              </label>
              <label className="field">
                <span className="field__label">Hạn hiệu lực</span>
                <input
                  className="input"
                  type="date"
                  value={validUntil}
                  onChange={(e) => setValidUntil(e.target.value)}
                />
                {fieldErr.validUntil && <span className="bg__err">{fieldErr.validUntil}</span>}
              </label>
              <label className="field">
                <span className="field__label">Lãi</span>
                <input
                  className="input"
                  value={margin}
                  onChange={(e) => setMargin(e.target.value)}
                  inputMode="numeric"
                />
                {fieldErr.margin && <span className="bg__err">{fieldErr.margin}</span>}
              </label>
              <label className="field">
                <span className="field__label">Chiết khấu / bậc SL</span>
                <input
                  className="input"
                  value={discount}
                  onChange={(e) => setDiscount(e.target.value)}
                  inputMode="numeric"
                />
                {fieldErr.discount && <span className="bg__err">{fieldErr.discount}</span>}
              </label>
            </div>

            <div className="bg__total">
              <span>Tổng giá bán</span>
              <strong>{fmtVnd(total)}</strong>
            </div>
          </div>

          {saveErr && (
            <div className="banner banner--error" role="alert">
              {saveErr}
            </div>
          )}

          <div className="bg__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>
              Hủy
            </Button>
            <Button type="submit" variant="primary" disabled={saving}>
              {saving ? "Đang lưu…" : isEdit ? "Lưu" : "Lưu nháp"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// --- Detail dialog (F3..F6) ---------------------------------------------------

const TRANSITION_LABELS: Record<string, string> = {
  sent: "Gửi khách",
  approved: "Duyệt",
  rejected: "Từ chối",
  expired: "Đánh dấu hết hạn",
  on_hold: "Tạm giữ",
  change_order: "Re-quote",
  cancelled: "Hủy",
};

function QuotationDetailDialog({
  quotationId,
  statuses,
  onClose,
  onEdit,
  onChanged,
}: {
  quotationId: number;
  statuses: EnumOption[];
  onClose: () => void;
  onEdit: (d: QuotationDetail) => void;
  onChanged: () => void;
}) {
  const { token } = useAuth();
  const [d, setD] = useState<QuotationDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [askCancel, setAskCancel] = useState(false);

  const reload = useCallback(async () => {
    if (!token) return;
    try {
      setD(await api.quotations.get(token, quotationId));
    } catch {
      setErr("Không tải được chi tiết báo giá.");
    }
  }, [token, quotationId]);

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
      await api.quotations.transition(token, d.id, {
        to_status: to,
        cancel_reason: to === "cancelled" ? cancelReason : null,
        row_version: d.row_version,
      });
      setAskCancel(false);
      setCancelReason("");
      await reload();
      onChanged();
    } catch (e) {
      if (e instanceof ApiError && e.isForbidden) setErr("Bạn không có quyền duyệt báo giá.");
      else if (e instanceof ApiError) setErr(e.message);
      else setErr("Thao tác không thành công.");
    } finally {
      setBusy(false);
    }
  }

  async function doRequote() {
    if (!token || !d) return;
    setBusy(true);
    setErr(null);
    try {
      const nv = await api.quotations.requote(token, d.id);
      setD(nv);
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Re-quote không thành công.");
    } finally {
      setBusy(false);
    }
  }

  async function openPdf() {
    if (!token || !d) return;
    try {
      const url = await api.quotations.pdfBlobUrl(token, d.id);
      window.open(url, "_blank", "noopener");
    } catch {
      setErr("Không xuất được PDF.");
    }
  }

  if (!d) {
    return (
      <div className="bg__overlay" onClick={onClose}>
        <div className="card bg__dialog bg__dialog--sm" onClick={(e) => e.stopPropagation()}>
          <div className="bg__dialog-body" role="status">
            Đang tải…
          </div>
        </div>
      </div>
    );
  }

  const transitions = d.allowed_transitions.filter(
    (t) => t !== "change_order", // re-quote is a dedicated button
  );

  return (
    <div className="bg__overlay" onClick={onClose}>
      <div className="card bg__dialog" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="bg__dialog-head">
          <h2>
            {d.code} <span className="bg__ver">v{d.version}</span>
          </h2>
          <button type="button" className="bg__close" onClick={onClose} aria-label="Đóng">
            ✕
          </button>
        </div>

        <div className="bg__dialog-body">
          <div className="bg__detail-top">
            <StatusBadge status={d.status} statuses={statuses} />
            {d.valid_until && (
              <span className="bg__muted">Hiệu lực đến {fmtDate(d.valid_until)}</span>
            )}
          </div>

          {d.customer && (
            <div className="bg__customer">
              <strong>{d.customer.name}</strong>
              {d.customer.tax_code && <span className="bg__muted"> · MST {d.customer.tax_code}</span>}
              <div className="bg__muted">{d.customer.credit_status_display}</div>
            </div>
          )}

          <div className="bg__pricetable">
            <div className="bg__priceline">
              <span>Giá vốn</span>
              <span>{fmtVnd(d.cost_von_total)}</span>
            </div>
            <div className="bg__priceline">
              <span>Lãi</span>
              <span>{fmtVnd(d.margin)}</span>
            </div>
            <div className="bg__priceline">
              <span>Chiết khấu</span>
              <span>− {fmtVnd(d.discount)}</span>
            </div>
            <div className="bg__priceline bg__priceline--total">
              <span>Tổng giá bán</span>
              <strong>{fmtVnd(d.total)}</strong>
            </div>
          </div>

          {(d.unit_price_snapshot || d.norm_snapshot) && (
            <div className="bg__snapshot">
              <p className="bg__section-title">Snapshot đã chốt (nội bộ)</p>
              <p className="bg__muted">
                Giá + định mức đã đóng băng copy-on-write
                {d.price_effective_from && ` từ ${fmtDate(d.price_effective_from)}`}
                {d.price_effective_to && ` đến ${fmtDate(d.price_effective_to)}`}. Giá bảng
                nguồn đổi sau không làm đổi phiếu này.
              </p>
            </div>
          )}

          {d.cancelled_at_state && (
            <div className="bg__muted">
              Đã hủy (từ trạng thái {labelOf(statuses, d.cancelled_at_state)})
              {d.cancel_reason && ` — ${d.cancel_reason}`}
            </div>
          )}

          {d.versions.length > 1 && (
            <div>
              <p className="bg__section-title">Lịch sử version</p>
              <ul className="bg__versions">
                {d.versions.map((v) => (
                  <li key={v.id} className={v.id === d.id ? "is-current" : ""}>
                    <span className="bg__mono">v{v.version}</span>
                    <StatusBadge status={v.status} statuses={statuses} />
                    <span className="bg__muted">{fmtVnd(v.total)}</span>
                  </li>
                ))}
              </ul>
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

          <div className="bg__dialog-actions bg__dialog-actions--wrap">
            {d.status === "draft" && (
              <Button type="button" variant="ghost" onClick={() => onEdit(d)}>
                Sửa
              </Button>
            )}
            <Button type="button" variant="ghost" onClick={openPdf}>
              Xuất PDF
            </Button>
            {d.allowed_transitions.includes("change_order") && (
              <Button type="button" variant="ghost" onClick={doRequote} disabled={busy}>
                Re-quote
              </Button>
            )}
            {transitions.map((t) => (
              <Button
                key={t}
                type="button"
                variant={t === "approved" ? "primary" : "ghost"}
                disabled={busy || (t === "approved" && !d.can_approve)}
                onClick={() => doTransition(t)}
                title={t === "approved" && !d.can_approve ? "Cần quyền duyệt (ngưỡng X/Y)" : undefined}
              >
                {TRANSITION_LABELS[t] ?? t}
              </Button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
