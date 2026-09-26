import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Calendar,
  ShieldCheck,
  Clock,
  Search,
  Filter,
  Layers,
  RefreshCw,
  SlidersHorizontal,
  List,
  Building,
  User,
  ArrowRight,
  Tag,
  Copy,
  Check,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  X,
  FileText,
  Download,
  Wallet,
  Package,
  ShoppingCart,
  Factory,
  BookOpen,
  MonitorSmartphone,
  ArrowUpCircle,
  Laptop,
  Smartphone,
  Tablet,
  Globe,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import {
  ApiError,
  api,
  type AuditFacets,
  type AuditPage,
  type AuditQuery,
  type AuditRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import type { NavigateFn } from "../components/AppShell";
import { Select } from "../components/Select";
import "./activity.css";

/* Nhãn hành động, nhóm và khoá quyền của từng mã ĐỀU do máy chủ trả về (`app/audit_registry.py`).
   Trước 25/09/2026 màn này tự khai một bảng 16 mã trong khi backend ghi gần 300 — 93% dòng hiện
   nhãn title-case tên cột ("Employee Create Account") giữa một giao diện tiếng Việt, và bốn chip
   nhóm đều đếm 0 vì mã lạ rơi vào nhóm "khác" mà màn không render tab nào cho nó.
   Ở đây chỉ còn phần TRÌNH BÀY: mỗi nhóm một icon + một màu. */
const ICON_NHOM: Record<string, { icon: typeof Activity; badge: string }> = {
  kinh_doanh: { icon: ShoppingCart, badge: "badge--blue" },
  san_xuat: { icon: Factory, badge: "badge--purple" },
  kho: { icon: Package, badge: "badge--amber" },
  mua_hang: { icon: ShoppingCart, badge: "badge--teal" },
  ke_toan: { icon: Wallet, badge: "badge--green" },
  nhan_su: { icon: User, badge: "badge--indigo" },
  luong: { icon: Wallet, badge: "badge--rose" },
  danh_muc: { icon: BookOpen, badge: "badge--slate" },
  he_thong: { icon: ShieldCheck, badge: "badge--red" },
  khac: { icon: Tag, badge: "badge--slate" },
};

function trinhBay(nhom: string) {
  return ICON_NHOM[nhom] ?? ICON_NHOM.khac;
}

/* --- Ngày giờ ------------------------------------------------------------------------------ */

function ngayISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

function formatExactTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;

  const now = new Date();
  const diffSec = Math.floor((now.getTime() - d.getTime()) / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHours = Math.floor(diffMin / 60);

  if (diffSec < 45) return "Vừa xong";
  if (diffMin < 60) return `${diffMin} phút trước`;
  if (diffHours < 24 && now.getDate() === d.getDate()) {
    return `Hôm nay ${d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`;
  }

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (yesterday.getDate() === d.getDate() && yesterday.getMonth() === d.getMonth()) {
    return `Hôm qua ${d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`;
  }

  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

function getDateGroupLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Khác";

  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 86400000;
  const weekStart = todayStart - 6 * 86400000;

  const time = d.getTime();
  if (time >= todayStart) return "Hôm nay";
  if (time >= yesterdayStart) return "Hôm qua";
  if (time >= weekStart) return "7 ngày qua";

  return d.toLocaleDateString("vi-VN", { month: "long", year: "numeric" });
}

function getUserInitials(name: string | null): string {
  if (!name || name.trim() === "") return "HT";
  const parts = name.trim().split(" ");
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export interface ParsedUA {
  browser: string;
  browserVer?: string;
  os: string;
  deviceType: "desktop" | "mobile" | "tablet";
  raw: string;
}

export function parseUserAgent(ua: string | null): ParsedUA | null {
  if (!ua) return null;

  let browser = "Trình duyệt khác";
  let browserVer = "";
  let os = "Hệ điều hành khác";
  let deviceType: "desktop" | "mobile" | "tablet" = "desktop";

  if (/iPad|Tablet|PlayBook|Silk/i.test(ua)) {
    deviceType = "tablet";
  } else if (/Mobile|iPhone|Android/i.test(ua)) {
    deviceType = "mobile";
  }

  if (/Windows NT 10/i.test(ua)) os = "Windows 10/11";
  else if (/Windows NT 6\.3/i.test(ua)) os = "Windows 8.1";
  else if (/Windows NT 6\.1/i.test(ua)) os = "Windows 7";
  else if (/Windows/i.test(ua)) os = "Windows";
  else if (/Mac OS X/i.test(ua)) {
    const macMatch = ua.match(/Mac OS X ([\d_]+)/);
    os = macMatch ? `macOS ${macMatch[1].replace(/_/g, ".")}` : "macOS";
  } else if (/Android/i.test(ua)) {
    const andMatch = ua.match(/Android ([\d.]+)/);
    os = andMatch ? `Android ${andMatch[1]}` : "Android";
  } else if (/iPhone|iPad|iPod/i.test(ua)) {
    const iosMatch = ua.match(/OS ([\d_]+)/);
    os = iosMatch ? `iOS ${iosMatch[1].replace(/_/g, ".")}` : "iOS";
  } else if (/Linux/i.test(ua)) {
    os = "Linux";
  }

  const edgMatch = ua.match(/Edg\/([\d.]+)/);
  const chromeMatch = ua.match(/Chrome\/([\d.]+)/);
  const firefoxMatch = ua.match(/Firefox\/([\d.]+)/);
  const safariMatch = ua.match(/Version\/([\d.]+).*Safari/);

  if (edgMatch) {
    browser = "Edge";
    browserVer = edgMatch[1].split(".")[0];
  } else if (chromeMatch) {
    browser = "Chrome";
    browserVer = chromeMatch[1].split(".")[0];
  } else if (firefoxMatch) {
    browser = "Firefox";
    browserVer = firefoxMatch[1].split(".")[0];
  } else if (safariMatch) {
    browser = "Safari";
    browserVer = safariMatch[1].split(".")[0];
  }

  return { browser, browserVer, os, deviceType, raw: ua };
}

/* --- Nội dung dòng ------------------------------------------------------------------------- */

function FormattedDetail({ detail }: { detail: string | null }) {
  const [copiedText, setCopiedText] = useState<string | null>(null);

  if (!detail) return <span className="act-muted">—</span>;

  const handleCopy = (text: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopiedText(text);
    setTimeout(() => setCopiedText(null), 1800);
  };

  if (detail.includes("→")) {
    const parts = detail.split("→");
    return (
      <span className="act-detail__highlighted">
        <span className="act-detail__text">{parts[0].trim()}</span>
        <ArrowRight size={12} className="act-detail__arrow" />
        <span className="act-detail__status-tag">{parts.slice(1).join("→").trim()}</span>
      </span>
    );
  }

  const lsxMatch = detail.match(/LSX\d+[-\w]*/i);
  if (lsxMatch) {
    const code = lsxMatch[0];
    const parts = detail.split(code);
    return (
      <span className="act-detail__inline-flex">
        {parts[0]}
        <span
          className="act-detail__code-tag"
          onClick={(e) => handleCopy(code, e)}
          title="Click để copy mã LSX"
        >
          {code}
          {copiedText === code ? (
            <Check size={10} className="act-copy-icon act-copy-icon--success" />
          ) : (
            <Copy size={10} className="act-copy-icon" />
          )}
        </span>
        {parts.slice(1).join(code)}
      </span>
    );
  }

  return <span className="act-detail__text">{detail}</span>;
}

/* --- Bộ lọc --------------------------------------------------------------------------------- */

interface BoLoc {
  q: string;
  tuNgay: string;
  denNgay: string;
  nhom: string; // "" = tất cả
  action: string;
  actorId: string;
  loai: string;
}

const CUA_SO_MAC_DINH_NGAY = 30;

/** Khoảng N ngày gần đây, tính CẢ hôm nay. Đếm bao gồm là điều người dùng đọc được từ nhãn:
 *  "Hôm nay" phải ra đúng một ngày chứ không kéo theo hôm qua, và "7 ngày" là 7 ngày chứ không
 *  phải 8. */
function khoangNgay(soNgay: number): { tuNgay: string; denNgay: string } {
  const den = new Date();
  const tu = new Date();
  tu.setDate(den.getDate() - (soNgay - 1));
  return { tuNgay: ngayISO(tu), denNgay: ngayISO(den) };
}

function locMacDinh(): BoLoc {
  return { q: "", ...khoangNgay(CUA_SO_MAC_DINH_NGAY), nhom: "", action: "", actorId: "", loai: "" };
}

/** Dãy ô trang để vẽ "1 · 2 · 3 … n": luôn giữ trang ĐẦU và trang CUỐI, cộng một cửa sổ quanh
 *  trang đang xem, chỗ đứt thì chèn "…". Không đổ hết n nút ra vì lọc 30 ngày ở đây đã ra ngót
 *  trăm trang — một hàng nút dài bằng màn hình thì không ai bấm trúng. */
function dayTrang(hienTai: number, tong: number): (number | "…")[] {
  const TOI_DA = 7;
  if (tong <= TOI_DA) return Array.from({ length: tong }, (_, i) => i + 1);
  const giu = new Set<number>([1, tong, hienTai, hienTai - 1, hienTai + 1]);
  // Ở sát hai đầu thì nới cửa sổ về phía còn lại, để số ô luôn bằng nhau — dãy không co giãn
  // giật cục mỗi lần bấm.
  if (hienTai <= 3) [2, 3, 4].forEach((n) => giu.add(n));
  if (hienTai >= tong - 2) [tong - 1, tong - 2, tong - 3].forEach((n) => giu.add(n));
  const ds = [...giu].filter((n) => n >= 1 && n <= tong).sort((a, b) => a - b);
  const ra: (number | "…")[] = [];
  ds.forEach((n, i) => {
    if (i > 0 && n - ds[i - 1] > 1) ra.push("…");
    ra.push(n);
  });
  return ra;
}

export function ActivityLogPage({
  navigate,
  eventTick = 0,
}: {
  navigate?: NavigateFn;
  /** Tăng khi kênh SSE báo có dòng nhật ký mới (AppShell). */
  eventTick?: number;
}) {
  const { token } = useAuth();

  // Bộ lọc KHÔNG ghi ra URL. App này không có router — AppShell điều hướng bằng state và để
  // URL đứng yên ở `/`, thậm chí xoá hash deep-link ngay sau khi dùng để thanh địa chỉ không
  // nói dối về màn đang mở. Màn này từng ghi `?nk_*` cho F5/chia sẻ link, nhưng thế là ngược
  // lệ: tham số nằm lại khi sang màn khác rồi tự bật lại bộ lọc lúc quay về.
  const [loc, setLoc] = useState<BoLoc>(locMacDinh);
  const [qGo, setQGo] = useState(loc.q); // ô tìm kiếm gõ tới đâu (chưa gửi đi)
  const [trang, setTrang] = useState<AuditPage | null>(null);
  const [facets, setFacets] = useState<AuditFacets | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  // Mặc định BẢNG: màn này để TRA — so ngày/người/hành động theo cột nhanh hơn đọc dòng thời
  // gian, và một màn hình chứa được nhiều dòng hơn. Timeline vẫn còn ở nút chuyển.
  const [viewMode, setViewMode] = useState<"timeline" | "table">("table");
  const [limit, setLimit] = useState(25);
  const [soTrang, setSoTrang] = useState(1);
  /** Mốc ảnh chụp do máy chủ trả ở trang 1; các trang sau gửi lại nguyên si để xấp trang không
   *  trượt khi có dòng mới ghi vào giữa lúc đang đọc. `ref` chứ không `state`: nó không vẽ ra gì. */
  const neoRef = useRef<string | null>(null);

  const [selectedRow, setSelectedRow] = useState<AuditRow | null>(null);
  const [showRawUa, setShowRawUa] = useState(false);
  const [copiedIp, setCopiedIp] = useState(false);
  const [copiedUa, setCopiedUa] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [dangXuat, setDangXuat] = useState(false);
  /** Có dòng mới trong lúc đang đọc — hiện băng, KHÔNG tự chèn vào danh sách đang xem. */
  const [coDongMoi, setCoDongMoi] = useState(false);
  const tickDaXem = useRef(eventTick);

  // Xuất CSV là ô quyền RIÊNG (`activity_log.can_export`): người chỉ được ĐỌC nhật ký thì không
  // được mang cả bảng — kèm số tiền — ra khỏi hệ thống. Máy chủ vẫn là cổng thật (403), đây chỉ
  // là chuyện không chìa ra một cái nút bấm vào là hỏng.
  const coTheXuat = useCan()("activity_log", "export");

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 2200);
  };

  /* Nhóm → danh sách mã hành động. Máy chủ lọc theo `action`, còn chip là chuyện trình bày, nên
     màn dịch nhóm thành danh sách mã bằng chính facets máy chủ vừa trả. */
  const maTheoNhom = useMemo(() => {
    const m: Record<string, string[]> = {};
    (facets?.hanh_dong ?? []).forEach((h) => {
      (m[h.nhom] ??= []).push(h.ma);
    });
    return m;
  }, [facets]);

  const truyVan = useCallback(
    (so: number, neo: string | null): AuditQuery => {
      const action = loc.action
        ? [loc.action]
        : loc.nhom
          ? (maTheoNhom[loc.nhom] ?? ["__khong_co__"])
          : undefined;
      return {
        q: loc.q || undefined,
        tu_ngay: loc.tuNgay || undefined,
        den_ngay: loc.denNgay ? `${loc.denNgay}T23:59:59` : undefined,
        action,
        actor_id: loc.actorId ? [Number(loc.actorId)] : undefined,
        loai: loc.loai ? [loc.loai] : undefined,
        limit,
        trang: so,
        neo,
      };
    },
    [loc, limit, maTheoNhom],
  );

  const napTrang = useCallback(
    (so: number) => {
      if (!token) return;
      // Về trang 1 là chụp lại ảnh mới: bỏ neo cũ đi để thấy những dòng vừa ghi.
      const neo = so <= 1 ? null : neoRef.current;
      setLoading(true);
      setError(null);
      setSoTrang(so);
      api.rbac
        .activityLog(token, truyVan(so, neo))
        .then((p) => {
          // Số dòng bị che chỉ có ở trang ĐẦU — giữ lại khi lật sang trang sau.
          setTrang((cu) => (so === 1 ? p : { ...p, so_dong_bi_an: cu?.so_dong_bi_an ?? null }));
          neoRef.current = p.neo;
          setCoDongMoi(false);
          tickDaXem.current = eventTick;
        })
        .catch((err) => {
          if (err instanceof ApiError && err.status === 403) setForbidden(true);
          else setError("Không tải được nhật ký hoạt động.");
        })
        .finally(() => setLoading(false));
    },
    [token, truyVan, eventTick],
  );

  const napFacets = useCallback(() => {
    if (!token) return;
    api.rbac
      .activityFacets(token, {
        q: loc.q || undefined,
        tu_ngay: loc.tuNgay || undefined,
        den_ngay: loc.denNgay ? `${loc.denNgay}T23:59:59` : undefined,
      })
      .then(setFacets)
      .catch(() => {});
  }, [token, loc.q, loc.tuNgay, loc.denNgay]);

  // Đổi bộ lọc → về trang đầu. Gộp một effect để không bắn hai lượt gọi chồng nhau.
  useEffect(() => {
    napTrang(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loc, limit]);

  useEffect(() => {
    napFacets();
  }, [napFacets]);

  // Dòng mới tới trong lúc đang đọc: chỉ bật băng. Tự chèn vào danh sách là làm nhảy chỗ người ta
  // đang đọc dở — với một màn dùng để TRA thì đó là phá, không phải tiện.
  useEffect(() => {
    if (eventTick !== tickDaXem.current) setCoDongMoi(true);
  }, [eventTick]);

  // Gõ tìm kiếm: chờ người ta ngừng gõ rồi mới hỏi máy chủ.
  useEffect(() => {
    if (qGo === loc.q) return;
    const t = setTimeout(() => setLoc((v) => ({ ...v, q: qGo })), 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qGo]);

  // Esc đóng cửa sổ chi tiết — trước đây chỉ bấm được vào nút X hoặc nền.
  useEffect(() => {
    if (!selectedRow) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedRow(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedRow]);

  const rows = trang?.items ?? [];
  const tongSoTrang = Math.max(1, Math.ceil((trang?.tong ?? rows.length) / limit));

  const groupedTimeline = useMemo(() => {
    const groups: { label: string; items: AuditRow[] }[] = [];
    let currentLabel = "";
    let currentItems: AuditRow[] = [];
    rows.forEach((r) => {
      const groupLabel = getDateGroupLabel(r.created_at);
      if (groupLabel !== currentLabel) {
        if (currentItems.length > 0) groups.push({ label: currentLabel, items: currentItems });
        currentLabel = groupLabel;
        currentItems = [r];
      } else {
        currentItems.push(r);
      }
    });
    if (currentItems.length > 0) groups.push({ label: currentLabel, items: currentItems });
    return groups;
  }, [rows]);

  const nhanLoai = useMemo(() => {
    const m: Record<string, { nhan: string; path: string }> = {};
    (facets?.loai ?? []).forEach((l) => (m[l.loai] = { nhan: l.nhan, path: l.path }));
    return m;
  }, [facets]);

  /** `giay:12` → "Giấy #12". Loại ngoài khối danh mục thì giữ nguyên mã — thà thô còn hơn đoán sai. */
  const moTaTarget = (target: string): string => {
    if (!target) return "";
    const [loai, id] = target.split(":");
    const d = nhanLoai[loai];
    return d ? `${d.nhan}${id ? ` #${id}` : ""}` : target;
  };

  const moBanGhi = (r: AuditRow) => {
    const d = r.target_loai ? nhanLoai[r.target_loai] : undefined;
    if (d && navigate) navigate(d.path);
  };

  const datLoc = (v: Partial<BoLoc>) => setLoc((cu) => ({ ...cu, ...v }));

  const nhanhNgay = (soNgay: number) => datLoc(khoangNgay(soNgay));

  const datLai = () => {
    const m = locMacDinh();
    setQGo("");
    setLoc(m);
  };

  const xuatCSV = () => {
    if (!token || dangXuat) return;
    setDangXuat(true);
    api.rbac
      .activityExport(token, { ...truyVan(1, null), limit: undefined, trang: undefined })
      .then((url) => {
        const link = document.createElement("a");
        link.href = url;
        link.setAttribute("download", `nhat-ky-hoat-dong-${ngayISO(new Date())}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        showToast("Đã xuất CSV theo đúng bộ lọc đang xem.");
      })
      .catch((err) => {
        showToast(
          err instanceof ApiError && err.status === 403
            ? "Bạn không có quyền xuất nhật ký."
            : "Không xuất được CSV.",
        );
      })
      .finally(() => setDangXuat(false));
  };

  // Kể cả khoảng ngày: người bấm "Hôm nay" rồi muốn quay lại toàn cảnh cũng cần một đường lùi.
  const macDinh = locMacDinh();
  const coLoc =
    !!loc.q || !!loc.nhom || !!loc.action || !!loc.actorId || !!loc.loai ||
    loc.tuNgay !== macDinh.tuNgay || loc.denNgay !== macDinh.denNgay;

  if (forbidden) {
    return (
      <main className="act-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền xem nhật ký hoạt động.
        </div>
      </main>
    );
  }

  const selectedNhom = selectedRow ? trinhBay(selectedRow.nhom) : null;
  const SelectedIcon = selectedNhom?.icon;

  return (
    <main className="act-page">
      {toastMsg && <div className="act-toast">{toastMsg}</div>}

      <header className="act-header">
        <div>

          <h1 className="act-title">Nhật ký hoạt động</h1>
        </div>
        <div className="act-header-actions">
          {coTheXuat && (
            <button
              type="button"
              className="btn btn--ghost"
              onClick={xuatCSV}
              disabled={dangXuat}
              title="Tải CSV toàn bộ dòng khớp bộ lọc (máy chủ xuất, không giới hạn trang đang xem)"
            >
              <Download size={14} />
              <span>{dangXuat ? "Đang xuất…" : "Xuất CSV"}</span>
            </button>
          )}
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => {
              napTrang(soTrang);
              napFacets();
            }}
          >
            <RefreshCw size={14} />
            <span>Làm mới</span>
          </button>
        </div>
      </header>

      {coDongMoi && (
        <button
          type="button"
          className="act-bang-moi"
          onClick={() => {
            napTrang(1);
            napFacets();
          }}
        >
          <ArrowUpCircle size={14} />
          Có bản ghi mới — bấm để xem
        </button>
      )}

      <section className="act-filters">
        <div className="act-filter-main">
          <div className="act-search">
            <Search size={14} className="act-search-icon" />
            <input
              className="act-search-input"
              placeholder="Tìm trong nội dung / đối tượng…"
              value={qGo}
              onChange={(e) => setQGo(e.target.value)}
            />
            {qGo && (
              <button
                type="button"
                className="act-search-clear"
                onClick={() => {
                  setQGo("");
                  datLoc({ q: "" });
                }}
                title="Xóa từ khóa"
              >
                <X size={12} />
              </button>
            )}
          </div>

          <div className="act-date-group">
            <div className="act-date-inputs">
              <Calendar size={13} className="act-select-icon" />
              <input
                type="date"
                className="act-date-input"
                value={loc.tuNgay}
                max={loc.denNgay || undefined}
                onChange={(e) => datLoc({ tuNgay: e.target.value })}
                title="Từ ngày"
              />
              <span className="act-date-sep">→</span>
              <input
                type="date"
                className="act-date-input"
                value={loc.denNgay}
                min={loc.tuNgay || undefined}
                onChange={(e) => datLoc({ denNgay: e.target.value })}
                title="Đến ngày"
              />
            </div>

            <div className="act-segmented-dates">
              {[
                { n: 1, nhan: "Hôm nay" },
                { n: 7, nhan: "7 ngày" },
                { n: 30, nhan: "30 ngày" },
                { n: 365, nhan: "1 năm" },
              ].map((x) => (
                <button
                  key={x.n}
                  type="button"
                  className="act-date-btn"
                  onClick={() => nhanhNgay(x.n)}
                >
                  {x.nhan}
                </button>
              ))}
            </div>
          </div>

          {coLoc && (
            <button
              type="button"
              className="act-btn-reset"
              onClick={datLai}
              title="Bỏ mọi bộ lọc, về 30 ngày gần nhất"
            >
              <RotateCcw size={12} />
              <span>Đặt lại</span>
            </button>
          )}

          <div className="act-view-toggle">
            <button
              type="button"
              className={`act-view-btn${viewMode === "timeline" ? " is-active" : ""}`}
              onClick={() => setViewMode("timeline")}
            >
              <Clock size={13} /> Timeline
            </button>
            <button
              type="button"
              className={`act-view-btn${viewMode === "table" ? " is-active" : ""}`}
              onClick={() => setViewMode("table")}
            >
              <List size={13} /> Bảng
            </button>
          </div>
        </div>

        <div className="act-filter-sub">
          <div className="act-select-group">
            <SlidersHorizontal size={13} className="act-select-icon" />
            <Select
              portal
              searchable
              searchPlaceholder="Gõ tên hành động…"
              ariaLabel="Lọc theo hành động"
              className="act-sel-trigger act-sel-trigger--wide"
              listClassName="act-sel-list"
              value={loc.action}
              onChange={(v) => datLoc({ action: v ?? "" })}
              options={[
                { value: "", label: "Tất cả hành động" },
                ...(facets?.hanh_dong ?? []).map((h) => ({
                  value: h.ma,
                  label: h.nhan,
                  hint: String(h.so_dong),
                  // Mã máy chủ không hiện ra, nhưng người quen đọc log vẫn gõ "quote_create".
                  search: h.ma,
                })),
              ]}
            />
          </div>

          <div className="act-select-group">
            <User size={13} className="act-select-icon" />
            <Select
              portal
              searchable
              searchPlaceholder="Gõ tên người…"
              ariaLabel="Lọc theo người thao tác"
              className="act-sel-trigger"
              listClassName="act-sel-list"
              value={loc.actorId}
              onChange={(v) => datLoc({ actorId: v ?? "" })}
              options={[
                { value: "", label: "Tất cả người thao tác" },
                ...(facets?.nguoi ?? [])
                  .filter((n) => n.id !== null)
                  .map((n) => ({
                    value: String(n.id),
                    label: n.ten ?? `#${n.id}`,
                    hint: String(n.so_dong),
                  })),
              ]}
            />
          </div>

          <div className="act-select-group">
            <Tag size={13} className="act-select-icon" />
            {/* Lọc theo LOẠI đối tượng — cần vì 12 màn danh mục dùng chung ba mã hành động. */}
            <Select
              portal
              searchable
              searchPlaceholder="Gõ tên đối tượng…"
              ariaLabel="Lọc theo loại đối tượng"
              className="act-sel-trigger"
              listClassName="act-sel-list"
              value={loc.loai}
              onChange={(v) => datLoc({ loai: v ?? "" })}
              options={[
                { value: "", label: "Tất cả đối tượng" },
                ...(facets?.loai ?? []).map((l) => ({
                  value: l.loai,
                  label: l.nhan,
                  search: l.loai,
                })),
              ]}
            />
          </div>
        </div>

        <div className="act-pills-strip">
          <button
            type="button"
            className={`act-pill${loc.nhom === "" ? " is-active" : ""}`}
            onClick={() => datLoc({ nhom: "", action: "" })}
          >
            <Layers size={13} />
            <span>Tất cả</span>
            <span className="act-pill-count">{trang?.tong ?? "…"}</span>
          </button>
          {(facets?.nhom ?? [])
            .filter((n) => n.so_dong > 0)
            .map((n) => {
              const tb = trinhBay(n.khoa);
              const Icon = tb.icon;
              return (
                <button
                  key={n.khoa}
                  type="button"
                  className={`act-pill${loc.nhom === n.khoa ? " is-active" : ""}`}
                  onClick={() =>
                    datLoc({ nhom: loc.nhom === n.khoa ? "" : n.khoa, action: "" })
                  }
                >
                  <Icon size={13} />
                  <span>{n.nhan}</span>
                  <span className="act-pill-count">{n.so_dong}</span>
                </button>
              );
            })}
        </div>
      </section>

      {!!trang?.so_dong_bi_an && (
        <div className="act-bang-an" role="status">
          <EyeOff size={14} />
          <span>
            <strong>{trang.so_dong_bi_an}</strong> dòng khớp bộ lọc nhưng bị ẩn vì bạn không có
            quyền xem màn đã sinh ra chúng (nhật ký chứa số tiền của các màn đó).
          </span>
        </div>
      )}

      <section className="act-body">
        {loading && rows.length === 0 ? (
          <div className="act-skeleton-container">
            {[1, 2, 3, 4, 5].map((i) => (
              <div className="act-skeleton-row" key={i}>
                <div className="act-skeleton-avatar" />
                <div className="act-skeleton-body">
                  <div className="act-skeleton-line act-skeleton-line--short" />
                  <div className="act-skeleton-line act-skeleton-line--long" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="banner banner--error" role="alert">
            <span>{error}</span>
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => napTrang(soTrang)}
            >
              Thử lại
            </button>
          </div>
        ) : rows.length === 0 ? (
          <div className="act-empty">
            <Filter size={32} className="act-empty-icon" />
            <p className="act-empty-title">Không tìm thấy nhật ký phù hợp</p>
            <p className="act-empty-desc">
              Khoảng ngày đang xem: {loc.tuNgay} → {loc.denNgay}. Nới khoảng ngày hoặc bỏ bớt bộ lọc.
            </p>
            {coLoc && (
              <button type="button" className="act-btn-ghost-sm" onClick={datLai}>
                <RotateCcw size={12} />
                Đặt lại bộ lọc
              </button>
            )}
          </div>
        ) : viewMode === "timeline" ? (
          <div className="act-timeline-container">
            {groupedTimeline.map((group) => (
              <div className="act-tl-group" key={group.label}>
                <div className="act-tl-group-header">
                  <Calendar size={13} />
                  <span>{group.label}</span>
                  <span className="act-tl-group-count">{group.items.length} bản ghi</span>
                </div>

                <div className="act-timeline">
                  {group.items.map((r) => {
                    const tb = trinhBay(r.nhom);
                    const IconComp = tb.icon;
                    const actorName = r.actor_name || "Hệ thống";
                    const coCua = !!(r.target_loai && nhanLoai[r.target_loai] && navigate);

                    return (
                      <div
                        className="act-tl-row"
                        key={r.id}
                        onClick={() => setSelectedRow(r)}
                        title="Click để xem chi tiết bản ghi nhật ký này"
                      >
                        <div className="act-tl-avatar-container">
                          <div className={`act-tl-node ${tb.badge}`}>
                            <IconComp size={12} />
                          </div>
                        </div>

                        <div className="act-tl-content">
                          <div className="act-tl-head">
                            <span className="act-avatar-xs">{getUserInitials(r.actor_name)}</span>
                            <span className="act-tl-actor">{actorName}</span>

                            <span className={`act-badge ${tb.badge}`}>
                              <IconComp size={11} />
                              {r.nhan}
                            </span>

                            {r.target && (
                              <span
                                className={`act-target-pill${coCua ? " act-target-pill--link" : ""}`}
                                onClick={(e) => {
                                  if (!coCua) return;
                                  e.stopPropagation();
                                  moBanGhi(r);
                                }}
                                title={coCua ? `Mở màn ${nhanLoai[r.target_loai!].nhan}` : r.target}
                              >
                                <Tag size={11} />
                                {moTaTarget(r.target)}
                              </span>
                            )}

                            <span className="act-tl-time" title={formatExactTime(r.created_at)}>
                              <Clock size={11} />
                              {formatRelativeTime(r.created_at)}
                            </span>
                          </div>

                          <div className="act-tl-body">
                            <FormattedDetail detail={r.detail} />
                          </div>
                        </div>

                        <div className="act-tl-meta">
                          <span className="act-tl-exact">{formatExactTime(r.created_at)}</span>
                          <span className="act-tl-id">#{r.id}</span>
                          <button
                            type="button"
                            className="act-btn-inspect"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedRow(r);
                            }}
                            title="Xem chi tiết đầy đủ"
                          >
                            <Eye size={12} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="act-table-wrap">
            <table className="act-table">
              <thead>
                <tr>
                  <th style={{ width: 170 }}>Thời gian</th>
                  <th style={{ width: 170 }}>Người thực hiện</th>
                  <th style={{ width: 210 }}>Hành động</th>
                  <th style={{ width: 170 }}>Đối tượng</th>
                  <th>Chi tiết</th>
                  <th style={{ width: 40 }}></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const tb = trinhBay(r.nhom);
                  const IconComp = tb.icon;
                  const actorName = r.actor_name || "Hệ thống";

                  return (
                    <tr key={r.id} onClick={() => setSelectedRow(r)} className="act-table-row">
                      <td className="act-td-time">
                        <span className="act-time-rel">{formatRelativeTime(r.created_at)}</span>
                        <span className="act-time-sub">{formatExactTime(r.created_at)}</span>
                      </td>
                      <td>
                        <div className="act-actor-cell">
                          <span className="act-avatar-xs">{getUserInitials(r.actor_name)}</span>
                          <span className="act-actor-name">{actorName}</span>
                        </div>
                      </td>
                      <td>
                        <span className={`act-badge ${tb.badge}`}>
                          <IconComp size={11} />
                          {r.nhan}
                        </span>
                      </td>
                      <td>
                        {r.target ? (
                          <span className="act-mono-pill">{moTaTarget(r.target)}</span>
                        ) : (
                          <span className="act-muted">—</span>
                        )}
                      </td>
                      <td>
                        <FormattedDetail detail={r.detail} />
                      </td>
                      <td>
                        <button
                          type="button"
                          className="act-btn-inspect"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedRow(r);
                          }}
                          title="Xem chi tiết đầy đủ"
                        >
                          <Eye size={12} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {!error && rows.length > 0 && (
          <footer className="act-footer">
            <div className="act-footer-info">
              Trang <strong>{soTrang}</strong>/{tongSoTrang} · {rows.length} dòng
              {trang?.tong != null && (
                <>
                  {" "}
                  / tổng <strong>{trang.tong}</strong> bản ghi khớp bộ lọc
                </>
              )}
            </div>

            <div className="act-footer-nav">
              <label className="act-size-select">
                <span>Dòng/trang:</span>
                <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
                  <option value={15}>15</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </label>

              <nav className="act-page-btns" aria-label="Phân trang nhật ký">
                <button
                  type="button"
                  className="act-btn-p"
                  disabled={soTrang <= 1 || loading}
                  onClick={() => napTrang(soTrang - 1)}
                  title="Trang trước"
                  aria-label="Trang trước"
                >
                  <ChevronLeft size={14} />
                </button>
                {dayTrang(soTrang, tongSoTrang).map((o, i) =>
                  o === "…" ? (
                    <span className="act-page-dots" key={`d${i}`} aria-hidden="true">
                      …
                    </span>
                  ) : (
                    <button
                      type="button"
                      key={o}
                      className={`act-page-num${o === soTrang ? " act-page-num--active" : ""}`}
                      disabled={loading}
                      aria-current={o === soTrang ? "page" : undefined}
                      onClick={() => o !== soTrang && napTrang(o)}
                    >
                      {o}
                    </button>
                  ),
                )}
                <button
                  type="button"
                  className="act-btn-p"
                  disabled={soTrang >= tongSoTrang || loading}
                  onClick={() => napTrang(soTrang + 1)}
                  title="Trang sau"
                  aria-label="Trang sau"
                >
                  <ChevronRight size={14} />
                </button>
              </nav>
            </div>
          </footer>
        )}
      </section>

      {selectedRow && (
        <div className="act-modal-overlay" onClick={() => setSelectedRow(null)}>
          <div
            className="act-modal-card"
            role="dialog"
            aria-modal="true"
            aria-label={`Chi tiết nhật ký ${selectedRow.id}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="act-modal-header">
              <div className="act-modal-title-group">
                <FileText size={18} className="act-modal-icon" />
                <div>
                  <h3 className="act-modal-title">Chi tiết nhật ký #{selectedRow.id}</h3>
                  <span className="act-modal-sub">{formatExactTime(selectedRow.created_at)}</span>
                </div>
              </div>
              <button
                type="button"
                className="act-modal-close"
                onClick={() => setSelectedRow(null)}
                title="Đóng (Esc)"
              >
                <X size={16} />
              </button>
            </div>

            <div className="act-modal-body">
              <div className="act-modal-grid">
                <div className="act-modal-field">
                  <span className="act-modal-label">Người thực hiện</span>
                  <div className="act-actor-cell">
                    <span className="act-avatar-xs">{getUserInitials(selectedRow.actor_name)}</span>
                    <strong className="act-modal-val">
                      {selectedRow.actor_name || "Hệ thống"}
                    </strong>
                  </div>
                </div>

                <div className="act-modal-field">
                  <span className="act-modal-label">Hành động</span>
                  <div>
                    {SelectedIcon && (
                      <span className={`act-badge ${selectedNhom!.badge}`}>
                        <SelectedIcon size={12} />
                        {selectedRow.nhan}
                      </span>
                    )}
                  </div>
                </div>

                <div className="act-modal-field">
                  <span className="act-modal-label">Đối tượng tác động</span>
                  <div>
                    {selectedRow.target ? (
                      <span className="act-mono-pill">{moTaTarget(selectedRow.target)}</span>
                    ) : (
                      <span className="act-muted">— Không xác định —</span>
                    )}
                  </div>
                </div>

                <div className="act-modal-field">
                  <span className="act-modal-label">Thời gian tương đối</span>
                  <span className="act-modal-val">{formatRelativeTime(selectedRow.created_at)}</span>
                </div>

                {/* Ai, TỪ ĐÂU — IP & Thiết bị với giao diện tối ưu */}
                <div className="act-modal-field">
                  <span className="act-modal-label">Địa chỉ IP</span>
                  <div className="act-ip-box">
                    <Globe size={13} className="act-ip-icon" />
                    <span className="act-modal-val">
                      {selectedRow.ip === "::1" || selectedRow.ip === "127.0.0.1"
                        ? "Localhost (::1)"
                        : selectedRow.ip ?? <span className="act-muted">— không ghi nhận —</span>}
                    </span>
                    {selectedRow.ip && (
                      <button
                        type="button"
                        className="act-btn-icon-copy"
                        onClick={() => {
                          navigator.clipboard.writeText(selectedRow.ip!);
                          setCopiedIp(true);
                          setTimeout(() => setCopiedIp(false), 1500);
                        }}
                        title="Sao chép IP"
                      >
                        {copiedIp ? <Check size={11} className="act-copy-icon--success" /> : <Copy size={11} />}
                      </button>
                    )}
                  </div>
                </div>

                <div className="act-modal-field act-modal-field--full">
                  <div className="act-modal-label-row">
                    <span className="act-modal-label">Thiết bị &amp; Trình duyệt</span>
                    {selectedRow.user_agent && (
                      <button
                        type="button"
                        className="act-btn-ghost-xs"
                        onClick={() => setShowRawUa((v) => !v)}
                        title="Bật/tắt xem chuỗi User Agent kỹ thuật"
                      >
                        {showRawUa ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                        {showRawUa ? "Ẩn UA gốc" : "Xem UA gốc"}
                      </button>
                    )}
                  </div>
                  {(() => {
                    const parsed = parseUserAgent(selectedRow.user_agent);
                    if (!parsed) return <span className="act-muted">— không ghi nhận —</span>;

                    const DeviceIcon =
                      parsed.deviceType === "mobile"
                        ? Smartphone
                        : parsed.deviceType === "tablet"
                          ? Tablet
                          : Laptop;

                    return (
                      <div className="act-ua-container">
                        <div className="act-ua-badges">
                          <span className="act-ua-badge act-ua-badge--device">
                            <DeviceIcon size={12} />
                            {parsed.deviceType === "mobile"
                              ? "Điện thoại"
                              : parsed.deviceType === "tablet"
                                ? "Máy tính bảng"
                                : "Máy tính"}
                          </span>
                          <span className="act-ua-badge act-ua-badge--browser">
                            <Globe size={12} />
                            {parsed.browser} {parsed.browserVer ? `v${parsed.browserVer}` : ""}
                          </span>
                          <span className="act-ua-badge act-ua-badge--os">
                            <MonitorSmartphone size={12} />
                            {parsed.os}
                          </span>
                        </div>

                        {showRawUa && (
                          <div className="act-raw-ua-box">
                            <code className="act-raw-ua-text">{selectedRow.user_agent}</code>
                            <button
                              type="button"
                              className="act-btn-icon-copy act-btn-icon-copy--dark"
                              onClick={() => {
                                navigator.clipboard.writeText(selectedRow.user_agent!);
                                setCopiedUa(true);
                                setTimeout(() => setCopiedUa(false), 1500);
                              }}
                              title="Sao chép chuỗi User Agent"
                            >
                              {copiedUa ? <Check size={12} className="act-copy-icon--success" /> : <Copy size={12} />}
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })()}
                </div>
              </div>

              <div className="act-modal-section">
                <span className="act-modal-label">Nội dung chi tiết</span>
                <div className="act-modal-detail-box">
                  <FormattedDetail detail={selectedRow.detail} />
                </div>
              </div>
            </div>

            <div className="act-modal-footer">
              {selectedRow.target_loai && nhanLoai[selectedRow.target_loai] && navigate && (
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => {
                    moBanGhi(selectedRow);
                    setSelectedRow(null);
                  }}
                >
                  <Building size={14} />
                  Mở màn {nhanLoai[selectedRow.target_loai].nhan}
                </button>
              )}
              <button
                type="button"
                className="act-btn-compact"
                onClick={() => setSelectedRow(null)}
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
