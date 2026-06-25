# Session Handoff

Fill this at the end of a session that spans more than one sitting, so the next
session can resume from the repo alone. For quick single-session notes,
`progress.md` is enough.

## Current Sprint

- Sprint spec: `docs/product-specs/sprint-01-auth.md`
- Goal: Runnable skeleton (React+Vite+TS / FastAPI / PostgreSQL-in-Docker) + seeded-user
  JWT login reaching a protected Dashboard.
- Phase: building → evaluating (feat-003 pending browser-validate score)

## Features This Session

| feat-id | name | status | latest score (design / orig / craft / func) | notes |
|---|---|---|---|---|
| feat-001 | App skeleton + Postgres in Docker | done | n/a (infra) | init.ps1 green |
| feat-002 | Seeded-user JWT login (backend) | done | n/a (API) | 8 pytest pass |
| feat-003 | Login screen + protected Dashboard | in-progress | not yet scored | build passes; run Evaluator |

## Latest Evaluation

- Threshold met? not yet run — feat-003 still needs the browser-validate Evaluator pass
  (record scores in `docs/EVALUATION.md`).
- Weakest criterion / what to improve next: TBD after first Evaluator run.

## Decisions Made

- Login-only (seeded users), JWT bearer auth, TypeScript frontend.
- `create_all` + idempotent seed for DB bootstrap; Alembic migrations deferred.
- Tests use in-memory SQLite; Postgres is the Docker/prod target via the same SQLAlchemy layer.

## Blockers / Risks

- Frontend not yet containerized (runs via `npm run dev`).
- Dev-only secrets (`JWT_SECRET`, seed password) must be overridden in real deploys.

## How to Run

1. `docker compose up -d db backend`  (Postgres :5432 + API :8000)
2. `cd frontend; npm install; npm run dev`  (SPA :5173)
3. Sign in with `admin@example.com` / `admin123` (dev seed).
4. API check: `POST http://localhost:8000/api/auth/login` then `GET /api/auth/me`.

## Next Session Startup

1. Read `AGENTS.md`, then `docs/ORCHESTRATION.md`.
2. Run `./init.ps1` (Windows) or `./init.sh` (Unix) — must pass (currently `9 passed`).
3. Read `feature_list.json` and this handoff.

## Recommended Next Step

- Run the browser-validate Evaluator on the running app to score feat-003; on PASS mark it
  `done` in `feature_list.json` and log scores in `docs/EVALUATION.md`. Then plan sprint-02
  (self-registration / Alembic migrations / RBAC).
