"""T-57 — the engine, and SPEC-COVERED-CALL §12's invariant suite (NFR-6).

The invariants are the point of this file. Each one is the executable half of the
brief's first grading criterion — *"logically consistent"* — and each runs over
**both** tapes: the seeded synthetic one, which carries a named week for every skip
path, and the committed real one, which is what the page will be built from. A test
that only ever saw the synthetic tape would be testing the generator.

Two rules from earlier sessions shape how they are written:

* **Compare a thing against something it did not produce** (T-46). The invariants
  recompute from the *blotter* and the *tape* — parsing the blotter's own ``time``
  and ``instrument`` columns, re-reading quotes out of ``tape.bars`` — rather than
  from anything ``run_backtest`` handed back on the side. I-1 reconciles the ledger
  against the blotter; I-9 re-runs ``select_strike`` on a chain it rebuilds itself.
* **A test written for a defect must be watched to fail on it.** Every guard here
  was mutation-checked; the ones worth naming are noted in place.
"""
from __future__ import annotations

import datetime as dt
import pathlib

import numpy as np
import pandas as pd
import pytest

from options_surface_lab.covered_call.engine import (
    BLOTTER_COLUMNS,
    CLOSING_BAR_HOUR_ET,
    FLAG_NEG_AVAILABLE,
    IM_RATE,
    MM_RATE,
    MONEY_DP,
    STATE_FLAT,
    STATE_STOCK_ONLY,
    Book,
    build_ledger,
    run_backtest,
    settlement_print,
    window_weeks,
)
from options_surface_lab.covered_call.rules import (
    SKIP_NO_QUOTE,
    SKIP_NO_STOCK_PRINT,
    SKIP_NO_STRIKE,
    SKIP_SHORT_WEEK,
    Params,
    entry_bar_ts,
    closing_bar_ts,
    is_itm,
    select_strike,
    valid_mid,
)
from options_surface_lab.covered_call.tape import Tape, synthesize_tape
from options_surface_lab.option_surface_utils import parse_option_ric

SKIP_REASONS = {SKIP_NO_STOCK_PRINT, SKIP_NO_STRIKE, SKIP_NO_QUOTE, SKIP_SHORT_WEEK}


# --------------------------------------------------------------------------
# Fixtures — the two books every invariant runs over
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def synthetic_book(synthetic_tape, params) -> Book:
    return run_backtest(synthetic_tape, params)


@pytest.fixture(scope="session")
def real_book(real_tape, params) -> Book:
    return run_backtest(real_tape, params)


@pytest.fixture(params=["synthetic", "real"], scope="session")
def book(request) -> Book:
    """Each invariant runs over both books (SPEC §12). The real one skips if absent."""
    return request.getfixturevalue(f"{request.param}_book")


@pytest.fixture(params=["synthetic", "real"], scope="session")
def book_and_tape(request):
    book = request.getfixturevalue(f"{request.param}_book")
    tape = request.getfixturevalue(f"{request.param}_tape")
    return book, tape


# --------------------------------------------------------------------------
# Helpers the invariants use — each rebuilds from the blotter, not from the engine
# --------------------------------------------------------------------------
def _blotter_times(book: Book) -> pd.DatetimeIndex:
    """The blotter's own ``time`` column, parsed back into exchange time.

    Deliberately read off the rendered column rather than from a timestamp the
    engine kept on the side: the blotter is the primary artifact (SPEC §1), so an
    invariant that reconciles against it has to reconcile against what it *says*.
    """
    return pd.DatetimeIndex(
        pd.to_datetime(book.blotter["time"]).dt.tz_localize(book.params.tz)
    )


def _bar_row(tape: Tape, ric: str, ts) -> dict | None:
    hits = tape.bars[(tape.bars["ric"] == ric) & (tape.bars["ts"] == ts)]
    return None if hits.empty else hits.iloc[0].to_dict()


def _stock_print_at(tape: Tape, ts) -> float | None:
    row = _bar_row(tape, tape.stock["ric"].iloc[0], ts)
    if row is None or pd.isna(row["trdprc_1"]):
        return None
    return float(row["trdprc_1"])


# ==========================================================================
# The window — SPEC §3.2 item 3
# ==========================================================================
def test_the_window_must_end_on_a_last_session_day(synthetic_tape):
    """A window ending mid-week would leave a short call open at the last bar.

    The engine refuses rather than inventing a close-out (DR-1): there is no price
    on the tape for a position the strategy never intended to exit. A Saturday `end`
    is the quiet version of the same mistake — every week is whole, so the straddle
    guard says nothing, and the window simply ends on a day no call resolves on.
    """
    saturday = Params(start=dt.date(2026, 7, 6), end=dt.date(2026, 9, 12))
    with pytest.raises(ValueError, match="not a last-session day"):
        window_weeks(synthetic_tape, saturday)


def test_a_week_the_window_only_half_covers_is_refused_not_quietly_dropped(synthetic_tape):
    """Straddling is the silent case, so it is the one that raises.

    Trading the inside half would book an entry whose expiry session the window does
    not carry; dropping it would break I-10, which says every week without an entry
    is in the skip log with a reason. Neither is acceptable, so neither happens.
    """
    straddle = Params(start=dt.date(2026, 7, 8), end=dt.date(2026, 9, 11))  # mid-week start
    with pytest.raises(ValueError, match="straddle"):
        window_weeks(synthetic_tape, straddle)


def test_a_tape_for_another_name_is_refused_at_the_door(synthetic_tape, params):
    """The failure that renders perfectly and is entirely wrong.

    ``tape.stock`` selects on ``kind == "stock"``, never on the RIC, so handing the
    engine somebody else's tape produced a complete, plausible book — priced off one
    underlying and written against another's chain, with every invariant green.
    """
    bars = synthetic_tape.bars.copy()
    bars.loc[bars["kind"] == "stock", "ric"] = "SPY.P"
    with pytest.raises(ValueError, match="Params.underlying"):
        run_backtest(Tape(bars=bars, meta=dict(synthetic_tape.meta)), params)


def test_a_tape_with_no_stock_bars_says_what_is_missing(synthetic_tape, params):
    bars = synthetic_tape.bars[synthetic_tape.bars["kind"] != "stock"].copy()
    with pytest.raises(ValueError, match="no stock bars"):
        run_backtest(Tape(bars=bars, meta=dict(synthetic_tape.meta)), params)


def test_a_window_with_no_weeks_on_the_tape_says_so(synthetic_tape):
    far_future = Params(start=dt.date(2027, 1, 4), end=dt.date(2027, 1, 8))
    with pytest.raises(ValueError, match="no trading weeks"):
        window_weeks(synthetic_tape, far_future)


def test_the_windows_weeks_are_the_tapes_weeks_inside_it(synthetic_tape, params):
    weeks = window_weeks(synthetic_tape, params)
    assert [w.label for w in weeks] == [
        f"2026-W{n}" for n in range(28, 38)
    ]
    assert weeks[0].entry_day >= params.start and weeks[-1].expiry_day == params.end


