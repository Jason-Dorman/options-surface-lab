"""T-65 — the strategy rules (SPEC-COVERED-CALL §2, §3.2, §5, §7).

The two tests that carry the most weight here are
:func:`test_i9_no_listed_strike_lies_between_spot_and_the_chosen_strike` (the I-9
property) and the closing-bar group, which pins the trap T-62 found: both tapes
run past the 16:00 ET close, so ``max(ts)`` of a session is a post-close stub.
"""
from __future__ import annotations

import datetime as dt
import random

import pandas as pd
import pytest

from options_surface_lab.covered_call.rules import (
    CLOSING_BAR_HOUR_ET,
    OPENING_BAR_HOUR_ET,
    Params,
    Week,
    closing_bar_ts,
    entry_bar_ts,
    is_itm,
    select_strike,
    trading_weeks,
)

ET = "America/New_York"


def _hourly_index(days, hours_et):
    """Bars at the given ET hours on the given days, built the way the tape is: UTC -> ET."""
    stamps = [
        pd.Timestamp(dt.datetime.combine(day, dt.time(hour)), tz=ET)
        for day in days
        for hour in hours_et
    ]
    return pd.DatetimeIndex(sorted(stamps))


# --------------------------------------------------------------------------
# Params — SPEC §2, and the SD-x decisions it encodes
# --------------------------------------------------------------------------
def test_defaults_are_the_decisions_the_po_made():
    p = Params()
    assert p.underlying == "QQQ.O" and p.root == "QQQ"          # SD-1
    assert (p.start, p.end) == (dt.date(2026, 7, 6), dt.date(2026, 9, 11))  # SD-2
    assert p.start_cash == 75_000.0                              # SD-3
    assert p.entry_bar == "last"                                 # SD-4
    assert p.strike_rule == "nearest_otm"                        # SD-5
    assert p.itm_rule == "strict"                                # SD-6
    assert (p.shares, p.contracts) == (100, 1)                   # S-1
    assert p.interval == "hourly"                                # DR-6


def test_sd4_last_means_the_1500_et_bar_not_the_last_bar():
    assert Params(entry_bar="last").entry_bar_hour_et == CLOSING_BAR_HOUR_ET == 15
    assert Params(entry_bar="first").entry_bar_hour_et == OPENING_BAR_HOUR_ET == 9


def test_params_is_frozen_so_a_run_cannot_rewrite_its_own_strategy():
    p = Params()
    with pytest.raises(Exception):
        p.start_cash = 1.0  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs, fragment",
    [
        ({"entry_bar": "middle"}, "entry_bar"),
        ({"strike_rule": "coin_flip"}, "strike_rule"),
        ({"itm_rule": "inclusive"}, "itm_rule"),          # SD-6 is strict
        ({"interval": "daily"}, "interval"),              # DR-6
        ({"strike_rule": "delta"}, "delta_target"),       # delta needs a target
        ({"delta_target": 0.3}, "delta_target"),          # nearest_otm must not carry one
        ({"start": dt.date(2026, 9, 11), "end": dt.date(2026, 7, 6)}, "precede"),
        ({"shares": 0}, "positive"),
        ({"start_cash": 0.0}, "positive"),
    ],
)
def test_params_refuses_a_strategy_it_cannot_run(kwargs, fragment):
    with pytest.raises(ValueError, match=fragment):
        Params(**kwargs)


def test_the_printed_rule_and_the_params_cannot_say_different_things():
    """SPEC §5 — the page renders this sentence rather than prose of its own (FR-14)."""
    sentence = Params().describe_strike_rule()
    assert "lowest listed strike at or above" in sentence
    assert "at the money" in sentence
    delta = Params(strike_rule="delta", delta_target=0.30).describe_strike_rule()
    assert "0.30" in delta and "delta" in delta


