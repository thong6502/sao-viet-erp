# Session Progress Log

## Current State

**Last Updated:** 2026-06-30
**Active Feature:** **spec-05 — Quản lý Phòng ban (feat-023..026)** — feat-023 (foundation) DONE; next
buildable = feat-024 (Tạo phòng ban, FE). spec-04 (feat-018..022) also done/code-verified.
Browser-validate via Playwright MCP not run (server not connected this session).

### spec-05 — Quản lý Phòng ban (PBI-4002/4003/4005, 2026-06-30)

- Planned feat-023..026 (spec `docs/product-specs/spec-05-departments.md`). Decisions: add `parent_id`
  + pick parent at create; code = `PB` + sequential (PB001…); delete blocks only on people (roles
  cascade) — changes feat-008 delete semantics (feat-026).
- **feat-023 DONE** (backend foundation): departments gained `code` (PB###, unique, system-generated),
  `description`, `parent_id` (self-FK tree); repo `_next_code`/`create(…desc,parent)`/`children_of`/
  `subtree`; DB_SCHEMA updated (guard passes); 6 tests. init.ps1 100 passed. Live dev.db ALTERed +
  codes backfilled PB001..PB004.
- **NEXT:** feat-024 Tạo phòng ban (FE form: code read-only, description, parent picker, inline
  duplicate-name error, list shows code) → feat-025 Sửa → feat-026 Xoá theo nhánh có chặn (also
  rewrites feat-008 delete + its tests). UI features need the Playwright browser-validate pass.

### spec-04 — User profile widget + self-service (feat-018..022, 2026-06-30)

- **Trigger:** user reported the Topbar user-menu items ("Thông tin tài khoản", "Đổi tên", "Đổi
  avatar") did nothing — they were stubs (AppShell didn't pass `onProfileAction` and no panels
  existed). Built the whole spec-04 to make the menu real.
- **feat-018** user widget: placement moved from the sidebar bottom to a top header (`Topbar.tsx`);
  avatar + name + dropdown (4 items + Đăng xuất), outside-click/Escape close, `assetUrl` for avatar.
- **feat-019** `GET /api/auth/me` enriched to `ProfileOut` (dept/role names + created_at); read-only
  InfoView. **feat-020** `PATCH /api/users/me {name}`. **feat-021** avatar upload/remove
  (`POST/DELETE /api/users/me/avatar`, `users.avatar_url`, StaticFiles `/static`, 2 MB + JPG/PNG
  guard). **feat-022** `POST /api/auth/change-password` (verify current → bump token_version +
  revoke all refresh tokens → 204 → frontend logs out to Login with a success notice).
- **Backend:** new `services/profile_service.py`, `routers/profile.py`, `schemas/profile.py`;
  `AuthService.change_password` + `PasswordChangeError`; user_repo set_name/set_avatar/set_password;
  16 new tests. **Test isolation fix:** `conftest` now drops+recreates the schema per test (the
  in-memory StaticPool DB was shared across the session, so the new mutating tests leaked state) —
  this is why the suite is now green at 94.
- **Frontend:** `ProfileDialog.tsx` (+ css), `assetUrl` + profile API methods + FormData support in
  `client.ts`, `AuthContext.updateUser`/`notice`, `.banner--success` + `--moss-soft`.
- **Live DB:** `backend/dev.db` ALTERed to add `avatar_url` (create_all does not ALTER); already has
  `username` from feat-017. Backend on :8000 runs with `--reload` and serves the new endpoints.
- **NEXT:** hard-refresh the browser (Ctrl+Shift+R) and click through the 4 menu items; run the formal
  Playwright browser-validate once that MCP server is connected. feat-017's live login journey is also
  still pending the same browser pass.

### feat-017 — Username replaces email entirely (spec-0001, in_progress 2026-06-30)

- **What changed:** **email column removed**; `users.username` (String(150), **NOT NULL**, unique,
  index) is now the sole account identity + login credential. Full replacement across the stack:
  login form / `LoginRequest` / `UserOut`; the HR **Người dùng** screen (create form, table, detail
  all use "Tên đăng nhập"); **Phòng ban** head-picker; audit detail; seed; every RBAC user shape.
  Wrong creds → generic **"Tên đăng nhập hoặc mật khẩu không đúng"** (no enumeration); duplicate
  username on create → 409. Seed admin username = `admin` (`SEED_ADMIN_USERNAME`).
- **Scope decision (per user request, evolved over the session):** first "login only", then "keep
  email too", finally **"xóa luôn cột email"** — so email is gone everywhere and username took its
  place, including the HR create-user form (it now captures username → new users can log in).
- **Verify:** `./init.ps1` → **78 passed** + compileall clean; frontend tsc + vite build green.
- **PENDING:** browser-validate of the live login + user-management journeys. Requires **dropping
  `backend/dev.db`** so `create_all` rebuilds `users` without `email` + with `username` (it does
  not ALTER), then restart the backend (re-seeds admin). Live login is now **`admin` / `admin123`**.

### spec-03 — Auth Hardening (feat-012..016, done 2026-06-27)

- **feat-012 — Production secret guard:** `config.assert_secure_config` refuses to boot when
  `APP_ENV=production` and `JWT_SECRET` is empty/default/<32 chars; called in `main.py` lifespan.
  6 tests.
- **feat-013 — Short access token + `token_version` hard-revoke:** access TTL 60→15 min; `tv`
  claim checked in `get_current_user`; `users.token_version` + `bump_token_version()`. 4 tests.
- **feat-014 — Refresh-token store + rotation:** `refresh_tokens` table (hash only) +
  `RefreshTokenService.issue/rotate/revoke`; rotation + family-revoke on replay. 8 tests.
- **feat-015 — `/refresh` + `/logout` + httpOnly cookie + CORS creds:** login sets the cookie;
  `/refresh` rotates; `/logout` revokes+clears (204, idempotent). 9 tests.
- **feat-016 — Frontend silent refresh + cookie restore + server logout:** in-memory access
  token (no localStorage), shared-promise refresh-and-retry on 401, restore via `/refresh` on
  mount, server-side logout. browser-validate PASS 4/4/5/4 (Score Log 2026-06-27).
- **Decisions:** access token in memory (not localStorage); refresh in httpOnly cookie
  (SameSite=lax, Path=/api/auth, Secure in prod); hard-revoke via `token_version`; one shared
  in-flight `/refresh` to avoid a refresh storm. `create_all` does not ALTER — drop `dev.db`
  (done this session) to pick up `token_version` + `refresh_tokens`.
- **Harness change:** the `generate` skill (+ `AGENTS.md`, `references/workflow.md`) now supports
  building a whole spec by iterating the single-feature cycle (one feature in flight at a time);
  the gan-loop orchestrator path stays one-per-pass.

Verify: `./init.ps1` → 78 passed (+27 over spec-02) + compileall; frontend tsc+vite build green.

## Status

### What's Done

- **feat-001 — App skeleton + Postgres in Docker:** monorepo `backend/` (FastAPI,
  layered routes→services→repositories→DB) + `frontend/` (React + Vite + TypeScript);
  `docker-compose.yml` runs `db` (postgres:16-alpine) + `backend`; `.env.example` at root
  and per app. `init.ps1` green.
- **feat-002 — Seeded-user JWT login (backend):** `POST /api/auth/login` (bcrypt verify →
  JWT) and `GET /api/auth/me`; seeded admin on startup; generic 401 (no user enumeration);
  ORM/bound-param SQL only. 8 backend tests pass.
- **Data dictionary:** `docs/DB_SCHEMA.md` documents every table (purpose, columns, PK/FK,
  indexes). Guard test `backend/tests/test_schema_documented.py` fails `init` if a model
  table/column is undocumented, so schema + docs can't drift. `init` now `11 passed`.

- **feat-004 — RBAC data model + seed (backend):** new tables `departments`, `roles`,
  `role_permissions`, `modules`, `audit_logs` + `users.department_id/role_id/is_active`;
  `rbac_repo` + `audit_repo`; idempotent `seed_all` (11-module catalog for Kinh doanh +
  HCNS only, 3 depts, 5 roles incl. Giám đốc all/all/all, admin linked + set as head).
  `docs/DB_SCHEMA.md` documents every new table/column (schema-doc guard passes).
- **feat-005 — Permission enforcement (backend):** `services/rbac_service.py`
  `AuthorizationService.can(user, module, action)`; `deps.require_permission(module, action)`
  (403 on missing perm); `get_current_user` rejects locked (`is_active=false`) accounts with
  403. 4 enforcement tests (allowed/missing/unauth/locked). `init.ps1`: **21 passed**.
- **feat-006 — Data-scope resolver (backend):** `rbac_service.scope_for(user, module)` +
  pure `apply_scope`/`scope_filter` narrow a query by own/department/all (ORM or Core cols).
  4 scope tests on a non-`Base` fixture table. `init.ps1`: **25 passed**.

- **feat-003 — Login screen + protected Dashboard (frontend):** Evaluator PASS 2026-06-26
  (design/orig/craft/func 4/4/5/5, overall 4) — golden journey clean & deterministic on a
  fresh RBAC-seeded backend; scores in `docs/EVALUATION.md`. Renders inside the ERP
  `AppShell` + `Sidebar`.

- **feat-007 — Vai trò (API + permission matrix screen):** backend RBAC admin routes
  (modules/departments/roles + role permission matrix) guarded by `require_permission`;
  frontend `RolesPage` matrix (CRUD + Phạm vi own/dept/all) reachable via sidebar
  Quản trị → Vai trò; `AppShell` now routes content by active nav id; `AuthContext`
  exposes `token`. Evaluator PASS 4/4/5/4. Follow-up: role **rename + delete** (PUT/DELETE
  `/api/roles/{id}`, delete blocked 409 if a user still holds the role) — browser-verified.
  `init.ps1`: **33 passed**.
- **feat-008 — Phòng ban (API + screen):** department CRUD + summaries (role/user counts,
  head) + set-head (must belong to dept) + delete blocked if roles/users remain;
  `DepartmentsPage` master-detail via sidebar Quản trị → Phòng ban. Evaluator PASS 4/4/5/4.
  `init.ps1`: **39 passed**.
- **feat-009 — Người dùng (API + screen):** HR create (email-unique, dept required) → no role
  yet; assign role validated to the user's department; lock/unlock with self-lock guard;
  `auth_service` + `get_current_user` both refuse a locked account. `UsersPage` table+detail
  via sidebar Quản trị → Người dùng. Evaluator PASS 4/4/5/4. `init.ps1`: **46 passed**.
- **feat-010 — Menu/route gating:** `GET /api/auth/permissions` (readable modules);
  Sidebar filters items by module + drops empty sections; AppShell loads perms on entry and
  gates content (forbidden → 403 banner). Verified live for admin (catalog only) and NV Sales
  (Dashboard + 3 KD items, no Quản trị). Evaluator PASS 4/4/5/4. `init.ps1`: **49 passed**.
- **feat-011 — Activity Log:** `GET /api/audit` + read-only `ActivityLogPage` (friendly
  Vietnamese action labels + filter-by-action); surfaced the full real audit history written
  across feat-004..010. Evaluator PASS 4/4/5/4. `init.ps1`: **51 passed**.

### What's In Progress

- None — **spec-02 RBAC is fully done (11/11 features)**.

### What's Next

1. Harden RBAC: live Postgres bring-up, password reset / invite email, "head assigns
   only within their level". Next spec is undecided — write a spec from `_TEMPLATE.md`
   → `/plan` → build when chosen.
2. Ops note: app runs on SQLite `backend/dev.db` (rebuilt this session). Restart the backend
   after backend route changes (uvicorn isn't hot-reloaded here); drop dev.db on schema change.

## Blockers / Risks

- Frontend is not yet a Docker service (runs via `npm run dev`); fine for dev, revisit for
  a fully-containerized deploy.
- `JWT_SECRET` and seed password are dev defaults — must be overridden via env in any real
  deployment (docs/SECURITY.md).

## Decisions Made

- Login-only this spec (users seeded, no self-registration) — per planning choice.
- Auth = JWT bearer token (localStorage), not cookie sessions.
- Frontend = TypeScript.
- DB bootstrap via `create_all` + idempotent seed; Alembic deferred to keep spec-01 small.
- Tests run on in-memory SQLite (StaticPool) so `init` stays green without Docker; Postgres
  is the Docker/prod target through the same SQLAlchemy layer.
- Pinned pydantic as a `>=2.11.5,<3` range (not exact) to avoid downgrading other tools in a
  shared global Python env.

## Files Modified This Session

- `backend/` — full FastAPI app (`app/**`), `tests/test_auth.py`, `requirements.txt`,
  `Dockerfile`, `.env.example`.
- `frontend/` — Vite+TS SPA (`src/**`, `package.json`, `tsconfig.json`, `vite.config.ts`,
  `index.html`, `.env.example`).
- `docker-compose.yml`, root `.env.example`.
- `feature_list.json`, `docs/product-specs/spec-01-auth.md`, `docs/product-specs/index.md`,
  `docs/ARCHITECTURE.md`, `pytest.ini`, `init.ps1`, `init.sh`.

## Evidence of Completion

- `init.ps1`: `9 passed` (1 template smoke + 8 auth) + `compileall` clean — 2026-06-25.
- `frontend`: `npm run build` (tsc --noEmit + vite build) succeeds, 39 modules.
- Login e2e (live, SQLite backend): `POST /api/auth/login` → JWT; `GET /api/auth/me` →
  `{id:1,email:admin@example.com,name:Admin}`; wrong password → `401 {"detail":"Invalid
  email or password"}`. Same SQLAlchemy layer runs on Postgres.

## Current Run / DB Status

- App is currently running on **SQLite** (`backend/dev.db`) so the UI is testable now:
  backend `uvicorn` :8000, frontend Vite :5173. Login: `admin@example.com` / `admin123`.
- **Postgres is fully wired but NOT live-verified yet** — the local Docker daemon got
  wedged (every container-create hangs; `docker version` responds but `docker run` /
  `docker compose up` time out, likely a stuck build/pull holding a lock). Per decision,
  we test on SQLite now and switch to Postgres once Docker is healthy.

### Switch to Postgres (when Docker daemon is healthy)

1. Restart Docker Desktop (tray → Restart) to clear the wedged daemon.
2. `docker compose up -d db`  → Postgres on :5432 (creds from root `.env`).
3. Stop the SQLite backend, then run the backend so it reads `backend/.env`
   (`DATABASE_URL=postgresql+psycopg2://app:app@localhost:5432/gan_app`):
   `cd backend; python -m uvicorn app.main:app --port 8000`  (lifespan create_all + seed
   runs against Postgres).
4. Re-test login — identical behavior, now Postgres-backed.
   (Full-Docker alternative once the backend image builds: `docker compose up -d`.)

## Notes for Next Session

- `.env` (root, for compose) and `backend/.env` (local backend → Postgres) exist and are
  gitignored. `.env.example` files are the committed templates.
- Seeded login: `admin@example.com` / `admin123` (dev defaults; do not ship).
- Backend deps are installed in the local Python env so `init.ps1` runs backend tests.
