# PACS Komparátor: design system (NIS style)

The UI follows the visual language of a hospital information system (NIS): plain, dense and functional. New screens must use the primitives below instead of their own styling.

## Tokens (`tailwind.config.js`)

| Token | Value / use |
|---|---|
| Font | Roboto 400/500/700 (`@fontsource/roboto`, latin + latin-ext) |
| Root size | 14 px (`html`), 18 px in presentation mode (`html.presentation`). All Tailwind sizes are rem, icons are em, so everything scales |
| `accent-*` | NIS blue `#0b6cf0` (`accent-600`), links, primary buttons, section icons |
| `nis-page` | page background `#e9edf3` |
| `nis-line` | panel and table borders |
| `nis-head` | table header background |
| `nis-text` / `nis-muted` / `nis-icon` / `nis-ink` | body text / secondary text / inactive icons / dark tags |
| `nis-ready`, `nis-attention`, `nis-danger`, `nis-info` | pastel row backgrounds |
| `nis-green`, `nis-amber`, `nis-red`, `nis-teal`, `nis-slate` | solid tag colors |
| `rounded-nis` | 5 px radius for panels, inputs, buttons |

## CSS classes (`src/index.css`)

`nis-panel` (white bordered panel), `nis-label` (11 px bold uppercase gray label), `nis-btn` + `nis-btn-primary | -secondary | -ghost | -icon`, `nis-input`, `nis-link`, `nis-table` (dense table), `nis-row-ready | -attention | -danger | -info` (pastel status rows), `nis-hatch` (hatched "empty" area).

## Components (`src/components/ui`, import from `components/ui`)

| Component | Props | Use |
|---|---|---|
| `Icon` | `name`, `size?` (default `1.3em`), `className?`, `title?` | Inline SVG line icons. Add new ones to `PATHS` in `Icon.tsx` |
| `SectionHeader` | `icon`, `title`, `subtitle?`, `as?`, children = right-side controls | Page header: blue circle icon + UPPERCASE title |
| `DateNav` | `label`, `onPrev?`, `onNext?`, `prevLabel`, `nextLabel` | `‹ ›` date switcher (undefined handler = disabled) |
| `HeaderDivider` | none | Vertical separator between header controls |
| `Panel` | `id?`, `title?`, `icon?`, `actions?`, `className?`, `bodyClassName?` | White section with optional header row |
| `Field`, `FieldLabel` | `label` / `htmlFor?` | Label above value |
| `DataTable` | children = `<thead>`/`<tbody>` | Dense table, scrolls horizontally |
| `Muted`, `ErrorState` | text / `message`, `retryLabel`, `onRetry` | Loading/empty text, error with retry |
| `Button`, `ButtonLink`, `IconButton` | `variant: primary \| secondary \| ghost`, `icon?`, plus native props / `to` | Actions |
| `Tag`, `StatusTag` | `tone`, `icon?`, `title?` | Small solid status tags (`TagTone`: slate, blue, teal, green, amber, red, gray, outline) |
| `TagField` | tag label + value | Dark tag before a value ("DG C61") as in the record header |
| `PillTabs` | `tabs`, `value`, `onChange`, `label` | Blue pill switches / filters with counts |
| `StatChip` | `icon`, `iconClass?`, `label`, `value` | Read-only counter chip (summary tiles) |

Tone maps in `Tag.tsx`: `READINESS_TONE`, `READINESS_ICON`, `READINESS_ROW` (readiness → tag tone / icon / row class), `ITEM_ROW` (required item state → row class), `REQUEST_TONE` (request state → tag tone).

Domain components built on top: `ReadinessBadge` (`ReadinessIcon`, `ReadinessTag`, default = tag + reason), `ReadinessLabel`, `AvailabilityChip`, `SimulaceTag`, `RequestProgress`.

## Patterns

- **Page** = `SectionHeader` + a stack of `Panel`s (`space-y-3`).
- **Status rows** = `DataTable` rows with `READINESS_ROW[state]` or `ITEM_ROW[state]`, `StatusTag`/`ReadinessTag` in the right column, chevron for navigation.
- **Request states**: `StatusTag tone={REQUEST_TONE[state]}` plus `RequestProgress`.
- **Actions**: one `Button variant="primary"` per area, the rest `secondary`/`ghost`.
- **Simulated data**: always show `SimulaceTag` next to it.
- **Shell**: icon rail and top bar in `App.tsx`. Add a rail entry to the `RAIL` array (`to`, `icon`, `label` from `cs.ts`); the breadcrumb is derived from the route.
- All labels live in `src/i18n/cs.ts`.

## Accessibility rule

Readiness is always shown as **icon + text + reason**, never color alone. Pastel rows are only an extra cue. Icon-only buttons need `aria-label`.

## Screens that should adopt this

Request actions and the request drawer, the nightly-run banner ("Schválit vše"), the `/stats` page and the agent chat panel: use `Panel`, `DataTable`, `StatusTag` + `REQUEST_TONE`, `Button` and `SimulaceTag`.
