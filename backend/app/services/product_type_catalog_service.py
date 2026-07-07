"""Product Type Catalog Service — spec-20/21 + spec page #1 (Loại sản phẩm & Quy tắc tính).
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ..models.product_type_catalog import (
    ProductTypeCatalog,
    CALCULATION_STRATEGIES,
    PRODUCT_GROUPS,
    DIMENSION_RULE_TYPES,
    SHEET_COUNT_MODES,
    INK_COST_MODES,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.product_type_catalog_repo import ProductTypeCatalogRepository

VALID_MATERIAL_TYPES = {
    "paper", "decal", "pp", "canvas", "carton", "film", "formex",
    "lamination", "glue", "chemical",
}
VALID_TECHNOLOGIES = {"offset", "digital", "large_format", "flexo"}
# Vocab field input trên màn Tính giá (spec §B / Tab 2).
VALID_INPUT_FIELDS = {
    "finished_w", "finished_h", "finished_d", "spread_w", "spread_h",
    "quantity", "colors", "sides", "page_count", "signature_count", "spine_width",
    "paper", "cover_paper", "body_paper", "ink", "machine", "sheet_size",
    "operations",
    # giữ back-compat với vocab cũ
    "gsm", "binding_type",
}
VALID_TOOLING_TYPES = {"khuon_be", "khuon_ep_kim", "khuon_dap_noi", "other"}

# Nhãn tiếng Việt để dựng câu "Quy tắc áp dụng" ở preview.
_DIM_LABEL = {"finished": "khổ thành phẩm", "spread": "khổ trải", "multi_page": "khổ trang (nhiều trang)"}
_SHEET_LABEL = {"by_pieces": "theo số con hình học", "by_pages": "theo số trang / tay", "manual": "nhập tay"}


class ProductTypeCatalogError(Exception):
    pass

class ProductTypeCatalogValidationError(ProductTypeCatalogError):
    pass

class ProductTypeCatalogDuplicate(ProductTypeCatalogError):
    pass

class ProductTypeCatalogNotFound(ProductTypeCatalogError):
    pass

class ProductTypeCatalogInUse(ProductTypeCatalogError):
    pass


class ProductTypeCatalogService:
    def __init__(
        self,
        repo: ProductTypeCatalogRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.repo = repo
        self.audit = audit

    # -----------------------------------------------------------------
    def _validate(self, *, product_type: str | None, name: str, cfg: dict) -> None:
        if product_type is not None:
            pt = product_type.strip()
            if not pt:
                raise ProductTypeCatalogValidationError("Mã loại sản phẩm không được trống.")
            # #24 — CHỈ chữ/số ASCII + gạch dưới.
            if not re.fullmatch(r"[A-Za-z0-9_]+", pt):
                raise ProductTypeCatalogValidationError("Mã loại sản phẩm phải là chuỗi ký tự không dấu và không chứa ký tự đặc biệt.")

        if not name.strip():
            raise ProductTypeCatalogValidationError("Tên loại sản phẩm không được trống.")

        if cfg.get("calculation_strategy") not in CALCULATION_STRATEGIES:
            raise ProductTypeCatalogValidationError("Chiến lược tính giá không hợp lệ.")
        if cfg.get("product_group", "an_pham") not in PRODUCT_GROUPS:
            raise ProductTypeCatalogValidationError("Nhóm sản phẩm không hợp lệ.")
        if cfg.get("dimension_rule_type", "finished") not in DIMENSION_RULE_TYPES:
            raise ProductTypeCatalogValidationError("Kiểu kích thước không hợp lệ.")
        if cfg.get("sheet_count_mode", "by_pieces") not in SHEET_COUNT_MODES:
            raise ProductTypeCatalogValidationError("Cách tính số tờ không hợp lệ.")
        if cfg.get("ink_cost_mode", "per_1000") not in INK_COST_MODES:
            raise ProductTypeCatalogValidationError("Cách tính mực không hợp lệ.")

        tech = cfg.get("technology", "offset")
        if tech not in VALID_TECHNOLOGIES:
            raise ProductTypeCatalogValidationError(f"Công nghệ '{tech}' không hợp lệ.")

        shown = list(cfg.get("shown_fields") or [])
        required = list(cfg.get("required_fields") or [])
        for f in shown + required:
            if f not in VALID_INPUT_FIELDS:
                raise ProductTypeCatalogValidationError(f"Field input '{f}' không hợp lệ.")
        # spec §8 — required ⊆ shown (không thể bắt buộc field bị ẩn).
        missing = [f for f in required if f not in shown]
        if missing:
            raise ProductTypeCatalogValidationError(
                f"Trường bắt buộc phải được bật hiển thị: {', '.join(missing)}."
            )

        # spec §8 — dùng khổ trải thì field khổ trải phải bật.
        if cfg.get("dimension_rule_type") == "spread":
            if "spread_w" not in shown or "spread_h" not in shown:
                raise ProductTypeCatalogValidationError(
                    "Kiểu kích thước 'khổ trải' yêu cầu bật hiển thị field khổ trải (spread_w, spread_h)."
                )
        # spec §8 — có bìa/ruột riêng thì phải bật input giấy bìa & giấy ruột.
        if cfg.get("has_cover_body_split"):
            if "cover_paper" not in shown or "body_paper" not in shown:
                raise ProductTypeCatalogValidationError(
                    "Có bìa/ruột riêng thì phải bật hiển thị giấy bìa (cover_paper) và giấy ruột (body_paper)."
                )
        # spec §8 — có số trang thì nên bật page_count.
        if cfg.get("has_page_count") and "page_count" not in shown:
            raise ProductTypeCatalogValidationError("Có dùng số trang thì phải bật hiển thị field số trang (page_count).")

        # spec §8 — routing không được trùng công đoạn; required ⊆ default.
        default_ops = list(cfg.get("default_operations") or [])
        if len(default_ops) != len(set(default_ops)):
            raise ProductTypeCatalogValidationError("Routing mặc định có công đoạn bị trùng.")
        req_ops = list(cfg.get("required_operations") or [])
        extra_req = [o for o in req_ops if o not in default_ops]
        if extra_req:
            raise ProductTypeCatalogValidationError(
                f"Công đoạn bắt buộc phải nằm trong routing mặc định: {', '.join(extra_req)}."
            )

        # Công đoạn phải tồn tại trong danh mục (so theo operation_type).
        if default_ops:
            from ..models.operation import Operation
            for op_code in default_ops:
                op = self.repo.db.execute(
                    select(Operation).where(Operation.operation_type == op_code)
                ).scalars().first()
                if not op:
                    raise ProductTypeCatalogValidationError(f"Công đoạn mặc định '{op_code}' không tồn tại trong danh mục.")

        for mat_type in (cfg.get("allowed_materials") or []):
            if mat_type not in VALID_MATERIAL_TYPES:
                raise ProductTypeCatalogValidationError(f"Loại vật tư '{mat_type}' không hợp lệ.")

        # spec §8 — có phát sinh khuôn thì phải chọn loại khuôn mặc định.
        if cfg.get("has_tooling"):
            tt = cfg.get("default_tooling_type")
            if not tt:
                raise ProductTypeCatalogValidationError("Có phát sinh khuôn thì phải chọn loại khuôn mặc định.")
            if tt not in VALID_TOOLING_TYPES:
                raise ProductTypeCatalogValidationError("Loại khuôn mặc định không hợp lệ.")

    # -----------------------------------------------------------------
    def list_items(
        self,
        *,
        q: str | None = None,
        is_active: bool | None = None,
        sort: str = "product_type",
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[ProductTypeCatalog], int]:
        return self.repo.list(q=q, is_active=is_active, sort=sort, page=page, size=size)

    def get_item(self, item_id: int) -> ProductTypeCatalog:
        item = self.repo.get_by_id(item_id)
        if item is None:
            raise ProductTypeCatalogNotFound("Không tìm thấy cấu hình loại sản phẩm.")
        return item

    def get_item_by_type(self, product_type: str) -> ProductTypeCatalog:
        item = self.repo.get_by_type(product_type)
        if item is None:
            raise ProductTypeCatalogNotFound("Không tìm thấy cấu hình loại sản phẩm.")
        return item

    @staticmethod
    def _normalize_shown(cfg: dict) -> None:
        # Back-compat: caller cũ chỉ gửi required_fields → coi như đó cũng là tập hiển thị.
        if cfg.get("shown_fields") is None:
            cfg["shown_fields"] = list(cfg.get("required_fields") or [])

    def create_item(self, *, product_type: str, name: str, is_active: bool = True, actor, **cfg) -> ProductTypeCatalog:
        pt = product_type.strip().lower()
        self._normalize_shown(cfg)
        self._validate(product_type=pt, name=name, cfg=cfg)
        if self.repo.get_by_type(pt) is not None:
            raise ProductTypeCatalogDuplicate("Mã loại sản phẩm đã tồn tại.")
        if self.repo.find_by_name(name) is not None:
            raise ProductTypeCatalogDuplicate("Tên loại sản phẩm đã tồn tại.")

        try:
            item = self.repo.create(product_type=pt, name=name.strip(), is_active=is_active, **cfg)
        except IntegrityError:
            raise ProductTypeCatalogDuplicate("Mã hoặc tên loại sản phẩm đã tồn tại.") from None
        self.audit.create(
            actor_user_id=actor.id,
            action="create_product_type_catalog",
            target=f"product_type:{item.id}",
            detail=f"{item.product_type} - {item.name}",
        )
        return item

    def update_item(self, *, item_id: int, name: str, is_active: bool | None = None, actor, **cfg) -> ProductTypeCatalog:
        item = self.get_item(item_id)
        self._normalize_shown(cfg)
        self._validate(product_type=None, name=name, cfg=cfg)
        dup = self.repo.find_by_name(name)
        if dup is not None and dup.id != item.id:
            raise ProductTypeCatalogDuplicate("Tên loại sản phẩm đã tồn tại.")

        try:
            item = self.repo.update(item, name=name.strip(), is_active=is_active, **cfg)
        except IntegrityError:
            raise ProductTypeCatalogDuplicate("Tên loại sản phẩm đã tồn tại.") from None
        self.audit.create(
            actor_user_id=actor.id,
            action="update_product_type_catalog",
            target=f"product_type:{item.id}",
            detail=f"{item.product_type} - {item.name}",
        )
        return item

    def clone_item(self, *, item_id: int, new_product_type: str, new_name: str, actor) -> ProductTypeCatalog:
        """spec §5.1 'Sao chép / Tạo version mới' — nhân bản toàn bộ cấu hình sang mã mới.

        Vì product_type là FK key (estimates/norms/products) nên 'version mới' hiện thực bằng
        clone sang mã mới thay vì đa-version cùng mã (tránh phá FK). Version bump +1 trên bản mới.
        """
        src = self.get_item(item_id)
        cfg = {f: getattr(src, f) for f in (
            "calculation_strategy", "product_group", "technology", "description", "display_order",
            "required_fields", "shown_fields", "dimension_rule_type", "default_bleed_mm",
            "default_gutter_mm", "default_trim_mm", "allow_rotation", "allow_custom_size",
            "has_page_count", "page_multiple", "pages_per_signature", "has_cover_body_split",
            "allowed_materials", "default_paper_material_id", "default_cover_material_id",
            "default_body_material_id", "default_ink_material_id", "has_packaging", "default_pack_qty",
            "default_operations", "required_operations", "allow_extra_operations",
            "compatible_technologies", "sheet_count_mode", "ink_cost_mode", "has_tooling",
            "default_tooling_type", "allow_manual_override", "waste_pct",
        )}
        item = self.create_item(product_type=new_product_type, name=new_name, actor=actor, **cfg)
        # bump version metadata trên bản clone.
        item.version = (src.version or 1) + 1
        self.repo.db.commit()
        return item

    def delete_item(self, *, item_id: int, actor) -> None:
        item = self.get_item(item_id)
        # #9 — guard xóa: estimates.product_type là FK NOT NULL, norms.product_type là FK.
        from ..models.product import Product
        from ..models.estimate import Estimate
        from ..models.norm import Norm
        pt = item.product_type
        referenced = any(
            self.repo.db.execute(select(m).where(m.product_type == pt)).first() is not None
            for m in (Product, Estimate, Norm)
        )
        # spec §8 — record đã dùng (used_count > 0, kể cả phiếu đã xóa) hoặc đang được tham chiếu
        # thì không xóa cứng; chỉ được Ngưng áp dụng.
        if referenced or (item.used_count or 0) > 0:
            raise ProductTypeCatalogInUse(
                "Không thể xóa loại sản phẩm đã dùng / đang được tham chiếu (sản phẩm / tính giá / định mức). "
                "Hãy đặt Ngưng áp dụng thay vì xóa."
            )

        pt, name = item.product_type, item.name
        self.repo.delete(item)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_product_type_catalog",
            target=f"product_type:{item_id}",
            detail=f"{pt} - {name}",
        )

    # --- Test nhanh form tính giá (spec §5.7 / §9) -----------------------
    def preview_config(self, *, item_id: int) -> dict:
        item = self.get_item(item_id)
        shown = list(item.shown_fields or item.required_fields or [])
        required = list(item.required_fields or [])
        routing = list(item.default_operations or [])
        req_ops = list(item.required_operations or [])
        warnings: list[str] = []
        if not shown:
            warnings.append("Chưa khai field hiển thị — màn Tính giá sẽ dùng bộ field mặc định.")
        if not routing:
            warnings.append("Chưa khai routing mặc định cho loại sản phẩm này.")

        rules: list[str] = []
        rules.append(f"Kích thước tính số con: {_DIM_LABEL.get(item.dimension_rule_type, item.dimension_rule_type)}.")
        if item.default_bleed_mm or item.default_gutter_mm or item.default_trim_mm:
            rules.append(
                f"Bleed {float(item.default_bleed_mm):g}mm · gutter {float(item.default_gutter_mm):g}mm · "
                f"lề xén {float(item.default_trim_mm):g}mm (mặc định)."
            )
        rules.append(f"Số tờ: {_SHEET_LABEL.get(item.sheet_count_mode, item.sheet_count_mode)}.")
        if routing:
            rules.append("Routing: " + " → ".join(routing) + ".")
        if item.has_tooling:
            rules.append(f"Có phát sinh khuôn ({item.default_tooling_type or 'chưa chọn loại'}).")
        if item.has_cover_body_split:
            rules.append("Tính bìa / ruột riêng.")
        if item.has_packaging:
            rules.append(f"Có bao bì (quy cách {item.default_pack_qty or 0} / thùng).")

        return {
            "product_type": item.product_type,
            "name": item.name,
            "shown_fields": shown,
            "required_fields": required,
            "routing": routing,
            "required_operations": req_ops,
            "dimension_rule_type": item.dimension_rule_type,
            "default_bleed_mm": float(item.default_bleed_mm),
            "default_gutter_mm": float(item.default_gutter_mm),
            "default_trim_mm": float(item.default_trim_mm),
            "sheet_count_mode": item.sheet_count_mode,
            "ink_cost_mode": item.ink_cost_mode,
            "has_tooling": item.has_tooling,
            "has_packaging": item.has_packaging,
            "has_cover_body_split": item.has_cover_body_split,
            "rules": rules,
            "warnings": warnings,
        }
