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

from ..repositories.audit_repo import AuditLogRepository
from ..repositories.cong_thuc_lich_su_repo import CongThucLichSuRepository

# --- Hành động: một tên cho mỗi loại thao tác, frontend dịch sang nhãn + icon --------------
ACTION_TAO = "dm_tao"
ACTION_SUA = "dm_sua"
ACTION_XOA = "dm_xoa"

# Trường công thức — đổi thì ghi thêm 1 dòng có cấu trúc vào `cong_thuc_lich_su` (xem docstring
# đầu file). Chỉ 2 trường này vì chỉ 2 tên cột công thức tồn tại trên cả 5 danh mục.
CONG_THUC_TRUONG = frozenset({"cong_thuc_luong", "cong_thuc_san_luong"})

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
    "he_so_ngoai_dong": "Hệ số vào → ra",
    "nhom_may_cho_phep": "Máy làm được công đoạn này",
    "department_id": "Tổ phụ trách",
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
    "cong_thuc_luong": "Công thức tính lượng",
    "cong_thuc_san_luong": "Công thức sản lượng ra",
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
    # Nhãn NGƯỜI DÙNG ĐỌC trong Nhật ký — phải khớp nhãn ô trên màn Khuôn, không thì cùng một thay
    # đổi mà hai chỗ gọi hai tên. "Có khuôn" chứ không "về": xưởng tự làm dao thì không về đâu cả.
    "ngay_ve_du_kien": "Ngày có khuôn (dự kiến)",
    # Máy & thiết bị — tên cột thật của bảng `may_thiet_bi` (khác hẳn bộ khoá tiếng Anh phía trên,
    # bộ đó là của bảng `machines` đời cũ).
    "hang_san_xuat": "Hãng sản xuất",
    "model": "Model",
    "so_seri": "Số seri",
    "toc_do_min": "Tốc độ tối thiểu",
    "toc_do_max": "Tốc độ tối đa",
    "don_vi_toc_do": "Đơn vị tốc độ",
    "makeready_time_default": "Tổng thời gian chuẩn bị",
    "so_nhan_cong": "Số người vận hành tiêu chuẩn",
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
    # `group_name` là NHÃN TỔ lưu trên dòng, khác `department_id` là con trỏ sang cây tổ chức: sửa
    # tổ thì cả hai cùng đổi, nên phải đọc ra hai câu khác nhau mới hiểu chuyện gì xảy ra.
    "group_name": "Tổ (nhãn trên dòng)",
    "unit": "Đơn vị",
    "unit_price": "Đơn giá",
    "cong_doan": "Công đoạn (cột cũ)",
    # Tiêu chí KCS (`san_xuat_kcs_tieu_chi`, mg 0250) — chữ lấy đúng nhãn cột đang hiện trên màn
    # (`rebuildCatalogConfigs`), để đọc nhật ký xong tìm ra đúng cái ô đó trên form.
    "huong_dan": "Hướng dẫn",
    "bat_buoc": "Bắt buộc",
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
    return SUB_NHAN.get(k) or k.replace("_", " ").capitalize()


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


def _hau_to(truong: str, ban_ghi: dict[str, Any]) -> str:
    if truong in TIEN:
        # Hai tên cột cho cùng một ý "ĐVT của bản ghi này": `don_vi_gia` ở mặt hàng gốc, `unit` ở
        # công việc khoán. Đọc cả hai để "Đơn giá 250 → 300 đ/tờ" chứ không phải "đ" trần.
        dv = (ban_ghi.get("don_vi_gia") or ban_ghi.get("unit") or "").strip()
        return f"đ/{dv}" if dv else "đ"
    return HAU_TO.get(truong, "")


def anh_chup(obj: Any) -> dict[str, Any]:
    """Chụp mọi cột nghiệp vụ của một bản ghi ORM.

    Đọc cột từ chính model (không khai tay từng danh mục) — thêm cột mới vào bảng là nhật ký
    tự theo dõi luôn, không ai phải nhớ cập nhật chỗ này.
    """
    if obj is None:
        return {}
    cols = sa_inspect(type(obj)).columns.keys()
    return {c: getattr(obj, c, None) for c in cols if c not in BO_QUA}


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


def mo_ta_thay_doi(truoc: dict[str, Any], sau: dict[str, Any]) -> list[str]:
    """Các dòng "Nhãn cũ → mới", chỉ cho trường THỰC SỰ đổi."""
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
        hau = _hau_to(truong, sau)
        dong.append(f"{nhan} {_chu(cu)} → {_chu(moi)}{(' ' + hau) if hau else ''}")
    return dong


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
    dong = mo_ta_thay_doi(truoc, sau)
    if not dong:
        return
    _ghi_lich_su_cong_thuc(audit, actor_id=actor_id, loai=loai, obj_id=obj.id, truoc=truoc, sau=sau)
    _ghi(audit, actor_id=actor_id, action=ACTION_SUA, loai=loai, obj_id=obj.id,
         detail=" · ".join(dong))


def ghi_xoa(audit, *, actor_id: int | None, loai: str, obj: Any) -> None:
    ten = getattr(obj, "ten", None) or getattr(obj, "ma", "") or ""
    _ghi(audit, actor_id=actor_id, action=ACTION_XOA, loai=loai, obj_id=obj.id, detail=str(ten))
