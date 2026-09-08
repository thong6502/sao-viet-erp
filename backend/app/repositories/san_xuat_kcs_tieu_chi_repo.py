"""Repository — Danh mục HẠNG MỤC KIỂM KCS (một hạng mục thuộc ĐÚNG MỘT công đoạn, mg `0285`)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.cong_doan import CongDoan
from ..models.san_xuat_kcs import SanXuatKcsTieuChi
from .catalog_base import CatalogRepo


class SanXuatKcsTieuChiRepository(CatalogRepo):
    model = SanXuatKcsTieuChi
    fields = ("cong_doan_id", "ten", "huong_dan", "bat_buoc", "thu_tu", "active")
    ma_case = "upper"
    ma_prefix = "KM"        # mã sinh ngầm: người khai chỉ gõ câu chữ hạng mục

    def cong_doan_ids_ton_tai(self, ids: set[int]) -> set[int]:
        """Tập id công đoạn CÓ THẬT trong `ids` — service dùng để chặn khai vào id ma."""
        if not ids:
            return set()
        return {i for (i,) in self.db.execute(
            select(CongDoan.id).where(CongDoan.id.in_(ids))
        ).all()}

    def trung_ten(self, cong_doan_id: int, ten: str, tru_id: int | None = None) -> bool:
        """Công đoạn này đã có hạng mục cùng câu chữ chưa (khớp `uq_kcs_hang_muc_cong_doan_ten`).

        Kiểm ở service để trả 400 có chữ, thay vì để UniqueConstraint bắn 500."""
        q = select(SanXuatKcsTieuChi.id).where(
            SanXuatKcsTieuChi.cong_doan_id == cong_doan_id,
            SanXuatKcsTieuChi.ten == ten,
        )
        if tru_id is not None:
            q = q.where(SanXuatKcsTieuChi.id != tru_id)
        return self.db.execute(q.limit(1)).first() is not None


def hang_muc_theo_cong_doan(db: Session) -> dict[int, list[SanXuatKcsTieuChi]]:
    """{cong_doan_id: [hạng mục]} cho TOÀN danh mục — màn khai báo bày ba tầng nên đọc một phát,
    đừng gọi mỗi công đoạn một truy vấn."""
    rows = list(db.execute(
        select(SanXuatKcsTieuChi).order_by(
            SanXuatKcsTieuChi.cong_doan_id, SanXuatKcsTieuChi.thu_tu, SanXuatKcsTieuChi.id
        )
    ).scalars())
    out: dict[int, list[SanXuatKcsTieuChi]] = {}
    for r in rows:
        out.setdefault(r.cong_doan_id, []).append(r)
    return out
