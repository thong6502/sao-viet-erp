// Hồ sơ nhân sự (module `nhan_su`, lát #1). Danh sách + KPI + Wizard thêm (5 bước) +
// Trang hồ sơ (tab Thông tin / Quá trình công tác / Đính kèm / Nhật ký) + dialog Đổi
// trạng thái / Điều chuyển / Nâng bậc (sinh Quá trình công tác) + nối/tạo tài khoản.
// Backend là cổng quyền thật (403); useCan chỉ ẩn/hiện nút cho gọn UX.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  api,
  ApiError,
  assetUrl,
  type EmployeeAttachment,
  type EmployeeDetail,
  type EmployeeEvent,
  type EmployeeInput,
  type EmployeeKpis,
  type EmployeeMeta,
  type EmployeeRow,
  type EmployeeTransitionInput,
  type UpdateRequest,
  type WorkShift,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import type { NavigateFn } from "../components/AppShell";
import { Timeline, type TimelineEntry } from "../components/Timeline";
import "./nhan-su.css";

const STATUS_LABEL: Record<string, string> = {
  probation: "Thử việc",
  active: "Chính thức",
  on_leave: "Nghỉ dài hạn",
  suspended: "Đình chỉ",
  resigned: "Đã nghỉ",
};
const STATUS_CLASS: Record<string, string> = {
  probation: "ns-badge--warn",
  active: "ns-badge--ok",
  on_leave: "ns-badge--info",
  suspended: "ns-badge--muted",
  resigned: "ns-badge--danger",
};
const GENDER_LABEL: Record<string, string> = { male: "Nam", female: "Nữ", other: "Khác" };
const DOC_KIND_LABEL: Record<string, string> = {
  hop_dong: "Hợp đồng",
  cccd: "CCCD",
  bang_cap: "Bằng cấp",
  khac: "Khác",
};
const EVENT_LABEL: Record<string, string> = {
  hired: "Vào làm",
  confirmed: "Chuyển chính thức",
  transferred: "Điều chuyển",
  promoted: "Nâng bậc / đổi chức danh",
  leave_start: "Bắt đầu nghỉ dài hạn",
  leave_end: "Đi làm lại",
  suspended: "Đình chỉ",
  resigned: "Nghỉ việc",
  reinstated: "Tuyển lại",
};

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString("vi-VN");
}

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return "Có lỗi xảy ra.";
}

function isEndingSoon(e: EmployeeRow): boolean {
  if (e.status !== "probation" || !e.probation_end_date) return false;
  const end = new Date(e.probation_end_date).getTime();
  const now = Date.now();
  return end >= now && end <= now + 14 * 24 * 3600 * 1000;
}

