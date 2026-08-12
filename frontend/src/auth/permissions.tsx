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
  | "edit_salary"
  | "adjust"
  | "approve_exception"
  | "set_credit_terms"
  | "record_deposit"
  // Kho (spec-kho-de-nghi §9.1) — quyền chi tiết của module `kho` + ghi sổ (SoD).
  | "request"
  | "view_stock"
  | "view_cost"
  // cham_cong: xem tab "Nhật ký chấm công" (tách khỏi "read" 11/08/2026).
  | "view_log"
  | "set_threshold"
  | "post"
  // Kho — kế toán: khóa kỳ (chốt sổ) + xem Báo cáo kho + export MISA.
  | "close_book";

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
    if (action === "edit_salary") return row.can_edit_salary;
    if (action === "adjust") return row.can_adjust;
    if (action === "approve_exception") return row.can_approve_exception;
    if (action === "set_credit_terms") return row.can_set_credit_terms;
    if (action === "record_deposit") return row.can_record_deposit;
    if (action === "request") return row.can_request;
    if (action === "view_stock") return row.can_view_stock;
    if (action === "view_cost") return row.can_view_cost;
    if (action === "view_log") return row.can_view_log;
    if (action === "set_threshold") return row.can_set_threshold;
    if (action === "post") return row.can_post;
    if (action === "close_book") return row.can_close_book;
    return false;
  }
  function scopeOf(moduleKey: string): Scope | null {
    return caps.get(moduleKey)?.scope ?? null;
  }
  return (
    <PermissionsContext.Provider value={{ can, scopeOf }}>{children}</PermissionsContext.Provider>
  );
}

/** Có ô TỰ PHỤC VỤ hay không — việc người lao động làm với hồ sơ của CHÍNH MÌNH: tự chấm công,
 *  xem công / phiếu lương của mình, tự gửi đơn nghỉ · phiếu tăng ca · xin tạm ứng.
 *
 *  Từ 10/08/2026 đây là ô quyền THẬT (`self_service`), bật sẵn cho mọi vai mới nhưng quản trị tắt
 *  được. Màn nào có nút tự phục vụ thì phải hỏi hàm này — không thì tắt ô xong nút vẫn bày ra, bấm
 *  mới ăn 403 (đợt 5). */
export function useSelfService(): boolean {
  return useCan()("self_service", "read");
}

/** Có ô THAO TÁC của Tự phục vụ không — được GHI với hồ sơ của chính mình: chấm công, gửi · sửa ·
 *  huỷ đơn nghỉ · phiếu tăng ca · xin đi muộn · xin tạm ứng, sửa thông tin liên hệ của mình.
 *
 *  Tách khỏi `useSelfService()` ngày 11/08/2026: trước đó `self_service` chỉ dùng động từ `read`
 *  nên cột "Thao tác" của nó là ô chết — gỡ tick đi thì thợ vẫn chấm công, vẫn gửi phiếu. Chủ chốt
 *  báo đúng chỗ này ở ba màn khác nhau (Tự phục vụ · Tăng ca · Nghỉ phép), cùng một gốc. */
export function useSelfServiceWrite(): boolean {
  return useCan()("self_service", "create");
}

/** Returns `can(module, action)`. Defaults to deny until the provider is mounted. */
export function useCan(): (moduleKey: string, action: PermAction) => boolean {
  return useContext(PermissionsContext).can;
}

/** Returns `scopeOf(module)` → own|department|all|null. */
export function useScopeOf(): (moduleKey: string) => Scope | null {
  return useContext(PermissionsContext).scopeOf;
}
