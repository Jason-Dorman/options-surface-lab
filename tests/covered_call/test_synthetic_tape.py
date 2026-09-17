"""T-63 — the synthetic tape (SPEC §3.4, AD-7).

Two things are being tested here, and they are different in kind.

The first is that the fixture **is a tape**: same schema, same dtypes, same payload
shape as a pulled one, so nothing downstream can tell them apart except by
``Tape.synthetic``. If they diverge, every test that runs on the fixture is testing
something the engine will never see.

The second is that it **contains the cases the engine must survive** — each named in
``SYNTHETIC_ROLES`` and checked here *through the engine's own helpers*, not against
the generator's intent. A fixture that merely claims to have a holiday week is worth
nothing; what matters is that ``trading_weeks`` reads a Thursday expiry out of it.
"""
from __future__ import annotations

import ast
import datetime as dt
import inspect
import textwrap
import warnings

import numpy as np
import pandas as pd
import pytest

from options_surface_lab.covered_call import tape as tape_mod
from options_surface_lab.covered_call.rules import (
    Params,
    closing_bar_ts,
    entry_bar_ts,
    is_itm,
    select_strike,
)
from options_surface_lab.covered_call.tape import (
    BAR_COLUMNS,
    STRIKE_STEP,
    empty_bars,
    load_tape,
    synthesize_tape,
)
from options_surface_lab.option_surface_utils import bs_price, parse_option_ric

#: The fixture's window, restated here rather than imported — `tests/` is not a
#: package. `test_the_fixture_is_built_from_these` pins the two together, so they
#: cannot drift apart silently.
FIXTURE_END_DATE = dt.date(2026, 9, 11)
FIXTURE_SEED = 7


def test_the_fixture_is_built_from_these(synthetic_tape):
    diag = synthetic_tape.meta["diagnostics"]
    assert diag["end_date"] == str(FIXTURE_END_DATE)
    assert diag["seed"] == FIXTURE_SEED


def _entry(tape, week, params):
    """(entry bar, spot, chain, chosen strike, its mid) — the engine's first move."""
    stock = tape.stock
    bar = entry_bar_ts(stock["ts"], week.entry_day, params)
    spot = None if bar is None else float(stock.loc[stock["ts"] == bar, "trdprc_1"].iloc[0])
    chain = tape.strikes_for(week.expiry_day)
    strike = select_strike(chain, spot, params)
    quote = tape.options[(tape.options["ts"] == bar)
                         & (tape.options["expiry"] == week.expiry_day)
                         & (tape.options["strike"] == strike)]
    mid = None if quote.empty or pd.isna(quote["mid"].iloc[0]) else float(quote["mid"].iloc[0])
    return bar, spot, chain, strike, mid


# --------------------------------------------------------------------------
# It is a tape
# --------------------------------------------------------------------------
def test_the_schema_is_indistinguishable_from_a_pulled_tape(synthetic_tape):
    """**Every** column, including the ones that hold python values.

    This used to `continue` past `ric`/`kind`/`cp`/`expiry` — "object columns carry
    python values, not dtypes" — and that exemption is precisely where the schema
    then drifted: under pandas 3 a parquet string column reads back as the new `str`
    dtype, so a tape off disk and a tape in memory had different dtypes on the same
    code. Local pandas 2 could not see it and CI went red on 2026-09-17. *A column a
    schema test skips is a column with no schema test.*
    """
    assert list(synthetic_tape.bars.columns) == BAR_COLUMNS + ["mid"]
    reference = empty_bars()
    for column in BAR_COLUMNS:
        got, want = synthetic_tape.bars[column].dtype, reference[column].dtype
        assert got == want, f"{column}: {got} is not a pulled tape's {want}"
    assert str(synthetic_tape.bars["ts"].dt.tz) == Params().tz
    # Declared, not inherited: pandas 2 forced ns, pandas 3 infers us from a datetime.
    assert synthetic_tape.bars["ts"].dt.unit == tape_mod.TS_UNIT


