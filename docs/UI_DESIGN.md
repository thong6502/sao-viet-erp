# UI_DESIGN.md

Single source of truth for the **visual language + how a real ERP screen is built and
behaves**. Two jobs:

- 🔨 **Generator** builds every screen to this document (tokens, screen archetypes,
  required states, cross-module panels) — read it before writing frontend code.
- 🔍 **Evaluator** scores **design quality + usability** against it and against the
  reference-quality bar (`docs/design-assets/`). Drift = lost points + rebuild.

> **North star: an ERP that is EXCELLENT and EASY TO USE.** The reference screenshots in
> `docs/design-assets/` show the *quality level* to reach — **calibration, not a layout to
> clone**. Match the depth, connectedness, and polish; do not pixel-copy. Use judgment.

---

## PART A — Design Tokens (the visual language)

Defined ONCE as CSS custom properties in the frontend theme; never hard-code raw values.
Palette = warm "paper + ink pigment" with a single rust accent.

### Color
| Token | Value | Use |
|-------|-------|-----|
| `--paper` | `#f5f1e8` | App background (warm paper) |
| `--canvas` | `#fbfaf5` | Cards, panels, tables, modals |
| `--ink` | `#14130f` | Primary text; dark sidebar; primary button |
| `--ash` | `#6b665b` | Secondary / hint text |
| `--ash-2` | `#918b7e` | Tertiary / placeholder |
| `--rust` | `#c5400a` | Primary action, link, accent, current/selected |
| `--rule` | `#d8d2c0` | Borders (`--rule-soft #e8e3d3` cards · `--rule-hair #efebde` row lines) |
| `--moss` | `#2f5d3a` | Success / done / on-time |
| `--amber` | `#9c7714` | Waiting / warning / in-progress |
| `--signal` | `#8a1f1f` | Destructive / error / overdue |
| `--steel` | `#4a5560` | Neutral / info |

Each semantic color ships a `-soft` tint (badge/status bg) and a `-deep` shade (text on
tint). Use **exactly one accent (rust)**. Light mode only.

### Typography
- `--ff-sans`: `'Geist','Inter',system-ui,sans-serif` (body/UI)
- `--ff-mono`: `'JetBrains Mono',ui-monospace,monospace` — **all numbers, codes, and
  micro-labels** (mono makes money/quantities scan cleanly).
- Base 14px. Scale: micro 10–11 · sm 12–13 · base 14 · lg 15–17 · xl–3xl 20/24/32 · page `<h1>` 26/600.
- **Signature label ("xs micro-upper"):** 10px, weight 600, mono, UPPERCASE, letter-spacing
  .14em, color ash — every table column header, KPI label, section eyebrow. KPI value = 28px/500.

### Spacing / Radius / Elevation / Motion
- Spacing: 4px scale (`4,8,12,16,20,24,28,32,40,48,64,80,96`). Grid gap 12px, card pad 20px, content pad `28px 32px`.
- Radius: sm 4px (badges/inputs) · md 6px (buttons) · lg 10px (cards/tables/modals) · pill 9999px.
- **Flat by default** — separate surfaces with hairlines + bg shifts, not shadows. Reserve shadow for popovers (`0 4px 12px rgba(20,19,15,.06)`) and modals/slide-overs (`0 14px 34px rgba(20,19,15,.17)`).
- Motion: fast ~120ms (hover) · base ~140ms (buttons/color). Honor `prefers-reduced-motion`.

---

## PART B — Screen Archetypes (how an ERP screen is structured)

Almost every ERP screen is one of two archetypes. Build to these — do NOT emit a bare CRUD form.

### B1 · List-Report (the entry screen for every module)
A full-page list a user scans and acts on. Required anatomy:
- **KPI header strip** — 3–5 summary cards (e.g. total count, this-month, overdue, avg value)
  in mono numbers with a trend hint. Gives instant situational awareness.
- **Search** (by the fields a user actually knows: name / code / MST / person) **+ filter
  tabs/chips** (status, segment) with a visible active-filter indicator.
- **Table** — first column is a **human-readable identity** (name + code/MST as sub-line),
  never a raw ID. Sortable headers; right-aligned mono numbers; **status badges**; row tags;
  pagination when >25 rows; row → opens the Object-Page. Bottom rule per row (no cell grid, no zebra).
- **Primary action** (e.g. "+ Tạo …") top-right.
- All **required states** (Part D).

### B2 · Object-Page / Detail (slide-over or full page)
The rich detail view — this is where "excellent + connected" is won. Required anatomy:
- **Identity header** — name + code + key status badge + a few key facts (MST, since-date,
  lifetime value, người phụ trách). Optional score/gauge where meaningful (payment reputation…).
- **Action toolbar** — ≥3 *contextual* actions the user actually needs here (Gọi · Email ·
  Zalo · Tạo báo giá · Lịch hẹn · In phiếu · YC thu tiền · Báo hỏng…), not just Edit/Delete.
- **Tabs** for related history when volume warrants (Dashboard · Lịch sử mua hàng · Lịch sử báo giá…).
- **Cross-module related panels** (Part C) — the defining requirement.
- **Analytics where data supports it** — bar chart (revenue 12 months), donut (product mix),
  heatmap (order frequency), gauge (reputation), top-N lists. Numbers mono. Don't force charts
  onto data that doesn't warrant them (judgment).