export function NhanSuPage({ navigate }: { navigate?: NavigateFn }) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("nhan_su", "create");
  const canApprove = can("nhan_su", "approve");

  const [data, setData] = useState<{ items: EmployeeRow[]; total: number; kpis: EmployeeKpis } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [deptFilter, setDeptFilter] = useState<number | "">("");
  const [sort, setSort] = useState("code");
  const [endingSoon, setEndingSoon] = useState(false); // KPI "sắp hết thử việc" (lọc client)
  const [exporting, setExporting] = useState(false);
  const [page, setPage] = useState(1);
  const size = 20;

  const [meta, setMeta] = useState<EmployeeMeta | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [reqOpen, setReqOpen] = useState(false);
  const [reqCount, setReqCount] = useState(0);

  const loadReqs = useCallback(() => {
    if (!token || !canApprove) return;
    api.employees.updateRequests(token, "pending").then((r) => setReqCount(r.items.length)).catch(() => setReqCount(0));
  }, [token, canApprove]);
  useEffect(() => { loadReqs(); }, [loadReqs]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.employees
      .list(token, {
        q: q || undefined,
        status: statusFilter || undefined,
        department_id: deptFilter === "" ? undefined : deptFilter,
        sort,
        page,
        size,
      })
      .then((res) => {
        setData({ items: res.items, total: res.total, kpis: res.kpis });
        setError(null);
      })
      .catch((e) => setError(errMsg(e)))
      .finally(() => setLoading(false));
  }, [token, q, statusFilter, deptFilter, sort, page]);

  async function exportExcel() {
    if (!token) return;
    setExporting(true);
    try {
      const res = await api.employees.list(token, {
        q: q || undefined, status: statusFilter || undefined,
        department_id: deptFilter === "" ? undefined : deptFilter, sort, page: 1, size: 200,
      });
      const rows: string[][] = [["Mã", "Họ tên", "Phòng/Tổ", "Chức danh", "Bậc", "Trạng thái", "Ngày vào", "Tài khoản"]];
      for (const e of res.items) rows.push([
        e.code, e.full_name, e.department_name ?? "", e.position ?? "", e.job_grade ?? "",
        STATUS_LABEL[e.status] ?? e.status, e.hire_date ?? "", e.account_username ?? "",
      ]);
      const csv = "﻿" + rows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(",")).join("\r\n");
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
      const a = document.createElement("a");
      a.href = url; a.download = "danh-sach-nhan-vien.csv";
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } finally { setExporting(false); }
  }

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (token) api.employees.meta(token).then(setMeta).catch(() => setMeta(null));
  }, [token]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / size)) : 1;
  const rows = (data?.items ?? []).filter((e) => !endingSoon || isEndingSoon(e));

  return (
    <main className="ns ns2">
      <header className="ns__head">
        <div>
          <h1 className="ns__title">Hồ sơ nhân sự</h1>
          <p className="ns__sub">Phòng Hành chính nhân sự · quản lý hồ sơ, quá trình công tác</p>
        </div>
        <div className="ns2__headact">
          {canApprove && (
            <button type="button" className={`btn btn--ghost${reqCount > 0 ? " ns2-reqbtn--on" : ""}`} onClick={() => setReqOpen(true)}>
              Yêu cầu cập nhật{reqCount > 0 ? ` (${reqCount})` : ""}
            </button>
          )}
          {canCreate && (
            <button type="button" className="btn btn--primary" onClick={() => setWizardOpen(true)}>
              + Thêm nhân viên
            </button>
          )}
        </div>
      </header>

      <div className="ns2__grid">
        <section className="ns2__list">
          {data && (
            <KpiStrip
              kpis={data.kpis}
              onPickProbation={() => { setEndingSoon(false); setStatusFilter("probation"); }}
              onPickEndingSoon={() => { setStatusFilter("probation"); setEndingSoon(true); }}
            />
          )}

          <div className="ns2__toolbar">
            <input
              className="ns__search"
              placeholder="Tìm tên / mã / CCCD / SĐT…"
              value={q}
              onChange={(e) => { setPage(1); setEndingSoon(false); setQ(e.target.value); }}
            />
            <div className="ns2__filters">
              <select value={statusFilter} onChange={(e) => { setPage(1); setEndingSoon(false); setStatusFilter(e.target.value); }}>
                <option value="">Mọi trạng thái</option>
                {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <select value={deptFilter} onChange={(e) => { setPage(1); setDeptFilter(e.target.value === "" ? "" : Number(e.target.value)); }}>
                <option value="">Mọi phòng/tổ</option>
                {meta?.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
              <select value={sort} onChange={(e) => { setPage(1); setSort(e.target.value); }} title="Sắp xếp">
                <option value="code">Mã ↑</option>
                <option value="full_name">Tên A→Z</option>
                <option value="-hire_date">Mới vào trước</option>
                <option value="hire_date">Vào lâu trước</option>
                <option value="status">Trạng thái</option>
              </select>
              <button className="btn btn--ghost" onClick={exportExcel} disabled={exporting}>{exporting ? "…" : "⬇ Excel"}</button>
              {endingSoon && (
                <button className="ns2-chip" onClick={() => setEndingSoon(false)}>⚠ Sắp hết thử việc ×</button>
              )}
            </div>
          </div>

          {error && <div className="banner banner--error" role="alert">{error}</div>}

          <div className="ns2__rows">
            {loading && <div className="ns__empty">Đang tải…</div>}
            {!loading && rows.length === 0 && (
              <div className="ns__empty">
                {endingSoon ? "Không có ai sắp hết thử việc." : "Chưa có nhân viên nào."}
              </div>
            )}
            {!loading && rows.map((e) => (
              <button
                key={e.id}
                type="button"
                className={`ns2-row${selectedId === e.id ? " is-active" : ""}${isEndingSoon(e) ? " is-soon" : ""}`}
                onClick={() => setSelectedId(e.id)}
              >
                <span className="ns2-row__av">{e.full_name.slice(0, 1).toUpperCase()}</span>
                <span className="ns2-row__body">
                  <span className="ns2-row__name">
                    {e.full_name}
                    {e.account_username && <span className="ns__chip" title="Có tài khoản">🔑</span>}
                  </span>
                  <span className="ns2-row__sub">{e.code} · {e.department_name ?? "—"}{e.job_grade ? ` · ${e.job_grade}` : ""}</span>
                </span>
                <StatusDot status={e.status} />
              </button>
            ))}
          </div>

          <div className="ns__pager">
            <span>{data ? `${data.total} nhân viên` : ""}</span>
            <div className="ns__pagerbtns">
              <button className="btn btn--ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>‹</button>
              <span>{page} / {totalPages}</span>
              <button className="btn btn--ghost" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>›</button>
            </div>
          </div>
        </section>

        <section className={`ns2__detail${selectedId != null ? " is-open" : ""}`}>
          {selectedId == null ? (
            <div className="ns2-blank">
              <div className="ns2-blank__icon">👤</div>
              <p>Chọn một nhân viên để xem hồ sơ</p>
              {canCreate && <span className="ns2-blank__hint">hoặc “+ Thêm nhân viên”</span>}
            </div>
          ) : (
            <EmployeeDetailPanel
              token={token!}
              employeeId={selectedId}
              meta={meta}
              navigate={navigate}
              onClose={() => setSelectedId(null)}
              onChanged={load}
            />
          )}
        </section>
      </div>

      {wizardOpen && meta && (
        <EmployeeWizard
          token={token!}
          meta={meta}
          onClose={() => setWizardOpen(false)}
          onCreated={(id) => { setWizardOpen(false); load(); setSelectedId(id); }}
        />
      )}

      {reqOpen && (
        <RequestQueueModal token={token!} onClose={() => setReqOpen(false)}
          onDecided={() => { loadReqs(); if (selectedId) load(); }} />
      )}
    </main>
  );
}

// Hàng đợi HCNS duyệt "yêu cầu cập nhật" của NV.
const REQ_FIELD_LABEL: Record<string, string> = {
  full_name: "Họ tên", date_of_birth: "Ngày sinh", national_id: "CCCD",
  national_id_date: "Ngày cấp CCCD", national_id_place: "Nơi cấp CCCD",
  permanent_address: "Hộ khẩu", bank_account: "Số tài khoản", bank_name: "Ngân hàng",
  dependents_count: "Người phụ thuộc",
};

function RequestQueueModal({ token, onClose, onDecided }: {
  token: string; onClose: () => void; onDecided: () => void;
}) {
  const [items, setItems] = useState<UpdateRequest[] | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.employees.updateRequests(token, "pending").then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token]);
  useEffect(() => { load(); }, [load]);

  async function decide(id: number, approve: boolean) {
    setBusy(true);
    try {
      if (approve) await api.employees.approveRequest(token, id);
      else await api.employees.rejectRequest(token, id, "Từ chối");
      load(); onDecided();
    } finally { setBusy(false); }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head"><h2>Yêu cầu cập nhật hồ sơ (chờ duyệt)</h2>
          <button className="ns-modal__x" onClick={onClose}>×</button></header>
        <div className="ns-modal__body">
          {!items ? <p className="ns__empty">Đang tải…</p> : (
            <div className="ns__tablewrap">
              <table className="ns__table">
                <thead><tr><th>Nhân viên</th><th>Đề nghị đổi</th><th>Lý do</th><th></th></tr></thead>
                <tbody>
                  {items.map((r) => (
                    <tr key={r.id}>
                      <td>{r.employee_name ?? `NV#${r.employee_id}`}</td>
                      <td>{Object.entries(r.changes).map(([k, v]) => `${REQ_FIELD_LABEL[k] ?? k}: ${v}`).join(" · ")}</td>
                      <td>{r.reason ?? "—"}</td>
                      <td className="cc-rowact">
                        <button className="btn btn--ghost" disabled={busy} onClick={() => decide(r.id, true)}>Duyệt</button>
                        <button className="btn btn--ghost ns-danger" disabled={busy} onClick={() => decide(r.id, false)}>Từ chối</button>
                      </td>
                    </tr>
                  ))}
                  {items.length === 0 && <tr><td colSpan={4} className="ns__empty">Không có yêu cầu chờ duyệt.</td></tr>}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <footer className="ns-modal__foot"><button className="btn btn--ghost" onClick={onClose}>Đóng</button></footer>
      </div>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  return (
    <span className={`ns2-status ns2-status--${status}`} title={STATUS_LABEL[status] ?? status}>
      <span className="ns2-status__dot" />
      <span className="ns2-status__txt">{STATUS_LABEL[status] ?? status}</span>
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`ns-badge ${STATUS_CLASS[status] ?? "ns-badge--muted"}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

function KpiStrip({ kpis, onPickProbation, onPickEndingSoon }: {
  kpis: EmployeeKpis; onPickProbation: () => void; onPickEndingSoon: () => void;
}) {
  return (
    <div className="ns__kpis ns2__kpis">
      <Kpi label="Tổng" value={kpis.total} />
      <button type="button" className="ns__kpi ns__kpi--warn ns2-kpibtn" onClick={onPickProbation}>
        <span className="ns__kpival">{kpis.probation}</span>
        <span className="ns__kpilabel">Thử việc</span>
      </button>
      <Kpi label="Đang làm" value={kpis.active} tone="ok" />
      <button type="button" className="ns__kpi ns__kpi--action" onClick={onPickEndingSoon}>
        <span className="ns__kpival">{kpis.probation_ending_soon}</span>
        <span className="ns__kpilabel">⚠ Sắp hết TV</span>
      </button>
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className={`ns__kpi ${tone ? `ns__kpi--${tone}` : ""}`}>
      <span className="ns__kpival">{value}</span>
      <span className="ns__kpilabel">{label}</span>
    </div>
  );
}

// --- Wizard thêm nhân viên (5 bước) ----------------------------------------

const STEPS = ["Định danh & việc làm", "Cá nhân", "BHXH / TNCN", "Đính kèm", "Tài khoản"];

function EmployeeWizard({
  token,
  meta,
  onClose,
  onCreated,
}: {
  token: string;
  meta: EmployeeMeta;
  onClose: () => void;
  onCreated: (id: number) => void;
}) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<EmployeeInput>({
    full_name: "",
    department_id: meta.departments[0]?.id ?? null,
    status: "probation",
    hire_date: new Date().toISOString().slice(0, 10),
    dependents_count: 0,
  });
  const [files, setFiles] = useState<{ file: File; doc_kind: string }[]>([]);
  const [makeAccount, setMakeAccount] = useState(false);
  const [acc, setAcc] = useState({ username: "", password: "", role_id: "" as number | "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof EmployeeInput>(k: K, v: EmployeeInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function submit() {
    setError(null);
    if (!form.full_name.trim()) {
      setStep(0);
      setError("Họ tên là bắt buộc.");
      return;
    }
    setBusy(true);
    try {
      const input: EmployeeInput = { ...form };
      if (makeAccount && acc.username.trim()) {
        input.account = {
          username: acc.username.trim(),
          password: acc.password,
          role_id: acc.role_id === "" ? null : acc.role_id,
        };
      }
      const res = await api.employees.create(token, input);
      const id = res.employee.id;
      // Upload các file đã chọn (cần id sau khi tạo).
      for (const f of files) {
        await api.employees.upload(token, id, f.file, f.doc_kind);
      }
      onCreated(id);
    } catch (e) {
      setError(errMsg(e));
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head">
          <h2>Thêm nhân viên mới</h2>
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng">×</button>
        </header>

        <ol className="ns-steps">
          {STEPS.map((s, i) => (
            <li key={s} className={i === step ? "is-active" : i < step ? "is-done" : ""}>
              <span className="ns-steps__n">{i + 1}</span>{s}
            </li>
          ))}
        </ol>

        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}

          {step === 0 && (
            <div className="ns-grid">
              <Field label="Họ tên *">
                <input value={form.full_name} onChange={(e) => set("full_name", e.target.value)} />
              </Field>
              <Field label="Phòng/Tổ *">
                <select value={form.department_id ?? ""} onChange={(e) => set("department_id", e.target.value === "" ? null : Number(e.target.value))}>
                  {meta.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </Field>
              <Field label="Chức danh">
                <input value={form.position ?? ""} onChange={(e) => set("position", e.target.value)} />
              </Field>
              <Field label="Ngày vào">
                <input type="date" value={form.hire_date ?? ""} onChange={(e) => set("hire_date", e.target.value)} />
              </Field>
              <Field label="Trạng thái">
                <select value={form.status} onChange={(e) => set("status", e.target.value)}>
                  <option value="probation">Thử việc</option>
                  <option value="active">Chính thức</option>
                </select>
              </Field>
              {form.status === "probation" && (
                <Field label="Ngày hết thử việc">
                  <input type="date" value={form.probation_end_date ?? ""} onChange={(e) => set("probation_end_date", e.target.value)} />
                </Field>
              )}
            </div>
          )}

          {step === 1 && (
            <div className="ns-grid">
              <Field label="Ngày sinh"><input type="date" value={form.date_of_birth ?? ""} onChange={(e) => set("date_of_birth", e.target.value)} /></Field>
              <Field label="Giới tính">
                <select value={form.gender ?? ""} onChange={(e) => set("gender", e.target.value || null)}>
                  <option value="">—</option>
                  <option value="male">Nam</option>
                  <option value="female">Nữ</option>
                  <option value="other">Khác</option>
                </select>
              </Field>
              <Field label="CCCD">
                <input value={form.national_id ?? ""} onChange={(e) => set("national_id", e.target.value)} />
              </Field>
              <Field label="SĐT"><input value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} /></Field>
              <Field label="Email"><input value={form.email ?? ""} onChange={(e) => set("email", e.target.value)} /></Field>
              <Field label="Hộ khẩu"><input value={form.permanent_address ?? ""} onChange={(e) => set("permanent_address", e.target.value)} /></Field>
              <Field label="Chỗ ở hiện tại"><input value={form.current_address ?? ""} onChange={(e) => set("current_address", e.target.value)} /></Field>
              <Field label="Liên hệ khẩn (tên)"><input value={form.emergency_contact_name ?? ""} onChange={(e) => set("emergency_contact_name", e.target.value)} /></Field>
              <Field label="Liên hệ khẩn (SĐT)"><input value={form.emergency_contact_phone ?? ""} onChange={(e) => set("emergency_contact_phone", e.target.value)} /></Field>
            </div>
          )}

          {step === 2 && (
            <div className="ns-grid">
              <Field label="Nhóm lương">
                <select value={form.payroll_group ?? ""} onChange={(e) => set("payroll_group", e.target.value || null)}>
                  <option value="">— chưa gán —</option>
                  {Object.entries(PG_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </Field>
              <Field label="Bậc lương (tổ In)">
                <select value={form.pay_grade_key ?? ""} onChange={(e) => set("pay_grade_key", e.target.value || null)}>
                  <option value="">— không theo bậc —</option>
                  {Object.entries(PGK_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </Field>
              <Field label="Bậc thợ"><input value={form.job_grade ?? ""} onChange={(e) => set("job_grade", e.target.value)} placeholder="vd 3/7" /></Field>
              <Field label="Số sổ BHXH"><input value={form.social_insurance_no ?? ""} onChange={(e) => set("social_insurance_no", e.target.value)} /></Field>
              <Field label="MST cá nhân"><input value={form.pit_tax_code ?? ""} onChange={(e) => set("pit_tax_code", e.target.value)} /></Field>
              <Field label="Người phụ thuộc"><input type="number" min={0} value={form.dependents_count ?? 0} onChange={(e) => set("dependents_count", Number(e.target.value))} /></Field>
              <Field label="Số tài khoản"><input value={form.bank_account ?? ""} onChange={(e) => set("bank_account", e.target.value)} /></Field>
              <Field label="Ngân hàng"><input value={form.bank_name ?? ""} onChange={(e) => set("bank_name", e.target.value)} /></Field>
            </div>
          )}

          {step === 3 && (
            <div>
              <FilePicker onAdd={(file, kind) => setFiles((fs) => [...fs, { file, doc_kind: kind }])} />
              <ul className="ns-filelist">
                {files.map((f, i) => (
                  <li key={i}>
                    <span>{DOC_KIND_LABEL[f.doc_kind]} · {f.file.name}</span>
                    <button className="btn btn--ghost" onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))}>Bỏ</button>
                  </li>
                ))}
                {files.length === 0 && <li className="ns__empty">Chưa chọn tệp nào (không bắt buộc).</li>}
              </ul>
            </div>
          )}

          {step === 4 && (
            <div>
              <label className="ns-check">
                <input type="checkbox" checked={makeAccount} onChange={(e) => setMakeAccount(e.target.checked)} />
                Tạo tài khoản đăng nhập cho nhân viên này
              </label>
              {makeAccount && (
                <div className="ns-grid" style={{ marginTop: 12 }}>
                  <Field label="Tên đăng nhập *"><input value={acc.username} onChange={(e) => setAcc({ ...acc, username: e.target.value })} /></Field>
                  <Field label="Mật khẩu tạm *"><input type="text" value={acc.password} onChange={(e) => setAcc({ ...acc, password: e.target.value })} /></Field>
                </div>
              )}
              <div className="ns-review">
                <h4>Xem lại</h4>
                <p><strong>{form.full_name || "(chưa nhập tên)"}</strong> · {meta.departments.find((d) => d.id === form.department_id)?.name ?? "—"} · {form.status === "active" ? "Chính thức" : "Thử việc"}</p>
                <p>Ngày vào {fmtDate(form.hire_date)} · {files.length} tệp đính kèm{makeAccount && acc.username ? ` · tài khoản "${acc.username}"` : ""}</p>
              </div>
            </div>
          )}
        </div>

        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <div className="ns-modal__footright">
            {step > 0 && <button className="btn btn--ghost" onClick={() => setStep((s) => s - 1)} disabled={busy}>‹ Trước</button>}
            {step < STEPS.length - 1 && <button className="btn btn--primary" onClick={() => setStep((s) => s + 1)}>Tiếp ›</button>}
            {step === STEPS.length - 1 && <button className="btn btn--primary" onClick={submit} disabled={busy}>{busy ? "Đang lưu…" : "Lưu & xem hồ sơ"}</button>}
          </div>
        </footer>
      </div>
    </div>
  );
}

function FilePicker({ onAdd }: { onAdd: (file: File, kind: string) => void }) {
  const [kind, setKind] = useState("hop_dong");
  return (
    <div className="ns-filepick">
      <select value={kind} onChange={(e) => setKind(e.target.value)}>
        {Object.entries(DOC_KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <input
        type="file"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onAdd(f, kind);
          e.target.value = "";
        }}
      />
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="ns-field">
      <span className="ns-field__label">{label}</span>
      {children}
    </label>
  );
}

// --- Trang hồ sơ (detail) ---------------------------------------------------

type Tab = "info" | "salary" | "events" | "files" | "activity";

function EmployeeDetailPanel({
  token,
  employeeId,
  meta,
  navigate,
  onClose,
  onChanged,
}: {
  token: string;
  employeeId: number;
  meta: EmployeeMeta | null;
  navigate?: NavigateFn;
  onClose: () => void;
  onChanged: () => void;
}) {
  const can = useCan();
  const canUpdate = can("nhan_su", "update");
  const canViewSalary = can("nhan_su", "view_salary");
  const [emp, setEmp] = useState<EmployeeDetail | null>(null);
  const [tab, setTab] = useState<Tab>("info");
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<string | null>(null); // dialog kind

  const reload = useCallback(() => {
    api.employees.get(token, employeeId).then(setEmp).catch((e) => setError(errMsg(e)));
  }, [token, employeeId]);

  useEffect(() => { setTab("info"); reload(); }, [reload]);

  if (!emp) {
    return <div className="ns2-detail__loading">{error ?? "Đang tải…"}</div>;
  }

  const resigned = emp.status === "resigned";
  const tabs: [Tab, string][] = [
    ["info", "Thông tin"],
    ...(canViewSalary ? [["salary", "Lương & BHXH"] as [Tab, string]] : []),
    ["events", "Quá trình công tác"],
    ["files", "Đính kèm"],
    ["activity", "Nhật ký"],
  ];

  return (
    <div className="ns2-detail">
      <header className="ns2-detail__head">
        <button className="ns2-detail__back" onClick={onClose} aria-label="Quay lại danh sách">‹</button>
        <div className="ns-avatar ns-avatar--lg">{assetUrl(emp.photo_url) ? <img src={assetUrl(emp.photo_url)!} alt="" /> : emp.full_name.slice(0, 1)}</div>
        <div className="ns2-detail__id">
          <h2>{emp.full_name} <StatusBadge status={emp.status} /></h2>
          <p className="ns-detail__meta">{emp.code} · {emp.department_name ?? "—"} · {emp.position ?? "—"}{emp.job_grade ? ` · Bậc ${emp.job_grade}` : ""}</p>
          <p className="ns-detail__meta">Vào làm {fmtDate(emp.hire_date)} · {emp.account_username ? `🔑 ${emp.account_username}` : "chưa nối tài khoản"}</p>
        </div>
      </header>

      {navigate && (
        <div className="ns2-detail__links">
          <span className="ns2-detail__linkslabel">Xem của NV này:</span>
          <button className="btn btn--ghost" onClick={() => navigate("cham-cong", { focusEmployeeId: emp.id })}>🕒 Chấm công</button>
          <button className="btn btn--ghost" onClick={() => navigate("nghi-phep", { focusEmployeeId: emp.id })}>📅 Nghỉ phép</button>
          <button className="btn btn--ghost" onClick={() => navigate("luong", { focusEmployeeId: emp.id })}>💰 Lương</button>
        </div>
      )}

      {canUpdate && (
        <div className="ns-detail__actions">
          {emp.status === "probation" && <button className="btn btn--ghost" onClick={() => setAction("confirm")}>Chuyển chính thức</button>}
          {emp.status === "active" && <button className="btn btn--ghost" onClick={() => setAction("leave_start")}>Cho nghỉ dài hạn</button>}
          {emp.status === "on_leave" && <button className="btn btn--ghost" onClick={() => setAction("leave_end")}>Đi làm lại</button>}
          {!resigned && <button className="btn btn--ghost" onClick={() => setAction("transfer")}>Điều chuyển</button>}
          {!resigned && <button className="btn btn--ghost" onClick={() => setAction("promote")}>Nâng bậc</button>}
          {!resigned && <button className="btn btn--ghost" onClick={() => setAction("suspend")}>Đình chỉ</button>}
          {!resigned && <button className="btn btn--ghost ns-danger" onClick={() => setAction("resign")}>Nghỉ việc</button>}
          {resigned && <button className="btn btn--ghost" onClick={() => setAction("reinstate")}>Tuyển lại</button>}
          {emp.account_username
            ? <button className="btn btn--ghost" onClick={() => setAction("unlink")}>Gỡ tài khoản</button>
            : <button className="btn btn--ghost" onClick={() => setAction("link")}>Nối tài khoản</button>}
        </div>
      )}

      <nav className="ns-tabs ns2-detail__tabs">
        {tabs.map(([id, label]) => (
          <button key={id} className={tab === id ? "is-active" : ""} onClick={() => setTab(id)}>{label}</button>
        ))}
      </nav>

      <div className="ns2-detail__body">
        {tab === "info" && <InfoTab token={token} emp={emp} canUpdate={canUpdate && !resigned} onSaved={() => { reload(); onChanged(); }} />}
        {tab === "salary" && canViewSalary && <SalaryTab token={token} emp={emp} canUpdate={canUpdate && !resigned} onSaved={() => { reload(); onChanged(); }} />}
        {tab === "events" && <EventsTab token={token} employeeId={employeeId} meta={meta} />}
        {tab === "files" && <FilesTab token={token} employeeId={employeeId} canUpdate={canUpdate} />}
        {tab === "activity" && <ActivityTab token={token} employeeId={employeeId} />}
      </div>

      {action && (
        <ActionDialog
          token={token}
          emp={emp}
          meta={meta}
          kind={action}
          onClose={() => setAction(null)}
          onDone={() => { setAction(null); reload(); onChanged(); }}
        />
      )}
    </div>
  );
}

function InfoTab({ token, emp, canUpdate, onSaved }: { token: string; emp: EmployeeDetail; canUpdate: boolean; onSaved: () => void }) {
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState<EmployeeInput>({ ...emp } as unknown as EmployeeInput);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shifts, setShifts] = useState<WorkShift[]>([]);
  useEffect(() => {
    api.attendance.shifts(token).then((r) => setShifts(r.items)).catch(() => setShifts([]));
  }, [token]);
  const shiftName = shifts.find((s) => s.id === emp.default_shift_id)?.name ?? null;

  function set<K extends keyof EmployeeInput>(k: K, v: EmployeeInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.employees.update(token, emp.id, form);
      setEdit(false);
      onSaved();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  if (edit) {
    return (
      <div>
        {error && <div className="banner banner--error">{error}</div>}
        <div className="ns-grid">
          <Field label="Họ tên *"><input value={form.full_name} onChange={(e) => set("full_name", e.target.value)} /></Field>
          <Field label="Chức danh"><input value={form.position ?? ""} onChange={(e) => set("position", e.target.value)} /></Field>
          <Field label="SĐT"><input value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} /></Field>
          <Field label="Email"><input value={form.email ?? ""} onChange={(e) => set("email", e.target.value)} /></Field>
          <Field label="CCCD"><input value={form.national_id ?? ""} onChange={(e) => set("national_id", e.target.value)} /></Field>
          <Field label="Ngày cấp CCCD"><input type="date" value={form.national_id_date ?? ""} onChange={(e) => set("national_id_date", e.target.value)} /></Field>
          <Field label="Nơi cấp CCCD"><input value={form.national_id_place ?? ""} onChange={(e) => set("national_id_place", e.target.value)} /></Field>
          <Field label="Hộ khẩu"><input value={form.permanent_address ?? ""} onChange={(e) => set("permanent_address", e.target.value)} /></Field>
          <Field label="Chỗ ở hiện tại"><input value={form.current_address ?? ""} onChange={(e) => set("current_address", e.target.value)} /></Field>
          <Field label="Liên hệ khẩn (tên)"><input value={form.emergency_contact_name ?? ""} onChange={(e) => set("emergency_contact_name", e.target.value)} /></Field>
          <Field label="Liên hệ khẩn (SĐT)"><input value={form.emergency_contact_phone ?? ""} onChange={(e) => set("emergency_contact_phone", e.target.value)} /></Field>
          <Field label="Ca làm việc">
            <select value={form.default_shift_id ?? ""} onChange={(e) => set("default_shift_id", e.target.value === "" ? null : Number(e.target.value))}>
              <option value="">— chưa gán —</option>
              {shifts.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.start_time}–{s.end_time})</option>)}
            </select>
          </Field>
          <Field label="Ghi chú"><input value={form.note ?? ""} onChange={(e) => set("note", e.target.value)} /></Field>
        </div>
        <div className="ns2-editfoot">
          <button className="btn btn--ghost" onClick={() => setEdit(false)} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>{busy ? "Đang lưu…" : "Lưu"}</button>
        </div>
      </div>
    );
  }

  return (
    <div>
      {canUpdate && (
        <div className="ns-inforow"><button className="btn btn--ghost" onClick={() => setEdit(true)}>Sửa thông tin</button></div>
      )}
      <Section title="Định danh & việc làm">
        <Row k="Mã NV" v={emp.code} /><Row k="Phòng/Tổ" v={emp.department_name} />
        <Row k="Chức danh" v={emp.position} /><Row k="Bậc thợ" v={emp.job_grade} />
        <Row k="Ngày vào" v={fmtDate(emp.hire_date)} /><Row k="Hết thử việc" v={fmtDate(emp.probation_end_date)} />
        <Row k="Ca làm việc" v={shiftName} />
        {emp.resign_date && <Row k="Ngày nghỉ" v={fmtDate(emp.resign_date)} />}
        {emp.resign_reason && <Row k="Lý do nghỉ" v={emp.resign_reason} />}
      </Section>
      <Section title="Cá nhân">
        <Row k="Ngày sinh" v={fmtDate(emp.date_of_birth)} /><Row k="Giới tính" v={emp.gender ? GENDER_LABEL[emp.gender] : null} />
        <Row k="CCCD" v={emp.national_id} /><Row k="Ngày cấp" v={fmtDate(emp.national_id_date)} />
        <Row k="Nơi cấp" v={emp.national_id_place} />
        <Row k="SĐT" v={emp.phone} /><Row k="Email" v={emp.email} />
        <Row k="Hộ khẩu" v={emp.permanent_address} /><Row k="Chỗ ở" v={emp.current_address} />
        <Row k="Liên hệ khẩn" v={emp.emergency_contact_name ? `${emp.emergency_contact_name} · ${emp.emergency_contact_phone ?? ""}` : null} />
      </Section>
      <Section title="Khác">
        <Row k="Ghi chú" v={emp.note} />
      </Section>
    </div>
  );
}

// Nhóm/bậc lương (đồng bộ với module Lương).
const PG_LABEL: Record<string, string> = {
  to_in: "Tổ In", san_xuat: "Sản xuất", van_phong: "Văn phòng",
  to_dan: "Tổ Dán", to_boi: "Tổ Bồi", quan_ly: "Quản lý",
};
const PGK_LABEL: Record<string, string> = {
  tho_1: "Thợ bậc 1", tho_2: "Thợ bậc 2", tho_3: "Thợ bậc 3", phu_1: "Phụ 1", phu_2: "Phụ 2",
};

// Tab Lương & BHXH — dữ liệu nhạy cảm (chỉ hiện với quyền `nhan_su:view_salary`).
function SalaryTab({ token, emp, canUpdate, onSaved }: { token: string; emp: EmployeeDetail; canUpdate: boolean; onSaved: () => void }) {
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState<EmployeeInput>({ ...emp } as unknown as EmployeeInput);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  function set<K extends keyof EmployeeInput>(k: K, v: EmployeeInput[K]) { setForm((f) => ({ ...f, [k]: v })); }
  async function save() {
    setBusy(true); setError(null);
    try { await api.employees.update(token, emp.id, form); setEdit(false); onSaved(); }
    catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  }

  if (edit) {
    return (
      <div>
        {error && <div className="banner banner--error">{error}</div>}
        <div className="ns-grid">
          <Field label="Nhóm lương">
            <select value={form.payroll_group ?? ""} onChange={(e) => set("payroll_group", e.target.value || null)}>
              <option value="">— chưa gán —</option>
              {Object.entries(PG_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Bậc lương (tổ In)">
            <select value={form.pay_grade_key ?? ""} onChange={(e) => set("pay_grade_key", e.target.value || null)}>
              <option value="">— không theo bậc —</option>
              {Object.entries(PGK_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Bậc thợ"><input value={form.job_grade ?? ""} onChange={(e) => set("job_grade", e.target.value)} placeholder="vd 3/7" /></Field>
          <Field label="Số sổ BHXH"><input value={form.social_insurance_no ?? ""} onChange={(e) => set("social_insurance_no", e.target.value)} /></Field>
          <Field label="MST cá nhân"><input value={form.pit_tax_code ?? ""} onChange={(e) => set("pit_tax_code", e.target.value)} /></Field>
          <Field label="Người phụ thuộc"><input type="number" min={0} value={form.dependents_count ?? 0} onChange={(e) => set("dependents_count", Number(e.target.value))} /></Field>
          <Field label="Số tài khoản"><input value={form.bank_account ?? ""} onChange={(e) => set("bank_account", e.target.value)} /></Field>
          <Field label="Ngân hàng"><input value={form.bank_name ?? ""} onChange={(e) => set("bank_name", e.target.value)} /></Field>
        </div>
        <div className="ns2-editfoot">
          <button className="btn btn--ghost" onClick={() => setEdit(false)} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>{busy ? "Đang lưu…" : "Lưu"}</button>
        </div>
      </div>
    );
  }
  return (
    <div>
      {canUpdate && (
        <div className="ns-inforow"><button className="btn btn--ghost" onClick={() => setEdit(true)}>Sửa lương & BHXH</button></div>
      )}
      <Section title="Nhóm & bậc lương">
        <Row k="Nhóm lương" v={emp.payroll_group ? (PG_LABEL[emp.payroll_group] ?? emp.payroll_group) : null} />
        <Row k="Bậc lương" v={emp.pay_grade_key ? (PGK_LABEL[emp.pay_grade_key] ?? emp.pay_grade_key) : null} />
        <Row k="Bậc thợ" v={emp.job_grade} />
      </Section>
      <Section title="BHXH / TNCN">
        <Row k="Số sổ BHXH" v={emp.social_insurance_no} /><Row k="MST cá nhân" v={emp.pit_tax_code} />
        <Row k="Người phụ thuộc" v={String(emp.dependents_count)} />
      </Section>
      <Section title="Ngân hàng">
        <Row k="Tài khoản NH" v={emp.bank_account ? `${emp.bank_account} · ${emp.bank_name ?? ""}` : null} />
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="ns-section">
      <h4 className="ns-section__title">{title}</h4>
      <div className="ns-section__grid">{children}</div>
    </div>
  );
}
function Row({ k, v }: { k: string; v: string | null | undefined }) {
  return (
    <div className="ns-kv"><span className="ns-kv__k">{k}</span><span className="ns-kv__v">{v || "—"}</span></div>
  );
}

function EventsTab({ token, employeeId, meta }: { token: string; employeeId: number; meta: EmployeeMeta | null }) {
  const [events, setEvents] = useState<EmployeeEvent[] | null>(null);
  useEffect(() => {
    api.employees.events(token, employeeId).then((r) => setEvents(r.items)).catch(() => setEvents([]));
  }, [token, employeeId]);
  if (!events) return <p className="ns__empty">Đang tải…</p>;

  // Dịch giá trị thô (mã trạng thái / id phòng / bậc) sang chữ dễ hiểu cho nhân viên.
  const humanize = (field: string | null, v: string | null): string | null => {
    if (!v) return null;
    if (field === "status") return STATUS_LABEL[v] ?? v;
    if (field === "department") {
      const d = meta?.departments.find((x) => String(x.id) === v);
      return d ? d.name : `phòng #${v}`;
    }
    return v; // bậc thợ ("3/7"), chức danh…
  };

  const items: TimelineEntry[] = events.map((ev) => {
    const f = humanize(ev.field, ev.from_value);
    const t = humanize(ev.field, ev.to_value);
    // "Vào làm" tự đủ nghĩa → không kèm "— → Thử việc". Còn lại: "A → B" hoặc chỉ "B".
    let change = "";
    if (ev.event_type !== "hired") {
      if (f && t) change = `${f} → ${t}`;
      else if (t) change = t;
    }
    const detailBits = [fmtDate(ev.effective_date), ev.note || null, ev.actor_name || null].filter(Boolean);
    const tone: TimelineEntry["tone"] | undefined =
      ev.event_type === "hired" ? "rust"
      : ["confirmed", "promoted", "leave_end", "reinstated"].includes(ev.event_type) ? "moss"
      : ev.event_type === "transferred" ? "steel"
      : ["resigned", "suspended", "leave_start"].includes(ev.event_type) ? "signal"
      : undefined;
    return {
      title: change ? `${EVENT_LABEL[ev.event_type] ?? ev.event_type}: ${change}` : (EVENT_LABEL[ev.event_type] ?? ev.event_type),
      meta: detailBits.join(" · "),
      accent: tone === "moss" || tone === "rust",
      tone,
    };
  });
  return <Timeline items={items} emptyText="Chưa có mốc quá trình công tác." />;
}

function FilesTab({ token, employeeId, canUpdate }: { token: string; employeeId: number; canUpdate: boolean }) {
  const [items, setItems] = useState<EmployeeAttachment[] | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.employees.attachments(token, employeeId).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token, employeeId]);
  useEffect(() => { load(); }, [load]);

  return (
    <div>
      {canUpdate && (
        <FilePicker onAdd={async (file, kind) => {
          setBusy(true);
          try { await api.employees.upload(token, employeeId, file, kind); load(); } finally { setBusy(false); }
        }} />
      )}
      {busy && <p className="ns__empty">Đang tải lên…</p>}
      <ul className="ns-filelist">
        {items?.map((a) => (
          <li key={a.id}>
            <a href={assetUrl(a.file_url) ?? "#"} target="_blank" rel="noreferrer">
              {DOC_KIND_LABEL[a.doc_kind] ?? a.doc_kind} · {a.file_name}
            </a>
            <span className="ns-file__date">{fmtDate(a.uploaded_at)}</span>
            {canUpdate && (
              <button className="btn btn--ghost" onClick={async () => { await api.employees.deleteAttachment(token, employeeId, a.id); load(); }}>Xóa</button>
            )}
          </li>
        ))}
        {items?.length === 0 && <li className="ns__empty">Chưa có tệp nào.</li>}
      </ul>
    </div>
  );
}

