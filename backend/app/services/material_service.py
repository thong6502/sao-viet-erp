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
from ..models.material import GROUP_FROM_TYPE, MATERIAL_GROUPS

# Field vật tư mới (tái thiết kế #2) — service chuyển thẳng xuống repo.
_EXTRA_MATERIAL_FIELDS = (
    "material_group", "default_supplier", "base_uom", "purchase_uom", "consumption_uom",
    "conversion_method", "conversion_factor", "ink_type", "ink_color_system",
    "ink_color_code", "film_type",
)

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

class ToggleActiveForbidden(MaterialError):
    """Đổi is_active qua nút Sửa khi không có quyền chi tiết `toggle_active` (Cách B).

    Chốt ở service để endpoint Sửa chung không thành đường vòng né quyền Bật/tắt."""


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

    def _clean_extra(self, extra: dict, material_type: str) -> dict:
        """Lọc field vật tư mới (#2) + suy material_group mặc định + validate nhóm."""
        clean = {k: v for k, v in extra.items() if k in _EXTRA_MATERIAL_FIELDS}
        group = clean.get("material_group") or GROUP_FROM_TYPE.get(material_type)
        if group is not None and group not in MATERIAL_GROUPS:
            raise MaterialValidationError(f"Nhóm vật tư '{group}' không hợp lệ.")
        clean["material_group"] = group
        for s in ("default_supplier", "base_uom", "purchase_uom", "consumption_uom",
                  "conversion_method", "ink_type", "ink_color_system", "ink_color_code", "film_type"):
            if isinstance(clean.get(s), str):
                clean[s] = clean[s].strip() or None
        return clean

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
        **extra,
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

        clean_extra = self._clean_extra(extra, material_type)
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
            **clean_extra,
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
        allow_toggle_active: bool = True,
        **extra,
    ) -> Material:
        material = self.get_material(material_id)
        # Bật/tắt hoạt động là quyền chi tiết `toggle_active` — thiếu nó thì is_active
        # phải giữ nguyên (các field khác vẫn sửa bình thường).
        if (
            is_active is not None
            and bool(is_active) != bool(material.is_active)
            and not allow_toggle_active
        ):
            raise ToggleActiveForbidden("Bạn không có quyền bật/tắt hoạt động vật tư.")
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

        clean_extra = self._clean_extra(extra, material_type)
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
            **clean_extra,
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
        supplier: str | None = None,
        price_type: str = "standard",
        vat_included: bool = False,
        transport_fee: int = 0,
        moq: float = 0.0,
        lead_time_days: int = 0,
        quantity_from: float | None = None,
        quantity_to: float | None = None,
    ) -> MaterialCost:
        material = self.get_material(material_id)
        if unit_price < 0:
            raise MaterialValidationError("Đơn giá không được âm.")
        if not price_unit.strip():
            raise MaterialValidationError("Đơn vị tính giá không được trống.")
        price_unit = price_unit.strip()

        # §12 — giấy tính giá theo kg phải có GSM (+ khổ) để engine quy đổi ra tờ.
        is_paperish = material.material_group == "paper" or material.material_type in ("paper", "carton")
        if price_unit == "kg" and is_paperish and not material.gsm:
            raise MaterialValidationError("Giấy tính giá theo kg phải khai định lượng (gsm) để quy đổi ra tờ.")
        if quantity_from is not None and quantity_to is not None and quantity_to < quantity_from:
            raise MaterialValidationError("Số lượng bậc: 'đến' không được nhỏ hơn 'từ'.")

        supplier = supplier.strip() if isinstance(supplier, str) and supplier.strip() else None

        # Overlap CHỈ trong cùng biến thể (price_unit + bậc + NCC + khổ). Nửa-mở [from, to).
        def same_variant(c) -> bool:
            return (
                c.price_unit == price_unit
                and c.quantity_from == quantity_from
                and c.quantity_to == quantity_to
                and (c.supplier or None) == supplier
            )

        current = self.repo.get_current_cost_variant(
            material_id, price_unit, quantity_from=quantity_from, quantity_to=quantity_to,
            supplier=supplier,
        )
        if current and effective_from <= current.effective_from:
            raise MaterialValidationError(
                f"Ngày hiệu lực mới phải sau ngày hiệu lực của bảng giá hiện hành ({current.effective_from})."
            )
        for cost in material.costs:
            if same_variant(cost) and cost.effective_to is not None:
                if cost.effective_from <= effective_from < cost.effective_to:
                    raise MaterialValidationError(
                        f"Ngày hiệu lực bị chồng lấn với bảng giá cũ từ {cost.effective_from} đến {cost.effective_to}."
                    )

        cost = self.repo.add_cost_price(
            material_id=material_id,
            price_unit=price_unit,
            unit_price=unit_price,
            effective_from=effective_from,
            supplier=supplier,
            price_type=price_type,
            vat_included=vat_included,
            transport_fee=transport_fee,
            moq=moq,
            lead_time_days=lead_time_days,
            quantity_from=quantity_from,
            quantity_to=quantity_to,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="add_material_price",
            target=f"material:{material.id}",
            detail=f"Đơn giá mới: {unit_price} VND/{price_unit} từ {effective_from}",
        )
        return cost

    def get_cost_history(self, material_id: int) -> list[MaterialCost]:
        material = self.get_material(material_id)
        return sorted(material.costs, key=lambda c: (c.price_unit, c.effective_from), reverse=True)

    @staticmethod
    def convert(*, gsm: int, width_cm: float, height_cm: float) -> dict:
        """Quy đổi khổ giấy → kg/tờ (kg/tờ = diện tích m² × gsm/1000)."""
        area = (float(width_cm) * float(height_cm)) / 10000.0
        kg_per_sheet = area * (float(gsm) / 1000.0)
        return {
            "area_m2": round(area, 4),
            "kg_per_sheet": round(kg_per_sheet, 4),
            "detail": (
                f"Diện tích = {width_cm}×{height_cm}/10000 = {area:.4f} m² · "
                f"Kg/tờ = {area:.4f} × {gsm}/1000 = {kg_per_sheet:.4f} kg"
            ),
        }

    @staticmethod
    def price_test(params) -> dict:
        """Test tính tiền vật tư theo đơn vị giá (§9) — không cần material trong DB."""
        import math as _m
        pu = params.price_unit
        up = float(params.unit_price)
        steps: list[str] = []
        total = 0.0
        if pu == "nghin_luot":
            blocks = _m.ceil(float(params.impressions) / 1000.0) if params.impressions else 0
            total = blocks * up
            steps.append(f"Số block 1.000 lượt = ceil({params.impressions:g}/1000) = {blocks}")
            steps.append(f"Tiền = {blocks} × {up:,.0f} = {total:,.0f}")
        elif pu == "kg":
            area = (float(params.width_cm or 0) * float(params.height_cm or 0)) / 10000.0
            kg_per_sheet = area * (float(params.gsm or 0) / 1000.0)
            total_kg = float(params.sheets) * kg_per_sheet
            total = total_kg * up
            steps.append(f"Kg/tờ = {area:.4f} × {params.gsm or 0}/1000 = {kg_per_sheet:.4f}")
            steps.append(f"Tổng kg = {params.sheets:g} × {kg_per_sheet:.4f} = {total_kg:.2f}")
            steps.append(f"Tiền = {total_kg:.2f} × {up:,.0f} = {total:,.0f}")
        elif pu == "ram":
            total = float(params.sheets) * up / 500.0
            steps.append(f"Tiền = {params.sheets:g} tờ × {up:,.0f}/500 = {total:,.0f}")
        elif pu == "m2":
            area = (float(params.width_cm or 0) * float(params.height_cm or 0)) / 10000.0
            total_m2 = float(params.sheets) * area if params.sheets else 0.0
            total = total_m2 * up
            steps.append(f"Tổng m² = {params.sheets:g} × {area:.4f} = {total_m2:.2f}")
            steps.append(f"Tiền = {total_m2:.2f} × {up:,.0f} = {total:,.0f}")
        elif pu == "to":
            total = float(params.sheets) * up
            steps.append(f"Tiền = {params.sheets:g} tờ × {up:,.0f} = {total:,.0f}")
        else:  # cai/cuon/thung...
            qty = float(params.quantity or params.sheets or 0)
            total = qty * up
            steps.append(f"Tiền = {qty:g} × {up:,.0f} = {total:,.0f}")
        if params.transport_fee:
            total += float(params.transport_fee)
            steps.append(f"+ Phí vận chuyển {float(params.transport_fee):,.0f} = {total:,.0f}")
        return {"total": round(total, 2), "steps": steps}

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
