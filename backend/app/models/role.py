"""Role + RolePermission ORM models.

A Role is a named permission bundle that belongs to exactly ONE department
(vai trò riêng cho từng phòng); a user holds exactly one role. Each Role carries
one RolePermission row per module: the CRUD flags (được làm gì) plus the data
`scope` (được thấy dữ liệu của ai).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Allowed data-scope values for a RolePermission.scope.
SCOPE_OWN = "own"
SCOPE_DEPARTMENT = "department"
SCOPE_ALL = "all"
SCOPES = (SCOPE_OWN, SCOPE_DEPARTMENT, SCOPE_ALL)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("name", "department_id", name="uq_roles_name_department"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    department_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("departments.id"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "module_key", name="uq_role_permissions_role_module"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roles.id"), index=True, nullable=False
    )
    module_key: Mapped[str] = mapped_column(
        String(64), ForeignKey("modules.key"), nullable=False
    )
    can_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_create: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_update: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_delete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default=SCOPE_OWN)
    # Quyền CHI TIẾT (spec phân quyền — Cách B): các hành động đặc thù ngoài CRUD. Chỉ có ý
    # nghĩa với module khai báo dùng chúng (vd Khách hàng). Mặc định tắt.
    can_reassign: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_export: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_view_debt: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Duyệt báo giá (bao_gia): tách khỏi "sửa" — chuyển trạng thái sang "Khách duyệt".
    can_approve: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Chốt / hủy đơn (don_hang_ban): đổi trạng thái vòng đời đơn, tách khỏi "sửa".
    can_manage_status: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Đặt lại mật khẩu người dùng (nguoi_dung): tách khỏi "sửa" hồ sơ.
    can_reset_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Nhóm 1 — quyền chi tiết đặc thù khác, tách khỏi CRUD thô:
    # nguoi_dung: khóa/mở, thu hồi phiên, gán vai trò, chuyển phòng ban.
    can_lock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_revoke_sessions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_assign_role: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_transfer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # phong_ban: đặt trưởng phòng (tách khỏi sửa phòng ban).
    can_set_head: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # bao_gia: tạo bản báo giá mới (re-quote) — tách khỏi "thêm".
    can_requote: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # bao_gia: hủy báo giá (chuyển trạng thái → Đã hủy) — tách khỏi "sửa". Báo giá không
    # xóa cứng nên đây là thao tác "kết thúc" một báo giá.
    can_cancel: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Nhóm B — tách các thao tác nhạy cảm khỏi CRUD thô:
    # vai_tro: sửa MA TRẬN phân quyền (cấp quyền cho người khác) — tách khỏi đổi tên vai trò.
    can_manage_permissions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # dm_giay_vat_tu: nhân bản (clone) giấy — tách khỏi "thêm".
    can_clone: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # dm_giay_vat_tu: bật/tắt hoạt động vật liệu — tách khỏi "sửa".
    can_toggle_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # phong_ban: đổi cấp trên (re-parent, tái cấu trúc cây tổ chức) — tách khỏi "sửa".
    can_reparent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # dm_giay_vat_tu / dm_thiet_bi / dm_cong_doan: cập nhật bảng giá theo mốc thời gian.
    can_manage_price: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
