"""Product (Sản phẩm in) business logic — spec-07-san-pham.

Framework-agnostic: raises domain errors the router maps to HTTP. Enforces the spec's
rules (§34 L893–895, §31 tay sách, §5/§7 enums):
  - name required (non-blank) + NOT duplicate (case-insensitive);
  - product_type ∈ §7 enum; binding_type nullable ∈ §5 enum;
  - a product WITH a spine (binding_type not none/null) MUST have ≥1 component;
  - per component: colors_front/back ∈ 0..8, page_count > 0, finished_w/h > 0, bleed ≥ 0,
    grain_direction ∈ {long, short, null};
  - `page_count % 4 == 0` applies ONLY to component_type=body of a BOUND product
    (binding != none) — NOT to cover, NOT to a loose-leaf product (binding none/null);
  - product + components persist in ONE transaction; every create/update/delete audits.

The paper picker is a SEAM-03 seam: `list_papers()` delegates to the raising port stub
(no fabricated paper list) until Danh mục Giấy (`dm_giay_vat_tu`) is built. `paper_master_id`
is FK-nullable meanwhile, so a component may be saved with paper_master_id=None.
"""
from __future__ import annotations

from ..models.product import (
    BINDING_NONE,
    BINDING_TYPES,
    COMPONENT_TYPES,
    GRAIN_DIRECTIONS,
    PRODUCT_TYPES,
    Product,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.product_repo import ComponentInput, ProductRepository
from ..services import product_ports

MAX_COLORS = 8


class ProductError(Exception):
    """Base for product domain errors."""


class ProductValidationError(ProductError):
    """A field failed validation (blank name, bad enum, colors out of range…)."""


class ProductDuplicateName(ProductError):
    """Another product already carries this name (hard block — catalog uniqueness)."""


class ProductNotFound(ProductError):
    """No product with that id."""


class ProductInUse(ProductError):
    """The product is referenced by a consumer (đơn/job) and cannot be deleted.

    No consumer exists at P0 (no reverse FK yet), so this is not raised today — it is the
    named hook the delete guard will use once Kinh doanh/Job is real (spec-07 F4).
    """


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _norm_binding(binding_type: str | None) -> str | None:
    """Normalize the binding: '', 'none', None all mean 'không gáy' → stored as None."""
    b = _clean(binding_type)
    if b is None or b == BINDING_NONE:
        return None
    return b


def _has_spine(binding_type: str | None) -> bool:
    """True when the product has a spine (perfect/saddle/sewn) → needs ≥1 component."""
    return _norm_binding(binding_type) is not None


class ProductService:
    def __init__(
        self,
        products: ProductRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.products = products
        self.audit = audit

    # --- validation helpers -------------------------------------------------

    @staticmethod
    def _validate_name(name: str | None) -> str:
        name = (name or "").strip()
        if not name:
            raise ProductValidationError("Tên sản phẩm là bắt buộc.")
        return name

    @staticmethod
    def _validate_product_type(product_type: str | None) -> str:
        pt = (product_type or "").strip()
        if pt not in PRODUCT_TYPES:
            raise ProductValidationError("Loại sản phẩm không hợp lệ.")
        return pt

    @staticmethod
    def _validate_binding(binding_type: str | None) -> str | None:
        b = _clean(binding_type)
        if b is None:
            return None
        if b not in BINDING_TYPES:
            raise ProductValidationError("Kiểu đóng không hợp lệ.")
        return _norm_binding(b)

    def _validate_components(
        self, raw_components: list[dict], *, binding_type: str | None
    ) -> list[ComponentInput]:
        """Validate + normalize each component row. Raises ProductValidationError on the
        first bad field, naming the row (1-based) so the UI can point at it."""
        bound = _has_spine(binding_type)
        if bound and not raw_components:
            raise ProductValidationError(
                "Sản phẩm có gáy cần ít nhất 1 cấu phần."
            )

        out: list[ComponentInput] = []
        for idx, c in enumerate(raw_components, start=1):
            ctype = (c.get("component_type") or "").strip()
            if ctype not in COMPONENT_TYPES:
                raise ProductValidationError(
                    f"Cấu phần {idx}: loại cấu phần không hợp lệ."
                )

            colors_front = self._validate_colors(c.get("colors_front"), idx, "trước")
            colors_back = self._validate_colors(c.get("colors_back"), idx, "sau")

            page_count = self._validate_int(
                c.get("page_count"), idx, "số trang", positive=True
            )
            # Tay sách: body của SP có gáy phải chia hết cho 4 (4/8/16/32, §31).
            # KHÔNG áp cho cover / insert, KHÔNG áp cho SP tờ rời (binding none).
            if bound and ctype == "body" and page_count % 4 != 0:
                raise ProductValidationError(
                    f"Cấu phần {idx}: số trang ruột phải chia hết cho 4 "
                    "(tay sách 4/8/16/32)."
                )

            finished_w = self._validate_dim(c.get("finished_w"), idx, "khổ rộng")
            finished_h = self._validate_dim(c.get("finished_h"), idx, "khổ cao")
            bleed = self._validate_bleed(c.get("bleed"), idx)

            grain = _clean(c.get("grain_direction"))
            if grain is not None and grain not in GRAIN_DIRECTIONS:
                raise ProductValidationError(
                    f"Cấu phần {idx}: canh thớ không hợp lệ."
                )

            paper_master_id = c.get("paper_master_id")
            if paper_master_id is not None and not isinstance(paper_master_id, int):
                raise ProductValidationError(
                    f"Cấu phần {idx}: giấy không hợp lệ."
                )

            sequence = c.get("sequence")
            sequence = idx - 1 if not isinstance(sequence, int) else sequence

            out.append(
                ComponentInput(
                    component_type=ctype,
                    paper_master_id=paper_master_id,
                    colors_front=colors_front,
                    colors_back=colors_back,
                    page_count=page_count,
                    finished_w=finished_w,
                    finished_h=finished_h,
                    bleed=bleed,
                    grain_direction=grain,
                    sequence=sequence,
                )
            )
        return out

    @staticmethod
    def _validate_colors(value, idx: int, side: str) -> int:
        if value is None:
            value = 0
        if not isinstance(value, int) or isinstance(value, bool):
            raise ProductValidationError(f"Cấu phần {idx}: số màu mặt {side} phải là số nguyên.")
        if value < 0 or value > MAX_COLORS:
            raise ProductValidationError(
                f"Cấu phần {idx}: số màu mặt {side} phải trong khoảng 0..{MAX_COLORS}."
            )
        return value

    @staticmethod
    def _validate_int(value, idx: int, label: str, *, positive: bool) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ProductValidationError(f"Cấu phần {idx}: {label} phải là số nguyên.")
        if positive and value <= 0:
            raise ProductValidationError(f"Cấu phần {idx}: {label} phải lớn hơn 0.")
        return value

    @staticmethod
    def _validate_dim(value, idx: int, label: str) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ProductValidationError(f"Cấu phần {idx}: {label} phải là số.") from None
        if v <= 0:
            raise ProductValidationError(f"Cấu phần {idx}: {label} phải lớn hơn 0.")
        return v

    @staticmethod
    def _validate_bleed(value, idx: int) -> float:
        if value is None:
            return 0.0
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ProductValidationError(f"Cấu phần {idx}: bleed phải là số.") from None
        if v < 0:
            raise ProductValidationError(f"Cấu phần {idx}: bleed không được âm.")
        return v

    # --- paper picker (SEAM-03) --------------------------------------------

    def list_papers(self, q: str | None = None) -> list:
        """List selectable papers for the component editor. Delegates to the SEAM-03
        port, which RAISES NotImplementedError until Danh mục Giấy is built — the router
        turns that into an explicit "Danh mục Giấy chưa sẵn sàng" state (never a fake
        list). NEVER fabricates papers here."""
        # SEAM-03: chờ dm_giay_vat_tu (PaperMaster — Danh mục Giấy, chưa build)
        return product_ports.list_paper_masters(q)

    # --- reads --------------------------------------------------------------

    def list_products(
        self,
        *,
        q: str | None = None,
        product_type: str | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Product], int, dict[int, int]]:
        return self.products.list(
            q=q, product_type=product_type, sort=sort, page=page, size=size
        )

    def get_product(self, product_id: int) -> Product:
        product = self.products.get_by_id(product_id)
        if product is None:
            raise ProductNotFound("Không tìm thấy sản phẩm.")
        return product

    # --- writes -------------------------------------------------------------

    def create_product(
        self,
        *,
        name: str,
        product_type: str,
        binding_type: str | None,
        note: str | None,
        components: list[dict],
        actor,
    ) -> Product:
        name = self._validate_name(name)
        product_type = self._validate_product_type(product_type)
        binding_type = self._validate_binding(binding_type)
        if self.products.find_by_name(name) is not None:
            raise ProductDuplicateName("Tên sản phẩm đã tồn tại.")
        comps = self._validate_components(components, binding_type=binding_type)

        product = self.products.create(
            name=name,
            product_type=product_type,
            binding_type=binding_type,
            note=_clean(note),
            components=comps,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_product",
            target=f"product:{product.id}",
            detail=f"{product.code} {name} ({product_type}, {len(comps)} cấu phần)",
        )
        return product

    def update_product(
        self,
        *,
        product_id: int,
        name: str,
        product_type: str,
        binding_type: str | None,
        note: str | None,
        components: list[dict],
        actor,
    ) -> Product:
        product = self.get_product(product_id)
        name = self._validate_name(name)
        product_type = self._validate_product_type(product_type)
        binding_type = self._validate_binding(binding_type)
        dup = self.products.find_by_name(name)
        if dup is not None and dup.id != product.id:
            raise ProductDuplicateName("Tên sản phẩm đã tồn tại.")
        comps = self._validate_components(components, binding_type=binding_type)

        product = self.products.update(
            product,
            name=name,
            product_type=product_type,
            binding_type=binding_type,
            note=_clean(note),
            components=comps,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="update_product",
            target=f"product:{product.id}",
            detail=f"{product.code} {name} ({product_type}, {len(comps)} cấu phần)",
        )
        return product

    def delete_product(self, *, product_id: int, actor) -> None:
        product = self.get_product(product_id)
        # SEAM (Kinh doanh/Job chưa build): no reverse FK exists yet, so there is nothing
        # to block on. Once đơn/job reference products, check that here → ProductInUse.
        code, name = product.code, product.name
        self.products.delete(product)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_product",
            target=f"product:{product_id}",
            detail=f"{code} {name}",
        )
