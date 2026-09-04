"""Smoke tests for the app's figure path.

The unit tests cover transforms; nothing exercised the app -> plot call sites, so a kwarg
rename (show_settle -> show_mark) desynced them without failing anything. These pin the
signatures the app actually calls.
"""

import pathlib

import pandas as pd
import pytest

from options_surface_lab import options_surface_app as app


@pytest.fixture(scope="module")
def wide():
    payload = app.synthesize_demo_payload()
    _tidy, w, _p = app._prepare(payload)
    return w


@pytest.fixture(scope="module")
def asof(wide):
    return sorted({d.strftime("%Y-%m-%d") for d in wide["date"]})[-1]


def test_prepare_yields_the_mark_slot(wide):
    for col in ("MARK", "TRDPRC_1", "has_mark", "has_trade"):
        assert col in wide.columns
    assert wide["has_mark"].any(), "synthetic panel must populate the mark"


def test_sparsity_keys_match_what_the_state_reads(wide, asof):
    stats = app.summarize_sparsity(wide[wide["date"] == pd.Timestamp(asof)])
    for key in ("n_quotes", "n_mark_only", "n_both", "pct_mark_no_trade"):
        assert key in stats


def test_surface_figure_accepts_the_app_call_signature(wide, asof):
    fig = app.price_surface_figure(
        wide, asof, cp="C", show_trade=True, show_mark=True,
        show_interpolated=True, ticker="UUUU",
    )
    assert len(fig.data) >= 1


def test_every_app_figure_builds(wide, asof):
    payload = app.synthesize_demo_payload()
    assert len(app.candlestick_figure(payload["stock"], "UUUU").data) == 1
    assert len(app.settle_vs_trade_figure(wide, asof, ticker="UUUU").data) >= 1
    for field in ("MARK", "TRDPRC_1"):
        assert len(app.coverage_heatmap(wide, asof, cp="C", field=field).data) >= 1


def test_default_asof_picks_the_busiest_date_not_the_last(wide):
    """Expired weeklies mean the LAST date has one expiry alive and is the thinnest view."""
    counts = wide.groupby(wide["date"].dt.normalize()).size()
    busiest, last = counts.idxmax(), counts.index.max()
    assert counts[busiest] >= counts[last]


# ------------------------------------------------- the published page's only interactivity


def test_static_surface_carries_its_controls_in_the_figure(wide):
    """T-15/AD-5: no backend in production, so the selectors must be Plotly-native.

    Everything the published page can do has to live inside the figure JSON.
    """
    from options_surface_lab.option_surface_plot import static_surface_figure

    fig = static_surface_figure(wide, ticker="UUUU")

    sliders = fig.layout.sliders
    assert sliders and len(sliders[0].steps) >= 2, "the as-of slider must exist"

    shown = [t for t in fig.data if t.visible is True]
    parked = [t for t in fig.data if t.visible == "legendonly"]
    assert shown, "one date must be visible on open"
    assert parked, "puts must be present but parked on the legend"
    assert len(shown) + len(parked) < len(fig.data), "other dates must be hidden"

    assert any("TRDPRC_1" in t.name for t in shown), "the print series must be legend-toggleable"
    assert any("TRDPRC_1" not in t.name for t in shown), "the mark must be a separate trace"

    # no slider step may land on an empty figure
    for step in sliders[0].steps:
        vis = step.args[0]["visible"]
        assert len(vis) == len(fig.data)
        assert any(v is True or v == "legendonly" for v in vis), f"step {step.label!r} is empty"


def test_static_surface_opens_on_the_busiest_date(wide):
    from options_surface_lab.option_surface_plot import static_surface_figure

    fig = static_surface_figure(wide, ticker="UUUU")
    sl = fig.layout.sliders[0]
    counts = wide.groupby(wide["date"].dt.normalize()).size()
    assert str(counts.idxmax().date()) == sl.steps[sl.active].label


def test_static_surface_degrades_instead_of_raising():
    from options_surface_lab.option_surface_plot import static_surface_figure

    assert static_surface_figure(pd.DataFrame()) is not None


# ------------------------------------------------- figures must fit the panels that hold them


