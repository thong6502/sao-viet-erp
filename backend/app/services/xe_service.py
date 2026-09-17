"""Danh mục Xe giao hàng — service CRUD.

Thân CRUD dùng chung ở `services/catalog_base.CatalogService`; ở đây chỉ còn luật riêng.
MỨC khoán km KHÔNG ở file này — nó là cấu hình LƯƠNG, nằm trong `DeliveryService`.
"""
from __future__ import annotations

from ..repositories.xe_repo import XeRepository
from .catalog_base import (
    CatalogDuplicate, CatalogError, CatalogNotFound, CatalogService, CatalogValidationError,
)


class XeError(CatalogError):
    pass


class XeValidationError(XeError, CatalogValidationError):
    pass


class XeDuplicate(XeError, CatalogDuplicate):
    pass


class XeNotFound(XeError, CatalogNotFound):
    pass


class XeService(CatalogService):
    LOAI = "xe"
    E_NOT_FOUND, E_DUPLICATE, E_VALIDATION = XeNotFound, XeDuplicate, XeValidationError
    MSG_NOT_FOUND = "Không tìm thấy xe."
    MSG_DUPLICATE = "Biển số đã tồn tại."

    def __init__(self, repo: XeRepository, audit=None, muc=None) -> None:
        super().__init__(repo, audit)
        # REPO mức — chỉ để kiểm "mức có thật không" lúc gán xe. Tuỳ chọn để test dựng service
        # gọn vẫn chạy; thiếu nó thì bỏ qua bước kiểm chứ không chặn oan.
        self.muc = muc

    def _validate(self, data: dict, obj=None) -> None:
        if not (data.get("ma") or "").strip():
            raise XeValidationError("Biển số không được trống.")
        if not (data.get("ten") or "").strip():
            raise XeValidationError("Tên xe không được trống.")
        tt = data.get("tai_trong")
        # Để TRỐNG được (xe mượn, chưa rõ giấy tờ), nhưng đã khai thì phải dương — tải trọng 0 hay
        # âm không nói lên điều gì, mà đó là số người ta nhìn để chọn xe cho đơn nặng.
        if tt is not None and float(tt) <= 0:
            raise XeValidationError("Tải trọng phải lớn hơn 0 (hoặc để trống).")
        # Mức BẮT BUỘC (chủ chốt 14/09/2026). Trước đó để trống được và xe trống âm thầm ăn đơn giá
        # phẳng `departments.don_gia_km` (3.600đ/km trên dev) mà không màn nào hiện số đó.
        # Sửa mà KHÔNG gửi ô mức (sửa một phần) thì xét mức ĐANG CÓ của xe — không gửi ≠ gỡ.
        muc_id = (data["muc_khoan_km_id"] if "muc_khoan_km_id" in data
                  else getattr(obj, "muc_khoan_km_id", None))
        if not muc_id:
            raise XeValidationError("Phải chọn mức khoán km cho xe (giá km của xe tra theo mức).")
        if self.muc is not None and self.muc.get(int(muc_id)) is None:
            raise XeValidationError("Mức khoán km không tồn tại.")
