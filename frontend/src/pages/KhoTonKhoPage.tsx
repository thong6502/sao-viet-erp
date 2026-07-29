// Màn "Kho hàng" của MỘT kho vật lý — bấm 1 kho dưới section "Kho hàng" trên navbar.
//
// Đây là VIỆC CỦA KHO (chỉ ai có `can_view_stock` mới thấy — gate ở AppShell). Gồm 2 tab:
//   • Tồn kho:  gom lô theo VẬT TƯ, bung xem từng lô (tồn = Σ sl_con_lai, spec §6).
//   • Phiếu kho: phiếu nhập/xuất ĐÃ LẬP tại kho này (chuyển vào đây thay vì ở Hộp yêu cầu — phiếu
//     là chứng từ của kho, nên nằm cùng chỗ với tồn/ngưỡng).
// Nút "Ngưỡng tồn" cũng nằm ở đây (không ở màn đề nghị) vì ngưỡng gắn với kho vật lý.
// Giá vốn CHỈ hiện với `can_view_cost` — thiếu quyền thì cột giá biến mất (ẩn cột, không "—").
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type StockLevel,
  type StockLot,
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
}: {
  khoId: number;
  ten: string;
  ma?: string;
  token: string;
  navigate: NavigateFn;
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
  const [open, setOpen] = useState<Set<number>>(new Set());
  // Mã đã tick để tạo Yêu cầu mua hàng (chỉ tab Tồn kho).
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [voucherFilter, setVoucherFilter] = useState<"all" | StockVoucherStatus>("all");
  const [voucherLoai, setVoucherLoai] = useState<"all" | StockRequestKind>("all");
  const [page, setPage] = useState(1);
  const [openVoucher, setOpenVoucher] = useState<number | null>(null);
  const [openRequest, setOpenRequest] = useState<number | null>(null);
  const [thresholdOpen, setThresholdOpen] = useState(false);
  const canViewStock = can("kho", "view_stock");

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

  // Về trang 1 khi đổi tab / tìm kiếm / lọc phiếu.
  useEffect(() => {
    setPage(1);
  }, [tab, q, voucherFilter, voucherLoai]);

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

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return groups;
    return groups.filter(
      (g) =>
        (g.name ?? "").toLowerCase().includes(s) || (g.code ?? "").toLowerCase().includes(s),
    );
  }, [groups, q]);

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

  function toggle(id: number) {
    setOpen((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }
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
  // Cột tab Tồn kho: [checkbox nếu canCreate] + caret + Vật tư + Mức + Tồn + Số lô
  // [+ Ngưỡng tồn + Ngưỡng tối đa nếu set_threshold] [+ Giá trị nếu view_cost].
  const tonCols =
    (canCreate ? 1 : 0) + 5 + (canSetThreshold ? 2 : 0) + (canViewCost ? 1 : 0);

  // Phân trang (dùng chung cho cả 2 tab; số tổng theo tab đang xem).
  const pageTotal = tab === "ton" ? filtered.length : shownVouchers.length;
  const maxPage = Math.max(1, Math.ceil(pageTotal / PAGE_SIZE));
  const pagedGroups = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const pagedVouchers = shownVouchers.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <main className="rc">
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
        {tab === "ton" && canViewCost && groups.length > 0 && (
          <div className="kho-ton__value">
            Giá trị tồn: <b>{money(Math.round(totalValue))}</b>
          </div>
        )}
        {canSetThreshold && (
          <Button variant="secondary" onClick={() => setThresholdOpen(true)}>
            Ngưỡng tồn
          </Button>
        )}
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

      <div className="rc__tablewrap">
        {tab === "ton" ? (
          <table className="rc__table">
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
                <th style={{ width: 32 }} aria-label="Mở rộng" />
                <th>Vật tư</th>
                <th style={{ width: "12%" }}>Mức</th>
                <th className="kho-num" style={{ width: "15%" }}>
                  Tồn khả dụng
                </th>
                <th className="kho-num" style={{ width: "9%" }}>
                  Số lô
                </th>
                {canSetThreshold && (
                  <>
                    <th className="kho-num" style={{ width: "12%" }}>
                      Ngưỡng tồn
                    </th>
                    <th className="kho-num" style={{ width: "12%" }}>
                      Ngưỡng tối đa
                    </th>
                  </>
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
                        <span className="rc-skel" style={{ width: c === 2 ? "70%" : "45%" }} />
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
                          : "Không có vật tư nào khớp tìm kiếm."}
                      </p>
                      {groups.length > 0 && (
                        <button type="button" className="btn btn--ghost" onClick={() => setQ("")}>
                          Xóa tìm kiếm
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                pagedGroups.map((g) => (
                  <FragmentRow
                    key={g.material_id}
                    g={g}
                    isOpen={open.has(g.material_id)}
                    canViewCost={canViewCost}
                    selectable={canCreate}
                    checked={selected.has(g.material_id)}
                    onToggleSel={() => toggleSel(g.material_id)}
                    onToggle={() => toggle(g.material_id)}
                    onOpenVoucher={setOpenVoucher}
                    canSetThreshold={canSetThreshold}
                    threshold={thresholds[g.material_id]}
                  />
                ))
              )}
            </tbody>
          </table>
        ) : (
          <table className="rc__table">
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
          canViewStock={canViewStock}
          onClose={() => setOpenRequest(null)}
          onChanged={loadVouchers}
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

function FragmentRow({
  g,
  isOpen,
  canViewCost,
  selectable,
  checked,
  onToggleSel,
  onToggle,
  onOpenVoucher,
  canSetThreshold,
  threshold,
}: {
  g: MaterialGroup;
  isOpen: boolean;
  canViewCost: boolean;
  selectable: boolean;
  checked: boolean;
  onToggleSel: () => void;
  onToggle: () => void;
  onOpenVoucher: (voucherId: number) => void;
  canSetThreshold: boolean;
  threshold: StockThreshold | undefined;
}) {
  return (
    <>
      <tr className="rc__row kho-ton__grow" onClick={onToggle}>
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
        <td className="kho-ton__caret">
          <span className={`kho-ton__chev${isOpen ? " is-open" : ""}`}>▸</span>
        </td>
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
        {canSetThreshold && (
          <>
            <td className="kho-num">
              {threshold?.nguong_ton != null ? (
                fmtQty(threshold.nguong_ton)
              ) : (
                <span className="rc__muted">—</span>
              )}
            </td>
            <td className="kho-num">
              {threshold?.nguong_toi_da != null ? (
                fmtQty(threshold.nguong_toi_da)
              ) : (
                <span className="rc__muted">—</span>
              )}
            </td>
          </>
        )}
        {canViewCost && <td className="kho-num">{money(Math.round(g.value))}</td>}
      </tr>
      {isOpen && (
        <tr className="kho-ton__detailrow">
          {selectable && <td />}
          <td />
          <td colSpan={4 + (canSetThreshold ? 2 : 0) + (canViewCost ? 1 : 0)}>
            <table className="kho-ton__lots">
              <thead>
                <tr>
                  <th>Mã lô</th>
                  <th className="kho-num">Còn</th>
                  <th>Ngày nhập</th>
                  {canViewCost && <th className="kho-num">Đơn giá</th>}
                </tr>
              </thead>
              <tbody>
                {g.lots.map((lot) => (
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
                    <td className="kho-num">{fmtQty(lot.sl_con_lai)}</td>
                    <td>{fmtDateISO(lot.ngay_nhap)}</td>
                    {canViewCost && (
                      <td className="kho-num">{money(lot.don_gia_nhap ?? 0)}</td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
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
