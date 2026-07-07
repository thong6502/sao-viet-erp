// "Hồ sơ của tôi" — self-service cho nhân viên thường (module không gate `nhan_su`).
// Xem hồ sơ CỦA MÌNH (backend /me), tự sửa liên lạc; định danh/lương do HCNS quản lý.
import { useCallback, useEffect, useState } from "react";
import {
  api,
  assetUrl,
  type EmployeeAttachment,
  type EmployeeDetail,
  type EmployeeEvent,
  type MyContactInput,
  type UpdateRequest,
  type UpdateRequestInput,
  type WorkShift,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Timeline, type TimelineEntry } from "../components/Timeline";
import "./nhan-su.css";
import "./ho-so-cua-toi.css";

const STATUS_LABEL: Record<string, string> = {
  probation: "Thử việc", active: "Chính thức", on_leave: "Nghỉ dài hạn",
  suspended: "Đình chỉ", resigned: "Đã nghỉ",
};
const STATUS_CLASS: Record<string, string> = {
  probation: "ns-badge--warn", active: "ns-badge--ok", on_leave: "ns-badge--info",
  suspended: "ns-badge--muted", resigned: "ns-badge--danger",
};
const GENDER_LABEL: Record<string, string> = { male: "Nam", female: "Nữ", other: "Khác" };
const DOC_KIND_LABEL: Record<string, string> = {
  hop_dong: "Hợp đồng", cccd: "CCCD", bang_cap: "Bằng cấp", khac: "Khác",
};
const EVENT_LABEL: Record<string, string> = {
  hired: "Vào làm", confirmed: "Chuyển chính thức", transferred: "Điều chuyển",
  promoted: "Nâng bậc / đổi chức danh", leave_start: "Bắt đầu nghỉ dài hạn",
  leave_end: "Đi làm lại", suspended: "Đình chỉ", resigned: "Nghỉ việc", reinstated: "Tuyển lại",
};

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString("vi-VN");
}

