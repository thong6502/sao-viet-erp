---
name: browser-validate
description: >-
  browser UI validation, snapshot, console, screenshot, visual regression, Playwright MCP,
  validate UI journey. Use to drive a real browser and verify a UI path end-to-end. Not for
  unit tests or code-only review.
license: MIT
---

# Browser-Validate — the 🔍 Evaluator (Playwright MCP)

This is the **🔍 Evaluator** stage of the 3-role GAN loop. After the 🔨 Generator
builds ONE feature (with code verification already green), this skill drives the
*running* app through that feature's golden journey, scores the **four criteria**,
and writes the result back into the Score Log. It judges, records, and hands the
**weakest criterion** to the Generator for a targeted rebuild — it never edits
feature code.

- **Rubric + Score Log (where scores go):**
  [../../../docs/EVALUATION.md](../../../docs/EVALUATION.md) — the four criteria,
  anchors, pass threshold, and the ledger this skill appends to.
- **Design-quality reference:**
  [../../../docs/UI_DESIGN.md](../../../docs/UI_DESIGN.md) — design quality is
  judged *against this document* (tokens, components, required UI states).
- **Playwright Execution SOP + Clean Criteria + tool map:**
  [../../../docs/sops/browser-validation-loop.md](../../../docs/sops/browser-validation-loop.md)
  — the deep loop this skill runs. Read it before driving the browser.

The loop orchestration lives in
[../../workflows/gan-loop.js](../../workflows/gan-loop.js); the role overview is in
[../../../docs/ORCHESTRATION.md](../../../docs/ORCHESTRATION.md).

## When this applies

- Scoring a just-built feature before it can be marked done (the Evaluator pass).
- A visible behavior changed (layout, state, copy, enable/disable, error surface).
- A bug only reproduces through interaction, not in a unit test.

Not for unit tests, code-only review, or repo-wide refactors.

## Playwright MCP tools

The full step→tool map is in the
[SOP](../../../docs/sops/browser-validation-loop.md#playwright-mcp-tool-map); the
core set this skill uses:

| Purpose | Tool |
|---------|------|
| Open / select the page | `browser_navigate`, `browser_tabs` |
| Read console (clear noise, observe delta) | `browser_console_messages` |
| Structural BEFORE/AFTER (diffable tree) | `browser_snapshot` |
| Trigger ONE path | `browser_click`, `browser_type`, `browser_fill_form`, `browser_select_option` |
| Wait for async settle (no blind sleeps) | `browser_wait_for` |
| Observe network | `browser_network_requests` |
| Visual AFTER (human evidence) | `browser_take_screenshot` |

Prefer `browser_snapshot` for assertions (stable, diffable, visual-regression
friendly); use screenshots for human-facing evidence. Avoid
`browser_run_code_unsafe` / `browser_evaluate` unless a snapshot cannot answer the
question.

## Shortest reliable loop

1. **Select the page.** `browser_navigate` to `<PLACEHOLDER app launch command / URL>`
   (start the dev server first; PowerShell form on Windows, bash form on Unix).
2. **Clear console noise.** Read `browser_console_messages` once to drain
   pre-existing messages, so the AFTER read shows only what THIS path produced.
3. **Snapshot BEFORE.** `browser_snapshot` (structure) and `browser_take_screenshot`
   if pixels matter — this is your baseline.
4. **Trigger exactly ONE path.** `browser_click` / `browser_type` /
   `browser_fill_form`, then `browser_wait_for` the expected text/state.
5. **Observe runtime.** Re-read `browser_console_messages` (new errors?) and
   `browser_network_requests` (expected calls fired with OK status?).
6. **Snapshot/screenshot AFTER.** `browser_snapshot` + `browser_take_screenshot`;
   compare to BEFORE.
7. **On failure, note the gap and stop scoring that pass** — the Evaluator records
   the weakness rather than patching code; the 🔨 Generator owns the fix.
8. **Rerun until clean.** Confirm the Clean Criteria hold on two independent runs
   before scoring functionality at the top anchors.

The Clean Criteria themselves are defined in the
[SOP](../../../docs/sops/browser-validation-loop.md#clean-criteria).

## Score the four criteria

Score each criterion **1–5** per the anchors in
[EVALUATION.md](../../../docs/EVALUATION.md#the-four-criteria), citing the
snapshot / screenshot / console / network observation that justifies it — never a
vibe.

1. **Design quality** — judged against
   [UI_DESIGN.md](../../../docs/UI_DESIGN.md): layout, spacing, type scale, color,
   component conventions, and the required loading / empty / error / success /
   retry states. A UI that drifts from those tokens/states loses points here.
2. **Originality** — distinctive, fit-to-purpose solution vs. generic scaffold.
3. **Craft** — runtime polish: interaction states, accessible structure, clean
   console/network — the things the
   [Clean Criteria](../../../docs/sops/browser-validation-loop.md#clean-criteria)
   surface.
4. **Functionality** — the feature meets its Acceptance Criteria, verified through
   this Playwright loop on a clean, deterministic run.

## Write the verdict

- **Append one row to the
  [Score Log in EVALUATION.md](../../../docs/EVALUATION.md#score-log)** — date,
  spec/feat-NNN, the four scores, `overall` (lowest of the four, a gate not an
  average), and `verdict` (`PASS` | `FAIL` | `BUDGET`). Append; never overwrite
  history.
- **PASS** when every criterion meets the
  [threshold](../../../docs/EVALUATION.md#pass-threshold): mark the feature done.
- **FAIL**: return the **single weakest criterion** + its concrete evidence to the
  🔨 Generator for a targeted rebuild (tie-break order in EVALUATION.md). Keep
  design-quality evidence grounded in `UI_DESIGN.md`, functionality/craft evidence
  grounded in this loop.
- **BUDGET**: if
  [`gan-loop.js`](../../workflows/gan-loop.js) exhausts its retry budget without a
  PASS, log the best result with verdict `BUDGET` and flag for human review. Never
  silently mark a sub-threshold feature done.

## Verification & cross-refs

- **Code verification stays `./init.sh` / `./init.ps1`** (`python -m pytest` +
  `python -m compileall .`). This loop is runtime evidence layered on top — it
  never replaces those checks or introduces a competing verify command.
- Feature spec + Acceptance Criteria for the journey come from the 🔨
  [Generator](../generate/SKILL.md) and `feature_list.json`.
- **Redact secrets/PII in any screenshot** per
  [SECURITY.md](../../../docs/SECURITY.md) before saving or sharing.

## Generic fallback

If the Playwright MCP browser tools are unavailable, fall back to the global `/run`
(launch and drive the app) or `/verify` (confirm a change works) skills for a
lighter, tool-agnostic check — then score from that weaker evidence and say so.

## Guardrails

- One path per observation — batching journeys destroys attribution.
- Wait on state with `browser_wait_for`, never a fixed delay.
- Score from observed runtime behavior, not the source. The Evaluator records; it
  does not edit feature code.
- Avoid `browser_run_code_unsafe` / `browser_evaluate` unless a snapshot cannot
  answer the question.