# ==========================================================================
# The weekly loop — SPEC §4, and the four reasons a week does not trade
# ==========================================================================
def test_every_skip_reason_is_reached_on_the_synthetic_tape(synthetic_book):
    """SPEC §3.4's named roles exist so this test is a lookup, not a hunt."""
    reasons = set(synthetic_book.skips["reason"])
    assert reasons == SKIP_REASONS, f"unreached skip path(s): {SKIP_REASONS - reasons}"


def test_a_skip_names_the_week_the_role_fixture_says_it_should(synthetic_book, role_weeks):
    """Each named pathology produces *its* reason, not merely some reason.

    The mutation that motivates this: swapping the order of the strike check and the
    quote check still skips both weeks, and a test that only counted reasons passed.
    """
    by_week = dict(zip(synthetic_book.skips["week"], synthetic_book.skips["reason"]))
    assert by_week[role_weeks["no_quote_at_entry"].label] == SKIP_NO_QUOTE
    assert by_week[role_weeks["no_strike_above_spot"].label] == SKIP_NO_STRIKE
    assert by_week[role_weeks["short_week"].label] == SKIP_SHORT_WEEK
    assert by_week[role_weeks["half_session_entry_day"].label] == SKIP_NO_STOCK_PRINT


def test_a_flat_week_with_no_quote_buys_no_stock_either(synthetic_book):
    """SPEC §4 step 3 — the entry is the combo.

    Buying the shares and failing to write the call is a different strategy (long
    stock), so the skip covers both legs. The skip's own detail says so, because a
    reader looking at a flat week that bought nothing needs to know it was a choice.

    **The week is found by its state, not by its role.** The first version asked
    ``role_weeks["no_quote_at_entry"]`` — and on seed 7 that week skips while the
    book is already holding shares, so the flat branch was never entered and a
    mutant that bought the stock anyway survived. The assertion now insists a
    *flat* no-quote week exists before it tests one.
    """
    flat_skips = synthetic_book.skips[
        (synthetic_book.skips["reason"] == SKIP_NO_QUOTE)
        & (synthetic_book.skips["state_at_skip"] == STATE_FLAT)
    ]
    assert len(flat_skips), "the fixture never skips a quote while flat — nothing is tested"
    for skip in flat_skips.to_dict("records"):
        assert "the entry is the combo" in skip["detail"]
        day = skip["detail"].split(" at ")[1].split()[0]
        booked = synthetic_book.blotter[
            synthetic_book.blotter["time"].str.startswith(day)
        ]
        assert booked.empty, f"{skip['week']}: a skipped flat week booked {list(booked['side'])}"


def test_no_week_that_skipped_booked_a_row(synthetic_book, role_weeks):
    """The general form of the rule above: a skip and a booking are exclusive.

    Complements I-10, which pairs weeks with reasons; this one pairs the *entry day*
    with the blotter, which is what catches a leg that fired before the skip did.
    """
    entry_days = {
        w.entry_day: w.label for w in role_weeks.values()
    }
    for record in synthetic_book.skips.to_dict("records"):
        week = next((w for w in role_weeks.values() if w.label == record["week"]), None)
        if week is None:
            continue
        same_day = synthetic_book.blotter[
            synthetic_book.blotter["time"].str.startswith(str(week.entry_day))
        ]
        assert same_day.empty, f"{record['week']} skipped and still booked rows"
    assert entry_days, "role fixture is empty"


def test_shares_are_kept_through_a_skipped_week(synthetic_book):
    """SPEC §4's STOCK_ONLY branch — uncovered, logged, and nothing invented."""
    stock_only = synthetic_book.skips[
        synthetic_book.skips["state_at_skip"] == STATE_STOCK_ONLY
    ]
    assert len(stock_only), "the fixture never skips while holding shares"
    ledger = synthetic_book.ledger.set_index("ts")
    for week in stock_only["week"]:
        bars = ledger[ledger["week"] == week]
        assert (bars["shares"] == 100).all(), f"{week}: shares moved on a skipped week"
        assert (bars["short_calls"] == 0).all(), f"{week}: a call appeared without a row"


def test_every_skip_row_says_what_the_tape_actually_showed(book):
    """SPEC §8.2 — the skip log is how the page says *"no bid/ask -> skip"* happened.

    A reason without a detail is a claim without evidence: the reader cannot check
    a skipped week against the tape, which is the only thing the table is for. A
    mutation that blanked the detail survived the rest of the suite.
    """
    if book.synthetic:
        assert len(book.skips) >= 4, (
            "the synthetic arm has no skips — this test would assert nothing"
        )
    for record in book.skips.to_dict("records"):
        assert record["detail"].strip(), f"{record['week']} skipped with no detail"
        assert record["state_at_skip"] in (STATE_FLAT, STATE_STOCK_ONLY)
        assert record["week"], "a skip with no week cannot be reconciled"


def test_the_engine_enters_every_week_of_the_real_tape(real_book):
    """FR-15's acceptance: the committed tape books, and books both outcomes."""
    assert real_book.skips.empty, real_book.skips.to_dict("records")
    assert (real_book.blotter["side"] == "BUY").sum() >= 1
    outcomes = real_book.weekly["outcome"].value_counts().to_dict()
    assert outcomes == {"ASSIGN": 6, "EXPIRE": 4}, outcomes


# ==========================================================================
# The hand-checked week — FR-15's acceptance criterion
# ==========================================================================
def test_week_37_hand_checked_against_the_raw_quotes(real_book, real_tape, params):
    """2026-W37, read off ``covered_call_tape.parquet`` by hand.

    Labor Day is Monday 2026-09-07, so the week's first session is **Tuesday
    2026-09-08** (DR-7 — the calendar comes off the stock tape, never from a
    weekday). Its closing bar starts 15:00 ET.

    Raw bars, from the tape::

        QQQ.O                2026-09-08 15:00   trdprc_1 = 718.41
        QQQI112671900.U^I26  2026-09-08 15:00   bid = 4.77   ask = 4.83
        QQQ.O                2026-09-11 15:00   trdprc_1 = 714.78

    By hand: spot 718.41; the chain lists every $1 strike through the band, so the
    smallest listed strike at or above 718.41 is **719**. Its quote is valid
    (both sides present and positive, ask >= bid), so mid = (4.77 + 4.83) / 2 =
    **4.80**. Flat at the start of the week, so both legs fire::

        BUY  100 QQQ.O               @ 718.41  ->  cash -71,841.00
        SELL   1 QQQI112671900.U^I26 @   4.80  ->  cash +   480.00

    At expiry 714.78 <= 719, so the call finishes out of the money and **EXPIRE**s
    (SD-6 would only assign strictly above 719). No cash moves, the shares stay.

    This is the same entry T-80's live rehearsal booked through the *other* code
    path, on a different day, against LSEG rather than a parquet file — which is
    what makes it a check rather than a restatement.
    """
    entry_ts = pd.Timestamp("2026-09-08 15:00", tz=params.tz)
    expiry_ts = pd.Timestamp("2026-09-11 15:00", tz=params.tz)
    call = "QQQI112671900.U^I26"

    quote = _bar_row(real_tape, call, entry_ts)
    assert (quote["bid"], quote["ask"]) == (4.77, 4.83)
    assert _stock_print_at(real_tape, entry_ts) == 718.41
    assert _stock_print_at(real_tape, expiry_ts) == 714.78
    assert valid_mid(quote["bid"], quote["ask"]) == 4.80

    rows = real_book.blotter[real_book.blotter["time"].isin(
        ["2026-09-08 15:00", "2026-09-11 15:00"]
    )]
    booked = [(r["side"], r["instrument"], r["qty"], r["fill"], r["cash_delta"])
              for r in rows.to_dict("records")]
    assert booked == [
        ("BUY", "QQQ.O", 100, 718.41, -71_841.00),
        ("SELL", call, 1, 4.80, 480.00),
        ("EXPIRE", call, 1, 0.0, 0.0),
    ]


