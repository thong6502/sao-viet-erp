// Profile dialog (spec-04, feat-019..022). A single modal whose body switches on the
// chosen action from the Topbar user menu: read-only account info, rename, change avatar,
// or change password. Each view talks to the API client only and reflects changes back
// into AuthContext so the widget updates without a reload.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, api, assetUrl, type Profile } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "./Button";
import { Field } from "./Field";
import { Icon } from "./Icons";
import "./profile-dialog.css";

export type ProfileAction = "info" | "name" | "avatar" | "password";

const TITLES: Record<ProfileAction, string> = {
  info: "Thông tin tài khoản",
  name: "Đổi tên hiển thị",
  avatar: "Đổi avatar",
  password: "Đổi mật khẩu",
};

interface ProfileDialogProps {
  action: ProfileAction | null;
  onClose: () => void;
}

export function ProfileDialog({ action, onClose }: ProfileDialogProps) {
  // Close on Escape.
  useEffect(() => {
    if (!action) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [action, onClose]);

  if (!action) return null;

  return (
    <div className="pd-overlay" onMouseDown={onClose}>
      <div
        className="pd-modal"
        role="dialog"
        aria-modal="true"
        aria-label={TITLES[action]}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="pd-modal__head">
          <h2 className="pd-modal__title">{TITLES[action]}</h2>
          <button type="button" className="pd-modal__close" aria-label="Đóng" onClick={onClose}>
            <Icon name="chevron" size={18} />
          </button>
        </header>
        <div className="pd-modal__body">
          {action === "info" && <InfoView />}
          {action === "name" && <NameView onDone={onClose} />}
          {action === "avatar" && <AvatarView onDone={onClose} />}
          {action === "password" && <PasswordView />}
        </div>
      </div>
    </div>
  );
}

// --- Thông tin tài khoản (feat-019) -----------------------------------------

function InfoView() {
  const { token } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    api
      .profile(token)
      .then((p) => !cancelled && setProfile(p))
      .catch(() => !cancelled && setError("Không tải được thông tin tài khoản."));
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (error) return <div className="banner banner--error" role="alert">{error}</div>;
  if (!profile)
    return (
      <div className="pd-loading" role="status" aria-live="polite">
        Đang tải…
      </div>
    );

  const display = profile.name?.trim() || profile.username;
  const avatarSrc = assetUrl(profile.avatar_url);
  const initials = display
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
  const created = formatDate(profile.created_at);

  return (
    <div className="pd-info">
      <div className="pd-info__hero">
        <div className="pd-avatar pd-avatar--xl">
          {avatarSrc ? <img src={avatarSrc} alt="" /> : <span>{initials}</span>}
        </div>
        <div className="pd-info__heroname">{display}</div>
      </div>
      <dl className="pd-info__grid">
        <Row label="Tên hiển thị" value={profile.name || "—"} />
        <Row label="Tên đăng nhập" value={profile.username} mono />
        <Row label="Phòng ban" value={profile.department_name ?? "Chưa gán"} />
        <Row label="Vai trò" value={profile.role_name ?? "Chưa gán"} />
        <Row label="Ngày tạo" value={created} />
      </dl>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="pd-info__row">
      <dt className="pd-info__label">{label}</dt>
      <dd className={`pd-info__value${mono ? " pd-info__value--mono" : ""}`}>{value}</dd>
    </div>
  );
}

// --- Đổi tên hiển thị (feat-020) --------------------------------------------

function NameView({ onDone }: { onDone: () => void }) {
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
    if (!trimmed) {
      setFieldError("Tên hiển thị không được để trống.");
      return; // no request on invalid input
    }
    if (trimmed.length > 100) {
      setFieldError("Tên hiển thị tối đa 100 ký tự.");
      return;
    }
    setFieldError(null);
    setSaving(true);
    try {
      const updated = await api.updateName(token!, trimmed);
      updateUser({ name: updated.name }); // widget reflects it immediately
      onDone();
    } catch (err) {
      setFormError(messageFor(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="pd-form" onSubmit={onSubmit} noValidate>
      {formError && <div className="banner banner--error" role="alert">{formError}</div>}
      <Field
        label="Tên hiển thị"
        value={name}
        error={fieldError ?? undefined}
        maxLength={120}
        autoFocus
        onChange={(e) => setName(e.target.value)}
        disabled={saving}
      />
      <div className="pd-form__actions">
        <Button type="submit" variant="accent" loading={saving}>
          Lưu
        </Button>
      </div>
    </form>
  );
}

// --- Đổi avatar (feat-021) --------------------------------------------------

const AVATAR_MAX_BYTES = 2 * 1024 * 1024;
const AVATAR_TYPES = ["image/jpeg", "image/png"];

function AvatarView({ onDone }: { onDone: () => void }) {
  const { token, user, updateUser } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Revoke the object URL when the preview changes/unmounts.
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const currentSrc = assetUrl(user?.avatar_url);
  const shownSrc = previewUrl ?? currentSrc;
  const initials = (user?.name?.trim() || user?.username || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  function pick(e: React.ChangeEvent<HTMLInputElement>) {
    setFormError(null);
    const f = e.target.files?.[0] ?? null;
    if (!f) return;
    if (!AVATAR_TYPES.includes(f.type)) {
      setFieldError("Ảnh phải là JPG hoặc PNG.");
      setFile(null);
      return;
    }
    if (f.size > AVATAR_MAX_BYTES) {
      setFieldError("Ảnh vượt quá 2 MB.");
      setFile(null);
      return;
    }
    setFieldError(null);
    setFile(f);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(f));
  }

  async function save() {
    if (!file || busy) return;
    setBusy(true);
    setFormError(null);
    try {
      const { avatar_url } = await api.uploadAvatar(token!, file);
      updateUser({ avatar_url });
      onDone();
    } catch (err) {
      setFormError(messageFor(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (busy) return;
    setBusy(true);
    setFormError(null);
    try {
      await api.removeAvatar(token!);
      updateUser({ avatar_url: null });
      onDone();
    } catch (err) {
      setFormError(messageFor(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pd-form">
      {formError && <div className="banner banner--error" role="alert">{formError}</div>}
      <div className="pd-avatar-edit">
        <div className="pd-avatar pd-avatar--xl">
          {shownSrc ? <img src={shownSrc} alt="" /> : <span>{initials}</span>}
        </div>
        <div className="pd-avatar-edit__controls">
          <input
            ref={inputRef}
            type="file"
            accept="image/jpeg,image/png"
            className="pd-visually-hidden"
            onChange={pick}
            disabled={busy}
          />
          <Button type="button" variant="ghost" onClick={() => inputRef.current?.click()} disabled={busy}>
            Chọn ảnh…
          </Button>
          <p className="pd-hint">JPG hoặc PNG, tối đa 2 MB.</p>
          {fieldError && <span className="field__error" role="alert">{fieldError}</span>}
        </div>
      </div>
      <div className="pd-form__actions pd-form__actions--split">
        {currentSrc && (
          <Button type="button" variant="ghost" onClick={remove} disabled={busy}>
            Xoá avatar
          </Button>
        )}
        <Button type="button" variant="accent" onClick={save} loading={busy} disabled={!file}>
          Lưu
        </Button>
      </div>
    </div>
  );
}

// --- Đổi mật khẩu (feat-022) ------------------------------------------------

interface PwErrors {
  current?: string;
  next?: string;
  confirm?: string;
}

function PasswordView() {
  const { token, logout, setNotice } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<PwErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function validate(): PwErrors {
    const e: PwErrors = {};
    if (!current) e.current = "Vui lòng nhập mật khẩu hiện tại.";
    if (next.length < 8) e.next = "Mật khẩu mới tối thiểu 8 ký tự.";
    else if (!/[a-zA-Z]/.test(next) || !/\d/.test(next))
      e.next = "Mật khẩu mới phải gồm cả chữ và số.";
    if (confirm !== next) e.confirm = "Xác nhận mật khẩu không khớp.";
    return e;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (saving) return;
    setFormError(null);
    const errs = validate();
    setErrors(errs);
    if (Object.keys(errs).length > 0) return; // no request on invalid input
    setSaving(true);
    try {
      await api.changePassword(token!, current, next);
      // All sessions ended server-side; bounce to Login with a success notice.
      setNotice("Đổi mật khẩu thành công. Vui lòng đăng nhập lại.");
      await logout();
    } catch (err) {
      // 400 = wrong current / same-as-old; keep the form so the user can retry.
      setFormError(messageFor(err));
      setSaving(false);
    }
  }

  return (
    <form className="pd-form" onSubmit={onSubmit} noValidate>
      {formError && <div className="banner banner--error" role="alert">{formError}</div>}
      <Field
        label="Mật khẩu hiện tại"
        type="password"
        autoComplete="current-password"
        value={current}
        error={errors.current}
        onChange={(e) => setCurrent(e.target.value)}
        disabled={saving}
      />
      <Field
        label="Mật khẩu mới"
        type="password"
        autoComplete="new-password"
        value={next}
        error={errors.next}
        onChange={(e) => setNext(e.target.value)}
        disabled={saving}
      />
      <Field
        label="Xác nhận mật khẩu mới"
        type="password"
        autoComplete="new-password"
        value={confirm}
        error={errors.confirm}
        onChange={(e) => setConfirm(e.target.value)}
        disabled={saving}
      />
      <div className="pd-form__actions">
        <Button type="submit" variant="accent" loading={saving}>
          Lưu
        </Button>
      </div>
    </form>
  );
}

// --- helpers ----------------------------------------------------------------

function messageFor(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.isNetwork) return "Mất kết nối. Vui lòng thử lại.";
    if (err.status >= 500) return "Có lỗi xảy ra, vui lòng thử lại sau.";
    return err.message; // surfaces the backend's Vietnamese detail (400/422)
  }
  return "Đã có lỗi xảy ra. Vui lòng thử lại.";
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
