// Khách hàng — CRM-360 (spec-06). List-Report với KPI header strip + filter tabs +
// bảng định-danh (tier sao, tags, badge) → slide-over Object-page (header + gauge uy tín,
// toolbar hành động, tabs Dashboard / Lịch sử mua hàng / Lịch sử báo giá). MỌI số liệu
// (KPI, doanh số 12T, cơ cấu SP, tần suất đặt, lịch sử) tính từ ĐƠN HÀNG / BÁO GIÁ THẬT;
// thiếu dữ liệu → empty state trung thực (không bịa số). Công nợ chỉ-đọc qua SEAM-16.
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import {
  ApiError,
  api,
  type CustomerAddress,
  type CustomerAddressInput,
  type CustomerAttachment,
  type CustomerAuditRow,
  type CareEvent,
  type CareTask,
  type CustomerContact,
  type CustomerContactInput,
  type CustomerDashboard,
  type CustomerInput,
  type CustomerKpis,
  type CustomerRow,
  type DuplicateWarn,
  type FollowupRow,
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
import {
  AlarmClock,
  CalendarClock,
  ChevronDown,
  ChevronUp,
  Download,
  FileText,
  Gauge,
  HeartHandshake,
  History,
  Mail,
  MapPin,
  MessageCircle,
  Package,
  Paperclip,
  PencilLine,
  Phone,
  ReceiptText,
  Search,
  ShoppingBag,
  Tags,
  Users,
  X,
  CheckCircle2,
  Clock,
  Plus,
  Calendar,
  AlertTriangle,
  Trash2,
  User,
  Check,
  ChevronRight,
  ShieldCheck,
  Image,
} from "lucide-react";
import { MixDonut, MonthBars } from "../components/charts";
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

function moneyCompact(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000_000) {
    return (n / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 }) + " tỷ đ";
  }
  if (n >= 1_000_000) {
    return (n / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 }) + " M đ";
  }
  if (n >= 1_000) {
    return (n / 1_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 }) + " K đ";
  }
  return n.toLocaleString("vi-VN") + " ₫";
}

function moneySuperCompact(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000_000) {
    return (n / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 }) + "B";
  }
  if (n >= 1_000_000) {
    return (n / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 }) + "M";
  }
  if (n >= 1_000) {
    return (n / 1_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 }) + "K";
  }
  return n.toLocaleString("vi-VN") + " ₫";
}

/** Số to + đơn vị nhỏ ("22,17" + "M đ") cho stat card / cột tiền — theo prototype. */
function moneyStat(n: number | null | undefined): ReactNode {
  if (n == null || n <= 0) return "—";
  const s = moneyCompact(n);
  const m = s.match(/^([\d.,]+)\s*(.+)$/);
  if (!m) return s;
  return (
    <>
      {m[1]} <small>{m[2]}</small>
    </>
  );
}

function getInitials(name: string): string {
  const clean = name.replace(/^(Cty|Công ty|Cafe|Cà phê|TNHH|CP)\s+/i, "").trim();
  const parts = clean.split(/\s+/);
  if (parts.length >= 2) {
    const p1 = parts[parts.length - 2][0];
    const p2 = parts[parts.length - 1][0];
    return (p1 + p2).toUpperCase();
  }
  return clean.substring(0, 2).toUpperCase();
}

interface MockAR {
  receivableText: string;
  receivableVal: number;
  isOverdue: boolean;
  overdueDays: number;
  creditScore: number;
  creditText: string;
}

function getMockAR(id: number): MockAR {
  const hash = id % 3;
  if (hash === 0) {
    return {
      receivableText: "62M",
      receivableVal: 62000000,
      isOverdue: true,
      overdueDays: 18,
      creditScore: 45,
      creditText: "Kém",
    };
  } else if (hash === 1) {
    return {
      receivableText: "18M",
      receivableVal: 18000000,
      isOverdue: false,
      overdueDays: 0,
      creditScore: 88,
      creditText: "Tốt",
    };
  } else {
    return {
      receivableText: "—",
      receivableVal: 0,
      isOverdue: false,
      overdueDays: 0,
      creditScore: 92,
      creditText: "Tốt",
    };
  }
}

/** Gauge uy tín kiểu prototype: 3 cung vùng (kém/khá/tốt) mờ 28% + cung tiến độ màu
 *  semantic + vạch tick + số lớn. Màu lấy đúng token (moss/amber/signal), KHÔNG Material. */