def test_a_settlement_print_exactly_on_the_strike_expires_rather_than_assigning(
    synthetic_tape, params
):
    """SD-6, strict — ``S_exp == K`` is out of the money, and never happens naturally.

    Neither tape ever prints a close exactly on a listed strike, so the whole
    ``itm_rule`` decision is untested by both books: a mutation run swapped
    ``is_itm`` for ``settle >= strike`` and the entire suite stayed green. The case
    has to be built. OCC auto-exercise triggers a **cent** in the money, so a call
    finishing exactly at the strike expires worthless and the shares stay.
    """
    book = run_backtest(synthetic_tape, params)
    assigned = book.blotter[book.blotter["side"] == "ASSIGN"].iloc[0]
    strike = parse_option_ric(assigned["instrument"])["strike"]
    stock_ric = synthetic_tape.stock["ric"].iloc[0]
    closing = pd.Timestamp(f"{assigned['time']}", tz=params.tz)

    bars = synthetic_tape.bars.copy()
    on_the_strike = (bars["ric"] == stock_ric) & (bars["ts"] == closing)
    assert on_the_strike.any()
    bars.loc[on_the_strike, "trdprc_1"] = strike
    pinned = run_backtest(Tape(bars=bars, meta=dict(synthetic_tape.meta)), params)

    resolution = pinned.blotter[
        (pinned.blotter["instrument"] == assigned["instrument"])
        & (pinned.blotter["side"].isin(("EXPIRE", "ASSIGN")))
    ]
    assert list(resolution["side"]) == ["EXPIRE"], "a call at the strike was assigned"
    sold = pinned.blotter[(pinned.blotter["time"] == assigned["time"])
                          & (pinned.blotter["instrument"] == params.underlying)]
    assert sold.empty, "the shares left the book on an out-of-the-money expiry"


def test_the_thursday_expiry_of_a_friday_holiday_week_settles_on_the_thursday(
    params, fixture_end_date
):
    """DR-7 at the *exit* — the expiry session is the week's last, holiday or not.

    Seed 7's ``friday_holiday`` week happens to draw the generator's 8% unquoted
    hole on its chosen strike at the entry bar, so it skips before it can settle;
    seed 2's books. Asking for a seed by number is worth it here because the
    alternative — hunting the weeks for one that expires on a Thursday — is how a
    fixture change quietly stops testing what the test claims (T-63's rule).
    """
    tape = synthesize_tape(fixture_end_date, seed=2)
    book = run_backtest(tape, params)
    thursday = book.weekly[book.weekly["expiry_day"] == dt.date(2026, 8, 13)]
    assert len(thursday) == 1 and thursday.iloc[0]["outcome"] in ("EXPIRE", "ASSIGN")

    exit_rows = book.blotter[book.blotter["time"].str.startswith("2026-08-13")]
    assert len(exit_rows), "the Thursday expiry booked no exit"
    assert all(t.endswith(f"{CLOSING_BAR_HOUR_ET:02d}:00") for t in exit_rows["time"])
    ric = exit_rows.iloc[0]["instrument"]
    assert parse_option_ric(ric)["expiry"] == dt.date(2026, 8, 13), (
        "the contract's own RIC must carry the Thursday the exchange listed"
    )


# ==========================================================================
# I-1 … I-12 — SPEC §12
# ==========================================================================
def test_i1_cash_reconciles_against_the_blotter_alone(book):
    """I-1 — every ledger bar's cash is ``start_cash`` plus the rows at or before it.

    Recomputed from the blotter's rendered ``time`` and ``cash_delta`` columns, so
    the ledger is checked against the artifact a reader can check it against too.
    """
    times = _blotter_times(book)
    deltas = book.blotter["cash_delta"].astype(float).to_numpy()
    for ts, cash in zip(book.ledger["ts"], book.ledger["cash"]):
        expected = book.params.start_cash + deltas[times <= ts].sum()
        assert cash == pytest.approx(expected, abs=0.005), f"cash disagrees at {ts}"
    assert book.final_cash == pytest.approx(
        book.params.start_cash + deltas.sum(), abs=0.005
    )


def test_every_dollar_on_the_blotter_is_held_to_money_dp(book):
    """The blotter may not disagree with itself (SPEC §8, §1).

    ``(6.01 + 6.08) / 2`` is not 6.045 in binary, so an unrounded mid reached the
    blotter as ``6.130000000000001`` while the same row's note printed ``mid=6.13``.
    It also reached ``blotter_csv()`` — the artifact I-12 hashes and the table T-59
    will render. Rounding now happens once, in ``rules.money()``.
    """
    for row in book.blotter.to_dict("records"):
        for column in ("fill", "cash_delta", "limit"):
            value = row[column]
            if isinstance(value, str):
                continue                              # NO_LIMIT on EXPIRE / ASSIGN
            assert round(float(value), MONEY_DP) == float(value), (
                f"{row['time']} {column}={value!r} is not held to {MONEY_DP} places"
            )
        if "mid=" in row["note"]:
            quoted = float(row["note"].split("mid=")[1].split()[0])
            assert float(row["fill"]) == quoted, (
                f"{row['time']}: fill {row['fill']!r} disagrees with its own note"
            )


def test_the_blotter_has_the_briefs_columns_in_the_briefs_order(book):
    """SPEC §8 fixes the columns exactly; the page renders them in this order."""
    assert list(book.blotter.columns) == BLOTTER_COLUMNS
    assert BLOTTER_COLUMNS == ["time", "instrument", "occ", "side", "qty",
                               "limit", "fill", "cash_delta", "note"]


def test_i2_nav_is_cash_plus_lmv_plus_option_mv(book):
    """I-2 — the NAV identity, on every row, with the short call negative (DR-4)."""
    ledger = book.ledger
    identity = ledger["cash"] + ledger["lmv"] + ledger["option_mv"]
    assert np.allclose(ledger["nav"], identity, atol=0.005)
    short = ledger[ledger["short_calls"] > 0]
    assert (short["option_mv"] <= 0).all(), "a short call was carried as an asset"


