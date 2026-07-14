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


def _migrate_role_permission_edit_salary(db: Session) -> None:
    """Phân quyền: thêm cột `role_permissions.can_edit_salary` (SỬA dữ liệu nhạy cảm hồ sơ:
    lương/BHXH — tách khỏi view_salary). No-op trên DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    if "can_edit_salary" not in _existing_columns(insp, "role_permissions"):
        db.execute(text("ALTER TABLE role_permissions ADD COLUMN can_edit_salary BOOLEAN NOT NULL DEFAULT FALSE"))
    db.commit()


def _migrate_user_code_nv_to_tk(db: Session) -> None:
    """Đổi tiền tố mã tài khoản 'NV###' → 'TK###' (GIỮ NGUYÊN số) để không trùng tiền tố với
    employees.code (Đ1: gỡ nhầm tài khoản vs hồ sơ). Idempotent: chỉ đụng mã còn 'NV%';
    no-op trên DB fresh (repo đã sinh mã 'TK')."""
    insp = inspect(db.get_bind())
    if "users" not in insp.get_table_names():
        return
    db.execute(text("UPDATE users SET code = 'TK' || substr(code, 3) WHERE code LIKE 'NV%'"))
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


def _migrate_drop_quy_tac_binh_bai(db: Session) -> None:
    """Bỏ HẲN module Quy tắc bình bài + Tính giá thành: drop 3 bảng
    `quy_tac_binh_bai_version` (FK → header) → `quy_tac_binh_bai` → `folding_scheme`.
    Best-effort mỗi câu (commit riêng, rollback nếu lỗi). No-op trên DB fresh (bảng không còn
    trong create_all vì model đã xóa). Cột `loai_san_pham.imposition_rule_id` giữ nguyên như
    số nguyên vô hại (không còn ai resolve)."""
    def run(sql: str) -> None:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    run("DROP TABLE IF EXISTS quy_tac_binh_bai_version")
    run("DROP TABLE IF EXISTS quy_tac_binh_bai")
    run("DROP TABLE IF EXISTS folding_scheme")


def _migrate_giay_chung_loai_and_vat_tu(db: Session) -> None:
    """Danh mục Giấy & Vật tư: thêm `giay_nguyen.chung_loai_giay_id`; GỘP `muc` + `ban_kem` →
    `vat_tu_in_an` rồi drop 2 bảng cũ. Bảng `chung_loai_giay` + `vat_tu_in_an` do create_all tạo
    (model mới). Best-effort mỗi câu. No-op trên DB fresh (muc/ban_kem không còn model → không tồn
    tại; giay_nguyen đã có cột). created_at/updated_at cấp CURRENT_TIMESTAMP (cột NOT NULL)."""
    bind = db.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    def run(sql: str) -> None:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    # 1) giay_nguyen.chung_loai_giay_id (giấy ăn theo chủng loại).
    if "giay_nguyen" in tables and "chung_loai_giay_id" not in _existing_columns(insp, "giay_nguyen"):
        db.execute(text("ALTER TABLE giay_nguyen ADD COLUMN chung_loai_giay_id INTEGER"))
        db.commit()
        run("CREATE INDEX IF NOT EXISTS ix_giay_nguyen_chung_loai_giay_id "
            "ON giay_nguyen (chung_loai_giay_id)")

    # 2) Gộp mực + bản kẽm cũ → vat_tu_in_an (mã MUC-*/KEM-* không đụng nhau).
    if "vat_tu_in_an" in tables:
        if "muc" in tables:
            run("INSERT INTO vat_tu_in_an "
                "(ma, ten, loai_vat_tu, don_vi_gia, don_gia, ton, loai_muc, ma_pantone, "
                " coverage_tiers, active, created_at, updated_at) "
                "SELECT ma, ten, 'muc', 'nghin_luot', don_gia, 0, loai_muc, ma_pantone, "
                " coverage_tiers, active, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM muc")
        if "ban_kem" in tables:
            run("INSERT INTO vat_tu_in_an "
                "(ma, ten, loai_vat_tu, don_vi_gia, don_gia, ton, khoa_class, active, "
                " created_at, updated_at) "
                "SELECT ma, ten, 'kem', 'ban', don_gia_kem, ton, khoa_class, active, "
                " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM ban_kem")

    # 3) Drop bảng cũ (đã gỡ model).
    run("DROP TABLE IF EXISTS muc")
    run("DROP TABLE IF EXISTS ban_kem")


def _migrate_may_thiet_bi_plate_print_area(db: Session) -> None:
    """Máy: thêm Khổ kẽm (`kho_kem_dai`/`kho_kem_rong`) + Vùng in lớn nhất
    (`vung_in_dai`/`vung_in_rong`) — mm, nullable Integer. Khớp DANH SÁCH MÁY IN của xưởng
    (khổ kẽm + vùng in ≠ khổ giấy). No-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "may_thiet_bi" not in insp.get_table_names():
        return
    existing = _existing_columns(insp, "may_thiet_bi")
    for name in ("kho_kem_dai", "kho_kem_rong", "vung_in_dai", "vung_in_rong"):
        if name not in existing:
            db.execute(text(f"ALTER TABLE may_thiet_bi ADD COLUMN {name} INTEGER"))
    db.commit()


