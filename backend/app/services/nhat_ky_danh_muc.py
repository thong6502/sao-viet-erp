"""Nhật ký thao tác cho các màn Cấu hình danh mục — MỘT chỗ dựng dòng "ai đổi gì".

Vì sao gom về đây: 10 màn danh mục đều là CRUD trên một bảng phẳng, nếu mỗi service tự viết
"so sánh trước/sau rồi ghi audit" thì thành 10 bản chép tay lệch nhau — chỗ ghi giá cũ, chỗ
quên, chỗ đặt tên action khác. Ở đây làm một lần, service chỉ gọi `ghi_tao` / `ghi_sua` / `ghi_xoa`.

Ghi vào bảng `audit_logs` sẵn có (target = `"{loai}:{id}"`, đúng quy ước của khách hàng · nhân sự ·
lệnh SX), KHÔNG đẻ bảng mới. Nhờ vậy các dòng này cũng chảy vào màn Nhật ký chung.

Dòng chi tiết trông như: `Đơn giá 27.800 → 29.000 đ/kg · Định lượng 100 → 120 g/m²`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect

from ..repositories.audit_repo import AuditLogRepository

# --- Hành động: một tên cho mỗi loại thao tác, frontend dịch sang nhãn + icon --------------
ACTION_TAO = "dm_tao"
ACTION_SUA = "dm_sua"
ACTION_XOA = "dm_xoa"

# Cột kỹ thuật — đổi cũng không ai quan tâm, ghi vào chỉ làm nhiễu nhật ký.
BO_QUA = frozenset({
    "id", "created_at", "updated_at", "created_by", "updated_by", "deleted_at",
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
    # Máy · công đoạn · bù hao
    "loai": "Loại",
    "loai_may": "Loại máy",
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
    "cho_ky_thuat_gio": "Chờ kỹ thuật (giờ)",
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
    "cho_ky_thuat_gio": "giờ",
    "setup_time_mins": "phút",
    "changeover_time_mins": "phút",
}

# Trường TIỀN: hậu tố lấy theo ĐVT của chính bản ghi ("đ/kg", "đ/tờ") vì mỗi mặt hàng một đơn vị.
TIEN = frozenset({"don_gia", "gia", "don_gia_kg", "don_gia_to", "đon_gia"})


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
    "chuan_bi_khoan": "Chuẩn bị khoan",
    "so_luong_dao": "Số lượng dao",
    "duong_kinh": "Đường kính",
    "khoan_lo": "Khoan lỗ",
    "can_mang": "Cán màng",
    "be_noi": "Bế nổi",
    "ep_kim": "Ép kim",
}


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
    if isinstance(v, dict):
        if not v:
            return "Trống"
        items = []
        for k, val in v.items():
            k_lbl = SUB_NHAN.get(k, k.replace("_", " ").title())
            if isinstance(val, (list, tuple)):
                v_lbl = ", ".join(_chu(x) for x in val) if val else "Chưa thiết lập"
            else:
                v_lbl = _chu(val)
            items.append(f"{k_lbl}: {v_lbl}")
        return "; ".join(items) if items else "Trống"
    if isinstance(v, (list, tuple)):
        if not v:
            return "Trống"
        return ", ".join(_chu(x) for x in v)
    return str(v)


def _hau_to(truong: str, ban_ghi: dict[str, Any]) -> str:
    if truong in TIEN:
        dv = (ban_ghi.get("don_vi_gia") or "").strip()
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
    → Chuẩn bị khoan: Chưa thiết lập", vì form luôn gửi kèm ô JSON đó.
    """
    if v is None or v == "":
        return True
    if isinstance(v, (list, tuple, set)):
        return all(_rong(x) for x in v)
    if isinstance(v, dict):
        return all(_rong(x) for x in v.values())
    return False


def mo_ta_thay_doi(truoc: dict[str, Any], sau: dict[str, Any]) -> list[str]:
    """Các dòng "Nhãn cũ → mới", chỉ cho trường THỰC SỰ đổi."""
    dong: list[str] = []
    for truong, moi in sau.items():
        cu = truoc.get(truong)
        if cu == moi:
            continue
        # 100 (int) vs 100.00 (Decimal) là CÙNG một giá trị — so thô sẽ đẻ ra thay đổi ma.
        # `bool` PHẢI loại trước: trong Python nó là con của `int`, mà Decimal("True") thì nổ.
        if _la_so(cu) and _la_so(moi) and Decimal(str(cu)) == Decimal(str(moi)):
            continue
        # Trống → vẫn trống (chỉ khác cách lưu) thì KHÔNG phải thay đổi của người dùng.
        if _rong(cu) and _rong(moi):
            continue
        hau = _hau_to(truong, sau)
        nhan = NHAN.get(truong, truong)
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


def ghi_sua(audit, *, actor_id: int | None, loai: str, obj: Any,
            truoc: dict[str, Any]) -> None:
    """Ghi MỘT dòng cho cả lần lưu — sửa 3 trường vẫn là một lần bấm Lưu, tách ra thì nhật ký
    loãng và mất ngữ cảnh. Không đổi gì thì không ghi (bấm Lưu mà giữ nguyên = không phải sự kiện)."""
    dong = mo_ta_thay_doi(truoc, anh_chup(obj))
    if not dong:
        return
    _ghi(audit, actor_id=actor_id, action=ACTION_SUA, loai=loai, obj_id=obj.id,
         detail=" · ".join(dong))


def ghi_xoa(audit, *, actor_id: int | None, loai: str, obj: Any) -> None:
    ten = getattr(obj, "ten", None) or getattr(obj, "ma", "") or ""
    _ghi(audit, actor_id=actor_id, action=ACTION_XOA, loai=loai, obj_id=obj.id, detail=str(ten))
