# Memory persistence — protocol

This directory is the project's **auto-memory**: agent-written facts that must survive
across sessions. It is separate from instruction memory (`AGENTS.md`, `CLAUDE.md`), which
is human-curated and version-controlled.

Keep this protocol OUT of `MEMORY.md` itself — the index is always-on and byte-capped, so
prose belongs here, not there.

## Layers (by scope and durability)

| Layer | File(s) | Who writes | Loaded |
|---|---|---|---|
| Instruction memory | `AGENTS.md`, `CLAUDE.md`, project conventions | Human | Every session (curated) |
| Auto-memory index | `memory/MEMORY.md` | Agent | Every session (bounded, always-on) |
| Auto-memory topics | `memory/topics/<slug>.md` | Agent | On demand (when a hook is relevant) |
| Session continuity | `progress.md`, `session-handoff.md` | Agent | At startup / handoff (see AGENTS.md) |

## What may be stored (taxonomy)

Only these three types. They are all things you CANNOT re-derive from the codebase:

- **PREFERENCE** — a standing user/team choice ("use uv, not pip"; "prefer table-driven tests").
- **DECISION** — a deliberate choice + rationale that isn't obvious from the code alone.
- **FACT** — a non-derivable external constraint ("prod runs Python 3.12"; account quirks).

## What must NEVER be stored (drift guard)

Anything derivable from the repository: architecture, code patterns, module/file layout,
function signatures, dependency lists, version history, test names. These go stale the
moment code changes and create drift between memory and reality. If you can read it from
the code, do not copy it into memory — re-derive it instead.

## How to save a memory (two-step, crash-safe order)

Always in THIS order so a crash leaves at worst an orphan, never a dangling index pointer:

1. Write the full detail to `memory/topics/<slug>.md` (use the EXAMPLE-topic.md shape).
2. Append exactly ONE line to the matching section of `memory/MEMORY.md`:
   `- [TYPE] <terse one-line hook> (YYYY-MM-DD) -> topics/<slug>.md`

Do NOT write the index line before the topic file exists. Do NOT put more than one line
in the index per memory. Detail, examples, links, and history live in the topic file only.

## Reading memory

At session start, read `memory/MEMORY.md` (cheap, bounded). Open a `topics/<slug>.md` file
only when its hook is relevant to the current task. Do not bulk-load all topic files.

## Instruction priority (counterintuitive — local wins)

When the same topic is set at multiple scopes, the MOST-LOCAL instruction wins:

```
org  <  user (~/.claude)  <  project (AGENTS.md/CLAUDE.md)  <  local (CLAUDE.local.md / root local file)
```

A memory hook does NOT override a project or local instruction. If you add a rule and it
seems ignored, a `CLAUDE.local.md` or local override in the project root is silently
beating it. Verify any new rule with the FULL stack present (user + project + local).

## Housekeeping (orphan sweep)

The two-step save can leave an orphaned `topics/*.md` if the process dies between steps.
Orphans don't corrupt the index but accumulate on disk. Run the sweep periodically:

```bash
python memory/sweep_orphans.py --apply     # delete topic files not referenced by MEMORY.md
python memory/sweep_orphans.py             # dry-run: list orphans only (default, safe)
```

This single Python script runs identically on Windows and Unix.

> A second, equivalent sweeper lives at `tools/memory_sweep.py` (with `.sh` / `.ps1`
> wrappers). It additionally warns when the index approaches its silent line/byte caps.
> Either tool is safe to run; both treat `MEMORY.md` as the source of truth for which
> topic files are referenced.

## Session-end extraction (race-safe)

If you extract memories at end of response, do it AFTER the final response with no pending
tool calls, and treat it as advisory: if the user sends the next message first, simply
reconsider those messages next turn. Never block the user on extraction, and if the main
agent already wrote to memory this turn, skip the extraction pass for that turn.
