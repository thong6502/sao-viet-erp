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
    # khach_hang: xem/sửa CHIẾT KHẤU riêng theo khách (CK thương mại + CK người mua hàng
    # — nhạy cảm, thực chất là hoa hồng phía khách). Thiếu quyền → API ẩn số và bỏ qua
    # thay đổi 2 trường này khi Sửa (pattern view_debt/view_salary).
    can_view_discount: Mapped[bool] = mapped_column(
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
    # nhan_su: xem DỮ LIỆU NHẠY CẢM của hồ sơ (lương/BHXH/MST/số phụ thuộc/tài khoản NH/
    # nhóm-bậc lương) — tách khỏi "xem hồ sơ" cơ bản. Thiếu quyền này thì các field đó bị ẩn.
    can_view_salary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # nhan_su: SỬA dữ liệu nhạy cảm hồ sơ (lương/BHXH/bank/nhóm-bậc lương) — TÁCH khỏi
    # `view_salary` (chỉ xem). Thiếu quyền này thì các field nhạy cảm bị BỎ QUA khi ghi (N5).
    can_edit_salary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # nhan_su (Chấm công): điều chỉnh CÔNG bằng cách thêm/xóa PUNCH NGUỒN (chấm bù, sửa)
    # — tách khỏi "sửa hồ sơ" (update). Người khai ca chưa chắc được sửa công NV.
    can_adjust: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # don_hang_ban (A2): DUYỆT "đơn đặc thù" (giá trị cao / biên thấp / dưới giá vốn) — CHỈ Giám đốc.
    # TÁCH khỏi `can_approve` (= chốt đơn thường, Trưởng phòng KD cũng có): đơn đặc thù chỉ GĐ ký,
    # Sales/TP KD không tự miễn cho mình. Mặc định tắt.
    can_approve_exception: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # khach_hang: THIẾT LẬP CHÍNH SÁCH TÀI CHÍNH khách (redesign spec-06 v2 — mở rộng từ
    # "điều khoản tín dụng"): hạn mức công nợ + điều khoản thanh toán + chiết khấu min/max +
    # biên lợi nhuận min/max. Mọi số tài chính AI CŨNG XEM; chỉ quyền này mới SỬA. Quyết định
    # "cho nợ/chiết khấu bao nhiêu" bàn NGOÀI ĐỜI — quyền chỉ gate AI được NHẬP, KHÔNG phải
    # bước duyệt. Thiếu quyền → các field tài chính bị BỎ QUA khi ghi (giữ nguyên / default
    # an toàn). Mặc định tắt.
    can_set_credit_terms: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # don_hang_ban: GHI PHIẾU THU CỌC (Kế toán) — tách khỏi CRUD đơn. NV KD lập đơn nhưng
    # KHÔNG tự ghi cọc (tiền vào két là việc Kế toán). Mặc định tắt.
    can_record_deposit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # san_xuat: GÁN VIỆC — tổ trưởng gán thợ vào công đoạn (routing_step) của lệnh đã phát. Tách
    # khỏi read: người được gán mới HỨNG việc + chỉ vai có bit này (full-tổ) mới thấy nút gán.
    can_assign_work: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # san_xuat: GHI SẢN LƯỢNG — tổ trưởng ghi đạt/hỏng cho bước của tổ (Lát 2, record-only).
    can_record_output: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # san_xuat: BÀN GIAO — tổ trưởng giao số sang tổ kế + xác nhận nhận (Lát 2, 2 con dấu).
    can_handover: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
