"""Danh mục nội quy: mọi tài khoản xem được; quyền thêm và xóa theo RBAC."""
from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status,
)

from ..deps import CurrentUser, get_noi_quy_service, get_user_repository, require_permission
from ..models.user import User
from ..repositories.user_repo import UserRepository
from ..schemas.noi_quy import NoiQuyRecordOut, NoiQuyRecordsOut
from ..services.noi_quy_service import (
    NoiQuyError,
    NoiQuyNotFound,
    NoiQuyService,
    NoiQuyValidationError,
)

router = APIRouter(prefix="/api/noi-quy", tags=["noi_quy"])
MODULE = "noi_quy"
MAX_FILE_BYTES = 20 * 1024 * 1024

Service = Annotated[NoiQuyService, Depends(get_noi_quy_service)]
Users = Annotated[UserRepository, Depends(get_user_repository)]
Creator = Annotated[User, Depends(require_permission(MODULE, "create"))]
Deleter = Annotated[User, Depends(require_permission(MODULE, "delete"))]


def _raise(exc: Exception) -> None:
    if isinstance(exc, NoiQuyNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, NoiQuyValidationError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _file_type(file_name: str, data: bytes) -> str:
    """Chỉ nhận loại trình duyệt xem trước trực tiếp và kiểm cả đuôi lẫn chữ ký file."""
    lower = file_name.lower()
    if lower.endswith(".pdf") and data[:1024].lstrip().startswith(b"%PDF-"):
        return "application/pdf"
    if lower.endswith(".png") and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")) and data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if (lower.endswith(".webp") and len(data) >= 12
            and data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
        return "image/webp"
    raise NoiQuyValidationError(
        "Chỉ nhận PDF, PNG, JPG/JPEG hoặc WebP hợp lệ để có thể xem trước."
    )


def _out(users: UserRepository, row) -> NoiQuyRecordOut:
    uploader = users.get_by_id(row.uploaded_by)
    uploader_name = (uploader.name or uploader.username) if uploader else "Người dùng đã xóa"
    return NoiQuyRecordOut(
        id=row.id,
        code=row.code,
        name=row.name,
        file_name=row.file_name,
        file_url=row.file_url,
        file_type=row.file_type,
        file_size=row.file_size,
        note=row.note,
        uploaded_by_user_id=row.uploaded_by,
        uploaded_by_name=uploader_name,
        uploaded_at=row.uploaded_at,
    )


@router.get("", response_model=NoiQuyRecordsOut)
def list_records(
    svc: Service,
    users: Users,
    user: CurrentUser,
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    # TRẦN 100: `_out` gọi `users.get_by_id` cho TỪNG dòng (N+1). Cỡ trang chuẩn của hệ là 20;
    # trần 100 để ai cần xuất/đối chiếu vẫn kéo được một mẻ lớn mà không mở cửa cho `size=100000`
    # kéo sập máy chủ bằng một lời gọi.
    size: int = Query(default=20, ge=1, le=100),
) -> NoiQuyRecordsOut:
    rows, total = svc.list_records(q=q, page=page, size=size)
    return NoiQuyRecordsOut(
        items=[_out(users, row) for row in rows], total=total, page=page, size=size,
    )


@router.post("", response_model=NoiQuyRecordOut, status_code=status.HTTP_201_CREATED)
async def create_record(
    svc: Service,
    users: Users,
    user: Creator,
    name: Annotated[str, Form(...)],
    note: Annotated[str | None, Form()] = None,
    file: UploadFile = File(...),
) -> NoiQuyRecordOut:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Tệp không được để trống.")
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="Tệp vượt quá 20 MB.")
    try:
        file_type = _file_type(file.filename or "", data)
        row = svc.create_record(
            name=name,
            note=note,
            file_name=file.filename or "tai-lieu",
            file_type=file_type,
            data=data,
            actor=user,
        )
    except NoiQuyError as exc:
        _raise(exc)
    return _out(users, row)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(record_id: int, svc: Service, user: Deleter) -> Response:
    try:
        svc.delete_record(record_id, actor=user)
    except NoiQuyError as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
