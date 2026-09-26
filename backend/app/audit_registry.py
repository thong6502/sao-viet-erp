"""MỘT NGUỒN cho danh mục HÀNH ĐỘNG của nhật ký (`audit_logs.action`).

Vì sao có file này: màn Nhật ký hoạt động trước đây tự khai nhãn ở frontend — 16 mã, trong khi
backend đang ghi gần 300. Mã lạ rơi vào nhánh dự phòng, hiện ra dưới dạng title-case tên cột
("Employee Create Account") giữa một giao diện tiếng Việt, và không lọc được theo nhóm nào.

Ba thứ mỗi dòng phải trả lời, vì có ba nơi hỏi:
  1. `nhan`   — màn Nhật ký hiển thị cái gì cho người đọc (thay cho mã kỹ thuật).
  2. `nhom`   — chip lọc theo phân hệ; đếm ở MÁY CHỦ chứ không đếm trên trang đang xem.
  3. `module` — khoá RBAC của MÀN sinh ra dòng đó. Dùng để che dòng khỏi người không có quyền
     xem màn ấy (`detail` của nhật ký chứa số tiền thật: giá gốc lô, tiền hoá đơn, đơn giá giờ
     máy). `None` = không gác — dòng hiện cho mọi người mở được màn Nhật ký.

⚠️ `module` phải là khoá THẬT trong `role_permissions.module_key`. Khai sai một khoá là che nhầm
một nhóm dòng khỏi đúng người cần đọc — với nhật ký thì đó là hỏng nặng hơn hở. Vì vậy quy ước là
**gác mở**: không chắc thì để `None`, và màn Nhật ký nói rõ "N dòng bị ẩn" chứ không nuốt im lặng.

Mã KHÔNG khai ở đây vẫn chạy: `tra()` trả về nhãn dự phòng, nhóm "khac", không gác. Nhưng có guard
test (`test_audit_registry.py`) quét mọi lời gọi `audit.create(...)` trong `app/` và bắt phải khai
đủ — thêm một action mới mà quên khai là `init` đỏ, cùng lối guard của `docs/DB_SCHEMA.md`.
"""
from __future__ import annotations

from dataclasses import dataclass

from .catalog_registry import DANH_MUC


@dataclass(frozen=True)
class HanhDong:
    """Một mã hành động, nhìn từ ba phía đang cần nó."""

    ma: str
    nhan: str
    nhom: str
    module: str | None = None


# Thứ tự = thứ tự chip trên màn Nhật ký. Bám khối của thanh bên để người đọc dò theo phân hệ.
NHOM: tuple[tuple[str, str], ...] = (
    ("kinh_doanh", "Kinh doanh"),
    ("san_xuat", "Sản xuất"),
    ("kho", "Kho hàng"),
    ("mua_hang", "Mua hàng"),
    ("ke_toan", "Kế toán"),
    ("nhan_su", "Nhân sự"),
    ("luong", "Lương"),
    ("danh_muc", "Danh mục"),
    ("he_thong", "Hệ thống"),
    ("khac", "Khác"),
)

NHOM_KHAC = "khac"


def _dong(nhom: str, module: str | None, cap: dict[str, str]) -> list[HanhDong]:
    return [HanhDong(ma, nhan, nhom, module) for ma, nhan in cap.items()]


_HD: list[HanhDong] = []

