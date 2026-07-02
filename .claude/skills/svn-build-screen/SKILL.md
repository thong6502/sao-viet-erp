---
name: svn-build-screen
description: >-
  build screen, grounded screen spec, print-domain screen, research UI for a
  module, màn hình mới, làm màn hình, spec màn hình in ấn. Use to research +
  author a reality-grounded screen spec, then autonomously drive it through the
  GAN loop to a finished screen. Not for one-off edits.
license: MIT
---

# svn-build-screen — grounded screen builder (autonomous, one-shot)

Turns a screen idea into a **reality-grounded product spec** (fields / buttons /
flow / validation), then drives it end-to-end through the existing 3-role GAN
loop (`plan → generate → gan-loop`) to a finished, self-verified screen.

Trigger when the human says: "làm màn hình X", "build the <screen> screen",
"dựng màn <...>", "research màn <...> rồi làm".

## Run mode: AUTONOMOUS (one-shot)
- **Run the whole chain without stopping. Deliver only the final result.**
- This workflow is a **deliberate, scoped exception** to the global
  "show-before-write" rule — write files as needed, do not pause for approval
  mid-run. (The global rule still applies everywhere else.)
- The only reason to stop early is a genuine **strategic blocker** the agent
  cannot resolve safely (e.g. the spec would violate a P0 invariant with no
  compliant option, or a needed schema change is ambiguous). Then stop, state
  the blocker, and ask — do not guess.
- Downstream `plan` normally stops to ask a detail level. In autonomous mode,
  **auto-answer it with "Full per-screen acceptance criteria"** (documented
  default) so the run does not stall; note that choice in the final report.

## Inputs to read first
1. `docs/DOMAIN_NHA_MAY_IN.md` — print-domain source of truth (the § for the
   relevant phân hệ/màn). Primary grounding; web research only fills gaps.
2. `docs/product-specs/index.md` + `_TEMPLATE.md` — spec catalog and shape.
3. `docs/DB_SCHEMA.md` — existing tables/columns the screen must respect, incl.
   P0 invariants: snapshot price copy-on-write, Order 1─n Job, PrintForm hidden
   from Sale.
4. `docs/PRODUCT_SENSE.md` + `docs/UI_DESIGN.md` — product bar + design system.

## The 5 steps

### ① Research (grounding) — scale to how "print-specific" the screen is
- Light (generic CRUD, e.g. Khách hàng): skip web; use domain doc + DB schema.
- Heavy (print core, e.g. Tính giá / Báo giá): WebSearch/WebFetch real print
  MIS/ERP (Label Traxx, PrintVis, Tharstern, Optimus, EFI Pace, PrintSmith,
  Avanti) for screen anatomy — what's shown, inputs, actions, flow.
- Record findings + sources in scratchpad; mark unverified as "suy ra".

### ② Reconcile with the domain
Cross-check the researched anatomy against `DOMAIN_NHA_MAY_IN.md`. Drop fields
that don't fit SVN; add print-specific ones the generic tools miss.

### ③ Adversarial verify (independent subagent)
Spawn a subagent to REFUTE the draft screen: which field is missing/redundant,
does the flow violate print business logic, does it break a P0 invariant? Fix
what survives. Do not skip for print-core screens.

### ④ Produce the screen spec (write directly, no approval gate)
Write the spec in `_TEMPLATE.md` shape — Goal / Screens / Features /
Logic-flow / System statuses / Edge cases / Acceptance criteria (observable) /
Out-of-scope / Failure states — plus an explicit **Screen anatomy** table:

| Purpose | Data shown | Inputs | Actions/buttons | Flow | Validation |

Save to `docs/product-specs/spec-NN-<screen>.md` and add it to `index.md`.

### ⑤ Drive the GAN loop to done (do NOT hand back — run it)
Run, in order, without stopping:
- 🧠 `plan` — spec → `feature_list.json` (auto-answer its detail menu with
  "Full per-screen acceptance criteria").
- 🔨 `generate` — build ONE feature, verify with `./init.sh` / `./init.ps1`.
- 🔍 `gan-loop` + `browser-validate` — build → independent score → rebuild
  until each feature passes threshold or budget is spent.
Iterate every feature in dependency order until the spec is done.

## Final report (the only human touchpoint)
When the whole screen is done (or blocked), report once: spec file written,
feat count + per-feature status/evidence, browser-validate scores, the
auto-chosen plan detail level, any P0/schema flags, and what (if anything)
remains. Do NOT commit or push unless the human asks.

## Guardrails
- **Autonomous, but truthful:** never mark a feature done without green
  `./init.sh` / `./init.ps1` and a passing independent score. Report failures
  as failures.
- **Domain doc is the source of truth;** web research fills gaps, never
  overrides SVN business rules. Mark unverified claims explicitly.
- **Respect P0 invariants & existing schema** (`DB_SCHEMA.md`). A required
  schema change is a strategic blocker — stop and ask, don't silently assume.
- **Stay in scope:** touch only files for the screen being built.
- Grounding depth is proportional: don't burn web research on generic CRUD.
