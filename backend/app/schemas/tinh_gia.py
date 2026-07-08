"""Schemas — Tính giá preview."""
from __future__ import annotations

from pydantic import BaseModel, Field


class QuoteConfig(BaseModel):
    overhead_cty_pct: float = 0.0
    kieu_lai: str = "markup_tren_von"          # markup_tren_von | margin_tren_gia_ban
    he_so_lai_pct: float = 0.0
    chiet_khau_pct: float = 0.0
    don_toi_thieu: float = 0.0
    vat_rate: float | None = None              # None ⇒ lấy theo Loại SP


class TinhGiaPreviewIn(BaseModel):
    loai_san_pham_id: int | None = None
    may_id: int
    giay_id: int
    so_luong: int = Field(gt=0)
    so_mau_truoc: int = 4
    so_mau_sau: int = 0
    rong_tp: float = Field(gt=0)               # khổ thành phẩm (mm)
    dai_tp: float = Field(gt=0)
    bleed_mm: float | None = None
    chi_phi_khac: float = 0.0                   # chế bản/proof/gói… (1 lần)
    quote: QuoteConfig | None = None


class TinhGiaPreviewOut(BaseModel):
    # Loose: engine trả dict breakdown; giữ field chính + cho phép thừa.
    model_config = {"extra": "allow"}
    gia_von: float
    gia_thanh: float
    gia_net: float
    vat: float
    gia_ban: float
    don_gia_ban: float
    moq_applied: bool = False
