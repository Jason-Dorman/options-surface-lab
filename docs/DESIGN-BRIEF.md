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

**Amber is type, never data.** `ACCENT` paints headings, metric values, panel numbers, the
as-of slider and the axis-toggle chip (§5), and nothing else. The chip is the one place amber
is a *fill* rather than type, and it carries `TEXT_INVERSE` for exactly that reason.
`test_the_chrome_colour_is_never_a_data_colour` enforces the separation — it exists because the first pass had a put series and the accent on the same
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
| `ACCENT` | `#FFB000` | **amber:** headings, metric values, panel numbers, slider, axis-toggle chip |
| `ACCENT_DIM` | `#8A6A1E` | amber at rest: slider track, button |
| `TEXT_INVERSE` | `#060B16` | text on an accent or data fill (bar labels, the axis chip) |
| `MENU_ACTIVE_BG` | `#F4FAFF` | **not ours** — plotly.js paints an `updatemenu`'s highlighted row this and exposes no override. Recorded so the contrast test can measure a ground we really do render type against; it is what rules amber type out of that control. |
| **Data** | | |
| `MARK` | `#22E3D0` | **the mark (MID_PRICE), calls** — circle *(README-locked)* |
| `MARK_PUT` | `#A78BFA` | the mark, puts — filled circle |
| `TRADE` | `#FF2E88` | **TRDPRC_1, calls** — diamond *(README-locked)* |
| `TRADE_PUT` | `#3DDC84` | TRDPRC_1, puts — filled diamond |
| `NEUTRAL` | `#6E8CB8` | the "both mark and print" bar — the uninteresting middle |
| `POSITIVE` / `NEGATIVE` | `#2FD4A0` / `#FF4D6D` | underlying up/down candles |
| **Reference** | | |
| `SPOT_PLANE` | `#7FA8D9` | FR-12's wall at `K = S` — slate, at `SPOT_PLANE_OPACITY` 0.18 |

**The plane is neither data nor chrome, and it has to look like neither** (T-18, 2026-09-04).
It is the one object in the scene that is a *ruler*: it asserts where the money was on the
as-of date and nothing else. So it takes no series hue — a reader would start looking for the
points that belong to it — and not the amber, which is type everywhere else on the page and
would read as chrome bolted onto the chart.

