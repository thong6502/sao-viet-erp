# SOP: Observability Feedback Loop

> PLACEHOLDER TEMPLATE — this repo's product source is currently EMPTY, so the
> concrete logs / metrics / traces stack is written as `<PLACEHOLDER>`. Fill those
> in when a runnable app exists. The loop and the Debug Session Checklist are
> reusable as-is.

Use this SOP when debugging is slow, agents keep claiming success without
evidence, or runtime behavior is harder to inspect than the code itself.

## Goal

Give the agent a local feedback loop over logs, metrics, traces, and a runnable
workload so it can reason from execution, not only from code inspection.

## Minimum Stack

- application emits structured **logs** — `<PLACEHOLDER: log format + where written>`
- application emits **metrics** when feasible — `<PLACEHOLDER: metric sink / names>`
- application emits **traces** or timing markers — `<PLACEHOLDER: trace backend / markers>`
- local fan-out or collection layer — `<PLACEHOLDER: collector, or note "none yet">`
- query interfaces for logs, metrics, and traces — `<PLACEHOLDER: how to query locally>`
- a repeatable workload to rerun after each change — **today that is the standard
  verification entrypoint**: `./init.sh` (Unix/CI) or `./init.ps1` (Windows),
  which runs `python -m pytest` + `python -m compileall .`. Until the product has
  its own runnable journey, this is the repeatable workload. Add new runtime
  assertions as pytest tests so the same green run still proves health — never
  introduce a competing verify command.

## Execution SOP

1. Define the golden runtime journeys that matter most (record them in
   `docs/RELIABILITY.md`).
2. Add structured logs to startup and the critical path.
3. Add metrics for latency, failure counts, or queue depth where useful.
4. Add traces or timing markers for slow or multi-step flows.
5. Make the signals queryable from the local dev environment.
6. Give the agent one repeatable workload to rerun (today: `./init.sh` /
   `./init.ps1`; later: the product's own journey, still exercisable from that
   same entrypoint).
7. Require the loop: query -> correlate -> reason -> implement -> restart ->
   rerun -> verify.

## Debug Session Checklist

- What failed?
- Which signal proves the failure?
- Which layer owns the failure?
- What changed after the fix?
- Did the app restart cleanly?
- Did the same workload pass after rerun?

## Definition Of Done

- The agent can explain a failure mode from runtime evidence.
- The same workload can be rerun after each change.
- Restart and rerun are part of the normal task loop.
- Reliability signals and golden journeys are documented in `docs/RELIABILITY.md`.
- A repeated failure mode has a guardrail wired into the single verification
  source of truth (`./init.sh` / `./init.ps1`) per `docs/RELIABILITY.md`.
