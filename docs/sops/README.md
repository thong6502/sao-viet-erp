# SOP Catalog

Standard Operating Procedures: step-by-step playbooks the agent follows when it
hits a recurring bottleneck. Each SOP is a **Tier-3 resource** — load it on
demand (when its trigger fires), not eagerly. The catalog itself is cheap to read.

These SOPs sit **on top of** the single verification source of truth, never
beside it: code health is always proven by `./init.sh` (Unix/CI) or `./init.ps1`
(Windows), which run `python -m pytest` + `python -m compileall .`. No SOP
introduces a competing verify command.

## Adopted SOPs

| SOP | Use it when... |
|-----|----------------|
| [`encode-knowledge-into-repo.md`](./encode-knowledge-into-repo.md) | Durable knowledge still lives in chat, tickets, or people's heads and a fresh session keeps re-discovering it. Routes that knowledge into the right repo doc. |
| [`observability-feedback-loop.md`](./observability-feedback-loop.md) | Debugging is slow or an agent claims success without runtime evidence. Sets up a query -> reason -> rerun loop over logs/metrics/traces. |
| [`browser-validation-loop.md`](./browser-validation-loop.md) | UI work depends on real runtime interaction (DOM, console, network) and a unit test cannot cover it. Drives a browser via the Playwright MCP tools. |

## How to use a SOP

1. Match the SOP to your current bottleneck (see the table above).
2. Run the SOP's checklist to set up the missing artifact or loop.
3. Encode the resulting durable rules back into the repo doc the SOP points to,
   so the next session inherits them.
4. When a repeated review comment or failure mode appears, convert it into a
   mechanical check wired into `./init.sh` / `./init.ps1` — do not leave it as a
   remembered rule.

> Note: the layered-domain-architecture remediation procedure is **not** an SOP
> here. When a layer/dependency violation is actually being remediated, that note
> lives under `docs/design/` (see the Change Checklist in `docs/ARCHITECTURE.md`).
