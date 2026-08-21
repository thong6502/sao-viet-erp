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
    # cham_cong: XEM TAB "Nhật ký chấm công" — tách khỏi `can_read` (chỉ mở Bảng công tháng)
    # ngày 11/08/2026. Bảng công tháng là số công đã tổng hợp; nhật ký là TỪNG LƯỢT BẤM của từng
    # người kèm giờ và toạ độ — ai đi sớm về muộn hôm nào, cả xưởng, đọc là biết. Hai mức nhạy cảm
    # khác nhau nên hai ô khác nhau. Thêm qua migration 0181.
    can_view_log: Mapped[bool] = mapped_column(
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
    # --- kho (spec-kho-de-nghi §9.1) — 4 quyền chi tiết của module Kho ------------------
    # TẠO ĐỀ NGHỊ nhập/xuất. TÁCH khỏi `can_create` (= lập PHIẾU): người đề nghị không lập
    # phiếu, còn thủ kho lập phiếu nhưng không tự đề nghị cho mình.
    can_request: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # XEM SỐ TỒN. Thiếu quyền → chỉ thấy ĐÈN TÍN HIỆU 5 màu, không thấy con số. Đây là cách
    # người đề nghị biết "sắp hết" mà vẫn không lộ số liệu tồn (spec §7/§8).
    can_view_stock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # XEM GIÁ VỐN & giá trị tồn. BRD §1.5: tồn ai cũng xem được, giá vốn chỉ Kế toán + BGĐ.
    # Thiếu quyền → API ẩn đơn giá/thành tiền, và bản in cũng bỏ 2 cột đó.
    can_view_cost: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # KHAI NGƯỠNG tồn / cận tồn / tối đa. Tách khỏi `can_update` vì đổi ngưỡng là đổi toàn
    # bộ hệ cảnh báo mua hàng, không phải sửa dữ liệu thường.
    can_set_threshold: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # GHI SỔ phiếu (chốt tồn). TÁCH khỏi `can_create` (= LẬP phiếu nháp) để giữ SoD: thủ kho
    # lập nháp, KẾ TOÁN KHO ghi sổ (BRD §3.19 — người ghi sổ khác người cầm hàng).
    can_post: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # KHÓA KỲ (chốt sổ) kế toán kho: xem Báo cáo kho + export MISA + chốt/mở kỳ. Chỉ kế toán kho.
    can_close_book: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # ── MÀN CHẤM CÔNG: MỘT Ô = MỘT TAB (chủ chốt 15/08/2026, mg 0194) ───────────────────────
    # Luật: cột Xem = mở màn + ba tab CỦA TÔI (bấm giờ · lịch công của mình · tự xin đi muộn);
    # mỗi ô dưới đây mở đúng MỘT tab, và tab đó luôn là thứ dính tới NGƯỜI KHÁC hoặc DÙNG CHUNG.
    # Trước đó `can_update` một mình mở ba tab cấu hình — bật một ô ra ba màn, người cấp quyền
    # không có cách nào biết mình vừa mở cái gì.

    # Lưới người × ngày, chứa nút Chốt kỳ công. Công cụ quản lý, cùng hạng với Bảng lương — thợ
    # mở màn Chấm công để bấm giờ nhưng KHÔNG được thấy công của cả xưởng.
    can_view_timesheet: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Duyệt phiếu đi muộn / về sớm / nghỉ nửa buổi của NGƯỜI KHÁC (và khai hộ = duyệt luôn).
    # Gộp từ khoá `di_muon` — nó vốn là một tab của màn này chứ không phải một màn riêng.
    can_approve_late_early: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Ba ô tách ra từ "Cấu hình chấm công", gọi đúng tên tab:
    can_manage_locations: Mapped[bool] = mapped_column(     # tab Điểm chấm công
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_manage_shifts: Mapped[bool] = mapped_column(        # tab Khai ca
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_manage_calendar: Mapped[bool] = mapped_column(      # tab Lịch & Ngày lễ
        Boolean, nullable=False, default=False, server_default="false"
    )

    # luong (mg 0195) — cùng khuôn "một ô = một tab": BẢNG LƯƠNG THÁNG là công cụ quản lý (danh
    # sách cả công ty + nút Tính lại / Chốt kỳ), KHÔNG phải "phần của tôi". Trước đó nó đi theo
    # cột Xem, nên cấp ô Lương ở phạm vi "Của tôi" là thợ vẫn mở được bảng lương.
    can_view_payroll_table: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Hai tab còn lại của màn Lương, tách khỏi cột Thao tác (mg 0196). Cột Thao tác KHÔNG được mở
    # tab nào — nó chỉ cho GHI vào tab mình đã mở được (chủ chốt 15/08/2026).
    can_manage_salary_profiles: Mapped[bool] = mapped_column(   # tab Lương nhân viên (hồ sơ lương)
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_manage_piece_rates: Mapped[bool] = mapped_column(       # tab Lương khoán (đơn giá khoán)
        Boolean, nullable=False, default=False, server_default="false"
    )
    # nghi_phep (mg 0197): DANH MỤC LOẠI NGHỈ — chính sách dùng chung cả công ty (phép năm, nghỉ
    # ốm, không lương…). Trước đó nó mượn chính cột `can_update`, mà `can_update` cũng là một
    # trong ba cột nút "Thao tác" bật ⇒ bật Thao tác là ô danh mục tự sáng theo. Hai việc khác
    # hẳn nhau: gửi/huỷ đơn của mình vs sửa chính sách nghỉ của cả nhà máy.
    can_manage_leave_types: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
