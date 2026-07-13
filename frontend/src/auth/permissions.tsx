// Permission context (spec-09): exposes `can(module, action)` so any screen can hide/disable
// write actions the current user's role doesn't grant. Backend remains the real gate (403);
// this only improves UX. AppShell loads the matrix once and provides it here.
import { createContext, useContext, type ReactNode } from "react";
import type { ModuleCapability, Scope } from "../api/client";

export type PermAction =
  | "read"
  | "create"
  | "update"
  | "delete"
  // Quyền chi tiết (Cách B).
  | "reassign"
  | "export"
  | "view_debt"
  | "view_discount"
  | "approve"
  | "manage_status"
  | "reset_password"
  | "lock"
  | "revoke_sessions"
  | "assign_role"
  | "transfer"
  | "set_head"
  | "requote"
  | "manage_price"
  | "cancel"
  | "manage_permissions"
  | "clone"
  | "toggle_active"
  | "reparent"
  | "view_salary"
  | "adjust"
  | "approve_exception";

export type Capabilities = Map<string, ModuleCapability>;

interface PermissionsCtx {
  can: (moduleKey: string, action: PermAction) => boolean;
  /** The caller's data scope on a module (own|department|all), or null if no permission. */
  scopeOf: (moduleKey: string) => Scope | null;
}

const PermissionsContext = createContext<PermissionsCtx>({
  can: () => false,
  scopeOf: () => null,
});

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
    if (action === "delete") return row.can_delete;
    if (action === "reassign") return row.can_reassign;
    if (action === "export") return row.can_export;
    if (action === "view_debt") return row.can_view_debt;
    if (action === "view_discount") return row.can_view_discount;
    if (action === "approve") return row.can_approve;
    if (action === "manage_status") return row.can_manage_status;
    if (action === "reset_password") return row.can_reset_password;
    if (action === "lock") return row.can_lock;
    if (action === "revoke_sessions") return row.can_revoke_sessions;
    if (action === "assign_role") return row.can_assign_role;
    if (action === "transfer") return row.can_transfer;
    if (action === "set_head") return row.can_set_head;
    if (action === "requote") return row.can_requote;
    if (action === "manage_price") return row.can_manage_price;
    if (action === "cancel") return row.can_cancel;
    if (action === "manage_permissions") return row.can_manage_permissions;
    if (action === "clone") return row.can_clone;
    if (action === "toggle_active") return row.can_toggle_active;
    if (action === "reparent") return row.can_reparent;
    if (action === "view_salary") return row.can_view_salary;
    if (action === "adjust") return row.can_adjust;
    if (action === "approve_exception") return row.can_approve_exception;
    return false;
  }
  function scopeOf(moduleKey: string): Scope | null {
    return caps.get(moduleKey)?.scope ?? null;
  }
  return (
    <PermissionsContext.Provider value={{ can, scopeOf }}>{children}</PermissionsContext.Provider>
  );
}

/** Returns `can(module, action)`. Defaults to deny until the provider is mounted. */
export function useCan(): (moduleKey: string, action: PermAction) => boolean {
  return useContext(PermissionsContext).can;
}

/** Returns `scopeOf(module)` → own|department|all|null. */
export function useScopeOf(): (moduleKey: string) => Scope | null {
  return useContext(PermissionsContext).scopeOf;
}
