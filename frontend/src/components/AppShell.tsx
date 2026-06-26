// Authenticated app shell: persistent left Sidebar + the active screen.
// On entry it loads the current user's readable modules (feat-010) to gate both
// the sidebar (handled in Sidebar) and the content (a forbidden module → 403).
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { DashboardPage } from "../pages/DashboardPage";
import { DepartmentsPage } from "../pages/DepartmentsPage";
import { RolesPage } from "../pages/RolesPage";
import { UsersPage } from "../pages/UsersPage";
import { MODULE_BY_NAV_ID, Sidebar } from "./Sidebar";

export function AppShell() {
  const { token } = useAuth();
  const [activeId, setActiveId] = useState("dashboard");
  const [readable, setReadable] = useState<Set<string> | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    api
      .myPermissions(token)
      .then((mods) => !cancelled && setReadable(new Set(mods)))
      .catch(() => !cancelled && setReadable(new Set()));
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (readable === null) {
    return (
      <div className="shell__center" role="status" aria-live="polite">
        Đang tải…
      </div>
    );
  }

  const moduleKey = MODULE_BY_NAV_ID[activeId];
  const allowed = moduleKey != null && readable.has(moduleKey);

  function renderContent() {
    if (!allowed) {
      return (
        <main className="shell__forbidden">
          <div className="banner banner--error" role="alert">
            <span>Bạn không có quyền truy cập mục này (403).</span>
            <button
              type="button"
              className="btn btn--ghost"
              style={{ padding: "2px 10px" }}
              onClick={() => setActiveId("dashboard")}
            >
              Về Dashboard
            </button>
          </div>
        </main>
      );
    }
    switch (activeId) {
      case "vai-tro":
        return <RolesPage />;
      case "phong-ban":
        return <DepartmentsPage />;
      case "nguoi-dung":
        return <UsersPage />;
      default:
        return <DashboardPage />;
    }
  }

  return (
    <div className="shell">
      <Sidebar activeId={activeId} onSelect={setActiveId} readable={readable} />
      <div className="shell__main">{renderContent()}</div>
    </div>
  );
}
