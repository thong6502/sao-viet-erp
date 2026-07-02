"""Pydantic schemas for the Product Type Catalog API — spec-20/21.
"""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class ProductTypeCatalogCreate(BaseModel):
    product_type: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=100)
    calculation_strategy: str = Field(min_length=1, max_length=32)
    required_fields: list[str] | None = Field(default=None)
    default_operations: list[str] | None = Field(default=None)
    allowed_materials: list[str] | None = Field(default=None)
    compatible_technologies: list[str] | None = Field(default=None)
    is_active: bool = True

class ProductTypeCatalogUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    calculation_strategy: str = Field(min_length=1, max_length=32)
    required_fields: list[str] | None = Field(default=None)
    default_operations: list[str] | None = Field(default=None)
    allowed_materials: list[str] | None = Field(default=None)
    compatible_technologies: list[str] | None = Field(default=None)
    is_active: bool | None = Field(default=None)

class ProductTypeCatalogRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_type: str
    name: str
    calculation_strategy: str
    # List phải trả các mảng cấu hình: (1) để bảng hiển thị cột "Thuộc tính/Công nghệ",
    # (2) để form Sửa prefill đúng — nếu thiếu, Sửa sẽ ghi đè rỗng = mất cấu hình.
    required_fields: list[str] | None = None
    default_operations: list[str] | None = None
    allowed_materials: list[str] | None = None
    compatible_technologies: list[str] | None = None
    is_active: bool
    created_at: datetime

class ProductTypeCatalogListOut(BaseModel):
    items: list[ProductTypeCatalogRow]
    total: int
    page: int
    size: int

class ProductTypeCatalogDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_type: str
    name: str
    calculation_strategy: str
    required_fields: list[str] | None
    default_operations: list[str] | None
    allowed_materials: list[str] | None
    compatible_technologies: list[str] | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