function ActivityTab({ token, employeeId }: { token: string; employeeId: number }) {
  const [items, setItems] = useState<{ action: string; detail: string; actor_name: string | null; created_at: string }[] | null>(null);
  useEffect(() => {
    api.employees.activity(token, employeeId).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token, employeeId]);
  if (!items) return <p className="ns__empty">Đang tải…</p>;
  const tl: TimelineEntry[] = items.map((a) => ({
    title: a.detail || a.action,
    meta: `${new Date(a.created_at).toLocaleString("vi-VN")}${a.actor_name ? ` · ${a.actor_name}` : ""}`,
  }));
  return <Timeline items={tl} emptyText="Chưa có hoạt động." />;
}

// --- Action dialog (transition / transfer / promote / account) --------------

const ACTION_TITLE: Record<string, string> = {
  confirm: "Chuyển chính thức",
  leave_start: "Cho nghỉ dài hạn",
  leave_end: "Đi làm lại",
  suspend: "Đình chỉ",
  resign: "Cho nghỉ việc",
  reinstate: "Tuyển lại",
  transfer: "Điều chuyển phòng/tổ",
  promote: "Nâng bậc / đổi chức danh",
  link: "Nối tài khoản đăng nhập",
  unlink: "Gỡ tài khoản đăng nhập",
};

