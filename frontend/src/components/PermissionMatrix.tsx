// Permission matrix — modules × (Xem/Thêm/Sửa/Xóa) + Phạm vi. Presentational + controlled:
// the parent owns the rows and gets toggle/scope callbacks. Shared by the Roles screen and
// the per-department "add role" popup so both edit permissions identically.
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ModuleDef, PermissionRow, Scope } from "../api/client";
import "./permission-matrix.css";

export const ACTIONS = [
  { key: "can_read", label: "Xem" },
  { key: "can_create", label: "Thêm" },
  { key: "can_update", label: "Sửa" },
  { key: "can_delete", label: "Xóa" },
] as const;

export type ActionKey =
  | "can_read"
  | "can_create"
  | "can_update"
  | "can_delete"
  // Quyền chi tiết (Cách B).
  | "can_reassign"
  | "can_export"
  | "can_view_debt"
  | "can_view_discount"
  | "can_approve"
  | "can_manage_status"
  | "can_reset_password"
  | "can_lock"
  | "can_revoke_sessions"
  | "can_assign_role"
  | "can_transfer"
  | "can_set_head"
  | "can_requote"
  | "can_manage_price"
  | "can_cancel"
  | "can_manage_permissions"
  | "can_clone"
  | "can_toggle_active"
  | "can_reparent"
  | "can_view_salary"
  | "can_adjust";

// UI gộp Thêm/Sửa/Xóa thành một công tắc "quyền chỉnh sửa": tick là bật cả ba.
// Dữ liệu vẫn lưu tách (can_create/can_update/can_delete) nên backend không đổi.
const WRITE_ACTIONS: ActionKey[] = ["can_create", "can_update", "can_delete"];

// Quyền CHI TIẾT khai báo theo từng module (Cách B). Module không có tên ở đây → không hiện
// cột chi tiết. Thêm module/hành động mới chỉ cần bổ sung vào bảng này + cột ở backend.
const FINE_ACTIONS: Record<string, { key: ActionKey; label: string }[]> = {
  khach_hang: [
    { key: "can_reassign", label: "Điều chuyển" },
    { key: "can_export", label: "Xuất file" },
    { key: "can_view_debt", label: "Xem công nợ" },
    { key: "can_view_discount", label: "Xem/sửa chiết khấu riêng" },
  ],
  bao_gia: [
    { key: "can_manage_status", label: "Thao tác trạng thái (gửi/từ chối/hết hạn)" },
    { key: "can_approve", label: "Duyệt báo giá" },
    { key: "can_cancel", label: "Hủy báo giá" },
    { key: "can_export", label: "Xuất PDF" },
    { key: "can_requote", label: "Tạo bản mới (Re-quote)" },
  ],
  don_hang_ban: [
    { key: "can_approve", label: "Chốt đơn" },
    { key: "can_cancel", label: "Hủy đơn" },
    { key: "can_manage_status", label: "Đổi trạng thái khác" },
  ],
  vai_tro: [{ key: "can_manage_permissions", label: "Sửa ma trận phân quyền" }],
  nguoi_dung: [
    { key: "can_reset_password", label: "Đặt lại mật khẩu" },
    { key: "can_lock", label: "Khóa / Mở tài khoản" },
    { key: "can_revoke_sessions", label: "Thu hồi phiên" },
    { key: "can_assign_role", label: "Gán vai trò" },
    { key: "can_transfer", label: "Chuyển phòng ban" },
  ],
  phong_ban: [
    { key: "can_set_head", label: "Đặt trưởng phòng" },
    { key: "can_reparent", label: "Đổi cấp trên (cây tổ chức)" },
  ],
  dm_giay_vat_tu: [
    { key: "can_manage_price", label: "Cập nhật bảng giá" },
    { key: "can_clone", label: "Nhân bản" },
    { key: "can_toggle_active", label: "Bật/tắt hoạt động" },
  ],
  dm_thiet_bi: [{ key: "can_manage_price", label: "Cập nhật đơn giá" }],
  dm_cong_doan: [{ key: "can_manage_price", label: "Cập nhật đơn giá" }],
  nhan_su: [
    { key: "can_view_salary", label: "Xem lương & BHXH (dữ liệu nhạy cảm)" },
    { key: "can_manage_status", label: "Thao tác vòng đời (chính thức/nghỉ/đình chỉ)" },
    { key: "can_transfer", label: "Điều chuyển & nâng bậc" },
    { key: "can_approve", label: "Duyệt yêu cầu cập nhật" },
    { key: "can_export", label: "Xuất Excel danh sách" },
    { key: "can_adjust", label: "Chấm công: chấm bù / sửa công" },
  ],
  luong: [
    { key: "can_approve", label: "Duyệt tạm ứng" },
    { key: "can_lock", label: "Chốt kỳ lương" },
    { key: "can_export", label: "Xuất bảng lương / file chuyển khoản" },
  ],
  ke_toan: [
    { key: "can_approve", label: "Duyệt PMH & lập Phiếu chi/UNC" },
    { key: "can_manage_status", label: "Xác nhận đã chi" },
    { key: "can_cancel", label: "Hủy chứng từ chờ chi" },
    { key: "can_export", label: "In / xuất chứng từ" },
  ],
  kho: [
    { key: "can_approve", label: "Duyệt & ghi sổ phiếu" },
    { key: "can_manage_price", label: "Xem giá vốn / giá trị tồn" },
  ],
  san_xuat: [
    { key: "can_approve", label: "Duyệt lệnh sản xuất" },
  ],
};

