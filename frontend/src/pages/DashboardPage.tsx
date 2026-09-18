import { useAuth } from "../auth/useAuth";
import "./auth.css";

export function DashboardPage() {
  const { user } = useAuth();

  return (
    <main className="dash">
      <section className="card">
        <p className="eyebrow">Trang chủ</p>
        <h1 className="auth__title" style={{ marginTop: "var(--sp-2)" }}>
          Xin chào{user?.name ? `, ${user.name}` : ""}.
        </h1>
        <p className="auth__sub">Chọn một mục ở thanh bên trái để bắt đầu làm việc.</p>
      </section>
    </main>
  );
}
