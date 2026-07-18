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
  type CareTask,
  type CustomerContact,
  type CustomerContactInput,
  type CustomerDashboard,
  type CustomerInput,
  type CustomerFinancialInput,
  type CustomerKind,
  type CustomerKpis,
  type CustomerNote,
  type CustomerRow,
  type DuplicateWarn,
  type FollowupRow,
  type ImportResultOut,
  type OrderHistoryRow,
  type QuoteHistoryRow,
  type ReceivableCard,
  type SaleOption,
} from "../api/client";
import type { NavigateFn } from "../components/AppShell";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { CareCalendar } from "./CareCalendar";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Select } from "../components/Select";
import {
  AlarmClock,
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
  Sparkles,
  Layers,
  Palette,
  Scissors,
  Box,
  Zap,
  CreditCard,
  Droplets,
  StickyNote,
  Pin,
} from "lucide-react";
import { MixDonut, MonthBars } from "../components/charts";
import "./khach-hang.css";


const MST_RE = /^(\d{10}|\d{13})$/;
const PAGE_SIZES = [25, 50, 100];

/* money() đầy-đủ-đồng đã bỏ: mọi chỗ hiển thị tiền dùng moneyStat/moneyCompact theo prototype.
   (Hàm cũ chỉ còn được nhắc trong khối PaymentGauge đã comment.) */
function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("vi-VN");
}
/** "HH:mm" từ ISO datetime thật (chip giờ cạnh ngày — theo prototype). */
function fmtTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Gộp giá trị theo tháng từ rows thật rồi trải trục LIÊN TỤC tối đa 12 tháng
 *  (tháng không phát sinh = 0 thật — trục không đứt quãng, như prototype). */
