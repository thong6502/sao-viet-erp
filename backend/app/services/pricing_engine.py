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
from ..models.plate_die_rate import PlateDieRate
from ..models.product_type_catalog import ProductTypeCatalog
from ..models.estimate import EstimateCostLine
from ..services.norm_service import NormService, NormLookupContext

# Nhãn tiếng Việt cho mã đơn vị khi nhúng vào mô tả dòng chi phí (hiển thị cho người dùng)
UNIT_LABELS_VI = {
    "to": "tờ", "ban": "bản", "luot": "lượt", "gio": "giờ", "trang": "trang",
    "m2": "m²", "cuon": "cuốn", "cai": "cái", "san_pham": "sản phẩm", "lo": "lô",
    "nghin_to": "1.000 tờ", "nghin_cai": "1.000 cái", "thung": "thùng",
}

def _rule_label(norm) -> str | None:
    """Nhãn rule để diễn giải trên màn Tính giá: 'CODE v{version}' (fallback tên/khóa)."""
    if norm is None:
        return None
    base = getattr(norm, "code", None) or getattr(norm, "name", None) or getattr(norm, "norm_key", None)
    ver = getattr(norm, "version", None)
    if base and ver:
        return f"{base} v{ver}"
    return base


def _clamp(v: float, lo, hi) -> float:
    """Kẹp v vào [lo, hi] (bỏ qua biên None)."""
    v = float(v)
    if lo is not None:
        v = max(v, float(lo))
    if hi is not None:
        v = min(v, float(hi))
    return v


def _compute_setup_sheets(norm, colors: int, sides: int) -> float:
    """Bù hao setup/makeready (danh mục #7 — SETUP_WASTE). Cộng thêm số tờ.

    method PER_COLOR_SIDE (legacy) hoặc None → value × màu × mặt (giữ đúng công thức cũ).
    Ngược lại → setup_waste_qty + per_color×màu + per_side×mặt. Sau đó clamp min/max.
    """
    method = getattr(norm, "calculation_method", None)
    if method in (None, "PER_COLOR_SIDE"):
        base = float(norm.value or 0) * colors * sides
    else:
        base = (
            float(getattr(norm, "setup_waste_qty", None) or 0)
            + float(getattr(norm, "setup_waste_per_color", None) or 0) * colors
            + float(getattr(norm, "setup_waste_per_side", None) or 0) * sides
        )
    return _clamp(base, getattr(norm, "min_waste_qty", None), getattr(norm, "max_waste_qty", None))


def _compute_running_sheets(norm, base_qty: int) -> float:
    """Bù hao chạy máy (RUNNING_WASTE) — CỘNG thêm ceil(base × %), clamp min/max."""
    pct = float(norm.value or 0)
    if not (0 <= pct < 1):
        pct = 0.0
    sheets = math.ceil(base_qty * pct)
    return _clamp(sheets, getattr(norm, "min_waste_qty", None), getattr(norm, "max_waste_qty", None))


def _compute_paper_extra(norm, production_sheets: int) -> float:
    """Hao giấy riêng (PAPER_EXTRA_WASTE) — số tờ cộng vào tờ mua, clamp min/max.

    PERCENT: ceil(SX × value) · FIXED: value tờ · PER_REAM: value × (SX / 500).
    """
    method = getattr(norm, "calculation_method", None) or "PERCENT"
    if method == "FIXED":
        v = float(norm.value or 0)
    elif method == "PER_REAM":
        v = float(norm.value or 0) * (production_sheets / 500.0)
    else:  # PERCENT
        v = math.ceil(production_sheets * float(norm.value or 0))
    return _clamp(v, getattr(norm, "min_waste_qty", None), getattr(norm, "max_waste_qty", None))


