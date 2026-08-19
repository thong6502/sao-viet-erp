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
| `salary_mechanism` | `String(24)` → `VARCHAR(24)` | — | no | `'cung'` | Bộ nguyên tắc lương (Pha 1): cơ chế ra mức lương cho cả phòng — `cung` (ấn định tay), `bac_tho` (theo bậc thợ), `tham_nien` (theo thâm niên), `tham_nien_gioi_tinh` (theo thâm niên × giới tính). |
| `probation_ratio` | `Numeric(5,4)` → `NUMERIC(5,4)` | — | no | `0.80` | % lương thử việc của phòng (công ty dùng 0.80). |
| `has_piece_work` | `Boolean` → `BOOLEAN` | — | no | `false` | Phòng sản xuất có lương khoán theo sản lượng (nối engine khoán ở pha sau). |
| `la_san_xuat`  | `Boolean` → `BOOLEAN`                                  | —                             | no   | `false`        | Đánh dấu phòng ban thuộc khối SẢN XUẤT (spec-ke-hoach-san-xuat §13.1). Tick ở 1 nút cha ⇒ cả cây con (theo `parent_id`) coi như sản xuất; phân hệ Sản xuất liệt kê đúng subtree. "Effective sản xuất" = cột này true HOẶC có tổ tiên true (tính ở service, không cascade lưu). |
| `la_kinh_doanh` | `Boolean` → `BOOLEAN`                                 | —                             | no   | `false`        | Đánh dấu phòng ban thuộc khối KINH DOANH (mg 0181) — cùng luật kế thừa cây con như `la_san_xuat`: tick phòng cha ⇒ KD1/KD2 bên dưới cũng là kinh doanh. Trả lời "ai được giao phụ trách khách hàng": hộp chọn NV phụ trách ở màn Khách hàng đổ theo khối này, giao với phạm vi dữ liệu của người xem. **Chưa tick phòng nào ⇒ lùi về quy tắc "ai có quyền module `khach_hang`"** nên DB cũ không cần khai lại. |
| `created_at`   | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                             | no   | now (UTC)      | When the department row was created.                                                                                                                                                                                                                                           |

**Keys & indexes**

- Primary key: `id`.
- Unique index: `ix_departments_name` on `name`, `ix_departments_code` on `code`.
- Indexes: `ix_departments_parent_id` on `parent_id`, `ix_departments_level_id` on `level_id`.
- Foreign keys: `parent_id FK→departments.id` (self-reference); `level_id FK→unit_levels.id`; `head_user_id` is a logical reference to `users.id` (no enforced FK).

**`ca_lam_ids`** (`JSON`, nullable, mg 0178) — **DORMANT từ 10/08/2026**. Từng là tập ca riêng của TỔ; nay đã bỏ cùng ô ca ở màn Máy: ca khai MỘT chỗ duy nhất ở Nhân sự → Ca kíp (cờ `work_shifts.dung_cho_lich_may`), bàn xếp lịch dùng tập chung đó cho các bước KHÔNG có máy. Không còn ô nhập, không còn trong API, engine thôi đọc. Cột giữ lại để không mất số cũ (không có Alembic, `create_all` không ALTER) — **đừng khai lại ô này**.

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
| `can_view_log` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (cham_cong) — XEM tab "Nhật ký chấm công" (từng lượt bấm kèm giờ + toạ độ). Tách khỏi `can_read` (chỉ mở Bảng công tháng) qua migration 0181. |
| `can_adjust` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (nhan_su · Chấm công) — chấm bù / sửa công qua punch nguồn (`attendance_logs.is_manual`), tách khỏi `can_update`. Thêm qua migration 0015. |
| `can_approve_exception` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (don_hang_ban · A2) — DUYỆT "đơn đặc thù" (giá trị cao / biên thấp / dưới giá vốn), tách khỏi `can_approve` (= chốt đơn thường). CHỈ Giám đốc; Trưởng phòng KD giữ `_full` nhưng KHÔNG có quyền này. Thêm qua migration 0050. |
| `can_set_credit_terms` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (khach_hang) — THIẾT LẬP **chính sách tài chính** khách: hạn mức công nợ + điều khoản thanh toán + **chiết khấu min/max + biên lợi nhuận min/max** (redesign spec-06 v2 mở rộng nghĩa từ "điều khoản tín dụng"). Mọi số tài chính ai cũng XEM; chỉ quyền này mới SỬA. Quyết định "cho nợ/chiết khấu bao nhiêu" bàn NGOÀI ĐỜI — quyền chỉ gate ai NHẬP, KHÔNG phải bước duyệt. Thiếu quyền → các field tài chính bị BỎ QUA khi ghi (giữ nguyên / về default an toàn). Bật qua `_full` (GĐ/GĐ KD/TP KD). Thêm qua migration 0059. |
| `can_record_deposit` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (don_hang_ban) — GHI **phiếu thu cọc** (Kế toán). Tách khỏi CRUD đơn: NV KD lập đơn nhưng KHÔNG tự ghi cọc (tiền vào két là việc Kế toán). Gán vai Kế toán. Thêm qua migration 0067. |
| `can_assign_work` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (san_xuat) — tổ trưởng **GÁN thợ** vào công đoạn (`routing_step`) của lệnh đã phát. Người được gán mới hứng việc; chỉ vai có cờ này (hoặc scope department/all, hoặc trưởng tổ) mới thấy TOÀN BỘ lệnh của tổ + nút gán. Thêm qua migration 0081. |
| `can_record_output` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (san_xuat, Lát 2) — tổ trưởng **GHI SẢN LƯỢNG** đạt/hỏng cho bước của tổ (bảng `san_luong`, record-only, cộng dồn). Thêm qua migration 0087. |
| `can_handover` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (san_xuat, Lát 2) — tổ trưởng **BÀN GIAO** số sang tổ kế + **XÁC NHẬN NHẬN** (bảng `ban_giao`, 2 con dấu, lệch được). Thêm qua migration 0087. |
| `can_request` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (kho) — **TẠO ĐỀ NGHỊ** nhập/xuất. Tách khỏi `can_create` (= lập PHIẾU): người đề nghị không lập phiếu, thủ kho lập phiếu nhưng không tự đề nghị cho mình. Thêm qua migration 0092. |
| `can_view_stock` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (kho) — **XEM SỐ TỒN**. Thiếu quyền chỉ thấy đèn tín hiệu 4 màu, không thấy con số: người đề nghị biết "sắp hết" mà không lộ số liệu tồn. Thêm qua migration 0092. |
| `can_view_cost` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (kho) — **XEM GIÁ VỐN** và giá trị tồn. Tồn ai cũng xem được, giá vốn chỉ Kế toán + BGĐ. Thiếu quyền → API ẩn đơn giá/thành tiền và bản in cũng bỏ 2 cột đó. Thêm qua migration 0092. |
| `can_set_threshold` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (kho) — **KHAI NGƯỠNG** tồn / tối đa (`stock_thresholds`). Tách khỏi `can_update` vì đổi ngưỡng là đổi toàn bộ hệ cảnh báo mua hàng, không phải sửa dữ liệu thường. Thêm qua migration 0092. |
| `can_post` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (kho) — **GHI SỔ** phiếu (chốt tồn). Tách khỏi `can_create` (= lập phiếu nháp) để giữ SoD: thủ kho lập nháp, Kế toán kho ghi sổ — người ghi sổ khác người cầm hàng. Thêm qua migration 0098. |
| `can_close_book` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (kho) — **KHÓA KỲ** (chốt sổ) kế toán kho: xem **Báo cáo kho** + **export Excel MISA** + chốt/mở kỳ khóa sổ (`kho_khoa_so`). Chỉ Kế toán kho + Giám đốc. Thêm qua migration 0169. |
| `can_view_timesheet` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (cham_cong, mg 0194) — tab **Bảng công tháng**: lưới người × ngày của cả phạm vi, chứa nút Chốt kỳ công. Công cụ QUẢN LÝ, cùng hạng với Bảng lương — thợ mở màn Chấm công để bấm giờ nhưng không được thấy công cả xưởng. Tách khỏi `can_read` (nay = mở màn + ba tab của chính mình). |
| `can_approve_late_early` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (cham_cong, mg 0194) — tab con **Duyệt phiếu đi muộn / về sớm / nghỉ nửa buổi** của người khác (khai hộ = duyệt luôn). Gộp từ khoá `di_muon` cũ: nó vốn là một tab của màn này, không phải một màn riêng. |
| `can_manage_locations` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (cham_cong, mg 0194) — tab **Điểm chấm công**. Tách từ `can_update` ("Cấu hình chấm công") vốn mở một lúc ba tab. |
| `can_manage_shifts` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (cham_cong, mg 0194) — tab **Khai ca**. Tách từ `can_update`. |
| `can_manage_calendar` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (cham_cong, mg 0194) — tab **Lịch & Ngày lễ**. Tách từ `can_update`. |
| `can_view_payroll_table` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (luong, mg 0195) — tab **Bảng lương tháng**: danh sách lương cả phạm vi kèm nút Tính lại · Chốt kỳ · Đánh dấu đã chi. Công cụ QUẢN LÝ, cùng hạng với `can_view_timesheet` bên Chấm công. Trước 15/08/2026 nó đi theo `can_read`, nên cấp ô Lương ở phạm vi *Của tôi* là thợ vẫn mở được bảng lương. |
| `can_manage_salary_profiles` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (luong, mg 0196) — tab **Lương nhân viên** (hồ sơ lương từng người). Tách khỏi cột Thao tác: cột đó nay chỉ cho GHI, không mở tab nào. |
| `can_manage_piece_rates` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (luong, mg 0196) — tab **Lương khoán** (đơn giá khoán theo tổ/công việc). Tách khỏi cột Thao tác. |
| `can_manage_leave_types` | `Boolean` → `BOOLEAN` | — | no | `false` | Quyền chi tiết (nghi_phep, mg 0197) — **danh mục loại nghỉ** (phép năm, nghỉ ốm, không lương…), chính sách dùng chung cả công ty. Trước đó nó mượn chính cột `can_update`, mà `can_update` là một trong ba cột nút *Thao tác* bật cùng lúc ⇒ bật Thao tác là ô này TỰ SÁNG THEO, mở luôn quyền sửa chính sách nghỉ của cả nhà máy. |

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
| `repeat_freq`      | `String(8)` → `VARCHAR(8)`                             | —                                     | no   | `none`         | Lịch lặp `none`/`day`/`week`/`month`; `none` = hẹn đơn lẻ. Migration 0077. |
| `repeat_interval`  | `Integer` → `INTEGER`                                  | —                                     | no   | `1`            | Lặp mỗi N đơn vị theo `repeat_freq`. Migration 0077.            |
| `repeat_until`     | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                     | yes  | —              | Lặp đến hết ngày này (null = không giới hạn; bung có cap chân trời). Migration 0077. |
| `series_id`        | `Integer` → `INTEGER`                                  | **IX**                                | yes  | —              | Dòng ngoại-lệ trỏ về id hẹn-đầu-chuỗi (soft, cùng bảng). Migration 0077. |
| `occurrence_date`  | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                     | yes  | —              | (Ngoại lệ) thay cho lần nào của chuỗi. Migration 0077.          |
| `created_by`       | `Integer` → `INTEGER`                                  | **FK→users.id**                       | yes  | —              | Người tạo việc.                                                  |
| `created_at`       | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                     | no   | now (UTC)      | Thời điểm tạo.                                                   |

**Keys & indexes**

- Primary key: `id`. Indexes: `ix_customer_care_tasks_customer_id`, `ix_customer_care_tasks_status`, `ix_customer_care_tasks_assignee_user_id`, `ix_customer_care_tasks_series_id`.
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

### `quotes`

**Purpose:** Báo giá header — mô hình **Header-Version-Item (H-V-I)** thay bảng `quotations`
phẳng cũ (bảng cũ còn trong dev.db như orphan, model đã gỡ). Header giữ danh tính phiếu
(`quote_number` BG26-xxxx duy nhất), khách hàng, trạng thái lifecycle
`draft → sent → accepted/rejected/expired → converted_to_order` (+ `cancelled`), và con trỏ
`current_version_id` tới phiên bản đang hiệu lực. Nội dung giá nằm ở `quote_versions` /
`quote_items`. Nguồn DUY NHẤT = 1 **Phiếu tính giá** (`phieu_tinh_gia_id`), mỗi "sản phẩm"
(`PhieuThanhPhan`) thành 1 dòng — đường Estimate cũ đã gỡ hẳn ở migration 0173.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | Surrogate primary key. |
| `quote_number` | `String(20)` | **UQ**, **IX** | no | — | Mã phiếu (BG26-0001…) — duy nhất; version nằm ở `quote_versions.version_number`. |
| `customer_id` | `Integer` | **FK→customers.id** (SET NULL), **IX** | yes | — | Khách hàng (SEAM-14 CRM read). |
| `customer_name_snapshot` | `String(255)` | — | yes | — | Tên KH chốt tại thời điểm tạo (copy-on-write hiển thị). |
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
copy-on-write: `internal_cost_snapshot_json` (phân rã giá vốn theo các dòng đã khóa lúc tạo)
— sửa Phiếu tính giá sau này không rewrite phiếu đã gửi (P0 §34).

| Column                          | Type            | Key                                | Null | Default | Meaning                                                                 |
| ------------------------------- | --------------- | ---------------------------------- | ---- | ------- | ----------------------------------------------------------------------- |
| `id`                            | `Integer`       | **PK**                             | no   | auto    | PK.                                                                     |
| `quote_id`                      | `Integer`       | **FK→quotes.id** (CASCADE), **IX** | no   | —       | Header cha.                                                             |
| `version_number`                | `Integer`       | —                                  | no   | `1`     | v1, v2… trong 1 quote.                                                  |
| `status`                        | `String(20)`    | —                                  | no   | `draft` | draft/locked/sent/accepted/rejected/superseded/cancelled (per-version). |
| `change_reason`                 | `String(255)`   | —                                  | yes  | —       | "Lý do/ghi chú phiên bản này" (đổi giấy, khách ép giá…).                |
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

**Purpose:** một dòng hàng của version — **mỗi dòng = 1 "sản phẩm" (`PhieuThanhPhan`) của
Phiếu tính giá nguồn** (báo giá không soạn tay). Giá vốn đóng băng per dòng
(`total_cost_snapshot`); markup/VAT per dòng.

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `quote_version_id` | `Integer` | **FK→quote_versions.id** (CASCADE), **IX** | no | — | Version cha. |
| `phieu_thanh_phan_id` | `Integer` → `INTEGER` | (soft) | yes | — | **BG-1**: dòng báo giá nguồn từ 1 "sản phẩm" (`PhieuThanhPhan`) của PTG. Soft ref. Migration 0051. |
| `nhom` | `String(120)` → `VARCHAR(120)` | — | yes | — | Nhãn NHÓM GỘP KHI IN (migration 0111) — đông cứng từ `phieu_thanh_phan.nhom_bao_gia` lúc tạo dòng. Bản in gửi khách gom các dòng cùng nhãn thành 1 dòng (ruột + bìa → "quyển sách"); dữ liệu vẫn 1 dòng/thành phần. |
| `line_no` | `Integer` | — | no | — | Thứ tự dòng. |
| `po_code` | `String(60)` | — | yes | — | Mã PO của khách cho dòng (cột "MÃ PO" mẫu báo giá thật). Migration 0052. |
| `product_type` | `String(50)` | — | no | — | Loại SP (snapshot từ phiếu). |
| `product_name` | `String(255)` | — | no | — | Tên SP (snapshot). |
| `product_spec_text` | `String(1000)` | — | yes | — | Spec đọc được ("21×29,7 cm · 4 màu/2 mặt"). |
| `dien_giai` | `Text` | — | yes | — | Diễn giải quy cách IN RA báo giá dưới tên SP — mỗi dòng = 1 gạch đầu dòng (khổ · giấy · in · gia công). Máy bung từ `PhieuThanhPhan` lúc TẠO dòng rồi ĐÔNG CỨNG (sửa PTG về sau không đổi bản đã gửi; đồng bộ lại → version mới bung lại). Người soạn sửa/bổ sung được (bồi sóng, đục lỗ… máy không suy ra nổi). Migration 0106. |
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
| `accepted` | `Boolean` → `BOOLEAN` | — | no | `false` | Khách chốt MỘT PHẦN: True = khách ưng dòng (kéo lên đơn), False = không lấy (giữ vết). Chỉ có nghĩa sau khi báo giá `accepted`. Đơn kéo dòng True (0 True → kéo tất cả, tương thích cũ). Migration 0091. |

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
| `is_rush` | `Boolean` → `BOOLEAN` | — | no | `false` | Đơn GẤP/ưu tiên — Sale bật để xưởng làm trước (chip đỏ + chảy xuống LSX). Migration 0076. |
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
| `delivery_contact_name` | `String(255)` → `VARCHAR(255)` | — | yes | — | Người nhận hàng (snapshot, Sale xổ từ danh bạ khách — KHÔNG auto-fill is_primary). Migration 0076. |
| `delivery_contact_phone` | `String(30)` → `VARCHAR(30)` | — | yes | — | SĐT người nhận hàng. Migration 0076. |
| `delivery_note` | `String(500)` → `VARCHAR(500)` | — | yes | — | Lưu ý GIAO HÀNG → tài xế/khâu Giao ("giao giờ HC", "gọi trước 30'"). Migration 0076. |
| `production_note` | `String(500)` → `VARCHAR(500)` | — | yes | — | Lưu ý SẢN XUẤT → tổ in/LSX ("in đúng màu mẫu lần trước"). Migration 0076. |
| `invoice_entity_name` | `String(255)` → `VARCHAR(255)` | — | yes | — | Pháp nhân xuất HĐ (khi khách xin tên khác; mặc định = khách). |
| `invoice_entity_tax_code` | `String(20)` → `VARCHAR(20)` | — | yes | — | MST pháp nhân xuất HĐ. |
| `deposit_pct` | `Float` → `FLOAT` | — | yes | — | % cọc phải thu ĐẶT TẠI ĐƠN (Kế toán/`record_deposit`, khóa khỏi Sale) — base cổng chốt; NULL = chưa đặt. |
| `cost_basis` | `String(16)` → `VARCHAR(16)` | — | no | `quote` | Nguồn giá vốn ∈ {quote, none}; none = nhập tay → biên "không xác định". |
| `needs_approval` | `Boolean` → `BOOLEAN` | — | no | `false` | Đơn cần duyệt tại đơn (nhập tay / bổ sung tự đặt giá). |
| `approval_state` | `String(16)` → `VARCHAR(16)` | — | no | `none` | Trình-duyệt ∈ {none, pending, approved, rejected}. |
| `ordered_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Đóng dấu lúc chốt đơn (P4). |
| `ordered_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Người chốt đơn. |
| `san_xuat_released_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Sale bấm "Chuyển xuống sản xuất" (sau chốt, đủ cọc) → đơn vào hàng chờ kế hoạch. NULL = chưa chuyển (migration `0078`). |
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
| `don_vi_tinh`         | `String(30)` → `VARCHAR(30)`          | —                        | no   | `'cái'`        | ĐVT dòng (migration 0076) — kéo từ báo giá (`quote_items.unit`) / gõ tay đơn nhập tay. |
| `nhom`                | `String(120)` → `VARCHAR(120)`        | —                        | yes  | —              | Nhãn NHÓM GỘP KHI IN (migration 0112) — copy từ `quote_items.nhom`. Bản in xác nhận đơn gom dòng cùng nhãn thành 1 dòng, khớp bản báo giá. KHÔNG ảnh hưởng sản xuất (1 dòng đơn = 1 lệnh). |
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
| `job_grade_id`            | `Integer` → `INTEGER`                                  | **FK→job_grades.id**, **IX**   | yes  | —              | **BẬC TAY NGHỀ — nguồn sự thật DUY NHẤT** (chủ 29/07/2026). Trỏ danh mục `job_grades`. Chỉ đổi qua TRANSITION (`promote`/`transfer`), KHÔNG qua sửa hồ sơ thường ⇒ mọi lần đổi bậc đều có dòng Quá trình công tác. NULL = chưa khai bậc. Thêm qua migration 0127. |
| `job_grade`               | `String(50)` → `VARCHAR(50)`                           | —                              | yes  | —              | ⚠️ **CỘT CŨ — NGỪNG GHI từ 29/07/2026.** Bậc thợ chữ tự do (vd "3/7"). Migration 0127 đã chuyển sang `job_grade_id`; cột giữ cho dữ liệu cũ, chỉ đọc khi `job_grade_id` NULL. |
| `prior_seniority_months`  | `Integer` → `INTEGER`                                  | —                              | no   | `0`            | Thâm niên đã có TRƯỚC khi vào làm (tháng); tổng thâm niên = số này + thời gian từ `hire_date`. Đợt 1 chỉ lưu/hiển thị. Thêm qua migration 0093. |
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
| `pit_mode`                | `String(16)` → `VARCHAR(16)`                           | —                              | no   | `luy_tien`     | **Cách tính TNCN của NGƯỜI này** — MỘT ô 3 giá trị thay vì 2 cờ (2 cờ = 4 tổ hợp, có 1 tổ hợp vô nghĩa = chỗ để dữ liệu lệch). `luy_tien` HĐ từ 3 tháng: bảng luỹ tiến + giảm trừ gia cảnh (mặc định) · `khau_tru_10` HĐ dưới 3 tháng/thời vụ/thực tập: khấu trừ 10% tại nguồn, KHÔNG luỹ tiến, KHÔNG giảm trừ · `cam_ket_08` đã làm cam kết 08/CK-TNCN ⇒ không khấu trừ. Thêm qua migration 0120. |
| `bank_account`            | `String(30)` → `VARCHAR(30)`                           | —                              | yes  | —              | Số tài khoản ngân hàng (chi lương).                                                                                 |
| `bank_name`               | `String(100)` → `VARCHAR(100)`                         | —                              | yes  | —              | Ngân hàng.                                                                                                          |
| `default_shift_id`        | `Integer` → `INTEGER`                                  | **IX**                         | yes  | —              | Ca làm việc mặc định (logical link → `work_shifts.id`, không FK cứng). Null = chưa gán ca. Thêm qua migration 0011. |
| `payroll_group`           | `String(40)` → `VARCHAR(40)`                           | **IX**                         | yes  | —              | Nhóm lương — trục tra `salary_rate_rules` (vd `to_in`, `san_xuat`, `van_phong`). Thêm qua migration 0012.           |
| `pay_grade_key`           | `String(20)` → `VARCHAR(20)`                           | —                              | yes  | —              | ⚠️ **CỘT CŨ — NGỪNG GHI từ 29/07/2026** (đã gỡ khỏi `EDITABLE_FIELDS`). Bậc lương chuẩn hóa `tho_1`..`phu_2`. Bộ mã này nay **là** danh mục `job_grades` (cùng mã) và bậc của NV nằm ở `job_grade_id`. Giữ cột cho dữ liệu cũ. Thêm qua migration 0012. |
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

### `employee_shift_assignments`

**Purpose:** ca làm việc MẶC ĐỊNH của nhân viên tại một mốc hiệu lực (module `nhan_su`). Đổi
ca = thêm mốc mới; khoảng kết thúc của mốc suy ra bằng ngày liền trước mốc kế tiếp (giống
`employee_salaries`). `shift_id = NULL` = bỏ gán ca từ ngày hiệu lực. Bảng do `create_all` tạo.

| Column           | Type (SQLAlchemy → SQLite / Postgres)                  | Key                         | Null | Default        | Meaning                                            |
| ---------------- | ------------------------------------------------------ | --------------------------- | ---- | -------------- | -------------------------------------------------- |
| `id`             | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                      | no   | auto-increment | Surrogate primary key.                             |
| `employee_id`    | `Integer` → `INTEGER`                                  | **FK→employees.id**, **IX** | no   | —              | Nhân viên chủ; `ON DELETE CASCADE`.                |
| `shift_id`       | `Integer` → `INTEGER`                                  | **IX**                      | yes  | —              | Soft-ref `work_shifts.id`; NULL = không gán ca.    |
| `effective_from` | `Date` → `DATE`                                        | **IX**                      | no   | —              | Hiệu lực từ.                                       |
| `created_by`     | `Integer` → `INTEGER`                                  | **FK→users.id**             | yes  | —              | Người gán.                                         |
| `created_at`     | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                           | no   | now (UTC)      | Khi ghi máy.                                       |

**Keys & indexes**

- Primary key: `id`. Unique: `(employee_id, effective_from)` — `uq_employee_shift_effective`.

---

### `employee_shift_days`

**Purpose:** ca của nhân viên tại MỘT NGÀY cụ thể — lớp **đè** lên ca mặc định theo mốc
(`employee_shift_assignments`). Dùng cho xoay ca linh hoạt (hôm nay ca khuya, mai ca ngày), khai
bằng lưới NV × ngày ở tab "Khai ca". Mỗi ngày công vẫn **chỉ 1 ca** — `(employee_id, work_date)`
UNIQUE là hàng rào cứng; làm ngoài khung ca là TĂNG CA (module riêng), không phải ca thứ hai.
Ba trạng thái một ô lưới: **không có dòng** = kế thừa ca mặc định · **có `shift_id`** = ca cụ thể ·
**`is_off=True`** = nghỉ theo lịch. `is_off` chỉ là dấu KẾ HOẠCH: KHÔNG chặn chấm công và KHÔNG
sinh hệ số lương (đi làm ngày nghỉ riêng vẫn hưởng 1× như ngày thường; chủ nhật vẫn theo luật nghỉ
tuần chung), nên `shift_id_on()` cố ý bỏ qua dòng `is_off` và rơi xuống ca nền. Bảng do `create_all` tạo.

| Column        | Type (SQLAlchemy → SQLite / Postgres)                  | Key                         | Null | Default        | Meaning                                              |
| ------------- | ------------------------------------------------------ | --------------------------- | ---- | -------------- | ---------------------------------------------------- |
| `id`          | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                      | no   | auto-increment | Surrogate primary key.                               |
| `employee_id` | `Integer` → `INTEGER`                                  | **FK→employees.id**, **IX** | no   | —              | Nhân viên chủ; `ON DELETE CASCADE`.                  |
| `work_date`   | `Date` → `DATE`                                        | **IX**                      | no   | —              | NGÀY CÔNG (cùng trục `work_day_of`), không phải ngày lịch của lượt bấm. |
| `shift_id`    | `Integer` → `INTEGER`                                  | **IX**                      | yes  | —              | Soft-ref `work_shifts.id`; NULL đi kèm `is_off` = nghỉ theo lịch. |
| `is_off`      | `Boolean` → `BOOLEAN`                                  | —                           | no   | `false`        | Nghỉ luân phiên theo lịch — dấu kế hoạch, không ra tiền. |
| `created_by`  | `Integer` → `INTEGER`                                  | **FK→users.id**             | yes  | —              | Người khai ca.                                       |
| `created_at`  | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                           | no   | now (UTC)      | Khi ghi máy.                                         |

**Keys & indexes**

- Primary key: `id`. Unique: `(employee_id, work_date)` — `uq_employee_shift_day`.

---

### `employee_shift_change_logs`

**Purpose:** LỊCH SỬ mọi lần ca của một người bị đổi — **và** hộp thư báo cho chính người đó
(chủ 28/07/2026). Hai bảng ca kia đều **ghi đè** nên giá trị cũ mất hẳn, còn `audit_logs` chỉ có
một dòng gộp kiểu *"3 ô khai, 1 ô về mặc định"* — không biết ô nào, từ ca gì sang ca gì.

⚠️ **Ca đến từ HAI lớp và có 5 đường ghi.** Quên móc một đường là màn lịch sử báo *"không có thay
đổi nào"* trong khi ca vừa bị đổi — sai kiểu đó tệ hơn là không có màn lịch sử:
`set_shift_plan` (lưới) · `set_default_shift` · `set_default_shift_bulk` · `update_employee` ·
`delete_shift_assignment`. Tất cả đi qua **một** hàm `EmployeeRepository.log_shift_change()`, và hàm
đó tự bỏ qua khi **trước == sau** (lưới hay được bấm Lưu cả tháng — không lọc là đẻ hàng chục dòng
rỗng + ngần ấy thông báo rác). `create_employee` **cố ý không ghi**: gán ca lần đầu chưa có ca cũ để
so. Bảng do `create_all` tạo (không migration).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| ------ | ------------------------------------- | --- | ---- | ------- | ------- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `employee_id` | `Integer` → `INTEGER` | **FK→employees.id**, **IX** | no | — | Nhân viên bị đổi ca; `ON DELETE CASCADE`. |
| `kind` | `String(8)` → `VARCHAR(8)` | — | no | — | `day` = ô một ngày trên lưới · `base` = ca nền theo mốc hiệu lực. Trục tách 2 lớp trên màn. |
| `origin` | `String(16)` → `VARCHAR(16)` | — | no | — | Thao tác đến từ màn nào: `grid` · `base_panel` · `base_bulk` · `profile` · `base_remove`. |
| `action` | `String(8)` → `VARCHAR(8)` | — | no | — | `set` · `off` · `inherit` · `remove`. |
| `apply_date` | `Date` → `DATE` | **IX** | no | — | `kind=day` → NGÀY CÔNG bị đổi. `kind=base` → `effective_from` của mốc (áp từ ngày này **trở về sau**). |
| `shift_id_before` | `Integer` → `INTEGER` | — | yes | — | Soft-ref `work_shifts.id` TRƯỚC khi sửa; NULL = không có ca. |
| `shift_id_after` | `Integer` → `INTEGER` | — | yes | — | Soft-ref `work_shifts.id` SAU khi sửa. |
| `is_off_before` | `Boolean` → `BOOLEAN` | — | no | `false` | Ô "Nghỉ theo lịch" trước khi sửa — chỉ có nghĩa với `kind=day`. |
| `is_off_after` | `Boolean` → `BOOLEAN` | — | no | `false` | Ô "Nghỉ theo lịch" sau khi sửa. |
| `inherited_before` | `Boolean` → `BOOLEAN` | — | no | `false` | `kind=day`: TRƯỚC đó ô đang **kế thừa ca nền** (chưa ai khai tay ngày này). Đây là chỗ trả lời "ca này do nền hay do người sửa" — nuôi icon cây bút trên lưới. |
| `actor_user_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | yes | — | Ai sửa. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | **IX** | no | now (UTC) | Sửa lúc nào. |
| `notified_user_id` | `Integer` → `INTEGER` | **IX** | yes | — | Tài khoản đã đẩy thông báo tới. **NULL = NV không có tài khoản đăng nhập** (công nhân xưởng) ⇒ không báo được cho ai; màn Khai ca đếm số này ra dòng *"N người chưa báo được"*. |
| `seen_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Người nhận đã đọc lúc nào. NULL = chưa đọc ⇒ nuôi badge. |

**Keys & indexes**

- Primary key: `id`. Index: `employee_id`, `apply_date`, `created_at`, `actor_user_id`,
  `notified_user_id`. Không UNIQUE — một ngày có thể bị sửa nhiều lần, mỗi lần một dòng.

---

### `job_grades`

**Purpose:** danh mục **BẬC TAY NGHỀ** cho khối SẢN XUẤT (chủ 29/07/2026). Bộ chủ chốt:
**5 bậc chính — Bậc 1 → Bậc 5**, trong đó **Bậc 1 là bậc cao nhất**. (Bản đầu trong ngày là 3
chính + 2 phụ `tho_*`/`phu_*`; chủ chốt lại bỏ bậc phụ ⇒ **migration 0129** đổi tên TẠI CHỖ, giữ
nguyên `id` nên ai đang mang bậc không bị mất.)

🚫 **KHAI BẬC THÔI — KHÔNG có tiền, KHÔNG có hệ số.** Bảng cố ý chỉ có mã · tên · thứ tự · bật/tắt;
gán bậc cho một người **không làm đổi một đồng nào** trên bảng lương (có test chốt). Khi nào cần
chia sản lượng khoán theo bậc thì treo cột vào ĐÂY, không phải đi sửa hồ sơ từng người — đó là lý
do bậc là một BẢNG có id chứ không phải ô chữ.

Trước 29/07/2026 bậc nằm ở **hai** cột song song, không cột nào dùng để tính được: `employees.job_grade`
(chữ tự do "3/7") và `employees.pay_grade_key` (chuẩn hoá nhưng không có màn). Migration 0127 gom
cả hai về một mối — nay chỉ còn `employees.job_grade_id` là nguồn sự thật. Bảng do `create_all` tạo (không migration); dữ liệu seed
+ backfill nằm ở **migration 0127**.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| ------ | ------------------------------------- | --- | ---- | ------- | ------- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `code` | `String(20)` → `VARCHAR(20)` | **UQ**, **IX** | no | — | Mã ổn định `bac_1`…`bac_5`. Bộ `pay_grade_key` CŨ (`tho_1`…`phu_2`) được migration 0127 **ánh xạ** sang đây khi backfill (theo mức lương giảm dần: `phu_1`→Bậc 4, `phu_2`→Bậc 5). Bậc do migration tự sinh từ chữ cũ lạ mang mã `cu_<n>`. |
| `name` | `String(60)` → `VARCHAR(60)` | — | no | — | Tên hiển thị ("Bậc 1", "Phụ 2"). Chủ sửa được. |
| `seq` | `Integer` → `INTEGER` | — | no | `0` | Thứ tự hiển thị. Số **NHỎ = bậc CAO** (Bậc 1 đứng đầu). |
| `is_active` | `Boolean` → `BOOLEAN` | — | no | `true` | Tắt thay vì xoá khi một bậc thôi dùng — hồ sơ cũ đang trỏ vào vẫn đọc được tên bậc. Bậc tự sinh từ dữ liệu cũ vào với `false` để danh sách chọn vẫn sạch 5 bậc. |
| `note` | `String(255)` → `VARCHAR(255)` | — | yes | — | Ghi chú. Bậc tự sinh mang ghi chú *"Tự sinh từ dữ liệu cũ — soát lại rồi gộp hoặc bật"*. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Ngày tạo. |

**Keys & indexes**

- Primary key: `id`. UNIQUE + index: `code`. Được `employees.job_grade_id` tham chiếu.

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

### `noi_quy_records`

**Purpose:** danh mục tài liệu nội quy hiện hành. Mỗi dòng là một file độc lập; module chỉ có
ba thao tác nghiệp vụ **Xem / Thêm / Xóa**, không có nháp, sửa nội dung hay ban hành phiên bản.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| ------ | ------------------------------------- | --- | ---- | ------- | ------- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Khóa chính nội bộ. |
| `code` | `String(24)` → `VARCHAR(24)` | **UQ, IX** | no | sinh tự động | Mã truy vết dạng `NQ-YYMMDD-XXXX`. |
| `name` | `String(200)` → `VARCHAR(200)` | — | no | — | Tên tài liệu. |
| `file_name` | `String(255)` → `VARCHAR(255)` | — | no | — | Tên file hiển thị. |
| `file_url` | `String(500)` → `VARCHAR(500)` | — | no | — | File riêng tư trong `/api/files/noi-quy/...`. |
| `file_type` | `String(100)` → `VARCHAR(100)` | — | no | — | MIME đã kiểm tra bằng chữ ký file; chỉ PDF/PNG/JPEG/WebP. |
| `file_size` | `Integer` → `INTEGER` | — | no | `0` | Dung lượng byte. |
| `note` | `String(500)` → `VARCHAR(500)` | — | yes | — | Ghi chú tùy chọn. |
| `uploaded_by` | `Integer` → `INTEGER` | **FK→users.id, IX** | no | — | Người tải tài liệu lên. |
| `uploaded_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | **IX** | no | now (UTC) | Thời điểm tải lên. |

Các bảng `noi_quy_documents`, `noi_quy_versions`, `noi_quy_attachments`, `noi_quy_pages` phía
dưới là dữ liệu **legacy** của luồng soạn thảo/ban hành cũ; được giữ để không làm mất dữ liệu DB.
API hiện hành không ghi vào các bảng đó.

---

### `noi_quy_documents` (legacy)

**Purpose:** **MỘT tài liệu trong bộ nội quy** — danh tính bền, sống qua mọi lần ban hành
(chủ 30/07/2026 — *"upload được nhiều file, mỗi file đi theo title, bấm title thì mở ra bên trái"*).

Bộ nội quy một nhà máy thường là **nhiều văn bản**: Nội quy lao động, Quy chế lương thưởng, An toàn
lao động, Các lỗi thường gặp… Mỗi cái một file, **một vòng đời riêng**: sửa "Các lỗi thường gặp" thì
"Nội quy lao động" giữ nguyên ngày ban hành cũ. Mỗi tài liệu là một **chuỗi version riêng** qua
`noi_quy_versions.document_id`.

⚠️ **KHÔNG có đường xoá tài liệu.** `noi_quy_pages` và `noi_quy_attachments` đều `ondelete=CASCADE`
theo version ⇒ xoá một tài liệu là bay toàn bộ lịch sử + ảnh trang + hàng file chỉ bằng một cú bấm.
Thôi dùng thì đặt `is_active=false`; bản cũ vẫn tra được vì *"hồi tháng 5 luật là gì"* là câu phải
trả lời được.

Bảng do `create_all` tạo (**không migration** — bảng mới).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| ------ | ------------------------------------- | --- | ---- | ------- | ------- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `title` | `String(200)` → `VARCHAR(200)` | — | no | — | Tên **HIỆN HÀNH**, dùng hiện danh sách bên phải. Tiêu đề của từng bản đã ban hành được chụp riêng ở `noi_quy_versions.title`. |
| `seq` | `Integer` → `INTEGER` | — | no | `1` | Thứ tự hiện trong danh sách. |
| `is_active` | `Boolean` → `BOOLEAN` | — | no | `true` | `false` = thôi áp dụng: mất khỏi danh sách nhân viên và khỏi bản hiệu lực, **nhưng KHÔNG mất khỏi lịch sử**. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Ngày tạo tài liệu. |

**Keys & indexes**

- Primary key: `id`. Không FK ra ngoài.

---

### `noi_quy_versions`

**Purpose:** **NỘI QUY CÔNG TY** (chủ 30/07/2026 — *"chỗ để Giám đốc viết nội quy, tất cả nhân viên
thấy"*). Mỗi lần ban hành là **MỘT dòng mới, KHÔNG ghi đè** bản cũ.

**Vì sao versioned:** nội quy là căn cứ kỷ luật. Sửa đè thì sau này không ai trả lời được *"hồi
tháng 5 luật là gì"* — mà lúc cần câu trả lời đó thường là lúc đang tranh chấp. Cùng khuôn
`employee_salaries`: thêm bản ghi, giữ lịch sử.

**Nháp vs Ban hành:** Giám đốc sửa trên bản `draft` (chỉ mình thấy); bấm ban hành thì thành
`published` và bản cũ lùi thành lịch sử. Thiếu bước này là cả công ty đọc nội quy viết dở.
Bản đang hiệu lực = `published` có `published_at` MỚI NHẤT.

Bảng do `create_all` tạo; cột `source_kind` thêm sau bằng **migration `0131`**.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| ------ | ------------------------------------- | --- | ---- | ------- | ------- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `document_id` | `Integer` → `INTEGER` | **FK→noi_quy_documents.id**, **IX** | yes | — | Tài liệu chứa bản này. **FK TRƠN, CỐ Ý KHÔNG cascade**: xoá lạc một tài liệu thì phải NỔ, không được âm thầm kéo theo cả lịch sử ban hành. Nullable vì cột thêm sau bằng migration `0132` (Postgres từ chối `ADD COLUMN NOT NULL` không default trên bảng đã có dòng); sau backfill thì mọi dòng đều có giá trị. |
| `title` | `String(200)` → `VARCHAR(200)` | — | yes | — | **BẢN CHỤP tiêu đề lúc ban hành**. Vì sao không đọc thẳng `noi_quy_documents.title`: đổi tên tài liệu khi đó sẽ viết lại tiêu đề của MỌI bản lịch sử — đúng thứ mà kiến trúc append-only này dựng ra để chống. Thêm bằng migration `0132`. |
| `noi_dung` | `Text` → `TEXT` | — | no | `""` | Toàn văn nội quy dạng **HTML đã lọc allowlist ở SERVER** (`lam_sach_html` — nh3): chỉ thẻ cấu trúc + định dạng chữ, `<img src>` chỉ được trỏ vào `/api/files/`. Lọc ở server mới là chốt thật (DOMPurify phía trình duyệt chỉ là lớp hai) vì nội quy do MỘT người ghi nhưng MỌI nhân viên render. Với `source_kind='file'` mà bản gốc là PDF thì cột này **trống** — nội dung nằm ở `noi_quy_pages`. |
| `source_kind` | `String(8)` → `VARCHAR(8)` | — | no | `html` | Nguồn của bản này: `html` (Giám đốc gõ/sửa trong app) · `file` (tải Word/PDF lên, hiện đúng bản gốc để **giữ nguyên dáng chữ**). Mỗi bản khai đúng MỘT nguồn — để cả hai cùng sống trên một bản thì sớm muộn lệch nhau và không ai biết bản nào đang là luật. |
| `ghi_chu` | `String(255)` → `VARCHAR(255)` | — | yes | — | "Bản này sửa gì" — để người đọc lịch sử khỏi phải so từng chữ. |
| `status` | `String(12)` → `VARCHAR(12)` | **IX** | no | `draft` | `draft` (chỉ người soạn thấy) · `published` (mọi nhân viên thấy). |
| `published_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | **IX** | yes | — | Ban hành lúc nào. **NULL = vẫn là nháp**, nhân viên KHÔNG thấy. Bản hiệu lực là bản `published` có giá trị này lớn nhất. |
| `published_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Ai ban hành (hiện chỉ Giám đốc có quyền). |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Ngày tạo bản nháp. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Lần sửa gần nhất (`onupdate`). |

**Keys & indexes**

- Primary key: `id`. Index: `status`, `published_at`. FK: `published_by → users.id`.

---

### `noi_quy_attachments`

**Purpose:** file đính kèm của **MỘT bản nội quy** — thường là bản PDF/Word đã ký, đóng dấu (nội
quy lao động trên 10 người phải đăng ký với Sở, bản gốc có dấu vẫn cần giữ). Gắn vào version chứ
không phải "toàn cục": bản scan có dấu là của đúng bản nội quy đó.

⚠️ **Bytes nằm dưới thư mục `noi-quy/`** của kho file chung, và thư mục này **CỐ Ý không khai
trong `_PREFIX_PERMISSION`** (`routers/files.py`) ⇒ ai đăng nhập cũng tải được, giống `avatars/`.
Thêm nó vào bảng đó là **chỉ Giám đốc mở được file** — phá đúng yêu cầu "tất cả nhân viên thấy".
Có test canh chuyện này.

Bảng do `create_all` tạo; cột `is_import_source` thêm sau bằng **migration `0131`**.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| ------ | ------------------------------------- | --- | ---- | ------- | ------- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `version_id` | `Integer` → `INTEGER` | **FK→noi_quy_versions.id**, **IX** | no | — | Bản nội quy chứa file này; `ON DELETE CASCADE`. |
| `file_name` | `String(255)` → `VARCHAR(255)` | — | no | — | Tên file gốc để hiển thị/tải về. |
| `file_url` | `String(500)` → `VARCHAR(500)` | — | no | — | Đường dẫn `/api/files/noi-quy/...`. |
| `file_type` | `String(100)` → `VARCHAR(100)` | — | yes | — | MIME type. |
| `is_import_source` | `Boolean` → `BOOLEAN` | — | no | `false` | `true` = file **GỐC của lần nhập/tải nội dung**, do hệ thống tự đính. Nhập lại thì hàng này bị **THAY, không cộng dồn**: nhập 3 lần mà để lại 3 file gần giống nhau thì lúc tranh chấp không ai biết bản nào là bản thật. File do người dùng tự bấm "Đính kèm" giữ `false` và **không bao giờ bị thay**. |
| `uploaded_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Ai tải lên. |
| `uploaded_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Tải lên lúc nào. |

**Keys & indexes**

- Primary key: `id`. Index: `version_id`. FK: `version_id → noi_quy_versions.id`
  (`ON DELETE CASCADE`), `uploaded_by → users.id`.

---

### `noi_quy_pages`

**Purpose:** **MỘT trang của bản nội quy dạng PDF, đã dựng thành ảnh** (chủ 30/07/2026 — *"nếu họ
đưa pdf hoặc word lên thì… form chữ kiểu chữ dáng chữ vẫn giữ nguyên"*).

**Vì sao dựng ảnh thay vì tách chữ:** PDF **không lưu đoạn văn hay kiểu chữ**, chỉ lưu vị trí từng
chữ trên trang — tách chữ ra là mất sạch dáng. Muốn giữ nguyên dáng thì cách duy nhất đúng là hiện
chính trang đó. Kèm lợi ích lớn: **bản SCAN đã ký, đóng dấu đỏ cũng dùng được**, không cần OCR.

**Dựng MỘT LẦN lúc ban hành**, không dựng lúc đọc — dựng khi đọc thì mỗi nhân viên mở màn là server
giải mã lại cả tập PDF. Dùng `pypdfium2` (Apache/BSD, bọc PDFium của Google) + `Pillow`; **cố ý
không dùng `PyMuPDF`** vì nó AGPL-3.0 hoặc phải trả phí bản quyền, và AGPL áp cả khi chỉ chạy làm
dịch vụ web nội bộ.

⚠️ Ảnh nằm dưới thư mục **`noi-quy/`** của kho file chung — cùng lý do như `noi_quy_attachments`:
thư mục này **CỐ Ý không khai trong `_PREFIX_PERMISSION`** nên mọi nhân viên tải được. Thêm vào bảng
đó là **cả công ty không xem được nội quy**.

Bảng do `create_all` tạo (**không migration** — bảng mới).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| ------ | ------------------------------------- | --- | ---- | ------- | ------- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `version_id` | `Integer` → `INTEGER` | **FK→noi_quy_versions.id**, **IX** | no | — | Bản nội quy chứa trang này; `ON DELETE CASCADE`. |
| `page_no` | `Integer` → `INTEGER` | — | no | — | Số trang, **đếm từ 1**. Dùng để xếp thứ tự khi hiện. |
| `file_url` | `String(500)` → `VARCHAR(500)` | — | no | — | Đường dẫn ảnh `/api/files/noi-quy/...`. |
| `width` | `Integer` → `INTEGER` | — | no | `0` | Bề rộng ảnh thật (px). |
| `height` | `Integer` → `INTEGER` | — | no | `0` | Bề cao ảnh thật (px). Cùng `width` để FE đặt sẵn kích thước trên `<img>` ⇒ trang **không nhảy** khi ảnh tải lười xong. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Dựng ảnh lúc nào. |

**Keys & indexes**

- Primary key: `id`. Index: `version_id`. FK: `version_id → noi_quy_versions.id`
  (`ON DELETE CASCADE`).

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

### `overtime_requests`

Phiếu tăng ca (module `tang_ca`): NV tự gửi → tổ trưởng duyệt, HOẶC tổ trưởng tạo thẳng cho thợ (duyệt luôn). Phiếu ĐÃ DUYỆT = **giấy phép + mức trần**: Bảng công tháng chỉ trả tiền phần giờ vượt ca nằm TRONG phiếu; không có phiếu thì vẫn đủ công ca chính, chỉ không ra tiền tăng ca. Máy KHÔNG tự điền giờ ra từ phiếu (lượt bấm ra mới là sự thật). Bảng mới do `create_all` tạo (không migration).

| Column | Type (Py → SQL) | Key | Null | Default | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` | **PK** | no | auto | Khóa chính. |
| `employee_id` | `Integer` → `INTEGER` | **FK→employees.id, IX** | no | — | NV tăng ca (ON DELETE CASCADE). |
| `work_date` | `Date` → `DATE` | **IX** | no | — | NGÀY CÔNG của ca gốc (ngày VÀO ca), không phải ngày lúc tan ca. |
| `from_minute` | `Integer` → `INTEGER` | — | no | — | Phút bắt đầu tăng ca tính từ 00:00 của `work_date`; > 1440 khi qua nửa đêm. |
| `to_minute` | `Integer` → `INTEGER` | — | no | — | Phút kết thúc, cùng trục với `from_minute` (vd 03:00 hôm sau = 1620). |
| `reason` | `String(500)` → `VARCHAR(500)` | — | yes | — | Lý do tăng ca. |
| `status` | `String(16)` → `VARCHAR(16)` | **IX** | no | `pending` | pending/approved/rejected/cancelled. |
| `decided_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Người duyệt/từ chối. |
| `decided_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Thời điểm quyết. |
| `decision_note` | `String(500)` → `VARCHAR(500)` | — | yes | — | Ghi chú / lý do từ chối (từ chối bắt buộc ghi). |
| `created_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | User tạo phiếu (NV tự gửi hoặc tổ trưởng tạo hộ). |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo. |
| `seen_by_employee_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | NV đã xem kết quả chưa (chuông Topbar). Timestamp, KHÔNG Boolean. |

**Keys & indexes**

- Primary key: `id`.
- Indexes: `employee_id`, `work_date`, `status`.

---

### `late_early_requests`

Phiếu xin **ĐI MUỘN / VỀ SỚM / NGHỈ NỬA BUỔI** (module `di_muon`): NV tự gửi → **tổ trưởng duyệt**, HOẶC tổ trưởng khai hộ (duyệt luôn) — cùng luồng phiếu tăng ca. Cố ý KHÔNG dùng chung `leave_requests`: đây là **phiếu chấm công ngoại lệ**, người duyệt khác (tổ trưởng vs HCNS), và gộp chung thì phải nhớ lọc nó ra ở 7 chỗ đọc đơn nghỉ (badge, chuông, lịch nghỉ, 2 danh sách, chặn chốt công, quota). **Hai nhánh tiền** phân biệt bằng `leave_type_id`: NULL = mất công phần vắng, không đụng quỹ phép; khác NULL = tiêu `leave_cong` ngày phép và phần vắng vẫn được trả theo **lương vị trí**. Cả hai nhánh đều được **miễn phạt** đi muộn/về sớm đúng số phút đã xin. Bảng mới do `create_all` tạo (không migration).

| Column | Type (Py → SQL) | Key | Null | Default | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` | **PK** | no | auto | Khóa chính. |
| `employee_id` | `Integer` → `INTEGER` | **FK→employees.id, IX** | no | — | NV xin vắng (ON DELETE CASCADE). |
| `work_date` | `Date` → `DATE` | **IX** | no | — | NGÀY CÔNG của ca gốc (ngày VÀO ca). |
| `from_minute` | `Integer` → `INTEGER` | — | no | — | Phút bắt đầu VẮNG MẶT, tính từ 00:00 của `work_date`. |
| `to_minute` | `Integer` → `INTEGER` | — | no | — | Phút kết thúc vắng mặt. Engine chỉ dùng ĐỘ DÀI `to − from`. |
| `leave_type_id` | `Integer` → `INTEGER` | **IX** | yes | — | Soft-ref `leave_types.id` (KHÔNG FK cứng). NULL = **không** trừ quỹ phép. |
| `leave_cong` | `Numeric(4,2)` → `NUMERIC` | — | no | `0` | Số ngày phép bị trừ, **đã làm tròn 0,5** (vắng ≤ nửa ca → 0,5; vượt → 1,0). |
| `reason` | `String(500)` → `VARCHAR(500)` | — | yes | — | Lý do xin vắng. |
| `status` | `String(16)` → `VARCHAR(16)` | **IX** | no | `pending` | pending/approved/rejected/cancelled. |
| `decided_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Người duyệt/từ chối. |
| `decided_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Thời điểm quyết. |
| `decision_note` | `String(500)` → `VARCHAR(500)` | — | yes | — | Ghi chú / lý do từ chối (từ chối bắt buộc ghi). |
| `created_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | User tạo phiếu (NV tự gửi hoặc tổ trưởng khai hộ). |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo. |
| `seen_by_employee_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | NV đã xem kết quả chưa (chuông Topbar). Timestamp, KHÔNG Boolean. |

**Keys & indexes**

- Primary key: `id`.
- Indexes: `employee_id`, `work_date`, `status`, `leave_type_id`.

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
| `standard_cong` | `Numeric(6,2)` → `NUMERIC` | — | yes | — | **Công chuẩn ĐÓNG BĂNG lúc chốt** (mg 0193). Lịch tuần làm việc chỉ có MỘT bản dùng chung, không có ngày hiệu lực — bỏ làm thứ Bảy là công chuẩn mọi tháng cũ đổi theo, mà đơn giá ngày = lương tháng ÷ công chuẩn. NULL = kỳ chốt trước 15/08/2026 ⇒ đọc lịch sống như cũ. Mở lại kỳ thì xoá về NULL. |
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
| `paid_leave_days` | `Numeric(6,2)` → `NUMERIC(6, 2)` | — | no | `0` | Nghỉ phép CÓ lương. Số LẺ được (phiếu nghỉ nửa buổi có trừ phép = 0,5 ngày). |
| `unpaid_leave_days` | `Integer` → `INTEGER` | — | no | `0` | Nghỉ KHÔNG lương. |
| `holiday_days` | `Integer` → `INTEGER` | — | no | `0` | Ngày nghỉ lễ hưởng công. |
| `total_hours` | `Numeric(7,2)` → `NUMERIC` | — | no | `0` | Tổng giờ có mặt. |
| `ot_minutes` | `Integer` → `INTEGER` | — | no | `0` | Tổng phút vượt ca (chờ duyệt OT — Pha 4). |
| `night_days` | `Integer` → `INTEGER` | — | no | `0` | Số ngày làm ca đêm. |
| `holiday_cong` | `Numeric(6,2)` → `NUMERIC` | — | no | `0` | Công LÀM ngày lễ (Đ98 → Lương trả premium). Thêm qua migration 0065. |
| `restday_cong` | `Numeric(6,2)` → `NUMERIC` | — | no | `0` | Công LÀM ngày nghỉ tuần (Đ98 → premium). Thêm qua migration 0065. |
| `plain_cong` | `Numeric(6,2)` → `NUMERIC` | — | no | `0` | Công LÀM ngày nghỉ `off1x` — Lương trả 1× (KHÔNG hệ số), uncapped. Thêm qua migration 0109. |
| `excused_cong` | `Numeric(6,2)` → `NUMERIC` | — | no | `0` | Công THIẾU nhưng CÓ ĐƠN nghỉ theo giờ đã duyệt (đi muộn/về sớm/nửa ngày). **KHÔNG** cộng vào `total_cong` — tiền công vẫn trừ; chỉ để Lương giữ nguyên phụ cấp chuyên cần. Thêm qua migration 0111. |
| `ot_holiday_minutes` | `Integer` → `INTEGER` | — | no | `0` | Phút OT ngày lễ. Thêm qua migration 0065. |
| `ot_restday_minutes` | `Integer` → `INTEGER` | — | no | `0` | Phút OT ngày nghỉ tuần. Thêm qua migration 0065. |
| `late_off_days_json`, `ca_lam_json` | `Text` → `TEXT` | — | yes | — | JSON list SỐ PHÚT vi phạm (trễ+sớm, không phép) MỖI NGÀY — đóng băng để Lương áp bảng phạt trễ/sớm tự động (mỗi phần tử = 1 lần). Thêm qua migration 0098. |
| `ot_days_json` | `Text` → `TEXT` | — | yes | — | `{"lam": {ngày: phút}, "nghi": {ngày: phút}}` — phút tăng ca TỪNG NGÀY, tách ngày làm việc / ngày nghỉ theo Lịch chung. Nền tính SUẤT CƠM TĂNG CA ở Lương (`ot_minutes` tổng tháng không trả lời được "ngày nào đủ ngưỡng"). Đóng băng khi chốt công. Thêm qua migration 0190. |
| `night_premium_minutes` | `Numeric(10,2)` → `NUMERIC(10,2)` | — | no | `0` | Σ phút đêm TRONG ca × (hệ số ca − 1) → Lương tính premium giờ đêm. Thêm qua migration 0101. |
| `ot_night_normal_minutes` | `Integer` → `INTEGER` | — | no | `0` | Phút TĂNG CA ĐÊM ngày thường (Lương áp hệ số luật). Thêm qua migration 0101. |
| `ot_night_restday_minutes` | `Integer` → `INTEGER` | — | no | `0` | Phút TĂNG CA ĐÊM ngày nghỉ tuần. Thêm qua migration 0101. |
| `ot_night_holiday_minutes` | `Integer` → `INTEGER` | — | no | `0` | Phút TĂNG CA ĐÊM ngày lễ. Thêm qua migration 0101. |
| `note` | `String(500)` → `VARCHAR(500)` | — | yes | — | Ghi chú. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo. |

**Keys & indexes**

- Primary key: `id`.
- Unique: `(period_id, employee_id)` (`uq_attendance_period_line_pe`).
- Foreign keys: `period_id FK→attendance_periods.id` (CASCADE), `employee_id FK→employees.id` (CASCADE).

---

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
| `credit_limit`   | `BigInteger` → `BIGINT`                                | —      | no   | `0`            | HẠN MỨC công nợ (VNĐ) — trần tiền được nợ NCC này. `0` = không đặt hạn mức. Chỉ CẢNH BÁO MỀM, không chặn ở đâu. Migration 0168. |
| `credit_days`    | `Integer` → `INTEGER`                                  | —      | yes  | —              | ĐỊNH MỨC công nợ = số NGÀY cho nợ từ ngày giao; dùng suy hạn trả của đợt giao. `0` = trả ngay · `NULL` = CHƯA đặt hạn (đợt giao không vào cột Quá hạn). Migration 0168. |
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
- One supplier can own many `supplier_items`.

---

### `supplier_items`

**Purpose:** danh sách mặt hàng/bảng giá hiện tại mà từng nhà cung cấp có thể cung ứng. One row = một mặt hàng của một NCC, dùng để gợi ý ĐVT/đơn giá/VAT khi lập phiếu mua, và (mg 0172) để **so giá giữa các NCC** qua `GET /api/supplier-items/so-gia`.

> Cặp `(hang_loai, hang_id)` NULLABLE có chủ ý: NCC còn bán thứ ngoài danh mục vật tư (dịch vụ, gia công) — bắt buộc gắn thì không khai nổi mấy dòng đó. Dòng nào CÓ gắn mới vào được bảng so giá. Không backfill từ `item_name`: ghép bằng chuỗi chính là cái sai đang đi chữa (thu mua gõ "Couche 150", danh mục ghi "Couché 150 79×109" là trượt, mà trượt thì im lặng).

| Column        | Type (SQLAlchemy → SQLite / Postgres)                  | Key                  | Null | Default        | Meaning                                      |
| ------------- | ------------------------------------------------------ | -------------------- | ---- | -------------- | -------------------------------------------- |
| `id`          | `Integer` → `INTEGER` / `SERIAL`                       | **PK**               | no   | auto-increment | Surrogate primary key.                       |
| `supplier_id` | `Integer` → `INTEGER`                                  | **FK→suppliers.id**, **IX** | no   | —              | Nhà cung cấp sở hữu mặt hàng/bảng giá.       |
| `hang_loai`   | `String(8)` → `VARCHAR(8)`                             | **IX** (cặp)         | yes  | —              | Mặt hàng gốc dòng này bán: `giay` \| `vat_tu` (mg 0172). |
| `hang_id`     | `Integer` → `INTEGER`                                  | **IX** (cặp)         | yes  | —              | Id trong `giay_nguyen` / `vat_tu_in_an`. Soft ref. |
| `item_name`   | `String(255)` → `VARCHAR(255)`                         | **IX**               | no   | —              | Tên vật tư/sản phẩm/dịch vụ NCC cung cấp.    |
| `unit`        | `String(32)` → `VARCHAR(32)`                           | —                    | no   | —              | Đơn vị NCC BÁN theo. Nếu đã gắn mặt hàng thì phải nằm trong tập đổi được của nó (service chặn) — không thì cột "giá quy về đơn vị gốc" vĩnh viễn trống và dòng đó biến mất khỏi so giá. |
| `unit_price`  | `BigInteger` → `BIGINT`                                | —                    | no   | `0`            | Đơn giá hiện tại của NCC.                    |
| `vat_percent` | `Numeric(6,2)` → `NUMERIC(6,2)`                        | —                    | no   | `0`            | Thuế GTGT tham khảo theo mặt hàng.           |
| `is_active`   | `Boolean` → `BOOLEAN`                                  | —                    | no   | `true`         | Cột kỹ thuật ẩn để tương thích DB cũ; UI không dùng trạng thái mặt hàng. |
| `lead_time_days` | `Integer` → `INTEGER`                               | —                    | no   | `0`            | **CỘT CHẾT — bỏ 10/08/2026** (thêm ở mg 0176). Số ngày NCC giao, phải khai tay ở bảng giá; lúc dựng danh mục chưa ai biết ông ấy giao mấy ngày nên số gõ vào là số đoán, mà kế hoạch lại dựa vào đó bật đèn "đặt muộn". Nay **hạn chót phải đặt = ngày cần − đệm kiểm nhập**, không phụ thuộc NCC. Cần chính xác hơn thì suy từ lịch sử mua (ngày đặt → ngày nhận thật), đừng bắt khai tay. Cột để nguyên trong DB, không code nào đọc/ghi. |
| `note`        | `Text` → `TEXT`                                        | —                    | yes  | —              | Ghi chú báo giá/điều kiện mua.               |
| `created_at`  | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                    | no   | now (UTC)      | Khi tạo.                                     |
| `updated_at`  | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                    | no   | now (UTC)      | Cập nhật cuối.                               |

**Keys & indexes**

- Primary key: `id`.
- Indexes on `supplier_id`, `item_name`.
- Foreign key: `supplier_id FK→suppliers.id` (cascade).

**Relationships**

- One supplier item belongs to one `suppliers` row.

---

### `purchase_deliveries`

**Purpose:** ĐỢT GIAO — một lần NCC giao hàng cho một phiếu mua. One row = một lần hàng về.
Có bảng này thì **nợ phát sinh theo từng đợt** (hàng về tới đâu nợ tới đó); trước đó số thực nhận
chỉ là một con số cộng dồn trên dòng nên công nợ chỉ biết "chưa nhận gì" và "nhận cả đơn" — giao
1/3 đợt là màn công nợ hiện 0đ (giấu nợ), bấm "Đã nhận hàng" sớm là ghi nợ đủ 100% (thừa nợ).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `purchase_request_id` | `Integer` → `INTEGER` | **FK→purchase_requests.id** (CASCADE), **IX** | no | — | Phiếu mua chứa đợt giao này. |
| `seq_no` | `Integer` → `INTEGER` | **U** cùng `purchase_request_id` | no | — | Đợt 1, 2, 3… trong phạm vi MỘT phiếu mua. Cố ý không cấp mã chứng từ toàn hệ. |
| `delivery_date` | `Date` → `DATE` | — | no | — | Ngày hàng về — gốc tính hạn trả. |
| `due_date` | `Date` → `DATE` | — | yes | — | Hạn trả riêng của đợt. `NULL` ⇒ suy `delivery_date + suppliers.credit_days`; NCC chưa khai số ngày thì đợt KHÔNG có hạn ⇒ không vào cột Quá hạn. |
| `invoice_number` | `String(64)` → `VARCHAR(64)` | **IX** | yes | — | Số hoá đơn. Nhiều đợt mang CÙNG số = cùng MỘT hoá đơn (NCC hay giao 3 đợt rồi mới xuất một hoá đơn chung). |
| `invoice_date` | `Date` → `DATE` | — | yes | — | Ngày hoá đơn. |
| `amount` | `BigInteger` → `BIGINT` | — | yes | — | SỐ TIỀN của đợt **theo hoá đơn**, người khai gõ tay — công nợ bám con số này. `NULL` = chưa khai ⇒ lùi về số máy tính từ đơn giá đã chốt trên phiếu (cũng là số form điền sẵn). Cố ý KHÔNG ràng buộc khớp đơn giá và KHÔNG chặn vượt giá trị đơn: hoá đơn là chứng từ, ghi sao nhập vậy; lệch thì `purchase_money` gắn cờ `vuot_gia_tri_don`. Migration 0170. |
| `note` | `Text` → `TEXT` | — | yes | — | Ghi chú. |
| `stock_voucher_id` | `Integer` → `INTEGER` | **IX** (soft ref) | yes | — | 🔌 Chỗ neo cho Phiếu nhập kho — đợt giao và phiếu nhập kho là CÙNG một sự kiện vật lý. Luôn NULL cho tới khi build Kho ↔ Mua hàng. |
| `created_by_user_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | yes | — | Người ghi đợt giao. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Cập nhật cuối. |

**Keys & indexes**

- `UNIQUE (purchase_request_id, seq_no)` — số đợt không trùng trong một phiếu.
- Bảng MỚI 06/08/2026 ⇒ `create_all` dựng; không có migration ADD COLUMN cho chính bảng này.

---

### `purchase_delivery_lines`

**Purpose:** dòng của một đợt giao — mặt hàng nào, đợt này nhận bao nhiêu.

**CỐ Ý KHÔNG CÓ CỘT TIỀN.** Tiền của đợt = `quantity` × đơn giá/CK/VAT đã chốt ở
`purchase_request_lines`. Mở ô tiền ở đây là đẻ nguồn sự thật thứ hai: tổng các đợt sẽ lệch với giá
trị đơn mà không ai phát hiện cho tới lúc đối chiếu với NCC.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `delivery_id` | `Integer` → `INTEGER` | **FK→purchase_deliveries.id** (CASCADE), **IX** | no | — | Đợt giao chứa dòng này. |
| `purchase_request_line_id` | `Integer` → `INTEGER` | **FK→purchase_request_lines.id** (RESTRICT), **IX** | no | — | Dòng ĐẶT mà đợt này giao vào. |
| `quantity` | `Numeric(14,2)` → `NUMERIC(14,2)` | — | no | `0` | Số thực nhận của RIÊNG đợt này. Tổng các đợt không được vượt số đặt. |
| `note` | `Text` → `TEXT` | — | yes | — | Ghi chú dòng. |

**Keys & indexes**

- `UNIQUE (delivery_id, purchase_request_line_id)` — một đợt không khai một mặt hàng hai dòng.

---

### `purchase_attachments`

**Purpose:** ảnh/file của mua hàng — hợp đồng (treo ở PMH) hoặc hoá đơn/biên bản giao nhận (treo ở
một đợt giao). Bytes nằm ở `mua-hang/<purchase_request_id>/` trong kho file; DB chỉ giữ metadata.

⚠️ Tiền tố `mua-hang` PHẢI có trong `_PREFIX_PERMISSION` (`routers/files.py`) — bảng đó fail-MỞ:
tiền tố không khai thì chỉ cần đăng nhập là đọc được, tức hợp đồng NCC lộ cho toàn công ty.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `purchase_request_id` | `Integer` → `INTEGER` | **FK→purchase_requests.id** (CASCADE), **IX** | no | — | Phiếu mua sở hữu file. |
| `delivery_id` | `Integer` → `INTEGER` | **FK→purchase_deliveries.id** (CASCADE), **IX** | yes | — | `NULL` = file của cả phiếu mua (hợp đồng); có giá trị = file của riêng một đợt giao. |
| `kind` | `String(24)` → `VARCHAR(24)` | — | no | `"khac"` | `hop_dong` · `hoa_don` · `bien_ban_giao` · `khac`. |
| `file_name` | `String(255)` → `VARCHAR(255)` | — | no | — | Tên file đã chuẩn hoá chống traversal. |
| `file_url` | `String(500)` → `VARCHAR(500)` | — | no | — | Đường dẫn đọc lại qua `/api/files/...`. |
| `file_type` | `String(100)` → `VARCHAR(100)` | — | yes | — | Content type (ảnh hoặc PDF). |
| `uploaded_by` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Người tải lên. |
| `uploaded_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tải lên. |

---

### `purchase_status_history`

**Purpose:** LỊCH SỬ ĐỔI TRẠNG THÁI của yêu cầu mua hàng (YCMH) và phiếu mua hàng (PMH).
One row = một lần trạng thái đổi. Chủ chốt 07/08/2026.

Vì sao KHÔNG dùng `audit_logs`: cột `detail` bên đó là **chữ tự do** (`"PMH-x — lý do y"`). Suy
ngược ra *"trạng thái TRƯỚC ĐÓ là gì"* từ chữ tự do là đoán — đoán trượt thì màn hiện sai mà không
có gì báo lỗi.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `doc_type` | `String(8)` → `VARCHAR(8)` | **IX** | no | — | `ycmh` · `pmh`. |
| `doc_id` | `Integer` → `INTEGER` | **IX** (soft ref) | no | — | id của YCMH **hoặc** PMH tuỳ `doc_type`. Hai bảng khác nhau nên **không khai được khoá ngoại**. |
| `from_status` | `String(24)` → `VARCHAR(24)` | — | yes | — | `NULL` = dòng đầu tiên (lúc chứng từ ra đời). |
| `to_status` | `String(24)` → `VARCHAR(24)` | — | no | — | Trạng thái mới. |
| `changed_by_user_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | yes | — | `NULL` = **MÁY tự suy**, không ai bấm. |
| `source` | `String(8)` → `VARCHAR(8)` | — | no | `"nguoi"` | `nguoi` · `may`. Trạng thái YCMH là số SUY RA từ các phiếu con — duyệt một PMH thì YCMH tự nhảy. Không phân biệt thì lịch sử hiện dòng không tên ai, người đọc tưởng mất dữ liệu. |
| `reason` | `Text` → `TEXT` | — | yes | — | Lý do từ chối/huỷ/đóng đơn/mở lại. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | **IX** | no | now (UTC) | Khi đổi. |

**Keys & indexes**

- Bảng MỚI 07/08/2026 ⇒ `create_all` dựng; không có migration `ADD COLUMN` cho chính bảng này.
- ⚠️ **Chỉ ghi khi trạng thái THỰC SỰ đổi** và **chỉ ghi đổi trạng thái**. YCMH được suy lại ở mọi
  thao tác chạm phiếu con; suy ra trùng trạng thái cũ mà vẫn ghi thì mỗi cú bấm đẻ một dòng rác.
  Sửa nội dung/dòng hàng vẫn thuộc `audit_logs`.
- Mọi lệnh đổi trạng thái đi qua **một cửa** `PurchaseService._dat_trang_thai` — trước đợt này có
  13 chỗ gán thẳng `row.status`, rải lệnh ghi ra 13 chỗ thì chắc chắn sót.

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
| `purpose`                | `String(500)` → `VARCHAR(500)`                         | —      | no   | —              | ⚠️ **DORMANT** từ 07/08/2026 — gộp vào `content`. Service vẫn ghi một bản sao cắt 500 ký tự vì cột này còn ràng buộc NOT NULL, nhưng **không ai đọc nó nữa**. |
| `content`                  | `Text` → `TEXT`                                        | —      | yes  | —              | Ô GỘP **"Nội dung / mục đích"** (07/08/2026). Migration 0171. |
| `reject_reason`            | `Text` → `TEXT`                                        | —      | yes  | —              | Lý do huỷ yêu cầu — tách khỏi `content`. Migration 0171. |
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
| `hang_loai`             | `String(8)` → `VARCHAR(8)`            | **IX** (cặp)                                   | yes  | —              | Mặt hàng gốc: `giay` \| `vat_tu` (mg 0174). Nút "Đề nghị mua" ở bảng cân đối vật tư ghi thẳng vào đây. |
| `hang_id`               | `Integer` → `INTEGER`                 | **IX** (cặp)                                   | yes  | —              | Id trong `giay_nguyen` / `vat_tu_in_an`. Soft ref. `NULL` = khai tay ngoài danh mục.          |
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
| `status`              | `String(24)` → `VARCHAR(24)`                           | **IX**                      | no   | `"draft"`      | Trạng thái: `draft`, `pending_approval`, `approved`, `rejected`, `purchased`, `partially_received`, `received`, `cancelled`. `partially_received` SUY từ `purchase_deliveries` (06/08/2026). |
| `supplier_id`         | `Integer` → `INTEGER`                                  | **FK→suppliers.id**, **IX** | yes  | —              | Nhà cung cấp dự kiến; null nếu chưa chốt NCC.                                                          |
| `purpose`             | `String(500)` → `VARCHAR(500)`                         | —                           | yes  | —              | ⚠️ **DORMANT** từ 07/08/2026 — gộp vào `content`. Service vẫn ghi một bản sao cắt 500 ký tự vì cột này còn ràng buộc NOT NULL, nhưng **không ai đọc nó nữa**. |
| `content`             | `Text` → `TEXT`                                        | —                           | yes  | —              | Ô GỘP **"Nội dung / mục đích"** — thay cặp `purpose` + `note` (07/08/2026). Migration 0171 dồn dữ liệu cũ sang. |
| `reject_reason`       | `Text` → `TEXT`                                        | —                           | yes  | —              | Lý do **từ chối · huỷ · đóng đơn · mở lại**. Tách hẳn khỏi `content`: trước đây `cancel()` chạy `row.note = reason` ⇒ **ghi đè mất** ghi chú của người lập. Migration 0171. |
| `needed_date`         | `Date` → `DATE`                                        | —                           | yes  | —              | Ngày cần hàng.                                                                                         |
| `expected_receipt_date` | `Date` → `DATE`                                        | —                           | yes  | —              | Ngày dự kiến nhận hàng (NCC hẹn giao) — migration 0038.                                                |
| `contract_number`     | `String(64)` → `VARCHAR(64)`                           | —                           | yes  | —              | Số hợp đồng mua. Bản thân hợp đồng là ảnh ở `purchase_attachments` (`kind='hop_dong'`) — cố ý không dựng danh mục hợp đồng. Migration 0168. |
| `deposit_expected`    | `BigInteger` → `BIGINT`                                | —                           | no   | `0`            | Cọc DỰ KIẾN theo hợp đồng — chỉ để NHẮC, **KHÔNG** vào công thức công nợ. Tiền cọc thật là một Phiếu chi `payment_stage='advance'`; cho số này vào công thức là trừ cọc HAI LẦN. Migration 0168. |
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
| `department_request_line_id` | `Integer` → `INTEGER`          | **FK→department_purchase_request_lines.id**, **IX** | yes | — | Dòng YCMH đã đẻ ra dòng này (nối DÒNG↔DÒNG, khác `purchase_request_sources` nối PHIẾU↔YÊU CẦU). Nền cho "trạng thái từng sản phẩm" ở chi tiết YCMH. `NULL` = phiếu lập trước 05/08/2026 hoặc dòng thu mua tự thêm. ⚠️ Khoá ngoại CHỈ có trên DB dựng bằng `create_all`; migration 0163 chỉ thêm cột (SQLite không ALTER được constraint) nên DB live có thể có id mồ côi — chỗ đọc phải chịu được. |
| `hang_loai`           | `String(8)` → `VARCHAR(8)`            | **IX** (cặp)                        | yes  | —              | Mặt hàng gốc dòng này mua: `giay` \| `vat_tu` (mg 0174). KẾ THỪA từ dòng YCMH qua `department_request_line_id` lúc lập phiếu. |
| `hang_id`             | `Integer` → `INTEGER`                 | **IX** (cặp)                        | yes  | —              | Id trong `giay_nguyen` / `vat_tu_in_an`. Soft ref. `NULL` = mua thứ ngoài danh mục (dịch vụ, gia công) ⇒ bảng cân đối vật tư **không** cộng dòng này vào "hàng đang về" (không đoán ngược từ `item_name`). |
| `item_name`           | `String(255)` → `VARCHAR(255)`        | —                                   | no   | —              | Tên vật tư/dịch vụ cần mua.                        |
| `unit`                | `String(32)` → `VARCHAR(32)`          | —                                   | no   | `"cái"`        | Đơn vị tính.                                       |
| `quantity`            | `Numeric(14,2)` → `NUMERIC(14,2)`     | —                                   | no   | `0`            | Số lượng cần mua.                                  |
| `received_quantity`   | `Numeric(14,2)` → `NUMERIC(14,2)`     | —                                   | yes  | —              | Số THỰC NHẬN, khai lúc bấm "Đã nhận hàng". `NULL` = chưa khai ⇒ coi như nhận đủ `quantity` (giữ nguyên hành vi phiếu cũ). Công nợ phải trả và trần lập phiếu chi cộng theo cột này. |
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

**Purpose:** danh mục tài khoản ngân hàng của công ty dùng cho tiền vào (Phiếu thu/chuyển khoản nhận) và tiền ra (UNC/chuyển khoản chi).

| Column           | Type (SQLAlchemy → SQLite / Postgres)                  | Key    | Null | Default        | Meaning                                  |
| ---------------- | ------------------------------------------------------ | ------ | ---- | -------------- | ---------------------------------------- |
| `id`             | `Integer` → `INTEGER` / `SERIAL`                       | **PK** | no   | auto-increment | Surrogate primary key.                   |
| `account_holder` | `String(255)` → `VARCHAR(255)`                         | —      | no   | —              | Tên chủ tài khoản.                       |
| `account_number` | `String(64)` → `VARCHAR(64)`                           | **IX** | no   | —              | Số tài khoản.                            |
| `bank_name`      | `String(255)` → `VARCHAR(255)`                         | **IX** | no   | —              | Tên ngân hàng.                           |
| `bank_branch`    | `String(255)` → `VARCHAR(255)`                         | —      | no   | —              | Chi nhánh ngân hàng.                     |
| `currency`       | `String(3)` → `VARCHAR(3)`                             | —      | no   | `"VND"`        | Loại tiền của tài khoản.                 |
| `is_default`     | `Boolean` → `BOOLEAN`                                  | —      | no   | `false`        | Cột cũ, không còn dùng từ 10/08/2026; kế toán tự chọn tài khoản khi lập chứng từ. |
| `is_active`      | `Boolean` → `BOOLEAN`                                  | **IX** | no   | `true`         | Tài khoản còn được phép chọn để lập chứng từ. |
| `use_for_receipts` | `Boolean` → `BOOLEAN`                                | —      | no   | `true`         | Bật nếu tài khoản được dùng để nhận tiền Phiếu thu/chuyển khoản vào. |
| `use_for_payments` | `Boolean` → `BOOLEAN`                                | —      | no   | `true`         | Bật nếu tài khoản được dùng để chi tiền/UNC/chuyển khoản ra. |
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
| `is_default`     | `Boolean` → `BOOLEAN`                                  | —                           | no   | `false`        | Cột cũ, không còn dùng từ 10/08/2026; kế toán tự chọn tài khoản thụ hưởng khi lập UNC. |
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

**Purpose:** Sổ Phiếu chi/Ủy nhiệm chi do người có quyền `ke_toan.approve` lập. PMH chỉ là một nguồn chi; phiếu cũng có thể được lập độc lập cho chi phí nội bộ, hoàn tiền khách hàng, khoản chi khác, hoặc **phiếu tạm ứng lương đã duyệt** (18/08/2026).

| Column                                | Type (SQLAlchemy → SQLite / Postgres)                  | Key                                      | Null | Default             | Meaning                                                                        |
| ------------------------------------- | ------------------------------------------------------ | ---------------------------------------- | ---- | ------------------- | ------------------------------------------------------------------------------ |
| `id`                                  | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                                   | no   | auto-increment      | Surrogate primary key.                                                         |
| `code`                                | `String(32)` → `VARCHAR(32)`                           | **U**, **IX**                            | no   | generated           | Mã `PC-YYMMDD-XXXX` hoặc `UNC-YYMMDD-XXXX`.                                    |
| `doc_no`                              | `String(16)` → `VARCHAR(16)`                           | **U**, **IX**                            | yes  | generated           | Số IN trên mẫu 02-TT (`PC00445`) — thứ tự LẬP phiếu, chạy liên tục không reset theo năm; dùng chung bộ đếm cho tiền mặt lẫn UNC; phiếu hủy vẫn giữ số. Migration 0040. |
| `source_type`                         | `String(24)` → `VARCHAR(24)`                           | **IX**                                   | no   | `"purchase_request"` | Nguồn chi: `purchase_request`, `internal_expense`, `customer_refund`, `other`, `salary_advance`. Migration 0176; thêm `salary_advance` ở 0207. |
| `purchase_request_id`                 | `Integer` → `INTEGER`                                  | **FK→purchase_requests.id**, **IX**      | yes  | —                   | PMH nguồn nếu `source_type='purchase_request'`; NULL với phiếu chi độc lập. Migration 0176. |
| `salary_advance_id`                   | `Integer` → `INTEGER`                                  | **FK→salary_advances.id** (RESTRICT), **U**, **IX** | yes  | —                   | Phiếu **TẠM ỨNG LƯƠNG** nguồn — chỉ có giá trị khi `source_type='salary_advance'`. **UNIQUE** ⇒ một phiếu tạm ứng chỉ lập được ĐÚNG MỘT phiếu chi; đây là chốt chống chi hai lần ở tầng DB, không chỉ ở service (hai request song song lách được service). Áp cho cả `kind='tam_ung'` lẫn `kind='luong_dot_1'` — cùng là tiền ra khỏi két. Chỉ lập được từ phiếu **ĐÃ DUYỆT**; và khi đã có phiếu chi thì **KHÔNG huỷ được phiếu tạm ứng** (`payroll_service.cancel_advance` chặn) — huỷ phiếu chi trước. Số tiền và người nhận trên phiếu chi **lấy từ phiếu tạm ứng**, payload gửi lên bị bỏ qua. Migration 0207. |
| `delivery_id`                         | `Integer` → `INTEGER`                                  | **IX** (soft ref → `purchase_deliveries.id`) | yes  | —                   | Đợt giao mà phiếu này trả cho. `NULL` = phiếu ĐẶT CỌC/ứng trước (chi khi hàng chưa về), hoặc phiếu lập trước 06/08/2026. Soft ref có chủ ý: xoá đợt còn phiếu chi đã bị chặn ở service. Migration 0168. |
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

### `sales_invoices`

**Purpose:** Hóa đơn bán đã phát hành — mốc làm phát sinh công nợ phải thu. Một Đơn hàng bán
có thể phát hành nhiều hóa đơn; công nợ chỉ tính các hóa đơn `issued`, không lấy trực tiếp từ
giá trị đơn đã chốt. One row = 1 hóa đơn bán.

| Column                       | Type (SQLAlchemy → SQLite / Postgres)                  | Key                               | Null | Default    | Meaning                                                        |
| ---------------------------- | ------------------------------------------------------ | --------------------------------- | ---- | ---------- | -------------------------------------------------------------- |
| `id`                         | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                            | no   | auto       | Surrogate primary key.                                         |
| `order_id`                   | `Integer` → `INTEGER`                                  | **FK→orders.id**, **IX**          | no   | —          | Đơn hàng bán nguồn; `ON DELETE RESTRICT`.                       |
| `customer_id`                | `Integer` → `INTEGER`                                  | **FK→customers.id**, **IX**       | yes  | —          | Khách hàng; `ON DELETE SET NULL`.                               |
| `invoice_symbol`             | `String(64)` → `VARCHAR(64)`                           | **UQ pair**                       | no   | —          | Ký hiệu hóa đơn.                                                |
| `invoice_number`             | `String(64)` → `VARCHAR(64)`                           | **UQ pair**                       | no   | —          | Số hóa đơn.                                                     |
| `invoice_date`               | `Date` → `DATE`                                        | —                                 | no   | —          | Ngày phát hành hóa đơn.                                         |
| `amount_vnd`                 | `BigInteger` → `BIGINT`                                | —                                 | no   | —          | Giá trị hóa đơn bằng VND; service bắt buộc lớn hơn 0.           |
| `payment_term_days_snapshot` | `Integer` → `INTEGER`                                  | —                                 | yes  | —          | Số ngày công nợ được chụp tại lúc phát hành.                    |
| `due_date`                   | `Date` → `DATE`                                        | —                                 | yes  | —          | Hạn thanh toán của hóa đơn.                                     |
| `customer_name_snapshot`     | `String(255)` → `VARCHAR(255)`                         | —                                 | no   | —          | Tên khách hàng tại lúc phát hành.                               |
| `status`                     | `String(16)` → `VARCHAR(16)`                           | **IX**                            | no   | `issued`   | `issued` hoặc `cancelled`.                                      |
| `created_by_user_id`         | `Integer` → `INTEGER`                                  | **FK→users.id**                   | yes  | —          | Người ghi nhận hóa đơn; `ON DELETE SET NULL`.                   |
| `created_at`                 | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                 | no   | now (UTC)  | Khi tạo.                                                        |
| `updated_at`                 | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                 | no   | now (UTC)  | Cập nhật cuối.                                                  |
| `cancelled_by_user_id`       | `Integer` → `INTEGER`                                  | **FK→users.id**                   | yes  | —          | Người hủy hóa đơn; `ON DELETE SET NULL`.                         |
| `cancelled_at`               | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | —                                 | yes  | —          | Thời điểm hủy.                                                  |
| `cancel_reason`              | `Text` → `TEXT`                                        | —                                 | yes  | —          | Lý do hủy.                                                      |

**Keys, indexes & rules**

- Primary key: `id`; unique constraint `(invoice_symbol, invoice_number)`.
- Indexes: `order_id`, `customer_id`, `status`.
- `amount_vnd > 0` được kiểm tra tại service.
- Hóa đơn `issued` làm phát sinh công nợ; hóa đơn `cancelled` không tính vào công nợ.

**Relationships**

- Many sales invoices belong to one `orders` row and optionally one `customers` row.
- One sales invoice has many `payment_receipts` rows; FK phía phiếu thu dùng `ON DELETE RESTRICT`.

---

### `payment_receipts`

**Purpose:** Phiếu thu (PT) đa nguồn: hoàn tiền từ Phiếu chi/UNC, cọc Đơn hàng bán, thu công nợ
theo Hóa đơn bán hoặc khoản thu khác. One row = 1 phiếu thu; chỉ phiếu thu `received` được tính
vào số tiền thực thu.

| Column                            | Type (SQLAlchemy → SQLite / Postgres)                  | Key                                     | Null | Default             | Meaning                                                            |
| --------------------------------- | ------------------------------------------------------ | --------------------------------------- | ---- | ------------------- | ------------------------------------------------------------------ |
| `id`                              | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                                  | no   | auto-increment      | Surrogate primary key.                                             |
| `code`                            | `String(32)` → `VARCHAR(32)`                           | **U**, **IX**                           | no   | generated           | Mã `PT-YYMMDD-XXXX`.                                               |
| `doc_no`                          | `String(16)` → `VARCHAR(16)`                           | **U**, **IX**                           | yes  | generated           | Số IN trên mẫu 01-TT (`PT00027`) — thứ tự lập, chạy liên tục không reset theo năm. Migration 0040. |
| `source_type`                     | `String(20)` → `VARCHAR(20)`                           | **IX**                                  | no   | `"purchase_refund"` | Nguồn ∈ {purchase_refund, order_deposit, sales_invoice, other}. Nguồn `sales_invoice` thêm ở migration 0187. |
| `payment_voucher_id`              | `Integer` → `INTEGER`                                  | **FK→payment_vouchers.id**, **IX**      | yes  | —                   | Phiếu chi gốc (RESTRICT). NULL cho phiếu thu cọc đơn bán. Nới NOT NULL mig 0070. |
| `purchase_request_id`             | `Integer` → `INTEGER`                                  | **FK→purchase_requests.id**, **IX**     | yes  | —                   | PMH nguồn (denormalize). NULL cho đơn bán. Nới NOT NULL mig 0070.  |
| `order_id`                        | `Integer` → `INTEGER`                                  | **FK→orders.id**, **IX**                | yes  | —                   | Đơn bán (RESTRICT) — cọc khách nộp. NULL cho đường phiếu chi. Migration 0070. |
| `sales_invoice_id`                | `Integer` → `INTEGER`                                  | **FK→sales_invoices.id**, **IX**        | yes  | —                   | Hóa đơn bán nguồn (RESTRICT) khi thu công nợ. Migration 0187.    |
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
| `customer_name_snapshot`          | `String(255)` → `VARCHAR(255)`                         | —                                       | yes  | —                   | Tên khách snapshot (V5, nhánh `order_deposit`) — hiện trên phiếu không join. Migration 0070. |
| `order_no_snapshot`               | `String(32)` → `VARCHAR(32)`                           | —                                       | yes  | —                   | Mã đơn (`order_no`) snapshot (V5, nhánh `order_deposit`). Migration 0070. |
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

- Primary key: `id`; unique index on `code`. Indexes: `source_type`, `order_id`, `sales_invoice_id`.
- **Đa nguồn (V5):** `source_type='purchase_refund'` → nhánh hoàn ứng NCC/NV (bắt buộc `payment_voucher_id`
  + `purchase_request_id`; hành vi cũ nguyên vẹn). `source_type='order_deposit'` → thu cọc khách gắn
  `order_id`; tạo THẲNG `received` (Kế toán bấm = đã thu), không qua phiếu chi. `source_type='other'` → thu khác/thu độc lập.
- Nhánh Hóa đơn bán: `source_type='sales_invoice'` → bắt buộc `sales_invoice_id`; phiếu thu
  `received` làm giảm công nợ của đúng hóa đơn được liên kết.
- Nhánh Phiếu chi: chỉ lập trên phiếu chi `paid`; tổng `amount_vnd` phiếu thu `waiting_receipt` +
  `received` không vượt `amount_vnd` phiếu chi gốc. Chỉ `waiting_receipt` mới sửa/hủy; `received` bất
  biến. Rollup PMH: `receipt_received_amount` = SUM phiếu thu `received`.
- Nhánh Đơn hàng bán: cổng "đủ cọc" của đơn = Σ `amount` phiếu thu (`order_id`, `received`) ≥
  `deposit_required`.

**Relationships**

- Nhánh Phiếu chi: many payment receipts belong to one `payment_vouchers` row (và một
  `purchase_requests` row). Nhánh Đơn hàng bán: many receipts belong to one `orders` row.
- Nhánh công nợ: many payment receipts belong to one `sales_invoices` row.
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
| `meal_allowance`  | `Numeric(14,2)` → `NUMERIC(14,2)`                    | —      | no   | `25000`        | Phụ cấp cơm khai theo CA (tăng ca 17h30→24h). NV gán ca này tự cộng. Đợt 1 chỉ lưu/phơi; engine chưa dùng. Thêm qua migration 0094. |
| `shift_allowance` | `Numeric(14,2)` → `NUMERIC(14,2)`                    | —      | no   | `50000`        | Phụ cấp CA (áp ca ngày hay đêm) khai theo CA. NV gán ca này tự cộng. Đợt 1 chỉ lưu/phơi; engine chưa dùng. Đổi tên từ `night_allowance` qua migration 0095. |
| `night_multiplier` | `Numeric(6,4)` → `NUMERIC(6,4)`                      | —      | no   | `1.3`          | Hệ số ca đêm: premium giờ rơi 22h–06h TRONG ca = (hệ số−1)×đơn giá giờ×giờ đêm. 1.3=+30%. Chỉ dùng ca qua đêm. Thêm qua migration 0100. |
| `grace_minutes` | `Integer` → `INTEGER`                                  | —      | no   | `5`            | Dung sai đi muộn (phút): vào trễ ≤ giá trị này vẫn coi đúng giờ. |
| `is_active`     | `Boolean` → `BOOLEAN`                                  | —      | no   | `true`         | Ca đang dùng.                                                    |
| `dung_cho_lich_may` | `Boolean` → `BOOLEAN`                              | —      | no   | `false`        | Ca thuộc LỊCH CHẠY MÁY của xưởng (khác ca chấm công HR). Xếp lịch công đoạn (Gantt) tính giờ theo tập ca có cờ này (nghỉ trưa = khe giữa 2 ca); chưa tick ca nào → fallback 8h phẳng `[08:00,16:00)`. Thêm qua migration 0095. |
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

**Purpose:** đơn xin nghỉ NGUYÊN NGÀY của một NV (Nghỉ phép — module `nhan_su`), từ `start_date`
đến `end_date` bao gồm 2 đầu. Workflow `pending → approved / rejected / cancelled`. Đơn `approved`
được Bảng công tháng đọc để đánh dấu P/KL.

⚠️ Nghỉ theo GIỜ (đi muộn / về sớm / nửa buổi) **KHÔNG** nằm ở bảng này — xem `late_early_requests`
(bảng riêng, tổ trưởng duyệt). Từng gộp chung rồi tách ra vì có 7 nơi đọc đơn nghỉ, sót một chỗ lọc
là phiếu 2 tiếng lại chặn chốt công / vẽ thành nghỉ trọn ngày.

| Column                | Type (SQLAlchemy → SQLite / Postgres)                  | Key                           | Null | Default        | Meaning                                                                                                                                            |
| --------------------- | ------------------------------------------------------ | ----------------------------- | ---- | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                  | `Integer` → `INTEGER` / `SERIAL`                       | **PK**                        | no   | auto-increment | Surrogate primary key.                                                                                                                             |
| `employee_id`         | `Integer` → `INTEGER`                                  | **FK→employees.id**, **IX**   | no   | —              | NV xin nghỉ; `ON DELETE CASCADE`.                                                                                                                  |
| `leave_type_id`       | `Integer` → `INTEGER`                                  | **FK→leave_types.id**, **IX** | yes  | —              | Loại nghỉ; `ON DELETE SET NULL`.                                                                                                                   |
| `start_date`          | `Date` → `DATE`                                        | **IX**                        | no   | —              | Từ ngày (bao gồm).                                                                                                                                 |
| `end_date`            | `Date` → `DATE`                                        | —                             | no   | —              | Đến ngày (bao gồm).                                                                                                                                |
| `days`                | `Integer` → `INTEGER`                                  | —                             | no   | `1`            | Số ngày nghỉ = số ngày lịch bao gồm 2 đầu. Đơn theo GIỜ luôn = 1.                                                                                   |
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
| `kind` | `String(8)` → `VARCHAR(8)` | — | no | `off` | `off` = nghỉ lễ; `work` = làm bù; `off1x` = nghỉ, đi làm chỉ 1× (không hệ số). |
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
| `standard_cong_default` | `Numeric(6,2)` | no | `26` | LƯỚI DỰ PHÒNG cho công chuẩn/tháng. Mặc định Lương lấy ĐỘNG theo Lịch (`standard_working_days`); chỉ rơi về cột này khi chưa có lịch. Ô khai đã gỡ khỏi Cấu hình lương. |
| `probation_ratio` | `Numeric(5,4)` | no | `0.80` | Thử việc hưởng % của lương chính thức — công ty dùng 0.80 (Đ26 BLLĐ tối thiểu 85%). |
| `bhxh_rate` | `Numeric(6,4)` | no | `0.08` | Tỷ lệ NV đóng BHXH. |
| `bhyt_rate` | `Numeric(6,4)` | no | `0.015` | Tỷ lệ NV đóng BHYT. |
| `bhtn_rate` | `Numeric(6,4)` | no | `0.01` | Tỷ lệ NV đóng BHTN. |
| `bhxh_rate_er` | `Numeric(6,4)` | no | `0.175` | Tỷ lệ NSDLĐ đóng BHXH — **KHÔNG trừ vào lương NV**, chỉ tính chi phí công ty. Thêm qua migration 0076. |
| `bhyt_rate_er` | `Numeric(6,4)` | no | `0.03` | Tỷ lệ NSDLĐ đóng BHYT (không trừ vào lương NV). Thêm qua migration 0076. |
| `bhtn_rate_er` | `Numeric(6,4)` | no | `0.01` | Tỷ lệ NSDLĐ đóng BHTN (không trừ vào lương NV). Thêm qua migration 0076. |
| `cong_doan_rate` | `Numeric(6,4)` | no | `0` | Tỷ lệ đoàn phí công đoàn (chủ tự khai; mẫu 0.5%=0.005). Thêm qua migration 0074. |
| `tnld_bnn_rate` | `Numeric(6,4)` | no | `0.005` | Tỷ lệ TNLĐ-BNN do CÔNG TY chịu (mẫu 0.5%=0.005) — dùng khi NV có BH đóng ở nơi khác (`employee_salaries.insurance_elsewhere`); KHÔNG trừ vào lương NV, chỉ hiển thị ở màn Sửa lương. Thêm qua migration 0096. |
| `phat_cap_pct` | `Numeric(6,4)` | no | `0.3` | **Trần khấu trừ kỷ luật** — mức **LUẬT** (Điều 102 BLLĐ 2019: phạt/bồi thường trừ vào lương không quá **30%** lương thực trả sau BHXH và TNCN), không phải chính sách công ty. `0` = **TẮT trần**: ghi phạt bao nhiêu trừ bấy nhiêu (`gross` vẫn có sàn 0, phần vượt KHÔNG dồn sang kỳ sau). Cột `payroll_lines.phat_bien_ban` luôn lưu số RAW chưa kẹp. Trước 29/07/2026 số 30% viết cứng trong `payroll_service._capped_penalty`. Thêm qua migration 0126. |
| `deduction_self` | `Numeric(14,2)` | no | `15500000` | Giảm trừ gia cảnh bản thân (TNCN, mức 2026 NQ 110/2025). |
| `deduction_dependent` | `Numeric(14,2)` | no | `6200000` | Giảm trừ mỗi người phụ thuộc (mức 2026). |
| `chuyen_can_default` | `Numeric(14,2)` | no | `300000` | Mức chuyên cần mặc định (đủ công). |
| `standard_hours_per_day` | `Numeric(5,2)` | no | `8` | Giờ công chuẩn/ngày (quy đơn giá giờ OT — Pha 4a). |
| `ot_multiplier` | `Numeric(5,2)` | no | `1.5` | Hệ số OT ngày thường (Đ98 ≥1.5 — Pha 4a). |
| `ot_multiplier_restday` | `Numeric(5,2)` | no | `2` | Hệ số OT ngày nghỉ tuần (Đ98 ≥2.0). Thêm qua migration 0064. |
| `ot_multiplier_holiday` | `Numeric(5,2)` | no | `3` | Hệ số OT ngày lễ (Đ98 ≥3.0). Thêm qua migration 0064. |
| `restday_work_multiplier` | `Numeric(5,2)` | no | `2` | Làm nguyên công ngày nghỉ tuần (Đ98 ≥200%). Thêm qua migration 0064. |
| `holiday_work_multiplier` | `Numeric(5,2)` | no | `3` | Làm nguyên công ngày lễ (Đ98 ≥300%). Thêm qua migration 0064. |
| `night_pct` | `Numeric(5,4)` | no | `0.3` | Phụ trội giờ đêm (dùng cho cộng dồn TĂNG CA ĐÊM Đ98.3, mặc định +30% = sàn luật). Khai được ở Cấu hình lương. Giờ đêm trong ca theo lịch dùng hệ số per-ca `work_shifts.night_multiplier`. |
| `ot_night_extra_pct` | `Numeric(6,4)` | no | `0.2` | Cộng dồn TĂNG CA ĐÊM (Đ98.3): +20% × hệ số loại ngày trên đơn giá giờ. Khai được. Thêm qua migration 0103. |
| `bh_base_cap` | `Numeric(14,2)` | no | `50600000` | Trần đóng BHXH+BHYT = 20× mức tham chiếu; 0 = không trần (Pha 4a). |
| `bhtn_base_cap` | `Numeric(14,2)` | no | `106200000` | Trần đóng BHTN = 20× lương tối thiểu vùng; 0 = không trần (Pha 4a). |
| `ot_max_minutes_per_month` | `Integer` | no | `0` | **TRẦN GIỜ LÀM THÊM MỘT THÁNG, tính bằng PHÚT** — số phút tối đa MỘT NGƯỜI được cấp phiếu trong MỘT tháng (Đ107 BLLĐ: 40 giờ = `2400`). **CHẶN CỨNG** khi tạo/sửa phiếu, **KHÔNG có đường vượt** (chủ chốt 17/08/2026) — hết trần thì lối duy nhất là nâng chính số này, mà nó áp cho CẢ công ty. Bộ đếm lấy phiếu ở trạng thái **chờ duyệt + đã duyệt** (phiếu chờ duyệt GIỮ CHỖ; từ chối/hủy trả chỗ ngay). ⚠️ `0` = **TẮT TRẦN** và là **mặc định** — cố ý, để migration chạy xong không chặn ai đột ngột. Chủ bật bằng cách gõ số ở Cấu hình lương. **KHÔNG có trần theo NĂM** — chủ đã bỏ 17/08/2026. Thêm qua migration 0206. |
| `ot_max_minutes_per_day` | `Integer` | no | `720` | Số PHÚT tối đa của **MỘT phiếu** tăng ca (Đ107.1: ≤ 12 giờ). Trước 17/08/2026 viết cứng ở hằng số `MAX_OT_MINUTES` trong `overtime_service`; đưa ra tham số vì ngưỡng luật đổi hằng năm. Thêm qua migration 0206. |
| `advance_max_pct` | `Numeric(6,4)` | no | `0.1` | TRẦN TẠM ỨNG/tháng: tổng tạm ứng 1 tháng của 1 NV ≤ tỷ lệ này × (lương vị trí + trách nhiệm). Đơn CHỜ DUYỆT cũng chiếm chỗ. `0` = không giới hạn. Thêm qua migration 0105. |
| `adjust_max_per_month` | `Integer` | no | `5` | HẠN MỨC CHỈNH CÔNG/tháng: mỗi NV tự gửi "Yêu cầu chỉnh công" cho tối đa ngần này **NGÀY CÔNG** (đếm `work_date` phân biệt, KHÔNG đếm số đơn — quên cả vào lẫn ra 1 ngày vẫn là 1 lượt). Đơn CHỜ DUYỆT cũng chiếm chỗ; bị từ chối/hủy thì trả lại. HCNS chấm bù TRỰC TIẾP không bị giới hạn. `0` = không giới hạn. Thêm qua migration 0114. |
| `pit_flat_rate` | `Numeric(6,4)` | no | `0.1` | Tỷ lệ **KHẤU TRỪ TẠI NGUỒN** cho HĐ dưới 3 tháng / thời vụ (`employees.pit_mode = khau_tru_10`). PHÂN SỐ: `0.10` = 10%. Khai được vì đây là số theo LUẬT, đổi theo luật — đừng viết cứng trong code. Thêm qua migration 0120. |
| `pit_flat_threshold` | `Numeric(14,2)` | no | `2000000` | Ngưỡng thu nhập MỖI LẦN TRẢ mới phải khấu trừ tại nguồn (hiện 2.000.000đ). Đi cặp với `pit_flat_rate`. Thêm qua migration 0120. |
| `phat_cap_pct` | `Numeric(6,4)` | no | `0.3` | **TRẦN KHẤU TRỪ KỶ LUẬT** — PHÂN SỐ (`0.30` = 30%). ⚠️ Đây là MỨC LUẬT, không phải chính sách công ty: Điều 102 BLLĐ 2019 giới hạn khấu trừ mỗi tháng không quá 30% lương còn lại sau khi trừ BHXH và TNCN. Trước viết cứng `0.30` trong `_capped_penalty`. `0` = TẮT TRẦN (ghi phạt bao nhiêu trừ bấy nhiêu; thực nhận vẫn có sàn 0, không âm) — màn Cấu hình lương cảnh báo khi đặt 0 hoặc > 30%. Thêm qua migration 0126. |
| `phu_cap_ca_min_cong` | `Numeric(5,2)` | no | `0.5` | **NGƯỠNG CÔNG để hưởng phụ cấp cơm/ca của một ngày** (chủ chốt 03/08/2026). Ngày có `cong >= ` số này thì hưởng **TRỌN** mức của ca; dưới ngưỡng thì **KHÔNG có gì** — cố ý **KHÔNG nhân theo tỷ lệ**: một suất ăn là có hoặc không, nhân tỷ lệ thì đi muộn 15 phút (công 0,97) ra 24.250đ tiền cơm. `0.5` = nghỉ nửa buổi vẫn được hưởng. ⚠️ Hệ thống KHÔNG có cờ "nửa buổi" — đi muộn/về sớm/nghỉ nửa buổi dùng chung `late_early_requests` và engine chỉ đọc ĐỘ DÀI khoảng vắng, nên luật buộc phải diễn đạt theo `cong`. Thêm qua migration 0157. |
| `com_tang_ca_nguong_phut` | `Integer` | no | `180` | Ngưỡng phút tăng ca trong MỘT NGÀY để được suất cơm — chỉ áp cho NGÀY LÀM VIỆC. Ngày nghỉ theo Lịch chung (gồm lễ, off1x) cứ có tăng ca là có suất. Thêm qua migration 0190. |
| `com_tang_ca_muc` | `Numeric(14,2)` | no | `0` | Tiền MỘT suất cơm tăng ca. Mặc định 0 = TẮT (chủ tự khai) — cùng lối `cong_doan_rate`. Thêm qua migration 0190. |
| `bhxh_mien_tu_so_ngay` | `Integer` | no | `14` | **SỐ NGÀY nghỉ không lương trong tháng mà từ đó tháng đó KHÔNG ĐÓNG BHXH.** ⚠️ MỨC LUẬT, không phải chính sách công ty: QĐ 595/QĐ-BHXH Đ42.4 — không làm việc và không hưởng tiền lương từ **14 ngày làm việc** trở lên trong tháng thì tháng đó không đóng BHXH. Engine đếm `ngay_khong_luong = standard_cong − actual_cong − plain_cong` (`plain_cong` là ngày off1x CÓ đi làm và CÓ trả 1× nên phải cộng lại, không thì người làm ngày đó mất BHXH oan). `0` = **TẮT LUẬT**: tháng nào cũng trừ BHXH, như hành vi trước 04/08/2026 — engine kiểm `> 0` TRƯỚC khi so, thiếu chốt đó thì `>= 0` luôn đúng và cả xưởng mất sạch BHXH. Trước 04/08/2026 số 14 viết cứng trong `payroll_service`. Thêm qua migration 0158. |
| `updated_at` | `DateTime(tz)` | no | now | Lần cập nhật. |

---

### `department_salary_components`

**Purpose:** bật/tắt + MỨC từng thành phần lương theo BỘ PHẬN (màn "Cấu hình lương" Tab 2). Cấu
hình theo TỔ (2 cấp NV → tổ): không có dòng = "chưa khai" (rơi xuống tham số chung với chuyên cần);
`is_enabled=false` = TẮT hẳn khoản đó cho cả bộ phận (cấp NV cũng không được cộng). 4 khoản còn khai
theo tổ: `chuyen_can`/`luong_khoan`/`tang_ca` (phụ cấp ca/thâm niên/khác đã chuyển sang KHAI TAY
theo từng NV ở `employee_salaries`). Bảng do `create_all` tạo.

| Column           | Type            | Key                                 | Null | Default | Meaning                                            |
| ---------------- | --------------- | ----------------------------------- | ---- | ------- | -------------------------------------------------- |
| `id`             | `Integer`       | **PK**                              | no   | auto    | PK.                                                |
| `department_id`  | `Integer`       | **FK→departments.id**, **IX**       | no   | —       | Bộ phận sở hữu; xóa phòng thì xóa dòng (CASCADE).  |
| `component_key`  | `String(32)`    | **U(department_id, component_key)** | no   | —       | `chuyen_can`/`luong_khoan`/`tang_ca`. Khoá `kpi` (thưởng năng suất) ĐÃ GỠ 29/07/2026 — migration 0130 xoá cả 2 cột `payroll_lines.kpi_*` lẫn các dòng cấu hình `kpi` ở bảng này. |
| `is_enabled`     | `Boolean`       | —                                   | no   | `true`  | Bộ phận có áp dụng khoản này không.                |
| `value`          | `Numeric(14,2)` | —                                   | yes  | —       | Mức của bộ phận; NULL = bật nhưng chưa khai mức (chuyên cần rơi về tham số chung). |
| `updated_at`     | `DateTime(tz)`  | —                                   | no   | now     | Lần cập nhật.                                      |

**Keys & indexes**

- Primary key: `id`. Foreign key: `department_id FK→departments.id` (CASCADE).
- Unique: `(department_id, component_key)` — `uq_dept_salary_component`.
- Index: `ix_department_salary_components_department_id`.

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
| `amount_mode`    | `String(8)`     | —                           | no   | `rule`  | rule (tra bảng) / manual (nhập tay) / dept_row (dòng bảng lương tổ). |
| `base_amount`    | `Numeric(14,2)` | —                           | yes  | —       | Mức tháng khi manual.                |
| `source_salary_row_id` | `Integer` | —                           | yes  | —       | LEGACY soft-ref `department_salary_rows` khi amount_mode=dept_row (đọc sống) — vừa là bậc vừa là nguồn tiền; PRD v2 tách 2 vai. |
| `luong_vi_tri`   | `Numeric(14,2)` | —                           | no   | `0`     | **Mức hợp đồng RIÊNG của NV — lương vị trí** (PRD v2 C2). Mức nền = vị trí + trách nhiệm (gốc prorate theo công + gốc tính tăng ca). Thêm qua migration 0088 (backfill từ dòng bậc → lương KHÔNG đổi). |
| `luong_trach_nhiem` | `Numeric(14,2)` | —                        | no   | `0`     | **Mức hợp đồng RIÊNG của NV — lương trách nhiệm**. Thêm qua migration 0088. |
| `luong_dot_1` | `Numeric(14,2)` | — | no | `0` | "Lương trả 1 lần" — số cố định điền sẵn khi tạo phiếu thanh toán lương đợt 1. Migration 0106. |
| `insurance_base` | `Numeric(14,2)` | —                           | yes  | —       | Mức đóng BH (NULL = mức lương).      |
| `allowance`      | `Numeric(14,2)` | —                           | no   | `0`     | **Phụ cấp KHÁC** của riêng NV (xăng/điện thoại/kiêm nhiệm…) — KHAI TAY, cộng phẳng (không prorate theo công, không vào gốc tính tăng ca). |
| `phu_cap_ca`     | `Numeric(14,2)` | —                           | no   | `0`     | **Phụ cấp CA** (ca đêm/ca tới sáng/cơm ca…) — KHAI TAY một số cố định dùng mọi tháng; hệ thống KHÔNG tự tính. Vào dòng lương ở `payroll_lines.night_pay`. Thêm qua migration 0090. |
| `phu_cap_tham_nien` | `Numeric(14,2)` | —                        | no   | `0`     | **Phụ cấp THÂM NIÊN** — KHAI TAY (bỏ hẳn cách tự tính theo số kỳ 6 tháng). Thêm qua migration 0090. |
| `chuyen_can`     | `Numeric(14,2)` | —                           | no   | `0`     | Chuyên cần của riêng NV (all-or-nothing, chỉ khi đủ công). |
| `insurance_elsewhere` | `Boolean`  | —                           | no   | `false` | Cờ **"BH đóng ở nơi khác"** — NV được nơi khác đóng BHXH/BHYT/BHTN → công ty KHÔNG trừ 3 khoản này của NV, chỉ chịu TNLĐ-BNN (`payroll_params.tnld_bnn_rate`). Đoàn phí CĐ theo `union_member`. Thêm qua migration 0096. |
| `union_member` | `Boolean` | —                           | no   | `false` | Cờ **"đoàn viên công đoàn"** — CHỈ đoàn viên mới bị trừ đoàn phí công đoàn (`payroll_params.cong_doan_rate`). Mặc định false = opt-in. Thêm qua migration 0097. |
| `apply_self_deduction` | `Boolean` | —                  | no   | `true`  | Có áp **GIẢM TRỪ BẢN THÂN** khi tính TNCN không. Người làm 2 nơi chỉ được đăng ký giảm trừ bản thân ở MỘT nơi — bỏ tích ở nơi còn lại. Mặc định BẬT (đại đa số chỉ làm một nơi; tắt là ngoại lệ). Giảm trừ NGƯỜI PHỤ THUỘC không đụng cờ này (theo `employees.dependents_count`). Thêm qua migration 0119. |
| `commission_pct` | `Numeric(6,4)` | —                  | no   | `0`     | **% HOA HỒNG** của nhân viên kinh doanh. PHÂN SỐ: `0.05` = 5%, đúng quy ước `cong_doan_rate`/`phat_cap_pct`. `0` = không hưởng (mặc định). Để ở bảng NÀY chứ không ở `employees` là có chủ đích: bảng này versioned theo `effective_from` ⇒ đổi % từ tháng sau thì kỳ tháng trước tính lại vẫn ra số cũ. ⚠️ **ĐỢT NÀY CHỈ KHAI** — `_compute` KHÔNG đọc cột này, khai bao nhiêu cũng không đổi một đồng; ra tiền cần `orders.commission_pct` + Σ phiếu thu theo đơn. Thêm qua migration 0128. |
| `note`           | `String(255)`   | —                           | yes  | —       | Ghi chú.                             |
| `created_by`     | `Integer`       | **FK→users.id**             | yes  | —       | Người khai/điều chỉnh.               |
| `created_at`     | `DateTime(tz)`  | —                           | no   | now     | Khi tạo.                             |

---

### `salary_advances`

**Purpose:** tạm ứng lương (đa lần/tháng), gắn kỳ `(period_year, period_month)`. Workflow duyệt.

| Column          | Type            | Key                         | Null | Default   | Meaning                              |
| --------------- | --------------- | --------------------------- | ---- | --------- | ------------------------------------ |
| `id`            | `Integer`       | **PK**                      | no   | auto      | PK.                                  |
| `code`          | `String(32)`    | **UQ**, **IX**              | yes  | —         | Mã tạm ứng TU26-xxxx (sinh khi tạo); hàng cũ backfill `TU-<id>`. |
| `employee_id`   | `Integer`       | **FK→employees.id**, **IX** | no   | —         | NV ứng; `ON DELETE CASCADE`.         |
| `period_year`   | `Integer`       | **IX**                      | no   | —         | Năm kỳ lương áp dụng.                |
| `period_month`  | `Integer`       | **IX**                      | no   | —         | Tháng kỳ lương áp dụng.              |
| `advance_date`  | `Date`          | —                           | no   | —         | Ngày ứng.                            |
| `amount`        | `Numeric(14,2)` | —                           | no   | —         | Số tiền ứng.                         |
| `reason`        | `String(255)`   | —                           | yes  | —         | Lý do.                               |
| `kind`          | `String(16)`    | —                           | no   | `tam_ung` | Loại phiếu: `tam_ung` (ad-hoc) \| `luong_dot_1` (thanh toán lương đợt 1). Migration 0107. |
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
| `generated_at` | `DateTime(tz)` | — | yes | — | Lần chạy engine (Tính lại) gần nhất. So với `attendance_periods.locked_at` để chặn chốt lương trên số tính TRƯỚC lúc chốt công. NULL = kỳ có từ trước migration `0186`. |
| `cong_bo_luc` | `DateTime(tz)` | — | yes | — | Mốc MỞ phiếu lương cho NLĐ. NULL = chưa công bố. Mốc tương lai = đã hẹn giờ. Mở lại kỳ ⇒ tự về NULL. Thêm qua migration `0187`. |
| `dong_phieu_luc` | `DateTime(tz)` | — | yes | — | Mốc ĐÓNG phiếu. NULL = mở không thời hạn. Cùng `cong_bo_luc` tạo một CỬA SỔ: NV thấy phiếu khi `cong_bo_luc <= now < dong_phieu_luc` — kiểm lúc ĐỌC, không cần job nền. Thêm qua migration `0189`. |

---

### `payroll_lines`

**Purpose:** dòng lương 1 NV trong 1 kỳ (snapshot). UNIQUE(`period_id`,`employee_id`).

> ⚠️ **6 cột thưởng đã NGỪNG GHI (28/07/2026):** `thuong_5s` · `thuong_doanh_so` ·
> `thuong_thanh_tich` · `phep_nam` · `tra_dong_phuc` · `other_bonus`. Chúng bị **đóng đinh chịu
> thuế**, không khai được "miễn thuế". Nay mọi khoản thưởng khai qua `payroll_line_components`
> (chọn từ danh mục ⇒ cờ `is_taxable` là quy tắc chung). Cột **vẫn còn và vẫn được engine cộng
> vào `gross`** để kỳ ĐÃ CHỐT giữ nguyên số; chỉ chặn ghi mới (bỏ khỏi `LineUpdateIn`).
> Migration `0124` đã dời số của các kỳ **draft** sang `payroll_line_components`.

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `period_id` | `Integer` | **FK→payroll_periods.id**, **IX** | no | — | Kỳ lương; `ON DELETE CASCADE`. |
| `employee_id` | `Integer` | **FK→employees.id**, **IX** | no | — | NV; `ON DELETE CASCADE`. |
| `is_probation` | `Boolean` | — | no | `false` | Thử việc (áp %thử việc). |
| `actual_cong` | `Numeric(6,2)` | — | no | `0` | Số công thực (từ Chấm công). |
| `standard_cong` | `Numeric(6,2)` | — | no | `26` | Công chuẩn kỳ. |
| `monthly_salary` | `Numeric(14,2)` | — | no | `0` | Mức lương tháng (đã giải). |
| `luong_cong` | `Numeric(14,2)` | — | no | `0` | Lương theo công (đã gồm phần ngày phép ở dòng dưới). |
| `luong_ngay_phep` | `Numeric(14,2)` | — | no | `0` | **TRONG ĐÓ** của `luong_cong`: tiền những ngày nghỉ phép, trả theo **lương vị trí** (không lương trách nhiệm). ĐỪNG cộng lại vào gross. Khác cột tay `phep_nam`. Thêm qua migration 0112. |
| `paid_leave_cong` | `Numeric(6,2)` | — | no | `0` | Số công phép CÓ LƯƠNG thực được trả (sau khi kẹp trần công chuẩn). Thêm qua migration 0112. |
| `special_cong` | `Numeric(6,2)` | — | no | `0` | **TRONG ĐÓ** của `actual_cong`: số công của **ngày LỄ / NGHỈ TUẦN có đi làm**. Tách riêng vì phần công này **KHÔNG đi qua trần** `min(công làm, công chuẩn)` — trước 17/08/2026 nó nằm chung rổ nên ai đã đủ công chuẩn rồi mới làm Chủ nhật thì phần gốc 1× bị trần nuốt, `ot_pay` chỉ bù `(hệ số − 1)` ⇒ thực nhận **1× thay vì 2×** (lễ: 2× thay vì 3×), trái Đ98.1.b/c. Snapshot để đường "Sửa 1 ô" (`update_line`) ra đúng số của "Tính lại". ĐỪNG cộng vào gross: đã nằm trong `luong_cong`. Kỳ cũ = `0` ⇒ **không hồi tố**. Thêm qua migration 0204. |
| `off1x_pay` | `Numeric(14,2)` | — | no | `0` | **TRONG ĐÓ** của `ot_pay`: tiền của **ngày off1x** (công ty cho nghỉ, ai đi làm được trả 1×, không hệ số). Tách riêng vì khoản này **CHỊU thuế TNCN** — trả đúng 1× nên không có phần "trả cao hơn" nào để miễn theo Luật 109/2025 K8 Đ4 + NĐ 253/2026 Đ26 (kế toán chốt 17/08/2026: *"lương thuế chỉ 1 công bình thường"*). `_auto_pit` nhận nó qua tham số `ot_taxable` và cộng ngược vào thu nhập chịu thuế. Snapshot để đường "Sửa 1 ô" ra đúng số của "Tính lại". **ĐỪNG cộng vào gross**: đã nằm trong `ot_pay`. Kỳ cũ = `0` ⇒ **không hồi tố**. Thêm qua migration 0205. |
| `excused_cong` | `Numeric(6,2)` | — | no | `0` | Công thiếu ĐƯỢC PHÉP (đơn nghỉ theo giờ đã duyệt) — chỉ để giải trình vì sao công thiếu mà chuyên cần vẫn đủ. Thêm qua migration 0112. |
| `chuyen_can` | `Numeric(14,2)` | — | no | `0` | Thưởng chuyên cần. |
| `allowance` | `Numeric(14,2)` | — | no | `0` | TỔNG phụ cấp tháng = phụ cấp KHÁC + trách nhiệm + thâm niên (2 cột dưới). Phụ cấp CA đi riêng ở `night_pay`. |
| `phu_cap_tham_nien` | `Numeric(14,2)` | — | no | `0` | **TRONG ĐÓ** của `allowance` — chép từ `employee_salaries.phu_cap_tham_nien`. Như trên: không cộng thêm vào gross. Thêm qua migration 0089. |
| `khoan` | `Numeric(14,2)` | — | no | `0` | Lương khoán (nhịp 2, từ sổ khoán). Thêm qua migration 0013. |
| `ot_minutes` | `Integer` | — | no | `0` | Tổng phút tăng ca (từ Chấm công). Thêm qua migration 0043. |
| `ot_pay` | `Numeric(14,2)` | — | no | `0` | Tiền tăng ca (hệ số phẳng). Thêm qua migration 0043. |
| `night_days` | `Integer` | — | no | `0` | Số ngày làm ca đêm (từ Chấm công) — chỉ để tham khảo, KHÔNG ra tiền. Thêm qua migration 0043. |
| `night_pay` | `Numeric(14,2)` | — | no | `0` | ⚠️ **NGƯNG từ 03/08/2026 — luôn 0.** Trước đây = số KHAI TAY ở `employee_salaries.phu_cap_ca` (cộng phẳng) và được miễn TNCN. Phần miễn đó là **di sản**: ô này vốn là tiền ca đêm ĐƯỢC TÍNH (đơn giá tổ × số lượt, bỏ ở mg 0090), khi đổi sang số gõ tay thì phần miễn bị bê nguyên sang — mà TT 111/2013 Đ3.1.i chỉ miễn **phần trả CAO HƠN** gắn với giờ đêm/tăng ca THỰC TẾ. Nay phụ cấp cơm/ca tính theo CA THỰC LÀM (2 cột dưới); cột này GIỮ để không mất lịch sử kỳ đã chốt. API vẫn phơi alias `ca_pay`. |
| `meal_allowance_pay` | `Numeric(14,2)` | — | no | `0` | Tiền **CƠM CA** = `work_shifts.meal_allowance` × số ngày THỰC LÀM ca đó. Thêm qua migration 0157. |
| `com_tang_ca_pay` | `Numeric(14,2)` | — | no | `0` | Tiền cơm **TĂNG CA** của kỳ. Cột RIÊNG, không gộp `meal_allowance_pay`: hai khoản khác luật và một ngày có thể ăn cả hai. Miễn TNCN như cơm ca. Thêm qua migration 0190. |
| `shift_allowance_pay` | `Numeric(14,2)` | — | no | `0` | **PHỤ CẤP CA** = `work_shifts.shift_allowance` × số ngày THỰC LÀM ca đó. Tách RIÊNG khỏi cột trên vì tiền ăn giữa ca có trần miễn thuế riêng (730k/tháng) — gộp một cục là mất đường tách sau. Cả hai **CHỊU thuế TNCN**; khoản nào thật sự miễn thì khai ở danh mục khoản thu nhập có cờ `is_taxable`. Thêm qua migration 0157. |
| `night_premium_pay` | `Numeric(14,2)` | — | no | `0` | **Premium CA ĐÊM theo GIỜ** (giờ 22h–06h × hệ số ca + tăng ca đêm Đ98.3) — tự tính từ chấm công, DÒNG RIÊNG, miễn TNCN. Thêm qua migration 0102. |
| `vi_pham` | `Numeric(14,2)` | — | no | `0` | Giảm trừ khác (nhập tay, RAW; gộp trần 30% Đ102). |
| `other_bonus` | `Numeric(14,2)` | — | no | `0` | ⚠️ **CỘT CŨ — NGỪNG GHI từ 28/07/2026.** Thưởng khác/hoa hồng (nhập tay). |
| `thuong_5s` | `Numeric(14,2)` | — | no | `0` | ⚠️ **CỘT CŨ — NGỪNG GHI từ 28/07/2026.** Thưởng 5S. Thêm qua migration 0074. |
| `thuong_doanh_so` | `Numeric(14,2)` | — | no | `0` | ⚠️ **CỘT CŨ — NGỪNG GHI từ 28/07/2026.** Thưởng doanh số. Thêm qua migration 0074. |
| `thuong_thanh_tich` | `Numeric(14,2)` | — | no | `0` | ⚠️ **CỘT CŨ — NGỪNG GHI từ 28/07/2026.** Thưởng thành tích. Thêm qua migration 0074. |
| `phep_nam` | `Numeric(14,2)` | — | no | `0` | ⚠️ **CỘT CŨ — NGỪNG GHI từ 28/07/2026.** Tiền phép năm nhập tay. Engine đã tự trả tiền ngày nghỉ phép ở `luong_ngay_phep` ⇒ ô này là đường trả HAI LẦN, nay `_RESERVED` chặn cả việc tạo khoản danh mục trùng tên. Thêm qua migration 0074. |
| `tra_dong_phuc` | `Numeric(14,2)` | — | no | `0` | ⚠️ **CỘT CŨ — NGỪNG GHI từ 28/07/2026.** Trả tiền đồng phục (cn thôi việc). Thêm qua migration 0074. |
| `dieu_chinh_luong` | `Numeric(14,2)` | — | no | `0` | Điều chỉnh lương (±, cộng đại số). Thêm qua migration 0074. |
| `di_tre` | `Numeric(14,2)` | — | no | `0` | Phạt đi trễ/về sớm/nghỉ KP (RAW). Tự động từ chấm công (bảng phạt × số phút vi phạm không phép mỗi ngày) trừ khi `di_tre_manual`. Thêm qua migration 0074. |
| `di_tre_manual` | `Boolean` | — | no | `false` | HCNS sửa tay ô "Đi trễ" → khóa không cho phạt tự động (từ chấm công) đè khi Tính lại. Mirror `pit_manual`. Thêm qua migration 0099. |
| `dt_vuot_troi` | `Numeric(14,2)` | — | no | `0` | Trừ điện thoại vượt trội (RAW). Thêm qua migration 0074. |
| `phat_bien_ban` | `Numeric(14,2)` | — | no | `0` | Phạt biên bản vi phạm (RAW). Thêm qua migration 0074. |
| `phat_5s_dong_phuc` | `Numeric(14,2)` | — | no | `0` | Tiền đồng phục/phạt 5S (RAW). Thêm qua migration 0074. |
| `gross` | `Numeric(14,2)` | — | no | `0` | Tổng thu nhập trước khấu trừ. |
| `insurance_base` | `Numeric(14,2)` | — | no | `0` | Mức đóng BH. |
| `bhxh` | `Numeric(14,2)` | — | no | `0` | Khấu trừ BHXH/BHYT/BHTN. |
| `cong_doan` | `Numeric(14,2)` | — | no | `0` | Đoàn phí công đoàn = insurance_base×cong_doan_rate (tự tính, thử việc=0). Thêm qua migration 0074. |
| `pit` | `Numeric(14,2)` | — | no | `0` | Thuế TNCN (tự tính, có thể ghi đè tay). |
| `pit_manual` | `Boolean` | — | no | `false` | TNCN do HCNS ghi đè tay (không auto ghi đè). Thêm qua migration 0044. |
| `pit_taxable` | `Numeric(14,2)` | — | no | `0` | Thu nhập **TÍNH** thuế đã dùng để tính TNCN (đã trừ BHXH + giảm trừ gia cảnh). Thêm qua migration 0044. ⚠️ KHÔNG phải `thu_nhap_chiu_thue` — hai số cách nhau ~15,5tr, dùng lẫn là sai thuế. |
| `thu_nhap_chiu_thue` | `Numeric(14,2)` | — | no | `0` | Thu nhập **CHỊU** thuế của kỳ = tổng lương − các khoản miễn, TRƯỚC mọi giảm trừ. Số DẪN XUẤT, không cộng vào gross lần nữa. Thêm qua migration 0118. |
| `thu_nhap_mien_thue` | `Numeric(14,2)` | — | no | `0` | Thu nhập **MIỄN** thuế của kỳ = tăng ca + ca đêm + các khoản trong `payroll_components` có `is_taxable = false`. Số DẪN XUẤT, không cộng vào gross lần nữa. Thêm qua migration 0115. |
| `advance_total` | `Numeric(14,2)` | — | no | `0` | Tổng tạm ứng đã duyệt (kind=tam_ung). |
| `luong_dot_1_total` | `Numeric(14,2)` | — | no | `0` | Tổng "thanh toán lương đợt 1" đã duyệt (kind=luong_dot_1) của kỳ. Migration 0108. |
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

### `payroll_components`

**Purpose:** DANH MỤC khoản thu nhập / khấu trừ của bảng lương (chủ 2026-07-27). Thay cho ô "Phụ cấp
KHÁC" gộp một cục — mỗi khoản một dòng, HCNS tự thêm/xoá/bật tắt, và mỗi khoản mang cờ `is_taxable`
là nguồn DUY NHẤT trả lời "khoản này có tính thuế TNCN không". Bảng do `create_all` tạo (không
migration); seed-once 21 khoản theo bảng lương kế toán đang dùng. **Xoá:** khoản đã dùng ở kỳ lương
nào thì KHÔNG xoá cứng, chỉ `is_active=false` — xoá cứng là phiếu lương kỳ cũ mất dòng, tổng không
còn khớp chữ ký người nhận.

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `code` | `String(40)` | **U**, **IX** | no | — | Mã khoản (vd `trang_phuc`). |
| `name` | `String(120)` | — | no | — | Tên hiện trên phiếu lương. |
| `kind` | `String(8)` | — | no | `thu` | `thu` = cộng vào tổng lương · `tru` = khấu trừ. |
| `is_taxable` | `Boolean` | — | no | `true` | **Có tính vào thu nhập chịu thuế TNCN không.** `false` = miễn. |
| `in_insurance_base` | `Boolean` | — | no | `false` | Có cộng vào gốc đóng BH không (mặc định KHÔNG — gốc đóng BH là `luong_vi_tri`). |
| `sort_order` | `Integer` | — | no | `0` | Thứ tự hiện trên phiếu lương. |
| `is_active` | `Boolean` | — | no | `true` | `false` = ngưng dùng (ẩn khỏi form nhập mới, kỳ cũ vẫn hiện). |
| `note` | `String(255)` | — | yes | — | Ghi chú. |
| `created_at` | `DateTime(tz)` | — | no | now | Thời điểm tạo. |

- Keys & indexes: PK `id`; UNIQUE `code`; index `code`.
- Relationships: referenced by `payroll_group_components.component_id` và
  `employee_salary_components.component_id` (cả hai ON DELETE CASCADE).

---

### `employee_salary_components`

**Purpose:** mức của một khoản cho MỘT NGƯỜI — đè lên mức mặc định của nhóm lương. Cố ý KHÔNG
version theo `effective_from` như `employee_salaries`: kỳ lương đã chốt vốn đã đóng băng ở
`payroll_lines`, thêm một trục version nữa chỉ tạo chỗ để lệch. Bảng do `create_all` tạo (không
migration).

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `employee_id` | `Integer` | **FK→employees.id**, **IX** | no | — | Nhân viên; `ON DELETE CASCADE`. |
| `component_id` | `Integer` | **FK→payroll_components.id**, **IX** | no | — | Khoản trong danh mục; `ON DELETE CASCADE`. |
| `amount` | `Numeric(14,2)` | — | no | `0` | Mức của riêng người này (đồng). |
| `note` | `String(255)` | — | yes | — | Ghi chú tự do — cho khoản "Thu nhập khác" lưu vết vì sao có khoản này (vd "Phụ cấp tiếng Nhật theo dự án X"). Chép sang snapshot dòng lương. Thêm qua migration 0121. |
| `created_at` | `DateTime(tz)` | — | no | now | Thời điểm tạo. |

- Keys & indexes: PK `id`; UNIQUE `(employee_id, component_id)` = `uq_employee_component`; index `employee_id`, `component_id`.
- Relationships: `employee_id FK→employees.id` (CASCADE), `component_id FK→payroll_components.id` (CASCADE).

---

### `payroll_line_components`

**Purpose:** SNAPSHOT từng khoản trên MỘT dòng lương — để phiếu lương hiện được từng khoản, và để
kỳ đã chốt giữ nguyên số cũ. Chép cả `code`/`name`/`kind`/`is_taxable` tại thời điểm tính chứ không
chỉ trỏ `component_id`: sau này chủ đổi tên khoản hay bỏ tích "Chịu thuế" thì phiếu lương các kỳ CŨ
vẫn in ra đúng y lúc trả tiền. Bảng do `create_all` tạo (không migration).

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `line_id` | `Integer` | **FK→payroll_lines.id**, **IX** | no | — | Dòng lương; `ON DELETE CASCADE`. |
| `component_id` | `Integer` | **IX** | no | — | Soft-ref `payroll_components.id` (KHÔNG FK cứng — khoản có thể bị xoá, snapshot vẫn đứng vững). |
| `code` | `String(40)` | — | no | — | Mã khoản, chép lúc tính. |
| `name` | `String(120)` | — | no | — | Tên khoản, chép lúc tính (phiếu lương in theo tên này). |
| `kind` | `String(8)` | — | no | — | `thu` / `tru`, chép lúc tính. |
| `is_taxable` | `Boolean` | — | no | `true` | Cờ chịu thuế TẠI THỜI ĐIỂM TÍNH — đổi cờ ở danh mục không sửa số kỳ cũ. |
| `amount` | `Numeric(14,2)` | — | no | `0` | Số tiền khoản này trên dòng lương (đồng). |
| `source` | `String(8)` | — | no | `employee` | NGUỒN dòng này: `employee` = chép từ hồ sơ NV ⇒ bị GHI ĐÈ mỗi lần "Tính lại"; `line` = HCNS thêm tay cho RIÊNG kỳ này (thưởng nóng) ⇒ GIỮ NGUYÊN qua mọi lần tính lại và KHÔNG lặp sang kỳ sau. Thiếu cột này thì "Tính lại" xoá sạch thưởng nóng. Thêm qua migration 0121. |
| `da_de_tay` | `Boolean` | — | no | `false` | HCNS đã SỬA TAY số tiền của dòng này cho RIÊNG kỳ này. Dòng đè vẫn giữ `source='employee'` nhưng được miễn khỏi lượt xoá-ghi-lại của "Tính lại", và `generate` phải BỎ QUA khoản hồ sơ đã có dòng đè (quên là sinh dòng trùng, NV ăn hai lần). Thêm qua migration `0188`. |
| `note` | `String(255)` | — | yes | — | Ghi chú (vd "Thưởng nóng của Sếp"). Thêm qua migration 0121. |

- Keys & indexes: PK `id`; UNIQUE `(line_id, component_id)` = `uq_line_component`; index `line_id`, `component_id`.
- Relationships: `line_id FK→payroll_lines.id` (CASCADE). `component_id` là soft-ref, KHÔNG FK.

---

### `late_penalty_brackets`

**Purpose:** bảng phạt đi trễ / về sớm KHÔNG phép (toàn công ty) — dữ liệu SỬA ĐƯỢC (PRD §4/D11).
Bảng do `create_all` tạo (không migration); seed-once 4 bậc mặc định (20k/40k/100k/150k). Engine
CHƯA tự áp bảng này (auto-tính từ chấm công là Đợt 2) — hiện chỉ lưu + phơi + sửa + tra tay ở
helper "Tính nhanh phạt" của modal Sửa lương.

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `seq` | `Integer` | — | no | — | Thứ tự bậc (1..N). |
| `up_to_minute` | `Integer` | — | yes | — | Trần số PHÚT trễ/sớm của bậc; NULL = bậc cao nhất (∞, trên 1 giờ). |
| `amount` | `Numeric(14,2)` | — | no | — | Tiền phạt/lần (đồng). |

---

### `piece_rates`

**Purpose:** đơn giá khoán (Lương khoán nhịp 2) theo tổ + đơn vị (m²/bài in/tấn/cuốn/lượt/hộp).

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `group_name` | `String(40)` | **IX** | no | — | Tổ khoán (to_boi/to_cat/may_in_5mau…). |
| `department_id` | `Integer` | **IX** | yes | — | Tổ sở hữu đơn giá (ref `departments.id`); khai trong Cấu hình lương của tổ. |
| `code` | `String(20)` | — | yes | — | Mã (A–F cho máy in). |
| `name` | `String(255)` | — | no | — | Tên công việc. |
| `cong_doan` | `String(30)` | **IX** | yes | — | **CỘT CHẾT** — trước tra đơn giá theo (tổ + công đoạn). Bảng này giờ là KHAI BÁO thuần: đơn giá chỉ treo vào TỔ, việc nào dùng dòng nào là bên sản xuất chọn ở bước lệnh. Giữ cột để không mất dữ liệu cũ, không đọc ở đâu nữa. |
| `unit` | `String(12)` | — | no | `khac` | Đơn vị (m2/bai_in/tan/cuon/luot/hop/to/khac). |
| `unit_price` | `Numeric(14,2)` | — | no | — | Đơn giá/đơn vị. |
| `note` | `String(255)` | — | yes | — | Ghi chú. |
| `is_active` | `Boolean` | — | no | `true` | Đang dùng. |
| `created_at` | `DateTime(tz)` | — | no | now | Khi tạo. |

---

### `piece_leader_bonus_brackets`

**Purpose:** bậc **THƯỞNG/PHẠT TỔ TRƯỞNG** theo **tỷ lệ hàng lỗi** của tổ (chủ 29/07/2026).
Tổ trưởng chịu trách nhiệm chất lượng nên thu nhập gắn với tỷ lệ lỗi: làm tốt được thưởng thêm,
để lỗi nhiều thì bị trừ — tính bằng **% trên TỔNG TIỀN KHOÁN của tổ** (*"% này là tiền đó nha"*).

**Mỗi TỔ một bộ mốc riêng** (`department_id`) — khác `late_penalty_brackets` / `pit_tax_brackets`
vốn là bảng toàn công ty. Cách tra thì y hệt: bậc **ĐẦU TIÊN** có `tỷ lệ lỗi ≤ up_to_defect_pct`
thắng; `up_to_defect_pct = NULL` là bậc cao nhất (∞), đúng MỘT bậc và phải nằm cuối.

Ví dụ: `≤5% → +2,00` · `≤10% → 0,00` · `(∞) → −10,00`.

> ⚠️ **ENGINE CHƯA ÁP BẢNG NÀY.** Tiền tính trên tổng khoán của tổ, mà tổng khoán hiện **luôn = 0**:
> `PieceWorkService.khoan_map` đọc từ `self.outputs`, nhưng `ProductionOutputRepository` **không tồn
> tại trong code** và `deps.py` truyền `outputs=None`. Khai mốc là chuẩn bị sẵn; nối vào lương cùng
> lúc dựng lại nguồn sản lượng. Màn khai có banner nói thẳng điều này.

Bảng do `create_all` tạo (không migration).

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `department_id` | `Integer` | **IX** | no | — | Tổ sở hữu bộ mốc. Soft-ref `departments.id` (không FK cứng, giống `piece_rates`). |
| `seq` | `Integer` | — | no | — | Thứ tự bậc 1..N. |
| `up_to_defect_pct` | `Numeric(6,2)` | — | yes | — | **Trần % HÀNG LỖI** của bậc. `NULL` = bậc cao nhất (∞) — đúng MỘT bậc, phải ở cuối. |
| `rate_pct` | `Numeric(6,2)` | — | no | — | **% trên TỔNG TIỀN KHOÁN của tổ. DƯƠNG = thưởng · ÂM = phạt.** Gõ nhầm dấu là đảo ngược ý nghĩa của bậc. |
| `note` | `String(255)` | — | yes | — | Ghi chú bậc. |
| `created_at` | `DateTime(tz)` | — | no | now | Khi tạo. |

**Keys & indexes**

- Primary key: `id`. Index: `department_id`. Không UNIQUE — bộ mốc được thay CẢ BỘ (xoá-ghi-lại)
  chứ không sửa lẻ từng dòng.

---

### `piece_leader_bonus_settings`

**Purpose:** **NGƯỠNG tối thiểu để xét** thưởng/phạt tổ trưởng — mỗi tổ một dòng (chủ 30/07/2026:
*"ở đó mới có Tỷ lệ lỗi tới nhưng không biết nằm trong phạm vi sản lượng là bao nhiêu"*).

**Vì sao cần:** bảng bậc chỉ có MỘT chiều là tỷ lệ lỗi, nên tổ làm rất ít và tổ làm rất nhiều bị đối
xử như nhau. Tệ hơn: **làm càng ít thì tỷ lệ lỗi càng vô nghĩa** — hỏng 2 tờ trên 20 tờ đã là 10%,
đủ rơi xuống bậc phạt nặng nhất dù thực tế chẳng làm được gì.

```
sản lượng của tổ  <  ngưỡng  ⇒  KHÔNG thưởng, KHÔNG phạt, bất kể tỷ lệ lỗi
sản lượng của tổ  ≥  ngưỡng  ⇒  áp bảng bậc như thường   (">=", KHÔNG phải ">")
ngưỡng = 0 / chưa khai       ⇒  KHÔNG gác
chưa biết sản lượng          ⇒  COI NHƯ dưới ngưỡng (fail-closed)
```

Đừng lẫn hai con số: **ngưỡng đo bằng SỐ LƯỢNG**, còn **% thưởng/phạt vẫn nhân trên TIỀN** — tổng
`payroll_lines.khoan` của **MỌI nhân sự thuộc tổ** trong kỳ (tính **cả phần của chính tổ trưởng**,
và là số **ĐÃ trừ** hao lỗi theo người).

⚠️ **Ngưỡng không kèm đơn vị** (chủ chốt *"Đơn vị bỏ đi"*). Hệ quả cho người nối nguồn sản lượng sau
này: cộng **toàn bộ** sản lượng của tổ trong kỳ rồi so, không lọc theo đơn vị. Tổ làm nhiều loại
việc khác đơn vị (vừa "m²" vừa "tờ") thì con số cộng lại không có ý nghĩa vật lý — **đánh đổi đã
biết, không phải sơ suất**.

> ⚠️ Cùng số phận với bảng bậc: **CHƯA RA TIỀN** cho tới khi dựng lại nguồn sản lượng — tổng khoán
> hiện luôn = 0 nên mọi tổ đều dưới mọi ngưỡng.

Bảng do `create_all` tạo (không migration).

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `department_id` | `Integer` | **UQ**, **IX** | no | — | Tổ sở hữu ngưỡng. Soft-ref `departments.id`. **UNIQUE**: mỗi tổ đúng một ngưỡng — hai dòng cùng tổ thì không ai biết dòng nào đang có hiệu lực. |
| `min_output_qty` | `Numeric(14,2)` | — | no | `0` | Ngưỡng **SẢN LƯỢNG** của tổ trong kỳ, **con số trần không kèm đơn vị**. `0` = không gác. Thêm bằng migration `0133` (trước đó là `min_khoan_to`, đo bằng tiền — chủ nhìn màn thật rồi đổi: *"nó là sản lượng mà sao lại chữ đ"*, và *"Đơn vị bỏ đi"*). |
| `created_at` | `DateTime(tz)` | — | no | now | Khi tạo. |
| `updated_at` | `DateTime(tz)` | — | no | now | Lần sửa gần nhất (`onupdate`). |

**Keys & indexes**

- Primary key: `id`. Unique + index: `department_id`.

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
| `status`        | `String(12)`   | **IX**                      | no   | `pending` | pending/approved/rejected/cancelled (NV tự rút).     |
| `decided_by`    | `Integer`      | **FK→users.id**             | yes  | —         | HCNS duyệt/từ chối — hoặc chính NV khi tự rút.       |
| `decided_at`    | `DateTime(tz)` | —                           | yes  | —         | Thời điểm quyết định / thời điểm NV rút lại.         |
| `decision_note` | `String(500)`  | —                           | yes  | —         | Ghi chú duyệt/lý do từ chối.                         |
| `created_at`    | `DateTime(tz)` | —                           | no   | now       | Khi gửi.                                             |

---

## Pipeline in-ấn (rebuild) — master data mới

> 4 module master mới (strangler, song song bảng cũ) — danh mục cấu hình sản xuất:
> `may_thiet_bi` · `giay_nguyen`/`muc`/`ban_kem` (vật liệu Kho) · `cong_doan` · `loai_san_pham`.
> Specs: `docs/spec-may-thiet-bi.md`, `spec-cong-doan.md`, `spec-san-pham.md`.
> (Quy tắc bình bài + Tính giá thành đã bỏ — xem git tag `backup/pre-remove-binhbai-tinhgia`.)

### `nhom_may`

**Purpose:** danh mục **NHÓM MÁY** — danh sách tên được phép chọn ở ô "Nhóm máy" của màn Thiết bị & Máy móc.

🔴 **KHÔNG phải khoá ngoại.** `may_thiet_bi.loai_may` vẫn lưu **CHỮ**; bảng này chỉ quản danh sách tên được bày ra. Lý do giữ chữ: chuỗi đó đang được đọc ở Lệnh SX (`LsxBuocDrawer` · `LsxDetailView` · `LsxRoutingTable`), Phiếu tính giá, và ở chính màn Máy (`isMayIn()` quyết định ẩn/hiện ~8 ô, facet tab lọc theo nó) — đổi sang id là kéo theo cả 5 chỗ đó cộng migration dữ liệu, trong khi việc cần làm chỉ là "cho thêm và cho xoá tên trong danh sách".

**Hệ quả bắt buộc nhớ:** vì không có FK, DB không tự giữ — nên **service CHẶN xoá khi còn máy dùng** (`NhomMayService.delete`, kèm SỐ máy trong thông báo). Xoá mù là để lại máy mang tên nhóm không còn tồn tại, và không chỗ nào báo. Tạo lại tên đã bị ẩn thì **bật lại dòng cũ** thay vì báo trùng.

Bảng MỚI → `create_all` tự dựng, **không cần migration cho bảng**; migration `0155` chỉ để **backfill** `DISTINCT may_thiet_bi.loai_may` + tên mặc định, để DB đang chạy không mất nhóm do xưởng tự đặt. Danh sách mặc định `NHOM_MAY_MAC_DINH` khai trong `models/may_thiet_bi.py` là nguồn DUY NHẤT, `seed_rebuild.seed_nhom_may` import lại (seed đôi — `schema_migrations` sống qua `drop_all` nên test không chạy migration).

**Tất cả cột:** `id`, `ten`, `active`, `created_at`, `updated_at`.

### `may_thiet_bi`

**Purpose:** máy sản xuất = **spec năng lực** (khổ/nhíp/vùng in/tốc độ/chuẩn bị). Một row = một máy. Field đặc thù theo `loai_may` + khối con của form gói trong JSON `fields_theo_loai`.

🔴 **DỌN LỚN 11/08/2026 — gỡ ~50 cột khỏi model.** Chủ chốt: *"không nhập liệu được thì là rác"*. Đã gỡ khỏi model/schema/repo (cột nằm lại **orphan** trong Postgres — dự án không có Alembic nên không drop, nhưng **không còn code nào đọc/ghi**): cả khối **BHR** (`nguon_bhr` `don_gia_gio_BHR` `von_dau_tu` `gia_tri_thu_hoi` `nam_khau_hao` `lai_von_pct` `gio_lam_nam` `availability_pct` `productivity_pct` `efficiency_pct` `luong_gio` `luong_burden_pct` `cong_suat_kW` `he_so_tai_dien` `don_gia_dien` `bao_hiem_nam` `dien_tich_san_m2` `don_gia_thue_m2_nam` `bao_tri_gio` `overhead_gio` `markup_pct` `ngay_cap_nhat_bhr`) kèm `compute_bhr` + endpoint `/bhr` · `/bhr-preview`; **tài sản** (`ma_tai_san` `ma_TK_cost_center` `nha_cung_cap` `ngay_dua_vao_su_dung` `het_han_bao_hanh` `phuong_phap_khau_hao`); **nhận diện thừa** (`dia_diem` `phong_ban_id` `ghi_chu_2` `nhom_cost_center` `finishing_subtype`); **năng lực không nối** (`min_stock_gsm` `max_stock_gsm` `vat_lieu_ho_tro_class` `so_ca` `chi_so_dem_luot` `so_may_song_song`); **offset chưa nối engine** (`so_units` `units_truoc` `units_sau` `khoa_class` `co_tro_mat` `cho_phep_tu_tro` `cho_phep_tro_dau_duoi` `bu_hao_canh_may_per_mau` `bu_hao_chay_pct` `ho_tro_cip3`); **bảo trì thô** (`ngay_bao_tri_gan_nhat` `chu_ky_bao_tri` `chu_ky_bao_tri_don_vi` `ngay_bao_tri_ke_tiep`); **dormant** (`ca_lam_ids` `thoi_gian_rua_muc`); và **`trang_thai` + property `active`** (bỏ ô "Tình trạng" khỏi form ⇒ mọi máy luôn `active`, cờ đó chưa bao giờ phân loại được gì — máy dừng thì khoá theo KHOẢNG THỜI GIAN ở `machine_unavailable_periods`, đó mới là thứ Xếp lịch đọc). BHR có spec §4 + test xanh nhưng **chưa bao giờ có ô nhập** và không engine giá nào gọi ⇒ luôn chạy trên dữ liệu rỗng. Bù hao canh máy vẫn tính được: `routing_engine.so_to_in_gross` nhận qua **tham số**, không đọc máy. **Thêm cột lại chỉ khi có ô nhập đi kèm** — đừng dựng cột trước rồi hẹn form sau.

| Column                                                       | Type           | Meaning                                                                       |
| ------------------------------------------------------------ | -------------- | ----------------------------------------------------------------------------- |
| `id`                                                         | `Integer` PK   | khóa chính.                                                                   |
| `ma`                                                         | `String(30)` U | mã máy (VD `OFF-74-4C`).                                                      |
| `ten`                                                        | `String(150)`  | tên.                                                                          |
| `loai_may`                                                   | `String` IX    | nhóm máy — **chữ TỰ DO**, khớp danh mục `nhom_may` (không FK).                |
| `hang_san_xuat` `model` `so_seri`                            | `String(100)`  | nhận diện thiết bị (bày ra form 11/08/2026).                                  |
| `gripper_mm` `nhip_giay_mm` `le_hong_mm` `duoi_thang_mau_mm` |                | chừa lề tờ in — engine bình bài.                                              |
| `kho_max_dai/rong` `kho_min_dai/rong` `kho_kem_dai/rong` `vung_in_dai/rong` | `Integer` | khổ giấy máy nhận · khổ kẽm · vùng in (mm).                          |
| `so_nhan_cong`                                               | `Numeric(5,2)` | Số người vận hành tiêu chuẩn (kíp chuẩn); dùng hoạch định nhân lực, không nhân tốc độ máy. |
| `fields_theo_loai`                                           | `JSON`         | field đặc thù theo `loai_may` + khối con của form: `chuan_bi_khoan` (các khoản chuẩn bị) và **`lich_bao_tri`** = danh sách **GÓI** bảo trì `[{id, viec, so, don_vi, hang_muc:[{id,ten}]}]` — gói mang chu kỳ, `hang_muc` là các việc con phải làm trong một lần dừng máy. Gói khai trước 12/08/2026 không có `hang_muc` vẫn đọc bình thường. Khoá cũ `lan_cuoi` / `dung_phut` đã bỏ ô nhập nhưng giá trị cũ được giữ nguyên khi lưu. |

**Tất cả cột:** `id`, `ma`, `ten`, `loai_may`, `hang_san_xuat`, `model`, `so_seri`, `ghi_chu`, `toc_do`, `toc_do_min`, `toc_do_max`, `don_vi_toc_do`, `makeready_time_default`, `cho_ky_thuat_gio`, `so_nhan_cong`, `kho_max_dai`, `kho_max_rong`, `kho_min_dai`, `kho_min_rong`, `kho_kem_dai`, `kho_kem_rong`, `vung_in_dai`, `vung_in_rong`, `gripper_mm`, `nhip_giay_mm`, `le_hong_mm`, `duoi_thang_mau_mm`, `fields_theo_loai`, `active`, `created_at`, `updated_at`. **`active`** (BOOLEAN NOT NULL DEFAULT TRUE, migration `0202`) = máy CÒN DÙNG hay đã thanh lý — cờ của nút "Ngừng dùng" trên màn Máy, nhờ nó màn này vào được luật xoá chung của danh mục. ĐỪNG NHẦM với `trang_thai` đã gỡ ở mg `0186`: cái cũ trộn ba nghĩa (đang chạy / bảo trì / đã nghỉ) và không có ô nhập nào. Máy dừng **TẠM** (bảo trì, hỏng) vẫn `active=TRUE` và khai bằng khoảng thời gian ở `machine_unavailable_periods` — đó vẫn là thứ Xếp lịch đọc để né khe. `xep_lich_service._may_lam_duoc` lọc `active`, nhưng luôn GIỮ máy đang gán để lệnh cũ mở ra không trống ô. **Hai loại nhíp — ĐỪNG LẪN:** `gripper_mm` = mép nhíp trên BẢN KẼM (~44mm, nhãn UI "Nhíp kẽm"); `nhip_giay_mm` (INTEGER nullable, migration 0107) = cạnh máy KẸP TỜ GIẤY (~8–12mm) → bình bài trừ vào chiều DÀI tờ in. `le_hong_mm` trừ MỖI BÊN chiều rộng, `duoi_thang_mau_mm` trừ chiều dài; cả hai đã có cột từ trước nhưng tới migration 0107 mới có ô nhập trên UI. **Ba cột tốc độ — chỉ MỘT cột chảy vào tính toán:** `toc_do` = tốc độ TRUNG BÌNH, là số duy nhất Tính giá / Lệnh SX / Xếp lịch đọc (tên cột giữ nguyên dù nhãn UI đã đổi thành "Tốc độ trung bình"); `toc_do_min` / `toc_do_max` (NUMERIC(12,2) nullable, migration 0152) là dải năng lực **CHỈ ĐỂ KHAI** theo chốt của chủ 03/08/2026 — không nối vào công thức nào. Cho lịch chạy bằng khoảng [sớm–muộn] là việc viết lại lõi xếp lịch, không phải chỉ đọc thêm hai cột này. **`don_vi_toc_do`** (VARCHAR(32) sau migration 0153, trước là 16) mang mã dạng `<đơn vị đếm>_gio` **suy ra từ danh mục `don_vi_do`** — chủ tự thêm/xoá đơn vị ở màn "Đơn vị & quy đổi" là danh sách chọn tự đổi theo, không có bảng riêng. `don_vi_do.ma` rộng 24 nên mã ở đây tới 28 ký tự; SQLite không ép độ dài (test không bắt được) nhưng Postgres thật thì lỗi lúc lưu — đó là lý do nới cột. Lệnh SX so khớp mã này với thứ công đoạn ĐẾM (`_DV_VAO_SANG_NS`); lệch là bỏ qua tốc độ trong im lặng, nên **đừng đổi quy ước đặt mã**.

**`ca_lam_ids`** (`JSON`, nullable, mg 0178) — **ĐÃ GỠ KHỎI MODEL 11/08/2026** (trước đó dormant từ 10/08). Từng là tập ca riêng của MÁY; nay đã bỏ: **máy là thiết bị, bàn xếp lịch cho chạy LIÊN TỤC** (`XepLichService._lich_may` → `LichXuong(lien_tuc=True)`), chỉ dừng vì ngày nghỉ/lễ của xưởng và vùng KHOÁ máy (`machine_unavailable_periods` kiểu `chan`). Ca là chuyện của người: cần tăng ca thì cứ xếp việc vào giờ đó, không phải sửa danh mục máy. Không còn ô nhập, không còn trong API. Hệ quả đã biết: trần giờ máy/ngày thành 24h nên đèn "quá tải máy" gần như không sáng — trần thật nằm ở quỹ giờ-NGƯỜI của tổ. Cột giữ lại để không mất số cũ — **đừng khai lại ô này**.


🔴 **GỠ KHỎI MODEL 13/08/2026** — chờ kỹ thuật bỏ khỏi cả hệ theo yêu cầu chủ (lúc gỡ: 0/24 máy, 0/10 đầu việc, 0/14 bước lệnh có khai). Cột còn NẰM IM trong DB đang chạy, không code nào đọc. `cho_ky_thuat_gio` (NUMERIC(6,2) NOT NULL DEFAULT 0, mg 0182): **CHỜ KỸ THUẬT của bước MÁY** — số GIỜ hàng nằm chờ sau khi chạy xong trên máy này (mực khô, màng nguội). Tính bằng GIỜ, khác `makeready_time_default` tính bằng PHÚT — nhãn form phải ghi rõ đơn vị.

**Vì sao khoá theo MÁY chứ không theo công đoạn** (chủ chốt 10/08/2026): CM-01/CM-02 là máy UV (khô dưới đèn, ≈0) còn CM-03/CM-04 là máy cán màng (phải để nguội vài giờ) — bốn máy CÙNG công đoạn "Cán màng / UV" mà chờ khác hẳn. Một số cho cả công đoạn là sai một trong hai vế, im lặng. Kéo lệnh sang máy khác ⇒ chờ tính lại.

⚠️ **KHÔNG chiếm máy** — xem `cong_doan_dau_viec.cho_ky_thuat_gio` (vế TỔ).

### `chung_loai_giay`

**Purpose:** chủng loại giấy (Couché/Ford/Bristol/Ivory/Duplex/Kraft…) — phân loại; `giay_nguyen` ăn theo đây. Một row = một chủng loại.

**Tất cả cột:** `id`, `ma`, `ten`, `mo_ta`, `active`, `created_at`, `updated_at`.

⚠️ `be_mat` · `tho_mac_dinh` GỠ HẲN 15/08/2026 — khỏi model, schema, repo, validator, seed, màn
khai, **và khỏi DB** bằng migration `0199_go_be_mat_tho_chung_loai_giay` (DROP COLUMN, best-effort:
SQLite đời cũ từ chối thì cột mồ côi vô hại). Đo trước khi gỡ: `be_mat` 6/6 dòng có giá trị nhưng
CHỈ để hiện trên bảng — không engine nào đọc để tính, nên không phiếu nào đổi số; `tho_mac_dinh`
0/6. **KHÔNG ĐẢO LẠI ĐƯỢC**: giá trị "bong"/"mo"/"nham" của 6 chủng loại đã mất, khai lại phải gõ tay.

Đừng nhầm `tho_mac_dinh` (đã gỡ) với `giay_nguyen.tho` — thớ của TỪNG loại giấy, vẫn còn và vẫn
dùng cho bình bài.

### `giay_nguyen`

**Purpose:** tờ giấy nguyên (khổ mua) — thuộc 1 chủng loại (`chung_loai_giay_id`, soft int). Một row = một loại giấy cụ thể.

**Tất cả cột:** `id`, `ma`, `ten`, `chung_loai_giay_id`, `kho_dai`, `kho_rong`, `gsm`, `caliper_micron`, `tho`, `don_vi_gia`, `don_gia`, `gia_thi_truong`, `kho_tinh_gia`, `cong_thuc_gia`, `cong_thuc_luong`, `ghi_chu`, `anh_url`, `version_no`, `active`, `created_at`, `updated_at`.

`cong_thuc_luong` (TEXT nullable, mg 0195): **CÔNG THỨC RA LƯỢNG** — vế giấy của cặp với `vat_tu_in_an.cong_thuc_luong` (mg 0194). Vd `dinh_luong * dai_in * rong_in * to_dau_vao` = số kg giấy cả lệnh. Có nó thì giấy khai ĐVT `kg` THẬT rồi tự ra kg, khỏi đi vòng qua cạnh quy đổi động `tờ → kg` — cạnh đó là chỗ duy nhất còn giữ "công thức mà lại có đích". `ke_hoach_vat_tu_service._ve_goc` hỏi cột này TRƯỚC, không có mới quy đổi.

`anh_url` (mg 0191, VARCHAR(500) nullable) = ảnh minh hoạ vật tư (1 ảnh). Lưu đường `/api/files/materials/giay/<id>/…` (đọc qua router có đăng nhập); trang QR công khai serve lại chính key này qua `/api/public/vat-lieu-anh` bằng token QR. NULL = chưa có ảnh.

`don_vi_gia` (mg 0170) là **ĐƠN VỊ GỐC** của mặt hàng: mã trong `don_vi_do`, không còn enum cứng ở frontend. Tồn kho cộng dồn theo đơn vị này; nhập bằng đơn vị nào cũng được rồi quy về đây. NULL = chưa chọn (mg 0170 xoá trắng mã không có trong `don_vi_do`) — không mặc định `kg` nữa vì đơn vị gốc quyết định cách cộng tồn, điền hộ một lần là sai vĩnh viễn.

`kho_dai`/`kho_rong` KHÔNG có ô nhập ở màn danh mục (bỏ 2026-07-21, khổ nhập ở phiếu tính giá) — chỉ seed ghi. Kho cố tình KHÔNG dùng hai cột này để quy đổi (chủ chốt 2026-08-08 "giấy chỉ đếm theo kg"): bơm khổ vào thì giấy seed đếm được tờ/ram còn giấy người dùng tự tạo (khổ = 0) thì không, cùng một màn hai cách cư xử. Muốn một loại giấy đếm theo tờ thì đặt `don_vi_gia = 'to'`, cặp cố định `1 ram = 500 tờ` chạy mà không cần khổ.

### `giay_gia_version`

**Purpose:** phiên bản giá giấy (lịch sử) — ẢNH CHỤP toàn bản ghi `giay_nguyen` tại 1 mốc hiệu lực. Mỗi lần "Thêm phiên bản" đẻ 1 row; `is_current` = mốc đang áp dụng (mirror giá lên `giay_nguyen`). Bảng mới do create_all tạo (không migration). `giay_id` soft int → `giay_nguyen`.

**Tất cả cột:** `id`, `giay_id`, `version_no`, `ngay_hieu_luc`, `is_current`, `kho_dai`, `kho_rong`, `gsm`, `caliper_micron`, `tho`, `don_vi_gia`, `don_gia`, `gia_thi_truong`, `ghi_chu`, `created_by`, `created_at`.

### `vat_tu_in_an`

**Purpose:** vật tư in ấn — danh mục PHẲNG (mực/kẽm/hoá chất/màng/keo… chung 1 bảng, phân biệt bằng tên) theo bảng xưởng: Mã · Tên · ĐVT · Giá · Ghi chú. Thay 2 bảng cũ `muc`+`ban_kem`.

**Tất cả cột:** `id`, `ma`, `ten`, `don_vi_gia`, `don_vi_dong_goi`, `he_so_dong_goi`, `don_gia`, `cong_thuc_gia`, `cong_thuc_luong`, `ghi_chu`, `anh_url`, `active`, `created_at`, `updated_at`.

`cong_thuc_luong` (TEXT nullable, mg 0194): **CÔNG THỨC RA LƯỢNG** của chính món hàng — "một lệnh cần bao nhiêu <đơn vị này>", biến lấy từ quy cách lệnh (vd keo: `0.002 * so_luong`). ĐỪNG LẪN với `cong_thuc_gia` ngay bên cạnh: ô kia ra **TIỀN** cho phiếu tính giá, ô này ra **LƯỢNG** cho BOM ở bước lệnh.

⚠️ Vì sao đặt ở VẬT TƯ chứ không ở đơn vị (chủ chốt 13/08/2026): `kg` dùng chung cho keo · mực · giấy mà mỗi thứ tiêu hao một kiểu. Gắn công thức lên `kg` là mọi vật tư đo bằng kg đều tính theo cùng một công thức; né bằng cách đẻ `kg_keo`/`kg_giay_to_in`… thì kho và mua hàng phải nhìn mấy cái tên đó thay vì `kg` thật. `LsxService._luong_vat_tu` hỏi cột này TRƯỚC, không có mới hỏi `don_vi_do.cong_thuc`, rồi mới tới quy đổi từ đơn vị của bước.

`anh_url` (mg 0191, VARCHAR(500) nullable) = ảnh minh hoạ vật tư (1 ảnh); đường `/api/files/materials/vat_tu/<id>/…`. Xem ghi chú ở `giay_nguyen.anh_url`.

`don_vi_gia` (mg 0170): **ĐƠN VỊ GỐC** — mã trong `don_vi_do`, NULL = chưa chọn. Xem ghi chú ở `giay_nguyen`.

`don_vi_dong_goi` + `he_so_dong_goi` (mg 0170) — **ĐÃ BỎ 10/08/2026, cột chết**: quy cách đóng gói riêng của món ("1 thùng = 3 kg"). Gỡ vì khai quy đổi ở hai nơi (đây và danh mục Đơn vị & quy đổi) là bắt người dùng nhớ luật vô ích; cần "thùng keo 20 kg" thì khai thẳng một đơn vị như vậy ở `don_vi_do` rồi chọn làm ĐVT. Đã gỡ khỏi model · schema · form · đồ thị quy đổi; hai cột để nguyên trong DB (dự án không có Alembic, không drop) nhưng KHÔNG còn code nào đọc/ghi.

### `cong_doan`

**Purpose:** danh mục công đoạn động, trung tính với cách thực hiện. Công đoạn chỉ khai tổ/phòng ban phụ trách, đơn vị, setup, bù hao và các đầu việc định mức; lựa chọn `may|to|thue_ngoai` cùng máy cụ thể thuộc bước KHSX. `department_id` soft → `departments`.

`setup_time` và `may_id` là mặc định khi bung LSX. `nang_suat` là cột legacy chỉ giữ để bảo toàn/backfill dữ liệu cũ: LSX mới lấy tốc độ bước Máy từ `may_thiet_bi.toc_do`, còn bước Tổ lấy năng suất/người từ `cong_doan_dau_viec`.

`spoilage_pct` là cột CŨ, chỉ `routing_engine` của hệ tính giá cũ dùng; không có ô nhập và Lệnh SX KHÔNG đọc — hao hụt đi qua module `bu_hao` (mỗi bậc tự chọn `to`|`pct`).

**Tất cả cột:** `id`, `ma`, `ten`, `ten_hien_thi`, `don_vi_vao`, `don_vi_ra`, `he_so_ngoai_dong`, `kieu_bu_hao`, `bu_hao_id`, `nhom`, `nhom_may_cho_phep`, `department_id`, `khoan_ghi_theo`, `allowed_defect_pct`, `allowed_defect_abs`, `che_do_tinh`, `pricing_basis`, `setup_cost`, `setup_time`, `nang_suat`, `run_rate`, `rate_tiers`, `size_tiers`, `first_unit_floor`, `min_charge`, `requires_tooling`, `tooling_type`, `spoilage_pct`, `so_to_bu_hao`, `inline_flag`, `cong_thuc_gia`, `ghi_chu`, `active`, `created_at`, `updated_at`.

`nhom_may_cho_phep` (JSON list, nullable, mg 0168): tên nhóm máy (`may_thiet_bi.loai_may`) làm được công đoạn này — chặn gán máy sai loại ở bước bài ghép (vd Ghi kẽm CTP không cho gán máy Bế). NULL/`[]` = chưa khai = không ràng buộc. Trục `loai_may` mịn hơn `nhom(3)` nên phân biệt được Bế với Cán màng.

### `cong_doan_dau_viec`

**Purpose:** quan hệ nhiều-nhiều giữa công đoạn loại Tổ và đầu việc khoán của đúng tổ, đồng thời giữ định mức thời gian.

**Tất cả cột:** `id`, `cong_doan_id`, `piece_rate_id`, `nang_suat_nguoi_gio`, `nang_suat_nguoi_gio_min`, `nang_suat_nguoi_gio_max`, `don_vi_nang_suat`, `so_nguoi_toi_thieu`, `so_nguoi_tieu_chuan`, `so_nguoi_toi_da`, `cho_ky_thuat_gio`.

🔴 **`is_default` GỠ 12/08/2026 (mg `0190`)** — cột radio "Mặc định" ở bảng đầu việc trong form Công đoạn. Nó chọn hộ đầu việc nào điền sẵn khi lập lệnh. Chủ chốt bỏ: cùng một công đoạn mà hai đầu việc khác nhau THẬT (bế TAY / bế MÁY · vào keo gáy vuông / khâu chỉ) thì chọn cái nào là quyết định theo **hàng cụ thể**, không phải hằng số khai một lần ở danh mục.

**Luật điền sẵn còn lại (một luật duy nhất, `LsxService._khoan_mac_dinh` và `LsxRoutingTable` phải khớp):** công đoạn có **đúng MỘT** đầu việc ⇒ tự điền; **từ hai trở lên ⇒ để TRỐNG**, người lập lệnh chọn. Lúc gỡ có 10 công đoạn ≥2 đầu việc (Bế thành phẩm 3 · Bế nổi 3 · Xén 3 mặt 3 · Cán màng bóng/mờ · Gấp tay sách · Bắt tay+vào keo · Ép kim · Bồi sóng · Ghép màng metalize) — từ nay chúng cần chọn tay.

**Ba mốc nhân lực:** `so_nguoi_tieu_chuan` là số điền sẵn vào bước lúc bung lệnh; `so_nguoi_toi_da` là TRẦN tính thời gian (`so_nguoi_tinh = min(kế hoạch, tối đa)` — thêm người nữa không rút ngắn thời gian, chỉ đẻ cảnh báo mềm). `so_nguoi_toi_thieu` (mg 0160, NOT NULL DEFAULT 1) hiện là **KHAI BÁO thuần** — ghim vào `lsx_cong_doan.khoan_json` để không mất, nhưng CHƯA vào công thức thời lượng và CHƯA chặn gì. Service chỉ kiểm thứ tự 1 ≤ tối thiểu ≤ tiêu chuẩn ≤ tối đa.

**Dải năng suất (mg 0158):** `nang_suat_nguoi_gio` là mức **TRUNG BÌNH** — số duy nhất chảy vào công thức thời lượng bước Tổ (`thời lượng = thời gian khác + SL vào ÷ (năng suất người × số người tính) × 60`); `nang_suat_nguoi_gio_min`/`_max` chỉ dùng để ra khoảng nhanh–chậm (râu Gantt), đúng lối `may_thiet_bi.toc_do` + `toc_do_min`/`toc_do_max`. Nullable — chưa khai thì ba mức bằng nhau, KHÔNG bịa min=max=TB. Service chặn min > TB và max < TB.

`don_vi_nang_suat` (VARCHAR(32), nullable): đơn vị người khai chọn, cùng bảng mã với ô "Đơn vị tốc độ" của máy (`<đơn vị>_gio`). Đây là **NHÃN KHAI BÁO** — engine chia thẳng SL vào cho năng suất, KHÔNG quy đổi và KHÔNG kiểm khớp với đơn vị bước (bước quy đổi làm sau). Trống = giữ lối cũ, suy theo `cong_doan.don_vi_vao`.

🔴 **GỠ KHỎI MODEL 13/08/2026** — chờ kỹ thuật bỏ khỏi cả hệ theo yêu cầu chủ (lúc gỡ: 0/24 máy, 0/10 đầu việc, 0/14 bước lệnh có khai). Cột còn NẰM IM trong DB đang chạy, không code nào đọc. `cho_ky_thuat_gio` (NUMERIC(6,2) NOT NULL DEFAULT 0, mg 0182): **CHỜ KỸ THUẬT của bước TỔ** — số GIỜ hàng phải nằm chờ SAU khi làm xong đầu việc này (keo đông, màng nguội). Vế TỔ của cặp với `may_thiet_bi.cho_ky_thuat_gio` (vế MÁY); hai vế không chồng nhau vì một bước hoặc Máy hoặc Tổ.

**Vì sao khoá theo ĐẦU VIỆC chứ không theo công đoạn** (chủ chốt 10/08/2026): cùng công đoạn "Bắt tay + vào keo", đầu việc *vào keo gáy vuông* phải chờ keo đông còn *khâu chỉ* thì không chờ gì — một số cho cả công đoạn không tách được. Bảng cũ `cong_doan_cho_ky_thuat` (khoá công đoạn × loại sản phẩm) đã GỠ vì cùng lý do.

⚠️ **KHÔNG chiếm máy**: `LsxService._cho_ky_thuat_phut` đổi giờ → phút rồi ghim vào `lsx_cong_doan.cho_phut`; số đó vào `tong_phut` chứ KHÔNG vào `chiem_may_phut`. Chưa khai = 0, KHÔNG đoán. Đổi đầu việc ⇒ tính lại (`_ke_thua`), người kế hoạch vẫn sửa đè được tại bước.

`he_so_ngoai_dong` (NUMERIC(18,6) nullable, mg 0196): **HỆ SỐ vào → ra cho bước NGOÀI dòng giấy** — "một đơn vị vào đẻ ra mấy đơn vị ra" (ghi kẽm 1 bài ra 4 bản ⇒ 4). NULL = 1.

⚠️ **Trên dòng giấy KHÔNG đọc cột này**: hệ số ở đó là số con/tờ · số mảnh xả · số tay, đều suy từ quy cách LỆNH (`LsxService._he_so_cau`). Khai ở đây là dựng nguồn thứ hai cho cùng một số. Ô nhập cũng chỉ hiện khi hai đơn vị KHÁC nhau — `kẽm → kẽm` thì hệ số luôn 1.

⚠️ **Vì sao cần dù mỗi đơn vị đã có `don_vi_do.cong_thuc`**: chỉ vế **RA** đọc công thức; vế **VÀO** suy ngược qua `vào = (ra ÷ hệ_số + hao_cố_định) ÷ (1 − hao_%)`. Cho cả hai đầu đọc công thức là hai đầu chốt cứng, hao hụt hết chỗ nhét — đúng bệnh của bản cũ (`vao = ra = so_kem if nhom == "prepress"`, gỡ 14/08/2026).

`don_vi_vao` / `don_vi_ra` (VARCHAR(24) sau migration `0186`, trước là 12, **nullable**): đơn vị đếm ĐẦU VÀO / ĐẦU RA của bước — **KHAI**, không suy từ tên. Mang **mã trong danh mục `don_vi_do`** (soft-ref), KHÔNG còn bó trong 5 mã dòng giấy.

### `cong_doan_dau_viec_vat_tu`

**Purpose:** VẬT TƯ mà một đầu việc của công đoạn tiêu thụ — nền của BOM (mg `0191`). Khai một lần ở danh mục Công đoạn; đến lệnh sản xuất, chọn "Công việc khoán" ở bước là các vật tư này tự bung vào khối "Vật tư cần dùng".

**Tất cả cột:** `id`, `cong_doan_dau_viec_id`, `vat_tu_id`, `thu_tu`.

**KHÔNG có cột số lượng** — cố ý. Định mức tuỳ quy cách từng lệnh (khổ tờ · số màu · số tờ chạy), nên một con số khai ở danh mục là số chết. Số lượng suy **lúc bung ở bước lệnh**: đổi `lsx_cong_doan.so_luong_vao` (theo `don_vi_vao` của bước) sang `vat_tu_in_an.don_vi_gia` bằng **quy đổi động** (`quy_doi_service.doi_theo_quy_cach` + `bien_cong_thuc.quy_cach_bien`). Đổi không được ⇒ KHÔNG bung dòng đó, kèm câu lý do — không đoán.

`cong_doan_dau_viec_id` → FK `cong_doan_dau_viec.id` ON DELETE CASCADE. `vat_tu_id` là **soft-ref** tới `vat_tu_in_an.id` (cùng lối `piece_rate_id`); service chặn id không tồn tại, đã ngừng dùng, hoặc **chưa chọn đơn vị tính** (không có đơn vị thì không có đích để quy đổi). UNIQUE `(cong_doan_dau_viec_id, vat_tu_id)`.

**Vì sao neo vào `cong_doan_dau_viec` chứ không vào `piece_rates`:** đây đúng là dòng người dùng nhìn thấy trong bảng "Đầu việc và định mức của tổ" ở drawer Công đoạn, và cho phép cùng một đầu việc dùng vật tư khác nhau ở hai công đoạn khác nhau.

Ba ca hợp lệ (`cong_doan_service`, chặn `[E-CD-DONVI]`):
- **cùng để trống** — bước CHƯA khai đơn vị (dữ liệu cũ / bước kế hoạch tự thêm); engine lùi về luật theo `nhom`.
- **hai đầu đều mang cờ trạm** (`don_vi_do.tram_dong_giay`) — bước TRÊN dòng giấy, phải đúng chiều: cùng trạm, hoặc một nhịp trong `CAU_TRAM` (`to_nguyen→to` · `to→con` · `con→cai` · `to→tay` · `tay→cai` · `to→cai`). Nhảy cóc `to_nguyen→cai` bị chặn.
- **hai đầu đều ngoài trạm** — bước không chạm giấy, khai đơn vị THẬT của nó (`bai → kem` cho ghi kẽm, `cai → me` cho trộn keo). Không có chiều nào để mà sai nên không kiểm chiều.

Ca **một chân trong một chân ngoài** (`cai → thung`, đóng gói) CHẶN ở lát này: hệ số của cặp đó là sức chứa từng đơn, chưa có chỗ khai → cho qua là engine ăn hệ số 1 trong im lặng.

🔴 **Đã gỡ 11/08/2026:** `DON_VI_DONG_GIAY` (5 mã cứng) + `CAP_DON_VI_HOP_LE` (6 cặp liệt kê theo MÃ). Chúng chính là thứ bắt bước ghi kẽm để trống đơn vị. Nay chỉ còn `CAU_TRAM` liệt kê theo **TRẠM** — đơn vị nào gắn cờ trạm nào thì tự khớp, thêm đơn vị không phải sửa code. Hệ số mỗi nhịp vẫn ở `lsx_service._he_so_cau` (lấy từ quy cách lệnh: bình bài · số mảnh xả · số tay), KHÔNG khai vào bảng cặp `don_vi_quy_doi` — khai hai nơi là hai số giấy đá nhau trên cùng một lệnh.

**NULL = bước KHÔNG CHẠM GIẤY** (chế bản ghi kẽm) → `thanh_phan_engine` loại khỏi dòng giấy, bù hao của nó không cộng vào số giấy phải mua. Danh mục KHÔNG có mã đơn vị `kem`/`bai`: kẽm là đơn vị của khâu chế bản chứ không phải một mức trên dòng giấy, nên `lsx_service._don_vi_theo_buoc` tự suy `kem` từ `nhom='prepress'` khi bung lệnh. Bước **không phải** chế bản mà bỏ trống → engine đẩy warning "chưa khai đơn vị vào/ra", tránh bù hao im lặng về 0.

**Hệ số quy đổi KHÔNG lưu ở đây** — phiếu tính giá đã có `con` (bình bài) và `so_manh_xa` (khổ giấy); lưu lại là đẻ nguồn sự thật thứ hai. Đây là thứ cho `bu_hao_engine.chuoi_nguoc_dv` tra bù hao ĐÚNG đơn vị của từng bước (bước đóng gói tra bậc theo số CON, không theo số tờ).

`size_tiers` (JSON): bậc đơn giá theo KÍCH THƯỚC thành phẩm (cạnh dài, cm) — `[{den_cm, don_gia}]`, "≤ den_cm → đơn giá"; engine chọn giá theo cỡ thay `run_rate` (vd công dán ≤20cm=100 · 40cm=200 · 100cm=800). `pricing_basis="per_job"` = trọn gói một lần (khuôn bế) — engine ÷ SL.

`khoan_ghi_theo`: công đoạn có tính khoán không — `nguoi` (ghi Phiếu sản lượng theo từng người → cột Khoán bảng lương) / `khong`. `allowed_defect_pct`/`allowed_defect_abs`: ngưỡng hao cho phép (max của 2), phần vượt mới trừ lỗi.

`kieu_bu_hao`: nối bù hao — `khong` / `tra_bang` (trỏ 1 mã bù hao qua `bu_hao_id` → tra bậc theo SL) / `co_dinh` (cộng `so_to_bu_hao` tờ). `bu_hao_id`: soft int → `bu_hao.id` (dùng khi `kieu_bu_hao='tra_bang'`).

### `cong_doan_cho_ky_thuat`

> 🔴 **BẢNG ĐÃ GỠ KHỎI MODEL 10/08/2026** (mg 0182) — chờ kỹ thuật nay khai ở `may_thiet_bi.cho_ky_thuat_gio` (bước Máy) và `cong_doan_dau_viec.cho_ky_thuat_gio` (bước Tổ). Bảng còn nằm im trong DB đang chạy (0 dòng lúc gỡ, dự án không có Alembic nên không drop). Mục này giữ để tra dữ liệu cũ.

**Purpose:** CHỜ KỸ THUẬT của một công đoạn theo LOẠI SẢN PHẨM — mực khô, keo đông, màng nguội. Bảng MỚI → `create_all` tự dựng (migration chỉ để ALTER bảng cũ). Bám precedent `cong_doan_dau_viec`.

**Tất cả cột:** `id`, `cong_doan_id`, `loai_san_pham_id`, `gio_cho`, `ghi_chu`.

**Khác hẳn "thời gian chuẩn bị máy"** (`may_thiet_bi.makeready_time_default`, đã có): chuẩn bị máy **CHIẾM MÁY**, còn chờ kỹ thuật thì **KHÔNG** — tờ nằm trên pallet chờ khô, máy in vẫn chạy job khác. Gộp hai thứ vào một số là hoặc khoá oan cái máy, hoặc xếp cán chồng lên lúc mực chưa khô.

**Vì sao theo CẶP (công đoạn × loại sản phẩm):** mực trên giấy couché bóng khô lâu hơn trên ford, keo gáy sách dày đông lâu hơn sách mỏng. Một con số cho mọi loại là con số sai với gần hết.

⚠️ **Khai đủ từng cặp; cặp CHƯA KHAI = 0, KHÔNG đoán** — không nội suy từ cặp gần giống. `gio_cho` tính bằng GIỜ (cho số lẻ 0,5); engine đổi sang phút khi ghim vào `lsx_cong_doan.cho_phut` lúc tạo lệnh / đổi loại SP, và **người kế hoạch sửa đè được tại bước** (kế thừa = mặc định, không read-only). Bài ghép mirror sang `bai_ghep_cong_doan.cho_phut`.

**Keys & indexes**

- Primary key: `id`. Unique: (`cong_doan_id`, `loai_san_pham_id`). Index: `cong_doan_id`, `loai_san_pham_id`.
- FK: `cong_doan_id FK→cong_doan.id` (CASCADE). `loai_san_pham_id` soft-ref theo convention repo.

### `to_quan_so_ngay`

**Purpose:** quân số CÓ MẶT của một TỔ trong một NGÀY, do người dùng **gõ đè** — nền cho quỹ giờ-người ở bàn xếp lịch (mục I). Bảng MỚI → `create_all` tự dựng (migration chỉ để ALTER bảng cũ). Bám precedent `cong_doan_cho_ky_thuat`.

**Tất cả cột:** `id`, `department_id`, `ngay`, `so_nguoi`, `ly_do`, `nguoi_sua_id`, `updated_at`.

**Vì sao cần bảng này khi đã có `employees` + `leaves`:** quân số TỰ TÍNH (nhân sự gắn đúng tổ lá, trạng thái `active`/`probation`, trừ đơn phép **đã duyệt** phủ ngày đó) đúng cho ngày bình thường, nhưng sai đúng những hôm cần chính xác nhất — mượn 3 người tổ Bế sang phụ tổ Dán, hai người ốm báo miệng buổi sáng. Tổ trưởng biết con số thật; đây là chỗ họ gõ đè.

⚠️ **KHÔNG lưu số tự tính vào đây.** Không có dòng gõ đè ⇒ engine tự tính lại mỗi lần đọc. Lưu cả hai là đẻ hai nguồn sự thật, rồi ảnh chụp cũ đứng im khi nhân sự đổi tổ. `so_nguoi = 0` (cả tổ nghỉ) KHÁC với "chưa gõ đè" — cái sau là KHÔNG có dòng. `ly_do` bắt buộc ≥ 3 ký tự ở service: một con số đè lên dữ liệu nhân sự mà không nói vì sao thì tháng sau không ai giải thích nổi hôm đó lịch tính ra như vậy.

**Người ở TẦNG GIỮA không tính vào tổ nào:** ai gắn ở "Xưởng in" (không thuộc tổ lá) thì không cộng vào tổ con — cộng vào là đếm thừa người và lịch hứa một năng lực không có thật. Định nghĩa Tổ = nút LÁ trong nhánh `la_san_xuat` (dùng chung `rbac_repo.to_san_xuat()`).

**Quỹ giờ-người ngày** = `so_nguoi` × giờ ca CHUNG của xưởng (tập `work_shifts.dung_cho_lich_may`; ca riêng của tổ đã bỏ 10/08/2026 — chưa tick ca nào thì rơi về 8h phẳng 08:00–16:00). Ràng buộc dùng nó: tại mọi thời điểm, Σ số người các việc đang chạy trong tổ ≤ quân số → vượt là vấn đề **Chặn** (`qua_tai_to`). Đây là thứ THAY cho luật "trùng giờ = xung đột" ở dòng tổ: tổ Dán 8 người chia được 5 người việc A + 3 người việc B cùng lúc.

**Keys & indexes**

- Primary key: `id`. Unique: (`department_id`, `ngay`). Index: `department_id`, `ngay`.
- FK: `nguoi_sua_id FK→users.id` (SET NULL). `department_id` **soft-ref** — FK cứng sẽ chặn xoá phòng vì một dòng quân số của ngày nào đó năm ngoái.

### `bu_hao`

**Purpose:** danh mục Bù hao — mỗi mã = danh sách BẬC số lượng → số tờ / %. Mô hình MỞ: bậc là dữ liệu JSON (`bac`), không phải cột cứng. Công đoạn TRỎ THẲNG 1 mã bù hao (qua `cong_doan.bu_hao_id`); engine tra bậc theo SL (bỏ trục số màu/số con). `bac` = `[{sl_tu, sl_den, gia_tri, don_vi(to|pct)}]`.

**Tất cả cột:** `id`, `ma`, `ten`, `bac`, `ghi_chu`, `active`, `created_at`, `updated_at`.

### `don_vi_do`

**Purpose:** danh mục ĐƠN VỊ ĐO, dùng CHUNG cho khoán · kho · mua hàng. Chỉ là DANH SÁCH TÊN — quy đổi nằm ở bảng cặp `don_vi_quy_doi`. `ma` là mã code tham chiếu (`to`, `cai`, `m2`); `ten` là chữ hiển thị người dùng gõ ("tờ", "m²") và `quy_doi_service.don_vi_map()` đánh chỉ mục theo CẢ HAI vì bảng đơn giá khoán lưu chữ hiển thị còn bước lệnh dùng mã. `ho` = LOẠI ĐO, **không** quyết định đổi được hay không (việc đó theo cặp đã khai) — chỉ để gom nhóm khi hiển thị; UI KHÔNG phơi ô này ra (chủ 2026-07-30). `he_so_goc` là **cột CHẾT** của mô hình cũ ("hệ số về đơn vị gốc của họ"), giữ để không mất dữ liệu lịch sử, KHÔNG đọc ở đâu nữa — migration `0135` đã chuyển nó thành cặp. Bảng mới → `create_all` tự dựng, không migration.

**Tất cả cột:** `id`, `ma`, `ten`, `ho`, `he_so_goc`, `hieu_luc_tu`, `ghi_chu`, `active`, `dung_lam_toc_do`, `tram_dong_giay`, `cong_thuc`, `created_at`, `updated_at`.

`cong_thuc` (VARCHAR(200) nullable, mg `0192`): **CÁCH ĐO** — công thức ĐỊNH NGHĨA chính đơn vị này, biến lấy từ quy cách của việc đang làm:

> `m² tờ in := dai_in * rong_in * to_sau_in`

Đây là **nguồn số lượng của BOM**: vật tư khai ĐVT là đơn vị nào thì lúc bung ở bước lệnh, `LsxService._luong_vat_tu` chạy công thức của đơn vị ấy với `bien_cong_thuc.quy_cach_bien(lsx)`. Mỗi đơn vị đúng MỘT cách đo nên không có gì để chọn nhầm. Để trống = đơn vị thường ⇒ lùi về quy đổi từ đơn vị của BƯỚC sang đơn vị vật tư (`doi_theo_quy_cach`). Cả hai đường tịt thì **không bung dòng đó**, kèm câu lý do — không đoán.

⚠️ **ĐỪNG nhầm với hai ô công thức khác trong hệ:**

| Ở đâu | Ra cái gì | Nối gì |
|---|---|---|
| `don_vi_do.cong_thuc` (cột này) | **LƯỢNG** | không nối với ai — định nghĩa chính nó |
| `giay_nguyen` · `vat_tu_in_an` `.cong_thuc_luong` | **LƯỢNG** | riêng cho một mặt hàng, đè lên cách đo của đơn vị |
| `giay_nguyen` · `vat_tu_in_an` · `cong_doan` `.cong_thuc_gia` | **TIỀN** | — |

(`don_vi_quy_doi.cong_thuc` — quy đổi động nối hai đơn vị — **đã gỡ 14/08/2026**, mg `0198`.)

Cả ba dùng chung bộ chip của `bien_cong_thuc`, nhưng kết quả khác nghĩa hẳn.

**`tram_dong_giay`** (VARCHAR(12) NULL, migration `0186`): đơn vị này đứng ở TRẠM nào trên **dòng giấy** — `to_nguyen` → `to` → `con`/`tay` → `cai`. NULL = ngoài dòng giấy, và đó là trạng thái của gần hết danh mục (kg · m² · thùng · kẽm · lượt). Đây là thứ **duy nhất** engine bù hao cần biết về một đơn vị: bước có cả hai đầu mang cờ trạm thì vào chuỗi tính ngược (`lsx_service.tinh_nguoc_routing`), không thì đứng ngoài — xem `services/dong_giay.py`.

🔴 **Vì sao đẻ cột này:** trước 11/08/2026 câu hỏi "bước có nằm trên dòng giấy không" trả lời bằng danh sách 5 mã CỨNG trong code (`cong_doan.DON_VI_DONG_GIAY`, đã gỡ). Hệ quả: công đoạn không chạm giấy buộc phải **để trống** đơn vị (ghi kẽm không khai được `bai → kem`), và mọi cách đếm khác của xưởng (mẻ · lượt · thùng) bị service chặn ngay ở cổng. Nay khai đơn vị ở màn Đơn vị là công đoạn dùng được ngay, khỏi sửa code.

String chứ không Boolean vì engine cần biết trạm NÀO để kiểm chiều chảy; Boolean không chặn nổi `cai → to`. Chiều hợp lệ = cùng trạm, hoặc nằm trong `CAU_TRAM` (`models/don_vi_do.py`) — danh sách các **nhịp có hệ số thật**, mỗi nhịp lấy số từ quy cách lệnh ở `lsx_service._he_so_cau`. `to_nguyen → cai` KHÔNG có trong đó: nhảy cóc qua khâu in thì không ai biết một tờ nguyên ra mấy thành phẩm, để lọt là engine lấy hệ số 1 rồi cấp thiếu giấy trong im lặng.

⚠️ **Lưới an toàn:** danh mục chưa gắn cờ trạm nào (DB chưa chạy `0186`, hoặc bảng trắng trong test) thì `dong_giay.ban_do_tram` lùi về `TRAM_MAC_DINH` — 5 mã mặc định của ngành in. Thiếu lưới này thì không bước nào nằm trên dòng giấy ⇒ chuỗi ngược rỗng ⇒ **mọi lệnh về 0 tờ trong im lặng**. Gắn cờ cho dù chỉ một đơn vị là danh mục thắng hoàn toàn.

🔴 **MỌI phép so trong ruột engine phải theo TRẠM, tuyệt đối không theo mã** (vá 11/08/2026, xem `tests/test_dong_giay.py`). Cờ này cho xưởng khai mã riêng cho một chặng (`to_in` gắn cờ *tờ in*) — chỗ nào còn so bằng mã là chỗ đó hỏng **im lặng**:
- tra hệ số cầu (`_he_so_cau` · `he_so_dv` · `chuoi_nguoc_dv`) → cặp mã không khớp ⇒ ăn hệ số 1;
- đọc mốc số tờ in / tờ nguyên (`_vao_tai`) → không thấy ⇒ rơi về số tờ trần, **mất sạch bù hao, không cảnh báo** (đo thật: 603 tờ → 103 tờ);
- khớp tốc độ máy (`_nang_suat_buoc`) → suy theo luật chung `<mã đơn vị>_gio`, `_DV_VAO_SANG_NS` chỉ còn là bảng NGOẠI LỆ (tay sách chạy máy đúng bằng một tờ). Bước NGOÀI dòng giấy nhận và nhả cùng một con số nên khớp được bằng đơn vị vào HOẶC ra; bước trên dòng giấy thì chỉ đơn vị vào.

**Đích của chuỗi bù hao** (`dong_giay.dich_chuoi`, dùng CHUNG cho tính giá và lệnh sản xuất): `đích = (SL đặt ÷ số cái trên 1 tờ) × (số <đơn vị cuối> trên 1 tờ)`. Trước đây tính giá xét `dv_cuoi == "cai"` rồi lấy số tờ cho mọi ca còn lại, còn lệnh sản xuất luôn lấy thẳng SL đặt — routing kết ở `con` là hai màn ra hai số giấy lệch nhau đúng số con/cái.

**Cảnh báo `buoc_ngoai_dong_giay`**: bước khai đơn vị hợp lệ nhưng ngoài dòng giấy (vd `lượt → lượt`) rơi khỏi chuỗi ⇒ số lượng đứng im ở 0 và bù hao biến mất. Chế bản KHÔNG bị kêu (vốn không chạm giấy). Hai tầng dùng chung một luật để không nói khác nhau về cùng dữ liệu.

**`dung_lam_toc_do`** (BOOLEAN NOT NULL DEFAULT FALSE, migration `0154`): đơn vị này có được bày trong ô "Đơn vị tốc độ" của màn Máy không — mã sinh ra là `<ma>_gio`. Cần cờ riêng vì bảng dùng CHUNG: đổ cả danh mục ra thì người khai máy phải chọn giữa `g/giờ`, `thùng/giờ`, `tấn/giờ`… (chủ soi ra 03/08/2026 — 17 dòng, quá nửa vô nghĩa với máy). 🔴 **"Xoá đơn vị tốc độ" trên màn Máy = BỎ CỜ, không xoá dòng** — xoá `kg` cho khuất mắt là gãy quy đổi bên kho và tiền khoán. Danh sách bật sẵn (`DON_VI_TOC_DO_MAC_DINH` trong `db_migrations.py`) là nguồn duy nhất, `seed_rebuild.seed_don_vi_do` import lại chứ không chép — migration chỉ bật LÚC TẠO CỘT, chạy lại sẽ không đè lựa chọn người dùng.

### `don_vi_quy_doi`

**Purpose:** CẶP quy đổi — mỗi dòng là một câu *"1 `tu` = `he_so` `den`"* (1 tấn = 1.000 kg · 1 ram = 500 tờ), đúng cách người ta nói ngoài đời. Nguồn chân lý của mọi phép đổi trong hệ.

Cạnh đi **hai chiều**: khai `tấn → kg = 1.000` là đủ để đổi ngược `kg → tấn` (nhân 1/1.000) — bắt khai hai dòng thì sớm muộn hai dòng lệch nhau, nên `find_cap` coi hai chiều là MỘT và chặn khai trùng. Cặp chưa khai thẳng thì `quy_doi_service.duong_di()` **dò đường BFS** qua trung gian (hỏi tấn → g thì đi qua kg, nhân dồn hệ số); BFS chứ không DFS để đường ít chặng nhất, sai số nhân dồn ít nhất.

**Chặn mâu thuẫn (không cho lưu):** thêm/sửa cặp mà lệch với đường đã có (đã có `1 tấn = 1.000 kg` + `1 kg = 1.000 g`, giờ khai `1 tấn = 999.000 g`) thì service từ chối và chỉ ra đường nào đang mâu thuẫn — chủ chốt 2026-07-30, vì số quy đổi chảy thẳng vào tiền khoán và tồn kho, lệch mà im lặng thì phát hiện ra đã trả lương sai mấy tháng. Sai số so sánh là TƯƠNG ĐỐI (`1e-6`) vì hệ số trải từ 0,001 tới 1.000.000.

🔴 **QUY ĐỔI ĐỘNG ĐÃ GỠ 14/08/2026 (mg `0198` DROP cột `cong_thuc`).** Cặp trong bảng này nay CHỈ mang hệ số cố định — không còn dòng nào kiểu *"1 tờ = dinh_luong × dai × rong kg"*.

Vì sao bỏ: cặp-mang-công-thức trả lời câu *"một tờ nặng mấy kg"*, nhưng cùng một đơn vị đích tới được bằng nhiều đường (`tờ → kg`, `tờ nguyên → kg`, `con → kg`) và ba đường cho ba số khác nhau ⇒ lúc bung BOM ở bước lệnh máy không có căn cứ chọn đường. Mô hình thay thế trả lời câu ĐÚNG hơn — *"cả lệnh này tốn bao nhiêu kg"* — và không đi qua đồ thị quy đổi:

| Khai ở đâu | Migration | Dùng khi |
|---|---|---|
| `don_vi_do.cong_thuc` (CÁCH ĐO của chính đơn vị) | `0192` | mọi vật tư dùng đơn vị đó, nếu không có công thức riêng |
| `vat_tu_in_an.cong_thuc_luong` | `0194` | vật tư khai riêng, đè lên cách đo của đơn vị |
| `giay_nguyen.cong_thuc_luong` | `0195` + `0197` điền sẵn `dinh_luong * dai_nguyen * rong_nguyen * to_nguyen` | giấy |

Thứ tự đọc (RIÊNG → CHUNG) ở `LsxService._luong_vat_tu`. Điểm khác cốt lõi: công thức cũ là **tỉ lệ cho MỘT đơn vị** rồi nhân với số lượng bước; công thức mới trả thẳng **LƯỢNG của cả lệnh**, nên đường "đã cấp"/"đang về" (số thật của phiếu kho) tuyệt đối không được chạy nó — xem cờ `tong_lenh` ở `ke_hoach_vat_tu_service._ve_goc`.

Thứ phụ thuộc từng mặt hàng ("1 thùng keo = 3 kg" khác "1 thùng mực = ? kg") KHÔNG khai ở đây — chỗ đó là `material.don_vi_phu` + `he_so_quy_doi`.

| Column | Type | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` | **PK** | no | auto | PK. |
| `tu_id` | `Integer` | **FK→don_vi_do.id**, **IX** | no | — | Vế trái. `ON DELETE CASCADE` — cặp mồ côi là đường đi MA, máy vẫn tính ra số mà không ai hiểu. |
| `den_id` | `Integer` | **FK→don_vi_do.id**, **IX** | no | — | Vế phải; `ON DELETE CASCADE`. |
| `he_so` | `Numeric(18,6)` | — | no | — | 1 `tu` = `he_so` `den`, LUÔN > 0 (service chặn 0/âm — chia 0 khi đi chiều ngược). |
| `ghi_chu` | `String(500)` | — | yes | — | Ghi chú. |
| `created_at` | `DateTime(tz)` | — | no | now | Khi tạo. |
| `updated_at` | `DateTime(tz)` | — | no | now | Khi sửa. |

- Unique: (`tu_id`, `den_id`) — `uq_don_vi_quy_doi_cap`. Bảng mới → `create_all` tự dựng; migration `0135` đổ dữ liệu từ `don_vi_do.he_so_goc` của mô hình cũ, `0137` thêm cột `cong_thuc` và `0198` gỡ lại chính nó (kèm xoá dòng động mồ côi `he_so = 0`).

### `kho_hang`

**Purpose:** danh mục KHAI BÁO kho (master data nhẹ) — mỗi dòng = 1 kho (vd "Kho thành phẩm") với mã / tên / vị trí / ghi chú. Đổ động ra navbar (mục "Kho hàng"); vận hành nhập/xuất/tồn để bản sau (KHÔNG kèm ở đây). Bảng mới → `create_all` tự dựng (không migration); tên `kho_hang` tránh đụng bảng `warehouses` cũ đã gỡ. Gác quyền module `kho`.

**Tất cả cột:** `id`, `ma`, `ten`, `vi_tri`, `ghi_chu`, `active`, `created_at`, `updated_at`.

### `khuon_be`

**Purpose:** danh mục KHAI BÁO nơi lưu trữ khuôn bế (master data nhẹ) — mỗi khuôn làm riêng cho hình bế của 1 ấn phẩm; đơn lặp lại thì lôi khuôn cũ ra dùng. Khai TAY để tìm lại: `ma` (KB-#### sinh ngầm) / `ten` (tên khuôn / ấn phẩm) / `khach_hang` (khai tay, đấu ref sau) / `so_ke` (số kệ, vị trí lưu — lõi) / `ngay_lam_khuon` / `tinh_trang` (dang_dung·hong·thanh_ly) / `ghi_chu`. Bảng mới → `create_all` tự dựng (không migration). Xóa mềm (`active=false`) giữ dấu vết. Gác quyền module RIÊNG `khuon_be`.

**Tất cả cột:** `id`, `ma`, `ten`, `khach_hang`, `so_ke`, `ngay_lam_khuon`, `tinh_trang`, `ngay_ve_du_kien`, `ghi_chu`, `active`, `created_at`, `updated_at`.

- `tinh_trang` (mg 0177) nhận thêm giá trị **`dang_dat_lam`** — khuôn CHƯA có trong tay, đang đặt thợ làm. Không phải DDL (`tinh_trang` là VARCHAR tự do, service kiểm giá trị theo hằng `TINH_TRANG`).
- `ngay_ve_du_kien` (`Date`, nullable, mg 0177) — chỉ có nghĩa với `dang_dat_lam`. Bàn xếp lịch so ngày này với giờ bắt đầu bước bế: về SAU giờ bế ⇒ vấn đề mức **Chặn**; về kịp ⇒ cảnh báo vàng. Không có nó thì `dang_dat_lam` chỉ là một chữ, không chặn được gì.

### ~~`bao_tri_phieu` · `bao_tri_hen` · `bao_tri_anh`~~ — MODULE ĐÃ GỠ 12/08/2026

Module **Bảo trì thiết bị** (FE + BE) bị gỡ hẳn theo yêu cầu chủ xưởng: model · repo · router ·
schema · service · seed · test và 4 file FE đều đã xoá, kèm mount router, module quyền `bao_tri`
trong `seed.py` / `role_service`, subdir storage `bao-tri`, migration `0187` + `0190`, và các mục
Sidebar / route / ma trận quyền.

⚠️ **Ba bảng vẫn NẰM LẠI trong Postgres dev/prod** — dự án không có Alembic nên `create_all`
không dựng lại mà cũng không drop. Không còn code nào đọc/ghi chúng. Muốn dọn thật thì drop tay;
để nguyên cũng không ảnh hưởng gì ngoài chỗ chứa.

Cái CÒN dùng của mảng bảo trì: khoá JSON `may_thiet_bi.fields_theo_loai.lich_bao_tri` (gói bảo trì
+ việc con, khai ở tab "Lịch bảo trì" màn Thiết bị) và bảng `machine_unavailable_periods` (vùng
khoá máy trên Gantt — nguồn của trạng thái *Đang bảo trì* / *Hỏng — chờ sửa* ở cột Trạng thái).

🔴 Module **Kỹ thuật máy** dựng 12/08/2026 (3 bảng `ky_thuat_*` ngay dưới) KHÔNG dùng lại ba tên
bảng trên — bảng cũ còn nằm trong Postgres nên `create_all` sẽ bỏ qua, model mới trỏ vào bảng thiếu
cột mà test SQLite (DB trắng) không bắt được.

### `ky_thuat_sua_chua`

**Purpose:** một lần máy hỏng, chạy từ lúc ghi nhận tới lúc sửa xong — module **Kỹ thuật máy**
(12/08/2026). Cố ý KHÔNG tách "phiếu báo hỏng" và "phiếu sửa chữa": cùng một máy, cùng một lần
hỏng, tách hai chứng từ là bắt thợ nhập hai lần rồi tự đi nối lại. Một vai thao tác (thợ sửa chữa)
⇒ không có bước duyệt, không tách người-sửa / người-nghiệm-thu. Gác quyền module `ky_thuat_may`.
Bảng mới → `create_all` tự dựng, không migration.

**Tất cả cột:** `id`, `ma` (SC-#### sinh ngầm), `may_id` (soft → `may_thiet_bi.id`),
`bo_phan_hong`, `mo_ta`, `muc_do` (nhe·trung_binh·nghiem_trong), `nguoi_bao_id` (soft →
`employees.id`), `nguoi_bao_ten` (snapshot), `thoi_diem`, `nguyen_nhan_phuong_an`, `trang_thai`
(cho_sua·dang_sua·cho_vat_tu·da_sua_xong), `hoan_thanh_at`, `hoan_thanh_boi`, `ghi_chu`,
`created_at`, `updated_at`.

- `nguoi_bao_id` là Ô CHỌN, KHÔNG mặc định bằng người đăng nhập: thợ đứng máy báo miệng, tổ kỹ
  thuật nhập hộ — lấy tên người đang gõ là ghi sai ngay từ đầu. Tên snapshot để nhân viên nghỉ
  việc vẫn tra được.
- `cho_vat_tu` lát này chỉ là chữ (thiếu đồ gì ghi vào `ghi_chu`); CHƯA nối `stock_requests`.
- Đóng phiếu (`da_sua_xong`) đòi **≥1 ảnh `giai_doan="sau"`** — chặn ở service, không cờ quyền nào bỏ qua.

### `ky_thuat_bao_tri`

**Purpose:** một lần bảo trì của một GÓI trên một máy (hoặc một lần đột xuất không thuộc gói nào).
Chu kỳ KHÔNG khai ở đây — nguồn là `may_thiet_bi.fields_theo_loai.lich_bao_tri`, phiếu chỉ neo
`goi_id` rồi snapshot tên/chu kỳ/việc con.

**Tất cả cột:** `id`, `ma` (PBT-####), `may_id`, `goi_id` (neo `lich_bao_tri[].id` dạng `hm-...`;
null = đột xuất), `goi_ten`, `chu_ky_so`, `chu_ky_don_vi` (ngay·tuan·thang·nam), `loai`
(dinh_ky·dot_xuat), `ngay_ke_hoach`, `ngay_ke_hoach_goc`, `ly_do_doi`, `hang_muc` (JSON
`[{id,ten,xong,bo_qua,ly_do_bo_qua}]`), `nguoi_thuc_hien_id`, `nguoi_thuc_hien`, `trang_thai`
(cho_thuc_hien·hoan_thanh), `ngay_hoan_thanh`, `hoan_thanh_boi`, `ghi_chu`,
`created_at`, `updated_at`.

- **Chỉ HAI trạng thái** (chủ chốt 12/08/2026): `cho_thuc_hien` → `hoan_thanh`. Nấc
  `dang_thuc_hien` và cả bước "nhận việc" ĐÃ BỎ — bảo trì định kỳ làm xong trong một lượt, bắt bấm
  hai lần chẳng nói thêm được gì. **mg 0193** đẩy phiếu đang kẹt ở nấc cũ về `cho_thuc_hien`
  (trạng thái lưu bằng CHUỖI nên DB không tự chặn: không dọn thì phiếu mang giá trị không còn
  trong `TRANG_THAI_BAO_TRI`, mọi tab đều không khớp và nó biến mất khỏi màn hình mà không báo lỗi).
- `nguoi_thuc_hien_id` (soft → `users.id`, **mg 0192**) — NGƯỜI LÀM = người bấm "Xác nhận đã bảo
  trì xong", **không có ô gõ tay, không có bước nhận việc**. `nguoi_thuc_hien` là TÊN SNAPSHOT để
  người nghỉ việc rồi vẫn tra được. Mở lại phiếu về `cho_thuc_hien` thì nhả cả hai cột — phiếu còn
  dở không mang tên ai. Thuê hãng ngoài ghi vào `ghi_chu`. ⚠️ Bảng dựng bằng `create_all` nên đã
  tồn tại trên Postgres dev từ trước ⇒ cột này BẮT BUỘC đi kèm migration, `create_all` không ALTER.

- **Đóng phiếu đi qua HAI cửa, cùng hạng (409), cùng nằm ở service** (14/08/2026): (1) checklist
  không còn việc nào chưa xử lý; (2) ≥1 ảnh `giai_doan="sau"`. Việc thật sự không phải làm kỳ này
  thì đánh `bo_qua=true` kèm `ly_do_bo_qua` (bắt buộc) ngay trong JSON `hang_muc` — không có đường
  lui đó thì thợ tick bừa cho qua và cái checklist mất sạch giá trị.
- **"Quá hạn" và "Đã dời" KHÔNG lưu** — dẫn xuất lúc đọc (`ngay_ke_hoach` đã qua mà chưa xong;
  `ngay_ke_hoach_goc` khác `ngay_ke_hoach`). Lưu là lại đẻ ra thứ phải nhớ đi cập nhật.
- `ngay_hoan_thanh` (Date) là MỐC NGHIỆP VỤ tính kỳ sau, không phải giờ bấm nút:
  `han_ke_tiep` = ngày hoàn thành gần nhất của gói + `chu_ky_so × chu_ky_don_vi`; chưa có phiếu nào
  thì lấy `goi.ngay_bat_dau`; **không có cả hai thì KHÔNG đoán** — trả `None` kèm lý do
  (`thieu_chu_ky` / `thieu_ngay_bat_dau`) để màn hình nói thành lời "chưa khai Bắt đầu từ". Bản đầu
  đoán là "tới hạn hôm nay" và một cú bấm đẻ ra 41 phiếu rác (12/08/2026) — đừng khôi phục.
- Mốc "lần cuối làm" **không ghi ngược** vào JSON của máy: form Máy dựng lại `fields_theo_loai` từ
  bản JSON nó đang giữ, backend ghi vào đó là bị lưu đè mất.

### `ky_thuat_may_anh`

**Purpose:** ảnh minh chứng dùng chung cho cả hai loại phiếu qua cặp (`loai_phieu`, `phieu_id`) —
một bảng chứ không hai, để mọi chỗ đọc/đếm/xoá ảnh chỉ viết một lần. File nằm dưới subdir
`ky-thuat-may/`, phục vụ qua `/api/files` và đòi quyền đọc `ky_thuat_may`.

**Tất cả cột:** `id`, `loai_phieu` (sua_chua·bao_tri), `phieu_id`, `giai_doan` (truoc·sau),
`file_name`, `file_url`, `file_type`, `uploaded_by`, `uploaded_at`.

- `giai_doan="truoc"` (hiện trạng) khuyến khích chứ không bắt buộc — máy hỏng lúc đang chạy đơn gấp
  mà bắt chụp trước mới cho ghi nhận là cản việc thật. `"sau"` mới là cái gác cửa đóng phiếu.

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

**Tất cả cột:** `id`, `phieu_id`, `thu_tu`, `loai_thanh_phan`, `ten`, `dai_thanh_pham`, `rong_thanh_pham`, `so_to_per_sp`, `so_trang`, `trang_moi_tay`, `so_luong`, `don_vi_tinh`, `nhom_bao_gia`, `loai_san_pham_id`, `giay_id`, `kho_nguyen`, `kho_nguyen_dai`, `kho_nguyen_rong`, `don_gia_giay`, `don_gia_don_vi`, `nguon_giay`, `chua_nhip`, `bleed_mm`, `khe_cat_mm`, `co_in`, `che_ban_loai`, `che_ban_don_gia`, `quy_cach_in`, `kho_in_dai`, `kho_in_rong`, `so_con`, `con_auto`, `may_id`, `don_gia_cong_in`, `muc_a`, `muc_b`, `so_mau_a`, `so_mau_b`, `so_mau_pha`, `ghi_chu_ky_thuat`, `gia_von_tp`, `created_at`, `updated_at`. `ghi_chu_ky_thuat` (TEXT nullable, migration 0079) = ghi chú KỸ THUẬT/SX theo SẢN PHẨM (canh màu như mẫu · kẽm cũ · bù hao) — gõ ở Tính giá, xuống drawer lệnh SX; kỹ thuật, KHÔNG giá; khác `orders.production_note` (cấp đơn). `don_vi_tinh` (VARCHAR, migration 0074, default `'cái'`) = ĐVT sản phẩm (text tự do) → chảy sang Báo giá (`quote_items.unit`, thay `'cái'` hardcode). `kho_nguyen_dai`/`kho_nguyen_rong` (mm, migration 0063) = khổ giấy nguyên ① nhập trên phiếu, ĐÈ khổ danh mục Giấy khi > 0 (đặt hàng xả khổ khác); 0 = lấy theo danh mục. `kho_nguyen` giữ làm nhãn hiển thị / `giay_ten` fallback. `bleed_mm`/`khe_cat_mm` (mm, migration 0108) = tràn lề MỖI CẠNH con và khe giữa 2 con kề nhau, sale nhập trên phiếu; 0 = không tràn lề / bình sát cắt chung nhát. **Chừa trừ theo CHIỀU, không gộp — nguồn là DANH MỤC MÁY:** chiều DÀI ← `may_thiet_bi.nhip_giay_mm` + `duoi_thang_mau_mm`; chiều RỘNG ← `le_hong_mm` ×2. Phiếu chỉ giữ MỘT ô đè `chua_nhip` (>0 thì thay nhíp của máy). `chua_tay_ke`/`chua_duoi`/`chua_xen`/`chua_ca_gay` đã DROP (mig `0139`): không có chỗ nhập, mà xén/gáy còn bị cộng đều cả hai chiều. `so_trang` / `trang_moi_tay` (migration `0147`, default 1) = số **TRANG NỘI DUNG** của 1 sản phẩm và số trang mỗi tay gấp — người dùng khai ở popover "tính từ số trang" và nay được **LƯU** (trước đây popover tính xong chỉ còn lại kết quả, mở lại không biết đã tính từ đâu). Số tờ in đi thẳng từ đây: `to_net = ceil(so_luong × so_trang / con)`. Tờ rời để `1/1` → về đúng `so_luong / con` như trước. `so_to_per_sp` = số **BÀI IN (khuôn)** khác nhau của 1 sản phẩm, nay **DẪN XUẤT** `ceil(so_trang / trang_moi_tay)` (engine ghi lại vào cột mỗi lần tính, client gửi lên bị bỏ qua) và chỉ còn nhân `so_kem` — KHÔNG còn nhân `to_net`: chia số TAY cho số CON là chia hai đại lượng khác đơn vị, sách bình tay vì thế ra sai. **Đã BỎ ở migration `0144`:** `kho_thanh_pham` · `kho_mo_rong` · `tay_gap` — ô nhập gỡ khỏi màn phiếu từ 2026-07-29 nên phiếu mới luôn rỗng, nhưng bản Lệnh sản xuất vẫn vẽ ba dòng "—" làm người đọc tưởng phiếu có khai. Phiếu cũ có `kho_thanh_pham` dạng nhãn chữ ("14,5×20,5 cm (A5)") — phần số trùng hoàn toàn với `dai_thanh_pham`/`rong_thanh_pham`, chỉ mất chú thích trong ngoặc; `quy_cach_json` của lệnh cũ vẫn giữ nguyên nhãn. Khổ thành phẩm THẬT là `dai_thanh_pham` / `rong_thanh_pham` (mm, nuôi bình bài). Cột cùng tên ở cấp phiếu (`phieu_tinh_gia.kho_thanh_pham`) là thứ KHÁC, giữ nguyên. `don_vi_tinh` nay đi qua engine (`_TP_SCALAR_FIELDS`) → Lệnh SX kế thừa ĐVT + tên sản phẩm từ PHIẾU; riêng SỐ LƯỢNG vẫn lấy từ ĐƠN (`order_line.qty`) vì đơn đặt theo đợt còn phiếu báo giá cho cả lô.

`muc_a` / `muc_b` (JSON, migration `0154`) = **TẬP MÃ MỰC** của mặt A và mặt B — nguồn sự thật của số kẽm. `C`/`M`/`Y`/`K` là bốn mã process cố định; mọi mã khác là màu pha, chuỗi tự do đã chuẩn hoá (viết hoa, gộp khoảng trắng). KHÔNG có danh mục mực — hợp tập chỉ tính trong phạm vi MỘT thành phần (ruột và bìa là hai bộ bản riêng) nên mã chỉ cần khớp giữa hai mặt của cùng sản phẩm, và UI cho bấm lại mã của mặt kia thay vì gõ lại.

**Số kẽm** (`so_kem_moi_tay` trong `thanh_phan_engine`, nhân `so_to_per_sp`): `1 mặt` → `|A|`; `AB` → `|A| + |B|` (hai mặt hai bộ bản riêng, cùng một Pantone hai mặt vẫn ra hai bản); `tự trở` / `trở nhíp` → **`|A ∪ B|`** (cả hai mặt chung MỘT bộ bản, in xong lật tờ chạy lại chính bản đó). `max(|A|,|B|)` là rút gọn SAI cho nhánh tự trở — nó chỉ đúng khi tập mặt ít màu nằm gọn trong tập mặt kia; mặt A `CMYK` với mặt B `185C` phải ra 5 bản còn `max` ra 4.

`so_mau_a` / `so_mau_b` / `so_mau_pha` nay là **DẪN XUẤT** của hai tập trên (`so_mau_dan_xuat`), engine tính rồi ghi đè xuống cột mỗi lần tính — client gửi lên bị bỏ qua. Nghĩa GIỮ NGUYÊN như trước: `so_mau_a/b` đếm mực PROCESS mỗi mặt, `so_mau_pha` (migration 0109) đếm mực PHA phân biệt của cả hai mặt gộp lại. Giữ cột + giữ nghĩa để ~28 chỗ đang đọc chúng (công thức mực `so_mau = a + b + pha`, `_may_fit` so số màu với đầu mực máy, lệnh SX, bài ghép, báo giá) không phải sửa gì. Backfill của `0154` (`N màu` → tiền tố `[K, C, M, Y]`, màu pha gắn mặt A) khiến tập bên ít màu LUÔN là con của bên nhiều màu, nên `|A ∪ B| = max` và **TỔNG** `so_mau_a + so_mau_b + so_mau_pha` — thứ công thức tiền mực dùng — giữ nguyên ở mọi tổ hợp. Số kẽm chỉ đổi ở hai ca engine cũ tính SAI: (1) tự trở/trở nhíp có mặt B nhiều màu hơn mặt A (cũ bỏ hẳn mặt B), (2) khai `so_mau_a ≥ 5` rồi in tự trở (process chỉ có 4 màu; backfill đọc phần dư thành mực riêng của từng mặt, còn `so_mau_pha` dẫn xuất nhận phần dư đó — tổng vẫn khớp). Đo trên DB dev 2026-08-05: 0 hàng rơi vào ca (1); 2 hàng khai 5 màu nhưng đều `mot_mat` nên kẽm không đổi.

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

### `supplier_items`

**Purpose:** Thu mua — mặt hàng/bảng giá hiện tại theo từng nhà cung cấp. One row = 1 vật tư/sản phẩm/dịch vụ NCC có thể cung cấp.

**Tất cả cột:** `id`, `supplier_id`, `item_name`, `unit`, `unit_price`, `vat_percent`, `is_active`, `note`, `created_at`, `updated_at`.

---

### `purchase_requests`

**Purpose:** Thu mua — phiếu mua hàng (PMH) gửi Kế toán duyệt. One row = 1 PMH.

**Tất cả cột:** `id`, `code`, `status`, `supplier_id`, `purpose`, `needed_date`, `expected_receipt_date`, `created_by_user_id`, `submitted_at`, `approved_by_user_id`, `approved_at`, `note`, `created_at`, `updated_at`.

---

### `purchase_request_lines`

**Purpose:** Thu mua — dòng hàng của PMH (mặt hàng, SL đặt, SL thực nhận, đơn giá, giảm giá %, VAT %). Tiền tính động.

**Tất cả cột:** `id`, `purchase_request_id`, `department_request_line_id`, `item_name`, `unit`, `quantity`, `received_quantity`, `expected_unit_price`, `discount_percent`, `vat_percent`, `note`.

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

**Purpose:** Kế toán — tài khoản ngân hàng công ty dùng chung cho thu/chi. One row = 1 TK.

**Tất cả cột:** `id`, `account_holder`, `account_number`, `bank_name`, `bank_branch`, `currency`, `is_default`, `is_active`, `use_for_receipts`, `use_for_payments`, `note`, `created_at`, `updated_at`.

---

### `supplier_bank_accounts`

**Purpose:** Kế toán — tài khoản ngân hàng thụ hưởng của NCC. One row = 1 TK NCC.

**Tất cả cột:** `id`, `supplier_id`, `account_holder`, `account_number`, `bank_name`, `bank_branch`, `currency`, `is_default`, `is_active`, `note`, `created_at`, `updated_at`.

---

### `payment_vouchers`

**Purpose:** Kế toán — chứng từ chi (Phiếu chi / Ủy nhiệm chi) từ PMH. One row = 1 chứng từ; nhiều cột `*_snapshot` chốt thông tin NCC/ngân hàng tại thời điểm lập.

**Tất cả cột:** `id`, `code`, `doc_no`, `source_type`, `purchase_request_id`, `supplier_id`, `voucher_type`, `payment_stage`, `status`, `voucher_date`, `planned_payment_date`, `amount`, `amount_vnd`, `currency`, `exchange_rate`, `content`, `invoice_number`, `invoice_date`, `contract_number`, `company_bank_account_id`, `supplier_bank_account_id`, `cash_recipient_name`, `cash_recipient_address`, `cash_recipient_identity`, `bank_fee_bearer`, `bank_reference`, `debit_account`, `credit_account`, `source_code_snapshot`, `supplier_name_snapshot`, `supplier_tax_code_snapshot`, `supplier_address_snapshot`, `company_account_holder_snapshot`, `company_account_number_snapshot`, `company_bank_name_snapshot`, `company_bank_branch_snapshot`, `beneficiary_account_holder_snapshot`, `beneficiary_account_number_snapshot`, `beneficiary_bank_name_snapshot`, `beneficiary_bank_branch_snapshot`, `created_by_user_id`, `paid_by_user_id`, `paid_at`, `cancelled_by_user_id`, `cancelled_at`, `cancel_reason`, `note`, `created_at`, `updated_at`.

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

**Purpose:** Kế toán — Phiếu thu đa nguồn (V5): hoàn ứng từ Phiếu chi đã chi (`purchase_refund`), thu cọc khách từ Đơn hàng bán (`order_deposit`), thu công nợ theo Hóa đơn bán (`sales_invoice`) hoặc thu khác/thu độc lập (`other`).

**Tất cả cột:** `id`, `code`, `doc_no`, `source_type`, `payment_voucher_id`, `purchase_request_id`, `order_id`, `sales_invoice_id`, `payer_name`, `payer_address`, `receipt_method`, `status`, `receipt_date`, `amount`, `amount_vnd`, `currency`, `exchange_rate`, `content`, `company_bank_account_id`, `bank_reference`, `debit_account`, `credit_account`, `voucher_code_snapshot`, `purchase_code_snapshot`, `supplier_name_snapshot`, `customer_name_snapshot`, `order_no_snapshot`, `company_account_holder_snapshot`, `company_account_number_snapshot`, `company_bank_name_snapshot`, `company_bank_branch_snapshot`, `created_by_user_id`, `received_by_user_id`, `received_at`, `cancelled_by_user_id`, `cancelled_at`, `cancel_reason`, `note`, `created_at`, `updated_at`.

---

### `payment_voucher_attachments`

**Purpose:** Kế toán — ảnh/chứng từ scan đính kèm Phiếu chi.

**Tất cả cột:** `id`, `payment_voucher_id`, `file_name`, `file_url`, `file_type`, `uploaded_by`, `uploaded_at`.

---

### `payment_receipt_attachments`

**Purpose:** Kế toán — ảnh/chứng từ scan đính kèm Phiếu thu.

**Tất cả cột:** `id`, `payment_receipt_id`, `file_name`, `file_url`, `file_type`, `uploaded_by`, `uploaded_at`.

---

## Kế hoạch & Lệnh sản xuất — LSX (bản dựng lại 2026-07)

> Mô hình 3 tầng chuẩn print MIS: **Job** (`orders` + `order_lines`) → **Part** (`lsx`) →
> **Operation** (`lsx_cong_doan`). Mỗi DÒNG ĐƠN sinh đúng 1 lệnh; các lệnh NGANG HÀNG (không
> cha-con). Quy cách + routing CHỤP SNAPSHOT lúc tạo lệnh (`quy_cach_json` + các dòng
> `lsx_cong_doan`) nên sửa phiếu tính giá về sau không lay lệnh, và sửa routing tại lệnh không
> ngược lên phiếu tính giá. Số lượng lấy từ ĐƠN (`order_lines.qty`), không lấy số lúc tính giá.
> FK THẬT: `lsx.order_id`/`order_line_id` + `lsx_cong_doan.lsx_id`; FK danh mục (máy · khuôn ·
> công đoạn · tổ · users) là MỀM. Bảng mới → `create_all` tự tạo (không migration).
> Ghép bài (nhiều lệnh in chung 1 tờ) là tầng KHÁC, dựng ở pha sau.

### `lsx`

**Purpose:** 1 lệnh sản xuất = 1 dòng đơn hàng = 1 "chi tiết sản phẩm" đã tính giá. Hồ sơ sản xuất độc lập: số lượng · bù hao · quy cách snapshot · routing · hạn · trạng thái.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto | Surrogate PK. |
| `ma` | `String(30)` → `VARCHAR(30)` | U, IX | no | — | `LSX26-0001` (`SequenceService.generate_code("job")`). |
| `loai` | `String(20)` | — | no | `san_xuat_moi` | `san_xuat_moi`/`bo_sung`/`bu`/`lam_lai`/`mau`/`noi_bo`. Lát 1 chỉ sinh loại mới. |
| `lsx_goc_id` | `Integer` | IX | yes | — | Soft → `lsx.id`: lệnh gốc của bổ sung/bù/làm lại (pha sau). |
| `ten` | `String(255)` | — | no | `""` | Tên chi tiết sản phẩm (snapshot `order_lines.description`). |
| `order_id` | `Integer` | FK→`orders.id`, IX | no | — | Đơn nguồn. |
| `order_line_id` | `Integer` | FK→`order_lines.id`, IX | no | — | Dòng đơn nguồn — 1 dòng chỉ 1 lệnh `san_xuat_moi` (guard ở service). |
| `quote_version_id` | `Integer` | — | yes | — | Soft → `quote_versions.id`: phiên bản báo giá đã chốt (truy vết). |
| `phieu_thanh_phan_id` | `Integer` | — | yes | — | Soft → `phieu_thanh_phan.id`: chi tiết tính giá nguồn. CHỈ truy vết — id đổi mỗi lần lưu PTG (replace-all) nên KHÔNG đọc-sống. |
| `so_luong_dat` | `Integer` | — | no | `0` | SL khách đặt = `order_lines.qty`. |
| `don_vi_tinh` | `String(30)` | — | no | `cái` | ĐVT thành phẩm (từ dòng đơn). |
| `so_to_ke_hoach` | `Integer` | — | no | `0` | Tờ vào máy (`to_dau_vao`). |
| `so_to_nguyen` | `Integer` | — | no | `0` | Tờ giấy nguyên cần xuất (`to_nguyen`). |
| `so_con` | `Integer` | — | no | `1` | Con/tờ (bình bài). |
| `ban_giao_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Mốc Sale chuyển xuống SX (snapshot `orders.san_xuat_released_at`). |
| `han_giao_khach` | `Date` → `DATE` | — | yes | — | Hạn giao khách (snapshot `orders.delivery_committed_date`). |
| `han_hoan_thanh_sx` | `Date` → `DATE` | — | yes | — | Hạn nội bộ — kế hoạch nhập. |
| `is_rush` | `Boolean` → `BOOLEAN` | — | no | `false` | Ưu tiên gấp (snapshot `orders.is_rush`, sửa được). |
| `quy_cach_json` | `JSON` | — | yes | — | Snapshot quy cách: khổ ①②③ · giấy + định lượng · số màu A/B · cách in · chừa · số kẽm · số lượt · ghi chú kỹ thuật. Read-only ở lát 1. |
| `routing_goc_json` | `JSON` | — | yes | — | Ảnh chụp routing LÚC TẠO lệnh (list rút gọn: `ten`·`nhom`·`loai_buoc`). CHỈ để cảnh báo "routing đã đổi so với bài tính giá" — không dùng tính lại gì. |
| `khuon_be_id` | `Integer` | IX | yes | — | Soft → `khuon_be.id` — kế hoạch gán khuôn. |
| `may_id` | `Integer` | IX | yes | — | Soft → `may_thiet_bi.id` — máy in dự kiến. |
| `trang_thai` | `String(20)` | — | no | `nhap` | `nhap` → `cho_bo_sung` → `san_sang` → `da_lap_ke_hoach` (đã sinh dòng xếp lịch → routing khóa). Mốc phát hành/thực thi thuộc pha sau. |
| `nguoi_phu_trach_id` | `Integer` | IX | yes | — | Soft → `users.id` — người kế hoạch phụ trách lệnh. |
| `ghi_chu` | `Text` | — | yes | — | Ghi chú kế hoạch. |
| `created_by` | `Integer` | — | yes | — | Soft → `users.id`. |
| `created_at` | `DateTime(timezone=True)` | — | no | now | |
| `updated_at` | `DateTime(timezone=True)` | — | no | now/onupdate | |

**Tất cả cột:** `id`, `ma`, `loai`, `lsx_goc_id`, `ten`, `order_id`, `order_line_id`, `quote_version_id`, `phieu_thanh_phan_id`, `so_luong_dat`, `don_vi_tinh`, `so_to_ke_hoach`, `so_to_nguyen`, `so_con`, `ban_giao_at`, `han_giao_khach`, `han_hoan_thanh_sx`, `is_rush`, `quy_cach_json`, `routing_goc_json`, `khuon_be_id`, `may_id`, `trang_thai`, `nguoi_phu_trach_id`, `ghi_chu`, `created_by`, `created_at`, `updated_at`.

---

### `lsx_cong_doan`

**Purpose:** 1 bước routing của lệnh (Operation) — copy từ `phieu_thanh_pham` lúc tạo, kế hoạch sửa được (thêm/bỏ/đổi thứ tự/đổi tổ/đổi máy/thuê ngoài/số lượng/thời gian). Mỗi bước mang SL + ĐƠN VỊ VÀO/RA riêng vì đơn vị đổi qua ranh giới xén (5.170 tờ vào → 20.680 con ra, hệ số 4).

Mô hình thời gian bám Dynamics 365 BC (nền của print MIS PrintVis): **setup tính 1 lần/lệnh, chạy scale theo SL**. **Chốt 2026-08-04** — bước loại MÁY dùng đúng một công thức, mọi số đều KẾ THỪA SỐNG từ `may_thiet_bi` (người kế hoạch không sửa được tại bước):

> `thời lượng = phat_sinh_phut + makeready_time_default + so_luong_vao × 60 ÷ toc_do × so_luot_chay`

Trả về BA số bằng cách thay `toc_do` bằng `toc_do_max` / `toc_do` / `toc_do_min` → `chiem_may_phut_min` / `chiem_may_phut` / `chiem_may_phut_max`. **Gantt đặt thanh theo số TRUNG BÌNH** và vẽ RÂU nhanh–chậm ở đuôi; máy chưa khai dải thì cả ba bằng nhau (không vẽ râu). Đơn vị tốc độ của máy phải khớp đơn vị bước đang đếm (`to`⟷`to_gio`…), lệch thì chạy = 0 + cảnh báo `don_vi_lech` chứ KHÔNG quy đổi bừa. Bước TỔ giữ lối cũ (năng suất đầu việc ÷ số người) và không có dải. `cho_phut`/`di_chuyen_phut`/`ve_sinh_phut`/`setup_phut`/`chay_phut` đã thành DORMANT — còn cột, không đọc.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` | **PK** | no | auto | |
| `step_key` | `String(36)` | U, IX | no | UUID | Khóa bất biến để upsert routing và tham chiếu phụ thuộc. |
| `lsx_id` | `Integer` | FK→`lsx.id` (CASCADE), IX | no | — | Lệnh chứa bước. |
| `thu_tu` | `Integer` | — | no | `0` | Chỉ dùng trình bày; quan hệ trước–sau nằm ở bảng phụ thuộc. |
| `cong_doan_id` | `Integer` | IX | yes | — | Soft → `cong_doan.id`. `null` = bước tên tự do. |
| `ten` | `String(255)` | — | no | `""` | Tên bước (snapshot hiển thị). |
| `nhom` | `String(12)` | — | yes | — | `prepress`/`print`/`finishing` (snapshot). |
| `department_id` | `Integer` | IX | yes | — | Soft → `departments.id` = tổ nhận việc (snapshot `cong_doan.department_id`). Cũng là "trung tâm sản xuất" — KHÔNG có bảng work_center riêng. |
| `may_id` | `Integer` | IX | yes | — | Soft → `may_thiet_bi.id` cho bước này. |
| `khuon_be_id` | `Integer` | IX | yes | — | Soft → `khuon_be.id` — khuôn dùng cho CHÍNH bước này (chỉ có nghĩa khi công đoạn nguồn bật `requires_tooling` với `tooling_type` là `khuon_be`/`khuon_ep`). Trước 11/08/2026 khuôn gán ở cấp lệnh (`lsx.khuon_be_id`) nên lệnh vừa Bế vừa Ép nhũ chỉ giữ được một khuôn — mg `0185` chuyển xuống bước. |
| `loai_buoc` | `String(12)` | — | no | `may` | Snapshot `may|to|thue_ngoai`. |
| `bat_buoc` | `Boolean` → `BOOLEAN` | — | no | `true` | Bước bắt buộc hay tùy chọn (§4.1). |
| `so_luong_vao` | `Numeric(14,2)` | — | no | `0` | SL đầu vào bước. |
| `so_luong_ra` | `Numeric(14,2)` | — | no | `0` | SL đầu ra bước. |
| `don_vi_vao` | `String(24)` | — | no | `to` | Mã trong `don_vi_do` — kế thừa từ `cong_doan.don_vi_vao` khi bung lệnh. Bước có nằm trên dòng giấy hay không đọc cờ `don_vi_do.tram_dong_giay`, KHÔNG suy từ "có khai đơn vị hay không" (mg `0186` nới từ 12). |
| `don_vi_ra` | `String(24)` | — | no | `to` | Như trên — khác `don_vi_vao` là bình thường ở bước đổi đơn vị (xả giấy `to_nguyen→to`, bế/xén `to→cai`). |
| `he_so_quy_doi` | `Numeric(12,4)` | — | no | `1` | Nhân khi đơn vị vào ≠ ra (tờ→con = số con/tờ). Vào ≠ ra mà hệ số vẫn `1` → chặn "Sẵn sàng". |
| `hao_hut` | `Numeric(14,2)` | — | no | `0` | Hao hụt TUYỆT ĐỐI (BC: Fixed Scrap Qty) — tờ canh máy, không theo SL. |
| `hao_hut_pct` | `Numeric(6,2)` | — | no | `0` | Hao hụt THEO % SL (BC: Scrap Factor %). Tính ngược: `SL_vào = SL_ra × (1 + pct) + hao_hut`, cộng dồn từ bước CUỐI về ĐẦU. Mặc định ← `cong_doan.spoilage_pct`. |
| `so_luot_chay` | `Integer` | — | no | `1` | Chỉ áp dụng cho bước Máy; nhân vào thời gian chạy. |
| `setup_phut` | `Numeric(10,2)` | — | no | `0` | Chuẩn bị máy, tính 1 LẦN/lệnh (không scale theo SL). Mặc định ← `cong_doan.setup_time`. |
| `nang_suat` | `Numeric(12,2)` | — | yes | — | Sản lượng/giờ. Mặc định ← `may_thiet_bi.toc_do`. |
| `don_vi_nang_suat` | `String(32)` | — | yes | — | Bước Máy: suy ra `to_gio`/`cai_gio`/`kem_gio`. Bước Tổ: mã người khai chọn ở định mức đầu việc (mg 0159 nới 10→32 vì `ban_proof_gio` dài 13). |
| `chay_phut` | `Numeric(10,2)` | — | yes | — | Người kế hoạch GÕ ĐÈ thời gian chạy. `null` = để máy tính từ `nang_suat`. |
| `ve_sinh_phut` | `Numeric(10,2)` | — | no | `0` | **DORMANT 2026-08-04** — vệ sinh/rửa mực đã gỡ khỏi hệ: không còn ô nhập, engine KHÔNG cộng vào thời gian chiếm máy, bước mới luôn ghi `0`. Cột giữ để không mất số cũ (không có Alembic). |
| `phat_sinh_phut` | `Numeric(10,2)` | — | no | `0` | "Thời gian khác" — phút phát sinh người kế hoạch gõ thêm (migration `0153`). Ô **DUY NHẤT** còn gõ được ở tab Thời gian: chuẩn bị + tốc độ nay kế thừa SỐNG từ `may_thiet_bi`. Cộng thẳng vào thời gian chiếm máy. |
| `cho_phut` | `Numeric(10,2)` | — | no | `0` | 🔴 GỠ KHỎI MODEL 13/08/2026 — cột còn trong DB, không code nào đọc. |
| `di_chuyen_phut` | `Numeric(10,2)` | — | no | `0` | Di chuyển bán thành phẩm sang tổ/máy kế. KHÔNG chiếm máy. |
| `so_nhan_cong` | `Integer` | — | no | `1` | Số người kế hoạch. Chỉ bước Tổ dùng để tính năng suất; kíp Máy không tăng tốc máy. |
| `so_nhan_cong_tieu_chuan` | `Integer` | — | no | `1` | Snapshot người tiêu chuẩn của đầu việc/kíp máy. |
| `so_nhan_cong_toi_da` | `Integer` | — | yes | — | Snapshot ngưỡng hiệu quả tối đa của đầu việc Tổ. |
| `khoan_json` | `JSON` | — | yes | — | ĐẦU VIỆC KHOÁN của bước — kế hoạch chọn "bước cán này làm *cán mờ* hay *ghép metalize*" (cùng công đoạn, hai đơn giá). SNAPSHOT `{rate_id, ten, don_vi, don_gia}` từ `piece_rates`, KHÔNG đọc-sống: xưởng lên giá khoán về sau không được xê dịch lệnh đã phát. Tiền khoán là số DẪN XUẤT (tính lúc đọc trong `lsx_service._khoan_derived`), không lưu cột. |
| `nha_cung_cap` | `String(150)` | — | yes | — | Nhà gia công khi `loai_buoc='thue_ngoai'` — khai TAY (cơ sở nhỏ thường chưa có trong `suppliers`). |
| `sl_gui` | `Numeric(14,2)` | — | yes | — | SL gửi đi gia công. |
| `ngay_gui_dk` | `Date` | — | yes | — | Ngày dự kiến gửi. |
| `van_chuyen_ngay` | `Numeric(6,2)` | — | yes | — | Thời gian vận chuyển 1 chiều (ngày). |
| `gia_cong_ngay` | `Numeric(6,2)` | — | yes | — | Thời gian gia công tại NCC (ngày). |
| `ngay_nhan_dk` | `Date` | — | yes | — | Ngày dự kiến nhận lại. Có nút gợi ý `gửi + vận chuyển + gia công + vận chuyển`, người quyết. |
| `hao_hut_cho_phep` | `Numeric(14,2)` | — | yes | — | Hao hụt cho phép ở NCC. |
| `don_gia_gia_cong` | `Numeric(18,2)` | — | yes | — | Giá gia công dự kiến. |
| `yeu_cau_ky_thuat` | `Text` | — | yes | — | Yêu cầu kỹ thuật gửi NCC. |
| `nguoi_giao_id` | `Integer` | IX | yes | — | Soft → `users.id` — ai mang hàng ra cổng (THỰC TẾ). |
| `giao_luc` | `DateTime(tz)` | — | yes | — | Ngày giờ giao THỰC. Trống = chưa gửi. |
| `sl_giao_thuc` | `Numeric(14,2)` | — | yes | — | Số THỰC gửi (khác `sl_gui` là dự kiến). |
| `nguoi_nhan_id` | `Integer` | IX | yes | — | Soft → `users.id` — ai nhận hàng về. |
| `nhan_luc` | `DateTime(tz)` | — | yes | — | Ngày giờ nhận THỰC. Có `giao_luc` mà trống = đang ở ngoài. |
| `sl_nhan_thuc` | `Numeric(14,2)` | — | yes | — | Số THỰC nhận. Hụt = `sl_giao_thuc − sl_nhan_thuc` (dẫn xuất, không lưu). |
| `ghi_chu` | `String(500)` | — | yes | — | |
| `created_at` | `DateTime(timezone=True)` | — | no | now | |
| `updated_at` | `DateTime(timezone=True)` | — | no | now/onupdate | |

> **Derived, KHÔNG lưu cột** (engine `lsx_service.thoi_luong_buoc(cd, may)` tính): `chiem_may_phut = phat_sinh + chuẩn bị(máy) + chạy(theo tốc độ máy)` · `chiem_may_phut_min`/`_max` theo `toc_do_max`/`toc_do_min` · `tong_phut = chiem_may_phut` (chờ/di chuyển đã bỏ) · `ty_le_hao_hut = hao_hut / so_luong_vao` · lead time cả lệnh.
> **Đã BỎ ở migration `0093`:** `thue_ngoai` (tập con của `loai_buoc`) · `don_vi` (tách thành `don_vi_vao`/`don_vi_ra`).

**Tất cả cột:** `id`, `step_key`, `lsx_id`, `thu_tu`, `cong_doan_id`, `ten`, `nhom`, `department_id`, `may_id`, `loai_buoc`, `bat_buoc`, `so_luong_vao`, `so_luong_ra`, `don_vi_vao`, `don_vi_ra`, `he_so_quy_doi`, `hao_hut`, `hao_hut_pct`, `so_luot_chay`, `setup_phut`, `nang_suat`, `don_vi_nang_suat`, `chay_phut`, `ve_sinh_phut`, `phat_sinh_phut`, `cho_phut`, `di_chuyen_phut`, `so_nhan_cong`, `so_nhan_cong_tieu_chuan`, `so_nhan_cong_toi_da`, `so_nhan_cong_toi_thieu`, `so_nhan_cong_toi_thieu`, `khoan_json`, `nha_cung_cap`, `sl_gui`, `ngay_gui_dk`, `van_chuyen_ngay`, `gia_cong_ngay`, `ngay_nhan_dk`, `hao_hut_cho_phep`, `don_gia_gia_cong`, `yeu_cau_ky_thuat`, `nguoi_giao_id`, `giao_luc`, `sl_giao_thuc`, `nguoi_nhan_id`, `nhan_luc`, `sl_nhan_thuc`, `ghi_chu`, `created_at`, `updated_at`.

### `lsx_cong_doan_vat_tu`

**Purpose:** nhu cầu vật tư khai trực tiếp trên từng bước LSX; chỉ snapshot nhận diện/đơn vị, không lưu giá hay trạng thái tồn.

**Tất cả cột:** `id`, `lsx_cong_doan_id`, `vat_tu_id`, `vat_tu_ma_snapshot`, `vat_tu_ten_snapshot`, `don_vi_snapshot`, `so_luong`, `thu_tu`, `tu_dong`.

`tu_dong` (BOOLEAN NOT NULL DEFAULT false, mg `0191`): **MÁY BUNG hay NGƯỜI KHAI.** `true` = dòng máy tự thêm khi người kế hoạch chọn "Công việc khoán" ở bước (danh sách lấy từ `cong_doan_dau_viec_vat_tu`, số lượng quy đổi từ `so_luong_vao` của bước) ⇒ lần bung sau được **thay** bộ mới. `false` = người tự thêm, hoặc dòng máy bung nhưng người đã sửa số lượng ⇒ máy **CHỪA RA**, không ghi đè. Không có cờ này thì đổi công việc khoán một cái là mất sạch số người vừa chỉnh.

### `lsx_cong_doan_phu_thuoc`

**Purpose:** cạnh DAG giữa hai bước LSX, cho phép nhiều tiền nhiệm và xuyên LSX trong cùng đơn hàng.

**Tất cả cột:** `id`, `buoc_truoc_id`, `buoc_sau_id`, `created_at`.

---

### `bai_ghep`

**Purpose:** Header một bài ghép (gang form) — gom các công đoạn chạy chung của nhiều LSX trên 1 tờ, 1 lần lên máy. 1 dòng = 1 bài ghép. Chỉ quản phần chạy chung (giấy + khổ tờ in chung + máy + hao hụt); mỗi LSX vẫn độc lập. Chung không chỉ có mỗi bước in — các bước chung do NGƯỜI khai, xem `bai_ghep_cong_doan`.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto | Surrogate PK. |
| `ma` | `String(30)` → `VARCHAR(30)` | U, IX | no | — | `GB26-0001` (`SequenceService.generate_code("bai_ghep")`). |
| `trang_thai` | `String(20)` | — | no | `nhap` | `nhap` → `san_sang` → `da_lap_ke_hoach` (đã lập kế hoạch → khóa sửa thành viên/giấy). Mốc phát hành/in thuộc pha sau. |
| `giay_id` | `Integer` | IX | yes | — | Soft → `giay_nguyen.id` — giấy chạy chung (1 tờ ghép 1 loại giấy). |
| `kho_in_dai` | `Integer` | — | yes | — | Khổ tờ in chạy chung (mm). |
| `kho_in_rong` | `Integer` | — | yes | — | Khổ tờ in chạy chung (mm). |
| `may_id` | `Integer` | IX | yes | — | Soft → `may_thiet_bi.id` — máy in (không bắt buộc lát 1). |
| `hao_hut_setup` | `Integer` | — | yes | — | Tờ bù canh máy. **NULL = chưa khai** → bài dùng hao máy đề xuất; **0 = khai "chạy đúng số, không bù"**. Hai ý này từng chung giá trị 0 nên `... or hao_de_xuat` nuốt mất ý định khai 0 (mig `0152`). |
| `hao_hut_chay` | `Integer` | — | yes | — | Tờ bù khi chạy. NULL/0 xem `hao_hut_setup`. |
| `ghi_chu` | `Text` | — | yes | — | Ghi chú kế hoạch. |
| `created_by` | `Integer` | — | yes | — | Soft → `users.id`. |
| `created_at` | `DateTime(timezone=True)` | — | no | now | |
| `updated_at` | `DateTime(timezone=True)` | — | no | now/onupdate | |

> **Derived, KHÔNG lưu cột** (engine `bai_ghep_service` tính lúc đọc): số tờ tốt = `max_i(ceil(lsx.so_luong_dat / so_con_tren_to))` · sản lượng dự kiến/dư mỗi thành viên · tổng tờ cấp = số tờ tốt + hao hụt · hạn in muộn nhất = `min(han_hoan_thanh_sx)` · % tờ dùng (fill).

**Keys & indexes**

- Primary key: `id`. Unique: `ma`. Indexes: `giay_id`, `may_id`.

**Relationships**

- Một `bai_ghep` có nhiều `bai_ghep_thanh_vien` (cascade delete). Các FK danh mục (`giay_id`, `may_id`) là MỀM.

**Tất cả cột:** `id`, `ma`, `trang_thai`, `giay_id`, `kho_in_dai`, `kho_in_rong`, `may_id`, `hao_hut_setup`, `hao_hut_chay`, `ghi_chu`, `created_by`, `created_at`, `updated_at`.

---

### `bai_ghep_thanh_vien`

**Purpose:** 1 LSX tham gia 1 bài ghép (gang member). 1 dòng = 1 LSX trong 1 bài. Neo `lsx_id` (FK THẬT), KHÔNG neo công đoạn (sửa routing LSX làm `lsx_cong_doan.id` tái sinh).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto | Surrogate PK. |
| `bai_ghep_id` | `Integer` | FK→`bai_ghep.id` (CASCADE), IX | no | — | Bài ghép chứa thành viên. |
| `lsx_id` | `Integer` | FK→`lsx.id` (RESTRICT), IX | no | — | LSX thành viên — RESTRICT chặn xoá LSX đang ghép ở tầng DB. |
| `so_con_tren_to` | `Integer` | — | no | `1` | Số con/tờ của LSX trong bài (ups). INPUT người sửa, mặc định `lsx.so_con`. |
| `buoc_in_step_key` | `String(40)` | — | yes | — | **DEPRECATED** → thay bằng `bai_ghep_cong_doan` + `bai_ghep_cong_doan_map`. Giả định "bước in là điểm gộp DUY NHẤT" — sai thực tế (còn CTP/cán/bế chung) và không diễn tả nổi nhiều bước gộp. Giữ cột để không vỡ dữ liệu cũ; code mới NGỪNG ĐỌC. Gỡ ở đợt dọn riêng. |

**Keys & indexes**

- Primary key: `id`. Foreign keys: `bai_ghep_id` FK→`bai_ghep.id` (on delete CASCADE), `lsx_id` FK→`lsx.id` (on delete RESTRICT). Unique: `(bai_ghep_id, lsx_id)` = `uq_bai_ghep_lsx` (chống thêm trùng LSX trong cùng bài). Indexes: `bai_ghep_id`, `lsx_id`.

**Relationships**

- Nhiều `bai_ghep_thanh_vien` thuộc một `bai_ghep`; mỗi thành viên trỏ một `lsx`. Guard "1 LSX ≤ 1 bài ghép" ở service (`NOT EXISTS`).

**Tất cả cột:** `id`, `bai_ghep_id`, `lsx_id`, `so_con_tren_to`, `buoc_in_step_key`.

---

### `bai_ghep_cong_doan`

**Purpose:** 1 công đoạn chạy CHUNG của bài ghép — lớp **GHI ĐÈ** lên bước tương ứng của từng LSX thành viên. Ghép bài không chỉ chung mỗi bước in: cùng tờ ghép thì bộ kẽm là một (CTP chung), cán màng cán cả tờ, bế chung nếu cùng dao. NGƯỜI khai (chọn các bước **cùng công đoạn** ở nhiều lệnh rồi gộp), máy không tự đoán. Mirror các trường *kế hoạch* của `lsx_cong_doan`; **CỐ Ý bỏ 6 cột thực-tế-giao-nhận** (`nguoi_giao_id`, `giao_luc`, `sl_giao_thuc`, `nguoi_nhan_id`, `nhan_luc`, `sl_nhan_thuc`) vì ghi nhận hàng đi/về là việc của pha thực thi. Bảng mới → `create_all` tự tạo (không migration).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto | Surrogate PK. |
| `step_key` | `String(36)` | U, IX | no | `uuid4()` | Neo bền của bước chung (giống `lsx_cong_doan.step_key`) — API gộp/tách/lập-KH tham chiếu bằng key này, không bằng `id`. |
| `bai_ghep_id` | `Integer` | FK→`bai_ghep.id` (CASCADE), IX | no | — | Bài ghép sở hữu bước chung. |
| `thu_tu` | `Integer` | — | no | `0` | Thứ tự hiển thị trong bài. Thứ tự CHẠY suy từ cạnh phụ thuộc (dẫn xuất), không lấy từ đây. |
| `cong_doan_id` | `Integer` | IX | yes | — | Soft → `cong_doan.id`. Điều kiện gộp = các bước **cùng** `cong_doan_id`. |
| `ten` | `String(255)` | — | no | `""` | Tên bước (snapshot từ bước gốc). |
| `nhom` | `String(12)` | — | yes | — | Nhóm công đoạn (snapshot) — `truoc_in` / `in` / `sau_in`… |
| `loai_buoc` | `String(12)` | — | no | `may` | `may` / `thu_cong` / `thue_ngoai` — cùng bộ giá trị `lsx_cong_doan.loai_buoc`. |
| `bat_buoc` | `Boolean` | — | no | `true` | Bước bắt buộc (snapshot). |
| `department_id` | `Integer` | IX | yes | — | Soft → `departments.id`. Một lượt chạy chung = MỘT tổ. NULL = chưa lập kế hoạch (thẻ hiện chip ⚠️). |
| `may_id` | `Integer` | IX | yes | — | Soft → `may_thiet_bi.id`. Một lượt chạy chung = MỘT máy. |
| `so_nhan_cong` | `Integer` | — | no | `1` | Số người kế hoạch cho lượt chung. |
| `so_nhan_cong_tieu_chuan` | `Integer` | — | no | `1` | Định biên chuẩn (snapshot danh mục) — mốc so sánh. |
| `so_nhan_cong_toi_da` | `Integer` | — | yes | — | Trần người của công đoạn (snapshot danh mục). |
| `khoan_json` | `JSON` | — | yes | — | Công việc khoán của bước chung — cùng hình dạng `lsx_cong_doan.khoan_json`. |
| `so_luong_vao` | `Numeric(14,2)` | — | no | `0` | Số lượng vào, tính ở **đơn vị tờ ghép** cho cả lượt (không phải phần của một lệnh). |
| `so_luong_ra` | `Numeric(14,2)` | — | no | `0` | Số lượng ra của cả lượt. Toả về từng lệnh theo `bai_ghep_thanh_vien.so_con_tren_to`. |
| `don_vi_vao` | `String(24)` | — | yes | — | Đơn vị vào (mã trong `don_vi_do`). `gop()` chép thẳng đơn vị của bước mẫu xuống đây nên mg `0186` phải nới CẢ bảng này, không thì mã dài >12 là gộp bài nổ trên Postgres. |
| `don_vi_ra` | `String(24)` | — | yes | — | Đơn vị ra. |
| `he_so_quy_doi` | `Numeric(12,4)` | — | no | `1` | Hệ số vào→ra (vd 1 tờ → 4 con). |
| `hao_hut` | `Numeric(14,2)` | — | no | `0` | Tờ hao **cố định** (canh máy) — đếm **ĐÚNG MỘT LẦN** cho cả lượt chung. Đây chính là chỗ sửa lỗi mỗi lệnh tự cộng một bộ hao cho cùng một lần lên máy. |
| `hao_hut_pct` | `Numeric(6,2)` | — | no | `0` | % hao theo độ dài lượt. Tách đôi với `hao_hut` vì hai thứ áp khác nhau (kiểu BC). |
| `so_luot_chay` | `Integer` | — | no | `1` | Số lượt chạy (vd in 2 mặt trở tự). |
| `setup_phut` | `Numeric(10,2)` | — | no | `0` | Phút canh máy — một lần cho lượt chung. |
| `nang_suat` | `Numeric(12,2)` | — | yes | — | Năng suất (theo `don_vi_nang_suat`). |
| `don_vi_nang_suat` | `String(32)` | — | yes | — | Như `lsx_cong_doan.don_vi_nang_suat` (mg 0159 nới 10→32). |
| `chay_phut` | `Numeric(10,2)` | — | yes | — | Phút chạy suy từ `so_luong_vao` + năng suất; NULL = chưa đủ dữ liệu. |
| `ve_sinh_phut` | `Numeric(10,2)` | — | no | `0` | **DORMANT 2026-08-04** — mirror `lsx_cong_doan.ve_sinh_phut`, cùng lý do: rửa mực gỡ khỏi hệ, cột giữ nguyên nhưng không đọc/ghi nữa. |
| `phat_sinh_phut` | `Numeric(10,2)` | — | no | `0` | "Thời gian khác" — mirror `lsx_cong_doan.phat_sinh_phut` (migration `0153`). |
| `cho_phut` | `Numeric(10,2)` | — | no | `0` | 🔴 GỠ KHỎI MODEL 13/08/2026 — cột còn trong DB, không code nào đọc. |
| `di_chuyen_phut` | `Numeric(10,2)` | — | no | `0` | Phút di chuyển giữa tổ/máy. |
| `nha_cung_cap` | `String(150)` | — | yes | — | Bước chung thuê ngoài → cả bài đi **một** phiếu, **một** NCC (bước chung nằm TRƯỚC điểm toả nên giao/nhận đều ở tầng bài). |
| `sl_gui` | `Numeric(14,2)` | — | yes | — | Số lượng gửi đi (DỰ KIẾN). |
| `ngay_gui_dk` | `Date` | — | yes | — | Ngày gửi dự kiến. |
| `van_chuyen_ngay` | `Numeric(6,2)` | — | yes | — | Số ngày vận chuyển (2 chiều). |
| `gia_cong_ngay` | `Numeric(6,2)` | — | yes | — | Số ngày gia công tại NCC. |
| `ngay_nhan_dk` | `Date` | — | yes | — | Ngày nhận dự kiến. |
| `hao_hut_cho_phep` | `Numeric(14,2)` | — | yes | — | Hao hụt cho phép thoả thuận với NCC. |
| `don_gia_gia_cong` | `Numeric(18,2)` | — | yes | — | Đơn giá gia công ngoài. |
| `yeu_cau_ky_thuat` | `Text` | — | yes | — | Yêu cầu kỹ thuật gửi NCC. |
| `ghi_chu` | `String(500)` | — | yes | — | Ghi chú của BÀI. Ghi chú kỹ thuật của từng lệnh **KHÔNG bị đè** — service gom lại kèm mã lệnh, vì thợ chạy chung một lượt phải đọc được yêu cầu của mọi khách trên tờ đó. |
| `created_at` | `DateTime(timezone=True)` | — | no | now | |
| `updated_at` | `DateTime(timezone=True)` | — | no | now/onupdate | |

> **Derived, KHÔNG lưu cột:** cạnh phụ thuộc của bài (đồ thị co: thay mỗi bước đã gộp bằng dòng chung của nó rồi khử trùng — khai ở hai nơi là hai nguồn sự thật) · điểm toả · dư tờ mỗi nhánh · phần giấy chia về từng lệnh (chia **theo con**).

**Keys & indexes**

- Primary key: `id`. Foreign keys: `bai_ghep_id` FK→`bai_ghep.id` (on delete CASCADE). Unique: `step_key`. Indexes: `step_key`, `bai_ghep_id`, `cong_doan_id`, `department_id`, `may_id`.

**Relationships**

- Một `bai_ghep` có nhiều `bai_ghep_cong_doan`. Mỗi dòng có nhiều `bai_ghep_cong_doan_map` (đè lên bước nào của lệnh nào) và nhiều `bai_ghep_cong_doan_vat_tu` — cả hai cascade delete.
- **GHI ĐÈ, KHÔNG PHÁ GỐC:** bước của LSX vẫn còn nguyên trong `lsx_cong_doan` với số của nó; tách gộp là số cũ quay lại, không phải khôi phục từ đâu. Engine chỉ việc "chỗ nào bị đè thì lấy số của bài".

**Tất cả cột:** `id`, `step_key`, `bai_ghep_id`, `thu_tu`, `cong_doan_id`, `ten`, `nhom`, `loai_buoc`, `bat_buoc`, `department_id`, `may_id`, `so_nhan_cong`, `so_nhan_cong_tieu_chuan`, `so_nhan_cong_toi_da`, `so_nhan_cong_toi_thieu`, `so_nhan_cong_toi_thieu`, `khoan_json`, `so_luong_vao`, `so_luong_ra`, `don_vi_vao`, `don_vi_ra`, `he_so_quy_doi`, `hao_hut`, `hao_hut_pct`, `so_luot_chay`, `setup_phut`, `nang_suat`, `don_vi_nang_suat`, `chay_phut`, `ve_sinh_phut`, `phat_sinh_phut`, `cho_phut`, `di_chuyen_phut`, `nha_cung_cap`, `sl_gui`, `ngay_gui_dk`, `van_chuyen_ngay`, `gia_cong_ngay`, `ngay_nhan_dk`, `hao_hut_cho_phep`, `don_gia_gia_cong`, `yeu_cau_ky_thuat`, `ghi_chu`, `created_at`, `updated_at`.

---

### `bai_ghep_cong_doan_map`

**Purpose:** Dòng chung này ĐÈ lên bước nào của lệnh nào. 1 dòng = 1 bước LSX bị một bước chung phủ. Neo bằng `lsx_step_key` chứ KHÔNG bằng `lsx_cong_doan.id`: sửa routing của lệnh là replace-all → `id` tái sinh, neo theo id sẽ mất dấu (cùng bài học đã khiến `bai_ghep_thanh_vien` neo vào `lsx_id`).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto | Surrogate PK. |
| `bai_ghep_cong_doan_id` | `Integer` | FK→`bai_ghep_cong_doan.id` (CASCADE), IX | no | — | Bước chung đang đè. |
| `lsx_id` | `Integer` | IX | no | — | Soft → `lsx.id` — lệnh có bước bị đè (soft vì đã có FK THẬT ở `bai_ghep_thanh_vien.lsx_id`). |
| `lsx_step_key` | `String(36)` | U, IX | no | — | Soft → `lsx_cong_doan.step_key` — bước bị đè. UNIQUE toàn bảng: một bước của lệnh chỉ được đè bởi **ĐÚNG MỘT** dòng chung. |

**Keys & indexes**

- Primary key: `id`. Foreign keys: `bai_ghep_cong_doan_id` FK→`bai_ghep_cong_doan.id` (on delete CASCADE). Unique: `lsx_step_key` = `uq_bgcd_map_lsx_step`. Indexes: `bai_ghep_cong_doan_id`, `lsx_id`, `lsx_step_key`.

**Relationships**

- Nhiều `bai_ghep_cong_doan_map` thuộc một `bai_ghep_cong_doan`. Tách gộp = xoá dòng chung → map biến theo (CASCADE) → bước LSX hết bị đè, số riêng của nó hiện lại.

**Tất cả cột:** `id`, `bai_ghep_cong_doan_id`, `lsx_id`, `lsx_step_key`.

---

### `bai_ghep_cong_doan_vat_tu`

**Purpose:** Vật tư của bước chung — mực, kẽm, màng… dùng cho **cả lượt**, không của riêng lệnh nào. Mirror ĐÚNG hình dạng `lsx_cong_doan_vat_tu` (kể cả kiểu snapshot) để drawer dùng lại không phải rẽ nhánh.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto | Surrogate PK. |
| `bai_ghep_cong_doan_id` | `Integer` | FK→`bai_ghep_cong_doan.id` (CASCADE), IX | no | — | Bước chung tiêu thụ vật tư. |
| `vat_tu_id` | `Integer` | IX | no | — | Soft → `vat_tu_in_an.id`. |
| `vat_tu_ma_snapshot` | `String(30)` | — | no | — | Mã vật tư chốt lúc lập kế hoạch (đổi danh mục không làm đổi kế hoạch cũ). |
| `vat_tu_ten_snapshot` | `String(150)` | — | no | — | Tên vật tư chốt lúc lập kế hoạch. |
| `don_vi_snapshot` | `String(16)` | — | no | — | Đơn vị chốt lúc lập kế hoạch. |
| `so_luong` | `Numeric(14,3)` | — | no | — | Định mức cho cả lượt chung. |
| `thu_tu` | `Integer` | — | no | `0` | Thứ tự hiển thị. |

**Keys & indexes**

- Primary key: `id`. Foreign keys: `bai_ghep_cong_doan_id` FK→`bai_ghep_cong_doan.id` (on delete CASCADE). Indexes: `bai_ghep_cong_doan_id`, `vat_tu_id`.

**Relationships**

- Nhiều `bai_ghep_cong_doan_vat_tu` thuộc một `bai_ghep_cong_doan` (cascade delete, `order_by` `thu_tu`). FK danh mục `vat_tu_id` là MỀM — snapshot mã/tên/đơn vị chịu trách nhiệm hiển thị.

**Tất cả cột:** `id`, `bai_ghep_cong_doan_id`, `vat_tu_id`, `vat_tu_ma_snapshot`, `vat_tu_ten_snapshot`, `don_vi_snapshot`, `so_luong`, `thu_tu`.

---

### `xep_lich_cong_doan`

**Purpose:** 1 dòng kế hoạch xếp lịch cho 1 công đoạn (operation của lệnh) HOẶC 1 lần in chung của bài ghép. Chỉ lưu QUYẾT ĐỊNH của người (máy/tổ/NCC · ca · giờ · trạng thái · khóa); số dẫn xuất tính lúc đọc. Bảng mới → `create_all` tự tạo (không migration).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto | Surrogate PK. |
| `nguon` | `String(12)` | — | no | `lsx` | `lsx` (công đoạn 1 lệnh) / `in_ghep` (in chung bài ghép). |
| `lsx_id` | `Integer` | FK→`lsx.id` (CASCADE), IX | yes | — | Lệnh chứa dòng; NULL khi `in_ghep`. |
| `lsx_cong_doan_id` | `Integer` | IX | yes | — | Soft → `lsx_cong_doan.id` (neo CHÍNH; id ổn định nhờ khóa routing khi đã lập KH). NULL khi `in_ghep`. |
| `bai_ghep_id` | `Integer` | FK→`bai_ghep.id` (CASCADE), IX | yes | — | Bài ghép của dòng chạy chung; NULL khi `lsx`. |
| `bai_ghep_cong_doan_id` | `Integer` | IX | yes | — | Soft → `bai_ghep_cong_doan.id` — dòng này là bước CHẠY CHUNG nào. Bài gộp nhiều công đoạn (CTP·in·cán·bế) nên MỖI bước chung là MỘT dòng; thiếu neo này thì gộp 3 bước mà chỉ đẻ 1 dòng, 2 bước kia bốc hơi khỏi board. NULL = dòng cũ trước migration `0151` (chạy nhánh thời lượng theo máy của bài). |
| `source_thu_tu` | `Integer` | — | no | `0` | Snapshot `lsx_cong_doan.thu_tu` — sắp chuỗi + suy bước trước/sau. |
| `loai_buoc` | `String(12)` | — | no | `may` | Snapshot loại bước (`may`/`to`/`thue_ngoai`). |
| `may_id` | `Integer` | IX | yes | — | Soft → `may_thiet_bi.id` — máy được gán. |
| `department_id` | `Integer` | IX | yes | — | Soft → `departments.id` — tổ (bước `to`/`kcs`). |
| `nha_cung_cap` | `String(150)` | — | yes | — | NCC khi thuê ngoài — text tự do (như `lsx_cong_doan.nha_cung_cap`). |
| `work_shift_id` | `Integer` | IX | yes | — | Soft → `work_shifts.id` — ca. |
| `start_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Giờ bắt đầu kế hoạch (intraday, giờ nhà máy). |
| `finish_at` | `DateTime(timezone=True)` | — | yes | — | Giờ kết thúc = `start_at` + chiếm máy (cộng theo giờ làm). Nguồn query xung đột máy. |
| `trang_thai` | `String(16)` | — | no | `cho_xep` | `cho_xep` / `da_xep`. "Đã khóa"/"Có xung đột" là hiển thị DẪN XUẤT (từ `is_locked` + cờ xung đột). |
| `is_locked` | `Boolean` → `BOOLEAN` | — | no | `false` | Ghim/khóa dòng (freeze — thao tác hàng loạt bỏ qua). |
| `blocked_reason` | `String(200)` | — | yes | — | Mã lý do chưa xếp được (`thieu_may` / `thieu_thoi_luong` / `cho_tien_de`). |
| `ghi_chu` | `String(500)` | — | yes | — | |
| `created_by` | `Integer` | — | yes | — | Soft → `users.id`. |
| `created_at` | `DateTime(timezone=True)` | — | no | now | |
| `updated_at` | `DateTime(timezone=True)` | — | no | now/onupdate | |

> **Derived, KHÔNG lưu cột** (service `xep_lich_service` tính lúc đọc): thời lượng (`chiem_may_phut`/`tong_phut` = `thoi_luong_buoc`) · sớm-nhất/muộn-nhất (forward/backward theo giờ làm) · độ dư + nhãn nguy cơ (`an_toan`/`sap_toi_han`/`nguy_co_tre`/`da_tre`/`chua_co_han`) · cờ xung đột máy (so khoảng `[start_at, finish_at)` cùng máy).

**Keys & indexes**

- Primary key: `id`. Foreign keys: `lsx_id` FK→`lsx.id` (on delete CASCADE), `bai_ghep_id` FK→`bai_ghep.id` (on delete CASCADE). Indexes: `lsx_id`, `lsx_cong_doan_id`, `bai_ghep_id`, `may_id`, `department_id`, `work_shift_id`, tổ hợp `ix_xep_lich_may_thoigian` (`may_id`, `start_at`).

**Relationships**

- Neo `lsx_cong_doan_id` là SOFT (không FK) — an toàn vì routing bị khóa khi lệnh `da_lap_ke_hoach`. Cấu trúc (`lsx_id`/`bai_ghep_id`) là FK THẬT + CASCADE (lớp chặn cuối DB); vòng đời "gỡ kế hoạch" xóa dòng TRƯỚC khi mở lại routing nên không mồ côi.

**Tất cả cột:** `id`, `nguon`, `lsx_id`, `lsx_cong_doan_id`, `bai_ghep_id`, `bai_ghep_cong_doan_id`, `source_thu_tu`, `loai_buoc`, `may_id`, `department_id`, `nha_cung_cap`, `work_shift_id`, `start_at`, `finish_at`, `trang_thai`, `is_locked`, `blocked_reason`, `ghi_chu`, `created_by`, `created_at`, `updated_at`.

---

### `machine_unavailable_periods`

**Purpose:** vùng máy KHÔNG khả dụng (Gantt theo máy, lát 2) — khoảng THỜI GIAN 1 máy bị khóa (bảo trì/hỏng/nghỉ riêng/khóa tay). Xếp lịch đọc để engine NÉ khi cộng giờ + tìm khe trống, và Gantt vẽ vùng khóa trên lane. Tách khỏi `may_thiet_bi.trang_thai` (cờ hiện tại) và cột `ngay_bao_tri_*` (mức ngày). Bảng MỚI → `create_all` tự tạo, KHÔNG migration.

| Column             | Type (SQLAlchemy → SQLite / Postgres)                 | Key    | Null | Default        | Meaning                                                                    |
| ------------------ | ----------------------------------------------------- | ------ | ---- | -------------- | -------------------------------------------------------------------------- |
| `id`               | `Integer` → `INTEGER` / `SERIAL`                      | **PK** | no   | auto-increment | Surrogate primary key.                                                     |
| `may_id`           | `Integer` → `INTEGER`                                 | **IX** | no   | —              | Soft → `may_thiet_bi.id` (không FK cứng) — máy bị khóa.                    |
| `kieu`             | `String(8)` → `VARCHAR(8)`                            | —      | no   | `chan`         | **Dấu của khoảng** (mg 0179). `chan` = máy KHÔNG chạy (nghĩa cũ, mọi hàng cũ giữ nguyên). `mo_them` = máy CHẠY THÊM ngoài ca ("tối thứ Tư máy in 2 chạy thêm 3 tiếng"). Cố ý KHÔNG đẻ bảng thứ hai cho vùng mở thêm: hai bảng là hai nơi phải nhớ khi vẽ Gantt và khi cộng giờ, quên một nơi thì lịch lệch mà không ai báo. Gantt vẽ hai kiểu KHÁC MÀU. |
| `reason`           | `String(16)` → `VARCHAR(16)`                          | —      | no   | `bao_tri`      | `bao_tri` / `hong_hoc` / `nghi` / `khac`.                                  |
| `unavailable_from` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ`| —      | no   | —              | Đầu khoảng khóa (giờ nhà máy).                                             |
| `unavailable_to`   | `DateTime(timezone=True)`                             | —      | no   | —              | Cuối khoảng khóa. Validate `from < to`.                                    |
| `note`             | `String(500)` → `VARCHAR(500)`                        | —      | yes  | —              | Ghi chú.                                                                   |
| `created_by`       | `Integer` → `INTEGER`                                 | —      | yes  | —              | Soft → `users.id`.                                                         |
| `created_at`       | `DateTime(timezone=True)`                             | —      | no   | now (UTC)      | Khi tạo.                                                                   |
| `updated_at`       | `DateTime(timezone=True)`                             | —      | no   | now/onupdate   | Lần cập nhật.                                                              |

**Keys & indexes**

- Primary key: `id`. Index: `may_id`; tổ hợp `ix_may_khoa_may_time` (`may_id`, `unavailable_from`). FK máy MỀM theo convention.

---

### `xep_lich_van_de`

**Purpose:** phần CON NGƯỜI XỬ LÝ của 1 vấn đề kế hoạch (xung đột / nguy cơ trễ). Bản thân vấn đề là DẪN XUẤT (service `xep_lich_van_de_service.liet_ke()` tính lúc đọc từ lịch — bám BC Planning Worksheet, KHÔNG lưu). Bảng chỉ neo tiếp nhận/giao/ghi chú/ngoại lệ theo `issue_key` (vân tay ổn định). Lịch sử chuyển trạng thái dùng `audit_log`. Bảng mới → `create_all` tự tạo (không migration).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto | Surrogate PK. |
| `issue_key` | `String(120)` | **U**, IX | no | — | Vân tay vấn đề dẫn xuất (vd `trung_may:{may_id}:{a}:{b}`). 1 vấn đề ↔ 1 dòng state. |
| `trang_thai` | `String(16)` | — | no | `tiep_nhan` | Vòng đời: `moi`(không có dòng)/`tiep_nhan`/`dang_xu_ly`/`da_xu_ly`/`ngoai_le`/`tam_hoan`. |
| `assigned_to` | `Integer` | — | yes | — | Soft → `users.id` — người xử lý. |
| `note` | `String(500)` | — | yes | — | Ghi chú xử lý. |
| `exception_ly_do` | `Text` | — | yes | — | Lý do khi chấp nhận ngoại lệ. |
| `exception_by` | `Integer` | — | yes | — | Soft → `users.id` — người duyệt ngoại lệ (`can_approve`). |
| `exception_expires_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Thời hạn ngoại lệ. |
| `tai_phat` | `Integer` | — | no | `0` | Số lần vấn đề tái phát (tự hết hiệu lực rồi khớp lại `issue_key`). |
| `resolved_at` | `DateTime(timezone=True)` | — | yes | — | Khi đánh dấu đã xử lý. |
| `created_by` | `Integer` | — | yes | — | Soft → `users.id`. |
| `created_at` | `DateTime(timezone=True)` | — | no | now (UTC) | Lần đầu có người chạm vào vấn đề. |
| `updated_at` | `DateTime(timezone=True)` | — | no | now/onupdate | |

**Keys & indexes**

- Primary key: `id`. Unique index: `issue_key` (1 vấn đề dẫn xuất ↔ 1 dòng state). FK user MỀM theo convention.

**Relationships**

- Không FK cấu trúc. `issue_key` liên kết logic tới các đối tượng lịch (`xep_lich_cong_doan` / `lsx` / `may_thiet_bi`) qua vân tay, nhưng vấn đề tính lúc đọc nên không neo FK cứng.

**Tất cả cột:** `id`, `issue_key`, `trang_thai`, `assigned_to`, `note`, `exception_ly_do`, `exception_by`, `exception_expires_at`, `tai_phat`, `resolved_at`, `created_by`, `created_at`, `updated_at`.

---

## Nhân sự & Lương — bậc tay nghề · danh mục khoản · lịch sử ca

### `job_grades`

**Purpose:** danh mục BẬC TAY NGHỀ (Bậc 1…Bậc 5). 1 dòng = 1 bậc.

> 🚫 **KHAI BẬC THÔI — KHÔNG tiền, KHÔNG hệ số** (chủ 2026-07-29). Gán bậc cho một người
> KHÔNG làm đổi một đồng nào trên bảng lương; có test chốt việc đó. Khi nào cần chia sản
> lượng khoán theo bậc thì treo thêm cột vào ĐÂY, không phải đi sửa hồ sơ từng người —
> đó là lý do bậc là một BẢNG có id, không phải ô chữ.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `code` | `String(20)` → `VARCHAR(20)` | **U**, **IX** | no | — | Mã ổn định: `bac_1`…`bac_5`. Bộ `pay_grade_key` CŨ (`tho_*`/`phu_*`) được migration 0127 ánh xạ sang đây khi backfill, nên hồ sơ khai bằng mã cũ vẫn về đúng bậc. |
| `name` | `String(60)` → `VARCHAR(60)` | — | no | — | Tên bậc hiển thị. |
| `seq` | `Integer` → `INTEGER` | — | no | `0` | Thứ tự hiển thị. Số NHỎ = bậc CAO (Bậc 1 đứng đầu) — theo cách chủ liệt kê. |
| `is_active` | `Boolean` → `BOOLEAN` | — | no | `true` | Tắt thay vì xoá khi một bậc thôi dùng: hồ sơ cũ đang trỏ vào vẫn đọc được tên bậc. |
| `note` | `String(255)` → `VARCHAR(255)` | — | yes | — | Ghi chú tự do. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo bậc. |

**Keys & indexes**

- Primary key: `id`. Unique index trên `code`.

**Relationships**

- `employees.job_grade_id FK→job_grades.id` — nguồn sự thật duy nhất về bậc của một người.

**Tất cả cột:** `id`, `code`, `name`, `seq`, `is_active`, `note`, `created_at`.

---

### `employee_shift_change_logs`

**Purpose:** nhật ký ĐỔI CA của nhân viên — 1 dòng = 1 lần ca bị đổi, kèm trước/sau và ai đổi.

> Luật xuyên suốt: **trước == sau thì KHÔNG ghi.** Lưới phân ca hay được bấm Lưu cả tháng
> một lần; không lọc thì mỗi lần lưu đẻ vài chục dòng rỗng + ngần ấy thông báo rác, chuông
> mất giá trị sau đúng một ngày. `create_employee` CỐ Ý KHÔNG ghi (chốt chủ 28/07/2026):
> gán ca lần đầu chưa có ca cũ nào để so.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `employee_id` | `Integer` → `INTEGER` | **FK→employees.id** (CASCADE), **IX** | no | — | Nhân viên bị đổi ca. |
| `kind` | `String(8)` → `VARCHAR(8)` | — | no | — | `day` = đổi NGÀY CÔNG cụ thể · `base` = đổi mốc CA NỀN. |
| `origin` | `String(16)` → `VARCHAR(16)` | — | no | — | Đường ghi nào tạo ra dòng này (lưới phân ca, panel ca nền, gán hàng loạt, sửa hồ sơ…). |
| `action` | `String(8)` → `VARCHAR(8)` | — | no | — | Hành động (đặt / gỡ / đổi). |
| `apply_date` | `Date` → `DATE` | **IX** | no | — | `kind=day` → ngày công bị đổi. `kind=base` → `effective_from` của mốc: ca áp từ ngày này TRỞ VỀ SAU, không riêng ngày đó. |
| `shift_id_before` | `Integer` → `INTEGER` | — | yes | — | Ca TRƯỚC. Liên kết logic → `work_shifts.id`, KHÔNG FK cứng (giống 2 bảng ca kia). NULL = không có ca. |
| `shift_id_after` | `Integer` → `INTEGER` | — | yes | — | Ca SAU. Cùng quy ước với cột trên. |
| `is_off_before` | `Boolean` → `BOOLEAN` | — | no | `false` | Ô "Nghỉ theo lịch" TRƯỚC. Chỉ có nghĩa với `kind=day`. |
| `is_off_after` | `Boolean` → `BOOLEAN` | — | no | `false` | Ô "Nghỉ theo lịch" SAU. Chỉ có nghĩa với `kind=day`. |
| `inherited_before` | `Boolean` → `BOOLEAN` | — | no | `false` | `kind=day`: TRƯỚC đó ô đang KẾ THỪA ca nền (chưa ai khai tay ngày này). Đây là chỗ trả lời "ca này do nền hay do người sửa" mà giao diện cần để hiện icon cây bút. |
| `actor_user_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | yes | — | Ai thực hiện việc đổi. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | **IX** | no | now (UTC) | Thời điểm đổi. |
| `notified_user_id` | `Integer` → `INTEGER` | **IX** | yes | — | Tài khoản ĐÃ đẩy thông báo tới. NULL = NV không có tài khoản đăng nhập (công nhân xưởng) ⇒ không báo được cho ai; màn khai ca đếm số này ra dòng "N người chưa báo được". |
| `seen_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Người nhận đã đọc lúc nào. NULL = chưa đọc ⇒ nuôi badge. |

**Keys & indexes**

- Primary key: `id`. Indexes: `employee_id`, `apply_date`, `created_at`, `actor_user_id`, `notified_user_id`.
- Foreign keys: `employee_id FK→employees.id` (ON DELETE CASCADE), `actor_user_id FK→users.id`.

**Relationships**

- Nhiều dòng log thuộc một `employees`. `shift_id_before`/`shift_id_after`/`notified_user_id` là liên kết MỀM (không FK cấu trúc).

**Tất cả cột:** `id`, `employee_id`, `kind`, `origin`, `action`, `apply_date`, `shift_id_before`, `shift_id_after`, `is_off_before`, `is_off_after`, `inherited_before`, `actor_user_id`, `created_at`, `notified_user_id`, `seen_at`.

---

### `payroll_components`

**Purpose:** danh mục KHOẢN thu nhập / khấu trừ của lương. 1 dòng = 1 khoản (Tầng 1).

> Trước đây mọi phụ cấp bị gộp vào `employee_salaries.allowance` nên engine thuế chỉ miễn
> được tăng ca + ca đêm, mọi phụ cấp khác **bị tính thuế oan**. Tách thành danh mục để
> `is_taxable` khai được tới từng khoản.
>
> ⛔ **XOÁ:** khoản đã dùng ở kỳ lương nào rồi thì KHÔNG xoá cứng, chỉ `is_active = false`.
> Xoá cứng là phiếu lương kỳ cũ mất dòng, tổng không còn khớp chữ ký người nhận.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `code` | `String(40)` → `VARCHAR(40)` | **U**, **IX** | no | — | Mã ổn định của khoản; `payroll_line_components.code` chép lại giá trị này khi tính. |
| `name` | `String(120)` → `VARCHAR(120)` | — | no | — | Tên khoản hiển thị trên phiếu lương. |
| `kind` | `String(8)` → `VARCHAR(8)` | — | no | `thu` | `thu` = thu nhập (cộng) · `tru` = khấu trừ (trừ). |
| `is_taxable` | `Boolean` → `BOOLEAN` | — | no | `true` | ⭐ Ô tích "Chịu thuế" của chủ: `true` = cộng vào thu nhập chịu thuế TNCN; `false` = miễn. Đổi cờ chỉ ảnh hưởng kỳ tính TỪ ĐÓ VỀ SAU (kỳ cũ đã snapshot). |
| `in_insurance_base` | `Boolean` → `BOOLEAN` | — | no | `false` | Có cộng vào GỐC ĐÓNG BẢO HIỂM không. Mặc định KHÔNG — gốc đóng BH là `luong_vi_tri` (chủ chốt 2026-07-20), phụ cấp không đụng vào. |
| `sort_order` | `Integer` → `INTEGER` | — | no | `0` | Thứ tự hiển thị trong danh mục và trên phiếu lương. |
| `is_active` | `Boolean` → `BOOLEAN` | — | no | `true` | Tắt thay cho xoá (xem cảnh báo trên). |
| `note` | `String(255)` → `VARCHAR(255)` | — | yes | — | Ghi chú tự do. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo khoản. |

**Keys & indexes**

- Primary key: `id`. Unique index trên `code`.

**Relationships**

- Được `employee_salary_components.component_id` (mức cố định của từng người) và
  `payroll_line_components.component_id` (snapshot trên dòng lương) tham chiếu.

**Tất cả cột:** `id`, `code`, `name`, `kind`, `is_taxable`, `in_insurance_base`, `sort_order`, `is_active`, `note`, `created_at`.

---

### `employee_salary_components`

**Purpose:** khoản thu nhập/khấu trừ **CỐ ĐỊNH HÀNG THÁNG** của một người (Tầng 2). 1 dòng = 1 (người × khoản).

> Cố ý KHÔNG version theo `effective_from` như `employee_salaries`: kỳ lương đã chốt vốn đã
> đóng băng ở `payroll_lines`, nên sửa mức hôm nay không đụng được số cũ; thêm một trục
> version nữa chỉ tạo chỗ để lệch.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `employee_id` | `Integer` → `INTEGER` | **FK→employees.id** (CASCADE), **IX** | no | — | Người hưởng/bị trừ khoản này. |
| `component_id` | `Integer` → `INTEGER` | **FK→payroll_components.id** (CASCADE), **IX** | no | — | Khoản trong danh mục. |
| `amount` | `Numeric(14,2)` → `NUMERIC(14,2)` | — | no | `0` | Số tiền cố định mỗi tháng. |
| `note` | `String(255)` → `VARCHAR(255)` | — | yes | — | Ghi chú tự do — cho khoản "mở" như "Thu nhập khác (chịu thuế)" lưu vết vì sao có khoản này (vd "Phụ cấp tiếng Nhật theo dự án X"). Chép sang snapshot dòng lương khi tính. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi gán khoản cho người này. |

**Keys & indexes**

- Primary key: `id`. Unique constraint `uq_employee_component` trên (`employee_id`, `component_id`) — mỗi người mỗi khoản đúng 1 dòng.
- Foreign keys: `employee_id FK→employees.id` (CASCADE), `component_id FK→payroll_components.id` (CASCADE).

**Relationships**

- Bảng nối nhiều-nhiều giữa `employees` và `payroll_components`, có mang giá trị `amount`.

**Tất cả cột:** `id`, `employee_id`, `component_id`, `amount`, `note`, `created_at`.

---

### `payroll_line_components`

**Purpose:** **SNAPSHOT** từng khoản trên MỘT dòng lương (Tầng 3) — phiếu lương hiện được từng khoản, và kỳ đã chốt giữ nguyên số cũ.

> Chép cả `code`/`name`/`kind`/`is_taxable` tại thời điểm tính, KHÔNG chỉ trỏ
> `component_id`: sau này chủ đổi tên khoản hay bỏ tích "Chịu thuế" thì phiếu lương các kỳ
> CŨ vẫn in ra đúng y như lúc trả tiền.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `line_id` | `Integer` → `INTEGER` | **FK→payroll_lines.id** (CASCADE), **IX** | no | — | Dòng lương chứa khoản này. |
| `component_id` | `Integer` → `INTEGER` | **IX** | no | — | **Soft-ref** tới `payroll_components.id` — KHÔNG FK cứng: khoản có thể bị xoá khỏi danh mục sau này, snapshot vẫn đứng vững nhờ 4 cột chép bên dưới. |
| `code` | `String(40)` → `VARCHAR(40)` | — | no | — | Bản chép `payroll_components.code` lúc tính. |
| `name` | `String(120)` → `VARCHAR(120)` | — | no | — | Bản chép tên khoản lúc tính. |
| `kind` | `String(8)` → `VARCHAR(8)` | — | no | — | Bản chép `thu`/`tru` lúc tính. |
| `is_taxable` | `Boolean` → `BOOLEAN` | — | no | `true` | Bản chép cờ chịu thuế lúc tính — lý do đổi cờ chỉ ảnh hưởng kỳ từ đó về sau. |
| `amount` | `Numeric(14,2)` → `NUMERIC(14,2)` | — | no | `0` | Số tiền của khoản trên dòng lương này. |
| `source` | `String(8)` → `VARCHAR(8)` | — | no | `employee` | **NGUỒN của dòng — quyết định số phận khi bấm "Tính lại".** `employee` = chép từ hồ sơ NV ⇒ bị GHI ĐÈ mỗi lần tính lại (đúng, vì hồ sơ là nguồn thật). `line` = HCNS thêm tay cho RIÊNG kỳ này (thưởng nóng) ⇒ PHẢI GIỮ NGUYÊN qua mọi lần tính lại và KHÔNG lặp sang kỳ sau. Không có cột này thì "Tính lại" xoá sạch thưởng nóng — mất tiền, không báo lỗi. Thêm qua migration 0121. |
| `note` | `String(255)` → `VARCHAR(255)` | — | yes | — | Ghi chú chép từ `employee_salary_components.note` hoặc HCNS gõ khi thêm tay. |

**Keys & indexes**

- Primary key: `id`. Unique constraint `uq_line_component` trên (`line_id`, `component_id`).
- Foreign keys: `line_id FK→payroll_lines.id` (CASCADE). `component_id` là soft-ref, KHÔNG FK.

**Relationships**

- Nhiều snapshot khoản thuộc một `payroll_lines`. Tổng các dòng `kind=thu` trừ `kind=tru` phải khớp số trên phiếu lương.

**Tất cả cột:** `id`, `line_id`, `component_id`, `code`, `name`, `kind`, `is_taxable`, `amount`, `source`, `note`.

---

### `piece_leader_bonus_brackets`

**Purpose:** mốc thưởng/phạt tổ trưởng theo **% HÀNG LỖI** của tổ. 1 dòng = 1 bậc.

> ⚠️ **ENGINE CHƯA ÁP BẢNG NÀY.** Tiền thưởng/phạt tính trên TỔNG TIỀN KHOÁN của tổ, mà
> tổng khoán hiện **luôn = 0**: `PieceWorkService.khoan_map` đọc từ `self.outputs`, nhưng
> `ProductionOutputRepository` KHÔNG TỒN TẠI trong code và `deps.py` truyền `outputs=None`.
> Khai mốc ở đây là chuẩn bị sẵn; nối vào lương cùng lúc dựng lại nguồn sản lượng. Màn khai
> có banner nói thẳng điều này — đừng gỡ.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `department_id` | `Integer` → `INTEGER` | **IX** | no | — | Tổ sở hữu bộ mốc. **Soft-ref** `departments.id` (không FK cứng, giống `piece_rates`). |
| `seq` | `Integer` → `INTEGER` | — | no | — | Thứ tự bậc 1..N. |
| `up_to_defect_pct` | `Numeric(6,2)` → `NUMERIC(6,2)` | — | yes | — | Trần % hàng lỗi của bậc. NULL = bậc cao nhất (∞) — đúng MỘT bậc và phải ở cuối. |
| `rate_pct` | `Numeric(6,2)` → `NUMERIC(6,2)` | — | no | — | % trên TỔNG TIỀN KHOÁN của tổ. **DƯƠNG = thưởng · ÂM = phạt.** Gõ nhầm dấu là đảo ngược ý nghĩa. |
| `note` | `String(255)` → `VARCHAR(255)` | — | yes | — | Ghi chú tự do. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi khai mốc. |

**Keys & indexes**

- Primary key: `id`. Index trên `department_id`. Không FK cấu trúc.

**Relationships**

- Nhiều mốc thuộc một tổ (`departments`, liên kết mềm). Cùng họ với `piece_rates`.

**Tất cả cột:** `id`, `department_id`, `seq`, `up_to_defect_pct`, `rate_pct`, `note`, `created_at`.

---

### `piece_leader_bonus_settings`

**Purpose:** NGƯỠNG sản lượng tối thiểu để xét thưởng/phạt tổ trưởng — mỗi tổ MỘT dòng.

> Vì sao tách khỏi `piece_leader_bonus_brackets`: bảng bậc chỉ có một chiều là % hàng lỗi, nên
> tổ làm 20 tờ và tổ làm 20.000 tờ bị đối xử như nhau — hỏng 2/20 tờ đã là 10%, rơi thẳng bậc
> phạt nặng nhất. Ngưỡng là MỘT luật cho cả bộ bậc, nhét vào từng bậc thì mỗi dòng mang một bản
> sao và sớm muộn lệch nhau.
>
> Luật: sản lượng `<` ngưỡng ⇒ KHÔNG thưởng KHÔNG phạt · `>=` ngưỡng ⇒ áp bảng bậc · ngưỡng `0`
> ⇒ không gác · **chưa biết sản lượng (None) ⇒ coi như DƯỚI ngưỡng** (fail-closed, có chủ ý).
>
> ⚠️ Cùng số phận với bảng bậc: **CHƯA RA TIỀN** — chưa nguồn nào báo sản lượng nên mọi tổ đều
> rơi vào nhánh fail-closed.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `department_id` | `Integer` → `INTEGER` | **UQ·IX** | no | — | Tổ được gác ngưỡng. **Soft-ref** `departments.id` (không FK cứng, giống bảng bậc). UNIQUE: hai dòng cùng tổ thì không ai biết dòng nào có hiệu lực. |
| `min_output_qty` | `Numeric(14,2)` → `NUMERIC(14,2)` | — | no | `0` | Sản lượng tối thiểu trong kỳ. **Số trần, KHÔNG kèm đơn vị** — người nối nguồn sản lượng phải cộng TOÀN BỘ sản lượng của tổ rồi so, không lọc theo đơn vị. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi khai ngưỡng. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC), `onupdate` | Lần sửa cuối. |

**Keys & indexes**

- Primary key: `id`. UNIQUE + index trên `department_id`. Không FK cấu trúc.

**Relationships**

- Một tổ (`departments`, liên kết mềm) ↔ đúng một ngưỡng. Đi kèm `piece_leader_bonus_brackets`.

**Tất cả cột:** `id`, `department_id`, `min_output_qty`, `created_at`, `updated_at`.

---

## Nội quy công ty — tài liệu · bản ban hành · trang · file

> **Append-only, KHÔNG sửa đè.** Nội quy là căn cứ kỷ luật: sửa đè thì sau này không trả lời được
> *"hồi tháng 5 luật là gì"* — mà lúc cần câu trả lời đó thường là lúc đang tranh chấp. Mỗi lần
> ban hành là một dòng `noi_quy_versions` mới, bản cũ lùi thành lịch sử.
>
> **Nháp vs Ban hành:** `draft` chỉ người soạn thấy; `published` cả công ty đọc. Bản hiệu lực của
> một tài liệu = `published` có `published_at` mới nhất TRONG tài liệu đó.
>
> **Một bản khai đúng MỘT nguồn** (`source_kind`): `html` gõ trong app, hay `file` tải tài liệu
> lên rồi dựng ảnh từng trang. Để cả hai cùng sống trên một bản thì sớm muộn chúng lệch nhau và
> không ai biết bản nào đang là luật.
>
> 4 bảng đều MỚI ⇒ `create_all` tự tạo, KHÔNG cần migration; nhưng phải export ở `models/__init__.py`.

---

### `noi_quy_documents`

**Purpose:** MỘT tài liệu trong bộ nội quy (Nội quy lao động · Quy chế lương thưởng · An toàn lao
động…) — danh tính bền, sống qua mọi lần ban hành. Mỗi tài liệu là một CHUỖI VERSION riêng.

> ⚠️ **KHÔNG có đường xoá tài liệu.** `noi_quy_pages` và `noi_quy_attachments` đều `ondelete=CASCADE`
> theo version ⇒ xoá một tài liệu là bay toàn bộ lịch sử + ảnh trang + file bằng một cú bấm. Thôi
> dùng thì đặt `is_active=False`, bản cũ vẫn tra được.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `title` | `String(200)` → `VARCHAR(200)` | — | no | — | Tên HIỆN HÀNH, dùng hiện danh sách. Tiêu đề từng bản đã ban hành chụp riêng ở `noi_quy_versions.title`. |
| `seq` | `Integer` → `INTEGER` | — | no | `1` | Thứ tự hiện trong danh sách. |
| `is_active` | `Boolean` → `BOOLEAN` | — | no | `true` | False = thôi áp dụng: mất khỏi danh sách nhân viên, KHÔNG mất khỏi lịch sử. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo tài liệu. |

**Keys & indexes**

- Primary key: `id`.

**Relationships**

- 1 tài liệu → nhiều `noi_quy_versions` (qua `document_id`, FK TRƠN không cascade).

**Tất cả cột:** `id`, `title`, `seq`, `is_active`, `created_at`.

---

### `noi_quy_versions`

**Purpose:** một BẢN của một tài liệu nội quy. Bản hiệu lực = `published` có `published_at` mới
nhất trong cùng `document_id`.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `document_id` | `Integer` → `INTEGER` | **FK·IX** | yes | — | → `noi_quy_documents.id`. **FK trơn, CỐ Ý không cascade**: xoá lạc một tài liệu thì phải NỔ, không được âm thầm kéo theo cả lịch sử ban hành. |
| `title` | `String(200)` → `VARCHAR(200)` | — | yes | — | BẢN CHỤP tiêu đề lúc ban hành. Không đọc thẳng từ `noi_quy_documents.title` vì đổi tên tài liệu sẽ viết lại tiêu đề của MỌI bản lịch sử. |
| `noi_dung` | `Text` → `TEXT` | — | no | `""` | **HTML đã lọc allowlist ở server** (`lam_sach_html`, nh3) — không phải văn bản thuần. `<img src>` chỉ được trỏ `/api/files/`. Bản `source_kind='file'` để trống, nội dung nằm ở `noi_quy_pages`. |
| `source_kind` | `String(8)` → `VARCHAR(8)` | — | no | `html` | Nguồn của bản này: `html` (gõ trong app) \| `file` (tải tài liệu lên). |
| `ghi_chu` | `String(255)` → `VARCHAR(255)` | — | yes | — | "Bản này sửa gì" — để người đọc lịch sử khỏi so từng chữ. |
| `status` | `String(12)` → `VARCHAR(12)` | **IX** | no | `draft` | `draft` \| `published`. |
| `published_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | **IX** | yes | — | Chỉ có giá trị khi đã ban hành. NULL ⇒ vẫn là nháp, nhân viên KHÔNG thấy. |
| `published_by` | `Integer` → `INTEGER` | **FK** | yes | — | → `users.id`. Ai bấm ban hành. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo bản nháp. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC), `onupdate` | Lần sửa cuối. |

**Keys & indexes**

- Primary key: `id`. FK `document_id` → `noi_quy_documents.id` (không cascade), `published_by` →
  `users.id`. Index trên `document_id`, `status`, `published_at`.

**Relationships**

- Thuộc một `noi_quy_documents`. 1 bản → nhiều `noi_quy_pages` và `noi_quy_attachments` (cascade).

**Tất cả cột:** `id`, `document_id`, `title`, `noi_dung`, `source_kind`, `ghi_chu`, `status`,
`published_at`, `published_by`, `created_at`, `updated_at`.

---

### `noi_quy_attachments`

**Purpose:** file đính kèm của MỘT bản nội quy (bản scan có ký/đóng dấu). Gắn vào version chứ
không phải toàn cục — bản PDF có dấu là của đúng bản đó.

> ⚠️ Bytes nằm ở kho file chung (`app/storage.py`), thư mục **`noi-quy/`**. Thư mục này CỐ Ý không
> khai trong `_PREFIX_PERMISSION` của `routers/files.py` ⇒ ai đăng nhập cũng tải được, giống
> `avatars/`. Thêm vào bảng đó là chỉ Giám đốc mở được file, phá đúng yêu cầu "tất cả nhân viên
> thấy". Có test canh.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `version_id` | `Integer` → `INTEGER` | **FK·IX** | no | — | → `noi_quy_versions.id`, `ondelete=CASCADE`. |
| `file_name` | `String(255)` → `VARCHAR(255)` | — | no | — | Tên file gốc lúc tải lên. |
| `file_url` | `String(500)` → `VARCHAR(500)` | — | no | — | Đường dẫn `/api/files/...` trong kho file. |
| `file_type` | `String(100)` → `VARCHAR(100)` | — | yes | — | MIME type. |
| `is_import_source` | `Boolean` → `BOOLEAN` | — | no | `false` | True = file GỐC của lần nhập nội dung, hệ thống tự đính; nhập lại thì hàng này bị THAY chứ không cộng dồn (3 file gần giống nhau thì lúc tranh chấp không ai biết bản thật). File người dùng tự đính = False, không bao giờ bị thay. |
| `uploaded_by` | `Integer` → `INTEGER` | **FK** | yes | — | → `users.id`. |
| `uploaded_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tải lên. |

**Keys & indexes**

- Primary key: `id`. FK `version_id` → `noi_quy_versions.id` (CASCADE), `uploaded_by` → `users.id`.
  Index trên `version_id`.

**Relationships**

- Nhiều file thuộc một `noi_quy_versions`; xoá bản là xoá theo.

**Tất cả cột:** `id`, `version_id`, `file_name`, `file_url`, `file_type`, `is_import_source`,
`uploaded_by`, `uploaded_at`.

---

### `noi_quy_pages`

**Purpose:** MỘT trang của bản nội quy dạng PDF, đã dựng thành ảnh.

> **Vì sao dựng ảnh thay vì tách chữ:** PDF không lưu đoạn văn hay kiểu chữ, chỉ lưu vị trí từng
> chữ — tách ra là mất sạch dáng. Yêu cầu là "giữ nguyên form chữ dáng chữ", nên cách đúng là hiện
> chính trang đó; kèm lợi ích lớn là bản SCAN đã ký/đóng dấu đỏ cũng dùng được, không cần OCR.
>
> Dựng MỘT LẦN lúc ban hành, không dựng lúc đọc — dựng khi đọc thì mỗi nhân viên mở màn là server
> giải mã lại cả tập PDF.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `version_id` | `Integer` → `INTEGER` | **FK·IX** | no | — | → `noi_quy_versions.id`, `ondelete=CASCADE`. |
| `page_no` | `Integer` → `INTEGER` | — | no | — | Số trang, đếm từ 1. |
| `file_url` | `String(500)` → `VARCHAR(500)` | — | no | — | Ảnh trang trong kho file (`noi-quy/`). |
| `width` | `Integer` → `INTEGER` | — | no | `0` | Bề rộng ảnh thật (px) — FE đặt sẵn lên `<img>` để trang KHÔNG nhảy khi ảnh tải lười xong. |
| `height` | `Integer` → `INTEGER` | — | no | `0` | Chiều cao ảnh thật (px), cùng lý do. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi dựng ảnh. |

**Keys & indexes**

- Primary key: `id`. FK `version_id` → `noi_quy_versions.id` (CASCADE). Index trên `version_id`.

**Relationships**

- Nhiều trang thuộc một `noi_quy_versions`; xoá bản là xoá theo.

**Tất cả cột:** `id`, `version_id`, `page_no`, `file_url`, `width`, `height`, `created_at`.

---

## Kho — đề nghị · phiếu · lô · ngưỡng

> Hai luật xương sống lấy từ BRD Module Kho:
>
> - **Kho KHÔNG duyệt.** Duyệt là việc của tổ trưởng/quản lý bộ phận ĐỀ NGHỊ. Kho chỉ lập
>   phiếu nhập/xuất ứng theo đề nghị đã duyệt.
> - **Đã duyệt là khoá.** Phiếu đã duyệt không sửa trực tiếp; muốn đổi thì hủy và tạo lại.
>
> Và một luật về tồn: **mỗi lần nhập = MỘT lô riêng, id riêng, giá riêng.** Không gộp lô kể
> cả trùng mã hàng, trùng giá — gộp là mất tính đích danh, mà BRD chốt phương pháp giá xuất
> là ĐÍCH DANH theo lô nhập. Hệ quả: **tồn của một mã hàng = tổng `sl_con_lai` của các lô**,
> không có cột "tồn" nào lưu rời, nên tồn không bao giờ lệch với lịch sử nhập/xuất.

### `stock_requests`

**Purpose:** header ĐỀ NGHỊ kho (nhập / xuất). 1 dòng = 1 chứng từ do người NGOÀI kho lập (tổ SX, mua hàng, bảo trì…).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `ma` | `String(30)` → `VARCHAR(30)` | **U**, **IX** | no | — | Số đề nghị in trên chứng từ (`DNN0001` / `DNX0001`) — sinh qua `document_sequences`. |
| `loai` | `String(8)` → `VARCHAR(8)` | **IX** | no | — | `NHAP` / `XUAT`. Có CHECK constraint. |
| `nguoi_tao_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | no | — | Người lập đề nghị. |
| `bo_phan_id` | `Integer` → `INTEGER` | **FK→departments.id**, **IX** | yes | — | Bộ phận đề nghị — dùng cho scope `department` và cho ô "Bộ phận" trên bản in. |
| `kho_id` | `Integer` → `INTEGER` | **FK→kho_hang.id**, **IX** | yes | — | Kho đích: XUẤT = lĩnh từ kho nào, NHẬP = nhập về kho nào. Đèn tồn tính theo kho này; phiếu kế thừa kho này (khoá). Nullable ở DB cho hàng cũ, nhưng API create BẮT BUỘC. |
| `ngay_can` | `Date` → `DATE` | — | yes | — | Ngày cần hàng. |
| `uu_tien` | `String(12)` → `VARCHAR(12)` | — | no | `binh_thuong` | `binh_thuong` / `gap`. |
| `ghi_chu` | `String(1000)` → `VARCHAR(1000)` | — | yes | — | Đặc thù nghiệp vụ (nhập mua / xuất cấp bù / xuất bảo trì…) ghi ở đây — giai đoạn 1 chưa tách loại phiếu riêng nên đây là chỗ DUY NHẤT giữ ngữ cảnh. |
| `loai_kho` | `String(50)` → `VARCHAR(50)` | — | yes | — | Loại nhập/xuất kho — TỰ DO người tạo gõ ở form yêu cầu (tên hoặc mã, vd "nhập mua" / "2"); Báo cáo kho kế toán đọc để xuất Excel MISA. NULL = chưa khai. Thêm `0169` (INT) → đổi VARCHAR ở `0170`. |
| `purchase_delivery_id` | `Integer` → `INTEGER` | **IX** | yes | — | NGUỒN: đợt giao đơn mua (`purchase_deliveries.id`) sinh ra yêu cầu NHẬP này (bấm "Nhập kho" ở đợt giao). **Soft ref** (không FK — module Mua hàng có thể migrate sau). Dùng CHẶN nhập kho TRÙNG một đợt: đợt đã có yêu cầu (chưa hủy) trỏ vào thì nút đổi "Đã nhập kho". Thêm qua migration `0189`. |
| `purchase_delivery_id` | `Integer` → `INTEGER` | **IX** | yes | — | NGUỒN: đợt giao đơn mua (`purchase_deliveries.id`) sinh ra yêu cầu NHẬP này (bấm "Nhập kho" ở đợt giao). Soft ref (KHÔNG FK — module Mua hàng migrate độc lập). Dùng CHẶN nhập kho TRÙNG một đợt: đợt đã có yêu cầu (chưa hủy) trỏ vào → nút đổi "Đã nhập kho". NULL = yêu cầu thường. Thêm qua migration `0189`. |
| `trang_thai` | `String(16)` → `VARCHAR(16)` | **IX** | no | `draft` | Vòng đời: `draft` → `pending` → `approved` → `received` → `preparing` → `partial` → `done`; nhánh `rejected` / `cancelled`. `partial`/`done` do hệ thống tự set khi phiếu ứng số lượng. Người tạo chỉ sửa/hủy được ở `draft`/`pending`; kho chỉ lập phiếu ứng ở `approved`/`received`/`preparing`/`partial`. |
| `nguoi_duyet_id` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Ai duyệt (tổ trưởng/quản lý bộ phận đề nghị — KHÔNG phải kho). |
| `duyet_luc` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Thời điểm duyệt. |
| `ly_do_tu_choi` | `String(500)` → `VARCHAR(500)` | — | yes | — | Lý do khi `rejected` — người DUYỆT từ chối. |
| `ly_do_huy` | `String(500)` → `VARCHAR(500)` | — | yes | — | Lý do KHO hủy đề nghị (hủy phiếu nháp → đề nghị KẾT THÚC ở `Đã hủy`). Tách khỏi `ly_do_tu_choi` vì là hai người và hai thời điểm khác nhau. NULL nếu chưa hủy. Thêm qua mig `0114`. |
| `quyet_dinh_xem_luc` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Người TẠO đã xem QUYẾT ĐỊNH (duyệt/từ chối/kho hủy) lúc nào — NULL = chưa xem ⇒ nuôi badge "yêu cầu của tôi vừa được quyết" (so `duyet_luc > coalesce(quyet_dinh_xem_luc, epoch)`). Mirror `decision_seen_at` báo giá. Thêm qua mig `0188`. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now/onupdate | Sửa lần cuối. |

**Keys & indexes**

- Primary key: `id`. Unique index trên `ma`. Indexes: `loai`, `trang_thai`, `nguoi_tao_id`, `bo_phan_id`, `kho_id`.
- CHECK `chk_stock_requests_loai`: `loai IN ('NHAP','XUAT')`.
- Foreign keys: `nguoi_tao_id`/`nguoi_duyet_id FK→users.id`, `bo_phan_id FK→departments.id`, `kho_id FK→kho_hang.id`.

**Relationships**

- Một đề nghị có nhiều `stock_request_lines` (cascade delete-orphan) và được nhiều `stock_vouchers` ứng vào.

**Tất cả cột:** `id`, `ma`, `loai`, `nguoi_tao_id`, `bo_phan_id`, `kho_id`, `ngay_can`, `uu_tien`, `ghi_chu`, `loai_kho`, `purchase_delivery_id`, `dieu_chuyen`, `kho_nguon_id`, `xuat_voucher_id`, `trang_thai`, `nguoi_duyet_id`, `duyet_luc`, `ly_do_tu_choi`, `ly_do_huy`, `quyet_dinh_xem_luc`, `created_at`, `updated_at`.

`dieu_chuyen`/`kho_nguon_id`/`xuat_voucher_id` (mig 0203) — ĐIỀU CHUYỂN KHO (2 yêu cầu): ấn điều chuyển sinh CẶP yêu cầu — XUẤT ở nguồn (tự lập + ghi sổ ngay, trừ tồn) và NHẬP ở đích (chờ nhận). Cả hai `dieu_chuyen=true`. Yêu cầu NHẬP đích: `kho_nguon_id` = kho nguồn (hiện "Điều chuyển từ …"); `xuat_voucher_id` = phiếu xuất nguồn đã ghi sổ (soft ref); dòng `don_gia` = giá vốn chốt từ nguồn (phiếu nhập đích khoá đơn giá). Phiếu vẫn NHAP/XUAT — không đổi CheckConstraint.

---

### `kho_khoa_so`

**Purpose:** khóa/mở sổ kỳ kế toán kho (chốt sổ) — LOG APPEND-ONLY: mỗi lần khóa/mở ghi 1 bản ghi cho KHOẢNG `[tu_ngay, den_ngay]` + phạm vi (`kho_id` NULL = toàn kho). Phiếu tại (kho, ngày) bị khóa nếu bản ghi MỚI NHẤT phủ ngày đó (toàn kho hoặc kho này) có `hanh_dong='khoa'`. Bảng vừa là hiệu lực vừa là LỊCH SỬ thao tác.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `kho_id` | `Integer` → `INTEGER` | **FK→kho_hang.id**, **IX** | yes | — | Kho bị khóa. NULL = khóa TOÀN KHO (áp cho mọi kho). |
| `tu_ngay` | `Date` → `DATE` | — | no | — | Đầu khoảng khóa/mở (bao gồm). Xét theo NGÀY CHỨNG TỪ phiếu. |
| `den_ngay` | `Date` → `DATE` | — | no | — | Cuối khoảng khóa/mở (bao gồm). |
| `hanh_dong` | `String(8)` → `VARCHAR(8)` | — | no | `khoa` | `khoa` = khóa kỳ; `mo` = mở lại. Bản ghi sau đè bản ghi trước ở các ngày giao nhau. |
| `nguoi_khoa_id` | `Integer` → `INTEGER` | **FK→users.id** | yes | — | Kế toán kho thực hiện khóa/mở kỳ. |
| `khoa_luc` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Thời điểm ghi bản ghi khóa. |
| `ten` | `String(120)` → `VARCHAR(120)` | — | yes | — | Tên kỳ (chỉ đặt khi `khoa`) — nhận diện nhanh + CHẶN TRÙNG tên với kỳ đang khóa khác. Bản ghi `mo` để trống. Thêm qua migration `0187`. |

**Keys & indexes**

- Primary key: `id`. Index trên `kho_id`.
- Foreign keys: `kho_id FK→kho_hang.id`, `nguoi_khoa_id FK→users.id`.

**Relationships**

- Bảng độc lập (không quan hệ ORM). Do `create_all` dựng; cấu trúc chốt ở migration `0170` (đổi từ 1 ngày `ngay_khoa` sang khoảng + `hanh_dong`). Thêm cùng Báo cáo kho (docs/spec-bao-cao-kho.md).

**Tất cả cột:** `id`, `kho_id`, `tu_ngay`, `den_ngay`, `hanh_dong`, `nguoi_khoa_id`, `khoa_luc`, `ten`.

### `notifications`

**Purpose:** Trung tâm thông báo (chuông Topbar). Mỗi bản ghi = 1 thông báo gửi tới MỘT người (`user_id`); hiện danh sách + đếm chưa đọc (`read_at IS NULL`). `link_loai` + `link_id` để bấm là mở đúng phiếu/yêu cầu. Cố tình GENERIC (không cột riêng cho kho) để sau nối thêm module. Bảng MỚI → `create_all` tự dựng (không cần migration).

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `user_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | no | — | Người NHẬN thông báo. |
| `loai` | `String(40)` → `VARCHAR(40)` | — | no | — | Phân loại nghiệp vụ (`kho_moi`, `kho_hoan_tat`, `kho_huy`…) — FE chọn icon/màu. |
| `tieu_de` | `String(200)` → `VARCHAR(200)` | — | no | — | Tiêu đề ngắn hiển thị. |
| `noi_dung` | `String(500)` → `VARCHAR(500)` | — | yes | — | Nội dung phụ (vd mã yêu cầu + người · phòng). |
| `link_loai` | `String(40)` → `VARCHAR(40)` | — | yes | — | Đích điều hướng: `kho_inbox` (Hộp yêu cầu/thủ kho) · `kho_mine` (màn Yêu cầu/người tạo). NULL = không nhảy. |
| `link_id` | `Integer` → `INTEGER` | — | yes | — | Id đối tượng đích (request_id). |
| `read_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Thời điểm ĐỌC (bấm vào). NULL = chưa đọc ⇒ tính vào badge chuông. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | **IX** | no | now (UTC) | Khi tạo. Sắp mới nhất trước. |

**Keys & indexes**

- Primary key: `id`. Index trên `user_id`, `created_at`.
- Foreign keys: `user_id FK→users.id`.

**Relationships**

- Bảng độc lập (không quan hệ ORM). Do `create_all` dựng.

**Tất cả cột:** `id`, `user_id`, `loai`, `tieu_de`, `noi_dung`, `link_loai`, `link_id`, `read_at`, `created_at`.

---

### `stock_request_lines`

**Purpose:** 1 dòng vật tư của đề nghị.

> Bốn con số chạy theo thứ tự `sl_de_nghi → sl_duyet → sl_da_ung`; **"còn lại" =
> `sl_duyet − sl_da_ung`, TÍNH chứ không lưu** — lưu thành cột thứ 4 là mời sai lệch.
> Service chặn cứng không cho ứng vượt `sl_duyet`.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `request_id` | `Integer` → `INTEGER` | **FK→stock_requests.id** (CASCADE), **IX** | no | — | Đề nghị chứa dòng này. |
| `hang_loai` | `String(8)` → `VARCHAR(8)` | **IX** (cặp) | no | — | Loại mặt hàng gốc: `giay` \| `vat_tu`. |
| `hang_id` | `Integer` → `INTEGER` | **IX** (cặp) | no | — | Id trong `giay_nguyen` / `vat_tu_in_an`. Soft ref (2 bảng đích nên không FK thật được). |
| `lsx_id` | `Integer` → `INTEGER` | **IX** | yes | — | **Xin cho LỆNH nào** (mg 0175) — soft ref `lsx.id`. Bảng cân đối vật tư đọc cột này để trừ phần "đã cấp" vào ĐÚNG dòng nhu cầu; thiếu nó thì kho cấp cho lệnh A mà mọi lệnh dùng chung loại giấy vẫn hiện "còn thiếu". |
| `bai_ghep_id` | `Integer` → `INTEGER` | **IX** | yes | — | Xin cho BÀI GHÉP nào (mg 0175) — soft ref `bai_ghep.id`. Cả hai cột để trống là hợp lệ (xin lặt vặt: băng dính, giẻ lau); khai cả hai cũng được nhưng service kiểm id có tồn tại, không im lặng bỏ. |
| `dvt` | `String(24)` → `VARCHAR(24)` | — | no | — | Đơn vị NGƯỜI ĐỀ NGHỊ chọn — phải nằm trong tập đổi được của mặt hàng (`quy_doi_service.don_vi_dung_duoc`). Mọi `sl_*` của dòng theo đơn vị này; quy về đơn vị gốc chỉ xảy ra lúc ghi sổ. |
| `sl_de_nghi` | `Numeric(14,2)` → `NUMERIC(14,2)` | — | no | — | Số người đề nghị xin. CHECK `> 0`. |
| `sl_duyet` | `Numeric(14,2)` → `NUMERIC(14,2)` | — | no | `0` | Số người duyệt CHO. CHECK `>= 0`. |
| `sl_da_ung` | `Numeric(14,2)` → `NUMERIC(14,2)` | — | no | `0` | Số kho ĐÃ cấp/nhập qua các phiếu. CHECK `>= 0`; service chặn vượt `sl_duyet`. |
| `don_gia` | `Integer` → `INTEGER` | — | yes | — | Đơn giá NHẬP do NGƯỜI ĐỀ NGHỊ khai (chỉ đề nghị NHẬP — họ biết giá NCC). Phiếu KẾ THỪA giá này khi ghi sổ; **kho KHÔNG sửa**. Null với đề nghị XUẤT (giá = giá vốn đích danh của lô). |
| `don_vi_phu` | `String(16)` → `VARCHAR(16)` | — | yes | — | Quy đổi đơn vị do NGƯỜI ĐỀ NGHỊ khai (1 `don_vi_phu` = `he_so_quy_doi` × dvt tồn). Hàng mới → kho tạo mã kèm quy đổi này; hàng có mã → prefill từ mặt hàng. Kho KHÔNG khai lại ở phiếu. |
| `he_so_quy_doi` | `Numeric(14,4)` → `NUMERIC(14,4)` | — | yes | — | Hệ số đi kèm `don_vi_phu`. |
| `ly_do_thieu` | `String(500)` → `VARCHAR(500)` | — | yes | — | **KHO PHẢN HỒI:** lý do kho cấp/nhập ÍT HƠN số còn phải cấp (vd NCC giao thiếu). Kho khai lúc lập phiếu khi SL < còn phải cấp; hiện ở mục "Kho phản hồi" của đề nghị. |
| `ghi_chu` | `String(500)` → `VARCHAR(500)` | — | yes | — | Ghi chú riêng của dòng. |

**Keys & indexes**

- Primary key: `id`. Indexes: `request_id`, `material_id`.
- CHECK: `sl_de_nghi > 0`, `sl_duyet >= 0`, `sl_da_ung >= 0`.
- Foreign keys: `request_id FK→stock_requests.id` (ON DELETE CASCADE), `material_id FK→materials.id`.

**Relationships**

- Nhiều dòng thuộc một `stock_requests`; được `stock_voucher_lines.request_line_id` trỏ vào để chặn ứng vượt.

**Tất cả cột:** `id`, `request_id`, `material_id`, `ten_tu_do`, `dvt`, `sl_de_nghi`, `sl_duyet`, `sl_da_ung`, `don_gia`, `don_vi_phu`, `he_so_quy_doi`, `ly_do_thieu`, `ghi_chu`.

---

### `stock_vouchers`

**Purpose:** header PHIẾU nhập / xuất kho — in ra theo mẫu 01-VT / 02-VT (TT200).

> **Mọi phiếu bắt buộc ứng theo một đề nghị đã duyệt** (`request_id` NOT NULL): mỗi nghiệp
> vụ kho đều có chứng từ đề nghị đứng trước. Ba miễn trừ của BRD (tồn đầu kỳ, điều chỉnh
> sau kiểm kê, hủy/thanh lý) đều NGOÀI phạm vi giai đoạn 1 nên chưa cần cửa thoát.
>
> Phiếu `draft` **chưa đụng tồn**; `posted` mới ghi sổ (tạo lô nếu nhập, trừ `sl_con_lai`
> nếu xuất) và cộng `sl_da_ung` về dòng đề nghị.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `ma` | `String(30)` → `VARCHAR(30)` | **U**, **IX** | no | — | Số phiếu in trên chứng từ (`PNK0001` / `PXK0001`) — sinh qua `document_sequences`. |
| `loai` | `String(8)` → `VARCHAR(8)` | **IX** | no | — | `NHAP` / `XUAT`. Có CHECK constraint. |
| `request_id` | `Integer` → `INTEGER` | **FK→stock_requests.id**, **IX** | no | — | **BẮT BUỘC** — không có đề nghị thì không có phiếu. |
| `kho_id` | `Integer` → `INTEGER` | **FK→kho_hang.id**, **IX** | no | — | Kho thao tác (kế thừa từ đề nghị, khoá). |
| `ngay` | `Date` → `DATE` | — | no | — | Ngày chứng từ. |
| `nguoi_lap_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | no | — | Người LẬP phiếu (thủ kho). |
| `nguoi_giao_nhan` | `String(150)` → `VARCHAR(150)` | — | yes | — | Ô "Họ tên người giao hàng" (01-VT) / "người nhận hàng" (02-VT) trên bản in. Text tự do vì người giao có thể là tài xế NCC — không phải user của hệ thống. |
| `ghi_chu` | `String(1000)` → `VARCHAR(1000)` | — | yes | — | Ghi chú phiếu. |
| `trang_thai` | `String(16)` → `VARCHAR(16)` | **IX** | no | `draft` | `draft` chưa ghi sổ (chưa đụng tồn) · `posted` đã ghi sổ (tồn đã đổi) · `cancelled` hủy khi còn nháp. |
| `ghi_so_luc` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | yes | — | Thời điểm ghi sổ. |
| `nguoi_ghi_so_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | yes | — | Ai GHI SỔ — người có `role_permissions.can_post` (Kế toán kho / QL kho). Null khi chưa ghi sổ. **Tách khỏi `nguoi_lap_id` theo SoD.** Thêm qua migration 0099. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now/onupdate | Sửa lần cuối. |

**Keys & indexes**

- Primary key: `id`. Unique index trên `ma`. Indexes: `loai`, `trang_thai`, `request_id`, `kho_id`, `nguoi_lap_id`, `nguoi_ghi_so_id`.
- CHECK `chk_stock_vouchers_loai`: `loai IN ('NHAP','XUAT')`.
- Foreign keys: `request_id FK→stock_requests.id`, `kho_id FK→kho_hang.id`, `nguoi_lap_id`/`nguoi_ghi_so_id FK→users.id`.

**Relationships**

- Một phiếu có nhiều `stock_voucher_lines` và nhiều `stock_voucher_attachments` (cả hai cascade delete-orphan). Phiếu NHẬP khi ghi sổ sinh ra `stock_lots`.

**Tất cả cột:** `id`, `ma`, `loai`, `request_id`, `kho_id`, `dieu_chuyen`, `ngay`, `nguoi_lap_id`, `nguoi_giao_nhan`, `ghi_chu`, `trang_thai`, `ghi_so_luc`, `nguoi_ghi_so_id`, `created_at`, `updated_at`.

`dieu_chuyen` (mig 0203) — bật cho CẢ phiếu xuất nguồn LẪN phiếu nhập đích của một điều chuyển; báo cáo kho gắn nhãn "điều chuyển" + LOẠI khỏi tổng mua/bán. Phiếu vẫn NHAP/XUAT (không đổi CheckConstraint).

---

### `stock_voucher_lines`

**Purpose:** 1 dòng phiếu = 1 lần đụng vào MỘT lô.

> Phiếu xuất ăn nhiều lô thì tách thành nhiều dòng phân bổ (10 từ lô 1 + 5 từ lô 2 = 2
> dòng), vì mỗi lô một giá vốn — gộp lại thì không truy được giá đích danh.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `voucher_id` | `Integer` → `INTEGER` | **FK→stock_vouchers.id** (CASCADE), **IX** | no | — | Phiếu chứa dòng này. |
| `request_line_id` | `Integer` → `INTEGER` | **FK→stock_request_lines.id**, **IX** | no | — | Dòng đề nghị mà dòng phiếu này ứng vào — nền cho chặn "ứng vượt SL duyệt". |
| `hang_loai` | `String(8)` → `VARCHAR(8)` | **IX** (cặp) | no | — | Mặt hàng KẾ THỪA từ dòng đề nghị (kho không đổi được). Loại: `giay` \| `vat_tu`. |
| `hang_id` | `Integer` → `INTEGER` | **IX** (cặp) | no | — | Id trong `giay_nguyen` / `vat_tu_in_an`. Soft ref (2 bảng đích nên không FK thật được). |
| `lot_id` | `Integer` → `INTEGER` | **FK→stock_lots.id**, **IX** | yes | — | Phiếu XUẤT: bắt buộc, trỏ vào lô bị trừ. Phiếu NHẬP: null lúc nháp, được gán khi ghi sổ (lúc đó lô mới được sinh ra). |
| `so_luong` | `Numeric(14,2)` → `NUMERIC(14,2)` | — | no | — | Số theo ĐƠN VỊ NGƯỜI KHAI (`stock_request_lines.dvt`) — giữ để phiếu in đúng con số họ đọc và so thẳng với `sl_duyet`. CHECK `> 0`. |
| `sl_goc` | `Numeric(14,4)` → `NUMERIC(14,4)` | — | no | — | Cùng số đó QUY VỀ ĐƠN VỊ GỐC — đây mới là số chạy vào lô/tồn (mg 0171). LƯU chứ không tính-lúc-đọc: hệ số quy đổi là dữ liệu sống, tính lại thì lô nhập 3 tháng trước tự đổi số. CHECK `> 0`. |
| `don_gia` | `BigInteger` → `BIGINT` | — | yes | — | Chỉ phiếu NHẬP: giá của lô sắp tạo, theo ĐƠN VỊ NGƯỜI KHAI (đ/ram nếu nhập theo ram). `post()` quy về đ/đơn-vị-gốc trước khi ghi vào lô. CHECK `IS NULL OR >= 0`. |
| `ghi_chu` | `String(500)` → `VARCHAR(500)` | — | yes | — | Ghi chú riêng cho DÒNG (mặt hàng) — vd tình trạng bao gói, lô hàng lỗi lẻ. Thêm qua migration 0094. |
| `vi_tri` | `String(100)` → `VARCHAR(100)` | — | yes | — | Phiếu NHẬP: vị trí cất lô trong kho (kệ/ô) — thủ kho khai; ghi sổ chép sang `stock_lots.vi_tri`. Null với XUẤT. Thêm qua migration 0115. |

**Keys & indexes**

- Primary key: `id`. Indexes: `voucher_id`, `request_line_id`, `material_id`, `lot_id`.
- CHECK: `so_luong > 0`, `don_gia IS NULL OR don_gia >= 0`.
- Foreign keys: `voucher_id FK→stock_vouchers.id` (ON DELETE CASCADE), `request_line_id FK→stock_request_lines.id`, `material_id FK→materials.id`, `lot_id FK→stock_lots.id`.

**Relationships**

- Nhiều dòng thuộc một `stock_vouchers`; mỗi dòng trỏ đúng 1 dòng đề nghị và (sau khi ghi sổ) đúng 1 lô.

**Tất cả cột:** `id`, `voucher_id`, `request_line_id`, `material_id`, `lot_id`, `so_luong`, `don_gia`, `ghi_chu`.

---

### `stock_voucher_attachments`

**Purpose:** hóa đơn / chứng từ gốc scan đính kèm phiếu nhập-xuất (hóa đơn NCC, biên bản giao nhận…).

> DB chỉ lưu **metadata + đường dẫn**, bytes nằm ngoài DB (mirror
> `payment_voucher_attachments`). Cho đính THÊM cả khi phiếu đã `posted` (hóa đơn về sau);
> chỉ chặn `cancelled`.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `stock_voucher_id` | `Integer` → `INTEGER` | **FK→stock_vouchers.id** (CASCADE), **IX** | no | — | Phiếu được đính kèm. |
| `file_name` | `String(255)` → `VARCHAR(255)` | — | no | — | Tên file gốc người dùng tải lên. |
| `file_url` | `String(500)` → `VARCHAR(500)` | — | no | — | Đường dẫn phục vụ file. |
| `file_type` | `String(100)` → `VARCHAR(100)` | — | yes | — | MIME type. |
| `uploaded_by` | `Integer` → `INTEGER` | **FK→users.id** (SET NULL) | yes | — | Ai tải lên. |
| `uploaded_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tải lên. |

**Keys & indexes**

- Primary key: `id`. Index trên `stock_voucher_id`.
- Foreign keys: `stock_voucher_id FK→stock_vouchers.id` (ON DELETE CASCADE), `uploaded_by FK→users.id` (ON DELETE SET NULL).

**Relationships**

- Nhiều file đính kèm thuộc một `stock_vouchers`.

**Tất cả cột:** `id`, `stock_voucher_id`, `file_name`, `file_url`, `file_type`, `uploaded_by`, `uploaded_at`.

---

### `stock_lots`

**Purpose:** 1 dòng = 1 LÔ nhập kho, mang GIÁ riêng của lần nhập đó.

> Ví dụ: SP A nhập đợt 1 giá 100k → lô 1; đợt 2 giá 200k → lô 2. Xuất 15 cái = 10 từ lô 1 +
> 5 từ lô 2 → giá vốn 10×100k + 5×200k.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `ma_lo` | `String(60)` → `VARCHAR(60)` | **U**, **IX** | no | — | Mã lô người dùng đọc được: `LOT-<mã hàng>-<yymmdd>-<seq>`. |
| `hang_loai` | `String(8)` → `VARCHAR(8)` | **IX** (cặp) | no | — | Loại mặt hàng gốc: `giay` \| `vat_tu`. |
| `hang_id` | `Integer` → `INTEGER` | **IX** (cặp) | no | — | Id trong `giay_nguyen` / `vat_tu_in_an`. Soft ref (2 bảng đích nên không FK thật được). |
> ⚠️ `sl_ban_dau`/`sl_con_lai`/`don_gia_nhap` của lô LUÔN theo **đơn vị gốc** của mặt hàng (`don_vi_gia`) — nhập bằng ram/thùng gì cũng quy về gốc trước khi ghi, nếu không thì `SUM(sl_con_lai)` là cộng táo với cam.

| `voucher_id` | `Integer` → `INTEGER` | **FK→stock_vouchers.id**, **IX** | yes | — | Phiếu nhập sinh ra lô. Nullable vì tồn đầu kỳ (giai đoạn sau) không có phiếu. |
| `kho_id` | `Integer` → `INTEGER` | **FK→kho_hang.id**, **IX** | no | — | Kho chứa lô. |
| `vi_tri` | `String(100)` → `VARCHAR(100)` | — | yes | — | Vị trí trong kho (kệ/ô). |
| `ngay_nhap` | `Date` → `DATE` | — | no | — | Ngày nhập lô. |
| `ncc` | `String(150)` → `VARCHAR(150)` | — | yes | — | Nhà cung cấp (text tự do). |
| `don_gia_nhap` | `BigInteger` → `BIGINT` | — | no | `0` | **Giá vốn của RIÊNG lô này** (VND/đvt). Chỉ vai có `role_permissions.can_view_cost` được xem — router ẩn trường này, kể cả trên bản in. CHECK `>= 0`. |
| `sl_ban_dau` | `Numeric(14,2)` → `NUMERIC(14,2)` | — | no | — | Số lượng lúc nhập. CHECK `> 0`. |
| `sl_con_lai` | `Numeric(14,2)` → `NUMERIC(14,2)` | — | no | — | Số còn lại của lô. CHECK `>= 0` và `<= sl_ban_dau`. **Tồn của một mã hàng = tổng cột này qua các lô.** |
| `hsd` | `Date` → `DATE` | — | yes | — | Hạn sử dụng / date in bao bì — nền cho gợi ý FEFO khi xuất. |
| `trang_thai` | `String(16)` → `VARCHAR(16)` | **IX** | no | `available` | `available` (chỉ trạng thái này tính vào TỒN KHẢ DỤNG và được chọn khi xuất) · `hold` giữ chỗ cho đơn/LSX · `qc_wait` chờ KCS · `defect` hàng lỗi · `empty` đã xuất hết. Hàng chờ KCS / lỗi vẫn nằm trong kho (tồn thực tế) nhưng không được xuất. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi tạo lô. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now/onupdate | Sửa lần cuối. |

**Keys & indexes**

- Primary key: `id`. Unique index trên `ma_lo`. Indexes: `material_id`, `voucher_id`, `kho_id`, `trang_thai`.
- CHECK: `don_gia_nhap >= 0`, `sl_ban_dau > 0`, `sl_con_lai >= 0`, `chk_stock_lots_con_lai` (`sl_con_lai <= sl_ban_dau`).
- Foreign keys: `material_id FK→materials.id`, `voucher_id FK→stock_vouchers.id`, `kho_id FK→kho_hang.id`.

**Relationships**

- Nhiều lô thuộc một `materials` và một `kho_hang`. Sinh ra từ `stock_vouchers` (phiếu nhập); bị `stock_voucher_lines.lot_id` trỏ vào khi xuất.

**Tất cả cột:** `id`, `ma_lo`, `material_id`, `voucher_id`, `kho_id`, `vi_tri`, `ngay_nhap`, `ncc`, `don_gia_nhap`, `sl_ban_dau`, `sl_con_lai`, `hsd`, `trang_thai`, `created_at`, `updated_at`.

---

### `stock_thresholds`

**Purpose:** ngưỡng tồn theo cặp (mặt hàng × kho). 1 dòng = 1 cặp. Khoá duy nhất `(hang_loai, hang_id, kho_id)` (mg 0171).

> So sánh chạy trên **TỒN KHẢ DỤNG** (chỉ lô `available`), không phải tồn thực tế: hàng chờ
> KCS / hàng lỗi nằm trong kho nhưng không dùng được nên không được tính.
>
> Đèn tín hiệu 4 mức: 🔵 `du_ton` (> ngưỡng tối đa) · 🟢 `du` · 🟠 `can_mua` (≤ ngưỡng tồn)
> · 🔴 `het` (= 0). Hai mức cuối kích hoạt đẩy nhắc realtime cho người có quyền đề nghị.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
|---|---|---|---|---|---|
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Surrogate primary key. |
| `hang_loai` | `String(8)` → `VARCHAR(8)` | **U** (cùng `kho_id`) | no | — | Loại mặt hàng gốc: `giay` \| `vat_tu`. |
| `hang_id` | `Integer` → `INTEGER` | **U** (cùng `kho_id`) | no | — | Id trong `giay_nguyen` / `vat_tu_in_an`. Soft ref (2 bảng đích nên không FK thật được). |
> Ngưỡng khai theo ĐƠN VỊ GỐC của mặt hàng — cùng thang với `stock_lots.sl_con_lai`, nếu khác thang thì so ngưỡng với tồn là so hai đơn vị khác nhau.

| `kho_id` | `Integer` → `INTEGER` | **FK→kho_hang.id** (CASCADE), **IX** | no | — | Kho áp ngưỡng. |
| `nguong_ton` | `Numeric(14,2)` → `NUMERIC(14,2)` | — | no | — | Dưới mức này = 🟠 phải mua ngay. CHECK `>= 0`. |
| `nguong_can_ton` | `Numeric(14,2)` → `NUMERIC(14,2)` | — | yes | — | ⚠️ **ĐÃ BỎ** mức "cận tồn/sắp hết" (2026-07-29). Cột giữ lại và LUÔN NULL để tránh migration phá DB; không còn dùng khi tính mức tồn. FE không khai nữa; endpoint vẫn nhận optional cho tương thích. CHECK `>= 0`. |
| `nguong_toi_da` | `Numeric(14,2)` → `NUMERIC(14,2)` | — | yes | — | Trần 🔵 — cảnh báo mua dư, hàng dễ quá date. CHECK `>= 0`. |
| `canh_bao` | `Boolean` → `BOOLEAN` | — | no | `true` | Có bật cảnh báo đẩy cho cặp này không. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now (UTC) | Khi khai ngưỡng. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now/onupdate | Sửa lần cuối. |

**Keys & indexes**

- Primary key: `id`. Unique constraint `uq_stock_thresholds_material_kho` trên (`material_id`, `kho_id`).
- CHECK: `nguong_ton >= 0`, `nguong_can_ton >= 0`, `nguong_toi_da >= 0`.
- Foreign keys: `material_id FK→materials.id` (CASCADE), `kho_id FK→kho_hang.id` (CASCADE).

**Relationships**

- Bảng nối (`materials` × `kho_hang`) mang ngưỡng. Chỉ vai có `role_permissions.can_set_threshold` mới sửa được.

**Tất cả cột:** `id`, `material_id`, `kho_id`, `nguong_ton`, `nguong_can_ton`, `nguong_toi_da`, `canh_bao`, `created_at`, `updated_at`.

---

## (LỊCH SỬ) Kế hoạch & Lệnh sản xuất — 8 bảng cũ ĐÃ DROP

> ⛔ **2026-07-23** — `lenh_sx` · `print_form` · `gang_placement` · `routing_step` ·
> `routing_step_assignment` · `san_luong` · `ban_giao` · `lenh_item` đã bị **DROP** ở migration
> `0092_drop_lenh_sx_cu` (tầng code gỡ trước đó ở commit `bcefd1c`). Module dựng lại dùng
> `lsx` / `lsx_cong_doan` ở mục trên. Migration `0079`–`0087` (ALTER các bảng cũ) vẫn ship nhưng
> tự no-op vì bảng không còn. Tài liệu mô tả 8 bảng cũ đã xoá khỏi file này để khỏi gây nhiễu.

### `module_notifications`

**Purpose:** một sự kiện nội bộ cần hiện badge ở một màn Thu mua/Kế toán; một dòng được dùng chung
cho mọi người có quyền đọc màn đó, không nhân bản theo người nhận.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Thứ tự sự kiện, đồng thời là mốc đọc ổn định. |
| `channel` | `String(32)` → `VARCHAR(32)` | **IX** | no | — | Kênh nhận: `thu_mua` hoặc `ke_toan`. |
| `event_type` | `String(64)` → `VARCHAR(64)` | — | no | — | Loại sự kiện realtime, ví dụ duyệt đơn hoặc cập nhật đợt giao. |
| `source_code` | `String(64)` → `VARCHAR(64)` | — | yes | — | Mã đơn/chứng từ nguồn để truy vết và soạn toast. |
| `actor_user_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | yes | — | Người tạo sự kiện; người này không tự nhận badge. |
| `recipient_user_id` | `Integer` → `INTEGER` | **FK→users.id**, **IX** | yes | — | Người nhận đích danh; NULL nghĩa là mọi người có quyền đọc kênh. |
| `created_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | **IX** | no | now (UTC) | Thời điểm phát sinh. |

**Keys & indexes**

- Primary key: `id`.
- Foreign keys: `actor_user_id FK→users.id` (`SET NULL`), `recipient_user_id FK→users.id` (`CASCADE`).
- Indexes: `channel`, `actor_user_id`, `recipient_user_id`, `created_at`.

**Relationships**

- Không giữ danh sách người nhận; quyền RBAC quyết định ai nhìn thấy badge của kênh.

**Tất cả cột:** `id`, `channel`, `event_type`, `source_code`, `actor_user_id`, `recipient_user_id`, `created_at`.

---

### `module_notification_reads`

**Purpose:** mốc thông báo cuối đã đọc của một người trong một kênh; một dòng cho mỗi cặp người × kênh.

| Column | Type (SQLAlchemy → SQLite / Postgres) | Key | Null | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `id` | `Integer` → `INTEGER` / `SERIAL` | **PK** | no | auto-increment | Khóa kỹ thuật. |
| `user_id` | `Integer` → `INTEGER` | **FK→users.id**, **U**, **IX** | no | — | Người đã đọc. |
| `channel` | `String(32)` → `VARCHAR(32)` | **U**, **IX** | no | — | Kênh `thu_mua` hoặc `ke_toan`. |
| `last_read_notification_id` | `Integer` → `INTEGER` | — | no | `0` | Mọi thông báo cùng kênh có id không lớn hơn mốc này đã đọc. |
| `updated_at` | `DateTime(timezone=True)` → `DATETIME` / `TIMESTAMPTZ` | — | no | now/onupdate | Lần vào màn gần nhất. |

**Keys & indexes**

- Primary key: `id`.
- Unique constraint `uq_module_notification_read_user_channel` trên (`user_id`, `channel`).
- Foreign key: `user_id FK→users.id` (`CASCADE`).

**Relationships**

- Nhiều mốc đọc thuộc một người dùng; không FK cứng tới thông báo cuối để việc dọn thông báo cũ không khóa nhau.

**Tất cả cột:** `id`, `user_id`, `channel`, `last_read_notification_id`, `updated_at`.

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
