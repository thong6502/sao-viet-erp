"""Pricing Engine — mathematical costing calculations for Estimates.
"""
from __future__ import annotations

import math
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.material import Material, MaterialCost
from ..models.machine import Machine, MachineRate
from ..models.operation import Operation, OperationRate
from ..models.click_ink_rate import ClickInkRate
from ..models.plate_die_rate import PlateDieRate
from ..models.estimate import EstimateCostLine
from ..services.norm_service import NormService, NormLookupContext

# Nhãn tiếng Việt cho mã đơn vị khi nhúng vào mô tả dòng chi phí (hiển thị cho người dùng)
UNIT_LABELS_VI = {
    "to": "tờ", "ban": "bản", "luot": "lượt", "gio": "giờ", "trang": "trang",
    "m2": "m²", "cuon": "cuốn", "cai": "cái", "san_pham": "sản phẩm", "lo": "lô",
    "nghin_to": "1.000 tờ", "nghin_cai": "1.000 cái", "thung": "thùng",
}

class PricingEngine:
    def __init__(self, db: Session) -> None:
        self.db = db
        from ..repositories.norm_repo import NormRepository
        from ..repositories.audit_repo import AuditLogRepository
        repo = NormRepository(db)
        audit = AuditLogRepository(db)
        self.norm_service = NormService(repo, audit)

    def calculate_option(self, input_spec: dict, qty: int, at_date: date | None = None) -> tuple[list[EstimateCostLine], float, list[dict]]:
        """Calculate detail cost breakdown (cost lines) and total cost for a specific quantity point.
        
        Returns:
            tuple of (cost_lines, total_cost, warnings)
        """
        if at_date is None:
            at_date = date.today()

        warnings: list[dict] = []

        def add_warning(severity: str, code: str, message: str, source_type: str | None = None, source_id: int | None = None) -> None:
            warnings.append({
                "severity": severity,
                "code": code,
                "message": message,
                "source_type": source_type,
                "source_id": source_id
            })

        # 1. Retrieve basic spec parameters
        product_type = input_spec.get("product_type")
        product_name = input_spec.get("product_name", "")
        finished_w = input_spec.get("finished_width") or input_spec.get("finished_w")
        finished_h = input_spec.get("finished_height") or input_spec.get("finished_h")
        colors = int(input_spec.get("colors", 4))
        sides = int(input_spec.get("sides", 2))
        # #26 — ép kiểu page_count (như colors/sides); chuỗi "8" từ JSON gây TypeError ở phép "8" > 0.
        page_count_raw = input_spec.get("page_count") or input_spec.get("pages")
        page_count = None
        if page_count_raw is not None:
            try:
                page_count = int(page_count_raw)
            except (ValueError, TypeError):
                add_warning("blocking_error", "INVALID_PAGE_COUNT", "Số trang (page_count) không hợp lệ.")
                page_count = None
        forms = int(input_spec.get("forms", 1))
        material_id = input_spec.get("material_id")
        machine_id = input_spec.get("machine_id")
        raw_ops = input_spec.get("operations", [])
        sheet_w = input_spec.get("sheet_w")
        sheet_h = input_spec.get("sheet_h")
        pieces_per_sheet_input = input_spec.get("pieces_per_sheet")
        grain_locked = bool(input_spec.get("grain_locked", False))
        # #4 — tham số bình bản (đơn vị cm), mặc định 0 ⇒ công thức trùng floor(khổ/thành phẩm) cũ.
        # gripper = kẹp nhíp cạnh nạp giấy; edge_trim = xén mép; bleed = tràn lề; gutter = chừa giữa con.
        gripper_cm = float(input_spec.get("gripper_cm") or 0)
        edge_trim_cm = float(input_spec.get("edge_trim_cm") or 0)
        bleed_cm = float(input_spec.get("bleed_cm") or 0)
        gutter_cm = float(input_spec.get("gutter_cm") or 0)

        # 2. Layout Calculation (pieces_per_sheet)
        pieces_per_sheet = 1
        if pieces_per_sheet_input is not None:
            try:
                pieces_per_sheet = int(pieces_per_sheet_input)
                if pieces_per_sheet < 1:
                    add_warning("blocking_error", "PIECES_PER_SHEET_INVALID", "Số con trên khổ (pieces_per_sheet) phải lớn hơn hoặc bằng 1.")
                    pieces_per_sheet = 1
            except (ValueError, TypeError):
                add_warning("blocking_error", "PIECES_PER_SHEET_INVALID", "Số con trên khổ không hợp lệ.")
                pieces_per_sheet = 1
        else:
            if not finished_w or not finished_h or not sheet_w or not sheet_h:
                add_warning(
                    "blocking_error",
                    "MISSING_DIMENSIONS",
                    "Không thể tính pieces_per_sheet do thiếu khổ vật liệu hoặc kích thước thành phẩm."
                )
                pieces_per_sheet = 1
            else:
                try:
                    fw, fh = float(finished_w), float(finished_h)
                    sw, sh = float(sheet_w), float(sheet_h)
                    if fw <= 0 or fh <= 0 or sw <= 0 or sh <= 0:
                        add_warning("blocking_error", "INVALID_DIMENSIONS", "Kích thước khổ phải lớn hơn 0.")
                        pieces_per_sheet = 1
                    else:
                        # #4 — trừ nhíp (1 cạnh nạp) + xén mép (2 cạnh); cộng bleed (2 cạnh) + gutter giữa con.
                        usable_w = sw - gripper_cm - 2 * edge_trim_cm
                        usable_h = sh - 2 * edge_trim_cm
                        piece_w = fw + 2 * bleed_cm + gutter_cm
                        piece_h = fh + 2 * bleed_cm + gutter_cm
                        if usable_w <= 0 or usable_h <= 0 or piece_w <= 0 or piece_h <= 0:
                            add_warning("blocking_error", "PIECES_PER_SHEET_ZERO", "Khổ thành phẩm (kèm bleed/nhíp/xén) lớn hơn khổ tờ vật liệu in.")
                            pieces_per_sheet = 1
                        else:
                            straight = max(0, int(usable_w // piece_w) * int(usable_h // piece_h))
                            if grain_locked:
                                pieces_per_sheet = straight
                            else:
                                rotated = max(0, int(usable_w // piece_h) * int(usable_h // piece_w))
                                pieces_per_sheet = max(straight, rotated)

                            if pieces_per_sheet < 1:
                                add_warning("blocking_error", "PIECES_PER_SHEET_ZERO", "Khổ thành phẩm lớn hơn khổ tờ vật liệu in.")
                                pieces_per_sheet = 1
                except (ValueError, TypeError):
                    add_warning("blocking_error", "INVALID_DIMENSIONS", "Kích thước khổ không hợp lệ.")
                    pieces_per_sheet = 1

        # 3. Load Material and Price
        material: Material | None = None
        material_cost: MaterialCost | None = None
        if not material_id:
            add_warning("blocking_error", "MISSING_MATERIAL", "Chưa cấu hình vật liệu in.")
        else:
            material = self.db.get(Material, material_id)
            if not material:
                add_warning("blocking_error", "MATERIAL_NOT_FOUND", f"Không tìm thấy vật liệu ID {material_id}.", "material", material_id)
            else:
                # Find active cost
                material_cost = self.db.execute(
                    select(MaterialCost)
                    .where(
                        MaterialCost.material_id == material_id,
                        MaterialCost.effective_from <= at_date,
                        (MaterialCost.effective_to == None) | (MaterialCost.effective_to > at_date)
                    )
                    .order_by(MaterialCost.effective_from.desc())
                ).scalars().first()
                if not material_cost:
                    add_warning("blocking_error", "MISSING_MATERIAL_PRICE", f"Không tìm thấy đơn giá cho vật liệu {material.name} tại ngày tính giá.", "material", material_id)

        # 4. Load Machine and Rate
        machine: Machine | None = None
        machine_rate: MachineRate | None = None
        if not machine_id:
            add_warning("blocking_error", "MISSING_MACHINE", "Chưa cấu hình máy in.")
        else:
            machine = self.db.get(Machine, machine_id)
            if not machine:
                add_warning("blocking_error", "MACHINE_NOT_FOUND", f"Không tìm thấy máy in ID {machine_id}.", "machine", machine_id)
            else:
                machine_rate = self.db.execute(
                    select(MachineRate)
                    .where(
                        MachineRate.machine_id == machine_id,
                        MachineRate.effective_from <= at_date,
                        (MachineRate.effective_to == None) | (MachineRate.effective_to > at_date)
                    )
                    .order_by(MachineRate.effective_from.desc())
                ).scalars().first()
                if not machine_rate:
                    add_warning("blocking_error", "MISSING_MACHINE_RATE", f"Không tìm thấy đơn giá vận hành cho máy {machine.name}.", "machine", machine_id)

        # 5. Load Operations
        operations_list: list[tuple[Operation, OperationRate | None, dict]] = []
        for idx, op_spec in enumerate(raw_ops):
            op_id = op_spec.get("operation_id")
            op_key = op_spec.get("operation_key")
            seq = op_spec.get("sequence", idx)
            exec_mode = op_spec.get("execution_mode", "internal")

            op = None
            if op_id:
                op = self.db.get(Operation, op_id)
            elif op_key:
                op = self.db.execute(select(Operation).where(Operation.operation_type == op_key)).scalars().first()

            if not op:
                add_warning("blocking_error", "OPERATION_NOT_FOUND", f"Không tìm thấy công đoạn tại chỉ mục {idx}.")
                continue

            op_rate = None
            if exec_mode == "internal":
                op_rate = self.db.execute(
                    select(OperationRate)
                    .where(
                        OperationRate.operation_id == op.id,
                        OperationRate.effective_from <= at_date,
                        (OperationRate.effective_to == None) | (OperationRate.effective_to > at_date)
                    )
                    .order_by(OperationRate.effective_from.desc())
                ).scalars().first()
                if not op_rate:
                    add_warning("blocking_error", "MISSING_OPERATION_RATE", f"Không tìm thấy đơn giá khoán cho công đoạn {op.name}.", "operation", op.id)
            
            operations_list.append((op, op_rate, op_spec))

        # Sort operations by sequence DESC for Reverse Waste Chain
        # We assume each operation_spec has sequence; if not, we use its original index.
        def get_seq(item):
            # item is (Operation, Rate, SpecDict)
            return item[2].get("sequence", 0)
        
        operations_list.sort(key=get_seq, reverse=True)

        # #27 — yield_rate (tỉ lệ thành phẩm đạt): số cần SẢN XUẤT = số giao ÷ yield_rate. Trước đây
        # engine không bao giờ đọc yield_rate → cấu hình vô nghĩa. Mặc định 1.0 = không ảnh hưởng.
        # TODO(SVN): xác nhận công thức (áp ở ĐẦU chuỗi, trước bù hao từng công đoạn).
        yield_rate = 1.0
        try:
            yr = self.norm_service.get_norm(
                "yield_rate",
                NormLookupContext(product_type=product_type, quantity=qty, at_date=at_date),
            )
            if yr and 0 < yr <= 1:
                yield_rate = yr
        except Exception:
            pass

        # 6. Reverse Waste Chain Calculation
        current_qty = int(math.ceil(qty / yield_rate))
        reverse_snaps = []
        for op, op_rate, op_spec in operations_list:
            # Lookup norm for this operation
            lookup_ctx = NormLookupContext(
                product_type=product_type,
                operation_id=op.id,
                operation_key=op.operation_type,
                quantity=current_qty,
                at_date=at_date
            )
            
            waste_pct = 0.02 # default fallback
            norm_id = None
            try:
                waste_pct = self.norm_service.get_norm("waste_pct_of_operation", lookup_ctx)
                # Find norm id for snapshot
                norm_rec = self.norm_service._find_norm_candidate("waste_pct_of_operation", lookup_ctx)
                if norm_rec:
                    norm_id = norm_rec.id
            except Exception:
                add_warning("warning", "DEFAULT_NORM_USED", f"Không tìm thấy định mức bù hao riêng cho công đoạn {op.name}, dùng mặc định 2%.", "operation", op.id)

            if waste_pct is None:
                waste_pct = 0.02

            if not (0 <= waste_pct < 1):
                add_warning("blocking_error", "INVALID_NORM_VALUE", f"Định mức bù hao công đoạn {op.name} phải từ 0 đến dưới 1.0 (nhận được {waste_pct}).", "operation", op.id)
                waste_pct = 0.02

            prev_qty = current_qty
            current_qty = int(math.ceil(prev_qty / (1 - waste_pct)))
            
            reverse_snaps.append({
                "operation_name": op.name,
                "operation_type": op.operation_type,
                "norm_id": norm_id,
                "waste_pct": waste_pct,
                "qty_after": prev_qty,
                "qty_before": current_qty
            })

        # Calculate printed sheets before print waste
        printed_sheets = int(math.ceil(current_qty / pieces_per_sheet))

        # Printing norms lookup
        print_ctx = NormLookupContext(
            product_type=product_type,
            machine_id=machine_id,
            colors=colors,
            sides=sides,
            quantity=qty,
            at_date=at_date
        )

        printing_waste_pct = 0.02
        print_waste_norm_id = None
        try:
            printing_waste_pct = self.norm_service.get_norm("running_waste_pct", print_ctx)
            norm_rec = self.norm_service._find_norm_candidate("running_waste_pct", print_ctx)
            if norm_rec:
                print_waste_norm_id = norm_rec.id
        except Exception:
            add_warning("warning", "DEFAULT_PRINT_RUNNING_WASTE", "Dùng định mức bù hao chạy bài in mặc định 2%.")

        if printing_waste_pct is None or not (0 <= printing_waste_pct < 1):
            printing_waste_pct = 0.02

        makeready_per_color_side = 15.0
        makeready_norm_id = None
        try:
            makeready_per_color_side = self.norm_service.get_norm("makeready_per_color_side", print_ctx)
            norm_rec = self.norm_service._find_norm_candidate("makeready_per_color_side", print_ctx)
            if norm_rec:
                makeready_norm_id = norm_rec.id
        except Exception:
            add_warning("warning", "DEFAULT_PRINT_MAKEREADY_WASTE", "Dùng định mức bù hao setup in mặc định 15 tờ/màu-mặt.")

        if makeready_per_color_side is None or makeready_per_color_side < 0:
            makeready_per_color_side = 15.0

        # Calculations
        running_sheets = int(math.ceil(printed_sheets / (1 - printing_waste_pct)))
        makeready_sheets = int(math.ceil(makeready_per_color_side * colors * sides * forms))
        # #5 — sàn makeready theo máy: một số máy cần tối thiểu N tờ canh bất kể số màu.
        # setup_waste_sheets mặc định 0 ⇒ không đổi (trước đây field này bị bỏ quên hoàn toàn).
        if machine is not None:
            makeready_sheets = max(makeready_sheets, int(float(machine.setup_waste_sheets or 0)))
        total_sheets = running_sheets + makeready_sheets

        calc_snapshot = {
            "qty_final": qty,
            "yield_rate": yield_rate,
            "pieces_per_sheet": pieces_per_sheet,
            "required_qty_before_printing": current_qty,
            "printed_sheets_before_waste": printed_sheets,
            "printing_waste_pct": printing_waste_pct,
            "makeready_per_color_side": makeready_per_color_side,
            "forms": forms,
            "colors": colors,
            "sides": sides,
            "running_sheets": running_sheets,
            "makeready_sheets": makeready_sheets,
            "total_sheets": total_sheets,
            "reverse_waste_chain": reverse_snaps
        }

        cost_lines: list[EstimateCostLine] = []

        # 7. Material Cost Line
        if material and material_cost:
            # Usage calculation
            is_sheet = (material.material_type in ("paper", "carton") or material_cost.price_unit in ("to", "ram"))
            
            unit_cost = float(material_cost.unit_price)
            setup_cost = 0.0
            min_charge_applied = False

            if is_sheet:
                unit = "to"
                if material_cost.price_unit == "ram":
                    # 1 ram ≈ 500 tờ
                    unit_cost = float(material_cost.unit_price) / 500.0
                elif material_cost.price_unit == "kg":
                    # #3 — quy đổi tờ↔kg: kg/tờ = (rộng×cao/10000 m²) × gsm/1000. Giấy bán theo ram VÀ kg (§4).
                    w_cm = float(sheet_w or material.width_cm or 0)
                    h_cm = float(sheet_h or material.height_cm or 0)
                    if material.gsm and w_cm > 0 and h_cm > 0:
                        sheet_kg = (w_cm * h_cm / 10000.0) * (float(material.gsm) / 1000.0)
                        unit_cost = float(material_cost.unit_price) * sheet_kg
                    else:
                        add_warning("blocking_error", "MISSING_GSM_FOR_KG", f"Giấy {material.name} tính giá theo kg nhưng thiếu định lượng (gsm) hoặc khổ để quy đổi ra tờ.", "material", material.id)
                        unit_cost = float(material_cost.unit_price)
                # else: giá theo tờ (unit_cost giữ nguyên đơn giá gốc)
                quantity = float(total_sheets)
                total_material_cost = quantity * unit_cost
                desc_text = f"Giấy in: {material.name} ({total_sheets} tờ)"
            else:
                # Area-based (decal, pp, canvas, lamination)
                # sheet size to m2: w_cm * h_cm / 10000
                w_cm = float(sheet_w or material.width_cm or 0)
                h_cm = float(sheet_h or material.height_cm or 0)
                sheet_m2 = (w_cm * h_cm) / 10000.0
                
                # If lamination (cán màng), we multiply by sides
                multiplier = 1.0
                if material.material_type == "lamination":
                    multiplier = float(sides)

                quantity = sheet_m2 * total_sheets * multiplier
                unit = "m2"
                total_material_cost = quantity * unit_cost
                desc_text = f"Vật tư {material.material_type}: {material.name} ({quantity:.2f} m²)"

            # #6 — bù hao riêng của vật tư (hao hụt xử lý/bốc dỡ), ngoài bù hao in & công đoạn.
            # default_waste_pct mặc định 0 ⇒ không đổi (trước đây field này không được engine đọc).
            waste_mult = 1.0 + float(material.default_waste_pct or 0) / 100.0
            if waste_mult != 1.0:
                quantity *= waste_mult
                total_material_cost = quantity * unit_cost

            # Apply min fee
            min_fee = float(material.min_fee or 0)
            if total_material_cost < min_fee:
                total_material_cost = min_fee
                min_charge_applied = True

            cost_lines.append(EstimateCostLine(
                category="material",
                description=desc_text,
                source_type="material_costs",
                source_id=material_cost.id,
                source_snapshot_json={
                    "material_id": material.id,
                    "code": material.code,
                    "name": material.name,
                    "unit": material.unit,
                    "price_unit": material_cost.price_unit,
                    "unit_price": material_cost.unit_price,
                    "min_fee": material.min_fee
                },
                calculation_snapshot_json={
                    "is_sheet": is_sheet,
                    "total_sheets": total_sheets,
                    "sheet_w": sheet_w,
                    "sheet_h": sheet_h,
                    "sides": sides,
                    "min_fee_applied": min_charge_applied
                },
                quantity=quantity,
                unit=unit,
                unit_cost=unit_cost,
                setup_cost=setup_cost,
                min_charge_applied=min_charge_applied,
                total_cost=total_material_cost
            ))

        # 8. Click/Ink Cost Line (for digital machines)
        if machine and machine_rate and machine.machine_type == "digital":
            # Lookup digital rate
            # digital usually charges per click/impression
            color_type = "cmyk" if colors > 1 else "grayscale"
            click_rate = self.db.execute(
                select(ClickInkRate)
                .where(
                    ClickInkRate.technology == "digital",
                    ClickInkRate.color_type == color_type,
                    (ClickInkRate.machine_id == None) | (ClickInkRate.machine_id == machine_id),
                    ClickInkRate.effective_from <= at_date,
                    (ClickInkRate.effective_to == None) | (ClickInkRate.effective_to > at_date)
                )
                # #21 — nulls_last: ưu tiên rate theo máy (machine_id non-null) hơn rate chung (NULL).
                # Postgres mặc định DESC = NULLS FIRST → bản chung lọt lên đầu, chọn sai. Ép NULLS LAST.
                .order_by(ClickInkRate.machine_id.desc().nulls_last(), ClickInkRate.effective_from.desc())
            ).scalars().first()

            if click_rate:
                # Calculate clicks
                if page_count and page_count > 0:
                    run_quantity = current_qty * page_count
                else:
                    run_quantity = total_sheets * sides

                click_unit_price = float(click_rate.unit_price)
                click_setup = float(click_rate.setup_fee or 0)
                click_cost = run_quantity * click_unit_price + click_setup
                
                min_charge_applied = False
                min_charge = float(click_rate.min_charge or 0)
                if click_cost < min_charge:
                    click_cost = min_charge
                    min_charge_applied = True

                cost_lines.append(EstimateCostLine(
                    category="click_ink",
                    description=f"Click in KTS ({color_type.upper()}): {run_quantity} lượt click",
                    source_type="click_ink_rates",
                    source_id=click_rate.id,
                    source_snapshot_json={
                        "rate_id": click_rate.id,
                        "unit_price": click_rate.unit_price,
                        "setup_fee": click_rate.setup_fee,
                        "min_charge": click_rate.min_charge
                    },
                    calculation_snapshot_json={
                        "run_quantity": run_quantity,
                        "page_count": page_count,
                        "total_sheets": total_sheets,
                        "sides": sides
                    },
                    quantity=float(run_quantity),
                    unit="click",
                    unit_cost=click_unit_price,
                    setup_cost=click_setup,
                    min_charge_applied=min_charge_applied,
                    total_cost=click_cost
                ))
            else:
                add_warning("warning", "MISSING_CLICK_RATE", f"Không tìm thấy đơn giá click KTS cho màu {color_type.upper()}.")

        # 9. Plate/Die Cost Line (for offset machines)
        if machine and machine_rate and machine.machine_type == "offset":
            # Lookup plate rate
            plate_rate = self.db.execute(
                select(PlateDieRate)
                .where(
                    PlateDieRate.technology == "offset",
                    PlateDieRate.plate_type == "ban_kem_offset",
                    PlateDieRate.effective_from <= at_date,
                    (PlateDieRate.effective_to == None) | (PlateDieRate.effective_to > at_date)
                )
                .order_by(PlateDieRate.effective_from.desc())
            ).scalars().first()

            if plate_rate:
                plates_count = colors * sides * forms
                plate_cost = plates_count * float(plate_rate.unit_price)
                
                cost_lines.append(EstimateCostLine(
                    category="plate_die",
                    description=f"Bản kẽm Offset: {plates_count} bản ({colors} màu x {sides} mặt x {forms} khuôn)",
                    source_type="plate_die_rates",
                    source_id=plate_rate.id,
                    source_snapshot_json={
                        "rate_id": plate_rate.id,
                        "unit_price": plate_rate.unit_price,
                        "setup_fee": plate_rate.setup_fee
                    },
                    calculation_snapshot_json={
                        "colors": colors,
                        "sides": sides,
                        "forms": forms
                    },
                    quantity=float(plates_count),
                    unit="ban",
                    unit_cost=float(plate_rate.unit_price),
                    setup_cost=0.0,
                    min_charge_applied=False,
                    total_cost=plate_cost
                ))
            else:
                add_warning("warning", "MISSING_PLATE_RATE", "Không tìm thấy đơn giá bản kẽm offset.")

        # 9b. Offset Ink Cost Line (#1) — mực in offset tính theo lượt-màu (impressions = tờ × màu × mặt).
        # Đơn giá là định mức versioned `ink_cost_per_1000_impressions` (đ/1000 lượt), cấu hình trên UI.
        if machine and machine_rate and machine.machine_type == "offset":
            impressions = int(total_sheets * colors * sides)
            ink_rate = None
            ink_norm_id = None
            try:
                ink_rate = self.norm_service.get_norm("ink_cost_per_1000_impressions", print_ctx)
                norm_rec = self.norm_service._find_norm_candidate("ink_cost_per_1000_impressions", print_ctx)
                if norm_rec:
                    ink_norm_id = norm_rec.id
            except Exception:
                pass

            if ink_rate and ink_rate > 0:
                ink_cost = math.ceil(impressions / 1000.0) * float(ink_rate)
                cost_lines.append(EstimateCostLine(
                    category="ink",
                    description=f"Mực in offset: {impressions} lượt-màu ({colors} màu × {sides} mặt × {total_sheets} tờ)",
                    source_type="norms",
                    source_id=ink_norm_id,
                    source_snapshot_json={
                        "norm_id": ink_norm_id,
                        "ink_cost_per_1000_impressions": ink_rate
                    },
                    calculation_snapshot_json={
                        "impressions": impressions,
                        "colors": colors,
                        "sides": sides,
                        "total_sheets": total_sheets
                    },
                    quantity=float(impressions),
                    unit="luot",
                    unit_cost=float(ink_rate) / 1000.0,
                    setup_cost=0.0,
                    min_charge_applied=False,
                    total_cost=ink_cost
                ))
            else:
                add_warning("warning", "MISSING_INK_RATE", "Chưa cấu hình đơn giá mực offset (định mức ink_cost_per_1000_impressions) — chi phí mực chưa được tính.")

        # 10. Machine Operating Cost Line
        if machine and machine_rate:
            # Resolve run qty based on speed_unit
            speed_unit = machine.speed_unit or "to/gio"
            
            if speed_unit == "to/gio":
                run_qty = float(total_sheets)
                unit_label = "to"
            elif speed_unit == "trang/phut":
                if page_count and page_count > 0:
                    run_qty = float(current_qty * page_count)
                else:
                    run_qty = float(total_sheets * sides)
                unit_label = "trang"
            elif speed_unit == "m2/gio":
                w_cm = float(sheet_w or machine.max_width_cm or 0)
                h_cm = float(sheet_h or machine.max_height_cm or 0)
                sheet_m2 = (w_cm * h_cm) / 10000.0
                run_qty = float(total_sheets * sheet_m2)
                unit_label = "m2"
            else:
                run_qty = float(total_sheets)
                unit_label = "to"

            # Speed hours calculation
            speed = float(machine.speed or 1.0)
            if speed_unit == "trang/phut":
                run_time_hours = run_qty / (speed * 60.0)
            else:
                run_time_hours = run_qty / speed

            # #2 — số pass = ⌈màu / số đơn vị màu của máy⌉ khi job nhiều màu hơn số đơn vị in của máy (§31c).
            # VD 6 màu trên máy 4 đơn vị → 2 lượt chạy → nhân đôi giờ máy. num_ink_units None ⇒ passes=1.
            num_ink_units = getattr(machine, "num_ink_units", None)
            passes = 1
            if num_ink_units:
                passes = max(1, math.ceil(colors / int(num_ink_units)))
            if passes > 1:
                run_time_hours *= passes
                add_warning("info", "MULTI_PASS", f"Job {colors} màu chạy trên máy {num_ink_units} đơn vị in → {passes} lượt in (giờ máy ×{passes}).", "machine", machine.id)

            setup_hours = float(machine.setup_time_mins + machine.changeover_time_mins) / 60.0
            machine_hours = run_time_hours + setup_hours
            
            hourly_rate = float(machine_rate.hourly_rate)
            machine_cost = machine_hours * hourly_rate
            
            min_charge_applied = False
            min_charge = float(machine_rate.min_charge or 0)
            if machine_cost < min_charge:
                machine_cost = min_charge
                min_charge_applied = True

            cost_lines.append(EstimateCostLine(
                category="machine",
                description=f"Chạy máy in: {machine.name} ({machine_hours:.2f} giờ)",
                source_type="machine_rates",
                source_id=machine_rate.id,
                source_snapshot_json={
                    "rate_id": machine_rate.id,
                    "hourly_rate": machine_rate.hourly_rate,
                    "min_charge": machine_rate.min_charge
                },
                calculation_snapshot_json={
                    "speed": speed,
                    "speed_unit": speed_unit,
                    "run_qty": run_qty,
                    "run_time_hours": run_time_hours,
                    "setup_hours": setup_hours,
                    "machine_hours": machine_hours
                },
                quantity=machine_hours,
                unit="gio",
                unit_cost=hourly_rate,
                setup_cost=0.0,
                min_charge_applied=min_charge_applied,
                total_cost=machine_cost
            ))

        # 11. Operation Cost Lines
        # Reverse sorted operations_list contains (Operation, Rate, Spec)
        # Note: when creating cost lines, we can add them in original sequence order if desired.
        # But here we append them.
        for op, op_rate, op_spec in operations_list:
            exec_mode = op_spec.get("execution_mode", "internal")
            
            if exec_mode == "internal" and op_rate:
                # Find intermediate qty for this operation step
                qty_at_op = qty
                for snap in reverse_snaps:
                    if snap["operation_type"] == op.operation_type:
                        qty_at_op = snap["qty_before"]
                        break

                # Resolve quantity based on op.unit
                op_unit = op.unit or "to"
                if op_unit == "to":
                    qty_val = float(math.ceil(qty_at_op / pieces_per_sheet))
                elif op_unit == "m2":
                    w_cm = float(sheet_w or 0)
                    h_cm = float(sheet_h or 0)
                    sheet_m2 = (w_cm * h_cm) / 10000.0
                    sheets_count = math.ceil(qty_at_op / pieces_per_sheet)
                    qty_val = float(sheets_count * sheet_m2)
                elif op_unit in ("cuon", "cai", "san_pham"):
                    qty_val = float(qty_at_op)
                else:
                    qty_val = float(qty_at_op)

                run_rate = float(op_rate.run_rate)
                labor_rate = float(op_rate.labor_rate or 0)
                setup_fee = float(op_rate.setup_fee or 0)

                run_cost = qty_val * run_rate
                labor_cost = qty_val * labor_rate
                op_cost = run_cost + labor_cost + setup_fee

                min_charge_applied = False
                min_charge = float(op_rate.min_charge or 0)
                if op_cost < min_charge:
                    op_cost = min_charge
                    min_charge_applied = True

                category = "packing" if op.operation_type == "dong_goi" else "operation"

                # Format vi-VN: chấm ngăn nghìn, phẩy thập phân (331.0 → "331", 1666.67 → "1.666,67")
                if float(qty_val).is_integer():
                    qty_disp = f"{int(qty_val):,}".replace(",", ".")
                else:
                    qty_disp = f"{qty_val:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
                cost_lines.append(EstimateCostLine(
                    category=category,
                    description=f"Gia công {op.name}: {qty_disp} {UNIT_LABELS_VI.get(op_unit, op_unit)}",
                    source_type="operation_rates",
                    source_id=op_rate.id,
                    source_snapshot_json={
                        "rate_id": op_rate.id,
                        "setup_fee": op_rate.setup_fee,
                        "run_rate": op_rate.run_rate,
                        "labor_rate": op_rate.labor_rate,
                        "min_charge": op_rate.min_charge
                    },
                    calculation_snapshot_json={
                        "qty_at_op": qty_at_op,
                        "pieces_per_sheet": pieces_per_sheet,
                        "run_cost": run_cost,
                        "labor_cost": labor_cost,
                        "setup_fee": setup_fee
                    },
                    quantity=qty_val,
                    unit=op_unit,
                    unit_cost=run_rate + labor_rate,
                    setup_cost=setup_fee,
                    min_charge_applied=min_charge_applied,
                    total_cost=op_cost
                ))
            
            elif exec_mode == "outsourced":
                # Outsource lookup (SEAM-12)
                # For Phase 2A, we support flat manual input or basic fallback rate from op_spec
                outsource_cost = float(op_spec.get("outsource_cost", 0.0))
                if outsource_cost <= 0:
                    add_warning("warning", "MISSING_OUTSOURCE_PRICE", f"Công đoạn {op.name} thuê ngoài chưa nhập chi phí.")

                cost_lines.append(EstimateCostLine(
                    category="outsource",
                    description=f"Thuê ngoài {op.name}",
                    source_type="input_spec",
                    source_id=None,
                    source_snapshot_json=None,
                    calculation_snapshot_json=None,
                    quantity=1.0,
                    unit="lo",
                    unit_cost=outsource_cost,
                    setup_cost=0.0,
                    min_charge_applied=False,
                    total_cost=outsource_cost
                ))

        # 12. Accumulate Cost
        total_cost = sum(float(line.total_cost) for line in cost_lines)

        return cost_lines, total_cost, warnings
