"""Design tokens — the single source of visual truth (FR-8, AD-6).

Every colour, font stack, size and layout default the site uses lives here. Nothing else
in the codebase may contain a hex value or a font name: that is FR-8's acceptance test and
it is mechanical, so `tests/test_theme.py` enforces it by grepping the other modules.

Imports nothing project-local, by design (SYSTEM-SPEC §4) — `theme` sits at the bottom of
the dependency graph so both the Plotly builders and the Reflex components can consume it
without a cycle.

The identity
------------
Deep-navy ground, **amber terminal type**, and a dense tiled layout. The Bloomberg reference
is about *arrangement* — numbered panels butted against each other under one command bar,
no floating cards, no scroll of whitespace — and the amber is the type colour that goes with
it. See DESIGN-BRIEF.md §1.

Two of the encodings are not ours to choose — the assignment brief fixes them:

    cyan   = the mark      (README: "Cyan: SETTLE")
    magenta = the print    (README: "Magenta diamonds: TRDPRC_1")

`ACCENT` (amber) is therefore type and chrome only: headings, metric values, panel numbers,
the as-of slider. It never encodes data. Keeping the brand colour out of the data channel is
what lets the page's one argument — the mark is not the print — read at a glance. Puts take
the hues furthest from their own call — violet for the mark, green for the print — with the
glyph fixed by role, so a four-series view stays legible without either right stealing the
other's hue.

Everything is named for its job, not its colour (`MARK`, not `CYAN`): the point of the
indirection is that re-toning the site is a change of values here, not a change of call
sites anywhere.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- surfaces

BG = "#060B16"           # page background — deep navy, near-black under type
SURFACE = "#0C1526"      # cards, panels, figure paper
SURFACE_ALT = "#111E33"  # plot interior, heatmap "no data" floor
BORDER = "#1B2A44"       # hairlines around panels
GRID = "#1F3152"         # axis gridlines — visible, never louder than the data

# --------------------------------------------------------------------------- type colour

TEXT = "#E8E3D9"         # body copy — warm off-white against the cool ground
TEXT_MUTED = "#94897A"   # captions, axis ticks, panel labels
TEXT_INVERSE = "#060B16"  # for text sitting on an accent fill (bar labels)

# --------------------------------------------------------------------------- chrome

ACCENT = "#FFB000"       # amber: headings, metric values, panel numbers, slider
ACCENT_DIM = "#8A6A1E"   # accent at rest: slider track, button, inactive chrome
# NOT ours to choose: plotly.js paints the highlighted row of an `updatemenu` this colour
# and exposes no property for it (`bgcolor` covers only the resting state). It is recorded
# here because it is a ground we really do render type against, so the contrast test can
# measure it like any other pairing — that is what forced the menu's dark-on-amber scheme.
MENU_ACTIVE_BG = "#F4FAFF"

# --------------------------------------------------------------------------- data encodings
#
# Locked by the assignment brief. Changing MARK or TRADE away from cyan/magenta is a
# deviation from the README and needs the PO, not just a nicer palette.

MARK = "#22E3D0"         # the mark (MID_PRICE) — calls. Circle.
MARK_PUT = "#A78BFA"     # the mark — puts. Filled circle, like its call.
TRADE = "#FF2E88"        # TRDPRC_1, someone actually traded — calls. Diamond.
TRADE_PUT = "#3DDC84"    # TRDPRC_1 — puts. Filled diamond, like its call.
TRADE_EDGE = "#FF8FBC"   # outline on trade markers, so a print never dissolves into the sheet

# FR-5's marker-identity invariant is colour *and* symbol, so the symbols are tokens too —
# a restyle that accidentally made both series circles would defeat the figure.
#
# The glyph carries the ROLE and nothing else: a circle is a mark, a diamond is a print,
# whichever right it belongs to. Calls and puts are separated by hue alone (PO, 2026-09-02).
# A brief attempt at square/cross for the puts encoded the right in the glyph too and made
# the legend four shapes deep for two ideas.
#
# All four are FILLED. The puts were open variants originally and were unreadable — a 4px
# ring on a dark ground, seen through a 3D projection, is a smudge rather than a point.
SYMBOL_MARK = "circle"
SYMBOL_MARK_PUT = "circle"
SYMBOL_TRADE = "diamond"
SYMBOL_TRADE_PUT = "diamond"
SIZE_MARK = 4
SIZE_TRADE = 6

# The interpolated sheet is an assumption, not a market (AD-9): it stays translucent and
# ramps toward its own series' colour so it reads as "the mark, smeared", never as data.
SHEET_OPACITY = 0.26
SHEET_SCALE = [[0.0, "#0A2E3A"], [0.5, "#12897F"], [1.0, MARK]]
SHEET_SCALE_PUT = [[0.0, "#1B1435"], [0.5, "#5B45A0"], [1.0, MARK_PUT]]

# FR-12's spot plane. It is the one object in the scene that is neither a market nor a model
# — a ruler standing where the money is on the as-of date — so it takes neither a series hue
# nor the chrome amber. A cool slate reads as *reference* beside four saturated data colours,
# and it is far enough from all of them (and from the amber type) that a reader never has to
# ask whether the wall is a series.
#
# Fainter than the interpolated sheet, deliberately. The sheet lies over the cloud in one thin
# layer; the plane stands side-on *through* the middle of it, so at the sheet's opacity it
# would fog every point behind it. It must be visible without becoming the thing you look at.
SPOT_PLANE = "#7FA8D9"
SPOT_PLANE_OPACITY = 0.18
SPOT_PLANE_SCALE = [[0.0, SPOT_PLANE], [1.0, SPOT_PLANE]]  # flat: it encodes no magnitude

# --------------------------------------------------------------------------- semantic status

POSITIVE = "#2FD4A0"     # underlying up-candle
NEGATIVE = "#FF4D6D"     # underlying down-candle
WARN = "#FFB000"         # the terminal's warning colour — shares the accent's amber
NEUTRAL = "#6E8CB8"      # "both mark and print": the uninteresting middle bar, so it is the
                         # one bar that takes neither a data colour nor the chrome amber

# Tight-and-tradeable through to the-midpoint-is-a-guess. Sequential in lightness so it
# survives being read quickly, and lands on the same amber/red the status tokens use.
SPREAD_SCALE = [[0.0, "#0E3446"], [0.35, MARK], [0.7, WARN], [1.0, NEGATIVE]]

# The put rule, second attempt. "Each right's put is its call's colour shifted toward blue"
# was wrong by construction: it made puts *deliberately similar* to their calls, and on the
# scatter the cyan calls and sky puts read as one cloud — the puts looked missing. Puts now
# take the two hues furthest from both locked colours and from the amber type:
#
#   mark   cyan #22E3D0 (calls)  /  violet #A78BFA (puts)   — 83 deg apart
#   print  magenta #FF2E88 (calls) / green #3DDC84 (puts)   — 150 deg apart
#
# Separation is largest *within* a role, which is the comparison the page is actually asking
# a reader to make — and since the glyph is fixed by role, hue is the only channel telling
# the two rights apart, so it has to do the work alone. Amber stays out of the data channel.

# --------------------------------------------------------------------------- typography

# Space Grotesk for display, JetBrains Mono for every number, Inter for prose. Each stack
# falls back all the way to a system face, so the page is legible before — or without —
# the webfont. GOOGLE_FONTS_LINK is the only network dependency the styling adds.
FONT_DISPLAY = "'Space Grotesk', 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif"
FONT_BODY = "'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, sans-serif"
FONT_MONO = (
    "'JetBrains Mono', ui-monospace, SFMono-Regular, 'Cascadia Mono', "
    "Menlo, Consolas, monospace"
)

# One URL, two consumers: Reflex takes it as a stylesheet, the static builder wraps it in
# <link> tags. The stacks above degrade to system faces if it never loads.
GOOGLE_FONTS_CSS = (
    "https://fonts.googleapis.com/css2?"
    "family=Space+Grotesk:wght@500;700&"
    "family=Inter:wght@400;600&"
    "family=JetBrains+Mono:wght@400;700&display=swap"
)

GOOGLE_FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    f'<link rel="stylesheet" href="{GOOGLE_FONTS_CSS}">'
)

SIZE_TITLE = 16
SIZE_AXIS_TITLE = 12
SIZE_TICK = 10
SIZE_CAPTION = 11
SIZE_LEGEND = 11
TRACKING = "2px"         # letter-spacing on the wordmark

# --------------------------------------------------------------------------- layout

TRANSPARENT = "rgba(0,0,0,0)"  # a legend backdrop that must not paint

LEGEND_Y = 1.0

# **Captions are HTML, not annotations** (T-47). They used to live inside the figure, in
# `paper` coordinates, in the band above the plot — sharing it with the title and a legend
# that GROWS as the figure narrows. A Plotly annotation is one unwrappable line of text
# pinned to a fraction of a box whose pixel size changes with the viewport, so that band was
# a standing collision waiting for a width: the hero's caption printed through its own legend
# (2026-09-02), the IV assumptions line was clipped clean off the canvas (T-17), then ran off
# a 5-column tile (T-45), then printed over a legend that had wrapped to two rows (T-18) —
# and a width audit found it escaping the figure entirely below 1440px and the hero's legend
# reaching SIX rows on a phone. Every one of those is the same defect wearing a new width.
#
# A caption in the panel's own HTML wraps like any other text, can never overlap anything,
# and cannot be clipped. The tokens that used to position it — CAPTION_Y,
# CAPTION_Y_OVER_LEGEND(_2), LEGEND_ROW, LEGEND_BOX_PAD, LEGEND_ENTRIES_PER_ROW — are gone
# with it, along with the arithmetic tests that policed them. `.osl-caption` below is the
# whole of the styling now, and both renderings read it.

# FR-10's axis control sits *inside* the plot, top-left, rather than in the band above it.
# Everything at or above LEGEND_Y is already spoken for (legend, caption, title) and Plotly's
# modebar floats over the top-right, so a control placed up there collides at some widths.
# Both values are inside the plot area by construction: y < LEGEND_Y and x near the left edge.
MENU_X = 0.01
MENU_Y = 0.98

# The top margin holds the title and the legend — the caption left this band in T-47, so it
# is two tenants now, not three. The dev hero shows one right at a time and its legend is a
# single row; the published one carries seven entries and wraps to three rows at
# FIGURE_MIN_WIDTH, which is what 116 reserves. Sized for the WORST case rather than tuned to
# one width, so the slack at 1600px is deliberate: a margin that fits only the width it was
# measured at is the defect this whole task was about.
HERO_MARGIN = dict(l=10, r=10, t=80, b=12)
HERO_MARGIN_WITH_SLIDER = dict(l=8, r=8, t=116, b=84)

# FR-11's smile colours by expiry, and expiry is an ORDERED variable — near-dated through
# far-dated — so it takes a sequential ramp rather than a categorical palette: the reader can
# tell which end of the ladder a curve sits on without consulting the legend.
#
# The ramp runs between the two MARK hues. Every point on that panel is inverted from the
# mark and there is no print series beside it for cyan to be mistaken for, so this introduces
# no new hue and leaves the README-locked cyan-mark / magenta-print encoding untouched (§3).
EXPIRY_RAMP = (MARK, MARK_PUT)

# The smile puts its legend BELOW the plot: a horizontal legend of nine expiries is far too
# wide for the top band of a 5-column tile, and bottom is free — the same arrangement
# `settle_vs_trade_figure` uses. Its top margin was 58 to hold two caption lines; those are
# HTML now (T-47) and the band above the plot is empty, so it is back to a tile's clearance.
SMILE_MARGIN = dict(l=56, r=18, t=26, b=88)
SMILE_LEGEND_Y = -0.30

SMILE_LINE_WIDTH = 1.6
SMILE_MARKER_SIZE = 5


def _hex_to_rgb(value: str) -> tuple:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def expiry_colors(n: int) -> list:
    """``n`` colours stepping across :data:`EXPIRY_RAMP`, near-dated first.

    Sampled rather than listed so the ladder restyles with the ramp and cannot fall out of
    step with the number of expiries in the panel (AD-6).
    """
    if n <= 0:
        return []
    lo, hi = (_hex_to_rgb(c) for c in EXPIRY_RAMP)
    if n == 1:
        return [EXPIRY_RAMP[0]]
    out = []
    for i in range(n):
        t = i / (n - 1)
        out.append("#%02X%02X%02X" % tuple(round(a + (b - a) * t) for a, b in zip(lo, hi)))
    return out


TEMPLATE = "plotly_dark"  # base only — every colour below is overridden explicitly


def figure_layout(**overrides) -> dict:
    """Layout defaults every figure starts from (AD-6).

    Merging shallowly is deliberate: call sites pass whole sub-dicts (`scene=`, `title=`,
    `legend=`) built from the helpers below, so a deep merge would only ever surprise.
    """
    base = dict(
        template=TEMPLATE,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE_ALT,
        font=dict(color=TEXT, family=FONT_BODY, size=SIZE_AXIS_TITLE),
        margin=dict(l=56, r=24, t=64, b=48),
        hoverlabel=dict(
            bgcolor=SURFACE,
            bordercolor=BORDER,
            font=dict(family=FONT_MONO, size=SIZE_CAPTION, color=TEXT),
        ),
    )
    base.update(overrides)
    return base


def title(text: str, **overrides) -> dict:
    """Figure title: display face, left-aligned to the panel edge like a terminal header."""
    spec = dict(
        text=text,
        font=dict(size=SIZE_TITLE, color=TEXT, family=FONT_DISPLAY),
        x=0.02,
        xanchor="left",
        y=0.98,
        yanchor="top",
    )
    spec.update(overrides)
    return spec


def axis(title_text: str | None = None, **overrides) -> dict:
    """2D cartesian axis. Numbers are monospaced so columns of ticks line up."""
    spec: dict = dict(
        gridcolor=GRID,
        zeroline=False,
        tickfont=dict(size=SIZE_TICK, color=TEXT_MUTED, family=FONT_MONO),
    )
    if title_text is not None:
        spec["title"] = dict(
            text=title_text, font=dict(size=SIZE_AXIS_TITLE, color=TEXT, family=FONT_BODY)
        )
    spec.update(overrides)
    return spec


def scene_axis(title_text: str, **overrides) -> dict:
    """One axis of a 3D scene — the panel walls behind the point cloud."""
    spec = dict(
        title=dict(
            text=title_text, font=dict(size=SIZE_AXIS_TITLE, color=TEXT, family=FONT_BODY)
        ),
        backgroundcolor=SURFACE_ALT,
        gridcolor=GRID,
        showbackground=True,
        zeroline=False,
        tickfont=dict(size=SIZE_TICK, color=TEXT_MUTED, family=FONT_MONO),
    )
    spec.update(overrides)
    return spec


def scene(**overrides) -> dict:
    """3D scene defaults: near-dated toward the viewer is set by the caller, not here."""
    spec = dict(
        bgcolor=BG,
        aspectmode="manual",
        aspectratio=dict(x=1.15, y=1.0, z=0.7),
        camera=dict(eye=dict(x=1.55, y=-1.45, z=0.85), center=dict(x=0, y=0, z=-0.05)),
    )
    spec.update(overrides)
    return spec


def legend(**overrides) -> dict:
    spec = dict(
        orientation="h",
        yanchor="bottom",
        y=LEGEND_Y,
        x=1.0,
        xanchor="right",
        bgcolor=_rgba(BG, 0.72),
        bordercolor=BORDER,
        borderwidth=1,
        font=dict(size=SIZE_LEGEND, color=TEXT, family=FONT_BODY),
        itemsizing="constant",
    )
    spec.update(overrides)
    return spec


def slider(**overrides) -> dict:
    """The published page's as-of control (T-15) — chrome, so it takes the accent."""
    spec = dict(
        pad=dict(t=8, b=8),
        x=0.02,
        len=0.96,
        currentvalue=dict(
            prefix="As-of  ", font=dict(size=13, color=ACCENT, family=FONT_MONO)
        ),
        bgcolor=ACCENT_DIM,
        activebgcolor=ACCENT,
        bordercolor=BORDER,
        font=dict(size=9, color=TEXT_MUTED, family=FONT_MONO),
        tickcolor=BORDER,
    )
    spec.update(overrides)
    return spec


