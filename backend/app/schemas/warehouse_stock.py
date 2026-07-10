"""Pydantic schemas — Kho P0 (StockLot + StockMove trên Material)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Lô tồn ------------------------------------------------------------------
class StockLotIn(BaseModel):
    material_id: int
    warehouse_id: int
    location: str | None = Field(default=None, max_length=60)
    ownership: str = "company"  # company | customer
    owner_customer_id: int | None = None
    order_id: int | None = None
    unit_cost: int | None = None
    supplier: str | None = Field(default=None, max_length=150)
    received_date: date | None = None
    expiry_date: date | None = None
    note: str | None = None
    is_active: bool = True


class StockLotRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    material_id: int
    warehouse_id: int
    location: str | None = None
    ownership: str
    owner_customer_id: int | None = None
    order_id: int | None = None
    unit_cost: int | None = None
    supplier: str | None = None
    received_date: date | None = None
    expiry_date: date | None = None
    note: str | None = None
    is_active: bool
    qty_on_hand: float = 0  # tính động từ StockMove


class StockLotListOut(BaseModel):
    items: list[StockLotRow]
    total: int
    page: int
    size: int


# --- Sổ cái ------------------------------------------------------------------
class StockMoveIn(BaseModel):
    material_id: int
    warehouse_id: int
    lot_id: int | None = None
    quantity: float = Field(description="Số lượng nhập vào (theo input_uom nếu có)")
    input_uom: str | None = Field(default=None, description="Đơn vị nhập (ream/kg…); trống = đơn vị tồn")
    move_type: str = "dieu_chinh"  # ton_dau_ky | nhap | xuat | dieu_chinh
    reason: str | None = Field(default=None, max_length=120)
    note: str | None = None


class StockMoveRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    material_id: int
    warehouse_id: int
    lot_id: int | None = None
    qty_delta: float
    unit: str
    move_type: str
    reason: str | None = None
    note: str | None = None
    created_by_user_id: int | None = None
    created_at: datetime


class StockMoveListOut(BaseModel):
    items: list[StockMoveRow]
    total: int
    page: int
    size: int


# --- Tồn tổng hợp ------------------------------------------------------------
class StockBalanceRow(BaseModel):
    material_id: int
    warehouse_id: int
    lot_id: int | None = None
    on_hand: float
    available: float = 0
    value: float = 0  # giá trị tồn (đồng); 0 nếu không có quyền xem giá vốn
    unit: str


class StockBalanceListOut(BaseModel):
    items: list[StockBalanceRow]
    total: int


# --- Option cho dropdown (gate `kho`, không cần quyền danh mục vật tư) --------
class MaterialOption(BaseModel):
    id: int
    code: str
    name: str
    unit: str


# --- Báo cáo Nhập–Xuất–Tồn (DacTa Table 7) ----------------------------------
class NxtRow(BaseModel):
    material_id: int
    warehouse_id: int
    unit: str
    opening: float
    in_qty: float
    out_qty: float
    closing: float
    # Giá trị (đồng) — 0 nếu không có quyền xem giá vốn.
    opening_value: float = 0
    in_value: float = 0
    out_value: float = 0
    closing_value: float = 0


class NxtReportOut(BaseModel):
    items: list[NxtRow]
    total: int
    date_from: str
    date_to: str


# --- Thẻ kho / Sổ chi tiết vật tư (chronological ledger) --------------------
class LedgerRow(BaseModel):
    move_id: int
    created_at: datetime
    move_type: str
    reason: str | None = None
    note: str | None = None
    lot_id: int | None = None
    warehouse_id: int
    qty_in: float
    qty_out: float
    balance: float  # tồn lũy kế sau dòng này
    unit_cost: float = 0  # 0 nếu không có quyền xem giá vốn
    value: float = 0  # giá trị dòng (qty_delta*unit_cost); 0 nếu không có quyền


class LedgerOut(BaseModel):
    material_id: int
    unit: str
    opening: float  # tồn đầu kỳ (trước date_from; 0 nếu không lọc ngày)
    closing: float  # tồn cuối
    total_in: float
    total_out: float
    opening_value: float = 0
    closing_value: float = 0
    items: list[LedgerRow]
    total: int
    date_from: str | None = None
    date_to: str | None = None


# --- Ngưỡng tồn tối thiểu + cảnh báo tồn thấp -------------------------------
class MinLevelIn(BaseModel):
    material_id: int
    warehouse_id: int
    min_qty: float = Field(ge=0)
    note: str | None = Field(default=None, max_length=120)


class MinLevelRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    material_id: int
    warehouse_id: int
    min_qty: float
    note: str | None = None


class MinLevelListOut(BaseModel):
    items: list[MinLevelRow]
    total: int


class LowStockRow(BaseModel):
    material_id: int
    warehouse_id: int
    min_qty: float
    on_hand: float
    shortfall: float  # thiếu bao nhiêu so với min (0 nếu đủ)
    below: bool
    note: str | None = None


class LowStockOut(BaseModel):
    items: list[LowStockRow]
    total: int


# --- Tồn theo vị trí ---------------------------------------------------------
class LocationStockRow(BaseModel):
    warehouse_id: int
    location: str
    material_id: int
    on_hand: float


class LocationStockOut(BaseModel):
    items: list[LocationStockRow]
    total: int
