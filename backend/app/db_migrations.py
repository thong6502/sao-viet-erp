"""Lightweight, idempotent schema migrations for the create_all-based DB.

Why this exists: the app builds its schema with ``Base.metadata.create_all`` at startup
(see :func:`app.db.init_db`). ``create_all`` creates MISSING tables but never ALTERs an
existing one. Production keeps a persistent Postgres volume (deploy does ``git reset`` +
``docker compose up`` and does NOT wipe ``pgdata`` — see docs/DEPLOY.md), so a new column
added to a model would be absent on the live DB and every query touching the table 500s.

This runner applies ordered, tracked, idempotent DDL steps AFTER create_all so an existing
DB is patched forward without adopting Alembic. Each step inspects the live schema before
issuing DDL, so it is a no-op on a fresh DB (tests / new installs) where create_all already
produced the current shape. Applied step ids are recorded in ``schema_migrations`` so each
runs at most once per DB.

Add a new migration by appending ``(id, fn)`` to :data:`MIGRATIONS` — never edit an id that
has shipped.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


def _existing_columns(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def _migrate_operation_full_fields(db: Session) -> None:
    """Add spec §A–§G columns to operations + operation_rates (Công đoạn & Đơn giá gia công).

    Defaults are chosen so an existing DB reproduces today's costing exactly:
    internal_pricing_method='per_qty' and pricing_method (labor) keeps its stored value —
    the engine's per_qty/theo_sp branches are byte-for-byte the old formula. No-op on a fresh
    create_all DB (tests / new installs) where the model already built these columns.
    """
    bind = db.get_bind()
    insp = inspect(bind)
    names = insp.get_table_names()

    op_cols = [
        ("process_group", "VARCHAR(20) NOT NULL DEFAULT 'sau_in'"),
        ("process_type", "VARCHAR(16) NOT NULL DEFAULT 'internal'"),
        ("default_sequence", "INTEGER NOT NULL DEFAULT 0"),
        ("quantity_formula_type", "VARCHAR(20) NOT NULL DEFAULT 'print_sheet_qty'"),
        ("allow_manual_quantity", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("internal_pricing_method", "VARCHAR(16) NOT NULL DEFAULT 'per_qty'"),
        ("labor_people_count", "NUMERIC(6,2) NOT NULL DEFAULT 1"),
        ("has_tooling", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("tooling_type", "VARCHAR(20)"),
        ("has_yield_loss", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("default_yield_rate", "NUMERIC(6,2)"),
        ("default_yield_rule", "VARCHAR(40)"),
    ]
    rate_cols = [
        ("hourly_rate", "BIGINT NOT NULL DEFAULT 0"),
        ("labor_shift_rate", "BIGINT NOT NULL DEFAULT 0"),
        ("labor_fixed", "BIGINT NOT NULL DEFAULT 0"),
        ("labor_min", "BIGINT NOT NULL DEFAULT 0"),
        ("tooling_unit_price", "BIGINT NOT NULL DEFAULT 0"),
        ("outsource_supplier", "VARCHAR(255)"),
        ("outsource_unit_price", "BIGINT NOT NULL DEFAULT 0"),
        ("outsource_setup_fee", "BIGINT NOT NULL DEFAULT 0"),
        ("outsource_min_charge", "BIGINT NOT NULL DEFAULT 0"),
        ("outsource_transport_fee", "BIGINT NOT NULL DEFAULT 0"),
        ("outsource_moq", "BIGINT NOT NULL DEFAULT 0"),
        ("outsource_lead_time_days", "INTEGER NOT NULL DEFAULT 0"),
    ]

    if "operations" in names:
        existing = _existing_columns(insp, "operations")
        # A legacy operations table predates the new fields — detect via internal_pricing_method.
        legacy_table = "internal_pricing_method" not in existing
        added_process_type = False
        for name, ddl in op_cols:
            if name not in existing:
                db.execute(text(f"ALTER TABLE operations ADD COLUMN {name} {ddl}"))
                if name == "process_type":
                    added_process_type = True
        # Backfill process_type from the pre-existing allow_outsource flag so old rows keep meaning.
        if added_process_type and "allow_outsource" in existing:
            db.execute(text(
                "UPDATE operations SET process_type = "
                "CASE WHEN allow_outsource THEN 'both' ELSE 'internal' END"
            ))
        # Behavior-preserving normalization: the OLD engine always computed labor as qty×labor_rate
        # regardless of the (then-dead) pricing_method value. The NEW engine honors pricing_method,
        # so force legacy rows to 'theo_sp' — the branch that reproduces the old number exactly.
        # Guarded to legacy tables only, so a fresh create_all DB (tests) is untouched.
        if legacy_table:
            db.execute(text("UPDATE operations SET pricing_method = 'theo_sp'"))

    if "operation_rates" in names:
        existing = _existing_columns(insp, "operation_rates")
        for name, ddl in rate_cols:
            if name not in existing:
                db.execute(text(f"ALTER TABLE operation_rates ADD COLUMN {name} {ddl}"))

    db.commit()


def _migrate_norms_waste_groups(db: Session) -> None:
    """Tái thiết kế danh mục #7 (Định mức & Bù hao): thêm cột nhóm/cách-tính/field theo nhóm.

    Backfill `waste_group` từ `norm_key` cũ và GỘP `waste_pct_of_operation` (hao công đoạn) →
    `yield_rate` với value = 1 − hao (quyết định #1). Default chọn sao cho DB cũ giữ đúng hành vi:
    rule chưa khai field mới ⇒ makeready/running/paper = 0 phần thêm. No-op trên DB fresh
    (create_all đã dựng cột). Xem docs/DINH_MUC_BU_HAO.md.
    """
    bind = db.get_bind()
    insp = inspect(bind)
    if "norms" not in insp.get_table_names():
        return

    coldefs = [
        ("code", "VARCHAR(64)"),
        ("name", "VARCHAR(200)"),
        ("waste_group", "VARCHAR(24)"),
        ("calculation_method", "VARCHAR(24)"),
        ("applicable_product_types", "JSON"),
        ("applicable_machine_ids", "JSON"),
        ("setup_waste_qty", "NUMERIC(12,3)"),
        ("setup_waste_per_color", "NUMERIC(12,3)"),
        ("setup_waste_per_side", "NUMERIC(12,3)"),
        ("min_waste_qty", "NUMERIC(12,3)"),
        ("max_waste_qty", "NUMERIC(12,3)"),
        ("paper_add_to_purchase", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ("priority", "INTEGER NOT NULL DEFAULT 100"),
        ("version", "INTEGER NOT NULL DEFAULT 1"),
        ("used_count", "INTEGER NOT NULL DEFAULT 0"),
        ("created_by", "INTEGER"),
        ("updated_by", "INTEGER"),
    ]
    existing = _existing_columns(insp, "norms")
    added_waste_group = False
    for name, ddl in coldefs:
        if name not in existing:
            db.execute(text(f"ALTER TABLE norms ADD COLUMN {name} {ddl}"))
            if name == "waste_group":
                added_waste_group = True

    if added_waste_group:
        # Gộp hao công đoạn → tỷ lệ đạt (value = 1 − hao), rồi đổi norm_key sang yield_rate.
        db.execute(text(
            "UPDATE norms SET value = 1 - value "
            "WHERE norm_key = 'waste_pct_of_operation'"
        ))
        db.execute(text(
            "UPDATE norms SET norm_key = 'yield_rate' "
            "WHERE norm_key = 'waste_pct_of_operation'"
        ))
        # Backfill waste_group từ norm_key.
        mapping = {
            "yield_rate": "YIELD_RATE",
            "makeready_per_color_side": "SETUP_WASTE",
            "running_waste_pct": "RUNNING_WASTE",
            "paper_extra_waste": "PAPER_EXTRA_WASTE",
        }
        for key, group in mapping.items():
            db.execute(
                text("UPDATE norms SET waste_group = :g WHERE norm_key = :k AND waste_group IS NULL"),
                {"g": group, "k": key},
            )
        # Cách tính mặc định cho rule legacy (giữ đúng công thức cũ).
        db.execute(text(
            "UPDATE norms SET calculation_method = 'PER_COLOR_SIDE' "
            "WHERE norm_key = 'makeready_per_color_side' AND calculation_method IS NULL"
        ))
        db.execute(text(
            "UPDATE norms SET calculation_method = 'PERCENT' "
            "WHERE norm_key IN ('yield_rate','running_waste_pct') AND calculation_method IS NULL"
        ))

    db.commit()


def _migrate_paper_size_full_fields(db: Session) -> None:
    """Khổ giấy tiêu chuẩn — full spec A–E: thêm nhóm khổ, 3 boolean loại khổ, xoay, máy JSON,
    quan hệ khổ cắt, versioning; swap unique(code) → unique(code, version). Đồng thời thêm 2 cột
    liên kết paper_sizes vào costing_paper_options (print_sheet_size_id / purchase_size_id).

    Default chọn sao cho DB cũ giữ đúng ý nghĩa: is_print_sheet_size mặc định TRUE, backfill từ
    `size_type` cũ ('mua' → khổ mua, 'in' → khổ tờ in). No-op trên DB fresh (create_all đã dựng cột).
    """
    bind = db.get_bind()
    insp = inspect(bind)
    names = insp.get_table_names()
    dialect = bind.dialect.name

    if "paper_sizes" in names:
        coldefs = [
            ("size_group", "VARCHAR(20) NOT NULL DEFAULT 'custom'"),
            ("is_purchase_size", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("is_print_sheet_size", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("is_cut_size", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("allow_rotation", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("compatible_machine_ids", "JSON"),
            ("default_machine_id", "INTEGER"),
            ("parent_size_id", "INTEGER"),
            ("cut_count", "INTEGER"),
            ("cut_waste_rate", "NUMERIC(5,2)"),
            ("version", "INTEGER NOT NULL DEFAULT 1"),
            ("effective_from", "DATE"),
            ("effective_to", "DATE"),
            ("used_count", "INTEGER NOT NULL DEFAULT 0"),
            ("created_by", "INTEGER"),
            ("updated_by", "INTEGER"),
        ]
        existing = _existing_columns(insp, "paper_sizes")
        added_booleans = False
        for name, ddl in coldefs:
            if name not in existing:
                db.execute(text(f"ALTER TABLE paper_sizes ADD COLUMN {name} {ddl}"))
                if name == "is_purchase_size":
                    added_booleans = True
        db.commit()
        # Backfill loại khổ booleans từ size_type cũ ('mua'/'in'). Commit ngay để DML không bị
        # mất bởi các câu DDL (ADD COLUMN / index) chạy sau — pysqlite auto-commit/rollback quanh
        # DDL có thể desync transaction của Session nếu trộn DML+DDL rồi commit một lần.
        if added_booleans and "size_type" in existing:
            db.execute(text("UPDATE paper_sizes SET is_purchase_size = TRUE WHERE size_type = 'mua'"))
            db.execute(text("UPDATE paper_sizes SET is_print_sheet_size = FALSE WHERE size_type = 'mua'"))
            db.execute(text("UPDATE paper_sizes SET is_print_sheet_size = TRUE WHERE size_type = 'in'"))
            db.commit()

        # Swap unique(code) → unique(code, version) — version-chain giá khổ giấy.
        if dialect == "postgresql":
            db.execute(text("ALTER TABLE paper_sizes DROP CONSTRAINT IF EXISTS paper_sizes_code_key"))
        db.execute(text("DROP INDEX IF EXISTS ix_paper_sizes_code"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_paper_sizes_code ON paper_sizes (code)"))
        db.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_size_code_version "
            "ON paper_sizes (code, version)"
        ))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_paper_sizes_size_group ON paper_sizes (size_group)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_paper_sizes_parent_size_id ON paper_sizes (parent_size_id)"))

    if "costing_paper_options" in names:
        existing = _existing_columns(insp, "costing_paper_options")
        for name in ("print_sheet_size_id", "purchase_size_id"):
            if name not in existing:
                db.execute(text(f"ALTER TABLE costing_paper_options ADD COLUMN {name} INTEGER"))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_costing_paper_options_print_sheet_size_id "
            "ON costing_paper_options (print_sheet_size_id)"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_costing_paper_options_purchase_size_id "
            "ON costing_paper_options (purchase_size_id)"
        ))

    db.commit()


def _migrate_machine_full_fields(db: Session) -> None:
    """Add spec A–G columns to machines + breakdown to machine_rates (Máy móc & Đơn giá giờ máy).

    Defaults reproduce today's costing exactly: setup_time_*_hour = 0 so the engine falls back to
    the legacy (setup_time_mins + changeover_time_mins)/60, rounding_hour_policy='none' = no
    rounding. No-op on a fresh create_all DB where the model already built these columns.
    """
    bind = db.get_bind()
    insp = inspect(bind)
    names = insp.get_table_names()

    machine_cols = [
        ("machine_group", "VARCHAR(20) NOT NULL DEFAULT 'may_in'"),
        ("status", "VARCHAR(16) NOT NULL DEFAULT 'active'"),
        ("note", "TEXT"),
        ("max_print_width_cm", "NUMERIC(10,2)"),
        ("max_print_height_cm", "NUMERIC(10,2)"),
        ("gripper_cm", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
        ("side_margin_cm", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
        ("top_bottom_margin_cm", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
        ("compatible_paper_size_ids", "JSON"),
        ("min_speed", "NUMERIC(10,2)"),
        ("max_speed", "NUMERIC(10,2)"),
        ("setup_time_base_hour", "NUMERIC(8,3) NOT NULL DEFAULT 0"),
        ("setup_time_per_color_hour", "NUMERIC(8,3) NOT NULL DEFAULT 0"),
        ("setup_time_per_side_hour", "NUMERIC(8,3) NOT NULL DEFAULT 0"),
        ("cleaning_time_hour", "NUMERIC(8,3) NOT NULL DEFAULT 0"),
        ("color_change_time_hour", "NUMERIC(8,3) NOT NULL DEFAULT 0"),
        ("plate_change_time_per_plate_hour", "NUMERIC(8,3) NOT NULL DEFAULT 0"),
        ("color_check_time_hour", "NUMERIC(8,3) NOT NULL DEFAULT 0"),
        ("min_setup_time_hour", "NUMERIC(8,3) NOT NULL DEFAULT 0"),
        ("max_setup_time_hour", "NUMERIC(8,3)"),
        ("rounding_hour_policy", "VARCHAR(8) NOT NULL DEFAULT 'none'"),
        ("overhead_included", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ("operator_included", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ("used_count", "INTEGER NOT NULL DEFAULT 0"),
        ("created_by", "INTEGER"),
        ("updated_by", "INTEGER"),
    ]
    rate_cols = [
        ("rate_depreciation", "BIGINT NOT NULL DEFAULT 0"),
        ("rate_energy", "BIGINT NOT NULL DEFAULT 0"),
        ("rate_maintenance", "BIGINT NOT NULL DEFAULT 0"),
        ("rate_labor", "BIGINT NOT NULL DEFAULT 0"),
        ("rate_overhead", "BIGINT NOT NULL DEFAULT 0"),
    ]

    if "machines" in names:
        existing = _existing_columns(insp, "machines")
        added_status = False
        for name, ddl in machine_cols:
            if name not in existing:
                db.execute(text(f"ALTER TABLE machines ADD COLUMN {name} {ddl}"))
                if name == "status":
                    added_status = True
        # Backfill status from the pre-existing is_active flag.
        if added_status and "is_active" in existing:
            db.execute(text(
                "UPDATE machines SET status = CASE WHEN is_active THEN 'active' ELSE 'inactive' END"
            ))

    if "machine_rates" in names:
        existing = _existing_columns(insp, "machine_rates")
        for name, ddl in rate_cols:
            if name not in existing:
                db.execute(text(f"ALTER TABLE machine_rates ADD COLUMN {name} {ddl}"))

    db.commit()


# Ordered list of (id, fn). Ids are immutable once shipped.
def _migrate_product_type_full_fields(db: Session) -> None:
    """Loại sản phẩm & Quy tắc tính (page #1) — full spec §A–§H: nhóm/công nghệ/mô tả/version,
    input shown/required, quy tắc kích thước (bleed/gutter/trim/xoay/custom), số trang/tay,
    vật tư mặc định (ID), routing required/extra, cờ tính (sheet/ink mode,
    tooling, packaging, override).

    Default chọn sao cho DB cũ giữ đúng hành vi (engine chưa đọc config này → thêm cột là no-op
    về số). Backfill shown_fields = required_fields cũ (nếu chưa khai). No-op trên DB fresh.
    Tách commit sau backfill DML khỏi DDL (gotcha pysqlite — xem migration 0004).
    """
    bind = db.get_bind()
    insp = inspect(bind)
    if "product_types_catalog" not in insp.get_table_names():
        return

    coldefs = [
        ("product_group", "VARCHAR(24) NOT NULL DEFAULT 'an_pham'"),
        ("technology", "VARCHAR(20) NOT NULL DEFAULT 'offset'"),
        ("description", "TEXT"),
        ("display_order", "INTEGER NOT NULL DEFAULT 100"),
        ("version", "INTEGER NOT NULL DEFAULT 1"),
        ("effective_from", "DATE"),
        ("effective_to", "DATE"),
        ("used_count", "INTEGER NOT NULL DEFAULT 0"),
        ("shown_fields", "JSON"),
        ("dimension_rule_type", "VARCHAR(16) NOT NULL DEFAULT 'finished'"),
        ("default_bleed_mm", "NUMERIC(6,2) NOT NULL DEFAULT 0"),
        ("default_gutter_mm", "NUMERIC(6,2) NOT NULL DEFAULT 0"),
        ("default_trim_mm", "NUMERIC(6,2) NOT NULL DEFAULT 0"),
        ("allow_rotation", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ("allow_custom_size", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ("has_page_count", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("page_multiple", "INTEGER NOT NULL DEFAULT 0"),
        ("pages_per_signature", "INTEGER NOT NULL DEFAULT 0"),
        ("has_cover_body_split", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("default_paper_material_id", "INTEGER"),
        ("default_cover_material_id", "INTEGER"),
        ("default_body_material_id", "INTEGER"),
        ("default_ink_material_id", "INTEGER"),
        ("has_packaging", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("default_pack_qty", "INTEGER NOT NULL DEFAULT 0"),
        ("required_operations", "JSON"),
        ("allow_extra_operations", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ("sheet_count_mode", "VARCHAR(16) NOT NULL DEFAULT 'by_pieces'"),
        ("ink_cost_mode", "VARCHAR(20) NOT NULL DEFAULT 'per_1000'"),
        ("has_tooling", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("default_tooling_type", "VARCHAR(20)"),
        ("allow_manual_override", "BOOLEAN NOT NULL DEFAULT FALSE"),
        # % bù hao (thay cả module Định mức cũ): áp thẳng vào số tờ sản xuất.
        ("waste_pct", "NUMERIC(6,2) NOT NULL DEFAULT 0"),
    ]
    existing = _existing_columns(insp, "product_types_catalog")
    added_shown = False
    for name, ddl in coldefs:
        if name not in existing:
            db.execute(text(f"ALTER TABLE product_types_catalog ADD COLUMN {name} {ddl}"))
            if name == "shown_fields":
                added_shown = True
    db.commit()

    # Backfill: shown_fields = required_fields cũ (loại SP cũ hiển thị đúng những field từng bắt buộc);
    # sheet_count_mode/has_page_count suy từ calculation_strategy. Commit NGAY (tách khỏi DDL — gotcha pysqlite).
    if added_shown:
        db.execute(text(
            "UPDATE product_types_catalog SET shown_fields = required_fields "
            "WHERE shown_fields IS NULL AND required_fields IS NOT NULL"
        ))
        db.execute(text(
            "UPDATE product_types_catalog SET sheet_count_mode = 'by_pages', has_page_count = TRUE "
            "WHERE calculation_strategy IN ('page_based', 'book_based')"
        ))
        db.execute(text(
            "UPDATE product_types_catalog SET dimension_rule_type = 'spread' "
            "WHERE calculation_strategy = 'box_based'"
        ))
        db.commit()

    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_product_types_catalog_group "
        "ON product_types_catalog (product_group)"
    ))
    db.commit()


def _migrate_materials_full_fields(db: Session) -> None:
    """Tái thiết kế danh mục #2 (Vật tư & Đơn giá): thêm nhóm/NCC/UoM/quy đổi/field-theo-nhóm vào
    materials; NCC/khổ/loại-giá/bậc-SL/phí/version vào material_costs; thay unique 'hiện hành' để
    cho phép nhiều bậc/NCC/khổ. Backfill material_group từ material_type. No-op trên DB fresh.
    Xem docs/VAT_TU_DON_GIA.md. (DML commit TRƯỚC DDL — tránh desync pysqlite, như migration 0004.)
    """
    bind = db.get_bind()
    insp = inspect(bind)
    names = insp.get_table_names()

    mat_cols = [
        ("material_group", "VARCHAR(20)"),
        ("default_supplier", "VARCHAR(150)"),
        ("base_uom", "VARCHAR(16)"),
        ("purchase_uom", "VARCHAR(16)"),
        ("consumption_uom", "VARCHAR(16)"),
        ("conversion_method", "VARCHAR(24)"),
        ("conversion_factor", "NUMERIC(12,4)"),
        ("ink_type", "VARCHAR(32)"),
        ("ink_color_system", "VARCHAR(32)"),
        ("ink_color_code", "VARCHAR(32)"),
        ("film_type", "VARCHAR(32)"),
        ("version", "INTEGER NOT NULL DEFAULT 1"),
    ]
    cost_cols = [
        ("supplier", "VARCHAR(150)"),
        ("paper_size_id", "INTEGER"),
        ("price_type", "VARCHAR(20) NOT NULL DEFAULT 'standard'"),
        ("vat_included", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("transport_fee", "BIGINT NOT NULL DEFAULT 0"),
        ("moq", "NUMERIC(12,2) NOT NULL DEFAULT 0"),
        ("lead_time_days", "INTEGER NOT NULL DEFAULT 0"),
        ("quantity_from", "NUMERIC(14,2)"),
        ("quantity_to", "NUMERIC(14,2)"),
        ("version", "INTEGER NOT NULL DEFAULT 1"),
    ]

    added_group = False
    if "materials" in names:
        existing = _existing_columns(insp, "materials")
        for name, ddl in mat_cols:
            if name not in existing:
                db.execute(text(f"ALTER TABLE materials ADD COLUMN {name} {ddl}"))
                if name == "material_group":
                    added_group = True

    if "material_costs" in names:
        existing = _existing_columns(insp, "material_costs")
        for name, ddl in cost_cols:
            if name not in existing:
                db.execute(text(f"ALTER TABLE material_costs ADD COLUMN {name} {ddl}"))
    db.commit()  # đóng đợt ADD COLUMN trước khi chạy DML backfill.

    # Backfill material_group từ material_type (map trong models.material.GROUP_FROM_TYPE).
    if added_group:
        mapping = {
            "paper": "paper", "carton": "paper",
            "lamination": "film", "film": "film",
            "glue": "glue",
            "decal": "auxiliary", "pp": "auxiliary", "canvas": "auxiliary",
            "formex": "auxiliary", "chemical": "auxiliary",
        }
        for mtype, group in mapping.items():
            db.execute(
                text("UPDATE materials SET material_group = :g WHERE material_type = :t AND material_group IS NULL"),
                {"g": group, "t": mtype},
            )
        db.commit()  # commit DML trước DDL index (pysqlite).

    # Thay unique 'hiện hành' (chỉ material+price_unit) → gồm bậc/NCC/khổ.
    if "material_costs" in names:
        db.execute(text("DROP INDEX IF EXISTS uix_material_costs_current"))
        db.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uix_material_costs_current ON material_costs "
            "(material_id, price_unit, coalesce(quantity_from, -1), coalesce(quantity_to, -1), "
            "coalesce(supplier, ''), coalesce(paper_size_id, 0)) WHERE effective_to IS NULL"
        ))
        db.commit()


def _migrate_plate_die_full_fields(db: Session) -> None:
    """Đơn giá kẽm & khuôn (#5) — full spec: Mã/Tên, khổ kẽm, máy áp dụng (JSON), pricing_method
    khuôn (fixed/area/perimeter/size_tier/manual) + đơn giá cm²/mét + trần + dùng lại + NCC +
    used_count; đổi khóa 'bản mở' từ (plate_type,technology,unit) → (code). Thêm
    operations.tooling_rate_id (link công đoạn → bảng giá khuôn). No-op trên DB fresh."""
    bind = db.get_bind()
    insp = inspect(bind)
    names = insp.get_table_names()

    if "plate_die_rates" in names:
        coldefs = [
            ("code", "VARCHAR(40) NOT NULL DEFAULT ''"),
            ("name", "VARCHAR(255) NOT NULL DEFAULT ''"),
            ("plate_kind", "VARCHAR(16)"),
            ("plate_width_mm", "INTEGER"),
            ("plate_height_mm", "INTEGER"),
            ("machine_ids", "JSON"),
            ("paper_size_ids", "JSON"),
            ("pricing_method", "VARCHAR(20) NOT NULL DEFAULT 'fixed'"),
            ("unit_price_area", "BIGINT NOT NULL DEFAULT 0"),
            ("unit_price_perimeter", "BIGINT NOT NULL DEFAULT 0"),
            ("max_charge", "BIGINT"),
            ("allow_manual_price", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("reuse_price_method", "VARCHAR(16)"),
            ("maintenance_fee", "BIGINT NOT NULL DEFAULT 0"),
            ("supplier", "VARCHAR(255)"),
            ("lead_time_days", "INTEGER NOT NULL DEFAULT 0"),
            ("transport_fee", "BIGINT NOT NULL DEFAULT 0"),
            ("moq", "INTEGER NOT NULL DEFAULT 0"),
            ("used_count", "INTEGER NOT NULL DEFAULT 0"),
            ("created_by", "INTEGER"),
            ("updated_by", "INTEGER"),
        ]
        existing = _existing_columns(insp, "plate_die_rates")
        added_code = False
        for name, ddl in coldefs:
            if name not in existing:
                db.execute(text(f"ALTER TABLE plate_die_rates ADD COLUMN {name} {ddl}"))
                if name == "code":
                    added_code = True
        db.commit()
        # Backfill Mã/Tên từ plate_type cho hàng cũ (commit trước, tách khỏi DDL đổi index).
        if added_code:
            db.execute(text("UPDATE plate_die_rates SET code = upper(plate_type) WHERE code = ''"))
            db.execute(text("UPDATE plate_die_rates SET name = plate_type WHERE name = ''"))
            db.commit()
        # Đổi khóa 'bản mở': (plate_type,technology,unit) → (code).
        db.execute(text("DROP INDEX IF EXISTS uix_plate_die_rates_current"))
        db.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uix_plate_die_rates_current "
            "ON plate_die_rates (code) WHERE effective_to IS NULL"
        ))
        db.commit()

    if "operations" in names:
        if "tooling_rate_id" not in _existing_columns(insp, "operations"):
            db.execute(text("ALTER TABLE operations ADD COLUMN tooling_rate_id INTEGER"))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_operations_tooling_rate_id "
            "ON operations (tooling_rate_id)"
        ))
        db.commit()


def _migrate_estimate_lifecycle(db: Session) -> None:
    """Add §9 lifecycle columns to estimates: locked_at, version, parent_id, superseded_by_id.
    Defaults = phiếu chưa khóa, version 1, không có cha/kế thừa — không đổi hành vi cũ."""
    insp = inspect(db.get_bind())
    if "estimates" not in insp.get_table_names():
        return
    cols = [
        ("locked_at", "TIMESTAMP"),
        ("version", "INTEGER NOT NULL DEFAULT 1"),
        ("parent_id", "INTEGER"),
        ("superseded_by_id", "INTEGER"),
    ]
    existing = _existing_columns(insp, "estimates")
    for name, ddl in cols:
        if name not in existing:
            db.execute(text(f"ALTER TABLE estimates ADD COLUMN {name} {ddl}"))
    db.commit()


def _migrate_norms_version_by_code(db: Session) -> None:
    """Định mức & Bù hao: chuyển định danh version từ 'cấu-hình-phạm-vi' sang 'mã' (1 quy tắc = 1 mã).

    Index cũ uix_norms_current khóa một-bản-mở theo (norm_key + scope scalar + context_key), BỎ QUA
    applicable_product_types/_machine_ids → 2 rule chỉ khác multi-select bị coi là cùng cấu hình nên
    âm thầm ghi đè nhau. Thay bằng uix_norms_open_code: mỗi mã chỉ 1 bản đang mở; rule khác mã cùng
    tồn tại. Rule không mã (legacy) không bị ràng (code IS NOT NULL) — vẫn theo lối cũ ở tầng service.
    """
    insp = inspect(db.get_bind())
    if "norms" not in insp.get_table_names():
        return

    # Gỡ ràng buộc một-bản-mở kiểu cũ (theo cấu-hình-phạm-vi).
    db.execute(text("DROP INDEX IF EXISTS uix_norms_current"))

    # Dedupe phòng hờ: nếu có >1 bản đang mở cùng một mã (dữ liệu cũ không được index chặn),
    # giữ bản id lớn nhất, hậu tố mã các bản cũ để index unique dựng được.
    open_coded = db.execute(text(
        "SELECT id, code FROM norms WHERE effective_to IS NULL AND code IS NOT NULL"
    )).all()
    seen: dict[str, int] = {}
    for row_id, code in open_coded:
        keep = seen.get(code)
        if keep is None:
            seen[code] = row_id
        elif row_id > keep:
            db.execute(text("UPDATE norms SET code = :c WHERE id = :i"), {"c": f"{code}-dup{keep}", "i": keep})
            seen[code] = row_id
        else:
            db.execute(text("UPDATE norms SET code = :c WHERE id = :i"), {"c": f"{code}-dup{row_id}", "i": row_id})

    db.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uix_norms_open_code ON norms (code) "
        "WHERE effective_to IS NULL AND code IS NOT NULL"
    ))
    db.commit()


def _migrate_employee_default_shift(db: Session) -> None:
    """Ca kíp: thêm cột `employees.default_shift_id` (ca làm việc mặc định của NV) — logical
    link tới work_shifts, nullable Integer (không FK cứng). No-op trên DB fresh (create_all đã
    dựng cột) hoặc khi bảng employees chưa tồn tại."""
    insp = inspect(db.get_bind())
    if "employees" not in insp.get_table_names():
        return
    if "default_shift_id" not in _existing_columns(insp, "employees"):
        db.execute(text("ALTER TABLE employees ADD COLUMN default_shift_id INTEGER"))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_employees_default_shift_id ON employees (default_shift_id)"
        ))
    db.commit()


def _migrate_employee_payroll_fields(db: Session) -> None:
    """Lương: thêm `employees.payroll_group` + `pay_grade_key` (trục tra bảng chính sách
    mức lương). Nullable String. No-op trên DB fresh (create_all đã dựng) / bảng chưa có."""
    insp = inspect(db.get_bind())
    if "employees" not in insp.get_table_names():
        return
    existing = _existing_columns(insp, "employees")
    if "payroll_group" not in existing:
        db.execute(text("ALTER TABLE employees ADD COLUMN payroll_group VARCHAR(40)"))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_employees_payroll_group ON employees (payroll_group)"
        ))
    if "pay_grade_key" not in existing:
        db.execute(text("ALTER TABLE employees ADD COLUMN pay_grade_key VARCHAR(20)"))
    db.commit()


def _migrate_payroll_line_khoan(db: Session) -> None:
    """Lương khoán (nhịp 2): thêm cột `payroll_lines.khoan` (tiền khoán cộng vào gross).
    No-op trên DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    if "payroll_lines" not in insp.get_table_names():
        return
    if "khoan" not in _existing_columns(insp, "payroll_lines"):
        db.execute(text("ALTER TABLE payroll_lines ADD COLUMN khoan NUMERIC(14,2) NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_role_permission_view_salary(db: Session) -> None:
    """Phân quyền: thêm cột `role_permissions.can_view_salary` (xem dữ liệu nhạy cảm hồ sơ:
    lương/BHXH). No-op trên DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    if "can_view_salary" not in _existing_columns(insp, "role_permissions"):
        db.execute(text("ALTER TABLE role_permissions ADD COLUMN can_view_salary BOOLEAN NOT NULL DEFAULT FALSE"))
    db.commit()


def _migrate_role_permission_adjust(db: Session) -> None:
    """Phân quyền: thêm cột `role_permissions.can_adjust` (Chấm công: điều chỉnh công qua
    punch nguồn). No-op trên DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    if "can_adjust" not in _existing_columns(insp, "role_permissions"):
        db.execute(text("ALTER TABLE role_permissions ADD COLUMN can_adjust BOOLEAN NOT NULL DEFAULT FALSE"))
    db.commit()


def _migrate_attendance_adjust_cols(db: Session) -> None:
    """Chấm công: thêm cột đánh dấu PUNCH điều chỉnh tay vào `attendance_logs`
    (is_manual / adjust_reason / fault_party / created_by_user_id). No-op nếu bảng chưa có."""
    insp = inspect(db.get_bind())
    if "attendance_logs" not in insp.get_table_names():
        return
    existing = _existing_columns(insp, "attendance_logs")
    if "is_manual" not in existing:
        db.execute(text("ALTER TABLE attendance_logs ADD COLUMN is_manual BOOLEAN NOT NULL DEFAULT FALSE"))
    if "adjust_reason" not in existing:
        db.execute(text("ALTER TABLE attendance_logs ADD COLUMN adjust_reason VARCHAR(500)"))
    if "fault_party" not in existing:
        db.execute(text("ALTER TABLE attendance_logs ADD COLUMN fault_party VARCHAR(20)"))
    if "created_by_user_id" not in existing:
        db.execute(text("ALTER TABLE attendance_logs ADD COLUMN created_by_user_id INTEGER"))
    db.commit()


def _migrate_leave_seen_by_employee(db: Session) -> None:
    """Nghỉ phép — chuông Topbar: thêm `leave_requests.seen_by_employee_at` (thời điểm NV xem
    kết quả duyệt/từ chối). Nullable timestamp. No-op trên DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    if "leave_requests" not in insp.get_table_names():
        return
    if "seen_by_employee_at" not in _existing_columns(insp, "leave_requests"):
        db.execute(text("ALTER TABLE leave_requests ADD COLUMN seen_by_employee_at TIMESTAMP"))
    db.commit()


def _migrate_product_type_waste_pct(db: Session) -> None:
    """Loại SP: thêm `product_types_catalog.waste_pct` (% bù hao, thay module Định mức cũ).
    PR #7 lỡ gắn cột này vào coldefs của migration 0006 — vốn đã chạy trên DB cũ nên không
    được ALTER lại → thiếu cột. Tách migration id RIÊNG để bù cho mọi DB hiện có (bài học:
    cột mới luôn phải là migration mới). No-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "product_types_catalog" not in insp.get_table_names():
        return
    if "waste_pct" not in _existing_columns(insp, "product_types_catalog"):
        db.execute(text(
            "ALTER TABLE product_types_catalog ADD COLUMN waste_pct NUMERIC(6,2) NOT NULL DEFAULT 0"
        ))
    db.commit()


def _migrate_drop_paper_sizes(db: Session) -> None:
    """Bỏ HẲN Danh mục Khổ giấy tiêu chuẩn: drop bảng `paper_sizes` + mọi cột tham chiếu.
      - material_costs.paper_size_id (nằm trong unique index composite → drop index, drop cột,
        tạo lại index KHÔNG có khổ),
      - machines.compatible_paper_size_ids / plate_die_rates.paper_size_ids (JSON, không index),
      - costing_paper_options.print_sheet_size_id / purchase_size_id (có index → drop index trước).
    Idempotent + best-effort mỗi câu (commit riêng, rollback nếu SQLite từ chối DROP COLUMN — dev.db
    có thể tạo lại). No-op trên DB fresh (create_all đã ra schema mới, các cột không tồn tại)."""
    bind = db.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    def has_col(table: str, col: str) -> bool:
        return table in tables and col in _existing_columns(insp, table)

    def run(sql: str) -> None:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    # 1) material_costs.paper_size_id — trong unique index composite uix_material_costs_current.
    if has_col("material_costs", "paper_size_id"):
        run("DROP INDEX IF EXISTS uix_material_costs_current")
        run("ALTER TABLE material_costs DROP COLUMN paper_size_id")
        run(
            "CREATE UNIQUE INDEX IF NOT EXISTS uix_material_costs_current ON material_costs "
            "(material_id, price_unit, coalesce(quantity_from, -1), coalesce(quantity_to, -1), "
            "coalesce(supplier, '')) WHERE effective_to IS NULL"
        )

    # 2) JSON cột tham chiếu (không index).
    if has_col("machines", "compatible_paper_size_ids"):
        run("ALTER TABLE machines DROP COLUMN compatible_paper_size_ids")
    if has_col("plate_die_rates", "paper_size_ids"):
        run("ALTER TABLE plate_die_rates DROP COLUMN paper_size_ids")

    # 3) costing_paper_options: 2 cột có index → drop index trước.
    if has_col("costing_paper_options", "print_sheet_size_id"):
        run("DROP INDEX IF EXISTS ix_costing_paper_options_print_sheet_size_id")
        run("ALTER TABLE costing_paper_options DROP COLUMN print_sheet_size_id")
    if has_col("costing_paper_options", "purchase_size_id"):
        run("DROP INDEX IF EXISTS ix_costing_paper_options_purchase_size_id")
        run("ALTER TABLE costing_paper_options DROP COLUMN purchase_size_id")

    # 4) drop bảng paper_sizes (FK duy nhất từ material_costs đã gỡ ở bước 1).
    run("DROP TABLE IF EXISTS paper_sizes")


def _migrate_customer_crm_fields(db: Session) -> None:
    """CRM đợt khảo sát (câu 7–29): điều khoản thanh toán riêng (#12), chiết khấu mặc
    định theo KH (#14, gate `can_view_discount`). Các BẢNG mới (customer_contacts /
    customer_addresses / customer_attachments) do create_all tự tạo — ở đây chỉ ADD
    COLUMN cho bảng đã tồn tại. No-op trên DB fresh."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "customers" in tables:
        cols = _existing_columns(insp, "customers")
        for name, ddl in (
            ("payment_term_type", "VARCHAR(24)"),
            ("payment_term_days", "INTEGER"),
            ("prepay_pct", "FLOAT"),
            ("payment_term_note", "VARCHAR(500)"),
            ("discount_trade_pct", "FLOAT"),
            ("discount_buyer_pct", "FLOAT"),
        ):
            if name not in cols:
                db.execute(text(f"ALTER TABLE customers ADD COLUMN {name} {ddl}"))
    if "role_permissions" in tables:
        if "can_view_discount" not in _existing_columns(insp, "role_permissions"):
            db.execute(text(
                "ALTER TABLE role_permissions ADD COLUMN can_view_discount BOOLEAN NOT NULL DEFAULT FALSE"
            ))
    db.commit()


MIGRATIONS: list[tuple[str, callable]] = [
    ("0002_operation_full_fields", _migrate_operation_full_fields),
    ("0003_norms_waste_groups", _migrate_norms_waste_groups),
    ("0004_paper_size_full_fields", _migrate_paper_size_full_fields),
    ("0005_machine_full_fields", _migrate_machine_full_fields),
    ("0006_product_type_full_fields", _migrate_product_type_full_fields),
    ("0007_materials_full_fields", _migrate_materials_full_fields),
    ("0008_plate_die_full_fields", _migrate_plate_die_full_fields),
    ("0009_estimate_lifecycle", _migrate_estimate_lifecycle),
    ("0010_norms_version_by_code", _migrate_norms_version_by_code),
    ("0011_employee_default_shift", _migrate_employee_default_shift),
    ("0012_employee_payroll_fields", _migrate_employee_payroll_fields),
    ("0013_payroll_line_khoan", _migrate_payroll_line_khoan),
    ("0014_role_permission_view_salary", _migrate_role_permission_view_salary),
    ("0015_role_permission_adjust", _migrate_role_permission_adjust),
    ("0016_attendance_adjust_cols", _migrate_attendance_adjust_cols),
    ("0017_leave_seen_by_employee", _migrate_leave_seen_by_employee),
    ("0018_product_type_waste_pct", _migrate_product_type_waste_pct),
    ("0019_drop_paper_sizes", _migrate_drop_paper_sizes),
    ("0020_customer_crm_fields", _migrate_customer_crm_fields),
]


def run_migrations(db: Session) -> None:
    """Apply any not-yet-applied migrations, tracked in schema_migrations."""
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "id VARCHAR(100) PRIMARY KEY, applied_at TIMESTAMP)"
    ))
    db.commit()
    applied = {r[0] for r in db.execute(text("SELECT id FROM schema_migrations")).all()}
    for mid, fn in MIGRATIONS:
        if mid in applied:
            continue
        fn(db)
        db.execute(
            text("INSERT INTO schema_migrations (id, applied_at) VALUES (:i, CURRENT_TIMESTAMP)"),
            {"i": mid},
        )
        db.commit()
