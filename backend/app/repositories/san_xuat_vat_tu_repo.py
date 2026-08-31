"""Truy vấn cho đề nghị cấp vật tư theo công đoạn."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models.san_xuat_vat_tu import SanXuatVatTuDeNghi


class SanXuatVatTuRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def de_nghi(self, de_nghi_id: int) -> SanXuatVatTuDeNghi | None:
        return self.db.scalars(
            select(SanXuatVatTuDeNghi)
            .options(selectinload(SanXuatVatTuDeNghi.dongs))
            .where(SanXuatVatTuDeNghi.id == de_nghi_id)
        ).first()

    def cac_de_nghi(self, cong_viec_id: int) -> list[SanXuatVatTuDeNghi]:
        return list(self.db.scalars(
            select(SanXuatVatTuDeNghi)
            .options(selectinload(SanXuatVatTuDeNghi.dongs))
            .where(SanXuatVatTuDeNghi.cong_viec_id == cong_viec_id)
            .order_by(SanXuatVatTuDeNghi.lan_so)
        ))

    def lan_ke_tiep(self, cong_viec_id: int) -> int:
        cao = self.db.scalar(
            select(func.max(SanXuatVatTuDeNghi.lan_so))
            .where(SanXuatVatTuDeNghi.cong_viec_id == cong_viec_id)
        )
        return int(cao or 0) + 1

    def co_voucher(self, stock_request_id: int | None) -> bool:
        """Uỷ quyền cho `StockRequestRepository.co_voucher` (ruling task-4-fix-1 minor-7): trước
        đây hai repo tự viết CÙNG một câu SELECT — giữ method này lại chỉ để không phá cửa gọi
        thẳng qua `SanXuatVatTuRepository` đang có (kể cả trong test), nhưng chỉ còn ĐÚNG MỘT
        truy vấn thật, nằm ở repo yêu cầu kho.
        """
        from .stock_request_repo import StockRequestRepository

        return StockRequestRepository(self.db).co_voucher(stock_request_id)
