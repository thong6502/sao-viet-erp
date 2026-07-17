// Báo giá (Quotation / Quote) — spec-09, Phase 2B/2C/2D.
// Danh sách phiếu (mã+version, khách, tổng giá bán, trạng thái, hạn hiệu lực) + Tạo/Sửa
// (H-V-I structure, multi-quantity spreadsheet pricing table, version timeline, PDF preview & Order handoff).
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type EnumOption,
  type QuotationActivity,
  type QuotationDetail,
  type QuotationEnumsOut,
  type QuotationRow,
  type QuotationStats,
  type QuoteItemDetail,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { StatusTabs } from "../components/StatusTabs";
import svnLogoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import {
  AlertCircle,
  ArrowLeftRight,
  ArrowRight,
  ArrowUpFromLine,
  Ban,
  Check,
  ChevronLeft,
  Clock,
  ExternalLink,
  Eye,
  FileText,
  GitBranch,
  Link2,
  Lock,
  Pencil,
  Phone,
  Plus,
  Printer,
  Save,
  Send,
  ShieldCheck,
  User,
  X,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import "./bao-gia.css";

// Điều khoản MẶC ĐỊNH điền sẵn khi tạo báo giá (khớp DEFAULT_TERMS backend). Mỗi dòng = 1 điều
// khoản; bản in tự đánh số 1..N theo dòng. Sale sửa thoải mái trước khi gửi khách.
const DEFAULT_TERMS = [
  "Hiệu lực báo giá: áp dụng từ ngày báo giá cho đến khi có thông báo mới.",
  "Giá đã bao gồm chi phí vận chuyển đến kho của Quý khách.",
  "Đơn giá trong bảng chưa gồm thuế GTGT; thuế GTGT 10% được cộng ở phần tổng.",
  "Thời gian giao hàng: 7–10 ngày kể từ khi nhận đơn hàng.",
  "Thời hạn thanh toán: theo thỏa thuận.",
].join("\n");

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
  openQuoteId = null,
  navigate,
  eventTick = 0,
}: {
  openQuoteId?: number | null;
  navigate?: (id: string, params?: any) => void;
  /** Tăng 1 mỗi lần kênh SSE báo luồng duyệt đổi (AppShell giữ kênh DUY NHẤT, đẩy tick xuống đây).
   *  Vào deps của `load()` → danh sách + số đếm tab tự tươi, không phải F5. */
  eventTick?: number;
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

  const [detail, setDetail] = useState<QuotationDetail | null>(null);
  

  const [stats, setStats] = useState<QuotationStats | null>(null);

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
    // eventTick: SSE báo có trình duyệt / có quyết định → chạy lại cả list lẫn stats.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, q, statusFilter, sort, page, eventTick]);

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
            // "Đã duyệt" cũng tô đỏ: GĐ duyệt xong thì bóng sang chân sale — còn nằm đây là còn
            // việc (phải gửi khách), không phải trạng thái nghỉ.
            { key: "approved", label: "Đã duyệt", count: stats?.approved, tone: "alert" },
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

// Feed Hoạt động: action (audit backend) → [icon, lớp màu chấm, nhãn tiếng Việt].
// Nhãn chỉ tả VIỆC, KHÔNG ghim vai ("Giám đốc KD duyệt") — vai thật đi kèm tên người thao tác,
// backend ghi theo hồ sơ ("Ban giám đốc · Giám đốc · Nguyễn Văn Giám", xem actor_display.py).
const ACT_META: Record<string, [LucideIcon, string, string]> = {
  create_quote: [Plus, "rust", "Tạo báo giá"],
  update_quote: [Pencil, "steel", "Cập nhật báo giá"],
  change_order: [GitBranch, "rust", "Tạo phiên bản mới"],
  transition_pending_approval: [ArrowUpFromLine, "amber", "Trình duyệt"],
  quote_exception_approved: [Check, "moss", "Duyệt báo giá đặc thù"],
  quote_exception_rejected: [X, "signal", "Từ chối duyệt"],
  transition_sent: [Send, "steel", "Gửi khách"],
  transition_accepted: [Check, "moss", "Khách hàng đồng ý"],
  transition_rejected: [X, "signal", "Khách hàng từ chối"],
  transition_expired: [AlertCircle, "ash", "Hết hiệu lực"],
  transition_cancelled: [Ban, "ash", "Hủy báo giá"],
  transition_converted_to_order: [ArrowRight, "moss", "Lên đơn hàng"],
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
  // Lên đơn từ báo giá đã chốt → cần quyền TẠO ở module Đơn hàng bán (nút chỉ hiện khi có).
  const canCreateOrder = useCan()("don_hang_ban", "create");
  const [d, setD] = useState<QuotationDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [apprNote, setApprNote] = useState("");
  const [apprSaving, setApprSaving] = useState(false);

  // Margin sống (preview cục bộ trước khi persist) — chỉ dùng khi báo giá 1 dòng.
  const [draftMargin, setDraftMargin] = useState<number | null>(null);
  // Markup từng dòng khi đang gõ (đa dòng) — override tạm để preview.
  const [lineDraft, setLineDraft] = useState<Record<number, number>>({});
  // Chiết khấu (đồng) từng dòng khi đang gõ — override tạm để preview trước khi persist.
  const [discDraft, setDiscDraft] = useState<Record<number, number>>({});
  // P3 (redesign-bao-gia §6): popover MarginPicker (gói biên + slider) mở cho DÒNG nào (đa dòng).
  const [mkOpenLine, setMkOpenLine] = useState<number | null>(null);
  // P3: danh sách khách để CHỌN/ĐỔI khách ngay ở detail (khi còn nháp) — auto-fill lại liên hệ + ĐC giao.
  const [customers, setCustomers] = useState<{ id: number; name: string; code: string }[]>([]);

  const [compareOn, setCompareOn] = useState(false);
  const [showPrint, setShowPrint] = useState(false);

  // Điều khoản chỉnh tại chỗ (nháp) — 1 khối text, mỗi dòng = 1 điều khoản.
  const [termsText, setTermsText] = useState(DEFAULT_TERMS);
  const [validity, setValidity] = useState<number>(30);
  const [validUntilEdit, setValidUntilEdit] = useState<string>("");   // ngày hết hạn (editable)
  const [verNote, setVerNote] = useState("");

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
        setDiscDraft({});
        setTermsText(det.terms_text ?? DEFAULT_TERMS);
        setVerNote((det as any).change_reason ?? "");
        setValidUntilEdit(det.valid_until ?? "");
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
    // Chiết khấu (đồng) — dùng bản nháp đang gõ nếu có, chặn trong [0, giá bán] như backend.
    const discRaw = discDraft[it.id] != null ? discDraft[it.id] : it.discount_amount;
    const disc = Math.min(selling, Math.max(0, discRaw));
    const net = Math.max(0, selling - disc);
    const vat = (net * (it.vat_percent || 0)) / 100;
    return { m, cost, selling, disc, net, vat, final: net + vat, profit: net - cost, qty: it.quantity };
  }
  let costT = 0, netT = 0, vatT = 0, grandT = 0, qtyT = 0, discountT = 0;
  d.items.forEach((it) => {
    const c = calcItem(it);
    costT += c.cost; netT += c.net; vatT += c.vat; grandT += c.final; qtyT += c.qty; discountT += c.disc;
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
        terms_text: termsText,
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
  // Chiết khấu (đồng) theo DÒNG — persist qua cùng endpoint update line. Backend tự chặn [0, giá bán]
  // + tính lại subtotal/discount/final của version (cổng đặc thù soi trên số mới).
  function commitLineDiscount(itemId: number, val: number) {
    if (!editable) return;
    const v = Math.max(0, Math.round(val || 0));
    persistItems([{ id: itemId, discount_amount: v }]);
  }
  // Áp % chiết khấu cho DÒNG → quy ra tiền theo giá bán hiện tại của dòng rồi persist như trên.


  // P3: đổi khách ngay ở detail (khi nháp). BE tự điền lại ĐC giao mặc định + người liên hệ chính
  // của khách mới (redesign-bao-gia §4).
  async function changeCustomer(newId: number | null) {
    if (!token || !d) return;
    setBusy(true);
    setErr(null);
    try {
      await api.quotations.update(token, d.id, {
        customer_id: newId,
        valid_until: d.valid_until,
        terms_text: termsText,
        items: null,
      });
      await reload(d.id);
      onChanged();
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
        terms_text: termsText,
        items: null,
      });
      await reload(d.id);
      onChanged();
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

  // Khách đã chốt (accepted) → lên đơn hàng bán từ CHÍNH báo giá này (BE kéo dòng/giá/cọc; guard
  // 1 báo giá → 1 đơn). Xong điều hướng sang màn Đơn hàng bán, mở luôn đơn vừa tạo.
  async function createOrderFromQuote() {
    if (!token || !d) return;
    setBusy(true);
    setErr(null);
    try {
      const order = await api.orders.create(token, { source_type: "bao_gia", quotation_id: d.id });
      navigate?.("don-hang-ban", { openOrderId: order.id });
    } catch (e) {
      // BE trả 409 khi báo giá đã có đơn (message rõ) → hiện nguyên văn.
      setErr(e instanceof ApiError ? e.message : "Không tạo được đơn hàng từ báo giá này.");
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

  // ---- Follow-up handler ---------------------------------------------------
  function recordContact() {
    if (!d) return;
    const today = new Date().toLocaleDateString("vi-VN");
    setLastContact(today);
    lsSet(`bgv_contact_${d.code}`, today);
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
            <button type="button" className="btn btn--ghost btn--sm" onClick={onClose}><ChevronLeft size={15} /> Danh sách</button>
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
          <Button variant="secondary" onClick={() => setShowPrint(true)}><Printer size={15} /> Xem in</Button>
          {/* Gating quyền chi tiết: từ chối/gửi cần `manage_status`, chốt cần `approve`
              (server tính d.can_approve), tạo bản mới cần `requote` — thiếu quyền thì ẨN nút. */}
          {viewingLatest && d.status === "sent" && (
            <>
              {canManageStatus && (
                <Button variant="secondary" disabled={busy} onClick={() => doTransition("rejected")}><X size={15} /> Khách từ chối</Button>
              )}
              {d.can_approve && (
                <Button variant="primary" disabled={busy || !d.allowed_transitions.includes("accepted")} onClick={() => doTransition("accepted")}><Check size={15} /> Khách chốt</Button>
              )}
            </>
          )}
          {/* Nháp: báo giá ĐẶC THÙ phải TRÌNH DUYỆT (→ Chờ duyệt → GĐ Kinh doanh duyệt); báo giá
              THƯỜNG gửi khách thẳng. Backend chặn cứng 2 đường (redesign-bao-gia §3). */}
          {canManageStatus && viewingLatest && d.status === "draft" && d.exception_required &&
            d.allowed_transitions.includes("pending_approval") && (
            <Button
              variant="accent"
              disabled={busy || !d.customer_id}
              title={!d.customer_id ? "Vui lòng chọn khách hàng trước" : "Báo giá đặc thù — trình duyệt trước khi gửi khách"}
              onClick={() => doTransition("pending_approval")}
            ><ArrowUpFromLine size={15} /> Trình duyệt</Button>
          )}
          {/* Gửi khách (SALE tự gửi): báo giá THƯỜNG từ Nháp, HOẶC đặc thù ĐÃ ĐƯỢC GĐ DUYỆT (approved). */}
          {canManageStatus && viewingLatest && d.allowed_transitions.includes("sent") &&
            ((d.status === "draft" && !d.exception_required) || d.status === "approved") && (
            <Button
              variant="accent"
              disabled={busy || !d.customer_id}
              title={!d.customer_id ? "Vui lòng chọn khách hàng trước" : (d.status === "approved" ? "Giám đốc đã duyệt — gửi báo giá cho khách" : undefined)}
              onClick={() => doTransition("sent")}
            ><Send size={15} /> Gửi khách</Button>
          )}
          {canRequote && viewingLatest && d.status === "rejected" && d.allowed_transitions.includes("change_order") && (
            <Button variant="primary" disabled={busy} onClick={openRequote}><GitBranch size={15} /> Tạo phiên bản mới</Button>
          )}
          {/* Báo giá ĐÃ có đơn (1 báo giá → 1 đơn) → liên kết sang đơn, KHÔNG cho tạo nữa. */}
          {d.order_id != null && (
            <Button variant="secondary" onClick={() => navigate?.("don-hang-ban", { openOrderId: d.order_id })}>
              <ArrowRight size={15} /> Xem đơn hàng{d.order_no ? ` ${d.order_no}` : ""}
            </Button>
          )}
          {/* Khách đã chốt & CHƯA có đơn → lên đơn hàng bán từ báo giá này. */}
          {canCreateOrder && d.status === "accepted" && d.order_id == null && (
            <Button variant="primary" disabled={busy} onClick={createOrderFromQuote}><ArrowRight size={15} /> Tạo đơn hàng</Button>
          )}
        </div>
      </div>

      {err && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "14px" }}>{err}</div>
      )}
      {/* Báo giá BỊ TỪ CHỐI (khách HOẶC GĐ/TP từ chối đặc thù) → nhắc "Tạo phiên bản mới" để sửa. */}
      {d.status === "rejected" && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "14px" }}>
          {d.exception_decision === "rejected" ? (
            <span>Giám đốc/Trưởng phòng KD đã <b>từ chối</b> báo giá đặc thù{d.exception_note ? `: ${d.exception_note}` : ""}. Bấm <b>Tạo phiên bản mới</b> để sửa rồi trình duyệt lại.</span>
          ) : (
            <span><b>Khách hàng từ chối</b>{d.cancel_reason ? `: ${d.cancel_reason}` : ""}. Bấm <b>Tạo phiên bản mới</b> để báo lại giá mới.</span>
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
                <Lock size={15} /> <span>{multi ? "Báo giá nhiều dòng" : "Giá vốn"}</span>
                <span className="mono-tag lock">{multi ? `${d.items.length} phiếu tính giá` : "Khóa từ PTG"}</span>
              </div>
            </div>
            <div className="locked-banner">
              <ShieldCheck size={14} /> Giá vốn khóa theo phiếu tính giá đã duyệt · markup riêng từng dòng · giá đã gồm VAT.
            </div>
            <table className="bg-lines">
              <thead>
                <tr>
                  <th>Sản phẩm</th><th>SL</th><th>Giá vốn</th><th>Markup %</th><th>Chiết khấu (%)</th><th>Thành tiền (VAT)</th>
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
                      <td>
                        <input
                          className="ln-mk bg__mono"
                          type="number" min={0} max={100} step={0.5}
                          value={c.selling > 0 ? Math.round(((discDraft[it.id] ?? it.discount_amount) / c.selling) * 100) : 0}
                          disabled={!editable}
                          onChange={(e) => {
                            const pct = Number(e.target.value);
                            const amt = Math.round((c.selling * pct) / 100);
                            setDiscDraft((p) => ({ ...p, [it.id]: amt }));
                          }}
                          onBlur={(e) => {
                            const pct = Number(e.target.value);
                            const amt = Math.round((c.selling * pct) / 100);
                            commitLineDiscount(it.id, amt);
                          }}
                          title="Chiết khấu phần trăm (%) cho dòng này — trừ TRƯỚC VAT"
                        />
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
                  <td>{discountT > 0 ? `−${vnd(discountT)}` : "—"}</td>
                  <td>{vnd(grandT)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Điều khoản & hiệu lực */}
          <div className="card">
            <div className="bg-card-head"><div className="title"><FileText size={15} /> Điều khoản &amp; hiệu lực</div></div>
            <div className="field-row">
              <span className="field-lbl">Điều khoản báo giá</span>
              <textarea
                className="field-in"
                rows={6}
                value={termsText}
                disabled={!editable}
                onChange={(e) => setTermsText(e.target.value)}
                placeholder="Mỗi dòng là một điều khoản — bản in tự đánh số 1, 2, 3…"
              />
              <span style={{ color: "var(--ash)", fontSize: "12px", marginTop: "4px" }}>
                Mỗi dòng = 1 điều khoản. Bản in tự đánh số theo thứ tự dòng.
              </span>
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
                <Eye size={14} /> Phiên bản này {STATUS_LABEL_SHORT[d.status] ?? "đã khóa"} — khóa chỉnh sửa. Bấm "Tạo phiên bản mới" để sửa.
              </div>
            )}
            <div style={{ marginTop: "14px", display: "flex", gap: "8px" }}>
              {editable && <Button variant="secondary" disabled={busy} onClick={saveTerms}><Save size={15} /> Lưu nháp</Button>}
              {canRequote && viewingLatest && d.allowed_transitions.includes("change_order") && (
                <Button variant="primary" disabled={busy} onClick={openRequote} title="Giữ bản hiện tại + tạo phiên bản mới (bắt buộc ghi chú)"><GitBranch size={15} /> Tạo phiên bản mới</Button>
              )}
            </div>
          </div>

          {/* Theo dõi gửi khách (follow-up) */}
          {d.status === "sent" && (
            <div className="card">
              <div className="bg-card-head">
                <div className="title"><Link2 size={15} /> Theo dõi gửi khách</div>
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
                  <Button variant="secondary" onClick={recordContact}><Phone size={15} /> Ghi nhận đã liên hệ</Button>
                </div>
              )}
            </div>
          )}
          {d.status === "rejected" && d.cancel_reason && (
            <div className="card">
              <div className="bg-card-head"><div className="title"><Ban size={15} /> Lý do từ chối</div></div>
              <div className="stage-note warn">{d.cancel_reason}</div>
            </div>
          )}

          {/* Lịch sử phiên bản */}
          <div className="card">
            <div className="bg-card-head">
              <div className="title"><Clock size={15} /> Lịch sử phiên bản</div>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setCompareOn((v) => !v)}><ArrowLeftRight size={14} /> So sánh</button>
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
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
                      {d.exception_decision === "rejected" ? <><X size={13} /> Từ chối</> : <><Check size={13} /> Duyệt</>}
                    </span>{" "}bởi{" "}
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
              <div><span className="row-key">Giá bán (chưa VAT)</span><span className="row-val">{numf(netT + discountT)}₫</span></div>
              {discountT > 0 && (
                <div><span className="row-key">Chiết khấu</span><span className="row-val" style={{ color: "var(--amber)" }}>−{numf(discountT)}₫</span></div>
              )}
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
            <div className="bg-card-head"><div className="title"><User size={15} /> Khách hàng</div></div>
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
                <b>{[d.contact_name_snapshot, d.contact_phone_snapshot].filter(Boolean).join(" · ") || "—"}</b>
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
                    {d.phieu_tinh_gia_ma ?? `#${d.phieu_tinh_gia_id}`} <ExternalLink size={13} />
                  </button>
                ) : (
                  <b>{ptgRefs.length ? ptgRefs.join(", ") : "—"}</b>
                )}
              </div>
            </div>
          </div>

          {/* Hoạt động — nhật ký tương tác THẬT: ai làm gì · khi nào (mọi vai trò đụng cùng phiếu) */}
          <div className="card">
            <div className="bg-card-head"><div className="title"><Zap size={15} /> Hoạt động</div><span className="sub">{acts.length} sự kiện</span></div>
            <div className="act-timeline">
              {acts.length === 0 ? (
                <div className="discuss-empty">Chưa có hoạt động.</div>
              ) : acts.map((a, i) => {
                const m = ACT_META[a.action] ?? [Zap, "ash", a.action];
                const ActIcon = m[0];
                return (
                  <div className="act-item" key={i}>
                    <span className={`a-dot ${m[1]}`}><ActIcon size={14} /></span>
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
              <button type="button" className="bg__close" onClick={() => setRequoteOpen(false)} aria-label="Đóng"><X size={18} /></button>
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
                <Button variant="primary" disabled={busy || !requoteNote.trim()} onClick={doRequote}><GitBranch size={15} /> Tạo phiên bản</Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showPrint && <QuotationPrintModal d={d} canDownload={canExport} onClose={() => setShowPrint(false)} />}
    </main>
  );
}

// ---- Bản in báo giá (một ngôn ngữ — tiếng Việt) ----------------------------
function QuotationPrintModal({
  d,
  canDownload,
  onClose,
}: {
  d: QuotationDetail;
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

  // Điều khoản in ra phiếu: mỗi dòng của terms_text = 1 mục (bản in tự đánh số). Bỏ trống → mặc định.
  const termLines = (d.terms_text || DEFAULT_TERMS)
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  return (
    <div className="bg__overlay" onClick={onClose}>
      <div className="card bg__dialog" style={{ maxWidth: "900px", padding: 0 }} onClick={(e) => e.stopPropagation()}>
        <div className="bg__dialog-head">
          <h2>Xem trước báo giá in</h2>
          <button type="button" className="bg__close" onClick={onClose} aria-label="Đóng"><X size={18} /></button>
        </div>
        <div className="qpdf">
          {/* HEADER: logo hộp | tiêu đề giữa | số & ngày phải */}
          <header className="q-mh">
            <div className="q-logo"><img src={svnLogoUrl} alt="Sao Việt Nhật" /></div>
            <div className="q-th">
              <h1>BẢNG BÁO GIÁ</h1>
              <div className="q-cty">{SVN_COMPANY.name}</div>
            </div>
            <div className="q-meta-r">
              <div>Số báo giá: <b>{qno}</b></div>
              <div>Ngày: <b>{qdate}</b></div>
            </div>
          </header>

          {/* DẢI THÔNG TIN: khách hàng (trái) + bên bán (phải) */}
          <div className="q-info">
            <div className="q-info-grid">
              <div className="q-info-col">
                <div><span className="q-lbl">Kính gửi:</span> <b>{d.customer?.name ?? "—"}</b></div>
                <div><span className="q-lbl">MST:</span> {d.customer?.tax_code ?? "—"}</div>
              </div>
              <div className="q-info-col">
                <div><span className="q-lbl">Hiệu lực đến:</span> {d.valid_until ?? "Đến khi có thông báo mới"}</div>
              </div>
            </div>
          </div>

          <div className="q-intro">Cảm ơn Quý khách đã quan tâm sản phẩm của {SVN_COMPANY.name}. Chúng tôi xin gửi bảng báo giá chi tiết như sau:</div>

          {/* CHI TIẾT: header xám, viền mảnh, cột tiền căn phải + tfoot Cộng/VAT */}
          <div className="q-sec">Chi tiết báo giá</div>
          <table className="q-tbl">
            <colgroup>
              <col style={{ width: "5%" }} /><col style={{ width: "12%" }} /><col style={{ width: "26%" }} />
              <col style={{ width: "15%" }} /><col style={{ width: "6%" }} /><col style={{ width: "9%" }} />
              <col style={{ width: "13%" }} /><col style={{ width: "14%" }} />
            </colgroup>
            <thead>
              <tr>
                <th>STT</th>
                <th>Mã hàng</th>
                <th>Mô tả sản phẩm</th>
                <th>Kích thước</th>
                <th>ĐVT</th>
                <th>Số lượng</th>
                <th>Đơn giá<span className="q-sub">chưa VAT</span></th>
                <th>Thành tiền<span className="q-sub">chưa VAT</span></th>
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
                <td className="q-sub-lbl" colSpan={7}>Cộng tiền hàng (chưa VAT)</td>
                <td className="r">{money(netSubtotal)}</td>
              </tr>
              <tr>
                <td className="q-sub-lbl" colSpan={7}>Thuế GTGT {vatPct}%</td>
                <td className="r">{money(vatAmount)}</td>
              </tr>
            </tfoot>
          </table>

          {/* PANEL TỔNG THANH TOÁN (đóng khung, nhãn trái + số lớn phải) */}
          <div className="q-grand">
            <div>
              <div className="q-gt">Tổng thanh toán <span className="q-gt-sub">đã gồm VAT</span></div>
              <div className="q-gs">Tiền hàng {money(netSubtotal)}đ + Thuế GTGT {money(vatAmount)}đ</div>
            </div>
            <div className="q-ga">{money(grand)}<span className="q-u">đ</span></div>
          </div>

          {/* ĐIỀU KHOẢN — bám dữ liệu thật (terms_text), tự đánh số theo dòng */}
          <div className="q-sec">Điều khoản</div>
          <ol className="q-notes">
            {termLines.map((t, i) => <li key={i}>{t}</li>)}
          </ol>

          {/* CHỮ KÝ 2 cột */}
          <div className="q-signs">
            <div>
              <div className="q-role">Khách hàng xác nhận</div>
              <div className="q-hint">(Ký, ghi rõ họ tên)</div>
              <div className="q-sp" />
            </div>
            <div>
              <div className="q-role">Đại diện bên bán</div>
              <div className="q-hint">(Ký, ghi rõ họ tên)</div>
              <div className="q-sp" />
            </div>
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
