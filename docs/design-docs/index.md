# Design Docs — Index & Registry

> Tier 3 resource (load on demand). Routed from `docs/DESIGN.md`.
> This is the authoritative registry of design decisions: their status, what they
> govern, and where the reasoning lives. It is the single place to enter individual
> design docs — `docs/DESIGN.md` points here and nowhere else.

> TEMPLATE PLACEHOLDER FILE — this is a reusable scaffold copied into new projects.
> The project source is currently EMPTY, so there are no project-specific design docs
> yet. The one Accepted entry below is the harness's own foundational decision (the
> agent contract). Add new rows as decisions are made; delete this banner once real
> entries exist.

## How To Use This Index

- Find the decision you care about by status, read its linked doc, then act.
- Before contradicting any **Accepted** decision, read it first and supersede it
  explicitly (do not silently diverge).
- A new design starts as **Proposed**; it becomes **Accepted** only once agreed and
  (where applicable) implemented; it becomes **Deprecated** when superseded.

## Accepted

Decisions in force. Treat these as binding rationale.

| Decision | Governs | Doc |
|----------|---------|-----|
| Agent operating contract | How agents start up, scope work, verify, and hand off — the canonical rules of record for this harness | `../../AGENTS.md` |

<PLACEHOLDER: add one row per Accepted design doc, e.g.
`| <decision name> | <what it governs> | ./<slug>.md |`.>

## Proposed

Decisions under discussion. Not yet binding; may change or be rejected.

| Decision | Governs | Doc |
|----------|---------|-----|
| <PLACEHOLDER: none yet — add proposals as `./<slug>.md` while under review> | | |

## Deprecated

Superseded or withdrawn decisions, kept for historical context so agents understand
why the current shape exists. Never re-adopt a Deprecated decision without a new
Proposed → Accepted cycle.

| Decision | Superseded By | Doc |
|----------|---------------|-----|
| <PLACEHOLDER: none yet> | | |

## Maintenance Rules

- **One decision per doc, one row per doc.** New design docs live beside this index as
  `docs/design-docs/<slug>.md`; add exactly one row in the matching status table.
- **Status lives here, not in the doc body.** Move a doc's row between tables when its
  status changes; do not leave the same decision in two tables. When superseding, fill
  the Deprecated **Superseded By** column with the replacing doc.
- **No contradictory Accepted entries.** Two Accepted rows must not conflict; resolve by
  deprecating one.
- **Promote settled structure.** When an Accepted decision becomes stable system shape,
  fold its map into `docs/ARCHITECTURE.md` and keep the design doc as rationale; note
  the promotion in the row.
- **No dangling links.** Every `Doc` link must resolve to a file that exists, via a
  forward-slash relative path. The Accepted "Agent operating contract" row points at the
  real `../../AGENTS.md` at the repo root.
- **Verification stays single-sourced.** Any verifiable claim in a design doc points at
  `./init.sh` / `./init.ps1` (currently `python -m pytest` + `python -m compileall .`).
  Never introduce a competing verify command.
