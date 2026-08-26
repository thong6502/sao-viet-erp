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
import os
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


def _migrate_ptg_muc_tap(db: Session) -> None:
    """Tính giá: `phieu_thanh_phan.muc_a` / `muc_b` — TẬP MÃ MỰC mỗi mặt thay cho con số.

    Vì sao phải là tập: tự trở / trở nhíp dùng CHUNG một bộ bản cho cả hai mặt nên số kẽm là
    `|A ∪ B|`. Mặt A `CMYK` với mặt B `185C` ra **5** kẽm; công thức cũ lấy `so_mau_a` ra 4 —
    thiếu đúng bản Pantone, ra tới máy mới lộ. Hai con số không đủ dữ liệu để tính hợp.

    BACKFILL. `N màu process` → tiền tố của `[K, C, M, Y]` (đen trước, đúng thứ tự xưởng gọi
    "1 màu" = đen), `so_mau_pha` màu pha → gắn vào mặt A thành `PHA 1..N`. Hệ quả CỐ Ý: tập bên
    ít màu LUÔN là con của bên nhiều màu ⇒ `|A ∪ B| = max(|A|,|B|)`, đúng bằng số kẽm tự trở mà
    engine cũ tính. TỔNG `so_mau_a + so_mau_b + so_mau_pha` (thứ công thức tiền mực dùng) cũng
    giữ nguyên ở mọi tổ hợp — đã quét 7×7×4×4 để chắc.

    Số kẽm chỉ đổi ở HAI ca, cả hai đều là ca engine cũ tính SAI:
      · tự trở / trở nhíp có mặt B nhiều màu hơn mặt A (cũ chỉ lấy `so_mau_a`, bỏ mất mặt B);
      · khai `so_mau_a ≥ 5` rồi in tự trở (process chỉ có 4 màu — phần dư là mực gì thì bản khai
        cũ không nói, backfill đọc thành mực riêng của từng mặt).
    Đo trên DB dev 2026-08-05: 0 hàng rơi vào ca một, 2 hàng khai 5 màu nhưng đều in `mot_mat`
    nên số kẽm không đổi. Muốn số đúng cho hai ca đó thì phải khai lại mực thật ở màn phiếu.

    Idempotent: cột đã có thì bỏ qua hẳn (không backfill đè lên mực người dùng đã khai)."""
    insp = inspect(db.get_bind())
    if "phieu_thanh_phan" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "phieu_thanh_phan")
    them = [c for c in ("muc_a", "muc_b") if c not in cols]
    for c in them:
        # JSON (không JSONB) để khớp thứ create_all sinh ra trên DB fresh — lệch kiểu giữa hai
        # đường tạo bảng đã từng phải đẻ nguyên một migration dọn (0133).
        db.execute(text(f"ALTER TABLE phieu_thanh_phan ADD COLUMN {c} JSON"))
    db.commit()
    if not them:
        return

    # Luật chuyển số → tập nằm ở ENGINE, không chép lại ở đây: engine cũng phải dùng đúng luật này
    # khi đọc thành phần chỉ-có-số (seed/script), hai bản là hai chỗ để lệch.
    from .services.thanh_phan_engine import tap_muc_tu_so

    rows = db.execute(text(
        "SELECT id, so_mau_a, so_mau_b, so_mau_pha FROM phieu_thanh_phan"
    )).fetchall()
    for r in rows:
        a, b = tap_muc_tu_so(r[1], r[2], r[3])
        db.execute(
            text("UPDATE phieu_thanh_phan SET muc_a = :a, muc_b = :b WHERE id = :i"),
            {"a": json.dumps(a, ensure_ascii=False), "b": json.dumps(b, ensure_ascii=False),
             "i": r[0]},
        )
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


def _migrate_buoc_phat_sinh_phut(db: Session) -> None:
    """Ô "Thời gian khác" trên bước — phút phát sinh người kế hoạch gõ thêm.

    Đi cùng đợt chốt công thức thời lượng 2026-08-04::

        thời lượng = thời gian khác + chuẩn bị (từ MÁY) + SL vào × 60 ÷ tốc độ × số lượt

    Sau đợt đó mọi ô thời gian khác trên bước đều thành READ-ONLY (kế thừa từ module Máy), nên
    đây là ô DUY NHẤT người kế hoạch còn gõ được — phải có cột thật để lưu, không nhét được vào
    cột cũ nào: `setup_phut`/`chay_phut`/`cho_phut`/`di_chuyen_phut`/`ve_sinh_phut` đều đã thành
    dormant và mang nghĩa cũ, dùng lại là trộn hai nghĩa vào một cột.

    Thêm cho CẢ HAI bảng bước (`lsx_cong_doan` + `bai_ghep_cong_doan` mirror nhau). Idempotent;
    no-op trên DB fresh (create_all đã ra cột) và DB chưa có bảng."""
    insp = inspect(db.get_bind())
    ten_bang = insp.get_table_names()
    for bang in ("lsx_cong_doan", "bai_ghep_cong_doan"):
        if bang not in ten_bang:
            continue
        if "phat_sinh_phut" in _existing_columns(insp, bang):
            continue
        db.execute(text(
            f"ALTER TABLE {bang} ADD COLUMN phat_sinh_phut NUMERIC(10,2) NOT NULL DEFAULT 0"
        ))
    db.commit()


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

    ⚠️⚠️ HAI CÔNG THỨC MỰC VÀ MÀNG DƯỚI ĐÂY SAI THANG 10⁶ — biết và CỐ Ý để nguyên (chủ chốt
    2026-08-09). Hệ số viết cho diện tích tính bằng MÉT, nhưng `dai_in`/`rong_in` engine đưa vào là
    MILIMÉT ⇒ diện tích to gấp một triệu lần::

        1.000 tờ 650×900, in 4 màu → 702.000 kg mực  = 175,5 TỶ đ   (đúng: 0,7 kg = 175.500 đ)
        1.000 tờ cán màng          → 585.000.000 m²  = 1.755 TỶ đ   (đúng: 585 m² = 1.755.000 đ)

    Không sửa vì xưởng tính giá KHOÁN THEO CÔNG ĐOẠN, không thêm dòng vật tư rời nào — hai công
    thức này hiện không chảy vào phiếu nào. Migration này đã CHẠY trên các DB cũ, nên sửa ở đây
    KHÔNG cứu được chúng; muốn dứt điểm phải viết migration MỚI chia 10⁶ (và chỉ đụng hàng còn
    nguyên chuỗi gốc, đừng đè công thức xưởng tự sửa).

    Ai định thêm dòng vật tư vào phiếu tính giá: SỬA HỆ SỐ TRƯỚC, không thì ra báo giá 175 tỷ.

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


def _migrate_job_grade_ten_dan_da(db: Session) -> None:
    """Đổi tên 5 bậc sang bộ DÂN DÃ theo cách xưởng gọi nhau (chủ 2026-08-19):
    Bậc 1…5 → Thợ lành nghề / Thợ vững / Thợ thường / Tập việc / Lính mới.
    Bậc 1 (cao nhất, cứng tay nhất) → "Thợ lành nghề"; Bậc 5 (thấp nhất) → "Lính mới".

    Đổi tên TẠI CHỖ theo `code`, GIỮ NGUYÊN id/seq/hạng — không ai bị đổi bậc, không cần gán lại
    (giống 0129). Chỉ đụng dòng CÒN NGUYÊN tên seed cũ ("Bậc N"); chủ đã tự đặt tên bậc nào thì
    giữ tên đó. Guard bằng chính `WHERE name = 'Bậc N'` nên chạy lại lần hai là no-op, và DB dựng
    mới đã seed thẳng tên dân dã (JOB_GRADE_SEED) thì cũng không còn "Bậc N" để đổi."""
    insp = inspect(db.get_bind())
    if "job_grades" not in insp.get_table_names():
        return
    doi = (("bac_1", "Bậc 1", "Thợ lành nghề"), ("bac_2", "Bậc 2", "Thợ vững"),
           ("bac_3", "Bậc 3", "Thợ thường"), ("bac_4", "Bậc 4", "Tập việc"),
           ("bac_5", "Bậc 5", "Lính mới"))
    for code, ten_cu, ten_moi in doi:
        db.execute(
            text("UPDATE job_grades SET name = :n WHERE code = :c AND name = :cu"),
            {"n": ten_moi, "c": code, "cu": ten_cu},
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
    cols = _existing_columns(insp, "stock_request_lines")
    if "ten_tu_do" not in cols:
        db.execute(text("ALTER TABLE stock_request_lines ADD COLUMN ten_tu_do VARCHAR(255)"))
    # Nới material_id (hàng free-text để rỗng). Postgres nới tại chỗ; SQLite không ALTER được
    # NOT NULL cũ → dev drop dev.db để create_all dựng lại theo model (đã nullable). Tests dùng
    # DB in-memory nên luôn theo model mới.
    #
    # PHẢI kiểm cột còn tồn tại: mg 0171 đã DROP `material_id` (kho đổi sang cặp `hang_loai/hang_id`)
    # và DB dựng mới bằng `create_all` cũng không có cột này, nên ALTER thẳng là nổ
    # `column "material_id" does not exist`. Chỉ Postgres mới chạy nhánh này nên SQLite (test) không
    # thấy — job CI "Migration trên Postgres trắng" bắt đúng ca đó 2026-08-09, lần chạy đầu tiên.
    if "material_id" in cols and db.get_bind().dialect.name == "postgresql":
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


def _migrate_stock_voucher_line_vi_tri(db: Session) -> None:
    """Vị trí cất lô (NHẬP) khai ở dòng phiếu: thêm stock_voucher_lines.vi_tri (VARCHAR(100)
    nullable). Ghi sổ chép sang stock_lots.vi_tri. No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "stock_voucher_lines" not in insp.get_table_names():
        return
    if "vi_tri" not in _existing_columns(insp, "stock_voucher_lines"):
        db.execute(text("ALTER TABLE stock_voucher_lines ADD COLUMN vi_tri VARCHAR(100)"))
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


def _migrate_stock_attachment_urls(db: Session) -> None:
    """Đính kèm phiếu kho từng lưu file_url `/static/kho/..` (mount /static đã gỡ vì lộ file) nên
    không mở được. Đổi sang `/api/files/kho/..` (router có đăng nhập). File trên đĩa vẫn đúng chỗ
    (LocalStorage gốc = <backend>/static) → chỉ cần sửa URL. `/static/` = 8 ký tự → substr từ vị trí 9."""
    insp = inspect(db.get_bind())
    if not insp.has_table("stock_voucher_attachments"):
        return
    db.execute(text(
        "UPDATE stock_voucher_attachments "
        "SET file_url = '/api/files/' || substr(file_url, 9) "
        "WHERE file_url LIKE '/static/%'"
    ))
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
        # Vị trí cất lô (NHẬP) khai ở dòng phiếu; ghi sổ chép sang lô.
    ("0151_stock_voucher_line_vi_tri", _migrate_stock_voucher_line_vi_tri),
    # Đính kèm phiếu kho: đổi file_url /static/kho/.. → /api/files/kho/.. (mount /static đã gỡ).
    ("0152_stock_attachment_url_api_files", _migrate_stock_attachment_urls),

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
    # Ô "Thời gian khác" — ô DUY NHẤT còn gõ được sau khi thời lượng bước kế thừa hết từ máy.
    ("0153_buoc_phat_sinh_phut", _migrate_buoc_phat_sinh_phut),
    # Mực in thành TẬP mã thay cho con số — số kẽm tự trở là |A ∪ B|, không tính được từ 2 số.
    ("0154_ptg_muc_tap", _migrate_ptg_muc_tap),
    # Đổi tên 5 bậc tay nghề sang bộ DÂN DÃ (Thợ lành nghề…Lính mới) — đổi tên tại chỗ, giữ hạng.
    ("0155_job_grade_ten_dan_da", _migrate_job_grade_ten_dan_da),
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


def _migrate_dau_viec_dai_nang_suat(db: Session) -> None:
    """Định mức đầu việc: thêm dải năng suất (min/max) + đơn vị năng suất KHAI BÁO.

    Bước Tổ nay có ba mức năng suất như máy có ba mức tốc độ — `nang_suat_nguoi_gio` giữ nguyên
    nghĩa TRUNG BÌNH (số đang chảy vào công thức), hai cột mới chỉ để ra khoảng nhanh–chậm.
    Nullable, KHÔNG backfill: định mức cũ để trống là đúng, ba mức bằng nhau.

    `don_vi_nang_suat` là NHÃN người khai chọn — engine không quy đổi theo nó (bước quy đổi làm
    sau). No-op trên DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "cong_doan_dau_viec" not in insp.get_table_names():
        return
    existing = _existing_columns(insp, "cong_doan_dau_viec")
    for name, kieu in (
        ("nang_suat_nguoi_gio_min", "NUMERIC(14,2)"),
        ("nang_suat_nguoi_gio_max", "NUMERIC(14,2)"),
        ("don_vi_nang_suat", "VARCHAR(32)"),
    ):
        if name not in existing:
            db.execute(text(f"ALTER TABLE cong_doan_dau_viec ADD COLUMN {name} {kieu}"))
    db.commit()


MIGRATIONS.append(("0158_dau_viec_dai_nang_suat", _migrate_dau_viec_dai_nang_suat))


def _migrate_buoc_don_vi_nang_suat_rong_hon(db: Session) -> None:
    """Bước lệnh / bước chung bài ghép: nới `don_vi_nang_suat` VARCHAR(10) → VARCHAR(32).

    Trước đây cột chỉ chứa ba mã suy ra (`to_gio` · `cai_gio` · `kem_gio`, dài nhất 7). Bước Tổ
    nay chép xuống mã người khai chọn ở định mức, mà `ban_proof_gio` đã 13 ký tự — SQLite không
    ép độ dài nên test vẫn xanh, chỉ Postgres THẬT mới lỗi lúc lưu. Chỉ Postgres cần ALTER."""
    insp = inspect(db.get_bind())
    if db.get_bind().dialect.name != "postgresql":
        return
    tables = insp.get_table_names()
    for bang in ("lsx_cong_doan", "bai_ghep_cong_doan"):
        if bang in tables:
            db.execute(text(f"ALTER TABLE {bang} ALTER COLUMN don_vi_nang_suat TYPE VARCHAR(32)"))
    db.commit()


MIGRATIONS.append(("0159_buoc_don_vi_nang_suat_rong_hon", _migrate_buoc_don_vi_nang_suat_rong_hon))


def _migrate_dau_viec_so_nguoi_toi_thieu(db: Session) -> None:
    """Định mức đầu việc: thêm `so_nguoi_toi_thieu` — mốc nhân lực thứ ba.

    NOT NULL DEFAULT 1: dòng cũ nhận 1, đọc ra là "không ràng buộc" nên hành vi không đổi.
    Mới là KHAI BÁO — chưa vào công thức thời lượng, chưa chặn gì; service chỉ kiểm thứ tự
    1 ≤ tối thiểu ≤ tiêu chuẩn ≤ tối đa."""
    insp = inspect(db.get_bind())
    if "cong_doan_dau_viec" not in insp.get_table_names():
        return
    if "so_nguoi_toi_thieu" not in _existing_columns(insp, "cong_doan_dau_viec"):
        db.execute(text(
            "ALTER TABLE cong_doan_dau_viec ADD COLUMN so_nguoi_toi_thieu "
            "INTEGER NOT NULL DEFAULT 1"))
    db.commit()


MIGRATIONS.append(("0160_dau_viec_so_nguoi_toi_thieu", _migrate_dau_viec_so_nguoi_toi_thieu))


def _migrate_buoc_so_nhan_cong_toi_thieu(db: Session) -> None:
    """Bước lệnh / bước chung bài ghép: thêm `so_nhan_cong_toi_thieu`.

    Ba mốc nhân lực nay KẾ THỪA từ định mức đầu việc nhưng SỬA ĐƯỢC tại bước, nên mốc thứ ba
    phải có chỗ đứng riêng trên bước chứ không chỉ nằm trong `khoan_json`. Nullable — bước cũ để
    trống, đọc ra là 'chưa khai'."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    for bang in ("lsx_cong_doan", "bai_ghep_cong_doan"):
        if bang in tables and "so_nhan_cong_toi_thieu" not in _existing_columns(insp, bang):
            db.execute(text(f"ALTER TABLE {bang} ADD COLUMN so_nhan_cong_toi_thieu INTEGER"))
    db.commit()


MIGRATIONS.append(("0161_buoc_so_nhan_cong_toi_thieu", _migrate_buoc_so_nhan_cong_toi_thieu))


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


MIGRATIONS.append(("0162_bhxh_mien_tu_so_ngay", _migrate_bhxh_mien_tu_so_ngay))


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


MIGRATIONS.append(("0163_thu_mua_bo_phan_khong_duyet", _migrate_thu_mua_bo_phan_khong_duyet))


def _migrate_xoa_chung_tu_ke_toan_lam_lai(db: Session) -> None:
    """XOÁ SẠCH chứng từ kế toán để dựng lại phân hệ (chủ 04/08/2026: "đập cả bảng dữ liệu").

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


MIGRATIONS.append(("0164_xoa_chung_tu_ke_toan_lam_lai", _migrate_xoa_chung_tu_ke_toan_lam_lai))


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


MIGRATIONS.append(("0165_thu_mua_pham_vi_nhin", _migrate_thu_mua_pham_vi_nhin))


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


MIGRATIONS.append(("0166_so_thuc_nhan_dong_phieu_mua", _migrate_so_thuc_nhan_dong_phieu_mua))


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
    ("0167_noi_dong_phieu_mua_voi_dong_yeu_cau", _migrate_noi_dong_phieu_mua_voi_dong_yeu_cau)
)


def _migrate_cong_doan_nhom_may_cho_phep(db: Session) -> None:
    """Cột `nhom_may_cho_phep` (JSON list tên nhóm máy) cho `cong_doan` — chặn gán máy SAI LOẠI ở
    bước (vd Ghi kẽm CTP không cho gán máy Bế). NULL = chưa khai = không ràng buộc.

    ADD COLUMN kiểu `JSON` chạy trên cả Postgres (json) lẫn SQLite (TEXT affinity).

    Backfill bằng raw SQL UPDATE nêu ĐÍCH DANH cột — TUYỆT ĐỐI không `db.query(CongDoan)`. Một ORM
    full-select kéo THEO MỌI cột model hiện tại, kể cả cột do migration SAU thêm (vd
    `he_so_ngoai_dong` ở 0196); trên DB prod cũ chưa có cột đó, select 500 `UndefinedColumn` ngay
    trong bước 0168 này (deploy đỏ 2026-08-21). UPDATE tường minh chỉ đụng `ten` + `nhom_may_cho_phep`
    nên miễn nhiễm cột-tương-lai; `json.dumps` tự serialize, Postgres ép chuỗi→json trong ngữ cảnh
    gán (không cần cast tay), SQLite lưu text. Chạy NGOÀI nhánh ADD + lọc `IS NULL` nên idempotent kể
    cả khi lượt trước đã ADD cột rồi chết giữa chừng (cột có sẵn, hàng còn NULL)."""
    insp = inspect(db.get_bind())
    if "cong_doan" not in insp.get_table_names():
        return
    if "nhom_may_cho_phep" not in _existing_columns(insp, "cong_doan"):
        db.execute(text("ALTER TABLE cong_doan ADD COLUMN nhom_may_cho_phep JSON"))
        db.commit()
    _bf = {
        "Ghi kẽm CTP": ["Chế bản"],
        "In offset": ["Máy in", "In ngoài"],
        "Cán màng bóng": ["Cán màng / UV"],
        "Bồi sóng": ["Bồi"],
        "Ép kim": ["Bế"],
        "Bế nổi": ["Bế"],
    }
    for ten, nhoms in _bf.items():
        db.execute(
            text(
                "UPDATE cong_doan SET nhom_may_cho_phep = :val "
                "WHERE ten = :ten AND nhom_may_cho_phep IS NULL"
            ),
            {"val": json.dumps(nhoms, ensure_ascii=False), "ten": ten},
        )
    db.commit()


MIGRATIONS.append(
    ("0168_cong_doan_nhom_may_cho_phep", _migrate_cong_doan_nhom_may_cho_phep)
)


def _migrate_xoa_cap_quy_doi_ngang_loai_do(db: Session) -> None:
    """Xoá cặp quy đổi SỐ CỐ ĐỊNH nối tờ với đơn vị KHỐI LƯỢNG — dữ liệu sai khai tay qua UI.

    DB dev đang có `1 tờ = 1.000 g`, tức mọi tờ giấy nặng đúng 1 kg. Thực tế tờ 65×86 Couché 150
    nặng 0,084 kg còn tờ 79×109 Couché 300 nặng 0,258 kg — con số này TUỲ khổ + định lượng, nên
    danh mục đã có sẵn cặp ĐỘNG `1 tờ = dinh_luong * dai * rong kg`. Hai dòng cùng trả lời một câu
    hỏi mà khác nhau; dòng cố định lại NGẮN đường hơn nên BFS chọn nó trước ⇒ mọi phép đổi tờ↔cân
    (tồn kho, tiền khoán cắt giấy theo tấn) đều sai mà không báo gì.

    Chỉ xoá cặp TĨNH ngang loại đo (`ho` khác nhau) có một đầu là `to`; cặp cùng loại đo
    ("1 tấn = 1.000 kg") và cặp động đều giữ nguyên. Idempotent: DB sạch thì không xoá gì.
    """
    insp = inspect(db.get_bind())
    if not {"don_vi_quy_doi", "don_vi_do"} <= set(insp.get_table_names()):
        return
    db.execute(text("""
        DELETE FROM don_vi_quy_doi
        WHERE (cong_thuc IS NULL OR cong_thuc = '')
          AND id IN (
            SELECT q.id FROM don_vi_quy_doi q
            JOIN don_vi_do a ON a.id = q.tu_id
            JOIN don_vi_do b ON b.id = q.den_id
            WHERE a.ho <> b.ho AND (a.ma = 'to' OR b.ma = 'to')
          )
    """))
    db.commit()


MIGRATIONS.append(
    ("0169_xoa_cap_quy_doi_ngang_loai_do", _migrate_xoa_cap_quy_doi_ngang_loai_do)
)


def _migrate_mat_hang_don_vi_goc(db: Session) -> None:
    """Đơn vị của Giấy / Vật tư khác lấy từ danh mục `don_vi_do` thay vì danh sách cứng trong FE.

    Ba việc:
    1. `vat_tu_in_an` thêm `don_vi_dong_goi` + `he_so_dong_goi` — quy cách đóng gói RIÊNG của từng
       món ("1 thùng = 3 kg"). Không khai vào bảng cặp chung được vì thùng keo ≠ thùng mực.
    2. Nới `giay_nguyen.don_vi_gia` lên 24 ký tự cho khớp `don_vi_do.ma`.
    3. Mã đơn vị không có trong `don_vi_do` thì XOÁ TRẮNG (dev đang có `ban` ở vật tư). Chủ chốt:
       không map cứng sang đơn vị gần giống — máy đoán sai một lần là sai vĩnh viễn; để trống thì
       màn danh mục hiện "Chưa chọn đơn vị" và người khai tự chọn đúng.
    """
    insp = inspect(db.get_bind())
    ten_bang = set(insp.get_table_names())
    if "vat_tu_in_an" in ten_bang:
        cols = _existing_columns(insp, "vat_tu_in_an")
        if "don_vi_dong_goi" not in cols:
            db.execute(text("ALTER TABLE vat_tu_in_an ADD COLUMN don_vi_dong_goi VARCHAR(24)"))
        if "he_so_dong_goi" not in cols:
            db.execute(text("ALTER TABLE vat_tu_in_an ADD COLUMN he_so_dong_goi NUMERIC(18,6)"))
        db.commit()

    # Nới kiểu + BỎ NOT NULL/DEFAULT: "chưa chọn đơn vị" giờ là trạng thái THẬT, mà default cũ
    # ("kg"/"cai") lại lặng lẽ điền một đơn vị không ai chọn. SQLite không ALTER được kiểu cột;
    # dev/prod đều Postgres, còn DB test dựng bằng create_all nên đã đúng model mới.
    if db.get_bind().dialect.name == "postgresql":
        for bang in ("giay_nguyen", "vat_tu_in_an"):
            if bang not in ten_bang:
                continue
            db.execute(text(f"ALTER TABLE {bang} ALTER COLUMN don_vi_gia TYPE VARCHAR(24)"))
            db.execute(text(f"ALTER TABLE {bang} ALTER COLUMN don_vi_gia DROP NOT NULL"))
            db.execute(text(f"ALTER TABLE {bang} ALTER COLUMN don_vi_gia DROP DEFAULT"))
        db.commit()

    if "don_vi_do" not in ten_bang:
        return
    for bang in ("giay_nguyen", "vat_tu_in_an"):
        if bang not in ten_bang:
            continue
        db.execute(text(
            f"UPDATE {bang} SET don_vi_gia = NULL "
            f"WHERE don_vi_gia IS NOT NULL AND don_vi_gia <> '' "
            f"  AND lower(don_vi_gia) NOT IN (SELECT lower(ma) FROM don_vi_do)"
        ))
    db.commit()


MIGRATIONS.append(
    ("0170_mat_hang_don_vi_goc", _migrate_mat_hang_don_vi_goc)
)


# Bốn bảng kho đổi khoá mặt hàng: `material_id` (→ `materials`) thành cặp `(hang_loai, hang_id)`
# trỏ thẳng danh mục gốc `giay_nguyen` / `vat_tu_in_an`.
_KHO_BANG_HANG = ("stock_lots", "stock_request_lines", "stock_voucher_lines", "stock_thresholds")

# Thứ tự xoá tôn trọng FK: attachment → dòng phiếu → lô → phiếu → dòng đề nghị → đề nghị → ngưỡng.
# DELETE chứ không TRUNCATE để chạy được cả trên SQLite (test / máy dev không Postgres).
_KHO_XOA_THEO_THU_TU = (
    "stock_voucher_attachments", "stock_voucher_lines", "stock_lots",
    "stock_vouchers", "stock_request_lines", "stock_requests", "stock_thresholds",
)


def _co_phep(bien: str) -> bool:
    """Cờ xác nhận của NGƯỜI VẬN HÀNH, đọc từ env. Mặc định TẮT — không có cờ thì migration dừng."""
    return (os.getenv(bien) or "").strip().lower() in ("1", "true", "yes")


def _migrate_kho_doi_goc_mat_hang(db: Session) -> None:
    """Kho thôi giữ sổ hàng riêng — trỏ thẳng vào danh mục Giấy / Vật tư khác.

    Vì sao đổi được thẳng, không cần backfill: cả bốn bảng kho đang TRỐNG (đo trên DB dev
    2026-08-08: stock_lots/stock_vouchers/stock_requests/… đều 0 dòng). Kho chưa từng nhập hàng
    thật, nên không có link nào để giữ.

    ⚠️ Đây là migration PHÁ HUỶ (drop cột). Nếu môi trường nào ĐÃ có dữ liệu kho thì `material_id`
    là thứ duy nhất nối lô với mặt hàng — drop đi là mất vĩnh viễn, mà mất im lặng thì tới lúc phát
    hiện đã không lần lại được. Nên gặp dữ liệu là DỪNG HẲN (raise): app không khởi động còn hơn
    khởi động với sổ kho đứt gốc. Người vận hành sẽ phải viết backfill map `materials` → danh mục
    gốc rồi mới chạy tiếp.
    """
    insp = inspect(db.get_bind())
    ten_bang = set(insp.get_table_names())
    co = [t for t in _KHO_BANG_HANG if t in ten_bang]
    if not co:
        return
    # Đã đổi rồi (DB mới dựng bằng create_all) → không làm gì.
    if all("hang_loai" in _existing_columns(insp, t) for t in co):
        return

    con_du_lieu = {t: db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() or 0 for t in co}
    if any(con_du_lieu.values()):
        # ĐƯỜNG THOÁT TƯỜNG MINH (2026-08-09): trước đó guard chỉ raise, nên môi trường nào có dữ
        # liệu kho là app không khởi động được và người vận hành phải vào psql gõ tay — staging đã
        # crash-loop 21 giờ đúng vì thế. Nay ai đã backup và chấp nhận mất sổ kho thử nghiệm thì
        # đặt cờ, migration tự dọn rồi đi tiếp.
        #
        # Cố ý KHÔNG làm cờ "bỏ qua migration": bỏ qua để schema đứng lại ở giữa (cột
        # `material_id` còn nguyên trong khi model đã đổi sang cặp khoá) còn tệ hơn dừng hẳn.
        if _co_phep("MIGRATION_0171_XOA_DU_LIEU_KHO"):
            for t in _KHO_XOA_THEO_THU_TU:
                if t in ten_bang:
                    db.execute(text(f"DELETE FROM {t}"))
            db.commit()
        else:
            raise RuntimeError(
                "Migration 0171 DỪNG: bảng kho đang có dữ liệu "
                f"({', '.join(f'{t}={n}' for t, n in con_du_lieu.items() if n)}). "
                "Đổi gốc mặt hàng sẽ drop `material_id`. Hai cách đi tiếp: "
                "(1) backfill sang (hang_loai, hang_id) rồi chạy lại; hoặc "
                "(2) nếu đây là dữ liệu THỬ NGHIỆM — backup trước (`pg_dump -t 'stock_*'`), rồi "
                "đặt MIGRATION_0171_XOA_DU_LIEU_KHO=true để migration tự dọn bảy bảng kho và đổi "
                "khoá. ⚠️ BỎ cờ đó khỏi .env ngay sau khi lên được, kẻo lần deploy sau có dữ liệu "
                "thật lại bị xoá âm thầm."
            )

    la_pg = db.get_bind().dialect.name == "postgresql"
    for t in co:
        cols = _existing_columns(insp, t)
        if "hang_loai" not in cols:
            db.execute(text(f"ALTER TABLE {t} ADD COLUMN hang_loai VARCHAR(8)"))
        if "hang_id" not in cols:
            db.execute(text(f"ALTER TABLE {t} ADD COLUMN hang_id INTEGER"))
        db.commit()
        # Bảng rỗng nên SET NOT NULL chạy được ngay, khỏi cần giá trị mặc định giả.
        if la_pg:
            db.execute(text(f"ALTER TABLE {t} ALTER COLUMN hang_loai SET NOT NULL"))
            db.execute(text(f"ALTER TABLE {t} ALTER COLUMN hang_id SET NOT NULL"))
        for cu in ("material_id",):
            if cu in cols:
                db.execute(text(f"ALTER TABLE {t} DROP COLUMN {cu}"))
        db.commit()

    # Dòng đề nghị: bỏ hàng gõ tay + quy đổi khai tay từng dòng (nay lấy từ đồ thị đơn vị chung).
    if "stock_request_lines" in co:
        cols = _existing_columns(insp, "stock_request_lines")
        for cu in ("ten_tu_do", "don_vi_phu", "he_so_quy_doi"):
            if cu in cols:
                db.execute(text(f"ALTER TABLE stock_request_lines DROP COLUMN {cu}"))
        if la_pg:
            db.execute(text("ALTER TABLE stock_request_lines ALTER COLUMN dvt TYPE VARCHAR(24)"))
        db.commit()

    # Dòng phiếu: thêm số đã quy về đơn vị gốc (chốt hệ số lúc lập phiếu, xem model).
    if "stock_voucher_lines" in co and "sl_goc" not in _existing_columns(insp, "stock_voucher_lines"):
        db.execute(text("ALTER TABLE stock_voucher_lines ADD COLUMN sl_goc NUMERIC(14,4)"))
        db.commit()
        if la_pg:
            db.execute(text("ALTER TABLE stock_voucher_lines ALTER COLUMN sl_goc SET NOT NULL"))
            db.commit()

    # Ngưỡng tồn: khoá duy nhất theo (mặt hàng × kho) — đổi theo cặp khoá mới.
    if "stock_thresholds" in co and la_pg:
        db.execute(text(
            "ALTER TABLE stock_thresholds DROP CONSTRAINT IF EXISTS uq_stock_thresholds_material_kho"))
        db.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_thresholds_hang_kho "
            "ON stock_thresholds (hang_loai, hang_id, kho_id)"))
        db.commit()

    if "stock_lots" in co:
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_stock_lots_hang ON stock_lots (hang_loai, hang_id)"))
        db.commit()


MIGRATIONS.append(
    ("0171_kho_doi_goc_mat_hang", _migrate_kho_doi_goc_mat_hang)
)


def _migrate_ncc_tro_ve_mat_hang_goc(db: Session) -> None:
    """`supplier_items` gắn được vào MẶT HÀNG GỐC — nền cho bảng so giá giữa các NCC.

    NULLABLE, không backfill: NCC vẫn bán được thứ ngoài danh mục vật tư (dịch vụ, gia công), và
    ghép ngược từ `item_name` bằng chuỗi chính là cái sai ta đang đi chữa — đoán sai một dòng là
    so giá ra kết quả sai mà không ai biết. Người dùng gắn tay từng dòng ở màn NCC.
    """
    insp = inspect(db.get_bind())
    if "supplier_items" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "supplier_items")
    if "hang_loai" not in cols:
        db.execute(text("ALTER TABLE supplier_items ADD COLUMN hang_loai VARCHAR(8)"))
    if "hang_id" not in cols:
        db.execute(text("ALTER TABLE supplier_items ADD COLUMN hang_id INTEGER"))
    db.commit()
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_supplier_items_hang ON supplier_items (hang_loai, hang_id)"))
    db.commit()


MIGRATIONS.append(
    ("0172_ncc_tro_ve_mat_hang_goc", _migrate_ncc_tro_ve_mat_hang_goc)
)


# Bảng của cụm tính giá đời cũ — DROP theo đúng thứ tự FK (con trước, cha sau).
_BANG_TINH_GIA_CU = (
    "estimate_cost_lines",
    "estimate_options",
    "estimates",
    "costing_operations",
    "costing_paper_options",
    "costings",
    "product_components",
    "products",
    "material_costs",
    "materials",
)


def _migrate_don_cum_tinh_gia_doi_cu(db: Session) -> None:
    """Đợt 5 — dọn hẳn cụm tính giá đời CŨ (`estimates`/`costings`/`products`/`materials`).

    Vì sao xoá được: engine đang chạy là `phieu_tinh_gia`/`thanh_phan_engine`, còn cụm này đã
    CHẾT trên UI từ lâu (không màn nào gọi /api/estimates · /api/costings · /api/materials), và
    Kho đã rời `materials` ở Đợt 3 nên 4 FK giữ nó lại đã biến mất.

    Phần ĐỘNG VÀO DỮ LIỆU THẬT (chủ đã chốt): báo giá đi đường Estimate cũ không còn nguồn giá
    vốn nên xoá hẳn, kèm đơn hàng bán ghim vào chúng.
      - `orders.quotation_id` là soft-ref (KHÔNG FK) nên xoá báo giá mà bỏ quên đơn thì đơn trỏ
        vào khoảng không, im lặng — phải xoá đơn TRƯỚC, tường minh.
      - Đơn đã đẻ LSX / đã có phiếu thu tiền / có đơn bổ sung con thì DỪNG HẲN (raise): đó là
        dữ liệu vận hành thật, không được xoá mù. Người vận hành xử tay rồi chạy lại.
    """
    insp = inspect(db.get_bind())
    ten_bang = set(insp.get_table_names())

    # --- 1. Dọn báo giá đường cũ + đơn hàng ghim vào chúng ---------------------
    if "quotes" in ten_bang and "estimate_id" in _existing_columns(insp, "quotes"):
        bg = "SELECT id FROM quotes WHERE estimate_id IS NOT NULL"
        dh = f"SELECT id FROM orders WHERE quotation_id IN ({bg})" if "orders" in ten_bang else None

        if dh:
            # Chặn: đơn đã chạy tiếp xuống sản xuất / kế toán thì không tự xoá.
            vuong: list[str] = []
            for bang, cot, nhan in (
                ("lsx", "order_id", "lệnh sản xuất"),
                ("payment_receipts", "order_id", "phiếu thu"),
                ("orders", "parent_order_id", "đơn bổ sung"),
            ):
                if bang not in ten_bang:
                    continue
                n = db.execute(text(f"SELECT COUNT(*) FROM {bang} WHERE {cot} IN ({dh})")).scalar() or 0
                if n:
                    vuong.append(f"{nhan}={n}")
            if vuong:
                raise RuntimeError(
                    "Migration 0173 DỪNG: đơn hàng ghim vào báo giá đường Estimate cũ đang có "
                    f"{', '.join(vuong)}. Đây là dữ liệu vận hành thật — xử tay (huỷ/tách nguồn) "
                    "rồi chạy lại, đừng để migration xoá mù."
                )
            # order_lines / order_approvals / order_attachments đi theo FK ON DELETE CASCADE.
            db.execute(text(f"DELETE FROM orders WHERE id IN ({dh})"))

        # quote_versions → quote_items, cùng activity_logs/approvals/attachments: đều CASCADE.
        db.execute(text(f"DELETE FROM quotes WHERE id IN ({bg})"))
        db.commit()

    # --- 2. Gỡ 3 cột neo Estimate khỏi bộ bảng Báo giá (bảng vẫn sống) ---------
    for bang, cot in (
        ("quotes", "estimate_id"),
        ("quote_items", "estimate_id"),
        ("quote_items", "estimate_option_id"),
        ("quote_versions", "estimate_snapshot_json"),
    ):
        if bang in ten_bang and cot in _existing_columns(insp, bang):
            db.execute(text(f"ALTER TABLE {bang} DROP COLUMN {cot}"))
    db.commit()

    # --- 3. Loại sản phẩm: 4 cột vật tư mặc định trỏ `materials` (đã đo 0 dòng non-null) ---
    if "product_types_catalog" in ten_bang:
        cols = _existing_columns(insp, "product_types_catalog")
        for cot in (
            "default_paper_material_id",
            "default_cover_material_id",
            "default_body_material_id",
            "default_ink_material_id",
        ):
            if cot in cols:
                db.execute(text(f"ALTER TABLE product_types_catalog DROP COLUMN {cot}"))
        db.commit()

    # --- 4. DROP 10 bảng, con trước cha sau ------------------------------------
    for bang in _BANG_TINH_GIA_CU:
        if bang in ten_bang:
            db.execute(text(f"DROP TABLE {bang}"))
    db.commit()


MIGRATIONS.append(
    ("0173_don_cum_tinh_gia_doi_cu", _migrate_don_cum_tinh_gia_doi_cu)
)

