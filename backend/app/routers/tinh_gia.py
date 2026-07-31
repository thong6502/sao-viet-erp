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
from ..services.thanh_phan_engine import binh_bai_layout, chua_theo_chieu
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
    chua_mm: float = Field(default=0, ge=0)   # chừa GỘP (mm) trừ mỗi chiều — dùng khi không tách chiều
    # Chừa TÁCH CHIỀU (ưu tiên hơn `chua_mm` khi gửi): dài ← nhíp giấy + đuôi; rộng ← lề hông ×2.
    chua_dai_mm: float | None = Field(default=None, ge=0)
    chua_rong_mm: float | None = Field(default=None, ge=0)
    # Hoặc gửi thẳng CHỪA THÔ của phiếu/quy cách lệnh — server tự tách chiều bằng `chua_theo_chieu`
    # (nhíp đè trên phiếu + nhíp/lề hông/đuôi của máy). Nơi gọi khỏi tự cộng: cộng tay ở màn thứ
    # hai chính là chỗ đẻ ra sơ đồ 105 con trong khi phiếu ra 99.
    chua_nhip: float | None = Field(default=None, ge=0)
    nhip_giay_mm: float | None = Field(default=None, ge=0)
    le_hong_mm: float | None = Field(default=None, ge=0)
    duoi_thang_mau_mm: float | None = Field(default=None, ge=0)
    bleed_mm: float = Field(default=0, ge=0)    # tràn lề mỗi cạnh con
    khe_cat_mm: float = Field(default=0, ge=0)  # khe giữa 2 con kề nhau


@router.post("/binh-bai")
def binh_bai(
    payload: BinhBaiIn,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Bình bài live: trả số con + LAYOUT (cols/rows/rotated/usable) để FE vẽ sơ đồ đúng engine + hiệu suất."""
    chua_d, chua_r = payload.chua_dai_mm, payload.chua_rong_mm
    tho = {k: v for k, v in payload.model_dump().items()
           if k in ("chua_nhip", "nhip_giay_mm", "le_hong_mm", "duoi_thang_mau_mm")
           and v is not None}
    if chua_d is None and chua_r is None and tho:
        chua_d, chua_r = chua_theo_chieu(tho)
    lay = binh_bai_layout(
        kho_in_dai=payload.kho_in_dai, kho_in_rong=payload.kho_in_rong,
        dai_tp=payload.dai_thanh_pham, rong_tp=payload.rong_thanh_pham, chua_mm=payload.chua_mm,
        chua_dai_mm=chua_d, chua_rong_mm=chua_r,
        bleed_mm=payload.bleed_mm, khe_cat_mm=payload.khe_cat_mm,
    )
    dt_tp = payload.dai_thanh_pham * payload.rong_thanh_pham
    dt_in = payload.kho_in_dai * payload.kho_in_rong
    hieu_suat = round(lay["con"] * dt_tp / dt_in * 100, 1) if dt_in > 0 else 0.0
    return {**lay, "hieu_suat": hieu_suat}


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