export function HoSoCuaToiPage() {
  const { token } = useAuth();
  const [emp, setEmp] = useState<EmployeeDetail | null>(null);
  const [hasEmp, setHasEmp] = useState<boolean | null>(null);
  const [events, setEvents] = useState<EmployeeEvent[]>([]);
  const [files, setFiles] = useState<EmployeeAttachment[]>([]);
  const [shift, setShift] = useState<WorkShift | null>(null);
  const [editing, setEditing] = useState(false);
  const [reqs, setReqs] = useState<UpdateRequest[]>([]);
  const [requesting, setRequesting] = useState(false);

  const load = useCallback(() => {
    if (!token) return;
    api.employees.me(token).then((r) => { setHasEmp(r.has_employee); setEmp(r.employee); }).catch(() => setHasEmp(false));
    api.employees.myEvents(token).then((r) => setEvents(r.items)).catch(() => setEvents([]));
    api.employees.myAttachments(token).then((r) => setFiles(r.items)).catch(() => setFiles([]));
    api.employees.myRequests(token).then((r) => setReqs(r.items)).catch(() => setReqs([]));
  }, [token]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (emp?.default_shift_id && token) {
      api.attendance.shifts(token).then((r) => setShift(r.items.find((s) => s.id === emp.default_shift_id) ?? null)).catch(() => setShift(null));
    }
  }, [token, emp?.default_shift_id]);

  const tl: TimelineEntry[] = events.map((ev) => {
    const tone: TimelineEntry["tone"] | undefined =
      ev.event_type === "hired" ? "rust"
      : ["confirmed", "promoted", "leave_end", "reinstated"].includes(ev.event_type) ? "moss"
      : ev.event_type === "transferred" ? "steel"
      : ["resigned", "suspended", "leave_start"].includes(ev.event_type) ? "signal" : undefined;
    return {
      title: EVENT_LABEL[ev.event_type] ?? ev.event_type,
      meta: [fmtDate(ev.effective_date), ev.note || null].filter(Boolean).join(" · "),
      accent: tone === "moss" || tone === "rust", tone,
    };
  });

  if (hasEmp === null) return <main className="ns"><p className="ns__empty">Đang tải…</p></main>;
  if (!hasEmp || !emp) {
    return (
      <main className="ns">
        <header className="ns__head"><div><h1 className="ns__title">Hồ sơ của tôi</h1></div></header>
        <div className="banner banner--warn" style={{ marginTop: 12 }}>
          Tài khoản của bạn <strong>chưa gắn hồ sơ nhân viên</strong>. Liên hệ phòng HCNS để nối hồ sơ.
        </div>
      </main>
    );
  }

  return (
    <main className="ns mine">
      <div className="mine__hero">
        <div className="ns-avatar ns-avatar--xl">{assetUrl(emp.photo_url) ? <img src={assetUrl(emp.photo_url)!} alt="" /> : emp.full_name.slice(0, 1)}</div>
        <div className="mine__heroid">
          <h1>{emp.full_name} <span className={`ns-badge ${STATUS_CLASS[emp.status] ?? "ns-badge--muted"}`}>{STATUS_LABEL[emp.status] ?? emp.status}</span></h1>
          <p>{emp.department_name ?? "—"}{emp.position ? ` · ${emp.position}` : ""}{emp.job_grade ? ` · Bậc ${emp.job_grade}` : ""}</p>
          <p className="mine__herosub">{emp.code} · Vào làm {fmtDate(emp.hire_date)}{emp.account_username ? ` · 🔑 ${emp.account_username}` : ""}</p>
        </div>
        <button className="btn btn--primary" onClick={() => setEditing(true)}>Cập nhật liên hệ</button>
      </div>

      <div className="mine__cards">
        <div className="mine__card">
          <h4 className="ns-section__title">Thông tin liên hệ</h4>
          <Row k="SĐT" v={emp.phone} /><Row k="Email" v={emp.email} />
          <Row k="Chỗ ở hiện tại" v={emp.current_address} />
          <Row k="Liên hệ khẩn" v={emp.emergency_contact_name ? `${emp.emergency_contact_name} · ${emp.emergency_contact_phone ?? ""}` : null} />
          <button className="btn btn--ghost mine__editbtn" onClick={() => setEditing(true)}>Sửa</button>
        </div>

        <div className="mine__card">
          <h4 className="ns-section__title">Cá nhân <span className="mine__lock">Do HCNS quản lý</span></h4>
          <Row k="Ngày sinh" v={fmtDate(emp.date_of_birth)} /><Row k="Giới tính" v={emp.gender ? GENDER_LABEL[emp.gender] : null} />
          <Row k="CCCD" v={emp.national_id} /><Row k="Hộ khẩu" v={emp.permanent_address} />
        </div>

        <div className="mine__card">
          <h4 className="ns-section__title">Ngân hàng / Thuế <span className="mine__lock">Do HCNS quản lý</span></h4>
          <Row k="Tài khoản NH" v={emp.bank_account ? `${emp.bank_account} · ${emp.bank_name ?? ""}` : null} />
          <Row k="MST cá nhân" v={emp.pit_tax_code} />
          <Row k="Người phụ thuộc" v={String(emp.dependents_count)} />
        </div>

        <div className="mine__card">
          <h4 className="ns-section__title">Ca làm việc</h4>
          <Row k="Ca mặc định" v={shift ? `${shift.name} (${shift.start_time}–${shift.end_time})` : null} />
        </div>
      </div>

      <div className="mine__card mine__wide">
        <div className="mine__reqhead">
          <h4 className="ns-section__title" style={{ margin: 0 }}>Đề nghị cập nhật (định danh / ngân hàng)</h4>
          <button className="btn btn--ghost" onClick={() => setRequesting(true)}>+ Gửi đề nghị</button>
        </div>
        <p className="cc-note">Các mục như tên, CCCD, hộ khẩu, số tài khoản… bạn không sửa thẳng — gửi đề nghị để HCNS duyệt.</p>
        <ul className="ns-filelist">
          {reqs.map((r) => (
            <li key={r.id}>
              <span>{Object.entries(r.changes).map(([k, v]) => `${REQ_FIELD_LABEL[k] ?? k}: ${v}`).join(" · ")}</span>
              <span className={`ns-badge ${r.status === "approved" ? "ns-badge--ok" : r.status === "rejected" ? "ns-badge--danger" : "ns-badge--muted"}`}>
                {r.status === "approved" ? "Đã duyệt" : r.status === "rejected" ? "Từ chối" : "Chờ duyệt"}
              </span>
            </li>
          ))}
          {reqs.length === 0 && <li className="ns__empty">Chưa có đề nghị nào.</li>}
        </ul>
      </div>

      <div className="mine__card mine__wide">
        <h4 className="ns-section__title">Giấy tờ của tôi</h4>
        <ul className="ns-filelist">
          {files.map((a) => (
            <li key={a.id}>
              <a href={assetUrl(a.file_url) ?? "#"} target="_blank" rel="noreferrer">{DOC_KIND_LABEL[a.doc_kind] ?? a.doc_kind} · {a.file_name}</a>
              <span className="ns-file__date">{fmtDate(a.uploaded_at)}</span>
            </li>
          ))}
          {files.length === 0 && <li className="ns__empty">Chưa có giấy tờ nào.</li>}
        </ul>
      </div>

      <div className="mine__card mine__wide">
        <h4 className="ns-section__title">Quá trình công tác</h4>
        <Timeline items={tl} emptyText="Chưa có mốc quá trình công tác." />
      </div>

      {editing && <ContactModal token={token!} emp={emp} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); load(); }} />}
      {requesting && <RequestModal token={token!} emp={emp} onClose={() => setRequesting(false)} onSaved={() => { setRequesting(false); load(); }} />}
    </main>
  );
}

const REQ_FIELD_LABEL: Record<string, string> = {
  full_name: "Họ tên", date_of_birth: "Ngày sinh", national_id: "CCCD",
  national_id_date: "Ngày cấp CCCD", national_id_place: "Nơi cấp CCCD",
  permanent_address: "Hộ khẩu", bank_account: "Số tài khoản", bank_name: "Ngân hàng",
  dependents_count: "Người phụ thuộc",
};