def _migrate_de_nghi_kho_bo_buoc_duyet(db: Session) -> None:
    """Bỏ bước DUYỆT đề nghị kho (chủ 06/08/2026): tổ trưởng tạo đề nghị là **approved NGAY**, kho
    cấp liền — không còn "Chờ duyệt". `service.create` đã sửa cho đề nghị MỚI; đây là vá DỮ LIỆU cho
    đề nghị CŨ còn kẹt ở `draft`/`pending` trên DB đang chạy:

      * header: `draft`/`pending` → `approved`; người duyệt = người tạo; mốc duyệt = lúc tạo.
      * mọi DÒNG của chúng: `sl_duyet = sl_de_nghi` (duyệt nguyên số đã xin) — để kho ứng được đúng
        số, khớp ràng buộc "không ứng vượt sl_duyet".

    DATA migration THUẦN (chỉ UPDATE) — KHÔNG đổi schema, an toàn. Cập nhật DÒNG TRƯỚC header: sau khi
    header đổi khỏi draft/pending thì subquery lọc dòng sẽ rỗng. Guard theo bảng → idempotent, no-op
    trên DB `create_all` mới (chưa có đề nghị nào)."""
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    if not {"stock_requests", "stock_request_lines"} <= tables:
        return
    db.execute(text(
        "UPDATE stock_request_lines SET sl_duyet = sl_de_nghi "
        "WHERE request_id IN ("
        "  SELECT id FROM stock_requests WHERE trang_thai IN ('draft', 'pending'))"
    ))
    db.execute(text(
        "UPDATE stock_requests SET "
        "  trang_thai = 'approved', "
        "  nguoi_duyet_id = COALESCE(nguoi_duyet_id, nguoi_tao_id), "
        "  duyet_luc = COALESCE(duyet_luc, created_at) "
        "WHERE trang_thai IN ('draft', 'pending')"
    ))
    db.commit()


MIGRATIONS.append(("0168_de_nghi_kho_bo_buoc_duyet", _migrate_de_nghi_kho_bo_buoc_duyet))


def _migrate_company_bank_account_usage(db: Session) -> None:
    """Tài khoản ngân hàng công ty dùng chung cho tiền vào/ra.

    Tài khoản cũ mặc định bật cả hai để UNC/Phiếu thu đang có không bị mất lựa chọn.
    Sau đó kế toán có thể tắt bớt từng mục đích trên giao diện.
    """
    insp = inspect(db.get_bind())
    if "company_bank_accounts" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "company_bank_accounts")
    if "use_for_receipts" not in cols:
        db.execute(
            text(
                "ALTER TABLE company_bank_accounts "
                "ADD COLUMN use_for_receipts BOOLEAN NOT NULL DEFAULT TRUE"
            )
        )
    if "use_for_payments" not in cols:
        db.execute(
            text(
                "ALTER TABLE company_bank_accounts "
                "ADD COLUMN use_for_payments BOOLEAN NOT NULL DEFAULT TRUE"
            )
        )
    db.commit()


MIGRATIONS.append(("0174_company_bank_account_usage", _migrate_company_bank_account_usage))


def _migrate_bank_accounts_bo_mac_dinh(db: Session) -> None:
    """Bỏ khái niệm tài khoản ngân hàng mặc định.

    Kế toán tự chọn tài khoản khi lập Phiếu thu/UNC để tránh hệ thống tự điền nhầm tài khoản.
    Cột `is_default` giữ lại để tương thích schema cũ, nhưng dữ liệu mới không còn dùng.
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    for table in ("company_bank_accounts", "supplier_bank_accounts"):
        if table in tables and "is_default" in _existing_columns(insp, table):
            db.execute(text(f"UPDATE {table} SET is_default = FALSE WHERE is_default = TRUE"))
    db.commit()


MIGRATIONS.append(("0175_bank_accounts_bo_mac_dinh", _migrate_bank_accounts_bo_mac_dinh))


def _migrate_payment_vouchers_da_nguon_chi(db: Session) -> None:
    """Phiếu chi trở thành sổ chi chung: PMH chỉ là một nguồn chi.

    - Thêm `source_type` để phân biệt: purchase_request / internal_expense /
      customer_refund / other.
    - Nới `purchase_request_id` nullable để lập phiếu chi độc lập.
    """
    bind = db.get_bind()
    insp = inspect(bind)
    if "payment_vouchers" not in insp.get_table_names():
        return
    cols = {c["name"]: c for c in insp.get_columns("payment_vouchers")}
    dialect = bind.dialect.name
    if dialect == "postgresql":
        if "source_type" not in cols:
            db.execute(
                text(
                    "ALTER TABLE payment_vouchers "
                    "ADD COLUMN source_type VARCHAR(24) NOT NULL DEFAULT 'purchase_request'"
                )
            )
        if cols.get("purchase_request_id", {}).get("nullable") is False:
            db.execute(text("ALTER TABLE payment_vouchers ALTER COLUMN purchase_request_id DROP NOT NULL"))
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_payment_vouchers_source_type "
                "ON payment_vouchers (source_type)"
            )
        )
        db.commit()
        return

    if dialect != "sqlite":
        if "source_type" not in cols:
            db.execute(
                text(
                    "ALTER TABLE payment_vouchers "
                    "ADD COLUMN source_type VARCHAR(24) NOT NULL DEFAULT 'purchase_request'"
                )
            )
        db.commit()
        return

    info = list(db.execute(text("PRAGMA table_info(payment_vouchers)")).mappings())
    has_source = any(row["name"] == "source_type" for row in info)
    purchase_not_null = any(row["name"] == "purchase_request_id" and row["notnull"] for row in info)
    if has_source and not purchase_not_null:
        return

    new_columns = [
        "id INTEGER PRIMARY KEY",
        "code VARCHAR(32) NOT NULL",
        "doc_no VARCHAR(16)",
        "source_type VARCHAR(24) NOT NULL DEFAULT 'purchase_request'",
        "purchase_request_id INTEGER",
        "delivery_id INTEGER",
        "supplier_id INTEGER",
        "voucher_type VARCHAR(24) NOT NULL",
        "payment_stage VARCHAR(16) NOT NULL",
        "status VARCHAR(24) NOT NULL DEFAULT 'waiting_payment'",
        "voucher_date DATE NOT NULL",
        "planned_payment_date DATE",
        "amount BIGINT NOT NULL",
        "amount_vnd BIGINT NOT NULL",
        "currency VARCHAR(3) NOT NULL DEFAULT 'VND'",
        "exchange_rate NUMERIC(18, 6) NOT NULL DEFAULT 1",
        "content VARCHAR(500) NOT NULL",
        "invoice_number VARCHAR(64)",
        "invoice_date DATE",
        "contract_number VARCHAR(64)",
        "company_bank_account_id INTEGER",
        "supplier_bank_account_id INTEGER",
        "cash_recipient_name VARCHAR(255)",
        "cash_recipient_address VARCHAR(500)",
        "cash_recipient_identity VARCHAR(64)",
        "bank_fee_bearer VARCHAR(16)",
        "bank_reference VARCHAR(64)",
        "debit_account VARCHAR(64)",
        "credit_account VARCHAR(64)",
        "source_code_snapshot VARCHAR(32) NOT NULL",
        "supplier_name_snapshot VARCHAR(255) NOT NULL",
        "supplier_tax_code_snapshot VARCHAR(20)",
        "supplier_address_snapshot VARCHAR(500)",
        "company_account_holder_snapshot VARCHAR(255)",
        "company_account_number_snapshot VARCHAR(64)",
        "company_bank_name_snapshot VARCHAR(255)",
        "company_bank_branch_snapshot VARCHAR(255)",
        "beneficiary_account_holder_snapshot VARCHAR(255)",
        "beneficiary_account_number_snapshot VARCHAR(64)",
        "beneficiary_bank_name_snapshot VARCHAR(255)",
        "beneficiary_bank_branch_snapshot VARCHAR(255)",
        "created_by_user_id INTEGER",
        "paid_by_user_id INTEGER",
        "paid_at DATETIME",
        "cancelled_by_user_id INTEGER",
        "cancelled_at DATETIME",
        "cancel_reason TEXT",
        "note TEXT",
        "created_at DATETIME NOT NULL",
        "updated_at DATETIME NOT NULL",
    ]
    old_names = {row["name"] for row in info}
    target_names = [col.split(" ", 1)[0] for col in new_columns]
    select_exprs = []
    for name in target_names:
        if name in old_names:
            select_exprs.append(name)
        elif name == "source_type":
            select_exprs.append("'purchase_request'")
        else:
            select_exprs.append("NULL")
    db.execute(text("DROP TABLE IF EXISTS payment_vouchers_new"))
    db.execute(text(f"CREATE TABLE payment_vouchers_new ({', '.join(new_columns)})"))
    db.execute(
        text(
            "INSERT INTO payment_vouchers_new "
            f"({', '.join(target_names)}) SELECT {', '.join(select_exprs)} "
            "FROM payment_vouchers"
        )
    )
    db.execute(text("DROP TABLE payment_vouchers"))
    db.execute(text("ALTER TABLE payment_vouchers_new RENAME TO payment_vouchers"))
    for ddl in (
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_payment_vouchers_code ON payment_vouchers (code)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_payment_vouchers_doc_no ON payment_vouchers (doc_no)",
        "CREATE INDEX IF NOT EXISTS ix_payment_vouchers_source_type ON payment_vouchers (source_type)",
        "CREATE INDEX IF NOT EXISTS ix_payment_vouchers_purchase_request_id ON payment_vouchers (purchase_request_id)",
        "CREATE INDEX IF NOT EXISTS ix_payment_vouchers_delivery_id ON payment_vouchers (delivery_id)",
        "CREATE INDEX IF NOT EXISTS ix_payment_vouchers_supplier_id ON payment_vouchers (supplier_id)",
        "CREATE INDEX IF NOT EXISTS ix_payment_vouchers_voucher_type ON payment_vouchers (voucher_type)",
        "CREATE INDEX IF NOT EXISTS ix_payment_vouchers_status ON payment_vouchers (status)",
    ):
        db.execute(text(ddl))
    db.commit()


MIGRATIONS.append(("0176_payment_vouchers_da_nguon_chi", _migrate_payment_vouchers_da_nguon_chi))
def _migrate_dong_mua_tro_mat_hang_goc(db: Session) -> None:
    """Dòng YÊU CẦU mua + dòng PHIẾU mua gắn được vào MẶT HÀNG GỐC `(hang_loai, hang_id)`.

    Vì sao cần: bảng cân đối vật tư cộng "hàng đang về" theo mặt hàng. Ghép bằng `item_name` là
    ghép bằng chuỗi — thu mua gõ "Couche 150" còn danh mục ghi "Couché 150 79×109" là trượt, mà
    trượt thì IM LẶNG: kế hoạch tưởng chưa ai mua, đi đề nghị mua thêm một lô giấy nữa.

    NULLABLE, KHÔNG backfill (đúng lối mg 0172): dòng mua còn dùng cho thứ ngoài danh mục vật tư
    (dịch vụ, gia công, văn phòng phẩm), và đoán ngược từ tên là đúng cái sai đang đi chữa. Dòng
    không gắn mặt hàng thì bảng cân đối KHÔNG trừ — thà báo thiếu oan còn hơn báo đủ oan.
    """
    insp = inspect(db.get_bind())
    ten_bang = set(insp.get_table_names())
    for bang in ("department_purchase_request_lines", "purchase_request_lines"):
        if bang not in ten_bang:
            continue
        cols = _existing_columns(insp, bang)
        if "hang_loai" not in cols:
            db.execute(text(f"ALTER TABLE {bang} ADD COLUMN hang_loai VARCHAR(8)"))
        if "hang_id" not in cols:
            db.execute(text(f"ALTER TABLE {bang} ADD COLUMN hang_id INTEGER"))
        db.commit()
        db.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_{bang}_hang ON {bang} (hang_loai, hang_id)"))
        db.commit()


MIGRATIONS.append(
    ("0174_dong_mua_tro_mat_hang_goc", _migrate_dong_mua_tro_mat_hang_goc)
)


def _migrate_de_nghi_kho_gan_lenh(db: Session) -> None:
    """Dòng đề nghị kho khai được "xin cho LỆNH nào" — `lsx_id` / `bai_ghep_id`.

    Bảng cân đối cần biết phần đã cấp thuộc về lệnh nào để trừ vào ĐÚNG dòng nhu cầu. Không có
    khoá này thì kho cấp 2.000 tờ cho LSX-0126 mà kế hoạch không biết trừ vào đâu ⇒ mọi lệnh dùng
    cùng loại giấy đều hiện "còn thiếu" y như lúc chưa cấp.

    Soft ref (không FK) và NULLABLE: xin lặt vặt (băng dính, giẻ lau) không thuộc lệnh nào — bắt
    buộc gắn là chặn luôn luồng kho đang chạy.
    """
    insp = inspect(db.get_bind())
    if "stock_request_lines" not in insp.get_table_names():
        return
    cols = _existing_columns(insp, "stock_request_lines")
    for cot in ("lsx_id", "bai_ghep_id"):
        if cot not in cols:
            db.execute(text(f"ALTER TABLE stock_request_lines ADD COLUMN {cot} INTEGER"))
    db.commit()
    for cot in ("lsx_id", "bai_ghep_id"):
        db.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_stock_request_lines_{cot} "
            f"ON stock_request_lines ({cot})"))
    db.commit()


MIGRATIONS.append(
    ("0175_de_nghi_kho_gan_lenh", _migrate_de_nghi_kho_gan_lenh)
)


def _migrate_ncc_lead_time(db: Session) -> None:
    """`supplier_items.lead_time_days` — bao nhiêu ngày kể từ lúc đặt thì hàng về.

    Bảng cân đối suy "HẠN CHÓT PHẢI ĐẶT HÀNG" = ngày cần − lead time. Không có số này thì màn chỉ
    nói được "thiếu", không nói được "thiếu và hôm nay là hạn cuối để đặt" — mà đúng câu sau mới
    làm người ta bấm nút.

    DEFAULT 0 (= đặt hôm nay có hàng hôm nay) là mức KHÔNG BAO GIỜ báo trễ oan: NCC chưa khai thì
    hệ im lặng thay vì hù. Người dùng khai dần ở màn NCC.
    """
    insp = inspect(db.get_bind())
    if "supplier_items" not in insp.get_table_names():
        return
    if "lead_time_days" not in _existing_columns(insp, "supplier_items"):
        db.execute(text(
            "ALTER TABLE supplier_items ADD COLUMN lead_time_days INTEGER NOT NULL DEFAULT 0"))
    db.commit()


MIGRATIONS.append(("0176_ncc_lead_time", _migrate_ncc_lead_time))


def _migrate_khuon_dang_dat_lam(db: Session) -> None:
    """`khuon_be.ngay_ve_du_kien` — khuôn ĐANG ĐẶT LÀM thì bao giờ về.

    Tình trạng `dang_dat_lam` thêm vào hằng `TINH_TRANG` (models/khuon_be.py), không phải DDL —
    cột `tinh_trang` là VARCHAR tự do, chỉ service kiểm giá trị.

    Có ngày về thì bàn lịch trả lời được câu duy nhất đáng hỏi: "khuôn về KỊP giờ bế chưa?". Không
    có nó thì `dang_dat_lam` chỉ là một chữ, không chặn được lệnh xếp bế vào ngày mai.
    """
    insp = inspect(db.get_bind())
    if "khuon_be" not in insp.get_table_names():
        return
    if "ngay_ve_du_kien" not in _existing_columns(insp, "khuon_be"):
        db.execute(text("ALTER TABLE khuon_be ADD COLUMN ngay_ve_du_kien DATE"))
    db.commit()


MIGRATIONS.append(("0177_khuon_dang_dat_lam", _migrate_khuon_dang_dat_lam))


def _migrate_ca_rieng_may_to(db: Session) -> None:
    """Máy / tổ khai được TẬP CA RIÊNG (`ca_lam_ids` JSON list id `work_shifts`).

    Hôm nay chỉ có MỘT tập ca chung (mọi ca `work_shifts` đang hoạt động) áp cho mọi máy và mọi tổ,
    nên lịch của tổ chạy 1 ca bị vẽ dài y như máy chạy 2 ca — giờ xong sai, mà sai âm thầm.

    NULL / rỗng = DÙNG TẬP CA CHUNG như hiện nay ⇒ dữ liệu cũ KHÔNG đổi hành vi. Bám precedent
    `cong_doan.nhom_may_cho_phep` (cũng là JSON list, cũng NULL = không ràng buộc).

    Kiểu `JSON` chạy trên cả Postgres (json) lẫn SQLite (TEXT affinity).
    """
    insp = inspect(db.get_bind())
    ten_bang = set(insp.get_table_names())
    for bang in ("may_thiet_bi", "departments"):
        if bang not in ten_bang:
            continue
        if "ca_lam_ids" not in _existing_columns(insp, bang):
            db.execute(text(f"ALTER TABLE {bang} ADD COLUMN ca_lam_ids JSON"))
    db.commit()


MIGRATIONS.append(("0178_ca_rieng_may_to", _migrate_ca_rieng_may_to))


def _migrate_vung_khoa_kieu(db: Session) -> None:
    """`machine_unavailable_periods.kieu` — vùng CHẶN hay vùng MỞ THÊM.

    Khai được "làm bù cho cả nhà máy" (lịch xưởng), nhưng *"tối thứ Tư máy in 2 chạy thêm 3 tiếng"*
    thì không có chỗ. Thêm `mo_them` vào chính bảng vùng khóa thay vì đẻ bảng thứ hai: cùng một
    khái niệm "khoảng giờ riêng của MỘT máy", chỉ khác dấu — hai bảng là hai nơi phải nhớ khi vẽ
    Gantt và khi cộng giờ, mà quên một nơi thì lịch lệch không ai báo.

    DEFAULT `chan` ⇒ mọi khoảng đã khai từ trước giữ nguyên nghĩa.
    """
    insp = inspect(db.get_bind())
    if "machine_unavailable_periods" not in insp.get_table_names():
        return
    if "kieu" not in _existing_columns(insp, "machine_unavailable_periods"):
        db.execute(text(
            "ALTER TABLE machine_unavailable_periods "
            "ADD COLUMN kieu VARCHAR(8) NOT NULL DEFAULT 'chan'"))
    db.commit()


MIGRATIONS.append(("0179_vung_khoa_kieu", _migrate_vung_khoa_kieu))

def _migrate_ke_hoach_sx_duoc_de_nghi_mua(db: Session) -> None:
    """Vai **Kế hoạch SX** được bit `thu_mua.can_request` — nút "Đề nghị mua" trên bảng cân đối.

    Bảng cân đối vật tư (Đợt 1) có nút gộp các dòng thiếu thành MỘT yêu cầu mua bộ phận. Nút đó gác
    bằng `PurchaseService.can_create_department_request` → `thu_mua:request`. Vai Kế hoạch SX chưa
    có bit này, nên nút TỰ ẨN: người điều độ nhìn thấy lệnh sắp thiếu giấy mà không làm gì được
    ngay tại chỗ, phải đi nhờ người khác lập phiếu.

    Seed đã cấp (`seed.py`) nhưng seed chỉ áp cho DB TRẮNG — hệ đang chạy phải cấp bằng migration.

    Cấp theo BỘ PHẬN + TÊN VAI: khác `0163` (gỡ theo bộ phận) vì trong khối "Sản xuất" còn Tổ
    trưởng SX và Thợ SX — hai vai đó KHÔNG được đề nghị mua, cấp nhầm là mở cửa chi tiền cho cả
    xưởng. Vai đã có sẵn dòng `thu_mua` thì chỉ bật cờ, không đụng scope họ đang có.

    Chỉ `can_request` + đọc phiếu của mình: điều độ ĐỀ NGHỊ, còn đặt hàng và duyệt chi vẫn là việc
    bộ phận Mua hàng (giữ nguyên tách vai đã chốt 04/08/2026).
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    if not {"role_permissions", "roles", "departments"} <= tables:
        return
    cols = _existing_columns(insp, "role_permissions")
    if "can_request" not in cols:
        return

    vai = (
        "SELECT r.id FROM roles r JOIN departments d ON d.id = r.department_id "
        "WHERE d.name = 'Sản xuất' AND r.name = 'Kế hoạch SX'"
    )
    # Đã có dòng thu_mua → chỉ bật cờ, giữ nguyên scope người ta đang set.
    db.execute(text(
        f"UPDATE role_permissions SET can_request = TRUE "
        f"WHERE module_key = 'thu_mua' AND role_id IN ({vai})"
    ))
    # Chưa có dòng nào → thêm mới, scope `own` (chỉ thấy phiếu của chính mình).
    db.execute(text(
        f"INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
        f"can_delete, can_request, scope) "
        f"SELECT id, 'thu_mua', TRUE, FALSE, FALSE, FALSE, TRUE, 'own' FROM ({vai}) AS v "
        f"WHERE NOT EXISTS ("
        f"  SELECT 1 FROM role_permissions rp "
        f"  WHERE rp.role_id = v.id AND rp.module_key = 'thu_mua')"
    ))
    db.commit()


MIGRATIONS.append(("0180_ke_hoach_sx_de_nghi_mua", _migrate_ke_hoach_sx_duoc_de_nghi_mua))


