# UI_DESIGN.md

> **PLACEHOLDER TEMPLATE** — the app source does not exist yet. This is the project's
> visual-language store; every value marked `<PLACEHOLDER>` must be filled when the
> real product, brand, or design system lands. The structure below is the contract
> agents follow until then. Code health stays `../init.sh` / `../init.ps1`; this file
> is the *design* contract, not a verification command.

This is the single source of truth for the **visual language** — colors, type,
spacing, component conventions, and required UI states. It is deliberately separate
from [ARCHITECTURE.md](./ARCHITECTURE.md), which owns *code structure* (layers,
domains, dependency rules). When a question is "how should this look / behave on
screen", the answer lives here. When it is "where does this code go", that is
ARCHITECTURE.

**Role in the GAN loop:**

- 🔨 **Generator** (`../.claude/skills/generate/SKILL.md`) builds every feature *to
  this document* — it must read the relevant tokens, component conventions, and the
  Required UI States before generating frontend code.
- 🔍 **Evaluator** (`../.claude/skills/browser-validate/SKILL.md`) scores the
  **design quality** criterion *against this document* (see
  [EVALUATION.md](./EVALUATION.md)). A feature whose UI drifts from these tokens,
  conventions, or required states should lose points on design quality and be fed
  back for a rebuild.

> **Figma MCP is available in this environment.** Design context can be pulled in
> directly rather than transcribed by hand. When a Figma file/frame URL is known,
> resolve tokens with `get_variable_defs`, capture a frame with `get_screenshot`,
> and read structure with `get_metadata` / `get_design_context`, then record the
> resulting values in the tables below. See [References](#references).

---

## Design Tokens

Tokens are the atomic, named values. Define them ONCE here, expose them as the
frontend's source of truth (e.g. CSS custom properties / a theme object —
`<PLACEHOLDER token mechanism>`), and never hard-code raw values in components.

### Color

| Token | Value | Use |
|-------|-------|-----|
| `--color-bg` | `<PLACEHOLDER>` | App background |
| `--color-surface` | `<PLACEHOLDER>` | Cards, panels, modals |
| `--color-text` | `<PLACEHOLDER>` | Primary text |
| `--color-text-muted` | `<PLACEHOLDER>` | Secondary / hint text |
| `--color-primary` | `<PLACEHOLDER>` | Primary action, focus accent |
| `--color-primary-contrast` | `<PLACEHOLDER>` | Text/icon on primary |
| `--color-border` | `<PLACEHOLDER>` | Dividers, input borders |
| `--color-success` | `<PLACEHOLDER>` | Success state |
| `--color-warning` | `<PLACEHOLDER>` | Warning state |
| `--color-danger` | `<PLACEHOLDER>` | Destructive / error state |
| `--color-focus-ring` | `<PLACEHOLDER>` | Keyboard focus outline |

