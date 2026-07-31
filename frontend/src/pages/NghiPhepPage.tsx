// Nghỉ phép (module `nhan_su`). 3 tab:
//   • Đơn của tôi — NV tạo đơn xin nghỉ + xem/hủy đơn của mình (self-service).
//   • Duyệt đơn (HR) — chờ duyệt → duyệt / từ chối; xem toàn bộ.
//   • Loại nghỉ (HR) — khai loại nghỉ (có lương / hạn mức).
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  type LeaveCalendar,
  type LeaveQuota,
  type LeaveRequest,
  type LeaveType,
  type LeaveTypeInput,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Timeline, type TimelineEntry } from "../components/Timeline";
import { AlertTriangle, Search, ChevronLeft, ChevronRight, Users, Clock, FileText, ClipboardCheck, Calendar, Sliders, Plus, Info, CheckCircle2, XCircle, LayoutGrid, List, Edit3, Trash2, ShieldCheck, Layers } from "lucide-react";
import "./nhan-su.css";
import "./cham-cong.css";
import "./nghi-phep.css";

type Tab = "me" | "approve" | "calendar" | "types";

const STATUS_LABEL: Record<string, string> = {
  pending: "Chờ duyệt", approved: "Đã duyệt", rejected: "Từ chối", cancelled: "Đã hủy",
};

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString("vi-VN");
}
function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : "Có lỗi xảy ra.";
}
function StatusBadge({ s }: { s: string }) {
  if (s === "approved") {
    return (
      <span className="cc-status-pill cc-status-pill--approved">
        <CheckCircle2 size={12} />
        <span>Đã duyệt</span>
      </span>
    );
  }
  if (s === "pending") {
    return (
      <span className="cc-status-pill cc-status-pill--pending">
        <span className="cc-status-dot cc-status-dot--pending" />
        <span>Chờ duyệt</span>
      </span>
    );
  }
  if (s === "rejected") {
    return (
      <span className="cc-status-pill cc-status-pill--rejected">
        <XCircle size={12} />
        <span>Từ chối</span>
      </span>
    );
  }
  return (
    <span className="cc-status-pill cc-status-pill--cancelled">
      <span className="cc-status-dot cc-status-dot--cancelled" />
      <span>{STATUS_LABEL[s] ?? s}</span>
    </span>
  );
}

function getInitials(name?: string | null) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
  return (parts[parts.length - 2][0] + parts[parts.length - 1][0]).toUpperCase();
}


export function NghiPhepPage({ onChanged, focusEmployeeId }: { onChanged?: () => void; focusEmployeeId?: number }) {
  const { token } = useAuth();
  const can = useCan();
  // Quyền DUYỆT đơn — HCNS/Admin, VÀ tổ trưởng (chủ chốt 29/07/2026: tổ trưởng duyệt đơn trong
  // tổ mình). Dùng cho tab "Duyệt đơn" + "Lịch nghỉ".
  const canManage = can("nghi_phep", "approve");
  // Danh mục LOẠI NGHỈ là chính sách TOÀN CÔNG TY, chỉ HCNS/Admin. Phải gác bằng `update` cho
  // KHỚP backend (`routers/leaves.py` gác 3 endpoint /types bằng `update`) — gác bằng `approve`
  // là tổ trưởng (approve=true, update=false) nhìn thấy tab, mở ra, bấm lưu rồi ăn 403: màn
  // mời-rồi-đuổi, người dùng tưởng mình có quyền.
  const canTypes = can("nghi_phep", "update");
  const [tab, setTab] = useState<Tab>("me");

  // Liên thông từ Hồ sơ NV → mở "Duyệt đơn" lọc đúng NV đó.
  useEffect(() => {
    if (focusEmployeeId && canManage) setTab("approve");
  }, [focusEmployeeId, canManage]);

  return (
    <main className="ns">
      <header className="ns__head">
        <div>
          <h1 className="ns__title">Nghỉ phép</h1>
          <p className="ns__sub">Đơn xin nghỉ · duyệt · loại nghỉ. Ngày nghỉ đã duyệt hiện trên Bảng công tháng.</p>
        </div>
      </header>
      <nav className="ns-tabs cc-tabs lg-tabs" aria-label="Phân hệ Nghỉ phép">
        <div className="lg-tabs__group">
          <button className={`lg-tab-btn ${tab === "me" ? "is-active" : ""}`} onClick={() => setTab("me")} title="Đơn xin nghỉ cá nhân">
            <FileText className="lg-tab-btn__icon" />
            <span>Đơn của tôi</span>
          </button>
          {canManage && (
            <button className={`lg-tab-btn ${tab === "approve" ? "is-active" : ""}`} onClick={() => setTab("approve")} title="Duyệt đơn xin nghỉ nhân viên">
              <ClipboardCheck className="lg-tab-btn__icon" />
              <span>Duyệt đơn</span>
            </button>
          )}
          {canManage && (
            <button className={`lg-tab-btn ${tab === "calendar" ? "is-active" : ""}`} onClick={() => setTab("calendar")} title="Lịch nghỉ toàn công ty">
              <Calendar className="lg-tab-btn__icon" />
              <span>Lịch nghỉ</span>
            </button>
          )}
          {/* Loại nghỉ theo quyền UPDATE (khác 3 tab trên dùng APPROVE) — giữ đúng phân quyền
              của dev, đừng gộp về canManage. */}
          {canTypes && (
            <button className={`lg-tab-btn ${tab === "types" ? "is-active" : ""}`} onClick={() => setTab("types")} title="Cấu hình loại nghỉ">
              <Sliders className="lg-tab-btn__icon" />
              <span>Loại nghỉ</span>
            </button>
          )}
        </div>
      </nav>
      {tab === "me" && <MyLeaveTab token={token!} onChanged={onChanged} />}
      {tab === "approve" && canManage && <ApproveTab token={token!} onChanged={onChanged} focusEmployeeId={focusEmployeeId} />}
      {tab === "calendar" && canManage && <CalendarTab token={token!} />}
      {tab === "types" && canTypes && <LeaveTypesTab token={token!} />}
    </main>
  );
}

// --- Tab: Đơn của tôi -------------------------------------------------------