def _migrate_department_la_kinh_doanh(db: Session) -> None:
    """`departments.la_kinh_doanh` — đánh dấu phòng thuộc khối KINH DOANH (cặp đôi với
    `la_san_xuat`, mg 0075), kế thừa xuống cây con y hệt.

    Dùng để trả lời "ai được giao phụ trách khách hàng": hộp chọn NV phụ trách ở màn Khách hàng
    đổ theo khối này thay vì đổ mọi tài khoản (trước đây Thủ kho / Quản lý kho đứng lẫn giữa Sale).

    KHÔNG backfill theo tên phòng: danh mục phòng ban là do người dùng khai, đoán chữ "Kinh doanh"
    là sai ngay khi ai đó đặt tên "Phòng Bán hàng". Để mặc định FALSE — chưa tick phòng nào thì
    router tự lùi về quy tắc "ai có quyền module khach_hang", nên DB đang chạy không đổi hành vi.

    No-op trên DB fresh (create_all đã dựng cột) / bảng chưa có / cột đã có.
    """
    insp = inspect(db.get_bind())
    if "departments" not in insp.get_table_names():
        return
    if "la_kinh_doanh" not in _existing_columns(insp, "departments"):
        db.execute(text(
            "ALTER TABLE departments ADD COLUMN la_kinh_doanh BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    db.commit()


MIGRATIONS.append(("0181_department_la_kinh_doanh", _migrate_department_la_kinh_doanh))


def _migrate_bu_cot_mua_hang_thieu(db) -> None:
    """Bù 9 cột của mảng MUA HÀNG chưa bao giờ được viết migration (06–08/08/2026).

    Vì sao lọt: `create_all` chỉ TẠO BẢNG, không ALTER. Bốn bảng dưới đã tồn tại từ trước,
    nên mọi cột thêm vào model sau đó KHÔNG tự vào DB đang chạy.

    Vì sao không cửa nào bắt được: test dùng SQLite `:memory:` dựng bằng `create_all`, job
    CI migration cũng chạy trên Postgres TRẮNG — DB trắng thì `create_all` sinh đủ cột nên
    cả hai đều xanh. Chỉ DB đã sống qua bản cũ mới vỡ, và đó chính là dev + prod.

    Triệu chứng: 500 `column purchase_requests.content does not exist` ở
    /api/ke-hoach-vat-tu/can-doi (bảng cân đối đọc phiếu mua để tính hàng đang về), và
    `column suppliers.credit_limit does not exist` ở mọi màn của phân hệ mua hàng.
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    can_bu = {
        "suppliers": [
            ("credit_limit", "BIGINT NOT NULL DEFAULT 0"),
            ("credit_days", "INTEGER"),
        ],
        "purchase_requests": [
            ("content", "TEXT"),
            ("reject_reason", "TEXT"),
            ("contract_number", "VARCHAR(64)"),
            ("deposit_expected", "BIGINT NOT NULL DEFAULT 0"),
        ],
        "department_purchase_requests": [
            ("content", "TEXT"),
            ("reject_reason", "TEXT"),
        ],
        # Soft ref có chủ ý (xem models/accounting.py) — KHÔNG thêm khoá ngoại ở đây.
        "payment_vouchers": [("delivery_id", "INTEGER")],
    }
    for bang, cot in can_bu.items():
        if bang not in tables:
            continue
        dang_co = _existing_columns(insp, bang)
        for ten, ddl in cot:
            if ten not in dang_co:
                db.execute(text(f"ALTER TABLE {bang} ADD COLUMN {ten} {ddl}"))

    # `content` gộp từ cặp `purpose` + `note` (chủ chốt 07/08/2026). Chứng từ cũ để trống thì
    # màn hiện ô nội dung RỖNG dù chữ vẫn nằm ở `purpose` — chép sang một lần.
    for bang in ("purchase_requests", "department_purchase_requests"):
        if bang in tables:
            db.execute(text(
                f"UPDATE {bang} SET content = purpose "
                f"WHERE content IS NULL AND purpose IS NOT NULL AND purpose <> ''"
            ))
    if "payment_vouchers" in tables:
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_payment_vouchers_delivery_id "
            "ON payment_vouchers (delivery_id)"
        ))
    db.commit()


MIGRATIONS.append(("0181_bu_cot_mua_hang_thieu", _migrate_bu_cot_mua_hang_thieu))


def _migrate_cho_ky_thuat_theo_may_va_dau_viec(db) -> None:
    """CHỜ KỸ THUẬT chuyển từ (công đoạn × loại sản phẩm) sang MÁY + ĐẦU VIỆC (chủ chốt 10/08/2026).

    Vì sao đổi khoá:
    · Vế MÁY — bốn máy CM-01…CM-04 cùng công đoạn "Cán màng / UV", nhưng hai máy UV khô dưới đèn
      (≈0 giờ) còn hai máy cán màng phải để nguội vài giờ. Khoá theo công đoạn là chắc chắn sai một
      trong hai vế, im lặng.
    · Vế TỔ — cùng công đoạn "Bắt tay + vào keo", đầu việc *vào keo gáy vuông* chờ keo đông còn
      *khâu chỉ* không chờ. Cũng không tách được nếu khoá theo công đoạn.

    Hai vế KHÔNG chồng nhau: một bước hoặc Máy hoặc Tổ.

    Đơn vị GIỜ (người khai nghĩ "mực khô 4 tiếng"), đổi sang phút đúng một chỗ ở
    `LsxService._cho_ky_thuat_phut`.

    ⚠️ KHÔNG chép dữ liệu từ `cong_doan_cho_ky_thuat`: bảng đó RỖNG (0 dòng lúc đổi) nên không có
    gì để mất, và chép ngược từ khoá công đoạn sang khoá máy là ĐOÁN — đúng cái sai vừa bỏ. Bảng cũ
    để nằm im (dự án không có Alembic, không drop).
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    for bang in ("may_thiet_bi", "cong_doan_dau_viec"):
        if bang not in tables:
            continue
        if "cho_ky_thuat_gio" not in _existing_columns(insp, bang):
            db.execute(text(
                f"ALTER TABLE {bang} ADD COLUMN cho_ky_thuat_gio NUMERIC(6,2) NOT NULL DEFAULT 0"
            ))
    db.commit()


MIGRATIONS.append(("0182_cho_ky_thuat_theo_may_va_dau_viec", _migrate_cho_ky_thuat_theo_may_va_dau_viec))


def _migrate_danh_muc_giay_quyen_rieng(db: Session) -> None:
    """Danh mục Giấy · Chủng loại giấy · Vật tư khác tách khỏi quyền `kho` → `dm_giay_vat_tu`.

    Ba màn đó vốn gác bằng module `kho`, nên ma trận phân quyền hiện nhóm Danh mục có 5 dòng
    trong khi menu Cấu hình danh mục có 10 mục: người cấp quyền bật đủ 5/5 rồi vẫn thấy người
    kia không mở được màn Giấy. Nay mỗi màn danh mục có quyền riêng của nó.

    Migration CHỈ CẤP, KHÔNG THU: mọi vai đang có quyền `kho` được copy y nguyên 4 bit sang
    `dm_giay_vat_tu` (thủ kho · quản lý kho · kế toán kho · GĐ…) — không có bước này thì sáng
    hôm sau họ mở app là mất màn Giấy. Ai muốn siết "thủ kho không đặt đơn giá giấy" thì tắt
    công tắc Thao tác trên ma trận, không phải sửa code.

    `scope` = 'all': danh mục là dữ liệu dùng chung, UI đã bỏ cột Phạm vi ở nhóm này
    (`SCOPELESS_MODULES` trong role_service ép 'all' khi lưu).

    Vai đã có sẵn dòng `dm_giay_vat_tu` (Giám đốc) thì KHÔNG đụng — họ đang full quyền, ghi đè
    chỉ có nước làm hẹp đi.
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    if not {"role_permissions", "modules"} <= tables:
        return

    # Bảo đảm module tồn tại trong danh mục module (DB cũ có thể thiếu / sai nhãn).
    # `created_at` NOT NULL và default nằm ở PYTHON (`default=_utcnow`), không phải server_default
    # → INSERT thô phải tự đặt, nếu không SQLite/Postgres đều chặn.
    db.execute(text(
        "INSERT INTO modules (key, label, created_at) "
        "SELECT 'dm_giay_vat_tu', 'Giấy & Vật tư', CURRENT_TIMESTAMP "
        "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = 'dm_giay_vat_tu')"
    ))
    db.execute(text(
        "UPDATE modules SET label = 'Giấy & Vật tư' WHERE key = 'dm_giay_vat_tu'"
    ))

    db.execute(text(
        "INSERT INTO role_permissions "
        "(role_id, module_key, can_read, can_create, can_update, can_delete, scope) "
        "SELECT k.role_id, 'dm_giay_vat_tu', k.can_read, k.can_create, k.can_update, "
        "       k.can_delete, 'all' "
        "FROM role_permissions k "
        "WHERE k.module_key = 'kho' AND k.can_read = TRUE "
        "  AND NOT EXISTS ("
        "    SELECT 1 FROM role_permissions rp "
        "    WHERE rp.role_id = k.role_id AND rp.module_key = 'dm_giay_vat_tu')"
    ))

    # Danh mục không có phạm vi own/department — chuẩn hoá các dòng cũ về 'all'.
    db.execute(text(
        "UPDATE role_permissions SET scope = 'all' WHERE module_key IN "
        "('dm_loai_san_pham', 'dm_giay_vat_tu', 'dm_thiet_bi', 'dm_cong_doan', 'khuon_be')"
    ))
    db.commit()


MIGRATIONS.append(("0183_danh_muc_giay_quyen_rieng", _migrate_danh_muc_giay_quyen_rieng))


# Danh mục MỚI tách ra → module NGUỒN để copy quyền sang. Ai đang làm được gì thì sau deploy vẫn
# làm được y thế; siết lại là việc của người quản trị trên ma trận, không phải của migration.
_DM_TACH: tuple[tuple[str, str, str], ...] = (
    # (module mới, nhãn, module nguồn để thừa hưởng quyền)
    ("dm_bu_hao", "Bù hao", "dm_cong_doan"),
    ("dm_don_vi", "Đơn vị & quy đổi", "dm_cong_doan"),
    ("dm_chung_loai_giay", "Chủng loại giấy", "dm_giay_vat_tu"),
    ("dm_giay", "Giấy", "dm_giay_vat_tu"),
    ("dm_vat_tu", "Vật tư khác", "dm_giay_vat_tu"),
    ("dm_kho_hang", "Khai báo kho", "kho"),
)


def _migrate_moi_man_danh_muc_mot_quyen(db: Session) -> None:
    """Mỗi màn trong "Cấu hình danh mục" có quyền RIÊNG — 10 mục menu = 10 dòng ma trận.

    Trước đây menu 10 mục mà ma trận chỉ 5 dòng: Bù hao và Đơn vị & quy đổi đi ké `dm_cong_doan`,
    ba màn giấy/vật tư mượn `kho` (mg 0183 mới gom tạm về `dm_giay_vat_tu`), Khai báo kho cũng
    dùng `kho`. Hệ quả: muốn cho kế toán khai "1 thùng = 24 hộp" là phải mở luôn danh mục công
    đoạn cho họ; bật đủ 5/5 nhóm Danh mục vẫn không thấy màn Giấy.

    Migration CHỈ CẤP, KHÔNG THU — mỗi module mới thừa hưởng nguyên 4 bit CRUD của module nguồn
    (`_DM_TACH`). `dm_giay_vat_tu` chỉ tồn tại giữa 0183 và 0184 nên sau khi rải quyền xong thì
    gỡ hẳn khỏi bảng `modules` + `role_permissions`, không để lại dòng ma trong ma trận.

    `scope` = 'all': danh mục là dữ liệu dùng chung, UI đã bỏ cột Phạm vi ở nhóm này.
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    if not {"role_permissions", "modules"} <= tables:
        return

    for key, label, _nguon in _DM_TACH:
        # created_at NOT NULL, default nằm ở Python → INSERT thô phải tự đặt.
        db.execute(text(
            "INSERT INTO modules (key, label, created_at) "
            "SELECT :k, :l, CURRENT_TIMESTAMP "
            "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"
        ), {"k": key, "l": label})
        db.execute(text("UPDATE modules SET label = :l WHERE key = :k"), {"k": key, "l": label})

    for key, _label, nguon in _DM_TACH:
        db.execute(text(
            "INSERT INTO role_permissions "
            "(role_id, module_key, can_read, can_create, can_update, can_delete, scope) "
            "SELECT s.role_id, :k, s.can_read, s.can_create, s.can_update, s.can_delete, 'all' "
            "FROM role_permissions s "
            "WHERE s.module_key = :nguon AND s.can_read = TRUE "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM role_permissions rp "
            "    WHERE rp.role_id = s.role_id AND rp.module_key = :k)"
        ), {"k": key, "nguon": nguon})

    # Nhãn cũ "Công đoạn gia công" → "Công đoạn": giờ nó chỉ còn gác đúng màn Công đoạn.
    db.execute(text("UPDATE modules SET label = 'Công đoạn' WHERE key = 'dm_cong_doan'"))

    # Gỡ module trung gian `dm_giay_vat_tu` (quyền đã rải sang 3 module con ở trên).
    db.execute(text("DELETE FROM role_permissions WHERE module_key = 'dm_giay_vat_tu'"))
    db.execute(text("DELETE FROM modules WHERE key = 'dm_giay_vat_tu'"))

    db.execute(text(
        "UPDATE role_permissions SET scope = 'all' WHERE module_key IN "
        "('dm_loai_san_pham', 'dm_thiet_bi', 'dm_cong_doan', 'dm_bu_hao', 'dm_don_vi', "
        " 'dm_chung_loai_giay', 'dm_giay', 'dm_vat_tu', 'khuon_be', 'dm_kho_hang')"
    ))
    db.commit()


MIGRATIONS.append(("0184_moi_man_danh_muc_mot_quyen", _migrate_moi_man_danh_muc_mot_quyen))


def _migrate_khuon_theo_buoc(db: Session) -> None:
    """Khuôn gán vào BƯỚC (`lsx_cong_doan.khuon_be_id`), không còn gán vào cả lệnh.

    Ô "Khuôn bế" ở màn Kế hoạch (cấp lệnh) đã bỏ 11/08/2026. Một lệnh có thể cần NHIỀU khuôn —
    hộp giấy vừa Bế (khuôn bế) vừa Ép nhũ (khuôn ép) — nên một ô cho cả lệnh là sai từ mô hình:
    giữ được một cái, cái kia không ai biết lấy khuôn nào, và bảng cân đối chỉ canh được một mốc
    thời gian trong khi hai bước chạy hai ngày khác nhau.

    CHUYỂN dữ liệu cũ, không vứt: `lsx.khuon_be_id` chép xuống bước ĐẦU TIÊN của lệnh đó có công
    đoạn bật `requires_tooling` với `tooling_type` là khuôn lưu kho (khuon_be · khuon_ep). `kem`
    KHÔNG tính — kẽm là vật tư tiêu hao, mỗi bài phơi mới, không có dòng nào trong kho khuôn.

    Cột `lsx.khuon_be_id` GIỮ NGUYÊN (dự án không có Alembic, không drop cột) nhưng thôi được đọc.
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    if "lsx_cong_doan" not in tables:
        return
    if "khuon_be_id" not in _existing_columns(insp, "lsx_cong_doan"):
        db.execute(text("ALTER TABLE lsx_cong_doan ADD COLUMN khuon_be_id INTEGER"))
        db.commit()

    if not {"lsx", "cong_doan"} <= tables:
        return
    if "khuon_be_id" not in _existing_columns(insp, "lsx"):
        return

    # Bước ĐẦU TIÊN (thu_tu nhỏ nhất) của mỗi lệnh mà công đoạn nguồn cần khuôn lưu kho.
    db.execute(text(
        "UPDATE lsx_cong_doan SET khuon_be_id = ("
        "  SELECT l.khuon_be_id FROM lsx l WHERE l.id = lsx_cong_doan.lsx_id"
        ") "
        "WHERE khuon_be_id IS NULL "
        "  AND id IN ("
        "    SELECT MIN(cd.id) FROM lsx_cong_doan cd "
        "    JOIN cong_doan c ON c.id = cd.cong_doan_id "
        "    JOIN lsx l2 ON l2.id = cd.lsx_id "
        "    WHERE c.requires_tooling = TRUE "
        "      AND c.tooling_type IN ('khuon_be', 'khuon_ep') "
        "      AND l2.khuon_be_id IS NOT NULL "
        "    GROUP BY cd.lsx_id"
        "  )"
    ))
    db.commit()


MIGRATIONS.append(("0185_khuon_theo_buoc", _migrate_khuon_theo_buoc))


def _migrate_kho_bao_cao_ke_toan(db: Session) -> None:
    """Báo cáo kho (kế toán) — docs/spec-bao-cao-kho.md:
      * `stock_requests.loai_kho` (INTEGER nullable) — mã loại nhập/xuất MISA người tạo gõ ở yêu cầu.
      * `role_permissions.can_close_book` (BOOLEAN default FALSE) — quyền xem Báo cáo kho + export
        Excel MISA + khóa kỳ (chốt sổ); cấp cho vai 'Kế toán kho' + 'Giám đốc'.
    Bảng `kho_khoa_so` do create_all dựng (không cần ở đây). No-op trên DB fresh / cột đã có."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "stock_requests" in tables and "loai_kho" not in _existing_columns(insp, "stock_requests"):
        db.execute(text("ALTER TABLE stock_requests ADD COLUMN loai_kho INTEGER"))
    if "role_permissions" in tables:
        if "can_close_book" not in _existing_columns(insp, "role_permissions"):
            db.execute(text(
                "ALTER TABLE role_permissions ADD COLUMN can_close_book BOOLEAN NOT NULL DEFAULT FALSE"
            ))
        if "roles" in tables:
            db.execute(text(
                "UPDATE role_permissions SET can_close_book = TRUE "
                "WHERE module_key = 'kho' AND role_id IN "
                "(SELECT id FROM roles WHERE name IN ('Kế toán kho', 'Giám đốc'))"
            ))
    db.commit()


MIGRATIONS.append(("0169_kho_bao_cao_ke_toan", _migrate_kho_bao_cao_ke_toan))


def _migrate_kho_bao_cao_v2(db: Session) -> None:
    """Vòng 2 Báo cáo kho (docs/spec-bao-cao-kho.md):
      * `stock_requests.loai_kho`: INT → VARCHAR(50) — người dùng gõ TÊN loại tự do (không phải mã).
      * `kho_khoa_so`: khóa 1 NGÀY (`ngay_khoa`) → khóa KHOẢNG `[tu_ngay, den_ngay]` + `hanh_dong`
        ('khoa'/'mo') = append-only (hiệu lực + lịch sử). Dữ liệu cũ không đáng kể → dựng lại bảng.
    Idempotent + no-op trên DB fresh (create_all đã ra schema mới)."""
    bind = db.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    insp = inspect(bind)
    tables = insp.get_table_names()

    # 1) loai_kho INT → VARCHAR(50).
    if "stock_requests" in tables and "loai_kho" in _existing_columns(insp, "stock_requests"):
        col = next((c for c in insp.get_columns("stock_requests") if c["name"] == "loai_kho"), None)
        type_str = str(col["type"]).upper() if col else ""
        already_text = "CHAR" in type_str or "TEXT" in type_str
        if not already_text:
            if is_sqlite:
                # SQLite affinity INTEGER → dựng lại cột kiểu VARCHAR (dữ liệu loai_kho mới/không đáng kể).
                db.execute(text("ALTER TABLE stock_requests DROP COLUMN loai_kho"))
                db.execute(text("ALTER TABLE stock_requests ADD COLUMN loai_kho VARCHAR(50)"))
            else:
                db.execute(text(
                    "ALTER TABLE stock_requests ALTER COLUMN loai_kho TYPE VARCHAR(50) "
                    "USING loai_kho::varchar"
                ))
        db.commit()

    # 2) kho_khoa_so: dựng lại nếu còn cột cũ 'ngay_khoa'.
    if "kho_khoa_so" in tables and "ngay_khoa" in _existing_columns(insp, "kho_khoa_so"):
        db.execute(text("DROP TABLE kho_khoa_so"))
        id_pk = "INTEGER PRIMARY KEY" if is_sqlite else "SERIAL PRIMARY KEY"
        db.execute(text(
            "CREATE TABLE kho_khoa_so ("
            f"id {id_pk}, "
            "kho_id INTEGER REFERENCES kho_hang(id), "
            "tu_ngay DATE NOT NULL, "
            "den_ngay DATE NOT NULL, "
            "hanh_dong VARCHAR(8) NOT NULL DEFAULT 'khoa', "
            "nguoi_khoa_id INTEGER REFERENCES users(id), "
            "khoa_luc TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        ))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_kho_khoa_so_kho_id ON kho_khoa_so (kho_id)"))
        db.commit()


MIGRATIONS.append(("0170_kho_bao_cao_v2", _migrate_kho_bao_cao_v2))


def _migrate_tach_module_thu_mua(db) -> None:
    """Tách `thu_mua` thành 3 màn: Mua hàng · Nhà cung cấp · Yêu cầu mua hàng (chủ chốt 10/08/2026).

    ⚠️ ĐÂY LÀ MIGRATION QUYỀN — sai là người thật mất đường làm việc sáng hôm sau.

    Hai việc, theo đúng thứ tự:
    1. Thêm 2 khoá module mới vào bảng `modules` (khoá ngoại của `role_permissions` trỏ vào đây,
       thiếu là INSERT ở bước 2 vỡ).
    2. **SAO CHÉP** mọi hàng quyền `thu_mua` hiện có sang hai khoá mới, giữ NGUYÊN mọi cờ và phạm
       vi. Không sao chép thì mọi vai đang làm thu mua mất sạch quyền Nhà cung cấp + Yêu cầu mua
       hàng ngay khi bản này lên.

    Sau bước này quyền là BỘ THỪA (ai có thu mua thì có cả ba màn) — đúng ý đồ: không ai mất gì,
    còn muốn siết lại thì quản trị tự bỏ tick từng màn. Siết sẵn trong migration là đoán thay chủ.

    Idempotent: chạy lại không đẻ hàng trùng (`WHERE NOT EXISTS`).
    """
    # ⚠️ HAI điều bắt buộc ở dòng này, cả hai đều đã vỡ thật:
    #
    # 1. ĐỪNG dùng `PRAGMA table_info(...)`. Trên Postgres nó KHÔNG trả rỗng mà NÉM SyntaxError,
    #    nên nhánh dự phòng "if not cols" không bao giờ chạy tới — app chết ngay lúc khởi động
    #    (DB dev, 11/08/2026). Bộ test chạy SQLite nên PRAGMA luôn ngon và test vẫn xanh.
    # 2. Gọi TRƯỚC MỌI LỆNH GHI. `inspect()` mở connection riêng; test dùng SQLite StaticPool nên
    #    connection đó CHÍNH LÀ connection của phiên — đóng nó là ROLLBACK luôn mấy câu INSERT
    #    đang chờ. Đặt sau phần ghi thì mất sạch dữ liệu vừa thêm mà không báo lỗi gì.
    cols = sorted(_existing_columns(inspect(db.get_bind()), "role_permissions"))

    for key, label in (("nha_cung_cap", "Nhà cung cấp"),
                       ("yeu_cau_mua_hang", "Yêu cầu mua hàng")):
        # `modules.created_at` NOT NULL và KHÔNG có server_default ⇒ phải tự điền, không thì
        # INSERT vỡ. Đây là bẫy chung của mọi migration thêm dòng danh mục trong dự án này.
        db.execute(
            text("INSERT INTO modules (key, label, created_at) "
                 "SELECT :k, :l, CURRENT_TIMESTAMP "
                 "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"),
            {"k": key, "l": label},
        )
    # Nhãn của `thu_mua` đổi nghĩa: nay chỉ còn màn Mua hàng.
    db.execute(text("UPDATE modules SET label = 'Mua hàng' WHERE key = 'thu_mua'"))

    chep = [c for c in cols if c not in ("id", "module_key")]
    danh_sach = ", ".join(chep)
    for key in ("nha_cung_cap", "yeu_cau_mua_hang"):
        db.execute(
            text(
                f"INSERT INTO role_permissions (module_key, {danh_sach}) "
                f"SELECT :k, {danh_sach} FROM role_permissions rp "
                "WHERE rp.module_key = 'thu_mua' AND NOT EXISTS ("
                "  SELECT 1 FROM role_permissions x "
                "  WHERE x.role_id = rp.role_id AND x.module_key = :k)"
            ),
            {"k": key},
        )

    # BƯỚC 3 — cấp bù cho TRƯỞNG PHÒNG đang tại vị.
    # Trước bản này, hàm `can_create_department_request` cho trưởng phòng lập yêu cầu mua hàng bằng
    # QUYỀN NGẦM theo chức danh (`departments.head_user_id`), không có bản ghi quyền nào cả — nên
    # bước 2 ở trên không có gì để sao chép. Bỏ đường ngầm mà không cấp bù là sáng hôm sau mọi
    # trưởng phòng mất quyền đề nghị vật tư.
    # Cấp read+create+update, phạm vi `department` (đúng tầm một trưởng phòng). Từ nay quyền này
    # HIỆN trên ma trận: quản trị bỏ tick là gỡ được, chứ không dính cứng vào chức danh.
    # Mọi cột còn lại của `role_permissions` đều là Boolean NOT NULL **không có server_default**
    # (chỉ có default phía Python) ⇒ INSERT thẳng bằng SQL mà bỏ sót cột nào là vỡ NOT NULL.
    # Nên liệt kê ĐỦ: ba ô cần bật = true, tất cả các ô khác = false.
    bat = ("can_read", "can_create", "can_update")
    ten_cot = [c for c in cols if c not in ("id", "role_id", "module_key", "scope")]
    gan = ", ".join(ten_cot)
    gia_tri = ", ".join("true" if c in bat else "false" for c in ten_cot)
    db.execute(
        text(
            f"INSERT INTO role_permissions (role_id, module_key, scope, {gan}) "
            f"SELECT DISTINCT u.role_id, 'yeu_cau_mua_hang', 'department', {gia_tri} "
            "FROM departments d "
            "JOIN users u ON u.id = d.head_user_id "
            "WHERE u.role_id IS NOT NULL AND NOT EXISTS ("
            "  SELECT 1 FROM role_permissions x "
            "  WHERE x.role_id = u.role_id AND x.module_key = 'yeu_cau_mua_hang')"
        )
    )
    db.commit()


MIGRATIONS.append(("0177_tach_module_thu_mua", _migrate_tach_module_thu_mua))


# Màn nào tách ra khoá nào, và ô "lập/thao tác" của màn đó lấy giá trị từ ĐÂU của quyền `ke_toan` cũ.
# Khoá cũ dùng `can_approve` làm cờ vạn năng cho "lập phiếu chi / lập phiếu thu / gán chứng từ";
# khoá mới gọi đúng tên là `can_create` (hoặc `can_update` với màn Tài khoản ngân hàng).
_TACH_KE_TOAN = (
    # (khoá mới, cột đích, các cột nguồn — đúng MỘT cái true là đích thành true)
    ("phieu_chi", "can_create", ("can_create", "can_approve")),
    ("phieu_thu", "can_create", ("can_create", "can_approve")),
    ("cong_no_phai_tra", None, ()),
    ("cong_no_phai_thu", None, ()),
    ("tk_ngan_hang", "can_update", ("can_update", "can_approve")),
)


def _migrate_tach_module_ke_toan(db) -> None:
    """Tách `ke_toan` thành 6 màn (chủ chốt 10/08/2026). Cùng khuôn với 0177 của Thu mua.

    ⚠️ MIGRATION QUYỀN + CÓ ĐỔI NGHĨA ĐỘNG TỪ — chỗ dễ sai nhất của cả đợt.

    Trước: cả phân hệ treo trên một khoá. `can_read` mở 6 màn; `can_approve` là cờ vạn năng cho
    "lập phiếu chi", "lập phiếu thu", "gán chứng từ" — bật một ô là tiền ra được.

    Sau: mỗi màn một khoá, và động từ gọi đúng tên (LẬP phiếu = `can_create`). Vì đổi tên động từ
    nên KHÔNG được sao chép nguyên xi: kế toán ngoài đời đang lập phiếu bằng ô `can_approve`, chép
    thẳng sang là sáng hôm sau họ mở màn ra mà không bấm được nút nào. Bảng `_TACH_KE_TOAN` ở trên
    khai rõ đích lấy từ nguồn nào.

    Idempotent: chạy lại không đẻ hàng trùng.
    """
    # ⚠️ HAI điều bắt buộc ở dòng này, cả hai đều đã vỡ thật:
    #
    # 1. ĐỪNG dùng `PRAGMA table_info(...)`. Trên Postgres nó KHÔNG trả rỗng mà NÉM SyntaxError,
    #    nên nhánh dự phòng "if not cols" không bao giờ chạy tới — app chết ngay lúc khởi động
    #    (DB dev, 11/08/2026). Bộ test chạy SQLite nên PRAGMA luôn ngon và test vẫn xanh.
    # 2. Gọi TRƯỚC MỌI LỆNH GHI. `inspect()` mở connection riêng; test dùng SQLite StaticPool nên
    #    connection đó CHÍNH LÀ connection của phiên — đóng nó là ROLLBACK luôn mấy câu INSERT
    #    đang chờ. Đặt sau phần ghi thì mất sạch dữ liệu vừa thêm mà không báo lỗi gì.
    cols = sorted(_existing_columns(inspect(db.get_bind()), "role_permissions"))

    for key, label in (("phieu_chi", "Phiếu chi / UNC"),
                       ("phieu_thu", "Phiếu thu"),
                       ("cong_no_phai_tra", "Công nợ phải trả"),
                       ("cong_no_phai_thu", "Công nợ phải thu"),
                       ("tk_ngan_hang", "Tài khoản ngân hàng")):
        db.execute(
            text("INSERT INTO modules (key, label, created_at) "
                 "SELECT :k, :l, CURRENT_TIMESTAMP "
                 "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"),
            {"k": key, "l": label},
        )
    db.execute(text("UPDATE modules SET label = 'Đơn mua hàng (Kế toán)' WHERE key = 'ke_toan'"))


    for key, cot_dich, cot_nguon in _TACH_KE_TOAN:
        chep = [c for c in cols if c not in ("id", "module_key")]
        # Cột đích lấy từ phép HOẶC của các cột nguồn; các cột còn lại chép nguyên.
        chon = []
        for c in chep:
            if cot_dich and c == cot_dich:
                dieu_kien = " OR ".join(f"rp.{n}" for n in cot_nguon if n in cols)
                chon.append(f"CASE WHEN {dieu_kien} THEN true ELSE false END")
            else:
                chon.append(f"rp.{c}")
        db.execute(
            text(
                f"INSERT INTO role_permissions (module_key, {', '.join(chep)}) "
                f"SELECT :k, {', '.join(chon)} FROM role_permissions rp "
                "WHERE rp.module_key = 'ke_toan' AND NOT EXISTS ("
                "  SELECT 1 FROM role_permissions x "
                "  WHERE x.role_id = rp.role_id AND x.module_key = :k)"
            ),
            {"k": key},
        )
    db.commit()


MIGRATIONS.append(("0178_tach_module_ke_toan", _migrate_tach_module_ke_toan))


def _migrate_tach_module_nhan_su_luong(db) -> None:
    """Tách phân hệ Nhân sự & Lương (chủ chốt 10/08/2026). Lát cuối của đợt phân quyền.

    ⚠️ MIGRATION QUYỀN — NĂM việc, mỗi việc hỏng một kiểu khác nhau. Đọc hết trước khi sửa.

    1. **Thêm khoá `cham_cong`** rồi SAO CHÉP quyền `nhan_su` sang. Trước đây màn Chấm công dùng
       chung khoá với màn Hồ sơ nhân sự, nên cấp quyền xem hồ sơ là mở luôn bảng công cả công ty.

    2. **`can_lock` lấy từ `can_adjust` cũ.** Chốt kỳ / Mở lại kỳ trước đây gác bằng ô "chấm bù"
       (`adjust`); nay tách thành ô riêng vì một cú bấm đóng băng đầu vào lương TOÀN NHÀ MÁY và
       *Mở lại kỳ* thì xoá sạch số liệu chốt. Không ánh xạ thì người đang chốt kỳ mất quyền ngay.
       Ánh xạ xong, quản trị bỏ tick `can_lock` cho ai không cần — đó mới là điều muốn có.

    3. **Khoá `self_service` cấp cho MỌI vai.** Tự phục vụ (tự chấm công, xem phiếu lương của
       mình, tự gửi đơn nghỉ / tăng ca / tạm ứng) trước đây chỉ đòi ĐĂNG NHẬP — luật ngầm, không
       có ô nào để tắt. Nay là ô thật; cấp cho mọi vai để không ai mất việc hằng ngày, khác ở chỗ
       từ nay nó HIỆN trên ma trận và gỡ được.

    4. **`noi_quy` read cấp cho MỌI vai** — cùng lý do: nội quy thì ai cũng phải đọc thật, nhưng
       phải là một ô nhìn thấy được chứ không phải "ai đăng nhập cũng vào".

    5. **Lương THÔI mượn phạm vi của Nhân sự.** `payroll._scope_for` trước đây đọc
       `scope_for(user, "nhan_su")`: cấp quyền Lương mà quên cấp Nhân sự thì người đó tụt về *chỉ
       mình* — không ai đoán ra. Nay Lương đọc phạm vi của CHÍNH nó, nên phải chép phạm vi
       `nhan_su` sang `luong` để giữ nguyên hành vi hôm nay.

    Idempotent: chạy lại không đẻ hàng trùng, không ghi đè phạm vi đã chép.
    """
    # ⚠️ HAI điều bắt buộc ở dòng này, cả hai đều đã vỡ thật:
    #
    # 1. ĐỪNG dùng `PRAGMA table_info(...)`. Trên Postgres nó KHÔNG trả rỗng mà NÉM SyntaxError,
    #    nên nhánh dự phòng "if not cols" không bao giờ chạy tới — app chết ngay lúc khởi động
    #    (DB dev, 11/08/2026). Bộ test chạy SQLite nên PRAGMA luôn ngon và test vẫn xanh.
    # 2. Gọi TRƯỚC MỌI LỆNH GHI. `inspect()` mở connection riêng; test dùng SQLite StaticPool nên
    #    connection đó CHÍNH LÀ connection của phiên — đóng nó là ROLLBACK luôn mấy câu INSERT
    #    đang chờ. Đặt sau phần ghi thì mất sạch dữ liệu vừa thêm mà không báo lỗi gì.
    cols = sorted(_existing_columns(inspect(db.get_bind()), "role_permissions"))

    for key, label in (("cham_cong", "Chấm công"), ("self_service", "Tự phục vụ")):
        db.execute(
            text("INSERT INTO modules (key, label, created_at) "
                 "SELECT :k, :l, CURRENT_TIMESTAMP "
                 "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"),
            {"k": key, "l": label},
        )
    db.execute(text("UPDATE modules SET label = 'Hồ sơ nhân sự' WHERE key = 'nhan_su'"))


    # (1)+(2) nhan_su → cham_cong, `can_lock` lấy từ `can_adjust` cũ.
    chep = [c for c in cols if c not in ("id", "module_key")]
    chon = []
    for c in chep:
        if c == "can_lock" and "can_adjust" in cols:
            chon.append("CASE WHEN rp.can_lock OR rp.can_adjust THEN true ELSE false END")
        else:
            chon.append(f"rp.{c}")
    db.execute(
        text(
            f"INSERT INTO role_permissions (module_key, {', '.join(chep)}) "
            f"SELECT 'cham_cong', {', '.join(chon)} FROM role_permissions rp "
            "WHERE rp.module_key = 'nhan_su' AND NOT EXISTS ("
            "  SELECT 1 FROM role_permissions x "
            "  WHERE x.role_id = rp.role_id AND x.module_key = 'cham_cong')"
        )
    )

    # (3)+(4) self_service + noi_quy: cấp `can_read` cho MỌI vai đang có.
    khac = [c for c in cols if c not in ("id", "role_id", "module_key", "scope")]
    gan = ", ".join(khac)
    for key, bat in (("self_service", {"can_read"}), ("noi_quy", {"can_read"})):
        gia_tri = ", ".join("true" if c in bat else "false" for c in khac)
        db.execute(
            text(
                f"INSERT INTO role_permissions (role_id, module_key, scope, {gan}) "
                f"SELECT r.id, :k, 'own', {gia_tri} FROM roles r "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM role_permissions x "
                "  WHERE x.role_id = r.id AND x.module_key = :k)"
            ),
            {"k": key},
        )

    # (5) Lương giữ nguyên phạm vi đang thực sự dùng = phạm vi của `nhan_su`.
    db.execute(text(
        "UPDATE role_permissions SET scope = ("
        "  SELECT ns.scope FROM role_permissions ns "
        "  WHERE ns.role_id = role_permissions.role_id AND ns.module_key = 'nhan_su') "
        "WHERE module_key = 'luong' AND EXISTS ("
        "  SELECT 1 FROM role_permissions ns "
        "  WHERE ns.role_id = role_permissions.role_id AND ns.module_key = 'nhan_su' "
        "    AND ns.scope <> role_permissions.scope)"
    ))
    db.commit()


MIGRATIONS.append(("0179_tach_module_nhan_su_luong", _migrate_tach_module_nhan_su_luong))


def _migrate_tach_o_danh_dau_da_chi_luong(db) -> None:
    """Tách "Đánh dấu ĐÃ CHI lương" khỏi "Chốt bảng lương" (đợt 4, 10/08/2026).

    Trước: bốn endpoint `/luong/lock`, `/reopen`, `/pay`, `/unpay` dùng CHUNG ô `can_lock`. Ai chốt
    được bảng lương thì tự tuyên bố luôn "đã trả tiền cho người lao động" — không còn ai đối chiếu.
    Ngoài đời hai việc hai người: người tính lương chốt số, kế toán mới xác nhận đã trả.

    Sau: `/pay` + `/unpay` đòi ô riêng `can_manage_status`.

    Ánh xạ `can_manage_status = can_lock` cũ để người đang làm không mất việc. Quản trị bỏ tick cho
    ai không cần — đó mới là điều muốn có. KHÔNG cấp cho người không có `can_lock`: đó là ô cho
    tiền ra, vống lên còn tệ hơn cái đang sửa.

    Idempotent: chỉ đụng dòng `luong` nào chưa bật `can_manage_status`.
    """
    db.execute(text(
        "UPDATE role_permissions SET can_manage_status = true "
        "WHERE module_key = 'luong' AND can_lock AND NOT can_manage_status"
    ))
    db.commit()


MIGRATIONS.append(("0180_tach_o_danh_dau_da_chi_luong", _migrate_tach_o_danh_dau_da_chi_luong))


def _migrate_them_o_xem_nhat_ky_cham_cong(db) -> None:
    """Thêm cột `role_permissions.can_view_log` + tách "Nhật ký chấm công · Xem" (11/08/2026).

    `create_all` chỉ TẠO bảng, KHÔNG ALTER ⇒ cột mới phải thêm ở đây thì DB đang chạy mới nhận.

    Ánh xạ `can_view_log = can_read` của `cham_cong`: ai đang xem được nhật ký thì vẫn xem được.
    Bỏ ánh xạ là sáng hôm sau tab Nhật ký trắng trơn với tất cả mọi người, kể cả HCNS.
    """
    insp = inspect(db.get_bind())
    if "can_view_log" not in _existing_columns(insp, "role_permissions"):
        db.execute(text(
            "ALTER TABLE role_permissions ADD COLUMN can_view_log BOOLEAN NOT NULL DEFAULT false"
        ))
        db.commit()
    db.execute(text(
        "UPDATE role_permissions SET can_view_log = true "
        "WHERE module_key = 'cham_cong' AND can_read AND NOT can_view_log"
    ))
    db.commit()


MIGRATIONS.append(("0181_them_o_xem_nhat_ky_cham_cong", _migrate_them_o_xem_nhat_ky_cham_cong))


def _migrate_doi_o_duyet_pmh_sang_ke_toan(db) -> None:
    """Dời "Duyệt / từ chối PMH" sang khoá `ke_toan`, tách 3 việc kia ra ô riêng (11/08/2026).

    Ô `thu_mua:can_approve` cũ mang HAI nghĩa và nằm SAI phân hệ:
      • "duyệt / từ chối PMH" — nút chỉ có ở màn **Đơn mua hàng (Kế toán)**;
      • "sửa số nhận · mở lại đơn · đóng đơn" — nút ở màn Mua hàng, chẳng liên quan tới duyệt.

    Nay tách đôi, mỗi ô về đúng màn có nút. Vì cùng một cờ cũ nuôi cả hai nên phải chép sang CẢ HAI
    đích, nếu không thì mất một trong hai đường làm việc:
      • `ke_toan.can_approve      = thu_mua.can_approve`  (người đang duyệt vẫn duyệt được)
      • `thu_mua.can_manage_status = thu_mua.can_approve` (người đang mở lại đơn vẫn mở được)

    `thu_mua.can_cancel` (ô "Hủy PMH") bỏ hẳn — endpoint và nút đều đã gỡ. KHÔNG xoá cột trong DB:
    cột dùng chung cho mọi module, `yeu_cau_mua_hang` và các phân hệ khác vẫn đang dùng.

    Idempotent: chỉ bật thêm, không ghi đè cái đã bật.
    """
    # ke_toan có thể chưa có dòng cho vai đó ⇒ vừa UPDATE vừa INSERT.
    cols = sorted(_existing_columns(inspect(db.get_bind()), "role_permissions"))
    db.execute(text(
        "UPDATE role_permissions SET can_approve = true "
        "WHERE module_key = 'ke_toan' AND NOT can_approve AND role_id IN ("
        "  SELECT role_id FROM role_permissions WHERE module_key = 'thu_mua' AND can_approve)"
    ))
    khac = [c for c in cols if c not in ("id", "role_id", "module_key", "scope")]
    gia_tri = ", ".join("true" if c in ("can_read", "can_approve") else "false" for c in khac)
    db.execute(text(
        f"INSERT INTO role_permissions (role_id, module_key, scope, {', '.join(khac)}) "
        f"SELECT rp.role_id, 'ke_toan', rp.scope, {gia_tri} FROM role_permissions rp "
        "WHERE rp.module_key = 'thu_mua' AND rp.can_approve AND NOT EXISTS ("
        "  SELECT 1 FROM role_permissions x "
        "  WHERE x.role_id = rp.role_id AND x.module_key = 'ke_toan')"
    ))
    db.execute(text(
        "UPDATE role_permissions SET can_manage_status = true "
        "WHERE module_key = 'thu_mua' AND can_approve AND NOT can_manage_status"
    ))
    db.commit()


MIGRATIONS.append(("0182_doi_o_duyet_pmh_sang_ke_toan", _migrate_doi_o_duyet_pmh_sang_ke_toan))


def _migrate_ycmh_khong_con_an_theo_khoa_thu_mua(db) -> None:
    """Gỡ lối tắt "có `thu_mua` là thấy YCMH cả công ty" — cấp bù phạm vi thật (11/08/2026).

    LỖ HỔNG ĐO ĐƯỢC: `_sees_all_department_requests` từng mở cửa cho bất kỳ vai nào CÓ dòng quyền
    `thu_mua`, **không xét phạm vi**. Hậu quả: quản trị chọn "Của tôi" hay "Cả phòng" ở màn Yêu cầu
    mua hàng cũng vô ích — vẫn thấy yêu cầu của mọi bộ phận. Đo: vai `yeu_cau_mua_hang` phạm vi
    `own` thấy 1 dòng; cấp thêm `thu_mua` (cũng `own`) thành 2 dòng, đủ cả hai phòng.

    Lối tắt sinh ra khi YCMH chưa có khoá riêng. Nay nó có `yeu_cau_mua_hang`, nên cách đúng là
    ghi thẳng phạm vi `all` lên khoá đó — hiện trên ma trận, quản trị gỡ được.

    Ai được cấp bù: vai đang có `thu_mua` (bộ phận mua hàng — hộp việc của họ đúng là toàn công
    ty). KHÔNG cấp cho vai chỉ có `bao_gia`/`kho`/`san_xuat`… — mấy vai đó xưa nay vẫn chỉ thấy
    phòng mình, giữ nguyên.

    Idempotent: chỉ nới phạm vi, không thu hẹp cái đã rộng.
    """
    cols = sorted(_existing_columns(inspect(db.get_bind()), "role_permissions"))
    khac = [c for c in cols if c not in ("id", "role_id", "module_key", "scope")]
    gia_tri = ", ".join("true" if c == "can_read" else "false" for c in khac)

    # Vai có `thu_mua` mà CHƯA có dòng `yeu_cau_mua_hang` ⇒ thêm dòng, phạm vi `all`.
    db.execute(text(
        f"INSERT INTO role_permissions (role_id, module_key, scope, {', '.join(khac)}) "
        f"SELECT rp.role_id, 'yeu_cau_mua_hang', 'all', {gia_tri} FROM role_permissions rp "
        "WHERE rp.module_key = 'thu_mua' AND NOT EXISTS ("
        "  SELECT 1 FROM role_permissions x "
        "  WHERE x.role_id = rp.role_id AND x.module_key = 'yeu_cau_mua_hang')"
    ))
    # Đã có dòng nhưng phạm vi hẹp ⇒ nới lên `all` + bật Xem (trước đây họ vẫn thấy hết mà).
    db.execute(text(
        "UPDATE role_permissions SET scope = 'all', can_read = true "
        "WHERE module_key = 'yeu_cau_mua_hang' AND scope <> 'all' AND role_id IN ("
        "  SELECT role_id FROM role_permissions WHERE module_key = 'thu_mua')"
    ))
    db.commit()


MIGRATIONS.append(
    ("0183_ycmh_khong_con_an_theo_khoa_thu_mua", _migrate_ycmh_khong_con_an_theo_khoa_thu_mua)
)


def _migrate_tu_phuc_vu_co_o_thao_tac(db) -> None:
    """Tự phục vụ tách làm hai ô: XEM (`can_read`) và THAO TÁC (`can_create`) — 11/08/2026.

    Trước đó khoá `self_service` CHỈ dùng động từ `read`, nên cột "Thao tác" của nó là ô chết: gỡ
    tick đi thì thợ vẫn chấm công, vẫn gửi phiếu tăng ca, vẫn xin nghỉ. Chủ chốt báo đúng ba lần
    ở ba màn khác nhau, cùng một gốc.

    ⚠️ ÁNH XẠ BẮT BUỘC — `can_create = can_read`. Cột `can_create` của `self_service` xưa nay chưa
    ai bật (nó vô nghĩa mà), nên không ánh xạ là sáng hôm sau **cả nhà máy không chấm công được**,
    không ai xin nghỉ được. Đây là migration mà quên thì cả công ty đứng.

    Thêm: `nghi_phep.can_create` (xin nghỉ) cũng đổ sang `self_service.can_create` — từ nay xin
    nghỉ cho chính mình đi cùng ô với xin tăng ca / đi muộn / tạm ứng, không còn một mình một kiểu.
    `nghi_phep.can_create` GIỮ NGUYÊN, nay mang nghĩa "nhập đơn HỘ người khác" (HCNS nhập giùm thợ
    không dùng máy).

    Idempotent: chỉ bật thêm, không tắt gì.
    """
    db.execute(text(
        "UPDATE role_permissions SET can_create = true "
        "WHERE module_key = 'self_service' AND can_read AND NOT can_create"
    ))
    db.execute(text(
        "UPDATE role_permissions SET can_create = true "
        "WHERE module_key = 'self_service' AND NOT can_create AND role_id IN ("
        "  SELECT role_id FROM role_permissions WHERE module_key = 'nghi_phep' AND can_create)"
    ))
    db.commit()


MIGRATIONS.append(("0184_tu_phuc_vu_co_o_thao_tac", _migrate_tu_phuc_vu_co_o_thao_tac))


def _migrate_tach_o_yeu_cau_chinh_cong(db) -> None:
    """Tách "Yêu cầu chỉnh công" ra ô riêng + Đi muộn chỉ còn ô Duyệt (11/08/2026).

    HAI việc, hai gốc khác nhau:

    1. **Yêu cầu chỉnh công** tách khỏi `cham_cong`. Trước đây xem thì dùng chung `cham_cong:read`,
       duyệt thì dùng chung `cham_cong:adjust`. Ai đang duyệt (`can_adjust`) được chép sang ô mới
       với `can_read` + `can_approve`; phạm vi giữ nguyên, nhưng `own` nâng lên `department` —
       duyệt yêu cầu của CHÍNH MÌNH là vô nghĩa, để `own` thì màn trống trơn.

    2. **Đi muộn / về sớm**: đọc danh sách nay đòi `di_muon:approve` thay vì `read` (màn chỉ còn
       một việc thật là duyệt). Ai đang có `read` mà chưa có `approve` sẽ mất đường vào — nhưng
       KHÔNG cấp bù `approve` cho họ: duyệt phiếu người khác là quyền nặng hơn hẳn quyền xem, tự
       nâng cấp là mở cửa. Họ vẫn xem phiếu CỦA MÌNH qua ô Tự phục vụ; quản trị muốn cho ai duyệt
       thì tick ô Duyệt — hiện rõ trên ma trận.

    Idempotent: chạy lại không đẻ hàng trùng.
    """
    for key, label in (("yeu_cau_chinh_cong", "Yêu cầu chỉnh công"),):
        db.execute(
            text("INSERT INTO modules (key, label, created_at) "
                 "SELECT :k, :l, CURRENT_TIMESTAMP "
                 "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"),
            {"k": key, "l": label},
        )

    cols = sorted(_existing_columns(inspect(db.get_bind()), "role_permissions"))
    khac = [c for c in cols if c not in ("id", "role_id", "module_key", "scope")]
    gia_tri = ", ".join(
        "true" if c in ("can_read", "can_approve") else "false" for c in khac
    )
    db.execute(text(
        f"INSERT INTO role_permissions (role_id, module_key, scope, {', '.join(khac)}) "
        f"SELECT rp.role_id, 'yeu_cau_chinh_cong', "
        # `own` → `department`: duyệt yêu cầu của chính mình là vô nghĩa.
        f"CASE WHEN rp.scope = 'own' THEN 'department' ELSE rp.scope END, {gia_tri} "
        "FROM role_permissions rp "
        "WHERE rp.module_key = 'cham_cong' AND rp.can_adjust AND NOT EXISTS ("
        "  SELECT 1 FROM role_permissions x "
        "  WHERE x.role_id = rp.role_id AND x.module_key = 'yeu_cau_chinh_cong')"
    ))
    db.commit()


MIGRATIONS.append(("0185_tach_o_yeu_cau_chinh_cong", _migrate_tach_o_yeu_cau_chinh_cong))


def _migrate_them_generated_at_cho_ky_luong(db) -> None:
    """Thêm `payroll_periods.generated_at` — dấu "engine chạy lần cuối lúc nào" (12/08/2026).

    `create_all` chỉ TẠO bảng, KHÔNG ALTER ⇒ cột mới phải thêm ở đây thì DB đang chạy mới nhận.

    DÙNG ĐỂ LÀM GÌ: bịt khe hở L4 của vòng khoá công ⇄ lương. Chuỗi mới bắt chốt công trước khi
    chốt lương, nhưng vẫn còn kẽ:

        9h  tính lương (số live)  →  10h  ai đó chấm bù  →  11h  chốt công  →  12h  chốt lương

    Dòng lương lúc 12h VẪN là số của 9h. So `generated_at` với `attendance_periods.locked_at` là
    biết ngay, rồi bắt bấm "Tính lại" trước khi cho chốt.

    KHÔNG ĐOÁN cho kỳ cũ: để NULL. Đoán bừa (vd gán `created_at`) là tự tay khẳng định một điều
    mình không biết — kỳ cũ nào lỡ rơi vào diện phải chặn thì cứ bấm Tính lại một lần là xong,
    rẻ hơn nhiều so với cho lọt một kỳ đáng ra phải chặn.
    """
    insp = inspect(db.get_bind())
    if "generated_at" not in _existing_columns(insp, "payroll_periods"):
        db.execute(text("ALTER TABLE payroll_periods ADD COLUMN generated_at TIMESTAMP NULL"))
        db.commit()


MIGRATIONS.append(("0186_them_generated_at_cho_ky_luong", _migrate_them_generated_at_cho_ky_luong))


def _migrate_sales_invoices_ar(db: Session) -> None:
    """AR: công nợ phải thu chỉ phát sinh từ hóa đơn bán đã phát hành (12/08/2026).

    Tạo sổ hóa đơn bán và nối Phiếu thu vào đúng hóa đơn nguồn. Trên DB trắng, `create_all`
    đã dựng đủ bảng/cột nên migration chỉ bảo đảm index; trên DB đang chạy, DDL dưới đây vá
    tiến idempotent cho cả SQLite và PostgreSQL.
    """
    bind = db.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    id_pk = "INTEGER PRIMARY KEY" if bind.dialect.name == "sqlite" else "SERIAL PRIMARY KEY"

    if "orders" in tables and "customers" in tables and "users" in tables:
        db.execute(text(
            "CREATE TABLE IF NOT EXISTS sales_invoices ("
            f"id {id_pk}, "
            "order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE RESTRICT, "
            "customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL, "
            "invoice_symbol VARCHAR(64) NOT NULL, "
            "invoice_number VARCHAR(64) NOT NULL, "
            "invoice_date DATE NOT NULL, "
            "amount_vnd BIGINT NOT NULL, "
            "payment_term_days_snapshot INTEGER, "
            "due_date DATE, "
            "customer_name_snapshot VARCHAR(255) NOT NULL, "
            "status VARCHAR(16) NOT NULL DEFAULT 'issued', "
            "created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
            "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "cancelled_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
            "cancelled_at TIMESTAMP, "
            "cancel_reason TEXT, "
            "CONSTRAINT uq_sales_invoice_symbol_number "
            "UNIQUE (invoice_symbol, invoice_number))"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sales_invoices_order_id "
            "ON sales_invoices (order_id)"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sales_invoices_customer_id "
            "ON sales_invoices (customer_id)"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sales_invoices_status "
            "ON sales_invoices (status)"
        ))

    # Refresh sau CREATE TABLE để SQLite/Postgres đều thấy schema mới trong cùng migration.
    insp = inspect(bind)
    migrated_tables = set(insp.get_table_names())
    if "payment_receipts" in migrated_tables and "sales_invoices" in migrated_tables:
        receipt_cols = _existing_columns(insp, "payment_receipts")
        if "sales_invoice_id" not in receipt_cols:
            db.execute(text(
                "ALTER TABLE payment_receipts ADD COLUMN sales_invoice_id INTEGER "
                "REFERENCES sales_invoices(id) ON DELETE RESTRICT"
            ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_payment_receipts_sales_invoice_id "
            "ON payment_receipts (sales_invoice_id)"
        ))

    db.commit()


MIGRATIONS.append(("0187_sales_invoices_ar", _migrate_sales_invoices_ar))


def _migrate_sales_invoices_legacy_compat(db: Session) -> None:
    """Đưa bảng hóa đơn bán đời cũ về schema AR hiện tại mà không làm mất dữ liệu.

    Một bản triển khai trước đã tạo ``sales_invoices`` với các tên
    ``invoice_series``/``invoice_no``/``payment_term_days``. Vì bảng đã tồn tại,
    migration 0187 dùng ``CREATE TABLE IF NOT EXISTS`` không thể bổ sung các cột
    mới và mọi truy vấn ORM đều lỗi ngay ở ``invoice_symbol``.
    """
    bind = db.get_bind()
    insp = inspect(bind)
    if "sales_invoices" not in set(insp.get_table_names()):
        return

    columns = _existing_columns(insp, "sales_invoices")
    additions = (
        ("invoice_symbol", "VARCHAR(64)"),
        ("invoice_number", "VARCHAR(64)"),
        ("payment_term_days_snapshot", "INTEGER"),
        ("updated_at", "TIMESTAMP"),
    )
    for name, sql_type in additions:
        if name not in columns:
            db.execute(text(f"ALTER TABLE sales_invoices ADD COLUMN {name} {sql_type}"))
    db.commit()

    columns = _existing_columns(inspect(bind), "sales_invoices")
    symbol_source = (
        "COALESCE(NULLIF(TRIM(invoice_series), ''), 'HD')"
        if "invoice_series" in columns
        else "'HD'"
    )
    number_candidates = []
    if "invoice_no" in columns:
        number_candidates.append("NULLIF(TRIM(invoice_no), '')")
    if "code" in columns:
        number_candidates.append("NULLIF(TRIM(code), '')")
    number_candidates.append("CAST(id AS VARCHAR(64))")
    number_source = (
        number_candidates[0]
        if len(number_candidates) == 1
        else f"COALESCE({', '.join(number_candidates)})"
    )

    db.execute(text(
        "UPDATE sales_invoices SET "
        f"invoice_symbol = COALESCE(invoice_symbol, {symbol_source}), "
        f"invoice_number = COALESCE(invoice_number, {number_source}), "
        "updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
    ))
    if "payment_term_days" in columns:
        db.execute(text(
            "UPDATE sales_invoices SET payment_term_days_snapshot = payment_term_days "
            "WHERE payment_term_days_snapshot IS NULL"
        ))
    if "customer_name_snapshot" in columns:
        db.execute(text(
            "UPDATE sales_invoices SET customer_name_snapshot = 'Khách hàng' "
            "WHERE customer_name_snapshot IS NULL OR TRIM(customer_name_snapshot) = ''"
        ))

    # Bảng cũ không bắt duy nhất cặp ký hiệu + số. Chỉ hậu tố những dòng trùng phía sau để
    # migration không làm sập startup mà vẫn giữ dòng đầu tiên đúng nguyên bản.
    db.execute(text(
        "UPDATE sales_invoices AS current_row SET "
        "invoice_number = invoice_number || '-' || CAST(id AS VARCHAR(32)) "
        "WHERE EXISTS (SELECT 1 FROM sales_invoices AS earlier "
        "WHERE earlier.invoice_symbol = current_row.invoice_symbol "
        "AND earlier.invoice_number = current_row.invoice_number "
        "AND earlier.id < current_row.id)"
    ))

    if bind.dialect.name == "postgresql":
        for name in ("invoice_symbol", "invoice_number", "updated_at"):
            db.execute(text(
                f"ALTER TABLE sales_invoices ALTER COLUMN {name} SET NOT NULL"
            ))
        # Các cột bắt buộc của schema cũ không còn được ORM hiện tại ghi. Cho phép NULL để
        # hóa đơn mới vẫn chèn được; dữ liệu lịch sử trong các cột này được giữ nguyên.
        for legacy_name in ("code", "subtotal_vnd", "vat_vnd"):
            if legacy_name in columns:
                db.execute(text(
                    f"ALTER TABLE sales_invoices ALTER COLUMN {legacy_name} DROP NOT NULL"
                ))

    db.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_invoice_symbol_number "
        "ON sales_invoices (invoice_symbol, invoice_number)"
    ))
    db.commit()


