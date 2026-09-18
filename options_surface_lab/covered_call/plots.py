"""Assignment 2's figures — FR-16's Reg T account and FR-17's fill evidence.

Presentation, and nothing else (AD-12): every number here is read off a ``Book`` or a
``MidVsPrint`` that was computed elsewhere. Nothing is recomputed on the way to a pixel —
a figure that derives its own statistic is a second source for a number the page already
prints, and SPEC §1's whole posture is that there is one.

**Figures are born panel-ready.** 1.1's builders emit a figure with a title and the page
then calls :func:`as_panel_figure` to strip it; that two-step exists because those figures
are shared with the Reflex app, which shows them standalone. This page is their only
consumer, so the step is skipped and the defect it invites goes with it — the dev app once
shipped un-panelised figures whose declared heights overflowed the boxes reserved for them
(DESIGN-BRIEF §8, 2026-09-02). Every figure below sets ``height`` explicitly, because
Plotly draws to ``layout.height`` regardless of the box and a taller figure paints over the
panel underneath.

**The captions are data, not drawn text** (T-47): :func:`with_caption` puts them in
``layout.meta`` and the panel renders them as HTML, where they wrap.

**Weekends are left in the account chart's axis.** A ``rangebreak`` would buy back ~28% of
the x axis, and it would also be a change of ruler — the kind this project has learned to
label rather than perform quietly (FR-10). The line across a weekend is flat because marks
carry forward and no bar exists to move them (S-7), so the gap is honest as drawn and
costs only space.
"""

from __future__ import annotations

import plotly.graph_objects as go

from options_surface_lab import theme as T
from options_surface_lab.covered_call.engine import FLAG_NEG_AVAILABLE, IM_RATE, MM_RATE
from options_surface_lab.covered_call.evidence import NON_SIMULTANEITY_CAVEAT
from options_surface_lab.page_shell import with_caption

#: FR-16's trace order, fixed. The page addresses these by index — the same contract
#: ``settle_vs_trade_figure``'s ``[Calls, Puts, y = x, bars]`` became when the as-of
#: listener started restyling it by position (T-42). Nothing restyles this figure today;
#: the order is pinned anyway, because the cost of pinning it is a constant and the cost of
#: discovering it was not pinned is a silently re-coloured chart.
#: Named as the account names them, not as the ledger columns do. "IM" and "MM" are
#: the engine's vocabulary; a reader meets these words on the Reg T cards above the
#: chart and in the brief itself ("Initial margin", "Maintenance margin"), so the
#: legend uses those and the ledger keeps its keys (T-59, 2026-09-18).
ACCOUNT_TRACES = ("NAV", "Initial", "Maintenance")

#: FR-17's, likewise. Points first so the two reference lines draw *over* the cloud rather
#: than under 16,000 markers.
EVIDENCE_TRACES = ("Contract-hours", "y = x", "Fit")

#: The ASCII anchor SPEC §11's publish guard keys on ("require the R² line"). The line it
#: guards is :meth:`MidVsPrint.headline`, which carries ``R²``, ``×`` and ``−`` — and a
#: guard is a shell grep over the built page, so it needs a phrase that is plain ASCII and
#: contains neither ``/`` nor ``·``: Plotly's JSON encoder ships a slash as ``\\/`` and the
#: same caption exists twice in the page, once as HTML and once inside ``layout.meta``
#: (T-45). Changing this string breaks the deploy, which is why it is a constant and not a
#: literal inside a caption.
FIT_CAPTION_PREFIX = "Fill assumption:"

#: Padding on the evidence panel's shared axis range, as a fraction of the span. The two
#: axes must carry the *same* range or ``y = x`` is not drawn at 45 degrees, and a reference
#: line that lies about its own slope is worse than no reference line.
_AXIS_PAD = 0.03


def _empty(message: str, height: int) -> go.Figure:
    """A themed "nothing to draw" panel. Never raise at a hole (AD-9).

    Declares its height like every other figure here: an empty figure that falls back to
    Plotly's default 450 renders taller than the box reserved for it and spills into the
    panel below, which reads as a rendering fault rather than as an empty result.
    """
    return go.Figure().update_layout(
        **T.figure_layout(title=T.title(message), height=height)
    )


