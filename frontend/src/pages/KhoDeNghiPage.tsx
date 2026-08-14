// Màn "Yêu cầu kho" — người YÊU CẦU (tổ trưởng SX, NV sản xuất, QL sản xuất, NV mua hàng).
//
// Ranh giới của màn này là ranh giới QUYỀN: người yêu cầu KHÔNG thấy số tồn, KHÔNG thấy giá,
// KHÔNG thấy lô, KHÔNG chọn kho. Yêu cầu chỉ nói "xin cái gì, bao nhiêu"; kho nào là quyết định
// ở BƯỚC LẬP PHIẾU (thủ kho). SIẾT 2026-08-08: mặt hàng phải có sẵn trong danh mục Giấy / Vật
// tư khác — không còn gõ tên tự do rồi kho gắn mã sau.
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type HangLoai,
  type MatHangOption,
  type StockRequest,
  type StockRequestKind,
  type StockRequestLineInput,
  type StockRequestStatus,
  type StockVoucher,
} from "../api/client";
import { VoucherDrawer } from "./KhoYeuCauPage";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { DiscardChangesDialog } from "../components/DiscardChangesDialog";
import { DonViChonTheoHang, MaterialCombobox } from "../components/MaterialCombobox";
import { PrintSheet } from "../components/PrintSheet";
import { Select } from "../components/Select";
import { fmtDate, fmtDateISO } from "../utils/format";
import { RequestStatusBadge, fmtQty, isOverdue, todayISO } from "./khoShared";
import "./rebuild-catalog.css";
import "./kho-request.css";

const PAGE_SIZE = 8;
// Trần một lần tải: đếm tab + sắp xếp + phân trang đều làm ở FE để số trên tab luôn khớp
// với bảng. Backend chặn `size` ở 200 nên đây cũng là trần thật của endpoint.
const FETCH_SIZE = 200;

type TabId = "all" | "dang-cap" | "done" | "khong-thanh";

// BỎ BƯỚC DUYỆT: tạo yêu cầu là 'approved' NGAY → không còn 'draft'/'pending' để lọc, bỏ luôn tab
// "Chờ duyệt". Yêu cầu mới rơi thẳng vào "Đang cấp".
const TAB_STATUSES: Record<Exclude<TabId, "all">, StockRequestStatus[]> = {
  "dang-cap": ["approved", "received", "preparing", "partial"],
  done: ["done"],
  "khong-thanh": ["rejected", "cancelled"],
};

/** VỪA CÓ PHẢN HỒI lên đầu: xếp theo `updated_at` (lần đổi gần nhất: tạo/cấp/hoàn tất/hủy) giảm dần
 *  → yêu cầu vừa được duyệt/hủy/cấp nhảy lên trên cùng cho dễ nhận biết, không chìm dưới theo ngày tạo. */
function sortRequests(a: StockRequest, b: StockRequest): number {
  const ua = a.updated_at ?? a.created_at;
  const ub = b.updated_at ?? b.created_at;
  if (ua !== ub) return ub.localeCompare(ua);
  return b.ma.localeCompare(a.ma);
}

