import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./auth.css";

export function DashboardPage() {
  const { user, logout } = useAuth();

  return (
    <main className="dash">
      <div className="dash__bar">
        <div className="dash__who">
          <p className="eyebrow">Signed in</p>
          <span className="dash__email">{user?.email}</span>
        </div>
        <Button variant="ghost" onClick={logout}>
          Log out
        </Button>
      </div>

      <section className="card">
        <p className="eyebrow">Dashboard</p>
        <h1 className="auth__title" style={{ marginTop: "var(--sp-2)" }}>
          Welcome{user?.name ? `, ${user.name}` : ""}.
        </h1>
        <p className="auth__sub">
          You are authenticated. This protected page is only reachable with a valid token —
          the first feature beyond auth will land here next spec.
        </p>
      </section>
    </main>
  );
}
