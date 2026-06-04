# AGENTS.md

Reusable GAN app-template: build a React + Vite / FastAPI / SQLite-Postgres app one feature at a time via a human-in-the-loop, generate-then-evaluate loop.

> This is the canonical agent router. `CLAUDE.md` only points here — do not duplicate guidance into it.

## The 3-Role GAN Loop

A human Planner seeds the work; two skills then loop, orchestrated by `.claude/workflows/gan-loop.js`:

1. Human writes a sprint spec in `docs/product-specs/<sprint>.md` (from `_TEMPLATE.md`).
2. 🧠 **plan** — reads the sprint, presents an options menu (with an "Other" free-text choice) on how much to detail it, refines per the choice, then converts it into `feature_list.json` (feat-001..N + acceptance criteria). It STOPS to ask — never auto-runs.
3. 🔨 **generate** — builds ONE feature from the spec + `docs/UI_DESIGN.md`, then verifies.
4. 🔍 **browser-validate** (Evaluator) — Playwright-clicks the running app, scores 4 criteria (design quality, originality, craft, functionality) per `docs/EVALUATION.md`.
5. If a score is below threshold, the weakest criterion feeds back to 🔨 and the feature is rebuilt — looping until pass or budget. `gan-loop.js` drives steps 3–5.

## Startup Workflow

Before writing code:

1. **Confirm working directory** with `pwd`.
2. **Read this file** completely.
3. **Read `docs/ORCHESTRATION.md`** — how the loop, skills, and scripts fit together.
4. **Run verification** — `./init.sh` (Unix/macOS/CI) or `./init.ps1` (Windows/PowerShell).
5. **Read `feature_list.json`** for current feature state.

If baseline verification is failing, repair that first before adding scope.

## Working Rules

- **One feature at a time**: pick exactly one unfinished feature from `feature_list.json`.
- **Verification required**: never claim done without running `init.sh` / `init.ps1`.
- **Mechanize repeated feedback**: when the same review/eval note recurs, promote it into a check (an `init.sh`/`init.ps1` step or a test) instead of re-explaining it.
- **Stay in scope**: don't modify files unrelated to the current feature; write only your own files.
- **Leave clean state**: next session must run `./init.sh` immediately, and update `progress.md` before ending.

## Definition of Done

A feature is done only when ALL of these hold:

- [ ] Target behavior is implemented per its acceptance criteria in `feature_list.json`.
- [ ] `./init.sh` / `./init.ps1` passed (`pytest` smoke + `compileall`).
- [ ] Evaluator score clears threshold per `docs/EVALUATION.md` (UI features).
- [ ] Evidence recorded in `feature_list.json` / `progress.md`; repo restartable from the startup path.

## Routing Map

Load a file only when its row is relevant.

| File | Purpose |
| --- | --- |
| `CLAUDE.md` | Pointer to this router. |
| `QUICKSTART.md` | Fastest path to run the loop end-to-end. |
| `docs/ORCHESTRATION.md` | How the 3 roles + `gan-loop.js` wire together. |
| `docs/PRODUCT_SENSE.md` | What "good" means; product bar for features. |
| `docs/ARCHITECTURE.md` | React + Vite / FastAPI / DB layout and conventions. |
| `docs/UI_DESIGN.md` | Design system the 🔨 generate skill builds against (assets in `docs/design-assets/`). |
| `docs/EVALUATION.md` | The 4 scoring criteria, thresholds, and recorded scores. |
| `docs/SECURITY.md` | Secrets, untrusted data, and external-action policy. |
| `docs/product-specs/index.md` | Sprint-spec catalog; author new specs from `_TEMPLATE.md`. |
| `docs/sops/browser-validation-loop.md` | Deep SOP behind the 🔍 browser-validate skill. |
| `.claude/workflows/gan-loop.js` | Orchestrator for generate → validate → feedback (steps 3–5). |
| `.claude/skills/plan/SKILL.md` | 🧠 sprint → `feature_list.json` (options menu, stops to ask). |
| `.claude/skills/generate/SKILL.md` | 🔨 build + verify one feature. |
| `.claude/skills/browser-validate/SKILL.md` | 🔍 Playwright-drive and score the running app. |
| `.claude/skills/README.md` | Skill authoring guide; validate via `.claude/skills/scripts/validate-skills.{sh,ps1}`. |

Mark unknown project specifics with `<PLACEHOLDER>`.
