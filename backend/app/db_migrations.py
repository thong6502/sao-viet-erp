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


def _migrate_imposition_type_full_fields(db: Session) -> None:
    """Add the full spec A–E columns to imposition_types and swap unique(code) →
    unique(code, version). No-op where create_all already built the current shape."""
    bind = db.get_bind()
    insp = inspect(bind)
    if "imposition_types" not in insp.get_table_names():
        return
    dialect = bind.dialect.name

    # (column, DDL fragment). DEFAULT so pre-existing rows satisfy NOT NULL on ADD COLUMN.
    # SQLite (>=3.23) and Postgres both accept TRUE/FALSE and JSON here.
    coldefs = [
        ("group_kind", "VARCHAR(20) NOT NULL DEFAULT 'custom'"),
        ("shared_plate_set", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("technology", "VARCHAR(20) NOT NULL DEFAULT 'offset'"),
        ("applies_to_sides", "VARCHAR(10) NOT NULL DEFAULT 'any'"),
        ("applicable_product_types", "JSON"),
        ("applicable_machine_ids", "JSON"),
        ("applicable_paper_size_ids", "JSON"),
        ("allow_multi_signature", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ("priority", "INTEGER NOT NULL DEFAULT 100"),
        ("version", "INTEGER NOT NULL DEFAULT 1"),
        ("effective_from", "DATE"),
        ("effective_to", "DATE"),
        ("used_count", "INTEGER NOT NULL DEFAULT 0"),
        ("created_by", "INTEGER"),
        ("updated_by", "INTEGER"),
    ]
    existing = _existing_columns(insp, "imposition_types")
    added_group_kind = False
    for name, ddl in coldefs:
        if name not in existing:
            db.execute(text(f"ALTER TABLE imposition_types ADD COLUMN {name} {ddl}"))
            if name == "group_kind":
                added_group_kind = True

    # Backfill Nhóm kiểu from số mặt for rows that predate the column (all default to 'custom').
    if added_group_kind:
        db.execute(text(
            "UPDATE imposition_types "
            "SET group_kind = CASE WHEN sides = 1 THEN 'one_side' ELSE 'two_side' END"
        ))

    # note grew from VARCHAR(255) → Text (mô tả tối đa 2000 ký tự). Widen on an existing
    # Postgres DB so a long description doesn't overflow the old column. SQLite ignores
    # VARCHAR length (TEXT affinity) so no action needed there.
    if dialect == "postgresql":
        db.execute(text("ALTER TABLE imposition_types ALTER COLUMN note TYPE TEXT"))

    # Swap unique(code) → unique(code, version). The OLD model declared `code` as
    # `unique=True, index=True` → a UNIQUE index `ix_imposition_types_code` (on BOTH dialects,
    # not a `_code_key` constraint). Drop it, recreate NON-unique, then add the composite
    # unique index. Both SQLite and Postgres support these `IF [NOT] EXISTS` forms; a no-op on a
    # fresh DB where create_all already produced the current shape.
    if dialect == "postgresql":
        # In case an even older DB used a bare `unique=True` (constraint, not index).
        db.execute(text(
            "ALTER TABLE imposition_types DROP CONSTRAINT IF EXISTS imposition_types_code_key"
        ))
    db.execute(text("DROP INDEX IF EXISTS ix_imposition_types_code"))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_imposition_types_code ON imposition_types (code)"))
    db.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_imposition_code_version "
        "ON imposition_types (code, version)"
    ))

    db.commit()


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

        # Swap unique(code) → unique(code, version) — mirror imposition_types.
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


# Ordered list of (id, fn). Ids are immutable once shipped.
MIGRATIONS: list[tuple[str, callable]] = [
    ("0001_imposition_type_full_fields", _migrate_imposition_type_full_fields),
    ("0002_operation_full_fields", _migrate_operation_full_fields),
    ("0003_norms_waste_groups", _migrate_norms_waste_groups),
    ("0004_paper_size_full_fields", _migrate_paper_size_full_fields),
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
