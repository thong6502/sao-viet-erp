"""Enabling point for the Tài xế Object-Page delivery-history seam (spec-25-tai_xe).

Source of truth for the seam = the `# SEAM-25` marker in
app/ports/driver_delivery_port.py + the matching skip test here.
docs/CROSS_MODULE_LINKS.md is only an index.

NOTE: SEAM-01..24 were already claimed by earlier specs, so this driver delivery-history
seam takes 25 (SEAM-19 = driver→Nhân sự employee resolve, a different seam on the same
screen).

Back-fill DoD: make the skip test pass against the real Giao hàng (Delivery/Shipment)
provider, DELETE the stub, flip ⏳→✅ in the registry, then remove the skip marker below.
"""
from __future__ import annotations

import pytest

from app.ports.driver_delivery_port import default_driver_delivery_port


@pytest.mark.skip(reason="SEAM-25 Tài xế cần lịch sử chuyến giao của tài xế từ Giao hàng (Delivery/Shipment) — chưa build")
def test_seam_25_list_deliveries():
    port = default_driver_delivery_port()
    # After back-fill: a driver who ran trips returns their delivery refs (newest first).
    rows = port.list_deliveries(driver_id=1)
    assert isinstance(rows, list) and rows and rows[0]["shipment_id"] > 0


def test_seam_25_stub_raises():
    """The stub must raise, not silently return a fake delivery list/count (a fabricated
    trip count would violate the honesty rule on the driver Object-Page)."""
    port = default_driver_delivery_port()
    with pytest.raises(NotImplementedError, match="SEAM-25"):
        port.list_deliveries(driver_id=1)
    with pytest.raises(NotImplementedError, match="SEAM-25"):
        port.count_deliveries(driver_id=1)
