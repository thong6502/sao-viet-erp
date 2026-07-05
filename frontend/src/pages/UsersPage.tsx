import { useEffect, useMemo, useState } from "react";
import { ApiError, api, type Department, type UserRow } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Select } from "../components/Select";
import { UserDetailDialog } from "../components/UserDetailDialog";
import "./users.css";

export function UsersPage() {
  const { token, user: me } = useAuth();
  const can = useCan();
  const canCreate = can("nguoi_dung", "create");

  const [users, setUsers] = useState<UserRow[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);

  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  // List: search + filters + pagination.
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "locked">("all");
  const [deptFilter, setDeptFilter] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  // Create-account modal.
  const [createOpen, setCreateOpen] = useState(false);
  const [cName, setCName] = useState("");
  const [cUsername, setCUsername] = useState("");
  const [cDept, setCDept] = useState<number | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  // Detail modal.
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const current = users.find((u) => u.id === selectedId) ?? null;

  function loadUsers(): Promise<UserRow[]> {
    return token ? api.rbac.users(token) : Promise.resolve([]);
  }

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

  async function refresh() {
    setUsers(await loadUsers());
  }

  const filtersActive =
    search.trim() !== "" || statusFilter !== "all" || deptFilter != null;

  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase();
    return users.filter((u) => {
      if (statusFilter === "active" && !u.is_active) return false;
      if (statusFilter === "locked" && u.is_active) return false;
      if (deptFilter != null && u.department_id !== deptFilter) return false;
      if (q) {
        const hay = `${u.name} ${u.username} ${u.department_name ?? ""} ${u.role_name ?? ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [users, search, statusFilter, deptFilter]);

  const pageCount = Math.max(1, Math.ceil(filteredUsers.length / pageSize));
  const pageUsers = filteredUsers.slice((page - 1) * pageSize, page * pageSize);
  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);

  function resetFilters() {
    setSearch("");
    setStatusFilter("all");
    setDeptFilter(null);
    setPage(1);
  }

  function openCreate() {
    setCName("");
    setCUsername("");
    setCDept(departments[0]?.id ?? null);
    setCreateError(null);
    setCreateOpen(true);
  }

  async function onCreate() {
    if (!token || creating) return;
    if (!cName.trim()) return setCreateError("Họ tên là bắt buộc.");
    if (!cUsername.trim()) return setCreateError("Tên đăng nhập là bắt buộc.");
    if (cDept == null) return setCreateError("Phòng ban là bắt buộc.");
    setCreating(true);
    setCreateError(null);
    try {
      await api.rbac.createUser(token, cName.trim(), cUsername.trim(), cDept);
      setCreateOpen(false);
      await refresh();
    } catch (e) {
      if (e instanceof ApiError && (e.isConflict || e.status === 404)) setCreateError(e.message);
      else if (e instanceof ApiError && e.isForbidden)
        setCreateError("Bạn không có quyền tạo tài khoản.");
      else setCreateError("Không tạo được tài khoản. Vui lòng thử lại.");
    } finally {
      setCreating(false);
    }
  }

  function openDetail(u: UserRow) {
    setSelectedId(u.id);
    setDetailOpen(true);
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

  return (
    <main className="users">
      <header className="users__head">
        <div>
          <p className="eyebrow">Quản lý hệ thống</p>
          <h1 className="users__title">Quản lý Người dùng</h1>
          <p className="users__sub">
            {canCreate
              ? "Tạo tài khoản, gán vai trò, khóa/mở tài khoản."
              : "Danh sách tài khoản trong hệ thống."}
          </p>
        </div>
        {canCreate && (
          <Button type="button" variant="accent" onClick={openCreate}>
            + Tạo tài khoản
          </Button>
        )}
      </header>

      {/* Toolbar: search + filters. */}
      <div className="users__toolbar">
        <input
          className="input users__search"
          placeholder="Tìm theo tên, tên đăng nhập, phòng, vai trò…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          aria-label="Tìm người dùng"
        />
        <div className="users__filters">
          <div className="users__filter">
            <Select
              ariaLabel="Lọc trạng thái"
              value={statusFilter}
              onChange={(v) => {
                setStatusFilter(v);
                setPage(1);
              }}
              options={[
                { value: "all", label: "Tất cả trạng thái" },
                { value: "active", label: "Đang hoạt động" },
                { value: "locked", label: "Đã khóa" },
              ]}
            />
          </div>
          <div className="users__filter">
            <Select
              ariaLabel="Lọc theo phòng"
              value={deptFilter}
              placeholder="Tất cả phòng"
              onChange={(v) => {
                setDeptFilter(v);
                setPage(1);
              }}
              options={[
                { value: null, label: "Tất cả phòng" },
                ...departments.map((d) => ({ value: d.id, label: d.name, hint: d.code || undefined })),
              ]}
            />
          </div>
          {filtersActive && (
            <button type="button" className="btn btn--ghost" onClick={resetFilters}>
              Đặt lại
            </button>
          )}
        </div>
      </div>

      {/* Table. */}
      <div className="card users__tablewrap">
        <table className="users__table">
          <thead>
            <tr>
              <th className="users__id">ID</th>
              <th>Tên</th>
              <th>Tên đăng nhập</th>
              <th>Phòng</th>
              <th>Vai trò</th>
              <th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {pageUsers.length === 0 ? (
              <tr>
                <td colSpan={6} className="users__empty">
                  {users.length !== 0
                    ? "Không có người dùng khớp tìm kiếm."
                    : canCreate
                      ? "Chưa có người dùng. Bấm “Tạo tài khoản” để thêm."
                      : "Chưa có người dùng nào để xem."}
                </td>
              </tr>
            ) : (
              <>
                {pageUsers.map((u) => (
                  <tr
                    key={u.id}
                    className="users__row"
                    role="button"
                    tabIndex={0}
                    onClick={() => openDetail(u)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        openDetail(u);
                      }
                    }}
                  >
                    <td className="users__id">{u.code ?? "—"}</td>
                    <td>{u.name}</td>
                    <td className="users__email">{u.username}</td>
                    <td>{u.department_name ?? "—"}</td>
                    <td>{u.role_name ?? <span className="users__muted">Chưa gán</span>}</td>
                    <td>
                      <span className={`users__badge${u.is_active ? "" : " users__badge--locked"}`}>
                        {u.is_active ? "Hoạt động" : "Đã khóa"}
                      </span>
                    </td>
                  </tr>
                ))}
                {/* Hàng đệm giữ chiều cao bảng ổn định khi trang cuối ít người. */}
                {pageCount > 1 &&
                  pageUsers.length < pageSize &&
                  Array.from({ length: pageSize - pageUsers.length }).map((_, i) => (
                    <tr
                      key={`filler-${i}`}
                      className="users__row users__row--filler"
                      aria-hidden="true"
                    >
                      <td colSpan={6}>&nbsp;</td>
                    </tr>
                  ))}
              </>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination. */}
      {filteredUsers.length > 0 && (
        <div className="users__pager">
          <div className="users__pager-left">
            <span className="users__pager-info">
              {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, filteredUsers.length)} trên{" "}
              {filteredUsers.length} người
            </span>
            <div className="users__pager-size">
              <span className="users__pager-info">Hiển thị</span>
              <Select
                ariaLabel="Số dòng mỗi trang"
                value={pageSize}
                onChange={(v) => {
                  setPageSize(v ?? 10);
                  setPage(1);
                }}
                options={[
                  { value: 10, label: "10" },
                  { value: 20, label: "20" },
                  { value: 50, label: "50" },
                ]}
              />
            </div>
          </div>
          <div className="users__pager-controls">
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ‹ Trước
            </button>
            <span className="users__pager-info">
              Trang {page}/{pageCount}
            </span>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page >= pageCount}
              onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
            >
              Sau ›
            </button>
          </div>
        </div>
      )}

      {/* Create-account modal. */}
      <ConfirmDialog
        open={createOpen}
        title="Tạo tài khoản"
        confirmLabel="Tạo tài khoản"
        busy={creating}
        error={createError}
        confirmDisabled={!cName.trim() || !cUsername.trim() || cDept == null}
        onConfirm={onCreate}
        onCancel={() => {
          if (!creating) setCreateOpen(false);
        }}
      >
        <div className="users__form">
          <div className="field">
            <label className="field__label" htmlFor="new-user-name">
              Họ tên <span className="users__req">*</span>
            </label>
            <input
              id="new-user-name"
              className="input"
              placeholder="VD: Nguyễn Văn A"
              value={cName}
              autoFocus
              onChange={(e) => {
                setCName(e.target.value);
                if (createError) setCreateError(null);
              }}
            />
          </div>
          <div className="field">
            <label className="field__label" htmlFor="new-user-username">
              Tên đăng nhập <span className="users__req">*</span>
            </label>
            <input
              id="new-user-username"
              className={`input${createError ? " input--error" : ""}`}
              placeholder="VD: nguyenvana"
              value={cUsername}
              onChange={(e) => {
                setCUsername(e.target.value);
                if (createError) setCreateError(null);
              }}
            />
          </div>
          <div className="field">
            <span className="field__label">
              Phòng ban <span className="users__req">*</span>
            </span>
            <Select
              portal
              ariaLabel="Phòng ban"
              value={cDept}
              placeholder="— Chọn phòng —"
              onChange={(v) => setCDept(v)}
              options={departments.map((d) => ({
                value: d.id,
                label: d.name,
                hint: d.code || undefined,
              }))}
            />
          </div>
          <p className="users__hint">
            Tài khoản mới dùng mật khẩu mặc định và chưa có vai trò — gán vai trò sau khi tạo.
          </p>
        </div>
      </ConfirmDialog>

      {/* User detail / actions modal. */}
      <UserDetailDialog
        open={detailOpen}
        user={current}
        departments={departments}
        token={token}
        currentUserId={me?.id ?? null}
        onClose={() => setDetailOpen(false)}
        onChanged={refresh}
      />
    </main>
  );
}
