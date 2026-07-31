// Màn "Đề nghị kho" — người ĐỀ NGHỊ (tổ trưởng SX, NV sản xuất, QL sản xuất, NV mua hàng).
//
// Ranh giới của màn này là ranh giới QUYỀN: người đề nghị KHÔNG thấy số tồn, KHÔNG thấy giá,
// KHÔNG thấy lô, KHÔNG chọn kho. Đề nghị chỉ nói "xin cái gì, bao nhiêu"; kho nào là quyết định
// ở BƯỚC LẬP PHIẾU (thủ kho). Hàng mới thì gõ tên tự do — thủ kho gắn/tạo mã khi lập phiếu.
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  type StockMaterialOption,
  type StockRequest,
  type StockRequestKind,
  type StockRequestLineInput,
  type StockRequestStatus,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DiscardChangesDialog } from "../components/DiscardChangesDialog";
import { MaterialCombobox } from "../components/MaterialCombobox";
import { PrintSheet } from "../components/PrintSheet";
import { Select } from "../components/Select";
import { fmtDate, fmtDateISO } from "../utils/format";
import { RequestStatusBadge, fmtQty, isOverdue } from "./khoShared";
import "./rebuild-catalog.css";
import "./kho-request.css";

const PAGE_SIZE = 8;
// Trần một lần tải: đếm tab + sắp xếp + phân trang đều làm ở FE để số trên tab luôn khớp
// với bảng. Backend chặn `size` ở 200 nên đây cũng là trần thật của endpoint.
const FETCH_SIZE = 200;

type TabId = "cho-toi-duyet" | "all" | "pending" | "dang-cap" | "done" | "khong-thanh";

const TAB_STATUSES: Record<Exclude<TabId, "all" | "cho-toi-duyet">, StockRequestStatus[]> = {
  // Đề nghị nháp gộp vào "pending": bỏ bước Lưu nháp → tạo là trình duyệt luôn, không còn nháp.
  pending: ["draft", "pending"],
  "dang-cap": ["approved", "received", "preparing", "partial"],
  done: ["done"],
  "khong-thanh": ["rejected", "cancelled"],
};

/** Ngày cần gần nhất → mới tạo nhất. Đề nghị không có ngày cần xếp sau cùng trong nhóm. */
function sortRequests(a: StockRequest, b: StockRequest): number {
  const da = a.ngay_can ?? "9999-12-31";
  const db = b.ngay_can ?? "9999-12-31";
  if (da !== db) return da < db ? -1 : 1;
  return b.created_at.localeCompare(a.created_at);
}

