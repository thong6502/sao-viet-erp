"""Router — Kế hoạch vật tư (bảng cân đối) của Kế hoạch sản xuất.

Prefix `/api/ke-hoach-vat-tu`. MODULE quyền RIÊNG = `ke_hoach_vat_tu` (tách khỏi `san_xuat` ngày
17/08/2026 — một ô quyền cho mỗi màn; migration 0209 sao chép quyền cũ sang nên không ai mất
đường làm việc). Màn này bày GIÁ vật tư và số phải mua, không phải thứ mặc nhiên đi kèm quyền xem
lệnh sản xuất.

Hai cửa, hai mức quyền khác nhau có chủ ý:
* `GET /can-doi` — chỉ cần đọc `ke_hoach_vat_tu`. Bảng này là công cụ NHÌN, ai lo sản xuất đều xem được.
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
from ..schemas.ke_hoach_vat_tu import (
    CanDoiOut,
    DeNghiMuaIn,
    DeNghiMuaOut,
    GiuChoIn,
    TheoLenhOut,
    TheoLenhRow,
)
from ..services.giu_cho_service import GiuChoError, GiuChoService
from ..services.ke_hoach_vat_tu_service import (
    KeHoachVatTuError,
    KeHoachVatTuService,
)
from ..services.purchase_service import PurchaseError, PurchaseForbidden, PurchaseService
from ..services.vat_lieu_kho_service import VatLieuKhoService

router = APIRouter(prefix="/api/ke-hoach-vat-tu", tags=["ke-hoach-vat-tu"])
MODULE = "ke_hoach_vat_tu"


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


def get_giu_cho(svc: Annotated[KeHoachVatTuService, Depends(get_service)],
                db: Annotated[Session, Depends(get_db)]) -> GiuChoService:
    """Giữ chỗ ăn CHUNG bảng cân đối với `/can-doi` trong cùng một request.

    Dùng lại `get_service` chứ không dựng bảng thứ hai: FastAPI cache dependency theo request, nên
    hai cửa của cùng một lần bấm nhìn đúng một bản số. Dựng riêng là mở đường cho hai con số lệch
    nhau ngay trong một màn hình.
    """
    return GiuChoService(db, svc)


Service = Annotated[KeHoachVatTuService, Depends(get_service)]
GiuCho = Annotated[GiuChoService, Depends(get_giu_cho)]
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


@router.get("/theo-lenh", response_model=TheoLenhOut)
def theo_lenh(
    giu: GiuCho,
    _user: Annotated[object, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None, description="Mã lệnh / mã hoặc tên mặt hàng"),
    chi_can_lo: bool = Query(default=False, description="Chỉ lệnh còn việc phải lo"),
    chi_giu_lau: bool = Query(default=False, description="Chỉ lệnh giữ lâu mà chưa xếp lịch"),
) -> TheoLenhOut:
    """CÙNG bảng cân đối, xoay theo LỆNH. Quyền y hệt `/can-doi` — vẫn chỉ là công cụ NHÌN."""
    try:
        return TheoLenhOut(**giu.theo_chu_the(q=q, chi_can_lo=chi_can_lo,
                                              chi_giu_lau=chi_giu_lau))
    except KeHoachVatTuError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


def _mot_chu_the(payload: GiuChoIn) -> tuple[int | None, int | None]:
    """Đúng MỘT chủ thể — cùng luật với `CheckConstraint` của bảng, chặn sớm ở biên API.

    Cả hai cùng có thì không biết giữ cho ai; cả hai cùng trống thì đẻ dòng mồ côi trừ vào tồn tự
    do của mọi người mà không tra ngược ra được ai giữ.
    """
    if (payload.lsx_id is None) == (payload.bai_ghep_id is None):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Cần đúng một trong hai: lsx_id hoặc bai_ghep_id.")
    return payload.lsx_id, payload.bai_ghep_id


@router.post("/giu-cho/bat", response_model=TheoLenhRow)
def giu_cho_bat(
    payload: GiuChoIn,
    giu: GiuCho,
    _user: Annotated[object, Depends(require_permission(MODULE, "update"))],
) -> TheoLenhRow:
    """BẬT giữ chỗ = ĐĂNG KÝ, không phải chụp một lần: giữ được bao nhiêu hay bấy nhiêu, hàng về
    sau thì tự nhặt bù. Đòi quyền `update` vì nó lấy tồn ra khỏi tay người khác."""
    lsx_id, bg_id = _mot_chu_the(payload)
    try:
        giu.bat(lsx_id=lsx_id, bai_ghep_id=bg_id)
    except GiuChoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return _tra_dong(giu, lsx_id, bg_id)


@router.post("/giu-cho/tat", response_model=TheoLenhRow)
def giu_cho_tat(
    payload: GiuChoIn,
    giu: GiuCho,
    _user: Annotated[object, Depends(require_permission(MODULE, "update"))],
) -> TheoLenhRow:
    """NHẢ HẾT — không phải hoàn tác. Bật lại có thể chẳng còn gì (lệnh khác đã nhặt mất), nên FE
    phải hỏi trước khi gọi."""
    lsx_id, bg_id = _mot_chu_the(payload)
    try:
        giu.tat(lsx_id=lsx_id, bai_ghep_id=bg_id)
    except GiuChoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return _tra_dong(giu, lsx_id, bg_id)


def _tra_dong(giu: GiuChoService, lsx_id: int | None, bg_id: int | None) -> TheoLenhRow:
    """Thẻ đã cập nhật của chính chủ thể vừa bấm.

    Chủ thể có thể KHÔNG còn trên bảng (tắt giữ chỗ cho một lệnh đã rơi khỏi phạm vi) — lúc đó trả
    thẻ rỗng đúng nghĩa "hết việc ở đây" thay vì 404: bấm tắt đã thành công, ném lỗi là nói ngược.
    """
    dong = giu.mot_dong(lsx_id=lsx_id, bai_ghep_id=bg_id)
    if dong is None:
        return TheoLenhRow(lsx_id=lsx_id, bai_ghep_id=bg_id, ma="")
    return TheoLenhRow(**dong)


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
    # Ngày cần của TỪNG lệnh nối vào cuối nội dung. Yêu cầu chỉ mang MỘT ngày (sớm nhất), nên thiếu
    # dòng này thì người mua không biết trong lô có lệnh nào cần muộn hơn hay lệnh nào đang gấp —
    # dễ hối cả đơn cho kịp mốc sớm nhất, hoặc chia đơn nhầm chỗ. Nối cả khi người dùng tự gõ ghi
    # chú: đây là dữ kiện của hệ, không phải câu chữ thay thế được.
    if gom.get("ghi_chu_ngay"):
        noi_dung = f"{noi_dung}\n{gom['ghi_chu_ngay']}"
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