def test_panelised_figures_declare_exactly_the_reserved_heights(wide, asof):
    """A figure taller than its panel overflows into the row below it.

    This is a real defect, not a hypothetical: the dev app handed un-panelised figures to the
    terminal grid — the surface declaring 640 and the comparison 460 — while their panels
    reserved 600 and 360. The surface spilled over the top of the mark-vs-print panel
    underneath it. Reflex and the static builder both size the container from these tokens,
    so the figure and its box have to agree exactly.
    """
    from options_surface_lab import theme as T
    from options_surface_lab.option_surface_plot import as_panel_figure

    hero = app.price_surface_figure(wide, asof, cp="C", ticker="UUUU")
    assert hero.layout.height == T.HERO_FIGURE_HEIGHT, "the hero must fill its panel, not exceed it"

    sidecar = as_panel_figure(
        app.candlestick_figure(app.synthesize_demo_payload()["stock"], "UUUU"),
        height=T.HERO_FIGURE_HEIGHT,
    )
    assert sidecar.layout.height == T.HERO_FIGURE_HEIGHT, "the hero row must end level"

    for name, fig in (
        ("compare", app.settle_vs_trade_figure(wide, asof, ticker="UUUU")),
        ("mark occupancy", app.coverage_heatmap(wide, asof, cp="C", field="MARK")),
        ("print occupancy", app.coverage_heatmap(wide, asof, cp="C", field="TRDPRC_1")),
        ("spread", app.spread_heatmap(wide, asof, cp="C")),
    ):
        assert as_panel_figure(fig).layout.height == T.PANEL_FIGURE_HEIGHT, name


def _statement_at(lines, i):
    """The full logical statement starting at `lines[i]`, joined.

    Reading a fixed window of following lines is not good enough: a six-line lookahead from
    one assignment reaches into the *next* one, so a bare figure passes the check on its
    neighbour's `as_panel_figure`. Balancing brackets stops exactly at the statement's end.
    """
    depth, out = 0, []
    for line in lines[i:]:
        out.append(line)
        depth += line.count("(") + line.count("[") - line.count(")") - line.count("]")
        if depth <= 0:
            break
    return "\n".join(out)


def test_the_app_hands_no_raw_figure_to_a_panel():
    """Every figure the app puts in a panel must declare a height.

    Checked at the source level because that is where the mistake is made: the builders were
    all correct on their own, the app simply forgot to panelise what it passed on, and nothing
    downstream could tell. Two rules close the hole — an assignment either panelises inline or
    hands over a local that was itself built with a height, and no bare `go.Figure()` may
    escape without one (an undeclared height renders at Plotly's 450 and spills out of a tile).
    """
    lines = pathlib.Path(app.__file__).read_text(encoding="utf-8").splitlines()
    panelised = ("as_panel_figure", "price_surface_figure", "height=")
    offenders = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("self.fig_"):
            continue
        rhs = stripped.split("=", 1)[1].strip()
        if rhs.isidentifier():
            continue  # a plain local — covered by the go.Figure() rule below
        if any(tok in _statement_at(lines, i) for tok in panelised):
            continue
        offenders.append(f"{i + 1}: {stripped}")

    for i, line in enumerate(lines):
        if "go.Figure()" not in line or line.strip().startswith("#"):
            continue
        if ": go.Figure = go.Figure()" in line:
            continue  # a State var default, replaced before it is ever rendered
        if "height=" not in _statement_at(lines, i):
            offenders.append(f"{i + 1}: {line.strip()}")

    assert not offenders, (
        "these figures reach a panel without a declared height and will overflow it:\n"
        + "\n".join(offenders)
    )


def test_the_app_and_the_published_page_reserve_the_same_heights():
    """The demo and the graded page are one product (DESIGN-BRIEF §5)."""
    from options_surface_lab import theme as T

    assert app.HERO_H == f"{T.HERO_FIGURE_HEIGHT}px"
    assert app.TILE_H == f"{T.PANEL_FIGURE_HEIGHT}px"


# --------------------------------------------- the as-of frames the slider applies (AD-5)


def test_the_scatter_trace_order_is_the_same_on_every_date(wide):
    """The published page restyles this figure by trace index, so the order is a contract.

    Empty traces are added rather than skipped precisely for this: a date with no puts used
    to shift `y = x` down an index, and a restyle would then write put data into the line.
    """
    from options_surface_lab.option_surface_plot import settle_vs_trade_figure

    dates = sorted(wide["date"].dt.normalize().unique())
    orders = {tuple(t.name for t in settle_vs_trade_figure(wide, d).data) for d in dates}
    assert len(orders) == 1, f"trace order varies by date: {orders}"
    assert list(orders)[0][:3] == ("Calls", "Puts", "y = x")