def test_i3_no_fill_without_a_quote(book_and_tape):
    """I-3 — a call is only sold on a bar whose mid is valid; stock only on a print."""
    book, tape = book_and_tape
    times = _blotter_times(book)
    for ts, row in zip(times, book.blotter.to_dict("records")):
        if row["side"] == "SELL" and parse_option_ric(row["instrument"]):
            bar = _bar_row(tape, row["instrument"], ts)
            assert bar is not None, f"{row['instrument']} has no bar at {ts}"
            assert valid_mid(bar["bid"], bar["ask"]) is not None, (
                f"a call was sold at {ts} on a quote SPEC §6.1 refuses"
            )
        if row["side"] == "BUY":
            assert _stock_print_at(tape, ts) is not None, f"stock bought at {ts}, no print"


def test_i4_every_option_fill_is_inside_the_market_at_its_bar(book_and_tape):
    """I-4 — ``bid <= fill <= ask``, and under the mid rule (DR-2) exactly the mid."""
    book, tape = book_and_tape
    times = _blotter_times(book)
    for ts, row in zip(times, book.blotter.to_dict("records")):
        if row["side"] != "SELL" or not parse_option_ric(row["instrument"]):
            continue
        bar = _bar_row(tape, row["instrument"], ts)
        assert bar["bid"] <= row["fill"] <= bar["ask"]
        assert row["fill"] == pytest.approx((bar["bid"] + bar["ask"]) / 2)
        assert row["limit"] == row["fill"], "limit and fill must agree under DR-2"


def test_i5_never_naked_and_never_short_stock(book):
    """I-5 — ``shares in {0, 100}``, at most one call, and a call only when covered."""
    ledger = book.ledger
    assert set(ledger["shares"]) <= {0, book.params.shares}
    assert ledger["short_calls"].between(0, book.params.contracts).all()
    covered = ledger["short_calls"] == book.params.contracts
    assert (ledger.loc[covered, "shares"] == book.params.shares).all(), (
        "the book was short a call with no shares behind it"
    )


def test_i6_every_trade_sits_on_a_bar_of_its_instrument(book_and_tape):
    """I-6 — no fill between bars, and none at a timestamp the tape does not carry.

    ``EXPIRE`` / ``ASSIGN`` are checked against the **stock's** bars, not the
    option's: settlement needs no option quote (SPEC §7), so an ITM call with no
    bid or ask on the expiry bar is still assigned and the option may legitimately
    have no bar there.
    """
    book, tape = book_and_tape
    stock_bars = set(tape.stock_index)
    for ts, row in zip(_blotter_times(book), book.blotter.to_dict("records")):
        if row["side"] in ("EXPIRE", "ASSIGN") or not parse_option_ric(row["instrument"]):
            assert ts in stock_bars, f"{row['side']} at {ts} is not a stock bar"
        else:
            assert _bar_row(tape, row["instrument"], ts) is not None, (
                f"{row['instrument']} has no bar at {ts}"
            )


def test_i7_every_open_call_resolves_exactly_once(book_and_tape):
    """I-7 — one ``EXPIRE``, or one ``ASSIGN`` plus a stock ``SELL`` at ``K``.

    Grouped by the contract's own RIC rather than by the engine's week labels, so a
    week-labelling defect cannot hide an unresolved call.
    """
    book, tape = book_and_tape
    times = _blotter_times(book)
    options = book.blotter.assign(ts=times)
    options = options[options["instrument"].map(lambda r: parse_option_ric(r) is not None)]
    assert len(options), "no option was ever traded"

    for ric, rows in options.groupby("instrument"):
        sides = list(rows["side"])
        assert sides.count("SELL") == 1, f"{ric} was written {sides.count('SELL')} times"
        exits = [s for s in sides if s in ("EXPIRE", "ASSIGN")]
        assert len(exits) == 1, f"{ric} resolved {len(exits)} times"

        contract = parse_option_ric(ric)
        exit_row = rows[rows["side"].isin(("EXPIRE", "ASSIGN"))].iloc[0]
        expected_bar = closing_bar_ts(tape.stock_index, contract["expiry"], book.params)
        # SPEC §7's carry-forward (added by T-57) lets the resolution sit on an
        # EARLIER bar of the same session when the closing bar carries no print. The
        # invariant keeps its teeth — nothing resolves after the close, nothing off
        # the expiry session, and a substitution is never silent — without
        # contradicting the rule the same document states.
        assert exit_row["ts"].date() == contract["expiry"], (
            f"{ric} resolved on {exit_row['ts'].date()}, not its expiry session"
        )
        if expected_bar is not None:
            assert exit_row["ts"] <= expected_bar, (
                f"{ric} resolved at {exit_row['ts']}, after the session's close"
            )
        assert exit_row["ts"] == expected_bar or "S_exp_carried" in exit_row["note"], (
            f"{ric} resolved off the closing bar without saying so"
        )
        if exit_row["side"] == "ASSIGN":
            sale = book.blotter.assign(ts=times)
            sale = sale[(sale["ts"] == exit_row["ts"])
                        & (sale["instrument"] == book.params.underlying)
                        & (sale["side"] == "SELL")]
            assert len(sale) == 1 and sale.iloc[0]["fill"] == contract["strike"], (
                f"{ric} was assigned but the shares did not leave at the strike"
            )


def _as_live_form(tape: Tape) -> Tape:
    """The same tape with every option RIC in the **live** form — no caret suffix.

    SPEC §3.3: which spelling a contract answers under depends on how long ago it
    expired, so which one a tape carries depends on the date of the pull. T-77
    measured the same window answering differently two days apart. This is a legal
    tape, not a corrupted one.
    """
    bars = tape.bars.copy()
    options = bars["kind"] == "option"
    assert options.any()
    bars.loc[options, "ric"] = bars.loc[options, "ric"].str.split("^").str[0]
    assert not bars.loc[options, "ric"].str.contains(r"\^").any()
    return Tape(bars=bars, meta=dict(tape.meta))


def test_the_book_is_identical_on_a_live_form_tape(book_and_tape):
    """The contract is a ``(expiry, strike)``, not a string — SPEC §3.3.

    The engine used to *rebuild* the RIC with `build_option_ric(..., expired=True)`,
    which hard-codes the caret form. On a tape pulled within a few days of expiry —
    which T-77 says is a matter of the pull date, not of correctness — that named a
    contract with no bars on the tape, and every per-bar call mark then missed and
    carried forward silently. The blotter half went red (I-3/I-4/I-6) but the
    **ledger** half had no invariant at all, and the ledger is what the NAV chart
    draws: 624 of 624 covered bars frozen, NAV wrong on 614 of 784 by up to $2,201.

    So the guard is a whole second book, compared against the first. Both are
    produced by the engine, but from tapes that differ *only* in a spelling the
    strategy has no opinion about — so any difference between them is a defect.
    """
    book, tape = book_and_tape
    live = _as_live_form(tape)
    other = run_backtest(live, book.params)

    # Against THIS tape's spellings only. Checking the union of both tapes would
    # accept a rebuilt caret RIC — the very defect — and a first draft of this guard
    # did exactly that and let the mutation through.
    on_tape = set(live.bars["ric"])
    for instrument in other.blotter["instrument"]:
        assert instrument in on_tape, (
            f"the blotter names {instrument}, which is absent from the tape it ran on"
        )

    assert other.final_nav == book.final_nav
    assert list(other.ledger["nav"]) == list(book.ledger["nav"])
    assert list(other.ledger["call_mark"].fillna(-1)) == list(
        book.ledger["call_mark"].fillna(-1)
    )
    assert other.ledger["mark_carried"].sum() == book.ledger["mark_carried"].sum()


