// Modal đổi mật khẩu (tách từ pages/HoSoCuaToiPage.tsx).
import { useState, type FormEvent } from "react";
import { api } from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import { Button } from "../../../../components/Button";
import { Field } from "../../../../components/Field";
import { Icon } from "../../../../components/Icons";
import { messageFor } from "../shared/helpers";

interface PwErrors { current?: string; next?: string; confirm?: string; }

// Đổi mật khẩu. Thành công (204) → báo + logout về Login. 400 (sai mật khẩu cũ) → lỗi inline, giữ form.
export function PasswordModal({ onClose }: { onClose: () => void }) {
  const { token, logout, setNotice } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [errors, setErrors] = useState<PwErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function validate(): PwErrors {
    const e: PwErrors = {};
    if (!current) e.current = "Vui lòng nhập mật khẩu hiện tại.";
    if (next.length < 8) e.next = "Mật khẩu mới tối thiểu 8 ký tự.";
    else if (!/[a-zA-Z]/.test(next) || !/\d/.test(next)) e.next = "Mật khẩu mới phải gồm cả chữ và số.";
    if (confirm !== next) e.confirm = "Xác nhận mật khẩu không khớp.";
    return e;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (saving) return;
    setFormError(null);
    const errs = validate();
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;
    setSaving(true);
    try {
      await api.changePassword(token!, current, next);
      setNotice("Đổi mật khẩu thành công. Vui lòng đăng nhập lại.");
      await logout();
    } catch (err) { setFormError(messageFor(err)); setSaving(false); }
  }

  const inputType = show ? "text" : "password";
  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="mine-pw-title">
      <form className="ns-modal__box" onSubmit={onSubmit} noValidate>
        <header className="ns-modal__head">
          <h2 id="mine-pw-title">
            <span className="mine__modal-title-icon"><Icon name="shield" size={15} /></span>
            Đổi mật khẩu
          </h2>
          <button type="button" className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={15} />
          </button>
        </header>
        <div className="ns-modal__body">
          {formError && <div className="banner banner--error" role="alert">{formError}</div>}
          <div className="mine__form">
            <Field label="Mật khẩu hiện tại" type={inputType} autoComplete="current-password" value={current} error={errors.current} onChange={(e) => setCurrent(e.target.value)} disabled={saving} />
            <Field label="Mật khẩu mới" type={inputType} autoComplete="new-password" value={next} error={errors.next} onChange={(e) => setNext(e.target.value)} disabled={saving} />
            <Field label="Xác nhận mật khẩu mới" type={inputType} autoComplete="new-password" value={confirm} error={errors.confirm} onChange={(e) => setConfirm(e.target.value)} disabled={saving} />
            <label className="mine__pw-show"><input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> Hiện mật khẩu</label>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <div className="ns-modal__footright" style={{ marginLeft: "auto" }}>
            <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu mật khẩu</Button>
          </div>
        </footer>
      </form>
    </div>
  );
}
