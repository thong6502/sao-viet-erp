---
name: generate
description: >-
  build feature, generate, implement sprint feature, generator, build one feature, GAN
  builder. Use to build ONE feature_list.json feature from its spec + UI_DESIGN, verify, and
  record evidence. Not for planning the backlog or scoring the UI.
license: MIT
---

# Generate (the 🔨 Builder of the 3-role GAN loop)

This is the **Generator** role of the human-in-the-loop GAN loop. It takes ONE feature from
`feature_list.json`, builds it from its spec + `docs/UI_DESIGN.md`, verifies, records
evidence, and marks it done. It is the build half of the loop the orchestrator
(`.claude/workflows/gan-loop.js`) runs as generate → browser-validate → feedback-rebuild.

Trigger this skill when the human says: "build feature", "generate the next feature",
"implement `<feature>`", "implement the sprint feature", "build feat-NNN", or "run the
generator". It is the skill form of the build lifecycle in `AGENTS.md` — invoke it instead
of re-deriving the steps.

Do NOT use this to (re)shape the backlog — that is the 🧠 Planner ([../plan/SKILL.md](../plan/SKILL.md)).
Do NOT use it to score the UI — that is the 🔍 Evaluator
([../browser-validate/SKILL.md](../browser-validate/SKILL.md)). Do NOT use it for one-off
edits that are not a tracked feature, or for repo-wide refactors.

## Inputs to read first

1. `feature_list.json` — the backlog and current status of every feature.
2. The feature's sprint spec at `docs/product-specs/<flow>.md` (the acceptance criteria the
   build must satisfy; see [../../../docs/product-specs/index.md](../../../docs/product-specs/index.md)).
3. [../../../docs/UI_DESIGN.md](../../../docs/UI_DESIGN.md) — the design system to build
   UI against (assets in `docs/design-assets/`).
4. [../../../docs/ARCHITECTURE.md](../../../docs/ARCHITECTURE.md) — React + Vite / FastAPI /
   DB layout and conventions for where code goes.
5. [../../../docs/EVALUATION.md](../../../docs/EVALUATION.md) — the 4 criteria and threshold
   a UI feature must clear; if the orchestrator handed back a **weakest-criterion** note,
   that note is your single rebuild target this pass.

## Shortest reliable workflow

1. **Orient.** Run verification first: `./init.sh` (Unix/CI) or `./init.ps1` (Windows). If
   the baseline is red, fix that before adding scope.
2. **Pick exactly ONE feature.** From `feature_list.json`, choose one whose `dependencies`
   are all `done` and whose `status` is `not-started` or `in-progress`. Set it to
   `in-progress`. (On a feedback rebuild, the orchestrator names the feature; reuse it.)
3. **Read the contract.** Load that feature's spec acceptance criteria and `docs/UI_DESIGN.md`
   so you build to the criteria, not a guess.
4. **Stay in lane.** Only touch files needed for this one feature. Note unrelated work in
   `progress.md` — do not do it now.
5. **Build** the target behavior per the acceptance criteria + design system, adding or
   extending tests as you go.
6. **Verify code.** Re-run `./init.sh` / `./init.ps1`. Every required check
   (`python -m pytest`, `python -m compileall .`) must pass. No green, no done.
7. **Verify UI (if the feature is user-facing).** Drive the running app through its golden
   journey with the [browser-validate](../browser-validate/SKILL.md) loop, then let the
   🔍 Evaluator score the 4 criteria per `docs/EVALUATION.md`. If a score is below
   threshold, the **weakest criterion** comes back as your rebuild target — return to step 5
   and fix only that, looping until PASS or the loop budget is spent.
8. **Record evidence.** Set the feature `status` to `done` and fill its `evidence` field
   with concrete proof (e.g. "pytest 12 passed; compileall clean; browser journey clean,
   eval design/orig/craft/func 4/4/5/5 PASS — 2026-06-05").
9. **Hand off.** Update `progress.md` with status and the next concrete step. Leave the repo
   so the next session can run `./init.sh` immediately.

See [references/workflow.md](references/workflow.md) for the full procedure, the "done"
contract, the feedback-rebuild loop, and how to split a feature that is too big.

## Editing feature_list.json safely

- Preserve every required field on each entry: `id`, `name`, `description`, `dependencies`,
  `status`, `evidence`. The validator rejects entries missing any.
- Allowed `status` values: `not-started`, `in-progress`, `done`, `blocked`.
- The 🧠 Planner owns backlog *shape*. As the Builder you only flip `status` and write
  `evidence` for the feature you are building; if you must add a sub-feature when splitting,
  copy [templates/feature-entry.json](templates/feature-entry.json) and replace every
  `<PLACEHOLDER>`.

## Verification & cross-refs

- **Single source of truth for code verification stays `./init.sh` / `./init.ps1`**
  (`python -m pytest` + `python -m compileall .`). Browser validation and the Evaluator
  score are runtime/quality gates layered on top — never a competing verify command.
- Build UI to the bar in `docs/UI_DESIGN.md`; judge it against `docs/EVALUATION.md`. The
  product bar for "good" lives in [../../../docs/PRODUCT_SENSE.md](../../../docs/PRODUCT_SENSE.md).
- The end-to-end role wiring (generate → browser-validate → feedback) lives in
  `docs/ORCHESTRATION.md` and is driven by `.claude/workflows/gan-loop.js`.

## Guardrails

- **One feature per session.** If two features compete, finish or park one first.
- **Build, don't plan or score.** Don't (re)shape the backlog (🧠 Planner) and don't author
  Evaluator scores (🔍 Evaluator); consume their output.
- **Never mark `done` from memory** — only after a real verification run this session, plus
  a passing Evaluator score for UI features.
- **One rebuild target at a time.** On feedback, fix only the weakest criterion handed back;
  do not re-scope the whole feature.
- **Stay restartable.** Don't store derivable facts (architecture, file layout) in
  `progress.md`; record decisions, status, and the next concrete step only.