def test_a_short_call_is_marked_at_the_tapes_own_quote_for_that_contract(book_and_tape):
    """S-7, checked against the tape rather than against the engine's own key.

    The pre-existing carry-forward guard looked the mark up by ``row["call_ric"]`` —
    the very string the ledger had used — so it passed with every mark frozen. T-46's
    rule, violated inside a guard written to enforce S-7. This one addresses the bar
    by ``(expiry, strike, ts)``, which the engine's output cannot influence.
    """
    book, tape = book_and_tape
    options = tape.options
    quotes = {
        (e, float(k), ts): valid_mid(b, a)
        for e, k, ts, b, a in zip(options["expiry"], options["strike"],
                                  options["ts"], options["bid"], options["ask"])
        if k is not None and not pd.isna(k)
    }
    short = book.ledger[(book.ledger["short_calls"] > 0) & (~book.ledger["mark_carried"])]
    assert len(short) > 10, "too few fresh marks to be testing anything"
    for row in short.to_dict("records"):
        key = (row["call_expiry"], float(row["call_strike"]), row["ts"])
        assert key in quotes, f"{key} is not a quoted bar of that contract"
        assert row["call_mark"] == pytest.approx(quotes[key])


def test_i8_assignment_follows_the_settlement_print_under_sd6(book_and_tape):
    """I-8 — ``ASSIGN`` iff ``S_exp > K``; equality expires (SD-6, strict)."""
    book, tape = book_and_tape
    for ts, row in zip(_blotter_times(book), book.blotter.to_dict("records")):
        if row["side"] not in ("EXPIRE", "ASSIGN"):
            continue
        strike = parse_option_ric(row["instrument"])["strike"]
        settle = _stock_print_at(tape, ts)
        assert settle is not None, f"settled at {ts} with no stock print there"
        assert is_itm(settle, strike, book.params) is (row["side"] == "ASSIGN"), (
            f"{row['side']} at {ts}: S_exp={settle} K={strike}"
        )


def test_i9_the_rule_chose_the_strike_it_says_it_chose(book_and_tape):
    """I-9 — re-run ``select_strike`` on the bar's own chain, and no strike in ``[S, K)``.

    The chain is rebuilt from the tape here rather than taken from the engine: the
    defect this catches is the engine narrowing the chain (to quoted strikes, say)
    before selecting, which would silently make the rule "nearest OTM *that was
    quoted*" — a different strategy that still passes a same-source check.
    """
    book, tape = book_and_tape
    for ts, row in zip(_blotter_times(book), book.blotter.to_dict("records")):
        if row["side"] != "SELL" or not parse_option_ric(row["instrument"]):
            continue
        contract = parse_option_ric(row["instrument"])
        spot = _stock_print_at(tape, ts)
        chain = tape.strikes_for(contract["expiry"])
        assert select_strike(chain, spot, book.params) == contract["strike"]
        assert not [k for k in chain if spot <= k < contract["strike"]]
        assert contract["strike"] >= spot, "the rule wrote an in-the-money call"


def test_i10_every_week_without_an_entry_is_in_the_skip_log_with_a_real_reason(book_and_tape):
    """I-10 — no week is silent, no week is in both tables, every reason is supported."""
    book, tape = book_and_tape
    weeks = window_weeks(tape, book.params)
    entered = set(book.weekly[book.weekly["outcome"].isin(("EXPIRE", "ASSIGN"))]["week"])
    skipped = set(book.skips["week"])

    assert entered.isdisjoint(skipped), f"a week both traded and skipped: {entered & skipped}"
    assert entered | skipped == {w.label for w in weeks}, "a week vanished"
    assert set(book.skips["reason"]) <= SKIP_REASONS

    by_label = {w.label: w for w in weeks}
    for record in book.skips.to_dict("records"):
        week = by_label[record["week"]]
        bar = entry_bar_ts(tape.stock_index, week.entry_day, book.params)
        spot = None if bar is None else _stock_print_at(tape, bar)
        if record["reason"] == SKIP_SHORT_WEEK:
            assert week.is_short
        elif record["reason"] == SKIP_NO_STOCK_PRINT:
            assert spot is None, f"{week.label} had a print at {bar}"
        elif record["reason"] == SKIP_NO_STRIKE:
            assert select_strike(tape.strikes_for(week.expiry_day), spot,
                                 book.params) is None
        else:                                              # SKIP_NO_QUOTE
            strike = select_strike(tape.strikes_for(week.expiry_day), spot, book.params)
            assert strike is not None
            quoted = tape.options[(tape.options["expiry"] == week.expiry_day)
                                  & (tape.options["strike"] == strike)
                                  & (tape.options["ts"] == bar)]
            assert quoted.empty or pd.isna(quoted["mid"].iloc[0]), (
                f"{week.label} skipped for want of a quote that the tape carries"
            )


def test_reg_t_rates_are_the_brief_s_numbers():
    """DR-4's percentages, pinned as literals.

    I-11 below multiplies by these constants, so on its own it would pass against
    *any* rate the module happened to hold — a check reading back its own effect
    (T-46's headline). A mutation run proved it: IM at 60% survived the whole suite.
    """
    assert (IM_RATE, MM_RATE) == (0.50, 0.25)


def test_i11_reg_t_arithmetic_and_the_flat_rows(book):
    """I-11 — IM 50%, MM 25%, available and excess; all zero when flat (DR-4).

    The rates are written out here rather than imported, for the reason the test
    above gives.
    """
    ledger = book.ledger
    assert np.allclose(ledger["im"], 0.50 * ledger["lmv"], atol=0.005)
    assert np.allclose(ledger["mm"], 0.25 * ledger["lmv"], atol=0.005)
    assert np.allclose(ledger["available"], ledger["nav"] - ledger["im"], atol=0.005)
    assert np.allclose(ledger["excess"], ledger["nav"] - ledger["mm"], atol=0.005)

    flat = ledger[ledger["shares"] == 0]
    assert (flat[["lmv", "im", "mm"]] == 0).all().all()
    assert np.allclose(flat["nav"], flat["cash"], atol=0.005)


def test_i12_the_same_tape_and_params_give_a_byte_identical_blotter(book_and_tape):
    """I-12 — determinism, compared as bytes rather than as frames."""
    book, tape = book_and_tape
    again = run_backtest(tape, book.params)
    assert again.blotter_csv() == book.blotter_csv()
    pd.testing.assert_frame_equal(again.ledger, book.ledger)
    pd.testing.assert_frame_equal(again.skips, book.skips)