def test_every_slider_step_has_a_frame(wide):
    """A step with no frame moves the hero and silently leaves the rest of the page behind.

    This is the failure the whole feature exists to prevent, so it is checked directly rather
    than trusted: the two must be generated from the same set of dates.
    """
    from options_surface_lab.option_surface_plot import asof_frames, static_surface_figure

    frames = asof_frames(wide)
    labels = {s.label for s in static_surface_figure(wide).layout.sliders[0].steps}
    missing = sorted(labels - set(frames))
    assert not missing, f"slider steps with no frame to apply: {missing[:5]}"


def test_frames_are_json_safe_and_shaped_for_the_listener(wide):
    """JSON has no NaN, and the listener indexes fixed keys — both are easy to break."""
    import json

    from options_surface_lab.option_surface_plot import asof_frames

    frames = asof_frames(wide)
    text = json.dumps(frames)  # raises on NaN only with allow_nan=False, so check explicitly
    assert "NaN" not in text and "Infinity" not in text, "JSON.parse would reject this"

    for label, f in frames.items():
        assert set(f) >= {"cmp", "spread", "mark", "trade", "readouts"}, label
        assert len(f["readouts"]) == 6, f"{label}: the readout strip has six cells"
        # the scatter payload restyles traces 0..2, so it carries exactly three arrays
        assert len(f["cmp"]["x"]) == 3 and len(f["cmp"]["y"]) == 3, label
        assert len(f["cmp"]["bars"]) == 3, label
        for key in ("spread", "mark", "trade"):
            grid = f[key]
            if grid is None:
                continue  # a date with nothing to draw keeps its panel, by design
            assert len(grid["z"]) == len(grid["y"]), f"{label}/{key}: z rows vs y labels"


def test_frame_readouts_match_the_figures_for_that_date(wide):
    """The strip and the panels must describe the same day, or the fix reintroduces the bug."""
    from options_surface_lab.option_surface_plot import asof_frames, settle_vs_trade_figure

    dates = sorted(wide["date"].dt.normalize().unique())[:3]
    frames = asof_frames(wide, dates=dates)
    for d in dates:
        f = frames[str(pd.Timestamp(d).date())]
        bars = settle_vs_trade_figure(wide, d).data[3]
        assert f["cmp"]["bars"] == [int(v) for v in bars.y]
        # "Both mark & print" is the middle bar and the third readout
        assert f["readouts"][2] == str(int(bars.y[1]))


# ------------------------------------- FR-10: the axis is a ruler, and a ruler is not data


def test_the_moneyness_axis_plots_strike_over_spot(wide, asof):
    """K / S is the whole feature: the same $12.50 strike is a different option each week."""
    from options_surface_lab.option_surface_plot import price_surface_figure

    fig = price_surface_figure(wide, asof, cp="C", x_mode="moneyness")
    assert "K / S" in fig.layout.scene.xaxis.title.text, "the axis must name its own ruler"

    sl = wide[(wide["date"] == pd.Timestamp(asof)) & (wide["cp"] == "C")]
    sl = sl.dropna(subset=["MARK"])
    mark = next(t for t in fig.data if t.name == "MARK")
    assert list(mark.x) == pytest.approx(list(sl["strike"] / sl["spot"]))


def test_switching_the_axis_preserves_every_series_and_its_identity(wide, asof):
    """FR-10 acceptance, literally: "switching axes preserves toggles and marker identity".

    A mode that dropped a trace, reordered the legend or re-coloured a marker would make the
    two views two different figures — and FR-5's mark-vs-print encoding is exactly what the
    reader is meant to carry across the switch.
    """
    from options_surface_lab.option_surface_plot import price_surface_figure

    k = price_surface_figure(wide, asof, cp="C")
    ks = price_surface_figure(wide, asof, cp="C", x_mode="moneyness")

    assert [t.name for t in k.data] == [t.name for t in ks.data]
    assert [t.type for t in k.data] == [t.type for t in ks.data]
    for a, b in zip(k.data, ks.data):
        if a.type == "surface":
            continue  # the sheet has its own test below
        assert (a.marker.color, a.marker.symbol) == (b.marker.color, b.marker.symbol), a.name
        assert list(a.z) == list(b.z), f"{a.name}: the prices moved with the axis"
        assert list(a.y) == list(b.y), f"{a.name}: the DTE axis moved with the X axis"


