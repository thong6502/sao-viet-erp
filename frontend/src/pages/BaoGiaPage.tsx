// Báo giá (Quotation / Quote) — spec-09, Phase 2B/2C/2D.
// Danh sách phiếu (mã+version, khách, tổng giá bán, trạng thái, hạn hiệu lực) + Tạo/Sửa
// (H-V-I structure, multi-quantity spreadsheet pricing table, version timeline, PDF preview & Order handoff).
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type EnumOption,
  type PinnedCustomer,
  type QuotationActivity,
  type QuotationDetail,
  type QuotationEnumsOut,
  type QuotationRow,
  type QuotationStats,
  type QuotePick,
  type QuoteItemDetail,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { StatusTabs } from "../components/StatusTabs";
import svnLogoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import "./bao-gia.css";

// Thông tin công ty in trên báo giá — Sao Việt Nhật.
// Luật dự án "không hardcode số liệu": các trường pháp lý để trống chờ khảo sát,
// điền giá trị thật khi có (địa chỉ/MST/điện thoại/email đăng ký kinh doanh).
const SVN_COMPANY = {
  name: "CÔNG TY SAO VIỆT NHẬT",
  nameEn: "Sao Viet Nhat",
  address: "—",
  taxCode: "—",
  phone: "—",
  email: "—",
  website: "—",
  sender: "—",
  senderEmail: "—",
};

const PAGE_SIZE = 10;

function labelOf(options: EnumOption[], value: string | null): string {
  if (!value) return "—";
  return options.find((o) => o.value === value)?.label ?? value;
}

