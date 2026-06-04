# Self-Contained Worker Prompt Template

Copy this file for each dispatched worker. Fill EVERY `<PLACEHOLDER>`. Delete any
section that genuinely does not apply. A worker sees ONLY what is written here —
it inherits no parent context (unless this is a deliberate single-level fork).

> Rule: if you cannot fill a `<PLACEHOLDER>` without saying "see previous
> conversation", you have not synthesized enough yet. Digest first.

---

## Task

<PLACEHOLDER: one-line statement of exactly what to produce, e.g. "Implement the
token-refresh handler in src/auth/refresh.py">

## Context (copied from coordinator synthesis — NOT a reference to history)

- Background: <PLACEHOLDER: the facts the worker needs, written out in full>
- Decision already made: <PLACEHOLDER: e.g. "Use refresh-token rotation">
- Relevant files: <PLACEHOLDER: absolute or repo-relative paths to read first>

## Your role

You are a **<PLACEHOLDER: researcher | implementer | reviewer>**.
<PLACEHOLDER: one sentence describing the job for this role.>

## Constraints

- Follow existing patterns in `<PLACEHOLDER: path/to/reference/module.py>`.
- Do NOT modify `<PLACEHOLDER: out-of-scope files/areas>`.
- Do NOT spawn sub-agents (single-level invariant; the fork guard will block it).
- <PLACEHOLDER: any other guardrails>

## Your tools (minimum for this role)

<PLACEHOLDER: list, e.g.>
- researcher: Read, Grep, Glob — NO write, NO shell
- implementer: Read, Grep, Glob, Edit, Write, plus shell limited to tests
- reviewer: Read, Grep, Glob, plus shell limited to tests

Verification command (this harness): `./init.sh` (Unix/CI) or `./init.ps1`
(Windows). Tests: `python -m pytest`.

## Deliverable

Write your result to `coordination/results/<PLACEHOLDER: task-id>.md`, then
return:

1. <PLACEHOLDER: e.g. "Implementation diff (files changed)">
2. <PLACEHOLDER: e.g. "Test results (pass/fail) from `python -m pytest`">
3. Any blockers or clarifications needed.

When done, update `coordination/tasks.md`: set this task's `status: done`.

## Do NOT return

<PLACEHOLDER: e.g. "Research findings, architectural debates, alternative
designs — only the deliverable above.">
