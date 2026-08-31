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

    # `co_voucher` KHÔNG ở đây: "yêu cầu này đã có phiếu chưa" là câu hỏi của phía KHO, và bản duy
    # nhất nằm ở `StockRequestRepository.co_voucher` (ruling task-4-fix-1 minor-7). Trước đây hai
    # repo tự viết CÙNG một câu SELECT; một facade uỷ quyền cũng vẫn là hai cửa để hai bên trôi
    # khỏi nhau, nên bỏ hẳn — mọi chỗ gọi thẳng repo kho.