export function KhoDeNghiPage({
  eventTick = 0,
  loai,
  initialSeed = null,
  onSeedConsumed,
  unseenDone = 0,
  unseenFail = 0,
  onSeen,
  openRequestId = null,
  onOpenRequestConsumed,
}: {
  eventTick?: number;
  /** Khoá chiều theo tab (Nhập/Xuất): lọc danh sách + cố định loại khi tạo mới. */
  loai: StockRequestKind;
  /** Điều hướng kèm dữ liệu → mở sẵn form TẠO đã điền (vd "Nhập kho" từ đợt giao đơn mua). */
  initialSeed?: KhoNhapSeed | null;
  /** Báo cha đã tiêu thụ seed (xoá đi để không mở lại khi remount). */
  onSeedConsumed?: () => void;
  /** Phản hồi kho CHƯA XEM của người tạo → số đỏ cạnh bộ lọc Hoàn tất / Không thành. */
  unseenDone?: number;
  unseenFail?: number;
  /** Sau khi mở xem 1 yêu cầu (đã đánh dấu đã xem) → refetch badge/số đỏ ở AppShell. */
  onSeen?: () => void;
  /** Bấm thông báo → mở sẵn drawer đúng yêu cầu này (id). */
  openRequestId?: number | null;
  onOpenRequestConsumed?: () => void;
}) {
  const { token, user } = useAuth();
  const can = useCan();
  const canRequest = can("kho", "request");

  const [rows, setRows] = useState<StockRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<TabId>("all");
  // Lọc theo khoảng NGÀY CẦN (rỗng = không lọc đầu đó).
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  // null = đóng; "new" = soạn mới; {id} = mở yêu cầu đã có; {seed} = tạo lại từ yêu cầu cũ.
  const [drawer, setDrawer] = useState<
    | null
    | { mode: "new"; seed?: SeedLine[]; loai?: StockRequestKind; ghiChu?: string; ngayCan?: string; locked?: boolean }
    | { mode: "open"; id: number }
  >(null);

  // Mở sẵn form TẠO khi được điều hướng kèm seed (bấm "Nhập kho" ở đợt giao đơn mua). Tiêu thụ
  // một lần: báo cha xoá seed để lần remount sau (đổi chiều Nhập/Xuất) không tự bật lại form.
  useEffect(() => {
    if (initialSeed?.seed?.length) {
      setDrawer({
        mode: "new",
        seed: initialSeed.seed,
        loai: "NHAP",
        ghiChu: initialSeed.ghi_chu,
        ngayCan: initialSeed.ngay_can,
        locked: initialSeed.locked,
      });
      onSeedConsumed?.();
    }
  }, [initialSeed, onSeedConsumed]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.kho.deNghi
      .list(token, { q: q || null, loai, size: FETCH_SIZE })
      .then((r) => {
        setRows(r.items);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được danh sách yêu cầu."))
      .finally(() => setLoading(false));
  }, [token, q, loai]);

  // Gõ tìm → chờ 300ms rồi mới gọi (mỗi lần gọi backend phải tính đèn tồn cho từng dòng).
  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [load]);

  // SSE đẩy tín hiệu đổi trạng thái → danh sách tự tươi, không bắt người dùng F5.
  useEffect(() => {
    if (eventTick > 0) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventTick]);

  // Bấm thông báo → mở sẵn drawer đúng yêu cầu + đánh dấu đã xem (là yêu cầu của người tạo) + hạ badge.
  useEffect(() => {
    if (openRequestId == null) return;
    setDrawer({ mode: "open", id: openRequestId });
    if (token) {
      api.kho.deNghi
        .markSeen(token, openRequestId)
        .then(() => onSeen?.())
        .catch(() => {});
    }
    onOpenRequestConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openRequestId]);

  const meId = user?.id ?? -1;

  // Mở xem 1 yêu cầu. Nếu là phản hồi cuối (Hoàn tất / Không thành) thì đánh dấu ĐÃ XEM (per-request)
  // rồi refetch badge/số đỏ — "bấm xem cái nào mất cái đó".
  function openRequest(r: StockRequest) {
    setDrawer({ mode: "open", id: r.id });
    const terminal =
      r.trang_thai === "done" || r.trang_thai === "rejected" || r.trang_thai === "cancelled";
    if (token && terminal) {
      api.kho.deNghi
        .markSeen(token, r.id)
        .then(() => onSeen?.())
        .catch(() => {});
    }
  }

  function countOf(id: TabId): number {
    if (id === "all") return rows.length;
    return rows.filter((r) => TAB_STATUSES[id].includes(r.trang_thai)).length;
  }

  const filtered = useMemo(() => {
    const base =
      tab === "all" ? rows : rows.filter((r) => TAB_STATUSES[tab].includes(r.trang_thai));
    // Lọc theo khoảng Ngày cần. Yêu cầu chưa đặt ngày cần → ẩn khi có áp bộ lọc ngày.
    const byDate = base.filter((r) => {
      if (!dateFrom && !dateTo) return true;
      if (!r.ngay_can) return false;
      if (dateFrom && r.ngay_can < dateFrom) return false;
      if (dateTo && r.ngay_can > dateTo) return false;
      return true;
    });
    return [...byDate].sort(sortRequests);
  }, [rows, tab, dateFrom, dateTo]);

  useEffect(() => {
    setPage(1);
  }, [tab, q, dateFrom, dateTo]);

  const total = filtered.length;
  const shown = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const tabs: { id: TabId; label: string }[] = [
    { id: "all", label: "Tất cả" },
    { id: "dang-cap", label: "Đang cấp" },
    { id: "done", label: "Hoàn tất" },
    { id: "khong-thanh", label: "Đã hủy" },
  ];

  // Yêu cầu KHÔNG gắn kho nên không có tồn để soi → bỏ hẳn cột đèn. Cột "Người" thay vào để
  // mỗi công đoạn hiện rõ AI yêu cầu → AI duyệt ngay trên bảng.
  const colCount = 6;

  return (
    <div className="kho-list">
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">Yêu cầu kho</h1>
          <span className="rc__count">{rows.length} yêu cầu</span>
        </div>
        <p className="rc__sub">
          Xin nhập hoặc lĩnh vật tư. Kho chỉ nhận yêu cầu đã được duyệt.
        </p>
      </header>

      <div className="rc__toolbar">
        <div className="rc__search-wrapper">
          <SearchIcon />
          <input
            className="rc__search"
            placeholder="Tìm mã yêu cầu / vật tư…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        {/* LỌC TRẠNG THÁI — dropdown thay dải tab cho gọn (đã có 2 hàng tab việc/chiều ở trên). */}
        <div className="kho-picker">
          <Select
            options={tabs.map((t) => ({
              value: t.id,
              label: t.label,
              hint: String(countOf(t.id)),
              // Số ĐỎ = phản hồi kho CHƯA XEM của người tạo, chỉ ở bộ lọc Hoàn tất / Không thành.
              badge:
                t.id === "done" ? unseenDone : t.id === "khong-thanh" ? unseenFail : undefined,
            }))}
            value={tab}
            onChange={(v) => v != null && setTab(v as TabId)}
            ariaLabel="Lọc trạng thái"
          />
        </div>
        {/* Lọc theo khoảng NGÀY CẦN. */}
        <div className="kho-daterange" title="Lọc theo Ngày cần">
          <input
            type="date"
            className="rc-input"
            value={dateFrom}
            max={dateTo || undefined}
            onChange={(e) => setDateFrom(e.target.value)}
            aria-label="Từ ngày"
          />
          <span className="kho-daterange__sep">→</span>
          <input
            type="date"
            className="rc-input"
            value={dateTo}
            min={dateFrom || undefined}
            onChange={(e) => setDateTo(e.target.value)}
            aria-label="Đến ngày"
          />
          {(dateFrom || dateTo) && (
            <button
              type="button"
              className="rc__link-btn"
              onClick={() => {
                setDateFrom("");
                setDateTo("");
              }}
            >
              Xóa
            </button>
          )}
        </div>
        <div className="rc__spacer" />
        {canRequest && (
          <Button variant="accent" onClick={() => setDrawer({ mode: "new", loai })}>
            <PlusIcon /> Tạo yêu cầu
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
            onClick={load}
          >
            Tải lại
          </button>
        </div>
      )}

      <div className="rc__tablewrap">
        <table className="rc__table rc__table--fixed">
          <thead>
            <tr>
              <th style={{ width: "13%" }}>Mã</th>
              <th>Vật tư</th>
              <th style={{ width: "15%" }}>Người</th>
              <th style={{ width: "12%" }}>Ngày yêu cầu</th>
              <th style={{ width: "12%" }}>{loai === "NHAP" ? "Ngày cần nhập" : "Ngày cần xuất"}</th>
              <th style={{ width: "13%" }}>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="rc-skel__row">
                  {Array.from({ length: colCount }).map((__, c) => (
                    <td key={c}>
                      <span className="rc-skel" style={{ width: c === 1 ? "80%" : "55%" }} />
                    </td>
                  ))}
                </tr>
              ))
            ) : shown.length === 0 ? (
              <tr>
                <td colSpan={colCount} className="rc__empty-state-td">
                  <div className="rc__empty-state">
                    <EmptyIcon />
                    <p className="rc__empty-text">
                      {rows.length === 0
                        ? "Chưa có yêu cầu nào. Tạo yêu cầu để xin nhập hoặc lĩnh vật tư."
                        : "Không có yêu cầu nào ở trạng thái này."}
                    </p>
                    {rows.length === 0 ? (
                      canRequest && (
                        <Button variant="ghost" onClick={() => setDrawer({ mode: "new", loai })}>
                          <PlusIcon /> Tạo yêu cầu
                        </Button>
                      )
                    ) : (
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setQ("");
                          setTab("all");
                        }}
                      >
                        Xóa bộ lọc
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ) : (
              <>
                {shown.map((r) => {
                const overdue = isOverdue(r.ngay_can, r.trang_thai);
                const first = r.lines[0];
                // "Người" = người yêu cầu (dòng trên) + phản hồi: bị từ chối thì nêu người từ chối.
                // Yêu cầu nay tạo là 'approved' luôn nên không còn nhánh "Chờ duyệt".
                const decided = r.nguoi_duyet_ten;
                const reply =
                  r.trang_thai === "rejected" ? `Từ chối: ${decided ?? "—"}` : "";
                return (
                  <tr
                    key={r.id}
                    className="rc__row"
                    onClick={() => openRequest(r)}
                  >
                    <td className="rc__nowrap">
                      <span className="rc__code-badge">{r.ma}</span>
                    </td>
                    <td>
                      <div
                        className="rc__name kho-name-clamp"
                        title={first?.hang_ten ?? undefined}
                      >
                        {first?.hang_ten ?? "—"}
                      </div>
                      {r.lines.length > 1 && (
                        <div className="rc__muted kho-hint">+{r.lines.length - 1} mã</div>
                      )}
                    </td>
                    <td>
                      <div className="rc__name">{r.nguoi_tao_ten ?? "—"}</div>
                      <div className="rc__muted kho-hint">{reply}</div>
                    </td>
                    <td className="rc__nowrap">{fmtDate(r.created_at)}</td>
                    <td className={`rc__nowrap${overdue ? " kho-overdue" : ""}`}>
                      {r.ngay_can ? fmtDateISO(r.ngay_can) : "—"}
                    </td>
                    <td>
                      <RequestStatusBadge status={r.trang_thai} />
                    </td>
                  </tr>
                );
                })}
                {Array.from({ length: Math.max(0, PAGE_SIZE - shown.length) }).map((_, i) => (
                  <tr key={`filler-${i}`} className="rc__filler" aria-hidden="true">
                    <td colSpan={colCount}>
                      <div className="rc__name">&nbsp;</div>
                      <div className="rc__muted kho-hint">&nbsp;</div>
                    </td>
                  </tr>
                ))}
              </>
            )}
          </tbody>
        </table>
      </div>

      {total > 0 && (
        <div className="kho-pager">
          <span className="kho-pager__page">{total} yêu cầu</span>
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

      {drawer && token && (
        <RequestDrawer
          key={drawer.mode === "open" ? `req-${drawer.id}` : "req-new"}
          token={token}
          meId={meId}
          requestId={drawer.mode === "open" ? drawer.id : null}
          seed={drawer.mode === "new" ? drawer.seed : undefined}
          seedLoai={drawer.mode === "new" ? drawer.loai : undefined}
          seedGhiChu={drawer.mode === "new" ? drawer.ghiChu : undefined}
          seedNgayCan={drawer.mode === "new" ? drawer.ngayCan : undefined}
          seedLocked={drawer.mode === "new" ? drawer.locked : undefined}
          canRequest={canRequest}
          onClone={(lines, loai) => setDrawer({ mode: "new", seed: lines, loai })}
          onClose={() => setDrawer(null)}
          onSaved={() => {
            setDrawer(null);
            load();
          }}
        />
      )}
    </div>
  );
}

