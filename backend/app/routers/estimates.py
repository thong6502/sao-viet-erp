"""Official routes for Estimate API — spec-08 / Phase 2A.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..deps import get_db, get_estimate_service, require_permission
from ..models.user import User
from ..schemas.estimate import (
    EstimateCreate,
    EstimateListOut,
    EstimateOut,
    EstimatePreviewIn,
    EstimatePreviewLineOut,
    EstimatePreviewOut,
    EstimateRow,
    EstimateStatsOut,
    EstimateUpdate,
)
from ..services.estimate_service import (
    EstimateInUse,
    EstimateNotFound,
    EstimateService,
    EstimateValidationError,
)

router = APIRouter(prefix="/api/estimates", tags=["estimates"])

MODULE = "tinh_gia_thanh"

def _fmt_dim(v: object) -> str:
    """10.0 → '10', 29.7 → '29,7' (hiển thị kích thước kiểu vi-VN)."""
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f.is_integer() else f"{f:g}".replace(".", ",")


def _spec_summary(spec: dict, material_names: dict[int, str]) -> str | None:
    """Dòng spec 2 tầng cho list: '21×29,7 cm · Couche 150gsm · 4 màu/2 mặt'."""
    parts: list[str] = []
    w, h = spec.get("finished_width"), spec.get("finished_height")
    if w and h:
        parts.append(f"{_fmt_dim(w)}×{_fmt_dim(h)} cm")
    mat = material_names.get(spec.get("material_id"))
    if mat:
        parts.append(mat)
    colors = spec.get("colors")
    if colors:
        sides = spec.get("sides")
        parts.append(f"{colors} màu" + (f"/{sides} mặt" if sides else ""))
    return " · ".join(parts) or None


@router.get("", response_model=EstimateListOut)
def list_estimates(
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    product_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    has_blocking: bool | None = Query(default=None),
    sort: str = "estimate_number",
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> EstimateListOut:
    rows, total = svc.list_estimates(
        q=q,
        product_type=product_type,
        status=status,
        has_blocking=has_blocking,
        sort=sort,
        page=page,
        size=size
    )

    # Prefetch tên hiển thị (khách, vật liệu, máy, người lập) cho trang hiện tại — tránh N+1
    from sqlalchemy import select as _select
    from ..models.customer import Customer
    from ..models.material import Material
    from ..models.machine import Machine

    customer_ids = {est.customer_id for est in rows if est.customer_id}
    material_ids = {(est.input_spec_json or {}).get("material_id") for est in rows}
    machine_ids = {(est.input_spec_json or {}).get("machine_id") for est in rows}
    user_ids = {est.created_by for est in rows if est.created_by}
    material_ids.discard(None)
    machine_ids.discard(None)

    customer_names: dict[int, str] = {}
    if customer_ids:
        customer_names = dict(db.execute(
            _select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids))
        ).all())
    material_names: dict[int, str] = {}
    if material_ids:
        material_names = dict(db.execute(
            _select(Material.id, Material.name).where(Material.id.in_(material_ids))
        ).all())
    machine_types: dict[int, str] = {}
    if machine_ids:
        machine_types = dict(db.execute(
            _select(Machine.id, Machine.machine_type).where(Machine.id.in_(machine_ids))
        ).all())
    user_names: dict[int, str] = {}
    if user_ids:
        user_names = dict(db.execute(
            _select(User.id, User.name).where(User.id.in_(user_ids))
        ).all())

    items = []
    for est in rows:
        # compute min and max cost from options
        costs = [float(opt.total_cost) for opt in est.options]
        min_cost = min(costs) if costs else None
        max_cost = max(costs) if costs else None

        # giá vốn/đơn thấp nhất giữa các mức SL (option nào cũng có quantity > 0)
        unit_costs = [float(opt.total_cost) / opt.quantity for opt in est.options if opt.quantity]
        unit_cost_min = min(unit_costs) if unit_costs else None

        # count warnings and blocking errors
        warnings_count = 0
        blocking_error_count = 0
        for opt in est.options:
            if opt.warnings_json:
                for w in opt.warnings_json:
                    if w.get("severity") == "blocking_error":
                        blocking_error_count += 1
                    else:
                        warnings_count += 1

        spec = est.input_spec_json or {}
        items.append(EstimateRow(
            id=est.id,
            estimate_number=est.estimate_number,
            product_type=est.product_type,
            product_name=est.product_name,
            status=est.status,
            locked_at=est.locked_at,
            version=est.version,
            quantity_list_json=est.quantity_list_json,
            total_cost_min=min_cost,
            total_cost_max=max_cost,
            warnings_count=warnings_count,
            blocking_error_count=blocking_error_count,
            created_at=est.created_at,
            updated_at=est.updated_at,
            customer_id=est.customer_id,
            customer_name=customer_names.get(est.customer_id),
            spec_summary=_spec_summary(spec, material_names),
            machine_type=machine_types.get(spec.get("machine_id")),
            unit_cost_min=unit_cost_min,
            created_by_name=user_names.get(est.created_by),
        ))

    return EstimateListOut(
        items=items,
        total=total,
        page=page,
        size=size
    )


@router.get("/stats", response_model=EstimateStatsOut)
def estimate_stats(
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> EstimateStatsOut:
    """Số đếm cho thanh tab list (tổng / nháp / đã tính / có lỗi chặn)."""
    return EstimateStatsOut(**svc.stats())


@router.post("/preview", response_model=EstimatePreviewOut)
def preview_estimate(
    payload: EstimatePreviewIn,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> EstimatePreviewOut:
    """Live preview (KHÔNG lưu): chạy PricingEngine với spec đang gõ để form hiện giá vốn
    tức thời. Kết quả không ghi DB — bấm "Tính giá & Lưu" mới tạo phương án chính thức."""
    from ..services.pricing_engine import PricingEngine

    cost_lines, total_cost, warnings = PricingEngine(db).calculate_option(
        payload.input_spec, payload.quantity
    )
    return EstimatePreviewOut(
        total_cost=float(total_cost),
        cost_lines=[
            EstimatePreviewLineOut(
                category=line.category,
                description=line.description,
                total_cost=float(line.total_cost),
            )
            for line in cost_lines
        ],
        warnings=warnings,
    )


@router.post("", response_model=EstimateOut, status_code=status.HTTP_201_CREATED)
def create_estimate(
    payload: EstimateCreate,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> EstimateOut:
    try:
        est = svc.create_estimate(
            product_type=payload.product_type,
            product_name=payload.product_name,
            quantity_list=payload.quantity_list,
            input_spec=payload.input_spec,
            customer_id=payload.customer_id,
            actor_id=user.id,
            status=payload.status
        )
    except EstimateValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        ) from None
    
    return est


@router.get("/{estimate_id}", response_model=EstimateOut)
def get_estimate(
    estimate_id: int,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> EstimateOut:
    try:
        est = svc.get_estimate(estimate_id)
    except EstimateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương án tính giá."
        ) from None
    return est


@router.put("/{estimate_id}", response_model=EstimateOut)
def update_estimate(
    estimate_id: int,
    payload: EstimateUpdate,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> EstimateOut:
    try:
        est = svc.update_estimate(
            estimate_id=estimate_id,
            product_type=payload.product_type,
            product_name=payload.product_name,
            quantity_list=payload.quantity_list,
            input_spec=payload.input_spec,
            customer_id=payload.customer_id,
            actor_id=user.id,
            status=payload.status
        )
    except EstimateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương án tính giá."
        ) from None
    except EstimateValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        ) from None
    except EstimateInUse as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        ) from None
    return est


@router.delete("/{estimate_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_estimate(
    estimate_id: int,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_estimate(estimate_id=estimate_id, actor_id=user.id)
    except EstimateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương án tính giá."
        ) from None
    except EstimateInUse as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{estimate_id}/lock", response_model=EstimateOut)
def lock_estimate(
    estimate_id: int,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> EstimateOut:
    """§9 — Khóa snapshot phiếu (chốt kết quả, không cho sửa nữa)."""
    try:
        return svc.lock_estimate(estimate_id, actor_id=user.id)
    except EstimateNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phương án tính giá.") from None
    except EstimateValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None


@router.post("/{estimate_id}/duplicate", response_model=EstimateOut, status_code=status.HTTP_201_CREATED)
def duplicate_estimate(
    estimate_id: int,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> EstimateOut:
    """§7/§9 — Sao chép phiếu (làm mẫu / version mới nếu phiếu nguồn đã khóa)."""
    try:
        return svc.duplicate_estimate(estimate_id, actor_id=user.id)
    except EstimateNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phương án tính giá.") from None
    except EstimateValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None