# --------------------------------------------------------------------------
# select_strike — SPEC §5
# --------------------------------------------------------------------------
def test_nearest_otm_takes_the_first_strike_above_spot():
    p = Params()
    assert select_strike([713, 714, 715, 716], 714.88, p) == 715.0


def test_spot_exactly_on_a_strike_is_atm_and_allowed():
    """The brief: 'or ATM if spot sits on a strike'. Not the next strike up."""
    assert select_strike([713, 714, 715, 716], 715.0, Params()) == 715.0


def test_no_strike_above_spot_returns_none_rather_than_the_highest():
    assert select_strike([700, 701, 702], 715.0, Params()) is None


def test_chain_order_duplicates_and_nans_do_not_change_the_answer():
    p = Params()
    messy = [716, 714, None, 715, float("nan"), 715, 713]
    assert select_strike(messy, 714.88, p) == 715.0
    assert select_strike([], 714.88, p) is None


def test_no_spot_means_no_strike():
    p = Params()
    assert select_strike([713, 714, 715], None, p) is None
    assert select_strike([713, 714, 715], float("nan"), p) is None


def test_a_sub_penny_move_above_a_strike_walks_to_the_next_one():
    """No epsilon: an epsilon would make a strike *below* spot eligible."""
    assert select_strike([714, 715, 716], 715.0001, Params()) == 716.0


def test_delta_rule_refuses_rather_than_silently_falling_back_to_nearest_otm():
    p = Params(strike_rule="delta", delta_target=0.30)
    with pytest.raises(NotImplementedError, match="P1"):
        select_strike([713, 714, 715], 714.0, p)


def test_i9_no_listed_strike_lies_between_spot_and_the_chosen_strike():
    """I-9, as a property over a seeded random sweep — deterministic for I-12."""
    p = Params()
    rng = random.Random(20260913)
    for _ in range(2_000):
        base = rng.randrange(600, 800)
        step = rng.choice([0.5, 1.0, 5.0])
        chain = [round(base + i * step, 2) for i in range(rng.randrange(1, 25))]
        spot = round(rng.uniform(base - 10, base + 30), 4)
        k = select_strike(chain, spot, p)
        if k is None:
            assert all(c < spot for c in chain), "refused while an eligible strike was listed"
            continue
        assert k >= spot, "chose a strike below spot"
        assert not [c for c in chain if spot <= c < k], "a listed strike lies in [S, K)"


# --------------------------------------------------------------------------
# is_itm — SPEC §7, SD-6 strict
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "settle, expected",
    [(715.01, True), (715.0, False), (714.99, False), (None, None)],
)
def test_strict_itm_assigns_only_strictly_above_the_strike(settle, expected):
    assert is_itm(settle, 715.0, Params()) is expected


def test_settlement_on_the_strike_expires_rather_than_assigns():
    """Equality is OTM under SD-6. OCC auto-exercise needs a cent in the money."""
    assert is_itm(715.0, 715.0, Params()) is False


# --------------------------------------------------------------------------
# The calendar — SPEC §3.2, DR-7
# --------------------------------------------------------------------------
def test_weeks_and_expiries_are_read_off_the_tape_not_generated():
    days = [dt.date(2026, 9, d) for d in (8, 9, 10, 11)]  # Labor Day week: no Monday
    weeks = trading_weeks(_hourly_index(days, [13, 15]), Params())
    assert len(weeks) == 1
    week = weeks[0]
    assert week.entry_day == dt.date(2026, 9, 8), "a Monday holiday must move entry to Tuesday"
    assert week.expiry_day == dt.date(2026, 9, 11)
    assert week.label == "2026-W37"
    assert not week.is_short


def test_a_week_with_one_session_is_flagged_short_and_not_dropped():
    """I-10 — a week the strategy cannot trade still has to be reportable as a skip."""
    weeks = trading_weeks(_hourly_index([dt.date(2026, 7, 6)], [15]), Params())
    assert len(weeks) == 1 and weeks[0].is_short


