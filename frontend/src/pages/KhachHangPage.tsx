// Khách hàng — CRM-360 (spec-06). List-Report với KPI header strip + filter tabs +
// bảng định-danh (tier sao, tags, badge) → slide-over Object-page (header + gauge uy tín,
// toolbar hành động, tabs Dashboard / Lịch sử mua hàng / Lịch sử báo giá). MỌI số liệu
// (KPI, doanh số 12T, cơ cấu SP, tần suất đặt, lịch sử) tính từ ĐƠN HÀNG / BÁO GIÁ THẬT;
// thiếu dữ liệu → empty state trung thực (không bịa số). Công nợ chỉ-đọc qua SEAM-16.
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type CustomerAddress,
  type CustomerAddressInput,
  type CustomerAttachment,
  type CustomerAuditRow,
  type CustomerContact,
  type CustomerContactInput,
  type CustomerDashboard,
  type CustomerInput,
  type CustomerKpis,
  type CustomerRow,
  type CustomerTier,
  type DuplicateWarn,
  type ImportResultOut,
  type OrderHistoryRow,
  type PinnedCustomer,
  type QuoteHistoryRow,
  type ReceivableCard,
  type SaleOption,
} from "../api/client";
import type { NavigateFn } from "../components/AppShell";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Select } from "../components/Select";
import "./khach-hang.css";

/** The customer slice CRM hands to a target screen when navigating (pin, no hand-typed ID). */
function pinOf(c: CustomerRow): PinnedCustomer {
  return { id: c.id, code: c.code, name: c.name, tax_code: c.tax_code };
}

const MST_RE = /^(\d{10}|\d{13})$/;
const PAGE_SIZES = [25, 50, 100];

function money(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("vi-VN") + " ₫";
}
function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("vi-VN");
}

const TIER_META: Record<CustomerTier, { label: string; stars: number; cls: string }> = {
  loyal: { label: "Thân thiết", stars: 3, cls: "tier--loyal" },
  partner: { label: "Đối tác lâu năm", stars: 2, cls: "tier--partner" },
  regular: { label: "Đang giao dịch", stars: 1, cls: "tier--regular" },
  new: { label: "Mới", stars: 0, cls: "tier--new" },
};

const ORDER_STATUS_LABELS: Record<string, string> = {
  draft: "Nháp",
  ordered: "Đã chốt",
  on_hold: "Tạm giữ",
  change_order: "Đã đổi",
  cancelled: "Đã hủy",
};
const QUOTE_STATUS_LABELS: Record<string, string> = {
  draft: "Nháp",
  sent: "Đã gửi",
  approved: "Đã duyệt",
  rejected: "Từ chối",
  expired: "Hết hạn",
  cancelled: "Đã hủy",
  on_hold: "Tạm giữ",
  change_order: "Re-quote",
};

interface FormState {
  name: string;
  tax_code: string;
  phone: string;
  email: string;
  address: string;
  contact_name: string;
  credit_limit: string;
  sale_user_id: string;
  status: string;
  // Điều khoản thanh toán (#12).
  payment_term_type: string;
  payment_term_days: string;
  prepay_pct: string;
  payment_term_note: string;
  // Chiết khấu riêng (#14) — chỉ hiện khi có quyền `view_discount`.
  discount_trade_pct: string;
  discount_buyer_pct: string;
}
const EMPTY_FORM: FormState = {
  name: "",
  tax_code: "",
  phone: "",
  email: "",
  address: "",
  contact_name: "",
  credit_limit: "0",
  sale_user_id: "",
  status: "active",
  payment_term_type: "",
  payment_term_days: "",
  prepay_pct: "",
  payment_term_note: "",
  discount_trade_pct: "",
  discount_buyer_pct: "",
};

const STATUS_LABELS: Record<string, string> = {
  lead: "Tiềm năng",
  active: "Đang giao dịch",
  inactive: "Ngừng",
};

const DUP_FIELD_LABELS: Record<DuplicateWarn["field"], string> = {
  tax_code: "MST",
  name: "tên công ty",
  email: "email",
};

const PAYMENT_TERM_LABELS: Record<string, string> = {
  prepay: "Trả trước X%",
  net_delivery: "X ngày từ ngày nhận hàng",
  net_eom: "Đối chiếu cuối tháng + X ngày",
  custom: "Đặc thù khác (ghi chú)",
};

/** Tóm tắt điều khoản thanh toán để hiển thị (hồ sơ + bảng). */
function termSummary(c: CustomerRow): string | null {
  switch (c.payment_term_type) {
    case "prepay":
      return `Trả trước ${c.prepay_pct ?? "?"}%`;
    case "net_delivery":
      return `${c.payment_term_days ?? "?"} ngày từ ngày nhận hàng`;
    case "net_eom":
      return `Đối chiếu cuối tháng + ${c.payment_term_days ?? "?"} ngày`;
    case "custom":
      return c.payment_term_note || "Đặc thù khác";
    default:
      return null;
  }
}

// =============================================================================
// List-Report page
// =============================================================================

