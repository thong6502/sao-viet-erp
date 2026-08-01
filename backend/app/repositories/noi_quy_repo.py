"""Truy cập dữ liệu cho danh mục tài liệu nội quy."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.noi_quy import NoiQuyRecord


class NoiQuyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(self) -> list[NoiQuyRecord]:
        return list(self.db.execute(
            select(NoiQuyRecord).order_by(
                NoiQuyRecord.uploaded_at.desc(), NoiQuyRecord.id.desc()
            )
        ).scalars())

    def get(self, record_id: int) -> NoiQuyRecord | None:
        return self.db.get(NoiQuyRecord, record_id)

    def code_exists(self, code: str) -> bool:
        return self.db.execute(
            select(NoiQuyRecord.id).where(NoiQuyRecord.code == code)
        ).scalar_one_or_none() is not None

    def create(self, **values) -> NoiQuyRecord:
        row = NoiQuyRecord(**values)
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise
        self.db.refresh(row)
        return row

    def delete(self, row: NoiQuyRecord) -> None:
        self.db.delete(row)
        self.db.commit()