def test_weeks_come_back_in_calendar_order():
    days = [dt.date(2026, 7, d) for d in (6, 10, 13, 17, 20)]
    weeks = trading_weeks(_hourly_index(days, [15]), Params())
    assert [w.label for w in weeks] == ["2026-W28", "2026-W29", "2026-W30"]
    assert [w.entry_day for w in weeks] == [
        dt.date(2026, 7, 6), dt.date(2026, 7, 13), dt.date(2026, 7, 20)
    ]


def test_a_naive_index_is_refused_because_it_is_almost_certainly_utc():
    """The OQ-11 guard: silently treating UTC as ET moves every bar by four hours."""
    naive = pd.DatetimeIndex([pd.Timestamp("2026-09-11 19:00:00")])
    with pytest.raises(ValueError, match="tz-naive"):
        trading_weeks(naive, Params())


# --------------------------------------------------------------------------
# The closing bar — SPEC §3.2 item 4. The T-62 trap.
# --------------------------------------------------------------------------
def _september_11_bars():
    """A real option session as T-62 measured it: 13:00..20:00 UTC = 09:00..16:00 ET."""
    return _hourly_index([dt.date(2026, 9, 11)], list(range(9, 17)))


def test_the_entry_bar_is_the_1500_et_bar_and_not_the_last_bar_of_the_session():
    index = _september_11_bars()
    chosen = entry_bar_ts(index, dt.date(2026, 9, 11), Params())
    assert chosen.hour == 15
    assert chosen != max(index), "max(ts) is the 16:00 ET post-close stub, not the close"


def test_the_stock_tape_runs_to_1900_et_so_max_is_three_hours_past_the_close():
    """The stock tape's extended session is 04:00-20:00 ET; its last bar starts 19:00."""
    index = _hourly_index([dt.date(2026, 9, 11)], list(range(4, 20)))
    assert max(index).hour == 19
    assert entry_bar_ts(index, dt.date(2026, 9, 11), Params()).hour == 15


def test_entry_bar_first_takes_the_opening_bar():
    index = _september_11_bars()
    assert entry_bar_ts(index, dt.date(2026, 9, 11), Params(entry_bar="first")).hour == 9


def test_settlement_reads_the_closing_bar_even_when_entry_is_the_open():
    """Entry follows SD-4; the exit is always the close (SPEC §7)."""
    index = _september_11_bars()
    day = dt.date(2026, 9, 11)
    for params in (Params(entry_bar="first"), Params(entry_bar="last")):
        assert closing_bar_ts(index, day, params).hour == CLOSING_BAR_HOUR_ET


def test_a_session_without_a_closing_bar_returns_none_rather_than_the_nearest_thing():
    """A half-session has no 15:00 bar. The engine reads None as a skip (AD-9)."""
    half_day = _hourly_index([dt.date(2026, 11, 27)], [9, 10, 11, 12])
    assert entry_bar_ts(half_day, dt.date(2026, 11, 27), Params()) is None
    assert closing_bar_ts(half_day, dt.date(2026, 11, 27), Params()) is None


def test_a_bar_on_another_day_is_never_borrowed():
    index = _hourly_index([dt.date(2026, 9, 10), dt.date(2026, 9, 11)], [15])
    chosen = entry_bar_ts(index, dt.date(2026, 9, 11), Params())
    assert chosen.date() == dt.date(2026, 9, 11)
    assert entry_bar_ts(index, dt.date(2026, 9, 9), Params()) is None


def test_utc_input_is_converted_before_the_hour_is_read():
    """19:00 UTC is the 15:00 ET closing bar under EDT — the conversion must happen first."""
    utc = pd.DatetimeIndex(pd.to_datetime(["2026-09-11 19:00:00"]).tz_localize("UTC"))
    chosen = entry_bar_ts(utc, dt.date(2026, 9, 11), Params())
    assert chosen is not None and chosen.hour == 15