MIGRATIONS.append(("0189_sales_invoices_legacy_compat", _migrate_sales_invoices_legacy_compat))


def _migrate_module_notifications(db: Session) -> None:
    """Tạo hai bảng badge đọc/chưa đọc cho DB đang chạy.

    DB trắng đã được ``create_all`` dựng từ model; ``checkfirst`` giữ migration idempotent cho cả
    SQLite và PostgreSQL mà không phải duy trì hai bản CREATE TABLE bằng chuỗi SQL.
    """
    from .models.module_notification import ModuleNotification, ModuleNotificationRead

    bind = db.get_bind()
    ModuleNotification.__table__.create(bind, checkfirst=True)
    ModuleNotificationRead.__table__.create(bind, checkfirst=True)
    db.commit()


MIGRATIONS.append(("0190_module_notifications", _migrate_module_notifications))


def _migrate_module_notification_recipient(db: Session) -> None:
    """Bổ sung người nhận cho bảng thông báo đã được tạo bởi bản 0190 đầu tiên.

    Một số DB đã chạy 0190 trước khi ``recipient_user_id`` được thêm vào model. Sửa lại 0190 không
    giúp các DB đó vì migration đã được đánh dấu hoàn tất, nên phải có một bước mới độc lập.
    """
    bind = db.get_bind()
    insp = inspect(bind)
    if "module_notifications" not in set(insp.get_table_names()):
        return
    if "recipient_user_id" not in _existing_columns(insp, "module_notifications"):
        db.execute(text(
            "ALTER TABLE module_notifications ADD COLUMN recipient_user_id INTEGER "
            "REFERENCES users(id) ON DELETE CASCADE"
        ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_module_notifications_recipient_user_id "
        "ON module_notifications (recipient_user_id)"
    ))
    db.commit()


MIGRATIONS.append((
    "0191_module_notification_recipient",
    _migrate_module_notification_recipient,
))


def _migrate_rejected_pmh_keeps_ycmh_reserved(db: Session) -> None:
    """Sửa YCMH cũ bị thả về ``open`` khi PMH nguồn bị Kế toán từ chối.

    Luồng đúng là Thu mua sửa và gửi lại chính PMH bị từ chối. YCMH phải tiếp tục được giữ ở
    ``pending_approval``; nếu để ``open``, cả giao diện lẫn API đều cho lập thêm PMH trùng nguồn.
    """
    tables = set(inspect(db.get_bind()).get_table_names())
    required = {
        "department_purchase_requests",
        "purchase_requests",
        "purchase_request_sources",
    }
    if not required.issubset(tables):
        return

    stale_ids = list(db.execute(text(
        "SELECT d.id FROM department_purchase_requests d "
        "WHERE d.status = 'open' AND EXISTS ("
        "SELECT 1 FROM purchase_request_sources prs "
        "JOIN purchase_requests pr ON pr.id = prs.purchase_request_id "
        "WHERE prs.department_request_id = d.id AND pr.status = 'rejected')"
    )).scalars())
    if not stale_ids:
        return

    has_history = "purchase_status_history" in tables
    has_updated_at = "updated_at" in _existing_columns(
        inspect(db.get_bind()), "department_purchase_requests"
    )
    for doc_id in stale_ids:
        if has_history:
            db.execute(text(
                "INSERT INTO purchase_status_history "
                "(doc_type, doc_id, from_status, to_status, changed_by_user_id, source, reason, created_at) "
                "VALUES ('ycmh', :doc_id, 'open', 'pending_approval', NULL, 'may', "
                ":reason, CURRENT_TIMESTAMP)"
            ), {
                "doc_id": doc_id,
                "reason": "Sửa dữ liệu: PMH bị từ chối vẫn giữ YCMH để chỉnh sửa và gửi lại",
            })
        db.execute(text(
            "UPDATE department_purchase_requests SET status = 'pending_approval'"
            + (", updated_at = CURRENT_TIMESTAMP" if has_updated_at else "")
            + " WHERE id = :doc_id AND status = 'open'"
        ), {"doc_id": doc_id})
    db.commit()


MIGRATIONS.append((
    "0192_rejected_pmh_keeps_ycmh_reserved",
    _migrate_rejected_pmh_keeps_ycmh_reserved,
))
def _migrate_kho_khoa_so_them_ten(db) -> None:
    """Thêm cột `ten` (tên kỳ, tuỳ chọn) vào kho_khoa_so — đặt khi 'khoa' để nhận diện nhanh + CHẶN
    TRÙNG với kỳ đang khóa khác. Nullable → no-op trên DB tạo mới bằng create_all."""
    insp = inspect(db.get_bind())
    if "kho_khoa_so" not in insp.get_table_names():
        return
    if "ten" not in _existing_columns(insp, "kho_khoa_so"):
        db.execute(text("ALTER TABLE kho_khoa_so ADD COLUMN ten VARCHAR(120)"))
        db.commit()


MIGRATIONS.append(("0187_kho_khoa_so_them_ten", _migrate_kho_khoa_so_them_ten))


def _migrate_stock_request_quyet_dinh_xem_luc(db) -> None:
    """Thêm cột `quyet_dinh_xem_luc` (người tạo đã MỞ XEM yêu cầu tới lúc nào) vào stock_requests —
    nuôi badge "yêu cầu của tôi vừa được kho PHẢN HỒI (hoàn tất/không thành)". Nullable → no-op trên
    DB tạo mới bằng create_all. BASELINE: coi mọi yêu cầu HIỆN CÓ là đã xem (seen = updated_at) →
    badge chỉ đếm phản hồi MỚI về sau, tránh nhảy số vì dữ liệu cũ."""
    insp = inspect(db.get_bind())
    if "stock_requests" not in insp.get_table_names():
        return
    if "quyet_dinh_xem_luc" not in _existing_columns(insp, "stock_requests"):
        db.execute(text("ALTER TABLE stock_requests ADD COLUMN quyet_dinh_xem_luc TIMESTAMP WITH TIME ZONE"))
        db.execute(text("UPDATE stock_requests SET quyet_dinh_xem_luc = updated_at"))
        db.commit()


MIGRATIONS.append(("0188_stock_request_quyet_dinh_xem_luc", _migrate_stock_request_quyet_dinh_xem_luc))


def _migrate_cong_bo_phieu_luong(db) -> None:
    """Thêm `payroll_periods.cong_bo_luc` — mốc PHÁT PHIẾU LƯƠNG cho NLĐ (12/08/2026).

    `create_all` chỉ TẠO bảng, KHÔNG ALTER ⇒ cột mới phải thêm ở đây thì DB đang chạy mới nhận.

    VÌ SAO CÓ: trước đó `latest_line_for_employee` trả dòng lương của kỳ mới nhất mà KHÔNG lọc
    trạng thái kỳ — HCNS vừa bấm "Tính lại", số còn đang soát, thợ đã mở điện thoại xem được; HCNS
    sửa tiếp thì số đổi, không ai báo gì.

    MỘT CỘT LÀM CẢ HAI VIỆC: "Công bố ngay" ghi thời điểm hiện tại, "Hẹn giờ" ghi mốc tương lai.
    Điều kiện thấy phiếu là `cong_bo_luc <= bây giờ`, KIỂM LÚC ĐỌC ⇒ không cần job chạy nền.

    ĐỂ NULL CHO MỌI KỲ CŨ, cố ý: kỳ cũ coi như CHƯA công bố. Chọn ngược lại (mở sẵn hết) thì cột
    này vô nghĩa ngay ngày đầu — mà mở sẵn cũng chỉ giữ nguyên hiện trạng đang muốn sửa.
    """
    insp = inspect(db.get_bind())
    if "cong_bo_luc" not in _existing_columns(insp, "payroll_periods"):
        db.execute(text("ALTER TABLE payroll_periods ADD COLUMN cong_bo_luc TIMESTAMP NULL"))
        db.commit()


MIGRATIONS.append(("0187_cong_bo_phieu_luong", _migrate_cong_bo_phieu_luong))


def _migrate_de_tay_khoan_tu_ho_so(db) -> None:
    """Thêm `payroll_line_components.da_de_tay` — sửa khoản "Từ hồ sơ" cho RIÊNG một kỳ (12/08/2026).

    Chủ chốt: *"gán cho nó Hỗ trợ chi phí đi lại, nhưng tháng này nó đi nhiều hơn thì sửa thế nào?"*
    Trước đó không sửa được: code chặn thẳng, vì dòng `source='employee'` bị xoá-ghi-lại mỗi lần
    bấm "Tính lại" nên sửa xong là mất số âm thầm.

    `false` cho mọi dòng cũ — không dòng nào đang bị đè, không có gì để đoán.
    """
    insp = inspect(db.get_bind())
    if "da_de_tay" not in _existing_columns(insp, "payroll_line_components"):
        db.execute(text(
            "ALTER TABLE payroll_line_components ADD COLUMN da_de_tay BOOLEAN NOT NULL DEFAULT false"
        ))
        db.commit()


MIGRATIONS.append(("0188_de_tay_khoan_tu_ho_so", _migrate_de_tay_khoan_tu_ho_so))


def _migrate_dong_phieu_luong(db) -> None:
    """Thêm `payroll_periods.dong_phieu_luc` — mốc ĐÓNG phiếu lương (12/08/2026).

    Cùng `cong_bo_luc` (mg 0187) tạo thành MỘT CỬA SỔ: NV thấy phiếu khi
    `cong_bo_luc <= bây giờ < dong_phieu_luc`. Chủ chốt: *"cài giờ phiếu nó hiển thị trong bao
    nhiêu lâu"* — phiếu lương không cần mở vĩnh viễn.

    NULL cho mọi kỳ cũ = mở không thời hạn ⇒ kỳ nào đang công bố vẫn giữ nguyên hành vi. Chọn
    ngược lại (đóng sẵn) là âm thầm rút phiếu của những kỳ đang mở.
    """
    insp = inspect(db.get_bind())
    if "dong_phieu_luc" not in _existing_columns(insp, "payroll_periods"):
        db.execute(text("ALTER TABLE payroll_periods ADD COLUMN dong_phieu_luc TIMESTAMP NULL"))
        db.commit()


MIGRATIONS.append(("0189_dong_phieu_luong", _migrate_dong_phieu_luong))


def _migrate_com_tang_ca(db) -> None:
    """SUẤT CƠM TĂNG CA (12/08/2026) — 3 cột, một luật.

    Chủ chốt: *"Tăng ca 3 tiếng sẽ được thưởng tiền cơm, cái này setup động nha; riêng tăng ca
    ngày chủ nhật thì cứ tăng ca là được tiền cơm cho dù 1 tiếng hay 2 tiếng."*

    Ba cột, mỗi cột một việc:
      • `attendance_period_lines.ot_days_json` — phút tăng ca TỪNG NGÀY, tách ngày làm / ngày nghỉ.
        Ảnh chụp cũ chỉ giữ TỔNG phút cả tháng nên không trả lời được "ngày nào đủ 3 tiếng".
      • `payroll_params.com_tang_ca_nguong_phut` — ngưỡng cho NGÀY LÀM VIỆC (mặc định 180' = 3h).
      • `payroll_params.com_tang_ca_muc` — tiền một suất. MẶC ĐỊNH 0 = TẮT, chủ tự khai.

    Vì sao mức mặc định 0 chứ không phải 25.000 như cơm ca: bật sẵn một khoản RA TIỀN cho cả nhà
    máy mà chưa ai duyệt số là tự ý tăng quỹ lương. Cùng lối với `cong_doan_rate` (cũng mặc định 0).
    Ngưỡng thì để 180' vì nó chỉ có nghĩa khi mức > 0.
    """
    insp = inspect(db.get_bind())
    if "ot_days_json" not in _existing_columns(insp, "attendance_period_lines"):
        db.execute(text("ALTER TABLE attendance_period_lines ADD COLUMN ot_days_json TEXT NULL"))
        db.commit()
    cot_params = _existing_columns(insp, "payroll_params")
    if "com_tang_ca_nguong_phut" not in cot_params:
        db.execute(text("ALTER TABLE payroll_params ADD COLUMN com_tang_ca_nguong_phut "
                        "INTEGER NOT NULL DEFAULT 180"))
        db.commit()
    if "com_tang_ca_muc" not in cot_params:
        db.execute(text("ALTER TABLE payroll_params ADD COLUMN com_tang_ca_muc "
                        "NUMERIC(14,2) NOT NULL DEFAULT 0"))
        db.commit()
    if "com_tang_ca_pay" not in _existing_columns(insp, "payroll_lines"):
        db.execute(text("ALTER TABLE payroll_lines ADD COLUMN com_tang_ca_pay "
                        "NUMERIC(14,2) NOT NULL DEFAULT 0"))
        db.commit()


MIGRATIONS.append(("0190_com_tang_ca", _migrate_com_tang_ca))


def _migrate_gop_o_dao_trang_thai_don(db) -> None:
    """Gộp ô "Sửa / đảo trạng thái đơn sau khi nhận hàng" về ô "Thao tác" (12/08/2026).

    Chủ chốt test rồi kết luận: *"quyền Sửa / đảo trạng thái đơn sau khi nhận hàng với Hủy PMH nó
    vô dụng, bỏ đi được không, tôi test mà nó chả có gì."*

    Hai ô, hai số phận khác nhau:

    • `thu_mua.can_manage_status` — CÓ gác thật (sửa số nhận · mở lại đơn · đóng đơn). Ba việc đó
      là việc thường ngày của chính người lập phiếu, tách ra chỉ thêm một ô phải nhớ tick. Nay
      service hỏi `can_update`, nên PHẢI ĐỔ QUYỀN CŨ SANG — bỏ bước này thì vai nào đang có
      `manage_status` mà chưa có `update` sẽ MẤT cả ba nút sáng hôm sau.

    • `thu_mua.can_cancel` — ô "Hủy PMH", CHƯA BAO GIỜ được đọc: `purchase_service.cancel` gác
      bằng `ke_toan:approve` (hoặc chính người lập khi phiếu còn nháp). Không có gì để đổ.
      KHÔNG xoá cột — nó dùng chung cho mọi module, chỉ gỡ ô khỏi ma trận.
    """
    db.execute(text(
        "UPDATE role_permissions SET can_update = true "
        "WHERE module_key = 'thu_mua' AND can_manage_status AND NOT can_update"
    ))
    db.commit()


MIGRATIONS.append(("0191_gop_o_dao_trang_thai_don", _migrate_gop_o_dao_trang_thai_don))
def _migrate_stock_request_purchase_delivery_id(db) -> None:
    """Thêm `stock_requests.purchase_delivery_id` — nguồn đợt giao đơn mua sinh ra yêu cầu NHẬP
    (chặn nhập kho trùng một đợt). Nullable, soft ref → no-op DB fresh / cột đã có."""
    insp = inspect(db.get_bind())
    if "stock_requests" not in insp.get_table_names():
        return
    if "purchase_delivery_id" not in _existing_columns(insp, "stock_requests"):
        db.execute(text("ALTER TABLE stock_requests ADD COLUMN purchase_delivery_id INTEGER"))
        db.commit()


MIGRATIONS.append(("0189_stock_request_purchase_delivery_id", _migrate_stock_request_purchase_delivery_id))


def _migrate_vat_lieu_kho_anh(db) -> None:
    """Thêm `anh_url` (ảnh minh hoạ vật tư) vào `giay_nguyen` + `vat_tu_in_an`. Nullable → no-op
    trên DB fresh / cột đã có. Lưu đường `/api/files/materials/…`; trang QR serve lại qua token."""
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    for tbl in ("giay_nguyen", "vat_tu_in_an"):
        if tbl in tables and "anh_url" not in _existing_columns(insp, tbl):
            db.execute(text(f"ALTER TABLE {tbl} ADD COLUMN anh_url VARCHAR(500)"))
    db.commit()


MIGRATIONS.append(("0191_vat_lieu_kho_anh", _migrate_vat_lieu_kho_anh))


def _migrate_don_vi_tram_dong_giay(db: Session) -> None:
    """Dòng giấy đọc từ DANH MỤC đơn vị: cờ `don_vi_do.tram_dong_giay` + nới cột đơn vị của bước.

    Trước 11/08/2026, câu hỏi "bước này có nằm trên dòng giấy không" trả lời bằng một danh sách 5
    mã CỨNG trong code (`cong_doan.DON_VI_DONG_GIAY`). Hệ quả: công đoạn không chạm giấy buộc phải
    để TRỐNG đơn vị (ghi kẽm không khai được `bai → kem`), và mọi cách đếm khác của xưởng — mẻ,
    lượt, thùng — không khai nổi vì service chặn ngay ở cổng. Nay đó là một CỜ trên danh mục Đơn
    vị & quy đổi: xưởng thêm đơn vị là dùng được ngay, khỏi sửa code.

    KHÔNG khai cặp quy đổi tĩnh giữa hai trạm: cầu `tờ nguyên → tờ in` là số mảnh xả, `tờ → con` là
    bình bài — thuộc QUY CÁCH TỪNG LỆNH, `_he_so_cau` cấp lúc chạy. Nhét vào bảng cặp là đẻ nguồn
    sự thật thứ hai, rồi hai nơi ra hai số giấy khác nhau trên cùng một lệnh.

    SỐ CỦA MỌI LỆNH ĐANG CHẠY KHÔNG ĐỔI: 5 mã được gắn cờ đúng bằng 5 mã của danh sách cứng cũ.
    """
    bind = db.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "don_vi_do" not in tables:
        return

    def run(sql: str) -> None:
        """Câu chỉ chạy được trên Postgres (ALTER COLUMN TYPE) — SQLite lỗi thì bỏ qua, vì SQLite
        không ép độ dài VARCHAR nên cột ở đó vốn đã không chật."""
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    if "tram_dong_giay" not in _existing_columns(insp, "don_vi_do"):
        db.execute(text("ALTER TABLE don_vi_do ADD COLUMN tram_dong_giay VARCHAR(12)"))
        db.commit()

    # Hai mã dòng giấy CHƯA từng có trong danh mục Đơn vị (chúng chỉ sống trong hằng số của code):
    # `to_nguyen` = giấy khổ mua về chưa xả, `tay` = tay sách đã gấp. Thiếu chúng thì công đoạn Xả
    # giấy / Gấp không chọn được đơn vị của chính mình.
    for ma, ten, ghi_chu in (
        ("to_nguyen", "tờ nguyên", "Tờ giấy khổ mua về, CHƯA xả ra tờ in."),
        ("tay", "tay sách", "Tờ in đã gấp lại thành một tay, mang nhiều trang."),
    ):
        db.execute(
            text("INSERT INTO don_vi_do (ma, ten, ho, he_so_goc, active, dung_lam_toc_do, "
                 "        ghi_chu, created_at, updated_at) "
                 "SELECT :ma, :ten, 'to', 1, TRUE, FALSE, :gc, "
                 "       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
                 "WHERE NOT EXISTS (SELECT 1 FROM don_vi_do WHERE ma = :ma)"),
            {"ma": ma, "ten": ten, "gc": ghi_chu},
        )
    db.commit()

    # Gắn cờ: mã đơn vị TRÙNG tên trạm ở cả 5 mức nên `tram_dong_giay = ma`. Chỉ ghi khi còn NULL,
    # nên xưởng ĐỔI cờ sang trạm khác thì không bị đè; còn xưởng GỠ cờ (về NULL) mà migration chạy
    # lại thì cờ quay về — chấp nhận, vì gỡ cờ của 5 mã lõi là làm sập chuỗi giấy của cả hệ.
    db.execute(text(
        "UPDATE don_vi_do SET tram_dong_giay = ma "
        "WHERE ma IN ('to_nguyen', 'to', 'con', 'tay', 'cai') AND tram_dong_giay IS NULL"
    ))
    db.commit()

    # Nới cột đơn vị của BƯỚC: mã danh mục dài tới 24 ký tự, VARCHAR(12) là Postgres ném lỗi độ dài
    # lúc ghi. Ba bảng — thiếu `bai_ghep_cong_doan` là gộp bài nổ, vì `gop()` chép thẳng đơn vị của
    # bước mẫu xuống đó.
    for bang in ("cong_doan", "lsx_cong_doan", "bai_ghep_cong_doan"):
        if bang not in tables:
            continue
        for cot in ("don_vi_vao", "don_vi_ra"):
            run(f"ALTER TABLE {bang} ALTER COLUMN {cot} TYPE VARCHAR(24)")


MIGRATIONS.append(("0186_don_vi_tram_dong_giay", _migrate_don_vi_tram_dong_giay))