export function KhachHangPage({ navigate }: { navigate: NavigateFn }) {
  const { token } = useAuth();

  const [rows, setRows] = useState<CustomerRow[]>([]);
  const [kpis, setKpis] = useState<CustomerKpis | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("code");
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>(""); // "" | "active" | "inactive"
  const [saleFilter, setSaleFilter] = useState<string>("");
  const [pageSize, setPageSize] = useState(25);
  const [sales, setSales] = useState<SaleOption[]>([]);

  // Điều chuyển khách hàng: gated bằng quyền chi tiết `reassign` (Cách B) — cấu hình trong
  // ma trận phân quyền, tách khỏi quyền Sửa thông thường.
  const can = useCan();
  const canReassign = can("khach_hang", "reassign");
  const canExport = can("khach_hang", "export");
  const canCreate = can("khach_hang", "create");
  const colCount = canReassign ? 7 : 6;

  // Import / export danh bạ (#23).
  const [importOpen, setImportOpen] = useState(false);
  const [exportingBook, setExportingBook] = useState(false);

  async function exportBook() {
    if (!token || exportingBook) return;
    setExportingBook(true);
    try {
      const url = await api.customers.exportCsvBlobUrl(token);
      const a = document.createElement("a");
      a.href = url;
      a.download = "danh-ba-khach-hang.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch {
      setListError("Xuất danh bạ không thành công.");
    } finally {
      setExportingBook(false);
    }
  }
  const [reassignOpen, setReassignOpen] = useState(false);
  const [fromSale, setFromSale] = useState<number | null>(null);
  const [toSale, setToSale] = useState<number | null>(null);
  const [reassignBusy, setReassignBusy] = useState(false);
  const [reassignError, setReassignError] = useState<string | null>(null);
  const [reassignMsg, setReassignMsg] = useState<string | null>(null);

  // Chọn nhiều dòng (checkbox) → thanh thao tác "Chuyển hàng loạt".
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkTarget, setBulkTarget] = useState<number | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [editing, setEditing] = useState<CustomerRow | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setListError(null);
    setSelectedIds(new Set()); // selection is per current page/filter
    api.customers
      .list(token, {
        q: q.trim() || undefined,
        sale: saleFilter ? Number(saleFilter) : null,
        status: statusFilter || null,
        sort,
        page,
        size: pageSize,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
        setKpis(res.kpis);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setListError("Không tải được danh bạ khách hàng.");
      })
      .finally(() => setLoading(false));
  }, [token, q, saleFilter, statusFilter, sort, page, pageSize]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, sort, page, pageSize, saleFilter, statusFilter]);

  useEffect(() => {
    if (!token) return;
    api.customers.sales(token).then(setSales).catch(() => setSales([]));
  }, [token]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    load();
  }

  function openReassign() {
    setFromSale(null);
    setToSale(null);
    setReassignError(null);
    setReassignMsg(null);
    setReassignOpen(true);
  }

  function toggleRow(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const allOnPageSelected = rows.length > 0 && rows.every((r) => selectedIds.has(r.id));

  function toggleAllOnPage() {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (rows.every((r) => next.has(r.id))) rows.forEach((r) => next.delete(r.id));
      else rows.forEach((r) => next.add(r.id));
      return next;
    });
  }

  function openBulk() {
    setBulkTarget(null);
    setBulkError(null);
    setReassignMsg(null);
    setBulkOpen(true);
  }

  async function doBulkReassign() {
    if (!token || bulkBusy) return;
    const ids = [...selectedIds];
    if (ids.length === 0) {
      setBulkError("Chưa chọn khách hàng nào.");
      return;
    }
    if (bulkTarget == null) {
      setBulkError("Chọn nhân viên đích.");
      return;
    }
    setBulkBusy(true);
    setBulkError(null);
    try {
      const res = await api.customers.reassignSelected(token, ids, bulkTarget);
      setBulkOpen(false);
      const toName = sales.find((s) => s.id === bulkTarget)?.name ?? "";
      setReassignMsg(
        `Đã chuyển ${res.moved} khách hàng sang ${toName}` +
          (res.skipped ? ` (bỏ qua ${res.skipped} khách ngoài phạm vi).` : "."),
      );
      load(); // also clears selection
    } catch (err) {
      if (err instanceof ApiError) setBulkError(err.message);
      else setBulkError("Điều chuyển thất bại. Vui lòng thử lại.");
    } finally {
      setBulkBusy(false);
    }
  }

  async function doReassign() {
    if (!token || reassignBusy) return;
    if (fromSale == null || toSale == null) {
      setReassignError("Chọn nhân viên nguồn và nhân viên đích.");
      return;
    }
    if (fromSale === toSale) {
      setReassignError("Nhân viên nguồn và đích phải khác nhau.");
      return;
    }
    setReassignBusy(true);
    setReassignError(null);
    try {
      const res = await api.customers.reassign(token, fromSale, toSale);
      setReassignOpen(false);
      const fromName = sales.find((s) => s.id === fromSale)?.name ?? "";
      const toName = sales.find((s) => s.id === toSale)?.name ?? "";
      setReassignMsg(`Đã điều chuyển ${res.moved} khách hàng từ ${fromName} sang ${toName}.`);
      load();
    } catch (err) {
      if (err instanceof ApiError) setReassignError(err.message);
      else setReassignError("Điều chuyển thất bại. Vui lòng thử lại.");
    } finally {
      setReassignBusy(false);
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const openIndex = useMemo(
    () => rows.findIndex((r) => r.id === openId),
    [rows, openId],
  );

  function pageSibling(delta: number) {
    if (openIndex < 0) return;
    const next = rows[openIndex + delta];
    if (next) setOpenId(next.id);
  }

  if (forbidden) {
    return (
      <main className="kh">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Khách hàng (403).
        </div>
      </main>
    );
  }

  return (
    <main className="kh">
      <header className="kh__head">
        <div>
          <p className="eyebrow">Kinh doanh · CRM</p>
          <h1 className="kh__title">Khách hàng</h1>
          <p className="kh__sub">
            Danh bạ 360° — tìm, phân loại theo lịch sử mua thật, xem dashboard & công nợ.
          </p>
        </div>
        <div className="kh__head-actions">
          {canReassign && (
            <Button variant="ghost" onClick={openReassign} disabled={sales.length < 2}>
              Điều chuyển KH
            </Button>
          )}
          <Button
            variant="primary"
            onClick={() => {
              setEditing(null);
              setMode("create");
            }}
          >
            + Tạo khách hàng
          </Button>
        </div>
      </header>

      {reassignMsg && (
        <div className="banner banner--success" role="status">
          {reassignMsg}
        </div>
      )}

      {/* KPI header strip — số thật từ đơn hàng */}
      <KpiStrip kpis={kpis} loading={loading && !kpis} />

      <div className="kh__toolbar">
        <form className="kh__search" onSubmit={onSearch} role="search">
          <input
            className="input"
            placeholder="Tìm theo tên / MST / điện thoại…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Tìm khách hàng"
          />
          <Button type="submit" variant="ghost">
            Tìm
          </Button>
        </form>

        <div className="kh__filter">
          <Select
            ariaLabel="Lọc theo NV phụ trách"
            value={saleFilter}
            placeholder="Tất cả NV phụ trách"
            onChange={(v) => {
              setSaleFilter(v ?? "");
              setPage(1);
            }}
            options={[
              { value: "", label: "Tất cả NV phụ trách" },
              ...sales.map((s) => ({ value: String(s.id), label: s.name })),
            ]}
          />
        </div>
        <div className="kh__filter">
          <Select
            ariaLabel="Lọc theo trạng thái"
            value={statusFilter}
            placeholder="Tất cả trạng thái"
            onChange={(v) => {
              setStatusFilter(v ?? "");
              setPage(1);
            }}
            options={[
              { value: "", label: "Tất cả trạng thái" },
              { value: "lead", label: "Tiềm năng" },
              { value: "active", label: "Đang giao dịch" },
              { value: "inactive", label: "Ngừng giao dịch" },
            ]}
          />
        </div>
        <div className="kh__toolbar-io">
          {canExport && (
            <Button variant="ghost" onClick={exportBook} loading={exportingBook}>
              ⬇ Xuất CSV
            </Button>
          )}
          {canCreate && (
            <Button variant="ghost" onClick={() => setImportOpen(true)}>
              ⬆ Nhập CSV
            </Button>
          )}
        </div>
      </div>

      {/* Khoảng CỐ ĐỊNH ngay trên bảng (chỉ cho người có quyền điều chuyển): luôn giữ chiều
          cao nên khi tick chọn, thanh thao tác lấp vào đúng chỗ — danh sách KHÔNG bị đẩy. */}
      {canReassign && (
        <div className="kh__bulkslot">
          {selectedIds.size > 0 ? (
            <div className="kh__bulkbar">
              <span className="kh__bulkbar-count">Đã chọn {selectedIds.size} khách hàng</span>
              <div className="kh__bulkbar-actions">
                <Button variant="accent" onClick={openBulk}>
                  Chuyển hàng loạt
                </Button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setSelectedIds(new Set())}
                >
                  Bỏ chọn
                </button>
              </div>
            </div>
          ) : (
            <span className="kh__bulkhint">
              Tick vào ô chọn ở đầu mỗi dòng để điều chuyển khách hàng hàng loạt.
            </span>
          )}
        </div>
      )}

      <div className="card kh__tablewrap">
        <table className="kh__table">
          <thead>
            <tr>
              {canReassign && (
                <th className="kh__check-col">
                  <input
                    type="checkbox"
                    aria-label="Chọn tất cả trên trang"
                    checked={allOnPageSelected}
                    onChange={toggleAllOnPage}
                  />
                </th>
              )}
              <th>
                <SortBtn label="Khách hàng" col="name" sort={sort} onSort={setSort} />
              </th>
              <th>NV phụ trách</th>
              <th className="kh__num">
                <SortBtn label="Doanh số 12T" col="revenue" sort={sort} onSort={setSort} />
              </th>
              <th className="kh__num">
                <SortBtn label="Số đơn" col="orders" sort={sort} onSort={setSort} />
              </th>
              <th>
                <SortBtn label="Mua gần nhất" col="last_order" sort={sort} onSort={setSort} />
              </th>
              <th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              [...Array(6)].map((_, i) => (
                <tr key={i} className="kh__skelrow">
                  {[...Array(colCount)].map((__, j) => (
                    <td key={j}>
                      <span className="kh__skel" />
                    </td>
                  ))}
                </tr>
              ))
            ) : listError ? (
              <tr>
                <td colSpan={colCount} className="kh__status">
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
                <td colSpan={colCount} className="kh__empty">
                  {q || statusFilter || saleFilter ? (
                    <>
                      <p>Không có khách hàng khớp bộ lọc.</p>
                      <button
                        type="button"
                        className="btn btn--ghost"
                        onClick={() => {
                          setQ("");
                          setStatusFilter("");
                          setSaleFilter("");
                          setPage(1);
                        }}
                      >
                        Xoá bộ lọc
                      </button>
                    </>
                  ) : (
                    <>
                      <p>Chưa có khách hàng nào trong sổ.</p>
                      <Button
                        variant="primary"
                        onClick={() => {
                          setEditing(null);
                          setMode("create");
                        }}
                      >
                        + Tạo khách hàng đầu tiên
                      </Button>
                    </>
                  )}
                </td>
              </tr>
            ) : (
              rows.map((c) => {
                return (
                  <tr
                    key={c.id}
                    className={`kh__row${openId === c.id ? " is-open" : ""}`}
                    onClick={() => setOpenId(c.id)}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") setOpenId(c.id);
                    }}
                  >
                    {canReassign && (
                      <td className="kh__check-col" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          aria-label={`Chọn ${c.name}`}
                          checked={selectedIds.has(c.id)}
                          onChange={() => toggleRow(c.id)}
                        />
                      </td>
                    )}
                    <td>
                      <div className="kh__identity">
                        <span className="kh__name">{c.name}</span>
                        <span className="kh__submeta">
                          <span className="kh__mono">{c.code}</span>
                          {c.tax_code && (
                            <>
                              {" · MST "}
                              <span className="kh__mono">{c.tax_code}</span>
                            </>
                          )}
                        </span>
                      </div>
                    </td>
                    <td>{c.sale_name ?? <span className="kh__muted">Chưa gán</span>}</td>
                    <td className="kh__num kh__mono">
                      {c.revenue_12m > 0 ? money(c.revenue_12m) : <span className="kh__muted">—</span>}
                    </td>
                    <td className="kh__num kh__mono">
                      {c.orders_total > 0 ? c.orders_total : <span className="kh__muted">0</span>}
                    </td>
                    <td className="kh__mono">
                      {c.last_order_at ? fmtDate(c.last_order_at) : <span className="kh__muted">—</span>}
                    </td>
                    <td>
                      <span
                        className={`kh__badge${
                          c.status === "active"
                            ? ""
                            : c.status === "lead"
                              ? " kh__badge--lead"
                              : " kh__badge--off"
                        }`}
                      >
                        {STATUS_LABELS[c.status] ?? c.status}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {!loading && !listError && rows.length > 0 && (
        <div className="kh__pager">
          <div className="kh__pager-left">
            <span className="kh__muted">
              {total} khách · trang {page}/{totalPages}
            </span>
            <div className="kh__pager-size">
              <span className="kh__muted">Hiển thị</span>
              <Select
                ariaLabel="Số dòng mỗi trang"
                value={pageSize}
                onChange={(v) => {
                  setPageSize(v ?? 25);
                  setPage(1);
                }}
                options={PAGE_SIZES.map((n) => ({ value: n, label: String(n) }))}
              />
            </div>
          </div>
          <div className="kh__pager-btns">
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

      {mode === "create" && (
        <CustomerFormDialog
          title="Tạo khách hàng"
          initial={{ ...EMPTY_FORM }}
          sales={sales}
          isEdit={false}
          onClose={() => setMode(null)}
          onSaved={() => {
            setMode(null);
            setPage(1);
            load();
          }}
        />
      )}

      {mode === "edit" && editing && (
        <CustomerFormDialog
          title={`Sửa khách hàng · ${editing.code}`}
          code={editing.code}
          customerId={editing.id}
          isEdit
          sales={sales}
          initial={{
            name: editing.name,
            tax_code: editing.tax_code ?? "",
            phone: editing.phone ?? "",
            email: editing.email ?? "",
            address: editing.address ?? "",
            contact_name: editing.contact_name ?? "",
            credit_limit: String(editing.credit_limit),
            sale_user_id: editing.sale_user_id != null ? String(editing.sale_user_id) : "",
            status: editing.status,
            payment_term_type: editing.payment_term_type ?? "",
            payment_term_days:
              editing.payment_term_days != null ? String(editing.payment_term_days) : "",
            prepay_pct: editing.prepay_pct != null ? String(editing.prepay_pct) : "",
            payment_term_note: editing.payment_term_note ?? "",
            discount_trade_pct:
              editing.discount_trade_pct != null ? String(editing.discount_trade_pct) : "",
            discount_buyer_pct:
              editing.discount_buyer_pct != null ? String(editing.discount_buyer_pct) : "",
          }}
          onClose={() => setMode(null)}
          onSaved={() => {
            setMode(null);
            load();
          }}
        />
      )}

      {importOpen && (
        <ImportDialog
          onClose={() => setImportOpen(false)}
          onImported={() => {
            setImportOpen(false);
            setPage(1);
            load();
          }}
        />
      )}

      {openId != null && mode == null && (
        <CustomerObjectPage
          customerId={openId}
          canPrev={openIndex > 0}
          canNext={openIndex >= 0 && openIndex < rows.length - 1}
          onPrev={() => pageSibling(-1)}
          onNext={() => pageSibling(1)}
          onClose={() => setOpenId(null)}
          navigate={navigate}
          onEdit={(row) => {
            setEditing(row);
            setMode("edit");
          }}
        />
      )}

      <ConfirmDialog
        open={reassignOpen}
        title="Điều chuyển khách hàng"
        message="Chuyển TOÀN BỘ khách hàng đang phụ trách của một nhân viên sang nhân viên khác (dùng khi bàn giao). Kiểm tra kỹ nguồn/đích trước khi xác nhận."
        confirmLabel="Điều chuyển"
        danger
        countdownSeconds={5}
        busy={reassignBusy}
        error={reassignError}
        confirmDisabled={fromSale == null || toSale == null || fromSale === toSale}
        onConfirm={doReassign}
        onCancel={() => !reassignBusy && setReassignOpen(false)}
      >
        <label className="field">
          <span className="field__label">Từ nhân viên (nguồn)</span>
          <Select
            ariaLabel="Nhân viên nguồn"
            portal
            value={fromSale}
            placeholder="— Chọn nhân viên nguồn —"
            onChange={(v) => setFromSale(v)}
            options={[
              { value: null, label: "— Chọn nhân viên nguồn —" },
              ...sales.map((s) => ({ value: s.id, label: s.name })),
            ]}
          />
        </label>
        <label className="field">
          <span className="field__label">Sang nhân viên (đích)</span>
          <Select
            ariaLabel="Nhân viên đích"
            portal
            value={toSale}
            placeholder="— Chọn nhân viên đích —"
            onChange={(v) => setToSale(v)}
            options={[
              { value: null, label: "— Chọn nhân viên đích —" },
              ...sales
                .filter((s) => s.id !== fromSale)
                .map((s) => ({ value: s.id, label: s.name })),
            ]}
          />
        </label>
      </ConfirmDialog>

      <ConfirmDialog
        open={bulkOpen}
        title={`Chuyển ${selectedIds.size} khách hàng đã chọn`}
        message="Các khách hàng đang tick sẽ được chuyển sang nhân viên tiếp nhận. Kiểm tra kỹ trước khi xác nhận."
        confirmLabel="Chuyển"
        danger
        countdownSeconds={5}
        busy={bulkBusy}
        error={bulkError}
        confirmDisabled={bulkTarget == null}
        onConfirm={doBulkReassign}
        onCancel={() => !bulkBusy && setBulkOpen(false)}
      >
        <label className="field">
          <span className="field__label">Sang nhân viên (đích)</span>
          <Select
            ariaLabel="Nhân viên đích"
            portal
            value={bulkTarget}
            placeholder="— Chọn nhân viên đích —"
            onChange={(v) => setBulkTarget(v)}
            options={[
              { value: null, label: "— Chọn nhân viên đích —" },
              ...sales.map((s) => ({ value: s.id, label: s.name })),
            ]}
          />
        </label>
      </ConfirmDialog>
    </main>
  );
}

// --- KPI header strip --------------------------------------------------------

function KpiStrip({ kpis, loading }: { kpis: CustomerKpis | null; loading: boolean }) {
  const cards = [
    { label: "Tổng khách hàng", value: kpis ? String(kpis.total_customers) : "—", hint: "trong phạm vi" },
    { label: "Khách thân thiết", value: kpis ? String(kpis.loyal_count) : "—", hint: "≥ 50tr / 12T" },
    { label: "Mới trong tháng", value: kpis ? String(kpis.new_this_month) : "—", hint: "vừa vào sổ" },
    {
      label: "TB / đơn (12T)",
      value: kpis && kpis.avg_order_value > 0 ? money(kpis.avg_order_value) : "—",
      hint: "từ đơn thật",
    },
  ];
  return (
    <div className="kh__kpis">
      {cards.map((c) => (
        <div className="kh__kpi card" key={c.label}>
          <span className="kh__kpi-label">{c.label}</span>
          <span className="kh__kpi-value">{loading ? <span className="kh__skel kh__skel--kpi" /> : c.value}</span>
          <span className="kh__kpi-hint">{c.hint}</span>
        </div>
      ))}
    </div>
  );
}

function TierBadge({ tier }: { tier: CustomerTier }) {
  const meta = TIER_META[tier];
  return (
    <span className={`kh__tier ${meta.cls}`} title={meta.label}>
      <span className="kh__stars" aria-hidden="true">
        {"★".repeat(meta.stars)}
        {"☆".repeat(Math.max(0, 3 - meta.stars))}
      </span>
      {meta.label}
    </span>
  );
}

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
      className={`kh__sortbtn${active ? " is-active" : ""}`}
      onClick={() => onSort(desc ? col : active ? `-${col}` : `-${col}`)}
    >
      {label}
      {active && <span aria-hidden="true">{desc ? " ↓" : " ↑"}</span>}
    </button>
  );
}

// =============================================================================
// Object-page slide-over
// =============================================================================

type Tab = "dashboard" | "orders" | "quotes" | "contacts" | "addresses" | "files" | "audit";

function CustomerObjectPage({
  customerId,
  canPrev,
  canNext,
  onPrev,
  onNext,
  onClose,
  onEdit,
  navigate,
}: {
  customerId: number;
  canPrev: boolean;
  canNext: boolean;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
  onEdit: (row: CustomerRow) => void;
  navigate: NavigateFn;
}) {
  const { token } = useAuth();
  const [customer, setCustomer] = useState<CustomerRow | null>(null);
  const [dash, setDash] = useState<CustomerDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("dashboard");
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setCustomer(null);
    setDash(null);
    setError(null);
    Promise.all([api.customers.get(token, customerId), api.customers.dashboard(token, customerId)])
      .then(([detail, d]) => {
        if (cancelled) return;
        setCustomer(detail.customer);
        setDash(d);
      })
      .catch(() => !cancelled && setError("Không tải được hồ sơ khách hàng."));
    return () => {
      cancelled = true;
    };
  }, [token, customerId]);

  // Esc closes; focus panel on open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const receivable: ReceivableCard | undefined = dash?.receivable;

  return (
    <div className="kh__scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside
        className="kh__slideover"
        role="dialog"
        aria-modal="true"
        aria-label="Hồ sơ khách hàng"
        ref={panelRef}
        tabIndex={-1}
      >
        <div className="kh__so-topbar">
          <div className="kh__so-nav">
            <button type="button" className="kh__iconbtn" disabled={!canPrev} onClick={onPrev} aria-label="Khách trước">
              ▲
            </button>
            <button type="button" className="kh__iconbtn" disabled={!canNext} onClick={onNext} aria-label="Khách sau">
              ▼
            </button>
          </div>
          <button type="button" className="kh__close" aria-label="Đóng" onClick={onClose}>
            ✕
          </button>
        </div>

        {error ? (
          <div className="kh__so-body">
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          </div>
        ) : !customer || !dash ? (
          <div className="kh__so-body">
            <div className="kh__so-headskel">
              <span className="kh__skel kh__skel--title" />
              <span className="kh__skel kh__skel--line" />
            </div>
            <div className="kh__kpis">
              {[...Array(4)].map((_, i) => (
                <div className="kh__kpi card" key={i}>
                  <span className="kh__skel kh__skel--kpi" />
                </div>
              ))}
            </div>
          </div>
        ) : (
          <>
            <ObjectHeader
              customer={customer}
              dash={dash}
              onEdit={() => onEdit(customer)}
              navigate={navigate}
              onClose={onClose}
            />
            <nav className="kh__so-tabs" aria-label="Nội dung">
              {(
                [
                  ["dashboard", "Dashboard"],
                  ["orders", "Lịch sử mua hàng"],
                  ["quotes", "Lịch sử báo giá"],
                  ["contacts", "Liên hệ"],
                  ["addresses", "Giao hàng"],
                  ["files", "Tài liệu"],
                  ["audit", "Nhật ký"],
                ] as [Tab, string][]
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={`kh__so-tab${tab === key ? " is-active" : ""}`}
                  aria-current={tab === key ? "true" : undefined}
                  onClick={() => setTab(key)}
                >
                  {label}
                </button>
              ))}
            </nav>

            <div className="kh__so-body">
              {tab === "dashboard" && <DashboardTab dash={dash} receivable={receivable} />}
              {tab === "orders" && (
                <OrdersTab
                  customerId={customerId}
                  code={customer.code}
                  onOpenOrder={(id) => {
                    onClose();
                    navigate("don-hang-ban", { openOrderId: id });
                  }}
                />
              )}
              {tab === "quotes" && (
                <QuotesTab
                  customerId={customerId}
                  onOpenQuote={(id) => {
                    onClose();
                    navigate("bao-gia", { openQuoteId: id });
                  }}
                />
              )}
              {tab === "contacts" && <ContactsTab customerId={customerId} />}
              {tab === "addresses" && <AddressesTab customerId={customerId} />}
              {tab === "files" && <AttachmentsTab customerId={customerId} />}
              {tab === "audit" && (
                <AuditTab
                  customerId={customerId}
                  onDrill={(refType, id) => {
                    onClose();
                    if (refType === "order") navigate("don-hang-ban", { openOrderId: id });
                    else navigate("bao-gia", { openQuoteId: id });
                  }}
                />
              )}
            </div>
          </>
        )}
      </aside>
    </div>
  );
}

