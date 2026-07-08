"""Loại sản phẩm — service: CRUD + validate (§5) + helper tương thích layout (§5.1)."""
from __future__ import annotations

from ..models.loai_san_pham import (
    BOX_SUB_TYPE, COVER_TYPE, STRUCT_LAYOUT_MATRIX, STRUCTURAL_TYPE, VAT_RATE, LoaiSanPham,
)
from ..repositories.loai_san_pham_repo import LoaiSanPhamRepository


class LoaiSanPhamError(Exception):
    pass


class LoaiSanPhamValidationError(LoaiSanPhamError):
    pass


class LoaiSanPhamDuplicate(LoaiSanPhamError):
    pass


class LoaiSanPhamNotFound(LoaiSanPhamError):
    pass


def is_layout_compatible(structural_type: str, layout_mode: str) -> bool:
    """§5.1 ma trận tương thích (KHÔNG equality). Engine gọi khi gán/dùng rule."""
    return layout_mode in STRUCT_LAYOUT_MATRIX.get(structural_type, ())


class LoaiSanPhamService:
    def __init__(self, repo: LoaiSanPhamRepository) -> None:
        self.repo = repo

    def _validate(self, data: dict) -> None:
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
        if int(data.get("vat_rate", 8)) not in VAT_RATE:
            raise LoaiSanPhamValidationError("vat_rate phải 5/8/10.")
        # imposition_rule_id: §2 nói bắt buộc; ở MVP cho phép NULL (gán sau khi Bình bài land)
        # để không hard-block, nhưng cảnh báo ở engine nếu thiếu khi báo giá.

    def get(self, sp_id: int) -> LoaiSanPham:
        sp = self.repo.get(sp_id)
        if sp is None:
            raise LoaiSanPhamNotFound("Không tìm thấy loại sản phẩm.")
        return sp

    def list(self, **kw):
        return self.repo.list(**kw)

    def create(self, data: dict) -> LoaiSanPham:
        self._validate(data)
        if self.repo.find_by_ma(data["ma"]) is not None:
            raise LoaiSanPhamDuplicate("Mã loại sản phẩm đã tồn tại.")
        return self.repo.create(data)

    def update(self, sp_id: int, data: dict) -> LoaiSanPham:
        sp = self.get(sp_id)
        self._validate(data)
        dup = self.repo.find_by_ma(data["ma"])
        if dup is not None and dup.id != sp.id:
            raise LoaiSanPhamDuplicate("Mã loại sản phẩm đã tồn tại.")
        return self.repo.update(sp, data)

    def delete(self, sp_id: int) -> None:
        self.repo.delete(self.get(sp_id))
