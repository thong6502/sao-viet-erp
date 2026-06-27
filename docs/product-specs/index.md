# Product Specs Index

One file per spec. The human Planner writes a spec here (from
`_TEMPLATE.md`); the plan skill reads these to produce `feature_list.json`.

## Active Specs

- `_TEMPLATE.md` (copy per spec) — the blank spec shape.
- [`spec-01-auth.md`](spec-01-auth.md) — Foundation & Login: app skeleton
  (React + Vite + TS / FastAPI / PostgreSQL-in-Docker) + seeded-user JWT login. **Active.**
- [`spec-02-rbac.md`](spec-02-rbac.md) — RBAC: Phòng ban · Vai trò (riêng từng phòng,
  1 vai trò/người) · phân quyền CRUD + Phạm vi dữ liệu (Của tôi/Cả phòng/Tất cả); HR gán
  phòng, trưởng phòng gán vai trò, Admin/GĐ định nghĩa khuôn vai trò. **Done** (feat-004..011,
  Evaluator PASS for each UI feature — see docs/EVALUATION.md).
- [`spec-03-auth-hardening.md`](spec-03-auth-hardening.md) — Auth hardening: short access token +
  refresh token (httpOnly cookie, rotation), `POST /api/auth/refresh` + `/logout`, server-side
  refresh-token store, `token_version` hard-revoke, and a production secret guard. **Planned**
  (feat-012..016 in `feature_list.json`; not yet built).

## Rules

- One file per spec, describing user-visible behavior and acceptance criteria.
- The plan skill reads these specs; keep this index current so a fresh
  agent (and the plan skill) can discover product scope quickly.
- If implementation diverges from the spec, update one of them in the same
  session.
- Acceptance criteria are the contract verification checks against. For UI work,
  state them as Playwright MCP browser assertions and confirm them through the
  browser validation loop (`../sops/browser-validation-loop.md`) on top of green
  `./init.sh` / `./init.ps1` — never as a replacement for it.
