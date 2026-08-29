"""Repository — Tồn cuối kỳ đã chốt (`kho_ky_ton`, snapshot N-X-T).

Đọc: `latest_before` / `latest_before_map` lấy tồn cuối kỳ TRƯỚC một mốc ngày làm ĐẦU KỲ. Ghi:
`upsert` (chốt lúc khóa kỳ, đè nếu khóa lại) + `delete_range` (mở kỳ → xoá để tính lại).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from ..models.kho_ky_ton import KhoKyTon

Key = tuple[int, str, int]   # (kho_id, hang_loai, hang_id)


class KhoKyTonRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def latest_before(self, kho_id: int, hang_loai: str, hang_id: int, ngay: date) -> KhoKyTon | None:
        """Snapshot có `den_ngay` LỚN NHẤT nhưng < `ngay` (tồn cuối kỳ liền trước) của 1 mặt hàng."""
        return self.db.execute(
            select(KhoKyTon)
            .where(
                KhoKyTon.kho_id == kho_id,
                KhoKyTon.hang_loai == hang_loai,
                KhoKyTon.hang_id == hang_id,
                KhoKyTon.den_ngay < ngay,
            )
            .order_by(KhoKyTon.den_ngay.desc())
            .limit(1)
        ).scalar_one_or_none()

    def latest_before_map(self, ngay: date, kho_ids: list[int] | None = None) -> dict[Key, KhoKyTon]:
        """Với MỌI (kho, hàng): snapshot MỚI NHẤT có `den_ngay < ngay`. Bảng nhỏ → gom ở Python."""
        stmt = select(KhoKyTon).where(KhoKyTon.den_ngay < ngay)
        if kho_ids:
            stmt = stmt.where(KhoKyTon.kho_id.in_(kho_ids))
        stmt = stmt.order_by(KhoKyTon.den_ngay.asc())   # asc → dòng sau (mới hơn) đè dòng trước
        out: dict[Key, KhoKyTon] = {}
        for row in self.db.execute(stmt).scalars():
            out[(row.kho_id, row.hang_loai, row.hang_id)] = row
        return out

    def upsert(
        self, *, kho_id: int, hang_loai: str, hang_id: int, tu_ngay: date, den_ngay: date,
        ten_ky: str | None, sl_cuoi: float, gt_cuoi: int, don_gia_bq: float | None,
        khoa_so_id: int | None,
    ) -> KhoKyTon:
        row = self.db.execute(
            select(KhoKyTon).where(
                KhoKyTon.kho_id == kho_id,
                KhoKyTon.hang_loai == hang_loai,
                KhoKyTon.hang_id == hang_id,
                KhoKyTon.den_ngay == den_ngay,
            )
        ).scalar_one_or_none()
        if row is None:
            row = KhoKyTon(
                kho_id=kho_id, hang_loai=hang_loai, hang_id=hang_id,
                tu_ngay=tu_ngay, den_ngay=den_ngay,
            )
            self.db.add(row)
        row.tu_ngay = tu_ngay
        row.ten_ky = ten_ky
        row.sl_cuoi = sl_cuoi
        row.gt_cuoi = gt_cuoi
        row.don_gia_bq = don_gia_bq
        row.khoa_so_id = khoa_so_id
        self.db.flush()
        return row

    def aggregate_periods(self):
        """Gom snapshot theo (tu_ngay, den_ngay): số dòng · số kho · tổng GT cuối · lần tính mới nhất
        · tên kỳ đại diện. Cho tab 'Kỳ đã tính' (mới nhất trước)."""
        stmt = (
            select(
                KhoKyTon.tu_ngay,
                KhoKyTon.den_ngay,
                func.count().label("so_dong"),
                func.count(func.distinct(KhoKyTon.kho_id)).label("so_kho"),
                func.coalesce(func.sum(KhoKyTon.gt_cuoi), 0).label("tong_gt"),
                func.max(KhoKyTon.created_at).label("tinh_luc"),
                func.max(KhoKyTon.ten_ky).label("ten"),
            )
            .group_by(KhoKyTon.tu_ngay, KhoKyTon.den_ngay)
            .order_by(KhoKyTon.den_ngay.desc(), KhoKyTon.tu_ngay.desc())
        )
        return self.db.execute(stmt).all()

    def khos_by_period(self) -> dict[tuple[date, date], set[int]]:
        """{(tu_ngay, den_ngay) → {kho_id}} — để kiểm 'đã khóa' theo từng kỳ."""
        rows = self.db.execute(
            select(KhoKyTon.tu_ngay, KhoKyTon.den_ngay, KhoKyTon.kho_id).distinct()
        ).all()
        out: dict[tuple[date, date], set[int]] = {}
        for r in rows:
            out.setdefault((r.tu_ngay, r.den_ngay), set()).add(r.kho_id)
        return out

    def count_for_den(self, den: date, kho_ids: list[int] | None = None) -> int:
        """Số dòng snapshot có `den_ngay == den` (kỳ này đã tính giá chưa) — cho cờ `da_tinh`."""
        stmt = select(func.count()).select_from(KhoKyTon).where(KhoKyTon.den_ngay == den)
        if kho_ids:
            stmt = stmt.where(KhoKyTon.kho_id.in_(kho_ids))
        return int(self.db.execute(stmt).scalar_one())

    def delete_for_den(self, den: date, kho_ids: list[int] | None = None) -> int:
        """Xoá snapshot của MỘT mốc kỳ (`den_ngay`) — gọi trước khi TÍNH LẠI để không sót dòng cũ
        của mặt hàng nay không còn phát sinh. `kho_ids` None = mọi kho."""
        cond = KhoKyTon.den_ngay == den
        if kho_ids:
            cond = and_(cond, KhoKyTon.kho_id.in_(kho_ids))
        res = self.db.execute(delete(KhoKyTon).where(cond))
        return res.rowcount or 0

    def delete_range(self, tu: date, den: date, kho_ids: list[int] | None = None) -> int:
        """Xoá snapshot có `den_ngay` trong [tu, den] — gọi khi MỞ SỔ kỳ đó: bỏ chốt giá để khoá lại
        phải tính lại (khớp luật 'phải khoá mới tính', không giữ số cũ). `kho_ids` None = mọi kho."""
        cond = and_(KhoKyTon.den_ngay >= tu, KhoKyTon.den_ngay <= den)
        if kho_ids:
            cond = and_(cond, KhoKyTon.kho_id.in_(kho_ids))
        res = self.db.execute(delete(KhoKyTon).where(cond))
        return res.rowcount or 0
