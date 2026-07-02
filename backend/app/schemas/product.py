"""Pydantic request/response models for the Sản phẩm in (Product catalog) API — spec-07.

Field-level constraints here are the first line of validation (422 shape); the service
enforces the domain rules (name non-blank + unique, enum membership, tay-sách %4, colors
0..8, khổ>0, ≥1 component for a bound product).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ComponentIn(BaseModel):
    """One ProductComponent row on create/update (§34 L893–894)."""

    component_type: str = Field(min_length=1, max_length=16)
    # SEAM-03: FK-nullable to PaperMaster — may be null until Danh mục Giấy is built.
    paper_master_id: int | None = None
    colors_front: int = Field(default=0, ge=0, le=8)
    colors_back: int = Field(default=0, ge=0, le=8)
    page_count: int = Field(default=0, ge=0)
    finished_w: float = Field(default=0)
    finished_h: float = Field(default=0)
    bleed: float = Field(default=0, ge=0)
    grain_direction: str | None = Field(default=None, max_length=8)
    sequence: int = Field(default=0)


class ComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sequence: int
    component_type: str
    paper_master_id: int | None
    # Resolved paper label via SEAM-03; None until Danh mục Giấy is built.
    paper_display: str | None = None
    colors_front: int
    colors_back: int
    page_count: int
    finished_w: float
    finished_h: float
    bleed: float
    grain_direction: str | None


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    product_type: str = Field(min_length=1, max_length=32)
    binding_type: str | None = Field(default=None, max_length=16)
    note: str | None = Field(default=None, max_length=1000)
    components: list[ComponentIn] = Field(default_factory=list)


class ProductUpdate(ProductCreate):
    """Same shape as create; mã is read-only and never sent."""


class ProductRow(BaseModel):
    """A row in the Danh mục list: mã (chỉ-đọc), tên, loại SP, kiểu đóng, số cấu phần."""

    id: int
    code: str
    name: str
    product_type: str
    binding_type: str | None
    component_count: int


class ProductListOut(BaseModel):
    items: list[ProductRow]
    total: int
    page: int
    size: int


class ProductDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    product_type: str
    binding_type: str | None
    note: str | None
    components: list[ComponentOut]


class PaperPickerOut(BaseModel):
    """The paper picker state (SEAM-03). When Danh mục Giấy is not built, `available` is
    False + `message` explains it — the UI shows "Danh mục Giấy chưa sẵn sàng", NEVER a
    fabricated paper list."""

    available: bool
    message: str | None = None
    items: list[dict] = Field(default_factory=list)


class EnumOption(BaseModel):
    value: str
    label: str


class ProductEnumsOut(BaseModel):
    """Enum vocab for the form selects (loại SP, kiểu đóng, loại cấu phần, canh thớ)."""

    product_types: list[EnumOption]
    binding_types: list[EnumOption]
    component_types: list[EnumOption]
    grain_directions: list[EnumOption]


__all__ = [
    "ComponentIn",
    "ComponentOut",
    "ProductCreate",
    "ProductUpdate",
    "ProductRow",
    "ProductListOut",
    "ProductDetailOut",
    "PaperPickerOut",
    "EnumOption",
    "ProductEnumsOut",
]
