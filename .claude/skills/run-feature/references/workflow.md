# Run Feature — full procedure

Deeper material for the `run-feature` skill. Load this only when the short workflow in
`SKILL.md` is not enough (e.g. a feature is too big, dependencies are unclear, or a
verification step is failing).

## Selecting the right feature

A feature is eligible to start when:

- `status` is `not-started` or `in-progress`, AND
- every id in its `dependencies` array points to a feature whose `status` is `done`.

If nothing is eligible, the blocker is an unfinished dependency — work that one instead,
or ask the user which to unblock. Never start a feature whose dependencies are red.

## The "done" contract

Mirror of `AGENTS.md` Definition of Done. All four must hold before `status: done`:

1. Target behavior implemented.
2. Required verification actually ran this session (`./init.sh` or `./init.ps1`, both of
   which run `python -m pytest` and `python -m compileall .`).
3. Evidence recorded in the feature's `evidence` field (and/or `progress.md`).
4. Repository remains restartable from the standard startup path.

## Splitting a feature that is too big

If a feature cannot be finished + verified in one focused session:

1. Keep the original entry, set it to `in-progress`.
2. Add narrower sub-features using `templates/feature-entry.json`, each depending on the
   prior one, so the dependency chain enforces order.
3. Record the split rationale in `progress.md` (a decision, not derivable detail).

## When verification fails

- Read the actual failing output; do not guess.
- If the failure is pre-existing (baseline was already red), fix the baseline first and
  note it — that is itself the active scope until green.
- On Windows, `init.ps1` checks `$LASTEXITCODE` after each native step; a nonzero code
  fails fast. On Unix, `init.sh` uses `set -e`. Behavior must match across both.

## Adding NEW reusable workflows as skills

This skill is the template for others. To add another workflow skill (e.g. "release",
"triage-bug"), follow `.claude/skills/README.md` and run the skill validator before
committing so every `references/` and `templates/` link resolves.
