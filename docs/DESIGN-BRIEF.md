# Design brief — Options Surface Lab

**Status:** adopted 2026-09-02 (T-13, FR-8). PO-directed; this document records the
decision so the identity survives the semester's later pages.
**Implementation:** [`options_surface_lab/theme.py`](../options_surface_lab/theme.py) — the
only file in the repo permitted to contain a colour, a font name or a layout measurement
(AD-6).

---

## 1. The direction

**A terminal.** The Bloomberg reference the PO gave is about **arrangement, not palette**:
numbered panels butted against each other under one command bar, a strip of readouts across
the top, no floating cards, no scroll of whitespace. Dense, square-cornered, hairline-ruled.
The layout is §5; it is the part that does the most work.

The colour that goes with it: **deep-navy ground, amber type**. Warm amber headings and
metric values against a cool near-black navy — the classic terminal contrast — with the
figures' own data colours the only other colour on the page.

The starter look (GitHub-dark grey `#0d1117`, cyan chrome, rounded cards in a single wide
column with big gaps) is gone entirely.

## 2. What was not ours to choose

The assignment brief fixes two encodings, and the whole page exists to make their difference
visible. They are constraints, not palette choices:

> *"Cyan: `SETTLE`. Magenta diamonds: `TRDPRC_1`."* — README, "What the 3D plot is doing"

So `MARK` stays cyan and `TRADE` stays magenta. `tests/test_theme.py` asserts this by **hue
family**, not by exact hex — the brief says "cyan", not a value, so re-toning within the hue
is free and moving out of it needs the PO.

**Amber is type, never data.** `ACCENT` paints headings, metric values, panel numbers and the
as-of slider, and nothing else. `test_the_chrome_colour_is_never_a_data_colour` enforces the
separation — it exists because the first pass had a put series and the accent on the same
hue, a collision that only became visible once amber became the heading colour.

## 3. Palette

| Token | Value | Job |
|---|---|---|
| `BG` | `#060B16` | page ground — deep navy, near-black under type |
| `SURFACE` | `#0C1526` | panels, readout cells, figure paper |
| `SURFACE_ALT` | `#111E33` | panel header bars, plot interior, the "no quote" floor |
| `BORDER` | `#1B2A44` | hairline rules — the grid is made of these |
| `GRID` | `#1F3152` | axis gridlines — visible, never louder than the data |
| **Type** | | |
| `TEXT` | `#E8E3D9` | body copy — warm off-white against the cool ground |
| `TEXT_MUTED` | `#94897A` | captions, axis ticks, panel labels |
| `ACCENT` | `#FFB000` | **amber:** headings, metric values, panel numbers, slider |
| `ACCENT_DIM` | `#8A6A1E` | amber at rest: slider track, button |
| `TEXT_INVERSE` | `#060B16` | text on an accent or data fill (bar labels) |
| **Data** | | |
| `MARK` | `#22E3D0` | **the mark (MID_PRICE), calls** — circle *(README-locked)* |
| `MARK_PUT` | `#A78BFA` | the mark, puts — filled circle |
| `TRADE` | `#FF2E88` | **TRDPRC_1, calls** — diamond *(README-locked)* |
| `TRADE_PUT` | `#3DDC84` | TRDPRC_1, puts — filled diamond |
| `NEUTRAL` | `#6E8CB8` | the "both mark and print" bar — the uninteresting middle |
| `POSITIVE` / `NEGATIVE` | `#2FD4A0` / `#FF4D6D` | underlying up/down candles |

**The put rule.** Puts take the two hues furthest from both locked colours *and* from the
amber type — separation is largest **within** a role, because calls-against-puts inside one
role is the comparison a reader actually makes:

| Role | Calls | Puts | Hue gap |
|---|---|---|---|
| mark | cyan `#22E3D0` ● circle | violet `#A78BFA` ● circle | 83° |
| print | magenta `#FF2E88` ◆ diamond | green `#3DDC84` ◆ diamond | 150° |

**The glyph encodes the role, not the right.** A circle is a mark and a diamond is a print,
whichever right it belongs to; calls and puts are told apart by hue alone. That is a PO
decision (2026-09-02) and it is the reason the hue gaps above have to be wide — with the
shape fixed, colour is the only channel left doing that work. An attempt at square/cross for
the puts put the right in the glyph too, and made the legend four shapes deep for two ideas.

**Every marker is filled.** The first pass derived puts by shifting each call's colour toward
blue and drew them with open symbols — both were wrong. The blue shift made puts *deliberately
similar* to their calls, so on the mark-vs-print scatter the cyan calls and sky puts read as
one cloud and the puts looked absent; and a 4px ring on a dark ground, seen through a 3D
projection, is a smudge rather than a point. Openness is not a strong enough channel at this
mark size. `test_a_right_is_never_a_near_shade_of_its_own_counterpart` (60° floor) and
`test_every_marker_is_filled` hold both corrections.

**Contrast.** Measured WCAG ratios on every pairing the page actually renders — all clear AA
(4.5:1), and `test_every_foreground_clears_wcag_aa` keeps it that way:

