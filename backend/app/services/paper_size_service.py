"""Paper Size Service — standard paper sizes master data.

Version-chain rule (spec E, mirror kiểu bình bài): sửa KÍCH THƯỚC (rộng/cao) một khổ đã dùng
(`used_count > 0`) KHÔNG sửa tại chỗ — nó đóng băng dòng cũ (effective_to = hôm nay, tắt) và
chèn `version` mới mang kích thước mới, để phiếu/báo giá cũ giữ nguyên số. Sửa các field vòng
đời/điều kiện (is_active, note, máy phù hợp, nhóm…) thì cập nhật tại chỗ kể cả khi đã dùng.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from ..models.paper_size import SIZE_GROUPS, PaperSize, summarize_size_type
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.paper_size_repo import PaperSizeRepository

# Field client được phép gán (code/version/used_count/audit do server quản).
_ASSIGNABLE = (
    "name", "size_group", "note", "is_active",
    "is_purchase_size", "is_print_sheet_size", "is_cut_size", "size_type",
    "width_cm", "height_cm", "allow_rotation",
    "compatible_machine_ids", "default_machine_id",
    "parent_size_id", "cut_count", "cut_waste_rate",
    "effective_from", "effective_to",
)
# Chỉ đổi các field này (khi used_count>0) mới ép version mới — tức KÍCH THƯỚC (spec §8).
_MATERIAL_FIELDS = ("width_cm", "height_cm")


class PaperSizeError(Exception):
    pass


class PaperSizeValidationError(PaperSizeError):
    pass


class PaperSizeDuplicate(PaperSizeError):
    pass


class PaperSizeNotFound(PaperSizeError):
    pass


def _f(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _fits_within(w: float, h: float, pw: float, ph: float) -> bool:
    """Khổ (w×h) lọt trong khổ cha (pw×ph), cho xoay."""
    return (w <= pw and h <= ph) or (h <= pw and w <= ph)


class PaperSizeService:
    def __init__(
        self,
        repo: PaperSizeRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.repo = repo
        self.audit = audit

    # -- normalize loại khổ (3 boolean) -----------------------------------
    def _normalize_type(self, data: dict) -> None:
        keys = ("is_purchase_size", "is_print_sheet_size", "is_cut_size")
        provided = any(data.get(k) is not None for k in keys)
        if provided:
            is_purchase = bool(data.get("is_purchase_size"))
            is_print = bool(data.get("is_print_sheet_size"))
            is_cut = bool(data.get("is_cut_size"))
        else:
            st = (data.get("size_type") or "").strip().lower()
            is_purchase = st in ("mua", "ca_hai")
            is_print = st in ("in", "ca_hai")
            is_cut = st == "cat"
            if not (is_purchase or is_print or is_cut):
                is_print = True  # mặc định: khổ tờ in
        data["is_purchase_size"] = is_purchase
        data["is_print_sheet_size"] = is_print
        data["is_cut_size"] = is_cut
        data["size_type"] = summarize_size_type(is_purchase, is_print, is_cut)

    # -- validation --------------------------------------------------------
    def _validate(self, data: dict, *, self_id: int | None = None) -> None:
        if not (data.get("name") or "").strip():
            raise PaperSizeValidationError("Tên khổ giấy không được trống.")
        w, h = _f(data.get("width_cm")), _f(data.get("height_cm"))
        if w is None or w <= 0:
            raise PaperSizeValidationError("Chiều rộng (cm) phải lớn hơn 0.")
        if h is None or h <= 0:
            raise PaperSizeValidationError("Chiều cao (cm) phải lớn hơn 0.")
        if data.get("size_group") not in SIZE_GROUPS:
            raise PaperSizeValidationError("Nhóm khổ không hợp lệ.")

        cwr = data.get("cut_waste_rate")
        if cwr is not None and (cwr < 0 or cwr > 100):
            raise PaperSizeValidationError("Hao hụt cắt (%) phải trong khoảng 0–100.")

        # Ngày hiệu lực không chồng lấn / hợp lệ
        ef, et = data.get("effective_from"), data.get("effective_to")
        if ef and et and et <= ef:
            raise PaperSizeValidationError("Ngày hết hiệu lực phải sau ngày bắt đầu.")

        # Khổ cắt phải có khổ cha, và không lớn hơn khổ cha
        parent_id = data.get("parent_size_id")
        if data.get("is_cut_size") and not parent_id:
            raise PaperSizeValidationError("Khổ cắt phải chọn khổ cha.")
        if parent_id is not None:
            if self_id is not None and parent_id == self_id:
                raise PaperSizeValidationError("Khổ cha không thể là chính nó.")
            parent = self.repo.get_by_id(parent_id)
            if parent is None:
                raise PaperSizeValidationError("Không tìm thấy khổ cha.")
            pw, ph = _f(parent.width_cm), _f(parent.height_cm)
            if not _fits_within(w, h, pw, ph):
                raise PaperSizeValidationError(
                    f"Khổ cắt ({w:g}×{h:g}) lớn hơn khổ cha {parent.code} ({pw:g}×{ph:g})."
                )

        # Khổ vượt khổ in tối đa của máy được gán
        bad = self.repo.machines_too_small(
            width_cm=w, height_cm=h,
            machine_ids=data.get("compatible_machine_ids"),
            allow_rotation=bool(data.get("allow_rotation", True)),
        )
        if bad:
            raise PaperSizeValidationError(
                "Khổ giấy vượt khổ in tối đa của máy: " + ", ".join(bad) + "."
            )

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
        size_type: str | None = None,
        size_group: str | None = None,
        machine_id: int | None = None,
        is_active: bool | None = None,
        current_only: bool = False,
        sort: str = "code",
        page: int = 1,
        size: int = 50,
    ):
        return self.repo.list(
            q=q, size_type=size_type, size_group=size_group, machine_id=machine_id,
            is_active=is_active, current_only=current_only, sort=sort, page=page, size=size,
        )

    def get_item(self, item_id: int) -> PaperSize:
        item = self.repo.get_by_id(item_id)
        if item is None:
            raise PaperSizeNotFound("Không tìm thấy khổ giấy.")
        return item

    def _is_used(self, item: PaperSize) -> bool:
        """Khổ 'đã dùng' = có snapshot (used_count) HOẶC đang được phiếu tính giá tham chiếu."""
        if int(item.used_count or 0) > 0:
            return True
        return self.repo.count_costing_refs(item.id) > 0

    def history(self, item_id: int) -> list[PaperSize]:
        item = self.get_item(item_id)
        return self.repo.list_versions(item.code)

    # -- writes ------------------------------------------------------------
    def create_item(self, data: dict, *, actor) -> PaperSize:
        self._normalize_type(data)
        self._validate(data)

        raw_code = (data.get("code") or "").strip()
        if raw_code:
            if self.repo.find_by_code_any_version(raw_code) is not None:
                raise PaperSizeDuplicate("Mã khổ giấy đã tồn tại.")
            code = raw_code
        else:
            code = self.repo._next_code()

        if self.repo.find_by_name(data["name"].strip()) is not None:
            raise PaperSizeDuplicate("Tên khổ giấy đã tồn tại.")

        fields = self._assignable(data)
        fields["name"] = data["name"].strip()
        fields["created_by"] = getattr(actor, "id", None)
        fields["updated_by"] = getattr(actor, "id", None)
        try:
            item = self.repo.create(code=code, version=1, **fields)
        except IntegrityError:
            raise PaperSizeDuplicate("Mã hoặc tên khổ giấy đã tồn tại.") from None
        self.audit.create(
            actor_user_id=actor.id,
            action="create_paper_size",
            target=f"paper_size:{item.id}",
            detail=f"{item.code} - {item.name}",
        )
        return item

    def update_item(self, item_id: int, data: dict, *, actor) -> PaperSize:
        item = self.get_item(item_id)
        self._normalize_type(data)
        self._validate(data, self_id=item.id)

        new_name = data["name"].strip()
        dup = self.repo.find_by_name(new_name)
        if dup is not None and dup.code != item.code:
            raise PaperSizeDuplicate("Tên khổ giấy đã tồn tại.")

        dims_changed = (
            _f(item.width_cm) != _f(data.get("width_cm"))
            or _f(item.height_cm) != _f(data.get("height_cm"))
        )

        fields = self._assignable(data)
        fields["name"] = new_name
        fields["updated_by"] = getattr(actor, "id", None)

        if int(item.used_count or 0) > 0 and dims_changed:
            # Version-chain: giữ dòng đã dùng đóng băng, chèn version mới mang kích thước mới.
            new_fields = dict(fields)
            new_fields.pop("effective_from", None)  # repo đặt effective_from = hôm nay
            new_fields.pop("effective_to", None)
            new_fields["created_by"] = getattr(actor, "id", None)
            new_fields.setdefault("is_active", True)
            try:
                new_item = self.repo.supersede_and_create_version(
                    item, effective_from=date.today(), **new_fields
                )
            except IntegrityError:
                raise PaperSizeDuplicate("Trùng phiên bản khổ giấy.") from None
            self.audit.create(
                actor_user_id=actor.id,
                action="version_paper_size",
                target=f"paper_size:{new_item.id}",
                detail=f"{new_item.code} v{new_item.version} (thay v{item.version} đã dùng {item.used_count} phiếu)",
            )
            return new_item

        try:
            item = self.repo.update(item, **fields)
        except IntegrityError:
            raise PaperSizeDuplicate("Tên khổ giấy đã tồn tại.") from None
        self.audit.create(
            actor_user_id=actor.id,
            action="update_paper_size",
            target=f"paper_size:{item.id}",
            detail=f"{item.code} - {item.name}",
        )
        return item

    def create_version_item(self, item_id: int, data: dict, *, actor) -> PaperSize:
        """"Tạo version mới" thủ công — luôn supersede dù chưa dùng."""
        item = self.get_item(item_id)
        self._normalize_type(data)
        self._validate(data, self_id=item.id)
        eff = data.get("effective_from") or date.today()
        fields = self._assignable(data)
        fields["name"] = data["name"].strip()
        fields.pop("effective_from", None)
        fields.pop("effective_to", None)
        fields["created_by"] = getattr(actor, "id", None)
        fields["updated_by"] = getattr(actor, "id", None)
        fields.setdefault("is_active", True)
        try:
            new_item = self.repo.supersede_and_create_version(item, effective_from=eff, **fields)
        except IntegrityError:
            raise PaperSizeDuplicate("Trùng phiên bản khổ giấy.") from None
        self.audit.create(
            actor_user_id=actor.id,
            action="version_paper_size",
            target=f"paper_size:{new_item.id}",
            detail=f"{new_item.code} v{new_item.version} (tạo version mới thủ công)",
        )
        return new_item

    def clone_item(self, item_id: int, *, actor) -> PaperSize:
        """"Sao chép" — tạo khổ logic MỚI (mã mới) copy field của khổ hiện có."""
        src = self.get_item(item_id)
        code = self.repo._next_code()
        base_name = f"{src.name} (bản sao)"
        name = base_name
        i = 2
        while self.repo.find_by_name(name) is not None:
            name = f"{base_name} {i}"
            i += 1
        fields = dict(
            name=name,
            size_group=src.size_group,
            is_purchase_size=src.is_purchase_size,
            is_print_sheet_size=src.is_print_sheet_size,
            is_cut_size=src.is_cut_size,
            size_type=src.size_type,
            note=src.note,
            is_active=src.is_active,
            width_cm=src.width_cm,
            height_cm=src.height_cm,
            allow_rotation=src.allow_rotation,
            compatible_machine_ids=src.compatible_machine_ids,
            default_machine_id=src.default_machine_id,
            parent_size_id=src.parent_size_id,
            cut_count=src.cut_count,
            cut_waste_rate=src.cut_waste_rate,
            created_by=getattr(actor, "id", None),
            updated_by=getattr(actor, "id", None),
        )
        item = self.repo.create(code=code, version=1, **fields)
        self.audit.create(
            actor_user_id=actor.id,
            action="clone_paper_size",
            target=f"paper_size:{item.id}",
            detail=f"{item.code} - {item.name} (sao chép từ {src.code})",
        )
        return item

    def delete_item(self, *, item_id: int, actor) -> None:
        item = self.get_item(item_id)
        if int(item.used_count or 0) > 0:
            raise PaperSizeValidationError(
                "Không thể xóa khổ giấy đã dùng trong phiếu — hãy tạm ngưng (Inactive) thay vì xóa."
            )
        if self.repo.get_children(item.id):
            raise PaperSizeValidationError(
                "Không thể xóa khổ giấy đang là khổ cha của khổ cắt khác."
            )
        code, name = item.code, item.name
        self.repo.delete(item)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_paper_size",
            target=f"paper_size:{item_id}",
            detail=f"{code} - {name}",
        )
