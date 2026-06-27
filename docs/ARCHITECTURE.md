# ARCHITECTURE.md

> **PLACEHOLDER TEMPLATE** — the app source does not exist yet. This file is the
> contract agents follow until real code lands. Slots marked `<PLACEHOLDER>` are
> intentionally blank; fill the Domain Map and System Shape when the first feature
> is generated. Single source of truth for "is the tree healthy" stays
> `./init.sh` / `./init.ps1` (smoke tests + `compileall`) — never add a competing
> verify command.

This file is the top-level map of the system. Read it on demand when implementing
or changing a cross-cutting boundary or a hard dependency. Keep it concise. For
anything visual — layout, components, tokens, styling, UX states — defer to
[docs/UI_DESIGN.md](UI_DESIGN.md); do not duplicate visual concerns here. For the
**database schema** — tables, column meanings, keys, indexes — defer to the data
dictionary [docs/DB_SCHEMA.md](DB_SCHEMA.md) (kept in sync with the models by a test);
do not duplicate per-column detail here.

## Stack

- **Frontend:** React + Vite (SPA, **TypeScript**). Source in `frontend/`.
- **Backend:** FastAPI (Python), served via ASGI (`uvicorn app.main:app`). Source in
  `backend/app/`.
- **Database:** SQLite for local/test (`sqlite:///./dev.db`, in-memory for tests),
  **PostgreSQL for Docker/prod** (`postgres:16-alpine` via `docker-compose.yml`) —
  single SQLAlchemy layer, same queries against both. Schema bootstrap this spec is
  `create_all` + seed; Alembic migrations are a later spec.
- **Transport:** JSON over HTTP; the frontend talks to the backend only through a
  typed API client.

## System Shape

- Product: GAN App (working title)
- Primary user workflow: sign in → reach the protected app shell (Dashboard).
- Runtime surfaces: web SPA (browser, Vite :5173), HTTP API service (FastAPI :8000),
  and relational DB (PostgreSQL :5432 in Docker).
- Source of truth for product behavior: the active spec under
  [docs/product-specs/](product-specs/index.md) and its derived `feature_list.json`.

## Domain Map

| Domain | Purpose | Frontend Entry | Backend Entry | Related Spec |
|--------|---------|----------------|---------------|--------------|
| `auth` | Seeded-user login, JWT issue/verify, current-user, session restore | `frontend/src/pages/LoginPage.tsx`, `frontend/src/auth/` | `backend/app/routers/auth.py` → `services/auth_service.py` → `repositories/user_repo.py` | [`product-specs/spec-01-auth.md`](product-specs/spec-01-auth.md) |
| `rbac` | Departments, roles (per department, 1/user), permission matrix (CRUD + data scope), audit log; seeded catalog/roles. Data model + seed landed (feat-004); enforcement/screens follow. | _(screens: feat-007..011)_ | `backend/app/models/{department,role,module,audit}.py`, `repositories/{rbac_repo,audit_repo}.py`, `seed.py` | [`product-specs/spec-02-rbac.md`](product-specs/spec-02-rbac.md) |

### Backend module layout (`backend/app/`)

`main.py` (app + CORS + lifespan seed) · `config.py` (env settings) · `db.py` (engine/session/Base)
· `security.py` (bcrypt + JWT) · `deps.py` (DI: db→repo→service, current-user) ·
`models/` · `schemas/` · `repositories/` · `services/` · `routers/` · `seed.py`.

## Layer Model

Use these fixed directional models so agents do not invent ad hoc architecture.
Data and dependencies flow in one direction only.

**Frontend (React + Vite):**

`UI components -> state / hooks -> API client -> (HTTP) -> backend`

- Components render and capture input; they hold no fetch logic.
- State and hooks own local/shared state and call the API client.
- The API client is the single place that knows backend URLs, request/response
  shapes, and error mapping.

**Backend (FastAPI):**

`API routes -> services -> repositories -> DB`

- Routes parse/validate (Pydantic schemas) and shape HTTP responses only.
- Services hold business logic and orchestration; they are framework-agnostic.
- Repositories own all SQL/ORM access and are the only layer that touches the DB.
- The DB (SQLite/Postgres) is reached exclusively through repositories.

## Hard Dependency Rules

- Lower layers must not import or depend on higher layers (DB never imports a
  service; a service never imports a route; the API client never imports a
  component).
- The frontend reaches the backend **only** through the API client — components,
  hooks, and views must not call `fetch`/`axios` directly.
- The backend reaches the database **only** through repositories — routes and
  services must not run raw SQL or open sessions.
- Routes contain no business logic; services contain no HTTP or DB-driver
  specifics; repositories contain no business rules.
- SQL must remain portable across SQLite and Postgres; backend-specific dialect
  features need an explicit, justified reason.
- Cross-cutting concerns (auth, logging, config) enter through explicit
  provider/dependency boundaries (e.g. FastAPI dependencies, a React context),
  not by reaching across layers. See [docs/SECURITY.md](SECURITY.md) for auth and
  secret-handling rules.
- New dependencies should be justified in the matching spec.

## Change Checklist

When you touch architecture-relevant code:

1. Update this file if the Domain Map or an allowed boundary changed.
2. Keep the layer flow intact — if a change requires crossing a boundary, fix the
   boundary, do not bypass it.
3. Put any visual/UI decision in [docs/UI_DESIGN.md](UI_DESIGN.md), not here.
4. Add or update an executable check so the rule is enforced mechanically by
   `./init.sh` / `./init.ps1` (the single verification source of truth) — never add
   a competing verify command.
5. Confirm the change is traceable to a feature in `feature_list.json` and its
   acceptance criteria in the spec; record evaluation outcomes per
   [docs/EVALUATION.md](EVALUATION.md).
