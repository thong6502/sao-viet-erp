"""Công việc khoán router — CRUD danh mục đơn giá khoán theo tổ.

Thân CRUD sinh từ `routers/catalog_base.make_catalog_router`. Dependency INLINE (không đụng
deps.py). MODULE quyền = "dm_cong_viec_khoan".

Bảng `piece_rates` trước khai ở một TAB của màn Lương (`/api/luong/khoan/rates`, gác bằng quyền
`luong`); từ 17/08/2026 nó là màn thứ 11 của Cấu hình danh mục. Bốn route cũ đã gỡ — hai đường ghi
vào cùng một bảng thì đường không đi qua `CongViecKhoanService` sẽ không ghi nhật ký, và tab Nhật
ký của màn lặng lẽ thiếu dòng.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.cong_viec_khoan_repo import CongViecKhoanRepository
from ..schemas.cong_viec_khoan import (
    CongViecKhoanIn, CongViecKhoanListOut, CongViecKhoanRow,
)
from ..services.cong_viec_khoan_service import CongViecKhoanService
from .catalog_base import make_catalog_router

router = APIRouter(prefix="/api/cong-viec-khoan", tags=["cong-viec-khoan"])
MODULE = "dm_cong_viec_khoan"

# Danh mục THAM CHIẾU — ai ĐỌC được bảng đơn giá khoán:
#   · người khai chính danh mục này;
#   · Lương (panel "Đơn giá khoán của tổ" trong Cấu hình lương vẫn khai ngay tại chỗ);
#   · Công đoạn (ô "Định mức đầu việc" của bước trỏ thẳng sang đây);
#   · Sản xuất (bước lệnh chọn đầu việc khoán của tổ).
# GHI thì vẫn đòi đúng `dm_cong_viec_khoan` — một ô quyền cho một màn, như 10 màn danh mục kia.
#
# MỘT dependency cho CẢ list LẪN detail: mở list bằng OR-gate mà khoá detail bằng quyền chặt thì
# người ta liệt kê được, bấm vào một dòng lại 403 giữa luồng — lỗi câm, không ai đoán ra thiếu gì.
_DOC = require_any_permission(
    (MODULE, "read"), ("luong", "read"), ("dm_cong_doan", "read"), ("san_xuat", "read"),
)


def get_service(db: Annotated[Session, Depends(get_db)]) -> CongViecKhoanService:
    return CongViecKhoanService(CongViecKhoanRepository(db), AuditLogRepository(db))


Service = Annotated[CongViecKhoanService, Depends(get_service)]


def _dung_rows(svc: CongViecKhoanService, objs: list) -> list[CongViecKhoanRow]:
    """Điền TÊN đơn vị (1 truy vấn cho cả trang) rồi mới dựng dòng.

    Truyền vào factory nên list · get · create · update dùng CÙNG một đường — bốn handler tự gọi
    thì chỉ cần quên một chỗ là màn hiện mã trần (`to` thay cho "tờ")."""
    svc.gan_ten_don_vi(objs)
    return [CongViecKhoanRow.model_validate(o) for o in objs]


make_catalog_router(
    router, ten="cong_viec_khoan", ServiceDep=Service, module=MODULE, doc=_DOC,
    InModel=CongViecKhoanIn, RowModel=CongViecKhoanRow, ListModel=CongViecKhoanListOut,
    # Tab lọc = TỔ. Giá trị là `group_name` (nhãn tổ trên dòng) chứ không phải id: dòng đời cũ chưa
    # gắn tổ nào vẫn phải nằm trong một tab đọc được.
    loc="to",
    facets=lambda svc, kw: svc.dem_theo_to(**kw),
    dung_rows=_dung_rows,
    ma_goi_y=True,      # repo khai `ma_prefix = "KH-"`
)