def _migrate_gop_don_gia_kg_ve_don_gia(db: Session) -> None:
    """Gộp `don_gia_kg` VÀ `don_gia_m2` về `don_gia` trong MỌI công thức đã khai.

    Ô công thức phơi tới BA chip đơn giá: "Đơn giá" · "Đơn giá theo cân" · "Đơn giá theo m²".
    Chúng cho CÙNG một số ở mọi mặt hàng đang có (23/23 dòng giấy khai đ/kg, màng khai đ/m²) —
    `don_gia_m2` thậm chí là bản sao y nguyên, engine gán cùng giá trị, KHÔNG BAO GIỜ khác. Người
    khai không có cách nào đoán nên chọn cái nào, còn `don_gia_kg` thì lặng lẽ lệch 1.000 lần ở
    mục khai giá theo TẤN. Chủ chốt bỏ, chỉ còn một chip (11/08/2026). Việc quy đổi về đơn vị cơ sở
    nay làm ở engine (`_don_gia_co_so`) trước khi bơm, nên `don_gia` mang đúng nghĩa cũ của cả hai
    biến kia — số KHÔNG đổi.

    Phải migrate vì công thức là DỮ LIỆU người dùng: bỏ biến mà không sửa dữ liệu thì công thức cũ
    ném lỗi rồi tính 0đ. Trên DB dev có 2 dòng dính (`MUC-CMYK` dùng `don_gia_kg`, `MANG-BONG` dùng
    `don_gia_m2`); prod có thể khác nên quét cả ba bảng có ô công thức.

    Thay theo RANH GIỚI TỪ: thay chuỗi trần sẽ đụng phải tên biến dài hơn nếu mai có
    `don_gia_kg_2`. Và phải thay `don_gia_kg`/`don_gia_m2` TRƯỚC — thay `don_gia` trước thì hai
    biến kia biến thành `don_gia_kg`/`don_gia_m2` méo mó.
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    is_pg = (db.get_bind().dialect.name or "").startswith("postgres")
    for bang, cot in (("giay_nguyen", "cong_thuc_gia"), ("vat_tu_in_an", "cong_thuc_gia"),
                      ("cong_doan", "cong_thuc_gia")):
        if bang not in tables or cot not in _existing_columns(insp, bang):
            continue
        for cu in ("don_gia_kg", "don_gia_m2"):
            if is_pg:
                db.execute(text(
                    f"UPDATE {bang} SET {cot} = regexp_replace({cot}, '\m{cu}\M', 'don_gia', 'g') "
                    f"WHERE {cot} LIKE '%{cu}%'"))
            else:
                # SQLite không có regexp_replace. Bộ test dựng bảng trắng nên gần như không có dòng
                # nào; thay chuỗi trần là đủ, hai mã này không phải tiền tố của biến nào khác.
                db.execute(text(
                    f"UPDATE {bang} SET {cot} = REPLACE({cot}, '{cu}', 'don_gia') "
                    f"WHERE {cot} LIKE '%{cu}%'"))
            db.commit()


MIGRATIONS.append(("0187_gop_bien_don_gia", _migrate_gop_don_gia_kg_ve_don_gia))


def _migrate_go_bien_so_vi_tri_dien_tich(db: Session) -> None:
    """Gỡ hai biến CHẾT khỏi công thức: `so_vi_tri` · `dien_tich`.

    Cả hai có kiểu dữ liệu, cột DB, schema API và engine có đọc — nhưng KHÔNG có ô nhập nào trên
    màn Tính giá, nên giá trị luôn là số 0 mà code đặt lúc tạo dòng (kiểm DB dev: 0/53 dòng khai
    khác 0). Hệ quả: công thức Ép kim `so_vi_tri * so_luong * 400` cho **0đ trên MỌI phiếu**.

    Chủ chốt bỏ (11/08/2026). Nhờ vậy ba ô công thức tiền về CÙNG một bộ biến.

    ⚠️ ĐỔI TIỀN — nói rõ để không ai ngã ngửa:
      · `so_vi_tri` → **1** (coi như một vị trí). Ép kim từ 0đ thành `so_luong × 400`. Không suy ra
        được từ đâu khác: số vị trí ép nhũ là quyết định thiết kế từng đơn, không nằm trong quy cách.
        Xưởng ép 2 vị trí thì sửa lại đơn giá/công thức ở màn Công đoạn.
      · `dien_tich` → **dai_tp * rong_tp * 10000** (khổ thành phẩm mét → cm², đúng đơn vị cũ). Cái
        này TÍNH ĐƯỢC nên thay bằng công thức thật thay vì hằng số — và nó sửa luôn lỗi luôn-bằng-0.

    Hai cột DB giữ nguyên (dự án không có Alembic) và `routing_engine` vẫn đọc chúng cho trục tính
    tiền đời cũ (`per_position` · `per_finished_area`) — chỉ gỡ khỏi TỪ VỰNG công thức.
    """
    import re as _re

    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    thay = (("so_vi_tri", "1"), ("dien_tich", "dai_tp * rong_tp * 10000"))

    def _sua(ct: str) -> str:
        for cu, moi in thay:
            ct = _re.sub(rf"\b{cu}\b", moi, ct)
        # Dọn cho dễ đọc: `1 * x` và `x * 1` là rác thị giác người khai phải nhìn mỗi lần mở ô.
        ct = _re.sub(r"\b1\s*\*\s*", "", ct)
        ct = _re.sub(r"\s*\*\s*1\b", "", ct)
        return ct.strip()

    for bang in ("giay_nguyen", "vat_tu_in_an", "cong_doan"):
        if bang not in tables or "cong_thuc_gia" not in _existing_columns(insp, bang):
            continue
        rows = db.execute(text(
            f"SELECT id, cong_thuc_gia FROM {bang} "
            f"WHERE cong_thuc_gia LIKE '%so_vi_tri%' OR cong_thuc_gia LIKE '%dien_tich%'"
        )).all()
        for _id, ct in rows:
            db.execute(text(f"UPDATE {bang} SET cong_thuc_gia = :ct WHERE id = :id"),
                       {"ct": _sua(ct or ""), "id": _id})
        if rows:
            db.commit()


MIGRATIONS.append(("0188_go_bien_so_vi_tri_dien_tich", _migrate_go_bien_so_vi_tri_dien_tich))


def _migrate_tach_bien_don_gia_va_bien_quy_doi(db: Session) -> None:
    """Mỗi ô công thức một tên biến đơn giá, và quy đổi dùng chung bộ biến với công thức tiền.

    Chủ chốt 11/08/2026 — nhìn chip "Đơn giá" không ai biết giá của CÁI GÌ, và hai ô có hai bảng
    từ vựng khác nhau thì người khai phải nhớ hai bộ. Sau đợt này::

        Giấy 17 · Vật tư 17 · Công đoạn 16 · Quy đổi 16

    Ba việc, SỐ KHÔNG ĐỔI ở đâu cả:

    1. `don_gia` → `don_gia_giay` (danh mục Giấy) · `don_gia_vat_tu` (Vật tư khác).

    2. Công đoạn MẤT hẳn biến đơn giá — nó là biến chết: không có ô nhập ở phiếu (bỏ 21/07) lẫn ở
       danh mục (form chỉ còn ô Công thức), nên chỉ ăn `run_rate` cũ kẹt trong DB. Công thức nào
       còn dùng thì THAY BẰNG CHÍNH SỐ `run_rate` của công đoạn đó — đúng con số engine vẫn đang
       thế vào, nên tiền giữ nguyên. Trên DB dev: 0/13 công thức dính (xưởng đã tự gõ số thẳng).

    3. Quy đổi bỏ ba biến VAI TRÒ: `dai`→`dai_in`, `rong`→`rong_in`, `so_con`→`so_tp`. Làm được vì
       `to_nguyen` nay là đơn vị thật (mig 0186) nên khai được dòng riêng cho tờ nguyên, khỏi cần
       một biến nhập nhằng "khổ của tờ đang đếm".
    """
    import re as _re

    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())

    def _doi(ct: str, cap: tuple[tuple[str, str], ...]) -> str:
        for cu, moi in cap:
            ct = _re.sub(rf"\b{cu}\b", moi, ct)
        return ct.strip()

    for bang, cap in (("giay_nguyen", (("don_gia", "don_gia_giay"),)),
                      ("vat_tu_in_an", (("don_gia", "don_gia_vat_tu"),))):
        if bang not in tables or "cong_thuc_gia" not in _existing_columns(insp, bang):
            continue
        rows = db.execute(text(
            f"SELECT id, cong_thuc_gia FROM {bang} "
            f"WHERE cong_thuc_gia LIKE '%don_gia%'")).all()
        for _id, ct in rows:
            db.execute(text(f"UPDATE {bang} SET cong_thuc_gia = :ct WHERE id = :id"),
                       {"ct": _doi(ct or "", cap), "id": _id})
        if rows:
            db.commit()

    # Công đoạn: `don_gia` → chính số `run_rate` (thứ engine vẫn thế vào). Không có run_rate thì
    # thay bằng 0 — công thức ra 0đ y như trước, chứ không phải tự bịa một mức giá.
    if "cong_doan" in tables and "cong_thuc_gia" in _existing_columns(insp, "cong_doan"):
        rows = db.execute(text(
            "SELECT id, cong_thuc_gia, run_rate FROM cong_doan "
            "WHERE cong_thuc_gia LIKE '%don_gia%'")).all()
        for _id, ct, rate in rows:
            so = f"{float(rate or 0):g}"
            db.execute(text("UPDATE cong_doan SET cong_thuc_gia = :ct WHERE id = :id"),
                       {"ct": _re.sub(r"\bdon_gia\b", so, ct or "").strip(), "id": _id})
        if rows:
            db.commit()

    # Quy đổi động: ba biến vai trò → tên cụ thể.
    if "don_vi_quy_doi" in tables and "cong_thuc" in _existing_columns(insp, "don_vi_quy_doi"):
        cap = (("dai", "dai_in"), ("rong", "rong_in"), ("so_con", "so_tp"))
        rows = db.execute(text(
            "SELECT id, cong_thuc FROM don_vi_quy_doi "
            "WHERE cong_thuc IS NOT NULL AND cong_thuc <> ''")).all()
        for _id, ct in rows:
            db.execute(text("UPDATE don_vi_quy_doi SET cong_thuc = :ct WHERE id = :id"),
                       {"ct": _doi(ct or "", cap), "id": _id})
        if rows:
            db.commit()


MIGRATIONS.append(("0189_tach_bien_don_gia_va_bien_quy_doi",
                   _migrate_tach_bien_don_gia_va_bien_quy_doi))


def _migrate_go_dau_viec_mac_dinh(db: Session) -> None:
    """Gỡ `cong_doan_dau_viec.is_default` — cột radio "Mặc định" ở bảng đầu việc của công đoạn.

    Nó chọn hộ đầu việc nào điền sẵn khi lập lệnh. Chủ chốt bỏ 12/08/2026: cùng một công đoạn mà
    hai đầu việc khác nhau THẬT (bế TAY / bế MÁY · vào keo gáy vuông / khâu chỉ) thì chọn cái nào
    là quyết định theo HÀNG cụ thể, không phải hằng số khai một lần ở danh mục — đúng luật
    "máy chỉ ghi nhận, phán đoán để con người".

    Mất gì: 10 công đoạn đang có ≥2 đầu việc (Bế thành phẩm 3 · Bế nổi 3 · Xén 3 mặt 3 · Cán màng
    bóng/mờ · Gấp tay sách · Bắt tay+vào keo · Ép kim · Bồi sóng · Ghép màng metalize) từ nay
    KHÔNG tự điền đầu việc nữa — người lập lệnh chọn. Công đoạn có đúng 1 đầu việc vẫn tự điền.

    Best-effort: SQLite cũ có thể từ chối DROP COLUMN → cột mồ côi vô hại (model đã hết đọc nó).
    """
    insp = inspect(db.get_bind())
    if "cong_doan_dau_viec" not in set(insp.get_table_names()):
        return
    if "is_default" not in _existing_columns(insp, "cong_doan_dau_viec"):
        return
    try:
        db.execute(text("ALTER TABLE cong_doan_dau_viec DROP COLUMN is_default"))
        db.commit()
    except Exception:
        db.rollback()


MIGRATIONS.append(("0190_go_dau_viec_mac_dinh", _migrate_go_dau_viec_mac_dinh))


def _migrate_dau_viec_vat_tu(db: Session) -> None:
    """Nền BOM: đầu việc của công đoạn mang sẵn danh sách VẬT TƯ nó tiêu thụ.

    Bảng nối thuần, KHÔNG có cột số lượng — định mức tuỳ quy cách từng lệnh nên số khai ở danh mục
    là số chết. Số lượng suy lúc bung ở bước lệnh qua quy đổi động. Xem `CongDoanDauViecVatTu`.

    Kèm cờ `lsx_cong_doan_vat_tu.tu_dong`: dòng do máy bung (true) thì lần bung sau được thay; dòng
    người tự thêm hoặc đã sửa (false) thì máy chừa ra, không ghi đè công sức người ta vừa chỉnh.
    """
    insp = inspect(db.get_bind())
    id_pk = "INTEGER PRIMARY KEY" if db.get_bind().dialect.name == "sqlite" else "SERIAL PRIMARY KEY"
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS cong_doan_dau_viec_vat_tu ("
        f"id {id_pk}, "
        "cong_doan_dau_viec_id INTEGER NOT NULL "
        "REFERENCES cong_doan_dau_viec(id) ON DELETE CASCADE, "
        "vat_tu_id INTEGER NOT NULL, thu_tu INTEGER NOT NULL DEFAULT 0, "
        "UNIQUE(cong_doan_dau_viec_id, vat_tu_id))"
    ))
    if "lsx_cong_doan_vat_tu" in set(insp.get_table_names()):
        if "tu_dong" not in _existing_columns(insp, "lsx_cong_doan_vat_tu"):
            db.execute(text(
                "ALTER TABLE lsx_cong_doan_vat_tu "
                "ADD COLUMN tu_dong BOOLEAN NOT NULL DEFAULT false"
            ))
    db.commit()


MIGRATIONS.append(("0191_dau_viec_vat_tu", _migrate_dau_viec_vat_tu))


def _migrate_don_vi_cach_do(db: Session) -> None:
    """`don_vi_do.cong_thuc` — CÁCH ĐO, công thức định nghĩa chính đơn vị đó.

        m² tờ in  :=  dai_in * rong_in * to_sau_in

    Đây là nguồn số lượng của BOM: vật tư khai ĐVT là đơn vị nào thì lúc bung ở bước lệnh, máy chạy
    công thức của đơn vị ấy với quy cách của lệnh. Mỗi đơn vị đúng MỘT cách đo nên không có gì để
    chọn nhầm.

    ĐỪNG nhầm với hai thứ đã có: `don_vi_quy_doi.cong_thuc` nối HAI đơn vị ("1 tờ = … kg"), còn ô
    công thức ở Giấy · Vật tư khác · Công đoạn ra TIỀN. Cột này ra LƯỢNG và không nối với ai.
    """
    insp = inspect(db.get_bind())
    if "don_vi_do" not in set(insp.get_table_names()):
        return
    if "cong_thuc" in _existing_columns(insp, "don_vi_do"):
        return
    db.execute(text("ALTER TABLE don_vi_do ADD COLUMN cong_thuc VARCHAR(200)"))
    db.commit()


MIGRATIONS.append(("0192_don_vi_cach_do", _migrate_don_vi_cach_do))


def _migrate_ky_thuat_bao_tri_nguoi_nhan(db: Session) -> None:
    """`ky_thuat_bao_tri.nguoi_thuc_hien_id` — người NHẬN việc, lấy từ tài khoản đăng nhập.

    Vì sao cần migration cho một bảng vừa dựng hôm qua: bảng `ky_thuat_*` sinh bằng `create_all`
    nên nó ĐÃ tồn tại trên Postgres dev từ lần chạy uvicorn đầu tiên. `create_all` chỉ TẠO bảng,
    không ALTER — thêm cột mà không có migration thì code đọc một đằng, DB có một nẻo, và test
    SQLite (drop/create mỗi lần) vẫn xanh nên không ai phát hiện.

    Ô "Người / đơn vị thực hiện" gõ tay đã bỏ khỏi form (chủ chốt 12/08/2026). Cột chữ
    `nguoi_thuc_hien` GIỮ LẠI làm tên snapshot — người nghỉ việc rồi vẫn tra được ai đã làm.
    """
    insp = inspect(db.get_bind())
    if "ky_thuat_bao_tri" not in set(insp.get_table_names()):
        return  # DB trắng: `create_all` dựng bảng đã có sẵn cột, không phải ALTER gì
    if "nguoi_thuc_hien_id" not in _existing_columns(insp, "ky_thuat_bao_tri"):
        db.execute(text("ALTER TABLE ky_thuat_bao_tri ADD COLUMN nguoi_thuc_hien_id INTEGER"))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_ky_thuat_bao_tri_nguoi_thuc_hien_id "
            "ON ky_thuat_bao_tri (nguoi_thuc_hien_id)"
        ))
    db.commit()


MIGRATIONS.append(("0192_ky_thuat_bao_tri_nguoi_nhan", _migrate_ky_thuat_bao_tri_nguoi_nhan))


def _migrate_bo_trang_thai_dang_thuc_hien(db: Session) -> None:
    """Bảo trì bỏ nấc `dang_thuc_hien` (chủ chốt 12/08/2026) — phiếu đang kẹt ở đó phải về hàng chờ.

    Trạng thái lưu bằng CHUỖI nên DB không tự chặn giá trị lạ: không dọn thì phiếu cũ mang một
    trạng thái không còn trong `TRANG_THAI_BAO_TRI`, tab nào cũng không khớp và nó biến mất khỏi
    mọi bộ lọc — người dùng thấy phiếu "bốc hơi" mà không có lỗi nào bật ra.

    Nhả luôn người nhận: người làm nay là người bấm XÁC NHẬN XONG, phiếu còn dở thì không mang tên ai.
    """
    insp = inspect(db.get_bind())
    if "ky_thuat_bao_tri" not in set(insp.get_table_names()):
        return
    db.execute(text(
        "UPDATE ky_thuat_bao_tri "
        "SET trang_thai = 'cho_thuc_hien', nguoi_thuc_hien_id = NULL, nguoi_thuc_hien = NULL "
        "WHERE trang_thai = 'dang_thuc_hien'"
    ))
    db.commit()


MIGRATIONS.append(("0193_bao_tri_bo_dang_thuc_hien", _migrate_bo_trang_thai_dang_thuc_hien))


def _migrate_vat_tu_cong_thuc_luong(db: Session) -> None:
    """Vật tư có ô CÔNG THỨC LƯỢNG riêng, tách khỏi công thức GIÁ (13/08/2026).

    `cong_thuc_gia` ra TIỀN cho phiếu tính giá; cột mới ra LƯỢNG cho BOM ở bước lệnh. Trước đó lượng
    chỉ suy được khi ĐƠN VỊ của vật tư mang công thức — mà `kg` dùng chung cho keo · mực · giấy nên
    không gắn được, buộc phải đẻ `kg_keo`/`kg_giay_to_in`… rồi kho và mua hàng phải nhìn mấy cái tên
    đó thay vì `kg` thật.
    """
    insp = inspect(db.get_bind())
    if "vat_tu_in_an" not in set(insp.get_table_names()):
        return
    if "cong_thuc_luong" in _existing_columns(insp, "vat_tu_in_an"):
        return
    db.execute(text("ALTER TABLE vat_tu_in_an ADD COLUMN cong_thuc_luong TEXT"))
    db.commit()


MIGRATIONS.append(("0194_vat_tu_cong_thuc_luong", _migrate_vat_tu_cong_thuc_luong))


def _migrate_giay_cong_thuc_luong(db: Session) -> None:
    """Giấy có ô CÔNG THỨC LƯỢNG riêng — vế còn lại của mg 0194 (vật tư khác đã có).

    Có cột này thì giấy khai ĐVT `kg` THẬT rồi tự tính ra kg, khỏi đi vòng qua cạnh quy đổi động
    `tờ → kg`. Cạnh đó là chỗ duy nhất còn giữ "công thức mà lại có đích" — chủ chốt 13/08/2026 là
    vô lý, nhưng chưa xoá được vì kế hoạch vật tư đang sống nhờ nó. Khai xong ở đây thì xoá được.
    """
    insp = inspect(db.get_bind())
    if "giay_nguyen" not in set(insp.get_table_names()):
        return
    if "cong_thuc_luong" in _existing_columns(insp, "giay_nguyen"):
        return
    db.execute(text("ALTER TABLE giay_nguyen ADD COLUMN cong_thuc_luong TEXT"))
    db.commit()


MIGRATIONS.append(("0195_giay_cong_thuc_luong", _migrate_giay_cong_thuc_luong))


def _migrate_cong_doan_he_so_ngoai_dong(db: Session) -> None:
    """Hệ số vào→ra cho bước NGOÀI dòng giấy (14/08/2026).

    Trên dòng giấy hệ số suy từ quy cách lệnh (bình bài · mảnh xả · số tay). Ngoài dòng không có
    gì nói "1 bài ra mấy kẽm" nên người khai — và chỉ khi hai đơn vị khác nhau.
    """
    insp = inspect(db.get_bind())
    if "cong_doan" not in set(insp.get_table_names()):
        return
    if "he_so_ngoai_dong" in _existing_columns(insp, "cong_doan"):
        return
    db.execute(text("ALTER TABLE cong_doan ADD COLUMN he_so_ngoai_dong NUMERIC(18,6)"))
    db.commit()


MIGRATIONS.append(("0196_cong_doan_he_so_ngoai_dong", _migrate_cong_doan_he_so_ngoai_dong))


def _migrate_giay_dien_cong_thuc_luong(db: Session) -> None:
    """Điền CÔNG THỨC LƯỢNG mặc định cho giấy — vế còn lại của việc gỡ quy đổi động (14/08/2026).

    Bốn cặp động (`tờ → kg`, `tờ → m²`, `tờ → cái`, `tờ nguyên → kg`) đã gỡ khỏi seed. Chỗ duy nhất
    ngoài lệnh còn sống nhờ chúng là **Kế hoạch vật tư — mua giấy theo cân**: nó cần đổi số tờ nguyên
    sang kg. Nay giấy tự khai công thức lượng, ra thẳng kg, khỏi đi vòng qua cặp.

    Công thức KHÔNG phải phỏng đoán — đó là định nghĩa cân của giấy:

        kg  =  định lượng (kg/m²)  ×  dài tờ nguyên (m)  ×  rộng tờ nguyên (m)  ×  số tờ nguyên

    ⚠️ CÔNG THỨC PHẢI KHỚP ĐƠN VỊ BÁN, mỗi đơn vị một chuỗi riêng. `_ve_goc` đọc kết quả là số theo
    ĐÚNG `don_vi_gia` của mặt hàng (`so_luong, dvt = safe_eval(ct), goc`) — dán chuỗi ra kg lên giấy
    bán theo TẤN là mua thừa 1.000 lần, mà bảng cân đối vẫn nhìn hợp lý. Bản đầu của migration này
    gộp cả kg/g/tấn vào một chuỗi; sửa 14/08/2026 trước khi có dòng nào dính (DB dev 5/5 giấy đều
    bán theo kg, đã đếm).

    Chỉ điền cho dòng CHƯA khai (`IS NULL`) — người dùng sửa rồi thì không đè. Và chỉ cho giấy bán
    theo CÂN hoặc theo TỜ; đơn vị khác thì để trống, dòng đó nhận "chưa tính được lượng" — đúng hơn
    là bịa một công thức sai đơn vị.

    Khổ/định lượng lấy theo thứ tự LỆNH trước, danh mục sau (`_quy_cach_cua`), nên giấy không khai
    khổ ở danh mục vẫn ra số khi lệnh có khổ.
    """
    insp = inspect(db.get_bind())
    if "giay_nguyen" not in set(insp.get_table_names()):
        return
    cols = _existing_columns(insp, "giay_nguyen")
    if "cong_thuc_luong" not in cols or "don_vi_gia" not in cols:
        return
    CAN = "dinh_luong * dai_nguyen * rong_nguyen * to_nguyen"
    for dvs, ct in ((("kg",), CAN), (("g",), f"{CAN} * 1000"), (("tan",), f"{CAN} / 1000"),
                    (("to", "to_nguyen"), "to_nguyen")):
        db.execute(
            text("UPDATE giay_nguyen SET cong_thuc_luong = :ct "
                 "WHERE cong_thuc_luong IS NULL AND lower(don_vi_gia) = ANY(:dvs)")
            if db.get_bind().dialect.name != "sqlite" else
            text("UPDATE giay_nguyen SET cong_thuc_luong = :ct "
                 f"WHERE cong_thuc_luong IS NULL AND lower(don_vi_gia) IN ({','.join(repr(d) for d in dvs)})"),
            {"ct": ct, "dvs": list(dvs)},
        )
    db.commit()


MIGRATIONS.append(("0197_giay_dien_cong_thuc_luong", _migrate_giay_dien_cong_thuc_luong))


def _migrate_go_quy_doi_dong(db: Session) -> None:
    """Gỡ QUY ĐỔI ĐỘNG — cột `don_vi_quy_doi.cong_thuc` (mg 0137 dựng lên, nay chết).

    Vì sao bỏ: cặp mang công thức nghĩa là "1 tờ = f(chip) kg". Một đơn vị đích có thể tới từ nhiều
    đường (`tờ → kg`, `tờ nguyên → kg`, `con → kg`) ⇒ lúc bung BOM máy không biết chọn đường nào, mà
    ba đường cho ba số khác nhau. Mô hình thay thế đã chạy: CÁCH ĐO khai ở CHÍNH đơn vị
    (`don_vi_do.cong_thuc`, mg 0192) và trả thẳng LƯỢNG của cả lệnh; giấy/vật tư có công thức riêng
    đè lên (`giay_nguyen.cong_thuc_luong` mg 0195 + 0197, `vat_tu_in_an.cong_thuc_luong` mg 0194).

    Hai việc, theo thứ tự:

    1. **Xoá dòng động mồ côi** — dòng có công thức thì `he_so` lưu 0, tức sau khi gỡ code nó là cặp
       "1 tờ = 0 kg": không đường quy đổi nào dùng được (`cap_map` bỏ qua `he_so <= 0`) nhưng vẫn
       hiện ở màn Đơn vị. Dòng vừa có công thức VỪA có `he_so > 0` thì GIỮ — nó là cặp số hợp lệ,
       chỉ mất phần công thức. DB dev hôm nay: 0 dòng động / 6 cặp (đã đếm trước khi viết).
    2. **DROP COLUMN**, best-effort: SQLite cũ từ chối thì cột mồ côi vô hại vì model đã hết map nó.
    """
    insp = inspect(db.get_bind())
    if "don_vi_quy_doi" not in set(insp.get_table_names()):
        return
    if "cong_thuc" not in _existing_columns(insp, "don_vi_quy_doi"):
        return
    db.execute(text(
        "DELETE FROM don_vi_quy_doi "
        "WHERE cong_thuc IS NOT NULL AND trim(cong_thuc) <> '' "
        "AND (he_so IS NULL OR he_so <= 0)"
    ))
    db.commit()
    try:
        db.execute(text("ALTER TABLE don_vi_quy_doi DROP COLUMN cong_thuc"))
        db.commit()
    except Exception:
        db.rollback()


MIGRATIONS.append(("0198_go_quy_doi_dong", _migrate_go_quy_doi_dong))


def _migrate_go_be_mat_tho_chung_loai_giay(db: Session) -> None:
    """Gỡ `chung_loai_giay.be_mat` + `.tho_mac_dinh` — chủ dự án yêu cầu 15/08/2026.

    ĐẾM TRƯỚC KHI GỠ (DB dev, qua API, ngay trước khi viết hàm này):

      | cột            | có dữ liệu | ai ĐỌC                                        |
      |----------------|-----------|-----------------------------------------------|
      | `be_mat`       | 6/6       | chỉ hiện trên bảng + `_validate` của chính nó  |
      | `tho_mac_dinh` | 0/6       | không ai                                       |

    ⚠️ MẤT DỮ LIỆU, KHÔNG ĐẢO LẠI: `be_mat` đang có giá trị ở cả 6 dòng ("bong"/"mo"/"nham").
    Mất nó là mất chữ Bóng/Mờ/Nhám trên bảng Chủng loại giấy — KHÔNG engine nào đọc để tính, nên
    không phiếu nào đổi số. `tho_mac_dinh` rỗng sạch; đừng nhầm với `giay_nguyen.tho` (thớ của
    TỪNG loại giấy) — cột đó KHÔNG đụng tới, vẫn dùng cho bình bài.

    KHÔNG gỡ `cong_thuc_luong` ở đây dù cùng đợt yêu cầu — xem ghi chú ở
    `models/vat_lieu_kho.GiayNguyen.cong_thuc_luong`: nó là thứ DUY NHẤT còn đổi được tờ → kg
    sau khi mg 0198 gỡ cặp quy đổi động, và bảng cặp hiện không có cầu `to → kg` nào
    (đã soi: chỉ `kg→g`, `ram→to`, `tan→kg`).

    DROP COLUMN best-effort: SQLite đời cũ từ chối thì cột mồ côi vô hại — model đã hết map nó.
    """
    insp = inspect(db.get_bind())
    if "chung_loai_giay" not in set(insp.get_table_names()):
        return
    for cot in ("be_mat", "tho_mac_dinh"):
        if cot not in _existing_columns(insp, "chung_loai_giay"):
            continue
        try:
            db.execute(text(f"ALTER TABLE chung_loai_giay DROP COLUMN {cot}"))
            db.commit()
        except Exception:
            db.rollback()


MIGRATIONS.append(("0199_go_be_mat_tho_chung_loai_giay", _migrate_go_be_mat_tho_chung_loai_giay))


def _migrate_go_o_bu_hao_nhap_tay(db: Session) -> None:
    """Gỡ HAI ô nhập hao bằng tay — chủ dự án yêu cầu 15/08/2026.

      | cột                              | ô trên màn                   | có dữ liệu |
      |----------------------------------|------------------------------|-----------|
      | `phieu_thanh_phan.bu_hao_so_to`  | Phiếu tính giá · "+ Bù thêm" | 0/7 phiếu |
      | `lsx.bu_hao_to`                  | Lệnh SX · "Hao hụt thêm"     | 0/3 lệnh  |

    (Đếm qua API trên DB dev ngay trước khi viết hàm này.)

    VÌ SAO GỠ chứ không sửa: ô của phiếu tính giá cộng một con số TỜ vào cả `vao` lẫn `ra` của MỌI
    bước mà không nhìn đơn vị — bước đếm cuốn nhận thêm 100 *tờ* thành 100 *cuốn*, nên hao hiện ra
    ÂM và đơn 500 cuốn hoá 600. Ô bên lệnh SX thì làm đúng (cộng vào bước cuối, có nhãn đơn vị),
    nhưng giữ một ô đúng và một ô sai cho cùng một khái niệm là để người dùng tự đoán màn nào tin
    được. Nay cả hệ còn MỘT đường khai hao: định mức của chính công đoạn trong danh mục Công đoạn —
    chỗ đó biết bước ấy đếm bằng gì nên quy ra giấy đúng cầu.

    KHÔNG đụng `lsx_cong_doan.hao_hut` / `.hao_hut_pct`: đó là số DẪN XUẤT do chuỗi ngược ghi, và
    `bai_ghep_service` đang đọc để chuyển hao lên bài chung. Cũng KHÔNG đụng `LsxPreviewLine.bu_hao_to`
    (số máy tự tra, chỉ để hiển thị ở màn xem trước) — trùng tên, khác thứ.

    DROP COLUMN best-effort: SQLite đời cũ từ chối thì cột mồ côi vô hại — model đã hết map nó.
    """
    insp = inspect(db.get_bind())
    ten_bang = set(insp.get_table_names())
    for bang, cot in (("phieu_thanh_phan", "bu_hao_so_to"), ("lsx", "bu_hao_to")):
        if bang not in ten_bang or cot not in _existing_columns(insp, bang):
            continue
        try:
            db.execute(text(f"ALTER TABLE {bang} DROP COLUMN {cot}"))
            db.commit()
        except Exception:
            db.rollback()


MIGRATIONS.append(("0200_go_o_bu_hao_nhap_tay", _migrate_go_o_bu_hao_nhap_tay))


def _migrate_go_hai_cot_hao_chet(db: Session) -> None:
    """Gỡ nốt HAI cột hao đã chết từ lâu ở `phieu_thanh_phan` — chủ dự án yêu cầu 15/08/2026.

      | cột             | ô trên màn              | tình trạng                                  |
      |-----------------|-------------------------|---------------------------------------------|
      | `hao_so_to`     | "− Hao"                 | ô gỡ khỏi UI từ trước; engine trả `hao_tay`=0 |
      | `tinh_bu_hao_cd`| nút bật/tắt bù hao tự   | nút gỡ khỏi UI từ trước; engine LUÔN tính chuỗi |

    Cả hai đã ngưng-đọc từ lâu (xem chú thích cũ ở `models/phieu_tinh_gia`), chỉ còn đi nhờ DTO
    giữa hai tầng — tức chúng vẫn hiện trong payload và trong OpenAPI như thể còn tác dụng.

    Đây là bước SAU của `0200`: gỡ xong ba ô nhập tay thì khối "Số tờ tự tính" của phiếu tính giá
    do máy tính TRỌN VẸN, không còn ô nào để hai người gõ hai số khác nhau trên cùng một phiếu.

    ⚠️ Danh sách cột dưới đây có CẢ `bu_hao_so_to` — đáng lẽ `0200` rút nó, nhưng `0200` gõ nhầm
    tên bảng (`phieu_tinh_gia_component`, không tồn tại) nên guard "bảng không có" nuốt mất trong
    im lặng. `0200` đã chạy trên DB dev nên sửa tại chỗ không đủ — phải rút lại ở đây. (Tên trong
    `0200` cũng đã vá, để DB dựng mới không dính lỗi đó.)

    DROP COLUMN best-effort: SQLite đời cũ từ chối thì cột mồ côi vô hại — model đã hết map nó.
    """
    insp = inspect(db.get_bind())
    if "phieu_thanh_phan" not in set(insp.get_table_names()):
        return
    for cot in ("bu_hao_so_to", "hao_so_to", "tinh_bu_hao_cd"):
        if cot not in _existing_columns(insp, "phieu_thanh_phan"):
            continue
        try:
            db.execute(text(f"ALTER TABLE phieu_thanh_phan DROP COLUMN {cot}"))
            db.commit()
        except Exception:
            db.rollback()


MIGRATIONS.append(("0201_go_hai_cot_hao_chet", _migrate_go_hai_cot_hao_chet))


def _migrate_phi_khuon_buoc(db: Session) -> None:
    """`phieu_thanh_pham.phi_khuon` — phí làm khuôn của CHÍNH bước đó, khoản MỘT LẦN.

    Nghiệp vụ (thông lệ ngành in, đã đối chiếu tài liệu ngoài): tiền làm dao thu ở ĐƠN ĐẦU, dao
    giữ lại trong kho nhà in, ĐƠN TÁI ĐẶT không thu lại. Cùng kết cấu hộp mà chỉ khác hình in thì
    vẫn một con dao — nên "dùng lại" là ca phổ biến, không phải ngoại lệ.

    Vì sao gắn vào BƯỚC chứ không vào sản phẩm: cờ `requires_tooling` + `tooling_type` vốn khai ở
    DANH MỤC CÔNG ĐOẠN, nên tiền phải nằm cùng chỗ với cái cờ sinh ra nó. Một hộp có thể cần ba
    con dao (bế · ép nhũ · dập nổi) ở ba bước khác nhau, thợ báo giá từng con, và lúc tái đơn
    thường chỉ MỘT con phải làm lại — gộp một cục thì tới lúc đó không biết trừ ra bao nhiêu.

    ⚠️ KHÔNG cộng vào `gia_von_tp` và KHÔNG chia theo số lượng — xem chú thích ở model.

    Cột NOT NULL DEFAULT 0 nên dòng cũ tự về 0 = "không tính phí dao", đúng nghĩa cần.
    """
    insp = inspect(db.get_bind())
    if "phieu_thanh_pham" not in set(insp.get_table_names()):
        return
    if "phi_khuon" in _existing_columns(insp, "phieu_thanh_pham"):
        return
    db.execute(text(
        "ALTER TABLE phieu_thanh_pham ADD COLUMN phi_khuon NUMERIC(18,2) NOT NULL DEFAULT 0"
    ))
    db.commit()


MIGRATIONS.append(("0202_phi_khuon_buoc", _migrate_phi_khuon_buoc))


def _migrate_go_khach_hang_khuon_be(db: Session) -> None:
    """Gỡ `khuon_be.khach_hang` — chủ dự án yêu cầu 15/08/2026.

    ⚠️ MẤT DỮ LIỆU, KHÔNG ĐẢO LẠI: đếm trước khi gỡ (DB dev, qua màn danh mục) — **6/6 dòng đang
    có tên khách** ("Cty Kinh Đô", "Cty Minh Long", "Dược Hậu Giang", "Cty Vinamilk", "Shop An
    Nhiên", "Công ty TNHH An Phát"). Khác hẳn các cột gỡ ở `0200`/`0201` (0 dòng có dữ liệu).

    Không engine nào đọc cột này — nó chỉ hiện thành một cột trên bảng và một ô trong drawer. Nhưng
    nó CÓ nằm trong `search_fields` của repo, nên sau khi gỡ, gõ tên khách vào ô tìm sẽ không ra
    khuôn nào nữa; ô tìm còn mã · tên ấn phẩm · số kệ.

    Vì sao gỡ hợp lý: cột khai TAY, không nối danh mục Khách hàng, nên nó là bản chép tên dễ lệch —
    "Cty Kinh Đô" ở đây và "Công ty CP Kinh Đô" bên CRM là hai chuỗi khác nhau mà không chỗ nào
    đối chiếu. Khuôn nhận diện bằng MÃ + TÊN ấn phẩm; muốn biết của khách nào thì tra qua lệnh
    sản xuất đang dùng khuôn đó.

    DROP COLUMN best-effort: SQLite đời cũ từ chối thì cột mồ côi vô hại — model đã hết map nó.
    """
    insp = inspect(db.get_bind())
    if "khuon_be" not in set(insp.get_table_names()):
        return
    if "khach_hang" not in _existing_columns(insp, "khuon_be"):
        return
    try:
        db.execute(text("ALTER TABLE khuon_be DROP COLUMN khach_hang"))
        db.commit()
    except Exception:
        db.rollback()


MIGRATIONS.append(("0202_go_khach_hang_khuon_be", _migrate_go_khach_hang_khuon_be))


def _migrate_may_thiet_bi_active(db: Session) -> None:
    """`may_thiet_bi.active` — máy còn dùng hay đã thanh lý. Chủ dự án yêu cầu 15/08/2026.

    ĐỪNG NHẦM với `trang_thai` đã gỡ ở mg `0186`: cái cũ trộn ba nghĩa (đang chạy / bảo trì / đã
    nghỉ) và không có ô nhập nào. Cột này trả lời ĐÚNG MỘT câu — xưởng còn máy này không. Máy dừng
    TẠM vẫn `active=True`, khai bằng khoảng thời gian ở `machine_unavailable_periods`.

    VÌ SAO CẦN: màn Máy là màn danh mục DUY NHẤT không có cờ này, nên nó đứng ngoài luật xoá chung
    — bấm Xóa là xoá cứng, không có đường "ngừng dùng". Sau khi hộp thoại xoá chuyển sang hỏi
    `kiem-xoa` (15/08), màn này rơi vào ngõ cụt: hỏi thì 404, ngừng dùng cũng 404.

    Backfill: mọi máy đang có = còn dùng (`TRUE`). Không suy từ dữ liệu nào khác — không có nguồn
    nào đáng tin để đoán máy nào đã thanh lý, mà đoán sai là máy biến mất khỏi ô chọn của xếp lịch.
    """
    insp = inspect(db.get_bind())
    if "may_thiet_bi" not in set(insp.get_table_names()):
        return
    if "active" in _existing_columns(insp, "may_thiet_bi"):
        return
    db.execute(text("ALTER TABLE may_thiet_bi ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE"))
    db.commit()


MIGRATIONS.append(("0202_may_thiet_bi_active", _migrate_may_thiet_bi_active))


def _migrate_go_khuon_khoi_lenh(db: Session) -> None:
    """Gỡ HẲN khuôn khỏi lệnh sản xuất & xếp lịch — chủ dự án yêu cầu 16/08/2026.

    Đếm trước khi quyết (Postgres dev, không đoán):

      | thứ                                  | số thật |
      |--------------------------------------|---------|
      | bước lệnh có gán khuôn               | 0 / 14  |
      | lệnh còn giữ cột đời cũ              | 1 / 3   |
      | kho khuôn (danh mục)                 | 6 dòng  |

    0/14 ⇒ tính năng gán khuôn CHƯA AI DÙNG THẬT. Cùng lượt này gỡ luôn ba hộ tiêu thụ của nó:
    hai detector khuôn ở xếp lịch (trùng dao · dao chưa sẵn sàng), dòng so sánh "Khuôn bế" ở bảng
    ghép chung, và nhóm "Công cụ" ở kế hoạch vật tư. Nhóm Công cụ bỏ hẳn chứ không giữ nửa vời:
    không biết CON DAO NÀO thì không tra được tình trạng / ngày về, mà đó là toàn bộ giá trị của
    nó — phần còn lại ("bước này cần khuôn") routing đã nói rồi.

    CÒN LẠI, đừng gỡ nhầm:
      · `khuon_be` (kho khuôn) — vẫn khai/sửa được, nay là sổ tài sản đứng riêng.
      · `cong_doan.requires_tooling` / `tooling_type` — phiếu tính giá cần, để biết bước nào hỏi
        PHÍ khuôn (`phieu_thanh_pham.phi_khuon`, mg `0202`). Tiền dao KHÔNG bị đụng tới ở đây.

    Hệ quả: cửa chặn xoá khuôn (`danh_muc_tham_chieu._khuon_be`) hết thứ để đếm ⇒ xoá khuôn trong
    danh mục nay không còn bị chặn bởi lệnh nào.

    DROP COLUMN best-effort: SQLite đời cũ từ chối thì cột mồ côi vô hại — model đã hết map nó.
    """
    insp = inspect(db.get_bind())
    ten_bang = set(insp.get_table_names())
    for bang in ("lsx_cong_doan", "lsx"):
        if bang not in ten_bang:
            continue
        if "khuon_be_id" not in _existing_columns(insp, bang):
            continue
        try:
            db.execute(text(f"ALTER TABLE {bang} DROP COLUMN khuon_be_id"))
            db.commit()
        except Exception:
            db.rollback()


MIGRATIONS.append(("0203_go_khuon_khoi_lenh", _migrate_go_khuon_khoi_lenh))


# 13 nhãn từng VIẾT CỨNG trong `KhachHangPage.tsx` (`DEFAULT_TAG_PRESETS`). Chép nguyên văn sang
# đây làm dữ liệu mồi để mở màn lên KHÔNG mất gì so với trước — khác mỗi chỗ: nay xoá được.
NHAN_KHACH_MOI = (
    "VIP", "Ưu tiên", "Đối tác lâu năm", "Tiềm năng cao", "Tái ký HĐ", "Trả đúng hạn",
    "Ưa giao nhanh", "Chuộng mẫu đẹp", "Bao bì cao cấp", "Cần chăm sóc", "Nhạy giá",
    "Khó tính", "Hay trễ hẹn",
)


def _migrate_kho_nhan_khach(db: Session) -> None:
    """Mồi kho nhãn khách (`customer_tag_catalog`) — chủ dự án yêu cầu 16/08/2026.

    Bảng do `create_all` tự dựng (dự án không Alembic; `create_all` TẠO bảng thiếu). Việc của
    migration này chỉ là ĐỔ 13 nhãn mồi.

    Guard là "bảng RỖNG HOÀN TOÀN", không phải "thiếu nhãn nào thì thêm nhãn đó". Khác biệt quan
    trọng: yêu cầu của chủ dự án là XOÁ ĐƯỢC nhãn. Nếu guard theo từng nhãn thì lần khởi động sau
    seeder mọc lại đúng nhãn vừa xoá — xoá xong tưởng xong, restart một phát nó về. Rỗng-mới-mồi
    nghĩa là chỉ rót đúng MỘT lần, ở lần đầu tiên.

    Nhãn đã gán cho khách (`customer_tags`) KHÔNG đụng tới: hai bảng nối nhau bằng chuỗi `label`,
    không khoá ngoại, nên khách đang mang nhãn nào thì giữ nguyên nhãn đó.
    """
    insp = inspect(db.get_bind())
    if "customer_tag_catalog" not in set(insp.get_table_names()):
        return
    if db.execute(text("SELECT count(*) FROM customer_tag_catalog")).scalar():
        return
    for nhan in NHAN_KHACH_MOI:
        db.execute(
            text("INSERT INTO customer_tag_catalog (label, created_at) VALUES (:l, :t)"),
            {"l": nhan, "t": datetime.now(timezone.utc)},
        )
    db.commit()


MIGRATIONS.append(("0204_kho_nhan_khach", _migrate_kho_nhan_khach))


def _migrate_noi_khuon_vao_buoc_lenh(db: Session) -> None:
    """Nối danh mục Khuôn vào bước lệnh sản xuất — chủ dự án chốt 16/08/2026.

    Ba cột:
      · `khuon_be.khach_hang_id` — FK khách đặt con dao. KHÁC cột `khach_hang` chuỗi đã xoá
        15/08: cột cũ gõ tay nên "Cty An Phát" ≠ "Công ty TNHH An Phát", lọc ra thiếu rồi người
        ta tưởng chưa có dao và đặt làm con thứ hai.
      · `khuon_be.loai` — bế / ép nhũ, cùng bộ mã với `cong_doan.tooling_type` để ô chọn lọc bằng
        phép so thẳng. Thiếu nó thì bước Ép nhũ thấy cả dao bế.
      · `lsx_cong_doan.khuon_be_id` — DỰNG LẠI cột mg `0203` vừa xoá sáng nay.

    ⚠️ Vì sao dựng lại thứ vừa xoá: `0203` xoá đúng — 0/14 bước có gán khuôn. Nhưng nguyên nhân là
    HÌNH DẠNG của ô chứ không phải nhu cầu: nó là select trống, mở ra danh sách rỗng, không có
    đường tạo dao mới, nên ai cũng bỏ qua. Bản dựng lại hỏi hai nhánh (dùng dao có sẵn / làm dao
    mới) và lọc sẵn theo khách + loại, tức có lối đi cho CẢ HAI câu trả lời.
    Không mất dữ liệu: cột cũ rỗng hoàn toàn khi bị xoá.

    ADD COLUMN best-effort trên từng cột — DB đã có sẵn cột nào thì bỏ qua cột đó.
    """
    insp = inspect(db.get_bind())
    ten_bang = set(insp.get_table_names())
    them = [
        ("khuon_be", "khach_hang_id", "INTEGER"),
        ("khuon_be", "loai", "VARCHAR(16)"),
        ("lsx_cong_doan", "khuon_be_id", "INTEGER"),
    ]
    for bang, cot, kieu in them:
        if bang not in ten_bang or cot in _existing_columns(insp, bang):
            continue
        db.execute(text(f"ALTER TABLE {bang} ADD COLUMN {cot} {kieu}"))
        db.commit()

    # Backfill `loai` nằm ở mg `0206` — KHÔNG gộp vào đây. Xem lý do ở đó: bản đầu viết chung một
    # hàm và chết vì Inspector cache.


MIGRATIONS.append(("0205_noi_khuon_vao_buoc_lenh", _migrate_noi_khuon_vao_buoc_lenh))


def _migrate_doan_loai_khuon(db: Session) -> None:
    """Đoán `khuon_be.loai` cho các dòng khai TRƯỚC mg `0205`, dựa vào TÊN dao.

    ⚠️ VÌ SAO LÀ MỘT MIGRATION RIÊNG — đây là bài học, đừng lặp lại:

    Bản đầu viết backfill này ngay trong `0205`, ngay sau vòng `ALTER TABLE ADD COLUMN`, và gác
    bằng `if "loai" in _existing_columns(insp, "khuon_be")` — dùng lại chính `insp` tạo ở ĐẦU hàm.

    `Inspector` CACHE kết quả reflection (`info_cache`). Cái tạo trước `ALTER` vẫn báo danh sách
    cột CŨ mãi mãi, nên guard luôn ra `False` và cả khối backfill bị bỏ qua — không lỗi, không log,
    migration vẫn ghi "đã chạy". Đo lại trên DB dev: 6/6 dòng còn `loai IS NULL` trong khi câu SQL
    hoàn toàn đúng (Postgres khớp cả 6 với `lower(ten) LIKE '%bế%'`).

    Hai cách chữa: tạo inspector MỚI sau vòng ALTER, hoặc tách ra hàm riêng như đây. Chọn cách sau
    vì `0205` đã chạy trên DB dev rồi — sửa tại chỗ thì nó không chạy lại, dữ liệu vẫn hỏng.

    LUẬT ĐOÁN: chỉ nhận khi TÊN nói rõ. "cái nào không ép thì là bế" nghe hợp lý nhưng sai với dao
    dập nổi / dao cắt — mà đoán sai ở đây là ô chọn dao LỌC MẤT con dao đúng, tệ hơn để trống (để
    trống thì dao vẫn hiện ở mọi loại bước).
    """
    insp = inspect(db.get_bind())
    if "khuon_be" not in set(insp.get_table_names()):
        return
    if "loai" not in _existing_columns(insp, "khuon_be"):
        return
    db.execute(text(
        "UPDATE khuon_be SET loai = 'khuon_ep' "
        "WHERE loai IS NULL AND (lower(ten) LIKE '%ép%' OR lower(ten) LIKE '%ep nhu%')"
    ))
    db.execute(text(
        "UPDATE khuon_be SET loai = 'khuon_be' "
        "WHERE loai IS NULL AND lower(ten) LIKE '%bế%'"
    ))
    db.commit()


MIGRATIONS.append(("0206_doan_loai_khuon", _migrate_doan_loai_khuon))


def _migrate_go_ngay_lam_khuon(db: Session) -> None:
    """Gộp hai ô ngày của kho khuôn về MỘT — chủ dự án yêu cầu 16/08/2026.

    Màn Khuôn đang có hai ô ngày sát nhau mà người khai phải tự đoán điền cái nào:
      · `ngay_lam_khuon`   — "Ngày làm khuôn"  (dao làm xong lúc nào)
      · `ngay_ve_du_kien`  — "Ngày có khuôn"   (dao nằm trong tay lúc nào)
    Với một con dao đã có thì hai câu đó là MỘT. Giữ cả hai là mời người ta khai lệch, rồi màn
    phải đoán hiển thị ô nào — chính chỗ đã phải viết một nhánh `if tinh_trang == 'dang_dat_lam'`
    trong cột bảng.

    Đo trước khi gộp (Postgres dev): 7 dòng — 6 có `ngay_lam_khuon`, 1 có `ngay_ve_du_kien`,
    **0 dòng có CẢ HAI**, 0 dòng trống cả hai. Hai cột bổ khuyết nhau hoàn hảo ⇒ chép sang là
    không mất và không đè số nào.

    CHÉP TRƯỚC, DROP SAU — và chỉ chép vào ô còn trống, để nếu có dòng nào lỡ khai cả hai thì giá
    trị người dùng nhập ở ô "có khuôn" thắng, không bị ngày làm ghi đè.
    """
    insp = inspect(db.get_bind())
    if "khuon_be" not in set(insp.get_table_names()):
        return
    cot = _existing_columns(insp, "khuon_be")
    if "ngay_lam_khuon" not in cot:
        return
    if "ngay_ve_du_kien" in cot:
        db.execute(text(
            "UPDATE khuon_be SET ngay_ve_du_kien = ngay_lam_khuon "
            "WHERE ngay_ve_du_kien IS NULL AND ngay_lam_khuon IS NOT NULL"
        ))
        db.commit()
    try:
        db.execute(text("ALTER TABLE khuon_be DROP COLUMN ngay_lam_khuon"))
        db.commit()
    except Exception:
        db.rollback()


MIGRATIONS.append(("0207_go_ngay_lam_khuon", _migrate_go_ngay_lam_khuon))


def _migrate_giu_cho_vat_tu(db: Session) -> None:
    """GIỮ CHỖ vật tư — bảng `vat_tu_giu_cho` + hai cờ công tắc. Chủ chốt 17/08/2026.

    Trước đó bảng cân đối CHỈ ĐỌC, tồn không thuộc về ai: lệnh A xếp lịch dựa trên 60 kg đang có,
    hôm sau lệnh B lĩnh mất 50 kg, lịch của A thành lịch ma mà không ai báo. Bảng này là chỗ tồn
    được đặt chỗ, và `tồn tự do = tồn − Σ đã giữ` mới là số kho cho người khác lĩnh.

    Ba thứ:
      · bảng `vat_tu_giu_cho` — (mặt hàng, số lượng) theo ĐƠN VỊ GỐC, chủ thể là lệnh HOẶC bài;
      · `lsx.giu_cho_bat` · `bai_ghep.giu_cho_bat` — công tắc "đã đăng ký giữ".

    ⚠️ Cờ Boolean dùng `FALSE` chứ KHÔNG phải `'0'`: chuỗi '0' chạy được trên SQLite nhưng VỠ khi
    Postgres tạo bảng trắng (bẫy đã ghi ở CLAUDE.md).

    ⚠️ Bảng tạo bằng `create_all` ở đường thường; hàm này chỉ lo DB đã có sẵn (dev/prod) — nơi
    `create_all` chỉ TẠO chứ không ALTER. `CREATE TABLE IF NOT EXISTS` để chạy lại vô hại.

    Cố ý KHÔNG có `UNIQUE` trên (chủ thể, mặt hàng): một chủ thể có thể giữ CÙNG một mặt hàng từ
    HAI nguồn — phần đã nằm trong kho và phần bám vào lô đang về (hai ngày về khác nhau thì hai
    dòng). Ép unique là ép gộp hai thứ có ràng buộc lịch khác hẳn nhau.
    """
    insp = inspect(db.get_bind())
    ten_bang = set(insp.get_table_names())

    if "vat_tu_giu_cho" not in ten_bang:
        db.execute(text(
            "CREATE TABLE IF NOT EXISTS vat_tu_giu_cho ("
            " id SERIAL PRIMARY KEY,"
            " hang_loai VARCHAR(8) NOT NULL,"
            " hang_id INTEGER NOT NULL,"
            " lsx_id INTEGER REFERENCES lsx(id) ON DELETE CASCADE,"
            " bai_ghep_id INTEGER REFERENCES bai_ghep(id) ON DELETE CASCADE,"
            " so_luong NUMERIC(14,2) NOT NULL,"
            " nguon VARCHAR(10) NOT NULL DEFAULT 'kho',"
            " ngay_ve DATE,"
            " created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            " CONSTRAINT ck_giu_cho_mot_chu_the CHECK ("
            "   (lsx_id IS NOT NULL AND bai_ghep_id IS NULL)"
            "   OR (lsx_id IS NULL AND bai_ghep_id IS NOT NULL)),"
            " CONSTRAINT ck_giu_cho_so_duong CHECK (so_luong > 0))"
        ))
        db.commit()
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_giu_cho_hang"
            " ON vat_tu_giu_cho (hang_loai, hang_id)"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vat_tu_giu_cho_lsx_id ON vat_tu_giu_cho (lsx_id)"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vat_tu_giu_cho_bai_ghep_id"
            " ON vat_tu_giu_cho (bai_ghep_id)"
        ))
        db.commit()

    for bang in ("lsx", "bai_ghep"):
        if bang not in ten_bang:
            continue
        # Inspector MỚI mỗi vòng: SQLAlchemy CACHE reflection, dùng lại bản cũ sau ALTER thì guard
        # luôn trả kết quả cũ và khối bị bỏ qua trong im lặng (đúng bẫy đã làm chết mg `0205`).
        if "giu_cho_bat" in _existing_columns(inspect(db.get_bind()), bang):
            continue
        db.execute(text(
            f"ALTER TABLE {bang} ADD COLUMN giu_cho_bat BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        db.commit()


MIGRATIONS.append(("0208_giu_cho_vat_tu", _migrate_giu_cho_vat_tu))


# Màn nào tách ra khoá nào, tách khỏi khoá cũ nào. Cùng khuôn 0177 (Thu mua) / 0178 (Kế toán).
#
# KHÁC 0178 ở một điểm: đợt này KHÔNG đổi nghĩa động từ nào cả. `read/create/update` của bốn màn
# mới mang đúng nghĩa cũ, nên chép NGUYÊN XI là đúng — không cần bảng ánh xạ cột nguồn→đích.
_TACH_SAN_XUAT = (
    # (khoá mới, nhãn, khoá cũ đang gác màn đó)
    ("ke_hoach_vat_tu", "Kế hoạch vật tư", "san_xuat"),
    ("bai_ghep", "Bài ghép", "san_xuat"),
    ("xep_lich", "Xếp lịch công đoạn", "san_xuat"),
    ("phieu_bao_tri", "Phiếu bảo trì", "ky_thuat_may"),
)


def _migrate_tach_module_san_xuat(db) -> None:
    """Tách khối Sản xuất thành 6 màn = 6 ô quyền (chủ chốt 17/08/2026).

    Trước: 6 mục menu treo trên ĐÚNG HAI khoá. `san_xuat` mở 4 màn (Kế hoạch SX · Kế hoạch vật tư ·
    Bài ghép · Xếp lịch công đoạn), `ky_thuat_may` mở 2 màn (Sửa chữa máy · Phiếu bảo trì). Không
    có cách nào cho một người xem lệnh mà không dời được lịch cả xưởng, hay xem bài ghép mà không
    thấy giá vật tư.

    Sau: mỗi màn một khoá. Hai khoá cũ GIỮ NGUYÊN TÊN nhưng thu hẹp nghĩa còn đúng một màn —
    `san_xuat` = Kế hoạch sản xuất, `ky_thuat_may` = Sửa chữa máy. Đổi tên khoá cũ là mọi hàng
    `role_permissions` đang có trỏ vào hư không ⇒ mất quyền hàng loạt, nên KHÔNG đổi.

    ⚠️ BƯỚC SAO CHÉP LÀ BẮT BUỘC, KHÔNG PHẢI "cho lành". Thiếu nó thì ngay lần deploy kế tiếp mọi
    vai đang có `san_xuat` mất sạch 3 màn và `ky_thuat_may` mất màn Phiếu bảo trì — sáng hôm sau bộ
    phận kế hoạch mở máy lên là trắng menu.

    Phạm vi: ba màn mới tách khỏi `san_xuat` đều nằm trong `SCOPELESS_MODULES` (không router nào
    của chúng đọc scope) nên ghi thẳng `all`. Chép nguyên `own` của vai Tổ trưởng SX sang thì hôm
    nay không sao, nhưng ngày có ai bật lọc theo scope là quyền bị bó âm thầm. `phieu_bao_tri`
    tách khỏi `ky_thuat_may` vốn đã scopeless nên chép sao cũng ra `all`.

    Idempotent: chạy lại không đẻ hàng trùng.
    """
    # Gọi TRƯỚC MỌI LỆNH GHI, và KHÔNG dùng PRAGMA — xem ghi chú dài ở `_migrate_tach_module_ke_toan`
    # (PRAGMA ném SyntaxError trên Postgres; `inspect()` đặt sau phần ghi thì rollback mất dữ liệu).
    cols = sorted(_existing_columns(inspect(db.get_bind()), "role_permissions"))

    for key, label, _cu in _TACH_SAN_XUAT:
        # `modules.created_at` NOT NULL và KHÔNG có server_default ⇒ phải tự điền.
        db.execute(
            text("INSERT INTO modules (key, label, created_at) "
                 "SELECT :k, :l, CURRENT_TIMESTAMP "
                 "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"),
            {"k": key, "l": label},
        )
    # Nhãn hai khoá cũ đổi nghĩa: nay mỗi khoá chỉ còn đúng một màn.
    db.execute(text("UPDATE modules SET label = 'Kế hoạch sản xuất' WHERE key = 'san_xuat'"))
    db.execute(text("UPDATE modules SET label = 'Sửa chữa máy' WHERE key = 'ky_thuat_may'"))

    chep = [c for c in cols if c not in ("id", "module_key")]
    for key, _label, cu in _TACH_SAN_XUAT:
        # `scope` ghi thẳng 'all' (xem docstring); các cột còn lại chép nguyên xi.
        chon = ["'all'" if c == "scope" else f"rp.{c}" for c in chep]
        db.execute(
            text(
                f"INSERT INTO role_permissions (module_key, {', '.join(chep)}) "
                f"SELECT :k, {', '.join(chon)} FROM role_permissions rp "
                "WHERE rp.module_key = :cu AND NOT EXISTS ("
                "  SELECT 1 FROM role_permissions x "
                "  WHERE x.role_id = rp.role_id AND x.module_key = :k)"
            ),
            {"k": key, "cu": cu},
        )
    db.commit()


MIGRATIONS.append(("0209_tach_module_san_xuat", _migrate_tach_module_san_xuat))


def _migrate_piece_rates_ten_cot_danh_muc(db: Session) -> None:
    """`piece_rates`: `code`→`ma` · `name`→`ten` · `is_active`→`active` (chủ chốt 17/08/2026).

    VÌ SAO: bảng này thành màn "Công việc khoán" của Cấu hình danh mục, mà cả ba tầng nền dùng chung
    (`CatalogRepo` · `CatalogService` · `make_catalog_router`) đều đọc ĐÚNG ba tên `ma`/`ten`/
    `active` — 8 danh mục kia đã dùng bộ tên đó. Chọn ĐỔI TÊN CỘT THẬT thay vì thêm bí danh: giữ hai
    tên cho cùng một ý là nguồn của những lỗi "sửa một bên, bên kia im lặng chạy tên cũ".

    RENAME chứ KHÔNG phải thêm-cột-rồi-copy: rename giữ nguyên dữ liệu, index và mọi hàng đang có;
    thêm cột mới thì phải copy rồi drop cột cũ — ba bước, và hỏng giữa đường là bảng ở trạng thái
    hai nửa. SQLite ≥ 3.25 và Postgres đều có `ALTER TABLE … RENAME COLUMN`.

    Idempotent: cột đích đã tồn tại thì bỏ qua từng cột một (DB trắng do `create_all` dựng theo
    model mới sẽ vào nhánh này và không làm gì).

    Hai việc dọn kèm, cùng một lần chạm bảng:

    * BACKFILL MÃ. `ma` nullable và dòng đời cũ có thể trống mã; màn danh mục hiện mã ở cột đầu,
      trống là một ô "null" giữa bảng. Cấp `KH-####` tiếp theo số lớn nhất đang có, KHÔNG đụng mã cũ
      của xưởng (`BE-01`, `XEN-01`, A–F của bảng giấy).
    * ĐỒNG BỘ NHÃN TỔ. `group_name` là nhãn tổ trên dòng; service mới suy lại nó từ `department_id`
      mỗi lần ghi, nên dòng cũ mang mã tổ đời cũ (`to_boi`) sẽ lệch cho tới lần sửa đầu tiên — mà
      panel "Đơn giá khoán của tổ" trong Cấu hình lương lọc theo ĐÚNG nhãn này, lệch là tổ đó nhìn
      vào bảng thiếu dòng. Chỉ đồng bộ dòng CÓ `department_id` trỏ tới một tổ còn tồn tại; dòng chưa
      gắn tổ giữ nguyên nhãn cũ (nó nằm ở tab riêng của màn, không mất đi đâu).
    * ĐỔI ĐƠN VỊ TỪ TÊN SANG MÃ. Ô Đơn vị của màn mới trỏ vào danh mục `Đơn vị & quy đổi` và lưu MÃ
      (`to`, `kg`) — đúng lối `giay.don_vi_gia` đang dùng. Dòng cũ lưu TÊN ("tờ", "cuốn") vì tab
      Lương trước đây gửi tên, nên không đổi thì mở dòng cũ ra là ô báo đỏ "không có trong danh mục".
      CHỈ đổi khi tên khớp CHÍNH XÁC một đơn vị trong danh mục; không khớp thì GIỮ NGUYÊN — thà để
      màn báo đỏ một dòng còn hơn đoán bừa rồi ghi sai đơn vị vào bảng giá.
    """
    insp = inspect(db.get_bind())
    if "piece_rates" not in set(insp.get_table_names()):
        return
    cols = _existing_columns(insp, "piece_rates")
    for cu, moi in (("code", "ma"), ("name", "ten"), ("is_active", "active")):
        if cu in cols and moi not in cols:
            db.execute(text(f"ALTER TABLE piece_rates RENAME COLUMN {cu} TO {moi}"))
    db.commit()

    # --- backfill mã ---
    cols = _existing_columns(inspect(db.get_bind()), "piece_rates")
    if "ma" not in cols:
        return
    thieu = [r[0] for r in db.execute(text(
        "SELECT id FROM piece_rates WHERE ma IS NULL OR TRIM(ma) = '' ORDER BY id"
    )).all()]
    if thieu:
        so = 0
        for (ma,) in db.execute(text("SELECT ma FROM piece_rates WHERE ma LIKE 'KH-%'")).all():
            duoi = str(ma or "")[3:]
            if duoi.isdigit():
                so = max(so, int(duoi))
        for rid in thieu:
            so += 1
            db.execute(text("UPDATE piece_rates SET ma = :m WHERE id = :i"),
                       {"m": f"KH-{so:04d}", "i": rid})
        db.commit()

    # --- nhãn tổ: đồng bộ theo `departments.name` ---
    bang = set(inspect(db.get_bind()).get_table_names())
    if "departments" in bang:
        db.execute(text(
            "UPDATE piece_rates SET group_name = ("
            "  SELECT SUBSTR(d.name, 1, 40) FROM departments d WHERE d.id = piece_rates.department_id"
            ") WHERE department_id IS NOT NULL AND EXISTS ("
            "  SELECT 1 FROM departments d WHERE d.id = piece_rates.department_id"
            "    AND d.name IS NOT NULL AND SUBSTR(d.name, 1, 40) <> piece_rates.group_name)"
        ))
        db.commit()

    # --- đơn vị: TÊN → MÃ (chỉ khi khớp chính xác) ---
    if "don_vi_do" not in bang:
        return
    dv = {str(ten).strip().lower(): str(ma) for ma, ten in db.execute(
        text("SELECT ma, ten FROM don_vi_do")).all() if ten}
    if not dv:
        return
    for rid, unit in db.execute(text("SELECT id, unit FROM piece_rates")).all():
        u = str(unit or "").strip()
        ma_dv = dv.get(u.lower())
        # Đã là mã (hoặc không khớp tên nào) ⇒ không đụng.
        if not ma_dv or ma_dv == u:
            continue
        db.execute(text("UPDATE piece_rates SET unit = :u WHERE id = :i"), {"u": ma_dv, "i": rid})
    db.commit()


MIGRATIONS.append(("0210_piece_rates_ten_cot_danh_muc", _migrate_piece_rates_ten_cot_danh_muc))


def _migrate_module_cong_viec_khoan(db: Session) -> None:
    """Ô quyền `dm_cong_viec_khoan` cho màn danh mục "Công việc khoán" (17/08/2026).

    Trước: bảng đơn giá khoán khai trong một tab của màn Lương, gác bằng khoá `luong`. Nay nó là
    màn thứ 11 của Cấu hình danh mục nên có ô quyền RIÊNG — một màn một ô, như 10 màn kia; ma trận
    quyền vì thế cấp được "khai đơn giá khoán" mà không mở cả bảng lương.

    ⚠️ BƯỚC SAO CHÉP LÀ BẮT BUỘC (cùng lý do mg `0209`): thiếu nó thì ngay lần deploy kế tiếp, mọi
    vai đang khai đơn giá khoán qua màn Lương mất sạch màn này — sáng hôm sau bộ phận lương mở lên
    thấy menu không có mục nào. Chép NGUYÊN XI quyền `luong` sang khoá mới: `read/create/update/
    delete` của màn mới mang đúng nghĩa cũ, không có động từ nào đổi nghĩa.

    `scope` ghi thẳng `all`: khoá mới nằm trong `SCOPELESS_MODULES` (nền danh mục không router nào
    đọc scope). Chép nguyên `own` của một vai nào đó thì hôm nay không sao, nhưng ngày có ai bật lọc
    theo scope là quyền bị bó âm thầm.

    Idempotent: chạy lại không đẻ hàng trùng.
    """
    # Gọi TRƯỚC MỌI LỆNH GHI (xem ghi chú dài ở `_migrate_tach_module_ke_toan`).
    cols = sorted(_existing_columns(inspect(db.get_bind()), "role_permissions"))

    db.execute(
        text("INSERT INTO modules (key, label, created_at) "
             "SELECT :k, :l, CURRENT_TIMESTAMP "
             "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"),
        {"k": "dm_cong_viec_khoan", "l": "Công việc khoán"},
    )
    chep = [c for c in cols if c not in ("id", "module_key")]
    chon = ["'all'" if c == "scope" else f"rp.{c}" for c in chep]
    db.execute(
        text(
            f"INSERT INTO role_permissions (module_key, {', '.join(chep)}) "
            f"SELECT :k, {', '.join(chon)} FROM role_permissions rp "
            "WHERE rp.module_key = 'luong' AND NOT EXISTS ("
            "  SELECT 1 FROM role_permissions x "
            "  WHERE x.role_id = rp.role_id AND x.module_key = :k)"
        ),
        {"k": "dm_cong_viec_khoan"},
    )
    db.commit()


MIGRATIONS.append(("0211_module_cong_viec_khoan", _migrate_module_cong_viec_khoan))


def _migrate_bai_ghep_2(db: Session) -> None:
    """Metadata Bài ghép 2 + chốt DB ``mỗi LSX chỉ thuộc tối đa một bài``.

    Bốn cột dùng chung bảng ``bai_ghep``. Backfill theo giá trị NULL/rỗng để retry sau deploy dở
    dang vẫn hoàn tất mà không đè metadata đã có. Trước mọi ALTER, migration báo đích danh mọi
    ``lsx_id`` đang trùng và dừng; tuyệt
    đối không tự chọn bài để xoá vì đó là quyết định nghiệp vụ.
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    if "bai_ghep" not in tables or "bai_ghep_thanh_vien" not in tables:
        return

    duplicates = db.execute(text(
        "SELECT lsx_id, COUNT(*) AS n FROM bai_ghep_thanh_vien "
        "GROUP BY lsx_id HAVING COUNT(*) > 1 ORDER BY lsx_id"
    )).all()
    if duplicates:
        detail = ", ".join(f"lsx_id={lsx_id} có {count} dòng" for lsx_id, count in duplicates)
        raise RuntimeError(
            "Không thể tạo unique bai_ghep_thanh_vien.lsx_id vì dữ liệu đang trùng: " + detail
        )

    cols = _existing_columns(insp, "bai_ghep")
    added: set[str] = set()
    definitions = (
        ("ten", "VARCHAR(255)"),
        ("han_hoan_thanh_sx", "DATE"),
        ("is_rush", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("nguoi_phu_trach_id", "INTEGER"),
    )
    for name, ddl in definitions:
        if name not in cols:
            db.execute(text(f"ALTER TABLE bai_ghep ADD COLUMN {name} {ddl}"))
            added.add(name)
    # ``ten`` không được rỗng sau một lần deploy dở dang; không đè tên đã được người dùng sửa.
    db.execute(text(
        "UPDATE bai_ghep SET ten = 'Bài ghép ' || ma "
        "WHERE ten IS NULL OR TRIM(ten) = ''"
    ))
    db.execute(text(
        "UPDATE bai_ghep SET han_hoan_thanh_sx = ("
        " SELECT MIN(l.han_hoan_thanh_sx) FROM bai_ghep_thanh_vien tv"
        " JOIN lsx l ON l.id = tv.lsx_id WHERE tv.bai_ghep_id = bai_ghep.id"
        ") WHERE han_hoan_thanh_sx IS NULL"
    ))
    # `is_rush` thêm kèm DEFAULT FALSE nên dòng cũ nhận FALSE chứ không phải NULL — không có cách
    # nào phân biệt "chưa backfill" với "người dùng đã tắt cờ" bằng riêng giá trị cột. Phân biệt
    # bằng `added`: chỉ suy từ thành viên ở ĐÚNG lượt vừa tạo cột; lần chạy lại sau đó chỉ vá dòng
    # còn NULL. Nếu không, một lần retry sẽ bật lại cờ gấp mà người lập kế hoạch vừa cố ý tắt.
    db.execute(text(
        "UPDATE bai_ghep SET is_rush = CASE WHEN EXISTS ("
        " SELECT 1 FROM bai_ghep_thanh_vien tv JOIN lsx l ON l.id = tv.lsx_id"
        " WHERE tv.bai_ghep_id = bai_ghep.id AND l.is_rush = TRUE"
        ") THEN TRUE ELSE FALSE END"
        + ("" if "is_rush" in added else " WHERE is_rush IS NULL")
    ))
    db.execute(text(
        "UPDATE bai_ghep SET nguoi_phu_trach_id = created_by "
        "WHERE nguoi_phu_trach_id IS NULL"
    ))

    db.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_bai_ghep_thanh_vien_lsx_id "
        "ON bai_ghep_thanh_vien (lsx_id)"
    ))
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("ALTER TABLE bai_ghep ALTER COLUMN ten SET NOT NULL"))
    db.commit()


