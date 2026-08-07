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
  type StockAllocationLine,
  type StockLot,
  type StockMaterialOption,
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

type TabId = "tat-ca" | "can-cap" | "dang-cap" | "done" | "da-huy";

const TAB_STATUSES: Record<TabId, StockRequestStatus[]> = {
  "tat-ca": ["approved", "received", "preparing", "partial", "done", "cancelled"],
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
  // Mới nhất lên đầu: đề nghị/phiếu vừa tạo (hoặc vừa có hoạt động) hiện trên cùng.
  if (a.created_at !== b.created_at) return b.created_at.localeCompare(a.created_at);
  return b.ma.localeCompare(a.ma);
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
  // ĐÃ GỘP quyền: ghi sổ + hủy dùng CHUNG quyền lập phiếu (create) — không còn 'post' riêng.
  const canPost = canCreate;
  const canViewCost = can("kho", "view_cost");

  const [khoList, setKhoList] = useState<KhoOption[]>([]);
  const [khoId, setKhoId] = useState<number | null>(() => readStoredKho(KHO_KEY));
  const [requests, setRequests] = useState<StockRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<TabId>("tat-ca");
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
    { id: "tat-ca", label: "Tất cả" },
    { id: "can-cap", label: "Cần cấp" },
    { id: "dang-cap", label: "Đang cấp" },
    { id: "done", label: "Hoàn tất" },
    { id: "da-huy", label: "Đã hủy" },
  ];

  // Cột đề nghị: 8 khi có nút Lập phiếu, 7 khi không (đã bỏ cột Tồn — đề nghị không gắn kho).
  const reqCols = canCreate ? 7 : 6;

  return (
    <div className="kho-list">
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
                <th style={{ width: "17%" }}>Bộ phận · Người</th>
                <th>Vật tư</th>
                <th style={{ width: "13%" }}>{loai === "NHAP" ? "Ngày cần nhập" : "Ngày cần xuất"}</th>
                <th style={{ width: "13%" }}>Trạng thái</th>
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
                          title={r.lines[0]?.material_name ?? r.lines[0]?.ten_tu_do ?? undefined}
                        >
                          {r.lines[0]?.material_name ?? r.lines[0]?.ten_tu_do ?? "—"}
                        </div>
                        {r.lines.length > 1 && (
                          <div className="rc__muted">+{r.lines.length - 1} mã</div>
                        )}
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
          onClose={() => setOpenRequest(null)}
          onCreateVoucher={openFulfil}
          onChanged={load}
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
    </div>
  );
}

// ── DRAWER: chi tiết đề nghị (góc nhìn KHO) ──────────────────────────────────

