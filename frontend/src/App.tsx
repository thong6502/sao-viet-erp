import { useAuth } from "./auth/useAuth";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";

// Route by auth state (no router lib needed for the auth gate this sprint):
//   loading  -> restoring session via /me
//   authed   -> protected Dashboard
//   anonymous-> Login
export function App() {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <div className="screen-center" role="status" aria-live="polite">
        Restoring session…
      </div>
    );
  }

  return status === "authenticated" ? <DashboardPage /> : <LoginPage />;
}
