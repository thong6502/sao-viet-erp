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

| Column          | Type (SQLAlchemy → SQLite / Postgres)                  | Key                           | Null | Default        | Meaning                                                                                                                                                                                                                               |
| --------------- | ------------------------------------------------------ | ----------------------------- | ---- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`            | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                        | no   | auto-increment | Surrogate primary key; stable internal id, also the JWT `sub` claim.                                                                                                                                                                  |
| `username`      | `String(150)` → `VARCHAR(150)`                         | **U**, **IX**                 | no   | —              | The sole account identity + login credential (spec-0001): users sign in with this. Required + unique (no two accounts share a username). Indexed for fast lookup at login. Email was removed entirely.                                |
| `name`          | `String(255)` → `VARCHAR(255)`                         | —                             | no   | `""`           | Human display name shown in the UI (e.g. Dashboard greeting).                                                                                                                                                                         |
| `password_hash` | `String(255)` → `VARCHAR(255)`                         | —                             | no   | —              | **bcrypt** hash of the password (`$2b$...`). The plaintext password is NEVER stored.                                                                                                                                                  |
| `department_id` | `Integer` → `INTEGER`                                  | **FK→departments.id**, **IX** | yes  | —              | The department (phòng ban) this user belongs to. Null until HR assigns one.                                                                                                                                                           |
| `role_id`       | `Integer` → `INTEGER`                                  | **FK→roles.id**, **IX**       | yes  | —              | The single role (vai trò) this user holds; its permissions decide access. Null until the department head assigns one.                                                                                                                 |
| `is_active`     | `Boolean` → `BOOLEAN`                                  | —                             | no   | `true`         | Whether the account is enabled. A locked (`false`) user is rejected even with a valid token.                                                                                                                                          |
| `avatar_url`    | `String(500)` → `VARCHAR(500)`                         | —                             | yes  | —              | Server-relative path of the user's uploaded profile picture (spec-04), e.g. `/static/avatars/<file>`. Null means no avatar — the UI shows an initials fallback. The plaintext file lives under the backend `static/` dir, not the DB. |
| `token_version` | `Integer` → `INTEGER`                                  | —                             | no   | `0`            | Hard-revoke counter (spec-03). Access tokens embed this as the `tv` claim; bumping it rejects every previously-issued access token (logout-all / forced invalidation).                                                                |
| `code`          | `String(20)` → `VARCHAR(20)`                           | **U**, **IX**                 | yes  | —              | Mã nhân viên hệ thống (spec-07): `NV` + số đệm 0 (`NV001`, `NV002`…). Read-only, repo tự sinh khi tạo; `backfill_user_codes` gán cho các user cũ còn thiếu mã. Null cho tới khi được gán.                                             |
| `created_at`    | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                             | no   | now (UTC)      | When the account row was created.                                                                                                                                                                                                     |

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

| Column         | Type (SQLAlchemy → SQLite / Postgres)                  | Key                           | Null | Default        | Meaning                                                                                                                                                                                                                                                                        |
| -------------- | ------------------------------------------------------ | ----------------------------- | ---- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `id`           | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                        | no   | auto-increment | Surrogate primary key.                                                                                                                                                                                                                                                         |
| `name`         | `String(255)` → `VARCHAR(255)`                         | **U**, **IX**                 | no   | —              | Department name (e.g. "Kinh doanh"); unique.                                                                                                                                                                                                                                   |
| `code`         | `String(20)` → `VARCHAR(20)`                           | **U**, **IX**                 | no   | —              | System-generated unique code (spec-05): `PB` + zero-padded sequence (`PB001`, `PB002`, …). Read-only — users never type it; the repository assigns it on create from the highest existing PB-number + 1, and the unique index guarantees no two live departments share a code. |
| `description`  | `String(500)` → `VARCHAR(500)`                         | —                             | yes  | —              | Optional free-text description of the department (spec-05).                                                                                                                                                                                                                    |
| `parent_id`    | `Integer` → `INTEGER`                                  | **FK→departments.id**, **IX** | yes  | —              | Parent department for the org tree (spec-05); null = root unit. A department and its whole subtree are cascade-deleted together (enforced in the service, not the DB).                                                                                                         |
| `level_id`     | `Integer` → `INTEGER`                                  | **FK→unit_levels.id**, **IX** | yes  | —              | Organizational tier this unit sits at (spec-06 / PBI-4009); null = untagged. Drives the head's title label (Trưởng khối / Trưởng phòng / Tổ trưởng) and blocks deleting a level still in use.                                                                                  |
| `head_user_id` | `Integer` → `INTEGER`                                  | —                             | yes  | —              | Logical reference to `users.id` of the trưởng phòng (no DB-level FK to avoid a create cycle; assigned via Alembic later).                                                                                                                                                      |
| `created_at`   | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                             | no   | now (UTC)      | When the department row was created.                                                                                                                                                                                                                                           |

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

| Column          | Type (SQLAlchemy → SQLite / Postgres)                  | Key                           | Null | Default        | Meaning                                                    |
| --------------- | ------------------------------------------------------ | ----------------------------- | ---- | -------------- | ---------------------------------------------------------- |
| `id`            | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                        | no   | auto-increment | Surrogate primary key.                                     |
| `name`          | `String(255)` → `VARCHAR(255)`                         | —                             | no   | —              | Role name (e.g. "NV Sales"); unique within its department. |
| `department_id` | `Integer` → `INTEGER`                                  | **FK→departments.id**, **IX** | no   | —              | The department this role belongs to.                       |
| `created_at`    | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                             | no   | now (UTC)      | When the role row was created.                             |

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
| `can_reassign` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (Cách B) — điều chuyển người phụ trách (vd Khách hàng). |
| `can_export` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — xuất file đối ngoại (CSV khách hàng, PDF báo giá). |
| `can_view_debt` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — xem công nợ / hạn mức khách hàng. |
| `can_view_discount` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (khach_hang) — xem/sửa chiết khấu riêng theo khách (#14, nhạy cảm). |
| `can_approve` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — duyệt báo giá (chuyển trạng thái → Khách duyệt). |
| `can_manage_status` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — chốt / hủy đơn hàng (đổi trạng thái vòng đời). |
| `can_reset_password` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — đặt lại mật khẩu người dùng. |
| `can_lock` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — khóa / mở tài khoản người dùng. |
| `can_revoke_sessions` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — thu hồi mọi phiên đăng nhập của người dùng. |
| `can_assign_role` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — gán vai trò cho người dùng (đơn + hàng loạt). |
| `can_transfer` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — chuyển người dùng sang phòng ban khác. |
| `can_set_head` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — đặt / đổi trưởng phòng (phong_ban). |
| `can_requote` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — tạo bản báo giá mới (re-quote). |
| `can_manage_price` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — cập nhật bảng giá theo mốc (vật liệu / thiết bị / công đoạn). |
| `can_cancel` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — hủy báo giá (→ Đã hủy) / hủy đơn hàng. |
| `can_manage_permissions` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — sửa MA TRẬN phân quyền của vai trò (tách khỏi đổi tên; chống leo thang quyền). |
| `can_clone` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — nhân bản giấy (vật liệu). |
| `can_toggle_active` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — bật/tắt hoạt động vật liệu. |
| `can_reparent` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết — đổi cấp trên phòng ban (tái cấu trúc cây tổ chức). |
| `can_view_salary` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (nhan_su) — xem dữ liệu nhạy cảm của hồ sơ (lương/BHXH/MST/số phụ thuộc/TK ngân hàng/nhóm-bậc lương). Thiếu quyền → các field đó bị ẩn. Thêm qua migration 0014. |
| `can_edit_salary` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (nhan_su) — SỬA dữ liệu nhạy cảm của hồ sơ (lương/BHXH/bank/nhóm-bậc lương), tách khỏi `can_view_salary` (chỉ xem). Thiếu quyền → các field đó bị BỎ QUA khi ghi (N5). Thêm qua migration 0041. |
| `can_adjust` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (nhan_su · Chấm công) — chấm bù / sửa công qua punch nguồn (`attendance_logs.is_manual`), tách khỏi `can_update`. Thêm qua migration 0015. |
| `can_approve_exception` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (don_hang_ban · A2) — DUYỆT "đơn đặc thù" (giá trị cao / biên thấp / dưới giá vốn), tách khỏi `can_approve` (= chốt đơn thường). CHỈ Giám đốc; Trưởng phòng KD giữ `_full` nhưng KHÔNG có quyền này. Thêm qua migration 0050. |
| `can_set_credit_terms` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (khach_hang) — THIẾT LẬP **chính sách tài chính** khách: hạn mức công nợ + điều khoản thanh toán + **chiết khấu min/max + biên lợi nhuận min/max** (redesign spec-06 v2 mở rộng nghĩa từ "điều khoản tín dụng"). Mọi số tài chính ai cũng XEM; chỉ quyền này mới SỬA. Quyết định "cho nợ/chiết khấu bao nhiêu" bàn NGOÀI ĐỜI — quyền chỉ gate ai NHẬP, KHÔNG phải bước duyệt. Thiếu quyền → các field tài chính bị BỎ QUA khi ghi (giữ nguyên / về default an toàn). Bật qua `_full` (GĐ/GĐ KD/TP KD). Thêm qua migration 0059. |
| `can_record_deposit` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (don_hang_ban) — GHI **phiếu thu cọc** (Kế toán). Tách khỏi CRUD đơn: NV KD lập đơn nhưng KHÔNG tự ghi cọc (tiền vào két là việc Kế toán). Gán vai Kế toán. Thêm qua migration 0067. |

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

| Column       | Type (SQLAlchemy → SQLite / Postgres)                  | Key           | Null | Default        | Meaning                                                                                    |
| ------------ | ------------------------------------------------------ | ------------- | ---- | -------------- | ------------------------------------------------------------------------------------------ |
| `id`         | `Integer` → `INTEGER` / `SERIAL`                       | **PK**        | no   | auto-increment | Surrogate primary key.                                                                     |
| `key`        | `String(64)` → `VARCHAR(64)`                           | **U**, **IX** | no   | —              | Stable module identifier (e.g. `khach_hang`); referenced by `role_permissions.module_key`. |
| `label`      | `String(255)` → `VARCHAR(255)`                         | —             | no   | —              | Human-readable module name shown in the permission matrix.                                 |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —             | no   | now (UTC)      | When the module row was created.                                                           |

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

| Column       | Type (SQLAlchemy → SQLite / Postgres)                  | Key           | Null | Default        | Meaning                                                                             |
| ------------ | ------------------------------------------------------ | ------------- | ---- | -------------- | ----------------------------------------------------------------------------------- |
| `id`         | `Integer` → `INTEGER` / `SERIAL`                       | **PK**        | no   | auto-increment | Surrogate primary key.                                                              |
| `name`       | `String(100)` → `VARCHAR(100)`                         | **U**, **IX** | no   | —              | Tier name (e.g. "Khối", "Phòng", "Tổ"); unique so the catalog has no duplicates.    |
| `rank`       | `Integer` → `INTEGER`                                  | **U**, **IX** | no   | —              | Display order, high→low (1 = highest tier); unique so two tiers never share a rank. |
| `head_title` | `String(100)` → `VARCHAR(100)`                         | —             | no   | `""`           | Title of the person heading a unit at this level (e.g. "Trưởng khối", "Tổ trưởng"). |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —             | no   | now (UTC)      | When the level row was created.                                                     |

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
narrows the list. `tax_code` (MST) is optional and only _soft_-checked for duplicates — a
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
| `status` | `String(16)` → `VARCHAR(16)` | — | no | `active` | **DORMANT (redesign spec-06 v2)** — lead/active/inactive đã bỏ khỏi UI + logic; cột giữ default `active` cho dữ liệu cũ, không dùng cho nghiệp vụ mới. |
| `customer_kind` | `String(12)` → `VARCHAR(12)` | — | no | `cong_ty` | Loại KH (redesign spec-06 v2): `ca_nhan` (cá nhân — form ẩn MST) / `cong_ty` (doanh nghiệp — hiện MST, tùy chọn). Khách cũ mặc định `cong_ty`. Thêm qua migration 0060. |
| `payment_term_days` | `Integer` → `INTEGER` | — | yes | — | **Số ngày công nợ TỐI ĐA** (net terms) — hạn thanh toán kể từ NGÀY XUẤT HÓA ĐƠN (redesign spec-06 v2). Cặp với `credit_limit` thành chính sách "cho nợ" (nợ tối đa X đồng VÀ trong Y ngày). NULL = chưa đặt hạn ngày. Sửa qua `/financial`, gate `set_credit_terms`; lưu + hiển thị (cảnh báo quá hạn là SEAM Công nợ AR). |
| `payment_term_type` | `String(24)` → `VARCHAR(24)` | — | yes | — | **DORMANT (2026-07-15)** — kiểu điều khoản (dropdown `prepay`/`net_delivery`/`net_eom`/`custom`) đã bỏ khỏi UI; chỉ giữ `payment_term_days`. Cột giữ lại, không dùng. |
| `prepay_pct` | `Float` → `FLOAT` | — | yes | — | **DORMANT (2026-07-15)** — % trả trước đã bỏ khỏi UI. Cột giữ lại, không dùng. |
| `payment_term_note` | `String(500)` → `VARCHAR(500)` | — | yes | — | **DORMANT (2026-07-15)** — ghi chú điều khoản tự do đã bỏ khỏi UI. Cột giữ lại, không dùng. |
| `discount_trade_pct` | `Float` → `FLOAT` | — | yes | — | **DORMANT (redesign spec-06 v2)** — "CK mặc định" đã bỏ, thay bằng rào `discount_min/max_pct`. Cột giữ lại, không dùng. |
| `discount_buyer_pct` | `Float` → `FLOAT` | — | yes | — | **DORMANT (redesign spec-06 v2)** — như trên. Cột giữ lại, không dùng. |
| `discount_min_pct` | `Float` → `FLOAT` | — | yes | — | Sàn chiết khấu cho phép (%) — rào chắn báo giá (redesign spec-06 v2). % ∈ [0,100], `min ≤ max`; NULL = chưa đặt. Sửa cần `set_credit_terms`. Thêm qua migration 0060. |
| `discount_max_pct` | `Float` → `FLOAT` | — | yes | — | Trần chiết khấu cho phép (%). Thêm qua migration 0060. |
| `margin_min_pct` | `Float` → `FLOAT` | — | yes | — | Sàn biên lợi nhuận yêu cầu (%). Thêm qua migration 0060. |
| `margin_max_pct` | `Float` → `FLOAT` | — | yes | — | Trần biên lợi nhuận (%). Thêm qua migration 0060. |
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

### `customer_contacts`

**Purpose:** người liên hệ của khách hàng (khảo sát #10–#11: khách luôn có nhiều người —
mua hàng, kho, kế toán, kỹ thuật — cần chức vụ + nhiệm vụ để các bộ phận tự liên hệ).
`customers.contact_name` vẫn giữ làm "liên hệ nhanh"; bảng này là danh sách đầy đủ.
Bất biến (service): tối đa MỘT `is_primary` mỗi khách.

| Column        | Type (SQLAlchemy → SQLite / Postgres)                  | Key                                   | Null | Default        | Meaning                                             |
| ------------- | ------------------------------------------------------ | ------------------------------------- | ---- | -------------- | --------------------------------------------------- |
| `id`          | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                                | no   | auto-increment | Surrogate primary key.                              |
| `customer_id` | `Integer` → `INTEGER`                                  | **FK→customers.id** (CASCADE), **IX** | no   | —              | Khách hàng sở hữu.                                  |
| `name`        | `String(255)` → `VARCHAR(255)`                         | —                                     | no   | —              | Tên người liên hệ (bắt buộc).                       |
| `title`       | `String(120)` → `VARCHAR(120)`                         | —                                     | yes  | —              | Chức vụ (kế toán, mua hàng…).                       |
| `duty`        | `String(255)` → `VARCHAR(255)`                         | —                                     | yes  | —              | Nhiệm vụ (đối chiếu công nợ, nhận hàng…).           |
| `phone`       | `String(30)` → `VARCHAR(30)`                           | —                                     | yes  | —              | Điện thoại.                                         |
| `email`       | `String(255)` → `VARCHAR(255)`                         | —                                     | yes  | —              | Email.                                              |
| `is_primary`  | `Boolean` → `BOOLEAN`                                  | —                                     | no   | `false`        | Liên hệ chính (#11) — service giữ tối đa một/khách. |
| `created_at`  | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                     | no   | now (UTC)      | Thời điểm tạo.                                      |

**Keys & indexes**

- Primary key: `id`. Index: `ix_customer_contacts_customer_id` on `customer_id`.
- Foreign keys: `customer_id FK→customers.id` (ON DELETE CASCADE).

---

### `customer_addresses`

**Purpose:** địa điểm giao hàng của khách (khảo sát #9: "khách hàng luôn có nhiều vị trí
giao hàng"). CHỖ NỐI Tính giá: phí giao hàng theo điểm giao sẽ đọc danh sách này khi
được wire (chưa wire ở đợt khảo sát). Bất biến (service): tối đa MỘT `is_default`/khách.

| Column        | Type (SQLAlchemy → SQLite / Postgres)                  | Key                                   | Null | Default        | Meaning                                            |
| ------------- | ------------------------------------------------------ | ------------------------------------- | ---- | -------------- | -------------------------------------------------- |
| `id`          | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                                | no   | auto-increment | Surrogate primary key.                             |
| `customer_id` | `Integer` → `INTEGER`                                  | **FK→customers.id** (CASCADE), **IX** | no   | —              | Khách hàng sở hữu.                                 |
| `label`       | `String(120)` → `VARCHAR(120)`                         | —                                     | no   | —              | Tên điểm giao ("Trụ sở", "Nhà máy Bắc Ninh").      |
| `address`     | `String(500)` → `VARCHAR(500)`                         | —                                     | no   | —              | Địa chỉ đầy đủ.                                    |
| `phone`       | `String(30)` → `VARCHAR(30)`                           | —                                     | yes  | —              | SĐT tại điểm giao.                                 |
| `note`        | `String(500)` → `VARCHAR(500)`                         | —                                     | yes  | —              | Ghi chú giao nhận.                                 |
| `is_default`  | `Boolean` → `BOOLEAN`                                  | —                                     | no   | `false`        | Điểm giao mặc định — service giữ tối đa một/khách. |
| `created_at`  | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                     | no   | now (UTC)      | Thời điểm tạo.                                     |

**Keys & indexes**

- Primary key: `id`. Index: `ix_customer_addresses_customer_id` on `customer_id`.
- Foreign keys: `customer_id FK→customers.id` (ON DELETE CASCADE).

---

### `customer_tags`

**Purpose:** nhãn phân loại do SALES GÁN TAY (khảo sát #7: khách lẻ / doanh nghiệp / đại
lý / VIP… "rất cần để phân loại chăm sóc"). Nhãn tự do, một khách nhiều nhãn; service
chặn trùng nhãn (case-insensitive) trong cùng khách. Chạy song song với tier tự động
(nhãn = người nói, tier = dữ liệu nói). Gán/gỡ ghi audit vào Nhật ký khách.

| Column        | Type (SQLAlchemy → SQLite / Postgres)                  | Key                                   | Null | Default        | Meaning                                    |
| ------------- | ------------------------------------------------------ | ------------------------------------- | ---- | -------------- | ------------------------------------------ |
| `id`          | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                                | no   | auto-increment | Surrogate primary key.                     |
| `customer_id` | `Integer` → `INTEGER`                                  | **FK→customers.id** (CASCADE), **IX** | no   | —              | Khách hàng mang nhãn.                      |
| `label`       | `String(50)` → `VARCHAR(50)`                           | **IX**                                | no   | —              | Nội dung nhãn (đã chuẩn hóa khoảng trắng). |
| `created_by`  | `Integer` → `INTEGER`                                  | **FK→users.id**                       | yes  | —              | Người gán.                                 |
| `created_at`  | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                     | no   | now (UTC)      | Thời điểm gán.                             |

**Keys & indexes**

- Primary key: `id`. Indexes: `ix_customer_tags_customer_id`, `ix_customer_tags_label` (lọc theo nhãn).
- Foreign keys: `customer_id FK→customers.id` (ON DELETE CASCADE), `created_by FK→users.id`.

---

### `customer_care_events`

**Purpose:** nhật ký chăm sóc khách (khảo sát #20/#27: ngày nào gọi/nhắn/email/gặp, trao
đổi gì). Hiện trong tab Chăm sóc và gộp vào timeline Nhật ký của khách (kind `care`).

| Column        | Type (SQLAlchemy → SQLite / Postgres)                  | Key                                   | Null | Default        | Meaning                                                                  |
| ------------- | ------------------------------------------------------ | ------------------------------------- | ---- | -------------- | ------------------------------------------------------------------------ |
| `id`          | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                                | no   | auto-increment | Surrogate primary key.                                                   |
| `customer_id` | `Integer` → `INTEGER`                                  | **FK→customers.id** (CASCADE), **IX** | no   | —              | Khách hàng được chăm sóc.                                                |
| `kind`        | `String(24)` → `VARCHAR(24)`                           | —                                     | no   | `khac`         | Hình thức: `goi_dien` / `nhan_tin` / `email` / `gap_truc_tiep` / `khac`. |
| `note`        | `String(1000)` → `VARCHAR(1000)`                       | —                                     | no   | —              | Nội dung trao đổi (bắt buộc).                                            |
| `happened_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                     | no   | now (UTC)      | Thời điểm chăm sóc thật (cho ghi bù).                                    |
| `created_by`  | `Integer` → `INTEGER`                                  | **FK→users.id**                       | yes  | —              | Người ghi.                                                               |
| `created_at`  | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                     | no   | now (UTC)      | Thời điểm ghi.                                                           |

**Keys & indexes**

- Primary key: `id`. Index: `ix_customer_care_events_customer_id` on `customer_id`.
- Foreign keys: `customer_id FK→customers.id` (ON DELETE CASCADE), `created_by FK→users.id`.

---

### `customer_care_tasks`

**Purpose:** việc chăm sóc CẦN LÀM / lịch hẹn follow-up (khảo sát #27–#28: "hẹn ngày 15
gọi lại", nhắc lần 1/2/3). Mức nhắc KHÔNG lưu — tính từ số ngày quá hạn khi đọc (lần 1 =
đến hạn, lần 2 = quá ≥2 ngày, lần 3 = quá ≥5 ngày) nên không cần cron và số luôn thật.
Panel "Cần chăm sóc" trên danh bạ đọc các việc `open` đã đến hạn trong scope người xem.

