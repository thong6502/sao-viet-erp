import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type Department,
  type DepartmentMember,
  type DepartmentSubtreeRow,
  type ModuleDef,
  type PermissionRow,
  type Role,
  type Scope,
  type UnitLevel,
  type UserBrief,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DiscardChangesDialog } from "../components/DiscardChangesDialog";
import { InfoHint } from "../components/InfoHint";
import { Select } from "../components/Select";
import { UnitLevelsDialog } from "../components/UnitLevelsDialog";
import {
  PermissionMatrix,
  defaultMatrix,
  type ActionKey,
} from "../components/PermissionMatrix";
import "./departments.css";

/** Group departments by parent and find the roots, so the list can render as a real tree.
 *  Orphans (parent missing/filtered out) are treated as roots so nothing ever disappears. */
function buildTree(list: Department[]): {
  childrenOf: Map<number, Department[]>;
  roots: Department[];
} {
  const ids = new Set(list.map((d) => d.id));
  const childrenOf = new Map<number, Department[]>();
  const roots: Department[] = [];
  for (const d of list) {
    const parent = d.parent_id ?? null;
    if (parent != null && ids.has(parent)) {
      const bucket = childrenOf.get(parent);
      if (bucket) bucket.push(d);
      else childrenOf.set(parent, [d]);
    } else {
      roots.push(d);
    }
  }
  return { childrenOf, roots };
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
  const can = useCan();
  const canCreateDept = can("phong_ban", "create");
  const canUpdateDept = can("phong_ban", "update");
  const canDeleteDept = can("phong_ban", "delete");
  const canCreateRole = can("vai_tro", "create");
  const canUpdateRole = can("vai_tro", "update");
  const canDeleteRole = can("vai_tro", "delete");
  const canTransfer = can("nguoi_dung", "update");

  const [departments, setDepartments] = useState<Department[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [members, setMembers] = useState<DepartmentMember[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [modules, setModules] = useState<ModuleDef[]>([]);
  // Org tiers (spec-06 / PBI-4009) + who may head the selected unit (its subtree, PBI-4004).
  const [levels, setLevels] = useState<UnitLevel[]>([]);
  const [headCandidates, setHeadCandidates] = useState<UserBrief[]>([]);
  const [levelsOpen, setLevelsOpen] = useState(false);
  // "Thông tin phòng" edit form now opens in a modal instead of expanding inline.
  const [infoOpen, setInfoOpen] = useState(false);
  // Warn before discarding unsaved edits when closing the modal.
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  // Collapsed branches in the cha–con tree (by parent department id).
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

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

  // Bulk transfer (PBI-4008): tick members + pick a target department.
  const [selectedMemberIds, setSelectedMemberIds] = useState<Set<number>>(new Set());
  const [transferTarget, setTransferTarget] = useState<number | null>(null);
  const [transferBusy, setTransferBusy] = useState(false);
  const [transferError, setTransferError] = useState<string | null>(null);
  // Staff list: search + status filter + pagination.
  const [memberSearch, setMemberSearch] = useState("");
  const [memberStatusFilter, setMemberStatusFilter] = useState<"all" | "active" | "locked">(
    "all",
  );
  const [memberPage, setMemberPage] = useState(1);

  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editHead, setEditHead] = useState<number | null>(null);
  const [editLevelId, setEditLevelId] = useState<number | null>(null);
  const [editParentId, setEditParentId] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Create (PBI-4002): name + optional description + optional parent + optional level; code is auto.
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newParentId, setNewParentId] = useState<number | null>(null);
  const [newLevelId, setNewLevelId] = useState<number | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  // List view (wireframe): full-width table with KPI stats, search, and filters.
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "complete" | "no_head" | "empty">(
    "all",
  );
  const [levelFilter, setLevelFilter] = useState<number | null>(null);
  // Staff-count range (wireframe): blank bound = open-ended. Kept as strings for the inputs.
  const [staffMin, setStaffMin] = useState("");
  const [staffMax, setStaffMax] = useState("");

  // Delete (PBI-4005): confirm shows the whole branch that will be removed.
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [subtree, setSubtree] = useState<DepartmentSubtreeRow[] | null>(null);
  const [subtreeLoading, setSubtreeLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const currentDept = departments.find((d) => d.id === selectedId) ?? null;
  const { childrenOf, roots } = useMemo(() => buildTree(departments), [departments]);
  const byId = useMemo(() => new Map(departments.map((d) => [d.id, d])), [departments]);
  // Units that can't be the selected unit's parent: itself + all its descendants (no cycles).
  const excludedParentIds = useMemo(() => {
    const ids = new Set<number>();
    if (selectedId == null) return ids;
    const walk = (id: number) => {
      ids.add(id);
      for (const c of childrenOf.get(id) ?? []) walk(c.id);
    };
    walk(selectedId);
    return ids;
  }, [selectedId, childrenOf]);

  // A department's staffing status (wireframe): no staff → trống; staff but no head → thiếu TP.
  function deptStatus(d: Department): "empty" | "no_head" | "complete" {
    if ((d.user_count ?? 0) === 0) return "empty";
    if (d.head_user_id == null) return "no_head";
    return "complete";
  }

  const stats = useMemo(() => {
    let staff = 0;
    let noHead = 0;
    let empty = 0;
    for (const d of departments) {
      staff += d.user_count ?? 0;
      const s = deptStatus(d);
      if (s === "no_head") noHead += 1;
      if (s === "empty") empty += 1;
    }
    return { count: departments.length, staff, noHead, empty };
  }, [departments]);

  const filtersActive =
    search.trim() !== "" ||
    statusFilter !== "all" ||
    levelFilter != null ||
    staffMin.trim() !== "" ||
    staffMax.trim() !== "";

  function matchesFilters(d: Department): boolean {
    const q = search.trim().toLowerCase();
    if (q) {
      const hay = `${d.code ?? ""} ${d.name} ${d.head_name ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (statusFilter !== "all" && deptStatus(d) !== statusFilter) return false;
    if (levelFilter != null && d.level_id !== levelFilter) return false;
    const count = d.user_count ?? 0;
    const min = staffMin.trim() === "" ? null : Number(staffMin);
    const max = staffMax.trim() === "" ? null : Number(staffMax);
    if (min != null && !Number.isNaN(min) && count < min) return false;
    if (max != null && !Number.isNaN(max) && count > max) return false;
    return true;
  }

  // Rows to render: a flat filtered list while searching/filtering, else the collapsible tree.
  const listRows = useMemo(() => {
    if (filtersActive) {
      return departments
        .filter(matchesFilters)
        .map((d) => ({ dept: d, depth: 0, hasKids: false }));
    }
    const rows: { dept: Department; depth: number; hasKids: boolean }[] = [];
    const walk = (d: Department, depth: number) => {
      const kids = childrenOf.get(d.id) ?? [];
      rows.push({ dept: d, depth, hasKids: kids.length > 0 });
      if (!collapsed.has(d.id)) for (const c of kids) walk(c, depth + 1);
    };
    for (const r of roots) walk(r, 0);
    return rows;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [departments, roots, childrenOf, collapsed, filtersActive, search, statusFilter, levelFilter, staffMin, staffMax]);

  function resetFilters() {
    setSearch("");
    setStatusFilter("all");
    setLevelFilter(null);
    setStaffMin("");
    setStaffMax("");
  }

  // Staff list, filtered + paginated (search by name/username/role, filter by lock status).
  const [memberPageSize, setMemberPageSize] = useState(8);
  const filteredMembers = useMemo(() => {
    const q = memberSearch.trim().toLowerCase();
    return members.filter((m) => {
      if (memberStatusFilter === "active" && !m.is_active) return false;
      if (memberStatusFilter === "locked" && m.is_active) return false;
      if (q) {
        const hay = `${m.name} ${m.username} ${m.role_name ?? ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [members, memberSearch, memberStatusFilter]);
  const memberPageCount = Math.max(1, Math.ceil(filteredMembers.length / memberPageSize));
  const pageMembers = filteredMembers.slice(
    (memberPage - 1) * memberPageSize,
    memberPage * memberPageSize,
  );
  useEffect(() => {
    if (memberPage > memberPageCount) setMemberPage(memberPageCount);
  }, [memberPage, memberPageCount]);

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
      api.rbac.unitLevels(token).catch(() => [] as UnitLevel[]),
    ])
      .then(([list, mods, lvls]) => {
        if (cancelled) return;
        setDepartments(list);
        setModules(mods);
        setLevels(lvls);
        setSelectedId(null); // start on the list; click a department to configure it
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
    setInfoOpen(false);
    setConfirmDiscard(false);
    setAddRoleOpen(false);
    setEditRoleOpen(false);
    setSubtree(null);
    setDeleteError(null);
    setSaveError(null);
    setDirty(false);
    setSelectedMemberIds(new Set());
    setTransferTarget(null);
    setTransferError(null);
    setMemberSearch("");
    setMemberStatusFilter("all");
    setMemberPage(1);
    const dept = departments.find((d) => d.id === selectedId) ?? null;
    setEditName(dept?.name ?? "");
    setEditDescription(dept?.description ?? "");
    setEditHead(dept?.head_user_id ?? null);
    setEditLevelId(dept?.level_id ?? null);
    setEditParentId(dept?.parent_id ?? null);
    if (!token || selectedId == null) {
      setMembers([]);
      setRoles([]);
      setHeadCandidates([]);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);
    Promise.all([
      api.rbac.departmentUsers(token, selectedId),
      api.rbac.roles(token, selectedId),
      api.rbac.headCandidates(token, selectedId).catch(() => [] as UserBrief[]),
    ])
      .then(([ms, rs, cands]) => {
        if (cancelled) return;
        setMembers(ms);
        setRoles(rs);
        setHeadCandidates(cands);
      })
      .catch(() => {
        if (cancelled) return;
        setMembers([]);
        setRoles([]);
        setHeadCandidates([]);
        setDetailError("Không tải được nhân sự / vai trò của phòng.");
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
    // Keep the open department if it still exists; otherwise fall back to the list view.
    if (keepId != null && list.some((d) => d.id === keepId)) setSelectedId(keepId);
    else setSelectedId(null);
  }

  // Open the "Thông tin phòng" edit modal, seeding the form from the current department.
  function openInfoEdit() {
    setEditName(currentDept?.name ?? "");
    setEditDescription(currentDept?.description ?? "");
    setEditHead(currentDept?.head_user_id ?? null);
    setEditLevelId(currentDept?.level_id ?? null);
    setEditParentId(currentDept?.parent_id ?? null);
    setSaveError(null);
    setDirty(false);
    setInfoOpen(true);
  }

  const parentName = (id: number | null | undefined) =>
    id == null ? null : byId.get(id)?.name ?? null;

  function toggleMember(id: number) {
    setSelectedMemberIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setTransferError(null);
  }

  async function doTransfer() {
    if (!token || transferTarget == null || selectedMemberIds.size === 0 || transferBusy) return;
    setTransferBusy(true);
    setTransferError(null);
    try {
      await api.rbac.transferUsers(token, [...selectedMemberIds], transferTarget);
      setSelectedMemberIds(new Set());
      setTransferTarget(null);
      // Reload this department's members + the tree counts.
      if (selectedId != null) {
        const [ms, cands] = await Promise.all([
          api.rbac.departmentUsers(token, selectedId),
          api.rbac.headCandidates(token, selectedId).catch(() => [] as UserBrief[]),
        ]);
        setMembers(ms);
        setHeadCandidates(cands);
      }
      await refresh(selectedId);
    } catch (err) {
      if (err instanceof ApiError && err.isForbidden)
        setTransferError("Bạn không có quyền chuyển nhân sự.");
      else setTransferError("Không chuyển được nhân sự. Vui lòng thử lại.");
    } finally {
      setTransferBusy(false);
    }
  }

  function toggleCollapse(id: number) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function openCreate() {
    setNewName("");
    setNewDescription("");
    setNewParentId(null);
    setNewLevelId(null);
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
        newLevelId,
      );
      setCreateOpen(false);
      await refresh(dept.id);
    } catch (err) {
      if (err instanceof ApiError && (err.isConflict || err.status === 400))
        setCreateError(err.message);
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
        editLevelId,
        editParentId,
      );
      await refresh(selectedId);
      setDirty(false);
      setInfoOpen(false);
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

  /** One row of the department table (wireframe): tree caret + code/name, counts, head,
   *  status badge. Clicking the row opens that department's config; the caret only toggles. */
  function renderRow({
    dept: d,
    depth,
    hasKids,
  }: {
    dept: Department;
    depth: number;
    hasKids: boolean;
  }) {
    const isCollapsed = collapsed.has(d.id);
    const status = deptStatus(d);
    const statusMeta = {
      complete: { label: "Đầy đủ", cls: "is-ok" },
      no_head: { label: "Thiếu TP", cls: "is-warn" },
      empty: { label: "Phòng trống", cls: "is-empty" },
    }[status];
    return (
      <div
        key={d.id}
        className="deptbl__row"
        role="button"
        tabIndex={0}
        onClick={() => setSelectedId(d.id)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setSelectedId(d.id);
          }
        }}
      >
        <div className="deptbl__cell deptbl__cell--name" style={{ paddingLeft: depth * 22 }}>
          {hasKids ? (
            <button
              type="button"
              className={`deptbl__toggle${isCollapsed ? "" : " is-open"}`}
              aria-label={isCollapsed ? "Mở rộng" : "Thu gọn"}
              aria-expanded={!isCollapsed}
              onClick={(e) => {
                e.stopPropagation();
                toggleCollapse(d.id);
              }}
            >
              <span className="deptbl__caret" aria-hidden="true">▸</span>
            </button>
          ) : (
            <span className="deptbl__toggle deptbl__toggle--leaf" aria-hidden="true" />
          )}
          {d.code && <span className="depts__code">{d.code}</span>}
          <span className="deptbl__name">{d.name}</span>
        </div>
        <div className="deptbl__cell deptbl__num">{d.user_count ?? 0}</div>
        <div className="deptbl__cell deptbl__num">{d.role_count ?? 0}</div>
        <div className="deptbl__cell deptbl__head">{d.head_name ?? "Chưa có"}</div>
        <div className="deptbl__cell">
          <span className={`deptbl__status ${statusMeta.cls}`}>{statusMeta.label}</span>
        </div>
      </div>
    );
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
            Quản lý cơ cấu phòng ban, nhân sự và vai trò trong từng phòng.
          </p>
        </div>
        <div className="depts__head-actions">
          <Button type="button" variant="ghost" onClick={() => setLevelsOpen(true)}>
            Cấp đơn vị
          </Button>
          {canCreateDept && (
            <Button type="button" variant="accent" onClick={openCreate}>
              + Tạo phòng ban
            </Button>
          )}
        </div>
      </header>

      {selectedId != null && currentDept ? (
        <section className="depts__detail depts__detail--full">
          <div className="depts__detail-bar">
            <button
              type="button"
              className="btn btn--ghost depts__back"
              onClick={() => setSelectedId(null)}
            >
              ← Danh sách phòng ban
            </button>
          </div>

              {/* Identity masthead + quick delete. */}
              <div className="card depts__id">
                <div className="depts__id-lead">
                  <div className="depts__id-avatar" aria-hidden="true">
                    {initials(currentDept.name)}
                  </div>
                  <div className="depts__id-main">
                    <div className="depts__id-line">
                      {currentDept.code && <span className="depts__code">{currentDept.code}</span>}
                      <h2 className="depts__id-name">{currentDept.name}</h2>
                    </div>
                    <p className="depts__id-meta">
                      {levels.find((l) => l.id === currentDept.level_id)?.name ?? "Chưa gán cấp"}
                      {" · "}
                      {parentName(currentDept.parent_id)
                        ? `Thuộc ${parentName(currentDept.parent_id)}`
                        : "Phòng gốc"}
                      {" · "}
                      {roles.length} vai trò · {members.length} người
                    </p>
                    {(childrenOf.get(currentDept.id)?.length ?? 0) > 0 && (
                      <p className="depts__id-branch">
                        Gồm cả nhánh con: {currentDept.total_role_count ?? roles.length} vai trò ·{" "}
                        {currentDept.total_user_count ?? members.length} người
                      </p>
                    )}
                  </div>
                </div>
                <div className="depts__id-actions">
                  {canUpdateDept && (
                    <Button type="button" variant="primary" onClick={openInfoEdit}>
                      Chỉnh sửa
                    </Button>
                  )}
                  {canDeleteDept && (
                    <button
                      type="button"
                      className="btn btn--ghost depts__danger-text"
                      onClick={openDeleteConfirm}
                    >
                      Xóa phòng
                    </button>
                  )}
                </div>
              </div>

              {/* Thông tin phòng — chỉnh sửa trong modal (mở từ nút "Chỉnh sửa" ở masthead). */}
              <ConfirmDialog
                open={infoOpen}
                title="Chỉnh sửa phòng"
                wide
                confirmLabel="Lưu thay đổi"
                busy={saving}
                error={saveError}
                confirmDisabled={!editName.trim() || !dirty}
                onConfirm={doSave}
                onCancel={() => {
                  if (saving) return;
                  if (dirty) setConfirmDiscard(true);
                  else setInfoOpen(false);
                }}
              >
                <div className="depts__form-grid">
                <div className="field depts__field--full">
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
                      if (saveError) setSaveError(null);
                    }}
                  />
                </div>

                <div className="field depts__field--full">
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
                    }}
                  />
                </div>

                <div className="field">
                  <span className="field__label depts__label">
                    Trực thuộc
                    <InfoHint label="Đơn vị cha trong sơ đồ tổ chức. Không thể chọn chính nó hoặc đơn vị con/cháu (tránh vòng lặp)." />
                  </span>
                  <Select
                    portal
                    ariaLabel="Trực thuộc"
                    value={editParentId}
                    placeholder="— Không (phòng gốc) —"
                    onChange={(v) => {
                      setEditParentId(v);
                      setDirty(true);
                      if (saveError) setSaveError(null);
                    }}
                    options={[
                      { value: null, label: "— Không (phòng gốc) —" },
                      ...departments
                        .filter((d) => !excludedParentIds.has(d.id))
                        .map((d) => ({ value: d.id, label: d.name, hint: d.code || undefined })),
                    ]}
                  />
                </div>

                <div className="field">
                  <span className="field__label depts__label">
                    Cấp đơn vị
                    <InfoHint label="Tầng trong cơ cấu (Khối · Phòng · Tổ). Quyết định nhãn chức danh người đứng đầu; cấp con phải thấp hơn cấp cha." />
                  </span>
                  <Select
                    portal
                    ariaLabel="Cấp đơn vị"
                    value={editLevelId}
                    placeholder="— Chưa gán cấp —"
                    onChange={(v) => {
                      setEditLevelId(v);
                      setDirty(true);
                      if (saveError) setSaveError(null);
                    }}
                    options={[
                      { value: null, label: "— Chưa gán cấp —" },
                      ...levels.map((lv) => ({
                        value: lv.id,
                        label: lv.name,
                        hint: lv.head_title || undefined,
                      })),
                    ]}
                  />
                </div>

                <div className="field depts__field--full">
                  <span className="field__label depts__label">
                    {currentDept.head_title || "Người đứng đầu"}
                    <InfoHint label="Người phụ trách đơn vị. Chỉ chọn được người thuộc phòng này hoặc đơn vị con của nó." />
                  </span>
                  <Select
                    portal
                    ariaLabel="Người đứng đầu"
                    value={editHead}
                    disabled={headCandidates.length === 0}
                    placeholder="— Chưa chỉ định —"
                    onChange={(v) => {
                      setEditHead(v);
                      setDirty(true);
                    }}
                    options={[
                      { value: null, label: "— Chưa chỉ định —" },
                      ...headCandidates.map((u) => ({
                        value: u.id,
                        label: u.name,
                        hint: `@${u.username}`,
                      })),
                    ]}
                  />
                  {headCandidates.length === 0 && (
                    <span className="depts__hint">
                      Chưa có người trong phòng hoặc nhánh con — thêm ở màn Người dùng trước.
                    </span>
                  )}
                </div>
                </div>

              </ConfirmDialog>

              {/* Cảnh báo khi thoát modal chỉnh sửa mà còn thay đổi chưa lưu. */}
              <DiscardChangesDialog
                open={confirmDiscard}
                onDiscard={() => {
                  setConfirmDiscard(false);
                  setInfoOpen(false);
                }}
                onKeepEditing={() => setConfirmDiscard(false)}
              />

              {/* Vai trò trong phòng — đặt TRÊN danh sách nhân sự cho dễ thao tác. */}
              <div className="card depts__section">
                <div className="depts__section-head">
                  <div className="depts__eyebrow-row">
                    <p className="eyebrow">Vai trò trong phòng</p>
                    <InfoHint
                      label={
                        canUpdateRole
                          ? "Các vai trò định nghĩa riêng cho phòng này. Bấm một vai trò để sửa quyền hoặc xóa."
                          : "Các vai trò định nghĩa riêng cho phòng này."
                      }
                    />
                  </div>
                  {canCreateRole && (
                    <Button type="button" variant="ghost" onClick={openAddRole}>
                      + Thêm vai trò
                    </Button>
                  )}
                </div>
                {detailLoading ? (
                  <p className="depts__status">Đang tải…</p>
                ) : roles.length === 0 ? (
                  <p className="depts__hint">
                    {canCreateRole
                      ? "Chưa có vai trò. Bấm “+ Thêm vai trò” để tạo."
                      : "Phòng này chưa có vai trò."}
                  </p>
                ) : (
                  <div className="depts__chips">
                    {roles.map((r) =>
                      // Chỉ người có quyền sửa vai trò mới mở được popup chi tiết/ma trận quyền;
                      // người chỉ xem thấy tên vai trò dưới dạng chip tĩnh (không bấm được).
                      canUpdateRole ? (
                        <button
                          key={r.id}
                          type="button"
                          className="depts__chip depts__chip--btn"
                          onClick={() => openEditRole(r)}
                        >
                          {r.name}
                        </button>
                      ) : (
                        <span key={r.id} className="depts__chip">
                          {r.name}
                        </span>
                      ),
                    )}
                  </div>
                )}
              </div>

              {/* Nhân sự trong phòng — tìm kiếm · lọc · chuyển hàng loạt · phân trang. */}
              <div className="card depts__section">
                <div className="depts__section-head">
                  <div className="depts__eyebrow-row">
                    <p className="eyebrow">Nhân sự trong phòng</p>
                    <InfoHint
                      label={
                        canTransfer
                          ? "Người thuộc phòng này. Tích chọn nhiều người rồi chọn phòng đích để chuyển hàng loạt."
                          : "Người thuộc phòng này."
                      }
                    />
                  </div>
                  <span className="depts__count-pill">{members.length}</span>
                </div>
                {detailLoading ? (
                  <p className="depts__status">Đang tải…</p>
                ) : detailError ? (
                  <span className="depts__inline-error" role="alert">
                    {detailError}
                  </span>
                ) : members.length === 0 ? (
                  <p className="depts__hint">
                    Phòng chưa có nhân sự. Thêm người ở màn “Người dùng”.
                  </p>
                ) : (
                  <>
                    {/* Toolbar: tìm kiếm + lọc trạng thái. */}
                    <div className="depts__staff-toolbar">
                      <input
                        className="input depts__staff-search"
                        placeholder="Tìm theo tên, tên đăng nhập, vai trò…"
                        value={memberSearch}
                        onChange={(e) => {
                          setMemberSearch(e.target.value);
                          setMemberPage(1);
                        }}
                        aria-label="Tìm nhân sự"
                      />
                      <div className="depts__staff-filter">
                        <Select
                          ariaLabel="Lọc trạng thái nhân sự"
                          value={memberStatusFilter}
                          onChange={(v) => {
                            setMemberStatusFilter(v);
                            setMemberPage(1);
                          }}
                          options={[
                            { value: "all", label: "Tất cả trạng thái" },
                            { value: "active", label: "Đang hoạt động" },
                            { value: "locked", label: "Đã khóa" },
                          ]}
                        />
                      </div>
                    </div>

                    {/* Thanh chuyển hàng loạt — hiện Ở TRÊN danh sách khi có người được chọn.
                        Chỉ dành cho người có quyền chuyển nhân sự (checkbox cũng đã ẩn). */}
                    {canTransfer && selectedMemberIds.size > 0 && (
                      <div className="depts__transfer">
                        <span className="depts__transfer-count">
                          Đã chọn {selectedMemberIds.size} người · chuyển sang
                        </span>
                        <div className="depts__transfer-select">
                          <Select
                            ariaLabel="Phòng đích"
                            value={transferTarget}
                            placeholder="— Chọn phòng đích —"
                            onChange={(v) => setTransferTarget(v)}
                            options={[
                              { value: null, label: "— Chọn phòng đích —" },
                              ...departments
                                .filter((d) => d.id !== selectedId)
                                .map((d) => ({
                                  value: d.id,
                                  label: d.name,
                                  hint: d.code || undefined,
                                })),
                            ]}
                          />
                        </div>
                        <Button
                          type="button"
                          variant="accent"
                          loading={transferBusy}
                          disabled={transferTarget == null || !canTransfer}
                          onClick={doTransfer}
                        >
                          Chuyển
                        </Button>
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() => setSelectedMemberIds(new Set())}
                        >
                          Bỏ chọn
                        </button>
                      </div>
                    )}
                    {transferError && (
                      <span className="depts__inline-error" role="alert">
                        {transferError}
                      </span>
                    )}
                    {canTransfer && selectedMemberIds.size > 0 && (
                      <p className="depts__hint">
                        Vai trò cũ sẽ bị gỡ sau khi chuyển; trưởng phòng mới gán lại.
                      </p>
                    )}

                    {/* Danh sách (trang hiện tại). */}
                    {filteredMembers.length === 0 ? (
                      <p className="depts__hint">Không có nhân sự khớp tìm kiếm.</p>
                    ) : (
                      <ul
                        className="depts__members"
                        style={
                          memberPageCount > 1 ? { minHeight: memberPageSize * 54 } : undefined
                        }
                      >
                        {pageMembers.map((m) => (
                          <li key={m.id} className="depts__member">
                            {canTransfer && (
                              <input
                                type="checkbox"
                                className="depts__member-check"
                                checked={selectedMemberIds.has(m.id)}
                                onChange={() => toggleMember(m.id)}
                                aria-label={`Chọn ${m.name} để chuyển`}
                              />
                            )}
                            <span className="depts__member-avatar" aria-hidden="true">
                              {initials(m.name)}
                            </span>
                            <span className="depts__member-main">
                              <span className="depts__member-line">
                                <span className="depts__member-name">{m.name}</span>
                                {m.is_head && (
                                  <span className="depts__badge depts__badge--head">Trưởng phòng</span>
                                )}
                                {!m.is_active && (
                                  <span className="depts__badge depts__badge--locked">Đã khóa</span>
                                )}
                              </span>
                              <span className="depts__member-meta">
                                <span className="depts__member-user">@{m.username}</span>
                                <span className="depts__member-role">
                                  {m.role_name ?? "Chưa gán vai trò"}
                                </span>
                              </span>
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}

                    {/* Phân trang — luôn hiện khi có nhân sự. */}
                    {filteredMembers.length > 0 && (
                      <div className="depts__pager">
                        <div className="depts__pager-left">
                          <span className="depts__pager-info">
                            {(memberPage - 1) * memberPageSize + 1}–
                            {Math.min(memberPage * memberPageSize, filteredMembers.length)} trên{" "}
                            {filteredMembers.length} người
                          </span>
                          <div className="depts__pager-size">
                            <span className="depts__pager-info">Hiển thị</span>
                            <Select
                              ariaLabel="Số dòng mỗi trang"
                              value={memberPageSize}
                              onChange={(v) => {
                                setMemberPageSize(v ?? 8);
                                setMemberPage(1);
                              }}
                              options={[
                                { value: 8, label: "8" },
                                { value: 16, label: "16" },
                                { value: 32, label: "32" },
                                { value: 50, label: "50" },
                              ]}
                            />
                          </div>
                        </div>
                        <div className="depts__pager-controls">
                          <button
                            type="button"
                            className="btn btn--ghost"
                            disabled={memberPage <= 1}
                            onClick={() => setMemberPage((p) => Math.max(1, p - 1))}
                          >
                            ‹ Trước
                          </button>
                          <span className="depts__pager-info">
                            Trang {memberPage}/{memberPageCount}
                          </span>
                          <button
                            type="button"
                            className="btn btn--ghost"
                            disabled={memberPage >= memberPageCount}
                            onClick={() => setMemberPage((p) => Math.min(memberPageCount, p + 1))}
                          >
                            Sau ›
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
        </section>
      ) : (
        <section className="depts__listview" aria-label="Danh sách phòng ban">
          {/* KPI stats. */}
          <div className="deptbl__stats">
            <div className="deptbl__stat">
              <span className="deptbl__stat-num">{stats.count}</span>
              <span className="deptbl__stat-label">phòng ban</span>
            </div>
            <div className="deptbl__stat">
              <span className="deptbl__stat-num">{stats.staff}</span>
              <span className="deptbl__stat-label">nhân sự</span>
            </div>
            <div className="deptbl__stat deptbl__stat--warn">
              <span className="deptbl__stat-num">{stats.noHead}</span>
              <span className="deptbl__stat-label">thiếu trưởng phòng</span>
            </div>
            <div className="deptbl__stat">
              <span className="deptbl__stat-num">{stats.empty}</span>
              <span className="deptbl__stat-label">phòng trống</span>
            </div>
          </div>

          {/* Search + filters. */}
          <div className="deptbl__toolbar">
            <input
              className="input deptbl__search"
              placeholder="Tìm theo tên phòng, mã phòng, người đứng đầu…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Tìm phòng ban"
            />
            <div className="deptbl__filters">
              <div className="deptbl__filter">
                <Select
                  ariaLabel="Lọc theo trạng thái"
                  value={statusFilter}
                  onChange={(v) => setStatusFilter(v)}
                  options={[
                    { value: "all", label: "Tất cả trạng thái" },
                    { value: "complete", label: "Đầy đủ" },
                    { value: "no_head", label: "Thiếu trưởng phòng" },
                    { value: "empty", label: "Phòng trống" },
                  ]}
                />
              </div>
              <div className="deptbl__filter">
                <Select
                  ariaLabel="Lọc theo cấp đơn vị"
                  value={levelFilter}
                  placeholder="Tất cả cấp"
                  onChange={(v) => setLevelFilter(v)}
                  options={[
                    { value: null, label: "Tất cả cấp" },
                    ...levels.map((lv) => ({ value: lv.id, label: lv.name })),
                  ]}
                />
              </div>
              <div className="deptbl__staff">
                <span className="deptbl__staff-label">Nhân sự:</span>
                <input
                  className="input deptbl__staff-input"
                  type="number"
                  min={0}
                  placeholder="từ"
                  value={staffMin}
                  onChange={(e) => setStaffMin(e.target.value)}
                  aria-label="Số nhân sự tối thiểu"
                />
                <span className="deptbl__staff-dash">–</span>
                <input
                  className="input deptbl__staff-input"
                  type="number"
                  min={0}
                  placeholder="đến"
                  value={staffMax}
                  onChange={(e) => setStaffMax(e.target.value)}
                  aria-label="Số nhân sự tối đa"
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
          {departments.length === 0 ? (
            <div className="depts__empty">
              <p className="depts__empty-title">Chưa có phòng ban</p>
              <p className="depts__hint">
                {canCreateDept
                  ? "Bấm “Tạo phòng ban” để thêm phòng đầu tiên."
                  : "Chưa có phòng ban nào để xem."}
              </p>
            </div>
          ) : (
            <div className="deptbl" role="table">
              <div className="deptbl__row deptbl__row--head" role="row">
                <div className="deptbl__cell deptbl__cell--name">Phòng ban</div>
                <div className="deptbl__cell deptbl__num">Nhân sự</div>
                <div className="deptbl__cell deptbl__num">Vai trò</div>
                <div className="deptbl__cell deptbl__head">Trưởng phòng</div>
                <div className="deptbl__cell">Trạng thái</div>
              </div>
              {listRows.length === 0 ? (
                <p className="depts__hint deptbl__none">Không có phòng ban khớp bộ lọc.</p>
              ) : (
                listRows.map(renderRow)
              )}
            </div>
          )}
          <p className="depts__hint deptbl__tip">
            Gợi ý: bấm vào một phòng ban để xem và cấu hình chi tiết.
          </p>
        </section>
      )}

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
            <span className="field__label">Trực thuộc</span>
            <Select
              portal
              ariaLabel="Trực thuộc"
              value={newParentId}
              placeholder="— Không (phòng gốc) —"
              onChange={(v) => setNewParentId(v)}
              options={[
                { value: null, label: "— Không (phòng gốc) —" },
                ...departments.map((d) => ({
                  value: d.id,
                  label: d.name,
                  hint: d.code || undefined,
                })),
              ]}
            />
          </div>

          <div className="field">
            <span className="field__label">Cấp đơn vị</span>
            <Select
              portal
              ariaLabel="Cấp đơn vị"
              value={newLevelId}
              placeholder="— Chưa gán cấp —"
              onChange={(v) => setNewLevelId(v)}
              options={[
                { value: null, label: "— Chưa gán cấp —" },
                ...levels.map((lv) => ({
                  value: lv.id,
                  label: lv.name,
                  hint: lv.head_title || undefined,
                })),
              ]}
            />
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

      {/* Edit a role in this department: its name + permission matrix.
          Không có quyền sửa → mở ở chế độ chỉ xem (input khóa, ma trận khóa, không nút Lưu). */}
      <ConfirmDialog
        open={editRoleOpen}
        title={canUpdateRole ? "Sửa vai trò" : "Chi tiết vai trò (chỉ xem)"}
        confirmLabel="Lưu"
        cancelLabel={canUpdateRole ? "Hủy" : "Đóng"}
        wide
        busy={editRoleBusy}
        error={editRoleError}
        confirmDisabled={editRoleLoading || !editRoleName.trim()}
        hideConfirm={!canUpdateRole}
        onConfirm={submitEditRole}
        onCancel={() => {
          if (!editRoleBusy && !editRoleDeleting) setEditRoleOpen(false);
        }}
      >
        <div className="field">
          <label className="field__label" htmlFor="edit-role-name">
            Tên vai trò {canUpdateRole && <span className="depts__req">*</span>}
          </label>
          <input
            id="edit-role-name"
            className={`input${editRoleError ? " input--error" : ""}`}
            value={editRoleName}
            autoFocus={canUpdateRole}
            disabled={!canUpdateRole}
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
              readOnly={!canUpdateRole}
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
          ) : canDeleteRole ? (
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
          ) : null}
        </div>
      </ConfirmDialog>

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

      {/* Danh mục cấp đơn vị (PBI-4009). Refresh levels + departments so head-title labels update. */}
      <UnitLevelsDialog
        open={levelsOpen}
        token={token}
        onClose={() => setLevelsOpen(false)}
        onChanged={() => {
          if (!token) return;
          api.rbac.unitLevels(token).then(setLevels).catch(() => {});
          void refresh(selectedId);
        }}
      />
    </main>
  );
}