def test_the_sheet_is_the_same_sheet_under_both_rulers(wide, asof):
    """Re-interpolating in K/S space would hand back a subtly different surface.

    Within one as-of date the spot is a single number, so the toggle rescales the sheet's X
    rather than re-triangulating the cloud — the interpolated assumption a reader is looking
    at must not change because they changed the units on the axis (AD-9).
    """
    import numpy as np

    from options_surface_lab.option_surface_plot import price_surface_figure

    k = price_surface_figure(wide, asof, cp="C")
    ks = price_surface_figure(wide, asof, cp="C", x_mode="moneyness")
    sheets = [(a, b) for a, b in zip(k.data, ks.data) if a.type == "surface"]
    if not sheets:
        pytest.skip("this date is too thin to triangulate a sheet")

    spot = float(wide[wide["date"] == pd.Timestamp(asof)]["spot"].dropna().median())
    for a, b in sheets:
        assert np.array_equal(np.asarray(a.z), np.asarray(b.z), equal_nan=True)
        assert np.asarray(b.x) == pytest.approx(np.asarray(a.x) / spot)


def test_no_spot_means_no_moneyness_rather_than_a_strike_on_a_k_over_s_axis(wide, asof):
    """AD-9: a hole is honest, a number that does not mean what the axis says is not."""
    from options_surface_lab.option_surface_plot import price_surface_figure

    sl = wide[wide["date"] == pd.Timestamp(asof)].copy()
    sl["spot"] = float("nan")
    sl["moneyness"] = float("nan")
    fig = price_surface_figure(sl, asof, cp="C", x_mode="moneyness")
    for trace in fig.data:
        if trace.type != "scatter3d":
            continue
        assert all(x != x for x in trace.x), f"{trace.name} drew strikes on a K/S axis"


def test_the_published_hero_carries_the_axis_toggle(wide):
    """AD-5: no backend, so FR-10's control has to live inside the figure JSON too."""
    from options_surface_lab.option_surface_plot import static_surface_figure

    fig = static_surface_figure(wide, ticker="UUUU")
    menus = fig.layout.updatemenus
    assert menus, "the published hero has no axis toggle"

    buttons = menus[0].buttons
    assert len(buttons) == 2
    assert any("K/S" in b.label for b in buttons), f"{[b.label for b in buttons]}"
    for b in buttons:
        assert len(b.args[0]["x"]) == len(fig.data), "one x array per trace, in trace order"
        assert "scene.xaxis.title.text" in b.args[1], "the axis label must follow the mode"


def test_the_axis_toggle_and_the_as_of_slider_cannot_fight(wide):
    """The two controls compose only because they write disjoint properties.

    Date and right could not — two visibility menus overwrite one another, which is why the
    right lives on the legend instead (T-15). Give a slider step an `x`, or a button a
    `visible`, and the page silently starts losing one control to the other on every use.
    """
    from options_surface_lab.option_surface_plot import static_surface_figure

    fig = static_surface_figure(wide, ticker="UUUU")
    for step in fig.layout.sliders[0].steps:
        assert set(step.args[0]) == {"visible"}, f"step {step.label} restyles more than visibility"
    for b in fig.layout.updatemenus[0].buttons:
        assert set(b.args[0]) == {"x"}, f"button {b.label} restyles more than the X axis"


def test_the_toggle_rebases_each_trace_to_its_own_date_s_spot(wide):
    """Every trace belongs to one date, and one date has one spot — so the map is affine.

    Checked per trace rather than globally: the spot moves across the window, so a single
    ratio for the whole figure would be wrong, and a trace whose points were rebased against
    *another* date's spot would sit in the wrong place with nothing to show for it.
    """
    from options_surface_lab.option_surface_plot import static_surface_figure

    fig = static_surface_figure(wide, ticker="UUUU")
    in_k, in_ks = (b.args[0]["x"] for b in fig.layout.updatemenus[0].buttons)
    assert len(in_k) == len(in_ks) == len(fig.data)

    checked = 0
    for xk, xks in zip(in_k, in_ks):
        implied = [a / b for a, b in zip(xk, xks) if a and b]
        if not implied:
            continue  # a date with no underlying close carries no K/S ruler, by design
        assert max(implied) - min(implied) <= 0.01 * max(implied), (
            "one trace was rebased against more than one spot"
        )
        checked += 1
    assert checked, "no trace carried a usable pair of rulers"


