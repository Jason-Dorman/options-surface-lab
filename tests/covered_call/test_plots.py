"""T-69 — FR-16's account chart and FR-17's fill evidence, as figures.

The module is presentation, so almost every assertion here is of one shape: **the figure
says what the Book or the MidVsPrint says, and nothing it computed itself.** That is T-46's
rule applied to a plot — a test that reads a number back out of the trace it just put there
proves only that Plotly stores what it is given.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from options_surface_lab import theme as T
from options_surface_lab.covered_call import plots
from options_surface_lab.covered_call.engine import (
    FLAG_NEG_AVAILABLE,
    IM_RATE,
    MM_RATE,
    run_backtest,
)
from options_surface_lab.covered_call.evidence import NON_SIMULTANEITY_CAVEAT, mid_vs_print
from options_surface_lab.covered_call.rules import Params
from options_surface_lab.page_shell import figure_caption

PACKAGE = Path(__file__).resolve().parents[2] / "options_surface_lab" / "covered_call"


@pytest.fixture(scope="module")
def book(synthetic_tape, params):
    return run_backtest(synthetic_tape, params)


@pytest.fixture(scope="module")
def evidence(synthetic_tape, params):
    return mid_vs_print(synthetic_tape, params)


@pytest.fixture(scope="module")
def account(book):
    return plots.account_figure(book)


@pytest.fixture(scope="module")
def scatter(evidence):
    return plots.mid_vs_print_figure(evidence)


# --------------------------------------------------------------------------
# FR-16 — the Reg T account
# --------------------------------------------------------------------------
def test_the_account_chart_draws_the_ledger_and_not_its_own_arithmetic(account, book):
    """Every point is a ledger cell. The figure recomputes nothing (AD-12, SPEC §1).

    Compared column by column against ``book.ledger`` — the frame the figure was handed,
    not a frame derived from the traces. A mutant that plotted ``lmv`` where ``im`` belongs,
    or that scaled a series, is caught here and nowhere else: the trace's *name* would still
    be right and the chart would still look like three plausible lines.
    """
    assert tuple(t.name for t in account.data) == plots.ACCOUNT_TRACES
    for trace, column in zip(account.data, ("nav", "im", "mm")):
        assert list(trace.y) == pytest.approx(list(book.ledger[column])), (
            f"the {trace.name} line is not the ledger's `{column}` column"
        )
        assert list(pd.DatetimeIndex(trace.x)) == list(pd.DatetimeIndex(book.ledger["ts"]))


def test_the_account_chart_draws_the_hourly_frame_not_the_daily_roll_up(account, book):
    """SPEC §9: the chart draws the hourly ledger, the table is the roll-up of these rows.

    The two differ by an order of magnitude (784 bars against 49 sessions), so drawing the
    roll-up would produce a chart that is *correct at every point it shows* while quietly
    dropping fifteen sixteenths of the window — including every intra-day move the panel
    exists to let a reader inspect.
    """
    assert len(account.data[0].y) == len(book.ledger)
    assert len(book.daily_ledger()) < len(book.ledger), "the fixture cannot tell the two apart"


def test_every_line_wears_the_role_the_theme_gives_it(account):
    """FR-8 / AD-6: the colours come from `theme.account_line`, not from this module.

    Read off the theme at assert time rather than compared against hex values written here:
    a token repointed in `theme.py` must restyle the chart, and a test holding its own copy
    of the palette is a second place the palette lives.
    """
    for trace, role in zip(account.data, ("nav", "im", "mm")):
        spec = T.account_line(role)
        assert trace.line.color == spec["color"], trace.name
        assert trace.line.width == spec["width"], trace.name
        assert (trace.line.dash or "solid") == spec["dash"], trace.name


def test_the_hover_shows_the_three_values_at_one_bar(account):
    """FR-16's acceptance criterion, literally: *"the chart's hover shows the three values
    per bar"*.

    `x unified` is what makes that one box rather than three separate hovers a reader has to
    collect by moving the pointer. Without it every assertion about the templates below is
    still true and the requirement is still unmet.
    """
    assert account.layout.hovermode == "x unified"
    for trace in account.data:
        assert trace.hovertemplate, f"{trace.name} has no hover value"
        assert trace.name in trace.hovertemplate, (
            f"{trace.name}'s hover does not say which line it is"
        )


def test_the_caption_quotes_the_floor_at_an_entry_bar_not_the_all_bars_minimum(account, book):
    """The T-82 defect, made impossible to reintroduce quietly.

    `NEG_AVAILABLE` is only ever checked at an entry bar, so the floor a reader is given has
    to be the floor *there*. The all-bars minimum sits on a thin pre-market bar — it is
    ``max(ts)``'s mistake in a new place, and it is the number that reached three documents.
    The two must differ on this fixture or this test is asserting nothing.
    """
    ledger = book.ledger
    at_entries = float(ledger[ledger["entry"]]["available"].min())
    all_bars = float(ledger["available"].min())
    assert all_bars < at_entries, (
        "the fixture's two minima are equal, so this test cannot tell them apart"
    )

    text = " ".join(figure_caption(account))
    assert f"${at_entries:,.2f}" in text, "the caption does not quote the entry-bar floor"
    assert f"${all_bars:,.2f}" not in text, "the caption quotes the all-bars minimum"


def test_the_caption_states_the_reg_t_rates_the_engine_applied(account):
    """The rates are read from `engine`, so the sentence cannot drift from the ledger.

    A page that says "IM = 50%" beside a ledger computed at 30% is a page that is wrong in
    the one place a reader would never check, because the words agree with themselves.
    """
    text = " ".join(figure_caption(account))
    assert f"IM = {IM_RATE:.0%}" in text and f"MM = {MM_RATE:.0%}" in text


def test_the_caption_says_so_when_the_flag_fires(synthetic_tape):
    """The brief's *"you could not have put the trade on — say so"* (FR-16).

    Forced by funding the account at a fraction of one round lot: under SD-3 the flag never
    fires, so the branch that reports it has no data behind it on either tape. A branch a
    fixture never reaches is a branch with no test, however many tests name it (T-57).
    """
    poor = Params(start=dt.date(2026, 7, 6), end=dt.date(2026, 9, 11), start_cash=1_000.0)
    book = run_backtest(synthetic_tape, poor)
    assert (book.ledger[book.ledger["entry"]]["flag"] == FLAG_NEG_AVAILABLE).any()

    text = " ".join(figure_caption(plots.account_figure(book)))
    assert "negative" in text.lower(), "the caption is silent about a breached account"
    assert "never fires" not in text, "the caption claims a clean book over a flagged one"


def test_an_empty_book_draws_an_empty_panel_rather_than_raising(params):
    """AD-9: a hole renders as a hole. An empty ledger is a result, not an error.

    The ``Book`` is built here rather than run, because ``run_backtest`` *refuses* a tape
    with no stock bars (T-82's guard) — so the only way this branch is ever reached is a
    window inside a real tape that holds no bar, and the only way to test it is to hand the
    figure the frame that situation produces.
    """
    fig = plots.account_figure(_empty_book(params))
    assert fig.layout.height == T.HERO_FIGURE_HEIGHT
    assert not fig.data, "an empty ledger drew lines"
    assert figure_caption(fig), "an empty panel still has to say why it is empty"


# --------------------------------------------------------------------------
# FR-17 — mid against the print
# --------------------------------------------------------------------------
def test_the_scatter_draws_every_point_in_the_sample(scatter, evidence):
    """No subsampling. The headline quotes `n`; the panel has to show `n`.

    A thinned cloud would look tighter or looser than the statistic beside it depending
    entirely on which rows went, and nothing on the page would say a row had gone.
    """
    points = scatter.data[0]
    assert len(points.x) == evidence.n == len(evidence.points)
    assert list(points.x) == pytest.approx(list(evidence.points["mid"]))
    assert list(points.y) == pytest.approx(list(evidence.points["trdprc_1"]))


def test_the_two_reference_lines_are_the_identity_and_the_fit(scatter, evidence):
    """`y = x` is the line that matters; the fit is the line the brief asks for.

    The fit is checked against ``slope`` and ``intercept`` recomputed here from the
    dataclass, not against ``fit_y`` — the function the figure called. A defect in `fit_y`
    reproduced faithfully by a test that calls `fit_y` is T-46's guard-that-reads-back-its-
    own-effect, and this module's whole job is to not be a second source.
    """
    assert tuple(t.name for t in scatter.data) == plots.EVIDENCE_TRACES

    identity = scatter.data[1]
    assert list(identity.x) == list(identity.y), "y = x is not the identity line"
    assert identity.line.color == T.IDENTITY_LINE and identity.line.dash == "dash"

    fit = scatter.data[2]
    expected = [evidence.intercept + evidence.slope * x for x in fit.x]
    assert list(fit.y) == pytest.approx(expected), "the fit is not the fit that was estimated"
    assert fit.line.color == T.FIT_LINE


def test_both_axes_carry_one_range_so_the_identity_line_is_at_45_degrees(scatter, evidence):
    """A reference line that misstates its own slope is worse than no reference line.

    Unequal axes tilt `y = x` while leaving it labelled `y = x`, and the reader's whole
    reading of the cloud — is the print above or below the mid — is read off that angle.
    The range must also contain every point, or the panel silently crops its own sample.
    """
    x_range, y_range = scatter.layout.xaxis.range, scatter.layout.yaxis.range
    assert tuple(x_range) == tuple(y_range), "the axes carry different rulers"

    pts = evidence.points
    lo, hi = float(x_range[0]), float(x_range[1])
    assert lo <= pts[["mid", "trdprc_1"]].min().min()
    assert hi >= pts[["mid", "trdprc_1"]].max().max()


def test_the_caption_is_the_headline_and_the_caveat_verbatim(scatter, evidence):
    """Both strings are owned elsewhere, and this module may not paraphrase either.

    `headline()` carries the row set with the number — T-17's lesson from OQ-2, where vol
    shifts quoted from three different subsets landed across the docs and not one was
    checkable. `NON_SIMULTANEITY_CAVEAT` lives in `evidence` so the page and the notebook
    cannot state the method differently (SPEC §10).
    """
    lines = figure_caption(scatter)
    assert lines[0] == f"{plots.FIT_CAPTION_PREFIX} {evidence.headline()}"
    assert NON_SIMULTANEITY_CAVEAT in lines


def test_the_publish_guard_has_an_anchor_a_grep_can_actually_find():
    """T-45, made mechanical: the phrase a CI guard keys on is pure ASCII.

    SPEC §11's guard requires "the R² line", and that line carries `R²`, `×` and `−`. A
    guard is a shell grep over the built page, and the caption exists there twice — as panel
    HTML and inside `layout.meta`, where Plotly's encoder ships a slash as `\\/`. So the
    anchor must contain no `/` and no `·`, and must survive a JSON round trip unchanged.
    Shortening a caption once left the publish guard hunting for a phrase that no longer
    existed; it would have failed the deploy.
    """
    anchor = plots.FIT_CAPTION_PREFIX
    assert anchor.isascii(), f"{anchor!r} will not survive a grep over the built page"
    assert "/" not in anchor and "·" not in anchor
    import json

    assert anchor in json.dumps(anchor), "the anchor is escaped by the JSON encoder"


def test_no_fit_draws_no_line(evidence):
    """AD-9, the shape FR-11's `iv_refusal` gave a regression: a fit that could not be
    estimated is absent, never a line through two points.

    Built by hand rather than hunted for, because neither tape produces a degenerate
    sample — and a case no fixture reaches is a case with no test.
    """
    degenerate = _with_points(evidence, evidence.points.head(1))
    fig = plots.mid_vs_print_figure(degenerate)
    assert [t.name for t in fig.data] == list(plots.EVIDENCE_TRACES[:2]), (
        "a fit was drawn for a sample that has none"
    )


def test_an_empty_sample_draws_an_empty_panel_that_says_why(evidence):
    fig = plots.mid_vs_print_figure(_with_points(evidence, evidence.points.iloc[0:0]))
    assert fig.layout.height == T.PANEL_FIGURE_HEIGHT
    assert plots.FIT_CAPTION_PREFIX in " ".join(figure_caption(fig))


# --------------------------------------------------------------------------
# The committed tape — the book and the sample that actually ship
# --------------------------------------------------------------------------
def test_the_shipped_account_panel_quotes_the_number_the_docs_publish(real_tape, params):
    """$38,886.50 is in PRD §15, BACKLOG-2 and CLAUDE.md. The panel has to agree with them.

    Derived from the ledger, never typed — the literal here is the *published* claim, and
    this test is what stops the page and the documents drifting apart in either direction
    (T-83: derive the doc's number from the artifact, then pin it).
    """
    book = run_backtest(real_tape, params)
    text = " ".join(figure_caption(plots.account_figure(book)))
    assert "$38,886.50" in text, text
    assert "never fires" in text, "the shipped book has no flagged bar"


def test_the_shipped_evidence_panel_shows_every_one_of_its_sixteen_thousand_points(
    real_tape, params
):
    """n = 16,626 on the committed tape (SPEC §10.1), and all of them are drawn.

    The published R² is what the caption promises; a cloud thinned on the way to the page
    would look tighter or looser than the number beside it, and nothing would say so.
    """
    ev = mid_vs_print(real_tape, params)
    fig = plots.mid_vs_print_figure(ev)
    assert len(fig.data[0].x) == ev.n == 16_626
    assert f"R² = {ev.r2:.4f}" in figure_caption(fig)[0]


# --------------------------------------------------------------------------
# The rules that hold for both
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name,expected",
    [("account", "HERO_FIGURE_HEIGHT"), ("scatter", "PANEL_FIGURE_HEIGHT")],
)
def test_every_figure_declares_the_height_its_panel_reserves(name, expected, request):
    """The standing rule (DESIGN-BRIEF §5). Plotly draws to `layout.height` whatever the
    box says, so a figure that leaves it unset renders at 450 and paints over the panel
    below — which the dev app did for a day before anyone looked at the right screen.

    Each figure is pinned to **its own** token, not to "one of the two". The looser form
    passed a hero rendered at tile height, which is the same defect a size smaller: a 360px
    box inside a 600px panel leaves 240px of dead navy that reads as a rendering fault.
    """
    fig = request.getfixturevalue(name)
    assert fig.layout.height == getattr(T, expected), (
        f"{name} is {fig.layout.height}px, not {expected}"
    )
    assert fig.layout.margin.t == T.PANEL_FIGURE_MARGIN["t"], "the panel margin was not applied"


@pytest.mark.parametrize("name", ["account", "scatter"])
def test_nothing_is_drawn_in_the_band_above_the_plot(name, request):
    """DESIGN-BRIEF §6 rule 7. Captions are HTML in the panel; a figure that draws its own
    text up there collides with a wrapping legend at some width, and *some width* arrives."""
    fig = request.getfixturevalue(name)
    assert not fig.layout.annotations, "this figure draws text in the band above the plot"
    assert not fig.layout.title.text, "a panel header already carries the name"
    assert figure_caption(fig), "a figure with no caption tells a page nothing to render"


def test_presentation_sits_above_the_core_and_the_core_never_imports_it():
    """AD-12's layering, checked structurally rather than by substring.

    `plots` may read `engine` and `evidence`; neither may read `plots`, or a change to a
    chart becomes a change to the book. Parsed with `ast` for the reason T-83 gave when a
    skeptic found the obvious substring ban list matching none of
    `from .engine import run_backtest`.
    """
    for module in ("rules", "engine", "evidence", "tape", "live"):
        tree = ast.parse((PACKAGE / f"{module}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [a.name for a in node.names]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            assert not any("plots" in (n or "") for n in names), (
                f"{module}.py imports the presentation layer"
            )


def test_the_figures_reach_no_network(monkeypatch, book, evidence):
    """NFR-4. Drawing a figure is the last thing that should ever open a session."""
    import options_surface_lab.covered_call.live as live

    def explode(*_a, **_k):
        raise AssertionError("a figure builder opened an LSEG session")

    monkeypatch.setattr(live, "lseg_session", explode)
    plots.account_figure(book)
    plots.mid_vs_print_figure(evidence)


# --------------------------------------------------------------------------
def _with_points(evidence, points):
    """A copy of ``evidence`` carrying a different sample, for the refusal paths."""
    import dataclasses

    fitted = len(points) >= 3
    return dataclasses.replace(
        evidence,
        points=points,
        n=len(points),
        slope=evidence.slope if fitted else float("nan"),
        intercept=evidence.intercept if fitted else float("nan"),
        r2=evidence.r2 if fitted else float("nan"),
    )


def _empty_book(params):
    """A ``Book`` whose every frame is empty, with the real column sets."""
    from options_surface_lab.covered_call.engine import (
        BLOTTER_COLUMNS,
        Book,
        LEDGER_COLUMNS,
        SKIP_COLUMNS,
        WEEKLY_COLUMNS,
    )

    return Book(
        params=params,
        blotter=pd.DataFrame(columns=BLOTTER_COLUMNS),
        skips=pd.DataFrame(columns=SKIP_COLUMNS),
        ledger=pd.DataFrame(columns=LEDGER_COLUMNS),
        weekly=pd.DataFrame(columns=WEEKLY_COLUMNS),
    )
