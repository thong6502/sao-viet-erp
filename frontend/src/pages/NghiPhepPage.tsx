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
import { AlertTriangle, Search, ChevronLeft, ChevronRight, Users, Clock } from "lucide-react";
import "./nhan-su.css";
import "./cham-cong.css";
import "./nghi-phep.css";

type Tab = "me" | "approve" | "calendar" | "types";

const STATUS_LABEL: Record<string, string> = {
  pending: "Chờ duyệt", approved: "Đã duyệt", rejected: "Từ chối", cancelled: "Đã hủy",
};
const STATUS_CLASS: Record<string, string> = {
  pending: "cc-badge-status--pending",
  approved: "cc-badge-status--approved",
  rejected: "cc-badge-status--rejected",
  cancelled: "cc-badge-status--cancelled",
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
  return <span className={`cc-badge-status ${STATUS_CLASS[s] ?? "cc-badge-status--cancelled"}`}>{STATUS_LABEL[s] ?? s}</span>;
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
  // Quyền DUYỆT (leave admin) — tách khỏi nhan_su.update; chỉ HCNS/Admin có.
  const canManage = can("nghi_phep", "approve");
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
      <nav className="ns-tabs cc-tabs">
        <button className={tab === "me" ? "is-active" : ""} onClick={() => setTab("me")}>Đơn của tôi</button>
        {canManage && <button className={tab === "approve" ? "is-active" : ""} onClick={() => setTab("approve")}>Duyệt đơn</button>}
        {canManage && <button className={tab === "calendar" ? "is-active" : ""} onClick={() => setTab("calendar")}>Lịch nghỉ</button>}
        {canManage && <button className={tab === "types" ? "is-active" : ""} onClick={() => setTab("types")}>Loại nghỉ</button>}
      </nav>
      {tab === "me" && <MyLeaveTab token={token!} onChanged={onChanged} />}
      {tab === "approve" && canManage && <ApproveTab token={token!} onChanged={onChanged} focusEmployeeId={focusEmployeeId} />}
      {tab === "calendar" && canManage && <CalendarTab token={token!} />}
      {tab === "types" && canManage && <LeaveTypesTab token={token!} />}
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
              <input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
            </label>
            <label className="ns-field">
              <span className="cc-field-label">Đến ngày *</span>
              <input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
            </label>
          </div>
          
          <label className="ns-field" style={{ marginTop: 14 }}>
            <span className="cc-field-label">Lý do xin nghỉ</span>
            <input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="vd: Về quê, khám bệnh…" />
          </label>
          
          <div className="cc-info-card-note" style={{ marginTop: 16 }}>
            <AlertTriangle size={14} className="cc-note-icon" />
            <span>Cuối tuần (T7/CN) không trừ vào phép năm. Đơn xin nghỉ phép năm sẽ bị chặn khi vượt quá số ngày phép còn lại.</span>
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
        <div className="cc-quota-container">
          <div className="cc-quota-list">
            {quotas.map((q) => {
              const isLow = q.remaining <= 0;
              const isMedium = q.remaining > 0 && q.remaining <= 2;
              const quotaClass = isLow ? "cc-quota-card--low" : isMedium ? "cc-quota-card--medium" : "cc-quota-card--high";
              return (
                <div key={q.leave_type_id} className={`cc-quota-card ${quotaClass}`}>
                  <div className="cc-quota-card-title">{q.name}</div>
                  <div className="cc-quota-card-val">
                    còn {q.remaining}
                    <span className="cc-quota-card-total"> / {q.annual_quota} ngày</span>
                  </div>
                  <div className="cc-quota-card-used">đã dùng {q.used} ngày làm việc</div>
                </div>
              );
            })}
          </div>
          <div className="cc-quota-actions">
            <button className="btn btn--primary" onClick={() => { setIsCreateOpen(true); setError(null); }}>+ Xin nghỉ phép</button>
            <span className="cc-note" style={{ margin: 0 }}>Nhấn vào dòng bản ghi đơn để xem tiến trình chi tiết.</span>
          </div>
        </div>
      ) : (
        <div className="cc-ts-toolbar" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <button className="btn btn--primary" onClick={() => { setIsCreateOpen(true); setError(null); }}>+ Xin nghỉ phép</button>
          <span className="cc-note" style={{ margin: 0 }}>Nhấn vào dòng bản ghi đơn để xem tiến trình chi tiết.</span>
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

function CalendarTab({ token }: { token: string }) {
  const now = new Date();
  const [ym, setYm] = useState<{ year: number; month: number }>({ year: now.getFullYear(), month: now.getMonth() + 1 });
  const [data, setData] = useState<LeaveCalendar | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
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

  const days = data ? Array.from({ length: data.days_in_month }, (_, i) => i + 1) : [];
  const isWeekend = (d: number) => { const wd = new Date(ym.year, ym.month - 1, d).getDay(); return wd === 0 || wd === 6; };

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

  // Filtering
  const filteredEmployees = data
    ? data.employees.filter(e => e.employee_name.toLowerCase().includes(searchQuery.toLowerCase()))
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
        </div>
      </div>

      {/* 2. Month Navigation & Legend Header */}
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
              Tháng {ym.month} / {ym.year}
            </label>
          </div>
          
          <button className="cc-calendar-month-btn" onClick={() => shift(1)} title="Tháng sau">
            <ChevronRight size={16} />
          </button>
        </div>

        <div className="cc-calendar-legends">
          <span className="cc-calendar-legend-item">
            <span className="cc-calendar-grid-cell-badge cc-calendar-grid-cell-badge--paid">P</span>
            <span>Có lương</span>
          </span>
          <span className="cc-calendar-legend-item">
            <span className="cc-calendar-grid-cell-badge cc-calendar-grid-cell-badge--unpaid">KL</span>
            <span>Không lương</span>
          </span>
          <span className="cc-calendar-legend-item">
            <span className="cc-calendar-grid-cell-dot" />
            <span>Chờ duyệt</span>
          </span>
        </div>
      </div>

      {/* 3. Main Leave Grid Table */}
      {!data ? (
        <p className="ns__empty">Đang tải...</p>
      ) : data.employees.length === 0 ? (
        <div className="ns__empty">Không có ai nghỉ trong tháng này.</div>
      ) : filteredEmployees.length === 0 ? (
        <div className="ns__empty">Không tìm thấy nhân viên nào khớp với từ khóa tìm kiếm.</div>
      ) : (
        <div className="cc-timesheet-scroll-container">
          <table className="cc-timesheet-table cc-calendar-table">
            <thead>
              <tr>
                <th className="cc-calendar-sticky-name">Nhân viên</th>
                {days.map((d) => {
                  const weekend = isWeekend(d);
                  const isToday = isCurrentMonth && d === todayDay;
                  let thCls = weekend ? "cc-day-hdr-v2 cc-day-cell--weekend" : "cc-day-hdr-v2";
                  if (isToday) thCls += " cc-day-hdr-v2--today";
                  
                  return (
                    <th key={d} className={thCls} style={{ textAlign: "center", minWidth: 28, padding: "8px 2px" }}>
                      {d}
                      {isToday && <span className="cc-today-indicator-dot" />}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {filteredEmployees.map((e) => (
                <tr key={e.employee_id}>
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
                    
                    let cellContent = null;
                    let cellClass = "";
                    if (cell) {
                      if (cell.status === "approved") {
                        const badgeClass = cell.is_paid ? "cc-calendar-grid-cell-badge--paid" : "cc-calendar-grid-cell-badge--unpaid";
                        cellContent = <span className={`cc-calendar-grid-cell-badge ${badgeClass}`}>{cell.is_paid ? "P" : "KL"}</span>;
                      } else {
                        cellContent = <span className="cc-calendar-grid-cell-dot" />;
                      }
                    }
                    
                    if (weekend) {
                      cellClass = "cc-day-cell--weekend";
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

      {/* 4. Interactive Live Tooltip */}
      {hoveredCell && (() => {
        const tooltipWidth = 230;
        const leftPos = Math.max(16, Math.min(window.innerWidth - tooltipWidth - 16, hoveredCell.rect.left + (hoveredCell.rect.width / 2) - (tooltipWidth / 2)));
        const showAbove = hoveredCell.rect.bottom + 110 > window.innerHeight;
        const topPos = showAbove ? hoveredCell.rect.top - 110 : hoveredCell.rect.bottom + 6;
        
        return (
          <div className="cc-calendar-tooltip" style={{
            position: "fixed",
            top: topPos,
            left: leftPos,
            zIndex: 1000
          }}>
            <div className="cc-calendar-tooltip-header">
              <span className="cc-calendar-tooltip-title">{hoveredCell.employeeName}</span>
              <span className="cc-calendar-tooltip-date">Ngày {hoveredCell.day} thg {ym.month}</span>
            </div>
            <div className="cc-calendar-tooltip-body">
              <div className="cc-calendar-tooltip-row">
                <span className="cc-calendar-tooltip-label">Loại nghỉ:</span>
                <span className="cc-calendar-tooltip-val">{hoveredCell.leaveTypeName}</span>
              </div>
              <div className="cc-calendar-tooltip-row">
                <span className="cc-calendar-tooltip-label">Chế độ:</span>
                <span className={`cc-calendar-tooltip-val cc-calendar-tooltip-val--paid-${hoveredCell.isPaid}`}>
                  {hoveredCell.isPaid ? "Có lương (P)" : "Không lương (KL)"}
                </span>
              </div>
              <div className="cc-calendar-tooltip-row">
                <span className="cc-calendar-tooltip-label">Trạng thái:</span>
                <span className={`cc-calendar-tooltip-status cc-calendar-tooltip-status--${hoveredCell.status}`}>
                  {hoveredCell.status === "approved" ? "Đã duyệt" : "Chờ duyệt"}
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
  const load = useCallback(() => {
    api.leaves.types(token).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token]);
  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <div className="cc-ts-toolbar">
        <button className="btn btn--primary" onClick={() => setEditing("new")}>+ Thêm loại nghỉ</button>
      </div>
      <div className="cc-timesheet-scroll-container">
        <table className="cc-timesheet-table">
          <thead>
            <tr>
              <th>Tên loại nghỉ</th>
              <th style={{ textAlign: "center" }}>Lương</th>
              <th style={{ textAlign: "center" }}>Hạn mức/năm</th>
              <th style={{ textAlign: "center" }}>Trạng thái</th>
              <th style={{ textAlign: "center" }}>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {items?.map((t) => (
              <tr key={t.id}>
                <td style={{ fontWeight: "bold", color: "var(--ink)" }}>{t.name}</td>
                <td style={{ textAlign: "center" }}>
                  {t.is_paid ? (
                    <span className="cc-cell-badge cc-cell-badge--work">Có lương</span>
                  ) : (
                    <span className="cc-cell-badge cc-cell-badge--leave">Không lương</span>
                  )}
                </td>
                <td style={{ textAlign: "center", fontFamily: "var(--ff-mono)", fontWeight: "bold" }}>
                  {t.annual_quota > 0 ? `${t.annual_quota} ngày` : "—"}
                </td>
                <td style={{ textAlign: "center" }}>
                  <span className={`cc-badge-status ${t.is_active ? "cc-badge-status--approved" : "cc-badge-status--cancelled"}`}>
                    {t.is_active ? "Đang dùng" : "Tắt"}
                  </span>
                </td>
                <td style={{ textAlign: "center" }}>
                  <div className="cc-approve-actions-cell" style={{ justifyContent: "center" }}>
                    <button className="btn btn--ghost" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => setEditing(t)}>Sửa</button>
                    <button className="btn btn--ghost cc-btn-reject" style={{ padding: "4px 10px", fontSize: 12 }} onClick={async () => { await api.leaves.deleteType(token, t.id); load(); }}>Xóa</button>
                  </div>
                </td>
              </tr>
            ))}
            {items?.length === 0 && <tr><td colSpan={5} className="ns__empty" style={{ padding: 24, textAlign: "center" }}>Chưa khai loại nghỉ nào.</td></tr>}
          </tbody>
        </table>
      </div>
      {editing && <LeaveTypeForm token={token} type={editing === "new" ? null : editing}
        onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
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
            <h2>{type ? "Sửa loại nghỉ" : "Thêm loại nghỉ mới"}</h2>
          </div>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body cc-day-detail-modal-body">
          {error && <div className="banner banner--error cc-ts-msg-banner" style={{ marginBottom: "16px" }}>{error}</div>}
          
          <label className="ns-field">
            <span className="cc-field-label">Tên loại nghỉ *</span>
            <input className="cc-input-text" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Phép năm / Nghỉ ốm…" />
          </label>
          
          <div className="ns-grid" style={{ marginTop: 14 }}>
            <label className="ns-field">
              <span className="cc-field-label">Hạn mức/năm (ngày)</span>
              <input type="number" className="cc-input-text" min={0} value={form.annual_quota} onChange={(e) => set("annual_quota", Number(e.target.value))} />
            </label>
          </div>
          
          <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 10 }}>
            <label className="ns-check" style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input type="checkbox" checked={!!form.is_paid} onChange={(e) => set("is_paid", e.target.checked)} /> 
              <span className="cc-field-label" style={{ margin: 0, fontWeight: "normal" }}>Có lương (tính công "P")</span>
            </label>
            <label className="ns-check" style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input type="checkbox" checked={!!form.is_active} onChange={(e) => set("is_active", e.target.checked)} /> 
              <span className="cc-field-label" style={{ margin: 0, fontWeight: "normal" }}>Đang sử dụng loại nghỉ này</span>
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
    <div className="cc-timesheet-scroll-container">
      <table className="cc-timesheet-table">
        <thead>
          <tr>
            {selectable && <th style={{ width: 32, textAlign: "center" }}><input type="checkbox" checked={allChecked} onChange={onToggleAll} title="Chọn tất cả đơn chờ" /></th>}
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
            <tr key={r.id} onClick={() => onRowClick?.(r)} style={{ cursor: onRowClick ? "pointer" : "default" }}>
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
                <span className="cc-reason-text" style={{ fontWeight: "bold" }}>
                  {r.leave_type_name ?? "—"}
                </span>
                {r.is_paid === false && <span className="cc-decision-note-sub" style={{ marginLeft: 6 }}>KL</span>}
              </td>
              <td>{fmtDate(r.start_date)}</td>
              <td>{fmtDate(r.end_date)}</td>
              <td style={{ textAlign: "center", fontFamily: "var(--ff-mono)", fontWeight: "bold" }}>{r.days}</td>
              <td>
                <div className="cc-reason-wrapper">
                  <span className="cc-reason-text">{r.reason ?? "—"}</span>
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
                  {onApprove && r.status === "pending" && <button className="btn btn--primary cc-btn-approve" onClick={() => onApprove(r.id)}>Duyệt</button>}
                  {onReject && r.status === "pending" && <button className="btn btn--ghost cc-btn-reject" onClick={() => onReject(r)}>Từ chối</button>}
                  {onCancel && (r.status === "pending" || r.status === "approved") && <button className="btn btn--ghost cc-btn-reject" onClick={() => onCancel(r.id)}>Hủy</button>}
                </div>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={cols} className="ns__empty" style={{ padding: "24px", textAlign: "center" }}>
                Chưa có đơn xin nghỉ phép nào.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
