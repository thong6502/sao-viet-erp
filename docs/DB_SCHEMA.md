# DB_SCHEMA.md — Data Dictionary

> **Single source of truth for the DATABASE SCHEMA.** Every table, what it is for, the
> meaning of each column, primary keys, foreign keys, and indexes live here. Code
> structure lives in [ARCHITECTURE.md](ARCHITECTURE.md); visuals in
> [UI_DESIGN.md](UI_DESIGN.md); the **data model** lives in THIS file.

- **Models (the actual definitions):** [`../backend/app/models/`](../backend/app/models/).
- **How the schema is built:** `create_all` in
  [`../backend/app/db.py`](../backend/app/db.py) on startup, then seed in
  [`../backend/app/seed.py`](../backend/app/seed.py). No Alembic migrations yet
  (deferred — see [`product-specs/spec-01-auth.md`](product-specs/spec-01-auth.md)).
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
in. (Spec-01: seeded only — no self-registration.) Login is by `username` (spec-0001).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key; stable internal id, also the JWT `sub` claim. |
| `username` | `String(150)` → `VARCHAR(150)` | **U**, **IX** | no | — | The sole account identity + login credential (spec-0001): users sign in with this. Required + unique (no two accounts share a username). Indexed for fast lookup at login. Email was removed entirely. |
| `name` | `String(255)` → `VARCHAR(255)` | — | no | `""` | Human display name shown in the UI (e.g. Dashboard greeting). |
| `password_hash` | `String(255)` → `VARCHAR(255)` | — | no | — | **bcrypt** hash of the password (`$2b$...`). The plaintext password is NEVER stored. |
| `department_id` | `Integer` → `INTEGER` | **FK→departments.id**, **IX** | yes | — | The department (phòng ban) this user belongs to. Null until HR assigns one. |
| `role_id` | `Integer` → `INTEGER` | **FK→roles.id**, **IX** | yes | — | The single role (vai trò) this user holds; its permissions decide access. Null until the department head assigns one. |
| `is_active` | `Boolean` → `BOOLEAN` | — | no | `true` | Whether the account is enabled. A locked (`false`) user is rejected even with a valid token. |
| `token_version` | `Integer` → `INTEGER` | — | no | `0` | Hard-revoke counter (spec-03). Access tokens embed this as the `tv` claim; bumping it rejects every previously-issued access token (logout-all / forced invalidation). |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the account row was created. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_users_username` on `username` (the login identifier; uniqueness + fast login lookup).
- Indexes: `ix_users_department_id` on `department_id`, `ix_users_role_id` on `role_id`.
- Foreign keys: `department_id FK→departments.id`, `role_id FK→roles.id`.

**Relationships**

- Many users belong to one `departments` (via `department_id`) and hold one `roles`
  (via `role_id`). A user is referenced back by `departments.head_user_id` (the trưởng
  phòng) and by `audit_logs.actor_user_id` (who performed an action).

---

### `departments`

**Purpose:** organizational departments (phòng ban). One row per department; a user
belongs to exactly one, and roles are defined per department.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `name` | `String(255)` → `VARCHAR(255)` | **U**, **IX** | no | — | Department name (e.g. "Kinh doanh"); unique. |
| `head_user_id` | `Integer` → `INTEGER` | — | yes | — | Logical reference to `users.id` of the trưởng phòng (no DB-level FK to avoid a create cycle; assigned via Alembic later). |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the department row was created. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_departments_name` on `name`.
- Foreign keys: none enforced (`head_user_id` is a logical reference to `users.id`).

**Relationships**

- One department has many `roles` and many `users`; `head_user_id` points at the user who heads it.

---

### `roles`

**Purpose:** a named permission bundle (vai trò) belonging to exactly one department.
A user holds exactly one role; its permissions decide access.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `name` | `String(255)` → `VARCHAR(255)` | — | no | — | Role name (e.g. "NV Sales"); unique within its department. |
| `department_id` | `Integer` → `INTEGER` | **FK→departments.id**, **IX** | no | — | The department this role belongs to. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the role row was created. |

**Keys & indexes**

- Primary key: `id`.
- Unique constraint: `uq_roles_name_department` on (`name`, `department_id`).
- Foreign keys: `department_id FK→departments.id`.

