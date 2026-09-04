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

# The modules FR-8 names: the figure builders and both pages (Reflex + static builder).
THEMED_SOURCES = [
    ROOT / "options_surface_lab" / "option_surface_plot.py",
    ROOT / "options_surface_lab" / "options_surface_app.py",
    ROOT / "build_preview.py",
]

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
    """AD-9 / FR-8: the sheet is an assumption and must never read as data."""
    assert T.SHEET_OPACITY < 0.5
    fig = price_surface_figure(wide, asof, cp="C", show_interpolated=True)
    sheets = [t for t in fig.data if t.type == "surface"]
    if sheets:  # a date too thin to triangulate contributes none — that is allowed
        assert all(s.opacity < 0.5 for s in sheets)
        assert all("nterpolat" in (s.name or "") for s in sheets), "the sheet must say so"


# ------------------------------------------------------------------- the terminal grid


def test_a_caption_never_shares_the_band_with_a_top_legend(wide, asof):
    """A horizontal legend at y=1.0 is about 0.05 of the plot area tall.

    A caption placed at 1.02 or 1.045 therefore lands *inside* it and the two print over each
    other — which is what the hero surface shipped with: the "drag the slider..." line ran
    straight through the legend swatches. Captions on a figure with a top legend must clear
    it, and the clearance lives in one token so both surfaces move together.
    """
    assert T.CAPTION_Y_OVER_LEGEND - T.LEGEND_Y >= 0.08, (
        "the clearance is smaller than a legend row is tall"
    )

    for name, fig in (
        ("static hero", static_surface_figure(wide, ticker="UUUU")),
        ("app hero", price_surface_figure(wide, asof, cp="C", ticker="UUUU")),
    ):
        legend = fig.layout.legend
        if legend.y is None or legend.y < 1:
            continue  # no top legend, nothing to clear
        captions = [a for a in fig.layout.annotations if a.yref == "paper"]
        assert captions, f"{name}: expected a how-to-read caption"
        for ann in captions:
            assert ann.y >= T.CAPTION_Y_OVER_LEGEND, (
                f"{name}: caption at y={ann.y} sits in the legend's band (y={legend.y})"
            )


def test_the_top_margin_has_room_for_the_whole_stack():
    """Title, caption and legend all live in the top margin; too little and they collide."""
    for name, margin in (
        ("hero", T.HERO_MARGIN),
        ("hero with slider", T.HERO_MARGIN_WITH_SLIDER),
    ):
        assert margin["t"] >= 100, f"{name}: {margin['t']}px cannot hold title + caption + legend"
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
    # the caption survives — it explains how to read the figure, it is not a label
    assert fig.layout.annotations, "the how-to-read caption must not be stripped with the title"


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


def test_the_axis_menu_clears_the_legend_and_the_caption(wide):
    """Three things share the band above the hero; the menu is the newest and the smallest.

    The caption is left-anchored and the legend sits a row lower, so the menu takes the right
    of the caption's row. A menu dropped to LEGEND_Y would land on the legend's swatches —
    the same collision the caption had before CAPTION_Y_OVER_LEGEND existed.
    """
    spec = T.menu()
    assert spec["y"] >= T.CAPTION_Y_OVER_LEGEND, "the menu sits in the legend's band"
    assert (spec["x"], spec["xanchor"]) == (1.0, "right"), "the caption owns the left of that row"

    fig = static_surface_figure(wide, ticker="UUUU")
    menu = fig.layout.updatemenus[0]
    captions = [a for a in fig.layout.annotations if a.yref == "paper"]
    assert all(a.xanchor == "left" for a in captions), "a centred caption would run into the menu"
    assert menu.y >= fig.layout.legend.y, "the menu must sit above the legend, not on it"


@pytest.mark.parametrize("label,fg,bg", CONTRAST_PAIRS, ids=[p[0] for p in CONTRAST_PAIRS])
def test_every_foreground_clears_wcag_aa(label, fg, bg):
    """FR-8: "text meets reasonable contrast on the chosen background" — measured, not eyeballed.

    A dark identity is easy to get wrong by degrees: each re-tone looks fine next to the last
    one and the page ends up unreadable on a projector. AA (4.5:1) is the floor.
    """
    ratio = _contrast(fg, bg)
    assert ratio >= 4.5, f"{label} is {ratio:.2f}:1, below WCAG AA"
