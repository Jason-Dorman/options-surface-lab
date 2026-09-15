"""T-56 — the hourly tape (FR-13, SPEC-COVERED-CALL §3).

Offline throughout (NFR-4). ``fetch_tape`` is exercised in full by replacing
``tape.lseg_session`` — the module's single network seam — with a fake Workspace
that answers in LSEG's shapes: tz-naive UTC bars stamped at the bar's start, flat
field columns for a single RIC, ``(RIC, field)`` columns for a universe, and an
exception for a universe that does not resolve. That is the same trick T-80 used on
``live.py``, and for the same reason: the guards worth having — the two RIC forms,
the per-week band, the batch retry — live on the pull path, so an offline suite that
stops at the seam never runs them.

The fake's calendar is deliberately awkward: a full week, a one-session week that is
no trading week at all, and a **Friday-holiday week** whose expiry is therefore the
Thursday.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json

import pandas as pd
import pytest

from options_surface_lab.covered_call import tape as tape_mod
from options_surface_lab.covered_call.rules import Params, valid_mid
from options_surface_lab.covered_call.tape import (
    BAR_COLUMNS,
    FIELDS,
    STRIKE_STEP,
    Tape,
    attach_mid,
    fetch_tape,
    load_tape,
    strike_band,
    week_strike_band,
)
from options_surface_lab.option_surface_utils import build_option_ric, parse_option_ric

# The fake window: 2026-07-06 .. 2026-07-23.
WEEK_A = [dt.date(2026, 7, d) for d in (6, 7, 8, 9, 10)]      # W28: full, Friday expiry
WEEK_SHORT = [dt.date(2026, 7, 13)]                           # W29: one session, not a week
WEEK_B = [dt.date(2026, 7, d) for d in (20, 21, 22, 23)]      # W30: Friday holiday -> Thursday
ALL_DAYS = WEEK_A + WEEK_SHORT + WEEK_B

#: T-62's measured sessions. The stock runs to a 19:00 ET bar, options to 16:00 ET —
#: three hours and one hour past the 16:00 ET close respectively.
STOCK_UTC_HOURS = list(range(13, 24))      # 09:00 .. 19:00 ET
OPTION_UTC_HOURS = list(range(13, 21))     # 09:00 .. 16:00 ET

#: Which RIC form each week's contracts answer to — the point of SPEC §3.3. Week A is
#: old enough for the caret; week B, more recent, still answers only live.
FORM_BY_EXPIRY = {dt.date(2026, 7, 10): "expired", dt.date(2026, 7, 23): "live"}

#: Spot per week, so the per-week band is visibly not the window's band.
SPOT_BY_WEEK = {dt.date(2026, 7, 10): 700.0, dt.date(2026, 7, 13): 700.0,
                dt.date(2026, 7, 23): 720.0}
LISTED_STRIKES = {expiry: [SPOT_BY_WEEK[expiry] - 2 + i for i in range(5)]
                  for expiry in FORM_BY_EXPIRY}

PARAMS = Params(start=dt.date(2026, 7, 6), end=dt.date(2026, 7, 23))


def _naive_utc(days, hours):
    """LSEG's shape: tz-naive UTC, stamped at the bar's START (T-62)."""
    return pd.DatetimeIndex(
        [pd.Timestamp(dt.datetime.combine(d, dt.time(h))) for d in days for h in hours]
    )


def _expiry_of(day: dt.date) -> dt.date:
    for week in (WEEK_A, WEEK_SHORT, WEEK_B):
        if day in week:
            return week[-1]
    raise AssertionError(f"the fake tape has no session on {day}")


def fake_lseg(days=ALL_DAYS, quote=(4.77, 4.83), reject_batches_over=None, listed=None):
    """A stand-in Workspace session. Answers only for the RICs it has listed."""
    listed = LISTED_STRIKES if listed is None else listed

    def listed_rics():
        out = {}
        for expiry, strikes in listed.items():
            expired = FORM_BY_EXPIRY[expiry] == "expired"
            for strike in strikes:
                out[build_option_ric("QQQ", expiry, "C", strike, expired=expired)] = strike
        return out

    class FakeLd:
        calls: list = []

        def get_history(self, universe, fields, start, end, interval):
            assert interval == "hourly", "DR-6: one bar size for both legs"
            self.calls.append(list(universe))
            window = [d for d in days
                      if dt.date.fromisoformat(str(start)[:10]) <= d
                      <= dt.date.fromisoformat(str(end)[:10])]
            if "QQQ.O" in universe:
                index = _naive_utc(window, STOCK_UTC_HOURS)
                frame = pd.DataFrame(index=index, columns=list(fields), dtype=float)
                for ts in index:
                    spot = SPOT_BY_WEEK[_expiry_of(ts.date())] + (ts.hour - 13) * 0.10
                    frame.loc[ts, "TRDPRC_1"] = spot
                    frame.loc[ts, "BID"], frame.loc[ts, "ASK"] = spot - 0.01, spot + 0.01
                    frame.loc[ts, "LOW_1"], frame.loc[ts, "HIGH_1"] = spot - 0.5, spot + 0.5
                return frame                       # single RIC -> flat field columns

            if reject_batches_over is not None and len(universe) > reject_batches_over:
                raise RuntimeError("LDError: request too large")
            answering = [r for r in universe if r in listed_rics()]
            if not answering:
                raise RuntimeError("LDError: The universe is not found")
            index = _naive_utc(window, OPTION_UTC_HOURS)
            columns = pd.MultiIndex.from_product([answering, list(fields)])
            frame = pd.DataFrame(index=index, columns=columns, dtype=float)
            for ric in answering:
                frame[(ric, "BID")] = quote[0]
                frame[(ric, "ASK")] = quote[1]
                frame[(ric, "TRDPRC_1")] = sum(quote) / 2
            return frame

    session_ld = FakeLd()

    @contextlib.contextmanager
    def _session():
        yield session_ld

    _session.ld = session_ld
    return _session


@pytest.fixture
def pulled(monkeypatch, tmp_path):
    """One complete fake pull, written to a scratch parquet and read back."""
    monkeypatch.delenv("OSL_OFFLINE", raising=False)
    session = fake_lseg()
    monkeypatch.setattr(tape_mod, "lseg_session", session)
    path = tmp_path / "covered_call_tape.parquet"
    tape = fetch_tape(PARAMS, path=path)
    return tape, path, session


# --------------------------------------------------------------------------
# The schema (SPEC §3.1)
# --------------------------------------------------------------------------
def test_the_stored_table_is_the_spec_31_schema(pulled):
    tape, path, _ = pulled
    stored = pd.read_parquet(path)
    assert list(stored.columns) == BAR_COLUMNS
    assert set(tape.bars["kind"]) == {"stock", "option"}


def test_mid_is_derived_at_load_and_never_stored(pulled):
    """A stored mid could contradict the bid and ask sitting beside it in the file."""
    tape, path, _ = pulled
    assert "mid" not in pd.read_parquet(path).columns
    assert "mid" in tape.bars.columns


def test_timestamps_come_back_as_exchange_time(pulled):
    tape, _, _ = pulled
    assert str(tape.bars["ts"].dt.tz) == PARAMS.tz


def test_a_1900_utc_bar_is_stored_as_the_1500_et_closing_bar(pulled):
    """The T-62 conversion, end to end: 19:00 UTC is 15:00 ET under EDT."""
    tape, _, _ = pulled
    day = dt.date(2026, 7, 10)
    hours = sorted({ts.hour for ts in tape.stock["ts"] if ts.date() == day})
    assert 15 in hours
    assert max(hours) == 19, "the stock tape must keep its post-close bars, not truncate"


def test_option_and_stock_rows_carry_their_identity(pulled):
    tape, _, _ = pulled
    options = tape.options
    assert set(options["cp"]) == {"C"}
    assert options["strike"].notna().all()
    assert options["expiry"].notna().all()
    assert tape.stock["strike"].isna().all()
    assert tape.stock["expiry"].isna().all()


def test_expiry_round_trips_through_parquet_as_a_date(pulled):
    tape, _, _ = pulled
    sample = tape.options["expiry"].iloc[0]
    assert isinstance(sample, dt.date) and not isinstance(sample, dt.datetime)


def test_the_payload_keys_sit_beside_the_table(pulled):
    tape, path, _ = pulled
    meta = json.loads(path.with_name(path.stem + ".meta.json").read_text(encoding="utf-8"))
    for key in ("ticker", "root", "window", "interval", "fetched_at", "synthetic",
                "diagnostics"):
        assert key in meta
    diag = meta["diagnostics"]
    for key in ("requested", "returned", "ric_form_used", "strike_step_discovered",
                "tz_convention", "weeks"):
        assert key in diag
    assert diag["strike_step_discovered"] == STRIKE_STEP
    assert "START" in diag["tz_convention"]
    assert tape.synthetic is False


def test_an_unlabelled_payload_is_treated_as_synthetic():
    """The dangerous default: a tape that forgot to say is not assumed to be real."""
    assert Tape(bars=tape_mod.empty_bars(), meta={}).synthetic is True


# --------------------------------------------------------------------------
# The calendar and the chain (SPEC §3.2, §3.3)
# --------------------------------------------------------------------------
def test_a_friday_holiday_expires_on_the_thursday_and_the_ric_carries_that_date(pulled):
    """FR-13's acceptance criterion, and DR-7's whole reason for existing."""
    tape, _, _ = pulled
    weeks = tape.weeks(PARAMS)
    by_label = {w.label: w for w in weeks}
    holiday_week = by_label["2026-W30"]
    assert holiday_week.expiry_day == dt.date(2026, 7, 23)     # Thursday, not the 24th
    assert holiday_week.entry_day == dt.date(2026, 7, 20)
    rics = tape.options[tape.options["expiry"] == dt.date(2026, 7, 23)]["ric"].unique()
    assert rics.size
    for ric in rics:
        assert parse_option_ric(ric)["expiry"] == dt.date(2026, 7, 23)


def test_each_contracts_ric_form_is_recorded(pulled):
    """SPEC §3.3: which form answered is a fact about the data, so it is written down."""
    tape, _, _ = pulled
    forms = tape.meta["diagnostics"]["ric_form_used"]
    assert set(forms.values()) == {"expired", "live"}
    for ric, form in forms.items():
        assert ("^" in ric) == (form == "expired")


def test_both_forms_are_requested_when_the_caret_form_answers_nothing(pulled):
    """The 09-11 case: a recently expired contract answers only without the suffix."""
    tape, _, _ = pulled
    requested = tape.meta["diagnostics"]["requested"]
    thursday = dt.date(2026, 7, 23)
    caret = [r for r in requested if "^" in r and parse_option_ric(r)["expiry"] == thursday]
    live = [r for r in requested if "^" not in r and parse_option_ric(r)["expiry"] == thursday]
    assert caret and live, "a week that answers live must have been tried under the caret too"


def test_a_contract_that_answered_is_not_asked_again_under_the_other_form(pulled):
    """Week A's listed strikes resolve under the caret, so they are never asked live.

    The strikes the caret form did *not* answer for are asked again — that is the
    fallback working, and it is why this checks the contracts that answered rather
    than the whole week.
    """
    tape, _, _ = pulled
    friday = dt.date(2026, 7, 10)
    requested = set(tape.meta["diagnostics"]["requested"])
    for strike in LISTED_STRIKES[friday]:
        caret = build_option_ric("QQQ", friday, "C", strike, expired=True)
        live = build_option_ric("QQQ", friday, "C", strike, expired=False)
        assert caret in requested and live not in requested


def test_a_one_session_week_is_recorded_and_its_chain_never_requested(pulled):
    """I-10 starts here: the week must be visible so the engine can log the skip."""
    tape, _, _ = pulled
    weeks = {w["week"]: w for w in tape.meta["diagnostics"]["weeks"]}
    short = weeks["2026-W29"]
    assert short["short_week"] is True
    assert short["n_contracts"] == 0
    assert not any(parse_option_ric(r)["expiry"] == WEEK_SHORT[-1]
                   for r in tape.meta["diagnostics"]["requested"])


def test_the_chain_is_the_weeks_listed_strikes(pulled):
    tape, _, _ = pulled
    assert tape.strikes_for(dt.date(2026, 7, 10)) == LISTED_STRIKES[dt.date(2026, 7, 10)]
    assert tape.strikes_for(dt.date(2026, 7, 23)) == LISTED_STRIKES[dt.date(2026, 7, 23)]
    assert tape.strikes_for(dt.date(2026, 7, 24)) == []


def test_every_requested_contract_gets_a_verdict(pulled):
    """Answered, or refused and recorded — never neither.

    This is the check that catches a batch failing in a way the retry does not cover:
    the contracts would simply not be in the tape, and a chain nobody knows is short
    produces a skipped week that looks like the market's fault. T-77's pull came out
    exact — 952 answered + 150 refused = 1,102 requested — but only because every
    leftover happened to land in a batch that failed *whole* and was retried one RIC
    at a time. A batch that answers **partially** raises nothing, so this fixture
    (where that is the normal case) is what makes the record explicit rather than
    lucky.
    """
    tape, _, _ = pulled
    diag = tape.meta["diagnostics"]
    requested = set(diag["requested"])
    answered = set(tape.options["ric"].unique())
    assert answered <= requested, "the tape holds contracts the pull never asked for"
    assert requested - answered == set(diag["unanswered"]), (
        "a requested contract returned nothing and was not recorded as unanswered"
    )
    assert not (answered & set(diag["unanswered"])), "a RIC is both answered and not"


def test_a_rejected_batch_is_retried_one_ric_at_a_time(monkeypatch, tmp_path):
    """AD-2: one bad guess in a batch of 25 must not cost the other 24."""
    monkeypatch.delenv("OSL_OFFLINE", raising=False)
    session = fake_lseg(reject_batches_over=3)
    monkeypatch.setattr(tape_mod, "lseg_session", session)
    tape = fetch_tape(PARAMS, path=tmp_path / "t.parquet", batch_size=25)
    assert tape.options["ric"].nunique() == sum(len(v) for v in LISTED_STRIKES.values())
    assert any(len(call) == 1 for call in session.ld.calls), "no single-RIC retry happened"
    assert tape.meta["diagnostics"]["errors"], "a rejected batch must be recorded, not hidden"


# --------------------------------------------------------------------------
# The strike band (SPEC §3.3, T-62's step)
# --------------------------------------------------------------------------
def test_the_band_is_generated_on_the_discovered_step():
    band = strike_band(709.16, 711.96, step=1.00, pad=2)
    assert band == [707.0, 708.0, 709.0, 710.0, 711.0, 712.0, 713.0, 714.0]


def test_a_half_dollar_step_is_honoured():
    assert strike_band(100.0, 101.0, step=0.50, pad=0) == [100.0, 100.5, 101.0]


def test_every_strike_in_the_band_round_trips_through_the_ric_grammar():
    """Float drift in a ladder builds a RIC one cent off a real contract — invisibly."""
    for strike in strike_band(690.0, 730.0, step=0.50, pad=1):
        ric = build_option_ric("QQQ", dt.date(2026, 9, 18), "C", strike, expired=False)
        assert parse_option_ric(ric)["strike"] == strike


def test_a_nonsense_band_is_refused_rather_than_returning_nothing():
    with pytest.raises(ValueError):
        strike_band(710.0, 700.0)
    with pytest.raises(ValueError):
        strike_band(700.0, 710.0, step=0.0)
    with pytest.raises(ValueError):
        strike_band(float("nan"), 710.0)


def test_the_band_follows_the_weeks_own_range_not_the_windows(pulled):
    """Two weeks 20 points apart must not each request the other's strikes."""
    tape, _, _ = pulled
    stock = tape.stock
    weeks = {w.label: w for w in tape.weeks(PARAMS)}
    band_a = week_strike_band(stock, weeks["2026-W28"], step=STRIKE_STEP, pad=1)
    band_b = week_strike_band(stock, weeks["2026-W30"], step=STRIKE_STEP, pad=1)
    assert max(band_a) < min(band_b)
    assert 700.0 in band_a and 720.0 in band_b


