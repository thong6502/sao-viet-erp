<!-- PLACEHOLDER TEMPLATE: the project source is currently EMPTY. All grade/row
     values are placeholders. Fill the <PLACEHOLDER: ...> slots once real
     subsystems and benchmark runs exist. -->

# QUALITY_SCORE.md

This document tracks whether the repository is getting stronger or weaker over
time. It is a trend scorecard, not a gate: the single source of truth for
"does it pass right now" is the verification entrypoint `init.sh` / `init.ps1`
(`python -m pytest` + `python -m compileall .`). Every `Verification` column
below records the observed result of running that entrypoint, never a separate
ad-hoc command.

Load this file only for a periodic repo-health review or before a
simplification. It is not needed for routine feature work.

## Grading Scale

- `A`: verified (init.sh / init.ps1 GREEN), legible, stable, boundaries enforced
- `B`: working with minor gaps
- `C`: partially working, notable confusion or instability
- `D`: broken, unsafe, or structurally unclear

## Product Domains

| Domain | Grade | Verification (init.sh / init.ps1) | Agent Legibility | Test Stability | Key Gaps | Last Updated |
|--------|-------|-----------------------------------|------------------|----------------|----------|--------------|
| `<PLACEHOLDER: domain-a>` | - | - | - | - | - | - |
| `<PLACEHOLDER: domain-b>` | - | - | - | - | - | - |
| `<PLACEHOLDER: domain-c>` | - | - | - | - | - | - |

## Module / Subsystem Grades

<PLACEHOLDER: name real Python subsystems> (e.g. packages/modules such as a
core library, a CLI entrypoint, an I/O or persistence layer). Replace the
example rows below once the codebase has real modules.

| Module / Subsystem | Grade | Boundary Enforcement | Agent Legibility | Key Gaps | Last Updated |
|--------------------|-------|----------------------|------------------|----------|--------------|
| `<PLACEHOLDER: core module>` | - | - | - | - | - |
| `<PLACEHOLDER: cli / entrypoint>` | - | - | - | - | - |
| `<PLACEHOLDER: io / persistence>` | - | - | - | - | - |

## Benchmark Snapshots

Each row is one repo-health checkpoint. `Verification` is the result of running
`init.sh` (bash) or `init.ps1` (PowerShell) at that point in time.

| Date | Harness Variant | Verification (init.sh / init.ps1) | Completion Rate | Retries | Defects Before Review | Notes |
|------|-----------------|-----------------------------------|-----------------|---------|-----------------------|-------|
| `<PLACEHOLDER: YYYY-MM-DD>` | `<PLACEHOLDER: baseline / improved / simplified>` | `<PLACEHOLDER: GREEN / RED>` | - | - | - | - |

## Simplification Log

Before removing a component, capture the pre-removal state here, then re-run
`init.sh` / `init.ps1` after removal and record whether verification stayed
GREEN. Keep the change only if behavior is unchanged.

| Date | Component Removed | Verification After (init.sh / init.ps1) | Outcome | Decision |
|------|-------------------|-----------------------------------------|---------|----------|
| `<PLACEHOLDER: YYYY-MM-DD>` | `<PLACEHOLDER: component>` | `<PLACEHOLDER: GREEN / RED>` | `<PLACEHOLDER: degraded / unchanged>` | `<PLACEHOLDER: restore / keep removed>` |