# --- Kinh doanh -----------------------------------------------------------------------------
_HD += _dong("kinh_doanh", "khach_hang", {
    "create_customer": "Tạo khách hàng",
    "update_customer": "Sửa khách hàng",
    "reassign_customer": "Chuyển khách sang người phụ trách khác",
    "reassign_customers": "Chuyển hàng loạt khách sang người phụ trách khác",
})
_HD += _dong("kinh_doanh", "bao_gia", {
    "create_quote": "Tạo báo giá",
    "update_quote": "Sửa báo giá",
    "extend_quote_validity": "Gia hạn hiệu lực báo giá",
    "quote_attach_add": "Đính kèm tệp vào báo giá",
    "quote_attach_delete": "Xoá tệp đính kèm báo giá",
    "quote_item_image_set": "Gắn ảnh cho dòng báo giá",
    "quote_item_image_clear": "Gỡ ảnh khỏi dòng báo giá",
    "quote_exception_approved": "Duyệt báo giá đặc thù",
    "quote_exception_rejected": "Từ chối báo giá đặc thù",
    # `transition_<trạng thái đích>` — một mã cho mỗi ô của vòng đời báo giá.
    "transition_draft": "Báo giá → Nháp",
    "transition_pending_approval": "Báo giá → Chờ duyệt",
    "transition_approved": "Báo giá → Đã duyệt",
    "transition_sent": "Báo giá → Đã gửi khách",
    "transition_accepted": "Báo giá → Khách đồng ý",
    "transition_rejected": "Báo giá → Khách từ chối",
    "transition_expired": "Báo giá → Hết hiệu lực",
    "transition_converted_to_order": "Báo giá → Đã lên đơn",
    "transition_cancelled": "Báo giá → Huỷ",
})
_HD += _dong("kinh_doanh", "don_hang_ban", {
    "create_order": "Tạo đơn hàng",
    "update_order": "Sửa đơn hàng",
    "change_order": "Sửa đơn đã chốt",
    "confirm_order": "Chốt đơn hàng",
    "cancel_order": "Huỷ đơn hàng",
    "record_deposit": "Ghi nhận tiền cọc",
    "update_production_hint": "Sửa lưu ý sản xuất của đơn",
    "push_production": "Đẩy đơn xuống sản xuất",
    "release_production": "Phát lệnh sản xuất từ đơn",
    "upload_consent": "Tải lên xác nhận của khách",
    "delete_consent": "Xoá xác nhận của khách",
})
_HD += _dong("kinh_doanh", "tinh_gia_thanh", {
    "create_ptg": "Tạo phiếu tính giá",
    "update_ptg": "Sửa phiếu tính giá",
    "delete_ptg": "Xoá phiếu tính giá",
})