def _migrate_may_thiet_bi_ghi_chu_2(db: Session) -> None:
    """Máy: thêm cột Ghi chú 2 (`ghi_chu_2`) — TEXT nullable. Bảng dữ liệu xưởng có 2 cột
    ghi chú. No-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "may_thiet_bi" not in insp.get_table_names():
        return
    if "ghi_chu_2" not in _existing_columns(insp, "may_thiet_bi"):
        db.execute(text("ALTER TABLE may_thiet_bi ADD COLUMN ghi_chu_2 TEXT"))
    db.commit()


def _migrate_vat_tu_simplify(db: Session) -> None:
    """Làm gọn theo bảng xưởng: bỏ TỒN khỏi giấy; vật tư về PHẲNG (mã·tên·ĐVT·giá·ghi chú) —
    thêm `vat_tu_in_an.ghi_chu`, gỡ loai_vat_tu/ton/loai_muc/ma_pantone/coverage_tiers/khoa_class
    + `giay_nguyen.ton`. Best-effort mỗi câu (SQLite cũ có thể từ chối DROP COLUMN → cột mồ côi vô
    hại vì model không map). No-op trên DB fresh (create_all đã ra shape mới; cột thừa không tồn tại)."""
    bind = db.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    def run(sql: str) -> None:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    if "vat_tu_in_an" in tables:
        cols = _existing_columns(insp, "vat_tu_in_an")
        if "ghi_chu" not in cols:
            db.execute(text("ALTER TABLE vat_tu_in_an ADD COLUMN ghi_chu VARCHAR(500)"))
            db.commit()
        for c in ("loai_vat_tu", "ton", "loai_muc", "ma_pantone", "coverage_tiers", "khoa_class"):
            if c in cols:
                run(f"ALTER TABLE vat_tu_in_an DROP COLUMN {c}")

    if "giay_nguyen" in tables and "ton" in _existing_columns(insp, "giay_nguyen"):
        run("ALTER TABLE giay_nguyen DROP COLUMN ton")


def _migrate_bu_hao_dynamic_bands(db: Session) -> None:
    """Bù hao mô hình MỞ: bỏ bảng `bu_hao` 7-cột-cứng (nếu có), tạo lại bảng bậc-động
    (truc/key_tu/key_den/bac JSON). Chỉ dev từng tạo bảng cũ (module chưa deploy) → drop an toàn.
    create_all chạy TRƯỚC migration nên bảng cũ không bị sửa; ở đây drop rồi tạo lại đúng shape mới."""
    bind = db.get_bind()
    insp = inspect(bind)
    if "bu_hao" in insp.get_table_names() and "to_le_3000" in _existing_columns(insp, "bu_hao"):
        db.execute(text("DROP TABLE bu_hao"))
        db.commit()
    # Tạo bảng theo model hiện tại (no-op nếu đã đúng shape).
    from .models.bu_hao import BuHao
    BuHao.__table__.create(bind, checkfirst=True)
    db.commit()


def _migrate_cong_doan_bu_hao_fields(db: Session) -> None:
    """Công đoạn: thêm `ten_hien_thi` (tên in cho thợ) + `so_to_bu_hao` (số tờ hao cộng khi có
    công đoạn này, mặc định 50). Bảng `bu_hao` (danh mục bù hao) do create_all tạo. No-op trên
    DB fresh / cột đã có."""
    insp = inspect(db.get_bind())
    if "cong_doan" not in insp.get_table_names():
        return
    existing = _existing_columns(insp, "cong_doan")
    if "ten_hien_thi" not in existing:
        db.execute(text("ALTER TABLE cong_doan ADD COLUMN ten_hien_thi VARCHAR(150)"))
    if "so_to_bu_hao" not in existing:
        db.execute(text("ALTER TABLE cong_doan ADD COLUMN so_to_bu_hao INTEGER NOT NULL DEFAULT 50"))
    db.commit()


def _migrate_giay_open_fields(db: Session) -> None:
    """Giấy mở hơn (Phương án A): thêm `giay_nguyen.gia_thi_truong` / `kho_tinh_gia` / `ghi_chu`
    (khớp cột bảng xưởng: Giá thị trường / Khổ tính giá? / Ghi chú). Khổ 0 = cuộn: đã cho phép ở
    tầng schema/service (cột kho_* vẫn Integer, 0 hợp lệ). No-op trên DB fresh / cột đã có."""
    insp = inspect(db.get_bind())
    if "giay_nguyen" not in insp.get_table_names():
        return
    existing = _existing_columns(insp, "giay_nguyen")
    for name, ddl in (
        ("gia_thi_truong", "NUMERIC(18,2)"),
        ("kho_tinh_gia", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ("ghi_chu", "VARCHAR(500)"),
    ):
        if name not in existing:
            db.execute(text(f"ALTER TABLE giay_nguyen ADD COLUMN {name} {ddl}"))
    db.commit()


def _migrate_giay_version_no(db: Session) -> None:
    """Giấy: thêm `giay_nguyen.version_no` (số phiên bản giá hiện hành, mirror từ
    `giay_gia_version`). Default 1. No-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "giay_nguyen" not in insp.get_table_names():
        return
    if "version_no" not in _existing_columns(insp, "giay_nguyen"):
        db.execute(text("ALTER TABLE giay_nguyen ADD COLUMN version_no INTEGER NOT NULL DEFAULT 1"))
    db.commit()


def _migrate_cong_doan_size_tiers(db: Session) -> None:
    """Công đoạn: thêm `cong_doan.size_tiers` (JSON) — bậc đơn giá theo KÍCH THƯỚC thành phẩm
    (cạnh dài, cm): [{den_cm, don_gia}]. Cho công đoạn kiểu dán/bế tính đơn giá theo cỡ (spec
    tính-giá diễn giải). Nullable → không ảnh hưởng công đoạn cũ. No-op trên DB fresh / cột đã có."""
    insp = inspect(db.get_bind())
    if "cong_doan" not in insp.get_table_names():
        return
    if "size_tiers" not in _existing_columns(insp, "cong_doan"):
        db.execute(text("ALTER TABLE cong_doan ADD COLUMN size_tiers JSON"))
    db.commit()


