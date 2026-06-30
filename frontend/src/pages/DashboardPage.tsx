import { useAuth } from "../auth/useAuth";
import "./auth.css";

export function DashboardPage() {
  const { user } = useAuth();

  return (
    <main className="dash">
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