**Relationships**

- Many roles belong to one `departments`; a role has many `role_permissions` (one per module) and many `users`.

---

### `role_permissions`

**Purpose:** one row per (role × module): the CRUD flags and the data scope that role
gets on that module.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `role_id` | `Integer` → `INTEGER` | **FK→roles.id**, **IX** | no | — | The role this permission belongs to. |
| `module_key` | `String(64)` → `VARCHAR(64)` | **FK→modules.key** | no | — | The module/resource this permission applies to. |
| `can_read` | `Boolean` → `BOOLEAN` | — | no | `false` | May view (Xem) records of this module. |
| `can_create` | `Boolean` → `BOOLEAN` | — | no | `false` | May create (Thêm) records of this module. |
| `can_update` | `Boolean` → `BOOLEAN` | — | no | `false` | May edit (Sửa) records of this module. |
| `can_delete` | `Boolean` → `BOOLEAN` | — | no | `false` | May delete (Xóa) records of this module. |
| `scope` | `String(16)` → `VARCHAR(16)` | — | no | `own` | Data scope: `own` (của tôi) / `department` (cả phòng) / `all` (tất cả). |

**Keys & indexes**

- Primary key: `id`.
- Unique constraint: `uq_role_permissions_role_module` on (`role_id`, `module_key`).
- Foreign keys: `role_id FK→roles.id`, `module_key FK→modules.key`.

**Relationships**

- Many permission rows belong to one `roles`; each references one `modules` by its `key`.

---

### `modules`

**Purpose:** catalog of system modules/resources that permissions are granted on. Seed
data that grows as new departments come online (adding a module is a new row).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `key` | `String(64)` → `VARCHAR(64)` | **U**, **IX** | no | — | Stable module identifier (e.g. `khach_hang`); referenced by `role_permissions.module_key`. |
| `label` | `String(255)` → `VARCHAR(255)` | — | no | — | Human-readable module name shown in the permission matrix. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the module row was created. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_modules_key` on `key`.
- Foreign keys: none.

**Relationships**

- One module is referenced by many `role_permissions` (via `module_key` → `key`).

---

### `audit_logs`

**Purpose:** one row per privilege-changing action (gán phòng, gán vai trò, sửa khuôn
quyền, khóa tài khoản) for the Activity Log.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `actor_user_id` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | The user who performed the action (null if system/seed). |
| `action` | `String(64)` → `VARCHAR(64)` | — | no | — | Action code (e.g. `assign_role`, `lock_user`). |
| `target` | `String(255)` → `VARCHAR(255)` | — | no | `""` | What the action targeted (e.g. the affected user/role). |
| `detail` | `Text` → `TEXT` | — | no | `""` | Free-text detail / before→after summary. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | **IX** | no | now (UTC) | When the action happened (indexed for time-ordered listing). |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_audit_logs_created_at` on `created_at` (time-ordered listing).
- Foreign keys: `actor_user_id FK→users.id`.

**Relationships**

- Many audit rows reference one `users` (the actor).

---

### `refresh_tokens`

**Purpose:** one row per issued refresh token (spec-03). Backs long-lived sessions and
server-side revocation. Only a hash is stored; the plaintext token lives solely in the
client's httpOnly cookie.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `user_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | no | — | The user this refresh token authenticates. |
| `token_hash` | `String(64)` → `VARCHAR(64)` | **U**, **IX** | no | — | SHA-256 hex digest of the opaque token. The plaintext is NEVER stored. |
| `family_id` | `String(36)` → `VARCHAR(36)` | **IX** | no | — | Rotation-chain id. Reusing a revoked token revokes every sibling in the family (theft signal). |
| `expires_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | — | When this token stops being valid. |
| `revoked_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Set when the token is rotated away or logged out; a non-null value means dead. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the token row was created. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_refresh_tokens_token_hash` on `token_hash`.
- Indexes: `ix_refresh_tokens_user_id` on `user_id`, `ix_refresh_tokens_family_id` on `family_id`.
- Foreign keys: `user_id FK→users.id`.

**Relationships**

- Many refresh tokens belong to one `users`; tokens sharing a `family_id` form one rotation chain.

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
