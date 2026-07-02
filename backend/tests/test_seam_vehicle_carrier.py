"""Enabling point for the Phương tiện vận chuyển (vehicles) cross-module seam
(spec-15-phuong-tien-van-chuyen).

Source of truth for the seam = the `# SEAM-21` marker in
app/ports/vehicle_carrier_port.py + the matching skip test here.
docs/CROSS_MODULE_LINKS.md is only an index.

NOTE: SEAM-01..20 were already claimed by earlier specs (19 = Tài xế→Nhân sự,
20 = Khoản mục chi phí→Kế toán), so this vehicle-carrier seam takes 21.

Back-fill DoD: make the skip test pass against the real `thu_mua` (NCC) provider,
DELETE the stub, add the real `vehicles.carrier_supplier_id` FK→thu_mua.id, flip
⏳→✅ in the registry, then remove the skip marker below.
"""
from __future__ import annotations

import pytest

from app.ports.vehicle_carrier_port import default_vehicle_carrier_port


@pytest.mark.skip(reason="SEAM-21 Phương tiện cần resolve nhà xe (carrier_supplier_id) từ Cung ứng (thu_mua/NCC) — chưa build")
def test_seam_21_carrier_lookup():
    port = default_vehicle_carrier_port()
    # After back-fill: a rented vehicle linked to a real NCC resolves its carrier ref.
    ref = port.get_carrier(carrier_supplier_id=1)
    assert ref is not None and ref["name"]


def test_seam_21_stub_raises():
    """The stub must raise, not silently return a fake carrier (would fake an NCC link
    and corrupt AP / Công nợ). The vehicle screen falls back to carrier_name free-text."""
    with pytest.raises(NotImplementedError, match="SEAM-21"):
        default_vehicle_carrier_port().get_carrier(carrier_supplier_id=1)