class PricingEngine:
    def _op_yield(self, op, op_ctx) -> tuple[float, int | None]:
        """Tỷ lệ đạt RIÊNG của một công đoạn sau in. Ưu tiên norm gắn công đoạn; nếu không có
        thì dùng tỷ lệ đạt mặc định khai ở công đoạn (spec §G). Norm khâu in / chung (không gắn
        CĐ) KHÔNG rớt xuống đây. Mặc định 1.0 (không hao)."""
        try:
            rec = self.norm_service._find_norm_candidate("yield_rate", op_ctx)
        except Exception:
            rec = None
        if rec is not None and (rec.operation_id is not None or rec.operation_key is not None):
            v = float(rec.value or 0)
            if 0 < v <= 1:
                return v, rec.id
        # spec §G — fallback: tỷ lệ đạt mặc định khai ở công đoạn (% → phân số).
        if getattr(op, "has_yield_loss", False) and getattr(op, "default_yield_rate", None) is not None:
            yr = float(op.default_yield_rate)
            if 0 < yr <= 100:
                return yr / 100.0, None
        return 1.0, None

    def _pick_cost_by_band(self, material_id: int, price_unit: str, at_date, qty: float):
        """Chọn dòng giá vật tư theo BẬC SỐ LƯỢNG (danh mục #2). Bậc khớp theo SỐ TỜ MUA (nửa-mở
        [from, to); bậc null = mọi SL). Ưu tiên bậc cụ thể; hòa → effective_from mới nhất.
        Không có dòng nào khớp → None (giữ lựa chọn cũ)."""
        rows = self.db.execute(
            select(MaterialCost)
            .where(
                MaterialCost.material_id == material_id,
                MaterialCost.price_unit == price_unit,
                MaterialCost.effective_from <= at_date,
                (MaterialCost.effective_to == None) | (MaterialCost.effective_to > at_date),  # noqa: E711
            )
            .order_by(MaterialCost.effective_from.desc())
        ).scalars().all()

        def band_ok(c) -> bool:
            lo, hi = c.quantity_from, c.quantity_to
            if lo is not None and qty < float(lo):
                return False
            if hi is not None and qty >= float(hi):
                return False
            return True

        matching = [c for c in rows if band_ok(c)]
        if not matching:
            return None
        matching.sort(
            key=lambda c: (c.quantity_from is not None or c.quantity_to is not None, c.effective_from),
            reverse=True,
        )
        return matching[0]

    def _op_setup(self, op_ctx, colors: int, sides: int) -> tuple[float, int | None]:
        """Bù hao setup RIÊNG của một công đoạn sau in (tờ). Chỉ nhận norm gắn công đoạn."""
        try:
            rec = self.norm_service._find_norm_candidate("makeready_per_color_side", op_ctx)
        except Exception:
            rec = None
        if rec is None or (rec.operation_id is None and rec.operation_key is None):
            return 0.0, None
        return _compute_setup_sheets(rec, colors, sides), rec.id

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
        # Loại sản phẩm (page #1) khai bleed/gutter/lề xén MẶC ĐỊNH (mm). Nếu spec KHÔNG gửi các tham
        # số này thì lấy default của loại SP (mm→cm). Spec có gửi (kể cả 0) thì tôn trọng spec.
        # Loại SP không có bản ghi catalog (vd golden 'hop_carton') → default 0 = giữ hành vi cũ.
        _pt_cfg = None
        if product_type:
            from ..models.product_type_catalog import ProductTypeCatalog
            _pt_cfg = self.db.execute(
                select(ProductTypeCatalog).where(ProductTypeCatalog.product_type == product_type)
            ).scalars().first()

        def _dim_cm(spec_key: str, catalog_mm_attr: str) -> float:
            if spec_key in input_spec and input_spec.get(spec_key) is not None:
                return float(input_spec.get(spec_key) or 0)
            if _pt_cfg is not None:
                return float(getattr(_pt_cfg, catalog_mm_attr, 0) or 0) / 10.0
            return 0.0

        edge_trim_cm = _dim_cm("edge_trim_cm", "default_trim_mm")
        bleed_cm = _dim_cm("bleed_cm", "default_bleed_mm")
        gutter_cm = _dim_cm("gutter_cm", "default_gutter_mm")

        # 1b. Hệ số in ấn suy THUẦN theo số mặt (đã bỏ danh mục Quy tắc bình bài):
        #   finished_factor = 1  → số con thành phẩm = số con hình học (không quy đổi bình bài),
        #   plate_set_factor = số mặt (1 mặt → 1 bộ kẽm, 2 mặt → 2 bộ kẽm riêng),
        #   ink_pass_factor  = số mặt (nuôi tiền mực theo lượt-màu),
        #   pass_count       = 1 lượt qua máy cơ bản (multi-pass theo số màu/máy tính riêng ở mục Máy).
        finished_factor = 1.0
        plate_set_factor = float(sides)
        ink_pass_factor = float(sides)

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

        # finished_factor = 1 (đã bỏ bình bài) → số con thành phẩm = số con hình học.
        geometric_pieces_per_sheet = pieces_per_sheet

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

            # Nạp bảng giá hiệu lực cho cả nội bộ lẫn thuê ngoài (thuê ngoài dùng bảng giá NCC — spec §E).
            op_rate = self.db.execute(
                select(OperationRate)
                .where(
                    OperationRate.operation_id == op.id,
                    OperationRate.effective_from <= at_date,
                    (OperationRate.effective_to == None) | (OperationRate.effective_to > at_date)
                )
                .order_by(OperationRate.effective_from.desc())
            ).scalars().first()
            if exec_mode == "internal" and not op_rate:
                add_warning("blocking_error", "MISSING_OPERATION_RATE", f"Không tìm thấy đơn giá khoán cho công đoạn {op.name}.", "operation", op.id)

            operations_list.append((op, op_rate, op_spec))

        # Sort operations by sequence DESC for Reverse Waste Chain
        # We assume each operation_spec has sequence; if not, we use its original index.
        def get_seq(item):
            # item is (Operation, Rate, SpecDict)
            return item[2].get("sequence", 0)
        
        operations_list.sort(key=get_seq, reverse=True)

        # 6. BÙ HAO — mô hình mới: một con số % duy nhất khai ở Loại sản phẩm (waste_pct),
        # thay cả module Định mức cũ (yield/makeready/running/paper_extra). Áp thẳng vào SỐ TỜ
        # SẢN XUẤT → đội giấy + mực + giờ máy; KHÔNG đội kẽm (kẽm làm 1 lần, không hao theo tờ).
        # Công đoạn dùng đúng số lượng đặt (không còn chuỗi ngược theo tỷ lệ đạt).
        current_qty = int(qty)
        reverse_snaps = [
            {
                "operation_name": op.name, "operation_type": op.operation_type,
                "norm_id": None, "setup_norm_id": None, "yield_rate": 1.0,
                "setup_sheets": 0, "waste_pct": 0.0,
                "qty_after": current_qty, "qty_before": current_qty,
            }
            for op, _op_rate, _op_spec in operations_list
        ]

        # Số tờ cần in (lý thuyết) = số lượng ÷ số con/tờ.
        printed_sheets = int(math.ceil(current_qty / pieces_per_sheet))

        # % bù hao lấy từ Loại sản phẩm.
        waste_pct = 0.0
        if product_type:
            pt_row = self.db.execute(
                select(ProductTypeCatalog).where(ProductTypeCatalog.product_type == product_type)
            ).scalars().first()
            if pt_row is not None and getattr(pt_row, "waste_pct", None):
                waste_pct = max(0.0, float(pt_row.waste_pct))

        # Số tờ 3 lớp: lý thuyết (printed_sheets) → sản xuất (×(1+hao%)) → mua.
        print_yield = 1.0
        print_yield_norm_id = None
        print_yield_rule = None
        sheets_after_yield = printed_sheets
        makeready_sheets = 0
        makeready_norm_id = None
        makeready_rule = None
        makeready_per_color_side = 0.0
        print_waste_norm_id = None
        printing_waste_pct = waste_pct / 100.0
        running_rule = f"Bù hao {waste_pct:g}% (Loại SP)" if waste_pct > 0 else None
        total_sheets = int(math.ceil(printed_sheets * (1.0 + waste_pct / 100.0)))
        running_add = total_sheets - printed_sheets  # phần tờ hao thêm
        running_sheets = total_sheets

        # §12 nâng cao — override SỐ TỜ SẢN XUẤT (kèm lý do). Áp trước khi tính giấy/mực/công in
        # (cascade). input_spec["override_production_sheets"] = {value, reason}.
        _ovps = input_spec.get("override_production_sheets")
        if isinstance(_ovps, dict) and _ovps.get("value") is not None:
            _reason = (_ovps.get("reason") or "").strip()
            if not _reason:
                add_warning("blocking_error", "OVERRIDE_NO_REASON", "Sửa tay số tờ sản xuất phải nhập lý do.")
            else:
                try:
                    _v = int(float(_ovps["value"]))
                    if _v >= 1:
                        add_warning("info", "OVERRIDE_PRODUCTION_SHEETS",
                                    f"Số tờ sản xuất sửa tay: {total_sheets:,}→{_v:,} tờ (lý do: {_reason}).")
                        total_sheets = _v
                except (ValueError, TypeError):
                    add_warning("warning", "OVERRIDE_INVALID", "Override số tờ sản xuất không hợp lệ.")

        # Không còn "hao giấy riêng" theo norm — % hao đã gộp hết vào total_sheets.
        paper_extra_sheets = 0
        paper_extra_norm_id = None
        paper_rule = None
        sheets_to_buy = total_sheets

        # Diễn giải "Bù hao áp dụng" cho màn Tính giá.
        norms_applied: list[dict] = []
        norms_applied.append({"label": "Số tờ lý thuyết", "rule": None, "detail": f"{printed_sheets:,} tờ".replace(",", "."), "norm_id": None})
        if running_add:
            norms_applied.append({
                "label": "Bù hao", "rule": running_rule,
                "detail": f"+{running_add:,} tờ ({waste_pct:g}%)".replace(",", "."), "norm_id": None,
            })
        norms_applied.append({"label": "Số tờ sản xuất", "rule": None, "detail": f"{total_sheets:,} tờ".replace(",", "."), "norm_id": None})

        # Số tờ 3 lớp: lý thuyết (printed_sheets) → sản xuất (total_sheets) → MUA GIẤY (purchase_sheets).
        # Mua giấy dùng Khổ giấy: nếu spec chỉ định khổ giấy mua (purchase_sheet_w/h) lớn hơn khổ tờ in,
        # mỗi tờ mua cắt ra nhiều tờ in → số tờ mua = ⌈số tờ cần mua / số tờ in mỗi tờ mua⌉.
        # Mặc định không có khổ mua ⇒ khổ mua = khổ in ⇒ số tờ mua = số tờ cần mua (giữ nguyên hành vi cũ).
        purchase_w = input_spec.get("purchase_sheet_w")
        purchase_h = input_spec.get("purchase_sheet_h")
        press_per_purchase = 1
        purchase_sheets = sheets_to_buy
        try:
            if purchase_w and purchase_h and sheet_w and sheet_h:
                pw, ph = float(purchase_w), float(purchase_h)
                pressw, pressh = float(sheet_w), float(sheet_h)
                if pressw > 0 and pressh > 0 and pw >= pressw and ph >= pressh:
                    straight = int(pw // pressw) * int(ph // pressh)
                    rotated = int(pw // pressh) * int(ph // pressw)
                    press_per_purchase = max(1, straight, rotated)
                    purchase_sheets = int(math.ceil(sheets_to_buy / press_per_purchase))
        except (ValueError, TypeError):
            press_per_purchase = 1
            purchase_sheets = sheets_to_buy

        # Chọn lại giá vật tư theo BẬC số tờ mua (danh mục #2) — nếu vật tư có nhiều bậc.
        if material is not None and material_cost is not None:
            banded = self._pick_cost_by_band(material.id, material_cost.price_unit, at_date, purchase_sheets)
            if banded is not None:
                material_cost = banded

        calc_snapshot = {
            "qty_final": qty,
            "print_yield": print_yield,
            "print_yield_norm_id": print_yield_norm_id,
            "finished_factor": finished_factor,
            "plate_set_factor": plate_set_factor,
            "ink_pass_factor": ink_pass_factor,
            "geometric_pieces_per_sheet": geometric_pieces_per_sheet,
            "pieces_per_sheet": pieces_per_sheet,
            "required_qty_before_printing": current_qty,
            "printed_sheets_before_waste": printed_sheets,
            "sheets_after_yield": sheets_after_yield,
            "printing_waste_pct": printing_waste_pct,
            "makeready_per_color_side": makeready_per_color_side,
            "makeready_norm_id": makeready_norm_id,
            "print_waste_norm_id": print_waste_norm_id,
            "forms": forms,
            "colors": colors,
            "sides": sides,
            "running_sheets": running_sheets,
            "running_waste_sheets": running_add,
            "makeready_sheets": makeready_sheets,
            "total_sheets": total_sheets,
            "theoretical_sheets": printed_sheets,
            "production_sheets": total_sheets,
            "paper_extra_sheets": paper_extra_sheets,
            "paper_extra_norm_id": paper_extra_norm_id,
            "press_per_purchase": press_per_purchase,
            "purchase_sheets": purchase_sheets,
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
                quantity = float(purchase_sheets)
                total_material_cost = quantity * unit_cost
                if press_per_purchase > 1:
                    desc_text = f"Giấy in: {material.name} ({purchase_sheets} tờ mua, cắt {press_per_purchase} tờ in/tờ mua từ {total_sheets} tờ SX)"
                else:
                    desc_text = f"Giấy in: {material.name} ({purchase_sheets} tờ)"
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

            # §12 nâng cao — override ĐƠN GIÁ vật tư (đơn giá/đơn vị cuối, bỏ qua quy đổi ram/kg).
            _ovmp = input_spec.get("override_material_unit_price")
            if isinstance(_ovmp, dict) and _ovmp.get("value") is not None:
                _r = (_ovmp.get("reason") or "").strip()
                if not _r:
                    add_warning("blocking_error", "OVERRIDE_NO_REASON", "Sửa tay đơn giá vật tư phải nhập lý do.")
                else:
                    try:
                        _uc = float(_ovmp["value"])
                        if _uc >= 0:
                            add_warning("info", "OVERRIDE_MATERIAL_PRICE",
                                        f"Đơn giá vật tư sửa tay: {unit_cost:,.2f}→{_uc:,.2f} (lý do: {_r}).")
                            unit_cost = _uc
                            total_material_cost = quantity * unit_cost
                    except (ValueError, TypeError):
                        add_warning("warning", "OVERRIDE_INVALID", "Override đơn giá vật tư không hợp lệ.")

            # Apply min fee
            min_fee = float(material.min_fee or 0)
            if total_material_cost < min_fee:
                total_material_cost = min_fee
                min_charge_applied = True

            # Phí vận chuyển (danh mục #2) — cộng 1 lần vào dòng vật tư (0 ⇒ không đổi hành vi cũ).
            transport_fee = float(getattr(material_cost, "transport_fee", 0) or 0)
            if transport_fee > 0:
                total_material_cost += transport_fee

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
                    "min_fee": material.min_fee,
                    "supplier": getattr(material_cost, "supplier", None),
                    "price_type": getattr(material_cost, "price_type", None),
                    "transport_fee": transport_fee,
                    "price_version": getattr(material_cost, "version", None),
                },
                calculation_snapshot_json={
                    "is_sheet": is_sheet,
                    "theoretical_sheets": printed_sheets,
                    "sheets_after_yield": sheets_after_yield,
                    "makeready_sheets": makeready_sheets,
                    "running_waste_sheets": running_add,
                    "production_sheets": total_sheets,
                    "paper_extra_sheets": paper_extra_sheets,
                    "purchase_sheets": purchase_sheets,
                    "press_per_purchase": press_per_purchase,
                    "total_sheets": total_sheets,
                    "sheet_w": sheet_w,
                    "sheet_h": sheet_h,
                    "sides": sides,
                    "min_fee_applied": min_charge_applied,
                    # Diễn giải "Định mức & Bù hao áp dụng" (mỗi bước nêu rule) — màn Tính giá.
                    "norms_applied": norms_applied,
                },
                quantity=quantity,
                unit=unit,
                unit_cost=unit_cost,
                setup_cost=setup_cost,
                min_charge_applied=min_charge_applied,
                total_cost=total_material_cost
            ))

        # 8. Plate/Die Cost Line (for offset machines) — chọn giá KẼM theo MÁY (DM #5).
        if machine and machine_rate and machine.machine_type == "offset":
            from ..repositories.plate_die_rate_repo import PlateDieRateRepository
            plate_rate = PlateDieRateRepository(self.db).resolve_plate_for_machine(machine_id, at_date)

            if plate_rate:
                # Số bản kẽm = số màu × số bộ kẽm (=số mặt) × số form/tay.
                plates_count = int(round(colors * plate_set_factor * forms))
                # Tiền kẽm = số bản × đơn giá + phí setup, sàn theo phí tối thiểu (đơn giá kẽm #5).
                # Seed hiện setup=min=0 ⇒ no-op, golden khay-carton giữ nguyên số.
                plate_setup = float(plate_rate.setup_fee or 0)
                plate_min = float(plate_rate.min_charge or 0)
                plate_cost = plates_count * float(plate_rate.unit_price) + plate_setup
                min_charge_applied = False
                if plate_cost < plate_min:
                    plate_cost = plate_min
                    min_charge_applied = True

                cost_lines.append(EstimateCostLine(
                    category="plate_die",
                    description=f"Bản kẽm Offset: {plates_count} bản ({colors} màu × {plate_set_factor:g} bộ kẽm × {forms} khuôn)",
                    source_type="plate_die_rates",
                    source_id=plate_rate.id,
                    source_snapshot_json={
                        "rate_id": plate_rate.id,
                        "unit_price": plate_rate.unit_price,
                        "setup_fee": plate_rate.setup_fee,
                        "min_charge": plate_rate.min_charge,
                    },
                    calculation_snapshot_json={
                        "colors": colors,
                        "sides": sides,
                        "plate_set_factor": plate_set_factor,
                        "forms": forms
                    },
                    quantity=float(plates_count),
                    unit="ban",
                    unit_cost=float(plate_rate.unit_price),
                    setup_cost=plate_setup,
                    min_charge_applied=min_charge_applied,
                    total_cost=plate_cost
                ))
            else:
                add_warning("warning", "MISSING_PLATE_RATE", "Không tìm thấy đơn giá bản kẽm offset.")

        # 9b. Offset Ink Cost Line — mực in offset tính theo lượt-màu (impressions = tờ × màu × mặt).
        # Đơn giá mực đọc từ DANH MỤC VẬT TƯ (#2): material nhóm 'ink', giá price_unit='nghin_luot'
        # (đ/1.000 lượt). Spec có thể chỉ định ink_material_id; nếu không → mực offset mặc định (id nhỏ nhất).
        if machine and machine_rate and machine.machine_type == "offset":
            # Số lượt-màu = số tờ sản xuất × số màu × số mặt (ink_pass_factor).
            impressions = int(round(total_sheets * colors * ink_pass_factor))
            ink_material = None
            ink_material_id = input_spec.get("ink_material_id")
            if ink_material_id:
                ink_material = self.db.get(Material, ink_material_id)
            if ink_material is None:
                ink_material = self.db.execute(
                    select(Material)
                    .join(MaterialCost, MaterialCost.material_id == Material.id)
                    .where(
                        Material.material_group == "ink",
                        Material.is_active == True,  # noqa: E712
                        MaterialCost.price_unit == "nghin_luot",
                        MaterialCost.effective_from <= at_date,
                        (MaterialCost.effective_to == None) | (MaterialCost.effective_to > at_date),
                    )
                    .order_by(Material.id.asc())
                ).scalars().first()

            ink_cost_row = None
            if ink_material is not None:
                ink_cost_row = self.db.execute(
                    select(MaterialCost)
                    .where(
                        MaterialCost.material_id == ink_material.id,
                        MaterialCost.price_unit == "nghin_luot",
                        MaterialCost.effective_from <= at_date,
                        (MaterialCost.effective_to == None) | (MaterialCost.effective_to > at_date),
                    )
                    .order_by(MaterialCost.effective_from.desc())
                ).scalars().first()

            if ink_cost_row and ink_cost_row.unit_price and ink_cost_row.unit_price > 0:
                ink_rate = float(ink_cost_row.unit_price)
                ink_cost = math.ceil(impressions / 1000.0) * ink_rate
                cost_lines.append(EstimateCostLine(
                    category="ink",
                    description=f"Mực in offset: {impressions} lượt-màu ({colors} màu × {ink_pass_factor:g} lượt × {total_sheets} tờ) — {ink_material.name}",
                    source_type="material_costs",
                    source_id=ink_cost_row.id,
                    source_snapshot_json={
                        "material_id": ink_material.id,
                        "code": ink_material.code,
                        "name": ink_material.name,
                        "price_unit": "nghin_luot",
                        "unit_price": ink_cost_row.unit_price,
                    },
                    calculation_snapshot_json={
                        "impressions": impressions,
                        "colors": colors,
                        "sides": sides,
                        "ink_pass_factor": ink_pass_factor,
                        "total_sheets": total_sheets,
                    },
                    quantity=float(impressions),
                    unit="luot",
                    unit_cost=ink_rate / 1000.0,
                    setup_cost=0.0,
                    min_charge_applied=False,
                    total_cost=ink_cost,
                ))
            else:
                add_warning("warning", "MISSING_INK_RATE", "Chưa cấu hình đơn giá mực (vật tư nhóm Mực, giá đ/1.000 lượt) — chi phí mực chưa được tính.")

        # 10. Machine Operating Cost Line
        if machine and machine_rate:
            # Kiểm tra khổ tờ in vs khả năng máy (spec §6A) — chỉ khi máy có khai khổ.
            try:
                if sheet_w and sheet_h:
                    _sw, _sh = float(sheet_w), float(sheet_h)
                    _mxw, _mxh = getattr(machine, "max_width_cm", None), getattr(machine, "max_height_cm", None)
                    if _mxw and _mxh and (_sw > float(_mxw) or _sh > float(_mxh)):
                        add_warning("warning", "SHEET_EXCEEDS_MACHINE",
                                    f"Khổ tờ in {_sw:g}×{_sh:g}cm vượt khổ giấy tối đa của máy {machine.name} ({float(_mxw):g}×{float(_mxh):g}cm) — máy có thể không chạy được.",
                                    "machine", machine.id)
                    _mnw, _mnh = getattr(machine, "min_width_cm", None), getattr(machine, "min_height_cm", None)
                    if _mnw and _mnh and (_sw < float(_mnw) or _sh < float(_mnh)):
                        add_warning("warning", "SHEET_BELOW_MACHINE_MIN",
                                    f"Khổ tờ in {_sw:g}×{_sh:g}cm nhỏ hơn khổ tối thiểu của máy {machine.name}.",
                                    "machine", machine.id)
            except (ValueError, TypeError):
                pass

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

            # Setup/canh máy (giờ) — công thức hạt theo DM Máy (spec §D): base + theo màu + theo mặt
            # + vệ sinh + đổi màu×màu + đổi kẽm×số bản + canh màu. Nếu chưa khai (tổng = 0) → FALLBACK
            # về (setup_time_mins + changeover_time_mins)/60 = đúng hành vi cũ (không đổi kết quả job cũ).
            plates_for_setup = int(round(colors * plate_set_factor * forms))
            setup_gran = (
                float(getattr(machine, "setup_time_base_hour", 0) or 0)
                + float(getattr(machine, "setup_time_per_color_hour", 0) or 0) * colors
                + float(getattr(machine, "setup_time_per_side_hour", 0) or 0) * sides
                + float(getattr(machine, "cleaning_time_hour", 0) or 0)
                + float(getattr(machine, "color_change_time_hour", 0) or 0) * colors
                + float(getattr(machine, "plate_change_time_per_plate_hour", 0) or 0) * plates_for_setup
                + float(getattr(machine, "color_check_time_hour", 0) or 0)
            )
            if setup_gran > 0:
                setup_hours = setup_gran
                _mn = float(getattr(machine, "min_setup_time_hour", 0) or 0)
                _mx = getattr(machine, "max_setup_time_hour", None)
                if _mn and setup_hours < _mn:
                    setup_hours = _mn
                if _mx is not None and setup_hours > float(_mx):
                    setup_hours = float(_mx)
            else:
                setup_hours = float(machine.setup_time_mins + machine.changeover_time_mins) / 60.0

            machine_hours = run_time_hours + setup_hours
            # Làm tròn giờ máy theo chính sách máy (none = không làm tròn = hành vi cũ).
            _round_policy = str(getattr(machine, "rounding_hour_policy", "none") or "none")
            if _round_policy in ("0.01", "0.25", "0.5"):
                _step = float(_round_policy)
                machine_hours = math.ceil(machine_hours / _step) * _step

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

            # Lượng tính giá của công đoạn (dùng cho cả nội bộ lẫn thuê ngoài).
            qty_at_op = qty
            for snap in reverse_snaps:
                if snap["operation_type"] == op.operation_type:
                    qty_at_op = snap["qty_before"]
                    break
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

            # Format vi-VN: chấm ngăn nghìn, phẩy thập phân (331.0 → "331", 1666.67 → "1.666,67")
            if float(qty_val).is_integer():
                qty_disp = f"{int(qty_val):,}".replace(",", ".")
            else:
                qty_disp = f"{qty_val:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")

            if exec_mode == "internal" and op_rate:
                run_rate = float(op_rate.run_rate)
                labor_rate = float(op_rate.labor_rate or 0)
                setup_fee = float(op_rate.setup_fee or 0)
                hourly_rate = float(getattr(op_rate, "hourly_rate", 0) or 0)

                # Giờ máy = setup + chạy (spec §C, dùng cho per_hour/combined & nhân công theo giờ).
                speed = float(op_rate.speed or 0)
                setup_h = float(op_rate.setup_time_mins or 0) / 60.0
                run_h = (qty_val / speed) if speed > 0 else 0.0
                machine_h = setup_h + run_h

                # --- Chi phí máy/sản lượng theo internal_pricing_method (spec §C) ---
                method = op.internal_pricing_method or "per_qty"
                if method == "per_hour":
                    # Chi phí = (setup_time + lượng/tốc độ) × đơn giá giờ máy
                    run_cost = machine_h * hourly_rate
                    setup_component = 0.0
                elif method == "combined":
                    # Chi phí = setup_fee + giờ máy × đơn giá giờ máy + lượng × đơn giá
                    run_cost = qty_val * run_rate + machine_h * hourly_rate
                    setup_component = setup_fee
                else:  # per_qty (MẶC ĐỊNH — công thức cũ, giữ nguyên số cho quote đang chạy)
                    run_cost = qty_val * run_rate
                    setup_component = setup_fee

                # --- Nhân công đa hình thức (spec §D) ---
                lp = op.pricing_method or "theo_sp"
                people = float(op.labor_people_count or 1)
                if lp == "none":
                    labor_cost = 0.0
                elif lp == "theo_gio":
                    labor_cost = people * machine_h * labor_rate
                elif lp == "theo_ca":
                    labor_cost = float(getattr(op_rate, "labor_shift_rate", 0) or 0)
                elif lp == "khoan":
                    labor_cost = float(getattr(op_rate, "labor_fixed", 0) or 0)
                else:  # theo_sp (MẶC ĐỊNH — công thức cũ)
                    labor_cost = qty_val * labor_rate
                labor_min = float(getattr(op_rate, "labor_min", 0) or 0)
                if lp != "none" and labor_cost < labor_min:
                    labor_cost = labor_min

                # --- Khuôn (spec §F) — giá từ DM Đơn giá kẽm & khuôn (#5) qua op.tooling_rate_id;
                #     fallback tooling_unit_price cũ trên OperationRate nếu chưa link (job cũ giữ số).
                tooling_cost = 0.0
                tooling_die = None
                if getattr(op, "has_tooling", False):
                    _rate_id = getattr(op, "tooling_rate_id", None)
                    _die = self.db.get(PlateDieRate, _rate_id) if _rate_id else None
                    if _die is not None:
                        _method = _die.pricing_method or "fixed"
                        if op_spec.get("tooling_reuse") and _die.reusable:
                            _rm = _die.reuse_price_method or "zero"
                            tooling_cost = (
                                0.0 if _rm == "zero"
                                else float(_die.maintenance_fee or 0) if _rm == "maintenance_fee"
                                else float(op_spec.get("tooling_manual_price") or 0)
                            )
                        else:
                            if _method == "area":
                                tooling_cost = float(op_spec.get("tooling_area_cm2") or 0) * float(_die.unit_price_area or 0)
                            elif _method == "perimeter":
                                tooling_cost = float(op_spec.get("tooling_perimeter_m") or 0) * float(_die.unit_price_perimeter or 0)
                            elif _method == "manual":
                                tooling_cost = float(op_spec.get("tooling_manual_price") or 0)
                            else:  # fixed / size_tier (MVP dùng đơn giá cố định)
                                tooling_cost = float(_die.unit_price or 0)
                            _minc = float(_die.min_charge or 0)
                            if tooling_cost < _minc:
                                tooling_cost = _minc
                            if _die.max_charge is not None and tooling_cost > float(_die.max_charge):
                                tooling_cost = float(_die.max_charge)
                        tooling_die = _die
                    elif getattr(op_rate, "tooling_unit_price", 0):
                        tooling_cost = float(op_rate.tooling_unit_price)

                op_cost = run_cost + setup_component + labor_cost + tooling_cost

                min_charge_applied = False
                min_charge = float(op_rate.min_charge or 0)
                if op_cost < min_charge:
                    op_cost = min_charge
                    min_charge_applied = True

                category = "packing" if op.operation_type == "dong_goi" else "operation"

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
                        "min_charge": op_rate.min_charge,
                        "hourly_rate": getattr(op_rate, "hourly_rate", 0),
                        "internal_pricing_method": method,
                        "labor_pricing_method": lp,
                        "tooling_unit_price": getattr(op_rate, "tooling_unit_price", 0),
                        "tooling_rate_id": getattr(op, "tooling_rate_id", None),
                        "tooling_rate_code": tooling_die.code if tooling_die else None,
                        "tooling_pricing_method": tooling_die.pricing_method if tooling_die else None,
                    },
                    calculation_snapshot_json={
                        "qty_at_op": qty_at_op,
                        "pieces_per_sheet": pieces_per_sheet,
                        "machine_hours": machine_h,
                        "run_cost": run_cost,
                        "labor_cost": labor_cost,
                        "setup_fee": setup_component,
                        "tooling_cost": tooling_cost,
                    },
                    quantity=qty_val,
                    unit=op_unit,
                    unit_cost=run_rate + labor_rate,
                    setup_cost=setup_component,
                    min_charge_applied=min_charge_applied,
                    total_cost=op_cost
                ))

            elif exec_mode == "outsourced":
                # Thuê ngoài (spec §E). Ưu tiên chi phí nhập tay ở màn tính giá; nếu không có thì
                # lấy bảng giá NCC từ biểu giá công đoạn: max(lượng × đơn giá, min charge) + setup + vận chuyển.
                manual_cost = float(op_spec.get("outsource_cost", 0.0))
                src_type = "input_spec"
                src_id = None
                src_snap = None
                calc_snap = None
                unit_disp = "lo"
                out_qty = 1.0

                if manual_cost > 0:
                    outsource_cost = manual_cost
                elif op_rate and (op_rate.outsource_unit_price or op_rate.outsource_min_charge):
                    up = float(op_rate.outsource_unit_price or 0)
                    setup = float(op_rate.outsource_setup_fee or 0)
                    minc = float(op_rate.outsource_min_charge or 0)
                    transport = float(op_rate.outsource_transport_fee or 0)
                    base = max(qty_val * up, minc)
                    outsource_cost = base + setup + transport
                    src_type = "operation_rates"
                    src_id = op_rate.id
                    src_snap = {
                        "rate_id": op_rate.id,
                        "outsource_supplier": op_rate.outsource_supplier,
                        "outsource_unit_price": op_rate.outsource_unit_price,
                        "outsource_setup_fee": op_rate.outsource_setup_fee,
                        "outsource_min_charge": op_rate.outsource_min_charge,
                        "outsource_transport_fee": op_rate.outsource_transport_fee,
                    }
                    calc_snap = {"qty_at_op": qty_at_op, "base": base, "setup": setup, "transport": transport}
                    unit_disp = op_unit
                    out_qty = qty_val
                    if op_rate.outsource_moq and qty_val < float(op_rate.outsource_moq):
                        add_warning("warning", "OUTSOURCE_BELOW_MOQ", f"Công đoạn {op.name}: lượng {qty_disp} dưới MOQ {op_rate.outsource_moq} của NCC.", "operation", op.id)
                else:
                    outsource_cost = 0.0
                    add_warning("warning", "MISSING_OUTSOURCE_PRICE", f"Công đoạn {op.name} thuê ngoài chưa nhập chi phí.", "operation", op.id)

                cost_lines.append(EstimateCostLine(
                    category="outsource",
                    description=f"Thuê ngoài {op.name}",
                    source_type=src_type,
                    source_id=src_id,
                    source_snapshot_json=src_snap,
                    calculation_snapshot_json=calc_snap,
                    quantity=out_qty,
                    unit=unit_disp,
                    unit_cost=float(op_rate.outsource_unit_price) if (src_type == "operation_rates" and op_rate) else outsource_cost,
                    setup_cost=float(op_rate.outsource_setup_fee or 0) if src_type == "operation_rates" else 0.0,
                    min_charge_applied=False,
                    total_cost=outsource_cost
                ))

        # 11b. Override thủ công tổng tiền từng dòng (§12) — kèm LÝ DO bắt buộc. Đọc từ
        # input_spec["overrides"] = [{target:"line:<category>", value:<số>, reason:<str>}]. Áp SAU
        # khi engine tính; lưu giá gốc + lý do vào snapshot dòng (được đóng băng qua input_spec_json).
        for ov in (input_spec.get("overrides") or []):
            try:
                target = str(ov.get("target") or "")
                if not target.startswith("line:"):
                    continue
                cat = target.split(":", 1)[1]
                reason = (ov.get("reason") or "").strip()
                new_val = float(ov.get("value"))
                if not reason:
                    add_warning("blocking_error", "OVERRIDE_NO_REASON",
                                f"Sửa tay dòng '{cat}' phải nhập lý do.")
                    continue
                if new_val < 0:
                    add_warning("blocking_error", "OVERRIDE_NEGATIVE", f"Giá sửa tay dòng '{cat}' không được âm.")
                    continue
                line = next((l for l in cost_lines if l.category == cat), None)
                if line is None:
                    add_warning("warning", "OVERRIDE_NO_LINE", f"Không có dòng '{cat}' để sửa tay.")
                    continue
                orig = float(line.total_cost)
                line.total_cost = new_val
                line.min_charge_applied = False
                line.note = f"[SỬA TAY] {orig:,.0f}→{new_val:,.0f}đ · Lý do: {reason}"
                snap = dict(line.calculation_snapshot_json or {})
                snap.update({"override_original": orig, "override_value": new_val, "override_reason": reason})
                line.calculation_snapshot_json = snap
                add_warning("info", "OVERRIDE_APPLIED",
                            f"Dòng '{cat}' sửa tay: {orig:,.0f}→{new_val:,.0f}đ (lý do: {reason}).")
            except (ValueError, TypeError):
                add_warning("warning", "OVERRIDE_INVALID", "Một mục sửa tay không hợp lệ đã bị bỏ qua.")

        # 12. Accumulate Cost
        total_cost = sum(float(line.total_cost) for line in cost_lines)

        return cost_lines, total_cost, warnings