def _migrate_purchase_line_discount_vat(db: Session) -> None:
    """Thu mua: thêm giảm giá (%) và thuế GTGT (%) cho từng dòng phiếu mua.

    Tiền giảm giá, tiền VAT và thành tiền được tính động từ số lượng, đơn giá,
    discount_percent và vat_percent nên không lưu dư ở bảng dòng hàng.
    """
    insp = inspect(db.get_bind())
    if "purchase_request_lines" not in insp.get_table_names():
        return
    existing = _existing_columns(insp, "purchase_request_lines")
    if "discount_percent" not in existing:
        db.execute(text(
            "ALTER TABLE purchase_request_lines "
            "ADD COLUMN discount_percent NUMERIC(6,2) NOT NULL DEFAULT 0"
        ))
    if "vat_percent" not in existing:
        db.execute(text(
            "ALTER TABLE purchase_request_lines "
            "ADD COLUMN vat_percent NUMERIC(6,2) NOT NULL DEFAULT 0"
        ))
    db.commit()


def _migrate_department_request_pending_approval_status(db: Session) -> None:
    """Reclassify source requests linked to purchase requests waiting for approval.

    Older code moved a department request straight to ``in_purchase`` as soon as a purchase
    request was created. Business-wise it should be ``pending_approval`` until accounting
    approves the purchase request.
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    required = {"department_purchase_requests", "purchase_request_sources", "purchase_requests"}
    if not required.issubset(tables):
        return

    db.execute(text(
        "UPDATE department_purchase_requests "
        "SET status = 'done' "
        "WHERE status <> 'cancelled' "
        "AND id IN ("
        "  SELECT prs.department_request_id "
        "  FROM purchase_request_sources prs "
        "  JOIN purchase_requests pr ON pr.id = prs.purchase_request_id "
        "  WHERE pr.status = 'received'"
        ")"
    ))
    db.execute(text(
        "UPDATE department_purchase_requests "
        "SET status = 'in_purchase' "
        "WHERE status NOT IN ('cancelled', 'done') "
        "AND id IN ("
        "  SELECT prs.department_request_id "
        "  FROM purchase_request_sources prs "
        "  JOIN purchase_requests pr ON pr.id = prs.purchase_request_id "
        "  WHERE pr.status IN ('approved', 'purchased')"
        ")"
    ))
    db.execute(text(
        "UPDATE department_purchase_requests "
        "SET status = 'pending_approval' "
        "WHERE status NOT IN ('cancelled', 'done') "
        "AND id IN ("
        "  SELECT prs.department_request_id "
        "  FROM purchase_request_sources prs "
        "  JOIN purchase_requests pr ON pr.id = prs.purchase_request_id "
        "  WHERE pr.status IN ('draft', 'pending_approval')"
        ") "
        "AND id NOT IN ("
        "  SELECT prs.department_request_id "
        "  FROM purchase_request_sources prs "
        "  JOIN purchase_requests pr ON pr.id = prs.purchase_request_id "
        "  WHERE pr.status IN ('approved', 'purchased', 'received')"
        ")"
    ))
    db.execute(text(
        "UPDATE department_purchase_requests "
        "SET status = 'open' "
        "WHERE status IN ('pending_approval', 'in_purchase') "
        "AND NOT EXISTS ("
        "  SELECT 1 "
        "  FROM purchase_request_sources prs "
        "  JOIN purchase_requests pr ON pr.id = prs.purchase_request_id "
        "  WHERE prs.department_request_id = department_purchase_requests.id "
        "  AND pr.status IN ('draft', 'pending_approval', 'approved', 'purchased', 'received')"
        ")"
    ))
    db.commit()


def _migrate_stock_moves_voucher(db: Session) -> None:
    """Kho Document Engine (spec-13): thêm cột `status_id` (trạng thái hàng) + `voucher_id`
    (truy nguồn phiếu) vào bảng `stock_moves` (P0). Bảng phiếu/trạng thái MỚI do create_all
    tự dựng — chỉ `stock_moves` cũ cần ALTER. No-op trên DB fresh / khi bảng chưa có."""
    insp = inspect(db.get_bind())
    if "stock_moves" not in insp.get_table_names():
        return
    existing = _existing_columns(insp, "stock_moves")
    for name, ddl in (("status_id", "INTEGER"), ("voucher_id", "INTEGER")):
        if name not in existing:
            db.execute(text(f"ALTER TABLE stock_moves ADD COLUMN {name} {ddl}"))
    db.commit()


def _migrate_stock_moves_unit_cost(db: Session) -> None:
    """Giá vốn kho (spec-13 E): thêm cột `unit_cost` vào `stock_moves`. No-op DB fresh."""
    insp = inspect(db.get_bind())
    if "stock_moves" not in insp.get_table_names():
        return
    if "unit_cost" not in _existing_columns(insp, "stock_moves"):
        db.execute(text("ALTER TABLE stock_moves ADD COLUMN unit_cost BIGINT"))
    db.commit()


def _migrate_production_order_header_fields(db: Session) -> None:
    """Sản xuất Lớp A: thêm cột header giàu vào `production_orders` (hợp đồng/khách/ngày đặt-nhận/
    lưu ý kỹ thuật/người cập nhật). Bảng `production_orders` do create_all dựng ở P1; DB đã có
    bảng bản cũ cần ALTER. No-op trên DB fresh (create_all đã dựng đủ cột)."""
    insp = inspect(db.get_bind())
    if "production_orders" not in insp.get_table_names():
        return
    cols = [
        ("contract_no", "VARCHAR(60)"),
        ("customer_id", "INTEGER"),
        ("customer_name", "VARCHAR(255)"),
        ("order_date", "DATE"),
        ("delivery_request_date", "DATE"),
        ("tech_note_print", "TEXT"),
        ("tech_note_finishing", "TEXT"),
        ("updated_by_user_id", "INTEGER"),
    ]
    existing = _existing_columns(insp, "production_orders")
    for name, ddl in cols:
        if name not in existing:
            db.execute(text(f"ALTER TABLE production_orders ADD COLUMN {name} {ddl}"))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_production_orders_customer_id ON production_orders (customer_id)"
    ))
    db.commit()


def _migrate_payment_voucher_amount_vnd(db: Session) -> None:
    """Store the VND equivalent used to reserve and reconcile a purchase total."""
    insp = inspect(db.get_bind())
    if "payment_vouchers" not in insp.get_table_names():
        return
    existing = _existing_columns(insp, "payment_vouchers")
    if "amount_vnd" not in existing:
        db.execute(text(
            "ALTER TABLE payment_vouchers "
            "ADD COLUMN amount_vnd BIGINT NOT NULL DEFAULT 0"
        ))
        db.execute(text(
            "UPDATE payment_vouchers "
            "SET amount_vnd = CAST(ROUND(amount * exchange_rate) AS BIGINT)"
        ))
    db.commit()


def _migrate_production_order_bu(db: Session) -> None:
    """Sản xuất: thêm cột lệnh bù vào `production_orders` (order_kind/parent_order_id/bu_reason).
    No-op trên DB fresh (create_all đã dựng đủ cột)."""
    insp = inspect(db.get_bind())
    if "production_orders" not in insp.get_table_names():
        return
    cols = [
        ("order_kind", "VARCHAR(10) NOT NULL DEFAULT 'thuong'"),
        ("parent_order_id", "INTEGER"),
        ("bu_reason", "VARCHAR(255)"),
    ]
    existing = _existing_columns(insp, "production_orders")
    for name, ddl in cols:
        if name not in existing:
            db.execute(text(f"ALTER TABLE production_orders ADD COLUMN {name} {ddl}"))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_production_orders_order_kind ON production_orders (order_kind)"
    ))
    db.commit()


def _migrate_production_order_bu_fields(db: Session) -> None:
    """Sản xuất: thêm loại lệnh bù vào `production_orders` — order_kind (thuong/bu),
    parent_order_id (LSX gốc), bu_reason (lý do bù). No-op trên DB fresh."""
    insp = inspect(db.get_bind())
    if "production_orders" not in insp.get_table_names():
        return
    cols = [
        ("order_kind", "VARCHAR(10) NOT NULL DEFAULT 'thuong'"),
        ("parent_order_id", "INTEGER"),
        ("bu_reason", "VARCHAR(255)"),
    ]
    existing = _existing_columns(insp, "production_orders")
    for name, ddl in cols:
        if name not in existing:
            db.execute(text(f"ALTER TABLE production_orders ADD COLUMN {name} {ddl}"))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_production_orders_order_kind ON production_orders (order_kind)"
    ))
    db.commit()


def _migrate_stock_count_phaseA(db: Session) -> None:
    """Kiểm kê phần A: thêm participants (đợt) + defective_qty/damaged_qty (dòng — kém/mất phẩm
    chất). No-op trên DB fresh."""
    insp = inspect(db.get_bind())
    names = insp.get_table_names()
    if "stock_counts" in names and "participants" not in _existing_columns(insp, "stock_counts"):
        db.execute(text("ALTER TABLE stock_counts ADD COLUMN participants TEXT"))
    if "stock_count_lines" in names:
        existing = _existing_columns(insp, "stock_count_lines")
        for name in ("defective_qty", "damaged_qty"):
            if name not in existing:
                db.execute(text(f"ALTER TABLE stock_count_lines ADD COLUMN {name} NUMERIC(18,3)"))
    db.commit()


def _migrate_purchase_request_expected_receipt_date(db: Session) -> None:
    """Thu mua: thêm `purchase_requests.expected_receipt_date` (Ngày dự kiến nhận hàng —
    NCC hẹn giao, khác needed_date là ngày phòng ban cần). Nullable Date. No-op trên DB
    fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "purchase_requests" not in insp.get_table_names():
        return
    if "expected_receipt_date" not in _existing_columns(insp, "purchase_requests"):
        db.execute(text("ALTER TABLE purchase_requests ADD COLUMN expected_receipt_date DATE"))
    db.commit()