| Pair | Ratio |
|---|---|
| `TEXT` on `BG` / on `SURFACE_ALT` | 15.4:1 / 13.1:1 |
| `TEXT_MUTED` on `BG` / `SURFACE` / `SURFACE_ALT` | 5.7:1 / 5.3:1 / 4.9:1 |
| `ACCENT` on `BG` / `SURFACE` | 10.7:1 / 10.0:1 |
| `MARK` / `MARK_PUT` on the plot interior | 10.3:1 / 6.1:1 |
| `TRADE` / `TRADE_PUT` on the plot interior | 4.8:1 / 9.4:1 |
| `NEUTRAL` on the plot interior | 4.9:1 |
| `TEXT_INVERSE` on `MARK` / `TRADE` / `ACCENT` (bar labels) | 12.2:1 / 5.6:1 / 10.7:1 |

`TRADE` on the plot interior is the tightest at 4.8:1 — magenta on navy is inherently the
narrowest pair here and it is held by the README. It clears AA, and print markers carry a
lighter outline (`TRADE_EDGE`) so they never dissolve into the sheet behind them.

## 4. Typography

| Role | Face | Where |
|---|---|---|
| Display | **Space Grotesk** 500/700 | wordmark, panel names, figure titles |
| Body | **Inter** 400/600 | prose, captions, axis titles, controls |
| Mono | **JetBrains Mono** 400/700 | every number: readout values, ticks, hover, slider, panel numbers |

The rule that does the work is the third one. Numerals in mono is what makes the page read as
an instrument rather than a report, and it is why the tick labels on the strike axis stack
into columns instead of drifting.

Loaded from Google Fonts via `theme.GOOGLE_FONTS_CSS` — one URL, consumed by Reflex as a
stylesheet and by the static builder as `<link>` tags. **Every stack falls back all the way
to a system face**, so the page is legible before the webfont arrives and correct if it never
does. This adds a second CDN to the published page alongside Plotly's; see §7.

## 5. Layout — the terminal grid

```
┌─ OPTIONS SURFACE LAB ─────────── UUUU · mark = MID_PRICE · as-of 2026-07-10 ─┐
├ SERIES 216 │ NO PRINT 1,601 (21%) │ BOTH 4,241 │ GAP $0.040 │ SPREAD 20% ────┤
├────────────────────────────────────────────┬─────────────────────────────────┤
│ [1] PRICE SURFACE · 3D              6 cols │ [2] UUUU UNDERLYING           4 │
│                                            │                                 │
│        (hero, 3D point cloud, 600px)       │         spot context,           │
│                                            │         600px to match          │
│  ──────────── as-of slider ────────────    │                                 │
├───────────────────────────┬────────────────┴─────────────────────────────────┤
│ [3] MARK VS PRINT       5 │ [4] SPREAD · CAN YOU BELIEVE THE MARK?         5 │
├───────────────────────────┼──────────────────────────────────────────────────┤
│ [5] MARK OCCUPANCY      5 │ [6] PRINT OCCUPANCY                            5 │
└───────────────────────────┴──────────────────────────────────────────────────┘
```

A **10-column** grid, because 10 divides cleanly into both `6+4` (the hero row) and `5+5`
(everything else) — 2 and 12 do not. Widths are the tokens `W_HERO`, `W_SIDECAR`, `W_HALF`
and `W_FULL`, and `test_panel_widths_tile_complete_rows` asserts they still add up: on a
hairline grid a row that does not fill its width leaves a visible hole.

- **Command bar** — wordmark left, instrument identity right (ticker, mark field, as-of,
  series count) in mono. One line, always the same place.
- **Readout strip** — the FR-6 headline numbers, butted together with a 1px rule between
  cells, directly under the bar. `grid-template-columns: repeat(auto-fit, minmax(158px,1fr))`,
  so it reflows without ever becoming a ragged wrap.
- **Panel grid** — 10 columns, collapsing to a single column under 1100px (below that the
  adjacency is not worth the squeeze). Every panel has a header rule: `[n]` in amber mono,
  the name in tracked display caps, and a right-aligned mono note telling you how to read it.
- **The underlying sits beside the surface**, not three panels away. Spot is what makes "near
  the money" mean anything, and the dense region of the cloud *is* the near-the-money band —
  so the figure that explains the density belongs next to the density. It also turns the
  as-of slider into cause and effect: the cloud shifts because spot moved, and both are in
  one glance. It is **6/4 rather than an even split** because the hero needs more of the
  width — its slider carries 53 steps and is the published page's only interactivity (AD-5),
  so starving it would cost more than the adjacency gains. (It started at 7/3; the PO widened
  the sidecar on 2026-09-02 — the candlestick was too narrow to read, and the surface gives up
  very little going from 7 to 6.) The sidecar reads `HERO_FIGURE_HEIGHT`, so the row ends
  level instead of ragged.
