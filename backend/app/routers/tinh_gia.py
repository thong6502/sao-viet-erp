"""Router Tính giá thành — POST /api/tinh-gia/binh-bai (bình bài live).

Bình bài KHÔNG trạng thái: nhận khổ → trả số con + layout để FE vẽ sơ đồ.
Tính giá vốn đầy đủ đi qua phiếu (`phieu_tinh_gia` → `compute_phieu_snapshot`, engine
`thanh_phan_engine`). RBAC MODULE = "tinh_gia_thanh".
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.phieu_tinh_gia import PhieuTinhGia
from ..models.user import User
from ..schemas.phieu_tinh_gia import PhieuTinhGiaCreate
from ..services.thanh_phan_engine import binh_bai_layout, binh_bai_nghich
from ..services.tinh_gia_service import compute_phieu_snapshot
from .phieu_tinh_gia import _build_thanh_phan

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


class BinhBaiNghichIn(BaseModel):
    """Bình bài NGHỊCH — số con ĐÚNG N → khổ tờ in ít phế nhất (xả từ tờ giấy nguyên).

    Yêu cầu khổ giấy nguyên > 0 (mốc tính phế); caller KHÔNG gọi khi nguyên còn trống.
    """
    con: int = Field(ge=1)
    dai_thanh_pham: float = Field(ge=0)
    rong_thanh_pham: float = Field(ge=0)
    chua_mm: float = Field(default=0, ge=0)
    kho_nguyen_dai: float = Field(ge=0)
    kho_nguyen_rong: float = Field(ge=0)
    kho_may_dai: float = Field(default=0, ge=0)    # vùng in máy (nếu có) → ràng buộc trên
    kho_may_rong: float = Field(default=0, ge=0)


@router.post("/binh-bai-nghich")
def binh_bai_nghich_api(
    payload: BinhBaiNghichIn,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Cho số con → khổ tờ in ít phế nhất khi xả từ tờ giấy nguyên. `con`=0 trong kết quả nghĩa
    là KHÔNG xếp được đúng N mà lọt tờ nguyên (FE báo đỏ, giữ nguyên khổ hiện tại)."""
    return binh_bai_nghich(
        con=payload.con, dai_tp=payload.dai_thanh_pham, rong_tp=payload.rong_thanh_pham,
        chua_mm=payload.chua_mm, kho_nguyen_dai=payload.kho_nguyen_dai,
        kho_nguyen_rong=payload.kho_nguyen_rong,
        kho_may_dai=payload.kho_may_dai, kho_may_rong=payload.kho_may_rong,
    )


@router.post("/preview")
def preview(
    payload: PhieuTinhGiaCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Xem-trước LIVE: chạy ĐÚNG engine (`compute_phieu_snapshot`) trên dữ liệu phiếu CHƯA lưu →
    trả `result` đầy đủ (mỗi thành phần: con, tờ vào máy/sau in, bù hao tự, kẽm, giá vốn). KHÔNG ghi DB.

    An toàn: KHÔNG `db.add` phiếu (transient), session autoflush=False → không insert; `rollback` cuối
    dọn sạch mọi thao tác đọc/resolve. Chỉ đọc danh mục (giấy/công đoạn/vật tư/bù hao)."""
    phieu = PhieuTinhGia(ma="__preview__", so_luong=int(payload.so_luong or 0))
    for i, tp_in in enumerate(payload.thanh_phans or []):
        phieu.thanh_phans.append(_build_thanh_phan(tp_in, i))
    result = compute_phieu_snapshot(db, phieu)
    db.rollback()
    return result
