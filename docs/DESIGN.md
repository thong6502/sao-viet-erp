# DESIGN.md — Design Doc Router

> Tier 3 doc (load on demand). Routed from AGENTS.md `### Design Docs`.
> This file is STRICTLY a router into `docs/design-docs/`. It carries no design
> bodies of its own and does NOT duplicate `AGENTS.md` (the canonical agent router).
> For the build map of the system read `docs/ARCHITECTURE.md`; for what-to-build state
> read `feature_list.json` / `progress.md`. Design docs hold the *reasoning* behind
> those, not the rules agents follow day to day.

> TEMPLATE PLACEHOLDER FILE — this is a reusable scaffold copied into new projects.
> The project source is currently EMPTY, so the design-doc registry starts essentially
> empty. Add real entries to `docs/design-docs/index.md` (and the doc files it points
> to) as decisions are made; delete this banner once the registry reflects a real repo.

## Purpose

Design docs capture **why** the system is shaped the way it is — the decisions,
trade-offs, and rejected alternatives behind the architecture. They are durable
reasoning, distinct from:

- `docs/ARCHITECTURE.md` — the current *map* of domains, layers, and boundaries (the
  "what is", not the "why").
- `docs/exec-plans/` (PLANS lane) — durable multi-session *plans* while work is in
  progress; see `docs/PLANS.md`.
- `feature_list.json` / `progress.md` — per-session build state and continuity.

A design doc explains a decision once, so future agents do not re-litigate it. When a
decision becomes settled structure, **promote the resulting map into
`docs/ARCHITECTURE.md`** and leave the design doc as the rationale of record.

## Read This When

Open this router (then the linked design doc) only when you are:

- making or revisiting a cross-cutting design decision (data model, boundary, protocol,
  dependency direction);
- about to contradict an existing decision — read the Accepted entry first;
- writing a new proposal that needs a durable home beyond a single session.

For routine feature work, you do **not** need design docs — use `AGENTS.md`,
`feature_list.json`, and `docs/ARCHITECTURE.md`.

## Canonical Design Docs

The authoritative registry — current status, owners, and links — lives in
**`docs/design-docs/index.md`**. Always enter design docs through that index; do not
hard-link individual docs from here so there is one place to maintain.

- Registry + lifecycle (Accepted / Proposed / Deprecated): `docs/design-docs/index.md`

<PLACEHOLDER: as Accepted design docs accumulate, the index lists them; this router
stays a single pointer and is not edited per-doc.>

## Design Rules

- **One decision per doc.** Each design doc covers a single decision with its
  trade-offs and rejected alternatives — not a grab-bag.
- **Status is tracked in the index, not here.** A doc is Accepted, Proposed, or
  Deprecated per `docs/design-docs/index.md`. Never let two Accepted docs contradict
  each other; supersede explicitly.
- **Promote settled structure.** Once a decision is implemented and stable, fold its
  *map* into `docs/ARCHITECTURE.md` and keep the design doc as rationale. Do not let the
  two drift.
- **Reasoning, not rules.** Design docs explain *why*; the rules agents follow live in
  `AGENTS.md` and the linked `docs/*.md` protocols. Do not restate agent instructions
  here, and do not let this file compete with `AGENTS.md`.
- **Verification stays single-sourced.** Any verifiable claim in a design doc points at
  `./init.sh` (Unix/macOS/CI) / `./init.ps1` (Windows/PowerShell) — currently
  `python -m pytest` + `python -m compileall .`. Never introduce a competing verify
  command.
- **No dangling links.** Every link added to the index must resolve to a file that
  exists; use forward-slash relative paths.
