// Hằng số dùng chung của màn Phòng ban (tách từ pages/DepartmentsPage.tsx).
import type { ActionKey } from "../../../../components/PermissionMatrix";

export const READ_IMPLYING_ACTIONS: ActionKey[] = [
  "can_create",
  "can_update",
  "can_delete",
  "can_reassign",
  "can_export",
  "can_view_debt",
  "can_view_discount",
  "can_approve",
  "can_manage_status",
  "can_reset_password",
  "can_lock",
  "can_revoke_sessions",
  "can_assign_role",
  "can_transfer",
  "can_set_head",
  "can_requote",
  "can_manage_price",
  "can_cancel",
  "can_manage_permissions",
  "can_clone",
  "can_toggle_active",
  "can_reparent",
  "can_view_salary",
  "can_edit_salary",
  "can_adjust",
  "can_approve_exception",
  "can_set_credit_terms",
  "can_record_deposit",
  "can_assign_work",
  "can_record_output",
  "can_handover",
  "can_request",
  "can_view_stock",
  "can_view_cost",
  "can_set_threshold",
  "can_post",
];

/** Đã kéo sơ đồ cây ít nhất 1 lần → không nhắc "kéo để di chuyển" nữa. */
export const PAN_HINT_KEY = "rdx-org-pan-hint";
