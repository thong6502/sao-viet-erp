// Máy trạng thái điều chuyển / thăng chức / đổi trạng thái (tách từ pages/NhanSuPage.tsx).
import { useState } from "react";
import {
  api,
  type EmployeeDetail,
  type EmployeeMeta,
  type EmployeeTransitionInput,
} from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { useCan } from "../../../../auth/permissions";
import { ACTION_TITLE } from "../shared/constants";
import { errMsg, isProduction } from "../shared/helpers";
import { useJobGrades } from "../hooks/useJobGrades";
import { Field, JobGradeField } from "../components/form-fields";

// --- Action dialog (transition / transfer / promote / account) --------------

export function ActionDialog({
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
  const can = useCan();
  const canCreateGrade = can("nhan_su", "create");
  const jg = useJobGrades(token);
  const [effective, setEffective] = useState(today);
  const [note, setNote] = useState("");
  const [newDept, setNewDept] = useState<number | "">("");
  // KHÔNG preselect bậc hiện tại: danh mục chỉ trả bậc đang BẬT, người mang bậc đã tắt sẽ bị
  // select nhảy về option đầu rồi âm thầm đổi bậc lúc bấm Xác nhận.
  const [newJobGradeId, setNewJobGradeId] = useState<number | null>(null);
  const [newPos, setNewPos] = useState("");
  const [resignReason, setResignReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isTransition = true;
  const curGrade = emp.job_grade_name ?? emp.job_grade;
  // Người đang mang bậc (kể cả bậc kiểu cũ) vẫn phải sửa được bậc dù phòng chưa tick cờ SX.
  const showGrade =
    isProduction(meta, emp.department_id) ||
    emp.job_grade_id != null ||
    !!emp.job_grade;
  // Điều chuyển: backend XOÁ bậc khi không nhận `new_job_grade_id` (bậc tổ In vô nghĩa ở tổ Dán).
  const transferDropsGrade =
    kind === "transfer" &&
    !!curGrade &&
    newDept !== "" &&
    newJobGradeId == null;

  async function submit() {
    if (kind === "promote" && newJobGradeId == null && !newPos.trim()) {
      setError(
        showGrade
          ? "Chọn bậc tay nghề mới hoặc nhập chức danh mới."
          : "Nhập chức danh mới.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const input: EmployeeTransitionInput = {
        kind,
        effective_date: effective,
        note: note || undefined,
      };
      if (kind === "transfer") {
        input.new_department_id = newDept === "" ? undefined : newDept;
        input.new_job_grade_id = newJobGradeId ?? undefined;
      }
      if (kind === "promote") {
        input.new_job_grade_id = newJobGradeId ?? undefined;
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
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}

          {isTransition && (
            <Field label="Ngày hiệu lực">
              <input
                type="date"
                value={effective}
                onChange={(e) => setEffective(e.target.value)}
              />
            </Field>
          )}
          {kind === "transfer" && (
            <>
              <Field label="Phòng/Tổ mới *">
                <select
                  value={newDept}
                  onChange={(e) => {
                    setNewDept(
                      e.target.value === "" ? "" : Number(e.target.value),
                    );
                    setNewJobGradeId(null); // bậc khai theo TỔ MỚI → đổi tổ thì bỏ lựa chọn cũ
                  }}
                >
                  <option value="">— chọn —</option>
                  {meta?.departments
                    .filter((d) => d.id !== emp.department_id)
                    .map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                </select>
              </Field>
              {newDept !== "" && isProduction(meta, newDept) && (
                <JobGradeField
                  grades={jg.grades}
                  err={jg.err}
                  reload={jg.reload}
                  addGrade={jg.addGrade}
                  value={newJobGradeId}
                  onChange={setNewJobGradeId}
                  label="Bậc tay nghề ở tổ mới"
                  hint="Bậc khai lại theo tổ mới — bậc của tổ cũ không mang sang."
                  canCreate={canCreateGrade}
                />
              )}
              {transferDropsGrade && (
                <div className="banner banner--warn">
                  Chuyển tổ mà không chọn bậc ⇒ bậc hiện tại (<b>{curGrade}</b>)
                  sẽ bị <b>xoá khỏi hồ sơ</b>.
                </div>
              )}
            </>
          )}
          {kind === "promote" && (
            <>
              {showGrade && (
                <JobGradeField
                  grades={jg.grades}
                  err={jg.err}
                  reload={jg.reload}
                  addGrade={jg.addGrade}
                  value={newJobGradeId}
                  onChange={setNewJobGradeId}
                  label="Bậc tay nghề mới"
                  hint={curGrade ? `Đang ở: ${curGrade}` : "Chưa khai bậc."}
                  allowKeep
                  canCreate={canCreateGrade}
                />
              )}
              <Field label="Chức danh mới (tùy chọn)">
                <input
                  value={newPos}
                  onChange={(e) => setNewPos(e.target.value)}
                />
              </Field>
              <div className="ns-wizard__hint">
                Nâng bậc / đổi chức danh KHÔNG tự đổi tiền lương — bậc chỉ là
                khai báo. Muốn đổi mức thì sang Lương → Lương nhân viên → Sửa
                lương.
              </div>
            </>
          )}
          {kind === "resign" && (
            <Field label="Lý do nghỉ *">
              <input
                value={resignReason}
                onChange={(e) => setResignReason(e.target.value)}
              />
            </Field>
          )}
          {isTransition && kind !== "resign" && (
            <Field label="Ghi chú">
              <input value={note} onChange={(e) => setNote(e.target.value)} />
            </Field>
          )}
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <Button variant="accent" onClick={submit} loading={busy}>
            {busy ? "Đang xử lý…" : "Xác nhận"}
          </Button>
        </footer>
      </div>
    </div>
  );
}