function ObjectHeader({
  customer,
  dash,
  onEdit,
  navigate,
  onClose,
}: {
  customer: CustomerRow;
  dash: CustomerDashboard;
  onEdit: () => void;
  navigate: NavigateFn;
  onClose: () => void;
}) {
  const canDebt = useCan()("khach_hang", "view_debt");
  const rec = dash.receivable;
  // Gauge uy tín thanh toán: chỉ khi Công nợ sẵn sàng; nếu không → seam trung thực.
  const usage = rec.available && rec.usage_pct != null ? rec.usage_pct : null;

  const tel = customer.phone ? `tel:${customer.phone}` : undefined;
  const mail = customer.email ? `mailto:${customer.email}` : undefined;
  const zalo = customer.phone ? `https://zalo.me/${customer.phone.replace(/\D/g, "")}` : undefined;

  return (
    <header className="kh__so-head">
      <div className="kh__so-headmain">
        <div className="kh__so-title">
          <h2>{customer.name}</h2>
          <TierBadge tier={customer.tier} />
        </div>
        <dl className="kh__so-facts">
          <div>
            <dt>Mã KH</dt>
            <dd className="kh__mono">{customer.code}</dd>
          </div>
          <div>
            <dt>MST</dt>
            <dd className="kh__mono">{customer.tax_code ?? "—"}</dd>
          </div>
          <div>
            <dt>Khách từ</dt>
            <dd className="kh__mono">{fmtDate(customer.created_at)}</dd>
          </div>
          <div>
            <dt>LTV (12T)</dt>
            <dd className="kh__mono">{dash.revenue_12m > 0 ? money(dash.revenue_12m) : "—"}</dd>
          </div>
          <div>
            <dt>Liên hệ</dt>
            <dd>{customer.contact_name ?? "—"}{customer.phone ? ` · ${customer.phone}` : ""}</dd>
          </div>
          <div>
            <dt>NV phụ trách</dt>
            <dd>{customer.sale_name ?? "Chưa gán"}</dd>
          </div>
          <div>
            <dt>Điều khoản TT</dt>
            <dd>{termSummary(customer) ?? "Chưa khai"}</dd>
          </div>
          {!customer.discount_hidden && (
            <div>
              <dt>Chiết khấu</dt>
              <dd>
                {customer.discount_trade_pct != null || customer.discount_buyer_pct != null
                  ? `TM ${customer.discount_trade_pct ?? "—"}% · NM ${customer.discount_buyer_pct ?? "—"}%`
                  : "Chưa khai"}
              </dd>
            </div>
          )}
        </dl>
      </div>

      {canDebt ? (
        <PaymentGauge usage={usage} available={rec.available} balance={rec.balance} limit={rec.credit_limit} />
      ) : (
        <div className="kh__gauge card" aria-label="Uy tín thanh toán">
          <span className="kh__kpi-label">Uy tín thanh toán</span>
          <span className="kh__seam-note">Bạn không có quyền xem công nợ</span>
        </div>
      )}

      {/* Action toolbar — drill-through to Báo giá / Đơn hàng with this customer pre-pinned. */}
      <div className="kh__toolbar-actions" role="toolbar" aria-label="Hành động">
        <a className={`btn btn--secondary${tel ? "" : " is-disabled"}`} href={tel} aria-disabled={!tel}>
          📞 Gọi
        </a>
        <a className={`btn btn--secondary${mail ? "" : " is-disabled"}`} href={mail} aria-disabled={!mail}>
          ✉ Email
        </a>
        <a
          className={`btn btn--secondary${zalo ? "" : " is-disabled"}`}
          href={zalo}
          target="_blank"
          rel="noreferrer"
          aria-disabled={!zalo}
        >
          💬 Zalo
        </a>
        <button
          type="button"
          className="btn btn--accent"
          title={`Mở màn Báo giá và ghim khách ${customer.name} (${customer.code})`}
          onClick={() => {
            onClose();
            navigate("bao-gia", { customer: pinOf(customer) });
          }}
        >
          + Tạo báo giá
        </button>
        <button
          type="button"
          className="btn btn--secondary"
          title={`Mở màn Đơn hàng bán và ghim khách ${customer.name} (${customer.code})`}
          onClick={() => {
            onClose();
            navigate("don-hang-ban", { customer: pinOf(customer) });
          }}
        >
          + Tạo đơn hàng
        </button>
        <button
          type="button"
          className="btn btn--secondary is-disabled"
          disabled
          title="Bảng kê công nợ cần phân hệ Công nợ (SEAM-16) — chưa sẵn sàng"
        >
          🧾 Xuất bảng kê công nợ (PDF)
        </button>
        <span className="kh__seam-hint" role="note">
          Bảng kê công nợ: chờ phân hệ Công nợ (SEAM-16)
        </span>
        <Button variant="ghost" onClick={onEdit}>
          Sửa
        </Button>
      </div>
    </header>
  );
}

