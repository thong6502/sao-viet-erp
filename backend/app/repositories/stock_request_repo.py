"""Repository — phiếu đề nghị nhập/xuất kho."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session, selectinload

from ..models.stock_request import StockRequest, StockRequestLine

_VN_TZ = timezone(timedelta(hours=7))
_PREFIX = {"nhap": "DNN", "xuat": "DNX"}  # Đề Nghị Nhập / Đề Nghị Xuất


class StockRequestRepo:
    def __init__(self, db: Session) -> None:
        self.db = db

    def next_code(self, request_type: str) -> str:
        """Mã đề nghị theo loại + năm: DNN-25-0001 (nhập) / DNX-25-0001 (xuất)."""
        yy = datetime.now(_VN_TZ).strftime("%y")
        prefix = f"{_PREFIX.get(request_type, 'DN')}-{yy}-"
        max_n = 0
        for code in self.db.execute(
            select(StockRequest.code).where(StockRequest.code.like(f"{prefix}%"))
        ).scalars():
            try:
                max_n = max(max_n, int(code[len(prefix):]))
            except ValueError:
                continue
        return f"{prefix}{max_n + 1:04d}"

    def get(self, request_id: int) -> StockRequest | None:
        return self.db.execute(
            select(StockRequest).options(selectinload(StockRequest.lines))
            .where(StockRequest.id == request_id)
        ).scalars().first()

    def list(
        self, *, request_type=None, status=None, warehouse_id=None,
        sort="-created_at", page=1, size=50,
    ) -> tuple[list[StockRequest], int]:
        conds = []
        if request_type:
            conds.append(StockRequest.request_type == request_type)
        if status:
            conds.append(StockRequest.status == status)
        if warehouse_id:
            conds.append(StockRequest.warehouse_id == warehouse_id)
        base = select(StockRequest).options(selectinload(StockRequest.lines))
        count_stmt = select(func.count()).select_from(StockRequest)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        direction = desc if sort.startswith("-") else asc
        base = base.order_by(direction(StockRequest.created_at), StockRequest.id.desc())
        page, size = max(1, page), max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def create(self, *, code: str, header: dict, lines: list[dict]) -> StockRequest:
        r = StockRequest(code=code, **header)
        for ln in lines:
            r.lines.append(StockRequestLine(**ln))
        self.db.add(r)
        self.db.commit()
        self.db.refresh(r)
        return r

    def replace_lines(self, request: StockRequest, lines: list[dict]) -> None:
        request.lines.clear()
        self.db.flush()
        for ln in lines:
            request.lines.append(StockRequestLine(**ln))
        self.db.commit()

    def save(self, request: StockRequest) -> StockRequest:
        self.db.commit()
        self.db.refresh(request)
        return request