# --------------------------------------------------------------------------
# The quote rule (SPEC §6.1) — one rule, two implementations, checked against
# each other rather than against itself
# --------------------------------------------------------------------------
QUOTE_CASES = [
    (4.77, 4.83), (0.0, 4.83), (4.83, 4.77), (None, 4.83), (4.77, None),
    (None, None), (-1.0, 4.83), (4.80, 4.80), (0.01, 0.02), (4.77, 0.0),
]


def test_the_vectorised_mid_agrees_with_the_scalar_rule_row_by_row():
    bars = tape_mod.empty_bars()
    bars = pd.DataFrame({
        "ts": pd.to_datetime(["2026-07-10 15:00"] * len(QUOTE_CASES)).tz_localize(PARAMS.tz),
        "ric": ["X"] * len(QUOTE_CASES), "kind": "option", "expiry": None,
        "strike": 700.0, "cp": "C",
        "bid": [b for b, _ in QUOTE_CASES], "ask": [a for _, a in QUOTE_CASES],
        "trdprc_1": 4.80, "open": None, "high": None, "low": None,
        "volume": None, "num_moves": None,
    })
    out = attach_mid(bars)
    for (bid, ask), got in zip(QUOTE_CASES, out["mid"]):
        expected = valid_mid(bid, ask)
        if expected is None:
            assert pd.isna(got), f"({bid}, {ask}) is not a valid quote (SPEC §6.1)"
        else:
            assert got == pytest.approx(expected)


