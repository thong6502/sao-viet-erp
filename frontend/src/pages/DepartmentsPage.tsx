import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type Department,
  type Role,
  type UserBrief,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./departments.css";

export function DepartmentsPage() {
  const { token } = useAuth();

  const [departments, setDepartments] = useState<Department[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [users, setUsers] = useState<UserBrief[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);

  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  const [editName, setEditName] = useState("");
  const [editHead, setEditHead] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [newName, setNewName] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const currentDept = departments.find((d) => d.id === selectedId) ?? null;

  function loadDepartments(): Promise<Department[]> {
    if (!token) return Promise.resolve([]);
    return api.rbac.departments(token);
  }

  // Boot.
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setBooting(true);
    setBootError(null);
    loadDepartments()
      .then((list) => {
        if (cancelled) return;
        setDepartments(list);
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

  // Load detail (users + roles) when the selection changes.
  useEffect(() => {
    setConfirmingDelete(false);
    setDeleteError(null);
    setSaveError(null);
    setSaved(false);
    setDirty(false);
    const dept = departments.find((d) => d.id === selectedId) ?? null;
    setEditName(dept?.name ?? "");
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

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!token || !name || creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      const dept = await api.rbac.createDepartment(token, name);
      setNewName("");
      await refresh(dept.id);
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) setCreateError(err.message);
      else setCreateError("Không tạo được phòng ban. Vui lòng thử lại.");
    } finally {
      setCreating(false);
    }
  }

  async function onSave() {
    if (!token || selectedId == null || !editName.trim() || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api.rbac.updateDepartment(token, selectedId, editName.trim(), editHead);
      await refresh(selectedId);
      setDirty(false);
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError && (err.isConflict || err.status === 400)) setSaveError(err.message);
      else setSaveError("Lưu thất bại. Vui lòng thử lại.");
    } finally {
      setSaving(false);
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
      else setDeleteError("Không xóa được phòng ban. Vui lòng thử lại.");
    } finally {
      setDeleteBusy(false);
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
          <p className="eyebrow">Quản lý hệ thống</p>
          <h1 className="depts__title">Quản lý Phòng ban</h1>
          <p className="depts__sub">Tạo phòng, đặt người đứng đầu, và xem vai trò của phòng.</p>
        </div>
      </header>

      <form className="depts__create" onSubmit={onCreate}>
        <input
          className={`input${createError ? " input--error" : ""}`}
          placeholder="Tên phòng ban mới (VD: Thiết kế)"
          value={newName}
          aria-invalid={createError ? true : undefined}
          onChange={(e) => {
            setNewName(e.target.value);
            if (createError) setCreateError(null);
          }}
        />
        <Button type="submit" variant="primary" disabled={!newName.trim()} loading={creating}>
          Tạo phòng
        </Button>
        {createError && (
          <span className="depts__inline-error" role="alert">
            {createError}
          </span>
        )}
      </form>

      <div className="depts__grid">
        <aside className="depts__list" aria-label="Danh sách phòng ban">
          {departments.length === 0 ? (
            <p className="depts__status">Chưa có phòng ban. Tạo phòng đầu tiên phía trên.</p>
          ) : (
            departments.map((d) => (
              <button
                key={d.id}
                type="button"
                className={`depts__item${d.id === selectedId ? " is-active" : ""}`}
                aria-current={d.id === selectedId ? "true" : undefined}
                onClick={() => setSelectedId(d.id)}
              >
                <span className="depts__item-name">{d.name}</span>
                <span className="depts__item-meta">
                  {d.role_count ?? 0} vai trò · {d.user_count ?? 0} người
                  {d.head_name ? ` · ${d.head_name}` : ""}
                </span>
              </button>
            ))
          )}
        </aside>

        <section className="card depts__detail">
          {!currentDept ? (
            <p className="depts__status">Chọn một phòng để xem chi tiết.</p>
          ) : (
            <>
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
                  <option value="">— Không —</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name} ({u.username})
                    </option>
                  ))}
                </select>
                {users.length === 0 && (
                  <span className="depts__hint">
                    Chưa có người dùng trong phòng — thêm ở màn Người dùng trước.
                  </span>
                )}
              </div>

              <div className="depts__save">
                <Button variant="accent" onClick={onSave} disabled={!dirty || !editName.trim()} loading={saving}>
                  Lưu thay đổi
                </Button>
                {saved && !dirty && <span className="depts__saved">Đã lưu</span>}
                {saveError && (
                  <span className="depts__inline-error" role="alert">
                    {saveError}
                  </span>
                )}
              </div>

              <div className="depts__roles">
                <p className="eyebrow">Vai trò trong phòng</p>
                {detailLoading ? (
                  <p className="depts__status">Đang tải…</p>
                ) : roles.length === 0 ? (
                  <p className="depts__hint">Chưa có vai trò. Tạo ở màn Vai trò.</p>
                ) : (
                  <ul className="depts__chips">
                    {roles.map((r) => (
                      <li key={r.id} className="depts__chip">
                        {r.name}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="depts__delete">
                {confirmingDelete ? (
                  <div className="depts__inline">
                    <span className="depts__confirm">Xóa phòng “{currentDept.name}”?</span>
                    <button type="button" className="btn btn--danger" disabled={deleteBusy} onClick={confirmDelete}>
                      {deleteBusy ? "Đang xóa…" : "Xác nhận xóa"}
                    </button>
                    <button type="button" className="btn btn--ghost" onClick={() => setConfirmingDelete(false)}>
                      Hủy
                    </button>
                    {deleteError && (
                      <span className="depts__inline-error" role="alert">
                        {deleteError}
                      </span>
                    )}
                  </div>
                ) : (
                  <button
                    type="button"
                    className="btn btn--ghost depts__danger-text"
                    onClick={() => {
                      setDeleteError(null);
                      setConfirmingDelete(true);
                    }}
                  >
                    Xóa phòng
                  </button>
                )}
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