function ActionDialog({
  token,
  emp,
  meta,
  kind,
  onClose,
  onDone,
}: {
  token: string;
  emp: EmployeeDetail;
  meta: EmployeeMeta | null;
  kind: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [effective, setEffective] = useState(today);
  const [note, setNote] = useState("");
  const [newDept, setNewDept] = useState<number | "">("");
  const [newGrade, setNewGrade] = useState("");
  const [newPos, setNewPos] = useState("");
  const [resignReason, setResignReason] = useState("");
  const [linkUser, setLinkUser] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isTransition = kind !== "link" && kind !== "unlink";

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (kind === "link") {
        if (linkUser === "") throw new ApiError("Chọn tài khoản để nối.", 400);
        await api.employees.linkAccount(token, emp.id, linkUser);
      } else if (kind === "unlink") {
        await api.employees.unlinkAccount(token, emp.id);
      } else {
        const input: EmployeeTransitionInput = { kind, effective_date: effective, note: note || undefined };
        if (kind === "transfer") input.new_department_id = newDept === "" ? undefined : newDept;
        if (kind === "promote") { input.new_job_grade = newGrade || undefined; input.new_position = newPos || undefined; }
        if (kind === "resign") input.resign_reason = resignReason;
        await api.employees.transition(token, emp.id, input);
      }
      onDone();
    } catch (e) {
      setError(errMsg(e));
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal ns-modal--top" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>{ACTION_TITLE[kind] ?? kind}</h2>
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng">×</button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}

          {kind === "unlink" && <p>Gỡ liên kết tài khoản <strong>{emp.account_username}</strong> khỏi hồ sơ này?</p>}

          {kind === "link" && (
            <Field label="Tài khoản chưa gắn">
              <select value={linkUser} onChange={(e) => setLinkUser(e.target.value === "" ? "" : Number(e.target.value))}>
                <option value="">— chọn —</option>
                {meta?.unlinked_users.map((u) => <option key={u.id} value={u.id}>{u.username} · {u.name}</option>)}
              </select>
            </Field>
          )}

          {isTransition && (
            <Field label="Ngày hiệu lực"><input type="date" value={effective} onChange={(e) => setEffective(e.target.value)} /></Field>
          )}
          {kind === "transfer" && (
            <Field label="Phòng/Tổ mới">
              <select value={newDept} onChange={(e) => setNewDept(e.target.value === "" ? "" : Number(e.target.value))}>
                <option value="">— chọn —</option>
                {meta?.departments.filter((d) => d.id !== emp.department_id).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </Field>
          )}
          {kind === "promote" && (
            <>
              <Field label="Bậc thợ mới"><input value={newGrade} onChange={(e) => setNewGrade(e.target.value)} placeholder={emp.job_grade ?? "vd 4/7"} /></Field>
              <Field label="Chức danh mới (tùy chọn)"><input value={newPos} onChange={(e) => setNewPos(e.target.value)} /></Field>
            </>
          )}
          {kind === "resign" && (
            <Field label="Lý do nghỉ *"><input value={resignReason} onChange={(e) => setResignReason(e.target.value)} /></Field>
          )}
          {isTransition && kind !== "resign" && (
            <Field label="Ghi chú"><input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          )}
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={submit} disabled={busy}>{busy ? "Đang xử lý…" : "Xác nhận"}</button>
        </footer>
      </div>
    </div>
  );
}
