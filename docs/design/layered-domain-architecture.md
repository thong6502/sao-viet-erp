# SOP: Layered Domain Architecture

> **PLACEHOLDER-STAGE TEMPLATE** — the project source is currently EMPTY, so there
> are no real domains or boundaries to remediate yet. This file is the on-demand
> remediation note referenced by the Change Checklist in `../ARCHITECTURE.md`; it is
> Tier-3 (load only when a layer/dependency violation is actually being fixed, per
> `../CONTEXT-MAP.md`). Replace the `<PLACEHOLDER: ...>` slots with real domains and
> the specific violation as soon as code lands. The single source of truth for "is the
> tree healthy" stays `../../init.sh` (Unix/CI) / `../../init.ps1` (Windows), which run
> `python -m pytest` + `python -m compileall .` — this SOP never adds a competing
> verify command.

Use this SOP when the agent keeps violating boundaries, duplicating logic across
layers, or producing code that becomes hard to review after a few sessions.

## Goal

Make domain boundaries explicit enough that agents can move quickly without
silently degrading structure.

## Target Model

Within a business domain, prefer this directional flow:

`Types -> Config -> Repo -> Service -> Runtime -> UI`

Cross-cutting concerns should enter through explicit providers or adapters.
Shared utils stay outside the domain and should not accumulate domain logic.

(This is the same layer model recorded in `../ARCHITECTURE.md`; keep the two in sync.)

## Setup Checklist

- Define the current domains in `../ARCHITECTURE.md`.
- Write allowed dependency directions in `../ARCHITECTURE.md`.
- Record cross-cutting interfaces such as auth, telemetry, and external APIs.
- Add one short note for the hardest current boundary violation.
- Decide what should be enforced mechanically by lint, tests, or scripts.

## Execution SOP

1. Map the codebase into domains before touching implementation style.
2. For each domain, identify the allowed layer sequence.
3. Identify all cross-cutting concerns and route them through providers or adapters.
4. Move ambiguous shared logic either into the owning domain or into truly generic utils.
5. Document the rules in `ARCHITECTURE.md`.
6. Add one executable guardrail for the highest-cost violation.
7. Update quality scoring after the change.

## Definition Of Done

- A fresh agent can tell which layer owns a change.
- UI code no longer reaches into repo or external side effects directly.
- Cross-cutting concerns have named entry points.
- At least one important boundary is enforced mechanically.

## One Executable Guardrail (this repo's surface)

Step 6 above is tool-neutral. In THIS harness, "executable guardrail" means a check
that runs under the single verification source of truth — `../../init.sh` /
`../../init.ps1`. Do not invent a separate command. Concretely, encode the boundary
as one of:

- **A `pytest` test** that fails on the violation (the lowest-friction option, since
  `python -m pytest` already runs first in `init`). For an import-direction rule, a
  test can walk modules and assert no lower layer imports a higher one — e.g. parse
  `import`/`from` statements and fail if a `repo` module imports from `ui`.
- **A `compileall`-visible structural check**, when the rule is about a module simply
  existing or being importable in the allowed place (`python -m compileall .` already
  runs second in `init`).

Wire the new test into the existing suite so `../../init.ps1` (Windows / PowerShell:
`./init.ps1`) and `../../init.sh` (Unix / bash: `./init.sh`) prove the boundary on
every run. Add a one-line entry to `../../feature_list.json` for the guardrail work and
record its passing evidence there, not in a side log.

<PLACEHOLDER: name the highest-cost boundary for this project and the exact test file
that enforces it once real domains exist — e.g. `tests/test_layer_boundaries.py`.>

## Repo Artifacts To Update

- `../ARCHITECTURE.md` — domain map, allowed layer/dependency directions, and the
  Cross-Cutting Interfaces table (the durable "map of record" for this rule).
- `../../feature_list.json` — add/track the guardrail and remediation work as features,
  with passing `init` output as evidence.
- `../../progress.md` — note where the remediation stopped so the next session resumes
  cleanly (per-session state; pair with `feature_list.json`).

<PLACEHOLDER: if a multi-session remediation plan is needed, open one in the PLANS lane
under `../exec-plans/` and link it from here — keep durable plans there, not inline.>
