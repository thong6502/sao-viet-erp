"""Schema-doc guard.

Every table and column defined in the SQLAlchemy models MUST be documented in
docs/DB_SCHEMA.md. This fails the build when the data model and the data dictionary
drift apart, so a schema change can't silently skip its documentation.

Keyed off `### `table_name`` section headings in the doc (see DB_SCHEMA.md
"Conventions").
"""
from __future__ import annotations

from pathlib import Path

import app.models  # noqa: F401  -- importing registers every table on Base.metadata
from app.db import Base

DOC = Path(__file__).resolve().parents[2] / "docs" / "DB_SCHEMA.md"


def _section_for(text: str, table: str) -> str | None:
    """Return the doc slice for a table: from its `### `table`` heading to the next
    `### ` heading (or end of file). None if the table has no section."""
    marker = f"### `{table}`"
    start = text.find(marker)
    if start == -1:
        return None
    rest = text[start + len(marker) :]
    nxt = rest.find("\n### ")
    return rest if nxt == -1 else rest[:nxt]


def test_db_schema_doc_exists():
    assert DOC.exists(), f"Missing data dictionary: {DOC}"


def test_every_table_and_column_is_documented():
    text = DOC.read_text(encoding="utf-8")
    missing: list[str] = []

    for table in Base.metadata.tables.values():
        section = _section_for(text, table.name)
        if section is None:
            missing.append(f"table `{table.name}` has no `### `{table.name}`` section")
            continue
        for col in table.columns:
            if col.name not in section:
                missing.append(f"column `{table.name}.{col.name}` is not documented")

    assert not missing, (
        "docs/DB_SCHEMA.md is out of sync with the models — update it (see its "
        '"How to update" section):\n  ' + "\n  ".join(missing)
    )
