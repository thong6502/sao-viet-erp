"""Sequence Service — business logic for document sequences.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from ..repositories.document_sequence_repo import DocumentSequenceRepository

PREFIX_MAP = {
    "costing": "TG",
    "quotation": "BG",
    "order": "DH",
    "job": "LSX",
}

# #18 — múi giờ NGHIỆP VỤ (VN = UTC+7, không DST → offset cố định, không cần tzdata). Server
# thường chạy UTC nên date.today() lệch ngày ~7 giờ đầu năm mới giờ VN → mã sinh sai năm
# (BG26 thay vì BG27). TODO(SVN): xác nhận múi giờ (nếu có chi nhánh khác múi giờ thì đổi).
BUSINESS_TZ = timezone(timedelta(hours=7))


def _business_today() -> date:
    return datetime.now(BUSINESS_TZ).date()

class SequenceService:
    def __init__(self, repo: DocumentSequenceRepository) -> None:
        self.repo = repo

    def generate_code(self, doc_type: str, at_date: date | None = None) -> str:
        """Generate a sequential document code for a given document type.
        
        Format: {PREFIX}{YY}-{NUMBER:04d}
        E.g. BG26-0001
        """
        if doc_type not in PREFIX_MAP:
            raise ValueError(f"Loại chứng từ '{doc_type}' không hợp lệ để sinh mã.")

        prefix = PREFIX_MAP[doc_type]
        ref_date = at_date or _business_today()
        year = ref_date.year
        yy = year % 100
        
        # Increment counter in DB (atomic)
        seq_num = self.repo.increment_and_get(doc_type, year)
        
        return f"{prefix}{yy:02d}-{seq_num:04d}"
