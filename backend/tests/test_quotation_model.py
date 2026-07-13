"""Báo giá H-V-I data model (Quote → QuoteVersion → QuoteItem).

Model-level: status constants, header/version/item roundtrip, current_version pointer,
per-item estimate reference (1 báo giá pick từ NHIỀU phiếu tính giá), cascade delete
(xóa quote → versions/items/activity đi theo).
"""
from __future__ import annotations

import pytest

from app.db import Base, SessionLocal, engine
from app.models.quotation import (
    QUOTE_STATUSES,
    STATUS_ACCEPTED,
    STATUS_CANCELLED,
    STATUS_CONVERTED_TO_ORDER,
    STATUS_DRAFT,
    STATUS_EXPIRED,
    STATUS_PENDING_APPROVAL,
    STATUS_REJECTED,
    STATUS_SENT,
    Quote,
    QuoteActivityLog,
    QuoteItem,
    QuoteVersion,
)


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _mk_quote(db, *, number="BGT-0001", status=STATUS_DRAFT) -> Quote:
    q = Quote(quote_number=number, status=status)
    db.add(q)
    db.flush()
    v = QuoteVersion(
        quote_id=q.id, version_number=1, status="draft",
        subtotal_amount=1_000_000, discount_amount=0, vat_percent=8,
        vat_amount=80_000, final_amount=1_080_000,
    )
    db.add(v)
    db.flush()
    q.current_version_id = v.id
    return q


def test_status_constants_complete():
    assert QUOTE_STATUSES == (
        STATUS_DRAFT, STATUS_PENDING_APPROVAL, STATUS_SENT, STATUS_ACCEPTED,
        STATUS_REJECTED, STATUS_EXPIRED, STATUS_CONVERTED_TO_ORDER, STATUS_CANCELLED,
    )


def test_header_version_item_roundtrip(db):
    q = _mk_quote(db)
    v = db.get(QuoteVersion, q.current_version_id)
    db.add(QuoteItem(
        quote_version_id=v.id, line_no=1, product_type="brochure", product_name="Catalogue A4",
        product_spec_text="21×29,7 cm · 4 màu/2 mặt", quantity=1000, unit="cái",
        total_cost_snapshot=800_000, margin_percent=20, selling_price=1_000_000,
        unit_price=1_000, discount_amount=0, vat_percent=8, vat_amount=80_000,
        final_amount=1_080_000,
    ))
    db.commit()

    fresh = db.get(Quote, q.id)
    assert fresh.quote_number == "BGT-0001"
    assert len(fresh.versions) == 1
    assert fresh.versions[0].items[0].product_name == "Catalogue A4"
    assert float(fresh.versions[0].items[0].total_cost_snapshot) == 800_000


def test_items_carry_per_line_estimate_reference(db):
    """1 báo giá pick từ NHIỀU phiếu tính giá — mỗi dòng giữ estimate_id riêng."""
    from app.models.estimate import Estimate

    e1 = Estimate(estimate_number="TGT-1", product_type="brochure", product_name="SP1",
                  status="calculated", input_spec_json={}, quantity_list_json=[1000])
    e2 = Estimate(estimate_number="TGT-2", product_type="box", product_name="SP2",
                  status="calculated", input_spec_json={}, quantity_list_json=[500])
    db.add_all([e1, e2])
    db.flush()

    q = _mk_quote(db, number="BGT-0002")
    v = db.get(QuoteVersion, q.current_version_id)
    for i, est in enumerate((e1, e2), start=1):
        db.add(QuoteItem(
            quote_version_id=v.id, estimate_id=est.id, line_no=i,
            product_type=est.product_type, product_name=est.product_name,
            quantity=100, unit="cái", total_cost_snapshot=1, margin_percent=0,
            selling_price=1, unit_price=1, discount_amount=0, vat_percent=0,
            vat_amount=0, final_amount=1,
        ))
    db.commit()

    fresh = db.get(Quote, q.id)
    refs = {it.estimate_id for it in fresh.versions[0].items}
    assert refs == {e1.id, e2.id}


def test_cascade_delete_versions_items_activity(db):
    q = _mk_quote(db, number="BGT-0003")
    v = db.get(QuoteVersion, q.current_version_id)
    db.add(QuoteItem(
        quote_version_id=v.id, line_no=1, product_type="x", product_name="x",
        quantity=1, unit="cái", total_cost_snapshot=0, margin_percent=0,
        selling_price=0, unit_price=0, discount_amount=0, vat_percent=0,
        vat_amount=0, final_amount=0,
    ))
    db.add(QuoteActivityLog(quote_id=q.id, action="create_quote"))
    db.commit()
    qid, vid = q.id, v.id

    db.delete(db.get(Quote, qid))
    db.commit()

    assert db.get(QuoteVersion, vid) is None
    assert db.query(QuoteItem).filter_by(quote_version_id=vid).count() == 0
    assert db.query(QuoteActivityLog).filter_by(quote_id=qid).count() == 0
