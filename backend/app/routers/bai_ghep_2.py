"""API Bài ghép 2 - cùng tài nguyên/engine Bài ghép, khóa quyền riêng ``bai_ghep_2``."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.bai_ghep import BaiGhep
from ..models.user import User
from ..realtime import hub
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.bai_ghep_2_repo import BaiGhep2Repository
from ..repositories.document_sequence_repo import DocumentSequenceRepository
from ..schemas.bai_ghep import (
    BaiGhepActivityItem, BaiGhepActivityOut, BaiGhepDetailOut, BaiGhepListItem,
    BaiGhep2UpdateIn, BaiGhepListOut, BuocChungUpdateIn, GopBuocIn, HangChoGhepItem,
    HangChoGhepOut, SoDoOut, SuaThanhVienIn, TaoBaiGhepIn, ThemThanhVienIn, TrangThaiIn,
    NguoiPhuTrachOption, NguoiPhuTrachOptionsOut, UngVienGopIn, UngVienGopOut,
    VatTuHieuLucOut,
)
from ..services.actor_display import actor_labels
from ..services.bai_ghep_2_service import BaiGhep2Service
from ..services.bai_ghep_service import (
    BaiGhepConflict,
    BaiGhepNotFound,
    BaiGhepValidationError,
    BaiGhepVongPhuThuoc,
)
from ..services.ke_hoach_vat_tu_service import KeHoachVatTuService
from ..services.sequence_service import SequenceService
from .ke_hoach_vat_tu import get_service as get_material_service

router = APIRouter(prefix="/api/bai-ghep-2", tags=["bai-ghep-2"])
MODULE = "bai_ghep_2"


def _map(exc: Exception) -> HTTPException:
    """Lỗi nghiệp vụ của engine bài ghép → mã HTTP.

    Trước đây hàm này `import` từ `routers/bai_ghep.py` (màn cũ) — phụ thuộc NGƯỢC, xoá màn cũ là
    màn này gãy. Dời hẳn về đây ngày 18/08/2026 khi gỡ màn cũ. Engine (`bai_ghep_service`) vẫn
    dùng chung, chỉ lớp HTTP là của riêng màn này.
    """
    if isinstance(exc, BaiGhepNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    # Vòng phụ thuộc: trả CẢ chu trình lẫn nhân chứng, không chỉ câu chữ — canvas cần đúng cặp
    # bước mâu thuẫn để tô, chứ hiện mỗi dòng chữ thì người dùng phải tự dò.
    if isinstance(exc, BaiGhepVongPhuThuoc):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "loai": "vong_phu_thuoc",
                    "nut": exc.nut, "tu_tro": exc.tu_tro, "nhan_chung": exc.nhan_chung},
        )
    if isinstance(exc, BaiGhepConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, BaiGhepValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


def _svc(db: Session) -> BaiGhep2Service:
    return BaiGhep2Service(
        db,
        BaiGhep2Repository(db),
        AuditLogRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
    )


def _detail(svc: BaiGhep2Service, bg: BaiGhep) -> BaiGhepDetailOut:
    return BaiGhepDetailOut.model_validate(svc.detail_dict(bg))


def _changed() -> None:
    hub.broadcast({"type": "bai_ghep_changed"})


@router.get("/hang-cho", response_model=HangChoGhepOut)
def hang_cho(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    giay_id: Annotated[int | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> HangChoGhepOut:
    kq = _svc(db).hang_cho_ghep(giay_id=giay_id, q=q)
    return HangChoGhepOut(
        items=[HangChoGhepItem.model_validate(i) for i in kq["items"]],
        total=len(kq["items"]),
        so_giu_cho=kq["so_giu_cho"],
    )


@router.get("", response_model=BaiGhepListOut)
def danh_sach(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> BaiGhepListOut:
    rows = _svc(db).list_rows()
    return BaiGhepListOut(items=[BaiGhepListItem.model_validate(r) for r in rows], total=len(rows))


@router.get("/nguoi-phu-trach-options", response_model=NguoiPhuTrachOptionsOut)
def nguoi_phu_trach_options(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> NguoiPhuTrachOptionsOut:
    rows = _svc(db).nguoi_phu_trach_options()
    return NguoiPhuTrachOptionsOut(
        items=[NguoiPhuTrachOption.model_validate(row) for row in rows]
    )


@router.get("/{bai_ghep_id}", response_model=BaiGhepDetailOut)
def chi_tiet(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> BaiGhepDetailOut:
    svc = _svc(db)
    try:
        return _detail(svc, svc._get(bai_ghep_id))
    except Exception as exc:
        raise _map(exc)


@router.get("/{bai_ghep_id}/so-do", response_model=SoDoOut)
def so_do(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> SoDoOut:
    svc = _svc(db)
    try:
        return SoDoOut.model_validate(svc.so_do(svc._get(bai_ghep_id)))
    except Exception as exc:
        raise _map(exc)


@router.get("/{bai_ghep_id}/vat-tu-hieu-luc", response_model=VatTuHieuLucOut)
def vat_tu_hieu_luc(
    bai_ghep_id: int,
    vat_tu: Annotated[KeHoachVatTuService, Depends(get_material_service)],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> VatTuHieuLucOut:
    try:
        return VatTuHieuLucOut.model_validate(vat_tu.vat_tu_hieu_luc(bai_ghep_id))
    except Exception as exc:
        raise _map(exc)


@router.post("", response_model=BaiGhepDetailOut, status_code=status.HTTP_201_CREATED)
def tao(
    payload: TaoBaiGhepIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> BaiGhepDetailOut:
    svc = _svc(db)
    try:
        bg = svc.tao(lsx_ids=payload.lsx_ids, actor=user)
    except Exception as exc:
        raise _map(exc)
    _changed()
    return _detail(svc, bg)


@router.put("/{bai_ghep_id}", response_model=BaiGhepDetailOut)
def sua(
    bai_ghep_id: int,
    payload: BaiGhep2UpdateIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> BaiGhepDetailOut:
    svc = _svc(db)
    try:
        bg = svc.sua(
            bai_ghep_id=bai_ghep_id,
            patch=payload.model_dump(exclude_unset=True),
            actor=user,
        )
    except Exception as exc:
        raise _map(exc)
    _changed()
    return _detail(svc, bg)


@router.post("/{bai_ghep_id}/thanh-vien", response_model=BaiGhepDetailOut)
def them_thanh_vien(
    bai_ghep_id: int,
    payload: ThemThanhVienIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> BaiGhepDetailOut:
    svc = _svc(db)
    try:
        bg = svc.them_thanh_vien(bai_ghep_id=bai_ghep_id, lsx_ids=payload.lsx_ids, actor=user)
    except Exception as exc:
        raise _map(exc)
    _changed()
    return _detail(svc, bg)


@router.put("/{bai_ghep_id}/thanh-vien/{thanh_vien_id}", response_model=BaiGhepDetailOut)
def sua_thanh_vien(
    bai_ghep_id: int,
    thanh_vien_id: int,
    payload: SuaThanhVienIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> BaiGhepDetailOut:
    svc = _svc(db)
    try:
        bg = svc.sua_thanh_vien(
            bai_ghep_id=bai_ghep_id,
            thanh_vien_id=thanh_vien_id,
            so_con_tren_to=payload.so_con_tren_to,
            actor=user,
        )
    except Exception as exc:
        raise _map(exc)
    _changed()
    return _detail(svc, bg)


@router.delete("/{bai_ghep_id}/thanh-vien/{thanh_vien_id}", response_model=BaiGhepDetailOut)
def bo_thanh_vien(
    bai_ghep_id: int,
    thanh_vien_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> BaiGhepDetailOut:
    svc = _svc(db)
    try:
        bg = svc.bo_thanh_vien(
            bai_ghep_id=bai_ghep_id, thanh_vien_id=thanh_vien_id, actor=user,
        )
    except Exception as exc:
        raise _map(exc)
    _changed()
    return _detail(svc, bg)


@router.post("/{bai_ghep_id}/gop", response_model=BaiGhepDetailOut)
def gop_buoc(
    bai_ghep_id: int,
    payload: GopBuocIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> BaiGhepDetailOut:
    svc = _svc(db)
    try:
        bg = svc.gop(bai_ghep_id=bai_ghep_id, step_keys=payload.step_keys, actor=user)
    except Exception as exc:
        raise _map(exc)
    _changed()
    return _detail(svc, bg)


@router.delete("/{bai_ghep_id}/gop/{gang_step_key}", response_model=BaiGhepDetailOut)
def tach_buoc(
    bai_ghep_id: int,
    gang_step_key: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> BaiGhepDetailOut:
    svc = _svc(db)
    try:
        bg = svc.tach(bai_ghep_id=bai_ghep_id, gang_step_key=gang_step_key, actor=user)
    except Exception as exc:
        raise _map(exc)
    _changed()
    return _detail(svc, bg)


@router.put("/{bai_ghep_id}/gop/{gang_step_key}", response_model=BaiGhepDetailOut)
def lap_ke_hoach_buoc_chung(
    bai_ghep_id: int,
    gang_step_key: str,
    payload: BuocChungUpdateIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> BaiGhepDetailOut:
    svc = _svc(db)
    try:
        bg = svc.lap_ke_hoach_buoc_chung(
            bai_ghep_id=bai_ghep_id,
            gang_step_key=gang_step_key,
            patch=payload.model_dump(exclude_unset=True),
            actor=user,
        )
    except Exception as exc:
        raise _map(exc)
    _changed()
    return _detail(svc, bg)


@router.post("/{bai_ghep_id}/ung-vien-gop", response_model=UngVienGopOut)
def ung_vien_gop(
    bai_ghep_id: int,
    payload: UngVienGopIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> UngVienGopOut:
    svc = _svc(db)
    try:
        return UngVienGopOut(
            ung_vien=svc.ung_vien_gop(svc._get(bai_ghep_id), payload.step_keys)
        )
    except Exception as exc:
        raise _map(exc)


@router.post("/{bai_ghep_id}/trang-thai", response_model=BaiGhepDetailOut)
def set_trang_thai(
    bai_ghep_id: int,
    payload: TrangThaiIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> BaiGhepDetailOut:
    svc = _svc(db)
    try:
        bg = svc.set_trang_thai(
            bai_ghep_id=bai_ghep_id, trang_thai=payload.trang_thai, actor=user,
        )
    except Exception as exc:
        raise _map(exc)
    _changed()
    return _detail(svc, bg)


@router.delete("/{bai_ghep_id}")
def xoa(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> dict:
    try:
        _svc(db).xoa(bai_ghep_id=bai_ghep_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    _changed()
    return {"ok": True}


@router.get("/{bai_ghep_id}/activity", response_model=BaiGhepActivityOut)
def activity(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> BaiGhepActivityOut:
    rows = AuditLogRepository(db).list_by_target(f"bai_ghep:{bai_ghep_id}")
    labels = actor_labels(db, {r.actor_user_id for r in rows})
    return BaiGhepActivityOut(items=[
        BaiGhepActivityItem(
            at=r.created_at, actor=labels.get(r.actor_user_id), action=r.action, detail=r.detail,
        )
        for r in rows
    ])
