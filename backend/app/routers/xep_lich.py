"""Router Xếp lịch công đoạn — bàn xếp lịch của bộ phận Kế hoạch sản xuất.

Prefix `/api/xep-lich`. RBAC MODULE = "san_xuat".

Luồng: LSX / bài ghép `san_sang` nằm ở `/hang-cho` → `POST /dua-vao/...` sinh dòng lịch (khóa routing)
→ bảng `/dong` gom theo máy/lệnh/bài ghép → `PUT /dong/{id}/gan` gán máy/ca/giờ (hệ tính giờ kết thúc +
xung đột) → khóa/gỡ. Máy chỉ ghi nhận; người kế hoạch quyết.
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
from ..repositories.xep_lich_repo import XepLichRepository
from ..schemas.xep_lich import (
    GanIn,
    GanLoatIn,
    GoiYOut,
    HangChoOut,
    KhoaIn,
    LichNenMayOut,
    PhatHanhOut,
    SanSangOut,
    VanDeActionIn,
    VanDeGhiChuIn,
    VanDeGiaoIn,
    VanDeListOut,
    VanDeNgoaiLeIn,
    VanDeStateOut,
    VungKhoaIn,
    VungKhoaItemOut,
    VungKhoaListOut,
    XemTruocIn,
    XemTruocOut,
    XepLichDongListOut,
    XepLichDongOut,
)
from ..services.xep_lich_service import (
    XepLichConflict,
    XepLichNotFound,
    XepLichService,
    XepLichValidationError,
)
from ..services.xep_lich_van_de_service import XepLichVanDeService

router = APIRouter(prefix="/api/xep-lich", tags=["xep-lich"])
MODULE = "san_xuat"


def _svc(db: Session) -> XepLichService:
    return XepLichService(db, XepLichRepository(db), AuditLogRepository(db))


def _svc_vd(db: Session) -> XepLichVanDeService:
    return XepLichVanDeService(db, AuditLogRepository(db))


def _vd_state_out(row) -> VanDeStateOut:
    return VanDeStateOut(
        issue_key=row.issue_key, trang_thai=row.trang_thai,
        assigned_to=row.assigned_to, note=row.note, tai_phat=row.tai_phat,
    )


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, XepLichNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, XepLichConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, XepLichValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


def _dong_out(svc: XepLichService, dong_id: int) -> XepLichDongOut:
    row = next((it for it in svc.danh_sach()["items"] if it["id"] == dong_id), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy dòng xếp lịch")
    return XepLichDongOut.model_validate(row)


# --- Hàng chờ + bảng --------------------------------------------------------
@router.get("/hang-cho", response_model=HangChoOut)
def hang_cho(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> HangChoOut:
    """Order-pool: LSX độc lập + bài ghép đã `san_sang` mà CHƯA đưa vào kế hoạch."""
    return HangChoOut.model_validate(_svc(db).hang_cho())


@router.get("/dong", response_model=XepLichDongListOut)
def danh_sach(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    may_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
) -> XepLichDongListOut:
    return XepLichDongListOut.model_validate(_svc(db).danh_sach(may_id=may_id, q=q))


# --- Đưa vào / gỡ kế hoạch --------------------------------------------------
@router.post("/dua-vao/lsx/{lsx_id}", status_code=status.HTTP_201_CREATED)
def dua_vao_lsx(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> dict:
    svc = _svc(db)
    try:
        svc.dua_vao_lsx(lsx_id=lsx_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "lsx_changed"})
    return {"ok": True}


@router.post("/dua-vao/bai-ghep/{bai_ghep_id}", status_code=status.HTTP_201_CREATED)
def dua_vao_bai_ghep(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> dict:
    svc = _svc(db)
    try:
        svc.dua_vao_bai_ghep(bai_ghep_id=bai_ghep_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "bai_ghep_changed"})
    return {"ok": True}


@router.delete("/lsx/{lsx_id}")
def go_lsx(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    svc = _svc(db)
    try:
        svc.go_lsx(lsx_id=lsx_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "lsx_changed"})
    return {"ok": True}


@router.delete("/bai-ghep/{bai_ghep_id}")
def go_bai_ghep(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    svc = _svc(db)
    try:
        svc.go_bai_ghep(bai_ghep_id=bai_ghep_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "bai_ghep_changed"})
    return {"ok": True}


# --- Gán / khóa dòng --------------------------------------------------------
@router.put("/dong/gan-loat", response_model=XepLichDongListOut)
def gan_loat(
    payload: GanLoatIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> XepLichDongListOut:
    svc = _svc(db)
    try:
        rows = [r.model_dump(exclude_unset=True) for r in payload.rows]
        done = svc.gan_loat(rows=rows, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    ids = {d.id for d in done}
    items = [it for it in svc.danh_sach()["items"] if it["id"] in ids]
    return XepLichDongListOut(
        items=[XepLichDongOut.model_validate(it) for it in items], total=len(items)
    )


@router.put("/dong/{dong_id}/gan", response_model=XepLichDongOut)
def gan(
    dong_id: int,
    payload: GanIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> XepLichDongOut:
    svc = _svc(db)
    try:
        svc.gan(dong_id=dong_id, patch=payload.model_dump(exclude_unset=True), actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    return _dong_out(svc, dong_id)


@router.post("/dong/{dong_id}/khoa", response_model=XepLichDongOut)
def khoa(
    dong_id: int,
    payload: KhoaIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> XepLichDongOut:
    svc = _svc(db)
    try:
        svc.khoa(dong_id=dong_id, khoa=payload.khoa, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    return _dong_out(svc, dong_id)


@router.post("/dong/{dong_id}/mo-khoa", response_model=XepLichDongOut)
def mo_khoa(
    dong_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> XepLichDongOut:
    svc = _svc(db)
    try:
        svc.khoa(dong_id=dong_id, khoa=False, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    return _dong_out(svc, dong_id)


@router.get("/dong/{dong_id}/goi-y", response_model=GoiYOut)
def goi_y(
    dong_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> GoiYOut:
    """Gợi ý máy trống sớm nhất + hạn lùi còn kịp giao. CHỈ ĐỌC (máy đề xuất, người quyết)."""
    svc = _svc(db)
    try:
        return GoiYOut.model_validate(svc.goi_y(dong_id=dong_id))
    except Exception as exc:
        raise _map(exc)


@router.post("/dong/{dong_id}/xem-truoc", response_model=XemTruocOut)
def xem_truoc(
    dong_id: int,
    payload: XemTruocIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> XemTruocOut:
    """Ảnh hưởng khi thả dòng vào (máy, giờ) trước khi xác nhận — KHÔNG commit, KHÔNG broadcast."""
    svc = _svc(db)
    try:
        return XemTruocOut.model_validate(
            svc.xem_truoc(dong_id=dong_id, may_id=payload.may_id, start_at=payload.start_at)
        )
    except Exception as exc:
        raise _map(exc)


# --- Lịch nền máy (Gantt) ---------------------------------------------------
@router.get("/may/{may_id}/lich-nen", response_model=LichNenMayOut)
def lich_nen(
    may_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    tu: date = Query(..., description="Ngày đầu dải xem"),
    den: date = Query(..., description="Ngày cuối dải xem"),
) -> LichNenMayOut:
    """Khoảng làm-việc theo ca + vùng khóa máy trong [tu, den] — Gantt vẽ nền + curtains. CHỈ ĐỌC."""
    return LichNenMayOut.model_validate(_svc(db).lich_nen_may(may_id=may_id, tu=tu, den=den))


# --- Vùng khóa máy (bảo trì/hỏng/nghỉ) — CRUD tối thiểu -----------------------
@router.get("/vung-khoa", response_model=VungKhoaListOut)
def vung_khoa_range(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    tu: date = Query(..., description="Ngày đầu dải"),
    den: date = Query(..., description="Ngày cuối dải"),
) -> VungKhoaListOut:
    """Mọi khoảng khóa (mọi máy) giao [tu, den] — Gantt overlay theo lane. CHỈ ĐỌC."""
    items = _svc(db).vung_khoa_range(tu=tu, den=den)
    return VungKhoaListOut(items=[VungKhoaItemOut.model_validate(x) for x in items])


@router.get("/may/{may_id}/vung-khoa", response_model=VungKhoaListOut)
def list_vung_khoa(
    may_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> VungKhoaListOut:
    items = _svc(db).list_vung_khoa(may_id=may_id)
    return VungKhoaListOut(items=[VungKhoaItemOut.model_validate(x) for x in items])


@router.post("/may/{may_id}/vung-khoa", response_model=VungKhoaItemOut, status_code=status.HTTP_201_CREATED)
def tao_vung_khoa(
    may_id: int,
    payload: VungKhoaIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> VungKhoaItemOut:
    svc = _svc(db)
    try:
        x = svc.tao_vung_khoa(may_id=may_id, tu=payload.tu, den=payload.den,
                              ly_do=payload.ly_do, note=payload.note, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    return VungKhoaItemOut.model_validate(x)


@router.delete("/vung-khoa/{pid}")
def xoa_vung_khoa(
    pid: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    svc = _svc(db)
    try:
        svc.xoa_vung_khoa(pid=pid, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    return {"ok": True}


# --- Vấn đề kế hoạch (xung đột & nguy cơ trễ) -------------------------------
@router.get("/van-de", response_model=VanDeListOut)
def van_de(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    severity: str | None = Query(default=None),
    category: str | None = Query(default=None),
    trang_thai: str | None = Query(default=None),
    lsx_id: int | None = Query(default=None),
    may_id: int | None = Query(default=None),
) -> VanDeListOut:
    """Danh sách xung đột & nguy cơ trễ (dẫn xuất lúc đọc) + tổng hợp theo mức. CHỈ ĐỌC."""
    return VanDeListOut.model_validate(
        _svc_vd(db).liet_ke(severity=severity, category=category, trang_thai=trang_thai,
                            lsx_id=lsx_id, may_id=may_id)
    )


@router.get("/san-sang-phat-hanh", response_model=SanSangOut)
def san_sang_phat_hanh(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> SanSangOut:
    """LSX/bài ghép đã lập kế hoạch + số xung đột CHẶN còn lại (0 = phát hành được)."""
    return SanSangOut.model_validate(_svc_vd(db).san_sang_phat_hanh())


@router.post("/van-de/tiep-nhan", response_model=VanDeStateOut)
def van_de_tiep_nhan(
    payload: VanDeActionIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> VanDeStateOut:
    row = _svc_vd(db).tiep_nhan(issue_key=payload.issue_key, actor=user)
    hub.broadcast({"type": "xep_lich_changed"})
    return _vd_state_out(row)


@router.post("/van-de/giao", response_model=VanDeStateOut)
def van_de_giao(
    payload: VanDeGiaoIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> VanDeStateOut:
    row = _svc_vd(db).giao(issue_key=payload.issue_key, user_id=payload.user_id, actor=user)
    hub.broadcast({"type": "xep_lich_changed"})
    return _vd_state_out(row)


@router.post("/van-de/ghi-chu", response_model=VanDeStateOut)
def van_de_ghi_chu(
    payload: VanDeGhiChuIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> VanDeStateOut:
    row = _svc_vd(db).ghi_chu(issue_key=payload.issue_key, note=payload.note, actor=user)
    hub.broadcast({"type": "xep_lich_changed"})
    return _vd_state_out(row)


@router.post("/van-de/danh-dau-xu-ly", response_model=VanDeStateOut)
def van_de_danh_dau_xu_ly(
    payload: VanDeActionIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> VanDeStateOut:
    row = _svc_vd(db).danh_dau_xu_ly(issue_key=payload.issue_key, actor=user)
    hub.broadcast({"type": "xep_lich_changed"})
    return _vd_state_out(row)


@router.post("/van-de/tam-hoan", response_model=VanDeStateOut)
def van_de_tam_hoan(
    payload: VanDeActionIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> VanDeStateOut:
    row = _svc_vd(db).tam_hoan(issue_key=payload.issue_key, actor=user)
    hub.broadcast({"type": "xep_lich_changed"})
    return _vd_state_out(row)


@router.post("/van-de/ngoai-le", response_model=VanDeStateOut)
def van_de_ngoai_le(
    payload: VanDeNgoaiLeIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> VanDeStateOut:
    """Chấp nhận ngoại lệ — cần quyền PHÁT (`can_approve`). Vấn đề kỹ thuật bất khả → 409."""
    svc = _svc_vd(db)
    try:
        row = svc.ngoai_le(issue_key=payload.issue_key, ly_do=payload.ly_do,
                           expires_at=payload.expires_at, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    return _vd_state_out(row)


# --- Phát hành kế hoạch (Released) — gate 0 xung đột Chặn ---------------------
@router.post("/phat-hanh/lsx/{lsx_id}", response_model=PhatHanhOut)
def phat_hanh_lsx(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> PhatHanhOut:
    svc = _svc_vd(db)
    try:
        lsx = svc.phat_hanh_lsx(lsx_id=lsx_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "lsx_changed"})
    return PhatHanhOut(id=lsx.id, ma=lsx.ma, trang_thai=lsx.trang_thai)


@router.post("/phat-hanh/bai-ghep/{bai_ghep_id}", response_model=PhatHanhOut)
def phat_hanh_bai_ghep(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> PhatHanhOut:
    svc = _svc_vd(db)
    try:
        bg = svc.phat_hanh_bai_ghep(bai_ghep_id=bai_ghep_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "bai_ghep_changed"})
    return PhatHanhOut(id=bg.id, ma=bg.ma, trang_thai=bg.trang_thai)


@router.delete("/phat-hanh/lsx/{lsx_id}", response_model=PhatHanhOut)
def go_phat_hanh_lsx(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> PhatHanhOut:
    svc = _svc_vd(db)
    try:
        lsx = svc.go_phat_hanh_lsx(lsx_id=lsx_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "lsx_changed"})
    return PhatHanhOut(id=lsx.id, ma=lsx.ma, trang_thai=lsx.trang_thai)


@router.delete("/phat-hanh/bai-ghep/{bai_ghep_id}", response_model=PhatHanhOut)
def go_phat_hanh_bai_ghep(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> PhatHanhOut:
    svc = _svc_vd(db)
    try:
        bg = svc.go_phat_hanh_bai_ghep(bai_ghep_id=bai_ghep_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "bai_ghep_changed"})
    return PhatHanhOut(id=bg.id, ma=bg.ma, trang_thai=bg.trang_thai)
