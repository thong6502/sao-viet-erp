// Authenticated app shell: persistent left Sidebar + the active screen.
// The active nav id selects the content; unbuilt modules fall back to the
// Dashboard until their feature lands.
import { useState } from "react";
import { DashboardPage } from "../pages/DashboardPage";
import { DepartmentsPage } from "../pages/DepartmentsPage";
import { RolesPage } from "../pages/RolesPage";
import { UsersPage } from "../pages/UsersPage";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  const [activeId, setActiveId] = useState("dashboard");

  function renderContent() {
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
      <Sidebar activeId={activeId} onSelect={setActiveId} />
      <div className="shell__main">{renderContent()}</div>
    </div>
  );
}
