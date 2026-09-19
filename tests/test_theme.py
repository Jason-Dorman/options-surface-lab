"""FR-8's acceptance criteria, made mechanical.

FR-8 is accepted when "no color/font literals remain in `*plot.py` or the page outside the
theme module" and "changing one token restyles everything". Both of those are checkable, so
they are checked here rather than eyeballed — an acceptance criterion nobody can run is a
criterion that quietly stops being true (AD-6, SYSTEM-SPEC §10).

The second group guards the constraint FR-8 is *not* allowed to break: the restyle must
leave the mark and the print distinguishable in colour and in symbol (FR-5).
"""

import re
from pathlib import Path

import pytest

from options_surface_lab import theme as T
from options_surface_lab.option_surface_plot import (
    SERIES_STYLE,
    SPOT_PLANE_NAME,
    coverage_heatmap,
    price_surface_figure,
    settle_vs_trade_figure,
    static_surface_figure,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def wide(synthetic_wide):
    return synthetic_wide


@pytest.fixture(scope="module")
def asof(wide):
    """The busiest date — the one both the app and the published page open on."""
    return wide.groupby(wide["date"].dt.normalize()).size().idxmax()

# The modules FR-8 names: the figure builders, the Reflex app, and every static builder —
# plus the shell they share, which is where the panel chrome actually lives from T-79.
#
# **Discovered, not hand-listed** (T-68). DESIGN-BRIEF §6 rule 5 said it itself: "a module
# that emits markup and is not on this list is a module free to hold a colour" — and a list a
# human maintains is exactly how that happens, silently, the first time somebody adds a
# module. Assignment 2 adds `covered_call/plots.py` and `covered_call/page.py` (T-69, T-59),
# and neither can arrive unguarded now. Everything in the package is swept: a module with no
# visual output has no colour literals to lose, so the only cost of over-covering is that a
# pure-logic module is proven clean, and the benefit is that a NEW one cannot be missed.
THEMED_SOURCES = sorted(
    [p for p in (ROOT / "options_surface_lab").rglob("*.py") if p.name != "theme.py"]
    + list(ROOT.glob("build_*.py"))
)


def test_the_themed_source_sweep_reaches_the_modules_that_render():
    """The discovery above is only a guard while it actually finds the renderers.

    A glob that silently matched nothing — a moved package, a renamed builder — would leave
    every literal test passing over an empty parametrisation, which is the shape of a guard
    that cannot fail. So the five modules the rule was written for are named here and the
    sweep must contain all of them.
    """
    names = {p.name for p in THEMED_SOURCES}
    for required in (
        "option_surface_plot.py",
        "options_surface_app.py",
        "page_shell.py",
        "build_preview.py",
        "build_covered_call.py",
    ):
        assert required in names, f"{required} is not in the themed-source sweep"
    assert "theme.py" not in names, "theme.py is where the literals live — it cannot be swept"

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
RGB = re.compile(r"\brgba?\(")
# Font *names*, not the word "font": a stack may only be assembled inside theme.py.
FONT_NAMES = re.compile(
    r"\b(Inter|Space Grotesk|JetBrains Mono|system-ui|sans-serif|monospace|"
    r"ui-monospace|SFMono-Regular|Menlo|Consolas|Helvetica|Roboto|Segoe UI)\b"
)


def _code_lines(path: Path):
    """Source lines with comments and docstring bodies excluded.

    Prose is allowed to say "cyan" or name a typeface; the ban is on values the renderer
    reads. Stripping `#`-comments also stops a hex value in a note from failing the build,
    which would push people to delete the explanation rather than the literal.
    """
    out, in_doc, delim = [], False, ""
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw
        if in_doc:
            if delim in line:
                in_doc = False
                line = line.split(delim, 1)[1]
            else:
                continue
        while True:
            m = re.search(r'"""|\'\'\'', line)
            if not m:
                break
            rest = line[m.end():]
            if m.group(0) in rest:  # docstring opens and closes on this line
                line = line[: m.start()] + rest.split(m.group(0), 1)[1]
                continue
            in_doc, delim = True, m.group(0)
            line = line[: m.start()]
            break
        line = re.sub(r"(?<!['\"])#.*$", "", line)
        if line.strip():
            out.append((i, line))
    return out


@pytest.mark.parametrize("path", THEMED_SOURCES, ids=lambda p: p.name)
def test_no_colour_literals_outside_the_theme(path):
    """FR-8 acceptance: the figures and the pages hold no colours of their own."""
    offenders = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in _code_lines(path)
        if HEX.search(line) or RGB.search(line)
    ]
    assert not offenders, (
        "colour literals must live in theme.py (FR-8 / AD-6):\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("path", THEMED_SOURCES, ids=lambda p: p.name)
def test_no_font_literals_outside_the_theme(path):
    offenders = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in _code_lines(path)
        if FONT_NAMES.search(line)
    ]
    assert not offenders, (
        "font stacks must live in theme.py (FR-8 / AD-6):\n" + "\n".join(offenders)
    )