# --------------------------------------------------------------------------
# FR-16 — the Reg T account
# --------------------------------------------------------------------------
def account_figure(book, *, height: int | None = None) -> go.Figure:
    """NAV, IM and MM over the window, on one axis, with the three values in one hover.

    The brief asks for one chart and FR-16 for "mouseover values", so the hover is
    ``x unified``: one box per bar carrying all three numbers, rather than three hovers a
    reader has to collect by moving the pointer.

    **One axis, shared with zero.** The panel's question is *does NAV stay above the
    requirement*, and that comparison is only meaningful on a common scale — which is also
    why a secondary axis for NAV would be wrong here however much flatter it makes the line
    look. The consequence is that NAV's own path is a ~2% band near the top of a chart that
    reaches down to zero; the return is the readout strip's job, not this panel's, and the
    caption points at the number that *does* answer this panel's question.

    **The hourly ledger is what is drawn** (SPEC §9), not the daily roll-up: the roll-up is
    a selection of these rows for a reader checking a week by hand, so a number in that
    table is by construction a number on this line.
    """
    height = height or T.HERO_FIGURE_HEIGHT
    ledger = book.ledger
    if ledger.empty:
        return with_caption(
            _empty("No bars in the window", height),
            "The ledger is empty — no stock bar in the window, so there is no account to draw.",
        )

    fig = go.Figure()
    for name, column, role in zip(ACCOUNT_TRACES, ("nav", "im", "mm"), ("nav", "im", "mm")):
        fig.add_trace(
            go.Scatter(
                x=ledger["ts"],
                y=ledger[column],
                mode="lines",
                name=name,
                line=T.account_line(role),
                hovertemplate="%{y:$,.2f}<extra>" + name + "</extra>",
            )
        )

    fig.update_layout(
        **T.figure_layout(
            height=height,
            margin=T.PANEL_FIGURE_MARGIN,
            hovermode="x unified",
            legend=T.legend(),
            xaxis=T.axis("Hourly bar"),
            yaxis=T.axis("Dollars", tickprefix="$", tickformat=","),
        )
    )
    return with_caption(fig, *_account_caption(book))


def _account_caption(book) -> tuple:
    """The two lines under FR-16's panel, both derived from the ledger the figure drew.

    The floor is read at **entry bars only**, because those are the only bars
    ``NEG_AVAILABLE`` is checked on. Quoting the all-bars minimum instead is how T-82's
    review came to publish $38,236 — a number off a thin 05:00 pre-market bar, which is
    ``max(ts)``'s mistake wearing different clothes.
    """
    ledger = book.ledger
    entries = ledger[ledger["entry"]] if "entry" in ledger else ledger.iloc[0:0]
    # Counted against the engine's own constant, not against "non-empty": a column of
    # NaN would satisfy the looser test and report a flag on every bar of a clean book.
    flags = int((ledger["flag"] == FLAG_NEG_AVAILABLE).sum()) if "flag" in ledger else 0

    if flags:
        verdict = (
            f"available went negative at {flags} bar(s) and the page flags the trade beside "
            "it — the rule still booked it, because the backtest reports what the rule did."
        )
    elif not entries.empty:
        floor = float(entries["available"].min())
        verdict = (
            f"available (NAV - IM) bottoms at ${floor:,.2f} at an entry bar — the only bars "
            "the flag is checked on — so NEG_AVAILABLE never fires on this book."
        )
    else:
        verdict = "No week entered, so available was never tested at an entry bar."

    return (
        f"NAV against the requirement it has to clear: IM = {IM_RATE:.0%} of long market "
        f"value, MM = {MM_RATE:.0%}. The short call is covered, so it adds $0 to both; when "
        "the book is flat all three fall to cash.",
        verdict,
    )


