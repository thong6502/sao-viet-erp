import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type Department,
  type ModuleDef,
  type PermissionRow,
  type Role,
  type Scope,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./roles.css";

const ACTIONS = [
  { key: "can_read", label: "Xem" },
  { key: "can_create", label: "Thêm" },
  { key: "can_update", label: "Sửa" },
  { key: "can_delete", label: "Xóa" },
] as const;

type ActionKey = (typeof ACTIONS)[number]["key"];

const SCOPES: { value: Scope; label: string }[] = [
  { value: "own", label: "Của tôi" },
  { value: "department", label: "Cả phòng" },
  { value: "all", label: "Tất cả" },
];

export function RolesPage() {
  const { token } = useAuth();

  const [modules, setModules] = useState<ModuleDef[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [deptId, setDeptId] = useState<number | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleId, setRoleId] = useState<number | null>(null);
  const [matrix, setMatrix] = useState<PermissionRow[]>([]);

  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [matrixLoading, setMatrixLoading] = useState(false);

  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [newName, setNewName] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const moduleLabel = useMemo(
    () => new Map(modules.map((m) => [m.key, m.label])),
    [modules],
  );
  const currentRole = roles.find((r) => r.id === roleId) ?? null;

  // Boot: load the module catalog + departments once.
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setBooting(true);
    setBootError(null);
    Promise.all([api.rbac.modules(token), api.rbac.departments(token)])
      .then(([mods, depts]) => {
        if (cancelled) return;
        setModules(mods);
        setDepartments(depts);
        setDeptId(depts[0]?.id ?? null);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setBootError("Không tải được dữ liệu. Vui lòng thử lại.");
      })
      .finally(() => !cancelled && setBooting(false));
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Load roles when the selected department changes.
  useEffect(() => {
    if (!token || deptId == null) {
      setRoles([]);
      setRoleId(null);
      return;
    }
    let cancelled = false;
    api.rbac
      .roles(token, deptId)
      .then((rs) => {
        if (cancelled) return;
        setRoles(rs);
        setRoleId(rs[0]?.id ?? null);
      })
      .catch(() => !cancelled && setRoles([]));
    return () => {
      cancelled = true;
    };
  }, [token, deptId]);

  // Load the permission matrix when the selected role changes.
  useEffect(() => {
    if (!token || roleId == null) {
      setMatrix([]);
      return;
    }
    let cancelled = false;
    setMatrixLoading(true);
    setSaveError(null);
    setSaved(false);
    api.rbac
      .permissions(token, roleId)
      .then((rows) => {
        if (cancelled) return;
        setMatrix(rows);
        setDirty(false);
      })
      .catch(() => !cancelled && setSaveError("Không tải được ma trận quyền."))
      .finally(() => !cancelled && setMatrixLoading(false));
    return () => {
      cancelled = true;
    };
  }, [token, roleId]);

  function toggle(moduleKey: string, action: ActionKey, value: boolean) {
    setMatrix((rows) =>
      rows.map((r) => (r.module_key === moduleKey ? { ...r, [action]: value } : r)),
    );
    setDirty(true);
    setSaved(false);
  }

  function setScope(moduleKey: string, scope: Scope) {
    setMatrix((rows) =>
      rows.map((r) => (r.module_key === moduleKey ? { ...r, scope } : r)),
    );
    setDirty(true);
    setSaved(false);
  }

  async function onSave() {
    if (!token || roleId == null || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await api.rbac.savePermissions(token, roleId, matrix);
      setMatrix(updated);
      setDirty(false);
      setSaved(true);
    } catch {
      setSaveError("Lưu thất bại. Vui lòng thử lại.");
    } finally {
      setSaving(false);
    }
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!token || deptId == null || !name || creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      const role = await api.rbac.createRole(token, name, deptId);
      setRoles((rs) => [...rs, role]);
      setRoleId(role.id);
      setNewName("");
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) setCreateError(err.message);
      else setCreateError("Không tạo được vai trò. Vui lòng thử lại.");
    } finally {
      setCreating(false);
    }
  }

  if (forbidden) {
    return (
      <main className="roles">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Quản lý Vai trò.
        </div>
      </main>
    );
  }

  if (booting) {
    return (
      <main className="roles">
        <p className="roles__status" role="status">
          Đang tải…
        </p>
      </main>
    );
  }

  if (bootError) {
    return (
      <main className="roles">
        <div className="banner banner--error" role="alert">
          <span>{bootError}</span>
          <button type="button" className="btn btn--ghost" onClick={() => location.reload()}>
            Thử lại
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="roles">
      <header className="roles__head">
        <div>
          <p className="eyebrow">Quản trị</p>
          <h1 className="roles__title">
            Thiết lập Quyền{currentRole ? `: ${currentRole.name}` : ""}
          </h1>
          <p className="roles__sub">
            Bật/tắt thao tác và chọn phạm vi dữ liệu cho từng module của vai trò.
          </p>
        </div>
        <div className="roles__save">
          {saved && !dirty && <span className="roles__saved">Đã lưu</span>}
          <Button
            variant="accent"
            onClick={onSave}
            disabled={!currentRole || !dirty}
            loading={saving}
          >
            Lưu thay đổi
          </Button>
        </div>
      </header>

      <div className="roles__toolbar">
        <label className="roles__pick">
          <span className="roles__pick-label">Phòng ban</span>
          <select
            className="input"
            value={deptId ?? ""}
            onChange={(e) => setDeptId(e.target.value ? Number(e.target.value) : null)}
          >
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>

        <label className="roles__pick">
          <span className="roles__pick-label">Vai trò</span>
          <select
            className="input"
            value={roleId ?? ""}
            disabled={roles.length === 0}
            onChange={(e) => setRoleId(e.target.value ? Number(e.target.value) : null)}
          >
            {roles.length === 0 && <option value="">— chưa có —</option>}
            {roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>

        <form className="roles__create" onSubmit={onCreate}>
          <label className="roles__pick">
            <span className="roles__pick-label">Vai trò mới</span>
            <input
              className={`input${createError ? " input--error" : ""}`}
              placeholder="VD: Trợ lý KD"
              value={newName}
              onChange={(e) => {
                setNewName(e.target.value);
                if (createError) setCreateError(null);
              }}
              aria-invalid={createError ? true : undefined}
            />
          </label>
          <Button type="submit" variant="primary" disabled={!newName.trim()} loading={creating}>
            Tạo
          </Button>
        </form>
      </div>

      {createError && (
        <p className="roles__create-error" role="alert">
          {createError}
        </p>
      )}

      {saveError && (
        <div className="banner banner--error" role="alert">
          {saveError}
        </div>
      )}

      <section className="card roles__matrix">
        {matrixLoading ? (
          <p className="roles__status" role="status">
            Đang tải ma trận…
          </p>
        ) : !currentRole ? (
          <div className="roles__empty">
            <p className="roles__empty-title">Phòng này chưa có vai trò</p>
            <p className="roles__sub">Tạo vai trò đầu tiên ở ô “Vai trò mới” phía trên.</p>
          </div>
        ) : (
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
              {matrix.map((row) => (
                <tr key={row.module_key}>
                  <td className="matrix__mod">
                    {moduleLabel.get(row.module_key) ?? row.module_key}
                  </td>
                  {ACTIONS.map((a) => (
                    <td key={a.key} className="matrix__act">
                      <input
                        type="checkbox"
                        className="switch"
                        checked={row[a.key]}
                        aria-label={`${a.label} — ${moduleLabel.get(row.module_key) ?? row.module_key}`}
                        onChange={(e) => toggle(row.module_key, a.key, e.target.checked)}
                      />
                    </td>
                  ))}
                  <td className="matrix__scope">
                    <select
                      className="input input--sm"
                      value={row.scope}
                      aria-label={`Phạm vi — ${moduleLabel.get(row.module_key) ?? row.module_key}`}
                      onChange={(e) => setScope(row.module_key, e.target.value as Scope)}
                    >
                      {SCOPES.map((s) => (
                        <option key={s.value} value={s.value}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
