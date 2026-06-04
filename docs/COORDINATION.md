# Multi-Agent Coordination

How this Python harness splits work across multiple agents without context
explosion, duplicated research, or runaway recursion. Read this before spawning
any sub-agent.

> Routing summary lives in `AGENTS.md` ("Multi-Agent Coordination"). This file
> is the full protocol. Worker prompt scaffolds live in
> `docs/coordination/worker-prompt.template.md`. The shared task ledger lives in
> `coordination/tasks.md`.

## The one rule that prevents chaos

**The coordinator synthesizes; it does not delegate understanding.**

- Anti-pattern: "Based on your findings, fix the auth system."
- Pattern: "Research found 3 flows (login, logout, refresh). Implement ONLY the
  token-refresh handler using the JWT strategy in [synthesized spec]. Return:
  diff + test results."

Every worker starts with **zero** inherited context (coordinator pattern) unless
you deliberately fork. So the coordinator must digest worker output into a
precise, self-contained spec before dispatching the next worker. If a prompt
contains "based on your previous" / "as discussed above", it is broken — the
worker cannot see that history.

## Pick a pattern

| Pattern | Context sharing | Best for | Hard constraint |
|---|---|---|---|
| **Coordinator** | None (workers start fresh) | Multi-phase: research -> synthesize -> implement -> verify | Slowest, safest. Default choice. |
| **Fork** | Full (child inherits parent history) | Quick parallel splits of already-loaded context | **Single level only** — children must NOT fork (enforced, see below) |
| **Swarm** | Peer-to-peer via shared task ledger | Long-running independent workstreams | **Flat roster** — teammates cannot spawn teammates |

Default to **Coordinator** unless you have a concrete reason. Fork only when the
loaded context is genuinely needed by every child and the split is one level
deep.

## Coordinator workflow (recommended)

```
Phase 1  Research    (tools: read/search/glob — NO write)   -> raw findings
   |  coordinator SYNTHESIZES findings into a spec
Phase 2  Plan        (coordinator, in-context)                -> precise spec
   |  coordinator writes a self-contained worker prompt
Phase 3  Implement   (tools: read/search/edit/test)           -> diff + tests
   |
Phase 4  Verify      (tools: read/test — runs ./init.ps1 or ./init.sh) -> pass/fail
```

Per phase:
1. Copy `docs/coordination/worker-prompt.template.md`, fill every `<PLACEHOLDER>`.
2. Filter the worker's tool set to the minimum it needs (see table above).
3. Dispatch (Claude Code: the `Task` sub-agent tool).
4. When the worker returns, the coordinator reads the result, synthesizes, and
   only then writes the next phase's prompt.

## Fork guard — the single-level invariant

Recursive forking multiplies context cost exponentially (parent + children +
grandchildren + ...). This harness enforces a **single-level** invariant:

- A child agent is marked by the env var `HARNESS_AGENT_DEPTH` (set when it is
  spawned). Depth `0`/unset = root coordinator; `1` = a child.
- The `PreToolUse` hook `coordination/hooks/fork-guard` **blocks** any sub-agent
  spawn (`Task` tool) when `HARNESS_AGENT_DEPTH >= 1`.
- The spawn tool may stay in the child's tool pool (for prompt-cache sharing)
  but is blocked at call time — do not rely on tool-list removal alone.

To spawn a child, the parent must export the next depth. Cross-platform:

```bash
# Unix / CI (bash) — before launching a child agent process
HARNESS_AGENT_DEPTH=$(( ${HARNESS_AGENT_DEPTH:-0} + 1 )) <child-launch-command>
```

```powershell
# Windows (PowerShell)
$env:HARNESS_AGENT_DEPTH = [int]($env:HARNESS_AGENT_DEPTH ?? 0) + 1
# then launch the child
```

> Within Claude Code, the depth env var is propagated by the launch wrapper. If
> you spawn children by hand, set it yourself or the guard cannot protect you.

## Swarm: flat roster + shared ledger

- Roster is **flat**: `researcher`, `implementer`, `reviewer`. A teammate
  **cannot** spawn another teammate (same depth guard applies).
- Coordination is **indirect** through `coordination/tasks.md` (the ledger), not
  by agents prompting each other. An agent claims a task by setting `owner`, does
  the work, and posts the result back.

### Two-phase result handoff (don't lose results to eviction)

A finished worker's output can be cleaned up before the parent reads it. Use two
phases:

1. **Eager (terminal state):** the worker writes its deliverable to a durable
   file under `coordination/results/<task-id>.md` and sets the task `status:
   done` in the ledger. Disk output for transient scratch may be cleaned now.
2. **Lazy (after parent reads):** the in-memory/working record and the result
   file are only removed AFTER the coordinator has recorded that it consumed the
   result (set `consumed: yes` in the ledger). Never delete a result file whose
   task is `done` but not yet `consumed`.

This makes a crash between phases safe: an unread result is reconsidered, not
lost.

## Tool filtering per role (always restrict)

| Role | read | search/glob | edit/write | test/shell | spawn (Task) |
|---|---|---|---|---|---|
| researcher | yes | yes | NO | NO | NO |
| implementer | yes | yes | yes | tests only | NO |
| reviewer | yes | yes | NO | tests only | NO |
| coordinator (root) | yes | yes | yes | yes | yes (depth 0 only) |

A researcher that can write will start implementing; an implementer with broad
shell access will run destructive commands. Restrict deliberately.

## Checklist before you spawn

- [ ] Chose Coordinator unless Fork/Swarm is justified.
- [ ] Worker prompt is fully self-contained (no "as above" / "your findings").
- [ ] Worker tool set is filtered to the minimum for its role.
- [ ] If forking: this is the first level (no grandchildren) and depth is set.
- [ ] Deliverable + "do NOT return" are stated explicitly.
- [ ] Results path (`coordination/results/<task-id>.md`) is named in the prompt.
