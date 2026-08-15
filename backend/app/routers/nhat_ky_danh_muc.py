"""Nhật ký của MỘT bản ghi danh mục — một cửa chung cho cả 10 màn Cấu hình danh mục.

Một endpoint thay vì mười: các màn danh mục giống hệt nhau về mặt này (đọc `audit_logs` theo
target `"{loai}:{id}"`), tách ra mười route chỉ tổ chép mười lần cùng một đoạn.

Quyền: KHÔNG đẻ ô quyền mới — ai ĐỌC được màn nào thì xem được nhật ký của bản ghi trong màn đó
(`LOAI_MODULE`). Loại lạ → 404 chứ không phải 403, để không lộ ra là có/không có dữ liệu.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..catalog_registry import MODULE_THEO_LOAI
from ..db import get_db
from ..deps import get_authorization_service, get_current_user
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..schemas.nhat_ky import NhatKyItem, NhatKyOut
from ..services.actor_display import actor_labels
from ..services.rbac_service import ACTION_READ, AuthorizationService

router = APIRouter(prefix="/api/nhat-ky-danh-muc", tags=["nhat-ky-danh-muc"])

# loại bản ghi (đúng chuỗi service dùng làm target) → module quyền của màn chứa nó.
#
# Phần DANH MỤC đọc thẳng từ `catalog_registry` — kể cả tên đời cũ (`product_type`, `machine`,
# `operation`) và bảng phụ đi ké ô quyền (`don_vi_quy_doi`, nằm trong drawer màn Đơn vị; trước
# 15/08/2026 nó ghi nhật ký dưới target `don_vi_do:<id cặp>`, tức là trộn lịch sử của hai thực
# thể khác bảng có cùng số id). Thêm màn danh mục ⇒ sửa registry, KHÔNG sửa file này.
LOAI_MODULE: dict[str, str] = {
    **MODULE_THEO_LOAI,
    # Kỹ thuật máy (12/08/2026) — KHÔNG phải danh mục nên KHÔNG vào registry, nhưng cùng một câu
    # hỏi "ai đổi gì, lúc nào" và cùng cách lưu (`audit_logs` theo target). Dựng endpoint thứ hai
    # chỉ để đổi tiền tố URL là chép lại y nguyên đoạn này.
    "ky_thuat_sua_chua": "ky_thuat_may",
    "ky_thuat_bao_tri": "ky_thuat_may",
}


@router.get("/{loai}/{obj_id}", response_model=NhatKyOut)
def nhat_ky_cua_ban_ghi(
    loai: str,
    obj_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=50, ge=1, le=200),
) -> NhatKyOut:
    """Ai đổi gì, lúc nào — mới nhất trước."""
    module = LOAI_MODULE.get(loai)
    if module is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không có nhật ký cho loại này.")
    if not authz.can(user, module, ACTION_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền xem.")

    rows = AuditLogRepository(db).list_by_target(f"{loai}:{obj_id}", limit=limit)
    ten = actor_labels(db, {r.actor_user_id for r in rows if r.actor_user_id is not None})
    return NhatKyOut(items=[
        NhatKyItem(
            at=r.created_at,
            actor_name=ten.get(r.actor_user_id) if r.actor_user_id else None,
            action=r.action,
            detail=r.detail,
        )
        for r in rows
    ])
