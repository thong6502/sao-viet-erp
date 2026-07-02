---
name: svn-build-module
description: >-
  build module, build phân hệ, làm cả phân hệ, run Kinh doanh, run a whole
  module, dựng nguyên phân hệ. Use to build an entire SVN module by launching
  the module-build workflow (spec → plan → build → back-fill, cross-module
  aware). Not for a single screen — use svn-build-screen.
license: MIT
---

# svn-build-module — build a whole phân hệ (workflow-backed, one-shot)

Building a whole module is implemented by the **`module-build` workflow**
(`.claude/workflows/module-build.mjs`), a deterministic multi-agent orchestrator.
This skill's job is to launch it correctly and honor the cross-module rules.

Trigger: "làm phân hệ X", "build the <module> module", "chạy Kinh doanh",
"dựng nguyên phân hệ <...>".

## How to run
Launch the workflow with the module name as args (multi-agent, opt-in — it can
spawn many agents and cost tokens; that is expected for a full module):

```
Workflow({ name: 'module-build', args: { module: 'Kinh doanh' } })
```

Optionally pass `{ module, layer: 'backend' | 'frontend' }` to limit scope
(default: both). The workflow reads §41 of `docs/DOMAIN_NHA_MAY_IN.md` to resolve
the module's screens + dependency order — nothing is hardcoded, so the same
workflow builds any module in the map.

## Run mode: AUTONOMOUS (one-shot)
Runs end-to-end without approval gates; reports once at the end. This is a
**deliberate, scoped exception** to the global show-before-write rule (the rule
still applies everywhere else). Stops early only on a genuine **strategic
blocker** (a P0/schema conflict with no compliant option).

## What the workflow does (5 phases)
1. **Resolve** — read §41 → screens + dependency order + spec numbers; read the
   Context Map for seams this module unblocks (back-fill list).
2. **Spec** — per screen, in parallel: research → reconcile → *independent*
   adversarial verify → write `docs/product-specs/spec-NN-<screen>.md`.
3. **Plan** — specs → `feature_list.json`; split features into **build-now** vs
   **deferred (needs module X)**; deferred ones become seams in the Context Map.
4. **Build** — sequential by dependency: BE + FE → `./init.ps1` → Playwright
   validate → bounded retry (escalates as a blocker, never loops forever).
5. **Back-fill** — Parallel Change: close every seam this module unblocks
   (skip-test → green, delete stub, mark ledger entry ✅).

## Cross-module rule (the reusable part)
A feature that depends on a not-yet-built module is **not built now** — instead
the workflow builds a clean **seam** (per `docs/CROSS_MODULE_LINKS.md`
conventions: `SEAM-NN` marker + explicit stub + skip-test + Context Map entry)
so a later module build can back-fill it additively. See
[../../../docs/CROSS_MODULE_LINKS.md](../../../docs/CROSS_MODULE_LINKS.md).

## Guardrails
- **Orchestration only** — real work happens inside the workflow's subagents and
  the existing GAN loop; this skill just launches and reports.
- **Dependency order is mandatory** — never build a screen before its
  dependencies; never parallelize half-built screens (AGENTS.md "one feature in
  flight").
- **Context Map is an index, code is the source of truth** — never mark a seam
  closed without its skip-test going green and its stub removed.
- **No commit/push** unless the human asks. Truthful reporting: failures are
  reported as failures; `validated:false` when the app can't be driven.
