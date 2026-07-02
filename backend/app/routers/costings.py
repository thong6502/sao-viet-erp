"""Tính giá (Costing / giá thành nội bộ) routes — spec-08-tinh-gia.

Thin HTTP shell over CostingService. Every route is guarded by
`require_permission('tinh_gia_thanh', <action>)` (module_key `tinh_gia_thanh` is the one
already seeded — feat-038 note; spec-08 uses `tinh_gia` as the domain label). The paper-cost
picker (SEAM-07) and the product read (SEAM-11) are seams: when the upstream module is not
built the port raises and we return an explicit "chưa sẵn sàng" state (never a fabricated
value). Cost numbers (giá vốn, số tờ, đơn giá) are DEFERRED to feat-040..042 behind
SEAM-07..12; the LÀM-NGAY endpoints cover list + header + phương án giấy + gợi ý hình học.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import get_costing_service, require_permission
from ..models.costing import (
    COSTING_STATUSES,
    EXECUTION_MODES,
    Costing,
)
from ..models.user import User
from ..schemas.costing import (
    CostingCreate,
    CostingDetailOut,
    CostingEnumsOut,
    CostingListOut,
    CostingRow,
    CostingUpdate,
    EnumOption,
    OperationOut,
    PaperCostPickerOut,
    PaperOptionOut,
    ProductPickerOut,
    SuggestPiecesIn,
    SuggestPiecesOut,
)
from ..services.costing_service import (
    CostingInUse,
    CostingNotFound,
    CostingService,
    CostingValidationError,
    suggest_pieces_per_sheet,
)

router = APIRouter(prefix="/api/costings", tags=["costings"])

MODULE = "tinh_gia_thanh"

Service = Annotated[CostingService, Depends(get_costing_service)]

STATUS_LABELS = {
    "draft": "Nháp",
    "ready": "Sẵn sàng",
}
EXECUTION_MODE_LABELS = {
    "internal": "Nội bộ (khoán)",
    "outsourced": "Thuê ngoài (NCC)",
}


def _row(costing: Costing, count: int) -> CostingRow:
    return CostingRow(
        id=costing.id,
        code=costing.code,
        product_id=costing.product_id,
        qty_final=costing.qty_final,
        paper_option_count=count,
        status=costing.status,
        # SEAM-07..12: giá vốn tổng chưa tính được → null (UI shows "—" / chưa sẵn sàng).
        total_cost=None,
    )


def _detail(costing: Costing) -> CostingDetailOut:
    return CostingDetailOut(
        id=costing.id,
        code=costing.code,
        product_id=costing.product_id,
        qty_final=costing.qty_final,
        status=costing.status,
        note=costing.note,
        paper_options=[
            PaperOptionOut(
                id=p.id,
                sheet_paper_master_id=p.sheet_paper_master_id,
                # SEAM-07: no live paper label/price until Danh mục Giấy is built.
                paper_display=None,
                sheet_w=float(p.sheet_w),
                sheet_h=float(p.sheet_h),
                pieces_per_sheet=p.pieces_per_sheet,
                grain_locked=p.grain_locked,
                selected=p.selected,
            )
            for p in costing.paper_options
        ],
        operations=[
            OperationOut(
                id=o.id,
                sequence=o.sequence,
                name=o.name,
                execution_mode=o.execution_mode,
            )
            for o in costing.operations
        ],
    )


@router.get("/enums", response_model=CostingEnumsOut)
def costing_enums(
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> CostingEnumsOut:
    """Enum vocab for the form selects (trạng thái draft/ready, hình thức công đoạn)."""
    return CostingEnumsOut(
        statuses=[
            EnumOption(value=v, label=STATUS_LABELS.get(v, v)) for v in COSTING_STATUSES
        ],
        execution_modes=[
            EnumOption(value=v, label=EXECUTION_MODE_LABELS.get(v, v))
            for v in EXECUTION_MODES
        ],
    )


@router.get("/papers", response_model=PaperCostPickerOut)
def list_paper_costs(
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> PaperCostPickerOut:
    """Paper-cost picker (SEAM-07). When Danh mục Giấy / Kho is not built the port raises →
    explicit "Danh mục Giấy chưa sẵn sàng" (never a fabricated paper/price list)."""
    from ..services import costing_ports

    try:
        # SEAM-07: chờ dm_giay_vat_tu/kho (PaperCost)
        costing_ports.get_paper_price(paper_master_id=0)
    except NotImplementedError:
        return PaperCostPickerOut(
            available=False,
            message="Danh mục Giấy chưa sẵn sàng",
        )
    # Once back-filled, a real adapter will list papers here.
    return PaperCostPickerOut(available=True, items=[])


@router.post("/suggest-pieces", response_model=SuggestPiecesOut)
def suggest_pieces(
    payload: SuggestPiecesIn,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> SuggestPiecesOut:
    """Parallel số-con/khổ suggestion — PURE geometry (usable area / piece area, xoay branch
    dropped when grain_locked, §31a). Returns 0 (never divides by zero) when giấy quá nhỏ /
    khổ SP lớn hơn tờ; the UI shows the suggestion NEXT TO the manual value (not auto-lock)."""
    pieces = suggest_pieces_per_sheet(
        sheet_w=payload.sheet_w,
        sheet_h=payload.sheet_h,
        piece_w=payload.piece_w,
        piece_h=payload.piece_h,
        grain_locked=payload.grain_locked,
    )
    message = (
        "Giấy quá nhỏ so với khổ thành phẩm — kiểm tra lại khổ tờ / khổ SP."
        if pieces == 0
        else None
    )
    return SuggestPiecesOut(pieces=pieces, message=message)


@router.get("/products/{product_id}", response_model=ProductPickerOut)
def read_product(
    product_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> ProductPickerOut:
    """Read a product + cấu phần for Khối A/B (SEAM-11). When `san_pham` does not expose
    ProductRead the port raises → explicit "Sản phẩm chưa sẵn sàng" (never fabricated specs)."""
    try:
        product = svc.read_product(product_id)
    except NotImplementedError:
        # SEAM-11: chờ san_pham (ProductRead)
        return ProductPickerOut(available=False, message="Sản phẩm chưa sẵn sàng")
    return ProductPickerOut(available=True, product=product)


@router.get("", response_model=CostingListOut)
def list_costings(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    product_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    sort: str = Query(default="code"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> CostingListOut:
    rows, total, counts = svc.list_costings(
        q=q,
        product_id=product_id,
        status=status_filter,
        sort=sort,
        page=page,
        size=size,
    )
    return CostingListOut(
        items=[_row(c, counts.get(c.id, 0)) for c in rows],
        total=total,
        page=page,
        size=size,
    )


@router.post("", response_model=CostingDetailOut, status_code=status.HTTP_201_CREATED)
def create_costing(
    payload: CostingCreate,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> CostingDetailOut:
    try:
        costing = svc.create_costing(
            product_id=payload.product_id,
            qty_final=payload.qty_final,
            note=payload.note,
            status=payload.status,
            paper_options=[p.model_dump() for p in payload.paper_options],
            operations=[o.model_dump() for o in payload.operations],
            actor=user,
        )
    except CostingValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return _detail(costing)


@router.get("/{costing_id}", response_model=CostingDetailOut)
def get_costing(
    costing_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> CostingDetailOut:
    try:
        costing = svc.get_costing(costing_id)
    except CostingNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương án tính giá.",
        ) from None
    return _detail(costing)


@router.put("/{costing_id}", response_model=CostingDetailOut)
def update_costing(
    costing_id: int,
    payload: CostingUpdate,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> CostingDetailOut:
    try:
        costing = svc.update_costing(
            costing_id=costing_id,
            product_id=payload.product_id,
            qty_final=payload.qty_final,
            note=payload.note,
            status=payload.status,
            paper_options=[p.model_dump() for p in payload.paper_options],
            operations=[o.model_dump() for o in payload.operations],
            actor=user,
        )
    except CostingNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương án tính giá.",
        ) from None
    except CostingValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return _detail(costing)


@router.delete(
    "/{costing_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
def delete_costing(
    costing_id: int,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_costing(costing_id=costing_id, actor=user)
    except CostingNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương án tính giá.",
        ) from None
    except CostingInUse as e:
        # Reserved for when Báo giá references costings (spec-08 F8).
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
