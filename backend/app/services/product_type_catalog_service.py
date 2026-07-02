"""Product Type Catalog Service — spec-20/21.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ..models.product_type_catalog import ProductTypeCatalog, CALCULATION_STRATEGIES
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.product_type_catalog_repo import ProductTypeCatalogRepository

class ProductTypeCatalogError(Exception):
    pass

class ProductTypeCatalogValidationError(ProductTypeCatalogError):
    pass

class ProductTypeCatalogDuplicate(ProductTypeCatalogError):
    pass

class ProductTypeCatalogNotFound(ProductTypeCatalogError):
    pass

class ProductTypeCatalogService:
    def __init__(
        self,
        repo: ProductTypeCatalogRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.repo = repo
        self.audit = audit

    def _validate(
        self,
        *,
        product_type: str | None = None,
        name: str,
        calculation_strategy: str,
        required_fields: list[str] | None,
        default_operations: list[str] | None,
        allowed_materials: list[str] | None,
        compatible_technologies: list[str] | None,
    ) -> None:
        if product_type is not None:
            pt = product_type.strip()
            if not pt:
                raise ProductTypeCatalogValidationError("Mã loại sản phẩm không được trống.")
            # #24 — CHỈ chữ/số ASCII + gạch dưới. str.isalnum() coi ký tự Unicode có dấu (cà_phê)
            # là alphanumeric nên lọt qua dù message hứa "không dấu"; dùng regex ASCII.
            if not re.fullmatch(r"[A-Za-z0-9_]+", pt):
                raise ProductTypeCatalogValidationError("Mã loại sản phẩm phải là chuỗi ký tự không dấu và không chứa ký tự đặc biệt.")
                
        name_str = name.strip()
        if not name_str:
            raise ProductTypeCatalogValidationError("Tên loại sản phẩm không được trống.")
            
        if calculation_strategy not in CALCULATION_STRATEGIES:
            raise ProductTypeCatalogValidationError("Chiến lược tính giá không hợp lệ.")

        # JSONB validation requirements
        if default_operations:
            # Check if operations model is available and has these codes
            try:
                from ..models.operation import Operation
                for op_code in default_operations:
                    op = self.repo.db.execute(
                        select(Operation).where(Operation.code == op_code)
                    ).scalars().first()
                    if not op:
                        raise ProductTypeCatalogValidationError(f"Công đoạn mặc định '{op_code}' không tồn tại trong danh mục.")
            except ImportError:
                pass  # Fallback if operation table is not imported yet

        if allowed_materials:
            # allowed_materials lists types (e.g. paper, decal)
            # We can check if these are valid material_types in materials model
            VALID_MATERIAL_TYPES = {
                "paper", "decal", "pp", "canvas", "carton", "film", "formex",
                "lamination", "glue", "chemical"
            }
            for mat_type in allowed_materials:
                if mat_type not in VALID_MATERIAL_TYPES:
                    raise ProductTypeCatalogValidationError(f"Loại vật tư '{mat_type}' không hợp lệ.")

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

    def create_item(
        self,
        *,
        product_type: str,
        name: str,
        calculation_strategy: str,
        required_fields: list[str] | None = None,
        default_operations: list[str] | None = None,
        allowed_materials: list[str] | None = None,
        compatible_technologies: list[str] | None = None,
        is_active: bool = True,
        actor,
    ) -> ProductTypeCatalog:
        pt = product_type.strip().lower()
        self._validate(
            product_type=pt,
            name=name,
            calculation_strategy=calculation_strategy,
            required_fields=required_fields,
            default_operations=default_operations,
            allowed_materials=allowed_materials,
            compatible_technologies=compatible_technologies,
        )
        if self.repo.get_by_type(pt) is not None:
            raise ProductTypeCatalogDuplicate("Mã loại sản phẩm đã tồn tại.")
        if self.repo.find_by_name(name) is not None:
            raise ProductTypeCatalogDuplicate("Tên loại sản phẩm đã tồn tại.")

        try:
            item = self.repo.create(
                product_type=pt,
                name=name.strip(),
                calculation_strategy=calculation_strategy,
                required_fields=required_fields,
                default_operations=default_operations,
                allowed_materials=allowed_materials,
                compatible_technologies=compatible_technologies,
                is_active=is_active,
            )
        except IntegrityError:
            # #25 — chốt chặn đua: unique DB (product_type/name) va nhau → 409 thay vì 500.
            raise ProductTypeCatalogDuplicate("Mã hoặc tên loại sản phẩm đã tồn tại.") from None
        self.audit.create(
            actor_user_id=actor.id,
            action="create_product_type_catalog",
            target=f"product_type:{item.id}",
            detail=f"{item.product_type} - {item.name}",
        )
        return item

    def update_item(
        self,
        *,
        item_id: int,
        name: str,
        calculation_strategy: str,
        required_fields: list[str] | None = None,
        default_operations: list[str] | None = None,
        allowed_materials: list[str] | None = None,
        compatible_technologies: list[str] | None = None,
        is_active: bool | None = None,
        actor,
    ) -> ProductTypeCatalog:
        item = self.get_item(item_id)
        self._validate(
            name=name,
            calculation_strategy=calculation_strategy,
            required_fields=required_fields,
            default_operations=default_operations,
            allowed_materials=allowed_materials,
            compatible_technologies=compatible_technologies,
        )
        dup = self.repo.find_by_name(name)
        if dup is not None and dup.id != item.id:
            raise ProductTypeCatalogDuplicate("Tên loại sản phẩm đã tồn tại.")

        try:
            item = self.repo.update(
                item,
                name=name.strip(),
                calculation_strategy=calculation_strategy,
                required_fields=required_fields,
                default_operations=default_operations,
                allowed_materials=allowed_materials,
                compatible_technologies=compatible_technologies,
                is_active=is_active,
            )
        except IntegrityError:
            raise ProductTypeCatalogDuplicate("Tên loại sản phẩm đã tồn tại.") from None
        self.audit.create(
            actor_user_id=actor.id,
            action="update_product_type_catalog",
            target=f"product_type:{item.id}",
            detail=f"{item.product_type} - {item.name}",
        )
        return item

    def delete_item(self, *, item_id: int, actor) -> None:
        item = self.get_item(item_id)
        # #9 — guard xóa phải kiểm MỌI tham chiếu, không chỉ Product: estimates.product_type là FK
        # NOT NULL (Postgres → 500 / SQLite → FK mồ côi) và norms.product_type là FK (mất specificity).
        from ..models.product import Product
        from ..models.estimate import Estimate
        from ..models.norm import Norm
        pt = item.product_type
        referenced = any(
            self.repo.db.execute(select(m).where(m.product_type == pt)).first() is not None
            for m in (Product, Estimate, Norm)
        )
        if referenced:
            raise ProductTypeCatalogError(
                "Không thể xóa loại sản phẩm đang được tham chiếu (sản phẩm / tính giá / định mức)."
            )

        pt, name = item.product_type, item.name
        self.repo.delete(item)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_product_type_catalog",
            target=f"product_type:{item_id}",
            detail=f"{pt} - {name}",
        )
