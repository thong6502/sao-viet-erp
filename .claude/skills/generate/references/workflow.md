# Generate (🔨 Builder) — full procedure

Deeper material for the `generate` skill. Load this only when the short workflow in
`SKILL.md` is not enough (e.g. a feature is too big, dependencies are unclear, a verification
step is failing, or the Evaluator keeps handing the feature back).

## Selecting the right feature

A feature is eligible to build when:

- `status` is `not-started` or `in-progress`, AND
- every id in its `dependencies` array points to a feature whose `status` is `done`.

If nothing is eligible, the blocker is an unfinished dependency — build that one instead, or
ask the human which to unblock. Never start a feature whose dependencies are red. On a
feedback rebuild, the orchestrator (`.claude/workflows/gan-loop.js`) names the feature; reuse
that one rather than picking a new feature mid-loop.

## The "done" contract

Mirror of `AGENTS.md` Definition of Done. All must hold before `status: done`:

1. Target behavior implemented per the acceptance criteria in the feature's spec
   (`docs/product-specs/<flow>.md`) and its `feature_list.json` entry.
2. Required code verification actually ran this session (`./init.sh` or `./init.ps1`, both of
   which run `python -m pytest` and `python -m compileall .`).
3. For a UI feature, the 🔍 Evaluator score clears the threshold in `docs/EVALUATION.md`
   (the browser journey is clean and every criterion meets the bar).
4. Evidence recorded in the feature's `evidence` field (and/or `progress.md`).
5. Repository remains restartable from the standard startup path.

## The feedback-rebuild loop

The Generator and Evaluator alternate until PASS or budget, orchestrated by
`.claude/workflows/gan-loop.js`:

1. Build the feature to its acceptance criteria + `docs/UI_DESIGN.md`; get code verification
   green.
2. Hand the running app to the 🔍 Evaluator ([../browser-validate/SKILL.md](../../browser-validate/SKILL.md)),
   which scores the four criteria per `docs/EVALUATION.md`.
3. On **FAIL**, the Evaluator returns the **single weakest criterion** (lowest score, with
   the concrete observed gap). Fix ONLY that weakness, re-verify, and resubmit.
4. Repeat until **PASS** (all criteria meet threshold) or the loop budget is exhausted. On
   budget exhaustion, stop, leave the feature `in-progress`, record the best result + the
   outstanding gap in `progress.md`, and flag for human review — never mark a sub-threshold
   feature `done`.

Keep each pass targeted: one weakness, one fix. Do not re-scope or rewrite the whole feature
in response to a single-criterion note.

## Splitting a feature that is too big

If a feature cannot be built + verified in one focused session:

1. Keep the original entry, set it to `in-progress`.
2. Add narrower sub-features using `templates/feature-entry.json`, each depending on the
   prior one, so the dependency chain enforces order.
3. Record the split rationale in `progress.md` (a decision, not derivable detail).

Backlog *shape* is normally the 🧠 Planner's job ([../plan/SKILL.md](../../plan/SKILL.md));
only split when continuing to build would otherwise stall, and keep every required field.

## When verification fails

- Read the actual failing output; do not guess.
- If the failure is pre-existing (baseline was already red), fix the baseline first and note
  it — that is itself the active scope until green.
- On Windows, `init.ps1` checks `$LASTEXITCODE` after each native step; a nonzero code fails
  fast. On Unix, `init.sh` uses `set -e`. Behavior must match across both.
- A failing browser journey is a build failure too: fix the smallest responsible layer per
  the [browser-validation loop](../../../../docs/sops/browser-validation-loop.md) before
  resubmitting to the Evaluator.

## Adding NEW reusable workflows as skills

This skill family is the template for others. To add another workflow skill (e.g. "release",
"triage-bug"), follow `.claude/skills/README.md` and run the skill validator before
committing so every `references/` and `templates/` link resolves.
