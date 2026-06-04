# FRONTEND.md — Frontend & UI Validation Policy

> Tier 3 doc (load on demand). Routed from AGENTS.md `### Frontend & UI Validation`.
> Defines stable frontend expectations so agents do not invent UI patterns
> unpredictably. The runnable browser loop lives in the `browser-validate` skill
> (`.claude/skills/browser-validate/SKILL.md`) — this file is policy, that skill is
> the procedure. Do not duplicate either into the other.

> <PLACEHOLDER: project source EMPTY and Python-only; activate when a frontend exists>
> This is a reusable scaffold copied into new projects. The current project ships no
> frontend (Python-only), so every UI-specific value below is a `<PLACEHOLDER>`. These
> rules go live the first time the project grows a real UI; delete this banner once a
> frontend exists and the placeholders are filled.

## UI Principles

- Optimize for clarity before novelty.
- Keep interaction flows discoverable and restartable.
- Prefer a small number of reusable components over one-off variants.
- Accessibility checks are part of normal verification, not polish work.

## Guardrails

- **Document the design system / component library in `docs/references/`** as a
  `<topic>-llms.txt` extract (see `docs/references/README.md`), and add its Tier 3 row to
  `docs/CONTEXT-MAP.md`. Do not inline component docs here.
  - `<PLACEHOLDER: design-system / component-library reference + its docs/references/ file>`
- **Record key user-facing states for each flow** so validation has a checklist to drive:
  - [ ] **empty** — no data yet (first run, filtered to nothing)
  - [ ] **loading** — request in flight (skeleton/spinner, no layout jump)
  - [ ] **success** — data rendered as intended
  - [ ] **error** — request/validation failed with a legible message
  - [ ] **retry** — the user can recover without a full reload
- Keep copy, keyboard behavior, and visual hierarchy consistent across flows.
- When a UI bug is fixed, add or update the matching validation step (and promote a
  worthwhile path as a golden journey in `docs/RELIABILITY.md`).

## Verification Expectations

UI claims need **runtime evidence on top of green code verification** — they never
replace it. Code verification stays single-sourced at `./init.sh` (Unix/macOS/CI) /
`./init.ps1` (Windows/PowerShell), currently `python -m pytest` + `python -m compileall .`.
Do not introduce a competing verify command for UI work.

Drive the browser through the **Playwright MCP** tools (no Chrome-DevTools-CLI assumption).
The repeatable, runnable loop is the `browser-validate` skill — invoke it rather than
re-deriving the steps. The standardized shape of a check is:

1. **`browser_navigate`** to the running app (`<PLACEHOLDER: app launch command / URL>`;
   start the dev server first, PowerShell form on Windows / bash form on Unix).
2. **`browser_snapshot`** (and `browser_take_screenshot` when pixels matter) to capture a
   BEFORE baseline; drain `browser_console_messages` so the AFTER read reflects only this path.
3. **Trigger exactly ONE path** (`browser_click` / `browser_type` / `browser_fill_form`),
   then **`browser_wait_for`** the expected state — never a blind sleep.
4. **Assert against the AFTER `browser_snapshot`** (the accessibility/DOM tree is stable and
   diffable — prefer it for assertions and visual-regression checks) and re-read
   `browser_console_messages` / `browser_network_requests` for new errors or unexpected calls.
5. **Standardize DOM/screenshot checks**: assert on the snapshot tree by default; reserve
   `browser_take_screenshot` for human-facing evidence and genuine pixel regressions. If
   visual regressions are common, fix the same DOM-node/screenshot pair every run so diffs
   are comparable.

Record the browser/runtime validation steps and their evidence in the relevant plan
(`docs/PLANS.md` / `docs/exec-plans/`) or the `feature_list.json` entry — not in chat.

> **Screenshot redaction:** Playwright screenshots and snapshots can capture tokens,
> logged-in pages, URLs with secrets, or PII. Redaction rules are NOT restated here —
> follow `docs/SECURITY.md` ("Redact from Playwright screenshots too") and treat saved
> screenshots as potentially secret artifacts.

## Cross-references

- **Runnable loop / Clean Criteria:** `.claude/skills/browser-validate/SKILL.md`
  (deep Execution SOP at `docs/sops/browser-validation-loop.md`).
- **Code verification (single source of truth):** `./init.sh` / `./init.ps1`.
- **Golden journeys:** `docs/RELIABILITY.md`.
- **Design-system / component references:** `docs/references/README.md`.
- **Secret/PII redaction in captures:** `docs/SECURITY.md`.
