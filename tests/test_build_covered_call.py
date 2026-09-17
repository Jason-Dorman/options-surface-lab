"""Tests for Assignment 2's published artifact (`build_covered_call.py`, T-79).

The page is graded, and every one of this project's worst defects has been deploy-only —
visible in the built file and in nothing else. What is checked here is what is specific to
*this* page; being a page at all (self-contained, classes that resolve, reachable) is
asserted of every page in `test_pages.py`.
"""

from __future__ import annotations

import datetime as dt
import re

import pytest

import build_covered_call as builder
from options_surface_lab.covered_call.engine import run_backtest
from options_surface_lab.covered_call.rules import Params
from options_surface_lab.covered_call.tape import load_tape
from options_surface_lab.page_shell import LOCAL_PATHS, SITE_PATHS
from pagelib import WORKFLOW, built_page, read

PAGE = "covered-call"


@pytest.fixture(scope="module")
def html() -> str:
    path = built_page(LOCAL_PATHS[PAGE])
    if not path.exists():
        pytest.skip(f"{path.name} not built in this working tree")
    return read(path)


@pytest.fixture(scope="module")
def synthetic_tape():
    """The seeded synthetic tape, on the same literal window `tests/covered_call/` uses.

    Synthesized here rather than imported: that conftest is scoped to its own directory.
    The window is a **literal** — a fixture anchored to the clock reports on the calendar,
    and one already failed CI on a Monday for a reason unrelated to the code under test
    (OQ-6, 2026-09-07).
    """
    from options_surface_lab.covered_call.tape import synthesize_tape

    return synthesize_tape(dt.date(2026, 9, 11), seed=7)


@pytest.fixture(scope="module")
def book():
    """The committed tape's book — what the page's numbers must equal.

    `load_tape` opens no session under any circumstances, so this reaches no network even
    on a machine with credentials (NFR-4).
    """
    params = Params()
    return run_backtest(load_tape(params=params), params)


# ------------------------------------------------------------------- the synthetic guard
def test_the_ci_guard_greps_for_the_marker_the_builder_emits():
    """The guard is a plain grep, so a reworded banner orphans it silently (T-45)."""
    workflow = read(WORKFLOW)
    assert builder.SYNTHETIC_MARKER.isascii(), "the marker must survive a grep"
    assert builder.SYNTHETIC_MARKER in workflow, (
        f"the CI guard no longer greps for {builder.SYNTHETIC_MARKER!r} — the covered-call "
        "page could publish a book run on a tape that is a shape, not a market"
    )


def test_the_two_pages_do_not_share_a_synthetic_marker():
    """One marker per page. Shared, one page's fabrication passes the other's check — and
    1.1's fallback panel and a synthetic covered-call tape are different fabrications."""
    import build_preview

    assert builder.SYNTHETIC_MARKER != build_preview.SYNTHETIC_MARKER


def test_the_committed_page_was_not_built_from_a_synthetic_tape(html):
    stale = builder.SYNTHETIC_MARKER in html
    assert not stale, (
        "the committed covered-call page was built from the synthetic tape — rebuild it "
        "with covered_call_tape.parquet present before submitting"
    )


def test_a_synthetic_book_is_self_identifying(synthetic_tape):
    """An unlabelled tape reads as synthetic, because that is the dangerous case, not the
    safe one (`Tape.synthetic` defaults True) — and the page must then say so in the words
    the CI guard greps for."""
    assert synthetic_tape.synthetic is True
    rendered = _render(Params(), tape=synthetic_tape)
    assert builder.SYNTHETIC_MARKER in rendered, "a fabricated book published quietly"
    assert "osl-warn" in rendered[rendered.index("<body>"):], "the banner must be loud"


# ------------------------------------------------------- the page says what the book says
def test_the_headline_numbers_come_from_the_engine(html, book):
    """I-13's shape, applied to the readouts: the page's numbers must be the book's.

    A number retyped in the builder is the one place on the page that can disagree with the
    engine, and it would disagree plausibly — the whole reason the ledger, skip log and
    weekly table are projections of the blotter rather than second sources (SPEC §1).

    Read off the **committed** page, so this also fails when the page is older than the
    module that renders it (the 2026-09-06 lesson: anything that changes what the page says
    needs a rebuild in the same commit).
    """
    assert _readouts(html) == _expected(book)