# --- Sản xuất -------------------------------------------------------------------------------
_HD += _dong("san_xuat", "san_xuat", {
    "create_lsx": "Tạo lệnh sản xuất",
    "update_lsx": "Sửa lệnh sản xuất",
    "delete_lsx": "Xoá lệnh sản xuất",
    "lsx_trang_thai": "Đổi trạng thái lệnh sản xuất",
    "update_lsx_routing": "Sửa chuỗi công đoạn của lệnh",
    "update_lsx_danh_muc": "Cập nhật lệnh theo danh mục",
    "lsx_dinh_kem_them": "Đính kèm tệp vào lệnh",
    "lsx_dinh_kem_xoa": "Xoá tệp đính kèm lệnh",
})
_HD += _dong("san_xuat", "bai_ghep_2", {
    "tao_bai_ghep": "Tạo bài ghép",
    "sua_bai_ghep": "Sửa bài ghép",
    "xoa_bai_ghep": "Xoá bài ghép",
    "bai_ghep_trang_thai": "Đổi trạng thái bài ghép",
    "tach_buoc_bai_ghep": "Tách bước bài ghép",
    "gop_buoc_bai_ghep": "Gộp bước bài ghép",
    "them_thanh_vien": "Thêm thành viên vào bài ghép",
    "sua_thanh_vien": "Sửa thành viên bài ghép",
    "bo_thanh_vien": "Gỡ thành viên khỏi bài ghép",
    "ke_hoach_buoc_chung": "Đặt kế hoạch bước chung",
})
_HD += _dong("san_xuat", "xep_lich", {
    "xep_lich_dua_vao": "Đưa lệnh vào xếp lịch",
    "xep_lich_gan": "Gán lịch cho công đoạn",
    "xep_lich_go": "Gỡ lịch của công đoạn",
    "xep_lich_khoa": "Khoá lịch",
    "xep_lich_mo_khoa": "Mở khoá lịch",
    "xep_lich_khoa_may": "Khoá máy trên lịch",
    "xep_lich_mo_khoa_may": "Mở khoá máy trên lịch",
    "xep_lich_phat_hanh": "Phát hành lịch",
    "xep_lich_go_phat_hanh": "Gỡ phát hành lịch",
    "xep_lich_quan_so_go_de": "Ghi quân số gỡ đè",
    "xep_lich_quan_so_bo_go_de": "Bỏ quân số gỡ đè",
    "xep_lich_ve_san_sang": "Đưa lệnh về sẵn sàng",
    # Xung đột & nguy cơ trễ — cùng bàn Xếp lịch.
    "van_de_tiep_nhan": "Tiếp nhận vấn đề xếp lịch",
    "van_de_xu_ly": "Xử lý vấn đề xếp lịch",
    "van_de_giao": "Giao vấn đề xếp lịch cho người khác",
    "van_de_tam_hoan": "Tạm hoãn vấn đề xếp lịch",
    "van_de_ngoai_le": "Đánh dấu ngoại lệ cho vấn đề xếp lịch",
    "van_de_ghi_chu": "Ghi chú vấn đề xếp lịch",
})
# Thực hiện sản xuất tại tổ: KHÔNG gác bằng một khoá tĩnh — quyền của nó là dòng ĐỘNG theo tổ
# (`to_sx_<id>`), không có một `module_key` nào đại diện. Để `None` = hiện cho mọi người mở được
# màn Nhật ký; các dòng này cũng không mang số tiền.
_HD += _dong("san_xuat", None, {
    "san_xuat_tao_batch": "Tạo mẻ sản xuất",
    "san_xuat_me_cap_nhat_danh_muc": "Cập nhật mẻ theo danh mục",
    "san_xuat_de_nghi_vat_tu": "Đề nghị cấp vật tư",
    "san_xuat_sua_de_nghi_vat_tu": "Sửa đề nghị cấp vật tư",
    "san_xuat_xac_nhan_vat_tu": "Xác nhận nhận vật tư",
    "san_xuat_kho_yeu_cau_nhap": "Yêu cầu kho nhập hàng",
    "san_xuat_ban_giao_de_xuat": "Đề xuất bàn giao",
    "san_xuat_ban_giao_sua": "Sửa đề xuất bàn giao",
    "san_xuat_ban_giao_xac_nhan": "Xác nhận bàn giao",
    "san_xuat_ban_giao_dieu_chinh": "Điều chỉnh bàn giao",
    "san_xuat_kcs_kiem": "KCS kiểm hàng",
    "san_xuat_kcs_dieu_chinh": "KCS điều chỉnh kết quả kiểm",
    "san_xuat_kcs_da_xem_loi": "KCS đánh dấu đã xem lỗi",
    "san_xuat_dong_nhom_du": "Đóng nhóm đủ số",
    "san_xuat_dong_nhom_thieu": "Đóng nhóm thiếu số",
    "san_xuat.phat_hanh_cap_nhat": "Phát hành cập nhật xuống xưởng",
    "san_xuat.thu_hoi_goi": "Thu hồi gói phát hành",
    "san_xuat.ho_tro.huy_phat_hanh_lai": "Huỷ phát hành lại",
    # Bàn tổ — điều hành công việc tại chỗ.
    "san_xuat_phan_cong": "Phân công thợ",
    "san_xuat_go_phan_cong": "Gỡ phân công thợ",
    "san_xuat_bat_dau": "Bắt đầu công việc",
    "san_xuat_tam_dung": "Tạm dừng công việc",
    "san_xuat_ket_thuc": "Kết thúc công việc",
    "san_xuat_doi_may": "Đổi máy đang chạy",
    "san_xuat_nhan_khuon": "Nhận khuôn",
    "san_xuat_tra_khuon": "Trả khuôn",
    # Đề xuất hỗ trợ giữa các tổ.
    "san_xuat.ho_tro.de_xuat": "Đề xuất hỗ trợ",
    "san_xuat.ho_tro.xac_nhan": "Xác nhận hỗ trợ",
    "san_xuat.ho_tro.huy": "Huỷ đề xuất hỗ trợ",
})
# Kỹ thuật máy dùng đúng HAI mã `create` / `update` cho cả ba loại phiếu, phân biệt bằng `target`
# (`ky_thuat_sua_chua` · `ky_thuat_bao_tri` · `ky_thuat_yeu_cau`) — cùng lối `dm_tao`/`dm_sua`/
# `dm_xoa` của khối danh mục, nên nhãn và khoá quyền cũng tra theo target (xem `tra()`).
_HD += _dong("san_xuat", "ky_thuat_may", {
    "create": "Tạo phiếu kỹ thuật máy",
    "update": "Sửa phiếu kỹ thuật máy",
})

# --- Kho hàng -------------------------------------------------------------------------------
_HD += _dong("kho", "bao_cao_kho", {
    "kho_export": "Xuất Excel báo cáo kho",
    "kho_tinh_gia": "Tính giá kỳ kho",
    "kho_sua_gia_goc": "Sửa giá gốc lô hàng",
})
_HD += _dong("kho", "kho", {
    "kho_xuat_dieu_chinh": "Điều chỉnh phiếu xuất kho",
})
_HD += _dong("kho", "dm_kho_hang", {
    "kho_vi_tri_create": "Tạo vị trí trong kho",
    "kho_vi_tri_delete": "Xoá vị trí trong kho",
})