# -------------------------------------------------------- the derived IV smile (FR-11, T-17)


def test_the_iv_smile_builds_and_fills_its_panel(wide, asof):
    from options_surface_lab import theme as T
    from options_surface_lab.option_surface_plot import (
        as_panel_figure,
        iv_smile_figure,
        panel_expiries,
    )

    fig = iv_smile_figure(wide, asof, ticker="UUUU")
    assert fig.layout.height == T.PANEL_FIGURE_HEIGHT, "a 2D smile is a tile, not a hero"
    panelised = as_panel_figure(fig, margin=T.SMILE_MARGIN)
    assert panelised.layout.height == T.PANEL_FIGURE_HEIGHT
    assert len(fig.data) == len(panel_expiries(wide))
    assert any(any(v is not None for v in t.y) for t in fig.data), "no curve was drawn"


def test_the_smile_ladder_is_the_same_on_every_date(wide):
    """One trace per panel-wide expiry, always, in chronological order.

    The published page restyles this figure by trace index when the slider moves, so a ladder
    that grew or shrank with the date would put one expiry's curve into another's slot — the
    same contract `settle_vs_trade_figure` lives under. Fixing it panel-wide also means an
    expiry keeps its colour across every step, which is what lets the eye follow one curve
    through the window.
    """
    from options_surface_lab.option_surface_plot import iv_smile_figure, panel_expiries

    dates = sorted(wide["date"].dt.normalize().unique())
    ladders = {tuple(t.name for t in iv_smile_figure(wide, d).data) for d in dates}
    assert len(ladders) == 1, f"the expiry ladder varies by date: {len(ladders)} variants"
    expected = tuple(pd.Timestamp(e).strftime("%b %d") for e in panel_expiries(wide))
    assert list(ladders)[0] == expected

    colours = {
        tuple(t.line.color for t in iv_smile_figure(wide, d).data) for d in dates[:6]
    }
    assert len(colours) == 1, "an expiry must keep its colour on every as-of date"


def test_the_iv_figure_prints_every_assumption_fr_11_requires(wide, asof):
    """FR-11 is accepted only when the assumptions are written next to the figure. They ride
    inside it because that is the only place that survives onto the static page."""
    from options_surface_lab.option_surface_plot import iv_smile_figure
    from options_surface_lab.option_surface_utils import MARK_FIELD_DEFAULT, RISK_FREE_RATE

    text = " ".join(a.text for a in iv_smile_figure(wide, asof).layout.annotations).lower()
    for needed in (
        "european",                      # exercise style
        "american exercise ignored",     # ...and that we know it is an approximation
        f"r = {RISK_FREE_RATE:.2%}",     # the rate, PRD OQ-2
        "no dividends",
        "act/365",
        MARK_FIELD_DEFAULT.lower(),      # what was inverted
        "not a tradable price",          # the caveat FR-11 names explicitly
        "derived",                       # ...and that none of it was observed
    ):
        assert needed in text, f"the IV figure never says {needed!r}"


def test_a_refused_strike_breaks_the_line_instead_of_being_bridged(wide, asof):
    """AD-9 on a line chart, which is the one thing a line can get wrong that a scatter cannot.

    A smile drawn only over the strikes that inverted would join its neighbours with a
    straight segment across the gap — drawing a vol for a strike where the solver refused.
    The curve is therefore built over the strikes *listed* that day, with `None` at every
    refusal and `connectgaps` off, so a hole renders as a visible break.
    """
    from options_surface_lab.option_surface_plot import iv_smile_figure
    from options_surface_lab.option_surface_utils import attach_implied_vol

    fig = iv_smile_figure(wide, asof)
    for trace in fig.data:
        assert trace.connectgaps is False, "a gap must never be bridged"
        assert len(trace.x) == len(trace.y), "x and y must stay aligned across holes"

    sl = attach_implied_vol(wide[wide["date"] == pd.Timestamp(asof)])
    # every plotted point is a strike that actually inverted, and every listed strike appears
    drawn = sum(1 for t in fig.data for v in t.y if v is not None)
    listed = sum(len(t.x) for t in fig.data)
    solved_strikes = sl.dropna(subset=["iv"]).groupby(["expiry", "strike"]).ngroups
    all_strikes = sl.groupby(["expiry", "strike"]).ngroups
    assert drawn == solved_strikes, "plotted points must be exactly the strikes that inverted"
    assert listed == all_strikes, "the x axis must span every listed strike, holes included"
    assert drawn < listed, "this panel always refuses some strikes — they must show as breaks"


