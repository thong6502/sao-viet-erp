<!-- PLACEHOLDER TEMPLATE: This is a reusable harness template file. The project source
     is currently EMPTY, so this folder holds NO real generated artifacts yet. This README
     defines the provenance contract every future generated/derived file in this folder MUST
     follow. Delete this banner once the first real artifact lands. -->

# Generated / Derived Artifacts — Provenance Contract

This folder holds **derivable-but-expensive** artifacts: content an agent could in
principle reconstruct from the codebase, but that is costly enough to reverse-engineer
on demand that we cache it here. Each file is regenerable and **provenance-stamped** so a
fresh session can tell where it came from and whether it is still trustworthy.

> There are no real artifacts here yet (the project source is empty). When you add one,
> name it for what it derives (e.g. `docs/generated/<artifact>.md`) and give it the header
> below. Do **not** create `db-schema.md` — no database exists in this project.

## The boundary: what belongs here vs. `memory/`

| Content | Goes in | Why |
|---|---|---|
| **Derivable but expensive** — a schema, API surface, dependency graph, or derived view you could rebuild from source but don't want to re-derive each session | **`docs/generated/`** (here) | Regenerable + provenance-stamped. If it drifts, you regenerate from the source of truth — the file is a cache, never the truth. |
| **Non-derivable** — a standing PREFERENCE, a DECISION + rationale, or an external FACT you can NOT read out of the code | **`memory/`** (`memory/MEMORY.md` index + `memory/topics/<slug>.md`) | The repo cannot reconstruct it, so it must be written down. See `memory/README.md`. |

One-line test: *"Could I rebuild this from the code if I deleted it?"* — **Yes →** here (regenerate it).
**No →** `memory/` (it is a fact, not a cache).

## Required header on every generated file

Every artifact in this folder MUST begin with these two provenance lines, plus the
do-not-hand-edit rule. Fill the `<PLACEHOLDER: ...>` blanks per artifact:

```markdown
<!-- GENERATED — do not hand-edit generated sections; regenerate from the source below. -->
> Generated-from: <PLACEHOLDER: command, script, or source path that produces this file>
> Last-refreshed: <PLACEHOLDER: YYYY-MM-DD>
```

- **Generated-from** — the exact source of truth that produces this artifact (a script,
  a tool invocation, or a source path). This is the regeneration recipe, not prose.
- **Last-refreshed** — the date the content was last regenerated, as `YYYY-MM-DD`. A
  reader compares this against the source's age to decide whether to trust the cache.

## Rules

- **Do not hand-edit generated sections.** Edits are overwritten on the next regenerate
  and silently diverge from the source. Change the *source*, then regenerate.
- **Regenerate when the source changes.** A stale artifact is worse than no artifact: it
  looks authoritative while lying. Bump `Last-refreshed` every regeneration.
- **Check `Last-refreshed` before trusting.** If it predates recent source changes, treat
  the file as suspect and regenerate before relying on it.
- **The artifact is a cache, never the source of truth.** If the file and the code
  disagree, the code wins — fix the generator, not the file.
- **Provenance is mandatory.** An artifact missing the `Generated-from` / `Last-refreshed`
  header is unverifiable; add the header or move the content to wherever its real source lives.

## Regeneration

Each artifact records its own regeneration recipe in its `Generated-from` header — there is
no single shell command baked in here, because generators are artifact- and project-specific
and must run identically on Windows (PowerShell) and Unix (bash). Keep any cross-platform
regen step in sync the same way `init.sh` / `init.ps1` are kept in sync.

> This folder is for **cached derived content only** — it is not a verification step.
> The single source of truth for verifying the repo stays `./init.sh` (Unix/CI) or
> `./init.ps1` (Windows). Do not add a competing verify or regen command at the harness level.
