"""Enabling-point test for the Sản phẩm (Product catalog) cross-module seam.

SEAM-03: Sản phẩm ← Danh mục Giấy (PaperMaster, module ``dm_giay_vat_tu``).
"""
from __future__ import annotations

from app.db import SessionLocal
from app.services import product_ports
from app.models.material import Material
from sqlalchemy import select

def test_seam_03_paper_master_lookup(client):
    """Back-fill: Danh mục Giấy resolves a PaperMaster for ProductComponent.paper_master_id."""
    db = SessionLocal()
    try:
        # Fetch the seeded paper
        paper_in_db = db.execute(
            select(Material).where(Material.material_type == "paper")
        ).scalars().first()
        assert paper_in_db is not None

        # Test the port lookup get
        paper = product_ports.get_paper_master(paper_master_id=paper_in_db.id, db=db)
        assert paper.paper_master_id == paper_in_db.id
        assert paper.display_name == paper_in_db.name

        # Test the port lookup list
        papers = product_ports.list_paper_masters(db=db, q="couche")
        assert isinstance(papers, list)
        assert len(papers) >= 1
        assert any(p.paper_master_id == paper_in_db.id for p in papers)
    finally:
        db.close()
