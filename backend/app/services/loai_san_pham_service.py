"""Loại sản phẩm — service: CRUD + validate (§5) + helper tương thích layout (§5.1).

Thân CRUD dùng chung ở `services/catalog_base.CatalogService`; ở đây chỉ còn luật riêng.
"""
from __future__ import annotations

from ..models.loai_san_pham import (
    BOX_SUB_TYPE, COVER_TYPE, STRUCT_LAYOUT_MATRIX, STRUCTURAL_TYPE,
)
from ..repositories.loai_san_pham_repo import LoaiSanPhamRepository
from .catalog_base import (
    CatalogDuplicate, CatalogError, CatalogNotFound, CatalogService, CatalogValidationError,
)


class LoaiSanPhamError(CatalogError):
    pass


class LoaiSanPhamValidationError(LoaiSanPhamError, CatalogValidationError):
    pass


class LoaiSanPhamDuplicate(LoaiSanPhamError, CatalogDuplicate):
    pass


class LoaiSanPhamNotFound(LoaiSanPhamError, CatalogNotFound):
    pass


def is_layout_compatible(structural_type: str, layout_mode: str) -> bool:
    """§5.1 ma trận tương thích (KHÔNG equality). Engine gọi khi gán/dùng rule."""
    return layout_mode in STRUCT_LAYOUT_MATRIX.get(structural_type, ())


class LoaiSanPhamService(CatalogService):
    """`audit` có DEFAULT `None`: 8 test hiện có dựng service bằng `LoaiSanPhamService(repo)`,
    thêm tham số bắt buộc là gãy hết mà chẳng được gì.

    Ghi NHẬT KÝ như 6 danh mục còn lại. Trước 15/08/2026 service này không nhận `audit` nên không
    ghi dòng nào — trong khi `routers/nhat_ky_danh_muc.LOAI_MODULE` đã map sẵn `loai_san_pham`,
    tức tab "Nhật ký" của màn này mở ra LUÔN RỖNG và không ai biết vì sao.
    """

    LOAI = "loai_san_pham"
    E_NOT_FOUND = LoaiSanPhamNotFound
    E_DUPLICATE = LoaiSanPhamDuplicate
    E_VALIDATION = LoaiSanPhamValidationError
    MSG_NOT_FOUND = "Không tìm thấy loại sản phẩm."
    MSG_DUPLICATE = "Mã loại sản phẩm đã tồn tại."

    def __init__(self, repo: LoaiSanPhamRepository, audit=None) -> None:
        super().__init__(repo, audit)

    def _validate(self, data: dict, obj=None) -> None:
        if not (data.get("ma") or "").strip():
            raise LoaiSanPhamValidationError("Mã loại sản phẩm không được trống.")
        if not (data.get("ten") or "").strip():
            raise LoaiSanPhamValidationError("Tên loại sản phẩm không được trống.")
        st = data.get("structural_type")
        if st not in STRUCTURAL_TYPE:
            raise LoaiSanPhamValidationError("structural_type không hợp lệ.")
        if st == "box" and data.get("box_sub_type") not in BOX_SUB_TYPE:
            raise LoaiSanPhamValidationError("Hộp cần box_sub_type (folding_carton/corrugated/rigid).")
        if data.get("has_cover") and data.get("cover_type") not in COVER_TYPE:
            raise LoaiSanPhamValidationError("Có bìa cần cover_type (tự bìa / bìa rời). [E-SP-COVER]")
        # imposition_rule_id: §2 nói bắt buộc; ở MVP cho phép NULL (gán sau khi Bình bài land)
        # để không hard-block, nhưng cảnh báo ở engine nếu thiếu khi báo giá.