MIGRATIONS.append(("0212_bai_ghep_2", _migrate_bai_ghep_2))


def _migrate_cong_thuc_luong_may_va_khoan(db: Session) -> None:
    """Ô CÔNG THỨC LƯỢNG cho MÁY và cho ĐẦU VIỆC KHOÁN (chủ chốt 17/08/2026).

    Vế thứ ba của cùng một ý đã làm cho vật tư (mg `0194`) và giấy (mg `0195`): công thức RIÊNG của
    chính đối tượng, đứng TRƯỚC công thức của đơn vị. Lý do y hệt — `don_vi_do.cong_thuc` là cách đo
    của một ĐƠN VỊ nên mọi người đo bằng đơn vị đó phải dùng chung một cách tính:

      · `may_thiet_bi.cong_thuc_luong` — "bước chạy trên máy này thì bằng bao nhiêu <đơn vị tốc độ>".
        Lượt in của máy 5 màu là `sl_vao * so_mau / 5`, của máy 2 màu chia 2 — số phụ thuộc CÁI MÁY.
        Ra LƯỢNG, không ra giờ: phép `÷ tốc độ` và hai tầng thời lượng không đụng tới.
      · `piece_rates.cong_thuc_luong` — "việc này khoán theo lượng nào", ra số đơn vị của `unit` rồi
        mới nhân `unit_price`. Ca thật: "Bắt tay + vào keo" khoán đ/`cuốn` mà bước đếm bằng `tay`;
        cầu `tay → cuốn` không có trong bảng cặp nên đầu việc đó CHƯA BAO GIỜ ra tiền được.

    Cả hai chảy vào MỘT hàm `LsxService._sl_theo_don_vi` ở BẬC 0 (trước cầu quy đổi, trước công thức
    đơn vị), tức bốn service đang gọi nó — lệnh · bài ghép · xếp lịch · kế hoạch vật tư — cùng ăn một
    số. Không đẻ đường tính thứ hai.

    Hai cột, MỘT migration: cùng một quyết định, cùng một ngày, và cùng vô hại (thêm cột NULL, không
    backfill). Tách hai chỉ để đánh hai số thứ tự thì lần rollback phải nhớ gỡ cả hai.

    Idempotent: cột đã có thì bỏ qua từng bảng một.
    """
    insp = inspect(db.get_bind())
    bang = set(insp.get_table_names())
    for ten_bang in ("may_thiet_bi", "piece_rates"):
        if ten_bang not in bang:
            continue
        if "cong_thuc_luong" in _existing_columns(insp, ten_bang):
            continue
        db.execute(text(f"ALTER TABLE {ten_bang} ADD COLUMN cong_thuc_luong TEXT"))
    db.commit()


MIGRATIONS.append(("0213_cong_thuc_luong_may_va_khoan", _migrate_cong_thuc_luong_may_va_khoan))


def _migrate_cong_doan_cong_thuc_san_luong(db: Session) -> None:
    """`cong_doan.cong_thuc_san_luong` — sản lượng RA của bước NGOÀI dòng giấy (chủ chốt 17/08/2026).

    Dời chỗ khai, KHÔNG đổi cơ chế: trước đây số này lấy từ công thức của ĐƠN VỊ RA
    (`don_vi_do.cong_thuc`, mg `0192`), nay khai ngay trên CÔNG ĐOẠN. Sai chủ sở hữu là lý do dời:
    "một bước ghi kẽm ra mấy bản" là việc của BƯỚC — hai công đoạn cùng đo bằng `kem` có thể ra số
    khác nhau, mà công thức treo ở đơn vị thì cả hai buộc dùng chung.

    ⚠️ KHÔNG chép giá trị cũ sang. DB dev hôm nay có đúng 3 đơn vị mang công thức và cả ba nhìn là
    GÕ THỬ (`bai := to_dau_vao + 2000`, `m2 := to_dau_vao + dinh_luong`, `kg := sl_ra * 200` — cộng
    tờ với định lượng không có nghĩa vật lý nào). Chép một công thức thử vào chỗ mới là để nó chảy
    thẳng ra sản lượng lệnh; thà để trống và báo người khai, vì trống thì nhìn thấy, còn số sai thì
    trông như thật. Công đoạn duy nhất đang dựa vào cơ chế này: `CD-0001 Ghi kẽm CTP`.

    Idempotent: cột đã có thì bỏ qua.
    """
    insp = inspect(db.get_bind())
    if "cong_doan" not in set(insp.get_table_names()):
        return
    if "cong_thuc_san_luong" in _existing_columns(insp, "cong_doan"):
        return
    db.execute(text("ALTER TABLE cong_doan ADD COLUMN cong_thuc_san_luong VARCHAR(200)"))
    db.commit()


MIGRATIONS.append(("0214_cong_doan_cong_thuc_san_luong", _migrate_cong_doan_cong_thuc_san_luong))


def _migrate_go_cong_thuc_cua_don_vi(db: Session) -> None:
    """GỠ `don_vi_do.cong_thuc` — module Đơn vị & quy đổi chỉ còn KHAI ĐƠN VỊ + QUY ĐỔI (17/08/2026).

    Chủ chốt: mọi nơi cần "một lệnh cần bao nhiêu" nay đều có ô RIÊNG của mình, nên cách-đo treo ở
    đơn vị hết chỗ đứng — nó là thứ dùng chung cho mọi người đếm bằng đơn vị đó, trong khi câu hỏi
    thật luôn thuộc về một MÓN / một MÁY / một ĐẦU VIỆC / một BƯỚC cụ thể:

      · `giay_nguyen.cong_thuc_luong` (mg 0195) · `vat_tu_in_an.cong_thuc_luong` (mg 0194)
      · `may_thiet_bi.cong_thuc_luong` + `piece_rates.cong_thuc_luong` (mg 0213)
      · `cong_doan.cong_thuc_san_luong` (mg 0214) — vế cuối, dời đúng nhánh bước ngoài dòng giấy.

    Bốn chỗ ĂN đã gỡ cùng đợt: `LsxService._sl_theo_don_vi` (bậc ②), `LsxService._luong_vat_tu`
    (đường 2), nhánh sản lượng bước ngoài dòng, và cửa chặn vòng-tròn ở `CongDoanService`.

    ⚠️ SỐ ĐO TRƯỚC KHI XOÁ (DB dev, 17/08/2026): 3/20 đơn vị có công thức — `bai`, `m2`, `kg`, cả ba
    là công thức gõ thử. Nơi dựa vào: 4 vật tư (2 mực · keo · màng) cho lượng BOM, 3 đầu việc khoán
    (CP-01 · CP-02 · IN-01K) cho tiền khoán, 1 công đoạn (CD-0001) cho sản lượng. Chủ đã chốt
    "gỡ hết ngay, không chuyển gì" sau khi nghe đủ danh sách này: chỗ nào cần thì khai lại ở ô mới
    của chính nó.

    DROP best-effort như mg `0198`: SQLite cũ từ chối thì cột mồ côi vô hại vì model đã hết map nó.
    """
    insp = inspect(db.get_bind())
    if "don_vi_do" not in set(insp.get_table_names()):
        return
    if "cong_thuc" not in _existing_columns(insp, "don_vi_do"):
        return
    try:
        db.execute(text("ALTER TABLE don_vi_do DROP COLUMN cong_thuc"))
        db.commit()
    except Exception:
        db.rollback()


MIGRATIONS.append(("0215_go_cong_thuc_cua_don_vi", _migrate_go_cong_thuc_cua_don_vi))


def _migrate_bai_ghep_2_thay_ban_cu(db: Session) -> None:
    """Bài ghép 2 thay hẳn màn Bài ghép cũ (18/08/2026) — chủ chốt nghiệm thu xong.

    HAI MÀN DÙNG CHUNG BẢNG. Migration này KHÔNG đụng `bai_ghep` / `bai_ghep_thanh_vien` /
    `bai_ghep_cong_doan` — không một bài ghép nào mất. Chỉ dọn phần RBAC: khoá `bai_ghep` hết
    người dùng vì router `/api/bai-ghep` bị gỡ cùng đợt.

    Thứ tự bắt buộc: CHÉP xong mới XOÁ. Chép nguyên xi 4 động từ (`read/create/update/delete`) và
    mọi ô quyền chi tiết — cùng lý do mg `0209`/`0211`: quên bước này thì lần deploy kế tiếp cả
    xưởng mất màn bài ghép, sáng hôm sau mở lên menu trống.

    `scope` ghi thẳng `all`: `bai_ghep_2` nằm trong `SCOPELESS_MODULES`, không router nào đọc
    scope của nó. Chép nguyên `own` của một vai thì hôm nay không sao, nhưng ngày có ai bật lọc
    theo scope là quyền bị bó âm thầm.

    Chốt chặn trước khi xoá: đếm lại: mỗi vai từng có `bai_ghep` PHẢI có `bai_ghep_2`. Lệch một
    dòng là DỪNG, không xoá — thà migration đỏ còn hơn âm thầm cắt quyền của một tổ.

    Idempotent: chạy lại không đẻ hàng trùng; lượt sau `bai_ghep` đã sạch nên chép/xoá đều 0 dòng.
    """
    # Gọi TRƯỚC MỌI LỆNH GHI (xem ghi chú dài ở `_migrate_tach_module_ke_toan`).
    cols = sorted(_existing_columns(inspect(db.get_bind()), "role_permissions"))

    # PHẢI có hàng `modules` của `bai_ghep_2` TRƯỚC khi chép quyền: `role_permissions.module_key`
    # trỏ FK về `modules.key`. `seed_modules` mới tạo hàng này lúc app khởi động, mà deploy chạy
    # `app.migrate` trong container tạm TRƯỚC — chưa seed. Trên DB trắng (CI) không lộ vì `bai_ghep`
    # chưa có quyền nào để chép (INSERT chọn 0 dòng); trên staging có quyền thật thì INSERT nổ FK
    # `role_permissions_module_key_fkey`: bai_ghep_2 chưa nằm trong `modules`. Chèn nếu thiếu — cùng
    # idiom idempotent như mg 0211. Nhãn "Bài ghép" khớp seed.py; UPDATE ở cuối lo ca hàng cũ lệch nhãn.
    db.execute(
        text("INSERT INTO modules (key, label, created_at) "
             "SELECT :k, :l, CURRENT_TIMESTAMP "
             "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"),
        {"k": "bai_ghep_2", "l": "Bài ghép"},
    )

    chep = [c for c in cols if c not in ("id", "module_key")]
    chon = ["'all'" if c == "scope" else f"rp.{c}" for c in chep]
    db.execute(text(
        f"INSERT INTO role_permissions (module_key, {', '.join(chep)}) "
        f"SELECT :moi, {', '.join(chon)} FROM role_permissions rp "
        "WHERE rp.module_key = :cu AND NOT EXISTS ("
        "  SELECT 1 FROM role_permissions x "
        "  WHERE x.role_id = rp.role_id AND x.module_key = :moi)"
    ), {"cu": "bai_ghep", "moi": "bai_ghep_2"})

    thieu = db.execute(text(
        "SELECT rp.role_id FROM role_permissions rp WHERE rp.module_key = :cu AND NOT EXISTS ("
        "  SELECT 1 FROM role_permissions x "
        "  WHERE x.role_id = rp.role_id AND x.module_key = :moi)"
    ), {"cu": "bai_ghep", "moi": "bai_ghep_2"}).scalars().all()
    if thieu:
        db.rollback()
        raise RuntimeError(
            "mg 0216: chép quyền bai_ghep → bai_ghep_2 chưa đủ, thiếu role_id "
            f"{sorted(thieu)}. Không xoá quyền cũ."
        )

    db.execute(text("DELETE FROM role_permissions WHERE module_key = :k"), {"k": "bai_ghep"})
    db.execute(text("DELETE FROM modules WHERE key = :k"), {"k": "bai_ghep"})
    # Nhãn "Bài ghép 2" thành "Bài ghép" — `seed_modules` cũng đồng bộ nhãn, đổi ở đây để DB đúng
    # ngay cả khi seeder chưa chạy (bản deploy chạy `app.migrate` trong container tạm trước).
    db.execute(text("UPDATE modules SET label = :l WHERE key = :k"),
               {"k": "bai_ghep_2", "l": "Bài ghép"})
    db.commit()


MIGRATIONS.append(("0216_bai_ghep_2_thay_ban_cu", _migrate_bai_ghep_2_thay_ban_cu))


def _migrate_index_lsx_phan_trang(db: Session) -> None:
    """Index cho màn Kế hoạch SX ở quy mô thật (đo trên 98.000 lệnh, 18/08/2026).

    KHÔNG thêm/đổi cột nào — chỉ index, nên `docs/DB_SCHEMA.md` không phải sửa theo.
    SQLite (test) bỏ qua: `create_all` dựng bảng trắng, vài chục dòng thì index vô nghĩa mà
    `gin_trgm_ops` cũng không tồn tại.

    `pg_trgm` là extension TRUSTED từ PG13 nên chủ sở hữu DB tạo được (prod là PG16). Vẫn bọc
    try/except: thiếu quyền thì bỏ 2 index GIN rồi đi tiếp — màn vẫn chạy, chỉ ô tìm chậm.
    KHÔNG để migration đỏ vì một cái index: deploy chạy `app.migrate` ở container tạm TRƯỚC khi
    đổi app, migration đỏ là kẹt nguyên lượt deploy.
    """
    if db.get_bind().dialect.name != "postgresql":
        return

    co_trgm = True
    try:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        db.commit()
    except Exception:
        db.rollback()
        co_trgm = False
        print("[0217] BO QUA 2 index tim kiem: khong tao duoc extension pg_trgm (thieu quyen).")

    lenh = [
        # Bộ lọc tab + sắp xếp mặc định của màn: WHERE trang_thai IN (…) ORDER BY created_at DESC.
        "CREATE INDEX IF NOT EXISTS ix_lsx_trang_thai_created_at "
        "ON lsx (trang_thai, created_at DESC)",
        # Tab "Tất cả" không lọc gì, chỉ sắp xếp.
        "CREATE INDEX IF NOT EXISTS ix_lsx_created_at ON lsx (created_at DESC)",
        # Vế `or_(nguoi_phu_trach_id IN …, created_by IN …)` của bộ lọc phạm vi RBAC.
        # `nguoi_phu_trach_id` đã có index sẵn; thêm vế này để planner ăn được BitmapOr.
        "CREATE INDEX IF NOT EXISTS ix_lsx_created_by ON lsx (created_by)",
        # Hàng chờ: đơn đã chốt + đã chuyển xuống sản xuất, mới nhất trước.
        "CREATE INDEX IF NOT EXISTS ix_orders_sx_released "
        "ON orders (status, san_xuat_released_at DESC)",
    ]
    if co_trgm:
        # `ilike %q%` không dùng được B-tree; trigram là cách duy nhất để ô tìm không quét cả bảng.
        lenh += [
            "CREATE INDEX IF NOT EXISTS ix_lsx_ma_trgm ON lsx USING gin (ma gin_trgm_ops)",
            "CREATE INDEX IF NOT EXISTS ix_lsx_ten_trgm ON lsx USING gin (ten gin_trgm_ops)",
        ]
    for sql in lenh:
        db.execute(text(sql))
    db.commit()


MIGRATIONS.append(("0217_index_lsx_phan_trang", _migrate_index_lsx_phan_trang))


def _migrate_xep_lich_2(db: Session) -> None:
    """Màn Xếp lịch 2 — cửa vào THỨ HAI cho cùng lịch xưởng (18/08/2026).

    HAI MÀN DÙNG CHUNG bảng `xep_lich_cong_doan`. Migration này KHÔNG đụng bảng lịch — chỉ dọn RBAC:
    tạo khoá module `xep_lich_2` và CHÉP nguyên quyền `xep_lich` sang, gồm cả hai bit `can_approve`
    (phát hành lịch) + `can_approve_exception` (duyệt ngoại lệ). Nhờ chép cả hàng `role_permissions`
    nên hai bit đó theo luôn — không phải cấp lại tay.

    KHÁC mg `0216`: KHÔNG xoá `xep_lich`. Hai màn chạy SONG SONG cho tới khi nghiệm thu xong (`./init.ps1`
    xanh + soi thực tế) mới hợp nhất quyền và gỡ màn cũ — đó là bước tách riêng, chờ mình gật.

    ⚠️ BƯỚC CHÉP LÀ BẮT BUỘC (cùng lý do mg `0209`/`0216`): thiếu nó thì lần deploy kế tiếp mọi vai
    đang xếp lịch mất màn mới. `scope` ghi thẳng 'all' — `xep_lich_2` nằm trong SCOPELESS_MODULES,
    không router nào đọc scope của nó.

    Chốt chặn: mỗi vai từng có `xep_lich` PHẢI có `xep_lich_2`. Lệch một dòng là DỪNG (migration đỏ
    còn hơn âm thầm cắt quyền của một tổ). Idempotent: chạy lại không đẻ hàng trùng.
    """
    # Gọi TRƯỚC MỌI LỆNH GHI (xem ghi chú dài ở `_migrate_tach_module_ke_toan`).
    cols = sorted(_existing_columns(inspect(db.get_bind()), "role_permissions"))

    db.execute(
        text("INSERT INTO modules (key, label, created_at) "
             "SELECT :k, :l, CURRENT_TIMESTAMP "
             "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"),
        {"k": "xep_lich_2", "l": "Xếp lịch công đoạn 2"},
    )
    chep = [c for c in cols if c not in ("id", "module_key")]
    chon = ["'all'" if c == "scope" else f"rp.{c}" for c in chep]
    db.execute(
        text(
            f"INSERT INTO role_permissions (module_key, {', '.join(chep)}) "
            f"SELECT :moi, {', '.join(chon)} FROM role_permissions rp "
            "WHERE rp.module_key = :cu AND NOT EXISTS ("
            "  SELECT 1 FROM role_permissions x "
            "  WHERE x.role_id = rp.role_id AND x.module_key = :moi)"
        ),
        {"cu": "xep_lich", "moi": "xep_lich_2"},
    )

    thieu = db.execute(text(
        "SELECT rp.role_id FROM role_permissions rp WHERE rp.module_key = :cu AND NOT EXISTS ("
        "  SELECT 1 FROM role_permissions x "
        "  WHERE x.role_id = rp.role_id AND x.module_key = :moi)"
    ), {"cu": "xep_lich", "moi": "xep_lich_2"}).scalars().all()
    if thieu:
        db.rollback()
        raise RuntimeError(
            "mg 0218: chép quyền xep_lich → xep_lich_2 chưa đủ, thiếu role_id "
            f"{sorted(thieu)}."
        )
    db.commit()


MIGRATIONS.append(("0218_xep_lich_2", _migrate_xep_lich_2))