# --- Mua hàng -------------------------------------------------------------------------------
_HD += _dong("mua_hang", "yeu_cau_mua_hang", {
    "create_purchase_request": "Tạo yêu cầu mua hàng",
    "update_purchase_request": "Sửa yêu cầu mua hàng",
    "submit_purchase_request": "Gửi yêu cầu mua hàng",
    "cancel_purchase_request": "Huỷ yêu cầu mua hàng",
    "delete_purchase_request": "Xoá yêu cầu mua hàng",
    "close_purchase_request": "Đóng yêu cầu mua hàng",
    "approve_purchase_request": "Duyệt yêu cầu mua hàng",
    "reject_purchase_request": "Từ chối yêu cầu mua hàng",
    "mark_purchase_request_purchased": "Đánh dấu đã mua",
    "mark_purchase_request_received": "Đánh dấu đã nhận hàng",
    "undo_purchase_request_received": "Bỏ đánh dấu đã nhận hàng",
    "update_purchase_request_received_quantities": "Sửa số lượng đã nhận",
    "create_department_purchase_request": "Tạo yêu cầu mua hàng của phòng",
    "update_department_purchase_request": "Sửa yêu cầu mua hàng của phòng",
    "cancel_department_purchase_request": "Huỷ yêu cầu mua hàng của phòng",
    "cancel_department_purchase_request_line": "Huỷ một món trong yêu cầu mua hàng",
})
_HD += _dong("mua_hang", "thu_mua", {
    "add_purchase_attachment": "Đính kèm tệp vào phiếu mua hàng",
    "delete_purchase_attachment": "Xoá tệp đính kèm phiếu mua hàng",
    "create_purchase_delivery": "Tạo phiếu giao hàng của nhà cung cấp",
    "update_purchase_delivery": "Sửa phiếu giao hàng của nhà cung cấp",
    "delete_purchase_delivery": "Xoá phiếu giao hàng của nhà cung cấp",
    "update_purchase_contract": "Sửa hợp đồng mua hàng",
})
_HD += _dong("mua_hang", "nha_cung_cap", {
    "create_supplier": "Tạo nhà cung cấp",
    "update_supplier": "Sửa nhà cung cấp",
    "toggle_supplier": "Bật/tắt nhà cung cấp",
    "create_supplier_bank_account": "Thêm tài khoản ngân hàng của nhà cung cấp",
    "update_supplier_bank_account": "Sửa tài khoản ngân hàng của nhà cung cấp",
    "toggle_supplier_bank_account": "Bật/tắt tài khoản ngân hàng của nhà cung cấp",
})

# --- Kế toán --------------------------------------------------------------------------------
_HD += _dong("ke_toan", "ke_toan", {
    "assign_purchase_invoice": "Gán hoá đơn cho đơn mua hàng",
})
_HD += _dong("ke_toan", "cong_no_phai_thu", {
    "create_sales_invoice": "Tạo hoá đơn bán hàng",
    "cancel_sales_invoice": "Huỷ hoá đơn bán hàng",
    "create_sales_invoice_receipt": "Ghi thu theo hoá đơn bán hàng",
})
_HD += _dong("ke_toan", "phieu_thu", {
    "create_payment_receipt": "Tạo phiếu thu",
    "update_payment_receipt": "Sửa phiếu thu",
    "cancel_payment_receipt": "Huỷ phiếu thu",
    "mark_payment_receipt_received": "Đánh dấu đã nhận tiền",
    "create_other_payment_receipt": "Tạo phiếu thu khác",
    "upload_payment_receipt_attachment": "Đính kèm tệp vào phiếu thu",
    "delete_payment_receipt_attachment": "Xoá tệp đính kèm phiếu thu",
    "create_order_receipt": "Tạo phiếu thu theo đơn hàng",
    "cancel_order_receipt": "Huỷ phiếu thu theo đơn hàng",
})
_HD += _dong("ke_toan", "phieu_chi", {
    "create_payment_voucher": "Tạo phiếu chi",
    "cancel_payment_voucher": "Huỷ phiếu chi",
    "upload_payment_voucher_attachment": "Đính kèm tệp vào phiếu chi",
    "delete_payment_voucher_attachment": "Xoá tệp đính kèm phiếu chi",
})
_HD += _dong("ke_toan", "tk_ngan_hang", {
    "create_company_bank_account": "Thêm tài khoản ngân hàng công ty",
    "update_company_bank_account": "Sửa tài khoản ngân hàng công ty",
    "toggle_company_bank_account": "Bật/tắt tài khoản ngân hàng công ty",
})