def test_the_headline_holds_on_a_book_with_skipped_weeks(synthetic_tape):
    """**The committed tape cannot tell a read-off number from a lucky one.**

    All ten of its weeks trade, so "entries" and "weeks" are the same integer and the
    premium sum equals any literal someone types. Both mutants survived the guard above for
    exactly that reason. The synthetic tape skips five weeks, which separates them — a
    fixture that never reaches a branch is a branch with no test, however many tests name
    it (T-57).
    """
    book = run_backtest(synthetic_tape, Params())
    weeks, entries = len(book.weekly), int(
        book.weekly["outcome"].isin(("ASSIGN", "EXPIRE")).sum()
    )
    assert 0 < entries < weeks, (
        f"this fixture must skip at least one week for the test to mean anything "
        f"({entries} entries over {weeks} weeks)"
    )
    assert _readouts(_render(Params(), tape=synthetic_tape)) == _expected(book)


def _readouts(html: str) -> list[str]:
    values = re.findall(r'data-osl-readout="\d">([^<]*)</div>', html)
    assert len(values) == 6, f"six readouts, found {len(values)}: {values}"
    return values


def _expected(book) -> list[str]:
    """The six headline strings, recomputed from the book's own weekly table."""
    weekly = book.weekly
    entries = int(weekly["outcome"].isin(("ASSIGN", "EXPIRE")).sum())
    assigned = int((weekly["outcome"] == "ASSIGN").sum())
    premium = float(weekly["premium"].fillna(0).sum())
    return [
        str(len(weekly)),
        f"{entries} of {len(weekly)}",
        f"{assigned} of {entries}" if entries else "0",
        f"${premium:,.2f}",
        f"${book.final_nav:,.2f}",
        f"{book.total_return:+.2%}",
    ]


def test_the_page_quotes_the_navs_closing_bar_not_the_last_ledger_row(html, book):
    """`final_nav` reads the last 15:00 ET row: the stock tape runs to a 19:00 stub, and on
    the committed tape the two differ by $10.65 (T-57). `max(ts)` one layer up — the same
    trap `rules` bans for bars, in the number a reader quotes."""
    stub = float(book.ledger["nav"].iloc[-1])
    assert f"${book.final_nav:,.2f}" in html
    if abs(stub - book.final_nav) > 0.005:
        assert f"${stub:,.2f}" not in html, "the page is quoting the post-close stub"


def test_the_window_and_the_cash_are_printed_from_params_not_retyped(html):
    """FR-14's discipline, early: the strategy a reader sees is the one the engine ran.

    Asserted against a *changed* `Params` rather than against the defaults — a builder that
    hardcoded the dates would satisfy the defaults perfectly and only be wrong the day
    someone changed one (the T-46 rule: compare against something the subject did not
    produce).
    """
    params = Params(start=dt.date(2026, 7, 13), end=dt.date(2026, 9, 4), start_cash=50_000.0)
    rendered = _render(params)
    assert "2026-07-13" in rendered and "2026-09-04" in rendered
    assert "$50,000" in rendered
    assert "2026-07-06" not in rendered, "the default window is hardcoded somewhere"


def test_the_strike_rule_on_the_page_is_the_rule_the_engine_applies(html):
    """`describe_strike_rule` exists so the printed sentence and `params` cannot say
    different things (SPEC §5). The page must render it, not paraphrase it."""
    assert Params().describe_strike_rule() in html


# ------------------------------------------------------------------------ where it lands
def test_the_builder_writes_the_route_the_workflow_guards(tmp_path):
    """`--site` is what puts the page on its route; the workflow greps a hardcoded path."""
    out = builder.build_covered_call(tmp_path)
    assert out == tmp_path / SITE_PATHS[PAGE]
    assert out.exists() and out.stat().st_size > 0
    assert f"_site/{SITE_PATHS[PAGE]}" in read(WORKFLOW)


def test_the_local_artifact_and_the_published_page_are_one_render(tmp_path, html):
    """Two destinations, one page. The only difference may be the nav hrefs — anything else
    and the artifact the PO checks is not the artifact CI ships (RUNBOOK §5)."""
    def strip(s: str) -> str:
        return re.sub(r'<div class="osl-nav">.*?</div>', "", s, flags=re.S)

    site_html = read(builder.build_covered_call(tmp_path))
    assert strip(site_html) == strip(html), (
        "the published page and the root artifact differ by more than their nav links"
    )


def _render(params: Params, *, tape=None) -> str:
    """Render the page and read it straight back, for tests that vary its inputs."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        return read(builder.build_covered_call(Path(tmp), params=params, tape=tape))