def _migrate_drop_payment_refunds_renamed(db: Session) -> None:
    """Kế toán: bảng `payment_refunds` được ĐỔI TÊN thành `payment_receipts` (Phiếu thu)
    TRƯỚC khi tính năng ship — bảng cũ chỉ tồn tại trên dev với dữ liệu thử. Drop
    best-effort; bảng mới do create_all dựng. No-op khi bảng cũ không tồn tại."""
    try:
        db.execute(text("DROP TABLE IF EXISTS payment_refunds"))
        db.commit()
    except Exception:
        db.rollback()


def _migrate_cong_doan_pricing_basis_v2(db: Session) -> None:
    """Công đoạn: nới `pricing_basis` VARCHAR(16)→(32) cho bộ đơn vị tính giá mới (key dài hơn,
    vd `per_finished_area`) — cần cho Postgres (SQLite bỏ qua độ dài). Đồng thời xóa giá trị theo
    bộ key CŨ (per_ram/per_1000_luot/per_pass/per_book/per_number/per_m2/per_hour) về NULL để không
    còn enum không hợp lệ. Best-effort; no-op khi bảng chưa có."""
    insp = inspect(db.get_bind())
    if "cong_doan" not in insp.get_table_names():
        return

    def run(sql: str) -> None:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    # Postgres: đổi kiểu cột. SQLite: câu này lỗi → bỏ qua (độ dài VARCHAR không bị ép).
    run("ALTER TABLE cong_doan ALTER COLUMN pricing_basis TYPE VARCHAR(32)")
    # Dọn key cũ không còn trong whitelist mới.
    run(
        "UPDATE cong_doan SET pricing_basis = NULL WHERE pricing_basis IN "
        "('per_ram','per_1000_luot','per_pass','per_book','per_number','per_m2','per_hour')"
    )


