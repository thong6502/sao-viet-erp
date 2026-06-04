<!-- PLACEHOLDER TEMPLATE: this repo's product source is currently EMPTY. -->
<!-- Active Specs lists only `_TEMPLATE.md` until a real flow spec is copied from it. -->

# Product Specs Index

Use this folder for current user-facing behavior specs.

## Active Specs

- `_TEMPLATE.md` (copy per flow) — <PLACEHOLDER: real flow specs land here, e.g. `new-user-onboarding.md`>

## Rules

- Specs should describe user-visible behavior and acceptance criteria.
- If implementation diverges from the spec, update one of them in the same
  session.
- Acceptance criteria are the contract verification checks against. For UI flows,
  state them as Playwright MCP browser assertions and confirm them through the
  browser validation loop (`../sops/browser-validation-loop.md`) on top of green
  `./init.sh` / `./init.ps1` — never as a replacement for it.
- Keep this index current so a fresh agent can discover product scope quickly.
