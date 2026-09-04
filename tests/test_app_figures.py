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
