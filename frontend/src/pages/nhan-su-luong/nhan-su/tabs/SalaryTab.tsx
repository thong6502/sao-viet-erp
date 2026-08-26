// Tab Lương & BHXH của hồ sơ nhân sự (tách từ pages/NhanSuPage.tsx).
import { useState } from "react";
import {
  api,
  PIT_MODE_META,
  type EmployeeDetail,
  type EmployeeInput,
} from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { CreditCard, FileText, Lock, Users } from "lucide-react";
import { errMsg } from "../shared/helpers";
import { Field } from "../components/form-fields";
import { CommissionCard } from "../components/badges";
import { InfoCard, InfoField } from "../components/info-display";

// Tab Lương & BHXH — dữ liệu nhạy cảm (chỉ hiện với quyền `nhan_su:view_salary`).
// "Nhóm lương / Bậc lương" (`payroll_group` / `pay_grade_key`) VẪN ĐỂ NGOÀI MÀN: PRD v2 bỏ hẳn
// "mức mặc định theo nhóm" nên nhóm lương không còn trục dùng nào, engine cũng không đọc — để
// lại chỉ khiến người dùng tưởng chọn nhóm là đã gán lương (PRD Cấu hình lương §8, bệnh B3).
// Khoản thu nhập gán theo TỪNG NGƯỜI: Lương → Lương nhân viên → Sửa lương → "+ Thêm khoản thu
// nhập" (CHỌN từ danh mục — màn nhân sự không có đường tạo khoản mới).
// Cách tính thuế TNCN (`pit_mode`) chỉ HIỆN ở đây, sửa ở Lương → Lương nhân viên → Sửa lương
// (một nơi khai, tránh 2 chỗ cùng sửa một số).
export function SalaryTab({
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
  const [form, setForm] = useState<EmployeeInput>({
    ...emp,
  } as unknown as EmployeeInput);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
        {/* Không còn ô "Bậc thợ" ở đây: `PUT /api/employees/{id}` CỐ TÌNH bỏ qua bậc (đổi bậc
            phải sinh mốc quá trình công tác) ⇒ ô sửa ở đây là đường ghi CHẾT, gõ xong bấm Lưu
            vẫn không đổi gì. Bậc xem ở tab Thông tin, đổi ở Thao tác hồ sơ → Nâng bậc. */}
        <div className="ns-grid">
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
          <Field
            label="Người phụ thuộc"
            hint="Mỗi người phụ thuộc được giảm trừ thêm khi tính thuế TNCN (mức lấy ở Cấu hình lương)."
          >
            <input
              type="number"
              min={0}
              value={form.dependents_count ?? 0}
              onChange={(e) => set("dependents_count", Number(e.target.value))}
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
        <div className="ns2-editfoot">
          <button
            className="btn btn--ghost"
            onClick={() => setEdit(false)}
            disabled={busy}
          >
            Hủy
          </button>
          {/* Hành động chính của form đang mở → cam. Mỗi tab chỉ có ĐÚNG một nút Lưu nên
              khay hồ sơ không bao giờ hiện hai nút cam cùng lúc. */}
          <Button variant="accent" onClick={save} loading={busy}>
            {busy ? "Đang lưu…" : "Lưu"}
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div>
      <div className="ns-info-sections">
        <CommissionCard token={token} employeeId={emp.id} />
        <InfoCard title="BHXH / TNCN" icon={FileText}>
          <InfoField
            label="Số sổ BHXH"
            value={emp.social_insurance_no}
            icon={FileText}
          />
          <InfoField
            label="MST cá nhân"
            value={emp.pit_tax_code}
            icon={FileText}
          />
          <InfoField
            label="Người phụ thuộc"
            value={String(emp.dependents_count)}
            icon={Users}
          />
          <InfoField
            label="Cách tính thuế TNCN"
            value={emp.pit_mode ? PIT_MODE_META[emp.pit_mode].label : null}
            icon={FileText}
            hint="Đổi ở Lương → Lương nhân viên → Sửa lương."
          />
        </InfoCard>
      </div>
      <InfoCard title="Ngân hàng" icon={Lock}>
        <InfoField
          label="Tài khoản NH"
          value={
            emp.bank_account
              ? `${emp.bank_account} · ${emp.bank_name ?? ""}`
              : null
          }
          icon={CreditCard}
        />
      </InfoCard>
    </div>
  );
}
