// Màn Phòng ban — cơ cấu tổ chức, nhân sự theo phòng, vai trò & quyền
// (tách từ pages/DepartmentsPage.tsx).
import { useEffect, useMemo, useState, useRef } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type Department,
  type DepartmentMember,
  type DepartmentSubtreeRow,
  type EmployeeMeta,
  type ModuleDef,
  type PermissionRow,
  type Role,
  type RoleTemplate,
  type Scope,
  type UserBrief,
} from "../../../api/client";
import { useAuth } from "../../../auth/useAuth";
import { useCan } from "../../../auth/permissions";
import { Button } from "../../../components/Button";
import { ConfirmDialog } from "../../../components/ConfirmDialog";
import { DiscardChangesDialog } from "../../../components/DiscardChangesDialog";
import { InfoHint } from "../../../components/InfoHint";
import { Select } from "../../../components/Select";
import {
  PermissionMatrix,
  defaultMatrix,
  type ActionKey,
} from "../../../components/PermissionMatrix";
import { EmployeeWizard } from "../nhan-su";
import { Icon } from "../../../components/Icons";
import {
  Building2,
  Factory,
  Handshake,
  Truck,
  Briefcase,
  Users,
  FolderTree,
  ChevronRight,
  Plus,
  Search,
  UserCheck,
  Crown,
  LayoutGrid,
  Network,
  User,
  ZoomIn,
  ZoomOut,
  Maximize2,
  ChevronUp,
  ChevronDown,
  Move,
  ShieldCheck,
  ArrowRightLeft,
  X,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import type { NavigateFn } from "../../../components/AppShell";
import { PAN_HINT_KEY } from "./shared/constants";
import {
  applyPermissionDependency,
  buildTree,
  initials,
} from "./shared/helpers";
import "../../departments.css";
import "../../nhan-su.css";
import "../../redesign-phong-ban.css";

export function DepartmentsPage({
  onDeptChanged,
}: { onDeptChanged?: () => void; navigate?: NavigateFn } = {}) {
  const { token, user } = useAuth();
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

  function renderMemberAvatar(
    name: string,
    options?: {
      isHead?: boolean;
      userId?: number | null;
      username?: string | null;
      avatarUrl?: string | null;
      size?: number;
    },
  ) {
    // Server đã trả ảnh cho TỪNG người (`avatar_url` / `head_avatar_url`), nên đây là nguồn chính.
    //
    // Nhánh dự phòng chỉ còn dùng khi đúng người đang đăng nhập: họ vừa đổi ảnh trong màn Tài khoản
    // thì context xác thực mới hơn danh sách đang cache, hiện ngay cho khỏi tưởng đổi không ăn.
    //
    const laChinhMinh = options?.userId != null && user?.id === options.userId;

    const src = options?.avatarUrl
      ? assetUrl(options.avatarUrl)
      : laChinhMinh && user?.avatar_url
      ? assetUrl(user.avatar_url)
      : null;

    const avatarSize = options?.size ?? 34;
    const badgeSize = Math.max(14, Math.round(avatarSize * 0.42));
    const iconSize = Math.max(9, Math.round(avatarSize * 0.26));

    return (
      <div
        className="rdx-avatar-wrap"
        style={{
          position: "relative",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          width: avatarSize,
          height: avatarSize,
        }}
      >
        {src ? (
          <img
            src={src}
            alt={name}
            className={`rdx-avatar-img${options?.isHead ? " rdx-avatar-img--head" : ""}`}
            style={{
              width: avatarSize,
              height: avatarSize,
              borderRadius: "50%",
              objectFit: "cover",
              objectPosition: "center",
              border: options?.isHead
                ? "1.5px solid #f59e0b"
                : "1.5px solid var(--rule-soft, #e8e3d3)",
              boxShadow: "0 1px 3px rgba(20, 19, 15, 0.08)",
            }}
          />
        ) : (
          <span
            className={`depts__member-avatar${options?.isHead ? " depts__member-avatar--head" : ""}`}
            style={{
              width: avatarSize,
              height: avatarSize,
              fontSize: Math.max(10, Math.round(avatarSize * 0.38)),
            }}
            aria-hidden="true"
          >
            {initials(name)}
          </span>
        )}

        {/* Badge Vương miện cho Trưởng phòng */}
        {options?.isHead && (
          <div
            className="rdx-avatar-badge--head"
            title="Trưởng phòng / Người đứng đầu"
            style={{
              position: "absolute",
              bottom: "-2px",
              right: "-2px",
              width: badgeSize,
              height: badgeSize,
              borderRadius: "50%",
              background: "linear-gradient(135deg, #f59e0b 0%, #b45309 100%)",
              border: "1.5px solid #ffffff",
              display: "grid",
              placeItems: "center",
              color: "#ffffff",
              boxShadow: "0 2px 6px rgba(180, 83, 9, 0.4)",
              zIndex: 2,
            }}
          >
            <Crown size={iconSize} strokeWidth={2.5} />
          </div>
        )}
      </div>
    );
  }

  const [departments, setDepartments] = useState<Department[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [members, setMembers] = useState<DepartmentMember[]>([]);
  // Mở form Thêm NV vào phòng đang xem; meta (danh sách phòng/vai trò…) nạp 1 lần khi có quyền.
  const [wizardOpen, setWizardOpen] = useState(false);
  const [empMeta, setEmpMeta] = useState<EmployeeMeta | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [modules, setModules] = useState<ModuleDef[]>([]);
  // Bảng VAI MẪU (đợt 6). Lỗi khi nạp ⇒ để rỗng: thanh chọn mẫu tự ẩn, ma trận vẫn cấp tay
  // được như cũ — mẫu là tiện ích, không phải điều kiện để cấp quyền.
  const [roleTemplates, setRoleTemplates] = useState<RoleTemplate[]>([]);
  // Who may head the selected unit (its subtree, PBI-4004).
  const [headCandidates, setHeadCandidates] = useState<UserBrief[]>([]);
  // Modal chỉ định Trưởng phòng nhanh trực tiếp từ Head Hero Card
  const [assignHeadOpen, setAssignHeadOpen] = useState(false);
  const [assignHeadTarget, setAssignHeadTarget] = useState<number | null>(null);
  const [assignHeadBusy, setAssignHeadBusy] = useState(false);
  const [assignHeadError, setAssignHeadError] = useState<string | null>(null);
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

  // Listen for Esc key to quickly clear selection
  useEffect(() => {
    if (selectedMemberIds.size === 0) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelectedMemberIds(new Set());
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedMemberIds.size]);
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
  // Tỷ lệ thử việc là quy định CHUNG toàn công ty (payroll_params) — chỉ HIỂN THỊ ở form
  // phòng, khai thật ở Lương → Cấu hình lương. null = chưa tải được (thiếu quyền luong).
  const [companyProbationRatio, setCompanyProbationRatio] = useState<
    number | null
  >(null);
  const [editLaSanXuat, setEditLaSanXuat] = useState(false);
  // Khối KINH DOANH — nền cho danh sách "NV phụ trách" ở màn Khách hàng (cả cây con kế thừa).
  const [editLaKinhDoanh, setEditLaKinhDoanh] = useState(false);
  const [editLaGiaoHang, setEditLaGiaoHang] = useState(false);
  // Khoán km giao hàng (đơn giá + %) ĐÃ DỜI sang Cấu hình lương → Cơ chế lương theo bộ phận
  // (chủ chốt 24/08/2026). Ở đây chỉ còn CỜ bật/tắt Bộ phận Giao hàng.
  // Cờ tổ KCS đích danh (§3.1/§14 spec bài ghép) — KHÔNG kế thừa cây con, khác 3 cờ trên.
  const [editIsKcs, setEditIsKcs] = useState(false);
  const [dirty, setDirty] = useState(false);
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
  const [treeFilter, setTreeFilter] = useState<"all" | "san_xuat" | "kinh_doanh" | "giao_hang" | "van_phong" | "no_head" | "no_staff">(
    "all",
  );
  // Chế độ xem: danh sách cây thẻ (tree) vs Sơ đồ khối trực quan (chart)
  const [viewMode, setViewMode] = useState<"tree" | "chart">("tree");
  // Mức thu phóng (zoom scale) cho Sơ đồ cây (chart mode)
  const [zoom, setZoom] = useState(1);

  // Canvas Refs & Control Handlers
  const canvasRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  // Mốc kéo giữ ở ref: pan chạy theo từng pixel, không việc gì phải render lại.
  const dragRef = useRef({ x: 0, y: 0, scrollLeft: 0, scrollTop: 0 });
  const draggingRef = useRef(false);
  // Đã thu hết cỡ mà sơ đồ vẫn không lọt khung → nói ra, kèm cách xử lý.
  const [fitCapped, setFitCapped] = useState(false);
  // Gợi ý "kéo để di chuyển" — tắt hẳn sau lần kéo đầu tiên (nhớ qua localStorage).
  const [panHint, setPanHint] = useState(() => {
    try {
      return localStorage.getItem(PAN_HINT_KEY) == null;
    } catch {
      return true;
    }
  });

  /** Canh tầm mắt vào GIỮA sơ đồ — gốc cây nằm giữa, không phải ở mép trái. */
  function centerCanvas(smooth = false) {
    const el = canvasRef.current;
    if (!el) return;
    el.scrollTo({
      left: Math.max(0, (el.scrollWidth - el.clientWidth) / 2),
      top: 0,
      behavior: smooth ? "smooth" : "auto",
    });
  }

  /** Kích thước THẬT của sơ đồ (đã trừ zoom): rect luôn đo theo pixel màn hình nên chia lại. */
  function measureChart() {
    const inner = innerRef.current;
    if (!inner) return null;
    const r = inner.getBoundingClientRect();
    const z = zoom || 1;
    return { w: r.width / z, h: r.height / z };
  }

  function applyZoom(next: number) {
    setZoom(next);
    // Zoom đổi → chiều rộng cuộn đổi; canh lại giữa SAU khi trình duyệt bố cục xong.
    requestAnimationFrame(() => centerCanvas(true));
  }

  const handleZoomIn = () => {
    setFitCapped(false);
    applyZoom(Math.min(1.5, Math.round((zoom + 0.15) * 100) / 100));
  };
  const handleZoomOut = () => {
    setFitCapped(false);
    applyZoom(Math.max(0.35, Math.round((zoom - 0.15) * 100) / 100));
  };
  const handleResetZoom = () => {
    setFitCapped(false);
    applyZoom(1);
  };

  // Gập/mở nhánh làm sơ đồ hẹp/rộng lại → lời cảnh báo "không lọt khung" cũ hết đúng.
  useEffect(() => setFitCapped(false), [collapsed]);

  /** "Xem toàn bộ" = thu vừa CẢ ngang lẫn dọc, không chỉ ngang. */
  const handleFitFull = () => {
    const el = canvasRef.current;
    const size = measureChart();
    if (!el || !size || size.w <= 0 || size.h <= 0) {
      applyZoom(0.45);
      return;
    }
    const raw = Math.min(el.clientWidth / size.w, el.clientHeight / size.h);
    // Dưới 35% thì chữ hết đọc được — thà chạm sàn và NÓI THẬT là chưa vừa,
    // còn hơn thu nhỏ tới mức vô dụng hoặc im lặng để người dùng tưởng nút hỏng.
    setFitCapped(raw < 0.35);
    // Làm tròn XUỐNG để không bao giờ thiếu 1px làm tràn lại.
    applyZoom(Math.min(1, Math.max(0.35, Math.floor(raw * 100) / 100)));
  };

  function dismissPanHint() {
    setPanHint(false);
    try {
      localStorage.setItem(PAN_HINT_KEY, "1");
    } catch {
      /* chế độ riêng tư chặn localStorage — bỏ qua, chỉ mất việc ghi nhớ */
    }
  }

  // Pointer Events + pointer capture: kéo ra ngoài khung vẫn không đứt tay
  // (mouse events cũ mất drag ngay khi con trỏ rời canvas).
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    if ((e.target as HTMLElement).closest("button, input, a, .rdx-org-node")) return;
    const el = canvasRef.current;
    if (!el) return;
    el.setPointerCapture(e.pointerId);
    dragRef.current = {
      x: e.clientX,
      y: e.clientY,
      scrollLeft: el.scrollLeft,
      scrollTop: el.scrollTop,
    };
    // Cờ kéo phải là REF: state React cập nhật sau khi render, kéo thật nhanh thì
    // pointermove đầu tiên chạy trước lúc state kịp đổi và nhát kéo đó rơi mất.
    // State chỉ còn để đổi con trỏ sang "nắm".
    draggingRef.current = true;
    setIsDragging(true);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = canvasRef.current;
    if (!draggingRef.current || !el) return;
    el.scrollLeft = dragRef.current.scrollLeft - (e.clientX - dragRef.current.x);
    el.scrollTop = dragRef.current.scrollTop - (e.clientY - dragRef.current.y);
    if (panHint) dismissPanHint();
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return;
    const el = canvasRef.current;
    if (el?.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
    draggingRef.current = false;
    setIsDragging(false);
  };

  // Mở chế độ Sơ đồ cây → canh vào giữa (gốc), chờ 1 nhịp cho cây dựng xong.
  useEffect(() => {
    if (viewMode !== "chart") return;
    const timer = setTimeout(() => centerCanvas(), 60);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode, departments]);

  // Drawer chi tiết (cột phải): 3 tab progressive-disclosure (mặc định mở tab Tổng quan).
  const [activeTab, setActiveTab] = useState<"overview" | "staff" | "roles">(
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
  // Ô "Ca làm việc của tổ" ĐÃ BỎ 2026-08-10 (cùng ô ca ở màn Máy): ca khai MỘT chỗ ở Nhân sự →
  // Ca kíp, không lặp lại ở từng tổ. Kèm theo đó `laTo` cũng gỡ — nó chỉ sinh ra để gate ô này.

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

  // Tình trạng một phòng. Xét TRƯỞNG TRƯỚC, người sau — thứ tự này là cả bug đã sửa:
  //
  // Bản cũ `if (employee_count === 0) return "empty"` thoát ngay ở dòng đầu, KHÔNG bao giờ xét tới
  // `head_user_id`. Mà badge chỉ có 2 nhánh (`no_head` / còn lại) nên `"empty"` rơi vào nhánh "Có
  // trưởng" ⇒ 5 trong 8 phòng của công ty đang hiện "Có trưởng" trong khi chưa gán ai, và chip lọc
  // đếm "Thiếu trưởng 0". Màn nói dối đúng chỗ người ta tin nó nhất.
  //
  // "Đã gán trưởng chưa" và "đã có người chưa" là HAI CHIỀU ĐỘC LẬP, gộp vào một enum là sai từ
  // gốc. Giờ trưởng quyết trước: phòng có trưởng mà chưa tuyển ai vẫn là `complete` (trưởng phòng
  // mới nhận việc), không tụt xuống `no_staff`.
  //
  // Cũng hết phụ thuộc vào `employee_count` cho việc xét trưởng — con số đó chỉ đếm hồ sơ RIÊNG của
  // phòng, không tính tổ con (department_service.py), nên phòng cha có người nằm hết ở tổ con vẫn
  // ra 0 và trước đây cũng bị gán nhầm là "có trưởng".
  function deptStatus(d: Department): "no_staff" | "no_head" | "complete" {
    if (d.head_user_id != null) return "complete";
    return (d.employee_count ?? 0) === 0 ? "no_staff" : "no_head";
  }

  // Đếm cho chip lọc cây: tổng · khối SX · văn phòng · thiếu trưởng · chưa có nhân sự.
  // Đếm RIÊNG hai loại chứ không gộp: gộp lại là mất đúng cái phân biệt vừa dựng ra — "có người mà
  // không ai phụ trách" là việc phải xử lý ngay, còn "phòng chưa tuyển ai" thì không.
  const treeStats = useMemo(() => {
    let sanXuat = 0;
    let kinhDoanh = 0;
    let giaoHang = 0;
    let noHead = 0;
    let noStaff = 0;
    for (const d of departments) {
      if (d.la_san_xuat) sanXuat += 1;
      if (d.la_kinh_doanh) kinhDoanh += 1;
      if (d.la_giao_hang) giaoHang += 1;
      const st = deptStatus(d);
      if (st === "no_head") noHead += 1;
      else if (st === "no_staff") noStaff += 1;
    }
    return {
      all: departments.length,
      san_xuat: sanXuat,
      kinh_doanh: kinhDoanh,
      giao_hang: giaoHang,
      van_phong: departments.length - sanXuat,
      no_head: noHead,
      no_staff: noStaff,
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
    if (treeFilter === "kinh_doanh" && !d.la_kinh_doanh) return false;
    if (treeFilter === "giao_hang" && !d.la_giao_hang) return false;
    if (treeFilter === "van_phong" && d.la_san_xuat) return false;
    if (treeFilter === "no_head" && deptStatus(d) !== "no_head") return false;
    if (treeFilter === "no_staff" && deptStatus(d) !== "no_staff") return false;
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
      api.rbac.roleTemplates(token).catch(() => [] as RoleTemplate[]),
    ])
      .then(([list, mods, mau]) => {
        if (cancelled) return;
        setDepartments(list);
        setModules(mods);
        setRoleTemplates(mau);
        // Tự động chọn phòng gốc hàng đầu (Root department) khi nạp màn hình để hiển thị ngay chi tiết
        const { roots: rts } = buildTree(list);
        const defaultId = rts[0]?.id ?? list[0]?.id ?? null;
        setSelectedId((prev) => (prev != null && list.some((d) => d.id === prev) ? prev : defaultId));
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
    setEditLaKinhDoanh(dept?.la_kinh_doanh ?? false);
    setEditLaGiaoHang(dept?.la_giao_hang ?? false);
    setEditIsKcs(dept?.is_kcs ?? false);
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
    setEditLaSanXuat(currentDept?.la_san_xuat ?? false);
    setEditLaKinhDoanh(currentDept?.la_kinh_doanh ?? false);
    setEditLaGiaoHang(currentDept?.la_giao_hang ?? false);
    setEditIsKcs(currentDept?.is_kcs ?? false);
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

  function openCreate(parentId?: number | null) {
    setNewName("");
    setNewDescription("");
    setNewParentId(parentId ?? null);
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
          // `has_piece_work` KHÔNG gửi từ đây (backend: không gửi = giữ nguyên) — cửa sửa
          // duy nhất là công tắc "Lương khoán / sản lượng" ở Cấu hình lương.
        },
        editLaSanXuat,
        editLaKinhDoanh,
        editLaGiaoHang,
        // Khoán km (đơn giá + %) ĐÃ DỜI sang Cấu hình lương — không gửi từ đây nữa.
        undefined,
        editIsKcs,
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

  function openAssignHeadQuick() {
    if (!currentDept) return;
    setAssignHeadTarget(currentDept.head_user_id ?? null);
    setAssignHeadError(null);
    setAssignHeadOpen(true);
  }

  async function submitAssignHeadQuick() {
    if (!token || selectedId == null || !currentDept || assignHeadBusy) return;
    setAssignHeadBusy(true);
    setAssignHeadError(null);
    try {
      await api.rbac.updateDepartment(
        token,
        selectedId,
        currentDept.name,
        assignHeadTarget,
        currentDept.description ?? null,
        currentDept.level_id ?? null,
        currentDept.parent_id ?? null,
        {
          salary_mechanism: currentDept.salary_mechanism ?? "cung",
          probation_ratio: currentDept.probation_ratio ?? 0.8,
        },
        currentDept.la_san_xuat,
      );
      await refresh(selectedId);
      setAssignHeadOpen(false);
      onDeptChanged?.();
    } catch (err) {
      if (err instanceof ApiError && (err.isConflict || err.status === 400)) {
        setAssignHeadError(err.message);
      } else {
        setAssignHeadError("Không thể chỉ định người đứng đầu. Vui lòng thử lại.");
      }
    } finally {
      setAssignHeadBusy(false);
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
      rows.map((r) =>
        r.module_key === moduleKey
          ? applyPermissionDependency(r, action, value)
          : r,
      ),
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

  /** Áp mẫu vào ma trận SỬA vai — THAY SẠCH, không trộn với quyền cũ.
   *  Trộn thì áp mẫu "Công nhân" lên một vai đang đầy quyền vẫn còn nguyên quyền cũ — đúng thứ
   *  vai mẫu sinh ra để tránh. Chỉ đổi state; chưa bấm Lưu thì chưa có gì xuống DB. */
  function apMauSuaVai(t: RoleTemplate) {
    setEditRoleMatrix(t.permissions.map((r) => ({ ...r })));
    setEditRoleError(null);
  }

  /** Áp mẫu vào ma trận THÊM vai mới. */
  function apMauThemVai(t: RoleTemplate) {
    setAddRoleMatrix(t.permissions.map((r) => ({ ...r })));
  }

  function toggleEditRole(moduleKey: string, action: ActionKey, value: boolean) {
    setEditRoleMatrix((rows) =>
      rows.map((r) =>
        r.module_key === moduleKey
          ? applyPermissionDependency(r, action, value)
          : r,
      ),
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

  /** Thẻ Cây Tổ Chức Trực Quan (Visual Card-Tile Org Tree):
   *  Caret + Icon SVG khối + Tên + Mã + Pill Khối SX + Micro metrics + Nút thêm phòng con nhanh khi hover. */
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
    const tinhTrang = deptStatus(d);

    // Lucide SVG Icon khối phòng ban
    const DeptIcon = d.parent_id == null
      ? Building2
      : d.la_san_xuat
      ? Factory
      : d.la_kinh_doanh
      ? Handshake
      : Briefcase;

    const kidsCount = childrenOf.get(d.id)?.length ?? 0;

    return (
      <div
        key={d.id}
        className={`rdx-tree__tile${isActive ? " is-active" : ""}${
          d.la_san_xuat ? " is-sx" : ""
        }`}
        role="button"
        tabIndex={0}
        aria-pressed={isActive}
        style={{ marginLeft: depth * 14 }}
        onClick={() => setSelectedId(d.id)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setSelectedId(d.id);
          }
        }}
      >
        <div className="rdx-tree__tile-left">
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
              <ChevronRight size={14} />
            </button>
          ) : (
            <span className="rdx-tree__caret rdx-tree__caret--leaf" aria-hidden="true" />
          )}

          <div className="rdx-tree__tile-icon-bg">
            <DeptIcon size={15} />
          </div>
        </div>

        <div className="rdx-tree__tile-main">
          <div className="rdx-tree__line1">
            <span className="rdx-tree__name">{d.name}</span>
            {d.code && <span className="rdx-tree__code">{d.code}</span>}
            {d.la_san_xuat && <span className="rdx-tree__pill">Khối SX</span>}
            {d.la_kinh_doanh && (
              <span className="rdx-tree__pill rdx-tree__pill--kd">Khối KD</span>
            )}
            {d.la_giao_hang && (
              <span className="rdx-tree__pill rdx-tree__pill--gh"
                    title="Người trong khối này hiện ở tab Nhân viên giao hàng và chọn được khi phân chuyến">
                Giao hàng
              </span>
            )}
          </div>

          <div className="rdx-tree__line2">
            <span className="rdx-tree__staff" title="Số lượng nhân sự">
              <Users size={12} />
              <span>{d.employee_count ?? 0}</span>
            </span>

            {/* Ba tình trạng, ba cách hiện. Chỉ `no_head` được tô CAM: phòng có người mà không ai
                phụ trách là việc phải xử lý ngay. Phòng chưa tuyển ai thì chưa có trưởng là bình
                thường ⇒ xám, để mắt còn bắt được chỗ cam thật sự (xem chú thích ở sơ đồ cây). */}
            {tinhTrang === "no_head" ? (
              <span className="rdx-tree__warn" title="Phòng đã có nhân sự nhưng chưa chỉ định Trưởng phòng">
                <span className="rdx-tree__dot rdx-tree__dot--warn" />
                Chưa chỉ định
              </span>
            ) : tinhTrang === "no_staff" ? (
              <span className="rdx-tree__muted" title="Phòng chưa có nhân sự nào, nên cũng chưa có Trưởng phòng">
                <span className="rdx-tree__dot rdx-tree__dot--muted" />
                Chưa có nhân sự
              </span>
            ) : (
              <span className="rdx-tree__head-ok" title={d.head_name ? `Trưởng phòng: ${d.head_name}` : "Đã có Trưởng phòng"}>
                <span className="rdx-tree__dot rdx-tree__dot--ok" />
                Có trưởng
              </span>
            )}

            {kidsCount > 0 && (
              <span className="rdx-tree__subcount" title="Số tổ/phòng trực thuộc">
                <FolderTree size={12} />
                <span>{kidsCount}</span>
              </span>
            )}
          </div>
        </div>

        {canCreateDept && (
          <button
            type="button"
            className="rdx-tree__add-sub"
            title={`Thêm phòng con trực thuộc ${d.name}`}
            onClick={(e) => {
              e.stopPropagation();
              openCreate(d.id);
            }}
          >
            <Plus size={13} />
          </button>
        )}
      </div>
    );
  }



  /** Đếm toàn bộ phòng nằm dưới một nhánh (theo đúng bộ lọc đang bật) — để nút gập
   *  nói được "còn 5 phòng bên dưới" thay vì chỉ đếm con trực tiếp. */
  function countBranch(dept: Department): number {
    const kids = (childrenOf.get(dept.id) ?? []).filter(
      (child) => !treeFiltersActive || matchesTree(child),
    );
    return kids.reduce((n, k) => n + 1 + countBranch(k), 0);
  }

  function renderOrgChartNode(dept: Department) {
    const kids = (childrenOf.get(dept.id) ?? []).filter((child) => {
      if (!treeFiltersActive) return true;
      return matchesTree(child);
    });
    const isCollapsed = collapsed.has(dept.id);
    const hasKids = kids.length > 0;
    const isOpen = hasKids && !isCollapsed;
    const isSelected = dept.id === selectedId;
    const tinhTrang = deptStatus(dept);
    const hiddenCount = hasKids && isCollapsed ? countBranch(dept) : 0;

    const DeptIcon = dept.parent_id == null
      ? Building2
      : dept.la_san_xuat
      ? Factory
      : dept.la_kinh_doanh
      ? Handshake
      : Briefcase;

    return (
      <div
        key={dept.id}
        className={`rdx-org-branch${isOpen ? " rdx-org-branch--open" : ""}`}
      >
        <div className="rdx-org-branch__parent">
          <div
            className={`rdx-org-node${isSelected ? " is-selected" : ""}${
              dept.la_san_xuat ? " is-sx" : ""
            }`}
            onClick={() => setSelectedId(dept.id)}
          >
            <div className="rdx-org-node__head">
              <div className="rdx-org-node__icon">
                <DeptIcon size={15} />
              </div>
              <div className="rdx-org-node__title-wrap">
                <div className="rdx-org-node__name" title={dept.name}>
                  {dept.name}
                </div>
                {dept.code && <span className="rdx-org-node__code">{dept.code}</span>}
              </div>
            </div>

            <div className="rdx-org-node__meta">
              <span className="rdx-org-node__badge" title="Số lượng nhân sự">
                <Users size={11} /> {dept.employee_count ?? 0}
              </span>

              {/* Chỉ CÁI CẦN XỬ LÝ mới được tô màu. Trước đây thẻ nào cũng có chip màu nên
                  cả sơ đồ rực lên, mắt không bắt được phòng nào đang thiếu trưởng.
                  Tên trưởng cũng KHÔNG rút gọn bằng từ cuối nữa: head_name có thể là chức
                  danh ("Tổ trưởng Tổ Chế bản") — cắt ra thành "bản", vô nghĩa. */}
              {tinhTrang === "no_head" ? (
                <span className="rdx-org-node__status rdx-org-node__status--warn"
                      title="Phòng đã có nhân sự nhưng chưa chỉ định Trưởng phòng">
                  <span className="rdx-org-node__dot rdx-org-node__dot--warn rdx-tree__dot--pulse" />
                  Thiếu TP
                </span>
              ) : tinhTrang === "no_staff" ? (
                <span className="rdx-org-node__status rdx-org-node__status--muted"
                      title="Phòng chưa có nhân sự nào, nên cũng chưa có Trưởng phòng">
                  <span className="rdx-org-node__dot rdx-org-node__dot--muted" />
                  Chưa có người
                </span>
              ) : (
                <span
                  className="rdx-org-node__status rdx-org-node__status--ok"
                  title={dept.head_name ? `Trưởng phòng: ${dept.head_name}` : "Đã gán Trưởng phòng, nhưng không tìm thấy tài khoản người đó"}
                >
                  <UserCheck size={10} />
                  {/* KHÔNG fallback về chữ "Có TP": `head_name` là null khi tài khoản trưởng đã bị
                      xoá (department_service._head_name trả None). In "Có TP" lúc đó là khẳng định
                      một điều sai — phòng đang trỏ vào một người không còn tồn tại, mà đó đúng là
                      thứ cần thấy để đi gán lại. */}
                  {dept.head_name ?? "TP không còn tài khoản"}
                </span>
              )}
            </div>

            {canCreateDept && (
              <div className="rdx-org-node__actions">
                <button
                  type="button"
                  className="rdx-org-node__act-btn"
                  title="Thêm phòng con"
                  onClick={(e) => {
                    e.stopPropagation();
                    openCreate(dept.id);
                  }}
                >
                  <Plus size={12} />
                </button>
              </div>
            )}

            {/* Gập/mở ngay tại thẻ — đây là cách rẻ nhất để cây khỏi tràn ngoài màn hình.
                Gập rồi thì nói luôn còn bao nhiêu phòng bên dưới, đừng bắt đoán. */}
            {hasKids && (
              <button
                type="button"
                className={`rdx-org-node__toggle${isCollapsed ? " is-collapsed" : ""}`}
                aria-expanded={!isCollapsed}
                aria-label={
                  isCollapsed
                    ? `Mở nhánh ${dept.name} — còn ${hiddenCount} phòng bên dưới`
                    : `Thu gọn nhánh ${dept.name}`
                }
                title={
                  isCollapsed ? `Mở nhánh — còn ${hiddenCount} phòng bên dưới` : "Thu gọn nhánh"
                }
                onClick={(e) => {
                  e.stopPropagation();
                  toggleCollapse(dept.id);
                }}
              >
                {isCollapsed ? (
                  <>
                    <ChevronDown size={11} />
                    <span className="rdx-org-node__toggle-n">{hiddenCount}</span>
                  </>
                ) : (
                  <ChevronUp size={11} />
                )}
              </button>
            )}
          </div>
        </div>

        {isOpen && (
          <div className="rdx-org-branch__children">
            {kids.map(renderOrgChartNode)}
          </div>
        )}
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
    // Khối Kinh doanh: quyết định ai vào được danh sách "NV phụ trách" ở màn Khách hàng — chip
    // này là chỗ duy nhất soi nhanh xem đã tick đúng phòng chưa.
    { key: "kinh_doanh", label: "Kinh doanh", n: treeStats.kinh_doanh },
    // Khối Giao hàng: quyết định ai hiện ở tab Nhân viên giao hàng và ai chọn được khi phân
    // chuyến — chip này là chỗ soi nhanh xem đã tick đúng phòng chưa.
    { key: "giao_hang", label: "Giao hàng", n: treeStats.giao_hang },
    { key: "van_phong", label: "Văn phòng", n: treeStats.van_phong },
    // Hai chip RIÊNG, cố ý không gộp: "Thiếu trưởng" là việc phải xử lý ngay (phòng có người mà
    // không ai phụ trách); "Chưa có nhân sự" chỉ là phòng mới khai, chưa tuyển ai. Gộp một số là
    // mất đúng cái phân biệt này — và trước đây gộp kiểu ngược lại nên chip luôn đếm 0.
    { key: "no_head", label: "Thiếu trưởng", n: treeStats.no_head },
    { key: "no_staff", label: "Chưa có nhân sự", n: treeStats.no_staff },
  ] as const;
  const tabs = [
    { key: "overview", label: "Tổng quan", count: undefined },
    { key: "staff", label: "Nhân sự", count: members.length },
    { key: "roles", label: "Vai trò & Quyền", count: roles.length },
  ] as const;

  return (
    <main className="depts rdx-dept">
      <header className="rdx-dept__head">
        <div className="rdx-dept__head-main">
          <p className="eyebrow">Nhân sự &amp; Lương</p>
          <h1 className="depts__title">Phòng ban</h1>
          <p className="depts__sub">
            Quản lý cơ cấu phòng ban, nhân sự và vai trò trong từng phòng.
          </p>
        </div>

        {/* ── Sleek Compact Metric Pills ─────────────────────────────────── */}
        <div className="rdx-compact-kpi" aria-label="Tóm tắt chỉ số cơ cấu">
          <div className="rdx-ckpi-item" title="Tổng số đơn vị cơ cấu phòng ban">
            <div className="rdx-ckpi-icon rdx-ckpi-icon--primary">
              <Building2 size={15} />
            </div>
            <div className="rdx-ckpi-body">
              <span className="rdx-ckpi-val">{treeStats.all}</span>
              <span className="rdx-ckpi-lbl">Phòng ban</span>
            </div>
          </div>

          <div className="rdx-ckpi-divider" aria-hidden="true" />

          <div className="rdx-ckpi-item" title="Tổng số nhân sự toàn công ty">
            <div className="rdx-ckpi-icon rdx-ckpi-icon--moss">
              <Users size={15} />
            </div>
            <div className="rdx-ckpi-body">
              <span className="rdx-ckpi-val">
                {departments.reduce((sum, d) => sum + (d.employee_count ?? 0), 0)}
              </span>
              <span className="rdx-ckpi-lbl">Nhân sự</span>
            </div>
          </div>

          <div className="rdx-ckpi-divider" aria-hidden="true" />

          <div className="rdx-ckpi-item" title="Số lượng phòng ban đã chỉ định Trưởng phòng">
            <div className="rdx-ckpi-icon rdx-ckpi-icon--amber">
              <UserCheck size={15} />
            </div>
            <div className="rdx-ckpi-body">
              <span className="rdx-ckpi-val">
                {treeStats.all - treeStats.no_head}/{treeStats.all}
              </span>
              <span className="rdx-ckpi-lbl" style={{ color: treeStats.no_head > 0 ? "#b45309" : "#166534" }}>
                {treeStats.no_head > 0 ? `${treeStats.no_head} chưa TP` : "Có TP"}
              </span>
            </div>
          </div>

          <div className="rdx-ckpi-divider" aria-hidden="true" />

          <div className="rdx-ckpi-item" title="Phân bổ giữa Khối Sản xuất & Văn phòng">
            <div className="rdx-ckpi-icon rdx-ckpi-icon--plum">
              <Factory size={15} />
            </div>
            <div className="rdx-ckpi-body">
              <span className="rdx-ckpi-val">{treeStats.san_xuat} SX / {treeStats.van_phong} VP</span>
              <span className="rdx-ckpi-lbl">Phân bổ</span>
            </div>
          </div>
        </div>
      </header>

      <div className="rdx-org-layout">
        <div className="rdx-org-toolbar">
          <div className="rdx-org-toolbar__row1">
            <div className="rdx-tree__search" style={{ width: "230px" }}>
              <Search size={15} className="rdx-tree__search-icon" />
              <input
                className="rdx-tree__search-input"
                placeholder="Tìm theo tên hoặc mã…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                aria-label="Tìm phòng ban"
              />
            </div>

            {/* ── View Mode Switcher ──────────────────────────────────── */}
            <div className="rdx-view-mode-toggle">
              <button
                type="button"
                className={`rdx-view-mode-btn${viewMode === "tree" ? " is-active" : ""}`}
                onClick={() => setViewMode("tree")}
                title="Xem dạng Cây Thẻ danh sách"
              >
                <LayoutGrid size={14} />
                <span>Danh sách</span>
              </button>
              <button
                type="button"
                className={`rdx-view-mode-btn${viewMode === "chart" ? " is-active" : ""}`}
                onClick={() => setViewMode("chart")}
                title="Xem dạng Sơ đồ Tổ chức Trực quan"
              >
                <Network size={14} />
                <span>Sơ đồ cây</span>
              </button>
            </div>

            <div className="rdx-tree__chips">
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

            <div className="rdx-org-toolbar__right">
              <button
                type="button"
                className="rdx-org-toolbar__btn"
                onClick={() => setCollapsed(new Set())}
                title="Mở tất cả các nhánh"
              >
                <ChevronDown size={14} />
                <span>Mở tất cả</span>
              </button>
              <button
                type="button"
                className="rdx-org-toolbar__btn"
                onClick={() => setCollapsed(new Set(departments.map((d) => d.id)))}
                title="Thu gọn tất cả các nhánh"
              >
                <ChevronUp size={14} />
                <span>Thu gọn tất cả</span>
              </button>
              {canCreateDept && (
                <Button type="button" variant="accent" onClick={() => openCreate(null)}>
                  <Plus size={15} /> Thêm phòng gốc
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Bề ngang hai cột khai bằng LỚP, không phải `style` inline: style inline thắng mọi
            luật CSS (trừ !important) nên khối @media ≤1024px trong redesign-phong-ban.css bị vô
            hiệu — ở điện thoại cột trái vẫn giữ 380px trong khung 296px và đẩy cả trang trượt
            ngang. Ba biến thể tương ứng ba nhánh cũ của biểu thức inline. */}
        <div
          className={`rdx-dept__body ${
            viewMode === "tree"
              ? "rdx-dept__body--tree"
              : selectedId != null
                ? "rdx-dept__body--org-sel"
                : "rdx-dept__body--org"
          }`}
        >
          {viewMode === "tree" ? (
            /* ── CỘT TRÁI: cây tổ chức dạng Danh sách Thẻ Card ──────────── */
            <aside className="rdx-dept__master" aria-label="Cây phòng ban">
              <div className="rdx-tree">
                {departments.length === 0 ? (
                  <div className="rdx-tree__empty">
                    <p className="rdx-tree__empty-title">Chưa có phòng ban nào</p>
                    <p className="depts__hint">
                      {canCreateDept
                        ? "Bấm “Thêm phòng gốc” để tạo phòng ban đầu tiên."
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
          ) : (
            /* ── INTERACTIVE ORG CHART CANVAS ──────────────────────────── */
            <div
              ref={canvasRef}
              className={`rdx-org-canvas-container${isDragging ? " is-dragging" : ""}`}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
            >
              {/* Floating Canvas Controls Bar */}
              <div className="rdx-canvas-controls">
                <button
                  type="button"
                  className="rdx-canvas-ctrl-btn"
                  onClick={handleZoomIn}
                  title="Phóng to (+)"
                >
                  <ZoomIn size={15} />
                </button>
                {/* Badge % KIÊM nút về 100% — nút reset riêng ẩn/hiện làm thanh nhảy chiều rộng. */}
                <button
                  type="button"
                  className="rdx-canvas-zoom-badge"
                  onClick={handleResetZoom}
                  disabled={zoom === 1}
                  title={zoom === 1 ? "Đang ở 100%" : "Bấm để về 100%"}
                >
                  {Math.round(zoom * 100)}%
                </button>
                <button
                  type="button"
                  className="rdx-canvas-ctrl-btn"
                  onClick={handleZoomOut}
                  title="Thu nhỏ (-)"
                >
                  <ZoomOut size={15} />
                </button>
                <button
                  type="button"
                  className="rdx-canvas-ctrl-btn rdx-canvas-ctrl-btn--text"
                  onClick={handleFitFull}
                  title="Thu vừa cả sơ đồ vào khung"
                >
                  <Maximize2 size={13} />
                  <span>Xem toàn bộ</span>
                </button>
              </div>

              {fitCapped ? (
                <p className="rdx-canvas-hint rdx-canvas-hint--warn" role="status">
                  <Move size={12} />
                  Đã thu nhỏ hết cỡ mà sơ đồ vẫn rộng hơn khung — thu gọn bớt nhánh hoặc kéo ngang
                  để xem tiếp.
                </p>
              ) : (
                panHint &&
                departments.length > 0 && (
                  <p className="rdx-canvas-hint" aria-hidden="true">
                    <Move size={12} />
                    Kéo để di chuyển sơ đồ
                  </p>
                )
              )}

              {departments.length === 0 ? (
                <div className="rdx-tree__empty">
                  <p className="rdx-tree__empty-title">Chưa có phòng ban nào</p>
                  <p className="depts__hint">
                    {canCreateDept
                      ? "Bấm “Thêm phòng gốc” để tạo phòng ban đầu tiên."
                      : "Chưa có phòng ban nào để xem."}
                  </p>
                </div>
              ) : listRows.length === 0 ? (
                <p className="depts__hint rdx-tree__none">Không có phòng ban khớp bộ lọc.</p>
              ) : (
                <div
                  ref={innerRef}
                  className="rdx-org-canvas-inner"
                  /* KHÔNG transition `zoom`: nó đổi bố cục, đang chạy dở thì scrollWidth
                     chưa chốt → canh giữa lệch. Đổi tỉ lệ tức thì, cuộn thì mới mượt. */
                  style={{ zoom }}
                >
                  <div className="rdx-org-tree-root">
                    {roots
                      .filter((r) => {
                        if (!treeFiltersActive) return true;
                        return matchesTree(r);
                      })
                      .map(renderOrgChartNode)}
                  </div>
                </div>
              )}
            </div>
          )}

        {/* ── CỘT PHẢI: drawer chi tiết (4 tab) ─────────────────────────── */}
        {(selectedId != null || viewMode === "tree") && (
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
                      {currentDept.la_kinh_doanh && (
                        <span className="rdx-drawer__pill rdx-drawer__pill--kd">Khối KD</span>
                      )}
                      {currentDept.la_giao_hang && (
                        <span className="rdx-drawer__pill rdx-drawer__pill--gh">Giao hàng</span>
                      )}
                      {currentDept.is_kcs && (
                        <span className="rdx-drawer__pill rdx-drawer__pill--gh">KCS</span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="rdx-drawer__headact">
                  <button
                    type="button"
                    className="rdx-drawer__close"
                    aria-label="Đóng chi tiết"
                    title="Đóng chi tiết phòng ban"
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
                    {t.count !== undefined && (
                      <span className="rdx-drawer__tab-badge">{t.count}</span>
                    )}
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

                    {/* Head Hero Card */}
                    <div className="rdx-head-hero">
                      {currentDept.head_name ? (
                        renderMemberAvatar(currentDept.head_name, {
                          isHead: true,
                          userId: currentDept.head_user_id,
                          avatarUrl: currentDept.head_avatar_url,
                          size: 48,
                        })
                      ) : (
                        <div className="rdx-head-hero__avatar rdx-head-hero__avatar--none">
                          <User size={20} />
                        </div>
                      )}
                      <div className="rdx-head-hero__info">
                        <span className="rdx-head-hero__label">
                          {currentDept.head_title || "Người đứng đầu"}
                        </span>
                        <span className="rdx-head-hero__name">
                          {currentDept.head_name ?? "Chưa chỉ định người đứng đầu"}
                        </span>
                        <span className="rdx-head-hero__sub">
                          {currentDept.head_name
                            ? "Phụ trách quản lý & điều hành đơn vị"
                            : "Bấm nút bên phải để chỉ định nhân sự điều hành ngay"}
                        </span>
                      </div>
                      {canSetHead && (
                        <button
                          type="button"
                          className={currentDept.head_name ? "rdx-drawer__ghost" : "rdx-head-hero__btn-highlight"}
                          onClick={openAssignHeadQuick}
                          style={{ flexShrink: 0 }}
                        >
                          {currentDept.head_name ? "Đổi" : "Chỉ định ngay"}
                        </button>
                      )}
                    </div>

                    <div className="rdx-ov__grid">
                      <div className="rdx-ov__item">
                        <span className="rdx-ov__k">Trực thuộc</span>
                        <span className="rdx-ov__v">
                          {parentName(currentDept.parent_id) ?? "Phòng gốc"}
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
                        <span className="rdx-ov__k">Khối kinh doanh</span>
                        <span className="rdx-ov__v">
                          {currentDept.la_kinh_doanh ? "Có" : "Không"}
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
                      <div className="rdx-subdept-section">
                        <p className="rdx-subdept-section__title">Các phòng/tổ trực thuộc</p>
                        <div className="rdx-subdept-grid">
                          {childrenOf.get(currentDept.id)?.map((child) => (
                            <div
                              key={child.id}
                              className="rdx-subdept-card"
                              onClick={() => setSelectedId(child.id)}
                            >
                              <span className="rdx-subdept-card__name" title={child.name}>
                                {child.name}
                              </span>
                              <span className="rdx-subdept-card__count">
                                {child.employee_count ?? 0} người
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
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
                    {detailLoading ? (
                      <p className="depts__status">Đang tải…</p>
                    ) : detailError ? (
                      <span className="depts__inline-error" role="alert">
                        {detailError}
                      </span>
                    ) : (
                      <>
                        {/* ⚠️ Thanh này phải nằm NGOÀI nhánh `members.length === 0`, đừng đẩy nó
                            trở lại vào trong. Trước đây cả thanh (kèm nút "Thêm nhân viên") nằm ở
                            nhánh else, còn dòng chữ "Bấm + Thêm nhân viên ở trên" nằm ở nhánh then
                            — hai nhánh loại trừ nhau nên câu hướng dẫn KHÔNG BAO GIỜ có thể đúng,
                            và phòng rỗng thì không còn đường nào thêm người đầu tiên.
                            Khuôn đúng để đối chiếu: nút "Thêm phòng gốc" ở thanh đầu trang, ngoài
                            mọi điều kiện rỗng.
                            Ô tìm + lọc thì ngược lại: chỉ có nghĩa khi đã có người, nên ẩn khi rỗng.
                            Không quyền thêm + phòng rỗng ⇒ thanh chẳng còn gì, bỏ hẳn khay trống. */}
                    {(members.length > 0 || canAddEmployee) && (
                      <div
                        className={`depts__staff-toolbar${
                          canBulk && selectedMemberIds.size > 0 ? " depts__staff-toolbar--morphed" : ""
                        }`}
                        style={{ marginBottom: 12 }}
                      >
                        {canBulk && selectedMemberIds.size > 0 ? (
                          /* ── MORPHED STATE: Contextual Bulk Action Bar ─────────── */
                          <div className="depts__morph-bar" role="region" aria-label="Thao tác hàng loạt">
                            <div className="depts__morph-left">
                              <div className="depts__dock-counter">
                                <CheckCircle2 size={15} className="depts__dock-counter-icon" />
                                <span>
                                  Đã chọn <strong key={selectedMemberIds.size} className="depts__dock-pop-num">{selectedMemberIds.size}</strong> người
                                </span>
                              </div>
                              <button
                                type="button"
                                className="depts__dock-clear-btn"
                                title="Nhấn Esc để bỏ chọn nhanh"
                                onClick={() => setSelectedMemberIds(new Set())}
                              >
                                <X size={14} />
                                <span>Bỏ chọn</span>
                                <kbd className="depts__dock-kbd">Esc</kbd>
                              </button>
                            </div>

                            <div className="depts__morph-actions">
                              {canAssignRole && roles.length > 0 && (
                                <div className="depts__dock-group">
                                  <div className="depts__dock-label-tag">
                                    <ShieldCheck size={14} className="depts__dock-icon--shield" />
                                    <span>Vai trò</span>
                                  </div>
                                  <div className="depts__dock-select-wrap">
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
                                    className="depts__dock-btn-accent"
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
                                  {selectedWithoutAccount > 0 && (
                                    <span className="depts__dock-warning-chip" title={`${selectedWithoutAccount} người chưa có tài khoản hệ thống`}>
                                      <AlertCircle size={12} /> {selectedWithoutAccount} chưa có TK
                                    </span>
                                  )}
                                </div>
                              )}

                              {canTransfer && (
                                <div className="depts__dock-group">
                                  <div className="depts__dock-label-tag">
                                    <ArrowRightLeft size={14} className="depts__dock-icon--transfer" />
                                    <span>Chuyển sang</span>
                                  </div>
                                  <div className="depts__dock-select-wrap">
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
                                    className="depts__dock-btn-accent"
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
                            </div>
                          </div>
                        ) : (
                          /* ── NORMAL STATE: Search & Filter Toolbar ─────────────── */
                          <>
                            {members.length > 0 && (
                              <>
                                <div className="rdx-tree__search" style={{ flex: "1 1 auto", maxWidth: "240px" }}>
                                  <Search size={14} className="rdx-tree__search-icon" />
                                  <input
                                    className="rdx-tree__search-input"
                                    placeholder="Tìm tên, mã, tài khoản…"
                                    value={memberSearch}
                                    onChange={(e) => {
                                      setMemberSearch(e.target.value);
                                      setMemberPage(1);
                                    }}
                                    aria-label="Tìm nhân sự"
                                  />
                                </div>

                                <div style={{ width: "160px", flexShrink: 0 }}>
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
                              </>
                            )}
                            {canAddEmployee && (
                              <button
                                type="button"
                                className="rdx-head-hero__btn-highlight"
                                style={{ height: "34px", fontSize: "12px", padding: "0 12px", flexShrink: 0 }}
                                disabled={!empMeta}
                                title={empMeta
                                  ? undefined
                                  : "Chưa nạp được danh mục phòng/vai trò/ca. Tải lại trang rồi thử lại."}
                                onClick={() => setWizardOpen(true)}
                              >
                                <Plus size={14} /> Thêm nhân viên
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    )}

                    {members.length === 0 ? (
                      <p className="depts__hint">
                        {canAddEmployee
                          ? "Phòng chưa có nhân sự. Bấm “+ Thêm nhân viên” ở trên để thêm người đầu tiên."
                          : "Phòng chưa có nhân sự. Thêm người ở màn “Hồ sơ nhân sự”."}
                      </p>
                    ) : (
                      <>

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
                            {pageMembers.map((m) => {
                              const isChecked = selectedMemberIds.has(m.employee_id);
                              return (
                                <li
                                  key={m.employee_id}
                                  className={`depts__member${isChecked ? " is-selected" : ""}`}
                                >
                                  {canBulk && (
                                    <input
                                      type="checkbox"
                                      className="depts__member-check"
                                      checked={isChecked}
                                      onChange={() => toggleMember(m.employee_id)}
                                      aria-label={`Chọn ${m.name}`}
                                    />
                                  )}
                                  {renderMemberAvatar(m.name, {
                                    isHead: m.is_head,
                                    userId: m.user_id,
                                    username: m.username,
                                    avatarUrl: m.avatar_url,
                                    size: 34,
                                  })}
                                  <div className="depts__member-main">
                                    <div className="depts__member-line">
                                      <span className="depts__member-name">{m.name}</span>
                                      {m.code && (
                                        <span className="depts__member-code">{m.code}</span>
                                      )}
                                      {m.is_head && (
                                        <span className="depts__badge--head">
                                          Trưởng phòng
                                        </span>
                                      )}
                                    </div>
                                    <div className="depts__member-sub">
                                      {m.position && <span>{m.position}</span>}
                                      {m.username && (
                                        <span className="depts__member-user">@{m.username}</span>
                                      )}
                                    </div>
                                  </div>

                                  <div className="depts__member-right">
                                    {m.role_name && (
                                      <span className="depts__role-pill">{m.role_name}</span>
                                    )}
                                    {m.user_id == null ? (
                                      <span className="depts__status-pill depts__status-pill--no-acc">
                                        ● Chưa có tài khoản
                                      </span>
                                    ) : m.is_active ? (
                                      <span className="depts__status-pill depts__status-pill--active">
                                        ● Đang hoạt động
                                      </span>
                                    ) : (
                                      <span className="depts__status-pill depts__status-pill--locked">
                                        ● Đã khóa
                                      </span>
                                    )}
                                  </div>
                                </li>
                              );
                            })}
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
                            templates={roleTemplates}
                            onApplyTemplate={apMauSuaVai}
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
        )}
      </div>
    </div>

      {/* ── Modal: chỉnh sửa thông tin phòng (mở từ tab Tổng quan / nút Sửa) ── */}
      {currentDept && (
        <ConfirmDialog
          open={infoOpen}
          title={
            <div style={{ display: "flex", alignItems: "center", gap: 12, width: "100%", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div className="rdx-modal-header-badge">
                  <Building2 size={20} />
                </div>
                <div className="rdx-modal-header-title">
                  <h2 className="rdx-modal-header-h2">Chỉnh sửa thông tin phòng ban</h2>
                  <p className="rdx-modal-header-sub">Cập nhật tên, cơ cấu trực thuộc và nhân sự điều hành</p>
                </div>
              </div>
            </div>
          }
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
                Tên phòng ban <span className="depts__req">*</span>
              </label>
              <input
                id="dept-name"
                className={`input${saveError ? " input--error" : ""}`}
                value={editName}
                placeholder="VD: Hành chính nhân sự"
                onChange={(e) => {
                  setEditName(e.target.value);
                  setDirty(true);
                  if (saveError) setSaveError(null);
                }}
              />
            </div>

            <div className="field depts__field--full">
              <label className="field__label" htmlFor="dept-desc">
                Mô tả chức năng
              </label>
              <textarea
                id="dept-desc"
                className="input depts__textarea"
                rows={2}
                placeholder="Nhập chức năng, nhiệm vụ chính của phòng ban…"
                value={editDescription}
                onChange={(e) => {
                  setEditDescription(e.target.value);
                  setDirty(true);
                }}
              />
            </div>

            <div className="field">
              <span className="field__label depts__label">
                Đơn vị Trực thuộc
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

            <div className="field">
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

            {/* Switch Card Tương tác cho "Bộ phận Sản xuất" */}
            <div className="field depts__field--full">
              <div
                className={`rdx-switch-card${editLaSanXuat ? " is-checked" : ""}`}
                onClick={() => {
                  setEditLaSanXuat(!editLaSanXuat);
                  setDirty(true);
                }}
              >
                <div className="rdx-switch-card__left">
                  <div className="rdx-switch-card__icon">
                    <Factory size={20} />
                  </div>
                  <div className="rdx-switch-card__main">
                    <span className="rdx-switch-card__title">
                      Bộ phận thuộc Khối Sản xuất
                      <InfoHint label="Đánh dấu phòng/khối thuộc SẢN XUẤT: cả cây con (đơn vị trực thuộc) tự coi là sản xuất và lên phân hệ Sản xuất." />
                    </span>
                    <span className="rdx-switch-card__desc">
                      Tự động liên kết các đơn vị trực thuộc vào phân hệ Quản lý &amp; Đơn hàng Sản xuất
                    </span>
                  </div>
                </div>
                <div className="rdx-toggle-switch" aria-hidden="true" />
              </div>
            </div>

            {/* Switch Card "Bộ phận Kinh doanh" — cặp đôi với Khối Sản xuất, cùng luật kế thừa
                cây con. Quyết định ai vào được hộp chọn "NV phụ trách" ở màn Khách hàng. */}
            <div className="field depts__field--full">
              <div
                className={`rdx-switch-card${editLaKinhDoanh ? " is-checked" : ""}`}
                onClick={() => {
                  setEditLaKinhDoanh(!editLaKinhDoanh);
                  setDirty(true);
                }}
              >
                <div className="rdx-switch-card__left">
                  <div className="rdx-switch-card__icon">
                    <Handshake size={20} />
                  </div>
                  <div className="rdx-switch-card__main">
                    <span className="rdx-switch-card__title">
                      Bộ phận thuộc Khối Kinh doanh
                      <InfoHint label="Đánh dấu phòng/khối thuộc KINH DOANH: cả cây con tự coi là kinh doanh. Người trong khối này là người được giao phụ trách khách hàng. Chưa tick phòng nào thì hệ thống tạm suy theo quyền module Khách hàng." />
                    </span>
                    <span className="rdx-switch-card__desc">
                      Người trong khối được giao phụ trách khách hàng — hiện trong danh sách NV phụ
                      trách ở màn Khách hàng
                    </span>
                  </div>
                </div>
                <div className="rdx-toggle-switch" aria-hidden="true" />
              </div>
            </div>

            {/* Switch Card "Bộ phận Giao hàng" — cùng luật kế thừa cây con với hai cờ trên.
                Quyết định AI hiện trong tab Nhân viên giao hàng. Trước 20/08/2026 tab đó lọc
                theo quyền RBAC rồi bỏ ai chưa có chuyến, nên tài xế mới tuyển không hiện ra. */}
            <div className="field depts__field--full">
              <div
                className={`rdx-switch-card${editLaGiaoHang ? " is-checked" : ""}`}
                onClick={() => {
                  setEditLaGiaoHang(!editLaGiaoHang);
                  setDirty(true);
                }}
              >
                <div className="rdx-switch-card__left">
                  <div className="rdx-switch-card__icon">
                    <Truck size={20} />
                  </div>
                  <div className="rdx-switch-card__main">
                    <span className="rdx-switch-card__title">
                      Bộ phận Giao hàng
                      <InfoHint label="Đánh dấu phòng/tổ làm GIAO HÀNG: cả cây con tự coi là giao hàng. Mọi người trong khối này hiện ở tab Nhân viên giao hàng — kể cả người chưa chạy chuyến nào, để còn phân chuyến cho họ." />
                    </span>
                    <span className="rdx-switch-card__desc">
                      Người trong khối là tài xế — hiện ở tab Nhân viên giao hàng để phân chuyến và
                      theo dõi km
                    </span>
                  </div>
                </div>
                <div className="rdx-toggle-switch" aria-hidden="true" />
              </div>
            </div>

            {/* Switch Card "Tổ KCS đích danh" — KHÔNG kế thừa cây con (khác 3 cờ trên). Gate
                phát hành bài ghép (spec §3.1/§14) yêu cầu bước KCS cuối nằm ở một phòng có cờ
                này mới cho chốt nghiệm thu. */}
            <div className="field depts__field--full">
              <div
                className={`rdx-switch-card${editIsKcs ? " is-checked" : ""}`}
                onClick={() => {
                  setEditIsKcs(!editIsKcs);
                  setDirty(true);
                }}
              >
                <div className="rdx-switch-card__left">
                  <div className="rdx-switch-card__icon">
                    <ShieldCheck size={20} />
                  </div>
                  <div className="rdx-switch-card__main">
                    <span className="rdx-switch-card__title">
                      Tổ KCS đích danh
                      <InfoHint label="Đánh dấu ĐÍCH DANH phòng/tổ này là KCS — KHÔNG kế thừa cho cây con. Dùng để chốt bước kiểm tra chất lượng cuối trong routing sản xuất; bài ghép chỉ phát hành được khi có bước KCS cuối nằm ở một phòng có cờ này." />
                    </span>
                    <span className="rdx-switch-card__desc">
                      Bắt buộc để bước KCS cuối trong routing sản xuất được công nhận khi phát hành
                    </span>
                  </div>
                </div>
                <div className="rdx-toggle-switch" aria-hidden="true" />
              </div>
            </div>

            {/* Nút gạt "Tổ hưởng lương khoán" ĐÃ ẨN 04/09/2026 — cờ
                `departments.has_piece_work` nay chỉ còn MỘT cửa sửa: Lương → Cấu hình lương →
                công tắc "Lương khoán / sản lượng" (chiều đó ghi ngược về cờ này). Bật/tắt ở đây
                KHÔNG đụng `department_salary_components` nên hai màn lệch nhau khi tổ đã khai
                dòng lương. Trạng thái vẫn xem được ở khối Tổng quan. */}

            {/* Thuộc tính lương thử việc */}
            <div className="field depts__field--full">
              <span className="field__label depts__label">Tỷ lệ Lương thử việc</span>
              <div className="rdx-info-card">
                <span className="rdx-info-card__badge">
                  {companyProbationRatio != null
                    ? `${Math.round(companyProbationRatio * 100)}%`
                    : "—"}
                </span>
                <span className="rdx-info-card__text">
                  Tỷ lệ lương thử việc áp dụng chung toàn công ty (Cấu hình tại <strong>Lương → Cấu hình lương</strong>)
                </span>
              </div>
            </div>
          </div>
        </ConfirmDialog>
      )}

      {/* Quick Modal: Chỉ định Trưởng phòng trực tiếp từ Head Hero Card */}
      {currentDept && (
        <ConfirmDialog
          open={assignHeadOpen}
          title={
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div className="rdx-modal-header-badge">
                <UserCheck size={20} />
              </div>
              <div className="rdx-modal-header-title">
                <h2 className="rdx-modal-header-h2">Chỉ định {currentDept.head_title || "Người đứng đầu"}</h2>
                <p className="rdx-modal-header-sub">Chọn nhân sự điều hành cho phòng {currentDept.name}</p>
              </div>
            </div>
          }
          confirmLabel="Lưu chỉ định"
          busy={assignHeadBusy}
          error={assignHeadError}
          onConfirm={submitAssignHeadQuick}
          onCancel={() => {
            if (!assignHeadBusy) setAssignHeadOpen(false);
          }}
        >
          <div className="rdx-candidate-picker">
            <p className="depts__hint" style={{ marginBottom: 12 }}>
              Danh sách ứng viên điều hành thuộc phòng ban này hoặc các đơn vị con trực thuộc:
            </p>

            <div className="rdx-candidate-list">
              {/* Option 1: Clear current head */}
              <div
                className={`rdx-candidate-card${assignHeadTarget === null ? " is-selected" : ""}`}
                onClick={() => setAssignHeadTarget(null)}
              >
                <div className="rdx-candidate-card__left">
                  <input
                    type="radio"
                    className="rdx-candidate-radio"
                    name="headCandidate"
                    checked={assignHeadTarget === null}
                    onChange={() => setAssignHeadTarget(null)}
                  />
                  <div className="rdx-candidate-avatar" style={{ background: "#f1f5f9", color: "#64748b" }}>
                    —
                  </div>
                  <div className="rdx-candidate-info">
                    <span className="rdx-candidate-name">— Chưa chỉ định —</span>
                    <span className="rdx-candidate-username">Tạm thời để trống vị trí điều hành</span>
                  </div>
                </div>
              </div>

              {/* Candidate options */}
              {headCandidates.length === 0 ? (
                <p className="depts__hint" style={{ padding: 12, textAlign: "center" }}>
                  Chưa có nhân sự trong phòng hoặc nhánh con để chỉ định.
                </p>
              ) : (
                headCandidates.map((u) => {
                  const isSel = assignHeadTarget === u.id;
                  const isCurrent = currentDept.head_user_id === u.id;
                  return (
                    <div
                      key={u.id}
                      className={`rdx-candidate-card${isSel ? " is-selected" : ""}`}
                      onClick={() => setAssignHeadTarget(u.id)}
                    >
                      <div className="rdx-candidate-card__left">
                        <input
                          type="radio"
                          className="rdx-candidate-radio"
                          name="headCandidate"
                          checked={isSel}
                          onChange={() => setAssignHeadTarget(u.id)}
                        />
                        {renderMemberAvatar(u.name, {
                          userId: u.id,
                          username: u.username,
                          avatarUrl: u.avatar_url,
                          size: 36,
                        })}
                        <div className="rdx-candidate-info">
                          <span className="rdx-candidate-name">{u.name}</span>
                          <span className="rdx-candidate-username">@{u.username}</span>
                        </div>
                      </div>

                      {isCurrent && (
                        <span className="rdx-candidate-current-badge">Đang phụ trách</span>
                      )}
                    </div>
                  );
                })
              )}
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

      {/* Create department form (popup). */}
      <ConfirmDialog
        open={createOpen}
        title={
          <div style={{ display: "flex", alignItems: "center", gap: 12, width: "100%", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div className="rdx-modal-header-badge">
                <Building2 size={20} />
              </div>
              <div className="rdx-modal-header-title">
                <h2 className="rdx-modal-header-h2">Tạo phòng ban mới</h2>
                <p className="rdx-modal-header-sub">Thêm mới đơn vị cơ cấu, thiết lập cấp trực thuộc và chức năng</p>
              </div>
            </div>
          </div>
        }
        wide
        confirmLabel="Tạo phòng ban"
        busy={creating}
        confirmDisabled={!newName.trim()}
        onConfirm={submitCreate}
        onCancel={closeCreate}
      >
        <div className="depts__form-grid">
          <div className="field depts__field--full">
            <label className="field__label" htmlFor="new-dept-name">
              Tên phòng ban <span className="depts__req">*</span>
            </label>
            <input
              id="new-dept-name"
              className={`input${createError ? " input--error" : ""}`}
              placeholder="VD: Phòng Thiết kế &amp; Tạo mẫu"
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

          <div className="field depts__field--full">
            <span className="field__label">Đơn vị trực thuộc</span>
            <Select
              portal
              ariaLabel="Đơn vị trực thuộc"
              value={newParentId}
              placeholder="— Không (đơn vị phòng gốc) —"
              onChange={(v) => setNewParentId(v)}
              options={[
                { value: null, label: "— Không (đơn vị phòng gốc) —" },
                ...departments.map((d) => ({
                  value: d.id,
                  label: d.name,
                  hint: d.code || undefined,
                })),
              ]}
            />
          </div>

          <div className="field depts__field--full">
            <label className="field__label" htmlFor="new-dept-desc">
              Mô tả chức năng &amp; phạm vi
            </label>
            <textarea
              id="new-dept-desc"
              className="input depts__textarea"
              placeholder="Nhập chức năng, nhiệm vụ chính của phòng ban..."
              rows={3}
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
            templates={roleTemplates}
            onApplyTemplate={apMauThemVai}
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
