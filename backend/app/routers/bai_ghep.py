"""Router Bài ghép (print gang) — bàn của Kế hoạch: gom công đoạn in nhiều LSX chạy chung 1 tờ.

Prefix `/api/bai-ghep`. RBAC MODULE = "san_xuat" (tái dùng, không đẻ quyền mới).

Luồng: hàng chờ ghép (LSX sẵn sàng cùng giấy) → tick → `POST /` tạo bài nháp → kiểm tương thích +
chọn giấy/khổ chung + sửa số con/tờ + khai hao hụt → `POST /{id}/trang-thai` đánh dấu sẵn sàng.
"""
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
from ..repositories.bai_ghep_repo import BaiGhepRepository
from ..repositories.document_sequence_repo import DocumentSequenceRepository
from ..schemas.bai_ghep import (
    BaiGhepActivityItem,
    BaiGhepActivityOut,
    BaiGhepDetailOut,
    BaiGhepListItem,
    BaiGhepListOut,
    BaiGhepUpdateIn,
    BuocChungUpdateIn,
    GopBuocIn,
    HangChoGhepItem,
    HangChoGhepOut,
    SoDoOut,
    SuaThanhVienIn,
    TaoBaiGhepIn,
    ThemThanhVienIn,
    TrangThaiIn,
    UngVienGopIn,
    UngVienGopOut,
)
from ..services.actor_display import actor_labels
from ..services.bai_ghep_service import (
    BaiGhepConflict,
    BaiGhepNotFound,
    BaiGhepService,
    BaiGhepValidationError,
    BaiGhepVongPhuThuoc,
)
from ..services.sequence_service import SequenceService

router = APIRouter(prefix="/api/bai-ghep", tags=["bai-ghep"])
MODULE = "san_xuat"


def _svc(db: Session) -> BaiGhepService:
    return BaiGhepService(
        db,
        BaiGhepRepository(db),
        AuditLogRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
    )


def _map(exc: Exception) -> HTTPException:
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


def _detail(svc: BaiGhepService, bg: BaiGhep) -> BaiGhepDetailOut:
    return BaiGhepDetailOut.model_validate(svc.detail_dict(bg))


# --- Hàng chờ ghép -----------------------------------------------------------
@router.get("/hang-cho", response_model=HangChoGhepOut)
def hang_cho(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    giay_id: Annotated[int | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> HangChoGhepOut:
    items = _svc(db).hang_cho_ghep(giay_id=giay_id, q=q)
    return HangChoGhepOut(items=[HangChoGhepItem.model_validate(i) for i in items], total=len(items))


# --- Danh sách bài ghép ------------------------------------------------------
@router.get("", response_model=BaiGhepListOut)
def danh_sach(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> BaiGhepListOut:
    rows = _svc(db).list_rows()
    return BaiGhepListOut(items=[BaiGhepListItem.model_validate(r) for r in rows], total=len(rows))


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
    """Đồ thị của bài: N nhánh vào → MỘT node IN → N nhánh ra.

    DẪN XUẤT, không lưu cạnh nào — xem `docs/spec-bai-ghep-dag.md` §2.1.
    """
    svc = _svc(db)
    try:
        return SoDoOut.model_validate(svc.so_do(svc._get(bai_ghep_id)))
    except Exception as exc:
        raise _map(exc)


# --- Tạo / sửa ---------------------------------------------------------------
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
    hub.broadcast({"type": "bai_ghep_changed"})
    return _detail(svc, bg)


@router.put("/{bai_ghep_id}", response_model=BaiGhepDetailOut)
def sua(
    bai_ghep_id: int,
    payload: BaiGhepUpdateIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> BaiGhepDetailOut:
    svc = _svc(db)
    try:
        bg = svc.sua(bai_ghep_id=bai_ghep_id, patch=payload.model_dump(exclude_unset=True), actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "bai_ghep_changed"})
    return _detail(svc, bg)


# --- Thành viên --------------------------------------------------------------
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
    hub.broadcast({"type": "bai_ghep_changed"})
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
            bai_ghep_id=bai_ghep_id, thanh_vien_id=thanh_vien_id,
            so_con_tren_to=payload.so_con_tren_to, actor=user,
        )
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "bai_ghep_changed"})
    return _detail(svc, bg)


# --- Gộp / tách bước chạy chung ----------------------------------------------
# Cửa ghi DUY NHẤT của lớp đè. Điều kiện gộp chỉ là CÙNG CÔNG ĐOẠN — quy cách thì người dùng có
# nghiệp vụ đó, máy không phán hộ.
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
    hub.broadcast({"type": "bai_ghep_changed"})
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
    hub.broadcast({"type": "bai_ghep_changed"})
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
            bai_ghep_id=bai_ghep_id, gang_step_key=gang_step_key,
            patch=payload.model_dump(exclude_unset=True), actor=user,
        )
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "bai_ghep_changed"})
    return _detail(svc, bg)


@router.post("/{bai_ghep_id}/ung-vien-gop", response_model=UngVienGopOut)
def ung_vien_gop(
    bai_ghep_id: int,
    payload: UngVienGopIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> UngVienGopOut:
    """Đang chọn các bước này thì gộp thêm được bước nào — canvas hỏi TRƯỚC khi cho bấm Gộp."""
    svc = _svc(db)
    try:
        bg = svc._get(bai_ghep_id)
        return UngVienGopOut(ung_vien=svc.ung_vien_gop(bg, payload.step_keys))
    except Exception as exc:
        raise _map(exc)


@router.delete("/{bai_ghep_id}/thanh-vien/{thanh_vien_id}", response_model=BaiGhepDetailOut)
def bo_thanh_vien(
    bai_ghep_id: int,
    thanh_vien_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> BaiGhepDetailOut:
    svc = _svc(db)
    try:
        bg = svc.bo_thanh_vien(bai_ghep_id=bai_ghep_id, thanh_vien_id=thanh_vien_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "bai_ghep_changed"})
    return _detail(svc, bg)


# --- Trạng thái / xoá --------------------------------------------------------
@router.post("/{bai_ghep_id}/trang-thai", response_model=BaiGhepDetailOut)
def set_trang_thai(
    bai_ghep_id: int,
    payload: TrangThaiIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> BaiGhepDetailOut:
    svc = _svc(db)
    try:
        bg = svc.set_trang_thai(bai_ghep_id=bai_ghep_id, trang_thai=payload.trang_thai, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "bai_ghep_changed"})
    return _detail(svc, bg)


@router.delete("/{bai_ghep_id}")
def xoa(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    svc = _svc(db)
    try:
        svc.xoa(bai_ghep_id=bai_ghep_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "bai_ghep_changed"})
    return {"ok": True}


# --- Nhật ký -----------------------------------------------------------------
@router.get("/{bai_ghep_id}/activity", response_model=BaiGhepActivityOut)
def activity(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> BaiGhepActivityOut:
    rows = AuditLogRepository(db).list_by_target(f"bai_ghep:{bai_ghep_id}")
    labels = actor_labels(db, {r.actor_user_id for r in rows})
    items = [
        BaiGhepActivityItem(
            at=r.created_at, actor=labels.get(r.actor_user_id), action=r.action, detail=r.detail
        )
        for r in rows
    ]
    return BaiGhepActivityOut(items=items)
