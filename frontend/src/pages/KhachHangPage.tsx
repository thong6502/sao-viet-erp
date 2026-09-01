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
  type KhoNhanRow,
  type OrderHistoryRow,
  type QuoteHistoryRow,
  type ReceivableCard,
  type SaleOption,
} from "../api/client";
import type { NavigateFn } from "../components/AppShell";
import { useAuth } from "../auth/useAuth";
import { useCan, useScopeOf } from "../auth/permissions";
import { CareCalendar } from "./CareCalendar";
import { gopTienTheoSanPham, tinhTiLeChot } from "./khachHangSo";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Select } from "../components/Select";
import {
  AlarmClock,
  BarChart3,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
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
  SearchX,
  Tags,
  UserPlus,
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
  ShieldCheck,
  Image,
  CreditCard,
  StickyNote,
  Pin,
  Clock3,
  Loader2,          // spinner nút "Tra cứu MST" (.kh__spin quay nó)
  LayoutGrid,
  List,
  ArrowLeftRight,
  ArrowRight,
  ShieldAlert,
} from "lucide-react";

import { MixDonut, MonthBars } from "../components/charts";
import "./khach-hang.css";


const MST_RE = /^(\d{10}|\d{13})$/;
const PAGE_SIZES = [25, 50, 100];
// Giá trị SENTINEL cho hộp lọc NV phụ trách: "" = tất cả, id NV = người cụ thể, còn giá trị này
// = khách CHƯA có người phụ trách (map sang query `chua_gan=true`, KHÔNG phải một id NV).
const SALE_CHUA_GAN = "__chua_gan__";

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
    return (n / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 }) + " Mđ";
  }
  if (n >= 1_000) {
    return (n / 1_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 }) + " Kđ";
  }
  return n.toLocaleString("vi-VN") + " ₫";
}

function moneySuperCompact(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000_000) {
    return (n / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 }) + " Bđ";
  }
  if (n >= 1_000_000) {
    return (n / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 }) + " Mđ";
  }
  if (n >= 1_000) {
    return (n / 1_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 }) + " Kđ";
  }
  return n.toLocaleString("vi-VN") + " ₫";
}