def _migrate_xep_lich_2_thay_ban_cu(db: Session) -> None:
    """Xếp lịch 2 thay hẳn màn Xếp lịch công đoạn cũ (19/08/2026) — nghiệm thu xong.

    HAI MÀN DÙNG CHUNG bảng `xep_lich_cong_doan`. Migration này KHÔNG đụng bảng lịch — không dòng
    lịch nào mất. Chỉ dọn phần RBAC: khoá `xep_lich` hết người dùng vì `routers/xep_lich.py` bị gỡ
    cùng đợt (van-de/phát-hành/duyệt-ngoại-lệ nay do `routers/xep_lich_2.py` phục vụ).

    Thứ tự bắt buộc: CHÉP xong mới XOÁ. mg `0218` đã chép `xep_lich → xep_lich_2` (gồm cả hai bit
    `can_approve` + `can_approve_exception`); bước chép ở đây LẶP LẠI nguyên xi, idempotent (NOT
    EXISTS) — self-contained để không phụ thuộc thứ tự nếu chạy lại lẻ. Cùng lý do mg `0209`/`0216`:
    thiếu bước chép thì lần deploy kế tiếp mọi vai đang xếp lịch mất màn, sáng ra menu trống.

    `scope` ghi thẳng `all`: `xep_lich_2` nằm trong `SCOPELESS_MODULES`, không router nào đọc scope
    của nó — chép nguyên `own` của một vai là ngày có ai bật lọc theo scope thì quyền bị bó âm thầm.

    Chốt chặn trước khi xoá: mỗi vai từng có `xep_lich` PHẢI có `xep_lich_2`. Lệch một dòng là DỪNG,
    không xoá — thà migration đỏ còn hơn âm thầm cắt quyền của một tổ.

    Idempotent: chạy lại không đẻ hàng trùng; lượt sau `xep_lich` đã sạch nên chép/xoá đều 0 dòng.
    """
    # Gọi TRƯỚC MỌI LỆNH GHI (xem ghi chú dài ở `_migrate_tach_module_ke_toan`).
    cols = sorted(_existing_columns(inspect(db.get_bind()), "role_permissions"))

    chep = [c for c in cols if c not in ("id", "module_key")]
    chon = ["'all'" if c == "scope" else f"rp.{c}" for c in chep]
    db.execute(text(
        f"INSERT INTO role_permissions (module_key, {', '.join(chep)}) "
        f"SELECT :moi, {', '.join(chon)} FROM role_permissions rp "
        "WHERE rp.module_key = :cu AND NOT EXISTS ("
        "  SELECT 1 FROM role_permissions x "
        "  WHERE x.role_id = rp.role_id AND x.module_key = :moi)"
    ), {"cu": "xep_lich", "moi": "xep_lich_2"})

    thieu = db.execute(text(
        "SELECT rp.role_id FROM role_permissions rp WHERE rp.module_key = :cu AND NOT EXISTS ("
        "  SELECT 1 FROM role_permissions x "
        "  WHERE x.role_id = rp.role_id AND x.module_key = :moi)"
    ), {"cu": "xep_lich", "moi": "xep_lich_2"}).scalars().all()
    if thieu:
        db.rollback()
        raise RuntimeError(
            "mg 0219: chép quyền xep_lich → xep_lich_2 chưa đủ, thiếu role_id "
            f"{sorted(thieu)}. Không xoá quyền cũ."
        )

    db.execute(text("DELETE FROM role_permissions WHERE module_key = :k"), {"k": "xep_lich"})
    db.execute(text("DELETE FROM modules WHERE key = :k"), {"k": "xep_lich"})
    # Nhãn "Xếp lịch công đoạn 2" thành "Xếp lịch công đoạn" — `seed_modules` cũng đồng bộ nhãn, đổi
    # ở đây để DB đúng ngay cả khi seeder chưa chạy (deploy chạy `app.migrate` trong container tạm trước).
    db.execute(text("UPDATE modules SET label = :l WHERE key = :k"),
               {"k": "xep_lich_2", "l": "Xếp lịch công đoạn"})
    db.commit()


MIGRATIONS.append(("0219_xep_lich_2_thay_ban_cu", _migrate_xep_lich_2_thay_ban_cu))


def _migrate_nen_thuc_hien_san_xuat(db: Session) -> None:
    """Nền tổ chức cho module THỰC HIỆN SẢN XUẤT (spec-thuc-hien-san-xuat, Giai đoạn 1).

    Hai cột cộng thêm, thuần additive, KHÔNG backfill — cả hai bỏ trống là đúng nghĩa "chưa bật":
    · `departments.is_kcs` (BOOLEAN, mặc định FALSE) — đánh dấu tổ KCS đích danh (§3.1, §14).
    · `job_grades.output_coefficient` (NUMERIC(6,3), NULL) — hệ số chia sản lượng khoán theo bậc
      (§8). NULL ⇒ engine coi 1.0; khai bậc vẫn KHÔNG đổi lương cho tới khi có hệ số + mẻ khoán.

    Boolean literal phải là FALSE (không phải "0") — chuỗi "0"/"1" vỡ khi Postgres create_all trên DB
    trắng. Guard theo cột ⇒ idempotent; no-op trên DB fresh (create_all đã dựng đủ)."""
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    if "departments" in tables and "is_kcs" not in _existing_columns(insp, "departments"):
        db.execute(text(
            "ALTER TABLE departments ADD COLUMN is_kcs BOOLEAN NOT NULL DEFAULT FALSE"))
    if "job_grades" in tables and "output_coefficient" not in _existing_columns(insp, "job_grades"):
        db.execute(text(
            "ALTER TABLE job_grades ADD COLUMN output_coefficient NUMERIC(6,3)"))
    db.commit()


MIGRATIONS.append(("0220_nen_thuc_hien_san_xuat", _migrate_nen_thuc_hien_san_xuat))


def _migrate_module_ly_do_san_xuat(db: Session) -> None:
    """Ô quyền `dm_ly_do_san_xuat` cho màn danh mục "Lý do & lỗi SX" (§15, 19/08/2026).

    Màn thứ 12 của Cấu hình danh mục: danh mục CHUẨN HOÁ lý do/lỗi (hỏng batch · lỗi KCS · tạm dừng
    · bắt đầu trễ · điều chỉnh bàn giao…) — thay cho việc hard-code danh sách lý do ở FE. Bảng
    `san_xuat_ly_do` là bảng MỚI nên `create_all` tự dựng, migration này CHỈ lo phần RBAC.

    ⚠️ BƯỚC SAO CHÉP LÀ BẮT BUỘC (cùng lý do mg `0211`): khoá quyền mới không tự có ở các vai đang
    chạy trên DB live — thiếu bước chép thì bộ phận sản xuất mở Cấu hình danh mục KHÔNG thấy màn này.
    Chép NGUYÊN XI quyền `san_xuat` (đúng đối tượng quản lý danh mục sản xuất: ai xem/sửa kế hoạch SX
    thì xem/sửa được danh mục lý do): read/create/update/delete mang đúng nghĩa, không động từ nào đổi.

    `scope` ghi thẳng `all`: khoá mới nằm trong `SCOPELESS_MODULES` (nền danh mục không router nào
    đọc scope). Chép nguyên `own`/`department` của một vai là ngày có ai bật lọc theo scope thì quyền
    bị bó âm thầm.

    Idempotent: chạy lại không đẻ hàng trùng.
    """
    # Gọi TRƯỚC MỌI LỆNH GHI (xem ghi chú dài ở `_migrate_tach_module_ke_toan`).
    cols = sorted(_existing_columns(inspect(db.get_bind()), "role_permissions"))

    db.execute(
        text("INSERT INTO modules (key, label, created_at) "
             "SELECT :k, :l, CURRENT_TIMESTAMP "
             "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"),
        {"k": "dm_ly_do_san_xuat", "l": "Lý do & lỗi SX"},
    )
    chep = [c for c in cols if c not in ("id", "module_key")]
    chon = ["'all'" if c == "scope" else f"rp.{c}" for c in chep]
    db.execute(
        text(
            f"INSERT INTO role_permissions (module_key, {', '.join(chep)}) "
            f"SELECT :k, {', '.join(chon)} FROM role_permissions rp "
            "WHERE rp.module_key = 'san_xuat' AND NOT EXISTS ("
            "  SELECT 1 FROM role_permissions x "
            "  WHERE x.role_id = rp.role_id AND x.module_key = :k)"
        ),
        {"k": "dm_ly_do_san_xuat"},
    )
    db.commit()


MIGRATIONS.append(("0221_module_ly_do_san_xuat", _migrate_module_ly_do_san_xuat))


def _migrate_khoang_tham_gia_snapshot_bac(db: Session) -> None:
    """Snapshot bậc tay nghề + hệ số sản lượng lên khoảng tham gia (spec §8, Giai đoạn 4).

    Hai cột cộng thêm trên bảng `san_xuat_khoang_tham_gia` (đã tồn tại từ G2), thuần additive,
    KHÔNG backfill — khoảng cũ (trước G4) bỏ trống là ĐÚNG: §8 cấm danh mục bậc đổi về sau viết lại
    dữ liệu đang chạy/đã xong. Khoảng MỚI được engine thực thi điền lúc mở (đọc `Employee.job_grade_id`
    + `JobGrade.output_coefficient`).
    · `job_grade_id` (INTEGER, NULL) — ảnh chụp bậc; FK chỉ khai ở model cho create_all (DB live để
      trần INTEGER như tiền lệ mg 0220, không siết constraint qua ALTER).
    · `output_coefficient` (NUMERIC(6,3), NULL) — NULL CHẶN chốt phân bổ (§8) chứ không chặn ghi batch.

    Guard theo cột ⇒ idempotent; no-op trên DB fresh (create_all đã dựng đủ cột)."""
    insp = inspect(db.get_bind())
    if "san_xuat_khoang_tham_gia" in set(insp.get_table_names()):
        cols = _existing_columns(insp, "san_xuat_khoang_tham_gia")
        if "job_grade_id" not in cols:
            db.execute(text(
                "ALTER TABLE san_xuat_khoang_tham_gia ADD COLUMN job_grade_id INTEGER"))
        if "output_coefficient" not in cols:
            db.execute(text(
                "ALTER TABLE san_xuat_khoang_tham_gia ADD COLUMN output_coefficient NUMERIC(6,3)"))
    db.commit()


MIGRATIONS.append(
    ("0222_khoang_tham_gia_snapshot_bac", _migrate_khoang_tham_gia_snapshot_bac)
)


def _migrate_phien_chay_ly_do_so_nguoi(db: Session) -> None:
    """Lý do số-người-lệch lên phiên chạy (spec §7.1, Giai đoạn 2 đuôi).

    Một cột cộng thêm trên bảng `san_xuat_phien_chay` (đã tồn tại từ G2), thuần additive, KHÔNG
    backfill — phiên cũ bỏ trống là ĐÚNG (không truy hồi lý do cho việc đã chạy). Phiên MỚI được
    engine `bat_dau` điền khi số người thực tế bắt đầu KHÁC số dự kiến chốt lúc phát hành
    (`cong_viec.dinh_muc_json['so_nhan_cong_tieu_chuan']`), song hành với `ly_do_bat_dau_tre`.

    Guard theo cột ⇒ idempotent; no-op trên DB fresh (create_all đã dựng đủ cột)."""
    insp = inspect(db.get_bind())
    if "san_xuat_phien_chay" in set(insp.get_table_names()):
        if "ly_do_so_nguoi" not in _existing_columns(insp, "san_xuat_phien_chay"):
            db.execute(text(
                "ALTER TABLE san_xuat_phien_chay ADD COLUMN ly_do_so_nguoi VARCHAR(255)"))
    db.commit()


MIGRATIONS.append(
    ("0223_phien_chay_ly_do_so_nguoi", _migrate_phien_chay_ly_do_so_nguoi)
)


def _migrate_ky_thuat_bao_tri_ly_do_huy(db: Session) -> None:
    """Lý do hủy phiếu bảo trì (thay chức năng dời lịch bằng hủy-kèm-lý-do).

    Một cột cộng thêm trên bảng `ky_thuat_bao_tri` (đã tồn tại từ module Kỹ thuật máy), thuần
    additive, KHÔNG backfill — phiếu cũ để trống là ĐÚNG. Trạng thái `da_huy` là giá trị mới của
    cột `trang_thai` (String), không cần DDL riêng. Phiếu chuyển sang `da_huy` bắt buộc có lý do;
    mở lại phiếu (hủy nhầm) sẽ xoá cột này về NULL.

    Guard theo cột ⇒ idempotent; no-op trên DB fresh (create_all đã dựng đủ cột)."""
    insp = inspect(db.get_bind())
    if "ky_thuat_bao_tri" in set(insp.get_table_names()):
        if "ly_do_huy" not in _existing_columns(insp, "ky_thuat_bao_tri"):
            db.execute(text(
                "ALTER TABLE ky_thuat_bao_tri ADD COLUMN ly_do_huy VARCHAR(300)"))
    db.commit()


MIGRATIONS.append(
    ("0224_ky_thuat_bao_tri_ly_do_huy", _migrate_ky_thuat_bao_tri_ly_do_huy)
)


def _migrate_module_yeu_cau_sua_chua(db: Session) -> None:
    """Ô quyền `yeu_cau_sua_chua` = "Báo máy hỏng" (20/08/2026).

    Bảng `ky_thuat_yeu_cau_sua` là bảng MỚI nên `create_all` tự dựng — migration này KHÔNG đụng
    schema, nó chỉ thêm một HÀNG DỮ LIỆU vào `modules`. Vẫn phải viết ở đây vì `modules` là danh
    sách ô quyền: DB live không có hàng này thì ma trận phân quyền không hiện ô nào để tick, và
    người ngoài tổ kỹ thuật vĩnh viễn không được cấp quyền báo máy hỏng.

    KHÔNG chép quyền từ khoá nào sang (khác 0209): mọi endpoint yêu cầu đều nhận `ky_thuat_may`
    làm đường vào thứ hai, nên tổ sửa chữa dùng được ngay mà không cần cấp thêm. Khoá mới chỉ để
    MỞ cho người ngoài — mà mở cho ai là quyết định của chủ chốt, không phải của migration.

    Idempotent: chạy lại không đẻ hàng trùng.
    """
    db.execute(
        # `modules.created_at` NOT NULL và KHÔNG có server_default ⇒ phải tự điền (khuôn 0209).
        text("INSERT INTO modules (key, label, created_at) "
             "SELECT :k, :l, CURRENT_TIMESTAMP "
             "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"),
        {"k": "yeu_cau_sua_chua", "l": "Báo máy hỏng"},
    )
    db.commit()


MIGRATIONS.append(
    ("0225_module_yeu_cau_sua_chua", _migrate_module_yeu_cau_sua_chua)
)
def _migrate_dieu_chuyen_kho(db) -> None:
    """Điều chuyển kho (mô hình 2 yêu cầu) — thêm cột đánh dấu/nối, KHÔNG đụng CheckConstraint loai
    (phiếu vẫn NHAP/XUAT) nên KHÔNG cần dựng lại bảng. Toàn ALTER ADD nullable / default → no-op DB
    fresh / cột đã có.

    - `stock_requests.dieu_chuyen` (bool) — cả yêu cầu XUẤT nguồn lẫn NHẬP đích của một điều chuyển.
    - `stock_requests.kho_nguon_id` (int) — trên yêu cầu NHẬP đích: kho nguồn (hiện "Điều chuyển từ …").
    - `stock_requests.xuat_voucher_id` (int) — trên yêu cầu NHẬP đích: phiếu xuất nguồn đã ghi sổ.
    - `stock_vouchers.dieu_chuyen` (bool) — cả phiếu xuất nguồn lẫn nhập đích (báo cáo gắn nhãn).
    """
    insp = inspect(db.get_bind())
    tables = insp.get_table_names()
    if "stock_requests" in tables:
        cols = _existing_columns(insp, "stock_requests")
        if "dieu_chuyen" not in cols:
            db.execute(text(
                "ALTER TABLE stock_requests ADD COLUMN dieu_chuyen BOOLEAN NOT NULL DEFAULT FALSE"
            ))
        if "kho_nguon_id" not in cols:
            db.execute(text("ALTER TABLE stock_requests ADD COLUMN kho_nguon_id INTEGER"))
        if "xuat_voucher_id" not in cols:
            db.execute(text("ALTER TABLE stock_requests ADD COLUMN xuat_voucher_id INTEGER"))
    if "stock_vouchers" in tables and "dieu_chuyen" not in _existing_columns(insp, "stock_vouchers"):
        db.execute(text(
            "ALTER TABLE stock_vouchers ADD COLUMN dieu_chuyen BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    db.commit()


MIGRATIONS.append(("0203_dieu_chuyen_kho", _migrate_dieu_chuyen_kho))


def _migrate_stock_voucher_line_hsd(db) -> None:
    """Hạn sử dụng khai ở DÒNG phiếu NHẬP: thêm `stock_voucher_lines.hsd` (DATE nullable). Một dòng
    nhập có thể tách nhiều lô theo hạn (mỗi (hạn, SL) là một dòng phiếu). Ghi sổ chép sang
    `stock_lots.hsd` (đã có sẵn, dùng cho FEFO). No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "stock_voucher_lines" not in insp.get_table_names():
        return
    if "hsd" not in _existing_columns(insp, "stock_voucher_lines"):
        db.execute(text("ALTER TABLE stock_voucher_lines ADD COLUMN hsd DATE"))
    db.commit()


MIGRATIONS.append(("0205_stock_voucher_line_hsd", _migrate_stock_voucher_line_hsd))
def _migrate_attendance_period_standard_cong(db) -> None:
    """Thêm `attendance_periods.standard_cong` — CÔNG CHUẨN đóng băng lúc chốt kỳ công.

    Vì sao cần (chủ chốt 15/08/2026): cấu hình tuần làm việc chỉ có MỘT bản dùng chung cho mọi
    thời điểm, không có ngày hiệu lực. Công ty bỏ làm thứ Bảy là công chuẩn của MỌI THÁNG TRONG
    QUÁ KHỨ đổi theo — mà đơn giá ngày = lương tháng ÷ công chuẩn, nên tính lại một tháng cũ sẽ
    ra tiền khác, dù tháng đó đã chốt công và đã trả lương.

    Đóng băng đúng theo lối cả vòng khoá đang dùng: chốt công là CHỤP ẢNH. Nay ảnh chụp thêm một
    số nữa. NULL = kỳ chốt TRƯỚC bản vá này ⇒ vẫn đọc lịch sống như cũ, không viết lại lịch sử."""
    insp = inspect(db.get_bind())
    if "attendance_periods" not in insp.get_table_names():
        return
    if "standard_cong" not in _existing_columns(insp, "attendance_periods"):
        db.execute(text("ALTER TABLE attendance_periods ADD COLUMN standard_cong NUMERIC(6, 2)"))
        db.commit()


MIGRATIONS.append(("0193_attendance_period_standard_cong", _migrate_attendance_period_standard_cong))


def _migrate_cham_cong_mot_o_mot_tab(db) -> None:
    """Màn Chấm công: MỘT Ô QUYỀN = MỘT TAB (chủ chốt 15/08/2026).

    Thêm 5 cột cờ rồi RÓT quyền đang có sang, theo hướng **chỉ bật thêm, không tắt gì** — không vai
    nào mất quyền sau khi cập nhật:

      cham_cong.can_read              → can_view_timesheet      (đang xem bảng công thì vẫn xem)
      cham_cong.can_update            → 3 ô cấu hình            ("Cấu hình chấm công" cũ mở cả ba)
      di_muon.can_approve             → can_approve_late_early  (gộp khoá về đúng màn của nó)
      yeu_cau_chinh_cong.can_approve  → cham_cong.can_approve   (cột này của cham_cong đang trống)

    Dòng quyền của hai module cũ (`di_muon`, `yeu_cau_chinh_cong`) GIỮ NGUYÊN tại chỗ — xoá ở lượt
    sau, sau khi chạy thật vài ngày. Migration đã xoá dữ liệu thì không có đường về."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    co = _existing_columns(insp, "role_permissions")
    for ten in ("can_view_timesheet", "can_approve_late_early", "can_manage_locations",
                "can_manage_shifts", "can_manage_calendar"):
        if ten not in co:
            db.execute(text(
                f"ALTER TABLE role_permissions ADD COLUMN {ten} BOOLEAN NOT NULL DEFAULT FALSE"))
    db.commit()

    # Rót TRONG CÙNG dòng cham_cong.
    db.execute(text(
        "UPDATE role_permissions SET can_view_timesheet = true "
        "WHERE module_key = 'cham_cong' AND can_read AND NOT can_view_timesheet"))
    db.execute(text(
        "UPDATE role_permissions SET can_manage_locations = true, can_manage_shifts = true, "
        "can_manage_calendar = true "
        "WHERE module_key = 'cham_cong' AND can_update"))
    db.commit()

    # Rót TỪ module khác sang: chỉ đụng những vai đã có dòng `cham_cong`; vai chưa có dòng đó thì
    # tạo mới với đúng ô vừa rót (kèm can_read để họ còn mở được màn mà dùng).
    for nguon, dich in (("di_muon", "can_approve_late_early"),
                        ("yeu_cau_chinh_cong", "can_approve")):
        vai = [r[0] for r in db.execute(text(
            f"SELECT role_id FROM role_permissions WHERE module_key = '{nguon}' AND can_approve"
        )).all()]
        for role_id in vai:
            co_dong = db.execute(text(
                "SELECT 1 FROM role_permissions WHERE role_id = :r AND module_key = 'cham_cong'"
            ), {"r": role_id}).first()
            if co_dong:
                db.execute(text(
                    f"UPDATE role_permissions SET {dich} = true "
                    "WHERE role_id = :r AND module_key = 'cham_cong'"), {"r": role_id})
            else:
                # Liệt kê ĐỦ mọi cột `can_*` và cho false — bảng có cột NOT NULL không kèm
                # server_default (can_create…), bỏ sót là vỡ ngay trên DB tạo mới bằng create_all.
                co_cot = [c for c in _existing_columns(insp, "role_permissions")
                          if c.startswith("can_")]
                gia_tri = {c: (c in ("can_read", dich)) for c in co_cot}
                ten_cot = ", ".join(gia_tri)
                cho = ", ".join(f":{c}" for c in gia_tri)
                db.execute(
                    text(f"INSERT INTO role_permissions (role_id, module_key, scope, {ten_cot}) "
                         f"VALUES (:r, 'cham_cong', 'department', {cho})"),
                    {"r": role_id, **gia_tri},
                )
    db.commit()


MIGRATIONS.append(("0194_cham_cong_mot_o_mot_tab", _migrate_cham_cong_mot_o_mot_tab))


def _migrate_luong_bang_luong_thanh_o_rieng(db) -> None:
    """Tab "Bảng lương tháng" thành Ô RIÊNG (chủ chốt 15/08/2026).

    Trước đó nó đi theo cột Xem của module `luong`, nên cấp ô Lương ở phạm vi *Của tôi* là người
    đó vẫn mở được BẢNG LƯƠNG — danh sách quản lý, kèm nút Tính lại / Chốt kỳ. Chủ chốt: *"Sao lại
    bảng lương với tạm ứng nhân viên được xem nhỉ"*. Cùng khuôn đã áp cho "Bảng công tháng".

    Rót theo hướng CHỈ THÊM: ai đang xem được bảng lương thì sau cập nhật vẫn xem được."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    if "can_view_payroll_table" not in _existing_columns(insp, "role_permissions"):
        db.execute(text(
            "ALTER TABLE role_permissions ADD COLUMN can_view_payroll_table "
            "BOOLEAN NOT NULL DEFAULT FALSE"))
        db.commit()
    db.execute(text(
        "UPDATE role_permissions SET can_view_payroll_table = true "
        "WHERE module_key = 'luong' AND can_read AND NOT can_view_payroll_table"))
    db.commit()


MIGRATIONS.append(("0195_luong_bang_luong_thanh_o_rieng", _migrate_luong_bang_luong_thanh_o_rieng))


def _migrate_luong_hai_tab_thanh_o_rieng(db) -> None:
    """Tab "Lương nhân viên" và "Lương khoán" thành Ô RIÊNG (chủ chốt 15/08/2026).

    Trước đó hai tab này đi theo CỘT THAO TÁC — bật Thao tác là ba tab bung ra cùng lúc, đúng cái
    bệnh vừa dọn ở "Cấu hình chấm công". Chủ chốt: *"lương nhân viên với lương khoán nó cũng là
    tab mà nên cũng phải có nút bật tắt chứ"*.

    Luật chốt: **cột Thao tác KHÔNG mở tab nào**, nó chỉ cho GHI vào tab đã mở được.

    Rót CHỈ THÊM: ai đang có ô Thao tác của Lương thì được bật sẵn hai ô mới — giữ nguyên hiện
    trạng, không ai mất tab đang dùng."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    co = _existing_columns(insp, "role_permissions")
    for ten in ("can_manage_salary_profiles", "can_manage_piece_rates"):
        if ten not in co:
            db.execute(text(
                f"ALTER TABLE role_permissions ADD COLUMN {ten} BOOLEAN NOT NULL DEFAULT FALSE"))
    db.commit()
    db.execute(text(
        "UPDATE role_permissions SET can_manage_salary_profiles = true, "
        "can_manage_piece_rates = true "
        "WHERE module_key = 'luong' AND can_update"))
    db.commit()


MIGRATIONS.append(("0196_luong_hai_tab_thanh_o_rieng", _migrate_luong_hai_tab_thanh_o_rieng))


def _migrate_nghi_phep_danh_muc_thanh_o_rieng(db) -> None:
    """Ô "Quản danh mục loại nghỉ" có CỘT RIÊNG (chủ chốt 15/08/2026).

    Trước đó nó mượn chính cột `can_update` — mà `can_update` cũng là một trong ba cột nút "Thao
    tác" bật cùng lúc. Hậu quả trên màn: bật Thao tác (để thợ gửi/huỷ đơn của mình) thì ô "Quản
    danh mục loại nghỉ" TỰ SÁNG THEO, tức là mở luôn quyền sửa chính sách nghỉ của cả nhà máy mà
    người cấp quyền không hề bấm vào đó.

    Rót CHỈ THÊM: vai nào đang có `nghi_phep.can_update` thì được bật ô mới — giữ nguyên hiện
    trạng, không ai mất quyền quản danh mục đang dùng."""
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    if "can_manage_leave_types" not in _existing_columns(insp, "role_permissions"):
        db.execute(text(
            "ALTER TABLE role_permissions ADD COLUMN can_manage_leave_types "
            "BOOLEAN NOT NULL DEFAULT FALSE"))
        db.commit()
    db.execute(text(
        "UPDATE role_permissions SET can_manage_leave_types = true "
        "WHERE module_key = 'nghi_phep' AND can_update AND NOT can_manage_leave_types"))
    db.commit()


MIGRATIONS.append(("0197_nghi_phep_danh_muc_thanh_o_rieng", _migrate_nghi_phep_danh_muc_thanh_o_rieng))


def _migrate_luong_o_that_thay_o_ma(db) -> None:
    """Màn Lương: đổi cổng vào từ ô ma `self_service` sang ô THẬT `luong`.

    Trước 15/08/2026 menu Lương mở khi có `luong` HOẶC `self_service`. `self_service` được cấp
    sẵn cho MỌI vai và ĐÃ BỊ GỠ khỏi bảng phân quyền ⇒ HCNS không nhìn thấy, không tắt được:
    một cái cổng không có tay nắm. Cùng lúc, luật "ghi là ghi" bắt xin tạm ứng phải có ô Lương →
    Thao tác, mà đo trên DB dev thì 17/20 vai không có ô Lương ⇒ vào tab được mà không gửi được.

    Migration này rót ô `luong` phạm vi `own` (Xem + Thao tác) cho những vai đang đi cửa
    `self_service`, để khi cổng ma bị gỡ thì KHÔNG ai mất màn Lương của mình. CHỈ THÊM:

      * vai CHƯA có dòng `luong`               → INSERT (scope own, can_read + can_create)
      * vai có dòng `luong` nhưng TRỐNG TRƠN    → UPDATE đúng hai ô đó
        (trống trơn = mọi cột `can_*` đều false; trong bảng phân quyền nó hiện y như chưa cấp)
      * vai có dòng `luong` đã bật ô nào đó     → KHÔNG ĐỤNG (đó là ý của người cấu hình)

    KHÔNG bật `can_view_payroll_table`: bảng lương tháng là việc của HCNS/kế toán —
    *"công nhân làm gì có quyền đó đâu"*. Dòng `self_service` giữ nguyên tại chỗ, xoá ở lượt sau.
    """
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    cot_can = [c for c in _existing_columns(insp, "role_permissions") if c.startswith("can_")]
    if "can_read" not in cot_can or "can_create" not in cot_can:
        return

    # Vai đi cửa self_service = vai cần giữ nguyên trải nghiệm hôm nay.
    vai_ss = [r[0] for r in db.execute(text(
        "SELECT role_id FROM role_permissions WHERE module_key = 'self_service' AND can_read"
    )).all()]
    if not vai_ss:
        return

    trong_tron = " AND ".join(f"NOT {c}" for c in cot_can)
    for role_id in vai_ss:
        dong = db.execute(text(
            "SELECT 1 FROM role_permissions WHERE role_id = :r AND module_key = 'luong'"
        ), {"r": role_id}).first()
        if dong is None:
            # Liệt kê ĐỦ mọi cột `can_*` — bảng có cột NOT NULL không kèm server_default,
            # bỏ sót là vỡ ngay trên DB tạo mới bằng create_all (bài học mg 0194).
            gia_tri = {c: (c in ("can_read", "can_create")) for c in cot_can}
            ten_cot = ", ".join(gia_tri)
            cho = ", ".join(f":{c}" for c in gia_tri)
            db.execute(
                text(f"INSERT INTO role_permissions (role_id, module_key, scope, {ten_cot}) "
                     f"VALUES (:r, 'luong', 'own', {cho})"),
                {"r": role_id, **gia_tri},
            )
        else:
            db.execute(text(
                "UPDATE role_permissions SET can_read = true, can_create = true "
                f"WHERE role_id = :r AND module_key = 'luong' AND {trong_tron}"
            ), {"r": role_id})
    db.commit()


MIGRATIONS.append(("0198_luong_o_that_thay_o_ma", _migrate_luong_o_that_thay_o_ma))


def _migrate_luong_special_cong(db: Session) -> None:
    """`payroll_lines.special_cong` — công NGÀY LỄ / NGHỈ TUẦN có đi làm (TRONG ĐÓ của
    `actual_cong`). Sửa 17/08/2026.

    VÌ SAO CẦN: `_luong_cong_split` kẹp `paid_worked = min(worked, std)`. Công ngày lễ/CN nằm chung
    rổ đó nên ai đã đủ công chuẩn rồi mới đi làm Chủ nhật thì phần gốc 1× bị trần nuốt, `ot_pay`
    chỉ bù `(hệ số − 1)` ⇒ thực nhận 1× thay vì 2× (lễ: 2× thay vì 3×) — trái Đ98.1.b/c.
    Nay công lễ/CN được trả NGOÀI trần. `_compute` biết số này từ Chấm công, nhưng đường "Sửa 1 ô"
    (`update_line`) chỉ đọc dòng lương nên PHẢI có cột, không thì hai đường tính ra hai số.

    KHÔNG BACKFILL: kỳ cũ để `0` ⇒ tính lại kỳ cũ vẫn ra đúng số đã chốt, không hồi tố tiền.
    Chỉ ADD COLUMN DEFAULT — idempotent, no-op trên DB fresh (create_all đã dựng)."""
    insp = inspect(db.get_bind())
    if "payroll_lines" not in set(insp.get_table_names()):
        return
    if "special_cong" in _existing_columns(insp, "payroll_lines"):
        return
    db.execute(text(
        "ALTER TABLE payroll_lines ADD COLUMN special_cong NUMERIC(6,2) NOT NULL DEFAULT 0"
    ))
    db.commit()


MIGRATIONS.append(("0204_luong_special_cong", _migrate_luong_special_cong))


def _migrate_luong_off1x_pay(db: Session) -> None:
    """`payroll_lines.off1x_pay` — tiền ngày off1x (TRONG ĐÓ của `ot_pay`). Sửa 17/08/2026.

    VÌ SAO CẦN: `_auto_pit` miễn thuế NGUYÊN `ot_pay`, mà `ot_pay` gộp cả tiền ngày off1x — khoản
    trả đúng 1×, KHÔNG hệ số, tức lương ngày làm việc bình thường, KHÔNG có phần "trả cao hơn" nào
    để miễn. Kế toán chốt 17/08/2026: "lương thuế chỉ 1 công bình thường" ⇒ khoản này CHỊU thuế.
    `_compute` biết số này, nhưng đường "Sửa 1 ô" (`update_line` / `_apply_auto_pit`) chỉ đọc dòng
    lương nên PHẢI có cột, không thì hai đường ra hai số thuế.

    KHÔNG BACKFILL: kỳ cũ để `0` ⇒ tính lại kỳ cũ vẫn ra đúng số đã chốt, không hồi tố thuế.
    Chỉ ADD COLUMN DEFAULT — idempotent, no-op trên DB fresh (create_all đã dựng)."""
    insp = inspect(db.get_bind())
    if "payroll_lines" not in set(insp.get_table_names()):
        return
    if "off1x_pay" in _existing_columns(insp, "payroll_lines"):
        return
    db.execute(text(
        "ALTER TABLE payroll_lines ADD COLUMN off1x_pay NUMERIC(14,2) NOT NULL DEFAULT 0"
    ))
    db.commit()


MIGRATIONS.append(("0205_luong_off1x_pay", _migrate_luong_off1x_pay))


def _migrate_tran_gio_tang_ca(db: Session) -> None:
    """`payroll_params.ot_max_minutes_per_month` + `.ot_max_minutes_per_day` — trần giờ làm thêm
    Điều 107 BLLĐ. Chủ chốt 17/08/2026: khai được số giờ/tháng, CHẶN CỨNG, không có đường vượt.

    ⚠️ `ot_max_minutes_per_month` mặc định **0 = TẮT TRẦN** — cố ý. Migration chạy xong KHÔNG chặn
    ai, không đổi một đồng nào. Chủ vào Cấu hình lương gõ 2400 (40 giờ) khi sẵn sàng bật.

    `ot_max_minutes_per_day` mặc định 720 (12 giờ) = ĐÚNG hằng số `MAX_OT_MINUTES` đang viết cứng
    trong `overtime_service` ⇒ hành vi không đổi, chỉ chuyển từ code sang tham số khai được.

    Chỉ ADD COLUMN DEFAULT — idempotent, no-op trên DB fresh (create_all đã dựng)."""
    insp = inspect(db.get_bind())
    if "payroll_params" not in set(insp.get_table_names()):
        return
    cols = _existing_columns(insp, "payroll_params")
    for name, ddl in (
        ("ot_max_minutes_per_month", "INTEGER NOT NULL DEFAULT 0"),
        ("ot_max_minutes_per_day", "INTEGER NOT NULL DEFAULT 720"),
    ):
        if name not in cols:
            db.execute(text(f"ALTER TABLE payroll_params ADD COLUMN {name} {ddl}"))
    db.commit()


MIGRATIONS.append(("0206_tran_gio_tang_ca", _migrate_tran_gio_tang_ca))


def _migrate_phieu_chi_tu_tam_ung(db: Session) -> None:
    """`payment_vouchers.salary_advance_id` — phiếu chi lập TỪ phiếu tạm ứng lương đã duyệt.
    Chủ chốt 18/08/2026.

    Chỉ ADD COLUMN + UNIQUE INDEX. Không backfill: phiếu chi cũ đều từ đơn mua hàng hoặc chi
    độc lập, không có phiếu tạm ứng nguồn.

    UNIQUE ⇒ một phiếu tạm ứng chỉ lập được ĐÚNG MỘT phiếu chi. Đây là chốt chống chi hai lần
    ở tầng DB, không chỉ ở tầng service — service có thể bị hai request chạy song song lách qua.
    KHÔNG dựng FK ở migration (SQLite của test không ALTER được FK); ràng buộc xoá đã chặn ở
    service, còn `create_all` trên DB trắng thì model tự dựng FK."""
    insp = inspect(db.get_bind())
    if "payment_vouchers" not in set(insp.get_table_names()):
        return
    if "salary_advance_id" not in _existing_columns(insp, "payment_vouchers"):
        db.execute(text("ALTER TABLE payment_vouchers ADD COLUMN salary_advance_id INTEGER"))
        db.commit()
    idx = {i["name"] for i in insp.get_indexes("payment_vouchers")}
    if "uq_payment_voucher_salary_advance" not in idx:
        db.execute(text(
            "CREATE UNIQUE INDEX uq_payment_voucher_salary_advance "
            "ON payment_vouchers (salary_advance_id)"
        ))
        db.commit()


MIGRATIONS.append(("0207_phieu_chi_tu_tam_ung", _migrate_phieu_chi_tu_tam_ung))


def _migrate_go_cho_lich_may(db: Session) -> None:
    """Rút `work_shifts.dung_cho_lich_may` — lịch xưởng ăn thẳng mọi ca `is_active`.

    ⚠️ SỐ ĐO TRƯỚC KHI XOÁ (Postgres dev, 21/08/2026): `work_shifts` 4 dòng · `is_active` 4 dòng ·
    `dung_cho_lich_may` **0 dòng**. Cột không mang một bit thông tin nào vì chưa bao giờ có đường
    ghi: không có trong `WorkShiftIn`/`WorkShiftOut`, frontend 0 chỗ nhắc, seeder không đặt. Nơi
    ĐỌC duy nhất là `XepLichService._ca_lich_may()` — và vì cờ luôn FALSE nên nó luôn thấy tập ca
    RỖNG rồi rơi về fallback 08:00–16:00, trong khi xưởng đã khai đủ Ca 1 (06–14) · Hành chính
    (08–17) · Ca 2 (14–22) · Ca 3 (22–06). Chủ chốt chọn "bỏ cờ" ngày 21/08/2026.

    DROP best-effort như mg `0198`/`0215`: SQLite cũ từ chối thì cột mồ côi vô hại vì model đã hết
    map nó. Idempotent; no-op khi bảng/cột không còn.
    """
    insp = inspect(db.get_bind())
    if "work_shifts" not in set(insp.get_table_names()):
        return
    if "dung_cho_lich_may" not in _existing_columns(insp, "work_shifts"):
        return
    try:
        db.execute(text("ALTER TABLE work_shifts DROP COLUMN dung_cho_lich_may"))
        db.commit()
    except Exception:
        db.rollback()


MIGRATIONS.append(("0226_go_cho_lich_may", _migrate_go_cho_lich_may))


def _migrate_giao_hang_module_va_hai_o_chi_tiet(db) -> None:
    """Phân hệ Giao hàng: khoá module `giao_hang` + hai ô quyền chi tiết.

    Sáu bảng dữ liệu của phân hệ đều MỚI ⇒ `create_all` tự dựng, không cần migration. Migration
    này chỉ lo hai thứ `create_all` KHÔNG làm được:

      1. `role_permissions.can_plan`        — tab "Yêu cầu chờ lên kế hoạch" + nút phân công tài xế
      2. `role_permissions.can_view_drivers`— tab "Nhân viên giao hàng" (lịch + KPI người khác)

    Hai cột này thêm vào bảng CŨ nên bắt buộc ALTER; `create_all` chỉ TẠO bảng, không ALTER.

    KHÔNG rót quyền cho vai nào: `giao_hang` là phân hệ mới, chưa ai đang làm việc trên nó nên
    không có "hiện trạng" nào phải giữ. HCNS cấp tay cho vai Giao hàng / Bán hàng khi bắt đầu
    dùng — khác hẳn mg 0198 (ở đó 17 vai ĐANG dùng màn Lương nên phải rót để không ai mất việc).
    """
    insp = inspect(db.get_bind())
    if "role_permissions" not in insp.get_table_names():
        return
    co = _existing_columns(insp, "role_permissions")
    for ten in ("can_plan", "can_view_drivers"):
        if ten not in co:
            db.execute(text(
                f"ALTER TABLE role_permissions ADD COLUMN {ten} BOOLEAN NOT NULL DEFAULT FALSE"))
    db.commit()

    if "modules" in insp.get_table_names():
        # `created_at` là NOT NULL và default nằm ở tầng Python (ORM), không phải server_default ⇒
        # SQL thuần phải tự điền, nếu không là IntegrityError ngay trên DB trắng. Cùng khuôn các
        # migration danh mục module trước đó.
        db.execute(
            text("INSERT INTO modules (key, label, created_at) "
                 "SELECT :k, :l, CURRENT_TIMESTAMP "
                 "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"),
            {"k": "giao_hang", "l": "Giao hàng"},
        )
        db.commit()


MIGRATIONS.append(("0199_giao_hang_module_va_hai_o_chi_tiet",
                   _migrate_giao_hang_module_va_hai_o_chi_tiet))


def _migrate_yeu_cau_kho_nho_chuyen_giao(db) -> None:
    """`stock_requests.delivery_trip_id` — nối yêu cầu XUẤT với chuyến giao hàng sinh ra nó.

    Vì sao đi đường này: giao hàng cũng phải có phiếu kho như mọi thứ khác ra khỏi kho (chủ chốt
    19/08/2026). Thay vì dựng một loại chứng từ song song, Giao hàng lập ĐÚNG một yêu cầu xuất
    kho bình thường — kho lập phiếu, ghi sổ, trừ tồn y hệt vật tư, KHÔNG phải học gì mới và
    KHÔNG một dòng code nào bên kho bị sửa.

    Cột này chỉ để Giao hàng đọc NGƯỢC: chuyến này đã gửi yêu cầu chưa, kho đang tới đâu. Cùng
    khuôn `purchase_delivery_id` mà Mua hàng đã dùng từ mg 0189 — không phát minh gì mới.

    ⚠️ Tên cột phải có mặt trong `_HEADER_FIELDS` của `stock_request_repo` — thiếu là giá trị bị
    NUỐT IM LẶNG: yêu cầu vẫn tạo, chỉ không nối về đâu cả. Đã cắn đúng vậy 19/08/2026.

    Ghi chú: mg `0200` (gộp ba trạng thái kho của `delivery_issue_requests`) ĐÃ GỠ cùng lượt —
    nó chuyển dữ liệu cho một chứng từ song song mà quyết định này xoá hẳn. DB nào đã chạy 0200
    thì vô hại: bảng `delivery_issue_requests` ở lại như dữ liệu chết, không model nào đọc.
    """
    insp = inspect(db.get_bind())
    if "stock_requests" not in insp.get_table_names():
        return
    if "delivery_trip_id" in _existing_columns(insp, "stock_requests"):
        return
    db.execute(text("ALTER TABLE stock_requests ADD COLUMN delivery_trip_id INTEGER"))
    db.commit()
    # Index rời: truy vấn "chuyến này đã gửi yêu cầu chưa" chạy mỗi lần mở màn Giao hàng.
    try:
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_stock_requests_delivery_trip_id "
            "ON stock_requests (delivery_trip_id)"
        ))
        db.commit()
    except Exception:
        # SQLite cũ / quyền hạn chế — thiếu index chỉ chậm, không sai.
        db.rollback()


