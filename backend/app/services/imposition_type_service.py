"""Imposition Type Service — imposition/bình bài types master data.

Version-chain rule (spec E): editing a type that has already been used in a báo giá snapshot
(`used_count > 0`) does NOT mutate its coefficients in place — it supersedes the current row
(effective_to = today, deactivated) and inserts a new `version` carrying the edits, so frozen
quotes keep their numbers. Only "material" fields (the ones that change what the engine
computes) trigger a new version; lifecycle/condition edits (is_active, note, applicable_*,
priority…) update in place even when used.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from ..models.imposition_type import GROUP_KINDS, APPLIES_TO_SIDES
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.imposition_type_repo import ImpositionTypeRepository

# Fields whose change (while used_count>0) forces a new version — i.e. anything that alters
# what the engine computes for a given code/name.
_MATERIAL_FIELDS = (
    "name", "sides", "finished_factor", "pass_count", "plate_set_factor",
    "ink_pass_factor", "allow_rotate", "shared_plate_set", "group_kind",
)
# Fields the client may assign (code handled separately; version/used_count/audit are server-managed).
_ASSIGNABLE = (
    "name", "group_kind", "note", "is_active", "sides", "finished_factor", "pass_count",
    "plate_set_factor", "ink_pass_factor", "allow_rotate", "shared_plate_set", "technology",
    "applies_to_sides", "applicable_product_types", "applicable_machine_ids",
    "applicable_paper_size_ids", "allow_multi_signature", "priority",
    "effective_from", "effective_to",
)


class ImpositionTypeError(Exception):
    pass


class ImpositionTypeValidationError(ImpositionTypeError):
    pass


class ImpositionTypeDuplicate(ImpositionTypeError):
    pass


class ImpositionTypeNotFound(ImpositionTypeError):
    pass


def _norm(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, list):
        return tuple(v)
    return v


def _material_signature(get) -> tuple:
    return tuple(_norm(get(f)) for f in _MATERIAL_FIELDS)


class ImpositionTypeService:
    def __init__(
        self,
        repo: ImpositionTypeRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.repo = repo
        self.audit = audit

    # -- validation --------------------------------------------------------
    def _validate(self, data: dict, *, require_code: bool) -> None:
        if require_code and not (data.get("code") or "").strip():
            raise ImpositionTypeValidationError("Mã kiểu bình bài không được trống.")
        if not (data.get("name") or "").strip():
            raise ImpositionTypeValidationError("Tên kiểu bình bài không được trống.")
        if data.get("group_kind") not in GROUP_KINDS:
            raise ImpositionTypeValidationError("Nhóm kiểu không hợp lệ.")
        if data.get("applies_to_sides", "any") not in APPLIES_TO_SIDES:
            raise ImpositionTypeValidationError("Giá trị 'áp dụng cho số mặt' không hợp lệ.")
        if data.get("sides") not in (1, 2):
            raise ImpositionTypeValidationError("Số mặt in phải là 1 hoặc 2.")
        ff = data.get("finished_factor")
        if ff is None or ff <= 0:
            raise ImpositionTypeValidationError("Hệ số thành phẩm phải lớn hơn 0.")
        pc = data.get("pass_count")
        if pc is None or pc <= 0:
            raise ImpositionTypeValidationError("Số lượt qua máy phải lớn hơn 0.")
        psf = data.get("plate_set_factor")
        if psf is None or psf < 0:
            raise ImpositionTypeValidationError("Hệ số bộ kẽm không được âm.")
        ipf = data.get("ink_pass_factor")
        if ipf is None or ipf < 0:
            raise ImpositionTypeValidationError("Hệ số lượt in màu không được âm.")
        if int(data.get("priority", 100)) < 0:
            raise ImpositionTypeValidationError("Thứ tự ưu tiên không được âm.")
        ef, et = data.get("effective_from"), data.get("effective_to")
        if ef and et and et <= ef:
            raise ImpositionTypeValidationError("Ngày hết hiệu lực phải sau ngày bắt đầu.")

    def _assignable(self, data: dict) -> dict:
        out = {}
        for k in _ASSIGNABLE:
            if k in data:
                v = data[k]
                if k == "note":
                    v = v.strip() if isinstance(v, str) and v.strip() else None
                out[k] = v
        return out

    # -- reads -------------------------------------------------------------
    def list_items(
        self,
        *,
        q: str | None = None,
        code: str | None = None,
        is_active: bool | None = None,
        current_only: bool = False,
        sort: str = "priority",
        page: int = 1,
        size: int = 50,
    ):
        return self.repo.list(
            q=q, code=code, is_active=is_active, current_only=current_only,
            sort=sort, page=page, size=size,
        )

    @staticmethod
    def _windows_overlap(a_from, a_to, b_from, b_to) -> bool:
        """[from, to) windows overlap? None from = -inf, None to = +inf."""
        lo, hi = date.min, date.max
        af, at = a_from or lo, a_to or hi
        bf, bt = b_from or lo, b_to or hi
        return af < bt and bf < at

    def _assert_no_overlap(self, code: str, eff_from, eff_to, exclude_id: int | None) -> None:
        for sib in self.repo.versions_of(code, exclude_id=exclude_id):
            if self._windows_overlap(eff_from, eff_to, sib.effective_from, sib.effective_to):
                raise ImpositionTypeValidationError(
                    f"Ngày hiệu lực chồng lấn với phiên bản v{sib.version} của mã {code}."
                )

    def get_item(self, item_id: int):
        item = self.repo.get_by_id(item_id)
        if item is None:
            raise ImpositionTypeNotFound("Không tìm thấy kiểu bình bài.")
        return item

    # -- "Đang dùng trong" / drill-down -----------------------------------
    def estimate_counts(self) -> dict[str, int]:
        """{CODE: số tính giá} cho cột 'Đang dùng trong' của bảng danh sách."""
        return self.repo.estimate_code_counts()

    def usage(self, item_id: int) -> dict:
        """Danh sách tính giá (estimates) đang dùng quy tắc — cho drill-down."""
        item = self.get_item(item_id)
        estimates = self.repo.list_estimates_by_code(item.code)
        return {"code": item.code, "estimate_count": len(estimates), "estimates": estimates}

    # -- Kiểm thử nhanh (preview engine) ----------------------------------
    def preview(self, data: dict) -> dict:
        """Chạy thử quy tắc với input test — cùng công thức engine (imposition_math)."""
        from . import imposition_math

        ff = data.get("finished_factor")
        if ff is None or ff <= 0:
            raise ImpositionTypeValidationError("Hệ số thành phẩm phải lớn hơn 0.")
        pc = data.get("pass_count")
        if pc is None or pc <= 0:
            raise ImpositionTypeValidationError("Số lượt qua máy phải lớn hơn 0.")
        return imposition_math.preview(
            finished_factor=float(ff),
            pass_count=float(pc),
            plate_set_factor=float(data.get("plate_set_factor") or 0),
            ink_pass_factor=float(data.get("ink_pass_factor") or 0),
            geometric_pieces=int(data.get("geometric_pieces") or 0),
            quantity=int(data.get("quantity") or 0),
            production_sheets=int(data.get("production_sheets") or 0),
            colors=int(data.get("colors") or 0),
            forms=int(data.get("forms") or 1),
            machine_speed=float(data.get("machine_speed") or 0),
        )

    # -- writes ------------------------------------------------------------
    def create_item(self, data: dict, *, actor):
        self._validate(data, require_code=True)
        code = (data["code"] or "").strip().upper()
        if self.repo.find_by_code_any_version(code) is not None:
            raise ImpositionTypeDuplicate("Mã kiểu bình bài đã tồn tại.")
        if self.repo.find_by_name(data["name"].strip()) is not None:
            raise ImpositionTypeDuplicate("Tên kiểu bình bài đã tồn tại.")

        fields = self._assignable(data)
        fields["name"] = data["name"].strip()
        fields["created_by"] = getattr(actor, "id", None)
        fields["updated_by"] = getattr(actor, "id", None)
        try:
            item = self.repo.create(code=code, version=1, **fields)
        except IntegrityError:
            raise ImpositionTypeDuplicate("Mã hoặc tên kiểu bình bài đã tồn tại.") from None
        self.audit.create(
            actor_user_id=actor.id,
            action="create_imposition_type",
            target=f"imposition_type:{item.id}",
            detail=f"{item.code} - {item.name}",
        )
        return item

    def update_item(self, item_id: int, data: dict, *, actor):
        item = self.get_item(item_id)
        self._validate(data, require_code=False)

        new_name = data["name"].strip()
        dup = self.repo.find_by_name(new_name)
        if dup is not None and dup.code != item.code:
            raise ImpositionTypeDuplicate("Tên kiểu bình bài đã tồn tại.")

        material_changed = _material_signature(item.__getattribute__) != _material_signature(
            lambda f: (data.get(f).strip() if f == "name" and isinstance(data.get(f), str) else data.get(f))
        )

        fields = self._assignable(data)
        fields["name"] = new_name
        fields["updated_by"] = getattr(actor, "id", None)

        # Tạo phiên bản mới khi: (a) đã dùng trong báo giá + đổi hệ số, hoặc (b) user chủ động yêu cầu.
        force_version = bool(data.get("force_version"))
        if force_version or (int(item.used_count or 0) > 0 and material_changed):
            # Version-chain: keep the used row frozen, spin a new version with the edits.
            new_fields = dict(fields)
            new_fields.pop("effective_from", None)  # repo sets effective_from = today
            new_fields.pop("effective_to", None)    # new version starts open
            new_fields["created_by"] = getattr(actor, "id", None)
            new_fields.setdefault("is_active", True)
            try:
                new_item = self.repo.supersede_and_create_version(
                    item, effective_from=date.today(), **new_fields
                )
            except IntegrityError:
                raise ImpositionTypeDuplicate("Trùng phiên bản kiểu bình bài.") from None
            self.audit.create(
                actor_user_id=actor.id,
                action="version_imposition_type",
                target=f"imposition_type:{new_item.id}",
                detail=f"{new_item.code} v{new_item.version} (thay v{item.version} đã dùng {item.used_count} phiếu)",
            )
            return new_item

        # Sửa tại chỗ: ngày hiệu lực không được chồng lấn phiên bản khác cùng mã.
        self._assert_no_overlap(
            item.code, data.get("effective_from"), data.get("effective_to"), exclude_id=item.id
        )
        try:
            item = self.repo.update(item, **fields)
        except IntegrityError:
            raise ImpositionTypeDuplicate("Tên kiểu bình bài đã tồn tại.") from None
        self.audit.create(
            actor_user_id=actor.id,
            action="update_imposition_type",
            target=f"imposition_type:{item.id}",
            detail=f"{item.code} - {item.name}",
        )
        return item

    def delete_item(self, *, item_id: int, actor) -> None:
        item = self.get_item(item_id)
        if int(item.used_count or 0) > 0:
            raise ImpositionTypeValidationError(
                "Không thể xóa kiểu bình bài đã dùng trong báo giá — hãy tạm ngưng (Inactive) thay vì xóa."
            )
        code, name = item.code, item.name
        self.repo.delete(item)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_imposition_type",
            target=f"imposition_type:{item_id}",
            detail=f"{code} - {name}",
        )