/** Số to + đơn vị ("22,17 Mđ") cho stat card / cột tiền — đồng màu 100%, không lệch font hay nhạt chữ. */
function moneyStat(n: number | null | undefined): ReactNode {
  if (n == null || n <= 0) return "—";
  return moneyCompact(n);
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

export const TAG_TONES = [
  "indigo",
  "emerald",
  "violet",
  "cyan",
  "amber",
  "rose",
  "fuchsia",
  "teal",
] as const;

export const TAG_SEMANTIC_TONES: Record<string, string> = {
  "ưu tiên": "violet",
  "tiềm năng": "emerald",
  "tiềm năng cao": "emerald",
  "đối tác lâu năm": "indigo",
  "tái ký hđ": "teal",
  "trả đúng hạn": "emerald",
  "nhạy giá": "amber",
  "hay trễ hẹn": "rose",
  "khó tính": "rose",
  "ưa giao nhanh": "cyan",
  "cần chăm sóc": "amber",
  "chuộng mẫu đẹp": "fuchsia",
  "bao bì cao cấp": "indigo",
};

export function tagTone(label: string): string {
  const lower = label.trim().toLowerCase();
  if (TAG_SEMANTIC_TONES[lower]) return TAG_SEMANTIC_TONES[lower];
  let h = 0;
  for (const ch of label) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return TAG_TONES[h % TAG_TONES.length];
}

const KH_CHU_CO_MAU = [
  "a", "b", "c", "d", "e", "g", "h", "k", "l", "m", "n", "p", "q", "s", "t", "u", "v", "x",
] as const;

/** Chữ cái quyết định MÀU của một khách — lấy từ chính CHỮ TẮT đang hiện trong vòng tròn.
 *
 *  Suy lại từ `getInitials` chứ không tự bóc tiền tố lần nữa: bản cũ tự bóc, mà chỉ bóc ĐƯỢC MỘT
 *  lần, nên "Công ty TNHH An Phát" còn lại "TNHH An Phát" → lấy chữ "T", trong khi vòng tròn ghi
 *  "AP". Màu chạy theo chữ "Công ty" chứ không theo tên khách ⇒ mọi "Công ty TNHH …" cùng một
 *  màu, mọi "Công ty CP …" cùng một màu khác. Lấy chữ đầu của chữ tắt thì màu và chữ KHÔNG THỂ
 *  lệch nhau, vì cả hai đọc từ một nguồn.
 */
function khChuMau(name: string): string {
  const ch = getInitials(name).slice(0, 1).toLowerCase();
  return (KH_CHU_CO_MAU as readonly string[]).includes(ch) ? ch : "default";
}

export function getKhAvatarClass(name: string): string {
  return `kh__avatar--${khChuMau(name)}`;
}

/** Chấm nhỏ ở góc avatar — CÙNG chữ cái với avatar, chỉ đậm tông hơn.
 *
 *  Trước 16/08/2026 chấm này tô theo "hạng khách" tự phán trong frontend (≥100 triệu = VIP,
 *  ≥3 đơn = Đối tác…). Ngưỡng không ai duyệt, không có trong DB, và chấm 7px không chú giải thì
 *  người dùng cũng không có cách nào biết cam nghĩa là gì. Nay chấm chỉ là phần của khối định
 *  danh — không giả vờ phân loại nữa. */
export function getKhDotClass(name: string): string {
  return `kh__avatar-dot--${khChuMau(name)}`;
}

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
  // Thiếu đúng dòng này nên badge in nguyên mã máy "CONVERTED_TO_ORDER" giữa các nhãn tiếng Việt
  // — mà đây lại là trạng thái ĐÔNG NHẤT của khách quen (báo giá nào cũng thành đơn).
  converted_to_order: "Đã lên đơn",
  pending_approval: "Chờ duyệt",
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

/** Dòng phụ dưới tên người trong mọi hộp chọn NV: "NV Sales · Kinh doanh". Thiếu vế nào thì bỏ
 *  vế đó (tài khoản chưa gán vai trò / chưa gắn phòng) — không hiện dấu chấm giữa lơ lửng. */
function moTaSale(s: SaleOption): string | undefined {
  const phan = [s.vai_tro, s.phong_ban].filter((x): x is string => !!x && x.trim() !== "");
  return phan.length ? phan.join(" · ") : undefined;
}

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
  // "" = tất cả; CHUA_GAN = khách chưa có người phụ trách; còn lại là id NV.
  const [saleFilter, setSaleFilter] = useState<string>("");
  // Redesign spec-06 v2: bỏ lọc trạng thái/tier; chỉ còn lọc theo THẺ + tab "Cần theo dõi".
  const [followupFilter, setFollowupFilter] = useState<boolean>(false);
  const [tagFilter, setTagFilter] = useState<string>("");
  const [tagLabels, setTagLabels] = useState<string[]>([]);
  const [pageSize, setPageSize] = useState(25);
  const [sales, setSales] = useState<SaleOption[]>([]);
  // id NV → "Vai trò · Phòng", để cột NV phụ trách của bảng hiện chức danh dưới tên.
  const saleMeta = useMemo(() => {
    const m = new Map<number, string>();
    for (const s of sales) {
      const t = moTaSale(s);
      if (t) m.set(s.id, t);
    }
    return m;
  }, [sales]);

  // Điều chuyển khách hàng: gated bằng quyền chi tiết `reassign` (Cách B) — cấu hình trong
  // ma trận phân quyền, tách khỏi quyền Sửa thông thường.
  const can = useCan();
  const scopeOf = useScopeOf();
  // Option "Chưa gán" chỉ có nghĩa với người phạm vi `all`: own/department lọc theo chủ sổ nên
  // khách vô chủ tự rơi ra ngoài tầm nhìn — thêm option cho họ chỉ ra danh sách rỗng, gây bối rối.
  const canSeeUnassigned = scopeOf("khach_hang") === "all";
  const canReassign = can("khach_hang", "reassign");
  const canExport = true; // Xuất file MẶC ĐỊNH BẬT (gỡ công tắc `export` khách 24/08/2026).
  const canCreate = can("khach_hang", "create");
  const colCount = canReassign ? 7 : 6; // [checkbox] · KH · doanh số · số đơn · TB/đơn · NV · ›

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
  const [viewMode, setViewMode] = useState<"table" | "cards">("table");
  const [quickTagModalCust, setQuickTagModalCust] = useState<{ id: number; name: string } | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setListError(null);
    setSelectedIds(new Set()); // selection is per current page/filter
    api.customers
      .list(token, {
        q: q.trim() || undefined,
        sale: saleFilter && saleFilter !== SALE_CHUA_GAN ? Number(saleFilter) : null,
        chua_gan: saleFilter === SALE_CHUA_GAN || undefined,
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
        <div className="kh__title-group">
          <p className="eyebrow">Kinh doanh · CRM</p>
          <div className="kh__title-row">
            <h1 className="kh__title">Khách hàng</h1>
            {kpis && (
              <span className="kh__badge-summary">
                <strong>{total}</strong> KH &middot; <strong>{kpis.new_this_month}</strong> mới tháng này
              </span>
            )}
          </div>
        </div>
        <div className="kh__head-actions">
          {canExport && (
            <Button variant="ghost" onClick={exportBook} loading={exportingBook}>
              <Download size={14} /> Xuất CSV
            </Button>
          )}
          {canCreate && (
            <Button variant="ghost" onClick={() => setImportOpen(true)}>
              Nhập CSV
            </Button>
          )}
          {canReassign && (
            <Button variant="ghost" onClick={openReassign} disabled={sales.length < 2}>
              Điều chuyển
            </Button>
          )}
          {canCreate && (
            <Button
              variant="primary"
              onClick={() => {
                setEditing(null);
                setMode("create");
              }}
            >
              + Tạo khách hàng
            </Button>
          )}
        </div>
      </header>

      {reassignMsg && (
        <div className="banner banner--success" role="status">
          {reassignMsg}
        </div>
      )}

      {/* KPI header strip — low profile compact bar */}
      <KpiStrip
        kpis={kpis}
        loading={loading && !kpis}
        careCount={followups.length}
        careOpen={followupsOpen}
        onToggleCare={() => setFollowupsOpen((v) => !v)}
      />

      {/* Executive Care Panel Wrapper */}
      {followups.length > 0 && followupsOpen && (
        <div className="kh__care-panel-wrapper">
          <div className="kh__care-panel-header">
            <div className="kh__care-panel-title">
              <AlarmClock size={16} style={{ color: "var(--ink)" }} />
              <span>Nhiệm vụ chăm sóc khách hàng</span>
              <span className="kh__care-panel-count-tag">{followups.length} mục</span>
            </div>
          </div>

          <div className="kh__care-cards-grid">
            {followups.map((f) => (
              <div key={f.id} className="kh__care-card-item kh__care-card-item--followup">
                <div className="kh__care-card-top">
                  <RemindBadge level={f.remind_level} days={f.overdue_days} />
                  <button type="button" className="kh__care-card-name" onClick={() => setOpenId(f.customer_id)}>
                    {f.customer_name}
                  </button>
                  <span className="kh__care-card-code">{f.customer_code}</span>
                </div>
                <div className="kh__care-card-body">
                  <span className="kh__care-card-note">{f.note}</span>
                  <div className="kh__care-card-subinfo">
                    <span className="kh__care-card-due">
                      <Clock3 size={11} /> Hạn {fmtDate(f.due_date)}
                    </span>
                    {f.assignee_name && <span className="kh__care-card-assignee">· {f.assignee_name}</span>}
                  </div>
                </div>
              </div>
            ))}

          </div>
        </div>
      )}

      {/* Single-row Integrated Toolbar */}
      <div className="kh__toolbar-strip">
        <div className="kh__sub-tabs">
          <button
            type="button"
            className={`kh__sub-tab${!followupFilter ? " is-active" : ""}`}
            onClick={() => {
              setFollowupFilter(false);
              setPage(1);
            }}
          >
            Tất cả <span className="chip-count">{total}</span>
          </button>
          <button
            type="button"
            className={`kh__sub-tab${followupFilter ? " is-active" : ""}`}
            onClick={() => {
              setFollowupFilter(true);
              setPage(1);
            }}
          >
            <AlarmClock size={13} /> Cần theo dõi{" "}
            <span className={`chip-count${followups.length > 0 ? " chip-count--alert" : ""}`}>
              {followups.length}
            </span>
          </button>
        </div>

        <div className="kh__toolbar-controls">
          <form className="kh__search" onSubmit={onSearch} role="search">
            <div className="kh__search-input-wrap">
              <span className="kh__search-icon" aria-hidden="true"><Search size={14} /></span>
              <input
                className="input kh__search-input"
                placeholder="Tìm theo tên / MST / điện thoại…"
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
              align="right"
              onChange={(v) => {
                setSaleFilter(v ?? "");
                setPage(1);
              }}
              options={[
                { value: "", label: "Tất cả NV phụ trách" },
                // Khách chưa có người phụ trách — chỉ hiện cho người phạm vi `all` (xem canSeeUnassigned).
                ...(canSeeUnassigned ? [{ value: SALE_CHUA_GAN, label: "Chưa gán ai" }] : []),
                // Hộp LỌC lấy CẢ người không còn đủ tư cách nhận khách mới (`co_the_gan=false`):
                // khách của họ vẫn hiện trong bảng, thiếu tên ở đây là có dòng không lọc ra được.
                ...sales.map((s) => ({
                  value: String(s.id),
                  label: s.name,
                  sub: moTaSale(s),
                  hint: s.so_kh ? `${s.so_kh} KH` : undefined,
                })),
              ]}
            />
          </div>
          {tagLabels.length > 0 && (
            <div className="kh__filter">
              <Select
                ariaLabel="Lọc theo nhãn"
                value={tagFilter}
                placeholder="Tất cả nhãn"
                align="right"
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

          {/* View Mode Switcher: Bảng ⟷ Thẻ CRM */}
          <div className="kh__view-switcher" role="group" aria-label="Chế độ hiển thị">
            <button
              type="button"
              className={`kh__view-btn${viewMode === "table" ? " is-active" : ""}`}
              title="Xem dạng Bảng"
              aria-pressed={viewMode === "table"}
              onClick={() => setViewMode("table")}
            >
              <List size={14} />
            </button>
            <button
              type="button"
              className={`kh__view-btn${viewMode === "cards" ? " is-active" : ""}`}
              title="Xem dạng Thẻ CRM"
              aria-pressed={viewMode === "cards"}
              onClick={() => setViewMode("cards")}
            >
              <LayoutGrid size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* Khoảng CỐ ĐỊNH ngay trên bảng (chỉ cho người có quyền điều chuyển): luôn giữ chiều
          cao nên khi tick chọn, thanh thao tác lấp vào đúng chỗ — danh sách KHÔNG bị đẩy. */}
      {canReassign && (
        <div className="kh__bulkslot">
          {selectedIds.size > 0 ? (
            <div className="kh__bulkbar">
              <div className="kh__bulkbar-left">
                <span className="kh__bulkcount">
                  Đã chọn <strong>{selectedIds.size}</strong> khách hàng
                </span>
              </div>
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

      {/* Vùng hiển thị dữ liệu: Dạng Bảng hoặc Dạng Thẻ CRM */}
      {viewMode === "cards" && !loading && !listError && rows.length > 0 ? (
        <div className="kh__cards-grid">
          {rows.map((c) => {
            const initials = getInitials(c.name);
            const careDue = followups.filter((f) => f.customer_id === c.id).length;
            const customerTags = c.tags ?? [];

            return (
              <div
                key={c.id}
                className={`kh__customer-card-v2${openId === c.id ? " is-open" : ""}`}
                onClick={() => setOpenId(c.id)}
              >
                <div className="kh__card-top">
                  <div className="kh__card-identity">
                    <div className="kh__avatar-wrapper">
                      <div className={`kh__avatar ${getKhAvatarClass(c.name)}`}>{initials}</div>
                      <span className={`kh__avatar-dot ${getKhDotClass(c.name)}`} />
                    </div>
                    <div className="kh__card-info">
                      <div className="kh__card-name-row">
                        <h3 className="kh__card-name" title={c.name}>{c.name}</h3>
                      </div>
                      <div className="kh__card-submeta">
                        <span className="kh__code-badge">{c.code || `KH${String(c.id).padStart(3, "0")}`}</span>
                        {c.tax_code && <span className="kh__mst-chip">MST {c.tax_code}</span>}
                        {careDue > 0 && (
                          <span className="kh__row-badge kh__row-badge--care">
                            <AlarmClock size={10} /> {careDue} việc
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="kh__card-tag-btn"
                    title="Gắn thẻ"
                    onClick={(e) => {
                      e.stopPropagation();
                      setQuickTagModalCust({ id: c.id, name: c.name });
                    }}
                  >
                    <Tags size={13} />
                  </button>
                </div>

                <div className="kh__card-stats">
                  <div className="kh__card-stat-item">
                    <span className="kh__card-stat-label">Doanh số 12T</span>
                    <span className="kh__card-stat-val kh__card-stat-val--rev">
                      {c.revenue_12m > 0 ? moneyStat(c.revenue_12m) : "—"}
                    </span>
                  </div>
                  <div className="kh__card-stat-item">
                    <span className="kh__card-stat-label">Số đơn hàng</span>
                    <span className="kh__card-stat-val">{c.orders_total} đơn</span>
                  </div>
                </div>

                <div className="kh__card-footer">
                  {c.sale_name ? (
                    <div className="kh__sale-chip-compact">
                      <span className="kh__sale-avatar">{getInitials(c.sale_name)}</span>
                      <span className="kh__sale-name">{c.sale_name}</span>
                    </div>
                  ) : (
                    <span className="kh__muted">Chưa gán NV</span>
                  )}
                  <div className="kh__card-tags">
                    {customerTags.slice(0, 2).map((t) => (
                      <span key={t} className={`kh__row-badge kh__row-badge--tag-${tagTone(t)}`}>
                        {t}
                      </span>
                    ))}
                    {customerTags.length > 2 && (
                      <span
                        className="kh__row-badge kh__row-badge--more"
                        title={customerTags.slice(2).join(", ")}
                      >
                        +{customerTags.length - 2}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="kh__tablewrap">
          <div className="kh__tablescroll">
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
                    <td colSpan={colCount} className="kh__empty-cell">
                      {q || tagFilter || saleFilter || followupFilter ? (
                        <div className="kh__empty-state">
                          <div className="kh__empty-icon">
                            <SearchX size={28} />
                          </div>
                          <h3 className="kh__empty-title">Không tìm thấy khách hàng</h3>
                          <p className="kh__empty-sub">
                            Không tìm thấy khách hàng nào phù hợp với điều kiện tìm kiếm hoặc bộ lọc hiện tại.
                          </p>
                          <Button
                            variant="ghost"
                            onClick={() => {
                              setQ("");
                              setTagFilter("");
                              setSaleFilter("");
                              setFollowupFilter(false);
                              setPage(1);
                            }}
                          >
                            Xoá bộ lọc
                          </Button>
                        </div>
                      ) : (
                        <div className="kh__empty-state">
                          <div className="kh__empty-icon">
                            <UserPlus size={28} />
                          </div>
                          <h3 className="kh__empty-title">Chưa có khách hàng nào trong sổ</h3>
                          <p className="kh__empty-sub">
                            Danh sách khách hàng của bạn hiện đang trống. Hãy tạo mới khách hàng đầu tiên để bắt đầu quản lý hồ sơ và giao dịch.
                          </p>
                          <Button
                            variant="primary"
                            onClick={() => {
                              setEditing(null);
                              setMode("create");
                            }}
                          >
                            + Tạo khách hàng đầu tiên
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ) : (
                  (() => {
                    const maxRevenueOnPage = Math.max(...rows.map((r) => r.revenue_12m || 0), 1);
                    return rows.map((c) => {
                      const initials = getInitials(c.name);
                      const avgOrderValue = c.orders_total > 0 ? Math.round(c.revenue_12m / c.orders_total) : 0;
                      const careDue = followups.filter((f) => f.customer_id === c.id).length;
                      const revPercent = c.revenue_12m > 0 ? Math.min(100, Math.round((c.revenue_12m / maxRevenueOnPage) * 100)) : 0;
                      const customerTags = c.tags ?? [];
                      const displayTags = customerTags.slice(0, 2);
                      const remainingTagsCount = customerTags.length - 2;
                      const salesRole = saleMeta.get(c.sale_user_id ?? -1);
                      const revGradient =
                        c.revenue_12m >= 100_000_000
                          ? "linear-gradient(90deg, #818cf8, #7c3aed)"
                          : c.revenue_12m >= 10_000_000
                          ? "linear-gradient(90deg, #34d399, #059669)"
                          : "linear-gradient(90deg, #94a3b8, #64748b)";

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
                              <div className="kh__avatar-wrapper">
                                <div className={`kh__avatar ${getKhAvatarClass(c.name)}`}>{initials}</div>
                                <span className={`kh__avatar-dot ${getKhDotClass(c.name)}`} />
                              </div>
                              <div className="kh__identity">
                                <div className="kh__name-row">
                                  <span className="kh__name" title={c.name}>{c.name}</span>
                                  <span className="kh__code-badge">{c.code || `KH${String(c.id).padStart(3, "0")}`}</span>
                                </div>
                                <div className="kh__submeta">
                                  {c.tax_code && <span className="kh__mst-chip">MST {c.tax_code}</span>}
                                  {careDue > 0 && (
                                    <span
                                      className="kh__row-badge kh__row-badge--care"
                                      title={`${careDue} việc chăm sóc đến hạn`}
                                    >
                                      <AlarmClock size={10} /> {careDue} việc
                                    </span>
                                  )}
                                  {displayTags.map((t) => (
                                    <span key={t} className={`kh__row-badge kh__row-badge--tag-${tagTone(t)}`}>
                                      {t}
                                    </span>
                                  ))}
                                  {remainingTagsCount > 0 && (
                                    <span
                                      className="kh__row-badge kh__row-badge--more"
                                      title={customerTags.slice(2).join(", ")}
                                    >
                                      +{remainingTagsCount}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td className="kh__num kh__money-cell">
                            {c.revenue_12m > 0 ? (
                              <div className="kh__rev-box">
                                <span className="kh__revenue-val">{moneyStat(c.revenue_12m)}</span>
                                <div className="kh__rev-bar-track" title={`${revPercent}% so với top trang`}>
                                  <div
                                    className="kh__rev-bar-fill"
                                    style={{
                                      width: `${Math.max(6, revPercent)}%`,
                                      background: revGradient,
                                    }}
                                  />
                                </div>
                              </div>
                            ) : (
                              <span className="kh__muted">—</span>
                            )}
                          </td>
                          <td className="kh__num">
                            {c.orders_total > 0 ? (
                              <span className="kh__orders-pill-v2">{c.orders_total}</span>
                            ) : (
                              <span className="kh__muted">0</span>
                            )}
                          </td>
                          <td className="kh__num kh__aov-cell">
                            {avgOrderValue > 0 ? moneySuperCompact(avgOrderValue) : <span className="kh__muted">—</span>}
                          </td>
                          <td>
                            {c.sale_name ? (
                              <div
                                className="kh__sale-chip-compact"
                                title={salesRole ? `${c.sale_name} · ${salesRole}` : c.sale_name}
                              >
                                <span className="kh__sale-avatar">{getInitials(c.sale_name)}</span>
                                <span className="kh__sale-name">{c.sale_name}</span>
                              </div>
                            ) : (
                              <span className="kh__muted">Chưa gán</span>
                            )}
                          </td>
                          <td className="kh__action-col" onClick={(e) => e.stopPropagation()}>
                            <div className="kh__row-quick-actions">
                              <button
                                type="button"
                                className="kh__quick-btn"
                                title="Gắn thẻ"
                                onClick={() => setQuickTagModalCust({ id: c.id, name: c.name })}
                              >
                                <Tags size={12} />
                              </button>
                              <button
                                type="button"
                                className="kh__quick-btn"
                                title="Xem hồ sơ"
                                onClick={() => setOpenId(c.id)}
                              >
                                <ChevronRight size={14} />
                              </button>
                            </div>
                            <ChevronRight size={15} className="kh__arrow-icon" />
                          </td>
                        </tr>
                      );
                    });
                  })()
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

  {!loading && !listError && rows.length > 0 && (
    <div className="kh__pager">
      <div className="kh__pager-left">
        <span className="kh__pager-info">
          Tổng {total} khách hàng · Trang {page}/{totalPages}
        </span>
        <span className="kh__pager-divider" />
        <div className="kh__pager-size">
          <span>Hiển thị</span>
          <Select
            ariaLabel="Số dòng mỗi trang"
            value={pageSize}
            onChange={(v) => {
              setPageSize(v ?? 25);
              setPage(1);
            }}
            options={PAGE_SIZES.map((n) => ({ value: n, label: `${n} dòng` }))}
          />
        </div>
      </div>
      <div className="kh__pager-btns">
        <button
          type="button"
          className="kh__pager-btn"
          disabled={page <= 1}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          title="Trang trước"
        >
          <ChevronLeft size={16} /> Trước
        </button>
        <span className="kh__pager-page-indicator">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          className="kh__pager-btn"
          disabled={page >= totalPages}
          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          title="Trang sau"
        >
          Sau <ChevronRight size={16} />
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

      {quickTagModalCust && (
        <TagModal
          customerId={quickTagModalCust.id}
          customerName={quickTagModalCust.name}
          current={(rows.find((r) => r.id === quickTagModalCust.id)?.tags ?? []).map((label, idx) => ({ id: idx + 1, label }))}
          onClose={() => setQuickTagModalCust(null)}
          onSaved={() => {
            setQuickTagModalCust(null);
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

      <CustomerReassignModal
        open={reassignOpen}
        sales={sales}
        fromSale={fromSale}
        toSale={toSale}
        setFromSale={setFromSale}
        setToSale={setToSale}
        busy={reassignBusy}
        error={reassignError}
        onConfirm={doReassign}
        onCancel={() => !reassignBusy && setReassignOpen(false)}
      />

      <BulkReassignModal
        open={bulkOpen}
        selectedCount={selectedIds.size}
        sales={sales}
        bulkTarget={bulkTarget}
        setBulkTarget={setBulkTarget}
        busy={bulkBusy}
        error={bulkError}
        onConfirm={doBulkReassign}
        onCancel={() => !bulkBusy && setBulkOpen(false)}
      />
    </main>
  );
}

// --- KPI header strip --------------------------------------------------------

function KpiStrip({
  kpis,
  loading,
  careCount,
  careOpen,
  onToggleCare,
}: {
  kpis: CustomerKpis | null;
  loading: boolean;
  careCount: number;
  careOpen: boolean;
  onToggleCare: () => void;
}) {
  const careTotal = careCount;

  // UI_DESIGN §4: chỉ số gộp thành MỘT dải pill (~38px), không phải 4 thẻ 84px xếp 4 cột —
  // thẻ cao đẩy bảng dữ liệu (nội dung thật của màn) xuống dưới màn hình.
  // "Cần chăm sóc" tách ra pill riêng: nó là VIỆC PHẢI LÀM, không phải số để đọc, nên nó
  // được mang màu (§3) — nhưng ở liều pill, không phải tô cả thẻ.
  return (
    <div className="kh__kpis">
      <div className="kh__ckpi">
        <div className="kh__ckpi-item">
          <span className="kh__ckpi-icon">
            <Users size={14} />
          </span>
          <span className="kh__ckpi-body">
            <span className="kh__ckpi-val">
              {loading ? <span className="kh__skel kh__skel--kpi" /> : (kpis ? String(kpis.total_customers) : "—")}
            </span>
            <span className="kh__ckpi-lbl">khách hàng</span>
          </span>
        </div>

        <span className="kh__ckpi-div" aria-hidden="true" />

        <div className="kh__ckpi-item">
          <span className="kh__ckpi-icon">
            <UserPlus size={14} />
          </span>
          <span className="kh__ckpi-body">
            <span className="kh__ckpi-val">
              {loading ? <span className="kh__skel kh__skel--kpi" /> : (kpis ? String(kpis.new_this_month) : "—")}
            </span>
            <span className="kh__ckpi-lbl">mới tháng này</span>
          </span>
        </div>

        <span className="kh__ckpi-div" aria-hidden="true" />

        <div className="kh__ckpi-item">
          <span className="kh__ckpi-icon">
            <BarChart3 size={14} />
          </span>
          <span className="kh__ckpi-body">
            <span className="kh__ckpi-val">
              {loading ? <span className="kh__skel kh__skel--kpi" /> : (kpis ? moneyStat(kpis.avg_order_value) : "—")}
            </span>
            <span className="kh__ckpi-lbl">TB / đơn (12T)</span>
          </span>
        </div>
      </div>

      <button
        type="button"
        className={`kh__care-pill${careTotal > 0 ? " is-alert" : ""}`}
        onClick={onToggleCare}
        aria-expanded={careOpen}
        disabled={careTotal === 0}
        title={careTotal === 0 ? "Không có việc chăm sóc nào hôm nay" : undefined}
      >
        <AlarmClock size={14} />
        {careTotal === 0 ? (
          <span>Không có việc chăm sóc</span>
        ) : (
          <>
            <span>
              Cần chăm sóc hôm nay <strong className="kh__care-n">{careCount}</strong>
            </span>
            <span className="kh__care-caret" aria-hidden="true">{careOpen ? "▲" : "▼"}</span>
          </>
        )}
      </button>
    </div>
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
  // Khách MỚI (chưa có đơn/báo giá): KHÔNG chặn cả tab. Chính sách tài chính là dữ liệu CẤU HÌNH
  // (không dẫn xuất từ giao dịch) nên phải luôn hiện để cấu hình được ngay. KPI/biểu đồ vẫn vẽ đủ
  // khung nhưng để rỗng (số THẬT = 0, không bịa) — chỉ kèm một dòng note trung thực ở đầu.
  // Công nợ MẶC ĐỊNH BẬT cho mọi vai xem khách (gỡ công tắc `view_debt` 24/08/2026) — luôn hiện thẻ.
  const canDebt = true;
  const avgVal = dash.avg_order_value ?? 0;
  const cards: { label: string; value: ReactNode; hint?: string; muted?: boolean }[] = [
    // Không có dữ liệu 24 tháng để so YoY thật → hint trung thực về phạm vi số liệu.
    { label: "Doanh số 12T", value: moneyStat(dash.revenue_12m), hint: "12 tháng gần nhất" },
    {
      label: "Số đơn 12T",
      value: `${dash.orders_12m} đơn`,
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
      {!dash.has_data && (
        <div className="kh__dash-newnote">
          <UserPlus size={15} strokeWidth={2} />
          <span>
            Khách mới — chưa phát sinh giao dịch. Doanh số, tần suất &amp; cơ cấu sản phẩm sẽ tự
            cập nhật từ đơn hàng thật; bạn vẫn cấu hình được <strong>Chính sách tài chính</strong>{" "}
            bên dưới ngay bây giờ.
          </span>
        </div>
      )}
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

      {/* Lưới 2 cột: Cơ cấu sản phẩm + Chính sách tài chính. */}
      <div className="kh__dash-grid-3 kh__dash-grid-3--2">
        {/* Cơ cấu sản phẩm — donut */}
        <section className="card kh__chart">
          <div className="kh__chart-head">
            <h3><Package size={14} /> Cơ cấu sản phẩm</h3>
          </div>
          <ProductDonut mix={dash.product_mix} />
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
// Điều khoản thanh toán đã BỎ theo yêu cầu — chỉ còn Hạn mức + rào Chiết khấu/Markup.

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
    markup_min_pct: "",
    markup_max_pct: "",
  });

  function openEdit() {
    const numStr = (n?: number | null) => (n != null ? String(n) : "");
    setF({
      credit_limit: String(customer.credit_limit ?? 0),
      payment_term_days: numStr(customer.payment_term_days),
      discount_min_pct: numStr(customer.discount_min_pct),
      discount_max_pct: numStr(customer.discount_max_pct),
      markup_min_pct: numStr(customer.markup_min_pct),
      markup_max_pct: numStr(customer.markup_max_pct),
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
      markup_min_pct: numOrNull(f.markup_min_pct),
      markup_max_pct: numOrNull(f.markup_max_pct),
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
            <span className="kh__fin-label" title="Markup = lợi nhuận / giá vốn — đúng ô Markup% trên báo giá">Markup (trên giá vốn)</span>
            <span>{rangeText(customer.markup_min_pct, customer.markup_max_pct)}</span>
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
              <span className="field__label">Markup tối thiểu (%)</span>
              <input className="input" type="number" min={0} max={100} value={f.markup_min_pct}
                onChange={(e) => set("markup_min_pct", e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Markup tối đa (%)</span>
              <input className="input" type="number" min={0} max={100} value={f.markup_max_pct}
                onChange={(e) => set("markup_max_pct", e.target.value)} />
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
  const canExport = true; // Xuất Excel lịch sử mua MẶC ĐỊNH BẬT (gỡ công tắc `export` 24/08/2026).
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

  // Đơn đã huỷ KHÔNG phải tiền thật đã chi — loại khỏi mọi tổng/biểu đồ tiền, chỉ giữ lại trong
  // bảng "Toàn bộ đơn hàng" bên dưới để còn thấy dấu vết. Khớp quy ước `_EXCLUDED_ORDER_STATUSES`
  // bên backend (customer_analytics.py) — trước đây SỐ ĐƠN HOÀN THÀNH loại đơn huỷ nhưng
  // TỔNG CHI TIÊU/TB-ĐƠN/Đơn lớn nhất/biểu đồ tháng/TOP sản phẩm thì không, nên hễ khách có 1 đơn
  // huỷ mang tiền là tiền đó vẫn cộng vào "đã chi" dù đơn chưa từng thật.
  const activeRows = useMemo(
    () => filteredRows.filter((o) => o.status !== "cancelled"),
    [filteredRows],
  );

  // "Hoàn thành" = ĐÃ CHỐT thật (status "ordered"), không tính Nháp/Tạm giữ/Đã đổi — siết chặt
  // hơn activeRows vì hai trạng thái đó chưa phải đơn xong. TB/ĐƠN + Đơn lớn nhất đi theo cùng
  // tập này cho khỏi lệch gốc (chia tổng-mọi-đơn cho đếm-riêng-đơn-chốt sẽ ra số sai).
  const completedRows = useMemo(
    () => activeRows.filter((o) => o.status === "ordered"),
    [activeRows],
  );

  const { totalLifetime, completedCount, avgSpend, maxSpend, perMonth, sinceDate } = useMemo(() => {
    if (activeRows.length === 0) {
      return { totalLifetime: 0, completedCount: 0, avgSpend: 0, maxSpend: 0, perMonth: 0, sinceDate: null as string | null };
    }
    const total = activeRows.reduce((s, o) => s + (o.total ?? 0), 0);
    // Nhịp đặt/tháng tính trên KHOẢNG THỜI GIAN THẬT của dữ liệu (đơn cũ nhất → mới nhất),
    // không chia bừa cho 12.
    const dates = activeRows.map((o) => new Date(o.created_at).getTime()).filter((t) => !Number.isNaN(t));
    const oldest = Math.min(...dates);
    const newest = Math.max(...dates);
    const spanMonths = Math.max(1, Math.round((newest - oldest) / (30.44 * 86_400_000)) + 1);

    const completed = completedRows.length;
    const completedTotal = completedRows.reduce((s, o) => s + (o.total ?? 0), 0);
    const completedMax = completedRows.reduce((m, o) => Math.max(m, o.total ?? 0), 0);

    return {
      totalLifetime: total,
      completedCount: completed,
      avgSpend: completed > 0 ? Math.round(completedTotal / completed) : 0,
      maxSpend: completedMax,
      perMonth: completed / spanMonths,
      sinceDate: new Date(oldest).toISOString(),
    };
  }, [activeRows, completedRows]);

  // So sánh THẬT với năm liền trước (chỉ khi đang lọc 1 năm và năm trước có dữ liệu).
  const yoyPct = useMemo(() => {
    if (!rows || !yearFilter) return null;
    const prevYear = String(Number(yearFilter) - 1);
    const sum = (yr: string) =>
      rows
        .filter((o) => o.status !== "cancelled" && o.created_at?.startsWith(yr))
        .reduce((s, o) => s + (o.total ?? 0), 0);
    const prev = sum(prevYear);
    if (prev <= 0) return null;
    return Math.round(((sum(yearFilter) - prev) / prev) * 100);
  }, [rows, yearFilter]);

  // Group by month for chart — trục liên tục tối đa 12 tháng như prototype.
  const monthlySpend = useMemo(() => monthlySeries(activeRows), [activeRows]);

  // Top products mix — TOP 4, cộng theo TIỀN THẬT của từng dòng đơn (xem `gopTienTheoSanPham`).
  const productMix = useMemo(() => gopTienTheoSanPham(activeRows), [activeRows]);

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
          <span className="kh__kpi-value">{completedCount} đơn</span>
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
      <div className="kh__tablewrap kh__tablewrap--orders">
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

  // Số liệu THẬT từ chính danh sách báo giá. Tỉ lệ chốt tính ở `tinhTiLeChot` (có test) — định
  // nghĩa "thắng"/"đã chào" phải khớp backend, xem chú thích trong `khachHangSo.ts`.
  const totalQuoted = filteredRows.reduce((s, q) => s + (q.total ?? 0), 0);
  const chot = tinhTiLeChot(filteredRows);

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
          <span className="kh__kpi-value">{filteredRows.length} BG</span>
          <span className="kh__kpi-hint">Tổng GT báo giá {moneyCompact(totalQuoted)}</span>
        </div>
        <div className="kh__kpi card">
          <span className="kh__kpi-label">TỈ LỆ CHỐT</span>
          {/* Chưa chào báo giá nào thì hiện "—", KHÔNG hiện 0%: 0% đọc ra là "chào mãi không ai
              mua", oan cho khách mới toanh. */}
          <span className="kh__kpi-value">{chot.pct === null ? "—" : `${chot.pct}%`}</span>
          {/* daChao < 3: mẫu quá nhỏ để % có nghĩa (2/2 = "100%" trông chắc như đinh nhưng chỉ
              từ 2 báo giá) — gắn nhãn cảnh báo thay vì để con số tự tin đánh lừa. */}
          {chot.pct !== null && chot.daChao < 3 && (
            <span
              className="kh__badge kh__badge--warn"
              style={{ fontSize: "12px", padding: "1px 6px", marginTop: "2px" }}
            >
              Mẫu nhỏ
            </span>
          )}
          <span className="kh__kpi-hint">
            {chot.pct === null
              ? "Chưa gửi báo giá nào cho khách"
              : `${chot.thang}/${chot.daChao} BG đã gửi khách`}
          </span>
        </div>
        <div className="kh__kpi card">
          <span className="kh__kpi-label">GIÁ TRỊ ĐÃ CHỐT</span>
          <span className="kh__kpi-value">{moneyStat(chot.giaTriThang)}</span>
          <span className="kh__kpi-hint">
            {chot.thang > 0
              ? `TB ${moneyCompact(Math.round(chot.giaTriThang / chot.thang))} / BG thắng`
              : "Chưa có BG thắng"}
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
      <div className="kh__tablewrap kh__tablewrap--orders">
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

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())} ${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}

function fmtTimeOnly(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}

function renderAuditDetailTags(detail: string | null) {
  if (!detail) return null;

  const trimmed = detail.trim();
  if (trimmed === "converted_to_order") {
    return (
      <div className="kh__tl-tags">
        <span className="kh__tl-badge kh__tl-badge--success">
          <CheckCircle2 size={11} /> Đã chuyển thành đơn hàng
        </span>
      </div>
    );
  }

  const parts = trimmed.split(/\s*·\s*|,\s*/).map((p) => p.trim()).filter(Boolean);

  return (
    <div className="kh__tl-tags">
      {parts.map((p, idx) => {
        let cls = "kh__tl-tag--default";
        let label = p;

        if (p === "converted_to_order") {
          label = "Đã chuyển thành đơn hàng";
          cls = "kh__tl-tag--success";
        } else if (p === "Đơn mới") {
          cls = "kh__tl-tag--brand";
        } else if (p === "Đã chốt") {
          cls = "kh__tl-tag--primary";
        } else if (p === "Nháp") {
          cls = "kh__tl-tag--muted";
        }

        return (
          <span key={idx} className={`kh__tl-tag ${cls}`}>
            {label}
          </span>
        );
      })}
    </div>
  );
}

function groupAuditRowsByDate(rows: CustomerAuditRow[]) {
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayStr = `${yesterday.getFullYear()}-${String(yesterday.getMonth() + 1).padStart(2, "0")}-${String(yesterday.getDate()).padStart(2, "0")}`;

  const groupsMap = new Map<string, { dateKey: string; dateLabel: string; items: CustomerAuditRow[] }>();

  for (const r of rows) {
    const d = new Date(r.at);
    let dateKey = r.at ? r.at.substring(0, 10) : "unknown";
    let dateLabel = "";

    if (Number.isNaN(d.getTime())) {
      dateKey = "khac";
      dateLabel = "Khác";
    } else {
      const formattedDate = `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
      if (dateKey === todayStr) {
        dateLabel = `Hôm nay · ${formattedDate}`;
      } else if (dateKey === yesterdayStr) {
        dateLabel = `Hôm qua · ${formattedDate}`;
      } else {
        dateLabel = formattedDate;
      }
    }

    if (!groupsMap.has(dateKey)) {
      groupsMap.set(dateKey, { dateKey, dateLabel, items: [] });
    }
    groupsMap.get(dateKey)!.items.push(r);
  }

  return Array.from(groupsMap.values());
}

const AUDIT_KIND_META: Record<CustomerAuditRow["kind"], { icon: JSX.Element; label: string; nodeCls: string }> = {
  profile: { icon: <PencilLine size={14} />, label: "Hồ sơ", nodeCls: "kh__tl-node--profile" },
  order: { icon: <Package size={14} />, label: "Đơn hàng", nodeCls: "kh__tl-node--order" },
  quote: { icon: <FileText size={14} />, label: "Báo giá", nodeCls: "kh__tl-node--quote" },
  care: { icon: <HeartHandshake size={14} />, label: "Chăm sóc", nodeCls: "kh__tl-node--care" },
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

  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<"all" | CustomerAuditRow["kind"]>("all");
  const [timeRange, setTimeRange] = useState<"all" | "7d" | "30d" | "this_month" | "custom">("all");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  
  // Trạng thái thu gọn nhóm ngày (mặc định rỗng = TẤT CẢ MẶC ĐỊNH MỞ RỘNG)
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

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

  const kindCounts = useMemo(() => {
    if (!rows) return { all: 0, profile: 0, order: 0, quote: 0, care: 0 };
    const counts = { all: rows.length, profile: 0, order: 0, quote: 0, care: 0 };
    for (const r of rows) {
      if (counts[r.kind] !== undefined) {
        counts[r.kind]++;
      }
    }
    return counts;
  }, [rows]);

  const filteredRows = useMemo(() => {
    if (!rows) return [];
    const normSearch = search
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D");

    return rows.filter((r) => {
      if (kindFilter !== "all" && r.kind !== kindFilter) return false;

      // Lọc Khoảng thời gian
      if (timeRange !== "all" && r.at) {
        const d = new Date(r.at);
        if (!Number.isNaN(d.getTime())) {
          const now = Date.now();
          if (timeRange === "7d") {
            const cutoff = now - 7 * 86400 * 1000;
            if (d.getTime() < cutoff) return false;
          } else if (timeRange === "30d") {
            const cutoff = now - 30 * 86400 * 1000;
            if (d.getTime() < cutoff) return false;
          } else if (timeRange === "this_month") {
            const first = new Date();
            first.setDate(1);
            first.setHours(0, 0, 0, 0);
            if (d.getTime() < first.getTime()) return false;
          } else if (timeRange === "custom") {
            if (startDate) {
              const s = new Date(startDate);
              s.setHours(0, 0, 0, 0);
              if (d.getTime() < s.getTime()) return false;
            }
            if (endDate) {
              const e = new Date(endDate);
              e.setHours(23, 59, 59, 999);
              if (d.getTime() > e.getTime()) return false;
            }
          }
        }
      }

      if (normSearch) {
        const textToSearch = `${r.title || ""} ${r.detail || ""} ${r.action || ""} ${r.actor_name || ""} ${AUDIT_KIND_META[r.kind]?.label || ""}`
          .toLowerCase()
          .normalize("NFD")
          .replace(/[\u0300-\u036f]/g, "")
          .replace(/đ/g, "d")
          .replace(/Đ/g, "D");
        if (!textToSearch.includes(normSearch)) return false;
      }

      return true;
    });
  }, [rows, kindFilter, timeRange, startDate, endDate, search]);

  const totalItems = filteredRows.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const currentPage = Math.min(page, totalPages);

  const paginatedRows = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredRows.slice(start, start + pageSize);
  }, [filteredRows, currentPage, pageSize]);

  const groupedPaginatedRows = useMemo(() => {
    return groupAuditRowsByDate(paginatedRows);
  }, [paginatedRows]);

  const areAllCollapsed = useMemo(() => {
    if (groupedPaginatedRows.length === 0) return false;
    return groupedPaginatedRows.every((g) => !!collapsedGroups[g.dateKey]);
  }, [groupedPaginatedRows, collapsedGroups]);

  function toggleGroup(dateKey: string) {
    setCollapsedGroups((prev) => ({
      ...prev,
      [dateKey]: !prev[dateKey],
    }));
  }

  function toggleAllGroups() {
    if (areAllCollapsed) {
      setCollapsedGroups({});
    } else {
      const next: Record<string, boolean> = {};
      for (const g of groupedPaginatedRows) {
        next[g.dateKey] = true;
      }
      setCollapsedGroups(next);
    }
  }

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

  const filterOptions: Array<{ key: "all" | CustomerAuditRow["kind"]; label: string; icon?: JSX.Element }> = [
    { key: "all", label: "Tất cả" },
    { key: "order", label: "Đơn hàng", icon: <Package size={13} /> },
    { key: "quote", label: "Báo giá", icon: <FileText size={13} /> },
    { key: "profile", label: "Hồ sơ", icon: <PencilLine size={13} /> },
    { key: "care", label: "Chăm sóc", icon: <HeartHandshake size={13} /> },
  ];

  const startItemIndex = totalItems > 0 ? (currentPage - 1) * pageSize + 1 : 0;
  const endItemIndex = Math.min(currentPage * pageSize, totalItems);

  return (
    <div className="kh__tl-v2">
      {/* Sleek Toolbar: Search, Time Range & Filter Segment Bar */}
      <div className="kh__tl-toolbar">
        <div className="kh__tl-toolbar-row">
          <div className="kh__tl-search-wrap">
            <Search size={14} className="kh__tl-search-icon" aria-hidden="true" />
            <input
              type="text"
              className="kh__tl-search-input"
              placeholder="Tìm sự kiện, mã đơn/báo giá, người thực hiện..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
            {search && (
              <button
                type="button"
                className="kh__tl-search-clear"
                title="Xóa tìm kiếm"
                onClick={() => {
                  setSearch("");
                  setPage(1);
                }}
              >
                <X size={13} />
              </button>
            )}
          </div>

          <div className="kh__tl-controls-right">
            <select
              className="kh__tl-range-select"
              value={timeRange}
              aria-label="Khoảng thời gian"
              onChange={(e) => {
                setTimeRange(e.target.value as any);
                setPage(1);
              }}
            >
              <option value="all">Tất cả thời gian</option>
              <option value="7d">7 ngày qua</option>
              <option value="30d">30 ngày qua</option>
              <option value="this_month">Tháng này</option>
              <option value="custom">Tùy chọn ngày...</option>
            </select>

            {timeRange === "custom" && (
              <div className="kh__tl-custom-dates">
                <input
                  type="date"
                  className="kh__tl-date-input"
                  value={startDate}
                  onChange={(e) => {
                    setStartDate(e.target.value);
                    setPage(1);
                  }}
                  title="Từ ngày"
                />
                <span className="kh__muted" style={{ fontSize: "12px" }}>-</span>
                <input
                  type="date"
                  className="kh__tl-date-input"
                  value={endDate}
                  onChange={(e) => {
                    setEndDate(e.target.value);
                    setPage(1);
                  }}
                  title="Đến ngày"
                />
              </div>
            )}

            {groupedPaginatedRows.length > 0 && (
              <button
                type="button"
                className="kh__tl-toggle-all-btn"
                onClick={toggleAllGroups}
                title={areAllCollapsed ? "Mở rộng toàn bộ nhóm ngày" : "Thu gọn toàn bộ nhóm ngày"}
              >
                {areAllCollapsed ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
                <span>{areAllCollapsed ? "Mở tất cả" : "Thu gọn tất cả"}</span>
              </button>
            )}

            <div className="kh__tl-counter-badge">
              {search || kindFilter !== "all" || timeRange !== "all" ? (
                <span>
                  <strong>{totalItems}</strong> / {rows.length}
                </span>
              ) : (
                <span>
                  <strong>{rows.length}</strong> sự kiện
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="kh__tl-toolbar-row" style={{ marginTop: "4px" }}>
          <div className="kh__tl-filters" role="tablist" aria-label="Lọc theo loại sự kiện">
            {filterOptions.map((opt) => {
              const count = kindCounts[opt.key];
              const isActive = kindFilter === opt.key;
              return (
                <button
                  key={opt.key}
                  type="button"
                  className={`kh__tl-chip${isActive ? " is-active" : ""}`}
                  onClick={() => {
                    setKindFilter(opt.key);
                    setPage(1);
                  }}
                >
                  {opt.icon}
                  <span>{opt.label}</span>
                  {count > 0 && <span className="kh__tl-chip-count">{count}</span>}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Empty filter result */}
      {filteredRows.length === 0 ? (
        <div className="kh__empty-panel kh__tl-empty">
          <p className="kh__empty-title">Không tìm thấy sự kiện nào</p>
          <p className="kh__muted">
            Không có nhật ký nào phù hợp với điều kiện tìm kiếm hoặc bộ lọc hiện tại.
          </p>
          <Button
            variant="secondary"
            onClick={() => {
              setSearch("");
              setKindFilter("all");
              setTimeRange("all");
              setStartDate("");
              setEndDate("");
              setPage(1);
            }}
          >
            Xóa tìm kiếm &amp; bộ lọc
          </Button>
        </div>
      ) : (
        <>
          {/* Scrollable Timeline Body Container */}
          <div className="kh__tl-scroll-body">
            {/* Vertical Timeline Tree */}
            <div className="kh__tl-tree">
              {groupedPaginatedRows.map((group) => {
                const isExpanded = !collapsedGroups[group.dateKey];

                return (
                  <div key={`group-${group.dateKey}`} className="kh__tl-date-group">
                    <div
                      className="kh__tl-date-header"
                      onClick={() => toggleGroup(group.dateKey)}
                      title={isExpanded ? "Bấm để thu gọn" : "Bấm để mở rộng"}
                    >
                      <Calendar size={13} />
                      <span>{group.dateLabel}</span>
                      <span className="kh__tl-date-count">({group.items.length})</span>
                      <ChevronDown size={13} className={`kh__tl-header-chevron${isExpanded ? " is-expanded" : ""}`} />
                    </div>

                    {isExpanded && (
                      <div className="kh__tl-group-items">
                        {group.items.map((r, i) => {
                          const meta = AUDIT_KIND_META[r.kind];
                          const drillable = (r.ref_type === "quotation" || r.ref_type === "order") && r.ref_id != null;
                          const initials = r.actor_name ? getInitials(r.actor_name) : null;
                          const itemTime = fmtTimeOnly(r.at);

                          return (
                            <div
                              key={`${r.kind}-${r.ref_id ?? "p"}-${i}`}
                              className={`kh__tl-item-v2${drillable ? " is-drillable" : ""}`}
                              onClick={drillable ? () => onDrill(r.ref_type as "order" | "quotation", r.ref_id!) : undefined}
                              tabIndex={drillable ? 0 : undefined}
                              onKeyDown={
                                drillable ? (e) => e.key === "Enter" && onDrill(r.ref_type as "order" | "quotation", r.ref_id!) : undefined
                              }
                              title={drillable ? `Mở chi tiết ${r.title}` : undefined}
                            >
                              <div className={`kh__tl-node-v2 ${meta.nodeCls}`} aria-hidden="true">
                                {meta.icon}
                              </div>

                              <div className="kh__tl-card-v2">
                                <div className="kh__tl-card-row">
                                  <div className="kh__tl-card-left">
                                    <h4 className="kh__tl-card-title">{r.title}</h4>
                                    {!r.title.toLowerCase().startsWith(meta.label.toLowerCase()) && (
                                      <span className="kh__tl-kind-label">{meta.label}</span>
                                    )}
                                    {renderAuditDetailTags(r.detail)}
                                  </div>

                                  <div className="kh__tl-card-right">
                                    {r.actor_name && (
                                      <div className="kh__tl-actor-chip" title={`Thực hiện bởi ${r.actor_name}`}>
                                        <div className="kh__tl-actor-avatar">{initials}</div>
                                        <span>{r.actor_name}</span>
                                      </div>
                                    )}
                                    <span className="kh__tl-card-time" title={fmtDateTime(r.at)}>
                                      <Clock size={11} /> {itemTime}
                                    </span>
                                    {drillable && (
                                      <span className="kh__tl-drill-link" title="Xem chi tiết">
                                        Xem chi tiết <ChevronRight size={13} />
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 || totalItems > 5 ? (
            <div className="kh__tl-pagination">
              <div className="kh__tl-page-info">
                <span>
                  Hiển thị <strong>{startItemIndex}–{endItemIndex}</strong> trong tổng số <strong>{totalItems}</strong> sự kiện
                </span>
              </div>
              <div className="kh__tl-page-controls">
                <div className="kh__tl-size-select">
                  <span className="kh__muted" style={{ fontSize: "12px" }}>Hiển thị:</span>
                  <select
                    className="kh__tl-select"
                    value={pageSize}
                    onChange={(e) => {
                      setPageSize(Number(e.target.value));
                      setPage(1);
                    }}
                  >
                    <option value={5}>5</option>
                    <option value={10}>10</option>
                    <option value={20}>20</option>
                    <option value={50}>50</option>
                  </select>
                </div>

                <div className="kh__tl-nav-btns">
                  <button
                    type="button"
                    className="kh__tl-nav-btn"
                    disabled={currentPage <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    title="Trang trước"
                  >
                    <ChevronLeft size={14} />
                  </button>
                  <span className="kh__tl-page-num">
                    Trang {currentPage} / {totalPages}
                  </span>
                  <button
                    type="button"
                    className="kh__tl-nav-btn"
                    disabled={currentPage >= totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    title="Trang sau"
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

// --- Nhãn thủ công (#7: sales gán tay để phân loại chăm sóc) --------------------


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

/** Modal "Gắn thẻ" 2.0: Fluid Vibrant Tag Cloud, Omni Search & Create bar thông minh,
 *  đa sắc màu hiện đại, tối giản không gian và thao tác tức thì. */
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
  const canUpdate = useCan()("khach_hang", "update");
  // KHO nhãn từ server (`customer_tag_catalog`) — thay cho mảng 13 chuỗi viết cứng cũ. Giữ cả
  // `so_khach` để hộp thoại xoá hỏi được bằng số thật thay vì "bạn có chắc không".
  const [kho, setKho] = useState<KhoNhanRow[]>([]);
  const [customs, setCustoms] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(current.map((t) => t.label)),
  );
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [xoaNhan, setXoaNhan] = useState<KhoNhanRow | null>(null);

  const napKho = useCallback(() => {
    if (!token) return;
    api.customers.tagKho(token).then((r) => setKho(r.items)).catch(() => setKho([]));
  }, [token]);
  useEffect(() => napKho(), [napKho]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  /** Số khách đang mang từng nhãn — tra theo nhãn hạ chữ, để hỏi trước khi xoá. */
  const soKhachTheoNhan = useMemo(() => {
    const m = new Map<string, KhoNhanRow>();
    for (const r of kho) m.set(r.label.toLowerCase(), r);
    return m;
  }, [kho]);

  // Danh sách tất cả nhãn duy nhất (case-insensitive dedup).
  // `current` vẫn phải góp mặt: khách có thể đang mang một nhãn mà kho chưa kịp nạp xong, thiếu nó
  // thì chip đang bật biến khỏi lưới và cú Lưu kế tiếp gỡ mất nhãn của khách.
  const allLabels = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const l of [...kho.map((r) => r.label), ...current.map((t) => t.label), ...customs]) {
      const key = l.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        out.push(l);
      }
    }
    return out;
  }, [kho, current, customs]);

  // Bộ lọc thẻ theo từ khoá tìm kiếm
  const filteredLabels = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return allLabels;
    return allLabels.filter((l) => l.toLowerCase().includes(q));
  }, [allLabels, query]);

  const exactMatchExists = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return allLabels.some((l) => l.toLowerCase() === q);
  }, [allLabels, query]);

  function toggle(label: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      const existing = [...next].find((l) => l.toLowerCase() === label.toLowerCase());
      if (existing) next.delete(existing);
      else next.add(label);
      return next;
    });
  }

  function clearAll() {
    setSelected(new Set());
  }

  function handleCreateOrAdd() {
    const label = query.trim().replace(/\s+/g, " ");
    if (!label) return;
    if (label.length > 50) {
      setError("Nhãn tối đa 50 ký tự.");
      return;
    }
    setError(null);
    const existing = allLabels.find((l) => l.toLowerCase() === label.toLowerCase());
    if (!existing) setCustoms((prev) => [...prev, label]);
    setSelected((prev) => {
      const next = new Set(prev);
      next.add(existing ?? label);
      return next;
    });
    setQuery("");
  }

  async function save() {
    if (!token || busy) return;
    setBusy(true);
    setError(null);
    try {
      const currentByLower = new Map(current.map((t) => [t.label.toLowerCase(), t]));
      const selectedLower = new Set([...selected].map((l) => l.toLowerCase()));
      
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

  const selectedCount = selected.size;
  const avatarClass = customerName ? getKhAvatarClass(customerName) : "kh__avatar--moss";
  const initials = customerName ? getInitials(customerName) : "KH";

  return (
    <div className="kh__overlay kh__overlay--blur" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        className="kh__dialog card kh__tagmodal-v3"
        role="dialog"
        aria-modal="true"
        aria-label="Gắn thẻ khách hàng"
      >
        {/* Header Modal với Avatar Khách hàng */}
        <div className="kh__tagmodal-head">
          <div className="kh__tagmodal-head-left">
            <div className={`kh__tagmodal-avatar ${avatarClass}`}>{initials}</div>
            <div>
              <div className="kh__tagmodal-subhead">Nhận diện &amp; Phân loại CRM</div>
              <h2 className="kh__tagmodal-title">{customerName || "Khách hàng"}</h2>
            </div>
          </div>
          <button type="button" className="kh__close" aria-label="Đóng" onClick={onClose}>
            <X size={16} strokeWidth={2} />
          </button>
        </div>

        {/* Body Modal */}
        <div className="kh__dialog-body kh__tagmodal-body">
          {/* Thanh Tìm kiếm & Tạo thẻ Omni-Input */}
          <div className="kh__tag-omni-bar">
            <Search size={15} className="kh__tag-omni-ic" />
            <input
              className="kh__tag-omni-input"
              placeholder="Tìm thẻ hoặc gõ tên để tạo mới (Enter)…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleCreateOrAdd();
                }
              }}
            />
            {query && (
              <button
                type="button"
                className="kh__tag-omni-clear"
                onClick={() => setQuery("")}
                title="Xóa tìm kiếm"
              >
                <X size={13} />
              </button>
            )}
          </div>

          {/* Tag Cloud đa sắc màu liền mạch */}
          <div className="kh__tagcloud-fluid">
            {filteredLabels.map((label) => {
              const on = [...selected].some((l) => l.toLowerCase() === label.toLowerCase());
              const tone = tagTone(label);
              // Chỉ nhãn ĐÃ Ở TRONG KHO mới xoá được. Nhãn vừa gõ ở ô trên (`customs`) chưa có id
              // — nó chỉ thành dòng thật sau khi Lưu, nên chưa có gì để xoá.
              const dongKho = soKhachTheoNhan.get(label.toLowerCase());
              return (
                <span key={label} className="kh__tagpill-wrap">
                  <button
                    type="button"
                    className={`kh__tagpill-v3${on ? " is-on" : ""} kh__tagpill--${tone}`}
                    aria-pressed={on}
                    onClick={() => toggle(label)}
                  >
                    {on ? (
                      <Check size={13} className="kh__tagpill-check" strokeWidth={2.5} />
                    ) : (
                      <span className="kh__tagpill-dot" />
                    )}
                    <span>{label}</span>
                  </button>
                  {canUpdate && dongKho && (
                    // Nút xoá NẰM NGOÀI pill, không lồng trong nó: button trong button là HTML
                    // không hợp lệ, trình duyệt tự gỡ lồng và cú bấm rơi nhầm sang nút cha.
                    <button
                      type="button"
                      className="kh__tagpill-del"
                      title={`Xoá nhãn "${label}" khỏi kho`}
                      aria-label={`Xoá nhãn ${label} khỏi kho`}
                      onClick={() => setXoaNhan(dongKho)}
                    >
                      <X size={11} strokeWidth={2.5} />
                    </button>
                  )}
                </span>
              );
            })}

            {/* Pill gợi ý tạo thẻ mới khi không khớp hoàn toàn */}
            {!exactMatchExists && query.trim() && (
              <button
                type="button"
                className="kh__tagpill-v3 kh__tagpill-create"
                onClick={handleCreateOrAdd}
              >
                <Plus size={13} strokeWidth={2.5} />
                <span>Tạo mới "<strong>{query.trim()}</strong>"</span>
              </button>
            )}
          </div>

          {error && <div className="banner banner--error" role="alert">{error}</div>}

          {/* Dải Tóm Tắt (Summary Bar) các thẻ đã chọn */}
          {selectedCount > 0 && (
            <div className="kh__tag-summary-bar">
              <div className="kh__tag-summary-left">
                <span className="kh__tag-summary-label">Đã chọn ({selectedCount}):</span>
                <div className="kh__tag-summary-chips">
                  {[...selected].map((label) => (
                    <span key={label} className={`kh__tag-summary-chip kh__tagchip--${tagTone(label)}`}>
                      {label}
                      <button
                        type="button"
                        className="kh__tag-summary-del"
                        onClick={(e) => {
                          e.stopPropagation();
                          toggle(label);
                        }}
                        title="Bỏ chọn"
                      >
                        <X size={10} />
                      </button>
                    </span>
                  ))}
                </div>
              </div>
              <button type="button" className="kh__tag-clear-btn" onClick={clearAll}>
                Bỏ chọn tất cả
              </button>
            </div>
          )}

          {/* Footer Action buttons */}
          <div className="kh__dialog-actions kh__tagmodal-actions">
            <Button variant="ghost" onClick={onClose}>
              Huỷ
            </Button>
            <Button variant="primary" onClick={save} loading={busy}>
              {selectedCount > 0 ? `Lưu ${selectedCount} thẻ` : "Lưu thay đổi"}
            </Button>
          </div>
        </div>
      </div>

      {/* Xoá nhãn khỏi KHO — khác hẳn bỏ tick (bỏ tick chỉ gỡ nhãn khỏi riêng khách này).
          Hỏi kèm SỐ KHÁCH THẬT chứ không "bạn có chắc không": con số là thứ duy nhất giúp người
          bấm biết mình sắp làm hỏng bao nhiêu. */}
      <ConfirmDialog
        open={xoaNhan !== null}
        danger
        title={`Xoá nhãn "${xoaNhan?.label ?? ""}" khỏi kho?`}
        message={
          xoaNhan && xoaNhan.so_khach > 0
            ? `${xoaNhan.so_khach} khách đang mang nhãn này — xoá thì nhãn rơi khỏi cả ${xoaNhan.so_khach} khách đó. `
              + "Không khôi phục được."
            : "Chưa khách nào mang nhãn này, xoá là an toàn."
        }
        confirmLabel="Xoá nhãn"
        busy={busy}
        onCancel={() => setXoaNhan(null)}
        onConfirm={async () => {
          if (!token || !xoaNhan) return;
          setBusy(true);
          setError(null);
          try {
            await api.customers.xoaNhanKho(token, xoaNhan.id);
            // Gỡ khỏi ô đang chọn luôn: giữ lại thì bấm Lưu sẽ gán lại đúng nhãn vừa xoá, và nó
            // tự chui về kho qua `add_tag` — xoá xong lại mọc.
            setSelected((prev) => {
              const next = new Set(prev);
              for (const l of next) {
                if (l.toLowerCase() === xoaNhan.label.toLowerCase()) next.delete(l);
              }
              return next;
            });
            setCustoms((prev) =>
              prev.filter((l) => l.toLowerCase() !== xoaNhan.label.toLowerCase()));
            setXoaNhan(null);
            napKho();
          } catch (err) {
            setError(err instanceof ApiError ? err.message : "Xoá nhãn không thành công.");
          } finally {
            setBusy(false);
          }
        }}
      />
    </div>
  );
}

// --- Modal Điều chuyển & Bàn giao Khách hàng (Handover Hub) -------------------

/** Modal Điều chuyển & Bàn giao toàn bộ khách hàng giữa 2 nhân sự kinh doanh */
function CustomerReassignModal({
  open,
  sales,
  fromSale,
  toSale,
  setFromSale,
  setToSale,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  sales: SaleOption[];
  fromSale: number | null;
  toSale: number | null;
  setFromSale: (v: number | null) => void;
  setToSale: (v: number | null) => void;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [countdown, setCountdown] = useState(5);

  useEffect(() => {
    if (!open) {
      setCountdown(5);
      return;
    }
    setCountdown(5);
    const timer = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          clearInterval(timer);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;

  const sourceSale = sales.find((s) => s.id === fromSale);
  const targetSale = sales.find((s) => s.id === toSale);
  const isConfirmDisabled = fromSale == null || toSale == null || fromSale === toSale || countdown > 0;
  const sourceCount = sourceSale?.so_kh ?? 0;
  const targetCount = targetSale?.so_kh ?? 0;

  return (
    <div className="kh__overlay kh__overlay--blur" onMouseDown={(e) => e.target === e.currentTarget && !busy && onCancel()}>
      <div
        className="kh__dialog card kh__reassign-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Điều chuyển khách hàng"
      >
        {/* Header Modal */}
        <div className="kh__reassign-head">
          <div className="kh__reassign-head-left">
            <div className="kh__reassign-head-icon">
              <ArrowLeftRight size={18} />
            </div>
            <div>
              <h2 className="kh__reassign-title">Điều chuyển &amp; Bàn giao khách hàng</h2>
              <div className="kh__reassign-subtitle">
                Bàn giao quyền phụ trách danh bạ giữa các nhân sự kinh doanh
              </div>
            </div>
          </div>
          <button type="button" className="kh__close" aria-label="Đóng" onClick={onCancel} disabled={busy}>
            <X size={16} strokeWidth={2} />
          </button>
        </div>

        {/* Body Modal */}
        <div className="kh__dialog-body kh__reassign-body">
          {/* Safety Notice Card */}
          <div className="kh__reassign-notice">
            <ShieldAlert size={16} className="kh__reassign-notice-ic" />
            <div className="kh__reassign-notice-text">
              <strong>Lưu ý bàn giao:</strong> Toàn bộ khách hàng của nhân viên nguồn sẽ được chuyển giao sang nhân viên tiếp nhận. Quyền chăm sóc và lịch sử giao dịch sẽ được bàn giao đầy đủ.
            </div>
          </div>

          {/* Interactive Transfer Duo */}
          <div className="kh__transfer-duo">
            {/* Cột Nguồn */}
            <div className="kh__transfer-col kh__transfer-col--source">
              <label className="kh__transfer-label">
                <Users size={13} />
                <span>Từ nhân viên (Nguồn)</span>
              </label>
              <Select
                ariaLabel="Nhân viên nguồn"
                portal
                value={fromSale}
                placeholder="— Chọn nhân viên nguồn —"
                onChange={(v) => setFromSale(v)}
                options={sales
                  .filter((s) => (s.so_kh ?? 0) > 0)
                  .map((s) => ({
                    value: s.id,
                    label: s.name,
                    sub: moTaSale(s),
                    hint: `${s.so_kh} KH`,
                  }))}
              />

              {sourceSale ? (
                <div className="kh__transfer-card">
                  <div className="kh__avatar-wrapper">
                    <div className={`kh__avatar ${getKhAvatarClass(sourceSale.name)}`}>
                      {getInitials(sourceSale.name)}
                    </div>
                  </div>
                  <div className="kh__transfer-card-info">
                    <div className="kh__transfer-card-name">{sourceSale.name}</div>
                    <div className="kh__transfer-card-role">{moTaSale(sourceSale) || "NV Kinh doanh"}</div>
                    <div className="kh__transfer-card-meta">
                      <span className="kh__transfer-count-badge">
                        Đang giữ: <strong>{sourceCount} KH</strong>
                      </span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="kh__transfer-card-empty">Chọn nhân viên có khách cần bàn giao</div>
              )}
            </div>

            {/* Mũi tên chuyển dịch */}
            <div className="kh__transfer-arrow-hub">
              <div className="kh__transfer-arrow-pill">
                {sourceCount > 0 ? `${sourceCount} KH` : "Bàn giao"}
              </div>
              <div className="kh__transfer-arrow-ic">
                <ArrowRight size={16} />
              </div>
            </div>

            {/* Cột Đích */}
            <div className="kh__transfer-col kh__transfer-col--target">
              <label className="kh__transfer-label">
                <ShieldCheck size={13} />
                <span>Sang nhân viên (Đích)</span>
              </label>
              <Select
                ariaLabel="Nhân viên đích"
                portal
                value={toSale}
                placeholder="— Chọn nhân viên đích —"
                onChange={(v) => setToSale(v)}
                options={sales
                  .filter((s) => s.id !== fromSale && s.co_the_gan !== false)
                  .map((s) => ({
                    value: s.id,
                    label: s.name,
                    sub: moTaSale(s),
                    hint: s.so_kh != null ? `${s.so_kh} KH` : undefined,
                  }))}
              />

              {targetSale ? (
                <div className="kh__transfer-card">
                  <div className="kh__avatar-wrapper">
                    <div className={`kh__avatar ${getKhAvatarClass(targetSale.name)}`}>
                      {getInitials(targetSale.name)}
                    </div>
                  </div>
                  <div className="kh__transfer-card-info">
                    <div className="kh__transfer-card-name">{targetSale.name}</div>
                    <div className="kh__transfer-card-role">{moTaSale(targetSale) || "NV Tiếp nhận"}</div>
                    <div className="kh__transfer-card-meta">
                      <span className="kh__transfer-count-badge">
                        Hiện có: <strong>{targetCount} KH</strong>
                      </span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="kh__transfer-card-empty">Chọn nhân viên tiếp nhận danh bạ</div>
              )}
            </div>
          </div>

          {/* Impact Preview Card */}
          {sourceSale && targetSale && (
            <div className="kh__reassign-impact">
              <div className="kh__reassign-impact-title">
                <CheckCircle2 size={14} className="kh__reassign-impact-ic" />
                <span>Dự kiến biến động sau khi bàn giao:</span>
              </div>
              <div className="kh__reassign-impact-grid">
                <div className="kh__reassign-impact-box">
                  <span className="kh__reassign-impact-sub">Nguồn: <strong>{sourceSale.name}</strong></span>
                  <div className="kh__reassign-impact-val">
                    <span>{sourceCount} KH</span>
                    <ArrowRight size={12} />
                    <strong className="kh__reassign-impact-zero">0 KH</strong>
                    <span className="kh__reassign-impact-subtag">(Bàn giao hết)</span>
                  </div>
                </div>
                <div className="kh__reassign-impact-box">
                  <span className="kh__reassign-impact-sub">Đích: <strong>{targetSale.name}</strong></span>
                  <div className="kh__reassign-impact-val">
                    <span>{targetCount} KH</span>
                    <ArrowRight size={12} />
                    <strong className="kh__reassign-impact-plus">{targetCount + sourceCount} KH</strong>
                    <span className="kh__reassign-impact-plustag">(+{sourceCount} KH)</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {error && <div className="banner banner--error" role="alert">{error}</div>}

          {/* Action buttons */}
          <div className="kh__dialog-actions kh__reassign-actions">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={onCancel}
              disabled={busy}
            >
              Huỷ
            </button>
            <button
              type="button"
              className="kh__reassign-confirm-btn"
              onClick={onConfirm}
              disabled={busy || isConfirmDisabled}
            >
              {busy ? (
                "Đang điều chuyển…"
              ) : countdown > 0 ? (
                <>
                  <Clock size={13} />
                  <span>Xác nhận bàn giao ({countdown}s)</span>
                </>
              ) : (
                <>
                  <ArrowLeftRight size={14} />
                  <span>Xác nhận bàn giao ngay</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Modal Chuyển hàng loạt khách hàng đã chọn sang nhân viên tiếp nhận */
function BulkReassignModal({
  open,
  selectedCount,
  sales,
  bulkTarget,
  setBulkTarget,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  selectedCount: number;
  sales: SaleOption[];
  bulkTarget: number | null;
  setBulkTarget: (v: number | null) => void;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [countdown, setCountdown] = useState(5);

  useEffect(() => {
    if (!open) {
      setCountdown(5);
      return;
    }
    setCountdown(5);
    const timer = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          clearInterval(timer);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;

  const targetSale = sales.find((s) => s.id === bulkTarget);
  const isConfirmDisabled = bulkTarget == null || countdown > 0;
  const targetCount = targetSale?.so_kh ?? 0;

  return (
    <div className="kh__overlay kh__overlay--blur" onMouseDown={(e) => e.target === e.currentTarget && !busy && onCancel()}>
      <div
        className="kh__dialog card kh__reassign-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Chuyển khách hàng đã chọn"
      >
        {/* Header Modal */}
        <div className="kh__reassign-head">
          <div className="kh__reassign-head-left">
            <div className="kh__reassign-head-icon">
              <Users size={18} />
            </div>
            <div>
              <h2 className="kh__reassign-title">Chuyển {selectedCount} khách hàng đã chọn</h2>
              <div className="kh__reassign-subtitle">
                Gán nhân viên phụ trách mới cho danh sách khách hàng đang chọn
              </div>
            </div>
          </div>
          <button type="button" className="kh__close" aria-label="Đóng" onClick={onCancel} disabled={busy}>
            <X size={16} strokeWidth={2} />
          </button>
        </div>

        {/* Body Modal */}
        <div className="kh__dialog-body kh__reassign-body">
          {/* Safety Notice Card */}
          <div className="kh__reassign-notice">
            <ShieldAlert size={16} className="kh__reassign-notice-ic" />
            <div className="kh__reassign-notice-text">
              <strong>Lưu ý:</strong> <strong>{selectedCount} khách hàng</strong> đang chọn sẽ được cập nhật người phụ trách sang nhân sự được chỉ định bên dưới.
            </div>
          </div>

          {/* Chọn nhân viên đích */}
          <div className="kh__bulk-target-box">
            <label className="kh__transfer-label">
              <ShieldCheck size={13} />
              <span>Chỉ định nhân viên tiếp nhận (Đích)</span>
            </label>
            <Select
              ariaLabel="Nhân viên đích"
              portal
              value={bulkTarget}
              placeholder="— Chọn nhân viên tiếp nhận —"
              onChange={(v) => setBulkTarget(v)}
              options={sales
                .filter((s) => s.co_the_gan !== false)
                .map((s) => ({
                  value: s.id,
                  label: s.name,
                  sub: moTaSale(s),
                  hint: s.so_kh != null ? `${s.so_kh} KH` : undefined,
                }))}
            />

            {targetSale && (
              <div className="kh__transfer-card" style={{ marginTop: "12px" }}>
                <div className="kh__avatar-wrapper">
                  <div className={`kh__avatar ${getKhAvatarClass(targetSale.name)}`}>
                    {getInitials(targetSale.name)}
                  </div>
                </div>
                <div className="kh__transfer-card-info">
                  <div className="kh__transfer-card-name">{targetSale.name}</div>
                  <div className="kh__transfer-card-role">{moTaSale(targetSale) || "NV Tiếp nhận"}</div>
                  <div className="kh__transfer-card-meta">
                    <span className="kh__transfer-count-badge">
                      Hiện có: <strong>{targetCount} KH</strong> ➔ Sau chuyển: <strong>{targetCount + selectedCount} KH</strong> (+{selectedCount} KH)
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {error && <div className="banner banner--error" role="alert">{error}</div>}

          {/* Action buttons */}
          <div className="kh__dialog-actions kh__reassign-actions">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={onCancel}
              disabled={busy}
            >
              Huỷ
            </button>
            <button
              type="button"
              className="kh__reassign-confirm-btn"
              onClick={onConfirm}
              disabled={busy || isConfirmDisabled}
            >
              {busy ? (
                "Đang điều chuyển…"
              ) : countdown > 0 ? (
                <>
                  <Clock size={13} />
                  <span>Xác nhận chuyển ({countdown}s)</span>
                </>
              ) : (
                <>
                  <Users size={14} />
                  <span>Xác nhận chuyển ngay</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

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
  if (level <= 0) {
    return (
      <span className="badge-sem badge-sem--moss">
        <CheckCircle2 size={11} /> Chưa đến hạn
      </span>
    );
  }
  return (
    <span className="kh__remind-badge-pill" title={days > 0 ? `Quá hạn ${days} ngày` : "Đến hạn hôm nay"}>
      <Clock size={11} /> Nhắc lần {level}{days > 0 ? ` (${days} ngày)` : ""}
    </span>
  );
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
                style={{ marginLeft: "auto", fontSize: 12 }}
                onClick={() => setShowCancelled((v) => !v)}
              >
                {showCancelled ? "Ẩn đã huỷ" : `Hiện đã huỷ (${cancelledCount})`}
              </button>
            )}
          </div>

          {visibleHistory.length === 0 ? (
            <p className="kh__muted kh__chart-empty" style={{ background: "var(--canvas)", border: "1px solid var(--rule-soft)", borderRadius: "var(--r-5)", padding: "var(--sp-6)", textAlign: "center" }}>
              Chưa có hoạt động nào — đặt hẹn ở lịch trên<span className="cc__hint-tick">, tick tròn khi làm xong</span> để lưu lịch sử.
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
                          <span className="kh__badge kh__badge--moss" style={{ fontSize: "12px", padding: "1px 6px", display: "inline-flex", alignItems: "center", gap: "2px", marginLeft: "6px" }}>
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
                      <span className="kh__badge kh__badge--moss" style={{ fontSize: "12px", padding: "1px 6px", display: "inline-flex", alignItems: "center", gap: "2px", marginLeft: "6px" }}>
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
                    <span className="kh__badge" style={{ fontSize: "12px", padding: "0 6px" }}>
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
  // Tra cứu tự động tên & địa chỉ công ty theo MST (VietQR public tax API)
  const [fetchingTax, setFetchingTax] = useState(false);
  const [taxLookupNote, setTaxLookupNote] = useState<string | null>(null);

  async function handleTaxLookup(overrideCode?: string) {
    const code = (overrideCode ?? form.tax_code).trim();
    if (!code || code.length < 10) {
      setErrors((e) => ({ ...e, tax_code: "Nhập MST 10 hoặc 13 số để tra cứu." }));
      return;
    }
    setFetchingTax(true);
    setTaxLookupNote(null);
    try {
      const res = await fetch(`https://api.vietqr.io/v2/business/${code}`);
      const json = await res.json();
      if (json.code === "00" && json.data) {
        const { name, address } = json.data;
        setForm((f) => ({
          ...f,
          name: name ? name : f.name,
          address: address ? address : f.address,
        }));
        setTaxLookupNote(`✓ Đã tra cứu thành công: ${name}`);
        setErrors((e) => ({ ...e, name: undefined, tax_code: undefined }));
        liveCheck();
      } else {
        setTaxLookupNote(json.desc || "Không tìm thấy dữ liệu doanh nghiệp từ MST này.");
      }
    } catch {
      setTaxLookupNote("Không kết nối được dịch vụ tra cứu MST. Vui lòng tự điền Tên & Địa chỉ.");
    } finally {
      setFetchingTax(false);
    }
  }

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
      <div className="kh__dialog card kh__dialog--hero" role="dialog" aria-modal="true" aria-label={title}>
        {/* Sleek Minimalist Header */}
        <div className="kh__dialog-head kh__dialog-head--hero">
          <div className="kh__dialog-title-wrap">
            <h2 className="kh__dialog-title">{title}</h2>
            <span className="kh__dialog-kind-chip">
              {form.customer_kind === "cong_ty" ? "Doanh nghiệp" : "Cá nhân"}
            </span>
          </div>
          <button type="button" className="kh__close" aria-label="Đóng" onClick={onClose}>
            <X size={16} strokeWidth={2} />
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
            <div className="kh__form-grid kh__form-grid--2col">
              {/* Hàng 1: Tên khách hàng (Left) & MST + Tra cứu (Right) */}
              <label className="field">
                <span className="field__label">
                  {form.customer_kind === "cong_ty" ? "Tên công ty / Tên khách hàng *" : "Họ và tên khách hàng *"}
                </span>
                <input
                  className="input"
                  placeholder={form.customer_kind === "cong_ty" ? "VD: Công ty TNHH Bao bì An Phát" : "VD: Nguyễn Văn A"}
                  value={form.name}
                  onChange={(e) => set("name", e.target.value)}
                  onBlur={liveCheck}
                  aria-invalid={!!errors.name}
                  autoFocus
                />
                {errors.name && <span className="kh__err" role="alert">{errors.name}</span>}
              </label>

              {form.customer_kind === "cong_ty" ? (
                <label className="field">
                  <div className="kh__field-label-bar">
                    <span className="field__label">Mã số thuế (MST)</span>
                    <button
                      type="button"
                      className="kh__tax-lookup-btn"
                      disabled={fetchingTax || !form.tax_code.trim()}
                      title="Tự động tra cứu Tên công ty & Địa chỉ từ dữ liệu Thuế công khai"
                      onClick={() => handleTaxLookup()}
                    >
                      {fetchingTax && <Loader2 size={12} className="kh__spin" />}
                      <span>{fetchingTax ? "Đang tra cứu…" : "Tra cứu MST"}</span>
                    </button>
                  </div>
                  <input
                    className="input"
                    placeholder="10 hoặc 13 chữ số MST (VD: 0101234567)"
                    value={form.tax_code}
                    onChange={(e) => set("tax_code", e.target.value)}
                    onBlur={() => {
                      liveCheck();
                      if (form.tax_code.trim().length >= 10 && !form.name.trim()) {
                        handleTaxLookup();
                      }
                    }}
                    aria-invalid={!!errors.tax_code}
                  />
                  {errors.tax_code && <span className="kh__err" role="alert">{errors.tax_code}</span>}
                  {taxLookupNote && (
                    <span className={`kh__tax-note${taxLookupNote.startsWith("✓") ? " is-success" : " is-warn"}`}>
                      {taxLookupNote}
                    </span>
                  )}
                </label>
              ) : (
                <label className="field">
                  <span className="field__label">Mã số thuế (nếu có)</span>
                  <input
                    className="input"
                    placeholder="Không bắt buộc đối với khách lẻ"
                    value={form.tax_code}
                    onChange={(e) => set("tax_code", e.target.value)}
                  />
                </label>
              )}

              {/* Hàng 2: Loại khách hàng (Left) & NV phụ trách (Right) */}
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
                <Select
                  ariaLabel="NV phụ trách"
                  portal
                  align="right"
                  disabled={saleLocked}
                  value={form.sale_user_id}
                  placeholder="— Mặc định (tôi) —"
                  onChange={(v) => set("sale_user_id", v ?? "")}
                  options={[
                    { value: "", label: "— Mặc định (tôi) —" },
                    ...sales
                      .filter((s) => s.co_the_gan !== false)
                      .map((s) => ({
                        value: String(s.id),
                        label: s.name,
                        sub: moTaSale(s),
                      })),
                  ]}
                />
                {saleLocked && (
                  <span className="kh__muted">
                    Mặc định là bạn; cần quyền “Điều chuyển” để gán cấp dưới.
                  </span>
                )}
              </label>

              {/* Hàng 3: Địa chỉ (Left) & Email (Right) */}
              <label className="field">
                <span className="field__label">
                  {form.customer_kind === "cong_ty" ? "Địa chỉ đăng ký thuế / xuất hóa đơn" : "Địa chỉ giao hàng / liên hệ"}
                </span>
                <input
                  className="input"
                  placeholder="Địa chỉ ghi trên hóa đơn tài chính…"
                  value={form.address}
                  onChange={(e) => set("address", e.target.value)}
                />
              </label>

              <label className="field">
                <span className="field__label">Email nhận hóa đơn điện tử</span>
                <input
                  className="input"
                  type="email"
                  placeholder="email@doanhnghiep.com"
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
                Huỷ <kbd className="kh__kbd">Esc</kbd>
              </Button>
              <Button type="submit" variant="primary" loading={saving}>
                {isEdit ? "Cập nhật khách hàng" : "Tạo khách hàng"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
