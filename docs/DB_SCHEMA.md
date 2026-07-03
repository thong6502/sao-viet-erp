# DB_SCHEMA.md — Data Dictionary

> **Single source of truth for the DATABASE SCHEMA.** Every table, what it is for, the
> meaning of each column, primary keys, foreign keys, and indexes live here.

- **Models (the actual definitions):** [`../backend/app/models/`](../backend/app/models/).
- **How the schema is built:** `create_all` in
  [`../backend/app/db.py`](../backend/app/db.py) on startup, then seed in
  [`../backend/app/seed.py`](../backend/app/seed.py). No Alembic migrations yet
  (deferred).
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
| `avatar_url` | `String(500)` → `VARCHAR(500)` | — | yes | — | Server-relative path of the user's uploaded profile picture (spec-04), e.g. `/static/avatars/<file>`. Null means no avatar — the UI shows an initials fallback. The plaintext file lives under the backend `static/` dir, not the DB. |
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
| `code` | `String(20)` → `VARCHAR(20)` | **U**, **IX** | no | — | System-generated unique code (spec-05): `PB` + zero-padded sequence (`PB001`, `PB002`, …). Read-only — users never type it; the repository assigns it on create from the highest existing PB-number + 1, and the unique index guarantees no two live departments share a code. |
| `description` | `String(500)` → `VARCHAR(500)` | — | yes | — | Optional free-text description of the department (spec-05). |
| `parent_id` | `Integer` → `INTEGER` | **FK→departments.id**, **IX** | yes | — | Parent department for the org tree (spec-05); null = root unit. A department and its whole subtree are cascade-deleted together (enforced in the service, not the DB). |
| `level_id` | `Integer` → `INTEGER` | **FK→unit_levels.id**, **IX** | yes | — | Organizational tier this unit sits at (spec-06 / PBI-4009); null = untagged. Drives the head's title label (Trưởng khối / Trưởng phòng / Tổ trưởng) and blocks deleting a level still in use. |
| `head_user_id` | `Integer` → `INTEGER` | — | yes | — | Logical reference to `users.id` of the trưởng phòng (no DB-level FK to avoid a create cycle; assigned via Alembic later). |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the department row was created. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_departments_name` on `name`, `ix_departments_code` on `code`.
- Indexes: `ix_departments_parent_id` on `parent_id`, `ix_departments_level_id` on `level_id`.
- Foreign keys: `parent_id FK→departments.id` (self-reference); `level_id FK→unit_levels.id`; `head_user_id` is a logical reference to `users.id` (no enforced FK).

**Relationships**

- One department has many `roles` and many `users`; `head_user_id` points at the user who heads it.
- Departments form a tree via `parent_id` (self-reference): a department has many child departments; deleting a department deletes its whole subtree (spec-05).
- Each department may be tagged with one `unit_levels` tier via `level_id` (spec-06).

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

### `unit_levels`

**Purpose:** catalog of organizational tiers (cấp đơn vị: Khối, Phòng, Tổ, …) — spec-06 /
PBI-4009. One row per tier; a department may be tagged with one via `departments.level_id`.
Admin-declared data (seeded with sensible defaults) that grows as the org model evolves.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `name` | `String(100)` → `VARCHAR(100)` | **U**, **IX** | no | — | Tier name (e.g. "Khối", "Phòng", "Tổ"); unique so the catalog has no duplicates. |
| `rank` | `Integer` → `INTEGER` | **U**, **IX** | no | — | Display order, high→low (1 = highest tier); unique so two tiers never share a rank. |
| `head_title` | `String(100)` → `VARCHAR(100)` | — | no | `""` | Title of the person heading a unit at this level (e.g. "Trưởng khối", "Tổ trưởng"). |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the level row was created. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_unit_levels_name` on `name`, `ix_unit_levels_rank` on `rank`.
- Foreign keys: none.

**Relationships**

- One unit level is referenced by many `departments` (via `level_id`); a level cannot be
  deleted while any department still uses it (enforced in the service).

---

### `customers`

