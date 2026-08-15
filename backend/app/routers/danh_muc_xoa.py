"""Hỏi trước khi xoá: "cái này còn ai dùng không?" — một cửa chung cho cả phân hệ danh mục.

MỘT endpoint thay vì tám, đúng cách `nhat_ky_danh_muc.py` đã làm: tám màn danh mục giống hệt nhau
về mặt này (đếm nơi dùng rồi trả lời cho hộp thoại xoá), tách ra tám route chỉ tổ chép tám lần
cùng một đoạn — và tám lần thì sẽ có lần quên.

Quyền: KHÔNG đẻ ô quyền mới. Ai XOÁ được màn nào thì hỏi được câu này cho bản ghi trong màn đó,
dùng chung bảng `LOAI_MODULE` với nhật ký. Loại lạ → 404 chứ không 403, để không lộ ra là
có/không có dữ liệu.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..catalog_registry import dang_ky_json
from ..db import get_db
from ..deps import get_authorization_service, get_current_user
from ..models.user import User
from ..services.danh_muc_tham_chieu import model_cua, tham_chieu
from ..services.rbac_service import AuthorizationService
from .nhat_ky_danh_muc import LOAI_MODULE

router = APIRouter(prefix="/api/danh-muc", tags=["danh-muc"])

ACTION_DELETE = "delete"


# ⚠️ Route TĨNH phải khai TRƯỚC route có tham số: FastAPI khớp theo thứ tự khai, để sau thì
# `"dang-ky"` có ngày bị nuốt vào `{loai}` của một route một-đoạn thêm sau này.
@router.get("/dang-ky")
def dang_ky(user: Annotated[User, Depends(get_current_user)]) -> dict:
    """Bảng khai 10 màn Cấu hình danh mục (loại · khoá quyền · nhãn · id màn).

    Để FE dựng menu + ma trận quyền từ MỘT nguồn thay vì chép tay lần thứ ba. Chỉ cần ĐĂNG NHẬP:
    đây là bảng khai TĨNH, không có dữ liệu nghiệp vụ nào — đẻ thêm ô quyền cho nó chỉ tạo ra một
    ô mà ai cũng phải bật.
    """
    _ = user
    return {"items": dang_ky_json()}


@router.get("/{loai}/{obj_id}/kiem-xoa")
def kiem_xoa(
    loai: str,
    obj_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Trả về đủ thứ hộp thoại xoá cần để tự quyết, KHÔNG tự quyết hộ:

      * `xoa_han_duoc` — chưa ai dùng ⇒ cho xoá hẳn (khai nhầm thì xoá ngay, đừng để làm rác);
      * `chan`         — danh sách "3 lệnh sản xuất", "12 dòng phiếu kho" ⇒ chỉ cho NGỪNG DÙNG;
      * `keo_theo`     — thứ sẽ BAY THEO nếu xoá hẳn (CASCADE ở DB), phải nói bằng SỐ trước khi bấm.
    """
    module = LOAI_MODULE.get(loai)
    model = model_cua(loai)
    if module is None or model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Không rà được nơi dùng cho loại này.")
    if not authz.can(user, module, ACTION_DELETE):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền xóa.")

    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bản ghi.")
    return tham_chieu(db, loai, obj).as_dict()