- **Export** where relevant (Xuất Excel for lists; branded PDF for documents — Part E).

> Use a **slide-over panel** for quick drill-in from a list (with ▲/▼ to page through
> siblings + ✕ to close); use a **full page** when content is heavy/multi-section.

---

## PART C — Cross-Module Related Panels (the "connected ERP" requirement)

A screen is a **hub of information**, not an island. Every Object-Page shows **live related
data from other modules** with **drill-through links**. Examples (build the panel; wire it
per Part F):

- **Đơn hàng** → source **Báo giá** (link) · **Lệnh sản xuất** card (máy, BOM, tiến độ,
  badge "Đang SX", "Mở LSX →") · **Giao hàng** · **Công nợ**.
- **Tính giá** → **imposition/proof** visual + tính-ra sản lượng (tờ in, hao hụt, lượt-tờ,
  giờ máy) · **Báo giá liên quan**.
- **Khách hàng** → **lịch sử mua hàng** · **lịch sử báo giá** · công nợ · doanh số 12T.

**Honesty rule (hard):** if the target module isn't built yet, the panel shows an explicit
**"chờ phân hệ X"** placeholder (a seam — see Part F). **Never fabricate numbers.** A fake
value is worse than an honest gap.

---

## PART D — Required States (mandatory on every data view)

| State | Requirement |
|-------|-------------|
| **Empty** | First-run / no-data / no-results, each distinct: one-line reason + a next action ("Tạo … đầu tiên" / "Xoá bộ lọc"). Never a blank area. |
| **Loading** | Skeleton for structured content (tables/cards/dashboard); spinner only for discrete blocking actions (save/upload); layout must not jump. |
| **Success** | Result clearly shown; transient confirmations announced (`aria-live`). Prefer inline update over full reload. |
| **Error** | Plain-language message beside the field/section, states the cause + how to fix, keeps the user's input, uses `--signal` + icon (not color alone). No raw stack/JSON. |
| **Retry / blocked** | Recoverable errors expose retry without duplicate side-effects; blocked states explain the block + fallback. |

---

## PART E — Document Export (branded)

Any document a user sends out (Báo giá, Đơn hàng, Phiếu giao, Hóa đơn) exports to a
**branded PDF**:
- **Letterhead Sao Việt Nhật**: logo + company name + address + **MST** + phone/hotline +
  email/website — **pulled from a single "Hồ sơ công ty" config (master data), not hard-coded**.
- **Tiếng Việt is sufficient** (bilingual VN/EN optional, not required).
- Proper document table (STT · mã hàng · mô tả · kích thước · ĐVT · SL · đơn giá chưa VAT ·
  ghi chú), a **Ghi chú block** (hiệu lực, vận chuyển, VAT%, thời gian giao), VAT line + total.
- Print-buildup internals (số con/khổ, số tờ, số bản kẽm, bù hao) stay **hidden** on
  customer-facing documents.

---

## PART F — Wiring (how panels & pickers get their data)

- **Pick, don't type:** every reference to another entity (khách/SP/giá/chứng-từ-nguồn) is a
  **searchable picker** returning a real record's id — **zero free-text ID inputs**. On select,
  auto-fill master fields.
- **Same-module dependency exists → wire it now** (Báo giá picks a real Khách hàng, pulls a
  real Tính giá result). Do not leave same-module links as manual inputs.
- **Cross-module dependency not built → seam:** render the related panel with an honest
  "chờ phân hệ X" state, register the seam per `docs/CROSS_MODULE_LINKS.md`; it back-fills real
  data when that module lands.
- **Snapshot on commit:** when a document is finalized, copy master values (price, norms,
  address) into it — later master edits must not change historical documents.

---

## PART G — Components & Accessibility (conventions)

- **Button:** primary (ink) · accent (rust CTA) · secondary (canvas+border) · ghost · link ·
  icon. Every interactive element defines default/hover/focus/active/disabled + loading where it acts.
- **Field:** shared `.input`; pair every field with a real `<label>` (top-aligned); no
  placeholder-as-label. Inline validation **on blur** ("reward early, punish late").
- **Modal / slide-over:** scrim + shadow + radius 10px, sticky header with ✕, `role="dialog"`
  + `aria-modal`, **Esc + scrim close, focus trapped and restored to trigger**.
- **Table / Badge / KPI card / Tabs / Toolbar:** reuse shared classes; status→color via Part A.
- **Accessibility (target WCAG 2.1 AA):** visible focus ring (≥3:1) on every control; full
  keyboard operability + hotkeys for high-frequency entry; `aria-current` on active nav; live
  region for toasts; contrast ≥4.5:1 (≥3:1 large/UI).

---

## References
- **Reference-quality screenshots** (the bar to reach): [design-assets/](./design-assets/).
- Product intent: [PRODUCT_SENSE.md](./PRODUCT_SENSE.md) · Scoring: [EVALUATION.md](./EVALUATION.md).
- Cross-module wiring: [CROSS_MODULE_LINKS.md](./CROSS_MODULE_LINKS.md).
- Browser validation SOP: [sops/browser-validation-loop.md](./sops/browser-validation-loop.md).
- Figma MCP is available; when a frame is wired, resolve tokens with `get_variable_defs` and reconcile here.
