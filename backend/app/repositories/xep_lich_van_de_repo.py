"""Repository Vấn đề kế hoạch — truy vấn bảng `xep_lich_van_de` (phần con người xử lý).

Bảng chỉ neo state theo `issue_key`; danh sách vấn đề là dẫn xuất (service tính lúc đọc) rồi LEFT JOIN
state qua `get_map`. Không có truy vấn đặc thù nào ngoài tra theo key.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.xep_lich_van_de import XepLichVanDe


class XepLichVanDeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads ---------------------------------------------------------------

    def get_by_key(self, issue_key: str) -> XepLichVanDe | None:
        return self.db.execute(
            select(XepLichVanDe).where(XepLichVanDe.issue_key == issue_key)
        ).scalar_one_or_none()

    def get_map(self, keys: list[str]) -> dict[str, XepLichVanDe]:
        """State của các issue_key cho trước (batch, LEFT JOIN lúc dựng danh sách vấn đề)."""
        keys = [k for k in keys if k]
        if not keys:
            return {}
        rows = self.db.execute(
            select(XepLichVanDe).where(XepLichVanDe.issue_key.in_(keys))
        ).scalars()
        return {r.issue_key: r for r in rows}

    # --- writes --------------------------------------------------------------

    def get_or_create(self, issue_key: str, *, created_by: int | None) -> tuple[XepLichVanDe, bool]:
        """Lấy dòng state theo key, tạo mới nếu chưa có. Trả (row, đã_tạo_mới)."""
        row = self.get_by_key(issue_key)
        if row is not None:
            return row, False
        row = XepLichVanDe(issue_key=issue_key, created_by=created_by)
        self.db.add(row)
        self.db.flush()
        return row, True

    def commit(self) -> None:
        self.db.commit()
