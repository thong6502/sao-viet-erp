// Nghỉ phép (module `nhan_su`). 3 tab:
//   • Đơn của tôi — NV tạo đơn xin nghỉ + xem/hủy đơn của mình (self-service).
//   • Duyệt đơn (HR) — chờ duyệt → duyệt / từ chối; xem toàn bộ.
//   • Loại nghỉ (HR) — khai loại nghỉ (có lương / hạn mức).
import { useCallback, useEffect, useState } from "react";
import {
  api,
  ApiError,
  type LeaveRequest,
  type LeaveType,
  type LeaveTypeInput,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import "./nhan-su.css";
import "./cham-cong.css";

type Tab = "me" | "approve" | "types";

const STATUS_LABEL: Record<string, string> = {
  pending: "Chờ duyệt", approved: "Đã duyệt", rejected: "Từ chối", cancelled: "Đã hủy",
};
const STATUS_CLASS: Record<string, string> = {
  pending: "ns-badge--warn", approved: "ns-badge--ok", rejected: "ns-badge--danger", cancelled: "ns-badge--muted",
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
  return <span className={`ns-badge ${STATUS_CLASS[s] ?? "ns-badge--muted"}`}>{STATUS_LABEL[s] ?? s}</span>;
}

export function NghiPhepPage() {
  const { token } = useAuth();
  const can = useCan();
  const canManage = can("nhan_su", "update");
  const [tab, setTab] = useState<Tab>("me");

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
        {canManage && <button className={tab === "types" ? "is-active" : ""} onClick={() => setTab("types")}>Loại nghỉ</button>}
      </nav>
      {tab === "me" && <MyLeaveTab token={token!} />}
      {tab === "approve" && canManage && <ApproveTab token={token!} />}
      {tab === "types" && canManage && <LeaveTypesTab token={token!} />}
    </main>
  );
}

// --- Tab: Đơn của tôi -------------------------------------------------------

function MyLeaveTab({ token }: { token: string }) {
  const [hasEmp, setHasEmp] = useState<boolean | null>(null);
  const [items, setItems] = useState<LeaveRequest[]>([]);
  const [types, setTypes] = useState<LeaveType[]>([]);
  const [form, setForm] = useState({ leave_type_id: "" as number | "", start_date: "", end_date: "", reason: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.leaves.me(token).then((r) => { setHasEmp(r.has_employee); setItems(r.items); }).catch(() => setHasEmp(false));
  }, [token]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.leaves.types(token).then((r) => setTypes(r.items.filter((t) => t.is_active))).catch(() => {}); }, [token]);

  async function submit() {
    setBusy(true); setError(null);
    try {
      if (form.leave_type_id === "") throw new ApiError("Chọn loại nghỉ.", 400);
      await api.leaves.create(token, {
        leave_type_id: form.leave_type_id, start_date: form.start_date, end_date: form.end_date, reason: form.reason || null,
      });
      setForm({ leave_type_id: "", start_date: "", end_date: "", reason: "" });
      load();
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  }
  async function cancel(id: number) {
    await api.leaves.cancel(token, id);
    load();
  }

  if (hasEmp === false) {
    return <div className="banner banner--warn" style={{ marginTop: 12 }}>
      Tài khoản của bạn <strong>chưa gắn hồ sơ nhân viên</strong> nên không tạo đơn nghỉ được. Liên hệ HCNS.
    </div>;
  }
  return (
    <div className="cc-grid">
      <div className="cc-card" style={{ textAlign: "left" }}>
        <h4 className="ns-section__title">Tạo đơn xin nghỉ</h4>
        {error && <div className="banner banner--error">{error}</div>}
        <label className="ns-field"><span className="ns-field__label">Loại nghỉ *</span>
          <select value={form.leave_type_id} onChange={(e) => setForm({ ...form, leave_type_id: e.target.value === "" ? "" : Number(e.target.value) })}>
            <option value="">— chọn —</option>
            {types.map((t) => <option key={t.id} value={t.id}>{t.name}{t.is_paid ? " (có lương)" : " (không lương)"}</option>)}
          </select>
        </label>
        <div className="ns-grid" style={{ marginTop: 10 }}>
          <label className="ns-field"><span className="ns-field__label">Từ ngày *</span>
            <input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></label>
          <label className="ns-field"><span className="ns-field__label">Đến ngày *</span>
            <input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></label>
        </div>
        <label className="ns-field" style={{ marginTop: 10 }}><span className="ns-field__label">Lý do</span>
          <input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></label>
        <button className="btn btn--primary" style={{ marginTop: 12 }} onClick={submit} disabled={busy}>{busy ? "Đang gửi…" : "Gửi đơn"}</button>
      </div>
      <div className="cc-logs">
        <h4 className="ns-section__title">Đơn của tôi</h4>
        <LeaveTable items={items} showEmployee={false} onCancel={cancel} />
      </div>
    </div>
  );
}

// --- Tab: Duyệt đơn (HR) ----------------------------------------------------

