# DESIGN.md

> **VISUAL-LANGUAGE STORE.** Unlike a blank template, the app source **does exist** —
> an HTML + vanilla-JS + CSS mockup. Every concrete value below is extracted from the
> live stylesheet `../assets/css/style.css` (tokens in `:root`) and `../assets/js/layout.js`.
> Values still marked `<PLACEHOLDER>` are genuinely undecided (brand/Figma/dark-mode) or
> point at harness files not yet created. Reference page for "what good looks like":
> `../pages/02-bao-gia.html`.

This is the single source of truth for the **visual language** — colors, type,
spacing, component conventions, and required UI states. It is deliberately separate
from `ARCHITECTURE.md` (`<PLACEHOLDER — not created>`), which owns *code structure*.
When a question is "how should this look / behave on screen", the answer lives here.
When it is "where does this code go", that is ARCHITECTURE.

**Role in the GAN loop:**

- 🔨 **Generator** builds every feature *to this document* — it must read the relevant
  tokens, component conventions, and the Required UI States before generating frontend
  code. (Skill path: `<PLACEHOLDER — ../.claude/skills/generate/SKILL.md not created>`.)
- 🔍 **Evaluator** scores the **design quality** criterion *against this document*. A
  feature whose UI drifts from these tokens, conventions, or required states should lose
  points and be fed back for a rebuild. (Skill path: `<PLACEHOLDER — browser-validate not created>`.)

