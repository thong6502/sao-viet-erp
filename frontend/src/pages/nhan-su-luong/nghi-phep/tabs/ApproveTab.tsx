// Tab "Duyệt đơn" (HR) (tách từ pages/NghiPhepPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { api, type LeaveRequest, type XinHuyChoDuyet } from "../../../../api/client";
import { Pager, trangHopLe } from "../../../../components/Pager";
import { LocThangTao } from "../../../../components/LocThangTao";
import { fmtDate } from "../../../../utils/format";
import { LeaveTable } from "../components/LeaveTable";
import { PAGE_SIZE } from "../shared/constants";
import { errMsg } from "../shared/helpers";
import { LyDoDialog, XinHuyHangDoi } from "../../xin-huy/XinHuy";

/** Tóm tắt một đơn nghỉ cho hàng đợi xin hủy / hộp thoại. */
const tomTat = (r: LeaveRequest) =>
  `${r.leave_type_name ?? "Nghỉ"} · ${fmtDate(r.start_date)}–${fmtDate(r.end_date)} (${r.days} ngày)`;

// --- Tab: Duyệt đơn (HR) ----------------------------------------------------

export function ApproveTab({ token, onChanged, focusEmployeeId, eventTick }: {
  token: string; onChanged?: () => void; focusEmployeeId?: number;
  /** Nhích theo mỗi sự kiện real-time — thợ gửi đơn / xin hủy là hàng đợi tự tươi (23/09/2026). */
  eventTick?: number;
}) {
  // Liên thông từ Hồ sơ NV: lọc theo 1 NV + mặc định xem TẤT CẢ trạng thái (không chỉ chờ duyệt).
  const [status, setStatus] = useState(focusEmployeeId ? "" : "pending");
  const [focus, setFocus] = useState<number | undefined>(focusEmployeeId);
  // Nhảy từ Hồ sơ NV sang: đổi bộ lọc thì phải VỀ TRANG 1 luôn, không thì rơi vào trang cũ
  // của bộ lọc cũ và màn báo "chưa có đơn nghỉ của người này" trong khi người ta có đơn.
  useEffect(() => { if (focusEmployeeId) { setFocus(focusEmployeeId); setStatus(""); setPage(1); } }, [focusEmployeeId]);
  const [items, setItems] = useState<LeaveRequest[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  /** Lọc theo THÁNG TẠO đơn (`YYYY-MM`, rỗng = tất cả) — 23/09/2026. */
  const [thang, setThang] = useState("");
  const [sel, setSel] = useState<Set<number>>(new Set());
  // Từ chối: đơn lẻ (LeaveRequest) HOẶC hàng loạt ("bulk") — cùng 1 modal, 1 lý do.
  const [rejectTarget, setRejectTarget] = useState<LeaveRequest | "bulk" | null>(null);
  const [rejectNote, setRejectNote] = useState("");
  const [busy, setBusy] = useState(false);
  /** Lỗi THAO TÁC (duyệt / từ chối) — hiện trong hộp thoại từ chối. */
  const [error, setError] = useState<string | null>(null);
  /** Lỗi TẢI hàng đợi — ô nhớ RIÊNG, chỉ nó mới được thay chỗ của bảng. */
  const [listError, setListError] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  // Yêu cầu HỦY đơn đã duyệt đang chờ trong phạm vi (23/09/2026) — tải riêng, lỗi thì chỉ khối này trống.
  const [xinHuy, setXinHuy] = useState<XinHuyChoDuyet<LeaveRequest>[]>([]);
  // Người duyệt hủy thẳng đơn ĐÃ DUYỆT — bắt buộc ghi lý do để người lao động biết.
  const [huyDon, setHuyDon] = useState<LeaveRequest | null>(null);
  const [huyBusy, setHuyBusy] = useState(false);
  const [huyErr, setHuyErr] = useState<string | null>(null);
  const loadXinHuy = useCallback(() => {
    api.leaves.xinHuyChoDuyet(token).then((r) => setXinHuy(r.items)).catch(() => setXinHuy([]));
  }, [token]);
  useEffect(() => { loadXinHuy(); }, [loadXinHuy, eventTick]);
  const load = useCallback(() => {
    setLoadingList(true);
    setListError(null);
    // LỌC THEO 1 NHÂN VIÊN CHẠY Ở MÁY CHỦ (`employeeId`), không còn `items.filter(...)` ở client.
    // Lọc ở client + phân trang = đơn của người đó nằm ở trang khác thì màn báo "chưa có đơn
    // nghỉ của người này" — sai sự thật, mà đường vào đây chính là bấm từ Hồ sơ NV.
    api.leaves.list(token, {
      status: status || undefined,
      employeeId: focus,
      thang: thang || undefined,
      page,
      size: PAGE_SIZE,
    })
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
        setSel(new Set());
        const trangCanVe = trangHopLe(page, r.total, PAGE_SIZE);
        if (trangCanVe !== null) setPage(trangCanVe);
      })
      .catch((e) => { setItems([]); setTotal(0); setListError(errMsg(e)); })
      .finally(() => setLoadingList(false));
  }, [token, status, focus, page, thang]);
  useEffect(() => { load(); }, [load, eventTick]);

  const shown = items;   // máy chủ đã lọc sẵn theo `focus`
  const focusName = focus ? items.find((i) => i.employee_id === focus)?.employee_name : undefined;
  // ⚠ CHỈ id chờ duyệt CỦA TRANG ĐANG XEM. "Chọn tất cả" và các nút hàng loạt vì thế cũng chỉ
  // tác động trong phạm vi trang này — chân bảng nói rõ điều đó cho người duyệt biết.
  const pendingIds = shown.filter((i) => i.status === "pending").map((i) => i.id);
  const selArr = [...sel];
  function toggle(id: number) { setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; }); }
  function toggleAll() { setSel((s) => (s.size === pendingIds.length && pendingIds.length > 0 ? new Set() : new Set(pendingIds))); }

  async function approve(id: number) { await api.leaves.approve(token, id); load(); onChanged?.(); }
  async function quyetXinHuy(ycId: number, dongY: boolean, ghiChu: string) {
    await api.leaves.quyetXinHuy(token, ycId, dongY, ghiChu || undefined);
    loadXinHuy(); load(); onChanged?.();
  }
  async function huyThang(lyDo: string) {
    if (!huyDon) return;
    setHuyBusy(true); setHuyErr(null);
    try {
      await api.leaves.cancel(token, huyDon.id, lyDo);
      setHuyDon(null); loadXinHuy(); load(); onChanged?.();
    } catch (e) { setHuyErr(errMsg(e)); } finally { setHuyBusy(false); }
  }
  async function bulkApprove() {
    setBusy(true);
    try { await api.leaves.bulkApprove(token, selArr); load(); onChanged?.(); }
    catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  }
  async function confirmReject() {
    if (!rejectNote.trim()) return;
    setBusy(true); setError(null);
    try {
      if (rejectTarget === "bulk") await api.leaves.bulkReject(token, selArr, rejectNote.trim());
      else if (rejectTarget) await api.leaves.reject(token, rejectTarget.id, rejectNote.trim());
      setRejectTarget(null); setRejectNote(""); load(); onChanged?.();
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  }

  return (
    <div>
      {focus != null && (
        <div className="cc-focus">
          <span>Đang xem đơn nghỉ của <b>{focusName ?? `NV #${focus}`}</b></span>
          <button type="button" className="btn btn--ghost" onClick={() => { setFocus(undefined); setPage(1); }}>✕ Bỏ lọc — xem cả xưởng</button>
        </div>
      )}
      <div className="cc-ts-toolbar">
        <div className="cc-select-wrapper" style={{ width: "160px" }}>
          {/* ĐỔI BỘ LỌC ⇒ VỀ TRANG 1, đặt NGAY TRONG handler (không qua `useEffect` theo dõi
              `status`): làm ở effect thì lượt tải cũ đã bắn đi với số trang cũ rồi mới tới lượt
              mới — hai lượt chồng nhau. Thiếu hẳn bước reset thì đang ở trang 3, đổi sang "Chờ
              duyệt" chỉ còn 1 trang ⇒ bảng rỗng trơn mà người duyệt tưởng hết việc. */}
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="pending">Chờ duyệt</option>
            <option value="approved">Đã duyệt</option>
            <option value="rejected">Từ chối</option>
            <option value="cancelled">Đã hủy</option>
            <option value="">Tất cả</option>
          </select>
        </div>
        {/* Đổi tháng ⇒ về trang 1 NGAY trong handler, cùng lý do với ô trạng thái ở trên. */}
        <LocThangTao value={thang} onChange={(v) => { setThang(v); setPage(1); }} />
      </div>
      {sel.size > 0 && (
        <div className="cc-bulk-actions-floating">
          <span className="cc-bulk-label">{sel.size} đơn đã chọn</span>
          <div className="cc-bulk-btn-group">
            <button className="btn btn--primary cc-btn-approve" onClick={bulkApprove} disabled={busy}>✓ Duyệt {sel.size}</button>
            <button className="btn btn--ghost cc-btn-reject" onClick={() => { setRejectTarget("bulk"); setRejectNote(""); setError(null); }} disabled={busy}>✕ Từ chối {sel.size}</button>
            <button className="btn btn--ghost" onClick={() => setSel(new Set())} disabled={busy}>Bỏ chọn</button>
          </div>
        </div>
      )}
      {/* Xin hủy đơn đã duyệt (23/09/2026): đứng TRÊN bảng — đơn vẫn hiệu lực tới khi quyết, để lâu
          là tổ trưởng xếp người theo một kế hoạch có thể đã đổi. */}
      <XinHuyHangDoi
        donVi="đơn"
        dong={xinHuy.map((x) => ({
          yc: x.yeu_cau,
          ten: x.don.employee_name ?? `NV#${x.don.employee_id}`,
          don: tomTat(x.don),
        }))}
        onQuyet={(yc, dongY, ghiChu) => quyetXinHuy(yc.id, dongY, ghiChu)}
      />
      <LeaveTable items={shown} showEmployee onApprove={approve}
        onHuyDaDuyet={(r) => { setHuyErr(null); setHuyDon(r); }}
        onReject={(r) => { setRejectTarget(r); setRejectNote(""); setError(null); }}
        selectable selected={sel} onToggle={toggle} onToggleAll={toggleAll} allPendingCount={pendingIds.length}
        loading={loadingList} listError={listError} onRetry={load}
        emptyTitle={focus ? "Chưa có đơn nghỉ của người này" : "Chưa có đơn xin nghỉ nào"}
        emptySub={thang ? "Không có đơn nào tạo trong tháng này khớp bộ lọc — bỏ lọc tháng (nút ✕) hoặc đổi trạng thái." : status === "pending" ? "Không còn đơn nào chờ duyệt. Đổi bộ lọc trạng thái để xem đơn đã xử lý." : "Thử đổi bộ lọc trạng thái ở trên."} />
      {!loadingList && !listError && shown.length > 0 && (
        <Pager
          total={total}
          page={page}
          size={PAGE_SIZE}
          loading={loadingList}
          unit="đơn"
          onPage={setPage}
          // Nói THẲNG giới hạn của nút hàng loạt: ô tick "chọn tất cả" chỉ quét trang đang xem.
          // Không nói thì người duyệt bấm "Duyệt 20" rồi tưởng đã dọn sạch hàng đợi.
          note={total > PAGE_SIZE ? "chọn hàng loạt chỉ áp cho trang đang xem" : undefined}
        />
      )}
      <LyDoDialog
        open={huyDon !== null}
        title="Hủy đơn đã duyệt"
        message={huyDon ? `${huyDon.employee_name ?? `NV#${huyDon.employee_id}`} · ${tomTat(huyDon)}. Người lao động được báo ngay kèm lý do.` : undefined}
        label="Lý do hủy"
        placeholder="vd: tổ cần người, đã báo trực tiếp"
        confirmLabel="Hủy đơn"
        danger
        busy={huyBusy}
        error={huyErr}
        onConfirm={huyThang}
        onCancel={() => setHuyDon(null)}
      />
      {rejectTarget && (
        <div className="ns-modal" role="dialog" aria-modal="true">
          <div className="ns-modal__box cc-day-detail-modal-box">
            <header className="ns-modal__head">
              <div className="cc-modal-title-group">
                <h2>{rejectTarget === "bulk" ? `Từ chối ${sel.size} đơn` : "Từ chối đơn nghỉ"}</h2>
                <p className="cc-modal-subtitle">
                  {rejectTarget === "bulk"
                    ? `Áp 1 lý do chung cho ${sel.size} đơn đã chọn.`
                    : `${rejectTarget.employee_name ?? `NV#${rejectTarget.employee_id}`} · ${rejectTarget.leave_type_name ?? "—"}`}
                </p>
              </div>
              <button className="ns-modal__x" onClick={() => setRejectTarget(null)}>×</button>
            </header>
            <div className="ns-modal__body cc-day-detail-modal-body">
              {error && <div className="banner banner--error cc-ts-msg-banner" style={{ marginBottom: "16px" }}>{error}</div>}
              {rejectTarget !== "bulk" && (
                <div className="cc-info-card-note" style={{ margin: "0 0 14px 0" }}>
                  <span>Ngày: <b>{fmtDate(rejectTarget.start_date)}–{fmtDate(rejectTarget.end_date)}</b> ({rejectTarget.days} ngày)</span>
                </div>
              )}
              <label className="ns-field">
                <span className="cc-field-label">Lý do từ chối *</span>
                <input autoFocus className="cc-input-text" value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} placeholder="Nêu rõ lý do để NV biết…" />
              </label>
            </div>
            <footer className="ns-modal__foot">
              <button className="btn btn--ghost" onClick={() => setRejectTarget(null)} disabled={busy}>Hủy</button>
              <button className="btn btn--primary ns-danger" onClick={confirmReject} disabled={busy || !rejectNote.trim()}>{busy ? "Đang gửi…" : "Từ chối"}</button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
