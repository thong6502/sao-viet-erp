"""Nhật ký thao tác cho các màn Cấu hình danh mục — MỘT chỗ dựng dòng "ai đổi gì".

Vì sao gom về đây: 10 màn danh mục đều là CRUD trên một bảng phẳng, nếu mỗi service tự viết
"so sánh trước/sau rồi ghi audit" thì thành 10 bản chép tay lệch nhau — chỗ ghi giá cũ, chỗ
quên, chỗ đặt tên action khác. Ở đây làm một lần, service chỉ gọi `ghi_tao` / `ghi_sua` / `ghi_xoa`.

Ghi vào bảng `audit_logs` sẵn có (target = `"{loai}:{id}"`, đúng quy ước của khách hàng · nhân sự ·
lệnh SX). Nhờ vậy các dòng này cũng chảy vào màn Nhật ký chung.

Dòng chi tiết trông như: `Đơn giá 27.800 → 29.000 đ/kg · Định lượng 100 → 120 g/m²`.

Riêng các trường CÔNG THỨC (`CONG_THUC_TRUONG`) còn được ghi THÊM, có cấu trúc, vào bảng
`cong_thuc_lich_su` (xem `models/cong_thuc_lich_su.py`) — phục vụ mục "Bảng định mức": màn danh
mục hiện được "lần trước công thức là gì, sửa lúc nào" và link xem lịch sử đầy đủ, thay vì phải
đọc lại chuỗi `detail` gộp chung của Nhật ký.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect

from ..models.may_thiet_bi import ma_don_vi_goc
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.cong_doan_repo import CongDoanRepository
from ..repositories.cong_thuc_lich_su_repo import CongThucLichSuRepository
from ..repositories.cong_viec_khoan_repo import CongViecKhoanRepository
from ..repositories.don_vi_do_repo import DonViDoRepository, nhan_don_vi

# --- Hành động: một tên cho mỗi loại thao tác, frontend dịch sang nhãn + icon --------------
ACTION_TAO = "dm_tao"
ACTION_SUA = "dm_sua"
ACTION_XOA = "dm_xoa"

# Trường công thức — đổi thì ghi thêm 1 dòng có cấu trúc vào `cong_thuc_lich_su` (xem docstring
# đầu file). `cong_thuc_san_luong` (Công đoạn) GỠ 18/09/2026 cùng cột ấy (mg `0324`).
CONG_THUC_TRUONG = frozenset({"cong_thuc_luong"})

# Cột kỹ thuật — đổi cũng không ai quan tâm, ghi vào chỉ làm nhiễu nhật ký.
# `version` là bộ đếm khoá lạc quan (chống hai người sửa đè nhau), tự tăng MỖI lần lưu: để nó lọt
# vào ảnh chụp thì lần sửa nào cũng đẻ thêm dòng "Phiên bản 3 → 4" bên cạnh thay đổi thật.
BO_QUA = frozenset({
    "id", "created_at", "updated_at", "created_by", "updated_by", "deleted_at", "version",
})

# Tên trường → nhãn tiếng Việt. Gom CHUNG cho mọi danh mục vì tên cột lặp lại nhiều
# (`ma`, `ten`, `don_gia`…). Trường lạ không có ở đây thì hiện luôn tên cột — thà xấu một dòng
# còn hơn im lặng nuốt mất một thay đổi.
NHAN: dict[str, str] = {
    "ma": "Mã",
    "code": "Mã",
    "ten": "Tên",
    "name": "Tên",
    "ten_ngan": "Tên ngắn",
    "mo_ta": "Mô tả",
    "ghi_chu": "Ghi chú",
    "tai_trong": "Tải trọng (tấn)",        # danh mục Xe giao hàng
    "muc_khoan_km_id": "Mức khoán km",     # danh mục Xe giao hàng
    # Ảnh minh hoạ mặt hàng (mg `0191`) — nhật ký in NHÃN chứ không in tên cột.
    "anh_url": "Ảnh minh hoạ",
    "note": "Ghi chú",
    "active": "Đang hoạt động",
    "is_active": "Đang hoạt động",
    "status": "Trạng thái",
    "thu_tu": "Thứ tự",
    "nhom": "Nhóm",
    "machine_group": "Nhóm máy",
    "machine_type": "Loại máy",
    "process_type": "Công đoạn máy",
    "fields_theo_loai": "Thông số theo loại máy",
    # Giấy · vật tư
    "chung_loai_id": "Chủng loại giấy",
    "chung_loai_ma": "Chủng loại giấy",
    "dinh_luong": "Định lượng",
    "kho_rong": "Khổ rộng",
    "kho_dai": "Khổ dài",
    "max_width_cm": "Khổ rộng tối đa",
    "max_height_cm": "Khổ dài tối đa",
    "min_width_cm": "Khổ rộng tối thiểu",
    "min_height_cm": "Khổ dài tối thiểu",
    "tho": "Thớ",
    "don_gia": "Đơn giá",
    "don_vi_gia": "ĐVT",
    "don_vi_dong_goi": "Đơn vị đóng gói",
    "quy_cach": "Quy cách",
    "so_luong_dong_goi": "SL đóng gói",
    # Cột chung `giay_nguyen`/`vat_tu_in_an` (mg 0239) — màn Giấy hiện "Giấy thay thế", màn Vật tư
    # hiện "Vật tư thay thế" (`rebuildCatalogConfigs.tsx`); NHAN dùng chung một dict cho mọi danh
    # mục nên gộp về một nhãn trung tính đọc được ở cả hai màn.
    "thay_the_ids": "Hàng thay thế",
    # Máy · công đoạn · bù hao
    "loai": "Loại",
    # `may_thiet_bi.loai_may` GIỮ giá trị mà màn gọi là "Nhóm máy" (ô chọn `NhomMayField`, danh mục
    # `/api/nhom-may`). Nhãn cũ "Loại máy" là tên CỘT, không phải tên người dùng thấy — đọc nhật ký
    # xong đi tìm ô "Loại máy" trên màn thì không có ô nào tên thế.
    "loai_may": "Nhóm máy",
    "so_mau": "Số màu",
    "kho_toi_da": "Khổ tối đa",
    "kho_toi_thieu": "Khổ tối thiểu",
    "toc_do": "Tốc độ",
    "speed": "Tốc độ",
    "speed_unit": "ĐVT tốc độ",
    "setup_time_mins": "Thời gian chuẩn bị (phút)",
    "changeover_time_mins": "Thời gian chuyển đổi (phút)",
    "setup_waste_sheets": "Tờ bù hao chuẩn bị",
    "supported_materials": "Vật liệu hỗ trợ",
    "num_ink_units": "Số đơn vị in",
    "supports_perfecting": "In 2 mặt cùng lúc",
    "max_print_width_cm": "Vùng in rộng tối đa",
    "max_print_height_cm": "Vùng in dài tối đa",
    "gripper_cm": "Lề nhíp (cm)",
    "side_margin_cm": "Lề bên (cm)",
    "top_bottom_margin_cm": "Lề trên/dưới (cm)",
    "makeready_phut": "Makeready (phút)",
    "phong_ban_id": "Tổ phụ trách",
    "cong_thuc": "Công thức",
    "don_vi": "Đơn vị",
    "he_so": "Hệ số",
    "ty_le": "Tỷ lệ",
    "so_to": "Số tờ",
    # Khuôn bế · kho
    "so_ke": "Số kệ",
    "vi_tri": "Vị trí",
    "tinh_trang": "Tình trạng",
    "ngay_lam": "Ngày làm",
    "khach_hang_id": "Khách hàng",
    # ── Bổ sung 15/08/2026: 59 cột danh mục trước đó KHÔNG có nhãn nên nhật ký in ra TÊN CỘT
    # (`he_so_ngoai_dong 1 → 8`). Chữ lấy đúng nhãn đang hiện trên màn (`rebuildCatalogConfigs`),
    # không tự đặt tên mới — đọc nhật ký xong phải tìm ra đúng cái ô đó trên form.
    # Đơn vị đo đi vào `HAU_TO` bên dưới, KHÔNG nhét vào nhãn: "Nhíp kẽm 10 → 12 mm" đọc gọn hơn
    # "Nhíp kẽm (mm) 10 → 12".
    # Loại sản phẩm
    "structural_type": "Dạng kết cấu",
    "box_sub_type": "Kiểu hộp",
    "imposition_rule_id": "Quy tắc bình bài",
    "has_cover": "Có bìa",
    "cover_type": "Loại bìa",
    "default_binding": "Kiểu đóng mặc định",
    "default_stock_class": "Nhóm giấy mặc định",
    "routing_template": "Chuỗi công đoạn mặc định",
    # Công đoạn
    "ten_hien_thi": "Tên hiển thị",
    "kieu_bu_hao": "Bù hao",
    "bu_hao_id": "Mã bù hao",
    "so_to_bu_hao": "Số lượng cộng cố định",
    "don_vi_vao": "Đơn vị đầu vào",
    "don_vi_ra": "Đơn vị đầu ra",
    # `he_so_ngoai_dong` · `cong_thuc_san_luong` · `don_vi_san_luong` GỠ 18/09/2026 (mg `0324`) —
    # nhãn giữ cho dòng nhật ký cũ.
    "he_so_ngoai_dong": "Hệ số vào → ra",
    "nhom_may_cho_phep": "Máy làm được công đoạn này",
    # `department_id` (một tổ) GỠ 18/09/2026 — nhãn giữ cho dòng nhật ký cũ. Nay tổ là DANH SÁCH,
    # gom thành chữ ở `_con_cua_cong_doan` (`to_phu_trach`).
    "department_id": "Tổ phụ trách",
    "to_phu_trach": "Tổ phụ trách",
    "khoan_ghi_theo": "Khoán ghi theo",
    "allowed_defect_pct": "Hỏng cho phép",
    "allowed_defect_abs": "Hỏng cho phép (số tuyệt đối)",
    "che_do_tinh": "Chế độ tính",
    "pricing_basis": "Cách tính giá",
    "setup_cost": "Phí chuẩn bị",
    "setup_time": "Thời gian chuẩn bị",
    "nang_suat": "Năng suất",
    "run_rate": "Đơn giá chạy",
    "rate_tiers": "Bậc đơn giá",
    "size_tiers": "Bậc theo khổ",
    "first_unit_floor": "Sàn đơn vị đầu",
    "min_charge": "Giá tối thiểu",
    "requires_tooling": "Cần khuôn / kẽm riêng",
    "tooling_type": "Loại dụng cụ",
    "spoilage_pct": "Tỷ lệ hao",
    "inline_flag": "Chạy nối tuyến (inline)",
    "cong_thuc_gia": "Công thức tính giá",
    # Ô của Giấy (mở lại 07/09/2026) và dòng vật tư của đầu việc dùng CHUNG nhãn này — cả hai đều
    # trả lời "một lệnh ăn bao nhiêu", nên gọi cùng một tên: "định mức".
    "cong_thuc_luong": "Công thức tính định mức",
    # Hai nhãn dưới: cột GỠ 18/09/2026 (mg `0324`), giữ cho dòng nhật ký cũ.
    "cong_thuc_san_luong": "Công thức sản lượng ra",
    "don_vi_san_luong": "Đơn vị sản lượng",
    # Bốn ô công thức chuyển về màn Công đoạn (06/09/2026) — thiếu nhãn là in tên cột thô ra.
    "cong_thuc_gio": "Công thức giờ chạy",
    "cong_thuc_khoan": "Công thức tính tiền công",
    "may_lam_duoc": "Máy chạy được công đoạn này",
    "vat_tus": "Vật tư và định mức",
    # Thành phẩm (mg 0203–0204, 0228) — mấy cột này nằm trên `vat_tu_in_an` nên nhật ký của MÀN
    # Vật tư khác cũng có thể chạm tới. Thiếu nhãn là in tên cột thô ra cho người dùng đọc.
    "customer_id": "Khách hàng",
    "order_id": "Đơn hàng gốc",
    "order_line_id": "Dòng đơn hàng gốc",
    # Công tắc chia hai màn danh mục (mg 0228). Người dùng KHÔNG khai ô này — repo tự đóng dấu —
    # nhưng nhật ký vẫn phải gọi được tên nó nếu có gì đó chạm vào.
    "la_thanh_pham": "Là thành phẩm",
    # Bù hao
    "bac": "Bậc số lượng",
    # Đơn vị & quy đổi
    "ho": "Họ đơn vị",
    "he_so_goc": "Hệ số về đơn vị gốc",
    "hieu_luc_tu": "Hiệu lực từ",
    "dung_lam_toc_do": "Dùng làm đơn vị tốc độ",
    "tram_dong_giay": "Trạm trên dòng giấy",
    # Chủng loại giấy · Giấy
    "chung_loai_giay_id": "Chủng loại giấy",
    "gsm": "Định lượng",
    "caliper_micron": "Độ dày",
    "gia_thi_truong": "Giá thị trường",
    "kho_tinh_gia": "Khổ dùng để tính giá",
    "version_no": "Phiên bản giá",
    # Khuôn bế — `khach_hang` là CHỮ tự do (khác `khach_hang_id` phía trên của bảng khác).
    "khach_hang": "Khách hàng",
    # `ngay_ve_du_kien` ĐÃ GỠ (mg `0293`) — nhật ký CŨ còn dòng đổi ô đó, nhưng nền nhật ký rơi về
    # chính tên khoá khi không tra được nhãn, nên không cần giữ mục chết ở đây.
    # Máy & thiết bị — tên cột thật của bảng `may_thiet_bi` (khác hẳn bộ khoá tiếng Anh phía trên,
    # bộ đó là của bảng `machines` đời cũ).
    "hang_san_xuat": "Hãng sản xuất",
    "model": "Model",
    "so_seri": "Số seri",
    "toc_do_min": "Tốc độ tối thiểu",
    "toc_do_max": "Tốc độ tối đa",
    "don_vi_toc_do": "Đơn vị tốc độ",
    "makeready_time_default": "Tổng thời gian chuẩn bị",
    "kho_max_dai": "Khổ giấy max — dài",
    "kho_max_rong": "Khổ giấy max — rộng",
    "kho_min_dai": "Khổ giấy min — dài",
    "kho_min_rong": "Khổ giấy min — rộng",
    "kho_kem_dai": "Khổ kẽm — dài",
    "kho_kem_rong": "Khổ kẽm — rộng",
    "vung_in_dai": "Vùng in max — dài",
    "vung_in_rong": "Vùng in max — rộng",
    "nhip_giay_mm": "Nhíp giấy",
    "le_hong_mm": "Lề hông",
    "duoi_thang_mau_mm": "Đuôi + thanh màu",
    # Công việc khoán (`piece_rates`, 17/08/2026) — tên cột đời cũ còn tiếng Anh, nhật ký in NHÃN.
    # `group_name` (nhãn tổ) GỠ 17/09/2026 cùng `department_id` của bảng này — nhãn giữ lại cho
    # dòng nhật ký cũ. Nay tổ là DANH SÁCH, gom thành chữ ở `_con_cua_cong_viec_khoan` (`to_lam`).
    "group_name": "Tổ (nhãn trên dòng)",
    "to_lam": "Tổ làm việc này",
    "unit": "Đơn vị",
    "unit_price": "Đơn giá",
    "cong_doan": "Công đoạn (cột cũ)",
    # Bảng con của công việc khoán (14/09/2026) — gom thành dict ở `_con_cua_cong_viec_khoan`.
    "viec_phat_sinh": "Việc phát sinh",
    # Tiêu chí KCS (`san_xuat_kcs_tieu_chi`, mg 0250) — chữ lấy đúng nhãn cột đang hiện trên màn
    # (`rebuildCatalogConfigs`), để đọc nhật ký xong tìm ra đúng cái ô đó trên form.
    "huong_dan": "Hướng dẫn",
    "bat_buoc": "Bắt buộc",
    "cong_doan_id": "Công đoạn",
}

# Hậu tố đơn vị cho vài trường số — để "100 → 120" không trần trụi.
HAU_TO: dict[str, str] = {
    "dinh_luong": "g/m²",
    "kho_rong": "cm",
    "kho_dai": "cm",
    "kho_toi_da": "cm",
    "kho_toi_thieu": "cm",
    "max_width_cm": "cm",
    "max_height_cm": "cm",
    "min_width_cm": "cm",
    "min_height_cm": "cm",
    "makeready_phut": "phút",
    "phut": "phút",          # khoá con của một khoản chuẩn bị (JSON), không phải cột
    "setup_time_mins": "phút",
    "changeover_time_mins": "phút",
    # 15/08/2026 — đơn vị của các cột vừa được đặt nhãn. Để ở ĐÂY chứ không nhét "(mm)" vào nhãn:
    # nhãn là tên Ô, hậu tố là đơn vị của SỐ, gộp lại thì câu thành "Nhíp kẽm (mm) 10 → 12".
    "gsm": "g/m²",
    "caliper_micron": "µm",
    "kho_max_dai": "mm", "kho_max_rong": "mm",
    "kho_min_dai": "mm", "kho_min_rong": "mm",
    "kho_kem_dai": "mm", "kho_kem_rong": "mm",
    "vung_in_dai": "mm", "vung_in_rong": "mm",
    "nhip_giay_mm": "mm",
    "le_hong_mm": "mm", "duoi_thang_mau_mm": "mm",
    "makeready_time_default": "phút",
    "setup_time": "phút",
    "allowed_defect_pct": "%",
    "spoilage_pct": "%",
}

# Trường TIỀN: hậu tố lấy theo ĐVT của chính bản ghi ("đ/kg", "đ/tờ") vì mỗi mặt hàng một đơn vị.
# `unit_price` = đơn giá khoán; ĐVT của nó nằm ở cột `unit` (xem `_hau_to`).
TIEN = frozenset({"don_gia", "gia", "don_gia_kg", "don_gia_to", "đon_gia", "unit_price"})

# Cột giữ MÃ đơn vị của danh mục Đơn vị & quy đổi — nhật ký in TÊN ("tờ", "bản kẽm"), không in mã
# ("to", "kem"): người đọc hiểu "đ/to" là chữ "to". `don_vi_toc_do` lưu `<mã>_gio`, xem `_ten_don_vi`.
DON_VI_MA = frozenset({"unit", "don_vi_gia", "don_vi_vao", "don_vi_ra", "don_vi_san_luong",
                       "don_vi_toc_do"})

# Ô CHỌN lưu MÃ → chữ đang hiện trong ô chọn trên màn (`rebuildCatalogConfigs.tsx`). Không có bảng
# này thì tổ bế tích nhận khuôn xong, Nhật ký ra "Tình trạng dang_dat_lam → dang_dung". Khoá theo
# tên trường như `NHAN`: mấy tên này chỉ có ở MỘT danh mục mỗi cái (khuôn · công đoạn). Mã lạ thì
# giữ nguyên mã. Thêm mã vào bộ hằng của model mà quên ở đây ⇒ `test_nhat_ky_nhan_du` đỏ.
_DUNG_CU = {"khuon_be": "Khuôn bế", "khuon_ep": "Khuôn ép kim", "khung_lua": "Khung lụa"}
GIA_TRI_NHAN: dict[str, dict[str, str]] = {
    "tinh_trang": {"dang_dung": "Đang dùng", "dang_dat_lam": "Đang đặt làm", "hong": "Hỏng",
                   "thanh_ly": "Thanh lý"},
    "loai": _DUNG_CU,
    "tooling_type": _DUNG_CU,
    "nhom": {"prepress": "Trước In", "print": "In", "finishing": "Gia công sau in",
             "other": "Dịch vụ khác"},
    "kieu_bu_hao": {"khong": "Không bù hao", "tra_bang": "Tra bảng theo mã bù hao",
                    "co_dinh": "Cộng cố định (số tờ)"},
}


def _la_so(v: Any) -> bool:
    """`True` KHÔNG phải số ở đây — nó là int trong Python nhưng phải hiện thành Có/Không."""
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _so(v: Decimal | float | int) -> str:
    """1234567.5 → '1.234.567,5' (kiểu Việt Nam). Số nguyên thì không kéo theo ',0'."""
    d = Decimal(str(v)).normalize()
    nguyen, _, le = f"{d:f}".partition(".")
    am = nguyen.startswith("-")
    nguyen = nguyen.lstrip("-")
    cum = f"{int(nguyen):,}".replace(",", ".") if nguyen else "0"
    return ("-" if am else "") + cum + (f",{le}" if le else "")


SUB_NHAN: dict[str, str] = {
    # Khoá con của ô JSON `fields_theo_loai` — lấy ĐÚNG chữ đang hiện trên form
    # (`rebuildCatalogConfigs.tsx`) để người đọc nhật ký nhận ra ngay ô nào vừa bị sửa.
    "chuan_bi_khoan": "Các khoản chuẩn bị",
    "lich_bao_tri": "Lịch bảo trì định kỳ",
    "so_luong_dao": "Số lượng dao",
    "duong_kinh": "Đường kính",
    "khoan_lo": "Khoan lỗ",
    "can_mang": "Cán màng",
    "be_noi": "Bế nổi",
    "ep_kim": "Ép kim",
    # Khoá nằm BÊN TRONG một dòng của danh sách (một gói bảo trì): viết thường vì chúng đi làm
    # phụ chú trong ngoặc — "Bảo trì tuần máy in (mỗi 1 tuần, từ 09/08/2026, 4 việc)".
    "ngay_bat_dau": "từ",
    "ghi_chu": "ghi chú",
    "so": "số",
    "don_vi": "đơn vị",
}

#: Khoá máy tự sinh trong một dòng JSON. Người dùng không hề thấy chúng trên form; để lọt vào
#: nhật ký thì được cái "Id: hm-seed-in-01-00" chẳng nói lên điều gì.
KHOA_KY_THUAT = frozenset({"id", "uid", "key", "step_key"})

#: Khoá mang TÊN của một dòng — đứng đầu cụm, phần còn lại lùi vào ngoặc.
KHOA_TEN = ("ten", "viec", "name", "nhan", "ma", "code")

#: Mã chu kỳ → chữ, đúng ô "Mỗi [số] [đơn vị]" của form Lịch bảo trì (`LichBaoTri.tsx`).
CHU_KY: dict[str, str] = {"ngay": "ngày", "tuan": "tuần", "thang": "tháng", "nam": "năm"}

#: Danh sách lồng bên trong một dòng thì ĐẾM chứ không bung: nhật ký kể việc, không vẽ lại form.
DEM: dict[str, str] = {"hang_muc": "việc"}

#: Số dòng in tối đa cho một danh sách. Một máy có thể khai hàng chục gói bảo trì — in hết thì
#: nhật ký lại thành bức tường chữ, đúng thứ đang phải sửa.
GIOI_HAN_MUC = 5

#: JSON không có kiểu ngày nên form gửi "2026-08-09"; người đọc nhật ký quen "09/08/2026".
_ISO_NGAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _nhan_con(k: str) -> str:
    """Nhãn cho một khoá con. Không có trong `SUB_NHAN` thì thà xấu còn hơn nuốt mất thay đổi —
    nhưng bỏ `.title()` đi: nó biến `lich_bao_tri` thành "Lich Bao Tri", trông như lỗi font."""
    if k in SUB_NHAN:
        return SUB_NHAN[k]
    # Khoá do chính chỗ gọi dựng sẵn thành câu (bảng con của Công đoạn) thì trả NGUYÊN:
    # `capitalize()` hạ hết chữ hoa phía sau, "IN-02 · Công thức giờ chạy" thành
    # "In-02 · công thức giờ chạy" — trông như lỗi dữ liệu.
    if " " in k:
        return k
    return k.replace("_", " ").capitalize()


def _muc(d: dict[str, Any]) -> str:
    """MỘT dòng của danh sách JSON → một cụm ngắn "Tên (phụ chú, phụ chú)".

    Bung thẳng từng khoá là cách cũ, và nó đẻ ra thứ trong ảnh chụp màn hình ngày 18/08/2026:
    `Id: hm-seed-in-01-00; Viec: Bảo trì tuần máy in; So: 1; Don Vi: tuan; Ngay Bat Dau: …`.
    Ở đây: bỏ khoá máy, tên đứng trước, số đi liền đơn vị, danh sách con chỉ đếm.
    """
    ten = next((str(d[k]).strip() for k in KHOA_TEN if not _rong(d.get(k))), "")
    phu: list[str] = []
    for k, val in d.items():
        if k in KHOA_KY_THUAT or k in KHOA_TEN or _rong(val):
            continue
        if k == "so" and not _rong(d.get("don_vi")):
            # "mỗi 3 tháng" — tách số khỏi đơn vị thì cả hai vế đều vô nghĩa.
            phu.append(f"mỗi {_chu(val)} {CHU_KY.get(str(d['don_vi']), str(d['don_vi']))}")
        elif k == "don_vi" and not _rong(d.get("so")):
            continue
        elif isinstance(val, (list, tuple)):
            phu.append(f"{len(val)} {DEM.get(k, 'mục')}")
        elif k in HAU_TO and _la_so(val):
            phu.append(f"{_so(val)} {HAU_TO[k]}")
        else:
            phu.append(f"{SUB_NHAN.get(k) or k.replace('_', ' ')} {_chu(val)}")
    if not ten:
        return ", ".join(phu) if phu else "Trống"
    return f"{ten} ({', '.join(phu)})" if phu else ten


def _gom(muc: list[str]) -> str:
    """Nối các dòng bằng "; ". KHÔNG dùng " · ": frontend cắt đúng chuỗi đó để tách trường
    (`NhatKyTab`), lỡ dùng là một thay đổi bị vẽ thành mấy dòng cụt nghĩa."""
    if len(muc) <= GIOI_HAN_MUC:
        return "; ".join(muc)
    return "; ".join(muc[:GIOI_HAN_MUC]) + f" … và {len(muc) - GIOI_HAN_MUC} mục nữa"


def _chu(v: Any) -> str:
    """Giá trị → chuỗi đọc được. None/rỗng thành '—' để mắt thấy ngay là bị bỏ trống."""
    if v is None or v == "":
        return "—"
    if isinstance(v, bool):
        return "Có" if v else "Không"
    if _la_so(v):
        return _so(v)
    if isinstance(v, datetime):
        return v.strftime("%H:%M %d/%m/%Y")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, str):
        return f"{v[8:10]}/{v[5:7]}/{v[:4]}" if _ISO_NGAY.fullmatch(v.strip()) else v
    if isinstance(v, dict):
        phan = [f"{_nhan_con(k)}: {_chu(val)}" for k, val in v.items() if not _rong(val)]
        return "; ".join(phan) if phan else "Trống"
    if isinstance(v, (list, tuple)):
        if not v:
            return "Trống"
        if any(isinstance(x, dict) for x in v):
            return _gom([_muc(x) if isinstance(x, dict) else _chu(x) for x in v])
        return ", ".join(_chu(x) for x in v)
    return str(v)


def _ten_don_vi(truong: str, ma: Any, bang: dict[str, str]) -> Any:
    """Mã đơn vị → tên theo danh mục; mã lạ giữ nguyên (luật của `nhan_don_vi`). Tốc độ máy lưu
    `to_gio` mà danh mục khoá theo `to`, nên cắt hậu tố rồi đọc "tờ/h" như cột Tốc độ của bảng máy."""
    if not isinstance(ma, str) or not ma.strip():
        return ma
    if truong == "don_vi_toc_do":
        return f"{nhan_don_vi(bang, ma_don_vi_goc(ma))}/h"
    return nhan_don_vi(bang, ma)


def _hau_to(truong: str, ban_ghi: dict[str, Any], bang: dict[str, str]) -> str:
    if truong in TIEN:
        # Hai tên cột cho cùng một ý "ĐVT của bản ghi này": `don_vi_gia` ở mặt hàng gốc, `unit` ở
        # công việc khoán. Đọc cả hai để "Đơn giá 250 → 300 đ/tờ" chứ không phải "đ" trần.
        dv = (ban_ghi.get("don_vi_gia") or ban_ghi.get("unit") or "").strip()
        return f"đ/{nhan_don_vi(bang, dv)}" if dv else "đ"
    return HAU_TO.get(truong, "")


def anh_chup(obj: Any) -> dict[str, Any]:
    """Chụp mọi cột nghiệp vụ của một bản ghi ORM.

    Đọc cột từ chính model (không khai tay từng danh mục) — thêm cột mới vào bảng là nhật ký
    tự theo dõi luôn, không ai phải nhớ cập nhật chỗ này.
    """
    if obj is None:
        return {}
    cols = sa_inspect(type(obj)).columns.keys()
    ra = {c: getattr(obj, c, None) for c in cols if c not in BO_QUA}
    ra.update(_con_cua_cong_doan(obj))
    ra.update(_con_cua_cong_viec_khoan(obj))
    return ra


def _con_cua_cong_viec_khoan(obj: Any) -> dict[str, Any]:
    """Việc phát sinh của công việc khoán → dict `{tên việc: "100 đ/bản kẽm"}` để nhật ký so từng việc.

    Kèm `to_lam` — DANH SÁCH tổ in thành một chuỗi tên ("Tổ Bế, Tổ Thành phẩm"): thêm/gỡ một tổ đọc
    ra một dòng "trước → sau". Tổ đã xoá khỏi cây tổ chức in "(tổ #id đã xoá)" chứ không bỏ trắng.

    Cùng lý do với `_con_cua_cong_doan`: `columns` không thấy bảng con, không gom thì đổi đơn giá
    thay kẽm không để lại vết nào. Khoá theo TÊN (thứ người đọc nhật ký nhận ra), nên đổi tên một
    việc hiện thành hai dòng "tên cũ … → —" và "tên mới — → …". Luôn trả khoá kể cả khi rỗng —
    thiếu khoá ở ảnh "sau" thì lần xoá sạch danh sách im lặng.

    Đơn vị in bằng TÊN danh mục ("100 đ/bản kẽm"), không in mã: "50 đ/to" người đọc nhật ký hiểu
    là chữ "to". Tra qua session của chính bản ghi — ảnh chụp trước và sau cùng một luật tra.
    """
    if getattr(obj, "__tablename__", "") != "piece_rates":
        return {}
    viecs = getattr(obj, "viec_phat_sinh", None) or []
    ids = list(getattr(obj, "department_ids", None) or [])
    s = sa_inspect(obj).session if (viecs or ids) else None
    bang = DonViDoRepository(s).ten_theo_ma() if s is not None and viecs else {}
    to = CongViecKhoanRepository(s).to_theo_id(ids) if s is not None and ids else {}
    return {
        "to_lam": ", ".join(to[i][1] if i in to else f"(tổ #{i} đã xoá)" for i in ids) or None,
        "viec_phat_sinh": {
            v.ten: f"{_so(v.don_gia)} đ/{nhan_don_vi(bang, v.don_vi)}" for v in viecs
        },
    }


def _con_cua_cong_doan(obj: Any) -> dict[str, dict[str, Any]]:
    """Công thức nằm ở BẢNG CON của công đoạn, gom lại thành dict con để nhật ký so được.

    `columns` chỉ thấy cột của CHÍNH bảng, nên nếu không gom ở đây thì sửa công thức giá của một
    máy — thứ đổi thẳng vào tiền báo giá — không để lại vết nào trong Nhật ký danh mục.
    `mo_ta_thay_doi` đã biết so từng khoá con của dict, nên mỗi máy / đầu việc ra đúng một dòng.

    Luôn trả MỌI khoá kể cả khi rỗng: thiếu khoá ở ảnh "sau" thì vòng lặp của
    `mo_ta_thay_doi` không ghé qua, và lần xoá sạch máy sẽ im lặng.
    """
    if getattr(obj, "__tablename__", "") != "cong_doan":
        return {}
    s = sa_inspect(obj).session
    # Tổ phụ trách là DANH SÁCH (mg `0312`) — in thành một chuỗi tên như `to_lam` của công việc khoán.
    ids = list(getattr(obj, "department_ids", None) or [])
    to = CongViecKhoanRepository(s).to_theo_id(ids) if s is not None and ids else {}
    to_phu_trach = ", ".join(to[i][1] if i in to else f"(tổ #{i} đã xoá)" for i in ids) or None
    # Khoá con in TÊN máy / vật tư ("Heidelberg SM102 (MAY-01)"), không in id — "Máy #55" người đọc
    # nhật ký không tra ra được. Kèm mã vì tên có thể trùng: hai máy cùng tên chung một khoá là
    # thay đổi của máy này đè mất máy kia. Tra theo lô, một câu cho cả danh sách.
    # Nối nhãn bằng " › ", KHÔNG bằng " · ": `ghi_sua` nối các thay đổi bằng " · " và `NhatKyTab`
    # cắt đúng chuỗi đó — khoá chứa " · " là một thay đổi bị vẽ thành hai dòng cụt.
    mays = list(getattr(obj, "may_lam_duoc", None) or [])
    vts = list(getattr(obj, "vat_tus", None) or [])
    repo = CongDoanRepository(s) if s is not None else None
    ten_may = repo.mays({r.may_id for r in mays}) if repo and mays else {}
    ten_vt = repo.vat_tus({v.vat_tu_id for v in vts}) if repo and vts else {}
    may: dict[str, Any] = {}
    for r in mays:
        for truong in ("cong_thuc_gio", "cong_thuc_gia"):
            may[f"{_ten_con(ten_may.get(r.may_id), 'máy', r.may_id)} › {NHAN[truong]}"] = getattr(
                r, truong, None)
    # Vật tư của công đoạn (mg `0316`) — MỘT tầng, mỗi món một dòng.
    vt: dict[str, Any] = {}
    for v in vts:
        vt[f"{_ten_con(ten_vt.get(v.vat_tu_id), 'vật tư', v.vat_tu_id)} › "
           f"{NHAN['cong_thuc_luong']}"] = getattr(v, "cong_thuc_luong", None)
    # Khoán là aggregate 1–1 của công đoạn (mg 0326). Chụp cả công thức lẫn từng việc phát sinh;
    # nếu không, người sửa đơn giá trong tab Khoán mà Nhật ký chỉ báo "đã sửa Công đoạn" trống.
    khoan_obj = getattr(obj, "khoan", None)
    khoan: dict[str, Any] = {}
    if khoan_obj is not None:
        bang_dv = DonViDoRepository(s).ten_theo_ma() if s is not None else {}
        khoan = {
            "Đơn vị tính khoán": nhan_don_vi(bang_dv, khoan_obj.unit),
            "Đơn giá khoán": f"{_so(khoan_obj.unit_price)} đ",
            "Công thức khoán": khoan_obj.cong_thuc_khoan,
        }
        for ps in getattr(khoan_obj, "viec_phat_sinh", None) or []:
            khoan[f"Việc phát sinh › {ps.ten}"] = (
                f"{_so(ps.don_gia)} đ/{nhan_don_vi(bang_dv, ps.don_vi)}"
            )
    return {
        "to_phu_trach": to_phu_trach, "may_lam_duoc": may, "vat_tus": vt, "khoan": khoan,
    }


def _ten_con(ban_ghi: Any, loai: str, id_: int) -> str:
    """Tên một dòng bảng con trong khoá nhật ký: "Tên (mã)"; bản ghi đã xoá thì "(máy #55 đã xoá)"
    như tổ phụ trách — không bỏ trắng. Tên tự gõ có " · " thì đổi đi (xem `_gom_dong`)."""
    if ban_ghi is None:
        return f"({loai} #{id_} đã xoá)"
    ten = (getattr(ban_ghi, "ten", None) or "").strip()
    ma = (getattr(ban_ghi, "ma", None) or "").strip()
    return f"{ten} ({ma})" if ten and ma else (ten or ma or f"{loai.capitalize()} #{id_}")


def _rong(v: Any) -> bool:
    """"Chưa có gì" dưới mọi hình dạng: None · "" · [] · {} · và dict/list mà mọi phần tử đều rỗng.

    `{"chuan_bi_khoan": []}` cũng là RỖNG — đó vẫn là "chưa thiết lập khoản nào", chỉ khác cách
    lưu. Không có luật này thì đổi mỗi Loại máy cũng đẻ thêm dòng "Thông số theo loại máy: —
    → Các khoản chuẩn bị: …", vì form luôn gửi kèm ô JSON đó.
    """
    if v is None or v == "":
        return True
    if isinstance(v, (list, tuple, set)):
        return all(_rong(x) for x in v)
    if isinstance(v, dict):
        return all(_rong(x) for x in v.values())
    return False


def _khac(cu: Any, moi: Any) -> bool:
    """Hai giá trị có khác nhau DƯỚI MẮT người dùng không. Dùng cho cả cột lẫn khoá con."""
    if cu == moi:
        return False
    # 100 (int) vs 100.00 (Decimal) là CÙNG một giá trị — so thô sẽ đẻ ra thay đổi ma.
    # `bool` PHẢI loại trước: trong Python nó là con của `int`, mà Decimal("True") thì nổ.
    if _la_so(cu) and _la_so(moi) and Decimal(str(cu)) == Decimal(str(moi)):
        return False
    # Trống → vẫn trống (chỉ khác cách lưu) thì KHÔNG phải thay đổi của người dùng.
    return not (_rong(cu) and _rong(moi))


def mo_ta_thay_doi(truoc: dict[str, Any], sau: dict[str, Any], *,
                   ten_don_vi: dict[str, str] | None = None) -> list[str]:
    """Các dòng "Nhãn cũ → mới", chỉ cho trường THỰC SỰ đổi.

    `ten_don_vi` = bảng MÃ → TÊN (`DonViDoRepository.ten_theo_ma`) để in đơn vị bằng tên; bỏ trống
    thì in mã. Hàm giữ thuần — nơi gọi nạp bảng (`ghi_sua`)."""
    bang = ten_don_vi or {}
    dong: list[str] = []
    for truong, moi in sau.items():
        cu = truoc.get(truong)
        if not _khac(cu, moi):
            continue
        nhan = NHAN.get(truong, truong)
        # Ô JSON (`fields_theo_loai`) nhét NHIỀU nhóm rời nhau vào MỘT cột. So nguyên cục thì sửa
        # một khoản chuẩn bị cũng lôi cả lịch bảo trì ra in hai lần, hai vế giống hệt nhau — dòng
        # nhật ký dài cả màn hình mà không chỉ ra được cái gì vừa đổi. So TỪNG khoá con, chỉ in
        # khoá nào thật sự đổi.
        if isinstance(cu, dict) or isinstance(moi, dict):
            d_cu = cu if isinstance(cu, dict) else {}
            d_moi = moi if isinstance(moi, dict) else {}
            for k in [*d_moi, *(k for k in d_cu if k not in d_moi)]:
                if not _khac(d_cu.get(k), d_moi.get(k)):
                    continue
                dong.append(
                    f"{nhan} › {_nhan_con(k)} {_chu(d_cu.get(k))} → {_chu(d_moi.get(k))}")
            continue
        if truong in DON_VI_MA:
            cu, moi = _ten_don_vi(truong, cu, bang), _ten_don_vi(truong, moi, bang)
        elif truong in GIA_TRI_NHAN:
            nhan_ma = GIA_TRI_NHAN[truong]
            cu, moi = (nhan_ma.get(v, v) if isinstance(v, str) else v for v in (cu, moi))
        hau = _hau_to(truong, sau, bang)
        dong.append(f"{nhan} {_chu(cu)} → {_chu(moi)}{(' ' + hau) if hau else ''}")
    return dong


def _bang_don_vi(obj: Any, truoc: dict[str, Any], sau: dict[str, Any]) -> dict[str, str]:
    """Bảng MÃ → TÊN đơn vị, CHỈ nạp khi lần lưu này đổi trường tiền / trường mã đơn vị — sửa tên
    hay ghi chú thì khỏi tốn thêm câu SQL. Tra qua session của chính bản ghi, như bảng con."""
    if not any(t in TIEN or t in DON_VI_MA for t, v in sau.items() if _khac(truoc.get(t), v)):
        return {}
    s = sa_inspect(obj).session
    return DonViDoRepository(s).ten_theo_ma() if s is not None else {}


def _ghi(audit: AuditLogRepository | None, *, actor_id: int | None, action: str,
         loai: str, obj_id: int, detail: str) -> None:
    if audit is None:
        return
    audit.create(
        actor_user_id=actor_id, action=action, target=f"{loai}:{obj_id}", detail=detail,
    )


def ghi_tao(audit, *, actor_id: int | None, loai: str, obj: Any) -> None:
    ten = getattr(obj, "ten", None) or getattr(obj, "ma", "") or ""
    _ghi(audit, actor_id=actor_id, action=ACTION_TAO, loai=loai, obj_id=obj.id, detail=str(ten))


def _ghi_lich_su_cong_thuc(audit: AuditLogRepository | None, *, actor_id: int | None,
                            loai: str, obj_id: int, truoc: dict[str, Any],
                            sau: dict[str, Any]) -> None:
    """Trường công thức đổi → thêm 1 dòng `cong_thuc_lich_su`. `db.add()` không tự `commit` —
    cưỡi chung giao dịch với `_ghi()` gọi ngay sau (xem `CongThucLichSuRepository.ghi`)."""
    if audit is None:
        return
    repo = CongThucLichSuRepository(audit.db)
    for truong in CONG_THUC_TRUONG:
        if truong not in sau:
            continue
        cu, moi = truoc.get(truong), sau.get(truong)
        if not _khac(cu, moi):
            continue
        repo.ghi(bang=loai, row_id=obj_id, truong=truong,
                 gia_tri_cu=cu, gia_tri_moi=moi, sua_boi=actor_id)


def ghi_sua(audit, *, actor_id: int | None, loai: str, obj: Any,
            truoc: dict[str, Any]) -> None:
    """Ghi MỘT dòng cho cả lần lưu — sửa 3 trường vẫn là một lần bấm Lưu, tách ra thì nhật ký
    loãng và mất ngữ cảnh. Không đổi gì thì không ghi (bấm Lưu mà giữ nguyên = không phải sự kiện)."""
    sau = anh_chup(obj)
    dong = mo_ta_thay_doi(truoc, sau, ten_don_vi=_bang_don_vi(obj, truoc, sau))
    if not dong:
        return
    _ghi_lich_su_cong_thuc(audit, actor_id=actor_id, loai=loai, obj_id=obj.id, truoc=truoc, sau=sau)
    _ghi(audit, actor_id=actor_id, action=ACTION_SUA, loai=loai, obj_id=obj.id,
         detail=_gom_dong(dong))


#: Dấu nối các thay đổi của MỘT lần lưu — `NhatKyTab` cắt đúng chuỗi này để vẽ từng dòng.
PHAN_CACH = " · "


def _gom_dong(dong: list[str]) -> str:
    """Nối các thay đổi bằng `PHAN_CACH`. Chuỗi đó mà lọt VÀO TRONG một dòng (tên máy, tên tổ,
    ghi chú người dùng tự gõ "In 4 màu · khổ lớn") thì màn cắt một thay đổi thành hai dòng cụt —
    nên đổi nó đi trước khi nối."""
    return PHAN_CACH.join(d.replace(PHAN_CACH, " – ") for d in dong)


def ghi_xoa(audit, *, actor_id: int | None, loai: str, obj: Any) -> None:
    ten = getattr(obj, "ten", None) or getattr(obj, "ma", "") or ""
    _ghi(audit, actor_id=actor_id, action=ACTION_XOA, loai=loai, obj_id=obj.id, detail=str(ten))
