// Hồ sơ nhân sự (module `nhan_su`, lát #1). Danh sách + KPI + Wizard thêm (5 bước) +
// Trang hồ sơ (tab Thông tin / Quá trình công tác / Đính kèm / Nhật ký) + dialog Đổi
// trạng thái / Điều chuyển / Nâng bậc (sinh Quá trình công tác) + nối/tạo tài khoản.
// Backend là cổng quyền thật (403); useCan chỉ ẩn/hiện nút cho gọn UX.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  api,
  ApiError,
  assetUrl,
  type AuditRow,
  type EmployeeAttachment,
  type EmployeeDetail,
  type EmployeeEvent,
  type EmployeeInput,
  type EmployeeKpis,
  type EmployeeMeta,
  type EmployeeRow,
  type EmployeeTransitionInput,
  type Session,
  type UpdateRequest,
  type UserRow,
  type WorkShift,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { money } from "../utils/format";
import type { NavigateFn } from "../components/AppShell";
import { Timeline, type TimelineEntry } from "../components/Timeline";
import {
  Users,
  Hourglass,
  UserCheck,
  AlertCircle,
  Search,
  Download,
  UserPlus,
  ChevronDown,
  Calendar,
  Briefcase,
  Clock,
  CreditCard,
  FileText,
  Activity,
  Phone,
  Mail,
  MapPin,
  Lock,
  Paperclip,
  Trash2,
  Edit2,
  TrendingUp,
  UserMinus,
  AlertTriangle,
  Key,
  X
} from "lucide-react";
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
  return end >= now && end <= now + 30 * 24 * 3600 * 1000; // khớp KPI backend (30 ngày)
}

function getAvatarClass(name: string): string {
  const firstChar = name.trim().slice(0, 1).toLowerCase();
  const validChars = ["a", "b", "c", "d", "e", "g", "h", "k", "l", "m", "n", "p", "q", "s", "t", "u", "v", "x"];
  if (validChars.includes(firstChar)) return `ns2-row__av--${firstChar}`;
  return "ns2-row__av--default";
}

