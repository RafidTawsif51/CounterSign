# Countersign frontend design system

This file is the source of truth for every screen in `frontend/`. Tokens live in `src/styles/globals.css` and must match this file. To see them rendered, run the dev server and open `/design-check` (a hidden route, not linked from the app).

If a design need is not covered here, add it here first, then build it.

## What it should feel like

Countersign runs a small AP team's weekly vendor payment run and stops fraudulent payments. The users are an AP clerk (runs the run) and a controller (approves exceptions). The interface is a financial instrument: a bank ledger crossed with an audit tool. Calm, dense, precise, trustworthy.

References: Linear's restraint, Mercury's clarity with money, a printed accounts ledger. Not a crypto dashboard. Not a SaaS landing page.

The one memorable thing is ledger discipline: money in a mono face with tabular figures, right-aligned, totals closed with accounting rules, and exceptions marked with a thin status rule on the row edge. Everything else stays quiet.

## Never

These are hard rules. A screen that breaks one is not done.

- No purple or blue gradients. No gradient text. No glassmorphism, backdrop blur, glow effects or blurred blobs.
- No emoji as icons. No sparkle icons for AI. AI output is labeled by what it did ("Held by risk check"), not decorated.
- No hero sections or marketing copy inside the app.
- No cards inside cards inside cards. Prefer tables, lists and hairline dividers. One panel level, maximum.
- No "Welcome back!" or similar fluff. No lorem ipsum. No generic placeholders ("Item 1", "John Doe", "Acme"). All copy is specific to AP work and uses the demo data (Ridgeline Builders, its vendors, Maria, Dev).
- No centered-everything layouts. Content is left-aligned on a grid. Numbers are right-aligned.
- Do not make every number a giant KPI card. A run has at most one headline figure; the rest live in the table.
- No status color used for decoration. Green, amber and brick mean paid, held and blocked. Nothing else.
- No shadows on panels, rows or buttons. Shadows are for overlays only.
- No pill-shaped controls or badges.
- No ALL CAPS labels, no labels joined with middle dots ("A · B · C"), no arrows appended to button text.
- No full bank account numbers anywhere. Show the last four only: `•••• 4417`.
- No em dashes in UI copy or code comments (project rule).

## Color

All colors are CSS variables. Use the Tailwind names, never raw hex in components.

### Light (default)

| Token | Hex | Tailwind | Use |
|---|---|---|---|
| `--paper` | `#F7F6F2` | `bg-paper` | Page background |
| `--surface` | `#FFFFFF` | `bg-surface` | Tables, panels, inputs, overlays |
| `--surface-sunken` | `#EFEDE6` | `bg-sunken` | Row hover, wells, secondary hover |
| `--ink` | `#16181D` | `text-ink` | Primary text, totals rules |
| `--ink-muted` | `#5B5F68` | `text-ink-muted` | Secondary text, column headers, pending |
| `--ink-faint` | `#8A8D94` | `text-ink-faint` | Placeholders and separators only (3.3:1, not for content text) |
| `--rule` | `#E4E2DA` | `border-rule` | 1px hairline dividers (default border color) |
| `--rule-strong` | `#CFCCC1` | `border-rule-strong` | Control borders (buttons, inputs) |
| `--accent` | `#1F3A5F` | `bg-accent`, `text-accent` | Primary action, focus ring, links, selected state |

### Dark (leaderboard second screen)

Apply with `data-theme="dark"` on `<html>` or on any subtree (the leaderboard page sets it on its root). Dark text uses the paper color so the dark screen reads as an inverted ledger.

| Token | Hex |
|---|---|
| `--paper` | `#10151C` |
| `--surface` | `#161D26` |
| `--surface-sunken` | `#0C1016` |
| `--ink` | `#ECEBE5` |
| `--ink-muted` | `#9BA1AB` |
| `--ink-faint` | `#6B717B` |
| `--rule` | `#253041` |
| `--rule-strong` | `#34404F` |
| `--accent` | `#8FB1DC` |