# --------------------------------------------------------------------------
# Cache-first, offline, and the refusals (AD-1, NFR-4)
# --------------------------------------------------------------------------
def test_the_loader_opens_no_session(pulled, monkeypatch):
    def explode():
        raise AssertionError("load_tape must never reach the network")

    monkeypatch.setattr(tape_mod, "lseg_session", explode)
    _, path, _ = pulled
    assert len(load_tape(path).bars) > 0


def test_the_loader_says_what_to_do_when_there_is_no_tape(tmp_path):
    with pytest.raises(FileNotFoundError) as excinfo:
        load_tape(tmp_path / "absent.parquet")
    assert "RUNBOOK" in str(excinfo.value)


def test_a_naive_timestamp_in_a_tape_is_read_as_utc_and_converted(tmp_path):
    """The docstring's promise, tested: a naive 19:00 is UTC, so it loads as 15:00 ET.

    Our own writer always stores tz-aware bars, so this path only runs for a file
    someone else produced — which is exactly the case where relabelling instead of
    converting would move every bar four hours and nothing would look wrong.
    """
    path = tmp_path / "naive.parquet"
    frame = tape_mod.empty_bars()
    frame.loc[0] = {c: None for c in BAR_COLUMNS}
    frame.loc[0, "ric"], frame.loc[0, "kind"] = "QQQ.O", "stock"
    frame["ts"] = pd.to_datetime(["2026-07-10 19:00:00"])          # naive, i.e. UTC
    frame.to_parquet(path, index=False)
    loaded = load_tape(path)
    assert loaded.bars["ts"].iloc[0].hour == 15
    assert str(loaded.bars["ts"].dt.tz) == PARAMS.tz


