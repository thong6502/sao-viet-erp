"""Sequence Service — business logic for document sequences.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from ..models.document_sequence import (
    SEQ_DOC_TYPE_PAYMENT_RECEIPT,
    SEQ_DOC_TYPE_PAYMENT_VOUCHER,
    SEQ_YEAR_GLOBAL,
)
from ..repositories.document_sequence_repo import DocumentSequenceRepository

PREFIX_MAP = {
    "costing": "TG",
    "quotation": "BG",
    "order": "DH",
    "job": "LSX",
}

# Số chứng từ IN trên mẫu Bộ Tài chính (PC00445 / PT00027) — không có năm, chạy liên tục.
FLAT_PREFIX_MAP = {
    SEQ_DOC_TYPE_PAYMENT_VOUCHER: "PC",  # dùng chung cho Phiếu chi tiền mặt LẪN UNC
    SEQ_DOC_TYPE_PAYMENT_RECEIPT: "PT",
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

    def generate_flat_code(self, doc_type: str) -> str:
        """Số chứng từ IN trên mẫu Bộ Tài chính: PC00445 / PT00027.

        Khác `generate_code` (có YY, reset hằng năm): số này chạy LIÊN TỤC, không reset
        theo năm — vì nó in trên chứng từ pháp lý và phải duy nhất vĩnh viễn để tra cứu.
        Vượt 99999 thì tự nới thành PC100000 (không vỡ).
        """
        if doc_type not in FLAT_PREFIX_MAP:
            raise ValueError(f"Loại chứng từ '{doc_type}' không hợp lệ để sinh số phiếu.")
        seq_num = self.repo.increment_and_get(doc_type, SEQ_YEAR_GLOBAL)
        return f"{FLAT_PREFIX_MAP[doc_type]}{seq_num:05d}"
