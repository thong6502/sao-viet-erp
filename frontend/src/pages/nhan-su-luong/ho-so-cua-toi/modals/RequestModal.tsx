// Modal gửi đề nghị HCNS sửa field bảo vệ (tách từ pages/HoSoCuaToiPage.tsx).
import { useState } from "react";
import {
  api,
  EMPLOYEE_FIELD_MAXLEN,
  type EmployeeDetail,
  type UpdateRequestInput,
} from "../../../../api/client";
import { Icon } from "../../../../components/Icons";

// Đề nghị sửa field bảo vệ → HCNS duyệt. Chỉ gửi field ĐÃ ĐỔI so với hiện tại.
export function RequestModal({ token, emp, onClose, onSaved }: {
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
  // Chặn độ dài NGAY Ở Ô NHẬP theo đúng độ dài cột hồ sơ. Không có `maxLength` thì gõ 44 ký
  // tự vào ô "Số tài khoản" (chỉ chứa 30) vẫn gửi đi bình thường — đề nghị nằm dạng JSON nên
  // không ai đo — và mãi tới lúc HCNS bấm Duyệt mới vỡ, người duyệt lãnh lỗi thay người gõ.
  const F = (label: string, k: string, type = "text", placeholder = "", className = "") => {
    const max = EMPLOYEE_FIELD_MAXLEN[k];
    const cham = max !== undefined && (form[k]?.length ?? 0) >= max;
    return (
      <label className="ns-field"><span className="ns-field__label">{label}</span>
        <input type={type} className={className} placeholder={placeholder} maxLength={max}
               value={form[k]} onChange={(e) => set(k, e.target.value)} />
        {cham && <span className="mine__field-hint">Đã chạm giới hạn {max} ký tự.</span>}
      </label>
    );
  };
  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="mine-req-title">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head">
          <h2 id="mine-req-title">
            <span className="mine__modal-title-icon"><Icon name="fileText" size={15} /></span>
            Đề nghị cập nhật hồ sơ
          </h2>
          <button type="button" className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={15} />
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <div className="mine__modal-notice">
            <span className="mine__modal-notice-icon"><Icon name="alert" size={14} /></span>
            <span>Sửa các mục cần đổi rồi gửi. Phòng HCNS duyệt xong mới áp dụng vào hồ sơ. Chỉ gửi các mục bạn thay đổi.</span>
          </div>
          <div className="ns-grid">
            {F("Họ tên", "full_name", "text", "Nhập họ và tên đầy đủ")}
            {F("Ngày sinh", "date_of_birth", "date")}
            {F("CCCD", "national_id", "text", "Nhập số CCCD/CMND", "mine__input-num")}
            {F("Ngày cấp CCCD", "national_id_date", "date")}
            {F("Nơi cấp CCCD", "national_id_place", "text", "Công an Tỉnh/Thành phố...")}
            {F("Hộ khẩu", "permanent_address", "text", "Địa chỉ hộ khẩu thường trú")}
            {F("Số tài khoản", "bank_account", "text", "Nhập số tài khoản ngân hàng", "mine__input-num")}
            {F("Ngân hàng", "bank_name", "text", "Tên ngân hàng (VD: Vietcombank)")}
            {F("Người phụ thuộc", "dependents_count", "number", "0", "mine__input-num")}
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Lý do đề nghị cập nhật</span>
            <input value={reason} placeholder="Ghi rõ lý do thay đổi thông tin (không bắt buộc)..." onChange={(e) => setReason(e.target.value)} />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <div className="ns-modal__footright" style={{ marginLeft: "auto", display: "flex", gap: "10px", alignItems: "center" }}>
            <button type="button" className="mine__btn-cancel" onClick={onClose} disabled={busy}>Đóng</button>
            <button type="button" className="mine__btn-primary" onClick={save} disabled={busy}>{busy ? "Đang gửi…" : "Gửi đề nghị"}</button>
          </div>
        </footer>
      </div>
    </div>
  );
}