# --- Nhân sự --------------------------------------------------------------------------------
_HD += _dong("nhan_su", "nhan_su", {
    "create_employee": "Tạo hồ sơ nhân sự",
    "update_employee": "Sửa hồ sơ nhân sự",
    "employee_add_attachment": "Đính kèm tệp vào hồ sơ nhân sự",
    "employee_delete_attachment": "Xoá tệp đính kèm hồ sơ nhân sự",
    "employee_create_account": "Tạo tài khoản đăng nhập cho nhân sự",
    "employee_link_account": "Nối hồ sơ nhân sự với tài khoản",
    "approve_profile_request": "Duyệt đề nghị sửa hồ sơ",
    "cancel_profile_request": "Huỷ đề nghị sửa hồ sơ",
    # `employee_<sự kiện>` — mốc quá trình công tác.
    "employee_hired": "Vào làm",
    "employee_probation_ended": "Hết hạn thử việc",
    "employee_confirmed": "Chuyển chính thức",
    "employee_transferred": "Điều chuyển phòng/tổ",
    "employee_promoted": "Đổi chức danh",
    "employee_leave_start": "Bắt đầu nghỉ dài hạn",
    "employee_leave_end": "Kết thúc nghỉ dài hạn",
    "employee_suspended": "Đình chỉ",
    "employee_unsuspended": "Gỡ đình chỉ",
    "employee_resigned": "Nghỉ việc",
    "employee_reinstated": "Tuyển lại",
})
_HD += _dong("nhan_su", "self_service", {
    "update_my_contact": "Tự cập nhật thông tin liên hệ",
})
_HD += _dong("nhan_su", "cham_cong", {
    "assign_default_shift": "Gán ca nền cho nhân sự",
    "assign_default_shift_bulk": "Gán ca nền hàng loạt",
    "delete_shift_assignment": "Gỡ ca đã gán",
    "set_shift_plan": "Đặt kế hoạch ca",
    "adjust_attendance": "Chỉnh công",
    "delete_manual_attendance": "Xoá chấm công nhập tay",
    "lock_attendance_period": "Khoá kỳ công",
    "reopen_attendance_period": "Mở lại kỳ công",
})
_HD += _dong("nhan_su", "yeu_cau_chinh_cong", {
    "cancel_attendance_adjust_request": "Huỷ yêu cầu chỉnh công",
    "reject_attendance_adjust_request": "Từ chối yêu cầu chỉnh công",
})
_HD += _dong("nhan_su", "nghi_phep", {
    "create_leave_request": "Tạo đơn nghỉ phép",
    "leave_approved": "Duyệt đơn nghỉ phép",
    "leave_rejected": "Từ chối đơn nghỉ phép",
    "leave_cancelled": "Huỷ đơn nghỉ phép",
    "leave_cancel_requested": "Xin huỷ đơn nghỉ phép",
    "leave_cancel_request_approved": "Duyệt xin huỷ đơn nghỉ phép",
    "leave_cancel_request_rejected": "Từ chối xin huỷ đơn nghỉ phép",
    "leave_cancel_request_withdrawn": "Rút xin huỷ đơn nghỉ phép",
})
_HD += _dong("nhan_su", "tang_ca", {
    "create_overtime_request": "Tạo đơn tăng ca",
    "create_overtime_request_approved": "Tạo đơn tăng ca (duyệt luôn)",
    "overtime_approved": "Duyệt đơn tăng ca",
    "overtime_rejected": "Từ chối đơn tăng ca",
    "overtime_cancelled": "Huỷ đơn tăng ca",
    "overtime_updated": "Sửa đơn tăng ca",
    "overtime_cancel_requested": "Xin huỷ đơn tăng ca",
    "overtime_cancel_request_approved": "Duyệt xin huỷ đơn tăng ca",
    "overtime_cancel_request_rejected": "Từ chối xin huỷ đơn tăng ca",
    "overtime_cancel_request_withdrawn": "Rút xin huỷ đơn tăng ca",
    "xac_nhan_tang_ca_theo_phieu": "Xác nhận tăng ca theo phiếu",
})
_HD += _dong("nhan_su", "di_muon", {
    "create_late_early_request": "Tạo phiếu đi muộn / về sớm",
    "create_late_early_request_approved": "Tạo phiếu đi muộn / về sớm (duyệt luôn)",
    "late_early_approved": "Duyệt phiếu đi muộn / về sớm",
    "late_early_rejected": "Từ chối phiếu đi muộn / về sớm",
    "late_early_cancelled": "Huỷ phiếu đi muộn / về sớm",
    "late_early_updated": "Sửa phiếu đi muộn / về sớm",
})
_HD += _dong("nhan_su", "noi_quy", {
    "create_noi_quy_record": "Ghi nhận nội quy lao động",
    "delete_noi_quy_record": "Xoá ghi nhận nội quy lao động",
})

