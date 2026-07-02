"""Ports (interfaces) the Sản phẩm (Product catalog) screen DEPENDS ON — owned by
the consumer (`san_pham`) per DIP. Upstream module (Danh mục Giấy · `dm_giay_vat_tu`)
implements these later; until then each is an explicit NotImplementedError stub
(no silent fake values).

Seam registry (source of truth = these markers + the matching skip-test in
``backend/tests/test_seam_product.py``; ``docs/CROSS_MODULE_LINKS.md`` is only an index):

- SEAM-03: Sản phẩm ← Danh mục Giấy (PaperMaster, module ``dm_giay_vat_tu``).
  ``ProductComponent.paper_master_id`` (DOMAIN §34 L894) references a PaperMaster
  (§23 L530: khóa họ×gsm×khổ, time-versioned). The product-component editor needs
  to look up / list papers; the paper catalog implements this port later.

NOTE (Planner): the global ledger docs/CROSS_MODULE_LINKS.md registers this as the
next free ID SEAM-03. ``app/services/quotation_ports.py`` uses an UNREGISTERED local
SEAM-03/04/05 scheme (never entered in the ledger) — that collision needs reconciling
so ``grep -r SEAM-03`` stays unambiguous. This module keeps its markers scoped and
its test named ``test_seam_product`` to make the two greppable apart meanwhile.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


# --- SEAM-03: chờ dm_giay_vat_tu (PaperMaster) ------------------------------
@runtime_checkable
class PaperMasterLookupPort(Protocol):
    """Downstream (Sản phẩm) port. Danh mục Giấy (``dm_giay_vat_tu``) implements it later.

    ``ProductComponent.paper_master_id`` (§34 L894) points at a PaperMaster keyed by
    họ×gsm×khổ (§23 L530). The catalog screen never snapshots a paper price here —
    price snapshot happens at order-close (copy-on-write, P0 §34 L877). This port is
    read-only lookup for the component editor.
    """

    def get(self, paper_master_id: int) -> "PaperMasterRef":  # pragma: no cover
        ...

    def list(self, q: str | None = None) -> list["PaperMasterRef"]:  # pragma: no cover
        ...


class PaperMasterRef:  # pragma: no cover - contract shape only, filled by dm_giay_vat_tu
    """``{ paper_master_id, family, gsm, sheet_w_cm, sheet_h_cm, display_name }`` (read-only)."""


def get_paper_master(paper_master_id: int) -> PaperMasterRef:
    # SEAM-03: chờ dm_giay_vat_tu (PaperMaster — Danh mục Giấy, chưa build)
    raise NotImplementedError("SEAM-03 chưa back-fill")


def list_paper_masters(q: str | None = None) -> list[PaperMasterRef]:
    # SEAM-03: chờ dm_giay_vat_tu (PaperMaster — Danh mục Giấy, chưa build)
    raise NotImplementedError("SEAM-03 chưa back-fill")