def test_a_file_that_is_not_a_tape_is_refused_by_name(tmp_path):
    path = tmp_path / "wrong.parquet"
    pd.DataFrame({"ts": [1], "close": [2.0]}).to_parquet(path, index=False)
    with pytest.raises(ValueError) as excinfo:
        load_tape(path)
    assert "missing columns" in str(excinfo.value)


def test_fetch_refuses_to_overwrite_an_existing_tape(pulled, monkeypatch):
    tape, path, session = pulled
    monkeypatch.setattr(tape_mod, "lseg_session", session)
    with pytest.raises(FileExistsError):
        fetch_tape(PARAMS, path=path)


def test_fetch_refuses_to_run_offline(monkeypatch, tmp_path):
    monkeypatch.setenv("OSL_OFFLINE", "1")
    monkeypatch.setattr(tape_mod, "lseg_session", fake_lseg())
    with pytest.raises(RuntimeError) as excinfo:
        fetch_tape(PARAMS, path=tmp_path / "t.parquet")
    assert "OSL_OFFLINE" in str(excinfo.value)


def test_a_pull_that_finds_no_stock_writes_nothing(monkeypatch, tmp_path):
    """A half-written tape would block the retry and render as an empty book."""
    monkeypatch.delenv("OSL_OFFLINE", raising=False)
    monkeypatch.setattr(tape_mod, "lseg_session", fake_lseg(days=[]))
    path = tmp_path / "t.parquet"
    with pytest.raises(RuntimeError):
        fetch_tape(PARAMS, path=path)
    assert not path.exists()


