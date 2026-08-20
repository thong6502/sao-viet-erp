"""Repository nhãn công đoạn — bản sao lối truy vấn của nhãn khách hàng (`customer_repo`).

Hạ chữ để dedup làm TRONG PYTHON chứ không `lower()` trong SQL: `lower()` của SQLite chỉ hạ chữ
ASCII nên "Ưu tiên" và "ưu tiên" ra hai nhóm — cùng lỗi đã ghi ở `customer_repo.ids_with_label`.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.cong_doan_tag import CongDoanTag, CongDoanTagCatalog


class CongDoanTagRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- kho nhãn dùng chung (`cong_doan_tag_catalog`) --------------------------

    def list_kho_nhan(self) -> list[CongDoanTagCatalog]:
        return list(
            self.db.execute(
                select(CongDoanTagCatalog).order_by(CongDoanTagCatalog.label)
            ).scalars()
        )

    def dem_buoc_theo_nhan(self) -> dict[str, int]:
        """Số bước đang mang từng nhãn, gom theo nhãn hạ chữ (Python, không GROUP BY lower)."""
        out: dict[str, int] = {}
        for (label,) in self.db.execute(select(CongDoanTag.label)).all():
            key = label.strip().lower()
            out[key] = out.get(key, 0) + 1
        return out

    def tim_nhan_kho(self, label: str) -> CongDoanTagCatalog | None:
        needle = label.strip().lower()
        for row in self.list_kho_nhan():
            if row.label.strip().lower() == needle:
                return row
        return None

    def get_nhan_kho(self, nhan_id: int) -> CongDoanTagCatalog | None:
        return self.db.get(CongDoanTagCatalog, nhan_id)

    def them_nhan_kho(self, *, label: str, created_by: int | None) -> CongDoanTagCatalog:
        row = CongDoanTagCatalog(label=label, created_by=created_by)
        self.db.add(row)
        self.db.flush()
        self.db.refresh(row)
        return row

    def xoa_nhan_kho(self, row: CongDoanTagCatalog) -> int:
        """Xoá dòng danh mục + mọi dòng gán mang đúng nhãn (case-insensitive). Trả số bước bị gỡ."""
        needle = row.label.strip().lower()
        go = [
            t for t in self.db.execute(select(CongDoanTag)).scalars()
            if t.label.strip().lower() == needle
        ]
        for t in go:
            self.db.delete(t)
        self.db.delete(row)
        self.db.flush()
        return len(go)

    # --- nhãn đã gán cho bước (`cong_doan_tags`) --------------------------------

    def list_tags(self, buoc_loai: str, buoc_id: int) -> list[CongDoanTag]:
        return list(
            self.db.execute(
                select(CongDoanTag)
                .where(CongDoanTag.buoc_loai == buoc_loai, CongDoanTag.buoc_id == buoc_id)
                .order_by(CongDoanTag.label)
            ).scalars()
        )

    def get_tag(self, tag_id: int) -> CongDoanTag | None:
        return self.db.get(CongDoanTag, tag_id)

    def find_tag_by_label(self, buoc_loai: str, buoc_id: int, label: str) -> CongDoanTag | None:
        needle = label.strip().lower()
        for t in self.list_tags(buoc_loai, buoc_id):
            if t.label.lower() == needle:
                return t
        return None

    def add_tag(
        self, buoc_loai: str, buoc_id: int, *, label: str, created_by: int | None
    ) -> CongDoanTag:
        tag = CongDoanTag(
            buoc_loai=buoc_loai, buoc_id=buoc_id, label=label, created_by=created_by
        )
        self.db.add(tag)
        self.db.flush()
        self.db.refresh(tag)
        return tag

    def delete_tag(self, tag: CongDoanTag) -> None:
        self.db.delete(tag)
        self.db.flush()

    def xoa_theo_buoc(self, buoc_loai: str, buoc_id: int) -> int:
        """Dọn mọi nhãn của một bước khi bước bị xoá. Trả số nhãn đã gỡ."""
        go = self.list_tags(buoc_loai, buoc_id)
        for t in go:
            self.db.delete(t)
        return len(go)
