import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type Department,
  type DepartmentMember,
  type DepartmentSalaryRow,
  type DepartmentSalaryRowInput,
  type DepartmentSubtreeRow,
  type EmployeeMeta,
  type SalaryMechanism,
  type ModuleDef,
  type PermissionRow,
  type Role,
  type Scope,
  type UserBrief,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DiscardChangesDialog } from "../components/DiscardChangesDialog";
import { InfoHint } from "../components/InfoHint";
import { Select } from "../components/Select";
import {
  PermissionMatrix,
  defaultMatrix,
  type ActionKey,
} from "../components/PermissionMatrix";
import { EmployeeWizard } from "./NhanSuPage";
import { Icon } from "../components/Icons";
import "./departments.css";
import "./nhan-su.css";
import "./redesign-phong-ban.css";

/** Cơ chế lương của phòng (Pha 1) — nhãn tiếng Việt cho từng kiểu ra mức lương. */
const SALARY_MECHANISM_OPTIONS: { value: SalaryMechanism; label: string }[] = [
  { value: "cung", label: "Lương cứng (ấn định tay từng người)" },
  { value: "bac_tho", label: "Theo bậc thợ (thợ 1/2/3, phụ 1/2)" },
  { value: "tham_nien", label: "Theo thâm niên (số năm làm)" },
  { value: "tham_nien_gioi_tinh", label: "Theo thâm niên + giới tính" },
];

/** Nhãn ngắn cho kiểu áp — hiện trong bảng lương của phòng. */
const APPLY_LABEL: Record<SalaryMechanism, string> = {
  cung: "Lương cứng",
  bac_tho: "Theo bậc thợ",
  tham_nien: "Theo thâm niên",
  tham_nien_gioi_tinh: "Thâm niên + giới tính",
};

const GRADE_OPTIONS = [
  { value: "tho_1", label: "Thợ bậc 1" },
  { value: "tho_2", label: "Thợ bậc 2" },
  { value: "tho_3", label: "Thợ bậc 3" },
  { value: "phu_1", label: "Phụ 1" },
  { value: "phu_2", label: "Phụ 2" },
];
const SENIORITY_BAND_OPTIONS = [
  { value: "lt1", label: "Dưới 1 năm" },
  { value: "y1_5", label: "1–5 năm" },
  { value: "y5_10", label: "5–10 năm" },
  { value: "gt10", label: "Trên 10 năm" },
];
const GENDER_OPTIONS = [
  { value: "male", label: "Nam" },
  { value: "female", label: "Nữ" },
];

function emptySalaryRow(): DepartmentSalaryRowInput {
  return {
    label: "",
    apply_by: "cung",
    pay_grade_key: null,
    seniority_band: null,
    gender: null,
    luong_vi_tri: 0,
    luong_trach_nhiem: 0,
    phu_cap: 0,
    chuyen_can: 0,
  };
}

/** Mô tả điều kiện khớp của một dòng lương (bậc/thâm niên/giới tính), để hiện cạnh cách áp. */
function applyDetail(row: DepartmentSalaryRow): string {
  const label = (opts: { value: string; label: string }[], v?: string | null) =>
    v ? (opts.find((o) => o.value === v)?.label ?? v) : null;
  const parts = [
    label(GRADE_OPTIONS, row.pay_grade_key),
    label(SENIORITY_BAND_OPTIONS, row.seniority_band),
    label(GENDER_OPTIONS, row.gender),
  ].filter(Boolean);
  return parts.length ? ` · ${parts.join(", ")}` : "";
}

/** Mức nền của một dòng = vị trí + trách nhiệm (phụ cấp/chuyên cần khai theo từng NV). */
function salaryRowTotal(r: {
  luong_vi_tri: number;
  luong_trach_nhiem: number;
}): number {
  return r.luong_vi_tri + r.luong_trach_nhiem;
}

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

