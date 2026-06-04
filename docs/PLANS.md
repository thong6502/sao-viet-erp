# PLANS.md

> Tier 3 doc (load on demand). Routed from AGENTS.md `### Execution Plans`.
> This file defines how durable execution plans are created, updated, completed,
> and archived. Read it only when a piece of work qualifies for a plan (see below).

## Scope — What This Governs (and What It Does NOT)

PLANS.md governs **durable, multi-session / multi-subsystem execution plans only**.
It is the home for work that must survive across sessions and agents while progress
is being made.

It does **NOT** replace the per-session continuity and build-state surfaces:

| Surface | Owns | Lane |
|---------|------|------|
| `docs/exec-plans/` (this lane) | Durable multi-session / multi-subsystem **plans** while progress is ongoing | PLANS |
| `progress.md` + `session-handoff.md` | **Per-session continuity** (where the last session stopped, handoff to the next) | session state |
| `feature_list.json` | **Build state** (which features exist and their status — source of truth for "done") | build state |

Rule of thumb: if it is *what to build next this session* it belongs in
`feature_list.json` / `progress.md`; if it is a *multi-session campaign with risk,
open decisions, and a verification path* it belongs in an exec-plan here. Do not
duplicate state across lanes — link instead.

## When A Plan Is Required

Create an execution plan when work:

- spans more than one session
- changes more than one subsystem
- has non-trivial verification or rollout risk
- depends on open decisions that should be logged

Trivial, single-session, single-file work does **not** need a plan — track it in
`feature_list.json` / `progress.md` instead (see Scope above).

## Plan Locations

- `docs/exec-plans/active/`: plans currently driving work
- `docs/exec-plans/completed/`: finished plans kept for future agent context
- `docs/exec-plans/tech-debt-tracker.md`: deferred work and follow-ups

## Minimum Plan Sections

- objective
- scope and out-of-scope
- verification path
- risks and blockers
- progress log
- open decisions

## Verification Path Guidance

A plan's **verification path** section must name the concrete checks that prove the
work is done — never a vague "tests pass".

- The single verification source of truth is `./init.sh` (Unix/macOS/CI) or
  `./init.ps1` (Windows/PowerShell). Both currently run `python -m pytest` and
  `python -m compileall .`. Point the plan's verification path at these scripts; do
  not invent a competing verify command.
- UI / front-end features may additionally verify through **Playwright MCP** per the
  `browser-validate` skill (`.claude/skills/browser-validate/SKILL.md`)
  <PLACEHOLDER: confirm skill path once the browser-validate skill is added to this
  template>. Record the exact browser checks (URL, action, expected DOM/visual state)
  in the plan's verification path so a fresh agent can reproduce them from the repo
  alone.

## Operating Rules

- One active plan should have one clearly owned current step.
- Update the plan as work progresses; do not treat it as static prose.
- If a decision changes implementation direction, record it in the plan.
- Move finished plans to `completed/` so agents can still discover prior context.
