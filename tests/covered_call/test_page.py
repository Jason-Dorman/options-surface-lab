"""T-59 — SPEC §11's panels, and I-13: the page says what its sources say.

`page.py` arranges and computes nothing, so the tests here are mostly of one shape: **a
value on the page is a value in the `Book`, the `MidVsPrint` or the live state.** That is
what makes I-13 checkable at all — a page that recomputed anything would be a second source
for a number the engine already owns (SPEC §1), and the two would agree right up until they
did not.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import re
from pathlib import Path

import pytest

from options_surface_lab import theme as T
from options_surface_lab.covered_call import page as page_mod
from options_surface_lab.covered_call import writeup
from options_surface_lab.covered_call.engine import BLOTTER_COLUMNS, run_backtest
from options_surface_lab.covered_call.evidence import mid_vs_print
from options_surface_lab.covered_call.rules import Params
from options_surface_lab.page_shell import PageShell

SPEC = Path(__file__).resolve().parents[2] / "docs" / "SPEC-COVERED-CALL.md"


@pytest.fixture(scope="module")
def page(synthetic_tape, params):
    """The synthetic book: it skips weeks and raises the synthetic banner, so it reaches
    branches the committed tape never does (T-79's lesson about a fixture that cannot tell
    a read-off number from a lucky one)."""
    return page_mod.build_page(synthetic_tape, params, shell=PageShell("t"))


@pytest.fixture(scope="module")
def real_page(real_tape, params):
    return page_mod.build_page(real_tape, params, shell=PageShell("t"))


def _html(page) -> str:
    return "\n".join(page.panels)


def _table_headers(markup: str, first_header: str) -> list:
    """The column names of the one table whose first column header is `first_header`."""
    for table in re.findall(r"<table[^>]*>.*?</table>", markup, re.S):
        heads = [html.unescape(h) for h in re.findall(r"<th>(.*?)</th>", table, re.S)]
        if heads and heads[0] == first_header:
            return heads
    raise AssertionError(f"no table whose first column is {first_header!r}")


def _table_rows(markup: str, first_header: str) -> list:
    """Rows of the one table whose first column header is `first_header`, as text cells.

    Parsed back out of the rendered markup rather than read off the frame the page was
    handed — that is the whole point of I-13. A test that asserts against the DataFrame it
    also passed in proves the DataFrame equals itself.
    """
    for table in re.findall(r"<table[^>]*>.*?</table>", markup, re.S):
        heads = re.findall(r"<th>(.*?)</th>", table, re.S)
        if heads and html.unescape(heads[0]) == first_header:
            return [
                [html.unescape(re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ")
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
                for row in re.findall(r"<tr>(.*?)</tr>", table, re.S)[1:]
            ]
    raise AssertionError(f"no table on the page whose first column is {first_header!r}")


# --------------------------------------------------------------------------
# The shape of the page — SPEC §11
# --------------------------------------------------------------------------
def test_the_page_carries_every_panel_the_spec_orders(page):
    """Seven panels, in SPEC §11's order, with the live book at [6].

    Pinned as a list rather than a count: a panel dropped and another duplicated keeps the
    count, and the page would be missing a graded requirement while looking complete.
    """
    names = re.findall(r'osl-panel-name">(.*?)<', _html(page))
    assert names == [
        "Strategy",
        "Reg T account",
        "Blotter and skip log",
        "Ledger — daily",
        "Mid vs print",
        "Live book",
        "Write-up",
    ]
    assert len(re.findall(r'class="osl-panel ', _html(page))) == 7

    # The indices, too. SPEC §11 numbers these panels and a reader navigates by them; a
    # panel that quietly loses its `[n]` renumbers every panel after it in the reader's
    # head while the page still renders perfectly.
    assert [int(n) for n in re.findall(r'osl-panel-n">\[(\d+)\]', _html(page))] == [
        1, 2, 3, 4, 5, 6, 7
    ]


def test_every_panel_declares_a_width_the_grid_defines(page):
    """CSS fails open: an undefined `.osl-w{n}` is not an error, it is no styling at all,
    and the panel silently collapses to one column. That shipped once (2026-09-02)."""
    widths = {int(n) for n in re.findall(r"osl-w(\d+)", _html(page))}
    assert widths <= set(range(1, T.GRID_COLUMNS + 1))
    for width in widths:
        assert f".osl-w{width} {{" in T.PAGE_CSS, f".osl-w{width} has no rule"


def test_the_two_figures_are_the_ones_plots_builds(page):
    """FR-16 and FR-17 come from `plots`, not from a figure this module assembles."""
    markup = _html(page)
    assert markup.count("plotly-graph-div") == 2
    assert 'id="osl-fig-2"' in markup and 'id="osl-fig-5"' in markup


# --------------------------------------------------------------------------
# I-13 — the page says what its sources say
# --------------------------------------------------------------------------
def test_i13_the_rendered_blotter_is_the_engines_blotter(real_page):
    """SPEC §12, I-13: the blotter *in the built page* equals `run_backtest`'s.

    Every cell, every row, in order — re-parsed out of the HTML. The T-44 lesson applied to
    a table: a panel can be right in its geometry and wrong in every value it states, and
    nothing about the render says which.
    """
    rendered = _table_rows(_html(real_page), BLOTTER_COLUMNS[0])
    expected = real_page.book.blotter.to_dict("records")
    assert len(rendered) == len(expected), "the page and the engine disagree on row count"

    for row, record in zip(rendered, expected):
        assert len(row) == len(BLOTTER_COLUMNS)
        for cell, column in zip(row, BLOTTER_COLUMNS):
            _assert_cell_is(cell, record[column], column)


def _assert_cell_is(cell: str, value, column: str) -> None:
    """A rendered cell against the raw value — **not** against `page._present(value)`.

    The first version of I-13 compared each cell to `_present(record[column])`, which is
    the very function that produced it: rounding money to whole dollars changed the page
    and the expectation together and the test stayed green. That is T-46's
    guard-that-reads-back-its-own-effect, landed on again in a new place, and it is why
    this reads the number back out of the string instead.
    """
    import math

    if isinstance(value, float) and math.isnan(value):
        assert cell == page_mod._ABSENT, f"{column}: NaN rendered as {cell!r}"
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        assert cell != page_mod._ABSENT, f"{column}: {value!r} rendered as an absence"
        assert float(cell.replace(",", "")) == pytest.approx(float(value), abs=5e-3), (
            f"{column}: page says {cell!r}, the engine says {value!r}"
        )
    else:
        expected = page_mod._ABSENT if value in (None, "") else str(value)
        assert cell == expected, f"{column}: page says {cell!r}, the engine says {value!r}"


def test_a_money_cell_keeps_its_cents(real_page):
    """Two decimal places, because a covered call's premium lives in them.

    A blotter rounded to whole dollars reconciles against nothing — the mid of 6.01/6.08 is
    6.045, and a page printing `6` for it describes a trade that was never booked.
    """
    fills = [row[BLOTTER_COLUMNS.index("fill")]
             for row in _table_rows(_html(real_page), BLOTTER_COLUMNS[0])]
    assert any("." in cell and cell.split(".")[-1] != "00" for cell in fills), (
        "no fill on the page carries cents — has the money format been rounded?"
    )


def test_i13_the_page_prints_the_r_squared_the_evidence_measured(real_page):
    """The other half of I-13. `evidence` may not import `engine`, so the invariant is two
    claims about two records, not one comparison (T-83's correction to the spec)."""
    markup = _html(real_page)
    assert f"R² = {real_page.evidence.r2:.4f}" in markup


def test_the_headline_numbers_are_the_books_own(page):
    """The readout strip is six numbers, and every one is read off `book`.

    The synthetic tape is what makes this a test: it skips weeks, so `entries` and `weeks`
    are different integers and the premium is not the sum of every week. On the committed
    tape all ten weeks trade, and a retyped number would agree with the book by accident.
    """
    readouts = dict(page.readouts)
    book = page.book
    assert readouts["Weeks in window"] == len(book.weekly)
    assert readouts["Entries booked"] == f"{page_mod.entries(book)} of {len(book.weekly)}"
    assert page_mod.entries(book) < len(book.weekly), "the fixture skips no week"
    assert readouts["Final NAV"] == f"${book.final_nav:,.2f}"
    assert readouts["Return on start cash"] == f"{book.total_return:+.2%}"


def test_the_headline_tracks_a_changed_window_rather_than_a_remembered_number(real_tape):
    """Varying the input is what tells a read-off number from a lucky one.

    Both tapes happen to hold ten weeks, so a hardcoded `10` agrees with the book on every
    fixture this suite has — the same trap T-79 hit when `entries` and `weeks` were the
    same integer. A shorter window is the cheapest input that cannot be guessed.
    """
    short = Params(start=dt.date(2026, 8, 3), end=dt.date(2026, 9, 11))
    page = page_mod.build_page(real_tape, short, shell=PageShell("t"))
    weeks = len(page.book.weekly)
    assert weeks < 10, "the shortened window is not shorter — the fixture cannot tell"
    assert dict(page.readouts)["Weeks in window"] == weeks


def test_the_ledger_table_is_the_daily_roll_up_whole(real_page):
    """Every column and every session (SPEC §9). A roll-up with columns quietly dropped
    invites the question of what else was dropped, and the width floor exists so it does
    not have to be."""
    from options_surface_lab.covered_call.engine import LEDGER_COLUMNS

    markup = _html(real_page)
    rendered = _table_rows(markup, LEDGER_COLUMNS[0])
    daily = real_page.book.daily_ledger()
    assert len(rendered) == len(daily)
    assert all(len(row) == len(LEDGER_COLUMNS) for row in rendered)

    # The header as well as the cells. Checking row width alone let a mutant that
    # truncated the *header* through — the table then renders twenty cells under nineteen
    # names, which silently relabels every column after the missing one.
    assert _table_headers(markup, LEDGER_COLUMNS[0]) == list(LEDGER_COLUMNS)


def test_a_missing_value_prints_as_an_absence_not_as_nan(real_page):
    """AD-9 in miniature. `nan` in a table looks like a value and is not one, and a reader
    cannot tell whether the number was missing or the code was."""
    markup = _html(real_page)
    for ghost in (">nan<", ">NaN<", ">None<", ">NaT<"):
        assert ghost not in markup, f"{ghost} reached the page"
    assert page_mod._ABSENT in markup, "nothing is ever absent — is the guard reaching cells?"


# --------------------------------------------------------------------------
# FR-14 — the sentence is pinned to the params
# --------------------------------------------------------------------------
def test_the_strategy_panel_prints_every_field_of_params(page):
    """FR-14's acceptance, literally: *"the strategy panel prints every field of `Params`"*.

    Walked with `dataclasses.fields`, so a parameter added to `Params` and not to the page
    fails here — a listed set silently stops being complete, and the page would then
    describe a strategy with one more knob than it shows.
    """
    rendered = {row[0] for row in _table_rows(_html(page), "Parameter")}
    expected = {f.name for f in dataclasses.fields(page.params)}
    assert rendered == expected, f"missing from the page: {sorted(expected - rendered)}"


def test_the_printed_rule_is_the_rule_the_engine_ran(page):
    """FR-14: *"a test pins that sentence to `params` so the page cannot describe a rule the
    engine did not run"*.

    `describe_strike_rule` is the rule's own words — rendered, never paraphrased — and the
    ITM half is re-derived from `params.itm_rule` rather than asserted as a string, so
    flipping SD-6 changes the page or fails here.
    """
    markup = _html(page)
    assert page.params.describe_strike_rule() in markup

    strict = page.params.itm_rule == "strict"
    assert ("strictly above the strike" in markup) is strict
    assert ("at or above the strike" in markup) is not strict


def test_the_page_prints_every_stated_simplification_the_spec_names(page):
    """SPEC §14: *"printed on the page under the strategy, because a reader who cannot see
    them cannot judge the book"*.

    The id set is checked against **the spec file**, not against the page's own tuple — a
    simplification added to §14 and not to the page is exactly the drift the lockstep rule
    exists for, and a test comparing a constant to itself would never see it.
    """
    in_spec = set(re.findall(r"^\| (S-\d+) \|", SPEC.read_text(encoding="utf-8"), re.M))
    assert in_spec, "SPEC §14's table could not be read — has its shape changed?"
    assert {sid for sid, _ in page_mod.SIMPLIFICATIONS} == in_spec

    rendered = {row[0] for row in _table_rows(_html(page), "Id")}
    assert rendered == in_spec, f"not on the page: {sorted(in_spec - rendered)}"


def test_every_rule_id_the_blotter_cites_is_explained(real_page):
    """A note reading `R-ASSIGN-SELL` is unreadable without the key, and the key is on the
    page rather than in the spec, because the page is what gets graded."""
    notes = " ".join(real_page.book.blotter["note"].astype(str))
    cited = set(re.findall(r"\bR-[A-Z-]+\b", notes))
    explained = {rid for rid, _ in page_mod.RULE_IDS}
    assert cited <= explained, f"unexplained on the page: {sorted(cited - explained)}"


# --------------------------------------------------------------------------
# FR-21 — the live book
# --------------------------------------------------------------------------
def test_the_live_panel_carries_the_booked_rows_and_their_raw_quotes(real_page):
    """FR-21's acceptance: *"the two 09-14 rows are on the page with their raw quotes"*.

    The quotes are the panel's evidence, not its decoration — a booked fill with no bid and
    ask beside it is a number a reader has to take on trust, and the whole argument for the
    midpoint is that the quote was what it was.
    """
    live = real_page.live
    assert live["blotter"], "no live rows — is covered_call_live.json committed?"

    markup = _html(real_page)
    for row in live["blotter"]:
        assert page_mod._present(row["fill"]) in markup
        assert row["side"] in markup

    capture = live["captures"][-1]
    call = live["position"]["call"]
    quoted = next(c for c in capture["chain"] if c["ric"] == call["ric"])
    for value in (capture["underlying"]["trdprc_1"], quoted["bid"], quoted["ask"]):
        assert page_mod._present(value) in markup, f"{value} is not beside the fill"


def test_the_live_panel_says_which_half_of_the_page_is_live(real_page):
    """FR-21: *"the panel states what is historical and what is live"*.

    The two books are identical in a table and mean entirely different things — one is a
    window that has already happened, the other is a position that is still open.
    """
    markup = _html(real_page)
    assert "historical" in markup and "forward" in markup
    assert "still open" in markup, "an open call must say so"


def test_a_live_book_that_has_not_run_says_so_rather_than_rendering_empty(
    real_tape, params
):
    """AD-9. An empty panel with no words in it reads as a rendering fault, and FR-21's is
    the one panel whose emptiness is a legitimate state — it is empty until Monday."""
    blank = page_mod.build_page(
        real_tape, params, shell=PageShell("t"),
        live={"blotter": [], "skips": [], "captures": [], "position": {}, "cash": 0},
    )
    markup = "\n".join(blank.panels)
    assert "No live week has been booked yet" in markup


def test_a_settled_live_book_stops_claiming_an_open_position(real_tape, params):
    """The panel's state sentence is derived, not written for this week.

    Friday 09-18's settlement leg closes the call; a page that still said "still open"
    afterwards would be stating a market fact that had stopped being true, on the one panel
    whose subject is the present tense.
    """
    import copy

    settled = copy.deepcopy(page_mod.live_mod.load_state(params))
    settled["position"]["call"] = None
    settled["position"]["short_calls"] = 0

    markup = "\n".join(
        page_mod.build_page(real_tape, params, shell=PageShell("t"), live=settled).panels
    )
    assert "still open" not in markup
    assert "Flat" in markup


# --------------------------------------------------------------------------
# FR-19 — the write-up
# --------------------------------------------------------------------------
def test_an_unwritten_answer_is_loud(page):
    """FR-19 inherits FR-7's mechanism whole: red on the page, a failing test, a CI refusal.

    This is the only part of the page with no figure behind it, so its absence would
    otherwise look like a design choice rather than a missing rubric item.
    """
    markup = _html(page)
    for question in writeup.QUESTIONS:
        assert question in markup, "a write-up question is missing from the page"

    unwritten = markup.count(writeup.UNWRITTEN)
    expected = sum(1 for a in writeup.ANSWERS if a == writeup.UNWRITTEN)
    assert unwritten == expected
    if unwritten:
        assert markup.count("osl-commentary-todo") == unwritten, (
            "an unwritten answer rendered as ordinary prose"
        )


def test_the_po_s_methodology_block_is_on_the_page(page):
    """T-70's written half — the Rule / Fill / Stock / Audit / Limitation hierarchy and the
    three paragraphs behind it. Rendered verbatim: this module may not paraphrase the PO."""
    markup = _html(page)
    for _, text in writeup.METHOD:
        assert text in markup
    for text in (writeup.OBSERVATION_POINT, writeup.SYNCHRONISATION,
                 writeup.MIDPOINT_EVIDENCE):
        assert text in markup


# --------------------------------------------------------------------------
# The synthetic banner
# --------------------------------------------------------------------------
def test_a_synthetic_book_raises_the_banner_and_a_real_one_does_not(page, real_page):
    """A synthetic book renders perfectly — ten plausible weeks of a market that never
    happened — so the *absence* of a banner is the dangerous case."""
    assert page.synthetic and page_mod.SYNTHETIC_MARKER in page.warning_text
    assert not real_page.synthetic and real_page.warning_text == ""