def _migrate_bu_hao_versioning(db: Session) -> None:
    """Bù hao: thêm `bu_hao.version_no` (số phiên bản hiện hành, mặc định 1)"""
    bind = db.get_bind()
    insp = inspect(bind)
    if "bu_hao" in insp.get_table_names():
        existing = _existing_columns(insp, "bu_hao")
        if "version_no" not in existing:
            db.execute(text("ALTER TABLE bu_hao ADD COLUMN version_no INTEGER NOT NULL DEFAULT 1"))
    db.commit()


def _migrate_cong_doan_kieu_bu_hao(db: Session) -> None:
    """Công đoạn: thêm `kieu_bu_hao` (khong/theo_so_mau/theo_so_con/co_dinh) — nối công đoạn tới
    trục bù hao. Mặc định 'khong'. No-op trên DB fresh / cột đã có."""
    insp = inspect(db.get_bind())
    if "cong_doan" not in insp.get_table_names():
        return
    if "kieu_bu_hao" not in _existing_columns(insp, "cong_doan"):
        db.execute(text(
            "ALTER TABLE cong_doan ADD COLUMN kieu_bu_hao VARCHAR(16) NOT NULL DEFAULT 'khong'"
        ))
    db.commit()


def _migrate_payroll_ot_night_bhxh_cap(db: Session) -> None:
    """Pha 4a: cắm tăng ca (OT) + phụ cấp ca đêm + trần đóng BHXH.
    - payroll_params += standard_hours_per_day, ot_multiplier, night_pct, bh_base_cap, bhtn_base_cap
    - payroll_lines  += ot_minutes, ot_pay, night_days, night_pay
    No-op trên DB fresh (create_all đã tạo đủ cột)."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "payroll_params" in tables:
        cols = _existing_columns(insp, "payroll_params")
        if "standard_hours_per_day" not in cols:
            db.execute(text("ALTER TABLE payroll_params ADD COLUMN standard_hours_per_day NUMERIC(5,2) NOT NULL DEFAULT 8"))
        if "ot_multiplier" not in cols:
            db.execute(text("ALTER TABLE payroll_params ADD COLUMN ot_multiplier NUMERIC(5,2) NOT NULL DEFAULT 1.5"))
        if "night_pct" not in cols:
            db.execute(text("ALTER TABLE payroll_params ADD COLUMN night_pct NUMERIC(5,4) NOT NULL DEFAULT 0.3"))
        if "bh_base_cap" not in cols:
            db.execute(text("ALTER TABLE payroll_params ADD COLUMN bh_base_cap NUMERIC(14,2) NOT NULL DEFAULT 50600000"))
        if "bhtn_base_cap" not in cols:
            db.execute(text("ALTER TABLE payroll_params ADD COLUMN bhtn_base_cap NUMERIC(14,2) NOT NULL DEFAULT 106200000"))
    if "payroll_lines" in tables:
        cols = _existing_columns(insp, "payroll_lines")
        if "ot_minutes" not in cols:
            db.execute(text("ALTER TABLE payroll_lines ADD COLUMN ot_minutes INTEGER NOT NULL DEFAULT 0"))
        if "ot_pay" not in cols:
            db.execute(text("ALTER TABLE payroll_lines ADD COLUMN ot_pay NUMERIC(14,2) NOT NULL DEFAULT 0"))
        if "night_days" not in cols:
            db.execute(text("ALTER TABLE payroll_lines ADD COLUMN night_days INTEGER NOT NULL DEFAULT 0"))
        if "night_pay" not in cols:
            db.execute(text("ALTER TABLE payroll_lines ADD COLUMN night_pay NUMERIC(14,2) NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_payroll_pit_2026(db: Session) -> None:
    """Pha 4b: TNCN tự tính theo luật 2026.
    - payroll_lines += pit_manual (bool), pit_taxable (numeric); backfill pit_manual=TRUE cho
      dòng đã có pit>0 (số nhập tay cũ → giữ, không bị auto ghi đè).
    - cập nhật giảm trừ gia cảnh dòng params đang ở mức CŨ (11tr/4.4tr) → 2026 (15.5tr/6.2tr)
      theo NQ 110/2025/UBTVQH15 — CHỈ đổi nếu còn mức cũ (không đè số admin đã chỉnh).
    Bảng pit_tax_brackets do create_all tạo + seed_pit_brackets. No-op fresh."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "payroll_lines" in tables:
        cols = _existing_columns(insp, "payroll_lines")
        if "pit_manual" not in cols:
            db.execute(text("ALTER TABLE payroll_lines ADD COLUMN pit_manual BOOLEAN NOT NULL DEFAULT FALSE"))
            db.execute(text("UPDATE payroll_lines SET pit_manual = TRUE WHERE pit > 0"))
        if "pit_taxable" not in cols:
            db.execute(text("ALTER TABLE payroll_lines ADD COLUMN pit_taxable NUMERIC(14,2) NOT NULL DEFAULT 0"))
    if "payroll_params" in tables:
        db.execute(text("UPDATE payroll_params SET deduction_self = 15500000 WHERE deduction_self = 11000000"))
        db.execute(text("UPDATE payroll_params SET deduction_dependent = 6200000 WHERE deduction_dependent = 4400000"))
    db.commit()


def _migrate_payroll_period_paid(db: Session) -> None:
    """Pha 4c: chi trả — payroll_periods += paid_at, paid_by (trạng thái 'paid'). No-op fresh."""
    insp = inspect(db.get_bind())
    if "payroll_periods" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "payroll_periods")
    if "paid_at" not in cols:
        db.execute(text("ALTER TABLE payroll_periods ADD COLUMN paid_at TIMESTAMP"))
    if "paid_by" not in cols:
        db.execute(text("ALTER TABLE payroll_periods ADD COLUMN paid_by INTEGER"))
    db.commit()


