"""MỘT NGUỒN cho danh sách 11 màn "Cấu hình danh mục".

Vì sao có file này: cùng một danh sách 11 màn đang bị CHÉP TAY ở nhiều nơi, mỗi nơi một hình
dạng và không nơi nào biết nơi kia — seed quyền, `SCOPELESS_MODULES`, bảng loại→module của nhật
ký, bảng loại→model của luồng xoá (và bên FE là menu + ma trận quyền). Thêm một màn danh mục là
phải nhớ sửa đủ sáu chỗ; quên một chỗ thì hỏng IM LẶNG: màn hiện ra nhưng không có ô quyền, hoặc
có ô quyền mà nhật ký trả 404.

File này KHÔNG phải schema, KHÔNG đụng DB. Nó chỉ là bảng khai tĩnh: mỗi màn một dòng, các nơi
kia đọc về thay vì tự khai lại.

⚠️ `module` là DỮ LIỆU SỐNG — nó nằm trong cột `role_permissions.module_key` của DB thật. Đổi một
chuỗi ở đây là làm mồ côi quyền đã cấp, phải có migration `UPDATE` đi kèm. Đặc biệt `khuon_be`
KHÔNG được "cho nhất quán" thành `dm_khuon_be`.

Phạm vi: CHỈ danh mục. Module không phải danh mục (`nhan_su`, `nghi_phep`, `ky_thuat_may`…) vẫn
khai ở chỗ cũ của chúng — nhét vào đây thì cái tên "catalog registry" hết nghĩa và nơi đọc lại
phải lọc ra.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module


@dataclass(frozen=True)
class DanhMuc:
    """Một màn Cấu hình danh mục, nhìn từ đủ bốn phía đang cần nó."""

    #: khoá loại bản ghi — đúng chuỗi service ghi vào `audit_logs.target` ("{loai}:{id}").
    loai: str
    #: khoá quyền RBAC (`role_permissions.module_key`). DỮ LIỆU SỐNG — xem cảnh báo đầu file.
    module: str
    #: nhãn tiếng Việt, dùng chung cho menu · ma trận quyền · nhãn module lúc seed.
    nhan: str
    #: id mục menu ở FE (`Sidebar.tsx` và khoá cấu hình màn trong `rebuildCatalogConfigs.tsx`).
    path: str
    #: tên `loai` ĐỜI CŨ còn nằm trong `audit_logs` (hoặc bảng phụ đi ké ô quyền của màn này).
    #: Phải tra ra đúng module thì lịch sử cũ mới còn đọc được.
    alias_loai: tuple[str, ...] = ()
    #: "models.bu_hao:BuHao" — để CHUỖI chứ không phải lớp, vì import lớp ở đây là kéo cả cây
    #: model vào mọi nơi chỉ cần biết tên màn. `None` = màn chưa có bộ đếm "còn ai dùng không".
    model: str | None = None


# Thứ tự = thứ tự menu "Cấu hình danh mục". Người cấp quyền dò theo MÀN HÌNH chứ không dò theo
# tên kỹ thuật, nên mọi nơi đọc về đều giữ nguyên thứ tự này.
DANH_MUC: tuple[DanhMuc, ...] = (
    DanhMuc("loai_san_pham", "dm_loai_san_pham", "Loại sản phẩm", "loai-san-pham",
            alias_loai=("product_type",), model="models.loai_san_pham:LoaiSanPham"),
    DanhMuc("may_thiet_bi", "dm_thiet_bi", "Thiết bị & Máy móc", "may-thiet-bi",
            alias_loai=("machine",), model="models.may_thiet_bi:MayThietBi"),
    DanhMuc("cong_doan", "dm_cong_doan", "Công đoạn", "cong-doan",
            alias_loai=("operation",), model="models.cong_doan:CongDoan"),
    # Đơn giá khoán theo tổ. Đứng ngay sau Công đoạn vì đó là chỗ nó được dùng (ô "Định mức đầu
    # việc" của bước). Trước 17/08/2026 khai ở một tab của màn Lương — bảng `piece_rates` giữ
    # nguyên tên, chỉ đổi CHỖ KHAI và ba tên cột mà nền danh mục đọc (mg `0210`).
    DanhMuc("cong_viec_khoan", "dm_cong_viec_khoan", "Công việc khoán", "cong-viec-khoan",
            model="models.piece_work:PieceRate"),
    DanhMuc("bu_hao", "dm_bu_hao", "Bù hao", "bu-hao", model="models.bu_hao:BuHao"),
    # `don_vi_quy_doi` là BẢNG RIÊNG, đánh số riêng — nhưng nằm trong drawer của màn Đơn vị nên
    # ăn chung ô quyền, vì thế đứng ở `alias_loai` chứ không thành một dòng riêng.
    DanhMuc("don_vi_do", "dm_don_vi", "Đơn vị & quy đổi", "don-vi",
            alias_loai=("don_vi_quy_doi",), model="models.don_vi_do:DonViDo"),
    DanhMuc("chung_loai_giay", "dm_chung_loai_giay", "Chủng loại giấy", "chung-loai-giay",
            model="models.vat_lieu_kho:ChungLoaiGiay"),
    DanhMuc("giay", "dm_giay", "Giấy", "giay", model="models.vat_lieu_kho:GiayNguyen"),
    DanhMuc("vat_tu", "dm_vat_tu", "Vật tư khác", "vat-tu-in-an",
            model="models.vat_lieu_kho:VatTuInAn"),
    # Thành phẩm CHUNG BẢNG với Vật tư khác (`vat_tu_in_an`), chia nhau bằng `customer_id` —
    # xem docs/prd-thanh-pham.md §3. Bảng riêng thì kho phải học `hang_loai` thứ ba, mà cột đó
    # nằm trong stock_lots · stock_vouchers · stock_requests · purchase.
    #
    # `model=None` là CỐ Ý: bộ đếm "còn ai dùng không" mà trỏ vào VatTuInAn thì nó đếm cả vật tư
    # thường, trả ra con số sai cho cả hai màn. Không có bộ đếm còn hơn có bộ đếm nói dối.
    DanhMuc("thanh_pham", "dm_thanh_pham", "Thành phẩm", "thanh-pham"),
    # `khuon_be` KHÔNG có tiền tố `dm_` — chuỗi này đã cấp quyền trong DB thật, đổi cần migration.
    DanhMuc("khuon_be", "khuon_be", "Khuôn bế", "khuon-be", model="models.khuon_be:KhuonBe"),
    DanhMuc("kho_hang", "dm_kho_hang", "Khai báo kho", "khai-bao-kho"),
    # Lý do & lỗi sản xuất (§15 spec-thuc-hien-san-xuat): danh mục CHUẨN HOÁ dùng chung cho hỏng
    # batch, lỗi KCS và các lý do vận hành (tạm dừng · bắt đầu trễ · điều chỉnh bàn giao…). Gộp vào
    # Cấu hình danh mục thay vì hard-code danh sách lý do ở FE. Module RIÊNG `dm_ly_do_san_xuat`
    # (mg `0221` chép quyền từ `san_xuat`); `model=None` như `kho_hang` — luồng xoá dùng chặn mềm
    # ở service, không cần bộ đếm nơi-dùng.
    DanhMuc("san_xuat_ly_do", "dm_ly_do_san_xuat", "Lý do & lỗi SX", "ly-do-san-xuat"),
)

#: 11 khoá quyền của nhóm danh mục, đúng thứ tự menu.
MODULE_KEYS: tuple[str, ...] = tuple(d.module for d in DANH_MUC)

#: (key, nhãn) để seed bảng module quyền — cùng hình dạng với `seed.MODULES`.
MODULES_SEED: list[tuple[str, str]] = [(d.module, d.nhan) for d in DANH_MUC]

_THEO_LOAI: dict[str, DanhMuc] = {d.loai: d for d in DANH_MUC}
# Alias khai TRƯỚC rồi để tên chính đè lên: tên chính luôn thắng nếu có ai lỡ khai trùng.
_THEO_LOAI_KE_ALIAS: dict[str, DanhMuc] = {
    **{a: d for d in DANH_MUC for a in d.alias_loai},
    **_THEO_LOAI,
}

#: loại bản ghi (kể cả tên đời cũ) → module quyền. 15 khoá cho 11 màn.
MODULE_THEO_LOAI: dict[str, str] = {k: d.module for k, d in _THEO_LOAI_KE_ALIAS.items()}


def theo_loai(loai: str, *, ke_alias: bool = False) -> DanhMuc | None:
    """Tra một dòng đăng ký theo `loai`.

    Mặc định CHỈ nhận tên chính. `ke_alias=True` mới nhận thêm tên đời cũ — dùng cho câu hỏi
    "màn nào chứa bản ghi này" (nhật ký), KHÔNG dùng cho câu hỏi "bản ghi này ở bảng nào":
    tên đời cũ không có bảng riêng, trả model theo alias là mở thêm đường vào bằng tên lạ.
    """
    return (_THEO_LOAI_KE_ALIAS if ke_alias else _THEO_LOAI).get(loai)


def module_cua(loai: str) -> str | None:
    """`loai` (tên chính hoặc tên đời cũ) → khoá quyền của màn chứa nó."""
    return MODULE_THEO_LOAI.get(loai)


def lop_model_cua(loai: str):
    """`loai` → lớp SQLAlchemy, hoặc None nếu màn chưa khai model.

    Import ĐỘNG ngay tại đây (không phải ở đầu file) để `catalog_registry` giữ được tính chất
    "bảng khai tĩnh, không kéo theo gì": các nơi chỉ cần tên/nhãn/quyền vẫn import rẻ như cũ.
    """
    dm = theo_loai(loai)
    if dm is None or dm.model is None:
        return None
    duong_dan, ten_lop = dm.model.split(":")
    return getattr(import_module(f".{duong_dan}", __package__), ten_lop)


def dang_ky_json() -> list[dict]:
    """Bảng đăng ký ở dạng JSON cho FE — chỉ những trường FE thật sự dùng để dựng menu + ma trận."""
    return [{"loai": d.loai, "module": d.module, "nhan": d.nhan, "path": d.path} for d in DANH_MUC]
