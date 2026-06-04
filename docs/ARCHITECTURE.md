# ARCHITECTURE.md

> **PLACEHOLDER TEMPLATE** — project source empty; fill Domain Map +
> Cross-Cutting Interfaces when real code lands. Until then the structure below is
> the contract agents follow; the `[replace]` / `[domain-a]` slots are intentionally
> blank. Single source of truth for "is the tree healthy" stays `./init.sh` / `./init.ps1`.

This file is the top-level map of the system. It is a Tier-3 resource (load on demand
per `docs/CONTEXT-MAP.md`): read it only when implementing or changing a cross-cutting
design or a hard dependency boundary. Keep it concise and point to deeper documents
when needed.

## System Shape

- Product: `[replace with product name]`
- Primary user workflow: `[replace with main workflow]`
- Runtime surfaces: `[desktop / web / cli / services / workers]`
- Source of truth for product behavior: `[replace with product/requirements doc path]`

## Domain Map

| Domain | Purpose | Primary Entry Points | Related Spec |
|--------|---------|----------------------|--------------|
| `[domain-a]` | `[what it owns]` | `[modules / routes / commands]` | `[spec path]` |
| `[domain-b]` | `[what it owns]` | `[modules / routes / commands]` | `[spec path]` |

## Layer Model

Use a fixed directional model so agents do not invent ad hoc architecture:

`Types -> Config -> Repo -> Service -> Runtime -> UI`

Cross-cutting concerns should enter through explicit provider or adapter
boundaries instead of reaching across layers directly.

## Hard Dependency Rules

- Lower layers must not depend on higher layers.
- UI must not bypass runtime or service contracts.
- Data access must enter through repositories or equivalent adapters.
- Shared utilities must remain generic and must not accumulate domain logic.
- New dependencies should be justified in the matching plan or design doc.

## Cross-Cutting Interfaces

| Concern | Approved Boundary | Notes |
|--------|-------------------|-------|
| Logging and tracing | `[provider / utility path]` | `[structured only, no ad hoc console use]` |
| Auth | `[provider path]` | `[token/session rules]` |
| External APIs | `[client or provider path]` | `[rate limit / retry guidance]` |
| Feature flags | `[flag boundary]` | `[ownership]` |

## Current Hot Spots

- `[area that is hardest for agents to change safely]`
- `[area with weak boundaries or fragile tests]`

## Change Checklist

When you touch architecture-relevant code:

1. Update this file if the domain map or allowed boundaries changed.
2. Update the matching design doc if the reasoning (not just the map) changed.
3. Add or update an executable check so the rule is enforced mechanically by
   `./init.sh` / `./init.ps1` (the single verification source of truth) — never add a
   competing verify command.
4. If a layer/dependency rule was violated and is being remediated, the on-demand
   remediation note lives at [docs/design/layered-domain-architecture.md](./design/layered-domain-architecture.md)
   (Tier-3; loaded only while remediating).
