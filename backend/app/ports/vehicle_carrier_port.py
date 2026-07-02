"""Port the Phương tiện vận chuyển (vehicles) catalog needs from a module that is
NOT built yet.

Per DIP: the *consumer* (Danh mục & Cấu hình · Phương tiện vận chuyển) OWNS this
interface; the *provider* (Cung ứng / thu_mua, the NCC vận chuyển thuê ngoài) implements
it later. Until then the default implementation is an explicit stub that raises — never a
silent fake value (a fake carrier record would make a rented vehicle look "linked" to a
supplier that does not exist, corrupting AP / Công nợ later). See docs/CROSS_MODULE_LINKS.md.

Why a seam and not a plain FK:
  A `vehicles.carrier_supplier_id` FK→thu_mua.id cannot be declared at P0 because the
  `thu_mua` (NCC) table does not exist yet — declaring the constraint now would point at a
  phantom table and break create_all / DDL. So `carrier_supplier_id` is a nullable Integer,
  indexed, with NO FK constraint (the "FK nullable" seam kind). Meanwhile `carrier_name`
  free-text is KEPT as a display fallback so the carrier's name is never lost while the seam
  is open. The FK is added when Cung ứng builds `thu_mua` (back-fill = add FK + close seam).

Seam parked here (SEAM-01..20 were claimed by earlier specs, so this takes 21):
  - SEAM-21  carrier resolve (a rented vehicle's nhà xe is an NCC) → Cung ứng (`thu_mua`)

Domain anchors: §15 L417 (vận chuyển nội bộ/thuê), §18 L461 (NCC vận chuyển = AP thật),
§42 L1202 (gia công/dịch vụ ngoài: Nợ 154/627 · Có 331).
"""
from __future__ import annotations

from typing import Optional, Protocol, TypedDict


class CarrierRef(TypedDict):
    """Read-only display of the NCC vận chuyển a rented vehicle is linked to."""

    name: str
    tax_code: Optional[str]


class VehicleCarrierPort(Protocol):
    """Resolve the NCC behind `vehicles.carrier_supplier_id`. Owned by Phương tiện,
    implemented by Cung ứng (module `thu_mua`) once it exists."""

    def get_carrier(self, carrier_supplier_id: int) -> Optional[CarrierRef]:
        """Return the carrier's display ref, or None if the id is unknown. Used to show
        'Nhà xe: <name>' on a rented vehicle; NOT for posting AP / bút toán."""
        ...


# --- Default stub (SEAM placeholder) ----------------------------------------
# This is the "chỗ nối". It MUST raise, not return a fake carrier value.

class _UnimplementedVehicleCarrier:
    def get_carrier(self, carrier_supplier_id: int) -> Optional[CarrierRef]:  # noqa: ARG002
        # SEAM-21: chờ Cung ứng · thu_mua (NCC vận chuyển thuê ngoài)
        raise NotImplementedError("SEAM-21 chưa back-fill")


def default_vehicle_carrier_port() -> VehicleCarrierPort:
    """Wired-in default until Cung ứng back-fills SEAM-21."""
    return _UnimplementedVehicleCarrier()
