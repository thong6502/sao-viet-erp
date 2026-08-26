"""Repo bảng `cong_thuc_lich_su` — xem `models/cong_thuc_lich_su.py` để biết vì sao có bảng này."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.cong_thuc_lich_su import CongThucLichSu


class CongThucLichSuRepository:
    def __init__(self, db: Session):
        self.db = db

    def ghi(self, *, bang: str, row_id: int, truong: str,
            gia_tri_cu: str | None, gia_tri_moi: str | None,
            sua_boi: int | None) -> None:
        """Chỉ `add` — KHÔNG `commit`: đi chung giao dịch với `AuditLogRepository.create()`
        đang gọi nó (xem `nhat_ky_danh_muc.ghi_sua`), để lịch sử công thức và nhật ký luôn khớp
        nhau, không bao giờ lệch nếu 1 trong 2 lỡ lưu mà cái kia rollback."""
        self.db.add(CongThucLichSu(
            bang=bang, row_id=row_id, truong=truong,
            gia_tri_cu=gia_tri_cu, gia_tri_moi=gia_tri_moi, sua_boi=sua_boi,
        ))

    def moi_nhat_nhieu(self, bang: str, row_ids: list[int],
                        truong: str) -> dict[int, CongThucLichSu]:
        """1 dòng mới nhất / row_id — 1 truy vấn cho cả trang, tránh N+1 (mẫu
        `VatLieuKhoService.gan_ten_don_vi`)."""
        if not row_ids:
            return {}
        rows = self.db.execute(
            select(CongThucLichSu)
            .where(
                CongThucLichSu.bang == bang,
                CongThucLichSu.row_id.in_(row_ids),
                CongThucLichSu.truong == truong,
            )
            .order_by(CongThucLichSu.row_id, CongThucLichSu.sua_luc.desc(),
                      CongThucLichSu.id.desc())
        ).scalars().all()
        ket: dict[int, CongThucLichSu] = {}
        for r in rows:
            ket.setdefault(r.row_id, r)
        return ket

    def liet_ke(self, bang: str, row_id: int, truong: str,
                limit: int = 50) -> list[CongThucLichSu]:
        return list(self.db.execute(
            select(CongThucLichSu)
            .where(
                CongThucLichSu.bang == bang,
                CongThucLichSu.row_id == row_id,
                CongThucLichSu.truong == truong,
            )
            .order_by(CongThucLichSu.sua_luc.desc(), CongThucLichSu.id.desc())
            .limit(limit)
        ).scalars().all())