### Payment status

Status colors are used only for payment state. Every status is always shown with its word, so state never depends on color alone.

| State | Light | Dark | Text | Tint (row highlight, badge fill) |
|---|---|---|---|---|
| Pending | `#5B5F68` (muted ink) | `#9BA1AB` | `text-pending-ink` | `bg-pending-tint` |
| Paid | `#2F6B4F` | `#5FAE86` | `text-paid-ink` | `bg-paid-tint` |
| Held | `#B7791F` | `#E0A443` | `text-held-ink` | `bg-held-tint` |
| Blocked | `#B4342D` | `#E5675F` | `text-blocked-ink` | `bg-blocked-tint` |

Status text uses the `-ink` shade (`text-held-ink` and so on), which equals the solid color except where the solid fails WCAG AA as small text on its tint: held in light (`#8F5E14`, 5.1:1) and blocked in dark (`#EC7B73`, 5.2:1). Solids are for marks: the row rule, badge marker, danger button border.

Tints are derived, not hand-picked: `color-mix(status, surface)` at 8% in light and 14% in dark (8% disappears on a dark surface). They are opaque so they look the same on any background.

## Type

- **IBM Plex Sans** for all words. Weights 400, 500, 600 only.
- **IBM Plex Mono** for money, account numbers, invoice numbers, IDs, timestamps and risk scores. Weights 400 and 500 only. Never use `font-semibold` on mono (it is not loaded and the browser fakes it).
- Use the `figure` class for anything set in mono. It sets Plex Mono, tabular figures and a slashed zero.
- Tables set `tabular-nums` globally, so numbers align even in Plex Sans.

| Token | Size / line height | Use |
|---|---|---|
| `text-xs` | 12 / 16 | Badges, captions, reason text in rows |
| `text-sm` | 13 / 18 | Secondary text, table metadata, column headers |
| `text-base` | 14 / 20 | Body (default) |
| `text-md` | 16 / 24 | Section headings, emphasized lines |
| `text-lg` | 20 / 28 | Page titles, drawer titles |
| `text-xl` | 28 / 34 | Rare. A run title on the board |
| `text-2xl` | 40 / 44 | One headline figure per screen at most (for example the run total) |

Line lengths stay under 80 characters for prose. Headings use sentence case.

## Space, size and shape

- 4px grid. Tailwind's spacing scale is already 4px per step (`p-1` = 4px). Do not use arbitrary pixel spacing.
- Table rows are 36 to 40px (`h-9` header, `h-10` body). Cell padding: `px-4` on the first and last columns, `px-3` between.
- Cells do not wrap (`whitespace-nowrap`). Long reasons truncate with a max width; the full text lives in the payment detail.
- Page content max width is 1120px with 16px side gutters on phones (`px-4`) and 24px from `sm` up. The live board may go full width.
- Radius: `rounded-md` (6px) on controls, `rounded-lg` (8px) on panels and overlays, `rounded-sm` (4px) on badges. No other radii exist in the theme.
- Borders over shadows. Content is separated by 1px `border-rule` hairlines. `shadow-overlay` is the only shadow and is used only on drawers, popovers and dialogs, over a `bg-scrim` backdrop.

## Ledger conventions

- Money is right-aligned, in `figure`, formatted `$48,250.00` (always two decimals). Use the `Money` component or `formatUSD` from `lib/format.ts`.
- Account numbers show as `•••• 4417`.
- A total sits between a single rule above and a double rule below: wrap it in `.ledger-total`.
- Exceptions are flagged on the row: add `.row-flag` and `data-status` to the `<tr>`. Held and blocked rows get a 2px status rule on the leading edge plus the tint. Paid and pending rows stay plain so a clean run reads quiet. Flagged rows do not change on hover.
- Risk scores render as plain mono numbers (`85`), muted below 60.

## Components

