# Reliability & Runtime Signals

> PLACEHOLDER TEMPLATE: this is a reusable harness file. The project source is
> currently EMPTY, so the Golden Journeys list below is a stub. Fill in the
> `<PLACEHOLDER: ...>` blanks when real runtime paths exist; until then keep the
> markers visible so they are obviously unfilled.

This doc defines the **runtime-signal** and **golden-journey** expectations a
feature must satisfy at runtime. It is narrow on purpose:

- **Restartability / "restarts cleanly afterward" is owned by the Lifecycle
  module and the Definition of Done — not here.** See `docs/LIFECYCLE.md`
  (staged, trust-gated bootstrap) and the Definition of Done in `AGENTS.md`
  ("Repository remains restartable from standard startup path"). This file does
  not restate or compete with that; it only *adds* the runtime observability and
  golden-journey bar on top.
- **There is one verification source of truth: `init.sh` / `init.ps1`.** This
  doc never introduces a second verify command. When it says "verify", it means
  run the standard entrypoint.

## Standard verification path (single source of truth)

Do not invent a reliability-specific check command. Health and journeys are
proven through the existing entrypoint already wired in `AGENTS.md`:

```bash
./init.sh        # Unix / macOS / CI (bash)
```
```powershell
./init.ps1       # Windows (PowerShell)
```

Both run the same checks: `python -m pytest` then `python -m compileall .`. Any
runtime signal or golden-journey assertion you add should be exercisable from
that path (e.g. a test under pytest), so that one green run still means "healthy".

## Required Runtime Signals

Every non-trivial feature should emit, at minimum:

- **Structured startup logs** for startup and critical flows — enough to tell,
  from repo-local output, what the system did and where it stopped.
- **Health checks** for key services / dependencies, so liveness is observable
  rather than inferred.
- **Trace or timing data** for slow paths, when available, to diagnose latency
  without a live debugger.
- **User-visible recoverable error states** — recoverable failures must surface
  a clear, actionable state instead of silently failing.

Runtime failures should be diagnosable from repo-local signals alone (logs,
test output, health endpoints), not from memory of a live session.

`<PLACEHOLDER: name this project's concrete log format, health-check endpoint(s),
and where logs/traces are written.>`

## Golden Journeys

The end-to-end paths that MUST keep working. Each golden journey needs a
repeatable verification path (a test runnable via `init.sh` / `init.ps1`) and a
clear failure signal.

- `<PLACEHOLDER: source empty>`
- `<PLACEHOLDER: source empty>`
- `<PLACEHOLDER: source empty>`

When real journeys exist, replace each placeholder with one line: the journey,
its repeatable check (pytest test id), and its failure signal.

## Repeated-failure rule -> add a guardrail

**If a repeated failure mode appears, add a benchmark or guardrail for it** so
the regression is caught mechanically next time. Route the guardrail to the
module that owns the failing surface — do not build a parallel mechanism here:

- **If the failure is a destructive / unsafe command** (the model ran or nearly
  ran something dangerous), add the pattern to the Bash guard and a matching
  case to its test suite: `.claude/hooks/test_guard_bash.py` (the TOOL_SAFETY
  guard tests, run under `init.sh` / `init.ps1`). Protocol: `docs/TOOL_SAFETY.md`.
- **If the failure is a behavior/logic regression**, add a pytest test that
  reproduces it (caught by the standard verify path).
- **Record the evidence** that the guardrail exists and passes in the active
  feature's `evidence` field in `feature_list.json` (see the Definition of Done
  in `AGENTS.md`). The guardrail is not "done" until that evidence is recorded.

## What this doc does NOT own

- **Restartability / clean restart after a feature** -> Definition of Done in
  `AGENTS.md` + `docs/LIFECYCLE.md`.
- **Command / tool safety classification and guards** -> `docs/TOOL_SAFETY.md`,
  `.claude/hooks/guard_bash.py`, `.claude/hooks/test_guard_bash.py`.
- **The verify command itself** -> `init.sh` / `init.ps1` (single source of truth).
