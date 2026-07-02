// Permission matrix — modules × (Xem/Thêm/Sửa/Xóa) + Phạm vi. Presentational + controlled:
// the parent owns the rows and gets toggle/scope callbacks. Shared by the Roles screen and
// the per-department "add role" popup so both edit permissions identically.
import type { ModuleDef, PermissionRow, Scope } from "../api/client";
import "./permission-matrix.css";

export const ACTIONS = [
  { key: "can_read", label: "Xem" },
  { key: "can_create", label: "Thêm" },
  { key: "can_update", label: "Sửa" },
  { key: "can_delete", label: "Xóa" },
] as const;

export type ActionKey = (typeof ACTIONS)[number]["key"];

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
  return (
    <table className="matrix">
      <thead>
        <tr>
          <th className="matrix__mod">Module</th>
          {ACTIONS.map((a) => (
            <th key={a.key} className="matrix__act">
              {a.label}
            </th>
          ))}
          <th className="matrix__scope">Phạm vi</th>
        </tr>
      </thead>
      <tbody>
        {matrix.map((row) => {
          const label = moduleLabel.get(row.module_key) ?? row.module_key;
          return (
            <tr key={row.module_key}>
              <td className="matrix__mod">{label}</td>
              {ACTIONS.map((a) => (
                <td key={a.key} className="matrix__act">
                  <input
                    type="checkbox"
                    className="switch"
                    checked={row[a.key]}
                    disabled={readOnly}
                    aria-label={`${a.label} — ${label}`}
                    onChange={(e) => onToggle(row.module_key, a.key, e.target.checked)}
                  />
                </td>
              ))}
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
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
