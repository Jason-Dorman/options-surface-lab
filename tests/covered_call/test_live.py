"""T-80 — the live leg (FR-21), offline.

``capture()`` is the only thing in ``live.py`` that touches the network, and it is
not exercised here: NFR-4 means the suite runs on a machine with no LSEG. What is
exercised is everything that decides what gets *booked* — the planners are pure
functions of a captured payload, which is exactly why they were written that way.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

from options_surface_lab.covered_call import live
from options_surface_lab.covered_call.rules import (
    SKIP_NO_QUOTE,
    SKIP_NO_STOCK_PRINT,
    SKIP_NO_STRIKE,
    Params,
    valid_mid,
)
from options_surface_lab.option_surface_utils import (
    build_option_ric,
    occ_symbol,
    parse_option_ric,
)

BAR = "2026-09-14 15:00"


def snapshot(spot=714.88, strikes=(713, 714, 715, 716), bid=6.69, ask=6.81, bar=BAR):
    """A captured payload shaped like ``capture()`` returns."""
    expiry = dt.date(2026, 9, 18)
    chain = []
    for k in strikes:
        chain.append({
            "ric": build_option_ric("QQQ", expiry, "C", k, expired=False),
            "strike": float(k), "ric_form": "live",
            "occ": occ_symbol("QQQ", expiry, "C", k),
            "trdprc_1": 6.85, "bid": bid, "ask": ask,
        })
    return {
        "captured_at": "2026-09-14T16:05:00", "expiry": str(expiry),
        "session": "2026-09-14", "entry_bar": bar,
        "underlying": {"ric": "QQQ.O", "trdprc_1": spot, "bid": spot, "ask": spot},
        "chain": chain, "diagnostics": {},
    }


def fresh_state(params=None):
    return live.empty_state(params or Params())


# --------------------------------------------------------------------------
# The RIC and OCC grammar this leg depends on (T-67)
# --------------------------------------------------------------------------
def test_a_live_contract_has_no_caret_suffix():
    """T-62 proved this exact shape returns hourly BID/ASK for an unexpired weekly."""
    ric = build_option_ric("QQQ", dt.date(2026, 9, 18), "C", 715.0, expired=False)
    assert ric == "QQQI182671500.U"


def test_the_expired_form_is_unchanged_by_the_new_flag():
    assert build_option_ric("QQQ", dt.date(2026, 9, 4), "C", 720.0) == "QQQI042672000.U^I26"


def test_the_day_is_zero_padded_because_the_unpadded_form_does_not_resolve():
    """OQ-15 — the brief says otherwise; LSEG disagrees, measured in T-62."""
    assert build_option_ric("AAPL", dt.date(2026, 8, 7), "C", 205.0) == "AAPLH072620500.U^H26"


def test_occ_symbol_matches_the_briefs_worked_example():
    assert occ_symbol("AAPL", dt.date(2026, 8, 7), "C", 205.0) == "AAPL  260807C00205000"


def test_a_strike_too_big_for_the_ric_grammar_is_refused_not_silently_mangled():
    """The strike field is 5 digits, so it stops at $999.99.

    QQQ sits near $715, but a six-digit strike would build a RIC that parses back
    to a *different* contract and returns no data — an invisible skipped week
    rather than an error. The OCC symbol has an 8-digit field and is unaffected.
    """
    with pytest.raises(ValueError, match="5-digit"):
        build_option_ric("QQQ", dt.date(2026, 9, 18), "C", 1_000.0, expired=False)
    assert occ_symbol("QQQ", dt.date(2026, 9, 18), "C", 1_000.0) == "QQQ   260918C01000000"


def test_occ_and_ric_name_the_same_contract():
    """T-67 — a blotter row cannot name one contract in its RIC and another in its OCC."""
    for strike in (7.5, 205.0, 715.0, 999.5):
        expiry = dt.date(2026, 9, 18)
        parsed = parse_option_ric(build_option_ric("QQQ", expiry, "C", strike, expired=False))
        occ = occ_symbol("QQQ", expiry, "C", strike)
        assert occ[:6].strip() == parsed["root"]
        assert occ[6:12] == expiry.strftime("%y%m%d")
        assert occ[12] == parsed["cp"]
        assert int(occ[13:]) / 1000.0 == parsed["strike"] == strike


# --------------------------------------------------------------------------
# valid_mid — SPEC §6.1, DR-1
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bid, ask, expected",
    [
        (6.69, 6.81, 6.75),
        (0.0, 6.81, None),       # a zero bid is "no bid"
        (6.69, 0.0, None),
        (None, 6.81, None),      # one side alone has no midpoint
        (6.69, None, None),
        (6.90, 6.81, None),      # crossed market is a bad print
        (6.75, 6.75, 6.75),      # touching is fine
        (float("nan"), 6.81, None),
    ],
)
def test_a_mid_exists_only_when_the_quote_is_real(bid, ask, expected):
    assert valid_mid(bid, ask) == expected


# --------------------------------------------------------------------------
# plan_entry — SPEC §4
# --------------------------------------------------------------------------
def test_a_clean_entry_books_the_stock_and_the_call():
    params = Params()
    rows, skip = live.plan_entry(snapshot(), fresh_state(), params)
    assert skip is None and len(rows) == 2
    stock, call = rows
    assert (stock.side, stock.qty, stock.fill) == ("BUY", 100, 714.88)
    assert stock.cash_delta == pytest.approx(-71_488.0)
    assert (call.side, call.qty) == ("SELL", 1)
    assert call.fill == pytest.approx(6.75)            # mid of 6.69 / 6.81
    assert call.cash_delta == pytest.approx(675.0)     # 1 x 100 x mid
    assert "K=715" in call.note and "mid=6.75" in call.note
    assert call.instrument == "QQQI182671500.U"


def test_the_strike_is_the_one_the_rule_chose():
    """I-9, on the live leg: nothing listed may lie between spot and the strike."""
    rows, _ = live.plan_entry(snapshot(spot=714.88), fresh_state(), Params())
    assert "K=715" in rows[1].note


def test_spot_exactly_on_a_strike_writes_that_strike():
    rows, _ = live.plan_entry(snapshot(spot=715.0), fresh_state(), Params())
    assert "K=715" in rows[1].note


def test_holding_shares_writes_only_the_call():
    """OTM last week: keep the shares, just write the next call (the brief)."""
    state = fresh_state()
    state["position"]["shares"] = 100
    rows, skip = live.plan_entry(snapshot(), state, Params())
    assert skip is None and len(rows) == 1 and rows[0].side == "SELL"


def test_no_quote_books_nothing_at_all_when_flat():
    """DR-1 and the combo rule: buying the shares alone would be a different strategy."""
    rows, skip = live.plan_entry(snapshot(bid=0.0), fresh_state(), Params())
    assert rows == []
    assert skip.reason == SKIP_NO_QUOTE
    assert skip.state_at_skip == "FLAT"
    assert "no stock bought either" in skip.detail


def test_no_quote_while_holding_shares_leaves_the_shares_uncovered():
    state = fresh_state()
    state["position"]["shares"] = 100
    rows, skip = live.plan_entry(snapshot(ask=None), state, Params())
    assert rows == [] and skip.reason == SKIP_NO_QUOTE
    assert skip.state_at_skip == "STOCK_ONLY"


def test_a_crossed_market_is_refused_rather_than_averaged():
    rows, skip = live.plan_entry(snapshot(bid=7.00, ask=6.81), fresh_state(), Params())
    assert rows == [] and skip.reason == SKIP_NO_QUOTE


def test_no_strike_above_spot_is_its_own_reason():
    rows, skip = live.plan_entry(snapshot(spot=999.0), fresh_state(), Params())
    assert rows == [] and skip.reason == SKIP_NO_STRIKE


def test_no_stock_print_is_its_own_reason():
    snap = snapshot()
    snap["underlying"]["trdprc_1"] = None
    rows, skip = live.plan_entry(snap, fresh_state(), Params())
    assert rows == [] and skip.reason == SKIP_NO_STOCK_PRINT


def test_a_missing_entry_bar_skips_rather_than_using_another_bar():
    rows, skip = live.plan_entry(snapshot(bar=None), fresh_state(), Params())
    assert rows == [] and skip.reason == SKIP_NO_STOCK_PRINT


# --------------------------------------------------------------------------
# plan_settlement — SPEC §7, SD-6
# --------------------------------------------------------------------------
def covered_state(strike=715.0):
    state = fresh_state()
    state["position"] = {
        "shares": 100, "short_calls": 1,
        "call": {"ric": "QQQI182671500.U", "occ": occ_symbol("QQQ", dt.date(2026, 9, 18), "C", strike),
                 "strike": strike, "expiry": "2026-09-18"},
    }
    return state


def test_settling_above_the_strike_assigns_and_sells_the_stock():
    snap = snapshot(spot=719.02, bar="2026-09-18 15:00")
    rows, skip = live.plan_settlement(snap, covered_state(), Params())
    assert skip is None and [r.side for r in rows] == ["ASSIGN", "SELL"]
    assert rows[0].cash_delta == 0.0
    assert rows[1].fill == 715.0 and rows[1].cash_delta == pytest.approx(71_500.0)
    assert rows[0].time == rows[1].time == "2026-09-18 15:00"


def test_settling_below_the_strike_expires_and_keeps_the_shares():
    snap = snapshot(spot=714.87, bar="2026-09-18 15:00")
    rows, _ = live.plan_settlement(snap, covered_state(), Params())
    assert [r.side for r in rows] == ["EXPIRE"]
    assert rows[0].cash_delta == 0.0 and rows[0].fill == 0.0


def test_settling_exactly_on_the_strike_expires():
    """SD-6 strict. OCC auto-exercise needs a cent in the money."""
    snap = snapshot(spot=715.0, bar="2026-09-18 15:00")
    rows, _ = live.plan_settlement(snap, covered_state(), Params())
    assert [r.side for r in rows] == ["EXPIRE"]


def test_settlement_needs_no_option_quote():
    """An ITM call with no bid or ask on the expiry bar is still assigned (SPEC §7)."""
    snap = snapshot(spot=719.02, bid=None, ask=None, bar="2026-09-18 15:00")
    rows, _ = live.plan_settlement(snap, covered_state(), Params())
    assert [r.side for r in rows] == ["ASSIGN", "SELL"]


def test_settling_with_nothing_open_books_nothing():
    rows, skip = live.plan_settlement(snapshot(), fresh_state(), Params())
    assert rows == [] and skip is None


# --------------------------------------------------------------------------
# apply_rows — DR-3, and the I-1/I-5 shape of the resulting book
# --------------------------------------------------------------------------
def test_cash_moves_only_by_the_blotter_and_the_position_tracks_it():
    params, state, snap = Params(), fresh_state(), snapshot()
    rows, _ = live.plan_entry(snap, state, params)
    live.apply_rows(state, rows, snap, params)

    assert state["cash"] == pytest.approx(75_000.0 - 71_488.0 + 675.0)
    assert state["cash"] == pytest.approx(
        params.start_cash + sum(r["cash_delta"] for r in state["blotter"])
    ), "I-1: cash must reconcile against the blotter alone"
    assert state["position"] == {
        "shares": 100, "short_calls": 1,
        "call": {"ric": "QQQI182671500.U", "occ": "QQQ   260918C00715000",
                 "strike": 715.0, "expiry": "2026-09-18"},
    }


def test_a_full_assigned_week_returns_to_flat_with_the_premium_kept():
    params, state = Params(), fresh_state()
    snap = snapshot()
    rows, _ = live.plan_entry(snap, state, params)
    live.apply_rows(state, rows, snap, params)

    exit_snap = snapshot(spot=719.02, bar="2026-09-18 15:00")
    rows, _ = live.plan_settlement(exit_snap, state, params)
    live.apply_rows(state, rows, exit_snap, params)

    assert state["position"]["shares"] == 0
    assert state["position"]["short_calls"] == 0
    assert state["position"]["call"] is None
    # bought at 714.88, called away at 715, plus the 6.75 premium
    assert state["cash"] == pytest.approx(75_000.0 - 71_488.0 + 675.0 + 71_500.0)
    assert state["cash"] == pytest.approx(
        params.start_cash + sum(r["cash_delta"] for r in state["blotter"])
    )
    assert all(r["side"] != "BUY" or r["qty"] == 100 for r in state["blotter"])


def test_an_otm_week_keeps_the_shares_and_writes_again_next_week():
    params, state = Params(), fresh_state()
    snap = snapshot()
    live.apply_rows(state, live.plan_entry(snap, state, params)[0], snap, params)

    exit_snap = snapshot(spot=700.0, bar="2026-09-18 15:00")
    live.apply_rows(state, live.plan_settlement(exit_snap, state, params)[0], exit_snap, params)
    assert state["position"] == {"shares": 100, "short_calls": 0, "call": None}

    next_snap = snapshot(spot=701.0, strikes=(700, 701, 702))
    rows, skip = live.plan_entry(next_snap, state, params)
    assert skip is None and len(rows) == 1 and rows[0].side == "SELL"


def test_a_skipped_week_books_no_rows_and_moves_no_cash():
    params, state = Params(), fresh_state()
    snap = snapshot(bid=0.0)
    rows, skip = live.plan_entry(snap, state, params)
    assert rows == []
    state["skips"].append(skip.as_dict())
    assert state["cash"] == params.start_cash
    assert state["blotter"] == []
    assert state["skips"][0]["reason"] == SKIP_NO_QUOTE


# --------------------------------------------------------------------------
# State on disk
# --------------------------------------------------------------------------
def test_state_round_trips_through_json(tmp_path):
    params, state, snap = Params(), fresh_state(), snapshot()
    live.apply_rows(state, live.plan_entry(snap, state, params)[0], snap, params)
    path = tmp_path / "covered_call_live.json"
    live.save_state(state, path)
    assert json.loads(path.read_text(encoding="utf-8")) == live.load_state(params, path)


def test_a_missing_state_file_opens_the_account_flat_and_funded(tmp_path):
    state = live.load_state(Params(), tmp_path / "nope.json")
    assert state["cash"] == 75_000.0
    assert state["position"] == {"shares": 0, "short_calls": 0, "call": None}
    assert state["params"]["described"] == Params().describe_strike_rule()


def test_the_state_path_is_anchored_to_the_package_not_the_cwd():
    assert live.STATE_PATH.is_absolute()
    assert live.STATE_PATH.name == "covered_call_live.json"


# --------------------------------------------------------------------------
# The CLI's operational guards — what stands between the PO and a double entry
# --------------------------------------------------------------------------
def test_the_coming_friday_is_this_weeks_friday():
    """Monday 2026-09-14's contract is Friday 2026-09-18 (FR-21's first entry)."""
    assert live.coming_friday(dt.date(2026, 9, 14)) == dt.date(2026, 9, 18)
    assert live.coming_friday(dt.date(2026, 9, 18)) == dt.date(2026, 9, 18)
    assert live.coming_friday(dt.date(2026, 9, 19)) == dt.date(2026, 9, 25)


def test_a_second_entry_on_the_same_session_is_refused():
    """Running the command twice on Monday must not book the week twice."""
    params, state, snap = Params(), fresh_state(), snapshot()
    assert not live.already_booked(state, "2026-09-14", ("BUY", "SELL"))
    live.apply_rows(state, live.plan_entry(snap, state, params)[0], snap, params)
    assert live.already_booked(state, "2026-09-14", ("BUY", "SELL"))
    assert not live.already_booked(state, "2026-09-14", ("EXPIRE", "ASSIGN"))
    assert not live.already_booked(state, "2026-09-21", ("BUY", "SELL"))


def test_settling_twice_is_refused_but_entering_the_next_week_is_not():
    params, state = Params(), fresh_state()
    snap = snapshot()
    live.apply_rows(state, live.plan_entry(snap, state, params)[0], snap, params)
    ex = snapshot(spot=700.0, bar="2026-09-18 15:00")
    live.apply_rows(state, live.plan_settlement(ex, state, params)[0], ex, params)
    assert live.already_booked(state, "2026-09-18", ("EXPIRE", "ASSIGN"))
    assert not live.already_booked(state, "2026-09-21", ("BUY", "SELL"))


# --------------------------------------------------------------------------
# capture() and the CLI, with the LSEG boundary faked.
#
# These stay offline (NFR-4) by replacing `lseg_session`, which is the single
# seam where this module touches the network. They exist because a mutation run
# found the two guards below were reachable only through code no offline test
# entered: the DR-7 session resolution, and the double-run refusal.
# --------------------------------------------------------------------------
import contextlib

import pandas as pd

UTC_SESSION_HOURS = [13, 14, 15, 16, 17, 18, 19, 20, 21]  # 09:00..17:00 ET


def _naive_utc_index(days, hours=UTC_SESSION_HOURS):
    """LSEG's shape: tz-naive UTC, stamped at the bar's start (T-62)."""
    return pd.DatetimeIndex(
        [pd.Timestamp(dt.datetime.combine(d, dt.time(h))) for d in days for h in hours]
    )


def fake_lseg(spot_by_hour=None, quote=(4.77, 4.83), days=None, chain_returns=True):
    """A stand-in for the Workspace session. Tuesday-open week: no Monday bars."""
    # `or` would treat an empty list as "use the default" — and an empty tape is
    # exactly the case worth testing (Monday before the open).
    days = [dt.date(2026, 9, d) for d in (8, 9, 10, 11)] if days is None else days

    class FakeLd:
        def get_history(self, universe, fields, start, end, interval):
            idx = _naive_utc_index(days)
            if isinstance(universe, str):                      # the stock
                frame = pd.DataFrame(index=idx, columns=fields, dtype=float)
                for ts in idx:
                    px = (spot_by_hour or {}).get(ts.hour, 700.0 + ts.hour)
                    frame.loc[ts, "TRDPRC_1"] = px
                    frame.loc[ts, "BID"], frame.loc[ts, "ASK"] = px - 0.01, px + 0.01
                return frame
            if not chain_returns:
                raise RuntimeError("no data")
            cols = pd.MultiIndex.from_product([universe, fields])
            frame = pd.DataFrame(index=idx, columns=cols, dtype=float)
            for ric in universe:
                frame[(ric, "BID")] = quote[0]
                frame[(ric, "ASK")] = quote[1]
                frame[(ric, "TRDPRC_1")] = sum(quote) / 2
            return frame

    @contextlib.contextmanager
    def _session():
        yield FakeLd()

    return _session


def test_capture_reads_the_1500_et_bar_and_finds_the_week_off_the_tape(monkeypatch):
    """DR-7 plus the T-62 trap, in the code path that actually runs on Monday.

    2026-09-07 is Labor Day, so the week's first session is Tuesday. Resolving the
    entry day as `expiry - 4 days` would enter on a day with no bars and log a
    false skip; the tape has to say which day it is.
    """
    monkeypatch.setattr(live, "lseg_session", fake_lseg({19: 718.41}))
    snap = live.capture(dt.date(2026, 9, 11), Params())

    assert snap["session"] == "2026-09-08", "the week opens Tuesday; Monday was a holiday"
    assert snap["entry_bar"] == "2026-09-08 15:00"
    assert snap["underlying"]["trdprc_1"] == 718.41
    assert snap["diagnostics"]["session_source"] == "first session on the tape (DR-7)"
    # 19:00 UTC is 15:00 ET; the session's last bar is 21:00 UTC = 17:00 ET
    assert snap["diagnostics"]["bars_in_session"][-1] == "2026-09-08 17:00"


def test_capture_requests_live_form_rics_around_spot():
    monkeypatch_free = live.build_option_ric("QQQ", dt.date(2026, 9, 18), "C", 719.0, expired=False)
    assert monkeypatch_free.endswith(".U") and "^" not in monkeypatch_free


def test_capture_picks_the_strike_the_rule_says_and_never_the_last_bar(monkeypatch):
    monkeypatch.setattr(live, "lseg_session", fake_lseg({19: 718.41, 21: 999.0}))
    snap = live.capture(dt.date(2026, 9, 11), Params())
    rows, skip = live.plan_entry(snap, fresh_state(), Params())
    assert skip is None
    assert "K=719" in rows[1].note, "spot 718.41 at the 15:00 bar -> the 719 strike"
    assert "S=718.4100" in rows[1].note, "a 17:00 ET print must not reach the decision"


def test_capture_fails_soft_when_the_chain_returns_nothing(monkeypatch):
    monkeypatch.setattr(live, "lseg_session", fake_lseg({19: 718.41}, chain_returns=False))
    snap = live.capture(dt.date(2026, 9, 11), Params())
    assert snap["chain"] == []
    assert snap["diagnostics"]["option_error"] is not None
    rows, skip = live.plan_entry(snap, fresh_state(), Params())
    assert rows == [] and skip.reason == SKIP_NO_STRIKE


def test_the_cli_refuses_to_book_the_same_session_twice(monkeypatch, tmp_path):
    """The guard that stands between a re-run and a double entry."""
    monkeypatch.setattr(live, "lseg_session", fake_lseg({19: 718.41}))
    state_file = tmp_path / "live.json"
    args = ["enter", "--expiry", "2026-09-11", "--state", str(state_file)]

    assert live.main(args) == 0
    booked = live.load_state(Params(), state_file)
    assert [r["side"] for r in booked["blotter"]] == ["BUY", "SELL"]

    assert live.main(args) == 1, "a second run must refuse"
    assert live.load_state(Params(), state_file)["blotter"] == booked["blotter"]


def test_the_cli_refuses_to_log_the_same_skip_twice(monkeypatch, tmp_path):
    """I-10: a week appears once in the skip log, not once per re-run."""
    monkeypatch.setattr(live, "lseg_session", fake_lseg({19: 718.41}, quote=(0.0, 4.83)))
    state_file = tmp_path / "live.json"
    args = ["enter", "--expiry", "2026-09-11", "--state", str(state_file)]

    assert live.main(args) == 0
    assert len(live.load_state(Params(), state_file)["skips"]) == 1
    assert live.main(args) == 1
    assert len(live.load_state(Params(), state_file)["skips"]) == 1


def test_a_full_cli_week_enters_then_settles(monkeypatch, tmp_path):
    state_file = tmp_path / "live.json"
    monkeypatch.setattr(live, "lseg_session", fake_lseg({19: 718.41}))
    assert live.main(["enter", "--expiry", "2026-09-11", "--state", str(state_file)]) == 0

    monkeypatch.setattr(live, "lseg_session", fake_lseg({19: 714.87}))
    assert live.main(["settle", "--expiry", "2026-09-11", "--state", str(state_file)]) == 0

    state = live.load_state(Params(), state_file)
    assert [r["side"] for r in state["blotter"]] == ["BUY", "SELL", "EXPIRE"]
    assert state["position"]["shares"] == 100 and state["position"]["short_calls"] == 0
    assert state["cash"] == pytest.approx(
        Params().start_cash + sum(r["cash_delta"] for r in state["blotter"])
    )


def test_an_unresolved_session_says_so_rather_than_claiming_the_tape(monkeypatch):
    """Before the session has any bars the entry day is not known.

    Run at 00:03 on Monday it reported the arithmetic Monday while labelling it
    "first session on the tape" — a diagnostic that would read as confirmation on
    the one morning it matters.
    """
    monkeypatch.setattr(live, "lseg_session", fake_lseg(days=[]))
    snap = live.capture(dt.date(2026, 9, 18), Params())
    assert snap["entry_bar"] is None
    assert snap["diagnostics"]["session_source"].startswith("UNRESOLVED")
    assert snap["chain"] == []


# --------------------------------------------------------------------------
# Synchronisation evidence — the two legs are read from one bar, not one instant
# --------------------------------------------------------------------------
def sync_snapshot(stock_ofst=3599.0, call_ofst=3594.0, high=719.55, low=717.25):
    snap = snapshot(spot=718.41, strikes=(717, 718, 719, 720), bid=4.77, ask=4.83)
    snap["underlying"].update(
        {"c_sec_ofst": stock_ofst, "o_sec_ofst": 0.0, "high_1": high, "low_1": low}
    )
    for c in snap["chain"]:
        c.update({"c_sec_ofst": call_ofst, "o_sec_ofst": 4.0})
    return snap


def test_the_measured_gap_between_the_two_legs_is_booked_with_the_trade():
    """The fill assumption rests on the legs being contemporaneous. Measure it."""
    rows, skip = live.plan_entry(sync_snapshot(), fresh_state(), Params())
    assert skip is None
    assert "sync=5s" in rows[1].note
    assert "K=719" in rows[1].note and "mid=4.8" in rows[1].note


def test_a_missing_offset_omits_the_claim_rather_than_inventing_a_zero():
    snap = sync_snapshot()
    for c in snap["chain"]:
        c.pop("c_sec_ofst")
    rows, _ = live.plan_entry(snap, fresh_state(), Params())
    assert "sync=" not in rows[1].note, "no measurement means no claim, not sync=0s"
    assert live.sync_gap_seconds(snap, snap["chain"][0]) is None


def test_the_gap_is_symmetric_and_absolute():
    assert live.sync_gap_seconds(sync_snapshot(3594.0, 3599.0), sync_snapshot()["chain"][0]) is not None
    snap = sync_snapshot(stock_ofst=3590.0, call_ofst=3599.0)
    assert live.sync_gap_seconds(snap, snap["chain"][0]) == 9.0


def test_the_intra_bar_range_is_captured_so_the_page_can_show_it(monkeypatch):
    """Spot ranged 717.25-719.55 inside the entry hour and the rule read the close.

    A reader who assumes the strike was never in doubt is wrong, and the tape says
    so — which is why the high and low of the entry bar are captured, not just the
    print the rule used.
    """
    monkeypatch.setattr(live, "lseg_session", fake_lseg({19: 718.41}))
    snap = live.capture(dt.date(2026, 9, 11), Params())
    assert "high_1" in snap["underlying"] and "low_1" in snap["underlying"]
    assert "c_sec_ofst" in snap["underlying"]



# --------------------------------------------------------------------------
# The seam's own guard: open_session() does not raise when the handshake fails
# --------------------------------------------------------------------------
class _StubLd:
    """Shaped like ``lseg.data``: ``ld.session.get_default().open_state``."""

    def __init__(self, state):
        self.session = self
        self._state = state

    def get_default(self):
        return self

    @property
    def open_state(self):
        return self._state


def test_a_closed_session_is_refused_before_a_week_can_be_skipped():
    """Worse here than in the pull: a closed session looks like a week with no print.

    The live leg would have written ``SKIP_NO_STOCK_PRINT`` into the book for a
    desktop-side outage — and I-10's "a week appears once" would then refuse the
    re-run that would have booked it correctly.
    """
    with pytest.raises(RuntimeError) as excinfo:
        live._require_open_session(_StubLd("OpenState.Closed"))
    assert "signed in" in str(excinfo.value)


def test_an_open_session_passes_the_guard():
    assert live._require_open_session(_StubLd("OpenState.Opened")) is None
