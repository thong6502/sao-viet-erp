"""Repository — GIÁ GỐC thành phẩm nhập từ KCS (design nhập kho thành phẩm §5).

Lô thành phẩm vào kho với giá gốc 0; kế toán kho gõ giá sau, một lần trên LÔ GỐC, hệ lan xuống mọi lô
sinh ra từ nó qua điều chuyển (`stock_lots.lo_goc_id`). Mọi truy vấn của việc đó nằm ở đây.
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.customer import Customer
from ..models.kho_hang import KhoHang
from ..models.lsx import Lsx
from ..models.order import Order
from ..models.stock_lot import StockLot
from ..models.stock_request import StockRequest, StockRequestLine
from ..models.stock_voucher import VOUCHER_NHAP, StockVoucher, StockVoucherLine
from ..models.vat_lieu_kho import VatTuInAn


class KhoGiaGocRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ho_lo(self, goc_id: int) -> list[StockLot]:
        """Lô gốc + mọi lô trỏ `lo_goc_id` về nó (ở bất kỳ kho nào), khoá dòng để hai người sửa cùng
        lúc không ghi đè nhau. Lô gốc đứng đầu."""
        rows = self.db.execute(
            select(StockLot)
            .where(or_(StockLot.id == goc_id, StockLot.lo_goc_id == goc_id))
            .order_by(StockLot.id)
            .with_for_update()
        ).scalars().all()
        return sorted(rows, key=lambda x: (x.id != goc_id, x.id))

    def dong_nhap_cua_lo(self, lot_ids) -> dict[int, StockVoucherLine]:
        """`{lot_id: dòng phiếu NHẬP đã đẻ ra lô}` — dòng phiếu xuất cũng trỏ `lot_id`, nên lọc NHẬP."""
        ids = {int(i) for i in lot_ids if i}
        if not ids:
            return {}
        return {
            int(ln.lot_id): ln
            for ln in self.db.execute(
                select(StockVoucherLine)
                .join(StockVoucher, StockVoucher.id == StockVoucherLine.voucher_id)
                .where(StockVoucherLine.lot_id.in_(ids), StockVoucher.loai == VOUCHER_NHAP)
            ).scalars()
        }

    def dvt_dong_yeu_cau(self, request_line_id: int) -> str | None:
        return self.db.execute(
            select(StockRequestLine.dvt).where(StockRequestLine.id == request_line_id)
        ).scalar_one_or_none()

    def gia_goc_theo_dong_yc(self, request_line_ids) -> dict[int, tuple[int | None, int | None]]:
        """`{dòng yêu cầu: (giá gốc theo đơn vị dòng, tiền gốc)}` đọc ở dòng phiếu NHẬP đã ghi sổ (đã
        đẻ lô) — chỗ kế toán kho gõ giá gốc (`sua_gia_goc`). Dòng yêu cầu thì giữ 0 mãi, đọc nó là không
        bao giờ thấy giá. Nhập nhiều đợt thì giá là bình quân theo số lượng (làm tròn đồng), còn tiền là
        Σ giá × SL từng đợt — nhân ngược giá bình quân đã làm tròn sẽ lệch tổng các phiếu. Còn MỘT lô
        giá 0 là cả dòng (None, None) — hiện con số lúc kế toán mới gõ được một nửa là đánh lừa người
        đọc. Chưa ghi sổ lô nào: không có khoá."""
        ids = {int(i) for i in request_line_ids if i}
        if not ids:
            return {}
        gom: dict[int, list[tuple[int, float]]] = {}
        for rl_id, gia, sl in self.db.execute(
            select(StockVoucherLine.request_line_id, StockVoucherLine.don_gia, StockVoucherLine.so_luong)
            .join(StockVoucher, StockVoucher.id == StockVoucherLine.voucher_id)
            .where(StockVoucherLine.request_line_id.in_(ids), StockVoucherLine.lot_id.is_not(None),
                   StockVoucher.loai == VOUCHER_NHAP)
        ).all():
            gom.setdefault(int(rl_id), []).append((int(gia or 0), float(sl or 0)))
        ra: dict[int, tuple[int | None, int | None]] = {}
        for rl_id, ds in gom.items():
            tong_sl = sum(sl for _, sl in ds)
            if any(gia <= 0 for gia, _ in ds) or tong_sl <= 0:
                ra[rl_id] = (None, None)
            else:
                tien = sum(gia * sl for gia, sl in ds)
                ra[rl_id] = (round(tien / tong_sl), round(tien))
        return ra

    def ma_don_theo_lsx(self, lsx_ids) -> dict[int, str]:
        """`{lệnh: số đơn hàng}` — kèm giá bán cho người đọc biết giá đó của đơn nào."""
        ids = {int(i) for i in lsx_ids if i}
        if not ids:
            return {}
        return {
            int(i): ma for i, ma in self.db.execute(
                select(Lsx.id, Order.order_no).join(Order, Order.id == Lsx.order_id)
                .where(Lsx.id.in_(ids))
            ).all()
        }

    def ds_lo_goc_tu_kcs(self, *, q: str | None, chi_chua_gia: bool, offset: int, limit: int):
        """Lô GỐC thành phẩm nhập từ KCS (mọi kho), mới nhất trước. Trả `(rows, total)`; mỗi row là
        `(lot, dòng phiếu nhập, dòng yêu cầu, tên kho, hàng, mã lệnh, số đơn, khách)`."""
        stmt = (
            select(StockLot, StockVoucherLine, StockRequestLine, KhoHang.ten, VatTuInAn,
                   Lsx.ma, Order.order_no, Customer.name)
            .join(StockVoucherLine, StockVoucherLine.lot_id == StockLot.id)
            .join(StockVoucher, StockVoucher.id == StockVoucherLine.voucher_id)
            .join(StockRequestLine, StockRequestLine.id == StockVoucherLine.request_line_id)
            .join(StockRequest, StockRequest.id == StockRequestLine.request_id)
            .outerjoin(KhoHang, KhoHang.id == StockLot.kho_id)
            .outerjoin(VatTuInAn, VatTuInAn.id == StockLot.hang_id)
            .outerjoin(Lsx, Lsx.id == StockRequestLine.lsx_id)
            .outerjoin(Order, Order.id == Lsx.order_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                StockLot.lo_goc_id.is_(None),
                StockLot.hang_loai == "vat_tu",
                StockVoucher.loai == VOUCHER_NHAP,
                StockRequest.san_xuat_cong_viec_id.is_not(None),
            )
        )
        if chi_chua_gia:
            stmt = stmt.where(func.coalesce(StockVoucherLine.don_gia, 0) == 0)
        tu = (q or "").strip().lower()
        if tu:
            mau = f"%{tu}%"
            stmt = stmt.where(or_(
                func.lower(StockLot.ma_lo).like(mau), func.lower(VatTuInAn.ma).like(mau),
                func.lower(VatTuInAn.ten).like(mau), func.lower(Lsx.ma).like(mau),
                func.lower(Order.order_no).like(mau), func.lower(Customer.name).like(mau),
            ))
        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = self.db.execute(
            stmt.order_by(StockLot.ngay_nhap.desc(), StockLot.id.desc()).offset(offset).limit(limit)
        ).all()
        return rows, int(total)

    def ton_theo_goc(self, goc_ids) -> dict[int, tuple[float, int]]:
        """`{lô gốc: (Σ còn lại của cả họ lô — đơn vị gốc, số lô trong họ)}`."""
        ids = {int(i) for i in goc_ids if i}
        if not ids:
            return {}
        goc = func.coalesce(StockLot.lo_goc_id, StockLot.id)
        return {
            int(g): (float(sl or 0), int(n))
            for g, sl, n in self.db.execute(
                select(goc, func.sum(StockLot.sl_con_lai), func.count())
                .where(goc.in_(ids))
                .group_by(goc)
            ).all()
        }
