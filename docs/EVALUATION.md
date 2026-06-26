<!-- PLACEHOLDER TEMPLATE: this repo's product source is currently EMPTY. -->
<!-- The Score Log holds one example row until a real sprint is evaluated. -->
<!-- Tune the PASS THRESHOLD for the project; <PLACEHOLDER tune> marks it. -->

# EVALUATION.md — Evaluator Rubric + Score Ledger

This is the contract for the 🔍 **Evaluator** stage of the 3-role GAN loop. The
Evaluator drives the *running* app, scores each built feature against four
criteria, records the result in the Score Log below, and hands the **weakest
criterion** back to the 🔨 Generator so the next rebuild targets it. The loop is
orchestrated by [`.claude/workflows/gan-loop.js`](../.claude/workflows/gan-loop.js);
the role overview lives in [ORCHESTRATION.md](ORCHESTRATION.md).

This rubric is a quality gate layered **on top of** green code verification
(`./init.sh` / `./init.ps1` = `python -m pytest` + `python -m compileall .`). It
never replaces those checks and never introduces a competing verify command.

## How the Evaluator runs

1. The 🔨 Generator builds ONE feature from its spec
   (`docs/product-specs/<flow>.md`, copied from
   [`_TEMPLATE.md`](product-specs/_TEMPLATE.md)) and `docs/UI_DESIGN.md`, with
   code verification already green.
2. The Evaluator drives the live app through that feature's golden journey using
   the [`browser-validate`](../.claude/skills/browser-validate/SKILL.md) skill —
   the Playwright MCP loop detailed in
   [`docs/sops/browser-validation-loop.md`](sops/browser-validation-loop.md)
   (navigate → snapshot → trigger ONE path → observe console/network → screenshot).