def test_the_covered_call_adds_nothing_to_margin(book):
    """DR-4 — Reg T, not portfolio margin: the short call's own IM and MM are $0.

    Checked by comparing a covered bar against a stock-only bar at the same LMV, so
    the claim is about the *call* rather than about the arithmetic I-11 already pins.
    The docstring used to describe that comparison without making it.
    """
    ledger = book.ledger
    covered = ledger[(ledger["short_calls"] == 1) & (ledger["lmv"] > 0)]
    uncovered = ledger[(ledger["short_calls"] == 0) & (ledger["lmv"] > 0)]
    assert len(covered), "the book is never covered"
    assert len(uncovered), "the book is never long stock without a call"

    def margin_per_dollar(rows):
        # Rounded to 6 places, not compared exactly: `im` and `mm` are held to
        # MONEY_DP in dollars, so their ratio to a ~$72,000 LMV carries a few
        # billionths of noise that says nothing about the rule.
        return sorted({(round(im / lmv, 6), round(mm / lmv, 6))
                       for im, mm, lmv in zip(rows["im"], rows["mm"], rows["lmv"])})

    assert margin_per_dollar(covered) == margin_per_dollar(uncovered) == [(0.5, 0.25)], (
        "the short call moved the margin requirement — Reg T says it adds $0 (DR-4)"
    )


# ==========================================================================
# The ledger's marks — SPEC §9, S-7
# ==========================================================================
def test_marks_are_carried_forward_and_flagged_never_interpolated(book_and_tape):
    """S-7 — a bar with no print wears the previous bar's mark, and says it does."""
    book, tape = book_and_tape
    ledger = book.ledger
    carried = ledger[ledger["mark_carried"]]
    assert len(carried), "no bar on this tape is missing a mark — check the fixture"
    for row in carried.to_dict("records"):
        fresh_stock = _stock_print_at(tape, row["ts"])
        fresh_call = None
        if row["short_calls"]:
            bar = _bar_row(tape, row["call_ric"], row["ts"])
            fresh_call = None if bar is None else valid_mid(bar["bid"], bar["ask"])
        assert fresh_stock is None or (row["short_calls"] and fresh_call is None), (
            f"{row['ts']} is flagged as carried but both marks are on the tape"
        )


def test_a_mark_is_never_a_number_the_tape_does_not_carry(book_and_tape):
    """The other half of S-7: a *fresh* mark equals the bar's own print / mid."""
    book, tape = book_and_tape
    fresh = book.ledger[~book.ledger["mark_carried"]]
    for row in fresh.to_dict("records"):
        printed = _stock_print_at(tape, row["ts"])
        if printed is not None and not pd.isna(row["stock_mark"]):
            assert row["stock_mark"] == pytest.approx(printed)


def test_the_ledger_row_at_an_entry_bar_already_contains_the_trade(book):
    """The ordering the module docstring warns about, pinned.

    ``cash`` counts every row at or **before** the bar, so an entry bar's row shows
    the position on, not the position about to go on. A reader checking NAV by hand
    against the chart depends on knowing which.
    """
    entries = book.ledger[book.ledger["entry"]]
    assert len(entries), "the book never entered"
    assert (entries["shares"] == book.params.shares).all()
    assert (entries["short_calls"] == book.params.contracts).all()


def test_the_daily_roll_up_is_a_selection_of_hourly_rows_not_a_re_aggregation(book):
    """SPEC §9 — so a number in the table is a number in the chart."""
    daily = book.daily_ledger()
    hours = pd.DatetimeIndex(daily["ts"]).hour
    assert (hours <= CLOSING_BAR_HOUR_ET).all(), "a post-close stub reached the roll-up"
    assert len(daily) == len(set(pd.DatetimeIndex(daily["ts"]).date))
    merged = daily.merge(book.ledger, on="ts", suffixes=("", "_full"))
    assert (merged["nav"] == merged["nav_full"]).all()


def test_the_daily_roll_up_loses_no_session(book):
    """Every session gets a row, including one with no 15:00 ET bar.

    Selecting on ``hour == 15`` made a half session vanish from the table entirely —
    no row and no note — and `final_nav` then quoted the *previous* session's close
    as the window's. The synthetic tape has such a day (2026-08-24), so this guard
    fails the moment the fallback is removed.
    """
    sessions = set(pd.DatetimeIndex(book.ledger["ts"]).date)
    rolled = set(pd.DatetimeIndex(book.daily_ledger()["ts"]).date)
    assert rolled == sessions, f"the roll-up dropped {sorted(sessions - rolled)}"


def test_the_headline_nav_comes_off_the_close_not_the_post_close_stub(real_book):
    """T-62's trap one layer up — ``ledger.iloc[-1]`` is a 19:00 ET bar.

    The stock tape runs past the equity close, so the last *row* of the ledger is a
    thin post-close bar. ``final_nav`` reads the last 15:00 row instead; on the
    committed tape the two differ, which is what makes this a check.
    """
    last_row_nav = float(real_book.ledger["nav"].iloc[-1])
    closing_nav = float(real_book.daily_ledger()["nav"].iloc[-1])
    assert real_book.final_nav == closing_nav
    assert real_book.final_nav != last_row_nav, (
        "the stub and the close happen to agree — this test proves nothing today"
    )


def test_total_return_is_nav_over_starting_cash_and_matches_the_documents(real_book):
    """The one number three graded documents quote, pinned where the engine can see it.

    ``total_return`` had no test at all: swapping ``final_nav`` for ``final_cash`` in
    its definition — which changes +1.66% to -93.6% — left the whole suite green,
    while PRD §16, BACKLOG-2's T-57 row and CLAUDE.md all print the figure. A number
    that reaches a document has to be pinned somewhere a change to the engine trips.
    """
    assert real_book.total_return == pytest.approx(
        real_book.final_nav / real_book.params.start_cash - 1.0
    )
    assert real_book.params.start_cash == 75_000.0                  # SD-3
    assert real_book.final_nav == pytest.approx(76_243.50, abs=0.005)
    assert round(real_book.total_return * 100, 2) == 1.66
    premium = real_book.blotter[
        (real_book.blotter["side"] == "SELL") & (real_book.blotter["occ"] != "")
    ]["cash_delta"].sum()
    assert premium == pytest.approx(6_657.50, abs=0.005)


# ==========================================================================
# Settlement's one asymmetry — SPEC §7, and the carry-forward it needs
# ==========================================================================
def _tape_without(tape: Tape, ric: str, stamps) -> Tape:
    """A copy of ``tape`` with ``trdprc_1`` blanked on the given bars."""
    bars = tape.bars.copy()
    mask = (bars["ric"] == ric) & bars["ts"].isin(stamps)
    assert mask.any(), "the bars this test edits are not on the tape"
    bars.loc[mask, "trdprc_1"] = np.nan
    return Tape(bars=bars, meta=dict(tape.meta))


