// Modal đổi ảnh đại diện (tách từ pages/HoSoCuaToiPage.tsx).
import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { api, assetUrl } from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import { Button } from "../../../../components/Button";
import { Icon } from "../../../../components/Icons";
import { messageFor } from "../shared/helpers";

// === Self-service tài khoản (gộp từ ProfileDialog) — vỏ ns-modal, không dùng vỏ pd-* ===

const AVATAR_MAX_BYTES = 2 * 1024 * 1024;
const AVATAR_TYPES = ["image/jpeg", "image/png"];

// Đổi ảnh đại diện. Nhân viên & admin đều dùng; BE tự ghi vào ảnh hồ sơ nếu có hồ sơ.
// Sau lưu/xóa: updateUser (topbar đọc user.avatar_url) + onSaved→load (hero đọc emp.photo_url) — CẬP NHẬT KÉP.
export function AvatarModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { token, user, updateUser } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Revoke object URL khi preview đổi / unmount.
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  const currentSrc = assetUrl(user?.avatar_url);
  const shownSrc = previewUrl ?? currentSrc;
  const initials = (user?.name?.trim() || user?.username || "?").trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("");

  function pick(e: ChangeEvent<HTMLInputElement>) {
    setFormError(null);
    const f = e.target.files?.[0] ?? null;
    if (!f) return;
    if (!AVATAR_TYPES.includes(f.type)) { setFieldError("Ảnh phải là JPG hoặc PNG."); setFile(null); return; }
    if (f.size > AVATAR_MAX_BYTES) { setFieldError("Ảnh vượt quá 2 MB."); setFile(null); return; }
    setFieldError(null);
    setFile(f);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(f));
  }

  async function save() {
    if (!file || busy) return;
    setBusy(true); setFormError(null);
    try {
      const { avatar_url } = await api.uploadAvatar(token!, file);
      updateUser({ avatar_url });
      onSaved();
    } catch (err) { setFormError(messageFor(err)); setBusy(false); }
  }

  async function remove() {
    if (busy) return;
    setBusy(true); setFormError(null);
    try {
      await api.removeAvatar(token!);
      updateUser({ avatar_url: null });
      onSaved();
    } catch (err) { setFormError(messageFor(err)); setBusy(false); }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="mine-avatar-title">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2 id="mine-avatar-title">
            <span className="mine__modal-title-icon"><Icon name="pencil" size={15} /></span>
            Đổi ảnh đại diện
          </h2>
          <button type="button" className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={15} />
          </button>
        </header>
        <div className="ns-modal__body">
          {formError && <div className="banner banner--error" role="alert">{formError}</div>}
          <div className="mine__avatar-modal">
            <div className="ns-avatar ns-avatar--xl">{shownSrc ? <img src={shownSrc} alt="" /> : initials}</div>
            <div className="mine__avatar-modal__controls">
              <input ref={inputRef} type="file" accept="image/jpeg,image/png" className="mine__vh" onChange={pick} disabled={busy} />
              <Button type="button" variant="ghost" onClick={() => inputRef.current?.click()} disabled={busy}>Chọn ảnh…</Button>
              <p className="mine__hint">JPG hoặc PNG, tối đa 2 MB.</p>
              {fieldError && <span className="field__error" role="alert">{fieldError}</span>}
            </div>
          </div>
        </div>
        <footer className="ns-modal__foot">
          {currentSrc
            ? <Button type="button" variant="ghost" onClick={remove} disabled={busy}>Xóa ảnh</Button>
            : <span />}
          <div className="ns-modal__footright" style={{ marginLeft: "auto" }}>
            <Button type="button" variant="primary" onClick={save} loading={busy} disabled={!file}>Lưu</Button>
          </div>
        </footer>
      </div>
    </div>
  );
}