Slate is deliberately the same family as `NEUTRAL` (3° apart in hue; `SPOT_PLANE` is the
lighter tint). `NEUTRAL` is already this palette's *not-a-series* colour — the "both mark and
print" bar, "the one bar that takes neither a data colour nor the chrome amber" — so the two
objects that mean **"this is not one of the four series"** look related on purpose. They never
share a panel: `NEUTRAL` is a bar in [4], `SPOT_PLANE` a translucent wall in [1]. Measured
distances from the four data hues: 39° (MARK), 43° (MARK_PUT), 66° (TRADE_PUT), 122°
(TRADE), and 171° from the amber. It is fainter
than the interpolated sheet on purpose: the sheet lies *over* the cloud in one thin layer,
while the plane stands side-on *through* the middle of it, so at the sheet's 0.26 it fogged
every point behind it. `test_the_spot_plane_is_neither_a_series_nor_the_chrome` holds all of
it, including the flat colour scale — a ramp would imply the wall measures something.

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
│   caption · legend · modebar (the full band)│                                 │
│  ┌────────────────────────────────────────┐ │         spot context,           │
│  │[Strike (K) ▾]  3D point cloud, 600px │ │         600px to match          │
│  └────────────────────────────────────────┘ │                                 │
│  ──────────── as-of slider ────────────    │                                 │
├───────────────────────────┬────────────────┴─────────────────────────────────┤
│ [3] IMPLIED VOL · DERIVED 5 │ [4] MARK VS PRINT                            5 │
│   smile, one curve/expiry   │                                                │
├───────────────────────────┴──────────────────────────────────────────────────┤
│ [5] SPREAD · CAN YOU BELIEVE THE MARK?                               10 cols │
├───────────────────────────┬──────────────────────────────────────────────────┤
│ [6] MARK OCCUPANCY      5 │ [7] PRINT OCCUPANCY                            5 │
└───────────────────────────┴──────────────────────────────────────────────────┘
```

A **10-column** grid, because 10 divides cleanly into both `6+4` (the hero row) and `5+5`
(everything else) — 2 and 12 do not. Widths are the tokens `W_HERO`, `W_SIDECAR`, `W_HALF`
and `W_FULL`, and `test_panel_widths_tile_complete_rows` asserts they still add up: on a
hairline grid a row that does not fill its width leaves a visible hole.

**The `.osl-w{n}` classes are generated for every column, never hand-listed.** This is the
one defect in the restyle that reached production. The hand-written stylesheet declared
`.osl-w3/.w5/.w7/.w10` from the 7/3 era; when the split became 6/4 the tokens changed and the
CSS did not, so `.osl-w6` and `.osl-w4` did not exist. **CSS fails open** — an undefined class
is not an error, `grid-column` simply stays `auto` — so the surface and the underlying
rendered *one column wide* on the deployed page while every other panel was correct. The
Reflex app styles its panels with inline `grid-column`, so it looked perfect locally, which
is what made it a deploy-only failure. Two tests now cover it: one that every width token has
a base-level rule, and one that walks the built page and fails on any class it uses but never
defines.

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
  then where the data simply is not there, and finally what you get if you push that mark
  through a model anyway. The two occupancy grids stay paired because comparing them *is* the
  reason both are shown, and the IV surface comes **last** because it only means anything
  once panels [3]–[6] have established what its input is worth.
- **The IV panel is a 2D smile in row 2, directly under the surface it comes from**
  (FR-11; PO, 2026-09-04). It shipped first as a full-width 3D scatter at the foot of the
  page and the PO's verdict was that it read as "a bunch of scattered points" with no
  discernible message — which was fair: a 3D point cloud with no sheet and no connecting
  structure gives the eye nothing to follow. The same numbers in two dimensions have a shape
  you can name. Implied vol against `K / S`, one curve per expiry, and the *near-dated curves
  are visibly steeper than the far-dated ones* — on the busiest date the 7-day expiry spans
  63–130% while the 42-day expiry spans 76–85%. That flattening is the term structure of the
  smile, and it was invisible in 3D.
- **Position is the argument, again.** The smile sits beside [4] mark-vs-print rather than at
  the foot, because it is the *same cloud read through a model* and belongs next to the price
  it was derived from, not three panels away. The cost, accepted knowingly: the model now
  comes *before* the evidence that its input is soft ([5] spread, [6]/[7] occupancy), where
  the original order built that case first. The two surfaces reading as a pair is worth more.
- **Spread went full width to keep the occupancy grids paired.** With the smile taking half
  of row 2, the three remaining panels cannot tile two rows evenly; something had to go wide.
  Spread is a strike × expiry grid that only gains from the room, and moving it protects the
  [6]/[7] adjacency that comparing them depends on.
- **Colour: expiry takes a sequential ramp, not a categorical palette.** Expiry is *ordered*,
  so the ladder runs `MARK` → `MARK_PUT` (`EXPIRY_RAMP`) and the reader can tell near from far
  without reading the legend. It introduces no new hue: both endpoints are existing mark
  colours, and every point on this panel is mark-derived, so there is no print series beside
  it for cyan to be mistaken for. The ladder is fixed **panel-wide**, so one expiry keeps one
  colour on every as-of date and the eye can follow a curve across the window.
- **A break in a line is a hole, and that had to be built deliberately.** A line chart is the
  one form that can *invent* data a scatter cannot: joining two inverted strikes across a
  refused one draws a vol that does not exist. The curves are therefore built over the strikes
  *listed* that day with `None` at each refusal and `connectgaps` off, so the gap renders as a
  visible break (AD-9).
- **`SMILE_MARGIN` puts the legend below the plot.** Nine expiries in a horizontal legend are
  far too wide to share the top band with a caption on a 5-column tile — they overprinted on
  the first build. Bottom is free, and it is the arrangement `settle_vs_trade_figure` already
  uses. `as_panel_figure` takes a `margin` for exactly this reason: the 30px tile default is
  right for a tile and wrong for a figure still carrying captions, and an annotation pushed
  above the paper does not error, it just stops drawing — which is how FR-11's assumptions
  vanished from the deliverable while every test stayed green (T-17).
  `test_every_caption_fits_inside_the_margin_reserved_for_it` now does that arithmetic for
  every panelised figure. It is the one figure on the page that is a *model output* rather than a
  measurement, so it says so twice: the panel note carries the model and the rate, and the
  figure's own caption carries every assumption plus "not a tradable price". That caption
  lives inside the figure because that is the only part which survives onto the static page,
  and CI greps the built HTML for it.
- **The X ruler drives both 3D/2D panels, not just the hero** (T-43). The surface and the
  smile derived from it must never be read on different axes, so the hero's chip switches
  both and they open on the same one. Dollars at load: panels [2], [5], [6] and [7] all carry
  dollar strike axes and are not affected by the chip, so opening in K keeps the whole page in
  one unit, and one click rebases the two that can be rebased.
- **The as-of slider drives every panel**, not just the hero (T-42/AD-5). Panel [2] is the
  deliberate exception: the underlying is 12 weeks of context, and re-cutting it per date
  would destroy the very thing it is there to show. Everything else — the scatter, the spread
  grid, both occupancy grids, and all six readouts — follows the slider, and the command bar's
  as-of moves with it. A page that showed two dates at once was the defect this closed.
- **The X ruler is a chip *inside* the plot, top-left** (FR-10, T-16). Switching the axis
  between raw strike and `K / S` is a change of units on one axis, so it belongs *on* that
  figure, naming the mode currently shown. It is a dropdown rather than a button pair because
  the closed control states the mode, and because one chip fits where two would not.
  It shipped in the band *above* the plot and the PO found it overlapping its neighbours
  (2026-09-04). That band is full: title, caption and legend already stack there, and Plotly's
  modebar floats over the top-right on top of them — a fourth tenant was always going to
  collide at some width. Inside is also where it belongs by meaning: it relabels an axis of
  *this* scene, so it should read as part of the chart, not as page chrome. **Top-left**
  specifically — the modebar owns the top-right, and the 3D cloud hangs below centre, so that
  corner is empty on every date in the panel. `MENU_X` / `MENU_Y` are tokens, and
  `test_the_axis_menu_sits_inside_the_plot_not_in_the_crowded_band_above` keeps it out of the
  band it came from.
  The colour scheme is forced rather than chosen: a Plotly menu has one font colour for every
  state and plotly.js paints the highlighted row `MENU_ACTIVE_BG` with no override, so the
  type has to clear AA on that near-white *and* on our own ground. Amber type fails there
  (1.7:1); dark type on an amber chip clears both, and `test_the_axis_menu_is_legible_in_both_of_its_states`
  measures it off `theme.menu()` itself.
- **The next step in the same direction — taken 2026-09-04 (T-18)** — is FR-12's spot plane
  at `K = S`, which puts spot *inside* the surface rather than beside it. The two compose:
  adjacency first, plane second. In K/S it stands on 1.00, so the plane and the axis say the
  same thing two ways.
- **The band above a plot stacks: legend, then caption, then title.** A horizontal legend
  anchored at `y=1.0` is roughly 0.05 of the plot area tall, so a caption at 1.02 or 1.045
  lands *inside* it and the two print over each other — the hero shipped that way, with its
  "drag the slider…" line running through the legend swatches. Figures with a top legend put
  their caption at `CAPTION_Y_OVER_LEGEND` (1.12) and reserve `HERO_MARGIN` /
  `HERO_MARGIN_WITH_SLIDER` for the stack. Asserted by
  `test_a_caption_never_shares_the_band_with_a_top_legend`.
- **A caption says only what no other chrome says.** The hero's caption was three clauses
  long and two of them repeated its panel header note. It is now the AD-9 point alone —
  *the translucent sheet is interpolated, not a market* — which also stopped it running the
  full width of the plot.
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
6. **A reference is not a series** (FR-12). The spot plane wears neither a data hue nor the
   amber, carries no colorbar, and stays fainter than the sheet it cuts through.
7. **Nothing is drawn in the band above a plot** (T-47). Captions are HTML in the panel, so
   they wrap; a figure that draws its own text there will collide with a wrapping legend at
   some width, and *some width* always arrives.

All seven are asserted in `tests/test_theme.py`. FR-8's acceptance criteria were three
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
| 2026-09-04 | **The page holds its shape at every width (T-47).** A 14-viewport audit found 131 layout defects, one of them at every width. Three changes, all PO-chosen: **captions are HTML** in the panel, not annotations in the plot, so they wrap instead of colliding or clipping — that band is now empty by rule, and `CAPTION_Y*` / `LEGEND_ROW` / `LEGEND_BOX_PAD` / `LEGEND_ENTRIES_PER_ROW` / `theme.caption()` are deleted along with the arithmetic that policed them; a **width floor** (`FIGURE_MIN_WIDTH`, `HERO_MIN_WIDTH`) below which a panel scrolls rather than squeezing a figure into a shape its own chrome cannot fit; and a **third grid band** at `BREAK_TWO_COL` (1400px) so a 1366px laptop stops crowding the 6+4 split. The Reflex app now renders this stylesheet and these class names instead of restating the chrome as inline props — it had no breakpoints at all — so `PANEL_STYLE` and `PANEL_HEADER_STYLE` are gone. Audit after: 0 defects across 14 widths. |
| 2026-09-04 | **FR-12's spot plane (T-18).** One new palette entry, `SPOT_PLANE` — slate, deliberately outside both the data and the chrome families, because the plane is a *ruler* and has to read as neither (§3, rule 6). It is also the hero's **seventh** legend entry: the legend wrapped to two rows and the caption at `CAPTION_Y_OVER_LEGEND` printed over its panel — the 2026-09-02 defect below arriving by a route a single token could not see. The clearance a caption needs depends on how many entries the legend has, so it is now `LEGEND_ROW` + `LEGEND_BOX_PAD` arithmetic with a token per row count (`CAPTION_Y_OVER_LEGEND_2`), and the test does the sum — deriving the row count from the figure's own entries via `LEGEND_ENTRIES_PER_ROW` rather than from a number a human typed, since the entry count is exactly what changed (T-46). |
| 2026-09-02 | Adopted. First pass shipped ice-blue chrome and a single-column layout; the PO corrected both — "Bloomberg" meant the **page layout**, and the font colours needed to change. Amber type and the panel grid replaced them; puts moved off amber onto the blue-shift rule (§3). Navy ground unchanged throughout. |
| 2026-09-02 | PO asked to pair the underlying with the price surface. Grid moved from 2 columns to 10 so the hero row could be 7/3 rather than an even split; the remaining four figures re-flowed 5+5 across two rows. |
| 2026-09-02 | PO caught three defects by eye. Put markers were unreadable (open symbols, and hues derived as near-shades of their calls) — puts re-hued to violet/green, all markers filled (§3). The mark-vs-print scatter drew one unlabelled array-coloured trace, so the puts read as missing — split into named Calls/Puts traces with a legend. And the hero row wasted vertical space — height 760 → 600 plus `align-items:start` (§5). All three now have tests. |
| 2026-09-04 | PO: the X-ruler chip overlapped its neighbours in the band above the plot. Moved **inside** the plot area, top-left, behind the `MENU_X`/`MENU_Y` tokens and a test that keeps it out of that band (§5). |
| 2026-09-04 | **PO reversed the IV panel's form and position (T-45).** The 3D scatter "just looks like a bunch of scattered points — I can't tell what it's trying to tell me", and the panel was too far from the surface it derives from. It is now a **2D smile** (IV vs `K / S`, one curve per expiry, sequential `EXPIRY_RAMP`) sitting at **[3]**, directly under the hero and beside mark-vs-print; spread moved to full width so the occupancy pair survives. Retired `SCENE_ASPECT_WIDE`, `SCENE_CAMERA_WIDE` and `WIDE_FIGURE_MARGIN` — the three tokens the 3D form had needed — and added `EXPIRY_RAMP`, `SMILE_MARGIN`, `SMILE_LEGEND_Y`, `SMILE_LINE_WIDTH`, `SMILE_MARKER_SIZE`. Three things were again visible only in the render: the legend overprinted the caption, the assumptions line ran off a 5-column tile, and the panel header wrapped and left the row 17px ragged. |
| 2026-09-04 | FR-11's IV surface added as panel **[7]**, full width at hero height, closing the page (T-17) — **superseded the same day by the row above**. Colour was free (it reused the mark hues and the circle glyph) but the geometry was not: a 2.6:1 panel needed three new measurements. Both of its defects were caught by looking at the built page rather than by a test — the tile margin clipped the assumptions caption off the canvas, and the hero's near-cubic scene left the cloud adrift in empty navy. |
| 2026-09-04 | FR-10's X-ruler toggle added to the hero (T-16). New chrome element: an amber dropdown chip at the right of the caption band. Its dark-on-amber scheme is forced by plotly.js's unthemeable `MENU_ACTIVE_BG` highlight, which amber type cannot clear (§3, §5). |
| 2026-09-03 | PO asked whether the spread chart should follow the slider. It did not — nor did any supporting panel — so the page showed two as-of dates at once. Cross-filtering wired in (T-42, AD-5 amendment); readout labels lost their embedded date since the as-of now moves. |
| 2026-09-02 | Hero caption overprinted its own legend — both sat in the band just above the plot. Caption clearance and the top margins are tokens now, and the caption was cut to the one thing the panel header does not already say. |
| 2026-09-02 | **Deploy-only breakage.** The published page rendered the surface and the underlying one column wide: `.osl-w6`/`.osl-w4` were never added when the split moved from 7/3 to 6/4, and an undefined CSS class fails open. Width classes are now generated from `GRID_COLUMNS`; a token-vs-stylesheet test and an orphan-class test over the built page both guard it (§5). |
| 2026-09-02 | PO found the 3D surface overflowing into the mark-vs-print panel in the **dev app**: it was handing un-panelised figures to the terminal grid, so titles doubled with the panel headers and declared heights (640, 460) exceeded the boxes reserved for them (600, 360). App figures now panelise exactly as the builder's do; `price_surface_figure` reads `HERO_FIGURE_HEIGHT`; empty figures declare a height. Guarded by tests (§5). |
| 2026-09-02 | PO refined the correction: the put **colours** were the problem, not the glyphs — square/cross reverted to circle/diamond, so the glyph encodes the role and hue alone separates the rights. Hero row widened from 7/3 to 6/4. |
