"""Role-management business logic (the Vai trò admin screen).

Framework-agnostic: raises domain errors the router maps to HTTP. Owns role
creation (with per-department name dedup) and reading/saving a role's permission
matrix (CRUD + scope per module), writing an audit row on every change.
"""
from __future__ import annotations

from ..catalog_registry import MODULE_KEYS
from ..models.role import Role, RolePermission
from .role_templates import danh_sach_mau
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.rbac_repo import DepartmentRepository, ModuleRepository, RoleRepository
from ..repositories.user_repo import UserRepository


class RoleError(Exception):
    """Base for role-management domain errors."""


class RoleNameTaken(RoleError):
    """A role with that name already exists in the department."""


class RoleNotFound(RoleError):
    """No role with that id."""


class DepartmentNotFound(RoleError):
    """No department with that id."""


class RoleInUse(RoleError):
    """A role still assigned to users cannot be deleted."""

    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(
            f"Không thể xóa: còn {count} người dùng đang giữ vai trò này. "
            "Hãy chuyển họ sang vai trò khác trước."
        )


# Module DANH MỤC — dữ liệu dùng chung toàn công ty, KHÔNG có phạm vi own/department. UI đã bỏ
# dropdown Phạm vi ở nhóm này; ép `all` khi lưu để vai mới (mặc định `own`) không bị bó âm thầm
# nếu sau này có ai bật lọc theo scope.
#
# 11 khoá danh mục lấy từ `catalog_registry` (thêm màn danh mục là tự có mặt ở đây, không phải
# nhớ chép sang). Ngoài danh mục thì liệt kê tay bên dưới — registry chỉ nói về danh mục.
SCOPELESS_MODULES = frozenset(MODULE_KEYS) | {
    # Kỹ thuật máy (12/08/2026): phiếu sửa chữa / bảo trì là việc chung của xưởng — không có khái
    # niệm "phiếu của tôi", nên bày dropdown Phạm vi chỉ khiến người cấp quyền tưởng mình vừa giới
    # hạn được cái gì.
    "ky_thuat_may",
    # Ba màn tách khỏi `san_xuat` ngày 17/08/2026. Đã soi: KHÔNG router nào của chúng đọc scope
    # (`bai_ghep.py` · `xep_lich.py` · `ke_hoach_vat_tu.py` đều 0 lần) — bài ghép và lịch xưởng là
    # bức tranh chung, không có "bài ghép của tôi". Riêng `san_xuat` KHÔNG vào đây: `lsx.py` đọc
    # scope thật (`_owner_ids_for_scope`) để thợ chỉ thấy lệnh của mình.
    "ke_hoach_vat_tu",
    "bai_ghep",
    "bai_ghep_2",
    "xep_lich",
    # Phiếu bảo trì tách khỏi `ky_thuat_may` cùng ngày, thừa hưởng đúng lý do của khoá mẹ.
    "phieu_bao_tri",
}

READ_IMPLYING_KEYS = (
    "can_create",
    "can_update",
    "can_delete",
    "can_reassign",
    "can_export",
    "can_view_debt",
    "can_view_discount",
    "can_approve",
    "can_manage_status",
    "can_reset_password",
    "can_lock",
    "can_revoke_sessions",
    "can_assign_role",
    "can_transfer",
    "can_set_head",
    "can_requote",
    "can_manage_price",
    "can_cancel",
    "can_manage_permissions",
    "can_clone",
    "can_toggle_active",
    "can_reparent",
    "can_view_salary",
    "can_edit_salary",
    "can_adjust",
    "can_view_log",
    "can_approve_exception",
    "can_set_credit_terms",
    "can_record_deposit",
    "can_assign_work",
    "can_record_output",
    "can_handover",
    "can_request",
    "can_view_stock",
    "can_view_cost",
    "can_set_threshold",
    "can_post",
    "can_close_book",
)


#: Mọi cột boolean của `role_permissions`, lấy thẳng từ model — thêm cột quyền mới là bảng vai mẫu
#: tự biết, không phải nhớ sửa thêm chỗ này.
_COT_QUYEN = [
    c.name for c in RolePermission.__table__.columns
    if c.name not in ("id", "role_id", "module_key", "scope")
]


