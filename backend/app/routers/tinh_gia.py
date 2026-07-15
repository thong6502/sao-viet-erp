"""Router Tính giá thành (engine MỚI) — POST /api/tinh-gia/preview.

Máy tính giá KHÔNG trạng thái: nhận cấu hình → gọi `services.tinh_gia_service.load_and_compute`
(load Giấy · Kẽm · Công đoạn · Bù hao rồi chạy engine thuần). RBAC MODULE = "tinh_gia_thanh".

Dependency INLINE (không đụng deps.py) — khớp convention module rebuild (cong_doan.py).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.user import User
from ..services.thanh_phan_engine import binh_bai_layout
from ..services.tinh_gia_service import load_and_compute

router = APIRouter(prefix="/api/tinh-gia", tags=["tinh-gia"])
MODULE = "tinh_gia_thanh"


class BinhBaiIn(BaseModel):
    """Bình bài live — tính số con/tờ từ khổ tờ in ② + khổ thành phẩm ③ (mm)."""
    kho_in_dai: float = Field(ge=0)
    kho_in_rong: float = Field(ge=0)
    dai_thanh_pham: float = Field(ge=0)
    rong_thanh_pham: float = Field(ge=0)
    chua_mm: float = Field(default=0, ge=0)   # tổng chừa (mm) trừ mỗi chiều


@router.post("/binh-bai")
def binh_bai(
    payload: BinhBaiIn,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Bình bài live: trả số con + LAYOUT (cols/rows/rotated/usable) để FE vẽ sơ đồ đúng engine + hiệu suất."""
    lay = binh_bai_layout(
        kho_in_dai=payload.kho_in_dai, kho_in_rong=payload.kho_in_rong,
        dai_tp=payload.dai_thanh_pham, rong_tp=payload.rong_thanh_pham, chua_mm=payload.chua_mm,
    )
    dt_tp = payload.dai_thanh_pham * payload.rong_thanh_pham
    dt_in = payload.kho_in_dai * payload.kho_in_rong
    hieu_suat = round(lay["con"] * dt_tp / dt_in * 100, 1) if dt_in > 0 else 0.0
    return {**lay, "hieu_suat": hieu_suat}


class PreviewIn(BaseModel):
    qty: int = Field(gt=0)
    pieces_per_sheet: int = Field(default=1, ge=1)
    so_mau: int = Field(default=4, ge=0)
    so_mat: int = Field(default=1, ge=1)
    so_con: int = Field(default=1, ge=1)
    giay_id: int | None = None
    kem: float | None = None                       # ép đơn giá kẽm; None → tự tra VatTuInAn
    loai_san_pham_id: int | None = None
    cong_doan_ids: list[int] | None = None
    dt_to_in_cm2: float = 0
    dt_thanh_pham_cm2: float = 0


@router.post("/preview")
def preview(
    payload: PreviewIn,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    result, _resolved = load_and_compute(
        db,
        qty=payload.qty,
        pieces_per_sheet=payload.pieces_per_sheet,
        so_mau=payload.so_mau,
        so_mat=payload.so_mat,
        so_con=payload.so_con,
        giay_id=payload.giay_id,
        kem=payload.kem,
        loai_san_pham_id=payload.loai_san_pham_id,
        cong_doan_ids=payload.cong_doan_ids,
        dt_to_in_cm2=payload.dt_to_in_cm2,
        dt_thanh_pham_cm2=payload.dt_thanh_pham_cm2,
    )
    return result
