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


def caption(text: str, y: float = 1.02, **overrides) -> dict:
    """The one-line "how to read this" note that sits above each figure."""
    spec = dict(
        text=text,
        xref="paper",
        yref="paper",
        x=0.0,
        y=y,
        xanchor="left",
        yanchor="bottom",
        showarrow=False,
        font=dict(size=SIZE_CAPTION, color=TEXT_MUTED, family=FONT_BODY),
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
        y=1.0,
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

# Panel widths in grid columns. Ten divides cleanly into both 6+4 (the hero row) and 5+5
# (everything else), which a 2- or 12-column grid does not.
#
# The hero row was 7/3 and is now 6/4 (PO, 2026-09-02): the candlestick was too narrow to
# read at 3, and the surface loses little going from 7 to 6 — its slider still has room for
# 53 steps, which is the constraint that stops this going to 5/5.
GRID_COLUMNS = 10
W_HERO, W_SIDECAR, W_HALF, W_FULL = 6, 4, 5, 10
PAGE_PAD = "14px"
PANEL_PAD = "10px 12px 12px 12px"
HEADER_PAD = "7px 12px"


# --------------------------------------------------------------------------- HTML / Reflex
#
# The same tokens, shaped for the two non-Plotly consumers: the Reflex page's component
# props and the static builder's inline styles. Both render the identical panel chrome, so
# the checkpoint demo and the graded page look like one product.

PANEL_STYLE = dict(
    bg=SURFACE,
    border=f"1px solid {BORDER}",
    padding="0",
)

PANEL_HEADER_STYLE = dict(
    bg=SURFACE_ALT,
    border_bottom=f"1px solid {BORDER}",
    padding=HEADER_PAD,
    width="100%",
)

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
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
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
  /* Below this the adjacency is not worth the squeeze — everything goes full width. */
  @media (max-width: 1100px) {{
    .osl-grid {{ grid-template-columns:minmax(0, 1fr); }}
    {_WIDTH_SELECTORS} {{ grid-column:span 1; }}
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
  }}
  .osl-panel-body {{ padding:{PANEL_PAD}; }}

  /* ---- prose blocks sit in the grid like any other panel ---- */
  .osl-note {{ color:{TEXT}; font-size:12.5px; line-height:1.55; }}
  .osl-note b {{ color:{ACCENT}; font-weight:600; }}

  .osl-warn {{
    background:{_rgba(NEGATIVE, 0.14)}; border:1px solid {NEGATIVE}; color:{NEGATIVE};
    padding:10px 14px; margin-bottom:10px; font-weight:600;
    font-family:{FONT_MONO}; font-size:12px;
  }}
"""