3. The Evaluator scores the four criteria (1–5) and writes one row in the
   [Score Log](#score-log) with an overall and a verdict.
4. If the verdict is **FAIL**, the **single weakest criterion** (lowest score;
   ties broken in the order listed below) becomes the feedback string returned to
   the Generator, which rebuilds only against that weakness. Repeat until PASS or
   the loop budget is exhausted.

The Evaluator only judges and records — it does not edit feature code. Keep
scoring evidence-based: cite the snapshot, the screenshot, or the console/network
observation that justifies each score, not a vibe.

## The four criteria

Each criterion is scored on the same **1–5 scale** (anchors below). Score against
*observed runtime behavior*, not the source.

### 1. Design quality

How closely the built UI matches the intended visual + interaction design.

- **Judged against [`docs/UI_DESIGN.md`](UI_DESIGN.md)** (and any reference in
  `docs/design-assets/`): layout, spacing, type scale, color, component usage,
  responsive behavior, and the loading / empty / error / success states the
  design calls for.

| Score | Anchor |
|-------|--------|
| 5 | Indistinguishable from the `UI_DESIGN.md` intent; all required states styled and polished. |
| 4 | Matches the design; only trivial cosmetic deltas. |
| 3 | Recognizably the design, but noticeable spacing/color/state gaps. |
| 2 | Loosely follows the design; several required states unstyled or wrong. |
| 1 | Ignores `UI_DESIGN.md`; unstyled or visually broken. |

### 2. Originality

Whether the result is a thoughtful, non-generic solution rather than boilerplate.

- Rewards distinctive, fit-to-purpose UI/UX and interaction ideas; penalizes
  cookie-cutter scaffolding that any template would emit.

| Score | Anchor |
|-------|--------|
| 5 | Distinctive, memorable solution clearly tailored to this product. |
| 4 | Thoughtful choices beyond the default; a clear point of view. |
| 3 | Competent but conventional; mostly the obvious approach. |
| 2 | Generic boilerplate with little adaptation to the spec. |
| 1 | Pure scaffold output; indistinguishable from an empty template. |

### 3. Craft

Implementation quality as visible at runtime: polish, robustness, and detail.

- Covers interaction states (hover/focus/disabled/loading), accessible
  structure, copy quality, empty/error handling, no console errors, and clean
  network behavior — the things the
  [browser-validation Clean Criteria](sops/browser-validation-loop.md) surface.

| Score | Anchor |
|-------|--------|
| 5 | Tight and resilient; clean console/network, all states handled, accessible. |
| 4 | Solid; minor rough edges that don't affect use. |
| 3 | Works, but missing states, noisy console, or accessibility gaps. |
| 2 | Fragile; broken states or recurring console/network errors. |
| 1 | Janky or error-spewing; unusable detail-level quality. |

### 4. Functionality

Whether the feature actually does what its acceptance criteria require.

- **Verified via the [`browser-validate`](../.claude/skills/browser-validate/SKILL.md)
  Playwright loop** against the feature's Acceptance Criteria
  (`docs/product-specs/<flow>.md`) and its entry in `feature_list.json`. The
  journey must be **clean on a fresh run** per the SOP's Clean Criteria.

| Score | Anchor |
|-------|--------|
| 5 | Every acceptance criterion passes; journey clean and deterministic. |
| 4 | All core criteria pass; only an edge case falls short. |
| 3 | Primary path works; a stated criterion fails or is flaky. |
| 2 | Partially works; a core acceptance criterion fails. |
| 1 | Does not perform the feature; blocked or broken path. |

## Pass threshold

> **`<PLACEHOLDER tune>`** — set the bar for this project. Default starting point:
> **every criterion ≥ 4** (and no criterion at 1–2). Tune per the product's
> quality bar in `docs/PRODUCT_SENSE.md`.

- **PASS** — all four criteria meet the threshold. Mark the feature done and let
  the orchestrator advance to the next feature.
- **FAIL** — any criterion is below the threshold. Return the **weakest
  criterion** (and the specific evidence) to the 🔨 Generator for a targeted
  rebuild; do not mark the feature done.
- **Overall** = the lowest of the four scores (a gate, not an average) — one weak
  criterion fails the feature even if the others are excellent. Record the
  numeric overall in the log for trend visibility.
- **Budget** — if the loop exhausts its retry budget (see
  [`.claude/workflows/gan-loop.js`](../.claude/workflows/gan-loop.js)) without a
  PASS, stop, log the best result with verdict **BUDGET**, and flag for human
  review. Never silently mark a sub-threshold feature done.

## Weakest-criterion feedback

The feedback to the Generator is the **single lowest-scoring criterion**, so each
rebuild has one clear target instead of a diffuse "make it better".

- On a tie, break in this order: **functionality → craft → design quality →
  originality** (a broken feature outranks a beautiful one).
- The feedback string names the criterion, its score, and the concrete observed
  gap (e.g. *"functionality=2: submit button fires no network request; acceptance
  criterion 'order is saved' unmet — see AFTER snapshot"*).
- Keep functionality/craft evidence grounded in the browser-validation loop and
  design-quality evidence grounded in `docs/UI_DESIGN.md`.

## Score Log

One row per Evaluator pass (append; never overwrite history). `overall` = lowest
of the four. `verdict` ∈ `PASS` | `FAIL` | `BUDGET`. Scores are 1–5.

| Date | Sprint | design | originality | craft | functionality | overall | verdict | notes |
|------|--------|:------:|:-----------:|:-----:|:-------------:|:-------:|:-------:|-------|
| 2026-06-26 | feat-003 | 4 | 4 | 5 | 5 | 4 | PASS | Login golden journey clean & deterministic: empty-submit fires no /login (validation only); wrong creds → login 401 "Invalid email or password" + password cleared; success → Dashboard (admin@example.com) via login 200; reload restores via /me 200; logout → Login and reload stays on Login (no /me). Console clean on all paths (only benign favicon 404 + the deliberately-triggered 401 the app handles). Built to UI_DESIGN tokens inside the ERP AppShell+Sidebar. Threshold: every criterion ≥ 4. |
| 2026-06-26 | feat-007 | 4 | 4 | 5 | 4 | 4 | PASS | Vai trò permission-matrix screen (admin): matrix renders 11 modules × (Xem/Thêm/Sửa/Xóa toggles + Phạm vi own/dept/all); switching dept/role reloads the right matrix (Giám đốc all/all, Trưởng phòng KD dept). Created "QA Reviewer", toggled Khách hàng=Xem + Phạm vi=Cả phòng, Saved (PUT 200) → after a FULL reload the change persisted. Duplicate name "NV Sales" → inline "Tên vai trò đã tồn tại…" (409), no creation. Console 0 errors (dev-only StrictMode double-fetch is benign). Non-admin→403 and empty-department→empty-state are covered by backend test (test_rbac_roles_api) + code branches but not browser-exercised (no non-admin live account / no empty dept in dev.db) → functionality 4. |

<!-- Append new rows below this line (newest last); never overwrite history. -->