def _migrate_piece_batch_status(db: Session) -> None:
    """Pha 5 Lương khoán: thêm cột chốt sổ `piece_batches.status/locked_at/locked_by`.
    Chỉ sổ đã chốt (locked) mới chảy vào bảng lương + cấm sửa. No-op trên DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    if "piece_batches" not in insp.get_table_names():
        return
    existing = _existing_columns(insp, "piece_batches")
    if "status" not in existing:
        db.execute(text("ALTER TABLE piece_batches ADD COLUMN status VARCHAR(8) NOT NULL DEFAULT 'draft'"))
    if "locked_at" not in existing:
        db.execute(text("ALTER TABLE piece_batches ADD COLUMN locked_at TIMESTAMP"))
    if "locked_by" not in existing:
        db.execute(text("ALTER TABLE piece_batches ADD COLUMN locked_by INTEGER"))
    db.commit()


def _migrate_phieu_san_luong_5b1(db: Session) -> None:
    """Pha 5b-1 Phiếu sản lượng công đoạn: thêm cột nối khoán↔công đoạn↔phiếu.
    - cong_doan.khoan_ghi_theo (to/nguoi/khong)
    - piece_rates.cong_doan (mã công đoạn gắn đơn giá)
    - piece_batch_entries.source + production_output_id (dòng materialize từ phiếu)
    Bảng production_outputs là bảng MỚI → create_all tự dựng, KHÔNG cần ở đây.
    No-op trên DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "cong_doan" in tables and "khoan_ghi_theo" not in _existing_columns(insp, "cong_doan"):
        db.execute(text("ALTER TABLE cong_doan ADD COLUMN khoan_ghi_theo VARCHAR(8) NOT NULL DEFAULT 'khong'"))
    if "piece_rates" in tables and "cong_doan" not in _existing_columns(insp, "piece_rates"):
        db.execute(text("ALTER TABLE piece_rates ADD COLUMN cong_doan VARCHAR(30)"))
    if "piece_batch_entries" in tables:
        cols = _existing_columns(insp, "piece_batch_entries")
        if "source" not in cols:
            db.execute(text("ALTER TABLE piece_batch_entries ADD COLUMN source VARCHAR(8) NOT NULL DEFAULT 'manual'"))
        if "production_output_id" not in cols:
            db.execute(text("ALTER TABLE piece_batch_entries ADD COLUMN production_output_id INTEGER"))
    db.commit()


