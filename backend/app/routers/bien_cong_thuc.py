"""Từ điển BIẾN của các ô gõ công thức — API để màn khai vẽ chip và validate.

Trước 11/08/2026 danh sách này nằm CỨNG trong frontend, còn giá trị thật nằm ở backend — hai nơi
không ai ép khớp và đã lệch (xem `services/bien_cong_thuc`). Nay frontend hỏi API, một nguồn.

Không gắn quyền riêng: đây là TỪ ĐIỂN tĩnh, không phải dữ liệu nghiệp vụ — ai vào được màn khai
công thức thì cần đọc được nó. Chỉ chặn ở mức đăng nhập.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_current_user
from ..models.user import User
from ..schemas.bien_cong_thuc import BienCongThucListOut
from ..services.bien_cong_thuc import BIEN, LOAI, bien_cho

router = APIRouter(prefix="/api/bien-cong-thuc", tags=["bien-cong-thuc"])


@router.get("", response_model=BienCongThucListOut)
def list_bien(
    _: Annotated[User, Depends(get_current_user)],
    loai: str | None = Query(default=None, description=f"Lọc theo ô công thức: {' · '.join(LOAI)}"),
) -> BienCongThucListOut:
    """Biến dùng được trong công thức. Không truyền `loai` → trả HẾT.

    Màn khai cần cả hai: lọc theo `loai` để vẽ chip đúng ô đang gõ, và danh sách ĐẦY ĐỦ để dịch
    nghĩa công thức cũ (công thức có thể chứa biến của ô khác — dịch được vẫn hơn hiện mã trần).
    """
    if loai is not None and loai not in LOAI:
        raise HTTPException(422, f"Loại công thức không hợp lệ. Chọn: {' · '.join(LOAI)}")
    return BienCongThucListOut(items=list(bien_cho(loai)) if loai else list(BIEN))
