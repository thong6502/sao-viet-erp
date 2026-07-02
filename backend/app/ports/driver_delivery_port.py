"""Port the Tài xế (drivers) Object-Page needs from a module that is NOT built yet.

The ERP driver detail screen (spec-25-tai_xe) is a *hub*: its defining cross-module
panel is **"Chuyến giao gần đây"** — the deliveries this driver ran. That data lives in
**Giao hàng** (Delivery / Shipment / DeliveryNote + POD, §15 L415-422), which does not
exist at P0. Per DIP the *consumer* (Danh mục & Cấu hình · Tài xế) OWNS this interface;
the *provider* (Giao hàng) implements it later.

Until then the default implementation is an explicit stub that raises — never a silent
fake list (a fabricated "3 chuyến giao" would violate the honesty rule: a fake number is
worse than an honest "chờ phân hệ Giao hàng" gap; see docs/UI_DESIGN.md Part C + PART F).

Direction / ADP: the driver catalog does NOT hold a back-reference or FK to Shipment; the
future Giao hàng module references `driver_id`. Tài xế only READS delivery refs through
this port for display + drill-through — no cycle.

Seam parked here (SEAM-01..24 were claimed by earlier specs, so this delivery-history seam
takes 25):
  - SEAM-25  driver delivery history (recent shipments a driver ran) → Giao hàng (Delivery/Shipment)

Domain anchors: §15 L415-422 (Giao hàng: vận chuyển nội bộ/thuê → phiếu giao → POD ký nhận;
thực thể Delivery/Shipment/Carrier/DeliveryNote).
"""
from __future__ import annotations

from typing import List, Optional, Protocol, TypedDict


class DeliveryRef(TypedDict):
    """Read-only display of one delivery/shipment a driver ran (for the driver's
    'Chuyến giao gần đây' panel + drill-through). NOT for costing/payroll."""

    shipment_id: int
    delivery_no: str
    delivered_on: str          # ISO date of the trip
    order_code: str            # source order (drill-through target)
    customer_name: str
    status: str                # e.g. đang giao / đã giao / đổi-trả
    pod_signed: bool           # đã ký nhận (POD) chưa


class DriverDeliveryPort(Protocol):
    """List the deliveries behind a driver. Owned by Tài xế, implemented by Giao hàng
    (Delivery/Shipment) once it exists."""

    def list_deliveries(self, driver_id: int, limit: int = 20) -> List[DeliveryRef]:
        """Most-recent deliveries this driver ran (newest first). Empty list = a driver
        with no trips yet (a real, honest empty state — distinct from 'module not built',
        which the stub signals by raising)."""
        ...

    def count_deliveries(self, driver_id: int) -> int:
        """Total trips this driver ran — feeds the driver KPI + the 'số chuyến 12T' chart.
        MUST NOT be faked; raises until Giao hàng back-fills."""
        ...


# --- Default stub (SEAM placeholder) ----------------------------------------
# This is the "chỗ nối". It MUST raise, not return a fake delivery list/count.

class _UnimplementedDriverDelivery:
    def list_deliveries(self, driver_id: int, limit: int = 20) -> List[DeliveryRef]:  # noqa: ARG002
        # SEAM-25: chờ Giao hàng (Delivery/Shipment)
        raise NotImplementedError("SEAM-25 chưa back-fill")

    def count_deliveries(self, driver_id: int) -> int:  # noqa: ARG002
        # SEAM-25: chờ Giao hàng (Delivery/Shipment)
        raise NotImplementedError("SEAM-25 chưa back-fill")


def default_driver_delivery_port() -> DriverDeliveryPort:
    """Wired-in default until Giao hàng back-fills SEAM-25."""
    return _UnimplementedDriverDelivery()
