"""Estimate Service — business logic for Estimates.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy.orm import Session

from ..models.estimate import Estimate, EstimateOption, EstimateCostLine
from ..repositories.estimate_repo import EstimateRepository
from ..repositories.audit_repo import AuditLogRepository
from .sequence_service import SequenceService
from .pricing_engine import PricingEngine

class EstimateError(Exception):
    """Base exception for estimate errors."""
    pass

class EstimateNotFound(EstimateError):
    """Estimate not found."""
    pass

class EstimateValidationError(EstimateError):
    """Estimate validation failed."""
    pass

class EstimateInUse(EstimateError):
    """Estimate is referenced by quote and cannot be deleted/modified."""
    pass


class EstimateService:
    def __init__(
        self,
        db: Session,
        repo: EstimateRepository,
        audit: AuditLogRepository,
        sequence: SequenceService
    ) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit
        self.sequence = sequence
        self.pricing_engine = PricingEngine(db)

    def _validate_spec(self, product_type: str, product_name: str, qty_list: list, input_spec: dict) -> None:
        if not product_type or not product_type.strip():
            raise EstimateValidationError("Loại sản phẩm là bắt buộc.")
        if not product_name or not product_name.strip():
            raise EstimateValidationError("Tên sản phẩm là bắt buộc.")
        if not isinstance(qty_list, list) or len(qty_list) == 0:
            raise EstimateValidationError("Danh sách số lượng tính giá không được trống.")
        for q in qty_list:
            if not isinstance(q, int) or q <= 0:
                raise EstimateValidationError("Số lượng tính giá phải là số nguyên dương lớn hơn 0.")
        if not isinstance(input_spec, dict):
            raise EstimateValidationError("Cấu hình thông số kỹ thuật (spec) không hợp lệ.")

    def get_estimate(self, estimate_id: int) -> Estimate:
        estimate = self.repo.get_by_id(estimate_id)
        if not estimate:
            raise EstimateNotFound("Không tìm thấy phương án tính giá.")
        return estimate

    def list_estimates(
        self,
        *,
        q: str | None = None,
        product_type: str | None = None,
        status: str | None = None,
        has_blocking: bool | None = None,
        sort: str = "estimate_number",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Estimate], int]:
        return self.repo.list_estimates(
            q=q,
            product_type=product_type,
            status=status,
            has_blocking=has_blocking,
            sort=sort,
            page=page,
            size=size
        )

    def stats(self) -> dict:
        return self.repo.stats()

    def create_estimate(
        self,
        *,
        product_type: str,
        product_name: str,
        quantity_list: list[int],
        input_spec: dict,
        customer_id: int | None = None,
        actor_id: int | None = None,
        status: str = "draft",
        allow_blocking: bool = False
    ) -> Estimate:
        self._validate_spec(product_type, product_name, quantity_list, input_spec)
        
        # Merge product info into input spec for engine
        spec_to_calc = dict(input_spec)
        spec_to_calc["product_type"] = product_type
        spec_to_calc["product_name"] = product_name

        # Begin Transaction for safe sequence code generation + calculation
        # The session is managed externally but we commit atomically here.
        estimate_number = self.sequence.generate_code("costing")
        
        estimate = Estimate(
            estimate_number=estimate_number,
            customer_id=customer_id,
            product_type=product_type,
            product_name=product_name,
            status="draft", # start with draft
            input_spec_json=input_spec,
            quantity_list_json=quantity_list,
            created_by=actor_id,
        )
        self.db.add(estimate)
        self.db.flush() # get estimate.id

        try:
            self._recalculate_options(estimate, spec_to_calc)
            
            # Final status logic: check if any option has blocking errors
            has_blocking = False
            for opt in estimate.options:
                if opt.warnings_json:
                    for w in opt.warnings_json:
                        if w.get("severity") == "blocking_error":
                            has_blocking = True
                            break
            
            if status == "calculated" and has_blocking and not allow_blocking:
                raise EstimateValidationError("Không thể chuyển sang trạng thái đã tính toán (calculated) do có lỗi chặn (blocking errors).")
            
            estimate.status = "calculated" if (status == "calculated" and (not has_blocking or allow_blocking)) else "draft"
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        if actor_id:
            self.audit.create(
                actor_user_id=actor_id,
                action="create_estimate",
                target=f"estimate:{estimate.id}",
                detail=f"Tạo phương án tính giá {estimate.estimate_number} cho SP {product_name} (SL={quantity_list})",
            )
        return estimate

    def update_estimate(
        self,
        estimate_id: int,
        *,
        product_type: str,
        product_name: str,
        quantity_list: list[int],
        input_spec: dict,
        customer_id: int | None = None,
        actor_id: int | None = None,
        status: str = "draft",
        allow_blocking: bool = False
    ) -> Estimate:
        estimate = self.get_estimate(estimate_id)
        if estimate.status == "converted_to_quote": # Phase 2C lock check
            raise EstimateInUse("Không thể chỉnh sửa phương án tính giá đã chuyển thành báo giá.")

        self._validate_spec(product_type, product_name, quantity_list, input_spec)

        spec_to_calc = dict(input_spec)
        spec_to_calc["product_type"] = product_type
        spec_to_calc["product_name"] = product_name

        estimate.product_type = product_type
        estimate.product_name = product_name
        estimate.input_spec_json = input_spec
        estimate.quantity_list_json = quantity_list
        estimate.customer_id = customer_id
        estimate.updated_at = datetime.now(timezone.utc)

        try:
            self._recalculate_options(estimate, spec_to_calc)

            has_blocking = False
            for opt in estimate.options:
                if opt.warnings_json:
                    for w in opt.warnings_json:
                        if w.get("severity") == "blocking_error":
                            has_blocking = True
                            break

            if status == "calculated" and has_blocking and not allow_blocking:
                raise EstimateValidationError("Không thể chuyển sang trạng thái đã tính toán (calculated) do có lỗi chặn (blocking errors).")

            estimate.status = "calculated" if (status == "calculated" and (not has_blocking or allow_blocking)) else "draft"
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        if actor_id:
            self.audit.create(
                actor_user_id=actor_id,
                action="update_estimate",
                target=f"estimate:{estimate.id}",
                detail=f"Cập nhật phương án tính giá {estimate.estimate_number} (SL={quantity_list})",
            )
        return estimate

    def delete_estimate(self, estimate_id: int, actor_id: int | None = None) -> None:
        estimate = self.get_estimate(estimate_id)
        if estimate.status == "converted_to_quote":
            raise EstimateInUse("Không thể xóa phương án tính giá đã chuyển thành báo giá.")
        
        estimate_number = estimate.estimate_number
        self.repo.delete(estimate)

        if actor_id:
            self.audit.create(
                actor_user_id=actor_id,
                action="delete_estimate",
                target=f"estimate:{estimate_id}",
                detail=f"Xóa phương án tính giá {estimate_number}",
            )

    def _recalculate_options(self, estimate: Estimate, spec_to_calc: dict) -> None:
        # Clear existing options
        estimate.options.clear()
        self.db.flush()

        for qty in estimate.quantity_list_json:
            cost_lines, total_cost, warnings = self.pricing_engine.calculate_option(spec_to_calc, qty)
            
            option = EstimateOption(
                quantity=qty,
                total_cost=total_cost,
                warnings_json=warnings,
                # Pricing placeholders (for Phase 2B/2C)
                margin_percent=0.0,
                selling_price=0.0,
                discount_amount=0.0,
                vat_percent=0.0,
                vat_amount=0.0,
                final_price=0.0,
                unit_price=0.0,
                actual_margin=0.0,
                included_in_quote=False
            )
            
            for line in cost_lines:
                option.cost_lines.append(line)
                
            estimate.options.append(option)
        
        self.db.flush()