def test_theme_imports_nothing_project_local():
    """SYSTEM-SPEC §4: theme sits at the bottom of the graph so everything may consume it."""
    src = (ROOT / "options_surface_lab" / "theme.py").read_text(encoding="utf-8")
    assert "options_surface_lab" not in src.replace('"""', "", 1).split('"""', 1)[-1], (
        "theme.py must not import from the project"
    )


def test_one_token_restyles_every_figure(wide, asof, monkeypatch):
    """FR-8's other half: the indirection is real, not decorative.

    Repoint a single token and rebuild — if any figure still paints the old value, some call
    site kept a copy. `figure_layout()` reads the module global at call time, which is what
    makes this work and what a future refactor to captured defaults would silently break.
    """
    sentinel = "#123456"
    monkeypatch.setattr(T, "SURFACE", sentinel)
    fig = coverage_heatmap(wide, asof, cp="C", field="MARK")
    assert fig.layout.paper_bgcolor == sentinel


# ------------------------------------------------------- FR-5 survives the restyle (FR-8)


def test_mark_and_trade_differ_in_colour_and_symbol():
    """The invariant the restyle is forbidden to break, for both rights."""
    for cp in ("C", "P"):
        mark, trade = SERIES_STYLE[(cp, "mark")], SERIES_STYLE[(cp, "trade")]
        assert mark["color"] != trade["color"], f"{cp}: mark and print share a colour"
        assert mark["symbol"] != trade["symbol"], f"{cp}: mark and print share a symbol"

    # and the two rights must not collide with each other either
    assert SERIES_STYLE[("C", "mark")]["color"] != SERIES_STYLE[("P", "mark")]["color"]
    assert SERIES_STYLE[("C", "trade")]["color"] != SERIES_STYLE[("P", "trade")]["color"]


def test_the_brief_s_cyan_and_magenta_are_still_the_data_colours():
    """The README fixes these two encodings; the identity is free everywhere else.

    Hue, not exact hex — the brief says "cyan" and "magenta", not a value. Moving either
    into another part of the wheel is a deviation from the README, so it needs the PO.
    """
    def hue_family(hex_color):
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
        return max(("r", r), ("g", g), ("b", b), key=lambda t: t[1])[0], r, g, b

    _, r, g, b = hue_family(T.MARK)
    assert g > r and b > r, f"MARK {T.MARK} is no longer cyan (README)"
    _, r, g, b = hue_family(T.TRADE)
    assert r > g and b > g, f"TRADE {T.TRADE} is no longer magenta (README)"


def test_the_chrome_colour_is_never_a_data_colour():
    """Amber is type (DESIGN-BRIEF §2). A marker wearing the heading colour reads as chrome.

    This is why the puts moved off amber when the type scheme changed — the earlier palette
    had `TRADE_PUT` and `ACCENT` on the same hue, which was invisible until amber became the
    heading colour and the two collided.
    """
    data_colours = {T.MARK, T.MARK_PUT, T.TRADE, T.TRADE_PUT, T.NEUTRAL}
    assert T.ACCENT not in data_colours, "the chrome colour leaked into the data channel"
    assert len(data_colours) == 5, "two data series share a colour"


def test_the_interpolated_sheet_stays_subordinate(wide, asof):
    """AD-9 / FR-8: the sheet is an assumption and must never read as data.

    Selected by name rather than by trace type: FR-12's spot plane is a `go.Surface` too, and
    "every surface on this figure is the sheet" stopped being true the day it landed.
    """
    assert T.SHEET_OPACITY < 0.5
    fig = price_surface_figure(wide, asof, cp="C", show_interpolated=True)
    sheets = [t for t in fig.data if t.type == "surface" and t.name != SPOT_PLANE_NAME]
    if sheets:  # a date too thin to triangulate contributes none — that is allowed
        assert all(s.opacity < 0.5 for s in sheets)
        assert all("nterpolat" in (s.name or "") for s in sheets), "the sheet must say so"


