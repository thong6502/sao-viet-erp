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
import { Button } from "../components/Button";
import { CodeLink } from "../components/CodeLink";
import { Icon } from "../components/Icons";
import { Select } from "../components/Select";
import { StockLevelChip } from "../components/StockLevelChip";
import type { NavigateFn } from "../components/AppShell";
import { fmtDateISO, money } from "../utils/format";
import { qrToSvg } from "../lib/qr";
import {
  DateFilterHead,
  NumFilterHead,
  PageSizeSelect,
  DEFAULT_PAGE_SIZE,
  VoucherStatusBadge,
  fmtQty,
  inNumRange,
  useHeaderTitles,
} from "./khoShared";
import { InboxRequestDrawer, VoucherDrawer } from "./KhoYeuCauPage";
import { ConfirmDialog } from "../components/ConfirmDialog";
import "./rebuild-catalog.css";
import "./kho-request.css";

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
  // Mức tồn 5 màu so với ngưỡng đã khai. null = chưa khai ngưỡng cho mã này ở kho này.
  level: StockLevel | null;
}

type TonTab = "ton" | "nhap" | "xuat";

/** Mức tồn 4 mức — MIRROR backend `stock_level` (bỏ "sắp hết/cận tồn"). Chưa khai ngưỡng
 *  → null (không bịa cảnh báo). Màn tồn chỉ có hàng còn tồn nên "het" gần như không xuất hiện. */
