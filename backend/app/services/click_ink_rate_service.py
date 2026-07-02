"""Click/Ink Rate Service — business logic for click and ink rates.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from ..repositories.click_ink_rate_repo import ClickInkRateRepository
from ..repositories.audit_repo import AuditLogRepository
from ..models.click_ink_rate import ClickInkRate

VALID_TECHNOLOGIES = {"offset", "digital", "large_format", "flexo"}
VALID_COLOR_TYPES = {"cmyk", "grayscale", "spot", "white"}
VALID_UNITS = {"trang", "m2", "ml", "click"}

class ClickInkRateError(Exception):
    pass

class ClickInkRateValidationError(ClickInkRateError):
    pass

class ClickInkRateNotFoundError(ClickInkRateError):
    pass

class ClickInkRateService:
    def __init__(
        self,
        repo: ClickInkRateRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.repo = repo
        self.audit = audit

    def get_rate(self, rate_id: int) -> ClickInkRate:
        rate = self.repo.get_by_id(rate_id)
        if not rate:
            raise ClickInkRateNotFoundError("Không tìm thấy đơn giá click/mực.")
        return rate

    def list_rates(
        self,
        *,
        technology: str | None = None,
        machine_id: int | None = None,
        is_active: bool | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[ClickInkRate], int]:
        return self.repo.list_rates(
            technology=technology,
            machine_id=machine_id,
            is_active=is_active,
            page=page,
            size=size,
        )

    def create_rate(
        self,
        *,
        technology: str,
        color_type: str,
        machine_id: int | None = None,
        unit: str,
        unit_price: int,
        setup_fee: int = 0,
        min_charge: int = 0,
        effective_from: date,
        actor: Any,
    ) -> ClickInkRate:
        # Validations
        if technology not in VALID_TECHNOLOGIES:
            raise ClickInkRateValidationError(f"Công nghệ '{technology}' không hợp lệ.")
        if color_type not in VALID_COLOR_TYPES:
            raise ClickInkRateValidationError(f"Loại màu '{color_type}' không hợp lệ.")
        if unit not in VALID_UNITS:
            raise ClickInkRateValidationError(f"Đơn vị tính '{unit}' không hợp lệ.")
        
        if unit_price < 0:
            raise ClickInkRateValidationError("Đơn giá click không được âm.")
        if setup_fee < 0:
            raise ClickInkRateValidationError("Phí setup không được âm.")
        if min_charge < 0:
            raise ClickInkRateValidationError("Phí tối thiểu không được âm.")

        # Date Overlap protection (sequential versions only)
        current = self.repo.get_current_rate(technology, color_type, machine_id, unit)
        if current:
            if effective_from <= current.effective_from:
                raise ClickInkRateValidationError(
                    f"Ngày hiệu lực mới ({effective_from}) phải lớn hơn ngày bắt đầu hiện tại ({current.effective_from})."
                )
        # #2 — guard trên chỉ soi bản đang mở; sau close_rate/backdate có thể chồng lên một bản
        # ĐÃ ĐÓNG. Chặn nếu ngày hiệu lực mới rơi vào khoảng của một bản đã đóng.
        covering = self.repo.get_closed_rate_covering(technology, color_type, machine_id, unit, effective_from)
        if covering is not None:
            raise ClickInkRateValidationError(
                f"Ngày hiệu lực ({effective_from}) nằm trong khoảng đơn giá đã đóng "
                f"({covering.effective_from} → {covering.effective_to}); không được chồng lấn."
            )

        rate = self.repo.add_rate(
            technology=technology,
            color_type=color_type,
            machine_id=machine_id,
            unit=unit,
            unit_price=unit_price,
            setup_fee=setup_fee,
            min_charge=min_charge,
            effective_from=effective_from,
        )

        self.audit.create(
            actor_user_id=actor.id,
            action="create_click_ink_rate",
            target=f"click_ink_rate:{rate.id}",
            detail=f"Tạo đơn giá click {technology}/{color_type}={unit_price} từ {effective_from}",
        )
        return rate

    def close_rate(
        self,
        *,
        rate_id: int,
        effective_to: date,
        actor: Any,
    ) -> ClickInkRate:
        rate = self.get_rate(rate_id)
        if effective_to <= rate.effective_from:
            raise ClickInkRateValidationError("Ngày kết thúc hiệu lực phải lớn hơn ngày bắt đầu.")

        rate.effective_to = effective_to
        rate.updated_at = datetime.now(timezone.utc)
        self.repo.db.add(rate)
        self.repo.db.commit()

        self.audit.create(
            actor_user_id=actor.id,
            action="close_click_ink_rate",
            target=f"click_ink_rate:{rate.id}",
            detail=f"Đóng đơn giá click {rate.technology}/{rate.color_type} tại ngày {effective_to}",
        )
        return rate

    def delete_rate(
        self,
        *,
        rate_id: int,
        actor: Any,
    ) -> None:
        rate = self.get_rate(rate_id)
        
        today = date.today()
        # Non-retroactivity logic: only future rates can be hard-deleted
        if rate.effective_from <= today:
            raise ClickInkRateValidationError("Không thể xóa cứng đơn giá đã hoặc đang hiệu lực. Hãy dùng chức năng Đóng.")

        # #3 — bản tương lai này khi tạo đã đóng bản tiền nhiệm; xóa cứng mà không mở lại tiền
        # nhiệm sẽ để lại khoảng trống (không còn bản đang hiệu lực). Mở lại sau khi xóa.
        predecessor = self.repo.find_predecessor(rate)
        self.repo.db.delete(rate)
        self.repo.db.flush()  # áp DELETE trước, tránh 2 hàng effective_to NULL cùng lúc (unique index)
        if predecessor is not None:
            predecessor.effective_to = None
            self.repo.db.add(predecessor)
        self.repo.db.commit()

        self.audit.create(
            actor_user_id=actor.id,
            action="delete_click_ink_rate",
            target=f"click_ink_rate:{rate_id}",
            detail=f"Xóa đơn giá click tương lai {rate.technology}/{rate.color_type}",
        )