export function NhanSuPage({ navigate }: { navigate?: NavigateFn }) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("nhan_su", "create");
  const canApprove = can("nhan_su", "approve");
  const canSalary = can("luong", "update");   // có quyền khai lương → hiện bước "Lương" khi thêm NV

  const [data, setData] = useState<{ items: EmployeeRow[]; total: number; kpis: EmployeeKpis } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [deptFilter, setDeptFilter] = useState<number | "">("");
  const [accountFilter, setAccountFilter] = useState(""); // "" | "yes" | "no"
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
        has_account: accountFilter === "" ? undefined : accountFilter === "yes",
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
  }, [token, q, statusFilter, deptFilter, accountFilter, sort, page]);

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
        e.code, e.full_name, e.department_name ?? "", e.role_name ?? e.position ?? "", e.job_grade ?? "",
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
            <button type="button" className={`btn btn--ghost${reqCount > 0 ? " ns2-reqbtn--on" : ""}`} style={{ display: "inline-flex", alignItems: "center", gap: "6px" }} onClick={() => setReqOpen(true)}>
              <Activity size={14} />
              Yêu cầu cập nhật{reqCount > 0 ? ` (${reqCount})` : ""}
            </button>
          )}
          {canCreate && (
            <button type="button" className="btn btn--primary" style={{ display: "inline-flex", alignItems: "center", gap: "6px" }} onClick={() => setWizardOpen(true)}>
              <UserPlus size={14} />
              Thêm nhân viên
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
            <div className="ns-search-wrapper">
              <Search className="ns-search-icon" size={16} />
              <input
                className="ns__search"
                placeholder="Tìm tên / mã / CCCD / SĐT…"
                value={q}
                onChange={(e) => { setPage(1); setEndingSoon(false); setQ(e.target.value); }}
              />
            </div>
            <div className="ns2__filters">
              <div className="ns-select-wrapper">
                <select value={statusFilter} onChange={(e) => { setPage(1); setEndingSoon(false); setStatusFilter(e.target.value); }}>
                  <option value="">Mọi trạng thái</option>
                  {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <ChevronDown className="ns-select-chevron" size={14} />
              </div>
              <div className="ns-select-wrapper">
                <select value={deptFilter} onChange={(e) => { setPage(1); setDeptFilter(e.target.value === "" ? "" : Number(e.target.value)); }}>
                  <option value="">Mọi phòng/tổ</option>
                  {meta?.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
                <ChevronDown className="ns-select-chevron" size={14} />
              </div>
              <div className="ns-select-wrapper">
                <select
                  value={accountFilter}
                  onChange={(e) => { setPage(1); setEndingSoon(false); setAccountFilter(e.target.value); }}
                  title="Lọc theo tài khoản đăng nhập"
                >
                  <option value="">Tài khoản: tất cả</option>
                  <option value="yes">Có tài khoản</option>
                  <option value="no">Chưa có tài khoản</option>
                </select>
                <ChevronDown className="ns-select-chevron" size={14} />
              </div>
              <div className="ns-select-wrapper">
                <select value={sort} onChange={(e) => { setPage(1); setSort(e.target.value); }} title="Sắp xếp">
                  <option value="code">Mã ↑</option>
                  <option value="full_name">Tên A→Z</option>
                  <option value="-hire_date">Mới vào trước</option>
                  <option value="hire_date">Vào lâu trước</option>
                  <option value="status">Trạng thái</option>
                </select>
                <ChevronDown className="ns-select-chevron" size={14} />
              </div>
              <button className="ns-btn-excel" onClick={exportExcel} disabled={exporting}>
                <Download size={14} />
                {exporting ? "Đang xuất…" : "Xuất Excel"}
              </button>
              {endingSoon && (
                <button className="ns2-chip" onClick={() => setEndingSoon(false)}>
                  <AlertCircle size={14} />
                  Sắp hết thử việc ×
                </button>
              )}
            </div>
          </div>

          {error && <div className="banner banner--error" role="alert">{error}</div>}

          <div className="ns-table-wrapper">
            <table className="ns-table-records">
              <thead>
                <tr>
                  <th>Mã NV</th>
                  <th>Nhân viên</th>
                  <th>Phòng/Tổ</th>
                  <th>Chức danh</th>
                  <th>Bậc thợ</th>
                  <th>Ngày vào làm</th>
                  <th>Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan={7} className="ns__empty">Đang tải danh sách…</td>
                  </tr>
                )}
                {!loading && rows.map((e) => {
                  const avatarClass = getAvatarClass(e.full_name);
                  return (
                    <tr
                      key={e.id}
                      className="ns-table-row"
                      onClick={() => setSelectedId(e.id)}
                    >
                      <td className="ns-cell-code">{e.code}</td>
                      <td>
                        <div className="ns-cell-employee">
                          <span className={`ns-table-avatar ${avatarClass}`}>
                            {e.full_name.trim().slice(0, 1).toUpperCase()}
                          </span>
                          <span className="ns-cell-name">
                            {e.full_name}
                            {e.account_username && (
                              <span title="Có tài khoản">
                                <Key size={13} style={{ marginLeft: "2px" }} />
                              </span>
                            )}
                          </span>
                        </div>
                      </td>
                      <td>{e.department_name ?? "—"}</td>
                      <td>{e.role_name ?? e.position ?? "—"}</td>
                      <td>{e.job_grade ?? "—"}</td>
                      <td>{fmtDate(e.hire_date)}</td>
                      <td>
                        <StatusBadge status={e.status} />
                      </td>
                    </tr>
                  );
                })}
                {!loading && rows.length === 0 && (
                  <tr>
                    <td colSpan={7} className="ns__empty">
                      {endingSoon ? "Không có ai sắp hết thử việc." : "Chưa có nhân viên nào."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="ns__pager">
            <span>{data ? `${data.total} nhân viên` : ""}</span>
            <div className="ns__pagerbtns">
              <button type="button" className="btn btn--ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>‹</button>
              <span>{page} / {totalPages}</span>
              <button type="button" className="btn btn--ghost" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>›</button>
            </div>
          </div>
        </section>
      </div>

      {selectedId != null && (
        <div className="ns-modal" role="dialog" aria-modal="true" onClick={() => setSelectedId(null)}>
          <div className="ns-detail-modal-box" onClick={(e) => e.stopPropagation()}>
            <EmployeeDetailPanel
              token={token!}
              employeeId={selectedId}
              meta={meta}
              navigate={navigate}
              onClose={() => setSelectedId(null)}
              onChanged={load}
            />
          </div>
        </div>
      )}

      {wizardOpen && meta && (
        <EmployeeWizard
          token={token!}
          meta={meta}
          canSalary={canSalary}
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
    <div className="ns2__kpis">
      <div className="ns__kpi ns__kpi--total">
        <span className="ns__kpi-icon"><Users size={16} /></span>
        <div className="ns__kpi-content">
          <span className="ns__kpilabel">Tổng nhân sự</span>
          <span className="ns__kpival">{kpis.total}</span>
        </div>
      </div>
      <button type="button" className="ns__kpi ns__kpi--probation" onClick={onPickProbation}>
        <span className="ns__kpi-icon"><Hourglass size={16} /></span>
        <div className="ns__kpi-content">
          <span className="ns__kpilabel">Đang thử việc</span>
          <span className="ns__kpival">{kpis.probation}</span>
        </div>
      </button>
      <div className="ns__kpi ns__kpi--active">
        <span className="ns__kpi-icon"><UserCheck size={16} /></span>
        <div className="ns__kpi-content">
          <span className="ns__kpilabel">Chính thức</span>
          <span className="ns__kpival">{kpis.active}</span>
        </div>
      </div>
      <button type="button" className="ns__kpi ns__kpi--action" onClick={onPickEndingSoon}>
        <span className="ns__kpi-icon"><AlertCircle size={16} /></span>
        <div className="ns__kpi-content">
          <span className="ns__kpilabel">Sắp hết thử việc</span>
          <span className="ns__kpival">{kpis.probation_ending_soon}</span>
        </div>
      </button>
    </div>
  );
}

// --- Wizard thêm nhân viên (5 bước) ----------------------------------------

export function EmployeeWizard({
  token,
  meta,
  canSalary,
  onClose,
  onCreated,
  initialDepartmentId,
}: {
  token: string;
  meta: EmployeeMeta;
  canSalary: boolean;
  onClose: () => void;
  onCreated: (id: number) => void;
  // Chọn sẵn tổ khi mở từ màn Phòng ban (khỏi chọn lại). Bỏ trống → tổ đầu danh sách như cũ.
  initialDepartmentId?: number | null;
}) {
  const STEPS = ["Định danh & việc làm", "Cá nhân", "Lương & BHXH", "Đính kèm", "Tài khoản"];
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<EmployeeInput>({
    full_name: "",
    department_id: initialDepartmentId ?? meta.departments[0]?.id ?? null,
    status: "probation",
    hire_date: new Date().toISOString().slice(0, 10),
    dependents_count: 0,
  });
  const [files, setFiles] = useState<{ file: File; doc_kind: string }[]>([]);
  const [makeAccount, setMakeAccount] = useState(false);
  const [acc, setAcc] = useState({ username: "", password: "", role_id: "" as number | "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Lương cơ bản = mức đóng BH; các khoản phụ cấp là số cố định khai riêng từng nhân viên.
  const [luongViTri, setLuongViTri] = useState(0);
  const [luongTrachNhiem, setLuongTrachNhiem] = useState(0);
  const [allowance, setAllowance] = useState(0);
  const [chuyenCan, setChuyenCan] = useState(0);
  // BH đóng ở nơi khác → công ty chỉ đóng TNLĐ-BNN (không trừ BHXH/BHYT/BHTN của NV).
  const [insuranceElsewhere, setInsuranceElsewhere] = useState(false);
  // Đoàn viên công đoàn → mới bị trừ đoàn phí công đoàn (mặc định không).
  const [unionMember, setUnionMember] = useState(false);
  // Chống tạo NV trùng nếu upload tệp lỗi sau khi hồ sơ đã được tạo.
  const [createdId, setCreatedId] = useState<number | null>(null);
  // Thâm niên đã có TRƯỚC khi vào làm — nhập theo NĂM (cho phép lẻ); submit lưu × 12 (tháng).
  const [priorSeniorityYears, setPriorSeniorityYears] = useState(0);

  function set<K extends keyof EmployeeInput>(k: K, v: EmployeeInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  const salaryBase = luongViTri + luongTrachNhiem;
  // Chỉ để XEM: tổng thâm niên = thâm niên trước khi vào + thời gian từ ngày vào tới nay.
  const seniorityText = seniorityLabel(priorSeniorityYears, form.hire_date);

  async function submit() {
    setError(null);
    if (!form.full_name.trim()) {
      setStep(0);
      setError("Họ tên là bắt buộc.");
      return;
    }
    if (canSalary && luongViTri <= 0) {
      setStep(2);
      setError("Lương cơ bản (đóng BH) của nhân viên phải lớn hơn 0.");
      return;
    }
    setBusy(true);
    try {
      // Giữ id đã tạo để nếu lỗi giữa chừng, bấm Lưu lại KHÔNG tạo nhân viên trùng.
      let id = createdId;
      if (id == null) {
        const input: EmployeeInput = { ...form };
        input.prior_seniority_months = Math.round(priorSeniorityYears * 12);
        if (makeAccount && acc.username.trim()) {
          input.account = {
            username: acc.username.trim(),
            password: acc.password,
            role_id: acc.role_id === "" ? null : acc.role_id,
          };
        }
        if (canSalary) {
          input.initial_salary = {
            effective_from: form.hire_date || new Date().toISOString().slice(0, 10),
            luong_vi_tri: luongViTri,
            luong_trach_nhiem: luongTrachNhiem,
            allowance,
            chuyen_can: chuyenCan,
            insurance_elsewhere: insuranceElsewhere,
            union_member: unionMember,
          };
        }
        const res = await api.employees.create(token, input);
        id = res.employee.id;
        setCreatedId(id);
      }
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

          {STEPS[step] === "Định danh & việc làm" && (
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
              <Field label="Loại / Bậc thợ">
                <input
                  value={form.job_grade ?? ""}
                  onChange={(e) => set("job_grade", e.target.value)}
                  placeholder="vd Thợ bậc 3, Thợ phụ"
                />
              </Field>
              <Field label="Thâm niên khi vào làm (năm)">
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={priorSeniorityYears || ""}
                  onChange={(e) =>
                    setPriorSeniorityYears(e.target.value === "" ? 0 : Number(e.target.value))
                  }
                  placeholder="0"
                />
                {seniorityText && <span className="ns-field__hint">{seniorityText}</span>}
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

          {STEPS[step] === "Cá nhân" && (
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
              <Field label="Ghi chú"><input value={form.note ?? ""} onChange={(e) => set("note", e.target.value)} placeholder="Ghi gì tuỳ ý…" /></Field>
            </div>
          )}

          {STEPS[step] === "Lương & BHXH" && (
            <div className="ns-grid">
              {canSalary ? (
                <>
                  <div className="ns-wizard__salary-intro ns-wizard__full">
                    <strong>Mức lương riêng của nhân viên</strong>
                    <span>BHXH/BHYT/BHTN đóng trên lương cơ bản. Các khoản phụ cấp là số cố định, cộng phẳng mỗi tháng.</span>
                  </div>
                  <Field label="Lương cơ bản (đóng BH) *">
                    <input type="number" min={0} step={100000} value={luongViTri} onChange={(e) => setLuongViTri(Number(e.target.value))} />
                  </Field>
                  <Field label="Lương trách nhiệm">
                    <input type="number" min={0} step={100000} value={luongTrachNhiem} onChange={(e) => setLuongTrachNhiem(Number(e.target.value))} />
                  </Field>
                  <div className="ns-wizard__salary-total ns-wizard__full">
                    <span>Mức nền theo hợp đồng</span>
                    <strong>{money(salaryBase)}</strong>
                  </div>
                  <Field label="Thưởng chuyên cần">
                    <input type="number" min={0} step={50000} value={chuyenCan} onChange={(e) => setChuyenCan(Number(e.target.value))} />
                  </Field>
                  <Field label="Các khoản phụ cấp">
                    <input type="number" min={0} step={50000} value={allowance} onChange={(e) => setAllowance(Number(e.target.value))} />
                  </Field>
                  <label className="ns-check ns-wizard__full">
                    <input type="checkbox" checked={insuranceElsewhere} onChange={(e) => setInsuranceElsewhere(e.target.checked)} />
                    Bảo hiểm đóng ở nơi khác — công ty chỉ đóng TNLĐ-BNN (không trừ BHXH/BHYT/BHTN của NV)
                  </label>
                  <label className="ns-check ns-wizard__full">
                    <input type="checkbox" checked={unionMember} onChange={(e) => setUnionMember(e.target.checked)} />
                    Đoàn viên công đoàn — có trừ đoàn phí công đoàn
                  </label>
                  {form.status === "probation" && salaryBase > 0 && (
                    <div className="ns-wizard__hint ns-wizard__hint--tv">
                      Thử việc: hệ thống tính 80% mức nền, dự kiến {money(salaryBase * 0.8)} trước công và phụ cấp.
                    </div>
                  )}
                </>
              ) : (
                <div className="ns-wizard__hint">Bạn không có quyền khai lương. Hồ sơ sẽ được tạo trước và người có quyền Lương sẽ bổ sung mức sau.</div>
              )}
              <div className="ns-wizard__section-title ns-wizard__full">Bảo hiểm, thuế và tài khoản nhận lương</div>
              <Field label="Số sổ BHXH"><input value={form.social_insurance_no ?? ""} onChange={(e) => set("social_insurance_no", e.target.value)} /></Field>
              <Field label="MST cá nhân"><input value={form.pit_tax_code ?? ""} onChange={(e) => set("pit_tax_code", e.target.value)} /></Field>
              <Field label="Người phụ thuộc"><input type="number" min={0} value={form.dependents_count ?? 0} onChange={(e) => set("dependents_count", Number(e.target.value))} /></Field>
              <Field label="Số tài khoản"><input value={form.bank_account ?? ""} onChange={(e) => set("bank_account", e.target.value)} /></Field>
              <Field label="Ngân hàng"><input value={form.bank_name ?? ""} onChange={(e) => set("bank_name", e.target.value)} /></Field>
            </div>
          )}

          {STEPS[step] === "Đính kèm" && (
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

          {STEPS[step] === "Tài khoản" && (
            <div>
              <label className="ns-check">
                <input type="checkbox" checked={makeAccount} onChange={(e) => setMakeAccount(e.target.checked)} />
                Tạo tài khoản đăng nhập cho nhân viên này
              </label>
              {makeAccount && (
                <div className="ns-grid" style={{ marginTop: 12 }}>
                  <Field label="Tên đăng nhập *"><input value={acc.username} onChange={(e) => setAcc({ ...acc, username: e.target.value })} /></Field>
                  <Field label="Mật khẩu tạm *"><input type="text" value={acc.password} onChange={(e) => setAcc({ ...acc, password: e.target.value })} /></Field>
                  {/* Không có vai trò thì NV đăng nhập được nhưng không thấy gì — phải chọn ngay
                      tại đây, đừng bắt sang màn khác gán. Vai trò thuộc phòng của hồ sơ. */}
                  <Field label="Vai trò">
                    <select
                      value={acc.role_id}
                      onChange={(e) => setAcc({ ...acc, role_id: e.target.value ? Number(e.target.value) : "" })}
                    >
                      <option value="">— chưa gán (đăng nhập nhưng chưa thấy gì) —</option>
                      {meta.roles
                        .filter((r) => r.department_id === form.department_id)
                        .map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </select>
                  </Field>
                </div>
              )}
              <div className="ns-review">
                <h4>Xem lại</h4>
                <p><strong>{form.full_name || "(chưa nhập tên)"}</strong> · {meta.departments.find((d) => d.id === form.department_id)?.name ?? "—"} · {form.status === "active" ? "Chính thức" : "Thử việc"}</p>
                {canSalary && (
                  <p>
                    Lương cơ bản <strong>{money(salaryBase)}</strong>
                  </p>
                )}
                <p>Ngày vào {fmtDate(form.hire_date)} · {files.length} tệp đính kèm{makeAccount && acc.username ? ` · tài khoản "${acc.username}"${acc.role_id ? ` (${meta.roles.find((r) => r.id === acc.role_id)?.name})` : " — CHƯA gán vai trò"}` : ""}</p>
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

/** "Thâm niên hiện tại: X năm Y tháng" (chỉ để xem) = thâm niên khai trước khi vào (đổi ra
 *  tháng) + số tháng từ ngày vào tới nay. Trả null khi chưa có gì để hiện. */
function seniorityLabel(priorYears: number, hireDate?: string | null): string | null {
  const prior = Math.round((priorYears || 0) * 12);
  let fromHire = 0;
  if (hireDate) {
    const h = new Date(hireDate);
    if (!Number.isNaN(h.getTime())) {
      const now = new Date();
      fromHire = Math.max(
        0,
        (now.getFullYear() - h.getFullYear()) * 12 + (now.getMonth() - h.getMonth()),
      );
    }
  }
  const total = prior + fromHire;
  if (total <= 0) return null;
  return `Thâm niên hiện tại: ${Math.floor(total / 12)} năm ${total % 12} tháng`;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  const required = label.trimEnd().endsWith("*");
  const text = required ? label.trimEnd().slice(0, -1).trimEnd() : label;
  return (
    <label className="ns-field">
      <span className="ns-field__label">
        {text}{required && <span className="ns-field__required" aria-hidden="true"> *</span>}
      </span>
      {children}
    </label>
  );
}

type Tab = "info" | "salary" | "account" | "events" | "files" | "activity";

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
  const canViewAccount = can("nguoi_dung", "read");
  const [emp, setEmp] = useState<EmployeeDetail | null>(null);
  const [tab, setTab] = useState<Tab>("info");
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<string | null>(null); // dialog kind
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [editInfo, setEditInfo] = useState(false);
  const [editSalary, setEditSalary] = useState(false);

  const reload = useCallback(() => {
    api.employees.get(token, employeeId).then(setEmp).catch((e) => setError(errMsg(e)));
  }, [token, employeeId]);

  useEffect(() => {
    setTab("info");
    setEditInfo(false);
    setEditSalary(false);
    reload();
  }, [reload]);

  if (!emp) {
    return <div className="ns2-detail__loading">{error ?? "Đang tải hồ sơ…"}</div>;
  }

  const resigned = emp.status === "resigned";
  const tabs: [Tab, string][] = [
    ["info", "Thông tin"],
    ...(canViewSalary ? [["salary", "Lương & BHXH"] as [Tab, string]] : []),
    // Gộp từ màn Người dùng (đã bỏ): mọi tài khoản thuộc một hồ sơ nên quản ngay tại đây.
    ...(canViewAccount ? [["account", "Tài khoản & Quyền"] as [Tab, string]] : []),
    ["events", "Quá trình công tác"],
    ["files", "Đính kèm"],
    ["activity", "Nhật ký"],
  ];

  return (
    <div className="ns2-detail">
      <header className="ns2-detail__head">
        <button type="button" className="ns-modal__close-btn" onClick={onClose} aria-label="Đóng">
          <X size={18} />
        </button>
        <div className="ns-avatar ns-avatar--lg">
          {assetUrl(emp.photo_url) ? (
            <img src={assetUrl(emp.photo_url)!} alt={emp.full_name} />
          ) : (
            emp.full_name.trim().slice(0, 1).toUpperCase()
          )}
        </div>
        <div className="ns2-detail__id">
          <h2>
            {emp.full_name}
            <StatusBadge status={emp.status} />
          </h2>
          <p className="ns-detail__meta">
            <Briefcase size={13} />
            {emp.code} · {emp.department_name ?? "—"} · {emp.position ?? "—"}{emp.job_grade ? ` · Bậc ${emp.job_grade}` : ""}
          </p>
          <p className="ns-detail__meta">
            <Calendar size={13} />
            Vào làm {fmtDate(emp.hire_date)} · {emp.account_username ? `🔑 ${emp.account_username}` : "chưa nối tài khoản"}
          </p>
        </div>
      </header>

      {(navigate || canUpdate) && (
        <div className="ns-detail__actions">
          <div className="ns-detail__shortcuts">
            {navigate && (
              <>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => navigate("cham-cong", { focusEmployeeId: emp.id })}>
                  <Clock size={12} />
                  Chấm công
                </button>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => navigate("nghi-phep", { focusEmployeeId: emp.id })}>
                  <Calendar size={12} />
                  Nghỉ phép
                </button>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => navigate("luong", { focusEmployeeId: emp.id })}>
                  <CreditCard size={12} />
                  Lương
                </button>
              </>
            )}
          </div>
          <div className="ns-detail__ops">
            {canUpdate && tab === "info" && !resigned && (
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setEditInfo(!editInfo)}
              >
                <Edit2 size={12} />
                {editInfo ? "Hủy sửa" : "Sửa thông tin"}
              </button>
            )}
            {canUpdate && tab === "salary" && canViewSalary && !resigned && (
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setEditSalary(!editSalary)}
              >
                <Edit2 size={12} />
                {editSalary ? "Hủy sửa" : "Sửa lương & BHXH"}
              </button>
            )}
            {canUpdate && (
              <div className="ns-dropdown">
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => setDropdownOpen(!dropdownOpen)}
                >
                  Thao tác hồ sơ
                  <ChevronDown size={12} />
                </button>
                {dropdownOpen && (
                  <div className="ns-dropdown-menu">
                    {emp.status === "probation" && (
                      <button type="button" className="ns-dropdown-item" onClick={() => { setAction("confirm"); setDropdownOpen(false); }}>
                        <UserCheck size={14} /> Chuyển chính thức
                      </button>
                    )}
                    {emp.status === "active" && (
                      <button type="button" className="ns-dropdown-item" onClick={() => { setAction("leave_start"); setDropdownOpen(false); }}>
                        <UserMinus size={14} /> Cho nghỉ dài hạn
                      </button>
                    )}
                    {emp.status === "on_leave" && (
                      <button type="button" className="ns-dropdown-item" onClick={() => { setAction("leave_end"); setDropdownOpen(false); }}>
                        <UserCheck size={14} /> Đi làm lại
                      </button>
                    )}
                    {!resigned && (
                      <button type="button" className="ns-dropdown-item" onClick={() => { setAction("transfer"); setDropdownOpen(false); }}>
                        <TrendingUp size={14} /> Điều chuyển tổ
                      </button>
                    )}
                    {!resigned && (
                      <button type="button" className="ns-dropdown-item" onClick={() => { setAction("promote"); setDropdownOpen(false); }}>
                        <TrendingUp size={14} /> Nâng bậc / Chức danh
                      </button>
                    )}
                    {!resigned && (
                      <button type="button" className="ns-dropdown-item" onClick={() => { setAction("suspend"); setDropdownOpen(false); }}>
                        <AlertTriangle size={14} /> Đình chỉ công tác
                      </button>
                    )}
                    {!resigned && (
                      <button type="button" className="ns-dropdown-item ns-danger" onClick={() => { setAction("resign"); setDropdownOpen(false); }}>
                        <UserMinus size={14} /> Thôi việc / Nghỉ việc
                      </button>
                    )}
                    {resigned && (
                      <button type="button" className="ns-dropdown-item" onClick={() => { setAction("reinstate"); setDropdownOpen(false); }}>
                        <UserPlus size={14} /> Tuyển dụng lại
                      </button>
                    )}
                    {/* Tài khoản đăng nhập quản ở tab "Tài khoản & Quyền" — mọi tài khoản
                        thuộc một hồ sơ nên không còn "gỡ liên kết". */}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      <nav className="ns-tabs ns2-detail__tabs">
        {tabs.map(([id, label]) => (
          <button key={id} className={tab === id ? "is-active" : ""} onClick={() => setTab(id)}>{label}</button>
        ))}
      </nav>

      <div className="ns2-detail__body">
        {tab === "info" && <InfoTab token={token} emp={emp} edit={editInfo} setEdit={setEditInfo} onSaved={() => { reload(); onChanged(); }} />}
        {tab === "salary" && canViewSalary && <SalaryTab token={token} emp={emp} edit={editSalary} setEdit={setEditSalary} onSaved={() => { reload(); onChanged(); }} />}
        {tab === "account" && canViewAccount && <AccountTab token={token} emp={emp} meta={meta} onChanged={() => { reload(); onChanged(); }} />}
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

function InfoTab({
  token,
  emp,
  edit,
  setEdit,
  onSaved,
}: {
  token: string;
  emp: EmployeeDetail;
  edit: boolean;
  setEdit: (e: boolean) => void;
  onSaved: () => void;
}) {
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
      <div className="ns-info-sections">
        <InfoCard title="Định danh & việc làm" icon={Briefcase}>
          <InfoField label="Mã NV" value={emp.code} icon={Briefcase} />
          <InfoField label="Phòng/Tổ" value={emp.department_name} icon={Users} />
          <InfoField label="Chức danh" value={emp.position} icon={UserCheck} />
          <InfoField label="Bậc thợ" value={emp.job_grade} icon={TrendingUp} />
          <InfoField label="Ngày vào" value={fmtDate(emp.hire_date)} icon={Calendar} />
          <InfoField label="Hết thử việc" value={fmtDate(emp.probation_end_date)} icon={Calendar} />
          <InfoField label="Ca làm việc" value={shiftName} icon={Clock} />
          {emp.resign_date && <InfoField label="Ngày nghỉ" value={fmtDate(emp.resign_date)} icon={Calendar} />}
          {emp.resign_reason && <InfoField label="Lý do nghỉ" value={emp.resign_reason} icon={FileText} />}
        </InfoCard>
        <InfoCard title="Cá nhân" icon={Users}>
          <InfoField label="Ngày sinh" value={fmtDate(emp.date_of_birth)} icon={Calendar} />
          <InfoField label="Giới tính" value={emp.gender ? GENDER_LABEL[emp.gender] : null} icon={Users} />
          <InfoField label="CCCD" value={emp.national_id} icon={FileText} />
          <InfoField label="Ngày cấp" value={fmtDate(emp.national_id_date)} icon={Calendar} />
          <InfoField label="Nơi cấp" value={emp.national_id_place} icon={MapPin} />
          <InfoField label="SĐT" value={emp.phone} icon={Phone} />
          <InfoField label="Email" value={emp.email} icon={Mail} />
          <InfoField label="Hộ khẩu" value={emp.permanent_address} icon={MapPin} />
          <InfoField label="Chỗ ở" value={emp.current_address} icon={MapPin} />
          <InfoField label="Liên hệ khẩn" value={emp.emergency_contact_name ? `${emp.emergency_contact_name} · ${emp.emergency_contact_phone ?? ""}` : null} icon={Phone} />
        </InfoCard>
      </div>
      <InfoCard title="Khác" icon={FileText}>
        <InfoField label="Ghi chú" value={emp.note} icon={FileText} />
      </InfoCard>
    </div>
  );
}

// Tab Lương & BHXH — dữ liệu nhạy cảm (chỉ hiện với quyền `nhan_su:view_salary`).
// "Nhóm lương / Bậc lương" (`payroll_group` / `pay_grade_key`) đã GỠ khỏi màn: engine không
// còn đọc, để lại chỉ khiến người dùng tưởng đang gán lương (PRD Cấu hình lương §8, bệnh B3).
// Cột vẫn còn trong DB — mức lương thật gán ở Lương → Lương nhân viên (trỏ dòng thang bậc).
function SalaryTab({
  token,
  emp,
  edit,
  setEdit,
  onSaved,
}: {
  token: string;
  emp: EmployeeDetail;
  edit: boolean;
  setEdit: (e: boolean) => void;
  onSaved: () => void;
}) {
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
      <div className="ns-info-sections">
        <InfoCard title="Bậc thợ" icon={CreditCard}>
          <InfoField label="Bậc thợ" value={emp.job_grade} icon={TrendingUp} />
        </InfoCard>
        <InfoCard title="BHXH / TNCN" icon={FileText}>
          <InfoField label="Số sổ BHXH" value={emp.social_insurance_no} icon={FileText} />
          <InfoField label="MST cá nhân" value={emp.pit_tax_code} icon={FileText} />
          <InfoField label="Người phụ thuộc" value={String(emp.dependents_count)} icon={Users} />
        </InfoCard>
      </div>
      <InfoCard title="Ngân hàng" icon={Lock}>
        <InfoField label="Tài khoản NH" value={emp.bank_account ? `${emp.bank_account} · ${emp.bank_name ?? ""}` : null} icon={CreditCard} />
      </InfoCard>
    </div>
  );
}

/** Mật khẩu tạm dễ đọc (bỏ 0/O/1/l/I để khỏi đọc nhầm khi bàn giao). */
function genPassword(len = 12): string {
  const chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789";
  const buf = new Uint32Array(len);
  crypto.getRandomValues(buf);
  return Array.from(buf, (n) => chars[n % chars.length]).join("");
}

function deviceLabel(ua: string | null): string {
  if (!ua) return "Thiết bị không rõ";
  const browser = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome"
    : /Safari\//.test(ua) ? "Safari" : /Firefox\//.test(ua) ? "Firefox" : "Trình duyệt khác";
  const os = /Windows/.test(ua) ? "Windows" : /Mac OS/.test(ua) ? "macOS"
    : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : "Hệ khác";
  return `${browser} · ${os}`;
}

/** Tab "Tài khoản & Quyền" — gộp từ màn Người dùng cũ (đã bỏ). Mọi tài khoản đều thuộc một
 * hồ sơ, nên đây là nơi DUY NHẤT cấp/quản tài khoản đăng nhập của nhân viên. */
function AccountTab({
  token,
  emp,
  meta,
  onChanged,
}: {
  token: string;
  emp: EmployeeDetail;
  meta: EmployeeMeta | null;
  onChanged: () => void;
}) {
  const can = useCan();
  const canCreate = can("nhan_su", "update");
  const canAssignRole = can("nguoi_dung", "assign_role");
  const canReset = can("nguoi_dung", "reset_password");
  const canLock = can("nguoi_dung", "lock");
  const canRevoke = can("nguoi_dung", "revoke_sessions");

  const [row, setRow] = useState<UserRow | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activity, setActivity] = useState<AuditRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tempPw, setTempPw] = useState<string | null>(null);
  // form tạo tài khoản (khi hồ sơ chưa có)
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState(() => genPassword());
  const [roleId, setRoleId] = useState<number | "">("");

  const uid = emp.user_id;
  const reload = useCallback(() => {
    if (uid == null) { setRow(null); return; }
    api.rbac.users(token).then((rows) => setRow(rows.find((u) => u.id === uid) ?? null)).catch(() => {});
    api.rbac.userSessions(token, uid).then(setSessions).catch(() => setSessions([]));
    api.rbac.userActivity(token, uid).then(setActivity).catch(() => setActivity([]));
  }, [token, uid]);
  useEffect(() => { reload(); }, [reload]);

  const roleOpts = (meta?.roles ?? []).filter((r) => r.department_id === emp.department_id);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await fn(); reload(); onChanged(); }
    catch (e) { setError(errMsg(e)); }
    finally { setBusy(false); }
  }

  // --- Chưa có tài khoản → cấp tài khoản ---
  if (uid == null) {
    return (
      <div>
        {error && <div className="banner banner--error">{error}</div>}
        <InfoCard title="Chưa có tài khoản đăng nhập" icon={Key}>
          <p className="ns-info-field__label" style={{ gridColumn: "1 / -1" }}>
            Nhân viên chưa đăng nhập được vào hệ thống. Công nhân xưởng có thể không cần tài khoản.
          </p>
        </InfoCard>
        {canCreate && (
          <div className="ns-grid">
            <Field label="Tên đăng nhập *">
              <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="vd nguyenvana" />
            </Field>
            <Field label="Mật khẩu ban đầu *">
              <input value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <Field label="Vai trò">
              <select value={roleId} onChange={(e) => setRoleId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">— chưa gán (đăng nhập nhưng chưa thấy gì) —</option>
                {roleOpts.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </Field>
          </div>
        )}
        {canCreate && (
          <div className="ns2-editfoot">
            <button type="button" className="btn btn--ghost" onClick={() => setPassword(genPassword())} disabled={busy}>
              Tạo mật khẩu khác
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy || !username.trim() || password.length < 6}
              onClick={() => run(async () => {
                await api.employees.createAccount(token, emp.id, {
                  username: username.trim(), password, role_id: roleId === "" ? null : roleId,
                });
                setTempPw(password);
              })}
            >
              {busy ? "Đang tạo…" : "Cấp tài khoản"}
            </button>
          </div>
        )}
        {tempPw && (
          <div className="banner banner--ok">
            Đã cấp tài khoản. Mật khẩu ban đầu: <strong>{tempPw}</strong> — bàn giao cho nhân viên rồi đổi khi đăng nhập lần đầu.
          </div>
        )}
      </div>
    );
  }

  // --- Đã có tài khoản ---
  const locked = row !== null && !row.is_active;
  return (
    <div>
      {error && <div className="banner banner--error">{error}</div>}
      {tempPw && (
        <div className="banner banner--ok">
          Mật khẩu tạm: <strong>{tempPw}</strong> — mọi phiên đã bị thu hồi, bàn giao cho nhân viên.
        </div>
      )}
      <div className="ns-info-sections">
        <InfoCard title="Tài khoản" icon={Key}>
          <InfoField label="Tên đăng nhập" value={row?.username ?? emp.account_username} icon={Key} />
          <InfoField label="Mã tài khoản" value={row?.code ?? null} icon={FileText} />
          <InfoField label="Trạng thái" value={locked ? "Đã khóa" : "Hoạt động"} icon={Lock} />
        </InfoCard>
        <InfoCard title="Vai trò" icon={Users}>
          {canAssignRole ? (
            <div className="ns-info-field" style={{ gridColumn: "1 / -1" }}>
              <div className="ns-info-field__content">
                <span className="ns-info-field__label">Vai trò (theo phòng của hồ sơ)</span>
                <select
                  value={row?.role_id ?? ""}
                  disabled={busy}
                  onChange={(e) => {
                    const v = e.target.value ? Number(e.target.value) : null;
                    run(() => api.rbac.assignUserRole(token, uid, v));
                  }}
                >
                  <option value="">— chưa gán —</option>
                  {roleOpts.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                </select>
              </div>
            </div>
          ) : (
            <InfoField label="Vai trò" value={row?.role_name} icon={Users} />
          )}
        </InfoCard>
      </div>

      <InfoCard title="Bảo mật" icon={Lock}>
        <div className="ns-detail__shortcuts" style={{ gridColumn: "1 / -1" }}>
          {canReset && (
            <button type="button" className="btn btn--ghost btn--sm" disabled={busy}
              onClick={() => run(async () => {
                const r = await api.rbac.resetUserPassword(token, uid);
                setTempPw(r.temporary_password);
              })}>
              <Key size={12} /> Đặt lại mật khẩu
            </button>
          )}
          {canRevoke && (
            <button type="button" className="btn btn--ghost btn--sm" disabled={busy}
              onClick={() => run(() => api.rbac.revokeUserSessions(token, uid))}>
              <Lock size={12} /> Thu hồi mọi phiên
            </button>
          )}
          {canLock && (
            <button type="button" className={`btn btn--sm ${locked ? "btn--primary" : "btn--ghost"}`} disabled={busy}
              onClick={() => run(() => api.rbac.setUserActive(token, uid, locked))}>
              <Lock size={12} /> {locked ? "Mở khóa tài khoản" : "Khóa tài khoản"}
            </button>
          )}
        </div>
        <p className="ns-info-field__label" style={{ gridColumn: "1 / -1" }}>
          Nhân viên <strong>đã nghỉ việc</strong> tự động không đăng nhập được (theo trạng thái hồ sơ) —
          không cần khóa tay. Khóa dùng khi muốn chặn một người <strong>đang làm việc</strong>.
        </p>
      </InfoCard>

      <InfoCard title={`Phiên đang hoạt động (${sessions.length})`} icon={Activity}>
        {sessions.length === 0 ? (
          <InfoField label="Phiên" value={null} icon={Activity} />
        ) : (
          sessions.map((s) => (
            <InfoField key={s.id} label={deviceLabel(s.user_agent)} value={`Đăng nhập ${fmtDate(s.created_at)}`} icon={Activity} />
          ))
        )}
      </InfoCard>

      <InfoCard title="Hoạt động tài khoản gần đây" icon={Activity}>
        {activity.length === 0 ? (
          <InfoField label="Hoạt động" value={null} icon={Activity} />
        ) : (
          activity.slice(0, 8).map((a) => (
            <InfoField key={a.id} label={`${a.action} · ${fmtDate(a.created_at)}`} value={a.actor_name ?? a.detail} icon={Activity} />
          ))
        )}
      </InfoCard>
    </div>
  );
}

function InfoCard({ title, icon: Icon, children }: { title: string; icon: any; children: ReactNode }) {
  return (
    <div className="ns-info-card">
      <h4 className="ns-info-card__title">
        {Icon && <Icon size={14} />} {title}
      </h4>
      <div className="ns-info-grid">{children}</div>
    </div>
  );
}

function InfoField({ label, value, icon: Icon }: { label: string; value: string | null | undefined; icon?: any }) {
  return (
    <div className="ns-info-field">
      {Icon && <Icon className="ns-info-field__icon" size={14} />}
      <div className="ns-info-field__content">
        <span className="ns-info-field__label">{label}</span>
        {value ? (
          <span className="ns-info-field__value">{value}</span>
        ) : (
          <span className="ns-info-field__value ns-info-field__value--empty">—</span>
        )}
      </div>
    </div>
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
    const detailBits = [
      fmtDate(ev.effective_date),
      ev.note || null,
      ev.actor_name ? `Người thực hiện: ${ev.actor_name}` : null,
    ].filter(Boolean);
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
              <Paperclip size={14} />
              <span>{DOC_KIND_LABEL[a.doc_kind] ?? a.doc_kind} · {a.file_name}</span>
            </a>
            <span className="ns-file__date">{fmtDate(a.uploaded_at)}</span>
            {canUpdate && (
              <button type="button" className="btn btn--ghost ns-danger" style={{ padding: "4px 8px", display: "inline-flex", alignItems: "center" }} onClick={async () => { await api.employees.deleteAttachment(token, employeeId, a.id); load(); }}>
                <Trash2 size={13} />
              </button>
            )}
          </li>
        ))}
        {items?.length === 0 && <li className="ns__empty" style={{ gridColumn: "span 2" }}>Chưa có tệp nào.</li>}
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
  const [newJobGrade, setNewJobGrade] = useState("");
  const [newPos, setNewPos] = useState("");
  const [resignReason, setResignReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isTransition = true;

  async function submit() {
    if (kind === "promote" && !newJobGrade.trim() && !newPos.trim()) {
      setError("Nhập bậc thợ mới hoặc chức danh mới.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const input: EmployeeTransitionInput = { kind, effective_date: effective, note: note || undefined };
      if (kind === "transfer") {
        input.new_department_id = newDept === "" ? undefined : newDept;
      }
      if (kind === "promote") {
        input.new_job_grade = newJobGrade.trim() || undefined;
        input.new_position = newPos || undefined;
      }
      if (kind === "resign") input.resign_reason = resignReason;
      await api.employees.transition(token, emp.id, input);
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

          {isTransition && (
            <Field label="Ngày hiệu lực"><input type="date" value={effective} onChange={(e) => setEffective(e.target.value)} /></Field>
          )}
          {kind === "transfer" && (
            <Field label="Phòng/Tổ mới *">
              <select value={newDept} onChange={(e) => setNewDept(e.target.value === "" ? "" : Number(e.target.value))}>
                <option value="">— chọn —</option>
                {meta?.departments.filter((d) => d.id !== emp.department_id).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </Field>
          )}
          {kind === "promote" && (
            <>
              <Field label="Bậc thợ mới (tùy chọn)"><input value={newJobGrade} onChange={(e) => setNewJobGrade(e.target.value)} placeholder="Vd: Thợ bậc 3" /></Field>
              <Field label="Chức danh mới (tùy chọn)"><input value={newPos} onChange={(e) => setNewPos(e.target.value)} /></Field>
              <div className="ns-wizard__hint">Nâng bậc / đổi chức danh không tự đổi tiền lương — mức lương giữ nguyên, chỉnh riêng ở màn Lương nếu cần.</div>
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
