"""Document Sequence model — spec-09/Phase 1B.

Safe atomic counters for system-generated document numbers (Báo giá, Đơn hàng, Tính giá, v.v.)
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

# Bộ đếm KHÔNG có chiều thời gian (số phiếu chi/thu chạy liên tục, không reset theo
# năm — số này in trên chứng từ pháp lý nên phải duy nhất vĩnh viễn để tra cứu).
# CHECK dưới cấm year=0 nên dùng 2000 = giá trị hợp lệ nhỏ nhất làm sentinel; không
# có chứng từ thật nào năm 2000.
SEQ_YEAR_GLOBAL = 2000
SEQ_DOC_TYPE_PAYMENT_VOUCHER = "payment_voucher"
SEQ_DOC_TYPE_PAYMENT_RECEIPT = "payment_receipt"


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
