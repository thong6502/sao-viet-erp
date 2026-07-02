"""Norm Service — business logic for norms and waste configuration.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from ..repositories.norm_repo import NormRepository
from ..repositories.audit_repo import AuditLogRepository
from ..models.norm import Norm

VALID_NORM_KEYS = {
    "yield_rate",
    "running_waste_pct",
    "makeready_per_color_side",
    # #10 — pricing_engine (chuỗi bù hao ngược) đọc key này cho TỪNG công đoạn; trước đây thiếu
    # nên bù hao mỗi công đoạn luôn kẹt mặc định 2%. TODO(SVN): xác nhận danh mục bù hao công đoạn.
    "waste_pct_of_operation",
    # #1 — đơn giá mực in offset (đ / 1000 lượt-màu). pricing_engine tính tiền mực = ⌈lượt/1000⌉ × giá.
    # Trước đây mực offset KHÔNG được tính vào giá thành. TODO(SVN): xác nhận đơn giá mực thực tế.
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

        # Sort: score DESC, effective_from DESC, id DESC
        valid_candidates.sort(
            key=lambda x: (_calculate_specificity_score(x), x.effective_from, x.id),
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
        norm_key: str,
        value: float,
        product_type: str | None = None,
        machine_id: int | None = None,
        operation_id: int | None = None,
        operation_key: str | None = None,
        qty_min: int | None = None,
        qty_max: int | None = None,
        context: dict | None = None,
        effective_from: date,
        note: str | None = None,
        actor: Any,
    ) -> Norm:
        # Validate norm key
        if norm_key not in VALID_NORM_KEYS:
            raise NormValidationError(f"Mã định mức '{norm_key}' không hợp lệ.")

        # Validate values
        if value < 0:
            raise NormValidationError("Giá trị định mức không được âm.")
        if norm_key == "yield_rate":
            if value <= 0 or value > 1:
                raise NormValidationError("Tỷ lệ thành phẩm (yield_rate) phải lớn hơn 0 và nhỏ hơn hoặc bằng 1.")
        # #10 — bù hao là phân số < 1 (100%); >=1 sẽ gây chia-cho-0/âm ở khâu tính sản lượng.
        if norm_key in _WASTE_KEYS and value >= 1:
            raise NormValidationError("Tỷ lệ bù hao phải nhỏ hơn 1 (100%).")

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
        )

        self.audit.create(
            actor_user_id=actor.id,
            action="create_norm",
            target=f"norm:{norm.id}",
            detail=f"Tạo định mức {norm_key}={value} áp dụng từ {effective_from}",
        )
        return norm

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