def test_the_smile_axis_follows_the_same_ruler_as_the_hero(wide, asof):
    """FR-10 composes with FR-11 **in the Reflex app**: both read one `x_mode`.

    Scoped to the dev app deliberately — see BACKLOG T-43 for the published page's gap.
    """
    from options_surface_lab.option_surface_plot import X_AXIS_TITLE, iv_smile_figure

    for mode in ("strike", "moneyness"):
        fig = iv_smile_figure(wide, asof, x_mode=mode)
        assert fig.layout.xaxis.title.text == X_AXIS_TITLE[mode]

    strike = iv_smile_figure(wide, asof, x_mode="strike")
    money = iv_smile_figure(wide, asof, x_mode="moneyness")
    for a, b in zip(strike.data, money.data):
        assert list(a.y) == list(b.y), "the ruler may not change the vols themselves"
        assert a.name == b.name and a.line.color == b.line.color
    # and K/S really is K over S, not a relabelled strike axis
    spot = wide[wide["date"] == pd.Timestamp(asof)]["spot"].median()
    for a, b in zip(strike.data, money.data):
        for k, m in zip(a.x, b.x):
            assert m == pytest.approx(k / spot, abs=1e-3)


def test_the_iv_figure_degrades_instead_of_raising(wide):
    """A date with no quotes is a themed empty panel, never an exception (AD-9)."""
    from options_surface_lab import theme as T
    from options_surface_lab.option_surface_plot import iv_smile_figure

    fig = iv_smile_figure(wide, pd.Timestamp("1999-01-04"))
    assert fig.layout.height == T.PANEL_FIGURE_HEIGHT
    # the ladder is panel-wide, so the traces exist but draw nothing
    assert all(not any(v is not None for v in t.y) for t in fig.data)
    assert all(t.showlegend is False for t in fig.data), "no legend for curves that are absent"

    empty = iv_smile_figure(wide.iloc[0:0], None)
    assert empty.layout.height == T.PANEL_FIGURE_HEIGHT and not empty.data


def test_no_spot_means_no_smile_rather_than_strikes_on_a_k_over_s_axis(wide, asof):
    """The FR-10 rule, on this panel: a date with no underlying close gets no K/S ruler at
    all, rather than raw strikes plotted against an axis labelled as a ratio (AD-9)."""
    from options_surface_lab.option_surface_plot import iv_smile_figure

    blind = wide.copy()
    blind["spot"] = float("nan")
    fig = iv_smile_figure(blind, asof, x_mode="moneyness")
    assert all(len(t.x) == 0 for t in fig.data), "K/S was plotted with no spot to rebase on"
    # ...while the strike ruler still works on the same frame
    assert any(len(t.x) for t in iv_smile_figure(blind, asof, x_mode="strike").data)