shadcn/ui primitives live in `src/components/ui/` and have been restyled to these tokens: button, badge, table, sheet, dialog, tabs, tooltip, input, textarea, select, dropdown-menu, separator, scroll-area, skeleton, sonner, command. When adding another with the shadcn CLI, restyle it before use: replace `bg-accent` hovers with `bg-sunken` (our accent is ink blue, not a hover gray), drop `shadow-*` except `shadow-overlay` on overlays, drop `rounded-full`, and swap zoom or slide animations for the ones in Motion below. Import `cn` from `@/lib/utils`, not the `cn` package.

Countersign components live beside them: `board/`, `payment/`, `call/`, `inbox/`, `attack/`, and `shared/` for cross-screen pieces.

| Component | File | Notes |
|---|---|---|
| `Button` | `ui/button.tsx` | Variants: `primary` (one per view, the main action), `secondary` (default), `ghost` (tertiary, toolbar), `danger` (reject and block only), `link`. Sizes: `sm` 28px, `md` 32px, `icon` 32px, `icon-sm` 28px. Icon on the left, 16px. |
| `Badge` | `ui/badge.tsx` | Radius 4. `neutral`, `accent`, and one variant per payment status. |
| `Table` | `ui/table.tsx` | 36px header, 40px rows, no wrapping, hover only on rows without `.row-flag`. |
| `Sheet` | `ui/sheet.tsx` | Right-side drawer, 560px, used for payment detail at `/payments/:id`. |
| `StatusBadge` | `shared/status-badge.tsx` | Tinted fill, `-ink` text, square marker. Pending uses an outlined marker. |
| `Money` | `shared/money.tsx` | The only way to render a dollar amount. |
| `PageHeader`, `EmptyState` | `shared/` | Every page starts with `PageHeader`; empty screens say what to do next. |
| `iconProps` | `shared/icon.ts` | Spread onto every lucide icon. |

Formatting lives in `src/lib/format.ts`: `formatUSD`, `formatAccount` (last four only), `formatRelativeTime`, `formatScore`. Never format money, accounts or scores inline.

## Motion

- 150 to 200ms, ease-out (`cubic-bezier(0.2, 0, 0, 1)`). Tailwind's default transition already uses it.
- Overlays use the theme animations: `animate-fade-in` / `animate-fade-out` (scrims, tooltips), `animate-pop-in` / `animate-pop-out` (dialogs, menus: fade plus 2px rise), `animate-sheet-in` / `animate-sheet-out` (drawer). No zoom, no bounce.
- framer-motion is only for the allowed state changes that CSS cannot do cleanly (a number ticking, a row reordering). `MotionConfig reducedMotion="user"` is set at the root.
- Animate only state changes: a row turning held or blocked, a number ticking, a drawer opening, a toast arriving. Never animate on page load, on scroll, or on hover beyond a color change.
- `prefers-reduced-motion` is respected globally in `globals.css`. Do not override it.

## Icons

lucide-react only. 16px, stroke 1.75: `<Phone {...iconProps} />`. Icons sit beside a text label; an icon-only button needs an `aria-label`. Never emoji.

## Copy

- Sentence case everywhere. Plain AP vocabulary: payment run, invoice, vendor, hold, block, release, verification call, controller, approve, reject, audit log.
- Buttons say exactly what happens: "Start payment run", "Approve payment", "Reject payment", "Call vendor". The result uses the same verb: "Payment rejected".
- Explanations name the evidence: "Held: new bank account, lookalike domain (summit-concrete.co)". Not "Something looks suspicious".
- Empty states tell the user what to do next: "No payments held. Start a payment run to process this week's 40 invoices."
- Errors say what failed and how to fix it, without apologizing.

## Accessibility floor

- Visible keyboard focus: 2px accent outline, 2px offset (global).
- Text contrast meets WCAG AA in both themes. Status never relies on color alone.
- Every screen works at 390px wide with no horizontal page scroll; wide tables scroll inside their own container.