# --- Lương ----------------------------------------------------------------------------------
_HD += _dong("luong", "luong", {
    "payroll_generate": "Tính bảng lương",
    "payroll_lock": "Chốt kỳ lương",
    "payroll_reopen": "Mở lại kỳ lương",
    "payroll_cong_bo": "Công bố phiếu lương",
    "payroll_thu_hoi": "Thu hồi phiếu lương đã công bố",
    "payroll_paid": "Đánh dấu đã trả lương",
    "payroll_unpaid": "Bỏ đánh dấu đã trả lương",
    "payroll_update_line": "Sửa dòng lương",
    "payroll_set_salary": "Đặt mốc lương của nhân sự",
    "payroll_delete_salary": "Xoá mốc lương của nhân sự",
    "payroll_create_advance": "Tạo đề nghị tạm ứng",
    "payroll_decide_advance": "Duyệt / từ chối tạm ứng",
    "payroll_cancel_advance": "Huỷ đề nghị tạm ứng",
    "payroll_update_params": "Cập nhật tham số lương",
    "payroll_pit_bracket_changed": "Sửa bậc thuế thu nhập cá nhân",
    "payroll_late_bracket_changed": "Sửa bậc phạt đi muộn",
    "payroll_chi_tieu_ngay_changed": "Sửa chỉ tiêu ngày công",
    "payroll_to_truong_changed": "Sửa cấu hình tổ trưởng",
    "payroll_component_taxable_changed": "Đổi tính chất chịu thuế của khoản lương",
    "payroll_set_dept_components": "Đặt khoản lương cho phòng ban",
    "create_payroll_component": "Tạo khoản lương",
    "delete_payroll_component": "Xoá khoản lương",
    "deactivate_payroll_component": "Ngừng dùng khoản lương",
    "add_line_component": "Thêm khoản vào dòng lương",
    "update_line_component": "Sửa khoản của dòng lương",
    "delete_line_component": "Xoá khoản của dòng lương",
    "bo_de_line_component": "Bỏ đè khoản của dòng lương",
    "bulk_assign_component": "Gán khoản lương hàng loạt",
    "unassign_all_component": "Gỡ khoản lương khỏi toàn bộ nhân viên",
    "set_employee_components": "Đặt khoản lương của nhân sự",
})

# --- Danh mục -------------------------------------------------------------------------------
# Ba mã dùng CHUNG cho 12 màn danh mục — loại nằm ở `target` (`"{loai}:{id}"`), nên nhãn và
# khoá quyền tra theo target chứ không theo mã (xem `tra()` / `module_cua()`).
_HD += _dong("danh_muc", None, {
    "dm_tao": "Thêm dòng danh mục",
    "dm_sua": "Sửa dòng danh mục",
    "dm_xoa": "Xoá dòng danh mục",
})
_HD += _dong("danh_muc", "dm_thiet_bi", {
    "create_machine": "Tạo máy / thiết bị",
    "update_machine": "Sửa máy / thiết bị",
    "delete_machine": "Xoá máy / thiết bị",
    "add_machine_rate": "Thêm đơn giá giờ máy",
})
_HD += _dong("danh_muc", "dm_cong_doan", {
    "create_operation": "Tạo công đoạn",
    "update_operation": "Sửa công đoạn",
    "delete_operation": "Xoá công đoạn",
    "add_operation_rate": "Thêm bảng giá công đoạn",
    "update_cong_doan_tag": "Sửa nhãn công đoạn",
})
_HD += _dong("danh_muc", "dm_don_vi", {
    "create_don_vi": "Tạo đơn vị đo",
    "update_don_vi": "Sửa đơn vị đo",
    "delete_don_vi": "Xoá đơn vị đo",
    "create_don_vi_cap": "Tạo cầu quy đổi đơn vị",
    "update_don_vi_cap": "Sửa cầu quy đổi đơn vị",
    "delete_don_vi_cap": "Xoá cầu quy đổi đơn vị",
})
_HD += _dong("danh_muc", "dm_loai_san_pham", {
    "create_product_type_catalog": "Tạo loại sản phẩm",
    "update_product_type_catalog": "Sửa loại sản phẩm",
    "delete_product_type_catalog": "Xoá loại sản phẩm",
})
_HD += _dong("danh_muc", "cham_cong", {
    "create_work_shift": "Tạo ca làm việc",
    "update_work_shift": "Sửa ca làm việc",
    "delete_work_shift": "Xoá ca làm việc",
    "create_work_location": "Tạo nơi làm việc",
    "update_work_location": "Sửa nơi làm việc",
    "delete_work_location": "Xoá nơi làm việc",
    "create_special_day": "Tạo ngày đặc biệt",
    "update_special_day": "Sửa ngày đặc biệt",
    "delete_special_day": "Xoá ngày đặc biệt",
    "update_calendar_config": "Sửa cấu hình lịch làm việc",
})
_HD += _dong("danh_muc", "nghi_phep", {
    "create_leave_type": "Tạo loại nghỉ phép",
    "update_leave_type": "Sửa loại nghỉ phép",
    "delete_leave_type": "Xoá loại nghỉ phép",
})
# Định mức bù hao: `norm_service` hiện KHÔNG có router nào gọi tới (engine tính giá đọc thẳng
# repo). Không có màn ⇒ không có khoá quyền để gác.
_HD += _dong("danh_muc", None, {
    "create_norm": "Tạo định mức",
    "close_norm": "Đóng định mức",
    "delete_norm": "Xoá định mức tương lai",
})