def test_a_tape_off_disk_and_a_tape_in_memory_carry_one_schema(synthetic_tape, tmp_path):
    """SPEC §3.4's claim, asserted against the **loader** rather than the generator.

    `empty_bars()` is what the generator was written against, so comparing to it alone
    can only catch the generator drifting. The failure that reached CI was the other
    side — the parquet round trip — so the reference here is a tape that has actually
    been through a file (T-46: compare a thing against something it did not produce).
    """
    path = tmp_path / "schema.parquet"
    synthetic_tape.bars[BAR_COLUMNS].to_parquet(path, index=False)
    reloaded = load_tape(path)
    assert reloaded.bars.dtypes.to_dict() == synthetic_tape.bars.dtypes.to_dict()
    # A stock row has no right; "missing" must be None on both sides, not None on one
    # and a float nan on the other — which is what `.astype(object)` alone would give.
    assert reloaded.bars.loc[reloaded.bars["kind"] == "stock", "cp"].isna().all()
    assert set(reloaded.bars.loc[reloaded.bars["kind"] == "stock", "cp"]) == {None}


def test_it_says_it_is_synthetic_in_the_place_the_page_reads(synthetic_tape):
    assert synthetic_tape.synthetic is True
    assert synthetic_tape.meta["synthetic"] is True
    assert "SYNTHETIC" in tape_mod.describe(synthetic_tape)


def test_option_rows_carry_a_ric_that_parses_back_to_their_own_identity(synthetic_tape):
    sample = synthetic_tape.options.drop_duplicates("ric").head(50)
    for _, row in sample.iterrows():
        parsed = parse_option_ric(row["ric"])
        assert parsed["expiry"] == row["expiry"]
        assert parsed["strike"] == row["strike"]
        assert parsed["cp"] == row["cp"] == "C"


def test_it_survives_a_round_trip_through_parquet(synthetic_tape, tmp_path):
    """A synthetic tape must be writable, or it cannot stand in for the real one."""
    path = tmp_path / "synthetic.parquet"
    synthetic_tape.bars[BAR_COLUMNS].to_parquet(path, index=False)
    reloaded = load_tape(path)
    pd.testing.assert_frame_equal(reloaded.bars, synthetic_tape.bars)


def test_each_weeks_chain_is_a_contiguous_ladder_on_the_discovered_step(synthetic_tape):
    """Per expiry, not per window.

    Each week's band is centred on its own entry spot, so the *union* across a window
    has gaps wherever the stock moved further than the band between two Mondays —
    which is what a real chain looks like too (the pulled tape's weekly bands overlap
    only partly). The ladder that has to be unbroken is the one the rule walks: a
    single expiry's.
    """
    for expiry in sorted(synthetic_tape.options["expiry"].dropna().unique()):
        strikes = synthetic_tape.strikes_for(expiry)
        steps = {round(b - a, 10) for a, b in zip(strikes, strikes[1:])}
        assert steps <= {STRIKE_STEP}, f"{expiry}: off-grid or gapped chain {steps}"


# --------------------------------------------------------------------------
# It does not depend on the calendar — OQ-6's lesson, made mechanical
# --------------------------------------------------------------------------
def test_the_window_ends_where_the_caller_said_and_nowhere_else():
    for end in (dt.date(2026, 9, 11), dt.date(2026, 3, 6), dt.date(2025, 11, 12)):
        tape = synthesize_tape(end, weeks=4)
        assert max(tape.stock["ts"]).date() == end
        assert tape.meta["window"][1] == str(end)


#: Every way this codebase could read a clock. Widened after T-81 found the first
#: version checked four spellings and could not detect the commonest one.
CLOCK_CALLS = (
    "date.today", "today()", "datetime.now", ".now(", "time.time",
    "Timestamp.now", "Timestamp('today')", 'Timestamp("today")', "utcnow",
)


def _generator_functions():
    """Every generator function, found rather than listed.

    The first version named five functions by hand and missed two; a helper added
    later would have been uncovered the day it was written.
    """
    return [fn for name, fn in vars(tape_mod).items()
            if callable(fn) and getattr(fn, "__module__", "") == tape_mod.__name__
            and (name.startswith("_synthetic") or name in ("synthesize_tape",
                                                           "dropped_roles"))]


