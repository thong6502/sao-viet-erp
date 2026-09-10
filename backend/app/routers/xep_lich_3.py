"""Router Xếp lịch 3 — bàn xếp lịch cấp LỆNH SẢN XUẤT.

Prefix `/api/xep-lich-3`. RBAC MODULE RIÊNG = "xep_lich_3" (mg 0292 chép quyền từ `xep_lich_2`).

Luồng gọn hơn màn 2 đúng một bậc: thẻ ở `/hang-cho` → `PUT /lenh/{id}` đặt hoặc dời mốc bắt đầu
(khóa lạc quan theo `updated_at` → 409) → `POST /phat-hanh/{id}`. KHÔNG có bước "đưa vào nháp",
KHÔNG có `xem-truoc`, KHÔNG có `kiem-phat-hanh`: màn này không chặn gì hết, xem trước chính là
thanh trên lưới, và phát hành bấm là đi.

Router CHỈ điều phối + kiểm quyền + đẩy SSE. Mọi luật nằm ở `services/xep_lich_3`.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.user import User
from ..realtime import hub
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.xep_lich_lenh_repo import XepLichLenhRepository
from ..schemas.xep_lich_3 import ChiTietOut, DatMocIn, DongLichOut, HangChoOut, LichOut
from ..services.xep_lich_3 import (
    XepLich3Conflict,
    XepLich3Error,
    XepLich3NotFound,
    XepLich3Service,
)
from ..services.xep_lich_service import (
    XepLichConflict,
    XepLichNotFound,
    XepLichValidationError,
)

router = APIRouter(prefix="/api/xep-lich-3", tags=["xep-lich-3"])
MODULE = "xep_lich_3"


def _svc(db: Session) -> XepLich3Service:
    return XepLich3Service(db, XepLichLenhRepository(db), AuditLogRepository(db))


def _map(exc: Exception) -> HTTPException:
    """Ánh xạ lỗi nghiệp vụ sang HTTP. KHÔNG nuốt lỗi lạ — re-raise để 500 nổi lên đúng chỗ.

    Ba lớp lỗi của `xep_lich` (màn 2) cũng vào đây: `thu_hoi` đi đường chung `go_phat_hanh_lsx`,
    nó ném kiểu của nó. Bỏ sót là "thiếu lý do thu hồi" hiện thành 500 câm.
    """
    if isinstance(exc, XepLichNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, XepLichConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, XepLichValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, XepLich3Conflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, XepLich3NotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, XepLich3Error):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


# --- Đọc ---------------------------------------------------------------------
@router.get("/hang-cho", response_model=HangChoOut)
def hang_cho(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    tim: str | None = Query(None, description="Tìm theo mã / tên lệnh — lọc Ở MÁY CHỦ"),
    trang: int = Query(1, ge=1),
    moi_trang: int = Query(20, ge=1, le=200),
) -> dict:
    return _svc(db).hang_cho(tim=tim, trang=trang, cd_trang=moi_trang)


@router.get("/lich", response_model=LichOut)
def lich(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    tu: date = Query(..., description="Ngày ĐẦU cửa sổ"),
    den: date = Query(..., description="Ngày CUỐI cửa sổ"),
) -> dict:
    """Các lệnh CHẠM cửa sổ. `tu`/`den` BẮT BUỘC — không mở đường trải cả lịch sử (spec §4.1)."""
    if den < tu:
        raise HTTPException(status_code=400, detail="Cửa sổ không hợp lệ: ngày cuối trước ngày đầu.")
    return _svc(db).lich(tu=tu, den=den)


@router.get("/lenh/{lsx_id}", response_model=ChiTietOut)
def chi_tiet(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    try:
        return _svc(db).chi_tiet(lsx_id)
    except Exception as exc:
        raise _map(exc)


# --- Ghi ---------------------------------------------------------------------
@router.put("/lenh/{lsx_id}", response_model=DongLichOut)
def dat_moc(
    lsx_id: int,
    payload: DatMocIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    """Đặt / dời giờ bắt đầu. Mốc ngoài giờ chạy thì TRƯỢT + báo, không chặn."""
    try:
        ra = _svc(db).dat_moc(
            lsx_id, payload.bat_dau_at, payload.expected_updated_at, nguoi_id=user.id,
        )
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_3_changed", "lsx_id": lsx_id})
    return ra


@router.delete("/lenh/{lsx_id}", response_model=None)
def xoa_moc(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    """Bỏ lịch — thẻ quay lại hàng chờ."""
    try:
        _svc(db).xoa_moc(lsx_id, nguoi_id=user.id)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_3_changed", "lsx_id": lsx_id})
    return {"ok": True}


@router.post("/phat-hanh/{lsx_id}", response_model=None)
def phat_hanh(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> dict:
    """Phát hành xuống xưởng — BẤM LÀ ĐI, không hộp thoại, không cửa gác (spec §1)."""
    try:
        _svc(db).phat_hanh(lsx_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_3_changed", "lsx_id": lsx_id})
    hub.broadcast({"type": "lsx_changed"})
    return {"ok": True}


@router.delete("/phat-hanh/{lsx_id}", response_model=None)
def thu_hoi(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
    ly_do: str | None = Query(None, max_length=500),
) -> dict:
    try:
        _svc(db).thu_hoi(lsx_id, actor=user, ly_do=ly_do)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_3_changed", "lsx_id": lsx_id})
    hub.broadcast({"type": "lsx_changed"})
    return {"ok": True}
