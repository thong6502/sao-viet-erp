"""Truy cập dữ liệu cho danh mục tài liệu nội quy."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.noi_quy import NoiQuyRecord
from ..models.user import User


class NoiQuyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _search_stmt(self, stmt, q: str | None):
        """Gắn OUTER JOIN users + điều kiện tìm cho `stmt`.

        Vì sao OUTER chứ không INNER: `uploaded_by` trỏ tới user có thể đã bị xoá — INNER JOIN
        là những bản ghi đó BIẾN MẤT khỏi danh sách (và khỏi `total`), người dùng tưởng tài liệu
        bị xoá theo người. Join 1-0..1 nên không nhân đôi dòng.

        Tìm cả TÊN NGƯỜI UPLOAD là cố ý: trước 09/08/2026 màn lọc ở client và có tìm theo người
        upload; đẩy `q` lên máy chủ mà bỏ cột này là người dùng thấy tính năng tự nhiên hụt đi."""
        stmt = stmt.outerjoin(User, NoiQuyRecord.uploaded_by == User.id)
        key = (q or "").strip()
        if not key:
            return stmt
        like = f"%{key}%"
        return stmt.where(or_(
            NoiQuyRecord.code.ilike(like),
            NoiQuyRecord.name.ilike(like),
            NoiQuyRecord.file_name.ilike(like),
            NoiQuyRecord.note.ilike(like),
            User.name.ilike(like),
            User.username.ilike(like),
        ))

    def list_all(self, *, q: str | None = None, limit: int | None = None,
                 offset: int = 0) -> list[NoiQuyRecord]:
        """`limit=None` = trả trọn bảng (hành vi cũ, giữ cho mọi lời gọi không phân trang)."""
        stmt = self._search_stmt(select(NoiQuyRecord), q).order_by(
            NoiQuyRecord.uploaded_at.desc(), NoiQuyRecord.id.desc()
        )
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars())

    def count(self, *, q: str | None = None) -> int:
        """Đếm ở DB (không `len(list_all())`) — nuôi số "Tổng N tài liệu" ở chân bảng."""
        stmt = self._search_stmt(
            select(func.count(NoiQuyRecord.id)).select_from(NoiQuyRecord), q
        )
        return int(self.db.execute(stmt).scalar_one())

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