def test_the_spot_plane_is_neither_a_series_nor_the_chrome(wide, asof):
    """FR-12: "obviously not data". The plane is a ruler standing in the scene.

    Two ways it could stop reading that way, both one careless token apart: wearing a series
    hue (a reader would look for the points that belong to it) or wearing the amber that every
    heading on the page is set in (it would read as chrome bolted onto the chart). It also has
    to sit *behind* the argument — fainter than the interpolated sheet, because the sheet lies
    over the cloud in one layer while the plane stands side-on through the middle of it.
    """
    assert T.SPOT_PLANE not in {T.MARK, T.MARK_PUT, T.TRADE, T.TRADE_PUT, T.NEUTRAL}, (
        "the spot plane is wearing a data series' colour"
    )
    assert T.SPOT_PLANE != T.ACCENT, "the spot plane is wearing the heading colour"
    assert T.SPOT_PLANE_OPACITY <= T.SHEET_OPACITY, (
        "the plane cuts through the whole cloud — at the sheet's opacity it fogs every "
        "point behind it"
    )

    plane = next(t for t in price_surface_figure(wide, asof, cp="C").data
                 if t.name == SPOT_PLANE_NAME)
    # On the TRACE, not only on the tokens. A mutation test found that an opaque plane passed
    # every assertion here, because the opacity check above compares two theme constants and
    # nothing tied them to what the figure actually renders (T-46).
    assert plane.opacity == T.SPOT_PLANE_OPACITY < T.SHEET_OPACITY, (
        f"the rendered plane is at opacity {plane.opacity}, not the token's "
        f"{T.SPOT_PLANE_OPACITY}"
    )
    assert plane.showscale is False, "a colorbar would claim the plane measures something"
    assert plane.hoverinfo == "skip", "a wall through the cloud must not steal a point's hover"
    assert {c[1] for c in plane.colorscale} == {T.SPOT_PLANE}, (
        "the plane's colour ramps, so it looks like it encodes a magnitude"
    )


# ------------------------------------------- Assignment 2's page: lines and tables (T-68)


def test_the_margin_lines_are_rulers_and_nav_is_the_series():
    """FR-16's panel asks one question: does NAV stay above IM and MM?

    IM and MM are *requirements* computed off LMV, not measurements of the strategy — so
    DESIGN-BRIEF §6 rule 6 binds them exactly as it binds FR-12's spot plane: a reference
    wears no series hue and no amber, and stays subordinate to the thing it is a reference
    for. Three co-equal lines would answer a question nobody asked.

    Read off `account_line()` rather than off the three colour constants, because the
    subordination lives in the weight and the dash — a restyle that kept the hues and
    equalised the strokes would pass a colours-only check while destroying the panel's point.
    """
    nav, im, mm = (T.account_line(r) for r in ("nav", "im", "mm"))

    assert nav["dash"] == "solid", "the series must be the unbroken line"
    for name, ruler in (("IM", im), ("MM", mm)):
        assert ruler["dash"] != "solid", f"{name} is drawn solid — it reads as a third series"
        assert ruler["width"] < nav["width"], (
            f"{name} is {ruler['width']}px against NAV's {nav['width']}px — a reference that "
            "is as heavy as the series is not subordinate to it"
        )
    assert im["dash"] != mm["dash"], "the two rulers are indistinguishable from each other"
    assert mm["width"] <= im["width"], (
        "MM is the further floor and must not be the louder of the two"
    )


def test_the_covered_call_lines_are_neither_chrome_nor_a_1_1_series():
    """§6 rule 2 and rule 6, on the page that added four new lines to the site.

    `WARN` is amber and is used on this page — on a skip *reason*, which is a word. The ban
    is on amber reaching a data channel, so what has to hold is that none of the four lines
    a figure draws wears it.
    """
    lines = {
        "NAV": T.NAV_LINE,
        "IM": T.MARGIN_IM,
        "MM": T.MARGIN_MM,
        "fit": T.FIT_LINE,
    }
    for name, colour in lines.items():
        assert colour != T.ACCENT, f"{name} is drawn in the heading colour"

    # The rulers may not wear a hue that means "a series" on the site. NAV may — it IS a
    # series — but not one whose meaning is spoken for on its own page: panel [5] is the
    # mid-vs-print scatter, so cyan is the mark and magenta is the print there too.
    series = {T.MARK, T.MARK_PUT, T.TRADE, T.TRADE_PUT}
    for name in ("IM", "MM", "fit"):
        assert lines[name] not in series, f"{name} is wearing a data series' colour"
    assert T.NAV_LINE not in {T.MARK, T.TRADE}, (
        "NAV is wearing the README's cyan or magenta, which panel [5] of the same page "
        "uses for the mark and the print (PO, 2026-09-17)"
    )