class RoleService:
    def __init__(
        self,
        roles: RoleRepository,
        modules: ModuleRepository,
        departments: DepartmentRepository,
        audit: AuditLogRepository,
        users: UserRepository,
    ) -> None:
        self.roles = roles
        self.modules = modules
        self.departments = departments
        self.audit = audit
        self.users = users

    def list_departments(self):
        return self.departments.list_all()

    def list_roles(self, department_id: int) -> list[Role]:
        return self.roles.list_by_department(department_id)

    def create_role(self, *, name: str, department_id: int, actor_id: int | None) -> Role:
        dept = self.departments.get_by_id(department_id)
        if dept is None:
            raise DepartmentNotFound("Không tìm thấy phòng ban")
        name = name.strip()
        if self.roles.get_by_name_and_department(name, department_id) is not None:
            raise RoleNameTaken("Tên vai trò đã tồn tại trong phòng này")
        role = self.roles.create(name=name, department_id=department_id)
        self.audit.create(
            actor_user_id=actor_id,
            action="create_role",
            target=f"role:{role.id}",
            detail=f"{dept.name} / {name}",
        )
        return role

    def rename_role(self, *, role_id: int, name: str, actor_id: int | None) -> Role:
        role = self.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound("Không tìm thấy vai trò")
        name = name.strip()
        clash = self.roles.get_by_name_and_department(name, role.department_id)
        if clash is not None and clash.id != role_id:
            raise RoleNameTaken("Tên vai trò đã tồn tại trong phòng này")
        old = role.name
        self.roles.update_name(role, name)
        self.audit.create(
            actor_user_id=actor_id,
            action="rename_role",
            target=f"role:{role_id}",
            detail=f"{old} → {name}",
        )
        return role

    def delete_role(self, *, role_id: int, actor_id: int | None) -> None:
        role = self.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound("Không tìm thấy vai trò")
        in_use = self.users.count_by_role(role_id)
        if in_use > 0:
            raise RoleInUse(in_use)
        name = role.name
        self.roles.delete(role)
        self.audit.create(
            actor_user_id=actor_id,
            action="delete_role",
            target=f"role:{role_id}",
            detail=name,
        )

    def list_modules(self) -> list[dict]:
        """Danh mục module, kèm những "việc" ĐÃ XÁC MINH là chết ở màn đó.

        Ma trận tắt + khoá + hover cảnh báo đúng mấy ô này. KHÔNG suy ngược từ "cái gì máy chủ
        không gác thì chết" — bản đầu làm vậy và khoá nhầm hàng loạt ô chỉ thi hành ở giao diện
        (In/xuất phiếu · Đặt trưởng phòng · Xem lương…). Xem `deps.O_CHET_DA_XAC_MINH`.
        """
        from ..deps import O_CHET_DA_XAC_MINH

        return [
            {
                "key": m.key,
                "label": m.label,
                "viec_chet": sorted(a for (k, a) in O_CHET_DA_XAC_MINH if k == m.key),
            }
            for m in self.modules.list_all()
        ]

    def role_templates(self) -> list[dict]:
        """Bảng vai mẫu, mỗi mẫu kèm ma trận ĐẦY ĐỦ theo danh mục module hiện có.

        Trả đủ mọi module (cờ ngoài mẫu = tắt) chứ không chỉ phần mẫu khai: giao diện thay thẳng
        state là xong, không phải trộn với quyền cũ của vai — trộn nửa vời thì áp mẫu "Công nhân"
        lên một vai đang có đầy quyền vẫn còn nguyên quyền cũ, đúng thứ vai mẫu sinh ra để tránh.

        Khoá module nào mẫu khai mà DB chưa có (mẫu đi trước migration) thì BỎ QUA — thà thiếu một
        dòng còn hơn trả về khoá không tồn tại rồi lưu xuống làm vỡ khoá ngoại.
        """
        khoa_co_that = [m.key for m in self.modules.list_all()]
        ket: list[dict] = []
        for mau in danh_sach_mau():
            rows = []
            for khoa in khoa_co_that:
                cai_dat = mau["quyen"].get(khoa, {})
                dong = {"module_key": khoa, "scope": cai_dat.get("scope", "own")}
                for cot in _COT_QUYEN:
                    dong[cot] = bool(cai_dat.get(cot, False))
                # HAI Ô MẶC ĐỊNH luôn BẬT trong mọi mẫu.
                # ⚠️ Không có mấy dòng này thì áp mẫu = GỠ chúng: ma trận trả về là bản ĐẦY ĐỦ và
                # giao diện thay sạch, nên khoá nào mẫu không khai sẽ về tắt. Áp mẫu "Công nhân"
                # cho một vai thợ là thợ hết tự chấm công được — đúng loại hồi quy mà cả đợt phân
                # quyền này sinh ra để chặn. Đo được khi soi giao diện thật 11/08/2026.
                # Ép ở ĐÂY chứ không bắt từng mẫu tự khai: thêm mẫu thứ sáu là quên ngay.
                if khoa in RoleRepository.O_MAC_DINH:
                    dong["can_read"] = True
                rows.append(dong)
            ket.append({
                "key": mau["key"], "label": mau["label"], "mo_ta": mau["mo_ta"],
                "permissions": rows,
            })
        return ket

    def get_matrix(self, role_id: int) -> list[dict]:
        """Full matrix for a role: one row per module, merged with stored permissions
        (modules with no stored row default to all-false / own scope)."""
        role = self.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound("Không tìm thấy vai trò")
        stored = {p.module_key: p for p in self.roles.permissions_for(role_id)}
        rows: list[dict] = []
        for module in self.modules.list_all():
            p = stored.get(module.key)
            rows.append(
                {
                    "module_key": module.key,
                    "can_read": bool(p.can_read) if p else False,
                    "can_create": bool(p.can_create) if p else False,
                    "can_update": bool(p.can_update) if p else False,
                    "can_delete": bool(p.can_delete) if p else False,
                    "scope": p.scope if p else "own",
                    "can_reassign": bool(p.can_reassign) if p else False,
                    "can_export": bool(p.can_export) if p else False,
                    "can_view_debt": bool(p.can_view_debt) if p else False,
                    "can_view_discount": bool(p.can_view_discount) if p else False,
                    "can_approve": bool(p.can_approve) if p else False,
                    "can_manage_status": bool(p.can_manage_status) if p else False,
                    "can_view_log": bool(p.can_view_log) if p else False,
                    # ⚠️ BA CỘT NÀY TỪNG BỊ SÓT Ở ĐÂY (vá 11/08/2026). `save_matrix` lưu đúng,
                    # máy chủ gác đúng, chỉ đường ĐỌC không trả về ⇒ công tắc trên ma trận luôn
                    # hiện TẮT dù quản trị đã bật và đã Lưu. Người cấp quyền tick đi tick lại,
                    # tưởng hệ thống không nhận. Guard `test_moi_cot_quyen_deu_di_het_duong_ong`
                    # nay soi RIÊNG hàm này nên bỏ sót lần nữa là test đỏ.
                    "can_view_salary": bool(p.can_view_salary) if p else False,
                    "can_edit_salary": bool(p.can_edit_salary) if p else False,
                    "can_adjust": bool(p.can_adjust) if p else False,
                    "can_reset_password": bool(p.can_reset_password) if p else False,
                    "can_lock": bool(p.can_lock) if p else False,
                    "can_revoke_sessions": bool(p.can_revoke_sessions) if p else False,
                    "can_assign_role": bool(p.can_assign_role) if p else False,
                    "can_transfer": bool(p.can_transfer) if p else False,
                    "can_set_head": bool(p.can_set_head) if p else False,
                    "can_requote": bool(p.can_requote) if p else False,
                    "can_manage_price": bool(p.can_manage_price) if p else False,
                    "can_cancel": bool(p.can_cancel) if p else False,
                    "can_manage_permissions": bool(p.can_manage_permissions) if p else False,
                    "can_clone": bool(p.can_clone) if p else False,
                    "can_toggle_active": bool(p.can_toggle_active) if p else False,
                    "can_reparent": bool(p.can_reparent) if p else False,
                    # A2 — quyền duyệt "đơn đặc thù" (chỉ GĐ). (view_salary/edit_salary/adjust vẫn
                    # do save_matrix xử lý riêng, giữ nguyên hành vi cũ — không mở rộng ở đây.)
                    "can_approve_exception": bool(p.can_approve_exception) if p else False,
                    "can_set_credit_terms": bool(p.can_set_credit_terms) if p else False,
                    "can_record_deposit": bool(p.can_record_deposit) if p else False,
                    "can_assign_work": bool(p.can_assign_work) if p else False,
                    "can_record_output": bool(p.can_record_output) if p else False,
                    "can_handover": bool(p.can_handover) if p else False,
                    # kho — quyền chi tiết (spec-kho-de-nghi §9.1) + ghi sổ (SoD).
                    "can_request": bool(p.can_request) if p else False,
                    "can_view_stock": bool(p.can_view_stock) if p else False,
                    "can_view_cost": bool(p.can_view_cost) if p else False,
                    "can_set_threshold": bool(p.can_set_threshold) if p else False,
                    "can_post": bool(p.can_post) if p else False,
                    "can_close_book": bool(p.can_close_book) if p else False,
                }
            )
        return rows

    def save_matrix(self, *, role_id: int, rows: list[dict], actor_id: int | None) -> list[dict]:
        role = self.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound("Không tìm thấy vai trò")
        valid_keys = {m.key for m in self.modules.list_all()}
        for row in rows:
            if row["module_key"] not in valid_keys:
                continue  # ignore unknown modules rather than create dangling rows
            normalized = dict(row)
            can_read = bool(normalized.get("can_read", False))
            if not can_read:
                for key in READ_IMPLYING_KEYS:
                    if normalized.get(key, False):
                        can_read = True
                        break
            normalized["can_read"] = can_read
            if normalized["module_key"] in SCOPELESS_MODULES:
                normalized["scope"] = "all"
            can_approve = normalized.get("can_approve", False)
            self.roles.set_permission(
                role_id=role_id,
                module_key=normalized["module_key"],
                can_read=can_read,
                can_create=normalized.get("can_create", False),
                can_update=normalized.get("can_update", False),
                can_delete=normalized.get("can_delete", False),
                scope=normalized.get("scope", "own"),
                can_reassign=normalized.get("can_reassign", False),
                can_export=normalized.get("can_export", False),
                can_view_debt=normalized.get("can_view_debt", False),
                can_view_discount=normalized.get("can_view_discount", False),
                can_approve=can_approve,
                can_manage_status=normalized.get("can_manage_status", False),
                can_reset_password=normalized.get("can_reset_password", False),
                can_lock=normalized.get("can_lock", False),
                can_revoke_sessions=normalized.get("can_revoke_sessions", False),
                can_assign_role=normalized.get("can_assign_role", False),
                can_transfer=normalized.get("can_transfer", False),
                can_set_head=normalized.get("can_set_head", False),
                can_requote=normalized.get("can_requote", False),
                can_manage_price=normalized.get("can_manage_price", False),
                can_cancel=normalized.get("can_cancel", False),
                can_manage_permissions=normalized.get("can_manage_permissions", False),
                can_clone=normalized.get("can_clone", False),
                can_toggle_active=normalized.get("can_toggle_active", False),
                can_reparent=normalized.get("can_reparent", False),
                can_view_salary=normalized.get("can_view_salary", False),
                can_edit_salary=normalized.get("can_edit_salary", False),
                can_adjust=normalized.get("can_adjust", False),
                can_view_log=normalized.get("can_view_log", False),
                can_approve_exception=normalized.get("can_approve_exception", False),
                can_set_credit_terms=normalized.get("can_set_credit_terms", False),
                can_record_deposit=normalized.get("can_record_deposit", False),
                can_assign_work=normalized.get("can_assign_work", False),
                can_record_output=normalized.get("can_record_output", False),
                can_handover=normalized.get("can_handover", False),
                can_request=normalized.get("can_request", False),
                can_view_stock=normalized.get("can_view_stock", False),
                can_view_cost=normalized.get("can_view_cost", False),
                can_set_threshold=normalized.get("can_set_threshold", False),
                can_post=normalized.get("can_post", False),
                can_close_book=normalized.get("can_close_book", False),
            )
        self.audit.create(
            actor_user_id=actor_id,
            action="update_role_permissions",
            target=f"role:{role_id}",
            detail=role.name,
        )
        return self.get_matrix(role_id)
