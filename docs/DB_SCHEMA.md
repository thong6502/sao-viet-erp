# DB_SCHEMA.md — Data Dictionary

> **Single source of truth for the DATABASE SCHEMA.** Every table, what it is for, the
> meaning of each column, primary keys, foreign keys, and indexes live here. Code
> structure lives in [ARCHITECTURE.md](ARCHITECTURE.md); visuals in
> [UI_DESIGN.md](UI_DESIGN.md); the **data model** lives in THIS file.

- **Models (the actual definitions):** [`../backend/app/models/`](../backend/app/models/).
- **How the schema is built:** `create_all` in
  [`../backend/app/db.py`](../backend/app/db.py) on startup, then seed in
  [`../backend/app/seed.py`](../backend/app/seed.py). No Alembic migrations yet
  (deferred — see [`product-specs/sprint-01-auth.md`](product-specs/sprint-01-auth.md)).
- **Portability:** the same SQLAlchemy layer runs on **SQLite** (local/test) and
  **PostgreSQL** (Docker/prod). Types below show the SQLAlchemy type and how it maps.

## How to update (REQUIRED on every schema change)

Whenever you **add / change / remove** a table, column, key, or index:

1. Edit the SQLAlchemy model under [`../backend/app/models/`](../backend/app/models/).
2. **Update this file in the SAME change** — add/edit/remove the matching section or row.
3. When Alembic lands, also add a migration; until then `create_all` builds the schema
   (note: `create_all` does **not** alter existing tables — for a changed column on an
   existing dev DB, drop `backend/dev.db` or recreate the Postgres volume to pick it up).
4. Run `./init.ps1` / `./init.sh`. The guard
   [`../backend/tests/test_schema_documented.py`](../backend/tests/test_schema_documented.py)
   **fails** if any model table/column is missing from this file — so docs can't silently
   drift from the models.

**Conventions**

- One `### \`table_name\`` section per table (the test keys off this heading).
- Each table lists: a one-line **Purpose**, a **column table**
  (Column / Type / Key / Null / Default / Meaning), then **Keys & indexes** and
  **Relationships**.
- Mark keys in the `Key` column: `PK` (primary), `FK→table.col` (foreign), `U` (unique),
  `IX` (indexed).

---

## Tables

### `users`

**Purpose:** application accounts that can authenticate. One row per person who can log
in. (Sprint-01: seeded only — no self-registration.)

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key; stable internal id, also the JWT `sub` claim. |
| `email` | `String(255)` → `VARCHAR(255)` | **U**, **IX** | no | — | Login identifier; unique (no two accounts share an email). Indexed for fast lookup at login. |
| `name` | `String(255)` → `VARCHAR(255)` | — | no | `""` | Human display name shown in the UI (e.g. Dashboard greeting). |
| `password_hash` | `String(255)` → `VARCHAR(255)` | — | no | — | **bcrypt** hash of the password (`$2b$...`). The plaintext password is NEVER stored. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the account row was created. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_users_email` on `email` (enforces uniqueness + speeds login lookup).
- Foreign keys: none.

**Relationships**

- None yet. Future per-user data (sessions, roles, owned records) will reference
  `users.id` via a `FK→users.id` column and be documented in that table's section.

---

## Template for a new table (copy when adding one)

```markdown
### `table_name`

**Purpose:** <one line: what this table represents, one row = ?>

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `<col>` | `<type>` | <PK/FK→t.col/U/IX/—> | <yes/no> | <default/—> | <meaning> |

**Keys & indexes**

- Primary key: `<col>`.
- Foreign keys: `<col> FK→<table>.<col>` — <on-delete behavior if any>.
- Indexes: `<name>` on `<cols>` (<unique?> — <why>).

**Relationships**

- <how this table relates to others, e.g. "many `<rows>` belong to one `users`">.
```
