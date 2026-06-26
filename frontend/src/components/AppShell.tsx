// Authenticated app shell: persistent left Sidebar + scrollable content.
// The active nav id lives here so content can react to it as real routes land;
// for now the sidebar selection is visual and `children` is the page body.
import { useState, type ReactNode } from "react";
import { Sidebar } from "./Sidebar";

export function AppShell({ children }: { children: ReactNode }) {
  const [activeId, setActiveId] = useState("dashboard");

  return (
    <div className="shell">
      <Sidebar activeId={activeId} onSelect={setActiveId} />
      <div className="shell__main">{children}</div>
    </div>
  );
}
