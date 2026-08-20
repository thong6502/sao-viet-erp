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
  | "close_book"
  // cham_cong (mg 0194) — MỘT Ô = MỘT TAB. Tên động từ gọi đúng tên tab.
  | "view_timesheet"        // tab Bảng công tháng (lưới cả xưởng + nút Chốt kỳ)
  | "approve_late_early"    // tab con Duyệt phiếu đi muộn / về sớm / nghỉ nửa buổi
  | "manage_locations"      // tab Điểm chấm công
  | "manage_shifts"         // tab Khai ca
  | "manage_calendar"       // tab Lịch & Ngày lễ
  // luong (mg 0195) — tab Bảng lương tháng, tách khỏi cột Xem.
  | "view_payroll_table"
  | "manage_salary_profiles"   // luong — tab Lương nhân viên
  | "manage_piece_rates"       // luong — tab Lương khoán
  | "manage_leave_types";      // nghi_phep — danh mục loại nghỉ

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
    // TRA THẲNG theo tên cờ, KHÔNG liệt kê từng động từ nữa (15/08/2026).
    //
    // Trước đây đây là một chuỗi `if` dài 38 dòng, mỗi động từ một dòng. Thêm ô quyền mới mà quên
    // thêm dòng ở đây thì: cột có trong DB ✓, ma trận tick được ✓, máy chủ gác đúng ✓, bộ quyền
    // gửi xuống đủ ✓ — nhưng `can()` rơi xuống `return false`, và **tab/nút không bao giờ hiện,
    // không một lời báo lỗi**. Đã cắn đúng như vậy với 5 ô mới của màn Chấm công.
    //
    // Tên động từ ↔ tên cột là quy ước bất di bất dịch của hệ (`approve` ↔ `can_approve`), nên tra
    // theo quy ước là đúng bản chất hơn chép tay 40 dòng. `PermAction` vẫn chặn gõ sai ở nơi gọi.
    const row = caps.get(moduleKey);
    if (!row) return false;
    return Boolean((row as unknown as Record<string, boolean | undefined>)[`can_${action}`]);
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
  // BỎ Ô `self_service` (chủ chốt 15/08/2026). Dữ liệu của CHÍNH MÌNH là quyền đương nhiên của mọi
  // tài khoản đăng nhập — xem công của mình, phiếu lương của mình, đơn của mình; gửi/sửa/huỷ đơn
  // của mình. Đó không phải quyền được ban: chặn nó là chặn người ta đi làm.
  //
  // Cái quyết định NHÌN THẤY MÀN NÀO vẫn là ô của chính màn đó — "phải cấp quyền mới hiển thị".
  // Giữ hàm (thay vì xoá 20 chỗ gọi) để chỗ gọi vẫn đọc được ý: đây là phần "của tôi".
  return true;
}

/** Có ô THAO TÁC của Tự phục vụ không — được GHI với hồ sơ của chính mình: chấm công, gửi · sửa ·
 *  huỷ đơn nghỉ · phiếu tăng ca · xin đi muộn · xin tạm ứng, sửa thông tin liên hệ của mình.
 *
 *  Tách khỏi `useSelfService()` ngày 11/08/2026: trước đó `self_service` chỉ dùng động từ `read`
 *  nên cột "Thao tác" của nó là ô chết — gỡ tick đi thì thợ vẫn chấm công, vẫn gửi phiếu. Chủ chốt
 *  báo đúng chỗ này ở ba màn khác nhau (Tự phục vụ · Tăng ca · Nghỉ phép), cùng một gốc. */
export function useSelfServiceWrite(): boolean {
  return true;   // xem `useSelfService` — ghi vào hồ sơ của chính mình cũng là quyền đương nhiên
}

/** Returns `can(module, action)`. Defaults to deny until the provider is mounted. */
export function useCan(): (moduleKey: string, action: PermAction) => boolean {
  return useContext(PermissionsContext).can;
}

/** Returns `scopeOf(module)` → own|department|all|null. */
export function useScopeOf(): (moduleKey: string) => Scope | null {
  return useContext(PermissionsContext).scopeOf;
}
