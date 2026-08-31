"""Truy vấn cho đề nghị cấp vật tư theo công đoạn."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models.san_xuat import SanXuatCongViec
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

    def boi_canh_san_xuat(self, request_ids: list[int]) -> dict[int, dict]:
        """`{request_id: {"can_luc", "cong_viec_id", "cong_doan_ten"}}` — MỘT truy vấn join
        `san_xuat_vat_tu_de_nghi` → `san_xuat_cong_viec` cho cả danh sách.

        Hộp yêu cầu kho hiện HÀNG TRĂM dòng một trang; hỏi từng yêu cầu là N+1 ngay trên đường mở
        màn chính của thủ kho (task-8-ruling-man-kho, Ruling 32/34). Danh sách rỗng ⇒ trả `{}` mà
        không chạm DB. Yêu cầu kho THƯỜNG (không sinh từ sản xuất) đơn giản không có dòng nào khớp
        `stock_request_id` — router đọc `.get(id)` ra `None`, tự lấy `{}` mà không phải phân nhánh.
        """
        ids = [i for i in set(request_ids) if i]
        if not ids:
            return {}
        rows = self.db.execute(
            select(SanXuatVatTuDeNghi.stock_request_id, SanXuatVatTuDeNghi.can_luc,
                   SanXuatVatTuDeNghi.cong_viec_id, SanXuatCongViec.ten_cong_doan)
            .join(SanXuatCongViec, SanXuatCongViec.id == SanXuatVatTuDeNghi.cong_viec_id)
            .where(SanXuatVatTuDeNghi.stock_request_id.in_(ids))
        )
        return {
            rid: {"can_luc": can_luc, "cong_viec_id": cv_id, "cong_doan_ten": ten}
            for rid, can_luc, cv_id, ten in rows
        }

    # `co_voucher` KHÔNG ở đây: "yêu cầu này đã có phiếu chưa" là câu hỏi của phía KHO, và bản duy
    # nhất nằm ở `StockRequestRepository.co_voucher` (ruling task-4-fix-1 minor-7). Trước đây hai
    # repo tự viết CÙNG một câu SELECT; một facade uỷ quyền cũng vẫn là hai cửa để hai bên trôi
    # khỏi nhau, nên bỏ hẳn — mọi chỗ gọi thẳng repo kho.
