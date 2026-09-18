"""Assignment 2's page — SPEC §11's panels, composed (FR-14, FR-15, FR-16, FR-18, FR-21).

Application layer (AD-12): this module *arranges*. Every number it prints is read off a
``Book``, a ``MidVsPrint`` or the committed live state, and the two figures come from
``plots``. It computes one thing — nothing — which is what makes I-13 checkable: the blotter
rendered into the built page must equal ``run_backtest``'s, and a page that recomputed
anything would be a second source for a number the engine already owns (SPEC §1).

**Panels are numbered 1–7 as SPEC §11 lists them**, not only the figures. That differs from
1.1, where an index names a *figure* because the indices are also the as-of listener's
addressing scheme (``osl-fig-{n}``, T-12) — this page cross-filters nothing, so nothing is
addressed by number and the spec's own ordering can be printed as written. The live book is
[6], between the evidence and the write-up: the backtest is the body, the live run is what
follows from it, and the PO's prose closes the page.

**Everything is full width except the pair at [5] and [6].** Nine blotter columns and twenty
ledger columns need the room, and the two that do not — a scatter and a two-row live
blotter — sit beside each other so the page is not one column of identical slabs.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from options_surface_lab import theme as T
from options_surface_lab.covered_call import live as live_mod
from options_surface_lab.covered_call import plots, writeup
from options_surface_lab.covered_call.engine import (
    BLOTTER_COLUMNS,
    FLAG_NEG_AVAILABLE,
    LEDGER_COLUMNS,
    SKIP_COLUMNS,
    run_backtest,
)
from options_surface_lab.covered_call.evidence import mid_vs_print
from options_surface_lab.covered_call.rules import Params
from options_surface_lab.page_shell import PageShell

#: SPEC §14, printed under the strategy because *"a reader who cannot see them cannot judge
#: the book"*. Held here as the page's rendering of the spec's table; `tests/` pins the id
#: set, so a simplification added to §14 and not to the page fails rather than going quiet.
SIMPLIFICATIONS = (
    ("S-1", "100 shares, 1 contract, always."),
    ("S-2", "Exit is to wait: no buy-backs, no rolls."),
    ("S-3", "Expiry is the week's last session per the stock tape."),
    ("S-4", "No commissions or fees."),
    ("S-5", "No margin interest."),
    ("S-6", "No early assignment; dividends ignored."),
    ("S-7", "Marks: stock at the bar's print, option at the bar's mid, carried forward "
            "when absent; intrinsic on the expiry bar."),
    ("S-8", "Timestamps are exchange time, on LSEG's bar convention."),
    ("S-9", "Skipped weeks are logged, not booked."),
)

#: The rule ids the blotter's `note` column cites, so the table is legible without the spec.
RULE_IDS = (
    ("R-ENTRY-STOCK", "Buy 100 shares at the entry bar's print."),
    ("R-ENTRY-CALL", "Write 1 call at the selected strike, filled at the bar's midpoint."),
    ("R-EXPIRE", "At expiry, out of the money: the call expires, the shares stay."),
    ("R-ASSIGN", "At expiry, in the money: the call is assigned."),
    ("R-ASSIGN-SELL", "The assignment's stock leg — 100 shares delivered at the strike."),
)

#: Columns whose cells are figures: right-aligned and tabular, so a column of dollars lines
#: up at the decimal. Named rather than inferred from dtype — `qty` is an integer and a
#: number, `week` is a string and not one, and `flag` is neither.
_NUMERIC = {
    "qty", "limit", "fill", "cash_delta", "shares", "short_calls", "cash", "stock_mark",
    "call_mark", "lmv", "option_mv", "nav", "im", "mm", "available", "excess",
    "call_strike", "strike", "premium", "spot", "mid", "settle",
}

#: What an absent value prints as. SPEC §8: `limit` is `—` on EXPIRE/ASSIGN and `fill` is 0.
_ABSENT = "—"


@dataclass(frozen=True)
class Page:
    """Everything the builder needs to write the document, plus the records behind it.

    The records travel with the rendering so a test can hold the page to its own sources
    (I-13) without re-running the backtest and hoping it got the same inputs.
    """

    params: Params
    book: object
    evidence: object
    live: dict
    ident: str
    readouts: tuple
    warning_text: str
    panels: tuple

    @property
    def synthetic(self) -> bool:
        return bool(self.book.synthetic)


def build_page(tape, params: Params | None = None, *, shell: PageShell | None = None,
               live: dict | None = None) -> Page:
    """Run the book over `tape` and render SPEC §11's panels.

    `shell` is the builder's own, because a `PageShell` carries the "have I emitted
    plotly.js yet" flag and a second shell would request the library twice — or, worse,
    never (T-79).

    `live` overrides the committed live state, for the tests that need a book in each of
    its states: open, settled, and never run.
    """
    params = params or Params()
    shell = shell or PageShell("Covered call")
    book = run_backtest(tape, params)
    evidence = mid_vs_print(tape, params)
    live = live_mod.load_state(params) if live is None else live

    panels = (
        _strategy_panel(shell, params),
        shell.figure_panel(
            2, "Reg T account", "FR-16 · NAV against the requirement",
            plots.account_figure(book), width=T.W_FULL, hero=True,
        ),
        _blotter_panel(shell, book),
        _ledger_panel(shell, book),
        # Hero height in a half-width panel, which is the one place on this site a
        # figure's *box* is load-bearing. The scatter ties its two axes to one pixel scale
        # so `y = x` is genuinely 45 degrees; in a wide box Plotly honours that by
        # letterboxing the data into the middle third. Roughly square is what makes the
        # constraint free, and 5 columns at hero height is roughly square.
        shell.figure_panel(
            5, "Mid vs print", "FR-17 · the fill assumption",
            plots.mid_vs_print_figure(evidence, height=T.HERO_FIGURE_HEIGHT),
            width=T.W_HALF,
        ),
        _live_panel(shell, params, live),
        _writeup_panel(shell),
    )

    return Page(
        params=params,
        book=book,
        evidence=evidence,
        live=live,
        ident=_ident(params, book),
        readouts=_headline(book),
        warning_text=_warning_text(book),
        panels=panels,
    )


# --------------------------------------------------------------------------
# The chrome's text
# --------------------------------------------------------------------------
def _ident(params: Params, book) -> str:
    return (
        f"<b>{params.root}</b> covered call &nbsp;·&nbsp; weekly &nbsp;·&nbsp; "
        f"<b>{params.start} → {params.end}</b> &nbsp;·&nbsp; {params.interval} bars "
        f"&nbsp;·&nbsp; {len(book.weekly)} weeks"
    )


def _warning_text(book) -> str:
    """The banner, or "". A synthetic book renders perfectly — ten plausible weeks of a
    market that never happened — so its *absence* of a banner is the dangerous case."""
    return "" if not book.synthetic else (
        f"Built from a {SYNTHETIC_MARKER}, not the LSEG pull — every number below is a "
        "shape, not a market. This must not be published."
    )


#: Grepped by the CI publish guard; distinct from 1.1's "synthetic panel" so one page's
#: fabrication cannot pass the other's check. Lives here with the text that carries it.
SYNTHETIC_MARKER = "synthetic tape"

#: SPEC §11's per-page publish guards, as the literal strings CI greps for. Kept here so the
#: page and the workflow cannot drift apart, and pinned to both by
#: `tests/test_build_covered_call.py` — the coupling that broke when a caption was
#: shortened and left the guard hunting a phrase the page had stopped saying (T-45).
#:
#: **Two kinds, with different rules.** A CAPTION marker is prose that exists *twice* in the
#: built page — as panel HTML and inside the figure's `layout.meta` — so it must be plain
#: ASCII with no `/` and no `·`: Plotly's encoder ships a slash as `\/` and the separators
#: are `&nbsp;·&nbsp;`, and a guard spanning either silently never matches. A STRUCTURAL
#: marker is markup, never inside figure JSON, so `</td>` is safe there and nowhere else.
CAPTION_MARKERS = (
    "Fill assumption:",   # FR-17's fit line — SPEC §11's "require the R-squared line"
)

#: At least one entry was booked. A blotter side cell, not a rule id: the rule ids are also
#: printed in the strategy panel's key, so grepping `R-ENTRY-STOCK` would pass on a page
#: whose blotter was empty — which is the exact failure the guard exists to catch.
BLOTTER_ENTRY_MARKER = "<td>BUY</td>"

#: ...and at least one week resolved. Either is enough; a window can be all of one.
BLOTTER_SETTLED_MARKERS = ("<td>EXPIRE</td>", "<td>ASSIGN</td>")


def entries(book) -> int:
    """Weeks the rule actually traded — a week with a settled outcome had an entry."""
    return int(book.weekly["outcome"].isin(("ASSIGN", "EXPIRE")).sum())


def _headline(book) -> tuple:
    """The six numbers the book leads with, each read off `book` and never restated."""
    weekly = book.weekly
    booked = entries(book)
    assigned = int((weekly["outcome"] == "ASSIGN").sum())
    premium = float(weekly["premium"].fillna(0).sum())
    return (
        ("Weeks in window", len(weekly)),
        ("Entries booked", f"{booked} of {len(weekly)}"),
        ("Assigned at expiry", f"{assigned} of {booked}" if booked else "0"),
        ("Premium collected", f"${premium:,.2f}"),
        ("Final NAV", f"${book.final_nav:,.2f}"),
        ("Return on start cash", f"{book.total_return:+.2%}"),
    )


# --------------------------------------------------------------------------
# [1] The strategy — FR-14
# --------------------------------------------------------------------------
def _strategy_panel(shell: PageShell, params: Params) -> str:
    """`Params` whole, the rule in words, and every stated simplification.

    FR-14's acceptance is that the panel prints **every field** of `Params` and **every**
    S-x — so the fields are walked with `dataclasses.fields` rather than listed. A listed
    set silently stops being complete the first time a parameter is added, and the page
    would then describe a strategy with one more knob than it shows.
    """
    rows = [
        (name, (str(_present(value)), "osl-num" if name in _NUMERIC else ""))
        for name, value in (
            (f.name, getattr(params, f.name)) for f in dataclasses.fields(params)
        )
    ]
    param_table = shell.table(("Parameter", "Value"), rows, kv=True)
    simplifications = shell.table(
        ("Id", "Stated simplification"),
        [((sid, "osl-label"), text) for sid, text in SIMPLIFICATIONS],
        kv=True,
    )
    rules = shell.table(
        ("Note", "What fired"),
        [((rid, "osl-label"), text) for rid, text in RULE_IDS],
        kv=True,
    )

    body = "".join(
        f'<div class="osl-commentary-item"><div class="osl-commentary-q">{title}</div>{inner}</div>'
        for title, inner in (
            (
                "The rule, and the whole parameter record",
                f'<div class="osl-note">One covered call a week on <b>{params.root}</b> '
                f"over <b>{params.start} → {params.end}</b>, on "
                f"<b>${params.start_cash:,.0f}</b> of starting cash: buy {params.shares} "
                f"shares and write {params.contracts} call at the {params.interval} bar "
                "the rule names, then hold through expiry. "
                f"{params.describe_strike_rule()} At expiry the call is assigned when the "
                f"settlement print is {_itm_words(params)}; otherwise it expires and the "
                "shares stay. A week whose quote is invalid is skipped and logged, never "
                "booked at an invented price.</div>" + param_table,
            ),
            ("Stated simplifications", simplifications),
            ("Rule ids in the blotter's notes", rules),
        )
    )
    return shell.panel(
        "Strategy",
        f"FR-14 · {params.strike_rule} · {params.itm_rule} ITM test",
        body,
        n=1,
        width=T.W_FULL,
        body_class="osl-commentary",
    )


def _itm_words(params: Params) -> str:
    """SD-6 in words, read off `params` so the sentence cannot outlive the decision."""
    return (
        "strictly above the strike" if params.itm_rule == "strict"
        else "at or above the strike"
    )


# --------------------------------------------------------------------------
# [3] The blotter and the skip log — FR-15, SPEC §8
# --------------------------------------------------------------------------
def _blotter_panel(shell: PageShell, book) -> str:
    """The brief's columns exactly, and below them the weeks the rule declined.

    The skip log shares this panel because it is the *other half* of the same statement:
    the brief grades the strategy doing what it says, and a skipped week is the strategy
    doing something. A page that showed only the trades would read as a rule that never
    had to decline (SPEC §8.2).
    """
    blotter = shell.table(
        tuple(BLOTTER_COLUMNS),
        (_row(record, BLOTTER_COLUMNS) for record in book.blotter.to_dict("records")),
    )
    if len(book.skips):
        skips = shell.table(
            tuple(SKIP_COLUMNS),
            (
                _row(record, SKIP_COLUMNS, classes={"reason": "osl-skip"})
                for record in book.skips.to_dict("records")
            ),
        )
        skip_note = f"{len(book.skips)} week(s) skipped — no trade was booked."
    else:
        skips = ""
        skip_note = "No week was skipped: every week in the window carried a tradable quote."

    body = (
        f'<div class="osl-note" style="padding-bottom:8px">{len(book.blotter)} booked rows. '
        "Cash moves only here — every other number on this page is a projection of this "
        "table.</div>"
        f"{blotter}"
        f'<div class="osl-commentary-q" style="padding:14px 0 5px 0">Skip log</div>'
        f'<div class="osl-note" style="padding-bottom:8px">{skip_note}</div>'
        f"{skips}"
    )
    return shell.panel(
        "Blotter and skip log",
        f"FR-15 · {len(book.blotter)} rows · {len(book.skips)} skips",
        body,
        n=3,
        width=T.W_FULL,
    )


# --------------------------------------------------------------------------
# [4] The ledger — SPEC §9
# --------------------------------------------------------------------------
def _ledger_panel(shell: PageShell, book) -> str:
    """The daily roll-up: each session's closing bar, so a week can be checked by hand.

    **Every column, not a chosen subset.** The roll-up is a *selection of hourly rows*,
    never a re-aggregation, and a table that dropped columns would invite the question of
    what else had been dropped. Twenty columns do not fit a panel, which is what
    `TABLE_MIN_WIDTH` is for: it scrolls rather than deforming (T-68).
    """
    daily = book.daily_ledger()
    body = (
        f'<div class="osl-note" style="padding-bottom:8px">'
        f"{len(daily)} sessions, each at its closing bar — a selection of the "
        f"{len(book.ledger)} hourly rows the chart above draws, never a re-aggregation, so "
        "a number here is a number on that line. <b>available</b> is NAV − IM and "
        "<b>excess</b> is NAV − MM; <b>mark_carried</b> says a mark came from an earlier "
        "bar (S-7).</div>"
        + shell.table(
            tuple(LEDGER_COLUMNS),
            (
                _row(record, LEDGER_COLUMNS, classes={"flag": "osl-flag"})
                for record in daily.to_dict("records")
            ),
        )
    )
    return shell.panel(
        "Ledger — daily",
        f"SPEC §9 · {len(daily)} sessions · Reg T",
        body,
        n=4,
        width=T.W_FULL,
    )


# --------------------------------------------------------------------------
# [6] The live book — FR-21
# --------------------------------------------------------------------------
def _live_panel(shell: PageShell, params: Params, live: dict) -> str:
    """The same rule, run forward on real quotes with simulated capital.

    FR-21 asks the panel to **state what is historical and what is live**, because the two
    books look identical in a table and mean entirely different things: one is a window
    that has already happened, the other is a position that is still open.
    """
    blotter_rows = live.get("blotter") or []
    position = live.get("position") or {}
    call = position.get("call")

    if not blotter_rows:
        body = (
            '<div class="osl-note">No live week has been booked yet. The forward run is '
            "one command — <code>python -m options_surface_lab.covered_call.live enter</code> "
            "— and writes nothing until it has a readable bar.</div>"
        )
        note = "FR-21 · not yet run"
    else:
        table = shell.table(
            tuple(BLOTTER_COLUMNS),
            (_row(record, BLOTTER_COLUMNS) for record in blotter_rows),
        )
        state = (
            f"Short the <b>{call['strike']:.0f}</b> call expiring <b>{call['expiry']}</b> "
            f"against {position.get('shares', 0)} shares — <b>still open</b>; it resolves "
            "at that session's closing bar."
            if call else
            "Flat — the call resolved and the position is closed."
        )
        body = (
            '<div class="osl-note" style="padding-bottom:8px">'
            "Everything above this panel is <b>historical</b>: a window that has already "
            f"happened, {params.start} → {params.end}. This is the same rule running "
            "<b>forward</b> on quotes as they arrive, with simulated capital, booked by "
            "<code>covered_call/live.py</code> rather than by hand — the same "
            f"<code>select_strike</code> and the same blotter rows. {state}</div>"
            f"{table}"
            + _capture_block(shell, live)
        )
        note = f"FR-21 · {len(blotter_rows)} rows · cash ${live.get('cash', 0):,.2f}"

    return shell.panel("Live book", note, body, n=6, width=T.W_HALF)


def _capture_block(shell: PageShell, live: dict) -> str:
    """The raw quotes behind the live rows — FR-21's *"with their raw quotes"*.

    This is the panel's evidence, not its decoration: a booked fill with no quote beside it
    is a number a reader has to take on trust, and the whole argument for the midpoint is
    that the bid and the ask were what they were.
    """
    captures = live.get("captures") or []
    if not captures:
        return ""
    last = captures[-1]
    under = last.get("underlying") or {}
    call = (live.get("position") or {}).get("call") or {}
    quoted = next(
        (c for c in last.get("chain") or [] if c.get("ric") == call.get("ric")), {}
    )
    rows = [
        (("Entry bar", "osl-label"), str(last.get("entry_bar", _ABSENT))),
        (("Stock print", "osl-label"), (_present(under.get("trdprc_1")), "osl-num")),
        (("Stock bar high / low", "osl-label"),
         (f"{_present(under.get('high_1'))} / {_present(under.get('low_1'))}", "osl-num")),
        (("Call bid / ask", "osl-label"),
         (f"{_present(quoted.get('bid'))} / {_present(quoted.get('ask'))}", "osl-num")),
        (("Last-trade offsets (stock / call)", "osl-label"),
         (f"{_present(under.get('c_sec_ofst'))}s / {_present(quoted.get('c_sec_ofst'))}s",
          "osl-num")),
        (("RIC form", "osl-label"), str(last.get("chain", [{}])[0].get("ric_form", _ABSENT))),
    ]
    return (
        '<div class="osl-commentary-q" style="padding:14px 0 5px 0">Raw quotes at the bar</div>'
        + shell.table(("Observation", "Value"), rows, kv=True)
    )


# --------------------------------------------------------------------------
# [7] The write-up — FR-19
# --------------------------------------------------------------------------
def _writeup_panel(shell: PageShell) -> str:
    """The PO's prose, and the slots that are still empty — loudly.

    FR-19's mechanism, inherited whole from FR-7: an unwritten slot renders in `NEGATIVE`,
    fails its test, and is refused by the Pages workflow. This is the only part of the page
    with no figure behind it, so its absence would otherwise look like a design choice.
    """
    method = shell.table(
        ("Step", "What was decided"),
        [((label, "osl-label"), text) for label, text in writeup.METHOD],
        kv=True,
    )
    paragraphs = "".join(
        f'<div class="osl-note" style="padding-bottom:10px">{text}</div>'
        for text in (
            writeup.OBSERVATION_POINT, writeup.SYNCHRONISATION, writeup.MIDPOINT_EVIDENCE
        )
    )
    answers = "".join(
        '<div class="osl-commentary-item">'
        f'<div class="osl-commentary-q">{question}</div>'
        f"{_answer(answer)}"
        "</div>"
        for question, answer in zip(writeup.QUESTIONS, writeup.ANSWERS)
    )
    # The method block sits ABOVE its own grid rather than inside it. As a sixth column
    # it was several times the height of the five answers beside it, and on a grid whose
    # panels deliberately do not stretch, one item towering over its row-mates reads as a
    # rendering fault rather than as emphasis (DESIGN-BRIEF §5).
    body = (
        '<div class="osl-commentary-q">Method — the decision hierarchy</div>'
        f"{method}{paragraphs}"
        f'<div class="osl-commentary-q" style="padding-top:6px">'
        "FR-19 — the five questions, answered by the PO</div>"
        f'<div class="osl-commentary" style="padding:0">{answers}</div>'
    )
    return shell.panel(
        "Write-up",
        "FR-19 · authored by the PO",
        body,
        n=7,
        width=T.W_FULL,
    )


def _answer(text: str) -> str:
    if text == writeup.UNWRITTEN:
        return f'<div class="osl-note osl-commentary-todo">{writeup.UNWRITTEN}</div>'
    return f'<div class="osl-note">{text}</div>'


# --------------------------------------------------------------------------
# Cells
# --------------------------------------------------------------------------
def _row(record: dict, columns, *, classes: dict | None = None) -> list:
    """One table row: every column of `columns`, in order, classed by what the cell is."""
    classes = classes or {}
    out = []
    for name in columns:
        value = _present(record.get(name))
        css = classes.get(name, "") if value not in ("", _ABSENT) else ""
        if not css and name in _NUMERIC:
            css = "osl-num"
        out.append((value, css) if css else value)
    return out


def _present(value) -> str:
    """A value as the page prints it — absence as `—`, never as `nan` or `None`.

    `nan` in a table is the AD-9 failure in miniature: it looks like a value, it is not one,
    and a reader cannot tell whether the number was missing or the code was.
    """
    import math

    if value is None:
        return _ABSENT
    if isinstance(value, float):
        if math.isnan(value):
            return _ABSENT
        return f"{value:,.2f}" if abs(value) >= 0.005 or value == 0 else f"{value:g}"
    text = str(value)
    return _ABSENT if text in ("", "None", "NaT", "nan") else text


__all__ = [
    "BLOTTER_ENTRY_MARKER",
    "BLOTTER_SETTLED_MARKERS",
    "CAPTION_MARKERS",
    "Page",
    "RULE_IDS",
    "SIMPLIFICATIONS",
    "SYNTHETIC_MARKER",
    "build_page",
    "entries",
]