export function DepartmentsPage({ onDeptChanged }: { onDeptChanged?: () => void } = {}) {
  const { token } = useAuth();
  const can = useCan();
  const canCreateDept = can("phong_ban", "create");
  const canUpdateDept = can("phong_ban", "update");
  const canDeleteDept = can("phong_ban", "delete");
  const canCreateRole = can("vai_tro", "create");
  const canUpdateRole = can("vai_tro", "update");
  const canDeleteRole = can("vai_tro", "delete");
  // Sửa MA TRẬN tách khỏi đổi tên vai trò (chống leo thang quyền): HCNS dựng được chỗ ngồi,
  // chỉ Admin cấp được quyền cho nó. Backend đã gác `PUT /roles/{id}/permissions` bằng cờ này
  // — FE trước đây mở ma trận theo `vai_tro:update` nên bấm Lưu là ăn 403.
  const canManagePerms = can("vai_tro", "manage_permissions");
  // Hộp "Sửa vai trò" gom 2 thứ tách quyền: ĐỔI TÊN (`update`) và MA TRẬN (`manage_permissions`).
  // Có một trong hai là còn nút Lưu; không có cả hai thì mở ở chế độ chỉ xem.
  const canEditRoleAnything = canUpdateRole || canManagePerms;
  // Quyền chi tiết nhóm 1: chuyển phòng + gán vai trò (module Người dùng), đặt trưởng phòng (Phòng ban).
  const canTransfer = can("nguoi_dung", "transfer");
  const canAssignRole = can("nguoi_dung", "assign_role");
  const canBulk = canTransfer || canAssignRole;
  const canSetHead = can("phong_ban", "set_head");
  const canReparent = can("phong_ban", "reparent");
  // Thêm nhân viên NGAY trong màn Phòng ban (tái dùng form Hồ sơ nhân sự — không dựng form mới).
  const canAddEmployee = can("nhan_su", "create");

  const [departments, setDepartments] = useState<Department[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [members, setMembers] = useState<DepartmentMember[]>([]);
  // Mở form Thêm NV vào phòng đang xem; meta (danh sách phòng/vai trò…) nạp 1 lần khi có quyền.
  const [wizardOpen, setWizardOpen] = useState(false);
  const [empMeta, setEmpMeta] = useState<EmployeeMeta | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [modules, setModules] = useState<ModuleDef[]>([]);
  // Who may head the selected unit (its subtree, PBI-4004).
  const [headCandidates, setHeadCandidates] = useState<UserBrief[]>([]);
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

  // Edit-role INLINE (mở bằng cách bấm một chip vai trò): tên + ma trận quyền của vai đó.
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
  // Gán vai trò hàng loạt ngay trong màn Phòng ban (không cần qua màn Người dùng).
  const [assignRoleTarget, setAssignRoleTarget] = useState<number | null>(null);
  const [assignRoleBusy, setAssignRoleBusy] = useState(false);
  const [assignRoleError, setAssignRoleError] = useState<string | null>(null);
  // Popup cảnh báo có đếm ngược 5s cho thao tác hàng loạt (gán vai trò / chuyển phòng).
  const [pendingBulk, setPendingBulk] = useState<null | {
    title: string;
    message: string;
    confirmLabel: string;
    danger?: boolean;
    run: () => void;
  }>(null);
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
  const [editParentId, setEditParentId] = useState<number | null>(null);
  // Thuộc tính lương cấp phòng (Pha 1). Cơ chế đã chuyển sang từng dòng bảng lương.
  const [editHasPieceWork, setEditHasPieceWork] = useState(false);
  // Tỷ lệ thử việc là quy định CHUNG toàn công ty (payroll_params) — chỉ HIỂN THỊ ở form
  // phòng, khai thật ở Lương → Quy tắc lương. null = chưa tải được (thiếu quyền luong).
  const [companyProbationRatio, setCompanyProbationRatio] = useState<
    number | null
  >(null);
  const [editLaSanXuat, setEditLaSanXuat] = useState(false);
  const [dirty, setDirty] = useState(false);
  // Bảng lương của phòng (Pha 1, lát 2).
  const [salaryRows, setSalaryRows] = useState<DepartmentSalaryRow[]>([]);
  // null = đóng; "new" = thêm dòng; object = sửa dòng.
  const [salaryEditing, setSalaryEditing] = useState<
    DepartmentSalaryRow | "new" | null
  >(null);
  const [salaryForm, setSalaryForm] = useState<DepartmentSalaryRowInput>(
    emptySalaryRow(),
  );
  const [salaryBusy, setSalaryBusy] = useState(false);
  const [salaryError, setSalaryError] = useState<string | null>(null);
  const [salaryDeleting, setSalaryDeleting] =
    useState<DepartmentSalaryRow | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Create (PBI-4002): name + optional description + optional parent + optional level; code is auto.
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newParentId, setNewParentId] = useState<number | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  // Cây tổ chức (cột trái) — tìm theo tên/mã + chip lọc phân loại phòng.
  const [search, setSearch] = useState("");
  const [treeFilter, setTreeFilter] = useState<"all" | "san_xuat" | "van_phong" | "no_head">(
    "all",
  );
  // Drawer chi tiết (cột phải): 4 tab progressive-disclosure.
  const [activeTab, setActiveTab] = useState<"overview" | "staff" | "roles" | "salary">(
    "overview",
  );

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
    if ((d.employee_count ?? 0) === 0) return "empty";
    if (d.head_user_id == null) return "no_head";
    return "complete";
  }

  // Đếm cho chip lọc cây: tổng · khối SX · văn phòng · thiếu trưởng.
  const treeStats = useMemo(() => {
    let sanXuat = 0;
    let noHead = 0;
    for (const d of departments) {
      if (d.la_san_xuat) sanXuat += 1;
      if (deptStatus(d) === "no_head") noHead += 1;
    }
    return {
      all: departments.length,
      san_xuat: sanXuat,
      van_phong: departments.length - sanXuat,
      no_head: noHead,
    };
  }, [departments]);

  // Tỷ lệ thử việc chung toàn công ty — chỉ để HIỂN THỊ (read-only) ở form phòng.
  useEffect(() => {
    if (!token) return;
    api.luong
      .getParams(token)
      .then((p) => setCompanyProbationRatio(p.probation_ratio))
      .catch(() => setCompanyProbationRatio(null));
  }, [token]);

  const treeFiltersActive = search.trim() !== "" || treeFilter !== "all";

  function matchesTree(d: Department): boolean {
    const q = search.trim().toLowerCase();
    if (q) {
      const hay = `${d.code ?? ""} ${d.name} ${d.head_name ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (treeFilter === "san_xuat" && !d.la_san_xuat) return false;
    if (treeFilter === "van_phong" && d.la_san_xuat) return false;
    if (treeFilter === "no_head" && deptStatus(d) !== "no_head") return false;
    return true;
  }

  // Hàng cây: khi tìm/lọc → danh sách phẳng khớp; ngược lại → cây cha–con thu gọn được.
  const listRows = useMemo(() => {
    if (treeFiltersActive) {
      return departments
        .filter(matchesTree)
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
  }, [departments, roots, childrenOf, collapsed, treeFiltersActive, search, treeFilter]);

  // Nhân sự của phòng (theo HỒ SƠ), lọc + phân trang. Lọc "Đã khóa" chỉ áp cho người CÓ
  // tài khoản — người chưa có tài khoản không có trạng thái khóa/mở nào để lọc.
  const [memberPageSize, setMemberPageSize] = useState(8);
  const filteredMembers = useMemo(() => {
    const q = memberSearch.trim().toLowerCase();
    return members.filter((m) => {
      if (memberStatusFilter === "active" && m.is_active !== true) return false;
      if (memberStatusFilter === "locked" && m.is_active !== false) return false;
      if (q) {
        const hay = `${m.code ?? ""} ${m.name} ${m.username ?? ""} ${m.position ?? ""} ${m.role_name ?? ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [members, memberSearch, memberStatusFilter]);
  // Gán vai trò chỉ áp cho người CÓ tài khoản → đếm sẵn để nói rõ trong hộp xác nhận.
  const selectedWithAccount = members.filter(
    (m) => selectedMemberIds.has(m.employee_id) && m.user_id != null,
  ).length;
  const selectedWithoutAccount = selectedMemberIds.size - selectedWithAccount;
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
    ])
      .then(([list, mods]) => {
        if (cancelled) return;
        setDepartments(list);
        setModules(mods);
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
    setEditRoleId(null);
    setSubtree(null);
    setDeleteError(null);
    setSaveError(null);
    setDirty(false);
    setSelectedMemberIds(new Set());
    setTransferTarget(null);
    setTransferError(null);
    setAssignRoleTarget(null);
    setAssignRoleError(null);
    setMemberSearch("");
    setMemberStatusFilter("all");
    setMemberPage(1);
    setActiveTab("overview");
    const dept = departments.find((d) => d.id === selectedId) ?? null;
    setEditName(dept?.name ?? "");
    setEditDescription(dept?.description ?? "");
    setEditHead(dept?.head_user_id ?? null);
    setEditParentId(dept?.parent_id ?? null);
    setEditLaSanXuat(dept?.la_san_xuat ?? false);
    if (!token || selectedId == null) {
      setMembers([]);
      setRoles([]);
      setHeadCandidates([]);
      setSalaryRows([]);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);
    Promise.all([
      api.rbac.departmentUsers(token, selectedId),
      api.rbac.roles(token, selectedId),
      api.rbac.headCandidates(token, selectedId).catch(() => [] as UserBrief[]),
      api.rbac
        .listSalaryRows(token, selectedId)
        .catch(() => [] as DepartmentSalaryRow[]),
    ])
      .then(([ms, rs, cands, srows]) => {
        if (cancelled) return;
        setMembers(ms);
        setRoles(rs);
        setHeadCandidates(cands);
        setSalaryRows(srows);
      })
      .catch(() => {
        if (cancelled) return;
        setMembers([]);
        setRoles([]);
        setHeadCandidates([]);
        setSalaryRows([]);
        setDetailError("Không tải được nhân sự / vai trò của phòng.");
      })
      .finally(() => !cancelled && setDetailLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, selectedId]);

  // Meta cho form Thêm nhân viên (danh sách phòng/vai trò/ca…) — nạp 1 lần, chỉ khi có quyền thêm NV.
  useEffect(() => {
    if (!token || !canAddEmployee) return;
    api.employees.meta(token).then(setEmpMeta).catch(() => setEmpMeta(null));
  }, [token, canAddEmployee]);

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
    setEditParentId(currentDept?.parent_id ?? null);
    setEditHasPieceWork(currentDept?.has_piece_work ?? false);
    setEditLaSanXuat(currentDept?.la_san_xuat ?? false);
    setSaveError(null);
    setDirty(false);
    setInfoOpen(true);
  }

  const parentName = (id: number | null | undefined) =>
    id == null ? null : byId.get(id)?.name ?? null;

  // Chuỗi breadcrumb tổ chức từ gốc → cha (không gồm chính phòng đang xem).
  function ancestorTrail(d: Department): string[] {
    const chain: string[] = [];
    const seen = new Set<number>();
    let pid = d.parent_id ?? null;
    while (pid != null && !seen.has(pid)) {
      seen.add(pid);
      const p = byId.get(pid);
      if (!p) break;
      chain.unshift(p.name);
      pid = p.parent_id ?? null;
    }
    return chain;
  }

  function toggleMember(id: number) {
    setSelectedMemberIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setTransferError(null);
    setAssignRoleError(null);
  }

  async function doTransfer() {
    if (!token || transferTarget == null || selectedMemberIds.size === 0 || transferBusy) return;
    setTransferBusy(true);
    setTransferError(null);
    try {
      // Chuyển theo HỒ SƠ → người chưa có tài khoản cũng đi được.
      await api.rbac.transferStaff(token, [...selectedMemberIds], transferTarget);
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

  async function doAssignRole() {
    if (!token || assignRoleTarget == null || selectedMemberIds.size === 0 || assignRoleBusy)
      return;
    setAssignRoleBusy(true);
    setAssignRoleError(null);
    try {
      // Vai trò gắn vào TÀI KHOẢN → chỉ áp cho người đã có tài khoản; người chưa có bị bỏ qua.
      const userIds = members
        .filter((m) => selectedMemberIds.has(m.employee_id) && m.user_id != null)
        .map((m) => m.user_id as number);
      if (userIds.length === 0) {
        setAssignRoleError("Những người đã chọn đều chưa có tài khoản — không gán vai trò được.");
        return;
      }
      await api.rbac.bulkAssignRole(token, userIds, assignRoleTarget);
      setSelectedMemberIds(new Set());
      setAssignRoleTarget(null);
      // Reload members so the new role shows on each row.
      if (selectedId != null) setMembers(await api.rbac.departmentUsers(token, selectedId));
    } catch (err) {
      if (err instanceof ApiError && err.isForbidden)
        setAssignRoleError("Bạn không có quyền gán vai trò.");
      else if (err instanceof ApiError && err.status === 400)
        setAssignRoleError("Vai trò không hợp lệ với phòng này.");
      else setAssignRoleError("Không gán được vai trò. Vui lòng thử lại.");
    } finally {
      setAssignRoleBusy(false);
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
        null, // cấp đơn vị đã gỡ khỏi form tạo phòng
      );
      setCreateOpen(false);
      await refresh(dept.id);
      // Phòng mới có thể nằm dưới cây SX (thừa hưởng cờ) → cập nhật menu con tổ ở navbar.
      onDeptChanged?.();
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
        currentDept?.level_id ?? null, // cấp đơn vị đã gỡ khỏi UI; giữ nguyên giá trị cũ
        editParentId,
        {
          salary_mechanism: currentDept?.salary_mechanism ?? "cung",
          probation_ratio: currentDept?.probation_ratio ?? 0.8,
          has_piece_work: editHasPieceWork,
        },
        editLaSanXuat,
      );
      await refresh(selectedId);
      setDirty(false);
      setInfoOpen(false);
      // Tick/bỏ cờ `la_san_xuat` (hoặc đổi cây cha) → menu con tổ ở navbar nhảy NGAY.
      onDeptChanged?.();
    } catch (err) {
      if (err instanceof ApiError && (err.isConflict || err.status === 400)) setSaveError(err.message);
      else setSaveError("Lưu thất bại. Vui lòng thử lại.");
    } finally {
      setSaving(false);
    }
  }

  // --- Bảng lương của phòng (Pha 1, lát 2) ---------------------------------
  async function reloadSalaryRows() {
    if (!token || selectedId == null) return;
    try {
      setSalaryRows(await api.rbac.listSalaryRows(token, selectedId));
    } catch {
      /* giữ danh sách hiện tại nếu tải lại lỗi */
    }
  }
  function openSalaryAdd() {
    setSalaryForm(emptySalaryRow());
    setSalaryError(null);
    setSalaryEditing("new");
  }
  function openSalaryEdit(row: DepartmentSalaryRow) {
    setSalaryForm({
      label: row.label,
      apply_by: row.apply_by,
      pay_grade_key: row.pay_grade_key ?? null,
      seniority_band: row.seniority_band ?? null,
      gender: row.gender ?? null,
      luong_vi_tri: row.luong_vi_tri,
      luong_trach_nhiem: row.luong_trach_nhiem,
      phu_cap: row.phu_cap,
      chuyen_can: row.chuyen_can,
    });
    setSalaryError(null);
    setSalaryEditing(row);
  }
  async function saveSalaryRow() {
    if (!token || selectedId == null || !salaryForm.label.trim() || salaryBusy)
      return;
    setSalaryBusy(true);
    setSalaryError(null);
    // Chuẩn hóa: chiều không dùng theo kiểu áp thì để trống.
    const payload: DepartmentSalaryRowInput = {
      ...salaryForm,
      label: salaryForm.label.trim(),
      pay_grade_key:
        salaryForm.apply_by === "bac_tho" ? salaryForm.pay_grade_key : null,
      seniority_band:
        salaryForm.apply_by === "tham_nien" ||
        salaryForm.apply_by === "tham_nien_gioi_tinh"
          ? salaryForm.seniority_band
          : null,
      gender:
        salaryForm.apply_by === "tham_nien_gioi_tinh" ? salaryForm.gender : null,
    };
    try {
      if (salaryEditing === "new")
        await api.rbac.createSalaryRow(token, selectedId, payload);
      else if (salaryEditing)
        await api.rbac.updateSalaryRow(token, salaryEditing.id, payload);
      setSalaryEditing(null);
      await reloadSalaryRows();
    } catch (err) {
      setSalaryError(
        err instanceof ApiError ? err.message : "Lưu dòng lương thất bại.",
      );
    } finally {
      setSalaryBusy(false);
    }
  }
  async function confirmDeleteSalaryRow() {
    if (!token || !salaryDeleting || salaryBusy) return;
    setSalaryBusy(true);
    try {
      await api.rbac.deleteSalaryRow(token, salaryDeleting.id);
      setSalaryDeleting(null);
      await reloadSalaryRows();
    } catch {
      setSalaryError("Xóa dòng lương thất bại.");
    } finally {
      setSalaryBusy(false);
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
      // Xóa nhánh có thể gỡ tổ khỏi khối SX → cập nhật menu con tổ ở navbar.
      onDeptChanged?.();
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
      // Không có quyền sửa ma trận → tạo vai trò với quyền TRỐNG, Admin cấp sau. (Gọi
      // savePermissions ở đây sẽ 403 SAU KHI vai trò đã tạo → báo "không tạo được" trong khi
      // nó đã nằm trong DB.)
      if (canManagePerms) await api.rbac.savePermissions(token, role.id, addRoleMatrix);
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

  // Bỏ chọn vai trò đang xem (đóng panel quyền inline).
  function closeEditRole() {
    if (editRoleBusy || editRoleDeleting) return;
    setEditRoleOpen(false);
    setEditRoleId(null);
    setEditRoleConfirmDelete(false);
    setEditRoleError(null);
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
      if (canManagePerms) await api.rbac.savePermissions(token, editRoleId, editRoleMatrix);
      if (selectedId != null) setRoles(await api.rbac.roles(token, selectedId));
      setEditRoleOpen(false);
      setEditRoleId(null);
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
      setEditRoleId(null);
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

  /** Một hàng cây tổ chức (cột trái): caret + tên + mã + pill Khối SX + chip số nhân sự +
   *  badge "chưa có trưởng". Bấm hàng chọn phòng; caret chỉ để thu/mở nhánh. Thụt lề theo cấp. */
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
    const isActive = d.id === selectedId;
    const noHead = deptStatus(d) === "no_head";
    return (
      <div
        key={d.id}
        className={`rdx-tree__row${isActive ? " is-active" : ""}`}
        role="button"
        tabIndex={0}
        aria-pressed={isActive}
        style={{ paddingLeft: 10 + depth * 18 }}
        onClick={() => setSelectedId(d.id)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setSelectedId(d.id);
          }
        }}
      >
        {hasKids ? (
          <button
            type="button"
            className={`rdx-tree__caret${isCollapsed ? "" : " is-open"}`}
            aria-label={isCollapsed ? "Mở rộng" : "Thu gọn"}
            aria-expanded={!isCollapsed}
            onClick={(e) => {
              e.stopPropagation();
              toggleCollapse(d.id);
            }}
          >
            <Icon name="chevron" size={14} />
          </button>
        ) : (
          <span className="rdx-tree__caret rdx-tree__caret--leaf" aria-hidden="true" />
        )}
        <span className="rdx-tree__body">
          <span className="rdx-tree__line1">
            <span className="rdx-tree__name">{d.name}</span>
            {d.code && <span className="rdx-tree__code">{d.code}</span>}
            {d.la_san_xuat && <span className="rdx-tree__pill">Khối SX</span>}
          </span>
          <span className="rdx-tree__line2">
            <span className="rdx-tree__staff">
              <Icon name="users" size={13} />
              {d.employee_count ?? 0}
            </span>
            {noHead && (
              <span className="rdx-tree__warn">
                <Icon name="help" size={12} />
                chưa có trưởng
              </span>
            )}
          </span>
        </span>
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

  const treeChips = [
    { key: "all", label: "Tất cả", n: treeStats.all },
    { key: "san_xuat", label: "Sản xuất", n: treeStats.san_xuat },
    { key: "van_phong", label: "Văn phòng", n: treeStats.van_phong },
    { key: "no_head", label: "Thiếu trưởng", n: treeStats.no_head },
  ] as const;
  const tabs = [
    { key: "overview", label: "Tổng quan" },
    { key: "staff", label: "Nhân sự" },
    { key: "roles", label: "Vai trò & Quyền" },
    { key: "salary", label: "Lương" },
  ] as const;

  return (
    <main className="depts rdx-dept">
      <header className="rdx-dept__head">
        <div>
          <p className="eyebrow">Nhân sự &amp; Lương</p>
          <h1 className="depts__title">Phòng ban</h1>
          <p className="depts__sub">
            Quản lý cơ cấu phòng ban, nhân sự và vai trò trong từng phòng.
          </p>
        </div>
      </header>

      <div className="rdx-dept__body">
        {/* ── CỘT TRÁI: cây tổ chức (luôn hiển thị) ─────────────────────── */}
        <aside className="rdx-dept__master" aria-label="Danh sách phòng ban">
          <div className="rdx-dept__master-top">
            <div className="rdx-tree__search">
              <Icon name="search" size={16} className="rdx-tree__search-icon" />
              <input
                className="rdx-tree__search-input"
                placeholder="Tìm theo tên hoặc mã…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                aria-label="Tìm phòng ban"
              />
            </div>
            {canCreateDept && (
              <Button type="button" variant="accent" onClick={openCreate}>
                <Icon name="plus" size={16} /> Thêm phòng
              </Button>
            )}
          </div>

          <div className="rdx-tree__chips" role="group" aria-label="Lọc phòng ban">
            {treeChips.map((c) => (
              <button
                key={c.key}
                type="button"
                className={`rdx-chip${treeFilter === c.key ? " is-active" : ""}`}
                aria-pressed={treeFilter === c.key}
                onClick={() => setTreeFilter(c.key)}
              >
                {c.label}
                <span className="rdx-chip__n">{c.n}</span>
              </button>
            ))}
          </div>

          <div className="rdx-tree">
            {departments.length === 0 ? (
              <div className="rdx-tree__empty">
                <p className="rdx-tree__empty-title">Chưa có phòng ban</p>
                <p className="depts__hint">
                  {canCreateDept
                    ? "Bấm “Thêm phòng” để tạo phòng đầu tiên."
                    : "Chưa có phòng ban nào để xem."}
                </p>
              </div>
            ) : listRows.length === 0 ? (
              <p className="depts__hint rdx-tree__none">Không có phòng ban khớp bộ lọc.</p>
            ) : (
              listRows.map(renderRow)
            )}
          </div>
        </aside>

        {/* ── CỘT PHẢI: drawer chi tiết (4 tab) ─────────────────────────── */}
        <section className="rdx-dept__detail" aria-label="Chi tiết phòng ban">
          {selectedId != null && currentDept ? (
            <div className="rdx-drawer">
              <header className="rdx-drawer__head">
                <div className="rdx-drawer__id">
                  <span className="rdx-drawer__avatar" aria-hidden="true">
                    <Icon name="building" size={22} />
                  </span>
                  <div className="rdx-drawer__idmain">
                    {(() => {
                      const trail = ancestorTrail(currentDept);
                      return (
                        <div className="rdx-drawer__crumbs">
                          {trail.length ? trail.join(" › ") : "Phòng gốc"}
                        </div>
                      );
                    })()}
                    <div className="rdx-drawer__nameline">
                      <h2 className="rdx-drawer__name">{currentDept.name}</h2>
                      {currentDept.code && (
                        <span className="rdx-drawer__code">{currentDept.code}</span>
                      )}
                      {currentDept.la_san_xuat && (
                        <span className="rdx-drawer__pill">Khối SX</span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="rdx-drawer__headact">
                  {canUpdateDept && (
                    <button
                      type="button"
                      className="rdx-drawer__ghost"
                      onClick={openInfoEdit}
                    >
                      <Icon name="pencil" size={15} /> Sửa
                    </button>
                  )}
                  <button
                    type="button"
                    className="rdx-drawer__close"
                    aria-label="Đóng chi tiết"
                    onClick={() => setSelectedId(null)}
                  >
                    <Icon name="x" size={18} />
                  </button>
                </div>
              </header>

              <div className="rdx-drawer__tabs" role="tablist" aria-label="Mục chi tiết">
                {tabs.map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === t.key}
                    className={`rdx-drawer__tab${activeTab === t.key ? " is-active" : ""}`}
                    onClick={() => setActiveTab(t.key)}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              <div className="rdx-drawer__panel">
                {/* ── TAB: Tổng quan ─────────────────────────────────── */}
                {activeTab === "overview" && (
                  <div className="rdx-ov">
                    {currentDept.description && (
                      <p className="rdx-ov__desc">{currentDept.description}</p>
                    )}
                    <div className="rdx-ov__grid">
                      <div className="rdx-ov__item">
                        <span className="rdx-ov__k">Trực thuộc</span>
                        <span className="rdx-ov__v">
                          {parentName(currentDept.parent_id) ?? "Phòng gốc"}
                        </span>
                      </div>
                      <div className="rdx-ov__item">
                        <span className="rdx-ov__k">
                          {currentDept.head_title || "Người đứng đầu"}
                        </span>
                        <span className="rdx-ov__v">
                          {currentDept.head_name ?? "Chưa chỉ định"}
                        </span>
                      </div>
                      <div className="rdx-ov__item">
                        <span className="rdx-ov__k">Nhân sự</span>
                        <span className="rdx-ov__v rdx-ov__v--num">
                          {currentDept.employee_count ?? 0}
                        </span>
                      </div>
                      <div className="rdx-ov__item">
                        <span className="rdx-ov__k">Vai trò</span>
                        <span className="rdx-ov__v rdx-ov__v--num">{roles.length}</span>
                      </div>
                      <div className="rdx-ov__item">
                        <span className="rdx-ov__k">Khối sản xuất</span>
                        <span className="rdx-ov__v">
                          {currentDept.la_san_xuat ? "Có" : "Không"}
                        </span>
                      </div>
                      <div className="rdx-ov__item">
                        <span className="rdx-ov__k">Lương khoán</span>
                        <span className="rdx-ov__v">
                          {currentDept.has_piece_work ? "Có" : "Không"}
                        </span>
                      </div>
                      <div className="rdx-ov__item rdx-ov__item--wide">
                        <span className="rdx-ov__k">Lương thử việc</span>
                        <span className="rdx-ov__v">
                          {companyProbationRatio != null
                            ? `${Math.round(companyProbationRatio * 100)}%`
                            : "—"}
                          <span className="rdx-ov__note">
                            {" "}
                            · áp chung toàn công ty
                          </span>
                        </span>
                      </div>
                    </div>

                    {(childrenOf.get(currentDept.id)?.length ?? 0) > 0 && (
                      <p className="rdx-ov__branch">
                        Gồm cả nhánh con:{" "}
                        {currentDept.total_role_count ?? roles.length} vai trò ·{" "}
                        {currentDept.total_employee_count ?? currentDept.employee_count} người
                      </p>
                    )}

                    <div className="rdx-ov__actions">
                      {canUpdateDept && (
                        <Button type="button" variant="primary" onClick={openInfoEdit}>
                          <Icon name="pencil" size={15} /> Chỉnh sửa thông tin
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
                )}

                {/* ── TAB: Nhân sự ───────────────────────────────────── */}
                {activeTab === "staff" && (
                  <div className="rdx-tab">
                    <div className="depts__section-head">
                      <div className="depts__eyebrow-row">
                        <p className="eyebrow">Nhân sự trong phòng</p>
                        <InfoHint
                          label={
                            canTransfer
                              ? "Liệt kê theo HỒ SƠ nhân sự — gồm cả người chưa có tài khoản đăng nhập (công nhân xưởng). Tích chọn nhiều người để chuyển sang phòng khác (ai cũng chuyển được) hoặc gán vai trò hàng loạt (chỉ áp cho người có tài khoản). Chuyển phòng: vai trò cũ bị gỡ, trưởng phòng mới gán lại."
                              : "Liệt kê theo HỒ SƠ nhân sự — gồm cả người chưa có tài khoản đăng nhập."
                          }
                        />
                      </div>
                      <div className="depts__section-head-actions">
                        <span className="depts__count-pill">{members.length}</span>
                        {canAddEmployee && (
                          <Button
                            type="button"
                            variant="ghost"
                            onClick={() => setWizardOpen(true)}
                          >
                            + Thêm nhân viên
                          </Button>
                        )}
                      </div>
                    </div>
                    {detailLoading ? (
                      <p className="depts__status">Đang tải…</p>
                    ) : detailError ? (
                      <span className="depts__inline-error" role="alert">
                        {detailError}
                      </span>
                    ) : members.length === 0 ? (
                      <p className="depts__hint">
                        {canAddEmployee
                          ? "Phòng chưa có nhân sự. Bấm “+ Thêm nhân viên” ở trên để thêm."
                          : "Phòng chưa có nhân sự. Thêm người ở màn “Hồ sơ nhân sự”."}
                      </p>
                    ) : (
                      <>
                        {/* Toolbar: tìm kiếm + lọc trạng thái — LUÔN hiển thị (không bị che). */}
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

                        {/* Khoảng CỐ ĐỊNH trên danh sách: luôn giữ chiều cao nên khi tick chọn,
                            thanh thao tác lấp vào đúng chỗ — danh sách KHÔNG bị đẩy. */}
                        {canBulk && (
                          <div className="depts__transferslot">
                            {selectedMemberIds.size > 0 ? (
                              <div className="depts__transfer depts__transfer--top">
                                <span className="depts__transfer-count">
                                  Đã chọn {selectedMemberIds.size} người
                                </span>
                                {canAssignRole && roles.length > 0 && (
                                  <div className="depts__bulk-action">
                                    <span className="depts__bulk-label">Gán vai trò</span>
                                    <div className="depts__transfer-select">
                                      <Select
                                        ariaLabel="Vai trò"
                                        value={assignRoleTarget}
                                        placeholder="— Chọn vai trò —"
                                        onChange={(v) => setAssignRoleTarget(v)}
                                        options={[
                                          { value: null, label: "— Chọn vai trò —" },
                                          ...roles.map((r) => ({ value: r.id, label: r.name })),
                                        ]}
                                      />
                                    </div>
                                    <Button
                                      type="button"
                                      variant="accent"
                                      loading={assignRoleBusy}
                                      disabled={assignRoleTarget == null || !canAssignRole}
                                      onClick={() =>
                                        setPendingBulk({
                                          title: "Xác nhận gán vai trò",
                                          message:
                                            `Bạn sắp gán vai trò "${roles.find((r) => r.id === assignRoleTarget)?.name ?? ""}" ` +
                                            `cho ${selectedWithAccount} người đã chọn. Vai trò cũ của họ sẽ bị thay thế.` +
                                            (selectedWithoutAccount > 0
                                              ? ` ${selectedWithoutAccount} người chưa có tài khoản sẽ được BỎ QUA (phải cấp tài khoản trước).`
                                              : "") +
                                            " Kiểm tra kỹ trước khi xác nhận.",
                                          confirmLabel: "Gán vai trò",
                                          run: doAssignRole,
                                        })
                                      }
                                    >
                                      Gán
                                    </Button>
                                  </div>
                                )}
                                {canTransfer && (
                                  <div className="depts__bulk-action">
                                    <span className="depts__bulk-label">Chuyển sang</span>
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
                                      onClick={() =>
                                        setPendingBulk({
                                          title: "Xác nhận chuyển phòng ban",
                                          message:
                                            `Bạn sắp chuyển ${selectedMemberIds.size} người sang phòng ` +
                                            `"${departments.find((d) => d.id === transferTarget)?.name ?? ""}". ` +
                                            "Vai trò hiện tại của họ sẽ bị gỡ. Kiểm tra kỹ trước khi xác nhận.",
                                          confirmLabel: "Chuyển phòng ban",
                                          danger: true,
                                          run: doTransfer,
                                        })
                                      }
                                    >
                                      Chuyển
                                    </Button>
                                  </div>
                                )}
                                <button
                                  type="button"
                                  className="btn btn--ghost"
                                  onClick={() => setSelectedMemberIds(new Set())}
                                >
                                  Bỏ chọn
                                </button>
                              </div>
                            ) : (
                              <span className="depts__transfer-hint">
                                Tick chọn nhân sự để gán vai trò hoặc chuyển sang phòng khác hàng loạt.
                              </span>
                            )}
                          </div>
                        )}

                        {(transferError || assignRoleError) && (
                          <span className="depts__inline-error" role="alert">
                            {transferError ?? assignRoleError}
                          </span>
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
                              <li key={m.employee_id} className="depts__member">
                                {canBulk && (
                                  <input
                                    type="checkbox"
                                    className="depts__member-check"
                                    checked={selectedMemberIds.has(m.employee_id)}
                                    onChange={() => toggleMember(m.employee_id)}
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
                                  </span>
                                  <span className="depts__member-meta">
                                    {m.code && (
                                      <span className="depts__member-code">{m.code}</span>
                                    )}
                                    {m.position && (
                                      <span className="depts__member-role">{m.position}</span>
                                    )}
                                    {m.user_id == null ? (
                                      <span className="depts__member-status">Chưa có tài khoản</span>
                                    ) : (
                                      <>
                                        <span className="depts__member-user">{m.username}</span>
                                        <span className="depts__member-role">
                                          {m.role_name ?? "Chưa gán vai trò"}
                                        </span>
                                        <span
                                          className={`depts__member-status${m.is_active ? "" : " is-locked"}`}
                                        >
                                          {m.is_active ? "Đang hoạt động" : "Đã khóa"}
                                        </span>
                                      </>
                                    )}
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
                )}

                {/* ── TAB: Vai trò & Quyền ──────────────────────────── */}
                {activeTab === "roles" && (
                  <div className="rdx-tab">
                    <div className="depts__section-head">
                      <div className="depts__eyebrow-row">
                        <p className="eyebrow">Vai trò trong phòng</p>
                        <InfoHint
                          label={
                            canUpdateRole
                              ? "Các vai trò định nghĩa riêng cho phòng này. Bấm một vai trò để xem/sửa quyền hoặc xóa."
                              : "Các vai trò định nghĩa riêng cho phòng này."
                          }
                        />
                      </div>
                    </div>

                    {detailLoading ? (
                      <p className="depts__status">Đang tải…</p>
                    ) : roles.length === 0 && !canCreateRole ? (
                      <p className="depts__hint">Phòng này chưa có vai trò.</p>
                    ) : (
                      <div className="rdx-roles__chips">
                        {roles.map((r) => {
                          const holders = members.filter((m) => m.role_name === r.name).length;
                          const isSel = editRoleOpen && editRoleId === r.id;
                          const chipInner = (
                            <>
                              <span className="rdx-rolechip__name">{r.name}</span>
                              {holders > 0 && (
                                <span className="rdx-rolechip__n">{holders}</span>
                              )}
                            </>
                          );
                          return canUpdateRole ? (
                            <button
                              key={r.id}
                              type="button"
                              className={`rdx-rolechip${isSel ? " is-active" : ""}`}
                              aria-pressed={isSel}
                              onClick={() =>
                                isSel ? closeEditRole() : openEditRole(r)
                              }
                            >
                              {chipInner}
                            </button>
                          ) : (
                            <span key={r.id} className="rdx-rolechip rdx-rolechip--static">
                              {chipInner}
                            </span>
                          );
                        })}
                        {canCreateRole && (
                          <button
                            type="button"
                            className="rdx-rolechip rdx-rolechip--add"
                            onClick={openAddRole}
                          >
                            <Icon name="plus" size={14} /> Vai trò
                          </button>
                        )}
                      </div>
                    )}

                    {/* Panel quyền của vai trò đang chọn (inline). */}
                    {editRoleOpen && editRoleId != null && (
                      <div className="rdx-rolepanel">
                        <div className="rdx-rolepanel__head">
                          <div className="field rdx-rolepanel__namefield">
                            <label className="field__label" htmlFor="edit-role-name">
                              Tên vai trò {canUpdateRole && <span className="depts__req">*</span>}
                            </label>
                            <input
                              id="edit-role-name"
                              className={`input${editRoleError ? " input--error" : ""}`}
                              value={editRoleName}
                              disabled={!canUpdateRole}
                              aria-invalid={editRoleError ? true : undefined}
                              onChange={(e) => {
                                setEditRoleName(e.target.value);
                                if (editRoleError) setEditRoleError(null);
                              }}
                            />
                          </div>
                          <button
                            type="button"
                            className="rdx-drawer__close"
                            aria-label="Bỏ chọn vai trò"
                            disabled={editRoleBusy || editRoleDeleting}
                            onClick={closeEditRole}
                          >
                            <Icon name="x" size={16} />
                          </button>
                        </div>

                        <p className="eyebrow depts__matrix-label">Phân quyền</p>
                        {editRoleLoading ? (
                          <p className="depts__status">Đang tải ma trận…</p>
                        ) : (
                          <PermissionMatrix
                            modules={modules}
                            matrix={editRoleMatrix}
                            onToggle={toggleEditRole}
                            onScope={scopeEditRole}
                            readOnly={!canManagePerms}
                          />
                        )}

                        {editRoleError && (
                          <span className="depts__inline-error" role="alert">
                            {editRoleError}
                          </span>
                        )}

                        <div className="rdx-rolepanel__foot">
                          <div className="rdx-rolepanel__danger">
                            {editRoleConfirmDelete ? (
                              <div className="depts__inline">
                                <span className="depts__confirm-count">
                                  Xóa vai trò này? Không thể hoàn tác.
                                </span>
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
                          {canEditRoleAnything && (
                            <Button
                              type="button"
                              variant="primary"
                              loading={editRoleBusy}
                              disabled={editRoleLoading || !editRoleName.trim()}
                              onClick={submitEditRole}
                            >
                              Lưu thay đổi
                            </Button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* ── TAB: Lương ────────────────────────────────────── */}
                {activeTab === "salary" && (
                  <div className="rdx-tab">
                    <div className="depts__section-head">
                      <div className="depts__eyebrow-row">
                        <p className="eyebrow">Bảng lương của phòng</p>
                        <InfoHint label="Các mức lương của phòng. Mỗi dòng: đặt tên + chọn cách áp (lương cứng / bậc thợ / thâm niên / thâm niên+giới tính) rồi gõ 4 khoản. Một phòng khai bao nhiêu dòng, bao nhiêu kiểu tùy ý. Người mới gán vào phòng sẽ theo bảng này." />
                      </div>
                      {canUpdateDept && (
                        <Button type="button" variant="ghost" onClick={openSalaryAdd}>
                          + Thêm mức lương
                        </Button>
                      )}
                    </div>
                    {detailLoading ? (
                      <p className="depts__status">Đang tải…</p>
                    ) : salaryRows.length === 0 ? (
                      <p className="depts__hint">
                        {canUpdateDept
                          ? "Chưa có mức lương. Bấm “+ Thêm mức lương” để phòng tự khai."
                          : "Phòng này chưa khai bảng lương."}
                      </p>
                    ) : (
                      <div className="depts__salary-wrap">
                        <table className="depts__salary-table">
                          <thead>
                            <tr>
                              <th>Tên mức</th>
                              <th>Cách áp</th>
                              <th className="num">Vị trí</th>
                              <th className="num">Trách nhiệm</th>
                              <th className="num">Mức nền</th>
                              {canUpdateDept && <th aria-label="Thao tác" />}
                            </tr>
                          </thead>
                          <tbody>
                            {salaryRows.map((r) => (
                              <tr key={r.id}>
                                <td>
                                  <strong>{r.label}</strong>
                                </td>
                                <td className="depts__salary-apply">
                                  {APPLY_LABEL[r.apply_by]}
                                  {applyDetail(r)}
                                </td>
                                <td className="num">
                                  {r.luong_vi_tri.toLocaleString("vi-VN")}
                                </td>
                                <td className="num">
                                  {r.luong_trach_nhiem.toLocaleString("vi-VN")}
                                </td>
                                <td className="num">
                                  <strong>
                                    {salaryRowTotal(r).toLocaleString("vi-VN")}
                                  </strong>
                                </td>
                                {canUpdateDept && (
                                  <td className="num depts__salary-actions">
                                    <button
                                      type="button"
                                      className="btn btn--ghost md-page__rowbtn"
                                      onClick={() => openSalaryEdit(r)}
                                    >
                                      Sửa
                                    </button>
                                    <button
                                      type="button"
                                      className="btn btn--ghost md-page__rowbtn md-page__rowbtn--danger"
                                      onClick={() => setSalaryDeleting(r)}
                                    >
                                      Xóa
                                    </button>
                                  </td>
                                )}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="rdx-dept__placeholder">
              <Icon name="building" size={40} className="rdx-dept__placeholder-icon" />
              <p className="rdx-dept__placeholder-title">Chọn một phòng ban</p>
              <p className="depts__hint">
                Bấm một phòng ở danh sách bên trái để xem nhân sự, vai trò và bảng lương.
              </p>
            </div>
          )}
        </section>
      </div>

      {/* ── Modal: chỉnh sửa thông tin phòng (mở từ tab Tổng quan / nút Sửa) ── */}
      {currentDept && (
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
                disabled={!canReparent}
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
              {!canReparent && (
                <span className="depts__hint">Cần quyền "Đổi cấp trên" để chuyển cây tổ chức.</span>
              )}
            </div>

            <div className="field depts__field--full">
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={editLaSanXuat}
                  onChange={(e) => {
                    setEditLaSanXuat(e.target.checked);
                    setDirty(true);
                  }}
                />
                <span className="field__label depts__label" style={{ margin: 0 }}>
                  Là bộ phận sản xuất
                  <InfoHint label="Đánh dấu phòng/khối thuộc SẢN XUẤT: cả cây con (đơn vị trực thuộc) tự coi là sản xuất và lên phân hệ Sản xuất." />
                </span>
              </label>
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
                disabled={headCandidates.length === 0 || !canSetHead}
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

            {/* Thuộc tính lương của phòng (Pha 1). Thử việc là quy định CHUNG toàn
                công ty → chỉ hiển thị; khai thật ở Lương → Quy tắc lương. */}
            <div className="field">
              <span className="field__label depts__label">
                Lương thử việc
              </span>
              <div className="depts__readonly">
                <strong>
                  {companyProbationRatio != null
                    ? `${Math.round(companyProbationRatio * 100)}%`
                    : "—"}
                </strong>{" "}
                <span className="depts__hint">
                  áp chung toàn công ty · khai ở Lương → Quy tắc lương
                </span>
              </div>
            </div>

            <div className="field">
              <span className="field__label depts__label">Lương khoán</span>
              <label className="depts__checkline">
                <input
                  type="checkbox"
                  checked={editHasPieceWork}
                  onChange={(e) => {
                    setEditHasPieceWork(e.target.checked);
                    setDirty(true);
                  }}
                />
                <span>Phòng sản xuất, có lương khoán theo sản lượng</span>
              </label>
            </div>
          </div>
        </ConfirmDialog>
      )}

      {/* Cảnh báo khi thoát modal chỉnh sửa mà còn thay đổi chưa lưu. */}
      <DiscardChangesDialog
        open={confirmDiscard}
        onDiscard={() => {
          setConfirmDiscard(false);
          setInfoOpen(false);
        }}
        onKeepEditing={() => setConfirmDiscard(false)}
      />

      {/* Thêm/sửa một mức lương của phòng. */}
      <ConfirmDialog
        open={salaryEditing !== null}
        title={salaryEditing === "new" ? "Thêm mức lương" : "Sửa mức lương"}
        wide
        confirmLabel="Lưu"
        busy={salaryBusy}
        error={salaryError}
        confirmDisabled={!salaryForm.label.trim()}
        onConfirm={saveSalaryRow}
        onCancel={() => {
          if (!salaryBusy) setSalaryEditing(null);
        }}
      >
        <div className="depts__form-grid">
          <div className="field depts__field--full">
            <label className="field__label" htmlFor="sal-label">
              Tên mức
            </label>
            <input
              id="sal-label"
              className="input"
              placeholder="Vd: Thợ bậc 1 · Tổ trưởng · Dưới 1 năm - Nam"
              value={salaryForm.label}
              onChange={(e) =>
                setSalaryForm((f) => ({ ...f, label: e.target.value }))
              }
            />
          </div>
          <div className="field depts__field--full">
            <label className="field__label" htmlFor="sal-apply">
              Cách áp (map người vào mức này)
            </label>
            <select
              id="sal-apply"
              className="input"
              value={salaryForm.apply_by}
              onChange={(e) =>
                setSalaryForm((f) => ({
                  ...f,
                  apply_by: e.target.value as SalaryMechanism,
                }))
              }
            >
              {SALARY_MECHANISM_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          {salaryForm.apply_by === "bac_tho" && (
            <div className="field">
              <label className="field__label" htmlFor="sal-grade">
                Bậc thợ
              </label>
              <select
                id="sal-grade"
                className="input"
                value={salaryForm.pay_grade_key ?? ""}
                onChange={(e) =>
                  setSalaryForm((f) => ({
                    ...f,
                    pay_grade_key: e.target.value || null,
                  }))
                }
              >
                <option value="">— Chọn bậc —</option>
                {GRADE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          )}
          {(salaryForm.apply_by === "tham_nien" ||
            salaryForm.apply_by === "tham_nien_gioi_tinh") && (
            <div className="field">
              <label className="field__label" htmlFor="sal-band">
                Thâm niên
              </label>
              <select
                id="sal-band"
                className="input"
                value={salaryForm.seniority_band ?? ""}
                onChange={(e) =>
                  setSalaryForm((f) => ({
                    ...f,
                    seniority_band: e.target.value || null,
                  }))
                }
              >
                <option value="">— Chọn thâm niên —</option>
                {SENIORITY_BAND_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          )}
          {salaryForm.apply_by === "tham_nien_gioi_tinh" && (
            <div className="field">
              <label className="field__label" htmlFor="sal-gender">
                Giới tính
              </label>
              <select
                id="sal-gender"
                className="input"
                value={salaryForm.gender ?? ""}
                onChange={(e) =>
                  setSalaryForm((f) => ({
                    ...f,
                    gender: e.target.value || null,
                  }))
                }
              >
                <option value="">— Chọn —</option>
                {GENDER_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="field">
            <label className="field__label" htmlFor="sal-vt">
              Lương vị trí
            </label>
            <input
              id="sal-vt"
              className="input"
              type="number"
              min={0}
              step={100000}
              value={salaryForm.luong_vi_tri}
              onChange={(e) =>
                setSalaryForm((f) => ({
                  ...f,
                  luong_vi_tri: Number(e.target.value) || 0,
                }))
              }
            />
          </div>
          <div className="field">
            <label className="field__label" htmlFor="sal-tn">
              Lương trách nhiệm
            </label>
            <input
              id="sal-tn"
              className="input"
              type="number"
              min={0}
              step={100000}
              value={salaryForm.luong_trach_nhiem}
              onChange={(e) =>
                setSalaryForm((f) => ({
                  ...f,
                  luong_trach_nhiem: Number(e.target.value) || 0,
                }))
              }
            />
          </div>
          <div className="field depts__field--full">
            <span className="depts__hint">
              Phụ cấp + Chuyên cần khai theo TỪNG NHÂN VIÊN (mỗi người mỗi khác) — ở
              hồ sơ nhân sự / màn Lương, không khai ở đây.
            </span>
          </div>
          <div className="field depts__field--full">
            <span className="depts__hint">
              Mức nền (vị trí + trách nhiệm):{" "}
              <strong>
                {salaryRowTotal(salaryForm).toLocaleString("vi-VN")} đ
              </strong>{" "}
              · Tăng ca sẽ tính trên (vị trí + trách nhiệm).
            </span>
          </div>
        </div>
      </ConfirmDialog>

      {/* Xác nhận xóa một mức lương. */}
      <ConfirmDialog
        open={salaryDeleting !== null}
        title="Xóa mức lương"
        danger
        confirmLabel="Xóa"
        busy={salaryBusy}
        onConfirm={confirmDeleteSalaryRow}
        onCancel={() => {
          if (!salaryBusy) setSalaryDeleting(null);
        }}
      >
        <p>
          Xóa mức lương{" "}
          <strong>{salaryDeleting?.label}</strong> khỏi bảng lương của
          phòng?
        </p>
      </ConfirmDialog>

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
        {canManagePerms ? (
          <PermissionMatrix
            modules={modules}
            matrix={addRoleMatrix}
            onToggle={toggleAddRole}
            onScope={scopeAddRole}
          />
        ) : (
          <p className="depts__status">
            Bạn không có quyền cấu hình phân quyền. Vai trò sẽ được tạo với quyền trống —
            quản trị hệ thống cấp quyền sau.
          </p>
        )}
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

      {/* Popup cảnh báo có đếm ngược 5s cho gán vai trò / chuyển phòng hàng loạt. */}
      <ConfirmDialog
        open={pendingBulk != null}
        title={pendingBulk?.title ?? ""}
        message={pendingBulk?.message}
        confirmLabel={pendingBulk?.confirmLabel ?? "Xác nhận"}
        danger={pendingBulk?.danger}
        countdownSeconds={5}
        onConfirm={() => {
          const p = pendingBulk;
          setPendingBulk(null);
          p?.run();
        }}
        onCancel={() => setPendingBulk(null)}
      />

      {/* Thêm nhân viên vào phòng đang xem — TÁI DÙNG form Hồ sơ nhân sự, chọn sẵn tổ này. */}
      {wizardOpen && empMeta && currentDept && token && (
        <EmployeeWizard
          token={token}
          meta={empMeta}
          canSalary={can("luong", "update")}
          initialDepartmentId={currentDept.id}
          onClose={() => setWizardOpen(false)}
          onCreated={async () => {
            setWizardOpen(false);
            // Nạp lại danh sách nhân sự của phòng + số đếm ở đầu danh sách.
            if (selectedId != null) {
              try {
                setMembers(await api.rbac.departmentUsers(token, selectedId));
              } catch {
                /* giữ danh sách cũ nếu tải lại lỗi */
              }
            }
            refresh(selectedId).catch(() => {});
          }}
        />
      )}
    </main>
  );
}
