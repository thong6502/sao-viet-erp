"""Router — Kế hoạch vật tư (bảng cân đối) của Kế hoạch sản xuất.

Prefix `/api/ke-hoach-vat-tu`. MODULE quyền = `san_xuat` (tái dùng, KHÔNG đẻ quyền mới).

Hai cửa, hai mức quyền khác nhau có chủ ý:
* `GET /can-doi` — chỉ cần đọc `san_xuat`. Bảng này là công cụ NHÌN, ai lo sản xuất đều xem được.
* `POST /de-nghi-mua` — đòi ĐÚNG quyền tạo yêu cầu mua cho bộ phận, kiểm qua chính
  `PurchaseService.can_create_department_request`. Không lách bằng cách tự chèn quyền ở đây: một
  cửa mới mà tự phán quyền là một lỗ mà bảng phân quyền không nhìn thấy.

Dependency dựng INLINE (`get_service`) theo lối `routers/kho_request.py`, không nhét vào `deps.py`.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, get_purchase_service, require_permission
from ..repositories.bai_ghep_repo import BaiGhepRepository
from ..repositories.don_vi_do_repo import DonViDoRepository
from ..repositories.lsx_repo import LsxRepository
from ..repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
from ..repositories.stock_lot_repo import StockLotRepository
from ..repositories.stock_request_repo import StockRequestRepository
from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository
from ..schemas.ke_hoach_vat_tu import CanDoiOut, DeNghiMuaIn, DeNghiMuaOut
from ..services.ke_hoach_vat_tu_service import (
    KeHoachVatTuError,
    KeHoachVatTuService,
)
from ..services.purchase_service import PurchaseError, PurchaseForbidden, PurchaseService
from ..services.vat_lieu_kho_service import VatLieuKhoService

router = APIRouter(prefix="/api/ke-hoach-vat-tu", tags=["ke-hoach-vat-tu"])
MODULE = "san_xuat"


def get_service(db: Annotated[Session, Depends(get_db)]) -> KeHoachVatTuService:
    return KeHoachVatTuService(
        db,
        lsx_repo=LsxRepository(db),
        bai_ghep_repo=BaiGhepRepository(db),
        hang=VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db)),
        lots=StockLotRepository(db),
        requests=StockRequestRepository(db),
        purchases=PurchaseRequestRepository(db),
        suppliers=SupplierRepository(db),
        don_vi=DonViDoRepository(db),
    )


Service = Annotated[KeHoachVatTuService, Depends(get_service)]
# Service thu mua THẬT (dependency dùng chung với `routers/purchases.py`) — nút "Đề nghị mua" đi
# đúng cửa đang chạy, không đẻ đường tạo yêu cầu mua thứ hai. Hai đường tạo là hai bộ luật, và bộ
# nào cũng sẽ có lúc quên cập nhật.
ThuMua = Annotated[PurchaseService, Depends(get_purchase_service)]


@router.get("/can-doi", response_model=CanDoiOut)
def can_doi(
    svc: Service,
    _user: Annotated[object, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None, description="Mã lệnh / mã hoặc tên mặt hàng"),
    chi_thieu: bool = Query(default=False, description="Chỉ nhóm có dòng đỏ"),
) -> CanDoiOut:
    try:
        return CanDoiOut(**svc.can_doi(q=q, chi_thieu=chi_thieu))
    except KeHoachVatTuError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.post("/de-nghi-mua", response_model=DeNghiMuaOut, status_code=status.HTTP_201_CREATED)
def de_nghi_mua(
    payload: DeNghiMuaIn,
    svc: Service,
    thu_mua: ThuMua,
    user: CurrentUser,
    # Gác CẢ HAI cửa: `san_xuat:read` để đọc bảng (số lượng mua suy ra từ chính bảng đó — cho phép
    # lập yêu cầu từ một bảng mình không được xem là một cửa mà bảng phân quyền không mô tả), rồi
    # `create_department_request` tự kiểm bit tạo yêu cầu mua bên trong.
    _quyen_doc: Annotated[object, Depends(require_permission(MODULE, "read"))] = None,
) -> DeNghiMuaOut:
    """Gộp các dòng đỏ đã tick thành MỘT yêu cầu mua bộ phận.

    Trả mã yêu cầu để FE mở lên xem — **không tự gửi đi**. Máy ghi nhận, người quyết.
    """
    try:
        gom = svc.gom_de_nghi([d.model_dump() for d in payload.dong])
    except KeHoachVatTuError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    noi_dung = (payload.ghi_chu or "").strip() or (
        f"Thiếu vật tư cho {gom['related_document_code']} — lập từ bảng cân đối kế hoạch vật tư."
    )
    try:
        row = thu_mua.create_department_request(
            source_type="san_xuat",
            related_document_type="lsx",
            related_document_code=gom["related_document_code"],
            content=noi_dung,
            needed_date=gom["needed_date"],
            lines=gom["lines"],
            actor=user,
        )
    except PurchaseForbidden as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    except PurchaseError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return DeNghiMuaOut(id=row["id"], code=row["code"])