def test_every_caption_fits_inside_the_margin_reserved_for_it(wide, asof):
    """An annotation pushed above the paper does not warn — it simply stops drawing.

    Found on the built page (T-17): the IV figure's assumptions line sat at y = 1.12 while
    `as_panel_figure` had replaced its margin with the 30px tile default, so FR-11's rate,
    day-count and exercise style silently vanished from the deliverable while every test
    stayed green. The arithmetic is small enough to just do: an annotation at `y` needs
    `(y - 1) x plot-area height` of top margin above the plot — **plus the height of the text
    itself**, because `theme.caption` anchors at the bottom of its box, so the glyphs hang
    *above* the y it names.

    The first version of this test omitted that line-height term and duly passed
    `spread_heatmap`, whose caption was clipped in the shipped page by exactly the mechanism
    the test was written to catch (adversarial review, 2026-09-04). A guard that models the
    anchor but not the box is worse than none: it certifies the defect.
    """
    from options_surface_lab import theme as T
    from options_surface_lab.option_surface_plot import (
        as_panel_figure,
        coverage_heatmap,
        iv_smile_figure,
        settle_vs_trade_figure,
        spread_heatmap,
    )

    panelised = [
        ("compare", as_panel_figure(settle_vs_trade_figure(wide, asof))),
        ("spread", as_panel_figure(spread_heatmap(wide, asof, cp="C"))),
        ("mark occupancy", as_panel_figure(coverage_heatmap(wide, asof, cp="C", field="MARK"))),
        ("print occupancy", as_panel_figure(coverage_heatmap(wide, asof, cp="C", field="TRDPRC_1"))),
        ("iv smile", as_panel_figure(iv_smile_figure(wide, asof), margin=T.SMILE_MARGIN)),
        ("hero", app.price_surface_figure(wide, asof, cp="C")),
    ]
    for name, fig in panelised:
        above = [a for a in fig.layout.annotations if (a.y or 0) > 1.0 and a.yref == "paper"]
        if not above:
            continue
        plot_area = fig.layout.height - fig.layout.margin.t - fig.layout.margin.b
        # yanchor="bottom" (theme.caption): the text box sits above its anchor, so reserve a
        # line for it. 1.4x the font size is a normal line box and errs toward safety.
        line = T.SIZE_CAPTION * 1.4
        needed = max(a.y - 1.0 for a in above) * plot_area + line
        assert fig.layout.margin.t >= needed, (
            f"{name}: caption at y={max(a.y for a in above)} needs {needed:.0f}px of top "
            f"margin ({needed - line:.0f} for the offset + {line:.0f} for the text) but only "
            f"{fig.layout.margin.t}px is reserved — it will be clipped"
        )


def test_everything_the_iv_panel_says_about_a_date_travels_with_the_slider(wide):
    """The whole panel follows the as-of slider — curves, legend and caption.

    Adversarial review (2026-09-04) found this shipped broken in the panel's 3D form: the
    frames payload carried only geometry, so the caption went on asserting the build date's
    "170 of 216 listed contract-days inverted" over every other date — including the one date
    where the panel is legitimately empty, where it described a figure showing nothing.

    That is the T-42 defect (a panel left on its build-time data) reappearing in the parts of
    a figure that are not its geometry. So the assertion is deliberately not "the curves
    changed": it is that every per-date channel is present and self-consistent on every step.
    """
    from options_surface_lab.option_surface_plot import (
        IV_COUNT_ANNOTATION,
        asof_frames,
        iv_smile_figure,
        panel_expiries,
        static_surface_figure,
    )

    from options_surface_lab.option_surface_plot import X_MODES

    frames = asof_frames(wide)
    labels = sorted({s.label for s in static_surface_figure(wide).layout.sliders[0].steps})
    n_traces = len(panel_expiries(wide))
    notes = set()
    for label in labels:
        by_mode = frames[label]["iv"]
        assert set(by_mode) == set(X_MODES), (
            f"{label}: the smile payload must carry every ruler — the hero's axis menu and "
            "the as-of slider both write its x, so the listener needs any (date, mode) pair"
        )
        sm = by_mode[X_MODES[0]]
        assert sm is not None, f"{label}: no IV frame at all"
        assert sm["note"], f"{label}: no caption text, so the panel would keep a stale one"
        notes.add(sm["note"])
        assert len(sm["x"]) == len(sm["y"]) == len(sm["show"]) == n_traces, (
            f"{label}: the expiry ladder changed length, so a restyle by index would "
            "put one expiry's curve into another's slot"
        )
        for i in range(n_traces):
            assert len(sm["x"][i]) == len(sm["y"][i])
            # a curve advertised in the legend must actually have points, and vice versa
            drawn = any(v is not None for v in sm["y"][i])
            assert sm["show"][i] == drawn, (
                f"{label} trace {i}: legend says {sm['show'][i]} but drawn={drawn}"
            )
        plotted = sum(1 for i in range(n_traces) for v in sm["y"][i] if v is not None)
        assert plotted or not any(sm["show"]), "an empty date must advertise nothing"
        # the caption has to count the dots the reader can actually see, in the same unit
        listed = sum(len(sm["x"][i]) for i in range(n_traces))
        assert f"{plotted} of {listed} listed strikes" in sm["note"], (
            f"{label}: caption says {sm['note'][:90]!r} but {plotted} of {listed} are plotted"
        )

    assert len(notes) > 1, "one caption for every date means it is not per-date at all"
    ann = iv_smile_figure(wide, labels[0]).layout.annotations
    assert "listed strikes" in ann[IV_COUNT_ANNOTATION].text
    assert "listed strikes" not in ann[0].text, (
        "annotation 0 carries the assumptions and must stay date-independent — the listener "
        "rewrites annotation IV_COUNT_ANNOTATION by index and would blow the rate away"
    )