export function InboxRequestDrawer({
  token,
  khoId,
  requestId,
  canCreate,
  onClose,
  onCreateVoucher,
  onChanged,
}: {
  token: string;
  khoId: number | null;
  requestId: number;
  canCreate: boolean;
  onClose: () => void;
  onCreateVoucher: (r: StockRequest) => void;
  /** Hủy phiếu nháp xong → cha refresh danh sách (chỉ dùng ở Hộp yêu cầu; chỗ chỉ-đọc bỏ trống). */
  onChanged?: () => void;
}) {
  const [req, setReq] = useState<StockRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Hủy phiếu nháp NGAY TỪ đề nghị (phương án a: hủy chỉ qua luồng đề nghị, bỏ nút Hủy ở phiếu).
  const [askCancel, setAskCancel] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelBusy, setCancelBusy] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

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

  // Đề nghị ĐÃ có phiếu nháp → hủy PHIẾU (kéo đề nghị sang "Đã hủy"). CHƯA có phiếu → hủy thẳng
  // ĐỀ NGHỊ (kho quyết định không lập phiếu). Cùng 1 popup lý do.
  async function doCancel() {
    if (!req) return;
    const ly = cancelReason.trim();
    if (!ly) return;
    setCancelBusy(true);
    setCancelError(null);
    try {
      if (req.open_voucher_id != null) {
        await api.kho.phieu.huy(token, req.open_voucher_id, ly);
      } else {
        await api.kho.deNghi.cancelByKho(token, req.id, ly);
      }
      setAskCancel(false);
      onChanged?.();
      onClose();
    } catch (e) {
      setCancelError(e instanceof ApiError ? e.message : "Không hủy được.");
    } finally {
      setCancelBusy(false);
    }
  }

  return (
    <>
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
                        <th style={{ width: 40 }}>STT</th>
                        <th style={{ minWidth: 150 }}>Vật tư</th>
                        <th style={{ width: 56 }}>ĐVT</th>
                        <th className="kho-num">Đề nghị</th>
                        <th className="kho-num">Duyệt</th>
                        <th className="kho-num">Đã ứng</th>
                        <th className="kho-num">Còn lại</th>
                      </tr>
                    </thead>
                    <tbody>
                      {req.lines.map((l, i) => (
                        <tr key={l.id}>
                          <td className="kho-lines__code">{i + 1}</td>
                          <td>
                            <div
                              className="kho-lines__name kho-name-clamp"
                              title={l.material_name ?? l.ten_tu_do ?? undefined}
                            >
                              {l.material_name ?? l.ten_tu_do ?? "—"}
                            </div>
                            <div className="kho-lines__code">
                              {l.material_code ?? (l.ten_tu_do ? "Hàng mới" : "")}
                            </div>
                          </td>
                          <td className="kho-lines__code">{l.dvt}</td>
                          <td className="kho-num">{fmtQty(l.sl_de_nghi)}</td>
                          <td className="kho-num">{fmtQty(l.sl_duyet)}</td>
                          <td className="kho-num">{fmtQty(l.sl_da_ung)}</td>
                          <td className="kho-num">{fmtQty(l.sl_con_lai)}</td>
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
          {/* Cạnh "Lập phiếu"/"Xem phiếu": có phiếu nháp → "Hủy phiếu"; chưa có phiếu → "Hủy đề nghị"
              (kho quyết định KHÔNG lập). Bấm → popup bắt nhập lý do; xong đề nghị chuyển "Đã hủy". */}
          {canFulfill && req && (
            <button
              type="button"
              className="btn btn--danger"
              onClick={() => {
                setCancelReason("");
                setCancelError(null);
                setAskCancel(true);
              }}
            >
              {req.open_voucher_id != null ? "Hủy phiếu" : "Hủy đề nghị"}
            </button>
          )}
          <button type="button" className="btn btn--secondary" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </aside>
    </div>

      <ConfirmDialog
        open={askCancel}
        title={req?.open_voucher_id != null ? "Hủy phiếu này?" : "Hủy đề nghị này?"}
        message={
          req?.open_voucher_id != null
            ? "Đề nghị sẽ chuyển 'Đã hủy' kèm lý do và KHÔNG cấp lại. Phiếu vẫn giữ số & in được, nhưng không ghi sổ được nữa."
            : "Đề nghị sẽ chuyển 'Đã hủy' kèm lý do và KHÔNG cấp nữa. Dùng khi kho quyết định không lập phiếu cho đề nghị này."
        }
        confirmLabel={req?.open_voucher_id != null ? "Hủy phiếu" : "Hủy đề nghị"}
        cancelLabel="Giữ lại"
        danger
        busy={cancelBusy}
        error={cancelError}
        confirmDisabled={!cancelReason.trim()}
        onCancel={() => setAskCancel(false)}
        onConfirm={() => void doCancel()}
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
  // Mã đã gắn cho dòng. Hàng đã có mã = line.material_id; hàng mới CHỌN mã có sẵn = id đó.
  // null = hàng mới CHƯA có mã → gửi `newProd` (backend tạo khi lưu/ghi sổ, không tạo eager).
  matId: number | null;
  matLabel: string;
  matCode: string | null;
  // Tên/ĐVT hàng mới (khi matId null) — hiển thị + tương thích. Quy đổi khai ở ĐỀ NGHỊ.
  newName: string;
  newUnit: string;
  cap: number;
  lots: LotPick[];
  thieu: number;
  donGia: string;
  /** Lý do cấp/nhập THIẾU (khi SL < còn phải cấp) — bắt buộc; hiện ở "Kho phản hồi" đề nghị. */
  lyDo: string;
  /** Ghi chú riêng cho mặt hàng (dòng) trên phiếu. */
  ghiChu: string;
  /** Phiếu NHẬP: vị trí cất lô (kệ/ô) — ghi sổ chép sang lô. */
  viTri: string;
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
  // Người giao (NHẬP) / nhận (XUẤT) điền sẵn = người đề nghị; thủ kho sửa được nếu khác.
  const [nguoiGiaoNhan, setNguoiGiaoNhan] = useState(request.nguoi_tao_ten ?? "");
  const [ghiChu, setGhiChu] = useState("");
  const [blocks, setBlocks] = useState<AllocBlock[]>([]);
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
      matId: l.material_id,
      matLabel: l.material_name ?? l.ten_tu_do ?? "—",
      matCode: l.material_code,
      // Hàng mới: điền sẵn form tạo (tên = tên đề nghị, ĐVT = ĐVT đề nghị) — backend tạo khi lưu.
      newName: l.material_id == null ? l.ten_tu_do ?? "" : "",
      newUnit: l.material_id == null ? l.dvt ?? "" : "",
      cap: l.sl_con_lai,
      lots: [],
      thieu: 0,
      // Đơn giá NHẬP LẤY TỪ ĐỀ NGHỊ (người đề nghị khai) — kho chỉ đọc, không sửa.
      donGia: l.don_gia != null ? String(l.don_gia) : "",
      lyDo: "",
      ghiChu: "",
      viTri: "",
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
    // XUẤT: chỉ tra lô cho hàng ĐÃ CÓ MÃ. Hàng mới chưa gắn mã thì không có lô để xuất.
    const targets = request.lines.filter((l) => l.sl_con_lai > 0 && l.material_id != null);
    Promise.all(
      targets.map(async (l) => {
        const mid = l.material_id as number;
        const [lots, alloc] = await Promise.all([
          api.kho.phieu
            .danhSachLo(token, { material_id: mid, kho_id: khoId, con_hang: true })
            .catch(() => [] as StockLot[]),
          api.kho.phieu
            .goiYLo(token, { material_id: mid, kho_id: khoId, so_luong: l.sl_con_lai })
            .catch(() => null),
        ]);
        return { l, lots, alloc };
      }),
    )
      .then((results) => {
        if (cancelled) return;
        for (const r of results) {
          const b = base.find((x) => x.line.id === r.l.id);
          if (b && r.alloc) {
            // Giữ danh sách lô đã tra (r.lots) để toLotPick điền vị trí; không còn cache catalog.
            b.lots = r.alloc.lines.map((a) => toLotPick(a, r.lots));
            b.thieu = r.alloc.thieu;
          }
        }
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

  // HÀNG MỚI ở phiếu: kho CHỌN mã có sẵn (nếu trùng tên) → gắn ngay. KHÔNG tạo mã eager nữa;
  // hàng thật sự mới thì chỉ điền form, backend tạo mã khi LƯU/GHI SỔ.
  function resolvePick(lineId: number, m: StockMaterialOption) {
    // Không cho hai dòng cùng trỏ một mã đã có (backend cũng chặn); nhắc ngay ở FE.
    if (blocks.some((b) => b.line.id !== lineId && b.matId === m.id)) {
      setError("Mã này đã gắn cho dòng khác trên phiếu.");
      return;
    }
    setError(null);
    patch(lineId, (cur) => ({
      ...cur,
      matId: m.id,
      matLabel: m.name ?? cur.matLabel,
      matCode: m.code ?? null,
      // Chọn hàng có sẵn → kéo quy đổi của nó vào để nút đổi đơn vị nhập hiện ngay.
      line: {
        ...cur.line,
        don_vi_phu: m.don_vi_phu ?? null,
        he_so_quy_doi: m.he_so_quy_doi ?? null,
      },
    }));
  }
  // Quay lại "tạo mới" (bỏ mã đã chọn) — trả dòng về trạng thái hàng mới.
  function resetToNew(lineId: number) {
    setError(null);
    patch(lineId, (cur) => ({
      ...cur,
      matId: null,
      matCode: null,
      matLabel: cur.newName || cur.line.ten_tu_do || "—",
      line: { ...cur.line, don_vi_phu: null, he_so_quy_doi: null },
    }));
  }

  const payload = useMemo<StockVoucherLineInput[]>(() => {
    const out: StockVoucherLineInput[] = [];
    for (const b of blocks) {
      if (b.line.sl_con_lai <= 0) continue;
      const ghi = b.ghiChu.trim() || null;
      // XUẤT đã bỏ ô lý do → cấp THIẾU (kho không đủ tồn) thì tự điền lý do cho backend (backend
      // bắt buộc ly_do khi SL < còn phải cấp). NHẬP vẫn nhập tay ở ô Lý do.
      const chosenX = b.lots.reduce((s, x) => s + x.so_luong, 0);
      const ly =
        b.lyDo.trim() ||
        (!isNhap && chosenX > 0 && chosenX < b.line.sl_con_lai - 1e-9 ? "Kho không đủ tồn" : null);
      const isNew = b.matId == null; // hàng mới chưa có mã → gửi new_* để backend tạo khi lưu
      if (isNhap) {
        if (b.cap <= 0) continue;
        if (isNew) {
          // Hàng mới: TÊN + ĐVT + QUY ĐỔI đã khai Ở ĐỀ NGHỊ → backend tạo mã từ dòng đề nghị.
          // (Gửi new_name/new_unit để tương thích; backend ưu tiên dữ liệu đề nghị.) SL theo ĐVT tồn.
          if (!b.newName.trim()) continue; // submit đã chặn; đây là lưới an toàn
          out.push({
            request_line_id: b.line.id,
            new_name: b.newName.trim(),
            new_unit: b.newUnit.trim() || b.line.dvt,
            so_luong: b.cap,
            don_gia: canViewCost ? Math.round(Number(b.donGia) || 0) : undefined,
            vi_tri: b.viTri.trim() || undefined,
            ly_do: ly,
            ghi_chu: ghi,
          });
        } else {
          // Nhập theo đơn vị PHỤ → quy về đơn vị TỒN để lưu lô: SL ×hệ số, đơn giá ÷hệ số.
          const hs = b.line.he_so_quy_doi ?? 0;
          const factor = b.unit === "phu" && hs > 0 ? hs : 1;
          out.push({
            request_line_id: b.line.id,
            material_id: b.matId,
            so_luong: b.cap * factor,
            don_gia: canViewCost ? Math.round((Number(b.donGia) || 0) / factor) : undefined,
            vi_tri: b.viTri.trim() || undefined,
            ly_do: ly,
            ghi_chu: ghi,
          });
        }
      } else {
        // XUẤT hàng mới (chưa có mã) không xuất được — bỏ qua. Còn lại tách theo lô.
        if (isNew) continue;
        let first = true;
        for (const lot of b.lots) {
          if (lot.so_luong > 0) {
            out.push({
              request_line_id: b.line.id,
              material_id: b.matId,
              so_luong: lot.so_luong,
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
    // Hàng mới đang cấp (NHẬP, SL>0) mà CHƯA nhập tên → chặn (backend sẽ tạo mã khi lưu, cần tên).
    const missingName = blocks.find(
      (b) =>
        b.matId == null &&
        b.line.sl_con_lai > 0 &&
        isNhap &&
        b.cap > 0 &&
        !b.newName.trim(),
    );
    if (missingName) {
      setError(
        `Hàng mới "${missingName.line.ten_tu_do ?? ""}" chưa nhập tên vật tư — điền tên (hoặc chọn mã có sẵn).`,
      );
      return;
    }
    if (!payload.length) {
      setError("Chưa có dòng nào để cấp. Nhập số lượng hoặc chọn lô trước khi lưu.");
      return;
    }
    // NHẬP thiếu so với đề nghị → bắt buộc LÝ DO (kho phản hồi). Chặn ngay ở FE cho rõ.
    // XUẤT thiếu KHÔNG chặn: form xuất đã bỏ ô lý do, payload tự điền "Kho không đủ tồn".
    const shortNoReason = blocks.find((b) => {
      if (b.line.sl_con_lai <= 0) return false;
      const capped = isNhap
        ? b.cap * (b.unit === "phu" && (b.line.he_so_quy_doi ?? 0) > 0 ? b.line.he_so_quy_doi! : 1)
        : b.lots.reduce((s, x) => s + x.so_luong, 0);
      return capped > 0 && capped < b.line.sl_con_lai - 1e-9 && !b.lyDo.trim() && isNhap;
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
                    min={todayISO()}
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
              ) : isNhap ? (
                // NHẬP: mỗi vật tư = 1 DÒNG bảng (không phải thẻ). Không có lô ở nhập — lô tạo lúc
                // ghi sổ. >6 dòng → cho cuộn trong khung. Bọc wrap để hẹp thì cuộn ngang, không vỡ.
                <div className={`kho-lines__wrap${blocks.length > 6 ? " kho-alloc-list--scroll" : ""}`}>
                  <table className="kho-lines kho-nhap">
                    <thead>
                      <tr>
                        <th className="kho-num kho-nhap__stt">STT</th>
                        <th>Vật tư</th>
                        <th>ĐVT</th>
                        <th>Vị trí</th>
                        <th className="kho-num">Cần phải nhập</th>
                        <th className="kho-num">SL nhập</th>
                        <th className="kho-num">Đơn giá</th>
                        {canViewCost && <th className="kho-num">Thành tiền</th>}
                        <th>Lý do</th>
                      </tr>
                    </thead>
                    <tbody>
                      {blocks.map((b, i) => (
                        <AllocRow
                          key={b.line.id}
                          token={token}
                          idx={i + 1}
                          block={b}
                          canViewCost={canViewCost}
                          onResolvePick={(m) => resolvePick(b.line.id, m)}
                          onResetToNew={() => resetToNew(b.line.id)}
                          onNewName={(v) => patch(b.line.id, (cur) => ({ ...cur, newName: v }))}
                          onNewUnit={(v) => patch(b.line.id, (cur) => ({ ...cur, newUnit: v }))}
                          onCap={(v) => patch(b.line.id, (cur) => ({ ...cur, touched: true, cap: v }))}
                          onLyDo={(v) => patch(b.line.id, (cur) => ({ ...cur, lyDo: v }))}
                          onViTri={(v) => patch(b.line.id, (cur) => ({ ...cur, viTri: v }))}
                          onUnit={(u) => patch(b.line.id, (cur) => ({ ...cur, unit: u }))}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                // XUẤT: mỗi vật tư = 1 DÒNG bảng (giống NHẬP + list Tồn kho). FIFO tự phân bổ lô,
                // KHÔNG sửa tay; bấm dòng → xổ bảng lô CHỈ ĐỌC. >6 dòng → cho cuộn trong khung.
                <div className={`kho-lines__wrap${blocks.length > 6 ? " kho-alloc-list--scroll" : ""}`}>
                  <table className="kho-lines kho-xuat">
                    <thead>
                      <tr>
                        <th className="kho-xuat__caret" aria-hidden="true" />
                        <th>Vật tư</th>
                        <th className="kho-num">SL cấp</th>
                        <th className="kho-num">Số lô</th>
                        {canViewCost && <th className="kho-num">Đơn giá BQ</th>}
                        {canViewCost && <th className="kho-num">Thành tiền</th>}
                        <th>Trạng thái</th>
                      </tr>
                    </thead>
                    <tbody>
                      {blocks.map((b) => (
                        <AllocRowXuat key={b.line.id} block={b} canViewCost={canViewCost} />
                      ))}
                    </tbody>
                  </table>
                </div>
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
            {/* Đã gộp quyền: người lập phiếu ghi sổ luôn (bỏ bước "Lưu nháp") → tạo + ghi sổ 1 lần. */}
            {canPost && (
              <Button variant="accent" loading={busy} onClick={() => setAskPost(true)}>
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

// ── XUẤT: một DÒNG bảng cho mỗi vật tư (thay thẻ AllocCard) ───────────────────
// Chỉ dùng cho phiếu XUẤT. Mỗi mặt hàng = 1 dòng; FIFO đã tự phân bổ lô (KHÔNG sửa tay).
// Cột: [▸] · Vật tư · SL cấp · Số lô · [Đơn giá BQ] · [Thành tiền] · Trạng thái.
// Bấm dòng → xổ bảng lô CHỈ ĐỌC (Mã lô · Nhập · Lấy · [Đơn giá] · [Thành tiền]).
// XUẤT luôn có mã (không "hàng mới") nên không cần combobox/quy đổi/ô lý do.
function AllocRowXuat({ block, canViewCost }: { block: AllocBlock; canViewCost: boolean }) {
  const l = block.line;
  const [open, setOpen] = useState(false);
  // SL cấp = tổng đã phân bổ (Σ lô); đơn giá BQ = bình quân gia quyền theo lô đã lấy.
  const chosen = block.lots.reduce((s, x) => s + x.so_luong, 0);
  const rawCost = block.lots.reduce((s, x) => s + x.so_luong * (x.don_gia_nhap ?? 0), 0);
  const blended = chosen > 0 ? Math.round(rawCost / chosen) : 0;
  const blendedTotal = Math.round(blended * chosen);
  // Thiếu khi FIFO không gom đủ số còn phải cấp (kho không đủ tồn).
  const isShort = chosen < l.sl_con_lai - 1e-9;
  const colSpan = canViewCost ? 7 : 5;

  return (
    <>
      <tr className="kho-xuat__row" onClick={() => setOpen((o) => !o)}>
        <td className="kho-xuat__caret" aria-hidden="true">
          {open ? "▾" : "▸"}
        </td>
        <td>
          <div className="kho-lines__name kho-name-clamp" title={block.matLabel}>
            {block.matLabel}
          </div>
          {block.matCode ? <div className="kho-lines__code">{block.matCode}</div> : null}
        </td>
        <td className="kho-num">{fmtQty(chosen)}</td>
        <td className="kho-num">{block.lots.length}</td>
        {canViewCost && <td className="kho-num">{money(blended)}</td>}
        {canViewCost && <td className="kho-num">{money(blendedTotal)}</td>}
        <td>
          {isShort ? (
            <span className="badge-sem badge-sem--amber">
              Thiếu {fmtQty(l.sl_con_lai - chosen)}
            </span>
          ) : (
            <span className="badge-sem badge-sem--moss">Đủ</span>
          )}
        </td>
      </tr>
      {open && (
        <tr className="kho-xuat__detail">
          <td colSpan={colSpan}>
            <table className="kho-lines">
              <thead>
                <tr>
                  <th className="kho-num">STT</th>
                  <th>Nhập</th>
                  <th className="kho-num">Lấy</th>
                  {canViewCost && <th className="kho-num">Đơn giá</th>}
                  {canViewCost && <th className="kho-num">Thành tiền</th>}
                </tr>
              </thead>
              <tbody>
                {block.lots.length === 0 ? (
                  <tr>
                    <td colSpan={canViewCost ? 5 : 3} className="kho-lines__empty">
                      Kho không đủ hàng — chưa phân bổ được lô.
                    </td>
                  </tr>
                ) : (
                  block.lots.map((lot, i) => (
                    <tr key={lot.lot_id}>
                      <td className="kho-num">{i + 1}</td>
                      <td>{fmtDateISO(lot.ngay_nhap)}</td>
                      <td className="kho-num">{fmtQty(lot.so_luong)}</td>
                      {canViewCost && (
                        <td className="kho-num">
                          {lot.don_gia_nhap != null ? money(lot.don_gia_nhap) : ""}
                        </td>
                      )}
                      {canViewCost && (
                        <td className="kho-num">
                          {lot.don_gia_nhap != null
                            ? money(Math.round(lot.so_luong * lot.don_gia_nhap))
                            : ""}
                        </td>
                      )}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}

// ── NHẬP: một DÒNG bảng cho mỗi vật tư ───────────────────────────────────────
// Chỉ dùng cho phiếu NHẬP (XUẤT dùng AllocRowXuat). Cột:
// STT · Vật tư · ĐVT · Còn phải nhập · SL nhập · Đơn giá · [Thành tiền] · Lý do.
// Ghi chú RIÊNG từng dòng đã bỏ; lý do chỉ hiện khi nhập THIẾU (bắt buộc, backend cũng chặn).
function AllocRow({
  token,
  idx,
  block,
  canViewCost,
  onResolvePick,
  onResetToNew,
  onNewName,
  onNewUnit,
  onCap,
  onLyDo,
  onViTri,
  onUnit,
}: {
  token: string;
  idx: number;
  block: AllocBlock;
  canViewCost: boolean;
  onResolvePick: (m: StockMaterialOption) => void;
  onResetToNew: () => void;
  onNewName: (v: string) => void;
  onNewUnit: (v: string) => void;
  onCap: (v: number) => void;
  onLyDo: (v: string) => void;
  onViTri: (v: string) => void;
  onUnit: (u: "ton" | "phu") => void;
}) {
  const l = block.line;
  // Hàng mới (đề nghị gõ tên tự do) chưa có mã → điền form; backend tạo mã khi Lưu/Ghi sổ.
  const needsCode = block.matId == null;
  const settled = l.sl_con_lai <= 0;
  const donGiaTxt = block.donGia ? `${Number(block.donGia).toLocaleString("vi-VN")} đ` : "—";

  // ĐÃ CẤP ĐỦ: dòng gọn, không ô nhập (giống badge "Đã cấp đủ" ở thẻ XUẤT).
  if (settled) {
    return (
      <tr>
        <td className="kho-num kho-nhap__stt">{idx}</td>
        <td>
          <span className="kho-lines__name">{block.matLabel}</span>
          {block.matCode ? <div className="kho-lines__code">{block.matCode}</div> : null}
        </td>
        <td>{l.dvt}</td>
        <td />
        <td>
          <span className="badge-sem badge-sem--moss">Đã cấp đủ</span>
        </td>
        <td className="kho-num">—</td>
        <td className="kho-num">{donGiaTxt}</td>
        {canViewCost && <td className="kho-num">—</td>}
        <td />
      </tr>
    );
  }

  // Quy đổi: SL nhập theo đơn vị PHỤ → quy về ĐVT tồn để so với "còn phải nhập".
  const hasQd = !!(l.don_vi_phu && l.he_so_quy_doi);
  const qdFactor = block.unit === "phu" && (l.he_so_quy_doi ?? 0) > 0 ? l.he_so_quy_doi! : 1;
  const cappedTon = block.cap * qdFactor;
  // Nhập THIẾU so với đề nghị → ô Lý do hiện ra + bắt buộc (dùng đúng logic thiếu ở submit).
  const isShort = cappedTon > 0 && cappedTon < l.sl_con_lai - 1e-9;
  // Thành tiền khớp cách tính giá vốn phiếu: đơn giá (đề nghị) × SL nhập.
  const thanhTien = Math.round((Number(block.donGia) || 0) * block.cap);
  // Hàng vốn mới nhưng đã trót CHỌN mã có sẵn → cho đổi lại (tạo mới / chọn khác).
  const canReset = l.material_id == null && block.matId != null;

  return (
    <tr>
      <td className="kho-num kho-nhap__stt">{idx}</td>

      {/* Vật tư: hàng mới → combobox tìm/tạo (hint gọn dưới ô); đã có mã → tên + mã (+ nút đổi). */}
      <td>
        {needsCode ? (
          <>
            <MaterialCombobox
              token={token}
              materialName={block.newName}
              onText={onNewName}
              onPick={onResolvePick}
              onCreate={onNewName}
              hideCreate
              placeholder="Gõ tên — chọn hàng có sẵn nếu trùng"
            />
            {hasQd && (
              <p className="kho-hint">
                Quy đổi (đề nghị): 1 {l.don_vi_phu} = {fmtQty(l.he_so_quy_doi)}{" "}
                {block.newUnit.trim() || "ĐVT tồn"}.
              </p>
            )}
          </>
        ) : (
          <>
            <span className="kho-lines__name">{block.matLabel}</span>
            {block.matCode ? <div className="kho-lines__code">{block.matCode}</div> : null}
            {canReset && (
              <button
                type="button"
                className="rc__link-btn"
                style={{ marginLeft: 8 }}
                onClick={onResetToNew}
              >
                đổi
              </button>
            )}
          </>
        )}
      </td>

      {/* ĐVT: hàng mới cho gõ; đã có mã → đọc từ đề nghị. */}
      <td>
        {needsCode ? (
          <input
            className="rc-input kho-nhap__dvt"
            value={block.newUnit}
            onChange={(e) => onNewUnit(e.target.value)}
            placeholder="cái…"
            aria-label="Đơn vị tính"
          />
        ) : (
          l.dvt
        )}
      </td>

      {/* Vị trí cất hàng (kệ/ô) — tuỳ chọn; ghi sổ chép sang lô. */}
      <td>
        <input
          className="rc-input kho-nhap__vitri"
          value={block.viTri}
          onChange={(e) => onViTri(e.target.value)}
          placeholder="kệ A / ô…"
          aria-label="Vị trí cất hàng"
        />
      </td>

      {/* Còn phải nhập (theo ĐVT tồn). */}
      <td className="kho-num">{fmtQty(l.sl_con_lai)}</td>

      {/* SL nhập + (nếu có quy đổi) nút gạt ĐVT tồn/phụ; hint quy đổi gọn dưới ô. */}
      <td className="kho-num">
        <div className="kho-nhap__slwrap">
          <input
            type="number"
            min={0}
            step="any"
            className="rc-input kho-num kho-nhap__sl"
            value={block.cap || ""}
            onChange={(e) => onCap(Number(e.target.value) || 0)}
            aria-label="Số lượng nhập"
          />
          {hasQd && (
            <div className="kho-alloc__uswitch">
              {(["ton", "phu"] as const).map((u) => (
                <button
                  key={u}
                  type="button"
                  className={`seg${block.unit === u ? " is-active" : ""}`}
                  onClick={() => onUnit(u)}
                >
                  {u === "ton" ? l.dvt : l.don_vi_phu}
                </button>
              ))}
            </div>
          )}
        </div>
        {block.unit === "phu" && l.he_so_quy_doi ? (
          <p className="kho-hint">
            = {fmtQty(block.cap * l.he_so_quy_doi)} {l.dvt}
          </p>
        ) : null}
      </td>

      {/* Đơn giá: LẤY TỪ ĐỀ NGHỊ, chỉ đọc. */}
      <td className="kho-num">{donGiaTxt}</td>

      {/* Thành tiền = đơn giá × SL nhập (khớp giá vốn phiếu). Ẩn cột khi thiếu quyền. */}
      {canViewCost && (
        <td className="kho-num">{block.cap > 0 ? money(thanhTien) : "—"}</td>
      )}

      {/* Lý do: CHỈ hiện ô khi nhập THIẾU (bắt buộc); đủ/không nhập → ô trống. */}
      <td>
        {isShort ? (
          <input
            className={`rc-input kho-nhap__lydo${!block.lyDo.trim() ? " rc-input--warn" : ""}`}
            value={block.lyDo}
            onChange={(e) => onLyDo(e.target.value)}
            placeholder={`Vì sao chỉ nhập ${fmtQty(cappedTon)}/${fmtQty(l.sl_con_lai)}?`}
            aria-label="Lý do nhập thiếu"
          />
        ) : null}
      </td>
    </tr>
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
  // Hủy phiếu ĐÃ DỜI sang luồng đề nghị (InboxRequestDrawer) — phiếu không còn nút Hủy.
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
        materialCode: l.material_code,
        materialName: l.material_name,
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
                          <th style={{ width: 52 }}>ĐVT</th>
                          {/* SL đề nghị (số đã xin) đứng TRƯỚC SL thực để đối chiếu. */}
                          <th className="kho-num">SL đề nghị</th>
                          <th className="kho-num">
                            {v.loai === "NHAP" ? "SL thực nhận" : "SL thực xuất"}
                          </th>
                          {canViewCost && <th className="kho-num">Đơn giá</th>}
                          {canViewCost && <th className="kho-num">Thành tiền</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {v.lines.map((l) => (
                          <tr key={l.id}>
                            <td>
                              <div className="kho-lines__name">{l.material_name ?? "—"}</div>
                              <div className="kho-lines__code">{l.material_code ?? ""}</div>
                            </td>
                            <td className="kho-lines__code">{l.dvt ?? "—"}</td>
                            <td className="kho-num">
                              {l.sl_de_nghi != null ? fmtQty(l.sl_de_nghi) : "—"}
                            </td>
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
            {/* HỦY phiếu ĐÃ DỜI sang đề nghị (InboxRequestDrawer): hủy chỉ qua luồng đề nghị. */}
            {/* Ghi sổ: cùng quyền lập phiếu (đã gộp) — người lập tự ghi sổ được. */}
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
  const [materialId, setMaterialId] = useState<number | null>(null);
  const [matQuery, setMatQuery] = useState("");
  const [matOpts, setMatOpts] = useState<StockMaterialOption[]>([]);
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
        for (const t of ths) m[`${t.kho_id}:${t.material_id}`] = t;
        setThByKey(m);
      })
      .catch(() => {});
  }, [token]);

  // Chọn vật tư (+ kho) → nạp ngưỡng đã khai của vật tư đó; chưa khai thì để trống (khai mới).
  useEffect(() => {
    if (materialId == null || khoId == null) return;
    const t = thByKey[`${khoId}:${materialId}`];
    setNguongTon(t?.nguong_ton != null ? String(t.nguong_ton) : "");
    setNguongToiDa(t?.nguong_toi_da != null ? String(t.nguong_toi_da) : "");
    setCanhBao(t?.canh_bao ?? true);
    setOk(false);
  }, [materialId, khoId, thByKey]);

  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(() => {
      api.kho.deNghi
        .vatTu(token, matQuery || null, 30)
        .then((r) => {
          if (!cancelled) setMatOpts(r);
        })
        .catch(() => {});
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [token, matQuery]);

  async function save() {
    if (materialId == null || khoId == null) {
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
        material_id: materialId,
        kho_id: khoId,
        nguong_ton: ton,
        nguong_can_ton: null,
        nguong_toi_da: max,
        canh_bao: canhBao,
      });
      setThByKey((prev) => ({ ...prev, [`${khoId}:${materialId}`]: t }));
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
                <Select
                  portal
                  searchable
                  options={matOpts.map((m) => ({
                    value: m.id,
                    label: m.name ?? String(m.id),
                    hint: m.code ?? undefined,
                  }))}
                  value={materialId}
                  onChange={(v) => {
                    setMaterialId(v == null ? null : Number(v));
                    setOk(false);
                  }}
                  onSearch={setMatQuery}
                  placeholder="Chọn vật tư"
                  searchPlaceholder="Tìm mã / tên vật tư…"
                  ariaLabel="Vật tư"
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
