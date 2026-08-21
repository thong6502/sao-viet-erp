"""Danh mục Khuôn bế — service CRUD (chỉ khai báo, validate nhẹ).

Thân CRUD dùng chung ở `services/catalog_base.CatalogService`; ở đây chỉ còn luật riêng.
"""
from __future__ import annotations

from ..models.khuon_be import LOAI_KHUON, TINH_TRANG
from ..repositories.khuon_be_repo import KhuonBeRepository
from .catalog_base import (
    CatalogDuplicate, CatalogError, CatalogNotFound, CatalogService, CatalogValidationError,
)


class KhuonBeError(CatalogError):
    pass


class KhuonBeValidationError(KhuonBeError, CatalogValidationError):
    pass


class KhuonBeDuplicate(KhuonBeError, CatalogDuplicate):
    pass


class KhuonBeNotFound(KhuonBeError, CatalogNotFound):
    pass


class KhuonBeService(CatalogService):
    LOAI = "khuon_be"
    E_NOT_FOUND = KhuonBeNotFound
    E_DUPLICATE = KhuonBeDuplicate
    E_VALIDATION = KhuonBeValidationError
    MSG_NOT_FOUND = "Không tìm thấy khuôn bế."
    MSG_DUPLICATE = "Mã khuôn đã tồn tại."
    MA_TU_SINH = True      # UI không cho gõ mã tay → server cấp KB-####

    def __init__(self, repo: KhuonBeRepository, audit=None) -> None:
        super().__init__(repo, audit)

    def _validate(self, data: dict, obj=None) -> None:
        if not (data.get("ten") or "").strip():
            raise KhuonBeValidationError("Tên khuôn không được trống.")
        tt = data.get("tinh_trang")
        if tt is not None and tt not in TINH_TRANG:
            raise KhuonBeValidationError("Tình trạng khuôn không hợp lệ.")
        loai = data.get("loai")
        if loai and loai not in LOAI_KHUON:
            raise KhuonBeValidationError("Loại khuôn không hợp lệ.")
        # `dang_dat_lam` = dao chưa có trong tay (thuê ngoài chưa về, hoặc xưởng đang tự làm).
        # Không khai ngày thì bước dùng dao ở lệnh sản xuất chỉ hiện "đang làm" trống trơn — người
        # xếp việc không biết chờ tới bao giờ, mà đó đúng là câu duy nhất họ cần.
        if tt == "dang_dat_lam" and not data.get("ngay_ve_du_kien"):
            raise KhuonBeValidationError(
                "Khuôn đang đặt làm phải khai NGÀY CÓ KHUÔN (dự kiến) — bước dùng khuôn ở lệnh "
                "sản xuất hiện ngày này để biết chờ tới bao giờ."
            )

    def dem_theo_tinh_trang(self, **kw) -> dict[str, int]:
        """Số khuôn theo tình trạng — cho tab lọc của màn Khuôn bế (xem repo)."""
        return self.repo.dem_theo_tinh_trang(**kw)
