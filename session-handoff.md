# Session Handoff

Fill this at the end of a session that spans more than one sitting, so the next
session can resume from the repo alone. For quick single-session notes,
`progress.md` is enough.

## Current Sprint

- Sprint spec: `docs/product-specs/sprint-02-rbac.md` (sprint-01 = `sprint-01-auth.md`, done).
- Goal: RBAC — Phòng ban · Vai trò (per department, 1/user) · permission matrix
  (CRUD + data scope own/department/all); HR assigns department, head assigns role,
  Admin/GĐ defines roles; menu gating + activity log.
- Phase: **COMPLETE** — feat-001..011 all `done` (11/11). Sprint-01 + Sprint-02 finished.

## Features This Session

| feat-id | name | status | score (d/o/c/f) | notes |
|---|---|---|---|---|
| feat-003 | Login + protected Dashboard | done | 4/4/5/5 | inside ERP AppShell+Sidebar |
| feat-004 | RBAC data model + seed | done | n/a (backend) | 5 tables + user cols; DB_SCHEMA guard green |
| feat-005 | Permission enforcement | done | n/a (backend) | require_permission 401/403 + locked-user |
| feat-006 | Data-scope resolver | done | n/a (backend) | own/department/all |
| feat-007 | Vai trò (matrix + rename/delete) | done | 4/4/5/5 | matrix CRUD+scope; persists |
| feat-008 | Phòng ban | done | 4/4/5/4 | summaries, head, delete-blocked |
| feat-009 | Người dùng | done | 4/4/5/4 | create+dept, assign role, lock/self-lock |
| feat-010 | Menu/route gating | done | 4/4/5/4 | sidebar + content gated by permission |
| feat-011 | Activity Log | done | 4/4/5/4 | read-only audit table + filter |

## Latest Evaluation

- All UI features PASS (every criterion ≥ 4). Full ledger in `docs/EVALUATION.md`.

## Decisions Made

- One role per user; roles defined per department; permission = CRUD + data scope.
- New HR-created accounts start with NO role (most-minimal) + a configurable initial
  password (`default_user_password`); a locked account can neither log in nor use `/me`.
- Module catalog seeded for Kinh doanh + Hành chính nhân sự only — it grows as more
  departments come online (data, not schema).
- create_all + idempotent seed; Alembic still deferred. Tests on in-memory SQLite.

## Blockers / Risks

- App still on SQLite `backend/dev.db` (Postgres wired but not live-verified).
- Dev-only secrets / initial passwords must be overridden in real deploys.
- Data-scope (own/department/all) is enforced in the resolver but has no real data-bearing
  module yet — it visibly applies once a data-bearing business module lands.

## How to Run

1. `cd backend; python -m uvicorn app.main:app --port 8000`  (API :8000, SQLite + seed)
   - On a schema change, delete `backend/dev.db` first so create_all rebuilds it.
2. `cd frontend; npm install; npm run dev`  (SPA :5173)
3. Sign in `admin@example.com` / `admin123` (seed admin = Giám đốc, all permissions).

## Next Session Startup

1. Read `AGENTS.md`, then `docs/ORCHESTRATION.md`.
2. Run `./init.ps1` (Windows) / `./init.sh` (Unix) — must pass (currently `51 passed`).
3. Read `feature_list.json` and this handoff.

## Recommended Next Step

- Next sprint is undecided. Candidate: harden RBAC (live Postgres bring-up, password reset /
  invite email, "head assigns only within their level"). Write a spec from `_TEMPLATE.md`
  → `/plan` → build once a direction is chosen.
