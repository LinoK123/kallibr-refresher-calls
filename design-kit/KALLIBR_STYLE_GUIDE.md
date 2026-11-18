# Kallibr Design Style Guide

Use this design style for any new Kallibr web tool. It is extracted from the Kallibr CRM / Sales Dashboard so new tools look like part of the same family.

**Files in this kit**
- `KALLIBR_STYLE_GUIDE.md`: this guide, covering the rules and the reasoning behind them.
- `kallibr-theme.css`: the stylesheet, with design tokens and every component. Link it, or paste it into a `<style>` block for single-file apps.
- `starter-template.html`: a working page that shows every component and the chart styling in use. It already contains the full stylesheet, so it works on its own. Start new builds from this file.

---

## 1. Look and feel

A soft, friendly, pastel admin UI. Calm cream background, white rounded cards, lavender as the brand colour, and elegant serif headings paired with a clean sans body. It should feel approachable and uncluttered, not corporate or dark.

- **Cards on cream.** All content sits in white cards (24px radius, a faint lavender hairline border, a very soft purple-tinted shadow) on a warm cream page background.
- **Lavender is the accent.** It's used for active states, primary buttons, table header rows, selected items and focus rings.
- **Pastel pairs.** Each colour has a light fill and a stronger accent (rose/rose2, sage/sage2, sky/sky2, lav/lav2, peach/peach2). Use the light one for backgrounds and the stronger one for stripes, borders and chart marks.
- **Semantic colour means something.** Red = overdue/lapsed/lost, amber = warning/today/pending, green = success/won/new, blue = info/contacted, orange = declining. Always dark text on a pale tint, never white text on bright colour except for active pills and buttons.
- **Emoji as icons.** Navigation items, section titles and status labels use a single emoji (📊 🏢 📞 📅 ✨ 🔴 🟡 🟢 🌱). There's no icon library.

## 2. Typography

| Use | Font | Size | Weight |
|---|---|---|---|
| Page title | DM Serif Display | 1.9rem | 400 |
| Card title | DM Serif Display | 1.05rem | 400 |
| KPI / big numbers | DM Serif Display | 1.7rem (1.2rem in small stat boxes) | 400 |
| Body, tables, inputs | DM Sans | 0.81–0.86rem | 400–500 |
| Labels, table headers, section titles | DM Sans, UPPERCASE, letter-spacing 0.05–0.1em | 0.63–0.73rem | 600–700 |
| Sub-text / hints | DM Sans, muted colour | 0.7–0.76rem | 400 |

Google Fonts link:
```html
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
```
Numbers in tables are right-aligned with `font-variant-numeric: tabular-nums` (class `.num`). Money is shown compact in summaries (`$1.24M`, `$48.2K`) and in full on detail views (`$48,210.00`), in Australian format.

## 3. Colour tokens

| Token | Hex | Role |
|---|---|---|
| `--cream` | `#fdf8f2` | Page background |
| `--white` | `#ffffff` | Cards |
| `--text` | `#2d2d3a` | Body text |
| `--text2` | `#6b6b82` | Muted text, labels |
| `--border` | `#ece8f4` | Hairlines (1.5px on cards/inputs, 1px on rows) |
| `--lav` / `--lav2` | `#ddd4f0` / `#b8a9de` | Brand: light fill / primary accent |
| `--brand-deep` | `#7B68C8` | Strong purple emphasis |
| `--rose` / `--rose2` | `#f9c8d0` / `#f2a0b0` | Pastel pair |
| `--sage` / `--sage2` | `#c8e6c8` / `#9ecf9e` | Pastel pair |
| `--sky` / `--sky2` | `#bde0f7` / `#87c5ef` | Pastel pair |
| `--peach` / `--peach2` | `#fddcb5` / `#f9be7c` | Pastel pair |

Semantic (text on tint): success `#2d7a2d` on `#edf7ed`, danger `#c0392b` on `#fde8e8`, warning `#856404` on `#fff3cd`, orange `#a05c00` on `#fddcb5`, info `#1565a8` on `#e3f0fb`, purple `#5a4a8a` on `#ece8f7`.

Shadows: cards use `0 2px 16px rgba(100,80,160,0.08)` and modals use `0 8px 32px rgba(100,80,160,0.14)`. They're purple-tinted, never grey or black.

Radii: cards 24px, banners 16px, buttons and inputs 10px, pills 20px, badges 99px (fully round), code tags 6px.

## 4. Layout

- **App shell:** a fixed white sidebar 220px wide on the left (logo block, small uppercase group labels, emoji nav items, footer with summary text), and main content with 30px/34px padding.
- **Page header:** a serif title plus a one-line muted subtitle on the left, and the main action (primary button or segmented toggle) on the right.
- **Content flow:** KPI row (`.grid-4`) → main chart or table card → `.grid-2` pairs of cards.
- **Spacing:** 14–20px gaps between cards, 22–26px card padding.
- **Responsive:** grids collapse to 2 columns at 900px and 1 column below that. The sidebar hides under 600px.

## 5. Components (classes in `kallibr-theme.css`)

