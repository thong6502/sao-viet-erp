# docs/references/ — Curated External Reference Extracts

<!--
PLACEHOLDER TEMPLATE — this folder is a convention scaffold, not real content.
The project source is currently EMPTY, so the only reference shipped here
(`deploy-llms.txt`) is a generalized starter. Replace / add real `*-llms.txt`
files once the project picks a concrete stack.
<PLACEHOLDER: add real reference files when the project picks a stack>
-->

## What this folder is

`docs/references/` holds **curated, token-bounded, agent-readable extracts of upstream
documentation** for the external services and tooling this project depends on (a deploy
builder, a package manager, an API client, a design system, etc.).

These are NOT mirrors of the vendor docs. Each file distills the parts an agent actually
needs to act — entrypoints, runtime assumptions, env-var expectations, and common failure
signatures — into a small flat text file it can load **just-in-time**.

Naming convention: `<topic>-llms.txt` (e.g. `deploy-llms.txt`, `db-llms.txt`,
`<some-api>-llms.txt`). The `-llms.txt` suffix marks the file as written *for an LLM to
read*, mirroring the [llms.txt](https://llmstxt.org/) idea.

## Why it exists (the convention)

- **Curated** — only the load-bearing facts, not the whole manual. If a detail can be
  re-derived from this repo (file layout, versions, code patterns) it does NOT go here; it
  would only drift. References capture *non-derivable upstream* behavior.
- **Token-bounded** — keep each file small (rule of thumb: a few KB, well under a screen of
  scrolling). A reference that grows large should be split by topic, not bloated.
- **Agent-readable** — plain prose + short lists, no rendering tricks. Optimized for an LLM
  to skim and act on, not for human browsing.
- **Load just-in-time** — these are Tier 3 (load-on-demand) resources. Do NOT read them at
  session start. Load the *one* file whose external service you are about to call, and only
  then. The trigger lives in `docs/CONTEXT-MAP.md`.

## How to use these files

1. Before calling/using an external service or tool, check `docs/CONTEXT-MAP.md` for the
   `docs/references/<topic>-llms.txt` row.
2. Load only that one file. Skip the rest.
3. Act. If the file is stale or wrong, fix it in the same change — references are part of
   the repo and are maintained like code, not treated as throwaway notes.

## How to add a new reference

1. Create `docs/references/<topic>-llms.txt`.
2. Distill the upstream docs down to: **entrypoints / commands**, **runtime assumptions**,
   **env-var expectations**, and **common failure signatures** (the same shape as
   `deploy-llms.txt`). Keep it token-bounded.
3. Cross-reference the single verification source of truth — `init.sh` / `init.ps1` — and
   `SETUP.md` rather than inventing a competing "how to build/verify" command.
4. Add ONE row to the Tier 3 table in `docs/CONTEXT-MAP.md` (load-on-demand), with a precise
   trigger ("when calling/using <that service>"). Do not load it eagerly anywhere else.

## What lives here now

| File | Topic | Status |
|------|-------|--------|
| `deploy-llms.txt` | Build + deploy (Nixpacks-style builder) | Generalized starter — `<PLACEHOLDER>` blanks inside |

> Do NOT add files speculatively. A reference is justified only when an agent will actually
> call that service in this project. (The upstream Pack also ships `uv-llms.txt` and a
> design-system reference — intentionally **not** copied here; add the ones THIS project needs.)