> Every text/background pair must meet the contrast bar in [Accessibility](#accessibility).
> Define a dark-mode mapping or state `<PLACEHOLDER: light only>` here so it is a
> decision, not an accident.

### Typography

| Token | Value | Use |
|-------|-------|-----|
| `--font-sans` | `<PLACEHOLDER font stack>` | Body / UI |
| `--font-mono` | `<PLACEHOLDER font stack>` | Code, data |
| `--font-weight-regular` / `-medium` / `-bold` | `<PLACEHOLDER>` | Weights in use |

Type scale (`<PLACEHOLDER base size>` base, `<PLACEHOLDER ratio>` ratio):

| Step | Size | Line height | Typical use |
|------|------|-------------|-------------|
| `xs` | `<PLACEHOLDER>` | `<PLACEHOLDER>` | Caption / meta |
| `sm` | `<PLACEHOLDER>` | `<PLACEHOLDER>` | Secondary text |
| `base` | `<PLACEHOLDER>` | `<PLACEHOLDER>` | Body |
| `lg` | `<PLACEHOLDER>` | `<PLACEHOLDER>` | Lead / subheading |
| `xl`–`3xl` | `<PLACEHOLDER>` | `<PLACEHOLDER>` | Headings |

### Spacing

Single spacing scale (`<PLACEHOLDER base unit>`, e.g. 4px) — use scale steps, not
arbitrary pixels.

| Token | Value |
|-------|-------|
| `--space-1` … `--space-8` | `<PLACEHOLDER scale: 4, 8, 12, 16, 24, 32, 48, 64 …>` |

### Radius

| Token | Value | Use |
|-------|-------|-----|
| `--radius-sm` | `<PLACEHOLDER>` | Inputs, small controls |
| `--radius-md` | `<PLACEHOLDER>` | Cards, buttons |
| `--radius-lg` | `<PLACEHOLDER>` | Modals, large surfaces |
| `--radius-full` | `<PLACEHOLDER>` | Pills, avatars |

### Shadow / Elevation

| Token | Value | Use |
|-------|-------|-----|
| `--shadow-sm` | `<PLACEHOLDER>` | Resting cards |
| `--shadow-md` | `<PLACEHOLDER>` | Popovers, raised controls |
| `--shadow-lg` | `<PLACEHOLDER>` | Modals, overlays |

### Motion

| Token | Value | Use |
|-------|-------|-----|
| `--duration-fast` / `--duration-base` | `<PLACEHOLDER>` | Transitions |
| `--easing-standard` | `<PLACEHOLDER>` | Default easing |

> Respect `prefers-reduced-motion`: disable or shorten non-essential motion.

---

## Components

Conventions every component honors. Build with tokens above; do not invent new
raw values. Each interactive component must define all of: **default, hover, focus
(visible ring), active, disabled**, plus its loading/error behavior where it acts.

### Button

- Variants: `<PLACEHOLDER: primary / secondary / ghost / danger>`.
- Sizes: `<PLACEHOLDER: sm / md / lg>`; padding from the spacing scale, radius
  `--radius-md`.
- Disabled is visually distinct AND `disabled`/`aria-disabled`. Async actions show
  an inline loading state (see Required UI States) and stay non-re-triggerable.
- Destructive actions use `--color-danger` and are never the lone default focus.

### Input / Field

- Always paired with a `<label>` (visible or `aria-label`); placeholder is not a label.
- States: default, focus (`--color-focus-ring`), error (`--color-danger` + message),
  disabled, read-only.
- Validation message sits adjacent to the field and is linked via
  `aria-describedby` / `aria-invalid`.

### Form

- One column by default; group related fields; primary action bottom-right
  (`<PLACEHOLDER per layout convention>`).
- Submit disabled or shows loading while in flight; never double-submit.
- Field-level errors inline; a form-level error summary appears on submit failure
  and moves focus to itself.

### Card

- Surface `--color-surface`, `--radius-md`, `--shadow-sm`; consistent internal
  padding from the spacing scale. Title → body → actions order.

### Modal / Dialog

- Overlay scrim, surface `--shadow-lg`, `--radius-lg`. Focus is **trapped** inside,
  `Esc` closes, focus returns to the trigger on close. `role="dialog"` +
  `aria-modal="true"` + labelled title. Background is inert/non-scrolling.

### Navigation

- Pattern: `<PLACEHOLDER: top bar / sidebar / tabs>`. Current location is clearly
  marked (`aria-current`). Targets meet the minimum hit size in
  [Accessibility](#accessibility).

> When a component originates in Figma, capture its variants/states with the Figma
> MCP (`get_metadata` for structure, `get_variable_defs` for the tokens it binds)
> and reconcile them with the tables above rather than guessing.

---

## Required UI States

**Mandatory.** Any view that loads data or runs an action MUST handle every state
below. The 🔍 Evaluator exercises these via the browser loop
([sops/browser-validation-loop.md](./sops/browser-validation-loop.md)); a missing
state is a design-quality failure, not a nice-to-have.

| State | Requirement |
|-------|-------------|
| **Empty** | First-run / no-data view with a one-line explanation and a next action — never a blank region. `<PLACEHOLDER copy>` |
| **Loading** | Visible progress (spinner / skeleton) within `<PLACEHOLDER>` ms; layout must not jump when content arrives. |
| **Success** | The intended result is clearly shown; transient confirmations (e.g. toast) are announced to assistive tech. |
| **Error** | Plain-language message (no raw stack/JSON), the cause if known, and what the user can do. Uses `--color-danger`. No silent failure. |
| **Retry** | Recoverable errors expose an explicit retry; retry shows its own loading state and does not duplicate side effects. |

These five are the canonical states a golden journey must walk. Map each to an
observable assertion in the matching product spec's Acceptance Criteria
([product-specs/_TEMPLATE.md](./product-specs/_TEMPLATE.md)).

---

## Layout & Navigation

- **Grid / max width:** `<PLACEHOLDER: container max-width, columns, gutter>`.
- **Breakpoints:** `<PLACEHOLDER: sm / md / lg / xl>`; mobile-first — components
  reflow, never overflow horizontally.
- **App shell:** `<PLACEHOLDER: header + content + optional sidebar>`; persistent
  regions vs per-route content defined here.
- **Primary navigation:** `<PLACEHOLDER>` (see Navigation component). Back/forward
  and deep-linkable routes behave predictably; current route is reflected in nav.
- **Density / rhythm:** consistent vertical rhythm from the spacing scale; align to
  the grid rather than ad hoc offsets.

---

## Accessibility

Baseline target: **`<PLACEHOLDER: e.g. WCAG 2.1 AA>`**. Non-negotiable items:

- **Contrast:** text ≥ 4.5:1 (≥ 3:1 for large text/UI glyphs) for every token pair.
- **Keyboard:** every interactive element reachable and operable by keyboard in a
  logical order; a **visible** focus ring (`--color-focus-ring`) is always present.
- **Focus management:** modals trap focus and restore it; route changes move focus
  to the new view's heading.
- **Semantics:** real landmarks/headings/lists; controls have accessible names;
  state conveyed by ARIA, not color alone.
- **Live regions:** async success/error is announced (`aria-live`) so it is not
  vision-only.
- **Targets:** minimum hit area `<PLACEHOLDER: e.g. 44×44px>`.
- **Motion:** honor `prefers-reduced-motion`.

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
