# FACEATTEND — Frontend Design System (R4 Foundation)

Target: professional attendance-management product. Ink-navy depth, frosted
surfaces where useful, restrained cyan/teal accents, semantic states, system
fonts (no remote fonts — interface renders offline). Neo-brutalist `brutal-*`
styles remain for unmigrated screens; new work uses `fa-*` tokens/components.

## 1. Principles

Density over decoration; every surface earns its place. Color carries meaning
(status) or affordance (action), never mere ornament. Keyboard and touch paths
are first-class. Motion is feedback, not spectacle — and always optional via
`prefers-reduced-motion`.

## 2. Color roles (verified pairs in §10)

| Token | Value | Role |
|---|---|---|
| `--fa-bg` | `#0B1220` | page background |
| `--fa-surface` | `#111B2D` | panels, header, sidebar |
| `--fa-surface-elev` | `#18253A` | raised cards, popovers |
| `--fa-text` | `#F1F5FC` | primary text (17.1:1 on bg) |
| `--fa-text-muted` | `#A8B5CA` | secondary text (9.0:1 on bg) |
| `--fa-accent` | `#75B7FF` | primary actions, links, highlights |
| `--fa-accent-2` | `#5EDBC6` | secondary highlights |
| `--fa-ok` | `#52D6A0` | success |
| `--fa-warn` | `#F5C66B` | warning |
| `--fa-err` | `#FF7887` | danger/error |
| `--fa-info` | `#75B7FF` | informational (accent reuse) |
| `--fa-ink` | `#0B1220` | text on bright fills (buttons, badges) |
| `--fa-border` | `rgba(148,178,255,0.16)` | hairlines |
| `--fa-ring` | `rgba(117,183,255,0.65)` | focus rings |

Rule: bright fills (`accent/ok/warn/err`) always pair with `--fa-ink` text
(measured 7.4–11.7:1). Never white-on-danger (measured 2.53:1 — fails).

## 3. Typography

System stack only:
`font-family: "Inter", "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif;`
mono: `ui-monospace, "Cascadia Mono", "Roboto Mono", Menlo, Consolas, monospace`.
Scale: `--fa-t-xs:11px; --fa-t-sm:13px; --fa-t-md:15px; --fa-t-lg:20px; --fa-t-xl:26px`.
Weights 400/600/800. Body 15px, headings 20–26px extrabold uppercase only for
brand/product labels (not body copy).

## 4. Spacing and grid

4px base: `--fa-s-1:4px; --fa-s-2:8px; --fa-s-3:12px; --fa-s-4:16px; --fa-s-6:24px; --fa-s-8:32px`.
App shell: max-width 1200px, page padding 16–24px, card gaps 16px. Sidebar
256px ≥1024px viewports, top bar below that (existing responsive pattern kept).

## 5. Radii, borders, shadows, glass

`--fa-r-sm:8px; --fa-r-md:12px; --fa-r-lg:16px`. Borders 1px `var(--fa-border)`.
Depth: `--fa-shadow-1: 0 1px 2px rgba(2,6,16,.5); --fa-shadow-2: 0 8px 28px rgba(2,6,16,.55)`.
Glass (`.fa-card-glass`, status panel, modal backdrop): translucent
`rgba(24,37,58,.72)` + `backdrop-filter: blur(14px) saturate(1.2)` with a
fully-opaque `@supports not (backdrop-filter: blur(1px))` fallback
(`#18253A`).

## 6. Breakpoints

`--fa-bp-sm:640px; --fa-bp-md:900px; --fa-bp-lg:1200px`. Narrow: single column,
horizontal nav scroll, tables scroll within cards (no page-level horizontal
overflow). Touch targets ≥40px.

## 7. Interaction states

Buttons: default → hover (brightness +1px lift) → `:focus-visible` ring
(2px `--fa-ring`, offset 2px) → active (press) → disabled (`opacity .45`, no
pointer) → loading (spinner + `aria-busy`, keeps size). Inputs: label above,
hint below, error text + `aria-invalid` + `aria-describedby`. Status text
always pairs icon/shape with words (never color alone).

## 8. Motion

`--fa-t-fast:120ms; --fa-t-med:200ms; ease: cubic-bezier(.2,.7,.2,1)`.
`@media (prefers-reduced-motion: reduce)`: all transitions/animations ≤1ms.
No motion on camera/scanner surfaces beyond the detection overlay itself.

## 9. Layering

`--fa-z-nav:10; --fa-z-pop:30; --fa-z-backdrop:40; --fa-z-modal:50`.
Modal (`FaModalFrame`, R5): Tab/Shift+Tab cycle is trapped inside the dialog;
backdrop click cancels (non-destructive) or is inert for confirm-critical
dialogs; Escape cancels; focus moves into the dialog on open and restores to
the opener on close; background scroll locks while open. Behavior is
statically reviewed (no browser tooling); screen-reader verification pending.

## 10. Accessibility expectations (verified where noted)

Computed WCAG 2.1 ratios (relative-luminance math, this phase): text/bg 17.1,
muted/bg 9.0, muted/surface 8.3, accent-text/bg 8.9, ink-on-accent 8.9,
ink-on-secondary 11.1, ink-on-success 10.2, ink-on-warning 11.7, ink-on-danger
7.4 — all ≥4.5. White-on-danger 2.5 — banned (see §2). Keyboard: all actions
reachable, focus ring always visible, inputs labeled, icon-only buttons named,
statuses redundant-coded, dialogs follow §9. Screen-reader spot-checks and a
two-browser pass remain for the UI phase (no tooling in R4 — recorded, not
claimed).

## 11. Component conventions

`frontend/src/fa/`: `tokens.css` (custom properties + base classes incl.
`fa-table`, `fa-video-frame`, `fa-log`, glass + reduced-motion rules),
`request.js` (shared `api`/auth-header/session/snapshot helpers),
`primitives.jsx` (`FaButton`, `FaCard`, `FaStatusIndicator`, `FaFormField`,
`FaSectionHeader`, `FaModalFrame` with full keyboard trap). Screens live in
`frontend/src/screens/` (one file per screen, props-driven, never fetch
directly — they import `api` from `../fa/request`). Props: stable, minimal,
sensible defaults. React 18 compatible (no experimental APIs).

## 12. Extension rules

New colors/spacing must enter as tokens with a measured contrast note; no raw
hex in new JSX. New components reuse primitives before inventing variants.
Any deviation (e.g., a legacy screen keeps brutal styles) is documented in
the phase report, not silently mixed in.
