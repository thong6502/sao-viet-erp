"""Repository — Phiếu nhập/xuất kho (spec-kho-de-nghi §5)."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models.stock_voucher import (
    VOUCHER_DRAFT,
    StockVoucher,
    StockVoucherAttachment,
    StockVoucherLine,
)

_HEADER_FIELDS = ("kho_id", "ngay", "nguoi_giao_nhan", "ghi_chu")


class StockVoucherRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, voucher_id: int) -> StockVoucher | None:
        return self.db.get(StockVoucher, voucher_id)

    def get_by_ma(self, ma: str) -> StockVoucher | None:
        return self.db.execute(
            select(StockVoucher).where(func.upper(StockVoucher.ma) == ma.strip().upper())
        ).scalars().first()

    def get_with_lines(self, voucher_id: int) -> StockVoucher | None:
        return self.db.execute(
            select(StockVoucher)
            .options(selectinload(StockVoucher.lines))
            .where(StockVoucher.id == voucher_id)
        ).scalars().first()

    def list(self, *, loai: str | None = None, trang_thai: str | None = None,
             request_id: int | None = None, kho_id: int | None = None,
             q: str | None = None, page: int = 1, size: int = 50):
        conds = []
        if loai:
            conds.append(StockVoucher.loai == loai)
        if trang_thai:
            conds.append(StockVoucher.trang_thai == trang_thai)
        if request_id is not None:
            conds.append(StockVoucher.request_id == request_id)
        if kho_id is not None:
            conds.append(StockVoucher.kho_id == kho_id)
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(
                func.lower(StockVoucher.ma).like(like),
                func.lower(func.coalesce(StockVoucher.ghi_chu, "")).like(like),
            ))

        base = select(StockVoucher).options(selectinload(StockVoucher.lines))
        count_stmt = select(func.count()).select_from(StockVoucher)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        base = base.order_by(StockVoucher.id.desc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def draft_ids_by_request(self, request_ids: list[int]) -> dict[int, int]:
        """Map {request_id: id phiếu ĐANG CHỜ GHI SỔ (draft) mới nhất}. Để đề nghị biết đã có
        phiếu chờ ghi sổ chưa → đổi nút 'Lập phiếu' thành 'Xem phiếu', chống tạo trùng."""
        if not request_ids:
            return {}
        rows = self.db.execute(
            select(StockVoucher.request_id, StockVoucher.id)
            .where(
                StockVoucher.request_id.in_(request_ids),
                StockVoucher.trang_thai == VOUCHER_DRAFT,
            )
            .order_by(StockVoucher.id.desc())
        ).all()
        out: dict[int, int] = {}
        for req_id, vid in rows:
            out.setdefault(req_id, vid)  # đã sắp desc → phần tử đầu mỗi req là mới nhất
        return out

    def sum_issued_for_line(self, request_line_id: int, *, exclude_voucher_id: int | None = None) -> float:
        """Tổng số lượng đã ứng vào 1 dòng đề nghị qua các phiếu ĐÃ GHI SỔ.

        Dùng để kiểm tra chặn "ứng vượt SL duyệt" một cách độc lập với `sl_da_ung` — hai
        con số phải khớp; lệch nghĩa là có bug ghi sổ, và cách tính lại này bắt được.
        """
        from ..models.stock_voucher import VOUCHER_POSTED

        stmt = (
            select(func.coalesce(func.sum(StockVoucherLine.so_luong), 0))
            .join(StockVoucher, StockVoucher.id == StockVoucherLine.voucher_id)
            .where(
                StockVoucherLine.request_line_id == request_line_id,
                StockVoucher.trang_thai == VOUCHER_POSTED,
            )
        )
        if exclude_voucher_id is not None:
            stmt = stmt.where(StockVoucher.id != exclude_voucher_id)
        return float(self.db.execute(stmt).scalar_one() or 0)

    def xuat_history(self, material_id: int, kho_id: int) -> list[dict]:
        """Lịch sử XUẤT của 1 mã hàng tại 1 kho — mỗi dòng phiếu XUẤT ĐÃ GHI SỔ, đích danh lô.

        Giá vốn của dòng xuất = giá của lô bị trừ (`don_gia_nhap`), không phải `line.don_gia`
        (phiếu xuất không khai giá). Router ẩn giá nếu người gọi thiếu `can_view_cost`.
        """
        from ..models.stock_lot import StockLot
        from ..models.stock_voucher import VOUCHER_POSTED, VOUCHER_XUAT

        stmt = (
            select(
                StockVoucher.id, StockVoucher.ma, StockVoucher.ngay,
                StockVoucherLine.lot_id, StockVoucherLine.so_luong,
                StockLot.ma_lo, StockLot.don_gia_nhap,
            )
            .join(StockVoucher, StockVoucher.id == StockVoucherLine.voucher_id)
            .join(StockLot, StockLot.id == StockVoucherLine.lot_id, isouter=True)
            .where(
                StockVoucherLine.material_id == material_id,
                StockVoucher.kho_id == kho_id,
                StockVoucher.loai == VOUCHER_XUAT,
                StockVoucher.trang_thai == VOUCHER_POSTED,
            )
            .order_by(StockVoucher.ngay.desc(), StockVoucher.id.desc())
        )
        return [
            {
                "voucher_id": r.id, "voucher_ma": r.ma, "ngay": r.ngay,
                "lot_id": r.lot_id, "ma_lo": r.ma_lo,
                "so_luong": float(r.so_luong), "don_gia": int(r.don_gia_nhap or 0),
            }
            for r in self.db.execute(stmt).all()
        ]

    def create(self, *, ma: str, loai: str, request_id: int, nguoi_lap_id: int,
               lines: list[dict], **header) -> StockVoucher:
        obj = StockVoucher(ma=ma, loai=loai, request_id=request_id, nguoi_lap_id=nguoi_lap_id)
        for k in _HEADER_FIELDS:
            if k in header:
                setattr(obj, k, header[k])
        for ln in lines:
            obj.lines.append(StockVoucherLine(
                request_line_id=ln["request_line_id"],
                material_id=ln["material_id"],
                lot_id=ln.get("lot_id"),
                so_luong=ln["so_luong"],
                don_gia=ln.get("don_gia"),
                ghi_chu=ln.get("ghi_chu"),
            ))
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def save(self, obj: StockVoucher) -> StockVoucher:
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj: StockVoucher) -> None:
        self.db.delete(obj)
        self.db.commit()

    # --- Đính kèm (hóa đơn/chứng từ gốc) -----------------------------------
    def list_attachments(self, voucher_id: int) -> list[StockVoucherAttachment]:
        return list(self.db.execute(
            select(StockVoucherAttachment)
            .where(StockVoucherAttachment.stock_voucher_id == voucher_id)
            .order_by(StockVoucherAttachment.id)
        ).scalars())

    def get_attachment(self, attachment_id: int) -> StockVoucherAttachment | None:
        return self.db.get(StockVoucherAttachment, attachment_id)

    def save_attachment(self, obj: StockVoucherAttachment) -> StockVoucherAttachment:
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete_attachment(self, obj: StockVoucherAttachment) -> None:
        self.db.delete(obj)
        self.db.commit()
