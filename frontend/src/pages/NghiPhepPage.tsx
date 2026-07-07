// Nghỉ phép (module `nhan_su`). 3 tab:
//   • Đơn của tôi — NV tạo đơn xin nghỉ + xem/hủy đơn của mình (self-service).
//   • Duyệt đơn (HR) — chờ duyệt → duyệt / từ chối; xem toàn bộ.
//   • Loại nghỉ (HR) — khai loại nghỉ (có lương / hạn mức).
import { useCallback, useEffect, useState } from "react";
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
import "./nhan-su.css";
import "./cham-cong.css";

type Tab = "me" | "approve" | "calendar" | "types";

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

function MyLeaveTab({ token, onChanged }: { token: string; onChanged?: () => void }) {
  const [hasEmp, setHasEmp] = useState<boolean | null>(null);
  const [items, setItems] = useState<LeaveRequest[]>([]);
  const [quotas, setQuotas] = useState<LeaveQuota[]>([]);
  const [types, setTypes] = useState<LeaveType[]>([]);
  const [sel, setSel] = useState<number | "new">("new");   // panel phải: form mới HOẶC 1 đơn
  const [form, setForm] = useState({ leave_type_id: "" as number | "", start_date: "", end_date: "", reason: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.leaves.me(token).then((r) => { setHasEmp(r.has_employee); setItems(r.items); setQuotas(r.quotas ?? []); }).catch(() => setHasEmp(false));
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
      load(); onChanged?.();
      setSel(created.id);   // nhảy sang chi tiết đơn vừa gửi
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  }
  async function cancel(id: number) {
    await api.leaves.cancel(token, id);
    load(); onChanged?.();
  }

  if (hasEmp === false) {
    return <div className="banner banner--warn" style={{ marginTop: 12 }}>
      Tài khoản của bạn <strong>chưa gắn hồ sơ nhân viên</strong> nên không tạo đơn nghỉ được. Liên hệ HCNS.
    </div>;
  }
  const selReq = typeof sel === "number" ? items.find((r) => r.id === sel) ?? null : null;

  return (
    <div>
      {quotas.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          {quotas.map((q) => {
            const low = q.remaining <= 0 ? "var(--signal)" : q.remaining <= 2 ? "var(--amber-deep)" : "var(--moss-deep)";
            return (
              <div key={q.leave_type_id} style={{ border: "1px solid var(--rule)", borderRadius: "var(--r-3)", background: "var(--canvas)", padding: "8px 14px", minWidth: 130 }}>
                <div style={{ fontSize: 12, color: "var(--ash)" }}>{q.name}</div>
                <div style={{ fontSize: 20, fontWeight: 600, color: low }}>
                  còn {q.remaining}<span style={{ fontSize: 12, color: "var(--ash)", fontWeight: 400 }}> / {q.annual_quota} ngày</span>
                </div>
                <div style={{ fontSize: 11, color: "var(--ash-2)" }}>đã dùng {q.used} ngày làm việc</div>
              </div>
            );
          })}
        </div>
      )}
      <div className="ns2__grid">
        <div className="ns2__list">
          <button className="btn btn--primary" style={{ width: "100%", marginBottom: 10 }} onClick={() => { setSel("new"); setError(null); }}>+ Xin nghỉ</button>
          <div className="ns2__rows">
            {items.map((r) => (
              <button key={r.id} type="button" className={`ns2-row${sel === r.id ? " is-active" : ""}`} onClick={() => setSel(r.id)}>
                <div className="ns2-row__body">
                  <div className="ns2-row__name">{r.leave_type_name ?? "—"} <StatusBadge s={r.status} /></div>
                  <div className="ns2-row__sub">{fmtDate(r.start_date)}–{fmtDate(r.end_date)} · {r.days} ngày</div>
                </div>
              </button>
            ))}
            {items.length === 0 && <div className="ns2-blank" style={{ minHeight: 120 }}><div className="ns2-blank__icon">🌴</div>Chưa có đơn nào</div>}
          </div>
        </div>

        <div className="ns2__detail is-open">
          {sel === "new" ? (
            <div className="ns2-detail">
              <div className="ns2-detail__head"><div className="ns2-detail__id"><h2>Xin nghỉ</h2></div></div>
              <div className="ns2-detail__body">
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
                  <input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="vd: Về quê, khám bệnh…" /></label>
                <p className="cc-note" style={{ marginTop: 10 }}>Cuối tuần (T7/CN) không trừ vào phép năm. Nghỉ phép năm bị chặn khi vượt hạn mức.</p>
                <button className="btn btn--primary" style={{ marginTop: 12 }} onClick={submit} disabled={busy}>{busy ? "Đang gửi…" : "Gửi đơn"}</button>
              </div>
            </div>
          ) : selReq ? (
            <div className="ns2-detail">
              <div className="ns2-detail__head">
                <button className="ns2-detail__back" onClick={() => setSel("new")}>←</button>
                <div className="ns2-detail__id">
                  <h2>{selReq.leave_type_name ?? "—"} <StatusBadge s={selReq.status} /></h2>
                  <div className="ns2-row__sub">{fmtDate(selReq.start_date)}–{fmtDate(selReq.end_date)} · {selReq.days} ngày{selReq.is_paid === false ? " · không lương" : ""}</div>
                </div>
              </div>
              <div className="ns2-detail__body">
                <div className="ns-kv"><span className="ns-kv__k">Lý do</span><span className="ns-kv__v">{selReq.reason || "—"}</span></div>
                <h4 className="ns-section__title" style={{ marginTop: 16 }}>Tiến trình</h4>
                <Timeline items={requestTimeline(selReq)} />
                {(selReq.status === "pending" || selReq.status === "approved") && (
                  <div className="ns2-editfoot">
                    <button className="btn btn--ghost ns-danger" onClick={() => cancel(selReq.id)}>Hủy đơn</button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="ns2-blank"><div className="ns2-blank__icon">📄</div>Chọn một đơn để xem chi tiết<div className="ns2-blank__hint">hoặc bấm “+ Xin nghỉ”</div></div>
          )}
        </div>
      </div>
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
      <div className="cc-toolbar">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="pending">Chờ duyệt</option>
          <option value="approved">Đã duyệt</option>
          <option value="rejected">Từ chối</option>
          <option value="">Tất cả</option>
        </select>
      </div>
      {sel.size > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", marginBottom: 8,
          background: "var(--rust-soft)", border: "1px solid var(--rust)", borderRadius: "var(--r-3)" }}>
          <strong style={{ color: "var(--rust-deep)" }}>{sel.size} đơn đã chọn</strong>
          <button className="btn btn--primary" onClick={bulkApprove} disabled={busy}>✓ Duyệt {sel.size}</button>
          <button className="btn btn--ghost ns-danger" onClick={() => { setRejectTarget("bulk"); setRejectNote(""); setError(null); }} disabled={busy}>✕ Từ chối {sel.size}</button>
          <button className="btn btn--ghost" onClick={() => setSel(new Set())} disabled={busy}>Bỏ chọn</button>
        </div>
      )}
      <LeaveTable items={shown} showEmployee onApprove={approve}
        onReject={(r) => { setRejectTarget(r); setRejectNote(""); setError(null); }}
        selectable selected={sel} onToggle={toggle} onToggleAll={toggleAll} allPendingCount={pendingIds.length} />
      {rejectTarget && (
        <div className="ns-modal" role="dialog" aria-modal="true">
          <div className="ns-modal__box">
            <header className="ns-modal__head">
              <h2>{rejectTarget === "bulk" ? `Từ chối ${sel.size} đơn` : "Từ chối đơn nghỉ"}</h2>
              <button className="ns-modal__x" onClick={() => setRejectTarget(null)}>×</button>
            </header>
            <div className="ns-modal__body">
              {error && <div className="banner banner--error">{error}</div>}
              <p style={{ marginTop: 0, color: "var(--ash)" }}>
                {rejectTarget === "bulk"
                  ? `Áp 1 lý do chung cho ${sel.size} đơn đã chọn.`
                  : `${rejectTarget.employee_name ?? `NV#${rejectTarget.employee_id}`} · ${rejectTarget.leave_type_name ?? "—"} · ${fmtDate(rejectTarget.start_date)}–${fmtDate(rejectTarget.end_date)} (${rejectTarget.days} ngày)`}
              </p>
              <label className="ns-field"><span className="ns-field__label">Lý do từ chối *</span>
                <input autoFocus value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} placeholder="Nêu rõ lý do để NV biết…" /></label>
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

  return (
    <div>
      <div className="cc-toolbar" style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button className="btn btn--ghost" onClick={() => shift(-1)}>‹</button>
        <strong style={{ minWidth: 110, textAlign: "center" }}>Tháng {ym.month}/{ym.year}</strong>
        <button className="btn btn--ghost" onClick={() => shift(1)}>›</button>
        <span style={{ marginLeft: 16, fontSize: 12, color: "var(--ash)", display: "inline-flex", alignItems: "center", gap: 6 }}>
          <i style={{ width: 12, height: 12, borderRadius: 3, background: "var(--moss-soft)", border: "1px solid var(--moss)", display: "inline-block" }} /> Đã duyệt
          <i style={{ width: 12, height: 12, borderRadius: 3, background: "var(--amber-soft)", border: "1px solid var(--amber)", display: "inline-block", marginLeft: 10 }} /> Chờ duyệt
        </span>
      </div>
      {data && data.employees.length === 0 && <div className="ns__empty">Không có ai nghỉ trong tháng này.</div>}
      {data && data.employees.length > 0 && (
        <div className="ns__tablewrap">
          <table className="ns__table" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ position: "sticky", left: 0, background: "var(--canvas)", zIndex: 1, minWidth: 150 }}>Nhân viên</th>
                {days.map((d) => (
                  <th key={d} style={{ textAlign: "center", minWidth: 24, padding: "4px 2px", color: isWeekend(d) ? "var(--ash-2)" : undefined }}>{d}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.employees.map((e) => (
                <tr key={e.employee_id}>
                  <td style={{ position: "sticky", left: 0, background: "var(--canvas)", fontWeight: 500 }}>{e.employee_name}</td>
                  {days.map((d) => {
                    const cell = e.days[String(d)];
                    const bg = cell ? (cell.status === "approved" ? "var(--moss-soft)" : "var(--amber-soft)") : (isWeekend(d) ? "var(--paper)" : "transparent");
                    const label = cell ? (cell.status === "approved" ? (cell.is_paid ? "P" : "KL") : "•") : "";
                    return (
                      <td key={d} title={cell ? `${cell.leave_type_name} · ${cell.status === "approved" ? "đã duyệt" : "chờ duyệt"}` : ""}
                        style={{ textAlign: "center", padding: "4px 2px", background: bg, fontSize: 11,
                          color: cell?.status === "approved" ? "var(--moss-deep)" : "var(--amber-deep)", fontWeight: 600 }}>
                        {label}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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

function LeaveTable({ items, showEmployee, onCancel, onApprove, onReject,
  selectable, selected, onToggle, onToggleAll, allPendingCount }: {
  items: LeaveRequest[]; showEmployee: boolean;
  onCancel?: (id: number) => void; onApprove?: (id: number) => void; onReject?: (r: LeaveRequest) => void;
  selectable?: boolean; selected?: Set<number>; onToggle?: (id: number) => void;
  onToggleAll?: () => void; allPendingCount?: number;
}) {
  const allChecked = !!allPendingCount && selected?.size === allPendingCount;
  const cols = (showEmployee ? 8 : 7) + (selectable ? 1 : 0);
  return (
    <div className="ns__tablewrap">
      <table className="ns__table">
        <thead>
          <tr>
            {selectable && <th style={{ width: 32 }}><input type="checkbox" checked={allChecked} onChange={onToggleAll} title="Chọn tất cả đơn chờ" /></th>}
            {showEmployee && <th>Nhân viên</th>}
            <th>Loại</th><th>Từ</th><th>Đến</th><th>Số ngày</th><th>Lý do</th><th>Trạng thái</th><th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.id}>
              {selectable && <td>{r.status === "pending" && <input type="checkbox" checked={selected?.has(r.id) ?? false} onChange={() => onToggle?.(r.id)} />}</td>}
              {showEmployee && <td>{r.employee_name ?? `NV#${r.employee_id}`}</td>}
              <td>{r.leave_type_name ?? "—"}{r.is_paid === false ? " (KL)" : ""}</td>
              <td>{fmtDate(r.start_date)}</td><td>{fmtDate(r.end_date)}</td>
              <td>{r.days}</td>
              <td title={r.decision_note ?? ""}>{r.reason ?? "—"}</td>
              <td><StatusBadge s={r.status} /></td>
              <td className="cc-rowact">
                {onApprove && r.status === "pending" && <button className="btn btn--ghost" onClick={() => onApprove(r.id)}>Duyệt</button>}
                {onReject && r.status === "pending" && <button className="btn btn--ghost ns-danger" onClick={() => onReject(r)}>Từ chối</button>}
                {onCancel && (r.status === "pending" || r.status === "approved") && <button className="btn btn--ghost" onClick={() => onCancel(r.id)}>Hủy</button>}
              </td>
            </tr>
          ))}
          {items.length === 0 && <tr><td colSpan={cols} className="ns__empty">Chưa có đơn nào.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