# --------------------------------------------------------------------------
# FR-17 — mid against the print
# --------------------------------------------------------------------------
def mid_vs_print_figure(evidence, *, height: int | None = None) -> go.Figure:
    """The near-the-money sample, the fit, and ``y = x`` — the case for filling at the mid.

    **``y = x`` is the line that matters, and the fit is the one that is asked for.** They
    differ in the sixth decimal on the committed tape (SPEC §10.2), so drawing both is what
    lets a reader see that rather than be told it. The fit is drawn only when one was
    actually estimated: below ``MIN_FIT_POINTS`` distinct mids ``fit_y`` returns nothing and
    this figure draws nothing, the same refusal posture ``iv_refusal`` gave FR-11.

    **Both axes carry one range and one pixel scale**, so the identity line sits at 45
    degrees whatever shape its panel is. A reference line that misstates its own slope is
    worse than none, and the reader's whole reading of the cloud — is the print above or
    below the mid — is read off that angle.

    ``Scattergl``: 16,626 SVG markers is a scroll that janks on a mid-range laptop. The
    sample is drawn **whole** — subsampling evidence offered as evidence would need saying
    out loud, and then the honest caption is longer than the saving. Hover carries the pair
    and not the contract: identity would cost ~200 KB of ``customdata`` for a label that
    cannot be aimed at a single point in a cloud this dense.
    """
    height = height or T.PANEL_FIGURE_HEIGHT
    points = evidence.points
    if points.empty:
        return with_caption(
            _empty("No near-the-money bars carried both a quote and a print", height),
            f"{FIT_CAPTION_PREFIX} {evidence.headline()}",
        )

    x, y = points["mid"], points["trdprc_1"]
    lo = float(min(x.min(), y.min()))
    hi = float(max(x.max(), y.max()))
    pad = (hi - lo) * _AXIS_PAD or 1.0
    axis_range = [lo - pad, hi + pad]
    line_x = [axis_range[0], axis_range[1]]

    fig = go.Figure()
    fig.add_trace(
        go.Scattergl(
            x=x,
            y=y,
            mode="markers",
            name=EVIDENCE_TRACES[0],
            marker=dict(color=T.MARK, size=T.SIZE_MARK, symbol=T.SYMBOL_MARK),
            hovertemplate="mid %{x:$,.3f}<br>print %{y:$,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=line_x,
            y=line_x,
            mode="lines",
            name=EVIDENCE_TRACES[1],
            line=dict(
                color=T.IDENTITY_LINE, dash="dash", width=T.IDENTITY_LINE_WIDTH
            ),
            hoverinfo="skip",
        )
    )
    fitted = evidence.fit_y(line_x)
    if fitted is not None:
        fig.add_trace(
            go.Scatter(
                x=line_x,
                y=fitted,
                mode="lines",
                name=EVIDENCE_TRACES[2],
                line=dict(color=T.FIT_LINE, width=T.FIT_LINE_WIDTH),
                hoverinfo="skip",
            )
        )

    fig.update_layout(
        **T.figure_layout(
            height=height,
            margin=T.PANEL_FIGURE_MARGIN,
            legend=T.legend(),
            xaxis=T.axis("Quoted mid ($)", range=axis_range),
            # `scaleanchor` is what actually makes the identity line 45 degrees. Equal
            # *ranges* are necessary and not sufficient: Plotly maps each axis onto its own
            # pixel span, so the same range in a 4:1 box renders `y = x` at about 14
            # degrees — the reference line lying about its slope in the one way a test that
            # compares two `range` tuples cannot see. Found by asking what the panel would
            # look like at full page width, not by a failing assertion.
            yaxis=T.axis(
                "Last print, TRDPRC_1 ($)",
                range=axis_range,
                scaleanchor="x",
                scaleratio=1,
            ),
        )
    )
    return with_caption(
        fig, f"{FIT_CAPTION_PREFIX} {evidence.headline()}", NON_SIMULTANEITY_CAVEAT
    )


__all__ = [
    "ACCOUNT_TRACES",
    "EVIDENCE_TRACES",
    "FIT_CAPTION_PREFIX",
    "account_figure",
    "mid_vs_print_figure",
]
