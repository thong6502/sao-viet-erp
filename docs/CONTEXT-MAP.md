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
| `.claude/skills/browser-validate/SKILL.md` + `docs/sops/browser-validation-loop.md` | Validating a UI journey in a real browser (snapshot/console/screenshot/network via Playwright MCP); skill is the thin entry, SOP holds the Execution loop + Clean Criteria |

## Load on demand (Tier 3 - resources)

| Resource | Load ONLY when... | Notes |
|----------|-------------------|-------|
| `docs/ARCHITECTURE.md` | implementing/changing a cross-cutting design or a hard dependency boundary | System shape + Domain Map + Layer Model (Types->Config->Repo->Service->Runtime->UI) + dependency rules; PLACEHOLDER until real code lands |
| `docs/DESIGN.md` | making or revisiting a cross-cutting design decision (data model, boundary, protocol, dependency direction) | thin router into the design-doc registry |
| `docs/design-docs/index.md` | you need the status/owner/link of a specific design decision | registry: Accepted / Proposed / Deprecated |
| `docs/design/layered-domain-architecture.md` | remediating a layer/dependency boundary violation | Tier-3 on-demand remediation SOP; routed from `docs/ARCHITECTURE.md` Change Checklist |
| `docs/PRODUCT_SENSE.md` | deciding what a user-visible change should do, or resolving product/requirements ambiguity | durable product judgment + No-Go patterns; `[replace]` placeholder until product scope is known |
| `docs/product-specs/index.md` + `docs/product-specs/<flow>.md` | defining/changing user-facing flow behavior or its acceptance criteria | index lists Active Specs; copy `_TEMPLATE.md` per flow (Goal / Entry Conditions / User Flow / Acceptance Criteria / Failure States); UI acceptance = Playwright MCP assertions via `docs/sops/browser-validation-loop.md` |
| `docs/FRONTEND.md` | doing UI/frontend work or validating a visible behavior change | frontend policy + user-facing states (empty/loading/success/error/retry) + Playwright MCP verification; runnable loop is the `browser-validate` skill <PLACEHOLDER: activate when a frontend exists> |
| `docs/references/<topic>-llms.txt` | calling/using that external service or tooling | curated extract, load only the one you need; convention in `docs/references/README.md` |
| `docs/generated/<artifact>.md` | you need a schema/derived view you'd otherwise reverse-engineer | generated; check `Last-refreshed` before trusting |
| `docs/COORDINATION.md` | delegating / spawning a sub-agent | full multi-agent protocol |
| `docs/TOOL_SAFETY.md` | adding a tool or editing permissions/guards | full tool-safety protocol |
| `docs/SECURITY.md` | handling secrets, untrusted/fetched/scraped data, or external/destructive actions | secrets + untrusted-data lane; delegates command gating to `docs/TOOL_SAFETY.md` |
| `docs/LIFECYCLE.md` | touching bootstrap / hooks / trust gating | full lifecycle protocol |
| `docs/RELIABILITY.md` | adding/reviewing runtime signals (logs, health checks, traces) or a golden journey, or hardening a repeated failure into a guardrail | runtime-signal + golden-journey bar; restartability stays in LIFECYCLE/DoD; verify via `init.sh`/`init.ps1` |
| `docs/QUALITY_SCORE.md` | doing a periodic repo-health review / before a simplification | trend scorecard (grades + benchmark + simplification log); load on demand |
| `docs/PLANS.md` | starting/resuming work that spans >1 session or >1 subsystem, or with rollout risk / open decisions | Durable exec-plan protocol; SEPARATE lane from `progress.md`/`session-handoff.md` (per-session) and `feature_list.json` (build state) |
| `docs/exec-plans/active/` + `completed/` | reading or updating an active multi-session plan, or archiving a finished one | One `YYYY-MM-DD-short-topic.md` per plan; resumable from repo alone; archive don't delete |
| `docs/exec-plans/tech-debt-tracker.md` | deferring real, acknowledged debt or checking a deferral's next trigger | Table: Date \| Area \| Debt \| Why Deferred \| Risk \| Next Trigger |
| `docs/sops/encode-knowledge-into-repo.md` | durable knowledge still lives in chat/tickets/heads and a fresh session keeps re-discovering it | routes knowledge into the right repo doc; `memory/` stays for non-derivable one-liners |
| `docs/sops/observability-feedback-loop.md` | debugging is slow or an agent claims success without runtime evidence | query -> reason -> rerun loop; repeatable workload today = `./init.sh` / `./init.ps1` |
| `docs/sops/browser-validation-loop.md` | UI behavior needs real runtime interaction (DOM/console/network) a unit test can't cover | drives a browser via Playwright MCP; runtime evidence on top of green verify |
| `memory/topics/<slug>.md` | the matching one-line hook in MEMORY.md is relevant | linked from the index |

## How to extend this map

When you create a new heavy doc, add ONE row to the correct tier here instead of loading
it eagerly elsewhere. The map stays cheap; the resources stay lazy.
