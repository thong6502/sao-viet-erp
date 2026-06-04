# Context Engineering Playbook

> Tier 2 file: read this when a session is getting long, when delegating work, or
> when deciding what to load/save. Routed from AGENTS.md. Keep it actionable, not prose.

Context is a **budget**, not a dump. Every token in the window must earn its place
through one of four operations. This file is the contract for how this harness manages
that budget. The companion index `docs/CONTEXT-MAP.md` says *what* to load *when*
(progressive disclosure); this file says *how* to operate the budget.

## The Four Operations

| Op | Meaning | In this harness |
|----|---------|-----------------|
| **SELECT** | Load context just-in-time, not all-at-once | Follow `docs/CONTEXT-MAP.md`; load Tier 3 docs only when triggered |
| **WRITE** | Persist durable, non-derivable facts back to storage | Append a one-line hook to `memory/MEMORY.md` (see rules below) |
| **COMPRESS** | Summarize older turns mid-session | Use the Compaction template below at the trigger threshold |
| **ISOLATE** | Delegated work must not pollute parent context | Sub-agents start fresh; single-level only (no recursive forking) |

## SELECT — Progressive Disclosure (3 tiers)

```
Tier 1  Metadata (always present, cheap)
        -> feature_list.json, memory/MEMORY.md index, progress.md status line
Tier 2  Instructions (loaded on activation)
        -> AGENTS.md, this file, skill bodies under .claude/skills/*
Tier 3  Resources (loaded ON DEMAND only)
        -> docs/ARCHITECTURE.md, API references, examples, memory/topics/*.md
```

Rules:

- Do NOT eagerly read Tier 3. Consult `docs/CONTEXT-MAP.md` and read a resource only
  when its trigger fires.
- Every variable-length block you paste (command output, file dumps) must be capped.
  If you truncate, leave a recovery pointer, e.g. `(truncated - re-run "git log" for full output)`.
- <PLACEHOLDER: list this project's biggest Tier 3 docs once they exist, e.g. docs/ARCHITECTURE.md, docs/API.md>

## WRITE — Memory discipline

The index `memory/MEMORY.md` has **hard caps enforced silently at read time**
(approx 200 lines / 25 KB). Over the cap, recent entries simply DISAPPEAR with no error.
Therefore:

- **One-line hooks only.** Each index entry is a single terse line, e.g.
  `- [DECISION] Use ruff+mypy, not flake8 - team standard (2026-06-05) -> topics/<slug>.md`.
  Multi-sentence entries hit the byte cap even while under the line cap.
- **Push detail into topic files** under `memory/topics/<slug>.md`. The index line links to it.
- **Never store derivable content.** Architecture, code patterns, file structure, version
  history, dependency lists -> all live in the repo and stale instantly. Memory is for
  **preferences, decisions, and non-derivable facts ONLY** (see the taxonomy in `memory/MEMORY.md`).
- After writing a topic file then updating the index, run the orphan sweep periodically
  (`tools/memory_sweep.py`, or the equivalent `memory/sweep_orphans.py`) so a crash
  between the two steps does not leave orphans.

## COMPRESS — Reactive compaction

When context usage crosses the trigger threshold:

1. **Trigger** at ~80% of the working budget below.
2. **Summarize** the older turns (roughly the first 50% by token count).
3. **Preserve** the most recent turns (~last 20%) verbatim.
4. **Label** the snapshot with the turn number so it is auditable.

Compaction snapshot template (write into your reply, or into `session-handoff.md` for big sessions):

```markdown
## Session Summary (Turns 1-N, compacted at turn N)

**Goal**: <PLACEHOLDER one-line goal>
**Decisions made**:
- <decision 1>
- <decision 2>
**Key files touched**:
- <path> (<why>)
**Open threads**:
- <what is still unfinished>
```

## ISOLATE — Delegation boundary

- Delegated/sub-agent work starts from a **fresh context**; do not inherit the parent's
  accumulated turns unless strictly needed.
- **Single-level only.** A sub-agent must NOT spawn its own sub-agents. Recursive forking
  multiplies context cost exponentially (parent + children + grandchildren). The fork
  guard enforces this (see `docs/COORDINATION.md`).
- Enforce the boundary at **call time**, not just by hiding tools from the prompt.
- A child's result must be read by the parent before the child's record is discarded
  (two-phase: clean disk output at completion, drop the in-memory record only after the
  parent has consumed it).

## Memoized builders -> invalidate at every mutation

Any cached/memoized context builder (e.g. "all recent commits", "file tree", "open TODOs")
is invalidated **manually, not automatically**. Every mutation point (file edit, state
change, new commit) MUST clear its matching cache entry, or the model reads stale data for
the rest of the session. When you add a builder, document its invalidation trigger here:

| Builder | Cached at | Invalidate when | <PLACEHOLDER> |
|---------|-----------|-----------------|---------------|
| <name>  | startup   | <mutation>      |               |

## Context Budget (tune per project)

| Category | Budget (tokens) | Status |
|----------|-----------------|--------|
| System prompt | 2,000 | baseline |
| Instruction files (AGENTS.md + this) | 3,000 | cap |
| Memory index | 1,000 | cap (mirrors the 25KB/200-line hard cap) |
| Session history | 10,000 | compact at 80% |
| Working context (files/output) | 15,000 | cap each block |
| **Total** | **~31,000** | **compaction trigger = 80%** |

> <PLACEHOLDER: adjust these numbers to the model/context window actually in use.>
