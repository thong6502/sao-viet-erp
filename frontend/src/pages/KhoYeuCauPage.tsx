// Màn "Hộp yêu cầu kho" — thủ kho / quản lý kho / kế toán kho (scope `all`).
//
// Yêu cầu đã duyệt VÀ phiếu nhập/xuất nằm CÙNG MỘT MÀN, phân bằng tab: với người trong kho
// đây là một việc liên tục (nhận yêu cầu → lấy hàng theo lô → ghi sổ), tách hai màn là bắt họ
// nhảy qua lại giữa hai danh sách của cùng một chứng từ.
//
// Hai cột nhạy cảm — "Tồn khả dụng" và "Giá vốn" — KHÔNG render khi thiếu quyền: cột biến mất
// khỏi <thead> chứ không hiện "—". Dấu gạch vẫn là một câu trả lời ("chỗ này có số, bạn không
// được xem"), còn ở đây phải im lặng hoàn toàn.
import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type DieuChinhLichSu,
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
import { Icon } from "../components/Icons";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DiscardChangesDialog } from "../components/DiscardChangesDialog";
import { MaterialCombobox } from "../components/MaterialCombobox";
import { Select } from "../components/Select";
import { fmtDate, fmtDateISO, fmtDateTime, money } from "../utils/format";
import {
  printStockVoucher,
  printTransferVoucher,
  type StockVoucherPrintData,
  type TransferPrintData,
} from "../utils/printStockVoucher";
import {
  DateFilterHead,
  DecimalInput,
  LoaiYeuCauChip,
  RequestStatusBadge,
  VoucherStatusBadge,
  TransferStatusBadge,
  type TransferStatus,
  PageSizeSelect,
  DEFAULT_PAGE_SIZE,
  fmtQty,
  isOverdue,
  readStoredKho,
  todayISO,
  useHeaderTitles,
  writeStoredKho,
} from "./khoShared";
import { tenDonVi, useNapTenDonVi } from "./tenDonVi";
import "./rebuild-catalog.css";
import "./kho-request.css";

const KHO_KEY = "kho.yeu-cau.kho-id";

type TabId = "tat-ca" | "can-cap" | "done" | "da-huy";

const TAB_STATUSES: Record<TabId, StockRequestStatus[]> = {
  "tat-ca": ["approved", "received", "preparing", "partial", "done", "cancelled"],
  // "Cần cấp" = MỌI yêu cầu còn phải cấp (chưa xong, chưa hủy) → gồm cả "Đã cấp một phần" để thủ
  // kho thấy ngay cái đang dở mà nhập/cấp tiếp, không bị chìm trong "Tất cả".
  "can-cap": ["approved", "received", "preparing", "partial"],
  done: ["done"],
  "da-huy": ["cancelled"],
};
// Một lần gọi cho cả 4 tab yêu cầu → số trên tab luôn khớp bảng, không lệch giữa các lần fetch.
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

/** Mã lệnh/bài của một yêu cầu (mg 0175) — gộp các dòng, hiện tối đa 2 rồi "+n".
 *
 * Một yêu cầu thường xin cho MỘT lệnh, nhưng không cấm xin cho nhiều — nên vẫn phải gộp thay vì
 * lấy dòng đầu. Không dòng nào gắn lệnh (xin lặt vặt) thì để gạch, đó cũng là một câu trả lời. */
function maLenhCuaDeNghi(r: StockRequest) {
  const mas = [...new Set(
    r.lines.map((l) => l.lsx_ma ?? l.bai_ghep_ma).filter((m): m is string => !!m),
  )];
  if (!mas.length) return <span className="rc__muted">—</span>;
  return (
    <>
      <div className="kho-lines__code">{mas.slice(0, 2).join(", ")}</div>
      {mas.length > 2 && <div className="rc__muted">+{mas.length - 2} lệnh</div>}
    </>
  );
}

function progressOf(r: StockRequest): { done: number; total: number; pct: number } {
  const total = r.lines.reduce((s, l) => s + l.sl_duyet, 0);
  const done = r.lines.reduce((s, l) => s + l.sl_da_ung, 0);
  return { done, total, pct: total > 0 ? Math.min(100, (done / total) * 100) : 0 };
}

/** Ký hiệu "≈" NHỎ đứng trước số khi giá trị HIỂN THỊ đã bị làm tròn (giá trị thật lẻ hơn).
 *  `decimals` = số chữ số lẻ của cách hiển thị. Tròn khớp → không hiện gì (số tròn để nguyên). */
function ApproxMark({ raw, decimals }: { raw: number; decimals: number }) {
  const factor = 10 ** decimals;
  if (Math.abs(raw - Math.round(raw * factor) / factor) <= 1e-9) return null;
  return <span className="kho-approx" title="Số đã làm tròn để hiển thị (giá trị thật lẻ hơn)">≈ </span>;
}

