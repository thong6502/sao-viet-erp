"""Phục vụ file người dùng tải lên — thay cho mount `/static` công khai trước đây.

Vì sao có router này: `/static` là public, ai có URL là đọc được scan CCCD, hợp đồng lao động,
chứng từ kế toán. Giờ mọi byte đi qua đây: phải ĐĂNG NHẬP, và với thư mục nhạy cảm còn phải có
quyền đọc module tương ứng.

Vì sao xác thực bằng cookie chứ không phải Bearer: `<img src>` / `<a download>` do trình duyệt
tự phát, không gắn được header `Authorization`, mà access token cố ý chỉ nằm trong RAM của tab
(`frontend/src/auth/AuthContext.tsx`). Chi tiết ở `app/deps.py::get_file_user`.
"""
from __future__ import annotations

import mimetypes
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ..deps import FileUser, get_authorization_service
from ..services.rbac_service import AuthorizationService
from ..storage import StorageFileNotFound, get_storage, is_safe_key

router = APIRouter(prefix="/api/files", tags=["files"])

# Thư mục nào đòi quyền gì. KHÔNG có trong bảng → chỉ cần đăng nhập (vd `avatars/`: ảnh đại diện
# hiện khắp app, ai đăng nhập cũng thấy). Module key lấy từ hằng `MODULE` của router tương ứng.
_PREFIX_PERMISSION: dict[str, str] = {
    "hr": "nhan_su",
    "crm": "khach_hang",
    "ke-toan": "ke_toan",
    "ke-toan-thu": "ke_toan",
    "don-hang": "don_hang_ban",
    "san-xuat": "san_xuat",
    "kho": "kho",  # đính kèm phiếu kho (chứng từ nhập/xuất) — chỉ người có quyền đọc kho xem được
}


@router.get("/{key:path}")
def download_file(
    key: str,
    user: FileUser,
    authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> StreamingResponse:
    # Kiểm khoá TRƯỚC khi chạm storage: `key` tới thẳng từ URL người dùng gõ.
    if not is_safe_key(key):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Đường dẫn tệp không hợp lệ")

    module = _PREFIX_PERMISSION.get(key.split("/", 1)[0])
    if module and not authz.can(user, module, "read"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bạn không có quyền xem tệp này")

    try:
        stream, size, content_type = get_storage().open_stream(key)
    except StorageFileNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tệp") from None

    # `private`: chặn proxy/CDN dùng chung cache — file này gắn với một người dùng cụ thể.
    headers = {"Cache-Control": "private, max-age=300"}
    if size is not None:
        headers["Content-Length"] = str(size)
    # LocalStorage không giữ content-type → đoán theo đuôi file.
    media = content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"
    return StreamingResponse(stream, media_type=media, headers=headers)
