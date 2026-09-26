"""Nhóm dùng chung (khối Kinh doanh) — liệt kê / gộp / sửa / xoá.

Gộp nhóm là quyết định "cho người này thấy dữ liệu của người kia" — cùng loại với việc CẤP
QUYỀN, nên gác bằng ô đã có `phong_ban:manage_permissions` thay vì đẻ ô quyền mới. Mọi thao
tác ghi vết: ai làm, lúc nào, với ai.

Nhóm chỉ tác động tới BỐN màn khối Kinh doanh và chỉ khi phạm vi của vai là "Của tôi" — xem
`repositories/org_scope.nhom_dung_chung_user_ids`.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.nhom_dung_chung import NhomDungChung
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.nhom_dung_chung_repo import NhomDungChungRepository, TenNhomTrung
from ..schemas.nhom_dung_chung import NhomCreate, NhomOut, NhomUpdate, ThanhVienOut

router = APIRouter(prefix="/api/nhom-dung-chung", tags=["nhom-dung-chung"])
MODULE = "phong_ban"

QuanTri = Annotated[User, Depends(require_permission(MODULE, "manage_permissions"))]


def _ra(repo: NhomDungChungRepository, nhom: NhomDungChung) -> NhomOut:
    return NhomOut(
        id=nhom.id,
        ten=nhom.ten,
        created_at=nhom.created_at,
        thanh_viens=[
            ThanhVienOut(user_id=uid, ho_ten=ho_ten, username=username)
            for uid, ho_ten, username in repo.thanh_viens(nhom.id)
        ],
    )


def _ten_nguoi(repo: NhomDungChungRepository, nhom_id: int) -> str:
    ten = [ho_ten for _, ho_ten, _ in repo.thanh_viens(nhom_id)]
    return ", ".join(ten) if ten else "(chưa có ai)"


@router.get("", response_model=list[NhomOut])
def list_items(
    db: Annotated[Session, Depends(get_db)],
    _: QuanTri,
) -> list[NhomOut]:
    repo = NhomDungChungRepository(db)
    return [_ra(repo, n) for n in repo.list_all()]


@router.post("", response_model=NhomOut, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: NhomCreate,
    db: Annotated[Session, Depends(get_db)],
    user: QuanTri,
) -> NhomOut:
    repo = NhomDungChungRepository(db)
    try:
        nhom = repo.create(ten=payload.ten, user_ids=payload.user_ids, actor_id=user.id)
    except TenNhomTrung:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Đã có nhóm tên “{payload.ten.strip()}”",
        )
    AuditLogRepository(db).create(
        actor_user_id=user.id,
        action="create_nhom_dung_chung",
        target=f"nhom_dung_chung:{nhom.id}",
        detail=f"Gộp nhóm dùng chung “{nhom.ten}”: {_ten_nguoi(repo, nhom.id)}",
    )
    return _ra(repo, nhom)


@router.patch("/{nhom_id}", response_model=NhomOut)
def update_item(
    nhom_id: int,
    payload: NhomUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: QuanTri,
) -> NhomOut:
    repo = NhomDungChungRepository(db)
    nhom = repo.get(nhom_id)
    if nhom is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm")
    truoc = _ten_nguoi(repo, nhom.id)
    try:
        repo.update(nhom, ten=payload.ten, user_ids=payload.user_ids, actor_id=user.id)
    except TenNhomTrung:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Đã có nhóm tên “{(payload.ten or '').strip()}”",
        )
    sau = _ten_nguoi(repo, nhom.id)
    AuditLogRepository(db).create(
        actor_user_id=user.id,
        action="update_nhom_dung_chung",
        target=f"nhom_dung_chung:{nhom.id}",
        detail=f"Sửa nhóm dùng chung “{nhom.ten}”: {truoc} → {sau}",
    )
    return _ra(repo, nhom)


@router.delete("/{nhom_id}")
def delete_item(
    nhom_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: QuanTri,
) -> dict:
    repo = NhomDungChungRepository(db)
    nhom = repo.get(nhom_id)
    if nhom is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm")
    ten, nguoi = nhom.ten, _ten_nguoi(repo, nhom.id)
    repo.delete(nhom)
    AuditLogRepository(db).create(
        actor_user_id=user.id,
        action="delete_nhom_dung_chung",
        target=f"nhom_dung_chung:{nhom_id}",
        detail=f"Xoá nhóm dùng chung “{ten}” (gồm: {nguoi})",
    )
    return {"ok": True}