def test_the_rulers_read_as_one_family_and_nav_as_something_else():
    """The panel must not go monochrome, stated structurally rather than as a number.

    The 60 deg floor in `test_a_right_is_never_a_near_shade_of_its_own_counterpart` is for
    4px markers separated by **hue alone**; these lines carry weight and dash as well, and
    NAV sits 39-42 deg off the rulers — the same neighbourhood the hero already renders
    between the slate spot plane and the violet puts, in one scene (DESIGN-BRIEF §3). So a
    number copied from there would be a number tuned to pass.

    What actually has to hold is the *shape* of the relationship: IM and MM are one family
    (3 deg apart — they are two floors on one account), and NAV is outside it. A restyle that
    collapsed all three into one hue fails the second assertion however wide the first gap
    is, which is the failure this guard exists for.
    """
    to_im, to_mm = _hue_gap(T.NAV_LINE, T.MARGIN_IM), _hue_gap(T.NAV_LINE, T.MARGIN_MM)
    between = _hue_gap(T.MARGIN_IM, T.MARGIN_MM)
    assert between < min(to_im, to_mm), (
        f"the two rulers are {between:.0f} deg apart but NAV is only {min(to_im, to_mm):.0f} "
        "deg away — they no longer read as a family with the series outside it"
    )
    for name, gap in (("IM", to_im), ("MM", to_mm)):
        assert gap >= 30, (
            f"NAV and {name} are {gap:.0f} deg apart — same hue family, so the panel reads "
            "as three shades of one line rather than a series and its floors"
        )


def test_the_two_pages_draw_one_identity_line(wide, asof):
    """`y = x` means the same thing on both pages, so it is one value, not two.

    `IDENTITY_LINE` is deliberately an alias rather than a repeated literal — the opposite
    decision from `NAV_LINE`, which repeats `MARK_PUT`'s value on purpose so that the two
    pages stay free to diverge. Pinned against the line 1.1 actually renders rather than
    against the constant it was copied from (T-46): a token that agrees only with itself
    proves nothing.
    """
    fig = settle_vs_trade_figure(wide, asof)
    drawn = next(t for t in fig.data if t.name == "y = x")
    assert T.IDENTITY_LINE == drawn.line.color, (
        f"1.1 draws y = x in {drawn.line.color} and Assignment 2 would draw it in "
        f"{T.IDENTITY_LINE}"
    )
    assert drawn.line.dash == "dash", "the identity line is a reference and must stay dashed"


# The classes Assignment 2's tables are built from. Hand-named on purpose: this list is the
# contract between `theme.PAGE_CSS` and the page that emits the markup (T-59), and CSS fails
# OPEN — an undefined class is not an error, it is simply no styling. That is how `.osl-w6`
# went missing from the published page while the dev app looked perfect.
TABLE_CLASSES = [
    ".osl-table-scroll",  # the scroll box, and the ancestor a sticky header resolves against
    ".osl-table",         # the table itself
    ".osl-table-kv",      # the strategy's key/value variant, which opts out of the floor
    ".osl-num",           # a right-aligned, tabular number
    ".osl-label",         # a cell that names rather than measures
    ".osl-skip",          # a skip reason — amber, the one exception
    ".osl-flag",          # NEG_AVAILABLE — red, the other one
    ".osl-up",            # cash in, and a BUY (PO, 2026-09-18)
    ".osl-down",          # cash out, and a SELL
]


_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _css_at_base_level(css: str) -> str:
    """`css` with every `@media { ... }` block and every comment removed.

    Braces are matched rather than split on. The first version of this helper took
    `css.split("@media")[0]`, which is text position and not nesting — most of the
    stylesheet is written *after* the two breakpoint blocks, so it declared seven perfectly
    unconditional rules to be missing. Comments go too, or a selector merely *named* in a
    note counts as a rule that exists.
    """
    css = _CSS_COMMENT.sub("", css)
    out, i = [], 0
    while True:
        j = css.find("@media", i)
        if j < 0:
            out.append(css[i:])
            return "".join(out)
        out.append(css[i:j])
        k, depth = css.find("{", j), 0
        while k < len(css):
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            if depth == 0:
                break
            k += 1
        i = k + 1


