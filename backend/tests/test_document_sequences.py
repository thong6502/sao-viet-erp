"""Backend tests for document sequences (Phase 1B).
"""
from __future__ import annotations

import pytest
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from app.db import SessionLocal
from app.repositories.document_sequence_repo import DocumentSequenceRepository
from app.services.sequence_service import SequenceService

def test_document_sequence_generation(client):
    db = SessionLocal()
    try:
        repo = DocumentSequenceRepository(db)
        service = SequenceService(repo)
        
        # Test first generation for quotation
        q_code_1 = service.generate_code("quotation", at_date=date(2026, 5, 10))
        assert q_code_1 == "BG26-0001"
        
        # Test second generation for quotation
        q_code_2 = service.generate_code("quotation", at_date=date(2026, 5, 10))
        assert q_code_2 == "BG26-0002"
        
        # Test different document type: costing
        c_code_1 = service.generate_code("costing", at_date=date(2026, 5, 10))
        assert c_code_1 == "TG26-0001"
        
        # Test order code
        o_code = service.generate_code("order", at_date=date(2026, 5, 10))
        assert o_code == "DH26-0001"
        
        # Test job code (LSX)
        j_code = service.generate_code("job", at_date=date(2026, 5, 10))
        assert j_code == "LSX26-0001"
        
        # Test code for next year (2027) starts fresh
        q_code_next_year = service.generate_code("quotation", at_date=date(2027, 1, 1))
        assert q_code_next_year == "BG27-0001"
    finally:
        db.close()


def test_invalid_doc_type_raises():
    db = SessionLocal()
    try:
        repo = DocumentSequenceRepository(db)
        service = SequenceService(repo)
        with pytest.raises(ValueError, match="Loại chứng từ"):
            service.generate_code("invalid_type")
    finally:
        db.close()


@pytest.mark.skip(reason="SQLite in-memory shared pool does not support concurrent write connections")
def test_document_sequence_concurrency(client):
    """Test concurrent generation of sequence codes.
    
    Ensures that generating codes concurrently produces no duplicates,
    has no gaps, and reaches exactly the expected count.
    """
    num_requests = 50
    doc_type = "quotation"
    ref_date = date(2026, 6, 1)
    
    # We will spawn concurrent threads generating codes using separate DB sessions
    def task():
        db = SessionLocal()
        try:
            repo = DocumentSequenceRepository(db)
            service = SequenceService(repo)
            return service.generate_code(doc_type, at_date=ref_date)
        finally:
            db.close()
            
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(task) for _ in range(num_requests)]
        codes = [f.result() for f in futures]
        
    # Check that there are no duplicate codes
    assert len(set(codes)) == num_requests
    
    # Verify exact sequential set of codes
    expected_codes = {f"BG26-{i:04d}" for i in range(1, num_requests + 1)}
    assert set(codes) == expected_codes


def test_cap_so_khong_tu_commit(client):
    """Bộ đếm đi CHUNG giao dịch với chứng từ — hỏng thì trả số lại.

    ⚠️ ĐÃ VỠ THẬT — 25/08/2026: `increment_and_get()` tự `commit()`, nên khi phát hành lệnh sản
    xuất nổ ở bước sau, cú commit đó đã cuốn theo cả `lsx.trang_thai = 'da_phat_hanh'` đang dở
    và cái vỏ gói rỗng — lệnh kẹt nửa vời, phải vá tay trên DB.
    """
    db = SessionLocal()
    try:
        service = SequenceService(DocumentSequenceRepository(db))
        ma_1 = service.generate_code("quotation", at_date=date(2030, 3, 3))
        db.rollback()  # giao dịch hỏng → số vừa cấp phải mất theo
        ma_2 = service.generate_code("quotation", at_date=date(2030, 3, 3))
        assert ma_1 == ma_2, f"số không được giữ lại sau rollback: {ma_1} rồi {ma_2}"
        assert ma_1.startswith("BG30-")
        db.rollback()
    finally:
        db.close()
