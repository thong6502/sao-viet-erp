"""Norm Service — business logic for norms and waste configuration.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from ..repositories.norm_repo import NormRepository
from ..repositories.audit_repo import AuditLogRepository
from ..models.norm import Norm, GROUP_TO_KEY, KEY_TO_GROUP, WASTE_GROUPS, METHODS_BY_GROUP

VALID_NORM_KEYS = {
    "yield_rate",
    "running_waste_pct",
    "makeready_per_color_side",
    # Hao giấy riêng (danh mục #7 — PAPER_EXTRA_WASTE) → cộng vào số tờ mua giấy.
    "paper_extra_waste",
    # Legacy — vẫn chấp nhận để không phá dữ liệu/đường cũ (migration quy về yield_rate).
    "waste_pct_of_operation",
    # #1 — đơn giá mực in offset (đ / 1000 lượt-màu). pricing_engine tính tiền mực = ⌈lượt/1000⌉ × giá.
    "ink_cost_per_1000_impressions",
}

# Các key bù hao là phân số [0,1) (khác yield_rate là (0,1]).
_WASTE_KEYS = {"running_waste_pct", "waste_pct_of_operation"}

# Context lookup chỉ hỗ trợ 2 chiều này; norm gắn context key khác sẽ KHÔNG khớp lookup nào.
SUPPORTED_CONTEXT_KEYS = {"colors", "sides"}

class NormError(Exception):
    pass

class NormValidationError(NormError):
    pass

class NormNotFoundError(NormError):
    pass

class NormLookupContext:
    def __init__(
        self,
        product_type: str | None = None,
        machine_id: int | None = None,
        operation_id: int | None = None,
        operation_key: str | None = None,
        quantity: int | None = None,
        colors: int | None = None,
        sides: int | None = None,
        at_date: date | None = None,
    ) -> None:
        self.product_type = product_type
        self.machine_id = machine_id
        self.operation_id = operation_id
        self.operation_key = operation_key
        self.quantity = quantity
        self.colors = colors
        self.sides = sides
        self.at_date = at_date or date.today()

def canonicalize_context(context: dict[str, Any] | None) -> str:
    """Produce a canonical sorted string representation of context dictionary."""
    if not context:
        return "{}"
    sorted_items = sorted((str(k), v) for k, v in context.items())
    return "|".join(f"{k}={v}" for k, v in sorted_items)

def _calculate_specificity_score(norm: Norm) -> int:
    """Higher = more specific → thắng khi chọn norm. product/machine/operation_id = 10 điểm,
    operation_key = 5, có dải số lượng (#12/#20) = 5, cộng 1 điểm mỗi chiều context."""
    score = 0
    if norm.product_type is not None:
        score += 10
    if norm.machine_id is not None:
        score += 10
    if norm.operation_id is not None:
        score += 10
    # operation_key gets 5 points, only counted if operation_id is None
    if norm.operation_id is None and norm.operation_key is not None:
        score += 5
    # #12/#20 — norm giới hạn theo dải số lượng đặc thù hơn norm không giới hạn số lượng.
    if norm.qty_min is not None or norm.qty_max is not None:
        score += 5
    # Context match score
    if norm.context:
        score += len(norm.context)
    # Phạm vi áp dụng multi-select đặc thù hơn rule áp dụng chung.
    if getattr(norm, "applicable_product_types", None):
        score += 3
    if getattr(norm, "applicable_machine_ids", None):
        score += 3
    return score

class NormService:
    def __init__(
        self,
        repo: NormRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.repo = repo
        self.audit = audit

    def _find_norm_candidate(self, norm_key: str, lookup_ctx: NormLookupContext) -> Norm | None:
        """Pick the most-specific active norm matching the context, or None.

        Dùng chung bởi get_norm (trả về value) và pricing_engine (cần id norm cho snapshot
        dòng chi phí — #19). Chọn = ứng viên từ repo → lọc context in-memory (colors/sides;
        BẤT KỲ context key khác nghĩa là norm KHÔNG áp dụng — #11) → chấm specificity →
        phá hòa effective_from DESC, id DESC.
        """
        candidates = self.repo.get_candidates(
            norm_key=norm_key,
            product_type=lookup_ctx.product_type,
            machine_id=lookup_ctx.machine_id,
            operation_id=lookup_ctx.operation_id,
            operation_key=lookup_ctx.operation_key,
            quantity=lookup_ctx.quantity,
            at_date=lookup_ctx.at_date,
        )

        valid_candidates = []
        for cand in candidates:
            # Phạm vi áp dụng multi-select: rule có applicable_product_types/_machine_ids thì
            # chỉ khớp khi loại SP / máy của lookup nằm trong danh sách (NULL/[] = tất cả).
            apt = getattr(cand, "applicable_product_types", None)
            if apt:
                if lookup_ctx.product_type is None or lookup_ctx.product_type not in apt:
                    continue
            aml = getattr(cand, "applicable_machine_ids", None)
            if aml:
                if lookup_ctx.machine_id is None or lookup_ctx.machine_id not in aml:
                    continue
            # Check context filters in memory (colors, sides)
            if cand.context:
                mismatch = False
                for k, v in cand.context.items():
                    if k == "colors":
                        if lookup_ctx.colors is None or lookup_ctx.colors != v:
                            mismatch = True
                            break
                    elif k == "sides":
                        if lookup_ctx.sides is None or lookup_ctx.sides != v:
                            mismatch = True
                            break
                    else:
                        # #11 — context key ngoài colors/sides KHÔNG được coi là khớp im lặng;
                        # lookup không mang chiều này nên norm không áp dụng.
                        mismatch = True
                        break
                if mismatch:
                    continue
            valid_candidates.append(cand)

        if not valid_candidates:
            return None

        # Sort: specificity DESC, priority DESC (§7 phá hòa tay), effective_from DESC, id DESC
        valid_candidates.sort(
            key=lambda x: (
                _calculate_specificity_score(x),
                int(getattr(x, "priority", 0) or 0),
                x.effective_from,
                x.id,
            ),
            reverse=True,
        )
        return valid_candidates[0]

    def get_norm(self, norm_key: str, lookup_ctx: NormLookupContext) -> float:
        """Retrieve the specificity-scored active norm value matching the context."""
        cand = self._find_norm_candidate(norm_key, lookup_ctx)
        if cand is None:
            raise NormNotFoundError(f"Không tìm thấy định mức cho key '{norm_key}' trong ngữ cảnh hiện tại.")
        return float(cand.value)

    def list_norms(
        self,
        *,
        norm_key: str | None = None,
        product_type: str | None = None,
        machine_id: int | None = None,
        operation_id: int | None = None,
        only_current: bool = False,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Norm], int]:
        return self.repo.list_norms(
            norm_key=norm_key,
            product_type=product_type,
            machine_id=machine_id,
            operation_id=operation_id,
            only_current=only_current,
            page=page,
            size=size,
        )

    def create_norm(
        self,
        *,
        norm_key: str | None = None,
        waste_group: str | None = None,
        calculation_method: str | None = None,
        value: float = 0.0,
        code: str | None = None,
        name: str | None = None,
        product_type: str | None = None,
        machine_id: int | None = None,
        operation_id: int | None = None,
        operation_key: str | None = None,
        applicable_product_types: list | None = None,
        applicable_machine_ids: list | None = None,
        qty_min: int | None = None,
        qty_max: int | None = None,
        context: dict | None = None,
        setup_waste_qty: float | None = None,
        setup_waste_per_color: float | None = None,
        setup_waste_per_side: float | None = None,
        min_waste_qty: float | None = None,
        max_waste_qty: float | None = None,
        paper_add_to_purchase: bool = True,
        priority: int = 100,
        effective_from: date,
        note: str | None = None,
        actor: Any,
    ) -> Norm:
        # Suy norm_key ⇄ waste_group (nhận một trong hai — backward-compat API cũ).
        if not norm_key and waste_group:
            norm_key = GROUP_TO_KEY.get(waste_group)
        if norm_key and not waste_group:
            waste_group = KEY_TO_GROUP.get(norm_key)
        if not norm_key:
            raise NormValidationError("Thiếu nhóm định mức (waste_group) hoặc mã khóa (norm_key).")

        # Validate norm key
        if norm_key not in VALID_NORM_KEYS:
            raise NormValidationError(f"Mã định mức '{norm_key}' không hợp lệ.")
        if waste_group is not None and waste_group not in WASTE_GROUPS:
            raise NormValidationError(f"Nhóm định mức '{waste_group}' không hợp lệ.")
        if (
            calculation_method is not None
            and waste_group in METHODS_BY_GROUP
            and calculation_method not in METHODS_BY_GROUP[waste_group]
        ):
            raise NormValidationError(
                f"Cách tính '{calculation_method}' không hợp lệ cho nhóm {waste_group}."
            )

        # Validate values
        if value < 0:
            raise NormValidationError("Giá trị định mức không được âm.")
        if norm_key == "yield_rate":
            if value <= 0 or value > 1:
                raise NormValidationError("Tỷ lệ đạt (yield_rate) phải lớn hơn 0 và nhỏ hơn hoặc bằng 1.")
        # Bù hao là phân số < 1 (100%); >=1 gây chia-cho-0/âm ở khâu tính sản lượng.
        if norm_key in _WASTE_KEYS and value >= 1:
            raise NormValidationError("Tỷ lệ bù hao phải nhỏ hơn 1 (100%).")

        # §7 — min/max bù hao.
        if min_waste_qty is not None and max_waste_qty is not None and max_waste_qty < min_waste_qty:
            raise NormValidationError("Bù hao tối đa không được nhỏ hơn bù hao tối thiểu.")

        # #11 — chặn tạo norm với context key sẽ không bao giờ khớp lookup (chỉ hỗ trợ colors/sides).
        if context:
            unknown = set(context.keys()) - SUPPORTED_CONTEXT_KEYS
            if unknown:
                raise NormValidationError(
                    f"Ngữ cảnh chỉ hỗ trợ {sorted(SUPPORTED_CONTEXT_KEYS)}; không hỗ trợ: {sorted(unknown)}."
                )

        # Check operation exclusivity constraint
        if operation_id is not None and operation_key is not None:
            raise NormValidationError("Chỉ được nhập một trong hai: ID công đoạn hoặc từ khóa công đoạn.")

        # Validate qty bounds
        if qty_min is not None and qty_min < 0:
            raise NormValidationError("Số lượng tối thiểu không được âm.")
        if qty_max is not None and qty_max < 0:
            raise NormValidationError("Số lượng tối đa không được âm.")
        if qty_min is not None and qty_max is not None and qty_max < qty_min:
            raise NormValidationError("Số lượng tối đa không được nhỏ hơn số lượng tối thiểu.")

        # Service-side canonicalization of context key
        context_key = canonicalize_context(context)

        # Date Overlap protection (sequential versions only)
        current = self.repo.get_active_norm_matching_config(
            norm_key=norm_key,
            product_type=product_type,
            machine_id=machine_id,
            operation_id=operation_id,
            operation_key=operation_key,
            qty_min=qty_min,
            qty_max=qty_max,
            context_key=context_key,
        )
        if current:
            if effective_from <= current.effective_from:
                raise NormValidationError(
                    f"Ngày hiệu lực mới ({effective_from}) phải lớn hơn ngày bắt đầu hiện tại ({current.effective_from})."
                )

        norm = self.repo.add_norm(
            norm_key=norm_key,
            value=value,
            product_type=product_type,
            machine_id=machine_id,
            operation_id=operation_id,
            operation_key=operation_key,
            qty_min=qty_min,
            qty_max=qty_max,
            context=context,
            context_key=context_key,
            effective_from=effective_from,
            note=note,
            waste_group=waste_group,
            calculation_method=calculation_method,
            code=code,
            name=name,
            applicable_product_types=applicable_product_types,
            applicable_machine_ids=applicable_machine_ids,
            setup_waste_qty=setup_waste_qty,
            setup_waste_per_color=setup_waste_per_color,
            setup_waste_per_side=setup_waste_per_side,
            min_waste_qty=min_waste_qty,
            max_waste_qty=max_waste_qty,
            paper_add_to_purchase=paper_add_to_purchase,
            priority=priority,
            created_by=getattr(actor, "id", None),
        )

        self.audit.create(
            actor_user_id=actor.id,
            action="create_norm",
            target=f"norm:{norm.id}",
            detail=f"Tạo định mức {code or norm_key}={value} áp dụng từ {effective_from}",
        )
        return norm

    def get_history(self, norm_id: int) -> list[Norm]:
        norm = self.repo.get_by_id(norm_id)
        if not norm:
            raise NormNotFoundError("Không tìm thấy định mức.")
        return self.repo.list_history(norm)

    def duplicate_norm(self, *, norm_id: int, effective_from: date, code: str | None, actor: Any) -> Norm:
        """Sao chép một rule sang cấu hình y hệt nhưng ngày hiệu lực mới (tạo version kế tiếp)."""
        src = self.repo.get_by_id(norm_id)
        if not src:
            raise NormNotFoundError("Không tìm thấy định mức để sao chép.")
        return self.create_norm(
            norm_key=src.norm_key,
            waste_group=src.waste_group,
            calculation_method=src.calculation_method,
            value=float(src.value),
            code=code or (f"{src.code}_COPY" if src.code else None),
            name=src.name,
            product_type=src.product_type,
            machine_id=src.machine_id,
            operation_id=src.operation_id,
            operation_key=src.operation_key,
            applicable_product_types=src.applicable_product_types,
            applicable_machine_ids=src.applicable_machine_ids,
            qty_min=src.qty_min,
            qty_max=src.qty_max,
            context=src.context,
            setup_waste_qty=float(src.setup_waste_qty) if src.setup_waste_qty is not None else None,
            setup_waste_per_color=float(src.setup_waste_per_color) if src.setup_waste_per_color is not None else None,
            setup_waste_per_side=float(src.setup_waste_per_side) if src.setup_waste_per_side is not None else None,
            min_waste_qty=float(src.min_waste_qty) if src.min_waste_qty is not None else None,
            max_waste_qty=float(src.max_waste_qty) if src.max_waste_qty is not None else None,
            paper_add_to_purchase=bool(src.paper_add_to_purchase),
            priority=int(src.priority or 100),
            effective_from=effective_from,
            note=src.note,
            actor=actor,
        )

    def simulate(self, params: Any) -> dict:
        """Test nhanh (§4.2 Khối 5): chạy chuỗi số tờ theo định mức hiện hành, không ghi DB.

        Tái dùng đúng công thức engine qua các helper _compute_* để số Test khớp màn Tính giá.
        """
        import math
        from .pricing_engine import _compute_setup_sheets, _compute_running_sheets, _compute_paper_extra

        at_date = params.at_date or date.today()
        colors = int(params.colors)
        sides = int(params.sides)
        forms = int(params.forms)
        pps = max(1, int(params.pieces_per_sheet))
        steps: list[dict] = []
        warnings: list[str] = []

        theoretical = int(math.ceil(params.quantity / pps))

        # Chuỗi ngược qua công đoạn (đảo thứ tự sản xuất).
        current = int(params.quantity)
        for op_key in reversed(params.operation_keys or []):
            ctx = NormLookupContext(
                product_type=params.product_type, operation_key=op_key,
                quantity=current, at_date=at_date,
            )
            yrec = self._candidate_op("yield_rate", ctx)
            yv = float(yrec.value) if yrec else 1.0
            srec = self._candidate_op("makeready_per_color_side", ctx)
            setup = int(round(_compute_setup_sheets(srec, colors, sides))) if srec else 0
            before = int(math.ceil(current / yv)) + setup
            steps.append({
                "label": f"Công đoạn {op_key}",
                "detail": f"ceil({current} / {yv:g}) + setup {setup} = {before} sản phẩm",
                "rule_code": (yrec.code if yrec else None),
                "value": yv,
            })
            current = before

        required_before_print = current
        printed = int(math.ceil(required_before_print / pps))

        print_ctx = NormLookupContext(
            product_type=params.product_type, machine_id=params.machine_id,
            colors=colors, sides=sides, quantity=params.quantity, at_date=at_date,
        )
        # Tỷ lệ đạt in (không gắn CĐ).
        yrec = self._candidate_noop("yield_rate", print_ctx)
        print_yield = float(yrec.value) if yrec else 1.0
        after_yield = int(math.ceil(printed / print_yield))
        steps.append({
            "label": "Tỷ lệ đạt in", "detail": f"ceil({printed} / {print_yield:g}) = {after_yield} tờ",
            "rule_code": (yrec.code if yrec else None), "value": print_yield,
        })

        mrec = self._candidate_noop("makeready_per_color_side", print_ctx)
        makeready = int(math.ceil(_compute_setup_sheets(mrec, colors, sides) * forms)) if mrec else 0
        steps.append({
            "label": "Makeready", "detail": f"{makeready} tờ",
            "rule_code": (mrec.code if mrec else None),
        })

        rrec = self._candidate_noop("running_waste_pct", print_ctx)
        running = int(_compute_running_sheets(rrec, after_yield)) if rrec else 0
        steps.append({
            "label": "Running waste", "detail": f"ceil({after_yield} × {float(rrec.value) if rrec else 0:g}) = {running} tờ",
            "rule_code": (rrec.code if rrec else None), "value": float(rrec.value) if rrec else 0.0,
        })

        production = after_yield + makeready + running
        steps.append({"label": "Số tờ sản xuất", "detail": f"{after_yield} + {makeready} + {running} = {production} tờ"})

        prec = self._candidate_noop("paper_extra_waste", print_ctx)
        paper_extra = int(_compute_paper_extra(prec, production)) if prec and bool(prec.paper_add_to_purchase) else 0
        purchase = production + paper_extra
        steps.append({
            "label": "Số tờ mua giấy", "detail": f"{production} + hao giấy {paper_extra} = {purchase} tờ",
            "rule_code": (prec.code if prec else None),
        })

        return {
            "theoretical_sheets": theoretical,
            "required_before_print": required_before_print,
            "sheets_after_yield": after_yield,
            "makeready_sheets": makeready,
            "running_sheets": after_yield + running,
            "production_sheets": production,
            "paper_extra_sheets": paper_extra,
            "purchase_sheets": purchase,
            "steps": steps,
            "warnings": warnings,
        }

    def _candidate_op(self, key: str, ctx: NormLookupContext):
        """Ứng viên gắn công đoạn (bỏ norm chung) — cho Test nhanh."""
        rec = self._find_norm_candidate(key, ctx)
        if rec is None or (rec.operation_id is None and rec.operation_key is None):
            return None
        return rec

    def _candidate_noop(self, key: str, ctx: NormLookupContext):
        """Ứng viên KHÔNG gắn công đoạn (norm khâu in / chung) — cho Test nhanh."""
        rec = self._find_norm_candidate(key, ctx)
        if rec is None:
            return None
        if key != "running_waste_pct" and (rec.operation_id is not None or rec.operation_key is not None):
            return None
        return rec

    def close_norm(
        self,
        *,
        norm_id: int,
        effective_to: date,
        actor: Any,
    ) -> Norm:
        """Manually close/terminate a norm rule by setting its effective_to date."""
        norm = self.repo.get_by_id(norm_id)
        if not norm:
            raise NormNotFoundError("Không tìm thấy định mức.")

        if effective_to <= norm.effective_from:
            raise NormValidationError("Ngày kết thúc hiệu lực phải lớn hơn ngày bắt đầu.")

        norm.effective_to = effective_to
        norm.updated_at = datetime.now(timezone.utc)
        self.repo.db.add(norm)
        self.repo.db.commit()

        self.audit.create(
            actor_user_id=actor.id,
            action="close_norm",
            target=f"norm:{norm.id}",
            detail=f"Đóng định mức {norm.norm_key} tại ngày {effective_to}",
        )
        return norm

    def delete_norm(
        self,
        *,
        norm_id: int,
        actor: Any,
    ) -> None:
        """Only future and unused norms can be deleted. Active/past norms are closed instead."""
        norm = self.repo.get_by_id(norm_id)
        if not norm:
            raise NormNotFoundError("Không tìm thấy định mức.")

        today = date.today()
        # If the norm is already active (effective_from <= today), it cannot be deleted
        if norm.effective_from <= today:
            raise NormValidationError("Không thể xóa cứng định mức đã hoặc đang hiệu lực. Hãy dùng chức năng Đóng.")

        # #1 — norm tương lai này (khi tạo) đã ĐÓNG norm tiền nhiệm (effective_to = effective_from
        # của nó). Xóa cứng mà không mở lại tiền nhiệm sẽ để lại khoảng trống định mức từ ngày đó.
        predecessor = self.repo.find_predecessor(norm)
        self.repo.db.delete(norm)
        self.repo.db.flush()  # áp DELETE trước, tránh 2 hàng effective_to NULL cùng lúc (unique index)
        if predecessor is not None:
            predecessor.effective_to = None
            self.repo.db.add(predecessor)
        self.repo.db.commit()

        self.audit.create(
            actor_user_id=actor.id,
            action="delete_norm",
            target=f"norm:{norm_id}",
            detail=f"Xóa định mức tương lai {norm.norm_key}",
        )
