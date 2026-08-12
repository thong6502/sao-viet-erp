"""Bảng VAI MẪU — bấm một phát ra sẵn bộ quyền cho một vai điển hình (đợt 6, 11/08/2026).

VÌ SAO CẦN: sau đợt tách quyền, ma trận dài ~32 khoá. Cấp tay cho một vai mới mất 10–15 phút và
rất dễ tick nhầm. Rủi ro thật không phải là "mất thời gian" mà là **người ta cấp bừa cho xong** —
tick hết cho nhanh — và như thế còn LỎNG HƠN trước khi tách. Vai mẫu là cái chống lại đúng chuyện đó.

CÁCH DÙNG: mẫu chỉ ĐIỀN SẴN ma trận đang mở ở giao diện. Quản trị xem lại rồi mới bấm Lưu — không
có đường nào ghi thẳng vào DB từ đây. Nhờ vậy chọn nhầm mẫu cũng không hỏng gì.

QUY ƯỚC KHAI:
- Mỗi mẫu khai theo kiểu `{khoa_module: {ten_co: True, "scope": "..."}}`. Cờ nào KHÔNG khai là
  TẮT — không có chuyện "kế thừa" ngầm, nhìn là biết vai đó được gì.
- `self_service` + `noi_quy` KHÔNG khai trong mẫu: mọi vai mới sinh ra đã có sẵn hai ô đó
  (`RoleRepository.O_MAC_DINH`). Khai lại chỉ làm mẫu dài ra mà không đổi gì.
- Có guard test đối chiếu MỌI khoá module và MỌI tên cờ với model thật — gõ sai là test đỏ, không
  phải tới lúc quản trị bấm mới biết.
"""

from __future__ import annotations

from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN

# ---------------------------------------------------------------------------
# Cụm quyền dùng lại giữa các mẫu. Viết hàm thay vì hằng để mỗi mẫu có bản sao
# riêng — sửa mẫu này không đụng mẫu kia.


def _xem(scope: str) -> dict:
    return {"can_read": True, "scope": scope}


def _tu_phuc_vu_nghi_phep() -> dict:
    """Nhân viên tự gửi + tự huỷ đơn nghỉ của CHÍNH MÌNH (không duyệt ai)."""
    return {"can_read": True, "can_create": True, "can_cancel": True, "scope": SCOPE_OWN}


def _duyet_don_cua_to(scope: str = SCOPE_DEPARTMENT) -> dict:
    """Duyệt đơn nghỉ / phiếu tăng ca / đi muộn của người trong tổ (+ khai hộ)."""
    return {
        "can_read": True, "can_create": True, "can_approve": True, "can_cancel": True,
        "scope": scope,
    }


