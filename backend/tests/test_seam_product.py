"""Enabling-point test for the Sản phẩm (Product catalog) cross-module seam.

SOURCE OF TRUTH for the seam (together with the ``# SEAM-03`` markers in
``app/services/product_ports.py``). ``docs/CROSS_MODULE_LINKS.md`` is only an index.
Back-filling Danh mục Giấy (``dm_giay_vat_tu`` · PaperMaster) flips this test green
(and the stubs must then be removed).
"""
from __future__ import annotations

import pytest

from app.services import product_ports


@pytest.mark.skip(reason="SEAM-03 chờ dm_giay_vat_tu (PaperMaster)")
def test_seam_03_paper_master_lookup():
    # Back-fill: Danh mục Giấy resolves a PaperMaster for ProductComponent.paper_master_id.
    paper = product_ports.get_paper_master(paper_master_id=1)
    assert paper.paper_master_id is not None
    assert paper.display_name is not None
    papers = product_ports.list_paper_masters(q="couche")
    assert isinstance(papers, list)


def test_seam_03_stubs_raise_until_backfilled():
    """The stubs must fail loudly (never return a silent fake) while pending."""
    with pytest.raises(NotImplementedError, match="SEAM-03"):
        product_ports.get_paper_master(paper_master_id=1)
    with pytest.raises(NotImplementedError, match="SEAM-03"):
        product_ports.list_paper_masters(q="couche")