def _migrate_phieu_san_luong_5b2(db: Session) -> None:
    """Pha 5b-2: trừ lỗi + ghi theo người.
    - cong_doan.allowed_defect_pct / allowed_defect_abs (ngưỡng hao cho phép)
    - production_outputs.defect_qty / defect_cause / defect_deduction
    No-op trên DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "cong_doan" in tables:
        cols = _existing_columns(insp, "cong_doan")
        if "allowed_defect_pct" not in cols:
            db.execute(text("ALTER TABLE cong_doan ADD COLUMN allowed_defect_pct NUMERIC(6,4) NOT NULL DEFAULT 0"))
        if "allowed_defect_abs" not in cols:
            db.execute(text("ALTER TABLE cong_doan ADD COLUMN allowed_defect_abs NUMERIC(14,2) NOT NULL DEFAULT 0"))
    if "production_outputs" in tables:
        cols = _existing_columns(insp, "production_outputs")
        if "defect_qty" not in cols:
            db.execute(text("ALTER TABLE production_outputs ADD COLUMN defect_qty NUMERIC(14,2) NOT NULL DEFAULT 0"))
        if "defect_cause" not in cols:
            db.execute(text("ALTER TABLE production_outputs ADD COLUMN defect_cause VARCHAR(20)"))
        if "defect_deduction" not in cols:
            db.execute(text("ALTER TABLE production_outputs ADD COLUMN defect_deduction NUMERIC(14,2) NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_order_line_cost_snapshot(db: Session) -> None:
    """A2 (đơn đặc thù): thêm cột `order_lines.cost_snapshot` (giá vốn TỔNG dòng, VND) để soi biên
    lợi nhuận. Đơn cũ = NULL → bỏ qua soi biên. No-op trên DB fresh / bảng chưa có.
    (Bảng `order_approvals` là bảng MỚI → create_all tự tạo, không cần ALTER ở đây.)"""
    insp = inspect(db.get_bind())
    if "order_lines" not in insp.get_table_names():
        return
    if "cost_snapshot" not in _existing_columns(insp, "order_lines"):
        db.execute(text("ALTER TABLE order_lines ADD COLUMN cost_snapshot BIGINT"))
    db.commit()


def _migrate_role_permission_approve_exception(db: Session) -> None:
    """Phân quyền A2: thêm cột `role_permissions.can_approve_exception` (GĐ duyệt "đơn đặc thù").
    Chỉ ADD COLUMN DEFAULT FALSE — quyền cho vai Giám đốc do seed_roles tự upsert lại mỗi lần khởi
    động (không cần backfill). No-op trên DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    if "can_approve_exception" not in _existing_columns(insp, "role_permissions"):
        db.execute(text(
            "ALTER TABLE role_permissions ADD COLUMN can_approve_exception BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    db.commit()


def _migrate_role_permission_set_credit_terms(db: Session) -> None:
    """khach_hang: thêm cột `role_permissions.can_set_credit_terms` (quyền THIẾT LẬP điều khoản
    tín dụng khách — hạn mức + điều khoản thanh toán). Chỉ ADD COLUMN DEFAULT FALSE — quyền cho
    vai Giám đốc/Kế toán trưởng do seed_roles tự upsert lại mỗi lần khởi động (không cần backfill).
    No-op trên DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    if "can_set_credit_terms" not in _existing_columns(insp, "role_permissions"):
        db.execute(text(
            "ALTER TABLE role_permissions ADD COLUMN can_set_credit_terms BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    db.commit()


def _migrate_customer_kind_and_pricing_bounds(db: Session) -> None:
    """Redesign khách hàng spec-06 v2: thêm `customers.customer_kind` (cá nhân/công ty, khách
    cũ mặc định 'cong_ty') + rào chiết khấu/biên min–max (4 cột FLOAT, NULL = chưa đặt).
    Chỉ ADD COLUMN. No-op trên DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    if "customers" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "customers")
    if "customer_kind" not in cols:
        db.execute(text(
            "ALTER TABLE customers ADD COLUMN customer_kind VARCHAR(12) NOT NULL DEFAULT 'cong_ty'"
        ))
    for col in ("discount_min_pct", "discount_max_pct", "margin_min_pct", "margin_max_pct"):
        if col not in cols:
            db.execute(text(f"ALTER TABLE customers ADD COLUMN {col} FLOAT"))
    db.commit()


def _migrate_quote_phieu_tinh_gia_link(db: Session) -> None:
    """BG-1: Báo giá dựng lại nguồn từ Phiếu tính giá (PTG). Thêm cột SOFT-link (plain int):
    `quotes.phieu_tinh_gia_id` + `quote_items.phieu_thanh_phan_id`. No-op DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "quotes" in tables and "phieu_tinh_gia_id" not in _existing_columns(insp, "quotes"):
        db.execute(text("ALTER TABLE quotes ADD COLUMN phieu_tinh_gia_id INTEGER"))
    if "quote_items" in tables and "phieu_thanh_phan_id" not in _existing_columns(insp, "quote_items"):
        db.execute(text("ALTER TABLE quote_items ADD COLUMN phieu_thanh_phan_id INTEGER"))
    db.commit()


def _migrate_quote_bao_gia_fields(db: Session) -> None:
    """redesign-bao-gia §5: người liên hệ snapshot trên báo giá (auto-fill từ CRM liên hệ chính)
    + MÃ PO per dòng (mẫu báo giá thật). No-op nếu bảng/cột đã có."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "quotes" in tables:
        qcols = _existing_columns(insp, "quotes")
        if "contact_name_snapshot" not in qcols:
            db.execute(text("ALTER TABLE quotes ADD COLUMN contact_name_snapshot VARCHAR(255)"))
        if "contact_phone_snapshot" not in qcols:
            db.execute(text("ALTER TABLE quotes ADD COLUMN contact_phone_snapshot VARCHAR(30)"))
        if "contact_title_snapshot" not in qcols:
            db.execute(text("ALTER TABLE quotes ADD COLUMN contact_title_snapshot VARCHAR(120)"))
    if "quote_items" in tables and "po_code" not in _existing_columns(insp, "quote_items"):
        db.execute(text("ALTER TABLE quote_items ADD COLUMN po_code VARCHAR(60)"))
    db.commit()


def _migrate_quote_decision_seen_at(db: Session) -> None:
    """Real-time 'gửi duyệt' (SSE): mốc người soạn đã xem quyết định GĐ gần nhất — nuôi badge/toast
    phía Sale. Nullable timestamp (NULL = có quyết định mới chưa xem). No-op nếu cột đã có."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "quotes" in tables and "decision_seen_at" not in _existing_columns(insp, "quotes"):
        db.execute(text("ALTER TABLE quotes ADD COLUMN decision_seen_at TIMESTAMP WITH TIME ZONE"))
    db.commit()


def _migrate_ptg_created_by(db: Session) -> None:
    """redesign-bao-gia §10 (P8): thêm chủ sở hữu `created_by` cho Phiếu tính giá để lọc phạm vi
    (NV Sales chỉ thấy phiếu của mình; TP KD/GĐ thấy cả phòng/tất cả). Best-effort backfill từ `ktv`
    (khớp users.name hoặc users.username) cho dữ liệu cũ; không khớp → NULL (chỉ scope 'all' thấy)."""
    insp = inspect(db.get_bind())
    if "phieu_tinh_gia" not in insp.get_table_names():
        return
    if "created_by" not in _existing_columns(insp, "phieu_tinh_gia"):
        db.execute(text("ALTER TABLE phieu_tinh_gia ADD COLUMN created_by INTEGER"))
        db.execute(text(
            "UPDATE phieu_tinh_gia SET created_by = ("
            " SELECT u.id FROM users u"
            " WHERE u.name = phieu_tinh_gia.ktv OR u.username = phieu_tinh_gia.ktv LIMIT 1"
            ") WHERE created_by IS NULL AND ktv IS NOT NULL"
        ))
    db.commit()


def _migrate_cong_doan_bu_hao_ref(db: Session) -> None:
    """Bù hao đổi mô hình: bỏ trục số màu/số con — công đoạn TRỎ THẲNG 1 mã bù hao. Thêm
    `cong_doan.bu_hao_id` (soft ref → bu_hao.id). Giá trị `kieu_bu_hao` cũ (theo_so_mau/
    theo_so_con) không còn tự dò được → đưa về 'khong' (người dùng cấu hình lại theo mã)."""
    insp = inspect(db.get_bind())
    if "cong_doan" not in insp.get_table_names():
        return
    if "bu_hao_id" not in _existing_columns(insp, "cong_doan"):
        db.execute(text("ALTER TABLE cong_doan ADD COLUMN bu_hao_id INTEGER"))
    db.execute(text(
        "UPDATE cong_doan SET kieu_bu_hao = 'khong' "
        "WHERE kieu_bu_hao IN ('theo_so_mau', 'theo_so_con')"
    ))
    db.commit()


def _migrate_redesign_formula_pricing(db: Session) -> None:
    """Add cong_thuc_gia to cong_doan, giay_nguyen, and vat_tu_in_an tables."""
    bind = db.get_bind()
    insp = inspect(bind)
    tables = insp.get_table_names()

    if "cong_doan" in tables:
        existing = _existing_columns(insp, "cong_doan")
        if "cong_thuc_gia" not in existing:
            db.execute(text("ALTER TABLE cong_doan ADD COLUMN cong_thuc_gia TEXT"))

    if "giay_nguyen" in tables:
        existing = _existing_columns(insp, "giay_nguyen")
        if "cong_thuc_gia" not in existing:
            db.execute(text("ALTER TABLE giay_nguyen ADD COLUMN cong_thuc_gia TEXT"))

    if "vat_tu_in_an" in tables:
        existing = _existing_columns(insp, "vat_tu_in_an")
        if "cong_thuc_gia" not in existing:
            db.execute(text("ALTER TABLE vat_tu_in_an ADD COLUMN cong_thuc_gia TEXT"))

    if "phieu_thanh_phan" in tables:
        existing = _existing_columns(insp, "phieu_thanh_phan")
        if "hao_so_to" not in existing:
            db.execute(text("ALTER TABLE phieu_thanh_phan ADD COLUMN hao_so_to INTEGER DEFAULT 0"))

    db.commit()


def _migrate_ptg_tinh_bu_hao_cd(db: Session) -> None:
    """Tính giá: thêm cột `phieu_thanh_phan.tinh_bu_hao_cd` (bật/TẮT tính bù hao công đoạn tự).
    Mặc định BẬT (TRUE). No-op trên DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    if "phieu_thanh_phan" not in insp.get_table_names():
        return
    if "tinh_bu_hao_cd" not in _existing_columns(insp, "phieu_thanh_phan"):
        db.execute(text(
            "ALTER TABLE phieu_thanh_phan ADD COLUMN tinh_bu_hao_cd BOOLEAN NOT NULL DEFAULT TRUE"
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
    ("0021_drop_quy_tac_binh_bai", _migrate_drop_quy_tac_binh_bai),
    ("0022_giay_chung_loai_and_vat_tu", _migrate_giay_chung_loai_and_vat_tu),
    ("0023_may_thiet_bi_plate_print_area", _migrate_may_thiet_bi_plate_print_area),
    ("0024_may_thiet_bi_ghi_chu_2", _migrate_may_thiet_bi_ghi_chu_2),
    ("0025_vat_tu_simplify", _migrate_vat_tu_simplify),
    ("0026_giay_open_fields", _migrate_giay_open_fields),
    ("0027_cong_doan_bu_hao_fields", _migrate_cong_doan_bu_hao_fields),
    ("0028_bu_hao_dynamic_bands", _migrate_bu_hao_dynamic_bands),
    ("0029_giay_version_no", _migrate_giay_version_no),
    ("0030_purchase_line_discount_vat", _migrate_purchase_line_discount_vat),
    ("0031_department_request_pending_approval_status", _migrate_department_request_pending_approval_status),
    ("0032_payment_voucher_amount_vnd", _migrate_payment_voucher_amount_vnd),
    ("0033_stock_moves_voucher", _migrate_stock_moves_voucher),
    ("0034_stock_moves_unit_cost", _migrate_stock_moves_unit_cost),
    ("0035_production_order_header_fields", _migrate_production_order_header_fields),
    ("0036_production_order_bu_fields", _migrate_production_order_bu_fields),
    ("0037_stock_count_phaseA", _migrate_stock_count_phaseA),
    ("0038_purchase_request_expected_receipt_date", _migrate_purchase_request_expected_receipt_date),
    ("0039_drop_payment_refunds_renamed", _migrate_drop_payment_refunds_renamed),
    ("0040_cong_doan_pricing_basis_v2", _migrate_cong_doan_pricing_basis_v2),
    ("0041_bu_hao_version_no", _migrate_bu_hao_versioning),
    ("0042_cong_doan_kieu_bu_hao", _migrate_cong_doan_kieu_bu_hao),
    ("0043_role_permission_edit_salary", _migrate_role_permission_edit_salary),
    ("0044_user_code_nv_to_tk", _migrate_user_code_nv_to_tk),
    ("0045_payroll_ot_night_bhxh_cap", _migrate_payroll_ot_night_bhxh_cap),
    ("0046_payroll_pit_2026", _migrate_payroll_pit_2026),
    ("0047_payroll_period_paid", _migrate_payroll_period_paid),
    ("0048_piece_batch_status", _migrate_piece_batch_status),
    ("0049_phieu_san_luong_5b1", _migrate_phieu_san_luong_5b1),
    ("0050_phieu_san_luong_5b2", _migrate_phieu_san_luong_5b2),
    ("0051_order_line_cost_snapshot", _migrate_order_line_cost_snapshot),
    ("0052_role_permission_approve_exception", _migrate_role_permission_approve_exception),
    ("0053_quote_phieu_tinh_gia_link", _migrate_quote_phieu_tinh_gia_link),
    ("0054_quote_bao_gia_fields", _migrate_quote_bao_gia_fields),
    ("0055_ptg_created_by", _migrate_ptg_created_by),
    ("0056_cong_doan_size_tiers", _migrate_cong_doan_size_tiers),
    ("0057_cong_doan_bu_hao_ref", _migrate_cong_doan_bu_hao_ref),
    ("0058_redesign_formula_pricing", _migrate_redesign_formula_pricing),
    ("0059_role_permission_set_credit_terms", _migrate_role_permission_set_credit_terms),
    ("0060_customer_kind_and_pricing_bounds", _migrate_customer_kind_and_pricing_bounds),
    ("0061_ptg_tinh_bu_hao_cd", _migrate_ptg_tinh_bu_hao_cd),
    ("0062_quote_decision_seen_at", _migrate_quote_decision_seen_at),
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
