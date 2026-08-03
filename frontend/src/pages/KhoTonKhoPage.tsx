// Màn "Kho hàng" của MỘT kho vật lý — bấm 1 kho dưới section "Kho hàng" trên navbar.
//
// Đây là VIỆC CỦA KHO (chỉ ai có `can_view_stock` mới thấy — gate ở AppShell). Gồm 2 tab:
//   • Tồn kho:  gom lô theo VẬT TƯ, bung xem từng lô (tồn = Σ sl_con_lai, spec §6).
//   • Phiếu kho: phiếu nhập/xuất ĐÃ LẬP tại kho này (chuyển vào đây thay vì ở Hộp yêu cầu — phiếu
//     là chứng từ của kho, nên nằm cùng chỗ với tồn/ngưỡng).
// Nút "Ngưỡng tồn" cũng nằm ở đây (không ở màn đề nghị) vì ngưỡng gắn với kho vật lý.
// Giá vốn CHỈ hiện với `can_view_cost` — thiếu quyền thì cột giá biến mất (ẩn cột, không "—").
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  type StockLevel,
  type StockLot,
  type StockMaterialHistory,
  type StockRequestKind,
  type StockThreshold,
  type StockVoucher,
  type StockVoucherStatus,
} from "../api/client";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { CodeLink } from "../components/CodeLink";
import { Select } from "../components/Select";
import { StockLevelChip } from "../components/StockLevelChip";
import type { NavigateFn } from "../components/AppShell";
import { fmtDateISO, money } from "../utils/format";
import { qrToSvg } from "../lib/qr";
import { VoucherStatusBadge, fmtQty } from "./khoShared";
import {
  InboxRequestDrawer,
  ThresholdDrawer,
  VoucherDrawer,
  type KhoOption,
} from "./KhoYeuCauPage";
import "./rebuild-catalog.css";
import "./kho-request.css";

interface MaterialGroup {
  material_id: number;
  code: string | null;
  name: string | null;
  dvt: string | null;
  total: number;
  value: number; // Σ sl_con_lai × đơn giá — chỉ có nghĩa khi thấy giá
  lots: StockLot[];
  // Mức tồn 5 màu so với ngưỡng đã khai. null = chưa khai ngưỡng cho mã này ở kho này.
  level: StockLevel | null;
}

type TonTab = "ton" | "phieu";

