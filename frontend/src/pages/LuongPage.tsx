// Lương (module `luong`, Phase 1 — lương thời gian). 5 tab:
//   • Bảng lương tháng — Tạo → soát ô vàng → Chốt → xuất Excel + file chuyển khoản.
//   • Lương nhân viên — khai báo (nhóm/bậc + mức) & điều chỉnh (lịch sử).
//   • Tạm ứng — ghi nhiều lần → duyệt → tự trừ.
//   • Quy tắc lương — tham số + bảng mức chuẩn.
//   • Phiếu lương của tôi — self-service.
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type EmployeeRow,
  type EmployeeSalary,
  type PayrollLine,
  type PayrollParams,
  type PayrollPeriod,
  type PieceRate,
  type PieceSheet,
  type SalaryAdvance,
  type SalaryPreview,
  type SalaryRule,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import "./nhan-su.css";
import "./luong.css";

type Tab = "bang" | "nhanvien" | "khoan" | "tamung" | "quytac" | "phieu";

// Tổ khoán (đơn giá theo tổ) + đơn vị tính.
const KHOAN_GROUPS: { key: string; label: string }[] = [
  { key: "to_boi", label: "Tổ Bồi" },
  { key: "to_can_phu", label: "Tổ Cán/Phủ" },
  { key: "to_cat", label: "Tổ Cắt" },
  { key: "may_in_5mau", label: "Máy in 5 màu" },
  { key: "may_in_2mau", label: "Máy in 2 màu" },
  { key: "to_thanh_pham", label: "Tổ Thành phẩm" },
];
const KHOAN_GROUP_LABEL: Record<string, string> = Object.fromEntries(KHOAN_GROUPS.map((g) => [g.key, g.label]));
const UNIT_LABEL: Record<string, string> = {
  m2: "m²", bai_in: "bài in", tan: "tấn", cuon: "cuốn", luot: "lượt", hop: "hộp", to: "tờ", khac: "khác",
};

const GROUP_LABEL: Record<string, string> = {
  to_in: "Tổ In", san_xuat: "Sản xuất", van_phong: "Văn phòng",
  to_dan: "Tổ Dán", to_boi: "Tổ Bồi", quan_ly: "Quản lý",
};
const GRADE_LABEL: Record<string, string> = {
  tho_1: "Thợ bậc 1", tho_2: "Thợ bậc 2", tho_3: "Thợ bậc 3", phu_1: "Phụ 1", phu_2: "Phụ 2",
};
const BAND_LABEL: Record<string, string> = {
  lt1: "< 1 năm", y1_5: "1–5 năm", y5_10: "5–10 năm", gt10: "> 10 năm",
};

