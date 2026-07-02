"""Document Sequence model — spec-09/Phase 1B.

Safe atomic counters for system-generated document numbers (Báo giá, Đơn hàng, Tính giá, v.v.)
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

class DocumentSequence(Base):
    __tablename__ = "document_sequences"

    doc_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    current_number: Mapped[int] = mapped_column(
        Integer, CheckConstraint("current_number >= 0"), nullable=False, default=0
    )

    __table_args__ = (
        CheckConstraint(
            "year >= 2000 AND year <= 2100",
            name="chk_document_sequences_year"
        ),
    )
