"""Materials router — spec-20.

Đọc: list / detail / cost history. Ghi (MVP danh mục vật tư kho): tạo / sửa / bật-tắt
hoạt động — dùng lại service sẵn có; mã vật tư (GY###/VT###) tự sinh. Các thao tác nâng
cao (xóa cứng / bảng giá nhiều bậc / clone / convert / price-test) vẫn để ngoài phạm vi.
"""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from ..deps import get_material_service, require_any_permission, require_permission
from ..models.user import User
from ..schemas.material import (
    MaterialCostOut,
    MaterialCreate,
    MaterialDetailOut,
    MaterialListOut,
    MaterialListStats,
    MaterialRow,
    MaterialUpdate,
)
from ..services.material_service import (
    MaterialDuplicate,
    MaterialNotFound,
    MaterialService,
    MaterialValidationError,
    ToggleActiveForbidden,
)

router = APIRouter(prefix="/api/materials", tags=["materials"])
MODULE = "dm_giay_vat_tu"
# Ghi mặt hàng cho phép người quản trị danh mục (dm_giay_vat_tu) HOẶC người vận hành kho
# (kho) — thủ kho/sản xuất tạo mặt hàng ngay khi lập phiếu (BRD §3.4). Đọc vẫn theo dm_giay_vat_tu.
_can_write = require_any_permission((MODULE, "create"), ("kho", "create"))
_can_edit = require_any_permission((MODULE, "update"), ("kho", "update"))
# Đọc 1 mặt hàng để mở form sửa từ luồng kho — cho phép người vận hành kho (kho:read).
_can_read_one = require_any_permission((MODULE, "read"), ("kho", "read"))

# Ảnh vật tư: <backend>/static/materials (serve read-only tại /static/materials — mirror avatar).
IMAGE_DIR = Path(__file__).resolve().parents[2] / "static" / "materials"
IMAGE_URL_PREFIX = "/static/materials"
MAX_IMAGE_BYTES = 3 * 1024 * 1024  # 3 MB
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

@router.get("", response_model=MaterialListOut)
def list_materials(
    svc: Annotated[MaterialService, Depends(get_material_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    material_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    warehouse_id: int | None = Query(default=None, description="Lọc danh mục theo kho quản lý"),
    sort: str = Query(default="code"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> MaterialListOut:
    rows, total = svc.list_materials(
        q=q, material_type=material_type, is_active=is_active, warehouse_id=warehouse_id,
        sort=sort, page=page, size=size,
    )
    stats = svc.get_list_stats()
    return MaterialListOut(
        items=[MaterialRow.model_validate(r) for r in rows],
        total=total,
        page=page,
        size=size,
        stats=MaterialListStats(**stats),
    )

@router.get("/{material_id}", response_model=MaterialDetailOut)
def get_material(
    material_id: int,
    svc: Annotated[MaterialService, Depends(get_material_service)],
    _: Annotated[User, Depends(_can_read_one)],
) -> MaterialDetailOut:
    try:
        material = svc.get_material(material_id)
    except MaterialNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return MaterialDetailOut.model_validate(material)


@router.post("/upload-image")
async def upload_material_image(
    _: Annotated[User, Depends(_can_write)],
    file: Annotated[UploadFile, File()],
) -> dict:
    """Tải ảnh vật tư (JPG/PNG/WebP ≤ 3 MB) → trả `image_url` để gắn vào payload create/update.
    Tách khỏi bản ghi vật tư nên dùng được cả khi Thêm mới (chưa có id)."""
    ext = ALLOWED_IMAGE_TYPES.get((file.content_type or "").lower())
    if ext is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ảnh phải là JPG, PNG hoặc WebP.")
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Tệp ảnh rỗng.")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ảnh vượt quá 3 MB.")
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"mat_{secrets.token_hex(8)}{ext}"
    (IMAGE_DIR / filename).write_bytes(data)
    return {"image_url": f"{IMAGE_URL_PREFIX}/{filename}"}


@router.post("", response_model=MaterialDetailOut, status_code=status.HTTP_201_CREATED)
def create_material(
    payload: MaterialCreate,
    svc: Annotated[MaterialService, Depends(get_material_service)],
    user: Annotated[User, Depends(_can_write)],
) -> MaterialDetailOut:
    """Thêm vật tư mới vào danh mục kho. Mã (GY###/VT###) tự sinh theo loại."""
    try:
        material = svc.create_material(**payload.model_dump(), actor=user)
    except MaterialDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except MaterialValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return MaterialDetailOut.model_validate(material)


@router.put("/{material_id}", response_model=MaterialDetailOut)
def update_material(
    material_id: int,
    payload: MaterialUpdate,
    svc: Annotated[MaterialService, Depends(get_material_service)],
    user: Annotated[User, Depends(_can_edit)],
) -> MaterialDetailOut:
    """Sửa vật tư. Mã giữ nguyên (chỉ đọc). Bật/tắt hoạt động cần quyền update."""
    try:
        material = svc.update_material(
            material_id=material_id, **payload.model_dump(), actor=user
        )
    except MaterialNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except MaterialDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except ToggleActiveForbidden as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from None
    except MaterialValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return MaterialDetailOut.model_validate(material)


@router.patch("/{material_id}/toggle-active", response_model=MaterialDetailOut)
def toggle_active(
    material_id: int,
    svc: Annotated[MaterialService, Depends(get_material_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> MaterialDetailOut:
    """Ẩn/hiện vật tư (is_active). Vật tư ẩn không còn xuất hiện ở dropdown Kho."""
    try:
        material = svc.toggle_active(material_id=material_id, actor=user)
    except MaterialNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return MaterialDetailOut.model_validate(material)

@router.get("/{material_id}/costs/history", response_model=list[MaterialCostOut])
def cost_history(
    material_id: int,
    svc: Annotated[MaterialService, Depends(get_material_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[MaterialCostOut]:
    try:
        rows = svc.get_cost_history(material_id)
    except MaterialNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return [MaterialCostOut.model_validate(r) for r in rows]
