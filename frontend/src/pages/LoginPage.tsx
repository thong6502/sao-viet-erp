import { useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import logoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import { Button } from "../components/Button";
import { Field } from "../components/Field";
import { Icon } from "../components/Icons";
import "./auth.css";

interface FieldErrors {
  username?: string;
  password?: string;
}

export function LoginPage() {
  const { login, notice, setNotice } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [showForgotModal, setShowForgotModal] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  function validate(): FieldErrors {
    const errs: FieldErrors = {};
    if (!username.trim()) errs.username = "Vui lòng nhập tên đăng nhập.";
    if (!password) errs.password = "Vui lòng nhập mật khẩu.";
    return errs;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (submitting) return;

    setFormError(null);
    setCanRetry(false);
    setNotice(null);

    const errs = validate();
    setFieldErrors(errs);
    if (Object.keys(errs).length > 0) return;

    setSubmitting(true);
    try {
      await login(username.trim(), password);
    } catch (err) {
      if (err instanceof ApiError && err.isAuth) {
        setFormError("Tên đăng nhập hoặc mật khẩu không đúng.");
        setPassword("");
      } else if (err instanceof ApiError && err.isNetwork) {
        setFormError(err.message);
        setCanRetry(true);
      } else {
        setFormError("Đã có lỗi xảy ra. Vui lòng thử lại.");
        setCanRetry(true);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth">
      {/* Subtle ambient light glows */}
      <div className="auth__ambient-glow auth__ambient-glow--1" aria-hidden="true" />
      <div className="auth__ambient-glow auth__ambient-glow--2" aria-hidden="true" />
      <div className="auth__grid-overlay" aria-hidden="true" />

      <section className={`auth__card${formError ? " is-error" : ""}`} aria-labelledby="auth-title">
        <div className="auth__card-body">
          <header className="auth__head auth__head--centered">
            <div className="auth__brand-logo-wrap">
              <img src={logoUrl} alt="Logo Sao Việt Nhật" className="auth__brand-logo" />
            </div>
            <span className="auth__brand-name">SAO VIỆT NHẬT ERP</span>
            <h1 className="auth__title" id="auth-title">
              Đăng nhập
            </h1>
          </header>

          {notice && !formError && (
            <div className="banner banner--success" role="status">
              <span>{notice}</span>
            </div>
          )}

          {formError && (
            <div className="banner banner--error" role="alert">
              <span>{formError}</span>
              {canRetry && (
                <button
                  type="button"
                  className="btn btn--ghost"
                  style={{ padding: "2px 10px" }}
                  onClick={() => void onSubmit(new Event("submit") as unknown as FormEvent)}
                >
                  Thử lại
                </button>
              )}
            </div>
          )}

          <form className="auth__form" onSubmit={onSubmit} noValidate>
            <Field
              label="TÊN ĐĂNG NHẬP"
              type="text"
              name="username"
              icon="users"
              autoComplete="username"
              placeholder="vd: admin"
              value={username}
              error={fieldErrors.username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={submitting}
            />

            <Field
              label="MẬT KHẨU"
              type={showPassword ? "text" : "password"}
              name="password"
              icon="lock"
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              error={fieldErrors.password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              endAction={
                <button
                  type="button"
                  className="auth__toggle-pw"
                  onClick={() => setShowPassword(!showPassword)}
                  tabIndex={-1}
                  aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  title={showPassword ? "Ẩn mật khẩu" : "Hiển thị mật khẩu"}
                >
                  <Icon name={showPassword ? "eye" : "lock"} size={15} />
                </button>
              }
            />

            <div className="auth__options">
              <label className="auth__remember">
                <input
                  type="checkbox"
                  className="auth__checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                />
                <span>Ghi nhớ đăng nhập</span>
              </label>
              <button
                type="button"
                className="auth__forgot-btn"
                onClick={() => setShowForgotModal(true)}
              >
                Quên mật khẩu?
              </button>
            </div>

            <div className="auth__actions">
              <Button type="submit" variant="accent" block loading={submitting}>
                {submitting ? "Đang xác thực…" : (
                  <span className="auth__btn-label">
                    Đăng nhập hệ thống <Icon name="arrowRight" size={16} />
                  </span>
                )}
              </Button>
            </div>
          </form>
        </div>
      </section>

      {/* Modern Custom Modal Dialog for Forgot Password */}
      {showForgotModal && (
        <div className="auth__modal-backdrop" onClick={() => setShowForgotModal(false)} role="presentation">
          <div
            className="auth__modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="forgot-title"
          >
            <div className="auth__modal-icon">
              <Icon name="help" size={24} />
            </div>
            <h3 className="auth__modal-title" id="forgot-title">
              Cấp lại mật khẩu
            </h3>
            <p className="auth__modal-body">
              Hệ thống quản trị ERP không hỗ trợ tự đặt lại mật khẩu trực tuyến vì lý do bảo mật doanh nghiệp.
            </p>
            <p className="auth__modal-sub">
              Vui lòng liên hệ <strong>Quản trị viên phòng IT</strong> hoặc <strong>Ban Giám Đốc</strong> để được cấp lại mật khẩu truy cập mới.
            </p>
            <div className="auth__modal-actions">
              <Button
                type="button"
                variant="accent"
                block
                onClick={() => setShowForgotModal(false)}
              >
                Đã hiểu
              </Button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}