def _css_rule(selector: str) -> str:
    """The declarations of the one base-level rule for `selector`."""
    body = _css_at_base_level(T.PAGE_CSS)
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", body)
    assert m, f"{selector} has no unconditional rule in PAGE_CSS"
    return m.group(1)


@pytest.mark.parametrize("cls", TABLE_CLASSES)
def test_every_table_class_is_defined_at_base_level(cls):
    """Defined outside any `@media` block, for the reason `.osl-hero` states in PAGE_CSS.

    A class that exists only inside a breakpoint is styled at some widths and unstyled at
    others, and the unstyled one renders perfectly — just wrong.
    """
    assert re.search(re.escape(cls) + r"[ ,:{]", _css_at_base_level(T.PAGE_CSS)), (
        f"{cls} has no unconditional rule in PAGE_CSS — CSS fails open, so a table using it "
        "would render unstyled with nothing to say why"
    )


def test_a_table_scrolls_rather_than_deforming():
    """T-47's posture, applied to a table (SPEC §11).

    Thirteen columns of dollars squeezed until the decimals stop lining up is the table
    version of "the chart is broken"; a scrollbar is the honest alternative. The floor has to
    be *wider* than a figure's, because a figure can be redrawn narrow and a column of
    numbers cannot, and the key/value table has to opt out or it scrolls for nothing.
    """
    assert T.TABLE_MIN_WIDTH > T.FIGURE_MIN_WIDTH, (
        "a 13-column table needs more room than a figure, not less"
    )
    assert f"min-width:{T.TABLE_MIN_WIDTH}px" in T.PAGE_CSS, (
        "TABLE_MIN_WIDTH is a token nothing renders — the stylesheet has its own number"
    )
    assert "overflow:auto" in _css_rule(".osl-table-scroll"), (
        "the scroll box does not scroll, so a wide table will push its panel out of the grid"
    )
    assert "min-width:0" in _css_rule(".osl-table-kv"), (
        "the key/value table inherits the 13-column width floor"
    )


# ------------------------------------------------------------------- the terminal grid


# Trace types whose `showlegend` defaults to False, so an unset attribute means "no entry".
# Everything else defaults to True. Plotly's own rule; spelled out because the hero mixes
# scatter3d (entry by default) with surface (no entry unless asked), and the difference is
# what makes the legend seven deep rather than nine.
_NO_LEGEND_BY_DEFAULT = {"surface"}


def _legend_entries(fig) -> int:
    """How many rows the legend will actually draw for the figure's OPENING state.

    Counts the traces a reader sees listed: the ones that are visible or parked on the legend
    (a `visible=False` trace has no entry), whose `showlegend` is on — explicitly, or by the
    trace type's default.
    """
    n = 0
    for t in fig.data:
        if t.visible is False:
            continue
        show = t.showlegend
        if show is None:
            show = t.type not in _NO_LEGEND_BY_DEFAULT
        if show:
            n += 1
    return n


def test_nothing_lives_in_the_band_above_a_plot_any_more(wide, asof):
    """A horizontal legend grows UPWARD as a figure narrows, and it grows into the band the
    caption used to sit in.

    That arrangement produced the same defect five times on this project at five different
    widths — caption through legend, caption clipped off the canvas, caption off the edge of a
    tile, caption over a legend that had wrapped to two rows, caption escaping the figure
    below 1440px. Policing it needed arithmetic over token positions, legend row counts and
    text-box heights, and the arithmetic was wrong twice.

    Captions are HTML now (T-47), so the rule is simply that the band is EMPTY. There is
    nothing left to collide with a legend, at any width, and no sum to get wrong.
    """
    from options_surface_lab.option_surface_plot import figure_caption

    for name, fig in (
        ("static hero", static_surface_figure(wide, ticker="UUUU")),
        ("app hero", price_surface_figure(wide, asof, cp="C", ticker="UUUU")),
    ):
        assert not fig.layout.annotations, (
            f"{name}: {len(fig.layout.annotations)} annotation(s) drawn inside the figure — "
            "a wrapping legend grows into that band, which is the arrangement this replaced"
        )
        assert figure_caption(fig), f"{name}: lost its how-to-read caption entirely"