- **Panels are never stretched to their row** (`align-items: start`), and `HERO_FIGURE_HEIGHT`
  is 600, not 760. At 760 the 3D scene gained only empty background, while the sidecar
  candlestick — which needs far less height — was stretched to match and left a visibly dead
  half-panel beneath the chart. Shorter is strictly better here: the whole page gets shorter
  and nothing is squeezed.
- **Panel order is the argument**, not the figure inventory: the surface with its spot
  context, then the evidence that mark ≠ print and whether the mark is believable at all,
  then where the data simply is not there. The two occupancy grids stay paired on the last
  row because comparing them *is* the reason both are shown.
- **The next step in the same direction** is FR-12's spot plane at `K = S`, which puts spot
  *inside* the surface rather than beside it. The two compose: adjacency first, plane second.
- **Titles live in the header, not the figure.** `as_panel_figure()` strips each tiled
  figure's Plotly title and tightens its margins, because the panel header already says the
  name and an in-plot title would eat a third of the tile. The **hero is the exception** —
  the as-of slider rewrites its title on every step, so that one has to stay inside the
  figure JSON (AD-5).

The Reflex dev app renders the same command bar, readout strip and numbered panels via
`theme.PANEL_STYLE` / `PANEL_HEADER_STYLE`, and panelises its figures through the same
`as_panel_figure()`. The checkpoint demo and the graded page are one product.

**A figure must declare exactly the height its panel reserves.** Both consumers size the
container from `HERO_FIGURE_HEIGHT` / `PANEL_FIGURE_HEIGHT`, and Plotly draws to
`layout.height` regardless — so a figure that declares more than its box overflows it and
paints over the panel below. The dev app hit this: it handed raw builders to the grid, the
surface declaring 640 into a 600px box, and it spilled across the mark-vs-print panel
underneath. `price_surface_figure` now reads `HERO_FIGURE_HEIGHT` directly, every tiled
figure goes through `as_panel_figure()`, and empty figures declare a height too — an
undeclared one renders at Plotly's 450 default and overflows a 360px tile. Three tests in
`tests/test_app_figures.py` hold it, including a source-level guard that no `self.fig_*`
assignment escapes without a height.

## 6. Rules the identity must not break

1. **Mark ≠ print, in colour *and* symbol** (FR-5), for both rights.
2. **Amber never encodes data** (§2).
3. **The interpolated sheet stays subordinate** (AD-9). Opacity 0.26, ramping toward its own
   series' colour, always labelled as interpolation. It must never read as data.
4. **Holes render as holes.** The heatmap "no quote" cell is `SURFACE_ALT` — a colour, not an
   absence, so an empty cell is visibly empty rather than invisibly missing.
5. **No visual literal outside `theme.py`**, across `option_surface_plot.py`,
   `options_surface_app.py` and `build_preview.py`.

All five are asserted in `tests/test_theme.py`. FR-8's acceptance criteria were three
judgement calls; they are executable now.

## 7. Consequences accepted

- **A second CDN on the published page.** The page reaches `fonts.googleapis.com` /
  `fonts.gstatic.com` alongside `cdn.plot.ly`. The self-containment guard in
  `tests/test_build_preview.py` allows exactly those hosts and no others. The page still has
  **no backend**, which is what AD-4/AD-5 actually require; a font that fails to load degrades
  to a system face rather than breaking the render. Plotly.js is now requested once by the
  first panel rather than once per figure, so that single dependency is visible in an audit.
- **Future pages inherit the identity for free** — the point of AD-6, and the reason this is a
  document rather than a commit message.

## 8. Revision history

| Date | Change |
|---|---|
| 2026-09-02 | Adopted. First pass shipped ice-blue chrome and a single-column layout; the PO corrected both — "Bloomberg" meant the **page layout**, and the font colours needed to change. Amber type and the panel grid replaced them; puts moved off amber onto the blue-shift rule (§3). Navy ground unchanged throughout. |
| 2026-09-02 | PO asked to pair the underlying with the price surface. Grid moved from 2 columns to 10 so the hero row could be 7/3 rather than an even split; the remaining four figures re-flowed 5+5 across two rows. |
| 2026-09-02 | PO caught three defects by eye. Put markers were unreadable (open symbols, and hues derived as near-shades of their calls) — puts re-hued to violet/green, all markers filled (§3). The mark-vs-print scatter drew one unlabelled array-coloured trace, so the puts read as missing — split into named Calls/Puts traces with a legend. And the hero row wasted vertical space — height 760 → 600 plus `align-items:start` (§5). All three now have tests. |
| 2026-09-02 | PO found the 3D surface overflowing into the mark-vs-print panel in the **dev app**: it was handing un-panelised figures to the terminal grid, so titles doubled with the panel headers and declared heights (640, 460) exceeded the boxes reserved for them (600, 360). App figures now panelise exactly as the builder's do; `price_surface_figure` reads `HERO_FIGURE_HEIGHT`; empty figures declare a height. Guarded by tests (§5). |
| 2026-09-02 | PO refined the correction: the put **colours** were the problem, not the glyphs — square/cross reverted to circle/diamond, so the glyph encodes the role and hue alone separates the rights. Hero row widened from 7/3 to 6/4. |
