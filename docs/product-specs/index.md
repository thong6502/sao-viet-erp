# Product Specs Index

One file per sprint. The human Planner writes a sprint spec here (from
`_TEMPLATE.md`); the plan skill reads these to produce `feature_list.json`.

## Active Specs

- `_TEMPLATE.md` (copy per sprint) — the blank sprint shape.
- [`sprint-01-auth.md`](sprint-01-auth.md) — Foundation & Login: app skeleton
  (React + Vite + TS / FastAPI / PostgreSQL-in-Docker) + seeded-user JWT login. **Active.**
- [`sprint-02-rbac.md`](sprint-02-rbac.md) — RBAC: Phòng ban · Vai trò (riêng từng phòng,
  1 vai trò/người) · phân quyền CRUD + Phạm vi dữ liệu (Của tôi/Cả phòng/Tất cả); HR gán
  phòng, trưởng phòng gán vai trò, Admin/GĐ định nghĩa khuôn vai trò. **Draft — chờ duyệt.**

## Rules

- One file per sprint, describing user-visible behavior and acceptance criteria.
- The plan skill reads these sprint specs; keep this index current so a fresh
  agent (and the plan skill) can discover product scope quickly.
- If implementation diverges from the spec, update one of them in the same
  session.
- Acceptance criteria are the contract verification checks against. For UI work,
  state them as Playwright MCP browser assertions and confirm them through the
  browser validation loop (`../sops/browser-validation-loop.md`) on top of green
  `./init.sh` / `./init.ps1` — never as a replacement for it.