def _source_without_docstrings(fn):
    """The function's code, with its docstring removed structurally.

    The first version stripped the docstring by replacing the literal text `today()`,
    which deleted the exact substring the `date.today` check then searched for — so
    that check could never fire. A prose mention must not be able to blind a guard
    (T-81).
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                             ast.Module)) and ast.get_docstring(node):
            node.body = node.body[1:]
    return ast.unparse(tree)


def test_no_clock_is_read_anywhere_in_the_generator():
    """OQ-6 in one assertion: a fixture that reads the clock reports on the clock."""
    functions = _generator_functions()
    assert len(functions) >= 6, f"only found {len(functions)} generator functions"
    code = "\n".join(_source_without_docstrings(fn) for fn in functions)
    for clock in CLOCK_CALLS:
        assert clock not in code, f"the generator reads {clock}"


def test_the_clock_guard_can_actually_fail():
    """The guard that guards the guard: prove the check fires on planted code.

    Its predecessor passed on a generator that called `dt.date.today()`, because the
    docstring sanitiser had eaten the needle. A test for absence must be shown to
    detect presence.
    """
    planted = chr(10).join(["def f():",
                            "    # mentions today() in a comment",
                         "    return dt.date.today()"])
    tree = ast.parse(planted)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and ast.get_docstring(node):
            node.body = node.body[1:]
    code = ast.unparse(tree)
    assert any(clock in code for clock in CLOCK_CALLS), (
        "the clock guard cannot detect a plain dt.date.today() call"
    )


def test_end_date_is_required_so_it_can_never_default_to_today():
    signature = inspect.signature(synthesize_tape)
    assert signature.parameters["end_date"].default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        synthesize_tape()


def test_a_weekend_end_date_is_refused_rather_than_silently_moved():
    with pytest.raises(ValueError):
        synthesize_tape(dt.date(2026, 9, 12))            # a Saturday


def test_the_same_seed_and_date_give_byte_identical_bars():
    """I-12's determinism rests on this, and so does every stored expectation."""
    a = synthesize_tape(FIXTURE_END_DATE, seed=FIXTURE_SEED)
    b = synthesize_tape(FIXTURE_END_DATE, seed=FIXTURE_SEED)
    pd.testing.assert_frame_equal(a.bars, b.bars)


def test_a_different_seed_gives_a_different_tape():
    a = synthesize_tape(FIXTURE_END_DATE, seed=FIXTURE_SEED)
    b = synthesize_tape(FIXTURE_END_DATE, seed=FIXTURE_SEED + 1)
    assert not a.bars["trdprc_1"].equals(b.bars["trdprc_1"])


# --------------------------------------------------------------------------
# It contains the cases the engine must survive — read back through rules.py
# --------------------------------------------------------------------------
def test_a_monday_holiday_makes_the_week_enter_on_the_tuesday(role_weeks):
    week = role_weeks["monday_holiday"]
    assert week.entry_day.weekday() == 1
    assert len(week.sessions) == 4


def test_a_friday_holiday_expires_thursday_and_the_ric_carries_that_date(
    synthetic_tape, role_weeks
):
    week = role_weeks["friday_holiday"]
    assert week.expiry_day.weekday() == 3
    rics = synthetic_tape.options[
        synthetic_tape.options["expiry"] == week.expiry_day
    ]["ric"].unique()
    assert rics.size
    for ric in rics:
        assert parse_option_ric(ric)["expiry"] == week.expiry_day


def test_a_one_session_week_is_visible_and_lists_no_chain(synthetic_tape, role_weeks):
    week = role_weeks["short_week"]
    assert week.is_short and len(week.sessions) == 1
    assert synthetic_tape.strikes_for(week.expiry_day) == []


def test_a_half_session_entry_day_has_no_entry_bar(synthetic_tape, role_weeks, params):
    """SKIP_NO_STOCK_PRINT: the session exists, the 15:00 bar does not (AD-9)."""
    week = role_weeks["half_session_entry_day"]
    assert entry_bar_ts(synthetic_tape.stock["ts"], week.entry_day, params) is None
    assert closing_bar_ts(synthetic_tape.stock["ts"], week.expiry_day, params) is not None


def test_one_entry_bar_in_the_window_has_no_valid_quote(synthetic_tape, role_weeks, params):
    """SPEC §3.4 requires this outright: the skip path is never reached by accident."""
    week = role_weeks["no_quote_at_entry"]
    bar, spot, chain, strike, mid = _entry(synthetic_tape, week, params)
    assert spot is not None and strike is not None, "the week must fail on the QUOTE"
    assert mid is None
    quote = synthetic_tape.options[(synthetic_tape.options["ts"] == bar)
                                   & (synthetic_tape.options["strike"] == strike)
                                   & (synthetic_tape.options["expiry"] == week.expiry_day)]
    assert float(quote["bid"].iloc[0]) == 0.0, "a zero bid is 'no bid' (SPEC §6.1)"