function levelOf(onHand: number, th: StockThreshold | undefined): StockLevel | null {
  if (onHand <= 0) return "het";
  if (!th) return null;
  if (onHand <= th.nguong_ton) return "can_mua";
  if (th.nguong_toi_da != null && onHand > th.nguong_toi_da) return "du_ton";
  return "du";
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

  // Về trang 1 khi đổi tab / tìm kiếm / lọc phiếu / lọc ngày-tồn / lọc phiếu (ngày·giá vốn).
  useEffect(() => {
    setPage(1);
  }, [
    tab,
    q,
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
          level: null,
        };
        m.set(key, g);
      }
      g.total += lot.sl_con_lai;
      g.value += lot.sl_con_lai * (lot.don_gia_nhap ?? 0);
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
    return groups.filter((g) => {
      if (
        s &&
        !((g.name ?? "").toLowerCase().includes(s) || (g.code ?? "").toLowerCase().includes(s))
      )
        return false;
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
  }, [groups, q, dateFrom, dateTo, tonFrom, tonTo, gtFrom, gtTo]);

  const shownVouchers = useMemo(() => {
    const s = q.trim().toLowerCase();
    // Tab quyết định loại phiếu (Nhập/Xuất) — thay bộ lọc dropdown cũ. Tab 'ton' không render list này.
    const wantLoai = tab === "xuat" ? "XUAT" : "NHAP";
    const vf = vValFrom.trim() === "" ? null : Number(vValFrom);
    const vt = vValTo.trim() === "" ? null : Number(vValTo);
    return vouchers
      .filter((v) => v.loai === wantLoai)
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

  const totalValue = useMemo(
    () => (canViewCost ? groups.reduce((s, g) => s + g.value, 0) : 0),
    [groups, canViewCost],
  );
  // Cảnh báo: mã đang ở "Cần mua" (≤ ngưỡng tồn).
  const canMua = useMemo(() => groups.filter((g) => g.level === "can_mua"), [groups]);

  // Xóa mọi bộ lọc của TAB đang xem (nút "Xóa lọc" ở empty-state). Funnel từng cột tự có nút riêng.
  function clearFilters() {
    if (tab === "ton") {
      setDateFrom("");
      setDateTo("");
      setTonFrom("");
      setTonTo("");
      setGtFrom("");
      setGtTo("");
    } else {
      setVDateFrom("");
      setVDateTo("");
      setVValFrom("");
      setVValTo("");
    }
  }

  // Tạo Yêu cầu mua hàng từ các mã đã tick: mở form YCMH (nguồn Kho) điền sẵn Tên + ĐVT + SL cần
  // mua; KHOÁ Tên + ĐVT (lấy từ mặt hàng đã có), chỉ cho sửa số lượng. SL cần mua = (ngưỡng tối đa
  // nếu có, không thì ngưỡng tồn) − tồn hiện tại, kẹp ≥ 0. Người dùng chỉnh lại được.
  function createPurchaseFromSelected() {
    const chosen = groups.filter((g) => selected.has(g.key));
    if (chosen.length === 0) return;
    navigate("yeu-cau-mua-hang", {
      purchaseSeedLines: chosen.map((g) => {
        // SL cần mua = (ngưỡng tối đa nếu có, không thì ngưỡng tồn) − tồn hiện tại, kẹp ≥ 0.
        // Gợi ý rule-based để về ngưỡng; người mua chỉnh lại được.
        const th = thresholds[g.key];
        const target = th?.nguong_toi_da ?? th?.nguong_ton ?? 0;
        return {
          // Mang theo CẶP chứ không chỉ tên: phía mua hàng nối được về đúng mặt hàng gốc,
          // thay vì ghép mù bằng chuỗi tên (ghép trượt thì im lặng sai).
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
  // Cột tab Tồn kho: [checkbox nếu canCreate] + Vật tư + Vị trí + Tồn khả dụng + Số đợt nhập +
  // Min/Max + Trạng thái + Ngày nhập (7 cột cố định — Min/Max & Trạng thái AI cũng xem được,
  // KHÔNG gate theo set_threshold) [+ Giá trị tồn nếu view_cost].
  const tonCols = (canCreate ? 1 : 0) + 7 + (canViewCost ? 1 : 0);

  // Phân trang (dùng chung cho cả 2 tab; số tổng theo tab đang xem).
  const pageTotal = tab === "ton" ? filtered.length : shownVouchers.length;
  const maxPage = Math.max(1, Math.ceil(pageTotal / pageSize));
  const pagedGroups = filtered.slice((page - 1) * pageSize, page * pageSize);
  const pagedVouchers = shownVouchers.slice((page - 1) * pageSize, page * pageSize);

  return (
    <main className="rc kho-list">
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">{ten}</h1>
          <span className="rc__count">
            {tab === "ton"
              ? `${groups.length} vật tư đang tồn`
              : `${shownVouchers.length} phiếu`}
            {ma ? ` · ${ma}` : ""}
          </span>
        </div>
        <p className="rc__sub">
          {tab === "ton"
            ? "Tồn khả dụng theo từng vật tư — bấm một dòng để xem chi tiết các lô."
            : tab === "nhap"
              ? "Phiếu NHẬP đã lập tại kho này."
              : "Phiếu XUẤT đã lập tại kho này."}
        </p>
      </header>

      <div className="kho-shell">
        <div className="kho-shell__fns">
          {(
            [
              ["ton", "Tồn kho"],
              ["nhap", "Phiếu nhập"],
              ["xuat", "Phiếu xuất"],
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
      </div>

      <div className="rc__toolbar">
        <div className="rc__search-wrapper">
          <SearchIcon />
          <input
            className="rc__search"
            placeholder={
              tab === "ton" ? "Tìm mã / tên vật tư…" : "Tìm số phiếu / mã yêu cầu / tên vật tư…"
            }
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        {tab !== "ton" && (
          <>
            <div className="kho-picker">
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
          </>
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

      {/* Cảnh báo tồn dưới ngưỡng — dựa trên ngưỡng đã khai cho kho này. */}
      {tab === "ton" && !loading && canMua.length > 0 && (
        <div className="banner banner--warn" role="status" style={{ marginBottom: "var(--sp-4)" }}>
          <span>
            <b>{canMua.length}</b> mã <b>cần mua</b> (≤ ngưỡng tồn) — tick để tạo yêu cầu mua.
          </span>
          {canCreate && (
            <button
              type="button"
              className="btn btn--ghost"
              style={{ padding: "4px 12px", fontSize: "12px" }}
              onClick={() => setSelected(new Set(canMua.map((g) => g.key)))}
            >
              Chọn hết
            </button>
          )}
        </div>
      )}

      {/* Thanh hành động khi đã tick — tạo Yêu cầu mua hàng cho các mã đã chọn. */}
      {tab === "ton" && canCreate && selected.size > 0 && (
        <div className="kho-selbar">
          <span>
            Đã chọn <b>{selected.size}</b> mã
          </span>
          <div className="rc__spacer" />
          <button type="button" className="btn btn--ghost" onClick={() => setSelected(new Set())}>
            Bỏ chọn
          </button>
          {khoOptions.filter((w) => w.id !== khoId).length > 0 && (
            <Button variant="secondary" onClick={() => setDcBulkOpen(true)}>
              ⇄ Điều chuyển
            </Button>
          )}
          <Button variant="accent" onClick={createPurchaseFromSelected}>
            Tạo yêu cầu mua
          </Button>
        </div>
      )}

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
                <th>Vật tư</th>
                <th style={{ width: "8%" }}>Vị trí</th>
                <NumFilterHead className="kho-num" style={{ width: "14%" }} label="Tồn khả dụng" from={tonFrom} to={tonTo} onChange={(f, t) => { setTonFrom(f); setTonTo(t); }} />
                <th className="kho-num" style={{ width: "10%" }}>
                  Số đợt nhập
                </th>
                <th className="kho-num" style={{ width: "11%" }}>
                  Min / Max
                </th>
                <th style={{ width: "9%" }}>Trạng thái</th>
                <DateFilterHead className="kho-num kho-colfil--num" style={{ width: "18%" }} label="Ngày nhập mới nhất" from={dateFrom} to={dateTo} onChange={(f, t) => { setDateFrom(f); setDateTo(t); }} />
                {canViewCost && (
                  <NumFilterHead className="kho-num" style={{ width: "12%" }} label="Giá trị tồn" from={gtFrom} to={gtTo} onChange={(f, t) => { setGtFrom(f); setGtTo(t); }} />
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
            </tbody>
          </table>
        )}
      </div>

      {!loading && pageTotal > 0 && (
        <div className="kho-pager">
          <PageSizeSelect value={pageSize} onChange={setPageSize} />
          <span className="kho-pager__page">
            {tab === "ton" ? `${pageTotal} vật tư` : `${pageTotal} phiếu`}
          </span>
          {tab === "ton" && canViewCost && groups.length > 0 && (
            <span className="kho-ton__value">
              Giá trị tồn: <b>{money(Math.round(totalValue))}</b>
            </span>
          )}
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

      {dcBulkOpen && (
        // Điều chuyển HÀNG LOẠT: các mã đã tick → gộp vào MỘT yêu cầu điều chuyển. Trừ tồn nguồn NGAY.
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
  // Ô Min/Max & badge Trạng thái bấm được (chỉ khi có quyền set_threshold) → mở popup đặt ngưỡng.
  // stopPropagation để KHÔNG kích hoạt onOpen (mở drawer chi tiết) của cả dòng.
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
  // Bấm dòng → mở popup lịch sử Nhập/Xuất (thay cho bung inline trước đây).
  // Ngày nhập: CHỈ hiện ngày nhập MỚI NHẤT (lô đã sort cũ→mới ở groups nên lô cuối là mới nhất).
  const newest = g.lots.length ? g.lots[g.lots.length - 1].ngay_nhap : null;
  // Vị trí: hiện tối đa 3 vị trí đầu (đã ưu tiên lô mới), dư K → " +K"; title = đủ danh sách.
  const viShown = g.viTris.slice(0, 3).join(", ");
  const viMore = g.viTris.length - 3;
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
        <div className="kho-lineimg">
          {g.anh
            ? <img className="kho-ton__thumb" src={assetUrl(g.anh) ?? undefined} alt="" loading="lazy" />
            : <span className="kho-ton__thumb kho-ton__thumb--ph" aria-hidden="true"><BoxIcon/></span>}
          <div className="kho-lineimg__txt">
            <div className="rc__name kho-ton__name" title={g.name ?? undefined}>{g.name ?? "—"}</div>
            {g.code && <div className="rc__muted kho-lines__code">{g.code}</div>}
          </div>
        </div>
      </td>
      <td title={g.viTris.length ? g.viTris.join(", ") : undefined}>
        {g.viTris.length === 0 ? (
          <span className="rc__muted">—</span>
        ) : (
          <span className="kho-ton__vitri">
            {viShown}
            {viMore > 0 ? <span className="kho-ton__vtmore"> +{viMore}</span> : null}
          </span>
        )}
      </td>
      <td className="kho-num kho-ton__total">
        {fmtQty(g.total)}
        {g.dvt ? <span className="kho-ton__dvt"> {g.dvt}</span> : null}
      </td>
      <td className="kho-num kho-ton__lots-n">{g.lots.length}</td>
      <td
        {...(setThProps
          ? { ...setThProps, className: `kho-num ${setThProps.className}` }
          : { className: "kho-num" })}
      >
        {threshold == null ? (
          <span className="rc__muted">— / —</span>
        ) : (
          <>
            {threshold.nguong_ton != null ? fmtQty(threshold.nguong_ton) : "—"} /{" "}
            {threshold.nguong_toi_da != null ? fmtQty(threshold.nguong_toi_da) : "—"}
          </>
        )}
      </td>
      <td {...(setThProps ?? {})}>
        {/* Cột tên là "Trạng thái" → chưa khai ngưỡng hiện chip xám "Chưa khai" (không để trống). */}
        {g.level ? (
          <StockLevelChip level={g.level} />
        ) : (
          <span className="kho-ton__unset">Chưa khai</span>
        )}
      </td>
      <td className="kho-ton__date">
        {newest == null ? <span className="rc__muted">—</span> : fmtDateISO(newest)}
      </td>
      {canViewCost && <td className="kho-num kho-ton__val">{money(Math.round(g.value))}</td>}
    </tr>
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
  const [tab, setTab] = useState<"tong_quan" | "nhap" | "xuat">("tong_quan");
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
  const nhapPaged = nhap.slice((page - 1) * DRAWER_PAGE, page * DRAWER_PAGE);
  const xuatPaged = xuat.slice((page - 1) * DRAWER_PAGE, page * DRAWER_PAGE);

  return (
    <>
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer rc-drawer--mid" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">LỊCH SỬ NHẬP / XUẤT</div>
            <h2 className="rc-drawer__title">{material.name ?? material.code ?? "—"}</h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
            {material.level && <StockLevelChip level={material.level} />}
            {/* Chuyển kho: chỉ khi có quyền lập phiếu, có kho đích, và mặt hàng còn tồn. Trừ tồn NGAY. */}
            {canCreate && khoDich.length > 0 && material.total > 0 && (
              <button
                type="button"
                className="rc__link-btn"
                onClick={() => setDcOpen(true)}
                title="Điều chuyển mặt hàng này sang kho khác"
              >
                ⇄ Chuyển kho
              </button>
            )}
            {/* Tem QR của vật tư — hiện ở MỌI tab (Tổng quan · Nhập · Xuất). */}
            <button
              type="button"
              className={`rc__link-btn${showQr ? " is-active" : ""}`}
              onClick={() => setShowQr((v) => !v)}
              aria-pressed={showQr}
              title="Tem QR vật tư — quét ra tồn & vị trí"
            >
              {showQr ? "▾ QR" : "▸ QR"}
            </button>
            <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
              ✕
            </button>
          </div>
        </header>

        {showQr && (
          // Tem QR: quét bằng điện thoại → mở TRANG TRA KHO CÔNG KHAI (tồn · vị trí · lịch sử). In dán kệ.
          <div className="kho-qr">
            {qrUrl ? (
              <div
                className="kho-qr__img"
                // qrSvg do chính ta sinh (không chứa dữ liệu người dùng) → an toàn.
                dangerouslySetInnerHTML={{ __html: qrSvg }}
              />
            ) : (
              <div className="kho-qr__img kho-qr__img--loading">Đang tạo mã…</div>
            )}
            <div className="kho-qr__side">
              <div className="kho-qr__note">
                Quét để xem tồn, vị trí &amp; lịch sử nhập/xuất của vật tư này (không cần đăng nhập).
              </div>
              {qrUrl && <div className="kho-qr__url">{qrUrl}</div>}
              <button type="button" className="rc__link-btn" onClick={printQr}>
                🖨 In tem
              </button>
            </div>
          </div>
        )}

        {(anh || canEditAnh) && (
          <div className="kho-anh">
            {anh ? (
              <button
                type="button"
                className="kho-anh__thumb"
                onClick={() => setZoom(true)}
                title="Bấm để phóng to"
              >
                <img src={assetUrl(anh) ?? undefined} alt={material.name ?? "Ảnh vật tư"} />
              </button>
            ) : (
              <div className="kho-anh__thumb kho-anh__thumb--empty" aria-hidden="true">
                <Icon name="camera" size={24} />
              </div>
            )}
            {canEditAnh && (
              <div className="kho-anh__actions">
                <label className={`rc__link-btn${anhBusy ? " is-disabled" : ""}`}>
                  {anh ? "Đổi ảnh" : "Thêm ảnh"}
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
                {anh && (
                  <button
                    type="button"
                    className="rc__link-btn kho-anh__del"
                    disabled={anhBusy}
                    onClick={() => void removeAnh()}
                  >
                    Xóa ảnh
                  </button>
                )}
                {anhBusy && <span className="kho-anh__hint">Đang lưu…</span>}
                {anhErr && <span className="kho-anh__err">{anhErr}</span>}
              </div>
            )}
          </div>
        )}

        <div className="kho-meta">
          {material.code ? `${material.code} · ` : ""}
          Tồn khả dụng: <b>{fmtQty(data?.on_hand ?? material.total)}</b>
          {material.dvt ? ` ${material.dvt}` : ""}
        </div>

        {/* NCC bán mặt hàng này — giá đã quy về ĐƠN VỊ GỐC nên so ngang được, rẻ nhất đứng đầu.
            "1.020.000 đ/ram" và "24.500 đ/kg" nhìn thẳng thì không so nổi. */}
        {soGia.length > 0 && (
          <div className="kho-meta" style={{ paddingTop: 0 }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>NCC bán mặt hàng này</div>
            <table className="rc__table rc__table--tight">
              <thead>
                <tr>
                  <th>Nhà cung cấp</th>
                  <th>Giá NCC báo</th>
                  <th style={{ textAlign: "right" }}>
                    Quy về {material.dvt ?? "đơn vị gốc"}
                  </th>
                </tr>
              </thead>
              <tbody>
                {soGia.map((s, i) => (
                  <tr key={s.supplier_item_id}>
                    <td>
                      {s.supplier_name}
                      {/* Chỉ gắn nhãn khi CÓ ít nhất 2 giá so được — một mình một chợ mà gọi
                          "rẻ nhất" là gợi ý sai. */}
                      {i === 0 && s.gia_quy_doi != null && soGia.length > 1 && (
                        <span className="badge-sem badge-sem--moss" style={{ marginLeft: 6 }}>
                          rẻ nhất
                        </span>
                      )}
                    </td>
                    <td className="rc__muted">
                      {s.unit_price.toLocaleString("vi-VN")} đ/{s.unit_ten ?? s.unit}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {s.gia_quy_doi != null ? (
                        <b>{s.gia_quy_doi.toLocaleString("vi-VN")} đ</b>
                      ) : (
                        <span className="rc__muted" title={s.ly_do ?? ""}>
                          — chưa quy đổi được
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Tab Nhập / Xuất — theo dõi nhập và xuất RIÊNG (spec màn Tồn kho). */}
        <div
          className="kho-shell__fns"
          style={{ padding: "0 var(--sp-5)", borderBottom: "1px solid var(--rule-hair)" }}
        >
          {(
            [
              ["tong_quan", "Tổng quan"],
              ["nhap", `Nhập (${nhap.length})`],
              ["xuat", `Xuất (${xuat.length})`],
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

        <div className="rc-drawer__body">
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
          ) : tab === "nhap" ? (
            nhap.length === 0 ? (
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
                          {lot.sl_de_nghi != null ? fmtQty(lot.sl_de_nghi) : "—"}
                        </td>
                        <td className="kho-num">{fmtQty(lot.sl_ban_dau)}</td>
                        {/* Vị trí là dữ liệu ĐÃ CHỐT sau ghi sổ → CHỈ hiển thị, không cho sửa. */}
                        <td>
                          <span className="kho-lines__code">{lot.vi_tri ?? "—"}</span>
                        </td>
                        {canViewCost && (
                          <td className="kho-num">{money(lot.don_gia_nhap ?? 0)}</td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          ) : xuat.length === 0 ? (
            <p className="kho-hint">Chưa có lần xuất nào cho vật tư này.</p>
          ) : (
            <div className="kho-lines__wrap">
              <table className="kho-lines">
                <thead>
                  <tr>
                    <th style={{ width: 96 }}>Ngày xuất</th>
                    <th style={{ width: 116 }}>Số phiếu</th>
                    {/* SL yêu cầu (số đã xin trên yêu cầu sinh ra dòng xuất) đứng TRƯỚC SL xuất thực tế. */}
                    <th className="kho-num">SL yêu cầu</th>
                    <th className="kho-num">SL xuất</th>
                    {canViewCost && <th className="kho-num">Giá vốn</th>}
                  </tr>
                </thead>
                <tbody>
                  {xuatPaged.map((r, i) => (
                    <tr key={`${r.voucher_id}-${r.lot_id}-${i}`}>
                      <td className="kho-lines__code">{fmtDateISO(r.ngay)}</td>
                      <td className="kho-lines__code">
                        <CodeLink
                          code={r.voucher_ma ?? "—"}
                          onOpen={() => onOpenVoucher(r.voucher_id)}
                        />
                      </td>
                      <td className="kho-num">
                        {r.sl_de_nghi != null ? fmtQty(r.sl_de_nghi) : "—"}
                      </td>
                      <td className="kho-num">{fmtQty(r.so_luong)}</td>
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
            (tab === "nhap" ? nhap.length : xuat.length) > DRAWER_PAGE && (
              <DrawerPager
                page={page}
                total={tab === "nhap" ? nhap.length : xuat.length}
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
  const loHetHang = lots.filter((l) => l.sl_con_lai <= 0).length;

  // Biểu đồ cột nhập/xuất theo tháng (12 tháng gần nhất) — SVG thuần.
  const monthlyChart = useMemo(() => {
    const buckets = new Map<string, { nhap: number; xuat: number }>();
    // Tạo 12 bucket tháng gần nhất.
    const now = new Date();
    for (let i = 11; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      buckets.set(key, { nhap: 0, xuat: 0 });
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
    return [...buckets.entries()].map(([key, v]) => ({ key, ...v }));
  }, [data]);

  const maxBar = Math.max(...monthlyChart.flatMap((m) => [m.nhap, m.xuat]), 1);

  // Chiều cao SVG
  const SVG_H = 80;
  const SVG_W = 360;
  const BAR_W = 10;
  const GAP = 4;
  const SLOT = BAR_W * 2 + GAP + 4;
  const totalSlots = monthlyChart.length;
  const chartW = totalSlots * SLOT;
  const offsetX = (SVG_W - chartW) / 2;

  return (
    <div className="kho-ov">
      {/* Hero số tồn + mức */}
      <div className="kho-ov__hero">
        <div className="kho-ov__big">
          {fmtQty(onHand)}
          {dvt ? <span className="kho-ov__dvt"> {dvt}</span> : null}
        </div>
        {level ? (
          <StockLevelChip level={level} />
        ) : (
          <span className="badge-sem badge-sem--muted">Chưa khai</span>
        )}
      </div>

      {/* Gauge ngưỡng */}
      {hasThreshold ? (
        <div className="kho-gauge" aria-hidden="true">
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
        <p className="kho-hint">Chưa khai ngưỡng cho vật tư này.</p>
      )}

      {/* Biểu đồ cột nhập/xuất 12 tháng */}
      {data != null && (totalNhap > 0 || totalXuat > 0) && (
        <div className="kho-ov__chart-wrap">
          <div className="kho-ov__chart-title">
            Nhập / Xuất 12 tháng gần nhất
          </div>
          <div className="kho-ov__chart-legend">
            <span className="kho-ov__legend-dot kho-ov__legend-dot--nhap" /> Nhập
            <span className="kho-ov__legend-dot kho-ov__legend-dot--xuat" style={{ marginLeft: 10 }} /> Xuất
          </div>
          <svg
            viewBox={`0 0 ${SVG_W} ${SVG_H + 18}`}
            width="100%"
            aria-label="Biểu đồ nhập xuất 12 tháng"
            style={{ overflow: "visible" }}
          >
            {/* Grid lines */}
            {[0, 0.5, 1].map((f) => (
              <line
                key={f}
                x1={0} y1={SVG_H * (1 - f)}
                x2={SVG_W} y2={SVG_H * (1 - f)}
                stroke="var(--rule-hair)"
                strokeWidth={1}
              />
            ))}
            {monthlyChart.map((m, i) => {
              const x = offsetX + i * SLOT;
              const nhapH = (m.nhap / maxBar) * SVG_H;
              const xuatH = (m.xuat / maxBar) * SVG_H;
              const label = m.key.slice(5); // "MM"
              return (
                <g key={m.key}>
                  {/* Cột Nhập — xanh rêu */}
                  {nhapH > 0 && (
                    <rect
                      x={x}
                      y={SVG_H - nhapH}
                      width={BAR_W}
                      height={nhapH}
                      fill="var(--moss)"
                      rx={2}
                      opacity={0.85}
                    >
                      <title>Nhập {fmtQty(m.nhap)} ({m.key})</title>
                    </rect>
                  )}
                  {/* Cột Xuất — rust */}
                  {xuatH > 0 && (
                    <rect
                      x={x + BAR_W + 2}
                      y={SVG_H - xuatH}
                      width={BAR_W}
                      height={xuatH}
                      fill="var(--rust)"
                      rx={2}
                      opacity={0.75}
                    >
                      <title>Xuất {fmtQty(m.xuat)} ({m.key})</title>
                    </rect>
                  )}
                  {/* Nhãn tháng */}
                  <text
                    x={x + BAR_W}
                    y={SVG_H + 14}
                    textAnchor="middle"
                    fontSize={9}
                    fill="var(--ash)"
                    fontFamily="var(--ff-sans)"
                  >
                    {label}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      )}

      {/* Lưới chỉ số */}
      <dl className="kho-ov__grid">
        <div className="kho-ov__cell">
          <dt>Số đợt nhập</dt>
          <dd>{fmtQty(lots.length)}</dd>
        </div>
        <div className="kho-ov__cell">
          <dt>Ngày nhập gần nhất</dt>
          <dd>{newest ? fmtDateISO(newest) : "—"}</dd>
        </div>
        <div className="kho-ov__cell">
          <dt>Tổng đã nhập</dt>
          <dd>{fmtQty(totalNhap)}{dvt ? ` ${dvt}` : ""}</dd>
        </div>
        <div className="kho-ov__cell">
          <dt>Tổng đã xuất</dt>
          <dd>{fmtQty(totalXuat)}{dvt ? ` ${dvt}` : ""}</dd>
        </div>
        <div className="kho-ov__cell">
          <dt>Ngưỡng</dt>
          <dd>
            {hasThreshold
              ? `Min ${min != null ? fmtQty(min) : "—"} / Max ${max != null ? fmtQty(max) : "—"}`
              : "Chưa khai ngưỡng"}
          </dd>
        </div>
        {loHetHang > 0 && (
          <div className="kho-ov__cell">
            <dt>Lô đã hết hàng</dt>
            <dd style={{ color: "var(--ash)" }}>{loHetHang} lô</dd>
          </div>
        )}
        <div className="kho-ov__cell kho-ov__cell--wide">
          <dt>Vị trí</dt>
          <dd>{viTris.length ? viTris.join(", ") : "—"}</dd>
        </div>
        {canViewCost && (
          <>
            <div className="kho-ov__cell">
              <dt>Giá trị tồn</dt>
              <dd>{money(Math.round(value))}</dd>
            </div>
            <div className="kho-ov__cell">
              <dt>Giá vốn bình quân</dt>
              <dd>{onHand > 0 ? `${money(Math.round(avgCost))}${dvt ? ` /${dvt}` : ""}` : "—"}</dd>
            </div>
          </>
        )}
        {hsdSoonest && (
          <div className="kho-ov__cell">
            <dt>HSD gần nhất</dt>
            <dd>{fmtDateISO(hsdSoonest)}</dd>
          </div>
        )}
      </dl>
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

const SearchIcon = () => (
  <svg
    width="15"
    height="15"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="rc__search-icon"
  >
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.3-4.3" />
  </svg>
);

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