TEMPLATES: list[dict] = [
    {
        "key": "cong_nhan",
        "label": "Công nhân",
        "mo_ta": (
            "Chỉ làm việc với hồ sơ của chính mình: chấm công, xem công và phiếu lương của mình, "
            "tự gửi đơn nghỉ / phiếu tăng ca / xin tạm ứng. Không thấy dữ liệu của ai khác."
        ),
        "quyen": {
            "dashboard": _xem(SCOPE_OWN),
            # Vào được màn Chấm công để bấm giờ; KHÔNG có `can_read` nên không thấy bảng công của
            # người khác — nút chấm công đi theo ô Tự phục vụ (bật sẵn cho mọi vai mới).
            "nghi_phep": _tu_phuc_vu_nghi_phep(),
            "tang_ca": {"can_read": True, "can_create": True, "can_cancel": True, "scope": SCOPE_OWN},
            "di_muon": {"can_read": True, "can_create": True, "can_cancel": True, "scope": SCOPE_OWN},
        },
    },
    {
        "key": "to_truong",
        "label": "Tổ trưởng",
        "mo_ta": (
            "Công nhân + quản người trong tổ mình: xem bảng công và nhật ký của tổ, duyệt đơn nghỉ "
            "/ tăng ca / đi muộn của tổ, đề nghị lĩnh vật tư và lập yêu cầu mua hàng. "
            "KHÔNG chấm bù, KHÔNG chốt kỳ."
        ),
        "quyen": {
            "dashboard": _xem(SCOPE_OWN),
            "san_xuat": {
                "can_read": True, "can_assign_work": True, "can_record_output": True,
                "can_handover": True, "scope": SCOPE_OWN,
            },
            # Xem công + nhật ký của tổ để biết ai vắng, ai đi muộn. KHÔNG `can_adjust` (chấm bù)
            # và KHÔNG `can_lock` (chốt kỳ) — hai việc đó của HCNS.
            "cham_cong": {"can_read": True, "can_view_log": True, "scope": SCOPE_DEPARTMENT},
            "nghi_phep": _duyet_don_cua_to(),
            "tang_ca": _duyet_don_cua_to(),
            "di_muon": _duyet_don_cua_to(),
            "kho": {
                "can_read": True, "can_request": True, "can_approve": True,
                "scope": SCOPE_DEPARTMENT,
            },
            "yeu_cau_mua_hang": {
                "can_read": True, "can_create": True, "can_update": True,
                "scope": SCOPE_DEPARTMENT,
            },
        },
    },
    {
        "key": "hcns",
        "label": "Hành chính nhân sự",
        "mo_ta": (
            "Quản hồ sơ nhân sự và chấm công toàn công ty: chấm bù, chốt kỳ công, duyệt đơn nghỉ / "
            "tăng ca / đi muộn, tính và chốt bảng lương. KHÔNG có ô 'Đánh dấu đã chi lương' — "
            "cái đó để kế toán xác nhận khi tiền thật sự ra."
        ),
        "quyen": {
            "dashboard": _xem(SCOPE_ALL),
            "phong_ban": {"can_read": True, "can_set_head": True, "scope": SCOPE_ALL},
            "nhan_su": {
                "can_read": True, "can_create": True, "can_update": True,
                "can_view_salary": True, "can_edit_salary": True, "can_manage_status": True,
                "can_transfer": True, "can_approve": True, "can_export": True,
                "scope": SCOPE_ALL,
            },
            "cham_cong": {
                "can_read": True, "can_view_log": True, "can_update": True,
                "can_adjust": True, "can_lock": True, "scope": SCOPE_ALL,
            },
            # Ô riêng từ 11/08/2026 — tách khỏi ô Chấm bù của màn Chấm công.
            "yeu_cau_chinh_cong": {"can_read": True, "can_approve": True, "scope": SCOPE_ALL},
            "nghi_phep": {
                "can_read": True, "can_create": True, "can_update": True, "can_delete": True,
                "can_approve": True, "can_cancel": True, "scope": SCOPE_ALL,
            },
            "tang_ca": _duyet_don_cua_to(SCOPE_ALL),
            "di_muon": _duyet_don_cua_to(SCOPE_ALL),
            "luong": {
                "can_read": True, "can_create": True, "can_update": True,
                "can_approve": True,      # duyệt tạm ứng
                "can_lock": True,         # chốt bảng lương / mở lại kỳ
                "can_export": True,
                "can_view_salary": True, "can_edit_salary": True,
                "scope": SCOPE_ALL,
            },
            "noi_quy": {"can_read": True, "can_create": True, "can_delete": True, "scope": SCOPE_ALL},
        },
    },
    {
        "key": "ke_toan",
        "label": "Kế toán",
        "mo_ta": (
            "Đơn mua hàng, phiếu chi, phiếu thu, công nợ, tài khoản ngân hàng — và xác nhận "
            "'đã chi lương' khi tiền thật sự ra. KHÔNG duyệt đơn mua hàng (người duyệt chi phải "
            "khác người viết phiếu chi)."
        ),
        "quyen": {
            "dashboard": _xem(SCOPE_ALL),
            "ke_toan": _xem(SCOPE_ALL),          # màn Đơn mua hàng — CHỈ xem, không duyệt
            "phieu_chi": {
                "can_read": True, "can_create": True, "can_cancel": True, "can_export": True,
                "scope": SCOPE_ALL,
            },
            "phieu_thu": {
                "can_read": True, "can_create": True, "can_manage_status": True,
                "can_cancel": True, "can_export": True, "scope": SCOPE_ALL,
            },
            "cong_no_phai_tra": _xem(SCOPE_ALL),
            "cong_no_phai_thu": _xem(SCOPE_ALL),
            "tk_ngan_hang": {"can_read": True, "can_update": True, "scope": SCOPE_ALL},
            "nha_cung_cap": _xem(SCOPE_ALL),
            "thu_mua": _xem(SCOPE_ALL),          # xem phiếu mua để đối chiếu trước khi chi
            # Lương: XEM bảng lương + ô "Đánh dấu đã chi" (tách khỏi ô Chốt ở đợt 4).
            # KHÔNG `can_lock`: chốt số là việc của HCNS, kế toán chỉ xác nhận tiền đã ra.
            "luong": {
                "can_read": True, "can_manage_status": True, "can_export": True,
                "can_view_salary": True, "scope": SCOPE_ALL,
            },
        },
    },
    {
        "key": "thu_mua",
        "label": "Thu mua",
        "mo_ta": (
            "Nhận yêu cầu mua hàng của các bộ phận, lập phiếu mua, quản danh mục nhà cung cấp và "
            "bảng giá. KHÔNG duyệt phiếu mua của chính mình — ai đề xuất chi tiền thì không được "
            "là người đồng ý chi."
        ),
        "quyen": {
            "dashboard": _xem(SCOPE_ALL),
            "thu_mua": {
                "can_read": True, "can_create": True, "can_update": True,
                # Sửa số nhận · Mở lại đơn · Đóng đơn — việc sau khi hàng về, của chính bộ phận
                # mua hàng. KHÔNG phải quyền duyệt: ô đó nay nằm ở màn Đơn mua hàng (Kế toán).
                "can_manage_status": True,
                "scope": SCOPE_DEPARTMENT,
            },
            "nha_cung_cap": {
                "can_read": True, "can_create": True, "can_update": True,
                "can_toggle_active": True, "can_export": True, "scope": SCOPE_ALL,
            },
            "yeu_cau_mua_hang": {
                "can_read": True, "can_create": True, "can_update": True, "can_cancel": True,
                "scope": SCOPE_ALL,
            },
            "kho": {"can_read": True, "can_request": True, "scope": SCOPE_DEPARTMENT},
            "dm_giay_vat_tu": _xem(SCOPE_ALL),
        },
    },
]


def danh_sach_mau() -> list[dict]:
    """Trả bản sao của bảng mẫu (tránh người gọi sửa nhầm hằng dùng chung)."""
    return [
        {
            "key": m["key"],
            "label": m["label"],
            "mo_ta": m["mo_ta"],
            "quyen": {k: dict(v) for k, v in m["quyen"].items()},
        }
        for m in TEMPLATES
    ]
