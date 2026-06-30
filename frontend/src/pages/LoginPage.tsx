import { useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { Field } from "../components/Field";
import "./auth.css";

interface FieldErrors {
  username?: string;
  password?: string;
}

export function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
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
    if (submitting) return; // guard against double-submit

    setFormError(null);
    setCanRetry(false);

    const errs = validate();
    setFieldErrors(errs);
    if (Object.keys(errs).length > 0) return; // no network call on invalid input

    setSubmitting(true);
    try {
      await login(username.trim(), password);
      // On success the app swaps to the Dashboard; nothing else to do here.
    } catch (err) {
      if (err instanceof ApiError && err.isAuth) {
        setFormError("Tên đăng nhập hoặc mật khẩu không đúng");
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
      <section className="card auth__card" aria-labelledby="auth-title">
        <header className="auth__head">
          <p className="eyebrow">Sao Việt Nhật ERP</p>
          <h1 className="auth__title" id="auth-title">
            Đăng nhập
          </h1>
          <p className="auth__sub">Nhập tài khoản nội bộ để tiếp tục.</p>
        </header>

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
            label="Tên đăng nhập"
            type="text"
            name="username"
            autoComplete="username"
            placeholder="vd: admin"
            value={username}
            error={fieldErrors.username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={submitting}
          />
          <Field
            label="Mật khẩu"
            type="password"
            name="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            error={fieldErrors.password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={submitting}
          />
          <div className="auth__actions">
            <Button type="submit" variant="accent" block loading={submitting}>
              {submitting ? "Đang đăng nhập…" : "Đăng nhập"}
            </Button>
          </div>
        </form>
      </section>
    </main>
  );
}