def test_a_missing_settlement_print_falls_back_inside_the_session_and_says_so(
    synthetic_tape, params
):
    """I-7 cannot be satisfied by skipping — the call is already short.

    Entry may skip, because nothing is owed yet; settlement may not, because a call
    left open is a position the book carries forever. So the settlement print falls
    back to the last print in that session at or **before** the close (S-7), and
    the blotter row itself records the substitution — a reader checking the week
    looks the closing bar up, and would otherwise find a number that is not there.
    """
    book = run_backtest(synthetic_tape, params)
    resolved = book.blotter[book.blotter["side"].isin(("EXPIRE", "ASSIGN"))].iloc[0]
    expiry_day = dt.date.fromisoformat(resolved["time"].split()[0])
    stock_ric = synthetic_tape.stock["ric"].iloc[0]
    closing = pd.Timestamp(f"{expiry_day} {CLOSING_BAR_HOUR_ET}:00", tz=params.tz)

    damaged = _tape_without(synthetic_tape, stock_ric, [closing])
    after = run_backtest(damaged, params)
    # Looked up by the contract, not by the timestamp: the row has MOVED to the bar
    # the print came from, which is the whole visible effect of the fallback.
    resolutions = after.blotter[
        (after.blotter["instrument"] == resolved["instrument"])
        & (after.blotter["side"].isin(("EXPIRE", "ASSIGN")))
    ]
    assert len(resolutions) == 1, "the call was left open, or resolved twice"
    row = resolutions.iloc[0]
    assert "S_exp_carried" in row["note"], "the substitution was silent"
    assert row["time"] != resolved["time"], "the row did not move to the bar it read"

    earlier = [ts for ts in damaged.stock_index
               if ts.date() == expiry_day and ts.hour < CLOSING_BAR_HOUR_ET
               and _stock_print_at(damaged, ts) is not None]
    expected = _stock_print_at(damaged, max(earlier))
    assert float(row["note"].split("S_exp=")[1].split()[0]) == pytest.approx(expected)
    assert row["time"] == f"{max(earlier):%Y-%m-%d %H:%M}"


def test_settlement_never_reaches_past_the_close_for_a_print(synthetic_tape, params):
    """The fallback searches *backwards* from the close, never forwards.

    Reaching forward would resolve a contract against a post-close stub, which is
    the ``max(ts)`` defect T-62 measured wearing a different hat.
    """
    stock_ric = synthetic_tape.stock["ric"].iloc[0]
    day = dt.date(2026, 9, 11)
    session = [ts for ts in synthetic_tape.stock_index if ts.date() == day]
    before_close = [ts for ts in session if ts.hour <= CLOSING_BAR_HOUR_ET]
    stock_by_ts = {ts: r for ts, r in zip(synthetic_tape.stock["ts"],
                                          synthetic_tape.stock.to_dict("records"))}
    closing = pd.Timestamp(f"{day} {CLOSING_BAR_HOUR_ET}:00", tz=params.tz)

    blanked = _tape_without(synthetic_tape, stock_ric, before_close)
    blanked_by_ts = {ts: r for ts, r in zip(blanked.stock["ts"],
                                            blanked.stock.to_dict("records"))}
    price, bar = settlement_print(blanked_by_ts, session, closing)
    assert (price, bar) == (None, None), (
        "settlement found a print after the close — that is the post-close stub"
    )
    price, bar = settlement_print(stock_by_ts, session, closing)
    assert bar == closing


def test_a_session_with_no_print_at_all_raises_rather_than_leaving_the_call_open(
    synthetic_tape, params
):
    """A tape that cannot resolve an open call is broken, and stopping says so."""
    book = run_backtest(synthetic_tape, params)
    resolved = book.blotter[book.blotter["side"].isin(("EXPIRE", "ASSIGN"))].iloc[0]
    expiry_day = dt.date.fromisoformat(resolved["time"].split()[0])
    stock_ric = synthetic_tape.stock["ric"].iloc[0]
    session = [ts for ts in synthetic_tape.stock_index if ts.date() == expiry_day]

    damaged = _tape_without(synthetic_tape, stock_ric, session)
    with pytest.raises(ValueError, match="cannot be resolved"):
        run_backtest(damaged, params)


# ==========================================================================
# FR-16 — the flag the brief asks for in words
# ==========================================================================
def test_an_entry_the_account_could_not_have_carried_is_booked_and_flagged(
    synthetic_tape,
):
    """FR-16 — the brief's *"you could not have put the trade on — say so"*.

    The backtest reports what the rule did, so the trade is still booked; the ledger
    row wears ``NEG_AVAILABLE`` beside it. Forced here by funding the account at a
    fraction of one round lot, because under SD-3's $75,000 it never fires — and a
    flag no test has ever seen fire is a flag nobody knows works.
    """
    poor = Params(start=dt.date(2026, 7, 6), end=dt.date(2026, 9, 11), start_cash=1_000.0)
    book = run_backtest(synthetic_tape, poor)
    entries = book.ledger[book.ledger["entry"]]
    assert len(entries), "nothing was entered"
    assert (entries["available"] < 0).all()
    assert (entries["flag"] == FLAG_NEG_AVAILABLE).all()
    assert (book.blotter["side"] == "BUY").sum() >= 1, "the trade was not booked"


def test_the_flag_never_fires_under_the_pos_funding_decision(book):
    """SD-3 measured: $75,000 sits above the peak entry cost, so the book is solvent."""
    assert (book.ledger["flag"] == "").all()
    assert (book.ledger["available"] >= 0).all()


def test_the_flag_only_marks_entry_bars(synthetic_tape):
    """SPEC §9 — ``available < 0`` matters at the moment risk goes on, not later."""
    poor = Params(start=dt.date(2026, 7, 6), end=dt.date(2026, 9, 11), start_cash=1_000.0)
    ledger = run_backtest(synthetic_tape, poor).ledger
    flagged = ledger[ledger["flag"] == FLAG_NEG_AVAILABLE]
    assert flagged["entry"].all()


# ==========================================================================
# The weekly projection — it must hold no number of its own
# ==========================================================================
def test_the_weekly_table_repeats_the_blotter_rather_than_restating_it(book):
    """SPEC §1 — no figure carries a number the blotter cannot reproduce."""
    traded = book.weekly[book.weekly["outcome"].isin(("EXPIRE", "ASSIGN"))]
    calls = book.blotter[(book.blotter["side"] == "SELL") & (book.blotter["occ"] != "")]
    assert len(traded) == len(calls)
    assert list(traded["mid"]) == [float(f) for f in calls["fill"]]
    assert list(traded["premium"]) == [float(c) for c in calls["cash_delta"]]
    for strike, ric in zip(traded["strike"], calls["instrument"]):
        assert strike == parse_option_ric(ric)["strike"]


