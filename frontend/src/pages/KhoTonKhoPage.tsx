// Màn "Kho hàng" của MỘT kho vật lý — bấm 1 kho dưới section "Kho hàng" trên navbar.
//
// Đây là VIỆC CỦA KHO (chỉ ai có `can_view_stock` mới thấy — gate ở AppShell). Gồm 2 tab:
//   • Tồn kho:  gom lô theo VẬT TƯ, bung xem từng lô (tồn = Σ sl_con_lai, spec §6).
//   • Phiếu kho: phiếu nhập/xuất ĐÃ LẬP tại kho này (chuyển vào đây thay vì ở Hộp yêu cầu — phiếu
//     là chứng từ của kho, nên nằm cùng chỗ với tồn/ngưỡng).
// Đặt ngưỡng tồn nằm ở đây (không ở màn yêu cầu) vì ngưỡng gắn với kho vật lý: bấm ô Min/Max
// hoặc badge Trạng thái của 1 mã → popup đặt ngưỡng (chỉ khi có quyền set_threshold).
// Giá vốn CHỈ hiện với `can_view_cost` — thiếu quyền thì cột giá biến mất (ẩn cột, không "—").
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type HangLoai,
  type SoGiaRow,
  type StockLevel,
  type StockLot,
  type StockMaterialHistory,
  type StockThreshold,
  type StockVoucher,
  type StockVoucherStatus,
} from "../api/client";
import { useCan } from "../auth/permissions";
import { CodeLink } from "../components/CodeLink";
import { Icon } from "../components/Icons";
import { Select } from "../components/Select";
import { StockLevelChip } from "../components/StockLevelChip";
import type { NavigateFn } from "../components/AppShell";
import { fmtDateISO, money } from "../utils/format";
import { qrToSvg } from "../lib/qr";
import { tenDonVi, useNapTenDonVi } from "./tenDonVi";
import {
  DateFilterHead,
  NumFilterHead,
  PageSizeSelect,
  DEFAULT_PAGE_SIZE,
  VoucherStatusBadge,
  fmtQty,
  inNumRange,
  todayISO,
  useHeaderTitles,
} from "./khoShared";
import { InboxRequestDrawer, VoucherDrawer } from "./KhoYeuCauPage";
import { ConfirmDialog } from "../components/ConfirmDialog";
import "./rebuild-catalog.css";
import "./kho-request.css";

import {
  Layers,
  Droplets,
  FlaskConical,
  Box,
  ArrowLeftRight,
  QrCode,
  ShoppingCart,
  Search,
  Printer,
  Check,
} from "lucide-react";

import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";



interface MaterialGroup {
  /** Khoá GỘP của bảng tồn: cặp trỏ danh mục gốc. Chuỗi `"giay:12"` dùng làm key của Map/JSX
   *  vì tuple không so sánh được bằng `===` trong Map. */
  hang_loai: HangLoai;
  hang_id: number;
  key: string;
  code: string | null;
  name: string | null;
  // `dvt` = TÊN có dấu để HIỂN THỊ (tờ/cái); `dvtCode` = MÃ (to/cai) cho logic (vd seed mua hàng).
  dvt: string | null;
  dvtCode: string | null;
  // Ảnh minh hoạ mặt hàng (từ danh mục). null = chưa có ảnh. Sửa được trong drawer (quyền danh mục).
  anh: string | null;
  total: number;
  value: number; // Σ sl_con_lai × đơn giá — chỉ có nghĩa khi thấy giá
  lots: StockLot[];
  // Vị trí cất (kệ/ô) distinct, ƯU TIÊN lô nhập gần nhất → rồi giữ thứ tự xuất hiện đầu.
  // Rỗng = chưa lô nào khai vị trí. Dùng ở cột Vị trí (cắt +K) và tab Tổng quan (đủ).
  viTris: string[];
  // Hạn sử dụng: hạn SỚM NHẤT (gần hết hạn nhất) của các lô CÒN tồn + số hạn KHÁC (cột "+N").
  // null = không lô nào còn tồn có hạn.
  hsdSoonest: string | null;
  hsdOthers: number;
  // Mức tồn 5 màu so với ngưỡng đã khai. null = chưa khai ngưỡng cho mã này ở kho này.
  level: StockLevel | null;
}

type TonTab = "ton" | "nhap" | "xuat" | "dc";

/** Mức tồn 4 mức — MIRROR backend `stock_level` (bỏ "sắp hết/cận tồn"). Chưa khai ngưỡng
 *  → null (không bịa cảnh báo). Màn tồn chỉ có hàng còn tồn nên "het" gần như không xuất hiện. */
function levelOf(onHand: number, th: StockThreshold | undefined): StockLevel | null {
  if (onHand <= 0) return "het";
  if (!th) return null;
  if (onHand <= th.nguong_ton) return "can_mua";
  if (th.nguong_toi_da != null && onHand > th.nguong_toi_da) return "du_ton";
  return "du";
}

function getCategory(g: MaterialGroup): "giay" | "muc" | "hoa_chat" | "khac" {
  const code = (g.code ?? "").toLowerCase();
  const name = (g.name ?? "").toLowerCase();
  const loai = (g.hang_loai ?? "").toLowerCase();
  if (
    loai === "giay" ||
    code.includes("couche") ||
    code.includes("ford") ||
    code.includes("ivory") ||
    code.includes("duplex") ||
    code.includes("kraft") ||
    code.includes("bristol") ||
    name.includes("giấy")
  ) {
    return "giay";
  }
  if (
    loai === "muc" ||
    code.includes("muc") ||
    name.includes("mực") ||
    name.includes("pantone") ||
    name.includes("cmyk")
  ) {
    return "muc";
  }
  if (
    code.includes("mang") ||
    code.includes("keo") ||
    code.includes("phu") ||
    name.includes("màng") ||
    name.includes("keo") ||
    name.includes("hóa chất") ||
    name.includes("bóng") ||
    name.includes("mờ") ||
    name.includes("phủ")
  ) {
    return "hoa_chat";
  }
  return "khac";
}


