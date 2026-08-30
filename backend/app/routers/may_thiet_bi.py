"""Máy thiết bị router — CRUD danh mục Máy + danh mục Nhóm máy.

Thân CRUD của màn Máy sinh từ `routers/catalog_base.make_catalog_router`. Dependency provider khai
INLINE để không đụng deps.py (file dùng chung).

⚠️ `/trang-thai` là route TĨNH nên phải khai TRƯỚC lời gọi factory ở cuối file — factory dựng
`/{item_id}`, mà FastAPI khớp theo THỨ TỰ khai: để sau thì "trang-thai" rơi vào `{item_id}` và ăn
422 vì không ép được sang int.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission, require_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.may_thiet_bi_repo import MayThietBiRepository, NhomMayRepository
from ..schemas.may_thiet_bi import (
    MayThietBiIn,
    MayThietBiListOut,
    MayThietBiRow,
    NhomMayIn,
    NhomMayListOut,
    NhomMayRow,
    TrangThaiMayOut,
    TrangThaiMayRow,
)
from ..services.may_thiet_bi_service import (
    MayThietBiDuplicate,
    MayThietBiNotFound,
    MayThietBiService,
    MayThietBiValidationError,
    NhomMayService,
)
from ..services.may_trang_thai import trang_thai_may
from ..services.catalog_excel_specs import MAY_THIET_BI
from .catalog_base import make_catalog_router

router = APIRouter(prefix="/api/may-thiet-bi", tags=["may-thiet-bi"])
MODULE = "dm_thiet_bi"

# Danh mục THAM CHIẾU: đọc được nếu có quyền cấu hình Máy HOẶC quyền Tính giá (màn Tính giá cần đổ
# dropdown Máy mà không phải mở màn cấu hình).
#
# MỘT dependency đọc dùng cho CẢ list LẪN detail. Trước 15/08/2026 list mở bằng OR-gate còn detail
# khoá bằng quyền chặt, nên người Tính giá liệt kê được nhưng bấm vào một dòng thì ăn 403 giữa
# luồng — lỗi câm, không ai đoán ra thiếu quyền gì.
_DOC = require_any_permission((MODULE, "read"), ("tinh_gia_thanh", "read"))


def get_service(db: Annotated[Session, Depends(get_db)]) -> MayThietBiService:
    return MayThietBiService(MayThietBiRepository(db), AuditLogRepository(db))


Service = Annotated[MayThietBiService, Depends(get_service)]


def _dung_rows(svc: MayThietBiService, objs: list) -> list[MayThietBiRow]:
    """Điền TÊN đơn vị tốc độ (1 truy vấn cho cả trang) rồi mới dựng dòng — list · get · create ·
    update dùng chung một đường nên không chỗ nào lệch."""
    svc.gan_ten_don_vi(objs)
    return [MayThietBiRow.model_validate(o) for o in objs]


# --- Route TĨNH: khai TRƯỚC factory (xem cảnh báo ở docstring) ---------------------------


@router.get("/trang-thai", response_model=TrangThaiMayOut)
def trang_thai(
    db: Annotated[Session, Depends(get_db)],
    svc: Service,
    _: Annotated[User, Depends(_DOC)],
) -> TrangThaiMayOut:
    """Máy nào đang nằm / đang chạy NGAY LÚC NÀY — cột "Trạng thái" của màn Thiết bị."""
    may_ids = svc.repo.all_ids()      # trước 15/08/2026 router tự `select(MayThietBi.id)`
    return TrangThaiMayOut(
        items={k: TrangThaiMayRow(**v) for k, v in trang_thai_may(db, may_ids).items()}
    )

make_catalog_router(
    router, ten="may_thiet_bi", ServiceDep=Service, module=MODULE, doc=_DOC,
    InModel=MayThietBiIn, RowModel=MayThietBiRow, ListModel=MayThietBiListOut,
    loc="loai_may",
    facets=lambda svc, kw: svc.dem_theo_loai(**kw),
    dung_rows=_dung_rows,
    # ⚠️ `may_thiet_bi` KHÔNG có cột `active` (gỡ 11/08/2026 — máy dừng khai theo khoảng thời gian
    # ở `machine_unavailable_periods`). Bật cờ này là nền đi lọc một cột không tồn tại.
    # Có `active` từ mg `0202` (15/08/2026) — nhờ đó màn Máy vào được luật xoá chung: còn dùng ở
    # lệnh/công đoạn thì NGỪNG DÙNG, khai nhầm thì xoá hẳn.
    co_active=True,
    # Không mở `/ma-goi-y`: mã máy đánh theo LOẠI (`IN-01`, `CM-03`, `BE-02`), không phải một dãy
    # số duy nhất ⇒ không có "mã kế tiếp" nào đúng. (Bảng đoán tiền tố ở frontend ghi `TB-` —
    # không khớp bất kỳ máy nào đang có trong DB.)
    enable_clone=True,
    cong_thuc_truong="cong_thuc_luong",
    excel_spec=MAY_THIET_BI,
)


# --- Danh mục NHÓM MÁY (/api/nhom-may) ---------------------------------------
# Router RIÊNG nhưng CÙNG module quyền `dm_thiet_bi` với màn Máy — nhờ vậy ai khai được máy thì
# thêm/xoá được nhóm ngay tại ô, không có cảnh thấy nút rồi ăn 403 (bài học từ tab "Loại nghỉ").
#
# KHÔNG dùng factory: bảng `nhom_may` không có cột `ma` (khoá nghiệp vụ là chính `ten`), không có
# `update`, và `POST` nhận đúng một chuỗi. Ép vào nền chỉ để cho đồng bộ là đẻ ba cờ mà mỗi cờ
# đúng một nơi dùng — xem `NhomMayService`.

nhom_may_router = APIRouter(prefix="/api/nhom-may", tags=["may-thiet-bi"])


def get_nhom_may_service(db: Annotated[Session, Depends(get_db)]) -> NhomMayService:
    return NhomMayService(NhomMayRepository(db))


NhomService = Annotated[NhomMayService, Depends(get_nhom_may_service)]


@nhom_may_router.get("", response_model=NhomMayListOut)
def list_nhom_may(
    svc: NhomService,
    # Đọc được nếu có quyền cấu hình Máy HOẶC Tính giá — cùng lý do với danh sách máy ở trên.
    _: Annotated[User, Depends(_DOC)],
) -> NhomMayListOut:
    rows = svc.list()
    # `page`/`size` trả kèm cho khớp phong bì `{items,total,page,size}` của 10 danh mục còn lại —
    # frontend dùng chung một `crud()` và đọc cả bốn khoá. Bảng này KHÔNG cắt trang (vài chục
    # dòng), nên luôn là trang 1 và `size` = số dòng thật.
    return NhomMayListOut(items=[NhomMayRow.model_validate(r) for r in rows],
                          total=len(rows), page=1, size=len(rows))


@nhom_may_router.post("", response_model=NhomMayRow, status_code=status.HTTP_201_CREATED)
def create_nhom_may(
    payload: NhomMayIn,
    svc: NhomService,
    _: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> NhomMayRow:
    try:
        return NhomMayRow.model_validate(svc.create(payload.ten))
    except MayThietBiDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except MayThietBiValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None


@nhom_may_router.delete("/{nhom_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_nhom_may(
    nhom_id: int,
    svc: NhomService,
    _: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete(nhom_id)
    except MayThietBiNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except MayThietBiValidationError as e:
        # 409 chứ không 422: dữ liệu gửi lên hợp lệ, chỉ là TRẠNG THÁI không cho xoá.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
