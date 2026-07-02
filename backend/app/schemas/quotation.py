"""Pydantic request/response models for the Báo giá (Quotation) API — spec-09.

Field constraints here are the first line of validation (422 shape); QuotationService
enforces the domain rules (amounts ≥ 0, discount ≤ cost+margin, valid_until ≥ today, edit
only when draft, transition legality, approver permission, optimistic lock). The buildup
(số con/khổ, số tờ, số bản kẽm, bù hao) is NEVER part of any response shape here (tài liệu
đối ngoại, L1132/L1218).
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- create / update (draft only) ---------------------------------------------

class QuotationCreate(BaseModel):
    # SEAM-14 (CRM): the customer; nullable so a draft can start unassigned.
    customer_id: int | None = None
    # SEAM-13 (Tính giá): the referenced costing result; nullable while chọn Tính giá.
    costing_id: int | None = None
    # Giá vốn (1 số) read off Tính giá. Optional at draft; None → total shows "—".
    cost_von_total: int | None = None
    margin: int = Field(default=0)          # lãi (service enforces ≥ 0)
    discount: int = Field(default=0)        # chiết khấu (≥ 0, ≤ cost+margin)
    valid_until: date | None = None


class QuotationUpdate(QuotationCreate):
    """Same shape + the optimistic-locking row_version (mã/version are never client-set)."""

    row_version: int = Field(default=1)


class TransitionRequest(BaseModel):
    """Move a quotation to `to_status` (send/approve/reject/hold/resume/expire/cancel)."""

    to_status: str = Field(min_length=1, max_length=16)
    cancel_reason: str | None = Field(default=None, max_length=500)
    row_version: int | None = None


# --- outputs ------------------------------------------------------------------

class CustomerDisplayOut(BaseModel):
    """Read-only customer display resolved via SEAM-14 (CRM). NOT a block gate."""

    customer_id: int
    name: str
    tax_code: str | None = None
    credit_status_display: str


class QuotationRow(BaseModel):
    """A row in the Danh sách list: mã+version, khách, tổng giá bán, status, valid_until."""

    id: int
    code: str
    version: int
    customer_id: int | None
    customer_name: str | None = None
    total: int | None
    status: str
    valid_until: date | None


class QuotationListOut(BaseModel):
    items: list[QuotationRow]
    total: int
    page: int
    size: int


class VersionRow(BaseModel):
    """A row in the version-history panel (F4)."""

    id: int
    version: int
    status: str
    total: int | None
    created_at: datetime


class QuotationDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    version: int
    customer_id: int | None
    customer: CustomerDisplayOut | None = None
    costing_id: int | None
    cost_von_total: int | None
    margin: int
    discount: int
    total: int | None
    valid_until: date | None
    status: str
    cancel_reason: str | None
    cancelled_at_state: str | None
    # P0 snapshot (internal — shown in the detail but ẩn khỏi PDF đối ngoại).
    unit_price_snapshot: dict | None
    norm_snapshot: dict | None
    price_effective_from: date | None
    price_effective_to: date | None
    row_version: int
    # Legal next transitions for the current status + whether the caller may approve.
    allowed_transitions: list[str] = Field(default_factory=list)
    can_approve: bool = False
    versions: list[VersionRow] = Field(default_factory=list)


class EnumOption(BaseModel):
    value: str
    label: str


class QuotationEnumsOut(BaseModel):
    statuses: list[EnumOption]


class CostingQtyOption(BaseModel):
    """One quantity point (bậc SL) of the referenced Tính giá."""

    quantity: int
    total_cost: int


class CostingPickerOut(BaseModel):
    """The Tính giá picker/read state (SEAM-13 — CLOSED). available=false + user-facing
    message when the estimate can't yield a frozen result (never a fabricated cost);
    otherwise cost_von_total of the chosen quantity point + all quantity points (bậc SL)."""

    available: bool
    message: str | None = None
    cost_von_total: int | None = None
    quantity: int | None = None
    options: list[CostingQtyOption] | None = None


__all__ = [
    "QuotationCreate",
    "QuotationUpdate",
    "TransitionRequest",
    "CustomerDisplayOut",
    "QuotationRow",
    "QuotationListOut",
    "VersionRow",
    "QuotationDetailOut",
    "EnumOption",
    "QuotationEnumsOut",
    "CostingQtyOption",
    "CostingPickerOut",
]