const PAGE_SIZE = 20;
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
  openMaterialId = null,
}: {
  khoId: number;
  ten: string;
  ma?: string;
  token: string;
  navigate: NavigateFn;
  /** Deep-link tem QR: mở thẳng drawer lô + vị trí của vật tư này khi tồn đã tải xong. */
  openMaterialId?: number | null;
}) {
  const can = useCan();
  const canViewCost = can("kho", "view_cost");
  const canCreate = can("kho", "create");
  const canPost = can("kho", "post");
  const canSetThreshold = can("kho", "set_threshold");

  const [tab, setTab] = useState<TonTab>("ton");
  const [lots, setLots] = useState<StockLot[]>([]);
  const [thresholds, setThresholds] = useState<Record<number, StockThreshold>>({});
  const [vouchers, setVouchers] = useState<StockVoucher[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingV, setLoadingV] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  // Vật tư đang mở popup lịch sử Nhập/Xuất (thay cho bung inline).
  const [openMaterial, setOpenMaterial] = useState<MaterialGroup | null>(null);
  // Mã đã tick để tạo Yêu cầu mua hàng (chỉ tab Tồn kho).
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [voucherFilter, setVoucherFilter] = useState<"all" | StockVoucherStatus>("all");
  const [voucherLoai, setVoucherLoai] = useState<"all" | StockRequestKind>("all");
  const [page, setPage] = useState(1);
  const [openVoucher, setOpenVoucher] = useState<number | null>(null);
  const [openRequest, setOpenRequest] = useState<number | null>(null);
  const [thresholdOpen, setThresholdOpen] = useState(false);
  // Bộ lọc tab Tồn kho (client-side): khoảng ngày nhập (khớp bất kỳ lô nào) + khoảng tồn.
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [tonFrom, setTonFrom] = useState("");
  const [tonTo, setTonTo] = useState("");
  const [filterOpen, setFilterOpen] = useState(false);
  const filterRef = useRef<HTMLDivElement | null>(null);

  // Kho đơn lẻ cho ThresholdDrawer (nó cần danh sách kho cho ô chọn — ở đây khoá đúng 1 kho).
  const khoOne: KhoOption[] = useMemo(
    () => [{ id: khoId, ma: ma ?? "", ten }],
    [khoId, ma, ten],
  );

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      api.kho.phieu.danhSachLo(token, { kho_id: khoId, con_hang: true }),
      // Ngưỡng tồn để so tồn → đèn cảnh báo. Lỗi/thiếu quyền set_threshold vẫn xem được tồn.
      api.kho.nguongTon.list(token).catch(() => [] as StockThreshold[]),
    ])
      .then(([r, ths]) => {
        setLots(r);
        const map: Record<number, StockThreshold> = {};
        for (const t of ths) if (t.kho_id === khoId) map[t.material_id] = t;
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

  // Về trang 1 khi đổi tab / tìm kiếm / lọc phiếu / lọc ngày-tồn.
  useEffect(() => {
    setPage(1);
  }, [tab, q, voucherFilter, voucherLoai, dateFrom, dateTo, tonFrom, tonTo]);

  // Đóng popover Lọc khi bấm ra ngoài / nhấn Esc.
  useEffect(() => {
    if (!filterOpen) return;
    const onDown = (e: MouseEvent) => {
      if (filterRef.current && !filterRef.current.contains(e.target as Node)) setFilterOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFilterOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [filterOpen]);

  const groups = useMemo<MaterialGroup[]>(() => {
    const m = new Map<number, MaterialGroup>();
    for (const lot of lots) {
      let g = m.get(lot.material_id);
      if (!g) {
        g = {
          material_id: lot.material_id,
          code: lot.material_code,
          name: lot.material_name,
          dvt: lot.dvt,
          total: 0,
          value: 0,
          lots: [],
          level: null,
        };
        m.set(lot.material_id, g);
      }
      g.total += lot.sl_con_lai;
      g.value += lot.sl_con_lai * (lot.don_gia_nhap ?? 0);
      g.lots.push(lot);
    }
    const arr = [...m.values()];
    for (const g of arr) {
      // Lô trong mỗi nhóm: nhập trước lên trước (FIFO), để đọc lịch sử nhập tự nhiên.
      g.lots.sort((a, b) => a.ngay_nhap.localeCompare(b.ngay_nhap));
      g.level = levelOf(g.total, thresholds[g.material_id]);
    }
    return arr.sort((a, b) => (a.name ?? "").localeCompare(b.name ?? "", "vi"));
  }, [lots, thresholds]);

  // Deep-link tem QR: khi có openMaterialId + tồn đã tải → bung drawer đúng vật tư (1 lần cho mỗi
  // id, ref chặn mở lại sau khi người dùng đóng).
  const deepLinkedId = useRef<number | null>(null);
  useEffect(() => {
    if (!openMaterialId || deepLinkedId.current === openMaterialId) return;
    const g = groups.find((x) => x.material_id === openMaterialId);
    if (!g) return;
    deepLinkedId.current = openMaterialId;
    setOpenMaterial(g);
  }, [openMaterialId, groups]);

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
      return true;
    });
  }, [groups, q, dateFrom, dateTo, tonFrom, tonTo]);

  const shownVouchers = useMemo(() => {
    const s = q.trim().toLowerCase();
    return vouchers
      .filter((v) => voucherLoai === "all" || v.loai === voucherLoai)
      .filter((v) => voucherFilter === "all" || v.trang_thai === voucherFilter)
      .filter(
        (v) =>
          !s ||
          v.ma.toLowerCase().includes(s) ||
          (v.request_ma ?? "").toLowerCase().includes(s) ||
          // Tìm cả theo TÊN / MÃ vật tư đi trong phiếu (khớp bất kỳ dòng nào).
          v.lines.some(
            (l) =>
              (l.material_name ?? "").toLowerCase().includes(s) ||
              (l.material_code ?? "").toLowerCase().includes(s),
          ),
      );
  }, [vouchers, voucherLoai, voucherFilter, q]);

  function toggleSel(id: number) {
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

  // Bộ lọc đang bật (để hiện badge số + pill + empty state).
  const hasDateFilter = dateFrom !== "" || dateTo !== "";
  const hasTonFilter = tonFrom !== "" || tonTo !== "";
  const activeFilters = (hasDateFilter ? 1 : 0) + (hasTonFilter ? 1 : 0);
  function clearFilters() {
    setDateFrom("");
    setDateTo("");
    setTonFrom("");
    setTonTo("");
  }

  // Tạo Yêu cầu mua hàng từ các mã đã tick: mở form YCMH (nguồn Kho) điền sẵn Tên + ĐVT,
  // để trống SL + ghi chú cho người dùng nhập.
  function createPurchaseFromSelected() {
    const chosen = groups.filter((g) => selected.has(g.material_id));
    if (chosen.length === 0) return;
    navigate("yeu-cau-mua-hang", {
      purchaseSeedLines: chosen.map((g) => ({
        item_name: g.name ?? g.code ?? "",
        unit: g.dvt ?? "",
        quantity: 0,
        note: "",
      })),
      purchaseSeedPurpose: `Bổ sung tồn kho ${ten}`,
    });
  }

  const voucherCols = canViewCost ? 7 : 6;
  // Cột tab Tồn kho: [checkbox nếu canCreate] + Vật tư + Mức + Tồn + Số lô + Ngày nhập
  // [+ Ngưỡng (gộp tồn–tối đa) nếu set_threshold] [+ Giá trị nếu view_cost].
  const tonCols =
    (canCreate ? 1 : 0) + 5 + (canSetThreshold ? 1 : 0) + (canViewCost ? 1 : 0);

  // Phân trang (dùng chung cho cả 2 tab; số tổng theo tab đang xem).
  const pageTotal = tab === "ton" ? filtered.length : shownVouchers.length;
  const maxPage = Math.max(1, Math.ceil(pageTotal / PAGE_SIZE));
  const pagedGroups = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const pagedVouchers = shownVouchers.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <main className="rc kho-list">
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">{ten}</h1>
          <span className="rc__count">
            {tab === "ton"
              ? `${groups.length} vật tư đang tồn`
              : `${vouchers.length} phiếu`}
            {ma ? ` · ${ma}` : ""}
          </span>
        </div>
        <p className="rc__sub">
          {tab === "ton"
            ? "Tồn khả dụng theo từng vật tư — bấm một dòng để xem chi tiết các lô."
            : "Phiếu nhập/xuất đã lập tại kho này."}
        </p>
      </header>

      <div className="kho-shell">
        <div className="kho-shell__fns">
          {(
            [
              ["ton", "Tồn kho"],
              ["phieu", "Phiếu kho"],
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
              tab === "ton" ? "Tìm mã / tên vật tư…" : "Tìm số phiếu / mã đề nghị / tên vật tư…"
            }
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        {tab === "phieu" && (
          <>
            <div className="kho-picker">
              <Select
                options={[
                  { value: "all", label: "Nhập & Xuất", hint: String(vouchers.length) },
                  {
                    value: "NHAP",
                    label: "Nhập",
                    hint: String(vouchers.filter((v) => v.loai === "NHAP").length),
                  },
                  {
                    value: "XUAT",
                    label: "Xuất",
                    hint: String(vouchers.filter((v) => v.loai === "XUAT").length),
                  },
                ]}
                value={voucherLoai}
                onChange={(v) => v != null && setVoucherLoai(v as "all" | StockRequestKind)}
                ariaLabel="Lọc nhập/xuất"
              />
            </div>
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
        {tab === "ton" && (
          <div className="kho-filter" ref={filterRef}>
            <Button
              variant="secondary"
              className={`kho-filter__btn${activeFilters > 0 ? " is-active" : ""}`}
              onClick={() => setFilterOpen((o) => !o)}
              aria-expanded={filterOpen}
            >
              <FilterIcon />
              Lọc
              {activeFilters > 0 && <span className="kho-filter__count">{activeFilters}</span>}
            </Button>
            {filterOpen && (
              <div className="kho-filter__pop" role="dialog" aria-label="Bộ lọc tồn kho">
                <div className="kho-filter__sec">
                  <div className="kho-filter__lbl">Ngày nhập</div>
                  <div className="kho-daterange">
                    <input
                      type="date"
                      className="rc-input"
                      value={dateFrom}
                      max={dateTo || undefined}
                      onChange={(e) => setDateFrom(e.target.value)}
                      aria-label="Ngày nhập từ"
                    />
                    <span className="kho-daterange__sep">–</span>
                    <input
                      type="date"
                      className="rc-input"
                      value={dateTo}
                      min={dateFrom || undefined}
                      onChange={(e) => setDateTo(e.target.value)}
                      aria-label="Ngày nhập đến"
                    />
                  </div>
                </div>
                <div className="kho-filter__sec">
                  <div className="kho-filter__lbl">Tồn khả dụng</div>
                  <div className="kho-daterange">
                    <input
                      type="number"
                      className="rc-input kho-num"
                      placeholder="từ"
                      value={tonFrom}
                      onChange={(e) => setTonFrom(e.target.value)}
                      aria-label="Tồn từ"
                    />
                    <span className="kho-daterange__sep">–</span>
                    <input
                      type="number"
                      className="rc-input kho-num"
                      placeholder="đến"
                      value={tonTo}
                      onChange={(e) => setTonTo(e.target.value)}
                      aria-label="Tồn đến"
                    />
                  </div>
                </div>
                <div className="kho-filter__foot">
                  <button
                    type="button"
                    className="btn btn--ghost"
                    disabled={activeFilters === 0}
                    onClick={clearFilters}
                  >
                    Xóa lọc
                  </button>
                  <button
                    type="button"
                    className="btn btn--secondary"
                    onClick={() => setFilterOpen(false)}
                  >
                    Xong
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
        <div className="rc__spacer" />
        {canSetThreshold && (
          <Button variant="secondary" onClick={() => setThresholdOpen(true)}>
            Ngưỡng tồn
          </Button>
        )}
      </div>

      {/* Pill các bộ lọc đang bật — chỉ tab Tồn kho. */}
      {tab === "ton" && activeFilters > 0 && (
        <div className="kho-filterbar">
          {hasDateFilter && (
            <span className="kho-filterpill">
              Ngày nhập: {dateFrom ? fmtDateISO(dateFrom) : "…"} – {dateTo ? fmtDateISO(dateTo) : "…"}
              <button
                type="button"
                className="kho-filterpill__x"
                aria-label="Bỏ lọc ngày nhập"
                onClick={() => {
                  setDateFrom("");
                  setDateTo("");
                }}
              >
                ✕
              </button>
            </span>
          )}
          {hasTonFilter && (
            <span className="kho-filterpill">
              Tồn: {tonFrom !== "" ? fmtQty(Number(tonFrom)) : "…"} –{" "}
              {tonTo !== "" ? fmtQty(Number(tonTo)) : "…"}
              <button
                type="button"
                className="kho-filterpill__x"
                aria-label="Bỏ lọc khoảng tồn"
                onClick={() => {
                  setTonFrom("");
                  setTonTo("");
                }}
              >
                ✕
              </button>
            </span>
          )}
          <button type="button" className="kho-filterbar__clear" onClick={clearFilters}>
            Xóa lọc
          </button>
        </div>
      )}

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
              onClick={() => setSelected(new Set(canMua.map((g) => g.material_id)))}
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
          <Button variant="accent" onClick={createPurchaseFromSelected}>
            Tạo yêu cầu mua
          </Button>
        </div>
      )}

      <div className="rc__tablewrap kho-tablewrap">
        {tab === "ton" ? (
          <table className="rc__table kho-table">
            <thead>
              <tr>
                {canCreate && (
                  <th style={{ width: 34 }}>
                    <input
                      type="checkbox"
                      aria-label="Chọn tất cả"
                      checked={filtered.length > 0 && filtered.every((g) => selected.has(g.material_id))}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? new Set(filtered.map((g) => g.material_id))
                            : new Set(),
                        )
                      }
                    />
                  </th>
                )}
                <th>Vật tư</th>
                <th style={{ width: "12%" }}>Mức</th>
                <th className="kho-num" style={{ width: "15%" }}>
                  Tồn khả dụng
                </th>
                <th className="kho-num" style={{ width: "9%" }}>
                  Số lô
                </th>
                <th className="kho-num" style={{ width: "13%" }}>
                  Ngày nhập
                </th>
                {canSetThreshold && (
                  <th className="kho-num" style={{ width: "16%" }}>
                    Ngưỡng
                  </th>
                )}
                {canViewCost && (
                  <th className="kho-num" style={{ width: "16%" }}>
                    Giá trị tồn
                  </th>
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
                    key={g.material_id}
                    g={g}
                    canViewCost={canViewCost}
                    selectable={canCreate}
                    checked={selected.has(g.material_id)}
                    onToggleSel={() => toggleSel(g.material_id)}
                    onOpen={() => setOpenMaterial(g)}
                    canSetThreshold={canSetThreshold}
                    threshold={thresholds[g.material_id]}
                  />
                ))
              )}
            </tbody>
          </table>
        ) : (
          <table className="rc__table kho-table">
            <thead>
              <tr>
                <th style={{ width: "14%" }}>Số phiếu</th>
                <th style={{ width: "8%" }}>Loại</th>
                <th style={{ width: "13%" }}>Theo đề nghị</th>
                <th style={{ width: "16%" }}>Người (lập · duyệt)</th>
                <th style={{ width: "12%" }}>Ngày</th>
                <th className="kho-num" style={{ width: "12%" }}>
                  Dòng / Σ SL
                </th>
                {canViewCost && (
                  <th className="kho-num" style={{ width: "14%" }}>
                    Giá vốn
                  </th>
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
                          ? "Chưa có phiếu kho nào ở kho này. Phiếu được lập từ một đề nghị đã duyệt."
                          : "Không có phiếu nào khớp bộ lọc."}
                      </p>
                      {vouchers.length > 0 && (
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() => {
                            setQ("");
                            setVoucherFilter("all");
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
                      <td>
                        <span
                          className={`badge-sem badge-sem--${v.loai === "NHAP" ? "moss" : "plum"}`}
                        >
                          {v.loai === "NHAP" ? "NHẬP" : "XUẤT"}
                        </span>
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
                        <div className="rc__muted kho-hint">
                          {v.nguoi_duyet_ten ? `Duyệt: ${v.nguoi_duyet_ten}` : "—"}
                        </div>
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
          key={`mat-${openMaterial.material_id}`}
          token={token}
          khoId={khoId}
          material={openMaterial}
          canViewCost={canViewCost}
          canCreate={canCreate}
          onOpenVoucher={setOpenVoucher}
          onClose={() => setOpenMaterial(null)}
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
        // Chỉ ĐỌC: mở đề nghị gốc từ mã "Theo đề nghị". Lập phiếu vẫn làm ở Hộp yêu cầu, nên
        // canCreate=false (ẩn nút Lập phiếu / Tiếp nhận / Chuẩn bị).
        <InboxRequestDrawer
          key={`req-${openRequest}`}
          token={token}
          khoId={khoId}
          requestId={openRequest}
          canCreate={false}
          onClose={() => setOpenRequest(null)}
          onCreateVoucher={() => {}}
        />
      )}

      {thresholdOpen && (
        <ThresholdDrawer
          token={token}
          khoList={khoOne}
          initialKhoId={khoId}
          // Đóng drawer → nạp lại tồn + ngưỡng để cột Mức/cảnh báo cập nhật ngay.
          onClose={() => {
            setThresholdOpen(false);
            load();
          }}
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
  materialId: number,
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
    const { token } = await api.kho.phieu.qrToken(authToken, khoId, materialId);
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
  canSetThreshold,
  threshold,
}: {
  g: MaterialGroup;
  canViewCost: boolean;
  selectable: boolean;
  checked: boolean;
  onToggleSel: () => void;
  onOpen: () => void;
  canSetThreshold: boolean;
  threshold: StockThreshold | undefined;
}) {
  // Bấm dòng → mở popup lịch sử Nhập/Xuất (thay cho bung inline trước đây).
  // Ngày nhập (lô đã sort cũ→mới ở groups): 1 lô → 1 ngày; nhiều lô → khoảng cũ→mới.
  const oldest = g.lots.length ? g.lots[0].ngay_nhap : null;
  const newest = g.lots.length ? g.lots[g.lots.length - 1].ngay_nhap : null;
  const oneDay =
    oldest != null && newest != null && oldest.slice(0, 10) === newest.slice(0, 10);
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
        <div className="rc__name">{g.name ?? "—"}</div>
        {g.code && <div className="rc__muted kho-lines__code">{g.code}</div>}
      </td>
      <td>
        {/* Chưa khai ngưỡng → không đèn (không cảnh báo bừa). */}
        {g.level ? <StockLevelChip level={g.level} /> : <span className="rc__muted">—</span>}
      </td>
      <td className="kho-num kho-ton__total">{fmtQty(g.total)}</td>
      <td className="kho-num">{g.lots.length}</td>
      <td className="kho-ton__date">
        {oldest == null ? (
          <span className="rc__muted">—</span>
        ) : oneDay ? (
          fmtDateISO(oldest)
        ) : (
          <>
            {fmtDateISO(oldest)}
            <span className="kho-ton__arrow">→</span>
            {fmtDateISO(newest)}
          </>
        )}
      </td>
      {canSetThreshold && (
        <td className="kho-num">
          {threshold?.nguong_ton == null && threshold?.nguong_toi_da == null ? (
            <span className="rc__muted">—</span>
          ) : (
            `${threshold?.nguong_ton != null ? fmtQty(threshold.nguong_ton) : "—"}–${
              threshold?.nguong_toi_da != null ? fmtQty(threshold.nguong_toi_da) : "—"
            }`
          )}
        </td>
      )}
      {canViewCost && <td className="kho-num">{money(Math.round(g.value))}</td>}
    </tr>
  );
}

function MaterialHistoryDrawer({
  token,
  khoId,
  material,
  canViewCost,
  canCreate,
  onOpenVoucher,
  onClose,
}: {
  token: string;
  khoId: number;
  material: MaterialGroup;
  canViewCost: boolean;
  canCreate: boolean;
  onOpenVoucher: (voucherId: number) => void;
  onClose: () => void;
}) {
  const [data, setData] = useState<StockMaterialHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"nhap" | "xuat">("nhap");
  const [page, setPage] = useState(1);
  // Sửa VỊ TRÍ cất lô (kệ/ô): ẩn sau nút "+"; bấm mới hiện ô nhập + nút Lưu.
  const [editViTriId, setEditViTriId] = useState<number | null>(null);
  const [draftViTri, setDraftViTri] = useState("");
  // Tem QR vật tư: quét ra TRANG TRA KHO CÔNG KHAI (không đăng nhập) qua token đã ký "#s=..".
  const [showQr, setShowQr] = useState(false);
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  // Lấy token ký khi mở panel QR lần đầu (mint cần đăng nhập → dùng chính token phiên).
  useEffect(() => {
    if (!showQr || qrUrl) return;
    let alive = true;
    api.kho.phieu
      .qrToken(token, khoId, material.material_id)
      .then(({ token: t }) => {
        if (alive) setQrUrl(`${window.location.origin}/#s=${t}`);
      })
      .catch(() => {
        /* lỗi mạng/quyền — panel hiện trạng thái đang tạo; nút In tem vẫn tự lấy token khi bấm */
      });
    return () => {
      alive = false;
    };
  }, [showQr, qrUrl, token, khoId, material.material_id]);
  // border 4 = quiet-zone chuẩn (đủ khoảng trắng để máy quét bắt được, kể cả khi in nhỏ).
  const qrSvg = useMemo(() => (qrUrl ? qrToSvg(qrUrl, { border: 4 }) : ""), [qrUrl]);

  // In tem = hàm dùng chung (giống nút QR trên từng hàng Tồn kho). Tự lấy token ký rồi in.
  function printQr() {
    void printMaterialQr(token, khoId, material.material_id, material.code, material.name);
  }

  async function saveViTri(lotId: number, viTri: string) {
    const v = viTri.trim() || null;
    try {
      await api.kho.phieu.suaViTriLo(token, lotId, v);
      setData((d) =>
        d
          ? { ...d, nhap: d.nhap.map((lot) => (lot.id === lotId ? { ...lot, vi_tri: v } : lot)) }
          : d,
      );
      setEditViTriId(null);
    } catch {
      /* lỗi quyền/mạng — giữ nguyên; ô về giá trị cũ khi mở lại drawer */
    }
  }

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.kho.phieu
      .lichSuVatTu(token, material.material_id, khoId)
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
  }, [token, khoId, material.material_id]);

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
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer rc-drawer--mid" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">LỊCH SỬ NHẬP / XUẤT</div>
            <h2 className="rc-drawer__title">{material.name ?? material.code ?? "—"}</h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
            {material.level && <StockLevelChip level={material.level} />}
            {/* QR gắn với LÔ nhập (vị trí lô) → chỉ hiện ở tab Nhập. */}
            {tab === "nhap" && (
              <button
                type="button"
                className={`rc__link-btn${showQr ? " is-active" : ""}`}
                onClick={() => setShowQr((v) => !v)}
                aria-pressed={showQr}
                title="Tem QR vật tư — quét ra lô & vị trí"
              >
                {showQr ? "▾ QR" : "▸ QR"}
              </button>
            )}
            <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
              ✕
            </button>
          </div>
        </header>

        {showQr && tab === "nhap" && (
          // Tem QR: quét bằng điện thoại → mở TRANG TRA KHO CÔNG KHAI (lô + vị trí). In để dán kệ.
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
                Quét để xem lô &amp; vị trí của vật tư này (không cần đăng nhập).
              </div>
              {qrUrl && <div className="kho-qr__url">{qrUrl}</div>}
              <button type="button" className="rc__link-btn" onClick={printQr}>
                🖨 In tem
              </button>
            </div>
          </div>
        )}

        <div className="kho-meta">
          {material.code ? `${material.code} · ` : ""}
          Tồn khả dụng: <b>{fmtQty(data?.on_hand ?? material.total)}</b>
          {material.dvt ? ` ${material.dvt}` : ""}
        </div>

        {/* Tab Nhập / Xuất — theo dõi nhập và xuất RIÊNG (spec màn Tồn kho). */}
        <div
          className="kho-shell__fns"
          style={{ padding: "0 var(--sp-5)", borderBottom: "1px solid var(--rule-hair)" }}
        >
          {(
            [
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
          ) : tab === "nhap" ? (
            nhap.length === 0 ? (
              <p className="kho-hint">Chưa có lô nhập nào cho vật tư này.</p>
            ) : (
              <div className="kho-lines__wrap">
                <table className="kho-lines">
                  <thead>
                    <tr>
                      <th style={{ minWidth: 150 }}>Mã lô</th>
                      <th style={{ width: 96 }}>Ngày nhập</th>
                      <th className="kho-num">SL nhập</th>
                      <th className="kho-num">Còn</th>
                      <th style={{ minWidth: 96 }}>Vị trí</th>
                      {canViewCost && <th className="kho-num">Đơn giá</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {nhapPaged.map((lot) => (
                      <tr key={lot.id}>
                        <td className="kho-lines__code">
                          {lot.voucher_id != null ? (
                            <CodeLink
                              code={lot.ma_lo}
                              onOpen={() => onOpenVoucher(lot.voucher_id!)}
                            />
                          ) : (
                            lot.ma_lo
                          )}
                        </td>
                        <td className="kho-lines__code">{fmtDateISO(lot.ngay_nhap)}</td>
                        <td className="kho-num">{fmtQty(lot.sl_ban_dau)}</td>
                        <td className="kho-num">{fmtQty(lot.sl_con_lai)}</td>
                        <td>
                          {!canCreate ? (
                            <span className="kho-lines__code">{lot.vi_tri ?? "—"}</span>
                          ) : editViTriId === lot.id ? (
                            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                              <input
                                className="rc-input"
                                style={{ width: 90, padding: "4px 8px" }}
                                value={draftViTri}
                                autoFocus
                                placeholder="Kệ/ô"
                                onChange={(e) => setDraftViTri(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") void saveViTri(lot.id, draftViTri);
                                  if (e.key === "Escape") setEditViTriId(null);
                                }}
                                aria-label={`Vị trí lô ${lot.ma_lo}`}
                              />
                              <button
                                type="button"
                                className="btn btn--accent"
                                style={{ height: 28, padding: "2px 10px" }}
                                onClick={() => void saveViTri(lot.id, draftViTri)}
                              >
                                Lưu
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className="rc__link-btn"
                              onClick={() => {
                                setDraftViTri(lot.vi_tri ?? "");
                                setEditViTriId(lot.id);
                              }}
                            >
                              {lot.vi_tri ? lot.vi_tri : "+ Vị trí"}
                            </button>
                          )}
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
                    <th style={{ minWidth: 140 }}>Từ lô</th>
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
                      <td className="kho-lines__code">{r.ma_lo ?? "—"}</td>
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

const FilterIcon = () => (
  <svg
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
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