def test_assignment_11s_cache_is_never_named_in_this_module():
    """CLAUDE.md's hard constraint, made mechanical rather than reviewed."""
    source = (tape_mod.__file__ or "")
    text = open(source, encoding="utf-8").read()
    body = text.split('"""', 2)[-1]           # the docstring may name it to forbid it
    assert "option_pipeline_data" not in body


def test_the_requested_fields_are_the_ones_the_schema_needs():
    assert {"TRDPRC_1", "BID", "ASK"} <= set(FIELDS)
    assert set(tape_mod.FIELD_TO_COLUMN.values()) <= set(BAR_COLUMNS)


def test_describe_reports_what_a_human_checks_before_committing(pulled):
    tape, _, _ = pulled
    text = tape_mod.describe(tape)
    assert "synthetic=False" in text
    assert "2026-W29" in text and "SHORT WEEK" in text     # the one-session week
    assert "expired" in text and "live" in text



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


def test_a_closed_session_is_refused_before_anything_is_requested():
    """The 2026-09-14 failure: a ready proxy, a handshake that never answered.

    ``open_session()`` logged and returned, leaving a closed session, so the pull
    requested the stock against it and reported "no bars returned" — blaming the tape
    for a desktop-side outage. The cause has to be named where it happens.
    """
    with pytest.raises(RuntimeError) as excinfo:
        tape_mod._require_open_session(_StubLd("OpenState.Closed"))
    assert "signed in" in str(excinfo.value)


def test_an_open_session_passes_the_guard():
    assert tape_mod._require_open_session(_StubLd("OpenState.Opened")) is None
