import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type Department,
  type DepartmentSubtreeRow,
  type ModuleDef,
  type PermissionRow,
  type Role,
  type Scope,
  type UserBrief,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import {
  PermissionMatrix,
  defaultMatrix,
  type ActionKey,
} from "../components/PermissionMatrix";
import "./departments.css";

/** Order departments as a tree (parent before its children) with a depth for indentation. */
function orderTree(list: Department[]): { dept: Department; depth: number }[] {
  const byParent = new Map<number | null, Department[]>();
  for (const d of list) {
    const key = d.parent_id ?? null;
    const bucket = byParent.get(key);
    if (bucket) bucket.push(d);
    else byParent.set(key, [d]);
  }
  const out: { dept: Department; depth: number }[] = [];
  const placed = new Set<number>();
  const visit = (parent: number | null, depth: number) => {
    for (const d of byParent.get(parent) ?? []) {
      if (placed.has(d.id)) continue;
      placed.add(d.id);
      out.push({ dept: d, depth });
      visit(d.id, depth + 1);
    }
  };
  visit(null, 0);
  // Orphans (parent filtered out / missing) fall back to roots so nothing disappears.
  for (const d of list) if (!placed.has(d.id)) out.push({ dept: d, depth: 0 });
  return out;
}

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

export function DepartmentsPage() {
  const { token } = useAuth();

  const [departments, setDepartments] = useState<Department[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [users, setUsers] = useState<UserBrief[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [modules, setModules] = useState<ModuleDef[]>([]);

  // Add-role popup (reuses the Roles permission matrix).
  const [addRoleOpen, setAddRoleOpen] = useState(false);
  const [addRoleName, setAddRoleName] = useState("");
  const [addRoleMatrix, setAddRoleMatrix] = useState<PermissionRow[]>([]);
  const [addRoleError, setAddRoleError] = useState<string | null>(null);
  const [addRoleBusy, setAddRoleBusy] = useState(false);

  // Edit-role popup (open by clicking a role chip): name + its permission matrix.
  const [editRoleOpen, setEditRoleOpen] = useState(false);
  const [editRoleId, setEditRoleId] = useState<number | null>(null);
  const [editRoleName, setEditRoleName] = useState("");
  const [editRoleMatrix, setEditRoleMatrix] = useState<PermissionRow[]>([]);
  const [editRoleLoading, setEditRoleLoading] = useState(false);
  const [editRoleError, setEditRoleError] = useState<string | null>(null);
  const [editRoleBusy, setEditRoleBusy] = useState(false);
  const [editRoleConfirmDelete, setEditRoleConfirmDelete] = useState(false);
  const [editRoleDeleting, setEditRoleDeleting] = useState(false);

  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editHead, setEditHead] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [confirmingSave, setConfirmingSave] = useState(false);

  // Create (PBI-4002): name + optional description + optional parent; code is auto.
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newParentId, setNewParentId] = useState<number | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  // Delete (PBI-4005): confirm shows the whole branch that will be removed.
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [subtree, setSubtree] = useState<DepartmentSubtreeRow[] | null>(null);
  const [subtreeLoading, setSubtreeLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const currentDept = departments.find((d) => d.id === selectedId) ?? null;
  const tree = useMemo(() => orderTree(departments), [departments]);
  const byId = useMemo(() => new Map(departments.map((d) => [d.id, d])), [departments]);

  function loadDepartments(): Promise<Department[]> {
    if (!token) return Promise.resolve([]);
    return api.rbac.departments(token);
  }

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setBooting(true);
    setBootError(null);
    Promise.all([
      loadDepartments(),
      api.rbac.modules(token).catch(() => [] as ModuleDef[]),
    ])
      .then(([list, mods]) => {
        if (cancelled) return;
        setDepartments(list);
        setModules(mods);
        setSelectedId(list[0]?.id ?? null);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setBootError("Không tải được danh sách phòng ban.");
      })
      .finally(() => !cancelled && setBooting(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    setConfirmingDelete(false);
    setConfirmingSave(false);
    setAddRoleOpen(false);
    setEditRoleOpen(false);
    setSubtree(null);
    setDeleteError(null);
    setSaveError(null);
    setSaved(false);
    setDirty(false);
    const dept = departments.find((d) => d.id === selectedId) ?? null;
    setEditName(dept?.name ?? "");
    setEditDescription(dept?.description ?? "");
    setEditHead(dept?.head_user_id ?? null);
    if (!token || selectedId == null) {
      setUsers([]);
      setRoles([]);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    Promise.all([api.rbac.departmentUsers(token, selectedId), api.rbac.roles(token, selectedId)])
      .then(([us, rs]) => {
        if (cancelled) return;
        setUsers(us);
        setRoles(rs);
      })
      .catch(() => {
        if (cancelled) return;
        setUsers([]);
        setRoles([]);
      })
      .finally(() => !cancelled && setDetailLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, selectedId]);

  async function refresh(keepId: number | null) {
    const list = await loadDepartments();
    setDepartments(list);
    if (keepId != null && list.some((d) => d.id === keepId)) setSelectedId(keepId);
    else setSelectedId(list[0]?.id ?? null);
  }

  const parentName = (id: number | null | undefined) =>
    id == null ? null : byId.get(id)?.name ?? null;

  function openCreate() {
    setNewName("");
    setNewDescription("");
    setNewParentId(null);
    setCreateError(null);
    setCreateOpen(true);
  }

  function closeCreate() {
    if (creating) return;
    setCreateOpen(false);
  }

  async function submitCreate() {
    const name = newName.trim();
    if (!token || !name || creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      const dept = await api.rbac.createDepartment(
        token,
        name,
        newDescription.trim() || null,
        newParentId,
      );
      setCreateOpen(false);
      await refresh(dept.id);
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) setCreateError(err.message);
      else if (err instanceof ApiError && err.isForbidden)
        setCreateError("Bạn không có quyền tạo phòng ban.");
      else setCreateError("Không tạo được phòng ban. Vui lòng thử lại.");
    } finally {
      setCreating(false);
    }
  }

  async function doSave() {
    if (!token || selectedId == null || !editName.trim() || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api.rbac.updateDepartment(
        token,
        selectedId,
        editName.trim(),
        editHead,
        editDescription.trim() || null,
      );
      await refresh(selectedId);
      setDirty(false);
      setSaved(true);
      setConfirmingSave(false);
    } catch (err) {
      if (err instanceof ApiError && (err.isConflict || err.status === 400)) setSaveError(err.message);
      else setSaveError("Lưu thất bại. Vui lòng thử lại.");
    } finally {
      setSaving(false);
    }
  }

  async function openDeleteConfirm() {
    if (!token || selectedId == null) return;
    setDeleteError(null);
    setConfirmingDelete(true);
    setSubtree(null);
    setSubtreeLoading(true);
    try {
      setSubtree(await api.rbac.departmentSubtree(token, selectedId));
    } catch {
      setSubtree(null);
      setDeleteError("Không tải được danh sách đơn vị sẽ bị xóa.");
    } finally {
      setSubtreeLoading(false);
    }
  }

  async function confirmDelete() {
    if (!token || selectedId == null || deleteBusy) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await api.rbac.deleteDepartment(token, selectedId);
      setConfirmingDelete(false);
      await refresh(null);
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) setDeleteError(err.message);
      else if (err instanceof ApiError && err.isForbidden)
        setDeleteError("Bạn không có quyền xóa phòng ban.");
      else setDeleteError("Không xóa được phòng ban. Vui lòng thử lại.");
    } finally {
      setDeleteBusy(false);
    }
  }

  function openAddRole() {
    setAddRoleName("");
    setAddRoleMatrix(defaultMatrix(modules));
    setAddRoleError(null);
    setAddRoleOpen(true);
  }

  function toggleAddRole(moduleKey: string, action: ActionKey, value: boolean) {
    setAddRoleMatrix((rows) =>
      rows.map((r) => (r.module_key === moduleKey ? { ...r, [action]: value } : r)),
    );
  }

  function scopeAddRole(moduleKey: string, scope: Scope) {
    setAddRoleMatrix((rows) =>
      rows.map((r) => (r.module_key === moduleKey ? { ...r, scope } : r)),
    );
  }

  async function submitAddRole() {
    const name = addRoleName.trim();
    if (!token || selectedId == null || !name || addRoleBusy) return;
    setAddRoleBusy(true);
    setAddRoleError(null);
    try {
      const role = await api.rbac.createRole(token, name, selectedId);
      await api.rbac.savePermissions(token, role.id, addRoleMatrix);
      const rs = await api.rbac.roles(token, selectedId); // refresh this department's roles
      setRoles(rs);
      setAddRoleOpen(false);
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) setAddRoleError(err.message);
      else if (err instanceof ApiError && err.isForbidden)
        setAddRoleError("Bạn không có quyền tạo vai trò.");
      else setAddRoleError("Không tạo được vai trò. Vui lòng thử lại.");
    } finally {
      setAddRoleBusy(false);
    }
  }

  async function openEditRole(role: Role) {
    setEditRoleId(role.id);
    setEditRoleName(role.name);
    setEditRoleMatrix([]);
    setEditRoleError(null);
    setEditRoleConfirmDelete(false);
    setEditRoleOpen(true);
    setEditRoleLoading(true);
    try {
      if (token) setEditRoleMatrix(await api.rbac.permissions(token, role.id));
    } catch {
      setEditRoleError("Không tải được ma trận quyền.");
    } finally {
      setEditRoleLoading(false);
    }
  }

  function toggleEditRole(moduleKey: string, action: ActionKey, value: boolean) {
    setEditRoleMatrix((rows) =>
      rows.map((r) => (r.module_key === moduleKey ? { ...r, [action]: value } : r)),
    );
  }

  function scopeEditRole(moduleKey: string, scope: Scope) {
    setEditRoleMatrix((rows) =>
      rows.map((r) => (r.module_key === moduleKey ? { ...r, scope } : r)),
    );
  }

  async function submitEditRole() {
    const name = editRoleName.trim();
    if (!token || editRoleId == null || !name || editRoleBusy) return;
    setEditRoleBusy(true);
    setEditRoleError(null);
    try {
      const current = roles.find((r) => r.id === editRoleId);
      if (current && current.name !== name) {
        await api.rbac.renameRole(token, editRoleId, name);
      }
      await api.rbac.savePermissions(token, editRoleId, editRoleMatrix);
      if (selectedId != null) setRoles(await api.rbac.roles(token, selectedId));
      setEditRoleOpen(false);
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) setEditRoleError(err.message);
      else if (err instanceof ApiError && err.isForbidden)
        setEditRoleError("Bạn không có quyền sửa vai trò.");
      else setEditRoleError("Lưu thất bại. Vui lòng thử lại.");
    } finally {
      setEditRoleBusy(false);
    }
  }

  async function deleteEditRole() {
    if (!token || editRoleId == null || editRoleDeleting) return;
    setEditRoleDeleting(true);
    setEditRoleError(null);
    try {
      await api.rbac.deleteRole(token, editRoleId);
      if (selectedId != null) setRoles(await api.rbac.roles(token, selectedId));
      setEditRoleOpen(false);
    } catch (err) {
      // 409 = a user still holds this role (delete blocked).
      if (err instanceof ApiError && err.isConflict) setEditRoleError(err.message);
      else if (err instanceof ApiError && err.isForbidden)
        setEditRoleError("Bạn không có quyền xóa vai trò.");
      else setEditRoleError("Không xóa được vai trò. Vui lòng thử lại.");
    } finally {
      setEditRoleDeleting(false);
      setEditRoleConfirmDelete(false);
    }
  }

  if (forbidden) {
    return (
      <main className="depts">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Quản lý Phòng ban.
        </div>
      </main>
    );
  }

  if (booting) {
    return (
      <main className="depts">
        <p className="depts__status" role="status">
          Đang tải…
        </p>
      </main>
    );
  }

  if (bootError) {
    return (
      <main className="depts">
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
    <main className="depts">
      <header className="depts__head">
        <div>
          <p className="eyebrow">Quản trị</p>
          <h1 className="depts__title">Phòng ban</h1>
          <p className="depts__sub">
            {departments.length} phòng · mã tự sinh, tổ chức theo cây cha–con.
          </p>
        </div>
        <Button type="button" variant="accent" onClick={openCreate}>
          + Tạo phòng ban
        </Button>
      </header>

      <div className="depts__grid">
        <aside className="depts__list" aria-label="Danh sách phòng ban">
          {departments.length === 0 ? (
            <div className="depts__empty">
              <p className="depts__empty-title">Chưa có phòng ban</p>
              <p className="depts__hint">Bấm “Tạo phòng ban” để thêm phòng đầu tiên.</p>
            </div>
          ) : (
            tree.map(({ dept: d, depth }) => (
              <button
                key={d.id}
                type="button"
                className={`depts__item${d.id === selectedId ? " is-active" : ""}`}
                style={depth ? { marginLeft: `${depth * 16}px` } : undefined}
                aria-current={d.id === selectedId ? "true" : undefined}
                onClick={() => setSelectedId(d.id)}
              >
                <span className="depts__item-top">
                  {d.code && <span className="depts__code">{d.code}</span>}
                  <span className="depts__item-name">{d.name}</span>
                </span>
                <span className="depts__item-meta">
                  {d.role_count ?? 0} vai trò · {d.user_count ?? 0} người
                  {depth > 0 && parentName(d.parent_id) ? ` · thuộc ${parentName(d.parent_id)}` : ""}
                </span>
              </button>
            ))
          )}
        </aside>

        <section className="depts__detail">
          {!currentDept ? (
            <div className="card depts__placeholder">
              <p className="depts__status">Chọn một phòng bên trái để xem chi tiết.</p>
            </div>
          ) : (
            <>
              {/* Header: identity at a glance — code badge, name, live counts. */}
              <div className="card depts__id">
                <div className="depts__id-avatar" aria-hidden="true">
                  {initials(currentDept.name)}
                </div>
                <div className="depts__id-main">
                  <div className="depts__id-line">
                    {currentDept.code && <span className="depts__code">{currentDept.code}</span>}
                    <h2 className="depts__id-name">{currentDept.name}</h2>
                  </div>
                  <p className="depts__id-meta">
                    {roles.length} vai trò · {users.length} người ·{" "}
                    {parentName(currentDept.parent_id)
                      ? `Thuộc ${parentName(currentDept.parent_id)}`
                      : "Phòng gốc"}
                  </p>
                </div>
              </div>

              {/* Edit section. */}
              <div className="card depts__section">
                <p className="eyebrow">Thông tin phòng</p>
                <div className="field">
                  <label className="field__label" htmlFor="dept-name">
                    Tên phòng
                  </label>
                  <input
                    id="dept-name"
                    className={`input${saveError ? " input--error" : ""}`}
                    value={editName}
                    onChange={(e) => {
                      setEditName(e.target.value);
                      setDirty(true);
                      setSaved(false);
                      if (saveError) setSaveError(null);
                    }}
                  />
                </div>

                <div className="field">
                  <label className="field__label" htmlFor="dept-desc">
                    Mô tả
                  </label>
                  <textarea
                    id="dept-desc"
                    className="input depts__textarea"
                    rows={2}
                    placeholder="Tùy chọn"
                    value={editDescription}
                    onChange={(e) => {
                      setEditDescription(e.target.value);
                      setDirty(true);
                      setSaved(false);
                    }}
                  />
                </div>

                <div className="field">
                  <label className="field__label" htmlFor="dept-head">
                    Người đứng đầu
                  </label>
                  <select
                    id="dept-head"
                    className="input"
                    value={editHead ?? ""}
                    disabled={users.length === 0}
                    onChange={(e) => {
                      setEditHead(e.target.value ? Number(e.target.value) : null);
                      setDirty(true);
                      setSaved(false);
                    }}
                  >
                    <option value="">— Chưa chỉ định —</option>
                    {users.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.name} ({u.username})
                      </option>
                    ))}
                  </select>
                  {users.length === 0 && (
                    <span className="depts__hint">
                      Phòng chưa có người dùng — thêm ở màn Người dùng trước.
                    </span>
                  )}
                </div>

                <div className="depts__section-foot">
                  {saved && !dirty && <span className="depts__saved">Đã lưu</span>}
                  {saveError && (
                    <span className="depts__inline-error" role="alert">
                      {saveError}
                    </span>
                  )}
                  <Button
                    variant="accent"
                    onClick={() => {
                      setSaveError(null);
                      setConfirmingSave(true);
                    }}
                    disabled={!dirty || !editName.trim()}
                  >
                    Lưu thay đổi
                  </Button>
                </div>
              </div>

              {/* Roles in this department — add a role (name + permission matrix) right here. */}
              <div className="card depts__section">
                <div className="depts__section-head">
                  <p className="eyebrow">Vai trò trong phòng</p>
                  <Button type="button" variant="ghost" onClick={openAddRole}>
                    + Thêm vai trò
                  </Button>
                </div>
                {detailLoading ? (
                  <p className="depts__status">Đang tải…</p>
                ) : roles.length === 0 ? (
                  <p className="depts__hint">Chưa có vai trò. Bấm “+ Thêm vai trò” để tạo.</p>
                ) : (
                  <div className="depts__chips">
                    {roles.map((r) => (
                      <button
                        key={r.id}
                        type="button"
                        className="depts__chip depts__chip--btn"
                        onClick={() => openEditRole(r)}
                      >
                        {r.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Danger zone. */}
              <div className="card depts__danger">
                <div className="depts__danger-row">
                  <div>
                    <p className="depts__danger-title">Xóa phòng ban</p>
                    <p className="depts__hint">Xóa phòng này cùng mọi phòng con và vai trò của chúng.</p>
                  </div>
                  <button type="button" className="btn btn--ghost depts__danger-text" onClick={openDeleteConfirm}>
                    Xóa phòng
                  </button>
                </div>
              </div>
            </>
          )}
        </section>
      </div>

      {/* Create department form (popup). */}
      <ConfirmDialog
        open={createOpen}
        title="Tạo phòng ban"
        confirmLabel="Tạo phòng"
        busy={creating}
        confirmDisabled={!newName.trim()}
        onConfirm={submitCreate}
        onCancel={closeCreate}
      >
        <div className="depts__form">
          <div className="field">
            <label className="field__label" htmlFor="new-dept-name">
              Tên phòng <span className="depts__req">*</span>
            </label>
            <input
              id="new-dept-name"
              className={`input${createError ? " input--error" : ""}`}
              placeholder="VD: Thiết kế"
              value={newName}
              autoFocus
              aria-invalid={createError ? true : undefined}
              onChange={(e) => {
                setNewName(e.target.value);
                if (createError) setCreateError(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void submitCreate();
                }
              }}
            />
            {createError && (
              <span className="field__error" role="alert">
                {createError}
              </span>
            )}
          </div>

          <div className="field">
            <label className="field__label" htmlFor="new-dept-parent">
              Trực thuộc
            </label>
            <select
              id="new-dept-parent"
              className="input"
              value={newParentId ?? ""}
              onChange={(e) => setNewParentId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">— Không (phòng gốc) —</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.code ? `${d.code} · ` : ""}
                  {d.name}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="new-dept-desc">
              Mô tả
            </label>
            <textarea
              id="new-dept-desc"
              className="input depts__textarea"
              placeholder="Tùy chọn — chức năng, phạm vi của phòng"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
            />
          </div>

          <p className="depts__hint">Mã phòng (PB###) sẽ được hệ thống tự sinh.</p>
        </div>
      </ConfirmDialog>

      {/* Add role to this department: name + the same permission matrix as the Roles screen. */}
      <ConfirmDialog
        open={addRoleOpen}
        title={currentDept ? `Thêm vai trò · ${currentDept.name}` : "Thêm vai trò"}
        confirmLabel="Tạo vai trò"
        wide
        busy={addRoleBusy}
        confirmDisabled={!addRoleName.trim()}
        onConfirm={submitAddRole}
        onCancel={() => {
          if (!addRoleBusy) setAddRoleOpen(false);
        }}
      >
        <div className="field">
          <label className="field__label" htmlFor="add-role-name">
            Tên vai trò <span className="depts__req">*</span>
          </label>
          <input
            id="add-role-name"
            className={`input${addRoleError ? " input--error" : ""}`}
            placeholder="VD: Trưởng phòng"
            value={addRoleName}
            autoFocus
            aria-invalid={addRoleError ? true : undefined}
            onChange={(e) => {
              setAddRoleName(e.target.value);
              if (addRoleError) setAddRoleError(null);
            }}
          />
          {addRoleError && (
            <span className="field__error" role="alert">
              {addRoleError}
            </span>
          )}
        </div>
        <p className="eyebrow depts__matrix-label">Phân quyền</p>
        <div className="matrix-scroll">
          <PermissionMatrix
            modules={modules}
            matrix={addRoleMatrix}
            onToggle={toggleAddRole}
            onScope={scopeAddRole}
          />
        </div>
      </ConfirmDialog>

      {/* Edit a role in this department: its name + permission matrix. */}
      <ConfirmDialog
        open={editRoleOpen}
        title="Sửa vai trò"
        confirmLabel="Lưu"
        wide
        busy={editRoleBusy}
        error={editRoleError}
        confirmDisabled={editRoleLoading || !editRoleName.trim()}
        onConfirm={submitEditRole}
        onCancel={() => {
          if (!editRoleBusy && !editRoleDeleting) setEditRoleOpen(false);
        }}
      >
        <div className="field">
          <label className="field__label" htmlFor="edit-role-name">
            Tên vai trò <span className="depts__req">*</span>
          </label>
          <input
            id="edit-role-name"
            className={`input${editRoleError ? " input--error" : ""}`}
            value={editRoleName}
            autoFocus
            aria-invalid={editRoleError ? true : undefined}
            onChange={(e) => {
              setEditRoleName(e.target.value);
              if (editRoleError) setEditRoleError(null);
            }}
          />
        </div>
        <p className="eyebrow depts__matrix-label">Phân quyền</p>
        {editRoleLoading ? (
          <p className="depts__status">Đang tải ma trận…</p>
        ) : (
          <div className="matrix-scroll">
            <PermissionMatrix
              modules={modules}
              matrix={editRoleMatrix}
              onToggle={toggleEditRole}
              onScope={scopeEditRole}
            />
          </div>
        )}

        <div className="depts__role-danger">
          {editRoleConfirmDelete ? (
            <div className="depts__inline">
              <span className="depts__confirm-count">Xóa vai trò này? Không thể hoàn tác.</span>
              <button
                type="button"
                className="btn btn--danger"
                disabled={editRoleDeleting}
                onClick={deleteEditRole}
              >
                {editRoleDeleting ? "Đang xóa…" : "Xác nhận xóa"}
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={editRoleDeleting}
                onClick={() => setEditRoleConfirmDelete(false)}
              >
                Hủy
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="btn btn--ghost depts__danger-text"
              disabled={editRoleBusy}
              onClick={() => {
                setEditRoleError(null);
                setEditRoleConfirmDelete(true);
              }}
            >
              Xóa vai trò
            </button>
          )}
        </div>
      </ConfirmDialog>

      {/* Confirm: save changes. */}
      <ConfirmDialog
        open={confirmingSave}
        title="Lưu thay đổi?"
        message={
          currentDept ? `Cập nhật thông tin phòng “${currentDept.name}”?` : undefined
        }
        confirmLabel="Lưu"
        busy={saving}
        error={saveError}
        onConfirm={doSave}
        onCancel={() => !saving && setConfirmingSave(false)}
      />

      {/* Confirm: delete the whole branch. */}
      <ConfirmDialog
        open={confirmingDelete}
        title="Xóa phòng ban?"
        message={
          currentDept
            ? `Xóa phòng “${currentDept.name}” và toàn bộ nhánh con? Không thể hoàn tác.`
            : undefined
        }
        confirmLabel="Xóa cả nhánh"
        danger
        busy={deleteBusy}
        error={deleteError}
        confirmDisabled={subtreeLoading}
        onConfirm={confirmDelete}
        onCancel={() => {
          if (deleteBusy) return;
          setConfirmingDelete(false);
          setSubtree(null);
        }}
      >
        {subtreeLoading ? (
          <p className="depts__status">Đang tải danh sách đơn vị…</p>
        ) : subtree && subtree.length > 0 ? (
          <>
            <p className="depts__confirm-count">{subtree.length} đơn vị sẽ bị xóa:</p>
            <ul className="depts__subtree">
              {subtree.map((s) => (
                <li key={s.id}>
                  {s.code && <span className="depts__code">{s.code}</span>}
                  {s.name}
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </ConfirmDialog>
    </main>
  );
}