// Gauge uy tín thanh toán — arc dựa % sử dụng hạn mức (Công nợ). SEAM-16 chưa build → seam.
function PaymentGauge({
  usage,
  available,
  balance,
  limit,
}: {
  usage: number | null;
  available: boolean;
  balance: number | null;
  limit: number;
}) {
  const pct = usage != null ? Math.min(100, Math.max(0, usage)) : 0;
  const angle = (pct / 100) * 180;
  const tone = pct >= 100 ? "signal" : pct >= 80 ? "amber" : "moss";
  return (
    <div className="kh__gauge card" aria-label="Uy tín thanh toán">
      <span className="kh__kpi-label">Uy tín thanh toán</span>
      {available ? (
        <>
          <div className={`kh__gauge-arc kh__gauge-arc--${tone}`} style={{ ["--ang" as string]: `${angle}deg` }}>
            <span className="kh__gauge-num kh__mono">{usage}%</span>
          </div>
          <span className="kh__kpi-hint">
            Dư nợ {money(balance)} / HM {money(limit)}
          </span>
        </>
      ) : (
        <div className="kh__gauge-seam">
          <div className="kh__gauge-arc kh__gauge-arc--muted" style={{ ["--ang" as string]: "0deg" }}>
            <span className="kh__gauge-num kh__muted">—</span>
          </div>
          <span className="kh__seam-note">
            Chờ phân hệ Công nợ (SEAM-16) — HM {money(limit)}
          </span>
        </div>
      )}
    </div>
  );
}

// --- Dashboard tab -----------------------------------------------------------

function DashboardTab({
  dash,
  receivable,
}: {
  dash: CustomerDashboard;
  receivable: ReceivableCard | undefined;
}) {
  if (!dash.has_data) {
    return (
      <div className="kh__empty-panel">
        <p className="kh__empty-title">Chưa có lịch sử giao dịch</p>
        <p className="kh__muted">
          Khách này chưa có đơn hàng hay báo giá nào. Dashboard sẽ tự cập nhật từ dữ liệu thật
          khi phát sinh giao dịch — không hiển thị số giả.
        </p>
      </div>
    );
  }
  const canDebt = useCan()("khach_hang", "view_debt");
  const maxRev = Math.max(1, ...dash.months.map((m) => m.revenue));
  const cards = [
    { label: "Doanh số 12T", value: money(dash.revenue_12m) },
    { label: "Số đơn 12T", value: String(dash.orders_12m) },
    { label: "TB / đơn", value: dash.avg_order_value != null ? money(dash.avg_order_value) : "—" },
    // Thẻ Công nợ chỉ hiện khi có quyền chi tiết `view_debt`.
    ...(canDebt
      ? [
          {
            label: "Công nợ",
            value: receivable?.available ? money(receivable.balance) : "chờ Công nợ",
            muted: !receivable?.available,
          },
        ]
      : []),
  ];

  return (
    <div className="kh__dash">
      <div className="kh__kpis">
        {cards.map((c) => (
          <div className="kh__kpi card" key={c.label}>
            <span className="kh__kpi-label">{c.label}</span>
            <span className={`kh__kpi-value${c.muted ? " kh__kpi-value--muted" : ""}`}>{c.value}</span>
          </div>
        ))}
      </div>

      {/* Doanh số 12 tháng — bar */}
      <section className="card kh__chart">
        <div className="kh__chart-head">
          <h3>Doanh số 12 tháng</h3>
          <span className="kh__muted">từ đơn hàng thật (không tính đơn hủy)</span>
        </div>
        <div className="kh__bars">
          {dash.months.map((m) => (
            <div className="kh__bar-col" key={m.month} title={`${m.label}: ${money(m.revenue)} · ${m.orders} đơn`}>
              <div className="kh__bar-track">
                <div
                  className="kh__bar-fill"
                  style={{ height: `${(m.revenue / maxRev) * 100}%` }}
                  aria-hidden="true"
                />
              </div>
              <span className="kh__bar-label kh__mono">{m.label}</span>
            </div>
          ))}
        </div>
      </section>

      <div className="kh__dash-grid">
        {/* Cơ cấu sản phẩm — donut */}
        <section className="card kh__chart">
          <div className="kh__chart-head">
            <h3>Cơ cấu sản phẩm</h3>
          </div>
          <ProductDonut mix={dash.product_mix} />
        </section>

        {/* Tần suất đặt — heatmap */}
        <section className="card kh__chart">
          <div className="kh__chart-head">
            <h3>Tần suất đặt hàng</h3>
            <span className="kh__muted">12 tháng × thứ trong tuần</span>
          </div>
          <Heatmap dash={dash} />
        </section>
      </div>
    </div>
  );
}

const DONUT_COLORS = ["var(--rust)", "var(--moss)", "var(--amber)", "var(--steel)", "var(--rust-deep)", "var(--ash-2)"];

