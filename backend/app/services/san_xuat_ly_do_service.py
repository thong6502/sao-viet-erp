"""Lý do & lỗi SX — service: CRUD trên nền `CatalogService` + luật riêng.

Bảng `san_xuat_ly_do` là danh mục thứ 12 của Cấu hình danh mục (§15). Thân CRUD (canh trùng mã ·
ghi nhật ký CÙNG giao dịch · mã tự sinh `LD-####` · bật/tắt bằng `dat_active`) nằm ở
`services/catalog_base`; ở đây chỉ còn luật riêng:

* `nhom` PHẢI thuộc `NHOM_LY_DO` — ô chọn ở FE lọc theo cột này, một giá trị lạ là một dòng không
  bao giờ hiện ra ở bất kỳ ô chọn nào (lỗi câm).
* Xoá MỀM (`XOA_MEM`): batch/điều chỉnh bàn giao ghim `nhom_loi_id`/`ly_do_id` bằng ID THẬT
  (SET NULL khi mất) — ngừng dùng thì các bản ghi lịch sử vẫn tra ra được nhãn, không đẻ rác.
"""
from __future__ import annotations

from ..models.san_xuat_ly_do import NHOM_LY_DO
from ..repositories.san_xuat_ly_do_repo import SanXuatLyDoRepository
from .catalog_base import (
    CatalogDuplicate, CatalogError, CatalogNotFound, CatalogService, CatalogValidationError,
)


class SanXuatLyDoError(CatalogError):
    pass


class SanXuatLyDoValidationError(SanXuatLyDoError, CatalogValidationError):
    pass


class SanXuatLyDoDuplicate(SanXuatLyDoError, CatalogDuplicate):
    pass


class SanXuatLyDoNotFound(SanXuatLyDoError, CatalogNotFound):
    pass


class SanXuatLyDoService(CatalogService):
    """`audit` có DEFAULT `None` để test dựng `SanXuatLyDoService(repo)` trần."""

    LOAI = "san_xuat_ly_do"
    E_NOT_FOUND = SanXuatLyDoNotFound
    E_DUPLICATE = SanXuatLyDoDuplicate
    E_VALIDATION = SanXuatLyDoValidationError
    MSG_NOT_FOUND = "Không tìm thấy lý do/lỗi."
    MSG_DUPLICATE = "Mã lý do/lỗi đã tồn tại."
    # Mã do máy cấp (`LD-####`): màn không có ô Mã lúc tạo. Mã truyền tay qua API mà trùng một dòng
    # ĐÃ ngừng dùng thì tái dùng đúng dòng đó — xem `CatalogService.MA_TU_SINH`.
    MA_TU_SINH = True
    # Ngừng dùng chứ không xoá hàng: batch/điều chỉnh giữ FK về nhãn lịch sử.
    XOA_MEM = True

    def __init__(self, repo: SanXuatLyDoRepository, audit=None) -> None:
        super().__init__(repo, audit)

    # -- luật riêng ---------------------------------------------------------------------

    def _chuan_hoa(self, data: dict) -> dict:
        data = dict(data)
        if "nhom" in data:
            data["nhom"] = str(data.get("nhom") or "").strip()
        if "ten" in data and data.get("ten") is not None:
            data["ten"] = str(data["ten"]).strip()
        return data

    def _validate(self, data: dict, obj=None) -> None:
        # Nhóm là BẮT BUỘC khi tạo và không được đổi sang giá trị lạ khi sửa: ô chọn ở FE lọc theo
        # `nhom`, một giá trị ngoài `NHOM_LY_DO` là dòng không hiện ở bất cứ ô nào.
        if "nhom" in data or obj is None:
            nhom = (data.get("nhom") or "").strip()
            if not nhom:
                raise SanXuatLyDoValidationError("Chưa chọn nhóm cho lý do/lỗi.")
            if nhom not in NHOM_LY_DO:
                raise SanXuatLyDoValidationError(f"Nhóm không hợp lệ: {nhom}.")
        if obj is None or "ten" in data:
            if not (data.get("ten") or "").strip():
                raise SanXuatLyDoValidationError("Tên lý do/lỗi không được trống.")
