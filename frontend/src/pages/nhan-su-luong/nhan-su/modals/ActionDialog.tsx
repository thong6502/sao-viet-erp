// Máy trạng thái điều chuyển / đổi chức danh / đổi trạng thái (tách từ pages/NhanSuPage.tsx).
import { useState } from "react";
import {
  api,
  type EmployeeDetail,
  type EmployeeMeta,
  type EmployeeTransitionInput,
} from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { ACTION_TITLE } from "../shared/constants";
import { errMsg } from "../shared/helpers";
import { Field } from "../components/form-fields";

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
  const [effective, setEffective] = useState(today);
  const [note, setNote] = useState("");
  const [newDept, setNewDept] = useState<number | "">("");
  const [newPos, setNewPos] = useState("");
  const [resignReason, setResignReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isTransition = true;

  async function submit() {
    if (kind === "promote" && !newPos.trim()) {
      setError("Nhập chức danh mới.");
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
      }
      if (kind === "promote") {
        input.new_position = newPos.trim();
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
            <Field
              label="Ngày hiệu lực"
              hint="Không chọn được ngày sau hôm nay: máy đổi trạng thái / phòng ban và khoá tài khoản ngay lúc bấm — tới ngày đó hãy bấm."
            >
              <input
                type="date"
                value={effective}
                max={today}
                onChange={(e) => setEffective(e.target.value)}
              />
            </Field>
          )}
          {kind === "transfer" && (
            <>
              <Field label="Phòng/Tổ mới *">
                <select
                  value={newDept}
                  onChange={(e) =>
                    setNewDept(e.target.value === "" ? "" : Number(e.target.value))
                  }
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
            </>
          )}
          {kind === "promote" && (
            <>
              <Field
                label="Chức danh mới *"
                hint={emp.position ? `Đang là: ${emp.position}` : "Chưa khai chức danh."}
              >
                <input
                  value={newPos}
                  onChange={(e) => setNewPos(e.target.value)}
                />
              </Field>
              <div className="ns-wizard__hint">
                Đổi chức danh KHÔNG tự đổi tiền lương. Muốn đổi mức thì sang
                Lương → Lương nhân viên → Sửa lương.
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