def test_one_week_lists_no_strike_at_or_above_spot(synthetic_tape, role_weeks, params):
    """SKIP_NO_STRIKE, which is a different skip from SKIP_NO_QUOTE (I-10)."""
    week = role_weeks["no_strike_above_spot"]
    bar, spot, chain, strike, _ = _entry(synthetic_tape, week, params)
    assert chain, "the week must list strikes — just none above spot"
    assert max(chain) < spot
    assert strike is None


def test_the_window_finishes_on_both_sides_of_the_strike(synthetic_tape, params):
    """A window that never assigns exercises neither the sale nor the shares leaving."""
    outcomes = []
    for week in synthetic_tape.weeks(params):
        _, spot, _, strike, mid = _entry(synthetic_tape, week, params)
        if mid is None or strike is None:
            continue
        close = closing_bar_ts(synthetic_tape.stock["ts"], week.expiry_day, params)
        if close is None:
            continue
        settle = float(synthetic_tape.stock.loc[
            synthetic_tape.stock["ts"] == close, "trdprc_1"].iloc[0])
        outcomes.append(is_itm(settle, strike, params))
    assert True in outcomes, "no week assigns"
    assert False in outcomes, "every week assigns"


def test_every_named_role_is_actually_used(role_weeks):
    assert set(role_weeks) == set(tape_mod.SYNTHETIC_ROLES.values())


# --------------------------------------------------------------------------
# The market's texture: spreads, prints, holes
# --------------------------------------------------------------------------
def test_spreads_are_wider_at_the_open_than_at_the_close(synthetic_tape):
    """The shape behind SD-4 — the closing bar is where a mid is most defensible."""
    options = synthetic_tape.options.dropna(subset=["bid", "ask"])
    spread_pct = (options["ask"] - options["bid"]) / options["mid"]
    by_hour = spread_pct.groupby(options["ts"].dt.hour).median()
    assert by_hour.loc[9] > by_hour.loc[15]


def test_most_option_bars_never_print(synthetic_tape):
    """1.1's whole finding, carried into the fixture: quoted is not traded."""
    options = synthetic_tape.options
    printed = options["trdprc_1"].notna().mean()
    assert 0.2 < printed < 0.5
    quoted_not_printed = (options["mid"].notna() & options["trdprc_1"].isna()).sum()
    assert quoted_not_printed > 0


def test_some_bars_are_not_quoted_at_all_and_some_are_crossed(synthetic_tape):
    options = synthetic_tape.options
    assert options["bid"].isna().any(), "every bar is quoted — no holes at all"
    crossed = (options["ask"] < options["bid"]).sum()
    assert crossed > 0, "no crossed quote in the window (SPEC §6.1's other refusal)"
    assert options.loc[options["ask"] < options["bid"], "mid"].isna().all()


def test_every_mid_is_the_price_of_the_bar_it_sits_on(synthetic_tape, params):
    """Priced off *each bar's* spot, not one fixed level — and that is testable.

    A mutation run found this hole: pricing every bar off a single spot still
    satisfies every static bound (intrinsic below, the stock above), because each
    number stays individually plausible. What it destroys is the *relationship* —
    and the relationship is the whole reason a synthetic tape can stand in for a real
    one, since T-58 fits prints against mids and T-57's fills read the option and the
    stock at the same bar.

    So the mid is recomputed here from the tape's own stock column and the documented
    vol, and must match to the cent the quote was rounded at. Correlation was the
    first attempt and is too blunt: cent rounding and the injected holes drag it to
    0.68 on a deep-OTM contract that is behaving perfectly.
    """
    options = synthetic_tape.options.dropna(subset=["mid"])
    spot = options["ts"].map(synthetic_tape.stock.set_index("ts")["trdprc_1"])
    expiry_close = pd.to_datetime(
        [dt.datetime.combine(e, dt.time(16)) for e in options["expiry"]]
    ).tz_localize(params.tz)
    life = expiry_close - pd.DatetimeIndex(options["ts"])
    years = life.total_seconds() / (365 * 24 * 3600)

    expected = [
        bs_price(s_, k, max(t, 0.0), tape_mod.SYNTHETIC_SIGMA, cp="C")
        for s_, k, t in zip(spot, options["strike"], years)
    ]
    off_the_floor = np.array(expected) > 0.10      # below it, the penny floors bind
    error = (options["mid"].to_numpy() - np.array(expected))[off_the_floor]
    assert len(error) > 1000, "too few priced bars to conclude anything"
    assert np.abs(error).max() <= 0.02, (
        f"a mid is {np.abs(error).max():.4f} away from the Black-Scholes price of its "
        "own bar — the option is not priced off the spot beside it"
    )


