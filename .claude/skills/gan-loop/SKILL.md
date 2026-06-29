---
name: gan-loop
description: >-
  run gan-loop, GAN loop orchestrator, build the spec, validate features, re-score a feature,
  validateOnly. Use to launch the gan-loop multi-agent workflow (build → independent
  browser-validate → feedback) over feature_list.json. Not for planning or one-off edits.
license: MIT
---

# gan-loop (launcher)

Thin launcher for the **gan-loop workflow** ([../../workflows/gan-loop.js](../../workflows/gan-loop.js)).
When the human types `/gan-loop [args]`, this skill maps the args and invokes the **Workflow tool**
(`name: "gan-loop"`). The workflow drives steps 3-5 of the 3-role GAN loop, one feature at a time:
a **build** agent ([../generate/SKILL.md](../generate/SKILL.md)) builds + verifies a feature, then a
**separate** evaluator agent ([../browser-validate/SKILL.md](../browser-validate/SKILL.md)) scores it
independently, and the weakest criterion feeds the next rebuild. Role wiring:
[../../../docs/ORCHESTRATION.md](../../../docs/ORCHESTRATION.md); rubric:
[../../../docs/EVALUATION.md](../../../docs/EVALUATION.md).

This skill does NOT build or score itself — it only launches the workflow. It is the build+validate
half of the loop; the 🧠 Planner ([../plan/SKILL.md](../plan/SKILL.md)) fills `feature_list.json` first.

## What to do when invoked

1. **Parse the slash args** (the text after `/gan-loop`) into a workflow `args` object:
   - any token matching `feat-NNN` → add to `args.features` (build/validate exactly these).
   - `validateOnly` / `validate-only` / "chỉ chấm" / "re-score" → `args.validateOnly = true`
     (skip building; just run the independent evaluator — e.g. to re-score an already-done feature).
   - any token matching `spec-*` → `args.specHint` (only features whose description mentions it).
   - `maxRounds=N` / `threshold=N` → `args.maxRounds` / `args.threshold` (numbers).
   - no args → omit `args` entirely (the workflow scans `feature_list.json` for every not-`done` feature).
2. **Confirm scope, then launch.** Call the Workflow tool with `{ name: "gan-loop", args }`. A full
   run spawns build + evaluator agents per feature and starts the app — it costs tokens and time, so
   confirm with the human first unless they were explicit. If the backlog has no not-`done` feature
   (and no `features`/`validateOnly` given), say so and stop — there is nothing to build.
3. **Relay the result.** The workflow returns `{ processed: [{id, passed, overall, weakest}], ... }`.
   Summarize per feature: passed/blocked + overall score; for any `blocked`, surface the weakest
   criterion for human follow-up. The agents persist status/evidence (feature_list.json), the Score
   Log (EVALUATION.md), and progress.md themselves.

## Examples

| Human types | Workflow `args` | Effect |
|---|---|---|
| `/gan-loop` | *(none)* | build+validate every not-`done` feature in dependency order |
| `/gan-loop spec-04` | `{ specHint: "spec-04" }` | build+validate ALL of spec-04's not-`done` features |
| `/gan-loop validateOnly spec-03` | `{ validateOnly: true, specHint: "spec-03" }` | re-score ALL of spec-03's features (any status), no build |
| `/gan-loop validateOnly feat-016` | `{ validateOnly: true, features: ["feat-016"] }` | re-score just feat-016 |
| `/gan-loop feat-013 feat-014` | `{ features: ["feat-013", "feat-014"] }` | only these two |
| `/gan-loop threshold=5` | `{ threshold: 5 }` | raise the pass bar to 5 |

> `specHint` matches the spec name **inside each feature's description** (there is no separate
> "spec" field in `feature_list.json`), so the spec file must be referenced there (it is, by
> convention, from the `plan` step). In **build** mode the scan skips `done` features; in
> **validateOnly** mode it includes them so a finished spec can be re-scored.

## Guardrails

- **Launch only.** Don't reshape the backlog (🧠 Planner) or hand-edit code here — the spawned
  agents do the build/score work by following their own skills.
- **Opt-in + bounded.** Only launch on an explicit human ask; the workflow is already bounded
  (`maxRounds`, pass threshold from EVALUATION.md). Never mark a sub-threshold feature `done`.
- **One feature in flight.** The workflow processes features sequentially (builds mutate shared
  files) — do not parallelize it.
