"""Smoke tests for the app's figure path.

The unit tests cover transforms; nothing exercised the app -> plot call sites, so a kwarg
rename (show_settle -> show_mark) desynced them without failing anything. These pin the
signatures the app actually calls.
"""

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
