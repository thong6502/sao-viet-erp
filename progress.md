# Session Progress Log

## Current State

**Last Updated:** 2026-06-26
**Active Feature:** feat-008 — Phòng ban (API + screen) — **done** (Evaluator PASS). Next
buildable is **feat-009** (Người dùng screen).

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

### What's In Progress

- None.

### What's Next

1. **feat-009** (Người dùng: HR tạo+gán phòng · trưởng phòng gán vai trò · khóa tài khoản) —
   buildable now (deps feat-007/008 done). Then **feat-010** (menu gating) → **feat-011**
   (Activity Log). feat-009 also unblocks live-testing of head pickers + data-scope.
2. UI features need the app running on the RBAC schema: `backend/dev.db` was rebuilt this
   session (backend :8000, frontend :5173); drop dev.db + restart if the schema changes.
   Restart the backend after backend route changes (uvicorn doesn't hot-reload here).
3. Sprint-02 RBAC backlog is planned in `feature_list.json` (feat-004..011) and specced in
   `docs/product-specs/sprint-02-rbac.md`.

## Blockers / Risks

- Frontend is not yet a Docker service (runs via `npm run dev`); fine for dev, revisit for
  a fully-containerized deploy.
- `JWT_SECRET` and seed password are dev defaults — must be overridden via env in any real
  deployment (docs/SECURITY.md).

## Decisions Made

- Login-only this sprint (users seeded, no self-registration) — per planning choice.
- Auth = JWT bearer token (localStorage), not cookie sessions.
- Frontend = TypeScript.
- DB bootstrap via `create_all` + idempotent seed; Alembic deferred to keep sprint-01 small.
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
- `feature_list.json`, `docs/product-specs/sprint-01-auth.md`, `docs/product-specs/index.md`,
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