function Row({ k, v }: { k: string; v: string | null | undefined }) {
  return <div className="ns-kv"><span className="ns-kv__k">{k}</span><span className="ns-kv__v">{v || "—"}</span></div>;
}

function ContactModal({ token, emp, onClose, onSaved }: {
  token: string; emp: EmployeeDetail; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<MyContactInput>({
    phone: emp.phone ?? "", email: emp.email ?? "", current_address: emp.current_address ?? "",
    emergency_contact_name: emp.emergency_contact_name ?? "", emergency_contact_phone: emp.emergency_contact_phone ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  function set<K extends keyof MyContactInput>(k: K, v: MyContactInput[K]) { setForm((f) => ({ ...f, [k]: v })); }
  async function save() {
    setBusy(true); setErr(null);
    try { await api.employees.updateMe(token, form); onSaved(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Lỗi khi lưu."); setBusy(false); }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head"><h2>Cập nhật thông tin liên hệ</h2>
          <button className="ns-modal__x" onClick={onClose}>×</button></header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <p className="cc-note" style={{ marginBottom: 12 }}>Bạn chỉ sửa được thông tin liên lạc. Định danh, chức danh, lương/BHXH do phòng HCNS quản lý.</p>
          <div className="ns-grid">
            <label className="ns-field"><span className="ns-field__label">SĐT</span><input value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} /></label>
            <label className="ns-field"><span className="ns-field__label">Email</span><input value={form.email ?? ""} onChange={(e) => set("email", e.target.value)} /></label>
            <label className="ns-field"><span className="ns-field__label">Liên hệ khẩn (tên)</span><input value={form.emergency_contact_name ?? ""} onChange={(e) => set("emergency_contact_name", e.target.value)} /></label>
            <label className="ns-field"><span className="ns-field__label">Liên hệ khẩn (SĐT)</span><input value={form.emergency_contact_phone ?? ""} onChange={(e) => set("emergency_contact_phone", e.target.value)} /></label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}><span className="ns-field__label">Chỗ ở hiện tại</span><input value={form.current_address ?? ""} onChange={(e) => set("current_address", e.target.value)} /></label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>{busy ? "Đang lưu…" : "Lưu"}</button>
        </footer>
      </div>
    </div>
  );
}

// Đề nghị sửa field bảo vệ → HCNS duyệt. Chỉ gửi field ĐÃ ĐỔI so với hiện tại.
function RequestModal({ token, emp, onClose, onSaved }: {
  token: string; emp: EmployeeDetail; onClose: () => void; onSaved: () => void;
}) {
  const orig: Record<string, string> = {
    full_name: emp.full_name ?? "", date_of_birth: emp.date_of_birth ?? "", national_id: emp.national_id ?? "",
    national_id_date: emp.national_id_date ?? "", national_id_place: emp.national_id_place ?? "",
    permanent_address: emp.permanent_address ?? "", bank_account: emp.bank_account ?? "",
    bank_name: emp.bank_name ?? "", dependents_count: String(emp.dependents_count ?? 0),
  };
  const [form, setForm] = useState<Record<string, string>>({ ...orig });
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function save() {
    const changes: UpdateRequestInput["changes"] = {};
    for (const k of Object.keys(orig)) {
      if (form[k] !== orig[k]) changes[k] = k === "dependents_count" ? Number(form[k]) : form[k];
    }
    if (Object.keys(changes).length === 0) { setErr("Bạn chưa thay đổi mục nào."); return; }
    setBusy(true); setErr(null);
    try { await api.employees.createMyRequest(token, { changes, reason: reason || null }); onSaved(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Lỗi khi gửi."); setBusy(false); }
  }
  const F = (label: string, k: string, type = "text") => (
    <label className="ns-field"><span className="ns-field__label">{label}</span>
      <input type={type} value={form[k]} onChange={(e) => set(k, e.target.value)} /></label>
  );
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head"><h2>Đề nghị cập nhật hồ sơ</h2>
          <button className="ns-modal__x" onClick={onClose}>×</button></header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <p className="cc-note" style={{ marginBottom: 12 }}>Sửa các mục cần đổi rồi gửi. HCNS duyệt xong mới áp vào hồ sơ. Chỉ gửi mục bạn thay đổi.</p>
          <div className="ns-grid">
            {F("Họ tên", "full_name")}
            {F("Ngày sinh", "date_of_birth", "date")}
            {F("CCCD", "national_id")}
            {F("Ngày cấp CCCD", "national_id_date", "date")}
            {F("Nơi cấp CCCD", "national_id_place")}
            {F("Hộ khẩu", "permanent_address")}
            {F("Số tài khoản", "bank_account")}
            {F("Ngân hàng", "bank_name")}
            {F("Người phụ thuộc", "dependents_count", "number")}
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}><span className="ns-field__label">Lý do</span>
            <input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>{busy ? "Đang gửi…" : "Gửi đề nghị"}</button>
        </footer>
      </div>
    </div>
  );
}