**Purpose:** the Kinh doanh contact book (Khách hàng / CRM) — spec-06-khach-hang. One row
per customer used to raise báo giá / đơn hàng. "Mở rộng từ nền RBAC" (DOMAIN §23 L528): a
customer is owned by a Sale (`sale_user_id`) so RBAC data-scope (own/department/all)
narrows the list. `tax_code` (MST) is optional and only *soft*-checked for duplicates — a
duplicate MST is a warning, NOT a hard block (§34 L885, §41 L1133) — so it is indexed but
NOT unique. `credit_limit` is the limit only; the live receivable balance lives in Công nợ
and is read via SEAM-16, never stored here.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `code` | `String(20)` → `VARCHAR(20)` | **U**, **IX** | no | — | System-generated sequential code (KH001, KH002…); read-only, never user-entered (KH-02, PB### pattern). |
| `name` | `String(255)` → `VARCHAR(255)` | — | no | — | Customer name (required, non-blank). |
| `tax_code` | `String(20)` → `VARCHAR(20)` | **IX** | yes | — | MST (mã số thuế). Optional; indexed for the duplicate-check but NOT unique (soft warning, §34 L885). 10 or 13 digits when present. |
| `phone` | `String(30)` → `VARCHAR(30)` | — | yes | — | Contact phone. |
| `email` | `String(255)` → `VARCHAR(255)` | — | yes | — | Contact email. |
| `address` | `String(500)` → `VARCHAR(500)` | — | yes | — | Billing / delivery address. |
| `contact_name` | `String(255)` → `VARCHAR(255)` | — | yes | — | Người liên hệ tại khách (CRM field). |
| `credit_limit` | `Integer` → `INTEGER` | — | no | `0` | Hạn mức tín dụng (VND integer). Limit only; live balance is read via SEAM-16. |
| `sale_user_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | yes | — | Owning Sale (RBAC scope owner). Nullable; indexed because every scoped list filters on it. |
| `status` | `String(16)` → `VARCHAR(16)` | — | no | `active` | `active` = đang giao dịch, `inactive` = ngừng giao dịch. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the customer row was created. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_customers_code` on `code`.
- Indexes: `ix_customers_tax_code` on `tax_code` (duplicate-check, non-unique), `ix_customers_sale_user_id` on `sale_user_id` (scope filter).
- Foreign keys: `sale_user_id FK→users.id`.

**Relationships**

- Many customers belong to one owning Sale (`users`); the customer's "department" for the
  `department` scope is that Sale's `department_id`.
- Receivable/CreditLimit live in Công nợ (Tài chính–Kế toán) and are read via SEAM-16 —
  NOT modeled as FKs here at P0 (cardinality `Customer 1─n Receivable` is inferred; see
  spec-06 open decision #3).

---

### `products`

**Purpose:** the Sản phẩm in catalog head (Product) — spec-07-san-pham. One row per
reusable commercial product ("cái khách mua"); đơn hàng / job reference it, never the
reverse (DOMAIN §29 L701, §34 L865). Khổ/giấy/màu live on `product_components`, NOT here —
a multi-component product (sách: bìa≠ruột) has no single trim size (§34 L894, spec-07
out-of-scope). Price / snapshot giá are NOT stored (snapshotted at order-close copy-on-write,
P0 #5, §34 L877). Portable across SQLite and Postgres.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `code` | `String(20)` → `VARCHAR(20)` | **U**, **IX** | no | — | System-generated sequential code (SP001, SP002…); read-only, never user-entered (§34 L865, KH###/PB### pattern). |
| `name` | `String(255)` → `VARCHAR(255)` | — | no | — | Product name (required, non-blank, unique case-insensitive). |
| `product_type` | `String(32)` → `VARCHAR(32)` | — | no | — | Loại SP (enum §7): catalogue, brochure, tem_nhan, hop, sach, to_roi, name_card. |
| `binding_type` | `String(16)` → `VARCHAR(16)` | — | yes | — | Kiểu đóng (enum §5, nullable — chỉ SP có gáy): perfect / saddle / sewn. Null = không gáy. |
| `note` | `String(1000)` → `VARCHAR(1000)` | — | yes | — | Ghi chú tự do. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the product row was created. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_products_code` on `code`.

**Relationships**

- One product has many `product_components` (bìa/ruột/tay đệm), cascade-deleted with it.
- Đơn/job reference the product (SP là master dùng lại) — those reverse FKs live on the
  Kinh doanh/Job side, not here (§29 L701). No reverse FK exists at P0.

---

### `product_components`

**Purpose:** one component (cấu phần) of a product (Sản phẩm in) — spec-07-san-pham. A
product with a spine (sách/hộp) breaks into ordered components; each carries its OWN khổ
thành phẩm, giấy, số màu 2 mặt, số trang, bleed, canh thớ (§34 L893–894) so báo giá / job /
bình bản read them back exactly. `paper_master_id` is an FK-nullable **SEAM-03** seam to
PaperMaster (module `dm_giay_vat_tu`, Danh mục Giấy) — a plain nullable Integer (no FK
constraint) until that catalog exists.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `product_id` | `Integer` → `INTEGER` | **FK→products.id**, **IX** | no | — | Parent product; `ON DELETE CASCADE` (component deleted with the product). |
| `sequence` | `Integer` → `INTEGER` | — | no | `0` | Display / print order (bìa trước ruột…). |
| `component_type` | `String(16)` → `VARCHAR(16)` | — | no | — | cover / body / insert (§34 L893). |
| `paper_master_id` | `Integer` → `INTEGER` | — | yes | — | **SEAM-03** FK-nullable to PaperMaster (Danh mục Giấy chưa build); no FK constraint yet. |
| `colors_front` | `Integer` → `INTEGER` | — | no | `0` | Số màu mặt trước (0..8, §23 L532). |
| `colors_back` | `Integer` → `INTEGER` | — | no | `0` | Số màu mặt sau (0..8). |
| `page_count` | `Integer` → `INTEGER` | — | no | `0` | Số trang. body của SP có gáy phải % 4 == 0 (tay sách, §31). |
| `finished_w` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | no | `0` | Khổ thành phẩm rộng (>0). |
| `finished_h` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | no | `0` | Khổ thành phẩm cao (>0). |
| `bleed` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | no | `0` | Bleed (mm, ≥0). |
| `grain_direction` | `String(8)` → `VARCHAR(8)` | — | yes | — | Canh thớ: long / short. |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_product_components_product_id` on `product_id`.
- Foreign keys: `product_id FK→products.id ON DELETE CASCADE`.

**Relationships**

- Many components belong to one `products` row; deleting the product cascades to its
  components (delete-orphan on the ORM side + `ON DELETE CASCADE` at the DB).
- `paper_master_id` → PaperMaster once Danh mục Giấy (`dm_giay_vat_tu`) is built (SEAM-03).

---

### `quotes`

**Purpose:** Báo giá header — mô hình **Header-Version-Item (H-V-I)** thay bảng `quotations`
phẳng cũ (bảng cũ còn trong dev.db như orphan, model đã gỡ). Header giữ danh tính phiếu
(`quote_number` BG26-xxxx duy nhất), khách hàng, trạng thái lifecycle
`draft → sent → accepted/rejected/expired → converted_to_order` (+ `cancelled`), và con trỏ
`current_version_id` tới phiên bản đang hiệu lực. Nội dung giá nằm ở `quote_versions` /
`quote_items`. Logic **pick từ phiếu tính giá**: 1 báo giá pick từ NHIỀU phiếu (per-item
`quote_items.estimate_id`); header `estimate_id` chỉ là phiếu đầu tiên (tương thích cũ).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | Surrogate primary key. |
| `quote_number` | `String(20)` | **UQ**, **IX** | no | — | Mã phiếu (BG26-0001…) — duy nhất; version nằm ở `quote_versions.version_number`. |
| `customer_id` | `Integer` | **FK→customers.id** (SET NULL), **IX** | yes | — | Khách hàng (SEAM-14 CRM read). |
| `customer_name_snapshot` | `String(255)` | — | yes | — | Tên KH chốt tại thời điểm tạo (copy-on-write hiển thị). |
| `estimate_id` | `Integer` | **FK→estimates.id** (SET NULL), **IX** | yes | — | Phiếu tính giá ĐẦU TIÊN (tương thích cũ); tham chiếu thật per dòng ở `quote_items.estimate_id`. |
| `salesperson_id` | `Integer` | **FK→users.id** (SET NULL), **IX** | yes | — | Sale phụ trách — RBAC data-scope owner. |
| `status` | `String(20)` | — | no | `draft` | draft/sent/accepted/rejected/expired/converted_to_order/cancelled. |
| `current_version_id` | `Integer` | **IX** | yes | — | Phiên bản đang hiệu lực (con trỏ, không FK để tránh vòng). |
| `valid_until` | `Date` | — | yes | — | Hạn hiệu lực; quá hạn → expired (chặn duyệt). |
| `payment_terms` | `String(255)` | — | yes | — | Điều khoản thanh toán. |
| `delivery_terms` | `String(255)` | — | yes | — | Điều khoản giao hàng. |
| `delivery_address` | `String(500)` | — | yes | — | Địa chỉ giao. |
| `customer_note` | `String(1000)` | — | yes | — | Ghi chú hiện cho khách. |
| `internal_note` | `String(1000)` | — | yes | — | Ghi chú nội bộ. |
| `cancel_reason` | `String(500)` | — | yes | — | Lý do hủy (bắt buộc khi cancelled). |
| `created_by` | `Integer` | **FK→users.id** (SET NULL) | yes | — | Người tạo. |
| `created_at` | `DateTime(tz)` | — | no | now (UTC) | Tạo lúc. |
| `updated_at` | `DateTime(tz)` | — | no | now (UTC) | Sửa lần cuối (onupdate). |

### `quote_versions`

**Purpose:** một phiên bản chào giá (v1, v2…) của 1 quote — re-quote sinh version mới, phiếu cũ
`superseded` giữ nguyên lịch sử. Khi **Gửi khách** (draft→sent) version đóng băng
copy-on-write: `estimate_snapshot_json` (spec phiếu tính giá) + `internal_cost_snapshot_json`
(phân rã giá vốn per mức SL) — đổi bảng giá sau này không rewrite phiếu đã gửi (P0 §34).

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `quote_id` | `Integer` | **FK→quotes.id** (CASCADE), **IX** | no | — | Header cha. |
| `version_number` | `Integer` | — | no | `1` | v1, v2… trong 1 quote. |
| `status` | `String(20)` | — | no | `draft` | draft/locked/sent/accepted/rejected/superseded/cancelled (per-version). |
| `change_reason` | `String(255)` | — | yes | — | "Lý do/ghi chú phiên bản này" (đổi giấy, khách ép giá…). |
| `estimate_snapshot_json` | `JSON` | — | yes | — | **Copy-on-write** spec phiếu tính giá tại lúc gửi. |
| `internal_cost_snapshot_json` | `JSON` | — | yes | — | **Copy-on-write** phân rã giá vốn (options → lines). |
| `customer_output_snapshot_json` | `JSON` | — | yes | — | Bản chốt nội dung đối ngoại (PDF data) nếu render. |
| `pricing_snapshot_json` | `JSON` | — | yes | — | Tham số pricing đã áp (gói biên, rounding…). |
| `total_cost_snapshot` | `Numeric(15,2)` | — | yes | — | Tổng giá vốn khóa của version. |
| `subtotal_amount` | `Numeric(15,2)` | — | no | `0` | Tổng giá bán trước VAT/chiết khấu. |
| `discount_amount` | `Numeric(15,2)` | — | no | `0` | Chiết khấu tổng. |
| `vat_percent` | `Numeric(5,2)` | — | no | `0` | %VAT áp version. |
| `vat_amount` | `Numeric(15,2)` | — | no | `0` | Tiền VAT. |
| `final_amount` | `Numeric(15,2)` | — | no | `0` | Tổng cộng (đã VAT). |
| `pdf_file_url` | `String(255)` | — | yes | — | File PDF đối ngoại đã xuất (nếu có). |
| `created_by` | `Integer` | **FK→users.id** (SET NULL) | yes | — | Người tạo version. |
| `created_at` | `DateTime(tz)` | — | no | now | Tạo lúc. |
| `sent_at` | `DateTime(tz)` | — | yes | — | Gửi khách lúc (tính tuổi phiếu "đã gửi N ngày"). |
| `accepted_at` | `DateTime(tz)` | — | yes | — | Khách chốt lúc. |
| `rejected_at` | `DateTime(tz)` | — | yes | — | Từ chối lúc. |

### `quote_items`

**Purpose:** một dòng hàng của version — **mỗi dòng = 1 phiếu tính giá + 1 mức số lượng đã
pick** (logic chốt: báo giá không soạn tay, chỉ pick từ phiếu tính giá `calculated`). Giá vốn
đóng băng per dòng (`total_cost_snapshot`); markup/VAT per dòng.

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `quote_version_id` | `Integer` | **FK→quote_versions.id** (CASCADE), **IX** | no | — | Version cha. |
| `estimate_id` | `Integer` | **FK→estimates.id** (SET NULL), **IX** | yes | — | Phiếu tính giá gốc của DÒNG NÀY (đa phiếu/1 báo giá). |
| `estimate_option_id` | `Integer` | — | yes | — | Mức số lượng (option) đã pick trong phiếu. |
| `line_no` | `Integer` | — | no | — | Thứ tự dòng. |
| `product_type` | `String(50)` | — | no | — | Loại SP (snapshot từ phiếu). |
| `product_name` | `String(255)` | — | no | — | Tên SP (snapshot). |
| `product_spec_text` | `String(1000)` | — | yes | — | Spec đọc được ("21×29,7 cm · 4 màu/2 mặt"). |
| `product_spec_snapshot_json` | `JSON` | — | yes | — | Spec đầy đủ copy-on-write. |
| `quantity` | `Integer` | — | no | — | Số lượng của mức đã pick. |
| `unit` | `String(16)` | — | no | `cái` | Đơn vị bán. |
| `total_cost_snapshot` | `Numeric(15,2)` | — | no | `0` | Giá vốn KHÓA của dòng (không sửa ở Báo giá). |
| `margin_percent` | `Numeric(5,2)` | — | no | `0` | % biên lợi nhuận dòng. |
| `selling_price` | `Numeric(15,2)` | — | no | `0` | Giá bán dòng (trước VAT). |
| `unit_price` | `Numeric(15,2)` | — | no | `0` | Đơn giá bán /sp. |
| `discount_amount` | `Numeric(15,2)` | — | no | `0` | Chiết khấu dòng. |
| `vat_percent` | `Numeric(5,2)` | — | no | `0` | %VAT dòng. |
| `vat_amount` | `Numeric(15,2)` | — | no | `0` | Tiền VAT dòng. |
| `final_amount` | `Numeric(15,2)` | — | no | `0` | Thành tiền dòng (đã VAT). |
| `note` | `String(500)` | — | yes | — | Ghi chú dòng. |

### `quote_attachments`

**Purpose:** file đính kèm phiếu báo giá (bản chào PDF, artwork tham chiếu…).

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `quote_id` | `Integer` | **FK→quotes.id** (CASCADE), **IX** | no | — | Phiếu cha. |
| `quote_version_id` | `Integer` | **FK→quote_versions.id** (CASCADE), **IX** | yes | — | Gắn version cụ thể (nếu có). |
| `file_name` | `String(255)` | — | no | — | Tên file. |
| `file_url` | `String(500)` | — | no | — | Đường dẫn lưu trữ. |
| `file_type` | `String(100)` | — | yes | — | MIME/loại file. |
| `uploaded_by` | `Integer` | **FK→users.id** (SET NULL) | yes | — | Người upload. |
| `uploaded_at` | `DateTime(tz)` | — | no | now | Upload lúc. |

### `quote_activity_logs`

**Purpose:** timeline "Hoạt động" của phiếu (tạo version, gửi khách, khách chốt…) — nguồn dữ
liệu cho khung timeline trên UI detail.

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `quote_id` | `Integer` | **FK→quotes.id** (CASCADE), **IX** | no | — | Phiếu cha. |
| `quote_version_id` | `Integer` | **FK→quote_versions.id** (CASCADE), **IX** | yes | — | Version liên quan (nếu có). |
| `action` | `String(50)` | — | no | — | Động từ sự kiện (create_quote, send_quote…). |
| `old_value_json` | `JSON` | — | yes | — | Giá trị trước (diff). |
| `new_value_json` | `JSON` | — | yes | — | Giá trị sau (diff). |
| `actor_id` | `Integer` | **FK→users.id** (SET NULL) | yes | — | Người thao tác. |
| `actor_name_snapshot` | `String(255)` | — | yes | — | Tên người thao tác chốt lúc ghi. |
| `created_at` | `DateTime(tz)` | — | no | now | Xảy ra lúc. |

---

### `orders`

**Purpose:** the Đơn hàng bán header — spec-10-don-hang-ban (bước ④ CHỐT ĐƠN). One row per đơn
created AFTER a khách chấp nhận a **báo giá đã duyệt** (`Quotation.status == approved` còn hạn).
It pins the quotation reference C1 (`quotation_id` + `quotation_version` + `quotation_effective_from`
via SEAM-04 `quotation_ref`, Báo giá LIVE) and moves through the lifecycle
`draft → ordered` (+ `on_hold` / `change_order` / `cancelled`, §32 L825-829). The ③→④ hard gate to
`ordered` needs `quotation.approved AND deposit ≥ total·min_deposit_pct` (§32 L827-828); the deposit
write is TREO behind SEAM-04 (Payment, feat-048). `parent_order_id` (self-FK) is used **ONLY** for an
**đơn bổ sung** (sub-job trỏ đơn gốc, §32 L807-813); đổi (`change_order`) giữ lịch sử qua
Quotation-version, KHÔNG dùng `parent_order_id` (decision #5). The physical layer (khổ/màu/kẽm/
imposition/PrintForm) is NEVER stored here — ẩn khỏi Sale (§29 P0 L730, §43 #1). `row_version`
(optimistic locking) is deliberately NOT modelled (doc chỉ Job/Quotation, §34 L898 — Out-of-scope).
VAT chân lý ở `InvoiceLine` (⑬); the order carries only `vat_pct_estimate`. Portable across SQLite
and Postgres.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `order_no` | `String(20)` → `VARCHAR(20)` | **U**, **IX** | no | — | System-generated order number (DH001, DH002…). Unique. NOT `PB###` (mã phòng ban); pattern chưa xác nhận với SVN. |
| `customer_id` | `Integer` → `INTEGER` | **FK→customers.id**, **IX** | yes | — | Customer kéo từ báo giá (read-only display via CRM). Nullable so a draft can exist while wiring. |
| `quotation_id` | `Integer` → `INTEGER` | **IX** | yes | — | Referenced approved quotation (SEAM-04 quotation_ref). Plain Integer (NO FK) — báo giá versioned, pin the exact version below. |
| `quotation_version` | `Integer` → `INTEGER` | — | yes | — | The exact quotation version pinned (C1); không tự nhảy sang version mới hơn. |
| `quotation_effective_from` | `Date` → `DATE` | — | yes | — | Effective-from of the snapshotted quotation price window (copy-on-write source pointer, not a FK). |
| `order_type` | `String(16)` → `VARCHAR(16)` | — | no | `theo_yc` | Loại đơn ∈ {noi_bo, theo_yc} (§41 L1135). |
| `order_kind` | `String(16)` → `VARCHAR(16)` | — | no | `moi` | Loại ∈ {moi, bo_sung}. Đơn bổ sung mang giá bán riêng, giữ kẽm cũ → rẻ (§32). |
| `parent_order_id` | `Integer` → `INTEGER` | **FK→orders.id**, **IX** | yes | — | Đơn gốc — set **CHỈ** khi order_kind=bo_sung (bắt buộc). NULL cho đơn mới; KHÔNG dùng cho change_order. |
| `sale_user_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | yes | — | NV kinh doanh phụ trách (hoa hồng) + RBAC data-scope owner (own/department/all, §41). |
| `status` | `String(16)` → `VARCHAR(16)` | — | no | `draft` | Lifecycle: draft/ordered/on_hold/change_order/cancelled. |
| `has_customer_paper` | `Boolean` → `BOOLEAN` | — | no | `false` | F4 cờ ứng giấy khách; chi tiết lô (ownership=customer, cost=0) sống ở Kho — read-only link via SEAM-06. |
| `vat_pct_estimate` | `Integer` → `INTEGER` | — | no | `0` | VAT DỰ KIẾN (%) để ước tổng — chân lý ở InvoiceLine (⑬). |
| `cancel_reason` | `String(500)` → `VARCHAR(500)` | — | yes | — | Set only when status=cancelled (F8). |
| `cancelled_at_state` | `String(16)` → `VARCHAR(16)` | — | yes | — | The status khi hủy (để biết hoàn/không hoàn vật tư-cọc theo §32 L817-825). |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the order row was created. |

**Keys & indexes**

- Primary key: `id`.
- Indexes: `ix_orders_order_no` (U), `ix_orders_customer_id`, `ix_orders_quotation_id`, `ix_orders_parent_order_id`, `ix_orders_sale_user_id` (scope filter).
- Foreign keys: `customer_id FK→customers.id` (ON DELETE SET NULL), `parent_order_id FK→orders.id` (ON DELETE SET NULL, self-FK), `sale_user_id FK→users.id`. `quotation_id` is deliberately NOT a FK (SEAM-04; báo giá versioned — the (id, version) pin is the reference).

**Relationships**

- `orders 1─n order_lines` (cascade delete). Cardinality Order 1─n Job → thực tế n-n Order-line ↔ Job/PrintForm (§34/§43 #6) is NOT modelled at P0 (Sản xuất chưa build; no hard FK to Job).
- The referenced quotation (`quotation_id` + version) is read via SEAM-04 (quotation_ref, Báo giá LIVE). The customer display is a read of `customers` (kéo từ báo giá). Cọc/proof/lô giấy/tiến độ/giao đều đọc qua SEAM-04(payment)/05/06/01/02 (TREO).

---

### `order_lines`

**Purpose:** a line of an `orders` (đơn hàng bán) — spec-10-don-hang-ban. Snapshotted từ báo giá đã
duyệt at create/chốt: `unit_price_snapshot` (Int) **and** `norm_snapshot` (JSON) are frozen
copy-on-write (P0 §34 L877-878, §43 #5) — there is NO live FK to a price/norm table, so đổi giá gốc
sau đó KHÔNG đổi số trên đơn. `description` is mô tả SP thương mại (đối ngoại) — the physical layer
(số màu/kẽm/khổ/imposition/PrintForm) is NEVER stored here (§29 P0). After chốt (`orders.status ==
ordered`) the lines are read-only (sửa → chặn; đổi phải change_order).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `order_id` | `Integer` → `INTEGER` | **FK→orders.id**, **IX** | no | — | Owning order (ON DELETE CASCADE). |
| `description` | `String(500)` → `VARCHAR(500)` | — | no | `''` | Mô tả SP thương mại (đối ngoại). NEVER số màu/kẽm/khổ/imposition/PrintForm. |
| `qty` | `Integer` → `INTEGER` | — | no | `1` | Số lượng dòng đơn. |
| `unit_price_snapshot` | `Integer` → `INTEGER` | — | yes | — | **P0 copy-on-write**: frozen unit price (VND) từ báo giá. NO live FK. |
| `norm_snapshot` | `JSON` → `JSON` | — | yes | — | **P0 copy-on-write**: frozen norm/định mức snapshot (ngang hàng unit_price_snapshot). |
| `vat_pct_estimate` | `Integer` → `INTEGER` | — | no | `0` | VAT DỰ KIẾN (%) cho dòng — chân lý ở InvoiceLine (⑬). |
| `line_total` | `Integer` → `INTEGER` | — | yes | — | Thành tiền = qty × unit_price_snapshot (derived + stored; null khi chưa có giá). |

**Keys & indexes**

- Primary key: `id`.
- Indexes: `ix_order_lines_order_id`.
- Foreign keys: `order_id FK→orders.id` (ON DELETE CASCADE).

**Relationships**

- Many `order_lines` belong to one `orders`. The snapshot pair lives on the line (copy-on-write); no FK to a live price/norm table.

---

### `costings`

**Purpose:** the Tính giá (Costing / giá thành nội bộ) header — spec-08-tinh-gia. One row per
phương án tính giá for a product + số lượng; Báo giá đọc lại kết quả (§43 L1217–1219). This
screen reads **live versioned** đơn giá/định mức and does NOT snapshot (snapshot P0
copy-on-write = chốt Đơn hàng, §34 L877-878). No bậc SL / lãi / chiết khấu here (thuộc Báo
giá). `product_id` is read via **SEAM-11** (ProductRead · `san_pham`). Portable across SQLite
and Postgres.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `code` | `String(20)` → `VARCHAR(20)` | **U**, **IX** | no | — | System-generated sequential code (CG001, CG002…); read-only, never user-entered (SP###/KH###/PB### pattern). |
| `product_id` | `Integer` → `INTEGER` | **FK→products.id**, **IX** | yes | — | **SEAM-11** the product this costing is for; `ON DELETE SET NULL`. Nullable so a draft can start before the product is picked. |
| `qty_final` | `Integer` → `INTEGER` | — | no | `0` | Số lượng cần giao (bắt buộc >0, validated in the service). KHÔNG bậc SL (A1). |
| `status` | `String(16)` → `VARCHAR(16)` | — | no | `draft` | Vòng đời: draft (đang lập) / ready (đủ input để Báo giá đọc). No snapshot. |
| `note` | `String(1000)` → `VARCHAR(1000)` | — | yes | — | Ghi chú tự do. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the costing row was created. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_costings_code` on `code`.
- Index: `ix_costings_product_id` on `product_id`.
- Foreign keys: `product_id FK→products.id ON DELETE SET NULL`.

**Relationships**

- One costing has many `costing_paper_options` (phương án giấy) + `costing_operations` (công
  đoạn gia công), cascade-deleted with it.
- Báo giá references a costing (đọc lại giá vốn) — that reverse FK lives on the `bao_gia` side
  once built, not here. No reverse FK exists at P0.

---

### `costing_paper_options`

**Purpose:** one phương án giấy & bình bản of a costing (Khối B) — spec-08. Estimator may lập
>1 phương án giấy per costing để so sánh giá vốn. `sheet_paper_master_id` is an FK-nullable
**SEAM-07** seam to PaperMaster (Danh mục Giấy / Kho · `dm_giay_vat_tu`/`kho`) — a plain
nullable Integer (no FK) until that catalog exists; giá per-ram/kg + lot_type + ownership are
looked up via the raising port stub, never fabricated.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `costing_id` | `Integer` → `INTEGER` | **FK→costings.id**, **IX** | no | — | Parent costing; `ON DELETE CASCADE`. |
| `sheet_paper_master_id` | `Integer` → `INTEGER` | — | yes | — | **SEAM-07** FK-nullable to PaperMaster (Danh mục Giấy chưa build); no FK constraint yet. |
| `sheet_w` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | no | `0` | Khổ tờ in rộng (cm). |
| `sheet_h` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | no | `0` | Khổ tờ in cao (cm). |
| `pieces_per_sheet` | `Integer` → `INTEGER` | — | no | `0` | Số con/khổ NHẬP TAY (>0); gợi ý song song là hình học (§31a), giá trị nhập là chuẩn. |
| `grain_locked` | `Boolean` → `BOOLEAN` | — | no | `false` | Ràng buộc thớ: khi true gợi ý bỏ nhánh xoay (§31 L782). |
| `selected` | `Boolean` → `BOOLEAN` | — | no | `false` | Phương án giấy được chọn để "dùng" (so sánh — F7). |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_costing_paper_options_costing_id` on `costing_id`.
- Foreign keys: `costing_id FK→costings.id ON DELETE CASCADE`.

**Relationships**

- Many phương án giấy belong to one `costings` row; deleting the costing cascades.
- `sheet_paper_master_id` → PaperMaster once Danh mục Giấy (`dm_giay_vat_tu`) is built (SEAM-07).

---

### `costing_operations`

**Purpose:** one công đoạn gia công of a costing (Khối E) — spec-08. Each carries an
`execution_mode` ∈ {internal, outsourced} (§14 L389–390, §23 L537): internal → đơn giá khoán
(SEAM-08), outsourced → đơn giá NCC (SEAM-12); cost pool "Gia công" phân đôi nguồn. Đơn giá is
NOT stored here — it is pulled versioned at cost time (feat-041).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `costing_id` | `Integer` → `INTEGER` | **FK→costings.id**, **IX** | no | — | Parent costing; `ON DELETE CASCADE`. |
| `sequence` | `Integer` → `INTEGER` | — | no | `0` | Display / process order. |
| `name` | `String(255)` → `VARCHAR(255)` | — | no | — | Tên công đoạn gia công (cán màng, bế, đóng cuốn…). |
| `execution_mode` | `String(16)` → `VARCHAR(16)` | — | no | `internal` | internal (khoán nội bộ · SEAM-08) / outsourced (NCC · SEAM-12). |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_costing_operations_costing_id` on `costing_id`.
- Foreign keys: `costing_id FK→costings.id ON DELETE CASCADE`.

**Relationships**

- Many công đoạn belong to one `costings` row; deleting the costing cascades.
- `execution_mode` routes the đơn giá source: SEAM-08 (internal) or SEAM-12 (outsourced).

---

### `estimates`

**Purpose:** internal cost estimates (headers) for product pricing, replacing the legacy `costings` logically.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `estimate_number` | `String(20)` → `VARCHAR(20)` | **U**, **IX** | no | — | Auto-generated sequential code (TG26-0001, TG26-0002...). |
| `customer_id` | `Integer` → `INTEGER` | **IX** | yes | — | Optional CRM customer reference. |
| `product_type` | `String(50)` → `VARCHAR(50)` | **FK→product_types_catalog.product_type** | no | — | Reference to product type strategy configuration. |
| `product_name` | `String(255)` → `VARCHAR(255)` | — | no | — | Name of product being estimated. |
| `status` | `String(20)` → `VARCHAR(20)` | — | no | `draft` | Status (draft, calculated, cancelled). |
| `input_spec_json` | `JSON` → `JSON` | — | no | — | Complete input specification configuration. |
| `quantity_list_json` | `JSON` → `JSON` | — | no | — | List of quantity points calculated. |
| `created_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | User who created the estimate. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Creation timestamp. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Last updated timestamp. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_estimates_estimate_number` on `estimate_number`.
- Index: `ix_estimates_customer_id` on `customer_id`.
- Foreign keys: `product_type FK→product_types_catalog.product_type`, `created_by FK→users.id`.

---

### `estimate_options`

**Purpose:** calculated estimate results for a specific quantity point.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `estimate_id` | `Integer` → `INTEGER` | **FK→estimates.id**, **IX** | no | — | Parent estimate ID. |
| `quantity` | `Integer` → `INTEGER` | — | no | — | Quantity point calculated. |
| `total_cost` | `Numeric(15,2)` → `NUMERIC(15,2)` | — | no | `0` | Total internal estimated cost. |
| `warnings_json` | `JSON` → `JSON` | — | yes | — | List of warnings or blocking errors. |
| `margin_percent` | `Numeric(5,2)` → `NUMERIC(5,2)` | — | no | `0` | Desired profit margin (%). |
| `selling_price` | `Numeric(15,2)` → `NUMERIC(15,2)` | — | no | `0` | Base selling price. |
| `discount_amount` | `Numeric(15,2)` → `NUMERIC(15,2)` | — | no | `0` | Absolute discount. |
| `vat_percent` | `Numeric(5,2)` → `NUMERIC(5,2)` | — | no | `0` | VAT rate (%). |
| `vat_amount` | `Numeric(15,2)` → `NUMERIC(15,2)` | — | no | `0` | Calculated VAT amount. |
| `final_price` | `Numeric(15,2)` → `NUMERIC(15,2)` | — | no | `0` | Selling price after discount + VAT. |
| `unit_price` | `Numeric(15,2)` → `NUMERIC(15,2)` | — | no | `0` | Per unit final price. |
| `actual_margin` | `Numeric(5,2)` → `NUMERIC(5,2)` | — | no | `0` | Actual margin calculated. |
| `included_in_quote` | `Boolean` → `BOOLEAN` | — | no | `false` | Selected for inclusion in quotation. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `uix_estimate_options_estimate_qty` on `(estimate_id, quantity)`.
- Index: `ix_estimate_options_estimate_id` on `estimate_id`.
- Foreign keys: `estimate_id FK→estimates.id ON DELETE CASCADE`.

---

### `estimate_cost_lines`

**Purpose:** detail breakdown of costs for an estimate option.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `estimate_option_id` | `Integer` → `INTEGER` | **FK→estimate_options.id**, **IX** | no | — | Parent estimate option ID. |
| `category` | `String(32)` → `VARCHAR(32)` | — | no | — | Cost pool category. |
| `description` | `String(255)` → `VARCHAR(255)` | — | no | — | Text description. |
| `source_type` | `String(50)` → `VARCHAR(50)` | — | yes | — | DB table for source rate. |
| `source_id` | `Integer` → `INTEGER` | — | yes | — | ID of source rate. |
| `source_snapshot_json` | `JSON` → `JSON` | — | yes | — | Copy of source configuration rate/norm. |
| `calculation_snapshot_json` | `JSON` → `JSON` | — | yes | — | Interim parameters and math formula. |
| `quantity` | `Numeric(12,2)` → `NUMERIC(12,2)` | — | no | — | Quantity of resource used. |
| `unit` | `String(16)` → `VARCHAR(16)` | — | no | — | Unit of resource. |
| `unit_cost` | `Numeric(15,2)` → `NUMERIC(15,2)` | — | no | — | Rate per resource unit. |
| `setup_cost` | `Numeric(15,2)` → `NUMERIC(15,2)` | — | no | `0` | Setup fee of operation or machine. |
| `min_charge_applied` | `Boolean` → `BOOLEAN` | — | no | `false` | Whether minimum charge was triggered. |
| `total_cost` | `Numeric(15,2)` → `NUMERIC(15,2)` | — | no | — | Final computed line cost. |
| `note` | `String(500)` → `VARCHAR(500)` | — | yes | — | Ghi chú. |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_estimate_cost_lines_estimate_option_id` on `estimate_option_id`.
- Foreign keys: `estimate_option_id FK→estimate_options.id ON DELETE CASCADE`.

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

### `product_types_catalog`

**Purpose:** configuration for product types (e.g. name card, brochure, catalogue, boxes...) mapping required inputs, default operations, allowed materials, and compatible printing strategies.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `product_type` | `String(32)` → `VARCHAR(32)` | **U**, **IX** | no | — | Unique key for the product type (e.g. `catalogue`, `business_card`). |
| `name` | `String(100)` → `VARCHAR(100)` | — | no | — | Human display name (e.g. `Catalogue`, `Name card`). |
| `calculation_strategy` | `String(32)` → `VARCHAR(32)` | — | no | — | Enum strategy (e.g. `sheet_based`, `page_based`, `area_based`, `roll_based`, `box_based`, `book_based`). |
| `required_fields` | `JSON` → `TEXT` / `JSONB` | — | yes | — | Array of required fields for inputs. |
| `default_operations` | `JSON` → `TEXT` / `JSONB` | — | yes | — | Array of default operation codes. |
| `allowed_materials` | `JSON` → `TEXT` / `JSONB` | — | yes | — | Array of allowed material types. |
| `compatible_technologies` | `JSON` → `TEXT` / `JSONB` | — | yes | — | Array of compatible technology keys. |
| `is_active` | `Boolean` → `BOOLEAN` | — | no | `true` | Active status of the product type configuration. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the row was created. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the row was last updated. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_product_types_catalog_product_type` on `product_type`.

**Relationships**

- Referenced as a foreign key by `norms.product_type`.

---

### `materials`

**Purpose:** unified catalog of raw materials and consumables (Paper, Decal, PP, canvas, carton, film, formex, lamination film, glue, chemical...).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `code` | `String(20)` → `VARCHAR(20)` | **U**, **IX** | no | — | Unique master code (GY### for paper, VT### for other materials). |
| `name` | `String(255)` → `VARCHAR(255)` | — | no | — | Master material name. |
| `material_type` | `String(32)` → `VARCHAR(32)` | **IX** | no | — | Material category (e.g. `paper`, `decal`, `pp`, `canvas`, `carton`, `film`, `lamination`, `glue`, `chemical`). |
| `unit` | `String(16)` → `VARCHAR(16)` | — | no | — | Unit of measurement (e.g. `to`, `m2`, `kg`, `cuon`, `cai`). |
| `min_fee` | `BigInteger` → `BIGINT` | — | no | `0` | Minimum usage fee (VND). |
| `width_cm` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | yes | — | Width dimensions (cm) for sheets and rolls. |
| `height_cm` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | yes | — | Height/length dimensions (cm) for sheets. Null for rolls. |
| `gsm` | `Integer` → `INTEGER` | — | yes | — | Paper grammage / density weight (gsm). |
| `thickness_mm` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | yes | — | Thickness dimensions (mm). |
| `default_waste_pct` | `Numeric(5,2)` → `NUMERIC(5,2)` | — | no | `0.0` | Default waste percentage. |
| `min_purchase_qty` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | no | `0.0` | Minimum quantity required for purchase. |
| `paper_family` | `String(32)` → `VARCHAR(32)` | — | yes | — | Paper family family designation (Couche, Ivory, Ford, Bristol, Duplex...). |
| `surface` | `String(32)` → `VARCHAR(32)` | — | yes | — | Surface tráng/bề mặt description (bong, mo, trang-1-mat...). |
| `is_active` | `Boolean` → `BOOLEAN` | — | no | `true` | Active status in selection pickers. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the material was created. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the material was last updated. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_materials_code` on `code`.
- Index: `ix_materials_material_type` on `material_type`.

**Relationships**

- One material has many historical `material_costs`.

---

### `material_costs`

**Purpose:** time-versioned unit cost prices for materials.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `material_id` | `Integer` → `INTEGER` | **FK→materials.id**, **IX** | no | — | Reference to target material. |
| `price_unit` | `String(16)` → `VARCHAR(16)` | — | no | — | Unit this price corresponds to (e.g. `to`, `ram`, `kg`, `m2`). |
| `unit_price` | `BigInteger` → `BIGINT` | — | no | `0` | Cost price (VND). |
| `effective_from` | `Date` → `DATE` | — | no | — | Date pricing becomes active. |
| `effective_to` | `Date` → `DATE` | — | yes | — | Date pricing stops being active. Null means current active price. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Creation timestamp. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Last updated timestamp. |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_material_costs_material_id` on `material_id`.
- Unique index: `uix_material_costs_current` on `(material_id, price_unit) WHERE effective_to IS NULL`.
- Foreign key: `material_id FK→materials.id`.

**Relationships**

- Belongs to one `materials`.

---

### `machines`

**Purpose:** machines catalog (printing & finishing) carrying mechanical dimensions and processing capability parameters.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `code` | `String(20)` → `VARCHAR(20)` | **U**, **IX** | no | — | Unique machine code (MY###). |
| `name` | `String(255)` → `VARCHAR(255)` | — | no | — | Machine name. |
| `machine_type` | `String(32)` → `VARCHAR(32)` | **IX** | no | — | Type designation (offset, digital, large_format, flexo...). |
| `process_type` | `String(32)` → `VARCHAR(32)` | — | no | — | Production step mapped (in, can_mang, be, gap...). |
| `max_width_cm` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | yes | — | Max width of sheet/roll machine can process. |
| `max_height_cm` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | yes | — | Max height of sheet machine can process. |
| `min_width_cm` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | yes | — | Min width machine can process. |
| `min_height_cm` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | yes | — | Min height machine can process. |
| `speed` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | no | — | Processing speed (must be > 0). |
| `speed_unit` | `String(32)` → `VARCHAR(32)` | — | no | — | Speed unit (trang/phut, to/gio, m2/gio). |
| `setup_time_mins` | `Integer` → `INTEGER` | — | no | `0` | Setup/makeready time (minutes). |
| `changeover_time_mins` | `Integer` → `INTEGER` | — | no | `0` | Job changeover/cleanup time (minutes). |
| `setup_waste_sheets` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | no | `0.0` | Fixed sheets/material waste during setup. |
| `supported_materials` | `JSON` → `TEXT` / `JSONB` | — | yes | — | List of supported material_type codes. |
| `num_ink_units` | `Integer` → `INTEGER` | — | yes | — | Số đơn vị in (số màu in được 1 lượt); dùng tính số pass `⌈màu/num_ink_units⌉` (§31c). Null = không áp dụng. |
| `supports_perfecting` | `Boolean` → `BOOLEAN` | — | no | `false` | Máy in được 2 mặt trong 1 lượt (trở nhật/lật, §3). |
| `is_active` | `Boolean` → `BOOLEAN` | — | no | `true` | Active status of machine. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Creation timestamp. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Last updated timestamp. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_machines_code` on `code`.
- Index: `ix_machines_machine_type` on `machine_type`.

**Relationships**

- One machine has many historical `machine_rates` and references in `norms`.

---

### `machine_rates`

**Purpose:** hourly rates and minimum job fees for running machines over time.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `machine_id` | `Integer` → `INTEGER` | **FK→machines.id**, **IX** | no | — | Reference to machine. |
| `hourly_rate` | `BigInteger` → `BIGINT` | — | no | — | Rate per hour of machine usage (VND). |
| `min_charge` | `BigInteger` → `BIGINT` | — | no | `0` | Minimum charge for running this machine (VND). |
| `min_run_time_mins` | `Integer` → `INTEGER` | — | no | `0` | Minimum running time billed (minutes). |
| `effective_from` | `Date` → `DATE` | — | no | — | Pricing effective start date. |
| `effective_to` | `Date` → `DATE` | — | yes | — | Pricing effective end date. Null means current. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Creation timestamp. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Last updated timestamp. |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_machine_rates_machine_id` on `machine_id`.
- Unique index: `uix_machine_rates_current` on `(machine_id) WHERE effective_to IS NULL`.
- Foreign key: `machine_id FK→machines.id`.

**Relationships**

- Belongs to one `machines`.

---

### `operations`

**Purpose:** execution operations and finishing catalog (folding, lamination, binding, cutting, packing...).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `code` | `String(20)` → `VARCHAR(20)` | **U**, **IX** | no | — | Unique operation code (CD###). |
| `name` | `String(255)` → `VARCHAR(255)` | — | no | — | Operation name. |
| `operation_type` | `String(32)` → `VARCHAR(32)` | **IX** | no | — | Operation type (in, can_mang, be, gap, dong_cuon, dong_goi). |
| `unit` | `String(16)` → `VARCHAR(16)` | — | no | — | Unit of quantity (e.g. `m2`, `luot`, `to`, `cuon`, `san_pham`). |
| `allow_outsource` | `Boolean` → `BOOLEAN` | — | no | `false` | Whether this operation can be outsourced. |
| `is_active` | `Boolean` → `BOOLEAN` | — | no | `true` | Active status. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Creation timestamp. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Last updated timestamp. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_operations_code` on `code`.
- Index: `ix_operations_operation_type` on `operation_type`.

**Relationships**

- One operation has many historical `operation_rates`, `vendor_service_rates`, and references in `norms`.

---

### `operation_rates`

**Purpose:** rates, setup fees and labor charges for operations over time.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `operation_id` | `Integer` → `INTEGER` | **FK→operations.id**, **IX** | no | — | Reference to operation. |
| `setup_fee` | `BigInteger` → `BIGINT` | — | no | `0` | Flat setup fee (VND). |
| `run_rate` | `BigInteger` → `BIGINT` | — | no | `0` | Rate per quantity unit (VND). |
| `labor_rate` | `BigInteger` → `BIGINT` | — | no | `0` | Labor rate per hour if any (VND). |
| `min_charge` | `BigInteger` → `BIGINT` | — | no | `0` | Minimum charge for using this operation (VND). |
| `speed` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | no | `0.0` | Speed of operation in units per hour. |
| `effective_from` | `Date` → `DATE` | — | no | — | Pricing effective start date. |
| `effective_to` | `Date` → `DATE` | — | yes | — | Pricing effective end date. Null means current. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Creation timestamp. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Last updated timestamp. |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_operation_rates_operation_id` on `operation_id`.
- Unique index: `uix_operation_rates_current` on `(operation_id) WHERE effective_to IS NULL`.
- Foreign key: `operation_id FK→operations.id`.

- Belongs to one `operations`.

---

### `click_ink_rates`

**Purpose:** click rates and ink/toner charges for digital or specialized machinery over time.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `technology` | `String(32)` → `VARCHAR(32)` | **IX** | no | — | Printing technology (offset, digital, large_format, flexo). |
| `color_type` | `String(32)` → `VARCHAR(32)` | — | no | — | Color style (cmyk, grayscale, spot, white). |
| `machine_id` | `Integer` → `INTEGER` | **FK→machines.id**, **IX** | yes | — | Specific machine reference (or Null for technology-wide default). |
| `unit` | `String(16)` → `VARCHAR(16)` | — | no | — | unit (trang, m2, ml, click). |
| `unit_price` | `BigInteger` → `BIGINT` | — | no | — | Price per unit (VND). |
| `setup_fee` | `BigInteger` → `BIGINT` | — | no | `0` | Flat setup fee for clicking (VND). |
| `min_charge` | `BigInteger` → `BIGINT` | — | no | `0` | Minimum charge (VND). |
| `effective_from` | `Date` → `DATE` | — | no | — | Rate effective start date. |
| `effective_to` | `Date` → `DATE` | — | yes | — | Rate effective end date. Null means current. |
| `is_active` | `Boolean` → `BOOLEAN` | — | no | `true` | Active status flag. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Creation timestamp. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Last updated timestamp. |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_click_ink_rates_technology` on `technology`.
- Index: `ix_click_ink_rates_machine_id` on `machine_id`.
- Unique index: `uix_click_ink_rates_current` on `(technology, color_type, COALESCE(machine_id, 0), unit) WHERE effective_to IS NULL`.
- Foreign key: `machine_id FK→machines.id`.

**Relationships**

- Optionally references one `machines`.

---

### `plate_die_rates`

**Purpose:** rates, setup fees and charges for offset plate-making, dies, and embossing clichés over time.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `plate_type` | `String(32)` → `VARCHAR(32)` | **IX** | no | — | Type of tooling (ban_kem_offset, khuon_be, khuon_ep_kim). |
| `technology` | `String(32)` → `VARCHAR(32)` | — | no | — | Tooling technology (offset, flexo, be, ep_kim). |
| `unit` | `String(16)` → `VARCHAR(16)` | — | no | — | unit (ban, bo, cm2). |
| `unit_price` | `BigInteger` → `BIGINT` | — | no | — | Price per unit (VND). |
| `setup_fee` | `BigInteger` → `BIGINT` | — | no | `0` | Flat setup fee (VND). |
| `min_charge` | `BigInteger` → `BIGINT` | — | no | `0` | Minimum charge (VND). |
| `reusable` | `Boolean` → `BOOLEAN` | — | no | `false` | Reusability of plate/die. |
| `effective_from` | `Date` → `DATE` | — | no | — | Rate effective start date. |
| `effective_to` | `Date` → `DATE` | — | yes | — | Rate effective end date. Null means current. |
| `is_active` | `Boolean` → `BOOLEAN` | — | no | `true` | Active status flag. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Creation timestamp. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Last updated timestamp. |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_plate_die_rates_plate_type` on `plate_type`.
- Unique index: `uix_plate_die_rates_current` on `(plate_type, technology, unit) WHERE effective_to IS NULL`.

---

### `norms`

**Purpose:** versioned loss and makeup norms, waste percentages, and setup wastes with specificity dimensions.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `norm_key` | `String(32)` → `VARCHAR(32)` | **IX** | no | — | Key identifying the norm (yield_rate, running_waste_pct, makeready_per_color_side). |
| `value` | `Numeric(10,4)` → `NUMERIC(10,4)` | — | no | — | Norm value (yield in (0, 1], waste rate >= 0, makeready sheet count). |
| `product_type` | `String(32)` → `VARCHAR(32)` | **FK→product_types_catalog.product_type**, **IX** | yes | — | Narrowing dimension for product type. |
| `machine_id` | `Integer` → `INTEGER` | **FK→machines.id**, **IX** | yes | — | Narrowing dimension for machine. |
| `operation_id` | `Integer` → `INTEGER` | **FK→operations.id**, **IX** | yes | — | Narrowing dimension for operation. |
| `operation_key` | `String(32)` → `VARCHAR(32)` | **IX** | yes | — | Fallback string key for operation. |
| `qty_min` | `Integer` → `INTEGER` | — | yes | — | Lower bound of print quantity range (inclusive). |
| `qty_max` | `Integer` → `INTEGER` | — | yes | — | Upper bound of print quantity range (inclusive). |
| `context` | `JSON` → `JSONB` / `JSON` | — | yes | — | Dynamic context parameters like colors, sides, etc. |
| `context_key` | `String(160)` → `VARCHAR(160)` | — | no | `"{}"` | Canonical string representation of context for uniqueness constraint. |
| `effective_from` | `Date` → `DATE` | — | no | — | Norm effective start date. |
| `effective_to` | `Date` → `DATE` | — | yes | — | Norm effective end date. Null means current. |
| `note` | `String(500)` → `VARCHAR(500)` | — | yes | — | Optional developer or admin notes. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Creation timestamp. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Last updated timestamp. |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_norms_norm_key` on `norm_key`.
- Index: `ix_norms_product_type` on `product_type`.
- Index: `ix_norms_machine_id` on `machine_id`.
- Index: `ix_norms_operation_id` on `operation_id`.
- Index: `ix_norms_operation_key` on `operation_key`.
- Unique index: `uix_norms_current` on `(norm_key, COALESCE(product_type, ''), COALESCE(machine_id, 0), COALESCE(operation_id, 0), COALESCE(operation_key, ''), COALESCE(qty_min, -1), COALESCE(qty_max, -1), context_key) WHERE effective_to IS NULL`.
- Foreign keys: `product_type FK→product_types_catalog.product_type`, `machine_id FK→machines.id`, `operation_id FK→operations.id`.

**Relationships**

- Optionally references `product_types_catalog`, `machines`, or `operations`.

---

### `document_sequences`

**Purpose:** atomic year-based counter sequences for generating auto-incrementing document codes (quotations, costings, orders, jobs).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `doc_type` | `String(32)` → `VARCHAR(32)` | **PK** | no | — | Document type (costing, quotation, order, job). |
| `year` | `Integer` → `INTEGER` | **PK** | no | — | Year of counter sequence (e.g. 2026). |
| `current_number` | `Integer` → `INTEGER` | — | no | `0` | Auto-incremented sequence number. |

**Keys & indexes**

- Primary key: `(doc_type, year)`.

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