function fmtVnd(v: number | null | undefined): string {
  if (v == null) return "—";
  return Math.round(v).toLocaleString("vi-VN") + " đ";
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
  estimateId = null,
  navigate,
}: {
  pinnedCustomer?: PinnedCustomer | null;
  openQuoteId?: number | null;
  estimateId?: number | null;
  navigate?: (id: string, params?: any) => void;
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
  
  // Pre-pinned entities
  const [pinned, setPinned] = useState<PinnedCustomer | null>(null);
  const [preSelectedEstimateId, setPreSelectedEstimateId] = useState<number | null>(null);

  const [stats, setStats] = useState<QuotationStats | null>(null);

  // Arriving from CRM with a customer to pre-pin
  useEffect(() => {
    if (pinnedCustomer) {
      setPinned(pinnedCustomer);
      setEditing(null);
      setPreSelectedEstimateId(null);
      setMode("create");
    }
  }, [pinnedCustomer]);

  // Arriving from TinhGia with an estimate to pre-select
  useEffect(() => {
    if (estimateId) {
      setPreSelectedEstimateId(estimateId);
      setEditing(null);
      setPinned(null);
      setMode("create");
    }
  }, [estimateId]);

  // Arriving from CRM history/audit drill-through
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

    // Số đếm cho thanh tab
    api.quotations.stats(token).then(setStats).catch(() => setStats(null));
  }, [token, q, statusFilter, sort, page]);

  useEffect(() => {
    load();
  }, [load]);

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

  // Detail = trang 2 cột in-page (thay danh sách), giống prototype inan5 (viewList ⇄ viewEditor).
  if (detail) {
    return (
      <QuotationDetailView
        quotationId={detail.id}
        statuses={statuses}
        navigate={navigate}
        onClose={() => setDetail(null)}
        onChanged={() => load()}
      />
    );
  }

  return (
    <main className="bg">
      <header className="bg__head">
        <p className="eyebrow">Kinh doanh</p>
        <h1 className="bg__title">Báo giá thương mại</h1>
        <p className="bg__sub">
          Quản lý báo giá chuyên nghiệp theo mô hình Header-Version-Item (H-V-I). Hỗ trợ nhiều mức số lượng độc lập, 
          lịch sử phiên bản đông cứng, bảo mật giá vốn nội bộ và tự động bàn giao sang Đơn hàng bán.
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

        <div className="bg__toolbar-spacer" />

        {/* BG-3/4: báo giá LUÔN khởi từ 1 Phiếu tính giá (1 PTG → 1 BG). Bỏ modal đa-pick cũ — nút
            này điều hướng sang màn Phiếu tính giá, ở đó bấm "Báo giá →" để tạo/mở báo giá. */}
        <Button variant="accent" onClick={() => navigate?.("tinh-gia")}>
          + Báo giá mới (từ Phiếu tính giá)
        </Button>
      </div>

      {/* Tab trạng thái đếm số — "Cần xử lý" = nháp + đã gửi chờ khách */}
      <div style={{ margin: "12px 0 16px" }}>
        <StatusTabs
          tabs={[
            { key: "", label: "Tất cả", count: stats?.total },
            { key: "need_action", label: "Cần xử lý", count: stats?.need_action, tone: "alert" },
            { key: "draft", label: "Soạn", count: stats?.draft },
            // "Chờ duyệt" = báo giá đặc thù đã Trình duyệt (list đã lọc theo phạm vi → người duyệt
            // thấy đúng "chờ TÔI duyệt"). Tone alert để nổi bật việc cần quyết định.
            { key: "pending_approval", label: "Chờ duyệt", count: stats?.pending_approval, tone: "alert" },
            { key: "approved", label: "Đã duyệt", count: stats?.approved },
            { key: "sent", label: "Đã gửi khách", count: stats?.sent },
            { key: "accepted", label: "Khách chốt", count: stats?.accepted },
            { key: "converted_to_order", label: "Đã lên đơn", count: stats?.converted_to_order },
            { key: "rejected", label: "Từ chối", count: stats?.rejected },
          ]}
          active={statusFilter}
          onChange={(k) => {
            setStatusFilter(k);
            setPage(1);
          }}
        />
      </div>

      <div className="card bg__tablewrap">
        <table className="bg__table">
          <thead>
            <tr>
              <th>
                <SortBtn label="Mã báo giá" col="code" sort={sort} onSort={setSort} />
              </th>
              <th>Khách hàng</th>
              <th>Sản phẩm · Tham chiếu</th>
              <th className="bg__num">
                <SortBtn label="Giá bán (đã VAT)" col="total" sort={sort} onSort={setSort} />
              </th>
              <th>
                <SortBtn label="Trạng thái" col="status" sort={sort} onSort={setSort} />
              </th>
              <th>Cập nhật</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="bg__status" role="status">
                  Đang tải danh sách báo giá…
                </td>
              </tr>
            ) : listError ? (
              <tr>
                <td colSpan={6} className="bg__status">
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
                <td colSpan={6} className="bg__empty">
                  <p>Chưa có báo giá thương mại nào được tạo.</p>
                  <Button
                    variant="accent"
                    onClick={() => {
                      setEditing(null);
                      setPreSelectedEstimateId(null);
                      setPinned(null);
                      setMode("create");
                    }}
                  >
                    + Tạo báo giá đầu tiên
                  </Button>
                </td>
              </tr>
            ) : (
              rows.map((r) => {
                // Tuổi phiếu: đã gửi N ngày chưa có phản hồi → nhắc follow-up
                const sentDays =
                  r.status === "sent" && r.sent_at
                    ? Math.floor((Date.now() - new Date(r.sent_at).getTime()) / 86_400_000)
                    : null;
                return (
                  <tr key={r.id} className="bg__row" onClick={() => openDetail(r)}>
                    <td className="bg__mono" style={{ fontWeight: "bold" }}>
                      {r.code}
                      <span className="bg__ver">v{r.version}</span>
                      {(r.version_count ?? 1) > 1 && (
                        <span className="tgroup__subdesc">{r.version_count} phiên bản</span>
                      )}
                    </td>
                    <td>
                      {r.customer_name ?? (
                        <span className="bg__muted">
                          {r.customer_id != null ? `KH #${r.customer_id}` : "Chưa chọn khách"}
                        </span>
                      )}
                    </td>
                    <td>
                      {r.product_summary ?? <span className="bg__muted">—</span>}
                      {r.estimate_refs && r.estimate_refs.length > 0 && (
                        <span className="tgroup__subdesc bg__mono">↳ {r.estimate_refs.join(", ")}</span>
                      )}
                    </td>
                    <td className="bg__num" style={{ color: "var(--rust-deep)", fontWeight: "bold" }}>
                      {r.total != null ? fmtVnd(r.total) : <span className="bg__muted">—</span>}
                      {r.margin_percent != null && (
                        <span className="tgroup__subdesc">biên {Math.round(r.margin_percent)}%</span>
                      )}
                    </td>
                    <td>
                      <StatusBadge status={r.status} statuses={statuses} />
                      {sentDays !== null && sentDays >= 0 && (
                        <span
                          className="tgroup__subdesc"
                          style={sentDays >= 7 ? { color: "var(--amber-deep)", fontWeight: 600 } : undefined}
                        >
                          Đã gửi {sentDays} ngày{sentDays >= 7 ? " · cần follow-up" : ""}
                        </span>
                      )}
                    </td>
                    <td>
                      <span style={{ whiteSpace: "nowrap" }}>{fmtDate(r.updated_at ?? null)}</span>
                      {r.salesperson_name && <span className="tgroup__subdesc">{r.salesperson_name}</span>}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {!loading && !listError && rows.length > 0 && (
        <div className="bg__pager">
          <span className="bg__muted">
            Tìm thấy {total} phiếu báo giá · Trang {page}/{totalPages}
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
          initialEstimateId={mode === "create" ? preSelectedEstimateId : null}
          onClose={() => {
            setMode(null);
            setEditing(null);
            setPinned(null);
            setPreSelectedEstimateId(null);
          }}
          onSaved={() => {
            setMode(null);
            setEditing(null);
            setPinned(null);
            setPreSelectedEstimateId(null);
            if (mode === "create") setPage(1);
            load();
          }}
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
    status === "accepted"
      ? " bg__badge--ok"
      : status === "rejected" || status === "expired" || status === "cancelled"
        ? " bg__badge--off"
        : status === "sent"
          ? " bg__badge--sent"
          : "";
  return <span className={`bg__badge${tone}`}>{labelOf(statuses, status)}</span>;
}

// --- Create / Edit dialog (F2 & Phase 2B spreadsheet pricing) ------------------------------------------------

interface LocalItem {
  id: number;
  /** Phiếu tính giá gốc của dòng (đa phiếu / 1 báo giá) */
  estimate_id: number | null;
  estimate_ref: string;
  estimate_option_id: number | null;
  line_no: number;
  product_type: string;
  product_name: string;
  quantity: number;
  unit: string;
  total_cost_snapshot: number;
  
  // Interactive inputs
  included: boolean;
  margin_percent: number;
  manual_selling_price: number | null;
  manual_unit_price: number | null;
  discount_amount: number;
  discount_percent: number;
  vat_percent: number;
  rounding: string;
  note: string;
  
  // Real-time calculated properties
  selling_price: number;
  unit_price: number;
  actual_margin: number;
  vat_amount: number;
  final_amount: number;
}

function QuotationFormDialog({
  existing,
  pinnedCustomer,
  initialEstimateId,
  onClose,
  onSaved,
}: {
  existing: QuotationDetail | null;
  pinnedCustomer: PinnedCustomer | null;
  initialEstimateId: number | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const isEdit = existing != null;

  const [customerId, setCustomerId] = useState<string>(
    existing?.customer_id != null
      ? String(existing.customer_id)
      : pinnedCustomer
        ? String(pinnedCustomer.id)
        : "",
  );
  // Đa phiếu: giỏ các phiếu tính giá đã pick (mỗi phiếu kéo các mức SL vào bảng định giá)
  const [picked, setPicked] = useState<{ id: number; estimate_number: string; product_name: string }[]>([]);
  const [pendingEstimateId, setPendingEstimateId] = useState<string>("");
  const [validUntil, setValidUntil] = useState<string>(existing?.valid_until ?? "");
  const [paymentTerms, setPaymentTerms] = useState<string>(existing?.payment_terms ?? "Tạm ứng 50% khi chốt đơn, 50% còn lại thanh toán khi giao hàng.");
  const [deliveryTerms, setDeliveryTerms] = useState<string>(existing?.delivery_terms ?? "Giao hàng tận nơi tại TP. Hồ Chí Minh.");
  const [deliveryAddress, setDeliveryAddress] = useState<string>(existing?.delivery_address ?? "");

  const [estimates, setEstimates] = useState<{ id: number; estimate_number: string; product_name: string }[]>([]);
  const [customers, setCustomers] = useState<{ id: number; name: string; code: string }[]>([]);
  
  // Spreadsheet Local state
  const [localItems, setLocalItems] = useState<LocalItem[]>([]);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  // Bulk action states & functions
  const [bulkMargin, setBulkMargin] = useState("");
  const [bulkDiscountPct, setBulkDiscountPct] = useState("");
  const [bulkVat, setBulkVat] = useState("10");

  const applyBulkMargin = () => {
    const val = Number(bulkMargin);
    if (Number.isNaN(val) || val < 0) return;
    setLocalItems((prev) =>
      prev.map((item) =>
        item.included
          ? calculateItemCalculatedFields({
              ...item,
              margin_percent: val,
              manual_selling_price: null,
              manual_unit_price: null,
            })
          : item
      )
    );
  };

  const applyBulkDiscountPct = () => {
    const val = Number(bulkDiscountPct);
    if (Number.isNaN(val) || val < 0 || val > 100) return;
    setLocalItems((prev) =>
      prev.map((item) =>
        item.included
          ? calculateItemCalculatedFields({
              ...item,
              discount_percent: val,
              discount_amount: 0,
            })
          : item
      )
    );
  };

  const applyBulkVat = () => {
    const val = Number(bulkVat);
    setLocalItems((prev) =>
      prev.map((item) =>
        item.included
          ? calculateItemCalculatedFields({
              ...item,
              vat_percent: val,
            })
          : item
      )
    );
  };

  // Load catalogs
  useEffect(() => {
    if (!token) return;
    api.customers.list(token, { page: 1, size: 200 }).then((r) => setCustomers(r.items)).catch(() => {});
    api.estimates.list(token, { status: "calculated", page: 1, size: 200 }).then((r) => setEstimates(r.items)).catch(() => {});
  }, [token]);

  // Load items from database if editing
  useEffect(() => {
    if (isEdit && existing) {
      const items = existing.items.map((item) => {
        return calculateItemCalculatedFields({
          id: item.id,
          estimate_id: item.estimate_id ?? null,
          estimate_ref: item.estimate_number ?? "",
          estimate_option_id: item.estimate_option_id,
          line_no: item.line_no,
          product_type: item.product_type,
          product_name: item.product_name,
          quantity: item.quantity,
          unit: item.unit,
          total_cost_snapshot: item.total_cost_snapshot,
          included: true,
          margin_percent: item.margin_percent,
          manual_selling_price: item.selling_price !== (item.total_cost_snapshot / (1 - item.margin_percent / 100)) ? item.selling_price : null,
          manual_unit_price: null,
          discount_amount: item.discount_amount,
          discount_percent: 0,
          vat_percent: item.vat_percent,
          rounding: "no_rounding",
          note: item.note ?? "",
        });
      });
      setLocalItems(items);
    }
  }, [isEdit, existing]);

  // Pre-pick từ trang Tính giá (nút "Tạo báo giá") — chờ catalog phiếu load xong để lấy mã/tên
  useEffect(() => {
    if (isEdit || !initialEstimateId || estimates.length === 0) return;
    if (picked.some((p) => p.id === initialEstimateId)) return;
    const est = estimates.find((e) => e.id === initialEstimateId);
    if (est) addPick(est);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isEdit, initialEstimateId, estimates]);

  /** Pick 1 phiếu: thêm vào giỏ + kéo các mức SL của nó vào bảng định giá (append). */
  async function addPick(est: { id: number; estimate_number: string; product_name: string }) {
    if (!token || picked.some((p) => p.id === est.id)) return;
    setSaveErr(null);
    try {
      const state = await api.quotations.costing(token, est.id);
      if (!state.available || !state.options || state.options.length === 0) {
        setSaveErr(state.message ?? `Phiếu ${est.estimate_number} không có mức số lượng khả dụng.`);
        return;
      }
      setPicked((prev) => [...prev, est]);
      setLocalItems((prev) => {
        const base = prev.length;
        const items = state.options!.map((opt, idx) =>
          calculateItemCalculatedFields({
            id: -(base + idx + 1), // temp negative ID for unsaved items
            estimate_id: est.id,
            estimate_ref: est.estimate_number,
            estimate_option_id: opt.id,
            line_no: base + idx + 1,
            product_type: "",
            product_name: est.product_name,
            quantity: opt.quantity,
            unit: "cái",
            total_cost_snapshot: opt.total_cost,
            included: true,
            margin_percent: opt.margin_percent,
            manual_selling_price: null,
            manual_unit_price: null,
            discount_amount: opt.discount_amount,
            discount_percent: 0,
            vat_percent: opt.vat_percent,
            rounding: "no_rounding",
            note: "",
          }),
        );
        return [...prev, ...items];
      });
    } catch {
      setSaveErr(`Không tải được mức số lượng của phiếu ${est.estimate_number}.`);
    }
  }

  function removePick(estId: number) {
    setPicked((prev) => prev.filter((p) => p.id !== estId));
    setLocalItems((prev) => prev.filter((i) => i.estimate_id !== estId));
  }

  // Pure mathematical pricing calculator matching backend formulas (Phase 2B)
  function calculateItemCalculatedFields(item: Omit<LocalItem, "selling_price" | "unit_price" | "actual_margin" | "vat_amount" | "final_amount">): LocalItem {
    const qty = Math.max(1, item.quantity);
    const cost = Number(item.total_cost_snapshot);
    let sellingPrice = 0;

    if (item.manual_selling_price !== null && item.manual_selling_price > 0) {
      sellingPrice = Number(item.manual_selling_price);
    } else if (item.manual_unit_price !== null && item.manual_unit_price > 0) {
      sellingPrice = Number(item.manual_unit_price) * qty;
    } else {
      const marginPct = Math.min(99.99, Math.max(0.0, Number(item.margin_percent)));
      sellingPrice = cost / (1.0 - marginPct / 100.0);
    }

    // Apply Rounding
    if (item.rounding === "round_up_1000") {
      sellingPrice = Math.ceil(sellingPrice / 1000) * 1000;
    } else if (item.rounding === "round_up_5000") {
      sellingPrice = Math.ceil(sellingPrice / 5000) * 5000;
    } else if (item.rounding === "round_up_10000") {
      sellingPrice = Math.ceil(sellingPrice / 10000) * 10000;
    }

    // Actual Margin
    const actualMargin = sellingPrice > 0 ? ((sellingPrice - cost) / sellingPrice) * 100 : 0;

    // Discount
    let discAmount = Number(item.discount_amount);
    if (item.discount_percent > 0) {
      discAmount = sellingPrice * (Number(item.discount_percent) / 100);
    }
    discAmount = Math.min(sellingPrice, Math.max(0.0, discAmount));

    const subtotal = Math.max(0.0, sellingPrice - discAmount);
    const vatAmount = subtotal * (Number(item.vat_percent) / 100);
    const finalAmount = subtotal + vatAmount;
    const unitPrice = sellingPrice / qty;

    return {
      ...item,
      selling_price: sellingPrice,
      unit_price: unitPrice,
      actual_margin: actualMargin,
      discount_amount: discAmount,
      vat_amount: vatAmount,
      final_amount: finalAmount,
    };
  }

  // Update specific field in table reactively
  const handleItemChange = (index: number, patch: Partial<LocalItem>) => {
    setLocalItems((prev) => {
      const updated = prev.map((item, idx) => {
        if (idx === index) {
          const merged = { ...item, ...patch } as LocalItem;
          // Clear opposite manual values to avoid conflicts
          if (patch.margin_percent !== undefined) {
            merged.manual_selling_price = null;
            merged.manual_unit_price = null;
          } else if (patch.manual_selling_price !== undefined) {
            merged.manual_unit_price = null;
          } else if (patch.manual_unit_price !== undefined) {
            merged.manual_selling_price = null;
          }
          return calculateItemCalculatedFields(merged);
        }
        return item;
      });
      return updated;
    });
  };

  const selectedCount = localItems.filter((i) => i.included).length;
  
  // Calculate Quote Totals in UI
  const totalCost = localItems.filter((i) => i.included).reduce((acc, i) => acc + i.total_cost_snapshot, 0);
  const totalSubtotal = localItems.filter((i) => i.included).reduce((acc, i) => acc + i.selling_price, 0);
  const totalDiscount = localItems.filter((i) => i.included).reduce((acc, i) => acc + i.discount_amount, 0);
  const totalVat = localItems.filter((i) => i.included).reduce((acc, i) => acc + i.vat_amount, 0);
  const totalFinal = localItems.filter((i) => i.included).reduce((acc, i) => acc + i.final_amount, 0);

  function validate(): boolean {
    setSaveErr(null);
    if (!customerId) {
      setSaveErr("Vui lòng chọn khách hàng.");
      return false;
    }
    if (!isEdit && picked.length === 0) {
      setSaveErr("Vui lòng pick ít nhất một phiếu tính giá.");
      return false;
    }
    if (selectedCount === 0) {
      setSaveErr("Cần chọn ít nhất một mức số lượng đưa vào báo giá.");
      return false;
    }
    if (validUntil) {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      if (new Date(validUntil) < today) {
        setSaveErr("Hạn hiệu lực không được ở quá khứ.");
        return false;
      }
    }
    return true;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token || busy) return;
    if (!validate()) return;
    
    setBusy(true);
    setSaveErr(null);

    const activeItems = localItems.filter((i) => i.included);

    try {
      if (isEdit && existing) {
        // Update existing draft version
        await api.quotations.update(token, existing.id, {
          customer_id: Number(customerId),
          valid_until: validUntil || null,
          payment_terms: paymentTerms,
          delivery_terms: deliveryTerms,
          delivery_address: deliveryAddress,
          items: activeItems.map((item) => ({
            id: item.id,
            margin_percent: item.margin_percent,
            manual_selling_price: item.manual_selling_price,
            manual_unit_price: item.manual_unit_price,
            discount_amount: item.discount_amount,
            discount_percent: item.discount_percent,
            vat_percent: item.vat_percent,
            rounding: item.rounding,
            note: item.note,
          })),
        });
      } else {
        // Create new quotation (đa phiếu: picks[]) + save custom item prices sequentially
        const picks: QuotePick[] = picked
          .map((p) => ({
            estimate_id: p.id,
            option_ids: activeItems
              .filter((i) => i.estimate_id === p.id && i.estimate_option_id !== null)
              .map((i) => i.estimate_option_id!),
          }))
          .filter((p) => p.option_ids.length > 0);

        const createdQuote = await api.quotations.create(token, {
          customer_id: Number(customerId),
          picks,
          valid_until: validUntil || null,
          payment_terms: paymentTerms,
          delivery_terms: deliveryTerms,
          delivery_address: deliveryAddress,
        });

        // Backend created draft item rows. We map local items to the newly created DB item IDs and save them.
        const createdDetail = await api.quotations.get(token, createdQuote.id);
        const itemIdsMapping = createdDetail.items.map((dbItem) => {
          // match by quantity option
          const localMatch = activeItems.find((li) => li.estimate_option_id === dbItem.estimate_option_id);
          return localMatch ? { ...localMatch, id: dbItem.id } : null;
        }).filter((x) => x !== null) as LocalItem[];

        await api.quotations.update(token, createdQuote.id, {
          customer_id: Number(customerId),
          valid_until: validUntil || null,
          payment_terms: paymentTerms,
          delivery_terms: deliveryTerms,
          delivery_address: deliveryAddress,
          items: itemIdsMapping.map((item) => ({
            id: item.id,
            margin_percent: item.margin_percent,
            manual_selling_price: item.manual_selling_price,
            manual_unit_price: item.manual_unit_price,
            discount_amount: item.discount_amount,
            discount_percent: item.discount_percent,
            vat_percent: item.vat_percent,
            rounding: item.rounding,
            note: item.note,
          })),
        });
      }
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setSaveErr(err.message);
      else setSaveErr("Lưu thất bại. Vui lòng kiểm tra lại dữ liệu.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg__overlay" onClick={onClose}>
      <div className="card bg__dialog bg__dialog-fullscreen" onClick={(e) => e.stopPropagation()}>
        <div className="bg__dialog-head">
          <h2>{isEdit ? `Chỉnh sửa báo giá · ${existing?.code}` : "Tạo báo giá thương mại"}</h2>
          <button type="button" className="bg__close" onClick={onClose} aria-label="Đóng">✕</button>
        </div>

        <form className="bg__dialog-body" onSubmit={submit} noValidate>
          <div className="bg__form-main-columns">
            {/* Left Inputs Card */}
            <div className="bg__form-left-panel">
              <p className="bg__section-title">1. Thông tin chung</p>
              
              <div className="bg__form-grid">
                {pinnedCustomer ? (
                  <div className="field">
                    <span className="field__label">Khách hàng (Ghim từ CRM)</span>
                    <div className="bg__pinned">
                      <strong>{pinnedCustomer.name}</strong>
                      <span className="bg__muted">Mã: {pinnedCustomer.code}</span>
                    </div>
                  </div>
                ) : (
                  <div className="field">
                    <span className="field__label">Khách hàng *</span>
                    <CustomerCombobox
                      customers={customers}
                      value={customerId ? Number(customerId) : null}
                      onChange={(id) => setCustomerId(id ? String(id) : "")}
                      disabled={isEdit}
                      placeholder="— Chọn Khách hàng (CRM) —"
                    />
                  </div>
                )}

                <label className="field">
                  <span className="field__label">Hạn hiệu lực</span>
                  <input className="input" type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
                </label>
              </div>

              {/* Picker đa phiếu: báo giá KHÔNG soạn tay — mọi dòng pick từ phiếu tính giá đã tính */}
              {!isEdit && (
                <div style={{ marginTop: "16px" }}>
                  <span className="field__label">Pick phiếu tính giá vào báo giá * <span className="bg__muted">(được chọn nhiều phiếu — nhiều sản phẩm trong 1 báo giá)</span></span>
                  <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
                    <select
                      className="input"
                      value={pendingEstimateId}
                      onChange={(e) => setPendingEstimateId(e.target.value)}
                      style={{ flex: 1 }}
                    >
                      <option value="">— Chọn phiếu Đã tính để thêm —</option>
                      {estimates
                        .filter((est) => !picked.some((p) => p.id === est.id))
                        .map((est) => (
                          <option key={est.id} value={est.id}>{est.estimate_number} — {est.product_name}</option>
                        ))}
                    </select>
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => {
                        const est = estimates.find((e) => e.id === Number(pendingEstimateId));
                        if (est) {
                          addPick(est);
                          setPendingEstimateId("");
                        }
                      }}
                      disabled={!pendingEstimateId}
                    >
                      ＋ Thêm phiếu
                    </Button>
                  </div>
                  {picked.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "8px" }}>
                      {picked.map((p) => (
                        <span
                          key={p.id}
                          className="bg__mono"
                          style={{ display: "inline-flex", alignItems: "center", gap: "6px", background: "var(--rust-soft)", border: "1px solid var(--rust)", color: "var(--rust-deep)", borderRadius: "999px", padding: "3px 10px", fontSize: "12px" }}
                        >
                          ↳ {p.estimate_number} · {p.product_name}
                          <button
                            type="button"
                            onClick={() => removePick(p.id)}
                            style={{ border: "none", background: "none", cursor: "pointer", color: "var(--rust-deep)", fontWeight: 700, padding: 0, lineHeight: 1 }}
                            aria-label={`Bỏ ${p.estimate_number}`}
                          >
                            ✕
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="bg__form-grid" style={{ marginTop: "16px" }}>
                <label className="field">
                  <span className="field__label">Địa chỉ giao hàng</span>
                  <input className="input" value={deliveryAddress} onChange={(e) => setDeliveryAddress(e.target.value)} placeholder="Nhập địa chỉ giao hàng..." />
                </label>
              </div>

              <p className="bg__section-title" style={{ marginTop: "24px" }}>2. Điều khoản thương mại</p>
              <div className="bg__form-grid">
                <label className="field">
                  <span className="field__label">Điều khoản thanh toán</span>
                  <textarea className="input bg__textarea" value={paymentTerms} onChange={(e) => setPaymentTerms(e.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Điều khoản giao nhận</span>
                  <textarea className="input bg__textarea" value={deliveryTerms} onChange={(e) => setDeliveryTerms(e.target.value)} />
                </label>
              </div>

            </div>

            {/* Pricing spreadsheet panel */}
            <div className="bg__form-right-panel">
              <p className="bg__section-title">3. Bảng định giá đa số lượng (Interactive Grid)</p>
              
              {localItems.length === 0 ? (
                <div className="bg__empty-state-placeholder">
                  <svg className="bg__empty-state-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <span style={{ fontSize: "14px", fontWeight: "bold", color: "var(--ink)" }}>Chưa pick phiếu tính giá nào</span>
                  <p className="bg__hint" style={{ textAlign: "center", maxWidth: "340px", margin: "4px auto 0", lineHeight: 1.4 }}>
                    Dùng ô <strong>"Pick phiếu tính giá vào báo giá"</strong> bên cột trái — mỗi phiếu kéo các mức
                    số lượng (kèm giá vốn khóa) vào bảng này. Pick nhiều phiếu nếu khách hỏi nhiều sản phẩm.
                  </p>
                </div>
              ) : (
                <>
                  {localItems.length > 0 && (
                    <div className="bg__spreadsheet-bulk-actions">
                      <span className="bg__bulk-label">⚡ Áp dụng nhanh:</span>
                      
                      <div className="bg__bulk-group">
                        <input
                          type="number"
                          className="input input--sm bg__mono"
                          style={{ width: "80px" }}
                          placeholder="Margin %"
                          value={bulkMargin}
                          onChange={(e) => setBulkMargin(e.target.value)}
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={applyBulkMargin}
                          title="Áp dụng Margin % cho các dòng được chọn"
                          style={{ padding: "4px 8px", fontSize: "12px" }}
                        >
                          Set Margin
                        </Button>
                      </div>

                      <div className="bg__bulk-group">
                        <input
                          type="number"
                          className="input input--sm bg__mono"
                          style={{ width: "80px" }}
                          placeholder="C.khấu %"
                          value={bulkDiscountPct}
                          onChange={(e) => setBulkDiscountPct(e.target.value)}
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={applyBulkDiscountPct}
                          title="Áp dụng chiết khấu % cho các dòng được chọn"
                          style={{ padding: "4px 8px", fontSize: "12px" }}
                        >
                          Set C.khấu %
                        </Button>
                      </div>

                      <div className="bg__bulk-group">
                        <select
                          className="input input--sm"
                          style={{ width: "90px" }}
                          value={bulkVat}
                          onChange={(e) => setBulkVat(e.target.value)}
                        >
                          <option value="0">0%</option>
                          <option value="8">8%</option>
                          <option value="10">10%</option>
                        </select>
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={applyBulkVat}
                          title="Áp dụng thuế VAT cho các dòng được chọn"
                          style={{ padding: "4px 8px", fontSize: "12px" }}
                        >
                          Set VAT
                        </Button>
                      </div>
                    </div>
                  )}
                  
                  <div className="bg__spreadsheet-container">
                    <table className="bg__spreadsheet">
                    <thead>
                      <tr>
                        <th style={{ width: "40px" }}>Chọn</th>
                        <th>Sản phẩm</th>
                        <th>Số lượng</th>
                        <th>Giá vốn</th>
                        <th style={{ width: "90px" }}>Margin (%)</th>
                        <th style={{ width: "120px" }}>Giá bán tổng</th>
                        <th style={{ width: "100px" }}>Đơn giá</th>
                        <th style={{ width: "110px" }}>C.khấu (đ)</th>
                        <th style={{ width: "90px" }}>Làm tròn</th>
                        <th style={{ width: "80px" }}>VAT</th>
                        <th>Tổng thanh toán</th>
                        <th>Ghi chú</th>
                      </tr>
                    </thead>
                    <tbody>
                      {localItems.map((item, idx) => {
                        const isUnderCost = item.selling_price < item.total_cost_snapshot;
                        return (
                          <tr key={item.id} className={item.included ? "is-selected" : "is-excluded"}>
                            <td style={{ textAlign: "center" }}>
                              <input
                                type="checkbox"
                                checked={item.included}
                                onChange={(e) => handleItemChange(idx, { included: e.target.checked })}
                              />
                            </td>
                            <td>
                              {item.product_name || <span className="bg__muted">—</span>}
                              {item.estimate_ref && (
                                <span className="tgroup__subdesc bg__mono">↳ {item.estimate_ref}</span>
                              )}
                            </td>
                            <td className="bg__mono font-bold">{item.quantity.toLocaleString("vi-VN")}</td>
                            <td className="bg__mono text-gray-500">{fmtVnd(item.total_cost_snapshot)}</td>
                            <td>
                              <input
                                className="input input--sm bg__mono"
                                type="number"
                                step="0.5"
                                value={item.margin_percent}
                                onChange={(e) => handleItemChange(idx, { margin_percent: Number(e.target.value) })}
                                disabled={!item.included}
                              />
                            </td>
                            <td>
                              <input
                                className={`input input--sm bg__mono ${isUnderCost ? "input--error" : ""}`}
                                type="number"
                                placeholder={Math.round(item.selling_price).toString()}
                                value={item.manual_selling_price || ""}
                                onChange={(e) => handleItemChange(idx, { manual_selling_price: e.target.value ? Number(e.target.value) : null })}
                                disabled={!item.included}
                              />
                              {isUnderCost && (
                                <span className="bg__item-warning">⚠️ Dưới vốn</span>
                              )}
                            </td>
                            <td>
                              <input
                                className="input input--sm bg__mono"
                                type="number"
                                placeholder={Math.round(item.unit_price).toString()}
                                value={item.manual_unit_price || ""}
                                onChange={(e) => handleItemChange(idx, { manual_unit_price: e.target.value ? Number(e.target.value) : null })}
                                disabled={!item.included}
                              />
                            </td>
                            <td>
                              <input
                                className="input input--sm bg__mono"
                                type="number"
                                value={item.discount_amount}
                                onChange={(e) => handleItemChange(idx, { discount_amount: Number(e.target.value) })}
                                disabled={!item.included}
                              />
                            </td>
                            <td>
                              <select
                                className="input input--sm"
                                value={item.rounding}
                                onChange={(e) => handleItemChange(idx, { rounding: e.target.value })}
                                disabled={!item.included}
                              >
                                <option value="no_rounding">K.tròn</option>
                                <option value="round_up_1000">Lên 1k</option>
                                <option value="round_up_5000">Lên 5k</option>
                                <option value="round_up_10000">Lên 10k</option>
                              </select>
                            </td>
                            <td>
                              <select
                                className="input input--sm"
                                value={item.vat_percent}
                                onChange={(e) => handleItemChange(idx, { vat_percent: Number(e.target.value) })}
                                disabled={!item.included}
                              >
                                <option value={0}>0%</option>
                                <option value={8}>8%</option>
                                <option value={10}>10%</option>
                              </select>
                            </td>
                            <td className="bg__mono font-bold text-rust" style={{ textAlign: "right" }}>
                              <span key={item.final_amount} className="bg__cell-flash">
                                {fmtVnd(item.final_amount)}
                              </span>
                            </td>
                            <td>
                              <input
                                className="input input--sm"
                                value={item.note}
                                onChange={(e) => handleItemChange(idx, { note: e.target.value })}
                                placeholder="Ghi chú SP..."
                                disabled={!item.included}
                              />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}

              {/* Totals panel */}
              {selectedCount > 0 && (
                <div className="bg__form-totals-panel">
                  <div className="bg__total-row">
                    <span>Tổng giá vốn (Nội bộ):</span>
                    <span className="bg__mono">{fmtVnd(totalCost)}</span>
                  </div>
                  <div className="bg__total-row">
                    <span>Tổng giá bán thương mại:</span>
                    <span className="bg__mono">{fmtVnd(totalSubtotal)}</span>
                  </div>
                  <div className="bg__total-row">
                    <span>Tổng chiết khấu:</span>
                    <span className="bg__mono text-danger">- {fmtVnd(totalDiscount)}</span>
                  </div>
                  <div className="bg__total-row">
                    <span>Thuế VAT:</span>
                    <span className="bg__mono">{fmtVnd(totalVat)}</span>
                  </div>
                  <div className="bg__total-row bg__total-row--final">
                    <span>TỔNG THANH TOÁN:</span>
                    <span key={totalFinal} className="text-xl text-rust-deep bg__cell-flash">
                      {fmtVnd(totalFinal)}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {saveErr && (
            <div className="banner banner--error" role="alert" style={{ marginTop: "16px" }}>
              {saveErr}
            </div>
          )}

          <div className="bg__dialog-actions" style={{ marginTop: "24px" }}>
            <Button type="button" variant="ghost" onClick={onClose}>
              Hủy
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={busy || selectedCount === 0}>
              {busy ? "Đang lưu…" : isEdit ? "Lưu thay đổi" : "Tạo Bản nháp (Save)"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// --- Detail 2-cột in-page (port "ý hệt" prototype inan5 02-bao-gia.html) ------------------------------------------------

// Gói biên lợi nhuận — shortcut UI (ô % từng dòng vẫn nhận giá trị bất kỳ;
// đợt sau chuyển thành catalog cấu hình được theo luật "không hardcode số liệu").
const MARGIN_PRESETS: Array<[string, number]> = [
  ["Tiêu chuẩn", 25],
  ["Khách quen", 18],
  ["Đơn gấp/khó", 35],
  ["Cạnh tranh", 12],
];

const STATUS_LABEL_SHORT: Record<string, string> = {
  pending_approval: "đang chờ Giám đốc duyệt",
  approved: "đã duyệt · chờ gửi khách",
  sent: "đã gửi khách",
  accepted: "được khách chốt",
  rejected: "bị từ chối",
  expired: "hết hạn",
  converted_to_order: "lên đơn hàng",
  cancelled: "hủy",
};

// Feed Hoạt động: action (audit backend) → [glyph, lớp màu chấm, nhãn tiếng Việt].
const ACT_META: Record<string, [string, string, string]> = {
  create_quote: ["+", "rust", "Tạo báo giá"],
  update_quote: ["✎", "steel", "Cập nhật báo giá"],
  change_order: ["⎇", "rust", "Tạo phiên bản mới"],
  transition_pending_approval: ["⇪", "amber", "Trình duyệt"],
  quote_exception_approved: ["✓", "moss", "Giám đốc KD duyệt"],
  quote_exception_rejected: ["✕", "signal", "Giám đốc KD từ chối"],
  transition_sent: ["✈", "steel", "Gửi khách"],
  transition_accepted: ["✓", "moss", "Khách hàng đồng ý"],
  transition_rejected: ["✕", "signal", "Khách hàng từ chối"],
  transition_expired: ["!", "ash", "Hết hiệu lực"],
  transition_cancelled: ["✕", "ash", "Hủy báo giá"],
  transition_converted_to_order: ["→", "moss", "Lên đơn hàng"],
};

// Ngày + giờ cho feed Hoạt động ("ai làm gì · khi nào").
function fmtDateTime(v: string | null): string {
  if (!v) return "—";
  const dt = new Date(v);
  return isNaN(dt.getTime()) ? "—" : dt.toLocaleString("vi-VN", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function QuotationDetailView({
  quotationId,
  statuses,
  navigate,
  onClose,
  onChanged,
}: {
  quotationId: number;
  statuses: EnumOption[];
  navigate?: (id: string, params?: any) => void;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { token } = useAuth();
  // Xuất PDF đối ngoại = quyền chi tiết `export` (tách khỏi "xem").
  const canExport = useCan()("bao_gia", "export");
  // Tạo phiên bản mới (requote) = thao tác thường: ai SỬA được báo giá thì làm được (gộp vào
  // `update` ở P8; quyền `requote` cũ đã bỏ). State machine (`change_order`) vẫn chặn đúng trạng thái.
  const canRequote = useCan()("bao_gia", "update");
  // Lưu ý: layout 2 cột (main) không còn nút Hủy báo giá — quyền `cancel` vẫn chặn ở backend.
  // Thao tác trạng thái chung (gửi / từ chối / đánh dấu hết hạn…) — tách khỏi "sửa".
  const canManageStatus = useCan()("bao_gia", "manage_status");
  // BG-2: duyệt "báo giá đặc thù" — CHỈ Giám đốc. Người có quyền này cũng thấy số biên.
  const canApproveException = useCan()("bao_gia", "approve_exception");
  const [d, setD] = useState<QuotationDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [apprNote, setApprNote] = useState("");
  const [apprSaving, setApprSaving] = useState(false);

  // Margin sống (preview cục bộ trước khi persist) — chỉ dùng khi báo giá 1 dòng.
  const [draftMargin, setDraftMargin] = useState<number | null>(null);
  // Markup từng dòng khi đang gõ (đa dòng) — override tạm để preview.
  const [lineDraft, setLineDraft] = useState<Record<number, number>>({});
  // P3 (redesign-bao-gia §6): popover MarginPicker (gói biên + slider) mở cho DÒNG nào (đa dòng).
  const [mkOpenLine, setMkOpenLine] = useState<number | null>(null);
  // P3: danh sách khách để CHỌN/ĐỔI khách ngay ở detail (khi còn nháp) — auto-fill lại liên hệ + ĐC giao.
  const [customers, setCustomers] = useState<{ id: number; name: string; code: string }[]>([]);

  const [compareOn, setCompareOn] = useState(false);
  const [showPrint, setShowPrint] = useState(false);

  // Điều khoản chỉnh tại chỗ (nháp)
  const [terms, setTerms] = useState("");
  const [validity, setValidity] = useState<number>(30);
  const [validUntilEdit, setValidUntilEdit] = useState<string>("");   // ngày hết hạn (editable)
  const [verNote, setVerNote] = useState("");
  // Gộp modal "Chỉnh sửa" vào detail (bỏ modal): điều khoản giao nhận + địa chỉ giao editable ngay đây.
  const [deliveryAddressEdit, setDeliveryAddressEdit] = useState("");
  const [deliveryTermsEdit, setDeliveryTermsEdit] = useState("");

  // Feed Hoạt động — nhật ký tương tác THẬT (ai làm gì) đọc từ backend.
  const [acts, setActs] = useState<QuotationActivity[]>([]);
  // Tạo phiên bản mới: BẮT BUỘC ghi chú → modal nhập lý do trước khi tạo.
  const [requoteOpen, setRequoteOpen] = useState(false);
  const [requoteNote, setRequoteNote] = useState("");
  // Theo dõi gửi khách (follow-up) — localStorage theo mã BG.
  const [lastContact, setLastContact] = useState<string | null>(null);

  const reload = useCallback(
    async (id: number) => {
      if (!token) return;
      try {
        const det = await api.quotations.get(token, id);
        setD(det);
        setDraftMargin(null);
        setLineDraft({});
        setTerms(det.payment_terms ?? "");
        setVerNote((det as any).change_reason ?? "");
        setValidUntilEdit(det.valid_until ?? "");
        setDeliveryAddressEdit(det.delivery_address ?? "");
        setDeliveryTermsEdit(det.delivery_terms ?? "");
        // Hiệu lực (ngày) suy từ valid_until so với ngày tạo bản hiện tại.
        const vr = det.versions.find((v) => v.version === det.version);
        const created = vr?.created_at ?? null;
        if (det.valid_until && created) {
          const days = Math.round(
            (new Date(det.valid_until).getTime() - new Date(created).getTime()) / 86_400_000,
          );
          setValidity(days > 0 ? days : 30);
        } else setValidity(30);
        setLastContact(lsGet(`bgv_contact_${det.code}`, null));
        // Feed Hoạt động — nhật ký THẬT (ai làm gì) từ backend.
        api.quotations.activity(token, id).then((r) => setActs(r.items)).catch(() => setActs([]));
      } catch {
        setErr("Không tải được chi tiết báo giá.");
      }
    },
    [token],
  );

  useEffect(() => {
    reload(quotationId);
  }, [reload, quotationId]);

  // P3: nạp danh sách khách để chọn/đổi khách ngay ở detail (khi còn nháp).
  useEffect(() => {
    if (!token) return;
    api.customers.list(token, { page: 1, size: 200 }).then((r) => setCustomers(r.items)).catch(() => {});
  }, [token]);

  if (!d) {
    return (
      <main className="bg bgv">
        <div className="card" role="status" style={{ padding: "40px", textAlign: "center", color: "var(--ash)" }}>
          Đang tải dữ liệu báo giá…
        </div>
      </main>
    );
  }

  const latestVer = Math.max(...d.versions.map((v) => v.version));
  const viewingLatest = d.version === latestVer;
  const editable = d.status === "draft" && viewingLatest;
  const multi = d.items.length > 1;

  // ---- Tính toán sống (áp override margin nếu có) --------------------------
  function calcItem(it: QuoteItemDetail) {
    const override = multi ? lineDraft[it.id] : draftMargin;
    const m = override != null ? override : it.margin_percent;
    const cost = it.total_cost_snapshot;
    const selling = m >= 100 ? cost : cost / (1 - m / 100);
    const net = Math.max(0, selling - it.discount_amount);
    const vat = (net * (it.vat_percent || 0)) / 100;
    return { m, cost, selling, net, vat, final: net + vat, profit: net - cost, qty: it.quantity };
  }
  let costT = 0, netT = 0, vatT = 0, grandT = 0, qtyT = 0;
  d.items.forEach((it) => {
    const c = calcItem(it);
    costT += c.cost; netT += c.net; vatT += c.vat; grandT += c.final; qtyT += c.qty;
  });
  const profitT = netT - costT;
  const singleMargin = draftMargin != null ? draftMargin : d.items[0]?.margin_percent ?? 0;
  const singleVat = d.items[0]?.vat_percent ?? 10;
  const aggMarginPct = costT ? Math.round((profitT / costT) * 100) : 0;
  const perUnit = qtyT ? Math.round(grandT / qtyT) : 0;
  const unitLabel = d.items[0]?.unit || "cái";

  const productSummary = d.items[0]?.product_name ?? "—";
  const ptgRefs = Array.from(new Set(d.items.map((it) => it.estimate_number).filter(Boolean)));

  // ---- Persist margin/VAT --------------------------------------------------
  // Patch theo dòng: bỏ trống field nào thì GIỮ giá trị hiện tại của dòng đó (dùng ?? để 0 vẫn áp).
  // Header lấy từ edit-state (không clobber ghi chú/điều khoản đang sửa chưa lưu).
  async function persistItems(
    items: { id: number; margin_percent?: number; vat_percent?: number; discount_amount?: number; rounding?: string; note?: string | null }[],
  ) {
    if (!token || !d) return;
    setBusy(true);
    setErr(null);
    try {
      await api.quotations.update(token, d.id, {
        customer_id: d.customer_id,
        valid_until: validUntilEdit || null,
        payment_terms: terms,
        delivery_terms: deliveryTermsEdit,
        delivery_address: deliveryAddressEdit,
        items: d.items.map((it) => {
          const patch = items.find((x) => x.id === it.id);
          return {
            id: it.id,
            margin_percent: patch?.margin_percent ?? it.margin_percent,
            discount_amount: patch?.discount_amount ?? it.discount_amount,
            discount_percent: 0,
            vat_percent: patch?.vat_percent ?? it.vat_percent,
            rounding: patch?.rounding ?? "no_rounding",
            note: patch?.note !== undefined ? patch.note : it.note,
          };
        }),
      });
      await reload(d.id);
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không lưu được giá bán.");
    } finally {
      setBusy(false);
    }
  }
  function commitSingleMargin(val: number) {
    if (!editable || !d) return;
    const v = Math.max(0, Math.min(100, val));
    persistItems(d.items.map((it) => ({ id: it.id, margin_percent: v })));
  }
  function commitLineMargin(itemId: number, val: number) {
    if (!editable) return;
    const v = Math.max(0, Math.min(100, val));
    persistItems([{ id: itemId, margin_percent: v }]);
  }
  // VAT áp CHUNG mọi dòng (VN chuẩn 0/8/10%).
  function commitVat(val: number) {
    if (!editable || !d) return;
    const v = Math.max(0, Math.min(100, val));
    persistItems(d.items.map((it) => ({ id: it.id, vat_percent: v })));
  }

  // P3: đổi khách ngay ở detail (khi nháp). Gửi delivery_address rỗng → BE tự điền ĐC giao mặc định
  // + làm mới người liên hệ chính của khách mới (redesign-bao-gia §4).
  async function changeCustomer(newId: number | null) {
    if (!token || !d) return;
    setBusy(true);
    setErr(null);
    try {
      await api.quotations.update(token, d.id, {
        customer_id: newId,
        valid_until: d.valid_until,
        payment_terms: terms,
        delivery_terms: d.delivery_terms,
        delivery_address: null,
        items: null,
      });
      await reload(d.id);
      onChanged();
      setNotice("Đã đổi khách — cập nhật liên hệ & địa chỉ giao.");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Đổi khách thất bại.");
    } finally {
      setBusy(false);
    }
  }

  async function saveTerms() {
    if (!token || !d) return;
    setBusy(true);
    setErr(null);
    try {
      await api.quotations.update(token, d.id, {
        customer_id: d.customer_id,
        valid_until: validUntilEdit || null,
        payment_terms: terms,
        delivery_terms: deliveryTermsEdit,
        delivery_address: deliveryAddressEdit,
        items: null,
      });
      await reload(d.id);
      onChanged();
      setNotice("Đã lưu nháp.");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Lưu nháp thất bại.");
    } finally {
      setBusy(false);
    }
  }

  async function doTransition(to: string) {
    if (!token || !d) return;
    setBusy(true);
    setErr(null);
    try {
      await api.quotations.transition(token, d.id, { to_status: to, cancel_reason: null });
      await reload(d.id);
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Thao tác không thành công.");
    } finally {
      setBusy(false);
    }
  }

  async function submitQuoteApproval(decision: "approved" | "rejected") {
    if (!token || !d) return;
    if (!apprNote.trim()) {
      setErr("Nhập lý do/ý kiến — bắt buộc khi duyệt HOẶC từ chối báo giá đặc thù.");
      return;
    }
    setApprSaving(true);
    setErr(null);
    try {
      await api.quotations.recordApproval(token, d.id, { decision, note: apprNote.trim() || null });
      setApprNote("");
      await reload(d.id);
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Ghi duyệt không thành công.");
    } finally {
      setApprSaving(false);
    }
  }

  function openRequote() {
    setRequoteNote("");
    setErr(null);
    setRequoteOpen(true);
  }
  async function doRequote() {
    if (!token || !d) return;
    const note = requoteNote.trim();
    if (!note) { setErr("Nhập lý do/ghi chú cho phiên bản mới — bắt buộc."); return; }
    setBusy(true);
    setErr(null);
    try {
      const nv = await api.quotations.requote(token, d.id, note);
      setRequoteOpen(false);
      setRequoteNote("");
      setD(null);
      await reload(nv.id);
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Tạo phiên bản mới không thành công.");
    } finally {
      setBusy(false);
    }
  }

  function handleCreateOrder() {
    if (!d || !navigate) return;
    navigate("don-hang-ban", {
      customer: d.customer ? { id: d.customer_id!, name: d.customer.name, code: "" } : undefined,
      openQuoteId: d.id,
    });
    onClose();
  }

  // ---- Follow-up handler ---------------------------------------------------
  function recordContact() {
    if (!d) return;
    const today = new Date().toLocaleDateString("vi-VN");
    setLastContact(today);
    lsSet(`bgv_contact_${d.code}`, today);
    setNotice("Đã ghi nhận liên hệ khách hôm nay.");
  }
  function duplicate() {
    setNotice("Đã nhân bản báo giá (mô phỏng) — bản sao sẽ xuất hiện ở danh sách khi nối backend.");
  }

  // ---- Follow-up (chỉ khi 'sent') ------------------------------------------
  const curVerRow = d.versions.find((v) => v.version === d.version);
  const sentDate = curVerRow?.created_at ?? null;
  const sentDays = sentDate ? Math.max(0, Math.floor((Date.now() - new Date(sentDate).getTime()) / 86_400_000)) : 0;
  const stale = d.status === "sent" && sentDays > 3;

  const statusCls = statusChipClass(d.status);

  return (
    <main className="bg bgv">
      {/* ---------- Header ---------- */}
      <div className="page-header">
        <div>
          <h1>
            <button type="button" className="btn btn--ghost btn--sm" onClick={onClose}>‹ Danh sách</button>
            <span style={{ fontFamily: "var(--ff-mono)", fontWeight: 500 }}>{d.code}</span>
            <span className="ver-badge">v{d.version}</span>
            <span className={`status-chip ${statusCls}`}>{labelOf(statuses, d.status)}</span>
          </h1>
          <p>
            {d.customer?.name ?? "—"} · {productSummary}
            {ptgRefs.length > 0 && <> · <span style={{ fontFamily: "var(--ff-mono)" }}>↳ {ptgRefs.join(", ")}</span></>}
          </p>
        </div>
        <div className="actions">
          <Button variant="secondary" onClick={() => setShowPrint(true)}>🖨️ Xem in</Button>
          <Button variant="secondary" onClick={duplicate}>⧉ Nhân bản</Button>
          {/* Gating quyền chi tiết: từ chối/gửi cần `manage_status`, chốt cần `approve`
              (server tính d.can_approve), tạo bản mới cần `requote` — thiếu quyền thì ẨN nút. */}
          {viewingLatest && d.status === "sent" && (
            <>
              {canManageStatus && (
                <Button variant="secondary" disabled={busy} onClick={() => doTransition("rejected")}>✕ Khách từ chối</Button>
              )}
              {d.can_approve && (
                <Button variant="primary" disabled={busy || !d.allowed_transitions.includes("accepted")} onClick={() => doTransition("accepted")}>✓ Khách chốt</Button>
              )}
            </>
          )}
          {/* Nháp: báo giá ĐẶC THÙ phải TRÌNH DUYỆT (→ Chờ duyệt → GĐ Kinh doanh duyệt); báo giá
              THƯỜNG gửi khách thẳng. Backend chặn cứng 2 đường (redesign-bao-gia §3). */}
          {canManageStatus && viewingLatest && d.status === "draft" && d.exception_required &&
            d.allowed_transitions.includes("pending_approval") && (
            <Button
              variant="accent"
              disabled={busy}
              title="Báo giá đặc thù — trình duyệt trước khi gửi khách"
              onClick={() => doTransition("pending_approval")}
            >⇪ Trình duyệt</Button>
          )}
          {/* Gửi khách (SALE tự gửi): báo giá THƯỜNG từ Nháp, HOẶC đặc thù ĐÃ ĐƯỢC GĐ DUYỆT (approved). */}
          {canManageStatus && viewingLatest && d.allowed_transitions.includes("sent") &&
            ((d.status === "draft" && !d.exception_required) || d.status === "approved") && (
            <Button
              variant="accent"
              disabled={busy}
              title={d.status === "approved" ? "Giám đốc đã duyệt — gửi báo giá cho khách" : undefined}
              onClick={() => doTransition("sent")}
            >➤ Gửi khách</Button>
          )}
          {viewingLatest && d.status === "accepted" && navigate && (
            <Button variant="accent" disabled={busy} onClick={handleCreateOrder}>🛒 Tạo đơn hàng</Button>
          )}
          {canRequote && viewingLatest && d.status === "rejected" && d.allowed_transitions.includes("change_order") && (
            <Button variant="primary" disabled={busy} onClick={openRequote}>⎇ Tạo phiên bản mới</Button>
          )}
        </div>
      </div>

      {notice && (
        <div className="banner banner--success" role="status" style={{ marginBottom: "14px" }}>
          <span>{notice}</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setNotice(null)}>Đóng</button>
        </div>
      )}
      {err && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "14px" }}>{err}</div>
      )}
      {/* Báo giá BỊ TỪ CHỐI (khách HOẶC GĐ/TP từ chối đặc thù) → nhắc "Tạo phiên bản mới" để sửa. */}
      {d.status === "rejected" && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "14px" }}>
          {d.exception_decision === "rejected" ? (
            <span>🔙 Giám đốc/Trưởng phòng KD đã <b>từ chối</b> báo giá đặc thù{d.exception_note ? `: ${d.exception_note}` : ""}. Bấm <b>Tạo phiên bản mới</b> để sửa rồi trình duyệt lại.</span>
          ) : (
            <span>✕ <b>Khách hàng từ chối</b>{d.cancel_reason ? `: ${d.cancel_reason}` : ""}. Bấm <b>Tạo phiên bản mới</b> để báo lại giá mới.</span>
          )}
        </div>
      )}

      <div className="bg-split">
        {/* ================= LEFT ================= */}
        <div className="bg-left">
          {/* Giá vốn khóa */}
          <div className="card cost-locked">
            <div className="bg-card-head">
              <div className="title">
                🔒 <span>{multi ? "Báo giá nhiều dòng" : "Giá vốn"}</span>
                <span className="mono-tag lock">{multi ? `${d.items.length} phiếu tính giá` : "Khóa từ PTG"}</span>
              </div>
            </div>
            <div className="locked-banner">
              🛡️ Giá vốn khóa theo phiếu tính giá đã duyệt · markup riêng từng dòng · giá đã gồm VAT.
            </div>
            <table className="bg-lines">
              <thead>
                <tr>
                  <th>Sản phẩm</th><th>SL</th><th>Giá vốn</th><th>Markup %</th><th>Thành tiền (VAT)</th>
                </tr>
              </thead>
              <tbody>
                {d.items.map((it) => {
                  const c = calcItem(it);
                  return (
                    <tr key={it.id}>
                      <td>
                        <div className="ln-prod">{it.product_name}</div>
                        {(it.estimate_number || it.product_spec_text) && (
                          <div className="ln-ref">
                            {it.estimate_number && <span>↳ {it.estimate_number}</span>}
                            {it.product_spec_text ? ` · ${it.product_spec_text}` : ""}
                          </div>
                        )}
                      </td>
                      <td className="bg__mono">{it.quantity.toLocaleString("vi-VN")}</td>
                      <td className="bg__mono">{vnd(c.cost)}</td>
                      <td style={{ position: "relative" }}>
                        {multi ? (
                          <>
                            <button
                              type="button"
                              className="ln-mk bg__mono"
                              disabled={!editable}
                              style={{ cursor: editable ? "pointer" : "default", minWidth: 54 }}
                              onClick={() => editable && setMkOpenLine(mkOpenLine === it.id ? null : it.id)}
                              title="Chọn gói biên / kéo slider cho dòng này"
                            >
                              {Math.round(lineDraft[it.id] ?? it.margin_percent)}%
                            </button>
                            {mkOpenLine === it.id && editable && (
                              <div
                                className="mk-block"
                                style={{
                                  position: "absolute", right: 0, top: "calc(100% + 4px)", zIndex: 30,
                                  minWidth: 232, padding: 12, borderRadius: 10,
                                  background: "var(--charcoal, #221c17)",
                                  boxShadow: "0 10px 28px rgba(0,0,0,.35)",
                                }}
                              >
                                <span className="mk-lbl">Gói biên · dòng này</span>
                                <div className="mk-presets">
                                  {MARGIN_PRESETS.map(([name, pct]) => (
                                    <button
                                      key={name} type="button"
                                      className={`mk-chip${Math.round(lineDraft[it.id] ?? it.margin_percent) === pct ? " on" : ""}`}
                                      disabled={busy}
                                      onClick={() => { setLineDraft((p) => ({ ...p, [it.id]: pct })); commitLineMargin(it.id, pct); }}
                                    >
                                      <span className="mc-name">{name}</span>
                                      <span className="mc-pct">{pct}%</span>
                                    </button>
                                  ))}
                                </div>
                                <div className="mk-controls">
                                  <input
                                    type="range" min={5} max={50} step={1} className="markup-slider"
                                    value={Math.max(5, Math.min(50, lineDraft[it.id] ?? it.margin_percent))}
                                    disabled={busy}
                                    onChange={(e) => setLineDraft((p) => ({ ...p, [it.id]: Number(e.target.value) }))}
                                    onMouseUp={(e) => commitLineMargin(it.id, Number((e.target as HTMLInputElement).value))}
                                    onTouchEnd={(e) => commitLineMargin(it.id, Number((e.target as HTMLInputElement).value))}
                                  />
                                  <div className="mk-manual">
                                    <input
                                      type="number" min={0} max={100} step={0.5}
                                      value={lineDraft[it.id] ?? it.margin_percent}
                                      disabled={busy}
                                      onChange={(e) => setLineDraft((p) => ({ ...p, [it.id]: Number(e.target.value) }))}
                                      onBlur={(e) => commitLineMargin(it.id, Number(e.target.value))}
                                    />
                                    <span>%</span>
                                  </div>
                                </div>
                                <button
                                  type="button" className="btn btn--ghost btn--sm"
                                  style={{ marginTop: 8 }} onClick={() => setMkOpenLine(null)}
                                >
                                  Đóng
                                </button>
                              </div>
                            )}
                          </>
                        ) : (
                          <input
                            className="ln-mk bg__mono"
                            type="number" min={0} max={100} step={0.5}
                            value={draftMargin ?? it.margin_percent}
                            disabled={!editable}
                            onChange={(e) => setDraftMargin(Number(e.target.value))}
                            onBlur={(e) => commitSingleMargin(Number(e.target.value))}
                          />
                        )}
                      </td>
                      <td className="bg__mono" style={{ fontWeight: 600, color: "var(--ink)" }}>{vnd(c.final)}</td>
                    </tr>
                  );
                })}
                <tr className="lines-sum">
                  <td>Tổng {d.items.length} dòng</td>
                  <td></td>
                  <td>{vnd(costT)}</td>
                  <td></td>
                  <td>{vnd(grandT)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Điều khoản & hiệu lực */}
          <div className="card">
            <div className="bg-card-head"><div className="title">📝 Điều khoản &amp; hiệu lực</div></div>
            <div className="field-row">
              <span className="field-lbl">Điều khoản thanh toán</span>
              <textarea className="field-in" rows={2} value={terms} disabled={!editable} onChange={(e) => setTerms(e.target.value)} />
            </div>
            <div className="field-row">
              <span className="field-lbl">Điều khoản giao nhận</span>
              <textarea className="field-in" rows={2} value={deliveryTermsEdit} disabled={!editable} onChange={(e) => setDeliveryTermsEdit(e.target.value)} />
            </div>
            <div className="field-row">
              <span className="field-lbl">Địa chỉ giao hàng</span>
              <input className="field-in" value={deliveryAddressEdit} disabled={!editable} onChange={(e) => setDeliveryAddressEdit(e.target.value)} placeholder="Nhập địa chỉ giao hàng…" />
            </div>
            <div className="field-inline">
              <span className="field-lbl">Hạn hiệu lực</span>
              <input
                className="field-in"
                type="date"
                style={{ width: "170px" }}
                value={validUntilEdit}
                disabled={!editable}
                onChange={(e) => setValidUntilEdit(e.target.value)}
              />
              <span style={{ color: "var(--ash)", fontSize: "12px" }}>
                {validUntilEdit ? `(${validity} ngày kể từ ngày gửi)` : "để trống = đến khi có thông báo mới"}
              </span>
            </div>
            {verNote && (
              <div className="field-row">
                <span className="field-lbl">Lý do phiên bản này</span>
                <input className="field-in" value={verNote} disabled readOnly />
              </div>
            )}
            {!editable && (
              <div className="ro-note" style={{ marginTop: "12px" }}>
                👁 Phiên bản này {STATUS_LABEL_SHORT[d.status] ?? "đã khóa"} — khóa chỉnh sửa. Bấm "Tạo phiên bản mới" để sửa.
              </div>
            )}
            <div style={{ marginTop: "14px", display: "flex", gap: "8px" }}>
              {editable && <Button variant="secondary" disabled={busy} onClick={saveTerms}>💾 Lưu nháp</Button>}
              {canRequote && viewingLatest && d.allowed_transitions.includes("change_order") && (
                <Button variant="primary" disabled={busy} onClick={openRequote} title="Giữ bản hiện tại + tạo phiên bản mới (bắt buộc ghi chú)">⎇ Tạo phiên bản mới</Button>
              )}
            </div>
          </div>

          {/* Theo dõi gửi khách (follow-up) */}
          {d.status === "sent" && (
            <div className="card">
              <div className="bg-card-head">
                <div className="title">🔗 Theo dõi gửi khách</div>
                {stale && <span className="sub" style={{ color: "var(--amber)" }}>CẦN FOLLOW-UP</span>}
              </div>
              <div className="stage-rows">
                <div className="sr"><span className="k">Kênh gửi</span><span className="v">Email</span></div>
                <div className="sr"><span className="k">Ngày gửi</span><span className="v">{fmtDate(sentDate)}</span></div>
                <div className="sr"><span className="k">Hạn phản hồi</span><span className="v">{fmtDate(d.valid_until)} ({validity} ngày)</span></div>
                {lastContact && <div className="sr"><span className="k">Liên hệ gần nhất</span><span className="v">{lastContact}</span></div>}
                <div className="sr"><span className="k">Đã gửi</span><span className={`v ${stale ? "warn" : ""}`}>{sentDays} ngày</span></div>
              </div>
              {stale && <div className="stage-note">Quá 3 ngày chưa chốt — nên liên hệ nhắc khách.</div>}
              {viewingLatest && (
                <div className="stage-card-actions">
                  <Button variant="secondary" onClick={recordContact}>📞 Ghi nhận đã liên hệ</Button>
                </div>
              )}
            </div>
          )}
          {d.status === "rejected" && d.cancel_reason && (
            <div className="card">
              <div className="bg-card-head"><div className="title">🚫 Lý do từ chối</div></div>
              <div className="stage-note warn">{d.cancel_reason}</div>
            </div>
          )}

          {/* Lịch sử phiên bản */}
          <div className="card">
            <div className="bg-card-head">
              <div className="title">🕒 Lịch sử phiên bản</div>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setCompareOn((v) => !v)}>⇄ So sánh</button>
            </div>
            <div>
              {d.versions.slice().sort((a, b) => b.version - a.version).map((v) => {
                const isCur = v.version === latestVer;
                const active = v.version === d.version;
                return (
                  <div
                    key={v.id}
                    className={`ver-item${active ? " active" : ""}${isCur ? " current" : ""}`}
                    onClick={() => v.id !== d.id && reload(v.id)}
                  >
                    <span className="v-tag">v{v.version}</span>
                    <div>
                      <div className="v-note">{v.change_reason || "—"}</div>
                      <div className="v-meta">{fmtDate(v.created_at)}{isCur ? " · " : ""}{isCur && <b style={{ color: "var(--moss)" }}>hiện tại</b>}</div>
                    </div>
                    <div className="v-price">{vnd(v.total ?? 0)}<div className="v-st"><span className={`status-chip ${statusChipClass(v.status)}`}>{labelOf(statuses, v.status)}</span></div></div>
                  </div>
                );
              })}
            </div>
            {compareOn && (
              <div style={{ marginTop: "12px", borderTop: "1px solid var(--rule-soft)", paddingTop: "12px", overflowX: "auto" }}>
                <table className="cmp-tbl">
                  <thead>
                    <tr><th>Chỉ tiêu</th>{d.versions.slice().sort((a, b) => a.version - b.version).map((v) => <th key={v.id}>v{v.version}</th>)}</tr>
                  </thead>
                  <tbody>
                    <tr><td>Giá bán (đã VAT)</td>{d.versions.slice().sort((a, b) => a.version - b.version).map((v) => <td key={v.id}>{vnd(v.total ?? 0)}</td>)}</tr>
                    <tr>
                      <td>Chênh lệch</td>
                      {d.versions.slice().sort((a, b) => a.version - b.version).map((v, i, arr) => {
                        if (i === 0) return <td key={v.id}>—</td>;
                        const diff = (v.total ?? 0) - (arr[i - 1].total ?? 0);
                        if (diff === 0) return <td key={v.id}>0</td>;
                        return <td key={v.id}><span className={diff > 0 ? "up" : "down"}>{diff > 0 ? "+" : ""}{vnd(diff)}</span></td>;
                      })}
                    </tr>
                    <tr><td>Trạng thái</td>{d.versions.slice().sort((a, b) => a.version - b.version).map((v) => <td key={v.id}>{labelOf(statuses, v.status)}</td>)}</tr>
                    <tr><td>Ngày</td>{d.versions.slice().sort((a, b) => a.version - b.version).map((v) => <td key={v.id}>{fmtDate(v.created_at)}</td>)}</tr>
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* ================= RIGHT ================= */}
        <div className="bg-sidebar">
          {/* Panel giá bán đề xuất */}
          <div className="summary-card">
            <div className="lbl">Giá bán đề xuất <span style={{ color: "var(--rust-2)" }}>· v{d.version}</span></div>
            <div className="grand"><span className={busy ? "" : "flash"}>{numf(grandT)}</span><span style={{ fontSize: "16px", color: "rgba(245,241,232,0.55)", marginLeft: "4px" }}>₫</span></div>
            <div className="grand-unit">≈ {numf(perUnit)}₫/{unitLabel} · đã VAT</div>

            {!multi && (
              <div className="mk-block">
                <span className="mk-lbl">Lợi nhuận · gói biên</span>
                <div className="mk-presets">
                  {MARGIN_PRESETS.map(([name, pct]) => (
                    <button
                      key={name}
                      type="button"
                      className={`mk-chip${Math.round(singleMargin) === pct ? " on" : ""}`}
                      disabled={!editable || busy}
                      onClick={() => { setDraftMargin(pct); commitSingleMargin(pct); }}
                    >
                      <span className="mc-name">{name}</span>
                      <span className="mc-pct">{pct}%</span>
                    </button>
                  ))}
                </div>
                <div className="mk-controls">
                  <input
                    type="range" min={5} max={50} step={1}
                    className="markup-slider"
                    value={Math.max(5, Math.min(50, singleMargin))}
                    disabled={!editable}
                    onChange={(e) => setDraftMargin(Number(e.target.value))}
                    onMouseUp={(e) => commitSingleMargin(Number((e.target as HTMLInputElement).value))}
                    onTouchEnd={(e) => commitSingleMargin(Number((e.target as HTMLInputElement).value))}
                  />
                  <div className="mk-manual">
                    <input
                      type="number" min={0} max={100} step={0.5}
                      value={singleMargin}
                      disabled={!editable}
                      onChange={(e) => setDraftMargin(Number(e.target.value))}
                      onBlur={(e) => commitSingleMargin(Number(e.target.value))}
                    />
                    <span>%</span>
                  </div>
                </div>
              </div>
            )}

            {/* Báo giá đặc thù (giá trị cao / lời mỏng / bán dưới vốn): Nháp → TRÌNH DUYỆT → Chờ duyệt →
                Giám đốc Kinh doanh duyệt (→ Đã duyệt/gửi) hoặc từ chối (→ về Nháp). Trạng thái bám máy
                trạng thái báo giá (d.status), KHÔNG bám riêng exception_status (redesign-bao-gia §3). */}
            {d.exception_required && (
              <div className="appr-block appr-block--exc">
                <div className="exc-title">Báo giá đặc thù — cần duyệt</div>
                <div className="exc-chips">
                  {d.exceptions.map((e) => (
                    <span key={e.key} className="exc-chip">{e.label}</span>
                  ))}
                  {d.margin_pct != null && (
                    <span className="exc-chip exc-chip--num">Biên {d.margin_pct}%</span>
                  )}
                </div>
                <div className={`exc-status exc-status--${d.status === "pending_approval" ? "pending" : d.status === "approved" ? "approved" : d.status === "rejected" ? "rejected" : d.exception_status}`}>
                  {d.status === "pending_approval"
                    ? canApproveException
                      ? "Chờ quyết định của bạn."
                      : "Đã trình — đang chờ duyệt."
                    : d.status === "approved"
                      ? "Đã DUYỆT — bấm ‘Gửi khách’ để gửi báo giá cho khách."
                    : d.status === "sent" || d.status === "accepted" || d.status === "converted_to_order"
                      ? ""
                      : d.status === "rejected"
                        ? `Bị từ chối — bấm ‘Tạo phiên bản mới’ để sửa rồi trình duyệt lại.${d.exception_note ? " Lý do: " + d.exception_note : ""}`
                        : d.exception_status === "stale"
                          ? "Báo giá đã đổi so với lần duyệt trước — cần Trình duyệt lại."
                          : canManageStatus
                            ? "Bấm ‘Trình duyệt’ để gửi duyệt."
                            : "Chưa trình duyệt."}
                </div>
                {/* AI đã quyết định gần nhất — để NV biết ai duyệt/từ chối + khi nào + lý do (P8b). */}
                {d.exception_decided_by_name && (
                  <div className="exc-decided">
                    {d.exception_decision === "rejected" ? "✕ Từ chối" : "✓ Duyệt"} bởi{" "}
                    <b>{d.exception_decided_by_name}</b>
                    {d.exception_decided_at ? ` · ${fmtDate(d.exception_decided_at)}` : ""}
                    {d.exception_note ? ` · “${d.exception_note}”` : ""}
                  </div>
                )}
                {/* GĐ Kinh doanh duyệt/từ chối — CHỈ khi báo giá đang Chờ duyệt (pending_approval). */}
                {d.status === "pending_approval" && canApproveException && (
                  <div className="exc-actions">
                    <textarea
                      className="exc-note"
                      value={apprNote}
                      onChange={(e) => setApprNote(e.target.value)}
                      placeholder="Lý do / ý kiến (bắt buộc — cả khi duyệt lẫn từ chối)"
                      rows={2}
                    />
                    <div className="exc-btns">
                      <Button variant="primary" disabled={apprSaving} onClick={() => submitQuoteApproval("approved")}>
                        {apprSaving ? "Đang ghi…" : "Duyệt"}
                      </Button>
                      <Button variant="ghost" disabled={apprSaving} onClick={() => submitQuoteApproval("rejected")}>
                        Từ chối (trả lại)
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="br-rows">
              <div className="row-cost"><span className="row-key">Giá vốn (khóa)</span><span className="row-val">{numf(costT)}₫</span></div>
              <div><span className="row-key">Lợi nhuận ({multi ? "~" + aggMarginPct : Math.round(singleMargin)}%)</span><span className="row-val">{numf(profitT)}₫</span></div>
              <div><span className="row-key">Giá bán (chưa VAT)</span><span className="row-val">{numf(netT)}₫</span></div>
              <div>
                <span className="row-key">
                  VAT
                  {!multi && editable ? (
                    <span className="vat-seg" role="group" aria-label="Chọn % VAT">
                      {[0, 8, 10].map((p) => (
                        <button
                          key={p}
                          type="button"
                          className={`vat-opt${Math.round(singleVat) === p ? " on" : ""}`}
                          disabled={busy}
                          onClick={() => commitVat(p)}
                          title={`Áp VAT ${p}% cho báo giá`}
                        >
                          {p}%
                        </button>
                      ))}
                    </span>
                  ) : (
                    ` (${multi ? "~" : Math.round(singleVat)}%)`
                  )}
                </span>
                <span className="row-val">{numf(vatT)}₫</span>
              </div>
              <div className="row-total"><span className="row-key">Tổng cộng</span><span className="row-val">{numf(grandT)}₫</span></div>
            </div>
          </div>

          {/* Khách hàng */}
          <div className="card">
            <div className="bg-card-head"><div className="title">👤 Khách hàng</div></div>
            <div className="cust-rows">
              <div>
                <span>Công ty</span>
                {editable ? (
                  <CustomerCombobox
                    customers={customers}
                    value={d.customer_id ?? null}
                    onChange={changeCustomer}
                    disabled={busy}
                    maxWidth={220}
                  />
                ) : (
                  <b>{d.customer?.name ?? "—"}</b>
                )}
              </div>
              <div>
                <span>Người liên hệ</span>
                <b>{d.contact_name_snapshot
                  ? `${d.contact_name_snapshot}${d.contact_phone_snapshot ? ` · ${d.contact_phone_snapshot}` : ""}`
                  : "—"}</b>
              </div>
              {/* Người duyệt biết báo giá này của NV nào (P8b). */}
              <div><span>Nhân viên soạn</span><b>{d.salesperson_name ?? "—"}</b></div>
              <div><span>MST</span><b>{d.customer?.tax_code ?? "—"}</b></div>
              <div><span>Tín dụng</span><b>{d.customer?.credit_status_display ?? "—"}</b></div>
              <div>
                <span>Phiếu tính giá</span>
                {d.phieu_tinh_gia_id ? (
                  <button
                    type="button" className="btn btn--ghost btn--sm"
                    style={{ fontFamily: "var(--ff-mono)", padding: "2px 8px" }}
                    onClick={() => navigate?.("tinh-gia", { focusPhieuId: d.phieu_tinh_gia_id ?? undefined })}
                    title="Mở phiếu tính giá nguồn"
                  >
                    ↳ {d.phieu_tinh_gia_ma ?? `#${d.phieu_tinh_gia_id}`} ↗
                  </button>
                ) : (
                  <b>{ptgRefs.length ? ptgRefs.join(", ") : "—"}</b>
                )}
              </div>
            </div>
          </div>

          {/* Hoạt động — nhật ký tương tác THẬT: ai làm gì · khi nào (mọi vai trò đụng cùng phiếu) */}
          <div className="card">
            <div className="bg-card-head"><div className="title">⚡ Hoạt động</div><span className="sub">{acts.length} sự kiện</span></div>
            <div className="act-timeline">
              {acts.length === 0 ? (
                <div className="discuss-empty">Chưa có hoạt động.</div>
              ) : acts.map((a, i) => {
                const m = ACT_META[a.action] ?? ["•", "ash", a.action];
                return (
                  <div className="act-item" key={i}>
                    <span className={`a-dot ${m[1]}`}>{m[0]}</span>
                    <div>
                      <div className="a-text">
                        {m[2]}
                        {a.actor_name && <> · <b>{a.actor_name}</b></>}
                      </div>
                      <div className="a-meta">{fmtDateTime(a.at)}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {requoteOpen && (
        <div className="bg__overlay" onClick={() => setRequoteOpen(false)}>
          <div className="card bg__dialog" style={{ maxWidth: "480px" }} onClick={(e) => e.stopPropagation()}>
            <div className="bg__dialog-head">
              <h2>Tạo phiên bản mới</h2>
              <button type="button" className="bg__close" onClick={() => setRequoteOpen(false)} aria-label="Đóng">✕</button>
            </div>
            <div style={{ padding: "16px" }}>
              <p style={{ margin: "0 0 10px", color: "var(--ash)", fontSize: "13px" }}>
                Ghi rõ lý do/thay đổi cho phiên bản này — <b>bắt buộc</b> (lưu vào Hoạt động &amp; Lịch sử phiên bản).
              </p>
              <textarea
                className="field-in"
                rows={3}
                autoFocus
                value={requoteNote}
                onChange={(e) => setRequoteNote(e.target.value)}
                placeholder="Ví dụ: KH yêu cầu giảm 5% · cập nhật số lượng · đổi quy cách giấy…"
              />
              {err && <div className="ro-note" style={{ marginTop: "8px", color: "var(--signal)" }}>{err}</div>}
              <div style={{ marginTop: "14px", display: "flex", gap: "8px", justifyContent: "flex-end" }}>
                <Button variant="ghost" disabled={busy} onClick={() => setRequoteOpen(false)}>Hủy</Button>
                <Button variant="primary" disabled={busy || !requoteNote.trim()} onClick={doRequote}>⎇ Tạo phiên bản</Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showPrint && <QuotationPrintModal d={d} statuses={statuses} canDownload={canExport} onClose={() => setShowPrint(false)} />}
    </main>
  );
}

// ---- Bản in báo giá song ngữ (MY AN PHU) -----------------------------------
function QuotationPrintModal({
  d,
  canDownload,
  onClose,
}: {
  d: QuotationDetail;
  statuses: EnumOption[];
  /** Quyền chi tiết `export`: thiếu thì chỉ xem trước, ẩn nút In. */
  canDownload: boolean;
  onClose: () => void;
}) {
  const now = new Date();
  const p2 = (n: number) => (n < 10 ? "0" : "") + n;
  const qdate = `${p2(now.getDate())}/${p2(now.getMonth() + 1)}/${now.getFullYear()}`;
  const qno = d.code.replace(/[^0-9A-Za-z]/g, "");
  const money = (v: number) => Math.round(v).toLocaleString("vi-VN");

  // Bảng hiển thị giá CHƯA VAT; VAT + tổng thanh toán ở panel dưới (bám dữ liệu thật của báo giá).
  const lines = d.items.map((it) => {
    const net = Math.max(0, it.selling_price - it.discount_amount); // thành tiền chưa VAT / dòng
    const netUnit = it.quantity ? Math.round(net / it.quantity) : Math.round(net);
    return { it, net, netUnit };
  });
  const netSubtotal = lines.reduce((s, l) => s + l.net, 0); // Σ tiền hàng chưa VAT
  const vatAmount = d.vat_amount;
  const grand = d.total; // tổng thanh toán (gồm VAT)
  const vatSet = new Set(d.items.map((it) => it.vat_percent));
  const vatPct =
    vatSet.size === 1
      ? [...vatSet][0]
      : netSubtotal > 0
        ? Math.round((vatAmount / netSubtotal) * 100)
        : 0;

  const note = (vi: string, en: string) => (
    <li>{vi} <span className="q-en">({en})</span></li>
  );

  return (
    <div className="bg__overlay" onClick={onClose}>
      <div className="card bg__dialog" style={{ maxWidth: "900px", padding: 0 }} onClick={(e) => e.stopPropagation()}>
        <div className="bg__dialog-head">
          <h2>Xem trước báo giá in</h2>
          <button type="button" className="bg__close" onClick={onClose} aria-label="Đóng">✕</button>
        </div>
        <div className="qpdf">
          {/* HEADER: logo hộp | tiêu đề giữa | số & ngày phải (bám Phiếu tính giá) */}
          <header className="q-mh">
            <div className="q-logo"><img src={svnLogoUrl} alt="Sao Việt Nhật" /></div>
            <div className="q-th">
              <h1>BẢNG BÁO GIÁ</h1>
              <div className="q-th-en">Quotation</div>
              <div className="q-cty">{SVN_COMPANY.name}</div>
            </div>
            <div className="q-meta-r">
              <div>Số báo giá: <b>{qno}</b></div>
              <div>Phiên bản: <b>v{d.version}</b></div>
              <div>Ngày: <b>{qdate}</b></div>
            </div>
          </header>

          {/* DẢI THÔNG TIN: khách hàng (trái) + bên bán (phải) */}
          <div className="q-info">
            <div className="q-info-grid">
              <div className="q-info-col">
                <div><span className="q-lbl">Kính gửi <span className="q-en">/ To:</span></span> <b>{d.customer?.name ?? "—"}</b></div>
                <div><span className="q-lbl">Địa chỉ <span className="q-en">/ Address:</span></span> {d.delivery_address ?? "—"}</div>
                <div><span className="q-lbl">MST <span className="q-en">/ Tax code:</span></span> {d.customer?.tax_code ?? "—"}</div>
              </div>
              <div className="q-info-col">
                <div><span className="q-lbl">Người gửi <span className="q-en">/ Sender:</span></span> {SVN_COMPANY.sender}</div>
                <div><span className="q-lbl">Điện thoại <span className="q-en">/ Phone:</span></span> {SVN_COMPANY.phone}</div>
                <div><span className="q-lbl">Hiệu lực đến <span className="q-en">/ Valid until:</span></span> {d.valid_until ?? "Đến khi có thông báo mới"}</div>
              </div>
            </div>
          </div>

          <div className="q-intro">Cảm ơn Quý khách đã quan tâm sản phẩm của {SVN_COMPANY.nameEn}. Chúng tôi xin gửi bảng báo giá chi tiết như sau:</div>

          {/* CHI TIẾT: header xám, viền mảnh, cột tiền căn phải + tfoot Cộng/VAT */}
          <div className="q-sec">Chi tiết báo giá <span className="q-sec-en">/ Quotation details</span></div>
          <table className="q-tbl">
            <colgroup>
              <col style={{ width: "5%" }} /><col style={{ width: "12%" }} /><col style={{ width: "26%" }} />
              <col style={{ width: "15%" }} /><col style={{ width: "6%" }} /><col style={{ width: "9%" }} />
              <col style={{ width: "13%" }} /><col style={{ width: "14%" }} />
            </colgroup>
            <thead>
              <tr>
                <th>STT<span className="q-en">No</span></th>
                <th>Mã hàng<span className="q-en">Code</span></th>
                <th>Mô tả sản phẩm<span className="q-en">Description</span></th>
                <th>Kích thước<span className="q-en">Size</span></th>
                <th>ĐVT<span className="q-en">Unit</span></th>
                <th>Số lượng<span className="q-en">Qty</span></th>
                <th>Đơn giá<span className="q-en">Unit price · chưa VAT</span></th>
                <th>Thành tiền<span className="q-en">Amount · chưa VAT</span></th>
              </tr>
            </thead>
            <tbody>
              {lines.map(({ it, net, netUnit }, i) => (
                <tr key={it.id}>
                  <td className="c">{i + 1}</td>
                  <td className="c">{it.estimate_number ?? "—"}</td>
                  <td><span className="q-prod">{it.product_name}</span>{it.note ? `, ${it.note}` : ""}</td>
                  <td className="c">{it.product_spec_text ?? "—"}</td>
                  <td className="c">{it.unit}</td>
                  <td className="c">{it.quantity.toLocaleString("vi-VN")}</td>
                  <td className="r">{money(netUnit)}</td>
                  <td className="r">{money(net)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td className="q-sub-lbl" colSpan={7}>Cộng tiền hàng (chưa VAT) <span className="q-en">/ Subtotal</span></td>
                <td className="r">{money(netSubtotal)}</td>
              </tr>
              <tr>
                <td className="q-sub-lbl" colSpan={7}>Thuế GTGT {vatPct}% <span className="q-en">/ VAT</span></td>
                <td className="r">{money(vatAmount)}</td>
              </tr>
            </tfoot>
          </table>

          {/* PANEL TỔNG THANH TOÁN (đóng khung, nhãn trái + số lớn phải) */}
          <div className="q-grand">
            <div>
              <div className="q-gt">Tổng thanh toán <span className="q-gt-en">/ Total · incl. VAT</span></div>
              <div className="q-gs">Tiền hàng {money(netSubtotal)}đ + Thuế GTGT {money(vatAmount)}đ</div>
            </div>
            <div className="q-ga">{money(grand)}<span className="q-u">đ</span></div>
          </div>

          {/* ĐIỀU KHOẢN */}
          <div className="q-sec">Điều khoản <span className="q-sec-en">/ Terms</span></div>
          <ol className="q-notes">
            {note("Hiệu lực báo giá: áp dụng từ ngày báo giá cho đến khi có thông báo mới.", "Validity: from the quote date until further notice.")}
            {note("Giá đã bao gồm chi phí vận chuyển đến kho của Quý khách.", "Prices include delivery to your warehouse.")}
            {note(`Đơn giá trong bảng chưa gồm thuế GTGT; thuế GTGT ${vatPct}% được cộng ở phần tổng.`, `Table prices exclude VAT; ${vatPct}% VAT is added in the total.`)}
            {note("Thời gian giao hàng: 7–10 ngày kể từ khi nhận đơn hàng.", "Delivery: 7–10 days from order placement.")}
            {note(`Thời hạn thanh toán: ${d.payment_terms || "theo thỏa thuận."}`, "Payment terms as agreed.")}
          </ol>

          {/* CHỮ KÝ 2 cột (bám cụm ký Phiếu tính giá) */}
          <div className="q-signs">
            <div>
              <div className="q-role">Khách hàng xác nhận <span>(Buyer's confirmation)</span></div>
              <div className="q-hint">(Ký, ghi rõ họ tên)</div>
              <div className="q-sp" />
            </div>
            <div>
              <div className="q-role">Đại diện bên bán <span>(Supplier)</span></div>
              <div className="q-hint">(Ký, ghi rõ họ tên)</div>
              <div className="q-sp" />
            </div>
          </div>

          <div className="q-foot">
            <span>Công ty Sao Việt Nhật · Báo giá có giá trị đối ngoại.</span>
            <span>{qno} · v{d.version}</span>
          </div>
        </div>
        <div className="bg__dialog-actions" style={{ padding: "16px 20px" }}>
          <Button variant="ghost" onClick={onClose}>Đóng</Button>
          {canDownload && (
            <Button variant="primary" onClick={() => window.print()}>In / Lưu PDF</Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---- Ô chọn khách hàng: gõ-để-tìm (tìm "tương đối", bỏ dấu vẫn ra) --------------
/** Bỏ dấu tiếng Việt + hạ chữ thường để so khớp gần đúng (gõ "bao bi" khớp "Bao Bì"). */
function normVi(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[đĐ]/g, "d")
    .toLowerCase()
    .trim();
}

function CustomerCombobox({
  customers,
  value,
  onChange,
  disabled,
  placeholder = "— Chọn khách hàng —",
  maxWidth,
}: {
  customers: { id: number; name: string; code: string }[];
  value: number | null;
  onChange: (id: number | null) => void;
  disabled?: boolean;
  placeholder?: string;
  maxWidth?: number;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);

  const selected = customers.find((c) => c.id === value) ?? null;
  const q = normVi(query);
  const matches = (q
    ? customers.filter((c) => normVi(`${c.name} ${c.code}`).includes(q))
    : customers
  ).slice(0, 50);

  // Đóng dropdown khi bấm ra ngoài.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  function pick(id: number | null) {
    onChange(id);
    setQuery("");
    setOpen(false);
  }

  return (
    <div ref={wrapRef} className="cust-combo" style={maxWidth ? { maxWidth } : undefined}>
      <input
        className="input cust-combo__in"
        disabled={disabled}
        placeholder={placeholder}
        value={open ? query : selected?.name ?? ""}
        onFocus={() => { setOpen(true); setActive(0); }}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, matches.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          else if (e.key === "Enter") { e.preventDefault(); if (open && matches[active]) pick(matches[active].id); }
          else if (e.key === "Escape") { setOpen(false); }
        }}
      />
      {open && !disabled && (
        <div className="cust-combo__pop" role="listbox">
          <button
            type="button" className="cust-combo__opt cust-combo__opt--clear"
            onMouseDown={(e) => { e.preventDefault(); pick(null); }}
          >— Bỏ chọn —</button>
          {matches.length === 0 && <div className="cust-combo__empty">Không tìm thấy khách phù hợp</div>}
          {matches.map((c, i) => (
            <button
              key={c.id} type="button"
              className={`cust-combo__opt${i === active ? " active" : ""}${c.id === value ? " sel" : ""}`}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => { e.preventDefault(); pick(c.id); }}
            >
              <span className="cc-name">{c.name}</span>
              {c.code && <span className="cc-code">{c.code}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ---- helpers cho detail view -----------------------------------------------
function statusChipClass(status: string): string {
  if (status === "accepted" || status === "converted_to_order") return "ok";
  if (status === "sent") return "sent";
  if (status === "pending_approval") return "pending";
  if (status === "rejected" || status === "expired" || status === "cancelled") return "reject";
  return "draft";
}
function vnd(v: number): string {
  return Math.round(v).toLocaleString("vi-VN") + "₫";
}
function numf(v: number): string {
  return Math.round(v).toLocaleString("vi-VN");
}
function lsGet<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}
function lsSet(key: string, val: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(val));
  } catch {
    /* ignore */
  }
}
