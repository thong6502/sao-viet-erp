// Modal NV tự sửa thông tin liên hệ (tách từ pages/HoSoCuaToiPage.tsx).
import { useState } from "react";
import { api, type EmployeeDetail, type MyContactInput } from "../../../../api/client";
import { Icon } from "../../../../components/Icons";

export function ContactModal({ token, emp, onClose, onSaved }: {
  token: string; emp: EmployeeDetail; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<MyContactInput>({
    phone: emp.phone ?? "", email: emp.email ?? "", current_address: emp.current_address ?? "",
    emergency_contact_name: emp.emergency_contact_name ?? "", emergency_contact_phone: emp.emergency_contact_phone ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  function set<K extends keyof MyContactInput>(k: K, v: MyContactInput[K]) { setForm((f) => ({ ...f, [k]: v })); }
  async function save() {
    setBusy(true); setErr(null);
    try { await api.employees.updateMe(token, form); onSaved(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Lỗi khi lưu."); setBusy(false); }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="mine-contact-title">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2 id="mine-contact-title">
            <span className="mine__modal-title-icon"><Icon name="users" size={15} /></span>
            Cập nhật thông tin liên hệ
          </h2>
          <button type="button" className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={15} />
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <div className="mine__modal-notice">
            <span className="mine__modal-notice-icon"><Icon name="alert" size={14} /></span>
            <span>Bạn chỉ sửa được thông tin liên lạc. Các thông tin định danh, chức danh, lương &amp; BHXH do phòng HCNS quản lý.</span>
          </div>
          <div className="ns-grid">
            <label className="ns-field">
              <span className="ns-field__label">SĐT cá nhân</span>
              <div className="mine__input-wrap">
                <Icon name="phone" size={15} className="mine__input-icon" />
                <input className="mine__input-num" value={form.phone ?? ""} placeholder="090x xxx xxx" onChange={(e) => set("phone", e.target.value)} />
              </div>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Email</span>
              <div className="mine__input-wrap">
                <Icon name="mail" size={15} className="mine__input-icon" />
                <input type="email" value={form.email ?? ""} placeholder="email@example.com" onChange={(e) => set("email", e.target.value)} />
              </div>
            </label>
            <label className="ns-field" style={{ gridColumn: "1 / -1" }}>
              <span className="ns-field__label">Chỗ ở hiện tại</span>
              <div className="mine__input-wrap">
                <Icon name="mapPin" size={15} className="mine__input-icon" />
                <input value={form.current_address ?? ""} placeholder="Nhập địa chỉ chỗ ở hiện tại..." onChange={(e) => set("current_address", e.target.value)} />
              </div>
            </label>

            <div className="mine__modal-emergency-box">
              <div className="mine__modal-section-title">
                <Icon name="users" size={14} /> Liên hệ khẩn cấp
              </div>
              <div className="ns-grid" style={{ gap: "12px", width: "100%" }}>
                <label className="ns-field">
                  <span className="ns-field__label">Họ tên người liên hệ</span>
                  <div className="mine__input-wrap">
                    <Icon name="users" size={15} className="mine__input-icon" />
                    <input value={form.emergency_contact_name ?? ""} placeholder="Họ và tên người thân" onChange={(e) => set("emergency_contact_name", e.target.value)} />
                  </div>
                </label>
                <label className="ns-field">
                  <span className="ns-field__label">SĐT người liên hệ</span>
                  <div className="mine__input-wrap">
                    <Icon name="phone" size={15} className="mine__input-icon" />
                    <input className="mine__input-num" value={form.emergency_contact_phone ?? ""} placeholder="090x xxx xxx" onChange={(e) => set("emergency_contact_phone", e.target.value)} />
                  </div>
                </label>
              </div>
            </div>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <div className="ns-modal__footright" style={{ marginLeft: "auto", display: "flex", gap: "10px", alignItems: "center" }}>
            <button type="button" className="mine__btn-cancel" onClick={onClose} disabled={busy}>Đóng</button>
            <button type="button" className="mine__btn-primary" onClick={save} disabled={busy}>
              {busy ? "Đang lưu…" : "Lưu thay đổi"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
