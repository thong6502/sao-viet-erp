"""Repository Lệnh sản xuất (LSX) — mọi truy vấn DB của module Kế hoạch SX nằm ở đây.

Hàng chờ = đơn đã CHỐT + Sale đã bấm "Chuyển xuống sản xuất" (`orders.san_xuat_released_at`) và
còn dòng chưa lên lệnh. Không có cột trạng thái "đã tiếp nhận" — đơn tự rời hàng chờ khi mọi dòng
đã có LSX.
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models.lsx import LOAI_MOI, Lsx, LsxCongDoan, LsxCongDoanPhuThuoc
from ..models.order import STATUS_ORDERED, Order, OrderLine


class LsxRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads ---------------------------------------------------------------

    def get(self, lsx_id: int) -> Lsx | None:
        return self.db.execute(
            select(Lsx).where(Lsx.id == lsx_id).options(
                selectinload(Lsx.cong_doans).selectinload(LsxCongDoan.vat_tus),
                selectinload(Lsx.cong_doans).selectinload(LsxCongDoan.phu_thuoc),
            )
        ).scalar_one_or_none()

    def list(
        self,
        *,
        order_id: int | None = None,
        trang_thai: str | None = None,
        q: str | None = None,
        owner_ids: set[int] | None = None,
    ) -> list[Lsx]:
        stmt = select(Lsx).options(selectinload(Lsx.cong_doans))
        if order_id is not None:
            stmt = stmt.where(Lsx.order_id == order_id)
        if trang_thai:
            stmt = stmt.where(Lsx.trang_thai == trang_thai)
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(Lsx.ma.ilike(like), Lsx.ten.ilike(like)))
        if owner_ids is not None:
            stmt = stmt.where(
                or_(Lsx.nguoi_phu_trach_id.in_(owner_ids), Lsx.created_by.in_(owner_ids))
            )
        return list(self.db.execute(stmt.order_by(Lsx.created_at.desc())).scalars())

    def by_order_lines(self, order_line_ids: list[int]) -> dict[int, Lsx]:
        """order_line_id → LSX 'sản xuất mới' đã tạo (nguồn của guard chống sinh trùng)."""
        if not order_line_ids:
            return {}
        rows = self.db.execute(
            select(Lsx).where(
                Lsx.order_line_id.in_(order_line_ids), Lsx.loai == LOAI_MOI
            )
        ).scalars()
        return {r.order_line_id: r for r in rows}

    def orders_ban_giao(self) -> list[Order]:
        """Đơn đã chốt + đã chuyển xuống sản xuất (kèm dòng đơn), mới nhất trước."""
        return list(
            self.db.execute(
                select(Order)
                .where(
                    Order.status == STATUS_ORDERED,
                    Order.san_xuat_released_at.is_not(None),
                )
                .options(selectinload(Order.lines))
                .order_by(Order.san_xuat_released_at.desc())
            ).scalars()
        )

    def count_by_order(self, order_ids: list[int]) -> dict[int, int]:
        """order_id → số LSX đã tạo (để biết đơn còn nợ lệnh hay không)."""
        if not order_ids:
            return {}
        rows = self.db.execute(
            select(Lsx.order_id, func.count())
            .where(Lsx.order_id.in_(order_ids))
            .group_by(Lsx.order_id)
        ).all()
        return {oid: n for oid, n in rows}

    def order_with_lines(self, order_id: int) -> Order | None:
        return self.db.execute(
            select(Order).where(Order.id == order_id).options(selectinload(Order.lines))
        ).scalar_one_or_none()

    def order_lines(self, order_id: int) -> list[OrderLine]:
        return list(
            self.db.execute(
                select(OrderLine).where(OrderLine.order_id == order_id).order_by(OrderLine.id)
            ).scalars()
        )

    # --- writes --------------------------------------------------------------

    def add(self, lsx: Lsx) -> Lsx:
        self.db.add(lsx)
        self.db.flush()
        return lsx

    def delete(self, lsx: Lsx) -> None:
        self.db.delete(lsx)
        self.db.flush()

    def sync_cong_doans(self, lsx: Lsx, rows: list[LsxCongDoan]) -> None:
        """Đồng bộ tại chỗ để giữ PK bước cho dòng lịch và cạnh phụ thuộc."""
        keep = {r.id for r in rows if r.id is not None}
        for old in list(lsx.cong_doans):
            if old.id not in keep:
                lsx.cong_doans.remove(old)
        for i, row in enumerate(rows):
            row.thu_tu = i
            if row not in lsx.cong_doans:
                lsx.cong_doans.append(row)
        self.db.flush()

    def phu_thuoc_toi_buoc(self, step_ids: set[int]) -> list[LsxCongDoanPhuThuoc]:
        if not step_ids:
            return []
        return list(self.db.execute(
            select(LsxCongDoanPhuThuoc).where(LsxCongDoanPhuThuoc.buoc_truoc_id.in_(step_ids))
        ).scalars())

    def commit(self) -> None:
        self.db.commit()