export const SCOPES: { value: Scope; label: string }[] = [
  { value: "own", label: "Của tôi" },
  { value: "department", label: "Cả phòng" },
  { value: "all", label: "Tất cả" },
];

/** A fresh all-off matrix (scope "own") for every module — used when creating a new role. */
export function defaultMatrix(modules: ModuleDef[]): PermissionRow[] {
  return modules.map((m) => ({
    module_key: m.key,
    can_read: false,
    can_create: false,
    can_update: false,
    can_delete: false,
    scope: "own",
    can_reassign: false,
    can_export: false,
    can_view_debt: false,
    can_view_discount: false,
    can_approve: false,
    can_manage_status: false,
    can_reset_password: false,
    can_lock: false,
    can_revoke_sessions: false,
    can_assign_role: false,
    can_transfer: false,
    can_set_head: false,
    can_requote: false,
    can_manage_price: false,
    can_cancel: false,
    can_manage_permissions: false,
    can_clone: false,
    can_toggle_active: false,
    can_reparent: false,
    can_view_salary: false,
    can_adjust: false,
  }));
}

interface PermissionMatrixProps {
  modules: ModuleDef[];
  matrix: PermissionRow[];
  onToggle: (moduleKey: string, action: ActionKey, value: boolean) => void;
  onScope: (moduleKey: string, scope: Scope) => void;
  /** Chế độ chỉ xem: mọi công tắc + phạm vi bị khóa (người dùng thiếu quyền sửa vai trò). */
  readOnly?: boolean;
}

