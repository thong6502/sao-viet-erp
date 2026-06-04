---
name: browser-validate
description: >-
  browser UI validation, snapshot, console, screenshot, visual regression, Playwright MCP,
  validate UI journey. Use to drive a real browser and verify a UI path end-to-end. Not for
  unit tests or code-only review.
license: MIT
---

# Browser UI Validation (Playwright MCP)

Run a repeatable browser interaction loop until a UI journey is **clean**: select the
page, clear console noise, snapshot BEFORE, trigger ONE path, observe console + network,
snapshot/screenshot AFTER, fix the smallest layer and restart, rerun until the Clean
Criteria hold. This is the runtime-evidence loop on top of green code verification.

The deep Execution SOP + Clean Criteria + tool map live in
[../../../docs/sops/browser-validation-loop.md](../../../docs/sops/browser-validation-loop.md).
Read it before driving the browser; this skill is the thin entry point.

## When this applies

- A visible behavior changed (layout, state, copy, enable/disable, error surface).
- A bug only reproduces through interaction, not in a unit test.
- Validating a golden journey before marking a feature done.

Not for unit tests, code-only review, or repo-wide refactors.

## Shortest reliable loop

1. **Select the page.** `browser_navigate` to `<PLACEHOLDER app launch command / URL>`
   (start the dev server first; use the PowerShell form on Windows, bash form on Unix).
2. **Clear console noise.** Read `browser_console_messages` once to drain pre-existing
   messages, so the AFTER read shows only what THIS path produced.
3. **Snapshot BEFORE.** `browser_snapshot` (structure) and `browser_take_screenshot` if
   pixels matter — this is your baseline.
4. **Trigger exactly ONE path.** `browser_click` / `browser_type` / `browser_fill_form`,
   then `browser_wait_for` the expected text/state (no blind sleeps).
5. **Observe runtime.** Re-read `browser_console_messages` (new errors?) and
   `browser_network_requests` (expected calls fired with OK status?).
6. **Snapshot/screenshot AFTER.** `browser_snapshot` + `browser_take_screenshot`; compare
   to BEFORE. Prefer the snapshot tree for assertions (stable, diffable, visual-regression
   friendly); use screenshots for human-facing evidence.
7. **On failure, fix the smallest responsible layer and restart.** Patch the narrowest
   layer, re-launch the app if needed, return to step 1 for the SAME path.
8. **Rerun until clean.** Repeat until the Clean Criteria hold on two independent runs.

## Verification & cross-refs

- **Single source of truth for code verification stays `./init.sh` / `./init.ps1`**
  (`python -m pytest` + `python -m compileall .`). This loop is runtime evidence layered
  on top — it never replaces those checks or introduces a competing verify command.
- Feeds the `run-feature` verify step (`.claude/skills/run-feature/SKILL.md`).
- UI states to exercise: `docs/FRONTEND.md` (loading / empty / error / success).
- Promote a worthwhile journey as a golden journey in `docs/RELIABILITY.md`.
- **Redact secrets/PII in any screenshot** per `docs/SECURITY.md` before saving/sharing.

## Generic fallback

If the Playwright MCP browser tools are unavailable, fall back to the global `/run`
(launch and drive the app) or `/verify` (confirm a change works) skills for a lighter,
tool-agnostic check.

## Guardrails

- One path per observation — batching journeys destroys attribution.
- Wait on state with `browser_wait_for`, never a fixed delay.
- Avoid `browser_run_code_unsafe` / `browser_evaluate` unless a snapshot cannot answer the
  question.
