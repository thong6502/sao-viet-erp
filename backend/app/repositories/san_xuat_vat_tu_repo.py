"""Truy vấn cho đề nghị cấp vật tư theo công đoạn."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models.san_xuat_vat_tu import SanXuatVatTuDeNghi, SanXuatVatTuDeNghiDong
from ..models.stock_voucher import StockVoucher


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
        """Yêu cầu kho đã có BẤT KỲ phiếu nào chưa — kể cả nháp, kể cả đã huỷ.

        Không lọc trạng thái phiếu: kho đã bắt tay soạn (dù nháp) thì con số đã đi vào đầu người
        soạn; sửa sau lưng họ là nguồn đẻ ra chênh lệch mà không ai truy được.
        """
        if not stock_request_id:
            return False
        return self.db.scalar(
            select(func.count()).select_from(StockVoucher)
            .where(StockVoucher.request_id == stock_request_id)
        ) > 0