MIGRATIONS.append(("0201_yeu_cau_kho_nho_chuyen_giao", _migrate_yeu_cau_kho_nho_chuyen_giao))


def _migrate_dong_yeu_cau_giao_mang_mat_hang_kho(db) -> None:
    """`delivery_request_lines` mang luôn `(hang_loai, hang_id, dvt)` của mặt hàng kho.

    Vì sao: dòng đơn hàng bán chỉ có CHỮ TỰ DO, không trỏ danh mục kho. Không lưu mắt xích này
    thì mỗi lần gửi yêu cầu xuất kho lại phải gõ tay mặt hàng — chủ chốt 19/08/2026: *"nó yêu cầu
    cái gì thì phải điền đúng sản phẩm đó vào chứ… điền thay cho mình mà không cho sửa"*.

    Chọn một lần lúc lập yêu cầu giao, từ đó bước xuất kho điền tự động và khoá cứng.
    Nullable: dòng lập trước migration này chưa có mặt hàng, phải sửa yêu cầu để khai bù.
    """
    insp = inspect(db.get_bind())
    if "delivery_request_lines" not in insp.get_table_names():
        return
    co = _existing_columns(insp, "delivery_request_lines")
    pg = db.get_bind().dialect.name == "postgresql"
    for ten, kieu in (("hang_loai", "VARCHAR(8)"), ("hang_id", "INTEGER"), ("dvt", "VARCHAR(24)")):
        if ten not in co:
            db.execute(text(f"ALTER TABLE delivery_request_lines ADD COLUMN {ten} {kieu}"))
    db.commit()
    if pg:
        try:
            db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_delivery_request_lines_hang "
                "ON delivery_request_lines (hang_loai, hang_id)"
            ))
            db.commit()
        except Exception:
            db.rollback()


MIGRATIONS.append(("0202_dong_yeu_cau_giao_mang_mat_hang_kho",
                   _migrate_dong_yeu_cau_giao_mang_mat_hang_kho))


def _migrate_thanh_pham_menu_rieng(db) -> None:
    """Danh mục THÀNH PHẨM — menu riêng, bảng chung (docs/prd-thanh-pham.md).

    Hai cột soft-ref trên `vat_tu_in_an` + khoá quyền `dm_thanh_pham`.

    Vì sao chung bảng: kho chỉ trỏ được vào `hang_loai` mà nó biết ("giay" | "vat_tu"). Bảng
    riêng ⇒ giá trị thứ ba ⇒ phải sửa 4 cổng chặn, 3 bảng tra, 1 chỗ FE chia quyền nhị phân
    (`KhoTonKhoPage.tsx:1084` — chỗ này ăn nhầm quyền IM LẶNG), cộng stock_lots ·
    stock_vouchers · stock_requests · purchase. Toàn code bên kho, mà kho không cần biết gì về
    thành phẩm cả.

    Quyền CHÉP TỪ `dm_vat_tu`: ai đang khai vật tư thì khai được thành phẩm. Không chép thì sau
    deploy menu hiện ra mà không vai nào vào được, kể cả admin.
    """
    insp = inspect(db.get_bind())
    if "vat_tu_in_an" not in insp.get_table_names():
        return

    co = _existing_columns(insp, "vat_tu_in_an")
    for ten in ("order_id", "order_line_id"):
        if ten not in co:
            db.execute(text(f"ALTER TABLE vat_tu_in_an ADD COLUMN {ten} INTEGER"))
    db.commit()

    try:
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vat_tu_in_an_order_line_id "
            "ON vat_tu_in_an (order_line_id)"
        ))
        db.commit()
    except Exception:
        # SQLite cũ / quyền hạn chế — thiếu index chỉ chậm, không sai.
        db.rollback()

    if "modules" not in insp.get_table_names():
        return
    db.execute(
        text("INSERT INTO modules (key, label, created_at) "
             "SELECT :k, :l, CURRENT_TIMESTAMP "
             "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"),
        {"k": "dm_thanh_pham", "l": "Thành phẩm"},
    )
    db.commit()

    if "role_permissions" not in insp.get_table_names():
        return
    cot = _existing_columns(insp, "role_permissions")
    # Chép NGUYÊN hàng quyền của `dm_vat_tu`, chỉ đổi `module_key`. Liệt kê cột động vì bảng này
    # đã thêm cờ nhiều lần (can_export, can_approve…) — hard-code là vỡ ở lần thêm cờ tiếp theo.
    bo_qua = {"id", "module_key", "created_at", "updated_at"}
    chep = [c for c in cot if c not in bo_qua]
    if "module_key" not in cot or not chep:
        return
    ds = ", ".join(chep)
    db.execute(text(
        f"INSERT INTO role_permissions (module_key, {ds}) "
        f"SELECT 'dm_thanh_pham', {ds} FROM role_permissions WHERE module_key = 'dm_vat_tu' "
        "AND NOT EXISTS (SELECT 1 FROM role_permissions WHERE module_key = 'dm_thanh_pham')"
    ))
    db.commit()


MIGRATIONS.append(("0203_thanh_pham_menu_rieng", _migrate_thanh_pham_menu_rieng))


def _migrate_thanh_pham_theo_khach(db) -> None:
    """`vat_tu_in_an.customer_id` — CHỦ của thành phẩm, và là công tắc chia hai màn danh mục.

    Sửa mg 0203 (docs/prd-thanh-pham.md §5 L2). Bản đó lấy khoá định danh là `order_line_id`, nên
    khách đặt lại món cũ là đẻ dòng danh mục THỨ HAI cùng tên. Nặng nhất không phải danh mục
    phình mà là **tồn kho bị xé đôi**: hàng dư đợt trước nằm ở dòng một, hàng in đợt này nằm ở
    dòng hai, và kho không trả lời được "còn bao nhiêu món này".

    Khoá đúng là `(khách, tên đã chuẩn hoá)`. Có KHÁCH trong khoá là bắt buộc — hai khách đều có
    thể đặt "Tờ hướng dẫn sử dụng — gấp 3" mà là hai file in khác hẳn.

    Migration làm ba việc:
      1. thêm cột + index;
      2. suy `customer_id` cho dòng cũ qua `order_id` (dòng nào không suy được thì để NULL — nó
         rơi về màn Vật tư khác, thấy ngay, hơn là biến mất khỏi cả hai màn);
      3. KHÔNG tự gộp dòng trùng. Gộp là phải dồn lô tồn và sửa phiếu đã ghi sổ — việc đó không
         được làm im lặng trong migration. Trùng thì người dùng tắt `active` dòng thừa.
    """
    insp = inspect(db.get_bind())
    if "vat_tu_in_an" not in insp.get_table_names():
        return

    if "customer_id" not in _existing_columns(insp, "vat_tu_in_an"):
        db.execute(text("ALTER TABLE vat_tu_in_an ADD COLUMN customer_id INTEGER"))
        db.commit()
    try:
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vat_tu_in_an_customer_id "
            "ON vat_tu_in_an (customer_id)"
        ))
        db.commit()
    except Exception:
        db.rollback()


    if "orders" not in insp.get_table_names():
        return
    # Dòng do mg 0203 sinh ra: có `order_id`, chưa có `customer_id`. Suy chủ từ đơn.
    db.execute(text(
        "UPDATE vat_tu_in_an SET customer_id = ("
        "  SELECT o.customer_id FROM orders o WHERE o.id = vat_tu_in_an.order_id"
        ") WHERE customer_id IS NULL AND order_id IS NOT NULL"
    ))
    db.commit()


MIGRATIONS.append(("0204_thanh_pham_theo_khach", _migrate_thanh_pham_theo_khach))


def _migrate_bo_phan_giao_hang(db) -> None:
    """`departments.la_giao_hang` — bộ phận GIAO HÀNG, nền cho tab Nhân viên giao hàng.

    Cùng khuôn `la_san_xuat` / `la_kinh_doanh`: cờ đặt ở phòng nào thì cả cây con thừa hưởng.

    Vì sao cần: tab Nhân viên giao hàng trước đó lọc theo QUYỀN RBAC rồi bỏ qua ai chưa có chuyến
    — tài xế mới tuyển không hiện ra, mà không hiện thì không ai phân chuyến được cho họ. Khai
    bộ phận là cách người dùng nghĩ, và nó nằm sẵn trên màn Phòng ban.

    ⚠️ Boolean thì `server_default` phải là `false` (bool của Python), KHÔNG phải chuỗi "0" —
    chuỗi chạy được trên SQLite nhưng vỡ khi Postgres `create_all` trên DB trắng.
    """
    insp = inspect(db.get_bind())
    if "departments" not in insp.get_table_names():
        return
    if "la_giao_hang" in _existing_columns(insp, "departments"):
        return
    db.execute(text(
        "ALTER TABLE departments ADD COLUMN la_giao_hang BOOLEAN NOT NULL DEFAULT false"
    ))
    db.commit()


MIGRATIONS.append(("0205_bo_phan_giao_hang", _migrate_bo_phan_giao_hang))


def _migrate_hoa_hong_kinh_doanh(db) -> None:
    """Hoa hồng KD (docs/redesign-luong-kinh-doanh.md §4.6): `orders.commission_pct` + khoản danh mục.

    Ô `%` của NHÂN VIÊN đã có từ mg 0128 (`employee_salaries.commission_pct`) nhưng engine lương
    KHÔNG đọc — khai bao nhiêu cũng không ra một đồng. Migration này lắp hai mắt xích còn thiếu:

      1. `orders.commission_pct` — % CHỤP vào từng đơn lúc chốt (đổi % người ta từ tháng sau
         không được sửa ngược hoa hồng đơn cũ);
      2. khoản danh mục `HOA_HONG_KD` — chỗ tiền hiện lên phiếu lương. Đi qua danh mục chứ không
         thêm cột `payroll_lines.hoa_hong`: cột kiểu đó (`thuong_doanh_so`) đã bị chặn ghi mới từ
         28/07/2026 vì cờ "Chịu thuế" phải là quy tắc khai được, không phải hằng số trong engine.

    `is_taxable=true` (hoa hồng là thu nhập chịu thuế TNCN) · `in_insurance_base=false` (không vào
    gốc đóng BHXH).
    """
    insp = inspect(db.get_bind())
    ten_bang = set(insp.get_table_names())

    if "orders" in ten_bang and "commission_pct" not in _existing_columns(insp, "orders"):
        db.execute(text(
            "ALTER TABLE orders ADD COLUMN commission_pct NUMERIC(6,4) NOT NULL DEFAULT 0"
        ))
        db.commit()

    if "payroll_components" not in ten_bang:
        return
    cot = _existing_columns(insp, "payroll_components")
    # Liệt kê cột động: bảng này đã thêm cờ vài lần, hard-code là vỡ ở lần thêm cờ tiếp theo.
    gia_tri = {
        "code": "hoa_hong_kd", "name": "Hoa hồng kinh doanh", "kind": "thu",
        "is_taxable": True, "in_insurance_base": False, "is_active": True, "sort_order": 50,
        "note": "Hệ tự tính theo hoá đơn bán trong kỳ — không gõ tay.",
    }
    dung = {k: v for k, v in gia_tri.items() if k in cot}
    ten_cot = ", ".join(dung)
    tham_so = ", ".join(f":{k}" for k in dung)
    # `created_at` NOT NULL mà KHÔNG có server default ⇒ phải tự điền. Đã cắn đúng bẫy này ở
    # mg 0199 với `modules.created_at`.
    if "created_at" in cot:
        ten_cot += ", created_at"
        tham_so += ", CURRENT_TIMESTAMP"
    db.execute(
        text(f"INSERT INTO payroll_components ({ten_cot}) SELECT {tham_so} "
             "WHERE NOT EXISTS (SELECT 1 FROM payroll_components WHERE code = :code)"),
        dung,
    )
    db.commit()


MIGRATIONS.append(("0227_hoa_hong_kinh_doanh", _migrate_hoa_hong_kinh_doanh))


def _migrate_thanh_pham_co_rieng(db) -> None:
    """Thành phẩm KHÔNG còn thuộc về một khách (chủ chốt 21/08/2026).

    "Thành phẩm này là một cái tên hàng mới nêu chưa khai để tái sử dụng, tránh phình lên" — tức
    nó là một CÁI TÊN dùng chung, giống bán cùng một cái quạt cho nhiều khách.

    Trước đợt này `vat_tu_in_an.customer_id` gánh ba việc: chủ · CÔNG TẮC chia màn Thành phẩm với
    Vật tư khác · phạm vi gộp trùng `(khách, tên)`. Bỏ ô Khách khỏi form thì công tắc mất, và mọi
    dòng khai mới sẽ rơi sang màn Vật tư rồi biến mất khỏi màn vừa tạo nó — không lỗi, chỉ mất
    tích. Nên phải có cột cờ RIÊNG trước đã.

    ⚠️ NẠP LẠI CỜ cho các dòng đang có. Thiếu bước này thì mọi thành phẩm cũ tụt về `false` và
    biến khỏi màn Thành phẩm ngay lần deploy đầu — dữ liệu còn nguyên nhưng không ai tìm ra.

    KHÔNG drop `customer_id`: giữ để tra "đơn đầu tiên của khách nào", và để đảo lại được nếu
    chủ đổi ý. Chỉ ngưng dùng nó làm khoá.
    """
    insp = inspect(db.get_bind())
    if "vat_tu_in_an" not in set(insp.get_table_names()):
        return
    if "la_thanh_pham" in _existing_columns(insp, "vat_tu_in_an"):
        return
    db.execute(text(
        "ALTER TABLE vat_tu_in_an ADD COLUMN la_thanh_pham BOOLEAN NOT NULL DEFAULT false"
    ))
    db.commit()
    db.execute(text(
        "UPDATE vat_tu_in_an SET la_thanh_pham = true WHERE customer_id IS NOT NULL"
    ))
    db.commit()


MIGRATIONS.append(("0228_thanh_pham_co_rieng", _migrate_thanh_pham_co_rieng))


def _migrate_mot_yeu_cau_mot_chuyen(db) -> None:
    """MỘT yêu cầu giao = MỘT chuyến (chủ chốt 22/08/2026).

    Cổng ở service đã chặn, nhưng cổng service chỉ giữ được đường đi qua service. Ràng buộc ở CSDL
    là thứ duy nhất giữ được khi có ai đó thêm đường ghi mới, hoặc sửa tay dữ liệu.

    Dữ liệu hiện tại đã thoả (đếm 22/08/2026: 3 yêu cầu / 3 chuyến, 0 yêu cầu có quá 1 chuyến) nên
    không cần dọn trước. Nếu về sau dựng lại từ dữ liệu cũ mà vướng, phải dọn TRƯỚC khi chạy —
    không tự ý xoá chuyến, vì mỗi chuyến là một lần xe đã lăn bánh.
    """
    insp = inspect(db.get_bind())
    if "delivery_trips" not in set(insp.get_table_names()):
        return
    ten = "uq_delivery_trips_request"
    if any(ix.get("name") == ten for ix in insp.get_indexes("delivery_trips")):
        return
    db.execute(text(f"CREATE UNIQUE INDEX {ten} ON delivery_trips (request_id)"))
    db.commit()


MIGRATIONS.append(("0229_mot_yeu_cau_mot_chuyen", _migrate_mot_yeu_cau_mot_chuyen))


def _migrate_giao_hang_dinh_kem(db) -> None:
    """File minh chứng của chuyến giao — ảnh/PDF (chủ chốt 22/08/2026).

    Hàng đi kèm hoá đơn: trước lúc đi đính hoá đơn cho tài xế cầm theo, giao xong chụp lại tờ
    khách đã ký. Bytes nằm ở kho file dùng chung, bảng này chỉ giữ metadata — mirror
    `payment_receipt_attachments`.
    """
    insp = inspect(db.get_bind())
    ten_bang = set(insp.get_table_names())
    if "delivery_trips" not in ten_bang or "delivery_trip_attachments" in ten_bang:
        return
    db.execute(text("""
        CREATE TABLE delivery_trip_attachments (
            id            SERIAL PRIMARY KEY,
            trip_id       INTEGER NOT NULL REFERENCES delivery_trips(id) ON DELETE CASCADE,
            file_name     VARCHAR(255) NOT NULL,
            file_url      VARCHAR(500) NOT NULL,
            file_type     VARCHAR(100),
            uploaded_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
            uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text(
        "CREATE INDEX ix_delivery_trip_attachments_trip ON delivery_trip_attachments (trip_id)"
    ))
    db.commit()


MIGRATIONS.append(("0230_giao_hang_dinh_kem", _migrate_giao_hang_dinh_kem))


def _migrate_khoan_km_giao_hang(db) -> None:
    """Khoán km cho tài xế (chủ chốt 24/08/2026) — xem `docs/prd-khoan-km-giao-hang.md`.

    Tài xế ăn lương chấm công CỘNG tiền theo km. Đo bảng lương thật T05/2026: phần km 19–22 tr
    trong khi lương cứng chỉ ~5 tr — tức đây là thu nhập CHÍNH của họ, đang tính tay ngoài hệ.

    Ba ô cấu hình để ở PHÒNG BAN, ngay dưới cờ `la_giao_hang`: đơn giá + tỷ lệ chia cho kíp xe
    (1 tài xế + 1 phụ xe). Không tách sang màn khác — một nhóm thiết lập thì ở một chỗ.

    Bốn cột trên chuyến: người phụ xe, và BA SỐ CHỤP LẠI lúc ghi kết quả (đơn giá + hai tỷ lệ).
    Chụp là bắt buộc: đổi đơn giá tháng sau mà kỳ trước tự nhảy theo thì bảng lương đã chốt biến
    thành số khác — đúng bài học `orders.commission_pct` ngày 21/08.

    Đơn giá seed 4.330 đ/km = 84.031.992 đ ÷ 19.406 km, tức mức giữ NGUYÊN tổng chi hiện tại của
    cả bốn xe. Tỷ lệ 60/40 là con số chủ đưa.
    """
    insp = inspect(db.get_bind())
    ten_bang = set(insp.get_table_names())

    if "departments" in ten_bang:
        cot = _existing_columns(insp, "departments")
        for ten, kieu in (("don_gia_km", "NUMERIC(14,2) NOT NULL DEFAULT 0"),
                          ("pct_tai_xe", "NUMERIC(5,2) NOT NULL DEFAULT 60"),
                          ("pct_phu_xe", "NUMERIC(5,2) NOT NULL DEFAULT 40")):
            if ten not in cot:
                db.execute(text(f"ALTER TABLE departments ADD COLUMN {ten} {kieu}"))
        # Phòng đang bật cờ Giao hàng thì nạp sẵn đơn giá, khỏi phải đi khai lại tay.
        if "la_giao_hang" in cot:
            db.execute(text("UPDATE departments SET don_gia_km = 4330 "
                            "WHERE la_giao_hang = true AND don_gia_km = 0"))

    if "delivery_trips" in ten_bang:
        cot = _existing_columns(insp, "delivery_trips")
        for ten, kieu in (
            ("phu_xe_employee_id", "INTEGER REFERENCES employees(id)"),
            # NULL = chuyến CŨ, chạy trước khi có tính năng ⇒ engine bỏ qua, không tự đẻ tiền
            # ngược cho quá khứ. Khác hẳn 0: 0 là "đã chụp, và bằng 0".
            ("don_gia_km", "NUMERIC(14,2)"),
            ("pct_tai_xe", "NUMERIC(5,2)"),
            ("pct_phu_xe", "NUMERIC(5,2)"),
        ):
            if ten not in cot:
                db.execute(text(f"ALTER TABLE delivery_trips ADD COLUMN {ten} {kieu}"))
        if "phu_xe_employee_id" not in cot:
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_delivery_trips_phu_xe "
                            "ON delivery_trips (phu_xe_employee_id)"))

    # Tiền khoán km là MỘT CỘT trên dòng lương, KHÔNG phải một dòng trong "Danh mục khoản thu nhập".
    #
    # ⭐ Bản nháp migration này từng seed một khoản `khoan_km_gh` vào danh mục — tức lặp lại đúng
    # cái lỗi vừa sửa xong cùng ngày với hoa hồng. Màn danh mục là chỗ HCNS khai phụ cấp/thưởng rồi
    # gán cho TỪNG NGƯỜI, thêm xoá thoải mái; nhét khoản hệ thống vào đó là đặt một cái công tắc
    # toàn hệ thống ngay cạnh nút xoá.
    #
    # Lý do duy nhất khiến hoa hồng phải là "dòng khoản" là để hiện trong "Khoản phát sinh tháng
    # này". Khoán km không cần: nó không sửa tay được. Mà mọi tiền engine tự tính khác đều đã là
    # cột sẵn — `khoan`, `ot_pay`, `night_pay`, `chuyen_can`, `meal_allowance_pay`… Làm cột là về
    # đúng nhà, không phải phá lệ.
    if "payroll_lines" in ten_bang:
        if "khoan_km" not in _existing_columns(insp, "payroll_lines"):
            db.execute(text(
                "ALTER TABLE payroll_lines ADD COLUMN khoan_km NUMERIC(14,2) NOT NULL DEFAULT 0"
            ))
    db.commit()


MIGRATIONS.append(("0231_khoan_km_giao_hang", _migrate_khoan_km_giao_hang))


def _migrate_khoan_km_cot_luong(db) -> None:
    """VÁ cột `payroll_lines.khoan_km` cho DB đã chạy 0231 TRƯỚC khi phần này được thêm vào.

    Vì sao cần một migration RIÊNG thay vì sửa 0231: 0231 chạy lần đầu (trên DB dev) khi thân nó
    mới có `departments` + `delivery_trips`; cột `payroll_lines.khoan_km` được thêm vào thân 0231
    SAU đó. Nhưng `run_migrations` bỏ qua mọi id đã nằm trong `schema_migrations`, nên phần thêm
    sau KHÔNG bao giờ chạy trên DB đã applied 0231 — bảng lương query cột không tồn tại ⇒ 500.

    Bài học (đã cắn 24/08/2026): sửa thân một migration ĐÃ applied là vô hình với mọi DB đã chạy
    nó. Thay đổi schema mới LUÔN là một migration mới.

    Idempotent: DB fresh chạy 0231 (thân hiện tại đã có cột) rồi tới đây thấy cột có → bỏ qua.
    Test dùng `create_all` dựng cột thẳng từ model → cũng bỏ qua.
    """
    insp = inspect(db.get_bind())
    if "payroll_lines" not in set(insp.get_table_names()):
        return
    if "khoan_km" in _existing_columns(insp, "payroll_lines"):
        return
    db.execute(text(
        "ALTER TABLE payroll_lines ADD COLUMN khoan_km NUMERIC(14,2) NOT NULL DEFAULT 0"
    ))
    db.commit()


MIGRATIONS.append(("0232_khoan_km_cot_luong", _migrate_khoan_km_cot_luong))


def _migrate_work_shift_ca_san_xuat(db: Session) -> None:
    """`work_shifts.ca_san_xuat` — ca nào CHẠY DƯỚI XƯỞNG, ca nào chỉ để chấm công.

    Vì sao cần: mẫu số đo % tải máy là "một ngày xưởng có bao nhiêu phút được ca phủ". Xưởng khai
    Ca 1 (06–14) · Ca 2 (14–22) · Ca 3 (22–06) · Hành chính (08–17); ba ca đầu là người đứng máy,
    cái thứ tư là văn phòng. Hôm nay Hành chính nằm GỌN trong Ca 1 + Ca 2 nên không nới thêm phút
    nào — nhưng đó là MAY chứ không phải thiết kế: tắt Ca 2 đi thì giờ xưởng còn 06–14 (8 tiếng) mà
    Hành chính kéo mẫu số tới 17:00 (11 tiếng) ⇒ mọi % tải thấp giả 27%.

    ⚠ Mặc định TRUE và backfill TRUE cho MỌI dòng đang có ⇒ migration chạy xong KHÔNG đổi một con
    số nào. Muốn ca văn phòng thôi tính vào lịch xưởng thì vào Nhân sự → Ca kíp bỏ tick — một cú
    click, đảo lại được. CỐ Ý không đoán theo TÊN ca ("Hành chính"): tên là dữ liệu người dùng gõ,
    xưởng khác gọi "Giờ HC" hay "Văn phòng" là trật.

    Đây là bản THỨ HAI của cờ này. Bản đầu `dung_cho_lich_may` (mg 0095) chết ở mg 0226 vì mặc định
    TẮT mà không có đường khai ⇒ 4/4 ca FALSE ⇒ engine thấy tập ca rỗng rồi rơi về fallback
    08:00–16:00. Lần này: (1) mặc định BẬT, (2) có ô ở màn Ca kíp + `WorkShiftIn/Out`, (3)
    `_ca_lich_may()` không ca nào bật thì dùng TẤT CẢ ca đang dùng — hết đường rơi về 8h.

    Chỉ ADD COLUMN DEFAULT — idempotent, no-op trên DB fresh (create_all đã dựng)."""
    insp = inspect(db.get_bind())
    if "work_shifts" not in set(insp.get_table_names()):
        return
    if "ca_san_xuat" in _existing_columns(insp, "work_shifts"):
        return
    db.execute(text(
        "ALTER TABLE work_shifts ADD COLUMN ca_san_xuat BOOLEAN NOT NULL DEFAULT TRUE"
    ))
    db.commit()


MIGRATIONS.append(("0233_work_shift_ca_san_xuat", _migrate_work_shift_ca_san_xuat))


def _migrate_go_gripper_mm(db: Session) -> None:
    """Rút `may_thiet_bi.gripper_mm` (nhãn UI "Nhíp kẽm").

    Cột này là mép nhíp trên BẢN KẼM (~44mm) — KHÁC nhíp GIẤY (`nhip_giay_mm`, ~10mm) mà engine
    bình bài thực sự dùng để chừa lề tờ in. Engine CỐ Ý không đọc `gripper_mm` (có test canh: dùng
    nhầm nó làm chừa giấy từng hụt 14-19% số con). Ngoài validate E-MAY-NHIP + nhãn nhật ký, không
    tầng nào ăn cột này ⇒ gỡ hẳn khỏi danh mục máy.

    Raw SQL đích danh cột, best-effort, idempotent; no-op khi bảng/cột không còn (DB fresh dựng bằng
    create_all đã không có cột)."""
    insp = inspect(db.get_bind())
    if "may_thiet_bi" not in set(insp.get_table_names()):
        return
    if "gripper_mm" not in _existing_columns(insp, "may_thiet_bi"):
        return
    try:
        db.execute(text("ALTER TABLE may_thiet_bi DROP COLUMN gripper_mm"))
        db.commit()
    except Exception:
        db.rollback()


MIGRATIONS.append(("0234_go_gripper_mm_nhip_kem", _migrate_go_gripper_mm))


def _migrate_huy_tung_dong_ycmh(db: Session) -> None:
    """`department_purchase_request_lines.cancelled_at/_by_user_id/cancel_reason` — huỷ TỪNG MÓN.

    24/08/2026, chủ chốt: *"phải quản tới từng món hàng, đừng quản tới cấp chứng từ nữa"*. Trước
    mốc này việc huỷ chỉ có ở cấp PHIẾU: yêu cầu 5 dòng mà 1 dòng khai thừa thì hoặc huỷ cả phiếu
    (mất 4 dòng Thu mua đang chạy), hoặc để nguyên cho nó nằm đó gây nhiễu bảng cân đối vật tư.

    Sau migration này `department_purchase_requests.status` DẪN XUẤT từ các dòng CÒN SỐNG
    (`cancelled_at IS NULL`); huỷ hết dòng thì phiếu mới về `cancelled`. Dòng đã huỷ giữ lại làm
    vết, không xoá — `purchase_request_lines.department_request_line_id` còn có thể trỏ tới.

    Chỉ ADD COLUMN NULLABLE, không backfill (NULL = còn sống, đúng nghĩa mọi dòng đang có).
    Raw SQL đích danh cột, idempotent, no-op trên DB fresh (create_all đã dựng)."""
    insp = inspect(db.get_bind())
    if "department_purchase_request_lines" not in set(insp.get_table_names()):
        return
    dang_co = _existing_columns(insp, "department_purchase_request_lines")
    them = [
        ("cancelled_at", "TIMESTAMP WITH TIME ZONE"),
        ("cancelled_by_user_id", "INTEGER"),
        ("cancel_reason", "TEXT"),
    ]
    for ten, kieu in them:
        if ten in dang_co:
            continue
        # SQLite không có TIMESTAMP WITH TIME ZONE; nó nhận "TIMESTAMP" và lưu như TEXT.
        kieu_that = "TIMESTAMP" if db.get_bind().dialect.name == "sqlite" else kieu
        db.execute(text(
            f"ALTER TABLE department_purchase_request_lines ADD COLUMN {ten} {kieu_that}"
        ))
    db.commit()


MIGRATIONS.append(("0235_huy_tung_dong_ycmh", _migrate_huy_tung_dong_ycmh))


def _migrate_kho_mm_so_thuc(db: Session) -> None:
    """6 cột mm của `phieu_thanh_phan` — khổ thành phẩm ③, giấy nguyên ①, tờ in ② — INTEGER → NUMERIC(10,2).

    Khổ in THẬT hay lẻ nửa ly: name card 88.9×50.8 (3.5×2 inch), thư mời khổ letter 215.9×279.4,
    bìa cộng gáy 3.5mm, giấy nhập cắt lẻ. Cả engine bình bài (`binh_bai_layout` nhận `float`) lẫn
    ô "Bleed"/"Khe cắt" cạnh bên (đã là Numeric) vốn xử số lẻ được — chỉ SÁU cột này còn INTEGER,
    nên gõ 215.9 là API trả 422 `int_from_float` và ô bình bài live đứng im, không ai hiểu vì sao.

    Nới cột (integer → numeric là cast NGẦM của Postgres, không cần USING, không mất số cũ).
    Raw SQL đích danh cột, idempotent (bỏ qua cột đã NUMERIC), no-op trên SQLite: cột khai
    INTEGER ở SQLite vẫn giữ nguyên 215.9 nhờ affinity, và DB test dựng bằng create_all."""
    bind = db.get_bind()
    if bind.dialect.name == "sqlite":
        return
    insp = inspect(bind)
    if "phieu_thanh_phan" not in set(insp.get_table_names()):
        return
    kieu = {c["name"]: str(c["type"]).upper() for c in insp.get_columns("phieu_thanh_phan")}
    for ten in (
        "dai_thanh_pham", "rong_thanh_pham",
        "kho_nguyen_dai", "kho_nguyen_rong",
        "kho_in_dai", "kho_in_rong",
    ):
        if not kieu.get(ten, "").startswith("INTEGER"):
            continue
        db.execute(text(f"ALTER TABLE phieu_thanh_phan ALTER COLUMN {ten} TYPE NUMERIC(10, 2)"))
    db.commit()


MIGRATIONS.append(("0236_kho_mm_so_thuc", _migrate_kho_mm_so_thuc))


def _migrate_sx_cong_viec_may_khoa_mem(db: Session) -> None:
    """0237 — `san_xuat_cong_viec.may_id`: gỡ KHOÁ NGOẠI CỨNG trỏ `machines`.

    Cột này là ảnh chụp MÁY của bước lúc phát hành, mà máy của bước lấy từ danh mục ĐANG CHẠY
    `may_thiet_bi`; `machines` là danh mục đời tính giá, id hai bảng KHÔNG trùng nhau. Vì thế
    mọi lệnh có bước chạy máy nằm ngoài dải id của `machines` đều vỡ lúc phát hành với
    ``ForeignKeyViolation ... Key (may_id)=(27) is not present in table "machines"`` — và vỡ ở
    GIỮA giao dịch, để lại lệnh kẹt nửa vời (`da_phat_hanh` nhưng không sinh được công việc nào).
    Test không bắt được vì fixture dựng máy thẳng vào `machines` nên id luôn khớp.

    Mọi bảng khác neo máy bằng khoá MỀM (`lsx_cong_doan`, `xep_lich_cong_doan`, `bai_ghep`,
    `ky_thuat_*`). Bước này đưa `san_xuat_cong_viec` về đúng quy ước đó. Tên ràng buộc lấy từ
    catalog thay vì đoán, phòng DB nào đó đặt tên khác.
    """
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    insp = inspect(bind)
    if "san_xuat_cong_viec" not in set(insp.get_table_names()):
        return
    ten_rang_buoc = [
        r[0]
        for r in db.execute(
            text(
                "SELECT tc.constraint_name FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON kcu.constraint_name = tc.constraint_name "
                " AND kcu.table_schema = tc.table_schema "
                "WHERE tc.constraint_type = 'FOREIGN KEY' "
                "  AND tc.table_schema = 'public' "
                "  AND tc.table_name = 'san_xuat_cong_viec' "
                "  AND kcu.column_name = 'may_id'"
            )
        ).all()
    ]
    for ten in ten_rang_buoc:
        db.execute(
            text(f'ALTER TABLE san_xuat_cong_viec DROP CONSTRAINT IF EXISTS "{ten}"')
        )
    db.commit()


MIGRATIONS.append(("0237_sx_cong_viec_may_khoa_mem", _migrate_sx_cong_viec_may_khoa_mem))


def _migrate_stock_lot_sl_scale(db: Session) -> None:
    """Đồng bộ scale tồn lô với dòng phiếu: `stock_lots.sl_ban_dau/sl_con_lai` NUMERIC(14,2) → (14,4).

    Dòng phiếu `stock_voucher_lines.sl_goc` là NUMERIC(14,4) (số quy về đơn vị gốc chảy vào lô);
    lô chỉ 14,2 nên khi ghi sổ NHẬP, Postgres LÀM TRÒN sl_goc về 2dp ⇒ xuất hết vẫn dư ~0.005,
    lô không chuyển 'empty', `SUM(sl_con_lai)` treo bụi (vỡ bất biến tồn = Σ sl_con_lai).

    SQLite KHÔNG ép scale NUMERIC nên no-op ở dev/test; chỉ ALTER trên Postgres. Nới scale (14,2→14,4)
    là mở rộng, không mất dữ liệu. Idempotent: ALTER về đúng type hiện có là vô hại.
    """
    bind = db.get_bind()
    if (bind.dialect.name or "") != "postgresql":
        return
    if "stock_lots" not in inspect(bind).get_table_names():
        return
    db.execute(text("ALTER TABLE stock_lots ALTER COLUMN sl_ban_dau TYPE NUMERIC(14,4)"))
    db.execute(text("ALTER TABLE stock_lots ALTER COLUMN sl_con_lai TYPE NUMERIC(14,4)"))
    db.commit()


MIGRATIONS.append(("0238_stock_lot_sl_scale", _migrate_stock_lot_sl_scale))