def menu(**overrides) -> dict:
    """A Plotly dropdown — the published page's second native control (FR-10, T-16).

    An amber chip with inverse type, the same affordance the Reflex app's Reload button uses.
    It is a dropdown rather than a button pair for two reasons: the closed control names the
    mode currently shown (FR-10 asks for exactly that), and one chip fits where two would not.

    **It sits INSIDE the plot area, top-left** (PO, 2026-09-04). The band above a plot is
    already three deep — title, caption, legend — plus Plotly's own modebar hovering at the
    top-right, and a fourth element put in there overlapped its neighbours at some widths.
    Inside is also where it belongs by meaning: it relabels an axis of *this* scene, so it
    reads as part of the chart rather than as page chrome. Top-**left** specifically, because
    the modebar owns the top-right corner and the 3D cloud hangs below centre, leaving that
    corner empty at every date in the panel.

    The colour scheme is forced, not chosen. A menu has ONE font colour for every state, and
    plotly.js paints the highlighted row `MENU_ACTIVE_BG` regardless of the theme — so the
    type has to be legible on that near-white *and* on our own ground. Amber type fails there
    (1.7:1); dark type on amber clears AA on both. Both pairings are pinned in
    `tests/test_theme.py`.
    """
    spec = dict(
        type="dropdown",
        direction="down",
        showactive=True,
        x=MENU_X,
        xanchor="left",
        y=MENU_Y,
        yanchor="top",
        pad=dict(l=4, r=4, t=4, b=4),
        bgcolor=ACCENT,
        bordercolor=BORDER,
        borderwidth=1,
        font=dict(size=SIZE_LEGEND, color=TEXT_INVERSE, family=FONT_MONO),
    )
    spec.update(overrides)
    return spec