export function KhoDeNghiPage({
  eventTick = 0,
  loai,
}: {
  eventTick?: number;
  /** Khoá chiều theo tab (Nhập/Xuất): lọc danh sách + cố định loại khi tạo mới. */
  loai: StockRequestKind;
}) {
  const { token, user } = useAuth();
  const can = useCan();
  const canApprove = can("kho", "approve");
  const canRequest = can("kho", "request");

  const [rows, setRows] = useState<StockRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<TabId>(canApprove ? "cho-toi-duyet" : "all");
  // Lọc theo khoảng NGÀY CẦN (rỗng = không lọc đầu đó).
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  // null = đóng; "new" = soạn mới; {id} = mở đề nghị đã có; {seed} = tạo lại từ đề nghị cũ.
  const [drawer, setDrawer] = useState<
    null | { mode: "new"; seed?: SeedLine[]; loai?: StockRequestKind } | { mode: "open"; id: number }
  >(null);

  // Người duyệt vào màn là để DUYỆT → tab mặc định phải là hộp việc của họ. Chỉ chạy một lần
  // khi ma trận quyền về (caps nạp bất đồng bộ nên lần render đầu canApprove luôn false).
  const tabPinned = useRef(false);
  useEffect(() => {
    if (tabPinned.current || !canApprove) return;
    tabPinned.current = true;
    setTab("cho-toi-duyet");
  }, [canApprove]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.kho.deNghi
      .list(token, { q: q || null, loai, size: FETCH_SIZE })
      .then((r) => {
        setRows(r.items);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được danh sách đề nghị."))
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

  const meId = user?.id ?? -1;
  const pendingForMe = useMemo(
    () => rows.filter((r) => r.trang_thai === "pending" && r.nguoi_tao_id !== meId),
    [rows, meId],
  );

  function countOf(id: TabId): number {
    if (id === "all") return rows.length;
    if (id === "cho-toi-duyet") return pendingForMe.length;
    return rows.filter((r) => TAB_STATUSES[id].includes(r.trang_thai)).length;
  }

  const filtered = useMemo(() => {
    const base =
      tab === "all"
        ? rows
        : tab === "cho-toi-duyet"
          ? pendingForMe
          : rows.filter((r) => TAB_STATUSES[tab].includes(r.trang_thai));
    // Lọc theo khoảng Ngày cần. Đề nghị chưa đặt ngày cần → ẩn khi có áp bộ lọc ngày.
    const byDate = base.filter((r) => {
      if (!dateFrom && !dateTo) return true;
      if (!r.ngay_can) return false;
      if (dateFrom && r.ngay_can < dateFrom) return false;
      if (dateTo && r.ngay_can > dateTo) return false;
      return true;
    });
    return [...byDate].sort(sortRequests);
  }, [rows, tab, pendingForMe, dateFrom, dateTo]);

  useEffect(() => {
    setPage(1);
  }, [tab, q, dateFrom, dateTo]);

  const total = filtered.length;
  const shown = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const tabs: { id: TabId; label: string; alert?: boolean }[] = [
    ...(canApprove ? [{ id: "cho-toi-duyet" as TabId, label: "Chờ tôi duyệt", alert: true }] : []),
    { id: "all", label: "Tất cả" },
    { id: "pending", label: "Chờ duyệt" },
    { id: "dang-cap", label: "Đang cấp" },
    { id: "done", label: "Hoàn tất" },
    { id: "khong-thanh", label: "Không thành" },
  ];

  // Đề nghị KHÔNG gắn kho nên không có tồn để soi → bỏ hẳn cột đèn. Cột "Người" thay vào để
  // mỗi công đoạn hiện rõ AI đề nghị → AI duyệt ngay trên bảng.
  const colCount = 6;

  return (
    <>
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">Đề nghị kho</h1>
          <span className="rc__count">{rows.length} đề nghị</span>
        </div>
        <p className="rc__sub">
          Xin nhập hoặc lĩnh vật tư. Kho chỉ nhận đề nghị đã được duyệt.
        </p>
      </header>

      <div className="rc__toolbar">
        <div className="rc__search-wrapper">
          <SearchIcon />
          <input
            className="rc__search"
            placeholder="Tìm mã đề nghị / vật tư…"
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
            <PlusIcon /> Tạo đề nghị
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
              <th style={{ width: "15%" }}>Mã</th>
              <th style={{ width: "8%" }}>Loại</th>
              <th>Vật tư</th>
              <th style={{ width: "18%" }}>Người</th>
              <th style={{ width: "12%" }}>Cần ngày</th>
              <th style={{ width: "14%" }}>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="rc-skel__row">
                  {Array.from({ length: colCount }).map((__, c) => (
                    <td key={c}>
                      <span className="rc-skel" style={{ width: c === 2 ? "80%" : "55%" }} />
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
                        ? "Chưa có đề nghị nào. Tạo đề nghị để xin nhập hoặc lĩnh vật tư."
                        : "Không có đề nghị nào ở trạng thái này."}
                    </p>
                    {rows.length === 0 ? (
                      canRequest && (
                        <Button variant="ghost" onClick={() => setDrawer({ mode: "new", loai })}>
                          <PlusIcon /> Tạo đề nghị
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
                // "Người" = trọn chuỗi trách nhiệm: ai đề nghị → ai duyệt. Đề nghị chưa duyệt
                // thì hiện "Chờ duyệt"; bị từ chối thì nêu người từ chối để không mập mờ.
                const decided = r.nguoi_duyet_ten;
                const reply =
                  r.trang_thai === "rejected"
                    ? `Từ chối: ${decided ?? "—"}`
                    : decided
                      ? `Duyệt: ${decided}`
                      : "Chờ duyệt";
                return (
                  <tr
                    key={r.id}
                    className="rc__row"
                    onClick={() => setDrawer({ mode: "open", id: r.id })}
                  >
                    <td className="rc__nowrap">
                      <span className="rc__code-badge">{r.ma}</span>
                    </td>
                    <td>
                      <span
                        className={`badge-sem badge-sem--${r.loai === "NHAP" ? "moss" : "plum"}`}
                      >
                        {r.loai === "NHAP" ? "NHẬP" : "XUẤT"}
                      </span>
                    </td>
                    <td>
                      <div className="rc__name">
                        {first?.material_name ?? first?.ten_tu_do ?? "—"}
                      </div>
                      {r.lines.length > 1 && (
                        <div className="rc__muted kho-hint">+{r.lines.length - 1} mã</div>
                      )}
                    </td>
                    <td>
                      <div className="rc__name">{r.nguoi_tao_ten ?? "—"}</div>
                      <div className="rc__muted kho-hint">{reply}</div>
                    </td>
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
          <span className="kho-pager__page">{total} đề nghị</span>
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
          canRequest={canRequest}
          canApprove={canApprove}
          onClone={(lines, loai) => setDrawer({ mode: "new", seed: lines, loai })}
          onClose={() => setDrawer(null)}
          onSaved={() => {
            setDrawer(null);
            load();
          }}
        />
      )}
    </>
  );
}

// ── DRAWER ────────────────────────────────────────────────────────────────────

export interface SeedLine {
  /** 0 = hàng mới chưa gắn mã (dùng `ten_tu_do`); >0 = hàng đã có mã. */
  material_id: number;
  material_code: string | null;
  material_name: string | null;
  /** Tên hàng mới gõ tự do (khi material_id = 0). Thủ kho gắn/tạo mã ở bước phiếu. */
  ten_tu_do: string | null;
  dvt: string;
  sl_de_nghi: number;
  /** Đơn giá NHẬP người đề nghị khai (chỉ đề nghị NHẬP). Phiếu kế thừa; kho không sửa. */
  don_gia: number | null;
  /** Quy đổi đơn vị người đề nghị khai (1 don_vi_phu = he_so_quy_doi × dvt tồn). */
  don_vi_phu: string | null;
  he_so_quy_doi: number | null;
  ghi_chu: string | null;
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
    material_id: seed?.material_id ?? 0,
    material_code: seed?.material_code ?? null,
    material_name: seed?.material_name ?? null,
    ten_tu_do: seed?.ten_tu_do ?? null,
    dvt: seed?.dvt ?? "",
    sl_de_nghi: seed?.sl_de_nghi ?? 0,
    don_gia: seed?.don_gia ?? null,
    don_vi_phu: seed?.don_vi_phu ?? null,
    he_so_quy_doi: seed?.he_so_quy_doi ?? null,
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
  canRequest: boolean;
  canApprove: boolean;
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
  canRequest,
  canApprove,
  onClone,
  onClose,
  onSaved,
}: RequestDrawerProps) {
  const [req, setReq] = useState<StockRequest | null>(null);
  const [loading, setLoading] = useState(requestId != null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [loai, setLoai] = useState<StockRequestKind>(seedLoai ?? "XUAT");
  const [ngayCan, setNgayCan] = useState("");
  const [ghiChu, setGhiChu] = useState("");
  const [lines, setLines] = useState<DraftLine[]>(() =>
    seed?.length ? seed.map((s) => newLine(s)) : [newLine()],
  );

  const [dirty, setDirty] = useState(false);
  const [askDiscard, setAskDiscard] = useState(false);
  const [askCancel, setAskCancel] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  // SL duyệt từng dòng, điền sẵn = SL đề nghị (mặc định duyệt nguyên số). Duyệt-cắt = sửa số
  // rồi bấm Duyệt — GỘP 1 bước, không còn "Duyệt → Xác nhận duyệt".
  const [approveQty, setApproveQty] = useState<Record<number, string>>({});
  const [printing, setPrinting] = useState(false);

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
            material_id: l.material_id ?? 0,
            material_code: l.material_code,
            material_name: l.material_name,
            ten_tu_do: l.ten_tu_do,
            dvt: l.dvt,
            sl_de_nghi: l.sl_de_nghi,
            don_gia: l.don_gia,
            don_vi_phu: l.don_vi_phu,
            he_so_quy_doi: l.he_so_quy_doi,
            ghi_chu: l.ghi_chu,
            sl_duyet: l.sl_duyet,
            sl_da_ung: l.sl_da_ung,
            ly_do_thieu: l.ly_do_thieu,
          })),
        );
        setDirty(false);
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Không tải được đề nghị."),
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
  const editable = (isNew || status === "draft" || status === "pending") && isOwner && canRequest;
  // Người này có thể duyệt đề nghị ĐANG mở: chờ duyệt + có quyền + KHÔNG phải người tạo.
  // Bật cột "SL duyệt" inline + nút Duyệt (không còn bước trung gian).
  const canApproveNow = status === "pending" && canApprove && !isOwner;
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

  function pickMaterial(key: string, m: StockMaterialOption) {
    // Trùng mã hàng: chặn ngay ở FE với ĐÚNG câu backend trả, để người dùng không gặp
    // hai cách diễn đạt khác nhau cho cùng một luật.
    if (lines.some((l) => l.key !== key && l.material_id === m.id)) {
      setError("Một mã hàng chỉ được xuất hiện 1 dòng — gộp số lượng lại.");
      return;
    }
    setError(null);
    patchLine(key, {
      material_id: m.id,
      material_code: m.code,
      material_name: m.name,
      // Đã chọn mã sẵn → xoá cờ hàng-mới.
      ten_tu_do: null,
      dvt: m.unit ?? "",
      // Prefill quy đổi từ mặt hàng (nếu mã đã khai) để người đề nghị thấy/sửa được.
      don_vi_phu: m.don_vi_phu ?? null,
      he_so_quy_doi: m.he_so_quy_doi ?? null,
    });
  }

  // Hàng MỚI: người đề nghị KHÔNG tạo mã — chỉ gõ tên tự do, thủ kho gắn/tạo mã ở phiếu.
  function nameFreeText(key: string, name: string) {
    setDirty(true);
    setError(null);
    setLines((prev) =>
      prev.map((l) =>
        l.key === key
          ? { ...l, material_id: 0, material_code: null, material_name: name, ten_tu_do: name }
          : l,
      ),
    );
  }

  function payloadLines(): StockRequestLineInput[] {
    const isNhap = loai === "NHAP";
    return lines
      .filter(
        (l) =>
          (l.material_id > 0 || (l.ten_tu_do ?? "").trim()) && Number(l.sl_de_nghi) > 0,
      )
      .map((l) => {
        // Đơn giá + QUY ĐỔI chỉ gửi cho đề nghị NHẬP (người đề nghị khai). XUẤT không có.
        const dvp = isNhap ? (l.don_vi_phu ?? "").trim() || null : null;
        const base = {
          dvt: l.dvt || "cái",
          sl_de_nghi: Number(l.sl_de_nghi),
          don_gia: isNhap && l.don_gia != null ? Number(l.don_gia) : null,
          don_vi_phu: dvp,
          he_so_quy_doi: dvp && l.he_so_quy_doi ? Number(l.he_so_quy_doi) : null,
          ghi_chu: l.ghi_chu || null,
        };
        return l.material_id > 0
          ? { material_id: l.material_id, ...base }
          : { ten_tu_do: (l.ten_tu_do ?? "").trim(), ...base };
      });
  }

  async function save(thenSubmit: boolean) {
    const body = payloadLines();
    if (!body.length) {
      setError("Thêm ít nhất một dòng vật tư có số lượng lớn hơn 0.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      let saved: StockRequest;
      if (req == null) {
        saved = await api.kho.deNghi.create(token, {
          loai,
          // Số đề nghị LUÔN tự sinh (DNN/DNX####) — không cho tự nhập.
          ngay_can: ngayCan || null,
          ghi_chu: ghiChu || null,
          lines: body,
        });
      } else {
        saved = await api.kho.deNghi.update(token, req.id, {
          ngay_can: ngayCan || null,
          ghi_chu: ghiChu || null,
          lines: body,
        });
      }
      if (thenSubmit) await api.kho.deNghi.submit(token, saved.id);
      setDirty(false);
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không lưu được đề nghị.");
    } finally {
      setBusy(false);
    }
  }

  async function act(fn: () => Promise<unknown>, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setDirty(false);
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  // --- Duyệt (1 bước, sửa SL duyệt inline) — ô trống = giữ nguyên SL đề nghị ---
  const approveTotal = lines.reduce(
    (s, l) => s + (l.lineId != null ? Number(approveQty[l.lineId] ?? l.sl_de_nghi) : 0),
    0,
  );

  async function confirmApprove() {
    if (!req) return;
    const map: Record<number, number> = {};
    for (const l of lines) {
      if (l.lineId == null) continue;
      const raw = Number(approveQty[l.lineId] ?? l.sl_de_nghi);
      map[l.lineId] = Math.max(0, Math.min(Number.isFinite(raw) ? raw : 0, l.sl_de_nghi));
    }
    await act(() => api.kho.deNghi.approve(token, req.id, map), "Không duyệt được đề nghị.");
  }

  function requestClose() {
    if (dirty) setAskDiscard(true);
    else onClose();
  }

  const kicker = loai === "NHAP" ? "ĐỀ NGHỊ NHẬP" : "ĐỀ NGHỊ XUẤT";

  return (
    <>
      <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={requestClose}>
        <aside className="rc-drawer rc-drawer--mid" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">{kicker}</div>
            <h2 className="rc-drawer__title">{req?.ma ?? "Đề nghị mới"}</h2>
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
            Đề nghị: {req.nguoi_tao_ten ?? "—"} · {fmtDate(req.created_at)}
            {req.nguoi_duyet_ten
              ? ` → Duyệt: ${req.nguoi_duyet_ten} · ${fmtDate(req.duyet_luc)}`
              : req.trang_thai === "pending"
                ? " → Chờ duyệt"
                : ""}
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
                  <div className="rc-field">
                    <span className="rc-field__label">Loại</span>
                    <div style={{ display: "flex", gap: "var(--sp-1)" }}>
                      {/* Chiều do TAB (Nhập/Xuất) quyết định — CHỈ hiện loại đang chọn, không hiện
                          nút loại kia (đề nghị đã cố định chiều). */}
                      <button type="button" className="seg is-active" disabled>
                        {loai === "XUAT" ? "Xuất (lĩnh)" : "Nhập"}
                      </button>
                    </div>
                  </div>
                  <div className="rc-field">
                    <label className="rc-field__label" htmlFor="kho-ngay-can">
                      Ngày cần
                    </label>
                    <input
                      id="kho-ngay-can"
                      type="date"
                      className="rc-input"
                      value={ngayCan}
                      disabled={!editable}
                      onChange={(e) => touch(setNgayCan)(e.target.value)}
                    />
                  </div>
                </div>
              </section>

              <section className="rc-sec">
                <h3 className="rc-sec__title">Vật tư đề nghị</h3>
                <div className="kho-lines__wrap">
                  <table className="kho-lines">
                    <thead className="kho-lines__head">
                      <tr>
                        <th style={{ minWidth: 180 }}>Vật tư</th>
                        <th style={{ width: 76 }}>ĐVT</th>
                        <th className="kho-num" style={{ width: 100 }}>
                          SL đề nghị
                        </th>
                        {/* SL đã cấp (sl_da_ung) — chỉ hiện khi đề nghị đã vào luồng cấp phát. */}
                        {showReply && (
                          <th className="kho-num" style={{ width: 90 }}>
                            SL cấp
                          </th>
                        )}
                        {/* Đơn giá CHỈ ở đề nghị NHẬP — người đề nghị khai (họ biết giá NCC);
                            phiếu kế thừa, kho không sửa. XUẤT lấy giá vốn đích danh của lô. */}
                        {loai === "NHAP" && (
                          <th className="kho-num" style={{ width: 120 }}>
                            Đơn giá
                          </th>
                        )}
                        {canApproveNow && (
                          <th className="kho-num" style={{ width: 118 }}>
                            SL duyệt
                          </th>
                        )}
                        {editable && <th style={{ width: 32 }} aria-label="Xóa" />}
                      </tr>
                    </thead>
                    <tbody>
                      {lines.map((l) => {
                        const cut =
                          canApproveNow && l.lineId != null
                            ? l.sl_de_nghi - (Number(approveQty[l.lineId] ?? l.sl_de_nghi) || 0)
                            : 0;
                        return (
                          <Fragment key={l.key}>
                          <tr>
                            <td>
                              {editable ? (
                                <MaterialCombobox
                                  token={token}
                                  materialName={l.material_name}
                                  onPick={(m) => pickMaterial(l.key, m)}
                                  // Gõ tên rồi "＋ Thêm" = ghi thẳng tên vật tư, KHÔNG tạo mã.
                                  // Thủ kho gắn/tạo mã ở bước lập phiếu (người đề nghị không cần biết).
                                  // XUẤT: chỉ lĩnh hàng ĐÃ có trong kho → không cho tạo hàng mới.
                                  createLabel="Thêm"
                                  allowCreate={loai === "NHAP"}
                                  onCreate={(nm) => nameFreeText(l.key, nm)}
                                />
                              ) : (
                                <>
                                  <div className="kho-lines__name">
                                    {l.material_name ?? l.ten_tu_do ?? "—"}
                                  </div>
                                  <div className="kho-lines__code">
                                    {l.material_code ?? (l.ten_tu_do ? "Hàng mới" : "")}
                                  </div>
                                </>
                              )}
                            </td>
                            <td>
                              {/* Hàng có mã → ĐVT khoá theo mã. Hàng mới → người đề nghị tự gõ. */}
                              {editable && l.material_id === 0 ? (
                                <input
                                  className="rc-input"
                                  style={{ width: 68 }}
                                  value={l.dvt}
                                  onChange={(e) => patchLine(l.key, { dvt: e.target.value })}
                                  placeholder="cái…"
                                  aria-label="Đơn vị tính"
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
                                  aria-label="Số lượng đề nghị"
                                />
                              ) : (
                                fmtQty(l.sl_de_nghi)
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
                            {canApproveNow && (
                              <td className="kho-num">
                                <input
                                  type="number"
                                  min={0}
                                  max={l.sl_de_nghi}
                                  step="any"
                                  className="rc-input kho-num"
                                  value={
                                    l.lineId != null
                                      ? (approveQty[l.lineId] ?? String(l.sl_de_nghi))
                                      : ""
                                  }
                                  onChange={(e) => {
                                    if (l.lineId == null) return;
                                    const raw = Number(e.target.value);
                                    const clamped = Number.isFinite(raw)
                                      ? Math.max(0, Math.min(raw, l.sl_de_nghi))
                                      : 0;
                                    setApproveQty((prev) => ({
                                      ...prev,
                                      [l.lineId as number]: String(clamped),
                                    }));
                                  }}
                                  aria-label="Số lượng duyệt"
                                />
                                {cut > 0 && (
                                  <span className="badge-sem badge-sem--amber">
                                    cắt {fmtQty(cut)}
                                  </span>
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
                {canApproveNow && approveTotal === 0 && (
                  <p className="kho-hint kho-hint--amber">
                    Duyệt 0 cho tất cả — hãy dùng Từ chối.
                  </p>
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
                          <span className="kho-reply__name">{l.material_name ?? "—"}</span> — Duyệt{" "}
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
            </>
          )}
        </div>

        <footer className="rc-drawer__foot">
          <RequestFooter
            status={isNew ? "draft" : status}
            isNew={isNew}
            isOwner={!!isOwner}
            canRequest={canRequest}
            canApprove={canApprove}
            busy={busy}
            // Duyệt 0 cho mọi dòng → ẩn nút Duyệt (buộc dùng Từ chối); hint đã hiện ở bảng.
            approveDisabled={approveTotal === 0}
            onCancelRequest={() => setAskCancel(true)}
            onSaveDraft={() => save(false)}
            onSubmit={() => save(true)}
            onSave={() => save(false)}
            onReject={() => setRejecting(true)}
            onApprove={confirmApprove}
            onPrint={() => setPrinting(true)}
            onClone={() =>
              onClone(
                lines.map((l) => ({
                  material_id: l.material_id,
                  material_code: l.material_code,
                  material_name: l.material_name,
                  ten_tu_do: l.ten_tu_do,
                  dvt: l.dvt,
                  sl_de_nghi: l.sl_de_nghi,
                  don_gia: l.don_gia,
                  don_vi_phu: l.don_vi_phu,
                  he_so_quy_doi: l.he_so_quy_doi,
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

      <ConfirmDialog
        open={askCancel}
        title="Hủy đề nghị này?"
        message="Đề nghị đã hủy không dùng lại được. Muốn xin tiếp thì tạo đề nghị mới."
        confirmLabel="Hủy đề nghị"
        cancelLabel="Giữ lại"
        danger
        busy={busy}
        onCancel={() => setAskCancel(false)}
        onConfirm={() => {
          setAskCancel(false);
          if (req) void act(() => api.kho.deNghi.cancel(token, req.id), "Không hủy được đề nghị.");
        }}
      />

      <ConfirmDialog
        open={rejecting}
        title="Từ chối đề nghị?"
        confirmLabel="Từ chối đề nghị"
        danger
        busy={busy}
        confirmDisabled={!rejectReason.trim()}
        onCancel={() => setRejecting(false)}
        onConfirm={() => {
          if (!req) return;
          setRejecting(false);
          void act(
            () => api.kho.deNghi.reject(token, req.id, rejectReason.trim()),
            "Không từ chối được đề nghị.",
          );
        }}
      >
        <div className="rc-field">
          <label className="rc-field__label" htmlFor="kho-reject">
            Lý do từ chối <em>*</em>
          </label>
          <textarea
            id="kho-reject"
            className="rc-textarea"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Vì sao không duyệt? Người đề nghị sẽ đọc câu này."
          />
        </div>
      </ConfirmDialog>

      {printing && req && (
        <RequestPrint req={req} lines={lines} onClose={() => setPrinting(false)} />
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
  canApprove: boolean;
  busy: boolean;
  approveDisabled?: boolean;
  onCancelRequest: () => void;
  onSaveDraft: () => void;
  onSubmit: () => void;
  onSave: () => void;
  onReject: () => void;
  onApprove: () => void;
  onPrint: () => void;
  onClone: () => void;
  onClose: () => void;
}) {
  const { status, isNew, isOwner, canRequest, canApprove, busy } = props;

  if ((isNew || status === "draft") && isOwner && canRequest) {
    // Bỏ "Lưu nháp": tạo đề nghị là trình duyệt luôn, không giữ bước nháp trung gian.
    return (
      <>
        {!isNew && (
          <button type="button" className="btn btn--ghost" onClick={props.onCancelRequest}>
            Hủy đề nghị
          </button>
        )}
        <Button variant="accent" onClick={props.onSubmit} loading={busy}>
          Lưu &amp; Trình duyệt
        </Button>
      </>
    );
  }

  if (status === "pending" && isOwner && canRequest) {
    return (
      <>
        <button type="button" className="btn btn--ghost" onClick={props.onCancelRequest}>
          Hủy đề nghị
        </button>
        <Button variant="accent" onClick={props.onSave} loading={busy}>
          Lưu thay đổi
        </Button>
        {/* Người duyệt kiêm người tạo: nút Duyệt ẨN HẲN, không disable — bấm-rồi-lỗi là cách
            tệ nhất để dạy một luật. */}
        {canApprove && <span className="kho-hint">Không tự duyệt đề nghị của mình.</span>}
      </>
    );
  }

  if (status === "pending" && canApprove && !isOwner) {
    return (
      <>
        <button type="button" className="btn btn--danger" onClick={props.onReject}>
          Từ chối
        </button>
        {/* Duyệt trực tiếp với SL duyệt đang hiện inline (mặc định = SL đề nghị). Ẩn khi tổng
            duyệt = 0 — lúc đó phải Từ chối. */}
        {!props.approveDisabled && (
          <Button variant="accent" onClick={props.onApprove} loading={busy}>
            Duyệt
          </Button>
        )}
      </>
    );
  }

  if ((status === "rejected" || status === "cancelled") && isOwner && canRequest) {
    return (
      <>
        <Button variant="accent" onClick={props.onClone}>
          Tạo lại từ đề nghị này
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
          In đề nghị
        </button>
      )}
      <button type="button" className="btn btn--secondary" onClick={props.onClose}>
        Đóng
      </button>
    </>
  );
}

/** Bản in giấy đề nghị — KHÔNG cột giá, KHÔNG cột tồn (người ký duyệt không cần và
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
    req.loai === "NHAP" ? "GIẤY ĐỀ NGHỊ NHẬP KHO" : "GIẤY ĐỀ NGHỊ LĨNH VẬT TƯ";
  return (
    <PrintSheet title={title} docNo={req.ma} docDate={fmtDate(req.created_at)} onClose={onClose}>
      <div className="kho-print__meta">
        <span>
          <b>Bộ phận:</b> {req.bo_phan_ten ?? "…"}
        </span>
        <span>
          <b>Người đề nghị:</b> {req.nguoi_tao_ten ?? "…"}
        </span>
        <span>
          <b>Ngày cần:</b> {req.ngay_can ? fmtDateISO(req.ngay_can) : "…"}
        </span>
      </div>
      {/* Trọn chuỗi trách nhiệm trên phiếu in: ai đề nghị (trên) → ai duyệt (đây). */}
      <div className="kho-print__meta">
        <span>
          <b>Người duyệt:</b>{" "}
          {req.nguoi_duyet_ten
            ? `${req.nguoi_duyet_ten}${req.duyet_luc ? ` · ${fmtDate(req.duyet_luc)}` : ""}`
            : "Chờ duyệt"}
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
            <th style={{ width: 90 }}>SL đề nghị</th>
            <th style={{ width: 90 }}>SL duyệt</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={l.key}>
              <td>{i + 1}</td>
              <td>{l.material_name ?? l.ten_tu_do ?? ""}</td>
              <td>{l.material_code ?? (l.ten_tu_do ? "(hàng mới)" : "")}</td>
              <td>{l.dvt}</td>
              <td style={{ textAlign: "right" }}>{fmtQty(l.sl_de_nghi)}</td>
              <td style={{ textAlign: "right" }}>{l.sl_duyet > 0 ? fmtQty(l.sl_duyet) : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="kho-print__signs">
        {["Người đề nghị", "Phụ trách bộ phận", "Thủ kho"].map((s) => (
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
