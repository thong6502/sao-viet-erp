// Permission context (spec-09): exposes `can(module, action)` so any screen can hide/disable
// write actions the current user's role doesn't grant. Backend remains the real gate (403);
// this only improves UX. AppShell loads the matrix once and provides it here.
import { createContext, useContext, type ReactNode } from "react";
import type { ModuleCapability } from "../api/client";

export type PermAction = "read" | "create" | "update" | "delete";

export type Capabilities = Map<string, ModuleCapability>;

interface PermissionsCtx {
  can: (moduleKey: string, action: PermAction) => boolean;
}

const PermissionsContext = createContext<PermissionsCtx>({ can: () => false });

export function buildCapabilities(rows: ModuleCapability[]): Capabilities {
  return new Map(rows.map((r) => [r.module_key, r]));
}

export function PermissionsProvider({
  caps,
  children,
}: {
  caps: Capabilities;
  children: ReactNode;
}) {
  function can(moduleKey: string, action: PermAction): boolean {
    const row = caps.get(moduleKey);
    if (!row) return false;
    if (action === "read") return row.can_read;
    if (action === "create") return row.can_create;
    if (action === "update") return row.can_update;
    return row.can_delete;
  }
  return <PermissionsContext.Provider value={{ can }}>{children}</PermissionsContext.Provider>;
}

/** Returns `can(module, action)`. Defaults to deny until the provider is mounted. */
export function useCan(): (moduleKey: string, action: PermAction) => boolean {
  return useContext(PermissionsContext).can;
}
