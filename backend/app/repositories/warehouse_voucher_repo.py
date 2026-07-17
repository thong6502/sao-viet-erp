"""Repository — phiếu kho (cỗ máy chứng từ, spec-13)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session, selectinload

from ..models.warehouse_voucher import StockVoucher, StockVoucherLine

_VN_TZ = timezone(timedelta(hours=7))
_SORT = {"code": StockVoucher.code, "created_at": StockVoucher.created_at}


class VoucherRepo:
    def __init__(self, db: Session) -> None:
        self.db = db

    def next_code(self, voucher_type_code: str) -> str:
        """Mã phiếu theo loại + năm: {LOAI}-{YY}-{NNNN} (DacTa VD NK-NVL-25-0001)."""
        yy = datetime.now(_VN_TZ).strftime("%y")
        prefix = f"{voucher_type_code}-{yy}-"
        max_n = 0
        for code in self.db.execute(
            select(StockVoucher.code).where(StockVoucher.code.like(f"{prefix}%"))
        ).scalars():
            try:
                max_n = max(max_n, int(code[len(prefix):]))
            except ValueError:
                continue
        return f"{prefix}{max_n + 1:04d}"

    def get(self, voucher_id: int) -> StockVoucher | None:
        return self.db.execute(
            select(StockVoucher).options(selectinload(StockVoucher.lines))
            .where(StockVoucher.id == voucher_id)
        ).scalars().first()

    def list(
        self, *, voucher_type_id=None, status=None, warehouse_id=None,
        partner_ref=None, created_by_user_id=None, ref_type=None, ref_id=None,
        sort="-created_at", page=1, size=50,
    ) -> tuple[list[StockVoucher], int]:
        conds = []
        if voucher_type_id:
            conds.append(StockVoucher.voucher_type_id == voucher_type_id)
        if status:
            conds.append(StockVoucher.status == status)
        if warehouse_id:
            conds.append(
                (StockVoucher.src_warehouse_id == warehouse_id)
                | (StockVoucher.dst_warehouse_id == warehouse_id)
            )
        if partner_ref:
            conds.append(func.lower(StockVoucher.partner_ref).like(f"%{partner_ref.strip().lower()}%"))
        if created_by_user_id:
            conds.append(StockVoucher.created_by_user_id == created_by_user_id)
        # Truy vết theo chứng từ gốc (VD mọi phiếu kho của 1 LSX): ref_type='lsx' + ref_id.
        if ref_type:
            conds.append(StockVoucher.ref_type == ref_type)
        if ref_id:
            conds.append(StockVoucher.ref_id == ref_id)
        base = select(StockVoucher).options(selectinload(StockVoucher.lines))
        count_stmt = select(func.count()).select_from(StockVoucher)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        direction, key = (desc, sort[1:]) if sort.startswith("-") else (asc, sort)
        base = base.order_by(direction(_SORT.get(key, StockVoucher.created_at)), StockVoucher.id.desc())
        page, size = max(1, page), max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def create(self, *, code: str, header: dict, lines: list[dict]) -> StockVoucher:
        v = StockVoucher(code=code, **header)
        for ln in lines:
            v.lines.append(StockVoucherLine(**ln))
        self.db.add(v)
        self.db.commit()
        self.db.refresh(v)
        return v

    def replace_lines(self, voucher: StockVoucher, lines: list[dict]) -> None:
        voucher.lines.clear()
        self.db.flush()
        for ln in lines:
            voucher.lines.append(StockVoucherLine(**ln))
        self.db.commit()

    def save(self, voucher: StockVoucher) -> StockVoucher:
        self.db.commit()
        self.db.refresh(voucher)
        return voucher
