---
name: run-feature
description: >-
  feature workflow, pick one feature, implement and verify, session handoff for this Python
  harness. Use to start/resume a feature from feature_list.json, run init verification, and
  leave a restartable state. Not for ad-hoc edits unrelated to a tracked feature.
license: MIT
---

# Run Feature (canonical harness workflow)

This skill packages THIS repository's core reusable workflow: take one feature from
`feature_list.json` from "not-started" to verified-done without overreaching. It is the
skill form of the lifecycle in `AGENTS.md` — invoke it instead of re-deriving the steps.

Trigger this skill when the user says: "work on the next feature", "implement <feature>",
"continue where we left off", "pick up a feature", or "finish the active feature".

Do NOT use this for one-off edits that are not a tracked feature, for repo-wide refactors,
or for anything that touches more than the single active feature.

## Shortest reliable workflow

1. **Orient.** Run verification first: `./init.sh` (Unix/CI) or `./init.ps1` (Windows).
   If baseline is red, fix that before adding scope.
2. **Pick exactly ONE feature.** Read `feature_list.json`; choose one feature whose
   `dependencies` are all `done` and whose `status` is `not-started` or `in-progress`.
   Set its `status` to `in-progress`.
3. **Stay in lane.** Only touch files needed for that feature. If you discover unrelated
   work, note it in `progress.md` — do not do it now.
4. **Implement** the target behavior, adding/extending tests as you go.
5. **Verify.** Re-run `./init.sh` / `./init.ps1`. Every required check
   (`python -m pytest`, `python -m compileall .`) must pass. No green, no done.
6. **Record evidence.** Set the feature `status` to `done` and fill its `evidence` field
   with the concrete proof (e.g. "pytest 12 passed; compileall clean — 2026-06-05").
7. **Hand off.** Update `progress.md` and, for larger sessions, `session-handoff.md`.
   Leave the repo so the next session can run `./init.sh` immediately.

See [references/workflow.md](references/workflow.md) for the full procedure, the
"done" contract, and how to split a feature that is too big.

## Editing feature_list.json safely

- Preserve every required field on each entry: `id`, `name`, `description`,
  `dependencies`, `status`, `evidence`. The validator rejects entries missing any.
- Allowed `status` values: `not-started`, `in-progress`, `done`, `blocked`.
- Add new features by copying [templates/feature-entry.json](templates/feature-entry.json)
  and replacing every `<PLACEHOLDER>`.

## Guardrails

- One feature per session. If two features compete, finish or park one first.
- Never mark `done` from memory — only after a real verification run in this session.
- Do not store derivable facts (architecture, file layout) in `progress.md`; record
  decisions, status, and the next concrete step only.
