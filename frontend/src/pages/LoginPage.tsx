import { useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { Field } from "../components/Field";
import "./auth.css";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface FieldErrors {
  email?: string;
  password?: string;
}

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  function validate(): FieldErrors {
    const errs: FieldErrors = {};
    if (!email.trim()) errs.email = "Email is required.";
    else if (!EMAIL_RE.test(email.trim())) errs.email = "Enter a valid email address.";
    if (!password) errs.password = "Password is required.";
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
      await login(email.trim(), password);
      // On success the app swaps to the Dashboard; nothing else to do here.
    } catch (err) {
      if (err instanceof ApiError && err.isAuth) {
        setFormError("Invalid email or password");
        setPassword("");
      } else if (err instanceof ApiError && err.isNetwork) {
        setFormError(err.message);
        setCanRetry(true);
      } else {
        setFormError("Something went wrong. Please try again.");
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
          <p className="eyebrow">GAN App</p>
          <h1 className="auth__title" id="auth-title">
            Sign in
          </h1>
          <p className="auth__sub">Enter your credentials to continue.</p>
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
                Retry
              </button>
            )}
          </div>
        )}

        <form className="auth__form" onSubmit={onSubmit} noValidate>
          <Field
            label="Email"
            type="email"
            name="email"
            autoComplete="username"
            placeholder="you@example.com"
            value={email}
            error={fieldErrors.email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={submitting}
          />
          <Field
            label="Password"
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
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
          </div>
        </form>
      </section>
    </main>
  );
}
