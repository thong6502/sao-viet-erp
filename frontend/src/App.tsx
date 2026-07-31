import { useAuth } from "./auth/useAuth";
import { AppShell } from "./components/AppShell";
import { LoginPage } from "./pages/LoginPage";
import logoUrl from "./assets/sao-viet-nhat-logo-mark.png";
import "./pages/auth.css";

// Route by auth state (no router lib needed for the auth gate this spec):
//   loading  -> restoring session via /me
//   authed   -> protected Dashboard
//   anonymous-> Login
export function App() {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <div className="screen-center" role="status" aria-live="polite">
        <div className="splash-card">
          <div className="splash-logo-wrap">
            <div className="splash-glow" />
            <div className="splash-spinner-ring" />
            <div className="splash-logo">
              <img src={logoUrl} alt="Sao Việt Nhật Logo" className="splash-logo-img" />
            </div>
          </div>
          <div className="splash-content">
            <h2 className="splash-title">
              Đang khôi phục phiên làm việc
              <span className="splash-dots">
                <span />
                <span />
                <span />
              </span>
            </h2>
            <p className="splash-sub">Sao Việt Nhật ERP — Hệ thống quản trị sản xuất in</p>
          </div>
        </div>
      </div>
    );
  }

  return status === "authenticated" ? <AppShell /> : <LoginPage />;
}
