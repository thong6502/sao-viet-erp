// Authenticated app shell: persistent left Sidebar + the active screen.
// The active nav id selects the content; unbuilt modules fall back to the
// Dashboard until their feature lands.
import { useState } from "react";
import { DashboardPage } from "../pages/DashboardPage";
import { RolesPage } from "../pages/RolesPage";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  const [activeId, setActiveId] = useState("dashboard");

  return (
    <div className="shell">
      <Sidebar activeId={activeId} onSelect={setActiveId} />
      <div className="shell__main">
        {activeId === "vai-tro" ? <RolesPage /> : <DashboardPage />}
      </div>
    </div>
  );
}