// ── Ô "Cho lệnh nào" (mg 0175) ───────────────────────────────────────────────
// MỘT ô cho cả lệnh lẫn bài ghép: người yêu cầu không nghĩ theo hai khái niệm, họ nghĩ "đợt hàng
// này". Giá trị mã hoá `lsx:<id>` / `bg:<id>` rồi tách ra lúc gửi, nên payload vẫn là hai cột rõ ràng.

interface LenhOption {
  kind: "lsx" | "bai_ghep";
  id: number;
  ma: string;
  ten: string;
}

function lenhNhan(opts: LenhOption[], lsxId: number | null, bgId: number | null): string {
  const o = opts.find(
    (x) => (x.kind === "lsx" && x.id === lsxId) || (x.kind === "bai_ghep" && x.id === bgId),
  );
  if (o) return o.ma;
  // Có id mà không còn trong danh sách (lệnh đã đóng) — vẫn phải hiện, đừng nuốt mất.
  if (lsxId) return `Lệnh #${lsxId}`;
  if (bgId) return `Bài #${bgId}`;
  return "—";
}

function LenhChon({
  options,
  lsxId,
  baiGhepId,
  onChange,
}: {
  options: LenhOption[];
  lsxId: number | null;
  baiGhepId: number | null;
  onChange: (lsxId: number | null, baiGhepId: number | null) => void;
}) {
  const value = lsxId ? `lsx:${lsxId}` : baiGhepId ? `bg:${baiGhepId}` : "";
  return (
    <select
      className="rc-input"
      style={{ minWidth: 156 }}
      value={value}
      aria-label="Xin cho lệnh sản xuất nào (bỏ trống nếu xin lặt vặt)"
      onChange={(e) => {
        const v = e.target.value;
        if (!v) onChange(null, null);
        else if (v.startsWith("lsx:")) onChange(Number(v.slice(4)), null);
        else onChange(null, Number(v.slice(3)));
      }}
    >
      <option value="">— Không theo lệnh —</option>
      {options.map((o) => (
        <option key={`${o.kind}:${o.id}`} value={`${o.kind === "lsx" ? "lsx" : "bg"}:${o.id}`}>
          {o.ma}
          {o.ten ? ` — ${o.ten}` : ""}
        </option>
      ))}
    </select>
  );
}