def test_the_top_margin_has_room_for_the_whole_stack():
    """Title and legend live in the top margin; too little and they collide.

    Two tenants now, not three — the caption left this band in T-47.
    """
    title_band = T.SIZE_TITLE * 1.75          # a display-face line plus its leading
    for name, margin, rows in (
        # The dev hero shows one right at a time, so its legend is a single row. The
        # published one carries seven entries and wraps to three at FIGURE_MIN_WIDTH — the
        # narrowest it is ever rendered, since the panel scrolls rather than squeezing it.
        ("hero", T.HERO_MARGIN, 1),
        ("hero with slider", T.HERO_MARGIN_WITH_SLIDER, 3),
    ):
        needed = title_band + rows * (T.SIZE_LEGEND * 2.0)
        assert margin["t"] >= needed, (
            f"{name}: {margin['t']}px cannot hold a title and a {rows}-row legend "
            f"({needed:.0f}px)"
        )
    assert T.HERO_MARGIN_WITH_SLIDER["b"] >= 80, "the as-of slider needs its own bottom room"


def test_every_width_token_has_a_stylesheet_class():
    """A width token with no matching CSS class silently collapses that panel to one column.

    This shipped. The hero split moved from 7/3 to 6/4, the tokens were updated and the
    hand-listed `.osl-w3/.w5/.w7/.w10` rules were not, so `.osl-w6` and `.osl-w4` did not
    exist. An undefined class is not an error in CSS — `grid-column` just stays `auto` — so
    the surface and the underlying rendered one column wide on the deployed page while every
    other panel was fine. The Reflex app styles panels inline and was unaffected, which is
    why it only ever appeared in production.
    """
    defined = {int(n) for n in re.findall(r"\.osl-w(\d+)\s*\{", T.PAGE_CSS)}
    for name in ("W_HERO", "W_SIDECAR", "W_HALF", "W_FULL"):
        width = getattr(T, name)
        assert width in defined, f"{name}={width} has no .osl-w{width} rule in PAGE_CSS"
    assert defined == set(range(1, T.GRID_COLUMNS + 1)), (
        "the width classes must be generated for every column, not hand-listed"
    )


def test_panel_widths_tile_complete_rows():
    """A hairline grid shows every gap, so a row that does not add up is immediately ugly.

    Cheap to assert and easy to break: widening the hero without narrowing its sidecar
    silently pushes the underlying onto its own row and leaves the surface with a hole
    beside it.
    """
    assert T.W_HERO + T.W_SIDECAR == T.GRID_COLUMNS, "the hero row does not fill its row"
    assert T.W_HALF * 2 == T.GRID_COLUMNS, "the 2-up rows do not fill their row"
    assert T.W_FULL == T.GRID_COLUMNS


def test_the_hero_and_its_sidecar_are_the_same_height(wide):
    """DESIGN-BRIEF §5: the underlying rides beside the surface, so the row must end level.

    `static_surface_figure` and `build_preview`'s candlestick both read HERO_FIGURE_HEIGHT.
    This pins the figure end of that contract — the side that a layout change would miss.
    """
    fig = static_surface_figure(wide, ticker="UUUU")
    assert fig.layout.height == T.HERO_FIGURE_HEIGHT


def test_a_tiled_figure_gives_its_title_to_the_panel_header(wide, asof):
    """`as_panel_figure` is what stops every tile from saying its name twice."""
    from options_surface_lab.option_surface_plot import as_panel_figure

    fig = as_panel_figure(coverage_heatmap(wide, asof, cp="C", field="MARK"))
    assert fig.layout.title.text is None
    assert fig.layout.height == T.PANEL_FIGURE_HEIGHT
    # The caption survives the panelising — it explains how to read the figure, it is not a
    # label. It lives in `layout.meta` now and the panel renders it as HTML (T-47).
    from options_surface_lab.option_surface_plot import figure_caption

    assert figure_caption(fig), "the how-to-read caption must not be lost with the title"


# --------------------------------------------- legibility of the four data series
#
# Both of these encode a defect the PO caught by eye on 2026-09-02, in the form that would
# have caught it automatically. Neither is a style preference: an unreadable series is a
# figure that does not make its argument.


