<!-- PLACEHOLDER TEMPLATE: this repo's product source is currently EMPTY. -->
<!-- Active Specs lists only `_TEMPLATE.md` until a real sprint spec is copied from it. -->

# Product Specs Index

One file per sprint. The human Planner writes a sprint spec here (from
`_TEMPLATE.md`); the plan skill reads these to produce `feature_list.json`.

## Active Specs

- `_TEMPLATE.md` (copy per sprint) — <PLACEHOLDER: real sprint specs land here, e.g. `sprint-01-onboarding.md`>

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