export function PermissionMatrix({
  modules,
  matrix,
  onToggle,
  onScope,
  readOnly = false,
}: PermissionMatrixProps) {
  const moduleLabel = new Map(modules.map((m) => [m.key, m.label]));
  // Cột "Quyền chi tiết" mở dạng POPOVER nổi (portal) — không đẩy hàng xuống. Chỉ 1 cái mở
  // một lúc; lưu module + vị trí nút để đặt popover.
  const [fineMenu, setFineMenu] = useState<{ module: string; rect: DOMRect } | null>(null);
  const openFineFor = (moduleKey: string, el: HTMLElement) =>
    setFineMenu((cur) =>
      cur?.module === moduleKey ? null : { module: moduleKey, rect: el.getBoundingClientRect() },
    );
  const fineRow = fineMenu ? matrix.find((r) => r.module_key === fineMenu.module) : undefined;
  return (
    <>
    <table className="matrix">
      <thead>
        <tr>
          <th className="matrix__mod">Module</th>
          <th className="matrix__act">Xem</th>
          <th className="matrix__act">Thêm / Sửa / Xóa</th>
          <th className="matrix__scope">Phạm vi</th>
          <th className="matrix__fine">Quyền chi tiết</th>
        </tr>
      </thead>
      <tbody>
        {matrix.map((row) => {
          const label = moduleLabel.get(row.module_key) ?? row.module_key;
          // Công tắc gộp: bật khi cả ba quyền cùng bật; tick/bỏ tick áp cho cả ba.
          const canWrite = WRITE_ACTIONS.every((k) => row[k]);
          const fineActs = FINE_ACTIONS[row.module_key];
          const fineGranted = fineActs ? fineActs.filter((a) => row[a.key]).length : 0;
          const fineOpen = fineMenu?.module === row.module_key;
          return (
            <tr key={row.module_key}>
              <td className="matrix__mod">{label}</td>
              <td className="matrix__act">
                <input
                  type="checkbox"
                  className="switch"
                  checked={row.can_read}
                  disabled={readOnly}
                  aria-label={`Xem — ${label}`}
                  onChange={(e) => onToggle(row.module_key, "can_read", e.target.checked)}
                />
              </td>
              <td className="matrix__act">
                <input
                  type="checkbox"
                  className="switch"
                  checked={canWrite}
                  disabled={readOnly}
                  aria-label={`Thêm, sửa, xóa — ${label}`}
                  onChange={(e) =>
                    WRITE_ACTIONS.forEach((k) => onToggle(row.module_key, k, e.target.checked))
                  }
                />
              </td>
              <td className="matrix__scope">
                <select
                  className="input input--sm"
                  value={row.scope}
                  disabled={readOnly}
                  aria-label={`Phạm vi — ${label}`}
                  onChange={(e) => onScope(row.module_key, e.target.value as Scope)}
                >
                  {SCOPES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </td>
              <td className="matrix__fine">
                {fineActs ? (
                  <button
                    type="button"
                    className={`matrix__fine-toggle${fineOpen ? " is-open" : ""}`}
                    aria-expanded={fineOpen}
                    onClick={(e) => openFineFor(row.module_key, e.currentTarget)}
                  >
                    <span>Quyền chi tiết</span>
                    <span className={`matrix__fine-badge${fineGranted > 0 ? " is-on" : ""}`}>
                      {fineGranted}/{fineActs.length}
                    </span>
                    <span className="matrix__fine-caret">▾</span>
                  </button>
                ) : (
                  <span className="matrix__fine-none">—</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
    {fineMenu && fineRow && (
      <FinePopover
        rect={fineMenu.rect}
        row={fineRow}
        acts={FINE_ACTIONS[fineMenu.module]}
        label={moduleLabel.get(fineMenu.module) ?? fineMenu.module}
        readOnly={readOnly}
        onToggle={onToggle}
        onClose={() => setFineMenu(null)}
      />
    )}
    </>
  );
}

/** Popover nổi (portal) chứa các công tắc quyền chi tiết — không đẩy layout bảng. */
function FinePopover({
  rect,
  row,
  acts,
  label,
  readOnly,
  onToggle,
  onClose,
}: {
  rect: DOMRect;
  row: PermissionRow;
  acts: { key: ActionKey; label: string }[];
  label: string;
  readOnly: boolean;
  onToggle: (moduleKey: string, action: ActionKey, value: boolean) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    // Vị trí neo theo nút lúc mở → cuộn/resize thì đóng cho khỏi lệch.
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onClose, true);
    window.addEventListener("resize", onClose);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onClose, true);
      window.removeEventListener("resize", onClose);
    };
  }, [onClose]);

  const WIDTH = 190;
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - WIDTH - 8));
  const top = rect.bottom + 6;

  return createPortal(
    <div
      ref={ref}
      className="matrix__fine-popover"
      role="dialog"
      aria-label={`Quyền chi tiết — ${label}`}
      style={{ top, left, width: WIDTH }}
    >
      {acts.map((a) => (
        <label key={a.key} className="matrix__fine-item">
          <input
            type="checkbox"
            className="switch"
            checked={!!row[a.key]}
            disabled={readOnly}
            aria-label={`${a.label} — ${label}`}
            onChange={(e) => onToggle(row.module_key, a.key, e.target.checked)}
          />
          <span>{a.label}</span>
        </label>
      ))}
    </div>,
    document.body,
  );
}