# --- Hệ thống -------------------------------------------------------------------------------
_HD += _dong("he_thong", "phong_ban", {
    "create_department": "Tạo phòng ban",
    "update_department": "Sửa phòng ban",
    "delete_department": "Xoá phòng ban",
    "create_role": "Tạo vai trò",
    "rename_role": "Đổi tên vai trò",
    "delete_role": "Xoá vai trò",
    "duplicate_role": "Nhân bản vai trò",
    "update_role_permissions": "Sửa ma trận quyền của vai trò",
    "create_unit_level": "Tạo cấp đơn vị",
    "update_unit_level": "Sửa cấp đơn vị",
    "delete_unit_level": "Xoá cấp đơn vị",
    "create_nhom_dung_chung": "Tạo nhóm dùng chung",
    "update_nhom_dung_chung": "Sửa nhóm dùng chung",
    "delete_nhom_dung_chung": "Xoá nhóm dùng chung",
})
# Bốn thao tác quản trị tài khoản nay là ô CHI TIẾT của `nhan_su` (mg `0331`).
_HD += _dong("he_thong", "nhan_su", {
    "create_user": "Tạo tài khoản đăng nhập",
    "update_user": "Sửa tài khoản đăng nhập",
    "assign_role": "Gán vai trò cho tài khoản",
    "transfer_user": "Chuyển tài khoản sang phòng ban khác",
    "lock_user": "Khoá tài khoản",
    "unlock_user": "Mở khoá tài khoản",
    "reset_password": "Đặt lại mật khẩu",
    "revoke_sessions": "Thu hồi phiên đăng nhập",
})
# Sự kiện truy cập + việc xuất chính nhật ký này: không gác bằng khoá màn nào — chúng là vết của
# hệ thống, ai đọc được nhật ký thì đọc được.
_HD += _dong("he_thong", None, {
    "dang_nhap": "Đăng nhập",
    "dang_nhap_that_bai": "Đăng nhập thất bại",
    "dang_xuat": "Đăng xuất",
    "audit_export": "Xuất nhật ký hoạt động",
})

