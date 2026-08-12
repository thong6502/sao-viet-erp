"""Công đoạn router (module MỚI) — CRUD danh mục. Chưa đăng ký main.py (unwired).

Dependency INLINE (không đụng deps.py). MODULE quyền = "dm_cong_doan".
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission, require_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.cong_doan_repo import CongDoanRepository
from ..repositories.rbac_repo import DepartmentRepository
from ..schemas.cong_doan import CongDoanIn, CongDoanListOut, CongDoanRow, RefOption, RefOptionListOut
from ..services.cong_doan_service import (
    CongDoanDuplicate, CongDoanNotFound, CongDoanService, CongDoanValidationError,
)

router = APIRouter(prefix="/api/cong-doan", tags=["cong-doan"])
MODULE = "dm_cong_doan"


def get_service(db: Annotated[Session, Depends(get_db)]) -> CongDoanService:
    return CongDoanService(CongDoanRepository(db), AuditLogRepository(db))


Service = Annotated[CongDoanService, Depends(get_service)]


def _err(e: Exception):
    if isinstance(e, CongDoanNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, CongDoanDuplicate):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("", response_model=CongDoanListOut)
def list_items(
    svc: Service,
    # Danh mục THAM CHIẾU: đọc được nếu có quyền cấu hình Công đoạn HOẶC quyền Tính giá
    # (màn Tính giá cần đổ dropdown Công đoạn mà không phải mở màn cấu hình).
    _: Annotated[User, Depends(require_any_permission((MODULE, "read"), ("tinh_gia_thanh", "read")))],
    q: str | None = Query(default=None),
    nhom: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> CongDoanListOut:
    rows, total = svc.list(q=q, nhom=nhom, active=active, page=page, size=size)
    svc.gan_ten_don_vi(rows)   # tên đơn vị đọc từ danh mục — xem `gan_ten_don_vi`
    return CongDoanListOut(items=[CongDoanRow.model_validate(r) for r in rows], total=total, page=page, size=size)


@router.get("/phong-ban", response_model=RefOptionListOut)
def list_phong_ban_options(
    db: Annotated[Session, Depends(get_db)],
    # Đọc được nếu có quyền cấu hình Công đoạn HOẶC Tính giá (đổ dropdown 'Phòng ban phụ trách').
    _: Annotated[User, Depends(require_any_permission((MODULE, "read"), ("tinh_gia_thanh", "read")))],
) -> RefOptionListOut:
    """TỔ cho dropdown 'Phòng ban / Tổ phụ trách' ở form Công đoạn (field ref: {id, ma, ten}).

    Dùng ĐỊNH NGHĨA CHUNG `to_san_xuat()` = nút LÁ trong nhánh Khối Sản xuất (mục H). Trước đây
    endpoint này đổ CẢ CHA LẪN CON, nên người khai chọn được "Xưởng in" (một tầng giữa) làm tổ phụ
    trách — và quỹ giờ-người ở bàn xếp lịch đếm chồng quân số của chính tổ con.

    ⚠️ KHÔNG phá dữ liệu cũ: công đoạn đã trỏ nút cha thì GIỮ NGUYÊN giá trị đó, chỉ kèm nhãn
    "(không còn là tổ)" để người khai biết mà sửa dần. Không tự xoá, không chặn lưu, không đụng
    lệnh đang chạy — đổi định nghĩa mà đi dọn dữ liệu người ta là tự ý sửa số liệu vận hành.
    """
    repo = DepartmentRepository(db)
    tos = repo.to_san_xuat()
    items = [RefOption(id=d.id, ma=d.code, ten=d.name) for d in tos]
    # Giá trị CŨ còn đang được công đoạn dùng nhưng nay không còn là tổ → vẫn cho chọn lại, có nhãn.
    dang_dung = CongDoanRepository(db).department_ids_dang_dung()
    con_thieu = dang_dung - {d.id for d in tos}
    if con_thieu:
        for d in repo.list_all():
            if d.id in con_thieu:
                items.append(RefOption(id=d.id, ma=d.code, ten=f"{d.name} (không còn là tổ)"))
    return RefOptionListOut(items=items)


@router.get("/dau-viec")
def list_dau_viec_options(
    svc: Service,
    _: Annotated[User, Depends(require_any_permission((MODULE, "read"), ("luong", "read")))],
    department_id: int | None = Query(default=None),
):
    items = svc.dau_viec_options(department_id)
    return {"items": items, "total": len(items), "page": 1, "size": max(len(items), 1)}


@router.get("/{cd_id}", response_model=CongDoanRow)
def get_item(cd_id: int, svc: Service, _: Annotated[User, Depends(require_permission(MODULE, "read"))]):
    try:
        cd = svc.get(cd_id)
        svc.gan_ten_don_vi([cd])
        return CongDoanRow.model_validate(cd)
    except CongDoanNotFound as e:
        raise _err(e) from None


@router.post("", response_model=CongDoanRow, status_code=status.HTTP_201_CREATED)
def create_item(payload: CongDoanIn, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "create"))]):
    try:
        cd = svc.create(payload.model_dump(exclude_unset=True), actor_id=user.id)
        svc.gan_ten_don_vi([cd])
        return CongDoanRow.model_validate(cd)
    except (CongDoanDuplicate, CongDoanValidationError) as e:
        raise _err(e) from None


@router.put("/{cd_id}", response_model=CongDoanRow)
def update_item(cd_id: int, payload: CongDoanIn, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "update"))]):
    try:
        cd = svc.update(cd_id, payload.model_dump(exclude_unset=True), actor_id=user.id)
        svc.gan_ten_don_vi([cd])
        return CongDoanRow.model_validate(cd)
    except (CongDoanNotFound, CongDoanDuplicate, CongDoanValidationError) as e:
        raise _err(e) from None


@router.delete("/{cd_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(cd_id: int, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete(cd_id, actor_id=user.id)
    except CongDoanNotFound as e:
        raise _err(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
