// Modal đổi tên hiển thị (tách từ pages/HoSoCuaToiPage.tsx).
import { useState, type FormEvent } from "react";
import { api } from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import { Button } from "../../../../components/Button";
import { Field } from "../../../../components/Field";
import { Icon } from "../../../../components/Icons";
import { messageFor } from "../shared/helpers";

// Đổi tên hiển thị — chỉ cho tài khoản CHƯA gắn hồ sơ (BE trả 400 nếu tài khoản có hồ sơ: tên do HCNS/hồ sơ quyết).
export function NameModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { token, user, updateUser } = useAuth();
  const [name, setName] = useState(user?.name ?? "");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (saving) return;
    setFormError(null);
    const trimmed = name.trim();
    if (!trimmed) { setFieldError("Tên hiển thị không được để trống."); return; }
    if (trimmed.length > 100) { setFieldError("Tên hiển thị tối đa 100 ký tự."); return; }
    setFieldError(null);
    setSaving(true);
    try {
      const updated = await api.updateName(token!, trimmed);
      updateUser({ name: updated.name });
      onSaved();
    } catch (err) { setFormError(messageFor(err)); setSaving(false); }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="mine-name-title">
      <form className="ns-modal__box" onSubmit={onSubmit} noValidate>
        <header className="ns-modal__head">
          <h2 id="mine-name-title">
            <span className="mine__modal-title-icon"><Icon name="users" size={15} /></span>
            Đổi tên hiển thị
          </h2>
          <button type="button" className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={15} />
          </button>
        </header>
        <div className="ns-modal__body">
          {formError && <div className="banner banner--error" role="alert">{formError}</div>}
          <div className="mine__form">
            <Field label="Tên hiển thị" value={name} error={fieldError ?? undefined} maxLength={120} autoFocus onChange={(e) => setName(e.target.value)} disabled={saving} />
          </div>
        </div>
        <footer className="ns-modal__foot">
          <div className="ns-modal__footright" style={{ marginLeft: "auto" }}>
            <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu</Button>
          </div>
        </footer>
      </form>
    </div>
  );
}