function money(n: number | null | undefined): string {
  if (n == null) return "0";
  return Math.round(n).toLocaleString("vi-VN");
}
function curYm(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function errText(e: unknown): string {
  return e instanceof Error ? e.message : "Có lỗi xảy ra.";
}

export function LuongPage({ focusEmployeeId }: { focusEmployeeId?: number }) {
  const { token } = useAuth();
  const can = useCan();
  const canManage = can("luong", "update");
  const [tab, setTab] = useState<Tab>(canManage ? "bang" : "phieu");

  // Liên thông từ Hồ sơ nhân sự → mở tab "Lương nhân viên" tại đúng NV.
  useEffect(() => {
    if (focusEmployeeId && canManage) setTab("nhanvien");
  }, [focusEmployeeId, canManage]);

  return (
    <main className="ns">
      <header className="ns__head">
        <div>
          <h1 className="ns__title">Lương</h1>
          <p className="ns__sub">Bảng lương thời gian hàng tháng · tự kéo công từ Chấm công</p>
        </div>
      </header>

      <nav className="ns-tabs cc-tabs">
        {canManage && <button className={tab === "bang" ? "is-active" : ""} onClick={() => setTab("bang")}>Bảng lương tháng</button>}
        {canManage && <button className={tab === "nhanvien" ? "is-active" : ""} onClick={() => setTab("nhanvien")}>Lương nhân viên</button>}
        {canManage && <button className={tab === "khoan" ? "is-active" : ""} onClick={() => setTab("khoan")}>Lương khoán</button>}
        {canManage && <button className={tab === "tamung" ? "is-active" : ""} onClick={() => setTab("tamung")}>Tạm ứng</button>}
        {canManage && <button className={tab === "quytac" ? "is-active" : ""} onClick={() => setTab("quytac")}>Quy tắc lương</button>}
        <button className={tab === "phieu" ? "is-active" : ""} onClick={() => setTab("phieu")}>Phiếu lương của tôi</button>
      </nav>

      {tab === "bang" && canManage && <BangLuongTab token={token!} />}
      {tab === "nhanvien" && canManage && <NhanVienTab token={token!} focusEmployeeId={focusEmployeeId} />}
      {tab === "khoan" && canManage && <KhoanTab token={token!} />}
      {tab === "tamung" && canManage && <TamUngTab token={token!} />}
      {tab === "quytac" && canManage && <QuyTacTab token={token!} />}
      {tab === "phieu" && <PhieuLuongTab token={token!} />}
    </main>
  );
}

// --- Tab: Bảng lương tháng --------------------------------------------------

function BangLuongTab({ token }: { token: string }) {
  const [ym, setYm] = useState(curYm);
  const [period, setPeriod] = useState<PayrollPeriod | null>(null);
  const [lines, setLines] = useState<PayrollLine[]>([]);
  const [filter, setFilter] = useState<"all" | "ct" | "tv">("all");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<PayrollLine | null>(null);
  const [year, month] = ym.split("-").map(Number);

  const load = useCallback(() => {
    api.luong.table(token, year, month)
      .then((t) => { setPeriod(t.period); setLines(t.lines); })
      .catch(() => { setPeriod(null); setLines([]); });
  }, [token, year, month]);
  useEffect(() => { load(); }, [load]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true); setErr(null);
    try { await fn(); load(); } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  }

  const shown = lines.filter((l) => filter === "all" || (filter === "tv" ? l.is_probation : !l.is_probation));
  const totalNet = shown.reduce((s, l) => s + l.net_pay, 0);
  const locked = period?.status === "locked";

  function exportCsv(kind: "full" | "bank") {
    const rows: string[][] = [];
    if (kind === "full") {
      rows.push(["Mã", "Họ tên", "Tổ", "Loại", "Công", "Lương công", "Chuyên cần", "Phụ cấp",
        "Khoán", "Vi phạm", "Thưởng", "Tổng", "BHXH", "TNCN", "Tạm ứng", "Thực lĩnh"]);
      for (const l of shown) rows.push([
        l.employee_code ?? "", l.employee_name ?? "", GROUP_LABEL[l.payroll_group ?? ""] ?? (l.payroll_group ?? ""),
        l.is_probation ? "Thử việc" : "Chính thức", String(l.actual_cong),
        String(Math.round(l.luong_cong)), String(Math.round(l.chuyen_can)), String(Math.round(l.allowance)),
        String(Math.round(l.khoan)), String(Math.round(l.vi_pham)), String(Math.round(l.other_bonus)),
        String(Math.round(l.gross)), String(Math.round(l.bhxh)), String(Math.round(l.pit)),
        String(Math.round(l.advance_total)), String(Math.round(l.net_pay)),
      ]);
    } else {
      rows.push(["Mã", "Họ tên", "Số tài khoản", "Ngân hàng", "Thực lĩnh"]);
      for (const l of shown) rows.push([
        l.employee_code ?? "", l.employee_name ?? "", l.bank_account ?? "", l.bank_name ?? "",
        String(Math.round(l.net_pay)),
      ]);
    }
    const csv = "﻿" + rows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${kind === "bank" ? "chuyen-khoan" : "bang-luong"}-${ym}.csv`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  }

  return (
    <div>
      <div className="cc-toolbar cc-ts-toolbar lg-toolbar">
        <input type="month" value={ym} onChange={(e) => setYm(e.target.value)} />
        <div className="lg-seg">
          {(["all", "ct", "tv"] as const).map((f) => (
            <button key={f} className={filter === f ? "is-active" : ""} onClick={() => setFilter(f)}>
              {f === "all" ? "Tất cả" : f === "ct" ? "Chính thức" : "Thử việc"}
            </button>
          ))}
        </div>
        {!locked
          ? <button className="btn btn--primary" onClick={() => run(() => api.luong.generate(token, year, month))} disabled={busy}>
              {busy ? "Đang tính…" : period ? "↻ Tính lại" : "Tạo bảng lương"}
            </button>
          : <button className="btn btn--ghost" onClick={() => run(() => api.luong.reopen(token, year, month))} disabled={busy}>Mở lại</button>}
        {period && !locked && (
          <button className="btn btn--ghost" onClick={() => run(() => api.luong.lock(token, year, month))} disabled={busy}>🔒 Chốt</button>
        )}
        {period && <button className="btn btn--ghost" onClick={() => exportCsv("full")}>⬇ Xuất Excel</button>}
        {period && <button className="btn btn--ghost" onClick={() => exportCsv("bank")}>⬇ File chuyển khoản</button>}
        {locked && <span className="ns-badge ns-badge--muted">Đã chốt</span>}
      </div>

      {err && <div className="banner banner--error" style={{ marginBottom: 12 }}>{err}</div>}

      {!period ? (
        <p className="ns__empty">Chưa có bảng lương tháng này. Bấm <b>“Tạo bảng lương”</b> để máy tính từ Chấm công + quy tắc + tạm ứng.</p>
      ) : (
        <div className="ns__tablewrap lg-table">
          <table className="ns__table">
            <thead>
              <tr>
                <th>Mã</th><th>Họ tên</th><th>Tổ</th><th className="lg-num">Công</th>
                <th className="lg-num">Lương công</th><th className="lg-num">Chuyên cần</th>
                <th className="lg-num">Phụ cấp</th><th className="lg-num">Khoán</th><th className="lg-num">Vi phạm</th>
                <th className="lg-num">Thưởng</th><th className="lg-num">BHXH</th>
                <th className="lg-num">Tạm ứng</th><th className="lg-num lg-net">Thực lĩnh</th><th></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((l) => (
                <tr key={l.id}>
                  <td className="ns__code">{l.employee_code}</td>
                  <td>{l.employee_name} {l.is_probation && <span className="ns-badge ns-badge--muted">TV</span>}</td>
                  <td>{GROUP_LABEL[l.payroll_group ?? ""] ?? (l.payroll_group ?? "—")}</td>
                  <td className="lg-num">{l.actual_cong}</td>
                  <td className="lg-num">{money(l.luong_cong)}</td>
                  <td className="lg-num">{money(l.chuyen_can)}</td>
                  <td className="lg-num">{money(l.allowance)}</td>
                  <td className="lg-num">{l.khoan ? money(l.khoan) : "—"}</td>
                  <td className={`lg-num ${l.vi_pham ? "lg-minus" : ""}`}>{l.vi_pham ? "−" + money(l.vi_pham) : "—"}</td>
                  <td className="lg-num">{l.other_bonus ? money(l.other_bonus) : "—"}</td>
                  <td className="lg-num lg-minus">{l.bhxh ? "−" + money(l.bhxh) : "—"}</td>
                  <td className={`lg-num ${l.advance_total ? "lg-minus" : ""}`}>{l.advance_total ? "−" + money(l.advance_total) : "—"}</td>
                  <td className="lg-num lg-net">{money(l.net_pay)}</td>
                  <td>{!locked && <button className="btn btn--ghost" onClick={() => setEditing(l)}>Sửa</button>}</td>
                </tr>
              ))}
              {shown.length === 0 && <tr><td colSpan={14} className="ns__empty">Không có nhân viên phù hợp bộ lọc.</td></tr>}
            </tbody>
            <tfoot>
              <tr className="lg-foot">
                <td colSpan={12}>Tổng thực lĩnh ({shown.length} người)</td>
                <td className="lg-num lg-net">{money(totalNet)}</td><td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {editing && (
        <LineEditModal token={token} line={editing} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }} />
      )}
    </div>
  );
}

function LineEditModal({ token, line, onClose, onSaved }: {
  token: string; line: PayrollLine; onClose: () => void; onSaved: () => void;
}) {
  const [viPham, setViPham] = useState(line.vi_pham);
  const [bonus, setBonus] = useState(line.other_bonus);
  const [pit, setPit] = useState(line.pit);
  const [note, setNote] = useState(line.note ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true); setErr(null);
    try {
      await api.luong.updateLine(token, line.id, {
        vi_pham: viPham, other_bonus: bonus, pit, note: note || null,
      });
      onSaved();
    } catch (e) { setErr(errText(e)); setBusy(false); }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>Sửa lương — {line.employee_name}</h2>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <p className="cc-note">Lương công {money(line.luong_cong)} · chuyên cần {money(line.chuyen_can)} · phụ cấp {money(line.allowance)} (tự tính, không sửa ở đây).</p>
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field"><span className="ns-field__label">Vi phạm (trừ)</span>
              <input type="number" min={0} value={viPham} onChange={(e) => setViPham(Number(e.target.value))} /></label>
            <label className="ns-field"><span className="ns-field__label">Thưởng / hoa hồng</span>
              <input type="number" min={0} value={bonus} onChange={(e) => setBonus(Number(e.target.value))} /></label>
            <label className="ns-field"><span className="ns-field__label">Thuế TNCN (trừ)</span>
              <input type="number" min={0} value={pit} onChange={(e) => setPit(Number(e.target.value))} /></label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}><span className="ns-field__label">Ghi chú</span>
            <input value={note} onChange={(e) => setNote(e.target.value)} /></label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>{busy ? "Đang lưu…" : "Lưu"}</button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Lương nhân viên ---------------------------------------------------

function NhanVienTab({ token, focusEmployeeId }: { token: string; focusEmployeeId?: number }) {
  const [emps, setEmps] = useState<EmployeeRow[]>([]);
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<EmployeeRow | null>(null);

  const load = useCallback(() => {
    api.employees.list(token, { size: 200, sort: "code" })
      .then((r) => setEmps(r.items)).catch(() => setEmps([]));
  }, [token]);
  useEffect(() => { load(); }, [load]);

  // Liên thông: khi mở từ Hồ sơ NV, tự bật modal lương của NV đó khi danh sách sẵn sàng.
  useEffect(() => {
    if (focusEmployeeId && emps.length) {
      const e = emps.find((x) => x.id === focusEmployeeId);
      if (e) setPicked(e);
    }
  }, [focusEmployeeId, emps]);

  const shown = emps.filter((e) => !q || e.full_name.toLowerCase().includes(q.toLowerCase()) || e.code.includes(q));

  return (
    <div>
      <div className="cc-toolbar">
        <input className="lg-search" placeholder="Tìm theo tên / mã…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="ns__tablewrap">
        <table className="ns__table">
          <thead>
            <tr><th>Mã</th><th>Họ tên</th><th>Vị trí</th><th>Trạng thái</th><th></th></tr>
          </thead>
          <tbody>
            {shown.map((e) => (
              <tr key={e.id}>
                <td className="ns__code">{e.code}</td>
                <td>{e.full_name}</td>
                <td>{e.position ?? "—"}</td>
                <td>{e.status === "probation" ? <span className="ns-badge ns-badge--muted">Thử việc</span> : e.status === "active" ? <span className="ns-badge ns-badge--ok">Chính thức</span> : e.status}</td>
                <td><button className="btn btn--ghost" onClick={() => setPicked(e)}>Lương</button></td>
              </tr>
            ))}
            {shown.length === 0 && <tr><td colSpan={5} className="ns__empty">Không có nhân viên.</td></tr>}
          </tbody>
        </table>
      </div>
      {picked && <SalaryModal token={token} emp={picked} onClose={() => { setPicked(null); load(); }} />}
    </div>
  );
}

function SalaryModal({ token, emp, onClose }: { token: string; emp: EmployeeRow; onClose: () => void }) {
  const [group, setGroup] = useState("");
  const [grade, setGrade] = useState("");
  const [preview, setPreview] = useState<SalaryPreview | null>(null);
  const [history, setHistory] = useState<EmployeeSalary[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  // form khai/điều chỉnh lương
  const [effFrom, setEffFrom] = useState(() => `${new Date().getFullYear()}-01-01`);
  const [mode, setMode] = useState<"rule" | "manual">("rule");
  const [baseAmount, setBaseAmount] = useState(0);
  const [insBase, setInsBase] = useState(0);
  const [allowance, setAllowance] = useState(0);

  const reload = useCallback(async () => {
    const [detail, prev, hist] = await Promise.all([
      api.employees.get(token, emp.id),
      api.luong.salaryPreview(token, emp.id).catch(() => null),
      api.luong.salaries(token, emp.id).catch(() => ({ items: [] as EmployeeSalary[], employee_id: emp.id, employee_name: null })),
    ]);
    setGroup(detail.payroll_group ?? "");
    setGrade(detail.pay_grade_key ?? "");
    setPreview(prev);
    setHistory(hist.items);
  }, [token, emp.id]);
  useEffect(() => { reload(); }, [reload]);

  async function saveGroup() {
    setBusy(true); setErr(null); setOk(null);
    try {
      const d = await api.employees.get(token, emp.id);
      // gửi full input (giữ nguyên dữ liệu), chỉ đổi nhóm/bậc.
      await api.employees.update(token, emp.id, {
        full_name: d.full_name, department_id: d.department_id, position: d.position,
        job_grade: d.job_grade, status: d.status, hire_date: d.hire_date,
        probation_end_date: d.probation_end_date, date_of_birth: d.date_of_birth, gender: d.gender,
        national_id: d.national_id, national_id_date: d.national_id_date, national_id_place: d.national_id_place,
        phone: d.phone, email: d.email, permanent_address: d.permanent_address, current_address: d.current_address,
        emergency_contact_name: d.emergency_contact_name, emergency_contact_phone: d.emergency_contact_phone,
        social_insurance_no: d.social_insurance_no, pit_tax_code: d.pit_tax_code, dependents_count: d.dependents_count,
        bank_account: d.bank_account, bank_name: d.bank_name, default_shift_id: d.default_shift_id,
        payroll_group: group || null, pay_grade_key: grade || null, note: d.note,
      });
      setOk("Đã lưu nhóm/bậc lương.");
      reload();
    } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  }

  async function saveSalary() {
    setBusy(true); setErr(null); setOk(null);
    try {
      await api.luong.setSalary(token, emp.id, {
        effective_from: effFrom, amount_mode: mode,
        base_amount: mode === "manual" ? baseAmount : null,
        insurance_base: insBase || null, allowance,
      });
      setOk("Đã lưu lương (hiệu lực " + effFrom + ").");
      reload();
    } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head">
          <h2>Lương — {emp.full_name} <span className="ns__code">{emp.code}</span></h2>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          {ok && <div className="banner banner--ok">{ok}</div>}

          {preview && (
            <div className="lg-preview">
              Mức lương hiện tại: <b>{money(preview.monthly)}đ</b>{" "}
              <span className="ns-badge ns-badge--muted">{preview.source === "manual" ? "nhập tay" : preview.source === "rule" ? "theo quy tắc" : "chưa có"}</span>
              {" · "}phụ cấp {money(preview.allowance)} · đóng BH trên {money(preview.insurance_base)}
            </div>
          )}

          <h4 className="ns-section__title">Nhóm & bậc lương</h4>
          <div className="ns-grid">
            <label className="ns-field"><span className="ns-field__label">Nhóm lương</span>
              <select value={group} onChange={(e) => setGroup(e.target.value)}>
                <option value="">— chọn —</option>
                {Object.entries(GROUP_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></label>
            <label className="ns-field"><span className="ns-field__label">Bậc (tổ In)</span>
              <select value={grade} onChange={(e) => setGrade(e.target.value)}>
                <option value="">— không theo bậc —</option>
                {Object.entries(GRADE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></label>
            <div className="ns-field" style={{ justifyContent: "end" }}>
              <button className="btn btn--ghost" onClick={saveGroup} disabled={busy}>Lưu nhóm/bậc</button>
            </div>
          </div>

          <h4 className="ns-section__title" style={{ marginTop: 16 }}>Khai / Điều chỉnh lương</h4>
          <div className="ns-grid">
            <label className="ns-field"><span className="ns-field__label">Hiệu lực từ</span>
              <input type="date" value={effFrom} onChange={(e) => setEffFrom(e.target.value)} /></label>
            <label className="ns-field"><span className="ns-field__label">Cách tính</span>
              <select value={mode} onChange={(e) => setMode(e.target.value as "rule" | "manual")}>
                <option value="rule">Theo quy tắc (nhóm/bậc)</option>
                <option value="manual">Nhập tay mức riêng</option>
              </select></label>
            {mode === "manual" && (
              <label className="ns-field"><span className="ns-field__label">Mức lương tháng</span>
                <input type="number" min={0} value={baseAmount} onChange={(e) => setBaseAmount(Number(e.target.value))} /></label>
            )}
            <label className="ns-field"><span className="ns-field__label">Phụ cấp cố định</span>
              <input type="number" min={0} value={allowance} onChange={(e) => setAllowance(Number(e.target.value))} /></label>
            <label className="ns-field"><span className="ns-field__label">Mức đóng BH (0 = theo lương)</span>
              <input type="number" min={0} value={insBase} onChange={(e) => setInsBase(Number(e.target.value))} /></label>
            <div className="ns-field" style={{ justifyContent: "end" }}>
              <button className="btn btn--primary" onClick={saveSalary} disabled={busy}>Lưu điều chỉnh</button>
            </div>
          </div>

          <h4 className="ns-section__title" style={{ marginTop: 16 }}>Lịch sử điều chỉnh</h4>
          <div className="ns__tablewrap">
            <table className="ns__table">
              <thead><tr><th>Hiệu lực từ</th><th>Cách tính</th><th className="lg-num">Mức tay</th><th className="lg-num">Phụ cấp</th><th>Ghi chú</th></tr></thead>
              <tbody>
                {history.map((s) => (
                  <tr key={s.id}>
                    <td>{s.effective_from}</td>
                    <td>{s.amount_mode === "manual" ? "Nhập tay" : "Theo quy tắc"}</td>
                    <td className="lg-num">{s.base_amount != null ? money(s.base_amount) : "—"}</td>
                    <td className="lg-num">{money(s.allowance)}</td>
                    <td>{s.note ?? "—"}</td>
                  </tr>
                ))}
                {history.length === 0 && <tr><td colSpan={5} className="ns__empty">Chưa khai lương.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>Đóng</button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Lương khoán -------------------------------------------------------

function KhoanTab({ token }: { token: string }) {
  const [sub, setSub] = useState<"sheet" | "rates">("sheet");
  return (
    <div>
      <div className="lg-subtabs">
        <button className={sub === "sheet" ? "is-active" : ""} onClick={() => setSub("sheet")}>Sổ khoán tháng</button>
        <button className={sub === "rates" ? "is-active" : ""} onClick={() => setSub("rates")}>Đơn giá khoán</button>
      </div>
      {sub === "sheet" ? <KhoanSheet token={token} /> : <KhoanRates token={token} />}
    </div>
  );
}

function KhoanSheet({ token }: { token: string }) {
  const [ym, setYm] = useState(curYm);
  const [group, setGroup] = useState(KHOAN_GROUPS[0].key);
  const [sheet, setSheet] = useState<PieceSheet | null>(null);
  const [emps, setEmps] = useState<EmployeeRow[]>([]);
  const [rates, setRates] = useState<PieceRate[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [year, month] = ym.split("-").map(Number);

  const load = useCallback(() => {
    api.luong.khoanSheet(token, year, month, group).then(setSheet).catch(() => setSheet(null));
  }, [token, year, month, group]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.employees.list(token, { size: 200, sort: "code" }).then((r) => setEmps(r.items)).catch(() => setEmps([]));
    api.luong.khoanRates(token).then((r) => setRates(r.items)).catch(() => setRates([]));
  }, [token]);

  async function run(fn: () => Promise<PieceSheet>) {
    setErr(null);
    try { setSheet(await fn()); } catch (e) { setErr(errText(e)); }
  }
  const batch = sheet?.batch ?? null;
  const groupRates = rates.filter((r) => r.group_name === group && r.is_active);
  const empName = (id: number) => emps.find((e) => e.id === id)?.full_name ?? `NV#${id}`;

  return (
    <div>
      <div className="cc-toolbar cc-ts-toolbar">
        <input type="month" value={ym} onChange={(e) => setYm(e.target.value)} />
        <select value={group} onChange={(e) => setGroup(e.target.value)}>
          {KHOAN_GROUPS.map((g) => <option key={g.key} value={g.key}>{g.label}</option>)}
        </select>
        {!batch && <button className="btn btn--primary" onClick={() => run(() => api.luong.openKhoanSheet(token, year, month, group))}>Mở sổ khoán tổ này</button>}
      </div>
      {err && <div className="banner banner--error" style={{ marginBottom: 12 }}>{err}</div>}

      {!batch ? (
        <p className="ns__empty">Chưa mở sổ khoán cho <b>{KHOAN_GROUP_LABEL[group]}</b> tháng này. Bấm <b>“Mở sổ khoán tổ này”</b>.</p>
      ) : (
        <>
          {sheet?.meta && (
            <div className="lg-khoan-meta">
              <span>Quỹ khoán: <b>{money(sheet.meta.revenue)}</b></span>
              <span>Sau bù lỗ/thưởng: <b>{money(sheet.meta.total)}</b></span>
              <span>Tổ trưởng lấy: <b>{money(sheet.meta.leader_cut)}</b></span>
              <span>Còn chia nhóm: <b className="lg-net">{money(sheet.meta.pool)}</b></span>
            </div>
          )}

          <KhoanConfig token={token} batch={batch} emps={emps} onSaved={run} />

          <h4 className="ns-section__title" style={{ marginTop: 16 }}>Sản lượng (nhập tay)</h4>
          <div className="ns__tablewrap">
            <table className="ns__table">
              <thead><tr><th>Công việc</th><th>Đơn vị</th><th className="lg-num">Đơn giá</th><th className="lg-num">Khối lượng</th><th className="lg-num">Thành tiền</th><th></th></tr></thead>
              <tbody>
                {sheet?.entries.map((en) => (
                  <tr key={en.id}>
                    <td>{en.work_name}</td>
                    <td>{UNIT_LABEL[en.unit] ?? en.unit}</td>
                    <td className="lg-num">{money(en.unit_price)}</td>
                    <td className="lg-num">{Number(en.quantity).toLocaleString("vi-VN")}</td>
                    <td className="lg-num lg-net">{money(en.amount)}</td>
                    <td><button className="btn btn--ghost ns-danger" onClick={() => run(() => api.luong.deleteKhoanEntry(token, en.id))}>Xóa</button></td>
                  </tr>
                ))}
                {sheet?.entries.length === 0 && <tr><td colSpan={6} className="ns__empty">Chưa có dòng sản lượng.</td></tr>}
              </tbody>
            </table>
          </div>
          <AddEntryRow token={token} batchId={batch.id} rates={groupRates} onAdded={run} />

          <h4 className="ns-section__title" style={{ marginTop: 16 }}>Chia về người (hệ số nhóm tự thỏa thuận)</h4>
          <div className="ns__tablewrap">
            <table className="ns__table">
              <thead><tr><th>Nhân viên</th><th className="lg-num">Hệ số</th><th className="lg-num">Tiền khoán</th><th></th></tr></thead>
              <tbody>
                {sheet?.shares.map((s) => (
                  <tr key={s.id}>
                    <td>{s.employee_name ?? empName(s.employee_id)} {batch.leader_employee_id === s.employee_id && <span className="ns-badge ns-badge--ok">Tổ trưởng</span>}</td>
                    <td className="lg-num">{s.weight}</td>
                    <td className="lg-num lg-net">{money(s.amount)}</td>
                    <td><button className="btn btn--ghost ns-danger" onClick={() => run(() => api.luong.deleteKhoanShare(token, s.id))}>Xóa</button></td>
                  </tr>
                ))}
                {sheet?.shares.length === 0 && <tr><td colSpan={4} className="ns__empty">Chưa chia cho ai.</td></tr>}
              </tbody>
            </table>
          </div>
          <AddShareRow token={token} batchId={batch.id} emps={emps} onAdded={run} />
        </>
      )}
    </div>
  );
}

function KhoanConfig({ token, batch, emps, onSaved }: {
  token: string; batch: NonNullable<PieceSheet["batch"]>; emps: EmployeeRow[];
  onSaved: (fn: () => Promise<PieceSheet>) => void;
}) {
  const [leader, setLeader] = useState<number | "">(batch.leader_employee_id ?? "");
  const [pct, setPct] = useState(batch.leader_pct);
  const [minG, setMinG] = useState(batch.min_guarantee);
  const [overT, setOverT] = useState(batch.over_target);
  const [overP, setOverP] = useState(batch.over_bonus_pct);
  return (
    <div className="lg-khoan-config">
      <label className="ns-field"><span className="ns-field__label">Tổ trưởng</span>
        <select value={leader} onChange={(e) => setLeader(e.target.value ? Number(e.target.value) : "")}>
          <option value="">— không —</option>
          {emps.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
        </select></label>
      <label className="ns-field"><span className="ns-field__label">% tổ trưởng</span>
        <input type="number" step={0.01} value={pct} onChange={(e) => setPct(Number(e.target.value))} /></label>
      <label className="ns-field"><span className="ns-field__label">Bù lỗ (min)</span>
        <input type="number" value={minG} onChange={(e) => setMinG(Number(e.target.value))} /></label>
      <label className="ns-field"><span className="ns-field__label">Mốc vượt</span>
        <input type="number" value={overT} onChange={(e) => setOverT(Number(e.target.value))} /></label>
      <label className="ns-field"><span className="ns-field__label">% thưởng vượt</span>
        <input type="number" step={0.05} value={overP} onChange={(e) => setOverP(Number(e.target.value))} /></label>
      <button className="btn btn--ghost" onClick={() => onSaved(() => api.luong.updateKhoanConfig(token, batch.id, {
        leader_employee_id: leader === "" ? null : Number(leader), leader_pct: pct,
        min_guarantee: minG, over_target: overT, over_bonus_pct: overP,
      }))}>Lưu cấu hình tổ</button>
    </div>
  );
}

function AddEntryRow({ token, batchId, rates, onAdded }: {
  token: string; batchId: number; rates: PieceRate[]; onAdded: (fn: () => Promise<PieceSheet>) => void;
}) {
  const [rateId, setRateId] = useState<number | "">("");
  const [qty, setQty] = useState(0);
  const rate = rates.find((r) => r.id === Number(rateId));
  return (
    <div className="lg-addrow">
      <select value={rateId} onChange={(e) => setRateId(e.target.value ? Number(e.target.value) : "")}>
        <option value="">— chọn công việc (đơn giá) —</option>
        {rates.map((r) => <option key={r.id} value={r.id}>{r.name} · {money(r.unit_price)}/{UNIT_LABEL[r.unit] ?? r.unit}</option>)}
      </select>
      <input type="number" min={0} placeholder="Khối lượng" value={qty || ""} onChange={(e) => setQty(Number(e.target.value))} />
      {rate && <span className="cc-note">= {money((rate.unit_price) * qty)}</span>}
      <button className="btn btn--primary" disabled={!rateId || qty <= 0}
        onClick={() => { onAdded(() => api.luong.addKhoanEntry(token, batchId, { piece_rate_id: Number(rateId), quantity: qty })); setRateId(""); setQty(0); }}>
        + Thêm sản lượng
      </button>
    </div>
  );
}

function AddShareRow({ token, batchId, emps, onAdded }: {
  token: string; batchId: number; emps: EmployeeRow[]; onAdded: (fn: () => Promise<PieceSheet>) => void;
}) {
  const [empId, setEmpId] = useState<number | "">("");
  const [weight, setWeight] = useState(1);
  return (
    <div className="lg-addrow">
      <select value={empId} onChange={(e) => setEmpId(e.target.value ? Number(e.target.value) : "")}>
        <option value="">— chọn nhân viên —</option>
        {emps.map((e) => <option key={e.id} value={e.id}>{e.code} · {e.full_name}</option>)}
      </select>
      <input type="number" min={0} step={0.5} placeholder="Hệ số" value={weight} onChange={(e) => setWeight(Number(e.target.value))} />
      <button className="btn btn--primary" disabled={!empId}
        onClick={() => { onAdded(() => api.luong.setKhoanShare(token, batchId, { employee_id: Number(empId), weight })); setEmpId(""); setWeight(1); }}>
        + Thêm người
      </button>
    </div>
  );
}

function KhoanRates({ token }: { token: string }) {
  const [rates, setRates] = useState<PieceRate[]>([]);
  const [editing, setEditing] = useState<PieceRate | "new" | null>(null);
  const load = useCallback(() => {
    api.luong.khoanRates(token).then((r) => setRates(r.items)).catch(() => setRates([]));
  }, [token]);
  useEffect(() => { load(); }, [load]);
  async function remove(id: number) { await api.luong.deleteKhoanRate(token, id); load(); }

  return (
    <div>
      <div className="cc-toolbar">
        <h4 className="ns-section__title" style={{ margin: 0, flex: 1 }}>Đơn giá khoán theo tổ</h4>
        <button className="btn btn--primary" onClick={() => setEditing("new")}>+ Thêm đơn giá</button>
      </div>
      <div className="ns__tablewrap">
        <table className="ns__table">
          <thead><tr><th>Tổ</th><th>Mã</th><th>Công việc</th><th>Đơn vị</th><th className="lg-num">Đơn giá</th><th></th></tr></thead>
          <tbody>
            {rates.map((r) => (
              <tr key={r.id}>
                <td>{KHOAN_GROUP_LABEL[r.group_name] ?? r.group_name}</td>
                <td>{r.code ?? "—"}</td>
                <td>{r.name}</td>
                <td>{UNIT_LABEL[r.unit] ?? r.unit}</td>
                <td className="lg-num">{money(r.unit_price)}</td>
                <td className="cc-rowact">
                  <button className="btn btn--ghost" onClick={() => setEditing(r)}>Sửa</button>
                  <button className="btn btn--ghost ns-danger" onClick={() => remove(r.id)}>Xóa</button>
                </td>
              </tr>
            ))}
            {rates.length === 0 && <tr><td colSpan={6} className="ns__empty">Chưa có đơn giá khoán nào.</td></tr>}
          </tbody>
        </table>
      </div>
      {editing && <KhoanRateModal token={token} rate={editing === "new" ? null : editing}
        onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
    </div>
  );
}

function KhoanRateModal({ token, rate, onClose, onSaved }: {
  token: string; rate: PieceRate | null; onClose: () => void; onSaved: () => void;
}) {
  const [group, setGroup] = useState(rate?.group_name ?? KHOAN_GROUPS[0].key);
  const [code, setCode] = useState(rate?.code ?? "");
  const [name, setName] = useState(rate?.name ?? "");
  const [unit, setUnit] = useState(rate?.unit ?? "m2");
  const [price, setPrice] = useState(rate?.unit_price ?? 0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true); setErr(null);
    const input = { group_name: group, code: code || null, name, unit, unit_price: price, is_active: true };
    try {
      if (rate) await api.luong.updateKhoanRate(token, rate.id, input);
      else await api.luong.createKhoanRate(token, input);
      onSaved();
    } catch (e) { setErr(errText(e)); setBusy(false); }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head"><h2>{rate ? "Sửa đơn giá khoán" : "Thêm đơn giá khoán"}</h2>
          <button className="ns-modal__x" onClick={onClose}>×</button></header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <div className="ns-grid">
            <label className="ns-field"><span className="ns-field__label">Tổ *</span>
              <select value={group} onChange={(e) => setGroup(e.target.value)}>
                {KHOAN_GROUPS.map((g) => <option key={g.key} value={g.key}>{g.label}</option>)}
              </select></label>
            <label className="ns-field"><span className="ns-field__label">Mã (A–F, nếu có)</span>
              <input value={code} onChange={(e) => setCode(e.target.value)} /></label>
            <label className="ns-field"><span className="ns-field__label">Đơn vị</span>
              <select value={unit} onChange={(e) => setUnit(e.target.value)}>
                {Object.entries(UNIT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></label>
            <label className="ns-field"><span className="ns-field__label">Đơn giá/đơn vị *</span>
              <input type="number" min={0} value={price} onChange={(e) => setPrice(Number(e.target.value))} /></label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}><span className="ns-field__label">Công việc *</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="vd: Bồi carton 3 lớp E,B" /></label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>{busy ? "Đang lưu…" : "Lưu"}</button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Tạm ứng -----------------------------------------------------------

function TamUngTab({ token }: { token: string }) {
  const [ym, setYm] = useState(curYm);
  const [items, setItems] = useState<SalaryAdvance[]>([]);
  const [emps, setEmps] = useState<EmployeeRow[]>([]);
  const [adding, setAdding] = useState(false);
  const [year, month] = ym.split("-").map(Number);

  const load = useCallback(() => {
    api.luong.advances(token, year, month).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token, year, month]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.employees.list(token, { size: 200, sort: "code" }).then((r) => setEmps(r.items)).catch(() => setEmps([])); }, [token]);

  async function act(fn: () => Promise<unknown>) { try { await fn(); load(); } catch { /* ignore */ } }

  const STATUS: Record<string, [string, string]> = {
    pending: ["Chờ duyệt", "ns-badge--muted"], approved: ["Đã duyệt", "ns-badge--ok"],
    rejected: ["Từ chối", "ns-badge--danger"], cancelled: ["Đã hủy", "ns-badge--muted"],
  };
  const totalApproved = items.filter((a) => a.status === "approved").reduce((s, a) => s + a.amount, 0);

  return (
    <div>
      <div className="cc-toolbar cc-ts-toolbar">
        <input type="month" value={ym} onChange={(e) => setYm(e.target.value)} />
        <button className="btn btn--primary" onClick={() => setAdding(true)}>+ Thêm ứng</button>
        <span className="cc-ts-legend">Đã duyệt: <b>{money(totalApproved)}đ</b></span>
      </div>
      <div className="ns__tablewrap">
        <table className="ns__table">
          <thead><tr><th>Nhân viên</th><th>Ngày ứng</th><th className="lg-num">Số tiền</th><th>Lý do</th><th>Trạng thái</th><th></th></tr></thead>
          <tbody>
            {items.map((a) => {
              const [label, cls] = STATUS[a.status] ?? [a.status, "ns-badge--muted"];
              return (
                <tr key={a.id}>
                  <td>{a.employee_name ?? `NV#${a.employee_id}`}</td>
                  <td>{a.advance_date}</td>
                  <td className="lg-num">{money(a.amount)}</td>
                  <td>{a.reason ?? "—"}</td>
                  <td><span className={`ns-badge ${cls}`}>{label}</span></td>
                  <td className="cc-rowact">
                    {a.status === "pending" && <>
                      <button className="btn btn--ghost" onClick={() => act(() => api.luong.approveAdvance(token, a.id))}>Duyệt</button>
                      <button className="btn btn--ghost ns-danger" onClick={() => act(() => api.luong.rejectAdvance(token, a.id))}>Từ chối</button>
                    </>}
                    {a.status === "approved" && <button className="btn btn--ghost ns-danger" onClick={() => act(() => api.luong.cancelAdvance(token, a.id))}>Hủy</button>}
                  </td>
                </tr>
              );
            })}
            {items.length === 0 && <tr><td colSpan={6} className="ns__empty">Chưa có tạm ứng tháng này.</td></tr>}
          </tbody>
        </table>
      </div>
      {adding && <AddAdvanceModal token={token} emps={emps} year={year} month={month}
        onClose={() => setAdding(false)} onSaved={() => { setAdding(false); load(); }} />}
    </div>
  );
}

function AddAdvanceModal({ token, emps, year, month, onClose, onSaved }: {
  token: string; emps: EmployeeRow[]; year: number; month: number; onClose: () => void; onSaved: () => void;
}) {
  const [empId, setEmpId] = useState<number | "">("");
  const [amount, setAmount] = useState(0);
  const [dateStr, setDateStr] = useState(() => new Date().toISOString().slice(0, 10));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (empId === "" || amount <= 0) { setErr("Chọn nhân viên và nhập số tiền > 0."); return; }
    setBusy(true); setErr(null);
    try {
      await api.luong.createAdvance(token, {
        employee_id: Number(empId), period_year: year, period_month: month,
        advance_date: dateStr, amount, reason: reason || null,
      });
      onSaved();
    } catch (e) { setErr(errText(e)); setBusy(false); }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head"><h2>Thêm tạm ứng — {String(month).padStart(2, "0")}/{year}</h2>
          <button className="ns-modal__x" onClick={onClose}>×</button></header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <label className="ns-field"><span className="ns-field__label">Nhân viên *</span>
            <select value={empId} onChange={(e) => setEmpId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">— chọn —</option>
              {emps.map((e) => <option key={e.id} value={e.id}>{e.code} · {e.full_name}</option>)}
            </select></label>
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field"><span className="ns-field__label">Số tiền *</span>
              <input type="number" min={0} value={amount} onChange={(e) => setAmount(Number(e.target.value))} /></label>
            <label className="ns-field"><span className="ns-field__label">Ngày ứng</span>
              <input type="date" value={dateStr} onChange={(e) => setDateStr(e.target.value)} /></label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}><span className="ns-field__label">Lý do</span>
            <input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>{busy ? "Đang lưu…" : "Lưu"}</button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Quy tắc lương -----------------------------------------------------

function QuyTacTab({ token }: { token: string }) {
  const [params, setParams] = useState<PayrollParams | null>(null);
  const [rules, setRules] = useState<SalaryRule[]>([]);
  const [editing, setEditing] = useState<SalaryRule | "new" | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const load = useCallback(() => {
    api.luong.getParams(token).then(setParams).catch(() => setParams(null));
    api.luong.rules(token).then((r) => setRules(r.items)).catch(() => setRules([]));
  }, [token]);
  useEffect(() => { load(); }, [load]);

  async function saveParams() {
    if (!params) return;
    await api.luong.updateParams(token, params);
    setOk("Đã lưu tham số."); setTimeout(() => setOk(null), 2000);
  }
  async function removeRule(id: number) { await api.luong.deleteRule(token, id); load(); }

  return (
    <div>
      {ok && <div className="banner banner--ok" style={{ marginBottom: 12 }}>{ok}</div>}
      {params && (
        <div className="lg-params">
          <h4 className="ns-section__title">Tham số chung</h4>
          <div className="ns-grid lg-params-grid">
            <NumField label="Công chuẩn/tháng" v={params.standard_cong_default} on={(x) => setParams({ ...params, standard_cong_default: x })} />
            <NumField label="% thử việc" v={params.probation_ratio} step={0.05} on={(x) => setParams({ ...params, probation_ratio: x })} />
            <NumField label="BHXH (NV)" v={params.bhxh_rate} step={0.005} on={(x) => setParams({ ...params, bhxh_rate: x })} />
            <NumField label="BHYT (NV)" v={params.bhyt_rate} step={0.005} on={(x) => setParams({ ...params, bhyt_rate: x })} />
            <NumField label="BHTN (NV)" v={params.bhtn_rate} step={0.005} on={(x) => setParams({ ...params, bhtn_rate: x })} />
            <NumField label="Chuyên cần" v={params.chuyen_can_default} on={(x) => setParams({ ...params, chuyen_can_default: x })} />
            <NumField label="Giảm trừ bản thân" v={params.deduction_self} on={(x) => setParams({ ...params, deduction_self: x })} />
            <NumField label="Giảm trừ/người PT" v={params.deduction_dependent} on={(x) => setParams({ ...params, deduction_dependent: x })} />
          </div>
          <button className="btn btn--primary" style={{ marginTop: 12 }} onClick={saveParams}>Lưu tham số</button>
        </div>
      )}

      <div className="cc-toolbar" style={{ marginTop: 20 }}>
        <h4 className="ns-section__title" style={{ margin: 0, flex: 1 }}>Bảng mức lương chuẩn</h4>
        <button className="btn btn--primary" onClick={() => setEditing("new")}>+ Thêm mức</button>
      </div>
      <div className="ns__tablewrap">
        <table className="ns__table">
          <thead><tr><th>Nhóm</th><th>Bậc</th><th>Thâm niên</th><th>Giới</th><th className="lg-num">Mức/tháng</th><th>Hiệu lực</th><th></th></tr></thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.id}>
                <td>{GROUP_LABEL[r.payroll_group] ?? r.payroll_group}</td>
                <td>{r.pay_grade_key ? (GRADE_LABEL[r.pay_grade_key] ?? r.pay_grade_key) : "—"}</td>
                <td>{r.seniority_band ? (BAND_LABEL[r.seniority_band] ?? r.seniority_band) : "—"}</td>
                <td>{r.gender === "male" ? "Nam" : r.gender === "female" ? "Nữ" : "—"}</td>
                <td className="lg-num">{money(r.monthly_amount)}</td>
                <td>{r.effective_from ?? "—"}</td>
                <td className="cc-rowact">
                  <button className="btn btn--ghost" onClick={() => setEditing(r)}>Sửa</button>
                  <button className="btn btn--ghost ns-danger" onClick={() => removeRule(r.id)}>Xóa</button>
                </td>
              </tr>
            ))}
            {rules.length === 0 && <tr><td colSpan={7} className="ns__empty">Chưa có mức lương nào.</td></tr>}
          </tbody>
        </table>
      </div>
      {editing && <RuleModal token={token} rule={editing === "new" ? null : editing}
        onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
    </div>
  );
}

function NumField({ label, v, on, step }: { label: string; v: number; on: (x: number) => void; step?: number }) {
  return (
    <label className="ns-field"><span className="ns-field__label">{label}</span>
      <input type="number" step={step ?? 1} value={v} onChange={(e) => on(Number(e.target.value))} /></label>
  );
}

function RuleModal({ token, rule, onClose, onSaved }: {
  token: string; rule: SalaryRule | null; onClose: () => void; onSaved: () => void;
}) {
  const [group, setGroup] = useState(rule?.payroll_group ?? "to_in");
  const [grade, setGrade] = useState(rule?.pay_grade_key ?? "");
  const [band, setBand] = useState(rule?.seniority_band ?? "");
  const [gender, setGender] = useState(rule?.gender ?? "");
  const [amount, setAmount] = useState(rule?.monthly_amount ?? 0);
  const [eff, setEff] = useState(rule?.effective_from ?? `${new Date().getFullYear()}-01-01`);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true); setErr(null);
    const input = {
      payroll_group: group, pay_grade_key: grade || null, seniority_band: band || null,
      gender: gender || null, monthly_amount: amount, effective_from: eff, is_active: true,
    };
    try {
      if (rule) await api.luong.updateRule(token, rule.id, input);
      else await api.luong.createRule(token, input);
      onSaved();
    } catch (e) { setErr(errText(e)); setBusy(false); }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head"><h2>{rule ? "Sửa mức lương" : "Thêm mức lương"}</h2>
          <button className="ns-modal__x" onClick={onClose}>×</button></header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <div className="ns-grid">
            <label className="ns-field"><span className="ns-field__label">Nhóm lương *</span>
              <select value={group} onChange={(e) => setGroup(e.target.value)}>
                {Object.entries(GROUP_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></label>
            <label className="ns-field"><span className="ns-field__label">Bậc (nếu theo bậc)</span>
              <select value={grade} onChange={(e) => setGrade(e.target.value)}>
                <option value="">—</option>
                {Object.entries(GRADE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></label>
            <label className="ns-field"><span className="ns-field__label">Thâm niên (nếu theo)</span>
              <select value={band} onChange={(e) => setBand(e.target.value)}>
                <option value="">—</option>
                {Object.entries(BAND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></label>
            <label className="ns-field"><span className="ns-field__label">Giới tính (nếu theo)</span>
              <select value={gender} onChange={(e) => setGender(e.target.value)}>
                <option value="">—</option><option value="male">Nam</option><option value="female">Nữ</option>
              </select></label>
            <label className="ns-field"><span className="ns-field__label">Mức lương/tháng *</span>
              <input type="number" min={0} value={amount} onChange={(e) => setAmount(Number(e.target.value))} /></label>
            <label className="ns-field"><span className="ns-field__label">Hiệu lực từ</span>
              <input type="date" value={eff} onChange={(e) => setEff(e.target.value)} /></label>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>{busy ? "Đang lưu…" : "Lưu"}</button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Phiếu lương của tôi -----------------------------------------------

function PhieuLuongTab({ token }: { token: string }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof api.luong.myPayslip>> | null>(null);
  useEffect(() => { api.luong.myPayslip(token).then(setData).catch(() => setData(null)); }, [token]);

  if (!data) return <p className="ns__empty">Đang tải…</p>;
  if (!data.has_employee) return <div className="banner banner--warn" style={{ marginTop: 12 }}>Tài khoản của bạn chưa gắn hồ sơ nhân viên.</div>;
  const l = data.line;
  if (!l || !data.period) return <p className="ns__empty">Chưa có phiếu lương nào. Chờ HCNS chốt bảng lương.</p>;

  const rows: [string, number, boolean?][] = [
    ["Lương theo công", l.luong_cong], ["Chuyên cần", l.chuyen_can], ["Phụ cấp", l.allowance],
    ["Lương khoán", l.khoan], ["Thưởng / hoa hồng", l.other_bonus], ["Vi phạm", -l.vi_pham, true],
    ["Tổng thu nhập", l.gross], ["BHXH/BHYT/BHTN", -l.bhxh, true], ["Thuế TNCN", -l.pit, true],
    ["Tạm ứng đã nhận", -l.advance_total, true],
  ];
  return (
    <div className="lg-payslip">
      <div className="lg-payslip__card">
        <div className="lg-payslip__head">
          <div>
            <div className="lg-payslip__who">{data.employee_name}</div>
            <div className="cc-card__hint">Phiếu lương tháng {String(data.period.month).padStart(2, "0")}/{data.period.year} · {l.actual_cong}/{l.standard_cong} công {l.is_probation && "· thử việc"}</div>
          </div>
          <span className={`ns-badge ${data.period.status === "locked" ? "ns-badge--ok" : "ns-badge--muted"}`}>{data.period.status === "locked" ? "Đã chốt" : "Tạm tính"}</span>
        </div>
        <table className="lg-payslip__table">
          <tbody>
            {rows.map(([label, val, minus]) => (
              <tr key={label} className={label.startsWith("Tổng") ? "lg-payslip__sub" : ""}>
                <td>{label}</td>
                <td className={`lg-num ${minus ? "lg-minus" : ""}`}>{minus && val !== 0 ? "−" : ""}{money(Math.abs(val))}</td>
              </tr>
            ))}
            <tr className="lg-payslip__net"><td>THỰC LĨNH</td><td className="lg-num">{money(l.net_pay)}đ</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