function monthlySeries(
  items: { created_at: string | null; total: number | null }[],
): { month: string; label: string; total: number }[] {
  const groups: Record<string, number> = {};
  items.forEach((o) => {
    if (!o.created_at) return;
    const m = o.created_at.substring(0, 7); // "YYYY-MM"
    groups[m] = (groups[m] || 0) + (o.total ?? 0);
  });
  const keys = Object.keys(groups).sort();
  if (keys.length === 0) return [];
  const first = keys[0];
  const [ly, lm] = keys[keys.length - 1].split("-").map(Number);
  const out: { month: string; label: string; total: number }[] = [];
  for (let i = 11; i >= 0; i--) {
    const d = new Date(ly, lm - 1 - i, 1);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    if (key < first) continue; // không vẽ tháng trước khi có giao dịch đầu tiên
    out.push({ month: key, label: `T${d.getMonth() + 1}`, total: groups[key] ?? 0 });
  }
  return out;
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

export const TAG_TONES = ["rust", "plum", "moss", "amber"] as const;

export function tagTone(label: string): (typeof TAG_TONES)[number] {
  let h = 0;
  for (const ch of label) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return TAG_TONES[h % TAG_TONES.length];
}

export function getKhAvatarClass(name: string): string {
  const clean = name.replace(/^(Cty|Công ty|Cafe|Cà phê|TNHH|CP)\s+/i, "").trim();
  const tones = ["rust", "plum", "moss", "amber", "steel"];
  let code = 0;
  for (let i = 0; i < clean.length; i++) {
    code = clean.charCodeAt(i) + ((code << 5) - code);
  }
  const tone = tones[Math.abs(code) % tones.length];
  return `kh__avatar--${tone}`;
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

// Form Thêm/Sửa — THÔNG TIN ĐỊNH DANH (redesign spec-06 v2). Tài chính sửa riêng ở detail.
interface FormState {
  name: string;
  customer_kind: CustomerKind;
  tax_code: string;
  email: string;
  address: string;
  sale_user_id: string;
}
const EMPTY_FORM: FormState = {
  name: "",
  customer_kind: "cong_ty",
  tax_code: "",
  email: "",
  address: "",
  sale_user_id: "",
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

// =============================================================================
// List-Report page
// =============================================================================

export function KhachHangPage({ navigate, onBadgeStale }: { navigate: NavigateFn; onBadgeStale?: () => void }) {
  const { token } = useAuth();

  const [rows, setRows] = useState<CustomerRow[]>([]);
  const [kpis, setKpis] = useState<CustomerKpis | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("code");
  const [q, setQ] = useState("");
  const [saleFilter, setSaleFilter] = useState<string>("");
  // Redesign spec-06 v2: bỏ lọc trạng thái/tier; chỉ còn lọc theo THẺ + tab "Cần theo dõi".
  const [followupFilter, setFollowupFilter] = useState<boolean>(false);
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
  const colCount = canReassign ? 7 : 6; // [checkbox] · KH · doanh số · số đơn · TB/đơn · NV · ›

  // Import / export danh bạ (#23).
  const [importOpen, setImportOpen] = useState(false);
  const [exportingBook, setExportingBook] = useState(false);

  // Panel "Cần chăm sóc" (#28): việc đến hạn/quá hạn trong scope của tôi.
  const [followups, setFollowups] = useState<FollowupRow[]>([]);
  const [followupsOpen, setFollowupsOpen] = useState(false);

  // Gợi ý chăm sóc rule-based (smart, thuần FE): khách thân thiết/đối tác mà lâu
  // không đặt hàng → nhắc hỏi thăm. Tính từ tier + last_order_at CÓ SẴN trong list.
  const [suggestions, setSuggestions] = useState<
    Array<{ customer_id: number; code: string; name: string; days: number }>
  >([]);
  const [dismissedSuggest, setDismissedSuggest] = useState<Set<number>>(new Set());
  const [suggestBusyId, setSuggestBusyId] = useState<number | null>(null);

  const loadSuggestions = useCallback(() => {
    if (!token) return;
    // Quét cả sổ trong scope (size 200 là đủ cỡ danh bạ hiện tại) — 1 call nhẹ.
    api.customers
      .list(token, { size: 200 })
      .then((res) => {
        const now = Date.now();
        const out = res.items
          // Redesign spec-06 v2: gợi ý theo LÂU CHƯA MUA thật (bỏ tier).
          .filter((c) => c.last_order_at)
          .map((c) => ({
            customer_id: c.id,
            code: c.code,
            name: c.name,
            days: Math.floor((now - new Date(c.last_order_at as string).getTime()) / 86_400_000),
          }))
          .filter((x) => x.days >= 45)
          .sort((a, b) => b.days - a.days)
          .slice(0, 5);
        setSuggestions(out);
      })
      .catch(() => setSuggestions([]));
  }, [token]);

  useEffect(() => {
    loadSuggestions();
  }, [loadSuggestions]);

  /** 1 chạm từ gợi ý: tạo luôn lịch hẹn "gọi hỏi thăm" hạn ngày mai 09:00. */
  async function suggestToTask(sg: { customer_id: number; name: string; days: number }) {
    if (!token || suggestBusyId != null) return;
    setSuggestBusyId(sg.customer_id);
    try {
      // Hẹn CUỐI GIỜ HÔM NAY: việc lập tức xuất hiện trong panel (feedback thấy ngay)
      // và đúng tinh thần gợi ý — "gọi hỏi thăm" là việc của hôm nay, không phải mai.
      await api.customers.addCareTask(token, sg.customer_id, {
        note: `Gọi hỏi thăm — ${sg.days} ngày chưa đặt lại`,
        due_date: new Date(`${dateInDays(0)}T17:00:00`).toISOString(),
      });
      setDismissedSuggest((prev) => new Set(prev).add(sg.customer_id));
      loadFollowups();
    } catch {
      /* lỗi mạng — giữ gợi ý để thử lại */
    } finally {
      setSuggestBusyId(null);
    }
  }

  const visibleSuggestions = suggestions.filter(
    (sg) =>
      !dismissedSuggest.has(sg.customer_id) &&
      // Đã có việc đến hạn cho khách này thì khỏi gợi ý thêm — tránh nhắc trùng.
      !followups.some((f) => f.customer_id === sg.customer_id),
  );

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
        followup: followupFilter || undefined,
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
  }, [token, q, saleFilter, followupFilter, tagFilter, sort, page, pageSize]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, sort, page, pageSize, saleFilter, followupFilter, tagFilter]);

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
                <strong>{total}</strong> KH &middot; <strong>{kpis.new_this_month}</strong> mới trong tháng &middot; TB đơn <strong>{moneyCompact(kpis.avg_order_value)}</strong>
              </span>
            ) : (
              "Danh bạ 360° — tìm theo thẻ gán tay, xem lịch sử mua thật & dashboard."
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

      {/* KPI header strip — ô 4 = Cần chăm sóc hôm nay (bấm xổ danh sách, hết panel riêng). */}
      <KpiStrip
        kpis={kpis}
        loading={loading && !kpis}
        careCount={followups.length}
        suggestCount={visibleSuggestions.length}
        careOpen={followupsOpen}
        onToggleCare={() => setFollowupsOpen((v) => !v)}
      />

      {/* Danh sách Cần chăm sóc — chỉ hiện khi bấm ô KPI, sát ngay dưới strip. */}
      {(followups.length > 0 || visibleSuggestions.length > 0) && followupsOpen && (
        <div className="kh__followups card">
          {(
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
              {/* Gợi ý rule-based: khách thân thiết/đối tác im ắng ≥45 ngày (tier +
                  last_order_at từ dữ liệu thật) — "Hẹn gọi" tạo việc ngày mai 1 chạm. */}
              {visibleSuggestions.map((sg) => (
                <li key={`sg-${sg.customer_id}`}>
                  <div className="kh__followups-row kh__followups-row--suggest">
                    <span className="badge-sem badge-sem--plum"><Sparkles size={11} /> Gợi ý</span>
                    <button
                      type="button"
                      className="kh__linkbtn kh__name"
                      onClick={() => setOpenId(sg.customer_id)}
                    >
                      {sg.name}
                    </button>
                    <span className="kh__mono kh__muted">{sg.code}</span>
                    <span className="kh__followups-note">{sg.days} ngày chưa đặt lại — hỏi thăm?</span>
                    <Button
                      variant="secondary"
                      loading={suggestBusyId === sg.customer_id}
                      onClick={() => suggestToTask(sg)}
                      style={{ padding: "3px 10px", fontSize: 12 }}
                    >
                      + Hẹn gọi
                    </Button>
                    <button
                      type="button"
                      className="kh__tag-x"
                      aria-label="Bỏ gợi ý này"
                      onClick={() =>
                        setDismissedSuggest((prev) => new Set(prev).add(sg.customer_id))
                      }
                    >
                      ×
                    </button>
                  </div>
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

      {/* Sub-tab: Tất cả + Cần theo dõi (redesign spec-06 v2 — bỏ tab tier). Lọc phân loại
          dùng THẺ gán tay ở dropdown "nhãn" phía trên. */}
      <div className="kh__sub-tabs">
        <button
          type="button"
          className={`kh__sub-tab kh__sub-tab--all${!followupFilter ? " is-active" : ""}`}
          onClick={() => {
            setFollowupFilter(false);
            setPage(1);
          }}
        >
          Tất cả <span className="kh__sub-tab-count">{kpis?.total_customers ?? 0}</span>
        </button>
        <button
          type="button"
          className={`kh__sub-tab kh__sub-tab--followup${followupFilter ? " is-active" : ""}`}
          onClick={() => {
            setFollowupFilter(true);
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
          ) : null}
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
                    title="Tick để chọn khách hàng — chọn xong sẽ hiện nút điều chuyển hàng loạt"
                    checked={allOnPageSelected}
                    onChange={toggleAllOnPage}
                  />
                </th>
              )}
              <th>
                <SortBtn label="Khách hàng" col="name" sort={sort} onSort={setSort} />
              </th>
              <th className="kh__num">
                <SortBtn label="Doanh số 12T" col="revenue" sort={sort} onSort={setSort} />
              </th>
              <th className="kh__num">
                <SortBtn label="Số đơn" col="orders" sort={sort} onSort={setSort} />
              </th>
              <th className="kh__num">TB / Đơn</th>
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
                  {q || tagFilter || saleFilter || followupFilter ? (
                    <>
                      <p>Không có khách hàng khớp bộ lọc.</p>
                      <button
                        type="button"
                        className="btn btn--ghost"
                        onClick={() => {
                          setQ("");
                          setTagFilter("");
                          setSaleFilter("");
                          setFollowupFilter(false);
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
                const avgOrderValue = c.orders_total > 0 ? Math.round(c.revenue_12m / c.orders_total) : 0;
                const careDue = followups.filter((f) => f.customer_id === c.id).length;

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
                        <div className={`kh__avatar ${getKhAvatarClass(c.name)}`}>{initials}</div>
                        <div className="kh__identity">
                          <span className="kh__name">{c.name}</span>
                          <span className="kh__submeta">
                            {c.tax_code && <span className="kh__mono">MST {c.tax_code}</span>}
                          </span>
                          <div className="kh__row-badges">
                            {careDue > 0 && (
                              <span
                                className="kh__row-badge kh__row-badge--care"
                                title={`${careDue} việc chăm sóc đến hạn`}
                              >
                                <AlarmClock size={10} /> {careDue}
                              </span>
                            )}
                            {/* Redesign spec-06 v2: badge = THẺ gán tay (#7), bỏ tier/mock. */}
                            {(c.tags ?? []).map((t) => (
                              <span key={t} className={`kh__row-badge kh__row-badge--tag-${tagTone(t)}`}>
                                {t}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
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
          customerId={editing.id}
          isEdit
          sales={sales}
          initial={{
            name: editing.name,
            customer_kind: editing.customer_kind,
            tax_code: editing.tax_code ?? "",
            email: editing.email ?? "",
            address: editing.address ?? "",
            sale_user_id: editing.sale_user_id != null ? String(editing.sale_user_id) : "",
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
          careDueCount={followups.filter((f) => f.customer_id === openId).length}
          onCareChanged={() => { loadFollowups(); onBadgeStale?.(); }}
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

function KpiStrip({
  kpis,
  loading,
  careCount,
  suggestCount,
  careOpen,
  onToggleCare,
}: {
  kpis: CustomerKpis | null;
  loading: boolean;
  careCount: number;
  suggestCount: number;
  careOpen: boolean;
  onToggleCare: () => void;
}) {
  // MỘT card chia 4 ngăn (mockup) — ô 4 = "Cần chăm sóc hôm nay" (như prototype),
  // bấm để xổ danh sách ngay dưới strip. Không còn panel riêng chiếm chỗ.
  const cells: { label: string; value: ReactNode; hint: string }[] = [
    { label: "Tổng khách hàng", value: kpis ? String(kpis.total_customers) : "—", hint: "trong phạm vi" },
    {
      label: "Mới trong tháng",
      value: kpis ? String(kpis.new_this_month) : "—",
      hint: "tạo tháng này",
    },
    {
      label: "TB / đơn (12T)",
      value: kpis ? moneyStat(kpis.avg_order_value) : "—",
      hint: "từ đơn thật",
    },
  ];
  const careTotal = careCount + suggestCount;
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
      <button
        type="button"
        className={`stat-strip__cell stat-strip__cell--action${careTotal > 0 ? " is-alert" : ""}`}
        onClick={onToggleCare}
        aria-expanded={careOpen}
        disabled={careTotal === 0}
      >
        <span className="stat__label">
          <AlarmClock size={10} /> Cần chăm sóc hôm nay
        </span>
        <span className="stat__value">
          {careCount}
          {suggestCount > 0 && <small> việc · {suggestCount} gợi ý</small>}
          {suggestCount === 0 && <small> việc</small>}
        </span>
        <span className="stat__hint">
          {careTotal === 0 ? "sạch sẽ — không có gì chờ" : careOpen ? "bấm để thu gọn" : "bấm để xem danh sách"}
        </span>
      </button>
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

type Tab = "dashboard" | "orders" | "quotes" | "care" | "notes" | "contacts" | "addresses" | "files" | "audit";

function CustomerObjectPage({
  customerId,
  careDueCount,
  onCareChanged,
  canPrev,
  canNext,
  onPrev,
  onNext,
  onClose,
  onEdit,
  navigate,
}: {
  customerId: number;
  careDueCount: number;
  onCareChanged?: () => void;
  canPrev: boolean;
  canNext: boolean;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
  onEdit: (row: CustomerRow) => void;
  navigate: NavigateFn;
}) {
  const { token } = useAuth();
  const canCredit = useCan()("khach_hang", "set_credit_terms");
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
            />
            <nav className="kh__so-tabs" aria-label="Nội dung">
              {(
                [
                  ["dashboard", "Dashboard", <Gauge size={14} key="i" />, null],
                  ["orders", "Lịch sử mua hàng", <ReceiptText size={14} key="i" />, dash.orders_total],
                  ["quotes", "Lịch sử báo giá", <FileText size={14} key="i" />, dash.quotes_total],
                  ["care", "Chăm sóc", <HeartHandshake size={14} key="i" />, careDueCount],
                  ["notes", "Ghi chú", <StickyNote size={14} key="i" />, null],
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
                  {count != null && count > 0 && (
                    <span className={`chip-count${key === "care" ? " chip-count--alert" : ""}`}>{count}</span>
                  )}
                </button>
              ))}
            </nav>

            <div className="kh__so-body">
              {tab === "dashboard" && (
                <DashboardTab
                  dash={dash}
                  receivable={receivable}
                  customer={customer}
                  canCredit={canCredit}
                  onCustomerUpdated={setCustomer}
                />
              )}
              {tab === "orders" && (
                <OrdersTab customerId={customerId} code={customer.code} />
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
              {tab === "care" && <CareTab customerId={customerId} onCareChanged={onCareChanged} />}
              {tab === "notes" && <NotesTab customerId={customerId} />}
              {tab === "contacts" && <ContactsTab customerId={customerId} />}
              {tab === "addresses" && <AddressesTab customerId={customerId} />}
              {tab === "files" && <AttachmentsTab customerId={customerId} />}
              {tab === "audit" && (
                <AuditTab
                  customerId={customerId}
                  onDrill={(_refType, id) => {
                    onClose();
                    navigate("bao-gia", { openQuoteId: id });
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
}: {
  customer: CustomerRow;
  dash: CustomerDashboard;
  onEdit: () => void;
}) {
  // const canDebt = useCan()("khach_hang", "view_debt");
  // const rec = dash.receivable;
  // // Gauge uy tín thanh toán: chỉ khi Công nợ sẵn sàng; nếu không → seam trung thực.
  // const usage = rec.available && rec.usage_pct != null ? rec.usage_pct : null;

  return (
    <header className="kh__so-head">
      <div className="kh__so-headmain">
        <div className="kh__so-title-row">
          {/* Redesign spec-06 v2: bỏ tier/★; nhãn = Loại KH. Phân loại chăm sóc = THẺ (dưới). */}
          <span className="kh__so-badge-tier">
            {customer.customer_kind === "ca_nhan" ? "CÁ NHÂN" : "CÔNG TY"}
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
  customer,
  canCredit,
  onCustomerUpdated,
}: {
  dash: CustomerDashboard;
  receivable: ReceivableCard | undefined;
  customer: CustomerRow;
  canCredit: boolean;
  onCustomerUpdated: (c: CustomerRow) => void;
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
    // Không có dữ liệu 24 tháng để so YoY thật → hint trung thực về phạm vi số liệu.
    { label: "Doanh số 12T", value: moneyStat(dash.revenue_12m), hint: "12 tháng gần nhất" },
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
            <h3><Package size={14} /> Cơ cấu sản phẩm</h3>
          </div>
          <ProductDonut mix={dash.product_mix} />
        </section>

        {/* Thông số in thường đặt */}
        <section className="card kh__chart">
          <div className="kh__chart-head">
            <h3><Droplets size={14} /> Thông số in thường đặt</h3>
            <span className="kh__muted-tag">KỸ THUẬT</span>
          </div>
          <div className="kh__specs-list">
            {[
              { ic: <Layers size={13} />, label: "Giấy ưa thích", val: "Couche 200gsm", pct: 85 },
              { ic: <Palette size={13} />, label: "Số màu TB", val: "5 màu (CMYK+Pantone)", pct: 70 },
              { ic: <Scissors size={13} />, label: "Gia công", val: "Cán bóng · Đóng keo", pct: 65 },
              { ic: <Box size={13} />, label: "Khổ phổ biến", val: "A4 / A5", pct: 90 },
              { ic: <Zap size={13} />, label: "Độ phủ mực TB", val: "Cao (50–60%)", pct: 55 },
            ].map((row) => (
              <div className="kh__spec-item" key={row.label}>
                <span className="kh__spec-ic" aria-hidden="true">{row.ic}</span>
                <div className="kh__spec-text">
                  <span className="kh__spec-label">{row.label}</span>
                  <span className="kh__spec-val">{row.val}</span>
                </div>
                <div className="kh__progress-bar"><div className="kh__progress-fill" style={{ width: `${row.pct}%` }}></div></div>
              </div>
            ))}
          </div>
        </section>

        {/* Chính sách tài chính (redesign spec-06 v2) — thay widget "Thanh toán" fake. */}
        <FinancialPolicyCard
          customer={customer}
          canEdit={canCredit}
          onSaved={onCustomerUpdated}
        />
      </div>
    </div>
  );
}

// --- Chính sách tài chính (inline view/edit, redesign spec-06 v2) -------------
// Điều khoản thanh toán đã BỎ theo yêu cầu — chỉ còn Hạn mức + rào Chiết khấu/Biên.

function rangeText(min?: number | null, max?: number | null): string {
  if (min == null && max == null) return "Chưa đặt";
  if (min != null && max != null) return `${min}% – ${max}%`;
  if (min != null) return `≥ ${min}%`;
  return `≤ ${max}%`;
}

function FinancialPolicyCard({
  customer,
  canEdit,
  onSaved,
}: {
  customer: CustomerRow;
  canEdit: boolean;
  onSaved: (c: CustomerRow) => void;
}) {
  const { token } = useAuth();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [f, setF] = useState({
    credit_limit: "0",
    payment_term_days: "",
    discount_min_pct: "",
    discount_max_pct: "",
    margin_min_pct: "",
    margin_max_pct: "",
  });

  function openEdit() {
    const numStr = (n?: number | null) => (n != null ? String(n) : "");
    setF({
      credit_limit: String(customer.credit_limit ?? 0),
      payment_term_days: numStr(customer.payment_term_days),
      discount_min_pct: numStr(customer.discount_min_pct),
      discount_max_pct: numStr(customer.discount_max_pct),
      margin_min_pct: numStr(customer.margin_min_pct),
      margin_max_pct: numStr(customer.margin_max_pct),
    });
    setErr(null);
    setEditing(true);
  }

  async function save() {
    if (!token || saving) return;
    setSaving(true);
    setErr(null);
    const numOrNull = (s: string) => (s.trim() === "" ? null : Number(s));
    const daysOrNull = (s: string) =>
      s.trim() === "" ? null : Math.max(0, Math.floor(Number(s) || 0));
    const input: CustomerFinancialInput = {
      credit_limit: Number(f.credit_limit) || 0,
      payment_term_days: daysOrNull(f.payment_term_days),
      discount_min_pct: numOrNull(f.discount_min_pct),
      discount_max_pct: numOrNull(f.discount_max_pct),
      margin_min_pct: numOrNull(f.margin_min_pct),
      margin_max_pct: numOrNull(f.margin_max_pct),
    };
    try {
      const res = await api.customers.updateFinancial(token, customer.id, input);
      onSaved(res.customer);
      setEditing(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) setErr(e.message);
      else if (e instanceof ApiError && e.isForbidden) setErr("Bạn không có quyền sửa chính sách tài chính.");
      else setErr("Lưu không thành công. Thử lại.");
    } finally {
      setSaving(false);
    }
  }

  const set = (k: keyof typeof f, v: string) => setF((s) => ({ ...s, [k]: v }));

  return (
    <section className="card kh__chart kh__finpolicy">
      <div className="kh__chart-head">
        <h3><CreditCard size={14} /> Chính sách tài chính</h3>
        {canEdit && !editing && (
          <button type="button" className="kh__fin-edit-btn" onClick={openEdit}>
            <PencilLine size={13} strokeWidth={2} /> Sửa
          </button>
        )}
      </div>

      {!editing ? (
        <div className="kh__finpolicy-view">
          <div className="kh__fin-row">
            <span className="kh__fin-label">Hạn mức công nợ</span>
            <strong className="kh__mono">{moneyStat(customer.credit_limit)}</strong>
          </div>
          <div className="kh__fin-row">
            <span className="kh__fin-label">Số ngày công nợ tối đa</span>
            <span>
              {customer.payment_term_days != null
                ? `${customer.payment_term_days} ngày kể từ ngày xuất HĐ`
                : "Chưa đặt"}
            </span>
          </div>
          <div className="kh__fin-row">
            <span className="kh__fin-label">Chiết khấu cho phép</span>
            <span>{rangeText(customer.discount_min_pct, customer.discount_max_pct)}</span>
          </div>
          <div className="kh__fin-row">
            <span className="kh__fin-label">Biên lợi nhuận</span>
            <span>{rangeText(customer.margin_min_pct, customer.margin_max_pct)}</span>
          </div>
          {!canEdit && (
            <p className="kh__lock-note">Cần quyền “Thiết lập chính sách tài chính” để sửa.</p>
          )}
        </div>
      ) : (
        <div className="kh__finpolicy-edit">
          <label className="field">
            <span className="field__label">Hạn mức công nợ (VND)</span>
            <input className="input" type="number" min={0} value={f.credit_limit}
              onChange={(e) => set("credit_limit", e.target.value)} />
          </label>
          <label className="field">
            <span className="field__label">Số ngày công nợ tối đa</span>
            <input className="input" type="number" min={0} step={1} placeholder="Kể từ ngày xuất HĐ"
              value={f.payment_term_days}
              onChange={(e) => set("payment_term_days", e.target.value)} />
          </label>
          <div className="kh__fin-bounds">
            <label className="field">
              <span className="field__label">CK tối thiểu (%)</span>
              <input className="input" type="number" min={0} max={100} value={f.discount_min_pct}
                onChange={(e) => set("discount_min_pct", e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">CK tối đa (%)</span>
              <input className="input" type="number" min={0} max={100} value={f.discount_max_pct}
                onChange={(e) => set("discount_max_pct", e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Biên tối thiểu (%)</span>
              <input className="input" type="number" min={0} max={100} value={f.margin_min_pct}
                onChange={(e) => set("margin_min_pct", e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Biên tối đa (%)</span>
              <input className="input" type="number" min={0} max={100} value={f.margin_max_pct}
                onChange={(e) => set("margin_max_pct", e.target.value)} />
            </label>
          </div>
          {err && <p className="kh__err" role="alert">{err}</p>}
          <div className="kh__fin-actions">
            <Button type="button" variant="ghost" onClick={() => setEditing(false)}>Huỷ</Button>
            <Button type="button" variant="primary" loading={saving} onClick={save}>Lưu</Button>
          </div>
        </div>
      )}
    </section>
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
      centerBottom="SP"
      formatValue={moneyCompact}
      height={170}
      stacked
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
}: {
  customerId: number;
  code: string;
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

  // Năm có dữ liệu THẬT (từ created_at) — không hardcode danh sách năm.
  const years = useMemo(() => {
    if (!rows) return [];
    return [...new Set(rows.map((o) => o.created_at?.slice(0, 4)).filter(Boolean))]
      .sort()
      .reverse() as string[];
  }, [rows]);

  // Memoized filter and aggregates
  const filteredRows = useMemo(() => {
    if (!rows) return [];
    if (!yearFilter) return rows;
    return rows.filter((o) => o.created_at && o.created_at.startsWith(yearFilter));
  }, [rows, yearFilter]);

  const { totalLifetime, completedCount, avgSpend, maxSpend, perMonth, sinceDate } = useMemo(() => {
    if (filteredRows.length === 0) {
      return { totalLifetime: 0, completedCount: 0, avgSpend: 0, maxSpend: 0, perMonth: 0, sinceDate: null as string | null };
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
    // Nhịp đặt/tháng tính trên KHOẢNG THỜI GIAN THẬT của dữ liệu (đơn cũ nhất → mới nhất),
    // không chia bừa cho 12.
    const dates = filteredRows.map((o) => new Date(o.created_at).getTime()).filter((t) => !Number.isNaN(t));
    const oldest = Math.min(...dates);
    const newest = Math.max(...dates);
    const spanMonths = Math.max(1, Math.round((newest - oldest) / (30.44 * 86_400_000)) + 1);
    return {
      totalLifetime: total,
      completedCount: completed,
      avgSpend: completed > 0 ? Math.round(total / completed) : 0,
      maxSpend: max,
      perMonth: completed / spanMonths,
      sinceDate: new Date(oldest).toISOString(),
    };
  }, [filteredRows]);

  // So sánh THẬT với năm liền trước (chỉ khi đang lọc 1 năm và năm trước có dữ liệu).
  const yoyPct = useMemo(() => {
    if (!rows || !yearFilter) return null;
    const prevYear = String(Number(yearFilter) - 1);
    const sum = (yr: string) =>
      rows.filter((o) => o.created_at?.startsWith(yr)).reduce((s, o) => s + (o.total ?? 0), 0);
    const prev = sum(prevYear);
    if (prev <= 0) return null;
    return Math.round(((sum(yearFilter) - prev) / prev) * 100);
  }, [rows, yearFilter]);

  // Group by month for chart — trục liên tục tối đa 12 tháng như prototype.
  const monthlySpend = useMemo(() => monthlySeries(filteredRows), [filteredRows]);

  // Top products mix — TOP 4 như prototype; chỉ số ĐO ĐƯỢC từ rows thật (số đơn + giá trị).
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
      .sort((a, b) => b.total - a.total)
      .slice(0, 4);
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
          {["", ...years].map((yr) => (
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

      {/* Stats Cards Strip — hint là số THẬT tính từ rows (YoY chỉ hiện khi có kỳ trước). */}
      <div className="kh__kpis kh__kpis--orders">
        <div className="kh__kpi card">
          <span className="kh__kpi-label">{yearFilter ? `CHI TIÊU ${yearFilter}` : "TỔNG CHI TIÊU LIFETIME"}</span>
          <span className="kh__kpi-value">{moneyStat(totalLifetime)}</span>
          <span className="kh__kpi-hint">
            {yoyPct != null
              ? `${yoyPct >= 0 ? "+" : ""}${yoyPct}% so với ${Number(yearFilter) - 1}`
              : sinceDate
                ? `từ ${fmtDate(sinceDate)}`
                : "—"}
          </span>
        </div>
        <div className="kh__kpi card">
          <span className="kh__kpi-label">SỐ ĐƠN HOÀN THÀNH</span>
          <span className="kh__kpi-value">
            {completedCount} <small>đơn</small>
          </span>
          <span className="kh__kpi-hint">{perMonth.toFixed(1)}/tháng TB</span>
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
            <span className="kh__chart-unit">TRIỆU đ</span>
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

        {/* Right Column: TOP Sản phẩm mua nhiều nhất — chỉ số thật (số đơn + giá trị). */}
        <section className="card kh__chart kh__chart--orders-top">
          <div className="kh__chart-head">
            <h3>Sản phẩm mua nhiều nhất</h3>
            <span className="kh__muted-tag">TOP {Math.max(productMix.length, 1)}</span>
          </div>
          <ul className="kh__top-products-list">
            {productMix.map((p, idx) => (
              <li key={p.name} className="kh__top-product-item">
                <span className="kh__top-rank">{String(idx + 1).padStart(2, "0")}</span>
                <div className="kh__top-prod-info">
                  <span className="kh__top-prod-name">{p.name}</span>
                  <span className="kh__top-prod-qty">{p.qty} đơn</span>
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

      {/* Order List Table — chỉ cột có dữ liệu THẬT (bỏ SL / NV tạo / hạn giao / %TT của mẫu). */}
      <div className="card kh__tablewrap kh__tablewrap--orders">
        <div className="kh__sec-head">
          <h3>Toàn bộ đơn hàng</h3>
          <span className="kh__sec-count">{filteredRows.length} ĐƠN</span>
          <span className="kh__sec-right">Mới nhất trước</span>
        </div>
        <table className="kh__table kh__table--tight kh__table--drill">
          <thead>
            <tr>
              <th>Mã đơn · Ngày đặt</th>
              <th>Sản phẩm</th>
              <th className="kh__num">Giá trị</th>
              <th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((o) => (
              <tr key={o.id}>
                <td>
                  <div className="kh__order-code-cell">
                    <span className="kh__mono">{o.order_no}</span>
                    <span className="kh__order-code-sub">
                      <span className="kh__mono kh__muted">{fmtDate(o.created_at)}</span>
                      {fmtTime(o.created_at) && (
                        <span className="kh__time-chip">{fmtTime(o.created_at)}</span>
                      )}
                    </span>
                  </div>
                </td>
                <td>
                  <div className="kh__order-prod-cell">
                    <span className="kh__order-summary-text">{o.summary}</span>
                    {o.order_kind === "bo_sung" && (
                      <span className="kh__order-prod-sub">Đơn bổ sung (giữ kẽm cũ)</span>
                    )}
                  </div>
                </td>
                <td className="kh__num kh__money">{moneyStat(o.total)}</td>
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
  const [yearFilter, setYearFilter] = useState<string>("");

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

  // Năm có dữ liệu thật — cùng cơ chế với tab mua hàng.
  const years = useMemo(() => {
    if (!rows) return [];
    return [...new Set(rows.map((q) => q.created_at?.slice(0, 4)).filter(Boolean))]
      .sort()
      .reverse() as string[];
  }, [rows]);

  const filteredRows = useMemo(() => {
    if (!rows) return [];
    if (!yearFilter) return rows;
    return rows.filter((q) => q.created_at && q.created_at.startsWith(yearFilter));
  }, [rows, yearFilter]);

  // Giá trị báo giá theo tháng — TÍNH THẬT từ created_at/total, trục liên tục ≤12 tháng.
  const monthlyQuoted = useMemo(() => monthlySeries(filteredRows), [filteredRows]);

  // Cơ cấu trạng thái — đếm + cộng giá trị thật theo status (thay cột TOP sản phẩm
  // của mẫu: BE lịch sử BG không trả summary sản phẩm nên không bịa được).
  const statusMix = useMemo(() => {
    const groups: Record<string, { count: number; total: number }> = {};
    filteredRows.forEach((q) => {
      if (!groups[q.status]) groups[q.status] = { count: 0, total: 0 };
      groups[q.status].count += 1;
      groups[q.status].total += q.total ?? 0;
    });
    return Object.entries(groups)
      .map(([status, stat]) => ({ status, ...stat }))
      .sort((a, b) => b.count - a.count);
  }, [filteredRows]);

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
  const totalQuoted = filteredRows.reduce((s, q) => s + (q.total ?? 0), 0);
  const won = filteredRows.filter((q) => q.status === "approved" || q.status === "accepted");
  const winRate = filteredRows.length > 0 ? Math.round((won.length / filteredRows.length) * 100) : 0;
  const wonValue = won.reduce((s, q) => s + (q.total ?? 0), 0);

  return (
    <div className="kh__histwrap">
      {/* Hàng lọc năm — cùng nhịp với tab mua hàng (mẫu). Không có nút Xuất Excel:
          BE chưa có endpoint export báo giá. */}
      <div className="kh__orders-filter-row">
        <div className="kh__year-filters">
          <span className="kh__year-filters-label">LỌC THEO NĂM:</span>
          {["", ...years].map((yr) => (
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
      </div>

      <div className="kh__kpis kh__kpis--orders">
        <div className="kh__kpi card">
          <span className="kh__kpi-label">{yearFilter ? `SỐ BÁO GIÁ ${yearFilter}` : "SỐ BÁO GIÁ LIFETIME"}</span>
          <span className="kh__kpi-value">
            {filteredRows.length} <small>BG</small>
          </span>
          <span className="kh__kpi-hint">Tổng GT báo giá {moneyCompact(totalQuoted)}</span>
        </div>
        <div className="kh__kpi card">
          <span className="kh__kpi-label">TỈ LỆ CHỐT</span>
          <span className="kh__kpi-value">
            {winRate} <small>%</small>
          </span>
          <span className="kh__kpi-hint">{won.length}/{filteredRows.length} BG chốt hoặc duyệt</span>
        </div>
        <div className="kh__kpi card">
          <span className="kh__kpi-label">GIÁ TRỊ ĐÃ CHỐT</span>
          <span className="kh__kpi-value">{moneyStat(wonValue)}</span>
          <span className="kh__kpi-hint">
            {won.length > 0 ? `TB ${moneyCompact(Math.round(wonValue / won.length))} / BG thắng` : "Chưa có BG thắng"}
          </span>
        </div>
      </div>

      {/* 2 cột: chart giá trị BG theo tháng + cơ cấu trạng thái (số thật). */}
      <div className="kh__orders-analysis-row">
        <section className="card kh__chart kh__chart--orders-monthly">
          <div className="kh__chart-head">
            <h3>Giá trị báo giá theo tháng</h3>
            <span className="kh__chart-unit">TRIỆU đ</span>
          </div>
          {monthlyQuoted.length === 0 ? (
            <span className="kh__muted kh__empty-chart-text">Chưa có dữ liệu tháng</span>
          ) : (
            <MonthBars
              data={monthlyQuoted.map((m) => ({ label: m.label, value: m.total }))}
              formatValue={moneyCompact}
              formatAxis={(v) => String(Math.round(v / 1_000_000))}
            />
          )}
        </section>

        <section className="card kh__chart kh__chart--orders-top">
          <div className="kh__chart-head">
            <h3>Cơ cấu trạng thái</h3>
            <span className="kh__muted-tag">{filteredRows.length} BG</span>
          </div>
          <ul className="kh__top-products-list">
            {statusMix.map((s) => (
              <li key={s.status} className="kh__top-product-item">
                <span className={`kh__ostat kh__ostat--${s.status}`}>
                  {QUOTE_STATUS_LABELS[s.status] ?? s.status}
                </span>
                <div className="kh__top-prod-info">
                  <span className="kh__top-prod-qty">{s.count} báo giá</span>
                </div>
                <span className="kh__top-prod-total">{moneyCompact(s.total)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {/* Bảng toàn bộ báo giá — bỏ cột SL / NV tạo / Đơn của mẫu (BE không trả các field đó). */}
      <div className="card kh__tablewrap kh__tablewrap--orders">
        <div className="kh__sec-head">
          <h3>Toàn bộ báo giá</h3>
          <span className="kh__sec-count">{filteredRows.length} BG</span>
          <span className="kh__sec-right">Mới nhất trước</span>
        </div>
        <table className="kh__table kh__table--tight kh__table--drill">
          <thead>
            <tr>
              <th>Mã BG · Ngày tạo</th>
              <th className="kh__num">Giá trị</th>
              <th>Hiệu lực đến</th>
              <th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((q) => (
              <tr
                key={q.id}
                className="kh__drillrow"
                onClick={() => onOpenQuote(q.id)}
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && onOpenQuote(q.id)}
                title={`Mở chi tiết báo giá ${q.code}`}
              >
                <td>
                  <div className="kh__order-code-cell">
                    <span className="kh__link kh__mono">
                      {q.code}
                      <span className="kh__muted"> v{q.version}</span>
                    </span>
                    <span className="kh__order-code-sub">
                      <span className="kh__mono kh__muted">{fmtDate(q.created_at)}</span>
                      {fmtTime(q.created_at) && (
                        <span className="kh__time-chip">{fmtTime(q.created_at)}</span>
                      )}
                    </span>
                  </div>
                </td>
                <td className="kh__num kh__money">{moneyStat(q.total)}</td>
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
    </div>
  );
}

// --- Nhật ký tab (unified activity timeline, real events) --------------------

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // "HH:mm dd/MM/yyyy" — gọn kiểu Việt Nam, bỏ giây (toLocaleString vi-VN trả "05:02:50 10/7/2026").
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())} ${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
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
          // Đơn hàng bán đã gỡ → chỉ báo giá còn mở được chi tiết (order-ref hiển thị nhưng không dẫn đi đâu).
          const drillable = r.ref_type === "quotation" && r.ref_id != null;
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

// --- Ghi chú tab (lưu ý tự do của team về khách; ghim + sửa/xóa) ---------------

function NotesTab({ customerId }: { customerId: number }) {
  const { token } = useAuth();
  const canUpdate = useCan()("khach_hang", "update");
  const [notes, setNotes] = useState<CustomerNote[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [editBody, setEditBody] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const reload = useCallback(() => {
    if (!token) return;
    api.customers
      .notes(token, customerId)
      .then((r) => setNotes(r.items))
      .catch(() => setError("Không tải được ghi chú."));
  }, [token, customerId]);

  useEffect(() => {
    setNotes(null);
    setError(null);
    reload();
  }, [reload]);

  async function add() {
    if (!token || busy || !draft.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.customers.addNote(token, customerId, draft.trim());
      setDraft("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Thêm ghi chú không thành công.");
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(n: CustomerNote) {
    if (!token || !editBody.trim()) return;
    try {
      await api.customers.updateNote(token, customerId, n.id, { body: editBody.trim() });
      setEditId(null);
      setEditBody("");
      reload();
    } catch {
      setError("Lưu ghi chú không thành công.");
    }
  }

  async function togglePin(n: CustomerNote) {
    if (!token) return;
    try {
      await api.customers.updateNote(token, customerId, n.id, { pinned: !n.pinned });
      reload();
    } catch {
      setError("Cập nhật ghim không thành công.");
    }
  }

  async function remove(n: CustomerNote) {
    if (!token) return;
    try {
      await api.customers.deleteNote(token, customerId, n.id);
      setConfirmDeleteId(null);
      reload();
    } catch {
      setError("Xóa ghi chú không thành công.");
    }
  }

  if (notes === null) return <p className="kh__muted">Đang tải…</p>;

  return (
    <div className="kh__notes">
      {canUpdate && (
        <div className="kh__note-composer">
          <div className="kh__note-composer-card">
            <textarea
              className="kh__note-input"
              rows={2}
              placeholder="Thêm ghi chú về khách (vd: thích giao buổi sáng, chốt qua Zalo nhanh nhất, hay trả trễ…)"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") add();
              }}
            />
            <div className="kh__note-composer-toolbar">
              <span className="kh__note-hint">⌘/Ctrl + Enter để lưu nhanh</span>
              <Button
                type="button"
                variant="primary"
                loading={busy}
                disabled={!draft.trim()}
                onClick={add}
              >
                <Plus size={14} /> Thêm ghi chú
              </Button>
            </div>
          </div>
        </div>
      )}

      {error && (
        <p className="kh__err" role="alert">
          {error}
        </p>
      )}

      {notes.length === 0 ? (
        <div className="kh__note-empty-container">
          <div className="kh__note-empty-icon">
            <StickyNote size={40} strokeWidth={1.5} />
          </div>
          <h3 className="kh__note-empty-title">Chưa có ghi chú nào</h3>
          <p className="kh__note-empty-desc">
            {canUpdate
              ? "Thêm ghi chú đầu tiên ở trên để lưu trữ các thông tin liên lạc, sở thích hoặc lưu ý quan trọng về khách hàng này."
              : "Chưa có lưu ý nào được ghi nhận cho khách hàng này."}
          </p>
        </div>
      ) : (
        <ul className="kh__note-list">
          {notes.map((n) => (
            <li key={n.id} className={`kh__note${n.pinned ? " is-pinned" : ""}`}>
              {editId === n.id ? (
                <div className="kh__note-edit">
                  <textarea
                    className="input"
                    rows={3}
                    value={editBody}
                    onChange={(e) => setEditBody(e.target.value)}
                  />
                  <div className="kh__note-edit-actions">
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => {
                        setEditId(null);
                        setEditBody("");
                      }}
                    >
                      Huỷ
                    </Button>
                    <Button
                      type="button"
                      variant="primary"
                      disabled={!editBody.trim()}
                      onClick={() => saveEdit(n)}
                    >
                      Lưu
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="kh__note-header">
                    <div className="kh__note-author-info">
                      <div className="kh__note-avatar">
                        {n.author_name ? getInitials(n.author_name) : "?"}
                      </div>
                      <span className="kh__note-author-name">{n.author_name || "—"}</span>
                      <span className="kh__note-dot">•</span>
                      <span className="kh__note-time" title={fmtDateTime(n.created_at)}>
                        {fmtDateTime(n.created_at)}
                      </span>
                      {n.edited && n.updated_at && (
                        <>
                          <span className="kh__note-dot">•</span>
                          <span className="kh__note-edited" title={`Đã sửa ${fmtDateTime(n.updated_at)}`}>
                            đã sửa
                          </span>
                        </>
                      )}
                    </div>
                    {canUpdate && confirmDeleteId !== n.id && (
                      <span className="kh__note-actions">
                        <button
                          type="button"
                          className={`kh__note-act${n.pinned ? " is-on" : ""}`}
                          title={n.pinned ? "Bỏ ghim" : "Ghim lên đầu"}
                          onClick={() => togglePin(n)}
                        >
                          <Pin size={13} />
                        </button>
                        <button
                          type="button"
                          className="kh__note-act"
                          title="Sửa"
                          onClick={() => {
                            setEditId(n.id);
                            setEditBody(n.body);
                          }}
                        >
                          <PencilLine size={13} />
                        </button>
                        <button
                          type="button"
                          className="kh__note-act kh__note-act--danger"
                          title="Xóa"
                          onClick={() => setConfirmDeleteId(n.id)}
                        >
                          <Trash2 size={13} />
                        </button>
                      </span>
                    )}
                  </div>
                  <div className="kh__note-body">
                    {n.pinned && <Pin size={12} className="kh__note-pin-ic" />}
                    <span>{n.body}</span>
                  </div>
                  {confirmDeleteId === n.id && (
                    <div className="kh__note-delete-confirm">
                      <span className="kh__note-delete-confirm-msg">Xác nhận xóa ghi chú này?</span>
                      <div className="kh__note-delete-confirm-actions">
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => setConfirmDeleteId(null)}
                        >
                          Hủy
                        </Button>
                        <Button
                          type="button"
                          variant="danger"
                          onClick={() => remove(n)}
                        >
                          Xác nhận
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --- Chăm sóc tab (#20/#27/#28: nhật ký + lịch hẹn follow-up, nhắc 1-2-3) ------

function RemindBadge({ level, days }: { level: number; days: number }) {
  // Mức nhắc TÍNH từ số ngày quá hạn (BE trả sẵn) — badge semantic theo token:
  // lần 1 = amber, lần 2 = rust, lần 3 = signal (nặng nhất), chưa đến hạn = moss.
  if (level <= 0) {
    return (
      <span className="badge-sem badge-sem--moss">
        <CheckCircle2 size={11} /> Chưa đến hạn
      </span>
    );
  }
  const cls = level >= 3 ? "badge-sem--signal" : level === 2 ? "badge-sem--rust" : "badge-sem--amber";
  const icon = level >= 3 ? <AlertTriangle size={11} /> : <Clock size={11} />;
  return (
    <span className={`badge-sem ${cls}`} title={days > 0 ? `Quá hạn ${days} ngày` : "Đến hạn hôm nay"}>
      {icon} Nhắc lần {level}{days > 0 ? ` (${days} ngày)` : ""}
    </span>
  );
}

/** yyyy-mm-dd của (hôm nay + n ngày) theo giờ máy — cho chip ngày nhanh. */
function dateInDays(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}


function CareTab({ customerId, onCareChanged }: { customerId: number; onCareChanged?: () => void }) {
  const { token } = useAuth();
  const canUpdate = useCan()("khach_hang", "update");
  const [tasks, setTasks] = useState<CareTask[] | null>(null);
  // Đánh giá chăm sóc (#28): xong đúng hạn / xong trễ / đang quá hạn — BE trả sẵn.
  const [taskStats, setTaskStats] = useState<{ done_on_time: number; done_late: number; overdue_open: number } | null>(null);

  const [error, setError] = useState<string | null>(null);

  // Timeline: mặc định ẨN việc đã huỷ (giảm nhiễu — xem lại được bằng toggle).
  const [showCancelled, setShowCancelled] = useState(false);
  // Chống "cuộn vô hạn": mặc định 6 mục mới nhất, bấm mới xem thêm.
  const [showAllHistory, setShowAllHistory] = useState(false);

  const reload = useCallback(() => {
    if (!token) return;
    api.customers.careTasks(token, customerId)
      .then((t) => {
        setTasks(t.items);
        setTaskStats({ done_on_time: t.done_on_time, done_late: t.done_late, overdue_open: t.overdue_open });
      })
      .catch(() => setError("Không tải được dữ liệu chăm sóc."));
  }, [token, customerId]);

  useEffect(() => {
    setTasks(null);
    setError(null);
    reload();
  }, [reload]);

  async function setTaskStatus(t: CareTask, status: string) {
    if (!token) return;
    try {
      await api.customers.setCareTaskStatus(token, customerId, t.id, { status });
      reload();
    } catch {
      setError("Cập nhật việc không thành công.");
    }
  }

  const historyItems = useMemo(() => {
    const list: Array<{
      id: string;
      date: Date;
      kind: string;
      title: string;
      detail: string;
      actor: string | null;
      badgeText: string;
      type: "event" | "task";
      rawTask?: CareTask;
    }> = [];

    if (tasks) {
      const closed = tasks.filter((t) => t.status !== "open");
      closed.forEach((t) => {
        list.push({
          id: `task-${t.id}`,
          // Việc huỷ không có mốc huỷ từ BE (cancelled_at) — chặn trên bằng "bây giờ"
          // để việc huỷ có hạn TƯƠNG LAI không ghim đầu timeline (bug sort cũ).
          date: t.done_at
            ? new Date(t.done_at)
            : new Date(Math.min(new Date(t.due_date).getTime(), Date.now())),
          kind: t.status === "done" ? "done_task" : "cancelled_task",
          title: t.status === "done" ? `Hoàn thành lịch hẹn: ${t.note}` : `Huỷ lịch hẹn: ${t.note}`,
          detail: t.note,
          actor: t.assignee_name,
          badgeText: t.status === "done" ? "Đã xong" : "Đã huỷ",
          type: "task",
          rawTask: t,
        });
      });
    }

    return list.sort((a, b) => b.date.getTime() - a.date.getTime());
  }, [tasks]);

  const cancelledCount = historyItems.filter((i) => i.kind === "cancelled_task").length;
  const visibleHistory = showCancelled
    ? historyItems
    : historyItems.filter((i) => i.kind !== "cancelled_task");
  const shownHistory = showAllHistory ? visibleHistory : visibleHistory.slice(0, 6);

  if (error && tasks == null) return <div className="banner banner--error" role="alert">{error}</div>;
  if (tasks == null) return <TableSkeleton cols={3} />;

  return (
    <div className="kh__care">
      {error && <div className="banner banner--error" role="alert">{error}</div>}

      {/* Lịch hẹn chăm sóc kiểu calendar (redesign-lich-hen-cham-soc) — lặp + bung tương lai. */}
      <CareCalendar customerId={customerId} onChange={() => { reload(); onCareChanged?.(); }} />

      {/* Đánh giá chăm sóc (#28) — một dòng gọn, ẩn khi chưa có gì đáng nói. */}
      {taskStats && taskStats.done_on_time + taskStats.done_late + taskStats.overdue_open > 0 && (
        <div className="care-eval-line">
          <span className="stat__label">Đánh giá</span>
          <span className="care-eval-item care-eval-item--good">
            <CheckCircle2 size={12} /> {taskStats.done_on_time} đúng hạn
          </span>
          <span className="care-eval-item care-eval-item--mid">
            <Clock size={12} /> {taskStats.done_late} trễ
          </span>
          <span className="care-eval-item care-eval-item--bad">
            <AlertTriangle size={12} /> {taskStats.overdue_open} đang quá hạn
          </span>
        </div>
      )}

      {/* Nhật ký hoạt động — các hẹn ĐÃ XONG / đã huỷ (máy tự ghi nhận khi tick trên lịch). */}
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <div className="timeline-section-title">
            <History size={12} /> Nhật ký hoạt động ({visibleHistory.length})
            {cancelledCount > 0 && (
              <button
                type="button"
                className="kh__linkbtn"
                style={{ marginLeft: "auto", fontSize: 11 }}
                onClick={() => setShowCancelled((v) => !v)}
              >
                {showCancelled ? "Ẩn đã huỷ" : `Hiện đã huỷ (${cancelledCount})`}
              </button>
            )}
          </div>

          {visibleHistory.length === 0 ? (
            <p className="kh__muted kh__chart-empty" style={{ background: "var(--canvas)", border: "1px solid var(--rule-soft)", borderRadius: "var(--r-5)", padding: "var(--sp-6)", textAlign: "center" }}>
              Chưa có hoạt động nào — đặt hẹn ở lịch trên, tick tròn khi làm xong để lưu lịch sử.
            </p>
          ) : (
            <div className="care-timeline">
              {shownHistory.map((item) => {
                const iconsMap: Record<string, React.ReactNode> = {
                  goi_dien: <Phone size={10} />,
                  nhan_tin: <MessageCircle size={10} />,
                  email: <Mail size={10} />,
                  gap_truc_tiep: <HeartHandshake size={10} />,
                  khac: <FileText size={10} />,
                  done_task: <Check size={10} />,
                  cancelled_task: <X size={10} />,
                };
                
                const iconClass = item.kind === "done_task"
                  ? "timeline-icon--done"
                  : item.kind === "cancelled_task"
                    ? "timeline-icon--cancelled"
                    : `timeline-icon--${item.kind}`;

                return (
                  <div key={item.id} className="timeline-item">
                    <div className={`timeline-icon ${iconClass}`} title={item.badgeText}>
                      {iconsMap[item.kind] || <FileText size={10} />}
                    </div>
                    <div className="timeline-card">
                      <p style={{ textDecoration: item.kind === "cancelled_task" ? "line-through" : "none", opacity: item.kind === "cancelled_task" ? 0.6 : 1, margin: 0 }}>
                        {item.type === "task" ? item.title : item.detail}
                      </p>
                      <div className="timeline-meta">
                        <span>
                          <Clock size={11} /> {fmtDateTime(item.date.toISOString())}
                        </span>
                        {item.actor && (
                          <span>
                            <User size={11} /> {item.actor}
                          </span>
                        )}
                        <span className={`badge-sem ${item.kind === "done_task" ? "badge-sem--moss" : "badge-sem--muted"}`}>
                          {item.badgeText}
                        </span>
                        {item.type === "task" && canUpdate && item.rawTask && (
                          <button
                            type="button"
                            className="closed-task-action-btn"
                            onClick={() => setTaskStatus(item.rawTask!, "open")}
                            style={{ marginLeft: "auto" }}
                          >
                            Mở lại
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          {visibleHistory.length > 6 && (
            <button
              type="button"
              className="kh__linkbtn"
              style={{ alignSelf: "center", fontSize: 12 }}
              onClick={() => setShowAllHistory((v) => !v)}
            >
              {showAllHistory ? "Thu gọn" : `Xem thêm ${visibleHistory.length - 6} hoạt động cũ hơn`}
            </button>
          )}
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
  customerId,
  isEdit,
  initial,
  sales,
  onClose,
  onSaved,
}: {
  title: string;
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
  // Redesign spec-06 v2: form chỉ ĐỊNH DANH; tài chính sửa ở detail. Người phụ trách mặc định
  // chính mình — khóa picker (kể cả khi Tạo) nếu không có quyền điều chuyển (chỉ quản lý mới
  // gán cấp dưới). Đổi Loại → ẩn/hiện MST.
  const saleLocked = !canReassign;
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
    // MST chỉ áp cho công ty; nếu có nhập thì phải đúng định dạng (khách lẻ không cần MST).
    if (form.customer_kind === "cong_ty" && form.tax_code.trim() && !MST_RE.test(form.tax_code.trim()))
      next.tax_code = "MST phải gồm 10 hoặc 13 chữ số.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    if (!validate()) return;
    setSaving(true);
    setServerError(null);
    const input: CustomerInput = {
      name: form.name.trim(),
      customer_kind: form.customer_kind,
      // Cá nhân → không gửi MST (ẩn).
      tax_code: form.customer_kind === "cong_ty" ? form.tax_code.trim() || null : null,
      email: form.email.trim() || null,
      address: form.address.trim() || null,
      sale_user_id: form.sale_user_id ? Number(form.sale_user_id) : null,
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
              <label className="field kh__form-wide">
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
                <span className="field__label">Loại khách hàng</span>
                <div className="kh__seg" role="radiogroup" aria-label="Loại khách hàng">
                  <button
                    type="button"
                    role="radio"
                    aria-checked={form.customer_kind === "cong_ty"}
                    className={`kh__seg-btn${form.customer_kind === "cong_ty" ? " is-active" : ""}`}
                    onClick={() => setForm((s) => ({ ...s, customer_kind: "cong_ty" }))}
                  >
                    Công ty
                  </button>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={form.customer_kind === "ca_nhan"}
                    className={`kh__seg-btn${form.customer_kind === "ca_nhan" ? " is-active" : ""}`}
                    onClick={() => setForm((s) => ({ ...s, customer_kind: "ca_nhan" }))}
                  >
                    Cá nhân
                  </button>
                </div>
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
                    Mặc định là bạn; cần quyền “Điều chuyển” để gán cấp dưới.
                  </span>
                )}
              </label>
              {form.customer_kind === "cong_ty" && (
                <label className="field">
                  <span className="field__label">MST</span>
                  <input
                    className="input"
                    value={form.tax_code}
                    onChange={(e) => set("tax_code", e.target.value)}
                    onBlur={liveCheck}
                    aria-invalid={!!errors.tax_code}
                  />
                  {errors.tax_code && <span className="kh__err" role="alert">{errors.tax_code}</span>}
                </label>
              )}
              <label className="field kh__form-wide">
                <span className="field__label">Địa chỉ (đăng ký / xuất hóa đơn)</span>
                <input className="input" value={form.address} onChange={(e) => set("address", e.target.value)} />
              </label>
              <label className="field kh__form-wide">
                <span className="field__label">Email nhận hóa đơn điện tử</span>
                <input
                  className="input"
                  value={form.email}
                  onChange={(e) => set("email", e.target.value)}
                  onBlur={liveCheck}
                />
              </label>
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