// ── DRAWER ────────────────────────────────────────────────────────────────────

export interface SeedLine {
  /** MẶT HÀNG GỐC — null = dòng trống chưa chọn. Không còn khái niệm "hàng chưa có mã". */
  hang_loai: HangLoai | null;
  hang_id: number | null;
  hang_ma: string | null;
  hang_ten: string | null;
  /** Đơn vị người yêu cầu chọn (trong tập đổi được của mặt hàng) + hệ số về đơn vị gốc để
   *  hiện trước con số sẽ vào tồn. */
  dvt: string;
  he_so_ve_goc: number | null;
  sl_de_nghi: number;
  /** Đơn giá NHẬP người yêu cầu khai (chỉ yêu cầu NHẬP), theo `dvt`. Phiếu kế thừa; kho không sửa. */
  don_gia: number | null;
  /** XIN CHO LỆNH NÀO (mg 0175). Bỏ trống được — xin lặt vặt (băng dính, giẻ lau) không thuộc lệnh
   *  nào. Khai rồi thì bảng cân đối vật tư của Kế hoạch trừ phần đã cấp vào ĐÚNG dòng nhu cầu. */
  lsx_id?: number | null;
  bai_ghep_id?: number | null;
  ghi_chu: string | null;
}

/** Gói dữ liệu điều hướng-kèm để mở sẵn form TẠO yêu cầu NHẬP đã điền — dùng khi bấm "Nhập kho"
 *  ở một đợt giao đơn mua (đợt giao ↔ phiếu nhập kho là CÙNG sự kiện hàng về). */
export interface KhoNhapSeed {
  seed: SeedLine[];
  /** Ghi chú cấp phiếu, thường trỏ về mã đơn mua + số đợt để truy vết. */
  ghi_chu?: string;
  /** Ngày nhập điền sẵn (yyyy-mm-dd) — lấy từ ngày giao của đợt. */
  ngay_can?: string;
  /** true = số liệu lấy từ đơn mua → KHOÁ, không cho sửa dòng (phải khớp hàng đã nhận). */
  locked?: boolean;
}

interface DraftLine extends SeedLine {
  key: string;
  /** id dòng đã lưu — cần để gửi `approved_qty`. */
  lineId: number | null;
  sl_duyet: number;
  sl_da_ung: number;
  /** Kho phản hồi: lý do cấp/nhập thiếu (chỉ đọc). */
  ly_do_thieu: string | null;
}

let lineSeq = 0;
function newLine(seed?: Partial<SeedLine>): DraftLine {
  lineSeq += 1;
  return {
    key: `l${lineSeq}`,
    lineId: null,
    hang_loai: seed?.hang_loai ?? null,
    hang_id: seed?.hang_id ?? null,
    hang_ma: seed?.hang_ma ?? null,
    hang_ten: seed?.hang_ten ?? null,
    dvt: seed?.dvt ?? "",
    he_so_ve_goc: seed?.he_so_ve_goc ?? null,
    sl_de_nghi: seed?.sl_de_nghi ?? 0,
    don_gia: seed?.don_gia ?? null,
    lsx_id: seed?.lsx_id ?? null,
    bai_ghep_id: seed?.bai_ghep_id ?? null,
    ghi_chu: seed?.ghi_chu ?? null,
    sl_duyet: 0,
    sl_da_ung: 0,
    ly_do_thieu: null,
  };
}

interface RequestDrawerProps {
  token: string;
  meId: number;
  requestId: number | null;
  seed?: SeedLine[];
  seedLoai?: StockRequestKind;
  seedGhiChu?: string;
  seedNgayCan?: string;
  seedLocked?: boolean;
  canRequest: boolean;
  onClone: (lines: SeedLine[], loai: StockRequestKind) => void;
  onClose: () => void;
  onSaved: () => void;
}

