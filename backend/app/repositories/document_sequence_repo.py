"""Document Sequence Repository — atomic counter generation for document codes.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session
from ..models.document_sequence import DocumentSequence

class DocumentSequenceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def increment_and_get(self, doc_type: str, year: int) -> int:
        """Atomic UPSERT and increment of the sequence for (doc_type, year).

        Returns the new incremented sequence number.

        KHÔNG commit: bộ đếm đi CHUNG giao dịch với chứng từ gọi nó. Trước 25/08/2026 hàm này
        tự `commit()`, nên khi việc lập chứng từ hỏng ở bước sau, mọi thay đổi ORM đang dở
        (đã bị cú commit đó cuốn theo) nằm lại DB — vụ lệnh sản xuất kẹt `da_phat_hanh` mà
        không có công việc nào là do đây. Nay hỏng ở đâu cũng rollback trọn vẹn, số cấp dở bị
        trả lại. Trên Postgres câu UPSERT giữ khoá dòng tới lúc commit ⇒ vẫn không cấp trùng.
        """
        dialect_name = self.db.bind.dialect.name
        
        if dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(DocumentSequence).values(doc_type=doc_type, year=year, current_number=1)
            stmt = stmt.on_conflict_do_update(
                index_elements=["doc_type", "year"],
                set_=dict(current_number=DocumentSequence.current_number + 1)
            ).returning(DocumentSequence.current_number)
            return self.db.execute(stmt).scalar_one()
        else:
            # Fallback for SQLite (tests/local development)
            # 1. Insert with 0 if not exists
            self.db.execute(
                text(
                    "INSERT OR IGNORE INTO document_sequences (doc_type, year, current_number) "
                    "VALUES (:doc_type, :year, 0)"
                ),
                {"doc_type": doc_type, "year": year}
            )
            # 2. Increment by 1
            self.db.execute(
                text(
                    "UPDATE document_sequences SET current_number = current_number + 1 "
                    "WHERE doc_type = :doc_type AND year = :year"
                ),
                {"doc_type": doc_type, "year": year}
            )
            # 3. Select current value
            val = self.db.execute(
                text(
                    "SELECT current_number FROM document_sequences "
                    "WHERE doc_type = :doc_type AND year = :year"
                ),
                {"doc_type": doc_type, "year": year}
            ).scalar_one()
            return val
