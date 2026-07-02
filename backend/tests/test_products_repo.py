"""feat-033 — Sản phẩm in (Product catalog) data model + repository (spec-07).

Repository level: sequential unique SP### codes, product+components in one transaction
(rollback → no orphan product), get returns components ordered by sequence, delete
cascades to components, paper_master_id FK-nullable (SEAM-03).
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db import Base, SessionLocal, engine, init_db
from app.models.product import ProductComponent
from app.repositories.product_repo import ComponentInput, ProductRepository


@pytest.fixture
def db():
    # Wipe + recreate the shared in-memory schema so each test starts empty (the
    # StaticPool DB is shared across the session — products would otherwise leak).
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    init_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _comp(ctype="body", seq=0, page_count=8, paper_master_id=None) -> ComponentInput:
    return ComponentInput(
        component_type=ctype,
        paper_master_id=paper_master_id,
        colors_front=4,
        colors_back=4,
        page_count=page_count,
        finished_w=20.0,
        finished_h=28.0,
        bleed=3.0,
        grain_direction="long",
        sequence=seq,
    )


def test_create_generates_sequential_unique_code(db):
    repo = ProductRepository(db)
    a = repo.create(name="SP A", product_type="name_card", binding_type=None, note=None, components=[])
    b = repo.create(name="SP B", product_type="name_card", binding_type=None, note=None, components=[])
    assert a.code.startswith("SP") and b.code.startswith("SP")
    assert a.code != b.code
    assert int(b.code[2:]) == int(a.code[2:]) + 1
    assert len(a.code) >= 5  # "SP" + >=3 digits


def test_create_persists_product_and_components_one_transaction(db):
    repo = ProductRepository(db)
    p = repo.create(
        name="Sách demo",
        product_type="sach",
        binding_type="saddle",
        note="ghi chú",
        components=[_comp("cover", seq=0, page_count=4), _comp("body", seq=1, page_count=32)],
    )
    assert p.id is not None
    assert len(p.components) == 2
    # Components ordered by sequence.
    assert [c.component_type for c in p.components] == ["cover", "body"]


def test_get_returns_components_ordered_by_sequence(db):
    repo = ProductRepository(db)
    p = repo.create(
        name="Ordered",
        product_type="sach",
        binding_type="perfect",
        note=None,
        components=[_comp("body", seq=2, page_count=16), _comp("cover", seq=0, page_count=4)],
    )
    loaded = repo.get_by_id(p.id)
    seqs = [c.sequence for c in loaded.components]
    assert seqs == sorted(seqs)
    assert loaded.components[0].sequence == 0


def test_paper_master_id_may_be_null(db):
    """SEAM-03: FK-nullable — a component saves with paper_master_id=None."""
    repo = ProductRepository(db)
    p = repo.create(
        name="No paper yet",
        product_type="sach",
        binding_type="saddle",
        note=None,
        components=[_comp("body", page_count=8, paper_master_id=None)],
    )
    assert p.components[0].paper_master_id is None


def test_delete_cascades_to_components(db):
    repo = ProductRepository(db)
    p = repo.create(
        name="To delete",
        product_type="sach",
        binding_type="saddle",
        note=None,
        components=[_comp("body", page_count=8), _comp("cover", seq=1, page_count=4)],
    )
    pid = p.id
    before = db.execute(
        select(func.count()).select_from(ProductComponent).where(ProductComponent.product_id == pid)
    ).scalar_one()
    assert before == 2
    repo.delete(p)
    after = db.execute(
        select(func.count()).select_from(ProductComponent).where(ProductComponent.product_id == pid)
    ).scalar_one()
    assert after == 0
    assert repo.get_by_id(pid) is None


def test_update_replaces_component_set(db):
    repo = ProductRepository(db)
    p = repo.create(
        name="Editable",
        product_type="sach",
        binding_type="saddle",
        note=None,
        components=[_comp("body", page_count=8), _comp("cover", seq=1, page_count=4)],
    )
    pid = p.id
    repo.update(
        p,
        name="Editable",
        product_type="sach",
        binding_type="saddle",
        note=None,
        components=[_comp("body", page_count=16)],
    )
    loaded = repo.get_by_id(pid)
    assert len(loaded.components) == 1
    assert loaded.components[0].page_count == 16
    # Orphaned old rows are gone.
    total = db.execute(
        select(func.count()).select_from(ProductComponent).where(ProductComponent.product_id == pid)
    ).scalar_one()
    assert total == 1


def test_list_filters_by_q_and_type_with_counts(db):
    repo = ProductRepository(db)
    repo.create(name="Alpha card", product_type="name_card", binding_type=None, note=None, components=[])
    repo.create(
        name="Beta book",
        product_type="sach",
        binding_type="saddle",
        note=None,
        components=[_comp("body", page_count=8)],
    )
    rows, total, counts = repo.list(q="alpha")
    assert total == 1 and rows[0].name == "Alpha card"
    rows2, total2, counts2 = repo.list(product_type="sach")
    assert total2 == 1 and rows2[0].name == "Beta book"
    assert counts2[rows2[0].id] == 1