| Component | Classes | Notes |
|---|---|---|
| Card | `.card`, `.card-title`, `.card-subtitle` | Default container for everything |
| Section heading | `.section-title` | Small uppercase label with a hairline running to the right, used inside cards |
| KPI card | `.kpi-card` + `.kpi-label` / `.kpi-value` / `.kpi-sub` | 4px coloured top stripe, which cycles rose → sage → sky → peach automatically inside `.grid-4`. Use `.accent-danger/-warning/-success/-brand` for meaning |
| Stat tile | `.stat-box` | Small cream tile for numbers inside a card |
| Hero | `.hero`, `.hero-stats` | Lavender→sky gradient header for detail pages |
| Buttons | `.btn-primary`, `.btn-ghost`, `.btn-danger`, `.btn-sm` | One primary button per area. Ghost for secondary actions |
| Segmented toggle | `.segmented > button.active` | For switching views (Monthly/Quarterly/Yearly) |
| Filter pills | `.filter-row`, `.pill.active`, `.pill-danger`, `.pill-success` | Rounded filter buttons above tables |
| Checkbox pill | `.check-pill > input[type=checkbox]` | A toggle filter that turns green when on |
| Chips | `.chips > .chip.selected` | Multi-select options in forms |
| Option tiles | `.option-grid > .option-tile.selected` | Click to toggle (e.g. assigning team members). Selected = lavender with a ring |
| Badges | `.badge-success/-danger/-warning/-orange/-info/-purple/-neutral` | Round status labels, often with an emoji (🔴 Lapsed, 🌱 New) |
| Tags | `.tag-rose/-blue/-violet/-green` | Square-ish code labels (QLD, NSW, VIC, CSQ) |
| Avatars | `.avatar` (`.sm`, `.lg`), `.avatar-stack` | Coloured circle with white initials. Overlap in a stack for multiple people |
| Table | `.table-wrap > .table-scroll > table.table`, `.pagination` | Lavender header row (uppercase), hover tint on rows, `th.sortable` turns lavender-filled on hover |
| Ranked list | `.list`, `.list-header`, `.list-item(.selected)`, `.bar-track > .bar-fill` | Rows with a mini lavender→sky gradient bar |
| Forms | `.form-group`, `.form-row(.three)`, `.form-label` (+ `.req`), `.form-input`, `.form-select`, `.form-textarea`, `.form-hint`, `.search-input` | Uppercase labels above fields, lavender focus border, custom select chevron |
| Banner | `.banner-warning/-danger/-info`, `.banner-title`, `.banner-sub` | Something to act on (e.g. "2 records need review") |
| Empty state | `.empty-state`, `.empty-icon` | Emoji plus one short line |
| Modal | `.modal-backdrop.open > .modal`, `.modal-head`, `.modal-x`, `.modal-foot` | Opens near the top, closes on backdrop click, Cancel (ghost) + action (primary) at the bottom right |
| Toast | `.toast.show` | Dark pill, bottom right, auto-hides after about 2.2s. Confirms saves ("Saved ✓") |
| Timeline | `.log-item`, `.log-top`, `.log-title`, `.log-date`, `.log-notes` | History entries on cream |

## 6. Charts (Chart.js 4.4.1)

Load from `https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js`. Match the settings in `starter-template.html`:
- **No legend** on bar and line charts. Tooltips show formatted money.
- **Axes:** x has no gridlines. y has very faint gridlines `rgba(0,0,0,0.04)` and no axis border. Tick text is 10px in `#6b6b82`.
- **Bars:** `borderRadius: 6`, a pastel fill at about 70% opacity with a matching solid border. When showing time, colour bars by year.
- **Lines:** colour `#b8a9de`, fill `rgba(184,169,222,0.12)`, `borderWidth: 2.5`, `tension: 0.4` (smooth), small points.
- **Doughnuts:** `cutout: '60%'`, white 2px segment borders, legend on the right (10px font, 11px boxes).
- **Palette order:** `#f2a0b0, #9ecf9e, #87c5ef, #b8a9de, #f9be7c, #a8d8ea, #f7c5e0, #b5ead7, #ffdac1, #c7ceea`.

## 7. Writing style

- Australian English (organisation, colour), plain and friendly.
- Page subtitles say what the page is for, in one line.
- Buttons use verbs: "Save Call Log", "+ Add Prospect", "Open →", "Merge".
- Confirmations are short toasts with ✓. Destructive actions ask first and say what happens.
- Empty states tell the user what to do next ("No prospects yet — click + Add Prospect…").

## 8. Do / Don't

**Do**
- Reuse the tokens (`var(--lav2)`) rather than new hex values.
- Keep one clear primary action per screen area.
- Use semantic badge colours consistently with their meanings.
- Keep the page single-file (HTML + CSS + JS) when it will be hosted on GitHub Pages.

**Don't**
- Use dark mode, heavy black shadows, sharp corners or saturated full-colour backgrounds.
- Mix in other font families or an icon library.
- Use white text on pastel fills. Contrast is too low.
- Put secrets (API keys, passwords) in front-end files.