def _hue_degrees(hex_color: str) -> float:
    """Hue angle in degrees. Enough to reason about "are these two the same colour?"."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    hi, lo = max(r, g, b), min(r, g, b)
    if hi == lo:
        return 0.0
    d = hi - lo
    if hi == r:
        deg = 60 * (((g - b) / d) % 6)
    elif hi == g:
        deg = 60 * (((b - r) / d) + 2)
    else:
        deg = 60 * (((r - g) / d) + 4)
    return deg % 360


def _hue_gap(a: str, b: str) -> float:
    d = abs(_hue_degrees(a) - _hue_degrees(b))
    return min(d, 360 - d)


def test_a_right_is_never_a_near_shade_of_its_own_counterpart():
    """The comparison the reader makes is calls-against-puts *within* a role.

    The first palette derived puts by shifting each call's colour toward blue, which made
    them deliberately similar — on the mark-vs-print scatter the cyan calls and the sky puts
    read as one cloud and the puts looked absent. 60 degrees is the floor for two hues that
    must be told apart at 7px.
    """
    for role, call, put in (
        ("mark", T.MARK, T.MARK_PUT),
        ("print", T.TRADE, T.TRADE_PUT),
    ):
        gap = _hue_gap(call, put)
        assert gap >= 60, f"{role}: calls {call} and puts {put} are only {gap:.0f} deg apart"


def test_every_marker_is_filled():
    """Open symbols were unreadable at these sizes and are not an available channel.

    A 4px ring on a dark ground, seen through a 3D projection, is a smudge. The rights are
    separated by hue and glyph instead; nothing relies on an outline being visible.
    """
    for key, style in SERIES_STYLE.items():
        assert not style["symbol"].endswith("-open"), (
            f"{key} uses {style['symbol']!r} — open markers disappear at size "
            f"{style['size']} on this ground"
        )


def test_the_scatter_names_both_rights_in_its_legend(wide, asof):
    """FR-5's figure has to show a reader that the puts are present.

    It previously drew one unlabelled trace coloured by a mapped array, so there was no
    legend entry for either right and no way to confirm the puts had been plotted at all.
    """
    fig = settle_vs_trade_figure(wide, asof)
    named = {t.name for t in fig.data if t.type == "scatter" and t.showlegend}
    assert {"Calls", "Puts"} <= named, f"both rights must be named in the legend, got {named}"

    calls = next(t for t in fig.data if t.name == "Calls")
    puts = next(t for t in fig.data if t.name == "Puts")

    # Both draw the mark, so both are circles — the glyph encodes the role, not the right
    # (PO, 2026-09-02). That leaves hue as the only channel separating the two clouds, which
    # is exactly why it has to be a wide gap rather than a neighbouring shade.
    assert calls.marker.symbol == puts.marker.symbol == T.SYMBOL_MARK
    assert _hue_gap(calls.marker.color, puts.marker.color) >= 60


def test_the_published_figure_is_themed_too(wide):
    """The static page is the deliverable — a restyle that stops at the dev app is half done."""
    fig = static_surface_figure(wide, ticker="UUUU")
    assert fig.layout.paper_bgcolor == T.SURFACE
    assert fig.layout.scene.bgcolor == T.BG
    assert T.ACCENT in str(fig.layout.sliders[0].currentvalue.font.color)


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg: str, bg: str) -> float:
    hi, lo = sorted((_relative_luminance(fg), _relative_luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# Every foreground/ground pairing the identity actually renders. Kept explicit rather than
# generated: the point is to name where each colour is allowed to sit.
CONTRAST_PAIRS = [
    ("TEXT on BG", T.TEXT, T.BG),
    ("TEXT_MUTED on BG", T.TEXT_MUTED, T.BG),
    ("TEXT_MUTED on SURFACE", T.TEXT_MUTED, T.SURFACE),
    ("TEXT_MUTED on SURFACE_ALT", T.TEXT_MUTED, T.SURFACE_ALT),  # axis ticks, panel headers
    ("TEXT on SURFACE_ALT", T.TEXT, T.SURFACE_ALT),
    ("ACCENT on SURFACE", T.ACCENT, T.SURFACE),
    ("TEXT on SURFACE", T.TEXT, T.SURFACE),          # FR-7's commentary sentences
    ("NEGATIVE on SURFACE", T.NEGATIVE, T.SURFACE),  # ... and its unwritten placeholder
    ("ACCENT on BG", T.ACCENT, T.BG),
    ("MARK on SURFACE_ALT", T.MARK, T.SURFACE_ALT),
    ("TRADE on SURFACE_ALT", T.TRADE, T.SURFACE_ALT),
    ("MARK_PUT on SURFACE_ALT", T.MARK_PUT, T.SURFACE_ALT),
    ("TRADE_PUT on SURFACE_ALT", T.TRADE_PUT, T.SURFACE_ALT),
    ("MARK_PUT on SURFACE", T.MARK_PUT, T.SURFACE),
    ("TEXT_INVERSE on MARK", T.TEXT_INVERSE, T.MARK),
    ("TEXT_INVERSE on TRADE", T.TEXT_INVERSE, T.TRADE),
    ("TEXT_INVERSE on ACCENT", T.TEXT_INVERSE, T.ACCENT),
    ("TEXT_INVERSE on NEUTRAL", T.TEXT_INVERSE, T.NEUTRAL),
    # Assignment 2's page (T-68): three lines on a plot interior, plus the two coloured cells
    # its tables allow. MM is the tightest of them and is deliberately the faintest thing on
    # that panel — "faintest" still has to clear the floor.
    ("NAV_LINE on SURFACE_ALT", T.NAV_LINE, T.SURFACE_ALT),
    ("MARGIN_IM on SURFACE_ALT", T.MARGIN_IM, T.SURFACE_ALT),
    ("MARGIN_MM on SURFACE_ALT", T.MARGIN_MM, T.SURFACE_ALT),
    ("FIT_LINE on SURFACE_ALT", T.FIT_LINE, T.SURFACE_ALT),
    ("WARN on SURFACE", T.WARN, T.SURFACE),  # a skip reason in the skip log
    # Direction in a blotter cell (PO, 2026-09-18). Measured on BOTH table grounds: a row
    # takes SURFACE at rest and SURFACE_ALT under the cursor, and a colour that clears the
    # floor only until someone hovers it is a colour that fails where it is being read.
    ("POSITIVE on SURFACE", T.POSITIVE, T.SURFACE),
    ("POSITIVE on SURFACE_ALT", T.POSITIVE, T.SURFACE_ALT),
    ("NEGATIVE on SURFACE_ALT", T.NEGATIVE, T.SURFACE_ALT),
]


def test_the_axis_menu_is_legible_in_both_of_its_states():
    """FR-10's control renders against a ground we do not own (AD-6's awkward edge).

    A Plotly menu has ONE font colour for every button, and plotly.js paints the highlighted
    row `MENU_ACTIVE_BG` with no property to override it. So the type has to clear AA on our
    ground *and* on that near-white — which is what rules out the amber type used everywhere
    else in the chrome (1.7:1) and forces dark type on an amber chip. Read off `menu()`
    itself, so re-toning the control cannot quietly drop below the floor.
    """
    spec = T.menu()
    for ground, name in ((spec["bgcolor"], "its own chip"), (T.MENU_ACTIVE_BG, "plotly's highlight")):
        ratio = _contrast(spec["font"]["color"], ground)
        assert ratio >= 4.5, f"the axis menu is {ratio:.2f}:1 on {name}, below WCAG AA"


def test_the_axis_menu_sits_inside_the_plot_not_in_the_crowded_band_above(wide):
    """The band above a plot is full, and a fourth tenant overlapped the other three.

    Title, caption and legend already stack there (see the caption/legend test above), and
    Plotly's modebar floats over the top-right on top of that. FR-10's control shipped at
    `CAPTION_Y_OVER_LEGEND` and the PO found it overlapping neighbours at real widths on
    2026-09-04. It now lives inside the plot area, top-left: below the legend's band, and on
    the opposite side from the modebar.
    """
    spec = T.menu()
    assert spec["yanchor"] == "top" and spec["y"] < T.LEGEND_Y, (
        f"the menu is at y={spec['y']}, back in the band that holds title/caption/legend"
    )
    assert 0.0 <= spec["y"] <= 1.0, "the menu must be inside the plot area"
    assert spec["xanchor"] == "left" and spec["x"] <= 0.25, (
        "the menu must stay left — Plotly's modebar owns the top-right corner"
    )

    fig = static_surface_figure(wide, ticker="UUUU")
    menu = fig.layout.updatemenus[0]
    assert menu.y < fig.layout.legend.y, "the menu is back on top of the legend"
    assert not fig.layout.annotations, (
        "the figure draws text again — captions belong in the panel's HTML (T-47)"
    )


@pytest.mark.parametrize("label,fg,bg", CONTRAST_PAIRS, ids=[p[0] for p in CONTRAST_PAIRS])
def test_every_foreground_clears_wcag_aa(label, fg, bg):
    """FR-8: "text meets reasonable contrast on the chosen background" — measured, not eyeballed.

    A dark identity is easy to get wrong by degrees: each re-tone looks fine next to the last
    one and the page ends up unreadable on a projector. AA (4.5:1) is the floor.
    """
    ratio = _contrast(fg, bg)
    assert ratio >= 4.5, f"{label} is {ratio:.2f}:1, below WCAG AA"
