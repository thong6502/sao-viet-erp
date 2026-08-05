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

import json
from datetime import datetime, timezone
from uuid import uuid4

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


def _migrate_may_nhip_giay(db: Session) -> None:
    """Bình bài: thêm `may_thiet_bi.nhip_giay_mm` — cạnh máy KẸP TỜ GIẤY (~8-12mm).

    KHÁC `gripper_mm` (mép nhíp trên BẢN KẼM, ~44mm) cả nghĩa lẫn độ lớn. Trước đây màn tính giá
    lấy nhầm nhíp kẽm làm chừa giấy → hụt 14-19% số con. Để trống = 0 = không trừ. No-op nếu đã có."""
    insp = inspect(db.get_bind())
    if "may_thiet_bi" not in insp.get_table_names():
        return
    if "nhip_giay_mm" not in _existing_columns(insp, "may_thiet_bi"):
        db.execute(text("ALTER TABLE may_thiet_bi ADD COLUMN nhip_giay_mm INTEGER"))
    db.commit()


def _migrate_ptg_so_mau_pha(db: Session) -> None:
    """Tính giá: thêm `phieu_thanh_phan.so_mau_pha` — số màu PHA (Pantone) nằm TRONG tổng số màu.

    Không cộng vào số kẽm (1 màu pha vẫn 1 kẽm, đã đếm ở so_mau_a/b). Ghi nhận để xưởng biết phải
    pha mực + rửa máy; engine phơi biến `so_mau_pha` cho công thức. No-op nếu đã có."""
    insp = inspect(db.get_bind())
    if "phieu_thanh_phan" not in insp.get_table_names():
        return
    if "so_mau_pha" not in _existing_columns(insp, "phieu_thanh_phan"):
        db.execute(text(
            "ALTER TABLE phieu_thanh_phan ADD COLUMN so_mau_pha INTEGER NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_ptg_so_trang(db: Session) -> None:
    """Tính giá: thêm `phieu_thanh_phan.so_trang` + `trang_moi_tay` — số trang NỘI DUNG của 1 sản
    phẩm và số trang mỗi tay gấp. Người dùng khai và LƯU (trước đây popover tính xong là mất, chỉ
    còn lại kết quả `so_to_per_sp` nên mở lại không biết đã tính từ đâu).

    Số tờ in nay tính thẳng từ số trang: `SL × so_trang / con` thay cho `SL × số bài in / con`.
    Công thức cũ chia "số tay" cho "số con" — hai đại lượng khác đơn vị — nên sách bình tay ra sai.
    Dữ liệu cũ: so_trang = trang_moi_tay = 1 (mặc định) ⇒ mọi phiếu TỜ RỜI đang có giữ NGUYÊN số
    tờ như trước (`SL × 1 / con` = `SL × 1 / con`). Phiếu sách phải khai lại số trang. No-op nếu
    đã có."""
    insp = inspect(db.get_bind())
    if "phieu_thanh_phan" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "phieu_thanh_phan")
    if "so_trang" not in cols:
        db.execute(text(
            "ALTER TABLE phieu_thanh_phan ADD COLUMN so_trang INTEGER NOT NULL DEFAULT 1"))
    if "trang_moi_tay" not in cols:
        db.execute(text(
            "ALTER TABLE phieu_thanh_phan ADD COLUMN trang_moi_tay INTEGER NOT NULL DEFAULT 1"))
    db.commit()


def _migrate_lsx_cong_doan_giao_nhan_thuc(db: Session) -> None:
    """Thuê ngoài: sổ GIAO – NHẬN THỰC TẾ trên chính bước lệnh (không đẻ bảng).

    Khối gia công ngoài trước nay toàn số DỰ KIẾN; hàng ra khỏi cổng không có tên người giao,
    người nhận, số thực gửi/nhận — trễ thì không truy được, thiếu thì không ai nhận.

    `nguoi_giao_nhan_id` (một người cho cả hai đầu việc) ĐỔI TÊN thành `nguoi_giao_id`: giao và
    nhận là HAI sự kiện, khác ngày khác người khác số lượng. Cột cũ chưa từng lên UI nên chắc
    chắn toàn NULL — đổi tên rẻ hơn là thêm cột thứ ba rồi bỏ cột cũ chết ở đó.

    KHÔNG thêm cột số hỏng (`= sl_giao_thuc - sl_nhan_thuc`), trạng thái (suy từ hai mốc thời
    gian) hay tiền gia công thực (`= sl_nhan_thuc × don_gia_gia_cong`) — đều là dẫn xuất.

    Idempotent; no-op trên DB fresh (create_all đã ra tên mới) và DB chưa có bảng."""
    insp = inspect(db.get_bind())
    if "lsx_cong_doan" not in insp.get_table_names():
        return

    def run(sql: str) -> None:
        """Best-effort DDL: SQLite cũ từ chối RENAME COLUMN thì đừng làm vỡ cả migration."""
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    cols = _existing_columns(insp, "lsx_cong_doan")
    if "nguoi_giao_nhan_id" in cols and "nguoi_giao_id" not in cols:
        run("ALTER TABLE lsx_cong_doan RENAME COLUMN nguoi_giao_nhan_id TO nguoi_giao_id")

    cols = _existing_columns(inspect(db.get_bind()), "lsx_cong_doan")
    for name, ddl in (
        ("nguoi_giao_id", "INTEGER"),          # đường lui nếu RENAME bị từ chối
        ("giao_luc", "TIMESTAMP"),
        ("sl_giao_thuc", "NUMERIC(14,2)"),
        ("nguoi_nhan_id", "INTEGER"),
        ("nhan_luc", "TIMESTAMP"),
        ("sl_nhan_thuc", "NUMERIC(14,2)"),
    ):
        if name not in cols:
            db.execute(text(f"ALTER TABLE lsx_cong_doan ADD COLUMN {name} {ddl}"))
    db.commit()
    run("CREATE INDEX IF NOT EXISTS ix_lsx_cong_doan_nguoi_giao_id "
        "ON lsx_cong_doan (nguoi_giao_id)")
    run("CREATE INDEX IF NOT EXISTS ix_lsx_cong_doan_nguoi_nhan_id "
        "ON lsx_cong_doan (nguoi_nhan_id)")


def _migrate_bai_ghep_buoc_in_step_key(db: Session) -> None:
    """Bài ghép neo ĐÍCH DANH bước in nào của thành viên chạy chung tờ.

    Trước nay nhận diện bằng quy ước ngầm `nhom == "print" and loai_buoc == "may"`. Quy ước đó
    đủ dùng khi mỗi lệnh có ĐÚNG MỘT bước in máy, nhưng lệnh in 2 lượt (mặt trước / mặt sau tách
    dòng, in nền + màu pha) thì `bo_qua_in` bỏ SẠCH mọi bước print — cả hai lượt biến mất khỏi
    board, thay bằng một dòng in ghép.

    Neo bằng `step_key` chứ KHÔNG phải `id`: `replace_routing` khớp hàng cũ bằng
    `{r.step_key: r}` nên step_key sống qua mọi lần lưu routing, còn id thì hàng dựng lại sinh id
    mới. (Quyết định cũ "bài ghép neo LSX, không neo công đoạn" đúng với id, không đúng với
    step_key.)

    Backfill: điền bước in đầu tiên cho thành viên đã có — lệnh một lượt in thì đúng luôn."""
    insp = inspect(db.get_bind())
    if "bai_ghep_thanh_vien" not in insp.get_table_names():
        return
    if "buoc_in_step_key" not in _existing_columns(insp, "bai_ghep_thanh_vien"):
        db.execute(text(
            "ALTER TABLE bai_ghep_thanh_vien ADD COLUMN buoc_in_step_key VARCHAR(40)"))
        db.commit()
    if "lsx_cong_doan" not in insp.get_table_names():
        return
    db.execute(text(
        "UPDATE bai_ghep_thanh_vien SET buoc_in_step_key = ("
        "  SELECT cd.step_key FROM lsx_cong_doan cd"
        "  WHERE cd.lsx_id = bai_ghep_thanh_vien.lsx_id"
        "    AND cd.nhom = 'print' AND cd.loai_buoc = 'may'"
        "  ORDER BY cd.thu_tu LIMIT 1)"
        " WHERE buoc_in_step_key IS NULL"
    ))
    db.commit()


def _migrate_don_vi_khau_sach(db: Session) -> None:
    """Khâu sách: `Gấp tay sách` và `Bắt tay + vào keo` đang khai `cái → cái` (mặc định của model,
    seed không khai đơn vị nên rơi vào đó).

    Gấp tay là gấp cả TỜ IN — một tờ thành một tay; vào keo mới là chỗ gom `số tay` tờ thành MỘT
    cuốn. Khai `cái → cái` thì chuỗi bù hao ngược không thấy ranh giới tờ↔cuốn nào để áp hệ số,
    chạy 1:1 từ cuốn xuống tận bước in → số giấy phải mua hụt đúng bằng số tay mỗi cuốn (sách 160
    trang tay 16 thì hụt 10 lần). No-op nếu mã không tồn tại hoặc đã khai đúng."""
    insp = inspect(db.get_bind())
    if "cong_doan" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "cong_doan")
    if "don_vi_vao" not in cols or "don_vi_ra" not in cols:
        return   # chưa chạy 0143 → không có gì để sửa
    for ma, dv_vao, dv_ra in (("CD-0007", "to", "to"), ("CD-0008", "to", "cai")):
        db.execute(
            text("UPDATE cong_doan SET don_vi_vao = :v, don_vi_ra = :r WHERE ma = :m"),
            {"v": dv_vao, "r": dv_ra, "m": ma},
        )
    db.commit()


def _migrate_ptg_nhom_bao_gia(db: Session) -> None:
    """Tính giá: thêm `phieu_thanh_phan.nhom_bao_gia` — nhãn GỘP DÒNG KHI BÁO GIÁ.

    Ruột + bìa của cùng 1 cuốn gõ chung nhãn → báo giá in ra 1 dòng "quyển sách" thay vì 2 dòng
    rời. Chỉ ảnh hưởng báo giá: tính giá vẫn tách từng dòng, sản xuất vẫn tách lệnh. Nullable
    (trống = không gộp) nên không cần default. No-op nếu đã có."""
    insp = inspect(db.get_bind())
    if "phieu_thanh_phan" not in insp.get_table_names():
        return
    if "nhom_bao_gia" not in _existing_columns(insp, "phieu_thanh_phan"):
        db.execute(text("ALTER TABLE phieu_thanh_phan ADD COLUMN nhom_bao_gia VARCHAR(120)"))
    db.commit()


def _migrate_quote_item_nhom(db: Session) -> None:
    """Báo giá: thêm `quote_items.nhom` — nhãn nhóm ĐÔNG CỨNG từ `phieu_thanh_phan.nhom_bao_gia`
    lúc sinh dòng (giống `dien_giai`), vì id thành phần đổi mỗi lần lưu PTG nên không đọc-sống
    được. Bản in báo giá gom các dòng cùng nhãn thành 1 dòng. No-op nếu đã có."""
    insp = inspect(db.get_bind())
    if "quote_items" not in insp.get_table_names():
        return
    if "nhom" not in _existing_columns(insp, "quote_items"):
        db.execute(text("ALTER TABLE quote_items ADD COLUMN nhom VARCHAR(120)"))
    db.commit()


def _migrate_order_line_nhom(db: Session) -> None:
    """Đơn hàng: thêm `order_lines.nhom` — copy từ dòng báo giá khi chốt đơn, để bản in xác nhận
    đơn gom dòng giống hệt bản báo giá (khách nhận 2 chứng từ khớp nhau). KHÔNG ảnh hưởng sản
    xuất: lệnh vẫn sinh theo TỪNG dòng đơn. No-op nếu đã có."""
    insp = inspect(db.get_bind())
    if "order_lines" not in insp.get_table_names():
        return
    if "nhom" not in _existing_columns(insp, "order_lines"):
        db.execute(text("ALTER TABLE order_lines ADD COLUMN nhom VARCHAR(120)"))
    db.commit()


def _migrate_ptg_bleed_khe_cat(db: Session) -> None:
    """Tính giá: thêm `phieu_thanh_phan.bleed_mm` + `khe_cat_mm` (mm) — bình bài đúng kích thước con.

    bleed = tràn lề MỖI CẠNH con (0 = không tràn lề); khe_cat = khe giữa 2 con kề nhau
    (0 = bình sát, cắt chung nhát). Sale nhập trên phiếu. No-op nếu đã có."""
    insp = inspect(db.get_bind())
    if "phieu_thanh_phan" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "phieu_thanh_phan")
    for col in ("bleed_mm", "khe_cat_mm"):
        if col not in cols:
            db.execute(text(
                f"ALTER TABLE phieu_thanh_phan ADD COLUMN {col} NUMERIC(10,2) NOT NULL DEFAULT 0"))
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


def _migrate_cong_doan_don_vi(db: Session) -> None:
    """Công đoạn: KHAI `don_vi_vao` / `don_vi_ra` thay vì đoán theo tên.

    Dòng giấy đi qua BA đơn vị với HAI điểm quy đổi (tờ nguyên → tờ in → tờ thành phẩm). Trước đây
    chữ `to` gộp cả tờ nguyên lẫn tờ in, và `lsx_service` phải dò chữ "bế"/"cấn" trong TÊN công
    đoạn để suy ra bước đổi đơn vị — đặt tên lạ là suy sai, mà tầng tính giá thì không suy gì cả
    nên tra bù hao sai đơn vị. Hệ số quy đổi KHÔNG lưu: phiếu đã có `con` + `so_manh_xa`.

    Cũng NỚI `lsx_cong_doan.don_vi_vao/ra` từ VARCHAR(8) → VARCHAR(12): mã mới `to_nguyen` dài 9,
    Postgres sẽ ném lỗi độ dài lúc ghi (SQLite không ép nên test không bắt được).

    Backfill một lần theo đúng luật tên mà `lsx_service` đang dùng, để lệnh SX đang chạy không tính
    sai ngay sau khi deploy; từ đó runtime CHỈ đọc cột, không còn đoán.
    """
    bind = db.get_bind()
    insp = inspect(bind)
    is_pg = (bind.dialect.name or "").startswith("postgres")
    tables = insp.get_table_names()

    if "cong_doan" in tables:
        existing = _existing_columns(insp, "cong_doan")
        for col in ("don_vi_vao", "don_vi_ra"):
            if col not in existing:
                # NULL được phép = bước KHÔNG CHẠM GIẤY. Cho DEFAULT 'to' để dòng cũ có giá trị,
                # rồi bỏ default + gỡ NULL constraint ngay bên dưới.
                db.execute(text(
                    f"ALTER TABLE cong_doan ADD COLUMN {col} VARCHAR(12) DEFAULT 'to'"
                ))
        db.commit()
        db.execute(text("UPDATE cong_doan SET don_vi_vao = 'to' WHERE don_vi_vao IS NULL"))
        db.execute(text("UPDATE cong_doan SET don_vi_ra = 'to' WHERE don_vi_ra IS NULL"))
        # Backfill: bế/cấn = ranh giới tờ in → tờ thành phẩm.
        db.execute(text(
            "UPDATE cong_doan SET don_vi_vao = 'to', don_vi_ra = 'cai' "
            "WHERE don_vi_ra = 'to' AND ("
            "  lower(ten) LIKE '%bế%' OR lower(ten) LIKE '%be %' OR lower(ten) LIKE '%cấn%')"
        ))
        # Chế bản KHÔNG nằm trên dòng giấy (nhả kẽm, không nhả tờ) → để TRỐNG. Lệnh sản xuất tự
        # suy ra kẽm từ `nhom`; danh mục không đẻ mã đơn vị riêng chỉ để phục vụ một khâu.
        db.execute(text(
            "UPDATE cong_doan SET don_vi_vao = NULL, don_vi_ra = NULL WHERE nhom = 'prepress'"
        ))
        # Nhánh còn lại của luật cũ: các bước ĐẾM CON (dán, gấp, đóng gói, xén thành phẩm…). Thứ tự
        # phải sau nhánh bế — "Bế thành phẩm" khớp CẢ HAI, luật cũ cho bế thắng.
        _dem_con = ("dán", "gấp", "đóng gói", "cắt thành phẩm", "kcs", "thùng", "bao bì",
                    "vào bìa", "đóng cuốn", "thành phẩm", "nhập kho")
        _like = " OR ".join(f"lower(ten) LIKE '%{k}%'" for k in _dem_con)
        db.execute(text(
            "UPDATE cong_doan SET don_vi_vao = 'cai', don_vi_ra = 'cai' "
            "WHERE nhom NOT IN ('prepress', 'print') "
            f"AND don_vi_vao = 'to' AND don_vi_ra = 'to' AND ({_like})"
        ))
        db.commit()

    # Bỏ DEFAULT của `cong_doan` (giá trị mặc định là việc của form, không phải của DB) — chỉ
    # Postgres; SQLite không ALTER được cột nên để nguyên, vô hại vì model đã nullable.
    if is_pg and "cong_doan" in tables:
        for col in ("don_vi_vao", "don_vi_ra"):
            db.execute(text(f"ALTER TABLE cong_doan ALTER COLUMN {col} DROP DEFAULT"))
        db.commit()

    # Nới độ dài cột bên bảng bước lệnh. SQLite lưu VARCHAR(n) như TEXT (không ép) → chỉ Postgres.
    if is_pg and "lsx_cong_doan" in tables:
        for col in ("don_vi_vao", "don_vi_ra"):
            db.execute(text(f"ALTER TABLE lsx_cong_doan ALTER COLUMN {col} TYPE VARCHAR(12)"))
        db.commit()


def _migrate_ptg_drop_kho_tp_mo_rong_tay_gap(db: Session) -> None:
    """Bỏ 3 cột khỏi sản phẩm của phiếu: `kho_thanh_pham` · `kho_mo_rong` · `tay_gap`.

    Ô nhập của cả ba đã gỡ khỏi màn phiếu tính giá từ 2026-07-29; từ đó cột chỉ còn được chép qua
    chép lại, phiếu mới luôn rỗng — nhưng bản Lệnh sản xuất vẫn vẽ ba dòng "Khổ thành phẩm / Khổ
    mở rộng / Tay gấp" nên người đọc tưởng phiếu có khai mà thực ra là "—".

    MẤT GÌ: phiếu cũ có `kho_thanh_pham` dạng nhãn chữ ("14,5×20,5 cm (A5)", "30×20,5 cm (khổ
    mở)") — phần SỐ trùng hoàn toàn với `dai_thanh_pham`/`rong_thanh_pham` (mm) vẫn còn, chỉ mất
    chú thích trong ngoặc. `kho_mo_rong`/`tay_gap` rỗng ở mọi dòng.

    Lệnh SX cũ giữ nguyên nhãn đó trong `quy_cach_json` (JSON không bị migration đụng), chỉ là màn
    lệnh thôi vẽ ra.

    KHÔNG đụng `phieu_tinh_gia.kho_thanh_pham` (cấp phiếu, cột khác) — nó nằm ngoài phạm vi chốt.

    Best-effort mỗi câu (SQLite cũ có thể từ chối DROP COLUMN → cột mồ côi vô hại vì model không
    map). No-op trên DB fresh."""
    insp = inspect(db.get_bind())
    if "phieu_thanh_phan" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "phieu_thanh_phan")
    for c in ("kho_thanh_pham", "kho_mo_rong", "tay_gap"):
        if c not in cols:
            continue
        try:
            db.execute(text(f"ALTER TABLE phieu_thanh_phan DROP COLUMN {c}"))
            db.commit()
        except Exception:
            db.rollback()


def _migrate_lsx_cong_doan_don_vi_nullable(db: Session) -> None:
    """Bước lệnh: `don_vi_vao`/`don_vi_ra` cho phép NULL = bước KHÔNG CHẠM GIẤY.

    Đơn vị bước nay KẾ THỪA từ `cong_doan` và chỉ có 3 mức của dòng giấy (`to_nguyen` → `to` →
    `cai`). Bước chế bản đếm kẽm — không nằm trên dòng giấy — nên để TRỐNG, thay vì rơi về `to`
    rồi hiện "4 tờ → 4 tờ" (số 4 là số KẼM).

    `DROP NOT NULL` là Postgres-only: SQLite không ép nên pytest xanh dù chưa chạy — phải kiểm
    bằng `psql`.
    """
    bind = db.get_bind()
    insp = inspect(bind)
    if "lsx_cong_doan" not in insp.get_table_names():
        return
    if (bind.dialect.name or "").startswith("postgres"):
        for col in ("don_vi_vao", "don_vi_ra"):
            db.execute(text(f"ALTER TABLE lsx_cong_doan ALTER COLUMN {col} DROP NOT NULL"))
            db.execute(text(f"ALTER TABLE lsx_cong_doan ALTER COLUMN {col} DROP DEFAULT"))
        db.commit()
    # Bước thuộc công đoạn chế bản → về TRỐNG. Dùng `nhom` của chính dòng bước (đã chụp lúc tạo)
    # để khỏi phụ thuộc công đoạn còn sống hay đã xoá.
    db.execute(text("UPDATE lsx_cong_doan SET don_vi_vao = NULL, don_vi_ra = NULL "
                    "WHERE nhom = 'prepress'"))
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


def _migrate_drop_piece_batches_khoan_theo_nguoi(db: Session) -> None:
    """Bỏ tầng "sổ khoán": DROP piece_batches + entries + shares. Lương khoán giờ = Phiếu sản lượng
    THEO NGƯỜI cộng thẳng vào cột `khoan` (không quỹ/hệ số/chốt sổ). Đổi công đoạn khoán 'theo tổ'
    → 'theo người'. No-op trên DB fresh (models đã bỏ 3 bảng → create_all không dựng)."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    # DROP con trước (FK → piece_batches) rồi tới bảng cha.
    for t in ("piece_batch_entries", "piece_batch_shares", "piece_batches"):
        if t in tables:
            db.execute(text(f"DROP TABLE {t}"))
    if "cong_doan" in tables and "khoan_ghi_theo" in _existing_columns(insp, "cong_doan"):
        db.execute(text("UPDATE cong_doan SET khoan_ghi_theo = 'nguoi' WHERE khoan_ghi_theo = 'to'"))
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


def _migrate_quote_deposit_pct(db: Session) -> None:
    """% tạm ứng/cọc nhập ở màn Báo giá (0–100, nullable). No-op nếu cột đã có."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "quotes" in tables and "deposit_pct" not in _existing_columns(insp, "quotes"):
        db.execute(text("ALTER TABLE quotes ADD COLUMN deposit_pct FLOAT"))
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