// Timeline trạng thái của 1 đơn (gửi → chờ → kết quả) cho panel chi tiết.
function requestTimeline(r: LeaveRequest): TimelineEntry[] {
  const tl: TimelineEntry[] = [
    { title: "Đã gửi đơn", meta: fmtDate(r.created_at), tone: "moss", accent: true },
  ];
  if (r.status === "pending") tl.push({ title: "Chờ HCNS duyệt…", tone: "rust", accent: true });
  else if (r.status === "approved") tl.push({ title: `Đã duyệt${r.is_paid === false ? " (không lương)" : " (tính công P)"}`, meta: [fmtDate(r.decided_at), r.decision_note].filter(Boolean).join(" · ") || undefined, tone: "moss", accent: true });
  else if (r.status === "rejected") tl.push({ title: "Bị từ chối", meta: r.decision_note ?? undefined, tone: "signal", accent: true });
  else if (r.status === "cancelled") tl.push({ title: "Đã hủy", tone: "steel" });
  return tl;
}

function LeaveRequestFormModal({
  types,
  busy,
  error,
  form,
  setForm,
  onClose,
  onSubmit,
}: {
  types: LeaveType[];
  busy: boolean;
  error: string | null;
  form: { leave_type_id: number | ""; start_date: string; end_date: string; reason: string };
  setForm: React.Dispatch<React.SetStateAction<{ leave_type_id: number | ""; start_date: string; end_date: string; reason: string }>>;
  onClose: () => void;
  onSubmit: () => void;
}) {
  // Ngày ngược (vd 1/8 → 31/7). Backend đã chặn (`leave_service.create_request`), nhưng để nó
  // chặn nghĩa là bắt người dùng đi hết một vòng gửi–chờ–báo đỏ mới biết mình gõ nhầm.
  const ngayNguoc = !!form.start_date && !!form.end_date && form.end_date < form.start_date;
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <div className="cc-modal-title-group">
            <h2>Tạo đơn xin nghỉ phép</h2>
          </div>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body cc-day-detail-modal-body">
          {error && <div className="banner banner--error cc-ts-msg-banner" style={{ marginBottom: "16px" }}>{error}</div>}

          <label className="ns-field">
            <span className="cc-field-label">Loại nghỉ *</span>
            <select value={form.leave_type_id} onChange={(e) => setForm({ ...form, leave_type_id: e.target.value === "" ? "" : Number(e.target.value) })}>
              <option value="">— chọn —</option>
              {types.map((t) => <option key={t.id} value={t.id}>{t.name}{t.is_paid ? " (có lương)" : " (không lương)"}</option>)}
            </select>
          </label>

          <div className="ns-grid" style={{ marginTop: 14 }}>
            <label className="ns-field">
              <span className="cc-field-label">Từ ngày *</span>
              {/* Đẩy "Từ ngày" vượt qua "Đến ngày" đã chọn ⇒ kéo Đến ngày theo. Nghỉ 1 ngày là ca
                  phổ biến nhất nên đây gần như luôn đúng ý, và người dùng THẤY ô đổi trước mắt
                  chứ không bị sửa lén lúc bấm Gửi. */}
              <input
                type="date"
                value={form.start_date}
                onChange={(e) => {
                  const bd = e.target.value;
                  setForm({
                    ...form,
                    start_date: bd,
                    end_date: bd && form.end_date && form.end_date < bd ? bd : form.end_date,
                  });
                }}
              />
            </label>
            <label className="ns-field">
              <span className="cc-field-label">Đến ngày *</span>
              {/* `min` chỉ làm mờ ngày trong lịch chọn — nút Gửi là onClick thường chứ không phải
                  submit của <form> nên validation gốc của trình duyệt KHÔNG BAO GIỜ chạy, gõ tay
                  vẫn lọt. Chốt thật nằm ở `submit()`. */}
              <input
                type="date"
                min={form.start_date || undefined}
                value={form.end_date}
                onChange={(e) => setForm({ ...form, end_date: e.target.value })}
              />
            </label>
          </div>
          {ngayNguoc && (
            <div className="banner banner--error" style={{ marginTop: 10 }}>
              Đến ngày phải sau hoặc bằng từ ngày.
            </div>
          )}

          <label className="ns-field" style={{ marginTop: 14 }}>
            <span className="cc-field-label">Lý do xin nghỉ</span>
            <input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="vd: Về quê, khám bệnh…" />
          </label>

          <div className="cc-info-card-note" style={{ marginTop: 16 }}>
            <AlertTriangle size={14} className="cc-note-icon" />
            <span>Ngày nghỉ theo lịch công ty (mặc định Chủ nhật) và ngày lễ không trừ vào phép năm. Đơn xin nghỉ phép năm sẽ bị chặn khi vượt quá số ngày phép còn lại.</span>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={onSubmit} disabled={busy}>
            {busy ? "Đang gửi đơn…" : "Gửi đơn xin nghỉ"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function LeaveRequestDetailModal({
  request,
  busy,
  onClose,
  onCancel,
}: {
  request: LeaveRequest;
  busy: boolean;
  onClose: () => void;
  onCancel: (id: number) => void;
}) {
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <div className="cc-modal-title-group">
            <h2>Chi tiết đơn xin nghỉ</h2>
            <p className="cc-modal-subtitle">
              {request.leave_type_name ?? "—"} · {fmtDate(request.start_date)}–{fmtDate(request.end_date)} ({request.days} ngày)
            </p>
          </div>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body cc-day-detail-modal-body">
          <div className="ns-kv">
            <span className="ns-kv__k">Loại nghỉ</span>
            <span className="ns-kv__v">{request.leave_type_name ?? "—"}{request.is_paid === false ? " (Không lương)" : " (Có lương)"}</span>
          </div>
          <div className="ns-kv">
            <span className="ns-kv__k">Thời gian nghỉ</span>
            <span className="ns-kv__v">{fmtDate(request.start_date)} đến {fmtDate(request.end_date)} ({request.days} ngày)</span>
          </div>
          <div className="ns-kv">
            <span className="ns-kv__k">Lý do xin nghỉ</span>
            <span className="ns-kv__v">{request.reason || "—"}</span>
          </div>
          {request.decision_note && (
            <div className="ns-kv">
              <span className="ns-kv__k">Ghi chú duyệt</span>
              <span className="ns-kv__v">{request.decision_note}</span>
            </div>
          )}
          
          <h4 className="ns-section__title" style={{ marginTop: 20, marginBottom: 10 }}>Tiến trình xử lý đơn</h4>
          <Timeline items={requestTimeline(request)} />
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>Đóng</button>
          {(request.status === "pending" || request.status === "approved") && (
            <button className="btn btn--ghost ns-danger" onClick={() => onCancel(request.id)} disabled={busy}>Hủy đơn</button>
          )}
        </footer>
      </div>
    </div>
  );
}

function MyLeaveTab({ token, onChanged }: { token: string; onChanged?: () => void }) {
  const [hasEmp, setHasEmp] = useState<boolean | null>(null);
  const [items, setItems] = useState<LeaveRequest[]>([]);
  const [quotas, setQuotas] = useState<LeaveQuota[]>([]);
  const [types, setTypes] = useState<LeaveType[]>([]);
  
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [selectedRequest, setSelectedRequest] = useState<LeaveRequest | null>(null);
  const [form, setForm] = useState({ leave_type_id: "" as number | "", start_date: "", end_date: "", reason: "" });

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Đọc id đơn đang mở qua ref để `load` KHÔNG phụ thuộc `selectedRequest`.
  // Nếu để trong deps + setSelectedRequest bên trong load → vòng lặp reopen: đóng modal
  // xong các load() cũ resolve lại set selectedRequest → popup bật lên liên tục.
  const selectedIdRef = useRef<number | null>(null);
  useEffect(() => { selectedIdRef.current = selectedRequest?.id ?? null; }, [selectedRequest]);

  const load = useCallback(() => {
    api.leaves.me(token).then((r) => {
      setHasEmp(r.has_employee);
      setItems(r.items);
      setQuotas(r.quotas ?? []);

      // Nếu modal đang mở thì đồng bộ lại trạng thái đơn (chỉ khi id còn khớp).
      const openId = selectedIdRef.current;
      if (openId != null) {
        const updated = r.items.find((item) => item.id === openId);
        if (updated) setSelectedRequest(updated);
      }
    }).catch(() => setHasEmp(false));
  }, [token]);
  
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.leaves.types(token).then((r) => setTypes(r.items.filter((t) => t.is_active))).catch(() => {}); }, [token]);

  async function submit() {
    setBusy(true); setError(null);
    try {
      if (form.leave_type_id === "") throw new ApiError("Chọn loại nghỉ.", 400);
      // Chốt THẬT cho ngày ngược (`min` trên ô date không chặn được vì nút Gửi không phải submit
      // của <form>). Dùng ĐÚNG câu chữ của backend `leave_service.create_request` — hai tầng nói
      // hai kiểu thì người dùng tưởng là hai lỗi khác nhau.
      if (form.start_date && form.end_date && form.end_date < form.start_date)
        throw new ApiError("Đến ngày phải sau hoặc bằng từ ngày.", 400);
      const created = await api.leaves.create(token, {
        leave_type_id: form.leave_type_id, start_date: form.start_date, end_date: form.end_date, reason: form.reason || null,
      });
      setForm({ leave_type_id: "", start_date: "", end_date: "", reason: "" });
      setIsCreateOpen(false);
      load(); 
      onChanged?.();
      setSelectedRequest(created); // Open details modal of newly created request
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  }
  
  async function cancel(id: number) {
    if (!window.confirm("Bạn có chắc chắn muốn hủy đơn xin nghỉ này không?")) return;
    setBusy(true);
    try {
      await api.leaves.cancel(token, id);
      setSelectedRequest(null);
      load(); 
      onChanged?.();
    } catch (e) {
      alert(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  if (hasEmp === false) {
    return <div className="banner banner--warn" style={{ marginTop: 12 }}>
      Tài khoản của bạn <strong>chưa gắn hồ sơ nhân viên</strong> nên không tạo đơn nghỉ được. Liên hệ HCNS.
    </div>;
  }

  return (
    <div>
      {quotas.length > 0 ? (
        <div className="cc-leave-header-strip">
          <div className="cc-quota-chips">
            {quotas.map((q) => {
              const isLow = q.remaining <= 0;
              const isMedium = q.remaining > 0 && q.remaining <= 2;
              const tone = isLow ? "low" : isMedium ? "medium" : "high";
              return (
                <div key={q.leave_type_id} className={`cc-quota-chip cc-quota-chip--${tone}`}>
                  <span className="cc-quota-chip-label">{q.name}</span>
                  <span className="cc-quota-chip-val">
                    còn <strong>{q.remaining}</strong>/{q.annual_quota} ngày
                  </span>
                  <span className="cc-quota-chip-sub">(đã dùng {q.used} ngày)</span>
                </div>
              );
            })}
          </div>

          <div className="cc-leave-header-right">
            <span className="cc-note-inline">
              <Info size={13} className="cc-note-inline-icon" />
              <span>Click dòng để xem chi tiết</span>
            </span>
            <button className="btn btn--primary cc-btn-cta-compact" onClick={() => { setIsCreateOpen(true); setError(null); }}>
              <Plus size={15} />
              <span>Xin nghỉ phép</span>
            </button>
          </div>
        </div>
      ) : (
        <div className="cc-leave-header-strip cc-leave-header-strip--simple">
          <span className="cc-note-inline">
            <Info size={13} className="cc-note-inline-icon" />
            <span>Click vào dòng bản ghi để xem chi tiết tiến trình đơn</span>
          </span>
          <button className="btn btn--primary cc-btn-cta-compact" onClick={() => { setIsCreateOpen(true); setError(null); }}>
            <Plus size={15} />
            <span>Xin nghỉ phép</span>
          </button>
        </div>
      )}

      <LeaveTable 
        items={items} 
        showEmployee={false} 
        onCancel={cancel}
        onRowClick={(r) => setSelectedRequest(r)}
      />

      {isCreateOpen && (
        <LeaveRequestFormModal 
          types={types}
          busy={busy}
          error={error}
          form={form}
          setForm={setForm}
          onClose={() => setIsCreateOpen(false)}
          onSubmit={submit}
        />
      )}

      {selectedRequest && (
        <LeaveRequestDetailModal 
          request={selectedRequest}
          busy={busy}
          onClose={() => setSelectedRequest(null)}
          onCancel={cancel}
        />
      )}
    </div>
  );
}

// --- Tab: Duyệt đơn (HR) ----------------------------------------------------

function ApproveTab({ token, onChanged, focusEmployeeId }: { token: string; onChanged?: () => void; focusEmployeeId?: number }) {
  // Liên thông từ Hồ sơ NV: lọc theo 1 NV + mặc định xem TẤT CẢ trạng thái (không chỉ chờ duyệt).
  const [status, setStatus] = useState(focusEmployeeId ? "" : "pending");
  const [focus, setFocus] = useState<number | undefined>(focusEmployeeId);
  useEffect(() => { if (focusEmployeeId) { setFocus(focusEmployeeId); setStatus(""); } }, [focusEmployeeId]);
  const [items, setItems] = useState<LeaveRequest[]>([]);
  const [sel, setSel] = useState<Set<number>>(new Set());
  // Từ chối: đơn lẻ (LeaveRequest) HOẶC hàng loạt ("bulk") — cùng 1 modal, 1 lý do.
  const [rejectTarget, setRejectTarget] = useState<LeaveRequest | "bulk" | null>(null);
  const [rejectNote, setRejectNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    api.leaves.list(token, status || undefined).then((r) => { setItems(r.items); setSel(new Set()); }).catch(() => setItems([]));
  }, [token, status]);
  useEffect(() => { load(); }, [load]);

  const shown = focus ? items.filter((i) => i.employee_id === focus) : items;
  const focusName = focus ? items.find((i) => i.employee_id === focus)?.employee_name : undefined;
  const pendingIds = shown.filter((i) => i.status === "pending").map((i) => i.id);
  const selArr = [...sel];
  function toggle(id: number) { setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; }); }
  function toggleAll() { setSel((s) => (s.size === pendingIds.length && pendingIds.length > 0 ? new Set() : new Set(pendingIds))); }

  async function approve(id: number) { await api.leaves.approve(token, id); load(); onChanged?.(); }
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
          <button type="button" className="btn btn--ghost" onClick={() => setFocus(undefined)}>✕ Bỏ lọc — xem cả xưởng</button>
        </div>
      )}
      <div className="cc-ts-toolbar">
        <div className="cc-select-wrapper" style={{ width: "160px" }}>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="pending">Chờ duyệt</option>
            <option value="approved">Đã duyệt</option>
            <option value="rejected">Từ chối</option>
            <option value="">Tất cả</option>
          </select>
        </div>
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
      <LeaveTable items={shown} showEmployee onApprove={approve}
        onReject={(r) => { setRejectTarget(r); setRejectNote(""); setError(null); }}
        selectable selected={sel} onToggle={toggle} onToggleAll={toggleAll} allPendingCount={pendingIds.length} />
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