function RequestDrawer({
  token,
  meId,
  requestId,
  seed,
  seedLoai,
  seedGhiChu,
  seedNgayCan,
  seedLocked,
  canRequest,
  onClone,
  onClose,
  onSaved,
}: RequestDrawerProps) {
  const [req, setReq] = useState<StockRequest | null>(null);
  const [loading, setLoading] = useState(requestId != null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [loai, setLoai] = useState<StockRequestKind>(seedLoai ?? "XUAT");
  const [ngayCan, setNgayCan] = useState(seedNgayCan ?? "");
  const [ghiChu, setGhiChu] = useState(seedGhiChu ?? "");
  const [lines, setLines] = useState<DraftLine[]>(() =>
    seed?.length ? seed.map((s) => newLine(s)) : [newLine()],
  );

  const [dirty, setDirty] = useState(false);
  const [askDiscard, setAskDiscard] = useState(false);
  const [printing, setPrinting] = useState(false);
  // Danh sách lệnh/bài để chọn ở ô "Cho lệnh" (mg 0175). Nạp MỘT lần cho cả drawer — mỗi dòng tự
  // gọi là N+1 request ngay lúc người ta đang gõ số lượng.
  const [lenhOptions, setLenhOptions] = useState<LenhOption[]>([]);
  // Phiếu kho đã lập từ yêu cầu này — người TẠO xem lại (chống mất chức năng "xem phiếu").
  const [vouchers, setVouchers] = useState<StockVoucher[]>([]);
  const [openVoucher, setOpenVoucher] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const [ls, bg] = await Promise.all([api.lsx.list(token), api.baiGhep.list(token)]);
        if (!alive) return;
        setLenhOptions([
          ...ls.items.map((l) => ({ kind: "lsx" as const, id: l.id, ma: l.ma, ten: l.ten })),
          ...bg.items.map((b) => ({ kind: "bai_ghep" as const, id: b.id, ma: b.ma, ten: "" })),
        ]);
      } catch {
        // Không lấy được danh sách lệnh KHÔNG được chặn việc lập yêu cầu — ô này vốn bỏ trống được.
        if (alive) setLenhOptions([]);
      }
    })();
    return () => {
      alive = false;
    };
  }, [token]);

  useEffect(() => {
    if (requestId == null) return;
    let cancelled = false;
    setLoading(true);
    api.kho.deNghi
      .get(token, requestId)
      .then((r) => {
        if (cancelled) return;
        setReq(r);
        setLoai(r.loai);
        setNgayCan(r.ngay_can ?? "");
        setGhiChu(r.ghi_chu ?? "");
        setLines(
          r.lines.map((l) => ({
            key: `s${l.id}`,
            lineId: l.id,
            hang_loai: l.hang_loai,
            hang_id: l.hang_id,
            hang_ma: l.hang_ma,
            hang_ten: l.hang_ten,
            dvt: l.dvt,
            // Suy ngược từ số server đã quy đổi — khỏi gọi thêm API chỉ để lấy hệ số.
            he_so_ve_goc: l.sl_quy_doi && l.sl_de_nghi ? l.sl_quy_doi / l.sl_de_nghi : null,
            sl_de_nghi: l.sl_de_nghi,
            don_gia: l.don_gia,
            lsx_id: l.lsx_id,
            bai_ghep_id: l.bai_ghep_id,
            ghi_chu: l.ghi_chu,
            sl_duyet: l.sl_duyet,
            sl_da_ung: l.sl_da_ung,
            ly_do_thieu: l.ly_do_thieu,
          })),
        );
        setDirty(false);
        // Phiếu đã lập từ yêu cầu này (chờ ghi sổ / đã ghi sổ) → cho người tạo xem lại.
        api.kho.phieu
          .list(token, { request_id: r.id, size: 50 })
          .then((p) => { if (!cancelled) setVouchers(p.items); })
          .catch(() => {});
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Không tải được yêu cầu."),
      )
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, requestId]);

  const status: StockRequestStatus = req?.trang_thai ?? "draft";
  const isNew = requestId == null;
  const isOwner = isNew || req?.nguoi_tao_id === meId;
  // BỎ BƯỚC DUYỆT: chỉ yêu cầu MỚI còn sửa được; tạo xong là 'approved' = khoá (BRD §1.5).
  // Seed từ đơn mua (locked) → khoá mọi ô dòng: số liệu phải khớp hàng đã nhận, chỉ được Tạo.
  const editable = isNew && canRequest && !seedLocked;
  const showReply = ["approved", "received", "preparing", "partial", "done"].includes(status);

  function touch<T>(setter: (v: T) => void) {
    return (v: T) => {
      setDirty(true);
      setter(v);
    };
  }

  function patchLine(key: string, patch: Partial<DraftLine>) {
    setDirty(true);
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  }

  function pickMaterial(key: string, m: MatHangOption) {
    // Trùng mặt hàng: chặn ngay ở FE với ĐÚNG câu backend trả, để người dùng không gặp
    // hai cách diễn đạt khác nhau cho cùng một luật.
    //
    // Khoá trùng gồm CẢ lệnh/bài (mg 0175): cùng loại giấy xin cho HAI lệnh khác nhau là hai dòng
    // hợp lệ — gộp lại thì mất thông tin "phần nào cho lệnh nào", đúng thứ bảng cân đối cần.
    const dong = lines.find((l) => l.key === key);
    if (
      lines.some(
        (l) =>
          l.key !== key &&
          l.hang_loai === m.hang_loai &&
          l.hang_id === m.hang_id &&
          (l.lsx_id ?? null) === (dong?.lsx_id ?? null) &&
          (l.bai_ghep_id ?? null) === (dong?.bai_ghep_id ?? null),
      )
    ) {
      setError("Một mặt hàng cho cùng một lệnh chỉ được xuất hiện 1 dòng — gộp số lượng lại.");
      return;
    }
    setError(null);
    // Đổi mặt hàng → XOÁ đơn vị cũ: đơn vị dùng được phụ thuộc chính mặt hàng, giữ lại đơn vị của
    // món trước là mời một dòng không quy đổi được. `DonViChonTheoHang` sẽ tự điền đơn vị gốc.
    patchLine(key, {
      hang_loai: m.hang_loai,
      hang_id: m.hang_id,
      hang_ma: m.ma,
      hang_ten: m.ten,
      dvt: "",
      he_so_ve_goc: null,
    });
  }

  function payloadLines(): StockRequestLineInput[] {
    const isNhap = loai === "NHAP";
    return lines
      .filter((l) => l.hang_loai && l.hang_id && l.dvt && Number(l.sl_de_nghi) > 0)
      .map((l) => ({
        hang_loai: l.hang_loai as HangLoai,
        hang_id: l.hang_id as number,
        dvt: l.dvt,
        sl_de_nghi: Number(l.sl_de_nghi),
        // Đơn giá chỉ gửi cho yêu cầu NHẬP (người yêu cầu biết giá NCC). XUẤT lấy giá vốn từ lô.
        don_gia: isNhap && l.don_gia != null ? Number(l.don_gia) : null,
        lsx_id: l.lsx_id ?? null,
        bai_ghep_id: l.bai_ghep_id ?? null,
        ghi_chu: l.ghi_chu || null,
      }));
  }

  // BỎ BƯỚC DUYỆT: tạo yêu cầu là 'approved' NGAY (backend tự set), không còn "trình duyệt".
  // Chỉ có luồng TẠO MỚI; yêu cầu đã tạo là khoá nên không có nhánh update ở đây.
  async function save() {
    const body = payloadLines();
    if (!body.length) {
      setError("Thêm ít nhất một dòng vật tư có số lượng lớn hơn 0.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.kho.deNghi.create(token, {
        loai,
        // Số yêu cầu LUÔN tự sinh (DNN/DNX####) — không cho tự nhập.
        ngay_can: ngayCan || null,
        ghi_chu: ghiChu || null,
        lines: body,
      });
      setDirty(false);
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không lưu được yêu cầu.");
    } finally {
      setBusy(false);
    }
  }

  function requestClose() {
    if (dirty) setAskDiscard(true);
    else onClose();
  }

  const kicker = loai === "NHAP" ? "YÊU CẦU NHẬP" : "YÊU CẦU XUẤT";

  return (
    <>
      <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={requestClose}>
        <aside className="rc-drawer rc-drawer--mid" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">{kicker}</div>
            <h2 className="rc-drawer__title">{req?.ma ?? "Yêu cầu mới"}</h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
            {req && <RequestStatusBadge status={req.trang_thai} />}
            <button type="button" className="rc-drawer__x" onClick={requestClose} aria-label="Đóng">
              ✕
            </button>
          </div>
        </header>

        {/* Dải meta MỘT DÒNG thay cho Timeline: API chỉ có 2 mốc (tạo · duyệt), dựng cả một
            trục thời gian cho 2 điểm là trang trí chứ không thêm thông tin nào. */}
        {req && (
          <div className="kho-meta">
            Yêu cầu: {req.nguoi_tao_ten ?? "—"} · {fmtDate(req.created_at)}
          </div>
        )}

        <div className="rc-drawer__body">
          {req?.trang_thai === "rejected" && req.ly_do_tu_choi && (
            <div className="banner banner--error" role="alert">
              <span>Bị từ chối: {req.ly_do_tu_choi}</span>
            </div>
          )}
          {req?.trang_thai === "cancelled" && req.ly_do_huy && (
            <div className="banner banner--warn" role="status">
              <span>Đã hủy: {req.ly_do_huy}</span>
            </div>
          )}
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
          ) : (
            <>
              <section className="rc-sec">
                <h3 className="rc-sec__title">Thông tin chung</h3>
                <div className="rc-grid">
                  {/* "Loại" (Nhập/Xuất) đã bỏ khỏi form: chiều do TAB quyết định, không cần hiện lại. */}
                  <div className="rc-field">
                    <label className="rc-field__label" htmlFor="kho-ngay-can">
                      {loai === "NHAP" ? "Ngày cần nhập" : "Ngày cần xuất"}
                    </label>
                    <input
                      id="kho-ngay-can"
                      type="date"
                      className="rc-input"
                      value={ngayCan}
                      min={todayISO()}
                      disabled={!editable}
                      onChange={(e) => touch(setNgayCan)(e.target.value)}
                    />
                  </div>
                </div>
              </section>

              <section className="rc-sec">
                <h3 className="rc-sec__title">Vật tư yêu cầu</h3>
                <div className="kho-lines__wrap">
                  <table className="kho-lines">
                    <thead className="kho-lines__head">
                      <tr>
                        <th style={{ width: 40 }}>STT</th>
                        <th style={{ minWidth: 180 }}>Vật tư</th>
                        {/* mg 0175 — "xin cho lệnh nào". Bỏ trống được: xin lặt vặt không thuộc
                            lệnh nào. Khai thì Kế hoạch trừ đúng phần đã cấp vào lệnh đó. */}
                        <th style={{ width: 172 }}>Cho lệnh</th>
                        <th style={{ width: 92 }}>ĐVT</th>
                        <th className="kho-num" style={{ width: 100 }}>
                          SL yêu cầu
                        </th>
                        {/* SL đã cấp (sl_da_ung) — chỉ hiện khi yêu cầu đã vào luồng cấp phát.
                            NHẬP = "SL thực nhận" · XUẤT = "SL thực cấp" (phân biệt với SL yêu cầu). */}
                        {showReply && (
                          <th className="kho-num" style={{ width: 90 }}>
                            {loai === "NHAP" ? "SL thực nhận" : "SL thực cấp"}
                          </th>
                        )}
                        {/* Đơn giá CHỈ ở yêu cầu NHẬP — người yêu cầu khai (họ biết giá NCC);
                            phiếu kế thừa, kho không sửa. XUẤT lấy giá vốn đích danh của lô. */}
                        {loai === "NHAP" && (
                          <th className="kho-num" style={{ width: 120 }}>
                            Đơn giá
                          </th>
                        )}
                        {editable && <th style={{ width: 32 }} aria-label="Xóa" />}
                      </tr>
                    </thead>
                    <tbody>
                      {lines.map((l, i) => {
                        return (
                          <Fragment key={l.key}>
                          <tr>
                            <td className="kho-lines__code">{i + 1}</td>
                            <td>
                              {/* Seed từ đơn mua (locked) chỉ có TÊN CHỮ → chưa map được mặt hàng:
                                  vẫn cho CHỌN vật tư (đơn mua không mang mã danh mục), khỏi bế tắc. */}
                              {editable || (seedLocked && !l.hang_id) ? (
                                <MaterialCombobox
                                  token={token}
                                  hangTen={l.hang_ten}
                                  onPick={(m) => pickMaterial(l.key, m)}
                                />
                              ) : (
                                <>
                                  <div
                                    className="kho-lines__name kho-name-clamp"
                                    title={l.hang_ten ?? undefined}
                                  >
                                    {l.hang_ten ?? "—"}
                                  </div>
                                  <div className="kho-lines__code">{l.hang_ma ?? ""}</div>
                                </>
                              )}
                            </td>
                            <td>
                              {editable ? (
                                <LenhChon
                                  options={lenhOptions}
                                  lsxId={l.lsx_id ?? null}
                                  baiGhepId={l.bai_ghep_id ?? null}
                                  onChange={(lsxId, bgId) =>
                                    patchLine(l.key, { lsx_id: lsxId, bai_ghep_id: bgId })
                                  }
                                />
                              ) : (
                                <span className="kho-lines__code">
                                  {lenhNhan(lenhOptions, l.lsx_id ?? null, l.bai_ghep_id ?? null)}
                                </span>
                              )}
                            </td>
                            <td>
                              {/* ĐVT KHÔNG gõ tự do nữa: chỉ chọn trong tập đổi được của chính
                                  mặt hàng — đơn vị lạ thì tồn kho không cộng được. Dòng khoá vừa
                                  CHỌN TAY mặt hàng (đơn mua) → dvt bị xoá → mở lại để chọn đơn vị. */}
                              {(editable || (seedLocked && !l.dvt)) && l.hang_loai && l.hang_id ? (
                                <DonViChonTheoHang
                                  token={token}
                                  hangLoai={l.hang_loai}
                                  hangId={l.hang_id}
                                  value={l.dvt}
                                  onChange={(ma, hs) =>
                                    patchLine(l.key, { dvt: ma, he_so_ve_goc: hs })
                                  }
                                />
                              ) : (
                                <span className="kho-lines__code">{l.dvt || "—"}</span>
                              )}
                            </td>
                            <td className="kho-num">
                              {editable ? (
                                <input
                                  type="number"
                                  min={0}
                                  step="any"
                                  className="rc-input kho-num"
                                  value={l.sl_de_nghi || ""}
                                  onChange={(e) =>
                                    patchLine(l.key, { sl_de_nghi: Number(e.target.value) })
                                  }
                                  aria-label="Số lượng yêu cầu"
                                />
                              ) : (
                                fmtQty(l.sl_de_nghi)
                              )}
                              {/* Con số THẬT SỰ vào tồn. Nhập "10 ram" mà tồn cộng 419,25 kg thì
                                  phải nói ra ngay tại đây, đừng để bấm Lưu xong mới ngã ngửa. */}
                              {l.he_so_ve_goc != null
                                && l.he_so_ve_goc !== 1
                                && Number(l.sl_de_nghi) > 0 && (
                                <div className="kho-hint">
                                  ≈ {fmtQty(Number(l.sl_de_nghi) * l.he_so_ve_goc)} (đơn vị gốc)
                                </div>
                              )}
                            </td>
                            {showReply && (
                              <td className="kho-num">{fmtQty(l.sl_da_ung)}</td>
                            )}
                            {loai === "NHAP" && (
                              <td className="kho-num">
                                {editable ? (
                                  <input
                                    type="number"
                                    min={0}
                                    step="any"
                                    className="rc-input kho-num"
                                    value={l.don_gia ?? ""}
                                    onChange={(e) =>
                                      patchLine(l.key, {
                                        don_gia:
                                          e.target.value === "" ? null : Number(e.target.value),
                                      })
                                    }
                                    aria-label="Đơn giá"
                                    placeholder="0"
                                  />
                                ) : l.don_gia != null ? (
                                  `${l.don_gia.toLocaleString("vi-VN")} đ`
                                ) : (
                                  "—"
                                )}
                              </td>
                            )}
                            {editable && (
                              <td>
                                <button
                                  type="button"
                                  className="rc-bands__del"
                                  aria-label="Xóa dòng"
                                  onClick={() => {
                                    setDirty(true);
                                    setLines((prev) =>
                                      prev.length > 1
                                        ? prev.filter((x) => x.key !== l.key)
                                        : [newLine()],
                                    );
                                  }}
                                >
                                  ✕
                                </button>
                              </td>
                            )}
                          </tr>
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {editable && (
                  <button
                    type="button"
                    className="rc-bands__add"
                    onClick={() => {
                      setDirty(true);
                      setLines((prev) => [...prev, newLine()]);
                    }}
                  >
                    + Thêm dòng
                  </button>
                )}
              </section>

              {showReply && (
                <section className="rc-sec">
                  <h3 className="rc-sec__title">Kho phản hồi</h3>
                  <div className="kho-reply">
                    {lines.map((l) => {
                      const done = l.sl_duyet > 0 && l.sl_da_ung >= l.sl_duyet;
                      const none = l.sl_duyet <= 0;
                      const cls = none ? "no" : done ? "ok" : "wait";
                      return (
                        <div key={l.key} className={`kho-reply__item kho-reply__item--${cls}`}>
                          <span className="kho-reply__name">{l.hang_ten ?? "—"}</span> — Duyệt{" "}
                          {fmtQty(l.sl_duyet)}/{fmtQty(l.sl_de_nghi)}
                          {none
                            ? " · Không duyệt"
                            : l.sl_da_ung > 0
                              ? ` · Kho đã cấp ${fmtQty(l.sl_da_ung)}`
                              : " · Chờ kho cấp"}
                          {l.ly_do_thieu && (
                            <div className="kho-reply__reason">Lý do: {l.ly_do_thieu}</div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {vouchers.length > 0 && (
                <section className="rc-sec">
                  <h3 className="rc-sec__title">Phiếu kho đã cấp</h3>
                  <div className="kho-vlinks">
                    {vouchers.map((v) => (
                      <button
                        key={v.id}
                        type="button"
                        className="kho-vlink"
                        onClick={() => setOpenVoucher(v.id)}
                      >
                        <span className="rc__code-badge">{v.ma}</span>
                        <span className="kho-vlink__meta">
                          {v.loai === "NHAP" ? "Nhập" : "Xuất"} · {fmtDate(v.ngay)} ·{" "}
                          {v.trang_thai === "posted"
                            ? "Đã ghi sổ"
                            : v.trang_thai === "cancelled"
                              ? "Đã hủy"
                              : "Chờ ghi sổ"}
                        </span>
                      </button>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </div>

        <footer className="rc-drawer__foot">
          <RequestFooter
            status={isNew ? "draft" : status}
            isNew={isNew}
            isOwner={!!isOwner}
            canRequest={canRequest}
            busy={busy}
            onSave={() => save()}
            onPrint={() => setPrinting(true)}
            onClone={() =>
              onClone(
                lines.map((l) => ({
                  hang_loai: l.hang_loai,
                  hang_id: l.hang_id,
                  hang_ma: l.hang_ma,
                  hang_ten: l.hang_ten,
                  dvt: l.dvt,
                  he_so_ve_goc: l.he_so_ve_goc,
                  sl_de_nghi: l.sl_de_nghi,
                  don_gia: l.don_gia,
                  ghi_chu: l.ghi_chu,
                })),
                loai,
              )
            }
            onClose={requestClose}
          />
        </footer>
        </aside>
      </div>

      {/* Dialog/preview ĐỨNG NGOÀI scrim: nếu nằm trong, mọi cú click trong dialog sẽ nổi bọt
          lên scrim và đóng luôn cả drawer phía sau. */}
      <DiscardChangesDialog
        open={askDiscard}
        onDiscard={() => {
          setAskDiscard(false);
          onClose();
        }}
        onKeepEditing={() => setAskDiscard(false)}
      />

      {printing && req && (
        <RequestPrint req={req} lines={lines} onClose={() => setPrinting(false)} />
      )}

      {/* Người TẠO xem phiếu đã cấp — cùng màn phiếu như bên kho, read-only. `canViewCost` để true
          vì backend cho người tạo thấy giá phiếu của CHÍNH yêu cầu họ (kho_voucher.py). */}
      {openVoucher != null && (
        <VoucherDrawer
          token={token}
          voucherId={openVoucher}
          canCreate={false}
          canPost={false}
          canViewCost={true}
          onClose={() => setOpenVoucher(null)}
          onChanged={() => {}}
        />
      )}
    </>
  );
}

// Footer tách riêng: bảng trạng thái × quyền dài, để lẫn trong JSX drawer thì mỗi lần đọc
// lại phải dò xem nhánh nào ứng với trạng thái nào.
function RequestFooter(props: {
  status: StockRequestStatus;
  isNew: boolean;
  isOwner: boolean;
  canRequest: boolean;
  busy: boolean;
  onSave: () => void;
  onPrint: () => void;
  onClone: () => void;
  onClose: () => void;
}) {
  const { status, isNew, isOwner, canRequest, busy } = props;

  // BỎ BƯỚC DUYỆT: chỉ còn luồng TẠO. Tạo xong yêu cầu là 'approved' (khoá) — không còn nút
  // Lưu nháp / Trình duyệt / Duyệt / Từ chối / Lưu thay đổi.
  if (isNew && isOwner && canRequest) {
    return (
      <Button variant="accent" onClick={props.onSave} loading={busy}>
        Tạo yêu cầu
      </Button>
    );
  }

  if ((status === "rejected" || status === "cancelled") && isOwner && canRequest) {
    return (
      <>
        <Button variant="accent" onClick={props.onClone}>
          Tạo lại từ yêu cầu này
        </Button>
        <button type="button" className="btn btn--ghost" onClick={props.onClose}>
          Đóng
        </button>
      </>
    );
  }

  return (
    <>
      {!isNew && (
        <button type="button" className="btn btn--ghost" onClick={props.onPrint}>
          In yêu cầu
        </button>
      )}
      <button type="button" className="btn btn--secondary" onClick={props.onClose}>
        Đóng
      </button>
    </>
  );
}

/** Bản in giấy yêu cầu — KHÔNG cột giá, KHÔNG cột tồn (người ký duyệt không cần và
 *  phần lớn không có quyền xem hai thứ đó). */
function RequestPrint({
  req,
  lines,
  onClose,
}: {
  req: StockRequest;
  lines: DraftLine[];
  onClose: () => void;
}) {
  const title =
    req.loai === "NHAP" ? "GIẤY YÊU CẦU NHẬP KHO" : "GIẤY YÊU CẦU LĨNH VẬT TƯ";
  return (
    <PrintSheet title={title} docNo={req.ma} docDate={fmtDate(req.created_at)} onClose={onClose}>
      <div className="kho-print__meta">
        <span>
          <b>Bộ phận:</b> {req.bo_phan_ten ?? "…"}
        </span>
        <span>
          <b>Người yêu cầu:</b> {req.nguoi_tao_ten ?? "…"}
        </span>
        <span>
          <b>Ngày cần:</b> {req.ngay_can ? fmtDateISO(req.ngay_can) : "…"}
        </span>
      </div>
      {/* Trọn chuỗi trách nhiệm trên phiếu in: ai yêu cầu (trên) → ai duyệt (đây). */}
      <div className="kho-print__meta">
        <span>
          <b>Người duyệt:</b>{" "}
          {req.nguoi_duyet_ten
            ? `${req.nguoi_duyet_ten}${req.duyet_luc ? ` · ${fmtDate(req.duyet_luc)}` : ""}`
            : "…"}
        </span>
        <span>
          <b>Lý do:</b> {req.ghi_chu ?? "…"}
        </span>
      </div>
      <table className="kho-print__table">
        <thead>
          <tr>
            <th style={{ width: 40 }}>STT</th>
            <th>Tên vật tư</th>
            <th style={{ width: 96 }}>Mã</th>
            <th style={{ width: 60 }}>ĐVT</th>
            <th style={{ width: 90 }}>SL yêu cầu</th>
            <th style={{ width: 90 }}>SL duyệt</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={l.key}>
              <td>{i + 1}</td>
              <td>{l.hang_ten ?? ""}</td>
              <td>{l.hang_ma ?? ""}</td>
              <td>{l.dvt}</td>
              <td style={{ textAlign: "right" }}>{fmtQty(l.sl_de_nghi)}</td>
              <td style={{ textAlign: "right" }}>{l.sl_duyet > 0 ? fmtQty(l.sl_duyet) : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="kho-print__signs">
        {["Người yêu cầu", "Phụ trách bộ phận", "Thủ kho"].map((s) => (
          <div className="kho-print__sign" key={s}>
            <b>{s}</b>
            <span>(Ký, họ tên)</span>
          </div>
        ))}
      </div>
    </PrintSheet>
  );
}

// ── INLINE SVG ICONS ─────────────────────────────────────────────────────────
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

const PlusIcon = () => (
  <svg
    width="13"
    height="13"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="3"
    strokeLinecap="round"
  >
    <path d="M12 5v14M5 12h14" />
  </svg>
);

const EmptyIcon = () => (
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
    <path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z" />
    <path d="M3 7.5 12 12l9-4.5M12 12v9" />
  </svg>
);