export function KhoYeuCauPage({
  eventTick = 0,
  loai,
  dieuChuyen = false,
  openRequestId = null,
  onOpenRequestConsumed,
}: {
  eventTick?: number;
  /** Khoá chiều theo tab (Nhập/Xuất): lọc yêu cầu + phiếu theo loai. */
  loai: StockRequestKind;
  /** Tab ĐIỀU CHUYỂN: chỉ hiện yêu cầu điều chuyển (dieu_chuyen=true). */
  dieuChuyen?: boolean;
  /** Bấm thông báo → mở sẵn drawer "ứng theo yêu cầu" đúng id này. */
  openRequestId?: number | null;
  onOpenRequestConsumed?: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("kho", "create");
  // Hover tiêu đề cột → hiện tên cột đầy đủ (kể cả khi bị cắt).
  const tableRef = useHeaderTitles();
  // Ghi sổ đã GỘP vào quyền "create" (bỏ tách "post"/SoD) — khớp backend: post_voucher chỉ đòi
  // create. Ai lập được phiếu là ghi sổ được luôn, không còn bước "Chờ ghi sổ" chờ người khác.
  const canPost = canCreate;
  const canViewStock = can("kho", "view_stock");
  const canViewCost = can("kho", "view_cost");

  const [khoList, setKhoList] = useState<KhoOption[]>([]);
  const [khoId, setKhoId] = useState<number | null>(() => readStoredKho(KHO_KEY));
  const [requests, setRequests] = useState<StockRequest[]>([]);
  const [totalCount, setTotalCount] = useState(0);         // tổng bản ghi khớp lọc (từ BE)
  const [counts, setCounts] = useState<Record<string, number>>({}); // số theo trạng thái → badge tab
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<TabId>("can-cap");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);
  // Lọc khoảng ngày theo cột "Cần ngày" (ngay_can) — bấm tiêu đề cột để bung Từ/Đến.
  const [dNeed, setDNeed] = useState({ from: "", to: "" });

  const [openRequest, setOpenRequest] = useState<number | null>(null);
  const [creatingFor, setCreatingFor] = useState<StockRequest | null>(null);
  const [openVoucher, setOpenVoucher] = useState<number | null>(null);
  // Tab ĐIỀU CHUYỂN: một drawer DUY NHẤT (phiếu điều chuyển làm mặt tiền) — bỏ qua openRequest/
  // openVoucher/creatingFor của nhánh Nhập/Xuất.
  const [openTransfer, setOpenTransfer] = useState<number | null>(null);

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
    // KHÔNG lọc theo kho: yêu cầu giờ không gắn kho (kho quyết ở phiếu) → mọi yêu cầu đã duyệt
    // đều vào chung một hộp cho thủ kho xử lý. Ô kho ở toolbar chỉ là kho MẶC ĐỊNH khi lập phiếu.
    // BE-paging: chỉ tải ĐÚNG trang theo tab + lọc ngày; đếm số theo trạng thái riêng (badge tab).
    const filters = {
      q: q || null,
      loai,
      dieu_chuyen: dieuChuyen,
      ngay_can_tu: dNeed.from || null,
      ngay_can_den: dNeed.to || null,
    };
    Promise.all([
      api.kho.deNghi.list(token, { ...filters, trang_thai: TAB_STATUSES[tab], page, size: pageSize }),
      api.kho.deNghi.tabCounts(token, { ...filters, trang_thai: INBOX_STATUSES }),
    ])
      .then(([r, c]) => {
        setRequests(r.items);
        setTotalCount(r.total);
        setCounts(c);
        setError(null);
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Không tải được hộp yêu cầu kho."),
      )
      .finally(() => setLoading(false));
  }, [token, q, loai, dieuChuyen, dNeed, tab, page, pageSize]);

  // "Lập phiếu" / "Xem phiếu": yêu cầu đã có phiếu ĐANG CHỜ GHI SỔ (`open_voucher_id`) thì MỞ LẠI
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

  // Bấm thông báo "yêu cầu mới chờ cấp" → mở sẵn drawer ứng theo đúng yêu cầu đó.
  useEffect(() => {
    if (openRequestId == null) return;
    if (dieuChuyen) setOpenTransfer(openRequestId);
    else setOpenRequest(openRequestId);
    onOpenRequestConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openRequestId]);

  useEffect(() => {
    setPage(1);
  }, [tab, q, khoId, dNeed, pageSize]);

  // Số trên tab = CỘNG số theo trạng thái (BE trả `counts`) của các trạng thái thuộc tab đó.
  function countOf(id: TabId): number {
    return TAB_STATUSES[id].reduce((s, st) => s + (counts[st] ?? 0), 0);
  }

  // BE đã lọc (tab + ngày + q) + phân trang + sắp theo id giảm (≈ created_at desc như sortInbox)
  // → dùng thẳng danh sách trả về làm trang hiện tại, không cắt/lọc lại ở client.
  const total = totalCount;
  const maxPage = Math.max(1, Math.ceil(total / pageSize));
  const pageRequests = requests;
  // "Mới" = yêu cầu MỚI NHẤT — nằm đầu TRANG 1 (BE sắp id desc); trang khác không đánh dấu.
  const newestReqId = page === 1 ? (requests[0]?.id ?? null) : null;

  // Tab ĐIỀU CHUYỂN đổi nhãn "Cần cấp" → "Chờ ghi sổ" (giữ nguyên TabId/TAB_STATUSES: can-cap =
  // yêu cầu NHẬP đích còn phiếu nháp chờ ghi sổ). Nhánh Nhập/Xuất giữ nhãn cũ.
  const tabs: { id: TabId; label: string }[] = [
    { id: "tat-ca", label: "Tất cả" },
    { id: "can-cap", label: dieuChuyen ? "Chờ ghi sổ" : "Cần cấp" },
    { id: "done", label: "Hoàn tất" },
    { id: "da-huy", label: "Đã hủy" },
  ];

  // Cột yêu cầu: 8 khi có nút Lập phiếu, 7 khi không (đã bỏ cột Tồn — yêu cầu không gắn kho).
  // Mã · Loại · Bộ phận · Vật tư · Cho lệnh · Tiến độ · Cần ngày · Trạng thái (+ cột thao tác).
  const reqCols = canCreate ? 9 : 8;

  return (
    <>
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">{dieuChuyen ? "Phiếu điều chuyển" : "Phiếu từ yêu cầu"}</h1>
          <span className="rc__count">
            {totalCount} {dieuChuyen ? "phiếu" : "yêu cầu"}
          </span>
        </div>
        <p className="rc__sub">
          {dieuChuyen
            ? "Điều chuyển nội bộ giữa các kho — chờ kho đích ghi sổ."
            : "Yêu cầu đã duyệt chờ kho cấp, và phiếu nhập/xuất đã lập."}
        </p>
      </header>

      <div className="rc__toolbar">
        <div className="rc__search-wrapper">
          <SearchIcon />
          <input
            className="rc__search"
            placeholder="Tìm mã yêu cầu / số phiếu / vật tư…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        {/* LỌC TRẠNG THÁI — cùng dải Filter Chips với màn Yêu cầu nhập xuất cho nhất quán. */}
        <div className="kho-filter-chips">
          {tabs.map((t) => {
            const count = countOf(t.id);
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                className={`kho-filter-chip${active ? " is-active" : ""}`}
                onClick={() => setTab(t.id)}
              >
                <span>{t.label}</span>
                <span className="kho-filter-chip__count">{count}</span>
              </button>
            );
          })}
        </div>
        {/* Kho là BẮT BUỘC ở màn này: chọn kho để tra cứu và lập phiếu */}
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
        {dieuChuyen ? (
          <TransferTable
            rows={pageRequests}
            loading={loading}
            canCreate={canCreate}
            canViewCost={canViewCost}
            newestReqId={newestReqId}
            tableRef={tableRef}
            pageSize={pageSize}
            onOpen={setOpenTransfer}
          />
        ) : (
          <table ref={tableRef} className="rc__table rc__table--fixed">
            <thead>
              <tr>
                <th style={{ width: "13%" }}>Mã</th>
                <th style={{ width: "10%" }}>Loại</th>
                <th style={{ width: "15%" }}>Bộ phận · Người</th>
                <th>Vật tư</th>
                {/* mg 0175 — soạn hàng theo LỆNH: thủ kho gom được các yêu cầu của cùng một lệnh
                    thay vì soạn rời từng phiếu. Cột thay cho việc dựng một màn "soạn hàng" riêng. */}
                <th style={{ width: "11%" }}>Cho lệnh</th>
                <th style={{ width: "12%" }}>Tiến độ</th>
                <DateFilterHead
                  label="Cần lúc"
                  from={dNeed.from}
                  to={dNeed.to}
                  onChange={(from, to) => setDNeed({ from, to })}
                  style={{ width: "11%" }}
                />
                <th style={{ width: "12%" }}>Trạng thái</th>
                {canCreate && <th className="rc__actcol" style={{ width: "10%" }} />}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonRows cols={reqCols} />
              ) : requests.length === 0 ? (
                <EmptyRow
                  cols={reqCols}
                  text={
                    requests.length === 0
                      ? "Chưa có yêu cầu nào được duyệt. Yêu cầu chỉ vào hộp này sau khi bộ phận duyệt."
                      : "Không có yêu cầu nào ở trạng thái này."
                  }
                  onClear={requests.length === 0 ? undefined : () => setTab("can-cap")}
                />
              ) : (
                <>
                  {pageRequests.map((r) => {
                  const p = progressOf(r);
                  const overdue = isOverdue(r.ngay_can, r.trang_thai, r.can_luc);
                  return (
                    <tr
                      key={r.id}
                      className={`rc__row${overdue ? " kho-row--overdue" : ""}${r.id === newestReqId ? " rc__row--new" : ""}`}
                      onClick={() => setOpenRequest(r.id)}
                    >
                      <td className="rc__nowrap">
                        <span className="rc__code-badge">{r.ma}</span>
                        {r.id === newestReqId && <span className="kho-new-pill">Mới</span>}
                      </td>
                      <td>
                        <LoaiYeuCauChip loai={r.loai} dieuChuyen={r.dieu_chuyen} />
                      </td>
                      <td>
                        <div className="kho-user-cell">
                          <div className="kho-user-avatar kho-user-avatar--sm">
                            {(r.nguoi_tao_ten || "U").slice(0, 1).toUpperCase()}
                          </div>
                          <div>
                            <div className="rc__name">{r.nguoi_tao_ten ?? "—"}</div>
                            <div className="rc__muted">
                              {r.bo_phan_ten ?? "—"}
                              {/* Yêu cầu SINH TỪ đề nghị cấp vật tư công đoạn → thêm tên công đoạn cho
                                  thủ kho biết đang soạn cho khâu nào (task-8-ruling-man-kho). */}
                              {r.san_xuat_cong_doan_ten ? ` · ${r.san_xuat_cong_doan_ten}` : ""}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <div
                          className="rc__name kho-name-clamp"
                          title={r.lines[0]?.hang_ten ?? undefined}
                        >
                          {r.lines[0]?.hang_ten ?? "—"}
                        </div>
                        {r.lines.length > 1 && (
                          <span className="badge-sem badge-sem--muted kho-morepill">+{r.lines.length - 1} mã</span>
                        )}
                      </td>
                      <td>{maLenhCuaDeNghi(r)}</td>
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
                        {/* GIỜ cần thật (từ đề nghị sản xuất) ưu tiên trước — `ngay_can` chỉ có DATE
                            nên không diễn đạt được ca chiều (task-8-ruling-man-kho). */}
                        <div>{r.can_luc ? fmtDateTime(r.can_luc) : r.ngay_can ? fmtDateISO(r.ngay_can) : "—"}</div>
                        {overdue && <span className="kho-priority-badge kho-priority-badge--critical" style={{ marginTop: 2 }}>Quá hạn</span>}
                      </td>
                      <td>
                        <RequestStatusBadge status={r.trang_thai} />
                      </td>
                      {canCreate && (
                        <td className="rc__actcol" onClick={(e) => e.stopPropagation()}>
                          {FULFILLABLE.includes(r.trang_thai) && (
                            <button
                              type="button"
                              className={`kho-act-btn${r.open_voucher_id != null ? " kho-act-btn--secondary" : ""}`}
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
                </>
              )}
              {/* Hàng ĐỆM giữ chiều cao bảng cố định — ít yêu cầu vẫn trải đủ pageSize dòng (đồng bộ
                  với các bảng kho khác), không teo lại khi lọc còn vài dòng. */}
              {Array.from({
                length: Math.max(
                  0,
                  pageSize - (loading ? 5 : requests.length === 0 ? 1 : pageRequests.length),
                ),
              }).map((_, i) => (
                <tr key={`reqfiller-${i}`} className="rc__filler" aria-hidden="true">
                  <td colSpan={reqCols}>&nbsp;</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {total > 0 && (
        <div className="kho-pager">
          <PageSizeSelect value={pageSize} onChange={setPageSize} />
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

      {openRequest != null && token && (
        <InboxRequestDrawer
          key={`inbox-${openRequest}`}
          token={token}
          khoId={khoId}
          requestId={openRequest}
          canCreate={canCreate}
          canViewStock={canViewStock}
          canViewCost={canViewCost}
          onClose={() => setOpenRequest(null)}
          onCreateVoucher={openFulfil}
          onOpenVoucher={setOpenVoucher}
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

      {dieuChuyen && openTransfer != null && token && (
        <TransferDrawer
          key={`tr-${openTransfer}`}
          token={token}
          requestId={openTransfer}
          canCreate={canCreate}
          canViewCost={canViewCost}
          onClose={() => setOpenTransfer(null)}
          onChanged={load}
        />
      )}
    </>
  );
}

// ── ĐIỀU CHUYỂN: bảng list + drawer (phiếu điều chuyển làm mặt tiền) ──────────

/** Trạng thái PHIẾU ĐIỀU CHUYỂN suy từ yêu cầu NHẬP đích: hủy → da-huy · hoàn tất → hoan-tat ·
 *  còn phiếu nháp chờ ghi sổ → cho-ghi-so. */
function transferStatusOf(r: StockRequest): TransferStatus {
  if (r.trang_thai === "cancelled") return "da-huy";
  if (r.trang_thai === "done") return "hoan-tat";
  return "cho-ghi-so";
}

function TransferTable({
  rows,
  loading,
  canCreate,
  canViewCost,
  newestReqId,
  tableRef,
  pageSize,
  onOpen,
}: {
  rows: StockRequest[];
  loading: boolean;
  canCreate: boolean;
  canViewCost: boolean;
  newestReqId: number | null;
  tableRef: RefObject<HTMLTableElement>;
  pageSize: number;
  onOpen: (id: number) => void;
}) {
  // Mã · Tuyến · Ngày · Trạng thái · [Tổng giá vốn] · Số dòng · [thao tác]
  const cols = 5 + (canViewCost ? 1 : 0) + (canCreate ? 1 : 0);
  return (
    <table ref={tableRef} className="rc__table rc__table--fixed">
      <thead>
        <tr>
          <th style={{ width: "15%" }}>Mã</th>
          <th style={{ width: "27%" }}>Tuyến</th>
          <th style={{ width: "13%" }}>Ngày</th>
          <th style={{ width: "15%" }}>Trạng thái</th>
          {canViewCost && <th className="kho-num" style={{ width: "15%" }}>Tổng giá vốn</th>}
          <th className="kho-num" style={{ width: "9%" }}>Số dòng</th>
          {canCreate && <th className="rc__actcol" style={{ width: "12%" }} />}
        </tr>
      </thead>
      <tbody>
        {loading ? (
          <SkeletonRows cols={cols} />
        ) : rows.length === 0 ? (
          <EmptyRow
            cols={cols}
            text="Chưa có phiếu điều chuyển. Tạo bằng nút Chuyển kho ở màn tồn kho."
          />
        ) : (
          rows.map((r) => {
            const giaVon = r.lines.reduce((s, l) => s + (l.don_gia ?? 0) * l.sl_duyet, 0);
            return (
              <tr
                key={r.id}
                className={`rc__row${r.id === newestReqId ? " rc__row--new" : ""}`}
                onClick={() => onOpen(r.id)}
              >
                <td className="rc__nowrap">
                  <span className="rc__code-badge">{r.ma}</span>
                  {r.id === newestReqId && <span className="kho-new-pill">Mới</span>}
                </td>
                <td>
                  <div className="kho-route">
                    <span className="rc__name">{r.kho_nguon_ten ?? "—"}</span>
                    <span aria-hidden className="kho-route__sep">⇄</span>
                    <span className="rc__name">{r.kho_ten ?? "—"}</span>
                  </div>
                </td>
                <td className="rc__nowrap">{fmtDate(r.created_at)}</td>
                <td>
                  <TransferStatusBadge status={transferStatusOf(r)} />
                </td>
                {canViewCost && <td className="kho-num">{money(giaVon)}</td>}
                <td className="kho-num">{r.lines.length}</td>
                {canCreate && (
                  <td className="rc__actcol" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className={`kho-act-btn${r.open_voucher_id == null ? " kho-act-btn--secondary" : ""}`}
                      onClick={() => onOpen(r.id)}
                    >
                      {r.open_voucher_id != null ? "Ghi sổ" : "Xem"}
                    </button>
                  </td>
                )}
              </tr>
            );
          })
        )}
        {/* Hàng ĐỆM giữ chiều cao bảng cố định (giống bảng khác) — ít phiếu vẫn trải đủ pageSize dòng. */}
        {Array.from({
          length: Math.max(0, pageSize - (loading ? 5 : rows.length === 0 ? 1 : rows.length)),
        }).map((_, i) => (
          <tr key={`tfiller-${i}`} className="rc__filler" aria-hidden="true">
            <td colSpan={cols}>&nbsp;</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function TransferDrawer({
  token,
  requestId,
  canCreate,
  canViewCost,
  onClose,
  onChanged,
}: {
  token: string;
  requestId: number;
  canCreate: boolean;
  canViewCost: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  useNapTenDonVi();
  const [req, setReq] = useState<StockRequest | null>(null);
  const [v, setV] = useState<StockVoucher | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [askPost, setAskPost] = useState(false);
  const [askCancel, setAskCancel] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [popupBlocked, setPopupBlocked] = useState(false);
  // Vị trí cất lô khai TRƯỚC ghi sổ (phiếu điều chuyển đích không có form nhập) — keyed theo line id.
  const [viTriEdit, setViTriEdit] = useState<Record<number, string>>({});

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.kho.deNghi
      .get(token, requestId)
      .then(async (r) => {
        if (cancelled) return;
        setReq(r);
        // Phiếu NHẬP đích: còn chờ ghi sổ thì có `open_voucher_id`; đã ghi sổ / đã hủy thì null →
        // truy lại qua list (request_id + loai NHAP) để vẫn hiện được các dòng theo lô.
        let voucherId = r.open_voucher_id;
        if (voucherId == null) {
          const list = await api.kho.phieu
            .list(token, { request_id: requestId, loai: "NHAP", size: 5 })
            .catch(() => null);
          voucherId = list?.items[0]?.id ?? null;
        }
        if (voucherId != null) {
          const voucher = await api.kho.phieu.get(token, voucherId).catch(() => null);
          if (!cancelled) setV(voucher);
        }
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Không tải được phiếu điều chuyển."),
      )
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, requestId]);

  // Nạp vị trí sẵn có của dòng phiếu vào ô sửa (điều chuyển đích thường trống tới khi thủ kho khai).
  useEffect(() => {
    if (!v) return;
    const init: Record<number, string> = {};
    v.lines.forEach((l) => {
      init[l.id] = l.vi_tri ?? "";
    });
    setViTriEdit(init);
  }, [v]);

  // Gợi ý vị trí cất (kệ/ô) đã khai của kho ĐÍCH — chỉ để GỢI Ý (datalist), vẫn gõ tự do được.
  const [viTriOptions, setViTriOptions] = useState<string[]>([]);
  useEffect(() => {
    const kho = v?.kho_id;
    if (kho == null) { setViTriOptions([]); return; }
    let alive = true;
    api.kho.viTri.list(token, kho)
      .then((r) => { if (alive) setViTriOptions(r.items.map((x) => x.ma)); })
      .catch(() => { if (alive) setViTriOptions([]); });
    return () => { alive = false; };
  }, [token, v?.kho_id]);

  const status: TransferStatus =
    req?.trang_thai === "cancelled"
      ? "da-huy"
      : v?.trang_thai === "posted" || req?.trang_thai === "done"
        ? "hoan-tat"
        : "cho-ghi-so";
  // Ghi sổ / Hủy chỉ khi CHƯA ghi sổ (còn phiếu nháp đích) — đã ghi sổ/hủy → chỉ đọc.
  const canAct =
    canCreate && req != null && req.open_voucher_id != null && req.trang_thai !== "cancelled";

  function ghiSo() {
    if (!v) return;
    setBusy(true);
    setError(null);
    // Lưu VỊ TRÍ đã khai (nếu có) TRƯỚC khi ghi sổ → ghi sổ chép sang lô. Một nhịp thao tác.
    const viTriLines = v.lines.map((l) => ({
      line_id: l.id,
      vi_tri: (viTriEdit[l.id] ?? "").trim() || null,
    }));
    api.kho.phieu
      .suaViTriDong(token, v.id, viTriLines)
      .then(() => api.kho.phieu.ghiSo(token, v.id))
      .then(() => {
        onChanged();
        onClose();
      })
      .catch((e) => {
        setAskPost(false);
        setBusy(false);
        setError(e instanceof ApiError ? e.message : "Không ghi sổ được phiếu.");
      });
  }

  function huy() {
    const ly = cancelReason.trim();
    if (!ly) return;
    setBusy(true);
    setError(null);
    api.kho.dieuChuyen
      .huy(token, requestId, ly)
      .then(() => {
        onChanged();
        onClose();
      })
      .catch((e) => {
        setAskCancel(false);
        setBusy(false);
        setError(e instanceof ApiError ? e.message : "Không hủy được phiếu điều chuyển.");
      });
  }

  function doPrint() {
    if (!req) return;
    // Mẫu điều chuyển RIÊNG (Từ kho → Đến kho + HSD), không phải 01-VT/02-VT. Dòng lấy từ phiếu
    // NHẬP đích (per-lô + giá vốn + HSD). Giá vốn null khi thiếu quyền → bản in tự bỏ 2 cột tiền.
    const data: TransferPrintData = {
      docNo: req.ma,
      docDate: v ? v.ngay : (req.created_at ? req.created_at.slice(0, 10) : null),
      khoNguon: req.kho_nguon_ten,
      khoDich: req.kho_ten,
      nguoiLap: v?.nguoi_lap_ten ?? req.nguoi_tao_ten ?? null,
      nguoiGiaoNhan: v?.nguoi_giao_nhan ?? null,
      lyDo: v?.ghi_chu ?? req.ghi_chu ?? null,
      // In ẩn GIÁ nghiêm theo quyền `view_cost` (không dựa API — API còn nới cho người tạo yêu cầu).
      tongTien: canViewCost ? (v?.gia_von ?? null) : null,
      cancelled: req.trang_thai === "cancelled",
      lines: (v?.lines ?? []).map((l) => ({
        materialCode: l.hang_ma,
        materialName: l.hang_ten,
        dvt: tenDonVi(l.dvt) ?? l.dvt,
        soLuong: l.so_luong,
        donGia: canViewCost ? l.don_gia : null,
        thanhTien: canViewCost ? l.thanh_tien : null,
        hsd: l.hsd ?? null,
      })),
    };
    setPopupBlocked(!printTransferVoucher(data));
  }

  return (
    <>
      <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
        <aside className="rc-drawer rc-drawer--wide" onClick={(e) => e.stopPropagation()}>
          <header className="rc-drawer__head">
            <div>
              <div className="rc-drawer__kicker">PHIẾU ĐIỀU CHUYỂN</div>
              <h2 className="rc-drawer__title">{req?.ma ?? "Đang tải…"}</h2>
            </div>
            <div className="kho-headside">
              {req && <TransferStatusBadge status={status} />}
              <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
                <Icon name="x" size={16} />
              </button>
            </div>
          </header>

          <div className="rc-drawer__body">
            {error && (
              <div className="banner banner--error" role="alert">
                <span>{error}</span>
              </div>
            )}
            {popupBlocked && (
              <div className="banner banner--warn" role="alert">
                <span>Trình duyệt đã chặn cửa sổ in. Cho phép pop-up cho trang này rồi bấm In lại.</span>
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
                  <h3 className="rc-sec__title">Tuyến điều chuyển</h3>
                  <div className="kho-info-grid">
                    <div className="kho-info-item">
                      <span className="kho-info-item__label">Từ kho (nguồn)</span>
                      <div className="kho-info-item__val" style={{ fontWeight: 600, color: "var(--moss-deep, #1e3a29)" }}>
                        {req.kho_nguon_ten ?? "—"}
                      </div>
                    </div>
                    <div className="kho-info-item">
                      <span className="kho-info-item__label">Đến kho (nhập về)</span>
                      <div className="kho-info-item__val" style={{ fontWeight: 600, color: "var(--steel-deep, #1e293b)" }}>
                        {req.kho_ten ?? "—"}
                      </div>
                    </div>
                    <div className="kho-info-item">
                      <span className="kho-info-item__label">Ngày</span>
                      <div className="kho-info-item__val">
                        {v ? fmtDateISO(v.ngay) : fmtDate(req.created_at)}
                      </div>
                    </div>
                    <div className="kho-info-item">
                      <span className="kho-info-item__label">Số CT phiếu nhập</span>
                      <div className="kho-info-item__val">
                        {v?.ma ? <span className="rc__code-badge">{v.ma}</span> : "—"}
                      </div>
                    </div>
                    <div className="kho-info-item">
                      <span className="kho-info-item__label">Người tạo</span>
                      <div className="kho-info-item__val">
                        {req.nguoi_tao_ten ?? "—"}
                        {req.bo_phan_ten ? ` (${req.bo_phan_ten})` : ""}
                      </div>
                    </div>
                    <div className="kho-info-item">
                      <span className="kho-info-item__label">Tạo lúc</span>
                      <div className="kho-info-item__val">{fmtDateTime(req.created_at)}</div>
                    </div>
                  </div>
                </section>

                <div className="banner banner--info">
                  <span>Ghi sổ sẽ <b>TRỪ</b> kho nguồn và <b>CỘNG</b> kho đích cùng lúc.</span>
                </div>

                <section className="rc-sec">
                  <h3 className="rc-sec__title">Dòng điều chuyển (theo lô)</h3>
                  <div className="kho-lines__wrap kho-lines-card">
                    {viTriOptions.length > 0 && (
                      <datalist id="kho-vitri-transfer">
                        {viTriOptions.map((x) => <option key={x} value={x} />)}
                      </datalist>
                    )}
                    <table className="kho-lines" style={{ width: "100%", tableLayout: "auto" }}>
                      <thead>
                        <tr>
                          <th style={{ minWidth: 220 }}>Vật tư</th>
                          <th className="kho-num" style={{ width: 120 }}>Số lượng</th>
                          {canViewCost && <th className="kho-num" style={{ width: 120 }}>Giá vốn</th>}
                          {canViewCost && <th className="kho-num" style={{ width: 130 }}>Thành tiền</th>}
                          <th style={{ width: 110 }}>HSD</th>
                          <th style={{ width: 180 }}>Vị trí</th>
                        </tr>
                      </thead>
                      <tbody>
                        {!v || v.lines.length === 0 ? (
                          <tr>
                            <td colSpan={canViewCost ? 6 : 4} className="kho-lines__empty" style={{ textAlign: "center", padding: "20px 0" }}>
                              <i>Không có dòng nào.</i>
                            </td>
                          </tr>
                        ) : (
                          v.lines.map((l) => (
                            <tr key={l.id}>
                              <td>
                                <div className="kho-lines__name" style={{ fontWeight: 600 }}>{l.hang_ten ?? "—"}</div>
                                <div className="kho-lines__code" style={{ fontSize: 11, color: "var(--ash-2)" }}>{l.hang_ma ?? ""}</div>
                              </td>
                              <td className="kho-num">
                                <strong>{fmtQty(l.so_luong)}</strong> {tenDonVi(l.dvt) ?? l.dvt ?? ""}
                              </td>
                              {canViewCost && (
                                <td className="kho-num">
                                  {l.don_gia != null ? money(l.don_gia) : "—"}
                                </td>
                              )}
                              {canViewCost && (
                                <td className="kho-num">
                                  <strong>{l.thanh_tien != null ? money(l.thanh_tien) : "—"}</strong>
                                </td>
                              )}
                              <td>{l.hsd ? fmtDateISO(l.hsd) : "—"}</td>
                              <td>
                                {canAct ? (
                                  <input
                                    className="rc-input"
                                    style={{ minWidth: 150, width: "100%" }}
                                    value={viTriEdit[l.id] ?? ""}
                                    list={viTriOptions.length > 0 ? "kho-vitri-transfer" : undefined}
                                    onChange={(e) =>
                                      setViTriEdit((m) => ({ ...m, [l.id]: e.target.value }))
                                    }
                                    placeholder="kệ / ô…"
                                  />
                                ) : (
                                  l.vi_tri ?? "—"
                                )}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                      {v && v.lines.length > 0 && (
                        <tfoot>
                          <tr style={{ fontWeight: 600 }}>
                            <td style={{ textAlign: "right" }}>Tổng cộng ({v.lines.length} dòng):</td>
                            <td className="kho-num">
                              {fmtQty(v.lines.reduce((s, l) => s + (l.so_luong ?? 0), 0))}
                            </td>
                            {canViewCost && <td className="kho-num">—</td>}
                            {canViewCost && (
                              <td className="kho-num">
                                {money(v.lines.reduce((s, l) => s + (l.thanh_tien ?? 0), 0))}
                              </td>
                            )}
                            <td colSpan={2}></td>
                          </tr>
                        </tfoot>
                      )}
                    </table>
                  </div>
                </section>
              </>
            )}
          </div>

          <footer className="rc-drawer__foot">
            {canAct && (
              <Button variant="accent" loading={busy} onClick={() => setAskPost(true)}>
                Ghi sổ
              </Button>
            )}
            {canAct && (
              <button
                type="button"
                className="btn btn--danger"
                onClick={() => {
                  setCancelReason("");
                  setAskCancel(true);
                }}
              >
                Hủy
              </button>
            )}
            {/* In được ở MỌI trạng thái (kể cả Chờ ghi sổ / Hoàn tất / Đã hủy) — bản giấy làm chứng
                từ đi đường. Cần phiếu đích (`v`) đã tải để có dòng theo lô. */}
            {v && (
              <button type="button" className="btn btn--secondary" onClick={doPrint}>
                In phiếu
              </button>
            )}
            <button type="button" className="btn btn--secondary" onClick={onClose}>
              Đóng
            </button>
          </footer>
        </aside>
      </div>

      <ConfirmDialog
        open={askPost}
        title="Ghi sổ phiếu điều chuyển?"
        message="Tồn kho nguồn sẽ TRỪ và kho đích sẽ CỘNG cùng lúc — phiếu không sửa được nữa."
        confirmLabel="Ghi sổ"
        busy={busy}
        onCancel={() => setAskPost(false)}
        onConfirm={ghiSo}
      />

      <ConfirmDialog
        open={askCancel}
        title="Hủy phiếu điều chuyển này?"
        message="Cả phiếu điều chuyển sẽ bị hủy kèm lý do. Chỉ hủy được khi CHƯA ghi sổ."
        confirmLabel="Hủy phiếu"
        cancelLabel="Giữ lại"
        danger
        busy={busy}
        confirmDisabled={!cancelReason.trim()}
        onCancel={() => setAskCancel(false)}
        onConfirm={huy}
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
            placeholder="Vì sao hủy điều chuyển này? (bắt buộc)"
            autoFocus
          />
        </label>
      </ConfirmDialog>
    </>
  );
}

// ── DRAWER: chi tiết yêu cầu (góc nhìn KHO) ──────────────────────────────────

export function InboxRequestDrawer({
  token,
  khoId,
  requestId,
  canCreate,
  canViewStock,
  canViewCost,
  onClose,
  onCreateVoucher,
  onOpenVoucher,
  onChanged,
}: {
  token: string;
  khoId: number | null;
  requestId: number;
  canCreate: boolean;
  canViewStock: boolean;
  /** Kế toán (view_cost) xem ĐƠN GIÁ + THÀNH TIỀN của dòng yêu cầu; không quyền thì cột biến mất. */
  canViewCost: boolean;
  onClose: () => void;
  onCreateVoucher: (r: StockRequest) => void;
  /** Mở phiếu ĐÃ lập từ yêu cầu này (kể cả đã ghi sổ) — cha có sẵn VoucherDrawer. Không truyền
   *  (vd popup chỉ-đọc) → ẩn khối "Phiếu đã cấp". */
  onOpenVoucher?: (voucherId: number) => void;
  /** Gọi khi yêu cầu đổi trạng thái (kho hủy) để cha refetch list ngay. */
  onChanged?: () => void;
}) {
  // Nhãn ĐVT phải là TÊN có dấu lấy từ danh mục ("bản kẽm"), KHÔNG phải mã lưu trong
  // `stock_request_lines.dvt` ("kem") — mã vẫn giữ nguyên khi gửi lên server để quy đổi.
  useNapTenDonVi();
  const [req, setReq] = useState<StockRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Phiếu đã lập từ yêu cầu này (chờ ghi sổ / đã ghi sổ) — xem lại kể cả khi yêu cầu đã Hoàn tất.
  const [vouchers, setVouchers] = useState<StockVoucher[]>([]);
  // Kho HỦY yêu cầu (quyết không cấp) — kèm lý do bắt buộc.
  const [askCancel, setAskCancel] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    setLoading(true);
    api.kho.deNghi
      .get(token, requestId, khoId)
      .then((r) => {
        setReq(r);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được yêu cầu."))
      .finally(() => setLoading(false));
    api.kho.phieu
      .list(token, { request_id: requestId, size: 50 })
      .then((p) => setVouchers(p.items))
      .catch(() => {});
  }, [token, requestId, khoId]);

  useEffect(reload, [reload]);

  const canFulfill = canCreate && req != null && FULFILLABLE.includes(req.trang_thai);

  const reqLines = req?.lines ?? [];
  const totalSKU = reqLines.length;
  const totalDeNghi = reqLines.reduce((acc, l) => acc + (Number(l.sl_de_nghi) || 0), 0);
  const totalDuyet = reqLines.reduce((acc, l) => acc + (Number(l.sl_duyet) || 0), 0);
  const percentDone = totalDeNghi > 0 ? Math.min(100, Math.round((totalDuyet / totalDeNghi) * 100)) : 0;

  const showStepper = req && req.trang_thai !== "cancelled" && req.trang_thai !== "rejected";
  const stepperSteps = [
    {
      label: "Yêu cầu tạo",
      sub: req?.nguoi_tao_ten ? `${req.nguoi_tao_ten}` : "Đã tạo",
      done: true,
      active: false,
    },
    {
      label: "Lập phiếu kho",
      sub: vouchers.length > 0 ? `${vouchers.length} phiếu kho` : "Chờ lập phiếu",
      done: req?.trang_thai === "done" || vouchers.length > 0,
      active: ["approved", "preparing", "partial"].includes(req?.trang_thai ?? "") && vouchers.length === 0,
    },
    {
      label: "Hoàn tất",
      sub: req?.trang_thai === "done" ? "Hoàn thành" : "Đang xử lý",
      done: req?.trang_thai === "done",
      active: false,
    },
  ];

  return (
    <>
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer rc-drawer--wide" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">
              {req?.dieu_chuyen
                ? "YÊU CẦU ĐIỀU CHUYỂN"
                : req?.loai === "NHAP"
                  ? "YÊU CẦU NHẬP"
                  : "YÊU CẦU XUẤT"}
            </div>
            <h2 className="rc-drawer__title">{req?.ma ?? "Đang tải…"}</h2>
          </div>
          <div className="kho-headside">
            {req && <RequestStatusBadge status={req.trang_thai} />}
            <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
              <Icon name="x" size={16} />
            </button>
          </div>
        </header>

        {showStepper && (
          <div className="kho-stepper">
            {stepperSteps.map((s, idx) => {
              const cls = s.done ? "done" : s.active ? "active" : "pending";
              return (
                <div key={idx} className={`kho-stepper__step kho-stepper__step--${cls}`}>
                  <div className="kho-stepper__dot">
                    {s.done ? <Icon name="check" size={13} /> : idx + 1}
                  </div>
                  <div className="kho-stepper__content">
                    <span className="kho-stepper__label">{s.label}</span>
                    <span className="kho-stepper__sub">{s.sub}</span>
                  </div>
                  {idx < stepperSteps.length - 1 && <div className="kho-stepper__line" />}
                </div>
              );
            })}
          </div>
        )}

        {req && (
          <div className="kho-kpi-wrapper">
            <div className="kho-kpi-bar">
              <div className="kho-kpi-pill">
                Mặt hàng: <strong>{totalSKU} loại</strong>
              </div>
              <div className="kho-kpi-pill">
                Tổng YC: <strong>{fmtQty(totalDeNghi)}</strong>
              </div>
              <div className={`kho-kpi-pill ${percentDone >= 100 ? "kho-kpi-pill--moss" : ""}`}>
                Đã duyệt/cấp: <strong>{fmtQty(totalDuyet)}</strong>
                {totalDeNghi > 0 && <span style={{ opacity: 0.85 }}>({percentDone}%)</span>}
              </div>
            </div>
            {totalDeNghi > 0 && (
              <div className="kho-kpi-progress-track">
                <div
                  className="kho-kpi-progress-fill"
                  style={{ width: `${percentDone}%` }}
                />
              </div>
            )}
          </div>
        )}

        {req && (
          <div className="kho-meta">
            <strong>{req.nguoi_tao_ten ?? "—"}</strong>
            {req.bo_phan_ten ? ` (${req.bo_phan_ten})` : ""} · {fmtDate(req.created_at)}
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
                <h3 className="rc-sec__title">Thông tin yêu cầu</h3>
                <div className="kho-info-grid">
                  <div className="kho-info-item">
                    {/* Ưu tiên GIỜ cần thật (`can_luc`, từ đề nghị sản xuất) như cột danh sách — trả field
                        về mà drawer vẫn chỉ hiện ngày trơn thì mất luôn thông tin giờ vừa thấy ở danh
                        sách khi bấm mở chi tiết (task-8-review.md Minor 6). */}
                    <span className="kho-info-item__label">{req.can_luc ? "Cần lúc" : "Ngày cần"}</span>
                    <div className="kho-info-item__val">
                      {req.can_luc
                        ? fmtDateTime(req.can_luc)
                        : req.ngay_can
                          ? fmtDateISO(req.ngay_can)
                          : "—"}
                    </div>
                  </div>
                  <div className="kho-info-item">
                    <span className="kho-info-item__label">Người đề nghị</span>
                    <div className="kho-info-item__val">
                      <strong>{req.nguoi_tao_ten ?? "—"}</strong>
                      {req.bo_phan_ten ? ` (${req.bo_phan_ten})` : ""}
                    </div>
                  </div>
                  {req.dieu_chuyen && (
                    <div className="kho-info-item">
                      <span className="kho-info-item__label">Điều chuyển</span>
                      <div className="kho-info-item__val">
                        Từ <strong>{req.kho_nguon_ten ?? "—"}</strong> → <strong>{req.kho_ten ?? "Kho đích"}</strong>
                      </div>
                    </div>
                  )}
                </div>
                {req.ghi_chu && (
                  <div className="rc-field rc-field--full" style={{ marginTop: 8 }}>
                    <span className="rc-field__label">Ghi chú người tạo</span>
                    <div className="kho-val-card">{req.ghi_chu}</div>
                  </div>
                )}
              </section>

              <section className="rc-sec">
                <h3 className="rc-sec__title">Dòng vật tư</h3>
                <div className="kho-lines__wrap kho-lines-card">
                  <table className="kho-lines">
                    <thead>
                      <tr>
                        <th style={{ minWidth: 160 }}>Vật tư</th>
                        <th style={{ width: 60, textAlign: "center" }}>ĐVT</th>
                        <th className="kho-num" style={{ width: 100 }}>Yêu cầu</th>
                        {/* Cột Tồn khả dụng có chiều rộng 140px chuẩn, không bao giờ bị xén */}
                        {canViewStock && <th className="kho-num" style={{ width: 140 }}>Tồn khả dụng</th>}
                        {canViewCost && <th className="kho-num" style={{ width: 100 }}>Đơn giá</th>}
                        {canViewCost && <th className="kho-num" style={{ width: 120 }}>Thành tiền</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {req.lines.map((l) => {
                        const dvtYc = tenDonVi(l.dvt) ?? l.dvt;   // đơn vị người yêu cầu (Yêu cầu)
                        const dvtGoc = tenDonVi(l.don_vi_goc ?? l.dvt) ?? l.don_vi_goc ?? l.dvt; // đơn vị gốc lưu kho (Tồn)
                        // `ton_kha_dung` ở ĐƠN VỊ GỐC (Σ sl_con_lai lô), còn `sl_con_lai` (dòng yêu cầu)
                        // ở đơn vị YÊU CẦU → quy về gốc rồi mới so thiếu/đủ, không thì trừ chéo đơn vị
                        // (70 tờ − 1 ram). DÙNG `sl_con_lai`, KHÔNG dùng `sl_duyet`: mục tiêu còn phải
                        // cấp sau khi kho CHỐT (điều chỉnh xuất) là `coalesce(sl_chot_thuc_xuat,
                        // sl_duyet) - sl_da_ung` kẹp ≥ 0 — MỘT đường tính duy nhất ở
                        // `StockRequestService.con_lai` (backend/app/services/stock_request_service.py:610),
                        // trả sẵn qua field này. Xin 100 · xuất 100 · điều chỉnh còn 70 ⇒ `sl_con_lai` =
                        // 0 ⇒ hết thiếu, không còn "Thiếu N" đá nhau với badge xanh "Hoàn tất" cạnh nó
                        // (task-8-review.md Important 3).
                        const heSoVeGoc = l.sl_quy_doi && l.sl_de_nghi ? l.sl_quy_doi / l.sl_de_nghi : 1;
                        const shortage = (l.sl_con_lai || 0) * heSoVeGoc - (l.ton_kha_dung || 0);
                        const isShort = l.sl_con_lai > 0 && l.ton_kha_dung != null && shortage > 1e-6;
                        return (
                          <tr key={l.id}>
                            <td>
                              <div className="kho-lineimg">
                                {l.hang_anh && (
                                  <img
                                    className="kho-lineimg__thumb"
                                    src={assetUrl(l.hang_anh) ?? undefined}
                                    alt=""
                                  />
                                )}
                                <div className="kho-lineimg__txt">
                                  <div
                                    className="kho-lines__name kho-name-clamp"
                                    title={l.hang_ten ?? undefined}
                                  >
                                    {l.hang_ten ?? "—"}
                                  </div>
                                  <div className="kho-lines__code">{l.hang_ma ?? ""}</div>
                                </div>
                              </div>
                            </td>
                            <td className="kho-lines__code" style={{ textAlign: "center" }}>
                              {tenDonVi(l.dvt) ?? l.dvt}
                            </td>
                            <td className="kho-num">
                              {fmtQty(l.sl_de_nghi)} <span className="kho-alloc__unit">{dvtYc}</span>
                              {/* Kho đã CHỐT thực xuất (điều chỉnh phiếu xuất) → hiện "thực xuất N / yêu
                                  cầu M" + Hoàn tất, KHÔNG hiện "còn thiếu" (kho không xử lý lý do lệch kế
                                  hoạch — task-8-ruling-man-kho). Mẫu số `sl_de_nghi` khớp con số ngay
                                  trên cùng ô (cột "Yêu cầu") — nhưng nếu người duyệt đã hạ số duyệt khác
                                  `sl_de_nghi` thì đó chưa từng là mục tiêu thật, nên chua thêm "(duyệt N)"
                                  (task-8-review.md Minor 5). */}
                              {l.sl_chot_thuc_xuat != null && (
                                <div>
                                  <span
                                    className="kho-line-badge kho-line-badge--moss"
                                    style={{ fontSize: 10, marginTop: 2 }}
                                  >
                                    Thực xuất {fmtQty(l.sl_chot_thuc_xuat)}/{fmtQty(l.sl_de_nghi)} {dvtYc}
                                    {l.sl_duyet !== l.sl_de_nghi ? ` (duyệt ${fmtQty(l.sl_duyet)})` : ""}
                                    {" "}· Hoàn tất
                                  </span>
                                </div>
                              )}
                            </td>
                            {canViewStock && (
                              <td className="kho-num">
                                <div style={{ fontFamily: "var(--ff-num)", fontWeight: "var(--fw-bold)" }}>
                                  {fmtQty(l.ton_kha_dung ?? 0)} <span className="kho-alloc__unit">{dvtGoc}</span>
                                </div>
                                {l.ton_kha_dung != null && (
                                  isShort ? (
                                    <span className="kho-priority-badge kho-priority-badge--critical" style={{ fontSize: 10, marginTop: 2 }}>
                                      Thiếu {fmtQty(shortage)} {dvtGoc}
                                    </span>
                                  ) : (
                                    <span className="kho-line-badge kho-line-badge--muted" style={{ fontSize: 10, marginTop: 2 }}>
                                      Đủ tồn
                                    </span>
                                  )
                                )}
                              </td>
                            )}
                            {canViewCost && (
                              <td className="kho-num">
                                {l.don_gia != null
                                  ? `${l.don_gia.toLocaleString("vi-VN")} đ`
                                  : <span className="rc__muted">—</span>}
                              </td>
                            )}
                            {canViewCost && (
                              <td className="kho-num">
                                {l.don_gia != null
                                  ? money(Math.round(l.don_gia * l.sl_de_nghi))
                                  : <span className="rc__muted">—</span>}
                              </td>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>

              {vouchers.length > 0 && onOpenVoucher && (
                <section className="rc-sec">
                  <h3 className="rc-sec__title">Phiếu kho đã cấp</h3>
                  <div className="kho-vlinks">
                    {vouchers.map((v) => (
                      <button
                        key={v.id}
                        type="button"
                        className="kho-vlink"
                        onClick={() => onOpenVoucher(v.id)}
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
          {/* Kho đi thẳng "Đã duyệt → Lập phiếu"; phiếu tự chuyển yêu cầu sang "đang chuẩn bị"
              (voucher.create → mark_in_progress). Đã bỏ bước Tiếp nhận / Bắt đầu chuẩn bị. */}
          {canFulfill && req && (
            <Button variant="accent" onClick={() => onCreateVoucher(req)}>
              {req.open_voucher_id != null ? "Xem phiếu" : "Lập phiếu"}
            </Button>
          )}
          {/* Kho quyết KHÔNG cấp → hủy yêu cầu kèm lý do (gate `create` như backend). Ẩn khi đã có
              phiếu đang mở (lúc đó xử lý ở phiếu), tránh hủy chồng lên phiếu. */}
          {canFulfill && req && req.open_voucher_id == null && (
            <button type="button" className="btn btn--ghost" onClick={() => setAskCancel(true)}>
              Hủy yêu cầu
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
        title="Hủy yêu cầu này?"
        message="Yêu cầu sẽ chuyển sang 'Đã hủy' kèm lý do và KHÔNG cấp nữa. Người yêu cầu sẽ thấy lý do."
        confirmLabel="Hủy yêu cầu"
        cancelLabel="Giữ lại"
        danger
        busy={busy}
        confirmDisabled={!cancelReason.trim()}
        onCancel={() => setAskCancel(false)}
        onConfirm={() => {
          const ly = cancelReason.trim();
          if (!ly) return;
          setBusy(true);
          api.kho.deNghi
            .cancelByKho(token, requestId, ly)
            .then(() => {
              setAskCancel(false);
              setCancelReason("");
              onChanged?.();
              onClose();
            })
            .catch((e) => setError(e instanceof ApiError ? e.message : "Không hủy được yêu cầu."))
            .finally(() => setBusy(false));
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
            placeholder="Vì sao kho không cấp yêu cầu này? (bắt buộc)"
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

// ── DRAWER: LẬP PHIẾU (khối .kho-alloc theo từng dòng yêu cầu) ───────────────

interface LotPick {
  lot_id: number;
  ma_lo: string;
  /** Mã phiếu NHẬP đã đưa lô vào kho — hiển thị THAY mã lô kỹ thuật. Null = tồn đầu kỳ. */
  voucher_ma: string | null;
  ngay_nhap: string;
  hsd: string | null;
  vi_tri: string | null;
  /** Tồn còn lại CỦA LÔ. */
  sl_con_lai: number;
  so_luong: number;
  don_gia_nhap: number | null;
}

interface AllocBlock {
  line: StockRequestLine;
  // Mặt hàng KẾ THỪA từ dòng yêu cầu — kho không đổi được, và không còn khối "hàng mới"
  // (siết 2026-08-08: mọi thứ nhập kho phải có sẵn trong danh mục gốc).
  matLabel: string;
  matCode: string | null;
  /** Ảnh minh hoạ mặt hàng ĐANG LƯU (từ danh mục). null = chưa có. */
  anh: string | null;
  /** Ảnh MỚI đang chờ (client-side) — chỉ tải lên danh mục khi LẬP PHIẾU. null = không đổi. */
  anhFile: File | null;
  /** Đánh dấu GỠ ảnh cũ khi lập phiếu (chỉ có tác dụng khi không kèm `anhFile`). */
  anhRemove: boolean;
  /** Hệ số về đơn vị gốc — để đổi số kho gõ (theo `line.dvt`) sang số tra lô/gợi ý phân bổ. */
  heSoVeGoc: number;
  cap: number;
  lots: LotPick[];
  thieu: number;
  donGia: string;
  /** Lý do cấp/nhập THIẾU (khi SL < còn phải cấp) — bắt buộc; hiện ở "Kho phản hồi" yêu cầu. */
  lyDo: string;
  /** Ghi chú riêng cho mặt hàng (dòng) trên phiếu. */
  ghiChu: string;
  /** Phiếu NHẬP: vị trí cất lô (kệ/ô) — tuỳ chọn; ghi sổ chép sang lô. */
  viTri: string;
  /** Phiếu NHẬP: HẠN SỬ DỤNG của đợt nhập này (tuỳ chọn, ISO). Một đợt = 1 lô = 1 hạn; nhiều hạn
   *  của cùng vật tư là do NHIỀU đợt nhập, tồn/báo cáo tự gom. */
  hsd: string;
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
    voucher_ma: full?.voucher_ma ?? null,
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
  onClose,
  onSaved,
}: {
  token: string;
  request: StockRequest;
  khoList: KhoOption[];
  initialKhoId: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  useNapTenDonVi();
  const isNhap = request.loai === "NHAP";
  // NGƯỜI LẬP PHIẾU LUÔN NHẬP + THẤY ĐƠN GIÁ (bỏ gate "xem giá vốn" ở bước lập) — theo yêu cầu:
  // ai tạo phiếu đều set giá; giá do người lập điền, không chờ Kế toán bổ sung nữa.
  const canViewCost = true;
  // Kho do BƯỚC LẬP PHIẾU quyết định (yêu cầu không còn chọn kho). Mặc định = kho đang xem ở
  // toolbar; thủ kho đổi được ngay tại đây. Đổi kho = nạp lại toàn bộ lô (dep của effect dưới).
  const [khoId, setKhoId] = useState<number>(request.kho_id ?? initialKhoId);
  const [ngay, setNgay] = useState(todayISO());
  // Người giao/nhận hàng mặc định = NGƯỜI YÊU CẦU (hàng về/ra theo đúng người xin); thủ kho sửa được.
  const [nguoiGiaoNhan, setNguoiGiaoNhan] = useState(request.nguoi_tao_ten ?? "");
  // ĐIỀU CHUYỂN: ghi chú phiếu nhập đích LẤY SẴN từ ghi chú điều chuyển (đã gắn vào yêu cầu); sửa được.
  const [ghiChu, setGhiChu] = useState(request.dieu_chuyen ? (request.ghi_chu ?? "") : "");
  // Chứng từ (ảnh/PDF) chọn SẴN lúc tạo — giữ client-side, upload sau khi có voucher_id.
  const [files, setFiles] = useState<File[]>([]);
  const [blocks, setBlocks] = useState<AllocBlock[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [askDiscard, setAskDiscard] = useState(false);
  const [askPost, setAskPost] = useState(false);
  // Gợi ý VỊ TRÍ cất (kệ/ô) đã khai của kho ĐÍCH — chỉ phiếu NHẬP mới ghi vị trí lô. Chỉ để GỢI Ý
  // (datalist), thủ kho vẫn gõ tự do được nếu vị trí chưa khai trong danh mục.
  const [viTriOptions, setViTriOptions] = useState<string[]>([]);
  useEffect(() => {
    if (!isNhap || khoId == null) { setViTriOptions([]); return; }
    let alive = true;
    api.kho.viTri.list(token, khoId)
      .then((r) => { if (alive) setViTriOptions(r.items.map((v) => v.ma)); })
      .catch(() => { if (alive) setViTriOptions([]); });
    return () => { alive = false; };
  }, [token, khoId, isNhap]);

  // Tự chọn "Kho (xuất từ)" = kho có NHIỀU hàng nhất (ưu tiên mặt hàng đầu tiên) NGAY khi mở phiếu
  // XUẤT — thay vì bê kho đang xem ở toolbar (dễ trỏ vào kho rỗng). Chỉ chạy MỘT LẦN, cho MỌI phiếu
  // XUẤT thường; chỉ chừa ĐIỀU CHUYỂN (kho nguồn đã bị khoá). Sau đó thủ kho đổi tay tùy ý.
  // KHÔNG dùng cờ `cancelled`: StrictMode (dev) chạy effect 2 lần — cleanup lần 1 sẽ set cancelled
  // = true trong khi ref đã chặn lần 2 fetch → kết quả bị VỨT. Ref one-shot đủ đảm bảo gọi 1 lần;
  // setKhoId idempotent, có unmount sớm cũng chỉ là no-op (React 18 không cảnh báo).
  const daGoiYKho = useRef(false);
  useEffect(() => {
    if (daGoiYKho.current || isNhap || request.dieu_chuyen) return;
    daGoiYKho.current = true;
    api.kho.deNghi
      .goiYKho(token, request.id)
      .then((r) => {
        if (r.kho_id == null || !khoList.some((w) => w.id === r.kho_id)) return;
        setKhoId(r.kho_id);
      })
      .catch(() => {});
  }, [token, request, isNhap, khoList]);

  // Gợi ý lô chạy NGAY khi mở drawer, không chờ bấm nút: thủ kho mở phiếu ra là để lấy hàng,
  // bắt bấm thêm một nút "gợi ý" chỉ để có đúng cái FEFO mặc định là thao tác thừa.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const base: AllocBlock[] = request.lines.map((l) => ({
      line: l,
      matLabel: l.hang_ten ?? "—",
      matCode: l.hang_ma,
      anh: l.hang_anh,
      anhFile: null,
      anhRemove: false,
      // Server đã quy sẵn cho SL yêu cầu — suy ngược ra hệ số, khỏi gọi thêm API.
      heSoVeGoc: l.sl_quy_doi && l.sl_de_nghi ? l.sl_quy_doi / l.sl_de_nghi : 1,
      cap: l.sl_con_lai,
      lots: [],
      thieu: 0,
      // Đơn giá NHẬP LẤY TỪ YÊU CẦU (người yêu cầu khai) — kho chỉ đọc, không sửa.
      donGia: l.don_gia != null ? String(l.don_gia) : "",
      lyDo: "",
      ghiChu: "",
      viTri: "",
      hsd: "",
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
    // XUẤT: tra lô theo ĐƠN VỊ GỐC — lô lưu theo đơn vị đó, gửi số theo đơn vị yêu cầu là lệch
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
        for (const r of results) {
          const b = base.find((x) => x.line.id === r.l.id);
          if (b && r.alloc) {
            // Tự lấy lô theo FIFO/FEFO (goiYLo) — chỉ đọc, người dùng không chọn/sửa lô.
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

  // XUẤT tự lấy lô theo FIFO/FEFO (goiYLo) làm MẶC ĐỊNH khi mở, nhưng kho SỬA được "SL lấy" từng lô
  // nếu cần (cap theo tồn của lô + số được duyệt). Không có "+ Thêm lô"/"✕" — chỉ sửa số là đủ.
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
      // Mốc duyệt `sl_con_lai` theo ĐƠN VỊ YÊU CẦU, còn số lô (`others`/`next`) theo ĐƠN VỊ GỐC —
      // phải quy mốc về gốc rồi mới so, không thì vật tư có quy đổi (vd xin ram, lô lưu tờ) bị ép
      // "SL lấy" về 0 khi sửa tay (others gốc đã vượt sl_con_lai yêu cầu).
      const capGoc = b.line.sl_con_lai * (b.heSoVeGoc || 1);
      if (others + next > capGoc) {
        next = Math.max(0, capGoc - others);
        warn = `Chỉ được cấp ${fmtQty(capGoc)} theo duyệt — muốn cấp thêm phải tạo yêu cầu mới.`;
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

  // GỠ 2026-08-08: `resolvePick` + `resetToNew` — kho gắn/tạo mã cho hàng gõ tay. Mặt hàng nay
  // kế thừa từ dòng yêu cầu và đã có sẵn trong danh mục gốc, không còn gì để gắn.

  const payload = useMemo<StockVoucherLineInput[]>(() => {
    const out: StockVoucherLineInput[] = [];
    for (const b of blocks) {
      if (b.line.sl_con_lai <= 0) continue;
      const ghi = b.ghiChu.trim() || null;
      const ly = b.lyDo.trim() || null; // lý do cấp thiếu (backend bắt buộc khi SL < còn phải cấp)
      if (isNhap) {
        if (b.cap <= 0) continue;
        // SL + đơn giá gửi theo ĐƠN VỊ CỦA DÒNG YÊU CẦU; server tự quy về đơn vị gốc và chốt hệ
        // số vào `sl_goc`. FE KHÔNG tự nhân hệ số nữa — hai nơi cùng quy đổi là hai nơi lệch nhau.
        // Một đợt nhập = MỘT lô = MỘT hạn (tuỳ chọn). Không hạn → lô không hạn.
        out.push({
          request_line_id: b.line.id,
          so_luong: b.cap,
          don_gia: canViewCost ? Math.round(Number(b.donGia) || 0) : undefined,
          vi_tri: b.viTri.trim() || undefined,
          hsd: b.hsd || undefined,
          ly_do: ly,
          ghi_chu: ghi,
        });
      } else {
        // XUẤT: tách theo lô. `lot.so_luong` ở ĐƠN VỊ GỐC (lô lưu theo đơn vị đó) → đổi ngược về
        // đơn vị dòng yêu cầu trước khi gửi, vì server so `so_luong` với `sl_duyet`.
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

  // Kiểm tra hợp lệ dùng CHUNG cho nút "Tạo & Ghi sổ" (báo NGAY khi bấm, không để lọt vào popup
  // rồi mới báo) và cho submit (chốt chặn). Trả câu lỗi ĐẦU TIÊN, null nếu hợp lệ.
  function firstError(): string | null {
    if (!payload.length)
      return "Chưa có dòng nào để cấp. Nhập số lượng hoặc chọn lô trước khi lưu.";
    for (const b of blocks) {
      if (b.line.sl_con_lai <= 0) continue;
      // Cả hai vế quy về ĐƠN VỊ DÒNG YÊU CẦU để so với `sl_con_lai` — lô đếm theo đơn vị gốc.
      const capped = isNhap
        ? b.cap
        : b.lots.reduce((s, x) => s + x.so_luong, 0) / (b.heSoVeGoc || 1);
      if (capped > b.line.sl_con_lai + 1e-9)
        return "Ứng vượt số đã duyệt. Muốn cấp thêm thì phải tạo yêu cầu mới.";
      // Cấp/nhập ÍT HƠN còn phải cấp → bắt buộc LÝ DO (kho phản hồi).
      if (capped > 0 && capped < b.line.sl_con_lai - 1e-9 && !b.lyDo.trim())
        return `"${b.matLabel}" cấp ít hơn số còn phải cấp — nhập LÝ DO (vd NCC giao thiếu).`;
    }
    return null;
  }

  async function submit(post: boolean) {
    const err = firstError();
    if (err) {
      setError(err);
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
      // Chứng từ đã chọn cần voucher_id → upload NGAY SAU khi tạo phiếu (trước khi ghi sổ).
      for (const f of files) {
        await api.kho.phieu.uploadAttachment(token, v.id, f);
      }
      // Ảnh mặt hàng (cả nhập lẫn xuất): CHỈ lưu vào danh mục khi ĐÃ tạo phiếu (thêm ảnh rồi thoát
      // giữa chừng thì không lưu). Best-effort — ảnh minh hoạ lỗi KHÔNG chặn/roll back việc tạo phiếu.
      for (const b of blocks) {
        try {
          if (b.anhFile)
            await api.matHang.uploadAnh(token, b.line.hang_loai, b.line.hang_id, b.anhFile);
          else if (b.anhRemove)
            await api.matHang.xoaAnh(token, b.line.hang_loai, b.line.hang_id);
        } catch {
          /* ảnh minh hoạ lỗi — bỏ qua, không chặn tạo phiếu */
        }
      }
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
        <aside className="rc-drawer rc-drawer--wide kho-voucher-drawer" onClick={(e) => e.stopPropagation()}>
          <header className="rc-drawer__head">
            <div>
              <div className="rc-drawer__kicker">
                {isNhap ? "PHIẾU NHẬP KHO" : "PHIẾU XUẤT KHO"}
              </div>
              <h2 className="rc-drawer__title">Ứng theo {request.ma}</h2>
            </div>
            <div className="kho-headside">
              {/* Không badge "Chờ ghi sổ" nữa: tạo = ghi sổ ngay (create & post gộp 1 quyền). */}
              <button
                type="button"
                className="rc-drawer__x"
                onClick={requestClose}
                aria-label="Đóng"
              >
                <Icon name="x" size={16} />
              </button>
            </div>
          </header>

          <div className="rc-drawer__body">
            {error && (
              <div className="banner banner--error" role="alert">
                <span>{error}</span>
              </div>
            )}

            {request.dieu_chuyen && isNhap && (
              // Phiếu NHẬP đích của một điều chuyển: đơn giá đã KHOÁ theo giá vốn chốt ở kho nguồn
              // (không gõ tay). Nêu rõ để người lập không thắc mắc vì sao đơn giá không sửa được.
              <div className="banner banner--info">
                <span>
                  Phiếu điều chuyển
                  {request.kho_nguon_ten ? ` từ kho ${request.kho_nguon_ten}` : ""} — đơn giá KHOÁ
                  theo giá vốn nguồn. <b>Ghi sổ phiếu này sẽ TRỪ kho nguồn và CỘNG kho đích cùng lúc.</b>
                </span>
              </div>
            )}

            <section className="rc-sec">
              <h3 className="rc-sec__title">Thông tin phiếu</h3>
              
              {/* Meta Summary Banner phẳng 3 cột hairline (Không viền dày bên trái) */}
              <div className="kho-meta-banner">
                <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                  <div>
                    <span className="kho-microlabel">Theo yêu cầu</span>
                    <span className="kho-meta-banner__badge">{request.ma}</span>
                  </div>
                  <div className="kho-vdivider" />
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div className="kho-user-avatar kho-user-avatar--charcoal">
                      {(request.nguoi_tao_ten || "U").slice(0, 1).toUpperCase()}
                    </div>
                    <div>
                      <span className="kho-microlabel">Người tạo yêu cầu</span>
                      <div style={{ fontWeight: "var(--fw-medium)", color: "var(--ink)", fontSize: 13 }}>
                        {request.nguoi_tao_ten || "—"} {request.bo_phan_ten ? `(${request.bo_phan_ten})` : ""}
                      </div>
                    </div>
                  </div>
                </div>

                {canViewCost && (
                  <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                    <div className="kho-vdivider" />
                    <div className="kho-top-kpi-pill">
                      <span className="kho-top-kpi-pill__label">Tổng giá vốn ({payload.length} dòng)</span>
                      <span className="kho-top-kpi-pill__val">{money(giaVon)}</span>
                    </div>
                  </div>
                )}
              </div>

              <div className="rc-grid">
                {request.dieu_chuyen ? (
                  <>
                    <Readout label="Từ kho (nguồn)" value={request.kho_nguon_ten || "—"} />
                    <Readout
                      label="Đến kho (nhập về)"
                      value={
                        request.kho_ten || khoList.find((w) => w.id === khoId)?.ten || "—"
                      }
                    />
                  </>
                ) : (
                  <div className="rc-field">
                    <span className="rc-field__label">
                      Kho {isNhap ? "(nhập về)" : "(xuất từ)"} <em>*</em>
                    </span>
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
                )}
                <div className="rc-field">
                  <label className="rc-field__label" htmlFor="v-ngay">
                    {isNhap ? "Ngày nhập kho" : "Ngày xuất kho"}
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
                <div className="kho-lines__wrap kho-lines-card">
                  {/* Gợi ý vị trí cất (kệ/ô) đã khai của kho — 1 datalist dùng chung cho mọi ô Vị trí. */}
                  {isNhap && viTriOptions.length > 0 && (
                    <datalist id="kho-vitri-suggest">
                      {viTriOptions.map((v) => <option key={v} value={v} />)}
                    </datalist>
                  )}
                  {/* Bảng dòng cấp auto-fit chiều rộng Drawer, min-width 240px cho cột Vật tư chống ép chữ */}
                  <table className="kho-lines" style={{ width: "100%", tableLayout: "auto" }}>
                    <thead>
                      <tr>
                        <th className="kho-nhap__stt" style={{ width: 40, textAlign: "center" }}>#</th>
                        <th style={{ minWidth: 300 }}>Vật tư</th>
                        <th style={{ width: 60, textAlign: "center" }}>Ảnh</th>
                        <th style={{ width: 60, textAlign: "center" }}>ĐVT</th>
                        <th className="kho-num" style={{ width: 90 }}>SL YC</th>
                        <th className="kho-num" style={{ width: 90 }}>Tồn kho</th>
                        <th className="kho-num" style={{ width: 110 }}>{isNhap ? "SL Nhập" : "Cấp"}</th>
                        <th className="kho-num" style={{ width: 120 }}>{isNhap ? "Đơn giá" : "Đơn giá BQ"}</th>
                        <th className="kho-num" style={{ width: 130 }}>Thành tiền</th>
                        {isNhap && <th style={{ width: 140 }}>Vị trí</th>}
                        {isNhap && <th style={{ width: 140 }}>HSD</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {blocks.map((b, i) => (
                        <AllocRow
                          key={b.line.id}
                          idx={i + 1}
                          token={token}
                          khoId={khoId}
                          block={b}
                          isNhap={isNhap}
                          canViewCost={canViewCost}
                          viTriListId={isNhap && viTriOptions.length > 0 ? "kho-vitri-suggest" : undefined}
                          onCap={(v) => patch(b.line.id, (cur) => ({ ...cur, touched: true, cap: v }))}
                          onLyDo={(v) => patch(b.line.id, (cur) => ({ ...cur, lyDo: v }))}
                          onLotQty={(lotId, v) => setLotQty(b.line.id, lotId, v)}
                          onViTri={(v) => patch(b.line.id, (cur) => ({ ...cur, touched: true, viTri: v }))}
                          onHsd={(v) => patch(b.line.id, (cur) => ({ ...cur, touched: true, hsd: v }))}
                          onAnhPick={(file) =>
                            patch(b.line.id, (cur) => ({ ...cur, anhFile: file, anhRemove: false }))
                          }
                          onAnhClear={() =>
                            patch(b.line.id, (cur) =>
                              cur.anhFile
                                ? { ...cur, anhFile: null }
                                : { ...cur, anhRemove: true },
                            )
                          }
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            {/* Đính kèm chứng từ NGAY khi tạo: chọn file giữ client-side, upload sau khi có voucher_id. */}
            <section className="rc-sec">
              <h3 className="rc-sec__title">Chứng từ gốc / Hóa đơn</h3>
              {files.length === 0 ? (
                <p className="kho-hint">
                  Chưa chọn file. Đính kèm ảnh/PDF hóa đơn, phiếu giao… (tuỳ chọn) — tải lên khi tạo phiếu.
                </p>
              ) : (
                <ul className="kho-att">
                  {files.map((f, i) => (
                    <li key={i} className="kho-att__item">
                      <span className="kho-att__name">{f.name}</span>
                      <button
                        type="button"
                        className="rc-bands__del"
                        aria-label={`Bỏ ${f.name}`}
                        onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                      >
                        <Icon name="x" size={13} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <label className="btn btn--secondary kho-att__upload">
                + Thêm file (ảnh / PDF)
                <input
                  type="file"
                  accept="image/*,application/pdf"
                  multiple
                  hidden
                  onChange={(e) => {
                    const picked = Array.from(e.target.files ?? []);
                    if (picked.length) {
                      setDirty(true);
                      setFiles((prev) => [...prev, ...picked]);
                    }
                    e.target.value = "";
                  }}
                />
              </label>
            </section>
          </div>

          <footer className="rc-drawer__foot">
            <button type="button" className="btn btn--ghost" onClick={requestClose}>
              Đóng
            </button>
            {/* Create & post đã GỘP 1 quyền: lập phiếu = GHI SỔ NGAY. Xác nhận trước khi ghi vì
                phiếu không sửa được nữa. */}
            <Button
              variant="accent"
              disabled={busy}
              onClick={() => {
                // Báo NGAY khi bấm (ứng vượt / cấp thiếu chưa nêu lý do) — không mở popup rồi mới báo.
                const err = firstError();
                if (err) {
                  setError(err);
                  return;
                }
                setError(null);
                setAskPost(true);
              }}
            >
              Tạo &amp; Ghi sổ
            </Button>
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
        message={
          isNhap
            ? "Tồn kho sẽ cộng ngay và phiếu không sửa được nữa."
            : "Tồn kho sẽ trừ ngay và phiếu không sửa được nữa."
        }
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

function AllocRow({
  token,
  khoId,
  block,
  isNhap,
  canViewCost,
  viTriListId,
  idx,
  onCap,
  onLyDo,
  onLotQty,
  onViTri,
  onHsd,
  onAnhPick,
  onAnhClear,
}: {
  token: string;
  khoId: number;
  block: AllocBlock;
  isNhap: boolean;
  canViewCost: boolean;
  /** id của <datalist> gợi ý vị trí (kệ/ô) đã khai của kho; undefined = không gợi ý (vẫn gõ tự do). */
  viTriListId?: string;
  idx: number;
  onCap: (v: number) => void;
  onLyDo: (v: string) => void;
  onLotQty: (lotId: number, v: number) => void;
  onViTri: (v: string) => void;
  onHsd: (v: string) => void;
  /** Chọn/đổi ảnh mặt hàng (chỉ phiếu NHẬP) — GIỮ file client-side, chỉ lưu khi LẬP PHIẾU. */
  onAnhPick: (file: File) => void;
  /** Bỏ ảnh: có file đang chờ thì huỷ chọn; không thì đánh dấu gỡ ảnh cũ (áp khi lập phiếu). */
  onAnhClear: () => void;
}) {
  const l = block.line;
  // Ảnh mặt hàng — chỉ phiếu NHẬP. GIỮ file ở CLIENT, chỉ lưu vào danh mục KHI LẬP PHIẾU: thêm ảnh
  // rồi thoát mà chưa lập thì KHÔNG lưu (lần sau vào lại như mới). `block.anhFile` = ảnh mới đang chờ;
  // `block.anhRemove` = đánh dấu gỡ ảnh cũ. Preview lấy từ file chờ (objectURL) hoặc ảnh cũ.
  const [anhZoom, setAnhZoom] = useState(false);
  const preview = useMemo(
    () => (block.anhFile ? URL.createObjectURL(block.anhFile) : null),
    [block.anhFile],
  );
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );
  const shownAnh = preview ?? (!block.anhRemove && block.anh ? assetUrl(block.anh) : null);
  // Tồn hiện tại trong kho này (cả NHẬP lẫn XUẤT) — hiện thành CỘT riêng để biết đang thêm/rút khỏi đâu.
  const [tonInfo, setTonInfo] = useState<{ ton: number; gia: number | null } | null>(null);
  useEffect(() => {
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
  }, [l.hang_loai, l.hang_id, khoId, token]);

  const chosen = block.lots.reduce((s, x) => s + x.so_luong, 0);   // tổng đã lấy — ĐƠN VỊ GỐC (lô)
  const target = block.cap;                                         // mốc cần — ĐƠN VỊ YÊU CẦU
  // `chosen` (gốc) và `target` (yêu cầu) KHÁC đơn vị — quy mốc cần về GỐC để so cho khớp bảng lô.
  const targetGoc = target * (block.heSoVeGoc || 1);
  const matched = Math.abs(chosen - targetGoc) < 1e-6;
  // Cấp/nhập ÍT HƠN còn phải cấp → bắt buộc LÝ DO (kho phản hồi). Quy cả hai vế về ĐƠN VỊ DÒNG
  // YÊU CẦU (lô đếm theo đơn vị gốc) rồi mới so với `sl_con_lai`.
  const cappedTon = isNhap ? block.cap : chosen / (block.heSoVeGoc || 1);
  const isShort = l.sl_con_lai > 0 && cappedTon > 0 && cappedTon < l.sl_con_lai - 1e-9;
  const settled = l.sl_con_lai <= 0;
  // Nhãn đơn vị: SL YC theo đơn vị NGƯỜI YÊU CẦU (`l.dvt`, vd "tờ"); Tồn kho theo đơn vị GỐC lưu
  // kho (`l.don_vi_goc`, vd "ram") — HAI CỘT KHÁC ĐƠN VỊ nên hiện nhãn để khỏi lẫn (70 tờ vs 1 ram).
  const dvtYc = tenDonVi(l.dvt) ?? l.dvt;
  const dvtGoc = tenDonVi(l.don_vi_goc ?? l.dvt) ?? l.don_vi_goc ?? l.dvt;
  // Giá vốn dòng: XUẤT tính đích danh theo lô đã lấy (đơn giá BÌNH QUÂN + tổng tiền); NHẬP theo
  // đơn giá người yêu cầu khai. Đơn giá/tổng của XUẤT là giá vốn → chỉ hiện khi có quyền xem giá.
  const nhapGia = Number(block.donGia || 0);
  const lotCost = block.lots.reduce((s, x) => s + x.so_luong * (x.don_gia_nhap ?? 0), 0);
  const thanhTien = isNhap ? block.cap * nhapGia : lotCost;
  const donGiaBq = isNhap ? nhapGia : chosen > 0 ? lotCost / chosen : 0;

  const rowCls = settled ? "kho-alloc--done" : block.thieu > 0 ? "kho-alloc--short" : "";

  // Con số THẬT SỰ vào tồn — nhập "10 ram" mà lô ghi 419,25 kg thì phải nói ra ngay đây.
  const quyDoiHint =
    isNhap && block.heSoVeGoc !== 1 && block.cap > 0 && l.don_vi_goc ? (
      <p className="kho-hint">
        = {fmtQty(block.cap * block.heSoVeGoc)} {tenDonVi(l.don_vi_goc) ?? l.don_vi_goc} (lô lưu theo {tenDonVi(l.don_vi_goc) ?? l.don_vi_goc})
        {l.quy_doi_dien_giai ? ` · ${l.quy_doi_dien_giai}` : ""}
      </p>
    ) : null;
  // Cấp/nhập ÍT HƠN còn phải cấp → BẮT BUỘC nhập lý do; hiện ở "Kho phản hồi" của yêu cầu.
  const lyDoBox = isShort ? (
    <div className="kho-alloc__note kho-alloc__lydo">
      <label htmlFor={`ly-${l.id}`}>
        {isNhap ? "Lý do nhập thiếu" : "Lý do cấp thiếu"} <em>*</em>
      </label>
      <input
        id={`ly-${l.id}`}
        className={`rc-input${!block.lyDo.trim() ? " rc-input--warn" : ""}`}
        value={block.lyDo}
        onChange={(e) => onLyDo(e.target.value)}
        placeholder={`Vì sao chỉ ${isNhap ? "nhập" : "cấp"} ${fmtQty(cappedTon)}/${fmtQty(l.sl_con_lai)}? (vd NCC giao thiếu)`}
      />
    </div>
  ) : null;

  // XUẤT tự lấy lô theo FIFO (goiYLo) sẵn → GẬP bảng lô lại, bấm dòng vật tư mới xổ ra xem. Tự bung
  // khi có vấn đề cần chú ý (thiếu hàng / cấp thiếu phải nêu lý do) để không giấu mất việc bắt buộc.
  const [manualOpen, setManualOpen] = useState<boolean | null>(null);
  const open = manualOpen ?? (block.thieu > 0 || isShort);
  // Hàng CHI TIẾT (colspan) thứ 2: NHẬP = tồn + quy đổi + lý do; XUẤT = bảng lô (gập được) + tổng.
  const hasDetail = !settled && (isNhap ? !!(quyDoiHint || lyDoBox) : open);

  return (
    <>
      <tr
        className={`${rowCls}${!isNhap && !settled ? " kho-xuat__row" : ""}`}
        onClick={!isNhap && !settled ? () => setManualOpen(!open) : undefined}
      >
        <td className="kho-nhap__stt">{idx}</td>
        <td style={{ minWidth: 300 }}>
          <div className="kho-lines__name">
            {/* Caret: XUẤT bấm dòng để xổ/gập bảng lô đã tự lấy theo FIFO. */}
            {!isNhap && !settled && (
              <span aria-hidden style={{ color: "var(--ash)", marginRight: 6, fontSize: 11 }}>
                {open ? "▾" : "▸"}
              </span>
            )}
            {block.matLabel}
          </div>
          {block.matCode ? <div className="kho-lines__code">{block.matCode}</div> : null}
        </td>
        {/* Ảnh mặt hàng — NGAY cạnh cột Vật tư (cả nhập lẫn xuất). Chọn file = GIỮ client, lưu khi lập
            phiếu. `stopPropagation` để bấm nút ảnh KHÔNG kích hoạt xổ/gập bảng lô của dòng XUẤT. */}
        <td onClick={(e) => e.stopPropagation()}>
          <div className="kho-anh kho-anh--cell">
            {shownAnh && (
              <button
                type="button"
                className="kho-anh__thumb kho-anh__thumb--sm"
                onClick={() => setAnhZoom(true)}
                title="Bấm để phóng to"
              >
                <img src={shownAnh} alt={block.matLabel} />
              </button>
            )}
            {/* Đổi / Xóa nằm DƯỚI ảnh (kho-anh--cell xếp dọc), không chen ngang làm rộng cột. */}
            <div className="kho-anh__cellacts">
              <label className="rc__link-btn">
                {shownAnh ? "Đổi" : "＋ Ảnh"}
                <input
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) onAnhPick(f);
                    e.target.value = "";
                  }}
                />
              </label>
              {shownAnh && (
                <button
                  type="button"
                  className="rc__link-btn kho-anh__del"
                  onClick={() => {
                    onAnhClear();
                    setAnhZoom(false);
                  }}
                >
                  Xóa
                </button>
              )}
            </div>
          </div>
        </td>
        <td className="kho-lines__code">{tenDonVi(l.dvt) ?? l.dvt}</td>
        <td className="kho-num">
          {/* SL người yêu cầu xin (sl_de_nghi) — không phải phần còn lại. Đã đủ thì báo "Đã cấp đủ". */}
          {settled ? (
            <span className="badge-sem badge-sem--moss">Đã cấp đủ</span>
          ) : (
            <>
              <b>{fmtQty(l.sl_de_nghi)}</b> <span className="kho-alloc__unit">{dvtYc}</span>
            </>
          )}
        </td>
        <td className="kho-num">
          {/* Tồn thực tế trong kho này TRƯỚC khi phiếu ghi sổ — biết đang thêm/rút khỏi đâu. Tồn theo
              ĐƠN VỊ GỐC (lô lưu theo gốc) nên nhãn là `dvtGoc`, có thể KHÁC đơn vị SL YC. */}
          {tonInfo ? (
            <>
              <b>{fmtQty(tonInfo.ton)}</b> <span className="kho-alloc__unit">{dvtGoc}</span>
            </>
          ) : (
            <span className="kho-hint">…</span>
          )}
        </td>
        <td className="kho-num">
          {/* Dòng không muốn làm đợt này thì để số lượng 0 là tự bỏ qua — không cần ô tick riêng. */}
          {settled ? (
            "—"
          ) : isNhap ? (
            <DecimalInput
              id={`cap-${l.id}`}
              className="rc-input kho-num kho-nhap__sl"
              value={block.cap}
              onChange={(n) => onCap(n ?? 0)}
              aria-label="SL nhập"
            />
          ) : (
            // XUẤT: cột "Cấp" = SL THỰC CẤP đợt này = tổng SL LẤY các lô (quy về đơn vị dòng yêu cầu),
            // KHÔNG phải SL yêu cầu bên cạnh. Sửa số cấp bằng cách đổi "SL lấy" ở bảng lô bên dưới.
            <b className="kho-alloc__capfixed">{fmtQty(cappedTon)}</b>
          )}
        </td>
        <td className="kho-num">
          {/* Đơn giá: NHẬP = giá người yêu cầu khai (số nguyên). XUẤT = đơn giá BÌNH QUÂN gia quyền các
              lô — hiện tới 2 SỐ LẺ để SL × đơn giá sát Thành tiền nhất (làm tròn đồng sẽ lệch to khi
              SL lớn). Thành tiền vẫn là tổng giá vốn THỰC từng lô, không suy từ đơn giá này. */}
          {isNhap ? (
            block.donGia ? `${Number(block.donGia).toLocaleString("vi-VN")} đ` : "—"
          ) : canViewCost && chosen > 0 ? (
            <>
              <ApproxMark raw={donGiaBq} decimals={2} />
              {donGiaBq.toLocaleString("vi-VN", { maximumFractionDigits: 2 })} đ
            </>
          ) : (
            "—"
          )}
        </td>
        <td className="kho-num">
          {/* Thành tiền: NHẬP = SL nhập × đơn giá; XUẤT = tổng giá vốn các lô (chỉ khi có quyền giá).
              "≈" nhỏ phía trước khi số bị làm tròn (giá trị thật lẻ hơn); số tròn thì để nguyên. */}
          {settled ? (
            "—"
          ) : isNhap ? (
            block.donGia && block.cap ? (
              <>
                <ApproxMark raw={thanhTien} decimals={0} />
                {money(Math.round(thanhTien))}
              </>
            ) : (
              "—"
            )
          ) : canViewCost && chosen > 0 ? (
            <>
              <ApproxMark raw={thanhTien} decimals={0} />
              {money(Math.round(thanhTien))}
            </>
          ) : (
            "—"
          )}
        </td>
        {/* Vị trí cất lô (kệ/ô) — chỉ NHẬP; tuỳ chọn, ghi sổ chép sang lô. */}
        {isNhap && (
          <td>
            {settled ? (
              "—"
            ) : (
              <input
                className="rc-input kho-nhap__vitri"
                value={block.viTri}
                list={viTriListId}
                onChange={(e) => onViTri(e.target.value)}
                placeholder="kệ A / ô…"
                aria-label="Vị trí cất hàng"
              />
            )}
          </td>
        )}
        {/* Hạn sử dụng của ĐỢT nhập này — 1 lô = 1 hạn (tuỳ chọn). Đợt sau nhập thì set hạn của đợt đó. */}
        {isNhap && (
          <td>
            {settled ? (
              "—"
            ) : (
              <input
                type="date"
                className="rc-input kho-hsd__date"
                value={block.hsd}
                onChange={(e) => onHsd(e.target.value)}
                aria-label="Hạn sử dụng"
              />
            )}
          </td>
        )}
      </tr>

      {hasDetail && (
        <tr className="kho-alloc__detailrow">
          <td aria-hidden />
          <td colSpan={isNhap ? 10 : 8}>
            {quyDoiHint}
            {lyDoBox}
            {!isNhap && (
              <>
                {block.thieu > 0 && (
                  <div className="banner banner--warn">
                    <span>
                      {/* `cappedTon` = phần cấp được, ĐÃ quy về ĐƠN VỊ YÊU CẦU (khớp nhãn `l.dvt`).
                          KHÔNG dùng `l.sl_con_lai - block.thieu`: sl_con_lai (yêu cầu) trừ thieu
                          (gốc) là trộn đơn vị → ra số âm khi vật tư có quy đổi. */}
                      Kho chỉ còn {fmtQty(cappedTon)} {tenDonVi(l.dvt) ?? l.dvt}. Cấp{" "}
                      {fmtQty(cappedTon)} lần này, phần còn lại chờ nhập hoặc tạo yêu
                      cầu mới.
                    </span>
                  </div>
                )}
                {/* Bảng lô CHỈ ĐỌC: tự lấy theo FIFO (goiYLo). Hiển thị theo MÃ PHIẾU nhập (đợt hàng
                    vào kho) thay mã lô kỹ thuật; cột Lấy không cho sửa. */}
                <div className="kho-alloc__lots">
                  <table>
                    <thead>
                      <tr>
                        <th>Mã phiếu</th>
                        <th>Nhập</th>
                        <th>Vị trí</th>
                        <th>HSD</th>
                        <th className="kho-num">SL thực tế</th>
                        {canViewCost && <th className="kho-num">Đơn giá</th>}
                        <th className="kho-num">SL lấy</th>
                        {canViewCost && <th className="kho-num">Thành tiền</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {block.lots.length === 0 ? (
                        <tr>
                          <td colSpan={canViewCost ? 8 : 6} className="kho-lines__empty">
                            Không còn lô khả dụng trong kho này.
                          </td>
                        </tr>
                      ) : (
                        block.lots.map((lot) => (
                          <tr key={lot.lot_id}>
                            {/* Mã phiếu nhập gốc; tồn đầu kỳ không có phiếu → lùi về mã lô. */}
                            <td className="kho-lines__code">{lot.voucher_ma ?? lot.ma_lo}</td>
                            <td>{fmtDateISO(lot.ngay_nhap)}</td>
                            <td>{lot.vi_tri ?? "—"}</td>
                            <td>{lot.hsd ? fmtDateISO(lot.hsd) : "—"}</td>
                            <td className="kho-num">{fmtQty(lot.sl_con_lai)}</td>
                            {canViewCost && (
                              <td className="kho-num">
                                {lot.don_gia_nhap != null ? money(lot.don_gia_nhap) : ""}
                              </td>
                            )}
                            {/* SL lấy: mặc định TỰ LẤY theo FIFO, kho SỬA được nếu cần (cap ở setLotQty). */}
                            <td className="kho-num">
                              <DecimalInput
                                className={`rc-input kho-num${block.warnLotId === lot.lot_id ? " rc-input--invalid" : ""}`}
                                value={lot.so_luong}
                                onChange={(n) => onLotQty(lot.lot_id, n ?? 0)}
                                aria-label={`SL lấy từ phiếu ${lot.voucher_ma ?? lot.ma_lo}`}
                              />
                            </td>
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
                </div>
                {block.warn && <p className="kho-hint kho-hint--rust">{block.warn}</p>}
                <div
                  className={`kho-alloc__sum${matched ? " kho-alloc__sum--ok" : " kho-alloc__sum--off"}`}
                >
                  {matched
                    ? `Lấy đủ ${fmtQty(chosen)} / cần ${fmtQty(targetGoc)}`
                    : `Lấy ${fmtQty(chosen)} / cần ${fmtQty(targetGoc)} · thiếu ${fmtQty(Math.max(0, targetGoc - chosen))}`}
                </div>
              </>
            )}
          </td>
        </tr>
      )}
      {anhZoom && shownAnh && (
        <tr>
          <td colSpan={isNhap ? 10 : 9} style={{ padding: 0, border: 0 }}>
            <div
              className="kho-anh__lightbox"
              role="dialog"
              aria-modal="true"
              onClick={() => setAnhZoom(false)}
            >
              <img src={shownAnh} alt={block.matLabel} onClick={(e) => e.stopPropagation()} />
            </div>
          </td>
        </tr>
      )}
    </>
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
  useNapTenDonVi();
  const [v, setV] = useState<StockVoucher | null>(null);
  // Bản in cần `sl_duyet` + ngày yêu cầu (mẫu 01-VT/02-VT có cột "Theo chứng từ") — hai thứ
  // này chỉ có trên yêu cầu, nên phiếu phải kéo kèm.
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
  // Điều chỉnh phiếu XUẤT đã ghi sổ khi SX dùng ÍT hơn (xuất 10 → 7): sửa giảm số, trả dư về lô.
  const [adjusting, setAdjusting] = useState(false);
  const [adjQty, setAdjQty] = useState<Record<number, number>>({});
  const [adjLyDo, setAdjLyDo] = useState("");   // lý do điều chỉnh (BẮT BUỘC)

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

  // Lịch sử ĐIỀU CHỈNH phiếu xuất (ai · bộ phận · lúc nào · đổi gì). Rỗng thì ẩn khối.
  const [dcHistory, setDcHistory] = useState<DieuChinhLichSu[]>([]);
  const loadDcHistory = useCallback(() => {
    api.kho.phieu
      .lichSuDieuChinh(token, voucherId)
      .then(setDcHistory)
      .catch(() => setDcHistory([]));
  }, [token, voucherId]);
  useEffect(loadDcHistory, [loadDcHistory]);

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
      nguoiLapPhieu: v.nguoi_lap_ten ?? null,
      khoTen: v.kho_ten,
      diaDiem: null,
      lyDo: v.ghi_chu,
      // In ẩn GIÁ nghiêm theo quyền `view_cost`: KHÔNG có quyền → bỏ Đơn giá/Thành tiền/Tổng (template
      // tự ẩn 2 cột khi donGia null). Gate ở đây, KHÔNG dựa API — vì API còn nới cho người TẠO yêu cầu.
      tongTien: canViewCost ? v.gia_von : null,
      cancelled: v.trang_thai === "cancelled",
      lines: v.lines.map((l) => ({
        materialCode: l.hang_ma,
        materialName: l.hang_ten,
        maLo: l.ma_lo,
        dvt: tenDonVi(l.dvt) ?? l.dvt,   // TÊN có dấu (tờ/bản kẽm) thay MÃ (to/kem) — khớp bản in điều chuyển
        soLuongChungTu: req?.lines.find((x) => x.id === l.request_line_id)?.sl_duyet ?? null,
        soLuong: l.so_luong,
        donGia: canViewCost ? l.don_gia : null,
        thanhTien: canViewCost ? l.thanh_tien : null,
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

  function startAdjust() {
    if (!v) return;
    const seed: Record<number, number> = {};
    v.lines.forEach((l) => { seed[l.id] = l.so_luong; });
    setAdjQty(seed);
    setAdjLyDo("");
    setError(null);
    setAdjusting(true);
  }
  async function saveAdjust() {
    if (!v) return;
    // Chỉ gửi dòng THỰC SỰ giảm; số mới phải > 0 (bỏ hẳn cả dòng không phải việc ở đây).
    const lines = v.lines
      .filter((l) => (adjQty[l.id] ?? l.so_luong) < l.so_luong - 1e-9)
      .map((l) => ({ line_id: l.id, so_luong_moi: adjQty[l.id] ?? l.so_luong }));
    if (lines.length === 0) {
      setError("Chưa giảm dòng nào — sửa số ở cột “Số lượng” cho nhỏ hơn rồi lưu.");
      return;
    }
    if (lines.some((x) => x.so_luong_moi <= 0)) {
      setError("Số lượng mới phải lớn hơn 0.");
      return;
    }
    if (!adjLyDo.trim()) {
      setError("Phải nhập lý do điều chỉnh.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setV(await api.kho.phieu.dieuChinhXuat(token, v.id, lines, adjLyDo.trim()));
      setAdjusting(false);
      loadDcHistory();   // hiện ngay dòng lịch sử vừa tạo
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không điều chỉnh được phiếu.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
        <aside className="rc-drawer rc-drawer--wide kho-voucher-drawer" onClick={(e) => e.stopPropagation()}>
          <header className="rc-drawer__head">
            <div>
              <div className="rc-drawer__kicker">
                {v?.loai === "NHAP" ? "PHIẾU NHẬP KHO" : "PHIẾU XUẤT KHO"}
              </div>
              <h2 className="rc-drawer__title">{v?.ma ?? "Đang tải…"}</h2>
            </div>
            <div className="kho-headside">
              {v && <VoucherStatusBadge status={v.trang_thai} />}
              <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
                <Icon name="x" size={16} />
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
                  
                  {/* Meta Summary Banner phẳng 3 cột hairline (Không viền dày bên trái) */}
                  <div className="kho-meta-banner">
                    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                      <div>
                        <span className="kho-microlabel">Theo yêu cầu</span>
                        <span className="kho-meta-banner__badge">{v.request_ma || "—"}</span>
                      </div>
                      <div className="kho-vdivider" />
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div className="kho-user-avatar kho-user-avatar--charcoal">
                          {(v.nguoi_lap_ten || "U").slice(0, 1).toUpperCase()}
                        </div>
                        <div>
                          <span className="kho-microlabel">Người lập phiếu</span>
                          <div style={{ fontWeight: "var(--fw-medium)", color: "var(--ink)", fontSize: 13 }}>
                            {v.nguoi_lap_ten || "—"}
                          </div>
                        </div>
                      </div>
                    </div>

                    {canViewCost && v.gia_von != null && (
                      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                        <div className="kho-vdivider" />
                        <div className="kho-top-kpi-pill">
                          <span className="kho-top-kpi-pill__label">Tổng giá vốn ({v.lines.length} dòng)</span>
                          <span className="kho-top-kpi-pill__val">{money(v.gia_von)}</span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* kho-voucher-info-grid: lưới 2 cột phẳng mượt */}
                  <div className="rc-grid kho-voucher-info-grid">
                    <Readout label="Người tạo yêu cầu" value={v.nguoi_de_nghi_ten || "—"} />
                    <Readout label="Người lập phiếu" value={v.nguoi_lap_ten || "—"} />
                    <Readout label="Theo yêu cầu" value={v.request_ma || "—"} />
                    <Readout label="Kho" value={v.kho_ten || "—"} />
                    <Readout
                      label={v.loai === "NHAP" ? "Ngày nhập kho" : "Ngày xuất kho"}
                      value={fmtDateISO(v.ngay)}
                    />
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
                  {adjusting && (
                    <div className="banner banner--info" style={{ marginBottom: 8 }}>
                      <span>
                        SX dùng ít hơn? Sửa <b>GIẢM</b> ô “Số lượng” từng dòng — phần dư trả về lô
                        nguồn, yêu cầu tính lại phần còn thiếu.
                      </span>
                    </div>
                  )}
                  <div className="kho-lines__wrap kho-lines-card">
                    <table className="kho-lines" style={{ width: "100%", tableLayout: "auto" }}>
                      <thead>
                        <tr>
                          <th style={{ minWidth: 300 }}>Vật tư</th>
                          <th style={{ width: 60, textAlign: "center" }}>ĐVT</th>
                          <th className="kho-num" style={{ width: 110 }}>Số lượng</th>
                          {canViewCost && <th className="kho-num" style={{ width: 120 }}>Đơn giá</th>}
                          {canViewCost && <th className="kho-num" style={{ width: 130 }}>Thành tiền</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {v.lines.map((l) => (
                          <tr key={l.id}>
                            <td style={{ minWidth: 300 }}>
                              <div className="kho-lines__name" style={{ fontWeight: "var(--fw-bold)", color: "var(--ink)" }}>{l.hang_ten ?? "—"}</div>
                              <div className="kho-lines__code" style={{ fontFamily: "var(--ff-num)", fontSize: 11, color: "var(--ash)" }}>{l.hang_ma ?? ""}</div>
                            </td>
                            <td className="kho-lines__code" style={{ textAlign: "center" }}>{tenDonVi(l.dvt) ?? l.dvt ?? "—"}</td>
                            <td className="kho-num">
                              {adjusting ? (
                                <DecimalInput
                                  className="rc-input rc-input--num"
                                  style={{ width: 92, textAlign: "right" }}
                                  value={adjQty[l.id] ?? l.so_luong}
                                  aria-label={`Số lượng thực dùng — ${l.hang_ten ?? ""}`}
                                  onChange={(n) => setAdjQty((m) => ({ ...m, [l.id]: n ?? 0 }))}
                                />
                              ) : (
                                fmtQty(l.so_luong)
                              )}
                            </td>
                            {canViewCost && (
                              <td className="kho-num">
                                {l.don_gia != null ? money(l.don_gia) : ""}
                              </td>
                            )}
                            {canViewCost && (
                              <td className="kho-num" style={{ fontWeight: "var(--fw-bold)" }}>
                                {l.thanh_tien != null ? money(l.thanh_tien) : ""}
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {adjusting && (
                    <label className="rc-field rc-field--full" style={{ marginTop: 10 }}>
                      <span className="rc-field__label">Lý do điều chỉnh <em>*</em></span>
                      <div className="rc-input-wrapper">
                        <textarea
                          className="rc-textarea"
                          rows={2}
                          value={adjLyDo}
                          onChange={(e) => setAdjLyDo(e.target.value)}
                          placeholder="Vd: SX chỉ dùng 7, trả 3 về kho / khai dư số lượng…"
                        />
                      </div>
                    </label>
                  )}
                </section>

                {dcHistory.length > 0 && (
                  <section className="rc-sec">
                    <h3 className="rc-sec__title">Lịch sử điều chỉnh</h3>
                    <div className="kho-lines__wrap kho-lines-card">
                      <table className="kho-lines" style={{ width: "100%", tableLayout: "auto" }}>
                        <thead>
                          <tr>
                            <th style={{ width: 140 }}>Thời điểm</th>
                            <th style={{ width: 130 }}>Người điều chỉnh</th>
                            <th style={{ width: 110 }}>Bộ phận</th>
                            <th style={{ width: 180 }}>Nội dung</th>
                            <th>Lý do</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dcHistory.map((h, i) => (
                            <tr key={i}>
                              <td>{fmtDateTime(h.thoi_diem)}</td>
                              <td><strong>{h.nguoi_ten ?? "—"}</strong></td>
                              <td>{h.bo_phan_ten ?? "—"}</td>
                              <td>{h.chi_tiet ?? "—"}</td>
                              <td>{h.ly_do ?? "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                )}

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
                            {a.file_name}
                          </a>
                          {canCreate && v.trang_thai !== "cancelled" && (
                            <button
                              type="button"
                              className="rc-bands__del"
                              aria-label={`Xóa ${a.file_name}`}
                              disabled={attBusy}
                              onClick={() => removeAtt(a.id)}
                            >
                              <Icon name="x" size={13} />
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
            {/* Điều chỉnh phiếu XUẤT ĐÃ ghi sổ khi SX dùng ít hơn — KHÔNG cho phiếu điều chuyển (vế
                nội bộ cặp đôi, sửa lệch vỡ cân đối 2 kho; muốn khác thì điều chuyển ngược lại). */}
            {canCreate && v?.loai === "XUAT" && v?.trang_thai === "posted"
              && !v?.dieu_chuyen && !adjusting && (
              <button type="button" className="btn btn--secondary" onClick={startAdjust}>
                Điều chỉnh (dùng ít hơn)
              </button>
            )}
            {adjusting && (
              <>
                <button type="button" className="btn btn--ghost" onClick={() => setAdjusting(false)} disabled={busy}>
                  Hủy sửa
                </button>
                <Button variant="accent" loading={busy} onClick={saveAdjust}>
                  Lưu điều chỉnh
                </Button>
              </>
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
        message={
          v?.loai === "NHAP"
            ? "Tồn kho sẽ cộng ngay và phiếu không sửa được nữa."
            : "Tồn kho sẽ trừ ngay và phiếu không sửa được nữa."
        }
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
        message="Yêu cầu sẽ chuyển sang 'Đã hủy' kèm lý do và KHÔNG cấp lại. Phiếu vẫn giữ số & in được, nhưng không ghi sổ được nữa."
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
            placeholder="Vì sao hủy yêu cầu này? (bắt buộc)"
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
            <Icon name="x" size={16} />
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
                {/* Cùng ô chọn với dòng yêu cầu — một cách chọn mặt hàng cho cả module, khỏi hai
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