function ApproveTab({ token }: { token: string }) {
  const [status, setStatus] = useState("pending");
  const [items, setItems] = useState<LeaveRequest[]>([]);
  const load = useCallback(() => {
    api.leaves.list(token, status || undefined).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token, status]);
  useEffect(() => { load(); }, [load]);

  async function approve(id: number) { await api.leaves.approve(token, id); load(); }
  async function reject(id: number) {
    const note = window.prompt("Lý do từ chối:");
    if (note == null || !note.trim()) return;
    await api.leaves.reject(token, id, note.trim());
    load();
  }

  return (
    <div>
      <div className="cc-toolbar">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="pending">Chờ duyệt</option>
          <option value="approved">Đã duyệt</option>
          <option value="rejected">Từ chối</option>
          <option value="">Tất cả</option>
        </select>
      </div>
      <LeaveTable items={items} showEmployee onApprove={approve} onReject={reject} />
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
      <div className="cc-toolbar"><button className="btn btn--primary" onClick={() => setEditing("new")}>+ Thêm loại nghỉ</button></div>
      <div className="ns__tablewrap">
        <table className="ns__table">
          <thead><tr><th>Tên</th><th>Lương</th><th>Hạn mức/năm</th><th>Trạng thái</th><th></th></tr></thead>
          <tbody>
            {items?.map((t) => (
              <tr key={t.id}>
                <td>{t.name}</td>
                <td>{t.is_paid ? <span className="ns-badge ns-badge--ok">Có lương</span> : <span className="ns-badge ns-badge--muted">Không lương</span>}</td>
                <td>{t.annual_quota > 0 ? `${t.annual_quota} ngày` : "—"}</td>
                <td>{t.is_active ? "Đang dùng" : "Tắt"}</td>
                <td className="cc-rowact">
                  <button className="btn btn--ghost" onClick={() => setEditing(t)}>Sửa</button>
                  <button className="btn btn--ghost ns-danger" onClick={async () => { await api.leaves.deleteType(token, t.id); load(); }}>Xóa</button>
                </td>
              </tr>
            ))}
            {items?.length === 0 && <tr><td colSpan={5} className="ns__empty">Chưa khai loại nghỉ nào.</td></tr>}
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
      <div className="ns-modal__box">
        <header className="ns-modal__head"><h2>{type ? "Sửa loại nghỉ" : "Thêm loại nghỉ"}</h2><button className="ns-modal__x" onClick={onClose}>×</button></header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}
          <label className="ns-field"><span className="ns-field__label">Tên loại *</span>
            <input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Phép năm / Nghỉ ốm…" /></label>
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field"><span className="ns-field__label">Hạn mức/năm (ngày)</span>
              <input type="number" min={0} value={form.annual_quota} onChange={(e) => set("annual_quota", Number(e.target.value))} /></label>
          </div>
          <label className="ns-check" style={{ marginTop: 12 }}><input type="checkbox" checked={!!form.is_paid} onChange={(e) => set("is_paid", e.target.checked)} /> Có lương (tính công "P")</label>
          <label className="ns-check"><input type="checkbox" checked={!!form.is_active} onChange={(e) => set("is_active", e.target.checked)} /> Đang dùng</label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>{busy ? "Đang lưu…" : "Lưu"}</button>
        </footer>
      </div>
    </div>
  );
}

// --- Shared table -----------------------------------------------------------

function LeaveTable({ items, showEmployee, onCancel, onApprove, onReject }: {
  items: LeaveRequest[]; showEmployee: boolean;
  onCancel?: (id: number) => void; onApprove?: (id: number) => void; onReject?: (id: number) => void;
}) {
  return (
    <div className="ns__tablewrap">
      <table className="ns__table">
        <thead>
          <tr>
            {showEmployee && <th>Nhân viên</th>}
            <th>Loại</th><th>Từ</th><th>Đến</th><th>Số ngày</th><th>Lý do</th><th>Trạng thái</th><th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.id}>
              {showEmployee && <td>{r.employee_name ?? `NV#${r.employee_id}`}</td>}
              <td>{r.leave_type_name ?? "—"}{r.is_paid === false ? " (KL)" : ""}</td>
              <td>{fmtDate(r.start_date)}</td><td>{fmtDate(r.end_date)}</td>
              <td>{r.days}</td>
              <td title={r.decision_note ?? ""}>{r.reason ?? "—"}</td>
              <td><StatusBadge s={r.status} /></td>
              <td className="cc-rowact">
                {onApprove && r.status === "pending" && <button className="btn btn--ghost" onClick={() => onApprove(r.id)}>Duyệt</button>}
                {onReject && r.status === "pending" && <button className="btn btn--ghost ns-danger" onClick={() => onReject(r.id)}>Từ chối</button>}
                {onCancel && (r.status === "pending" || r.status === "approved") && <button className="btn btn--ghost" onClick={() => onCancel(r.id)}>Hủy</button>}
              </td>
            </tr>
          ))}
          {items.length === 0 && <tr><td colSpan={showEmployee ? 8 : 7} className="ns__empty">Chưa có đơn nào.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
