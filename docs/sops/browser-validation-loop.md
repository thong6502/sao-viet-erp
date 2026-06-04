# SOP: Browser UI Validation Loop (Playwright MCP)

> PLACEHOLDER TEMPLATE — this repo's product source is currently EMPTY. The launch
> command and URL below are written as `<PLACEHOLDER ...>`; fill them in when the
> project has a runnable app. The loop itself is reusable as-is.

Use this SOP when UI work depends on real runtime interaction — when screenshots,
the live DOM/accessibility tree, console output, and network behavior matter more
than code inspection alone. It retargets the classic "DevTools validation loop"
onto the **Playwright MCP** tools so the agent can drive a browser deterministically.

This is the deep procedure behind the `browser-validate` skill
(`.claude/skills/browser-validate/SKILL.md`). The skill is the thin entry point;
this file is the authoritative Execution SOP + Clean Criteria.

## When to use

- A visible behavior changed (layout, state, copy, enable/disable, error surface).
- A bug only reproduces through interaction (click/type/submit), not in a unit test.
- You are validating a golden journey before marking a feature done.

Prefer adding a fast automated test where possible; use this loop for the runtime
gap a test cannot cover. The single verification source of truth stays `./init.sh`
/ `./init.ps1` (`python -m pytest` + `python -m compileall .`) — this loop is
runtime evidence on top of green verification, never a replacement for it.

## Required inputs

- **A stable launch command + URL.**
  `<PLACEHOLDER app launch command / URL>` — e.g. start the dev server with the
  project's runner, then the journey begins at `<PLACEHOLDER URL>`. On Windows use
  the PowerShell form, on Unix the bash form (`$env:VAR` vs `$VAR`).
- **A reproducible UI journey** — the exact sequence of user actions, written down.
- **A definition of "clean"** in observable terms (see Clean Criteria).

## Playwright MCP tool map

| Loop step | Playwright MCP tool |
|-----------|---------------------|
| Open / select the page | `browser_navigate` (and `browser_tabs` to pick a tab) |
| Read console (clear noise) | `browser_console_messages` |
| Capture structural BEFORE/AFTER | `browser_snapshot` (accessibility tree) |
| Trigger one path | `browser_click`, `browser_type`, `browser_fill_form`, `browser_select_option` |
| Wait for async settle | `browser_wait_for` (text / state, not blind sleeps) |
| Observe network | `browser_network_requests` |
| Capture visual AFTER | `browser_take_screenshot` |

Prefer `browser_snapshot` over `browser_take_screenshot` for assertions: the
snapshot is a stable, diffable text tree (good for visual-regression-style
comparison). Use screenshots for human-facing evidence and pixel concerns. Avoid
`browser_run_code_unsafe` / `browser_evaluate` unless a snapshot cannot answer the
question — arbitrary page JS is higher risk and harder to reproduce.

## Core loop (one path at a time)

1. **Select the page.** `browser_navigate` to `<PLACEHOLDER URL>` (or pick the
   right tab with `browser_tabs`).
2. **Clear console noise.** Read `browser_console_messages` once to drain/record
   pre-existing messages so the AFTER read shows only what THIS path produced.
3. **Snapshot BEFORE.** `browser_snapshot` (structure) and, if pixels matter,
   `browser_take_screenshot`. This is your baseline.
4. **Trigger exactly ONE path.** One user action or one short chain
   (`browser_click` / `browser_type` / `browser_fill_form`). Never batch multiple
   unrelated journeys into one observation — you lose attribution.
5. **Wait deterministically.** `browser_wait_for` on the expected text/state.
6. **Observe runtime.** Re-read `browser_console_messages` (new errors/warnings?)
   and `browser_network_requests` (expected calls fired? status codes OK? no
   unexpected 4xx/5xx?).
7. **Snapshot AFTER.** `browser_snapshot` + `browser_take_screenshot`; compare to
   the BEFORE evidence.
8. **If it fails, fix the smallest responsible layer and restart.** Patch the
   narrowest layer (markup → component state → data/handler → service), re-launch
   the app if the change requires it, and go back to step 1 for the SAME path.
9. **Re-run until the Clean Criteria hold** on a fresh run.

## Execution SOP (detailed)

1. Write the target journey and its success conditions in the active plan /
   `progress.md` BEFORE driving the browser, so the loop has a fixed target.
2. State success in observable terms: text present, control enabled, prior error
   gone, console clean, the expected request returned 2xx.
3. Establish the baseline: launch the app, `browser_navigate`, drain console,
   snapshot BEFORE.
4. Trigger one path; wait with `browser_wait_for`, not a fixed delay.
5. Record evidence: console delta, network list, AFTER snapshot/screenshot.
6. On failure, change ONE layer, restart the app if needed, and re-run the same
   path — do not pile on additional changes before re-measuring.
7. Compare BEFORE vs AFTER each iteration; stop when Clean Criteria hold twice on
   independent runs (stability check).

## Clean Criteria

A journey is clean when ALL hold on a fresh run:

- The intended visible state is present (matches the written success condition).
- No unexpected console errors; every warning is understood or cleared.
- Network calls for the path completed with expected status codes; no surprise
  failures or duplicated requests.
- The structural snapshot matches the expected AFTER state (no missing/duplicated
  regions, no stuck loading state).
- Re-running the same path yields the same result (deterministic).

## Cross-references

- **Verify step:** this loop produces runtime evidence for the `run-feature`
  verify step (`.claude/skills/run-feature/SKILL.md`). Code verification still goes
  through `./init.sh` / `./init.ps1` first; never introduce a competing command.
- **UI states:** consult `docs/FRONTEND.md` for the canonical loading / empty /
  error / success states a journey must exercise (created by the frontend policy
  pack file).
- **Golden journeys:** when a journey is worth protecting, promote it in
  `docs/RELIABILITY.md` as a golden journey so regressions are caught deliberately.
- **Screenshot safety:** before saving or sharing any `browser_take_screenshot`
  output, redact secrets/PII per `docs/SECURITY.md` (tokens, emails, account data
  can appear on screen). Treat captured artifacts as potentially sensitive.

## Generic fallback

If the Playwright MCP browser tools are unavailable, fall back to the global
`/run` skill (launch and drive the app) or `/verify` (confirm a change works) for
a lighter, tool-agnostic check. Those are generic; this SOP is the structured,
evidence-producing loop when the Playwright MCP server is connected.

## Repo artifacts to update

- The active execution plan / `progress.md` (target journey + result).
- `docs/RELIABILITY.md` if the journey becomes a golden path.
- The product spec if the visible behavior changed.
