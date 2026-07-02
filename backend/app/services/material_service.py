"""Material Service — spec-20 business logic.

Unified service to validate and manage raw materials (consumables, paper, etc.)
and their time-versioned prices.
"""
from __future__ import annotations

from datetime import date, datetime
from sqlalchemy import select, func
from ..models.material import Material, MaterialCost
from ..models.product import ProductComponent, Product
from ..models.costing import CostingPaperOption, Costing
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.material_repo import MaterialRepository

VALID_MATERIAL_TYPES = {
    "paper",
    "decal",
    "pp",
    "canvas",
    "carton",
    "film",
    "formex",
    "lamination",
    "glue",
    "chemical",
}

class MaterialError(Exception):
    pass

class MaterialValidationError(MaterialError):
    pass

class MaterialDuplicate(MaterialError):
    pass

class MaterialNotFound(MaterialError):
    pass

class MaterialService:
    def __init__(
        self,
        repo: MaterialRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.repo = repo
        self.audit = audit

    def _validate(
        self,
        *,
        name: str,
        material_type: str,
        unit: str,
        min_fee: int,
        width_cm: float | None,
        height_cm: float | None,
        gsm: int | None,
        thickness_mm: float | None,
        default_waste_pct: float,
        min_purchase_qty: float,
        paper_family: str | None,
        surface: str | None,
    ) -> None:
        name_str = name.strip()
        if not name_str:
            raise MaterialValidationError("Tên vật tư không được trống.")

        if material_type not in VALID_MATERIAL_TYPES:
            raise MaterialValidationError("Loại vật tư không hợp lệ.")

        if not unit.strip():
            raise MaterialValidationError("Đơn vị tính không được trống.")

        if min_fee < 0:
            raise MaterialValidationError("Phí tối thiểu không được âm.")

        # Numeric dimensions checks
        if width_cm is not None and width_cm < 0:
            raise MaterialValidationError("Khổ rộng không được âm.")
        if height_cm is not None and height_cm < 0:
            raise MaterialValidationError("Khổ cao/dài không được âm.")
        if gsm is not None and gsm < 0:
            raise MaterialValidationError("Định lượng gsm không được âm.")
        if thickness_mm is not None and thickness_mm < 0:
            raise MaterialValidationError("Độ dày không được âm.")
        if default_waste_pct < 0:
            raise MaterialValidationError("Tỷ lệ hao hụt không được âm.")
        if min_purchase_qty < 0:
            raise MaterialValidationError("Số lượng mua tối thiểu không được âm.")

        # Paper-specific checks: "khổ cạnh ngắn trước" (width_cm <= height_cm)
        if material_type == "paper":
            if width_cm is not None and height_cm is not None:
                if width_cm > height_cm:
                    raise MaterialValidationError("Quy ước khổ giấy: Cạnh ngắn viết trước (Rộng <= Cao).")
            if not paper_family or not paper_family.strip():
                raise MaterialValidationError("Vật tư là Giấy yêu cầu điền Họ giấy.")
        else:
            # Non-papers shouldn't enforce paper_family or surface, we can clean them
            pass

    def list_materials(
        self,
        *,
        q: str | None = None,
        material_type: str | None = None,
        is_active: bool | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Material], int]:
        return self.repo.list(
            q=q, material_type=material_type, is_active=is_active, sort=sort, page=page, size=size
        )

    def get_material(self, material_id: int) -> Material:
        material = self.repo.get_by_id(material_id)
        if material is None:
            raise MaterialNotFound("Không tìm thấy vật tư.")
        return material

    def create_material(
        self,
        *,
        name: str,
        material_type: str,
        unit: str,
        min_fee: int = 0,
        width_cm: float | None = None,
        height_cm: float | None = None,
        gsm: int | None = None,
        thickness_mm: float | None = None,
        default_waste_pct: float = 0.0,
        min_purchase_qty: float = 0.0,
        paper_family: str | None = None,
        surface: str | None = None,
        is_active: bool = True,
        actor,
    ) -> Material:
        self._validate(
            name=name,
            material_type=material_type,
            unit=unit,
            min_fee=min_fee,
            width_cm=width_cm,
            height_cm=height_cm,
            gsm=gsm,
            thickness_mm=thickness_mm,
            default_waste_pct=default_waste_pct,
            min_purchase_qty=min_purchase_qty,
            paper_family=paper_family,
            surface=surface,
        )
        if self.repo.find_by_name(name) is not None:
            raise MaterialDuplicate("Tên vật tư đã tồn tại.")

        material = self.repo.create(
            name=name.strip(),
            material_type=material_type,
            unit=unit.strip(),
            min_fee=min_fee,
            width_cm=width_cm,
            height_cm=height_cm,
            gsm=gsm,
            thickness_mm=thickness_mm,
            default_waste_pct=default_waste_pct,
            min_purchase_qty=min_purchase_qty,
            paper_family=paper_family.strip() if paper_family else None,
            surface=surface.strip() if surface else None,
            is_active=is_active,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_material",
            target=f"material:{material.id}",
            detail=f"{material.code} - {material.name} ({material_type})",
        )
        return material

    def update_material(
        self,
        *,
        material_id: int,
        name: str,
        material_type: str,
        unit: str,
        min_fee: int,
        width_cm: float | None = None,
        height_cm: float | None = None,
        gsm: int | None = None,
        thickness_mm: float | None = None,
        default_waste_pct: float = 0.0,
        min_purchase_qty: float = 0.0,
        paper_family: str | None = None,
        surface: str | None = None,
        is_active: bool | None = None,
        actor,
    ) -> Material:
        material = self.get_material(material_id)
        self._validate(
            name=name,
            material_type=material_type,
            unit=unit,
            min_fee=min_fee,
            width_cm=width_cm,
            height_cm=height_cm,
            gsm=gsm,
            thickness_mm=thickness_mm,
            default_waste_pct=default_waste_pct,
            min_purchase_qty=min_purchase_qty,
            paper_family=paper_family,
            surface=surface,
        )
        dup = self.repo.find_by_name(name)
        if dup is not None and dup.id != material.id:
            raise MaterialDuplicate("Tên vật tư đã tồn tại.")

        material = self.repo.update(
            material,
            name=name.strip(),
            material_type=material_type,
            unit=unit.strip(),
            min_fee=min_fee,
            width_cm=width_cm,
            height_cm=height_cm,
            gsm=gsm,
            thickness_mm=thickness_mm,
            default_waste_pct=default_waste_pct,
            min_purchase_qty=min_purchase_qty,
            paper_family=paper_family.strip() if paper_family else None,
            surface=surface.strip() if surface else None,
            is_active=is_active,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="update_material",
            target=f"material:{material.id}",
            detail=f"{material.code} - {material.name}",
        )
        return material

    def toggle_active(self, *, material_id: int, actor) -> Material:
        material = self.get_material(material_id)
        material.is_active = not material.is_active
        self.repo.db.commit()
        action = "activate_material" if material.is_active else "deactivate_material"
        self.audit.create(
            actor_user_id=actor.id,
            action=action,
            target=f"material:{material.id}",
            detail=f"{material.code} {material.name}",
        )
        return material

    def clone_paper(self, *, material_id: int, gsm: int, width_cm: float, height_cm: float, actor) -> Material:
        """Helper to duplicate a paper with a new gsm/size."""
        source = self.get_material(material_id)
        if source.material_type != "paper":
            raise MaterialValidationError("Chỉ có thể nhân bản vật liệu dạng Giấy.")

        new_name = f"{source.paper_family} {gsm}gsm {width_cm}x{height_cm}"
        return self.create_material(
            name=new_name,
            material_type="paper",
            unit=source.unit,
            min_fee=source.min_fee,
            width_cm=width_cm,
            height_cm=height_cm,
            gsm=gsm,
            thickness_mm=source.thickness_mm,
            default_waste_pct=source.default_waste_pct,
            min_purchase_qty=source.min_purchase_qty,
            paper_family=source.paper_family,
            surface=source.surface,
            is_active=True,
            actor=actor,
        )

    def delete_material(self, *, material_id: int, actor) -> None:
        material = self.get_material(material_id)

        # 1. Check ProductComponent references in DB
        has_component = self.repo.db.execute(
            select(ProductComponent).where(ProductComponent.paper_master_id == material.id)
        ).first() is not None
        if has_component:
            raise MaterialValidationError("Không thể xóa vật tư đang được sử dụng trong cấu phần Sản phẩm.")

        # 2. Check CostingPaperOption references in DB
        has_costing = self.repo.db.execute(
            select(CostingPaperOption).where(CostingPaperOption.sheet_paper_master_id == material.id)
        ).first() is not None
        if has_costing:
            raise MaterialValidationError("Không thể xóa vật tư đang được sử dụng trong Phương án Tính giá.")

        # 3. Check StockLot reference via SEAM-22
        try:
            from ..ports.paper_stock_usage_port import is_paper_referenced_in_stock
            if is_paper_referenced_in_stock(material.id):
                raise MaterialValidationError("Không thể xóa vật tư đang được sử dụng trong Kho.")
        except NotImplementedError:
            # Let the user know they cannot hard delete without verifying Kho
            raise MaterialValidationError(
                "Chưa kiểm tra được tham chiếu Kho (SEAM-22). Vui lòng dùng chức năng Ẩn thay vì Xóa."
            )

        code, name = material.code, material.name
        self.repo.delete(material)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_material",
            target=f"material:{material_id}",
            detail=f"{code} {name}",
        )

    # --- pricing writes & overlap validations ------------------------------

    def add_material_price(
        self,
        *,
        material_id: int,
        price_unit: str,
        unit_price: int,
        effective_from: date,
        actor,
    ) -> MaterialCost:
        material = self.get_material(material_id)
        if unit_price < 0:
            raise MaterialValidationError("Đơn giá không được âm.")
        if not price_unit.strip():
            raise MaterialValidationError("Đơn vị tính giá không được trống.")

        # Validate date interval overlaps
        # 1. If there's an active price, the new starting date must be strictly greater than active starting date.
        current = self.repo.get_current_cost(material_id, price_unit)
        if current and effective_from <= current.effective_from:
            raise MaterialValidationError(
                f"Ngày hiệu lực mới phải sau ngày hiệu lực của bảng giá hiện hành ({current.effective_from})."
            )

        # 2. Check if new effective_from falls inside any historical price interval
        #    #6 — CHỈ xét cùng price_unit (mỗi đơn vị giá là một chuỗi thời gian độc lập);
        #    trước đây lặp mọi cost nên giá đơn vị khác (vd kg) chặn nhầm giá đơn vị 'to'.
        #    Dùng nửa-mở [from, to): cận trên LOẠI TRỪ, khớp cách đóng giá (#5).
        for cost in material.costs:
            if cost.price_unit == price_unit and cost.effective_to is not None:
                if cost.effective_from <= effective_from < cost.effective_to:
                    raise MaterialValidationError(
                        f"Ngày hiệu lực bị chồng lấn với bảng giá cũ từ {cost.effective_from} đến {cost.effective_to}."
                    )

        cost = self.repo.add_cost_price(
            material_id=material_id,
            price_unit=price_unit,
            unit_price=unit_price,
            effective_from=effective_from,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="add_material_price",
            target=f"material:{material.id}",
            detail=f"Đơn giá mới: {unit_price} VND/{price_unit} từ {effective_from}",
        )
        return cost

    # --- stats calculation --------------------------------------------------

    def get_list_stats(self) -> dict:
        """Returns statistics for materials dashboard list."""
        db = self.repo.db
        
        # 1. Total counts
        total_mats = db.execute(select(func.count()).select_from(Material)).scalar_one()
        total_papers = db.execute(
            select(func.count()).select_from(Material).where(Material.material_type == "paper")
        ).scalar_one()
        total_consumables = total_mats - total_papers
        
        # 2. Items without any current price row
        # We check materials that do not have a corresponding cost row in material_costs where effective_to is null
        has_price_sub = select(MaterialCost.material_id).where(MaterialCost.effective_to.is_(None)).scalar_subquery()
        no_price = db.execute(
            select(func.count()).select_from(Material).where(Material.id.not_in(has_price_sub))
        ).scalar_one()

        # 3. Price updates this month
        today = date.today()
        first_day_of_month = date(today.year, today.month, 1)
        this_month_updates = db.execute(
            select(func.count(MaterialCost.id)).where(MaterialCost.effective_from >= first_day_of_month)
        ).scalar_one()

        return {
            "total_materials": total_mats,
            "total_papers": total_papers,
            "total_consumables": total_consumables,
            "no_price_count": no_price,
            "price_updates_this_month": this_month_updates,
        }