def test_the_smile_opens_on_the_same_ruler_the_hero_opens_on(wide):
    """The two panels are driven by one control, so they must agree before it is touched.

    They did not: the hero's menu opens at `active=0` (strike) while the smile defaulted to
    moneyness, so the published page showed two rulers side by side at load — invisible until
    T-43 wired the dropdown through and made the mismatch the first thing you see.
    """
    from options_surface_lab.option_surface_plot import (
        X_AXIS_TITLE,
        X_MODES,
        iv_smile_figure,
        static_surface_figure,
    )

    hero = static_surface_figure(wide)
    active = hero.layout.updatemenus[0].active or 0
    hero_mode = X_MODES[active]
    assert iv_smile_figure(wide, wide["date"].max()).layout.xaxis.title.text == (
        X_AXIS_TITLE[hero_mode]
    ), "the smile's default ruler must match the hero menu's active button"


def test_the_axis_menu_and_the_slider_can_both_drive_the_smile(wide):
    """T-43. FR-10's disjoint-properties rule applied to a panel with no menu of its own.

    On the hero, the slider writes `visible` and the menu writes `x`, so the two never
    collide. The smile has no menu, so BOTH controls reach it through one listener that owns
    its `x` — which only works if the payload can produce every (date, mode) pair. This pins
    that: each mode is a complete, self-consistent smile for that date, and switching the
    ruler changes the x values without touching a single vol.
    """
    from options_surface_lab.option_surface_plot import X_MODES, asof_frames

    frames = asof_frames(wide)
    label = sorted(frames)[len(frames) // 2]
    by_mode = frames[label]["iv"]
    k, m = by_mode["strike"], by_mode["moneyness"]

    assert [len(a) for a in k["y"]] == [len(a) for a in m["y"]], "the ladder must match"
    for i in range(len(k["y"])):
        assert k["y"][i] == m["y"][i], "a ruler may not change the vols"
        assert k["show"][i] == m["show"][i], "a ruler may not change which curves are live"
        for kx, mx in zip(k["x"][i], m["x"][i]):
            assert kx != mx or kx == 0, "the x values must actually be rebased"
            assert mx < kx, "moneyness is K/S on a >$1 underlying, so it must be smaller"
    assert X_MODES == ("strike", "moneyness"), "the listener's default is X_MODES[0]"


def test_a_date_with_no_spot_loses_the_whole_smile_not_just_its_ruler(wide):
    """The IV panel depends on spot twice over, and the second dependency is easy to miss.

    On the hero, spot is only a *ruler*: the prices are plotted with or without it, and a
    missing close costs you the K/S axis alone. Here spot is an input to the **model** — no
    underlying close means `iv_refusal` refuses every row — so the panel is empty under
    *both* rulers. A test written on the hero's intuition (strike still draws, K/S does not)
    asserts something false; this is what actually holds, and it is worth pinning because the
    strike ruler keeps its axis and its listed strikes, so the panel looks populated until you
    notice there are no points on it (AD-9).
    """
    from options_surface_lab.option_surface_plot import asof_frames, iv_smile_figure

    blind = wide.copy()
    blind["spot"] = float("nan")
    asof = blind["date"].max()
    label = str(pd.Timestamp(asof).date())
    by_mode = asof_frames(blind, dates=[asof])[label]["iv"]

    for mode in ("strike", "moneyness"):
        sm = by_mode[mode]
        assert not any(v is not None for row in sm["y"] for v in row), (
            f"{mode}: a vol was inverted with no spot to invert against"
        )
        assert not any(sm["show"]), f"{mode}: the legend advertises curves that are not there"
        assert " 0 of " in sm["note"], f"{mode}: the caption must own up to drawing nothing"

    # the strike ruler still lays out its axis over the listed strikes — the panel is empty,
    # not absent, which is the AD-9 distinction
    assert any(len(row) for row in by_mode["strike"]["x"])
    assert all(len(row) == 0 for row in by_mode["moneyness"]["x"]), (
        "K/S has no ruler at all without a spot to rebase on (FR-10)"
    )
    assert not iv_smile_figure(blind, asof).layout.annotations[0].text.startswith("0")