# --- Mã ĐỜI CŨ: không còn trong code, nhưng dữ liệu vẫn còn ----------------------------------
# Nhật ký là bảng KHÔNG ai xoá, nên mã của những module đã gỡ vẫn nằm đó và vẫn hiện ra màn. Không
# khai thì đúng những dòng lịch sử ấy lại mang nhãn tự chế — bệnh mà file này sinh ra để chữa.
# Guard test không quét được chúng (code đã xoá), nên đây là nơi duy nhất giữ tên cho chúng.
_HD += _dong("san_xuat", None, {
    # Lớp thực thi SX đời trước, gỡ khi gộp `merge-main-vao-rebuild-sanxuat`.
    "san_xuat_kcs_diem_kiem": "KCS điểm kiểm (bản cũ)",
    "san_xuat_kcs_dot_xuat": "KCS kiểm đột xuất (bản cũ)",
    "san_xuat_kcs_tao_batch": "KCS tạo mẻ kiểm (bản cũ)",
    "san_xuat_kcs_ghi_loi": "KCS ghi lỗi (bản cũ)",
    "san_xuat.phan_bo.tinh": "Tính phân bổ (bản cũ)",
    "san_xuat.phan_bo.chot": "Chốt phân bổ (bản cũ)",
    "san_xuat.phan_bo.mo_lai": "Mở lại phân bổ (bản cũ)",
    "san_xuat.phan_bo.loai_tru": "Loại trừ khỏi phân bổ (bản cũ)",
    # Xếp lịch 2 và Xếp lịch 3 — cả hai khoá module đã gỡ (mg `0314`).
    "xep_lich_2_tu_xep": "Tự xếp lịch (bản cũ)",
    "xep_lich_2_luu": "Lưu lịch (bản cũ)",
    "xep_lich_2_tach_dong": "Tách dòng lịch (bản cũ)",
    "xep_lich_2_gop_dong": "Gộp dòng lịch (bản cũ)",
    "xep_lich_3_phat_hanh": "Phát hành lịch (bản cũ)",
    "xep_lich_3_ve_san_sang": "Đưa lệnh về sẵn sàng (bản cũ)",
})
_HD += _dong("nhan_su", None, {
    # Bậc tay nghề gỡ hẳn 17/09/2026 (mg `0305`, `0307`).
    "job_grade_updated": "Sửa bậc tay nghề (đã gỡ)",
})

HANH_DONG: tuple[HanhDong, ...] = tuple(_HD)

THEO_MA: dict[str, HanhDong] = {h.ma: h for h in HANH_DONG}

# `loai` (tiền tố của `target`) → dòng danh mục, gồm cả tên loại ĐỜI CŨ còn nằm trong `audit_logs`.
_LOAI: dict[str, object] = {}
for _d in DANH_MUC:
    _LOAI[_d.loai] = _d
    for _alias in _d.alias_loai:
        _LOAI[_alias] = _d

_DM = {"dm_tao": "Thêm", "dm_sua": "Sửa", "dm_xoa": "Xoá"}

# Kỹ thuật máy: hai mã chung `create`/`update`, loại phiếu nằm ở `target`.
_KTM = {"create": "Tạo", "update": "Sửa"}
_KTM_LOAI: dict[str, tuple[str, str]] = {
    "ky_thuat_sua_chua": ("phiếu sửa chữa", "ky_thuat_may"),
    "ky_thuat_yeu_cau": ("yêu cầu báo hỏng", "ky_thuat_may"),
    # Phiếu bảo trì tách thành khoá riêng 17/08/2026 — điều độ xem lịch bảo trì mà không nên đọc
    # phiếu máy hỏng, nên hai loại này KHÁC khoá quyền dù cùng một mã action.
    "ky_thuat_bao_tri": ("phiếu bảo trì", "phieu_bao_tri"),
}


def _loai_cua(target: str) -> object | None:
    return _LOAI.get(target.split(":", 1)[0]) if target else None


def tra(ma: str, target: str = "") -> HanhDong:
    """Dòng danh mục của một mã. Mã lạ → nhãn dự phòng, nhóm "khac", không gác.

    `target` chỉ cần cho ba mã danh mục dùng chung (`dm_tao`/`dm_sua`/`dm_xoa`): nhãn và khoá quyền
    của chúng phụ thuộc màn nào sinh ra dòng, mà điều đó nằm ở `target`.
    """
    hd = THEO_MA.get(ma)
    if hd is None:
        return HanhDong(ma, ma.replace("_", " ").strip().capitalize(), NHOM_KHAC, None)
    if ma in _DM:
        d = _loai_cua(target)
        if d is not None:
            return HanhDong(ma, f"{_DM[ma]} · {d.nhan}", hd.nhom, d.module)
    if ma in _KTM:
        loai = target.split(":", 1)[0] if target else ""
        if loai in _KTM_LOAI:
            nhan, module = _KTM_LOAI[loai]
            return HanhDong(ma, f"{_KTM[ma]} {nhan}", hd.nhom, module)
    return hd


def module_cua(ma: str, target: str = "") -> str | None:
    """Khoá quyền của MÀN sinh ra dòng, hoặc `None` khi không gác."""
    return tra(ma, target).module


def nhan_nhom(khoa: str) -> str:
    for k, nhan in NHOM:
        if k == khoa:
            return nhan
    return khoa
