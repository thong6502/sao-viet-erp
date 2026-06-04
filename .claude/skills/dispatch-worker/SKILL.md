---
name: dispatch-worker
description: Spawn a sub-agent / delegate work — coordinator, fork, swarm. Write self-contained worker prompts, filter tools per role, enforce single-level fork, two-phase result handoff. Use before any Task/sub-agent dispatch.
---

# Dispatch Worker

Front-loaded triggers: spawn sub-agent, delegate, coordinator, fork, swarm,
parallel agents, research-then-implement. Use this whenever you are about to
hand work to another agent.

## Do this every time

1. **Read** `docs/COORDINATION.md` (full protocol) before dispatching.
2. **Pick a pattern**: default **Coordinator** (zero context inheritance);
   **Fork** only for one-level parallel splits of loaded context; **Swarm** for
   long-running flat-roster workstreams via `coordination/tasks.md`.
3. **Synthesize first.** The coordinator digests prior results into a precise
   spec. Never write "based on your findings / as above" — the worker sees only
   the prompt text.
4. **Scaffold the prompt** from `docs/coordination/worker-prompt.template.md`.
   Fill every `<PLACEHOLDER>`.
5. **Filter tools** to the role minimum (researcher: read/search, no write;
   implementer: +edit/+tests; reviewer: read/search/+tests). Never grant broad
   shell to a worker.
6. **Respect the single-level invariant.** A worker MUST NOT spawn sub-agents.
   The `fork-guard` PreToolUse hook blocks it when `HARNESS_AGENT_DEPTH >= 1`.
   When you launch a child outside Claude Code, increment that env var so the
   guard can protect against grandchildren.
7. **Two-phase handoff.** Worker writes `coordination/results/<task-id>.md` and
   sets `status: done`. Coordinator reads it, then sets `consumed: yes`. Do not
   delete a `done`-but-not-`consumed` result.

## Anti-patterns (reject these)

- A prompt that references unseen history ("continue from before").
- A researcher with write/shell access; an implementer with unrestricted shell.
- A child that itself dispatches sub-agents (recursive fork).
- Deleting a worker result before recording it was consumed.