function ProductDonut({ mix }: { mix: CustomerDashboard["product_mix"] }) {
  if (mix.length === 0) {
    return <p className="kh__muted kh__chart-empty">Chưa đủ dữ liệu sản phẩm 12 tháng.</p>;
  }
  const total = mix.reduce((s, m) => s + m.revenue, 0) || 1;
  let acc = 0;
  const stops = mix.slice(0, 6).map((m, i) => {
    const start = (acc / total) * 360;
    acc += m.revenue;
    const end = (acc / total) * 360;
    return `${DONUT_COLORS[i % DONUT_COLORS.length]} ${start}deg ${end}deg`;
  });
  return (
    <div className="kh__donut-wrap">
      <div
        className="kh__donut"
        style={{ background: `conic-gradient(${stops.join(",")})` }}
        role="img"
        aria-label="Cơ cấu sản phẩm theo doanh số"
      >
        <div className="kh__donut-hole">
          <span className="kh__mono">{mix.length}</span>
          <span className="kh__kpi-label">nhóm SP</span>
        </div>
      </div>
      <ul className="kh__legend">
        {mix.slice(0, 6).map((m, i) => (
          <li key={m.label}>
            <span
              className="kh__legend-dot"
              style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }}
              aria-hidden="true"
            />
            <span className="kh__legend-label">{m.label}</span>
            <span className="kh__mono kh__legend-val">{Math.round((m.revenue / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const WEEKDAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

function Heatmap({ dash }: { dash: CustomerDashboard }) {
  const maxCount = Math.max(1, ...dash.heatmap.map((h) => h.count));
  const grid = new Map<string, number>();
  for (const h of dash.heatmap) grid.set(`${h.month_index}:${h.weekday}`, h.count);
  return (
    <div className="kh__heat">
      <div className="kh__heat-row kh__heat-labels">
        <span className="kh__heat-corner" />
        {dash.months.map((m) => (
          <span key={m.month} className="kh__heat-mlabel kh__mono">
            {m.label.replace("T", "")}
          </span>
        ))}
      </div>
      {WEEKDAYS.map((wd, wi) => (
        <div className="kh__heat-row" key={wd}>
          <span className="kh__heat-wlabel kh__mono">{wd}</span>
          {dash.months.map((m, mi) => {
            const c = grid.get(`${mi}:${wi}`) ?? 0;
            const lvl = c === 0 ? 0 : Math.ceil((c / maxCount) * 4);
            return (
              <span
                key={m.month}
                className={`kh__heat-cell kh__heat-l${lvl}`}
                title={`${wd} ${m.label}: ${c} đơn`}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}

// --- Orders tab (Lịch sử mua hàng) -------------------------------------------

function OrdersTab({
  customerId,
  code,
  onOpenOrder,
}: {
  customerId: number;
  code: string;
  onOpenOrder: (id: number) => void;
}) {
  const { token } = useAuth();
  const canExport = useCan()("khach_hang", "export");
  const [rows, setRows] = useState<OrderHistoryRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setRows(null);
    setError(null);
    api.customers
      .orderHistory(token, customerId)
      .then((r) => !cancelled && setRows(r.items))
      .catch(() => !cancelled && setError("Không tải được lịch sử mua hàng."));
    return () => {
      cancelled = true;
    };
  }, [token, customerId]);

  async function exportCsv() {
    if (!token) return;
    setExporting(true);
    try {
      const url = await api.customers.orderCsvBlobUrl(token, customerId);
      const a = document.createElement("a");
      a.href = url;
      a.download = `lich-su-mua-hang-${code}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch {
      setError("Xuất Excel không thành công.");
    } finally {
      setExporting(false);
    }
  }

  if (error) return <div className="banner banner--error" role="alert">{error}</div>;
  if (rows == null) return <TableSkeleton cols={5} />;
  if (rows.length === 0)
    return (
      <div className="kh__empty-panel">
        <p className="kh__empty-title">Chưa có đơn hàng</p>
        <p className="kh__muted">Khách này chưa phát sinh đơn hàng nào (wire từ Đơn hàng bán).</p>
      </div>
    );

  return (
    <div className="kh__histwrap">
      <div className="kh__hist-toolbar">
        <span className="kh__muted">{rows.length} đơn</span>
        {canExport && (
          <Button variant="secondary" onClick={exportCsv} loading={exporting}>
            ⬇ Xuất Excel
          </Button>
        )}
      </div>
      <table className="kh__table kh__table--tight kh__table--drill">
        <thead>
          <tr>
            <th>Mã đơn</th>
            <th>Ngày</th>
            <th>Sản phẩm</th>
            <th className="kh__num">Thành tiền</th>
            <th>Trạng thái</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((o) => (
            <tr
              key={o.id}
              className="kh__drillrow"
              onClick={() => onOpenOrder(o.id)}
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && onOpenOrder(o.id)}
              title={`Mở chi tiết đơn ${o.order_no}`}
            >
              <td className="kh__mono kh__link">{o.order_no}</td>
              <td className="kh__mono">{fmtDate(o.created_at)}</td>
              <td>{o.summary}</td>
              <td className="kh__num kh__mono">{money(o.total)}</td>
              <td>
                <span className={`kh__ostat kh__ostat--${o.status}`}>
                  {ORDER_STATUS_LABELS[o.status] ?? o.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- Quotes tab (Lịch sử báo giá) --------------------------------------------

function QuotesTab({
  customerId,
  onOpenQuote,
}: {
  customerId: number;
  onOpenQuote: (id: number) => void;
}) {
  const { token } = useAuth();
  const [rows, setRows] = useState<QuoteHistoryRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setRows(null);
    setError(null);
    api.customers
      .quoteHistory(token, customerId)
      .then((r) => !cancelled && setRows(r.items))
      .catch(() => !cancelled && setError("Không tải được lịch sử báo giá."));
    return () => {
      cancelled = true;
    };
  }, [token, customerId]);

  if (error) return <div className="banner banner--error" role="alert">{error}</div>;
  if (rows == null) return <TableSkeleton cols={5} />;
  if (rows.length === 0)
    return (
      <div className="kh__empty-panel">
        <p className="kh__empty-title">Chưa có báo giá</p>
        <p className="kh__muted">Khách này chưa có báo giá nào (wire từ Báo giá in ấn).</p>
      </div>
    );

  return (
    <div className="kh__histwrap">
      <table className="kh__table kh__table--tight kh__table--drill">
        <thead>
          <tr>
            <th>Mã BG</th>
            <th>Ngày</th>
            <th className="kh__num">Tổng giá bán</th>
            <th>Hiệu lực đến</th>
            <th>Trạng thái</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((q) => (
            <tr
              key={q.id}
              className="kh__drillrow"
              onClick={() => onOpenQuote(q.id)}
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && onOpenQuote(q.id)}
              title={`Mở chi tiết báo giá ${q.code}`}
            >
              <td className="kh__mono kh__link">
                {q.code}
                <span className="kh__muted"> v{q.version}</span>
              </td>
              <td className="kh__mono">{fmtDate(q.created_at)}</td>
              <td className="kh__num kh__mono">{money(q.total)}</td>
              <td className="kh__mono">{fmtDate(q.valid_until)}</td>
              <td>
                <span className={`kh__ostat kh__ostat--${q.status}`}>
                  {QUOTE_STATUS_LABELS[q.status] ?? q.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- Nhật ký tab (unified activity timeline, real events) --------------------

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("vi-VN");
}

const AUDIT_KIND_META: Record<CustomerAuditRow["kind"], { icon: string; label: string; cls: string }> = {
  profile: { icon: "✎", label: "Hồ sơ", cls: "kh__tl--profile" },
  order: { icon: "📦", label: "Đơn hàng", cls: "kh__tl--order" },
  quote: { icon: "🧮", label: "Báo giá", cls: "kh__tl--quote" },
};

function AuditTab({
  customerId,
  onDrill,
}: {
  customerId: number;
  onDrill: (refType: "order" | "quotation", id: number) => void;
}) {
  const { token } = useAuth();
  const [rows, setRows] = useState<CustomerAuditRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setRows(null);
    setError(null);
    api.customers
      .audit(token, customerId)
      .then((r) => !cancelled && setRows(r.items))
      .catch(() => !cancelled && setError("Không tải được nhật ký khách hàng."));
    return () => {
      cancelled = true;
    };
  }, [token, customerId]);

  if (error) return <div className="banner banner--error" role="alert">{error}</div>;
  if (rows == null) return <TableSkeleton cols={3} />;
  if (rows.length === 0)
    return (
      <div className="kh__empty-panel">
        <p className="kh__empty-title">Chưa có hoạt động</p>
        <p className="kh__muted">
          Nhật ký tổng hợp mọi thay đổi hồ sơ và mốc giao dịch (đơn hàng, báo giá) của khách —
          từ dữ liệu thật, không bịa. Chưa phát sinh sự kiện nào.
        </p>
      </div>
    );

  return (
    <div className="kh__timeline">
      <p className="kh__muted kh__tl-sub">{rows.length} sự kiện · mới nhất trước</p>
      <ol className="kh__tl-list">
        {rows.map((r, i) => {
          const meta = AUDIT_KIND_META[r.kind];
          const drillable = r.ref_type != null && r.ref_id != null;
          return (
            <li
              key={`${r.kind}-${r.ref_id ?? "p"}-${i}`}
              className={`kh__tl-item ${meta.cls}${drillable ? " is-drillable" : ""}`}
              onClick={drillable ? () => onDrill(r.ref_type!, r.ref_id!) : undefined}
              tabIndex={drillable ? 0 : undefined}
              onKeyDown={
                drillable ? (e) => e.key === "Enter" && onDrill(r.ref_type!, r.ref_id!) : undefined
              }
              title={drillable ? `Mở chi tiết ${r.title}` : undefined}
            >
              <span className="kh__tl-dot" aria-hidden="true">
                {meta.icon}
              </span>
              <div className="kh__tl-body">
                <div className="kh__tl-line1">
                  <span className={`kh__tl-title${drillable ? " kh__link" : ""}`}>{r.title}</span>
                  <span className="kh__tl-kind">{meta.label}</span>
                  <span className="kh__tl-time kh__mono">{fmtDateTime(r.at)}</span>
                </div>
                {r.detail && <p className="kh__tl-detail">{r.detail}</p>}
                {r.actor_name && <p className="kh__muted kh__tl-actor">bởi {r.actor_name}</p>}
              </div>
              {drillable && <span className="kh__tl-arrow" aria-hidden="true">›</span>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// --- Liên hệ tab (#10–#11: nhiều người liên hệ, chức vụ + nhiệm vụ) -----------

interface ContactFormState {
  name: string;
  title: string;
  duty: string;
  phone: string;
  email: string;
  is_primary: boolean;
}
const EMPTY_CONTACT: ContactFormState = {
  name: "",
  title: "",
  duty: "",
  phone: "",
  email: "",
  is_primary: false,
};

function ContactsTab({ customerId }: { customerId: number }) {
  const { token } = useAuth();
  const canUpdate = useCan()("khach_hang", "update");
  const [items, setItems] = useState<CustomerContact[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null); // -1 = thêm mới
  const [form, setForm] = useState<ContactFormState>(EMPTY_CONTACT);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const reload = useCallback(() => {
    if (!token) return;
    api.customers
      .contacts(token, customerId)
      .then((r) => setItems(r.items))
      .catch(() => setError("Không tải được danh sách liên hệ."));
  }, [token, customerId]);

  useEffect(() => {
    setItems(null);
    setError(null);
    setEditingId(null);
    reload();
  }, [reload]);

  function startAdd() {
    setForm(EMPTY_CONTACT);
    setFormError(null);
    setEditingId(-1);
  }
  function startEdit(c: CustomerContact) {
    setForm({
      name: c.name,
      title: c.title ?? "",
      duty: c.duty ?? "",
      phone: c.phone ?? "",
      email: c.email ?? "",
      is_primary: c.is_primary,
    });
    setFormError(null);
    setEditingId(c.id);
  }

  async function save() {
    if (!token || busy) return;
    if (!form.name.trim()) {
      setFormError("Tên người liên hệ là bắt buộc.");
      return;
    }
    setBusy(true);
    setFormError(null);
    const input: CustomerContactInput = {
      name: form.name.trim(),
      title: form.title.trim() || null,
      duty: form.duty.trim() || null,
      phone: form.phone.trim() || null,
      email: form.email.trim() || null,
      is_primary: form.is_primary,
    };
    try {
      if (editingId === -1) await api.customers.addContact(token, customerId, input);
      else if (editingId != null)
        await api.customers.updateContact(token, customerId, editingId, input);
      setEditingId(null);
      reload();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Lưu không thành công.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    if (!token) return;
    try {
      await api.customers.deleteContact(token, customerId, id);
      reload();
    } catch {
      setError("Xóa không thành công.");
    }
  }

  if (error) return <div className="banner banner--error" role="alert">{error}</div>;
  if (items == null) return <TableSkeleton cols={4} />;

  return (
    <div className="kh__histwrap">
      <div className="kh__hist-toolbar">
        <span className="kh__muted">
          {items.length} người liên hệ · ghi rõ chức vụ + nhiệm vụ để các bộ phận tự liên hệ
        </span>
        {canUpdate && editingId == null && (
          <Button variant="secondary" onClick={startAdd}>
            + Thêm liên hệ
          </Button>
        )}
      </div>

      {editingId != null && (
        <div className="card kh__subform">
          <div className="kh__form-grid">
            <label className="field">
              <span className="field__label">Tên *</span>
              <input
                className="input"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                autoFocus
              />
            </label>
            <label className="field">
              <span className="field__label">Chức vụ</span>
              <input
                className="input"
                value={form.title}
                placeholder="Kế toán, mua hàng, kho…"
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              />
            </label>
            <label className="field">
              <span className="field__label">Nhiệm vụ</span>
              <input
                className="input"
                value={form.duty}
                placeholder="Đối chiếu công nợ, nhận hàng…"
                onChange={(e) => setForm((f) => ({ ...f, duty: e.target.value }))}
              />
            </label>
            <label className="field">
              <span className="field__label">Điện thoại</span>
              <input
                className="input"
                value={form.phone}
                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
              />
            </label>
            <label className="field">
              <span className="field__label">Email</span>
              <input
                className="input"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              />
            </label>
            <label className="field kh__checkfield">
              <input
                type="checkbox"
                checked={form.is_primary}
                onChange={(e) => setForm((f) => ({ ...f, is_primary: e.target.checked }))}
              />
              <span>Liên hệ chính (chỉ một người)</span>
            </label>
          </div>
          {formError && <div className="banner banner--error" role="alert">{formError}</div>}
          <div className="kh__dialog-actions">
            <Button variant="ghost" onClick={() => setEditingId(null)}>
              Huỷ
            </Button>
            <Button variant="primary" onClick={save} loading={busy}>
              Lưu
            </Button>
          </div>
        </div>
      )}

      {items.length === 0 && editingId == null ? (
        <div className="kh__empty-panel">
          <p className="kh__empty-title">Chưa có người liên hệ</p>
          <p className="kh__muted">
            Khách luôn có nhiều đầu mối (mua hàng, kho, kế toán, kỹ thuật…) — thêm để các bộ
            phận tự chủ liên hệ khi cần.
          </p>
        </div>
      ) : (
        items.length > 0 && (
          <table className="kh__table kh__table--tight">
            <thead>
              <tr>
                <th>Tên</th>
                <th>Chức vụ / nhiệm vụ</th>
                <th>Liên lạc</th>
                {canUpdate && <th className="kh__num">Thao tác</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id}>
                  <td>
                    <span className="kh__name">{c.name}</span>
                    {c.is_primary && <span className="kh__badge kh__badge--lead"> Chính</span>}
                  </td>
                  <td>
                    {c.title ?? "—"}
                    {c.duty && <span className="kh__muted"> · {c.duty}</span>}
                  </td>
                  <td className="kh__mono">
                    {[c.phone, c.email].filter(Boolean).join(" · ") || "—"}
                  </td>
                  {canUpdate && (
                    <td className="kh__num">
                      <button type="button" className="btn btn--ghost" onClick={() => startEdit(c)}>
                        Sửa
                      </button>
                      <button type="button" className="btn btn--ghost" onClick={() => remove(c.id)}>
                        Xóa
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}

// --- Giao hàng tab (#9: nhiều địa chỉ giao — chỗ nối phí giao hàng của Tính giá) --

interface AddressFormState {
  label: string;
  address: string;
  phone: string;
  note: string;
  is_default: boolean;
}
const EMPTY_ADDRESS: AddressFormState = {
  label: "",
  address: "",
  phone: "",
  note: "",
  is_default: false,
};

function AddressesTab({ customerId }: { customerId: number }) {
  const { token } = useAuth();
  const canUpdate = useCan()("khach_hang", "update");
  const [items, setItems] = useState<CustomerAddress[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<AddressFormState>(EMPTY_ADDRESS);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const reload = useCallback(() => {
    if (!token) return;
    api.customers
      .addresses(token, customerId)
      .then((r) => setItems(r.items))
      .catch(() => setError("Không tải được danh sách địa chỉ giao hàng."));
  }, [token, customerId]);

  useEffect(() => {
    setItems(null);
    setError(null);
    setEditingId(null);
    reload();
  }, [reload]);

  function startAdd() {
    setForm(EMPTY_ADDRESS);
    setFormError(null);
    setEditingId(-1);
  }
  function startEdit(a: CustomerAddress) {
    setForm({
      label: a.label,
      address: a.address,
      phone: a.phone ?? "",
      note: a.note ?? "",
      is_default: a.is_default,
    });
    setFormError(null);
    setEditingId(a.id);
  }

  async function save() {
    if (!token || busy) return;
    if (!form.label.trim() || !form.address.trim()) {
      setFormError("Tên điểm giao và địa chỉ là bắt buộc.");
      return;
    }
    setBusy(true);
    setFormError(null);
    const input: CustomerAddressInput = {
      label: form.label.trim(),
      address: form.address.trim(),
      phone: form.phone.trim() || null,
      note: form.note.trim() || null,
      is_default: form.is_default,
    };
    try {
      if (editingId === -1) await api.customers.addAddress(token, customerId, input);
      else if (editingId != null)
        await api.customers.updateAddress(token, customerId, editingId, input);
      setEditingId(null);
      reload();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Lưu không thành công.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    if (!token) return;
    try {
      await api.customers.deleteAddress(token, customerId, id);
      reload();
    } catch {
      setError("Xóa không thành công.");
    }
  }

  if (error) return <div className="banner banner--error" role="alert">{error}</div>;
  if (items == null) return <TableSkeleton cols={3} />;

  return (
    <div className="kh__histwrap">
      <div className="kh__hist-toolbar">
        <span className="kh__muted">
          {items.length} điểm giao · phí giao hàng theo điểm sẽ nối vào Tính giá sau
        </span>
        {canUpdate && editingId == null && (
          <Button variant="secondary" onClick={startAdd}>
            + Thêm điểm giao
          </Button>
        )}
      </div>

      {editingId != null && (
        <div className="card kh__subform">
          <div className="kh__form-grid">
            <label className="field">
              <span className="field__label">Tên điểm giao *</span>
              <input
                className="input"
                value={form.label}
                placeholder="Trụ sở / Nhà máy Bắc Ninh…"
                onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
                autoFocus
              />
            </label>
            <label className="field kh__form-wide">
              <span className="field__label">Địa chỉ *</span>
              <input
                className="input"
                value={form.address}
                onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
              />
            </label>
            <label className="field">
              <span className="field__label">SĐT tại điểm giao</span>
              <input
                className="input"
                value={form.phone}
                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
              />
            </label>
            <label className="field kh__form-wide">
              <span className="field__label">Ghi chú giao nhận</span>
              <input
                className="input"
                value={form.note}
                placeholder="Giờ nhận hàng, người nhận, yêu cầu xe…"
                onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
              />
            </label>
            <label className="field kh__checkfield">
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(e) => setForm((f) => ({ ...f, is_default: e.target.checked }))}
              />
              <span>Điểm giao mặc định</span>
            </label>
          </div>
          {formError && <div className="banner banner--error" role="alert">{formError}</div>}
          <div className="kh__dialog-actions">
            <Button variant="ghost" onClick={() => setEditingId(null)}>
              Huỷ
            </Button>
            <Button variant="primary" onClick={save} loading={busy}>
              Lưu
            </Button>
          </div>
        </div>
      )}

      {items.length === 0 && editingId == null ? (
        <div className="kh__empty-panel">
          <p className="kh__empty-title">Chưa có điểm giao hàng</p>
          <p className="kh__muted">
            Khách thường có nhiều vị trí giao (trụ sở, nhà máy…) — khai để báo giá ghi rõ
            giao ở đâu và sau này tính phí giao hàng theo điểm.
          </p>
        </div>
      ) : (
        items.length > 0 && (
          <table className="kh__table kh__table--tight">
            <thead>
              <tr>
                <th>Điểm giao</th>
                <th>Địa chỉ</th>
                <th>Ghi chú</th>
                {canUpdate && <th className="kh__num">Thao tác</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id}>
                  <td>
                    <span className="kh__name">{a.label}</span>
                    {a.is_default && <span className="kh__badge kh__badge--lead"> Mặc định</span>}
                    {a.phone && <div className="kh__muted kh__mono">{a.phone}</div>}
                  </td>
                  <td>{a.address}</td>
                  <td>{a.note ?? "—"}</td>
                  {canUpdate && (
                    <td className="kh__num">
                      <button type="button" className="btn btn--ghost" onClick={() => startEdit(a)}>
                        Sửa
                      </button>
                      <button type="button" className="btn btn--ghost" onClick={() => remove(a.id)}>
                        Xóa
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}

// --- Tài liệu tab (#21: hợp đồng / GPKD / file thiết kế đính kèm hồ sơ) ---------

const DOC_KIND_LABELS: Record<string, string> = {
  hop_dong: "Hợp đồng",
  gpkd: "GPKD",
  thiet_ke: "File thiết kế",
  khac: "Khác",
};

function AttachmentsTab({ customerId }: { customerId: number }) {
  const { token } = useAuth();
  const canUpdate = useCan()("khach_hang", "update");
  const [items, setItems] = useState<CustomerAttachment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [docKind, setDocKind] = useState("hop_dong");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(() => {
    if (!token) return;
    api.customers
      .attachments(token, customerId)
      .then((r) => setItems(r.items))
      .catch(() => setError("Không tải được danh sách tài liệu."));
  }, [token, customerId]);

  useEffect(() => {
    setItems(null);
    setError(null);
    reload();
  }, [reload]);

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!token || !file) return;
    setUploading(true);
    setError(null);
    try {
      await api.customers.uploadAttachment(token, customerId, file, docKind);
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload không thành công.");
    } finally {
      setUploading(false);
    }
  }

  async function remove(id: number) {
    if (!token) return;
    try {
      await api.customers.deleteAttachment(token, customerId, id);
      reload();
    } catch {
      setError("Xóa không thành công.");
    }
  }

  if (error && items == null)
    return <div className="banner banner--error" role="alert">{error}</div>;
  if (items == null) return <TableSkeleton cols={3} />;

  return (
    <div className="kh__histwrap">
      <div className="kh__hist-toolbar">
        <span className="kh__muted">{items.length} tài liệu</span>
        {canUpdate && (
          <div className="kh__upload-row">
            <Select
              ariaLabel="Loại tài liệu"
              value={docKind}
              onChange={(v) => setDocKind(v ?? "khac")}
              options={Object.entries(DOC_KIND_LABELS).map(([value, label]) => ({
                value,
                label,
              }))}
            />
            <input ref={fileRef} type="file" hidden onChange={onPick} />
            <Button
              variant="secondary"
              loading={uploading}
              onClick={() => fileRef.current?.click()}
            >
              ⬆ Tải tài liệu lên
            </Button>
          </div>
        )}
      </div>
      {error && <div className="banner banner--error" role="alert">{error}</div>}

      {items.length === 0 ? (
        <div className="kh__empty-panel">
          <p className="kh__empty-title">Chưa có tài liệu</p>
          <p className="kh__muted">
            Đính kèm hợp đồng, GPKD, file thiết kế, biên bản… để xử lý ngay khi cần, không
            phải đi tìm nơi khác.
          </p>
        </div>
      ) : (
        <table className="kh__table kh__table--tight">
          <thead>
            <tr>
              <th>Tài liệu</th>
              <th>Loại</th>
              <th>Ngày tải</th>
              {canUpdate && <th className="kh__num">Thao tác</th>}
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id}>
                <td>
                  <a className="kh__link" href={a.file_url} target="_blank" rel="noreferrer">
                    {a.file_name}
                  </a>
                </td>
                <td>{DOC_KIND_LABELS[a.doc_kind] ?? a.doc_kind}</td>
                <td className="kh__mono">{fmtDate(a.uploaded_at)}</td>
                {canUpdate && (
                  <td className="kh__num">
                    <button type="button" className="btn btn--ghost" onClick={() => remove(a.id)}>
                      Xóa
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// --- Import CSV dialog (#23: dry-run xem trước → xác nhận ghi) ------------------

function ImportDialog({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: () => void;
}) {
  const { token } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResultOut | null>(null);
  const [result, setResult] = useState<ImportResultOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function downloadTemplate() {
    if (!token) return;
    try {
      const url = await api.customers.importTemplateBlobUrl(token);
      const a = document.createElement("a");
      a.href = url;
      a.download = "mau-import-khach-hang.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch {
      setError("Không tải được file mẫu.");
    }
  }

  async function runDry(f: File) {
    if (!token) return;
    setBusy(true);
    setError(null);
    setPreview(null);
    try {
      setPreview(await api.customers.importCsv(token, f, true));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không đọc được file.");
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (!token || !file || busy) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.customers.importCsv(token, file, false));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Import không thành công.");
    } finally {
      setBusy(false);
    }
  }

  const shown = result ?? preview;

  return (
    <div className="kh__overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="kh__dialog card" role="dialog" aria-modal="true" aria-label="Nhập danh bạ từ CSV">
        <div className="kh__dialog-head">
          <h2>Nhập danh bạ khách hàng (CSV)</h2>
          <button type="button" className="kh__close" aria-label="Đóng" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="kh__dialog-body">
          {result == null && (
            <>
              <p className="kh__muted">
                File CSV UTF-8 theo{" "}
                <button type="button" className="kh__linkbtn" onClick={downloadTemplate}>
                  file mẫu
                </button>{" "}
                (Excel: Save As → CSV UTF-8). Hệ thống kiểm tra trước, bạn xem kết quả từng
                dòng rồi mới xác nhận ghi. Trùng MST/tên/email chỉ cảnh báo, không chặn.
              </p>
              <input
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null;
                  setFile(f);
                  setResult(null);
                  if (f) void runDry(f);
                }}
              />
            </>
          )}

          {error && <div className="banner banner--error" role="alert">{error}</div>}

          {shown && (
            <>
              <div className={`banner ${shown.errors > 0 ? "banner--warn" : "banner--success"}`} role="status">
                {result
                  ? `Đã nhập ${result.created} khách hàng (${result.warnings} cảnh báo trùng, ${result.errors} dòng lỗi bị bỏ qua).`
                  : `Xem trước: ${shown.total} dòng — ${shown.total - shown.errors} hợp lệ (${shown.warnings} trùng), ${shown.errors} lỗi.`}
              </div>
              {shown.rows.some((r) => r.status !== "created") && (
                <div className="kh__import-rows">
                  <table className="kh__table kh__table--tight">
                    <thead>
                      <tr>
                        <th>Dòng</th>
                        <th>Khách hàng</th>
                        <th>Kết quả</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shown.rows
                        .filter((r) => r.status !== "created")
                        .map((r) => (
                          <tr key={r.row}>
                            <td className="kh__mono">{r.row}</td>
                            <td>{r.name ?? "—"}</td>
                            <td>
                              <span
                                className={`kh__badge${r.status === "error" ? " kh__badge--off" : " kh__badge--lead"}`}
                              >
                                {r.status === "error" ? "Lỗi" : "Trùng"}
                              </span>{" "}
                              {r.message}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          <div className="kh__dialog-actions">
            {result ? (
              <Button variant="primary" onClick={onImported}>
                Xong
              </Button>
            ) : (
              <>
                <Button variant="ghost" onClick={onClose}>
                  Huỷ
                </Button>
                <Button
                  variant="primary"
                  onClick={commit}
                  loading={busy}
                  disabled={!file || !preview || preview.total === preview.errors}
                >
                  Nhập {preview ? preview.total - preview.errors : ""} dòng hợp lệ
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function TableSkeleton({ cols }: { cols: number }) {
  return (
    <table className="kh__table kh__table--tight">
      <tbody>
        {[...Array(4)].map((_, i) => (
          <tr key={i} className="kh__skelrow">
            {[...Array(cols)].map((__, j) => (
              <td key={j}>
                <span className="kh__skel" />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// =============================================================================
// Create / edit dialog (chọn NV từ picker, validation, MST soft-dup warn)
// =============================================================================

function CustomerFormDialog({
  title,
  code,
  customerId,
  isEdit,
  initial,
  sales,
  onClose,
  onSaved,
}: {
  title: string;
  code?: string;
  customerId?: number;
  isEdit: boolean;
  initial: FormState;
  sales: SaleOption[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  // Đổi NV phụ trách của KH ĐANG CÓ = quyền chi tiết `reassign` (backend cũng chặn) —
  // thiếu quyền thì khóa picker khi Sửa; khi Tạo mới vẫn chọn được (gán lần đầu).
  const can = useCan();
  const canReassign = can("khach_hang", "reassign");
  // Chiết khấu riêng (#14): thiếu quyền `view_discount` → ẩn hẳn khối (backend cũng bỏ qua).
  const canDiscount = can("khach_hang", "view_discount");
  const saleLocked = isEdit && !canReassign;
  const [form, setForm] = useState<FormState>(initial);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  // Cảnh báo trùng MỀM sau khi lưu (#15: MST + tên cty + email — không chặn).
  const [savedWarns, setSavedWarns] = useState<DuplicateWarn[] | null>(null);
  // Check trùng tức thời khi rời ô nhập (#8) — chỉ là gợi ý, không chặn Lưu.
  const [liveWarns, setLiveWarns] = useState<DuplicateWarn[]>([]);

  async function liveCheck() {
    if (!token) return;
    const tax = form.tax_code.trim();
    const name = form.name.trim();
    const email = form.email.trim();
    if (!tax && !name && !email) {
      setLiveWarns([]);
      return;
    }
    try {
      const warns = await api.customers.checkDuplicate(token, {
        tax_code: tax || undefined,
        name: name || undefined,
        email: email || undefined,
        exclude_id: customerId,
      });
      setLiveWarns(warns);
    } catch {
      setLiveWarns([]); // gợi ý thôi — lỗi mạng thì im lặng
    }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  function set<K extends keyof FormState>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => ({ ...e, [key]: undefined }));
    setServerError(null);
  }

  function validate(): boolean {
    const next: Partial<Record<keyof FormState, string>> = {};
    if (!form.name.trim()) next.name = "Tên khách hàng là bắt buộc.";
    if (form.tax_code.trim() && !MST_RE.test(form.tax_code.trim()))
      next.tax_code = "MST phải gồm 10 hoặc 13 chữ số.";
    const limit = Number(form.credit_limit);
    if (form.credit_limit.trim() === "" || Number.isNaN(limit) || limit < 0)
      next.credit_limit = "Hạn mức phải là số ≥ 0.";
    // Điều khoản thanh toán (#12): validate theo kiểu mốc.
    const term = form.payment_term_type;
    if (term === "prepay") {
      const p = Number(form.prepay_pct);
      if (form.prepay_pct.trim() === "" || Number.isNaN(p) || p < 0 || p > 100)
        next.prepay_pct = "Nhập tỷ lệ trả trước 0–100%.";
    }
    if (term === "net_delivery" || term === "net_eom") {
      const d = Number(form.payment_term_days);
      if (form.payment_term_days.trim() === "" || !Number.isInteger(d) || d < 0)
        next.payment_term_days = "Nhập số ngày công nợ (số nguyên ≥ 0).";
    }
    for (const key of ["discount_trade_pct", "discount_buyer_pct"] as const) {
      if (form[key].trim() !== "") {
        const v = Number(form[key]);
        if (Number.isNaN(v) || v < 0 || v > 100) next[key] = "Chiết khấu phải trong 0–100%.";
      }
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    if (!validate()) return;
    setSaving(true);
    setServerError(null);
    const term = form.payment_term_type;
    const input: CustomerInput = {
      name: form.name.trim(),
      tax_code: form.tax_code.trim() || null,
      phone: form.phone.trim() || null,
      email: form.email.trim() || null,
      address: form.address.trim() || null,
      contact_name: form.contact_name.trim() || null,
      credit_limit: Number(form.credit_limit),
      sale_user_id: form.sale_user_id ? Number(form.sale_user_id) : null,
      status: form.status,
      payment_term_type: term || null,
      payment_term_days:
        term === "net_delivery" || term === "net_eom" ? Number(form.payment_term_days) : null,
      prepay_pct: term === "prepay" ? Number(form.prepay_pct) : null,
      payment_term_note: form.payment_term_note.trim() || null,
      // Backend: khi Sửa, null = giữ nguyên CK (xóa CK → gửi 0); thiếu quyền thì bị bỏ qua.
      discount_trade_pct:
        canDiscount && form.discount_trade_pct.trim() !== ""
          ? Number(form.discount_trade_pct)
          : null,
      discount_buyer_pct:
        canDiscount && form.discount_buyer_pct.trim() !== ""
          ? Number(form.discount_buyer_pct)
          : null,
    };
    try {
      const res =
        isEdit && customerId != null
          ? await api.customers.update(token, customerId, input)
          : await api.customers.create(token, input);
      if (res.duplicates.length > 0) {
        setSavedWarns(res.duplicates);
        setSaving(false);
        return;
      }
      onSaved();
    } catch (err) {
      if (err instanceof ApiError && err.isForbidden)
        setServerError("Bạn không có quyền thực hiện thao tác này.");
      else if (err instanceof ApiError && err.status === 422) setServerError(err.message);
      else setServerError("Lưu không thành công. Vui lòng thử lại.");
      setSaving(false);
    }
  }

  return (
    <div className="kh__overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="kh__dialog card" role="dialog" aria-modal="true" aria-label={title}>
        <div className="kh__dialog-head">
          <h2>{title}</h2>
          <button type="button" className="kh__close" aria-label="Đóng" onClick={onClose}>
            ✕
          </button>
        </div>

        {savedWarns ? (
          <div className="kh__dialog-body">
            <div className="banner banner--warn" role="alert">
              <div>
                <p>Đã lưu. Lưu ý trùng thông tin (cảnh báo mềm, không chặn):</p>
                <ul className="kh__dup-list">
                  {savedWarns.map((w) => (
                    <li key={`${w.field}-${w.id}`}>
                      Trùng <strong>{DUP_FIELD_LABELS[w.field]}</strong> với khách{" "}
                      <strong>
                        {w.code} · {w.name}
                      </strong>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            <div className="kh__dialog-actions">
              <Button variant="primary" onClick={onSaved}>
                Đã hiểu, tiếp tục
              </Button>
            </div>
          </div>
        ) : (
          <form className="kh__dialog-body" onSubmit={onSubmit}>
            <div className="kh__form-grid">
              <label className="field">
                <span className="field__label">Mã KH</span>
                <input className="input" value={code ?? "(tự sinh)"} readOnly disabled />
              </label>
              <label className="field">
                <span className="field__label">Tên khách hàng *</span>
                <input
                  className="input"
                  value={form.name}
                  onChange={(e) => set("name", e.target.value)}
                  onBlur={liveCheck}
                  aria-invalid={!!errors.name}
                  autoFocus
                />
                {errors.name && <span className="kh__err" role="alert">{errors.name}</span>}
              </label>
              <label className="field">
                <span className="field__label">MST</span>
                <input
                  className="input"
                  value={form.tax_code}
                  onChange={(e) => set("tax_code", e.target.value)}
                  onBlur={liveCheck}
                  placeholder="10 hoặc 13 chữ số"
                  aria-invalid={!!errors.tax_code}
                />
                {errors.tax_code && <span className="kh__err" role="alert">{errors.tax_code}</span>}
              </label>
              <label className="field">
                <span className="field__label">Điện thoại</span>
                <input className="input" value={form.phone} onChange={(e) => set("phone", e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Email</span>
                <input
                  className="input"
                  value={form.email}
                  onChange={(e) => set("email", e.target.value)}
                  onBlur={liveCheck}
                />
              </label>
              <label className="field">
                <span className="field__label">Người liên hệ</span>
                <input
                  className="input"
                  value={form.contact_name}
                  onChange={(e) => set("contact_name", e.target.value)}
                />
              </label>
              <label className="field kh__form-wide">
                <span className="field__label">Địa chỉ</span>
                <input className="input" value={form.address} onChange={(e) => set("address", e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Hạn mức tín dụng (VND)</span>
                <input
                  className="input"
                  type="number"
                  min={0}
                  value={form.credit_limit}
                  onChange={(e) => set("credit_limit", e.target.value)}
                  aria-invalid={!!errors.credit_limit}
                />
                {errors.credit_limit && <span className="kh__err" role="alert">{errors.credit_limit}</span>}
              </label>
              <label className="field">
                <span className="field__label">NV phụ trách</span>
                <select
                  className="input"
                  value={form.sale_user_id}
                  disabled={saleLocked}
                  onChange={(e) => set("sale_user_id", e.target.value)}
                >
                  <option value="">— Mặc định (tôi) —</option>
                  {sales.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
                {saleLocked && (
                  <span className="kh__muted">
                    Cần quyền “Điều chuyển” để đổi người phụ trách.
                  </span>
                )}
              </label>
              <label className="field">
                <span className="field__label">Trạng thái</span>
                <select
                  className="input"
                  value={form.status}
                  onChange={(e) => set("status", e.target.value)}
                >
                  <option value="lead">Tiềm năng (chào hàng)</option>
                  <option value="active">Đang giao dịch</option>
                  {isEdit && <option value="inactive">Ngừng giao dịch</option>}
                </select>
              </label>

              {/* Điều khoản thanh toán riêng (#12) — dữ liệu chờ Công nợ. */}
              <label className="field kh__form-wide">
                <span className="field__label">Điều khoản thanh toán</span>
                <select
                  className="input"
                  value={form.payment_term_type}
                  onChange={(e) => set("payment_term_type", e.target.value)}
                >
                  <option value="">— Chưa khai —</option>
                  {Object.entries(PAYMENT_TERM_LABELS).map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              {(form.payment_term_type === "net_delivery" ||
                form.payment_term_type === "net_eom") && (
                <label className="field">
                  <span className="field__label">Số ngày công nợ *</span>
                  <input
                    className="input"
                    type="number"
                    min={0}
                    value={form.payment_term_days}
                    onChange={(e) => set("payment_term_days", e.target.value)}
                    aria-invalid={!!errors.payment_term_days}
                  />
                  {errors.payment_term_days && (
                    <span className="kh__err" role="alert">{errors.payment_term_days}</span>
                  )}
                </label>
              )}
              {form.payment_term_type === "prepay" && (
                <label className="field">
                  <span className="field__label">Tỷ lệ trả trước (%) *</span>
                  <input
                    className="input"
                    type="number"
                    min={0}
                    max={100}
                    value={form.prepay_pct}
                    onChange={(e) => set("prepay_pct", e.target.value)}
                    aria-invalid={!!errors.prepay_pct}
                  />
                  {errors.prepay_pct && (
                    <span className="kh__err" role="alert">{errors.prepay_pct}</span>
                  )}
                </label>
              )}
              {form.payment_term_type && (
                <label className="field kh__form-wide">
                  <span className="field__label">
                    Ghi chú điều khoản{form.payment_term_type === "custom" ? " *" : ""}
                  </span>
                  <input
                    className="input"
                    value={form.payment_term_note}
                    onChange={(e) => set("payment_term_note", e.target.value)}
                    placeholder="VD: 30 ngày từ ngày đối chiếu, cọc 50% khi đặt…"
                  />
                </label>
              )}

              {/* Chiết khấu riêng theo KH (#14) — chỉ người có quyền `view_discount`. */}
              {canDiscount && (
                <>
                  <label className="field">
                    <span className="field__label">CK thương mại (%)</span>
                    <input
                      className="input"
                      type="number"
                      min={0}
                      max={100}
                      step="0.1"
                      value={form.discount_trade_pct}
                      onChange={(e) => set("discount_trade_pct", e.target.value)}
                      aria-invalid={!!errors.discount_trade_pct}
                      placeholder="Mặc định điền vào báo giá"
                    />
                    {errors.discount_trade_pct && (
                      <span className="kh__err" role="alert">{errors.discount_trade_pct}</span>
                    )}
                  </label>
                  <label className="field">
                    <span className="field__label">CK người mua hàng (%)</span>
                    <input
                      className="input"
                      type="number"
                      min={0}
                      max={100}
                      step="0.1"
                      value={form.discount_buyer_pct}
                      onChange={(e) => set("discount_buyer_pct", e.target.value)}
                      aria-invalid={!!errors.discount_buyer_pct}
                      placeholder="Dữ liệu nhạy cảm — chỉ người có quyền thấy"
                    />
                    {errors.discount_buyer_pct && (
                      <span className="kh__err" role="alert">{errors.discount_buyer_pct}</span>
                    )}
                  </label>
                </>
              )}
            </div>

            {liveWarns.length > 0 && (
              <div className="banner banner--warn" role="status">
                <div>
                  <p>Có thể trùng khách đã có (không chặn lưu):</p>
                  <ul className="kh__dup-list">
                    {liveWarns.map((w) => (
                      <li key={`${w.field}-${w.id}`}>
                        Trùng <strong>{DUP_FIELD_LABELS[w.field]}</strong> với{" "}
                        <strong>
                          {w.code} · {w.name}
                        </strong>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {serverError && (
              <div className="banner banner--error" role="alert">
                {serverError}
              </div>
            )}

            <div className="kh__dialog-actions">
              <Button type="button" variant="ghost" onClick={onClose}>
                Huỷ
              </Button>
              <Button type="submit" variant="primary" loading={saving}>
                Lưu
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