def _migrate_ptg_kho_nguyen_override(db: Session) -> None:
    """Tính giá: thêm 2 cột `phieu_thanh_phan.kho_nguyen_dai/rong` (mm) — cho ĐÈ khổ giấy nguyên ①
    ngay trên phiếu (đặt hàng xả khổ khác danh mục). 0 = lấy theo danh mục Giấy. No-op nếu đã có."""
    insp = inspect(db.get_bind())
    if "phieu_thanh_phan" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "phieu_thanh_phan")
    for col in ("kho_nguyen_dai", "kho_nguyen_rong"):
        if col not in cols:
            db.execute(text(f"ALTER TABLE phieu_thanh_phan ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_payroll_special_day_multipliers(db: Session) -> None:
    """Pha 4d (Đ98): hệ số làm thêm/làm ngày đặc biệt trong `payroll_params`.
    OT ngày nghỉ tuần ×2, OT ngày lễ ×3; làm nguyên công nghỉ tuần ×2, lễ ×3. No-op nếu đã có."""
    insp = inspect(db.get_bind())
    if "payroll_params" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "payroll_params")
    for col, default in (("ot_multiplier_restday", "2"), ("ot_multiplier_holiday", "3"),
                         ("restday_work_multiplier", "2"), ("holiday_work_multiplier", "3")):
        if col not in cols:
            db.execute(text(
                f"ALTER TABLE payroll_params ADD COLUMN {col} NUMERIC(5,2) NOT NULL DEFAULT {default}"))
    db.commit()


def _migrate_attendance_line_special_day(db: Session) -> None:
    """Pha 4d (Đ98): snapshot công/OT theo LOẠI NGÀY vào `attendance_period_lines` (đóng băng lúc
    Chốt công để Lương trả premium sau khi đã chốt). No-op nếu đã có."""
    insp = inspect(db.get_bind())
    if "attendance_period_lines" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "attendance_period_lines")
    for col, typ in (("holiday_cong", "NUMERIC(6,2)"), ("restday_cong", "NUMERIC(6,2)"),
                     ("ot_holiday_minutes", "INTEGER"), ("ot_restday_minutes", "INTEGER")):
        if col not in cols:
            db.execute(text(
                f"ALTER TABLE attendance_period_lines ADD COLUMN {col} {typ} NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_attendance_line_plain_cong(db: Session) -> None:
    """Ngày nghỉ 'off1x' (chủ 25/07/2026): công LÀM ngày đó trả 1× (không hệ số). Snapshot vào
    `attendance_period_lines.plain_cong` để Lương trả sau khi chốt. No-op nếu đã có."""
    insp = inspect(db.get_bind())
    if "attendance_period_lines" not in insp.get_table_names():
        return
    if "plain_cong" not in _existing_columns(insp, "attendance_period_lines"):
        db.execute(text(
            "ALTER TABLE attendance_period_lines ADD COLUMN plain_cong NUMERIC(6,2) NOT NULL DEFAULT 0"))
        db.commit()


def _migrate_attendance_line_paid_leave_fraction(db: Session) -> None:
    """Phiếu nghỉ NỬA BUỔI có trừ phép (chủ 27/07/2026) ⇒ `paid_leave_days` phải chứa 0,5.
    SQLite không ALTER kiểu cột được, nhưng nó lưu kiểu động nên cột INTEGER cũ vẫn nhận 0.5 —
    chỉ Postgres mới cần đổi thật. Idempotent, no-op nếu đã là NUMERIC hoặc bảng chưa có."""
    insp = inspect(db.get_bind())
    if "attendance_period_lines" not in insp.get_table_names():
        return
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(text(
        "ALTER TABLE attendance_period_lines "
        "ALTER COLUMN paid_leave_days TYPE NUMERIC(6,2) USING paid_leave_days::numeric"))
    db.commit()


def _migrate_payroll_line_luong_ngay_phep(db: Session) -> None:
    """Ngày nghỉ phép năm chỉ trả LƯƠNG VỊ TRÍ (chủ 27/07/2026). `luong_ngay_phep` là số TRONG ĐÓ
    của `luong_cong` (đừng cộng vào gross); 2 cột công đi kèm để giải trình. No-op nếu đã có."""
    insp = inspect(db.get_bind())
    if "payroll_lines" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "payroll_lines")
    if "luong_ngay_phep" not in cols:
        db.execute(text(
            "ALTER TABLE payroll_lines ADD COLUMN luong_ngay_phep NUMERIC(14,2) NOT NULL DEFAULT 0"))
    for name in ("paid_leave_cong", "excused_cong"):
        if name not in cols:
            db.execute(text(
                f"ALTER TABLE payroll_lines ADD COLUMN {name} NUMERIC(6,2) NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_attendance_line_excused_cong(db: Session) -> None:
    """Nghỉ theo GIỜ có đơn (chủ 27/07/2026): phần công thiếu ĐƯỢC PHÉP, snapshot để phụ cấp
    chuyên cần không bị trừ sau khi chốt công. No-op nếu đã có."""
    insp = inspect(db.get_bind())
    if "attendance_period_lines" not in insp.get_table_names():
        return
    if "excused_cong" not in _existing_columns(insp, "attendance_period_lines"):
        db.execute(text(
            "ALTER TABLE attendance_period_lines ADD COLUMN excused_cong NUMERIC(6,2) NOT NULL DEFAULT 0"))
        db.commit()


def _migrate_order_redesign_fields(db: Session) -> None:
    """Redesign Đơn hàng bán (P1, redesign-don-hang-ban.md): thêm cột mới vào `orders`
    (nguồn/bản chất/đặt hàng/duyệt/chốt/hủy). Chỉ ADD COLUMN với default
    an toàn (đơn cũ giữ nghĩa: source_type='bao_gia', order_nature='hang_hoa', approval_state='none').
    Bảng cọc `order_deposits`(+attachments) là bảng MỚI → create_all tự tạo, không ALTER ở đây.
    No-op trên DB fresh / bảng chưa có."""
    insp = inspect(db.get_bind())
    if "orders" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "orders")
    order_cols = [
        ("source_type", "VARCHAR(16) NOT NULL DEFAULT 'bao_gia'"),
        ("order_nature", "VARCHAR(16) NOT NULL DEFAULT 'hang_hoa'"),
        ("customer_po_no", "VARCHAR(100)"),
        ("delivery_committed_date", "DATE"),
        ("delivery_address", "VARCHAR(500)"),
        ("invoice_entity_name", "VARCHAR(255)"),
        ("invoice_entity_tax_code", "VARCHAR(20)"),
        ("deposit_pct", "FLOAT"),
        ("cost_basis", "VARCHAR(16) NOT NULL DEFAULT 'quote'"),
        ("needs_approval", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("approval_state", "VARCHAR(16) NOT NULL DEFAULT 'none'"),
        ("ordered_at", "TIMESTAMP WITH TIME ZONE"),
        ("ordered_by", "INTEGER"),
        ("cancel_by", "INTEGER"),
        ("cancel_at", "TIMESTAMP WITH TIME ZONE"),
        ("cancel_fault", "VARCHAR(16)"),
    ]
    for name, ddl in order_cols:
        if name not in cols:
            db.execute(text(f"ALTER TABLE orders ADD COLUMN {name} {ddl}"))
    db.commit()


def _migrate_role_permission_record_deposit(db: Session) -> None:
    """don_hang_ban: thêm cột `role_permissions.can_record_deposit` (Kế toán ghi phiếu thu cọc).
    Chỉ ADD COLUMN DEFAULT FALSE — quyền do seed_roles upsert lại mỗi khởi động. No-op DB fresh."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    if "can_record_deposit" not in _existing_columns(insp, "role_permissions"):
        db.execute(text(
            "ALTER TABLE role_permissions ADD COLUMN can_record_deposit BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    db.commit()


def _migrate_role_permission_assign_work(db: Session) -> None:
    """san_xuat: thêm cột `role_permissions.can_assign_work` (tổ trưởng gán thợ vào công đoạn).
    Chỉ ADD COLUMN DEFAULT FALSE — quyền do seed_roles upsert lại mỗi khởi động. No-op DB fresh."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    if "can_assign_work" not in _existing_columns(insp, "role_permissions"):
        db.execute(text(
            "ALTER TABLE role_permissions ADD COLUMN can_assign_work BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    db.commit()


def _migrate_role_permission_output_handover(db: Session) -> None:
    """san_xuat (Lát 2): thêm `role_permissions.can_record_output` (ghi sản lượng đạt/hỏng) +
    `can_handover` (bàn giao + xác nhận nhận). Chỉ ADD COLUMN DEFAULT FALSE — quyền do seed upsert
    lại mỗi khởi động. No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "role_permissions")
    if "can_record_output" not in cols:
        db.execute(text(
            "ALTER TABLE role_permissions ADD COLUMN can_record_output BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    if "can_handover" not in cols:
        db.execute(text(
            "ALTER TABLE role_permissions ADD COLUMN can_handover BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    db.commit()


def _migrate_department_salary_policy(db: Session) -> None:
    """departments: bộ nguyên tắc lương của phòng (Pha 1) — cơ chế ra mức lương
    (`salary_mechanism`), % thử việc (`probation_ratio`), cờ có lương khoán
    (`has_piece_work`). Chỉ ADD COLUMN DEFAULT — idempotent, no-op trên DB fresh."""
    insp = inspect(db.get_bind())
    if "departments" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "departments")
    for name, ddl in (
        ("salary_mechanism", "VARCHAR(24) NOT NULL DEFAULT 'cung'"),
        ("probation_ratio", "NUMERIC(5,4) NOT NULL DEFAULT 0.80"),
        ("has_piece_work", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ):
        if name not in cols:
            db.execute(text(f"ALTER TABLE departments ADD COLUMN {name} {ddl}"))
    db.commit()


def _migrate_probation_ratio_80(db: Session) -> None:
    """Công ty dùng thử việc 80% (không phải 85% mặc định BLLĐ). Hạ dòng `payroll_params`
    còn để đúng mặc định cũ 0.85 xuống 0.80. Guard `= 0.85` để KHÔNG đè giá trị chủ đã
    tự chỉnh; idempotent, no-op trên DB fresh (create_all đã dựng default 0.80)."""
    insp = inspect(db.get_bind())
    if "payroll_params" not in insp.get_table_names():
        return
    db.execute(text("UPDATE payroll_params SET probation_ratio = 0.80 WHERE probation_ratio = 0.85"))
    db.commit()


def _migrate_employee_salary_source_row(db: Session) -> None:
    """employee_salaries: trỏ tới 1 dòng bảng lương của tổ (`source_salary_row_id`) — khi
    gán NV, chọn 1 dòng `department_salary_rows`; engine đọc SỐNG dòng đó. Chỉ ADD COLUMN
    nullable — idempotent, no-op trên DB fresh (create_all đã dựng cột)."""
    insp = inspect(db.get_bind())
    if "employee_salaries" not in insp.get_table_names():
        return
    if "source_salary_row_id" not in _existing_columns(insp, "employee_salaries"):
        db.execute(text("ALTER TABLE employee_salaries ADD COLUMN source_salary_row_id INTEGER"))
    db.commit()


def _migrate_employee_salary_chuyen_can(db: Session) -> None:
    """employee_salaries: chuyên cần theo TỪNG NGƯỜI (mỗi người mỗi khác) — tách khỏi bảng
    lương của tổ. Phụ cấp dùng lại cột `allowance` sẵn có. Chỉ ADD COLUMN NOT NULL DEFAULT 0
    — idempotent, no-op trên DB fresh."""
    insp = inspect(db.get_bind())
    if "employee_salaries" not in insp.get_table_names():
        return
    if "chuyen_can" not in _existing_columns(insp, "employee_salaries"):
        db.execute(text("ALTER TABLE employee_salaries ADD COLUMN chuyen_can NUMERIC(14,2) NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_payslip_detail_items(db: Session) -> None:
    """Phiếu lương chi tiết (Pha 4d): tách riêng từng khoản thưởng/phạt trên dòng lương +
    đoàn phí công đoàn (`payroll_lines`) + tỷ lệ công đoàn (`payroll_params`). Chỉ ADD COLUMN
    NUMERIC NOT NULL DEFAULT 0 — idempotent, no-op trên DB fresh."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "payroll_lines" in tables:
        cols = _existing_columns(insp, "payroll_lines")
        for name in ("thuong_5s", "thuong_doanh_so", "thuong_thanh_tich", "phep_nam",
                     "tra_dong_phuc", "dieu_chinh_luong", "di_tre", "dt_vuot_troi",
                     "phat_bien_ban", "phat_5s_dong_phuc", "cong_doan"):
            if name not in cols:
                db.execute(text(f"ALTER TABLE payroll_lines ADD COLUMN {name} NUMERIC(14,2) NOT NULL DEFAULT 0"))
    if "payroll_params" in tables:
        if "cong_doan_rate" not in _existing_columns(insp, "payroll_params"):
            db.execute(text("ALTER TABLE payroll_params ADD COLUMN cong_doan_rate NUMERIC(6,4) NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_salary_advance_code(db: Session) -> None:
    """salary_advances: thêm MÃ tạm ứng (TU26-xxxx, sinh khi tạo). ADD COLUMN nullable + backfill
    hàng cũ `TU-<id>` (định dạng LEGACY, khác format sinh mã → không đụng mã mới) + unique index
    khớp create_all. Idempotent, no-op trên DB fresh."""
    insp = inspect(db.get_bind())
    if "salary_advances" not in insp.get_table_names():
        return
    if "code" not in _existing_columns(insp, "salary_advances"):
        db.execute(text("ALTER TABLE salary_advances ADD COLUMN code VARCHAR(32)"))
        db.execute(text("UPDATE salary_advances SET code = 'TU-' || id WHERE code IS NULL"))
        db.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_salary_advances_code ON salary_advances (code)"
        ))
    db.commit()


def _migrate_payment_doc_no_and_accounts(db: Session) -> None:
    """Kế toán — in theo mẫu Bộ Tài chính (TT 200/2014/TT-BTC):

    - `doc_no`: số IN trên phiếu (PC00445 / PT00027), chạy LIÊN TỤC không reset theo năm
      (bộ đếm `document_sequences` với year = SEQ_YEAR_GLOBAL). Phiếu CŨ được đánh số bổ
      sung theo thứ tự id, rồi nhấc bộ đếm lên đúng mức để phiếu mới nối tiếp.
    - `debit_account` / `credit_account`: định khoản Nợ/Có nhập tay (cả 2 bảng).
    - `payer_address`: địa chỉ người nộp (mẫu 01-TT), chỉ ở phiếu thu.

    Idempotent KHÔNG dựa vào `schema_migrations` (test gọi hàm 2 lần): guard bằng
    `_existing_columns` + `IF NOT EXISTS` + `WHERE doc_no IS NULL`. No-op trên DB fresh
    (create_all đã dựng đủ cột + index; bảng rỗng nên không seed bộ đếm).
    """
    from .models.document_sequence import (
        SEQ_DOC_TYPE_PAYMENT_RECEIPT,
        SEQ_DOC_TYPE_PAYMENT_VOUCHER,
        SEQ_YEAR_GLOBAL,
    )

    insp = inspect(db.get_bind())
    names = set(insp.get_table_names())

    specs = [
        ("payment_vouchers", SEQ_DOC_TYPE_PAYMENT_VOUCHER, "PC"),
        ("payment_receipts", SEQ_DOC_TYPE_PAYMENT_RECEIPT, "PT"),
    ]
    coldefs = {
        "doc_no": "VARCHAR(16)",
        "debit_account": "VARCHAR(64)",
        "credit_account": "VARCHAR(64)",
    }

    for table, _doc_type, _prefix in specs:
        if table not in names:
            continue
        existing = _existing_columns(insp, table)
        for name, ddl in coldefs.items():
            if name not in existing:
                db.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        if table == "payment_receipts" and "payer_address" not in existing:
            db.execute(text("ALTER TABLE payment_receipts ADD COLUMN payer_address VARCHAR(500)"))
        db.commit()  # đóng đợt DDL trước khi tạo index / chạy DML (gotcha pysqlite)
        # ALTER ADD COLUMN KHÔNG tạo index — phải tạo riêng, tên khớp create_all.
        db.execute(
            text(f"CREATE UNIQUE INDEX IF NOT EXISTS ix_{table}_doc_no ON {table} (doc_no)")
        )
        db.commit()

    if "document_sequences" not in names:
        return  # chưa có bộ đếm (DB rất cũ) — phiếu mới sẽ tự tạo khi lập

    for table, doc_type, prefix in specs:
        if table not in names:
            continue
        ids = [
            row[0]
            for row in db.execute(
                text(f"SELECT id FROM {table} WHERE doc_no IS NULL ORDER BY id")
            ).all()
        ]
        if not ids:
            continue  # DB fresh/không có phiếu cũ → KHÔNG tạo dòng counter (giữ PC00001)
        start = db.execute(
            text(
                "SELECT current_number FROM document_sequences "
                "WHERE doc_type = :t AND year = :y"
            ),
            {"t": doc_type, "y": SEQ_YEAR_GLOBAL},
        ).scalar()
        next_number = int(start or 0)
        for row_id in ids:
            next_number += 1
            db.execute(
                text(f"UPDATE {table} SET doc_no = :no WHERE id = :i"),
                {"no": f"{prefix}{next_number:05d}", "i": row_id},
            )
        # Nhấc bộ đếm lên; `current_number < :n` chặn tụt số nếu chạy lại.
        if start is None:
            db.execute(
                text(
                    "INSERT INTO document_sequences (doc_type, year, current_number) "
                    "VALUES (:t, :y, :n)"
                ),
                {"t": doc_type, "y": SEQ_YEAR_GLOBAL, "n": next_number},
            )
        else:
            db.execute(
                text(
                    "UPDATE document_sequences SET current_number = :n "
                    "WHERE doc_type = :t AND year = :y AND current_number < :n"
                ),
                {"t": doc_type, "y": SEQ_YEAR_GLOBAL, "n": next_number},
            )
        db.commit()


def _migrate_drop_ghost_modules(db: Session) -> None:
    """Gỡ 5 module khỏi ma trận phân quyền: san_pham · dm_gia_click · dm_gia_khuon_ban ·
    dm_dinh_muc · dm_binh_bai (không màn nào dùng; router đã gỡ khỏi main.py). `seed_modules`
    chỉ thêm/đổi-nhãn nên DB đã chạy vẫn giữ dòng cũ → phải xóa tay ở đây (đúng lý do
    "Quy tắc bình bài" còn hiện dù module bỏ từ 0021). Xóa `role_permissions` TRƯỚC vì
    module_key là FK → modules.key. GIỮ NGUYÊN dữ liệu norms/plate_die_rates/products: engine
    tính giá đọc thẳng repo, đây chỉ gỡ cửa phân quyền. Best-effort; no-op trên DB fresh."""
    keys = ("san_pham", "dm_gia_click", "dm_gia_khuon_ban", "dm_dinh_muc", "dm_binh_bai")
    marks = ", ".join(f":k{i}" for i in range(len(keys)))
    params = {f"k{i}": k for i, k in enumerate(keys)}
    for sql in (
        f"DELETE FROM role_permissions WHERE module_key IN ({marks})",
        f"DELETE FROM modules WHERE key IN ({marks})",
    ):
        try:
            db.execute(text(sql), params)
            db.commit()
        except Exception:
            db.rollback()


def _migrate_drop_hop_dong_module(db: Session) -> None:
    """Gỡ module ma `hop_dong` khỏi ma trận phân quyền (giống 0069). Không router/màn nào enforce
    quyền này — "Hợp đồng" trong sản phẩm chỉ là LOẠI TÀI LIỆU đính kèm (doc_kind='hop_dong') nằm
    dưới Khách hàng/Nhân sự, gác bằng quyền khach_hang/nhan_su → tick ô này không đổi gì. `seed_modules`
    chỉ thêm/đổi-nhãn nên DB đã seed vẫn giữ dòng cũ → xóa tay ở đây. role_permissions TRƯỚC vì
    module_key là FK → modules.key. KHÔNG đụng doc_kind='hop_dong' (đường khác). Best-effort; no-op fresh."""
    for sql in (
        "DELETE FROM role_permissions WHERE module_key = :k",
        "DELETE FROM modules WHERE key = :k",
    ):
        try:
            db.execute(text(sql), {"k": "hop_dong"})
            db.commit()
        except Exception:
            db.rollback()


def _migrate_drop_san_luong_module(db: Session) -> None:
    """Gỡ module ma `san_luong` ("Sản lượng công đoạn") khỏi ma trận (giống 0088). Là quyền còn sót
    của module "Theo dõi sản xuất / nhập liệu xưởng" đã gỡ (commit e628c4b). Việc ghi sản lượng THẬT
    (Lát 2) đã chuyển sang gate `san_xuat:record_output` → không router/màn nào enforce `san_luong`.
    Xóa role_permissions TRƯỚC (FK → modules.key). KHÔNG đụng bảng `san_luong` (dữ liệu Lát 2) hay
    enum che_do_tinh='theo_san_luong' — đường khác. Best-effort; no-op trên DB fresh."""
    for sql in (
        "DELETE FROM role_permissions WHERE module_key = :k",
        "DELETE FROM modules WHERE key = :k",
    ):
        try:
            db.execute(text(sql), {"k": "san_luong"})
            db.commit()
        except Exception:
            db.rollback()


def _migrate_receipt_source_and_drop_order_deposits(db: Session) -> None:
    """V5 — Thu cọc đơn hàng bán = Phiếu thu THẬT (Kế toán) lập từ đơn.

    (a) `payment_receipts` đa nguồn: thêm `source_type` (default 'purchase_refund' cho data
        cũ), `order_id` (nhánh đơn), `customer_name_snapshot`, `order_no_snapshot`. NỚI NULLABLE
        5 cột nhánh Phiếu chi (`payment_voucher_id`, `purchase_request_id`, `voucher_code_snapshot`,
        `purchase_code_snapshot`, `supplier_name_snapshot`) để phiếu thu cọc khỏi cần.
    (b) DROP bảng `order_deposit_attachments` → `order_deposits` (module đơn CHƯA live → cọc cũ chỉ
        là seed throwaway; KHÔNG migrate dữ liệu).

    Idempotent + guard `_existing_columns`: trên DB fresh (test/new install) create_all đã dựng đúng
    model mới (cột mới có sẵn, 5 cột kia đã nullable, bảng cọc không còn) → no-op hoàn toàn. Nới NOT
    NULL chỉ chạy trên Postgres (prod) vì SQLite fresh vốn đã nullable; SQLite cũ thì dev drop dev.db.
    """
    bind = db.get_bind()
    insp = inspect(bind)
    names = set(insp.get_table_names())
    dialect = bind.dialect.name

    def run(sql: str) -> None:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    if "payment_receipts" in names:
        cols = {c["name"]: c for c in insp.get_columns("payment_receipts")}
        add_cols = [
            # TÍCH HỢP: dùng ĐÚNG hằng nguồn của model kế toán (accounting-wip): purchase_refund
            # (data cũ = phiếu chi hoàn) · order_deposit (cọc đơn). Cột snapshot = order_no_snapshot
            # để khớp AccountingService.create_order_receipt + model PaymentReceipt.
            ("source_type", "VARCHAR(20) NOT NULL DEFAULT 'purchase_refund'"),
            ("order_id", "INTEGER"),
            ("customer_name_snapshot", "VARCHAR(255)"),
            ("order_no_snapshot", "VARCHAR(32)"),
        ]
        for name, ddl in add_cols:
            if name not in cols:
                db.execute(text(f"ALTER TABLE payment_receipts ADD COLUMN {name} {ddl}"))
        db.commit()  # đóng đợt DDL trước khi tạo index (gotcha pysqlite)
        # ADD COLUMN không tạo index — tạo riêng, tên khớp create_all.
        run("CREATE INDEX IF NOT EXISTS ix_payment_receipts_source_type "
            "ON payment_receipts (source_type)")
        run("CREATE INDEX IF NOT EXISTS ix_payment_receipts_order_id "
            "ON payment_receipts (order_id)")
        # Nới NOT NULL nhánh Phiếu chi (chỉ Postgres — SQLite fresh vốn nullable, SQLite cũ drop db).
        if dialect == "postgresql":
            for c in (
                "payment_voucher_id", "purchase_request_id", "voucher_code_snapshot",
                "purchase_code_snapshot", "supplier_name_snapshot",
            ):
                col = cols.get(c)
                if col is not None and not col.get("nullable", True):
                    run(f"ALTER TABLE payment_receipts ALTER COLUMN {c} DROP NOT NULL")

    # Drop bảng cọc cũ (attachments trước vì FK → order_deposits).
    run("DROP TABLE IF EXISTS order_deposit_attachments")
    run("DROP TABLE IF EXISTS order_deposits")


def _migrate_order_line_phieu_thanh_phan(db: Session) -> None:
    """Đơn hàng: thêm `order_lines.phieu_thanh_phan_id` (soft ref → PhieuThanhPhan của PTG mà dòng
    báo giá nguồn trỏ tới) — pin truy vết ấn phẩm ở khúc chốt bán (song sinh
    QuoteItem.phieu_thanh_phan_id). Nullable Integer, KHÔNG FK cứng. No-op trên DB fresh
    (create_all đã dựng) hoặc khi bảng chưa tồn tại."""
    insp = inspect(db.get_bind())
    if "order_lines" not in insp.get_table_names():
        return
    if "phieu_thanh_phan_id" not in _existing_columns(insp, "order_lines"):
        db.execute(text("ALTER TABLE order_lines ADD COLUMN phieu_thanh_phan_id INTEGER"))
    db.commit()


def _migrate_cong_doan_department_id(db: Session) -> None:
    """Công đoạn: thêm `cong_doan.department_id` (soft int → departments.id) — phòng ban/tổ phụ
    trách công đoạn, để phát Lệnh SX đẩy việc theo đúng tổ. Nullable → không ảnh hưởng công đoạn
    cũ. No-op trên DB fresh / cột đã có."""
    insp = inspect(db.get_bind())
    if "cong_doan" not in insp.get_table_names():
        return
    if "department_id" not in _existing_columns(insp, "cong_doan"):
        db.execute(text("ALTER TABLE cong_doan ADD COLUMN department_id INTEGER"))
    db.commit()


def _migrate_quote_terms_text(db: Session) -> None:
    """Báo giá gộp 3 ô điều khoản thành 1 khối text tự do `terms_text` (mỗi dòng = 1 điều khoản,
    bản in đánh số theo dòng) + chuyển % cọc sang Đơn hàng bán:
      - THÊM quotes.terms_text, back-fill từ payment_terms/delivery_terms của phiếu cũ,
      - GỠ quotes.payment_terms / delivery_terms / deposit_pct (không màn nào nhập nữa).
    GIỮ quotes.delivery_address: không hiện/không in ở báo giá nhưng đơn hàng lấy làm ĐC giao mặc
    định. Best-effort mỗi câu (SQLite cũ có thể từ chối DROP COLUMN → cột mồ côi vô hại).
    No-op trên DB fresh."""
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    if "quotes" not in tables:
        return
    cols = _existing_columns(insp, "quotes")

    def run(sql: str) -> None:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    if "terms_text" not in cols:
        run("ALTER TABLE quotes ADD COLUMN terms_text TEXT")
        # Back-fill 2 ô cũ thành 2 dòng (nối ở Python — `||`/char(10) khác nhau giữa SQLite ↔ Postgres).
        # Phiếu không có gì → để NULL, API tự trả bộ điều khoản mặc định.
        if "payment_terms" in cols and "delivery_terms" in cols:
            try:
                rows = db.execute(
                    text("SELECT id, payment_terms, delivery_terms FROM quotes")
                ).all()
                for qid, pay, deliv in rows:
                    merged = "\n".join(x.strip() for x in (pay, deliv) if x and x.strip())
                    if merged:
                        db.execute(
                            text("UPDATE quotes SET terms_text = :t WHERE id = :i"),
                            {"t": merged, "i": qid},
                        )
                db.commit()
            except Exception:
                db.rollback()
    for col in ("payment_terms", "delivery_terms", "deposit_pct"):
        if col in cols:
            run(f"ALTER TABLE quotes DROP COLUMN {col}")


def _migrate_ptg_don_vi_tinh(db: Session) -> None:
    """Tính giá: thêm cột `phieu_thanh_phan.don_vi_tinh` (ĐVT sản phẩm — text tự do, mặc định 'cái').
    Chảy sang Báo giá (thay 'cái' hardcode). No-op trên DB fresh / bảng chưa có / đã có cột."""
    insp = inspect(db.get_bind())
    if "phieu_thanh_phan" not in insp.get_table_names():
        return
    if "don_vi_tinh" not in _existing_columns(insp, "phieu_thanh_phan"):
        db.execute(text(
            "ALTER TABLE phieu_thanh_phan ADD COLUMN don_vi_tinh VARCHAR(30) NOT NULL DEFAULT 'cái'"
        ))
    db.commit()


def _migrate_seed_pricing_formulas(db: Session) -> None:
    """Backfill công thức giá cho 3 danh mục CHUẨN (mực CMYK · màng bóng · ghi kẽm CTP) trên DB đã
    seed TRƯỚC khi có cột `cong_thuc_gia` (mig 0058) — để mực/màng/kẽm ra tiền thật thay vì 0đ.

    Chỉ đụng hàng còn MÃ CHUẨN và CHƯA có công thức (cong_thuc_gia rỗng) → KHÔNG đè cấu hình xưởng
    tự sửa. Mực: đơn giá placeholder 8.000/kg (giá ảo) → 250.000/kg CHỈ khi còn đúng 8.000. Ghi kẽm:
    ghi trọn cụm (theo_san_luong + per_other + run_rate 95.000) thì công thức `so_kem*don_gia` mới ra
    tiền — nhưng siết chỉ khi CD-0001 còn ĐÚNG placeholder cũ (theo_gio, chưa có run_rate/pricing_basis)
    để không đạp máy tính-giờ nếu xưởng đã tự set. No-op trên DB fresh (seed_rebuild đã ghi) / bảng-cột
    chưa có / hàng đã cấu hình."""
    bind = db.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if "vat_tu_in_an" in tables and "cong_thuc_gia" in _existing_columns(insp, "vat_tu_in_an"):
        db.execute(text(
            "UPDATE vat_tu_in_an SET cong_thuc_gia = "
            "'so_mau * dai_in * rong_in * don_gia_kg * to_dau_vao * 0.0003' "
            "WHERE ma = 'MUC-CMYK' AND (cong_thuc_gia IS NULL OR cong_thuc_gia = '')"
        ))
        db.execute(text(
            "UPDATE vat_tu_in_an SET don_gia = 250000 WHERE ma = 'MUC-CMYK' AND don_gia = 8000"
        ))
        db.execute(text(
            "UPDATE vat_tu_in_an SET cong_thuc_gia = "
            "'dai_in * rong_in * don_gia_m2 * to_sau_in' "
            "WHERE ma = 'MANG-BONG' AND (cong_thuc_gia IS NULL OR cong_thuc_gia = '')"
        ))

    if "cong_doan" in tables and "cong_thuc_gia" in _existing_columns(insp, "cong_doan"):
        db.execute(text(
            "UPDATE cong_doan SET cong_thuc_gia = 'so_kem * don_gia', "
            "che_do_tinh = 'theo_san_luong', pricing_basis = 'per_other', run_rate = 95000 "
            "WHERE ma = 'CD-0001' "
            "AND (cong_thuc_gia IS NULL OR cong_thuc_gia = '') "
            "AND che_do_tinh = 'theo_gio' "
            "AND run_rate IS NULL "
            "AND (pricing_basis IS NULL OR pricing_basis = '')"
        ))

    db.commit()


def _migrate_order_graft_fields(db: Session) -> None:
    """Graft trường đơn V4 → đơn V5 (erp), khớp DB_SCHEMA.md §orders/§order_lines: Order thêm
    delivery_contact_name/_phone (người nhận + SĐT) + delivery_note (lưu ý giao) + production_note
    (lưu ý SX) + is_rush (hàng gấp); OrderLine thêm don_vi_tinh (ĐVT — kéo từ báo giá). No-op trên
    DB fresh (create_all đã dựng) / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    names = insp.get_table_names()
    if "orders" in names:
        existing = _existing_columns(insp, "orders")
        for name, ddl in (
            ("delivery_contact_name", "VARCHAR(255)"),
            ("delivery_contact_phone", "VARCHAR(30)"),
            ("delivery_note", "VARCHAR(500)"),
            ("production_note", "VARCHAR(500)"),
            ("is_rush", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ):
            if name not in existing:
                db.execute(text(f"ALTER TABLE orders ADD COLUMN {name} {ddl}"))
    if "order_lines" in names and "don_vi_tinh" not in _existing_columns(insp, "order_lines"):
        db.execute(text("ALTER TABLE order_lines ADD COLUMN don_vi_tinh VARCHAR(30) NOT NULL DEFAULT 'cái'"))
    db.commit()


def _migrate_care_task_recurrence(db: Session) -> None:
    """Lịch hẹn chăm sóc kiểu calendar (redesign-lich-hen-cham-soc): thêm luật lặp + chuỗi ngoại
    lệ vào customer_care_tasks (repeat_freq/interval/until + series_id + occurrence_date). No-op
    trên DB fresh (create_all đã dựng) / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "customer_care_tasks" not in insp.get_table_names():
        return
    existing = _existing_columns(insp, "customer_care_tasks")
    for name, ddl in (
        ("repeat_freq", "VARCHAR(8) NOT NULL DEFAULT 'none'"),
        ("repeat_interval", "INTEGER NOT NULL DEFAULT 1"),
        ("repeat_until", "TIMESTAMP"),
        ("series_id", "INTEGER"),
        ("occurrence_date", "TIMESTAMP"),
    ):
        if name not in existing:
            db.execute(text(f"ALTER TABLE customer_care_tasks ADD COLUMN {name} {ddl}"))
    db.commit()
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_customer_care_tasks_series_id "
        "ON customer_care_tasks (series_id)"
    ))
    db.commit()


def _migrate_department_la_san_xuat(db: Session) -> None:
    """Phân hệ Sản xuất: thêm `departments.la_san_xuat` (Boolean,
    default false) — đánh dấu phòng/khối là bộ phận sản xuất; cả cây con (theo parent_id) kế thừa.
    No-op trên DB fresh (create_all đã dựng cột) / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "departments" not in insp.get_table_names():
        return
    if "la_san_xuat" not in _existing_columns(insp, "departments"):
        db.execute(text(
            "ALTER TABLE departments ADD COLUMN la_san_xuat BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    db.commit()


def _migrate_order_san_xuat_released(db: Session) -> None:
    """Handoff Đơn→Kế hoạch: thêm `orders.san_xuat_released_at` (TIMESTAMP nullable). Sale bấm
    'Chuyển xuống sản xuất' (SAU chốt, đủ cọc) mới set → đơn mới vào hàng chờ kế hoạch (người quyết).
    Nullable nên không cần default. No-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "orders" not in insp.get_table_names():
        return
    if "san_xuat_released_at" not in _existing_columns(insp, "orders"):
        db.execute(text("ALTER TABLE orders ADD COLUMN san_xuat_released_at TIMESTAMP"))
    db.commit()


def _migrate_lenh_item_quy_cach_override(db: Session) -> None:
    """OVERRIDE quy cách in tại lệnh: thêm `lenh_item.quy_cach_override` (JSON nullable) — kế hoạch
    sửa quy cách ở lệnh nháp, không đụng báo giá. Nullable nên không cần default. No-op trên DB fresh
    (create_all đã có cột) / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "lenh_item" not in insp.get_table_names():
        return
    if "quy_cach_override" not in _existing_columns(insp, "lenh_item"):
        db.execute(text("ALTER TABLE lenh_item ADD COLUMN quy_cach_override JSON"))
    db.commit()


def _migrate_ptp_ghi_chu_ky_thuat(db: Session) -> None:
    """Note KỸ THUẬT/SX theo SẢN PHẨM: thêm `phieu_thanh_phan.ghi_chu_ky_thuat` (TEXT nullable) —
    canh màu/kẽm cũ/bù hao gõ ở Tính giá, xuống drawer lệnh. Nullable nên không cần default.
    No-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "phieu_thanh_phan" not in insp.get_table_names():
        return
    if "ghi_chu_ky_thuat" not in _existing_columns(insp, "phieu_thanh_phan"):
        db.execute(text("ALTER TABLE phieu_thanh_phan ADD COLUMN ghi_chu_ky_thuat TEXT"))
    db.commit()


def _migrate_quote_item_dien_giai(db: Session) -> None:
    """Diễn giải quy cách in ra báo giá: thêm `quote_items.dien_giai` (TEXT nullable) — máy bung từ
    bài tính giá lúc tạo dòng, người soạn sửa được. Nullable nên không cần default.
    No-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "quote_items" not in insp.get_table_names():
        return
    if "dien_giai" not in _existing_columns(insp, "quote_items"):
        db.execute(text("ALTER TABLE quote_items ADD COLUMN dien_giai TEXT"))
    db.commit()


def _migrate_routing_step_ghi_chu(db: Session) -> None:
    """② Fix routing copy: thêm `routing_step.ghi_chu` (VARCHAR nullable) + `quy_cach` (VARCHAR
    nullable) — ảnh chụp ghi chú kỹ thuật + quy cách BƯỚC copy từ `PhieuThanhPham` khi bung (tổ hết
    trơ). Nullable nên không cần default (không dính bẫy Boolean). No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "routing_step" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "routing_step")
    if "ghi_chu" not in cols:
        db.execute(text("ALTER TABLE routing_step ADD COLUMN ghi_chu VARCHAR(500)"))
    if "quy_cach" not in cols:
        db.execute(text("ALTER TABLE routing_step ADD COLUMN quy_cach VARCHAR(255)"))
    db.commit()


def _migrate_lenh_sx_han_giao(db: Session) -> None:
    """① Hạn giao thuộc tính LỆNH: thêm `lenh_sx.han_giao_khach` + `han_giao_noi_bo` (DATE nullable) —
    hạn khách (snapshot đơn lúc bung) + hạn nội bộ (buffer planner nhập). Nullable nên không cần
    default. No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "lenh_sx" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "lenh_sx")
    if "han_giao_khach" not in cols:
        db.execute(text("ALTER TABLE lenh_sx ADD COLUMN han_giao_khach DATE"))
    if "han_giao_noi_bo" not in cols:
        db.execute(text("ALTER TABLE lenh_sx ADD COLUMN han_giao_noi_bo DATE"))
    db.commit()


def _migrate_lenh_sx_khuon_be_id(db: Session) -> None:
    """③ Gán khuôn bế: thêm `lenh_sx.khuon_be_id` (Integer nullable, soft → khuon_be.id) — điều độ
    link khuôn cho lệnh có bế. Nullable nên không cần default. No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "lenh_sx" not in insp.get_table_names():
        return
    if "khuon_be_id" not in _existing_columns(insp, "lenh_sx"):
        db.execute(text("ALTER TABLE lenh_sx ADD COLUMN khuon_be_id INTEGER"))
    db.commit()


def _migrate_lenh_sx_lich_chay(db: Session) -> None:
    """④ Lịch chạy (bảng Máy×Ngày): thêm `lenh_sx.ngay_chay` (DATE) + `thu_tu_chay` (INTEGER) +
    `thoi_luong_phut` (INTEGER — nền Gantt-đầy-đủ pha sau). Nullable nên không cần default.
    No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "lenh_sx" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "lenh_sx")
    if "ngay_chay" not in cols:
        db.execute(text("ALTER TABLE lenh_sx ADD COLUMN ngay_chay DATE"))
    if "thu_tu_chay" not in cols:
        db.execute(text("ALTER TABLE lenh_sx ADD COLUMN thu_tu_chay INTEGER"))
    if "thoi_luong_phut" not in cols:
        db.execute(text("ALTER TABLE lenh_sx ADD COLUMN thoi_luong_phut INTEGER"))
    db.commit()


def _migrate_routing_step_may_ca(db: Session) -> None:
    """Lát 1 · 1.12 — tổ tự xếp máy finishing + ca cho bước: thêm `routing_step.may_id` (INTEGER
    nullable, soft → may_thiet_bi.id) + `ca` (VARCHAR(16) nullable, "Ca 1/2/3"). Record-only. Nullable
    nên không cần default. No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "routing_step" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "routing_step")
    if "may_id" not in cols:
        db.execute(text("ALTER TABLE routing_step ADD COLUMN may_id INTEGER"))
    if "ca" not in cols:
        db.execute(text("ALTER TABLE routing_step ADD COLUMN ca VARCHAR(16)"))
    db.commit()


def _migrate_quote_item_accepted(db: Session) -> None:
    """Khách chốt MỘT PHẦN: thêm `quote_items.accepted` (BOOLEAN NOT NULL DEFAULT FALSE). Khi ghi
    "Khách chốt", mỗi dòng nhận quyết định ưng/không-ưng; đơn hàng chỉ kéo dòng accepted=True. DEFAULT
    FALSE (bool Postgres) an toàn cho báo giá cũ (chưa quyết định) — order_service fallback: 0 dòng
    True → kéo tất cả. No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "quote_items" not in insp.get_table_names():
        return
    if "accepted" not in _existing_columns(insp, "quote_items"):
        db.execute(text("ALTER TABLE quote_items ADD COLUMN accepted BOOLEAN NOT NULL DEFAULT FALSE"))
    db.commit()


def _migrate_drop_kho_giay_chuan(db: Session) -> None:
    """Gỡ HẲN module "Khổ giấy chuẩn": drop bảng `kho_giay_chuan`. Khổ giấy nguyên tờ
    nay nhập tay ở phiếu tính giá; danh mục Giấy chỉ giữ định lượng + đơn giá/kg. No-op trên
    DB fresh (bảng không còn trong create_all vì model đã xóa)."""
    try:
        db.execute(text("DROP TABLE IF EXISTS kho_giay_chuan"))
        db.commit()
    except Exception:
        db.rollback()
def _migrate_cau_hinh_luong(db: Session) -> None:
    """Màn "Cấu hình lương" (docs/prd-cau-hinh-luong.md §9) — chỉ ADD COLUMN, idempotent:
      - `department_salary_rows.promotion_condition` (VARCHAR(255) nullable) — điều kiện thăng bậc.
      - `payroll_params` += 3 tỷ lệ phía NGƯỜI SỬ DỤNG LAO ĐỘNG (BHXH 17.5% · BHYT 3% · BHTN 1%)
        — KHÔNG trừ vào lương NV, chỉ để tính chi phí bảo hiểm của công ty.
      - `payroll_lines` += `kpi_percent` (% đạt nhập tay) + `kpi_bonus` (tiền thưởng KPI).
    Hai bảng MỚI `department_salary_components` + `allowance_types` do `create_all` tự tạo.
    No-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "department_salary_rows" in tables:
        if "promotion_condition" not in _existing_columns(insp, "department_salary_rows"):
            db.execute(text(
                "ALTER TABLE department_salary_rows ADD COLUMN promotion_condition VARCHAR(255)"
            ))
    if "payroll_params" in tables:
        cols = _existing_columns(insp, "payroll_params")
        for name, ddl in (
            ("bhxh_rate_er", "NUMERIC(6,4) NOT NULL DEFAULT 0.175"),
            ("bhyt_rate_er", "NUMERIC(6,4) NOT NULL DEFAULT 0.03"),
            ("bhtn_rate_er", "NUMERIC(6,4) NOT NULL DEFAULT 0.01"),
        ):
            if name not in cols:
                db.execute(text(f"ALTER TABLE payroll_params ADD COLUMN {name} {ddl}"))
    if "payroll_lines" in tables:
        cols = _existing_columns(insp, "payroll_lines")
        for name, ddl in (
            ("kpi_percent", "NUMERIC(6,2) NOT NULL DEFAULT 0"),
            ("kpi_bonus", "NUMERIC(14,2) NOT NULL DEFAULT 0"),
        ):
            if name not in cols:
                db.execute(text(f"ALTER TABLE payroll_lines ADD COLUMN {name} {ddl}"))
    db.commit()


def _migrate_department_salary_policy_note(db: Session) -> None:
    """`departments.salary_policy_note` (VARCHAR(500) nullable) — ô ghi chú chính sách lương
    của tổ ở màn Cấu hình lương Tab 1 (prd-cau-hinh-luong §3). Nullable nên không cần default.
    Idempotent, no-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "departments" not in insp.get_table_names():
        return
    if "salary_policy_note" not in _existing_columns(insp, "departments"):
        db.execute(text("ALTER TABLE departments ADD COLUMN salary_policy_note VARCHAR(500)"))
    db.commit()


def _migrate_luong_v2_khung_bac(db: Session) -> None:
    """PRD v2 "Cấu hình lương" (docs/prd-cau-hinh-luong.md §10) — tách BẬC khỏi TIỀN:

      - `department_salary_rows` += `luong_min`/`luong_max` (KHUNG của bậc — C1, nullable).
      - `employee_salaries` += `luong_vi_tri`/`luong_trach_nhiem` (mức hợp đồng RIÊNG của NV — C2)
        + `pay_grade_row_id` (bậc, CHỈ để phân loại — tách khỏi nguồn tiền).

    **BACKFILL GIỮ NGUYÊN LƯƠNG NGƯỜI CŨ:** bản ghi đang trỏ `source_salary_row_id` được COPY
    `luong_vi_tri`/`luong_trach_nhiem` CỦA DÒNG BẬC xuống chính bản ghi NV, và `pay_grade_row_id
    = source_salary_row_id`. Sau migration engine đọc mức từ bản ghi NV → SỐ LƯƠNG KHÔNG ĐỔI.

    Idempotent: backfill chỉ chạm hàng `pay_grade_row_id IS NULL` (chạy lại = no-op, không đè số
    admin đã sửa). Hai bảng MỚI `department_shift_rates` + `payroll_line_shifts` do `create_all`
    tự tạo. No-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "department_salary_rows" in tables:
        cols = _existing_columns(insp, "department_salary_rows")
        for name in ("luong_min", "luong_max"):
            if name not in cols:
                db.execute(text(f"ALTER TABLE department_salary_rows ADD COLUMN {name} NUMERIC(14,2)"))
    if "employee_salaries" not in tables:
        db.commit()
        return
    cols = _existing_columns(insp, "employee_salaries")
    for name, ddl in (
        ("luong_vi_tri", "NUMERIC(14,2) NOT NULL DEFAULT 0"),
        ("luong_trach_nhiem", "NUMERIC(14,2) NOT NULL DEFAULT 0"),
        ("pay_grade_row_id", "INTEGER"),
    ):
        if name not in cols:
            db.execute(text(f"ALTER TABLE employee_salaries ADD COLUMN {name} {ddl}"))
    db.commit()   # commit DDL TRƯỚC backfill (gotcha pysqlite — xem migration 0004)
    if "department_salary_rows" in tables and "source_salary_row_id" in cols:
        db.execute(text(
            "UPDATE employee_salaries SET"
            " luong_vi_tri = COALESCE((SELECT r.luong_vi_tri FROM department_salary_rows r"
            "                          WHERE r.id = employee_salaries.source_salary_row_id), 0),"
            " luong_trach_nhiem = COALESCE((SELECT r.luong_trach_nhiem FROM department_salary_rows r"
            "                               WHERE r.id = employee_salaries.source_salary_row_id), 0),"
            " pay_grade_row_id = source_salary_row_id"
            " WHERE pay_grade_row_id IS NULL AND source_salary_row_id IS NOT NULL"
            " AND EXISTS (SELECT 1 FROM department_salary_rows r"
            "             WHERE r.id = employee_salaries.source_salary_row_id)"
        ))
    db.commit()


def _migrate_payroll_line_allowance_split(db: Session) -> None:
    """Tách phụ cấp trên PHIẾU LƯƠNG (PRD v2 bệnh B2 "phụ cấp một cục", nghiệm thu §12.6):
    `payroll_lines` += `phu_cap_trach_nhiem` + `phu_cap_tham_nien` — số tiền TỪNG khoản đã tính
    của kỳ, để phiếu lương hiện dòng riêng thay vì một cục "Phụ cấp".

    **KHÔNG đổi tiền của ai:** hai cột này là "TRONG ĐÓ" của `payroll_lines.allowance` (tổng
    phụ cấp) — engine vẫn cộng đúng một lần qua `allowance`. Dòng lương CŨ nhận DEFAULT 0 nên
    `allowance` vẫn là tổng đúng (phiếu cũ hiện "Phụ cấp khác" = toàn bộ, 2 dòng kia = 0).
    Chỉ ADD COLUMN, idempotent; no-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "payroll_lines" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "payroll_lines")
    for name in ("phu_cap_trach_nhiem", "phu_cap_tham_nien"):
        if name not in cols:
            db.execute(text(
                f"ALTER TABLE payroll_lines ADD COLUMN {name} NUMERIC(14,2) NOT NULL DEFAULT 0"
            ))
    db.commit()


def _migrate_luong_phu_cap_khai_tay(db: Session) -> None:
    """Chủ chốt 2026-07-20 — ĐẢO NGƯỢC cách khai phụ cấp: *"Phụ cấp ca, trách nhiệm, thâm niên
    — cho nó khai tay đi, hệ thống không cần tính toán, khi nào sửa thì nó sửa"* và *"Đơn giá ca
    — bỏ đi, vì khi khai lương rồi thì nó tự chia"*. Khai theo TỪNG NGƯỜI, một SỐ CỐ ĐỊNH.

      - `employee_salaries` += `phu_cap_ca` · `phu_cap_trach_nhiem` · `phu_cap_tham_nien`
        (NOT NULL DEFAULT 0) — engine cộng PHẲNG y như `allowance` ("phụ cấp khác").
      - DROP `department_shift_rates` · `payroll_line_shifts` · `allowance_types`: 3 bảng của
        cách tính cũ (đơn giá ca × số lượt · danh mục phụ cấp cấp công ty) không còn điều khiển
        gì. An toàn vì cả cụm này CHƯA commit/CHƯA deploy — chỉ tồn tại ở dev.db.
      - Dọn `department_salary_components` các dòng `phu_cap_*`: 3 khoản đã chuyển hẳn về cấp NV,
        để lại chỉ gây hiểu nhầm "khai ở tổ mà không ra tiền".

    Chuyên cần/KPI/lương bậc/khoán/tăng ca vẫn khai theo TỔ — không đụng. Idempotent, no-op trên
    DB trắng / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "employee_salaries" in tables:
        cols = _existing_columns(insp, "employee_salaries")
        for name in ("phu_cap_ca", "phu_cap_trach_nhiem", "phu_cap_tham_nien"):
            if name not in cols:
                db.execute(text(
                    f"ALTER TABLE employee_salaries ADD COLUMN {name} NUMERIC(14,2) NOT NULL DEFAULT 0"
                ))
        db.commit()
    for tbl in ("payroll_line_shifts", "department_shift_rates", "allowance_types"):
        if tbl in tables:
            db.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
    if "department_salary_components" in tables:
        db.execute(text(
            "DELETE FROM department_salary_components WHERE component_key IN"
            " ('phu_cap_ca_dem', 'phu_cap_trach_nhiem', 'phu_cap_tham_nien')"
        ))
    db.commit()


def _migrate_employee_shift_history(db: Session) -> None:
    """Backfill versioned shifts from the legacy employee default shift."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "employee_shift_assignments" not in tables or "employees" not in tables:
        return
    db.execute(text(
        "INSERT INTO employee_shift_assignments"
        " (employee_id, shift_id, effective_from, created_by, created_at)"
        " SELECT e.id, e.default_shift_id, COALESCE(e.hire_date, '1900-01-01'), NULL, CURRENT_TIMESTAMP"
        " FROM employees e"
        " WHERE e.default_shift_id IS NOT NULL"
        " AND NOT EXISTS (SELECT 1 FROM employee_shift_assignments a WHERE a.employee_id = e.id)"
    ))
    db.commit()


def _migrate_luong_bo_bac_luong(db: Session) -> None:
    """Chủ chốt 2026-07-20 (đảo phần bậc): BỎ HẲN hệ thống bậc lương — bậc chỉ để phân nhóm,
    không quyết định tiền (bảng T05: cùng bậc 2 mà người 20tr người 10,5tr). Bậc về lại free-text
    `employees.job_grade` đã có sẵn. Và bỏ khoản `phu_cap_trach_nhiem` khai tay (trùng ý với
    `luong_trach_nhiem`).

      - DROP TABLE `department_salary_rows` (khung/điều kiện thăng bậc/đếm NV theo bậc).
      - DROP COLUMN `employee_salaries.pay_grade_row_id` · `.phu_cap_trach_nhiem`.
      - DROP COLUMN `payroll_lines.phu_cap_trach_nhiem` (dòng phiếu lương trùng).
      - DROP COLUMN `departments.salary_policy_note`.

    `employee_salaries.insurance_base` GIỮ dormant (Điều 2 — không migration phá hủy). Best-effort
    từng câu (SQLite cũ từ chối DROP COLUMN → cột mồ côi vô hại, model không map). An toàn vì cả cụm
    bậc lương CHƯA commit/CHƯA deploy. Idempotent, no-op trên DB trắng / bảng-cột chưa/đã bỏ."""
    bind = db.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    def run(sql: str) -> None:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    if "department_salary_rows" in tables:
        run("DROP TABLE IF EXISTS department_salary_rows")
    for tbl, col in (
        ("employee_salaries", "pay_grade_row_id"),
        ("employee_salaries", "phu_cap_trach_nhiem"),
        ("payroll_lines", "phu_cap_trach_nhiem"),
        ("departments", "salary_policy_note"),
    ):
        if tbl in tables and col in _existing_columns(insp, tbl):
            run(f"ALTER TABLE {tbl} DROP COLUMN {col}")


def _migrate_luong_phu_cap_com_ca_dem(db: Session) -> None:
    """Đợt 1 nhân sự & lương:
      - `payroll_params.com_allowance` (25000) + `.night_allowance` (50000) — phụ cấp cơm khi
        tăng ca (17h30→24h) + phụ cấp ca đêm (qua 12h), cấp CÔNG TY. Đợt 1 chỉ LƯU + phơi;
        engine `_compute` CHƯA đọc (nối ở Đợt 2).
      - `employees.prior_seniority_months` (0) — thâm niên đã có TRƯỚC khi vào làm (tháng);
        tổng thâm niên = số này + thời gian từ hire_date. Chỉ lưu + hiển thị.

    Idempotent (kiểm cột trước khi ALTER), no-op trên DB fresh (create_all đã dựng) / bảng chưa có."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "payroll_params" in tables:
        existing = _existing_columns(insp, "payroll_params")
        if "com_allowance" not in existing:
            db.execute(text(
                "ALTER TABLE payroll_params ADD COLUMN com_allowance NUMERIC(14,2) NOT NULL DEFAULT 25000"
            ))
        if "night_allowance" not in existing:
            db.execute(text(
                "ALTER TABLE payroll_params ADD COLUMN night_allowance NUMERIC(14,2) NOT NULL DEFAULT 50000"
            ))
    if "employees" in tables:
        if "prior_seniority_months" not in _existing_columns(insp, "employees"):
            db.execute(text(
                "ALTER TABLE employees ADD COLUMN prior_seniority_months INTEGER NOT NULL DEFAULT 0"
            ))
    db.commit()


def _migrate_ca_phu_cap_com_ca_dem(db: Session) -> None:
    """Đợt 1b — chuyển phụ cấp cơm/ca đêm từ cấp CÔNG TY sang khai theo TỪNG CA (chủ 2026-07-21):
      - GỠ `payroll_params.com_allowance` + `.night_allowance` (vừa thêm ở 0093) — best-effort:
        SQLite < 3.35 không hỗ trợ DROP COLUMN → bỏ qua, để cột mồ côi vô hại (model không map).
        Postgres prod DROP bình thường.
      - THÊM `work_shifts.meal_allowance` (25000) + `.night_allowance` (50000) — phụ cấp khai
        theo ca; NV được gán ca đó tự cộng. Đợt 1 chỉ LƯU; engine `_compute` CHƯA cộng (Đợt 2).

    Idempotent (kiểm cột trước khi ALTER), forward-only, no-op trên DB fresh (create_all đã dựng)
    / bảng chưa có."""
    bind = db.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    def run(sql: str) -> None:
        """Best-effort DDL: nuốt lỗi (SQLite cũ từ chối DROP COLUMN) để migration không vỡ."""
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    if "payroll_params" in tables:
        existing = _existing_columns(insp, "payroll_params")
        for col in ("com_allowance", "night_allowance"):
            if col in existing:
                run(f"ALTER TABLE payroll_params DROP COLUMN {col}")

    if "work_shifts" in tables:
        existing = _existing_columns(insp, "work_shifts")
        if "meal_allowance" not in existing:
            db.execute(text(
                "ALTER TABLE work_shifts ADD COLUMN meal_allowance NUMERIC(14,2) NOT NULL DEFAULT 25000"
            ))
        if "night_allowance" not in existing:
            db.execute(text(
                "ALTER TABLE work_shifts ADD COLUMN night_allowance NUMERIC(14,2) NOT NULL DEFAULT 50000"
            ))
    db.commit()


def _migrate_ca_rename_shift_allowance_go_night_shift(db: Session) -> None:
    """Đợt 2a — chỉnh danh mục CA (`work_shifts`), chủ 2026-07-21:
      - ĐỔI TÊN `night_allowance` → `shift_allowance` (giữ default 50000): phụ cấp của CA,
        áp cho ca ngày hay đêm (bỏ chữ "đêm").
      - GỠ `night_shift` — cờ "Ca đêm (có phụ cấp)" thừa (phụ cấp giờ là ô SỐ gắn vào ca).

    Mỗi bước guard riêng theo cột tồn tại → idempotent, forward-only, chạy 2 lần OK, no-op trên
    DB trắng (create_all đã dựng đúng shape). SQLite ≥ 3.35 hỗ trợ RENAME/DROP COLUMN; engine cũ
    thì bọc best-effort (bỏ qua, để cột dormant vô hại). Postgres prod chạy bình thường."""
    bind = db.get_bind()
    insp = inspect(bind)
    if "work_shifts" not in insp.get_table_names():
        return

    def run(sql: str) -> None:
        """Best-effort DDL: nuốt lỗi (SQLite cũ từ chối RENAME/DROP COLUMN) để migration không vỡ."""
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    existing = _existing_columns(insp, "work_shifts")

    # 1) ĐỔI TÊN night_allowance → shift_allowance (chỉ khi nguồn còn & đích chưa có).
    if "night_allowance" in existing and "shift_allowance" not in existing:
        run("ALTER TABLE work_shifts RENAME COLUMN night_allowance TO shift_allowance")

    # 2) GỠ night_shift (chỉ khi còn tồn tại).
    if "night_shift" in existing:
        run("ALTER TABLE work_shifts DROP COLUMN night_shift")

    db.commit()


def _migrate_luong_insurance_elsewhere(db: Session) -> None:
    """BH đóng ở nơi khác (chủ 2026-07-21):
      - `payroll_params.tnld_bnn_rate` — tỷ lệ TNLĐ-BNN công ty chịu (mặc định 0.5% = 0.005).
      - `employee_salaries.insurance_elsewhere` — cờ NV có BH đóng ở nơi khác → công ty KHÔNG trừ
        BHXH/BHYT/BHTN của NV, chỉ chịu TNLĐ-BNN.

    Mỗi cột guard riêng theo tồn tại → idempotent, forward-only, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "payroll_params" in tables and "tnld_bnn_rate" not in _existing_columns(insp, "payroll_params"):
        db.execute(text(
            "ALTER TABLE payroll_params ADD COLUMN tnld_bnn_rate NUMERIC(6,4) NOT NULL DEFAULT 0.005"))
    if ("employee_salaries" in tables
            and "insurance_elsewhere" not in _existing_columns(insp, "employee_salaries")):
        db.execute(text(
            "ALTER TABLE employee_salaries ADD COLUMN insurance_elsewhere BOOLEAN NOT NULL DEFAULT FALSE"))
    db.commit()


def _migrate_luong_union_member(db: Session) -> None:
    """Đoàn phí công đoàn theo TỪNG NGƯỜI (chủ 2026-07-21): CHỈ đoàn viên mới đóng.
    `employee_salaries.insurance_elsewhere` đã có; nay thêm `union_member` (mặc định FALSE = opt-in).
    Guard theo cột tồn tại → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if ("employee_salaries" in insp.get_table_names()
            and "union_member" not in _existing_columns(insp, "employee_salaries")):
        db.execute(text(
            "ALTER TABLE employee_salaries ADD COLUMN union_member BOOLEAN NOT NULL DEFAULT FALSE"))
    db.commit()


def _migrate_attendance_late_off_days(db: Session) -> None:
    """Phạt trễ/sớm TỰ ĐỘNG (chủ 2026-07-21): snapshot kỳ công đóng băng danh sách SỐ PHÚT vi phạm
    (trễ+sớm, không phép) mỗi ngày để Lương áp bảng phạt. Thêm `attendance_period_lines.late_off_days_json`
    (TEXT, chứa JSON list). Guard theo cột tồn tại → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if ("attendance_period_lines" in insp.get_table_names()
            and "late_off_days_json" not in _existing_columns(insp, "attendance_period_lines")):
        db.execute(text("ALTER TABLE attendance_period_lines ADD COLUMN late_off_days_json TEXT"))
    db.commit()


def _migrate_payroll_di_tre_manual(db: Session) -> None:
    """Phạt trễ/sớm TỰ ĐỘNG (chủ 2026-07-21): cờ `payroll_lines.di_tre_manual` — HCNS sửa tay ô "Đi trễ"
    thì khóa không cho phạt tự động (từ chấm công) đè khi Tính lại. Mirror `pit_manual`. Guard theo cột
    tồn tại → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if ("payroll_lines" in insp.get_table_names()
            and "di_tre_manual" not in _existing_columns(insp, "payroll_lines")):
        db.execute(text("ALTER TABLE payroll_lines ADD COLUMN di_tre_manual BOOLEAN NOT NULL DEFAULT FALSE"))
    db.commit()


def _migrate_ca_night_multiplier(db: Session) -> None:
    """Lương ca đêm theo giờ (chủ 2026-07-22): hệ số ca đêm per-ca `work_shifts.night_multiplier`
    (mặc định 1.3 = +30%). Guard theo cột tồn tại → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if ("work_shifts" in insp.get_table_names()
            and "night_multiplier" not in _existing_columns(insp, "work_shifts")):
        db.execute(text("ALTER TABLE work_shifts ADD COLUMN night_multiplier NUMERIC(6,4) NOT NULL DEFAULT 1.3"))
    db.commit()


def _migrate_attendance_night_premium(db: Session) -> None:
    """Lương ca đêm theo giờ (chủ 2026-07-22): snapshot kỳ công đóng băng phút đêm để Lương tính premium.
    Thêm `attendance_period_lines`: night_premium_minutes (Σ phút đêm × (hệ số−1)) + 3 cột phút TĂNG CA ĐÊM
    theo loại ngày. Guard theo từng cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if "attendance_period_lines" in insp.get_table_names():
        cols = _existing_columns(insp, "attendance_period_lines")
        for name, ddl in (
            ("night_premium_minutes", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
            ("ot_night_normal_minutes", "INTEGER NOT NULL DEFAULT 0"),
            ("ot_night_restday_minutes", "INTEGER NOT NULL DEFAULT 0"),
            ("ot_night_holiday_minutes", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in cols:
                db.execute(text(f"ALTER TABLE attendance_period_lines ADD COLUMN {name} {ddl}"))
    db.commit()


def _migrate_payroll_night_premium_pay(db: Session) -> None:
    """Lương ca đêm theo giờ (chủ 2026-07-22): dòng riêng `payroll_lines.night_premium_pay` = tiền premium
    giờ đêm + tăng ca đêm (tách khỏi ô "Phụ cấp ca" khai tay). Guard theo cột → idempotent."""
    insp = inspect(db.get_bind())
    if ("payroll_lines" in insp.get_table_names()
            and "night_premium_pay" not in _existing_columns(insp, "payroll_lines")):
        db.execute(text("ALTER TABLE payroll_lines ADD COLUMN night_premium_pay NUMERIC(14,2) NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_payroll_ot_night_extra_pct(db: Session) -> None:
    """Lương ca đêm theo giờ (chủ 2026-07-22): tham số KHAI ĐƯỢC `payroll_params.ot_night_extra_pct`
    (cộng dồn tăng ca đêm Đ98.3, mặc định 0.2 = 20%). `night_pct` (phụ trội đêm) đã có sẵn.
    Guard theo cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if ("payroll_params" in insp.get_table_names()
            and "ot_night_extra_pct" not in _existing_columns(insp, "payroll_params")):
        db.execute(text("ALTER TABLE payroll_params ADD COLUMN ot_night_extra_pct NUMERIC(6,4) NOT NULL DEFAULT 0.2"))
    db.commit()


def _migrate_component_note_and_source(db: Session) -> None:
    """Danh mục khoản thu nhập v2 (chủ 2026-07-27):
      - `employee_salary_components.note` — ghi vết cho khoản "Thu nhập khác".
      - `payroll_line_components.source`  — `employee` (chép từ hồ sơ, ghi đè khi tính lại) vs
        `line` (thưởng nóng thêm tay, PHẢI giữ nguyên). Default `employee` để mọi dòng đã snapshot
        trước đây được hiểu đúng là chép-từ-hồ-sơ.
      - `payroll_line_components.note`.
    Guard theo cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    names = insp.get_table_names()
    if "employee_salary_components" in names:
        if "note" not in _existing_columns(insp, "employee_salary_components"):
            db.execute(text("ALTER TABLE employee_salary_components ADD COLUMN note VARCHAR(255)"))
    if "payroll_line_components" in names:
        cols = _existing_columns(insp, "payroll_line_components")
        if "source" not in cols:
            db.execute(text("ALTER TABLE payroll_line_components ADD COLUMN source "
                            "VARCHAR(8) NOT NULL DEFAULT 'employee'"))
        if "note" not in cols:
            db.execute(text("ALTER TABLE payroll_line_components ADD COLUMN note VARCHAR(255)"))
    db.commit()


def _migrate_pit_mode_and_flat_rate(db: Session) -> None:
    """Nhánh thuế cho lao động THỜI VỤ / thực tập (chủ 2026-07-27).

    `employees.pit_mode` — `luy_tien` (mặc định, giữ nguyên hành vi cũ cho toàn bộ dữ liệu đang có)
    · `khau_tru_10` (HĐ dưới 3 tháng: khấu trừ 10% tại nguồn) · `cam_ket_08` (không khấu trừ).
    `payroll_params.pit_flat_rate` + `pit_flat_threshold` — hai số này đổi theo luật nên khai được.
    Guard theo cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    names = insp.get_table_names()
    if "employees" in names and "pit_mode" not in _existing_columns(insp, "employees"):
        db.execute(text(
            "ALTER TABLE employees ADD COLUMN pit_mode VARCHAR(16) NOT NULL DEFAULT 'luy_tien'"))
    if "payroll_params" in names:
        cols = _existing_columns(insp, "payroll_params")
        if "pit_flat_rate" not in cols:
            db.execute(text("ALTER TABLE payroll_params ADD COLUMN pit_flat_rate "
                            "NUMERIC(6,4) NOT NULL DEFAULT 0.1"))
        if "pit_flat_threshold" not in cols:
            db.execute(text("ALTER TABLE payroll_params ADD COLUMN pit_flat_threshold "
                            "NUMERIC(14,2) NOT NULL DEFAULT 2000000"))
    db.commit()


def _migrate_salary_apply_self_deduction(db: Session) -> None:
    """`employee_salaries.apply_self_deduction` (chủ 2026-07-27): có áp giảm trừ bản thân khi tính
    TNCN không. Người làm 2 nơi chỉ được đăng ký giảm trừ bản thân ở MỘT nơi. Mặc định BẬT nên dữ
    liệu cũ giữ nguyên số. Guard theo cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if "employee_salaries" not in insp.get_table_names():
        return
    if "apply_self_deduction" not in _existing_columns(insp, "employee_salaries"):
        db.execute(text(
            "ALTER TABLE employee_salaries ADD COLUMN apply_self_deduction "
            "BOOLEAN NOT NULL DEFAULT true"))
    db.commit()


def _migrate_payroll_line_thu_nhap_chiu_thue(db: Session) -> None:
    """`payroll_lines.thu_nhap_chiu_thue` — tổng thu nhập CHỊU thuế TNCN của kỳ (tổng lương trừ
    các khoản miễn, TRƯỚC giảm trừ gia cảnh). Chủ yêu cầu hiện số này trên phiếu lương; cột
    `pit_taxable` sẵn có là thu nhập TÍNH thuế (sau giảm trừ), lệch nhau ~15,5tr nên không thay
    thế được. Guard theo cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if "payroll_lines" not in insp.get_table_names():
        return
    if "thu_nhap_chiu_thue" not in _existing_columns(insp, "payroll_lines"):
        db.execute(text(
            "ALTER TABLE payroll_lines ADD COLUMN thu_nhap_chiu_thue NUMERIC(14,2) NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_seed_missing_payroll_components(db: Session) -> None:
    """Bù các khoản danh mục còn THIẾU (sự cố seed 27/07/2026).

    `seed_payroll_components` là seed-once theo ĐẾM DÒNG: bảng có dòng nào rồi là bỏ qua sạch.
    Máy dev đã seed nhầm một bản dở (thiếu đúng 4 khoản MIỄN THUẾ là lý do sinh ra danh mục:
    trang phục · tiền nhà · đi lại · tiền cơm), và seed-once không bao giờ bù lại được.

    Chỉ INSERT code chưa có; KHÔNG đụng dòng đang tồn tại (giữ nguyên chỉnh sửa của chủ). Chạy
    một lần qua registry migration nên khoản chủ CỐ Ý xoá sau này sẽ không bị mọc lại."""
    insp = inspect(db.get_bind())
    if "payroll_components" not in insp.get_table_names():
        return
    from .seed import _PAYROLL_COMPONENTS_SEED
    have = {r[0] for r in db.execute(text("SELECT code FROM payroll_components")).all()}
    for code, name, kind, taxable, order in _PAYROLL_COMPONENTS_SEED:
        if code in have:
            continue
        db.execute(
            # `created_at` chỉ có default phía Python (không server_default) ⇒ INSERT thô phải
            # tự điền, nếu không vướng NOT NULL.
            # Cột BOOLEAN phải nhận bool/`false`/`true` — số `0`/`1` chạy được trên SQLite nhưng
            # Postgres từ chối thẳng (DatatypeMismatch).
            text("INSERT INTO payroll_components "
                 "(code, name, kind, is_taxable, in_insurance_base, sort_order, is_active, created_at) "
                 "VALUES (:c, :n, :k, :t, false, :o, true, :now)"),
            {"c": code, "n": name, "k": kind, "t": bool(taxable), "o": order,
             "now": datetime.now(timezone.utc)},
        )
    db.commit()


def _migrate_payroll_phat_cap_pct(db: Session) -> None:
    """Trần khấu trừ kỷ luật thành THAM SỐ (chủ 29/07/2026 — "bỏ cái 30% fix cứng trong code").

    Trước đây `_capped_penalty` viết thẳng `0.30`. Đây là mức LUẬT (Điều 102 BLLĐ) nên không xoá
    trần, chỉ bỏ chỗ viết cứng: mặc định 0.30 giữ nguyên hành vi cũ, `0` = tắt trần.
    Guard theo cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if ("payroll_params" in insp.get_table_names()
            and "phat_cap_pct" not in _existing_columns(insp, "payroll_params")):
        db.execute(text(
            "ALTER TABLE payroll_params ADD COLUMN phat_cap_pct NUMERIC(6,4) NOT NULL DEFAULT 0.3"))
    db.commit()


def _migrate_job_grade_catalog(db: Session) -> None:
    """Bậc tay nghề: từ CHỮ TỰ DO thành DANH MỤC có id (chủ 29/07/2026 — "khai bậc tay nghề cho
    nhân viên sản xuất", "chia nó thành 3 bậc, 2 bậc phụ").

    Trước đây bậc nằm ở HAI chỗ song song, không cái nào dùng được để tính:
      - `employees.job_grade`     — chữ tự do "3/7", máy không gộp được với "Thợ bậc 3"
      - `employees.pay_grade_key` — chuẩn hoá 'tho_1'…, nhưng KHÔNG có màn nào khai

    Migration này gom cả hai về `employees.job_grade_id` → `job_grades`. Mã danh mục dùng LẠI
    đúng bộ `pay_grade_key` cũ nên đường (a) khớp chắc chắn, không đoán.

    ⚠️ Seed đặt ở ĐÂY chứ không ở `seed.py`: `SEED_DEMO` đang tắt nên `seed.py` không chạy, mà
    danh mục rỗng thì màn hồ sơ không có gì để chọn. Cùng cách đã làm ở migration 0123.

    Guard theo cột/số dòng → chạy lại lần hai là no-op, KHÔNG đè bậc chủ đã sửa tên."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "job_grades" not in tables:
        return                       # create_all chưa chạy → không có gì để làm

    # (1) Cột mới trên `employees` — create_all KHÔNG bao giờ ALTER bảng đã có.
    if "employees" in tables and "job_grade_id" not in _existing_columns(insp, "employees"):
        db.execute(text("ALTER TABLE employees ADD COLUMN job_grade_id INTEGER"))
        db.commit()

    # (2) Seed 5 bậc — CHỈ khi danh mục còn rỗng.
    # Viết thẳng ở đây, KHÔNG import từ models: migration là bản ghi LỊCH SỬ, phải cho ra cùng
    # kết quả mãi mãi. Import hằng số của model thì mai kia sửa model là đổi luôn hành vi của
    # migration cũ trên DB chưa nâng cấp.
    seed_rows = (("bac_1", "Bậc 1", 1), ("bac_2", "Bậc 2", 2), ("bac_3", "Bậc 3", 3),
                 ("bac_4", "Bậc 4", 4), ("bac_5", "Bậc 5", 5))
    # Bộ mã `pay_grade_key` CŨ ('tho_*'/'phu_*') → bậc mới. Xếp theo mức lương giảm dần trong
    # bảng lương thật 2026 (25/22/20tr rồi 14,5/10,5tr) nên phụ 1–2 rơi đúng xuống bậc 4–5.
    legacy_codes = {"tho_1": "bac_1", "tho_2": "bac_2", "tho_3": "bac_3",
                    "phu_1": "bac_4", "phu_2": "bac_5"}
    now = datetime.now(timezone.utc)
    if not db.execute(text("SELECT 1 FROM job_grades LIMIT 1")).first():
        for code, name, seq in seed_rows:
            db.execute(
                text("INSERT INTO job_grades (code, name, seq, is_active, created_at) "
                     "VALUES (:c, :n, :s, true, :now)"),
                {"c": code, "n": name, "s": seq, "now": now},
            )
        db.commit()

    if "employees" not in tables:
        return

    def _by_code() -> dict[str, int]:
        return {r[1]: r[0] for r in db.execute(text("SELECT id, code FROM job_grades"))}

    def _by_name() -> dict[str, int]:
        # Khoá so khớp: bỏ dấu cách thừa + gộp hoa/thường. "  bậc 3 " ≡ "Bậc 3".
        return {" ".join(str(r[1]).split()).lower(): r[0]
                for r in db.execute(text("SELECT id, name FROM job_grades"))}

    # (3a) Backfill từ `pay_grade_key` — khớp MÃ, chắc chắn đúng, không đoán.
    if "pay_grade_key" in _existing_columns(insp, "employees"):
        codes = _by_code()
        for emp_id, key in db.execute(text(
            "SELECT id, pay_grade_key FROM employees "
            "WHERE job_grade_id IS NULL AND pay_grade_key IS NOT NULL"
        )).all():
            k = str(key).strip()
            gid = codes.get(k) or codes.get(legacy_codes.get(k, ""))
            if gid:
                db.execute(text("UPDATE employees SET job_grade_id = :g WHERE id = :i"),
                           {"g": gid, "i": emp_id})
        db.commit()

    # (3b/c) Backfill từ `job_grade` (chữ). Không khớp bậc nào ⇒ VẪN tạo dòng danh mục nhưng
    # `is_active = false`: không vứt dữ liệu người ta đã nhập, mà cũng không làm bẩn danh sách
    # chọn. Chủ vào soát rồi gộp/bật lại tuỳ ý.
    if "job_grade" not in _existing_columns(insp, "employees"):
        return
    rows = db.execute(text(
        "SELECT id, job_grade FROM employees "
        "WHERE job_grade_id IS NULL AND job_grade IS NOT NULL AND TRIM(job_grade) <> ''"
    )).all()
    if not rows:
        return
    names = _by_name()
    next_seq = (db.execute(text("SELECT MAX(seq) FROM job_grades")).scalar() or 0) + 1
    for emp_id, raw in rows:
        label = " ".join(str(raw).split())
        gid = names.get(label.lower())
        if gid is None:
            db.execute(
                text("INSERT INTO job_grades (code, name, seq, is_active, note, created_at) "
                     "VALUES (:c, :n, :s, false, :note, :now)"),
                {"c": f"cu_{next_seq}", "n": label[:60], "s": next_seq,
                 "note": "Tự sinh từ dữ liệu cũ — soát lại rồi gộp hoặc bật", "now": now},
            )
            db.commit()
            names = _by_name()
            gid = names[label.lower()]
            next_seq += 1
        db.execute(text("UPDATE employees SET job_grade_id = :g WHERE id = :i"),
                   {"g": gid, "i": emp_id})
    db.commit()


def _migrate_drop_kpi_bonus(db: Session) -> None:
    """Xoá hẳn thưởng năng suất KPI (chủ 29/07/2026 — "xưởng không dùng tới, xóa backend luôn,
    đang phát triển mà chưa chạy thật đâu").

    Gỡ 2 cột `payroll_lines.kpi_percent` / `kpi_bonus` và các dòng bật/tắt KPI theo tổ.

    🔴 **HÃM AN TOÀN — đừng gỡ.** DROP COLUMN là thao tác KHÔNG LÙI ĐƯỢC: mất là mất luôn, trong
    DB không còn bản sao nào để khôi phục. DB dev thì đọc được (0 dòng có tiền KPI) nhưng DB thật
    trên VPS thì KHÔNG. Nên trước khi drop phải ĐẾM: còn dòng lương nào mang tiền KPI thì **bỏ
    qua, giữ nguyên cột**.

    Bỏ sót vài cột thừa trên một DB nào đó là vô hại — SQLAlchemy chỉ đọc cột đã khai trong model.
    Xoá nhầm tiền của người ta thì không cứu được. Chọn phía an toàn.

    Guard theo cột ⇒ chạy lần hai là no-op; DB dựng mới bằng `create_all` không có 2 cột này nên
    tự bỏ qua."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()

    if "payroll_lines" in tables:
        cols = _existing_columns(insp, "payroll_lines")
        con = [c for c in ("kpi_percent", "kpi_bonus") if c in cols]
        if con:
            dieu_kien = " OR ".join(f"{c} <> 0" for c in con)
            con_tien = int(db.execute(text(
                f"SELECT COUNT(*) FROM payroll_lines WHERE {dieu_kien}")).scalar() or 0)
            if con_tien:
                # KHÔNG drop. Giữ cột + số; chủ soi rồi quyết, chứ máy không tự xoá tiền.
                print(f"[0130] BO QUA drop cot KPI: con {con_tien} dong luong mang tien KPI. "
                      f"Cot giu nguyen (vo hai — model khong doc nua).")
            else:
                for c in con:
                    db.execute(text(f"ALTER TABLE payroll_lines DROP COLUMN {c}"))
                db.commit()

    # Dòng bật/tắt KPI theo tổ: chỉ là cấu hình, xoá vô điều kiện (không phải tiền).
    if "department_salary_components" in tables:
        db.execute(text("DELETE FROM department_salary_components WHERE component_key = 'kpi'"))
        db.commit()


def _migrate_job_grade_drop_phu(db: Session) -> None:
    """Bỏ bậc PHỤ: 3 chính + 2 phụ → **5 bậc chính** Bậc 1…Bậc 5 (chủ 2026-07-29, chốt lại trong
    ngày: *"bỏ phụ đi cho 5 bậc chính đánh từ bậc 1 đến bậc 5"*).

    Đổi tên **TẠI CHỖ, GIỮ NGUYÊN `id`** — không xoá rồi seed lại. Ai đang mang bậc thì
    `employees.job_grade_id` vẫn trỏ đúng dòng đó, không mất bậc, không cần gán lại.

    Ánh xạ theo mức lương giảm dần của bảng lương thật 2026 (25/22/20tr rồi 14,5/10,5tr) nên
    Phụ 1–2 rơi đúng xuống Bậc 4–5, thứ tự tay nghề giữ nguyên.

    Chỉ đụng dòng CÒN NGUYÊN tên seed cũ: chủ đã đổi tên bậc nào thì giữ tên đó (chỉ chuẩn hoá
    `code`), không đè công khai báo của chủ."""
    insp = inspect(db.get_bind())
    if "job_grades" not in insp.get_table_names():
        return
    doi = (("tho_1", "bac_1", "Bậc 1", 1), ("tho_2", "bac_2", "Bậc 2", 2),
           ("tho_3", "bac_3", "Bậc 3", 3), ("phu_1", "bac_4", "Phụ 1", "Bậc 4"),
           ("phu_2", "bac_5", "Phụ 2", "Bậc 5"))
    for row in doi:
        ma_cu, ma_moi = row[0], row[1]
        ten_cu = row[2] if isinstance(row[3], str) else None
        ten_moi = row[3] if isinstance(row[3], str) else row[2]
        seq_moi = int(ma_moi[-1])
        cur = db.execute(text("SELECT id, name FROM job_grades WHERE code = :c"),
                         {"c": ma_cu}).first()
        if cur is None:
            continue                       # DB mới đã seed thẳng bac_* → không có gì để đổi
        if db.execute(text("SELECT 1 FROM job_grades WHERE code = :c"),
                      {"c": ma_moi}).first():
            continue                       # đã có bậc mới trùng mã → đừng đụng, tránh vỡ UNIQUE
        # Tên: chỉ đổi khi chủ CHƯA sửa tay (tên còn đúng tên seed cũ).
        con_nguyen = cur[1] == (ten_cu if ten_cu is not None else ten_moi)
        db.execute(
            text("UPDATE job_grades SET code = :cm, seq = :s"
                 + (", name = :n" if con_nguyen else "") + " WHERE id = :i"),
            ({"cm": ma_moi, "s": seq_moi, "n": ten_moi, "i": cur[0]} if con_nguyen
             else {"cm": ma_moi, "s": seq_moi, "i": cur[0]}),
        )
    db.commit()


def _migrate_noi_quy_nguon_va_file_goc(db: Session) -> None:
    """Nội quy: khai NGUỒN của từng bản + đánh dấu file gốc của lần nhập (chủ 30/07/2026 —
    *"nếu họ đưa pdf hoặc word lên thì… form chữ kiểu chữ dáng chữ vẫn giữ nguyên"*).

    Hai cột:

    - `noi_quy_versions.source_kind` — `'html'` (gõ trong app) hay `'file'` (tải tài liệu lên,
      hiện đúng bản gốc). Mỗi BẢN khai đúng MỘT nguồn: để cả hai cùng sống trên một bản thì sớm
      muộn chúng lệch nhau và không ai biết bản nào đang là luật. Mặc định `'html'` nên mọi bản
      cũ giữ nguyên hành vi hiện tại.
    - `noi_quy_attachments.is_import_source` — file GỐC do hệ thống tự đính khi nhập. Nhập lại thì
      hàng này bị thay, không cộng dồn: nhập 3 lần mà để lại 3 file gần giống nhau thì lúc tranh
      chấp không ai biết bản nào là bản thật. Mặc định `false` ⇒ mọi file người dùng đã tự đính
      kèm trước đây được coi là chứng từ và KHÔNG bao giờ bị thay.

    Bảng `noi_quy_pages` là bảng MỚI nên `create_all` tự tạo — không cần làm gì ở đây.

    Guard theo cột ⇒ chạy lần hai là no-op; DB dựng mới bằng `create_all` đã có sẵn 2 cột nên tự
    bỏ qua."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()

    if ("noi_quy_versions" in tables
            and "source_kind" not in _existing_columns(insp, "noi_quy_versions")):
        db.execute(text(
            "ALTER TABLE noi_quy_versions "
            "ADD COLUMN source_kind VARCHAR(8) NOT NULL DEFAULT 'html'"))

    if ("noi_quy_attachments" in tables
            and "is_import_source" not in _existing_columns(insp, "noi_quy_attachments")):
        # `false` (bool Python) chứ KHÔNG phải "0": chuỗi "0" chạy được trên SQLite nhưng VỠ khi
        # Postgres tạo cột Boolean — bẫy đã ghi trong CLAUDE.md.
        db.execute(text(
            "ALTER TABLE noi_quy_attachments "
            "ADD COLUMN is_import_source BOOLEAN NOT NULL DEFAULT false"))
    db.commit()


def _migrate_nguong_to_truong_theo_san_luong(db: Session) -> None:
    """Ngưỡng xét thưởng/phạt tổ trưởng: đo bằng TIỀN → đo bằng SẢN LƯỢNG (chủ 30/07/2026).

    Chủ nhìn màn thật rồi nói: *"nó là sản lượng mà sao lại chữ đ là sao"*. Ô đang là tiền, nhưng
    trong đầu chủ nó là số lượng làm được — và màn hình là phép thử cuối.

    Bê THẲNG con số cũ sang cột mới (chủ chốt: `3.000.000 đ` → `3.000.000 sản lượng`). Ngưỡng là
    một con số trần, **không kèm đơn vị** — chủ chốt *"Đơn vị bỏ đi"*.

    Bảng này mới dựng cùng ngày và chưa từng lên prod; trên DB dev nó đang **0 dòng** nên thực tế
    không có gì để bê. Vẫn viết bước bê cho đúng ý và cho DB nào lỡ có dữ liệu.

    Guard theo cột ⇒ chạy lần hai là no-op. Bảng chưa tồn tại (DB trắng, `create_all` sẽ dựng đúng
    hình mới) thì bỏ qua."""
    insp = inspect(db.get_bind())
    if "piece_leader_bonus_settings" not in insp.get_table_names():
        return

    cols = _existing_columns(insp, "piece_leader_bonus_settings")
    if "min_output_qty" not in cols:
        db.execute(text(
            "ALTER TABLE piece_leader_bonus_settings "
            "ADD COLUMN min_output_qty NUMERIC(14,2) NOT NULL DEFAULT 0"))
    db.commit()

    if "min_khoan_to" in cols:
        db.execute(text(
            "UPDATE piece_leader_bonus_settings SET min_output_qty = min_khoan_to "
            "WHERE min_output_qty = 0 AND min_khoan_to <> 0"))
        db.commit()
        db.execute(text("ALTER TABLE piece_leader_bonus_settings DROP COLUMN min_khoan_to"))
        db.commit()


def _migrate_noi_quy_nhieu_tai_lieu(db: Session) -> None:
    """Nội quy: một bản ban hành → NHIỀU tài liệu, mỗi tài liệu một chuỗi version riêng
    (chủ 30/07/2026 — *"upload được nhiều file, mỗi file đi theo title"*).

    Gắn mọi bản nội quy đang có vào ĐÚNG MỘT tài liệu. Chúng vốn là các lần ban hành lại của cùng
    một văn bản, nên gom vào một tài liệu là đúng — KHÔNG tách thành nhiều tài liệu.

    Tiêu đề mặc định là HẰNG CHUỖI viết thẳng ở đây. Đã cân nhắc và loại hai nguồn "thông minh" hơn:
      - `ghi_chu` — đó là *ghi chú thay đổi* ("Bổ sung quy định giờ tăng ca"), đặt làm tên tài liệu
        thì sai mà nhìn vẫn hợp lý, loại sai tệ nhất.
      - tên file gốc — ra "mau-noi-quy-lao-dong.pdf".
    Chủ đổi tên trong màn hình mất 5 giây. Migration không đoán được thì migration không đoán.

    Bảng `noi_quy_documents` là bảng MỚI ⇒ `create_all` lo; ở đây chỉ thêm cột + backfill."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "noi_quy_versions" not in tables:
        return
    if "noi_quy_documents" not in tables:
        # `create_all` chạy TRƯỚC migration, nên tới đây mà chưa có bảng nghĩa là model chưa được
        # export. Tự `CREATE TABLE` ở đây sẽ đẻ ra một bảng lệch với model — im lặng bỏ qua.
        return

    cols = _existing_columns(insp, "noi_quy_versions")
    # NULLABLE, không NOT NULL: Postgres từ chối `ADD COLUMN NOT NULL` không default khi bảng đã có
    # dòng — mà ở đây KHÔNG có default hợp lý (tài liệu chưa tồn tại lúc thêm cột).
    if "document_id" not in cols:
        db.execute(text("ALTER TABLE noi_quy_versions ADD COLUMN document_id INTEGER"))
    if "title" not in cols:
        db.execute(text("ALTER TABLE noi_quy_versions ADD COLUMN title VARCHAR(200)"))
    db.commit()

    # Guard theo DỮ LIỆU MỒ CÔI, không theo "đã insert tài liệu nào chưa": chạy lần hai là no-op,
    # và nếu chủ đã tự tạo tài liệu thật rồi thì KHÔNG đẻ thêm một tài liệu rác nữa.
    mo_coi = int(db.execute(text(
        "SELECT COUNT(*) FROM noi_quy_versions WHERE document_id IS NULL")).scalar() or 0)
    if not mo_coi:
        return

    ten = "Nội quy lao động"
    db.execute(
        text("INSERT INTO noi_quy_documents (title, seq, is_active, created_at) "
             "VALUES (:t, 1, true, :now)"),
        {"t": ten, "now": datetime.now(timezone.utc)},
    )
    db.commit()
    doc_id = db.execute(text("SELECT MIN(id) FROM noi_quy_documents")).scalar()

    # Gắn HẾT — cả published lẫn draft. Bỏ sót bản nào là bản đó thành mồ côi: không tài liệu nào
    # trỏ tới ⇒ cả công ty mở nội quy ra thấy "chưa ban hành", dù dòng vẫn nằm nguyên trong DB.
    db.execute(text("UPDATE noi_quy_versions SET document_id = :d WHERE document_id IS NULL"),
               {"d": doc_id})
    # Tiêu đề bản chụp: bản cũ chưa có, lấy tên tài liệu làm mốc.
    db.execute(text("UPDATE noi_quy_versions SET title = :t WHERE title IS NULL"), {"t": ten})
    db.commit()

    con_sot = int(db.execute(text(
        "SELECT COUNT(*) FROM noi_quy_versions WHERE document_id IS NULL")).scalar() or 0)
    if con_sot:
        # NỔ chứ không đi tiếp. `run_migrations` không bọc try/except nên app chết lúc khởi động và
        # `0132` KHÔNG được ghi vào `schema_migrations` ⇒ lần sau chạy lại. Thà không boot còn hơn
        # boot với nội quy mồ côi mà không ai biết.
        raise RuntimeError(
            f"[0132] Con {con_sot} ban noi quy chua gan tai lieu — DUNG de khong mat du lieu.")


def _migrate_employee_salary_commission_pct(db: Session) -> None:
    """% hoa hồng cho nhân viên kinh doanh (chủ 29/07/2026 — "khai phần trăm hoa hồng cho nhân
    viên sale").

    Đặt trên `employee_salaries` (không phải `employees`) để có LỊCH SỬ miễn phí: bảng này vốn
    mỗi lần khai là một bản ghi mới theo `effective_from`. Đổi % từ tháng 8 thì kỳ tháng 7 tính
    lại vẫn ra số cũ.

    Lưu PHÂN SỐ (0.05 = 5%), đúng quy ước `cong_doan_rate` / `phat_cap_pct`. Đợt này CHỈ KHAI —
    engine lương không đọc cột này, khai bao nhiêu cũng không đổi một đồng nào."""
    insp = inspect(db.get_bind())
    if ("employee_salaries" in insp.get_table_names()
            and "commission_pct" not in _existing_columns(insp, "employee_salaries")):
        db.execute(text(
            "ALTER TABLE employee_salaries "
            "ADD COLUMN commission_pct NUMERIC(6,4) NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_piece_rate_unit_free_text(db: Session) -> None:
    """Đơn vị đơn giá khoán: nới 12→24 ký tự và đổi MÃ cũ sang CHỮ hiển thị (chủ 29/07/2026).

    Trước đây `unit` lưu mã (`m2`, `bai_in`) rồi FE dịch sang nhãn (`m²`, `bài in`). Nay ô Đơn vị
    cho gõ tự do + gợi ý, nên giữ tầng mã là hỏng: bấm gợi ý "m²" lưu ra chuỗi KHÁC với mã "m2"
    của dòng cũ ⇒ hai dòng cùng nghĩa, khác giá trị, thống kê không gom được.

    An toàn: `unit` thuần NHÃN HIỂN THỊ, không logic nào rẽ nhánh theo nó (hằng `PIECE_UNITS` cũ
    khai ra rồi không ai dùng). Idempotent: chạy lại không đổi gì vì mã cũ đã hết."""
    insp = inspect(db.get_bind())
    if "piece_rates" not in insp.get_table_names():
        return
    # Postgres ép độ dài VARCHAR nên phải ALTER; SQLite thì không ⇒ bỏ qua là đúng.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("ALTER TABLE piece_rates ALTER COLUMN unit TYPE VARCHAR(24)"))
    for ma, nhan in (("m2", "m²"), ("bai_in", "bài in"), ("tan", "tấn"), ("cuon", "cuốn"),
                     ("luot", "lượt"), ("hop", "hộp"), ("to", "tờ"), ("khac", "khác")):
        db.execute(text("UPDATE piece_rates SET unit = :nhan WHERE unit = :ma"),
                   {"nhan": nhan, "ma": ma})
    db.commit()


def _migrate_move_bonus_columns_to_components(db: Session) -> None:
    """Dời 6 cột thưởng nhập tay sang khoản DANH MỤC (chủ 28/07/2026).

    Chủ: *"khoản 5s hay thưởng gì thì cho nó select từ quy tắc, để coi nó chịu thuế hay không"*.
    6 ô tay (`thuong_5s`, `thuong_doanh_so`, `thuong_thanh_tich`, `phep_nam`, `tra_dong_phuc`,
    `other_bonus`) vốn bị ĐÓNG ĐINH chịu thuế, nay khai qua danh mục để cờ `is_taxable` dùng chung.

    ⚠️ CHỈ đụng kỳ `draft`. Kỳ đã CHỐT/ĐÃ CHI giữ nguyên cột cũ — phiếu lương đã ký của người lao
    động không được đổi một đồng nào, và engine vẫn cộng các cột đó nên số cũ vẫn đúng.

    Tiền KHÔNG đổi: mỗi đồng rời khỏi cột thì vào đúng một dòng `payroll_line_components`
    (`source='line'` — khoản của RIÊNG kỳ này, không lặp sang kỳ sau, và sống sót "Tính lại")."""
    insp = inspect(db.get_bind())
    names = insp.get_table_names()
    for t in ("payroll_lines", "payroll_line_components", "payroll_components", "payroll_periods"):
        if t not in names:
            return
    cols = {c["name"] for c in insp.get_columns("payroll_lines")}
    # `phep_nam` + `other_bonus` không có khoản danh mục riêng (cố ý — xem `_RESERVED` và seed):
    # dồn vào khoản MỞ "Thu nhập khác (chịu thuế)", ghi rõ nguồn ở `note` để không mất dấu vết.
    plan = (
        ("thuong_5s",         "thuong_5s",        None),
        ("thuong_doanh_so",   "thuong_doanh_so",  None),
        ("thuong_thanh_tich", "thuong_thanh_tich", None),
        ("tra_dong_phuc",     "tra_dong_phuc",    None),
        ("phep_nam",          "thu_nhap_khac_ct", "Phép năm (cột cũ)"),
        ("other_bonus",       "thu_nhap_khac_ct", "Thưởng khác (cột cũ)"),
    )
    plan = [p for p in plan if p[0] in cols]
    if not plan:
        return
    comp = {
        r[0]: r for r in db.execute(text(
            "SELECT code, id, name, kind, is_taxable FROM payroll_components")).all()
    }
    # Thiếu khoản đích (chủ đã xoá tay) ⇒ BỎ QUA cột đó, để nguyên tiền ở cột cũ. Thà hiện ở khối
    # "Khoản kỳ cũ" chỉ đọc còn hơn làm bay mất tiền của người lao động.
    plan = [p for p in plan if p[1] in comp]
    if not plan:
        return

    src = ", ".join(p[0] for p in plan)
    rows = db.execute(text(
        f"SELECT l.id, {src} FROM payroll_lines l "
        "JOIN payroll_periods p ON p.id = l.period_id WHERE p.status = 'draft'"
    )).all()
    for row in rows:
        line_id = row[0]
        taken = {
            r[0] for r in db.execute(
                text("SELECT component_id FROM payroll_line_components WHERE line_id = :l"),
                {"l": line_id}).all()
        }
        # Gộp theo khoản ĐÍCH: `phep_nam` và `other_bonus` cùng trỏ "Thu nhập khác (chịu thuế)"
        # nên phải cộng vào MỘT dòng — hai dòng sẽ vướng UNIQUE(line_id, component_id).
        bucket: dict[int, list] = {}
        cleared: list[str] = []
        for i, (col, code, label) in enumerate(plan, start=1):
            amount = float(row[i] or 0)
            if not amount:
                continue
            code_, cid, cname, ckind, ctax = comp[code]
            if cid in taken:
                # Dòng khoản này đã tồn tại (HCNS tự thêm trước đó) ⇒ không đụng vào, giữ nguyên
                # cột cũ. Cộng thêm vào số của người dùng là sửa dữ liệu sau lưng họ.
                continue
            slot = bucket.setdefault(cid, [code_, cname, ckind, ctax, 0.0, []])
            slot[4] += amount
            slot[5].append(label or "Chuyển từ cột cũ")
            cleared.append(col)
        for cid, (code_, cname, ckind, ctax, amount, labels) in bucket.items():
            db.execute(text(
                "INSERT INTO payroll_line_components "
                "(line_id, component_id, code, name, kind, is_taxable, amount, source, note) "
                "VALUES (:l, :c, :code, :n, :k, :t, :a, 'line', :note)"),
                # `is_taxable` là BOOLEAN: `ctax` đọc ra là bool (Postgres) hay int (SQLite) đều
                # phải ép về bool, nếu không Postgres báo DatatypeMismatch.
                {"l": line_id, "c": cid, "code": code_, "n": cname, "k": ckind,
                 "t": bool(ctax), "a": amount, "note": " · ".join(labels)[:255]})
        if cleared:
            sets = ", ".join(f"{c} = 0" for c in cleared)
            db.execute(text(f"UPDATE payroll_lines SET {sets} WHERE id = :l"), {"l": line_id})
    db.commit()


def _migrate_drop_duplicate_payroll_components(db: Session) -> None:
    """Dọn các khoản danh mục TRÙNG với cột đã có (lỗi seed đợt đầu 27/07/2026).

    Bản seed đầu liệt kê cả tăng ca / chuyên cần / phụ cấp ca / thưởng / khoán / các khoản phạt —
    những thứ ĐÃ CÓ ô khai riêng và engine đã tự tính. Khai tiền ở cả hai chỗ là TRẢ HAI LẦN.
    Seed là seed-once nên bản sửa không tự dọn được dữ liệu đã tạo.

    CHỈ xoá khoản chưa hề dùng: không có dòng lương nào, không có mức khai theo nhóm hay theo
    người. Khoản đã dùng thì để nguyên cho chủ tự quyết — dữ liệu của người dùng, không tự xoá."""
    insp = inspect(db.get_bind())
    names = insp.get_table_names()
    if "payroll_components" not in names:
        return
    dup = (
        "them_gio_150", "them_gio_200", "chuyen_can_pc", "phu_cap_ca_dem",
        "thuong_thanh_tich", "thuong_doanh_so", "thuong_5s", "luong_san_luong",
        "tra_dong_phuc", "phat_bien_ban", "dt_vuot_troi", "phat_5s",
        "di_tre_ve_som", "tru_loi_khoan",
    )
    marks = ", ".join(f"'{c}'" for c in dup)
    used = []
    for tbl, col in (("payroll_line_components", "component_id"),
                     ("payroll_group_components", "component_id"),
                     ("employee_salary_components", "component_id")):
        if tbl in names:
            used.append(f"SELECT {col} FROM {tbl}")
    guard = f" AND id NOT IN ({' UNION '.join(used)})" if used else ""
    db.execute(text(f"DELETE FROM payroll_components WHERE code IN ({marks}){guard}"))
    db.commit()


def _migrate_payroll_line_thu_nhap_mien_thue(db: Session) -> None:
    """Danh mục khoản thu nhập (chủ 2026-07-27): `payroll_lines.thu_nhap_mien_thue` — tổng phần
    thu nhập được MIỄN thuế của kỳ, để phiếu lương giải trình số thuế. Phần chịu thuế đã có sẵn ở
    cột `pit_taxable`, không thêm cột trùng.
    Guard theo cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if "payroll_lines" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "payroll_lines")
    if "thu_nhap_mien_thue" not in cols:
        db.execute(text(
            "ALTER TABLE payroll_lines ADD COLUMN thu_nhap_mien_thue NUMERIC(14,2) NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_payroll_adjust_max_per_month(db: Session) -> None:
    """Hạn mức chỉnh công (chủ 2026-07-27): `payroll_params.adjust_max_per_month` — mỗi NV tự gửi
    yêu cầu chỉnh công cho tối đa ngần này NGÀY CÔNG mỗi tháng. 0 = không giới hạn.
    Guard theo cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if ("payroll_params" in insp.get_table_names()
            and "adjust_max_per_month" not in _existing_columns(insp, "payroll_params")):
        db.execute(text(
            "ALTER TABLE payroll_params ADD COLUMN adjust_max_per_month INTEGER NOT NULL DEFAULT 5"))
    db.commit()


def _migrate_payroll_advance_max_pct(db: Session) -> None:
    """Trần tạm ứng (chủ 2026-07-23): `payroll_params.advance_max_pct` — tổng tạm ứng 1 tháng của 1 NV
    không vượt tỷ lệ này × (lương vị trí + trách nhiệm). 0 = không giới hạn.
    Guard theo cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if ("payroll_params" in insp.get_table_names()
            and "advance_max_pct" not in _existing_columns(insp, "payroll_params")):
        db.execute(text("ALTER TABLE payroll_params ADD COLUMN advance_max_pct NUMERIC(6,4) NOT NULL DEFAULT 0.1"))
    db.commit()


def _migrate_salary_luong_dot_1(db: Session) -> None:
    """Lương đợt 1 (chủ 2026-07-24): `employee_salaries.luong_dot_1` — mức trả 1 lần cố định theo hồ sơ.
    Guard theo cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if ("employee_salaries" in insp.get_table_names()
            and "luong_dot_1" not in _existing_columns(insp, "employee_salaries")):
        db.execute(text("ALTER TABLE employee_salaries ADD COLUMN luong_dot_1 NUMERIC(14,2) NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_salary_advance_kind(db: Session) -> None:
    """Phân loại phiếu (chủ 2026-07-24): `salary_advances.kind` = tam_ung | luong_dot_1. Mặc định tam_ung
    (hàng cũ = tạm ứng). Guard theo cột → idempotent."""
    insp = inspect(db.get_bind())
    if ("salary_advances" in insp.get_table_names()
            and "kind" not in _existing_columns(insp, "salary_advances")):
        db.execute(text("ALTER TABLE salary_advances ADD COLUMN kind VARCHAR(16) NOT NULL DEFAULT 'tam_ung'"))
    db.commit()


def _migrate_payroll_line_luong_dot_1_total(db: Session) -> None:
    """Snapshot lương đợt 1 đã duyệt của kỳ (chủ 2026-07-24): `payroll_lines.luong_dot_1_total`.
    Guard theo cột → idempotent."""
    insp = inspect(db.get_bind())
    if ("payroll_lines" in insp.get_table_names()
            and "luong_dot_1_total" not in _existing_columns(insp, "payroll_lines")):
        db.execute(text("ALTER TABLE payroll_lines ADD COLUMN luong_dot_1_total NUMERIC(14,2) NOT NULL DEFAULT 0"))
    db.commit()


def _migrate_piece_rate_department_id(db: Session) -> None:
    """Lương khoán: gắn đơn giá `piece_rates` vào TỔ cụ thể (departments.id) để khai đơn giá
    ngay trong Cấu hình lương của tổ. Cột nullable — đơn giá cũ/chưa gắn tổ vẫn hợp lệ.
    Guard theo cột → idempotent, no-op trên DB create_all mới / bảng chưa có."""
    insp = inspect(db.get_bind())
    if ("piece_rates" in insp.get_table_names()
            and "department_id" not in _existing_columns(insp, "piece_rates")):
        db.execute(text("ALTER TABLE piece_rates ADD COLUMN department_id INTEGER"))
    db.commit()


def _migrate_drop_lenh_sx_cu(db: Session) -> None:
    """DỌN NỀN module Kế hoạch SX cũ: DROP 8 bảng của bản đã gỡ (commit `bcefd1c` xoá tầng code
    nhưng GIỮ bảng). Module mới dựng bảng TÊN KHÁC (`lsx` / `lsx_cong_doan`), nên bảng cũ chỉ còn
    là rác — mà để lại thì `create_all` không đụng tới, dữ liệu mồ côi nằm mãi trên prod.

    Drop CON TRƯỚC CHA để khỏi vướng FK; Postgres thêm CASCADE (SQLite bỏ qua từ khoá này nên tách
    2 nhánh theo dialect). Best-effort từng bảng: bảng nào không có thì bỏ qua, no-op trên DB fresh.
    Các migration 0079–0087 (ALTER mấy bảng này) GIỮ NGUYÊN — chúng đã tự guard "bảng chưa có → return".
    """
    is_pg = (db.get_bind().dialect.name or "").startswith("postgres")
    for table in (
        "routing_step_assignment", "san_luong", "ban_giao", "gang_placement",
        "lenh_item", "routing_step", "print_form", "lenh_sx",
    ):
        try:
            db.execute(text(f"DROP TABLE IF EXISTS {table}{' CASCADE' if is_pg else ''}"))
            db.commit()
        except Exception:
            db.rollback()


# (tên cột, định nghĩa SQL) cho `lsx_cong_doan` ở migration 0093. Mọi cột NOT NULL đều kèm DEFAULT
# nên ALTER chạy được trên bảng đã có dữ liệu. BOOLEAN dùng literal `TRUE` (KHÔNG phải '1') — chuỗi
# '1' chạy SQLite nhưng vỡ khi Postgres tạo bảng trắng.
_LSX_CD_COLS_0093: tuple[tuple[str, str], ...] = (
    # Nhận diện bước
    ("loai_buoc", "VARCHAR(12) NOT NULL DEFAULT 'may'"),
    ("bat_buoc", "BOOLEAN NOT NULL DEFAULT TRUE"),
    # Số lượng & hao hụt (cặp Scrap Factor % + Fixed Scrap Qty)
    ("don_vi_vao", "VARCHAR(8) NOT NULL DEFAULT 'to'"),
    ("don_vi_ra", "VARCHAR(8) NOT NULL DEFAULT 'to'"),
    ("he_so_quy_doi", "NUMERIC(12,4) NOT NULL DEFAULT 1"),
    ("hao_hut_pct", "NUMERIC(6,2) NOT NULL DEFAULT 0"),
    ("so_luot_chay", "INTEGER NOT NULL DEFAULT 1"),
    # Năng suất & thời gian (nguồn cho Gantt)
    ("setup_phut", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
    ("nang_suat", "NUMERIC(12,2)"),
    ("don_vi_nang_suat", "VARCHAR(10)"),
    ("chay_phut", "NUMERIC(10,2)"),
    ("ve_sinh_phut", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
    ("cho_phut", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
    ("di_chuyen_phut", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
    ("so_nhan_cong", "INTEGER NOT NULL DEFAULT 1"),
    # Phương thức thực hiện
    ("may_thay_the_ids", "JSON"),
    ("dieu_kien_json", "JSON"),
    # Gia công ngoài (§8)
    ("sl_gui", "NUMERIC(14,2)"),
    ("ngay_gui_dk", "DATE"),
    ("van_chuyen_ngay", "NUMERIC(6,2)"),
    ("gia_cong_ngay", "NUMERIC(6,2)"),
    ("ngay_nhan_dk", "DATE"),
    ("hao_hut_cho_phep", "NUMERIC(14,2)"),
    ("don_gia_gia_cong", "NUMERIC(18,2)"),
    ("yeu_cau_ky_thuat", "TEXT"),
    ("nguoi_giao_nhan_id", "INTEGER"),
)

# Suy `loai_buoc` từ TÊN bước khi backfill (bản cũ chỉ có cờ `thue_ngoai` + `nhom`). Chạy trong
# Python chứ không LIKE trong SQL: SQLite `LOWER()` không hạ được chữ có dấu tiếng Việt.
_TEN_LOAI_BUOC_0093: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("kcs", ("kcs", "kiểm tra", "kiem tra", "duyệt màu", "duyet mau")),
    ("cho", ("chờ", "cho kho", "khô mực", "kho muc", "khô keo", "kho keo")),
    ("xa_to", ("xả tờ", "xa to", "chia bán thành phẩm", "chia ban thanh pham")),
    ("to", ("dán", "dan tay", "gấp", "gap tay", "đóng gói", "dong goi", "vào bìa", "vao bia",
            "đóng cuốn", "dong cuon", "bao bì", "bao bi")),
)


def _migrate_lsx_routing_chi_tiet(db: Session) -> None:
    """Routing lệnh SX lát 2: bổ sung dữ liệu để xếp được Gantt + khối gia công ngoài đầy đủ.

    Thêm 26 cột `lsx_cong_doan` (loại bước · đơn vị vào/ra + hệ số quy đổi · hao hụt % · năng suất
    và 4 loại thời gian · số nhân công · điều kiện bắt đầu · 9 cột thuê ngoài) + `lsx.routing_goc_json`
    (ảnh chụp routing lúc tạo, để cảnh báo "routing đã đổi so với bài tính giá").

    Rồi BỎ hai cột cũ đã bị thay: `thue_ngoai` (tập con của `loai_buoc`) và `don_vi` (tách thành
    `don_vi_vao`/`don_vi_ra`) — giữ lại sẽ thành hai nguồn sự thật. DROP là best-effort: SQLite
    < 3.35 từ chối thì để cột mồ côi, vô hại vì model không map nữa và cả hai đều có DEFAULT.

    Idempotent, no-op trên DB fresh (create_all đã ra schema mới) và trên DB chưa có bảng `lsx`."""
    bind = db.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "lsx_cong_doan" not in tables:
        return

    def run(sql: str) -> None:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    cols = _existing_columns(insp, "lsx_cong_doan")
    for name, ddl in _LSX_CD_COLS_0093:
        if name not in cols:
            db.execute(text(f"ALTER TABLE lsx_cong_doan ADD COLUMN {name} {ddl}"))
    if "routing_goc_json" not in _existing_columns(insp, "lsx"):
        db.execute(text("ALTER TABLE lsx ADD COLUMN routing_goc_json JSON"))
    db.commit()
    run("CREATE INDEX IF NOT EXISTS ix_lsx_cong_doan_nguoi_giao_nhan_id "
        "ON lsx_cong_doan (nguoi_giao_nhan_id)")

    # --- Backfill từ schema cũ (chỉ khi cột cũ còn) ---
    if "don_vi" in cols:
        db.execute(text("UPDATE lsx_cong_doan SET don_vi_vao = don_vi, don_vi_ra = don_vi "
                        "WHERE don_vi IS NOT NULL AND don_vi <> ''"))
        db.commit()
    if "thue_ngoai" in cols:
        db.execute(text("UPDATE lsx_cong_doan SET loai_buoc = 'thue_ngoai' WHERE thue_ngoai"))
        db.commit()
        # Bước nội bộ: mặc định 'may', hạ về 'to'/'kcs'/'cho'/'xa_to' theo tên (thủ công/kiểm/chờ).
        rows = db.execute(text(
            "SELECT id, ten FROM lsx_cong_doan WHERE loai_buoc <> 'thue_ngoai'"
        )).all()
        for row_id, ten in rows:
            low = (ten or "").strip().lower()
            for loai, keys in _TEN_LOAI_BUOC_0093:
                if any(k in low for k in keys):
                    db.execute(
                        text("UPDATE lsx_cong_doan SET loai_buoc = :l WHERE id = :i"),
                        {"l": loai, "i": row_id},
                    )
                    break
        db.commit()

    # --- Bỏ cột đã bị thay (best-effort) ---
    run("ALTER TABLE lsx_cong_doan DROP COLUMN thue_ngoai")
    run("ALTER TABLE lsx_cong_doan DROP COLUMN don_vi")


def _migrate_cong_doan_nang_suat(db: Session) -> None:
    """Thêm `cong_doan.nang_suat` (output/giờ) — năng suất mặc định khi lên Lệnh sản xuất.

    Dành cho bước KHÔNG gắn máy: máy có `may_thiet_bi.toc_do` riêng, còn việc làm tay (dán, đóng
    gói) thì năng suất thuộc về công đoạn — không có ô này thì kế hoạch phải gõ lại ở MỌI lệnh.
    NULL = chưa khai (routing để trống, không bịa số 0). Đơn vị KHÔNG lưu: suy từ đơn vị đầu vào
    của bước. Idempotent; no-op trên DB fresh (create_all đã ra cột) hoặc khi bảng chưa có."""
    insp = inspect(db.get_bind())
    if "cong_doan" not in insp.get_table_names():
        return
    if "nang_suat" not in _existing_columns(insp, "cong_doan"):
        db.execute(text("ALTER TABLE cong_doan ADD COLUMN nang_suat NUMERIC(12,2)"))
    db.commit()


def _migrate_work_shift_dung_cho_lich_may(db: Session) -> None:
    """Thêm `work_shifts.dung_cho_lich_may` (BOOLEAN NOT NULL DEFAULT FALSE) — đánh dấu ca nào thuộc
    LỊCH CHẠY MÁY của xưởng (khác ca chấm công HR). Xếp lịch công đoạn (Gantt theo máy) tính giờ theo
    TẬP ca có cờ này (nghỉ trưa = khe giữa 2 ca); chưa tick ca nào → fallback 8h phẳng [08:00,16:00)
    giữ nguyên hành vi lát 1. Idempotent; no-op DB fresh (create_all đã ra cột) / bảng chưa có."""
    insp = inspect(db.get_bind())
    if "work_shifts" not in insp.get_table_names():
        return
    if "dung_cho_lich_may" not in _existing_columns(insp, "work_shifts"):
        db.execute(text(
            "ALTER TABLE work_shifts ADD COLUMN dung_cho_lich_may BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    db.commit()


def _migrate_stock_request_line_ten_tu_do(db: Session) -> None:
    """Đề nghị hàng MỚI gõ tên tự do (spec-kho-de-nghi): thêm `stock_request_lines.ten_tu_do`
    (VARCHAR(255)). material_id để rỗng cho hàng chưa có mã — SQLite/PG không siết lại NOT NULL
    cũ được qua ALTER, nhưng model đã cho nullable nên hàng mới ghi material_id NULL bình thường
    (cột cũ vốn NOT NULL trên DB cũ; hàng free-text chỉ phát sinh SAU migration này). No-op nếu
    bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "stock_request_lines" not in insp.get_table_names():
        return
    if "ten_tu_do" not in _existing_columns(insp, "stock_request_lines"):
        db.execute(text("ALTER TABLE stock_request_lines ADD COLUMN ten_tu_do VARCHAR(255)"))
    # Nới material_id (hàng free-text để rỗng). Postgres nới tại chỗ; SQLite không ALTER được
    # NOT NULL cũ → dev drop dev.db để create_all dựng lại theo model (đã nullable). Tests dùng
    # DB in-memory nên luôn theo model mới.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("ALTER TABLE stock_request_lines ALTER COLUMN material_id DROP NOT NULL"))
    db.commit()


def _migrate_stock_request_line_material_nullable(db: Session) -> None:
    """Nới `stock_request_lines.material_id` → NULLABLE (hàng free-text ở đề nghị để mã rỗng).

    0096 thêm `ten_tu_do` nhưng KHÔNG nới được NOT NULL cũ trên SQLite (không ALTER COLUMN được),
    nên DB dev đã áp 0096 vẫn chèn hàng mới (material_id NULL) là dính IntegrityError. Migration
    này làm nốt việc nới, GIỮ NGUYÊN dữ liệu:
      * Postgres: `ALTER COLUMN ... DROP NOT NULL` tại chỗ.
      * SQLite:   DỰNG LẠI bảng theo model (material_id nullable), copy trọn dữ liệu, tạo lại index.
    Idempotent: nếu material_id đã nullable (DB mới create_all theo model) → no-op.
    """
    insp = inspect(db.get_bind())
    if "stock_request_lines" not in insp.get_table_names():
        return
    cols = {c["name"]: c for c in insp.get_columns("stock_request_lines")}
    mat = cols.get("material_id")
    if mat is None or mat.get("nullable", True):
        return  # đã nullable → không cần làm gì

    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(text("ALTER TABLE stock_request_lines ALTER COLUMN material_id DROP NOT NULL"))
        db.commit()
        return
    if dialect == "sqlite":
        # App KHÔNG bật PRAGMA foreign_keys (mặc định OFF) → drop/rename không bị FK chặn.
        # Bảng _new khớp đúng model: material_id NULLABLE, có ten_tu_do (0096 đã thêm trước).
        db.execute(text(
            "CREATE TABLE stock_request_lines_new ("
            " id INTEGER NOT NULL PRIMARY KEY,"
            " request_id INTEGER NOT NULL,"
            " material_id INTEGER,"
            " ten_tu_do VARCHAR(255),"
            " dvt VARCHAR(16) NOT NULL,"
            " sl_de_nghi NUMERIC(14, 2) NOT NULL CHECK (sl_de_nghi > 0),"
            " sl_duyet NUMERIC(14, 2) NOT NULL DEFAULT '0' CHECK (sl_duyet >= 0),"
            " sl_da_ung NUMERIC(14, 2) NOT NULL DEFAULT '0' CHECK (sl_da_ung >= 0),"
            " ghi_chu VARCHAR(500),"
            " FOREIGN KEY(request_id) REFERENCES stock_requests (id) ON DELETE CASCADE,"
            " FOREIGN KEY(material_id) REFERENCES materials (id)"
            ")"
        ))
        db.execute(text(
            "INSERT INTO stock_request_lines_new"
            " (id, request_id, material_id, ten_tu_do, dvt, sl_de_nghi, sl_duyet, sl_da_ung, ghi_chu)"
            " SELECT id, request_id, material_id, ten_tu_do, dvt, sl_de_nghi, sl_duyet, sl_da_ung,"
            " ghi_chu FROM stock_request_lines"
        ))
        db.execute(text("DROP TABLE stock_request_lines"))
        db.execute(text("ALTER TABLE stock_request_lines_new RENAME TO stock_request_lines"))
        db.execute(text(
            "CREATE INDEX ix_stock_request_lines_request_id ON stock_request_lines (request_id)"
        ))
        db.execute(text(
            "CREATE INDEX ix_stock_request_lines_material_id ON stock_request_lines (material_id)"
        ))
        db.commit()


def _migrate_material_kho_conversion(db: Session) -> None:
    """Quy đổi đơn vị KHO (spec-kho-de-nghi): thêm `materials.don_vi_phu` (VARCHAR(16)) +
    `materials.he_so_quy_doi` (NUMERIC(14,4)). Nullable. No-op DB fresh / cột đã có."""
    insp = inspect(db.get_bind())
    if "materials" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "materials")
    if "don_vi_phu" not in cols:
        db.execute(text("ALTER TABLE materials ADD COLUMN don_vi_phu VARCHAR(16)"))
    if "he_so_quy_doi" not in cols:
        db.execute(text("ALTER TABLE materials ADD COLUMN he_so_quy_doi NUMERIC(14,4)"))
    db.commit()


def _migrate_stock_voucher_line_ghi_chu(db: Session) -> None:
    """Ghi chú theo DÒNG phiếu (spec-kho-de-nghi): thêm `stock_voucher_lines.ghi_chu`
    (VARCHAR(500) nullable). No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "stock_voucher_lines" not in insp.get_table_names():
        return
    if "ghi_chu" not in _existing_columns(insp, "stock_voucher_lines"):
        db.execute(text("ALTER TABLE stock_voucher_lines ADD COLUMN ghi_chu VARCHAR(500)"))
    db.commit()


def _migrate_stock_request_kho_id(db: Session) -> None:
    """Kho ĐÍCH của đề nghị (spec-kho-de-nghi): thêm `stock_requests.kho_id` (INTEGER nullable,
    soft → kho_hang.id). Nullable để hàng cũ (đề nghị trước khi có cột) không vỡ; API create
    bắt buộc. No-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "stock_requests" not in insp.get_table_names():
        return
    if "kho_id" not in _existing_columns(insp, "stock_requests"):
        db.execute(text("ALTER TABLE stock_requests ADD COLUMN kho_id INTEGER"))
    db.commit()


def _migrate_role_permission_kho(db: Session) -> None:
    """Phân quyền module Kho (spec-kho-de-nghi §9.1): thêm 4 cột quyền chi tiết vào
    `role_permissions` — can_request (tạo đề nghị), can_view_stock (xem SỐ tồn, thiếu thì
    chỉ thấy đèn tín hiệu), can_view_cost (xem giá vốn), can_set_threshold (khai ngưỡng tồn).
    DEFAULT FALSE (bool, KHÔNG phải '0' — chuỗi chạy SQLite nhưng vỡ Postgres). No-op trên
    DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "role_permissions")
    for col in ("can_request", "can_view_stock", "can_view_cost", "can_set_threshold"):
        if col not in cols:
            db.execute(text(
                f"ALTER TABLE role_permissions ADD COLUMN {col} BOOLEAN NOT NULL DEFAULT FALSE"
            ))
    db.commit()


def _migrate_role_permission_kho_post(db: Session) -> None:
    """Tách GHI SỔ phiếu khỏi LẬP phiếu (SoD): thêm `role_permissions.can_post`. Thủ kho chỉ
    lập nháp (can_create), Kế toán kho/QL kho ghi sổ (can_post). DEFAULT FALSE (bool). No-op
    DB fresh / cột đã có. Seed cấp can_post cho các vai kho phù hợp lúc reseed."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    if "can_post" not in _existing_columns(insp, "role_permissions"):
        db.execute(text(
            "ALTER TABLE role_permissions ADD COLUMN can_post BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    db.commit()


def _migrate_kho_post_thukho_off(db: Session) -> None:
    """SoD: Thủ kho LẬP phiếu nhưng KHÔNG ghi sổ (khớp RolePermission.can_post / BRD §3.19). Seed
    cũ gộp can_post vào cụm "Quản lý kho" nên lỡ cấp cho Thủ kho — gỡ lại. CHỈ đụng vai tên
    'Thủ kho', module kho; QL kho / Kế toán kho giữ nguyên. No-op DB fresh / chưa có bảng."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "role_permissions" not in tables or "roles" not in tables:
        return
    db.execute(text(
        "UPDATE role_permissions SET can_post = FALSE "
        "WHERE module_key = 'kho' AND role_id IN "
        "(SELECT id FROM roles WHERE name = 'Thủ kho')"
    ))
    db.commit()


def _migrate_stock_request_ly_do_huy(db: Session) -> None:
    """Lý do KHO hủy đề nghị (hủy phiếu → đề nghị 'Đã hủy'): thêm stock_requests.ly_do_huy
    (VARCHAR(500) nullable). No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "stock_requests" not in insp.get_table_names():
        return
    if "ly_do_huy" not in _existing_columns(insp, "stock_requests"):
        db.execute(text("ALTER TABLE stock_requests ADD COLUMN ly_do_huy VARCHAR(500)"))
    db.commit()


def _migrate_stock_voucher_nguoi_ghi_so(db: Session) -> None:
    """Lưu AI GHI SỔ phiếu (duyệt/chốt): thêm `stock_vouchers.nguoi_ghi_so_id` (INTEGER nullable,
    soft → users.id). Null cho phiếu cũ. No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "stock_vouchers" not in insp.get_table_names():
        return
    if "nguoi_ghi_so_id" not in _existing_columns(insp, "stock_vouchers"):
        db.execute(text("ALTER TABLE stock_vouchers ADD COLUMN nguoi_ghi_so_id INTEGER"))
    db.commit()


def _migrate_stock_request_line_don_gia(db: Session) -> None:
    """Đơn giá NHẬP do người đề nghị khai: thêm `stock_request_lines.don_gia` (INTEGER nullable).
    Phiếu kế thừa giá này khi ghi sổ (kho không sửa). No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "stock_request_lines" not in insp.get_table_names():
        return
    if "don_gia" not in _existing_columns(insp, "stock_request_lines"):
        db.execute(text("ALTER TABLE stock_request_lines ADD COLUMN don_gia INTEGER"))
    db.commit()


def _migrate_stock_request_line_ly_do_thieu(db: Session) -> None:
    """Kho phản hồi: thêm `stock_request_lines.ly_do_thieu` (VARCHAR(500) nullable) — lý do kho
    cấp/nhập ít hơn số còn phải cấp. No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "stock_request_lines" not in insp.get_table_names():
        return
    if "ly_do_thieu" not in _existing_columns(insp, "stock_request_lines"):
        db.execute(text("ALTER TABLE stock_request_lines ADD COLUMN ly_do_thieu VARCHAR(500)"))
    db.commit()


def _migrate_stock_request_line_quy_doi(db: Session) -> None:
    """Quy đổi đơn vị khai Ở ĐỀ NGHỊ (chuyển từ phiếu sang): thêm `stock_request_lines.don_vi_phu`
    (VARCHAR(16)) + `he_so_quy_doi` (NUMERIC(14,4)), nullable. No-op DB fresh / bảng chưa có / đã có."""
    insp = inspect(db.get_bind())
    if "stock_request_lines" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "stock_request_lines")
    if "don_vi_phu" not in cols:
        db.execute(text("ALTER TABLE stock_request_lines ADD COLUMN don_vi_phu VARCHAR(16)"))
    if "he_so_quy_doi" not in cols:
        db.execute(text("ALTER TABLE stock_request_lines ADD COLUMN he_so_quy_doi NUMERIC(14,4)"))
    db.commit()


def _migrate_piece_rate_cong_doan_mas(db: Session) -> None:
    """Đầu việc khoán dùng cho NHIỀU công đoạn + trục quy đổi: thêm `piece_rates.cong_doan_mas`
    (JSON list mã) và `tinh_theo` (VARCHAR(32)), nullable. Backfill `cong_doan_mas = [cong_doan]`
    cho dòng cũ đã trỏ 1 mã để không mất liên kết. No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "piece_rates" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "piece_rates")
    is_pg = db.get_bind().dialect.name == "postgresql"
    if "cong_doan_mas" not in cols:
        # JSON (KHÔNG JSONB) để khớp `mapped_column(JSON)` của model: DB trắng đi đường `create_all`
        # sẽ ra kiểu `json`, migration mà tạo `jsonb` là dev/prod lệch kiểu — query dùng toán tử
        # jsonb chạy ở DB cũ rồi vỡ ở DB mới. Đã bắt được đúng lỗi này khi thử trên Postgres trắng.
        db.execute(text("ALTER TABLE piece_rates ADD COLUMN cong_doan_mas JSON"))
    if "tinh_theo" not in cols:
        db.execute(text("ALTER TABLE piece_rates ADD COLUMN tinh_theo VARCHAR(32)"))
    db.commit()
    # Backfill: dòng cũ có `cong_doan` → list 1 phần tử. Ghép chuỗi JSON cho cả 2 dialect (cột kiểu
    # `json` nên `to_jsonb` của Postgres không dùng được ở đây).
    _cast = "::json" if is_pg else ""
    db.execute(text(
        f"UPDATE piece_rates SET cong_doan_mas = ('[\"' || cong_doan || '\"]'){_cast} "
        "WHERE cong_doan IS NOT NULL AND cong_doan <> '' AND cong_doan_mas IS NULL"
    ))
    db.commit()


def _migrate_lsx_cong_doan_khoan_json(db: Session) -> None:
    """Bước lệnh ghim ĐẦU VIỆC KHOÁN: thêm `lsx_cong_doan.khoan_json` (JSON, nullable) =
    {rate_id, ten, don_vi, don_gia, tinh_theo}. Ghim snapshot chứ không đọc-sống vì xưởng lên giá
    khoán về sau KHÔNG được làm xê dịch lệnh đã phát. No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "lsx_cong_doan" not in insp.get_table_names():
        return
    if "khoan_json" not in _existing_columns(insp, "lsx_cong_doan"):
        # JSON, KHÔNG JSONB — xem ghi chú kiểu cột ở `_migrate_piece_rate_cong_doan_mas`.
        db.execute(text("ALTER TABLE lsx_cong_doan ADD COLUMN khoan_json JSON"))
    db.commit()


def _migrate_piece_rate_bo_luat_ngam(db: Session) -> None:
    """Bảng đơn giá khoán về đúng nghĩa KHAI BÁO: xoá `cong_doan_mas` + `tinh_theo`.

    Hai cột đó là hai luật NGẦM mà mở form ra không ai đoán được: `cong_doan_mas` khiến dòng khai
    riêng thắng dòng khai chung khi khớp bước lệnh, `tinh_theo` khiến SL bị nhân thêm số lượt chạy
    trước khi nhân đơn giá. Chủ chốt 2026-07-31: chỗ này chỉ ghi lại cái người ta gõ, mọi phép
    tính nằm bên sản xuất. Đơn giá giờ chỉ treo vào TỔ; muốn trả theo lượt thì khai đơn vị `lượt`.

    Cột `piece_rates.cong_doan` (1 mã, bản còn cũ hơn) GIỮ nguyên để không mất dữ liệu lịch sử —
    đã đánh dấu cột chết trong model, không đọc ở đâu nữa.
    """
    insp = inspect(db.get_bind())
    if "piece_rates" not in insp.get_table_names():
        return
    co = _existing_columns(insp, "piece_rates")
    for cot in ("cong_doan_mas", "tinh_theo"):
        if cot in co:
            db.execute(text(f"ALTER TABLE piece_rates DROP COLUMN {cot}"))
    db.commit()


def _migrate_don_vi_quy_doi_cong_thuc(db: Session) -> None:
    """Quy đổi ĐỘNG: thêm `don_vi_quy_doi.cong_thuc` (nullable).

    "1 tờ bằng mấy kg" không có đáp án chung nhưng TÍNH ĐƯỢC từ khổ + định lượng, nên cột này cho
    dòng quy đổi ghi công thức thay cho con số; biến do nơi gọi bơm vào lúc chạy. Trước đó ba phép
    đó nằm cứng trong code (`quy_doi_service.CAU`) nên xưởng không tự khai được.
    No-op DB fresh / bảng chưa có / cột đã có.
    """
    insp = inspect(db.get_bind())
    if "don_vi_quy_doi" not in insp.get_table_names():
        return
    if "cong_thuc" not in _existing_columns(insp, "don_vi_quy_doi"):
        db.execute(text("ALTER TABLE don_vi_quy_doi ADD COLUMN cong_thuc VARCHAR(200)"))
    db.commit()


def _migrate_don_vi_don_cap_du(db: Session) -> None:
    """Xoá CẶP DƯ: cạnh mà bỏ đi rồi hai đầu vẫn đổi được cho nhau qua đường khác.

    DB đã chạy bản 0135 đầu tiên có 7 cặp 1-1 cho 5 đơn vị đếm thành phẩm (cái · con · cuốn · bộ ·
    hộp) vì migration và seed cùng nối một nhóm. Không sai số nhưng bảng Quy đổi nhìn rối, và mỗi
    dòng dư là một chỗ để người ta sửa lệch về sau. Giữ cạnh hệ số ≠ 1 (số thật của xưởng), chỉ xét
    cạnh 1-1; xoá dần và kiểm lại sau mỗi lần để không cắt đứt liên thông.
    """
    insp = inspect(db.get_bind())
    if "don_vi_quy_doi" not in insp.get_table_names():
        return
    rows = db.execute(text(
        "SELECT q.id, a.ma, b.ma, q.he_so FROM don_vi_quy_doi q "
        "JOIN don_vi_do a ON a.id = q.tu_id JOIN don_vi_do b ON b.id = q.den_id"
    )).all()
    canh = [(r[0], r[1], r[2], float(r[3])) for r in rows]

    def _lien_thong(bo_qua: set[int], tu: str, den: str) -> bool:
        g: dict[str, set[str]] = {}
        for cid, a, b, _hs in canh:
            if cid in bo_qua:
                continue
            g.setdefault(a, set()).add(b)
            g.setdefault(b, set()).add(a)
        seen, stack = {tu}, [tu]
        while stack:
            cur = stack.pop()
            if cur == den:
                return True
            for ke in g.get(cur, ()):
                if ke not in seen:
                    seen.add(ke)
                    stack.append(ke)
        return den in seen

    bo: set[int] = set()
    for cid, a, b, hs in canh:
        if abs(hs - 1.0) > 1e-9:
            continue                       # cạnh mang số thật → giữ
        if _lien_thong(bo | {cid}, a, b):  # bỏ nó mà vẫn đi được → dư
            bo.add(cid)
    for cid in bo:
        db.execute(text("DELETE FROM don_vi_quy_doi WHERE id = :i"), {"i": cid})
    db.commit()


def _migrate_don_vi_he_so_goc_sang_cap(db: Session) -> None:
    """Chuyển mô hình quy đổi: "hệ số về đơn vị gốc" (1 cột) → BẢNG CẶP `don_vi_quy_doi`.

    Chủ 2026-07-30: *"có logic nào dễ hơn không, kiểu tạo được đơn vị rồi có hệ số quy đổi giữa các
    đơn vị"* — mô hình cũ đúng về máy nhưng bắt người khai nhớ "đơn vị chuẩn của nhóm" mới điền được
    số, nhìn vào không hiểu. Nay khai theo cặp như cách nói ngoài đời: "1 tấn = 1.000 kg".

    Chuyển: mỗi đơn vị có `he_so_goc` ≠ 1 sinh 1 cặp về đơn vị gốc CÙNG HỌ (dòng hệ số 1).

    Các đơn vị cùng họ mà ĐỀU hệ số 1 (cái · con · cuốn · bộ · hộp) thì KHÔNG nối ở đây — `seed_don_vi_do`
    đã nối hết về `cai`. Nối cả hai nơi thì ra hai bộ cạnh chồng nhau (đã gặp thật: 7 cặp 1-1 cho 5
    đơn vị, thừa 3 dòng nhìn rối dù không sai số).

    Bảng do `create_all` dựng; ở đây chỉ đổ dữ liệu, và no-op nếu đã có cặp.
    """
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "don_vi_do" not in tables or "don_vi_quy_doi" not in tables:
        return
    if "he_so_goc" not in _existing_columns(insp, "don_vi_do"):
        return
    if db.execute(text("SELECT count(*) FROM don_vi_quy_doi")).scalar_one():
        return      # đã có cặp (DB mới seed) → không đụng
    rows = db.execute(
        text("SELECT id, ma, ho, he_so_goc FROM don_vi_do ORDER BY ho, id")
    ).all()
    theo_ho: dict[str, list] = {}
    for r in rows:
        theo_ho.setdefault((r[2] or "khac").strip().lower(), []).append(r)
    for _ho, ds in theo_ho.items():
        goc = next((d for d in ds if abs(float(d[3] or 0) - 1.0) < 1e-9), None)
        if goc is None:
            continue
        for d in ds:
            if d[0] == goc[0]:
                continue
            hs = float(d[3] or 0)
            if hs <= 0 or abs(hs - 1.0) < 1e-9:
                continue        # hệ số 1 → để `seed_don_vi_do` nối, xem docstring
            db.execute(
                text("INSERT INTO don_vi_quy_doi (tu_id, den_id, he_so, created_at, updated_at) "
                     "VALUES (:tu, :den, :hs, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
                {"tu": d[0], "den": goc[0], "hs": hs},
            )
    db.commit()


def _migrate_don_vi_bai_in_gop_vao_bai(db: Session) -> None:
    """Dọn hai thứ cùng nghĩa của bản seed đầu: đơn vị `bai_in` (trùng vai `bai` — cùng họ, cùng hệ
    số 1, tức HAI đơn vị gốc trong một họ) và các dòng đơn giá khoán ghi `unit='bai_in'`.

    `unit` của đơn giá là CHỮ HIỂN THỊ, nên "bai_in" không khớp mã (`bai`) lẫn tên ("bài in") → 3 dòng
    "Bài in A/B/C" của seed lương cũ vĩnh viễn báo "chưa khai đơn vị". Đổi chữ trước rồi mới xoá đơn
    vị dư, giữ đúng thứ tự để không có lúc nào dòng đơn giá trỏ vào đơn vị không tồn tại."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "piece_rates" in tables:
        db.execute(text("UPDATE piece_rates SET unit = 'bài in' WHERE unit = 'bai_in'"))
        db.commit()
    if "don_vi_do" in tables:
        # Chỉ xoá khi `bai` đã có mặt để nhận vai — không thì thà giữ dòng dư còn hơn mất đơn vị.
        co_bai = db.execute(text("SELECT count(*) FROM don_vi_do WHERE ma = 'bai'")).scalar_one()
        if co_bai:
            db.execute(text("DELETE FROM don_vi_do WHERE ma = 'bai_in'"))
        db.commit()


def _migrate_khoan_json_ve_json(db: Session) -> None:
    """Hạ `jsonb` → `json` cho 2 cột khoán ở DB đã chạy bản migration ĐẦU (bản đó tạo JSONB).

    Vì sao phải dọn: DB TRẮNG đi đường `create_all` từ `mapped_column(JSON)` nên ra kiểu `json`, còn
    DB cũ chạy migration bản đầu lại có `jsonb`. Cùng một cột mà dev/prod khác kiểu là bẫy âm thầm:
    query dùng toán tử jsonb (`jsonb_array_length`, `@>`) chạy ở nơi này, vỡ ở nơi kia. Chỉ Postgres
    mới có phân biệt này; SQLite no-op. Không dữ liệu nào mất — jsonb → json là cast an toàn."""
    if db.get_bind().dialect.name != "postgresql":
        return
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    for bang, cot in (("piece_rates", "cong_doan_mas"), ("lsx_cong_doan", "khoan_json")):
        if bang not in tables:
            continue
        kieu = next(
            (str(c["type"]).lower() for c in insp.get_columns(bang) if c["name"] == cot), ""
        )
        if "jsonb" in kieu:
            db.execute(text(
                f"ALTER TABLE {bang} ALTER COLUMN {cot} TYPE JSON USING {cot}::text::json"
            ))
    db.commit()


def _migrate_don_vi_do_chuan_hoa_ho(db: Session) -> None:
    """Chuẩn hoá danh mục đơn vị của bản seed ĐẦU (trước khi chốt mô hình họ):

    · gộp `con` · `cuon` · `bo` · `hop` về họ **thanh_pham** — chúng đều là "một thành phẩm xong",
      để mỗi thứ một họ thì bước lệnh đếm `cai` không khớp nổi đơn giá "700 đ/cuốn";
    · bỏ `bai_in` (trùng vai với `bai`, mà `bai` mới là mã đơn vị bước lệnh dùng);
    · sửa nhãn `cai` từ "con / cái" thành "cái" cho diễn giải gọn.

    No-op nếu bảng chưa có / đã chuẩn. KHÔNG đụng đơn vị người dùng tự khai.
    """
    insp = inspect(db.get_bind())
    if "don_vi_do" not in insp.get_table_names():
        return
    db.execute(text(
        "UPDATE don_vi_do SET ho = 'thanh_pham' "
        "WHERE ma IN ('con', 'cuon', 'bo', 'hop', 'cai') AND ho <> 'thanh_pham'"
    ))
    db.execute(text("UPDATE don_vi_do SET ten = 'cái' WHERE ma = 'cai' AND ten = 'con / cái'"))
    # `bai_in` chỉ xoá khi CHƯA ai dùng làm đơn vị đơn giá khoán — còn dùng thì để lại, đổi họ cho
    # nó chung nhà với `bai` là đủ (xoá mất là bảng khoán hiện "đơn vị chưa khai").
    con_dung = db.execute(text(
        "SELECT COUNT(*) FROM piece_rates WHERE lower(unit) IN ('bai_in', 'bài in')"
    )).scalar() or 0
    if con_dung:
        db.execute(text("UPDATE don_vi_do SET ho = 'bai' WHERE ma = 'bai_in'"))
    else:
        db.execute(text("DELETE FROM don_vi_do WHERE ma = 'bai_in'"))
    db.commit()


def _migrate_ptg_drop_chua_thua(db: Session) -> None:
    """Bỏ 4 khoản chừa khỏi phiếu: `chua_tay_ke` · `chua_duoi` · `chua_xen` · `chua_ca_gay`.

    Chừa tờ in là đặc tính của MÁY (`nhip_giay_mm` / `le_hong_mm` / `duoi_thang_mau_mm` ở danh mục
    máy) — bốn cột này chưa từng có ô nhập ở bất kỳ màn nào, mà xén/cả gáy còn bị engine cộng đều
    CẢ HAI chiều nên chỉ làm số con lệch âm thầm. Giữ lại `chua_nhip` làm ô đè theo job.

    CẢNH BÁO GIÁ: phiếu cũ có `chua_tay_ke`/`chua_duoi` > 0 mà máy chưa khai chừa thì sau bước này
    chừa về 0 → con/tờ tăng → số tờ giảm → giá vốn giảm. Điền danh mục Máy trước khi chạy.

    Best-effort mỗi câu (SQLite cũ có thể từ chối DROP COLUMN → cột mồ côi vô hại vì model không
    map). No-op trên DB fresh."""
    insp = inspect(db.get_bind())
    if "phieu_thanh_phan" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "phieu_thanh_phan")
    for c in ("chua_tay_ke", "chua_duoi", "chua_xen", "chua_ca_gay"):
        if c not in cols:
            continue
        try:
            db.execute(text(f"ALTER TABLE phieu_thanh_phan DROP COLUMN {c}"))
            db.commit()
        except Exception:
            db.rollback()


def _migrate_lsx_qc_chua_ve_may(db: Session) -> None:
    """Dọn chừa MỒ CÔI trong `lsx.quy_cach_json` sau mig 0139.

    Snapshot quy cách của lệnh chụp nguyên dict thành phần, nên lệnh cũ còn giữ `chua_tay_ke` /
    `chua_duoi` / `chua_xen` / `chua_ca_gay`. Từ 0139 engine không đọc chúng nữa → chừa của lệnh
    tụt (vd 15/10 → 10/0) trong khi phiếu tính giá vẫn 15/10: CÙNG một tờ, hai màn hai số.

    Chuyển giá trị sang đúng khoá máy trong snapshot (giữ nguyên Ý ĐỊNH lúc chụp, KHÔNG đọc lại
    danh mục máy hiện tại — snapshot phải đứng yên):
      · `chua_tay_ke` → `le_hong_mm`         (cùng đơn vị: mỗi bên, engine nhân 2)
      · `chua_duoi`   → `duoi_thang_mau_mm`  (cộng một lần vào chiều dài)
      · `chua_xen` + `chua_ca_gay` trước cộng đều CẢ HAI chiều → dồn vào đuôi (dài) và nửa vào
        lề hông (rộng, vì bị nhân 2) để tổng mỗi chiều không đổi.
    Chỉ ghi khi khoá máy đang trống — lệnh chụp lúc danh mục máy đã khai thì để yên. Xoá 4 khoá
    chết sau khi chuyển. No-op nếu bảng chưa có / đã dọn."""
    insp = inspect(db.get_bind())
    if "lsx" not in insp.get_table_names():
        return
    pg = db.get_bind().dialect.name == "postgresql"
    sql = ("UPDATE lsx SET quy_cach_json = CAST(:v AS JSON) WHERE id = :i" if pg
           else "UPDATE lsx SET quy_cach_json = :v WHERE id = :i")
    rows = db.execute(text("SELECT id, quy_cach_json FROM lsx WHERE quy_cach_json IS NOT NULL")).all()
    for lsx_id, qc in rows:
        if isinstance(qc, str):
            qc = json.loads(qc)
        if not isinstance(qc, dict):
            continue
        chet = ("chua_tay_ke", "chua_duoi", "chua_xen", "chua_ca_gay")
        if not any(k in qc for k in chet):
            continue

        def _f(k: str) -> float:
            try:
                return float(qc.get(k) or 0)
            except (TypeError, ValueError):
                return 0.0

        deu = _f("chua_xen") + _f("chua_ca_gay")
        if not _f("duoi_thang_mau_mm"):
            qc["duoi_thang_mau_mm"] = _f("chua_duoi") + deu
        if not _f("le_hong_mm"):
            qc["le_hong_mm"] = _f("chua_tay_ke") + deu / 2
        for k in chet:
            qc.pop(k, None)
        db.execute(text(sql), {"v": json.dumps(qc, ensure_ascii=False), "i": lsx_id})
    db.commit()


def _migrate_xoa_don_gia_khoan_mo_coi(db: Session) -> None:
    """Xoá 12 dòng đơn giá khoán DEMO mồ côi do `seed_piece_work` (seed.py) sinh ra.

    Chúng mang `group_name` là mã cứng ('to_boi', 'to_cat', 'may_in_5mau'…) và `department_id` để
    TRỐNG. Bước lệnh sản xuất lọc đầu việc bằng `department_id` (`dau_viec_khop`) nên 12 dòng này
    chưa bao giờ tới được người lập lệnh — chúng chỉ làm bảng khai dài ra và khiến ô "Tổ" phải giữ
    danh sách mã cứng. Đơn giá khoán THẬT do `seed_luong_ban_sx` sinh, có `department_id` đầy đủ.

    Nhắm CHÍNH XÁC dòng của seed (`note` = 'Đơn giá khoán demo' và chưa gắn tổ): đơn giá người dùng
    tự khai — kể cả khi cũng chưa gắn tổ — KHÔNG bị đụng tới.

    An toàn với lệnh đã phát: bước lệnh ghim ẢNH CHỤP (`khoan_snapshot`: tên · đơn vị · đơn giá)
    chứ không đọc-sống bảng giá, nên xoá dòng gốc không xê dịch lệnh cũ."""
    insp = inspect(db.get_bind())
    if "piece_rates" not in insp.get_table_names():
        return
    db.execute(text(
        "DELETE FROM piece_rates WHERE department_id IS NULL AND note = :n"
    ), {"n": "Đơn giá khoán demo"})
    db.commit()


def _migrate_lsx_drop_may_thay_the(db: Session) -> None:
    """Bỏ `lsx_cong_doan.may_thay_the_ids` — danh sách máy thay thế KHÔNG ai đọc.

    Nó chỉ là ghi chú tay ("for information only" theo Print MIS): xếp lịch, Gantt và danh sách vấn
    đề đều không tra tới. Việc "máy này có kham nổi bài không" đã có `_may_fit.kiem_kha_nang` tự
    tính từ spec máy × quy cách (khổ · số màu · định lượng) mỗi lần gán/kéo máy — số liệu sống,
    không phụ thuộc ai nhớ tick.

    Best-effort (SQLite cũ có thể từ chối DROP COLUMN → cột mồ côi vô hại vì model không map).
    No-op trên DB fresh."""
    insp = inspect(db.get_bind())
    if "lsx_cong_doan" not in insp.get_table_names():
        return
    if "may_thay_the_ids" not in _existing_columns(insp, "lsx_cong_doan"):
        return
    try:
        db.execute(text("ALTER TABLE lsx_cong_doan DROP COLUMN may_thay_the_ids"))
        db.commit()
    except Exception:
        db.rollback()


def _migrate_khsx_dinh_muc_vat_tu_phu_thuoc(db: Session) -> None:
    """KHSX động: định mức đầu việc, step key, vật tư bước và DAG phụ thuộc."""
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    # SQLite chỉ tự tăng với đúng `INTEGER PRIMARY KEY`; PostgreSQL cần identity/serial.
    id_pk = "INTEGER PRIMARY KEY" if db.get_bind().dialect.name == "sqlite" else "SERIAL PRIMARY KEY"
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS cong_doan_dau_viec ("
        f"id {id_pk}, cong_doan_id INTEGER NOT NULL REFERENCES cong_doan(id) ON DELETE CASCADE, "
        "piece_rate_id INTEGER NOT NULL, nang_suat_nguoi_gio NUMERIC(14,2) NOT NULL, "
        "so_nguoi_tieu_chuan INTEGER NOT NULL DEFAULT 1, so_nguoi_toi_da INTEGER NOT NULL DEFAULT 1, "
        "is_default BOOLEAN NOT NULL DEFAULT false, UNIQUE(cong_doan_id,piece_rate_id))"
    ))
    if "piece_rates" in tables and "cong_doan" in tables:
        rows = db.execute(text(
            "SELECT c.id,c.department_id,c.nang_suat FROM cong_doan c "
            "WHERE c.department_id IS NOT NULL AND c.nang_suat IS NOT NULL AND c.nang_suat>0"
        )).all()
        for cid, did, ns in rows:
            rates = db.execute(text(
                "SELECT id FROM piece_rates WHERE department_id=:d AND is_active=true"
            ), {"d": did}).all()
            if len(rates) == 1:
                db.execute(text(
                    "INSERT INTO cong_doan_dau_viec "
                    "(cong_doan_id,piece_rate_id,nang_suat_nguoi_gio,so_nguoi_tieu_chuan,so_nguoi_toi_da,is_default) "
                    "SELECT :c,:r,:n,1,1,true WHERE NOT EXISTS (SELECT 1 FROM cong_doan_dau_viec "
                    "WHERE cong_doan_id=:c AND piece_rate_id=:r)"
                ), {"c": cid, "r": rates[0][0], "n": ns})

    if "lsx_cong_doan" in tables:
        cols = _existing_columns(insp, "lsx_cong_doan")
        if "step_key" not in cols:
            db.execute(text("ALTER TABLE lsx_cong_doan ADD COLUMN step_key VARCHAR(36)"))
        if "so_nhan_cong_tieu_chuan" not in cols:
            db.execute(text("ALTER TABLE lsx_cong_doan ADD COLUMN so_nhan_cong_tieu_chuan INTEGER NOT NULL DEFAULT 1"))
        if "so_nhan_cong_toi_da" not in cols:
            db.execute(text("ALTER TABLE lsx_cong_doan ADD COLUMN so_nhan_cong_toi_da INTEGER"))
        for (sid,) in db.execute(text("SELECT id FROM lsx_cong_doan WHERE step_key IS NULL OR step_key=''")):
            db.execute(text("UPDATE lsx_cong_doan SET step_key=:k WHERE id=:i"),
                       {"k": str(uuid4()), "i": sid})
        db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_lsx_cong_doan_step_key ON lsx_cong_doan(step_key)"))
        db.execute(text(
            "UPDATE lsx_cong_doan SET so_nhan_cong_tieu_chuan=CASE WHEN so_nhan_cong<1 THEN 1 ELSE so_nhan_cong END, "
            "so_nhan_cong_toi_da=CASE WHEN loai_buoc IN ('to','kcs') THEN "
            "CASE WHEN so_nhan_cong<1 THEN 1 ELSE so_nhan_cong END ELSE NULL END"
        ))
        db.execute(text("UPDATE lsx_cong_doan SET loai_buoc='to' WHERE loai_buoc='kcs'"))
        db.execute(text("UPDATE lsx_cong_doan SET loai_buoc='may' WHERE loai_buoc='xa_to'"))

        waits = db.execute(text(
            "SELECT id,lsx_id,thu_tu,setup_phut,chay_phut,ve_sinh_phut,cho_phut,di_chuyen_phut "
            "FROM lsx_cong_doan WHERE loai_buoc='cho' ORDER BY lsx_id,thu_tu"
        )).all()
        for wid, lid, seq, setup, run, clean, wait, move in waits:
            prev = db.execute(text(
                "SELECT id FROM lsx_cong_doan WHERE lsx_id=:l AND thu_tu<:s AND loai_buoc<>'cho' "
                "ORDER BY thu_tu DESC LIMIT 1"
            ), {"l": lid, "s": seq}).first()
            if prev is None:
                raise RuntimeError(f"LSX {lid} có bước Chờ đầu tuyến (id={wid}); cần audit tay trước migration")
            total = sum(float(x or 0) for x in (setup, run, clean, wait, move))
            db.execute(text("UPDATE lsx_cong_doan SET cho_phut=cho_phut+:p WHERE id=:i"),
                       {"p": total, "i": prev[0]})
            if "xep_lich_cong_doan" in tables:
                db.execute(text("DELETE FROM xep_lich_cong_doan WHERE lsx_cong_doan_id=:i"), {"i": wid})
            db.execute(text("DELETE FROM lsx_cong_doan WHERE id=:i"), {"i": wid})
        gang_ids = [x[0] for x in db.execute(text("SELECT id FROM lsx_cong_doan WHERE loai_buoc='bai_ghep'"))]
        for sid in gang_ids:
            if "xep_lich_cong_doan" in tables:
                db.execute(text("DELETE FROM xep_lich_cong_doan WHERE lsx_cong_doan_id=:i"), {"i": sid})
            db.execute(text("DELETE FROM lsx_cong_doan WHERE id=:i"), {"i": sid})

    db.execute(text(
        "CREATE TABLE IF NOT EXISTS lsx_cong_doan_vat_tu ("
        f"id {id_pk}, lsx_cong_doan_id INTEGER NOT NULL REFERENCES lsx_cong_doan(id) ON DELETE CASCADE, "
        "vat_tu_id INTEGER NOT NULL, vat_tu_ma_snapshot VARCHAR(30) NOT NULL, "
        "vat_tu_ten_snapshot VARCHAR(150) NOT NULL, don_vi_snapshot VARCHAR(16) NOT NULL, "
        "so_luong NUMERIC(14,3) NOT NULL, thu_tu INTEGER NOT NULL DEFAULT 0, "
        "UNIQUE(lsx_cong_doan_id,vat_tu_id))"
    ))
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS lsx_cong_doan_phu_thuoc ("
        f"id {id_pk}, buoc_truoc_id INTEGER NOT NULL REFERENCES lsx_cong_doan(id), "
        "buoc_sau_id INTEGER NOT NULL REFERENCES lsx_cong_doan(id) ON DELETE CASCADE, "
        "created_at TIMESTAMP NOT NULL, UNIQUE(buoc_truoc_id,buoc_sau_id))"
    ))
    if "lsx_cong_doan" in tables:
        for (lid,) in db.execute(text("SELECT DISTINCT lsx_id FROM lsx_cong_doan")):
            ids = [x[0] for x in db.execute(text(
                "SELECT id FROM lsx_cong_doan WHERE lsx_id=:l ORDER BY thu_tu,id"
            ), {"l": lid})]
            for prev, cur in zip(ids, ids[1:]):
                db.execute(text(
                    "INSERT INTO lsx_cong_doan_phu_thuoc (buoc_truoc_id,buoc_sau_id,created_at) "
                    "SELECT :p,:c,CURRENT_TIMESTAMP WHERE NOT EXISTS (SELECT 1 FROM lsx_cong_doan_phu_thuoc "
                    "WHERE buoc_truoc_id=:p AND buoc_sau_id=:c)"
                ), {"p": prev, "c": cur})
    if "xep_lich_cong_doan" in tables:
        db.execute(text("UPDATE xep_lich_cong_doan SET loai_buoc='to' WHERE loai_buoc='kcs'"))
        db.execute(text("UPDATE xep_lich_cong_doan SET loai_buoc='may' WHERE loai_buoc='xa_to'"))
    # Dùng snapshot `cols` đã đọc đầu migration. Gọi `inspect(engine)` lần nữa tại đây sẽ mở
    # connection thứ hai trong khi transaction hiện tại đang giữ lock UPDATE/ALTER trên chính
    # bảng này; PostgreSQL khi đó chờ khóa của chính app và startup treo vô hạn.
    if "lsx_cong_doan" in tables and "dieu_kien_json" in cols:
        db.execute(text("ALTER TABLE lsx_cong_doan DROP COLUMN dieu_kien_json"))
    db.commit()


def _migrate_xep_lich_bai_ghep_cong_doan(db: Session) -> None:
    """Dòng lịch của bài ghép neo ĐÍCH DANH bước chạy chung nào.

    Trước nay bài chỉ đẻ ĐÚNG MỘT dòng "in ghép" — đúng khi điểm gộp duy nhất là bước in. Nay
    người dùng gộp cả CTP / cán / bế, mà `_sinh_dong` thì loại MỌI bước bị đè khỏi routing lệnh:
    gộp ba công đoạn là ba bước biến mất khỏi board, chỉ còn một dòng thay thế, và dòng đó lấy
    máy của BÀI chứ không lấy máy người dùng vừa khai cho lượt chung.

    KHÔNG backfill: dòng cũ (`bai_ghep_cong_doan_id IS NULL`) vẫn chạy nhánh thời lượng cũ theo
    máy của bài, nên bài đã lập kế hoạch từ trước không vỡ.
    """
    insp = inspect(db.get_bind())
    if "xep_lich_cong_doan" not in insp.get_table_names():
        return
    if "bai_ghep_cong_doan_id" not in _existing_columns(insp, "xep_lich_cong_doan"):
        db.execute(text(
            "ALTER TABLE xep_lich_cong_doan ADD COLUMN bai_ghep_cong_doan_id INTEGER"))
        db.commit()


def _migrate_bai_ghep_hao_nullable(db: Session) -> None:
    """`bai_ghep.hao_hut_setup/chay`: NOT NULL DEFAULT 0 → nullable. NULL = CHƯA KHAI.

    Cột cũ không phân biệt được "chưa ai khai" với "khai 0". Engine đọc chúng bằng
    `int(setup) + int(chay) or hao_de_xuat`, nên ai cố ý khai không-bù-hao vẫn bị thay bằng số
    máy đề xuất — không có đường nào bảo bài chạy đúng số.

    Đưa bài đang 0/0 về NULL để GIỮ NGUYÊN số đang hiện (code cũ hiểu 0/0 là chưa khai). Bài có
    bất kỳ số khác 0 thì giữ nguyên — đó là số người đã khai thật.

    `DROP NOT NULL` là Postgres-only: SQLite dựng bảng thẳng từ model nên đã nullable sẵn, và
    pytest sẽ xanh dù nhánh này chưa chạy — phải kiểm trên Postgres.
    """
    insp = inspect(db.get_bind())
    if "bai_ghep" not in insp.get_table_names():
        return
    if (db.get_bind().dialect.name or "").startswith("postgres"):
        for col in ("hao_hut_setup", "hao_hut_chay"):
            db.execute(text(f"ALTER TABLE bai_ghep ALTER COLUMN {col} DROP NOT NULL"))
            db.execute(text(f"ALTER TABLE bai_ghep ALTER COLUMN {col} DROP DEFAULT"))
    db.execute(text(
        "UPDATE bai_ghep SET hao_hut_setup = NULL, hao_hut_chay = NULL "
        "WHERE COALESCE(hao_hut_setup, 0) = 0 AND COALESCE(hao_hut_chay, 0) = 0"
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
    ("0040_payment_doc_no_and_accounts", _migrate_payment_doc_no_and_accounts),
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
    ("0063_quote_deposit_pct", _migrate_quote_deposit_pct),
    ("0063_ptg_kho_nguyen_override", _migrate_ptg_kho_nguyen_override),
    ("0064_payroll_special_day_multipliers", _migrate_payroll_special_day_multipliers),
    ("0065_attendance_line_special_day", _migrate_attendance_line_special_day),
    ("0066_order_redesign_fields", _migrate_order_redesign_fields),
    ("0067_role_permission_record_deposit", _migrate_role_permission_record_deposit),
    ("0068_drop_piece_batches_khoan_theo_nguoi", _migrate_drop_piece_batches_khoan_theo_nguoi),
    ("0069_drop_ghost_modules", _migrate_drop_ghost_modules),
    ("0070_receipt_source_and_drop_order_deposits", _migrate_receipt_source_and_drop_order_deposits),
    ("0071_order_line_phieu_thanh_phan", _migrate_order_line_phieu_thanh_phan),
    ("0072_cong_doan_department_id", _migrate_cong_doan_department_id),
    # Tích hợp accounting-wip (đánh số tiếp, KHÔNG đụng id đã ship): báo giá terms_text + PTG ĐVT.
    ("0073_quote_terms_text", _migrate_quote_terms_text),
    ("0074_ptg_don_vi_tinh", _migrate_ptg_don_vi_tinh),
    # Nhánh giá/đơn/care (session 2026-07-18).
    ("0075_seed_pricing_formulas", _migrate_seed_pricing_formulas),
    ("0076_order_graft_fields", _migrate_order_graft_fields),
    ("0077_care_task_recurrence", _migrate_care_task_recurrence),
    # Nhánh HCNS (lương/chấm công/nhân sự) — trùng SỐ 0070-0075 nhưng khác CHUỖI id nên
    # schema_migrations coi là migration riêng, vẫn chạy đúng 1 lần. Giữ nguyên id (không đổi id đã ship).
    ("0070_department_salary_policy", _migrate_department_salary_policy),
    ("0071_probation_ratio_80", _migrate_probation_ratio_80),
    ("0072_employee_salary_source_row", _migrate_employee_salary_source_row),
    ("0073_employee_salary_chuyen_can", _migrate_employee_salary_chuyen_can),
    ("0074_payslip_detail_items", _migrate_payslip_detail_items),
    ("0075_salary_advance_code", _migrate_salary_advance_code),
    # Màn "Cấu hình lương" 3 tab (prd-cau-hinh-luong §9) — nối tiếp nhánh HCNS.
    ("0076_cau_hinh_luong", _migrate_cau_hinh_luong),
    ("0077_department_salary_policy_note", _migrate_department_salary_policy_note),
    # Nhánh Kế hoạch/LSX (accounting-wip): cờ phòng sản xuất. Khác CHUỖI id nên không đụng 0075 ở trên.
    ("0075_department_la_san_xuat", _migrate_department_la_san_xuat),
    # Handoff Đơn→Kế hoạch: Sale 'Chuyển xuống sản xuất' (sau chốt) → đơn vào hàng chờ.
    ("0078_order_san_xuat_released", _migrate_order_san_xuat_released),
    # Note kỹ thuật theo sản phẩm (canh màu/kẽm cũ/bù hao) — Tính giá gõ → drawer lệnh.
    ("0079_ptp_ghi_chu_ky_thuat", _migrate_ptp_ghi_chu_ky_thuat),
    # Override quy cách in tại lệnh (kế thừa báo giá nhưng sửa được ở nháp).
    ("0080_lenh_item_quy_cach_override", _migrate_lenh_item_quy_cach_override),
    # san_xuat: ô quyền gán việc (tổ trưởng gán thợ vào công đoạn lệnh đã phát) — Lát 1.
    ("0081_role_permission_assign_work", _migrate_role_permission_assign_work),
    # Lát 1b ②: routing_step chở ghi chú + quy cách BƯỚC (copy từ PhieuThanhPham) — tổ hết trơ.
    ("0082_routing_step_ghi_chu", _migrate_routing_step_ghi_chu),
    # Lát 1b ①: hạn giao thành thuộc tính LỆNH (hạn khách snapshot đơn + hạn nội bộ buffer).
    ("0083_lenh_sx_han_giao", _migrate_lenh_sx_han_giao),
    # ③: gán khuôn bế vào lệnh (soft → khuon_be.id).
    ("0084_lenh_sx_khuon_be_id", _migrate_lenh_sx_khuon_be_id),
    # ④: lịch chạy (bảng Máy×Ngày) — ngày chạy + thứ tự trong ô + thời lượng (nền Gantt sau).
    ("0085_lenh_sx_lich_chay", _migrate_lenh_sx_lich_chay),
    ("0086_routing_step_may_ca", _migrate_routing_step_may_ca),
    ("0087_role_permission_output_handover", _migrate_role_permission_output_handover),
    # Gỡ module ma `hop_dong` (như 0069) — không router/màn dùng; "Hợp đồng" chỉ là doc_kind đính kèm.
    ("0088_drop_hop_dong_module", _migrate_drop_hop_dong_module),
    # Gỡ module ma `san_luong` — sót của "Theo dõi SX" đã gỡ; ghi sản lượng Lát 2 dùng san_xuat:record_output.
    ("0089_drop_san_luong_module", _migrate_drop_san_luong_module),
    # Gỡ module "Khổ giấy chuẩn" — danh mục thừa; khổ giấy nhập tay ở phiếu tính giá.
    ("0090_drop_kho_giay_chuan", _migrate_drop_kho_giay_chuan),
    # Khách chốt MỘT PHẦN: cờ dòng báo giá khách ưng/không (đơn chỉ kéo dòng accepted).
    ("0091_quote_item_accepted", _migrate_quote_item_accepted),
    # Module Kho — đề nghị/phiếu/lô: 4 ô quyền chi tiết. Bảng stock_* là bảng MỚI nên
    # create_all tự dựng, không cần migration; chỉ role_permissions là bảng cũ phải ALTER.
    ("0092_role_permission_kho", _migrate_role_permission_kho),
    ("0093_stock_request_kho_id", _migrate_stock_request_kho_id),
    ("0094_stock_voucher_line_ghi_chu", _migrate_stock_voucher_line_ghi_chu),
    ("0095_material_kho_conversion", _migrate_material_kho_conversion),
    ("0096_stock_request_line_ten_tu_do", _migrate_stock_request_line_ten_tu_do),
    # Nới NOT NULL cũ của material_id (0096 chỉ nới được trên Postgres) → dev SQLite hết
    # IntegrityError khi đề nghị hàng mới. SQLite phải dựng lại bảng, giữ nguyên dữ liệu.
    ("0097_stock_request_line_material_nullable", _migrate_stock_request_line_material_nullable),
    # Tách ghi sổ phiếu khỏi lập phiếu (SoD): can_post cho role_permissions.
    ("0098_role_permission_kho_post", _migrate_role_permission_kho_post),
    # Lưu người ghi sổ phiếu (hiện "ai duyệt/ghi sổ phiếu" trên chi tiết).
    ("0099_stock_voucher_nguoi_ghi_so", _migrate_stock_voucher_nguoi_ghi_so),
    # Đơn giá NHẬP khai ở đề nghị (người đề nghị nhập, phiếu kế thừa; kho không sửa).
    ("0100_stock_request_line_don_gia", _migrate_stock_request_line_don_gia),
    # Quy đổi đơn vị khai ở đề nghị (chuyển từ phiếu sang).
    ("0101_stock_request_line_quy_doi", _migrate_stock_request_line_quy_doi),
    # Kho phản hồi: lý do cấp/nhập thiếu so với còn phải cấp.
    ("0102_stock_request_line_ly_do_thieu", _migrate_stock_request_line_ly_do_thieu),
    # --- Nhánh rebuild-san-xuat (Kế hoạch SX / Gantt) — id chuỗi ĐẦY ĐỦ khác main dù trùng số ---
    # Dọn nền module Kế hoạch SX cũ (bảng còn sót sau khi gỡ code) — bản mới dùng `lsx`/`lsx_cong_doan`.
    ("0092_drop_lenh_sx_cu", _migrate_drop_lenh_sx_cu),
    # Routing lệnh SX lát 2: dữ liệu đủ để lên Gantt (loại bước · đơn vị vào/ra · năng suất & thời
    # gian · số nhân công) + gia công ngoài đầy đủ; bỏ `thue_ngoai`/`don_vi` đã bị thay.
    ("0093_lsx_routing_chi_tiet", _migrate_lsx_routing_chi_tiet),
    # Năng suất mặc định của công đoạn — cho bước làm TAY (không gắn máy) khỏi phải gõ lại mỗi lệnh.
    ("0094_cong_doan_nang_suat", _migrate_cong_doan_nang_suat),
    # Gantt theo máy (lát 2): cờ ca thuộc lịch chạy máy của xưởng — engine tính giờ theo ca thật
    # (nghỉ trưa/đa ca/ca đêm); rỗng → fallback 8h phẳng giữ hành vi lát 1.
    ("0095_work_shift_dung_cho_lich_may", _migrate_work_shift_dung_cho_lich_may),
    # --- Nhánh main (Nhân sự / Lương / Chấm công) — bảng khác, chạy độc lập với khối trên ---
    # PRD v2 Cấu hình lương: khung bậc + mức hợp đồng riêng của NV (tách bậc khỏi tiền).
    ("0088_luong_v2_khung_bac", _migrate_luong_v2_khung_bac),
    # Phiếu lương tách dòng phụ cấp trách nhiệm / thâm niên (B2 — không đổi tổng tiền).
    ("0089_payroll_line_allowance_split", _migrate_payroll_line_allowance_split),
    # Phụ cấp ca/trách nhiệm/thâm niên → KHAI TAY theo từng NV; gỡ đơn giá ca + danh mục phụ cấp.
    ("0090_luong_phu_cap_khai_tay", _migrate_luong_phu_cap_khai_tay),
    ("0091_employee_shift_history", _migrate_employee_shift_history),
    # Bỏ hẳn hệ thống bậc lương (về free-text job_grade) + bỏ phu_cap_trach_nhiem khai tay.
    ("0092_luong_bo_bac_luong", _migrate_luong_bo_bac_luong),
    # Đợt 1: phụ cấp cơm/ca đêm cấp công ty (payroll_params) + thâm niên trước khi vào làm (employees).
    ("0093_luong_phu_cap_com_ca_dem", _migrate_luong_phu_cap_com_ca_dem),
    # Đợt 1b: dời phụ cấp cơm/ca đêm từ payroll_params → khai theo từng CA (work_shifts).
    ("0094_ca_phu_cap_com_ca_dem", _migrate_ca_phu_cap_com_ca_dem),
    # Đợt 2a: work_shifts — đổi night_allowance→shift_allowance · gỡ night_shift.
    ("0095_ca_rename_shift_allowance_go_night_shift", _migrate_ca_rename_shift_allowance_go_night_shift),
    ("0096_luong_insurance_elsewhere", _migrate_luong_insurance_elsewhere),
    ("0097_luong_union_member", _migrate_luong_union_member),
    ("0098_attendance_late_off_days", _migrate_attendance_late_off_days),
    ("0099_payroll_di_tre_manual", _migrate_payroll_di_tre_manual),
    ("0100_ca_night_multiplier", _migrate_ca_night_multiplier),
    ("0101_attendance_night_premium", _migrate_attendance_night_premium),
    ("0102_payroll_night_premium_pay", _migrate_payroll_night_premium_pay),
    ("0103_payroll_ot_night_extra_pct", _migrate_payroll_ot_night_extra_pct),
    ("0104_piece_rate_department_id", _migrate_piece_rate_department_id),
    ("0105_payroll_advance_max_pct", _migrate_payroll_advance_max_pct),
    ("0106_salary_luong_dot_1", _migrate_salary_luong_dot_1),
    ("0107_salary_advance_kind", _migrate_salary_advance_kind),
    ("0108_payroll_line_luong_dot_1_total", _migrate_payroll_line_luong_dot_1_total),
    ("0109_attendance_line_plain_cong", _migrate_attendance_line_plain_cong),
    ("0111_attendance_line_excused_cong", _migrate_attendance_line_excused_cong),
    ("0112_payroll_line_luong_ngay_phep", _migrate_payroll_line_luong_ngay_phep),
    ("0113_attendance_line_paid_leave_fraction", _migrate_attendance_line_paid_leave_fraction),
    ("0114_payroll_adjust_max_per_month", _migrate_payroll_adjust_max_per_month),
    ("0115_payroll_line_thu_nhap_mien_thue", _migrate_payroll_line_thu_nhap_mien_thue),
    ("0116_drop_duplicate_payroll_components", _migrate_drop_duplicate_payroll_components),
    ("0117_seed_missing_payroll_components", _migrate_seed_missing_payroll_components),
    ("0118_payroll_line_thu_nhap_chiu_thue", _migrate_payroll_line_thu_nhap_chiu_thue),
    ("0119_salary_apply_self_deduction", _migrate_salary_apply_self_deduction),
    ("0120_pit_mode_and_flat_rate", _migrate_pit_mode_and_flat_rate),
    ("0121_component_note_and_source", _migrate_component_note_and_source),
    ("0122_seed_open_income_components", _migrate_seed_missing_payroll_components),
    # 0123 dùng LẠI hàm top-up: 4 khoản thưởng vừa thêm vào `_PAYROLL_COMPONENTS_SEED` sẽ được
    # bù cho DB đã seed từ trước. Lưu ý `0116` từng XOÁ đúng 4 code này (hồi đó chúng còn là ô
    # tay ⇒ trùng); nay ô tay đã gỡ nên tạo lại là CÓ CHỦ Ý, không phải lặp lỗi cũ.
    ("0123_seed_bonus_components", _migrate_seed_missing_payroll_components),
    ("0124_move_bonus_columns_to_components", _migrate_move_bonus_columns_to_components),
    ("0125_piece_rate_unit_free_text", _migrate_piece_rate_unit_free_text),
    ("0126_payroll_phat_cap_pct", _migrate_payroll_phat_cap_pct),
    ("0127_job_grade_catalog", _migrate_job_grade_catalog),
    ("0128_employee_salary_commission_pct", _migrate_employee_salary_commission_pct),
    ("0129_job_grade_drop_phu", _migrate_job_grade_drop_phu),
    # Nhánh nội quy / thưởng tổ trưởng (nhập từ dev) — số 0130-0133 TRÙNG dãy khoán ngay dưới là
    # có chủ ý: khoá thật là CẢ CHUỖI id, không đụng nhau. Đừng đánh lại số.
    ("0130_drop_kpi_bonus", _migrate_drop_kpi_bonus),
    ("0131_noi_quy_nguon_va_file_goc", _migrate_noi_quy_nguon_va_file_goc),
    ("0132_noi_quy_nhieu_tai_lieu", _migrate_noi_quy_nhieu_tai_lieu),
    ("0133_nguong_to_truong_theo_san_luong", _migrate_nguong_to_truong_theo_san_luong),
    # Khoán theo ĐẦU VIỆC: 1 đầu việc phủ nhiều công đoạn + trục quy đổi; bước lệnh ghim đầu việc.
    ("0130_piece_rate_cong_doan_mas", _migrate_piece_rate_cong_doan_mas),
    ("0131_lsx_cong_doan_khoan_json", _migrate_lsx_cong_doan_khoan_json),
    ("0132_don_vi_do_chuan_hoa_ho", _migrate_don_vi_do_chuan_hoa_ho),
    # Dọn lệch kiểu cột do bản migration đầu tạo JSONB (create_all ra `json`) — xem docstring.
    ("0133_khoan_json_ve_json", _migrate_khoan_json_ve_json),
    ("0134_don_vi_bai_in_gop_vao_bai", _migrate_don_vi_bai_in_gop_vao_bai),
    # Đổi mô hình quy đổi sang BẢNG CẶP ("1 tấn = 1.000 kg") — chủ thấy mô hình "hệ số về đơn vị
    # gốc" khó hiểu. Chạy SAU 0134 để dữ liệu đơn vị đã dọn xong mới sinh cặp.
    ("0135_don_vi_he_so_goc_sang_cap", _migrate_don_vi_he_so_goc_sang_cap),
    # Dọn cặp 1-1 dư do bản 0135 đầu tiên + seed cùng nối nhóm đếm thành phẩm.
    ("0136_don_vi_don_cap_du", _migrate_don_vi_don_cap_du),
    # Quy đổi ĐỘNG: hệ số được phép là công thức ("1 tờ = dinh_luong * dai * rong" kg).
    ("0137_don_vi_quy_doi_cong_thuc", _migrate_don_vi_quy_doi_cong_thuc),
    # Đơn giá khoán về đúng nghĩa khai báo: bỏ luật khớp ngầm + phép nhân ngầm.
    ("0138_piece_rate_bo_luat_ngam", _migrate_piece_rate_bo_luat_ngam),
    # --- Nhánh tính giá / báo giá — bảng khác, chạy độc lập với khối lương ở trên ---
    # Số 0106+ TRÙNG với dãy lương ngay trên là CÓ CHỦ Ý: hai dãy đánh số song song, khoá
    # thật trong `schema_migrations` là CẢ CHUỖI id nên không đụng nhau. ĐỪNG đánh lại số —
    # đổi id là DB đã chạy rồi sẽ chạy lại migration đó.
    # Diễn giải quy cách dưới mỗi sản phẩm trên bản in báo giá (bung từ tính giá, sửa được).
    ("0106_quote_item_dien_giai", _migrate_quote_item_dien_giai),
    # Bình bài: nhíp GIẤY của máy (khác nhíp kẽm) + bleed/khe cắt trên phiếu tính giá.
    ("0107_may_nhip_giay", _migrate_may_nhip_giay),
    ("0108_ptg_bleed_khe_cat", _migrate_ptg_bleed_khe_cat),
    # Màu pha Pantone — ghi nhận để xưởng biết pha mực; không đổi số kẽm.
    ("0109_ptg_so_mau_pha", _migrate_ptg_so_mau_pha),
    # Nhóm gộp dòng KHI IN cho khách (ruột + bìa của 1 cuốn → 1 dòng trên báo giá / xác nhận đơn).
    # Nhãn chảy PTG → báo giá → đơn; sản xuất KHÔNG đọc, vẫn 1 lệnh mỗi dòng đơn.
    ("0110_ptg_nhom_bao_gia", _migrate_ptg_nhom_bao_gia),
    ("0111_quote_item_nhom", _migrate_quote_item_nhom),
    ("0112_order_line_nhom", _migrate_order_line_nhom),
    # SoD kho: gỡ can_post khỏi vai Thủ kho (lập phiếu ≠ ghi sổ) — seed cũ gộp nên lỡ cấp.
    ("0113_kho_post_thukho_off", _migrate_kho_post_thukho_off),
    # Lý do kho hủy đề nghị (hủy phiếu → đề nghị 'Đã hủy' kèm lý do).
    ("0114_stock_request_ly_do_huy", _migrate_stock_request_ly_do_huy),
    # Chừa tờ in về MỘT nguồn: danh mục Máy. Phiếu chỉ còn ô đè `chua_nhip`.
    ("0139_ptg_drop_chua_thua", _migrate_ptg_drop_chua_thua),
    # Lệnh cũ còn ôm chừa mồ côi trong snapshot → chuyển sang khoá máy, kẻo lệch với phiếu.
    ("0140_lsx_qc_chua_ve_may", _migrate_lsx_qc_chua_ve_may),
    # Đơn giá khoán demo không gắn tổ → bước lệnh không bao giờ thấy; xoá cho sạch bảng khai.
    ("0141_xoa_don_gia_khoan_mo_coi", _migrate_xoa_don_gia_khoan_mo_coi),
    # Máy thay thế: ghi chú tay không ai đọc → bỏ, để `_may_fit` tự kiểm khi gán/kéo máy.
    ("0142_lsx_drop_may_thay_the", _migrate_lsx_drop_may_thay_the),
    # Đơn vị vào/ra của công đoạn: KHAI thay vì dò chữ trong tên — để engine tra bù hao đúng đơn vị
    # ở ranh giới tờ nguyên → tờ in → tờ thành phẩm.
    ("0143_cong_doan_don_vi", _migrate_cong_doan_don_vi),
    # Ba cột chưa từng có ô nhập nhưng vẫn bày ra bản lệnh dưới dạng "—" → bỏ hẳn.
    ("0144_ptg_drop_kho_tp_mo_rong_tay_gap", _migrate_ptg_drop_kho_tp_mo_rong_tay_gap),
    # Bước lệnh: đơn vị cho phép TRỐNG = bước không chạm giấy (chế bản đếm kẽm). Đơn vị nay kế
    # thừa từ danh mục công đoạn, server ghi — client không gửi.
    ("0145_lsx_cong_doan_don_vi_nullable", _migrate_lsx_cong_doan_don_vi_nullable),
    ("0146_khsx_dinh_muc_vat_tu_phu_thuoc", _migrate_khsx_dinh_muc_vat_tu_phu_thuoc),
    # Số tờ in tính thẳng từ SỐ TRANG (lưu lại, không còn là phép tính vứt đi trong popover).
    ("0147_ptg_so_trang", _migrate_ptg_so_trang),
    # Gấp tay / vào keo khai `cái → cái` làm chuỗi bù hao ngược mất ranh giới tờ↔cuốn.
    ("0148_don_vi_khau_sach", _migrate_don_vi_khau_sach),
    # Thuê ngoài: sổ giao – nhận THỰC TẾ (ai giao, ai nhận, số thực gửi/nhận) trên chính bước lệnh.
    ("0149_lsx_cong_doan_giao_nhan_thuc", _migrate_lsx_cong_doan_giao_nhan_thuc),
    # Bài ghép neo ĐÍCH DANH bước in chạy chung tờ (quy ước ngầm theo `nhom` vỡ khi lệnh in 2 lượt).
    ("0150_bai_ghep_buoc_in_step_key", _migrate_bai_ghep_buoc_in_step_key),
    # Bài ghép gộp nhiều công đoạn (CTP/in/cán/bế) → MỖI bước chung một dòng lịch, phải neo được.
    ("0151_xep_lich_bai_ghep_cong_doan", _migrate_xep_lich_bai_ghep_cong_doan),
    # Hao của bài: NULL = chưa khai, 0 = khai "không bù" — hai ý khác nhau, trước dùng chung số 0.
    ("0152_bai_ghep_hao_nullable", _migrate_bai_ghep_hao_nullable),
]


def _migrate_noi_quy_file_registry(db: Session) -> None:
    """Đưa tài liệu có file của luồng ban hành cũ sang danh mục file mới.

    Chỉ lấy bản published mới nhất của mỗi tài liệu và một file gốc xem trước được. Các bảng cũ
    vẫn giữ nguyên; migration không xóa lịch sử.
    """
    tables = set(inspect(db.get_bind()).get_table_names())
    required = {
        "noi_quy_records", "noi_quy_documents", "noi_quy_versions", "noi_quy_attachments",
    }
    if not required.issubset(tables):
        return
    db.execute(text("""
        INSERT INTO noi_quy_records (
            code, name, file_name, file_url, file_type, file_size, note,
            uploaded_by, uploaded_at
        )
        SELECT
            'NQ-LEGACY-' || d.id,
            d.title,
            a.file_name,
            a.file_url,
            CASE
                WHEN lower(a.file_name) LIKE '%.pdf' THEN 'application/pdf'
                WHEN lower(a.file_name) LIKE '%.png' THEN 'image/png'
                WHEN lower(a.file_name) LIKE '%.jpg' OR lower(a.file_name) LIKE '%.jpeg'
                    THEN 'image/jpeg'
                WHEN lower(a.file_name) LIKE '%.webp' THEN 'image/webp'
                ELSE 'application/octet-stream'
            END,
            0,
            'Chuyển từ dữ liệu nội quy cũ',
            COALESCE(a.uploaded_by, v.published_by),
            COALESCE(a.uploaded_at, v.published_at, d.created_at)
        FROM noi_quy_documents d
        JOIN noi_quy_versions v ON v.id = (
            SELECT v2.id FROM noi_quy_versions v2
            WHERE v2.document_id = d.id AND v2.status = 'published'
            ORDER BY v2.published_at DESC, v2.id DESC LIMIT 1
        )
        JOIN noi_quy_attachments a ON a.id = (
            SELECT a2.id FROM noi_quy_attachments a2
            WHERE a2.version_id = v.id
              AND (
                lower(a2.file_name) LIKE '%.pdf' OR lower(a2.file_name) LIKE '%.png'
                OR lower(a2.file_name) LIKE '%.jpg' OR lower(a2.file_name) LIKE '%.jpeg'
                OR lower(a2.file_name) LIKE '%.webp'
              )
            ORDER BY a2.is_import_source DESC, a2.id ASC LIMIT 1
        )
        WHERE COALESCE(a.uploaded_by, v.published_by) IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM noi_quy_records r WHERE r.code = 'NQ-LEGACY-' || d.id
          )
    """))
    db.commit()


MIGRATIONS.append(("0134_noi_quy_file_registry", _migrate_noi_quy_file_registry))


def _migrate_supplier_items(db: Session) -> None:
    """Thu mua: bảng mặt hàng/bảng giá hiện tại theo từng nhà cung cấp."""
    if "suppliers" not in inspect(db.get_bind()).get_table_names():
        return
    id_pk = "INTEGER PRIMARY KEY" if db.get_bind().dialect.name == "sqlite" else "SERIAL PRIMARY KEY"
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS supplier_items ("
        f"id {id_pk}, "
        "supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE, "
        "item_name VARCHAR(255) NOT NULL, "
        "unit VARCHAR(32) NOT NULL, "
        "unit_price BIGINT NOT NULL DEFAULT 0, "
        "vat_percent NUMERIC(6,2) NOT NULL DEFAULT 0, "
        "note TEXT, "
        "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    ))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_supplier_items_supplier_id ON supplier_items (supplier_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_supplier_items_item_name ON supplier_items (item_name)"))
    db.commit()


MIGRATIONS.append(("0151_supplier_items", _migrate_supplier_items))


def _migrate_may_toc_do_min_max(db: Session) -> None:
    """Máy: thêm `toc_do_min` / `toc_do_max` — dải năng lực, CHỈ ĐỂ KHAI.

    `toc_do` giữ nguyên nghĩa (tốc độ TRUNG BÌNH) và vẫn là số duy nhất chảy vào Tính giá / Lệnh
    SX / Xếp lịch — hai cột mới không nối vào công thức nào (chủ 03/08/2026). Nullable, không
    backfill: máy cũ để trống là đúng, KHÔNG bịa min=max=tốc độ hiện có.
    No-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "may_thiet_bi" not in insp.get_table_names():
        return
    existing = _existing_columns(insp, "may_thiet_bi")
    for name in ("toc_do_min", "toc_do_max"):
        if name not in existing:
            db.execute(text(f"ALTER TABLE may_thiet_bi ADD COLUMN {name} NUMERIC(12,2)"))
    db.commit()


MIGRATIONS.append(("0152_may_toc_do_min_max", _migrate_may_toc_do_min_max))


def _migrate_may_don_vi_toc_do_rong_hon(db: Session) -> None:
    """Máy: nới `don_vi_toc_do` VARCHAR(16) → VARCHAR(32).

    Đơn vị tốc độ nay SUY RA từ danh mục `don_vi_do` (chủ tự thêm/xoá) với mã `<ma>_gio`; `ma`
    rộng 24 ⇒ mã có thể tới 28 ký tự. SQLite không ép độ dài nên test không bao giờ bắt được —
    chỉ Postgres THẬT mới lỗi lúc lưu máy. Chỉ Postgres cần ALTER; SQLite no-op."""
    insp = inspect(db.get_bind())
    if "may_thiet_bi" not in insp.get_table_names():
        return
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(text("ALTER TABLE may_thiet_bi ALTER COLUMN don_vi_toc_do TYPE VARCHAR(32)"))
    db.commit()


MIGRATIONS.append(("0153_may_don_vi_toc_do_rong_hon", _migrate_may_don_vi_toc_do_rong_hon))

# Đơn vị được bày trong ô "Đơn vị tốc độ" của màn Máy. CHỈ những thứ máy thật sự chạy theo —
# `g`, `kg`, `tấn`, `thùng`, `ram`, `cm²` là đơn vị kho/mua hàng, bày ra chỉ tổ rối.
# ⚠️ Danh sách này PHẢI khớp bản trong `seed_rebuild.seed_don_vi_do` — `schema_migrations` sống qua
# `drop_all` nên test không chạy lại migration; chỉ seed mới dựng được DB test.
DON_VI_TOC_DO_MAC_DINH = ("to", "kem", "bai", "luot", "cai", "con", "m2", "m")


def _migrate_don_vi_dung_lam_toc_do(db: Session) -> None:
    """Đơn vị: thêm cờ `dung_lam_toc_do` + bật sẵn cho các đơn vị máy thật sự chạy theo.

    Ô "Đơn vị tốc độ" bên màn Máy trước đây đổ CẢ danh mục ra (17 dòng, quá nửa vô nghĩa: g/giờ,
    thùng/giờ…). Cờ này lọc lại. "Xoá đơn vị tốc độ" = bỏ cờ, KHÔNG xoá dòng — bảng dùng chung với
    kho/khoán/mua hàng, xoá thật là gãy quy đổi bên đó."""
    insp = inspect(db.get_bind())
    if "don_vi_do" not in insp.get_table_names():
        return
    if "dung_lam_toc_do" not in _existing_columns(insp, "don_vi_do"):
        db.execute(text(
            "ALTER TABLE don_vi_do ADD COLUMN dung_lam_toc_do BOOLEAN NOT NULL DEFAULT FALSE"))
        # Chỉ bật lúc TẠO CỘT: chạy lại lần sau sẽ đè mất lựa chọn người dùng đã sửa.
        ma_list = ", ".join(f"'{m}'" for m in DON_VI_TOC_DO_MAC_DINH)
        db.execute(text(f"UPDATE don_vi_do SET dung_lam_toc_do = TRUE WHERE ma IN ({ma_list})"))
    db.commit()


MIGRATIONS.append(("0154_don_vi_dung_lam_toc_do", _migrate_don_vi_dung_lam_toc_do))


def _migrate_nhom_may_backfill(db: Session) -> None:
    """Nạp danh mục `nhom_may` từ dữ liệu ĐANG CÓ + các tên mặc định.

    BẢNG do `create_all` dựng (bảng mới không cần migration) — migration này chỉ để **backfill**:
    trước đây "nhóm máy" chỉ là chữ tự do trên từng máy, nên DB đang chạy có những nhóm do xưởng
    tự đặt. Không nạp thì mở màn ra là danh sách trống trơn và mọi máy trỏ vào nhóm "không tồn
    tại". Lấy DISTINCT `may_thiet_bi.loai_may` để KHÔNG NUỐT nhóm nào."""
    from .models.may_thiet_bi import NHOM_MAY_MAC_DINH

    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    if "nhom_may" not in tables:
        return
    da_co = {r[0] for r in db.execute(text("SELECT ten FROM nhom_may")).all()}
    ten_can = list(NHOM_MAY_MAC_DINH)
    if "may_thiet_bi" in tables:
        ten_can += [
            r[0] for r in db.execute(text(
                "SELECT DISTINCT loai_may FROM may_thiet_bi "
                "WHERE loai_may IS NOT NULL AND TRIM(loai_may) <> ''")).all()
        ]
    for ten in ten_can:
        ten = (ten or "").strip()
        if ten and ten not in da_co:
            # PHẢI ghi cả created_at/updated_at: model khai NOT NULL với default phía PYTHON
            # (`default=_utcnow`), không có server_default — nên INSERT bằng SQL thô mà bỏ trống
            # là rơi thẳng NOT NULL constraint.
            db.execute(text(
                "INSERT INTO nhom_may (ten, active, created_at, updated_at) "
                "VALUES (:t, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"), {"t": ten})
            da_co.add(ten)
    db.commit()


MIGRATIONS.append(("0155_nhom_may_backfill", _migrate_nhom_may_backfill))


def _migrate_supplier_items_is_active_default(db: Session) -> None:
    """Thu mua: giữ `supplier_items.is_active` như cột kỹ thuật ẩn nếu DB cũ đã có.

    UI/API không dùng trạng thái mặt hàng, nhưng một số DB live đã có cột này dạng NOT NULL.
    Backfill/default = true để thêm mặt hàng NCC không bị lỗi thiếu `is_active`.
    """
    insp = inspect(db.get_bind())
    if "supplier_items" not in insp.get_table_names():
        return
    existing = _existing_columns(insp, "supplier_items")
    if "is_active" not in existing:
        db.execute(text("ALTER TABLE supplier_items ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true"))
        db.commit()
        return
    db.execute(text("UPDATE supplier_items SET is_active = true WHERE is_active IS NULL"))
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("ALTER TABLE supplier_items ALTER COLUMN is_active SET DEFAULT true"))
    db.commit()


MIGRATIONS.append(("0156_supplier_items_is_active_default", _migrate_supplier_items_is_active_default))


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


def _migrate_phu_cap_ca_theo_ca(db: Session) -> None:
    """Nối Đợt 2 phụ cấp cơm/ca (chủ 03/08/2026): 3 cột mới.

    · `attendance_period_lines.ca_lam_json` — đóng băng {ca → [công từng ngày]} qua Chốt công.
      Thiếu nó thì phụ cấp NHẢY SỐ đúng lúc bấm Chốt (draft một số, chốt xong một số).
    · `payroll_lines.meal_allowance_pay` / `.shift_allowance_pay` — hai cột RIÊNG, không gộp một
      cục: phiếu lương phải nói rõ khoản nào, và tiền ăn giữa ca có trần miễn thuế riêng nên sau
      này còn tách được.

    Guard theo cột → idempotent. No-op trên DB fresh (create_all đã dựng)."""
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    if "attendance_period_lines" in tables:
        if "ca_lam_json" not in _existing_columns(insp, "attendance_period_lines"):
            db.execute(text("ALTER TABLE attendance_period_lines ADD COLUMN ca_lam_json TEXT"))
    if "payroll_lines" in tables:
        co = _existing_columns(insp, "payroll_lines")
        for col in ("meal_allowance_pay", "shift_allowance_pay"):
            if col not in co:
                db.execute(text(
                    f"ALTER TABLE payroll_lines ADD COLUMN {col} NUMERIC(14,2) NOT NULL DEFAULT 0"))
    if "payroll_params" in tables:
        if "phu_cap_ca_min_cong" not in _existing_columns(insp, "payroll_params"):
            db.execute(text(
                "ALTER TABLE payroll_params ADD COLUMN phu_cap_ca_min_cong "
                "NUMERIC(5,2) NOT NULL DEFAULT 0.5"))
    db.commit()


MIGRATIONS.append(("0157_phu_cap_ca_theo_ca", _migrate_phu_cap_ca_theo_ca))


def _migrate_bhxh_mien_tu_so_ngay(db: Session) -> None:
    """Ngưỡng "14 ngày không lương thì không đóng BHXH" thành THAM SỐ (chủ 04/08/2026 — *"đang
    hard code à, vậy sao đổi luật thì sao"*).

    Trước đó `_compute` so với hằng số `BHXH_MIEN_TU_SO_NGAY = 14` viết thẳng trong service. Đây là
    mức LUẬT (QĐ 595/QĐ-BHXH Đ42.4) nên không bỏ luật, chỉ bỏ chỗ viết cứng — cùng lối đã làm cho
    `phat_cap_pct` (0126) và `pit_flat_rate` (0120). Mặc định 14 giữ nguyên hành vi cũ; `0` = tắt.

    Guard theo cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if ("payroll_params" in insp.get_table_names()
            and "bhxh_mien_tu_so_ngay" not in _existing_columns(insp, "payroll_params")):
        db.execute(text(
            "ALTER TABLE payroll_params ADD COLUMN bhxh_mien_tu_so_ngay "
            "INTEGER NOT NULL DEFAULT 14"))
    db.commit()


MIGRATIONS.append(("0158_bhxh_mien_tu_so_ngay", _migrate_bhxh_mien_tu_so_ngay))


def _migrate_thu_mua_bo_phan_khong_duyet(db: Session) -> None:
    """Bộ phận Mua hàng KHÔNG duyệt phiếu mua (chủ 04/08/2026: *"thu mua làm gì có quyền duyệt,
    từ chối, huỷ — nó chỉ có giám đốc và người được trao quyền chứ"*).

    Tách vai: ai đề xuất chi tiền thì không được là người đồng ý chi. `seed.py` đã sửa nhưng seed
    chỉ áp cho DB TRẮNG — hệ đang chạy phải gỡ bằng migration, không thì trưởng bộ phận mua hàng
    vẫn duyệt được phiếu của chính mình.

    Gỡ theo BỘ PHẬN chứ không theo tên vai: tên vai sửa tay lúc nào cũng được, mà sửa xong thì câu
    lệnh bám theo tên câm lặng thất hiệu.

    ⚠️ CỐ Ý chỉ gỡ cho bộ phận "Mua hàng". Vai nào khác đang có `thu_mua.can_approve` thì KHÔNG
    đụng — đoán mò rồi gỡ nhầm quyền của giám đốc là tắc cả luồng duyệt, mà không ai hiểu vì sao.
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    if not {"role_permissions", "roles", "departments"} <= tables:
        return
    db.execute(text(
        "UPDATE role_permissions SET can_approve = FALSE "
        "WHERE module_key = 'thu_mua' AND role_id IN ("
        "  SELECT r.id FROM roles r JOIN departments d ON d.id = r.department_id "
        "  WHERE d.name = 'Mua hàng')"
    ))
    db.commit()


MIGRATIONS.append(("0159_thu_mua_bo_phan_khong_duyet", _migrate_thu_mua_bo_phan_khong_duyet))


def _migrate_xoa_chung_tu_ke_toan_lam_lai(db: Session) -> None:
    """🔴 XOÁ SẠCH chứng từ kế toán để dựng lại phân hệ (chủ 04/08/2026: "đập cả bảng dữ liệu").

    Xoá con trước cha sau cho khỏi vướng khoá ngoại:
      `payment_receipt_attachments` → `payment_voucher_attachments` → `payment_receipts`
      → `payment_vouchers`, rồi reset bộ đếm số chứng từ về 0 (đánh lại từ PC00001).

    ⚠️ KHÔNG lùi lại được. Chủ đã xác nhận dữ liệu hiện tại là dữ liệu thử.

    CỐ Ý GIỮ `company_bank_accounts` và `supplier_bank_accounts`: đó là thông tin ai đó ngồi gõ
    (số tài khoản, chi nhánh), không phải chứng từ phát sinh — xoá đi là bắt gõ lại mà chẳng
    được gì.

    Chạy MỘT LẦN: `schema_migrations` nhớ tên nên lần khởi động sau không xoá lại. Nhưng nếu ai đó
    xoá dòng ghi nhớ đó thì nó xoá lần nữa — đừng làm vậy trên DB có dữ liệu thật.
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    for name in ("payment_receipt_attachments", "payment_voucher_attachments",
                 "payment_receipts", "payment_vouchers"):
        if name in tables:
            db.execute(text(f"DELETE FROM {name}"))
    if "document_sequences" in tables:
        db.execute(text(
            "UPDATE document_sequences SET current_number = 0 WHERE doc_type = 'payment_voucher'"))
    db.commit()


MIGRATIONS.append(("0160_xoa_chung_tu_ke_toan_lam_lai", _migrate_xoa_chung_tu_ke_toan_lam_lai))


def _migrate_thu_mua_pham_vi_nhin(db: Session) -> None:
    """Co phạm vi nhìn phiếu mua theo vai (chủ 04/08/2026: *"tôi là nhân viên chỉ thấy đơn của tôi
    thôi, còn trưởng bộ phận hoặc giám đốc mới thấy cả"*).

    - Nhân viên mua hàng → `own` (chỉ phiếu mình lập)
    - Trưởng bộ phận mua hàng → `department` (cả bộ phận)
    - Giám đốc giữ `all` — KHÔNG đụng tới.

    Trước đây cả hai vai đều `all`, mà `list_requests` lại không hề đọc scope nên ai có
    `thu_mua:read` là thấy phiếu toàn công ty. Service đã vá; đây là vá phần khai báo trên DB
    đang chạy (seed chỉ áp cho DB trắng).

    Đổi theo **bộ phận + tên vai** — không quét cả bảng, để không cắt nhầm phạm vi của vai khác.
    """
    insp = inspect(db.get_bind())
    if not {"role_permissions", "roles", "departments"} <= set(insp.get_table_names()):
        return
    for ten_vai, scope in (("Nhân viên mua hàng", "own"),
                           ("Trưởng bộ phận mua hàng", "department")):
        db.execute(
            text(
                "UPDATE role_permissions SET scope = :sc "
                "WHERE module_key = 'thu_mua' AND role_id IN ("
                "  SELECT r.id FROM roles r JOIN departments d ON d.id = r.department_id "
                "  WHERE d.name = 'Mua hàng' AND r.name = :ten)"
            ),
            {"sc": scope, "ten": ten_vai},
        )
    db.commit()


MIGRATIONS.append(("0161_thu_mua_pham_vi_nhin", _migrate_thu_mua_pham_vi_nhin))


def _migrate_so_thuc_nhan_dong_phieu_mua(db: Session) -> None:
    """Số THỰC NHẬN từng dòng phiếu mua, nền cho màn Công nợ phải trả (chủ 05/08/2026).

    Trước đó `mark_received` chỉ lật một trạng thái, không ghi được hàng về BAO NHIÊU ⇒ hệ luôn
    hiểu NCC giao đủ. Giao thiếu 20% mà công nợ vẫn ghi đủ 100% là kế toán chi thừa tiền thật.

    Cột để **NULL** (không DEFAULT): null = chưa ai khai ⇒ service coi như nhận đủ `quantity`. Nhờ
    vậy mọi phiếu cũ giữ nguyên số tiền, không đơn nào tự đổi giá trị sau khi nâng cấp. Nếu đặt
    DEFAULT 0 thì mọi đơn cũ hoá thành "nhận 0" và công nợ về 0 sạch — mất trắng nợ đang có.

    Guard theo cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if ("purchase_request_lines" in insp.get_table_names()
            and "received_quantity" not in _existing_columns(insp, "purchase_request_lines")):
        db.execute(text(
            "ALTER TABLE purchase_request_lines ADD COLUMN received_quantity NUMERIC(14,2)"))
    db.commit()


MIGRATIONS.append(("0162_so_thuc_nhan_dong_phieu_mua", _migrate_so_thuc_nhan_dong_phieu_mua))


def _migrate_noi_dong_phieu_mua_voi_dong_yeu_cau(db: Session) -> None:
    """Nối DÒNG phiếu mua với DÒNG yêu cầu đã đẻ ra nó (chủ 05/08/2026: *"bấm vào chi tiết thì nó
    sẽ hiện trạng thái của từng sản phẩm chứ nhỉ"*).

    Trước đó nối duy nhất là `purchase_request_sources` — PHIẾU ↔ YÊU CẦU, ở mức đầu phiếu. Biết
    "PMH-01 đến từ YCMH-05" nhưng không biết dòng giấy trong PMH-01 là dòng nào của YCMH-05, nên
    không hiện được trạng thái từng sản phẩm, và trạng thái YCMH chỉ suy được ở mức phiếu.

    ⚠️ Chỉ thêm CỘT, **không** thêm khoá ngoại: `ALTER TABLE ... ADD CONSTRAINT` không chạy trên
    SQLite nên migration sẽ vỡ ở môi trường khác. DB dựng mới bằng `create_all` thì có khoá ngoại
    (khai trong model); DB đang chạy thì không. Hệ quả: xoá một dòng YCMH có thể để lại id mồ côi
    trên DB live ⇒ chỗ đọc PHẢI chịu được "nối tới dòng không còn tồn tại", đừng giả định luôn tìm
    thấy.

    Guard theo cột → idempotent, no-op trên DB create_all mới."""
    insp = inspect(db.get_bind())
    if "purchase_request_lines" not in insp.get_table_names():
        return
    if "department_request_line_id" not in _existing_columns(insp, "purchase_request_lines"):
        db.execute(text(
            "ALTER TABLE purchase_request_lines ADD COLUMN department_request_line_id INTEGER"))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_purchase_request_lines_department_request_line_id "
        "ON purchase_request_lines (department_request_line_id)"))
    db.commit()


MIGRATIONS.append(
    ("0163_noi_dong_phieu_mua_voi_dong_yeu_cau", _migrate_noi_dong_phieu_mua_voi_dong_yeu_cau)
)
