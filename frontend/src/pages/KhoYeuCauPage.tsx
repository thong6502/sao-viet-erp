// Màn "Hộp yêu cầu kho" — thủ kho / quản lý kho / kế toán kho (scope `all`).
//
// Đề nghị đã duyệt VÀ phiếu nhập/xuất nằm CÙNG MỘT MÀN, phân bằng tab: với người trong kho
// đây là một việc liên tục (nhận đề nghị → lấy hàng theo lô → ghi sổ), tách hai màn là bắt họ
// nhảy qua lại giữa hai danh sách của cùng một chứng từ.
//
// Hai cột nhạy cảm — "Tồn khả dụng" và "Giá vốn" — KHÔNG render khi thiếu quyền: cột biến mất
// khỏi <thead> chứ không hiện "—". Dấu gạch vẫn là một câu trả lời ("chỗ này có số, bạn không
// được xem"), còn ở đây phải im lặng hoàn toàn.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type HangLoai,
  type StockAllocationLine,
  type StockLot,
  type StockRequest,
  type StockRequestKind,
  type StockRequestLine,
  type StockRequestStatus,
  type StockThreshold,
  type StockVoucher,
  type StockVoucherAttachment,
  type StockVoucherLineInput,
} from "../api/client";
import { crud } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DiscardChangesDialog } from "../components/DiscardChangesDialog";
import { MaterialCombobox } from "../components/MaterialCombobox";
import { Select } from "../components/Select";
import { StockLevelChip } from "../components/StockLevelChip";
import { fmtDate, fmtDateISO, money } from "../utils/format";
import { printStockVoucher, type StockVoucherPrintData } from "../utils/printStockVoucher";
import {
  RequestStatusBadge,
  VoucherStatusBadge,
  fmtQty,
  isOverdue,
  readStoredKho,
  todayISO,
  writeStoredKho,
} from "./khoShared";
import "./rebuild-catalog.css";
import "./kho-request.css";

const KHO_KEY = "kho.yeu-cau.kho-id";
const PAGE_SIZE = 8;
const FETCH_SIZE = 200;

type TabId = "can-cap" | "dang-cap" | "done" | "da-huy";

const TAB_STATUSES: Record<TabId, StockRequestStatus[]> = {
  "can-cap": ["approved"],
  "dang-cap": ["received", "preparing", "partial"],
  done: ["done"],
  "da-huy": ["cancelled"],
};
// Một lần gọi cho cả 4 tab đề nghị → số trên tab luôn khớp bảng, không lệch giữa các lần fetch.
const INBOX_STATUSES: StockRequestStatus[] = [
  "approved",
  "received",
  "preparing",
  "partial",
  "done",
  "cancelled",
];
const FULFILLABLE: StockRequestStatus[] = ["approved", "received", "preparing", "partial"];

export interface KhoOption {
  id: number;
  ma: string;
  ten: string;
}

/** Quá hạn → ngày cần → mã. */
function sortInbox(a: StockRequest, b: StockRequest): number {
  const late = (r: StockRequest) => (isOverdue(r.ngay_can, r.trang_thai) ? 0 : 1);
  if (late(a) !== late(b)) return late(a) - late(b);
  const da = a.ngay_can ?? "9999-12-31";
  const db = b.ngay_can ?? "9999-12-31";
  if (da !== db) return da < db ? -1 : 1;
  return a.ma.localeCompare(b.ma);
}

function progressOf(r: StockRequest): { done: number; total: number; pct: number } {
  const total = r.lines.reduce((s, l) => s + l.sl_duyet, 0);
  const done = r.lines.reduce((s, l) => s + l.sl_da_ung, 0);
  return { done, total, pct: total > 0 ? Math.min(100, (done / total) * 100) : 0 };
}

