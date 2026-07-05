// Báo giá (Quotation / Quote) — spec-09, Phase 2B/2C/2D.
// Danh sách phiếu (mã+version, khách, tổng giá bán, trạng thái, hạn hiệu lực) + Tạo/Sửa
// (H-V-I structure, multi-quantity spreadsheet pricing table, version timeline, PDF preview & Order handoff).
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type EnumOption,
  type PinnedCustomer,
  type QuotationDetail,
  type QuotationEnumsOut,
  type QuotationRow,
  type QuotationStats,
  type QuotePick,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { StatusTabs } from "../components/StatusTabs";
import { DarkSummaryPanel } from "../components/DarkSummaryPanel";
import "./bao-gia.css";

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

        <Button
          variant="accent"
          onClick={() => {
            setEditing(null);
            setPreSelectedEstimateId(null);
            setPinned(null);
            setMode("create");
          }}
        >
          + Báo giá mới (pick từ Tính giá)
        </Button>
      </div>

      {/* Tab trạng thái đếm số — "Cần xử lý" = nháp + đã gửi chờ khách */}
      <div style={{ margin: "12px 0 16px" }}>
        <StatusTabs
          tabs={[
            { key: "", label: "Tất cả", count: stats?.total },
            { key: "need_action", label: "Cần xử lý", count: stats?.need_action, tone: "alert" },
            { key: "draft", label: "Soạn", count: stats?.draft },
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

      {detail && (
        <QuotationDetailDialog
          quotationId={detail.id}
          statuses={statuses}
          navigate={navigate}
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
  const [customerNote, setCustomerNote] = useState<string>(existing?.customer_note ?? "");
  const [internalNote, setInternalNote] = useState<string>(existing?.internal_note ?? "");

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
          customer_note: customerNote,
          internal_note: internalNote,
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
          customer_note: customerNote,
          internal_note: internalNote,
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
          customer_note: customerNote,
          internal_note: internalNote,
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
                  <label className="field">
                    <span className="field__label">Khách hàng *</span>
                    <select className="input" value={customerId} onChange={(e) => setCustomerId(e.target.value)} disabled={isEdit}>
                      <option value="">— Chọn Khách hàng (CRM) —</option>
                      {customers.map((c) => (
                        <option key={c.id} value={c.id}>{c.name} ({c.code})</option>
                      ))}
                    </select>
                  </label>
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

              <div className="bg__form-grid" style={{ marginTop: "16px" }}>
                <label className="field">
                  <span className="field__label">Ghi chú đối ngoại (In trên PDF)</span>
                  <textarea className="input bg__textarea" value={customerNote} onChange={(e) => setCustomerNote(e.target.value)} placeholder="Ví dụ: Đơn giá đã bao gồm khuôn bế..." />
                </label>
                <label className="field">
                  <span className="field__label">Ghi chú nội bộ</span>
                  <textarea className="input bg__textarea" value={internalNote} onChange={(e) => setInternalNote(e.target.value)} placeholder="Thông tin lưu ý cho phòng sản xuất..." />
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

// --- Detail dialog (Commercial & Internal views, Version Timeline & PDF Preview) ------------------------------------------------

// Nhãn HÀNH ĐỘNG cho nút chuyển trạng thái (statuses H-V-I mới).
const TRANSITION_LABELS: Record<string, string> = {
  sent: "Gửi khách",
  accepted: "Khách duyệt",
  rejected: "Từ chối",
  expired: "Đánh dấu hết hạn",
  converted_to_order: "Tạo đơn hàng",
  cancelled: "Hủy",
};

// Gói biên lợi nhuận — shortcut UI (ô % từng dòng vẫn nhận giá trị bất kỳ;
// đợt sau chuyển thành catalog cấu hình được theo luật "không hardcode số liệu").
const MARGIN_PRESETS: Array<[string, number]> = [
  ["Tiêu chuẩn", 25],
  ["Khách quen", 18],
  ["Đơn gấp/khó", 35],
  ["Cạnh tranh", 12],
];

const STATUS_LABEL_SHORT: Record<string, string> = {
  sent: "gửi khách",
  accepted: "được khách chốt",
  rejected: "bị từ chối",
  expired: "hết hạn",
  converted_to_order: "lên đơn hàng",
  cancelled: "hủy",
};

function QuotationDetailDialog({
  quotationId,
  statuses,
  navigate,
  onClose,
  onEdit,
  onChanged,
}: {
  quotationId: number;
  statuses: EnumOption[];
  navigate?: (id: string, params?: any) => void;
  onClose: () => void;
  onEdit: (d: QuotationDetail) => void;
  onChanged: () => void;
}) {
  const { token } = useAuth();
  // Xuất PDF đối ngoại = quyền chi tiết `export` (tách khỏi "xem").
  const canExport = useCan()("bao_gia", "export");
  const canRequote = useCan()("bao_gia", "requote");
  const canCancel = useCan()("bao_gia", "cancel");
  // Thao tác trạng thái chung (gửi / từ chối / đánh dấu hết hạn…) — tách khỏi "sửa".
  const canManageStatus = useCan()("bao_gia", "manage_status");
  const [d, setD] = useState<QuotationDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Detail Tabs
  const [activeTab, setActiveTab] = useState<"commercial" | "internal" | "timeline" | "pdf">("commercial");

  // Lifecycle states
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

  async function doRequote() {
    if (!token || !d) return;
    setBusy(true);
    setErr(null);
    try {
      const nv = await api.quotations.requote(token, d.id);
      setD(nv);
      setActiveTab("commercial");
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Re-quote không thành công.");
    } finally {
      setBusy(false);
    }
  }

  /** Gói biên: áp 1 mức % cho TOÀN BỘ dòng (chỉ khi còn nháp). */
  async function applyMarginAll(pct: number) {
    if (!token || !d || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await api.quotations.update(token, d.id, {
        customer_id: d.customer_id,
        valid_until: d.valid_until,
        payment_terms: d.payment_terms,
        delivery_terms: d.delivery_terms,
        delivery_address: d.delivery_address,
        customer_note: d.customer_note,
        internal_note: d.internal_note,
        items: d.items.map((it) => ({
          id: it.id,
          margin_percent: pct,
          discount_amount: it.discount_amount,
          discount_percent: 0,
          vat_percent: it.vat_percent,
          rounding: "no_rounding",
          note: it.note,
        })),
      });
      await reload();
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không áp được gói biên.");
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

  function handleCreateOrder() {
    if (!d || !navigate) return;
    // Redirect to Order Page, pinning this quotation
    navigate("don-hang-ban", {
      customer: d.customer ? { id: d.customer_id!, name: d.customer.name, code: "" } : undefined,
      openQuoteId: d.id, // pre-pin quote selection
    });
    onClose();
  }

  if (!d) {
    return (
      <div className="bg__overlay" onClick={onClose}>
        <div className="card bg__dialog bg__dialog--sm" onClick={(e) => e.stopPropagation()}>
          <div className="bg__dialog-body" role="status">
            Đang tải dữ liệu báo giá…
          </div>
        </div>
      </div>
    );
  }

  const transitions = d.allowed_transitions.filter(
    (t) => t !== "change_order" && t !== "cancelled", // custom render
  );

  return (
    <div className="bg__overlay" onClick={onClose}>
      <div className="card bg__dialog bg__dialog-fullscreen" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="bg__dialog-head">
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <h2>{d.code}</h2>
            <span className="bg__ver">v{d.version}</span>
            <StatusBadge status={d.status} statuses={statuses} />
          </div>
          <button type="button" className="bg__close" onClick={onClose} aria-label="Đóng">✕</button>
        </div>

        <div className="bg__dialog-body">
          {/* Detail layout structure: Tab navigation + Content pane */}
          <div className="bg__detail-tabs-nav">
            <button className={`bg__tab-btn ${activeTab === "commercial" ? "active" : ""}`} onClick={() => setActiveTab("commercial")}>
              📄 Báo giá gửi khách (Đối ngoại)
            </button>
            <button className={`bg__tab-btn ${activeTab === "internal" ? "active" : ""}`} onClick={() => setActiveTab("internal")}>
              🔐 Phân tích lợi nhuận (Nội bộ)
            </button>
            <button className={`bg__tab-btn ${activeTab === "timeline" ? "active" : ""}`} onClick={() => setActiveTab("timeline")}>
              🕒 Lịch sử phiên bản ({d.versions.length})
            </button>
            <button className={`bg__tab-btn ${activeTab === "pdf" ? "active" : ""}`} onClick={() => setActiveTab("pdf")} style={{ color: "var(--rust-deep)" }}>
              🖨️ Preview PDF
            </button>
          </div>

          <div className="bg__tab-content-container">
            {activeTab === "commercial" && (
              <div className="bg__commercial-tab">
                {d.customer && (
                  <div className="bg__customer-banner">
                    <p className="eyebrow">KHÁCH HÀNG / CLIENT</p>
                    <h3>{d.customer.name}</h3>
                    {d.customer.tax_code && <p className="text-gray-500">MST: {d.customer.tax_code}</p>}
                    <p className="text-gray-500">{d.customer.credit_status_display}</p>
                  </div>
                )}

                <div className="bg__items-table-container">
                  <table className="bg__detail-table">
                    <thead>
                      <tr>
                        <th style={{ width: "50px" }}>STT</th>
                        <th>Tên sản phẩm / Quy cách</th>
                        <th className="bg__num">Số lượng</th>
                        <th>Đơn vị</th>
                        <th className="bg__num">Đơn giá</th>
                        <th className="bg__num">Chiết khấu</th>
                        <th style={{ textAlign: "center" }}>VAT</th>
                        <th className="bg__num">Thành tiền (gồm VAT)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.items.map((item, idx) => (
                        <tr key={item.id}>
                          <td>{idx + 1}</td>
                          <td>
                            <strong>{item.product_name}</strong>
                            {item.note && <span className="bg__item-table-note">{item.note}</span>}
                          </td>
                          <td className="bg__num bg__mono">{item.quantity.toLocaleString("vi-VN")}</td>
                          <td>{item.unit}</td>
                          <td className="bg__num bg__mono">{fmtVnd(item.unit_price)}</td>
                          <td className="bg__num bg__mono text-danger">- {fmtVnd(item.discount_amount)}</td>
                          <td style={{ textAlign: "center" }}>{item.vat_percent}%</td>
                          <td className="bg__num bg__mono font-bold text-rust-deep">{fmtVnd(item.final_amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="bg__commercial-footer">
                  {/* Terms on left */}
                  <div className="bg__terms-col">
                    <h4 className="font-bold text-gray-700">Điều khoản & Ghi chú thương mại</h4>
                    {d.payment_terms && (
                      <p><strong>Thanh toán:</strong> {d.payment_terms}</p>
                    )}
                    {d.delivery_terms && (
                      <p><strong>Vận chuyển:</strong> {d.delivery_terms}</p>
                    )}
                    {d.delivery_address && (
                      <p><strong>Địa chỉ giao hàng:</strong> {d.delivery_address}</p>
                    )}
                    {d.customer_note && (
                      <p><strong>Ghi chú:</strong> {d.customer_note}</p>
                    )}
                  </div>

                  {/* Totals on right */}
                  <div className="bg__totals-col">
                    <div className="bg__total-row">
                      <span>Cộng tiền hàng:</span>
                      <span className="bg__mono">{fmtVnd(d.subtotal_amount)}</span>
                    </div>
                    <div className="bg__total-row">
                      <span>Chiết khấu thương mại:</span>
                      <span className="bg__mono text-danger">- {fmtVnd(d.discount_amount)}</span>
                    </div>
                    <div className="bg__total-row">
                      <span>Thuế GTGT (VAT):</span>
                      <span className="bg__mono">{fmtVnd(d.vat_amount)}</span>
                    </div>
                    <div className="bg__total-row bg__total-row--final">
                      <span>TỔNG TIỀN PHẢI THANH TOÁN:</span>
                      <span className="text-2xl text-rust-deep">{fmtVnd(d.total)}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === "internal" && (
              <div className="bg__internal-tab">
                <div className="banner banner--warn" style={{ marginBottom: "20px" }}>
                  <span>⚠️ <strong>Thông tin nội bộ:</strong> Giá vốn và biên lợi nhuận chỉ hiển thị cho nhân viên kinh doanh sở hữu và cấp quản lý. Tuyệt đối không gửi bản in này cho khách hàng.</span>
                </div>

                {/* Panel GIÁ BÁN ĐỀ XUẤT + gói biên (kiểu phiếu tính giá nhà in) */}
                <div style={{ maxWidth: "420px", marginBottom: "20px" }}>
                  <DarkSummaryPanel
                    label="GIÁ BÁN ĐỀ XUẤT"
                    labelExtra={`V${d.version}`}
                    amount={Math.round(d.total).toLocaleString("vi-VN")}
                    sub={`${d.items.length} dòng · giá vốn khóa từ phiếu tính giá`}
                    rows={[
                      { label: "Giá vốn (khóa)", value: fmtVnd(d.total_cost) },
                      { label: "Lợi nhuận gộp", value: fmtVnd(d.subtotal_amount - d.total_cost) },
                      { label: "Giá bán (chưa VAT)", value: fmtVnd(d.subtotal_amount - d.discount_amount) },
                      { label: "VAT", value: fmtVnd(d.vat_amount) },
                      { label: "Tổng cộng", value: fmtVnd(d.total), total: true },
                    ]}
                  >
                    {d.status === "draft" ? (
                      <div>
                        <span style={{ fontSize: "10.5px", letterSpacing: "0.08em", color: "var(--ash-2)", fontWeight: 700 }}>
                          LỢI NHUẬN · GÓI BIÊN — ÁP CẢ PHIẾU
                        </span>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px", marginTop: "6px" }}>
                          {MARGIN_PRESETS.map(([label, pct]) => {
                            const isActive = d.items.length > 0 && d.items.every((it) => Math.round(it.margin_percent) === pct);
                            return (
                              <button
                                key={label}
                                type="button"
                                disabled={busy}
                                onClick={() => applyMarginAll(pct)}
                                style={{
                                  border: `1px solid ${isActive ? "var(--rust)" : "rgba(245,241,232,0.25)"}`,
                                  background: isActive ? "var(--rust)" : "transparent",
                                  color: isActive ? "#fff" : "var(--rule)",
                                  borderRadius: "6px",
                                  padding: "7px 10px",
                                  cursor: busy ? "wait" : "pointer",
                                  textAlign: "left",
                                  fontSize: "12.5px",
                                  lineHeight: 1.3,
                                }}
                              >
                                {label}
                                <strong style={{ display: "block", fontSize: "14px" }}>{pct}%</strong>
                              </button>
                            );
                          })}
                        </div>
                        <p style={{ fontSize: "11px", color: "var(--ash-2)", marginTop: "6px", lineHeight: 1.5 }}>
                          Chỉnh % lẻ từng dòng: nút "Sửa" (bảng định giá).
                        </p>
                      </div>
                    ) : (
                      <p style={{ fontSize: "11.5px", color: "var(--ash-2)", lineHeight: 1.5 }}>
                        Phiếu đã {STATUS_LABEL_SHORT[d.status] ?? d.status} — muốn đổi biên, dùng "Re-quote" tạo phiên bản mới.
                      </p>
                    )}
                  </DarkSummaryPanel>
                </div>

                <table className="bg__detail-table">
                  <thead>
                    <tr>
                      <th style={{ width: "50px" }}>STT</th>
                      <th>Quy cách sản phẩm</th>
                      <th className="bg__num">Số lượng</th>
                      <th className="bg__num">Giá vốn nội bộ (đ)</th>
                      <th className="bg__num">Biên lãi dự kiến (Margin)</th>
                      <th className="bg__num">Biên lãi thực tế (Actual)</th>
                      <th className="bg__num">Giá bán chưa VAT</th>
                      <th className="bg__num">Lợi nhuận gộp (đ)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.items.map((item, idx) => {
                      const netSelling = item.selling_price - item.discount_amount;
                      const profit = netSelling - item.total_cost_snapshot;
                      const actualMargin = netSelling > 0 ? (profit / netSelling) * 100 : 0;
                      return (
                        <tr key={item.id} className={profit < 0 ? "bg__row-cat-outsource" : ""}>
                          <td>{idx + 1}</td>
                          <td><strong>{item.product_name}</strong></td>
                          <td className="bg__num bg__mono">{item.quantity.toLocaleString("vi-VN")}</td>
                          <td className="bg__num bg__mono text-gray-500">{fmtVnd(item.total_cost_snapshot)}</td>
                          <td className="bg__num bg__mono">{item.margin_percent.toFixed(1)}%</td>
                          <td className={`bg__num bg__mono font-bold ${actualMargin < 0 ? "text-danger" : "text-moss-deep"}`}>
                            {actualMargin.toFixed(1)}%
                          </td>
                          <td className="bg__num bg__mono">{fmtVnd(netSelling)}</td>
                          <td className={`bg__num bg__mono font-bold ${profit < 0 ? "text-danger" : "text-moss-deep"}`}>
                            {fmtVnd(profit)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                {d.internal_note && (
                  <div className="bg__internal-notes" style={{ marginTop: "24px" }}>
                    <h4>Ghi chú sản xuất / Ghi chú nội bộ</h4>
                    <p className="bg__internal-note-content">{d.internal_note}</p>
                  </div>
                )}
              </div>
            )}

            {activeTab === "timeline" && (
              <div className="bg__timeline-tab">
                <div className="bg__timeline">
                  {d.versions.map((v) => {
                    const isCurrent = v.id === d.id;
                    return (
                      <div key={v.id} className={`bg__timeline-node ${isCurrent ? "is-current" : ""}`}>
                        <div className="bg__timeline-badge">
                          v{v.version}
                        </div>
                        <div className="bg__timeline-content">
                          <div className="bg__timeline-header">
                            <h4>Phiên bản v{v.version} {isCurrent && <span className="bg__badge bg__badge--ok">Hiện tại</span>}</h4>
                            <span className="bg__timeline-date">{fmtDate(v.created_at)}</span>
                          </div>
                          <div className="bg__timeline-details" style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "8px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                              <span className="text-gray-500">Trạng thái phiên bản:</span>
                              <StatusBadge status={v.status} statuses={statuses} />
                            </div>
                            <div>
                              <span className="text-gray-500">Tổng giá trị chào thầu:</span> <strong style={{ color: "var(--rust-deep)", marginLeft: "4px" }}>{fmtVnd(v.total)}</strong>
                            </div>
                            {v.change_reason && (
                              <p className="bg__timeline-reason">Lý do điều chỉnh: <em>"{v.change_reason}"</em></p>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {activeTab === "pdf" && (
              <div className="bg__pdf-tab">
                <div className="bg__pdf-preview-header">
                  <span>Xem trước định dạng PDF in gửi khách hàng</span>
                  {canExport && (
                    <Button variant="ghost" onClick={openPdf}>🖨️ Tải bản PDF</Button>
                  )}
                </div>
                <div className="bg__pdf-mockup-frame">
                  <div className="bg__pdf-mockup-sheet">
                    <div style={{ textAlign: "center", borderBottom: "2px solid #000", paddingBottom: "15px", marginBottom: "25px" }}>
                      <h1 style={{ fontSize: "24px", margin: 0, letterSpacing: "0.1em" }}>BÁO GIÁ THƯƠNG MẠI</h1>
                      <p style={{ margin: "5px 0 0", fontSize: "12px", color: "var(--ash)" }}>SAO VIỆT ERP — COMMERCIAL QUOTATION</p>
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "20px", fontSize: "12px" }}>
                      <div>
                        <p><strong>Mã báo giá:</strong> {d.code} / v{d.version}</p>
                        {d.customer && (
                          <>
                            <p><strong>Khách hàng:</strong> {d.customer.name}</p>
                            {d.customer.tax_code && <p><strong>MST:</strong> {d.customer.tax_code}</p>}
                          </>
                        )}
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <p><strong>Ngày báo giá:</strong> {fmtDate(d.versions.find(v => v.id === d.id)?.created_at ?? null)}</p>
                        {d.valid_until && <p><strong>Hiệu lực đến:</strong> {fmtDate(d.valid_until)}</p>}
                      </div>
                    </div>

                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", marginBottom: "25px" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid #000", fontWeight: "bold", textAlign: "left" }}>
                          <th style={{ padding: "8px 4px" }}>STT</th>
                          <th style={{ padding: "8px 4px" }}>Sản phẩm / Quy cách</th>
                          <th style={{ padding: "8px 4px", textAlign: "right" }}>Số lượng</th>
                          <th style={{ padding: "8px 4px" }}>Đơn vị</th>
                          <th style={{ padding: "8px 4px", textAlign: "right" }}>Đơn giá (đ)</th>
                          <th style={{ padding: "8px 4px", textAlign: "right" }}>VAT</th>
                          <th style={{ padding: "8px 4px", textAlign: "right" }}>Thành tiền (đ)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.items.map((item, idx) => (
                          <tr key={item.id} style={{ borderBottom: "1px dashed #eee" }}>
                            <td style={{ padding: "8px 4px" }}>{idx + 1}</td>
                            <td style={{ padding: "8px 4px" }}>
                              <strong>{item.product_name}</strong>
                              {item.note && <div style={{ fontSize: "10px", color: "var(--ash)" }}>{item.note}</div>}
                            </td>
                            <td style={{ padding: "8px 4px", textAlign: "right" }}>{item.quantity.toLocaleString("vi-VN")}</td>
                            <td style={{ padding: "8px 4px" }}>{item.unit}</td>
                            <td style={{ padding: "8px 4px", textAlign: "right" }}>{Math.round(item.unit_price).toLocaleString("vi-VN")}</td>
                            <td style={{ padding: "8px 4px", textAlign: "right" }}>{item.vat_percent}%</td>
                            <td style={{ padding: "8px 4px", textAlign: "right", fontWeight: "bold" }}>{Math.round(item.final_amount).toLocaleString("vi-VN")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>

                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", marginTop: "15px" }}>
                      <div style={{ width: "60%" }}>
                        <p style={{ fontWeight: "bold", marginBottom: "5px" }}>ĐIỀU KHOẢN THƯƠNG MẠI</p>
                        {d.payment_terms && <p style={{ margin: "2px 0" }}>- Thanh toán: {d.payment_terms}</p>}
                        {d.delivery_terms && <p style={{ margin: "2px 0" }}>- Giao nhận: {d.delivery_terms}</p>}
                        {d.customer_note && <p style={{ margin: "2px 0" }}>- Ghi chú: {d.customer_note}</p>}
                      </div>
                      <div style={{ width: "35%", textAlign: "right" }}>
                        <p style={{ margin: "4px 0" }}>Tổng tiền hàng: {fmtVnd(d.subtotal_amount)}</p>
                        <p style={{ margin: "4px 0" }}>Chiết khấu: -{fmtVnd(d.discount_amount)}</p>
                        <p style={{ margin: "4px 0" }}>Thuế VAT: {fmtVnd(d.vat_amount)}</p>
                        <p style={{ margin: "6px 0 0", fontSize: "14px", fontWeight: "bold", borderTop: "1px solid #000", paddingTop: "6px" }}>
                          TỔNG CỘNG: {fmtVnd(d.total)}
                        </p>
                    </div>
                  </div>

                  {/* Signature Block */}
                    <div style={{ display: "flex", justifyContent: "space-between", marginTop: "60px", fontSize: "11px", borderTop: "1px dashed #ddd", paddingTop: "20px" }}>
                      <div style={{ width: "45%", textAlign: "center" }}>
                        <p style={{ fontWeight: "bold", margin: "0 0 60px" }}>ĐẠI DIỆN KHÁCH HÀNG (BÊN A)</p>
                        <p style={{ color: "var(--ash-2)", fontSize: "10px" }}>(Ký, ghi rõ họ tên)</p>
                      </div>
                      <div style={{ width: "45%", textAlign: "center" }}>
                        <p style={{ fontWeight: "bold", margin: "0 0 60px" }}>ĐẠI DIỆN SAO VIỆT ERP (BÊN B)</p>
                        <p style={{ color: "var(--ash-2)", fontSize: "10px" }}>(Ký, đóng dấu và ghi rõ họ tên)</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {err && (
            <div className="banner banner--error" role="alert" style={{ marginTop: "15px" }}>
              {err}
            </div>
          )}

          {askCancel && (
            <label className="field" style={{ marginTop: "15px" }}>
              <span className="field__label">Lý do hủy báo giá *</span>
              <input
                className="input input--error"
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="Nhập lý do hủy bắt buộc..."
                autoFocus
              />
            </label>
          )}

          <div className="bg__dialog-actions bg__dialog-actions--wrap" style={{ marginTop: "24px" }}>
            {d.status === "draft" && (
              <Button type="button" variant="ghost" onClick={() => onEdit(d)}>
                Sửa báo giá
              </Button>
            )}
            
            {canExport && (
              <Button type="button" variant="ghost" onClick={openPdf}>
                Xuất PDF
              </Button>
            )}

            {canRequote && d.allowed_transitions.includes("change_order") && (
              <Button type="button" variant="ghost" onClick={doRequote} disabled={busy}>
                Re-quote (Tạo V{d.version + 1})
              </Button>
            )}

            {d.status === "accepted" && navigate && (
              <Button type="button" variant="accent" onClick={handleCreateOrder} title="Tạo Đơn hàng bán thực tế từ báo giá được khách duyệt này">
                🛒 Tạo đơn hàng
              </Button>
            )}

            {transitions
              // Ẩn nút mà người dùng không có quyền: 'accepted' cần quyền Duyệt; các
              // trạng thái khác (gửi/từ chối/hết hạn) cần quyền Thao tác trạng thái.
              .filter((t) => (t === "accepted" ? d.can_approve : canManageStatus))
              .map((t) => (
                <Button
                  key={t}
                  type="button"
                  variant={t === "accepted" ? "primary" : "ghost"}
                  disabled={busy}
                  onClick={() => doTransition(t)}
                >
                  {TRANSITION_LABELS[t] ?? t}
                </Button>
              ))}

            {canCancel && d.status !== "cancelled" && d.status !== "converted_to_order" && (
              <Button
                type="button"
                variant="danger"
                disabled={busy}
                onClick={() => doTransition("cancelled")}
              >
                {askCancel ? "Xác nhận Hủy" : "Hủy báo giá"}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
