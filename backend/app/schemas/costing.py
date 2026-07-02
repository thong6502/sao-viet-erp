"""Pydantic request/response models for the Tính giá (Costing) API — spec-08.

Field-level constraints here are the first line of validation (422 shape); the service
enforces the domain rules (qty_final > 0, ≥1 phương án giấy, pieces_per_sheet > 0, enum
membership). Cost numbers (giá vốn, số tờ, đơn giá) are DEFERRED behind SEAM-07..12 and are
NOT part of the LÀM-NGAY response shapes.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PaperOptionIn(BaseModel):
    """One phương án giấy on create/update (Khối B)."""

    # SEAM-07: FK-nullable to PaperMaster — may be null until Danh mục Giấy is built.
    sheet_paper_master_id: int | None = None
    sheet_w: float = Field(default=0, ge=0)
    sheet_h: float = Field(default=0, ge=0)
    # Số con/khổ NHẬP TAY (>0 enforced in the service so we return the domain message).
    pieces_per_sheet: int = Field(default=0)
    grain_locked: bool = False
    selected: bool = False


class OperationIn(BaseModel):
    """One công đoạn gia công on create/update (Khối E)."""

    name: str = Field(min_length=1, max_length=255)
    execution_mode: str = Field(min_length=1, max_length=16)
    sequence: int = Field(default=0)


class CostingCreate(BaseModel):
    # SEAM-11: the product picked from Sản phẩm; nullable so a draft can start without it.
    product_id: int | None = None
    qty_final: int = Field(default=0)
    note: str | None = Field(default=None, max_length=1000)
    status: str | None = Field(default=None, max_length=16)
    paper_options: list[PaperOptionIn] = Field(default_factory=list)
    operations: list[OperationIn] = Field(default_factory=list)


class CostingUpdate(CostingCreate):
    """Same shape as create; mã is read-only and never sent."""


class PaperOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sheet_paper_master_id: int | None
    # Resolved paper label + price via SEAM-07; None until Danh mục Giấy is built.
    paper_display: str | None = None
    sheet_w: float
    sheet_h: float
    pieces_per_sheet: int
    grain_locked: bool
    selected: bool


class OperationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sequence: int
    name: str
    execution_mode: str


class CostingRow(BaseModel):
    """A row in the Danh sách list: mã (chỉ-đọc), SP, số lượng, nhãn phương án giấy, trạng thái.

    `total_cost` is null at P0 (giá vốn tổng needs SEAM-07..12); the UI shows "—" / "chưa
    sẵn sàng" rather than a fabricated number."""

    id: int
    code: str
    product_id: int | None
    qty_final: int
    paper_option_count: int
    status: str
    total_cost: float | None = None


class CostingListOut(BaseModel):
    items: list[CostingRow]
    total: int
    page: int
    size: int


class CostingDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    product_id: int | None
    qty_final: int
    status: str
    note: str | None
    paper_options: list[PaperOptionOut]
    operations: list[OperationOut]


class ProductPickerOut(BaseModel):
    """The Sản phẩm picker/read state (SEAM-11). When `san_pham` does not expose ProductRead
    the port raises → `available` False + `message` — the UI shows "Sản phẩm chưa sẵn sàng",
    NEVER fabricated cấu phần specs."""

    available: bool
    message: str | None = None
    product: dict | None = None


class SuggestPiecesIn(BaseModel):
    """Inputs for the parallel số-con/khổ suggestion (pure geometry, no seam)."""

    sheet_w: float
    sheet_h: float
    piece_w: float
    piece_h: float
    grain_locked: bool = False


class SuggestPiecesOut(BaseModel):
    """The suggestion result. `pieces` = 0 means giấy quá nhỏ / khổ SP lớn hơn tờ → the UI
    warns, never divides by zero. `message` explains a 0."""

    pieces: int
    message: str | None = None


class EnumOption(BaseModel):
    value: str
    label: str


class CostingEnumsOut(BaseModel):
    """Enum vocab for the form selects (trạng thái, hình thức thực hiện công đoạn)."""

    statuses: list[EnumOption]
    execution_modes: list[EnumOption]


class PaperCostPickerOut(BaseModel):
    """The paper-cost picker state (SEAM-07). available=false + message → "Danh mục Giấy chưa
    sẵn sàng"; NEVER a fabricated paper/price list."""

    available: bool
    message: str | None = None
    items: list[dict] = Field(default_factory=list)


__all__ = [
    "PaperOptionIn",
    "OperationIn",
    "CostingCreate",
    "CostingUpdate",
    "PaperOptionOut",
    "OperationOut",
    "CostingRow",
    "CostingListOut",
    "CostingDetailOut",
    "ProductPickerOut",
    "SuggestPiecesIn",
    "SuggestPiecesOut",
    "EnumOption",
    "CostingEnumsOut",
    "PaperCostPickerOut",
]