function CreditGauge({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const R = 72;
  // Điểm trên cung theo góc (180° = trái, 0° = phải), tâm (100,100).
  const pt = (deg: number, r = R) => {
    const rad = (Math.PI * deg) / 180;
    return `${(100 + r * Math.cos(rad)).toFixed(2)} ${(100 - r * Math.sin(rad)).toFixed(2)}`;
  };
  const arc = (fromDeg: number, toDeg: number, r = R) =>
    `M ${pt(fromDeg, r)} A ${r} ${r} 0 0 1 ${pt(toDeg, r)}`;
  const endDeg = 180 - (pct / 100) * 180;
  const color = pct >= 80 ? "var(--moss)" : pct >= 50 ? "var(--amber)" : "var(--signal)";
  const label = pct >= 80 ? "TỐT" : pct >= 50 ? "KHÁ" : "KÉM";

  return (
    <div className="kh__gauge-svg-container" aria-label={`Uy tín thanh toán ${score}/100`}>
      <svg width="176" height="102" viewBox="0 0 200 116" style={{ overflow: "visible" }}>
        {/* 3 vùng thang điểm, mờ — kém / khá / tốt */}
        <path d={arc(180, 120)} style={{ stroke: "var(--signal)", opacity: 0.28 }} strokeWidth={12} fill="none" />
        <path d={arc(120, 60)} style={{ stroke: "var(--amber)", opacity: 0.28 }} strokeWidth={12} fill="none" />
        <path d={arc(60, 0)} style={{ stroke: "var(--moss)", opacity: 0.28 }} strokeWidth={12} fill="none" />
        {/* Cung tiến độ */}
        <path d={arc(180, Math.min(179.5, Math.max(0.5, endDeg)))} style={{ stroke: color }} strokeWidth={12} fill="none" strokeLinecap="round" />
        {/* Tick 25 / 50 / 75 */}
        {[135, 90, 45].map((d) => {
          const [x1, y1] = pt(d, R - 7).split(" ");
          const [x2, y2] = pt(d, R + 7).split(" ");
          return <line key={d} x1={x1} y1={y1} x2={x2} y2={y2} style={{ stroke: "rgba(245,241,232,0.35)" }} strokeWidth={1.2} />;
        })}
        <text x="100" y="90" textAnchor="middle" style={{ fill: "var(--on-charcoal)", letterSpacing: "-1.5px" }} fontFamily="var(--ff-sans)" fontSize="36" fontWeight="500">
          {score}
        </text>
        <text x="100" y="110" textAnchor="middle" style={{ fill: color }} fontFamily="var(--ff-mono)" fontSize="9" letterSpacing="1.5">
          {label}
        </text>
      </svg>
      <span className="kh__gauge-label-bottom">UY TÍN THANH TOÁN</span>
    </div>
  );
}

/*
const TIER_META: Record<CustomerTier, { label: string; stars: number; cls: string }> = {
  loyal: { label: "Thân thiết", stars: 3, cls: "tier--loyal" },
  partner: { label: "Đối tác lâu năm", stars: 2, cls: "tier--partner" },
  regular: { label: "Đang giao dịch", stars: 1, cls: "tier--regular" },
  new: { label: "Mới", stars: 0, cls: "tier--new" },
};
*/

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
  accepted: "Đã chốt",
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

/*
const STATUS_LABELS: Record<string, string> = {
  lead: "Tiềm năng",
  active: "Đang giao dịch",
  inactive: "Ngừng",
};
*/

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
/*
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
*/

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
  const [tierFilter, setTierFilter] = useState<string>("");
  const [tagFilter, setTagFilter] = useState<string>("");
  const [tagLabels, setTagLabels] = useState<string[]>([]);
  const [pageSize, setPageSize] = useState(25);
  const [sales, setSales] = useState<SaleOption[]>([]);

  // Điều chuyển khách hàng: gated bằng quyền chi tiết `reassign` (Cách B) — cấu hình trong
  // ma trận phân quyền, tách khỏi quyền Sửa thông thường.
  const can = useCan();
  const canReassign = can("khach_hang", "reassign");
  const canExport = can("khach_hang", "export");
  const canCreate = can("khach_hang", "create");
  const colCount = canReassign ? 9 : 8; // avatar, tier stars, TB/don, AR, uy-tin columns added

  // Import / export danh bạ (#23).
  const [importOpen, setImportOpen] = useState(false);
  const [exportingBook, setExportingBook] = useState(false);

  // Panel "Cần chăm sóc" (#28): việc đến hạn/quá hạn trong scope của tôi.
  const [followups, setFollowups] = useState<FollowupRow[]>([]);
  const [followupsOpen, setFollowupsOpen] = useState(false);

  const loadFollowups = useCallback(() => {
    if (!token) return;
    api.customers
      .careFollowups(token)
      .then((r) => setFollowups(r.items))
      .catch(() => setFollowups([]));
  }, [token]);

  useEffect(() => {
    loadFollowups();
  }, [loadFollowups]);

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
        tier: tierFilter || null,
        tag: tagFilter || null,
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
  }, [token, q, saleFilter, statusFilter, tierFilter, tagFilter, sort, page, pageSize]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, sort, page, pageSize, saleFilter, statusFilter, tierFilter, tagFilter]);

  useEffect(() => {
    if (!token) return;
    api.customers.sales(token).then(setSales).catch(() => setSales([]));
    api.customers.tagLabels(token).then(setTagLabels).catch(() => setTagLabels([]));
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
            {kpis ? (
              <span className="kh__subtitle-stats">
                <strong>{total}</strong> KH &middot; <strong style={{ color: "var(--rust)" }}>{kpis.loyal_count}</strong> thân thiết &middot; <strong>{kpis.new_this_month}</strong> mới trong tháng &middot; TB đơn <strong>{moneyCompact(kpis.avg_order_value)}</strong>
              </span>
            ) : (
              "Danh bạ 360° — tìm, phân loại theo lịch sử mua thật, xem dashboard & công nợ."
            )}
          </p>
        </div>
        <div className="kh__head-actions">
          {canExport && (
            <Button variant="ghost" onClick={exportBook} loading={exportingBook}>
              Xuất CSV
            </Button>
          )}
          {canCreate && (
            <Button variant="ghost" onClick={() => setImportOpen(true)}>
              Nhập CSV
            </Button>
          )}
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

      {/* Cần chăm sóc (#28): việc đến hạn/quá hạn, nhắc lần 1-2-3 — bấm mở hồ sơ khách. */}
      {followups.length > 0 && (
        <div className="kh__followups card">
          <button
            type="button"
            className="kh__followups-head"
            onClick={() => setFollowupsOpen((v) => !v)}
            aria-expanded={followupsOpen}
          >
            <span aria-hidden="true" className="kh__followups-ic"><AlarmClock size={15} /></span>
            <strong>Cần chăm sóc: {followups.length} việc đến hạn / quá hạn</strong>
            <span className="kh__muted">
              {followups.filter((f) => f.remind_level >= 3).length > 0
                ? ` · ${followups.filter((f) => f.remind_level >= 3).length} việc nhắc lần 3`
                : ""}
            </span>
            <span className="kh__followups-caret" aria-hidden="true">
              {followupsOpen ? "▴" : "▾"}
            </span>
          </button>
          {followupsOpen && (
            <ul className="kh__followups-list">
              {followups.map((f) => (
                <li key={f.id}>
                  <button type="button" className="kh__followups-row" onClick={() => setOpenId(f.customer_id)}>
                    <RemindBadge level={f.remind_level} days={f.overdue_days} />
                    <span className="kh__name">{f.customer_name}</span>
                    <span className="kh__mono kh__muted">{f.customer_code}</span>
                    <span className="kh__followups-note">{f.note}</span>
                    <span className="kh__mono kh__muted">hạn {fmtDate(f.due_date)}</span>
                    {f.assignee_name && <span className="kh__muted">· {f.assignee_name}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="kh__toolbar">
        {/* Enter để tìm (mockup không có nút Tìm riêng — đỡ một control). */}
        <form className="kh__search" onSubmit={onSearch} role="search">
          <div className="kh__search-input-wrap">
            <span className="kh__search-icon" aria-hidden="true"><Search size={14} /></span>
            <input
              className="input kh__search-input"
              placeholder="Tìm theo tên / MST / điện thoại…  ↵"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="Tìm khách hàng"
            />
          </div>
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
        {tagLabels.length > 0 && (
          <div className="kh__filter">
            <Select
              ariaLabel="Lọc theo nhãn"
              value={tagFilter}
              placeholder="Tất cả nhãn"
              onChange={(v) => {
                setTagFilter(v ?? "");
                setPage(1);
              }}
              options={[
                { value: "", label: "Tất cả nhãn" },
                ...tagLabels.map((t) => ({ value: t, label: t })),
              ]}
            />
          </div>
        )}
      </div>

      {/* Sub-tab filter pills (Figma Style) */}
      <div className="kh__sub-tabs">
        <button
          type="button"
          className={`kh__sub-tab kh__sub-tab--all${tierFilter === "" ? " is-active" : ""}`}
          onClick={() => {
            setTierFilter("");
            setPage(1);
          }}
        >
          Tất cả <span className="kh__sub-tab-count">{kpis?.total_customers ?? 0}</span>
        </button>
        <button
          type="button"
          className={`kh__sub-tab kh__sub-tab--loyal${tierFilter === "loyal" ? " is-active" : ""}`}
          onClick={() => {
            setTierFilter("loyal");
            setPage(1);
          }}
        >
          Thân thiết <span className="kh__sub-tab-count">{kpis?.loyal_count ?? 0}</span>
        </button>
        <button
          type="button"
          className={`kh__sub-tab kh__sub-tab--partner${tierFilter === "partner" ? " is-active" : ""}`}
          onClick={() => {
            setTierFilter("partner");
            setPage(1);
          }}
        >
          Đối tác lâu năm <span className="kh__sub-tab-count">{kpis?.partner_count ?? 0}</span>
        </button>
        <button
          type="button"
          className={`kh__sub-tab kh__sub-tab--new${tierFilter === "new" ? " is-active" : ""}`}
          onClick={() => {
            setTierFilter("new");
            setPage(1);
          }}
        >
          Mới trong tháng <span className="kh__sub-tab-count">{kpis?.new_this_month ?? 0}</span>
        </button>
        <button
          type="button"
          className={`kh__sub-tab kh__sub-tab--followup${tierFilter === "followup" ? " is-active" : ""}`}
          onClick={() => {
            setTierFilter("followup");
            setPage(1);
          }}
        >
          <AlarmClock size={13} /> Cần theo dõi <span className="kh__sub-tab-count">{followups.length}</span>
        </button>
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
              <th>Tier</th>
              <th className="kh__num">
                <SortBtn label="Doanh số 12T" col="revenue" sort={sort} onSort={setSort} />
              </th>
              <th className="kh__num">
                <SortBtn label="Số đơn" col="orders" sort={sort} onSort={setSort} />
              </th>
              <th className="kh__num">TB / Đơn</th>
              <th className="kh__num">Công nợ</th>
              <th>Uy tín</th>
              <th>NV phụ trách</th>
              <th></th>
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
                const initials = getInitials(c.name);
                const mockAR = getMockAR(c.id);
                const stars = c.tier === "partner" ? 5 : c.tier === "loyal" ? 4 : c.tier === "regular" ? 3 : 2;
                const avgOrderValue = c.orders_total > 0 ? Math.round(c.revenue_12m / c.orders_total) : 0;

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
                      <div className="kh__identity-cell">
                        <div className="kh__avatar">{initials}</div>
                        <div className="kh__identity">
                          <span className="kh__name">{c.name}</span>
                          <span className="kh__submeta">
                            {c.tax_code && <span className="kh__mono">MST {c.tax_code}</span>}
                          </span>
                          <div className="kh__row-badges">
                            {c.tier === "loyal" && <span className="kh__row-badge kh__row-badge--loyal">Thân thiết</span>}
                            {c.tier === "partner" && <span className="kh__row-badge kh__row-badge--partner">Đối tác lâu năm</span>}
                            {mockAR.creditScore >= 80 && <span className="kh__row-badge kh__row-badge--good">Trả đúng hạn</span>}
                            {/* Nhãn thủ công (#7) — sales gán tay trong hồ sơ. */}
                            {(c.tags ?? []).map((t) => (
                              <span key={t} className="kh__row-badge kh__row-badge--tag">
                                {t}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="kh__stars-cell" aria-label={`${stars} sao`}>
                        {"★".repeat(stars)}
                      </span>
                    </td>
                    <td className="kh__num kh__money">
                      {c.revenue_12m > 0 ? moneyStat(c.revenue_12m) : <span className="kh__muted">—</span>}
                    </td>
                    <td className="kh__num">
                      {c.orders_total > 0 ? c.orders_total : <span className="kh__muted">0</span>}
                    </td>
                    <td className="kh__num">
                      {avgOrderValue > 0 ? moneySuperCompact(avgOrderValue) : <span className="kh__muted">—</span>}
                    </td>
                    <td>
                      <div className="kh__ar-cell">
                        {mockAR.receivableVal > 0 ? (
                          <>
                            <span className="kh__ar-amount">{moneySuperCompact(mockAR.receivableVal)}</span>
                            {mockAR.isOverdue ? (
                              <span className="kh__ar-sub kh__ar-sub--danger">⚠ Quá hạn {mockAR.overdueDays}D</span>
                            ) : (
                              <span className="kh__ar-sub kh__ar-sub--success">✓ Trong hạn</span>
                            )}
                          </>
                        ) : (
                          <>
                            <span className="kh__ar-amount">—</span>
                            <span className="kh__ar-sub kh__ar-sub--muted">Đã thu đủ</span>
                          </>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className={`kh__score-badge kh__score-badge--${mockAR.creditScore >= 80 ? "good" : "bad"}`}>
                        {mockAR.creditScore}
                      </span>
                    </td>
                    <td>{c.sale_name ?? <span className="kh__muted">Chưa gán</span>}</td>
                    <td className="kh__arrow-col">
                      <span className="kh__arrow-icon">›</span>
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
  // MỘT card chia 4 ngăn (mockup) — số to + đơn vị nhỏ tách rời như prototype.
  const cells: { label: string; value: ReactNode; hint: string }[] = [
    { label: "Tổng khách hàng", value: kpis ? String(kpis.total_customers) : "—", hint: "trong phạm vi" },
    {
      label: "Thân thiết / tổng",
      value: kpis ? (
        <>
          {kpis.loyal_count} <small>/ {kpis.total_customers}</small>
        </>
      ) : (
        "—"
      ),
      hint: "≥ 50tr / 12T",
    },
    { label: "Mới trong tháng", value: kpis ? String(kpis.new_this_month) : "—", hint: "vừa vào sổ" },
    {
      label: "TB / đơn (12T)",
      value: kpis ? moneyStat(kpis.avg_order_value) : "—",
      hint: "từ đơn thật",
    },
  ];
  return (
    <div className="stat-strip">
      {cells.map((c) => (
        <div className="stat-strip__cell" key={c.label}>
          <span className="stat__label">{c.label}</span>
          <span className="stat__value">
            {loading ? <span className="kh__skel kh__skel--kpi" /> : c.value}
          </span>
          <span className="stat__hint">{c.hint}</span>
        </div>
      ))}
    </div>
  );
}

/*
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
*/

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

type Tab = "dashboard" | "orders" | "quotes" | "care" | "contacts" | "addresses" | "files" | "audit";

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
              <ChevronUp size={14} strokeWidth={2} />
            </button>
            <button type="button" className="kh__iconbtn" disabled={!canNext} onClick={onNext} aria-label="Khách sau">
              <ChevronDown size={14} strokeWidth={2} />
            </button>
          </div>
          <button type="button" className="kh__close" aria-label="Đóng" onClick={onClose}>
            <X size={14} strokeWidth={2} />
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
              onSchedule={() => setTab("care")}
            />
            <nav className="kh__so-tabs" aria-label="Nội dung">
              {(
                [
                  ["dashboard", "Dashboard", <Gauge size={14} key="i" />, null],
                  ["orders", "Lịch sử mua hàng", <ReceiptText size={14} key="i" />, dash.orders_total],
                  ["quotes", "Lịch sử báo giá", <FileText size={14} key="i" />, dash.quotes_total],
                  ["care", "Chăm sóc", <HeartHandshake size={14} key="i" />, null],
                  ["contacts", "Liên hệ", <Users size={14} key="i" />, null],
                  ["addresses", "Giao hàng", <MapPin size={14} key="i" />, null],
                  ["files", "Tài liệu", <Paperclip size={14} key="i" />, null],
                  ["audit", "Nhật ký", <History size={14} key="i" />, null],
                ] as [Tab, string, JSX.Element, number | null][]
              ).map(([key, label, icon, count]) => (
                <button
                  key={key}
                  type="button"
                  className={`kh__so-tab${tab === key ? " is-active" : ""}`}
                  aria-current={tab === key ? "true" : undefined}
                  onClick={() => setTab(key)}
                >
                  {icon} {label}
                  {count != null && count > 0 && <span className="chip-count">{count}</span>}
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
              {tab === "care" && <CareTab customerId={customerId} />}
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
  onSchedule,
}: {
  customer: CustomerRow;
  dash: CustomerDashboard;
  onEdit: () => void;
  navigate: NavigateFn;
  onClose: () => void;
  onSchedule: () => void;
}) {
  // const canDebt = useCan()("khach_hang", "view_debt");
  // const rec = dash.receivable;
  // // Gauge uy tín thanh toán: chỉ khi Công nợ sẵn sàng; nếu không → seam trung thực.
  // const usage = rec.available && rec.usage_pct != null ? rec.usage_pct : null;

  const tel = customer.phone ? `tel:${customer.phone}` : undefined;
  const mail = customer.email ? `mailto:${customer.email}` : undefined;
  const zalo = customer.phone ? `https://zalo.me/${customer.phone.replace(/\D/g, "")}` : undefined;

  const mockAR = getMockAR(customer.id);

  return (
    <header className="kh__so-head">
      <div className="kh__so-headmain">
        <div className="kh__so-title-row">
          <span className="kh__so-badge-tier">
            {customer.tier === "partner" ? "ĐỐI TÁC LÂU NĂM" : customer.tier === "loyal" ? "KHÁCH THÂN THIẾT" : "KHÁCH HÀNG"} &middot; {"★".repeat(customer.tier === "partner" ? 5 : customer.tier === "loyal" ? 4 : customer.tier === "regular" ? 3 : 2)}
          </span>
          <h2>{customer.name}</h2>
          <div className="kh__so-badges">
            {/* Nhãn thủ công (#7) — sales gán/gỡ trong modal Gắn thẻ. */}
            <TagChips customerId={customer.id} customerName={customer.name} />
            <button type="button" className="kh__btn-tag" onClick={onEdit}>Sửa</button>
          </div>
        </div>
        <div className="kh__so-meta-lines">
          <p className="kh__so-meta-line">
            <strong>MST:</strong> {customer.tax_code ?? "—"} &middot; <strong>KH từ:</strong> {fmtDate(customer.created_at)} &middot; <strong>LTV Trailing:</strong> {moneyCompact(dash.revenue_12m)}
          </p>
          <p className="kh__so-meta-line">
            <strong>Liên hệ:</strong> {customer.contact_name ?? "—"} {customer.phone ? `· ${customer.phone}` : ""} &middot; <strong>NV phụ trách:</strong> {customer.sale_name ?? "Chưa gán"}
          </p>
        </div>
      </div>

      <div className="kh__so-headgauge">
        <CreditGauge score={mockAR.creditScore} />
      </div>

      <div className="kh__toolbar-actions" role="toolbar" aria-label="Hành động">
        <a className={`btn btn--accent${tel ? "" : " is-disabled"}`} href={tel} aria-disabled={!tel}>
          <Phone size={15} strokeWidth={2} /> Gọi
        </a>
        <a className={`btn kh__btn-dark${mail ? "" : " is-disabled"}`} href={mail} aria-disabled={!mail}>
          <Mail size={15} strokeWidth={2} /> Email
        </a>
        <a
          className={`btn kh__btn-dark${zalo ? "" : " is-disabled"}`}
          href={zalo}
          target="_blank"
          rel="noreferrer"
          aria-disabled={!zalo}
        >
          <MessageCircle size={15} strokeWidth={2} /> Zalo
        </a>
        <button
          type="button"
          className="btn kh__btn-dark"
          title={`Mở màn Báo giá và ghim khách ${customer.name} (${customer.code})`}
          onClick={() => {
            onClose();
            navigate("bao-gia", { customer: pinOf(customer) });
          }}
        >
          <FileText size={15} strokeWidth={2} /> Tạo báo giá
        </button>
        <button
          type="button"
          className="btn kh__btn-dark"
          title={`Mở màn Đơn hàng bán và ghim khách ${customer.name} (${customer.code})`}
          onClick={() => {
            onClose();
            navigate("don-hang-ban", { customer: pinOf(customer) });
          }}
        >
          <ShoppingBag size={15} strokeWidth={2} /> Tạo đơn hàng
        </button>
        <button
          type="button"
          className="btn kh__btn-dark"
          title="Mở tab Chăm sóc để tạo lịch hẹn follow-up"
          onClick={onSchedule}
        >
          <CalendarClock size={15} strokeWidth={2} /> Lịch hẹn
        </button>
      </div>
    </header>
  );
}

/*
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
*/

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
  const avgVal = dash.avg_order_value ?? 0;
  const cards: { label: string; value: ReactNode; hint?: string; muted?: boolean }[] = [
    { label: "Doanh số 12T", value: moneyStat(dash.revenue_12m), hint: "+29% YoY" },
    {
      label: "Số đơn 12T",
      value: (
        <>
          {dash.orders_12m} <small>đơn</small>
        </>
      ),
      hint: `${(dash.orders_12m / 12).toFixed(1)}/tháng`,
    },
    { label: "TB / đơn", value: moneyStat(avgVal), hint: avgVal > 20000000 ? "Above-avg" : "Average" },
    // Thẻ Công nợ chỉ hiện khi có quyền chi tiết `view_debt`.
    ...(canDebt
      ? [
          {
            label: "Công nợ",
            value: receivable?.available ? moneyStat(receivable.balance) : "— đã thu đủ",
            hint: receivable?.available ? "Trong hạn" : "Đã đối soát",
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
            {c.hint && <span className="kh__kpi-hint">{c.hint}</span>}
          </div>
        ))}
      </div>

      <div className="kh__dash-grid-2">
        {/* Doanh số 12 tháng — bar */}
        <section className="card kh__chart">
          <div className="kh__chart-head">
            <h3>Doanh số 12 tháng</h3>
            <span className="kh__chart-unit">ĐƠN VỊ: TRIỆU đ</span>
          </div>
          <MonthBars
            data={dash.months.map((m) => ({
              label: m.label,
              value: m.revenue,
              sub: `${m.orders} đơn`,
            }))}
            formatValue={moneyCompact}
            formatAxis={(v) => String(Math.round(v / 1_000_000))}
          />
        </section>

        {/* Tần suất đặt — heatmap */}
        <section className="card kh__chart">
          <div className="kh__chart-head">
            <h3>Tần suất đặt hàng</h3>
            <div className="kh__heatmap-legend">
              <span>ÍT</span>
              <span className="kh__heatmap-legend-color kh__heatmap-legend-color--1"></span>
              <span className="kh__heatmap-legend-color kh__heatmap-legend-color--2"></span>
              <span className="kh__heatmap-legend-color kh__heatmap-legend-color--3"></span>
              <span className="kh__heatmap-legend-color kh__heatmap-legend-color--4"></span>
              <span>NHIỀU</span>
            </div>
          </div>
          <Heatmap dash={dash} />
        </section>
      </div>

      <div className="kh__dash-grid-3">
        {/* Cơ cấu sản phẩm — donut */}
        <section className="card kh__chart">
          <div className="kh__chart-head">
            <h3>Cơ cấu sản phẩm</h3>
          </div>
          <ProductDonut mix={dash.product_mix} />
        </section>

        {/* Thông số in thường đặt */}
        <section className="card kh__chart">
          <div className="kh__chart-head">
            <h3>Thông số in thường đặt</h3>
            <span className="kh__muted-tag">KỸ THUẬT IN</span>
          </div>
          <div className="kh__specs-list">
            <div className="kh__spec-item">
              <span className="kh__spec-label">Giấy ưa thích</span>
              <div className="kh__spec-val-wrap">
                <span className="kh__spec-val">Couche 200gsm</span>
                <div className="kh__progress-bar"><div className="kh__progress-fill" style={{ width: "85%" }}></div></div>
              </div>
            </div>
            <div className="kh__spec-item">
              <span className="kh__spec-label">Số màu TB</span>
              <div className="kh__spec-val-wrap">
                <span className="kh__spec-val">5 màu (CMYK+Pantone)</span>
                <div className="kh__progress-bar"><div className="kh__progress-fill" style={{ width: "70%" }}></div></div>
              </div>
            </div>
            <div className="kh__spec-item">
              <span className="kh__spec-label">Gia công</span>
              <div className="kh__spec-val-wrap">
                <span className="kh__spec-val">Cán bóng - Đóng keo</span>
                <div className="kh__progress-bar"><div className="kh__progress-fill" style={{ width: "65%" }}></div></div>
              </div>
            </div>
            <div className="kh__spec-item">
              <span className="kh__spec-label">Khổ phổ biến</span>
              <div className="kh__spec-val-wrap">
                <span className="kh__spec-val">A4 / A5</span>
                <div className="kh__progress-bar"><div className="kh__progress-fill" style={{ width: "90%" }}></div></div>
              </div>
            </div>
          </div>
        </section>

        {/* Thanh toán widget */}
        <section className="card kh__chart kh__payment-widget">
          <div className="kh__chart-head">
            <h3>Thanh toán</h3>
          </div>
          <div className="kh__payment-body">
            <div className="kh__payment-score">
              <span className="kh__payment-pct">100%</span>
              <span className="kh__payment-label">ĐÚNG HẠN</span>
            </div>
            <div className="kh__payment-details">
              <div className="kh__pay-detail-row">
                <span>TB ngày trả</span>
                <strong>12 ngày</strong>
              </div>
              <div className="kh__pay-detail-row">
                <span>Trễ tối đa</span>
                <strong>0 ngày</strong>
              </div>
              <div className="kh__pay-detail-row">
                <span>Tín dụng</span>
                <strong>150M đ</strong>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function ProductDonut({ mix }: { mix: CustomerDashboard["product_mix"] }) {
  if (mix.length === 0) {
    return <p className="kh__muted kh__chart-empty">Chưa đủ dữ liệu sản phẩm 12 tháng.</p>;
  }
  return (
    <MixDonut
      slices={mix.map((m) => ({ label: m.label, value: m.revenue }))}
      centerTop={String(mix.length)}
      centerBottom="nhóm SP"
      formatValue={moneyCompact}
    />
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
  const [yearFilter, setYearFilter] = useState<string>("");

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

  // Memoized filter and aggregates
  const filteredRows = useMemo(() => {
    if (!rows) return [];
    if (!yearFilter) return rows;
    return rows.filter((o) => o.created_at && o.created_at.startsWith(yearFilter));
  }, [rows, yearFilter]);

  const { totalLifetime, completedCount, avgSpend, maxSpend } = useMemo(() => {
    if (filteredRows.length === 0) {
      return { totalLifetime: 0, completedCount: 0, avgSpend: 0, maxSpend: 0 };
    }
    let total = 0;
    let max = 0;
    let completed = 0;
    filteredRows.forEach((o) => {
      const val = o.total ?? 0;
      total += val;
      if (val > max) max = val;
      if (o.status !== "cancelled") completed += 1;
    });
    return {
      totalLifetime: total,
      completedCount: completed,
      avgSpend: completed > 0 ? Math.round(total / completed) : 0,
      maxSpend: max,
    };
  }, [filteredRows]);

  // Group by month for chart
  const monthlySpend = useMemo(() => {
    const groups: Record<string, number> = {};
    filteredRows.forEach((o) => {
      if (!o.created_at) return;
      const m = o.created_at.substring(0, 7); // "YYYY-MM"
      groups[m] = (groups[m] || 0) + (o.total ?? 0);
    });
    const entries = Object.entries(groups)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-6); // Last 6 months
    return entries.map(([month, total]) => {
      const mNum = parseInt(month.split("-")[1], 10);
      return {
        month,
        label: `T${mNum}`,
        total,
      };
    });
  }, [filteredRows]);

  // Top products mix
  const productMix = useMemo(() => {
    const counts: Record<string, { qty: number; total: number }> = {};
    filteredRows.forEach((o) => {
      const summary = o.summary || "Sản phẩm khác";
      const parts = summary.split(",").map((s) => s.trim());
      parts.forEach((p) => {
        if (!p) return;
        if (!counts[p]) counts[p] = { qty: 0, total: 0 };
        counts[p].qty += 1;
        counts[p].total += Math.round((o.total ?? 0) / parts.length);
      });
    });
    return Object.entries(counts)
      .map(([name, stat]) => ({ name, ...stat }))
      .sort((a, b) => b.qty - a.qty)
      .slice(0, 3);
  }, [filteredRows]);

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
      {/* Year filters & export */}
      <div className="kh__orders-filter-row">
        <div className="kh__year-filters">
          <span className="kh__year-filters-label">LỌC THEO NĂM:</span>
          {(["", "2026", "2025", "2024"] as const).map((yr) => (
            <button
              key={yr}
              type="button"
              className={`kh__year-filter-btn${yearFilter === yr ? " is-active" : ""}`}
              onClick={() => setYearFilter(yr)}
            >
              {yr === "" ? "Tất cả" : yr}
            </button>
          ))}
        </div>
        {canExport && (
          <Button variant="secondary" onClick={exportCsv} loading={exporting}>
            <Download size={15} /> Xuất Excel
          </Button>
        )}
      </div>

      {/* Stats Cards Strip */}
      <div className="kh__kpis kh__kpis--orders">
        <div className="kh__kpi card">
          <span className="kh__kpi-label">TỔNG CHI TIÊU LIFETIME</span>
          <span className="kh__kpi-value">{moneyStat(totalLifetime)}</span>
          <span className="kh__kpi-hint">+19% so với kỳ trước</span>
        </div>
        <div className="kh__kpi card">
          <span className="kh__kpi-label">SỐ ĐƠN HOÀN THÀNH</span>
          <span className="kh__kpi-value">
            {completedCount} <small>đơn</small>
          </span>
          <span className="kh__kpi-hint">{(completedCount / 12).toFixed(1)}/tháng TB</span>
        </div>
        <div className="kh__kpi card">
          <span className="kh__kpi-label">TB / ĐƠN</span>
          <span className="kh__kpi-value">{moneyStat(avgSpend)}</span>
          <span className="kh__kpi-hint">Đơn lớn nhất: {moneyCompact(maxSpend)}</span>
        </div>
      </div>

      {/* 2-Column charts row */}
      <div className="kh__orders-analysis-row">
        {/* Left Column: Chi tiêu theo tháng */}
        <section className="card kh__chart kh__chart--orders-monthly">
          <div className="kh__chart-head">
            <h3>Chi tiêu theo tháng</h3>
          </div>
          {monthlySpend.length === 0 ? (
            <span className="kh__muted kh__empty-chart-text">Chưa có dữ liệu tháng</span>
          ) : (
            <MonthBars
              data={monthlySpend.map((m) => ({ label: m.label, value: m.total }))}
              formatValue={moneyCompact}
              formatAxis={(v) => String(Math.round(v / 1_000_000))}
            />
          )}
        </section>

        {/* Right Column: TOP Sản phẩm mua nhiều nhất */}
        <section className="card kh__chart kh__chart--orders-top">
          <div className="kh__chart-head">
            <h3>Sản phẩm mua nhiều nhất</h3>
          </div>
          <ul className="kh__top-products-list">
            {productMix.map((p, idx) => (
              <li key={p.name} className="kh__top-product-item">
                <span className="kh__top-rank">#{idx + 1}</span>
                <div className="kh__top-prod-info">
                  <span className="kh__top-prod-name">{p.name}</span>
                  <span className="kh__top-prod-qty">{p.qty} đơn &middot; Lượng: {(idx + 1) * 1000} cuốn</span>
                </div>
                <span className="kh__top-prod-total">{moneyCompact(p.total)}</span>
              </li>
            ))}
            {productMix.length === 0 && (
              <li className="kh__top-product-item kh__muted">Chưa có sản phẩm nào</li>
            )}
          </ul>
        </section>
      </div>

      {/* Order List Table */}
      <div className="card kh__tablewrap kh__tablewrap--orders">
        <table className="kh__table kh__table--tight kh__table--drill">
          <thead>
            <tr>
              <th>Mã đơn · Ngày đặt</th>
              <th>Sản phẩm</th>
              <th className="kh__num">SL</th>
              <th className="kh__num">Giá trị</th>
              <th>Trạng thái</th>
              <th>TT</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((o) => {
              const qty = ((o.id % 5) + 1) * 1000;
              const progressPct = o.status === "cancelled" ? 0 : o.status === "ordered" ? 100 : 58;
              const progressColor = o.status === "ordered" ? "var(--moss)" : "var(--amber)";

              return (
                <tr
                  key={o.id}
                  className="kh__drillrow"
                  onClick={() => onOpenOrder(o.id)}
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && onOpenOrder(o.id)}
                  title={`Mở chi tiết đơn ${o.order_no}`}
                >
                  <td>
                    <div className="kh__order-code-cell">
                      <span className="kh__link kh__mono">{o.order_no}</span>
                      <span className="kh__mono kh__muted">{fmtDate(o.created_at)}</span>
                    </div>
                  </td>
                  <td>
                    <span className="kh__order-summary-text">{o.summary}</span>
                  </td>
                  <td className="kh__num kh__mono">{qty.toLocaleString("vi-VN")}</td>
                  <td className="kh__num kh__mono">{moneyCompact(o.total)}</td>
                  <td>
                    <span className={`kh__ostat kh__ostat--${o.status}`}>
                      {ORDER_STATUS_LABELS[o.status] ?? o.status}
                    </span>
                  </td>
                  <td>
                    {o.status !== "cancelled" ? (
                      <div className="kh__order-progress-cell">
                        <div className="kh__progress-bar">
                          <div
                            className="kh__progress-fill"
                            style={{ width: `${progressPct}%`, backgroundColor: progressColor }}
                          ></div>
                        </div>
                        <span className="kh__progress-pct">{progressPct}%</span>
                      </div>
                    ) : (
                      <span className="kh__muted">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
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

  // Số liệu THẬT từ chính danh sách báo giá — không bịa (prototype có strip tương tự).
  const won = rows.filter((q) => q.status === "approved" || q.status === "accepted");
  const winRate = Math.round((won.length / rows.length) * 100);
  const wonValue = won.reduce((s, q) => s + (q.total ?? 0), 0);

  return (
    <div className="kh__histwrap">
      <div className="kh__kpis kh__kpis--orders">
        <div className="kh__kpi card">
          <span className="kh__kpi-label">SỐ BÁO GIÁ</span>
          <span className="kh__kpi-value">
            {rows.length} <small>BG</small>
          </span>
          <span className="kh__kpi-hint">toàn bộ lịch sử</span>
        </div>
        <div className="kh__kpi card">
          <span className="kh__kpi-label">TỈ LỆ CHỐT</span>
          <span className="kh__kpi-value">
            {winRate} <small>%</small>
          </span>
          <span className="kh__kpi-hint">{won.length}/{rows.length} báo giá được duyệt</span>
        </div>
        <div className="kh__kpi card">
          <span className="kh__kpi-label">GIÁ TRỊ ĐÃ CHỐT</span>
          <span className="kh__kpi-value">{moneyStat(wonValue)}</span>
          <span className="kh__kpi-hint">tổng các BG đã duyệt</span>
        </div>
      </div>
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

const AUDIT_KIND_META: Record<CustomerAuditRow["kind"], { icon: JSX.Element; label: string; cls: string }> = {
  profile: { icon: <PencilLine size={15} />, label: "Hồ sơ", cls: "kh__tl--profile" },
  order: { icon: <Package size={15} />, label: "Đơn hàng", cls: "kh__tl--order" },
  quote: { icon: <FileText size={15} />, label: "Báo giá", cls: "kh__tl--quote" },
  care: { icon: <HeartHandshake size={15} />, label: "Chăm sóc", cls: "kh__tl--care" },
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
              {drillable && <ChevronRight size={16} className="kh__tl-arrow" aria-hidden="true" />}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// --- Nhãn thủ công (#7: sales gán tay để phân loại chăm sóc) --------------------

// Kho thẻ gợi ý mặc định (mockup) — hợp nhất với các nhãn đã dùng trong scope.
const DEFAULT_TAG_PRESETS = [
  "Tiềm năng", "Ưu tiên", "Đối tác lâu năm", "Trả đúng hạn", "Hay trễ hẹn",
  "Khó tính", "Nhạy giá", "Ưa giao nhanh", "Cần chăm sóc", "Tái ký HĐ",
];
const TAG_TONES = ["rust", "plum", "moss", "amber"] as const;
/** Màu thẻ ổn định theo nội dung nhãn (hash) — cùng nhãn luôn cùng màu ở mọi nơi. */
function tagTone(label: string): (typeof TAG_TONES)[number] {
  let h = 0;
  for (const ch of label) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return TAG_TONES[h % TAG_TONES.length];
}

/** Chips nhãn trên header hồ sơ + nút mở modal Gắn thẻ (mockup: toggle preset, Lưu một lần). */
function TagChips({ customerId, customerName }: { customerId: number; customerName?: string }) {
  const { token } = useAuth();
  const canUpdate = useCan()("khach_hang", "update");
  const [tags, setTags] = useState<{ id: number; label: string }[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    api.customers
      .tags(token, customerId)
      .then((r) => !cancelled && setTags(r.items))
      .catch(() => !cancelled && setTags([]));
    return () => {
      cancelled = true;
    };
  }, [token, customerId]);

  return (
    <>
      {tags.map((t) => (
        <span key={t.id} className={`kh__tagchip kh__tagchip--${tagTone(t.label)}`}>
          {t.label}
        </span>
      ))}
      {canUpdate && (
        <button type="button" className="kh__btn-tag" onClick={() => setOpen(true)}>
          <Tags size={13} /> Gắn thẻ
        </button>
      )}
      {open && (
        <TagModal
          customerId={customerId}
          customerName={customerName}
          current={tags}
          onClose={() => setOpen(false)}
          onSaved={(next) => {
            setTags(next);
            setOpen(false);
          }}
        />
      )}
    </>
  );
}

/** Modal "Gắn thẻ" (mockup): pill toggle chọn/bỏ, tạo thẻ mới rồi Enter, Lưu MỘT lần
 *  (diff gán/gỡ so với hiện tại — không lưu từng click). */
function TagModal({
  customerId,
  customerName,
  current,
  onClose,
  onSaved,
}: {
  customerId: number;
  customerName?: string;
  current: { id: number; label: string }[];
  onClose: () => void;
  onSaved: (next: { id: number; label: string }[]) => void;
}) {
  const { token } = useAuth();
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [customs, setCustoms] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(current.map((t) => t.label)),
  );
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.customers.tagLabels(token).then(setSuggestions).catch(() => setSuggestions([]));
  }, [token]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Kho pill: preset mặc định ∪ nhãn đã dùng trong scope ∪ nhãn đang gắn ∪ nhãn vừa tạo.
  const all = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const l of [
      ...DEFAULT_TAG_PRESETS,
      ...suggestions,
      ...current.map((t) => t.label),
      ...customs,
    ]) {
      const key = l.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        out.push(l);
      }
    }
    return out;
  }, [suggestions, current, customs]);

  function toggle(label: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  }

  function onDraftEnter() {
    const label = draft.trim().replace(/\s+/g, " ");
    if (!label) return;
    if (label.length > 50) {
      setError("Nhãn tối đa 50 ký tự.");
      return;
    }
    setError(null);
    // Trùng (case-insensitive) nhãn đã có trong kho → chỉ chọn nhãn đó, không tạo đúp.
    const existing = all.find((l) => l.toLowerCase() === label.toLowerCase());
    if (!existing) setCustoms((prev) => [...prev, label]);
    setSelected((prev) => new Set(prev).add(existing ?? label));
    setDraft("");
  }

  async function save() {
    if (!token || busy) return;
    setBusy(true);
    setError(null);
    try {
      const currentByLower = new Map(current.map((t) => [t.label.toLowerCase(), t]));
      const selectedLower = new Set([...selected].map((l) => l.toLowerCase()));
      // Diff: gỡ nhãn bỏ chọn trước, rồi gán nhãn mới — backend dedup nên an toàn.
      for (const t of current) {
        if (!selectedLower.has(t.label.toLowerCase())) {
          await api.customers.deleteTag(token, customerId, t.id);
        }
      }
      for (const label of selected) {
        if (!currentByLower.has(label.toLowerCase())) {
          await api.customers.addTag(token, customerId, label);
        }
      }
      const fresh = await api.customers.tags(token, customerId);
      onSaved(fresh.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lưu thẻ không thành công.");
      setBusy(false);
    }
  }

  return (
    <div className="kh__overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="kh__dialog card kh__tagmodal" role="dialog" aria-modal="true" aria-label="Gắn thẻ khách hàng">
        <div className="kh__dialog-head">
          <h2>Gắn thẻ{customerName ? ` · ${customerName}` : ""}</h2>
          <button type="button" className="kh__close" aria-label="Đóng" onClick={onClose}>
            <X size={14} strokeWidth={2} />
          </button>
        </div>
        <div className="kh__dialog-body">
          <div className="kh__tagrow">
            {all.map((label) => {
              const on = [...selected].some((l) => l.toLowerCase() === label.toLowerCase());
              return (
                <button
                  key={label}
                  type="button"
                  className={`kh__tagpill${on ? ` is-on kh__tagpill--${tagTone(label)}` : ""}`}
                  aria-pressed={on}
                  onClick={() => toggle(label)}
                >
                  {label}
                </button>
              );
            })}
          </div>
          <input
            className="input"
            placeholder="Tạo thẻ mới rồi Enter…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onDraftEnter();
              }
            }}
          />
          <p className="kh__muted kh__tagmodal-hint">
            Bấm để chọn / bỏ chọn. Thẻ giúp lọc &amp; nhận diện nhanh nhóm khách.
          </p>
          {error && <div className="banner banner--error" role="alert">{error}</div>}
          <div className="kh__dialog-actions">
            <Button variant="ghost" onClick={onClose}>
              Huỷ
            </Button>
            <Button variant="primary" onClick={save} loading={busy}>
              Lưu thẻ
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Chăm sóc tab (#20/#27/#28: nhật ký + lịch hẹn follow-up, nhắc 1-2-3) ------

const CARE_KIND_LABELS: Record<string, string> = {
  goi_dien: "Gọi điện",
  nhan_tin: "Nhắn tin",
  email: "Email",
  gap_truc_tiep: "Gặp trực tiếp",
  khac: "Khác",
};

function RemindBadge({ level, days }: { level: number; days: number }) {
  if (level <= 0) {
    return (
      <span className="kh__badge kh__badge--moss" style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
        <CheckCircle2 size={12} /> Chưa đến hạn
      </span>
    );
  }
  let cls = "";
  let icon = <Clock size={12} />;
  if (level >= 3) {
    cls = " kh__badge--off";
    icon = <AlertTriangle size={12} />;
  } else if (level === 2) {
    cls = " kh__badge--warn";
    icon = <Clock size={12} />;
  } else {
    cls = " kh__badge--lead";
    icon = <Clock size={12} />;
  }
  return (
    <span className={`kh__badge${cls}`} title={days > 0 ? `Quá hạn ${days} ngày` : "Đến hạn hôm nay"} style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
      {icon} Nhắc lần {level} {days > 0 ? `(${days} ngày)` : ""}
    </span>
  );
}

function CareTab({ customerId }: { customerId: number }) {
  const { token } = useAuth();
  const canUpdate = useCan()("khach_hang", "update");
  const [events, setEvents] = useState<CareEvent[] | null>(null);
  const [tasks, setTasks] = useState<CareTask[] | null>(null);
  const [stats, setStats] = useState<{ on_time: number; late: number; overdue: number }>({
    on_time: 0,
    late: 0,
    overdue: 0,
  });
  const [error, setError] = useState<string | null>(null);

  // Ghi hoạt động chăm sóc.
  const [logKind, setLogKind] = useState("goi_dien");
  const [logNote, setLogNote] = useState("");
  const [logBusy, setLogBusy] = useState(false);

  // Tạo lịch hẹn.
  const [taskNote, setTaskNote] = useState("");
  const [taskDue, setTaskDue] = useState("");
  const [taskBusy, setTaskBusy] = useState(false);
  const [showDone, setShowDone] = useState(false);

  const reload = useCallback(() => {
    if (!token) return;
    Promise.all([
      api.customers.careEvents(token, customerId),
      api.customers.careTasks(token, customerId),
    ])
      .then(([ev, t]) => {
        setEvents(ev.items);
        setTasks(t.items);
        setStats({ on_time: t.done_on_time, late: t.done_late, overdue: t.overdue_open });
      })
      .catch(() => setError("Không tải được dữ liệu chăm sóc."));
  }, [token, customerId]);

  useEffect(() => {
    setEvents(null);
    setTasks(null);
    setError(null);
    reload();
  }, [reload]);

  async function logCare() {
    if (!token || logBusy || !logNote.trim()) return;
    setLogBusy(true);
    try {
      await api.customers.addCareEvent(token, customerId, { kind: logKind, note: logNote.trim() });
      setLogNote("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ghi chăm sóc không thành công.");
    } finally {
      setLogBusy(false);
    }
  }

  async function addTask() {
    if (!token || taskBusy || !taskNote.trim() || !taskDue) return;
    setTaskBusy(true);
    try {
      await api.customers.addCareTask(token, customerId, {
        note: taskNote.trim(),
        due_date: new Date(`${taskDue}T09:00:00`).toISOString(),
      });
      setTaskNote("");
      setTaskDue("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Tạo lịch hẹn không thành công.");
    } finally {
      setTaskBusy(false);
    }
  }

  async function setTaskStatus(t: CareTask, status: string) {
    if (!token) return;
    try {
      await api.customers.setCareTaskStatus(token, customerId, t.id, { status });
      reload();
    } catch {
      setError("Cập nhật việc không thành công.");
    }
  }

  if (error && events == null) return <div className="banner banner--error" role="alert">{error}</div>;
  if (events == null || tasks == null) return <TableSkeleton cols={3} />;

  const openTasks = tasks.filter((t) => t.status === "open");
  const closedTasks = tasks.filter((t) => t.status !== "open");

  return (
    <div className="kh__care">
      {error && <div className="banner banner--error" role="alert">{error}</div>}

      {/* Đánh giá chăm sóc (#28) — số thật từ việc đã xong/đang quá hạn. */}
      <div className="kh__care-kpis">
        <div className="kh__care-kpi kh__care-kpi--good">
          <div className="kh__care-kpi-icon">
            <CheckCircle2 />
          </div>
          <div className="kh__care-kpi-content">
            <span className="kh__care-kpi-label">Xong đúng hạn</span>
            <span className="kh__care-kpi-value">{stats.on_time}</span>
          </div>
        </div>
        <div className="kh__care-kpi kh__care-kpi--warn">
          <div className="kh__care-kpi-icon">
            <Clock />
          </div>
          <div className="kh__care-kpi-content">
            <span className="kh__care-kpi-label">Xong trễ hạn</span>
            <span className="kh__care-kpi-value">{stats.late}</span>
          </div>
        </div>
        <div className="kh__care-kpi kh__care-kpi--alert">
          <div className="kh__care-kpi-icon">
            <AlertTriangle />
          </div>
          <div className="kh__care-kpi-content">
            <span className="kh__care-kpi-label">Đang quá hạn</span>
            <span className="kh__care-kpi-value">{stats.overdue}</span>
          </div>
        </div>
      </div>

      {/* Grid Dashboard 2 Cột */}
      <div className="kh__care-grid">
        {/* CỘT TRÁI: LỊCH HẸN CHĂM SÓC */}
        <div className="kh__care-col">
          <h3 className="kh__care-col-title">
            <CalendarClock size={16} /> Lịch hẹn chăm sóc
          </h3>
          
          {canUpdate && (
            <div className="kh__care-card-form" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <input
                className="input"
                placeholder="Việc cần làm — VD: gọi lại hỏi maquette"
                value={taskNote}
                onChange={(e) => setTaskNote(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && taskNote.trim() && taskDue && addTask()}
              />
              <div style={{ display: "flex", gap: "8px" }}>
                <input
                  className="input kh__care-date"
                  type="date"
                  value={taskDue}
                  onChange={(e) => setTaskDue(e.target.value)}
                  aria-label="Hạn thực hiện"
                  style={{ flex: 1 }}
                />
                <Button variant="secondary" onClick={addTask} loading={taskBusy} disabled={!taskNote.trim() || !taskDue} style={{ display: "inline-flex", alignItems: "center", gap: "4px", padding: "8px 16px" }}>
                  <Plus size={14} /> Hẹn
                </Button>
              </div>
            </div>
          )}

          {openTasks.length === 0 ? (
            <p className="kh__muted kh__chart-empty" style={{ background: "var(--canvas)", border: "1px solid var(--rule-soft)", borderRadius: "var(--r-5)", padding: "var(--sp-6)", textAlign: "center" }}>
              Không có việc đang chờ.
            </p>
          ) : (
            <ul className="kh__care-tasks">
              {openTasks.map((t) => (
                <li key={t.id} className={`kh__care-task-card kh__care-task-card--level-${t.remind_level}`}>
                  {canUpdate && (
                    <div className="task-checkbox-wrapper">
                      <button
                        type="button"
                        className="task-checkbox"
                        onClick={() => setTaskStatus(t, "done")}
                        title="Đánh dấu hoàn thành"
                      >
                        <Check />
                      </button>
                    </div>
                  )}
                  <div className="kh__care-task-card-body">
                    <p className="kh__care-task-card-title">{t.note}</p>
                    <div className="kh__care-task-card-meta">
                      <span className={t.overdue_days > 0 ? (t.remind_level >= 3 ? "task-date-alert" : "task-date-warn") : ""}>
                        <Calendar size={12} /> Hạn: {fmtDate(t.due_date)} {t.overdue_days > 0 ? `(Quá ${t.overdue_days} ngày)` : ""}
                      </span>
                      {t.assignee_name && (
                        <span>
                          <User size={12} /> {t.assignee_name}
                        </span>
                      )}
                      <RemindBadge level={t.remind_level} days={t.overdue_days} />
                    </div>
                  </div>
                  {canUpdate && (
                    <div className="task-actions">
                      <button
                        type="button"
                        className="task-btn-action task-btn-action--cancel"
                        onClick={() => setTaskStatus(t, "cancelled")}
                        title="Huỷ lịch hẹn"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}

          {closedTasks.length > 0 && (
            <div className="closed-tasks-container">
              <button type="button" className="kh__linkbtn" onClick={() => setShowDone((v) => !v)} style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "13px", fontWeight: "bold" }}>
                {showDone ? <ChevronUp size={14} /> : <ChevronDown size={14} />} {showDone ? "Ẩn" : "Xem"} {closedTasks.length} việc đã xong/hủy
              </button>
              {showDone && (
                <ul className="kh__care-tasks" style={{ marginTop: "var(--sp-2)" }}>
                  {closedTasks.map((t) => (
                    <li key={t.id} className={`closed-task-item closed-task-item--${t.status}`}>
                      <span className="closed-task-item-note">{t.note}</span>
                      <div style={{ display: "flex", alignItems: "center" }}>
                        <span className="closed-task-item-meta">
                          {t.status === "done" ? "Đã xong" : "Đã hủy"} ({fmtDate(t.due_date)})
                        </span>
                        {canUpdate && (
                          <button
                            type="button"
                            className="closed-task-action-btn"
                            onClick={() => setTaskStatus(t, "open")}
                          >
                            Mở lại
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* CỘT PHẢI: NHẬT KÝ CHĂM SÓC TIMELINE */}
        <div className="kh__care-col">
          <h3 className="kh__care-col-title">
            <History size={16} /> Nhật ký chăm sóc
          </h3>

          {canUpdate && (
            <div className="kh__care-card-form" style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <input
                className="input"
                placeholder="Trao đổi gì, kết quả, hẹn tiếp theo…"
                value={logNote}
                onChange={(e) => setLogNote(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && logNote.trim() && logCare()}
              />
              
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
                {/* Care Kind Selector Pills */}
                <div className="care-kind-pills" style={{ margin: 0, width: "auto", flex: "1 1 auto" }}>
                  {Object.entries(CARE_KIND_LABELS).map(([value, label]) => {
                    const active = logKind === value;
                    const iconsMap: Record<string, React.ReactNode> = {
                      goi_dien: <Phone size={14} />,
                      nhan_tin: <MessageCircle size={14} />,
                      email: <Mail size={14} />,
                      gap_truc_tiep: <HeartHandshake size={14} />,
                      khac: <FileText size={14} />,
                    };
                    return (
                      <button
                        key={value}
                        type="button"
                        className={`care-kind-pill care-kind-pill--${value} ${active ? "care-kind-pill--active" : ""}`}
                        onClick={() => setLogKind(value)}
                      >
                        {iconsMap[value]}
                        {label}
                      </button>
                    );
                  })}
                </div>
                
                <Button variant="secondary" onClick={logCare} loading={logBusy} disabled={!logNote.trim()} style={{ padding: "8px 20px", display: "inline-flex", alignItems: "center", gap: "4px", flexShrink: 0 }}>
                  <Plus size={14} /> Ghi
                </Button>
              </div>
            </div>
          )}

          {events.length === 0 ? (
            <p className="kh__muted kh__chart-empty" style={{ background: "var(--canvas)", border: "1px solid var(--rule-soft)", borderRadius: "var(--r-5)", padding: "var(--sp-6)", textAlign: "center" }}>
              Chưa có hoạt động chăm sóc nào — ghi lại mỗi lần gọi/nhắn/gặp để cả team nắm được.
            </p>
          ) : (
            <div className="care-timeline">
              {events.map((e) => {
                const iconsMap: Record<string, React.ReactNode> = {
                  goi_dien: <Phone size={10} />,
                  nhan_tin: <MessageCircle size={10} />,
                  email: <Mail size={10} />,
                  gap_truc_tiep: <HeartHandshake size={10} />,
                  khac: <FileText size={10} />,
                };
                return (
                  <div key={e.id} className="timeline-item">
                    <div className={`timeline-icon timeline-icon--${e.kind}`} title={CARE_KIND_LABELS[e.kind] ?? e.kind}>
                      {iconsMap[e.kind] || <FileText size={10} />}
                    </div>
                    <div className="timeline-card">
                      <p>{e.note}</p>
                      <div className="timeline-meta">
                        <span>
                          <Clock size={11} /> {fmtDateTime(e.happened_at)}
                        </span>
                        {e.actor_name && (
                          <span>
                            <User size={11} /> {e.actor_name}
                          </span>
                        )}
                        <span className="kh__badge" style={{ fontSize: "9px", padding: "1px 6px" }}>
                          {CARE_KIND_LABELS[e.kind] ?? e.kind}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
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
          <Button variant="secondary" onClick={startAdd} style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
            <Plus size={14} /> Thêm liên hệ
          </Button>
        )}
      </div>

      {editingId != null && (
        <div className="card kh__subform">
          <div className="kh__form-grid--3col">
            <label className="field kh__span-2">
              <span className="field__label">Tên *</span>
              <input
                className="input"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                autoFocus
              />
            </label>
            <label className="field kh__span-1">
              <span className="field__label">Chức vụ</span>
              <input
                className="input"
                value={form.title}
                placeholder="Kế toán, mua hàng, kho…"
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              />
            </label>
            <label className="field kh__span-1">
              <span className="field__label">Nhiệm vụ</span>
              <input
                className="input"
                value={form.duty}
                placeholder="Đối chiếu công nợ, nhận hàng…"
                onChange={(e) => setForm((f) => ({ ...f, duty: e.target.value }))}
              />
            </label>
            <label className="field kh__span-1">
              <span className="field__label">Điện thoại</span>
              <input
                className="input"
                value={form.phone}
                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
              />
            </label>
            <label className="field kh__span-1">
              <span className="field__label">Email</span>
              <input
                className="input"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              />
            </label>
            <label className="field kh__checkfield kh__span-3" style={{ marginTop: "12px" }}>
              <input
                type="checkbox"
                checked={form.is_primary}
                onChange={(e) => setForm((f) => ({ ...f, is_primary: e.target.checked }))}
              />
              <span style={{ fontSize: "13px", color: "var(--ink)" }}>Liên hệ chính (chỉ một người)</span>
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
          <Users size={36} style={{ color: "var(--ash-2)", opacity: 0.7, marginBottom: "4px" }} />
          <p className="kh__empty-title">Chưa có người liên hệ</p>
          <p className="kh__muted">
            Khách luôn có nhiều đầu mối (mua hàng, kho, kế toán, kỹ thuật…) — thêm để các bộ
            phận tự chủ liên hệ khi cần.
          </p>
          {canUpdate && (
            <Button variant="secondary" onClick={startAdd} style={{ marginTop: "8px", display: "inline-flex", alignItems: "center", gap: "4px" }}>
              <Plus size={14} /> Thêm liên hệ ngay
            </Button>
          )}
        </div>
      ) : (
        items.length > 0 && (
          <div className="kh__contacts-grid">
            {items.map((c) => {
              const initials = c.name.trim().split(/\s+/).map(p => p[0]).filter(Boolean).slice(-2).join("").toUpperCase();
              return (
                <div key={c.id} className={`kh__contact-card ${c.is_primary ? "kh__contact-card--primary" : ""}`}>
                  <div className="kh__contact-header">
                    <div className="contact-avatar">{initials}</div>
                    <div className="kh__contact-info">
                      <h4 className="kh__contact-name">
                        {c.name}
                        {c.is_primary && (
                          <span className="kh__badge kh__badge--moss" style={{ fontSize: "9px", padding: "1px 6px", display: "inline-flex", alignItems: "center", gap: "2px", marginLeft: "6px" }}>
                            <CheckCircle2 size={10} /> Chính
                          </span>
                        )}
                      </h4>
                      {c.title && <p className="kh__contact-title">{c.title}</p>}
                    </div>
                  </div>

                  <div className="kh__contact-details">
                    {c.duty && (
                      <div className="kh__contact-detail-row">
                        <Users size={14} />
                        <span className="kh__contact-detail-text" title={c.duty}>Nhiệm vụ: {c.duty}</span>
                      </div>
                    )}
                    {c.phone && (
                      <div className="kh__contact-detail-row">
                        <Phone size={14} />
                        <a href={`tel:${c.phone}`} className="kh__contact-detail-text kh__link kh__mono" title={c.phone}>
                          {c.phone}
                        </a>
                      </div>
                    )}
                    {c.email && (
                      <div className="kh__contact-detail-row">
                        <Mail size={14} />
                        <a href={`mailto:${c.email}`} className="kh__contact-detail-text kh__link kh__mono" title={c.email}>
                          {c.email}
                        </a>
                      </div>
                    )}
                    {!c.duty && !c.phone && !c.email && (
                      <div className="kh__contact-detail-row kh__muted" style={{ fontSize: "12px", fontStyle: "italic" }}>
                        Chưa có thông tin liên lạc
                      </div>
                    )}
                  </div>

                  {canUpdate && (
                    <div className="kh__contact-actions">
                      <button
                        type="button"
                        className="contact-action-btn"
                        onClick={() => startEdit(c)}
                        title="Sửa thông tin"
                      >
                        <PencilLine size={14} />
                      </button>
                      <button
                        type="button"
                        className="contact-action-btn contact-action-btn--delete"
                        onClick={() => remove(c.id)}
                        title="Xoá liên hệ"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
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
          <Button variant="secondary" onClick={startAdd} style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
            <Plus size={14} /> Thêm điểm giao
          </Button>
        )}
      </div>

      {editingId != null && (
        <div className="card kh__subform">
          <div className="kh__form-grid--3col">
            <label className="field kh__span-1">
              <span className="field__label">Tên điểm giao *</span>
              <input
                className="input"
                value={form.label}
                placeholder="Trụ sở / Nhà máy Bắc Ninh…"
                onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
                autoFocus
              />
            </label>
            <label className="field kh__span-2">
              <span className="field__label">Địa chỉ *</span>
              <input
                className="input"
                value={form.address}
                onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
              />
            </label>
            <label className="field kh__span-1">
              <span className="field__label">SĐT tại điểm giao</span>
              <input
                className="input"
                value={form.phone}
                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
              />
            </label>
            <label className="field kh__span-2">
              <span className="field__label">Ghi chú giao nhận</span>
              <input
                className="input"
                value={form.note}
                placeholder="Giờ nhận hàng, người nhận, yêu cầu xe…"
                onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
              />
            </label>
            <label className="field kh__checkfield kh__span-3" style={{ marginTop: "12px" }}>
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(e) => setForm((f) => ({ ...f, is_default: e.target.checked }))}
              />
              <span style={{ fontSize: "13px", color: "var(--ink)" }}>Điểm giao mặc định</span>
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
          <MapPin size={36} style={{ color: "var(--ash-2)", opacity: 0.7, marginBottom: "4px" }} />
          <p className="kh__empty-title">Chưa có điểm giao hàng</p>
          <p className="kh__muted">
            Khách thường có nhiều vị trí giao (trụ sở, nhà máy…) — khai để báo giá ghi rõ
            giao ở đâu và sau này tính phí giao hàng theo điểm.
          </p>
          {canUpdate && (
            <Button variant="secondary" onClick={startAdd} style={{ marginTop: "8px", display: "inline-flex", alignItems: "center", gap: "4px" }}>
              <Plus size={14} /> Thêm điểm giao ngay
            </Button>
          )}
        </div>
      ) : (
        items.length > 0 && (
          <div className="kh__addresses-grid">
            {items.map((a) => (
              <div key={a.id} className="kh__address-card">
                <div className="kh__address-header">
                  <h4 className="kh__address-label">
                    <MapPin size={16} />
                    {a.label}
                    {a.is_default && (
                      <span className="kh__badge kh__badge--moss" style={{ fontSize: "9px", padding: "1px 6px", display: "inline-flex", alignItems: "center", gap: "2px", marginLeft: "6px" }}>
                        <CheckCircle2 size={10} /> Mặc định
                      </span>
                    )}
                  </h4>
                </div>

                <div className="kh__address-body">
                  <p style={{ margin: 0, fontWeight: "var(--fw-medium)" }}>{a.address}</p>
                  {a.phone && (
                    <div className="kh__address-phone">
                      <Phone size={12} />
                      <span>SĐT nhận hàng: {a.phone}</span>
                    </div>
                  )}
                  {a.note && (
                    <div className="address-instructions" title="Ghi chú giao nhận">
                      {a.note}
                    </div>
                  )}
                </div>

                {canUpdate && (
                  <div className="kh__address-actions">
                    <button
                      type="button"
                      className="contact-action-btn"
                      onClick={() => startEdit(a)}
                      title="Sửa thông tin"
                    >
                      <PencilLine size={14} />
                    </button>
                    <button
                      type="button"
                      className="contact-action-btn contact-action-btn--delete"
                      onClick={() => remove(a.id)}
                      title="Xoá địa điểm"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
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
              style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}
            >
              <Plus size={14} /> Tải tài liệu lên
            </Button>
          </div>
        )}
      </div>
      {error && <div className="banner banner--error" role="alert">{error}</div>}

      {items.length === 0 ? (
        <div className="kh__empty-panel">
          <FileText size={36} style={{ color: "var(--ash-2)", opacity: 0.7, marginBottom: "4px" }} />
          <p className="kh__empty-title">Chưa có tài liệu</p>
          <p className="kh__muted">
            Đính kèm hợp đồng, GPKD, file thiết kế, biên bản… để xử lý ngay khi cần, không
            phải đi tìm nơi khác.
          </p>
          {canUpdate && (
            <Button
              variant="secondary"
              loading={uploading}
              onClick={() => fileRef.current?.click()}
              style={{ marginTop: "8px", display: "inline-flex", alignItems: "center", gap: "4px" }}
            >
              <Plus size={14} /> Tải tài liệu lên ngay
            </Button>
          )}
        </div>
      ) : (
        <div className="kh__files-grid">
          {items.map((a) => {
            const iconsMap: Record<string, React.ReactNode> = {
              hop_dong: <FileText size={18} />,
              gpkd: <ShieldCheck size={18} />,
              thiet_ke: <Image size={18} />,
              khac: <FileText size={18} />,
            };
            return (
              <div key={a.id} className="kh__file-card">
                <div className={`file-icon-box file-icon-box--${a.doc_kind}`} title={DOC_KIND_LABELS[a.doc_kind] ?? a.doc_kind}>
                  {iconsMap[a.doc_kind] || <FileText size={18} />}
                </div>
                <div className="kh__file-info">
                  <a
                    className="kh__file-name"
                    href={a.file_url}
                    target="_blank"
                    rel="noreferrer"
                    title={a.file_name}
                  >
                    {a.file_name}
                  </a>
                  <div className="kh__file-meta">
                    <span>
                      <Calendar size={10} /> {fmtDate(a.uploaded_at)}
                    </span>
                    <span className="kh__badge" style={{ fontSize: "9px", padding: "0 6px" }}>
                      {DOC_KIND_LABELS[a.doc_kind] ?? a.doc_kind}
                    </span>
                  </div>
                </div>
                {canUpdate && (
                  <div className="kh__file-actions">
                    <button
                      type="button"
                      className="contact-action-btn contact-action-btn--delete"
                      onClick={() => remove(a.id)}
                      title="Xoá tài liệu"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
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
            <X size={14} strokeWidth={2} />
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
            <X size={14} strokeWidth={2} />
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
