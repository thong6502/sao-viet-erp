"""Ports (interfaces) the Tính giá (Costing) screen DEPENDS ON — owned by the consumer
(`tinh_gia`) per DIP. Each upstream module implements its port LATER; until then every
function is an explicit ``NotImplementedError`` stub carrying its exact SEAM id — NEVER a
silent fake value (spec-08 System statuses; docs/CROSS_MODULE_LINKS.md).

Source of truth for each seam = these ``# SEAM-NN`` markers + the matching skip-test in
``backend/tests/test_seam_tinh_gia.py``. ``docs/CROSS_MODULE_LINKS.md`` is only an index.
Back-filling an upstream module flips its ``test_seam_NN`` green (and the stub must then be
replaced by the real adapter).

Seams (spec-08 §Cross-module seams):
- **SEAM-07** — giá giấy: Tính giá ← Danh mục Giấy / Kho (`dm_giay_vat_tu`/`kho`).
- **SEAM-08** — đơn giá khoán nội bộ: Tính giá ← Tổ & Đầu việc / SX.
- **SEAM-09** — định mức & bù hao: Tính giá ← Định mức & Bù hao (Danh mục).
- **SEAM-10** — specs máy: Tính giá ← Thiết bị / Máy (`may_moc`).
- **SEAM-11** — đọc Sản phẩm + cấu phần: Tính giá ← Sản phẩm (`san_pham`, spec-07).
- **SEAM-12** — đơn giá NCC gia công: Tính giá ← Cung ứng / NCC (`thu_mua`).
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable


# --- SEAM-07: chờ dm_giay_vat_tu/kho (PaperCost) ---------------------------
@runtime_checkable
class PaperCostLookupPort(Protocol):
    """Downstream (Tính giá) port. Danh mục Giấy / Kho implements it later.

    Returns the **time-versioned** giá per-ram / per-kg + `lot_type` (nguyên_ram/lẻ/đầu_tấm)
    + `ownership` (customer → cost=0 nhưng vẫn trừ tồn — §43 #7) for a paper master at a date
    (§23 L530, §12 L361–362). Read-only pull; Tính giá never snapshots this.
    """

    def get_price(self, paper_master_id: int, at_date: date | None = None) -> dict:  # pragma: no cover
        ...


def get_paper_price(paper_master_id: int, at_date: date | None = None) -> dict:
    # SEAM-07: chờ dm_giay_vat_tu/kho (PaperCost)
    raise NotImplementedError("SEAM-07 chưa back-fill")


# --- SEAM-08: chờ To_DauViec (PieceRate) -----------------------------------
@runtime_checkable
class PieceRateLookupPort(Protocol):
    """Downstream (Tính giá) port. Tổ & Đầu việc (SX) implements it later.

    Returns the **versioned** đơn giá khoán nội bộ ``{unit, unit_price}`` for a công đoạn
    (execution_mode=internal) at a date (§41 L1137, §43 L1201–1202).
    """

    def get_rate(self, operation_key: str, at_date: date | None = None) -> dict:  # pragma: no cover
        ...


def get_piece_rate(operation_key: str, at_date: date | None = None) -> dict:
    # SEAM-08: chờ To_DauViec (PieceRate)
    raise NotImplementedError("SEAM-08 chưa back-fill")


# --- SEAM-09: chờ DinhMuc_BuHao (Norm) -------------------------------------
@runtime_checkable
class NormLookupPort(Protocol):
    """Downstream (Tính giá) port. Định mức & Bù hao (Danh mục) implements it later.

    Returns a **versioned** định mức value for ``norm_key`` (yield_rate / running_waste_pct /
    makeready_per_color_side) in a context at a date (§31b L788–793, §43 #3 L1207).
    """

    def get_norm(self, norm_key: str, context: dict | None = None, at_date: date | None = None) -> float:  # pragma: no cover
        ...


def get_norm(norm_key: str, context: dict | None = None, at_date: date | None = None) -> float:
    # SEAM-09: chờ DinhMuc_BuHao (Norm)
    raise NotImplementedError("SEAM-09 chưa back-fill")


# --- SEAM-10: chờ may_moc (MachineSpec) ------------------------------------
@runtime_checkable
class MachineSpecLookupPort(Protocol):
    """Downstream (Tính giá) port. Thiết bị / Máy (`may_moc`) implements it later.

    Returns ``{units_per_pass, max_sheet_w, max_sheet_h}`` for a machine — số đơn vị máy per
    pass drives ``số pass = ceil(đơn vị in / đơn vị máy)`` (§31c L797–800, §23 L534).
    """

    def get(self, machine_id: int) -> dict:  # pragma: no cover
        ...


def get_machine_spec(machine_id: int) -> dict:
    # SEAM-10: chờ may_moc (MachineSpec)
    raise NotImplementedError("SEAM-10 chưa back-fill")


# --- SEAM-11: chờ san_pham (ProductRead) -----------------------------------
@runtime_checkable
class ProductReadPort(Protocol):
    """Downstream (Tính giá) port. Sản phẩm (`san_pham`, spec-07) implements it later.

    Returns the product + its cấu phần (khổ TP, bleed, thớ, colors_front/back, số trang) so
    Khối A/B kéo specs về mà không nhập lại (§34 L893–894). ``san_pham`` is same-app but the
    domain contract still flows through this port (no direct model reach-across).
    """

    def get(self, product_id: int) -> dict:  # pragma: no cover
        ...


def get_product_for_costing(product_id: int) -> dict:
    # SEAM-11: chờ san_pham (ProductRead)
    raise NotImplementedError("SEAM-11 chưa back-fill")


# --- SEAM-12: chờ thu_mua (OutsourcePrice) ---------------------------------
@runtime_checkable
class OutsourcePriceLookupPort(Protocol):
    """Downstream (Tính giá) port. Cung ứng / NCC (`thu_mua`) implements it later.

    Returns the đơn giá NCC gia công (unit_price) for a công đoạn (execution_mode=outsourced)
    optionally per supplier at a date (§14 L389–390, §23 L538). Cost pool "Gia công" cộng cả
    internal (SEAM-08) + outsourced (this).
    """

    def get_rate(self, operation_key: str, supplier_id: int | None = None, at_date: date | None = None) -> float:  # pragma: no cover
        ...


def get_outsource_price(operation_key: str, supplier_id: int | None = None, at_date: date | None = None) -> float:
    # SEAM-12: chờ thu_mua (OutsourcePrice)
    raise NotImplementedError("SEAM-12 chưa back-fill")
