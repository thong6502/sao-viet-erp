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
import { gopTheoNhom, nhomLechSoLuong } from "../utils/gop-nhom";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { StatusTabs } from "../components/StatusTabs";
import svnLogoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import {
  Activity,
  AlertCircle,
  ArrowLeftRight,
  ArrowRight,
  ArrowUpFromLine,
  Ban,
  Building2,
  Calendar,
  Check,
  ChevronLeft,
  CornerDownLeft,
  DollarSign,
  FileText,
  GitBranch,
  History,
  Lock,
  Pencil,
  Plus,
  Printer,
  Save,
  Search,
  Send,
  ShieldCheck,
  Table,
  TriangleAlert,
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
      <main className="rdx-quote">
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
    <main className="rdx-quote">
      <div className="q-pagehead">
        <div>
          <p className="q-eyebrow"><span className="sq" />Kinh doanh · Chứng từ khách hàng</p>
          <h1>Báo giá thương mại</h1>
          <p className="sub">Giá bán gửi khách — dựng từ phiếu tính giá, cộng markup từng dòng.</p>
        </div>
        {/* BG-3/4: báo giá LUÔN khởi từ 1 Phiếu tính giá (1 PTG → 1 BG). Bỏ modal đa-pick cũ — nút
            này điều hướng sang màn Phiếu tính giá, ở đó bấm "Báo giá →" để tạo/mở báo giá. */}
        <Button variant="accent" onClick={() => navigate?.("tinh-gia")}>
          <Plus size={15} /> Báo giá mới
        </Button>
      </div>

      <form className="q-toolbar" onSubmit={onSearch} role="search">
        <div className="q-search">
          <Search size={15} />
          <input
            placeholder="Tìm mã báo giá, khách hàng…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Tìm báo giá"
          />
        </div>
        <Button type="submit" variant="ghost">
          Tìm
        </Button>
      </form>

      {/* Tab trạng thái đếm số — "Cần xử lý" = nháp + đã gửi chờ khách */}
      <div style={{ marginBottom: 14 }}>
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

      <div className="q-card">
        <table>
          <thead>
            <tr>
              <th>
                <SortBtn label="Mã báo giá" col="code" sort={sort} onSort={setSort} />
              </th>
              <th>Khách hàng</th>
              <th>Sản phẩm · nguồn PTG</th>
              <th className="num">
                <SortBtn label="Giá bán · VAT" col="total" sort={sort} onSort={setSort} />
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
                <td colSpan={6} className="tl-empty" role="status">
                  Đang tải danh sách báo giá…
                </td>
              </tr>
            ) : listError ? (
              <tr>
                <td colSpan={6}>
                  <div className="banner banner--error" role="alert" style={{ margin: 14 }}>
                    <span>{listError}</span>
                    <button type="button" className="btn btn--ghost" onClick={() => load()}>
                      Thử lại
                    </button>
                  </div>
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="tl-empty">
                  Chưa có báo giá thương mại nào được tạo.
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
                  <tr key={r.id} className="click" onClick={() => openDetail(r)}>
                    <td>
                      <span className="code">
                        {r.code}
                        <span className="v">v{r.version}</span>
                        {(r.version_count ?? 1) > 1 && (
                          <span className="vc">{r.version_count} phiên bản</span>
                        )}
                      </span>
                    </td>
                    <td>
                      {r.customer_name ?? (
                        <span className="muted">
                          {r.customer_id != null ? `KH #${r.customer_id}` : "Chưa chọn khách"}
                        </span>
                      )}
                    </td>
                    <td>
                      <div className="prod">
                        <span className="nm">{r.product_summary ?? "—"}</span>
                        {r.estimate_refs && r.estimate_refs.length > 0 && (
                          <span className="ptg">
                            <CornerDownLeft size={12} /> {r.estimate_refs.join(", ")}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="num">
                      {r.total != null ? (
                        <span className="rust-num">{fmtVnd(r.total)}</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                      {r.margin_percent != null && (
                        <span className="vc">biên {Math.round(r.margin_percent)}%</span>
                      )}
                    </td>
                    <td>
                      <StatusPill status={r.status} statuses={statuses} />
                      {sentDays !== null && sentDays >= 0 && (
                        <span
                          className="vc"
                          style={sentDays >= 7 ? { color: "var(--rust-deep)", fontWeight: 600 } : undefined}
                        >
                          Đã gửi {sentDays} ngày{sentDays >= 7 ? " · cần follow-up" : ""}
                        </span>
                      )}
                    </td>
                    <td>
                      <div className="prod">
                        <span className="nm" style={{ fontWeight: 500, whiteSpace: "nowrap" }}>
                          {fmtDate(r.updated_at ?? null)}
                        </span>
                        {r.salesperson_name && <span className="spec">{r.salesperson_name}</span>}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {!loading && !listError && rows.length > 0 && (
        <div className="foot">
          <span>
            Tìm thấy {total} phiếu báo giá · Trang {page}/{totalPages}
          </span>
          <div className="foot-btns">
            <Button
              variant="ghost"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ‹ Trước
            </Button>
            <Button
              variant="ghost"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Sau ›
            </Button>
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

// Thang badge trạng thái — CHỈ 3 màu chính (kem/mực/cam) + đỏ mờ signal cho Từ chối/Huỷ.
// Cùng 1 kiểu pill + chấm; khác nhau ở nền/chữ theo mức tiến triển của phiếu.
function statusBadgeVariant(status: string): string {
  if (status === "accepted") return "solid"; // Khách chốt — cam đặc, chữ trắng
  if (status === "converted_to_order") return "dark"; // Đã lên đơn — nền đen chữ kem
  if (status === "sent") return "soft"; // Đã gửi khách — cam nhạt
  if (status === "approved") return "pending"; // Đã duyệt · chờ gửi — xám + chấm cam
  if (status === "pending_approval") return "pending"; // Chờ duyệt — xám + chấm cam
  if (status === "rejected" || status === "expired" || status === "cancelled") return "signal";
  return "neutral"; // Nháp — xám
}
function StatusPill({ status, statuses }: { status: string; statuses: EnumOption[] }) {
  return (
    <span className={`badge ${statusBadgeVariant(status)}`}>
      <span className="d" />
      {labelOf(statuses, status)}
    </span>
  );
}

// --- Detail 2-cột in-page (port "ý hệt" prototype inan5 02-bao-gia.html) ------------------------------------------------

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

/** Node bảng báo giá: 1 nhóm gộp (in ra khách 1 dòng) hoặc 1 dòng lẻ. */
type NodeBaoGia =
  | { kind: "don"; key: string; it: QuoteItemDetail }
  | { kind: "nhom"; key: string; ten: string; members: QuoteItemDetail[] };

/** Gom dòng cùng nhãn `nhom`, giữ vị trí dòng ĐẦU của mỗi nhóm. Không nhãn = đứng riêng. */
function gomDongTheoNhom(items: QuoteItemDetail[]): NodeBaoGia[] {
  const out: NodeBaoGia[] = [];
  const viTri = new Map<string, number>();
  for (const it of items) {
    const nh = (it.nhom ?? "").trim();
    if (!nh) {
      out.push({ kind: "don", key: `d${it.id}`, it });
      continue;
    }
    const k = nh.toLowerCase();
    const at = viTri.get(k);
    if (at === undefined) {
      viTri.set(k, out.length);
      out.push({ kind: "nhom", key: k, ten: nh, members: [it] });
    } else {
      (out[at] as { members: QuoteItemDetail[] }).members.push(it);
    }
  }
  return out;
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
  // Diễn giải quy cách đang sửa: id dòng đang mở ô + nội dung gõ dở (lưu khi rời ô).
  const [dgOpen, setDgOpen] = useState<number | null>(null);
  const [dgDraft, setDgDraft] = useState<string>("");
  // P3: danh sách khách để CHỌN/ĐỔI khách ngay ở detail (khi còn nháp) — auto-fill lại liên hệ + ĐC giao.
  const [customers, setCustomers] = useState<{ id: number; name: string; code: string }[]>([]);

  const [compareOn, setCompareOn] = useState(false);
  const [showPrint, setShowPrint] = useState(false);

  // Điều khoản chỉnh tại chỗ (nháp) — 1 khối text, mỗi dòng = 1 điều khoản.
  const [termsText, setTermsText] = useState(DEFAULT_TERMS);
  const [validity, setValidity] = useState<number>(30);
  const [validUntilEdit, setValidUntilEdit] = useState<string>("");   // ngày hết hạn (editable)
  const [verNote, setVerNote] = useState("");
  // Ghi chú nội bộ (per-quote, không in cho khách) — sửa được khi NHÁP, lưu cùng điều khoản.
  const [internalNoteEdit, setInternalNoteEdit] = useState<string>("");

  // Feed Hoạt động — nhật ký tương tác THẬT (ai làm gì) đọc từ backend.
  const [acts, setActs] = useState<QuotationActivity[]>([]);
  // Tạo phiên bản mới: BẮT BUỘC ghi chú → modal nhập lý do trước khi tạo.
  const [requoteOpen, setRequoteOpen] = useState(false);
  const [requoteNote, setRequoteNote] = useState("");
  // Khách chốt MỘT PHẦN: picker chọn dòng khách ưng trước khi ghi "Khách chốt". Mặc định tick hết
  // (case phổ biến = ưng cả) → 1 lần bấm là xong; bỏ tick dòng khách không lấy.
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [acceptPicks, setAcceptPicks] = useState<Record<number, boolean>>({});

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
        setInternalNoteEdit(det.internal_note ?? "");
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
      <main className="rdx-quote bgv">
        <div className="panel" role="status" style={{ padding: "40px", textAlign: "center", color: "var(--ash)" }}>
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

  // Tên tóm tắt: dòng đầu thuộc nhóm thì lấy TÊN NHÓM (khách mua "quyển sách", không mua "ruột").
  const productSummary = d.items[0]?.nhom?.trim() || d.items[0]?.product_name || "—";
  const ptgRefs = Array.from(new Set(d.items.map((it) => it.estimate_number).filter(Boolean)));

  // ---- Persist margin/VAT --------------------------------------------------
  // Patch theo dòng: bỏ trống field nào thì GIỮ giá trị hiện tại của dòng đó (dùng ?? để 0 vẫn áp).
  // Header lấy từ edit-state (không clobber ghi chú/điều khoản đang sửa chưa lưu).
  async function persistItems(
    items: { id: number; margin_percent?: number; vat_percent?: number; discount_amount?: number; rounding?: string; note?: string | null; dien_giai?: string | null }[],
  ) {
    if (!token || !d) return;
    setBusy(true);
    setErr(null);
    try {
      await api.quotations.update(token, d.id, {
        customer_id: d.customer_id,
        valid_until: validUntilEdit || null,
        terms_text: termsText,
        internal_note: internalNoteEdit,
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
            // Payload dump đủ field ở BE → phải echo giá trị cũ, không gửi = XOÁ diễn giải.
            dien_giai: patch?.dien_giai !== undefined ? patch.dien_giai : it.dien_giai,
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
  /** Lưu diễn giải quy cách của 1 dòng (rời ô mới lưu). Không đổi thì bỏ qua — khỏi ghi nhật ký thừa. */
  function commitDienGiai(itemId: number) {
    setDgOpen(null);
    if (!editable || !d) return;
    const cur = d.items.find((it) => it.id === itemId)?.dien_giai ?? "";
    const next = dgDraft.trim();
    if (next === cur.trim()) return;
    persistItems([{ id: itemId, dien_giai: next || null }]);
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
        internal_note: internalNoteEdit,
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
        internal_note: internalNoteEdit,
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

  // Khách chốt: mở picker chọn dòng khách ưng (mặc định tick hết). 1 dòng thì khỏi hỏi — chốt luôn.
  function openAcceptPicker() {
    if (!d) return;
    if (d.items.length <= 1) { void doAccept(d.items.map((it) => it.id)); return; }
    setAcceptPicks(Object.fromEntries(d.items.map((it) => [it.id, true])));
    setErr(null);
    setAcceptOpen(true);
  }

  // Ghi "Khách chốt" kèm danh sách dòng khách ƯNG (khách chốt một phần). Đơn hàng sau chỉ kéo dòng này.
  async function doAccept(ids: number[]) {
    if (!token || !d) return;
    if (ids.length === 0) { setErr("Chọn ít nhất 1 sản phẩm khách chốt."); return; }
    setBusy(true);
    setErr(null);
    try {
      await api.quotations.transition(token, d.id, { to_status: "accepted", accepted_item_ids: ids });
      setAcceptOpen(false);
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



  const marginPctDisp = multi ? aggMarginPct : Math.round(singleMargin);
  const meterW = Math.max(0, Math.min(100, marginPctDisp));

  // Khách chốt một phần: chỉ đánh dấu "khách không lấy" khi báo giá ĐÃ chốt VÀ có ít nhất 1 dòng được
  // ưng (phân biệt với báo giá cũ chốt-toàn-phần: accepted toàn false → coi như lấy hết, không gạch).
  const quoteClosed = d.status === "accepted" || d.status === "converted_to_order";
  const acceptedDecided = d.items.some((it) => it.accepted);
  const declinedCount = quoteClosed && acceptedDecided ? d.items.filter((it) => !it.accepted).length : 0;
  // Cây hiển thị của bảng: dòng cùng nhãn `nhom` kéo về cạnh nhau dưới 1 dải, tại vị trí dòng đầu.
  // KHÔNG bọc useMemo: chỗ này nằm sau một `return` sớm của component → thêm hook ở đây là đổi
  // thứ tự hook giữa các lần render (React văng). Danh sách vài dòng, tính thẳng rẻ hơn nhiều.
  const nhomTrongBaoGia = gomDongTheoNhom(d.items);
  // Nhóm gộp có các dòng lệch SL → bản in lấy SL dòng đầu, phải nhắc người soạn.
  const nhomLech = nhomLechSoLuong(d.items, (it) => ({
    nhom: it.nhom, ten: it.product_name, soLuong: it.quantity, donViTinh: it.unit,
    thanhTien: 0, tienVat: 0, vatPct: it.vat_percent,
  }));

  return (
    <main className="rdx-quote bgv">
      {/* ---------- Header ---------- */}
      <div className="dhead">
        <div>
          <button type="button" className="back" onClick={onClose}><ChevronLeft size={15} /> Danh sách</button>
          <div className="titleline">
            <h1>{d.code}</h1>
            <span className="ver">v{d.version}</span>
            <StatusPill status={d.status} statuses={statuses} />
          </div>
          {/* Bỏ dấu "—" thừa khi chưa chọn khách: chỉ nối phần có giá trị. */}
          <div className="subline">{[d.customer?.name, productSummary].filter(Boolean).join(" · ") || "—"}</div>
        </div>
        <div className="acts">
          <Button variant="secondary" onClick={() => setShowPrint(true)}><Printer size={15} /> Xem bản in</Button>
          {/* Gating quyền chi tiết: từ chối/gửi cần `manage_status`, chốt cần `approve`
              (server tính d.can_approve), tạo bản mới cần `requote` — thiếu quyền thì ẨN nút. */}
          {viewingLatest && d.status === "sent" && (
            <>
              {canManageStatus && (
                <Button variant="secondary" disabled={busy} onClick={() => doTransition("rejected")}><X size={15} /> Khách từ chối</Button>
              )}
              {d.can_approve && (
                <Button variant="primary" disabled={busy || !d.allowed_transitions.includes("accepted")} onClick={openAcceptPicker}><Check size={15} /> Khách chốt</Button>
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

      <div className="g2">
        {/* ================= LEFT: bảng + điều khoản ================= */}
        <div className="stack">
          {/* Báo giá nhiều dòng — giá vốn khóa, markup + chiết khấu chỉnh tại chỗ */}
          <div className="panel">
            <div className="panel__hd">
              <h3><Table size={16} /> {multi ? "Báo giá nhiều dòng" : "Giá vốn"}</h3>
              {/* Đếm DÒNG, không phải phiếu — 1 phiếu tính giá đẻ nhiều dòng là chuyện thường. */}
              <span className="tag">{multi ? `${d.items.length} dòng` : "Khóa từ PTG"}</span>
            </div>
            <div className="hint">
              <ShieldCheck size={15} />
              <span>
                {declinedCount > 0
                  ? `Khách chốt ${d.items.length - declinedCount}/${d.items.length} sản phẩm · ${declinedCount} dòng khách không lấy (đã gạch) không lên đơn.`
                  : "Markup riêng từng dòng · giá đã gồm VAT."}
              </span>
            </div>
            {/* Bản in lấy SL của DÒNG ĐẦU nhóm. SL trong nhóm lệch nhau là dấu hiệu khai nhầm
                (bìa 1.250 / ruột 1.200) → nhắc ngay, không âm thầm in ra số sai. */}
            {nhomLech.length > 0 && (
              <div className="hint hint--warn" role="status">
                <TriangleAlert size={15} />
                <span>
                  Nhóm {nhomLech.map((n) => `"${n}"`).join(", ")} có các dòng lệch số lượng — bản
                  in gửi khách lấy SL của dòng đầu nhóm. Kiểm lại trước khi gửi.
                </span>
              </div>
            )}
            <table>
              <thead>
                <tr>
                  <th>Sản phẩm</th><th className="num">SL</th><th className="num">Giá vốn</th><th className="num">Markup</th><th className="num">Chiết khấu</th><th className="num">Thành tiền · VAT</th>
                </tr>
              </thead>
              <tbody>
                {/* Dải NHÓM: các dòng cùng nhãn in ra khách thành 1 dòng, nên bày chúng dưới một
                    dải mang đúng con số khách thấy. Markup/chiết khấu vẫn nằm ở TỪNG dòng con. */}
                {nhomTrongBaoGia.flatMap((node) => {
                  const dongIt = (it: QuoteItemDetail, con: boolean, cuoi = false) => {
                  const c = calcItem(it);
                  const markupVal = multi ? (lineDraft[it.id] ?? it.margin_percent) : (draftMargin ?? it.margin_percent);
                  const discPct = c.selling > 0 ? Math.round(((discDraft[it.id] ?? it.discount_amount) / c.selling) * 100) : 0;
                  const declined = quoteClosed && acceptedDecided && !it.accepted;
                  return (
                    <tr
                      key={it.id}
                      className={
                        `${declined ? "declined" : ""}${con ? " qrow--con" : ""}${cuoi ? " qrow--conCuoi" : ""}`
                          .trim() || undefined
                      }
                    >
                      <td>
                        <span className="pname">{it.product_name}</span>
                        {declined && <span className="declined-badge">Khách không lấy</span>}
                        {/* Diễn giải quy cách IN cho khách — máy bung từ bài tính giá, sửa tại chỗ. */}
                        {dgOpen === it.id ? (
                          <textarea
                            className="dg-ta"
                            autoFocus
                            rows={4}
                            value={dgDraft}
                            placeholder={"Mỗi dòng 1 ý, ví dụ:\nKT: 350×215mm\nGiấy kraft 200g\nIn 1 màu"}
                            onChange={(e) => setDgDraft(e.target.value)}
                            onBlur={() => commitDienGiai(it.id)}
                            onKeyDown={(e) => { if (e.key === "Escape") setDgOpen(null); }}
                          />
                        ) : it.dien_giai ? (
                          <ul className="dg-list">
                            {it.dien_giai.split("\n").filter(Boolean).map((ln, k) => <li key={k}>{ln}</li>)}
                            {editable && (
                              <li className="dg-edit">
                                <button type="button" onClick={() => { setDgDraft(it.dien_giai ?? ""); setDgOpen(it.id); }}>
                                  Sửa diễn giải
                                </button>
                              </li>
                            )}
                          </ul>
                        ) : editable ? (
                          <button
                            type="button"
                            className="dg-add"
                            onClick={() => { setDgDraft(""); setDgOpen(it.id); }}
                          >
                            + Thêm diễn giải
                          </button>
                        ) : null}
                      </td>
                      <td className="num">{it.quantity.toLocaleString("vi-VN")}</td>
                      <td className="num muted">{numf(c.cost)}</td>
                      <td className="num">
                        <div className="pctcell">
                          <input
                            className="inp"
                            type="number" min={0} max={100} step={0.5}
                            value={markupVal}
                            disabled={!editable}
                            onChange={(e) => multi
                              ? setLineDraft((p) => ({ ...p, [it.id]: Number(e.target.value) }))
                              : setDraftMargin(Number(e.target.value))}
                            onBlur={(e) => multi
                              ? commitLineMargin(it.id, Number(e.target.value))
                              : commitSingleMargin(Number(e.target.value))}
                            title="Markup (%) cho dòng này"
                          />%
                        </div>
                      </td>
                      <td className="num">
                        <div className="pctcell">
                          <input
                            className="inp"
                            type="number" min={0} max={100} step={0.5}
                            value={discPct}
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
                          />%
                        </div>
                      </td>
                      <td className="num strong">{vnd(c.final)}</td>
                    </tr>
                  );
                  };

                  if (node.kind === "don") return [dongIt(node.it, false)];
                  const tongVon = node.members.reduce((s, m) => s + calcItem(m).cost, 0);
                  const tongTien = node.members.reduce((s, m) => s + calcItem(m).final, 0);
                  return [
                    <tr key={`nh-${node.key}`} className="qgrouphd">
                      <td>
                        <span className="qgrouphd__ten">{node.ten}</span>
                        <span className="qgrouphd__sub">
                          {node.members.length} phần · in ra khách 1 dòng
                        </span>
                      </td>
                      <td className="num">{node.members[0].quantity.toLocaleString("vi-VN")}</td>
                      <td className="num muted">{numf(tongVon)}</td>
                      <td className="num muted">—</td>
                      <td className="num muted">—</td>
                      <td className="num strong">{vnd(tongTien)}</td>
                    </tr>,
                    ...node.members.map((m, k) => dongIt(m, true, k === node.members.length - 1)),
                  ];
                })}
                {/* Hàng tổng chỉ có nghĩa khi ≥2 dòng; 1 dòng thì lặp lại chính dòng đó. */}
                {d.items.length > 1 && (
                  <tr className="tot">
                    <td className="lbl">Tổng {d.items.length} dòng</td>
                    <td></td>
                    <td className="num muted">{numf(costT)}</td>
                    <td></td>
                    <td className="num">{discountT > 0 ? `−${numf(discountT)}` : "—"}</td>
                    <td className="num rust-num">{vnd(grandT)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Điều khoản & hiệu lực (Redesigned Modern WOW UI) */}
          <div className="panel terms-redesign-panel">
            <div className="panel__hd">
              <div className="terms-hd-title">
                <h3><FileText size={18} className="terms-hd-icon" /> Điều khoản &amp; Hiệu lực báo giá</h3>
                <span className="terms-badge-pill">
                  {editable ? "Đang mở chỉnh sửa" : "Bản đã khóa"}
                </span>
              </div>
            </div>

            <div className="terms">
              {/* Section 1: Điều khoản in cho khách */}
              <div className="terms-section">
                <div className="terms-section__title">
                  <span className="terms-section__lbl">Điều khoản áp dụng (Gửi khách hàng)</span>
                  <span className="terms-section__hint">Hiển thị trên bản in báo giá PDF</span>
                </div>

                {editable ? (
                  <textarea
                    className="terms-textarea"
                    rows={6}
                    value={termsText}
                    onChange={(e) => setTermsText(e.target.value)}
                    placeholder="Mỗi dòng là một điều khoản — bản in tự đánh số 1, 2, 3…"
                  />
                ) : (
                  <div className="terms-read-list">
                    {termsText
                      .split("\n")
                      .filter((line) => line.trim().length > 0)
                      .map((line, idx) => (
                        <div key={idx} className="terms-read-item">
                          <span className="terms-item-num">{idx + 1}</span>
                          <span className="terms-item-text">{line}</span>
                        </div>
                      ))}
                  </div>
                )}
              </div>

              {/* Section 2: Hạn hiệu lực & Thời gian */}
              <div className="terms-validity-bar">
                <div className="validity-pill-box">
                  <div className="validity-icon"><Calendar size={15} /></div>
                  <div className="validity-info">
                    <span className="validity-lbl">Hạn hiệu lực báo giá</span>
                    <div className="validity-val-row">
                      {editable ? (
                        <input
                          className="datepill-edit"
                          type="date"
                          value={validUntilEdit}
                          onChange={(e) => setValidUntilEdit(e.target.value)}
                        />
                      ) : (
                        <span className="validity-date-str">
                          {validUntilEdit ? fmtDate(validUntilEdit) : "Cho đến khi có thông báo mới"}
                        </span>
                      )}
                      {validUntilEdit && (
                        <span className="validity-tag">
                          {validity > 0 ? `Còn ${validity} ngày` : "Đã hết hạn"}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Section 3: Ghi chú nội bộ (Confidential box) */}
              <div className="internal-note-box">
                <div className="internal-note-hd">
                  <Lock size={14} className="internal-note-icon" />
                  <span>Ghi chú nội bộ (Bảo mật - Chỉ hiển thị cho SX &amp; Kế toán)</span>
                </div>
                {editable ? (
                  <textarea
                    className="internal-note-textarea"
                    rows={3}
                    value={internalNoteEdit}
                    onChange={(e) => setInternalNoteEdit(e.target.value)}
                    placeholder="Lưu ý nội bộ cho SX/kế toán — KHÔNG in cho khách."
                  />
                ) : (
                  <p className="internal-note-text">
                    {internalNoteEdit || "Không có ghi chú nội bộ cho phiên bản này."}
                  </p>
                )}
              </div>

              {verNote && (
                <div className="verline-box">
                  <span className="verline-lbl">Lý do điều chỉnh phiên bản này:</span>
                  <span className="verline-val">{verNote}</span>
                </div>
              )}

              {!editable && (
                <div className="ro-lock-banner">
                  <Lock size={16} className="ro-lock-icon" />
                  <div className="ro-lock-desc">
                    <strong>Phiên bản {STATUS_LABEL_SHORT[d.status] ?? "đã khóa"}</strong> — Đã khóa chỉnh sửa để bảo đảm tính toàn vẹn dữ liệu. Bấm "Tạo phiên bản mới" nếu cần thay đổi giá hoặc điều khoản.
                  </div>
                </div>
              )}

              <div className="tactions-redesign">
                {editable && (
                  <Button variant="secondary" disabled={busy} onClick={saveTerms}>
                    <Save size={15} /> Lưu nháp điều khoản
                  </Button>
                )}
                {canRequote && viewingLatest && d.allowed_transitions.includes("change_order") && (
                  <Button
                    variant="primary"
                    disabled={busy}
                    onClick={openRequote}
                    title="Giữ bản hiện tại + tạo phiên bản mới (bắt buộc ghi chú)"
                  >
                    <GitBranch size={15} /> Tạo phiên bản mới (v{d.version + 1})
                  </Button>
                )}
              </div>
            </div>
          </div>


          {d.status === "rejected" && d.cancel_reason && (
            <div className="panel">
              <div className="panel__hd"><h3><Ban size={16} /> Lý do từ chối</h3></div>
              <div className="hint" style={{ margin: "14px 16px", color: "var(--signal)" }}><span>{d.cancel_reason}</span></div>
            </div>
          )}
        </div>

        {/* ================= RIGHT: giá bán + khách hàng ================= */}
        <div className="stack">
          {/* Giá bán đề xuất (dark card) */}
          <div className="dk">
            <div className="dk__hd"><div className="dk__eyebrow"><DollarSign size={13} /> Giá bán đề xuất · v{d.version}</div></div>
            <div className="dk__big">{numf(grandT)}<span className="u">đ</span></div>
            <div className="dk__meta">≈ {numf(perUnit)} đ/{unitLabel} · đã gồm VAT</div>
            <div className="dk__meter">
              <div className="lbl"><span>Biên lợi nhuận</span><b>{marginPctDisp}%</b></div>
              <div className="mbar"><span className="p" style={{ width: `${meterW}%` }} /></div>
            </div>
            <div className="dk__rows">
              <div className="drow"><span className="k">Giá vốn (khóa)</span><span className="v">{numf(costT)} đ</span></div>
              <div className="drow profit"><span className="k">Lợi nhuận</span><span className="v">{profitT >= 0 ? "+" : ""}{numf(profitT)} đ</span></div>
              <div className="drow"><span className="k">Giá bán (chưa VAT)</span><span className="v">{numf(netT + discountT)} đ</span></div>
              {discountT > 0 && (
                <div className="drow"><span className="k">Chiết khấu</span><span className="v" style={{ color: "var(--rust)" }}>−{numf(discountT)} đ</span></div>
              )}
              <div className="drow">
                <span className="k">
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
                    ` ${multi ? "" : Math.round(singleVat) + "%"}`
                  )}
                </span>
                <span className="v">{numf(vatT)} đ</span>
              </div>
              {/* Bỏ "Tổng cộng" — trùng số lớn "Giá bán đề xuất" ở đầu card. */}
            </div>

            {/* Báo giá đặc thù (giá trị cao / lời mỏng / bán dưới vốn): Nháp → TRÌNH DUYỆT → Chờ duyệt →
                Giám đốc Kinh doanh duyệt (→ Đã duyệt/gửi) hoặc từ chối (→ về Nháp). Trạng thái bám máy
                trạng thái báo giá (d.status), KHÔNG bám riêng exception_status (redesign-bao-gia §3). */}
            {d.exception_required && (
              <div className="dk__extra">
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
              </div>
            )}
          </div>

          {/* Khách hàng (kèm link Phiếu tính giá) */}
          <div className="panel">
            <div className="panel__hd"><h3><Building2 size={16} /> Khách hàng</h3></div>
            <div className="info">
              <div className="irow">
                <span className="k">Công ty</span>
                {editable ? (
                  <span className="v">
                    <CustomerCombobox
                      customers={customers}
                      value={d.customer_id ?? null}
                      onChange={changeCustomer}
                      disabled={busy}
                      maxWidth={200}
                    />
                  </span>
                ) : (
                  <span className="v">{d.customer?.name ?? "—"}</span>
                )}
              </div>
              <div className="irow"><span className="k">Người liên hệ</span><span className="v mono">{[d.contact_name_snapshot, d.contact_phone_snapshot].filter(Boolean).join(" · ") || "—"}</span></div>
              {/* Người duyệt biết báo giá này của NV nào (P8b). */}
              <div className="irow"><span className="k">NV soạn</span><span className="v">{d.salesperson_name ?? "—"}</span></div>
              <div className="irow"><span className="k">MST</span><span className="v mono">{d.customer?.tax_code ?? "—"}</span></div>
              <div className="irow"><span className="k">Tín dụng</span><span className="v">{d.customer?.credit_status_display ?? "—"}</span></div>
              <div className="irow">
                {/* Hệ mới (PhieuTinhGia) → link mở được. Hệ cũ (Estimate, UI đã ngừng) → chỉ là
                    tham chiếu, KHÔNG mở được: đổi nhãn + làm mờ + bỏ vẻ-như-link để không hiểu nhầm. */}
                <span className="k">
                  {!d.phieu_tinh_gia_id && ptgRefs.length ? "Ước tính (hệ cũ)" : "Phiếu tính giá"}
                </span>
                <span className="v ptgs">
                  {d.phieu_tinh_gia_id ? (
                    <button
                      type="button" className="ptg"
                      onClick={() => navigate?.("tinh-gia", { focusPhieuId: d.phieu_tinh_gia_id ?? undefined })}
                      title="Mở phiếu tính giá nguồn"
                    >
                      <CornerDownLeft size={13} /> {d.phieu_tinh_gia_ma ?? `#${d.phieu_tinh_gia_id}`}
                    </button>
                  ) : ptgRefs.length ? (
                    ptgRefs.map((r, i) => (
                      <span key={i} className="ptg-legacy" title="Ước tính hệ cũ — không mở được">{r}</span>
                    ))
                  ) : (
                    "—"
                  )}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ===== Khu dưới: Lịch sử phiên bản | Hoạt động — mỗi khối cuộn trong khối (chống dài) ===== */}
      <div className="gg">
        {/* Lịch sử phiên bản */}
        <div className="panel">
          <div className="panel__hd">
            <h3><History size={16} /> Lịch sử phiên bản</h3>
            <button type="button" className="viewall" onClick={() => setCompareOn((v) => !v)}><ArrowLeftRight size={14} /> So sánh</button>
          </div>
          <div className="vh scrollbox">
            {d.versions.slice().sort((a, b) => b.version - a.version).map((v) => {
              const isCur = v.version === latestVer;
              const active = v.version === d.version;
              return (
                <div
                  key={v.id}
                  className={`vrow${active ? " cur" : ""}${!isCur ? " old" : ""}`}
                  onClick={() => v.id !== d.id && reload(v.id)}
                  title={active ? "Đang xem phiên bản này" : "Bấm để xem phiên bản này"}
                >
                  <span className="vtag">v{v.version}</span>
                  {active && <span className="vnow">Đang xem</span>}
                  <div className="vmid">
                    <div className="a">{v.change_reason || "—"}</div>
                    <div className="m">{fmtDate(v.created_at)}{isCur ? " · hiện tại" : ""}</div>
                  </div>
                  <div className="vright">
                    <div className="p rust-num">{vnd(v.total ?? 0)}</div>
                    <StatusPill status={v.status} statuses={statuses} />
                  </div>
                </div>
              );
            })}
          </div>
          {compareOn && (
            <div style={{ padding: "0 14px 14px" }}>
              <div style={{ borderTop: "1px solid var(--rule-soft)", paddingTop: "12px", overflowX: "auto" }}>
                <table className="cmp-tbl">
                  <thead>
                    <tr><th>Chỉ tiêu</th>{d.versions.slice().sort((a, b) => a.version - b.version).map((v) => <th key={v.id}>v{v.version}</th>)}</tr>
                  </thead>
                  <tbody>
                    <tr><td>Giá vốn (khóa)</td>{d.versions.slice().sort((a, b) => a.version - b.version).map((v) => <td key={v.id}>{v.total_cost != null ? vnd(v.total_cost) : "—"}</td>)}</tr>
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
                    <tr><td>Chiết khấu</td>{d.versions.slice().sort((a, b) => a.version - b.version).map((v) => <td key={v.id}>{v.discount ? vnd(v.discount) : "—"}</td>)}</tr>
                    <tr><td>Lý do</td>{d.versions.slice().sort((a, b) => a.version - b.version).map((v) => <td key={v.id} style={{ textAlign: "left", fontWeight: 400, whiteSpace: "normal" }}>{v.change_reason || "—"}</td>)}</tr>
                    <tr><td>Trạng thái</td>{d.versions.slice().sort((a, b) => a.version - b.version).map((v) => <td key={v.id}>{labelOf(statuses, v.status)}</td>)}</tr>
                    <tr><td>Ngày</td>{d.versions.slice().sort((a, b) => a.version - b.version).map((v) => <td key={v.id}>{fmtDate(v.created_at)}</td>)}</tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Hoạt động — nhật ký tương tác THẬT: ai làm gì · khi nào (mọi vai trò đụng cùng phiếu) */}
        <div className="panel">
          <div className="panel__hd"><h3><Activity size={16} /> Hoạt động</h3><span className="tag">{acts.length} sự kiện</span></div>
          <div className="tl scrollbox">
            {acts.length === 0 ? (
              <div className="tl-empty">Chưa có hoạt động.</div>
            ) : acts.map((a, i) => {
              const m = ACT_META[a.action] ?? [Zap, "ash", a.action];
              const ActIcon = m[0];
              const tone = a.action === "quote_exception_rejected" || a.action === "transition_rejected" || a.action === "transition_cancelled" || a.action === "transition_expired"
                ? "sig"
                : i > 0 ? "mut" : "";
              return (
                <div className={`tlrow ${tone}`} key={i}>
                  <span className="tlic"><ActIcon size={14} /></span>
                  <div className="tlb">
                    <div className="a">{m[2]}{a.actor_name && <> — <b>{a.actor_name}</b></>}</div>
                    <div className="m">{fmtDateTime(a.at)}</div>
                  </div>
                </div>
              );
            })}
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

      {acceptOpen && (() => {
        const picked = d.items.filter((it) => acceptPicks[it.id]);
        const pickedIds = picked.map((it) => it.id);
        const pickedTotal = picked.reduce((s, it) => s + calcItem(it).final, 0);
        // Đếm theo SẢN PHẨM THƯƠNG MẠI (nhóm = 1), không đếm dòng — khách mua 2 thứ chứ không
        // phải 3: quyển catalogue (ruột + bìa) và sản phẩm 3.
        const soNhomDaChon = nhomTrongBaoGia.filter((n) =>
          n.kind === "don" ? !!acceptPicks[n.it.id] : n.members.every((m) => acceptPicks[m.id]),
        ).length;
        return (
          <div className="bg__overlay" onClick={() => setAcceptOpen(false)}>
            <div className="card bg__dialog" style={{ maxWidth: "560px" }} onClick={(e) => e.stopPropagation()}>
              <div className="bg__dialog-head">
                <h2>Khách chốt — chọn sản phẩm</h2>
                <button type="button" className="bg__close" onClick={() => setAcceptOpen(false)} aria-label="Đóng"><X size={18} /></button>
              </div>
              <div style={{ padding: "16px" }}>
                <div className="accept-pick-head">
                  <label className="accept-pick-all">
                    <input
                      type="checkbox"
                      checked={pickedIds.length === d.items.length}
                      ref={(el) => { if (el) el.indeterminate = pickedIds.length > 0 && pickedIds.length < d.items.length; }}
                      onChange={(e) => setAcceptPicks(Object.fromEntries(d.items.map((it) => [it.id, e.target.checked])))}
                    />
                    <span>Chọn tất cả</span>
                  </label>
                  <span className="accept-pick-head-count">{soNhomDaChon}/{nhomTrongBaoGia.length} khách lấy</span>
                </div>
                {/* Khách chốt theo SẢN PHẨM THƯƠNG MẠI: 1 ô tick cho cả nhóm. Cho tick lẻ ruột
                    mà bỏ bìa là ra đơn không làm được cuốn sách — nên nhóm đi liền một khối. */}
                <div className="accept-pick-list">
                  {nhomTrongBaoGia.map((node) => {
                    if (node.kind === "don") {
                      const it = node.it;
                      const on = !!acceptPicks[it.id];
                      return (
                        <label key={it.id} className={`accept-pick-row${on ? "" : " off"}`}>
                          <input
                            type="checkbox"
                            checked={on}
                            onChange={(e) => setAcceptPicks((p) => ({ ...p, [it.id]: e.target.checked }))}
                          />
                          <span className="accept-pick-name">
                            {it.product_name}
                            <span className="accept-pick-qty">{it.quantity.toLocaleString("vi-VN")} {it.unit}</span>
                          </span>
                          <span className="accept-pick-amt">{vnd(calcItem(it).final)}</span>
                        </label>
                      );
                    }
                    const on = node.members.every((m) => acceptPicks[m.id]);
                    const dau = node.members[0];
                    const tien = node.members.reduce((s, m) => s + calcItem(m).final, 0);
                    return (
                      <label key={node.key} className={`accept-pick-row${on ? "" : " off"}`}>
                        <input
                          type="checkbox"
                          checked={on}
                          onChange={(e) =>
                            setAcceptPicks((p) => ({
                              ...p,
                              ...Object.fromEntries(node.members.map((m) => [m.id, e.target.checked])),
                            }))
                          }
                        />
                        <span className="accept-pick-name">
                          {node.ten}
                          <span className="accept-pick-qty">
                            {dau.quantity.toLocaleString("vi-VN")} {dau.unit} ·{" "}
                            {node.members.map((m) => m.product_name).join(" + ")}
                          </span>
                        </span>
                        <span className="accept-pick-amt">{vnd(tien)}</span>
                      </label>
                    );
                  })}
                </div>
                <div className="accept-pick-sum">
                  <span>Khách chốt <b>{soNhomDaChon}</b>/{nhomTrongBaoGia.length} sản phẩm</span>
                  <span className="accept-pick-sum-amt">{vnd(pickedTotal)}</span>
                </div>
                {err && <div className="ro-note" style={{ marginTop: "8px", color: "var(--signal)" }}>{err}</div>}
                <div style={{ marginTop: "14px", display: "flex", gap: "8px", justifyContent: "flex-end" }}>
                  <Button variant="ghost" disabled={busy} onClick={() => setAcceptOpen(false)}>Hủy</Button>
                  <Button variant="primary" disabled={busy || pickedIds.length === 0} onClick={() => doAccept(pickedIds)}><Check size={15} /> Xác nhận khách chốt</Button>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

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
  // GỘP NHÓM: ruột + bìa cùng nhãn `nhom` in ra 1 dòng "quyển sách" (khách mua 1 cuốn, không phải
  // 1 ruột + 1 bìa). Chỉ gộp ở bản in — dữ liệu vẫn từng dòng để markup riêng + xuống SX tách lệnh.
  const lines = gopTheoNhom(d.items, (it) => ({
    nhom: it.nhom,
    ten: it.product_name,
    soLuong: it.quantity,
    donViTinh: it.unit,
    thanhTien: Math.max(0, it.selling_price - it.discount_amount),   // net chưa VAT
    tienVat: it.vat_amount,
    vatPct: it.vat_percent,
    kichThuoc: it.product_spec_text,
    dienGiai: it.dien_giai,
  }));
  const netSubtotal = lines.reduce((s, l) => s + l.thanhTien, 0); // Σ tiền hàng chưa VAT
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
              {lines.map((g, i) => {
                // Nhóm 1 dòng → mã hàng + ghi chú của chính dòng đó; nhóm gộp → để trống vì mã
                // của ruột và bìa khác nhau, in một cái ra là sai.
                const don = g.goc.length === 1 ? g.goc[0] : null;
                return (
                  <tr key={g.key}>
                    <td className="c">{i + 1}</td>
                    <td className="c">{don?.estimate_number ?? "—"}</td>
                    <td>
                      <span className="q-prod">{g.ten}</span>{don?.note ? `, ${don.note}` : ""}
                      {/* Diễn giải quy cách: gạch đầu dòng dưới tên SP (nhóm gộp → mỗi phần 1 mục). */}
                      {g.dienGiai.length > 0 && (
                        <ul className="q-dg">
                          {g.dienGiai.map((ln, k) => <li key={k}>{ln}</li>)}
                        </ul>
                      )}
                    </td>
                    <td className="c">{g.kichThuoc ?? "—"}</td>
                    <td className="c">{g.donViTinh}</td>
                    <td className="c">{g.soLuong.toLocaleString("vi-VN")}</td>
                    <td className="r">{money(g.donGia)}</td>
                    <td className="r">{money(g.thanhTien)}</td>
                  </tr>
                );
              })}
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
function vnd(v: number): string {
  return Math.round(v).toLocaleString("vi-VN") + "₫";
}
function numf(v: number): string {
  return Math.round(v).toLocaleString("vi-VN");
}