def test_the_weekly_tables_other_columns_come_from_the_tape_and_the_blotter(book_and_tape):
    """``spot``, ``settle``, ``state_at_entry`` and ``detail``, each against a second source.

    Those four were unguarded: pinning ``state_at_entry`` to the constant ``FLAT``
    mislabels 3 of the real book's 10 weeks, and blanking ``detail`` loses the exit's
    rule id — and the whole covered-call suite stayed green through both. ``mid`` and
    ``premium`` above are read off the same blotter row they are compared to, which is
    a same-source check; these are not.
    """
    book, tape = book_and_tape
    times = _blotter_times(book)
    blotter = book.blotter.assign(ts=times)
    traded = book.weekly[book.weekly["outcome"].isin(("EXPIRE", "ASSIGN"))]
    assert len(traded), "nothing traded"

    for record in traded.to_dict("records"):
        entry = blotter[(blotter["side"] == "SELL") & (blotter["occ"] != "")
                        & (blotter["ts"].dt.date == record["entry_day"])].iloc[0]
        exit_row = blotter[blotter["side"].isin(("EXPIRE", "ASSIGN"))
                           & (blotter["ts"].dt.date == record["expiry_day"])].iloc[0]
        assert record["spot"] == pytest.approx(_stock_print_at(tape, entry["ts"]))
        assert record["settle"] == pytest.approx(_stock_print_at(tape, exit_row["ts"]))
        assert record["detail"] == exit_row["note"] and record["detail"].strip()

        bought = not blotter[(blotter["side"] == "BUY")
                             & (blotter["ts"] == entry["ts"])].empty
        assert record["state_at_entry"] == (STATE_FLAT if bought else STATE_STOCK_ONLY)

    if not book.synthetic:
        assert set(traded["state_at_entry"]) == {STATE_FLAT, STATE_STOCK_ONLY}, (
            "the column is constant on the real book — a pinned value would pass"
        )


def test_the_weekly_table_has_one_row_per_week_the_engine_considered(book_and_tape):
    book, tape = book_and_tape
    assert list(book.weekly["week"]) == [w.label for w in window_weeks(tape, book.params)]
    assert book.diagnostics["weeks_considered"] == len(book.weekly)
    assert book.diagnostics["weeks_entered"] + book.diagnostics["weeks_skipped"] == len(
        book.weekly
    )


def test_the_book_says_whether_its_tape_was_generated(synthetic_book, real_book):
    """SPEC §11's CI guard reads this, so it may not be guessed."""
    assert synthetic_book.synthetic is True
    assert real_book.synthetic is False


# ==========================================================================
# Purity — AD-12 / NFR-5
# ==========================================================================
def _engine_code_without_docstrings() -> str:
    """``engine.py``'s executable text — no comments, no docstrings.

    The first version of this guard grepped the raw file, and the module docstring's
    own sentence *"no network, no clock, no plotly"* tripped every banned word in
    it. A guard that a description of the rule can break is a guard that will be
    deleted the next time someone edits prose.
    """
    import ast

    from options_surface_lab.covered_call import engine

    tree = ast.parse(pathlib.Path(engine.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        head = body[0]
        if (isinstance(head, ast.Expr) and isinstance(head.value, ast.Constant)
                and isinstance(head.value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


def test_the_engine_holds_no_network_no_clock_and_no_presentation():
    """AD-12's layering, as a grep over the module's executable source.

    ``engine.py`` sits in the transform core: it may import ``rules`` and the RIC
    grammar and nothing that reaches outward. The clock is banned for OQ-6's reason
    — a backtest that reads ``today()`` reports on the calendar — and ``max(ts)``
    for T-62's, which ``rules`` owns the only exception to.
    """
    code = _engine_code_without_docstrings()
    for banned in ("lseg", "requests", "plotly", "theme", "read_parquet", "open(",
                   "date.today", "datetime.now", "Timestamp.now", "Timestamp.today",
                   "utcnow", "time.time"):
        assert banned not in code, f"engine.py reaches for {banned!r}"
    assert "from .rules import" in code


def test_no_bar_in_the_engine_is_chosen_with_max_or_min():
    """T-62's rule, checked structurally instead of by a string that cannot match.

    The ban list used to carry the literal ``"max(ts)"`` — which no real code ever
    spells, so it could never fire. What the rule actually forbids is picking a bar
    out of a collection of bars by extremum; ``rules.entry_bar_ts`` /
    ``closing_bar_ts`` are the only functions allowed to decide which bar is which.
    ``max(stock_mark - K, 0)`` is arithmetic on prices and stays legal.
    """
    import ast

    from options_surface_lab.covered_call import engine

    tree = ast.parse(pathlib.Path(engine.__file__).read_text(encoding="utf-8"))
    bar_collections = {"stock_index", "bars", "bars_by_day", "session_bars",
                       "stamps", "ordered", "ts", "index"}
    offenders = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id not in ("max", "min"):
            continue
        for arg in node.args:
            names = {n.id for n in ast.walk(arg) if isinstance(n, ast.Name)}
            if names & bar_collections:
                offenders.append((node.lineno, ast.unparse(node)[:70]))
    assert not offenders, (
        f"a bar is chosen by extremum, not by the calendar helpers: {offenders}"
    )


def test_the_engine_imports_the_acquisition_modules_only_for_type_checking():
    """AD-12, signed 2026-09-14: ``engine.py`` never imports the module holding the
    network. ``Tape`` is a parameter, so the import it needs is a type-checking one.

    Checked structurally rather than by grep: the import must sit inside the
    ``if TYPE_CHECKING:`` block, which is the difference between a name the type
    checker sees and a module the interpreter loads.
    """
    import ast

    from options_surface_lab.covered_call import engine

    tree = ast.parse(pathlib.Path(engine.__file__).read_text(encoding="utf-8"))
    guarded, runtime = set(), set()
    for node in tree.body:
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Name)
                and node.test.id == "TYPE_CHECKING"):
            targets = guarded
            children = node.body
        else:
            targets = runtime
            children = [node]
        for child in ast.walk(ast.Module(body=children, type_ignores=[])):
            if isinstance(child, ast.ImportFrom):
                targets.add(child.module or "")
            elif isinstance(child, ast.Import):
                targets.update(alias.name for alias in child.names)

    assert ".tape" not in runtime and "tape" not in runtime
    assert ".live" not in runtime and "live" not in runtime
    assert "tape" in {m.lstrip(".") for m in guarded}


def test_the_engine_reads_nothing_but_the_tape_it_is_given(synthetic_tape, params):
    """NFR-4 — no file, no cache, no committed parquet behind the caller's back."""
    import options_surface_lab.covered_call.tape as tape_module

    seen = []
    originals = (tape_module.load_tape, pd.read_parquet)
    tape_module.load_tape = lambda *a, **k: seen.append("load_tape")
    pd.read_parquet = lambda *a, **k: seen.append("read_parquet")
    try:
        run_backtest(synthetic_tape, params)
    finally:
        tape_module.load_tape, pd.read_parquet = originals
    assert not seen, f"run_backtest went to disk: {seen}"


def test_build_ledger_on_an_empty_book_is_the_starting_cash(synthetic_tape, params):
    """The degenerate case renders, rather than raising on an empty frame."""
    ledger = build_ledger(synthetic_tape, params, [], {})
    assert len(ledger), "the window has bars even when nothing traded"
    assert (ledger["cash"] == params.start_cash).all()
    assert (ledger["nav"] == params.start_cash).all()
    assert (ledger[["lmv", "im", "mm", "option_mv"]] == 0).all().all()