export function KhoYeuCauPage({
  eventTick = 0,
  loai,
}: {
  eventTick?: number;
  /** Khoá chiều theo tab (Nhập/Xuất): lọc đề nghị + phiếu theo loai. */
  loai: StockRequestKind;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("kho", "create");
  const canPost = can("kho", "post");
  const canViewStock = can("kho", "view_stock");
  const canViewCost = can("kho", "view_cost");

  const [khoList, setKhoList] = useState<KhoOption[]>([]);
  const [khoId, setKhoId] = useState<number | null>(() => readStoredKho(KHO_KEY));
  const [requests, setRequests] = useState<StockRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<TabId>("can-cap");
  const [page, setPage] = useState(1);

  const [openRequest, setOpenRequest] = useState<number | null>(null);
  const [creatingFor, setCreatingFor] = useState<StockRequest | null>(null);
  const [openVoucher, setOpenVoucher] = useState<number | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    crud("/api/kho")
      .list(token, { active: true })
      .then((r) => {
        if (cancelled) return;
        const items = r.items.map((w) => ({
          id: Number(w.id),
          ma: String(w.ma),
          ten: String(w.ten),
        }));
        setKhoList(items);
        setKhoId((prev) => {
          if (prev != null && items.some((w) => w.id === prev)) return prev;
          return items.length ? items[0].id : null;
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    writeStoredKho(KHO_KEY, khoId);
  }, [khoId]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    // KHÔNG lọc theo kho: đề nghị giờ không gắn kho (kho quyết ở phiếu) → mọi đề nghị đã duyệt
    // đều vào chung một hộp cho thủ kho xử lý. Ô kho ở toolbar chỉ là kho MẶC ĐỊNH khi lập phiếu.
    api.kho.deNghi
      .list(token, {
        q: q || null,
        loai,
        trang_thai: INBOX_STATUSES,
        size: FETCH_SIZE,
      })
      .then((r) => {
        setRequests(r.items);
        setError(null);
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Không tải được hộp yêu cầu kho."),
      )
      .finally(() => setLoading(false));
  }, [token, q, loai, khoId]);

  // "Lập phiếu" / "Xem phiếu": đề nghị đã có phiếu ĐANG CHỜ GHI SỔ (`open_voucher_id`) thì MỞ LẠI
  // đúng phiếu đó — thấy nguyên dữ liệu đã nhập + Ghi sổ/Hủy — thay vì đẻ ra phiếu trống (mất dữ
  // liệu + tạo trùng). Chưa có mới mở form lập mới.
  const openFulfil = useCallback((r: StockRequest) => {
    setOpenRequest(null);
    if (r.open_voucher_id != null) setOpenVoucher(r.open_voucher_id);
    else setCreatingFor(r);
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    if (eventTick > 0) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventTick]);

  useEffect(() => {
    setPage(1);
  }, [tab, q, khoId]);

  function countOf(id: TabId): number {
    return requests.filter((r) => TAB_STATUSES[id].includes(r.trang_thai)).length;
  }

  const shownRequests = useMemo(
    () => requests.filter((r) => TAB_STATUSES[tab].includes(r.trang_thai)).sort(sortInbox),
    [requests, tab],
  );

  const total = shownRequests.length;
  const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const slice = <T,>(arr: T[]) => arr.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const pageRequests = slice(shownRequests);

  const tabs: { id: TabId; label: string }[] = [
    { id: "can-cap", label: "Cần cấp" },
    { id: "dang-cap", label: "Đang cấp" },
    { id: "done", label: "Hoàn tất" },
    { id: "da-huy", label: "Đã hủy" },
  ];

  // Cột đề nghị: 8 khi có nút Lập phiếu, 7 khi không (đã bỏ cột Tồn — đề nghị không gắn kho).
  const reqCols = canCreate ? 8 : 7;

  return (
    <>
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">Phiếu từ đề nghị</h1>
          <span className="rc__count">{requests.length} đề nghị</span>
        </div>
        <p className="rc__sub">Đề nghị đã duyệt chờ kho cấp, và phiếu nhập/xuất đã lập.</p>
      </header>

      <div className="rc__toolbar">
        <div className="rc__search-wrapper">
          <SearchIcon />
          <input
            className="rc__search"
            placeholder="Tìm mã đề nghị / số phiếu / vật tư…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        {/* LỌC TRẠNG THÁI — dropdown thay dải tab cho gọn. */}
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
        {/* Kho là BẮT BUỘC ở màn này: không biết kho thì không tra được lô, không lập được phiếu. */}
        <div className="kho-picker">
          <Select
            options={khoList.map((w) => ({ value: w.id, label: w.ten, hint: w.ma }))}
            value={khoId}
            onChange={setKhoId}
            ariaLabel="Kho"
            placeholder="Chọn kho"
          />
        </div>
        <div className="rc__spacer" />
      </div>

      {!khoId && !loading && (
        <div className="banner banner--warn" style={{ marginBottom: "var(--sp-4)" }}>
          <span>Chọn kho ở thanh trên để lập phiếu theo đúng kho.</span>
        </div>
      )}

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
        {(
          <table className="rc__table rc__table--fixed">
            <thead>
              <tr>
                <th style={{ width: "13%" }}>Mã</th>
                <th style={{ width: "7%" }}>Loại</th>
                <th style={{ width: "15%" }}>Bộ phận · Người</th>
                <th>Vật tư</th>
                <th style={{ width: "12%" }}>Tiến độ</th>
                <th style={{ width: "11%" }}>Cần ngày</th>
                <th style={{ width: "12%" }}>Trạng thái</th>
                {canCreate && <th className="rc__actcol" style={{ width: "10%" }} />}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonRows cols={reqCols} />
              ) : shownRequests.length === 0 ? (
                <EmptyRow
                  cols={reqCols}
                  text={
                    requests.length === 0
                      ? "Chưa có đề nghị nào được duyệt. Đề nghị chỉ vào hộp này sau khi bộ phận duyệt."
                      : "Không có đề nghị nào ở trạng thái này."
                  }
                  onClear={requests.length === 0 ? undefined : () => setTab("can-cap")}
                />
              ) : (
                <>
                  {pageRequests.map((r) => {
                  const p = progressOf(r);
                  const overdue = isOverdue(r.ngay_can, r.trang_thai);
                  return (
                    <tr
                      key={r.id}
                      className={`rc__row${overdue ? " kho-row--overdue" : ""}`}
                      onClick={() => setOpenRequest(r.id)}
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
                        <div>{r.nguoi_tao_ten ?? "—"}</div>
                        <div className="rc__muted">{r.bo_phan_ten ?? "—"}</div>
                      </td>
                      <td>
                        <div
                          className="rc__name kho-name-clamp"
                          title={r.lines[0]?.hang_ten ?? undefined}
                        >
                          {r.lines[0]?.hang_ten ?? "—"}
                        </div>
                        {r.lines.length > 1 && (
                          <div className="rc__muted">+{r.lines.length - 1} mã</div>
                        )}
                      </td>
                      <td>
                        <div className="kho-prog">
                          <span className="kho-prog__track">
                            <span
                              className={`kho-prog__bar${p.pct >= 100 ? "" : p.pct > 0 ? " kho-prog__bar--partial" : " kho-prog__bar--none"}`}
                              style={{ width: `${p.pct}%` }}
                            />
                          </span>
                          <span className="kho-prog__num">
                            {fmtQty(p.done)}/{fmtQty(p.total)}
                          </span>
                        </div>
                      </td>
                      <td className={`rc__nowrap${overdue ? " kho-overdue" : ""}`}>
                        {r.ngay_can ? fmtDateISO(r.ngay_can) : "—"}
                      </td>
                      <td>
                        <RequestStatusBadge status={r.trang_thai} />
                      </td>
                      {canCreate && (
                        <td className="rc__actcol" onClick={(e) => e.stopPropagation()}>
                          {FULFILLABLE.includes(r.trang_thai) && (
                            <button
                              type="button"
                              className="rc__link-btn"
                              onClick={() => openFulfil(r)}
                            >
                              {r.open_voucher_id != null ? "Xem phiếu" : "Lập phiếu"}
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                  })}
                  {Array.from({ length: Math.max(0, PAGE_SIZE - pageRequests.length) }).map((_, i) => (
                    <tr key={`filler-${i}`} className="rc__filler" aria-hidden="true">
                      <td colSpan={reqCols}>
                        <div className="rc__name">&nbsp;</div>
                        <div className="rc__muted">&nbsp;</div>
                      </td>
                    </tr>
                  ))}
                </>
              )}
            </tbody>
          </table>
        )}
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

      {openRequest != null && token && (
        <InboxRequestDrawer
          key={`inbox-${openRequest}`}
          token={token}
          khoId={khoId}
          requestId={openRequest}
          canCreate={canCreate}
          canViewStock={canViewStock}
          onClose={() => setOpenRequest(null)}
          onCreateVoucher={openFulfil}
        />
      )}

      {creatingFor && token && khoId != null && (
        <VoucherCreateDrawer
          key={`mk-${creatingFor.id}`}
          token={token}
          request={creatingFor}
          khoList={khoList}
          initialKhoId={khoId}
          canPost={canPost}
          onClose={() => setCreatingFor(null)}
          onSaved={() => {
            setCreatingFor(null);
            load();
          }}
        />
      )}

      {openVoucher != null && token && (
        <VoucherDrawer
          key={`v-${openVoucher}`}
          token={token}
          voucherId={openVoucher}
          canCreate={canCreate}
          canPost={canPost}
          canViewCost={canViewCost}
          onClose={() => setOpenVoucher(null)}
          onChanged={load}
        />
      )}
    </>
  );
}

// ── DRAWER: chi tiết đề nghị (góc nhìn KHO) ──────────────────────────────────

export function InboxRequestDrawer({
  token,
  khoId,
  requestId,
  canCreate,
  canViewStock,
  onClose,
  onCreateVoucher,
}: {
  token: string;
  khoId: number | null;
  requestId: number;
  canCreate: boolean;
  canViewStock: boolean;
  onClose: () => void;
  onCreateVoucher: (r: StockRequest) => void;
}) {
  const [req, setReq] = useState<StockRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    api.kho.deNghi
      .get(token, requestId, khoId)
      .then((r) => {
        setReq(r);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được đề nghị."))
      .finally(() => setLoading(false));
  }, [token, requestId, khoId]);

  useEffect(reload, [reload]);

  const canFulfill = canCreate && req != null && FULFILLABLE.includes(req.trang_thai);

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer rc-drawer--mid" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">
              {req?.loai === "NHAP" ? "ĐỀ NGHỊ NHẬP" : "ĐỀ NGHỊ XUẤT"}
            </div>
            <h2 className="rc-drawer__title">{req?.ma ?? "Đang tải…"}</h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
            {req && <RequestStatusBadge status={req.trang_thai} />}
            <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
              ✕
            </button>
          </div>
        </header>

        {req && (
          <div className="kho-meta">
            {req.nguoi_tao_ten ?? "—"}
            {req.bo_phan_ten ? ` · ${req.bo_phan_ten}` : ""} · {fmtDate(req.created_at)}
            {req.nguoi_duyet_ten
              ? ` → Duyệt: ${req.nguoi_duyet_ten} · ${fmtDate(req.duyet_luc)}`
              : ""}
          </div>
        )}

        <div className="rc-drawer__body">
          {error && (
            <div className="banner banner--error" role="alert">
              <span>{error}</span>
            </div>
          )}
          {loading || !req ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
              {Array.from({ length: 4 }).map((_, i) => (
                <span key={i} className="rc-skel" style={{ width: `${90 - i * 12}%` }} />
              ))}
            </div>
          ) : (
            <>
              {req.trang_thai === "cancelled" && req.ly_do_huy && (
                <div className="banner banner--warn" role="status">
                  <span>
                    <b>Đã hủy</b> — Lý do: {req.ly_do_huy}
                  </span>
                </div>
              )}
              <section className="rc-sec">
                <h3 className="rc-sec__title">Yêu cầu</h3>
                <div className="rc-grid">
                  <Readout
                    label="Ngày cần"
                    value={req.ngay_can ? fmtDateISO(req.ngay_can) : "—"}
                  />
                  <div className="rc-field rc-field--full">
                    <span className="rc-field__label">Ghi chú</span>
                    <span>{req.ghi_chu || "—"}</span>
                  </div>
                </div>
              </section>

              <section className="rc-sec">
                <h3 className="rc-sec__title">Dòng vật tư</h3>
                <div className="kho-lines__wrap">
                  <table className="kho-lines">
                    <thead>
                      <tr>
                        <th style={{ minWidth: 150 }}>Vật tư</th>
                        <th style={{ width: 56 }}>ĐVT</th>
                        <th className="kho-num">Đề nghị</th>
                        <th className="kho-num">Duyệt</th>
                        <th className="kho-num">Đã ứng</th>
                        <th className="kho-num">Còn lại</th>
                        {/* Không có `can_view_stock` → cột BIẾN MẤT, không phải "—". */}
                        {canViewStock && <th className="kho-num">Tồn khả dụng</th>}
                        <th style={{ width: 92 }}>Đèn</th>
                      </tr>
                    </thead>
                    <tbody>
                      {req.lines.map((l) => (
                        <tr key={l.id}>
                          <td>
                            <div
                              className="kho-lines__name kho-name-clamp"
                              title={l.hang_ten ?? undefined}
                            >
                              {l.hang_ten ?? "—"}
                            </div>
                            <div className="kho-lines__code">{l.hang_ma ?? ""}</div>
                          </td>
                          <td className="kho-lines__code">{l.dvt}</td>
                          <td className="kho-num">{fmtQty(l.sl_de_nghi)}</td>
                          <td className="kho-num">{fmtQty(l.sl_duyet)}</td>
                          <td className="kho-num">{fmtQty(l.sl_da_ung)}</td>
                          <td className="kho-num">{fmtQty(l.sl_con_lai)}</td>
                          {canViewStock && (
                            <td className="kho-num">{fmtQty(l.ton_kha_dung ?? 0)}</td>
                          )}
                          <td>
                            <StockLevelChip level={l.muc_ton} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </div>

        <footer className="rc-drawer__foot">
          {/* Kho đi thẳng "Đã duyệt → Lập phiếu"; phiếu tự chuyển đề nghị sang "đang chuẩn bị"
              (voucher.create → mark_in_progress). Đã bỏ bước Tiếp nhận / Bắt đầu chuẩn bị. */}
          {canFulfill && req && (
            <Button variant="accent" onClick={() => onCreateVoucher(req)}>
              {req.open_voucher_id != null ? "Xem phiếu" : "Lập phiếu"}
            </Button>
          )}
          <button type="button" className="btn btn--secondary" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </aside>
    </div>
  );
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className="rc-field">
      <span className="rc-field__label">{label}</span>
      <span>{value}</span>
    </div>
  );
}

// ── DRAWER: LẬP PHIẾU (khối .kho-alloc theo từng dòng đề nghị) ───────────────

interface LotPick {
  lot_id: number;
  ma_lo: string;
  ngay_nhap: string;
  hsd: string | null;
  vi_tri: string | null;
  /** Tồn còn lại CỦA LÔ — trần của ô "Lấy". */
  sl_con_lai: number;
  so_luong: number;
  don_gia_nhap: number | null;
}

interface AllocBlock {
  line: StockRequestLine;
  // Mặt hàng KẾ THỪA từ dòng đề nghị — kho không đổi được, và không còn khối "hàng mới"
  // (siết 2026-08-08: mọi thứ nhập kho phải có sẵn trong danh mục gốc).
  matLabel: string;
  matCode: string | null;
  /** Hệ số về đơn vị gốc — để đổi số kho gõ (theo `line.dvt`) sang số tra lô/gợi ý phân bổ. */
  heSoVeGoc: number;
  cap: number;
  lots: LotPick[];
  thieu: number;
  donGia: string;
  /** Lý do cấp/nhập THIẾU (khi SL < còn phải cấp) — bắt buộc; hiện ở "Kho phản hồi" đề nghị. */
  lyDo: string;
  /** Ghi chú riêng cho mặt hàng (dòng) trên phiếu. */
  ghiChu: string;
  /** Phiếu NHẬP: đơn vị đang gõ ở ô SL nhập — "ton" (đơn vị tồn) hoặc "phu" (đơn vị quy đổi). */
  unit: "ton" | "phu";
  touched: boolean;
  warn: string | null;
  /** Lô vừa bị chặn trần — để tô viền rust ĐÚNG ô đang sai, không tô cả khối. */
  warnLotId: number | null;
}

function toLotPick(a: StockAllocationLine, catalog: StockLot[]): LotPick {
  const full = catalog.find((x) => x.id === a.lot_id);
  return {
    lot_id: a.lot_id,
    ma_lo: a.ma_lo,
    ngay_nhap: a.ngay_nhap,
    hsd: a.hsd,
    vi_tri: full?.vi_tri ?? null,
    sl_con_lai: a.sl_con_lai,
    so_luong: a.so_luong,
    don_gia_nhap: a.don_gia_nhap,
  };
}

function VoucherCreateDrawer({
  token,
  request,
  khoList,
  initialKhoId,
  canPost,
  onClose,
  onSaved,
}: {
  token: string;
  request: StockRequest;
  khoList: KhoOption[];
  initialKhoId: number;
  canPost: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isNhap = request.loai === "NHAP";
  // NGƯỜI LẬP PHIẾU LUÔN NHẬP + THẤY ĐƠN GIÁ (bỏ gate "xem giá vốn" ở bước lập) — theo yêu cầu:
  // ai tạo phiếu đều set giá; giá do người lập điền, không chờ Kế toán bổ sung nữa.
  const canViewCost = true;
  // Kho do BƯỚC LẬP PHIẾU quyết định (đề nghị không còn chọn kho). Mặc định = kho đang xem ở
  // toolbar; thủ kho đổi được ngay tại đây. Đổi kho = nạp lại toàn bộ lô (dep của effect dưới).
  const [khoId, setKhoId] = useState<number>(request.kho_id ?? initialKhoId);
  const [ngay, setNgay] = useState(todayISO());
  const [nguoiGiaoNhan, setNguoiGiaoNhan] = useState("");
  const [ghiChu, setGhiChu] = useState("");
  const [blocks, setBlocks] = useState<AllocBlock[]>([]);
  const [catalog, setCatalog] = useState<Record<string, StockLot[]>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [askDiscard, setAskDiscard] = useState(false);
  const [askPost, setAskPost] = useState(false);

  // Gợi ý lô chạy NGAY khi mở drawer, không chờ bấm nút: thủ kho mở phiếu ra là để lấy hàng,
  // bắt bấm thêm một nút "gợi ý" chỉ để có đúng cái FEFO mặc định là thao tác thừa.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const base: AllocBlock[] = request.lines.map((l) => ({
      line: l,
      matLabel: l.hang_ten ?? "—",
      matCode: l.hang_ma,
      // Server đã quy sẵn cho SL đề nghị — suy ngược ra hệ số, khỏi gọi thêm API.
      heSoVeGoc: l.sl_quy_doi && l.sl_de_nghi ? l.sl_quy_doi / l.sl_de_nghi : 1,
      cap: l.sl_con_lai,
      lots: [],
      thieu: 0,
      // Đơn giá NHẬP LẤY TỪ ĐỀ NGHỊ (người đề nghị khai) — kho chỉ đọc, không sửa.
      donGia: l.don_gia != null ? String(l.don_gia) : "",
      lyDo: "",
      ghiChu: "",
      unit: "ton",
      touched: false,
      warn: null,
      warnLotId: null,
    }));
    if (isNhap) {
      setBlocks(base);
      setLoading(false);
      return;
    }
    // XUẤT: tra lô theo ĐƠN VỊ GỐC — lô lưu theo đơn vị đó, gửi số theo đơn vị đề nghị là lệch
    // đúng bằng hệ số quy đổi (xin 10 ram mà đi tìm 10 kg).
    const targets = request.lines.filter((l) => l.sl_con_lai > 0);
    Promise.all(
      targets.map(async (l) => {
        const hs = l.sl_quy_doi && l.sl_de_nghi ? l.sl_quy_doi / l.sl_de_nghi : 1;
        const mid = `${l.hang_loai}:${l.hang_id}`;
        const [lots, alloc] = await Promise.all([
          api.kho.phieu
            .danhSachLo(token, {
              hang_loai: l.hang_loai, hang_id: l.hang_id, kho_id: khoId, con_hang: true,
            })
            .catch(() => [] as StockLot[]),
          api.kho.phieu
            .goiYLo(token, {
              hang_loai: l.hang_loai, hang_id: l.hang_id, kho_id: khoId,
              so_luong: l.sl_con_lai * hs,
            })
            .catch(() => null),
        ]);
        return { l, mid, lots, alloc };
      }),
    )
      .then((results) => {
        if (cancelled) return;
        const cat: Record<string, StockLot[]> = {};
        for (const r of results) {
          cat[r.mid] = r.lots;
          const b = base.find((x) => x.line.id === r.l.id);
          if (b && r.alloc) {
            b.lots = r.alloc.lines.map((a) => toLotPick(a, r.lots));
            b.thieu = r.alloc.thieu;
          }
        }
        setCatalog(cat);
        setBlocks(base);
      })
      .catch(() => {
        if (!cancelled) setBlocks(base);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // Đổi kho = đổi toàn bộ lô → nạp lại; đó là lý do kho bị khoá sau khi đã chọn lô đầu tiên.
  }, [token, request, khoId, isNhap]);

  function patch(lineId: number, fn: (b: AllocBlock) => AllocBlock) {
    setDirty(true);
    setBlocks((prev) => prev.map((b) => (b.line.id === lineId ? fn(b) : b)));
  }

  function setLotQty(lineId: number, lotId: number, raw: number) {
    patch(lineId, (b) => {
      const others = b.lots
        .filter((x) => x.lot_id !== lotId)
        .reduce((s, x) => s + x.so_luong, 0);
      const lot = b.lots.find((x) => x.lot_id === lotId);
      if (!lot) return b;
      const value = Number.isFinite(raw) ? Math.max(0, raw) : 0;
      let warn: string | null = null;
      let next = value;
      if (next > lot.sl_con_lai) {
        next = lot.sl_con_lai;
        warn = `Lô này chỉ còn ${fmtQty(lot.sl_con_lai)}.`;
      }
      if (others + next > b.line.sl_con_lai) {
        next = Math.max(0, b.line.sl_con_lai - others);
        warn = `Chỉ được cấp ${fmtQty(b.line.sl_con_lai)} theo duyệt — muốn cấp thêm phải tạo đề nghị mới.`;
      }
      return {
        ...b,
        touched: true,
        warn,
        warnLotId: warn ? lotId : null,
        lots: b.lots.map((x) => (x.lot_id === lotId ? { ...x, so_luong: next } : x)),
      };
    });
  }

  function addLot(lineId: number, lotId: number) {
    const b = blocks.find((x) => x.line.id === lineId);
    if (!b) return;
    const lot = (catalog[`${b.line.hang_loai}:${b.line.hang_id}`] ?? []).find((x) => x.id === lotId);
    if (!lot) return;
    patch(lineId, (cur) => ({
      ...cur,
      touched: true,
      lots: [
        ...cur.lots,
        {
          lot_id: lot.id,
          ma_lo: lot.ma_lo,
          ngay_nhap: lot.ngay_nhap,
          hsd: lot.hsd,
          vi_tri: lot.vi_tri,
          sl_con_lai: lot.sl_con_lai,
          so_luong: 0,
          don_gia_nhap: lot.don_gia_nhap,
        },
      ],
    }));
  }

  // GỠ 2026-08-08: `resolvePick` + `resetToNew` — kho gắn/tạo mã cho hàng gõ tay. Mặt hàng nay
  // kế thừa từ dòng đề nghị và đã có sẵn trong danh mục gốc, không còn gì để gắn.

  const payload = useMemo<StockVoucherLineInput[]>(() => {
    const out: StockVoucherLineInput[] = [];
    for (const b of blocks) {
      if (b.line.sl_con_lai <= 0) continue;
      const ghi = b.ghiChu.trim() || null;
      const ly = b.lyDo.trim() || null; // lý do cấp thiếu (backend bắt buộc khi SL < còn phải cấp)
      if (isNhap) {
        if (b.cap <= 0) continue;
        // SL + đơn giá gửi theo ĐƠN VỊ CỦA DÒNG ĐỀ NGHỊ; server tự quy về đơn vị gốc và chốt hệ
        // số vào `sl_goc`. FE KHÔNG tự nhân hệ số nữa — hai nơi cùng quy đổi là hai nơi lệch nhau.
        out.push({
          request_line_id: b.line.id,
          so_luong: b.cap,
          don_gia: canViewCost ? Math.round(Number(b.donGia) || 0) : undefined,
          ly_do: ly,
          ghi_chu: ghi,
        });
      } else {
        // XUẤT: tách theo lô. `lot.so_luong` ở ĐƠN VỊ GỐC (lô lưu theo đơn vị đó) → đổi ngược về
        // đơn vị dòng đề nghị trước khi gửi, vì server so `so_luong` với `sl_duyet`.
        let first = true;
        for (const lot of b.lots) {
          if (lot.so_luong > 0) {
            out.push({
              request_line_id: b.line.id,
              so_luong: b.heSoVeGoc > 0 ? lot.so_luong / b.heSoVeGoc : lot.so_luong,
              lot_id: lot.lot_id,
              ly_do: first ? ly : null,
              ghi_chu: first ? ghi : null,
            });
            first = false;
          }
        }
      }
    }
    return out;
  }, [blocks, isNhap, canViewCost]);

  const giaVon = useMemo(() => {
    if (!canViewCost) return 0;
    let sum = 0;
    for (const b of blocks) {
      if (b.line.sl_con_lai <= 0) continue;
      if (isNhap) sum += (Number(b.donGia) || 0) * b.cap;
      else for (const lot of b.lots) sum += (lot.don_gia_nhap ?? 0) * lot.so_luong;
    }
    return Math.round(sum);
  }, [blocks, isNhap, canViewCost]);

  async function submit(post: boolean) {
    if (!payload.length) {
      setError("Chưa có dòng nào để cấp. Nhập số lượng hoặc chọn lô trước khi lưu.");
      return;
    }
    // Cấp/nhập ÍT HƠN còn phải cấp → bắt buộc LÝ DO (kho phản hồi). Chặn ngay ở FE cho rõ.
    const shortNoReason = blocks.find((b) => {
      if (b.line.sl_con_lai <= 0) return false;
      // Cả hai vế quy về ĐƠN VỊ DÒNG ĐỀ NGHỊ để so với `sl_con_lai` — lô đếm theo đơn vị gốc.
      const capped = isNhap
        ? b.cap
        : b.lots.reduce((s, x) => s + x.so_luong, 0) / (b.heSoVeGoc || 1);
      return capped > 0 && capped < b.line.sl_con_lai - 1e-9 && !b.lyDo.trim();
    });
    if (shortNoReason) {
      setError(
        `"${shortNoReason.matLabel}" cấp ít hơn số còn phải cấp — nhập LÝ DO (vd NCC giao thiếu).`,
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const v = await api.kho.phieu.create(token, {
        request_id: request.id,
        kho_id: khoId,
        // Số phiếu LUÔN tự sinh (PNK/PXK####) — không cho tự nhập.
        ngay,
        nguoi_giao_nhan: nguoiGiaoNhan || null,
        ghi_chu: ghiChu || null,
        lines: payload,
      });
      if (post) await api.kho.phieu.ghiSo(token, v.id);
      setDirty(false);
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không lưu được phiếu.");
    } finally {
      setBusy(false);
    }
  }

  function requestClose() {
    if (dirty) setAskDiscard(true);
    else onClose();
  }

  return (
    <>
      <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={requestClose}>
        <aside className="rc-drawer rc-drawer--wide" onClick={(e) => e.stopPropagation()}>
          <header className="rc-drawer__head">
            <div>
              <div className="rc-drawer__kicker">
                {isNhap ? "PHIẾU NHẬP KHO" : "PHIẾU XUẤT KHO"}
              </div>
              <h2 className="rc-drawer__title">Ứng theo {request.ma}</h2>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
              <VoucherStatusBadge status="draft" />
              <button
                type="button"
                className="rc-drawer__x"
                onClick={requestClose}
                aria-label="Đóng"
              >
                ✕
              </button>
            </div>
          </header>

          <div className="rc-drawer__body">
            {error && (
              <div className="banner banner--error" role="alert">
                <span>{error}</span>
              </div>
            )}

            <section className="rc-sec">
              <h3 className="rc-sec__title">Thông tin phiếu</h3>
              <div className="rc-grid">
                {/* Chuỗi trách nhiệm kế thừa từ đề nghị — ghi thẳng vào phiếu (chỉ đọc). */}
                <Readout label="Theo đề nghị" value={request.ma} />
                <Readout label="Người đề nghị" value={request.nguoi_tao_ten || "—"} />
                <Readout label="Người duyệt" value={request.nguoi_duyet_ten || "—"} />
                <div className="rc-field">
                  <span className="rc-field__label">
                    Kho {isNhap ? "(nhập về)" : "(xuất từ)"} <em>*</em>
                  </span>
                  {/* Bước lập phiếu QUYẾT ĐỊNH kho (đề nghị không chọn kho). Đổi kho → nạp lại lô. */}
                  <Select
                    portal
                    options={khoList.map((w) => ({ value: w.id, label: w.ten, hint: w.ma }))}
                    value={khoId}
                    onChange={(v) => {
                      if (v == null) return;
                      setDirty(true);
                      setKhoId(Number(v));
                    }}
                    ariaLabel="Kho của phiếu"
                    placeholder="Chọn kho"
                  />
                </div>
                <div className="rc-field">
                  <label className="rc-field__label" htmlFor="v-ngay">
                    Ngày
                  </label>
                  <input
                    id="v-ngay"
                    type="date"
                    className="rc-input"
                    value={ngay}
                    onChange={(e) => {
                      setDirty(true);
                      setNgay(e.target.value);
                    }}
                  />
                </div>
                <div className="rc-field">
                  <label className="rc-field__label" htmlFor="v-nguoi">
                    {isNhap ? "Họ tên người giao hàng" : "Họ tên người nhận hàng"}
                  </label>
                  <input
                    id="v-nguoi"
                    className="rc-input"
                    value={nguoiGiaoNhan}
                    onChange={(e) => {
                      setDirty(true);
                      setNguoiGiaoNhan(e.target.value);
                    }}
                  />
                </div>
                <div className="rc-field">
                  <label className="rc-field__label" htmlFor="v-ghichu">
                    Ghi chú
                  </label>
                  <input
                    id="v-ghichu"
                    className="rc-input"
                    value={ghiChu}
                    onChange={(e) => {
                      setDirty(true);
                      setGhiChu(e.target.value);
                    }}
                  />
                </div>
              </div>
            </section>

            <section className="rc-sec">
              <h3 className="rc-sec__title">Dòng cấp</h3>
              {loading ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
                  {Array.from({ length: 3 }).map((_, i) => (
                    <span key={i} className="rc-skel" style={{ width: "100%", height: 72 }} />
                  ))}
                </div>
              ) : (
                blocks.map((b) => (
                  <AllocCard
                    key={b.line.id}
                    token={token}
                    khoId={khoId}
                    block={b}
                    isNhap={isNhap}
                    canViewCost={canViewCost}
                    catalog={catalog[`${b.line.hang_loai}:${b.line.hang_id}`] ?? []}
                    onCap={(v) => patch(b.line.id, (cur) => ({ ...cur, touched: true, cap: v }))}
                    onLyDo={(v) => patch(b.line.id, (cur) => ({ ...cur, lyDo: v }))}
                    onGhiChu={(v) => patch(b.line.id, (cur) => ({ ...cur, ghiChu: v }))}
                    onLotQty={(lotId, v) => setLotQty(b.line.id, lotId, v)}
                    onAddLot={(lotId) => addLot(b.line.id, lotId)}
                    onRemoveLot={(lotId) =>
                      patch(b.line.id, (cur) => ({
                        ...cur,
                        touched: true,
                        warn: null,
                        warnLotId: null,
                        lots: cur.lots.filter((x) => x.lot_id !== lotId),
                      }))
                    }
                  />
                ))
              )}
            </section>

            {/* Section giá vốn KHÔNG TỒN TẠI khi thiếu quyền — không phải ẩn số bên trong. */}
            {canViewCost && (
              <section className="rc-sec">
                <h3 className="rc-sec__title">Giá vốn phiếu</h3>
                <div className="dpanel">
                  <div className="dpanel__label">
                    <span>Tổng giá vốn</span>
                    <span className="dpanel__label-extra">{payload.length} dòng</span>
                  </div>
                  <div className="dpanel__amount">{money(giaVon)}</div>
                  <div className="dpanel__sub">
                    {isNhap
                      ? "Tính theo đơn giá nhập khai trên từng dòng."
                      : "Tính đích danh theo giá của từng lô được lấy."}
                  </div>
                </div>
              </section>
            )}
          </div>

          <footer className="rc-drawer__foot">
            <button type="button" className="btn btn--ghost" onClick={requestClose}>
              Đóng
            </button>
            {/* TẠO = GỬI LUÔN: phiếu vào trạng thái "Chờ ghi sổ", người lập KHÔNG sửa/hủy được nữa.
                Ai có quyền Ghi sổ (Kế toán kho / QL kho) mở phiếu để Ghi sổ hoặc Hủy. */}
            <Button variant={canPost ? "secondary" : "accent"} loading={busy} onClick={() => submit(false)}>
              Tạo phiếu
            </Button>
            {/* Vừa lập vừa có quyền ghi sổ (QL kho) → làm 1 lần cho nhanh. */}
            {canPost && (
              <Button variant="accent" disabled={busy} onClick={() => setAskPost(true)}>
                Tạo &amp; Ghi sổ
              </Button>
            )}
          </footer>
        </aside>
      </div>

      <DiscardChangesDialog
        open={askDiscard}
        onDiscard={() => {
          setAskDiscard(false);
          onClose();
        }}
        onKeepEditing={() => setAskDiscard(false)}
      />

      <ConfirmDialog
        open={askPost}
        title={isNhap ? "Ghi sổ phiếu nhập kho?" : "Ghi sổ phiếu xuất kho?"}
        message="Tồn kho sẽ trừ ngay và phiếu không sửa được nữa. Muốn sửa phải lập phiếu điều chỉnh."
        confirmLabel="Ghi sổ"
        busy={busy}
        onCancel={() => setAskPost(false)}
        onConfirm={() => {
          setAskPost(false);
          void submit(true);
        }}
      />
    </>
  );
}

function AllocCard({
  token,
  khoId,
  block,
  isNhap,
  canViewCost,
  catalog,
  onCap,
  onLyDo,
  onGhiChu,
  onLotQty,
  onAddLot,
  onRemoveLot,
}: {
  token: string;
  khoId: number;
  block: AllocBlock;
  isNhap: boolean;
  canViewCost: boolean;
  catalog: StockLot[];
  onCap: (v: number) => void;
  onLyDo: (v: string) => void;
  onGhiChu: (v: string) => void;
  onLotQty: (lotId: number, v: number) => void;
  onAddLot: (lotId: number) => void;
  onRemoveLot: (lotId: number) => void;
}) {
  const l = block.line;
  // Phiếu NHẬP: hiện tồn hiện tại + giá nhập gần nhất trong kho này để biết đang thêm vào đâu.
  const [tonInfo, setTonInfo] = useState<{ ton: number; gia: number | null } | null>(null);
  useEffect(() => {
    if (!isNhap) {
      setTonInfo(null);
      return;
    }
    let cancelled = false;
    api.kho.phieu
      .danhSachLo(token, {
        hang_loai: l.hang_loai, hang_id: l.hang_id, kho_id: khoId, con_hang: true,
      })
      .then((lots) => {
        if (cancelled) return;
        const ton = lots.reduce((s, x) => s + x.sl_con_lai, 0);
        const gia = lots.length ? lots[lots.length - 1].don_gia_nhap ?? null : null;
        setTonInfo({ ton, gia });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isNhap, l.hang_loai, l.hang_id, khoId, token]);

  const chosen = block.lots.reduce((s, x) => s + x.so_luong, 0);
  const target = block.cap;
  const matched = Math.abs(chosen - target) < 1e-9;
  // Cấp/nhập ÍT HƠN còn phải cấp → bắt buộc LÝ DO (kho phản hồi). Quy cả hai vế về ĐƠN VỊ DÒNG
  // ĐỀ NGHỊ (lô đếm theo đơn vị gốc) rồi mới so với `sl_con_lai`.
  const cappedTon = isNhap ? block.cap : chosen / (block.heSoVeGoc || 1);
  const isShort = l.sl_con_lai > 0 && cappedTon > 0 && cappedTon < l.sl_con_lai - 1e-9;
  const settled = l.sl_con_lai <= 0;
  // Lô đã dùng trong khối thì loại khỏi dropdown — chọn trùng chỉ tạo hai dòng cùng một lô.
  const used = new Set(block.lots.map((x) => x.lot_id));
  const options = catalog
    .filter((lot) => !used.has(lot.id))
    .map((lot) => ({
      value: lot.id,
      label: lot.ma_lo,
      // KHÔNG có giá trong dropdown, kể cả khi có quyền: chọn lô là quyết định theo hạn dùng,
      // kéo giá vào đây là mời người ta lấy lô rẻ trước cho đẹp sổ.
      hint: `còn ${fmtQty(lot.sl_con_lai)} · nhập ${fmtDateISO(lot.ngay_nhap)}`,
    }));

  const cls = [
    "kho-alloc",
    settled ? "kho-alloc--done" : "",
    !settled && block.thieu > 0 ? "kho-alloc--short" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cls}>
      <div className="kho-alloc__head">
        <div className="kho-alloc__title">
          {block.matLabel}
          {block.matCode ? <small>{block.matCode}</small> : null}
        </div>
        {settled ? (
          <span className="badge-sem badge-sem--moss">Đã cấp đủ</span>
        ) : (
          // Dòng không muốn làm đợt này thì để số lượng 0 là tự bỏ qua — không cần ô tick riêng.
          <span className="kho-alloc__remain">
            {isNhap ? "Còn phải nhập" : "Còn phải cấp"}
            <b>{fmtQty(l.sl_con_lai)}</b> {l.dvt}
          </span>
        )}
      </div>

      {/* Mặt hàng luôn có sẵn trong danh mục (siết) nên không còn nhánh "chưa có mã". */}
      {!settled && (
        <>
          {isNhap && tonInfo && (
            <p className="kho-hint">
              Tồn hiện tại: <b>{fmtQty(tonInfo.ton)}</b> {l.dvt}
              {canViewCost && tonInfo.gia != null
                ? ` · giá nhập gần nhất ${money(tonInfo.gia)}`
                : ""}
            </p>
          )}
          <div className="kho-alloc__ctl">
            <label htmlFor={isNhap ? `cap-${l.id}` : undefined}>
              {isNhap ? "SL nhập" : "Cấp lần này"}
            </label>
            {isNhap ? (
              <input
                id={`cap-${l.id}`}
                type="number"
                min={0}
                step="any"
                className="rc-input kho-num"
                value={block.cap || ""}
                onChange={(e) => onCap(Number(e.target.value) || 0)}
              />
            ) : (
              // XUẤT: cấp đúng số CÒN ĐƯỢC ỨNG từ đề nghị — không cho sửa. Muốn cấp một phần
              // thì chọn ít lô hơn; phần còn lại chờ đợt sau hoặc tạo đề nghị mới.
              <b className="kho-alloc__capfixed">{fmtQty(l.sl_con_lai)}</b>
            )}
            {/* MỘT đơn vị duy nhất: đơn vị người đề nghị đã chọn. Nút gạt "tồn / phụ" cũ đã bỏ —
                kho gõ theo đúng đơn vị trên đề nghị, server lo quy về đơn vị gốc. */}
            <span className="kho-alloc__unit">{l.dvt}</span>
            {/* Đơn giá LẤY TỪ ĐỀ NGHỊ (người đề nghị khai) — kho CHỈ ĐỌC, không sửa. */}
            {isNhap && (
              <>
                <label>Đơn giá</label>
                <b className="kho-alloc__capfixed">
                  {block.donGia ? `${Number(block.donGia).toLocaleString("vi-VN")} đ` : "—"}
                </b>
              </>
            )}
            <div className="kho-alloc__spacer" />
          </div>
          {/* Con số THẬT SỰ vào tồn — nhập "10 ram" mà lô ghi 419,25 kg thì phải nói ra ngay đây. */}
          {isNhap && block.heSoVeGoc !== 1 && block.cap > 0 && l.don_vi_goc ? (
            <p className="kho-hint">
              = {fmtQty(block.cap * block.heSoVeGoc)} {l.don_vi_goc} (lô lưu theo {l.don_vi_goc})
              {l.quy_doi_dien_giai ? ` · ${l.quy_doi_dien_giai}` : ""}
            </p>
          ) : null}
          {/* Cấp/nhập ÍT HƠN còn phải cấp → BẮT BUỘC nhập lý do; hiện ở "Kho phản hồi" của đề nghị. */}
          {isShort && (
            <div className="kho-alloc__note kho-alloc__lydo">
              <label htmlFor={`ly-${l.id}`}>
                Lý do cấp thiếu <em>*</em>
              </label>
              <input
                id={`ly-${l.id}`}
                className={`rc-input${!block.lyDo.trim() ? " rc-input--warn" : ""}`}
                value={block.lyDo}
                onChange={(e) => onLyDo(e.target.value)}
                placeholder={`Vì sao chỉ ${isNhap ? "nhập" : "cấp"} ${fmtQty(cappedTon)}/${fmtQty(l.sl_con_lai)}? (vd NCC giao thiếu)`}
              />
            </div>
          )}
          <div className="kho-alloc__note">
            <label htmlFor={`ghi-${l.id}`}>Ghi chú</label>
            <input
              id={`ghi-${l.id}`}
              className="rc-input"
              value={block.ghiChu}
              onChange={(e) => onGhiChu(e.target.value)}
              placeholder="Ghi chú riêng cho mặt hàng này (không bắt buộc)"
            />
          </div>

          {!isNhap && (
            <>
              {block.thieu > 0 && (
                <div className="banner banner--warn">
                  <span>
                    Kho chỉ còn {fmtQty(l.sl_con_lai - block.thieu)} {l.dvt}. Cấp{" "}
                    {fmtQty(l.sl_con_lai - block.thieu)} lần này, phần còn lại chờ nhập hoặc tạo đề
                    nghị mới.
                  </span>
                </div>
              )}
              <div className="kho-alloc__lots">
                <table>
                  <thead>
                    <tr>
                      <th>Mã lô</th>
                      <th>Nhập</th>
                      <th className="kho-num">Còn</th>
                      {canViewCost && <th className="kho-num">Đơn giá</th>}
                      <th className="kho-num">Lấy</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {block.lots.length === 0 ? (
                      <tr>
                        <td colSpan={canViewCost ? 6 : 5} className="kho-lines__empty">
                          Chưa chọn lô nào.
                        </td>
                      </tr>
                    ) : (
                      block.lots.map((lot) => (
                        <tr key={lot.lot_id}>
                          <td className="kho-lines__code">{lot.ma_lo}</td>
                          <td>{fmtDateISO(lot.ngay_nhap)}</td>
                          <td className="kho-num">{fmtQty(lot.sl_con_lai)}</td>
                          {canViewCost && (
                            <td className="kho-num">
                              {lot.don_gia_nhap != null ? money(lot.don_gia_nhap) : ""}
                            </td>
                          )}
                          <td className="kho-num">
                            <input
                              type="number"
                              min={0}
                              step="any"
                              className={`rc-input kho-num${block.warnLotId === lot.lot_id ? " rc-input--invalid" : ""}`}
                              value={lot.so_luong || ""}
                              onChange={(e) => onLotQty(lot.lot_id, Number(e.target.value))}
                              aria-label={`Lấy từ lô ${lot.ma_lo}`}
                            />
                          </td>
                          <td>
                            <button
                              type="button"
                              className="rc-bands__del"
                              aria-label={`Bỏ lô ${lot.ma_lo}`}
                              onClick={() => onRemoveLot(lot.lot_id)}
                            >
                              ✕
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
              {options.length > 0 && (
                <div style={{ maxWidth: 320 }}>
                  <Select
                    portal
                    searchable
                    options={options}
                    value={null}
                    onChange={(v) => v != null && onAddLot(Number(v))}
                    placeholder="+ Thêm lô"
                    searchPlaceholder="Tìm mã lô…"
                    ariaLabel="Thêm lô"
                  />
                </div>
              )}
              {block.warn && <p className="kho-hint kho-hint--rust">{block.warn}</p>}
              <div
                className={`kho-alloc__sum${matched ? " kho-alloc__sum--ok" : " kho-alloc__sum--off"}`}
              >
                {matched
                  ? `✓ Đã chọn ${fmtQty(chosen)} / cần ${fmtQty(target)}`
                  : `Đã chọn ${fmtQty(chosen)} / cần ${fmtQty(target)} · còn ${fmtQty(Math.max(0, target - chosen))} chưa chọn lô`}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

// ── DRAWER: xem phiếu (chỉ đọc) ──────────────────────────────────────────────

export function VoucherDrawer({
  token,
  voucherId,
  canCreate,
  canPost,
  canViewCost,
  onClose,
  onChanged,
}: {
  token: string;
  voucherId: number;
  canCreate: boolean;
  canPost: boolean;
  canViewCost: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [v, setV] = useState<StockVoucher | null>(null);
  // Bản in cần `sl_duyet` + ngày đề nghị (mẫu 01-VT/02-VT có cột "Theo chứng từ") — hai thứ
  // này chỉ có trên đề nghị, nên phiếu phải kéo kèm.
  const [req, setReq] = useState<StockRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [popupBlocked, setPopupBlocked] = useState(false);
  const [askCancel, setAskCancel] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [askPost, setAskPost] = useState(false);
  // Đính kèm hóa đơn/chứng từ gốc (ảnh hoặc PDF).
  const [attachments, setAttachments] = useState<StockVoucherAttachment[]>([]);
  const [attBusy, setAttBusy] = useState(false);
  const [attError, setAttError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.kho.phieu
      .get(token, voucherId)
      .then(async (voucher) => {
        if (cancelled) return;
        setV(voucher);
        const r = await api.kho.deNghi.get(token, voucher.request_id).catch(() => null);
        if (!cancelled) setReq(r);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được phiếu."))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, voucherId]);

  const loadAtt = useCallback(() => {
    api.kho.phieu
      .attachments(token, voucherId)
      .then((r) => setAttachments(r.items))
      .catch(() => {});
  }, [token, voucherId]);
  useEffect(loadAtt, [loadAtt]);

  async function uploadAtt(file: File) {
    setAttBusy(true);
    setAttError(null);
    try {
      await api.kho.phieu.uploadAttachment(token, voucherId, file);
      loadAtt();
    } catch (e) {
      setAttError(e instanceof ApiError ? e.message : "Không tải được file lên.");
    } finally {
      setAttBusy(false);
    }
  }
  async function removeAtt(attId: number) {
    setAttBusy(true);
    setAttError(null);
    try {
      await api.kho.phieu.deleteAttachment(token, voucherId, attId);
      loadAtt();
    } catch (e) {
      setAttError(e instanceof ApiError ? e.message : "Không xóa được file.");
    } finally {
      setAttBusy(false);
    }
  }

  function doPrint() {
    if (!v) return;
    const data: StockVoucherPrintData = {
      kind: v.loai === "NHAP" ? "nhap" : "xuat",
      docNo: v.ma,
      docDate: v.ngay,
      debitAccount: null,
      creditAccount: null,
      boPhan: req?.bo_phan_ten ?? null,
      nguoiGiaoNhan: v.nguoi_giao_nhan,
      chungTuGoc: v.request_ma,
      chungTuGocNgay: req ? fmtDate(req.created_at) : null,
      nguoiDeNghi: req?.nguoi_tao_ten ?? null,
      nguoiDuyet: req?.nguoi_duyet_ten ?? null,
      nguoiLapPhieu: v.nguoi_lap_ten ?? null,
      khoTen: v.kho_ten,
      diaDiem: null,
      lyDo: v.ghi_chu,
      tongTien: v.gia_von,
      cancelled: v.trang_thai === "cancelled",
      lines: v.lines.map((l) => ({
        materialCode: l.hang_ma,
        materialName: l.hang_ten,
        maLo: l.ma_lo,
        dvt: l.dvt,
        soLuongChungTu: req?.lines.find((x) => x.id === l.request_line_id)?.sl_duyet ?? null,
        soLuong: l.so_luong,
        donGia: l.don_gia,
        thanhTien: l.thanh_tien,
      })),
    };
    setPopupBlocked(!printStockVoucher(data));
  }

  async function act(fn: () => Promise<StockVoucher>, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      setV(await fn());
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
        <aside className="rc-drawer rc-drawer--mid" onClick={(e) => e.stopPropagation()}>
          <header className="rc-drawer__head">
            <div>
              <div className="rc-drawer__kicker">
                {v?.loai === "NHAP" ? "PHIẾU NHẬP KHO" : "PHIẾU XUẤT KHO"}
              </div>
              <h2 className="rc-drawer__title">{v?.ma ?? "Đang tải…"}</h2>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
              {v && <VoucherStatusBadge status={v.trang_thai} />}
              <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
                ✕
              </button>
            </div>
          </header>

          {v && (
            <div className="kho-meta">
              {fmtDateISO(v.ngay)} · {v.kho_ten ?? "—"}
              {v.ghi_so_luc ? ` → Ghi sổ: ${fmtDate(v.ghi_so_luc)}` : ""}
            </div>
          )}

          <div className="rc-drawer__body">
            {popupBlocked && (
              <div className="banner banner--warn" role="alert">
                <span>
                  Trình duyệt đã chặn cửa sổ in. Cho phép pop-up cho trang này rồi bấm In lại.
                </span>
              </div>
            )}
            {error && (
              <div className="banner banner--error" role="alert">
                <span>{error}</span>
              </div>
            )}
            {loading || !v ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
                {Array.from({ length: 4 }).map((_, i) => (
                  <span key={i} className="rc-skel" style={{ width: `${90 - i * 12}%` }} />
                ))}
              </div>
            ) : (
              <>
                <section className="rc-sec">
                  <h3 className="rc-sec__title">Thông tin phiếu</h3>
                  <div className="rc-grid">
                    {/* Chuỗi trách nhiệm — ai đề nghị → ai duyệt → ai lập phiếu (kho). */}
                    <Readout label="Người đề nghị" value={v.nguoi_de_nghi_ten || "—"} />
                    <Readout label="Người duyệt" value={v.nguoi_duyet_ten || "—"} />
                    <Readout label="Người lập phiếu" value={v.nguoi_lap_ten || "—"} />
                    <Readout label="Theo đề nghị" value={v.request_ma || "—"} />
                    <Readout label="Kho" value={v.kho_ten || "—"} />
                    <Readout label="Ngày" value={fmtDateISO(v.ngay)} />
                    <Readout
                      label={v.loai === "NHAP" ? "Người giao hàng" : "Người nhận hàng"}
                      value={v.nguoi_giao_nhan || "—"}
                    />
                    <Readout
                      label="Người ghi sổ"
                      value={
                        v.ghi_so_luc
                          ? `${v.nguoi_ghi_so_ten ?? "—"} · ${fmtDate(v.ghi_so_luc)}`
                          : "Chưa ghi sổ"
                      }
                    />
                    <div className="rc-field rc-field--full">
                      <span className="rc-field__label">Ghi chú</span>
                      <span>{v.ghi_chu || "—"}</span>
                    </div>
                  </div>
                </section>

                <section className="rc-sec">
                  <h3 className="rc-sec__title">Dòng phiếu</h3>
                  <div className="kho-lines__wrap">
                    <table className="kho-lines">
                      <thead>
                        <tr>
                          <th style={{ minWidth: 150 }}>Vật tư</th>
                          <th style={{ width: 118 }}>Mã lô</th>
                          <th style={{ width: 52 }}>ĐVT</th>
                          <th className="kho-num">Số lượng</th>
                          {canViewCost && <th className="kho-num">Đơn giá</th>}
                          {canViewCost && <th className="kho-num">Thành tiền</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {v.lines.map((l) => (
                          <tr key={l.id}>
                            <td>
                              <div className="kho-lines__name">{l.hang_ten ?? "—"}</div>
                              <div className="kho-lines__code">{l.hang_ma ?? ""}</div>
                            </td>
                            <td className="kho-lines__code">{l.ma_lo ?? "—"}</td>
                            <td className="kho-lines__code">{l.dvt ?? "—"}</td>
                            <td className="kho-num">{fmtQty(l.so_luong)}</td>
                            {canViewCost && (
                              <td className="kho-num">
                                {l.don_gia != null ? money(l.don_gia) : ""}
                              </td>
                            )}
                            {canViewCost && (
                              <td className="kho-num">
                                {l.thanh_tien != null ? money(l.thanh_tien) : ""}
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="rc-sec">
                  <h3 className="rc-sec__title">Chứng từ gốc / Hóa đơn</h3>
                  {attError && (
                    <div className="banner banner--error" role="alert">
                      <span>{attError}</span>
                    </div>
                  )}
                  {attachments.length === 0 ? (
                    <p className="kho-hint">Chưa có file đính kèm.</p>
                  ) : (
                    <ul className="kho-att">
                      {attachments.map((a) => (
                        <li key={a.id} className="kho-att__item">
                          <a
                            href={assetUrl(a.file_url) ?? "#"}
                            target="_blank"
                            rel="noreferrer"
                            className="kho-att__name"
                          >
                            📎 {a.file_name}
                          </a>
                          {canCreate && v.trang_thai !== "cancelled" && (
                            <button
                              type="button"
                              className="rc-bands__del"
                              aria-label={`Xóa ${a.file_name}`}
                              disabled={attBusy}
                              onClick={() => removeAtt(a.id)}
                            >
                              ✕
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                  {canCreate && v.trang_thai !== "cancelled" && (
                    <label className={`btn btn--secondary kho-att__upload${attBusy ? " is-disabled" : ""}`}>
                      {attBusy ? "Đang tải…" : "+ Thêm file (ảnh / PDF)"}
                      <input
                        type="file"
                        accept="image/*,application/pdf"
                        hidden
                        disabled={attBusy}
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f) void uploadAtt(f);
                          e.target.value = "";
                        }}
                      />
                    </label>
                  )}
                </section>

                {canViewCost && v.gia_von != null && (
                  <section className="rc-sec">
                    <h3 className="rc-sec__title">Giá vốn phiếu</h3>
                    <div className="dpanel">
                      <div className="dpanel__label">
                        <span>Tổng giá vốn</span>
                        <span className="dpanel__label-extra">{v.lines.length} dòng</span>
                      </div>
                      <div className="dpanel__amount">{money(v.gia_von)}</div>
                    </div>
                  </section>
                )}
              </>
            )}
          </div>

          <footer className="rc-drawer__foot">
            {/* In được ở mọi trạng thái (kể cả "Chờ ghi sổ" và đã hủy) — bản giấy cần cho luân
                chuyển nội bộ + kiểm toán. */}
            <button type="button" className="btn btn--ghost" onClick={doPrint} disabled={!v}>
              In phiếu
            </button>
            {/* HỦY = quyền của người GHI SỔ (Kế toán kho / QL kho), KHÔNG phải người lập. Người lập
                tạo phiếu là gửi luôn, không tự rút lại được (SoD). */}
            {canPost && v?.trang_thai === "draft" && (
              <button
                type="button"
                className="btn btn--danger"
                onClick={() => {
                  setCancelReason("");
                  setAskCancel(true);
                }}
              >
                Hủy phiếu
              </button>
            )}
            {/* Ghi sổ gác quyền RIÊNG `post` (Kế toán kho / QL kho) — thủ kho lập nháp không tự ghi sổ. */}
            {canPost && v?.trang_thai === "draft" && (
              <Button variant="accent" loading={busy} onClick={() => setAskPost(true)}>
                Ghi sổ
              </Button>
            )}
            <button type="button" className="btn btn--secondary" onClick={onClose}>
              Đóng
            </button>
          </footer>
        </aside>
      </div>

      <ConfirmDialog
        open={askPost}
        title={v?.loai === "NHAP" ? "Ghi sổ phiếu nhập kho?" : "Ghi sổ phiếu xuất kho?"}
        message="Tồn kho sẽ trừ ngay và phiếu không sửa được nữa. Muốn sửa phải lập phiếu điều chỉnh."
        confirmLabel="Ghi sổ"
        busy={busy}
        onCancel={() => setAskPost(false)}
        onConfirm={() => {
          setAskPost(false);
          if (v) void act(() => api.kho.phieu.ghiSo(token, v.id), "Không ghi sổ được phiếu.");
        }}
      />

      <ConfirmDialog
        open={askCancel}
        title="Hủy phiếu này?"
        message="Đề nghị sẽ chuyển sang 'Đã hủy' kèm lý do và KHÔNG cấp lại. Phiếu vẫn giữ số & in được, nhưng không ghi sổ được nữa."
        confirmLabel="Hủy phiếu"
        cancelLabel="Giữ lại"
        danger
        busy={busy}
        confirmDisabled={!cancelReason.trim()}
        onCancel={() => setAskCancel(false)}
        onConfirm={() => {
          const ly = cancelReason.trim();
          if (!ly || !v) return;
          setAskCancel(false);
          void act(() => api.kho.phieu.huy(token, v.id, ly), "Không hủy được phiếu.");
        }}
      >
        <label className="rc-field">
          <span className="rc-field__label">
            Lý do hủy <em>*</em>
          </span>
          <textarea
            className="rc-textarea"
            rows={3}
            value={cancelReason}
            onChange={(e) => setCancelReason(e.target.value)}
            placeholder="Vì sao hủy đề nghị này? (bắt buộc)"
            autoFocus
          />
        </label>
      </ConfirmDialog>
    </>
  );
}

// ── DRAWER: ngưỡng tồn ───────────────────────────────────────────────────────

export function ThresholdDrawer({
  token,
  khoList,
  initialKhoId,
  onClose,
}: {
  token: string;
  khoList: KhoOption[];
  initialKhoId: number | null;
  onClose: () => void;
}) {
  const [khoId, setKhoId] = useState<number | null>(initialKhoId);
  // Mặt hàng gốc đang khai ngưỡng. Giữ cả `ten` để ô chọn hiện lại tên sau khi chọn.
  const [hang, setHang] = useState<{ loai: HangLoai; id: number; ten: string } | null>(null);
  const [nguongTon, setNguongTon] = useState("");
  const [nguongToiDa, setNguongToiDa] = useState("");
  const [canhBao, setCanhBao] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  // Ngưỡng đã lưu, key = "kho:vật tư" — để CHỌN VẬT TƯ NÀO thì nạp sẵn ngưỡng của vật tư đó.
  const [thByKey, setThByKey] = useState<Record<string, StockThreshold>>({});

  useEffect(() => {
    api.kho.nguongTon
      .list(token)
      .then((ths) => {
        const m: Record<string, StockThreshold> = {};
        for (const t of ths) m[`${t.kho_id}:${t.hang_loai}:${t.hang_id}`] = t;
        setThByKey(m);
      })
      .catch(() => {});
  }, [token]);

  // Chọn mặt hàng (+ kho) → nạp ngưỡng đã khai của món đó; chưa khai thì để trống (khai mới).
  useEffect(() => {
    if (hang == null || khoId == null) return;
    const t = thByKey[`${khoId}:${hang.loai}:${hang.id}`];
    setNguongTon(t?.nguong_ton != null ? String(t.nguong_ton) : "");
    setNguongToiDa(t?.nguong_toi_da != null ? String(t.nguong_toi_da) : "");
    setCanhBao(t?.canh_bao ?? true);
    setOk(false);
  }, [hang, khoId, thByKey]);

  async function save() {
    if (hang == null || khoId == null) {
      setError("Chọn vật tư và kho trước khi lưu.");
      return;
    }
    const ton = Number(nguongTon);
    if (!Number.isFinite(ton) || ton < 0) {
      setError("Ngưỡng tồn phải là số không âm.");
      return;
    }
    const max = nguongToiDa === "" ? null : Number(nguongToiDa);
    if (max != null && max < ton) {
      setError("Ngưỡng tối đa phải lớn hơn hoặc bằng ngưỡng tồn.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const t = await api.kho.nguongTon.upsert(token, {
        hang_loai: hang.loai,
        hang_id: hang.id,
        kho_id: khoId,
        nguong_ton: ton,
        nguong_can_ton: null,
        nguong_toi_da: max,
        canh_bao: canhBao,
      });
      setThByKey((prev) => ({ ...prev, [`${khoId}:${hang.loai}:${hang.id}`]: t }));
      setOk(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không lưu được ngưỡng tồn.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer rc-drawer--mid" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">CẤU HÌNH KHO</div>
            <h2 className="rc-drawer__title">Ngưỡng tồn</h2>
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            ✕
          </button>
        </header>

        <div className="rc-drawer__body">
          {error && (
            <div className="banner banner--error" role="alert">
              <span>{error}</span>
            </div>
          )}
          {ok && (
            <div className="banner banner--success" role="status">
              <span>Đã lưu ngưỡng cho vật tư này.</span>
            </div>
          )}

          <section className="rc-sec">
            <h3 className="rc-sec__title">Áp cho</h3>
            <div className="rc-grid">
              <div className="rc-field">
                <span className="rc-field__label">Vật tư</span>
                {/* Cùng ô chọn với dòng đề nghị — một cách chọn mặt hàng cho cả module, khỏi hai
                    kiểu tìm khác nhau cho cùng một danh mục. Ngưỡng khai theo ĐƠN VỊ GỐC. */}
                <MaterialCombobox
                  token={token}
                  hangTen={hang?.ten ?? null}
                  onPick={(m) => {
                    setHang({ loai: m.hang_loai, id: m.hang_id, ten: m.ten });
                    setOk(false);
                  }}
                  placeholder="Tìm mã / tên vật tư…"
                />
              </div>
              <div className="rc-field">
                <span className="rc-field__label">Kho</span>
                <Select
                  portal
                  options={khoList.map((w) => ({ value: w.id, label: w.ten, hint: w.ma }))}
                  value={khoId}
                  onChange={(v) => setKhoId(v == null ? null : Number(v))}
                  ariaLabel="Kho"
                />
              </div>
            </div>
          </section>

          <section className="rc-sec">
            <h3 className="rc-sec__title">Ba ngưỡng</h3>
            <div className="rc-grid">
              <div className="rc-field">
                <label className="rc-field__label" htmlFor="ng-ton">
                  Ngưỡng tồn <em>*</em>
                </label>
                <input
                  id="ng-ton"
                  type="number"
                  min={0}
                  step="any"
                  className="rc-input kho-num"
                  value={nguongTon}
                  onChange={(e) => setNguongTon(e.target.value)}
                />
                <p className="rc-field__hint">Dưới mức này là "Cần mua".</p>
              </div>
              <div className="rc-field">
                <label className="rc-field__label" htmlFor="ng-max">
                  Ngưỡng tối đa
                </label>
                <input
                  id="ng-max"
                  type="number"
                  min={0}
                  step="any"
                  className="rc-input kho-num"
                  value={nguongToiDa}
                  onChange={(e) => setNguongToiDa(e.target.value)}
                />
                <p className="rc-field__hint">Vượt mức này báo "Dư" (đọng vốn).</p>
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
          </section>
        </div>

        <footer className="rc-drawer__foot">
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
          <Button variant="accent" loading={busy} onClick={save}>
            Lưu ngưỡng
          </Button>
        </footer>
      </aside>
    </div>
  );
}

// ── Mảnh dùng lại trong màn ──────────────────────────────────────────────────

function SkeletonRows({ cols }: { cols: number }) {
  return (
    <>
      {Array.from({ length: 5 }).map((_, i) => (
        <tr key={`sk-${i}`} className="rc-skel__row">
          {Array.from({ length: cols }).map((__, c) => (
            <td key={c}>
              <span className="rc-skel" style={{ width: "60%" }} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

function EmptyRow({
  cols,
  text,
  onClear,
}: {
  cols: number;
  text: string;
  onClear?: () => void;
}) {
  return (
    <tr>
      <td colSpan={cols} className="rc__empty-state-td">
        <div className="rc__empty-state">
          <EmptyIcon />
          <p className="rc__empty-text">{text}</p>
          {onClear && (
            <Button variant="ghost" onClick={onClear}>
              Xóa bộ lọc
            </Button>
          )}
        </div>
      </td>
    </tr>
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
