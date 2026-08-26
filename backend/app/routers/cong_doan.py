"""Công đoạn router — CRUD danh mục + hai cửa tham chiếu (`/phong-ban`, `/dau-viec`).

Thân CRUD sinh từ `routers/catalog_base.make_catalog_router`. Dependency INLINE (không đụng
deps.py). MODULE quyền = "dm_cong_doan".

⚠️ Hai route TĨNH bên dưới phải khai TRƯỚC lời gọi factory ở cuối file — factory dựng
`/{item_id}`, mà FastAPI khớp route theo THỨ TỰ khai: để sau thì `"phong-ban"` rơi vào
`{item_id}` và ăn 422 vì không ép được sang int.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.cong_doan_repo import CongDoanRepository
from ..schemas.cong_doan import CongDoanIn, CongDoanListOut, CongDoanRow, RefOption, RefOptionListOut
from ..services.cong_doan_service import CongDoanService
from .catalog_base import make_catalog_router

router = APIRouter(prefix="/api/cong-doan", tags=["cong-doan"])
MODULE = "dm_cong_doan"

# Danh mục THAM CHIẾU: đọc được nếu có quyền cấu hình Công đoạn HOẶC quyền Tính giá (màn Tính giá
# cần đổ dropdown Công đoạn mà không phải mở màn cấu hình).
#
# MỘT dependency đọc dùng cho CẢ list LẪN detail. Trước 15/08/2026 list mở bằng OR-gate còn detail
# khoá bằng quyền chặt, nên người Tính giá liệt kê được nhưng bấm vào một dòng thì ăn 403 giữa
# luồng — lỗi câm, không ai đoán ra thiếu quyền gì.
_DOC = require_any_permission((MODULE, "read"), ("tinh_gia_thanh", "read"))


def get_service(db: Annotated[Session, Depends(get_db)]) -> CongDoanService:
    return CongDoanService(CongDoanRepository(db), AuditLogRepository(db))


Service = Annotated[CongDoanService, Depends(get_service)]


def _dung_rows(svc: CongDoanService, objs: list) -> list[CongDoanRow]:
    """Điền TÊN đơn vị vào/ra (1 truy vấn cho cả trang) rồi mới dựng dòng.

    Truyền vào factory nên list · get · create · update dùng CÙNG một đường — trước 15/08/2026
    bốn handler tự gọi `gan_ten_don_vi` và chỉ cần quên một chỗ là màn hiện mã trần.
    """
    svc.gan_ten_don_vi(objs)
    return [CongDoanRow.model_validate(o) for o in objs]


# --- Route TĨNH: khai TRƯỚC factory (xem cảnh báo ở docstring) ---------------------------


@router.get("/phong-ban", response_model=RefOptionListOut)
def list_phong_ban_options(
    svc: Service,
    # Đọc được nếu có quyền cấu hình Công đoạn HOẶC Tính giá (đổ dropdown 'Phòng ban phụ trách').
    _: Annotated[User, Depends(_DOC)],
) -> RefOptionListOut:
    """TỔ cho dropdown 'Phòng ban / Tổ phụ trách' ở form Công đoạn — luật ở service."""
    return RefOptionListOut(items=[RefOption(**r) for r in svc.phong_ban_options()])


@router.get("/dau-viec")
def list_dau_viec_options(
    svc: Service,
    _: Annotated[User, Depends(require_any_permission((MODULE, "read"), ("luong", "read")))],
    department_id: int | None = Query(default=None),
):
    """Đầu việc khoán của một tổ — BẢNG CON (`piece_rates`), không phải danh mục Công đoạn.

    Giữ THỦ CÔNG: nó đọc bảng khác, gác bằng quyền khác (`luong`), và trả phong bì dựng tay.
    """
    items = svc.dau_viec_options(department_id)
    return {"items": items, "total": len(items), "page": 1, "size": max(len(items), 1)}


# Import Excel (mục 1 "Bảng định mức") — bỏ `bu_hao_id`/`nhom_may_cho_phep`/`department_id`: đều là
# FK/mảng id, không gõ tay được trong Excel; khai qua dropdown ở màn sau khi đã có dòng.
IMPORT_COLUMNS_CONG_DOAN = {
    "Mã": "ma",
    "Tên": "ten",
    "Tên hiển thị": "ten_hien_thi",
    "Nhóm": "nhom",
    "Đơn vị vào": "don_vi_vao",
    "Đơn vị ra": "don_vi_ra",
    "Công thức sản lượng": "cong_thuc_san_luong",
}

# "Nhóm" là 1 trong 4 mã cố định (`models/cong_doan.NHOM`) nhưng người khai không gõ mã tiếng Anh —
# màn (dropdown) hiện nhãn tiếng Việt của `rebuildCatalogConfigs.tsx:NHOM_CD`. Nhận CẢ nhãn tiếng
# Việt LẪN mã gốc (ai quen mã thì gõ mã vẫn qua), dịch trước khi vào Pydantic.
_NHOM_NHAN = {
    "che ban": "prepress", "in": "print",
    "gia cong sau in": "finishing", "dich vu khac": "other",
}


def _bo_dau(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _resolve_nhom(du_lieu: dict, svc: CongDoanService) -> dict:
    from ..models.cong_doan import NHOM

    gia_tri = du_lieu.get("nhom")
    if gia_tri not in (None, ""):
        goc = str(gia_tri).strip()
        if goc not in NHOM:
            khoa = _bo_dau(goc).lower()
            ma = _NHOM_NHAN.get(khoa)
            if not ma:
                raise ValueError(
                    f'Nhóm "{goc}" không hợp lệ — chọn: Chế bản, In, Gia công sau in, Dịch vụ khác.')
            du_lieu["nhom"] = ma
    # `che_do_tinh`/`pricing_basis` không phải ô người khai gõ — màn hiện tại LUÔN ép hai giá trị
    # này (`rebuildCatalogConfigs.tsx` transformSubmit, "CHỈ TÍNH THEO CÔNG THỨC"). Thiếu là
    # `_validate` chặn "[E-CD-BASIS]"; import theo đúng luật màn đang chạy, không hỏi lại người khai.
    du_lieu["che_do_tinh"] = "theo_san_luong"
    du_lieu["pricing_basis"] = "per_other"
    return du_lieu

make_catalog_router(
    router, ten="cong_doan", ServiceDep=Service, module=MODULE, doc=_DOC,
    InModel=CongDoanIn, RowModel=CongDoanRow, ListModel=CongDoanListOut,
    loc="nhom",
    facets=lambda svc, kw: svc.dem_theo_nhom(**kw),
    dung_rows=_dung_rows,
    ma_goi_y=True,      # repo khai `ma_prefix = "CD-"`
    enable_clone=True,
    cong_thuc_truong="cong_thuc_san_luong",
    enable_import=True,
    import_columns=IMPORT_COLUMNS_CONG_DOAN,
    import_resolve=_resolve_nhom,
)
