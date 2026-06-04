# ARCHITECTURE.md

> **PLACEHOLDER TEMPLATE** — the app source does not exist yet. This file is the
> contract agents follow until real code lands. Slots marked `<PLACEHOLDER>` are
> intentionally blank; fill the Domain Map and System Shape when the first feature
> is generated. Single source of truth for "is the tree healthy" stays
> `./init.sh` / `./init.ps1` (smoke tests + `compileall`) — never add a competing
> verify command.

This file is the top-level map of the system. Read it on demand when implementing
or changing a cross-cutting boundary or a hard dependency. Keep it concise. For
anything visual — layout, components, tokens, styling, UX states — defer to
[docs/UI_DESIGN.md](UI_DESIGN.md); do not duplicate visual concerns here.

## Stack

- **Frontend:** React + Vite (SPA, TypeScript or JSX `<PLACEHOLDER>`).
- **Backend:** FastAPI (Python), served via ASGI (`uvicorn` `<PLACEHOLDER>`).
- **Database:** SQLite for local/dev, Postgres for production (single SQL layer,
  same migrations and queries against both).
- **Transport:** JSON over HTTP; the frontend talks to the backend only through a
  typed API client.

## System Shape

- Product: `<PLACEHOLDER product name>`
- Primary user workflow: `<PLACEHOLDER main workflow>`
- Runtime surfaces: web SPA (browser) + HTTP API service + relational DB.
- Source of truth for product behavior: the active sprint spec under
  [docs/product-specs/](product-specs/index.md) and its derived `feature_list.json`.

## Domain Map

| Domain       | Purpose          | Frontend Entry   | Backend Entry        | Related Spec  |
|--------------|------------------|------------------|----------------------|---------------|
| `<domain-a>` | `<what it owns>` | `<route / view>` | `<router / service>` | `<spec path>` |
| `<domain-b>` | `<what it owns>` | `<route / view>` | `<router / service>` | `<spec path>` |

## Layer Model

Use these fixed directional models so agents do not invent ad hoc architecture.
Data and dependencies flow in one direction only.

**Frontend (React + Vite):**

`UI components -> state / hooks -> API client -> (HTTP) -> backend`

- Components render and capture input; they hold no fetch logic.
- State and hooks own local/shared state and call the API client.
- The API client is the single place that knows backend URLs, request/response
  shapes, and error mapping.

**Backend (FastAPI):**

`API routes -> services -> repositories -> DB`

- Routes parse/validate (Pydantic schemas) and shape HTTP responses only.
- Services hold business logic and orchestration; they are framework-agnostic.
- Repositories own all SQL/ORM access and are the only layer that touches the DB.
- The DB (SQLite/Postgres) is reached exclusively through repositories.

## Hard Dependency Rules

- Lower layers must not import or depend on higher layers (DB never imports a
  service; a service never imports a route; the API client never imports a
  component).
- The frontend reaches the backend **only** through the API client — components,
  hooks, and views must not call `fetch`/`axios` directly.
- The backend reaches the database **only** through repositories — routes and
  services must not run raw SQL or open sessions.
- Routes contain no business logic; services contain no HTTP or DB-driver
  specifics; repositories contain no business rules.
- SQL must remain portable across SQLite and Postgres; backend-specific dialect
  features need an explicit, justified reason.
- Cross-cutting concerns (auth, logging, config) enter through explicit
  provider/dependency boundaries (e.g. FastAPI dependencies, a React context),
  not by reaching across layers. See [docs/SECURITY.md](SECURITY.md) for auth and
  secret-handling rules.
- New dependencies should be justified in the matching sprint spec.

## Change Checklist

When you touch architecture-relevant code:

1. Update this file if the Domain Map or an allowed boundary changed.
2. Keep the layer flow intact — if a change requires crossing a boundary, fix the
   boundary, do not bypass it.
3. Put any visual/UI decision in [docs/UI_DESIGN.md](UI_DESIGN.md), not here.
4. Add or update an executable check so the rule is enforced mechanically by
   `./init.sh` / `./init.ps1` (the single verification source of truth) — never add
   a competing verify command.
5. Confirm the change is traceable to a feature in `feature_list.json` and its
   acceptance criteria in the sprint spec; record evaluation outcomes per
   [docs/EVALUATION.md](EVALUATION.md).
