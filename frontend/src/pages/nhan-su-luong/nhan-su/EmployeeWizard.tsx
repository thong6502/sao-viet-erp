// Wizard thêm nhân viên (tách từ pages/NhanSuPage.tsx) — GIỮ NGUYÊN KHỐI.
import { useEffect, useState } from "react";
import {
  api,
  type EmployeeInput,
  type EmployeeMeta,
  type PayrollComponent,
} from "../../../api/client";
import { Button } from "../../../components/Button";
import { useCan } from "../../../auth/permissions";
import { fmtDate, money } from "../../../utils/format";
import { Trash2 } from "lucide-react";
import { DOC_KIND_LABEL } from "./shared/constants";
import {
  errMsg,
  formatFileSize,
  getFileTypeInfo,
  isProduction,
  seniorityLabel,
} from "./shared/helpers";
import { useJobGrades } from "./hooks/useJobGrades";
import { Field, FilePicker, JobGradeField } from "./components/form-fields";

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
  const STEPS = [
    "Định danh & việc làm",
    "Cá nhân",
    "Lương & BHXH",
    "Đính kèm",
    "Tài khoản",
  ];
  const can = useCan();
  const canCreateGrade = can("nhan_su", "create");
  const jg = useJobGrades(token);
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
  const [acc, setAcc] = useState({
    username: "",
    password: "",
    role_id: "" as number | "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // ⚠️ Mức đóng BH = lương cơ bản + lương trách nhiệm (chủ chốt 12/08/2026, đảo chốt cũ
  // 20/07 "chỉ lương cơ bản"). Các khoản phụ cấp là số cố định khai riêng từng nhân viên.
  const [luongViTri, setLuongViTri] = useState(0);
  const [luongTrachNhiem, setLuongTrachNhiem] = useState(0);
  // "Lương trả 1 lần" (đợt 1): mức trả trong MỘT lần — số điền sẵn khi lập phiếu đợt 1 ở màn Lương.
  const [luongDot1, setLuongDot1] = useState(0);
  // % hoa hồng NV kinh doanh — nhập theo PHẦN TRĂM ở UI, gửi lên là PHÂN SỐ. Chỉ để KHAI:
  // engine lương không tự cộng khoản này.
  const [commissionPct, setCommissionPct] = useState(0);
  // Khoản thu nhập chọn từ DANH MỤC (Tầng 1 → Tầng 2). Giữ ở state cục bộ tới lúc tạo xong hồ
  // sơ mới gán được — API gán khoản cần `employee_id` mà lúc này chưa có.
  const [comps, setComps] = useState<PayrollComponent[] | null>(null);
  const [picked, setPicked] = useState<
    { id: number; amount: number; note: string }[]
  >([]);
  const [pickOpen, setPickOpen] = useState(false);
  useEffect(() => {
    if (!canSalary) return;
    api.luong.components
      .list(token)
      .then((r) => setComps(r.items))
      .catch(() => setComps([]));
  }, [token, canSalary]);
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
  const gradeName =
    jg.grades?.find((g) => g.id === form.job_grade_id)?.name ?? null;

  async function submit() {
    setError(null);
    if (!form.full_name.trim()) {
      setStep(0);
      setError("Họ tên là bắt buộc.");
      return;
    }
    if (canSalary && luongViTri <= 0) {
      setStep(2);
      setError("Lương cơ bản của nhân viên phải lớn hơn 0.");
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
            effective_from:
              form.hire_date || new Date().toISOString().slice(0, 10),
            luong_vi_tri: luongViTri,
            luong_trach_nhiem: luongTrachNhiem,
            luong_dot_1: luongDot1,
            chuyen_can: chuyenCan,
            insurance_elsewhere: insuranceElsewhere,
            union_member: unionMember,
            // Backend nhận PHÂN SỐ và chặn `le=1` ⇒ kẹp trần 100% ở đây, đừng để người gõ nhầm
            // "150" ăn nguyên cục 422 mà không hiểu vì sao.
            commission_pct: Math.min(commissionPct, 100) / 100,
          };
        }
        const res = await api.employees.create(token, input);
        id = res.employee.id;
        setCreatedId(id);
        // Gán khoản ngay sau khi có id — cùng nếp với upload file bên dưới.
        if (canSalary && picked.length) {
          await api.luong.components.setEmployeeValues(
            token,
            id,
            picked.map((p) => ({
              component_id: p.id,
              amount: p.amount,
              note: p.note.trim() || null,
            })),
          );
        }
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
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>

        <ol className="ns-steps">
          {STEPS.map((s, i) => (
            <li
              key={s}
              className={i === step ? "is-active" : i < step ? "is-done" : ""}
            >
              <span className="ns-steps__n">{i + 1}</span>
              {s}
            </li>
          ))}
        </ol>

        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}

          {STEPS[step] === "Định danh & việc làm" && (
            <div className="ns-grid">
              <Field label="Họ tên *">
                <input
                  value={form.full_name}
                  onChange={(e) => set("full_name", e.target.value)}
                />
              </Field>
              <Field label="Phòng/Tổ *">
                <select
                  value={form.department_id ?? ""}
                  onChange={(e) => {
                    const id =
                      e.target.value === "" ? null : Number(e.target.value);
                    // Đổi sang phòng KHÔNG phải sản xuất thì phải XOÁ bậc ngay: chỉ ẩn ô mà giữ
                    // state là vẫn submit bậc lên backend (backend không chặn) ⇒ kế toán nhận
                    // một nhân viên văn phòng mang bậc thợ.
                    setForm((f) => ({
                      ...f,
                      department_id: id,
                      job_grade_id: isProduction(meta, id)
                        ? f.job_grade_id
                        : null,
                    }));
                  }}
                >
                  {meta.departments.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Chức danh">
                <input
                  value={form.position ?? ""}
                  onChange={(e) => set("position", e.target.value)}
                />
              </Field>
              {isProduction(meta, form.department_id) && (
                <JobGradeField
                  grades={jg.grades}
                  err={jg.err}
                  reload={jg.reload}
                  addGrade={jg.addGrade}
                  value={form.job_grade_id ?? null}
                  onChange={(id) => set("job_grade_id", id)}
                  label="Bậc tay nghề"
                  // hint="Chỉ khai cho khối sản xuất. Khai bậc thôi — bậc KHÔNG làm đổi tiền lương."
                  canCreate={canCreateGrade}
                />
              )}
              <Field label="Thâm niên khi vào làm (năm)">
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={priorSeniorityYears || ""}
                  onChange={(e) =>
                    setPriorSeniorityYears(
                      e.target.value === "" ? 0 : Number(e.target.value),
                    )
                  }
                  placeholder="0"
                />
                {seniorityText && (
                  <span className="ns-field__hint">{seniorityText}</span>
                )}
              </Field>
              <Field label="Ngày vào">
                <input
                  type="date"
                  value={form.hire_date ?? ""}
                  onChange={(e) => set("hire_date", e.target.value)}
                />
              </Field>
              <Field label="Trạng thái">
                <select
                  value={form.status}
                  onChange={(e) => set("status", e.target.value)}
                >
                  <option value="probation">Thử việc</option>
                  <option value="active">Chính thức</option>
                </select>
              </Field>
              {form.status === "probation" && (
                <Field label="Ngày hết thử việc *">
                  <input
                    type="date"
                    required
                    value={form.probation_end_date ?? ""}
                    onChange={(e) => set("probation_end_date", e.target.value)}
                  />
                  {/* Nói LÝ DO chứ không chỉ "bắt buộc": người khai hiểu bỏ trống thì hỏng cái
                      gì mới chịu điền đúng, thay vì gõ bừa một ngày cho qua ô. */}
                  <span className="ns-field__hint">
                    Bắt buộc — tới ngày này hệ thống tự chuyển sang “Hết thử việc · chờ xác
                    nhận” để nhắc bấm chuyển chính thức. Lương vẫn tính mức thử việc cho tới
                    lúc bấm.
                  </span>
                </Field>
              )}
            </div>
          )}

          {STEPS[step] === "Cá nhân" && (
            <div className="ns-grid">
              <Field label="Ngày sinh">
                <input
                  type="date"
                  value={form.date_of_birth ?? ""}
                  onChange={(e) => set("date_of_birth", e.target.value)}
                />
              </Field>
              <Field label="Giới tính">
                <select
                  value={form.gender ?? ""}
                  onChange={(e) => set("gender", e.target.value || null)}
                >
                  <option value="">—</option>
                  <option value="male">Nam</option>
                  <option value="female">Nữ</option>
                  <option value="other">Khác</option>
                </select>
              </Field>
              <Field label="CCCD">
                <input
                  value={form.national_id ?? ""}
                  onChange={(e) => set("national_id", e.target.value)}
                />
              </Field>
              <Field label="SĐT">
                <input
                  value={form.phone ?? ""}
                  onChange={(e) => set("phone", e.target.value)}
                />
              </Field>
              <Field label="Email">
                <input
                  value={form.email ?? ""}
                  onChange={(e) => set("email", e.target.value)}
                />
              </Field>
              <Field label="Hộ khẩu">
                <input
                  value={form.permanent_address ?? ""}
                  onChange={(e) => set("permanent_address", e.target.value)}
                />
              </Field>
              <Field label="Chỗ ở hiện tại">
                <input
                  value={form.current_address ?? ""}
                  onChange={(e) => set("current_address", e.target.value)}
                />
              </Field>
              <Field label="Liên hệ khẩn (tên)">
                <input
                  value={form.emergency_contact_name ?? ""}
                  onChange={(e) =>
                    set("emergency_contact_name", e.target.value)
                  }
                />
              </Field>
              <Field label="Liên hệ khẩn (SĐT)">
                <input
                  value={form.emergency_contact_phone ?? ""}
                  onChange={(e) =>
                    set("emergency_contact_phone", e.target.value)
                  }
                />
              </Field>
              <Field label="Ghi chú">
                <input
                  value={form.note ?? ""}
                  onChange={(e) => set("note", e.target.value)}
                  placeholder="Ghi gì tuỳ ý…"
                />
              </Field>
            </div>
          )}

          {STEPS[step] === "Lương & BHXH" && (
            <div className="ns-grid">
              {canSalary ? (
                <>
                  <div className="ns-wizard__salary-intro ns-wizard__full">
                    <strong>Mức lương riêng của nhân viên</strong>
                    <span>
                      BHXH/BHYT/BHTN đóng trên lương cơ bản. Các khoản phụ cấp
                      là số cố định, cộng phẳng mỗi tháng.
                    </span>
                  </div>
                  <Field label="Lương cơ bản *">
                    <input
                      type="number"
                      min={0}
                      step={100000}
                      value={luongViTri}
                      onChange={(e) => setLuongViTri(Number(e.target.value))}
                    />
                  </Field>
                  <Field label="Lương trách nhiệm">
                    <input
                      type="number"
                      min={0}
                      step={100000}
                      value={luongTrachNhiem}
                      onChange={(e) =>
                        setLuongTrachNhiem(Number(e.target.value))
                      }
                    />
                  </Field>
                  <div className="ns-wizard__salary-total ns-wizard__full">
                    <span>Mức nền theo hợp đồng</span>
                    <strong>{money(salaryBase)}</strong>
                  </div>
                  <Field label="Thưởng chuyên cần">
                    <input
                      type="number"
                      min={0}
                      step={50000}
                      value={chuyenCan}
                      onChange={(e) => setChuyenCan(Number(e.target.value))}
                    />
                  </Field>
                  <Field
                    label="Lương trả 1 lần (đợt 1)"
                    hint="Mức trả trong 1 lần. Điền sẵn khi lập phiếu 'lương đợt 1' ở màn Lương; duyệt xong mới trừ."
                  >
                    <input
                      type="number"
                      min={0}
                      step={100000}
                      value={luongDot1}
                      onChange={(e) => setLuongDot1(Number(e.target.value))}
                    />
                  </Field>
                  <Field
                    label="% hoa hồng (NV kinh doanh)"
                    hint="Bỏ trống / 0 nếu không phải nhân viên kinh doanh."
                  >
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={0.5}
                      value={commissionPct || ""}
                      onChange={(e) =>
                        setCommissionPct(
                          e.target.value === "" ? 0 : Number(e.target.value),
                        )
                      }
                      placeholder="0"
                    />
                  </Field>
                  {/* <div className="banner banner--warn ns-wizard__full">
                    Ô này <b>chỉ để KHAI</b> — hệ thống{" "}
                    <b>CHƯA tự cộng hoa hồng vào lương</b>. Muốn trả thì vẫn
                    phải thêm bằng tay ở <b>khoản thu nhập</b> của nhân viên
                    hoặc ngay trên phiếu lương.
                  </div> */}
                  <div className="ns-wizard__full">
                    <div className="ns-field__label">
                      Khoản thu nhập / phụ cấp
                    </div>
                    {picked.length === 0 && (
                      <p className="ns-wizard__hint">
                        Chưa chọn khoản nào. Chọn từ danh mục bên dưới — mỗi
                        khoản đã mang sẵn quy tắc chịu thuế TNCN hay không.
                      </p>
                    )}
                    {picked.map((p, i) => {
                      const c = comps?.find((x) => x.id === p.id);
                      return (
                        <div key={p.id} className="ns-comp-row">
                          <span className="ns-comp-row__name">
                            {c?.name ?? `#${p.id}`}
                            <span
                              className={
                                c?.is_taxable
                                  ? "ns-tag ns-tag--tax"
                                  : "ns-tag ns-tag--free"
                              }
                            >
                              {c?.is_taxable ? "Chịu thuế" : "Miễn thuế"}
                            </span>
                          </span>
                          <input
                            type="number"
                            min={0}
                            step={50000}
                            value={p.amount}
                            onChange={(e) =>
                              setPicked(
                                picked.map((x, j) =>
                                  j === i
                                    ? { ...x, amount: Number(e.target.value) }
                                    : x,
                                ),
                              )
                            }
                          />
                          <input
                            type="text"
                            placeholder="Ghi chú (không bắt buộc)"
                            value={p.note}
                            onChange={(e) =>
                              setPicked(
                                picked.map((x, j) =>
                                  j === i ? { ...x, note: e.target.value } : x,
                                ),
                              )
                            }
                          />
                          <button
                            type="button"
                            className="btn btn--ghost"
                            onClick={() =>
                              setPicked(picked.filter((_, j) => j !== i))
                            }
                          >
                            Gỡ
                          </button>
                        </div>
                      );
                    })}
                    <div className="ns-comp-add">
                      <button
                        type="button"
                        className="btn btn--ghost ns-comp-add__btn"
                        onClick={() => setPickOpen((v) => !v)}
                      >
                        + Thêm khoản thu nhập
                      </button>
                      {pickOpen && (
                        <>
                          <div
                            className="ns-comp-pop__veil"
                            onClick={() => setPickOpen(false)}
                          />
                          <div className="ns-comp-pop" role="listbox">
                            {(comps ?? []).filter(
                              (c) =>
                                c.is_active &&
                                !picked.some((p) => p.id === c.id),
                            ).length === 0 ? (
                              <p className="ns-comp-pop__empty">
                                Đã chọn hết khoản đang dùng.
                              </p>
                            ) : (
                              (comps ?? [])
                                .filter(
                                  (c) =>
                                    c.is_active &&
                                    !picked.some((p) => p.id === c.id),
                                )
                                .map((c) => (
                                  <button
                                    key={c.id}
                                    type="button"
                                    role="option"
                                    aria-selected={false}
                                    onClick={() => {
                                      setPicked([
                                        ...picked,
                                        { id: c.id, amount: 0, note: "" },
                                      ]);
                                      setPickOpen(false);
                                    }}
                                  >
                                    <span className="ns-comp-pop__name">
                                      {c.name}
                                    </span>
                                    <span
                                      className={
                                        c.is_taxable
                                          ? "ns-tag ns-tag--tax"
                                          : "ns-tag ns-tag--free"
                                      }
                                    >
                                      {c.is_taxable ? "Chịu thuế" : "Miễn thuế"}
                                    </span>
                                  </button>
                                ))
                            )}
                            <div className="ns-comp-pop__foot">
                              Không thấy khoản cần dùng? Tạo ở{" "}
                              <b>Cấu hình lương → Danh mục khoản thu nhập</b>.
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                  <label className="ns-check ns-wizard__full">
                    <input
                      type="checkbox"
                      checked={insuranceElsewhere}
                      onChange={(e) => setInsuranceElsewhere(e.target.checked)}
                    />
                    Bảo hiểm đóng ở nơi khác — công ty chỉ đóng TNLĐ-BNN (không
                    trừ BHXH/BHYT/BHTN của NV)
                  </label>
                  <label className="ns-check ns-wizard__full">
                    <input
                      type="checkbox"
                      checked={unionMember}
                      onChange={(e) => setUnionMember(e.target.checked)}
                    />
                    Đoàn viên công đoàn — có trừ đoàn phí công đoàn
                  </label>
                  {form.status === "probation" && salaryBase > 0 && (
                    <div className="ns-wizard__hint ns-wizard__hint--tv">
                      Thử việc: hệ thống tính 80% mức nền, dự kiến{" "}
                      {money(salaryBase * 0.8)} trước công và phụ cấp.
                    </div>
                  )}
                </>
              ) : (
                <div className="ns-wizard__hint">
                  Bạn không có quyền khai lương. Hồ sơ sẽ được tạo trước và
                  người có quyền Lương sẽ bổ sung mức sau.
                </div>
              )}
              <div className="ns-wizard__section-title ns-wizard__full">
                Bảo hiểm, thuế và tài khoản nhận lương
              </div>
              <Field label="Số sổ BHXH">
                <input
                  value={form.social_insurance_no ?? ""}
                  onChange={(e) => set("social_insurance_no", e.target.value)}
                />
              </Field>
              <Field label="MST cá nhân">
                <input
                  value={form.pit_tax_code ?? ""}
                  onChange={(e) => set("pit_tax_code", e.target.value)}
                />
              </Field>
              <Field label="Người phụ thuộc">
                <input
                  type="number"
                  min={0}
                  value={form.dependents_count ?? 0}
                  onChange={(e) =>
                    set("dependents_count", Number(e.target.value))
                  }
                />
              </Field>
              <Field label="Số tài khoản">
                <input
                  value={form.bank_account ?? ""}
                  onChange={(e) => set("bank_account", e.target.value)}
                />
              </Field>
              <Field label="Ngân hàng">
                <input
                  value={form.bank_name ?? ""}
                  onChange={(e) => set("bank_name", e.target.value)}
                />
              </Field>
            </div>
          )}

          {STEPS[step] === "Đính kèm" && (
            <div>
              <FilePicker
                onAdd={(file, kind) =>
                  setFiles((fs) => [...fs, { file, doc_kind: kind }])
                }
              />
              <ul className="ns-filelist-v2">
                {files.map((f, i) => {
                  const typeInfo = getFileTypeInfo(f.file.name);
                  const IconComponent = typeInfo.icon;
                  return (
                    <li key={i} className="ns-fileitem">
                      <div className={`ns-fileitem__icon ${typeInfo.className}`}>
                        <IconComponent size={18} />
                      </div>
                      <div className="ns-fileitem__main">
                        <div className="ns-fileitem__name-group">
                          <span className="ns-fileitem__name" title={f.file.name}>
                            {f.file.name}
                          </span>
                          <div className="ns-fileitem__sub">
                            {formatFileSize(f.file.size)}
                          </div>
                        </div>
                        <span className="ns-fileitem__badge">
                          {DOC_KIND_LABEL[f.doc_kind] ?? f.doc_kind}
                        </span>
                      </div>
                      <div className="ns-fileitem__actions">
                        <button
                          type="button"
                          className="btn btn--ghost ns-danger btn--sm"
                          style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                          title="Xóa tệp"
                          onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))}
                        >
                          <Trash2 size={13} /> Bỏ
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {STEPS[step] === "Tài khoản" && (
            <div>
              <label className="ns-check">
                <input
                  type="checkbox"
                  checked={makeAccount}
                  onChange={(e) => setMakeAccount(e.target.checked)}
                />
                Tạo tài khoản đăng nhập cho nhân viên này
              </label>
              {makeAccount && (
                <div className="ns-grid" style={{ marginTop: 12 }}>
                  <Field label="Tên đăng nhập *">
                    <input
                      value={acc.username}
                      onChange={(e) =>
                        setAcc({ ...acc, username: e.target.value })
                      }
                    />
                  </Field>
                  <Field label="Mật khẩu tạm *">
                    <input
                      type="text"
                      value={acc.password}
                      onChange={(e) =>
                        setAcc({ ...acc, password: e.target.value })
                      }
                    />
                  </Field>
                  {/* Không có vai trò thì NV đăng nhập được nhưng không thấy gì — phải chọn ngay
                      tại đây, đừng bắt sang màn khác gán. Vai trò thuộc phòng của hồ sơ. */}
                  <Field label="Vai trò">
                    <select
                      value={acc.role_id}
                      onChange={(e) =>
                        setAcc({
                          ...acc,
                          role_id: e.target.value ? Number(e.target.value) : "",
                        })
                      }
                    >
                      <option value="">
                        — chưa gán (đăng nhập nhưng chưa thấy gì) —
                      </option>
                      {meta.roles
                        .filter((r) => r.department_id === form.department_id)
                        .map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.name}
                          </option>
                        ))}
                    </select>
                  </Field>
                </div>
              )}
              <div className="ns-review">
                <h4>Xem lại</h4>
                <p>
                  <strong>{form.full_name || "(chưa nhập tên)"}</strong> ·{" "}
                  {meta.departments.find((d) => d.id === form.department_id)
                    ?.name ?? "—"}{" "}
                  · {form.status === "active" ? "Chính thức" : "Thử việc"}
                  {gradeName ? ` · ${gradeName}` : ""}
                </p>
                {canSalary && (
                  <p>
                    Lương cơ bản <strong>{money(salaryBase)}</strong>
                  </p>
                )}
                {canSalary && commissionPct > 0 && (
                  <p>Hoa hồng {commissionPct}% (chỉ khai)</p>
                )}
                <p>
                  Ngày vào {fmtDate(form.hire_date)} · {files.length} tệp đính
                  kèm
                  {makeAccount && acc.username
                    ? ` · tài khoản "${acc.username}"${acc.role_id ? ` (${meta.roles.find((r) => r.id === acc.role_id)?.name})` : " — CHƯA gán vai trò"}`
                    : ""}
                </p>
              </div>
            </div>
          )}
        </div>

        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <div className="ns-modal__footright">
            {step > 0 && (
              <button
                className="btn btn--ghost"
                onClick={() => setStep((s) => s - 1)}
                disabled={busy}
              >
                ‹ Trước
              </button>
            )}
            {/* Nút ĐI TỚI của wizard = hành động chính của hộp thoại → cam (`accent`).
                "Tiếp" và "Lưu" không bao giờ hiện cùng lúc nên vẫn đúng luật MỘT nút cam. */}
            {step < STEPS.length - 1 && (
              <Button variant="accent" onClick={() => setStep((s) => s + 1)}>
                Tiếp ›
              </Button>
            )}
            {step === STEPS.length - 1 && (
              <Button variant="accent" onClick={submit} loading={busy}>
                {busy ? "Đang lưu…" : "Lưu & xem hồ sơ"}
              </Button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}