| Column             | Type (SQLAlchemy → SQLite / Postgres)                  | Key                                   | Null | Default        | Meaning                                                          |
| ------------------ | ------------------------------------------------------ | ------------------------------------- | ---- | -------------- | ---------------------------------------------------------------- |
| `id`               | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                                | no   | auto-increment | Surrogate primary key.                                           |
| `customer_id`      | `Integer` → `INTEGER`                                  | **FK→customers.id** (CASCADE), **IX** | no   | —              | Khách hàng.                                                      |
| `note`             | `String(500)` → `VARCHAR(500)`                         | —                                     | no   | —              | Việc cần làm (bắt buộc).                                         |
| `due_date`         | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                     | no   | —              | Hạn thực hiện.                                                   |
| `status`           | `String(16)` → `VARCHAR(16)`                           | **IX**                                | no   | `open`         | `open` / `done` / `cancelled`.                                   |
| `assignee_user_id` | `Integer` → `INTEGER`                                  | **FK→users.id**, **IX**               | yes  | —              | Người phụ trách việc — mặc định Sale phụ trách khách.            |
| `done_at`          | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                     | yes  | —              | Lúc hoàn thành (so với `due_date` → đúng hạn/trễ, đánh giá #28). |
| `created_by`       | `Integer` → `INTEGER`                                  | **FK→users.id**                       | yes  | —              | Người tạo việc.                                                  |
| `created_at`       | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                     | no   | now (UTC)      | Thời điểm tạo.                                                   |

**Keys & indexes**

- Primary key: `id`. Indexes: `ix_customer_care_tasks_customer_id`, `ix_customer_care_tasks_status`, `ix_customer_care_tasks_assignee_user_id`.
- Foreign keys: `customer_id FK→customers.id` (ON DELETE CASCADE), `assignee_user_id FK→users.id`, `created_by FK→users.id`.

---

### `customer_attachments`

**Purpose:** tài liệu đính kèm hồ sơ khách (khảo sát #21: hợp đồng, GPKD, file thiết kế…).
Bytes nằm dưới `<backend>/static/crm/<customer_id>/`, serve read-only tại `/static`; chỉ
lưu path ở đây (mirror `employee_attachments` / `quote_attachments`).

| Column        | Type (SQLAlchemy → SQLite / Postgres)                  | Key                                   | Null | Default        | Meaning                                                   |
| ------------- | ------------------------------------------------------ | ------------------------------------- | ---- | -------------- | --------------------------------------------------------- |
| `id`          | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                                | no   | auto-increment | Surrogate primary key.                                    |
| `customer_id` | `Integer` → `INTEGER`                                  | **FK→customers.id** (CASCADE), **IX** | no   | —              | Khách hàng sở hữu.                                        |
| `doc_kind`    | `String(24)` → `VARCHAR(24)`                           | —                                     | no   | `khac`         | Loại tài liệu: `hop_dong` / `gpkd` / `thiet_ke` / `khac`. |
| `file_name`   | `String(255)` → `VARCHAR(255)`                         | —                                     | no   | —              | Tên file gốc (đã sanitize).                               |
| `file_url`    | `String(500)` → `VARCHAR(500)`                         | —                                     | no   | —              | Path `/static/crm/<customer_id>/<token>_<name>`.          |
| `file_type`   | `String(100)` → `VARCHAR(100)`                         | —                                     | yes  | —              | MIME type.                                                |
| `uploaded_by` | `Integer` → `INTEGER`                                  | **FK→users.id**                       | yes  | —              | Người upload.                                             |
| `uploaded_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                     | no   | now (UTC)      | Thời điểm upload.                                         |

**Keys & indexes**

- Primary key: `id`. Index: `ix_customer_attachments_customer_id` on `customer_id`.
- Foreign keys: `customer_id FK→customers.id` (ON DELETE CASCADE), `uploaded_by FK→users.id`.

---

### `customer_notes`

**Purpose:** ghi chú TỰ DO của team về một khách (tab "Ghi chú"). Lưu ý dùng chung ("khách
khó tính · thích giao sáng · chốt qua Zalo nhanh nhất"). Khác `customer_care_events` (việc ĐÃ
LÀM, có loại) và Nhật ký (audit + mốc chứng từ). Bảng MỚI → `create_all` tự tạo, KHÔNG cần
migration. KHÔNG ghi audit (giữ tách khỏi Nhật ký).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `customer_id` | `Integer` → `INTEGER` | **FK→customers.id** (CASCADE), **IX** | no | — | Khách hàng sở hữu ghi chú. |
| `body` | `String(4000)` → `VARCHAR(4000)` | — | no | — | Nội dung ghi chú (text tự do). |
| `pinned` | `Boolean` → `BOOLEAN` | — | no | `false` | Ghim ghi chú quan trọng lên đầu danh sách. |
| `created_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Người ghi. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Thời điểm ghi. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | CHỈ set khi sửa NỘI DUNG (bật/tắt ghim không bump); NULL = chưa sửa → FE hiện "đã sửa" khi != NULL. |

**Keys & indexes**

- Primary key: `id`. Index: `ix_customer_notes_customer_id` on `customer_id`.
- Foreign keys: `customer_id FK→customers.id` (ON DELETE CASCADE), `created_by FK→users.id`.

---

### `products`

**Purpose:** the Sản phẩm in catalog head (Product) — spec-07-san-pham. One row per
reusable commercial product ("cái khách mua"); đơn hàng / job reference it, never the
reverse (DOMAIN §29 L701, §34 L865). Khổ/giấy/màu live on `product_components`, NOT here —
a multi-component product (sách: bìa≠ruột) has no single trim size (§34 L894, spec-07
out-of-scope). Price / snapshot giá are NOT stored (snapshotted at order-close copy-on-write,
P0 #5, §34 L877). Portable across SQLite and Postgres.

| Column         | Type (SQLAlchemy → SQLite / Postgres)                  | Key           | Null | Default        | Meaning                                                                                                          |
| -------------- | ------------------------------------------------------ | ------------- | ---- | -------------- | ---------------------------------------------------------------------------------------------------------------- |
| `id`           | `Integer` → `INTEGER` / `SERIAL`                       | **PK**        | no   | auto-increment | Surrogate primary key.                                                                                           |
| `code`         | `String(20)` → `VARCHAR(20)`                           | **U**, **IX** | no   | —              | System-generated sequential code (SP001, SP002…); read-only, never user-entered (§34 L865, KH###/PB### pattern). |
| `name`         | `String(255)` → `VARCHAR(255)`                         | —             | no   | —              | Product name (required, non-blank, unique case-insensitive).                                                     |
| `product_type` | `String(32)` → `VARCHAR(32)`                           | —             | no   | —              | Loại SP (enum §7): catalogue, brochure, tem_nhan, hop, sach, to_roi, name_card.                                  |
| `binding_type` | `String(16)` → `VARCHAR(16)`                           | —             | yes  | —              | Kiểu đóng (enum §5, nullable — chỉ SP có gáy): perfect / saddle / sewn. Null = không gáy.                        |
| `note`         | `String(1000)` → `VARCHAR(1000)`                       | —             | yes  | —              | Ghi chú tự do.                                                                                                   |
| `created_at`   | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —             | no   | now (UTC)      | When the product row was created.                                                                                |

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

| Column            | Type (SQLAlchemy → SQLite / Postgres) | Key                        | Null | Default        | Meaning                                                                                  |
| ----------------- | ------------------------------------- | -------------------------- | ---- | -------------- | ---------------------------------------------------------------------------------------- |
| `id`              | `Integer` → `INTEGER` / `SERIAL`      | **PK**                     | no   | auto-increment | Surrogate primary key.                                                                   |
| `product_id`      | `Integer` → `INTEGER`                 | **FK→products.id**, **IX** | no   | —              | Parent product; `ON DELETE CASCADE` (component deleted with the product).                |
| `sequence`        | `Integer` → `INTEGER`                 | —                          | no   | `0`            | Display / print order (bìa trước ruột…).                                                 |
| `component_type`  | `String(16)` → `VARCHAR(16)`          | —                          | no   | —              | cover / body / insert (§34 L893).                                                        |
| `paper_master_id` | `Integer` → `INTEGER`                 | —                          | yes  | —              | **SEAM-03** FK-nullable to PaperMaster (Danh mục Giấy chưa build); no FK constraint yet. |
| `colors_front`    | `Integer` → `INTEGER`                 | —                          | no   | `0`            | Số màu mặt trước (0..8, §23 L532).                                                       |
| `colors_back`     | `Integer` → `INTEGER`                 | —                          | no   | `0`            | Số màu mặt sau (0..8).                                                                   |
| `page_count`      | `Integer` → `INTEGER`                 | —                          | no   | `0`            | Số trang. body của SP có gáy phải % 4 == 0 (tay sách, §31).                              |
| `finished_w`      | `Numeric(10,2)` → `NUMERIC(10,2)`     | —                          | no   | `0`            | Khổ thành phẩm rộng (>0).                                                                |
| `finished_h`      | `Numeric(10,2)` → `NUMERIC(10,2)`     | —                          | no   | `0`            | Khổ thành phẩm cao (>0).                                                                 |
| `bleed`           | `Numeric(10,2)` → `NUMERIC(10,2)`     | —                          | no   | `0`            | Bleed (mm, ≥0).                                                                          |
| `grain_direction` | `String(8)` → `VARCHAR(8)`            | —                          | yes  | —              | Canh thớ: long / short.                                                                  |

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
| `estimate_id` | `Integer` | **FK→estimates.id** (SET NULL), **IX** | yes | — | Phiếu tính giá ĐẦU TIÊN (tương thích cũ); tham chiếu thật per dòng ở `quote_items.estimate_id`. Gỡ ở BG-4. |
| `phieu_tinh_gia_id` | `Integer` → `INTEGER` | **IX** (soft) | yes | — | **BG-1**: nguồn MỚI = 1 Phiếu tính giá (PTG). Soft link (plain int). 1 PTG → 1 BG đang hiệu lực — guard ở service (KHÔNG unique cứng; cancelled/rejected/expired nhả chỗ). Migration 0051. |
| `salesperson_id` | `Integer` | **FK→users.id** (SET NULL), **IX** | yes | — | Sale phụ trách — RBAC data-scope owner. |
| `status` | `String(20)` | — | no | `draft` | draft/**pending_approval**/sent/accepted/rejected/expired/converted_to_order/cancelled (redesign-bao-gia §3). |
| `current_version_id` | `Integer` | **IX** | yes | — | Phiên bản đang hiệu lực (con trỏ, không FK để tránh vòng). |
| `valid_until` | `Date` | — | yes | — | Hạn hiệu lực; quá hạn → expired (chặn duyệt). |
| `terms_text` | `Text` | — | yes | — | Điều khoản báo giá — 1 khối text, mỗi dòng = 1 điều khoản (bản in tự đánh số). Tạo mới điền sẵn `DEFAULT_TERMS`; gộp từ `payment_terms`+`delivery_terms` cũ (migration 0070). Là thứ DUY NHẤT in ở mục Điều khoản. |
| `delivery_address` | `String(500)` | — | yes | — | Địa chỉ giao (auto-fill từ `CustomerAddress.is_default`). Chỉ-đọc trên báo giá, không in; đơn hàng lấy làm ĐC giao mặc định khi chốt đơn. |
| `contact_name_snapshot` | `String(255)` | — | yes | — | **redesign-bao-gia §5**: người liên hệ snapshot (auto-fill CRM `CustomerContact.is_primary`). Migration 0052. |
| `contact_phone_snapshot` | `String(30)` | — | yes | — | SĐT người liên hệ snapshot. Migration 0052. |
| `contact_title_snapshot` | `String(120)` | — | yes | — | Chức vụ người liên hệ snapshot. Migration 0052. |
| `customer_note` | `String(1000)` | — | yes | — | Ghi chú hiện cho khách. |
| `internal_note` | `String(1000)` | — | yes | — | Ghi chú nội bộ. |
| `cancel_reason` | `String(500)` | — | yes | — | Lý do hủy (bắt buộc khi cancelled). |
| `created_by` | `Integer` | **FK→users.id** (SET NULL) | yes | — | Người tạo. |
| `created_at` | `DateTime(tz)` | — | no | now (UTC) | Tạo lúc. |
| `updated_at` | `DateTime(tz)` | — | no | now (UTC) | Sửa lần cuối (onupdate). |
| `decision_seen_at` | `DateTime(tz)` | — | yes | — | Mốc người soạn đã xem quyết định GĐ gần nhất (real-time gửi duyệt); NULL = có quyết định mới chưa xem. |

> **Bỏ (migration 0070):** `payment_terms`, `delivery_terms` (gộp vào `terms_text`), `deposit_pct` (% cọc chuyển sang **Đơn hàng bán** — thỏa thuận lúc chốt đơn, Kế toán đặt).

### `quote_versions`

**Purpose:** một phiên bản chào giá (v1, v2…) của 1 quote — re-quote sinh version mới, phiếu cũ
`superseded` giữ nguyên lịch sử. Khi **Gửi khách** (draft→sent) version đóng băng
copy-on-write: `estimate_snapshot_json` (spec phiếu tính giá) + `internal_cost_snapshot_json`
(phân rã giá vốn per mức SL) — đổi bảng giá sau này không rewrite phiếu đã gửi (P0 §34).

| Column                          | Type            | Key                                | Null | Default | Meaning                                                                 |
| ------------------------------- | --------------- | ---------------------------------- | ---- | ------- | ----------------------------------------------------------------------- |
| `id`                            | `Integer`       | **PK**                             | no   | auto    | PK.                                                                     |
| `quote_id`                      | `Integer`       | **FK→quotes.id** (CASCADE), **IX** | no   | —       | Header cha.                                                             |
| `version_number`                | `Integer`       | —                                  | no   | `1`     | v1, v2… trong 1 quote.                                                  |
| `status`                        | `String(20)`    | —                                  | no   | `draft` | draft/locked/sent/accepted/rejected/superseded/cancelled (per-version). |
| `change_reason`                 | `String(255)`   | —                                  | yes  | —       | "Lý do/ghi chú phiên bản này" (đổi giấy, khách ép giá…).                |
| `estimate_snapshot_json`        | `JSON`          | —                                  | yes  | —       | **Copy-on-write** spec phiếu tính giá tại lúc gửi.                      |
| `internal_cost_snapshot_json`   | `JSON`          | —                                  | yes  | —       | **Copy-on-write** phân rã giá vốn (options → lines).                    |
| `customer_output_snapshot_json` | `JSON`          | —                                  | yes  | —       | Bản chốt nội dung đối ngoại (PDF data) nếu render.                      |
| `pricing_snapshot_json`         | `JSON`          | —                                  | yes  | —       | Tham số pricing đã áp (gói biên, rounding…).                            |
| `total_cost_snapshot`           | `Numeric(15,2)` | —                                  | yes  | —       | Tổng giá vốn khóa của version.                                          |
| `subtotal_amount`               | `Numeric(15,2)` | —                                  | no   | `0`     | Tổng giá bán trước VAT/chiết khấu.                                      |
| `discount_amount`               | `Numeric(15,2)` | —                                  | no   | `0`     | Chiết khấu tổng.                                                        |
| `vat_percent`                   | `Numeric(5,2)`  | —                                  | no   | `0`     | %VAT áp version.                                                        |
| `vat_amount`                    | `Numeric(15,2)` | —                                  | no   | `0`     | Tiền VAT.                                                               |
| `final_amount`                  | `Numeric(15,2)` | —                                  | no   | `0`     | Tổng cộng (đã VAT).                                                     |
| `pdf_file_url`                  | `String(255)`   | —                                  | yes  | —       | File PDF đối ngoại đã xuất (nếu có).                                    |
| `created_by`                    | `Integer`       | **FK→users.id** (SET NULL)         | yes  | —       | Người tạo version.                                                      |
| `created_at`                    | `DateTime(tz)`  | —                                  | no   | now     | Tạo lúc.                                                                |
| `sent_at`                       | `DateTime(tz)`  | —                                  | yes  | —       | Gửi khách lúc (tính tuổi phiếu "đã gửi N ngày").                        |
| `accepted_at`                   | `DateTime(tz)`  | —                                  | yes  | —       | Khách chốt lúc.                                                         |
| `rejected_at`                   | `DateTime(tz)`  | —                                  | yes  | —       | Từ chối lúc.                                                            |

### `quote_items`

**Purpose:** một dòng hàng của version — **mỗi dòng = 1 phiếu tính giá + 1 mức số lượng đã
pick** (logic chốt: báo giá không soạn tay, chỉ pick từ phiếu tính giá `calculated`). Giá vốn
đóng băng per dòng (`total_cost_snapshot`); markup/VAT per dòng.

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `quote_version_id` | `Integer` | **FK→quote_versions.id** (CASCADE), **IX** | no | — | Version cha. |
| `estimate_id` | `Integer` | **FK→estimates.id** (SET NULL), **IX** | yes | — | Phiếu tính giá gốc của DÒNG NÀY (đa phiếu/1 báo giá — hệ cũ, gỡ ở BG-4). |
| `phieu_thanh_phan_id` | `Integer` → `INTEGER` | (soft) | yes | — | **BG-1**: dòng báo giá nguồn từ 1 "sản phẩm" (`PhieuThanhPhan`) của PTG. Soft ref. Migration 0051. |
| `estimate_option_id` | `Integer` | — | yes | — | Mức số lượng (option) đã pick trong phiếu. |
| `line_no` | `Integer` | — | no | — | Thứ tự dòng. |
| `po_code` | `String(60)` | — | yes | — | Mã PO của khách cho dòng (cột "MÃ PO" mẫu báo giá thật). Migration 0052. |
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

| Column             | Type           | Key                                        | Null | Default | Meaning                      |
| ------------------ | -------------- | ------------------------------------------ | ---- | ------- | ---------------------------- |
| `id`               | `Integer`      | **PK**                                     | no   | auto    | PK.                          |
| `quote_id`         | `Integer`      | **FK→quotes.id** (CASCADE), **IX**         | no   | —       | Phiếu cha.                   |
| `quote_version_id` | `Integer`      | **FK→quote_versions.id** (CASCADE), **IX** | yes  | —       | Gắn version cụ thể (nếu có). |
| `file_name`        | `String(255)`  | —                                          | no   | —       | Tên file.                    |
| `file_url`         | `String(500)`  | —                                          | no   | —       | Đường dẫn lưu trữ.           |
| `file_type`        | `String(100)`  | —                                          | yes  | —       | MIME/loại file.              |
| `uploaded_by`      | `Integer`      | **FK→users.id** (SET NULL)                 | yes  | —       | Người upload.                |
| `uploaded_at`      | `DateTime(tz)` | —                                          | no   | now     | Upload lúc.                  |

### `quote_activity_logs`

**Purpose:** timeline "Hoạt động" của phiếu (tạo version, gửi khách, khách chốt…) — nguồn dữ
liệu cho khung timeline trên UI detail.

| Column                | Type           | Key                                        | Null | Default | Meaning                                      |
| --------------------- | -------------- | ------------------------------------------ | ---- | ------- | -------------------------------------------- |
| `id`                  | `Integer`      | **PK**                                     | no   | auto    | PK.                                          |
| `quote_id`            | `Integer`      | **FK→quotes.id** (CASCADE), **IX**         | no   | —       | Phiếu cha.                                   |
| `quote_version_id`    | `Integer`      | **FK→quote_versions.id** (CASCADE), **IX** | yes  | —       | Version liên quan (nếu có).                  |
| `action`              | `String(50)`   | —                                          | no   | —       | Động từ sự kiện (create_quote, send_quote…). |
| `old_value_json`      | `JSON`         | —                                          | yes  | —       | Giá trị trước (diff).                        |
| `new_value_json`      | `JSON`         | —                                          | yes  | —       | Giá trị sau (diff).                          |
| `actor_id`            | `Integer`      | **FK→users.id** (SET NULL)                 | yes  | —       | Người thao tác.                              |
| `actor_name_snapshot` | `String(255)`  | —                                          | yes  | —       | Tên người thao tác chốt lúc ghi.             |
| `created_at`          | `DateTime(tz)` | —                                          | no   | now     | Xảy ra lúc.                                  |

---

### `orders`

**Purpose:** the Đơn hàng bán header — redesign-don-hang-ban.md (bước ④ CHỐT ĐƠN). One row per đơn.
**2 nguồn** (`source_type`): `bao_gia` (tạo từ báo giá đã duyệt — ghim C1 `quotation_id`+`quotation_version`+
`quotation_effective_from` qua SEAM-04, snapshot giá+giá vốn bất biến) · `nhap_tay` (không giá vốn →
`cost_basis='none'`, biên "không xác định", LUÔN cần duyệt). Vòng đời ACTIVE `draft → ordered → cancelled`
(`on_hold`/`change_order` = hằng số DORMANT, không dùng). Cổng chốt: báo giá còn duyệt & còn hạn AND Σ cọc thực
nhận ≥ `deposit_pct`×tổng (deposit_pct **đặt tại đơn** — Kế toán/`record_deposit`, khóa khỏi Sale; báo giá
không còn giữ % cọc) AND đủ PO+ngày giao AND chứng cứ đồng ý AND
(nhập tay: đã duyệt) AND không đặc thù treo — cọc = Σ `payment_receipts`(`order_id`, `received`) (V5). `parent_order_id` (self-FK) CHỈ cho
**đơn bổ sung** (`order_kind=bo_sung`, giữ kẽm → giá riêng). `order_nature` {hang_hoa, gia_cong} thay
`has_customer_paper` (2 gốc thuế). Layer vật lý (khổ/màu/kẽm/imposition) NEVER lưu ở đây — ẩn khỏi Sale. VAT chân
lý ở `InvoiceLine` (⑬). Hủy: `cancel_*` (lý do + lỗi tại ai) — cọc KHÔNG xóa, "còn cọc chưa quyết toán" suy từ
data. Duyệt bản in + tiến độ SX = luồng NGOÀI hệ thống (không lưu field). Portable across SQLite and Postgres.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `order_no` | `String(20)` → `VARCHAR(20)` | **U**, **IX** | no | — | System-generated order number (DH001, DH002…). Unique. NOT `PB###` (mã phòng ban); pattern chưa xác nhận với SVN. |
| `customer_id` | `Integer` → `INTEGER` | **FK→customers.id**, **IX** | yes | — | Customer kéo từ báo giá (read-only display via CRM). Nullable so a draft can exist while wiring. |
| `quotation_id` | `Integer` → `INTEGER` | **IX** | yes | — | Referenced approved quotation (SEAM-04 quotation_ref). Plain Integer (NO FK) — báo giá versioned, pin the exact version below. |
| `quotation_version` | `Integer` → `INTEGER` | — | yes | — | The exact quotation version pinned (C1); không tự nhảy sang version mới hơn. |
| `quotation_effective_from` | `Date` → `DATE` | — | yes | — | Effective-from of the snapshotted quotation price window (copy-on-write source pointer, not a FK). |
| `order_kind` | `String(16)` → `VARCHAR(16)` | — | no | `moi` | Loại ∈ {moi, bo_sung}. Đơn bổ sung mang giá bán riêng, giữ kẽm cũ → rẻ (§32). *(order_type ĐÃ BỎ 2026-07-16 — mig 0073 drop; in nội bộ đi thẳng Lệnh sản xuất.)* |
| `parent_order_id` | `Integer` → `INTEGER` | **FK→orders.id**, **IX** | yes | — | Đơn gốc — set **CHỈ** khi order_kind=bo_sung (bắt buộc). NULL cho đơn mới; KHÔNG dùng cho change_order. |
| `sale_user_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | yes | — | NV kinh doanh phụ trách (hoa hồng) + RBAC data-scope owner (own/department/all, §41). |
| `status` | `String(16)` → `VARCHAR(16)` | — | no | `draft` | Lifecycle ACTIVE: draft/ordered/cancelled (P1 redesign). `on_hold`/`change_order` = giá trị DORMANT (không dùng trong luồng). |
| `is_rush` | `Boolean` → `BOOLEAN` | — | no | `false` | Đơn GẤP/ưu tiên — Sale bật để xưởng làm trước (chip đỏ + chảy xuống LSX). Migration 0073. |
| `has_customer_paper` | `Boolean` → `BOOLEAN` | — | no | `false` | **DORMANT** (P1 thay bằng `order_nature` {hang_hoa, gia_cong}). |
| `vat_pct_estimate` | `Integer` → `INTEGER` | — | no | `0` | VAT DỰ KIẾN (%) để ước tổng — chân lý ở InvoiceLine (⑬). |
| `cancel_reason` | `String(500)` → `VARCHAR(500)` | — | yes | — | Set only when status=cancelled (F8). |
| `cancelled_at_state` | `String(16)` → `VARCHAR(16)` | — | yes | — | **DORMANT** (P1 dùng `cancel_fault` + lý do hủy). |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the order row was created. |
| `source_type` | `String(16)` → `VARCHAR(16)` | — | no | `bao_gia` | Nguồn tạo đơn ∈ {bao_gia, nhap_tay} (P1 redesign). Migration 0066. |
| `order_nature` | `String(16)` → `VARCHAR(16)` | — | no | `hang_hoa` | Bản chất ∈ {hang_hoa, gia_cong} (2 gốc thuế) — thay has_customer_paper. Migration 0066. |
| `customer_po_no` | `String(100)` → `VARCHAR(100)` | — | yes | — | Số PO khách (mức đơn). |
| `delivery_committed_date` | `Date` → `DATE` | — | yes | — | Ngày giao cam kết ban đầu; dời lịch = module Kế hoạch giao hàng (SEAM-02). |
| `delivery_address` | `String(500)` → `VARCHAR(500)` | — | yes | — | Địa chỉ giao (snapshot, sửa khi nháp). |
| `delivery_contact_name` | `String(255)` → `VARCHAR(255)` | — | yes | — | Người nhận hàng (snapshot, Sale xổ từ danh bạ khách — KHÔNG auto-fill is_primary). Migration 0071. |
| `delivery_contact_phone` | `String(30)` → `VARCHAR(30)` | — | yes | — | SĐT người nhận hàng. Migration 0071. |
| `delivery_note` | `String(500)` → `VARCHAR(500)` | — | yes | — | Lưu ý GIAO HÀNG → tài xế/khâu Giao ("giao giờ HC", "gọi trước 30'"). Migration 0071. |
| `production_note` | `String(500)` → `VARCHAR(500)` | — | yes | — | Lưu ý SẢN XUẤT → tổ in/LSX ("in đúng màu mẫu lần trước"). Migration 0071. |
| `invoice_entity_name` | `String(255)` → `VARCHAR(255)` | — | yes | — | Pháp nhân xuất HĐ (khi khách xin tên khác; mặc định = khách). |
| `invoice_entity_tax_code` | `String(20)` → `VARCHAR(20)` | — | yes | — | MST pháp nhân xuất HĐ. |
| `deposit_pct` | `Float` → `FLOAT` | — | yes | — | % cọc phải thu ĐẶT TẠI ĐƠN (Kế toán/`record_deposit`, khóa khỏi Sale) — base cổng chốt; NULL = chưa đặt. |
| `cost_basis` | `String(16)` → `VARCHAR(16)` | — | no | `quote` | Nguồn giá vốn ∈ {quote, none}; none = nhập tay → biên "không xác định". |
| `needs_approval` | `Boolean` → `BOOLEAN` | — | no | `false` | Đơn cần duyệt tại đơn (nhập tay / bổ sung tự đặt giá). |
| `approval_state` | `String(16)` → `VARCHAR(16)` | — | no | `none` | Trình-duyệt ∈ {none, pending, approved, rejected}. |
| `ordered_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Đóng dấu lúc chốt đơn (P4). |
| `ordered_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Người chốt đơn. |
| `cancel_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Người hủy đơn. |
| `cancel_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Thời điểm hủy. |
| `cancel_fault` | `String(16)` → `VARCHAR(16)` | — | yes | — | Lỗi tại ai khi hủy ∈ {khach, xuong}. |

**Keys & indexes**

- Primary key: `id`.
- Indexes: `ix_orders_order_no` (U), `ix_orders_customer_id`, `ix_orders_quotation_id`, `ix_orders_parent_order_id`, `ix_orders_sale_user_id` (scope filter).
- Foreign keys: `customer_id FK→customers.id` (ON DELETE SET NULL), `parent_order_id FK→orders.id` (ON DELETE SET NULL, self-FK), `sale_user_id FK→users.id`. `quotation_id` is deliberately NOT a FK (SEAM-04; báo giá versioned — the (id, version) pin is the reference).

### `payments`

**Purpose:** ⚠️ **OBSOLETE (2026-07-15):** bảng `payments` (cơ chế cọc sell-side cũ) ĐÃ GỠ khỏi model — cọc mới dùng `order_deposits` (+ `order_deposit_attachments`) đa hình thức, xem trên. Đoạn dưới GIỮ để tham chiếu lịch sử, KHÔNG còn là bảng thực. — (cũ) thu tiền bán (CỌC + đợt thu) của một Đơn hàng bán — Pha A "Lát Tài chính". `deposit_total(order) = NET Σ(thu)−Σ(hoàn)` trên `kind=deposit` là điều kiện chốt đơn ③→④ (§32 L827-828), đóng **SEAM-04 (deposit)**. Cọc **KHÔNG sinh hóa đơn** (N5, NĐ123/2020 — chỉ treo Nợ 111/112 / Có 131); chân lý hóa đơn/doanh thu ở ⑬ (MISA). Khác `payment_vouchers` (Phiếu CHI mua hàng, AP). Bảng MỚI do `create_all` dựng (không cần migration). Portable across SQLite và Postgres.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `order_id` | `Integer` → `INTEGER` | **FK→orders.id**, **IX** | no | — | Đơn hàng bán khoản thu này gắn vào (ON DELETE CASCADE). |
| `customer_id` | `Integer` → `INTEGER` | **FK→customers.id**, **IX** | yes | — | Khách kéo TỪ ĐƠN (cộng dồn công nợ/đối chiếu theo khách). ON DELETE SET NULL. |
| `kind` | `String(16)` → `VARCHAR(16)` | — | no | `deposit` | deposit (cọc, mở cổng chốt) / partial / final (thu đợt sau — Pha D). |
| `direction` | `String(8)` → `VARCHAR(8)` | — | no | `thu` | thu (tiền vào) / hoan (hoàn cọc khi hủy đơn §32). `deposit_total` tính NET thu−hoàn. |
| `amount` | `BigInteger` → `BIGINT` | — | no | `0` | Số tiền (VND). BigInteger vì đơn in giá trị lớn (vượt Int 2³¹). Luôn > 0. |
| `method` | `String(16)` → `VARCHAR(16)` | — | no | `bank` | cash (Nợ 111) / bank (Nợ 112). |
| `paid_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Thời điểm thu. |
| `voucher_no` | `String(40)` → `VARCHAR(40)` | — | yes | — | Số phiếu thu (đối chiếu MISA — §4.9). Nullable. |
| `note` | `String(500)` → `VARCHAR(500)` | — | yes | — | Ghi chú. |
| `created_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Người ghi khoản thu. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the row was created. |

**Keys & indexes**

- Primary key: `id`.
- Indexes: `ix_payments_order_id`, `ix_payments_customer_id`.
- Foreign keys: `order_id FK→orders.id` (ON DELETE CASCADE), `customer_id FK→customers.id` (ON DELETE SET NULL), `created_by FK→users.id`.

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

| Column                | Type (SQLAlchemy → SQLite / Postgres) | Key                      | Null | Default        | Meaning                                                                               |
| --------------------- | ------------------------------------- | ------------------------ | ---- | -------------- | ------------------------------------------------------------------------------------- |
| `id`                  | `Integer` → `INTEGER` / `SERIAL`      | **PK**                   | no   | auto-increment | Surrogate primary key.                                                                |
| `order_id`            | `Integer` → `INTEGER`                 | **FK→orders.id**, **IX** | no   | —              | Owning order (ON DELETE CASCADE).                                                     |
| `description`         | `String(500)` → `VARCHAR(500)`        | —                        | no   | `''`           | Mô tả SP thương mại (đối ngoại). NEVER số màu/kẽm/khổ/imposition/PrintForm.           |
| `qty`                 | `Integer` → `INTEGER`                 | —                        | no   | `1`            | Số lượng dòng đơn.                                                                    |
| `don_vi_tinh`         | `String(30)` → `VARCHAR(30)`          | —                        | no   | `'cái'`        | ĐVT dòng (migration 0075) — kéo từ báo giá (`quote_items.unit`) / gõ tay đơn nhập tay. |
| `unit_price_snapshot` | `Integer` → `INTEGER`                 | —                        | yes  | —              | **P0 copy-on-write**: frozen unit price (VND) từ báo giá. NO live FK.                 |
| `norm_snapshot`       | `JSON` → `JSON`                       | —                        | yes  | —              | **P0 copy-on-write**: frozen norm/định mức snapshot (ngang hàng unit_price_snapshot). |
| `vat_pct_estimate`    | `Integer` → `INTEGER`                 | —                        | no   | `0`            | VAT DỰ KIẾN (%) cho dòng — chân lý ở InvoiceLine (⑬).                                 |
| `line_total`          | `Integer` → `INTEGER`                 | —                        | yes  | —              | Thành tiền = qty × unit_price_snapshot (derived + stored; null khi chưa có giá).      |
| `cost_snapshot`       | `BigInteger` → `BIGINT`               | —                        | yes  | —              | **Copy-on-write**: giá vốn đông cứng từ `QuoteItem.total_cost_snapshot` lúc tạo — CÙNG GRAIN với `line_total` (tổng cả SL), dùng soi biên lợi nhuận. NULL cho đơn cũ (trước A2). |
| `phieu_thanh_phan_id` | `Integer` → `INTEGER`                 | (soft)                   | yes  | —              | Pin truy vết ấn phẩm: `PhieuThanhPhan` của PTG mà dòng báo giá nguồn trỏ tới (song sinh `QuoteItem.phieu_thanh_phan_id`). Soft ref, KHÔNG FK cứng, copy lúc snapshot. NULL cho đơn nhập tay. Migration 0071. |

**Keys & indexes**

- Primary key: `id`.
- Indexes: `ix_order_lines_order_id`.
- Foreign keys: `order_id FK→orders.id` (ON DELETE CASCADE).

**Relationships**

- Many `order_lines` belong to one `orders`. The snapshot pair lives on the line (copy-on-write); no FK to a live price/norm table.

---

### `order_approvals`

**Purpose:** A2 — duyệt "đơn đặc thù" (Giám đốc). Hệ tự soi đơn khi chuẩn bị chốt: **giá trị cao** (tổng gồm VAT ≥ ngưỡng) / **biên lợi nhuận thấp** / **bán dưới giá vốn** → CHẶN chốt ③→④ tới khi GĐ duyệt (audit). Một hàng = một QUYẾT ĐỊNH (duyệt/từ chối), GHIM số + ngưỡng tại thời điểm đó để re-check "bao phủ" lúc chốt (đơn xấu đi so mức GĐ ký → `stale`, phải trình lại) + căn cứ audit. Vượt-hạn-mức-công-nợ HOÃN Pha D (chưa có hóa đơn → nợ = −cọc là số giả). Bảng MỚI do `create_all` dựng (không cần migration). Portable across SQLite và Postgres.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `order_id` | `Integer` → `INTEGER` | **FK→orders.id**, **IX** | no | — | Đơn được duyệt (ON DELETE CASCADE). |
| `decision` | `String(16)` → `VARCHAR(16)` | — | no | — | `approved` (duyệt, mở khóa chốt nếu bao phủ) / `rejected` (từ chối, chặn). |
| `triggers_json` | `JSON` → `JSON` | — | yes | — | Các điều kiện đặc thù đang bật lúc quyết định (`['high_value','low_margin','below_cost']`). |
| `order_total` | `BigInteger` → `BIGINT` | — | no | `0` | GHIM tổng GỒM VAT lúc quyết định (đối chiếu ngưỡng giá-trị-cao khi re-check bao phủ). |
| `order_subtotal` | `BigInteger` → `BIGINT` | — | no | `0` | GHIM subtotal TRƯỚC VAT (base tính biên) lúc quyết định. |
| `order_cost` | `BigInteger` → `BIGINT` | — | yes | — | GHIM tổng giá vốn snapshot lúc quyết định (null nếu không soi được biên). |
| `margin_pct_snapshot` | `Integer` → `INTEGER` | — | yes | — | GHIM biên (%) lúc quyết định — hiển thị/audit. |
| `min_margin_pct` | `Integer` → `INTEGER` | — | yes | — | Ngưỡng biên đang HIỆU LỰC lúc GĐ ký (đổi hằng số sau vẫn còn căn cứ audit). |
| `high_value_threshold` | `BigInteger` → `BIGINT` | — | yes | — | Ngưỡng giá-trị-cao đang HIỆU LỰC lúc GĐ ký. |
| `note` | `String(1000)` → `VARCHAR(1000)` | — | yes | — | Lý do GĐ (khuyến nghị khi từ chối). |
| `decided_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Người quyết định (GĐ). ON DELETE SET NULL. |
| `decided_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Thời điểm quyết định (tie-break cho "bản gần nhất"). |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the row was created. |

**Keys & indexes**

- Primary key: `id`.
- Indexes: `ix_order_approvals_order_id`.
- Foreign keys: `order_id FK→orders.id` (ON DELETE CASCADE), `decided_by FK→users.id` (ON DELETE SET NULL).

**Relationships**

- Many `order_approvals` belong to one `orders`. Bản GẦN NHẤT (theo `decided_at`, tie-break `id`) quyết định cổng chốt: `approved`+bao phủ → cleared; `rejected`/`stale`/chưa có → chặn.

---

### `order_attachments`

**Purpose:** Đính kèm CẤP ĐƠN — chứng cứ khách đồng ý (`kind=consent`, ảnh PO/Zalo…) làm điều kiện cổng chốt §8(d) cho đơn nhập tay. Bytes dưới `<backend>/static/don-hang/<order_id>/`, phục vụ qua `/static`. Bảng MỚI do `create_all` dựng. Portable.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `order_id` | `Integer` → `INTEGER` | **FK→orders.id**, **IX** | no | — | Đơn gắn đính kèm (ON DELETE CASCADE). |
| `kind` | `String(16)` → `VARCHAR(16)` | — | no | `consent` | Loại đính kèm (hiện: consent = chứng cứ khách đồng ý). |
| `file_url` | `String(500)` → `VARCHAR(500)` | — | no | — | URL phục vụ qua /static. |
| `file_name` | `String(255)` → `VARCHAR(255)` | — | yes | — | Tên file gốc. |
| `content_type` | `String(100)` → `VARCHAR(100)` | — | yes | — | MIME type. |
| `size_bytes` | `Integer` → `INTEGER` | — | no | `0` | Kích thước file (byte). |
| `uploaded_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Người tải lên. ON DELETE SET NULL. |
| `uploaded_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When uploaded. |

**Keys & indexes**

- Primary key: `id`. Indexes: `ix_order_attachments_order_id`. Foreign keys: `order_id`→orders.id (CASCADE), `uploaded_by`→users.id (SET NULL).

---

### `quote_approvals`

**Purpose:** BG-2 — GĐ duyệt "báo giá ĐẶC THÙ" (biên thấp / bán dưới vốn / giá trị cao) → chặn "gửi khách" tới khi duyệt. **Song sinh** với `order_approvals` (cùng máy `services/exception_gate.py`), khóa theo `quote_id`. GHIM số + ngưỡng lúc quyết định để re-check "bao phủ" (báo giá đổi xấu đi → trình lại) + audit. Bản GẦN NHẤT quyết định cổng. Đơn hàng tạo từ báo giá đã duyệt "bao phủ" → A2 tự thông. Bảng MỚI do `create_all` dựng. Portable across SQLite và Postgres.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `quote_id` | `Integer` → `INTEGER` | **FK→quotes.id**, **IX** | no | — | Báo giá được duyệt (ON DELETE CASCADE). |
| `decision` | `String(16)` → `VARCHAR(16)` | — | no | — | `approved` (duyệt, mở "gửi khách" nếu bao phủ) / `rejected` (từ chối). |
| `triggers_json` | `JSON` → `JSON` | — | yes | — | Điều kiện đặc thù đang bật lúc quyết định (`['high_value','low_margin','below_cost']`). |
| `total` | `BigInteger` → `BIGINT` | — | no | `0` | GHIM tổng GỒM VAT lúc quyết định (mốc quy mô khi re-check bao phủ). |
| `subtotal` | `BigInteger` → `BIGINT` | — | no | `0` | GHIM subtotal TRƯỚC VAT (base biên) lúc quyết định. |
| `cost` | `BigInteger` → `BIGINT` | — | yes | — | GHIM tổng giá vốn lúc quyết định (null nếu không soi được biên). |
| `margin_pct_snapshot` | `Integer` → `INTEGER` | — | yes | — | GHIM biên (%) lúc quyết định — hiển thị/audit. |
| `min_margin_pct` | `Integer` → `INTEGER` | — | yes | — | Ngưỡng biên đang HIỆU LỰC lúc GĐ ký. |
| `high_value_threshold` | `BigInteger` → `BIGINT` | — | yes | — | Ngưỡng giá-trị-cao đang HIỆU LỰC lúc GĐ ký. |
| `note` | `String(1000)` → `VARCHAR(1000)` | — | yes | — | Lý do GĐ (khuyến nghị khi từ chối). |
| `decided_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Người quyết định (GĐ). ON DELETE SET NULL. |
| `decided_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Thời điểm quyết định (tie-break "bản gần nhất"). |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | When the row was created. |

**Keys & indexes**

- Primary key: `id`. Indexes: `ix_quote_approvals_quote_id`.
- Foreign keys: `quote_id FK→quotes.id` (ON DELETE CASCADE), `decided_by FK→users.id` (ON DELETE SET NULL).

**Relationships**

- Many `quote_approvals` belong to one `quotes`. Bản GẦN NHẤT quyết định cổng "gửi khách"; `approved`+bao phủ → cho gửi; `rejected`/`stale`/chưa có → chặn.

---

### `costings`

**Purpose:** the Tính giá (Costing / giá thành nội bộ) header — spec-08-tinh-gia. One row per
phương án tính giá for a product + số lượng; Báo giá đọc lại kết quả (§43 L1217–1219). This
screen reads **live versioned** đơn giá/định mức and does NOT snapshot (snapshot P0
copy-on-write = chốt Đơn hàng, §34 L877-878). No bậc SL / lãi / chiết khấu here (thuộc Báo
giá). `product_id` is read via **SEAM-11** (ProductRead · `san_pham`). Portable across SQLite
and Postgres.

| Column       | Type (SQLAlchemy → SQLite / Postgres)                  | Key                        | Null | Default        | Meaning                                                                                                                        |
| ------------ | ------------------------------------------------------ | -------------------------- | ---- | -------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `id`         | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                     | no   | auto-increment | Surrogate primary key.                                                                                                         |
| `code`       | `String(20)` → `VARCHAR(20)`                           | **U**, **IX**              | no   | —              | System-generated sequential code (CG001, CG002…); read-only, never user-entered (SP###/KH###/PB### pattern).                   |
| `product_id` | `Integer` → `INTEGER`                                  | **FK→products.id**, **IX** | yes  | —              | **SEAM-11** the product this costing is for; `ON DELETE SET NULL`. Nullable so a draft can start before the product is picked. |
| `qty_final`  | `Integer` → `INTEGER`                                  | —                          | no   | `0`            | Số lượng cần giao (bắt buộc >0, validated in the service). KHÔNG bậc SL (A1).                                                  |
| `status`     | `String(16)` → `VARCHAR(16)`                           | —                          | no   | `draft`        | Vòng đời: draft (đang lập) / ready (đủ input để Báo giá đọc). No snapshot.                                                     |
| `note`       | `String(1000)` → `VARCHAR(1000)`                       | —                          | yes  | —              | Ghi chú tự do.                                                                                                                 |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                          | no   | now (UTC)      | When the costing row was created.                                                                                              |

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

> 1 phương án giấy per costing để so sánh giá vốn. `sheet_paper_master_id` is an FK-nullable
> **SEAM-07** seam to PaperMaster (Danh mục Giấy / Kho · `dm_giay_vat_tu`/`kho`) — a plain
> nullable Integer (no FK) until that catalog exists; giá per-ram/kg + lot_type + ownership are
> looked up via the raising port stub, never fabricated.

| Column                  | Type (SQLAlchemy → SQLite / Postgres) | Key                        | Null | Default        | Meaning                                                                                  |
| ----------------------- | ------------------------------------- | -------------------------- | ---- | -------------- | ---------------------------------------------------------------------------------------- |
| `id`                    | `Integer` → `INTEGER` / `SERIAL`      | **PK**                     | no   | auto-increment | Surrogate primary key.                                                                   |
| `costing_id`            | `Integer` → `INTEGER`                 | **FK→costings.id**, **IX** | no   | —              | Parent costing; `ON DELETE CASCADE`.                                                     |
| `sheet_paper_master_id` | `Integer` → `INTEGER`                 | —                          | yes  | —              | **SEAM-07** FK-nullable to PaperMaster (Danh mục Giấy chưa build); no FK constraint yet. |
| `sheet_w`               | `Numeric(10,2)` → `NUMERIC(10,2)`     | —                          | no   | `0`            | Khổ tờ in rộng (cm).                                                                     |
| `sheet_h`               | `Numeric(10,2)` → `NUMERIC(10,2)`     | —                          | no   | `0`            | Khổ tờ in cao (cm).                                                                      |
| `pieces_per_sheet`      | `Integer` → `INTEGER`                 | —                          | no   | `0`            | Số con/khổ NHẬP TAY (>0); gợi ý song song là hình học (§31a), giá trị nhập là chuẩn.     |
| `grain_locked`          | `Boolean` → `BOOLEAN`                 | —                          | no   | `false`        | Ràng buộc thớ: khi true gợi ý bỏ nhánh xoay (§31 L782).                                  |
| `selected`              | `Boolean` → `BOOLEAN`                 | —                          | no   | `false`        | Phương án giấy được chọn để "dùng" (so sánh — F7).                                       |

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

| Column           | Type (SQLAlchemy → SQLite / Postgres) | Key                        | Null | Default        | Meaning                                                         |
| ---------------- | ------------------------------------- | -------------------------- | ---- | -------------- | --------------------------------------------------------------- |
| `id`             | `Integer` → `INTEGER` / `SERIAL`      | **PK**                     | no   | auto-increment | Surrogate primary key.                                          |
| `costing_id`     | `Integer` → `INTEGER`                 | **FK→costings.id**, **IX** | no   | —              | Parent costing; `ON DELETE CASCADE`.                            |
| `sequence`       | `Integer` → `INTEGER`                 | —                          | no   | `0`            | Display / process order.                                        |
| `name`           | `String(255)` → `VARCHAR(255)`        | —                          | no   | —              | Tên công đoạn gia công (cán màng, bế, đóng cuốn…).              |
| `execution_mode` | `String(16)` → `VARCHAR(16)`          | —                          | no   | `internal`     | internal (khoán nội bộ · SEAM-08) / outsourced (NCC · SEAM-12). |

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

| Column               | Type (SQLAlchemy → SQLite / Postgres)                  | Key                                       | Null | Default        | Meaning                                                                       |
| -------------------- | ------------------------------------------------------ | ----------------------------------------- | ---- | -------------- | ----------------------------------------------------------------------------- |
| `id`                 | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                                    | no   | auto-increment | Surrogate primary key.                                                        |
| `estimate_number`    | `String(20)` → `VARCHAR(20)`                           | **U**, **IX**                             | no   | —              | Auto-generated sequential code (TG26-0001, TG26-0002...).                     |
| `customer_id`        | `Integer` → `INTEGER`                                  | **IX**                                    | yes  | —              | Optional CRM customer reference.                                              |
| `product_type`       | `String(50)` → `VARCHAR(50)`                           | **FK→product_types_catalog.product_type** | no   | —              | Reference to product type strategy configuration.                             |
| `product_name`       | `String(255)` → `VARCHAR(255)`                         | —                                         | no   | —              | Name of product being estimated.                                              |
| `status`             | `String(20)` → `VARCHAR(20)`                           | —                                         | no   | `draft`        | Status (draft, calculated, cancelled).                                        |
| `input_spec_json`    | `JSON` → `JSON`                                        | —                                         | no   | —              | Complete input specification configuration.                                   |
| `quantity_list_json` | `JSON` → `JSON`                                        | —                                         | no   | —              | List of quantity points calculated.                                           |
| `created_by`         | `Integer` → `INTEGER`                                  | **FK→users.id**                           | yes  | —              | User who created the estimate.                                                |
| `created_at`         | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                         | no   | now (UTC)      | Creation timestamp.                                                           |
| `updated_at`         | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                         | no   | now (UTC)      | Last updated timestamp.                                                       |
| `locked_at`          | `DateTime` → `TIMESTAMP`                               | —                                         | yes  | —              | §9 lifecycle: khi phiếu bị khóa (đông cứng để Báo giá đọc); null = chưa khóa. |
| `version`            | `Integer` → `INTEGER`                                  | —                                         | no   | `1`            | §9 lifecycle: số phiên bản phiếu tính giá (re-estimate sinh version mới).     |
| `parent_id`          | `Integer` → `INTEGER`                                  | —                                         | yes  | —              | §9 lifecycle: phiếu cha (phiếu gốc khi tạo phiên bản mới); null = phiếu gốc.  |
| `superseded_by_id`   | `Integer` → `INTEGER`                                  | —                                         | yes  | —              | §9 lifecycle: phiếu kế thừa thay thế phiếu này; null = chưa bị thay.          |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_estimates_estimate_number` on `estimate_number`.
- Index: `ix_estimates_customer_id` on `customer_id`.
- Foreign keys: `product_type FK→product_types_catalog.product_type`, `created_by FK→users.id`.

---

### `estimate_options`

**Purpose:** calculated estimate results for a specific quantity point.

| Column              | Type (SQLAlchemy → SQLite / Postgres) | Key                         | Null | Default        | Meaning                              |
| ------------------- | ------------------------------------- | --------------------------- | ---- | -------------- | ------------------------------------ |
| `id`                | `Integer` → `INTEGER` / `SERIAL`      | **PK**                      | no   | auto-increment | Surrogate primary key.               |
| `estimate_id`       | `Integer` → `INTEGER`                 | **FK→estimates.id**, **IX** | no   | —              | Parent estimate ID.                  |
| `quantity`          | `Integer` → `INTEGER`                 | —                           | no   | —              | Quantity point calculated.           |
| `total_cost`        | `Numeric(15,2)` → `NUMERIC(15,2)`     | —                           | no   | `0`            | Total internal estimated cost.       |
| `warnings_json`     | `JSON` → `JSON`                       | —                           | yes  | —              | List of warnings or blocking errors. |
| `margin_percent`    | `Numeric(5,2)` → `NUMERIC(5,2)`       | —                           | no   | `0`            | Desired profit margin (%).           |
| `selling_price`     | `Numeric(15,2)` → `NUMERIC(15,2)`     | —                           | no   | `0`            | Base selling price.                  |
| `discount_amount`   | `Numeric(15,2)` → `NUMERIC(15,2)`     | —                           | no   | `0`            | Absolute discount.                   |
| `vat_percent`       | `Numeric(5,2)` → `NUMERIC(5,2)`       | —                           | no   | `0`            | VAT rate (%).                        |
| `vat_amount`        | `Numeric(15,2)` → `NUMERIC(15,2)`     | —                           | no   | `0`            | Calculated VAT amount.               |
| `final_price`       | `Numeric(15,2)` → `NUMERIC(15,2)`     | —                           | no   | `0`            | Selling price after discount + VAT.  |
| `unit_price`        | `Numeric(15,2)` → `NUMERIC(15,2)`     | —                           | no   | `0`            | Per unit final price.                |
| `actual_margin`     | `Numeric(5,2)` → `NUMERIC(5,2)`       | —                           | no   | `0`            | Actual margin calculated.            |
| `included_in_quote` | `Boolean` → `BOOLEAN`                 | —                           | no   | `false`        | Selected for inclusion in quotation. |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `uix_estimate_options_estimate_qty` on `(estimate_id, quantity)`.
- Index: `ix_estimate_options_estimate_id` on `estimate_id`.
- Foreign keys: `estimate_id FK→estimates.id ON DELETE CASCADE`.

---

### `estimate_cost_lines`

**Purpose:** detail breakdown of costs for an estimate option.

| Column                      | Type (SQLAlchemy → SQLite / Postgres) | Key                                | Null | Default        | Meaning                                 |
| --------------------------- | ------------------------------------- | ---------------------------------- | ---- | -------------- | --------------------------------------- |
| `id`                        | `Integer` → `INTEGER` / `SERIAL`      | **PK**                             | no   | auto-increment | Surrogate primary key.                  |
| `estimate_option_id`        | `Integer` → `INTEGER`                 | **FK→estimate_options.id**, **IX** | no   | —              | Parent estimate option ID.              |
| `category`                  | `String(32)` → `VARCHAR(32)`          | —                                  | no   | —              | Cost pool category.                     |
| `description`               | `String(255)` → `VARCHAR(255)`        | —                                  | no   | —              | Text description.                       |
| `source_type`               | `String(50)` → `VARCHAR(50)`          | —                                  | yes  | —              | DB table for source rate.               |
| `source_id`                 | `Integer` → `INTEGER`                 | —                                  | yes  | —              | ID of source rate.                      |
| `source_snapshot_json`      | `JSON` → `JSON`                       | —                                  | yes  | —              | Copy of source configuration rate/norm. |
| `calculation_snapshot_json` | `JSON` → `JSON`                       | —                                  | yes  | —              | Interim parameters and math formula.    |
| `quantity`                  | `Numeric(12,2)` → `NUMERIC(12,2)`     | —                                  | no   | —              | Quantity of resource used.              |
| `unit`                      | `String(16)` → `VARCHAR(16)`          | —                                  | no   | —              | Unit of resource.                       |
| `unit_cost`                 | `Numeric(15,2)` → `NUMERIC(15,2)`     | —                                  | no   | —              | Rate per resource unit.                 |
| `setup_cost`                | `Numeric(15,2)` → `NUMERIC(15,2)`     | —                                  | no   | `0`            | Setup fee of operation or machine.      |
| `min_charge_applied`        | `Boolean` → `BOOLEAN`                 | —                                  | no   | `false`        | Whether minimum charge was triggered.   |
| `total_cost`                | `Numeric(15,2)` → `NUMERIC(15,2)`     | —                                  | no   | —              | Final computed line cost.               |
| `note`                      | `String(500)` → `VARCHAR(500)`        | —                                  | yes  | —              | Ghi chú.                                |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_estimate_cost_lines_estimate_option_id` on `estimate_option_id`.
- Foreign keys: `estimate_option_id FK→estimate_options.id ON DELETE CASCADE`.

---

### `audit_logs`

**Purpose:** one row per privilege-changing action (gán phòng, gán vai trò, sửa khuôn
quyền, khóa tài khoản) for the Activity Log.

| Column          | Type (SQLAlchemy → SQLite / Postgres)                  | Key             | Null | Default        | Meaning                                                      |
| --------------- | ------------------------------------------------------ | --------------- | ---- | -------------- | ------------------------------------------------------------ |
| `id`            | `Integer` → `INTEGER` / `SERIAL`                       | **PK**          | no   | auto-increment | Surrogate primary key.                                       |
| `actor_user_id` | `Integer` → `INTEGER`                                  | **FK→users.id** | yes  | —              | The user who performed the action (null if system/seed).     |
| `action`        | `String(64)` → `VARCHAR(64)`                           | —               | no   | —              | Action code (e.g. `assign_role`, `lock_user`).               |
| `target`        | `String(255)` → `VARCHAR(255)`                         | —               | no   | `""`           | What the action targeted (e.g. the affected user/role).      |
| `detail`        | `Text` → `TEXT`                                        | —               | no   | `""`           | Free-text detail / before→after summary.                     |
| `created_at`    | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | **IX**          | no   | now (UTC)      | When the action happened (indexed for time-ordered listing). |

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

| Column       | Type (SQLAlchemy → SQLite / Postgres)                  | Key                     | Null | Default        | Meaning                                                                                                                                                   |
| ------------ | ------------------------------------------------------ | ----------------------- | ---- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`         | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                  | no   | auto-increment | Surrogate primary key.                                                                                                                                    |
| `user_id`    | `Integer` → `INTEGER`                                  | **FK→users.id**, **IX** | no   | —              | The user this refresh token authenticates.                                                                                                                |
| `token_hash` | `String(64)` → `VARCHAR(64)`                           | **U**, **IX**           | no   | —              | SHA-256 hex digest of the opaque token. The plaintext is NEVER stored.                                                                                    |
| `family_id`  | `String(36)` → `VARCHAR(36)`                           | **IX**                  | no   | —              | Rotation-chain id. Reusing a revoked token revokes every sibling in the family (theft signal).                                                            |
| `expires_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                       | no   | —              | When this token stops being valid.                                                                                                                        |
| `revoked_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                       | yes  | —              | Set when the token is rotated away or logged out; a non-null value means dead.                                                                            |
| `user_agent` | `String(400)` → `VARCHAR(400)`                         | —                       | yes  | —              | User-Agent captured when the token was issued (spec-08); shown as the "device" of a session in the admin user-detail view. Never used for auth decisions. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                       | no   | now (UTC)      | When the token row was created.                                                                                                                           |

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

| Column                      | Type (SQLAlchemy → SQLite / Postgres)                  | Key           | Null | Default        | Meaning                                                                                                  |
| --------------------------- | ------------------------------------------------------ | ------------- | ---- | -------------- | -------------------------------------------------------------------------------------------------------- |
| `id`                        | `Integer` → `INTEGER` / `SERIAL`                       | **PK**        | no   | auto-increment | Surrogate primary key.                                                                                   |
| `product_type`              | `String(32)` → `VARCHAR(32)`                           | **U**, **IX** | no   | —              | Unique key for the product type (e.g. `catalogue`, `business_card`).                                     |
| `name`                      | `String(100)` → `VARCHAR(100)`                         | —             | no   | —              | Human display name (e.g. `Catalogue`, `Name card`).                                                      |
| `calculation_strategy`      | `String(32)` → `VARCHAR(32)`                           | —             | no   | —              | Enum strategy (e.g. `sheet_based`, `page_based`, `area_based`, `roll_based`, `box_based`, `book_based`). |
| `required_fields`           | `JSON` → `TEXT` / `JSONB`                              | —             | yes  | —              | Array of required fields for inputs.                                                                     |
| `default_operations`        | `JSON` → `TEXT` / `JSONB`                              | —             | yes  | —              | Array of default operation codes.                                                                        |
| `allowed_materials`         | `JSON` → `TEXT` / `JSONB`                              | —             | yes  | —              | Array of allowed material types.                                                                         |
| `compatible_technologies`   | `JSON` → `TEXT` / `JSONB`                              | —             | yes  | —              | Array of compatible technology keys.                                                                     |
| `product_group`             | `String(24)` → `VARCHAR(24)`                           | —             | no   | `an_pham`      | §A Nhóm sản phẩm (an_pham/bao_bi/sach/nhan/khac).                                                        |
| `technology`                | `String(20)` → `VARCHAR(20)`                           | —             | no   | `offset`       | §A Công nghệ áp dụng chính.                                                                              |
| `description`               | `Text` → `TEXT`                                        | —             | yes  | —              | §A Mô tả nghiệp vụ.                                                                                      |
| `display_order`             | `Integer` → `INTEGER`                                  | —             | no   | `100`          | §A Thứ tự hiển thị.                                                                                      |
| `version`                   | `Integer` → `INTEGER`                                  | —             | no   | `1`            | §A Version metadata (clone bump).                                                                        |
| `effective_from`            | `Date` → `DATE`                                        | —             | yes  | —              | §A Ngày bắt đầu hiệu lực.                                                                                |
| `effective_to`              | `Date` → `DATE`                                        | —             | yes  | —              | §A Ngày kết thúc hiệu lực.                                                                               |
| `used_count`                | `Integer` → `INTEGER`                                  | —             | no   | `0`            | §A Số lần đã dùng (guard).                                                                               |
| `shown_fields`              | `JSON` → `TEXT` / `JSONB`                              | —             | yes  | —              | §B Field hiển thị trên màn Tính giá (superset của required).                                             |
| `dimension_rule_type`       | `String(16)` → `VARCHAR(16)`                           | —             | no   | `finished`     | §C Kiểu kích thước tính số con (finished/spread/multi_page).                                             |
| `default_bleed_mm`          | `Numeric(6,2)` → `NUMERIC`                             | —             | no   | `0`            | §C Bleed mặc định (mm).                                                                                  |
| `default_gutter_mm`         | `Numeric(6,2)` → `NUMERIC`                             | —             | no   | `0`            | §C Gutter mặc định (mm).                                                                                 |
| `default_trim_mm`           | `Numeric(6,2)` → `NUMERIC`                             | —             | no   | `0`            | §C Lề xén mặc định (mm).                                                                                 |
| `allow_rotation`            | `Boolean` → `BOOLEAN`                                  | —             | no   | `true`         | §C Cho phép xoay bài.                                                                                    |
| `allow_custom_size`         | `Boolean` → `BOOLEAN`                                  | —             | no   | `true`         | §C Cho phép nhập khổ custom.                                                                             |
| `has_page_count`            | `Boolean` → `BOOLEAN`                                  | —             | no   | `false`        | §D Có dùng số trang.                                                                                     |
| `page_multiple`             | `Integer` → `INTEGER`                                  | —             | no   | `0`            | §D Số trang chia hết cho (0 = không ràng buộc).                                                          |
| `pages_per_signature`       | `Integer` → `INTEGER`                                  | —             | no   | `0`            | §D Số trang mỗi tay.                                                                                     |
| `has_cover_body_split`      | `Boolean` → `BOOLEAN`                                  | —             | no   | `false`        | §D Tính bìa/ruột riêng.                                                                                  |
| `default_paper_material_id` | `Integer` → `INTEGER`                                  | —             | yes  | —              | §E Giấy mặc định (materials.id).                                                                         |
| `default_cover_material_id` | `Integer` → `INTEGER`                                  | —             | yes  | —              | §E Giấy bìa mặc định.                                                                                    |
| `default_body_material_id`  | `Integer` → `INTEGER`                                  | —             | yes  | —              | §E Giấy ruột mặc định.                                                                                   |
| `default_ink_material_id`   | `Integer` → `INTEGER`                                  | —             | yes  | —              | §E Mực mặc định.                                                                                         |
| `has_packaging`             | `Boolean` → `BOOLEAN`                                  | —             | no   | `false`        | §E Có bao bì.                                                                                            |
| `default_pack_qty`          | `Integer` → `INTEGER`                                  | —             | no   | `0`            | §E Quy cách đóng gói (cái/thùng).                                                                        |
| `required_operations`       | `JSON` → `TEXT` / `JSONB`                              | —             | yes  | —              | §F Công đoạn bắt buộc (⊆ default_operations).                                                            |
| `allow_extra_operations`    | `Boolean` → `BOOLEAN`                                  | —             | no   | `true`         | §F Cho phép thêm công đoạn ngoài template.                                                               |
| `sheet_count_mode`          | `String(16)` → `VARCHAR(16)`                           | —             | no   | `by_pieces`    | §H Cách tính số tờ (by_pieces/by_pages/manual).                                                          |
| `ink_cost_mode`             | `String(20)` → `VARCHAR(20)`                           | —             | no   | `per_1000`     | §H Cách tính mực (per_1000/coverage).                                                                    |
| `has_tooling`               | `Boolean` → `BOOLEAN`                                  | —             | no   | `false`        | §H Có phát sinh khuôn.                                                                                   |
| `default_tooling_type`      | `String(20)` → `VARCHAR(20)`                           | —             | yes  | —              | §H Loại khuôn mặc định.                                                                                  |
| `allow_manual_override`     | `Boolean` → `BOOLEAN`                                  | —             | no   | `false`        | §H Cho phép override công thức.                                                                          |
| `waste_pct`                 | `Numeric(6,2)` → `NUMERIC`                             | —             | no   | `0`            | §H % bù hao đội vào số tờ in (giấy+mực+giờ máy, không đội kẽm); thay module Định mức & Bù hao cũ.        |
| `is_active`                 | `Boolean` → `BOOLEAN`                                  | —             | no   | `true`         | Active status of the product type configuration.                                                         |
| `created_at`                | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —             | no   | now (UTC)      | When the row was created.                                                                                |
| `updated_at`                | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —             | no   | now (UTC)      | When the row was last updated.                                                                           |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_product_types_catalog_product_type` on `product_type`.

**Relationships**

- Referenced as a foreign key by `norms.product_type`.

---

### `materials`

**Purpose:** unified catalog of raw materials and consumables (Paper, Decal, PP, canvas, carton, film, formex, lamination film, glue, chemical...).

| Column              | Type (SQLAlchemy → SQLite / Postgres)                  | Key           | Null | Default        | Meaning                                                                                                        |
| ------------------- | ------------------------------------------------------ | ------------- | ---- | -------------- | -------------------------------------------------------------------------------------------------------------- |
| `id`                | `Integer` → `INTEGER` / `SERIAL`                       | **PK**        | no   | auto-increment | Surrogate primary key.                                                                                         |
| `code`              | `String(20)` → `VARCHAR(20)`                           | **U**, **IX** | no   | —              | Unique master code (GY### for paper, VT### for other materials).                                               |
| `name`              | `String(255)` → `VARCHAR(255)`                         | —             | no   | —              | Master material name.                                                                                          |
| `material_type`     | `String(32)` → `VARCHAR(32)`                           | **IX**        | no   | —              | Material category (e.g. `paper`, `decal`, `pp`, `canvas`, `carton`, `film`, `lamination`, `glue`, `chemical`). |
| `unit`              | `String(16)` → `VARCHAR(16)`                           | —             | no   | —              | Unit of measurement (e.g. `to`, `m2`, `kg`, `cuon`, `cai`).                                                    |
| `min_fee`           | `BigInteger` → `BIGINT`                                | —             | no   | `0`            | Minimum usage fee (VND).                                                                                       |
| `width_cm`          | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | yes  | —              | Width dimensions (cm) for sheets and rolls.                                                                    |
| `height_cm`         | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | yes  | —              | Height/length dimensions (cm) for sheets. Null for rolls.                                                      |
| `gsm`               | `Integer` → `INTEGER`                                  | —             | yes  | —              | Paper grammage / density weight (gsm).                                                                         |
| `thickness_mm`      | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | yes  | —              | Thickness dimensions (mm).                                                                                     |
| `default_waste_pct` | `Numeric(5,2)` → `NUMERIC(5,2)`                        | —             | no   | `0.0`          | Default waste percentage.                                                                                      |
| `min_purchase_qty`  | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | no   | `0.0`          | Minimum quantity required for purchase.                                                                        |
| `paper_family`      | `String(32)` → `VARCHAR(32)`                           | —             | yes  | —              | Paper family family designation (Couche, Ivory, Ford, Bristol, Duplex...).                                     |
| `surface`           | `String(32)` → `VARCHAR(32)`                           | —             | yes  | —              | Surface tráng/bề mặt description (bong, mo, trang-1-mat...).                                                   |
| `material_group`    | `String(20)` → `VARCHAR(20)`                           | **IX**        | yes  | —              | Nhóm vật tư trục UI (`paper`/`ink`/`film`/`glue`/`packaging`/`auxiliary`); `material_type` vẫn là trục engine. |
| `default_supplier`  | `String(150)` → `VARCHAR(150)`                         | —             | yes  | —              | Nhà cung cấp mặc định.                                                                                         |
| `base_uom`          | `String(16)` → `VARCHAR(16)`                           | —             | yes  | —              | Đơn vị cơ sở (base UoM).                                                                                       |
| `purchase_uom`      | `String(16)` → `VARCHAR(16)`                           | —             | yes  | —              | Đơn vị mua hàng (purchase UoM).                                                                                |
| `consumption_uom`   | `String(16)` → `VARCHAR(16)`                           | —             | yes  | —              | Đơn vị tiêu hao (consumption UoM).                                                                             |
| `conversion_method` | `String(24)` → `VARCHAR(24)`                           | —             | yes  | —              | Cách quy đổi UoM (`gsm_area`/`ream_500`/`area_m2`/`fixed_factor`/`none`).                                      |
| `conversion_factor` | `Numeric(12,4)` → `NUMERIC(12,4)`                      | —             | yes  | —              | Hệ số quy đổi UoM.                                                                                             |
| `ink_type`          | `String(32)` → `VARCHAR(32)`                           | —             | yes  | —              | Loại mực (nhóm ink).                                                                                           |
| `ink_color_system`  | `String(32)` → `VARCHAR(32)`                           | —             | yes  | —              | Hệ màu mực (nhóm ink).                                                                                         |
| `ink_color_code`    | `String(32)` → `VARCHAR(32)`                           | —             | yes  | —              | Mã màu mực (nhóm ink).                                                                                         |
| `film_type`         | `String(32)` → `VARCHAR(32)`                           | —             | yes  | —              | Loại film (nhóm film).                                                                                         |
| `version`           | `Integer` → `INTEGER`                                  | —             | no   | `1`            | Số phiên bản bản ghi (optimistic lock).                                                                        |
| `is_active`         | `Boolean` → `BOOLEAN`                                  | —             | no   | `true`         | Active status in selection pickers.                                                                            |
| `created_at`        | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —             | no   | now (UTC)      | When the material was created.                                                                                 |
| `updated_at`        | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —             | no   | now (UTC)      | When the material was last updated.                                                                            |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_materials_code` on `code`.
- Index: `ix_materials_material_type` on `material_type`.

**Relationships**

- One material has many historical `material_costs`.

---

### `material_costs`

**Purpose:** time-versioned unit cost prices for materials.

| Column           | Type (SQLAlchemy → SQLite / Postgres)                  | Key                         | Null | Default        | Meaning                                                           |
| ---------------- | ------------------------------------------------------ | --------------------------- | ---- | -------------- | ----------------------------------------------------------------- |
| `id`             | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                      | no   | auto-increment | Surrogate primary key.                                            |
| `material_id`    | `Integer` → `INTEGER`                                  | **FK→materials.id**, **IX** | no   | —              | Reference to target material.                                     |
| `price_unit`     | `String(16)` → `VARCHAR(16)`                           | —                           | no   | —              | Unit this price corresponds to (e.g. `to`, `ram`, `kg`, `m2`).    |
| `unit_price`     | `BigInteger` → `BIGINT`                                | —                           | no   | `0`            | Cost price (VND).                                                 |
| `supplier`       | `String(150)` → `VARCHAR(150)`                         | —                           | yes  | —              | Nhà cung cấp của mức giá này.                                     |
| `price_type`     | `String(20)` → `VARCHAR(20)`                           | —                           | no   | `standard`     | Loại giá (`standard`...).                                         |
| `vat_included`   | `Boolean` → `BOOLEAN`                                  | —                           | no   | `false`        | Giá đã bao gồm VAT hay chưa.                                      |
| `transport_fee`  | `BigInteger` → `BIGINT`                                | —                           | no   | `0`            | Phí vận chuyển (VND).                                             |
| `moq`            | `Numeric(12,2)` → `NUMERIC(12,2)`                      | —                           | no   | `0.0`          | Số lượng đặt hàng tối thiểu (MOQ).                                |
| `lead_time_days` | `Integer` → `INTEGER`                                  | —                           | no   | `0`            | Thời gian giao hàng (ngày).                                       |
| `quantity_from`  | `Numeric(14,2)` → `NUMERIC(14,2)`                      | —                           | yes  | —              | Cận dưới bậc số lượng (price tier).                               |
| `quantity_to`    | `Numeric(14,2)` → `NUMERIC(14,2)`                      | —                           | yes  | —              | Cận trên bậc số lượng (price tier).                               |
| `version`        | `Integer` → `INTEGER`                                  | —                           | no   | `1`            | Số phiên bản bản ghi (optimistic lock).                           |
| `effective_from` | `Date` → `DATE`                                        | —                           | no   | —              | Date pricing becomes active.                                      |
| `effective_to`   | `Date` → `DATE`                                        | —                           | yes  | —              | Date pricing stops being active. Null means current active price. |
| `created_at`     | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                           | no   | now (UTC)      | Creation timestamp.                                               |
| `updated_at`     | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                           | no   | now (UTC)      | Last updated timestamp.                                           |

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

| Column                             | Type (SQLAlchemy → SQLite / Postgres)                  | Key           | Null | Default        | Meaning                                                                                                     |
| ---------------------------------- | ------------------------------------------------------ | ------------- | ---- | -------------- | ----------------------------------------------------------------------------------------------------------- |
| `id`                               | `Integer` → `INTEGER` / `SERIAL`                       | **PK**        | no   | auto-increment | Surrogate primary key.                                                                                      |
| `code`                             | `String(20)` → `VARCHAR(20)`                           | **U**, **IX** | no   | —              | Unique machine code (MY###).                                                                                |
| `name`                             | `String(255)` → `VARCHAR(255)`                         | —             | no   | —              | Machine name.                                                                                               |
| `machine_type`                     | `String(32)` → `VARCHAR(32)`                           | **IX**        | no   | —              | Type designation (offset, digital, large_format, flexo...).                                                 |
| `process_type`                     | `String(32)` → `VARCHAR(32)`                           | —             | no   | —              | Production step mapped (in, can_mang, be, gap...).                                                          |
| `max_width_cm`                     | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | yes  | —              | Max width of sheet/roll machine can process.                                                                |
| `max_height_cm`                    | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | yes  | —              | Max height of sheet machine can process.                                                                    |
| `min_width_cm`                     | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | yes  | —              | Min width machine can process.                                                                              |
| `min_height_cm`                    | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | yes  | —              | Min height machine can process.                                                                             |
| `speed`                            | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | no   | —              | Processing speed (must be > 0).                                                                             |
| `speed_unit`                       | `String(32)` → `VARCHAR(32)`                           | —             | no   | —              | Speed unit (trang/phut, to/gio, m2/gio).                                                                    |
| `setup_time_mins`                  | `Integer` → `INTEGER`                                  | —             | no   | `0`            | Setup/makeready time (minutes).                                                                             |
| `changeover_time_mins`             | `Integer` → `INTEGER`                                  | —             | no   | `0`            | Job changeover/cleanup time (minutes).                                                                      |
| `setup_waste_sheets`               | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | no   | `0.0`          | Fixed sheets/material waste during setup.                                                                   |
| `supported_materials`              | `JSON` → `TEXT` / `JSONB`                              | —             | yes  | —              | List of supported material_type codes.                                                                      |
| `num_ink_units`                    | `Integer` → `INTEGER`                                  | —             | yes  | —              | Số đơn vị in (số màu in được 1 lượt); dùng tính số pass `⌈màu/num_ink_units⌉` (§31c). Null = không áp dụng. |
| `supports_perfecting`              | `Boolean` → `BOOLEAN`                                  | —             | no   | `false`        | Máy in được 2 mặt trong 1 lượt (trở nhật/lật, §3).                                                          |
| `machine_group`                    | `String(20)` → `VARCHAR(20)`                           | —             | no   | `may_in`       | Nhóm máy — `may_in`/`may_can`/`may_be`/`may_xen`/`khac`.                                                    |
| `status`                           | `String(16)` → `VARCHAR(16)`                           | —             | no   | `active`       | Trạng thái — `active`/`inactive`/`maintenance`. `is_active` được suy từ status.                             |
| `note`                             | `Text` → `TEXT`                                        | —             | yes  | —              | Ghi chú.                                                                                                    |
| `max_print_width_cm`               | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | yes  | —              | Khổ IN tối đa (vùng in) — rộng. ≤ khổ giấy tối đa.                                                          |
| `max_print_height_cm`              | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | yes  | —              | Khổ IN tối đa — cao.                                                                                        |
| `gripper_cm`                       | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | no   | `0`            | Nhíp máy (cm) — trừ khỏi vùng in khả dụng.                                                                  |
| `side_margin_cm`                   | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | no   | `0`            | Lề an toàn ngang (cm).                                                                                      |
| `top_bottom_margin_cm`             | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | no   | `0`            | Lề an toàn dọc (cm).                                                                                        |
| `min_speed`                        | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | yes  | —              | Tốc độ tối thiểu.                                                                                           |
| `max_speed`                        | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —             | yes  | —              | Tốc độ tối đa.                                                                                              |
| `setup_time_base_hour`             | `Numeric(8,3)` → `NUMERIC(8,3)`                        | —             | no   | `0`            | Setup cố định (giờ). Tổng các \*\_hour = 0 ⇒ engine fallback `(setup_time_mins+changeover)/60`.             |
| `setup_time_per_color_hour`        | `Numeric(8,3)` → `NUMERIC(8,3)`                        | —             | no   | `0`            | Setup theo màu (giờ/màu).                                                                                   |
| `setup_time_per_side_hour`         | `Numeric(8,3)` → `NUMERIC(8,3)`                        | —             | no   | `0`            | Setup theo mặt (giờ/mặt).                                                                                   |
| `cleaning_time_hour`               | `Numeric(8,3)` → `NUMERIC(8,3)`                        | —             | no   | `0`            | Vệ sinh máy (giờ).                                                                                          |
| `color_change_time_hour`           | `Numeric(8,3)` → `NUMERIC(8,3)`                        | —             | no   | `0`            | Đổi màu (giờ/màu).                                                                                          |
| `plate_change_time_per_plate_hour` | `Numeric(8,3)` → `NUMERIC(8,3)`                        | —             | no   | `0`            | Đổi kẽm (giờ/bản).                                                                                          |
| `color_check_time_hour`            | `Numeric(8,3)` → `NUMERIC(8,3)`                        | —             | no   | `0`            | Kiểm/canh màu (giờ).                                                                                        |
| `min_setup_time_hour`              | `Numeric(8,3)` → `NUMERIC(8,3)`                        | —             | no   | `0`            | Clamp dưới cho giờ setup.                                                                                   |
| `max_setup_time_hour`              | `Numeric(8,3)` → `NUMERIC(8,3)`                        | —             | yes  | —              | Clamp trên cho giờ setup.                                                                                   |
| `rounding_hour_policy`             | `String(8)` → `VARCHAR(8)`                             | —             | no   | `none`         | Làm tròn giờ máy — `none`/`0.01`/`0.25`/`0.5`.                                                              |
| `overhead_included`                | `Boolean` → `BOOLEAN`                                  | —             | no   | `true`         | Overhead xưởng đã gồm trong đơn giá giờ.                                                                    |
| `operator_included`                | `Boolean` → `BOOLEAN`                                  | —             | no   | `true`         | Nhân công vận hành đã gồm trong đơn giá giờ (hourly_rate_includes_operator).                                |
| `used_count`                       | `Integer` → `INTEGER`                                  | —             | no   | `0`            | Số báo giá snapshot đã dùng máy. `>0` ⇒ khóa sửa thông số ảnh hưởng giá; không xóa.                         |
| `created_by`                       | `Integer` → `INTEGER`                                  | **FK**        | yes  | —              | Người tạo → `users.id` (ON DELETE SET NULL).                                                                |
| `updated_by`                       | `Integer` → `INTEGER`                                  | **FK**        | yes  | —              | Người sửa → `users.id` (ON DELETE SET NULL).                                                                |
| `is_active`                        | `Boolean` → `BOOLEAN`                                  | —             | no   | `true`         | Active status of machine (suy từ `status == active`).                                                       |
| `created_at`                       | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —             | no   | now (UTC)      | Creation timestamp.                                                                                         |
| `updated_at`                       | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —             | no   | now (UTC)      | Last updated timestamp.                                                                                     |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_machines_code` on `code`.
- Index: `ix_machines_machine_type` on `machine_type`.

**Relationships**

- One machine has many historical `machine_rates` and references in `norms`.

---

### `machine_rates`

**Purpose:** hourly rates and minimum job fees for running machines over time.

| Column              | Type (SQLAlchemy → SQLite / Postgres)                  | Key                        | Null | Default        | Meaning                                                                                                                        |
| ------------------- | ------------------------------------------------------ | -------------------------- | ---- | -------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `id`                | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                     | no   | auto-increment | Surrogate primary key.                                                                                                         |
| `machine_id`        | `Integer` → `INTEGER`                                  | **FK→machines.id**, **IX** | no   | —              | Reference to machine.                                                                                                          |
| `hourly_rate`       | `BigInteger` → `BIGINT`                                | —                          | no   | —              | Rate per hour of machine usage (VND); dùng khi `billing_mode=per_hour`.                                                        |
| `impression_rate`   | `BigInteger` → `BIGINT`                                | —                          | no   | `0`            | D1 — đơn giá công in cho 1 lượt-màu (1 tờ×1 màu×1 mặt); dùng khi `billing_mode=per_impression`. 0 = chưa cấu hình ⇒ công in 0. |
| `min_charge`        | `BigInteger` → `BIGINT`                                | —                          | no   | `0`            | Minimum charge for running this machine (VND).                                                                                 |
| `min_run_time_mins` | `Integer` → `INTEGER`                                  | —                          | no   | `0`            | Minimum running time billed (minutes).                                                                                         |
| `rate_depreciation` | `BigInteger` → `BIGINT`                                | —                          | no   | `0`            | Cấu thành tham khảo: khấu hao (đ/giờ). Engine chỉ dùng tổng `hourly_rate`.                                                     |
| `rate_energy`       | `BigInteger` → `BIGINT`                                | —                          | no   | `0`            | Cấu thành tham khảo: điện/vật tư phụ (đ/giờ).                                                                                  |
| `rate_maintenance`  | `BigInteger` → `BIGINT`                                | —                          | no   | `0`            | Cấu thành tham khảo: bảo trì (đ/giờ).                                                                                          |
| `rate_labor`        | `BigInteger` → `BIGINT`                                | —                          | no   | `0`            | Cấu thành tham khảo: nhân công (đ/giờ).                                                                                        |
| `rate_overhead`     | `BigInteger` → `BIGINT`                                | —                          | no   | `0`            | Cấu thành tham khảo: overhead xưởng (đ/giờ).                                                                                   |
| `effective_from`    | `Date` → `DATE`                                        | —                          | no   | —              | Pricing effective start date.                                                                                                  |
| `effective_to`      | `Date` → `DATE`                                        | —                          | yes  | —              | Pricing effective end date. Null means current.                                                                                |
| `created_at`        | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                          | no   | now (UTC)      | Creation timestamp.                                                                                                            |
| `updated_at`        | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                          | no   | now (UTC)      | Last updated timestamp.                                                                                                        |

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

| Column                    | Type (SQLAlchemy → SQLite / Postgres)                  | Key           | Null | Default           | Meaning                                                                                                                                                                      |
| ------------------------- | ------------------------------------------------------ | ------------- | ---- | ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                      | `Integer` → `INTEGER` / `SERIAL`                       | **PK**        | no   | auto-increment    | Surrogate primary key.                                                                                                                                                       |
| `code`                    | `String(20)` → `VARCHAR(20)`                           | **U**, **IX** | no   | —                 | Unique operation code (CD###).                                                                                                                                               |
| `name`                    | `String(255)` → `VARCHAR(255)`                         | —             | no   | —                 | Operation name.                                                                                                                                                              |
| `operation_type`          | `String(32)` → `VARCHAR(32)`                           | **IX**        | no   | —                 | Operation type (in, can_mang, be, gap, dong_cuon, dong_goi).                                                                                                                 |
| `unit`                    | `String(16)` → `VARCHAR(16)`                           | —             | no   | —                 | Unit of quantity (e.g. `m2`, `luot`, `to`, `cuon`, `san_pham`).                                                                                                              |
| `allow_outsource`         | `Boolean` → `BOOLEAN`                                  | —             | no   | `false`           | Whether this operation can be outsourced.                                                                                                                                    |
| `basis_quantity`          | `String(16)` → `VARCHAR(16)`                           | —             | no   | `to`              | Đại lượng engine nhân với run_rate (m2/to/luot/cm2/cuon/cai/thung/kg) — §2.2.                                                                                                |
| `pricing_method`          | `String(16)` → `VARCHAR(16)`                           | —             | no   | `theo_sp`         | Hình thức tính công nhân công (theo_gio/theo_ca/theo_sp/khoan) — mục 14.                                                                                                     |
| `process_group`           | `String(20)` → `VARCHAR(20)`                           | —             | no   | `sau_in`          | Phân nhóm công đoạn (sau_in/dong_goi/dac_biet) — spec §A.                                                                                                                    |
| `process_type`            | `String(16)` → `VARCHAR(16)`                           | —             | no   | `internal`        | Luồng xử lý: nội bộ / thuê ngoài / cả hai (internal/outsource/both) — spec §A.                                                                                               |
| `default_sequence`        | `Integer` → `INTEGER`                                  | —             | no   | `0`               | Thứ tự mặc định của công đoạn trong luồng xử lý.                                                                                                                             |
| `quantity_formula_type`   | `String(20)` → `VARCHAR(20)`                           | —             | no   | `print_sheet_qty` | Công thức lượng tính (print_sheet_qty/finished_qty/area_m2/linear_meter/book_qty/box_qty/pack_qty/manual) — spec §B.                                                         |
| `allow_manual_quantity`   | `Boolean` → `BOOLEAN`                                  | —             | no   | `false`           | Cho phép nhập tay số lượng thay vì tính tự động — spec §B.                                                                                                                   |
| `internal_pricing_method` | `String(16)` → `VARCHAR(16)`                           | —             | no   | `per_qty`         | Cách tính nội bộ: theo sản lượng / giờ máy / kết hợp (per_qty/per_hour/combined) — spec §C.                                                                                  |
| `labor_people_count`      | `Numeric(6,2)` → `NUMERIC(6,2)`                        | —             | no   | `1`               | Số người tham gia (dùng cho nhân công theo giờ) — spec §D.                                                                                                                   |
| `has_tooling`             | `Boolean` → `BOOLEAN`                                  | —             | no   | `false`           | Có sử dụng khuôn/tooling hay không — spec §F.                                                                                                                                |
| `tooling_type`            | `String(20)` → `VARCHAR(20)`                           | —             | yes  | —                 | Loại khuôn (khuon_be/khuon_ep_kim/khuon_dap_noi/other) — spec §F.                                                                                                            |
| `tooling_rate_id`         | `Integer` → `INTEGER`                                  | **IX**        | yes  | —                 | Link tới bảng giá khuôn (`plate_die_rates.id`, plain Integer no FK); engine lấy giá khuôn theo pricing_method của bảng đó. NULL = dùng `operation_rates.tooling_unit_price`. |
| `has_yield_loss`          | `Boolean` → `BOOLEAN`                                  | —             | no   | `false`           | Có phát sinh hao hụt/bù hao hay không — spec §G.                                                                                                                             |
| `default_yield_rate`      | `Numeric(6,2)` → `NUMERIC(6,2)`                        | —             | yes  | —                 | Tỷ lệ đạt mặc định (%), vd 98.00 — spec §G.                                                                                                                                  |
| `default_yield_rule`      | `String(40)` → `VARCHAR(40)`                           | —             | yes  | —                 | Mã rule bù hao mặc định, vd YIELD_DIECUT — spec §G.                                                                                                                          |
| `is_active`               | `Boolean` → `BOOLEAN`                                  | —             | no   | `true`            | Active status.                                                                                                                                                               |
| `created_at`              | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —             | no   | now (UTC)         | Creation timestamp.                                                                                                                                                          |
| `updated_at`              | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —             | no   | now (UTC)         | Last updated timestamp.                                                                                                                                                      |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_operations_code` on `code`.
- Index: `ix_operations_operation_type` on `operation_type`.

**Relationships**

- One operation has many historical `operation_rates`, `vendor_service_rates`, and references in `norms`.

---

### `operation_rates`

**Purpose:** rates, setup fees and labor charges for operations over time.

| Column                     | Type (SQLAlchemy → SQLite / Postgres)                  | Key                          | Null | Default        | Meaning                                                     |
| -------------------------- | ------------------------------------------------------ | ---------------------------- | ---- | -------------- | ----------------------------------------------------------- |
| `id`                       | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                       | no   | auto-increment | Surrogate primary key.                                      |
| `operation_id`             | `Integer` → `INTEGER`                                  | **FK→operations.id**, **IX** | no   | —              | Reference to operation.                                     |
| `setup_fee`                | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Flat setup fee (VND).                                       |
| `run_rate`                 | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Rate per quantity unit (VND).                               |
| `labor_rate`               | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Labor rate per hour if any (VND).                           |
| `min_charge`               | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Minimum charge for using this operation (VND).              |
| `speed`                    | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —                            | no   | `0.0`          | Speed of operation in units per hour.                       |
| `setup_time_mins`          | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —                            | no   | `0`            | Thời gian setup/đổi khuôn cho công đoạn (phút) — mục 12.    |
| `hourly_rate`              | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Đơn giá giờ máy nội bộ (per_hour/combined) (VND) — spec §C. |
| `labor_shift_rate`         | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Đơn giá nhân công theo ca (VND) — spec §D.                  |
| `labor_fixed`              | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Nhân công khoán cố định (VND) — spec §D.                    |
| `labor_min`                | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Nhân công tối thiểu (VND) — spec §D.                        |
| `tooling_unit_price`       | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Đơn giá khuôn/tooling (VND) — spec §F.                      |
| `outsource_supplier`       | `String(255)` → `VARCHAR(255)`                         | —                            | yes  | —              | Nhà cung cấp thuê ngoài — spec §E.                          |
| `outsource_unit_price`     | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Đơn giá thuê ngoài theo đơn vị (VND) — spec §E.             |
| `outsource_setup_fee`      | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Phí setup thuê ngoài (VND) — spec §E.                       |
| `outsource_min_charge`     | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Phí tối thiểu thuê ngoài (VND) — spec §E.                   |
| `outsource_transport_fee`  | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Phí vận chuyển thuê ngoài (VND) — spec §E.                  |
| `outsource_moq`            | `BigInteger` → `BIGINT`                                | —                            | no   | `0`            | Sản lượng tối thiểu đặt hàng thuê ngoài (MOQ) — spec §E.    |
| `outsource_lead_time_days` | `Integer` → `INTEGER`                                  | —                            | no   | `0`            | Thời gian giao hàng thuê ngoài (ngày) — spec §E.            |
| `effective_from`           | `Date` → `DATE`                                        | —                            | no   | —              | Pricing effective start date.                               |
| `effective_to`             | `Date` → `DATE`                                        | —                            | yes  | —              | Pricing effective end date. Null means current.             |
| `created_at`               | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                            | no   | now (UTC)      | Creation timestamp.                                         |
| `updated_at`               | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                            | no   | now (UTC)      | Last updated timestamp.                                     |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_operation_rates_operation_id` on `operation_id`.
- Unique index: `uix_operation_rates_current` on `(operation_id) WHERE effective_to IS NULL`.
- Foreign key: `operation_id FK→operations.id`.

- Belongs to one `operations`.

---

### `plate_die_rates`

**Purpose:** Đơn giá kẽm & khuôn (#5) — kẽm in offset (`ban_kem_offset`, engine chọn theo MÁY áp dụng) và khuôn gia công (`khuon_be`/`khuon_ep_kim`/`khuon_dap_noi`/`khuon_khac`, theo `pricing_method`). Versioning hiệu lực-theo-ngày, family key = **`code`** (một bản mở duy nhất mỗi mã).

| Column                 | Type (SQLAlchemy → SQLite / Postgres)                  | Key             | Null | Default        | Meaning                                                                                              |
| ---------------------- | ------------------------------------------------------ | --------------- | ---- | -------------- | ---------------------------------------------------------------------------------------------------- |
| `id`                   | `Integer` → `INTEGER` / `SERIAL`                       | **PK**          | no   | auto-increment | Surrogate primary key.                                                                               |
| `code`                 | `String(40)` → `VARCHAR(40)`                           | **IX**          | no   | —              | Mã bảng giá (PLATE_102_CTP, DIE_BOX_STD…). Family key của version-chain; một bản MỞ duy nhất mỗi mã. |
| `name`                 | `String(255)` → `VARCHAR(255)`                         | —               | no   | —              | Tên bảng giá.                                                                                        |
| `plate_type`           | `String(32)` → `VARCHAR(32)`                           | **IX**          | no   | —              | ban_kem_offset / khuon_be / khuon_ep_kim / khuon_dap_noi / khuon_khac.                               |
| `technology`           | `String(32)` → `VARCHAR(32)`                           | —               | no   | —              | offset / flexo / be / ep_kim / dap_noi.                                                              |
| `unit`                 | `String(16)` → `VARCHAR(16)`                           | —               | no   | —              | ban / bo / cm2 / met.                                                                                |
| `plate_kind`           | `String(16)` → `VARCHAR(16)`                           | —               | yes  | —              | Loại kẽm: ctp / ps / thuong.                                                                         |
| `plate_width_mm`       | `Integer` → `INTEGER`                                  | —               | yes  | —              | Khổ kẽm rộng (mm).                                                                                   |
| `plate_height_mm`      | `Integer` → `INTEGER`                                  | —               | yes  | —              | Khổ kẽm dài (mm).                                                                                    |
| `machine_ids`          | `JSON` → `JSON`                                        | —               | yes  | —              | List machine id áp dụng (NULL/`[]`=mọi máy); engine chọn giá kẽm theo máy.                           |
| `unit_price`           | `BigInteger` → `BIGINT`                                | —               | no   | —              | Đơn giá 1 bản kẽm / khuôn cố định (VND).                                                             |
| `setup_fee`            | `BigInteger` → `BIGINT`                                | —               | no   | `0`            | Phí setup cố định (VND).                                                                             |
| `min_charge`           | `BigInteger` → `BIGINT`                                | —               | no   | `0`            | Phí tối thiểu (VND).                                                                                 |
| `pricing_method`       | `String(20)` → `VARCHAR(20)`                           | —               | no   | `fixed`        | Cách tính khuôn: fixed / area / perimeter / size_tier / manual.                                      |
| `unit_price_area`      | `BigInteger` → `BIGINT`                                | —               | no   | `0`            | Đơn giá theo diện tích (VND/cm²).                                                                    |
| `unit_price_perimeter` | `BigInteger` → `BIGINT`                                | —               | no   | `0`            | Đơn giá theo chu vi (VND/mét dao).                                                                   |
| `max_charge`           | `BigInteger` → `BIGINT`                                | —               | yes  | —              | Trần chi phí khuôn (VND).                                                                            |
| `allow_manual_price`   | `Boolean` → `BOOLEAN`                                  | —               | no   | `false`        | Cho phép nhập tay giá khuôn.                                                                         |
| `reusable`             | `Boolean` → `BOOLEAN`                                  | —               | no   | `false`        | Cho dùng lại khuôn cũ.                                                                               |
| `reuse_price_method`   | `String(16)` → `VARCHAR(16)`                           | —               | yes  | —              | Khi dùng lại: zero / maintenance_fee / manual.                                                       |
| `maintenance_fee`      | `BigInteger` → `BIGINT`                                | —               | no   | `0`            | Phí bảo trì khuôn khi dùng lại (VND).                                                                |
| `supplier`             | `String(255)` → `VARCHAR(255)`                         | —               | yes  | —              | Nhà cung cấp khuôn.                                                                                  |
| `lead_time_days`       | `Integer` → `INTEGER`                                  | —               | no   | `0`            | Lead time (ngày).                                                                                    |
| `transport_fee`        | `BigInteger` → `BIGINT`                                | —               | no   | `0`            | Phí vận chuyển (VND).                                                                                |
| `moq`                  | `Integer` → `INTEGER`                                  | —               | no   | `0`            | Số lượng đặt tối thiểu.                                                                              |
| `effective_from`       | `Date` → `DATE`                                        | —               | no   | —              | Rate effective start date.                                                                           |
| `effective_to`         | `Date` → `DATE`                                        | —               | yes  | —              | Rate effective end date. Null means current.                                                         |
| `is_active`            | `Boolean` → `BOOLEAN`                                  | —               | no   | `true`         | Active status flag.                                                                                  |
| `used_count`           | `Integer` → `INTEGER`                                  | —               | no   | `0`            | Số phiếu/công đoạn đã dùng.                                                                          |
| `created_by`           | `Integer` → `INTEGER`                                  | **FK→users.id** | yes  | —              | Người tạo; `ON DELETE SET NULL`.                                                                     |
| `updated_by`           | `Integer` → `INTEGER`                                  | **FK→users.id** | yes  | —              | Người sửa cuối; `ON DELETE SET NULL`.                                                                |
| `created_at`           | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —               | no   | now (UTC)      | Creation timestamp.                                                                                  |
| `updated_at`           | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —               | no   | now (UTC)      | Last updated timestamp.                                                                              |

**Keys & indexes**

- Primary key: `id`.
- Index: `ix_plate_die_rates_plate_type` on `plate_type`; `ix_plate_die_rates_code` on `code`.
- Unique index: `uix_plate_die_rates_current` on `(code) WHERE effective_to IS NULL`.
- Foreign keys: `created_by` / `updated_by` → `users.id` (`ON DELETE SET NULL`).
- Referenced by `operations.tooling_rate_id` (plain Integer, no FK).

---

### `norms`

**Purpose:** versioned loss and makeup norms, waste percentages, and setup wastes with specificity dimensions.

| Column                     | Type (SQLAlchemy → SQLite / Postgres)                  | Key                                               | Null | Default        | Meaning                                                                                               |
| -------------------------- | ------------------------------------------------------ | ------------------------------------------------- | ---- | -------------- | ----------------------------------------------------------------------------------------------------- |
| `id`                       | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                                            | no   | auto-increment | Surrogate primary key.                                                                                |
| `norm_key`                 | `String(32)` → `VARCHAR(32)`                           | **IX**                                            | no   | —              | Key identifying the norm (yield_rate, running_waste_pct, makeready_per_color_side).                   |
| `value`                    | `Numeric(10,4)` → `NUMERIC(10,4)`                      | —                                                 | no   | —              | Norm value (yield in (0, 1], waste rate >= 0, makeready sheet count).                                 |
| `product_type`             | `String(32)` → `VARCHAR(32)`                           | **FK→product_types_catalog.product_type**, **IX** | yes  | —              | Narrowing dimension for product type.                                                                 |
| `machine_id`               | `Integer` → `INTEGER`                                  | **FK→machines.id**, **IX**                        | yes  | —              | Narrowing dimension for machine.                                                                      |
| `operation_id`             | `Integer` → `INTEGER`                                  | **FK→operations.id**, **IX**                      | yes  | —              | Narrowing dimension for operation.                                                                    |
| `operation_key`            | `String(32)` → `VARCHAR(32)`                           | **IX**                                            | yes  | —              | Fallback string key for operation.                                                                    |
| `qty_min`                  | `Integer` → `INTEGER`                                  | —                                                 | yes  | —              | Lower bound of print quantity range (inclusive).                                                      |
| `qty_max`                  | `Integer` → `INTEGER`                                  | —                                                 | yes  | —              | Upper bound of print quantity range (inclusive).                                                      |
| `context`                  | `JSON` → `JSONB` / `JSON`                              | —                                                 | yes  | —              | Dynamic context parameters like colors, sides, etc.                                                   |
| `context_key`              | `String(160)` → `VARCHAR(160)`                         | —                                                 | no   | `"{}"`         | Canonical string representation of context for uniqueness constraint.                                 |
| `effective_from`           | `Date` → `DATE`                                        | —                                                 | no   | —              | Norm effective start date.                                                                            |
| `effective_to`             | `Date` → `DATE`                                        | —                                                 | yes  | —              | Norm effective end date. Null means current.                                                          |
| `note`                     | `String(500)` → `VARCHAR(500)`                         | —                                                 | yes  | —              | Optional developer or admin notes.                                                                    |
| `code`                     | `String(64)` → `VARCHAR(64)`                           | **IX**                                            | yes  | —              | Mã định mức tùy chọn — Tái thiết kế danh mục #7.                                                      |
| `name`                     | `String(200)` → `VARCHAR(200)`                         | —                                                 | yes  | —              | Tên định mức hiển thị.                                                                                |
| `waste_group`              | `String(24)` → `VARCHAR(24)`                           | **IX**                                            | yes  | —              | Nhóm định mức (YIELD_RATE/SETUP_WASTE/RUNNING_WASTE/PAPER_EXTRA_WASTE); NULL = rule đơn giá cũ (mực). |
| `calculation_method`       | `String(24)` → `VARCHAR(24)`                           | —                                                 | yes  | —              | Cách tính theo nhóm (PERCENT/FIXED/PER_COLOR/PER_SIDE/COMBINED/PER_COLOR_SIDE/PER_REAM).              |
| `applicable_product_types` | `JSON` → `JSONB` / `JSON`                              | —                                                 | yes  | —              | Phạm vi áp dụng theo loại sản phẩm (multi-select); NULL/[] = tất cả.                                  |
| `applicable_machine_ids`   | `JSON` → `JSONB` / `JSON`                              | —                                                 | yes  | —              | Phạm vi áp dụng theo máy (multi-select); NULL/[] = tất cả.                                            |
| `setup_waste_qty`          | `Numeric(12,3)` → `NUMERIC(12,3)`                      | —                                                 | yes  | —              | SETUP_WASTE: số tờ bù cố định (makeready).                                                            |
| `setup_waste_per_color`    | `Numeric(12,3)` → `NUMERIC(12,3)`                      | —                                                 | yes  | —              | SETUP_WASTE: số tờ bù cộng theo mỗi màu.                                                              |
| `setup_waste_per_side`     | `Numeric(12,3)` → `NUMERIC(12,3)`                      | —                                                 | yes  | —              | SETUP_WASTE: số tờ bù cộng theo mỗi mặt.                                                              |
| `min_waste_qty`            | `Numeric(12,3)` → `NUMERIC(12,3)`                      | —                                                 | yes  | —              | Clamp dưới (min) cho SETUP/RUNNING/PAPER.                                                             |
| `max_waste_qty`            | `Numeric(12,3)` → `NUMERIC(12,3)`                      | —                                                 | yes  | —              | Clamp trên (max) cho SETUP/RUNNING/PAPER.                                                             |
| `paper_add_to_purchase`    | `Boolean` → `BOOLEAN`                                  | —                                                 | no   | `true`         | PAPER_EXTRA_WASTE: có cộng vào số tờ mua giấy hay không.                                              |
| `priority`                 | `Integer` → `INTEGER`                                  | —                                                 | no   | `100`          | Độ ưu tiên chọn rule khi nhiều rule cùng khớp.                                                        |
| `version`                  | `Integer` → `INTEGER`                                  | —                                                 | no   | `1`            | Số phiên bản của bản ghi định mức.                                                                    |
| `used_count`               | `Integer` → `INTEGER`                                  | —                                                 | no   | `0`            | Số lần rule được sử dụng.                                                                             |
| `created_by`               | `Integer` → `INTEGER`                                  | **FK→users.id**                                   | yes  | —              | Người tạo bản ghi.                                                                                    |
| `updated_by`               | `Integer` → `INTEGER`                                  | **FK→users.id**                                   | yes  | —              | Người cập nhật gần nhất.                                                                              |
| `created_at`               | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                                 | no   | now (UTC)      | Creation timestamp.                                                                                   |
| `updated_at`               | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                                 | no   | now (UTC)      | Last updated timestamp.                                                                               |

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

**Purpose:** atomic counter sequences for generating auto-incrementing document codes (quotations, costings, orders, jobs, phiếu chi/thu).

| Column           | Type (SQLAlchemy → SQLite / Postgres) | Key    | Null | Default | Meaning                                         |
| ---------------- | ------------------------------------- | ------ | ---- | ------- | ----------------------------------------------- |
| `doc_type`       | `String(32)` → `VARCHAR(32)`          | **PK** | no   | —       | Document type (costing, quotation, order, job, payment_voucher, payment_receipt). |
| `year`           | `Integer` → `INTEGER`                 | **PK** | no   | —       | Năm của bộ đếm (vd 2026). **2000 = sentinel** cho bộ đếm KHÔNG reset theo năm (`SEQ_YEAR_GLOBAL` — số phiếu chi/thu in trên chứng từ pháp lý phải duy nhất vĩnh viễn); CHECK cấm year=0 nên dùng cận dưới 2000. |
| `current_number` | `Integer` → `INTEGER`                 | —      | no   | `0`     | Auto-incremented sequence number.               |

**Keys & indexes**

- Primary key: `(doc_type, year)`.
- CHECK: `year >= 2000 AND year <= 2100`, `current_number >= 0`.

---

### `employees`

**Purpose:** hồ sơ nhân sự (Hồ sơ nhân viên — module `nhan_su`, lát #1). One row per
employee. `code` NV### tự sinh (read-only); owned by a `department_id` (trục RBAC
data-scope own/department/all). `user_id` nối tài khoản login 1–1 tùy chọn (UNIQUE,
nullable) — công nhân xưởng không đăng nhập vẫn có hồ sơ. Đây là **provider sẵn** cho
SEAM-19 (`drivers.employee_id` back-fill khi Tài xế build). Portable across SQLite/Postgres.

| Column                    | Type (SQLAlchemy → SQLite / Postgres)                  | Key                            | Null | Default        | Meaning                                                                                                             |
| ------------------------- | ------------------------------------------------------ | ------------------------------ | ---- | -------------- | ------------------------------------------------------------------------------------------------------------------- |
| `id`                      | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                         | no   | auto-increment | Surrogate primary key.                                                                                              |
| `code`                    | `String(20)` → `VARCHAR(20)`                           | **U**, **IX**                  | no   | —              | Mã NV tự sinh (NV001, NV002…); read-only, theo pattern KH###/SP###/PB###.                                           |
| `full_name`               | `String(255)` → `VARCHAR(255)`                         | —                              | no   | —              | Họ tên (bắt buộc, non-blank).                                                                                       |
| `department_id`           | `Integer` → `INTEGER`                                  | **FK→departments.id**, **IX**  | yes  | —              | Phòng/tổ; trục RBAC data-scope. Null tới khi gán.                                                                   |
| `user_id`                 | `Integer` → `INTEGER`                                  | **FK→users.id**, **U**, **IX** | yes  | —              | Tài khoản login nối 1–1 (UNIQUE); null = chưa nối.                                                                  |
| `position`                | `String(255)` → `VARCHAR(255)`                         | —                              | yes  | —              | Chức danh.                                                                                                          |
| `job_grade`               | `String(50)` → `VARCHAR(50)`                           | —                              | yes  | —              | Bậc thợ (vd "3/7"); đầu vào lương khoán.                                                                            |
| `status`                  | `String(16)` → `VARCHAR(16)`                           | —                              | no   | `probation`    | probation/active/on_leave/suspended/resigned.                                                                       |
| `hire_date`               | `Date` → `DATE`                                        | —                              | yes  | —              | Ngày vào làm.                                                                                                       |
| `probation_end_date`      | `Date` → `DATE`                                        | —                              | yes  | —              | Ngày dự kiến hết thử việc (KPI "sắp hết thử việc").                                                                 |
| `resign_date`             | `Date` → `DATE`                                        | —                              | yes  | —              | Ngày nghỉ việc.                                                                                                     |
| `resign_reason`           | `String(255)` → `VARCHAR(255)`                         | —                              | yes  | —              | Lý do nghỉ (bắt buộc khi status=resigned).                                                                          |
| `date_of_birth`           | `Date` → `DATE`                                        | —                              | yes  | —              | Ngày sinh.                                                                                                          |
| `gender`                  | `String(8)` → `VARCHAR(8)`                             | —                              | yes  | —              | male/female/other.                                                                                                  |
| `national_id`             | `String(20)` → `VARCHAR(20)`                           | **IX**                         | yes  | —              | CCCD/CMND; indexed cho check-trùng mềm, KHÔNG unique.                                                               |
| `national_id_date`        | `Date` → `DATE`                                        | —                              | yes  | —              | Ngày cấp CCCD.                                                                                                      |
| `national_id_place`       | `String(255)` → `VARCHAR(255)`                         | —                              | yes  | —              | Nơi cấp CCCD.                                                                                                       |
| `phone`                   | `String(30)` → `VARCHAR(30)`                           | —                              | yes  | —              | Điện thoại.                                                                                                         |
| `email`                   | `String(255)` → `VARCHAR(255)`                         | —                              | yes  | —              | Email.                                                                                                              |
| `permanent_address`       | `String(500)` → `VARCHAR(500)`                         | —                              | yes  | —              | Hộ khẩu thường trú.                                                                                                 |
| `current_address`         | `String(500)` → `VARCHAR(500)`                         | —                              | yes  | —              | Chỗ ở hiện tại.                                                                                                     |
| `emergency_contact_name`  | `String(255)` → `VARCHAR(255)`                         | —                              | yes  | —              | Người liên hệ khẩn cấp.                                                                                             |
| `emergency_contact_phone` | `String(30)` → `VARCHAR(30)`                           | —                              | yes  | —              | SĐT liên hệ khẩn cấp.                                                                                               |
| `social_insurance_no`     | `String(20)` → `VARCHAR(20)`                           | **IX**                         | yes  | —              | Số sổ BHXH; indexed check-trùng mềm, KHÔNG unique.                                                                  |
| `pit_tax_code`            | `String(20)` → `VARCHAR(20)`                           | —                              | yes  | —              | MST cá nhân (TNCN).                                                                                                 |
| `dependents_count`        | `Integer` → `INTEGER`                                  | —                              | no   | `0`            | Số người phụ thuộc (giảm trừ gia cảnh).                                                                             |
| `bank_account`            | `String(30)` → `VARCHAR(30)`                           | —                              | yes  | —              | Số tài khoản ngân hàng (chi lương).                                                                                 |
| `bank_name`               | `String(100)` → `VARCHAR(100)`                         | —                              | yes  | —              | Ngân hàng.                                                                                                          |
| `default_shift_id`        | `Integer` → `INTEGER`                                  | **IX**                         | yes  | —              | Ca làm việc mặc định (logical link → `work_shifts.id`, không FK cứng). Null = chưa gán ca. Thêm qua migration 0011. |
| `payroll_group`           | `String(40)` → `VARCHAR(40)`                           | **IX**                         | yes  | —              | Nhóm lương — trục tra `salary_rate_rules` (vd `to_in`, `san_xuat`, `van_phong`). Thêm qua migration 0012.           |
| `pay_grade_key`           | `String(20)` → `VARCHAR(20)`                           | —                              | yes  | —              | Bậc lương chuẩn hóa cho tổ theo bậc (tho_1..phu_2). Tách khỏi `job_grade` free-text. Thêm qua migration 0012.       |
| `photo_url`               | `String(500)` → `VARCHAR(500)`                         | —                              | yes  | —              | Đường dẫn ảnh hồ sơ (mirror avatar), `/static/hr/<id>/…`. Null = initials.                                          |
| `note`                    | `String(1000)` → `VARCHAR(1000)`                       | —                              | yes  | —              | Ghi chú tự do.                                                                                                      |
| `created_at`              | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                              | no   | now (UTC)      | Khi tạo hồ sơ.                                                                                                      |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_employees_code` on `code`, `ix_employees_user_id` on `user_id` (UNIQUE — 1 account ↔ ≤1 NV).
- Indexes: `ix_employees_department_id` on `department_id` (scope filter), `ix_employees_national_id` on `national_id`, `ix_employees_social_insurance_no` on `social_insurance_no` (non-unique — soft dup).
- Foreign keys: `department_id FK→departments.id`, `user_id FK→users.id`.

**Relationships**

- Many employees belong to one `departments` (via `department_id`). At most one `users`
  account backs an employee (via UNIQUE `user_id`).
- One employee has many `employee_events` (Quá trình công tác) and many
  `employee_attachments`, both cascade-deleted with it.
- Provider của SEAM-19: `drivers.employee_id` sẽ FK vào `employees.id` khi Tài xế build.

---

### `employee_events`

**Purpose:** một mốc "Quá trình công tác" của nhân viên (module `nhan_su`). Service ghi 1
dòng mỗi khi đổi giai đoạn (status / department / job_grade) — timeline theo `effective_date`
(ngày hiệu lực, khác `created_at` = ngày nhập máy).

| Column           | Type (SQLAlchemy → SQLite / Postgres)                  | Key                         | Null | Default        | Meaning                                                                                   |
| ---------------- | ------------------------------------------------------ | --------------------------- | ---- | -------------- | ----------------------------------------------------------------------------------------- |
| `id`             | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                      | no   | auto-increment | Surrogate primary key.                                                                    |
| `employee_id`    | `Integer` → `INTEGER`                                  | **FK→employees.id**, **IX** | no   | —              | Nhân viên chủ; `ON DELETE CASCADE`.                                                       |
| `event_type`     | `String(24)` → `VARCHAR(24)`                           | —                           | no   | —              | hired/confirmed/transferred/promoted/leave_start/leave_end/suspended/resigned/reinstated. |
| `effective_date` | `Date` → `DATE`                                        | **IX**                      | yes  | —              | Ngày hiệu lực của giai đoạn.                                                              |
| `field`          | `String(40)` → `VARCHAR(40)`                           | —                           | yes  | —              | Trường thay đổi (vd "status", "department", "job_grade").                                 |
| `from_value`     | `String(255)` → `VARCHAR(255)`                         | —                           | yes  | —              | Giá trị trước.                                                                            |
| `to_value`       | `String(255)` → `VARCHAR(255)`                         | —                           | yes  | —              | Giá trị sau.                                                                              |
| `note`           | `String(500)` → `VARCHAR(500)`                         | —                           | yes  | —              | Lý do / ghi chú mốc.                                                                      |
| `actor_user_id`  | `Integer` → `INTEGER`                                  | **FK→users.id**             | yes  | —              | Người thao tác.                                                                           |
| `created_at`     | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                           | no   | now (UTC)      | Khi ghi máy.                                                                              |

**Keys & indexes**

- Primary key: `id`.
- Indexes: `ix_employee_events_employee_id` on `employee_id`, `ix_employee_events_effective_date` on `effective_date`.
- Foreign keys: `employee_id FK→employees.id` (`ON DELETE CASCADE`), `actor_user_id FK→users.id`.

**Relationships**

- Many events belong to one `employees` row; deleting the employee cascades to its events.

---

### `employee_attachments`

**Purpose:** file đính kèm hồ sơ nhân viên (HĐ scan / CCCD / bằng cấp) — module `nhan_su`.
Bytes lưu dưới `<backend>/static`, phục vụ read-only ở `/static`; chỉ path lưu ở đây
(mirror `quote_attachments` / `users.avatar_url`).

| Column        | Type (SQLAlchemy → SQLite / Postgres)                  | Key                         | Null | Default        | Meaning                                  |
| ------------- | ------------------------------------------------------ | --------------------------- | ---- | -------------- | ---------------------------------------- |
| `id`          | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                      | no   | auto-increment | Surrogate primary key.                   |
| `employee_id` | `Integer` → `INTEGER`                                  | **FK→employees.id**, **IX** | no   | —              | Nhân viên chủ; `ON DELETE CASCADE`.      |
| `doc_kind`    | `String(24)` → `VARCHAR(24)`                           | —                           | no   | `khac`         | hop_dong/cccd/bang_cap/khac.             |
| `file_name`   | `String(255)` → `VARCHAR(255)`                         | —                           | no   | —              | Tên file gốc.                            |
| `file_url`    | `String(500)` → `VARCHAR(500)`                         | —                           | no   | —              | Đường dẫn lưu trữ (`/static/hr/<id>/…`). |
| `file_type`   | `String(100)` → `VARCHAR(100)`                         | —                           | yes  | —              | MIME / loại file.                        |
| `uploaded_by` | `Integer` → `INTEGER`                                  | **FK→users.id**             | yes  | —              | Người upload.                            |
| `uploaded_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                           | no   | now (UTC)      | Upload lúc.                              |

**Keys & indexes**

- Primary key: `id`.
- Indexes: `ix_employee_attachments_employee_id` on `employee_id`.
- Foreign keys: `employee_id FK→employees.id` (`ON DELETE CASCADE`), `uploaded_by FK→users.id`.

**Relationships**

- Many attachments belong to one `employees` row; deleting the employee cascades to its files.

---

### `work_locations`

**Purpose:** điểm chấm công (geofence) — module `nhan_su`, lát Chấm công GPS. One row per
work site; HR khai nhiều điểm (xưởng/kho/VP). Nhân viên chấm công khi ở trong `radius_m`
mét quanh BẤT KỲ điểm `is_active` nào (kiểm khoảng cách Haversine ở server).

| Column       | Type (SQLAlchemy → SQLite / Postgres)                  | Key    | Null | Default        | Meaning                                           |
| ------------ | ------------------------------------------------------ | ------ | ---- | -------------- | ------------------------------------------------- |
| `id`         | `Integer` → `INTEGER` / `SERIAL`                       | **PK** | no   | auto-increment | Surrogate primary key.                            |
| `name`       | `String(255)` → `VARCHAR(255)`                         | —      | no   | —              | Tên điểm (vd "Xưởng in chính").                   |
| `latitude`   | `Numeric(10,7)` → `NUMERIC(10,7)`                      | —      | no   | —              | Vĩ độ WGS-84 (độ thập phân).                      |
| `longitude`  | `Numeric(10,7)` → `NUMERIC(10,7)`                      | —      | no   | —              | Kinh độ WGS-84 (độ thập phân).                    |
| `radius_m`   | `Integer` → `INTEGER`                                  | —      | no   | `100`          | Bán kính cho phép chấm công (mét).                |
| `is_active`  | `Boolean` → `BOOLEAN`                                  | —      | no   | `true`         | Điểm đang dùng; chỉ điểm active mới xét khi chấm. |
| `note`       | `String(500)` → `VARCHAR(500)`                         | —      | yes  | —              | Ghi chú (địa chỉ…).                               |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —      | no   | now (UTC)      | Khi tạo.                                          |

**Keys & indexes**

- Primary key: `id`.

**Relationships**

- One work location is referenced by many `attendance_logs` (via `work_location_id`, ON DELETE SET NULL).

---

### `attendance_logs`

**Purpose:** bản ghi chấm công của một nhân viên (module `nhan_su`). Mỗi lần chấm VÀO/RA =
1 dòng; toạ độ + khoảng cách lưu để đối soát. Người chấm = user đăng nhập → NV qua
`employees.user_id`. Ngoài phạm vi bị chặn cứng (không tạo dòng).

| Column               | Type (SQLAlchemy → SQLite / Postgres)                  | Key                              | Null | Default        | Meaning                                                                                                                 |
| -------------------- | ------------------------------------------------------ | -------------------------------- | ---- | -------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `id`                 | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                           | no   | auto-increment | Surrogate primary key.                                                                                                  |
| `employee_id`        | `Integer` → `INTEGER`                                  | **FK→employees.id**, **IX**      | no   | —              | Nhân viên chấm; `ON DELETE CASCADE`.                                                                                    |
| `work_location_id`   | `Integer` → `INTEGER`                                  | **FK→work_locations.id**, **IX** | yes  | —              | Điểm khớp gần nhất lúc chấm; `ON DELETE SET NULL`.                                                                      |
| `check_type`         | `String(8)` → `VARCHAR(8)`                             | —                                | no   | —              | `in` (vào) / `out` (ra).                                                                                                |
| `checked_at`         | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | **IX**                           | no   | now (UTC)      | Thời điểm chấm.                                                                                                         |
| `latitude`           | `Numeric(10,7)` → `NUMERIC(10,7)`                      | —                                | yes  | —              | Vĩ độ trình duyệt gửi lúc chấm.                                                                                         |
| `longitude`          | `Numeric(10,7)` → `NUMERIC(10,7)`                      | —                                | yes  | —              | Kinh độ lúc chấm.                                                                                                       |
| `distance_m`         | `Numeric(10,2)` → `NUMERIC(10,2)`                      | —                                | yes  | —              | Khoảng cách (mét) tới điểm khớp.                                                                                        |
| `within_range`       | `Boolean` → `BOOLEAN`                                  | —                                | no   | `true`         | Trong bán kính hay không (chặn cứng ⇒ luôn true khi ghi).                                                               |
| `note`               | `String(500)` → `VARCHAR(500)`                         | —                                | yes  | —              | Ghi chú.                                                                                                                |
| `is_manual`          | `Boolean` → `BOOLEAN`                                  | —                                | no   | `false`        | Punch ĐIỀU CHỈNH TAY (HCNS chấm bù/sửa qua quyền `nhan_su.adjust`); công tự tính lại từ punch. Thêm qua migration 0016. |
| `adjust_reason`      | `String(500)` → `VARCHAR(500)`                         | —                                | yes  | —              | Lý do điều chỉnh (bắt buộc khi `is_manual`). Migration 0016.                                                            |
| `fault_party`        | `String(20)` → `VARCHAR(20)`                           | —                                | yes  | —              | Nguyên nhân chấm bù: `nv_quen`/`may_hong`/`duyet`/`khac`. Migration 0016.                                               |
| `created_by_user_id` | `Integer` → `INTEGER`                                  | —                                | yes  | —              | User (HCNS) thực hiện điều chỉnh. Migration 0016.                                                                       |
| `created_at`         | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                | no   | now (UTC)      | Khi ghi máy.                                                                                                            |

**Keys & indexes**

- Primary key: `id`.
- Indexes: `ix_attendance_logs_employee_id`, `ix_attendance_logs_work_location_id`, `ix_attendance_logs_checked_at`.
- Foreign keys: `employee_id FK→employees.id` (CASCADE), `work_location_id FK→work_locations.id` (SET NULL).

**Relationships**

- Many logs belong to one `employees` (cascade delete) and reference one `work_locations`.

---

### `attendance_adjust_requests`

Yêu cầu chỉnh công: NV tự gửi (giải trình 1 ngày công) → HCNS duyệt/từ chối. Duyệt ⇒ sinh 1 punch điều chỉnh tay (`attendance_logs.is_manual`) → công tự tính lại. Bảng mới do `create_all` tạo (không migration).

| Column               | Type (Py → SQL)                                        | Key                     | Null | Default   | Notes                                           |
| -------------------- | ------------------------------------------------------ | ----------------------- | ---- | --------- | ----------------------------------------------- |
| `id`                 | `Integer` → `INTEGER`                                  | **PK**                  | no   | auto      | Khóa chính.                                     |
| `employee_id`        | `Integer` → `INTEGER`                                  | **FK→employees.id, IX** | no   | —         | NV gửi yêu cầu (ON DELETE CASCADE).             |
| `work_date`          | `Date` → `DATE`                                        | —                       | no   | —         | Ngày công cần chỉnh (giờ VN).                   |
| `check_type`         | `String(8)` → `VARCHAR(8)`                             | —                       | no   | —         | Punch NV đề nghị bù: `in`/`out`.                |
| `suggested_time`     | `String(5)` → `VARCHAR(5)`                             | —                       | yes  | —         | Giờ gợi ý "HH:MM".                              |
| `reason`             | `String(500)` → `VARCHAR(500)`                         | —                       | no   | —         | NV giải trình.                                  |
| `fault_party`        | `String(20)` → `VARCHAR(20)`                           | —                       | yes  | —         | `nv_quen`/`may_hong`/`duyet`/`khac`.            |
| `status`             | `String(16)` → `VARCHAR(16)`                           | **IX**                  | no   | `pending` | pending/approved/rejected/cancelled.            |
| `decided_by`         | `Integer` → `INTEGER`                                  | —                       | yes  | —         | HCNS duyệt/từ chối (user id).                   |
| `decided_at`         | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                       | yes  | —         | Thời điểm quyết.                                |
| `decision_note`      | `String(500)` → `VARCHAR(500)`                         | —                       | yes  | —         | Ghi chú / lý do từ chối.                        |
| `resulting_log_id`   | `Integer` → `INTEGER`                                  | —                       | yes  | —         | Punch sinh ra khi duyệt (`attendance_logs.id`). |
| `created_by_user_id` | `Integer` → `INTEGER`                                  | —                       | yes  | —         | User tạo yêu cầu.                               |
| `created_at`         | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                       | no   | now (UTC) | Khi gửi.                                        |

**Keys & indexes**

- Primary key: `id`.
- Indexes: `ix_attendance_adjust_requests_employee_id`, `ix_attendance_adjust_requests_status`.
- Foreign keys: `employee_id FK→employees.id` (CASCADE).

**Relationships**

- Many requests belong to one `employees` (cascade delete). Approval writes a manual `attendance_logs` row.

---

### `attendance_periods`

**Purpose:** kỳ CÔNG tháng — Chốt công (Pha 2, module `nhan_su`). 1 dòng/(year,month): `draft → locked`
= đóng băng Bảng công để Lương đọc bản đã khóa (Đ3). Mirror `payroll_periods`.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `year` | `Integer` → `INTEGER` | **IX** | no | — | Năm kỳ công. |
| `month` | `Integer` → `INTEGER` | **IX** | no | — | Tháng kỳ công (1–12). |
| `status` | `String(12)` → `VARCHAR(12)` | **IX** | no | `draft` | `draft` (đang mở) / `locked` (đã chốt). |
| `locked_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Thời điểm chốt. |
| `locked_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Người chốt. |
| `created_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Người tạo kỳ. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Cập nhật cuối. |

**Keys & indexes**

- Primary key: `id`.
- Unique: `(year, month)` (`uq_attendance_period_ym`).

---

### `attendance_period_lines`

**Purpose:** snapshot CÔNG của 1 NV trong 1 kỳ, đóng băng lúc Chốt (Pha 2). Lương đọc `total_cong`
từ đây khi kỳ đã `locked`. Xóa + ghi lại mỗi lần Chốt / Mở lại.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `period_id` | `Integer` → `INTEGER` | **FK→attendance_periods.id**, **IX** | no | — | Kỳ công; `ON DELETE CASCADE`. |
| `employee_id` | `Integer` → `INTEGER` | **FK→employees.id**, **IX** | no | — | NV; `ON DELETE CASCADE`. |
| `total_cong` | `Numeric(6,2)` → `NUMERIC` | — | no | `0` | Số công thực (đã gồm công lễ + nghỉ phép có lương). |
| `total_days` | `Integer` → `INTEGER` | — | no | `0` | Số ngày có chấm công. |
| `total_leave` | `Integer` → `INTEGER` | — | no | `0` | Tổng ngày nghỉ phép đã duyệt. |
| `paid_leave_days` | `Integer` → `INTEGER` | — | no | `0` | Nghỉ phép CÓ lương. |
| `unpaid_leave_days` | `Integer` → `INTEGER` | — | no | `0` | Nghỉ KHÔNG lương. |
| `holiday_days` | `Integer` → `INTEGER` | — | no | `0` | Ngày nghỉ lễ hưởng công. |
| `total_hours` | `Numeric(7,2)` → `NUMERIC` | — | no | `0` | Tổng giờ có mặt. |
| `ot_minutes` | `Integer` → `INTEGER` | — | no | `0` | Tổng phút vượt ca (chờ duyệt OT — Pha 4). |
| `night_days` | `Integer` → `INTEGER` | — | no | `0` | Số ngày làm ca đêm. |
| `holiday_cong` | `Numeric(6,2)` → `NUMERIC` | — | no | `0` | Công LÀM ngày lễ (Đ98 → Lương trả premium). Thêm qua migration 0065. |
| `restday_cong` | `Numeric(6,2)` → `NUMERIC` | — | no | `0` | Công LÀM ngày nghỉ tuần (Đ98 → premium). Thêm qua migration 0065. |
| `ot_holiday_minutes` | `Integer` → `INTEGER` | — | no | `0` | Phút OT ngày lễ. Thêm qua migration 0065. |
| `ot_restday_minutes` | `Integer` → `INTEGER` | — | no | `0` | Phút OT ngày nghỉ tuần. Thêm qua migration 0065. |
| `note` | `String(500)` → `VARCHAR(500)` | — | yes | — | Ghi chú. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo. |

**Keys & indexes**

- Primary key: `id`.
- Unique: `(period_id, employee_id)` (`uq_attendance_period_line_pe`).
- Foreign keys: `period_id FK→attendance_periods.id` (CASCADE), `employee_id FK→employees.id` (CASCADE).

---

### `warehouses`

**Purpose:** cấu hình kho hàng (module `dm_kho`, admin master data). One row = một kho do admin
khai báo; về sau module "Kho hàng" vận hành (phiếu nhập/xuất) tham chiếu tới đây.

| Column        | Type (SQLAlchemy → SQLite / Postgres)                  | Key           | Null | Default        | Meaning                                                                    |
| ------------- | ------------------------------------------------------ | ------------- | ---- | -------------- | -------------------------------------------------------------------------- |
| `id`          | `Integer` → `INTEGER` / `SERIAL`                       | **PK**        | no   | auto-increment | Surrogate primary key.                                                     |
| `code`        | `String(20)` → `VARCHAR(20)`                           | **U**, **IX** | no   | —              | Mã kho hệ thống tự sinh `KHO` + số đệm 0 (`KHO001`, `KHO002`…). Read-only. |
| `name`        | `String(255)` → `VARCHAR(255)`                         | —             | no   | —              | Tên kho.                                                                   |
| `description` | `Text` → `TEXT`                                        | —             | yes  | —              | Mô tả kho (tùy chọn).                                                      |
| `notes`       | `Text` → `TEXT`                                        | —             | yes  | —              | Ghi chú (tùy chọn).                                                        |
| `is_active`   | `Boolean` → `BOOLEAN`                                  | —             | no   | `true`         | Kho còn dùng (`true`) hay đã ẩn.                                           |
| `created_at`  | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —             | no   | now (UTC)      | Khi tạo.                                                                   |
| `updated_at`  | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —             | no   | now (UTC)      | Cập nhật cuối.                                                             |

**Keys & indexes**

- Primary key: `id`. Unique index on `code`.

---

### `warehouse_items`

**Purpose:** module "Kho hàng" vận hành (nhân viên nhập). One row = một mặt hàng cơ bản nhập vào
MỘT kho đã cấu hình (`warehouses`). MVP — về sau mở rộng thành phiếu nhập/xuất đầy đủ.

| Column               | Type (SQLAlchemy → SQLite / Postgres)                  | Key                          | Null | Default        | Meaning                                                |
| -------------------- | ------------------------------------------------------ | ---------------------------- | ---- | -------------- | ------------------------------------------------------ |
| `id`                 | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                       | no   | auto-increment | Surrogate primary key.                                 |
| `warehouse_id`       | `Integer` → `INTEGER`                                  | **FK→warehouses.id**, **IX** | no   | —              | Kho chứa (admin đã cấu hình). Cascade-delete theo kho. |
| `name`               | `String(255)` → `VARCHAR(255)`                         | —                            | no   | —              | Tên mặt hàng.                                          |
| `quantity`           | `Numeric(14,2)` → `NUMERIC(14,2)`                      | —                            | no   | `0`            | Số lượng tồn (CHECK ≥ 0).                              |
| `unit`               | `String(32)` → `VARCHAR(32)`                           | —                            | no   | `"cái"`        | Đơn vị tính.                                           |
| `notes`              | `Text` → `TEXT`                                        | —                            | yes  | —              | Ghi chú (tùy chọn).                                    |
| `created_by_user_id` | `Integer` → `INTEGER`                                  | **FK→users.id**, **IX**      | yes  | —              | Người nhập; null để không mất bản ghi khi user bị xóa. |
| `created_at`         | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                            | no   | now (UTC)      | Khi tạo.                                               |
| `updated_at`         | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                            | no   | now (UTC)      | Cập nhật cuối.                                         |

**Keys & indexes**

- Primary key: `id`. Indexes on `warehouse_id`, `created_by_user_id`.
- Foreign keys: `warehouse_id FK→warehouses.id` (cascade), `created_by_user_id FK→users.id`.

---

### `stock_lots`

**Purpose:** Kho P0 — lô tồn của MỘT vật tư (`Material`) trong một kho. `Material` là item master (không tạo master trùng). Số lượng còn lại tính động từ `stock_moves`. Back-fill SEAM-06 (giấy khách theo đơn).

| Column              | Type           | Key                          | Null | Default     | Meaning                                     |
| ------------------- | -------------- | ---------------------------- | ---- | ----------- | ------------------------------------------- |
| `id`                | `Integer`      | **PK**                       | no   | auto        | Surrogate PK.                               |
| `code`              | `String(30)`   | **U**, **IX**                | no   | —           | Mã lô tự sinh `LO######`.                   |
| `material_id`       | `Integer`      | **FK→materials.id**, **IX**  | no   | —           | Vật tư (item master).                       |
| `warehouse_id`      | `Integer`      | **FK→warehouses.id**, **IX** | no   | —           | Kho chứa.                                   |
| `location`          | `String(60)`   | —                            | yes  | —           | Vị trí (chuỗi; P0 chưa có danh mục vị trí). |
| `ownership`         | `String(16)`   | —                            | no   | `'company'` | company / customer (giấy khách gửi).        |
| `owner_customer_id` | `Integer`      | **FK→customers.id**          | yes  | —           | Khách sở hữu (giấy khách).                  |
| `order_id`          | `Integer`      | **IX**                       | yes  | —           | Đơn hàng gắn lô (SEAM-06).                  |
| `unit_cost`         | `BigInteger`   | —                            | yes  | —           | Giá vốn / đơn vị tồn (đồng).                |
| `supplier`          | `String(150)`  | —                            | yes  | —           | NCC lô nhập.                                |
| `received_date`     | `Date`         | —                            | yes  | —           | Ngày nhập.                                  |
| `expiry_date`       | `Date`         | —                            | yes  | —           | HSD / date bao bì.                          |
| `note`              | `Text`         | —                            | yes  | —           | Ghi chú.                                    |
| `is_active`         | `Boolean`      | —                            | no   | `true`      | Còn dùng.                                   |
| `created_at`        | `DateTime(tz)` | —                            | no   | now         | Khi tạo.                                    |
| `updated_at`        | `DateTime(tz)` | —                            | no   | now         | Cập nhật cuối.                              |

---

### `stock_min_levels`

**Purpose:** Kho — ngưỡng tồn tối thiểu theo (vật tư × kho). Tồn thực tế < `min_qty` → cảnh báo bổ sung (`/api/kho/reports/low-stock`). UNIQUE(material_id, warehouse_id).

| Column         | Type            | Key                                         | Null | Default | Meaning                            |
| -------------- | --------------- | ------------------------------------------- | ---- | ------- | ---------------------------------- |
| `id`           | `Integer`       | **PK**                                      | no   | auto    | Surrogate PK.                      |
| `material_id`  | `Integer`       | **FK→materials.id**, **IX**, **U(mat,wh)**  | no   | —       | Vật tư.                            |
| `warehouse_id` | `Integer`       | **FK→warehouses.id**, **IX**, **U(mat,wh)** | no   | —       | Kho.                               |
| `min_qty`      | `Numeric(18,3)` | —                                           | no   | `0`     | Ngưỡng tồn tối thiểu (đơn vị tồn). |
| `note`         | `String(120)`   | —                                           | yes  | —       | Ghi chú.                           |
| `updated_at`   | `DateTime(tz)`  | —                                           | no   | now     | Cập nhật cuối.                     |

---

### `stock_moves`

**Purpose:** Kho P0 — sổ cái tồn append-only. `qty_delta` CÓ DẤU; tồn = SUM(qty_delta) theo (material × warehouse × lot). Đơn vị lưu theo đơn vị tồn của vật tư (đã quy đổi).

| Column               | Type            | Key                              | Null | Default        | Meaning                                                              |
| -------------------- | --------------- | -------------------------------- | ---- | -------------- | -------------------------------------------------------------------- |
| `id`                 | `Integer`       | **PK**                           | no   | auto           | Surrogate PK.                                                        |
| `material_id`        | `Integer`       | **FK→materials.id**, **IX**      | no   | —              | Vật tư.                                                              |
| `warehouse_id`       | `Integer`       | **FK→warehouses.id**, **IX**     | no   | —              | Kho.                                                                 |
| `lot_id`             | `Integer`       | **FK→stock_lots.id**, **IX**     | yes  | —              | Lô.                                                                  |
| `qty_delta`          | `Numeric(18,3)` | —                                | no   | —              | CÓ DẤU: + tăng / − giảm tồn.                                         |
| `unit`               | `String(16)`    | —                                | no   | `''`           | Đơn vị tồn (snapshot).                                               |
| `unit_cost`          | `BigInteger`    | —                                | yes  | —              | §spec-13 E Giá vốn/đơn vị (đồng); giá trị = qty_delta × unit_cost.   |
| `move_type`          | `String(24)`    | —                                | no   | `'dieu_chinh'` | ton_dau_ky/nhap/xuat/dieu_chinh/dieu_chuyen_in/dieu_chuyen_out.      |
| `status_id`          | `Integer`       | **FK→wh_item_statuses.id**       | yes  | —              | §spec-13 Trạng thái hàng (quyết định tồn khả dụng); null = khả dụng. |
| `voucher_id`         | `Integer`       | **FK→stock_vouchers.id**, **IX** | yes  | —              | §spec-13 Phiếu nguồn; null = ghi trực tiếp.                          |
| `reason`             | `String(120)`   | —                                | yes  | —              | Lý do.                                                               |
| `note`               | `Text`          | —                                | yes  | —              | Diễn giải.                                                           |
| `ref_type`           | `String(24)`    | —                                | yes  | —              | Loại chứng từ nguồn (P1+).                                           |
| `ref_id`             | `Integer`       | —                                | yes  | —              | Id chứng từ nguồn.                                                   |
| `created_by_user_id` | `Integer`       | **FK→users.id**, **IX**          | yes  | —              | Người ghi.                                                           |
| `created_at`         | `DateTime(tz)`  | **IX**                           | no   | now            | Thời điểm.                                                           |

---

### `wh_item_statuses`

**Purpose:** Kho Document Engine (spec-13, DacTa 3.15) — trạng thái hàng. `count_available` quyết định tồn khả dụng. Bộ chuẩn seed `is_system`.

| Column            | Type           | Key           | Null | Default | Meaning                                      |
| ----------------- | -------------- | ------------- | ---- | ------- | -------------------------------------------- |
| `id`              | `Integer`      | **PK**        | no   | auto    | PK.                                          |
| `code`            | `String(24)`   | **U**, **IX** | no   | —       | AVAILABLE/RESERVED/QC_WAIT/DEFECT/CANCELLED. |
| `name`            | `String(120)`  | —             | no   | —       | Tên.                                         |
| `count_on_hand`   | `Boolean`      | —             | no   | `true`  | Cộng vào tồn thực tế.                        |
| `count_available` | `Boolean`      | —             | no   | `true`  | Cộng vào tồn khả dụng.                       |
| `allow_issue`     | `Boolean`      | —             | no   | `true`  | Được xuất.                                   |
| `display_order`   | `Integer`      | —             | no   | `100`   | Thứ tự.                                      |
| `is_system`       | `Boolean`      | —             | no   | `false` | Bộ chuẩn — chỉ ẩn không xóa.                 |
| `notes`           | `Text`         | —             | yes  | —       | Ghi chú.                                     |
| `is_active`       | `Boolean`      | —             | no   | `true`  | Còn dùng.                                    |
| `created_at`      | `DateTime(tz)` | —             | no   | now     | Khi tạo.                                     |
| `updated_at`      | `DateTime(tz)` | —             | no   | now     | Cập nhật cuối.                               |

---

### `wh_voucher_types`

**Purpose:** Kho Document Engine (spec-13, DacTa 3.16) — loại phiếu, khai HÀNH VI (chiều tồn, kho nguồn/đích, duyệt, MISA). Thêm nghiệp vụ = thêm loại phiếu.

| Column             | Type           | Key           | Null | Default  | Meaning                                         |
| ------------------ | -------------- | ------------- | ---- | -------- | ----------------------------------------------- |
| `id`               | `Integer`      | **PK**        | no   | auto     | PK.                                             |
| `code`             | `String(24)`   | **U**, **IX** | no   | —        | NK-NVL/XK-SX/DC-KHO… (cũng là prefix mã phiếu). |
| `name`             | `String(120)`  | —             | no   | —        | Tên.                                            |
| `voucher_group`    | `String(24)`   | —             | no   | `'nhap'` | nhap/xuat/dieu_chuyen/kiem_ke/dieu_chinh.       |
| `stock_effect`     | `String(24)`   | —             | no   | `'tang'` | tang/giam/chuyen_vi_tri/khong_tac_dong.         |
| `require_src_wh`   | `Boolean`      | —             | no   | `false`  | Bắt buộc kho nguồn.                             |
| `require_dst_wh`   | `Boolean`      | —             | no   | `false`  | Bắt buộc kho đích.                              |
| `require_approval` | `Boolean`      | —             | no   | `false`  | Cần duyệt trước khi ghi sổ.                     |
| `sync_misa`        | `Boolean`      | —             | no   | `false`  | Cờ đồng bộ MISA (chưa hiện thực).               |
| `notes`            | `Text`         | —             | yes  | —        | Ghi chú.                                        |
| `is_active`        | `Boolean`      | —             | no   | `true`   | Còn dùng.                                       |
| `created_at`       | `DateTime(tz)` | —             | no   | now      | Khi tạo.                                        |
| `updated_at`       | `DateTime(tz)` | —             | no   | now      | Cập nhật cuối.                                  |

---

### `stock_vouchers`

**Purpose:** Kho Document Engine (spec-13, DacTa Table 2) — Header phiếu. Ghi `stock_moves` khi GHI SỔ. Mã tự sinh `{loại}-{YY}-{NNNN}`.

| Column                | Type           | Key                                | Null | Default   | Meaning                         |
| --------------------- | -------------- | ---------------------------------- | ---- | --------- | ------------------------------- |
| `id`                  | `Integer`      | **PK**                             | no   | auto      | PK.                             |
| `code`                | `String(30)`   | **U**, **IX**                      | no   | —         | Mã phiếu (NK-NVL-25-0001).      |
| `voucher_type_id`     | `Integer`      | **FK→wh_voucher_types.id**, **IX** | no   | —         | Loại phiếu (hành vi).           |
| `doc_date`            | `Date`         | —                                  | yes  | —         | Ngày chứng từ.                  |
| `partner_kind`        | `String(16)`   | —                                  | yes  | —         | ncc/khach/bo_phan/may.          |
| `partner_ref`         | `String(150)`  | —                                  | yes  | —         | Đối tượng (text, P1).           |
| `src_warehouse_id`    | `Integer`      | **FK→warehouses.id**, **IX**       | yes  | —         | Kho nguồn.                      |
| `dst_warehouse_id`    | `Integer`      | **FK→warehouses.id**               | yes  | —         | Kho đích.                       |
| `ref_type`            | `String(24)`   | —                                  | yes  | —         | lsx/order/po.                   |
| `ref_id`              | `Integer`      | —                                  | yes  | —         | Id chứng từ nguồn.              |
| `reason`              | `String(200)`  | —                                  | yes  | —         | Lý do/diễn giải.                |
| `note`                | `Text`         | —                                  | yes  | —         | Ghi chú.                        |
| `status`              | `String(16)`   | **IX**                             | no   | `'draft'` | draft/pending/posted/cancelled. |
| `created_by_user_id`  | `Integer`      | **FK→users.id**                    | yes  | —         | Người tạo.                      |
| `approved_by_user_id` | `Integer`      | **FK→users.id**                    | yes  | —         | Người duyệt/ghi sổ.             |
| `approved_at`         | `DateTime(tz)` | —                                  | yes  | —         | Thời điểm ghi sổ.               |
| `misa_ref`            | `String(40)`   | —                                  | yes  | —         | Mã đối chiếu MISA (P1).         |
| `created_at`          | `DateTime(tz)` | —                                  | no   | now       | Khi tạo.                        |
| `updated_at`          | `DateTime(tz)` | —                                  | no   | now       | Cập nhật cuối.                  |

---

### `stock_voucher_lines`

**Purpose:** Kho Document Engine (spec-13, DacTa Table 3) — dòng phiếu. `quantity` theo `uom` (quy đổi về đơn vị tồn khi ghi sổ).

| Column          | Type            | Key                                        | Null | Default | Meaning                    |
| --------------- | --------------- | ------------------------------------------ | ---- | ------- | -------------------------- |
| `id`            | `Integer`       | **PK**                                     | no   | auto    | PK.                        |
| `voucher_id`    | `Integer`       | **FK→stock_vouchers.id** (cascade), **IX** | no   | —       | Phiếu cha.                 |
| `material_id`   | `Integer`       | **FK→materials.id**                        | no   | —       | Vật tư (item master).      |
| `quantity`      | `Numeric(18,3)` | —                                          | no   | —       | Số lượng (dương).          |
| `uom`           | `String(16)`    | —                                          | yes  | —       | Đơn vị nhập (ream/kg…).    |
| `lot_id`        | `Integer`       | **FK→stock_lots.id**                       | yes  | —       | Lô.                        |
| `location`      | `String(60)`    | —                                          | yes  | —       | Vị trí (nguồn).            |
| `dest_location` | `String(60)`    | —                                          | yes  | —       | Vị trí đích (điều chuyển). |
| `status_id`     | `Integer`       | **FK→wh_item_statuses.id**                 | yes  | —       | Trạng thái hàng.           |
| `unit_cost`     | `BigInteger`    | —                                          | yes  | —       | Giá vốn/đơn vị (P1).       |
| `note`          | `Text`          | —                                          | yes  | —       | Ghi chú dòng.              |

---

### `stock_counts`

**Purpose:** Kho — đợt kiểm kê (spec-13 C, DacTa ch.8). Chốt tồn hệ thống → nhập thực đếm → duyệt sinh `stock_moves` điều chỉnh (move_type `kiem_ke`).

| Column               | Type           | Key                          | Null | Default  | Meaning                                      |
| -------------------- | -------------- | ---------------------------- | ---- | -------- | -------------------------------------------- |
| `id`                 | `Integer`      | **PK**                       | no   | auto     | PK.                                          |
| `code`               | `String(24)`   | **U**, **IX**                | no   | —        | Mã đợt `KK-YY-NNNN`.                         |
| `warehouse_id`       | `Integer`      | **FK→warehouses.id**, **IX** | no   | —        | Kho kiểm kê.                                 |
| `status`             | `String(16)`   | **IX**                       | no   | `'open'` | open/posted/cancelled.                       |
| `participants`       | `Text`         | —                            | yes  | —        | Thành viên tham gia đợt kiểm kê (JSON/text). |
| `note`               | `Text`         | —                            | yes  | —        | Ghi chú.                                     |
| `created_by_user_id` | `Integer`      | **FK→users.id**              | yes  | —        | Người tạo.                                   |
| `posted_by_user_id`  | `Integer`      | **FK→users.id**              | yes  | —        | Người duyệt.                                 |
| `posted_at`          | `DateTime(tz)` | —                            | yes  | —        | Thời điểm duyệt.                             |
| `created_at`         | `DateTime(tz)` | —                            | no   | now      | Khi tạo.                                     |
| `updated_at`         | `DateTime(tz)` | —                            | no   | now      | Cập nhật cuối.                               |

---

### `stock_count_lines`

**Purpose:** Kho — dòng kiểm kê (spec-13 C). `system_qty` = tồn hệ thống lúc chốt; `counted_qty` = thực đếm; chênh lệch = counted − system.

| Column          | Type            | Key                                      | Null | Default | Meaning                            |
| --------------- | --------------- | ---------------------------------------- | ---- | ------- | ---------------------------------- |
| `id`            | `Integer`       | **PK**                                   | no   | auto    | PK.                                |
| `count_id`      | `Integer`       | **FK→stock_counts.id** (cascade), **IX** | no   | —       | Đợt cha.                           |
| `material_id`   | `Integer`       | **FK→materials.id**                      | no   | —       | Vật tư.                            |
| `lot_id`        | `Integer`       | **FK→stock_lots.id**                     | yes  | —       | Lô.                                |
| `system_qty`    | `Numeric(18,3)` | —                                        | no   | `0`     | Tồn hệ thống (snapshot).           |
| `counted_qty`   | `Numeric(18,3)` | —                                        | yes  | —       | Thực đếm (null = chưa đếm).        |
| `defective_qty` | `Numeric(18,3)` | —                                        | yes  | —       | Số kém phẩm chất (phần A).         |
| `damaged_qty`   | `Numeric(18,3)` | —                                        | yes  | —       | Số mất phẩm chất/hư hỏng (phần A). |
| `unit`          | `String(16)`    | —                                        | yes  | —       | Đơn vị tồn.                        |
| `note`          | `Text`          | —                                        | yes  | —       | Ghi chú.                           |

### `suppliers`

**Purpose:** danh mục nhà cung cấp do bộ phận Thu mua quản lý. One row = một đối tác cung cấp
vật tư/dịch vụ, dùng để chọn vào phiếu yêu cầu mua hàng.

| Column           | Type (SQLAlchemy → SQLite / Postgres)                  | Key    | Null | Default        | Meaning                                              |
| ---------------- | ------------------------------------------------------ | ------ | ---- | -------------- | ---------------------------------------------------- |
| `id`             | `Integer` → `INTEGER` / `SERIAL`                       | **PK** | no   | auto-increment | Surrogate primary key.                               |
| `name`           | `String(255)` → `VARCHAR(255)`                         | **IX** | no   | —              | Tên nhà cung cấp.                                    |
| `tax_code`       | `String(20)` → `VARCHAR(20)`                           | **IX** | yes  | —              | Mã số thuế, nếu có.                                  |
| `phone`          | `String(30)` → `VARCHAR(30)`                           | —      | yes  | —              | Số điện thoại liên hệ.                               |
| `email`          | `String(255)` → `VARCHAR(255)`                         | —      | yes  | —              | Email liên hệ.                                       |
| `address`        | `String(500)` → `VARCHAR(500)`                         | —      | yes  | —              | Địa chỉ.                                             |
| `contact_name`   | `String(255)` → `VARCHAR(255)`                         | —      | yes  | —              | Người liên hệ chính.                                 |
| `supplier_group` | `String(32)` → `VARCHAR(32)`                           | **IX** | yes  | —              | Nhóm nhà cung cấp (giấy, mực, gia công, dịch vụ...). |
| `payment_terms`  | `String(255)` → `VARCHAR(255)`                         | —      | yes  | —              | Điều khoản thanh toán tham khảo.                     |
| `status`         | `String(16)` → `VARCHAR(16)`                           | —      | no   | `"active"`     | Trạng thái `active`/`inactive`.                      |
| `note`           | `Text` → `TEXT`                                        | —      | yes  | —              | Ghi chú.                                             |
| `created_at`     | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —      | no   | now (UTC)      | Khi tạo.                                             |
| `updated_at`     | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —      | no   | now (UTC)      | Cập nhật cuối.                                       |

**Keys & indexes**

- Primary key: `id`.
- Indexes on `name`, `tax_code`, `supplier_group`.

**Relationships**

- One supplier can be referenced by many `purchase_requests`.
- One supplier can own many `supplier_bank_accounts`.

---

### `department_purchase_requests`

**Purpose:** phiếu yêu cầu mua do các phòng ban phát sinh trước khi Thu mua lập phiếu mua. One row = một nhu cầu mua cần Thu mua xử lý.

| Column                     | Type (SQLAlchemy → SQLite / Postgres)                  | Key                           | Null | Default        | Meaning                                                                                          |
| -------------------------- | ------------------------------------------------------ | ----------------------------- | ---- | -------------- | ------------------------------------------------------------------------------------------------ |
| `id`                       | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                        | no   | auto-increment | Surrogate primary key.                                                                           |
| `code`                     | `String(32)` → `VARCHAR(32)`                           | **U**, **IX**                 | no   | generated      | Mã yêu cầu nguồn do backend sinh, vd `YCMH-260710-K8P2`.                                         |
| `status`                   | `String(24)` → `VARCHAR(24)`                           | **IX**                        | no   | `"open"`       | Trạng thái: `open`, `pending_approval`, `in_purchase`, `done`, `cancelled`.                      |
| `source_type`              | `String(32)` → `VARCHAR(32)`                           | **IX**                        | no   | —              | Bộ phận/nguồn phát sinh: `kinh_doanh`, `kho`, `san_xuat`, `cong_nghe`, `gia_cong_ngoai`, `khac`. |
| `requesting_department_id` | `Integer` → `INTEGER`                                  | **FK→departments.id**, **IX** | yes  | —              | Phòng ban phát sinh yêu cầu, lấy từ user tạo nếu có.                                             |
| `requested_by_user_id`     | `Integer` → `INTEGER`                                  | **FK→users.id**, **IX**       | yes  | —              | Người tạo yêu cầu mua.                                                                           |
| `related_document_type`    | `String(64)` → `VARCHAR(64)`                           | —                             | yes  | —              | Loại chứng từ liên quan, vd `sales_order`, `production_order`.                                   |
| `related_document_code`    | `String(64)` → `VARCHAR(64)`                           | **IX**                        | yes  | —              | Mã đơn/lệnh liên quan để truy vết nghiệp vụ.                                                     |
| `purpose`                  | `String(500)` → `VARCHAR(500)`                         | —                             | no   | —              | Mục đích yêu cầu mua.                                                                            |
| `needed_date`              | `Date` → `DATE`                                        | —                             | no   | —              | Ngày phòng ban cần hàng/vật tư/dịch vụ.                                                          |
| `note`                     | `Text` → `TEXT`                                        | —                             | yes  | —              | Ghi chú yêu cầu.                                                                                 |
| `created_at`               | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                             | no   | now (UTC)      | Khi tạo.                                                                                         |
| `updated_at`               | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                             | no   | now (UTC)      | Cập nhật cuối.                                                                                   |

**Keys & indexes**

- Primary key: `id`. Unique index on `code`.
- Indexes on `status`, `source_type`, `requesting_department_id`, `requested_by_user_id`, `related_document_code`.
- Foreign keys: `requesting_department_id FK→departments.id` (set null), `requested_by_user_id FK→users.id` (set null).

**Relationships**

- One department request has many `department_purchase_request_lines`.
- One department request can be linked to many `purchase_requests` through `purchase_request_sources`.

---

### `department_purchase_request_lines`

**Purpose:** dòng vật tư/dịch vụ mà phòng ban đang yêu cầu mua. One row = một vật tư trong yêu cầu nguồn.

| Column                  | Type (SQLAlchemy → SQLite / Postgres) | Key                                            | Null | Default        | Meaning                                                                                      |
| ----------------------- | ------------------------------------- | ---------------------------------------------- | ---- | -------------- | -------------------------------------------------------------------------------------------- |
| `id`                    | `Integer` → `INTEGER` / `SERIAL`      | **PK**                                         | no   | auto-increment | Surrogate primary key.                                                                       |
| `department_request_id` | `Integer` → `INTEGER`                 | **FK→department_purchase_requests.id**, **IX** | no   | —              | Phiếu yêu cầu nguồn cha.                                                                     |
| `item_name`             | `String(255)` → `VARCHAR(255)`        | —                                              | no   | —              | Tên vật tư/dịch vụ cần mua.                                                                  |
| `unit`                  | `String(32)` → `VARCHAR(32)`          | —                                              | no   | —              | Đơn vị tính.                                                                                 |
| `quantity`              | `Numeric(14,2)` → `NUMERIC(14,2)`     | —                                              | no   | `0`            | Số lượng cần mua.                                                                            |
| `expected_unit_price`   | `BigInteger` → `BIGINT`               | —                                              | no   | `0`            | Luôn bằng 0 ở yêu cầu phòng ban; phòng ban chỉ nhập số lượng, Thu mua mới nhập giá trên PMH. |
| `note`                  | `Text` → `TEXT`                       | —                                              | yes  | —              | Ghi chú dòng.                                                                                |

**Keys & indexes**

- Primary key: `id`.
- Index on `department_request_id`.
- Foreign key: `department_request_id FK→department_purchase_requests.id` (cascade).

**Relationships**

- Many lines belong to one `department_purchase_requests` row.

---

### `purchase_requests`

**Purpose:** phiếu yêu cầu mua hàng trong module Thu mua. One row = phần đầu phiếu; kế toán
duyệt trực tiếp trên phiếu này trước khi Thu mua mua hàng.

| Column                | Type (SQLAlchemy → SQLite / Postgres)                  | Key                         | Null | Default        | Meaning                                                                                                |
| --------------------- | ------------------------------------------------------ | --------------------------- | ---- | -------------- | ------------------------------------------------------------------------------------------------------ |
| `id`                  | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                      | no   | auto-increment | Surrogate primary key.                                                                                 |
| `code`                | `String(32)` → `VARCHAR(32)`                           | **U**, **IX**               | no   | generated      | Mã phiếu mua do backend sinh, vd `PMH-260710-K8P2`.                                                    |
| `status`              | `String(24)` → `VARCHAR(24)`                           | **IX**                      | no   | `"draft"`      | Trạng thái: `draft`, `pending_approval`, `approved`, `rejected`, `purchased`, `received`, `cancelled`. |
| `supplier_id`         | `Integer` → `INTEGER`                                  | **FK→suppliers.id**, **IX** | yes  | —              | Nhà cung cấp dự kiến; null nếu chưa chốt NCC.                                                          |
| `purpose`             | `String(500)` → `VARCHAR(500)`                         | —                           | yes  | —              | Mục đích mua.                                                                                          |
| `needed_date`         | `Date` → `DATE`                                        | —                           | yes  | —              | Ngày cần hàng.                                                                                         |
| `expected_receipt_date` | `Date` → `DATE`                                        | —                           | yes  | —              | Ngày dự kiến nhận hàng (NCC hẹn giao) — migration 0038.                                                |
| `created_by_user_id`  | `Integer` → `INTEGER`                                  | **FK→users.id**, **IX**     | yes  | —              | Người tạo phiếu.                                                                                       |
| `submitted_at`        | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                           | yes  | —              | Khi gửi duyệt.                                                                                         |
| `approved_by_user_id` | `Integer` → `INTEGER`                                  | **FK→users.id**, **IX**     | yes  | —              | Người duyệt/từ chối.                                                                                   |
| `approved_at`         | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                           | yes  | —              | Khi duyệt/từ chối.                                                                                     |
| `note`                | `Text` → `TEXT`                                        | —                           | yes  | —              | Ghi chú hoặc lý do từ chối/hủy.                                                                        |
| `created_at`          | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                           | no   | now (UTC)      | Khi tạo.                                                                                               |
| `updated_at`          | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                           | no   | now (UTC)      | Cập nhật cuối.                                                                                         |

**Keys & indexes**

- Primary key: `id`.
- Unique index on `code`.
- Indexes on `status`, `supplier_id`, `created_by_user_id`, `approved_by_user_id`.
- Foreign keys: `supplier_id FK→suppliers.id` (set null), `created_by_user_id FK→users.id` (set null), `approved_by_user_id FK→users.id` (set null).

**Relationships**

- One purchase request has many `purchase_request_lines`.
- One purchase request links back to one or many `department_purchase_requests` through `purchase_request_sources`.
- One purchase request optionally references one `suppliers` row.

---

### `purchase_request_lines`

**Purpose:** các dòng hàng/vật tư trong một phiếu yêu cầu mua hàng. One row = một mặt hàng
cần mua trong phiếu.

| Column                | Type (SQLAlchemy → SQLite / Postgres) | Key                                 | Null | Default        | Meaning                                            |
| --------------------- | ------------------------------------- | ----------------------------------- | ---- | -------------- | -------------------------------------------------- |
| `id`                  | `Integer` → `INTEGER` / `SERIAL`      | **PK**                              | no   | auto-increment | Surrogate primary key.                             |
| `purchase_request_id` | `Integer` → `INTEGER`                 | **FK→purchase_requests.id**, **IX** | no   | —              | Phiếu cha.                                         |
| `item_name`           | `String(255)` → `VARCHAR(255)`        | —                                   | no   | —              | Tên vật tư/dịch vụ cần mua.                        |
| `unit`                | `String(32)` → `VARCHAR(32)`          | —                                   | no   | `"cái"`        | Đơn vị tính.                                       |
| `quantity`            | `Numeric(14,2)` → `NUMERIC(14,2)`     | —                                   | no   | `0`            | Số lượng cần mua.                                  |
| `expected_unit_price` | `BigInteger` → `BIGINT`               | —                                   | no   | `0`            | Đơn giá dự kiến (VND).                             |
| `discount_percent`    | `Numeric(6,2)` → `NUMERIC(6,2)`       | —                                   | no   | `0`            | Giảm giá theo % trên tiền trước giảm của dòng mua. |
| `vat_percent`         | `Numeric(6,2)` → `NUMERIC(6,2)`       | —                                   | no   | `0`            | Thuế GTGT theo % trên tiền sau giảm giá.           |
| `note`                | `Text` → `TEXT`                       | —                                   | yes  | —              | Ghi chú dòng hàng.                                 |

**Keys & indexes**

- Primary key: `id`.
- Index on `purchase_request_id`.
- Foreign key: `purchase_request_id FK→purchase_requests.id` (cascade).

**Relationships**

- Many lines belong to one `purchase_requests` row. Tổng dự kiến được tính động từ `quantity × expected_unit_price`, trừ `discount_percent`, cộng `vat_percent`, không lưu dư trong header.

---

### `purchase_request_sources`

**Purpose:** bảng nối giữ truy vết từ phiếu mua của Thu mua về các yêu cầu mua gốc của phòng ban. One row = một yêu cầu nguồn được gom vào một phiếu mua.

| Column                  | Type (SQLAlchemy → SQLite / Postgres)                  | Key                                            | Null | Default        | Meaning                                                                   |
| ----------------------- | ------------------------------------------------------ | ---------------------------------------------- | ---- | -------------- | ------------------------------------------------------------------------- |
| `id`                    | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                                         | no   | auto-increment | Surrogate primary key.                                                    |
| `purchase_request_id`   | `Integer` → `INTEGER`                                  | **FK→purchase_requests.id**, **IX**            | no   | —              | Phiếu mua do Thu mua lập.                                                 |
| `department_request_id` | `Integer` → `INTEGER`                                  | **FK→department_purchase_requests.id**, **IX** | no   | —              | Yêu cầu mua gốc từ phòng ban.                                             |
| `source_code_snapshot`  | `String(32)` → `VARCHAR(32)`                           | —                                              | no   | —              | Mã yêu cầu nguồn chụp lại tại thời điểm gắn để hiển thị/truy vết ổn định. |
| `created_at`            | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                              | no   | now (UTC)      | Khi gắn nguồn vào phiếu mua.                                              |

**Keys & indexes**

- Primary key: `id`.
- Indexes on `purchase_request_id`, `department_request_id`.
- Foreign keys: `purchase_request_id FK→purchase_requests.id` (cascade), `department_request_id FK→department_purchase_requests.id` (restrict).

**Relationships**

- Many source links belong to one `purchase_requests` row.
- Many source links point to one `department_purchase_requests` row.

---

### `company_bank_accounts`

**Purpose:** danh mục tài khoản ngân hàng của công ty dùng làm tài khoản trích nợ khi lập UNC.

| Column           | Type (SQLAlchemy → SQLite / Postgres)                  | Key    | Null | Default        | Meaning                                  |
| ---------------- | ------------------------------------------------------ | ------ | ---- | -------------- | ---------------------------------------- |
| `id`             | `Integer` → `INTEGER` / `SERIAL`                       | **PK** | no   | auto-increment | Surrogate primary key.                   |
| `account_holder` | `String(255)` → `VARCHAR(255)`                         | —      | no   | —              | Tên chủ tài khoản.                       |
| `account_number` | `String(64)` → `VARCHAR(64)`                           | **IX** | no   | —              | Số tài khoản.                            |
| `bank_name`      | `String(255)` → `VARCHAR(255)`                         | **IX** | no   | —              | Tên ngân hàng.                           |
| `bank_branch`    | `String(255)` → `VARCHAR(255)`                         | —      | no   | —              | Chi nhánh ngân hàng.                     |
| `currency`       | `String(3)` → `VARCHAR(3)`                             | —      | no   | `"VND"`        | Loại tiền của tài khoản.                 |
| `is_default`     | `Boolean` → `BOOLEAN`                                  | —      | no   | `false`        | Tài khoản mặc định trong cùng danh mục.  |
| `is_active`      | `Boolean` → `BOOLEAN`                                  | **IX** | no   | `true`         | Tài khoản còn được phép chọn để lập UNC. |
| `note`           | `Text` → `TEXT`                                        | —      | yes  | —              | Ghi chú.                                 |
| `created_at`     | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —      | no   | now (UTC)      | Khi tạo.                                 |
| `updated_at`     | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —      | no   | now (UTC)      | Cập nhật cuối.                           |

**Keys & indexes**

- Primary key: `id`; unique constraint on (`bank_name`, `account_number`).
- Indexes on `account_number`, `bank_name`, `is_active`.

---

### `supplier_bank_accounts`

**Purpose:** tài khoản thụ hưởng của từng nhà cung cấp, do Kế toán hoặc Thu mua có quyền quản lý.

| Column           | Type (SQLAlchemy → SQLite / Postgres)                  | Key                         | Null | Default        | Meaning                                  |
| ---------------- | ------------------------------------------------------ | --------------------------- | ---- | -------------- | ---------------------------------------- |
| `id`             | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                      | no   | auto-increment | Surrogate primary key.                   |
| `supplier_id`    | `Integer` → `INTEGER`                                  | **FK→suppliers.id**, **IX** | no   | —              | Nhà cung cấp sở hữu tài khoản.           |
| `account_holder` | `String(255)` → `VARCHAR(255)`                         | —                           | no   | —              | Tên chủ tài khoản.                       |
| `account_number` | `String(64)` → `VARCHAR(64)`                           | **IX**                      | no   | —              | Số tài khoản.                            |
| `bank_name`      | `String(255)` → `VARCHAR(255)`                         | **IX**                      | no   | —              | Tên ngân hàng.                           |
| `bank_branch`    | `String(255)` → `VARCHAR(255)`                         | —                           | no   | —              | Chi nhánh ngân hàng.                     |
| `currency`       | `String(3)` → `VARCHAR(3)`                             | —                           | no   | `"VND"`        | Loại tiền của tài khoản.                 |
| `is_default`     | `Boolean` → `BOOLEAN`                                  | —                           | no   | `false`        | Tài khoản mặc định của nhà cung cấp.     |
| `is_active`      | `Boolean` → `BOOLEAN`                                  | **IX**                      | no   | `true`         | Tài khoản còn được phép chọn để lập UNC. |
| `note`           | `Text` → `TEXT`                                        | —                           | yes  | —              | Ghi chú.                                 |
| `created_at`     | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                           | no   | now (UTC)      | Khi tạo.                                 |
| `updated_at`     | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                           | no   | now (UTC)      | Cập nhật cuối.                           |

**Keys & indexes**

- Primary key: `id`; unique constraint on (`supplier_id`, `bank_name`, `account_number`).
- Foreign key: `supplier_id FK→suppliers.id` (cascade).
- Indexes on `supplier_id`, `account_number`, `bank_name`, `is_active`.

---

### `payment_vouchers`

**Purpose:** Phiếu chi/Ủy nhiệm chi do người có quyền `ke_toan.approve` lập từ PMH. Một PMH có
thể có nhiều chứng từ để hỗ trợ tạm ứng, thanh toán từng phần và thanh toán cuối.

| Column                                | Type (SQLAlchemy → SQLite / Postgres)                  | Key                                      | Null | Default             | Meaning                                                                        |
| ------------------------------------- | ------------------------------------------------------ | ---------------------------------------- | ---- | ------------------- | ------------------------------------------------------------------------------ |
| `id`                                  | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                                   | no   | auto-increment      | Surrogate primary key.                                                         |
| `code`                                | `String(32)` → `VARCHAR(32)`                           | **U**, **IX**                            | no   | generated           | Mã `PC-YYMMDD-XXXX` hoặc `UNC-YYMMDD-XXXX`.                                    |
| `doc_no`                              | `String(16)` → `VARCHAR(16)`                           | **U**, **IX**                            | yes  | generated           | Số IN trên mẫu 02-TT (`PC00445`) — thứ tự LẬP phiếu, chạy liên tục không reset theo năm; dùng chung bộ đếm cho tiền mặt lẫn UNC; phiếu hủy vẫn giữ số. Migration 0040. |
| `purchase_request_id`                 | `Integer` → `INTEGER`                                  | **FK→purchase_requests.id**, **IX**      | no   | —                   | PMH nguồn; không được xóa khi còn chứng từ.                                    |
| `supplier_id`                         | `Integer` → `INTEGER`                                  | **FK→suppliers.id**, **IX**              | yes  | —                   | Nhà cung cấp hiện tại; thông tin pháp lý còn được snapshot bên dưới.           |
| `voucher_type`                        | `String(24)` → `VARCHAR(24)`                           | **IX**                                   | no   | —                   | `cash` hoặc `bank_transfer`.                                                   |
| `payment_stage`                       | `String(16)` → `VARCHAR(16)`                           | —                                        | no   | —                   | `advance`, `partial`, `final`, `other`.                                        |
| `status`                              | `String(24)` → `VARCHAR(24)`                           | **IX**                                   | no   | `"waiting_payment"` | `waiting_payment`, `paid`, `cancelled`.                                        |
| `voucher_date`                        | `Date` → `DATE`                                        | —                                        | no   | —                   | Ngày chứng từ.                                                                 |
| `planned_payment_date`                | `Date` → `DATE`                                        | —                                        | yes  | —                   | Ngày dự kiến chi.                                                              |
| `amount`                              | `BigInteger` → `BIGINT`                                | —                                        | no   | —                   | Số tiền theo nguyên tệ.                                                        |
| `amount_vnd`                          | `BigInteger` → `BIGINT`                                | —                                        | no   | —                   | Số tiền quy đổi VND dùng giữ hạn mức và đối soát PMH; thêm qua migration 0022. |
| `currency`                            | `String(3)` → `VARCHAR(3)`                             | —                                        | no   | `"VND"`             | Mã loại tiền.                                                                  |
| `exchange_rate`                       | `Numeric(18,6)` → `NUMERIC(18,6)`                      | —                                        | no   | `1`                 | Tỷ giá sang VND; VND bắt buộc bằng 1.                                          |
| `content`                             | `String(500)` → `VARCHAR(500)`                         | —                                        | no   | —                   | Nội dung chi.                                                                  |
| `invoice_number`                      | `String(64)` → `VARCHAR(64)`                           | —                                        | yes  | —                   | Số hóa đơn tham chiếu.                                                         |
| `invoice_date`                        | `Date` → `DATE`                                        | —                                        | yes  | —                   | Ngày hóa đơn.                                                                  |
| `contract_number`                     | `String(64)` → `VARCHAR(64)`                           | —                                        | yes  | —                   | Số hợp đồng tham chiếu.                                                        |
| `company_bank_account_id`             | `Integer` → `INTEGER`                                  | **FK→company_bank_accounts.id**, **IX**  | yes  | —                   | Tài khoản trích nợ, bắt buộc với UNC.                                          |
| `supplier_bank_account_id`            | `Integer` → `INTEGER`                                  | **FK→supplier_bank_accounts.id**, **IX** | yes  | —                   | Tài khoản thụ hưởng, bắt buộc với UNC.                                         |
| `cash_recipient_name`                 | `String(255)` → `VARCHAR(255)`                         | —                                        | yes  | —                   | Người nhận tiền, bắt buộc với Phiếu chi.                                       |
| `cash_recipient_address`              | `String(500)` → `VARCHAR(500)`                         | —                                        | yes  | —                   | Địa chỉ người nhận tiền.                                                       |
| `cash_recipient_identity`             | `String(64)` → `VARCHAR(64)`                           | —                                        | yes  | —                   | CCCD/giấy tờ người nhận.                                                       |
| `bank_fee_bearer`                     | `String(16)` → `VARCHAR(16)`                           | —                                        | yes  | —                   | `payer`, `beneficiary`, `shared`.                                              |
| `bank_reference`                      | `String(64)` → `VARCHAR(64)`                           | —                                        | yes  | —                   | Mã giao dịch/số báo nợ, bắt buộc khi xác nhận UNC đã chi.                      |
| `debit_account`                       | `String(64)` → `VARCHAR(64)`                           | —                                        | yes  | —                   | Định khoản Nợ in trên mẫu (vd "242, 1331") — nhập tay. Migration 0040.         |
| `credit_account`                      | `String(64)` → `VARCHAR(64)`                           | —                                        | yes  | —                   | Định khoản Có in trên mẫu (vd "1111") — nhập tay. Migration 0040.              |
| `source_code_snapshot`                | `String(32)` → `VARCHAR(32)`                           | —                                        | no   | —                   | Mã PMH snapshot để truy vết ổn định.                                           |
| `supplier_name_snapshot`              | `String(255)` → `VARCHAR(255)`                         | —                                        | no   | —                   | Tên nhà cung cấp tại lúc lập.                                                  |
| `supplier_tax_code_snapshot`          | `String(20)` → `VARCHAR(20)`                           | —                                        | yes  | —                   | Mã số thuế snapshot.                                                           |
| `supplier_address_snapshot`           | `String(500)` → `VARCHAR(500)`                         | —                                        | yes  | —                   | Địa chỉ snapshot.                                                              |
| `company_account_holder_snapshot`     | `String(255)` → `VARCHAR(255)`                         | —                                        | yes  | —                   | Chủ tài khoản trích nợ snapshot.                                               |
| `company_account_number_snapshot`     | `String(64)` → `VARCHAR(64)`                           | —                                        | yes  | —                   | Số tài khoản trích nợ snapshot.                                                |
| `company_bank_name_snapshot`          | `String(255)` → `VARCHAR(255)`                         | —                                        | yes  | —                   | Ngân hàng trích nợ snapshot.                                                   |
| `company_bank_branch_snapshot`        | `String(255)` → `VARCHAR(255)`                         | —                                        | yes  | —                   | Chi nhánh trích nợ snapshot.                                                   |
| `beneficiary_account_holder_snapshot` | `String(255)` → `VARCHAR(255)`                         | —                                        | yes  | —                   | Chủ tài khoản thụ hưởng snapshot.                                              |
| `beneficiary_account_number_snapshot` | `String(64)` → `VARCHAR(64)`                           | —                                        | yes  | —                   | Số tài khoản thụ hưởng snapshot.                                               |
| `beneficiary_bank_name_snapshot`      | `String(255)` → `VARCHAR(255)`                         | —                                        | yes  | —                   | Ngân hàng thụ hưởng snapshot.                                                  |
| `beneficiary_bank_branch_snapshot`    | `String(255)` → `VARCHAR(255)`                         | —                                        | yes  | —                   | Chi nhánh thụ hưởng snapshot.                                                  |
| `created_by_user_id`                  | `Integer` → `INTEGER`                                  | **FK→users.id**, **IX**                  | yes  | —                   | Người lập chứng từ.                                                            |
| `paid_by_user_id`                     | `Integer` → `INTEGER`                                  | **FK→users.id**, **IX**                  | yes  | —                   | Người xác nhận đã chi.                                                         |
| `paid_at`                             | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                        | yes  | —                   | Khi xác nhận đã chi.                                                           |
| `cancelled_by_user_id`                | `Integer` → `INTEGER`                                  | **FK→users.id**, **IX**                  | yes  | —                   | Người hủy chứng từ.                                                            |
| `cancelled_at`                        | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                        | yes  | —                   | Khi hủy.                                                                       |
| `cancel_reason`                       | `Text` → `TEXT`                                        | —                                        | yes  | —                   | Lý do hủy.                                                                     |
| `note`                                | `Text` → `TEXT`                                        | —                                        | yes  | —                   | Ghi chú.                                                                       |
| `created_at`                          | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                        | no   | now (UTC)           | Khi tạo.                                                                       |
| `updated_at`                          | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                        | no   | now (UTC)           | Cập nhật cuối.                                                                 |

**Keys, indexes & rules**

- Primary key: `id`; unique index on `code`.
- Foreign keys to PMH, supplier, bank accounts and actor users as listed above.
- Tổng `amount_vnd` của chứng từ `waiting_payment` + `paid` không được vượt tổng PMH.
- PMH có chứng từ `waiting_payment` hoặc `paid` không được hủy; chứng từ đã `paid` không được sửa/hủy.
- Dòng vật tư được đọc từ `purchase_request_lines`, không tạo bảng dòng chứng từ thanh toán trùng lặp.
- Truy vết đầy đủ: `payment_vouchers → purchase_requests → purchase_request_sources → department_purchase_requests`.

**Relationships**

- Many payment vouchers belong to one `purchase_requests` row.
- UNC optionally references one company account and one supplier account while retaining snapshots.

---

### `payment_receipts`

**Purpose:** Phiếu thu (PT) gắn với một Phiếu chi/UNC **đã chi**: tiền chi ra tiêu không hết
quay VỀ công ty — người nộp (NCC hoặc nhân viên phụ trách mua, suy sẵn từ phiếu chi) nộp quỹ
tiền mặt hoặc chuyển về tài khoản công ty. One row = 1 phiếu thu; chỉ phiếu thu `received`
mới trừ vào số đã-chi-thực của PMH (mở lại hạn mức lập chứng từ).

| Column                            | Type (SQLAlchemy → SQLite / Postgres)                  | Key                                     | Null | Default             | Meaning                                                            |
| --------------------------------- | ------------------------------------------------------ | --------------------------------------- | ---- | ------------------- | ------------------------------------------------------------------ |
| `id`                              | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                                  | no   | auto-increment      | Surrogate primary key.                                             |
| `code`                            | `String(32)` → `VARCHAR(32)`                           | **U**, **IX**                           | no   | generated           | Mã `PT-YYMMDD-XXXX`.                                               |
| `doc_no`                          | `String(16)` → `VARCHAR(16)`                           | **U**, **IX**                           | yes  | generated           | Số IN trên mẫu 01-TT (`PT00027`) — thứ tự lập, chạy liên tục không reset theo năm. Migration 0040. |
| `source_type`                     | `String(20)` → `VARCHAR(20)`                           | **IX**                                  | no   | `"purchase_refund"` | Nguồn ∈ {purchase_refund (đường phiếu chi), order_deposit (cọc đơn bán)}. Migration 0070. |
| `payment_voucher_id`              | `Integer` → `INTEGER`                                  | **FK→payment_vouchers.id**, **IX**      | yes  | —                   | Phiếu chi gốc (RESTRICT). NULL cho phiếu thu cọc đơn bán. Nới NOT NULL mig 0070. |
| `purchase_request_id`             | `Integer` → `INTEGER`                                  | **FK→purchase_requests.id**, **IX**     | yes  | —                   | PMH nguồn (denormalize). NULL cho đơn bán. Nới NOT NULL mig 0070.  |
| `order_id`                        | `Integer` → `INTEGER`                                  | **FK→orders.id**, **IX**                | yes  | —                   | Đơn bán (RESTRICT) — cọc khách nộp. NULL cho đường phiếu chi. Migration 0070. |
| `order_no_snapshot`               | `String(32)` → `VARCHAR(32)`                           | —                                       | yes  | —                   | Mã đơn snapshot (đường đơn bán). Migration 0070.                   |
| `customer_name_snapshot`          | `String(255)` → `VARCHAR(255)`                         | —                                       | yes  | —                   | Tên khách snapshot (đường đơn bán). Migration 0070.                |
| `payer_name`                      | `String(255)` → `VARCHAR(255)`                         | —                                       | no   | —                   | Người nộp tiền (NCC/nhân viên) — default suy từ phiếu chi.         |
| `payer_address`                   | `String(500)` → `VARCHAR(500)`                         | —                                       | yes  | —                   | Địa chỉ người nộp — ô "Địa chỉ" bắt buộc của mẫu 01-TT. Migration 0040. |
| `receipt_method`                  | `String(24)` → `VARCHAR(24)`                           | —                                       | no   | —                   | `cash` (nhập quỹ) hoặc `bank_transfer` (về TK công ty).            |
| `status`                          | `String(24)` → `VARCHAR(24)`                           | **IX**                                  | no   | `"waiting_receipt"` | `waiting_receipt`, `received`, `cancelled`.                        |
| `receipt_date`                    | `Date` → `DATE`                                        | —                                       | no   | —                   | Ngày chứng từ thu.                                                 |
| `amount`                          | `BigInteger` → `BIGINT`                                | —                                       | no   | —                   | Số tiền thu theo nguyên tệ (cùng currency phiếu chi gốc).          |
| `amount_vnd`                      | `BigInteger` → `BIGINT`                                | —                                       | no   | —                   | Quy đổi VND — trục so hạn mức thu và rollup PMH.                   |
| `currency`                        | `String(3)` → `VARCHAR(3)`                             | —                                       | no   | `"VND"`             | Ép bằng currency phiếu chi gốc.                                    |
| `exchange_rate`                   | `Numeric(18,6)` → `NUMERIC(18,6)`                      | —                                       | no   | `1`                 | Tỷ giá sang VND (default = tỷ giá phiếu gốc).                      |
| `content`                         | `String(500)` → `VARCHAR(500)`                         | —                                       | no   | —                   | Nội dung thu.                                                      |
| `company_bank_account_id`         | `Integer` → `INTEGER`                                  | **FK→company_bank_accounts.id**, **IX** | yes  | —                   | TK công ty nhận tiền, bắt buộc khi bank_transfer.                  |
| `bank_reference`                  | `String(64)` → `VARCHAR(64)`                           | —                                       | yes  | —                   | Mã giao dịch/số báo có, bắt buộc khi xác nhận đã thu qua CK.       |
| `debit_account`                   | `String(64)` → `VARCHAR(64)`                           | —                                       | yes  | —                   | Định khoản Nợ in trên mẫu (vd "1111") — nhập tay. Migration 0040.  |
| `credit_account`                  | `String(64)` → `VARCHAR(64)`                           | —                                       | yes  | —                   | Định khoản Có in trên mẫu (vd "131") — nhập tay. Migration 0040.   |
| `voucher_code_snapshot`           | `String(32)` → `VARCHAR(32)`                           | —                                       | yes  | —                   | Mã PC/UNC gốc snapshot — truy vết bất biến. NULL nhánh đơn (V5, Migration 0070 nới nullable). |
| `purchase_code_snapshot`          | `String(32)` → `VARCHAR(32)`                           | —                                       | yes  | —                   | Mã PMH snapshot. NULL nhánh đơn (V5).                             |
| `supplier_name_snapshot`          | `String(255)` → `VARCHAR(255)`                         | —                                       | yes  | —                   | Tên NCC snapshot từ phiếu chi gốc. NULL nhánh đơn (V5).           |
| `customer_name_snapshot`          | `String(255)` → `VARCHAR(255)`                         | —                                       | yes  | —                   | Tên khách snapshot (V5, nhánh `don_hang_ban`) — hiện trên phiếu không join. Migration 0070. |
| `order_code_snapshot`             | `String(32)` → `VARCHAR(32)`                           | —                                       | yes  | —                   | Mã đơn (`order_no`) snapshot (V5, nhánh `don_hang_ban`). Migration 0070. |
| `company_account_holder_snapshot` | `String(255)` → `VARCHAR(255)`                         | —                                       | yes  | —                   | Chủ TK nhận snapshot.                                              |
| `company_account_number_snapshot` | `String(64)` → `VARCHAR(64)`                           | —                                       | yes  | —                   | Số TK nhận snapshot.                                               |
| `company_bank_name_snapshot`      | `String(255)` → `VARCHAR(255)`                         | —                                       | yes  | —                   | Ngân hàng nhận snapshot.                                           |
| `company_bank_branch_snapshot`    | `String(255)` → `VARCHAR(255)`                         | —                                       | yes  | —                   | Chi nhánh nhận snapshot.                                           |
| `created_by_user_id`              | `Integer` → `INTEGER`                                  | **FK→users.id**, **IX**                 | yes  | —                   | Người lập phiếu thu.                                               |
| `received_by_user_id`             | `Integer` → `INTEGER`                                  | **FK→users.id**, **IX**                 | yes  | —                   | Người xác nhận đã thu tiền.                                        |
| `received_at`                     | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                       | yes  | —                   | Khi xác nhận đã thu.                                               |
| `cancelled_by_user_id`            | `Integer` → `INTEGER`                                  | **FK→users.id**, **IX**                 | yes  | —                   | Người hủy phiếu thu.                                               |
| `cancelled_at`                    | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                       | yes  | —                   | Khi hủy.                                                           |
| `cancel_reason`                   | `Text` → `TEXT`                                        | —                                       | yes  | —                   | Lý do hủy.                                                         |
| `note`                            | `Text` → `TEXT`                                        | —                                       | yes  | —                   | Ghi chú.                                                           |
| `created_at`                      | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                       | no   | now (UTC)           | Khi tạo.                                                           |
| `updated_at`                      | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                       | no   | now (UTC)           | Cập nhật cuối.                                                     |

**Keys, indexes & rules**

- Primary key: `id`; unique index on `code`. Indexes: `source_type`, `order_id` (V5).
- **Đa nguồn (V5):** `source_type='phieu_chi'` → nhánh hoàn ứng NCC/NV (bắt buộc `payment_voucher_id`
  + `purchase_request_id`; hành vi cũ nguyên vẹn). `source_type='don_hang_ban'` → thu cọc khách gắn
  `order_id`; tạo THẲNG `received` (Kế toán bấm = đã thu), không qua phiếu chi.
- Nhánh Phiếu chi: chỉ lập trên phiếu chi `paid`; tổng `amount_vnd` phiếu thu `waiting_receipt` +
  `received` không vượt `amount_vnd` phiếu chi gốc. Chỉ `waiting_receipt` mới sửa/hủy; `received` bất
  biến. Rollup PMH: `receipt_received_amount` = SUM phiếu thu `received`.
- Nhánh Đơn hàng bán: cổng "đủ cọc" của đơn = Σ `amount` phiếu thu (`order_id`, `received`) ≥
  `deposit_required`.

**Relationships**

- Nhánh Phiếu chi: many payment receipts belong to one `payment_vouchers` row (và một
  `purchase_requests` row). Nhánh Đơn hàng bán: many receipts belong to one `orders` row.
- Bank transfer references one `company_bank_accounts` row while retaining snapshots.

---

### `work_shifts`

**Purpose:** ca làm việc (module `nhan_su`, lát Ca kíp). One row per ca (Hành chính, Ca
1/2/3…). Giờ vào/ra lưu bằng **phút-từ-nửa-đêm** (0..1439) cho dễ tính công; API phơi "HH:MM".
Gán cho NV qua `employees.default_shift_id`. Dùng để đối chiếu chấm công → đi muộn/về sớm/OT
và tính công theo tỷ lệ giờ làm.

| Column          | Type (SQLAlchemy → SQLite / Postgres)                  | Key    | Null | Default        | Meaning                                                          |
| --------------- | ------------------------------------------------------ | ------ | ---- | -------------- | ---------------------------------------------------------------- |
| `id`            | `Integer` → `INTEGER` / `SERIAL`                       | **PK** | no   | auto-increment | Surrogate primary key.                                           |
| `name`          | `String(100)` → `VARCHAR(100)`                         | —      | no   | —              | Tên ca (vd "Hành chính", "Ca 1").                                |
| `start_minute`  | `Integer` → `INTEGER`                                  | —      | no   | —              | Giờ vào ca = phút từ 0h (8:00 = 480).                            |
| `end_minute`    | `Integer` → `INTEGER`                                  | —      | no   | —              | Giờ ra ca = phút từ 0h (17:00 = 1020).                           |
| `is_overnight`  | `Boolean` → `BOOLEAN`                                  | —      | no   | `false`        | Ca qua ngày (ra hôm sau, vd 22:00→06:00).                        |
| `night_shift`   | `Boolean` → `BOOLEAN`                                  | —      | no   | `false`        | Ca đêm (cờ phụ cấp — quy tiền để module Lương).                  |
| `grace_minutes` | `Integer` → `INTEGER`                                  | —      | no   | `5`            | Dung sai đi muộn (phút): vào trễ ≤ giá trị này vẫn coi đúng giờ. |
| `is_active`     | `Boolean` → `BOOLEAN`                                  | —      | no   | `true`         | Ca đang dùng.                                                    |
| `note`          | `String(500)` → `VARCHAR(500)`                         | —      | yes  | —              | Ghi chú.                                                         |
| `created_at`    | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —      | no   | now (UTC)      | Khi tạo.                                                         |

**Keys & indexes**

- Primary key: `id`.

**Relationships**

- Referenced by `employees.default_shift_id` (logical link, no enforced FK).

---

### `leave_types`

**Purpose:** catalog loại nghỉ (Nghỉ phép — module `nhan_su`), HR khai. One row per loại
(Phép năm / Ốm / Không lương / Việc riêng…). `is_paid` quyết định tác động "công" trên Bảng
công tháng (có lương = 1 công "P"; không lương = 0 công "KL").

| Column         | Type (SQLAlchemy → SQLite / Postgres)                  | Key    | Null | Default        | Meaning                                                             |
| -------------- | ------------------------------------------------------ | ------ | ---- | -------------- | ------------------------------------------------------------------- |
| `id`           | `Integer` → `INTEGER` / `SERIAL`                       | **PK** | no   | auto-increment | Surrogate primary key.                                              |
| `name`         | `String(100)` → `VARCHAR(100)`                         | —      | no   | —              | Tên loại nghỉ.                                                      |
| `is_paid`      | `Boolean` → `BOOLEAN`                                  | —      | no   | `true`         | Có lương hay không (tác động công).                                 |
| `annual_quota` | `Integer` → `INTEGER`                                  | —      | no   | `0`            | Hạn mức ngày/năm (thông tin; trừ dần để Lương). 0 = không giới hạn. |
| `is_active`    | `Boolean` → `BOOLEAN`                                  | —      | no   | `true`         | Loại đang dùng.                                                     |
| `note`         | `String(500)` → `VARCHAR(500)`                         | —      | yes  | —              | Ghi chú.                                                            |
| `created_at`   | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —      | no   | now (UTC)      | Khi tạo.                                                            |

**Keys & indexes**

- Primary key: `id`.

**Relationships**

- Referenced by `leave_requests.leave_type_id` (ON DELETE SET NULL).

---

### `leave_requests`

**Purpose:** đơn xin nghỉ của một NV (Nghỉ phép — module `nhan_su`). Nguyên ngày, từ
`start_date` đến `end_date` bao gồm. Workflow `pending → approved / rejected / cancelled`.
Đơn `approved` được Bảng công tháng đọc (đánh dấu P/KL các ngày trong khoảng).

| Column                | Type (SQLAlchemy → SQLite / Postgres)                  | Key                           | Null | Default        | Meaning                                                                                                                                            |
| --------------------- | ------------------------------------------------------ | ----------------------------- | ---- | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                  | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                        | no   | auto-increment | Surrogate primary key.                                                                                                                             |
| `employee_id`         | `Integer` → `INTEGER`                                  | **FK→employees.id**, **IX**   | no   | —              | NV xin nghỉ; `ON DELETE CASCADE`.                                                                                                                  |
| `leave_type_id`       | `Integer` → `INTEGER`                                  | **FK→leave_types.id**, **IX** | yes  | —              | Loại nghỉ; `ON DELETE SET NULL`.                                                                                                                   |
| `start_date`          | `Date` → `DATE`                                        | **IX**                        | no   | —              | Từ ngày (bao gồm).                                                                                                                                 |
| `end_date`            | `Date` → `DATE`                                        | —                             | no   | —              | Đến ngày (bao gồm).                                                                                                                                |
| `days`                | `Integer` → `INTEGER`                                  | —                             | no   | `1`            | Số ngày nghỉ = số ngày lịch bao gồm 2 đầu.                                                                                                         |
| `reason`              | `String(500)` → `VARCHAR(500)`                         | —                             | yes  | —              | Lý do nghỉ.                                                                                                                                        |
| `status`              | `String(16)` → `VARCHAR(16)`                           | **IX**                        | no   | `pending`      | pending/approved/rejected/cancelled.                                                                                                               |
| `decided_by`          | `Integer` → `INTEGER`                                  | **FK→users.id**               | yes  | —              | Người duyệt/từ chối.                                                                                                                               |
| `decided_at`          | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                             | yes  | —              | Thời điểm duyệt/từ chối.                                                                                                                           |
| `decision_note`       | `String(500)` → `VARCHAR(500)`                         | —                             | yes  | —              | Lý do từ chối / ghi chú duyệt.                                                                                                                     |
| `created_by`          | `Integer` → `INTEGER`                                  | **FK→users.id**               | yes  | —              | Người tạo đơn.                                                                                                                                     |
| `created_at`          | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                             | no   | now (UTC)      | Khi tạo đơn.                                                                                                                                       |
| `seen_by_employee_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                             | yes  | —              | Thời điểm NV mở Nghỉ phép (mark-seen) — đơn đã quyết mà chưa xem thì đếm vào chuông. Timestamp (không Boolean, né gotcha server_default Postgres). |

**Keys & indexes**

- Primary key: `id`.
- Indexes: `ix_leave_requests_employee_id`, `ix_leave_requests_leave_type_id`, `ix_leave_requests_start_date`, `ix_leave_requests_status`.
- Foreign keys: `employee_id FK→employees.id` (CASCADE), `leave_type_id FK→leave_types.id` (SET NULL), `decided_by`/`created_by FK→users.id`.

**Relationships**

- Many requests belong to one `employees` (cascade delete) and reference one `leave_types`.

---

### `work_calendar_config`

**Purpose:** cấu hình tuần làm việc (Lịch làm việc & Ngày lễ — module `nhan_su`, Pha 1). 1 dòng
active (id nhỏ nhất), get-or-create như `payroll_params`. 7 cột boolean bật/tắt từng thứ — nguồn
chung cho Chấm công / Nghỉ phép / Lương thay hardcode T7/CN. Mặc định T2–T7 làm, CN nghỉ.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `works_mon` | `Boolean` → `BOOLEAN` | — | no | `true` | Thứ 2 là ngày làm việc. |
| `works_tue` | `Boolean` → `BOOLEAN` | — | no | `true` | Thứ 3 là ngày làm việc. |
| `works_wed` | `Boolean` → `BOOLEAN` | — | no | `true` | Thứ 4 là ngày làm việc. |
| `works_thu` | `Boolean` → `BOOLEAN` | — | no | `true` | Thứ 5 là ngày làm việc. |
| `works_fri` | `Boolean` → `BOOLEAN` | — | no | `true` | Thứ 6 là ngày làm việc. |
| `works_sat` | `Boolean` → `BOOLEAN` | — | no | `true` | Thứ 7 là ngày làm việc. |
| `works_sun` | `Boolean` → `BOOLEAN` | — | no | `false` | Chủ Nhật là ngày làm việc. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Lần cập nhật. |

**Keys & indexes**

- Primary key: `id`.

---

### `special_days`

**Purpose:** ngày đặc biệt theo ngày dương (Lịch làm việc & Ngày lễ — module `nhan_su`, Pha 1).
`kind='off'` = nghỉ lễ / nghỉ hoán đổi; `kind='work'` = làm bù (đi làm ngày lẽ ra nghỉ). Nguồn
sự thật để `is_working_day` đảo trạng thái ngày theo tuần. `is_paid` (chỉ với `off`) = lễ hưởng
lương → Bảng công cộng 1 công. Giả định `is_paid` = công ty trả 100% (nghỉ nguồn BHXH không khai).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `day` | `Date` → `DATE` | **UQ**, **IX** | no | — | Ngày dương cụ thể (1 ngày 1 bản ghi). |
| `kind` | `String(8)` → `VARCHAR(8)` | — | no | `off` | `off` = nghỉ lễ; `work` = làm bù. |
| `name` | `String(200)` → `VARCHAR(200)` | — | no | — | Tên ngày (vd "Quốc khánh"). |
| `is_paid` | `Boolean` → `BOOLEAN` | — | no | `true` | Lễ hưởng lương (chỉ có nghĩa với `off`). |
| `note` | `String(500)` → `VARCHAR(500)` | — | yes | — | Ghi chú (vd "mùng 1 Tết ÂL"). |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo. |

**Keys & indexes**

- Primary key: `id`.
- Unique + index: `day` (`ix_special_days_day`, unique) — lookup nhanh + chặn khai trùng ngày.

---

### `payroll_params`

**Purpose:** tham số cấu hình Lương (module `luong`) — 1 dòng active. Không hardcode.

| Column | Type | Null | Default | Meaning |
|---|---|---|---|---|
| `id` | `Integer` | no | auto | PK. |
| `standard_cong_default` | `Numeric(6,2)` | no | `26` | Công chuẩn/tháng để prorate lương thời gian. |
| `probation_ratio` | `Numeric(5,4)` | no | `0.85` | Thử việc hưởng % của lương chính thức (Đ26 BLLĐ ≥85%). |
| `bhxh_rate` | `Numeric(6,4)` | no | `0.08` | Tỷ lệ NV đóng BHXH. |
| `bhyt_rate` | `Numeric(6,4)` | no | `0.015` | Tỷ lệ NV đóng BHYT. |
| `bhtn_rate` | `Numeric(6,4)` | no | `0.01` | Tỷ lệ NV đóng BHTN. |
| `deduction_self` | `Numeric(14,2)` | no | `15500000` | Giảm trừ gia cảnh bản thân (TNCN, mức 2026 NQ 110/2025). |
| `deduction_dependent` | `Numeric(14,2)` | no | `6200000` | Giảm trừ mỗi người phụ thuộc (mức 2026). |
| `chuyen_can_default` | `Numeric(14,2)` | no | `300000` | Mức chuyên cần mặc định (đủ công). |
| `standard_hours_per_day` | `Numeric(5,2)` | no | `8` | Giờ công chuẩn/ngày (quy đơn giá giờ OT — Pha 4a). |
| `ot_multiplier` | `Numeric(5,2)` | no | `1.5` | Hệ số OT ngày thường (Đ98 ≥1.5 — Pha 4a). |
| `ot_multiplier_restday` | `Numeric(5,2)` | no | `2` | Hệ số OT ngày nghỉ tuần (Đ98 ≥2.0). Thêm qua migration 0064. |
| `ot_multiplier_holiday` | `Numeric(5,2)` | no | `3` | Hệ số OT ngày lễ (Đ98 ≥3.0). Thêm qua migration 0064. |
| `restday_work_multiplier` | `Numeric(5,2)` | no | `2` | Làm nguyên công ngày nghỉ tuần (Đ98 ≥200%). Thêm qua migration 0064. |
| `holiday_work_multiplier` | `Numeric(5,2)` | no | `3` | Làm nguyên công ngày lễ (Đ98 ≥300%). Thêm qua migration 0064. |
| `night_pct` | `Numeric(5,4)` | no | `0.3` | Phụ cấp ca đêm: % đơn giá 1 công/ngày ca đêm (Đ98 ≥30% — Pha 4a). |
| `bh_base_cap` | `Numeric(14,2)` | no | `50600000` | Trần đóng BHXH+BHYT = 20× mức tham chiếu; 0 = không trần (Pha 4a). |
| `bhtn_base_cap` | `Numeric(14,2)` | no | `106200000` | Trần đóng BHTN = 20× lương tối thiểu vùng; 0 = không trần (Pha 4a). |
| `updated_at` | `DateTime(tz)` | no | now | Lần cập nhật. |

---

### `salary_rate_rules`

**Purpose:** bảng chính sách MỨC lương theo `(payroll_group, pay_grade_key?, seniority_band?, gender?)`.
Lookup khớp cụ thể nhất, `effective_from ≤ kỳ`. Chiều NULL = wildcard.

| Column           | Type            | Key    | Null | Default | Meaning                                         |
| ---------------- | --------------- | ------ | ---- | ------- | ----------------------------------------------- |
| `id`             | `Integer`       | **PK** | no   | auto    | PK.                                             |
| `payroll_group`  | `String(40)`    | **IX** | no   | —       | Nhóm lương (trục tra chính).                    |
| `pay_grade_key`  | `String(20)`    | —      | yes  | —       | Bậc lương chuẩn hóa (tho_1..phu_2).             |
| `seniority_band` | `String(8)`     | —      | yes  | —       | Nhóm thâm niên (lt1/y1_5/y5_10/gt10).           |
| `gender`         | `String(8)`     | —      | yes  | —       | Giới tính áp dụng (male/female).                |
| `monthly_amount` | `Numeric(14,2)` | —      | no   | —       | Mức lương tháng chuẩn.                          |
| `chuyen_can`     | `Numeric(14,2)` | —      | yes  | —       | Mức chuyên cần riêng nhóm (NULL = dùng params). |
| `effective_from` | `Date`          | **IX** | yes  | —       | Hiệu lực từ.                                    |
| `is_active`      | `Boolean`       | —      | no   | `true`  | Đang áp dụng.                                   |
| `note`           | `String(255)`   | —      | yes  | —       | Ghi chú.                                        |
| `created_at`     | `DateTime(tz)`  | —      | no   | now     | Khi tạo.                                        |

---

### `employee_salaries`

**Purpose:** lương ẤN ĐỊNH của 1 NV tại một mốc hiệu lực (versioned). Điều chỉnh = thêm bản ghi;
"hiện hành" = `effective_from` lớn nhất ≤ kỳ.

| Column           | Type            | Key                         | Null | Default | Meaning                              |
| ---------------- | --------------- | --------------------------- | ---- | ------- | ------------------------------------ |
| `id`             | `Integer`       | **PK**                      | no   | auto    | PK.                                  |
| `employee_id`    | `Integer`       | **FK→employees.id**, **IX** | no   | —       | NV; `ON DELETE CASCADE`.             |
| `effective_from` | `Date`          | **IX**                      | no   | —       | Hiệu lực từ.                         |
| `amount_mode`    | `String(8)`     | —                           | no   | `rule`  | rule (tra bảng) / manual (nhập tay). |
| `base_amount`    | `Numeric(14,2)` | —                           | yes  | —       | Mức tháng khi manual.                |
| `insurance_base` | `Numeric(14,2)` | —                           | yes  | —       | Mức đóng BH (NULL = mức lương).      |
| `allowance`      | `Numeric(14,2)` | —                           | no   | `0`     | Phụ cấp cố định tháng.               |
| `note`           | `String(255)`   | —                           | yes  | —       | Ghi chú.                             |
| `created_by`     | `Integer`       | **FK→users.id**             | yes  | —       | Người khai/điều chỉnh.               |
| `created_at`     | `DateTime(tz)`  | —                           | no   | now     | Khi tạo.                             |

---

### `salary_advances`

**Purpose:** tạm ứng lương (đa lần/tháng), gắn kỳ `(period_year, period_month)`. Workflow duyệt.

| Column          | Type            | Key                         | Null | Default   | Meaning                              |
| --------------- | --------------- | --------------------------- | ---- | --------- | ------------------------------------ |
| `id`            | `Integer`       | **PK**                      | no   | auto      | PK.                                  |
| `employee_id`   | `Integer`       | **FK→employees.id**, **IX** | no   | —         | NV ứng; `ON DELETE CASCADE`.         |
| `period_year`   | `Integer`       | **IX**                      | no   | —         | Năm kỳ lương áp dụng.                |
| `period_month`  | `Integer`       | **IX**                      | no   | —         | Tháng kỳ lương áp dụng.              |
| `advance_date`  | `Date`          | —                           | no   | —         | Ngày ứng.                            |
| `amount`        | `Numeric(14,2)` | —                           | no   | —         | Số tiền ứng.                         |
| `reason`        | `String(255)`   | —                           | yes  | —         | Lý do.                               |
| `status`        | `String(12)`    | **IX**                      | no   | `pending` | pending/approved/rejected/cancelled. |
| `decided_by`    | `Integer`       | **FK→users.id**             | yes  | —         | Người duyệt.                         |
| `decided_at`    | `DateTime(tz)`  | —                           | yes  | —         | Thời điểm duyệt.                     |
| `decision_note` | `String(255)`   | —                           | yes  | —         | Ghi chú duyệt.                       |
| `created_by`    | `Integer`       | **FK→users.id**             | yes  | —         | Người tạo.                           |
| `created_at`    | `DateTime(tz)`  | —                           | no   | now       | Khi tạo.                             |

---

### `payroll_periods`

**Purpose:** kỳ lương 1 tháng. UNIQUE(`year`,`month`). draft → locked (chốt, khóa số).

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `year` | `Integer` | **UQ(year,month)** | no | — | Năm. |
| `month` | `Integer` | **UQ(year,month)** | no | — | Tháng. |
| `status` | `String(8)` | — | no | `draft` | draft/locked/paid. |
| `standard_cong` | `Numeric(6,2)` | — | no | `26` | Công chuẩn của kỳ. |
| `locked_at` | `DateTime(tz)` | — | yes | — | Thời điểm chốt. |
| `locked_by` | `Integer` | **FK→users.id** | yes | — | Người chốt. |
| `paid_at` | `DateTime(tz)` | — | yes | — | Thời điểm đánh dấu đã chi. Thêm qua migration 0045. |
| `paid_by` | `Integer` | **FK→users.id** | yes | — | Người đánh dấu đã chi. Thêm qua migration 0045. |
| `created_by` | `Integer` | **FK→users.id** | yes | — | Người tạo kỳ. |
| `created_at` | `DateTime(tz)` | — | no | now | Khi tạo. |

---

### `payroll_lines`

**Purpose:** dòng lương 1 NV trong 1 kỳ (snapshot). UNIQUE(`period_id`,`employee_id`).

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `period_id` | `Integer` | **FK→payroll_periods.id**, **IX** | no | — | Kỳ lương; `ON DELETE CASCADE`. |
| `employee_id` | `Integer` | **FK→employees.id**, **IX** | no | — | NV; `ON DELETE CASCADE`. |
| `is_probation` | `Boolean` | — | no | `false` | Thử việc (áp %thử việc). |
| `actual_cong` | `Numeric(6,2)` | — | no | `0` | Số công thực (từ Chấm công). |
| `standard_cong` | `Numeric(6,2)` | — | no | `26` | Công chuẩn kỳ. |
| `monthly_salary` | `Numeric(14,2)` | — | no | `0` | Mức lương tháng (đã giải). |
| `luong_cong` | `Numeric(14,2)` | — | no | `0` | Lương theo công. |
| `chuyen_can` | `Numeric(14,2)` | — | no | `0` | Thưởng chuyên cần. |
| `allowance` | `Numeric(14,2)` | — | no | `0` | Phụ cấp cố định. |
| `khoan` | `Numeric(14,2)` | — | no | `0` | Lương khoán (nhịp 2, từ sổ khoán). Thêm qua migration 0013. |
| `ot_minutes` | `Integer` | — | no | `0` | Tổng phút tăng ca (từ Chấm công). Thêm qua migration 0043. |
| `ot_pay` | `Numeric(14,2)` | — | no | `0` | Tiền tăng ca (hệ số phẳng). Thêm qua migration 0043. |
| `night_days` | `Integer` | — | no | `0` | Số ngày làm ca đêm. Thêm qua migration 0043. |
| `night_pay` | `Numeric(14,2)` | — | no | `0` | Phụ cấp ca đêm. Thêm qua migration 0043. |
| `vi_pham` | `Numeric(14,2)` | — | no | `0` | Trừ vi phạm (nhập tay). |
| `other_bonus` | `Numeric(14,2)` | — | no | `0` | Thưởng/hoa hồng (nhập tay). |
| `gross` | `Numeric(14,2)` | — | no | `0` | Tổng thu nhập trước khấu trừ. |
| `insurance_base` | `Numeric(14,2)` | — | no | `0` | Mức đóng BH. |
| `bhxh` | `Numeric(14,2)` | — | no | `0` | Khấu trừ BHXH/BHYT/BHTN. |
| `pit` | `Numeric(14,2)` | — | no | `0` | Thuế TNCN (tự tính, có thể ghi đè tay). |
| `pit_manual` | `Boolean` | — | no | `false` | TNCN do HCNS ghi đè tay (không auto ghi đè). Thêm qua migration 0044. |
| `pit_taxable` | `Numeric(14,2)` | — | no | `0` | Thu nhập tính thuế đã dùng để tính TNCN. Thêm qua migration 0044. |
| `advance_total` | `Numeric(14,2)` | — | no | `0` | Tổng tạm ứng đã duyệt. |
| `net_pay` | `Numeric(14,2)` | — | no | `0` | Thực lĩnh. |
| `note` | `String(255)` | — | yes | — | Ghi chú. |
| `updated_at` | `DateTime(tz)` | — | no | now | Lần cập nhật. |

---

### `pit_tax_brackets`

**Purpose:** biểu thuế TNCN lũy tiến từng phần (biểu tháng) — dữ liệu SỬA ĐƯỢC để cập nhật khi
luật đổi. Bảng do `create_all` tạo (không migration); seed-once 5 bậc 2026 (Luật 109/2025/QH15).

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `seq` | `Integer` | — | no | — | Thứ tự bậc (1..N), tính lũy tiến theo thứ tự. |
| `up_to` | `Numeric(14,2)` | — | yes | — | Trần thu nhập tính thuế/tháng của bậc; NULL = bậc cao nhất (∞). |
| `rate` | `Numeric(5,4)` | — | no | — | Thuế suất (0.05 = 5%). |

---

### `piece_rates`

**Purpose:** đơn giá khoán (Lương khoán nhịp 2) theo tổ + đơn vị (m²/bài in/tấn/cuốn/lượt/hộp).

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `group_name` | `String(40)` | **IX** | no | — | Tổ khoán (to_boi/to_cat/may_in_5mau…). |
| `code` | `String(20)` | — | yes | — | Mã (A–F cho máy in). |
| `name` | `String(255)` | — | no | — | Tên công việc. |
| `cong_doan` | `String(30)` | **IX** | yes | — | Mã công đoạn gắn đơn giá (Pha 5b, ref `cong_doan.ma`). |
| `unit` | `String(12)` | — | no | `khac` | Đơn vị (m2/bai_in/tan/cuon/luot/hop/to/khac). |
| `unit_price` | `Numeric(14,2)` | — | no | — | Đơn giá/đơn vị. |
| `note` | `String(255)` | — | yes | — | Ghi chú. |
| `is_active` | `Boolean` | — | no | `true` | Đang dùng. |
| `created_at` | `DateTime(tz)` | — | no | now | Khi tạo. |

---

### `profile_update_requests`

**Purpose:** yêu cầu cập nhật hồ sơ (nhan_su) — NV đề nghị sửa field định danh/pháp lý/ngân
hàng; HCNS duyệt (quyền `approve`) mới áp vào `employees`.

| Column          | Type           | Key                         | Null | Default   | Meaning                                              |
| --------------- | -------------- | --------------------------- | ---- | --------- | ---------------------------------------------------- |
| `id`            | `Integer`      | **PK**                      | no   | auto      | PK.                                                  |
| `employee_id`   | `Integer`      | **FK→employees.id**, **IX** | no   | —         | NV đề nghị; `ON DELETE CASCADE`.                     |
| `changes`       | `JSON`         | —                           | no   | —         | {field: giá trị mới} — whitelist REQUESTABLE_FIELDS. |
| `reason`        | `String(500)`  | —                           | yes  | —         | Lý do đề nghị.                                       |
| `status`        | `String(12)`   | **IX**                      | no   | `pending` | pending/approved/rejected.                           |
| `decided_by`    | `Integer`      | **FK→users.id**             | yes  | —         | HCNS duyệt/từ chối.                                  |
| `decided_at`    | `DateTime(tz)` | —                           | yes  | —         | Thời điểm quyết định.                                |
| `decision_note` | `String(500)`  | —                           | yes  | —         | Ghi chú duyệt/lý do từ chối.                         |
| `created_at`    | `DateTime(tz)` | —                           | no   | now       | Khi gửi.                                             |

---

## Pipeline in-ấn (rebuild) — master data mới

> 4 module master mới (strangler, song song bảng cũ) — danh mục cấu hình sản xuất:
> `may_thiet_bi` · `giay_nguyen`/`muc`/`ban_kem` (vật liệu Kho) · `cong_doan` · `loai_san_pham`.
> Specs: `docs/spec-may-thiet-bi.md`, `spec-cong-doan.md`, `spec-san-pham.md`.
> (Quy tắc bình bài + Tính giá thành đã bỏ — xem git tag `backup/pre-remove-binhbai-tinhgia`.)

### `may_thiet_bi`

**Purpose:** máy sản xuất = cost center (BHR) + spec năng lực (khổ/nhíp/units). Một row = một máy. Field theo `loai_may` gói trong JSON `fields_theo_loai`; các field engine dùng nhiều được promote thành cột thật.

| Column                                                                                  | Type           | Meaning                                                                       |
| --------------------------------------------------------------------------------------- | -------------- | ----------------------------------------------------------------------------- |
| `id`                                                                                    | `Integer` PK   | khóa chính.                                                                   |
| `ma`                                                                                    | `String(30)` U | mã máy (VD `OFF-74-4C`).                                                      |
| `ten`                                                                                   | `String(150)`  | tên.                                                                          |
| `loai_may`                                                                              | `String` IX    | discriminator (press_offset_sheet / digital / ctp / finishing / thue_ngoai…). |
| `trang_thai`                                                                            | `String`       | active / maintenance / retired (không có cột `active` riêng).                 |
| `khoa_class`                                                                            | `String`       | lớp khổ máy → tra giá kẽm (`ban_kem.khoa_class`).                             |
| `gripper_mm` `so_units` `kho_max_dai/rong` `kho_min_dai/rong`                           |                | seam bình bài.                                                                |
| BHR (`von_dau_tu` `nam_khau_hao` `gio_lam_nam` `availability_pct` `productivity_pct` …) |                | công thức đơn giá giờ máy (spec §4).                                          |
| `fields_theo_loai`                                                                      | `JSON`         | field đặc thù theo `loai_may`.                                                |

**Tất cả cột:** `id`, `ma`, `ten`, `loai_may`, `finishing_subtype`, `nhom_cost_center`, `phong_ban_id`, `dia_diem`, `hang_san_xuat`, `model`, `so_seri`, `trang_thai`, `ghi_chu`, `ghi_chu_2`, `ma_tai_san`, `ma_TK_cost_center`, `nha_cung_cap`, `ngay_dua_vao_su_dung`, `het_han_bao_hanh`, `phuong_phap_khau_hao`, `nguon_bhr`, `don_gia_gio_BHR`, `von_dau_tu`, `gia_tri_thu_hoi`, `nam_khau_hao`, `lai_von_pct`, `gio_lam_nam`, `availability_pct`, `productivity_pct`, `efficiency_pct`, `so_nhan_cong`, `luong_gio`, `luong_burden_pct`, `cong_suat_kW`, `he_so_tai_dien`, `don_gia_dien`, `bao_hiem_nam`, `dien_tich_san_m2`, `don_gia_thue_m2_nam`, `bao_tri_gio`, `overhead_gio`, `markup_pct`, `ngay_cap_nhat_bhr`, `toc_do`, `don_vi_toc_do`, `makeready_time_default`, `thoi_gian_rua_muc`, `min_stock_gsm`, `max_stock_gsm`, `vat_lieu_ho_tro_class`, `so_may_song_song`, `so_ca`, `chi_so_dem_luot`, `ngay_bao_tri_gan_nhat`, `chu_ky_bao_tri`, `chu_ky_bao_tri_don_vi`, `ngay_bao_tri_ke_tiep`, `kho_max_dai`, `kho_max_rong`, `kho_min_dai`, `kho_min_rong`, `kho_kem_dai`, `kho_kem_rong`, `vung_in_dai`, `vung_in_rong`, `gripper_mm`, `le_hong_mm`, `duoi_thang_mau_mm`, `so_units`, `units_truoc`, `units_sau`, `khoa_class`, `co_tro_mat`, `cho_phep_tu_tro`, `cho_phep_tro_dau_duoi`, `bu_hao_canh_may_per_mau`, `bu_hao_chay_pct`, `ho_tro_cip3`, `fields_theo_loai`, `created_at`, `updated_at`.

### `chung_loai_giay`

**Purpose:** chủng loại giấy (Couché/Ford/Bristol/Ivory/Duplex/Kraft…) — phân loại; `giay_nguyen` ăn theo đây. Một row = một chủng loại.

**Tất cả cột:** `id`, `ma`, `ten`, `be_mat`, `tho_mac_dinh`, `mo_ta`, `active`, `created_at`, `updated_at`.

### `giay_nguyen`

**Purpose:** tờ giấy nguyên (khổ mua) — thuộc 1 chủng loại (`chung_loai_giay_id`, soft int). Một row = một loại giấy cụ thể.

**Tất cả cột:** `id`, `ma`, `ten`, `chung_loai_giay_id`, `kho_dai`, `kho_rong`, `gsm`, `caliper_micron`, `tho`, `don_vi_gia`, `don_gia`, `gia_thi_truong`, `kho_tinh_gia`, `cong_thuc_gia`, `ghi_chu`, `version_no`, `active`, `created_at`, `updated_at`.

### `giay_gia_version`

**Purpose:** phiên bản giá giấy (lịch sử) — ẢNH CHỤP toàn bản ghi `giay_nguyen` tại 1 mốc hiệu lực. Mỗi lần "Thêm phiên bản" đẻ 1 row; `is_current` = mốc đang áp dụng (mirror giá lên `giay_nguyen`). Bảng mới do create_all tạo (không migration). `giay_id` soft int → `giay_nguyen`.

**Tất cả cột:** `id`, `giay_id`, `version_no`, `ngay_hieu_luc`, `is_current`, `kho_dai`, `kho_rong`, `gsm`, `caliper_micron`, `tho`, `don_vi_gia`, `don_gia`, `gia_thi_truong`, `ghi_chu`, `created_by`, `created_at`.

### `kho_giay_chuan`

**Purpose:** khổ giấy chuẩn (DANH MỤC KHỔ GIẤY CHUẨN, đơn vị **cm**) — mỗi row = 1 khổ của 1 chủng loại. `dai` NULL = giấy cuộn/khổ mở (cắt tự do 1 chiều). `la_hiem` = khổ hiếm (báo thu mua trước). `chung_loai_giay_id` soft int → `chung_loai_giay`.

**Tất cả cột:** `id`, `ma`, `ten`, `chung_loai_giay_id`, `rong`, `dai`, `la_hiem`, `ghi_chu`, `active`, `created_at`, `updated_at`.

### `vat_tu_in_an`

**Purpose:** vật tư in ấn — danh mục PHẲNG (mực/kẽm/hoá chất/màng/keo… chung 1 bảng, phân biệt bằng tên) theo bảng xưởng: Mã · Tên · ĐVT · Giá · Ghi chú. Thay 2 bảng cũ `muc`+`ban_kem`.

**Tất cả cột:** `id`, `ma`, `ten`, `don_vi_gia`, `don_gia`, `cong_thuc_gia`, `ghi_chu`, `active`, `created_at`, `updated_at`.

### `cong_doan`

**Purpose:** danh mục công đoạn (thao tác + cách tính giá + máy) — spec-cong-doan §2. Routing per-job (`routing_step`) = Phase D. `may_id` soft int → `may_thiet_bi`. `department_id` soft int → `departments` (tổ/bộ phận phụ trách — phát Lệnh SX đẩy việc theo đây).

**Tất cả cột:** `id`, `ma`, `ten`, `ten_hien_thi`, `kieu_bu_hao`, `bu_hao_id`, `nhom`, `may_id`, `department_id`, `khoan_ghi_theo`, `allowed_defect_pct`, `allowed_defect_abs`, `che_do_tinh`, `pricing_basis`, `setup_cost`, `setup_time`, `run_rate`, `rate_tiers`, `size_tiers`, `first_unit_floor`, `min_charge`, `requires_tooling`, `tooling_type`, `spoilage_pct`, `so_to_bu_hao`, `inline_flag`, `cong_thuc_gia`, `ghi_chu`, `active`, `created_at`, `updated_at`.

`size_tiers` (JSON): bậc đơn giá theo KÍCH THƯỚC thành phẩm (cạnh dài, cm) — `[{den_cm, don_gia}]`, "≤ den_cm → đơn giá"; engine chọn giá theo cỡ thay `run_rate` (vd công dán ≤20cm=100 · 40cm=200 · 100cm=800). `pricing_basis="per_job"` = trọn gói một lần (khuôn bế) — engine ÷ SL.

`khoan_ghi_theo`: công đoạn có tính khoán không — `nguoi` (ghi Phiếu sản lượng theo từng người → cột Khoán bảng lương) / `khong`. `allowed_defect_pct`/`allowed_defect_abs`: ngưỡng hao cho phép (max của 2), phần vượt mới trừ lỗi.

`kieu_bu_hao`: nối bù hao — `khong` / `tra_bang` (trỏ 1 mã bù hao qua `bu_hao_id` → tra bậc theo SL) / `co_dinh` (cộng `so_to_bu_hao` tờ). `bu_hao_id`: soft int → `bu_hao.id` (dùng khi `kieu_bu_hao='tra_bang'`).

### `bu_hao`

**Purpose:** danh mục Bù hao — mỗi mã = danh sách BẬC số lượng → số tờ / %. Mô hình MỞ: bậc là dữ liệu JSON (`bac`), không phải cột cứng. Công đoạn TRỎ THẲNG 1 mã bù hao (qua `cong_doan.bu_hao_id`); engine tra bậc theo SL (bỏ trục số màu/số con). `bac` = `[{sl_tu, sl_den, gia_tri, don_vi(to|pct)}]`.

**Tất cả cột:** `id`, `ma`, `ten`, `bac`, `ghi_chu`, `active`, `created_at`, `updated_at`.

### `loai_san_pham`

**Purpose:** template loại sản phẩm (spec-san-pham §2) — gán `imposition_rule_id` (soft → `quy_tac_binh_bai`) + `routing_template` (JSON list `cong_doan.id`) + VAT. `jobspec`/`component` = Phase D.

**Tất cả cột:** `id`, `ma`, `ten`, `structural_type`, `box_sub_type`, `imposition_rule_id`, `has_cover`, `cover_type`, `default_binding`, `default_stock_class`, `routing_template`, `ghi_chu`, `active`, `created_at`, `updated_at`.

### `phieu_tinh_gia`

**Purpose:** Phiếu tính giá (costing ticket) THEO THÀNH PHẦN — bản LƯU của máy tính giá vốn. 1 phiếu = header (thông tin chung + SL đặt + soft FK loại SP) + NHIỀU thành phần (`phieu_thanh_phan`, mỗi thành phần = 1 tờ giấy). Giữ ẢNH CHỤP kết quả engine (`result_json`, `tong_gia_von`, `gia_von_don`, `warnings_json`) để FE liệt kê + mở lại xem/sửa/tính lại. Số con / màu / mặt / giấy / máy / công đoạn ĐÃ DỜI xuống `phieu_thanh_phan`. Không có công nghệ / khách hàng / trạng thái (thuộc module Báo giá).

**Tất cả cột:** `id`, `ma`, `ten_san_pham`, `kho_thanh_pham`, `loai_san_pham_id`, `so_luong`, `tong_gia_von`, `gia_von_don`, `result_json`, `warnings_json`, `ktv`, `created_by`, `ghi_chu`, `created_at`, `updated_at`.

- `created_by`: `Integer` soft → `users.id` — chủ sở hữu phiếu (P8, migration 0053). Lọc phạm vi Tính giá: NV Sales scope "Của tôi" chỉ thấy phiếu mình lập, TP KD/GĐ scope phòng/tất cả thấy hết. Dữ liệu cũ backfill từ `ktv` (khớp name/username), không khớp = NULL (chỉ scope 'all' thấy).

---

### `phieu_thanh_phan`

**Purpose:** Thành phần (1 tờ giấy) của 1 phiếu tính giá — con của `phieu_tinh_gia` (`phieu_id` FK thật, cascade xoá). Gom cấu hình GIẤY (khổ nguyên, khổ thành phẩm ③ dạng số `dai/rong_thanh_pham`, đơn giá theo tờ|tấn, nguồn công ty|khách, bù hao số tờ, các loại tờ chừa) + KỸ THUẬT IN (chế bản/kẽm, quy cách 1 mặt|2 mặt|tự trở, khổ tờ in ② `kho_in_dai/rong`, số con ④ `so_con` + cờ `con_auto` tự bình bài, máy, đơn giá công in gộp mực) + MÀU (đã gộp: chỉ `so_mau_a`/`so_mau_b` — KHÔNG hệ số, KHÔNG tách SEL/Pantone/Nền). `giay_id`/`may_id` soft FK. `gia_von_tp` = ảnh chụp giá vốn thành phần (Σ 4 nhóm A/B/C/D). Mỗi thành phần có nhiều dòng gia công sau in (`phieu_thanh_pham`). Tính giá vốn KHÔNG dùng hệ số (mọi hệ số = 1 → đã gỡ khỏi model).

**Tất cả cột:** `id`, `phieu_id`, `thu_tu`, `loai_thanh_phan`, `ten`, `kho_thanh_pham`, `dai_thanh_pham`, `rong_thanh_pham`, `kho_mo_rong`, `tay_gap`, `so_to_per_sp`, `so_luong`, `don_vi_tinh`, `loai_san_pham_id`, `giay_id`, `kho_nguyen`, `kho_nguyen_dai`, `kho_nguyen_rong`, `don_gia_giay`, `don_gia_don_vi`, `nguon_giay`, `bu_hao_so_to`, `hao_so_to`, `tinh_bu_hao_cd`, `chua_xen`, `chua_tay_ke`, `chua_nhip`, `chua_duoi`, `chua_ca_gay`, `co_in`, `che_ban_loai`, `che_ban_don_gia`, `quy_cach_in`, `kho_in_dai`, `kho_in_rong`, `so_con`, `con_auto`, `may_id`, `don_gia_cong_in`, `so_mau_a`, `so_mau_b`, `gia_von_tp`, `created_at`, `updated_at`. `don_vi_tinh` (VARCHAR, migration 0074, default `'cái'`) = ĐVT sản phẩm (text tự do) → chảy sang Báo giá (`quote_items.unit`, thay `'cái'` hardcode). `kho_nguyen_dai`/`kho_nguyen_rong` (mm, migration 0063) = khổ giấy nguyên ① nhập trên phiếu, ĐÈ khổ danh mục Giấy khi > 0 (đặt hàng xả khổ khác); 0 = lấy theo danh mục. `kho_nguyen` giữ làm nhãn hiển thị / `giay_ten` fallback.

---

### `phieu_thanh_pham`

**Purpose:** 1 dòng công đoạn gia công sau in (finishing) của 1 thành phần — con của `phieu_thanh_phan` (`thanh_phan_id` FK thật, cascade xoá). Hoặc tính giá PHẲNG (`don_gia` > 0 × số lượng — `so_luong`=0 nghĩa dùng SL đặt của phiếu) hoặc dùng cấu hình công đoạn danh mục (`cong_doan_id`, soft FK) qua `routing_engine.compute_step_cost` với `so_mat`/`so_vi_tri`/`dien_tich`. `nha_cung_cap` → nhãn thuê ngoài. `bu_hao` cờ báo dòng có góp hao. (Không cột lợi nhuận — đây là giá vốn.)

**Tất cả cột:** `id`, `thanh_phan_id`, `thu_tu`, `cong_doan_id`, `ten`, `don_gia`, `so_luong`, `bu_hao`, `so_mat`, `so_vi_tri`, `dien_tich`, `nha_cung_cap`, `ghi_chu`, `created_at`, `updated_at`.

---

### `phieu_vat_tu`

**Purpose:** 1 dòng VẬT TƯ IN ẤN (mực/màng/keo…) thêm tay của 1 thành phần → NGUYÊN VẬT LIỆU (song song giấy) — con của `phieu_thanh_phan` (`thanh_phan_id` FK thật, cascade xoá). Trỏ 1 mã `vat_tu_id` (soft → `vat_tu_in_an.id`); engine kéo `cong_thuc_gia` + `don_gia` + `don_vi_gia` từ danh mục rồi thế biến vào công thức — HỆT giấy. `don_gia` = ghi đè (0 → lấy danh mục); `so_luong` (0 → SL đặt) cho công thức nếu cần; `ten` nhãn hiển thị; `ghi_chu` ghi chú.

**Tất cả cột:** `id`, `thanh_phan_id`, `thu_tu`, `vat_tu_id`, `ten`, `don_gia`, `so_luong`, `ghi_chu`, `created_at`, `updated_at`.

---

### `suppliers`

**Purpose:** Thu mua (PR#8) — nhà cung cấp. One row = 1 NCC (thông tin liên hệ + nhóm + điều khoản thanh toán).

**Tất cả cột:** `id`, `name`, `tax_code`, `phone`, `email`, `address`, `contact_name`, `supplier_group`, `payment_terms`, `status`, `note`, `created_at`, `updated_at`.

---

### `purchase_requests`

**Purpose:** Thu mua — phiếu mua hàng (PMH) gửi Kế toán duyệt. One row = 1 PMH.

**Tất cả cột:** `id`, `code`, `status`, `supplier_id`, `purpose`, `needed_date`, `expected_receipt_date`, `created_by_user_id`, `submitted_at`, `approved_by_user_id`, `approved_at`, `note`, `created_at`, `updated_at`.

---

### `purchase_request_lines`

**Purpose:** Thu mua — dòng hàng của PMH (mặt hàng, SL, đơn giá, giảm giá %, VAT %). Tiền tính động.

**Tất cả cột:** `id`, `purchase_request_id`, `item_name`, `unit`, `quantity`, `expected_unit_price`, `discount_percent`, `vat_percent`, `note`.

---

### `department_purchase_requests`

**Purpose:** Thu mua — yêu cầu mua hàng từ bộ phận (nguồn của PMH). One row = 1 yêu cầu bộ phận.

**Tất cả cột:** `id`, `code`, `status`, `source_type`, `requesting_department_id`, `requested_by_user_id`, `related_document_type`, `related_document_code`, `purpose`, `needed_date`, `note`, `created_at`, `updated_at`.

---

### `department_purchase_request_lines`

**Purpose:** Thu mua — dòng hàng của yêu cầu bộ phận.

**Tất cả cột:** `id`, `department_request_id`, `item_name`, `unit`, `quantity`, `expected_unit_price`, `note`.

---

### `purchase_request_sources`

**Purpose:** Thu mua — liên kết PMH ↔ yêu cầu bộ phận nguồn (giữ snapshot mã nguồn).

**Tất cả cột:** `id`, `purchase_request_id`, `department_request_id`, `source_code_snapshot`, `created_at`.

---

### `company_bank_accounts`

**Purpose:** Kế toán — tài khoản ngân hàng công ty (chi trả). One row = 1 TK.

**Tất cả cột:** `id`, `account_holder`, `account_number`, `bank_name`, `bank_branch`, `currency`, `is_default`, `is_active`, `note`, `created_at`, `updated_at`.

---

### `supplier_bank_accounts`

**Purpose:** Kế toán — tài khoản ngân hàng thụ hưởng của NCC. One row = 1 TK NCC.

**Tất cả cột:** `id`, `supplier_id`, `account_holder`, `account_number`, `bank_name`, `bank_branch`, `currency`, `is_default`, `is_active`, `note`, `created_at`, `updated_at`.

---

### `payment_vouchers`

**Purpose:** Kế toán — chứng từ chi (Phiếu chi / Ủy nhiệm chi) từ PMH. One row = 1 chứng từ; nhiều cột `*_snapshot` chốt thông tin NCC/ngân hàng tại thời điểm lập.

**Tất cả cột:** `id`, `code`, `doc_no`, `purchase_request_id`, `supplier_id`, `voucher_type`, `payment_stage`, `status`, `voucher_date`, `planned_payment_date`, `amount`, `amount_vnd`, `currency`, `exchange_rate`, `content`, `invoice_number`, `invoice_date`, `contract_number`, `company_bank_account_id`, `supplier_bank_account_id`, `cash_recipient_name`, `cash_recipient_address`, `cash_recipient_identity`, `bank_fee_bearer`, `bank_reference`, `debit_account`, `credit_account`, `source_code_snapshot`, `supplier_name_snapshot`, `supplier_tax_code_snapshot`, `supplier_address_snapshot`, `company_account_holder_snapshot`, `company_account_number_snapshot`, `company_bank_name_snapshot`, `company_bank_branch_snapshot`, `beneficiary_account_holder_snapshot`, `beneficiary_account_number_snapshot`, `beneficiary_bank_name_snapshot`, `beneficiary_bank_branch_snapshot`, `created_by_user_id`, `paid_by_user_id`, `paid_at`, `cancelled_by_user_id`, `cancelled_at`, `cancel_reason`, `note`, `created_at`, `updated_at`.

---

### `payment_voucher_attachments`

**Purpose:** Kế toán — file chứng từ đính kèm Phiếu chi/UNC (hóa đơn/biên nhận scan, minh chứng đã mua). One row = 1 file; bytes ở `backend/static/ke-toan/<voucher_id>/`, DB chỉ lưu metadata + path. Đính thêm được cả khi phiếu đã `paid`; chỉ chặn `cancelled`.

**Tất cả cột:** `id`, `payment_voucher_id`, `file_name`, `file_url`, `file_type`, `uploaded_by`, `uploaded_at`.

---

### `payment_receipt_attachments`

**Purpose:** Kế toán — ảnh minh chứng đã thu đính kèm Phiếu thu (biên nhận/UNC báo có scan). One row = 1 file; bytes ở `backend/static/ke-toan-thu/<receipt_id>/`, DB chỉ lưu metadata + path. Đính thêm được cả khi phiếu đã `received`; chỉ chặn `cancelled`.

**Tất cả cột:** `id`, `payment_receipt_id`, `file_name`, `file_url`, `file_type`, `uploaded_by`, `uploaded_at`.

---

### `payment_receipts`

**Purpose:** Kế toán — Phiếu thu đa nguồn (V5): hoàn ứng từ Phiếu chi đã chi (`phieu_chi`) HOẶC thu cọc khách từ Đơn hàng bán (`don_hang_ban`).

**Tất cả cột:** `id`, `code`, `doc_no`, `source_type`, `payment_voucher_id`, `purchase_request_id`, `order_id`, `payer_name`, `payer_address`, `receipt_method`, `status`, `receipt_date`, `amount`, `amount_vnd`, `currency`, `exchange_rate`, `content`, `company_bank_account_id`, `bank_reference`, `debit_account`, `credit_account`, `voucher_code_snapshot`, `purchase_code_snapshot`, `supplier_name_snapshot`, `customer_name_snapshot`, `order_code_snapshot`, `company_account_holder_snapshot`, `company_account_number_snapshot`, `company_bank_name_snapshot`, `company_bank_branch_snapshot`, `created_by_user_id`, `received_by_user_id`, `received_at`, `cancelled_by_user_id`, `cancelled_at`, `cancel_reason`, `note`, `created_at`, `updated_at`.

---

### `payment_voucher_attachments`

**Purpose:** Kế toán — ảnh/chứng từ scan đính kèm Phiếu chi.

**Tất cả cột:** `id`, `payment_voucher_id`, `file_name`, `file_url`, `file_type`, `uploaded_by`, `uploaded_at`.

---

### `payment_receipt_attachments`

**Purpose:** Kế toán — ảnh/chứng từ scan đính kèm Phiếu thu.

**Tất cả cột:** `id`, `payment_receipt_id`, `file_name`, `file_url`, `file_type`, `uploaded_by`, `uploaded_at`.

---

### `stock_voucher_attachments`

**Purpose:** Kho — file đính kèm phiếu kho (chứng từ scan). One row = 1 file.

**Tất cả cột:** `id`, `voucher_id`, `file_name`, `file_url`, `file_type`, `uploaded_by`, `uploaded_at`.

---

## Template for a new table (copy when adding one)

```markdown
### `table_name`

**Purpose:** <one line: what this table represents, one row = ?>

| Column  | Type (SQLAlchemy → SQLite / Postgres) | Key                  | Null     | Default        | Meaning                |
| ------- | ------------------------------------- | -------------------- | -------- | -------------- | ---------------------- |
| `id`    | `Integer` → `INTEGER` / `SERIAL`      | **PK**               | no       | auto-increment | Surrogate primary key. |
| `<col>` | `<type>`                              | <PK/FK→t.col/U/IX/—> | <yes/no> | <default/—>    | <meaning>              |

**Keys & indexes**

- Primary key: `<col>`.
- Foreign keys: `<col> FK→<table>.<col>` — <on-delete behavior if any>.
- Indexes: `<name>` on `<cols>` (<unique?> — <why>).

**Relationships**

- <how this table relates to others, e.g. "many `<rows>` belong to one `users`">.
```
