# Context Map (Progressive Disclosure Index)

> Tier 1 metadata: this is the cheap "table of contents" that tells you WHAT to load
> and WHEN. Reading this file is always allowed and should be cheap. Do not read the
> linked Tier 3 resources until the matching trigger fires (SELECT operation).

## Always loaded (Tier 1 - metadata)

| Resource | Why |
|----------|-----|
| `feature_list.json` | Active feature + status |
| `progress.md` | Where the last session stopped |
| `memory/MEMORY.md` | One-line memory hooks (preferences/decisions) |
| this file | The load map itself |

## Load on activation (Tier 2 - instructions)

| Resource | Trigger |
|----------|---------|
| `AGENTS.md` | Every session start |
| `docs/CONTEXT.md` | Session getting long, delegating, or deciding what to load/save |
| `.claude/skills/*/SKILL.md` | When that skill's task type comes up |

## Load on demand (Tier 3 - resources)

| Resource | Load ONLY when... | Notes |
|----------|-------------------|-------|
| `docs/ARCHITECTURE.md` | implementing/changing a cross-cutting design | <PLACEHOLDER: create when it exists> |
| `docs/API.md` or external API refs | calling that external service | <PLACEHOLDER> |
| `docs/COORDINATION.md` | delegating / spawning a sub-agent | full multi-agent protocol |
| `docs/TOOL_SAFETY.md` | adding a tool or editing permissions/guards | full tool-safety protocol |
| `docs/LIFECYCLE.md` | touching bootstrap / hooks / trust gating | full lifecycle protocol |
| `memory/topics/<slug>.md` | the matching one-line hook in MEMORY.md is relevant | linked from the index |
| `<example/snippet dirs>` | you need a concrete pattern to copy | <PLACEHOLDER> |

## How to extend this map

When you create a new heavy doc, add ONE row to the correct tier here instead of loading
it eagerly elsewhere. The map stays cheap; the resources stay lazy.