export function KhoTonKhoPage({
  khoId,
  ten,
  ma,
  token,
  navigate,
  openMatHangKey = null,
  khoOptions = [],
}: {
  khoId: number;
  ten: string;
  ma?: string;
  token: string;
  navigate: NavigateFn;
  /** Deep-link tem QR: mở thẳng drawer lô + vị trí của vật tư này khi tồn đã tải xong. */
  openMatHangKey?: string | null;
  /** Mọi kho đã khai báo — để drawer chọn KHO ĐÍCH khi điều chuyển (loại kho hiện tại). */
  khoOptions?: { id: number; ma: string; ten: string }[];
}) {
  const can = useCan();
  const canViewCost = can("kho", "view_cost");
  const canViewStock = can("kho", "view_stock");
  const canCreate = can("kho", "create");
  // ĐÃ GỘP quyền: ghi sổ + hủy dùng CHUNG quyền lập phiếu (create) — không còn 'post' riêng.
  const canPost = canCreate;
  const canSetThreshold = can("kho", "set_threshold");

  const [tab, setTab] = useState<TonTab>("ton");
  const [lots, setLots] = useState<StockLot[]>([]);
  // Khoá `"giay:12"` — cặp (hang_loai, hang_id) dẹp thành chuỗi để dùng làm key Record/JSX.
  const [thresholds, setThresholds] = useState<Record<string, StockThreshold>>({});
  const [vouchers, setVouchers] = useState<StockVoucher[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingV, setLoadingV] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  // Vật tư đang mở popup lịch sử Nhập/Xuất (thay cho bung inline).
  const [openMaterial, setOpenMaterial] = useState<MaterialGroup | null>(null);
  // Mã đã tick để tạo Yêu cầu mua hàng (chỉ tab Tồn kho).
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [voucherFilter, setVoucherFilter] = useState<"all" | StockVoucherStatus>("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);
  const [openVoucher, setOpenVoucher] = useState<number | null>(null);
  const [openRequest, setOpenRequest] = useState<number | null>(null);
  // Điều chuyển HÀNG LOẠT: mở popup cho các mã đã tick → gộp vào 1 yêu cầu điều chuyển.
  const [dcBulkOpen, setDcBulkOpen] = useState(false);
  // Hover tiêu đề cột → hiện tên cột đầy đủ (kể cả khi bị cắt). Bảng Tồn + bảng Phiếu (mỗi bảng 1 ref).
  const tonTableRef = useHeaderTitles();
  const phieuTableRef = useHeaderTitles();
  // Popup đặt ngưỡng cho MỘT mã — mở khi bấm ô Min/Max hoặc badge Trạng thái (cần set_threshold).
  const [nguongFor, setNguongFor] = useState<MaterialGroup | null>(null);
  // Bộ lọc tab Tồn kho (client-side): khoảng ngày nhập (khớp bất kỳ lô nào) + khoảng tồn.
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [tonFrom, setTonFrom] = useState("");
  const [tonTo, setTonTo] = useState("");
  const [gtFrom, setGtFrom] = useState(""); // Giá trị tồn (g.value)
  const [gtTo, setGtTo] = useState("");
  // Bộ lọc tab Phiếu Nhập/Xuất (RIÊNG — khác ngữ nghĩa tab tồn): khoảng NGÀY PHIẾU + khoảng GIÁ VỐN.
  const [vDateFrom, setVDateFrom] = useState("");
  const [vDateTo, setVDateTo] = useState("");
  const [vValFrom, setVValFrom] = useState("");
  const [vValTo, setVValTo] = useState("");

  // Bộ lọc Phân loại & Trạng thái Tồn kho Redesign
  const [categoryFilter, setCategoryFilter] = useState<"all" | "giay" | "muc" | "hoa_chat" | "khac">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "can_mua" | "du" | "du_ton" | "het" | "chuakhai" | "sap_het_han">("all");


  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      // con_hang: false → lấy CẢ lô đã xuất hết → vật tư tồn 0 VẪN nằm trong danh sách (đèn "Hết"),
      // không rớt khỏi kho. Số đợt/vị trí/ngày tính theo lô còn (sl_con_lai>0) ở bước gộp bên dưới.
      api.kho.phieu.danhSachLo(token, { kho_id: khoId, con_hang: false }),
      // Ngưỡng tồn để so tồn → đèn cảnh báo. Lỗi/thiếu quyền set_threshold vẫn xem được tồn.
      api.kho.nguongTon.list(token).catch(() => [] as StockThreshold[]),
    ])
      .then(([r, ths]) => {
        setLots(r);
        const map: Record<string, StockThreshold> = {};
        for (const t of ths) if (t.kho_id === khoId) map[`${t.hang_loai}:${t.hang_id}`] = t;
        setThresholds(map);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được tồn kho."))
      .finally(() => setLoading(false));
  }, [token, khoId]);


  const loadVouchers = useCallback(() => {
    setLoadingV(true);
    api.kho.phieu
      .list(token, { kho_id: khoId, size: 200 })
      .then((r) => {
        setVouchers(r.items);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được phiếu kho."))
      .finally(() => setLoadingV(false));
  }, [token, khoId]);

  useEffect(() => {
    load();
    loadVouchers();
  }, [load, loadVouchers]);

  useEffect(() => {
    setPage(1);
  }, [
    tab,
    q,
    categoryFilter,
    statusFilter,
    voucherFilter,
    dateFrom,
    dateTo,
    tonFrom,
    tonTo,
    vDateFrom,
    vDateTo,
    vValFrom,
    vValTo,
    pageSize,
  ]);

  // Đổi tab → XÓA sạch mọi bộ lọc (khỏi lẫn bộ lọc giữa 2 nhóm tab). Effect RIÊNG chỉ theo [tab].
  useEffect(() => {
    setCategoryFilter("all");
    setStatusFilter("all");
    setDateFrom("");
    setDateTo("");
    setTonFrom("");
    setTonTo("");
    setGtFrom("");
    setGtTo("");
    setVDateFrom("");
    setVDateTo("");
    setVValFrom("");
    setVValTo("");
  }, [tab]);


  const groups = useMemo<MaterialGroup[]>(() => {
    const m = new Map<string, MaterialGroup>();
    for (const lot of lots) {
      const key = `${lot.hang_loai}:${lot.hang_id}`;
      let g = m.get(key);
      if (!g) {
        g = {
          hang_loai: lot.hang_loai,
          hang_id: lot.hang_id,
          key,
          code: lot.hang_ma,
          name: lot.hang_ten,
          dvt: lot.dvt_ten ?? lot.dvt,
          dvtCode: lot.dvt,
          anh: lot.hang_anh,
          total: 0,
          value: 0,
          lots: [],
          viTris: [],
          hsdSoonest: null,
          hsdOthers: 0,
          level: null,
        };
        m.set(key, g);
      }
      // TỒN KHẢ DỤNG = chỉ lô `available` (khớp backend `on_hand`/`LOT_ISSUABLE`). Lô chờ KCS
      // (`qc_wait`) / giữ chỗ (`hold`) / lỗi (`defect`) KHÔNG tính vào "khả dụng" — trước đây cộng
      // bừa nên list lệch drawer (vd 300,25 list vs 285,25 drawer). Vẫn giữ MỌI lô trong `g.lots`
      // để hiển thị vị trí / HSD / lịch sử.
      if (lot.trang_thai === "available") {
        g.total += lot.sl_con_lai;
        g.value += lot.sl_con_lai * (lot.don_gia_nhap ?? 0);
      }
      g.lots.push(lot);
    }
    const arr = [...m.values()];
    for (const g of arr) {
      // g.total/g.value đã cộng ĐÚNG (lô hết cộng 0). Chỉ giữ lô CÒN TỒN cho phần hiển thị
      // (số đợt nhập · vị trí · ngày). Vật tư xuất hết → nhóm vẫn tồn tại (đã tạo từ lô hết) với
      // tồn 0 + đèn "Hết"; nhưng lô hết KHÔNG đếm vào số đợt / vị trí.
      g.lots = g.lots.filter((l) => l.sl_con_lai > 0);
      // Lô trong mỗi nhóm: nhập trước lên trước (FIFO), để đọc lịch sử nhập tự nhiên.
      g.lots.sort((a, b) => a.ngay_nhap.localeCompare(b.ngay_nhap));
      // Vị trí: dùng BẢN SAO sort GIẢM DẦN (nhập mới trước) để KHÔNG phá FIFO ở trên, rồi
      // distinct giữ thứ tự xuất hiện đầu — vị trí của lô mới nhất lên đầu danh sách.
      const seen = new Set<string>();
      const viTris: string[] = [];
      for (const lot of [...g.lots].sort((a, b) => b.ngay_nhap.localeCompare(a.ngay_nhap))) {
        const v = (lot.vi_tri ?? "").trim();
        if (v && !seen.has(v)) {
          seen.add(v);
          viTris.push(v);
        }
      }
      g.viTris = viTris;
      // Hạn sử dụng: distinct các hạn của lô CÒN tồn, sắp TĂNG dần → hạn sớm nhất lên đầu (FEFO).
      const hsds = [...new Set(g.lots.map((l) => l.hsd).filter((h): h is string => !!h))].sort();
      g.hsdSoonest = hsds[0] ?? null;
      g.hsdOthers = Math.max(0, hsds.length - 1);
      g.level = levelOf(g.total, thresholds[g.key]);
    }
    return arr.sort((a, b) => (a.name ?? "").localeCompare(b.name ?? "", "vi"));
  }, [lots, thresholds]);

  // Deep-link tem QR: khi có khoá mặt hàng (`"giay:12"`) + tồn đã tải → bung drawer đúng mặt
  // hàng (1 lần cho mỗi khoá, ref chặn mở lại sau khi người dùng đóng).
  const deepLinkedId = useRef<string | null>(null);
  useEffect(() => {
    if (!openMatHangKey || deepLinkedId.current === openMatHangKey) return;
    const g = groups.find((x) => x.key === openMatHangKey);
    if (!g) return;
    deepLinkedId.current = openMatHangKey;
    setOpenMaterial(g);
  }, [openMatHangKey, groups]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    const tf = tonFrom.trim() === "" ? null : Number(tonFrom);
    const tt = tonTo.trim() === "" ? null : Number(tonTo);

    const targetDate = new Date();
    targetDate.setDate(targetDate.getDate() + 30);
    const targetISO = targetDate.toISOString().slice(0, 10);

    return groups.filter((g) => {
      if (
        s &&
        !((g.name ?? "").toLowerCase().includes(s) || (g.code ?? "").toLowerCase().includes(s))
      )
        return false;

      // Category Filter
      if (categoryFilter !== "all") {
        const cat = getCategory(g);
        if (cat !== categoryFilter) return false;
      }

      // Status Filter
      if (statusFilter === "can_mua" && g.level !== "can_mua") return false;
      if (statusFilter === "du" && g.level !== "du") return false;
      if (statusFilter === "du_ton" && g.level !== "du_ton") return false;
      if (statusFilter === "chuakhai" && g.level !== null) return false;
      if (statusFilter === "het" && g.total > 0) return false;
      if (statusFilter === "sap_het_han") {
        const isExpiring = g.lots.some((l) => l.hsd && l.hsd <= targetISO);
        if (!isExpiring) return false;
      }

      // Ngày nhập: hiện nếu CÓ ≥1 lô có ngay_nhap rơi trong [dateFrom, dateTo] (so ISO yyyy-mm-dd).
      if (dateFrom || dateTo) {
        const hit = g.lots.some((lot) => {
          const d = lot.ngay_nhap.slice(0, 10);
          if (dateFrom && d < dateFrom) return false;
          if (dateTo && d > dateTo) return false;
          return true;
        });
        if (!hit) return false;
      }
      // Khoảng tồn khả dụng.
      if (tf != null && !Number.isNaN(tf) && g.total < tf) return false;
      if (tt != null && !Number.isNaN(tt) && g.total > tt) return false;
      // Khoảng GIÁ TRỊ TỒN (g.value).
      if (!inNumRange(g.value, { from: gtFrom, to: gtTo })) return false;
      return true;
    });
  }, [groups, q, categoryFilter, statusFilter, dateFrom, dateTo, tonFrom, tonTo, gtFrom, gtTo]);


  const shownVouchers = useMemo(() => {
    const s = q.trim().toLowerCase();
    // Tab quyết định nhóm phiếu: Nhập / Xuất (KHÔNG lẫn điều chuyển) · Điều chuyển (cả 2 vế của kho
    // này — xuất đi + nhập về). Tab 'ton' không render list này.
    const vf = vValFrom.trim() === "" ? null : Number(vValFrom);
    const vt = vValTo.trim() === "" ? null : Number(vValTo);
    return vouchers
      .filter((v) =>
        tab === "dc"
          ? v.dieu_chuyen
          : v.loai === (tab === "xuat" ? "XUAT" : "NHAP") && !v.dieu_chuyen,
      )
      .filter((v) => voucherFilter === "all" || v.trang_thai === voucherFilter)
      .filter(
        (v) =>
          !s ||
          v.ma.toLowerCase().includes(s) ||
          (v.request_ma ?? "").toLowerCase().includes(s) ||
          // Tìm cả theo TÊN / MÃ vật tư đi trong phiếu (khớp bất kỳ dòng nào).
          v.lines.some(
            (l) =>
              (l.hang_ten ?? "").toLowerCase().includes(s) ||
              (l.hang_ma ?? "").toLowerCase().includes(s),
          ),
      )
      // Khoảng NGÀY PHIẾU (v.ngay) — so ISO yyyy-mm-dd bằng chuỗi (như filter ngày tab tồn).
      .filter((v) => {
        if (!vDateFrom && !vDateTo) return true;
        const d = v.ngay.slice(0, 10);
        if (vDateFrom && d < vDateFrom) return false;
        if (vDateTo && d > vDateTo) return false;
        return true;
      })
      // Khoảng GIÁ VỐN phiếu (v.gia_von) — chỉ khi xem được giá; phiếu chưa có giá vốn (null) bị
      // loại khi có đặt cận (không có giá để so).
      .filter((v) => {
        if (vf == null && vt == null) return true;
        if (v.gia_von == null) return false;
        if (vf != null && !Number.isNaN(vf) && v.gia_von < vf) return false;
        if (vt != null && !Number.isNaN(vt) && v.gia_von > vt) return false;
        return true;
      });
  }, [vouchers, tab, voucherFilter, q, vDateFrom, vDateTo, vValFrom, vValTo]);

  function toggleSel(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const clearFilters = useCallback(() => {
    setQ("");
    setCategoryFilter("all");
    setStatusFilter("all");
    setDateFrom("");
    setDateTo("");
    setTonFrom("");
    setTonTo("");
    setGtFrom("");
    setGtTo("");
    setVDateFrom("");
    setVDateTo("");
    setVValFrom("");
    setVValTo("");
  }, []);


  function createPurchaseFromSelected() {
    const chosen = groups.filter((g) => selected.has(g.key));
    if (chosen.length === 0) return;
    navigate("yeu-cau-mua-hang", {
      purchaseSeedLines: chosen.map((g) => {
        const th = thresholds[g.key];
        const target = th?.nguong_toi_da ?? th?.nguong_ton ?? 0;
        return {
          hang_loai: g.hang_loai,
          hang_id: g.hang_id,
          item_name: g.name ?? g.code ?? "",
          unit: g.dvtCode ?? "",
          quantity: Math.max(0, target - g.total),
          note: "",
        };
      }),
      purchaseSeedPurpose: `Bổ sung tồn kho ${ten}`,
    });
  }

  const voucherCols = canViewCost ? 6 : 5;

  // Cột tab Tồn kho: [checkbox nếu canCreate] + Vật tư + Vị trí + Hạn sử dụng + Tồn khả dụng + Ngưỡng & Trạng Thái + Ngày nhập mới nhất [+ Giá trị tồn nếu view_cost]
  const tonCols = (canCreate ? 1 : 0) + 6 + (canViewCost ? 1 : 0);

  // Phân trang (dùng chung cho cả 2 tab; số tổng theo tab đang xem).
  const pageTotal = tab === "ton" ? filtered.length : shownVouchers.length;
  const maxPage = Math.max(1, Math.ceil(pageTotal / pageSize));
  const pagedGroups = filtered.slice((page - 1) * pageSize, page * pageSize);
  const pagedVouchers = shownVouchers.slice((page - 1) * pageSize, page * pageSize);

  return (
    <main className="rc kho-list">
      {/* Header Redesign với Quick Action Buttons */}
      <header className="rc__head">
        <div className="rc__headrow" style={{ justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <h1 className="rc__title">{ten}</h1>
            <span className="rc__count">
              {tab === "ton"
                ? `${groups.length} vật tư đang tồn`
                : `${shownVouchers.length} phiếu`}
              {ma ? ` · ${ma}` : ""}
            </span>
          </div>
        </div>
        <p className="rc__sub">
          {tab === "ton"
            ? "Tồn khả dụng theo từng vật tư — bấm một dòng để xem chi tiết các lô & lịch sử."
            : tab === "nhap"
              ? "Danh sách phiếu NHẬP kho đã lập."
              : tab === "xuat"
                ? "Danh sách phiếu XUẤT kho đã lập."
                : "Danh sách phiếu ĐIỀU CHUYỂN kho (chuyển đi / nhận về)."}
        </p>
      </header>

      {/* Unified Single-Row Toolbar (Gộp Tabs + Search + Select Filters) */}
      <div className="rc__toolbar" style={{ marginTop: 0, marginBottom: 16, gap: 12 }}>
        <div className="kho-shell__fns" style={{ margin: 0 }}>
          {(
            [
              ["ton", `Tồn kho (${groups.length})`],
              ["nhap", `Phiếu nhập (${vouchers.filter((v) => v.loai === "NHAP" && !v.dieu_chuyen).length})`],
              ["xuat", `Phiếu xuất (${vouchers.filter((v) => v.loai === "XUAT" && !v.dieu_chuyen).length})`],
              ["dc", `Điều chuyển (${vouchers.filter((v) => v.dieu_chuyen).length})`],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`kho-shell__fn${tab === id ? " is-active" : ""}`}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="rc__search-wrapper" style={{ width: 220 }}>
          <Search className="rc__search-icon" style={{ width: 15, height: 15 }} />
          <input
            className="rc__search"
            placeholder={
              tab === "ton"
                ? "Tìm mã, tên vật tư…"
                : "Tìm số phiếu, mã yêu cầu…"
            }
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>

        {tab === "ton" ? (
          <>
            <div className="kho-picker" style={{ width: 145 }}>
              <Select
                options={[
                  { value: "all", label: "Mọi chủng loại" },
                  { value: "giay", label: "Giấy in" },
                  { value: "muc", label: "Mực in" },
                  { value: "hoa_chat", label: "Hóa chất / Phủ" },
                  { value: "khac", label: "Vật tư phụ" },
                ]}
                value={categoryFilter}
                onChange={(v) => v != null && setCategoryFilter(v as any)}
                ariaLabel="Lọc chủng loại"
              />
            </div>

            <div className="kho-picker" style={{ width: 155 }}>
              <Select
                options={[
                  { value: "all", label: "Mọi trạng thái" },
                  { value: "can_mua", label: "Cần mua" },
                  { value: "du", label: "Đủ" },
                  { value: "du_ton", label: "Dư" },
                  { value: "chuakhai", label: "Chưa khai" },
                  { value: "sap_het_han", label: "Sắp hết hạn" },
                ]}
                value={statusFilter}
                onChange={(v) => v != null && setStatusFilter(v as any)}
                ariaLabel="Lọc trạng thái"
              />
            </div>
          </>
        ) : (
          <div className="kho-picker" style={{ width: 155 }}>
            <Select
              options={[
                { value: "all", label: "Mọi trạng thái", hint: String(vouchers.length) },
                {
                  value: "draft",
                  label: "Chờ ghi sổ",
                  hint: String(vouchers.filter((v) => v.trang_thai === "draft").length),
                },
                {
                  value: "posted",
                  label: "Đã ghi sổ",
                  hint: String(vouchers.filter((v) => v.trang_thai === "posted").length),
                },
                {
                  value: "cancelled",
                  label: "Đã hủy",
                  hint: String(vouchers.filter((v) => v.trang_thai === "cancelled").length),
                },
              ]}
              value={voucherFilter}
              onChange={(v) => v != null && setVoucherFilter(v as "all" | StockVoucherStatus)}
              ariaLabel="Lọc trạng thái phiếu"
            />
          </div>
        )}

        <div className="rc__spacer" />
      </div>


      {error && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          <span>{error}</span>
          <button
            type="button"
            className="btn btn--ghost"
            style={{ padding: "4px 12px", fontSize: "12px" }}
            onClick={tab === "ton" ? load : loadVouchers}
          >
            Tải lại
          </button>
        </div>
      )}

      {/* Bảng Dữ Liệu Tồn Kho Căn Khớp 100% 8 Cột Chuẩn */}
      <div className="rc__tablewrap kho-tablewrap">
        {tab === "ton" ? (
          <table ref={tonTableRef} className="rc__table kho-table kho-ton-table">
            <thead>
              <tr>
                {canCreate && (
                  <th style={{ width: 34 }}>
                    <input
                      type="checkbox"
                      aria-label="Chọn tất cả"
                      checked={filtered.length > 0 && filtered.every((g) => selected.has(g.key))}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? new Set(filtered.map((g) => g.key))
                            : new Set(),
                        )
                      }
                    />
                  </th>
                )}
                <th style={{ minWidth: 220 }}>Vật tư</th>
                <th style={{ minWidth: 104 }}>Vị trí</th>
                <th style={{ minWidth: 90 }} title="Hạn SỚM NHẤT của lô còn tồn">
                  Hạn sử dụng
                </th>
                <NumFilterHead
                  className="kho-num"
                  style={{ minWidth: 130 }}
                  label="Tồn khả dụng"
                  from={tonFrom}
                  to={tonTo}
                  onChange={(f, t) => {
                    setTonFrom(f);
                    setTonTo(t);
                  }}
                />
                <th style={{ minWidth: 140 }}>Ngưỡng &amp; Trạng thái</th>
                <DateFilterHead
                  className="kho-num kho-colfil--num"
                  style={{ minWidth: 120 }}
                  label="Ngày nhập mới nhất"
                  from={dateFrom}
                  to={dateTo}
                  onChange={(f, t) => {
                    setDateFrom(f);
                    setDateTo(t);
                  }}
                />
                {canViewCost && (
                  <NumFilterHead
                    className="kho-num"
                    style={{ minWidth: 130 }}
                    label="Giá trị tồn"
                    from={gtFrom}
                    to={gtTo}
                    onChange={(f, t) => {
                      setGtFrom(f);
                      setGtTo(t);
                    }}
                  />
                )}
              </tr>
            </thead>

            <tbody>
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={`sk-${i}`} className="rc-skel__row">
                    {Array.from({ length: tonCols }).map((__, c) => (
                      <td key={c}>
                        <span
                          className="rc-skel"
                          style={{ width: c === (canCreate ? 1 : 0) ? "70%" : "45%" }}
                        />
                      </td>
                    ))}
                  </tr>
                ))
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={tonCols} className="rc__empty-state-td">
                    <div className="rc__empty-state">
                      <BoxIcon />
                      <p className="rc__empty-text">
                        {groups.length === 0
                          ? "Kho này chưa có hàng. Hàng sẽ xuất hiện sau khi ghi sổ phiếu nhập."
                          : "Không có vật tư nào khớp bộ lọc."}
                      </p>
                      {groups.length > 0 && (
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() => {
                            setQ("");
                            clearFilters();
                          }}
                        >
                          Xóa bộ lọc
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                pagedGroups.map((g) => (
                  <MaterialRow
                    key={g.key}
                    g={g}
                    canViewCost={canViewCost}
                    selectable={canCreate}
                    checked={selected.has(g.key)}
                    onToggleSel={() => toggleSel(g.key)}
                    onOpen={() => setOpenMaterial(g)}
                    threshold={thresholds[g.key]}
                    canSetThreshold={canSetThreshold}
                    onSetThreshold={setNguongFor}
                  />
                ))
              )}
              {/* Hàng ĐỆM giữ độ dài (chiều cao) bảng cố định — trang cuối / ít vật tư vẫn trải đủ
                  pageSize dòng, đồng bộ với bảng phiếu & Báo cáo. */}
              {Array.from({
                length: Math.max(
                  0,
                  pageSize - (loading ? 5 : filtered.length === 0 ? 1 : pagedGroups.length),
                ),
              }).map((_, i) => (
                <tr key={`tonfiller-${i}`} className="rc__filler" aria-hidden="true">
                  <td colSpan={tonCols}>&nbsp;</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table ref={phieuTableRef} className="rc__table kho-table">
            <thead>
              <tr>
                <th style={{ width: "14%" }}>Số phiếu</th>
                <th style={{ width: "13%" }}>Theo yêu cầu</th>
                <th style={{ width: "16%" }}>Người lập</th>
                <DateFilterHead style={{ width: "12%" }} label={tab === "xuat" ? "Ngày xuất" : "Ngày nhập"} from={vDateFrom} to={vDateTo} onChange={(f, t) => { setVDateFrom(f); setVDateTo(t); }} />
                <th className="kho-num" style={{ width: "12%" }}>
                  Mặt hàng / Tổng SL
                </th>
                {canViewCost && (
                  <NumFilterHead className="kho-num" style={{ width: "14%" }} label="Giá vốn" from={vValFrom} to={vValTo} onChange={(f, t) => { setVValFrom(f); setVValTo(t); }} />
                )}
                <th style={{ width: "12%" }}>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {loadingV ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={`skv-${i}`} className="rc-skel__row">
                    {Array.from({ length: voucherCols + 1 }).map((__, c) => (
                      <td key={c}>
                        <span className="rc-skel" style={{ width: c === 0 ? "60%" : "45%" }} />
                      </td>
                    ))}
                  </tr>
                ))
              ) : shownVouchers.length === 0 ? (
                <tr>
                  <td colSpan={voucherCols + 1} className="rc__empty-state-td">
                    <div className="rc__empty-state">
                      <BoxIcon />
                      <p className="rc__empty-text">
                        {vouchers.length === 0
                          ? "Chưa có phiếu kho nào ở kho này. Phiếu được lập từ một yêu cầu đã duyệt."
                          : "Không có phiếu nào khớp bộ lọc."}
                      </p>
                      {vouchers.length > 0 && (
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() => {
                            setQ("");
                            setVoucherFilter("all");
                            clearFilters();
                          }}
                        >
                          Xóa bộ lọc
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                pagedVouchers.map((v) => {
                  const sumQty = v.lines.reduce((s, l) => s + l.so_luong, 0);
                  return (
                    <tr key={v.id} className="rc__row" onClick={() => setOpenVoucher(v.id)}>
                      <td className="rc__nowrap">
                        <span className="rc__code-badge">{v.ma}</span>
                        {tab === "dc" && (
                          <span style={{ marginLeft: 6, fontSize: 11, color: "var(--ash)" }}>
                            {v.loai === "XUAT" ? "⇄ chuyển đi" : "⇄ nhận về"}
                          </span>
                        )}
                      </td>
                      <td className="rc__nowrap kho-lines__code">
                        {v.request_ma ? (
                          <CodeLink
                            code={v.request_ma}
                            onOpen={() => setOpenRequest(v.request_id)}
                          />
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        <div className="rc__name">{v.nguoi_lap_ten ?? "—"}</div>
                      </td>
                      <td className="rc__nowrap">{fmtDateISO(v.ngay)}</td>
                      <td className="kho-num">
                        {v.lines.length} / {fmtQty(sumQty)}
                      </td>
                      {canViewCost && (
                        <td className="kho-num">{v.gia_von != null ? money(v.gia_von) : ""}</td>
                      )}
                      <td>
                        <VoucherStatusBadge status={v.trang_thai} />
                      </td>
                    </tr>
                  );
                })
              )}
              {/* Hàng ĐỆM giữ ĐỘ DÀI (chiều cao) bảng cố định giữa các tab — ít dữ liệu (vd 1-2 phiếu)
                  bảng vẫn trải đủ pageSize dòng như bảng Báo cáo/Khóa sổ, không co ngắn tủn. */}
              {Array.from({
                length: Math.max(
                  0,
                  pageSize - (loadingV ? 5 : shownVouchers.length === 0 ? 1 : pagedVouchers.length),
                ),
              }).map((_, i) => (
                <tr key={`vfiller-${i}`} className="rc__filler" aria-hidden="true">
                  <td colSpan={voucherCols + 1}>&nbsp;</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {!loading && pageTotal > 0 && (
        <div className="kho-pager">
          <PageSizeSelect value={pageSize} onChange={setPageSize} />
          <div className="rc__spacer" />

          <button
            type="button"
            className="btn btn--ghost"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Trước
          </button>
          <span className="kho-pager__page">
            Trang {page} / {maxPage}
          </span>
          <button
            type="button"
            className="btn btn--ghost"
            disabled={page >= maxPage}
            onClick={() => setPage((p) => Math.min(maxPage, p + 1))}
          >
            Sau
          </button>
        </div>
      )}

      {openMaterial && (
        // Popup lịch sử Nhập/Xuất của 1 vật tư. Bấm mã lô / số phiếu bên trong → mở VoucherDrawer
        // (render SAU khối này nên chồng lên trên). Vẫn giữ "bấm mã lô ra phiếu".
        <MaterialHistoryDrawer
          key={`mat-${openMaterial.key}`}
          token={token}
          khoId={khoId}
          khoTen={ten}
          material={openMaterial}
          threshold={thresholds[openMaterial.key]}
          canViewCost={canViewCost}
          // Kho ĐÍCH khi điều chuyển = mọi kho khác kho hiện tại.
          khoDich={khoOptions.filter((w) => w.id !== khoId)}
          onOpenVoucher={setOpenVoucher}
          // Điều chuyển xong TRỪ TỒN NGUỒN NGAY → nạp lại tồn + phiếu để bảng phản ánh tức thì.
          onDieuChuyenDone={() => {
            load();
            loadVouchers();
          }}
          onClose={() => setOpenMaterial(null)}
          onAnhChanged={(hl, hid, url) =>
            setLots((prev) =>
              prev.map((l) =>
                l.hang_loai === hl && l.hang_id === hid ? { ...l, hang_anh: url } : l,
              ),
            )
          }
        />
      )}

      {openVoucher != null && (
        <VoucherDrawer
          key={`v-${openVoucher}`}
          token={token}
          voucherId={openVoucher}
          canCreate={canCreate}
          canPost={canPost}
          canViewCost={canViewCost}
          onClose={() => setOpenVoucher(null)}
          onChanged={() => {
            loadVouchers();
            load();
          }}
        />
      )}

      {openRequest != null && (
        // Chỉ ĐỌC: mở yêu cầu gốc từ mã "Theo yêu cầu". Lập phiếu vẫn làm ở Hộp yêu cầu, nên
        // canCreate=false (ẩn nút Lập phiếu / Tiếp nhận / Chuẩn bị).
        <InboxRequestDrawer
          key={`req-${openRequest}`}
          token={token}
          khoId={khoId}
          requestId={openRequest}
          canCreate={false}
          canViewStock={canViewStock}
          onClose={() => setOpenRequest(null)}
          onCreateVoucher={() => {}}
        />
      )}

      {nguongFor && (
        // Popup đặt ngưỡng cho 1 mã (thay drawer chọn-mã-từ-dropdown cũ). Lưu xong cập nhật
        // thresholds tại chỗ → cột Min/Max + Trạng thái + gauge Tổng quan đổi ngay.
        <SetThresholdDialog
          key={`ng-${nguongFor.key}`}
          token={token}
          khoId={khoId}
          material={nguongFor}
          current={thresholds[nguongFor.key]}
          onSaved={(t) =>
            setThresholds((prev) => ({ ...prev, [nguongFor.key]: t }))
          }
          onClose={() => setNguongFor(null)}
        />
      )}

      {/* macOS Floating Command Dock khi tick chọn mã */}
      {tab === "ton" && canCreate && selected.size > 0 && (
        <div className="kho-dock-overlay">
          <div className="kho-dock">
            <div className="kho-dock__badge">
              <span className="kho-dock__led" />
              Đã chọn {selected.size} mặt hàng
            </div>

            <button
              type="button"
              className="kho-dock__btn kho-dock__btn--primary"
              onClick={createPurchaseFromSelected}
            >
              <ShoppingCart style={{ width: 15, height: 15 }} />
              Tạo yêu cầu mua
            </button>

            {khoOptions.filter((w) => w.id !== khoId).length > 0 && (
              <button
                type="button"
                className="kho-dock__btn kho-dock__btn--secondary"
                onClick={() => setDcBulkOpen(true)}
              >
                <ArrowLeftRight style={{ width: 15, height: 15 }} />
                Điều chuyển
              </button>
            )}

            {selected.size === 1 && (
              <button
                type="button"
                className="kho-dock__btn kho-dock__btn--secondary"
                onClick={() => {
                  const selKey = Array.from(selected)[0];
                  const g = groups.find((item) => item.key === selKey);
                  if (g) {
                    printMaterialQr(token, khoId, g.hang_loai, g.hang_id, g.code, g.name);
                  }
                }}
              >
                <QrCode style={{ width: 15, height: 15 }} />
                In tem QR
              </button>
            )}

            <button
              type="button"
              className="kho-dock__btn kho-dock__btn--ghost"
              onClick={() => setSelected(new Set())}
            >
              ✕ Bỏ chọn
            </button>
          </div>
        </div>
      )}

      {dcBulkOpen && (
        <DieuChuyenDialog
          token={token}
          khoNguonId={khoId}
          khoNguonTen={ten}
          khoDich={khoOptions.filter((w) => w.id !== khoId)}
          items={groups
            .filter((g) => selected.has(g.key))
            .map((g) => ({
              hang_loai: g.hang_loai,
              hang_id: g.hang_id,
              ten: g.name ?? g.code ?? "vật tư",
              dvt: g.dvt ?? "",
              tonKhaDung: g.total,
            }))}
          onDone={() => {
            setDcBulkOpen(false);
            setSelected(new Set());
            load();
            loadVouchers();
          }}
          onCancel={() => setDcBulkOpen(false)}
        />
      )}
    </main>
  );
}


// In tem QR cho MỘT vật tư ở MỘT kho. Mã QR trỏ TRANG TRA KHO CÔNG KHAI qua token đã KÝ
// (`#s=<token>`) — quét KHÔNG cần đăng nhập và KHÔNG dò id tuần tự được (services/qr_token).
// Dùng chung cho nút QR trên từng hàng Tồn kho VÀ nút "In tem" trong drawer → tem giống hệt.
async function printMaterialQr(
  authToken: string,
  khoId: number,
  hangLoai: HangLoai,
  hangId: number,
  code?: string | null,
  name?: string | null,
) {
  // Mở cửa sổ NGAY trong nhịp click (tránh popup-blocker chặn sau await); điền nội dung sau.
  const w = window.open("", "_blank", "width=460,height=600");
  if (!w) return;
  w.document.write(
    `<!doctype html><meta charset="utf-8"><title>Tem QR</title>` +
      `<body style="font-family:system-ui,sans-serif;text-align:center;padding:48px;color:#64748b">Đang tạo tem…</body>`,
  );
  const esc = (s: string) =>
    s.replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]!);
  try {
    // Lấy token đã ký từ server (cần đăng nhập — người in tem luôn đang đăng nhập).
    const { token } = await api.kho.phieu.qrToken(authToken, khoId, hangLoai, hangId);
    const url = `${window.location.origin}/#s=${token}`;
    // border 4 = quiet-zone chuẩn (đủ khoảng trắng để máy quét bắt được, kể cả khi in nhỏ).
    const svg = qrToSvg(url, { border: 4 });
    const c = esc(code ?? "");
    const n = esc(name ?? "");
    w.document.open();
    w.document.write(
      `<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>Tem QR ${c || n}</title>` +
        `<style>*{box-sizing:border-box}body{font-family:'Be Vietnam Pro',system-ui,sans-serif;margin:0;padding:24px;text-align:center;color:#0f172a}` +
        `.card{display:inline-block;border:1px solid #cbd5e1;border-radius:12px;padding:20px 24px}` +
        `.code{font-size:22px;font-weight:800;letter-spacing:.5px}.name{font-size:14px;color:#475569;margin:4px 0 14px;max-width:280px}` +
        `svg{width:280px;height:280px}.hint{font-size:11px;color:#94a3b8;margin-top:10px}</style></head>` +
        `<body><div class="card"><div class="code">${c}</div><div class="name">${n}</div>${svg}` +
        `<div class="hint">Quét để xem lô &amp; vị trí trong kho</div></div>` +
        `<script>window.onload=function(){window.focus();window.print()}</script></body></html>`,
    );
    w.document.close();
  } catch {
    w.document.open();
    w.document.write(
      `<!doctype html><meta charset="utf-8"><body style="font-family:system-ui,sans-serif;text-align:center;padding:48px;color:#c5400a">` +
        `Không tạo được tem QR. Đóng cửa sổ này và thử lại.</body>`,
    );
    w.document.close();
  }
}

function MaterialRow({
  g,
  canViewCost,
  selectable,
  checked,
  onToggleSel,
  onOpen,
  threshold,
  canSetThreshold,
  onSetThreshold,
}: {
  g: MaterialGroup;
  canViewCost: boolean;
  selectable: boolean;
  checked: boolean;
  onToggleSel: () => void;
  onOpen: () => void;
  threshold: StockThreshold | undefined;
  canSetThreshold: boolean;
  onSetThreshold: (g: MaterialGroup) => void;
}) {
  const cat = getCategory(g);
  const newest = g.lots.length ? g.lots[g.lots.length - 1].ngay_nhap : null;
  const viMore = g.viTris.length - 2;

  const setThProps = canSetThreshold
    ? {
        className: "kho-ton__setth",
        title: "Đặt ngưỡng",
        onClick: (e: ReactMouseEvent) => {
          e.stopPropagation();
          onSetThreshold(g);
        },
      }
    : null;

  return (
    <tr className="rc__row kho-ton__grow" onClick={onOpen}>
      {selectable && (
        <td onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            aria-label={`Chọn ${g.name ?? g.code ?? ""}`}
            checked={checked}
            onChange={onToggleSel}
          />
        </td>
      )}
      <td>
        <div className="kho-lineimg" style={{ alignItems: "center" }}>
          {g.anh ? (
            <img className="kho-ton__thumb" src={assetUrl(g.anh) ?? undefined} alt="" loading="lazy" />
          ) : (
            // Nền neutral (slate) đồng nhất — CHỦNG LOẠI đã phân biệt bằng icon, không cần pastel.
            <span className="kho-ton__thumb kho-ton__thumb--ph" aria-hidden="true">
              {cat === "giay" ? (
                <Layers style={{ width: 16, height: 16 }} />
              ) : cat === "muc" ? (
                <Droplets style={{ width: 16, height: 16 }} />
              ) : cat === "hoa_chat" ? (
                <FlaskConical style={{ width: 16, height: 16 }} />
              ) : (
                <Box style={{ width: 16, height: 16 }} />
              )}
            </span>
          )}
          <div className="kho-lineimg__txt">
            <div className="rc__name kho-ton__name" title={g.name ?? undefined}>
              {g.name ?? "—"}
            </div>
            {g.code && <div className="rc__muted kho-lines__code">{g.code}</div>}
          </div>
        </div>
      </td>

      {/* Vị trí — tối đa 2 chip trên MỘT hàng + "+N" (nhiều hơn 2 thì gộp phần dư). */}
      <td>
        {g.viTris.length === 0 ? (
          <span className="rc__muted">—</span>
        ) : (
          <div className="kho-loc-cell" title={g.viTris.join(", ")}>
            {g.viTris.slice(0, 2).map((v) => (
              <span key={v} className="kho-badge-loc" title={v}>
                {v}
              </span>
            ))}
            {viMore > 0 ? <span className="kho-loc-cell__more">+{viMore}</span> : null}
          </div>
        )}
      </td>

      {/* Hạn sử dụng — CẢNH BÁO đỏ khi có lô CÒN TỒN đã quá hạn (hsdSoonest tính từ lô sl_con_lai>0). */}
      <td
        title={
          g.hsdSoonest
            ? `${g.hsdSoonest < todayISO() ? "CÓ LÔ CÒN TỒN ĐÃ QUÁ HẠN — " : ""}Hạn sớm nhất: ${fmtDateISO(g.hsdSoonest)}${
                g.hsdOthers ? ` · +${g.hsdOthers} hạn khác` : ""
              }`
            : undefined
        }
      >
        {g.hsdSoonest == null ? (
          <span className="rc__muted">—</span>
        ) : g.hsdSoonest < todayISO() ? (
          <span className="kho-lines__hsd kho-lines__hsd--qua">
            {fmtDateISO(g.hsdSoonest)} · Quá hạn
            {g.hsdOthers > 0 ? <span className="kho-ton__vtmore"> +{g.hsdOthers}</span> : null}
          </span>
        ) : (
          <span className="kho-ton__vitri">
            {fmtDateISO(g.hsdSoonest)}
            {g.hsdOthers > 0 ? <span className="kho-ton__vtmore"> +{g.hsdOthers}</span> : null}
          </span>
        )}
      </td>

      {/* Tồn khả dụng */}
      <td className="kho-num kho-ton__total">
        <span>{fmtQty(g.total)}</span>
        {g.dvt ? <span className="kho-ton__dvt"> {g.dvt}</span> : null}
      </td>

      {/* Ngưỡng & Trạng thái — chip token gọn (align-items:flex-start ⇒ KHÔNG dãn tràn cột) +
          Min/Max phụ xám nhạt. */}
      <td {...(setThProps ?? {})}>
        {g.level ? (
          <div className="kho-ton__thstack">
            <StockLevelChip level={g.level} />
            {threshold && (
              <span className="kho-ton__thmm">
                Min {threshold.nguong_ton != null ? fmtQty(threshold.nguong_ton) : "—"} · Max{" "}
                {threshold.nguong_toi_da != null ? fmtQty(threshold.nguong_toi_da) : "—"}
              </span>
            )}
          </div>
        ) : (
          <span className="kho-ton__unset" title="Bấm để khai báo ngưỡng tồn">—</span>
        )}
      </td>

      {/* Ngày nhập mới nhất */}
      <td className="kho-ton__date">
        {newest == null ? <span className="rc__muted">—</span> : fmtDateISO(newest)}
      </td>

      {/* Giá trị tồn */}
      {canViewCost && <td className="kho-num kho-ton__val">{money(Math.round(g.value))}</td>}
    </tr>
  );
}


/** Ô HSD của một lô — dùng chung cho cả tab Nhập và Xuất.
 *
 *  Quá hạn thì tô đỏ + có `title`: cột hạn dùng mà không cảnh báo thì chỉ là thêm một cột chữ,
 *  trong khi đúng thứ thủ kho cần biết là "lô này còn dùng được không". Lô không khai HSD (bản
 *  kẽm, giấy…) vẫn hiện "—" mờ như cũ — phần lớn vật tư in không có hạn. */
function HsdCell({ hsd }: { hsd: string | null | undefined }) {
  if (!hsd) return <td className="kho-lines__code">—</td>;
  const quaHan = hsd < todayISO();
  return (
    <td
      className={quaHan ? "kho-lines__hsd kho-lines__hsd--qua" : "kho-lines__hsd"}
      title={quaHan ? "Đã quá hạn" : undefined}
    >
      {fmtDateISO(hsd)}
    </td>
  );
}

function MaterialHistoryDrawer({
  token,
  khoId,
  khoTen,
  material,
  threshold,
  canViewCost,
  khoDich,
  onOpenVoucher,
  onDieuChuyenDone,
  onClose,
  onAnhChanged,
}: {
  token: string;
  khoId: number;
  khoTen: string;
  material: MaterialGroup;
  threshold: StockThreshold | undefined;
  canViewCost: boolean;
  /** Kho ĐÍCH khả dĩ khi điều chuyển (đã loại kho hiện tại). Rỗng → ẩn nút "Chuyển kho". */
  khoDich: { id: number; ma: string; ten: string }[];
  onOpenVoucher: (voucherId: number) => void;
  /** Điều chuyển thành công → cha nạp lại tồn + phiếu (tồn nguồn đã bị trừ ngay). */
  onDieuChuyenDone: () => void;
  onClose: () => void;
  /** Đổi/gỡ ảnh xong → báo cha cập nhật `hang_anh` mọi lô cùng mặt hàng (mở lại không bị ảnh cũ). */
  onAnhChanged: (hangLoai: HangLoai, hangId: number, url: string | null) => void;
}) {
  useNapTenDonVi(); // nạp nhãn đơn vị (danh mục) để ghi rõ đơn vị ở các bảng lịch sử
  const [data, setData] = useState<StockMaterialHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Ảnh minh hoạ mặt hàng — xem + THÊM/ĐỔI/XÓA ngay tại đây (ngoài đường lập phiếu nhập). Tải lên
  // NGAY khi chọn file (cập nhật danh mục); bấm ảnh để phóng to. Cho ai LẬP PHIẾU KHO (`kho.create`)
  // hoặc sửa DANH MỤC (`dm_giay`/`dm_vat_tu` update) — khớp guard ở backend.
  const can = useCan();
  const canEditAnh =
    can("kho", "create") ||
    can(material.hang_loai === "giay" ? "dm_giay" : "dm_vat_tu", "update");
  // Điều chuyển kho: quyền lập phiếu kho + phải có kho đích. Trừ tồn nguồn NGAY (mở dialog xác nhận).
  const canCreate = can("kho", "create");
  const [dcOpen, setDcOpen] = useState(false);
  const [anh, setAnh] = useState<string | null>(material.anh);
  const [anhBusy, setAnhBusy] = useState(false);
  const [anhErr, setAnhErr] = useState<string | null>(null);
  const [zoom, setZoom] = useState(false);
  useEffect(() => {
    setAnh(material.anh);
    setAnhErr(null);
  }, [material.hang_loai, material.hang_id, material.anh]);
  async function pickAnh(file: File) {
    setAnhBusy(true);
    setAnhErr(null);
    try {
      const r = await api.matHang.uploadAnh(token, material.hang_loai, material.hang_id, file);
      setAnh(r.anh_url);
      onAnhChanged(material.hang_loai, material.hang_id, r.anh_url);
    } catch (e) {
      setAnhErr(e instanceof ApiError ? e.message : "Không tải được ảnh.");
    } finally {
      setAnhBusy(false);
    }
  }
  async function removeAnh() {
    setAnhBusy(true);
    setAnhErr(null);
    try {
      await api.matHang.xoaAnh(token, material.hang_loai, material.hang_id);
      setAnh(null);
      setZoom(false);
      onAnhChanged(material.hang_loai, material.hang_id, null);
    } catch (e) {
      setAnhErr(e instanceof ApiError ? e.message : "Không xóa được ảnh.");
    } finally {
      setAnhBusy(false);
    }
  }
  // Tab MẶC ĐỊNH = "Tổng quan" (đầu tiên) khi mở drawer; giữ nguyên Nhập/Xuất phía sau.
  const [tab, setTab] = useState<"tong_quan" | "lo_ton" | "nhap" | "xuat" | "chuyen">("tong_quan");
  const [page, setPage] = useState(1);
  // Tem QR vật tư: quét ra TRANG TRA KHO CÔNG KHAI (không đăng nhập) qua token đã ký "#s=..".
  const [showQr, setShowQr] = useState(false);
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  // Lấy token ký khi mở panel QR lần đầu (mint cần đăng nhập → dùng chính token phiên).
  useEffect(() => {
    if (!showQr || qrUrl) return;
    let alive = true;
    api.kho.phieu
      .qrToken(token, khoId, material.hang_loai, material.hang_id)
      .then(({ token: t }) => {
        if (alive) setQrUrl(`${window.location.origin}/#s=${t}`);
      })
      .catch(() => {
        /* lỗi mạng/quyền — panel hiện trạng thái đang tạo; nút In tem vẫn tự lấy token khi bấm */
      });
    return () => {
      alive = false;
    };
  }, [showQr, qrUrl, token, khoId, material.hang_loai, material.hang_id]);
  // border 4 = quiet-zone chuẩn (đủ khoảng trắng để máy quét bắt được, kể cả khi in nhỏ).
  const qrSvg = useMemo(() => (qrUrl ? qrToSvg(qrUrl, { border: 4 }) : ""), [qrUrl]);

  // In tem = hàm dùng chung (giống nút QR trên từng hàng Tồn kho). Tự lấy token ký rồi in.
  function printQr() {
    void printMaterialQr(token, khoId, material.hang_loai, material.hang_id, material.code, material.name);
  }

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.kho.phieu
      .lichSuVatTu(token, material.hang_loai, material.hang_id, khoId)
      .then((d) => {
        if (!alive) return;
        setData(d);
        setError(null);
      })
      .catch((e) => {
        if (alive) setError(e instanceof ApiError ? e.message : "Không tải được lịch sử.");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [token, khoId, material.hang_loai, material.hang_id]);

  // NCC bán mặt hàng này + giá đã quy về đơn vị gốc (Đợt 4). Gộp vào ĐÂY chứ không dựng màn
  // so-giá riêng: đây là lúc người ta vừa thấy hàng sắp hết, câu hỏi tiếp theo luôn là "mua của
  // ai" — bắt họ đi sang màn khác rồi tìm lại đúng mặt hàng là thao tác thừa.
  const [soGia, setSoGia] = useState<SoGiaRow[]>([]);
  useEffect(() => {
    let alive = true;
    api.matHang
      .soGia(token, material.hang_loai, material.hang_id)
      .then((d) => {
        if (alive) setSoGia(d.items);
      })
      .catch(() => {
        if (alive) setSoGia([]);
      });
    return () => {
      alive = false;
    };
  }, [token, material.hang_loai, material.hang_id]);

  // Mỗi tab phân trang riêng, 10 dòng/trang; đổi tab → về trang 1.
  useEffect(() => {
    setPage(1);
  }, [tab]);

  const DRAWER_PAGE = 10;
  const nhap = data?.nhap ?? [];
  const xuat = data?.xuat ?? [];
  // Đơn vị GỐC của mã hàng (ram/tờ…) — nhãn cho MỌI số theo đơn vị lô (SL nhập/xuất/chuyển).
  // Cột "SL yêu cầu" thì theo đơn vị NGƯỜI XIN (dvt_yeu_cau, có thể khác) — ghi riêng từng dòng.
  const dvtGoc = tenDonVi(data?.dvt) ?? data?.dvt ?? "";
  const dvtYeuCau = (ma?: string | null) => (ma ? tenDonVi(ma) ?? ma : dvtGoc);
  // Dòng XUẤT chỉ mang `lot_id`; vị trí + HSD nằm ở LÔ. `nhap` đã chứa MỌI lô của mặt hàng (kể cả
  // lô đã hết) nên tra ngay tại chỗ — không phải gọi thêm API chỉ để hiện hai cột.
  const lotById = useMemo(() => new Map(nhap.map((l) => [l.id, l])), [nhap]);
  // TÁCH điều chuyển ra tab riêng: tab Nhập/Xuất chỉ còn NHẬP/XUẤT THƯỜNG; tab "Chuyển kho" gộp cả
  // hai chiều — lô NHẬN VỀ (lô sinh từ phiếu điều chuyển) + dòng CHUYỂN ĐI (dòng xuất điều chuyển).
  const nhapThuong = useMemo(() => nhap.filter((l) => !l.dieu_chuyen), [nhap]);
  const xuatThuong = useMemo(() => xuat.filter((r) => !r.dieu_chuyen), [xuat]);
  const chuyenRows = useMemo(() => {
    const ins = nhap
      .filter((l) => l.dieu_chuyen)
      .map((l) => ({
        key: `in-${l.id}`,
        dir: "in" as const,
        ngay: l.ngay_nhap,
        voucher_id: l.voucher_id,
        voucher_ma: l.voucher_ma ?? l.ma_lo,
        so_luong: l.sl_ban_dau,
        don_gia: l.don_gia_nhap,
        vi_tri: l.vi_tri,
        hsd: l.hsd,
      }));
    const outs = xuat
      .filter((r) => r.dieu_chuyen)
      .map((r, i) => {
        const lot = r.lot_id != null ? lotById.get(r.lot_id) : undefined;
        return {
          key: `out-${r.voucher_id}-${r.lot_id}-${i}`,
          dir: "out" as const,
          ngay: r.ngay,
          voucher_id: r.voucher_id as number | null,
          voucher_ma: r.voucher_ma,
          so_luong: r.so_luong,
          don_gia: r.don_gia,
          vi_tri: lot?.vi_tri ?? null,
          hsd: lot?.hsd ?? null,
        };
      });
    // Mới nhất lên đầu (ngày giảm) — cùng hướng sắp xếp với tab Nhập/Xuất.
    return [...ins, ...outs].sort((a, b) => (a.ngay < b.ngay ? 1 : a.ngay > b.ngay ? -1 : 0));
  }, [nhap, xuat, lotById]);
  // Tab "Lô tồn" = các lô CÒN TỒN (sl_con_lai > 0) — số lô đang thực sự có hàng của mã này tại kho.
  const loTon = useMemo(() => nhap.filter((l) => l.sl_con_lai > 0), [nhap]);
  const nhapPaged = nhapThuong.slice((page - 1) * DRAWER_PAGE, page * DRAWER_PAGE);
  const xuatPaged = xuatThuong.slice((page - 1) * DRAWER_PAGE, page * DRAWER_PAGE);
  const chuyenPaged = chuyenRows.slice((page - 1) * DRAWER_PAGE, page * DRAWER_PAGE);
  const loTonPaged = loTon.slice((page - 1) * DRAWER_PAGE, page * DRAWER_PAGE);

  const cat = getCategory(material);
  const catLabel =
    cat === "giay"
      ? "GIẤY IN"
      : cat === "muc"
      ? "MỰC IN"
      : cat === "hoa_chat"
      ? "HÓA CHẤT"
      : "VẬT TƯ IN";
  // Icon chủng loại — DÙNG LẠI bộ lucide của bảng tồn (Layers/Droplets/FlaskConical/Box) thay cho
  // emoji ở kicker, để cả màn chỉ một bộ icon (không lẫn emoji OS-render).
  const CatIcon =
    cat === "giay" ? Layers : cat === "muc" ? Droplets : cat === "hoa_chat" ? FlaskConical : Box;

  return (
    <>
      <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
        <aside className="rc-drawer rc-drawer--mid rc-drawer--mat-wide" onClick={(e) => e.stopPropagation()}>
          {/* Drawer Header */}
          <header className="rc-drawer__head" style={{ borderBottom: "1px solid var(--rule-soft)", paddingBottom: 16 }}>
            <div>
              <div
                className="rc-drawer__kicker"
                style={{ color: "var(--ash-2)", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 6 }}
              >
                <CatIcon style={{ width: 13, height: 13 }} aria-hidden="true" /> {catLabel}
              </div>
              <h2 className="rc-drawer__title" style={{ fontSize: 22, fontWeight: 700, marginTop: 2 }}>
                {material.name ?? material.code ?? "—"}
              </h2>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {canCreate && khoDich.length > 0 && material.total > 0 && (
                <button
                  type="button"
                  className="kho-action-pill"
                  onClick={() => setDcOpen(true)}
                  title="Điều chuyển mặt hàng này sang kho khác"
                  style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 12px", background: "var(--paper)", border: "1px solid var(--rule)", borderRadius: 6, cursor: "pointer", fontSize: 12.5, fontWeight: 600 }}
                >
                  <ArrowLeftRight style={{ width: 14, height: 14 }} /> Chuyển kho
                </button>
              )}
              <button
                type="button"
                className={`kho-action-pill${showQr ? " is-active" : ""}`}
                onClick={() => setShowQr((v) => !v)}
                aria-pressed={showQr}
                title="Tem QR vật tư — quét ra tồn & vị trí"
                style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 12px", background: showQr ? "var(--rust-soft)" : "var(--paper)", color: showQr ? "var(--rust)" : "var(--ink)", border: "1px solid var(--rule)", borderRadius: 6, cursor: "pointer", fontSize: 12.5, fontWeight: 600 }}
              >
                <QrCode style={{ width: 14, height: 14 }} /> {showQr ? "Ẩn QR" : "Tem QR"}
              </button>
              <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
                ✕
              </button>
            </div>
          </header>

          <div className="rc-drawer__body" style={{ padding: 20 }}>
            {/* Top Grid: QR Card & Hero Banner */}
            <div className={showQr ? "drawer-top-grid" : "drawer-hero-only"}>
              {showQr && (
                <div className="kho-qr-card">
                  <div className="kho-qr-card__head">TEM QR VẬT TƯ (IN KỆ KHO)</div>
                  {qrUrl ? (
                    <div className="kho-qr-card__svg" dangerouslySetInnerHTML={{ __html: qrSvg }} />
                  ) : (
                    <div className="kho-qr-card__loading">Đang tạo mã…</div>
                  )}
                  <button
                    type="button"
                    className="kho-qr-card__btn"
                    onClick={printQr}
                    style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6 }}
                  >
                    <Printer style={{ width: 13, height: 13 }} aria-hidden="true" /> In Tem QR dán kệ
                  </button>
                </div>
              )}

              {/* Hero Banner Hợp Nhất 1 Khối (Avatar + Thông Tin Tồn Kho) */}
              <div className="drawer-hero-banner-unified">
                {/* Avatar Ảnh + Thông tin cơ bản */}
                <div className="hero-banner__avatar-col">
                  <div className="hero-avatar-wrapper" title={anh ? "Bấm để phóng to ảnh" : undefined}>
                    {anh ? (
                      <button
                        type="button"
                        className="hero-avatar-btn"
                        onClick={() => setZoom(true)}
                      >
                        <img src={assetUrl(anh) ?? undefined} alt={material.name ?? ""} />
                      </button>
                    ) : (
                      <div className="hero-avatar-ph" aria-hidden="true">
                        <Icon name="camera" size={22} />
                      </div>
                    )}
                    {canEditAnh && (
                      <label className="hero-avatar-action-overlay" title="Tải lên / Đổi ảnh vật tư">
                        <span>{anh ? "Đổi" : "+ Ảnh"}</span>
                        <input
                          type="file"
                          accept="image/*"
                          hidden
                          disabled={anhBusy}
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (f) void pickAnh(f);
                            e.target.value = "";
                          }}
                        />
                      </label>
                    )}
                  </div>

                  <div className="hero-info-txt">
                    <div className="hero-title-row">
                      <h3 className="hero-name">{material.name ?? material.code ?? "—"}</h3>
                      {anh && canEditAnh && (
                        <button
                          type="button"
                          className="hero-del-img-btn"
                          disabled={anhBusy}
                          onClick={() => void removeAnh()}
                          title="Xóa ảnh minh hoạ"
                        >
                          Xóa ảnh
                        </button>
                      )}
                    </div>
                    <div className="hero-sub-code">
                      {material.code ? `Mã: ${material.code}` : "Mặt hàng kho"}
                      {anhBusy && <span className="hero-img-busy"> · Đang lưu ảnh…</span>}
                      {anhErr && <span className="hero-img-err"> · {anhErr}</span>}
                    </div>
                  </div>
                </div>

                {/* Số tồn + Trạng thái LED */}
                <div className="hero-banner__stock-col">
                  <div className="hero-stock-main">
                    <span className="hero-stock-num">{fmtQty(data?.on_hand ?? material.total)}</span>
                    <span className="hero-stock-dvt">{material.dvt ?? "đvt"}</span>
                  </div>
                  {/* CHỈ một chỉ báo trạng thái: StockLevelChip đã tự mang chấm kho-dot--* + chữ.
                      Bỏ đèn LED chói/glow cạnh nó (hai thứ cùng nói một trạng thái). */}
                  <div className="hero-status-row">
                    {material.level ? (
                      <StockLevelChip level={material.level} />
                    ) : (
                      <span className="badge-sem badge-sem--muted">Chưa khai ngưỡng</span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Bảng so sánh giá Nhà Cung Cấp */}
            {soGia.length > 0 && (
              <div className="supplier-price-card">
                <div className="supplier-price-card__head">BÁO GIÁ NHÀ CUNG CẤP QUY ĐỔI</div>
                <table className="rc__table supplier-price-table">
                  <thead>
                    <tr>
                      <th>Nhà cung cấp</th>
                      <th>Báo giá nguyên bản</th>
                      <th className="kho-num">Quy đổi ({material.dvt ?? "gốc"})</th>
                    </tr>
                  </thead>
                  <tbody>
                    {soGia.map((s, i) => {
                      const isCheapest = i === 0 && s.gia_quy_doi != null && soGia.length > 1;
                      return (
                        <tr key={s.supplier_item_id} className={isCheapest ? "is-best-price" : ""}>
                          <td>
                            <b>{s.supplier_name}</b>
                            {isCheapest && (
                              <span className="supplier-best-badge">
                                <Check style={{ width: 12, height: 12 }} aria-hidden="true" /> Rẻ nhất
                              </span>
                            )}
                          </td>
                          <td className="rc__muted">{s.unit_price.toLocaleString("vi-VN")} đ/{s.unit_ten ?? s.unit}</td>
                          <td className="kho-num">
                            {s.gia_quy_doi != null ? <b>{money(Math.round(s.gia_quy_doi))}</b> : <span className="rc__muted">—</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Sticky Tabs Bar */}
            <div className="drawer-sticky-tabs" style={{ margin: "20px 0 16px 0", borderBottom: "1px solid var(--rule-soft)" }}>
              {(
                [
                  ["tong_quan", "Tổng quan"],
                  ["lo_ton", `Lô tồn (${loTon.length})`],
                  ["nhap", `Lịch sử nhập (${nhapThuong.length})`],
                  ["xuat", `Lịch sử xuất (${xuatThuong.length})`],
                  ["chuyen", `Lịch sử chuyển kho (${chuyenRows.length})`],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={`drawer-tab-btn${tab === id ? " is-active" : ""}`}
                  onClick={() => setTab(id)}
                >
                  {label}
                </button>
              ))}
            </div>

          {error && (
            <div className="banner banner--error" role="alert">
              <span>{error}</span>
            </div>
          )}
          {loading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
              {Array.from({ length: 4 }).map((_, i) => (
                <span key={i} className="rc-skel" style={{ width: `${90 - i * 12}%` }} />
              ))}
            </div>
          ) : tab === "tong_quan" ? (
          <MaterialOverview
              material={material}
              threshold={threshold}
              canViewCost={canViewCost}
              onHand={data?.on_hand ?? material.total}
              data={data}
            />
          ) : tab === "lo_ton" ? (
            loTon.length === 0 ? (
              <p className="kho-hint">Không còn lô nào tồn cho vật tư này.</p>
            ) : (
              <div className="kho-lines__wrap">
                <table className="kho-lines">
                  <thead>
                    <tr>
                      <th style={{ minWidth: 130 }}>Phiếu</th>
                      <th style={{ width: 96 }}>Ngày nhập</th>
                      <th className="kho-num">Còn lại</th>
                      <th style={{ minWidth: 96 }}>Vị trí</th>
                      <th style={{ width: 96 }}>HSD</th>
                      {canViewCost && <th className="kho-num">Đơn giá</th>}
                      {canViewCost && <th className="kho-num">Giá trị</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {loTonPaged.map((lot) => (
                      <tr key={lot.id}>
                        <td className="kho-lines__code">
                          {lot.voucher_id != null ? (
                            <CodeLink
                              code={lot.voucher_ma ?? lot.ma_lo}
                              onOpen={() => onOpenVoucher(lot.voucher_id!)}
                            />
                          ) : (
                            "Đầu kỳ"
                          )}
                        </td>
                        <td className="kho-lines__code">{fmtDateISO(lot.ngay_nhap)}</td>
                        <td className="kho-num">{`${fmtQty(lot.sl_con_lai)} ${dvtGoc}`.trim()}</td>
                        <td className="kho-lines__vt">{lot.vi_tri ?? "—"}</td>
                        <HsdCell hsd={lot.hsd} />
                        {canViewCost && (
                          <td className="kho-num">{money(lot.don_gia_nhap ?? 0)}</td>
                        )}
                        {canViewCost && (
                          <td className="kho-num">
                            {money(Math.round(lot.sl_con_lai * (lot.don_gia_nhap ?? 0)))}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          ) : tab === "nhap" ? (
            nhapThuong.length === 0 ? (
              <p className="kho-hint">Chưa có lô nhập nào cho vật tư này.</p>
            ) : (
              <div className="kho-lines__wrap">
                <table className="kho-lines">
                  <thead>
                    <tr>
                      <th style={{ minWidth: 130 }}>Phiếu</th>
                      <th style={{ width: 96 }}>Ngày nhập</th>
                      {/* SL yêu cầu (số đã xin trên yêu cầu sinh ra lô) đứng TRƯỚC SL nhập thực tế. */}
                      <th className="kho-num">SL yêu cầu</th>
                      <th className="kho-num">SL nhập</th>
                      <th style={{ minWidth: 96 }}>Vị trí</th>
                      <th style={{ width: 96 }}>HSD</th>
                      {canViewCost && <th className="kho-num">Đơn giá</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {nhapPaged.map((lot) => (
                      <tr key={lot.id}>
                        {/* Lô hiển thị theo MÃ PHIẾU nhập (đi theo phiếu) — bấm mở phiếu. Đầu kỳ = không có phiếu. */}
                        <td className="kho-lines__code">
                          {lot.voucher_id != null ? (
                            <CodeLink
                              code={lot.voucher_ma ?? lot.ma_lo}
                              onOpen={() => onOpenVoucher(lot.voucher_id!)}
                            />
                          ) : (
                            "Đầu kỳ"
                          )}
                        </td>
                        <td className="kho-lines__code">{fmtDateISO(lot.ngay_nhap)}</td>
                        <td className="kho-num">
                          {lot.sl_de_nghi != null
                            ? `${fmtQty(lot.sl_de_nghi)} ${dvtYeuCau(lot.dvt_yeu_cau)}`.trim()
                            : "—"}
                        </td>
                        <td className="kho-num">{`${fmtQty(lot.sl_ban_dau)} ${dvtGoc}`.trim()}</td>
                        {/* Vị trí là dữ liệu ĐÃ CHỐT sau ghi sổ → CHỈ hiển thị, không cho sửa.
                            KHÔNG dùng .kho-lines__code (11px/xám — class đó dành cho MÃ): đây là
                            cột thủ kho đọc rồi cầm xuống kho, phải rõ như các cột số. */}
                        <td className="kho-lines__vt">{lot.vi_tri ?? "—"}</td>
                        <HsdCell hsd={lot.hsd} />
                        {canViewCost && (
                          <td className="kho-num">{money(lot.don_gia_nhap ?? 0)}</td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          ) : tab === "xuat" ? (
            xuatThuong.length === 0 ? (
            <p className="kho-hint">Chưa có lần xuất nào cho vật tư này.</p>
          ) : (
            <div className="kho-lines__wrap">
              <table className="kho-lines">
                <thead>
                  <tr>
                    {/* Số phiếu ĐỨNG TRƯỚC ngày, đúng thứ tự tab Nhập — mở drawer là mắt rơi vào
                        cùng một chỗ dù đang ở tab nào. */}
                    <th style={{ minWidth: 130 }}>Số phiếu</th>
                    <th style={{ width: 96 }}>Ngày xuất</th>
                    {/* SL yêu cầu (số đã xin trên yêu cầu sinh ra dòng xuất) đứng TRƯỚC SL xuất thực tế. */}
                    <th className="kho-num">SL yêu cầu</th>
                    <th className="kho-num">SL xuất</th>
                    {/* Vị trí + HSD của LÔ đã xuất — cùng bộ cột với tab Nhập để mắt không phải
                        đổi chỗ khi bấm qua lại giữa hai tab. */}
                    <th style={{ minWidth: 96 }}>Vị trí</th>
                    <th style={{ width: 96 }}>HSD</th>
                    {canViewCost && <th className="kho-num">Giá vốn</th>}
                  </tr>
                </thead>
                <tbody>
                  {xuatPaged.map((r, i) => {
                    const lot = r.lot_id != null ? lotById.get(r.lot_id) : undefined;
                    return (
                    <tr key={`${r.voucher_id}-${r.lot_id}-${i}`}>
                      <td className="kho-lines__code">
                        <CodeLink
                          code={r.voucher_ma ?? "—"}
                          onOpen={() => onOpenVoucher(r.voucher_id)}
                        />
                      </td>
                      <td className="kho-lines__code">{fmtDateISO(r.ngay)}</td>
                      <td className="kho-num">
                        {r.sl_de_nghi != null
                          ? `${fmtQty(r.sl_de_nghi)} ${dvtYeuCau(r.dvt_yeu_cau)}`.trim()
                          : "—"}
                      </td>
                      <td className="kho-num">{`${fmtQty(r.so_luong)} ${dvtGoc}`.trim()}</td>
                      <td className="kho-lines__vt">{lot?.vi_tri ?? "—"}</td>
                      <HsdCell hsd={lot?.hsd} />
                      {canViewCost && (
                        <td className="kho-num">
                          {r.don_gia != null ? money(Math.round(r.don_gia * r.so_luong)) : ""}
                        </td>
                      )}
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
          ) : chuyenRows.length === 0 ? (
            <p className="kho-hint">Chưa có lần chuyển kho nào cho vật tư này.</p>
          ) : (
            <div className="kho-lines__wrap">
              <table className="kho-lines">
                <thead>
                  <tr>
                    <th style={{ minWidth: 130 }}>Số phiếu</th>
                    <th style={{ width: 96 }}>Ngày</th>
                    <th style={{ minWidth: 100 }}>Chiều</th>
                    <th className="kho-num">Số lượng</th>
                    <th style={{ minWidth: 96 }}>Vị trí</th>
                    <th style={{ width: 96 }}>HSD</th>
                    {canViewCost && <th className="kho-num">Giá trị</th>}
                  </tr>
                </thead>
                <tbody>
                  {chuyenPaged.map((r) => (
                    <tr key={r.key}>
                      <td className="kho-lines__code">
                        {r.voucher_id != null ? (
                          <CodeLink
                            code={r.voucher_ma ?? "—"}
                            onOpen={() => onOpenVoucher(r.voucher_id!)}
                          />
                        ) : (
                          r.voucher_ma ?? "—"
                        )}
                      </td>
                      <td className="kho-lines__code">{fmtDateISO(r.ngay)}</td>
                      {/* Chiều điều chuyển ở góc nhìn của KHO NÀY: nhận về (là kho đích) / chuyển đi
                          (là kho nguồn). Text tự rõ nghĩa nên giữ màu trung tính, không tô đỏ/xanh. */}
                      <td className="rc__nowrap">
                        <span style={{ fontSize: 12, color: "var(--ash)" }}>
                          {r.dir === "in" ? "⇄ nhận về" : "⇄ chuyển đi"}
                        </span>
                      </td>
                      <td className="kho-num">{`${fmtQty(r.so_luong)} ${dvtGoc}`.trim()}</td>
                      <td className="kho-lines__vt">{r.vi_tri ?? "—"}</td>
                      <HsdCell hsd={r.hsd} />
                      {canViewCost && (
                        <td className="kho-num">
                          {r.don_gia != null ? money(Math.round(r.don_gia * r.so_luong)) : ""}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!loading &&
            tab !== "tong_quan" &&
            (tab === "nhap"
              ? nhapThuong.length
              : tab === "xuat"
                ? xuatThuong.length
                : tab === "lo_ton"
                  ? loTon.length
                  : chuyenRows.length) > DRAWER_PAGE && (
              <DrawerPager
                page={page}
                total={
                  tab === "nhap"
                    ? nhapThuong.length
                    : tab === "xuat"
                      ? xuatThuong.length
                      : tab === "lo_ton"
                        ? loTon.length
                        : chuyenRows.length
                }
                pageSize={DRAWER_PAGE}
                onPage={setPage}
              />
            )}
        </div>
      </aside>
    </div>
    {zoom && anh && (
      <div
        className="kho-anh__lightbox"
        role="dialog"
        aria-modal="true"
        onClick={() => setZoom(false)}
      >
        <img
          src={assetUrl(anh) ?? undefined}
          alt={material.name ?? "Ảnh vật tư"}
          onClick={(e) => e.stopPropagation()}
        />
      </div>
    )}
    {dcOpen && (
      <DieuChuyenDialog
        token={token}
        khoNguonId={khoId}
        khoNguonTen={khoTen}
        khoDich={khoDich}
        items={[
          {
            hang_loai: material.hang_loai,
            hang_id: material.hang_id,
            ten: material.name ?? material.code ?? "vật tư",
            dvt: material.dvt ?? "",
            tonKhaDung: data?.on_hand ?? material.total,
          },
        ]}
        onDone={() => {
          setDcOpen(false);
          onDieuChuyenDone();
          onClose(); // tồn nguồn đã đổi → đóng drawer, cha đã nạp lại danh sách
        }}
        onCancel={() => setDcOpen(false)}
      />
    )}
    </>
  );
}

// Dialog ĐIỀU CHUYỂN 1 mặt hàng sang kho khác. Trừ tồn nguồn NGAY khi xác nhận (tự lập + ghi sổ
// phiếu xuất), rồi sinh YÊU CẦU ĐIỀU CHUYỂN ở đích cho kho đích lập phiếu nhận. Tái dùng ConfirmDialog.
// 1 mặt hàng trong popup điều chuyển (dùng chung cho 1 mặt hàng ở drawer LẪN nhiều mặt hàng tick
// hàng loạt ở danh sách tồn).
interface DcItem {
  hang_loai: HangLoai;
  hang_id: number;
  ten: string;
  dvt: string;
  tonKhaDung: number;
}

function DieuChuyenDialog({
  token,
  khoNguonId,
  khoNguonTen,
  khoDich,
  items,
  onDone,
  onCancel,
}: {
  token: string;
  khoNguonId: number;
  khoNguonTen: string;
  khoDich: { id: number; ma: string; ten: string }[];
  items: DcItem[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const keyOf = (it: DcItem) => `${it.hang_loai}:${it.hang_id}`;
  const [khoDenId, setKhoDenId] = useState<number | null>(null);
  // SL chuyển từng mặt hàng — mặc định = tồn khả dụng (chuyển hết), sửa được từng dòng.
  const [qty, setQty] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      items.map((it) => [keyOf(it), it.tonKhaDung > 0 ? String(it.tonKhaDung) : ""]),
    ),
  );
  // Vị trí cất ở KHO ĐÍCH (kệ/ô) — tuỳ chọn, khai ngay lúc ấn; áp cho mọi lô của mặt hàng.
  const [viTri, setViTri] = useState<Record<string, string>>({});
  const [ghiChu, setGhiChu] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nhieu = items.length > 1;

  async function chuyen() {
    if (khoDenId == null) {
      setError("Chọn kho đích.");
      return;
    }
    const chosen: { it: DcItem; sl: number }[] = [];
    for (const it of items) {
      const sl = Number(qty[keyOf(it)]);
      if (!Number.isFinite(sl) || sl <= 0) continue;
      if (sl > it.tonKhaDung + 1e-9) {
        setError(`“${it.ten}” vượt tồn khả dụng (${fmtQty(it.tonKhaDung)} ${it.dvt}).`);
        return;
      }
      chosen.push({ it, sl });
    }
    if (chosen.length === 0) {
      setError("Nhập số lượng > 0 cho ít nhất 1 mặt hàng.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.kho.phieu.dieuChuyen(token, {
        kho_nguon_id: khoNguonId,
        kho_den_id: khoDenId,
        items: chosen.map((x) => ({
          hang_loai: x.it.hang_loai,
          hang_id: x.it.hang_id,
          so_luong: x.sl,
          vi_tri: (viTri[keyOf(x.it)] ?? "").trim() || null,
        })),
        ghi_chu: ghiChu.trim() || null,
      });
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không điều chuyển được.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      open
      wide={nhieu}
      title={nhieu ? `Chuyển kho — ${items.length} mặt hàng` : `Chuyển kho — ${items[0]?.ten ?? "vật tư"}`}
      message={`Gộp vào MỘT yêu cầu điều chuyển sang kho đích. Tồn CHƯA đổi — chỉ trừ kho “${khoNguonTen}” và cộng kho đích KHI kho đích ghi sổ phiếu nhập.`}
      confirmLabel="Điều chuyển"
      cancelLabel="Hủy"
      busy={busy}
      error={error}
      confirmDisabled={khoDenId == null}
      onConfirm={() => void chuyen()}
      onCancel={onCancel}
    >
      <div className="rc-grid kho-setth">
        <div className="rc-field">
          <span className="rc-field__label">Từ kho (nguồn)</span>
          <input className="rc-input" value={khoNguonTen} disabled readOnly />
        </div>
        <div className="rc-field">
          <label className="rc-field__label" htmlFor="dc-kho-den">
            Đến kho (đích) <em>*</em>
          </label>
          <Select
            id="dc-kho-den"
            portal
            ariaLabel="Kho đích"
            placeholder="— Chọn kho đích —"
            value={khoDenId}
            onChange={(v) => setKhoDenId(v as number | null)}
            options={khoDich.map((w) => ({ value: w.id, label: w.ten, hint: w.ma }))}
          />
        </div>
      </div>

      <div className="kho-dc-lines">
        <table className="kho-lines">
          <thead className="kho-lines__head">
            <tr>
              <th style={{ minWidth: 160 }}>Vật tư</th>
              <th className="kho-num">Tồn khả dụng</th>
              <th className="kho-num" style={{ width: 140 }}>SL chuyển</th>
              <th style={{ width: 160 }}>Vị trí (kho đích)</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it) => {
              const k = keyOf(it);
              return (
                <tr key={k}>
                  <td>{it.ten}</td>
                  <td className="kho-num">
                    {fmtQty(it.tonKhaDung)} {it.dvt}
                  </td>
                  <td className="kho-num">
                    <input
                      type="number"
                      min={0}
                      step="any"
                      className="rc-input kho-num"
                      value={qty[k] ?? ""}
                      onChange={(e) => setQty((prev) => ({ ...prev, [k]: e.target.value }))}
                      aria-label={`SL chuyển ${it.ten}`}
                    />
                  </td>
                  <td>
                    <input
                      className="rc-input"
                      value={viTri[k] ?? ""}
                      onChange={(e) => setViTri((prev) => ({ ...prev, [k]: e.target.value }))}
                      placeholder="kệ / ô… (tuỳ chọn)"
                      aria-label={`Vị trí ${it.ten}`}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="rc-field">
        <label className="rc-field__label" htmlFor="dc-ghichu">
          Ghi chú
        </label>
        <input
          id="dc-ghichu"
          className="rc-input"
          value={ghiChu}
          maxLength={1000}
          placeholder="Lý do / ghi chú điều chuyển (tuỳ chọn)"
          onChange={(e) => setGhiChu(e.target.value)}
        />
      </div>
    </ConfirmDialog>
  );
}

// Tab "Tổng quan" của drawer vật tư — CHỈ ĐỌC, gộp từ material.lots + threshold. Thanh gauge
// Min–Max tô theo mức tồn (cùng tông StockLevelChip) + lưới chỉ số. Chưa khai ngưỡng → ẩn gauge.
function MaterialOverview({
  material,
  threshold,
  canViewCost,
  onHand,
  data,
}: {
  material: MaterialGroup;
  threshold: StockThreshold | undefined;
  canViewCost: boolean;
  onHand: number;
  data: StockMaterialHistory | null;
}) {
  const { dvt, lots, level, value, viTris } = material;
  // Ngày nhập gần nhất (max) — lô còn tồn của mã này.
  let newest: string | null = null;
  for (const l of lots) if (newest == null || l.ngay_nhap > newest) newest = l.ngay_nhap;
  // HSD gần nhất = lô sắp hết hạn SỚM nhất (min) trong các lô có khai HSD.
  let hsdSoonest: string | null = null;
  for (const l of lots) {
    if (!l.hsd) continue;
    if (hsdSoonest == null || l.hsd < hsdSoonest) hsdSoonest = l.hsd;
  }
  const hasThreshold = threshold != null;
  const min = threshold?.nguong_ton ?? null;
  const max = threshold?.nguong_toi_da ?? null;
  const avgCost = onHand > 0 ? value / onHand : 0;

  // Thang gauge: domain 0 → (max hoặc mốc trên) + 15% headroom; kẹp % trong [0,100].
  const upper = max ?? min ?? onHand;
  const domainMax = Math.max(onHand, upper ?? 0, min ?? 0) * 1.15 || 1;
  const pct = (v: number) => Math.max(0, Math.min(100, (v / domainMax) * 100));
  const fillPct = pct(onHand);
  const minPct = min != null ? pct(min) : null;
  const maxPct = max != null ? pct(max) : null;

  // Tổng nhập/xuất toàn thời gian từ data.
  const totalNhap = (data?.nhap ?? []).reduce((s, l) => s + l.sl_ban_dau, 0);
  const totalXuat = (data?.xuat ?? []).reduce((s, r) => s + r.so_luong, 0);
  // Đếm lô ĐÃ XUẤT HẾT từ `data.nhap` (con_hang=false → có cả lô `empty`); KHÔNG dùng `material.lots`
  // vì mảng đó đã lọc bỏ lô hết (sl_con_lai>0) nên đếm ở đó luôn ra 0.
  const loHetHang = (data?.nhap ?? []).filter((l) => l.sl_con_lai <= 0).length;

  // Biểu đồ cột nhập/xuất 12 tháng gần nhất (Recharts Composed Chart + Area Gradient)
  const monthlyChart = useMemo(() => {
    const buckets = new Map<string, { monthLabel: string; nhap: number; xuat: number }>();
    const now = new Date();
    for (let i = 11; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      const monthLabel = `T${String(d.getMonth() + 1).padStart(2, "0")}`;
      buckets.set(key, { monthLabel, nhap: 0, xuat: 0 });
    }
    for (const l of data?.nhap ?? []) {
      const key = l.ngay_nhap.slice(0, 7);
      const b = buckets.get(key);
      if (b) b.nhap += l.sl_ban_dau;
    }
    for (const r of data?.xuat ?? []) {
      const key = r.ngay.slice(0, 7);
      const b = buckets.get(key);
      if (b) b.xuat += r.so_luong;
    }
    return [...buckets.values()];
  }, [data]);

  // Tìm tháng cao điểm nhất
  const peakMonth = useMemo(() => {
    let best = { monthLabel: "", val: 0, type: "nhập" };
    for (const m of monthlyChart) {
      if (m.nhap > best.val) best = { monthLabel: m.monthLabel, val: m.nhap, type: "nhập" };
      if (m.xuat > best.val) best = { monthLabel: m.monthLabel, val: m.xuat, type: "xuất" };
    }
    return best.val > 0 ? best : null;
  }, [monthlyChart]);

  return (
    <div className="kho-ov">
      {/* Gauge ngưỡng tồn */}
      {hasThreshold ? (
        <div className="kho-gauge" aria-hidden="true" style={{ marginBottom: 16 }}>
          <div className="kho-gauge__track">
            {minPct != null && maxPct != null && (
              <span
                className="kho-gauge__band"
                style={{ left: `${minPct}%`, width: `${Math.max(0, maxPct - minPct)}%` }}
              />
            )}
            <span
              className={`kho-gauge__fill kho-gauge__fill--${level ?? "du"}`}
              style={{ width: `${fillPct}%` }}
            />
            {minPct != null && (
              <span className="kho-gauge__tick" style={{ left: `${minPct}%` }} />
            )}
            {maxPct != null && (
              <span className="kho-gauge__tick" style={{ left: `${maxPct}%` }} />
            )}
          </div>
        </div>
      ) : (
        <p className="kho-hint" style={{ marginBottom: 16 }}>Chưa khai ngưỡng cho vật tư này.</p>
      )}

      {/* Biểu đồ Recharts Composed Area-Bar Chart */}
      {data != null && (totalNhap > 0 || totalXuat > 0) && (
        <div className="recharts-overview-box">
          <div className="recharts-overview-box__head">
            <div className="recharts-overview-box__title">
              BIỂU ĐỒ NHẬP / XUẤT 12 THÁNG GẦN NHẤT
            </div>
            <div className="recharts-pills-row">
              <span className="pill-stat pill-stat--nhap">
                <span className="kho-dot" aria-hidden="true" /> Nhập: {fmtQty(totalNhap)} {dvt ?? ""}
              </span>
              <span className="pill-stat pill-stat--xuat">
                <span className="kho-dot" aria-hidden="true" /> Xuất: {fmtQty(totalXuat)} {dvt ?? ""}
              </span>
              {peakMonth && (
                <span className="pill-stat pill-stat--peak">
                  Cao nhất: {peakMonth.monthLabel} ({fmtQty(peakMonth.val)} {dvt ?? ""})
                </span>
              )}
            </div>
          </div>

          <div style={{ width: "100%", height: 210 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={monthlyChart} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <defs>
                  {/* Nhập = moss (#2f5d3a, ĐÚNG --moss), Xuất = rust (#c5400a, ĐÚNG --rust): cặp
                      màu chuẩn của phân hệ kho — KHÔNG dùng xanh chói #22c55e off-palette. */}
                  <linearGradient id="nhapGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#2f5d3a" stopOpacity={0.9} />
                    <stop offset="95%" stopColor="#2f5d3a" stopOpacity={0.3} />
                  </linearGradient>
                  <linearGradient id="xuatGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#c5400a" stopOpacity={0.9} />
                    <stop offset="95%" stopColor="#c5400a" stopOpacity={0.3} />
                  </linearGradient>
                </defs>

                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="monthLabel" tickLine={false} axisLine={{ stroke: "#cbd5e1" }} tick={{ fontSize: 11, fill: "var(--ash)" }} />
                <YAxis tickLine={false} axisLine={false} tickFormatter={(v) => fmtQty(v)} tick={{ fontSize: 11, fill: "var(--ash)" }} />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (active && payload && payload.length) {
                      return (
                        <div className="custom-recharts-tooltip">
                          <div className="custom-recharts-tooltip__title">Tháng {label}</div>
                          {payload.map((entry, idx) => (
                            <div key={idx} className="custom-recharts-tooltip__row" style={{ color: entry.name === "nhap" ? "#6f9e79" : "#e8996a" }}>
                              <span>{entry.name === "nhap" ? "Nhập kho:" : "Xuất kho:"}</span>
                              <b>{fmtQty(Number(entry.value))} {dvt ?? ""}</b>
                            </div>
                          ))}
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                {/* Nhập + Xuất CÙNG dạng cột (grouped bars) → cân xứng, dễ so sánh từng tháng. */}
                <Bar dataKey="nhap" name="nhap" fill="url(#nhapGrad)" stroke="#2f5d3a" radius={[4, 4, 0, 0]} barSize={14} />
                <Bar dataKey="xuat" name="xuat" fill="url(#xuatGrad)" stroke="#c5400a" radius={[4, 4, 0, 0]} barSize={14} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Rich Data Summary Panel (Gắn 2 Khối Đa Cột Giàu Thông Tin) */}
      <div className="drawer-rich-panel">
        {/* Box 1: Chỉ số vận hành & Chu kỳ kho */}
        <div className="rich-panel-box">
          <div className="rich-panel-box__title">CHỈ SỐ VẬN HÀNH KHO</div>
          <div className="rich-data-grid">
            <div className="rich-data-item">
              <span className="rich-data-item__label">Tổng số lô tồn</span>
              <span className="rich-data-item__val">{lots.length} lô</span>
            </div>
            <div className="rich-data-item">
              <span className="rich-data-item__label">Ngày nhập gần nhất</span>
              <span className="rich-data-item__val">{newest ? fmtDateISO(newest) : "—"}</span>
            </div>
            <div className="rich-data-item">
              <span className="rich-data-item__label">HSD gần nhất</span>
              <span className="rich-data-item__val">{hsdSoonest ? fmtDateISO(hsdSoonest) : "Không khai"}</span>
            </div>
            <div className="rich-data-item">
              <span className="rich-data-item__label">Tổng đã nhập (toàn thời gian)</span>
              <span className="rich-data-item__val">{fmtQty(totalNhap)} {dvt ?? ""}</span>
            </div>
            <div className="rich-data-item">
              <span className="rich-data-item__label">Tổng đã xuất (toàn thời gian)</span>
              <span className="rich-data-item__val">{fmtQty(totalXuat)} {dvt ?? ""}</span>
            </div>
            <div className="rich-data-item">
              <span className="rich-data-item__label">Vị trí cất kho</span>
              <span className="rich-data-item__val">{viTris.length ? viTris.join(", ") : "Chưa gắn"}</span>
            </div>
          </div>
        </div>

        {/* Box 2: Giá vốn & Tài chính tồn kho */}
        {canViewCost && (
          <div className="rich-panel-box">
            <div className="rich-panel-box__title">TÀI CHÍNH & GIÁ VỐN TỒN KHO</div>
            <div className="rich-data-grid">
              <div className="rich-data-item">
                <span className="rich-data-item__label">Tổng giá trị tồn kho</span>
                <span className="rich-data-item__val rich-data-item__val--primary">{money(Math.round(value))}</span>
              </div>
              <div className="rich-data-item">
                <span className="rich-data-item__label">Giá vốn bình quân</span>
                <span className="rich-data-item__val">{onHand > 0 ? `${money(Math.round(avgCost))}/${dvt ?? "đvt"}` : "—"}</span>
              </div>
              <div className="rich-data-item">
                <span className="rich-data-item__label">Giá trị trung bình 1 lô</span>
                <span className="rich-data-item__val">{lots.length > 0 ? money(Math.round(value / lots.length)) : "—"}</span>
              </div>
              <div className="rich-data-item">
                <span className="rich-data-item__label">Số lô đã xuất hết</span>
                <span className="rich-data-item__val">{loHetHang} lô</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


// Popup đặt ngưỡng tồn cho MỘT mã (thay drawer chọn-mã cũ). Bấm ô Min/Max hoặc badge Trạng thái
// trên dòng → mở đây với mã đã khoá sẵn. Tái dùng ConfirmDialog (giữ mở khi lỗi/đang lưu).
function SetThresholdDialog({
  token,
  khoId,
  material,
  current,
  onSaved,
  onClose,
}: {
  token: string;
  khoId: number;
  material: MaterialGroup;
  current: StockThreshold | undefined;
  onSaved: (t: StockThreshold) => void;
  onClose: () => void;
}) {
  // Pre-fill từ ngưỡng hiện có (nếu mã đã khai); chưa khai → rỗng + cảnh báo BẬT mặc định.
  const [nguongTon, setNguongTon] = useState(current ? String(current.nguong_ton) : "");
  const [nguongToiDa, setNguongToiDa] = useState(
    current?.nguong_toi_da != null ? String(current.nguong_toi_da) : "",
  );
  const [canhBao, setCanhBao] = useState(current ? current.canh_bao : true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    // Validate mirror ThresholdDrawer: Min số hữu hạn ≥ 0; Max rỗng→null, nếu có phải ≥ Min.
    const ton = Number(nguongTon);
    if (!Number.isFinite(ton) || ton < 0) {
      setError("Ngưỡng tồn phải là số không âm.");
      return;
    }
    const max = nguongToiDa.trim() === "" ? null : Number(nguongToiDa);
    if (max != null && (!Number.isFinite(max) || max < ton)) {
      setError("Ngưỡng tối đa phải lớn hơn hoặc bằng ngưỡng tồn.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const t = await api.kho.nguongTon.upsert(token, {
        hang_loai: material.hang_loai,
        hang_id: material.hang_id,
        kho_id: khoId,
        nguong_ton: ton,
        nguong_can_ton: null,
        nguong_toi_da: max,
        canh_bao: canhBao,
      });
      onSaved(t);
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không lưu được ngưỡng tồn.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      open
      title={`Đặt ngưỡng — ${material.name ?? material.code ?? "vật tư"}`}
      confirmLabel="Lưu ngưỡng"
      cancelLabel="Hủy"
      busy={busy}
      error={error}
      onConfirm={() => void save()}
      onCancel={onClose}
    >
      <div className="rc-grid kho-setth">
        <div className="rc-field">
          <label className="rc-field__label" htmlFor="setth-ton">
            Ngưỡng tồn (Min) <em>*</em>
          </label>
          <input
            id="setth-ton"
            type="number"
            min={0}
            step="any"
            className="rc-input kho-num"
            value={nguongTon}
            autoFocus
            onChange={(e) => setNguongTon(e.target.value)}
          />
          <p className="rc-field__hint">Dưới mức này là "Cần mua".</p>
        </div>
        <div className="rc-field">
          <label className="rc-field__label" htmlFor="setth-max">
            Ngưỡng tối đa (Max)
          </label>
          <input
            id="setth-max"
            type="number"
            min={0}
            step="any"
            className="rc-input kho-num"
            value={nguongToiDa}
            onChange={(e) => setNguongToiDa(e.target.value)}
          />
          <p className="rc-field__hint">
            Vượt mức này báo "Dư". Bỏ trống → tự tính = Min × 1.3.
          </p>
        </div>
        <div className="rc-field rc-field--check">
          <span className="rc-field__label">Bật cảnh báo</span>
          <label className="rc-switch">
            <input
              type="checkbox"
              checked={canhBao}
              onChange={(e) => setCanhBao(e.target.checked)}
            />
            <span className="rc-switch__slider" />
          </label>
        </div>
      </div>
    </ConfirmDialog>
  );
}

// Phân trang cho bảng trong drawer Lịch sử Nhập/Xuất — cùng khung .kho-pager với màn Tồn kho.
function DrawerPager({
  page,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  total: number;
  pageSize: number;
  onPage: (p: number) => void;
}) {
  const maxPage = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="kho-pager">
      <span className="kho-pager__page">{total} dòng</span>
      <div className="rc__spacer" />
      <button
        type="button"
        className="btn btn--ghost"
        disabled={page <= 1}
        onClick={() => onPage(Math.max(1, page - 1))}
      >
        Trước
      </button>
      <span className="kho-pager__page">
        Trang {page} / {maxPage}
      </span>
      <button
        type="button"
        className="btn btn--ghost"
        disabled={page >= maxPage}
        onClick={() => onPage(Math.min(maxPage, page + 1))}
      >
        Sau
      </button>
    </div>
  );
}

const BoxIcon = () => (
  <svg
    width="48"
    height="48"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="rc__empty-icon"
  >
    <path d="M3 8.6 12 4l9 4.6v6.8L12 20l-9-4.6z" />
    <path d="M3 8.6 12 13m0 0 9-4.4M12 13v7" />
  </svg>
);