// --- Tab: Lịch nghỉ (HR) — lưới NV × ngày, tránh duyệt trùng người ----------

const WEEKDAYS = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

function CalendarTab({ token }: { token: string }) {
  const now = new Date();
  const [ym, setYm] = useState<{ year: number; month: number }>({ year: now.getFullYear(), month: now.getMonth() + 1 });
  const [data, setData] = useState<LeaveCalendar | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "approved" | "pending" | "paid" | "unpaid">("all");
  const [hoveredCell, setHoveredCell] = useState<{
    employeeName: string;
    day: number;
    leaveTypeName: string;
    isPaid: boolean;
    status: string;
    rect: DOMRect;
  } | null>(null);

  useEffect(() => {
    api.leaves.calendar(token, ym.year, ym.month).then(setData).catch(() => setData(null));
  }, [token, ym]);

  function shift(delta: number) {
    let m = ym.month + delta, y = ym.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    setYm({ year: y, month: m });
  }

  function goToToday() {
    setYm({ year: now.getFullYear(), month: now.getMonth() + 1 });
  }

  const days = data ? Array.from({ length: data.days_in_month }, (_, i) => i + 1) : [];
  const isWeekend = (d: number) => { const wd = new Date(ym.year, ym.month - 1, d).getDay(); return wd === 0 || wd === 6; };
  const getWeekday = (d: number) => WEEKDAYS[new Date(ym.year, ym.month - 1, d).getDay()];

  // Date highlights
  const isCurrentMonth = now.getFullYear() === ym.year && (now.getMonth() + 1) === ym.month;
  const todayDay = now.getDate();

  // Stats calculation
  const totalEmployeesOff = data
    ? data.employees.filter(e => Object.values(e.days).some(d => d.status === "approved" || d.status === "pending")).length
    : 0;

  const totalPendingRequests = data
    ? data.employees.reduce((acc, e) => acc + Object.values(e.days).filter(d => d.status === "pending").length, 0)
    : 0;

  const totalPaidDays = data
    ? data.employees.reduce((acc, e) => acc + Object.values(e.days).filter(d => d.status === "approved" && d.is_paid).length, 0)
    : 0;

  // Filtering employees
  const filteredEmployees = data
    ? data.employees.filter(e => {
        const matchesName = e.employee_name.toLowerCase().includes(searchQuery.toLowerCase());
        if (!matchesName) return false;

        if (statusFilter === "all") return true;
        const dayList = Object.values(e.days);
        if (statusFilter === "pending") return dayList.some(d => d.status === "pending");
        if (statusFilter === "approved") return dayList.some(d => d.status === "approved");
        if (statusFilter === "paid") return dayList.some(d => d.status === "approved" && d.is_paid);
        if (statusFilter === "unpaid") return dayList.some(d => d.status === "approved" && !d.is_paid);
        return true;
      })
    : [];

  const ymStr = `${ym.year}-${String(ym.month).padStart(2, "0")}`;

  return (
    <div className="cc-calendar-tab-wrapper">
      {/* 1. Stats & Quick Search Bar */}
      <div className="cc-calendar-dashboard">
        <div className="cc-calendar-search-wrapper">
          <Search size={16} className="cc-calendar-search-icon" />
          <input
            type="text"
            className="cc-calendar-search-input"
            placeholder="Tìm theo tên nhân viên..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="cc-calendar-search-clear" onClick={() => setSearchQuery("")}>×</button>
          )}
        </div>
        
        <div className="cc-calendar-stats-strip">
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--users"><Users size={16} /></span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{totalEmployeesOff}</span>
              <span className="cc-calendar-stat-label">Nhân sự nghỉ</span>
            </div>
          </div>
          
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--clock"><Clock size={16} /></span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{totalPendingRequests}</span>
              <span className="cc-calendar-stat-label">Đơn chờ duyệt</span>
            </div>
          </div>

          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--check"><CheckCircle2 size={16} /></span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{totalPaidDays}</span>
              <span className="cc-calendar-stat-label">Ngày phép P</span>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Month Navigation & Filter Chips Bar */}
      <div className="cc-calendar-grid-header">
        <div className="cc-calendar-navigator">
          <button className="cc-calendar-month-btn" onClick={() => shift(-1)} title="Tháng trước">
            <ChevronLeft size={16} />
          </button>
          
          <div className="cc-calendar-month-picker-wrapper">
            <input
              type="month"
              className="cc-month-picker-hidden"
              value={ymStr}
              onChange={(e) => {
                if (e.target.value) {
                  const [y, m] = e.target.value.split("-").map(Number);
                  setYm({ year: y, month: m });
                }
              }}
              id="cc-calendar-month-picker"
            />
            <label htmlFor="cc-calendar-month-picker" className="cc-calendar-month-title-pill" title="Bấm để chọn nhanh tháng">
              <Calendar size={14} style={{ marginRight: 6 }} />
              Tháng {ym.month} / {ym.year}
            </label>
          </div>
          
          <button className="cc-calendar-month-btn" onClick={() => shift(1)} title="Tháng sau">
            <ChevronRight size={16} />
          </button>

          {!isCurrentMonth && (
            <button className="cc-calendar-today-btn" onClick={goToToday} title="Trở về tháng hiện tại">
              Hôm nay
            </button>
          )}
        </div>

        <div className="cc-calendar-filter-chips">
          <button
            className={`cc-calendar-chip ${statusFilter === "all" ? "is-active" : ""}`}
            onClick={() => setStatusFilter("all")}
          >
            Tất cả
          </button>
          <button
            className={`cc-calendar-chip cc-calendar-chip--paid ${statusFilter === "paid" ? "is-active" : ""}`}
            onClick={() => setStatusFilter(statusFilter === "paid" ? "all" : "paid")}
          >
            <span className="cc-calendar-grid-cell-badge cc-calendar-grid-cell-badge--paid">P</span>
            Có lương
          </button>
          <button
            className={`cc-calendar-chip cc-calendar-chip--unpaid ${statusFilter === "unpaid" ? "is-active" : ""}`}
            onClick={() => setStatusFilter(statusFilter === "unpaid" ? "all" : "unpaid")}
          >
            <span className="cc-calendar-grid-cell-badge cc-calendar-grid-cell-badge--unpaid">KL</span>
            Không lương
          </button>
          <button
            className={`cc-calendar-chip cc-calendar-chip--pending ${statusFilter === "pending" ? "is-active" : ""}`}
            onClick={() => setStatusFilter(statusFilter === "pending" ? "all" : "pending")}
          >
            <span className="cc-calendar-grid-cell-dot" />
            Chờ duyệt
          </button>
        </div>
      </div>

      {/* 3. Main Leave Grid Table */}
      {!data ? (
        <div className="ns__empty cc-calendar-loading">
          <div className="cc-loading-spinner" />
          <span>Đang tải dữ liệu lịch nghỉ...</span>
        </div>
      ) : data.employees.length === 0 ? (
        <div className="ns__empty">Không có ai nghỉ trong tháng này.</div>
      ) : filteredEmployees.length === 0 ? (
        <div className="ns__empty">Không tìm thấy nhân viên nào khớp với bộ lọc.</div>
      ) : (
        <div className="cc-timesheet-scroll-container cc-calendar-scroll-wrapper">
          <table className="cc-timesheet-table cc-calendar-table">
            <thead>
              <tr className="cc-calendar-dow-row">
                <th className="cc-calendar-sticky-name">NHÂN VIÊN</th>
                {days.map((d) => {
                  const weekend = isWeekend(d);
                  const dow = getWeekday(d);
                  const isToday = isCurrentMonth && d === todayDay;
                  let thCls = "cc-day-dow";
                  if (weekend) thCls += " cc-day-cell--weekend";
                  if (isToday) thCls += " cc-day-hdr-v2--today";
                  return (
                    <th key={d} className={thCls}>
                      {dow}
                    </th>
                  );
                })}
              </tr>
              <tr>
                <th className="cc-calendar-sticky-name cc-calendar-sticky-sub">
                  <span className="cc-emp-count-badge">{filteredEmployees.length} NV</span>
                </th>
                {days.map((d) => {
                  const weekend = isWeekend(d);
                  const isToday = isCurrentMonth && d === todayDay;
                  let thCls = weekend ? "cc-day-hdr-v2 cc-day-cell--weekend" : "cc-day-hdr-v2";
                  if (isToday) thCls += " cc-day-hdr-v2--today";
                  
                  return (
                    <th key={d} className={thCls} style={{ textAlign: "center", minWidth: 32, padding: "6px 2px" }}>
                      {d}
                      {isToday && <span className="cc-today-indicator-dot" />}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {filteredEmployees.map((e) => (
                <tr key={e.employee_id} className="cc-calendar-row">
                  <td className="cc-calendar-sticky-name">
                    <div className="cc-name-cell-wrapper">
                      <span className="cc-name-avatar">{getInitials(e.employee_name)}</span>
                      <span className="cc-name-text-plain" title={e.employee_name}>
                        {e.employee_name}
                      </span>
                    </div>
                  </td>
                  {days.map((d) => {
                    const cell = e.days[String(d)];
                    const weekend = isWeekend(d);
                    const isToday = isCurrentMonth && d === todayDay;

                    // Check neighbor cells for continuous span styling
                    const prevCell = e.days[String(d - 1)];
                    const nextCell = e.days[String(d + 1)];
                    const isSpanStart = cell && (!prevCell || prevCell.leave_type_name !== cell.leave_type_name);
                    const isSpanEnd = cell && (!nextCell || nextCell.leave_type_name !== cell.leave_type_name);

                    let cellContent = null;
                    let cellClass = "cc-calendar-cell";
                    if (cell) {
                      cellClass += " cc-calendar-cell--has-leave";
                      if (isSpanStart) cellClass += " cc-calendar-cell--span-start";
                      if (isSpanEnd) cellClass += " cc-calendar-cell--span-end";

                      if (cell.status === "approved") {
                        const badgeClass = cell.is_paid ? "cc-calendar-grid-cell-badge--paid" : "cc-calendar-grid-cell-badge--unpaid";
                        cellContent = <span className={`cc-calendar-grid-cell-badge ${badgeClass}`}>{cell.is_paid ? "P" : "KL"}</span>;
                      } else {
                        cellContent = <span className="cc-calendar-grid-cell-dot" title="Chờ duyệt" />;
                      }
                    }
                    
                    if (weekend) {
                      cellClass += " cc-day-cell--weekend";
                    }
                    if (isToday) {
                      cellClass += " cc-day-cell--today";
                    }
                    
                    return (
                      <td key={d}
                        className={cellClass}
                        style={{ textAlign: "center", padding: "6px 2px", position: "relative" }}
                        onMouseEnter={(event) => {
                          if (cell) {
                            setHoveredCell({
                              employeeName: e.employee_name,
                              day: d,
                              leaveTypeName: cell.leave_type_name,
                              isPaid: cell.is_paid,
                              status: cell.status,
                              rect: event.currentTarget.getBoundingClientRect()
                            });
                          }
                        }}
                        onMouseLeave={() => setHoveredCell(null)}
                      >
                        {cellContent}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 4. Glassmorphic Popover Tooltip */}
      {hoveredCell && (() => {
        const tooltipWidth = 240;
        const leftPos = Math.max(16, Math.min(window.innerWidth - tooltipWidth - 16, hoveredCell.rect.left + (hoveredCell.rect.width / 2) - (tooltipWidth / 2)));
        const showAbove = hoveredCell.rect.bottom + 120 > window.innerHeight;
        const topPos = showAbove ? hoveredCell.rect.top - 120 : hoveredCell.rect.bottom + 8;
        
        return (
          <div className="cc-calendar-tooltip" style={{
            position: "fixed",
            top: topPos,
            left: leftPos,
            zIndex: 1000
          }}>
            <div className="cc-calendar-tooltip-header">
              <span className="cc-calendar-tooltip-avatar">{getInitials(hoveredCell.employeeName)}</span>
              <div>
                <span className="cc-calendar-tooltip-title">{hoveredCell.employeeName}</span>
                <span className="cc-calendar-tooltip-date">Ngày {hoveredCell.day} tháng {ym.month}/{ym.year}</span>
              </div>
            </div>
            <div className="cc-calendar-tooltip-body">
              <div className="cc-calendar-tooltip-row">
                <span className="cc-calendar-tooltip-label">Loại nghỉ</span>
                <span className="cc-calendar-tooltip-val">{hoveredCell.leaveTypeName}</span>
              </div>
              <div className="cc-calendar-tooltip-row">
                <span className="cc-calendar-tooltip-label">Chế độ lương</span>
                <span className={`cc-calendar-tooltip-val cc-calendar-tooltip-val--paid-${hoveredCell.isPaid}`}>
                  {hoveredCell.isPaid ? "Có lương (P)" : "Không lương (KL)"}
                </span>
              </div>
              <div className="cc-calendar-tooltip-row">
                <span className="cc-calendar-tooltip-label">Trạng thái</span>
                <span className={`cc-calendar-tooltip-status cc-calendar-tooltip-status--${hoveredCell.status}`}>
                  {hoveredCell.status === "approved" ? "✓ Đã duyệt" : "⏳ Chờ duyệt"}
                </span>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

// --- Tab: Loại nghỉ (HR) ----------------------------------------------------

function LeaveTypesTab({ token }: { token: string }) {
  const [items, setItems] = useState<LeaveType[] | null>(null);
  const [editing, setEditing] = useState<LeaveType | "new" | null>(null);
  const [viewMode, setViewMode] = useState<"grid" | "table">("grid");

  const load = useCallback(() => {
    api.leaves.types(token).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token]);
  useEffect(() => { load(); }, [load]);

  async function toggleActive(t: LeaveType) {
    try {
      await api.leaves.updateType(token, t.id, {
        name: t.name,
        is_paid: t.is_paid,
        annual_quota: t.annual_quota,
        note: t.note,
        is_active: !t.is_active,
      });
      load();
    } catch (e) {
      alert(errMsg(e));
    }
  }

  async function handleDelete(t: LeaveType) {
    if (!window.confirm(`Bạn có chắc chắn muốn xóa loại nghỉ "${t.name}" không?`)) return;
    try {
      await api.leaves.deleteType(token, t.id);
      load();
    } catch (e) {
      alert(errMsg(e));
    }
  }

  const totalTypes = items?.length ?? 0;
  const paidTypes = items?.filter((t) => t.is_paid).length ?? 0;
  const unpaidTypes = items?.filter((t) => !t.is_paid).length ?? 0;

  return (
    <div className="cc-leave-types-wrapper">
      {/* 1. Header Toolbar & Quick Stats */}
      <div className="cc-calendar-dashboard" style={{ marginBottom: 20 }}>
        <div className="cc-calendar-stats-strip">
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--users"><Layers size={16} /></span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{totalTypes}</span>
              <span className="cc-calendar-stat-label">Loại nghỉ</span>
            </div>
          </div>
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--check"><CheckCircle2 size={16} /></span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{paidTypes}</span>
              <span className="cc-calendar-stat-label">Có lương P</span>
            </div>
          </div>
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--clock"><ShieldCheck size={16} /></span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{unpaidTypes}</span>
              <span className="cc-calendar-stat-label">Không lương</span>
            </div>
          </div>
        </div>

        <div className="cc-leave-types-toolbar-right">
          <div className="cc-view-toggle">
            <button
              className={`cc-view-toggle-btn ${viewMode === "grid" ? "is-active" : ""}`}
              onClick={() => setViewMode("grid")}
              title="Xem dạng thẻ"
            >
              <LayoutGrid size={15} />
            </button>
            <button
              className={`cc-view-toggle-btn ${viewMode === "table" ? "is-active" : ""}`}
              onClick={() => setViewMode("table")}
              title="Xem dạng bảng"
            >
              <List size={15} />
            </button>
          </div>

          <button className="btn btn--primary cc-btn-cta-compact" onClick={() => setEditing("new")}>
            <Plus size={16} />
            <span>Thêm loại nghỉ mới</span>
          </button>
        </div>
      </div>

      {/* 2. Main Content Display */}
      {items === null ? (
        <div className="ns__empty cc-calendar-loading">
          <div className="cc-loading-spinner" />
          <span>Đang tải loại nghỉ...</span>
        </div>
      ) : items.length === 0 ? (
        <div className="ns__empty" style={{ padding: 40 }}>
          Chưa khai loại nghỉ nào. Bấm "+ Thêm loại nghỉ mới" để khởi tạo.
        </div>
      ) : viewMode === "grid" ? (
        /* GRID VIEW (FEATURE CARDS) */
        <div className="cc-leave-types-grid">
          {items.map((t) => {
            return (
              <div key={t.id} className={`cc-leave-type-card ${!t.is_active ? "is-inactive" : ""}`}>
                <div className="cc-leave-type-card-head">
                  <div className="cc-leave-type-title-group">
                    <h3 className="cc-leave-type-card-name" title={t.name}>{t.name}</h3>
                    <div className="cc-leave-type-badges-row">
                      {t.is_paid ? (
                        <span className="cc-type-badge cc-type-badge--paid">
                          Có lương
                        </span>
                      ) : (
                        <span className="cc-type-badge cc-type-badge--unpaid">
                          Không lương
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="cc-leave-type-active-switch">
                    <label className="cc-switch" title={t.is_active ? "Đang sử dụng (Click để tắt)" : "Đã tắt (Click để bật)"}>
                      <input type="checkbox" checked={t.is_active} onChange={() => toggleActive(t)} />
                      <span className="cc-slider" />
                    </label>
                  </div>
                </div>

                <div className="cc-leave-type-card-body">
                  <div className="cc-leave-type-info-row">
                    <span className="cc-leave-type-info-label">Hạn mức/năm:</span>
                    <span className="cc-leave-type-info-val">
                      {t.annual_quota > 0 ? (
                        <span className="cc-quota-badge-val">{t.annual_quota} ngày</span>
                      ) : (
                        <span className="cc-quota-badge-val cc-quota-badge-val--unlimited">Theo đơn xin</span>
                      )}
                    </span>
                  </div>
                  {t.note && (
                    <p className="cc-leave-type-note-text" title={t.note}>
                      {t.note}
                    </p>
                  )}
                </div>

                <div className="cc-leave-type-card-foot">
                  <button className="cc-leave-type-action-btn" onClick={() => setEditing(t)}>
                    <Edit3 size={13} />
                    <span>Sửa</span>
                  </button>
                  <button className="cc-leave-type-action-btn cc-leave-type-action-btn--danger" onClick={() => handleDelete(t)}>
                    <Trash2 size={13} />
                    <span>Xóa</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* TABLE VIEW */
        <div className="cc-timesheet-scroll-container cc-calendar-scroll-wrapper">
          <table className="cc-timesheet-table">
            <thead>
              <tr>
                <th>Tên loại nghỉ</th>
                <th style={{ textAlign: "center" }}>Chế độ lương</th>
                <th style={{ textAlign: "center" }}>Hạn mức hàng năm</th>
                <th style={{ textAlign: "center" }}>Trạng thái</th>
                <th style={{ textAlign: "center" }}>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => {
                return (
                  <tr key={t.id} className={!t.is_active ? "is-inactive-row" : ""}>
                    <td style={{ fontWeight: "bold", color: "var(--ink)" }}>
                      <span>{t.name}</span>
                    </td>
                    <td style={{ textAlign: "center" }}>
                      {t.is_paid ? (
                        <span className="cc-type-badge cc-type-badge--paid">
                          Có lương
                        </span>
                      ) : (
                        <span className="cc-type-badge cc-type-badge--unpaid">
                          Không lương
                        </span>
                      )}
                    </td>
                    <td style={{ textAlign: "center", fontWeight: "bold" }}>
                      {t.annual_quota > 0 ? `${t.annual_quota} ngày/năm` : "Theo đơn xin"}
                    </td>
                    <td style={{ textAlign: "center" }}>
                      <label className="cc-switch" title={t.is_active ? "Đang sử dụng" : "Đã tắt"}>
                        <input type="checkbox" checked={t.is_active} onChange={() => toggleActive(t)} />
                        <span className="cc-slider" />
                      </label>
                    </td>
                    <td style={{ textAlign: "center" }}>
                      <div className="cc-approve-actions-cell" style={{ justifyContent: "center" }}>
                        <button className="btn btn--ghost" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => setEditing(t)}>Sửa</button>
                        <button className="btn btn--ghost cc-btn-reject" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => handleDelete(t)}>Xóa</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <LeaveTypeForm
          token={token}
          type={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </div>
  );
}

function LeaveTypeForm({ token, type, onClose, onSaved }: {
  token: string; type: LeaveType | null; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<LeaveTypeInput>({
    name: type?.name ?? "", is_paid: type?.is_paid ?? true, annual_quota: type?.annual_quota ?? 0,
    note: type?.note ?? "", is_active: type?.is_active ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof LeaveTypeInput>(k: K, v: LeaveTypeInput[K]) { setForm((f) => ({ ...f, [k]: v })); }

  async function save() {
    setBusy(true); setError(null);
    try {
      if (!form.name.trim()) throw new ApiError("Vui lòng nhập tên loại nghỉ.", 400);
      if (type) await api.leaves.updateType(token, type.id, form);
      else await api.leaves.createType(token, form);
      onSaved();
    } catch (e) { setError(errMsg(e)); setBusy(false); }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <div className="cc-modal-title-group">
            <h2>{type ? "Chỉnh sửa loại nghỉ phép" : "Tạo loại nghỉ phép mới"}</h2>
            <p className="cc-modal-subtitle">Cấu hình chế độ lương và hạn mức nghỉ phép hàng năm</p>
          </div>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body cc-day-detail-modal-body">
          {error && <div className="banner banner--error cc-ts-msg-banner" style={{ marginBottom: "16px" }}>{error}</div>}
          
          <label className="ns-field">
            <span className="cc-field-label">Tên loại nghỉ phép *</span>
            <input className="cc-input-text" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="vd: Phép năm, Nghỉ ốm, Việc riêng..." />
          </label>
          
          <div className="ns-grid" style={{ marginTop: 14 }}>
            <label className="ns-field">
              <span className="cc-field-label">Hạn mức / năm (số ngày)</span>
              <input type="number" className="cc-input-text" min={0} value={form.annual_quota} onChange={(e) => set("annual_quota", Number(e.target.value))} placeholder="0 = Không giới hạn" />
              <span className="cc-field-subtext">Nhập 0 nếu không áp dụng hạn mức năm (cho nghỉ không lương / ốm)</span>
            </label>
          </div>
          
          <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 14 }}>
            <label className="ns-check" style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
              <input type="checkbox" checked={!!form.is_paid} onChange={(e) => set("is_paid", e.target.checked)} /> 
              <div>
                <span className="cc-field-label" style={{ margin: 0 }}>Hưởng nguyên lương (Tính công P)</span>
                <span className="cc-field-subtext" style={{ display: "block" }}>Đơn nghỉ loại này được duyệt sẽ tự động chấm công ký hiệu P trên Bảng công tháng.</span>
              </div>
            </label>

            <label className="ns-check" style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
              <input type="checkbox" checked={!!form.is_active} onChange={(e) => set("is_active", e.target.checked)} /> 
              <div>
                <span className="cc-field-label" style={{ margin: 0 }}>Đang sử dụng loại nghỉ này</span>
                <span className="cc-field-subtext" style={{ display: "block" }}>Cho phép nhân viên chọn loại nghỉ này khi tạo đơn xin nghỉ mới.</span>
              </div>
            </label>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>{busy ? "Đang lưu…" : "Lưu cấu hình"}</button>
        </footer>
      </div>
    </div>
  );
}

// --- Shared table -----------------------------------------------------------

function LeaveTable({ items, showEmployee, onCancel, onApprove, onReject,
  selectable, selected, onToggle, onToggleAll, allPendingCount, onRowClick }: {
  items: LeaveRequest[]; showEmployee: boolean;
  onCancel?: (id: number) => void; onApprove?: (id: number) => void; onReject?: (r: LeaveRequest) => void;
  selectable?: boolean; selected?: Set<number>; onToggle?: (id: number) => void;
  onToggleAll?: () => void; allPendingCount?: number;
  onRowClick?: (r: LeaveRequest) => void;
}) {
  const allChecked = !!allPendingCount && selected?.size === allPendingCount;
  const cols = (showEmployee ? 8 : 7) + (selectable ? 1 : 0);
  return (
    <div className="cc-table-card">
      <div className="cc-timesheet-scroll-container">
        <table className="cc-timesheet-table cc-leave-table">
          <thead>
            <tr>
              {selectable && <th style={{ width: 36, textAlign: "center" }}><input type="checkbox" checked={allChecked} onChange={onToggleAll} title="Chọn tất cả đơn chờ" /></th>}
              {showEmployee && <th>Nhân viên</th>}
              <th>Loại nghỉ</th>
              <th>Từ ngày</th>
              <th>Đến ngày</th>
              <th style={{ textAlign: "center" }}>Số ngày</th>
              <th>Lý do</th>
              <th style={{ textAlign: "center" }}>Trạng thái</th>
              <th style={{ textAlign: "center" }}>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id} onClick={() => onRowClick?.(r)} className="cc-leave-table-row">
                {selectable && (
                  <td style={{ textAlign: "center" }} onClick={(e) => e.stopPropagation()}>
                    {r.status === "pending" && <input type="checkbox" checked={selected?.has(r.id) ?? false} onChange={() => onToggle?.(r.id)} />}
                  </td>
                )}
                {showEmployee && (
                  <td>
                    <div className="cc-name-cell-wrapper">
                      <span className="cc-name-avatar">{getInitials(r.employee_name)}</span>
                      <span className="cc-name-text-plain" title={r.employee_name ?? `NV#${r.employee_id}`}>
                        {r.employee_name ?? `NV#${r.employee_id}`}
                      </span>
                    </div>
                  </td>
                )}
                <td>
                  <div className="cc-leave-type-cell">
                    <span className="cc-leave-type-name">{r.leave_type_name ?? "—"}</span>
                    {r.is_paid === false ? (
                      <span className="cc-type-badge cc-type-badge--unpaid">Không lương</span>
                    ) : (
                      <span className="cc-type-badge cc-type-badge--paid">Có lương</span>
                    )}
                  </div>
                </td>
                <td className="cc-date-cell">{fmtDate(r.start_date)}</td>
                <td className="cc-date-cell">{fmtDate(r.end_date)}</td>
                <td style={{ textAlign: "center" }}>
                  <span className="cc-days-pill">{r.days} ngày</span>
                </td>
                <td>
                  <div className="cc-reason-wrapper">
                    <span className="cc-reason-text">{r.reason || "—"}</span>
                    {r.decision_note && (
                      <div className="cc-decision-note-sub">
                        💬 {r.decision_note}
                      </div>
                    )}
                  </div>
                </td>
                <td style={{ textAlign: "center" }}><StatusBadge s={r.status} /></td>
                <td style={{ textAlign: "center" }} onClick={(e) => e.stopPropagation()}>
                  <div className="cc-approve-actions-cell" style={{ justifyContent: "center" }}>
                    {onApprove && r.status === "pending" && <button className="btn btn--primary cc-btn-approve-sm" onClick={() => onApprove(r.id)}>Duyệt</button>}
                    {onReject && r.status === "pending" && <button className="btn btn--ghost cc-btn-reject-sm" onClick={() => onReject(r)}>Từ chối</button>}
                    {onCancel && (r.status === "pending" || r.status === "approved") && <button className="btn btn--ghost cc-btn-cancel-sm" onClick={() => onCancel(r.id)}>Hủy</button>}
                  </div>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={cols} className="ns__empty" style={{ padding: "32px 16px", textAlign: "center", color: "#64748b" }}>
                  Chưa có đơn xin nghỉ phép nào.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
