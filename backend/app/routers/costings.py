"""Tính giá (Costing) compatibility adapter routes — spec-08.

Acts as an HTTP adapter mapping legacy Costing payload shapes to the new Estimate service
so that the existing frontend integration and test suite do not break.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import get_estimate_service, require_permission
from ..models.user import User
from ..models.estimate import Estimate
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
from ..services.estimate_service import (
    EstimateInUse,
    EstimateNotFound,
    EstimateService,
    EstimateValidationError,
)
from ..services.costing_service import suggest_pieces_per_sheet
from ..services.phieu_tinh_gia import estimate_to_phieu

router = APIRouter(prefix="/api/costings", tags=["costings"])

MODULE = "tinh_gia_thanh"

STATUS_LABELS = {
    "draft": "Nháp",
    "ready": "Sẵn sàng",
    "calculated": "Đã tính toán",
}
EXECUTION_MODE_LABELS = {
    "internal": "Nội bộ (khoán)",
    "outsourced": "Thuê ngoài (NCC)",
}


def _detail_from_estimate(est: Estimate, qty: int) -> CostingDetailOut:
    opt = None
    for o in est.options:
        if o.quantity == qty:
            opt = o
            break
    if not opt and est.options:
        opt = est.options[0]

    spec = est.input_spec_json or {}

    paper_options = []
    paper_options.append(
        PaperOptionOut(
            id=opt.id if opt else est.id,
            sheet_paper_master_id=spec.get("material_id"),
            paper_display=None,
            sheet_w=float(spec.get("sheet_w") or 0),
            sheet_h=float(spec.get("sheet_h") or 0),
            pieces_per_sheet=int(spec.get("pieces_per_sheet") or 1),
            grain_locked=bool(spec.get("grain_locked", False)),
            selected=True,
        )
    )

    operations = []
    raw_ops = spec.get("operations") or []
    for idx, ro in enumerate(raw_ops):
        operations.append(
            OperationOut(
                id=idx + 1,
                sequence=ro.get("sequence") or idx,
                name=ro.get("operation_key") or "Công đoạn",
                execution_mode=ro.get("execution_mode") or "internal",
            )
        )

    # Map estimate status back to ready if calculated to satisfy tests
    legacy_status = "ready" if est.status == "calculated" else est.status

    return CostingDetailOut(
        id=est.id,
        code=est.estimate_number,
        product_id=spec.get("product_id"),
        qty_final=qty,
        status=legacy_status,
        note=None,
        paper_options=paper_options,
        operations=operations,
    )


@router.get("/enums", response_model=CostingEnumsOut)
def costing_enums(
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> CostingEnumsOut:
    """Enum vocab for the form selects (trạng thái draft/ready, hình thức công đoạn)."""
    return CostingEnumsOut(
        statuses=[
            EnumOption(value="draft", label="Nháp"),
            EnumOption(value="ready", label="Sẵn sàng"),
        ],
        execution_modes=[
            EnumOption(value=v, label=EXECUTION_MODE_LABELS.get(v, v))
            for v in EXECUTION_MODE_LABELS
        ],
    )


@router.get("/papers", response_model=PaperCostPickerOut)
def list_paper_costs(
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> PaperCostPickerOut:
    """Paper-cost picker (SEAM-07)."""
    from ..services import costing_ports

    try:
        costing_ports.get_paper_price(paper_master_id=0)
    except NotImplementedError:
        return PaperCostPickerOut(
            available=False,
            message="Danh mục Giấy chưa sẵn sàng",
        )
    return PaperCostPickerOut(available=True, items=[])


@router.post("/suggest-pieces", response_model=SuggestPiecesOut)
def suggest_pieces(
    payload: SuggestPiecesIn,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> SuggestPiecesOut:
    """Parallel pieces suggestion."""
    pieces = suggest_pieces_per_sheet(
        sheet_w=payload.sheet_w,
        sheet_h=payload.sheet_h,
        piece_w=payload.piece_w,
        piece_h=payload.piece_h,
        grain_locked=payload.grain_locked,
        gripper_cm=payload.gripper_cm,
        edge_trim_cm=payload.edge_trim_cm,
        bleed_cm=payload.bleed_cm,
        gutter_cm=payload.gutter_cm,
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
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> ProductPickerOut:
    """Read a product (SEAM-11)."""
    from ..services import costing_ports

    try:
        product = costing_ports.get_product_for_costing(product_id)
    except NotImplementedError:
        return ProductPickerOut(available=False, message="Sản phẩm chưa sẵn sàng")
    return ProductPickerOut(available=True, product=product)


@router.get("", response_model=CostingListOut)
def list_costings(
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    product_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    sort: str = "code",
    page: int = 1,
    size: int = 20,
) -> CostingListOut:
    sort_mapped = "estimate_number"
    if sort == "code":
        sort_mapped = "estimate_number"
    elif sort == "-code":
        sort_mapped = "-estimate_number"
    elif sort in ("qty_final", "-qty_final", "created_at", "-created_at"):
        sort_mapped = "created_at" if "created_at" in sort else "estimate_number"
        if sort.startswith("-"):
            sort_mapped = "-" + sort_mapped

    legacy_status = "calculated" if status_filter == "ready" else status_filter

    rows, total = svc.list_estimates(
        q=q,
        status=legacy_status,
        sort=sort_mapped,
        page=page,
        size=size,
    )

    items = []
    for est in rows:
        qty = est.quantity_list_json[0] if est.quantity_list_json else 1000
        spec = est.input_spec_json or {}
        
        legacy_row_status = "ready" if est.status == "calculated" else est.status

        items.append(
            CostingRow(
                id=est.id,
                code=est.estimate_number,
                product_id=spec.get("product_id"),
                qty_final=qty,
                paper_option_count=1,
                status=legacy_row_status,
                total_cost=None,
            )
        )

    return CostingListOut(
        items=items,
        total=total,
        page=page,
        size=size,
    )


@router.post("", response_model=CostingDetailOut, status_code=status.HTTP_201_CREATED)
def create_costing(
    payload: CostingCreate,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> CostingDetailOut:
    if not payload.paper_options:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cần ít nhất 1 phương án giấy.",
        )

    paper = payload.paper_options[0]
    if paper.pieces_per_sheet <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Phương án giấy 1: số con/khổ phải lớn hơn 0.",
        )

    input_spec = {
        "product_id": payload.product_id,
        "sheet_w": paper.sheet_w,
        "sheet_h": paper.sheet_h,
        "pieces_per_sheet": paper.pieces_per_sheet,
        "grain_locked": paper.grain_locked,
        "material_id": paper.sheet_paper_master_id,
        "operations": [
            {
                "operation_key": op.name,
                "sequence": op.sequence,
                "execution_mode": op.execution_mode,
            }
            for op in payload.operations
        ],
    }

    for op in payload.operations:
        if op.execution_mode not in ("internal", "outsourced"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Công đoạn: hình thức thực hiện không hợp lệ.",
            )

    product_type = "brochure"
    product_name = "Sản phẩm mẫu"
    if payload.product_id:
        try:
            from ..services import costing_ports

            prod = costing_ports.get_product_for_costing(payload.product_id)
            if prod:
                product_type = prod.get("product_type") or "brochure"
                product_name = prod.get("name") or "Sản phẩm mẫu"
        except Exception:
            pass

    # Map legacy status ready to calculated
    status_to_use = "calculated" if payload.status == "ready" else (payload.status or "draft")

    try:
        est = svc.create_estimate(
            product_type=product_type,
            product_name=product_name,
            quantity_list=[payload.qty_final],
            input_spec=input_spec,
            actor_id=user.id,
            status=status_to_use,
            allow_blocking=True,
        )
    except EstimateValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None

    return _detail_from_estimate(est, payload.qty_final)


@router.get("/{costing_id}", response_model=CostingDetailOut)
def get_costing(
    costing_id: int,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> CostingDetailOut:
    try:
        est = svc.get_estimate(costing_id)
    except EstimateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương án tính giá.",
        ) from None
    qty = est.quantity_list_json[0] if est.quantity_list_json else 1000
    return _detail_from_estimate(est, qty)


@router.get("/{costing_id}/phieu")
def get_costing_phieu(
    costing_id: int,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    qty: int | None = Query(default=None),
) -> dict:
    """Kết quả tính giá của 1 phiếu gom thành 4 nhóm (A Giấy · B Công in · C Chế bản ·
    D Gia công sau in) + tổng giá vốn, phục vụ in "Phiếu tính giá".

    `qty` chọn mức số lượng muốn in; bỏ trống ⇒ lấy phương án đầu tiên của phiếu."""
    try:
        est = svc.get_estimate(costing_id)
    except EstimateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương án tính giá.",
        ) from None
    return estimate_to_phieu(est, qty)


@router.put("/{costing_id}", response_model=CostingDetailOut)
def update_costing(
    costing_id: int,
    payload: CostingUpdate,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> CostingDetailOut:
    if not payload.paper_options:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cần ít nhất 1 phương án giấy.",
        )

    paper = payload.paper_options[0]
    if paper.pieces_per_sheet <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Phương án giấy 1: số con/khổ phải lớn hơn 0.",
        )

    input_spec = {
        "product_id": payload.product_id,
        "sheet_w": paper.sheet_w,
        "sheet_h": paper.sheet_h,
        "pieces_per_sheet": paper.pieces_per_sheet,
        "grain_locked": paper.grain_locked,
        "material_id": paper.sheet_paper_master_id,
        "operations": [
            {
                "operation_key": op.name,
                "sequence": op.sequence,
                "execution_mode": op.execution_mode,
            }
            for op in payload.operations
        ],
    }

    for op in payload.operations:
        if op.execution_mode not in ("internal", "outsourced"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Công đoạn: hình thức thực hiện không hợp lệ.",
            )

    product_type = "brochure"
    product_name = "Sản phẩm mẫu"
    if payload.product_id:
        try:
            from ..services import costing_ports

            prod = costing_ports.get_product_for_costing(payload.product_id)
            if prod:
                product_type = prod.get("product_type") or "brochure"
                product_name = prod.get("name") or "Sản phẩm mẫu"
        except Exception:
            pass

    status_to_use = "calculated" if payload.status == "ready" else (payload.status or "draft")

    try:
        est = svc.update_estimate(
            estimate_id=costing_id,
            product_type=product_type,
            product_name=product_name,
            quantity_list=[payload.qty_final],
            input_spec=input_spec,
            actor_id=user.id,
            status=status_to_use,
            allow_blocking=True,
        )
    except EstimateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương án tính giá.",
        ) from None
    except EstimateValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    except EstimateInUse as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)
        ) from None

    return _detail_from_estimate(est, payload.qty_final)


@router.delete(
    "/{costing_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
def delete_costing(
    costing_id: int,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_estimate(estimate_id=costing_id, actor_id=user.id)
    except EstimateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương án tính giá.",
        ) from None
    except EstimateInUse as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
