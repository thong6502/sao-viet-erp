"""Plate/Die Rate Service — business logic for plate and die rates.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from ..repositories.plate_die_rate_repo import PlateDieRateRepository
from ..repositories.audit_repo import AuditLogRepository
from ..models.plate_die_rate import PlateDieRate

VALID_PLATE_TYPES = {"ban_kem_offset", "khuon_be", "khuon_ep_kim"}
VALID_TECHNOLOGIES = {"offset", "flexo", "be", "ep_kim"}
VALID_UNITS = {"ban", "bo", "cm2"}

class PlateDieRateError(Exception):
    pass

class PlateDieRateValidationError(PlateDieRateError):
    pass

class PlateDieRateNotFoundError(PlateDieRateError):
    pass

class PlateDieRateService:
    def __init__(
        self,
        repo: PlateDieRateRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.repo = repo
        self.audit = audit

    def get_rate(self, rate_id: int) -> PlateDieRate:
        rate = self.repo.get_by_id(rate_id)
        if not rate:
            raise PlateDieRateNotFoundError("Không tìm thấy đơn giá khuôn/bản kẽm.")
        return rate

    def list_rates(
        self,
        *,
        plate_type: str | None = None,
        technology: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PlateDieRate], int]:
        return self.repo.list_rates(
            plate_type=plate_type,
            technology=technology,
            is_active=is_active,
            page=page,
            size=size,
        )

    def create_rate(
        self,
        *,
        plate_type: str,
        technology: str,
        unit: str,
        unit_price: int,
        setup_fee: int = 0,
        min_charge: int = 0,
        reusable: bool = False,
        effective_from: date,
        actor: Any,
    ) -> PlateDieRate:
        # Validations
        if plate_type not in VALID_PLATE_TYPES:
            raise PlateDieRateValidationError(f"Loại khuôn/bản '{plate_type}' không hợp lệ.")
        if technology not in VALID_TECHNOLOGIES:
            raise PlateDieRateValidationError(f"Công nghệ gia công '{technology}' không hợp lệ.")
        if unit not in VALID_UNITS:
            raise PlateDieRateValidationError(f"Đơn vị tính '{unit}' không hợp lệ.")
        
        if unit_price < 0:
            raise PlateDieRateValidationError("Đơn giá không được âm.")
        if setup_fee < 0:
            raise PlateDieRateValidationError("Phí setup không được âm.")
        if min_charge < 0:
            raise PlateDieRateValidationError("Phí tối thiểu không được âm.")

        # Date Overlap protection (sequential versions only)
        current = self.repo.get_current_rate(plate_type, technology, unit)
        if current:
            if effective_from <= current.effective_from:
                raise PlateDieRateValidationError(
                    f"Ngày hiệu lực mới ({effective_from}) phải lớn hơn ngày bắt đầu hiện tại ({current.effective_from})."
                )
        # #14 — guard trên chỉ soi bản đang mở; chặn thêm nếu chồng lên một bản ĐÃ ĐÓNG.
        covering = self.repo.get_closed_rate_covering(plate_type, technology, unit, effective_from)
        if covering is not None:
            raise PlateDieRateValidationError(
                f"Ngày hiệu lực ({effective_from}) nằm trong khoảng đơn giá đã đóng "
                f"({covering.effective_from} → {covering.effective_to}); không được chồng lấn."
            )

        rate = self.repo.add_rate(
            plate_type=plate_type,
            technology=technology,
            unit=unit,
            unit_price=unit_price,
            setup_fee=setup_fee,
            min_charge=min_charge,
            reusable=reusable,
            effective_from=effective_from,
        )

        self.audit.create(
            actor_user_id=actor.id,
            action="create_plate_die_rate",
            target=f"plate_die_rate:{rate.id}",
            detail=f"Tạo đơn giá {plate_type}/{technology}={unit_price} từ {effective_from}",
        )
        return rate

    def close_rate(
        self,
        *,
        rate_id: int,
        effective_to: date,
        actor: Any,
    ) -> PlateDieRate:
        rate = self.get_rate(rate_id)
        if effective_to <= rate.effective_from:
            raise PlateDieRateValidationError("Ngày kết thúc hiệu lực phải lớn hơn ngày bắt đầu.")

        rate.effective_to = effective_to
        rate.updated_at = datetime.now(timezone.utc)
        self.repo.db.add(rate)
        self.repo.db.commit()

        self.audit.create(
            actor_user_id=actor.id,
            action="close_plate_die_rate",
            target=f"plate_die_rate:{rate.id}",
            detail=f"Đóng đơn giá {rate.plate_type}/{rate.technology} tại ngày {effective_to}",
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
            raise PlateDieRateValidationError("Không thể xóa cứng đơn giá đã hoặc đang hiệu lực. Hãy dùng chức năng Đóng.")

        # #4 — mở lại bản tiền nhiệm mà bản tương lai này đã đóng, tránh khoảng trống phủ giá.
        predecessor = self.repo.find_predecessor(rate)
        self.repo.db.delete(rate)
        self.repo.db.flush()  # áp DELETE trước, tránh 2 hàng effective_to NULL cùng lúc (unique index)
        if predecessor is not None:
            predecessor.effective_to = None
            self.repo.db.add(predecessor)
        self.repo.db.commit()

        self.audit.create(
            actor_user_id=actor.id,
            action="delete_plate_die_rate",
            target=f"plate_die_rate:{rate_id}",
            detail=f"Xóa đơn giá tương lai {rate.plate_type}/{rate.technology}",
        )
