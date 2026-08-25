// Form khai loại nghỉ (tách từ pages/NghiPhepPage.tsx).
import { useState } from "react";
import {
  api,
  ApiError,
  type LeaveType,
  type LeaveTypeInput,
} from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { errMsg } from "../shared/helpers";

export function LeaveTypeForm({ token, type, onClose, onSaved }: {
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
      if (!form.name.trim()) throw new ApiError("Vui lòng nhập tên loại nghỉ.", 400);
      if (type) await api.leaves.updateType(token, type.id, form);
      else await api.leaves.createType(token, form);
      onSaved();
    } catch (e) { setError(errMsg(e)); setBusy(false); }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <div className="cc-modal-title-group">
            <h2>{type ? "Chỉnh sửa loại nghỉ phép" : "Tạo loại nghỉ phép mới"}</h2>
            <p className="cc-modal-subtitle">Cấu hình chế độ lương và hạn mức nghỉ phép hàng năm</p>
          </div>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body cc-day-detail-modal-body">
          {error && <div className="banner banner--error cc-ts-msg-banner" style={{ marginBottom: "16px" }}>{error}</div>}
          
          <label className="ns-field">
            <span className="cc-field-label">Tên loại nghỉ phép *</span>
            <input className="cc-input-text" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="vd: Phép năm, Nghỉ ốm, Việc riêng..." />
          </label>
          
          <div className="ns-grid" style={{ marginTop: 14 }}>
            <label className="ns-field">
              <span className="cc-field-label">Hạn mức / năm (số ngày)</span>
              <input type="number" className="cc-input-text" min={0} value={form.annual_quota} onChange={(e) => set("annual_quota", Number(e.target.value))} placeholder="0 = Không giới hạn" />
              <span className="cc-field-subtext">Nhập 0 nếu không áp dụng hạn mức năm (cho nghỉ không lương / ốm)</span>
            </label>
          </div>
          
          <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 14 }}>
            <label className="ns-check" style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
              <input type="checkbox" checked={!!form.is_paid} onChange={(e) => set("is_paid", e.target.checked)} /> 
              <div>
                <span className="cc-field-label" style={{ margin: 0 }}>Hưởng nguyên lương (Tính công P)</span>
                <span className="cc-field-subtext" style={{ display: "block" }}>Đơn nghỉ loại này được duyệt sẽ tự động chấm công ký hiệu P trên Bảng công tháng.</span>
              </div>
            </label>

            <label className="ns-check" style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
              <input type="checkbox" checked={!!form.is_active} onChange={(e) => set("is_active", e.target.checked)} /> 
              <div>
                <span className="cc-field-label" style={{ margin: 0 }}>Đang sử dụng loại nghỉ này</span>
                <span className="cc-field-subtext" style={{ display: "block" }}>Cho phép nhân viên chọn loại nghỉ này khi tạo đơn xin nghỉ mới.</span>
              </div>
            </label>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <Button variant="accent" onClick={save} loading={busy}>{busy ? "Đang lưu…" : "Lưu cấu hình"}</Button>
        </footer>
      </div>
    </div>
  );
}
