---
name: plan
description: >-
  plan sprint, expand sprint spec, sprint to features, feature breakdown, product planning,
  convert spec to feature_list.json. Use to turn a human sprint spec into feat-001..N. Not for
  building features or running the GAN loop.
license: MIT
---

# Plan (the human-in-the-loop Planner)

This is the **Planner** role of the 3-role GAN loop. It takes a human-authored sprint spec
and converts it into the machine-readable backlog (`feature_list.json`) that the builder and
evaluator consume. It is the **only** role allowed to (re)shape the backlog.

Trigger this skill when the human says: "plan this sprint", "expand the sprint spec",
"break the spec into features", "turn `<sprint>.md` into a feature list", or "plan the next
sprint".

This skill **never builds and never auto-runs the loop.** It stops to ask the human how
much detail they want, refines the spec accordingly, writes `feature_list.json`, and then
hands off. Building ONE feature at a time is the 🔨 builder's job; clicking the running app
and scoring it is the 🔍 evaluator's job — both are orchestrated by `gan-loop`, not here.

## Inputs to read first

1. The human's sprint spec at `docs/product-specs/<sprint>.md` (copied from
   [_TEMPLATE.md](../../../docs/product-specs/_TEMPLATE.md)). If no sprint file exists,
   stop and ask the human to write one from the template — do not invent scope.
2. [docs/product-specs/index.md](../../../docs/product-specs/index.md) for active scope.
3. [docs/PRODUCT_SENSE.md](../../../docs/PRODUCT_SENSE.md) for cross-cutting product
   priorities and No-Go patterns.
4. The current `feature_list.json` (you will rewrite it) to preserve schema and any
   already-`done` features.

## Step 1 — PRESENT THE OPTIONS MENU (always stop here first)

Before refining anything, **present an options menu** to the human on how much to detail
the sprint, and **wait for their choice**. Offer it as an AskUserQuestion-style single-select
list, and **ALWAYS include a final free-text "Other" choice**:

- **Keep as written** — trust the spec's acceptance criteria as-is; only normalize wording.
- **Add validation + edge-cases** — keep the flow, but enrich each criterion with input
  validation, empty/loading/error states, and failure-state coverage.
- **Full per-screen acceptance criteria** — expand into screen-by-screen, observable
  Playwright-style assertions (snapshot/text/state) for every step of the user flow.
- **Other (free text)** — let the human describe a different depth or focus in their own
  words, then follow that instruction.

Do not proceed past this step without an explicit choice. This is the human-in-the-loop
gate that makes the Planner human-driven rather than automatic.

## Step 2 — Refine the spec per the chosen option

Apply ONLY the depth the human picked:

- Edit `docs/product-specs/<sprint>.md` in place so the spec and the backlog stay in sync
  (same-session rule from `docs/product-specs/index.md`).
- Keep refinements grounded in the spec's own sections — Goal / Logic-flow / System
  statuses / Edge cases / Acceptance criteria / Failure states; carry each into the
  feature `description`s so no flow step or edge case is silently dropped. Treat genuine
  ambiguity as a spec gap to flag, not as license to guess.
- For UI work, phrase acceptance criteria as observable browser assertions confirmed on top
  of green `./init.sh` / `./init.ps1` (the single verification command), never as a
  replacement for it. The pixel/interaction bar lives in `docs/UI_DESIGN.md`.

## Step 3 — CONVERT the refined spec into feature_list.json

Rewrite `feature_list.json` as `feat-001..N`, one feature per cohesive, independently
verifiable slice of the refined spec. **Keep exactly these fields on every entry** (the
schema the builder and validator depend on):

```json
{
  "id": "feat-001",
  "name": "<PLACEHOLDER short feature name>",
  "description": "<PLACEHOLDER what the builder must implement + its acceptance criteria>",
  "dependencies": [],
  "status": "not-started",
  "evidence": ""
}
```

Rules for the conversion:

- `id`: stable, zero-padded, sequential (`feat-001`, `feat-002`, …). Never renumber an
  already-`done` feature.
- `name`: one short noun phrase a human can scan.
- `description`: the concrete behavior to build **plus** its acceptance criteria, so the
  builder and evaluator can act without re-reading the whole spec.
- `dependencies`: list the `id`s that must be `done` first; the first real feature usually
  depends on project setup. Keep the graph acyclic.
- `status`: every new feature starts `not-started`. Allowed values: `not-started`,
  `in-progress`, `done`, `blocked`. **Preserve the `status` and `evidence` of features that
  are already `done`** — do not reset prior work.
- `evidence`: empty (`""`) for new features; the builder/evaluator fill it.

Validate the JSON parses and every dependency `id` exists before saving.

## Step 4 — STOP and hand off (never auto-run the build)

After writing `feature_list.json`, **stop.** Do not start building. Report to the human:
the sprint that was planned, the feat count, and the first buildable feature
(`status: not-started` with all dependencies `done`).

Then point to the rest of the loop — the Planner does not run it:

- 🔨 **generate** ([../generate/SKILL.md](../generate/SKILL.md)) builds ONE feature at a
  time from the spec + `docs/UI_DESIGN.md`, then verifies.
- 🔍 **browser-validate** ([../browser-validate/SKILL.md](../browser-validate/SKILL.md))
  drives the running app and scores the 4 criteria from `docs/EVALUATION.md`.
- The `.claude/workflows/gan-loop.js` orchestrator runs generate → browser-validate →
  feedback-rebuild until a feature passes or the budget is spent. The end-to-end contract is
  documented in `docs/ORCHESTRATION.md`. Tell the human to launch that loop when they are
  ready — this skill never launches it for them.

## Guardrails

- **Human-in-the-loop is mandatory:** never skip Step 1's options menu, and never proceed
  without an explicit choice (including a typed "Other").
- **Plan only.** Do not implement features, run the dev server, or invoke the GAN loop.
- **Backlog integrity:** only this skill rewrites `feature_list.json`; keep all required
  fields and never discard `done` features or their evidence.
- **Spec is the source of truth.** If the spec and backlog disagree, fix the spec in the
  same session rather than encoding a guess into the features.
