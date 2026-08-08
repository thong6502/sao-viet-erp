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


def _qty_overlap(amin, amax, bmin, bmax) -> bool:
    """Hai dải số lượng [min, max) có giao nhau không (None min=0, None max=∞)."""
    lo_a = amin if amin is not None else 0
    hi_a = amax if amax is not None else float("inf")
    lo_b = bmin if bmin is not None else 0
    hi_b = bmax if bmax is not None else float("inf")
    return lo_a < hi_b and lo_b < hi_a


def _scope_overlap(a: Norm, b: Norm) -> bool:
    """Hai định mức có thể cùng khớp một ca sản xuất không (mọi chiều phạm vi đều tương thích)."""
    # Loại sản phẩm (multi-select + legacy single); rỗng = tất cả.
    pa = set(a.applicable_product_types or ([] if a.product_type is None else [a.product_type]))
    pb = set(b.applicable_product_types or ([] if b.product_type is None else [b.product_type]))
    if pa and pb and pa.isdisjoint(pb):
        return False
    # Máy.
    ma = set(a.applicable_machine_ids or ([] if a.machine_id is None else [a.machine_id]))
    mb = set(b.applicable_machine_ids or ([] if b.machine_id is None else [b.machine_id]))
    if ma and mb and ma.isdisjoint(mb):
        return False
    # Công đoạn (chỉ so cùng loại định danh).
    if a.operation_id is not None and b.operation_id is not None and a.operation_id != b.operation_id:
        return False
    if a.operation_key is not None and b.operation_key is not None and a.operation_key != b.operation_key:
        return False
    # Dải số lượng.
    if not _qty_overlap(a.qty_min, a.qty_max, b.qty_min, b.qty_max):
        return False
    # Context (số màu / số mặt): chỉ xung khắc khi cả hai chỉ định và khác nhau.
    ca = a.context or {}
    cb = b.context or {}
    for k in ("colors", "sides"):
        va, vb = ca.get(k), cb.get(k)
        if va is not None and vb is not None and va != vb:
            return False
    return True


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
        q: str | None = None,
        norm_key: str | None = None,
        product_type: str | None = None,
        machine_id: int | None = None,
        operation_id: int | None = None,
        only_current: bool = False,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Norm], int]:
        return self.repo.list_norms(
            q=q,
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

        # Date Overlap protection (sequential versions only).
        # "1 quy tắc = 1 mã": nếu có mã, phiên bản kế tiếp phải hiệu lực sau bản đang mở cùng mã.
        # Mã mới (chưa có bản mở) = quy tắc mới → không ràng ngày. Rule không mã dùng lối cũ.
        if code:
            current = self.repo.get_open_by_code(code)
        else:
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

    def get_norm_by_id(self, norm_id: int) -> Norm:
        norm = self.repo.get_by_id(norm_id)
        if not norm:
            raise NormNotFoundError("Không tìm thấy định mức.")
        return norm

    def detect_conflicts(self) -> dict:
        """Tìm các cặp định mức cùng loại (norm_key) có thể cùng khớp một ca mà engine
        KHÔNG phân xử rõ được: phạm vi giao nhau + độ cụ thể BẰNG nhau (specificity ngang
        ⇒ chỉ còn ưu tiên/ngày phá hòa). Khác độ cụ thể thì rule cụ thể hơn thắng, không cảnh báo.
        """
        from collections import defaultdict

        rows = self.repo.list_open_norms()
        by_key: dict[str, list[Norm]] = defaultdict(list)
        for r in rows:
            by_key[r.norm_key].append(r)
        conflicts: dict[int, list[int]] = {}
        for group in by_key.values():
            scored = [(n, _calculate_specificity_score(n)) for n in group]
            for i, (a, sa) in enumerate(scored):
                for b, sb in scored[i + 1:]:
                    if sa != sb:
                        continue
                    if _scope_overlap(a, b):
                        conflicts.setdefault(a.id, []).append(b.id)
                        conflicts.setdefault(b.id, []).append(a.id)
        labels = {r.id: (r.code or r.name or r.norm_key) for r in rows if r.id in conflicts}
        return {"conflicts": conflicts, "labels": labels}

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
