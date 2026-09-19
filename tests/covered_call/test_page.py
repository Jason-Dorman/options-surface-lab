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
from options_surface_lab.covered_call.engine import (
    BLOTTER_COLUMNS,
    FLAG_NEG_AVAILABLE,
    LEDGER_COLUMNS,
    run_backtest,
)
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


def _find_table(markup: str, want) -> tuple:
    """`(headers, rows)` of the one table matching `want`.

    `want` is either the **full** header list, matched exactly, or a single string matched
    against the first column. The exact form exists because the blotter and the ledger now
    share a first header — both start with `Time`, since both are keyed on a bar — so
    matching on column one alone silently handed back the blotter when the ledger was
    asked for. Here that surfaced as `33 == 49`; a subtler change would have found a table
    of the right shape carrying the wrong contents, which is the whole class I-13 is for.
    """
    exact = not isinstance(want, str)
    for table in re.findall(r"<table[^>]*>.*?</table>", markup, re.S):
        heads = [html.unescape(h) for h in re.findall(r"<th>(.*?)</th>", table, re.S)]
        if not heads:
            continue
        if (heads == list(want)) if exact else (heads[0] == want):
            rows = [
                [html.unescape(re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ")
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
                for row in re.findall(r"<tr>(.*?)</tr>", table, re.S)[1:]
            ]
            return heads, rows
    raise AssertionError(f"no table on the page matching {want!r}")


def _table_headers(markup: str, want) -> list:
    return _find_table(markup, want)[0]


def _table_rows(markup: str, want) -> list:
    """Parsed back out of the rendered markup rather than read off the frame the page was
    handed — that is the whole point of I-13. A test that asserts against the DataFrame it
    also passed in proves the DataFrame equals itself."""
    return _find_table(markup, want)[1]


# --------------------------------------------------------------------------
# The shape of the page — SPEC §11
# --------------------------------------------------------------------------

def test_the_page_carries_every_panel_the_spec_orders(page):
    """Seven panels in the order the assignment's example page uses (SPEC §11, reworked
    2026-09-18): the two charts, the blotter, the ledger, the rules and write-up, the
    contracts queried, and the live book last.

    Pinned as a list rather than a count: a panel dropped and another duplicated keeps the
    count, and the page would be missing a graded requirement while looking complete.
    """
    markup = _html(page)
    assert re.findall(r'osl-panel-name">(.*?)<', markup) == [
        "Growth of the book",
        "Midpoint assumption",
        "Blotter: Executed Trades",
        "Position, cash, and margin over time",
        "Covered-call rules and write-up",
        "Expired contracts this book queried",
        "Live book",
    ]
    assert len(re.findall(r'class="osl-panel ', markup)) == 7
    assert [int(n) for n in re.findall(r'osl-panel-n">\[(\d+)\]', markup)] == [
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
    """FR-16 and FR-17 come from `plots`, not from a figure this module assembles, and they
    open the page together — the example leads with both charts, above the tables."""
    markup = _html(page)
    assert markup.count("plotly-graph-div") == 2
    assert 'id="osl-fig-1"' in markup and 'id="osl-fig-2"' in markup


# --------------------------------------------------------------------------
# I-13 — the page says what its sources say
# --------------------------------------------------------------------------

def test_i13_the_rendered_blotter_is_the_engines_blotter(real_page):
    """SPEC §12, I-13: the blotter *in the built page* equals `run_backtest`'s.

    Every cell, every row, in order — re-parsed out of the HTML. The T-44 lesson applied to
    a table: a panel can be right in its geometry and wrong in every value it states, and
    nothing about the render says which.

    The **OCC rides inside Instrument** as the brief's column description asks, so that cell
    carries two values and is checked for both.
    """
    rendered = _table_rows(_html(real_page), list(page_mod._BLOTTER_HEADERS))
    expected = real_page.book.blotter.to_dict("records")
    assert len(rendered) == len(expected), "the page and the engine disagree on row count"

    for row, record in zip(rendered, expected):
        assert len(row) == len(page_mod._BLOTTER_RENDERED)
        for cell, column in zip(row, page_mod._BLOTTER_RENDERED):
            if column == "instrument":
                assert record["instrument"] in cell
                occ = str(record.get("occ") or "").strip()
                assert (occ in cell) if occ else True, "the OCC subtitle is missing"
            else:
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
    at = page_mod._BLOTTER_RENDERED.index("fill")
    fills = [row[at] for row in _table_rows(_html(real_page), list(page_mod._BLOTTER_HEADERS))]
    assert any("." in cell and cell.split(".")[-1] != "00" for cell in fills), (
        "no fill on the page carries cents — has the money format been rounded?"
    )


def test_i13_the_page_prints_the_r_squared_the_evidence_measured(real_page):
    """The other half of I-13. `evidence` may not import `engine`, so the invariant is two
    claims about two records, not one comparison (T-83's correction to the spec)."""
    markup = _html(real_page)
    assert f"R² = {real_page.evidence.r2:.4f}" in markup



def test_the_cards_are_the_reg_t_account_at_the_last_booked_bar(real_page):
    """FR-16 is *"used like an account"*, so the strip is the account (2026-09-18).

    It carried six statistics about the backtest — weeks, entries, premium, return — which
    is a summary of a study. Every card is now a cell of the last `event_ledger` row, and
    this is I-13 extended to the strip: the cards say what the ledger says.

    Read against the **event** ledger, never `ledger.iloc[-1]`: the last hourly row is a
    post-close stub, which is T-62's trap and the reason `final_nav` exists.
    """
    last = real_page.book.event_ledger().iloc[-1]
    cards = {label: value for label, value, *_ in real_page.readouts}

    assert list(cards) == [
        "Cash", "Stock LMV", "Short option", "NAV / equity",
        "Initial margin", "Maintenance", "Available funds", "Excess equity",
    ]
    for label, column in (
        ("Cash", "cash"), ("Stock LMV", "lmv"), ("Short option", "option_mv"),
        ("NAV / equity", "nav"), ("Initial margin", "im"), ("Maintenance", "mm"),
        ("Available funds", "available"), ("Excess equity", "excess"),
    ):
        shown = float(cards[label].replace("$", "").replace(",", "").replace("\u2212", "-"))
        assert shown == pytest.approx(float(last[column]), abs=5e-3), label


def test_every_card_says_where_its_number_comes_from(real_page):
    """A Reg T figure a reader cannot check is a figure they have to take on trust, and the
    rates in the hints are read from the engine so the words cannot outlive the ledger."""
    from options_surface_lab.covered_call.engine import IM_RATE, MM_RATE

    hints = {label: (rest[0] if rest else "") for label, _value, *rest in real_page.readouts}
    assert all(hints.values()), f"a card has no hint: {hints}"
    assert f"{IM_RATE:.0%}" in hints["Initial margin"]
    assert f"{MM_RATE:.0%}" in hints["Maintenance"]
    assert "NAV − initial" in hints["Available funds"]
    assert "NAV − maintenance" in hints["Excess equity"]



def test_the_cards_track_a_changed_input_rather_than_a_remembered_number(real_tape):
    """Varying the input is what tells a read-off number from a lucky one.

    Both tapes hold ten weeks and the same $75,000, so a hardcoded figure agrees with the
    book on every fixture this suite has — the trap T-79 hit when `entries` and `weeks`
    were the same integer. Funding the account differently is the cheapest input that
    cannot be guessed, and it has to move cash and NAV together.
    """
    poorer = Params(start_cash=50_000.0)
    page = page_mod.build_page(real_tape, poorer, shell=PageShell("t"))
    cards = {label: value for label, value, *_ in page.readouts}
    last = page.book.event_ledger().iloc[-1]

    assert cards["NAV / equity"] == f"${float(last['nav']):,.2f}"
    assert cards["NAV / equity"] != f"${75_000.0:,.2f}"



def test_the_ledger_table_is_one_row_per_booked_event(real_page):
    """SPEC §9 as amended 2026-09-18: keyed on the blotter's bars, not on sessions.

    A reader checking the book by hand checks it against the blotter, so the two tables
    have to read straight across. Every column the page promises is present, and the row
    count is the engine's selection — not a number this test remembers.
    """
    markup = _html(real_page)
    expected = list(LEDGER_HEADERS)
    assert [h for _, h in page_mod.PAGE_LEDGER_COLUMNS] == expected, (
        "PAGE_LEDGER_COLUMNS no longer matches the eleven columns the assignment's example "
        "prints — see LEDGER_HEADERS"
    )
    rendered = _table_rows(markup, expected)

    events = real_page.book.event_ledger()
    assert len(rendered) == len(events)
    assert len(events) < len(real_page.book.daily_ledger()), (
        "the event ledger is no smaller than the daily one — the fixture cannot tell them apart"
    )
    assert all(len(row) == len(expected) for row in rendered)
    assert _table_headers(markup, expected) == expected


def test_the_short_call_cell_names_the_contract_the_blotter_wrote(real_page):
    """Three ledger columns folded into one cell, so the cell has to carry all three.

    `short_calls`, `call_strike` and `call_expiry` became **Short call** to reach the
    example's eleven columns. A fold that lost the strike would print "1 × C 07-10" on every
    covered row and read as perfectly reasonable.
    """
    rows = real_page.book.event_ledger()
    covered = rows[rows["short_calls"] > 0]
    assert len(covered), "no covered row in the fixture"

    at = [name for name, _ in page_mod.PAGE_LEDGER_COLUMNS].index("short_call")
    cells = [row[at] for row in _table_rows(_html(real_page), list(LEDGER_HEADERS))]
    for _, record in covered.iterrows():
        strike = f"{float(record['call_strike']):g}"
        expiry = str(record["call_expiry"])[5:10]
        assert any(strike in c and expiry in c for c in cells), (
            f"no Short call cell names the {strike} call expiring {expiry}"
        )
    assert any(c == "flat" for c in cells), "a flat row must say so, not print an empty cell"


def test_a_breached_account_is_flagged_beside_the_row(real_tape):
    """FR-16: *"you could not have put the trade on — say so"*, on the table as well as the
    caption.

    `NEG_AVAILABLE` never fires under SD-3's funding, so this builds the case rather than
    hunting for it — the same reason `test_engine.py` funds an account at $1,000. A branch
    no fixture reaches is a branch with no test, however many tests name it (T-57).
    """
    poor = Params(start_cash=1_000.0)
    page = page_mod.build_page(real_tape, poor, shell=PageShell("t"))
    assert (page.book.ledger["flag"] == FLAG_NEG_AVAILABLE).any(), "the flag never fired"

    at = [name for name, _ in page_mod.PAGE_LEDGER_COLUMNS].index("available")
    cells = [row[at] for row in _table_rows(_html(page), list(LEDGER_HEADERS))]
    assert any(FLAG_NEG_AVAILABLE in c for c in cells), (
        "a row the engine flagged is printed as an ordinary number"
    )
    assert "osl-flag" in _html(page), "the flagged cell is not rendered loudly"


def test_the_contracts_table_reads_its_rics_off_the_blotter(real_page):
    """T-82's defect, in a new place: which form an expired contract answers under depends
    on how long ago it expired, so a table that *rebuilt* the RIC could name a contract that
    returned no bars — and it would look entirely plausible.

    Compared against the blotter's own strings, which is the only source that can be right.
    """
    booked = {
        str(r["instrument"]) for r in real_page.book.blotter.to_dict("records")
        if str(r["instrument"]) != real_page.params.underlying
    }
    assert booked, "no option was written in the fixture"

    listed = {row[1] for row in _table_rows(_html(real_page), ["Contract", "RIC"])}
    assert listed == booked, (
        f"the contracts table and the blotter disagree: {listed ^ booked}"
    )


def test_every_ledger_row_is_a_row_the_chart_draws(real_page):
    """*"A selection, never a re-aggregation"* (SPEC §1). Each row exists in the hourly
    frame, which is what lets a number in the table be a number on the line above it."""
    hourly = {str(ts) for ts in real_page.book.ledger["ts"]}
    for ts in real_page.book.event_ledger()["ts"]:
        assert str(ts) in hourly, f"{ts} is in the table and not in the chart"


def test_a_missing_value_prints_as_an_absence_not_as_nan(real_page):
    """AD-9 in miniature. `nan` in a table looks like a value and is not one, and a reader
    cannot tell whether the number was missing or the code was."""
    markup = _html(real_page)
    for ghost in (">nan<", ">NaN<", ">None<", ">NaT<"):
        assert ghost not in markup, f"{ghost} reached the page"
    assert page_mod._ABSENT in markup, "nothing is ever absent — is the guard reaching cells?"


BRIEF = Path(__file__).resolve().parents[2] / "docs" / "ASSIGNMENT-2-COVERED-CALL.md"

#: The ledger as the assignment's example page prints it. Written out here rather than read
#: from `page.PAGE_LEDGER_COLUMNS`, which is the thing under test: deriving the expectation
#: from the constant means deleting a column changes the page *and* the expectation together
#: and the suite stays green. That is T-46's guard-that-reads-back-its-own-effect, and it
#: survived a mutant here before this list existed.
#: Which blotter sides take a direction colour, written out here rather than read from
#: `page.SIDE_CLASS`, which is the thing under test. Deriving the expectation from the
#: constant means adding `EXPIRE` to it changes the page *and* the expectation together and
#: the suite stays green — T-46's guard-that-reads-back-its-own-effect, which survived a
#: mutant here before this literal existed.
DIRECTIONAL_SIDES = {"BUY": "osl-up", "SELL": "osl-down"}

LEDGER_HEADERS = (
    "Date", "Cash", "Shares", "Short call", "Spot", "LMV", "Opt MV", "NAV",
    "Initial", "Maint", "Available",
)



def test_the_blotter_headers_are_exactly_the_ones_the_brief_names(real_page):
    """*"Blotter (non-negotiable)"* — the brief names these columns, so the page uses them
    and **only** them.

    Read out of **the brief file**, not out of `COLUMN_LABELS`: a test comparing the page
    to the page's own dict proves the dict equals itself, and what is asserted here is
    conformance to a precedence-1 document. Equality, not containment — the OCC was a ninth
    column until 2026-09-18, which says the same thing in a shape the brief does not ask
    for. It is a subtitle inside Instrument now, which is what the brief's own column
    description says.
    """
    table = (
        BRIEF.read_text(encoding="utf-8")
        .split("## Blotter (non-negotiable)", 1)[1]
        .split("##", 1)[0]
    )
    named = [
        row.split("|")[1].strip()
        for row in table.splitlines()
        if row.startswith("|") and "---" not in row
    ][1:]
    assert named, "the brief's blotter table could not be read — has its shape changed?"

    rendered = _table_headers(_html(real_page), list(page_mod._BLOTTER_HEADERS))
    assert rendered == named, (
        f"the brief names {named} and the page renders {rendered}"
    )


def test_a_side_and_its_cash_carry_their_direction(real_page):
    """PO, 2026-09-18, reversing the 09-17 decision that only exceptions take colour.

    `BUY` green and `SELL` red in the side column; the cash column coloured by the **sign of
    the number**, not by the side. Those are the same answer on this book — every BUY pays
    out and every SELL pays in — and reading it off the side would still be the wrong rule:
    an assignment's stock leg is a `SELL` that pays in, and a row whose cash did not move
    must take neither colour.
    """
    markup = _html(real_page)
    blotter = re.search(r'<table class="osl-table">.*?</table>', markup, re.S).group(0)
    rows = re.findall(r"<tr>(.*?)</tr>", blotter, re.S)[1:]
    assert rows, "no blotter rows to check"

    side_at = page_mod._BLOTTER_RENDERED.index("side")
    cash_at = page_mod._BLOTTER_RENDERED.index("cash_delta")
    sides = set()
    for row in rows:
        cells = re.findall(r"<td([^>]*)>(.*?)</td>", row, re.S)
        side_cls, side = cells[side_at]
        cash_cls, cash = cells[cash_at]
        sides.add(side.strip())

        expected = DIRECTIONAL_SIDES.get(side.strip(), "")
        assert (expected in side_cls) if expected else ("osl-up" not in side_cls
                                                        and "osl-down" not in side_cls), (
            f"{side.strip()} is classed {side_cls!r}"
        )

        amount = float(cash.replace(",", "").replace("\u2212", "-"))
        want = "osl-up" if amount > 0 else "osl-down" if amount < 0 else ""
        if want:
            assert want in cash_cls, f"cash {amount} is classed {cash_cls!r}"
        else:
            assert "osl-up" not in cash_cls and "osl-down" not in cash_cls

    assert {"BUY", "SELL"} <= sides, "the fixture never exercises both directions"
    assert sides & {"EXPIRE", "ASSIGN"}, "no resolution row to prove it stays uncoloured"
    assert page_mod.SIDE_CLASS == DIRECTIONAL_SIDES, (
        "SIDE_CLASS has gained or lost a side — see DIRECTIONAL_SIDES"
    )


def test_the_occ_is_a_subtitle_inside_instrument(real_page):
    """The brief: *"Stock or option RIC; OCC as a subtitle"*. One cell, two lines."""
    markup = _html(real_page)
    assert "OCC" not in page_mod._BLOTTER_HEADERS, "the OCC is a column again"

    option = next(r for r in real_page.book.blotter.to_dict("records") if r["occ"])
    assert f'{option["instrument"]}<div class="osl-subcell">' in markup, (
        "the RIC and its OCC are not in one cell"
    )



def test_no_table_header_is_an_engine_key(real_page):
    """SPEC §9: *"Column names are lower case in the code ...; the page title-cases them."*

    A snake_case header on a graded page is a DataFrame leaking through the presentation
    layer. Checked over every header the page renders, so a column added later cannot slip
    through un-labelled.
    """
    markup = _html(real_page)
    for want in (
        list(page_mod._BLOTTER_HEADERS),
        [header for _, header in page_mod.PAGE_LEDGER_COLUMNS],
    ):
        for header in _table_headers(markup, want):
            assert "_" not in header, f"{header!r} is an engine key, not a column name"
            assert header[0].isupper(), f"{header!r} is not title-cased"



def test_every_engine_column_has_a_label(real_page):
    """A column the engine adds and `COLUMN_LABELS` does not know renders as its raw key.

    `labels()` fails soft on purpose — an unfinished column should look unfinished rather
    than take the page down — which is exactly why the completeness check belongs here.
    The ledger is exempt: the page renders eleven columns of its own choosing, and
    `PAGE_LEDGER_COLUMNS` carries their headers.
    """
    from options_surface_lab.covered_call.engine import SKIP_COLUMNS

    for columns in (BLOTTER_COLUMNS, SKIP_COLUMNS):
        missing = [c for c in columns if c not in page_mod.COLUMN_LABELS]
        assert not missing, f"no header label for: {missing}"


# --------------------------------------------------------------------------
# FR-14 — the sentence is pinned to the params
# --------------------------------------------------------------------------
def test_the_write_up_prints_every_field_of_params(page):
    """FR-14's acceptance: *"the strategy panel prints every field of `Params`"*.

    The strategy stopped being a panel of its own on 2026-09-18 — it folds into the
    write-up, where the example page keeps its rules — so this now asserts of the page what
    it used to assert of one panel. The requirement is that the fields are *printed*.

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