def test_a_mid_is_never_inconsistent_with_the_underlying_beside_it(synthetic_tape, params):
    """Priced off the bar's own spot, so intrinsic value is never violated.

    T-58's evidence and T-57's invariants read the option and the stock together; a
    fixture where a call trades below intrinsic would make either of them look broken.
    """
    options = synthetic_tape.options.dropna(subset=["mid"])
    spot_by_ts = synthetic_tape.stock.set_index("ts")["trdprc_1"]
    spot = options["ts"].map(spot_by_ts)
    intrinsic = (spot - options["strike"]).clip(lower=0.0)
    slack = (options["ask"] - options["bid"]) / 2 + 0.02
    assert (options["mid"] >= intrinsic - slack).all(), "a call priced below intrinsic"
    assert (options["mid"] <= spot).all(), "a call worth more than the stock"


# --------------------------------------------------------------------------
# The loader's fallback (AD-1, AD-7)
# --------------------------------------------------------------------------
def test_the_loader_falls_back_to_the_synthetic_tape_and_says_so_loudly(tmp_path):
    with pytest.warns(RuntimeWarning, match="synthetic"):
        tape = load_tape(tmp_path / "absent.parquet")
    assert tape.synthetic is True


def test_the_fallback_can_be_refused_by_a_caller_that_wants_the_real_tape(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_tape(tmp_path / "absent.parquet", fallback=False)


def test_offline_does_not_mean_synthetic_when_a_tape_is_committed(monkeypatch, tmp_path):
    """CI sets OSL_OFFLINE on every build. If that meant "synthesize", the page would
    be built from a shape — and the publish guard would then refuse the deploy."""
    path = tmp_path / "t.parquet"
    synthesize_tape(FIXTURE_END_DATE, weeks=3).bars[BAR_COLUMNS].to_parquet(path, index=False)
    monkeypatch.setenv("OSL_OFFLINE", "1")
    with warnings.catch_warnings():
        warnings.simplefilter("error")          # no fallback warning may fire
        tape = load_tape(path)
    assert len(tape.bars) > 0
    assert tape.synthetic is True               # no sidecar: unlabelled reads as dangerous


def test_the_loader_never_touches_assignment_11s_cache(synthetic_tape):
    assert "option_pipeline_data" not in str(tape_mod.TAPE_PATH)
    assert np.isnan(synthetic_tape.stock["strike"]).all()


# --------------------------------------------------------------------------
# T-81 — what the adversarial review found in this generator
# --------------------------------------------------------------------------
@pytest.mark.parametrize("weeks", [3, 4, 6, 8, 9, 12, 14])
def test_the_window_always_ends_on_end_date_whatever_weeks_is(weeks):
    """A role used to trim the LAST week before the end_date clip.

    `weeks=8` ending on a Friday quietly produced a tape ending on the Thursday, and
    one combination produced a week with no sessions that vanished from the tape
    entirely. The last week anchors the window and now carries no pathology.
    """
    tape = synthesize_tape(FIXTURE_END_DATE, weeks=weeks)
    assert max(tape.stock["ts"]).date() == FIXTURE_END_DATE
    assert tape.meta["window"][1] == str(FIXTURE_END_DATE)
    assert len(tape.weeks(Params())) == weeks


def test_a_window_too_short_for_its_roles_says_which_it_dropped():
    """Silence here would let a test pass for want of the case, not for handling it."""
    short = synthesize_tape(FIXTURE_END_DATE, weeks=4)
    dropped = short.meta["diagnostics"]["dropped_roles"]
    assert "no_quote_at_entry" in dropped and "short_week" in dropped
    full = synthesize_tape(FIXTURE_END_DATE, weeks=12)
    assert full.meta["diagnostics"]["dropped_roles"] == []


def test_the_fixture_window_drops_no_role(synthetic_tape):
    assert synthetic_tape.meta["diagnostics"]["dropped_roles"] == []


def test_killing_a_quote_changes_the_bid_and_nothing_else():
    """A zero bid is a missing bid, not a mispriced contract.

    The kill used to be applied before the bar's print was drawn, so the fixture's
    canonical DR-1 bar carried a trade at about half the contract's Black-Scholes
    value — a bar that reads as a pricing error rather than a one-sided quote, on the
    exact row T-58's fit and T-57's skip path both look at.

    Driven at the row level with the SAME seed on both sides, which also pins the other
    half of the fix: the number of rng draws must not depend on the data, or every bar
    after a killed one would shift.
    """
    fields = dict(ts=pd.Timestamp("2026-09-11 15:00", tz=Params().tz), hour=15,
                  spot=700.0, strike=700.0, t_years=7 / 365,
                  expiry=dt.date(2026, 9, 11), params=Params())
    # Seed 0 is chosen because its bar PRINTS. With a seed whose bar does not print,
    # both sides are NaN and the comparison below passes without testing anything —
    # the vacuity this whole review pass was about.
    honest = tape_mod._synthetic_option_row(
        **fields, rng=np.random.default_rng(0), kill_quote=False)
    killed = tape_mod._synthetic_option_row(
        **fields, rng=np.random.default_rng(0), kill_quote=True)

    assert not pd.isna(honest["trdprc_1"]), (
        "the fixture bar must print, or this proves nothing"
    )
    assert killed["bid"] == 0.0 and honest["bid"] > 0
    assert killed["ask"] == honest["ask"]
    for column in ("trdprc_1", "volume", "num_moves"):
        a, b = honest[column], killed[column]
        assert (pd.isna(a) and pd.isna(b)) or a == b, (
            f"{column} moved with the killed bid"
        )


def test_the_killed_bar_is_the_one_the_rule_would_have_chosen(
    synthetic_tape, role_weeks, params
):
    """And it is on the entry bar of the week that names the role (SPEC §3.4)."""
    week = role_weeks["no_quote_at_entry"]
    bar, spot, chain, strike, mid = _entry(synthetic_tape, week, params)
    row = synthetic_tape.options[(synthetic_tape.options["ts"] == bar)
                                 & (synthetic_tape.options["strike"] == strike)
                                 & (synthetic_tape.options["expiry"] == week.expiry_day)]
    assert len(row) == 1
    assert float(row["bid"].iloc[0]) == 0.0
    assert float(row["ask"].iloc[0]) > 0, "the ask was collateral damage"
    assert pd.isna(row["mid"].iloc[0]), "valid_mid accepted a zero bid"


def test_every_synthetic_week_has_at_least_one_session():
    """The property the generator's ValueError enforces, over a wide sweep.

    The raise itself is unreachable by construction now that the last week carries no
    role — it is insurance for whoever adds the next pathology.
    """
    for weeks in (2, 3, 5, 8, 12, 16):
        for end in (dt.date(2026, 9, 11), dt.date(2026, 9, 7), dt.date(2026, 3, 4)):
            for index, role, days in tape_mod._synthetic_weeks(end, weeks):
                assert days, f"weeks={weeks} end={end}: week {index} ({role}) is empty"


# --------------------------------------------------------------------------
# The committed artifact itself — offline, and skipped where it is absent
# --------------------------------------------------------------------------
def test_the_committed_tape_reconciles_against_its_own_sidecar(real_tape):
    """The real 37,857-bar artifact had no test at all until T-81 pointed it out."""
    meta = real_tape.meta
    assert meta["synthetic"] is False
    assert meta["n_bars"] == len(real_tape.bars)
    answered = {(p["expiry"], p["strike"]) for p in
                map(parse_option_ric, real_tape.options["ric"].unique()) if p}
    requested = {(p["expiry"], p["strike"]) for p in
                 map(parse_option_ric, meta["diagnostics"]["requested"]) if p}
    assert answered <= requested, "the tape holds contracts the pull never asked for"
    assert meta["n_contracts"] == len(real_tape.options["ric"].unique())


def test_the_committed_tape_has_a_closing_bar_for_every_week(real_tape, params):
    """What the engine will actually ask of it (T-57), asserted before T-57 exists."""
    weeks = real_tape.weeks(params)
    assert len(weeks) == 10
    for week in weeks:
        assert entry_bar_ts(real_tape.stock["ts"], week.entry_day, params) is not None
        assert closing_bar_ts(real_tape.stock["ts"], week.expiry_day, params) is not None