def _rgba(hex_color: str, alpha: float) -> str:
    """`#RRGGBB` + alpha -> a Plotly `rgba()` string, so translucency needs no second token."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


# --------------------------------------------------------------------------- layout metrics
#
# The terminal arrangement (DESIGN-BRIEF §5): one command bar, a readout strip, then numbered
# panels butted against each other on a hairline grid. Tight gutters and square corners are
# the whole point — rounded cards floating in whitespace is the look this replaced.

GUTTER = "1px"           # panels are separated by a rule, not by space
# A tiled figure gives its title back to the panel header, so it needs far less top room
# than a standalone one. Bottom keeps space for the caption line and tick labels.
PANEL_FIGURE_MARGIN = dict(l=54, r=18, t=30, b=46)
PANEL_FIGURE_HEIGHT = 360

# The hero row is 7/10 surface + 3/10 underlying. Both panels read this, so they cannot
# drift apart; `static_surface_figure` uses it as its own height.
#
# Was 760. A 3D scene does not gain much past ~600 — the extra height went into empty scene
# background — while the sidecar candlestick, which needs far less, was stretched to match
# and left a visibly dead half-panel underneath. Shorter here is strictly better: the whole
# page gets shorter and nothing is squeezed. See also `align-items:start` in PAGE_CSS.
HERO_FIGURE_HEIGHT = 600
# NOT width-dependent, and it cannot be. In the two-column band the hero runs the full row,
# and a 3D scene keeps its own proportions (`aspectmode="manual"`), so the cloud sits in a
# wider box with navy either side. Giving the container more height there does NOT fix it:
# plotly only sizes a figure to its container for dimensions the layout leaves unset, and
# this one is set — a CSS override just adds empty box below the plot. Measured 2026-09-04.
# The honest options are a resize listener (more custom JS than this page is allowed) or
# living with a roomier hero between 1101 and 1399px. We live with it.

# Panel widths in grid columns. Ten divides cleanly into both 6+4 (the hero row) and 5+5
# (everything else), which a 2- or 12-column grid does not.
#
# The hero row was 7/3 and is now 6/4 (PO, 2026-09-02): the candlestick was too narrow to
# read at 3, and the surface loses little going from 7 to 6 — its slider still has room for
# 53 steps, which is the constraint that stops this going to 5/5.
GRID_COLUMNS = 10
W_HERO, W_SIDECAR, W_HALF, W_FULL = 6, 4, 5, 10

# Three layout bands, not two (T-47). The single 1100px breakpoint left a wide gap where the
# 6+4 and 5+5 splits were cramped but had not yet collapsed — a 1366x768 laptop, the most
# common screen there is, sat squarely in it: panel headers wrapped and left rows ragged, and
# the IV panel's assumptions line ran off its tile. Below MID the grid drops to two equal
# columns with the hero across both; below NARROW everything is one column.
#
#   >= 1400   the full 10-column grid   6+4 / 5+5 / 10 / 5+5
#   1101-1399 two equal columns         hero full, then pairs — the occupancy grids stay paired
#   <= 1100   one column
BREAK_TWO_COL = 1400
BREAK_ONE_COL = 1100
MID_COLUMNS = 2

# A figure is never rendered narrower than this; its panel body scrolls instead. Plotly lays
# a legend, a slider and an axis out in PIXELS inside a box we size in percent, so below some
# width the chrome simply does not fit however carefully it is placed — 53 slider steps and a
# seven-entry legend need room that a 380px phone does not have. A floor turns "the chart is
# broken" into "the chart scrolls", which is the honest trade (AD-9's posture, applied to
# layout). The hero carries both the slider and the widest legend, so it needs more.
FIGURE_MIN_WIDTH = 520
HERO_MIN_WIDTH = 680
PAGE_PAD = "14px"
PANEL_PAD = "10px 12px 12px 12px"
HEADER_PAD = "7px 12px"


# --------------------------------------------------------------------------- HTML / Reflex
#
# The same tokens, shaped for the two non-Plotly consumers: the Reflex page's component
# props and the static builder's inline styles. Both render the identical panel chrome, so
# the checkpoint demo and the graded page look like one product.

# The Reflex page used to restate the panel chrome here as component props while the static
# builder used the classes below. Two spellings of one design is how the published page once
# shipped with the hero one column wide while `reflex run` looked perfect -- and, later, how
# the Reflex app ended up with no responsive breakpoints at all. Both pages now render the
# same class names against PAGE_CSS, so these props are gone (T-47).

# Every width from 1..GRID_COLUMNS gets a class, generated rather than listed. Hand-listing
# them is how the published page broke on 2026-09-02: the hero split moved from 7/3 to 6/4,
# the tokens were updated and the stylesheet was not, so `.osl-w6` and `.osl-w4` did not
# exist and both panels silently fell back to one column. The Reflex app styles its panels
# inline, so it kept working — the defect only ever appeared on the deployed page.
_WIDTH_CLASSES = "\n".join(
    f"  .osl-w{n} {{ grid-column:span {n}; }}" for n in range(1, GRID_COLUMNS + 1)
)
_WIDTH_SELECTORS = ", ".join(f".osl-w{n}" for n in range(1, GRID_COLUMNS + 1))


PAGE_CSS = f"""
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; background:{BG}; color:{TEXT};
    font-family:{FONT_BODY}; font-size:13px; padding:{PAGE_PAD};
  }}

  /* ---- command bar: wordmark left, instrument identity right ---- */
  .osl-bar {{
    display:flex; align-items:baseline; justify-content:space-between; gap:16px;
    flex-wrap:wrap; background:{SURFACE}; border:1px solid {BORDER};
    padding:10px 14px;
  }}
  .osl-wordmark {{
    font-family:{FONT_DISPLAY}; font-weight:700; font-size:19px;
    letter-spacing:{TRACKING}; color:{ACCENT}; text-transform:uppercase;
  }}
  .osl-ident {{
    font-family:{FONT_MONO}; font-size:12px; color:{TEXT_MUTED};
    letter-spacing:0.5px; text-align:right;
  }}
  .osl-ident b {{ color:{TEXT}; font-weight:700; }}

  /* ---- readout strip: KPIs butted together under the bar ---- */
  .osl-readouts {{
    display:grid; grid-template-columns:repeat(auto-fit, minmax(158px, 1fr));
    gap:{GUTTER}; background:{BORDER}; border:1px solid {BORDER}; border-top:0;
    margin-bottom:10px;
  }}
  .osl-readout {{ background:{SURFACE}; padding:9px 12px 10px 12px; }}
  .osl-readout-label {{
    color:{TEXT_MUTED}; font-size:10px; letter-spacing:1.2px; text-transform:uppercase;
    /* Wraps rather than truncating: "Median |mark - trade|" was being cut to "Median |mark"
       below 1024px, which reads as a different statistic. The strip is a grid, so a
       two-line label lifts every cell in the row together and nothing goes ragged. */
    overflow-wrap:anywhere;
  }}
  .osl-readout-value {{
    color:{ACCENT}; font-family:{FONT_MONO}; font-size:20px; font-weight:700;
    margin-top:3px; line-height:1.15;
  }}

  /* ---- the panel grid: 10 columns, so 7+3 and 5+5 both divide cleanly ---- */
  .osl-grid {{
    display:grid; grid-template-columns:repeat({GRID_COLUMNS}, minmax(0, 1fr)); gap:10px;
    /* Never stretch a panel to its row's height: a panel taller than its figure is dead
       navy under a chart, which reads as a rendering fault rather than as spacing. */
    align-items:start;
  }}
{_WIDTH_CLASSES}
  /* The hero names itself rather than being recognised by its span, because the span changes
     between bands and the identity does not. Defined at BASE level, not only inside a media
     query: a class that exists only in an override is how `.osl-w6` went missing from the
     published page while the Reflex app looked perfect. */
  .osl-hero {{ grid-column:span {W_HERO}; }}
  /* Two equal columns: the hero goes full width and everything else pairs off, so the
     occupancy grids — the one pair whose whole point is being compared — stay side by side.
     Without this band a 1366px laptop kept the 6+4 split and crowded every panel in it. */
  @media (max-width: {BREAK_TWO_COL - 1}px) and (min-width: {BREAK_ONE_COL + 1}px) {{
    .osl-grid {{ grid-template-columns:repeat({MID_COLUMNS}, minmax(0, 1fr)); }}
    {_WIDTH_SELECTORS} {{ grid-column:span 1; }}
    /* The hero, its sidecar and the full-width panel each take the whole row, which leaves
       the two genuine PAIRS -- smile beside mark-vs-print, and the two occupancy grids --
       side by side, where comparing them is the entire reason both are shown. Pairing the
       sidecar with a tile instead put a 600px candlestick beside a 360px one and left 224px
       of dead navy under the short one. */
    .osl-hero, .osl-w{W_SIDECAR}, .osl-w{W_FULL} {{ grid-column:span {MID_COLUMNS}; }}
    /* Half a 1280px screen is narrow enough that FR-11's assumptions line wraps to three
       rows while its row-mate's caption still fits two, which put the pair 16px apart.
       Reserve the taller here rather than everywhere: at full width two lines is the most
       any caption needs, and 16px of dead navy under all seven panels to fix a band 300px
       wide is a bad trade. */
    .osl-panel .osl-caption {{ min-height:calc(3 * 1.45em + 8px); }}
  }}
  /* Below this the adjacency is not worth the squeeze — everything goes full width. */
  @media (max-width: {BREAK_ONE_COL}px) {{
    .osl-grid {{ grid-template-columns:minmax(0, 1fr); }}
    {_WIDTH_SELECTORS}, .osl-hero {{ grid-column:span 1; }}
  }}

  .osl-panel {{ background:{SURFACE}; border:1px solid {BORDER}; min-width:0; }}
  .osl-panel-head {{
    display:flex; align-items:baseline; justify-content:space-between; gap:12px;
    background:{SURFACE_ALT}; border-bottom:1px solid {BORDER}; padding:{HEADER_PAD};
  }}
  .osl-panel-n {{
    color:{ACCENT}; font-family:{FONT_MONO}; font-size:11px; font-weight:700;
    margin-right:8px;
  }}
  .osl-panel-name {{
    font-family:{FONT_DISPLAY}; font-weight:500; font-size:12px;
    letter-spacing:1.4px; text-transform:uppercase; color:{TEXT};
  }}
  .osl-panel-note {{
    font-family:{FONT_MONO}; font-size:10px; color:{TEXT_MUTED}; text-align:right;
    /* One line, always. A wrapped note makes its panel taller than the one beside it, and
       on a hairline grid where panels deliberately do not stretch, 17px of that reads as a
       rendering fault. It truncates instead; the caption below carries the same ground. */
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0;
  }}
  .osl-panel-head > div:first-child {{ white-space:nowrap; }}

  /* ---- the caption: the "how to read this" line, in HTML so it can WRAP ---- */
  .osl-caption {{
    color:{TEXT_MUTED}; font-family:{FONT_BODY}; font-size:{SIZE_CAPTION}px;
    line-height:1.45; padding:8px 12px 0 12px;
    /* Two lines' worth, always. FR-11's panel carries two caption lines and its row-mate
       carries one, so without this the pair sat 16px apart -- and on a hairline grid where
       panels deliberately do not stretch, a small mismatch between two panels that should
       match reads as a rendering fault. Reserving the taller of the two keeps every row
       level; a caption that wraps further still grows, which is the correct trade. */
    min-height:calc(2 * 1.45em + 8px);
  }}
  .osl-caption-line {{ display:block; }}

  /* Below the floor the panel scrolls rather than squeezing a figure into a shape where its
     own legend and slider collide. See FIGURE_MIN_WIDTH. */
  .osl-panel-body {{ padding:{PANEL_PAD}; overflow-x:auto; }}
  .osl-figure {{ min-width:{FIGURE_MIN_WIDTH}px; }}
  .osl-figure-hero {{ min-width:{HERO_MIN_WIDTH}px; }}

  /* ---- prose blocks sit in the grid like any other panel ---- */
  .osl-note {{ color:{TEXT}; font-size:12.5px; line-height:1.55; }}
  .osl-note b {{ color:{ACCENT}; font-weight:600; }}

  .osl-warn {{
    background:{_rgba(NEGATIVE, 0.14)}; border:1px solid {NEGATIVE}; color:{NEGATIVE};
    padding:10px 14px; margin-bottom:10px; font-weight:600;
    font-family:{FONT_MONO}; font-size:12px;
  }}
"""
