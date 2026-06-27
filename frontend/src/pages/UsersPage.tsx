import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type Department,
  type Role,
  type UserRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./users.css";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function UsersPage() {
  const { token, user: me } = useAuth();

  const [users, setUsers] = useState<UserRow[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [deptRoles, setDeptRoles] = useState<Role[]>([]);

  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [rolesLoading, setRolesLoading] = useState(false);

  const [cName, setCName] = useState("");
  const [cEmail, setCEmail] = useState("");
  const [cDept, setCDept] = useState<number | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [editRole, setEditRole] = useState<number | null>(null);
  const [roleSaving, setRoleSaving] = useState(false);
  const [roleSaved, setRoleSaved] = useState(false);
  const [roleError, setRoleError] = useState<string | null>(null);

  const [activeBusy, setActiveBusy] = useState(false);
  const [activeError, setActiveError] = useState<string | null>(null);

  const current = users.find((u) => u.id === selectedId) ?? null;

  function loadUsers(): Promise<UserRow[]> {
    return token ? api.rbac.users(token) : Promise.resolve([]);
  }

  // Boot: users + departments (for the create form).
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setBooting(true);
    setBootError(null);
    Promise.all([loadUsers(), api.rbac.departments(token)])
      .then(([us, depts]) => {
        if (cancelled) return;
        setUsers(us);
        setDepartments(depts);
        setCDept(depts[0]?.id ?? null);
        setSelectedId(us[0]?.id ?? null);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setBootError("Không tải được danh sách người dùng.");
      })
      .finally(() => !cancelled && setBooting(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Load the selected user's department roles for the role picker.
  useEffect(() => {
    setRoleSaved(false);
    setRoleError(null);
    setActiveError(null);
    const u = users.find((x) => x.id === selectedId) ?? null;
    setEditRole(u?.role_id ?? null);
    if (!token || u == null || u.department_id == null) {
      setDeptRoles([]);
      return;
    }
    let cancelled = false;
    setRolesLoading(true);
    api.rbac
      .roles(token, u.department_id)
      .then((rs) => !cancelled && setDeptRoles(rs))
      .catch(() => !cancelled && setDeptRoles([]))
      .finally(() => !cancelled && setRolesLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, selectedId]);

  async function refresh(keepId: number | null) {
    const us = await loadUsers();
    setUsers(us);
    if (keepId != null && us.some((u) => u.id === keepId)) setSelectedId(keepId);
    else setSelectedId(us[0]?.id ?? null);
  }

  function validateCreate(): string | null {
    if (!cName.trim()) return "Họ tên là bắt buộc.";
    if (!EMAIL_RE.test(cEmail.trim())) return "Email không hợp lệ.";
    if (cDept == null) return "Phòng ban là bắt buộc.";
    return null;
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!token || creating) return;
    const err = validateCreate();
    if (err) {
      setCreateError(err);
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const created = await api.rbac.createUser(token, cName.trim(), cEmail.trim(), cDept!);
      setCName("");
      setCEmail("");
      await refresh(created.id);
    } catch (e2) {
      if (e2 instanceof ApiError && e2.isConflict) setCreateError(e2.message);
      else if (e2 instanceof ApiError && e2.status === 404) setCreateError(e2.message);
      else setCreateError("Không tạo được tài khoản. Vui lòng thử lại.");
    } finally {
      setCreating(false);
    }
  }

  async function onSaveRole() {
    if (!token || current == null || roleSaving) return;
    setRoleSaving(true);
    setRoleError(null);
    try {
      await api.rbac.assignUserRole(token, current.id, editRole);
      await refresh(current.id);
      setRoleSaved(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) setRoleError(e.message);
      else setRoleError("Không gán được vai trò. Vui lòng thử lại.");
    } finally {
      setRoleSaving(false);
    }
  }

  async function onToggleActive() {
    if (!token || current == null || activeBusy) return;
    setActiveBusy(true);
    setActiveError(null);
    try {
      await api.rbac.setUserActive(token, current.id, !current.is_active);
      await refresh(current.id);
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) setActiveError(e.message);
      else setActiveError("Không đổi được trạng thái. Vui lòng thử lại.");
    } finally {
      setActiveBusy(false);
    }
  }

  if (forbidden) {
    return (
      <main className="users">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Quản lý Người dùng.
        </div>
      </main>
    );
  }
  if (booting) {
    return (
      <main className="users">
        <p className="users__status" role="status">
          Đang tải…
        </p>
      </main>
    );
  }
  if (bootError) {
    return (
      <main className="users">
        <div className="banner banner--error" role="alert">
          <span>{bootError}</span>
          <button type="button" className="btn btn--ghost" onClick={() => location.reload()}>
            Thử lại
          </button>
        </div>
      </main>
    );
  }

  const isSelf = current != null && me != null && current.id === me.id;
  const roleDirty = current != null && editRole !== (current.role_id ?? null);

  return (
    <main className="users">
      <header className="users__head">
        <p className="eyebrow">Quản lý hệ thống</p>
        <h1 className="users__title">Quản lý Người dùng</h1>
        <p className="users__sub">Tạo tài khoản, gán phòng & vai trò, khóa/mở tài khoản.</p>
      </header>

      <form className="users__create" onSubmit={onCreate}>
        <input
          className="input"
          placeholder="Họ tên"
          value={cName}
          onChange={(e) => {
            setCName(e.target.value);
            if (createError) setCreateError(null);
          }}
        />
        <input
          className="input"
          type="email"
          placeholder="Email"
          value={cEmail}
          onChange={(e) => {
            setCEmail(e.target.value);
            if (createError) setCreateError(null);
          }}
        />
        <select
          className="input"
          value={cDept ?? ""}
          onChange={(e) => setCDept(e.target.value ? Number(e.target.value) : null)}
        >
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <Button type="submit" variant="primary" loading={creating}>
          Tạo tài khoản
        </Button>
        {createError && (
          <span className="users__inline-error" role="alert">
            {createError}
          </span>
        )}
      </form>

      <div className="users__grid">
        <div className="card users__tablewrap">
          <table className="users__table">
            <thead>
              <tr>
                <th>Tên</th>
                <th>Email</th>
                <th>Phòng</th>
                <th>Vai trò</th>
                <th>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr
                  key={u.id}
                  className={`users__row${u.id === selectedId ? " is-active" : ""}`}
                  aria-current={u.id === selectedId ? "true" : undefined}
                  onClick={() => setSelectedId(u.id)}
                >
                  <td>{u.name}</td>
                  <td className="users__email">{u.email}</td>
                  <td>{u.department_name ?? "—"}</td>
                  <td>{u.role_name ?? <span className="users__muted">Chưa gán</span>}</td>
                  <td>
                    <span className={`users__badge${u.is_active ? "" : " users__badge--locked"}`}>
                      {u.is_active ? "Hoạt động" : "Đã khóa"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <section className="card users__detail">
          {!current ? (
            <p className="users__status">Chọn một người dùng để gán vai trò / khóa.</p>
          ) : (
            <>
              <div className="users__who">
                <p className="users__who-name">{current.name}</p>
                <p className="users__muted">{current.email}</p>
                <p className="users__muted">{current.department_name ?? "—"}</p>
              </div>

              <div className="field">
                <label className="field__label" htmlFor="user-role">
                  Vai trò (trong phòng)
                </label>
                <select
                  id="user-role"
                  className="input"
                  value={editRole ?? ""}
                  disabled={rolesLoading}
                  onChange={(e) => {
                    setEditRole(e.target.value ? Number(e.target.value) : null);
                    setRoleSaved(false);
                  }}
                >
                  <option value="">— Chưa gán —</option>
                  {deptRoles.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
                {deptRoles.length === 0 && !rolesLoading && (
                  <span className="users__hint">Phòng chưa có vai trò — tạo ở màn Vai trò.</span>
                )}
              </div>

              <div className="users__actions">
                <Button variant="accent" onClick={onSaveRole} disabled={!roleDirty} loading={roleSaving}>
                  Lưu vai trò
                </Button>
                {roleSaved && !roleDirty && <span className="users__saved">Đã lưu</span>}
                {roleError && (
                  <span className="users__inline-error" role="alert">
                    {roleError}
                  </span>
                )}
              </div>

              <div className="users__lock">
                <button
                  type="button"
                  className={`btn ${current.is_active ? "btn--danger" : "btn--primary"}`}
                  disabled={activeBusy || isSelf}
                  onClick={onToggleActive}
                >
                  {current.is_active ? "Khóa tài khoản" : "Mở khóa"}
                </button>
                {isSelf && <span className="users__hint">Không thể tự khóa tài khoản của mình.</span>}
                {activeError && (
                  <span className="users__inline-error" role="alert">
                    {activeError}
                  </span>
                )}
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
