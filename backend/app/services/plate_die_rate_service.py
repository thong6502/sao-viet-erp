"""Plate/Die Rate Service — Đơn giá kẽm & khuôn (catalog #5).

Kẽm (`ban_kem_offset`) khai theo MÁY; khuôn (`khuon_*`) khai theo pricing_method. Versioning
hiệu lực-theo-ngày, family key = `code`: sửa một bản đã dùng ⇒ tạo version mới (đóng bản cũ).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from ..models.plate_die_rate import (
    PLATE_KEM, PRICING_METHODS, REUSE_METHODS, VALID_PLATE_TYPES, PlateDieRate,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.plate_die_rate_repo import ASSIGNABLE, PlateDieRateRepository

VALID_TECHNOLOGIES = {"offset", "flexo", "be", "ep_kim", "dap_noi"}
VALID_UNITS = {"ban", "bo", "cm2", "met"}


class PlateDieRateError(Exception):
    pass


class PlateDieRateValidationError(PlateDieRateError):
    pass


class PlateDieRateDuplicate(PlateDieRateError):
    pass


class PlateDieRateNotFoundError(PlateDieRateError):
    pass


class PlateDieRateService:
    def __init__(self, repo: PlateDieRateRepository, audit: AuditLogRepository) -> None:
        self.repo = repo
        self.audit = audit

    # -- reads -------------------------------------------------------------
    def get_rate(self, rate_id: int) -> PlateDieRate:
        rate = self.repo.get_by_id(rate_id)
        if not rate:
            raise PlateDieRateNotFoundError("Không tìm thấy đơn giá kẽm/khuôn.")
        return rate

    def list_rates(self, **kw) -> tuple[list[PlateDieRate], int]:
        return self.repo.list_rates(**kw)

    def history(self, rate_id: int) -> list[PlateDieRate]:
        return self.repo.list_versions(self.get_rate(rate_id).code)

    # -- validation --------------------------------------------------------
    def _validate(self, d: dict) -> None:
        if not (d.get("code") or "").strip():
            raise PlateDieRateValidationError("Mã bảng giá không được trống.")
        if not (d.get("name") or "").strip():
            raise PlateDieRateValidationError("Tên bảng giá không được trống.")
        plate_type = d.get("plate_type")
        if plate_type not in VALID_PLATE_TYPES:
            raise PlateDieRateValidationError(f"Loại kẽm/khuôn '{plate_type}' không hợp lệ.")
        if d.get("technology") not in VALID_TECHNOLOGIES:
            raise PlateDieRateValidationError("Công nghệ/công đoạn không hợp lệ.")
        if d.get("unit") not in VALID_UNITS:
            raise PlateDieRateValidationError("Đơn vị tính không hợp lệ.")
        for f, label in (("unit_price", "Đơn giá"), ("setup_fee", "Phí setup"),
                         ("min_charge", "Phí tối thiểu")):
            v = d.get(f) or 0
            if v < 0:
                raise PlateDieRateValidationError(f"{label} không được âm.")

        is_kem = plate_type == PLATE_KEM
        if is_kem:
            # Kẽm phải có đơn giá/bản (spec §11: khổ kẽm/máy/đơn giá).
            if not (d.get("unit_price") or 0) > 0:
                raise PlateDieRateValidationError("Đơn giá 1 bản kẽm phải lớn hơn 0.")
        else:
            method = d.get("pricing_method") or "fixed"
            if method not in PRICING_METHODS:
                raise PlateDieRateValidationError("Cách tính giá khuôn không hợp lệ.")
            if method == "fixed" and not (d.get("unit_price") or 0) > 0:
                raise PlateDieRateValidationError("Khuôn giá cố định phải có đơn giá > 0.")
            if method == "area" and not (d.get("unit_price_area") or 0) > 0:
                raise PlateDieRateValidationError("Cách tính theo diện tích phải có đơn giá/cm².")
            if method == "perimeter" and not (d.get("unit_price_perimeter") or 0) > 0:
                raise PlateDieRateValidationError("Cách tính theo chu vi phải có đơn giá/mét dao.")
            if d.get("reusable") and d.get("reuse_price_method") not in (None, *REUSE_METHODS):
                raise PlateDieRateValidationError("Cách tính phí dùng lại khuôn không hợp lệ.")
        mx = d.get("max_charge")
        if mx is not None and mx < (d.get("min_charge") or 0):
            raise PlateDieRateValidationError("Phí tối đa không được nhỏ hơn phí tối thiểu.")

    def _fields(self, d: dict) -> dict:
        out = {}
        for k in ASSIGNABLE:
            if k in d:
                out[k] = d[k]
        out["name"] = (d.get("name") or "").strip()
        return out

    # -- writes ------------------------------------------------------------
    def create_rate(self, data: dict, *, actor: Any) -> PlateDieRate:
        self._validate(data)
        code = (data["code"] or "").strip()
        if self.repo.find_by_code_any(code) is not None:
            raise PlateDieRateDuplicate("Mã bảng giá đã tồn tại.")
        fields = self._fields(data)
        fields["created_by"] = getattr(actor, "id", None)
        fields["updated_by"] = getattr(actor, "id", None)
        rate = self.repo.add_rate(code=code, effective_from=data["effective_from"], **fields)
        self._audit(actor, "create_plate_die_rate", rate, f"Tạo {rate.code} ({rate.plate_type})")
        return rate

    def create_version(self, rate_id: int, data: dict, *, actor: Any) -> PlateDieRate:
        """Tạo version mới (đóng bản đang mở của cùng mã)."""
        base = self.get_rate(rate_id)
        data = {**data, "code": base.code}
        self._validate(data)
        eff = data["effective_from"]
        current = self.repo.get_open_for_code(base.code)
        if current and eff <= current.effective_from:
            raise PlateDieRateValidationError(
                f"Ngày hiệu lực mới ({eff}) phải sau ngày bắt đầu bản hiện tại ({current.effective_from})."
            )
        if self.repo.get_closed_rate_covering(base.code, eff) is not None:
            raise PlateDieRateValidationError("Ngày hiệu lực chồng lấn với một bản đã đóng.")
        fields = self._fields(data)
        fields["created_by"] = getattr(actor, "id", None)
        fields["updated_by"] = getattr(actor, "id", None)
        rate = self.repo.add_rate(code=base.code, effective_from=eff, **fields)
        self._audit(actor, "version_plate_die_rate", rate, f"Version mới {rate.code} từ {eff}")
        return rate

    def clone_rate(self, rate_id: int, *, actor: Any) -> PlateDieRate:
        src = self.get_rate(rate_id)
        # Mã mới = code + _COPY (+ số nếu trùng)
        base_code = f"{src.code}_COPY"
        code = base_code
        i = 2
        while self.repo.find_by_code_any(code) is not None:
            code = f"{base_code}{i}"
            i += 1
        fields = {k: getattr(src, k) for k in ASSIGNABLE}
        fields["name"] = f"{src.name} (bản sao)"
        fields["created_by"] = getattr(actor, "id", None)
        fields["updated_by"] = getattr(actor, "id", None)
        rate = self.repo.add_rate(code=code, effective_from=src.effective_from, **fields)
        self._audit(actor, "clone_plate_die_rate", rate, f"Sao chép {src.code} → {rate.code}")
        return rate

    def close_rate(self, *, rate_id: int, effective_to: date, actor: Any) -> PlateDieRate:
        rate = self.get_rate(rate_id)
        if effective_to <= rate.effective_from:
            raise PlateDieRateValidationError("Ngày kết thúc phải lớn hơn ngày bắt đầu.")
        rate.effective_to = effective_to
        rate.updated_at = datetime.now(timezone.utc)
        self.repo.db.add(rate)
        self.repo.db.commit()
        self._audit(actor, "close_plate_die_rate", rate, f"Đóng {rate.code} tại {effective_to}")
        return rate

    def delete_rate(self, *, rate_id: int, actor: Any) -> None:
        rate = self.get_rate(rate_id)
        if rate.effective_from <= date.today():
            raise PlateDieRateValidationError(
                "Không thể xóa cứng đơn giá đã/đang hiệu lực. Hãy dùng chức năng Đóng."
            )
        predecessor = self.repo.find_predecessor(rate)
        self.repo.db.delete(rate)
        self.repo.db.flush()
        if predecessor is not None:
            predecessor.effective_to = None
            self.repo.db.add(predecessor)
        self.repo.db.commit()
        self.audit.create(
            actor_user_id=actor.id, action="delete_plate_die_rate",
            target=f"plate_die_rate:{rate_id}",
            detail=f"Xóa bản tương lai {rate.code}",
        )

    def _audit(self, actor, action: str, rate: PlateDieRate, detail: str) -> None:
        self.audit.create(
            actor_user_id=actor.id, action=action,
            target=f"plate_die_rate:{rate.id}", detail=detail,
        )