> **Figma MCP is available in this environment** but no Figma file is wired to this
> project yet. When a frame URL is known, resolve tokens with `get_variable_defs`,
> capture with `get_screenshot`, read structure with `get_metadata` /
> `get_design_context`, then record values in the tables below. See [References](#references).

---

## Design Tokens

Tokens are the atomic, named values. They are defined ONCE as **CSS custom properties
in `:root` (`../assets/css/style.css`)** and are the frontend's source of truth — never
hard-code raw values in components. The palette is warm "paper + ink pigment" with a
single rust accent.

### Color

| Token | Value | Use |
|-------|-------|-----|
| `--paper` (bg) | `#f5f1e8` | App background (warm paper) |
| `--canvas` (surface) | `#fbfaf5` | Cards, panels, tables, modals |
| `--ink` (text) | `#14130f` | Primary text; dark sidebar; primary button |
| `--ash` (text-muted) | `#6b665b` | Secondary / hint text |
| `--ash-2` | `#918b7e` | Tertiary text / placeholder |
| `--rust` (primary) | `#c5400a` | Primary action, link, accent, current/selected |
| `--paper` (primary-contrast) | `#f5f1e8` | Text/icon on rust (and on ink) |
| `--rule` (border) | `#d8d2c0` | Dividers, input borders (`--rule-soft #e8e3d3` cards, `--rule-hair #efebde` row lines) |
| `--moss` (success) | `#2f5d3a` | Success / done / sufficient |
| `--amber` (warning) | `#9c7714` | Waiting / warning |
| `--signal` (danger) | `#8a1f1f` | Destructive / error / overdue |
| `--ink` (focus-ring) | `#14130f` | ⚠️ No dedicated ring — focus currently = ink border + `outline:none` (see [Accessibility](#accessibility)) |

Each semantic color ships a `-soft` tint (badge/status background) and a `-deep` shade
(text on tint / filled-hover): rust `#e85a2a`/`#f4e2d6`/`#8a2d07` · moss `#dde8d8`/`#1f4127`
· amber `#f0e6c4` · signal `#efd5d5` · steel `#4a5560`/`#e0e5ea` (neutral/info).

> **Dark mode:** `<PLACEHOLDER — light only; no dark-mode mapping defined>`.
> Use **exactly one accent (rust)**. Legacy alias tokens (`--brand-yellow`, `--brand-blue`…)
> map to this palette so old pages don't break — **new code uses the tokens above only**.

### Typography

| Token | Value | Use |
|-------|-------|-----|
| `--ff-sans` | `'Geist', 'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif` | Body / UI |
| `--ff-mono` | `'JetBrains Mono', ui-monospace, 'SF Mono', monospace` | Column/section labels, codes, **all numbers** |
| weight regular / medium / bold | `400 / 500 / 600` | Body 400; headings & labels 500; emphasis 600 |

Type scale (**14px base**, custom scale — not a single modular ratio; headings weight 500,
slightly negative tracking):

| Step | Size | Line height | Typical use |
|------|------|-------------|-------------|
| `xs` (micro) | 10–11px | 1.4 | Mono uppercase labels (column/KPI/section), meta |
| `sm` | 12–13px | 1.4–1.5 | Caption, secondary, table cell, badge |
| `base` | 14px | 1.55 | Body |
| `lg` | 15–17px | 1.3–1.5 | Subtitle / H4–H5 |
| `xl–3xl` | 20 / 24 / 32px | 1.25 / 1.18 / 1.1 | Headings (H3→H1); page title 26px/600 |
| `display / hero` | 48 / 64px | 1.05 / 1.02 | Landing only |

> Signature label style ("xs micro-upper"): **10px, weight 600, mono, UPPERCASE,
> letter-spacing .14em, color ash** — used for every table column header, KPI label,
> and section eyebrow. KPI value = 28px/500; page `<h1>` = 26px/600.

### Spacing

Single 4px scale — use scale steps, not arbitrary pixels.

| Token | Value |
|-------|-------|
| `--sp-1 … --sp-24` | `4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 64, 80, 96` px |

Defaults: grid gap **12px**, card padding **20px**, content padding **28px 32px**.

### Radius

| Token | Value | Use |
|-------|-------|-----|
| `--r-2` (sm) | `4px` | Badges, inputs, small controls |
| `--r-3` (md) | `6px` | Buttons |
| `--r-5` (lg) | `10px` | Cards, tables, KPI, modals |
| `--r-pill` (full) | `9999px` | Pills, avatars, toggles |

### Shadow / Elevation

Design is **flat by default** — separate surfaces with hairlines + background shifts, not shadows.

| Token | Value | Use |
|-------|-------|-----|
| `--shadow-1` (sm) | `0 1px 0 var(--rule-soft)` | Resting hairline lift (rarely used) |
| `--shadow-4` (md) | `0 4px 12px rgba(20,19,15,0.06)` | Popovers, raised controls |
| (lg) | `0 14px 34px rgba(20,19,15,0.17)` | Modals, overlays |

### Motion

| Token | Value | Use |
|-------|-------|-----|
| `--duration-fast` | ~120ms | Row hover, small toggles |
| `--duration-base` | ~140ms | Buttons, color/border transitions (nav caret ~180ms) |
| `--easing-standard` | `ease` | Default easing |

> ⚠️ `prefers-reduced-motion` is **not yet honored** (`<PLACEHOLDER — to implement>`).

---

## Components

Conventions every component honors. Build with the tokens above; do not invent raw
values. Each interactive component should define: **default, hover, focus, active,
disabled**, plus loading/error where it acts. Reuse the shared classes — do not
hand-roll new variants.

### Button

- Variants: **primary** (ink/black bg, paper text) · **secondary** (canvas + rule border)
  · **accent** (rust — strong CTA) · **ghost** (transparent) · **link** (rust underlined)
  · **icon**.
- Sizes: **sm / md / lg**; padding from the spacing scale, radius `6px`. Icon `~14px` inside.
- Press feedback: 1px nudge + brief flash. ⚠️ Disabled state and async inline-loading are
  `<PLACEHOLDER — not standardized>` (mockup feeds back via toast, not spinner).
- Destructive actions use `--signal`.

### Input / Field

- Shared `.input`. Focus = **ink border** + canvas bg (no visible ring — a11y gap).
- States present: default, focus, read-only. ⚠️ Error / disabled styling and
  `<label>`-pairing are inconsistent (some fields are placeholder-only) — `<PLACEHOLDER — tighten>`.

### Form

- One column; primary action bottom-right. Submit/validation are **mock** (toast
  confirmations), not real async — `<PLACEHOLDER — real validation when backend lands>`.

### Card

- Surface `--canvas`, radius `10px`, border `--rule-soft`, **no shadow** (flat), padding `20px`.
  Order: title → body → actions. Optional left accent bar (`card-feature-*`) to categorize.

### Modal / Dialog

- `ERPInteract.showModal()`. Scrim overlay, surface shadow `0 14px 34px …`, radius `10px`,
  sticky header with **✕**, `role="dialog"` + `aria-modal="true"`, **Esc** + click-scrim close,
  `onPrimary` returning `false` keeps it open (validation).
- ⚠️ Focus is **not trapped** and **not restored** to the trigger on close — `<PLACEHOLDER — add focus trap>`.

### Navigation

- Pattern: **left sidebar** (collapsible sections, RBAC-filtered) + sticky **topbar**
  (breadcrumb, role switch, search, bell). Built by `layout.js` from a single `app-shell` div.
- Current item marked via `.active` class. ⚠️ `aria-current` not set — `<PLACEHOLDER>`.

### Table (project signature)

- Shared `.tbl` + `.table-wrap`: **bottom rule per row only — no cell grid, no zebra**.
  Two-tier cells (primary + `.sub-soft` secondary), ~6 full columns, never split sparse
  attributes into thin "—" columns. Header = xs mono-upper ash. Numbers right-aligned,
  tabular. (Exception: production stage sheets intentionally use an Excel grid.)

### Status / Badge

- `.badge-*` / `.status-*` pills on `-soft` backgrounds, 11px. Map status → color via §Color.

> When a component later originates in Figma, capture variants/states with the Figma MCP
> (`get_metadata` for structure, `get_variable_defs` for bound tokens) and reconcile with
> the tables above rather than guessing.

---

## Required UI States

**Mandatory.** Any view that loads data or runs an action MUST handle every state below.
Current mockup coverage is noted honestly — gaps are design-quality failures to close.

| State | Requirement | Mockup status |
|-------|-------------|---------------|
| **Empty** | First-run / no-data view with a one-line explanation + next action — never blank. | ⚠️ Partial — present on some pages (e.g. "no drafts" panels), missing on others. |
| **Loading** | Visible progress (spinner / skeleton); layout must not jump. | ⚠️ Largely absent — data is read synchronously from `localStorage`, so no async spinners. `<PLACEHOLDER for real backend>`. |
| **Success** | Result clearly shown; transient confirmations announced to assistive tech. | ✅ Toasts via `ERPInteract`; stack is `aria-live="polite"`. |
| **Error** | Plain-language message (no raw stack/JSON), cause, and recovery. Uses `--signal`. | ◐ Error toasts exist; no full error views/boundaries. |
| **Retry** | Recoverable errors expose explicit retry without duplicate side effects. | ⚠️ Not implemented (mock data never fails). |

These five are the canonical states a golden journey must walk. Map each to an observable
assertion in the matching product spec's Acceptance Criteria
(`<PLACEHOLDER — product-specs/_TEMPLATE.md not created>`).

---

## Layout & Navigation

- **Grid / max width:** content container **max-width 1480px**, padding **28px 32px**;
  internal grids `grid-2/-3/-4/-12` with **12px** gutter.
- **Breakpoints (desktop-first, max-width):** **1280 / 1024 / 768 / 480**px; components
  reflow (sidebar/topbar condense), never overflow horizontally.
- **App shell:** persistent **sidebar + topbar**, per-route **content**. A page declares
  only `<div id="app-shell" data-active data-title data-crumb>…</div>`; `layout.js` builds
  the shell, runs the RBAC guard, then fires `erp:ready` for page code.
- **Primary navigation:** left sidebar (see Navigation). Each page is its own HTML file;
  links navigate via `<a href>`; active route reflected in the sidebar.
- **Density / rhythm:** consistent vertical rhythm from the 4px scale; align to the grid.

---

## Accessibility

Baseline target: **`<PLACEHOLDER — not formally targeted (mockup); aim WCAG 2.1 AA>`**.
Current state, recorded honestly:

- **Contrast:** ✅ ink `#14130f` on paper `#f5f1e8` and semantic text on `-soft` tints are
  strong; verify every new pair to ≥ 4.5:1 (≥ 3:1 large text/UI).
- **Keyboard / focus ring:** ⚠️ **Gap** — controls use `outline:none`; focus shows only as a
  border-color change. Add a visible focus ring (`--rust` or `--ink`) for every interactive element.
- **Focus management:** ⚠️ **Gap** — modal does not trap or restore focus; route changes
  (full page loads) do not move focus to the new heading.
- **Semantics:** ◐ Real landmarks/headings exist; nav uses `.active` not `aria-current`;
  some inputs are placeholder-only (need real `<label>`).
- **Live regions:** ✅ Toast stack is `aria-live="polite"` so success/error is announced.
- **Targets:** `<PLACEHOLDER — define min hit area, e.g. 44×44px>`.
- **Motion:** ⚠️ `prefers-reduced-motion` not honored yet.

---

## References

Pointers to the design source(s) of truth. Keep links resolving to a real artifact;
mark unknowns as `<PLACEHOLDER>`.

- **Figma file / project:** `<PLACEHOLDER figma.com/design/... URL>` — pull tokens
  and frames via the Figma MCP (`get_variable_defs`, `get_screenshot`,
  `get_metadata`, `get_design_context`). Load the `/figma-use` skill before any
  write-back to Figma.
- **Mockups / exported flows:** `<PLACEHOLDER: links or files>`.
- **Local design assets** (logos, icons, exported screenshots, palettes):
  [design-assets/](./design-assets/) — commit static references here so agents and
  the Evaluator can read them offline.
- **Product intent behind the visuals:** [PRODUCT_SENSE.md](./PRODUCT_SENSE.md).
- **Code structure (not visual language):** [ARCHITECTURE.md](./ARCHITECTURE.md).
- **How design quality is scored:** [EVALUATION.md](./EVALUATION.md).
- **How states are validated in a real browser:**
  [sops/browser-validation-loop.md](./sops/browser-validation-loop.md).
