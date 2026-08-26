// Tab Thông tin của hồ sơ nhân sự (tách từ pages/NhanSuPage.tsx).
import { useEffect, useState } from "react";
import {
  api,
  type EmployeeDetail,
  type EmployeeInput,
  type EmployeeMeta,
  type WorkShift,
} from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { fmtDate } from "../../../../utils/format";
import {
  Briefcase,
  Calendar,
  Clock,
  FileText,
  Mail,
  MapPin,
  Phone,
  TrendingUp,
  UserCheck,
  Users,
} from "lucide-react";
import { GENDER_LABEL } from "../shared/constants";
import { errMsg, isProduction } from "../shared/helpers";
import { Field } from "../components/form-fields";
import { InfoCard, InfoField } from "../components/info-display";

export function InfoTab({
  token,
  emp,
  meta,
  canUpdate,
  edit,
  setEdit,
  onSaved,
}: {
  token: string;
  emp: EmployeeDetail;
  meta: EmployeeMeta | null;
  canUpdate: boolean;
  edit: boolean;
  setEdit: (e: boolean) => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<EmployeeInput>({
    ...emp,
  } as unknown as EmployeeInput);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shifts, setShifts] = useState<WorkShift[]>([]);
  useEffect(() => {
    api.attendance
      .shifts(token)
      .then((r) => setShifts(r.items))
      .catch(() => setShifts([]));
  }, [token]);
  const shiftName =
    shifts.find((s) => s.id === emp.default_shift_id)?.name ?? null;
  const resigned = emp.status === "resigned";

  function set<K extends keyof EmployeeInput>(k: K, v: EmployeeInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }
  async function save() {
    setBusy(true);
    setError(null);
    try {
      // Ca làm việc KHÔNG gán ở đây nữa (Chấm công → Khai ca → Phân ca tháng là nơi duy
      // nhất). Bỏ khỏi payload để form hồ sơ không bao giờ ghi đè ca — đường ghi này
      // không tạo mốc hiệu lực nên sẽ làm mất dấu lịch sử đổi ca.
      const { default_shift_id: _ignored, ...payload } = form;
      await api.employees.update(token, emp.id, payload as EmployeeInput);
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
          <Field label="Họ tên *">
            <input
              value={form.full_name}
              onChange={(e) => set("full_name", e.target.value)}
            />
          </Field>
          <Field label="Chức danh">
            <input
              value={form.position ?? ""}
              onChange={(e) => set("position", e.target.value)}
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
          <Field label="CCCD">
            <input
              value={form.national_id ?? ""}
              onChange={(e) => set("national_id", e.target.value)}
            />
          </Field>
          <Field label="Ngày cấp CCCD">
            <input
              type="date"
              value={form.national_id_date ?? ""}
              onChange={(e) => set("national_id_date", e.target.value)}
            />
          </Field>
          <Field label="Nơi cấp CCCD">
            <input
              value={form.national_id_place ?? ""}
              onChange={(e) => set("national_id_place", e.target.value)}
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
              onChange={(e) => set("emergency_contact_name", e.target.value)}
            />
          </Field>
          <Field label="Liên hệ khẩn (SĐT)">
            <input
              value={form.emergency_contact_phone ?? ""}
              onChange={(e) => set("emergency_contact_phone", e.target.value)}
            />
          </Field>
          <Field label="Ghi chú">
            <input
              value={form.note ?? ""}
              onChange={(e) => set("note", e.target.value)}
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
        <InfoCard title="Định danh & việc làm" icon={Briefcase}>
          <InfoField label="Mã NV" value={emp.code} icon={Briefcase} />
          <InfoField
            label="Phòng/Tổ"
            value={emp.department_name}
            icon={Users}
          />
          <InfoField label="Chức danh" value={emp.position} icon={UserCheck} />
          {/* NƠI DUY NHẤT hiện bậc trong hồ sơ. Bậc không dính tiền nên không thuộc tab Lương,
              và chỉ đổi được qua Thao tác hồ sơ (đường ghi thẳng đã bị backend bỏ qua). */}
          {(isProduction(meta, emp.department_id) ||
            (emp.job_grade_name ?? emp.job_grade)) && (
            <InfoField
              label="Bậc tay nghề"
              value={emp.job_grade_name ?? emp.job_grade}
              icon={TrendingUp}
              hint={
                canUpdate && !resigned
                  ? "Đổi bậc ở Thao tác hồ sơ → Nâng bậc / Chức danh."
                  : undefined
              }
            />
          )}
          <InfoField
            label="Ngày vào"
            value={fmtDate(emp.hire_date)}
            icon={Calendar}
          />
          <InfoField
            label="Hết thử việc"
            value={fmtDate(emp.probation_end_date)}
            icon={Calendar}
          />
          <InfoField
            label="Ca làm việc"
            value={shiftName ?? "— chưa gán —"}
            icon={Clock}
            hint="Gán/đổi ca ở Chấm công → Khai ca → Phân ca tháng"
          />
          {emp.resign_date && (
            <InfoField
              label="Ngày nghỉ"
              value={fmtDate(emp.resign_date)}
              icon={Calendar}
            />
          )}
          {emp.resign_reason && (
            <InfoField
              label="Lý do nghỉ"
              value={emp.resign_reason}
              icon={FileText}
            />
          )}
        </InfoCard>
        <InfoCard title="Cá nhân" icon={Users}>
          <InfoField
            label="Ngày sinh"
            value={fmtDate(emp.date_of_birth)}
            icon={Calendar}
          />
          <InfoField
            label="Giới tính"
            value={emp.gender ? GENDER_LABEL[emp.gender] : null}
            icon={Users}
          />
          <InfoField label="CCCD" value={emp.national_id} icon={FileText} />
          <InfoField
            label="Ngày cấp"
            value={fmtDate(emp.national_id_date)}
            icon={Calendar}
          />
          <InfoField
            label="Nơi cấp"
            value={emp.national_id_place}
            icon={MapPin}
          />
          <InfoField label="SĐT" value={emp.phone} icon={Phone} />
          <InfoField label="Email" value={emp.email} icon={Mail} />
          <InfoField
            label="Hộ khẩu"
            value={emp.permanent_address}
            icon={MapPin}
          />
          <InfoField label="Chỗ ở" value={emp.current_address} icon={MapPin} />
          <InfoField
            label="Liên hệ khẩn"
            value={
              emp.emergency_contact_name
                ? `${emp.emergency_contact_name} · ${emp.emergency_contact_phone ?? ""}`
                : null
            }
            icon={Phone}
          />
        </InfoCard>
      </div>
      <InfoCard title="Khác" icon={FileText}>
        <InfoField label="Ghi chú" value={emp.note} icon={FileText} />
      </InfoCard>
    </div>
  );
}
