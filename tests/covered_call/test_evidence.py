"""T-58 — ``covered_call/evidence.py``, the mid-vs-print fit (SPEC §10, FR-17).

The transform's whole job is to say how far the price the backtest *fills* at sits
from a price somebody actually *paid*. That makes two things load-bearing, and this
file is organised around them:

* **The fit has to be a real estimate.** A slope estimator hard-coded to 1.0 passes
  every test run against the seeded synthetic tape, because that tape plants
  ``print = mid + noise`` — slope 1, intercept 0. So the recovery tests plant a
  *different* line and demand it back (T-46: compare a thing against something it
  did not produce).
* **The refusals are half the claim.** ``n`` alone is a number without a
  denominator. Every bar the window holds is either in the sample or in exactly one
  refusal bucket, and a test adds them up — a tally that does not reconcile is what
  a silently dropped sample looks like from outside (T-77).

Both tapes are used throughout: the synthetic one has a named pathology per case,
and the committed real one is what the page will be built from. Neither exercises
``no_spot`` or (for the synthetic tape) ``outside_band`` on its own, so the tests
for those **build** the case rather than hunting for one — a branch a fixture never
reaches is a branch with no test, however many tests name it (T-57).
"""
from __future__ import annotations

import datetime as dt
import pathlib

import numpy as np
import pandas as pd
import pytest

from options_surface_lab.covered_call.evidence import (
    EVIDENCE_COLUMNS,
    MIN_FIT_POINTS,
    NON_SIMULTANEITY_CAVEAT,
    REFUSAL_ORDER,
    MidVsPrint,
    _ols,
    mid_vs_print,
)
from options_surface_lab.covered_call.rules import (
    CLOSING_BAR_HOUR_ET,
    NTM_BAND_DEFAULT,
    Params,
    valid_mid,
)
from options_surface_lab.covered_call.tape import Tape, attach_mid

# --------------------------------------------------------------------------
# Helpers — each one reads the tape, never the transform's own output
# --------------------------------------------------------------------------
def _retape(tape: Tape, bars: pd.DataFrame) -> Tape:
    """A copy of ``tape`` carrying different bars, with ``mid`` re-derived.

    Re-deriving rather than copying the column is the point: a test that edits a
    quote and keeps the old ``mid`` would be checking the transform against a
    tape that contradicts itself.
    """
    return Tape(bars=attach_mid(bars.drop(columns=["mid"])), meta=dict(tape.meta))


def _stock_print_at(tape: Tape, ts) -> float | None:
    stock = tape.stock
    hits = stock[stock["ts"] == ts]
    if hits.empty or pd.isna(hits.iloc[0]["trdprc_1"]):
        return None
    return float(hits.iloc[0]["trdprc_1"])


def _residual_std(evidence: MidVsPrint) -> float:
    """Spread of ``print - fit(mid)``, recomputed from the published points."""
    fitted = np.asarray(evidence.fit_y(evidence.points["mid"]), dtype=float)
    return float((evidence.points["trdprc_1"].to_numpy(dtype=float) - fitted).std())


def _raw_bar(tape: Tape, ric: str, ts) -> dict:
    hits = tape.bars[(tape.bars["ric"] == ric) & (tape.bars["ts"] == ts)]
    assert not hits.empty, f"{ric} has no bar at {ts}"
    return hits.iloc[0].to_dict()


@pytest.fixture(scope="session")
def synthetic_evidence(synthetic_tape, params) -> MidVsPrint:
    return mid_vs_print(synthetic_tape, params)


@pytest.fixture(scope="session")
def real_evidence(real_tape, params) -> MidVsPrint:
    return mid_vs_print(real_tape, params)


@pytest.fixture(params=["synthetic", "real"])
def case(request) -> tuple[Tape, MidVsPrint]:
    """Every structural guard runs over both tapes, with the tape it was built from.

    Resolved lazily through ``getfixturevalue`` rather than taken as arguments: the
    real tape's fixture *skips* when nothing has been pulled (conftest), and asking
    for it up front would take the synthetic arm down with it on a fresh clone.
    """
    tape = request.getfixturevalue(f"{request.param}_tape")
    return tape, request.getfixturevalue(f"{request.param}_evidence")


# ==========================================================================
# The fit is a real estimate — FR-17's acceptance criterion
# ==========================================================================
def test_the_synthetic_tapes_planted_slope_is_recovered(synthetic_evidence):
    """The generator plants ``trade = mid + noise``: slope 1, intercept 0.

    Drawn in ``tape._synthetic_option_row`` from the bar's own honest quote, with
    noise ~ N(0, max(spread/3, 0.01)) and rounded to the cent. The fit has to come
    back to that line, and the noise has to leave a visible mark: an R² of exactly
    1.0 would mean the sample had collapsed onto a single contract.
    """
    ev = synthetic_evidence
    assert ev.fitted
    assert ev.n > 500, f"only {ev.n} points — this test would assert very little"
    assert ev.slope == pytest.approx(1.0, abs=0.01), ev.headline()
    assert ev.intercept == pytest.approx(0.0, abs=0.05), ev.headline()
    assert 0.9 < ev.r2 < 1.0, ev.headline()


def test_a_different_planted_slope_is_recovered(synthetic_tape, params):
    """Plant ``print = 0.6 x mid + 1.25`` and demand exactly that back.

    This is the test the previous one cannot be: the synthetic tape's own line is
    ``y = x``, so a "slope" that returned the constant 1.0, or the ratio of the
    means, or a correlation, would pass it. Here the line is one the fixture never
    produced, the residual is zero by construction, and the estimator has nowhere
    to hide. Mutation-checked, and the result is the reason this test exists:
    replacing the slope with ``1.0``, with ``y.mean() / x.mean()`` or with
    ``corr(x, y)`` fails here (and in four other tests) while the test above it —
    the one that reads the tape's *own* planted line — passes all three.
    """
    slope, intercept = 0.6, 1.25
    bars = synthetic_tape.bars.copy()
    options = bars["kind"] == "option"
    mid = (bars["bid"] + bars["ask"]) / 2.0
    # Only where a print already exists, so the sample's membership is unchanged
    # and this test moves the *line*, not the row set.
    planted = options & bars["trdprc_1"].notna()
    bars.loc[planted, "trdprc_1"] = (intercept + slope * mid[planted]).round(4)

    ev = mid_vs_print(_retape(synthetic_tape, bars), params)
    assert ev.n > 500
    assert ev.slope == pytest.approx(slope, abs=1e-6), ev.headline()
    assert ev.intercept == pytest.approx(intercept, abs=1e-6), ev.headline()
    assert ev.r2 == pytest.approx(1.0, abs=1e-9), "an exact line is R-squared 1"


def test_noise_lowers_r_squared_without_moving_the_slope(synthetic_tape, params):
    """Symmetric noise on an exact line: same slope, strictly worse R².

    R² is the number FR-19 is asked to cite, so it has to respond to dispersion
    rather than to the fit being present. Seeded, so the assertion is reproducible.

    The residual is measured, not ``median_gap``: that column is ``|print - mid|``,
    the distance from ``y = x``, and on a planted line of slope 0.6 it is over a
    dollar before any noise is added. The first version of this test asserted the
    gap would grow and failed — correctly — because the two numbers answer
    different questions.
    """
    slope, intercept = 0.6, 1.25
    base = synthetic_tape.bars.copy()
    options = base["kind"] == "option"
    mid = (base["bid"] + base["ask"]) / 2.0
    planted = options & base["trdprc_1"].notna()
    exact = (intercept + slope * mid[planted]).round(4)

    base.loc[planted, "trdprc_1"] = exact
    clean = mid_vs_print(_retape(synthetic_tape, base), params)

    noisy_bars = base.copy()
    rng = np.random.default_rng(11)
    noisy_bars.loc[planted, "trdprc_1"] = (
        exact + rng.normal(0.0, 0.25, size=len(exact))
    ).round(4)
    noisy = mid_vs_print(_retape(synthetic_tape, noisy_bars), params)

    assert noisy.n == clean.n, "the noise must not change which bars qualify"
    assert noisy.r2 < clean.r2 - 1e-6, (clean.r2, noisy.r2)
    assert noisy.slope == pytest.approx(slope, abs=0.02)
    assert _residual_std(noisy) > _residual_std(clean) + 0.1


def test_the_fit_is_ordinary_least_squares_recomputed_by_hand(case):
    """Recompute slope, intercept and R² from ``points`` with the textbook formulas.

    The transform's own arrays are not consulted — only the frame it published, the
    one the page and the notebook read. A fit that disagreed with its own points
    would render a line through a cloud it does not describe.
    """
    _, ev = case
    x = ev.points["mid"].to_numpy(dtype=float)
    y = ev.points["trdprc_1"].to_numpy(dtype=float)
    slope = np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1)
    intercept = y.mean() - slope * x.mean()
    resid = y - (intercept + slope * x)
    r2 = 1.0 - (resid**2).sum() / ((y - y.mean()) ** 2).sum()

    assert ev.slope == pytest.approx(slope, rel=1e-6)
    assert ev.intercept == pytest.approx(intercept, abs=1e-5)
    assert ev.r2 == pytest.approx(r2, rel=1e-6)


# ==========================================================================
# The sample — every point is a pair the tape really carried
# ==========================================================================
def test_every_point_is_a_real_bar_with_a_valid_quote_and_a_print(case):
    """Each row re-read out of ``tape.bars``, by ``(ric, ts)``, not from the sample.

    T-46's rule and T-82's repair of it: a guard that looks its subject up by the
    key under test is not a guard. The bid, ask and print are checked against the
    raw bar, the mid against :func:`rules.valid_mid` — the same scalar rule the
    engine fills on, so the evidence and the book cannot disagree about what a
    quote is.
    """
    tape, evidence = case
    merged = evidence.points.merge(
        tape.bars[["ric", "ts", "kind", "cp", "bid", "ask", "trdprc_1"]],
        on=["ric", "ts"], how="left", suffixes=("", "_tape"), validate="one_to_one",
    )
    assert len(merged) == len(evidence.points), "a published point has no bar"

    assert (merged["kind"] == "option").all()
    assert (merged["cp"] == "C").all(), "SPEC §10's sample is calls"
    for column in ("bid", "ask", "trdprc_1"):
        same = np.isclose(merged[column], merged[f"{column}_tape"], equal_nan=True)
        assert same.all(), f"{(~same).sum()} rows disagree with the tape on {column}"

    # The mid through the *scalar* rule the engine fills on, row by row, so the
    # evidence and the book cannot disagree about what a quote is.
    recomputed = [valid_mid(b, a) for b, a in zip(merged["bid_tape"], merged["ask_tape"])]
    assert np.allclose(recomputed, merged["mid"]), "a published mid is not valid_mid's"
    assert np.allclose(merged["gap"], merged["trdprc_1"] - merged["mid"], atol=1e-4)
    assert np.allclose(merged["abs_gap"], merged["gap"].abs())


def test_every_points_spot_is_the_stock_print_at_that_same_bar(case):
    """Spot is read off the stock's own bar at that timestamp — not the close.

    SPEC §10 bands on the bar's own spot, and the moneyness column is what a
    reader uses to check the band by eye. If either came from another bar the
    sample would be near the money at a time that is not this one.
    """
    tape, evidence = case
    stock = tape.stock[["ts", "trdprc_1"]].rename(columns={"trdprc_1": "spot_tape"})
    merged = evidence.points.merge(stock, on="ts", how="left", validate="many_to_one")
    assert len(merged) == len(evidence.points)

    assert merged["spot_tape"].notna().all() and (merged["spot_tape"] > 0).all()
    assert np.allclose(merged["spot"], merged["spot_tape"], atol=1e-4)
    assert np.allclose(merged["moneyness"], merged["strike"] / merged["spot_tape"],
                       atol=1e-6)
    assert ((merged["moneyness"] - 1.0).abs() <= evidence.band + 1e-12).all()


def test_the_sample_stays_inside_the_window(case, params):
    """SPEC §10 fits the bars of the window, so a wider tape may not leak in."""
    _, evidence = case
    days = pd.DatetimeIndex(evidence.points["ts"]).date
    assert days.min() >= params.start
    assert days.max() <= params.end


def test_a_bar_outside_the_window_is_excluded_and_not_merely_unreachable(
    synthetic_tape, params
):
    """Narrow the window by a week: the sample shrinks and the excluded bars go.

    The fixture's tape is wider than ``Params``' window already, but a transform
    that ignored the window entirely would still pass the test above on this tape,
    because the extra bars sit *before* ``start`` where nothing else looks. Moving
    ``start`` forward makes the omission visible.
    """
    wide = mid_vs_print(synthetic_tape, params)
    later = params.__class__(**{**params.__dict__, "start": dt.date(2026, 8, 3)})
    narrow = mid_vs_print(synthetic_tape, later)

    assert narrow.n < wide.n
    assert narrow.considered < wide.considered
    assert pd.DatetimeIndex(narrow.points["ts"]).date.min() >= later.start


# ==========================================================================
# The refusals — the other half of the claim
# ==========================================================================
def test_the_refusal_tally_reconciles_with_the_bars_considered(case):
    """``n`` + every refusal == the option bars the window holds. To the row.

    The reconciliation T-77 had to learn twice: a count that does not add up is
    indistinguishable from a sample quietly dropping rows, and it reaches a doc as
    a number an operator then "checks".
    """
    _, ev = case
    assert set(ev.refusals) == set(REFUSAL_ORDER), ev.refusals
    assert ev.n + sum(ev.refusals.values()) == ev.considered, ev.describe()
    assert all(count >= 0 for count in ev.refusals.values())


def test_the_bars_considered_are_the_window_s_option_bars(case, params):
    """``considered`` counted from the tape, not from anything the transform kept."""
    tape, evidence = case
    opts = tape.options
    days = pd.DatetimeIndex(opts["ts"]).date
    expected = int(((days >= params.start) & (days <= params.end)).sum())
    assert evidence.considered == expected


def test_an_unquoted_bar_is_refused_as_no_quote_and_never_fitted(synthetic_tape,
                                                                params):
    """Blank one near-the-money bar's ask: the point leaves, ``no_quote`` gains one.

    SPEC §6.1 is the same rule the engine fills on — a one-sided quote has no
    midpoint. The count has to move by exactly one, because a transform that
    dropped the row without recording *why* would satisfy the tally test above.
    """
    before = mid_vs_print(synthetic_tape, params)
    victim = before.points.iloc[0]

    bars = synthetic_tape.bars.copy()
    hit = (bars["ric"] == victim["ric"]) & (bars["ts"] == victim["ts"])
    assert hit.sum() == 1
    bars.loc[hit, "ask"] = np.nan
    after = mid_vs_print(_retape(synthetic_tape, bars), params)

    assert after.n == before.n - 1
    assert after.refusals["no_quote"] == before.refusals["no_quote"] + 1
    assert after.refusals["no_print"] == before.refusals["no_print"]
    assert not ((after.points["ric"] == victim["ric"])
                & (after.points["ts"] == victim["ts"])).any()


def test_a_bar_with_no_print_is_refused_as_no_print(synthetic_tape, params):
    """A quoted bar nobody traded on is the commonest refusal, and it is named."""
    before = mid_vs_print(synthetic_tape, params)
    victim = before.points.iloc[0]

    bars = synthetic_tape.bars.copy()
    hit = (bars["ric"] == victim["ric"]) & (bars["ts"] == victim["ts"])
    bars.loc[hit, "trdprc_1"] = np.nan
    after = mid_vs_print(_retape(synthetic_tape, bars), params)

    assert after.n == before.n - 1
    assert after.refusals["no_print"] == before.refusals["no_print"] + 1
    assert after.refusals["no_quote"] == before.refusals["no_quote"]


def test_a_bar_whose_underlying_did_not_print_is_refused_as_no_spot(synthetic_tape,
                                                                    params):
    """Neither tape carries this case, so the test builds it (T-57's rule).

    Without a spot there is no moneyness, so the bar cannot be called near the
    money or not. Refusing it is AD-9: the alternative is to carry a spot in from
    another bar, which is exactly the invented number DR-1 forbids.
    """
    before = mid_vs_print(synthetic_tape, params)
    assert before.refusals["no_spot"] == 0, "the fixture already has one — pick another"
    victim_ts = before.points["ts"].iloc[0]
    at_ts = int((before.points["ts"] == victim_ts).sum())
    assert at_ts >= 1

    bars = synthetic_tape.bars.copy()
    blank = (bars["kind"] == "stock") & (bars["ts"] == victim_ts)
    assert blank.sum() == 1
    bars.loc[blank, "trdprc_1"] = np.nan
    after = mid_vs_print(_retape(synthetic_tape, bars), params)

    assert after.n == before.n - at_ts
    assert after.refusals["no_spot"] > 0
    assert not (after.points["ts"] == victim_ts).any()
    assert after.n + sum(after.refusals.values()) == after.considered


def test_narrowing_the_band_moves_rows_into_outside_band_and_nowhere_else(
    synthetic_tape, params
):
    """The synthetic chain sits inside ±5%, so ``outside_band`` needs building too.

    Narrowing the band may only move rows *out* of the sample and into that one
    bucket: the quote and the print of a bar do not depend on which band it is
    being judged against. A transform that re-attributed them would report a
    market that changed when the reader changed the lens.
    """
    wide = mid_vs_print(synthetic_tape, params, band=NTM_BAND_DEFAULT)
    assert wide.refusals["outside_band"] == 0, "fixture already exercises this"

    narrow = mid_vs_print(synthetic_tape, params, band=0.005)
    assert narrow.n < wide.n
    assert narrow.refusals["outside_band"] > 0
    assert narrow.considered == wide.considered
    assert narrow.n + sum(narrow.refusals.values()) == narrow.considered
    assert (narrow.points["moneyness"] - 1.0).abs().max() <= 0.005 + 1e-12

    # The structural buckets are decided before the band and may not move with it.
    for bucket in ("not_a_call", "no_strike", "post_close", "no_spot"):
        assert narrow.refusals[bucket] == wide.refusals[bucket], bucket
    # "and nowhere else" was in this test's name and in none of its assertions
    # (T-83). Band-first attribution means a narrower band takes rows *out* of
    # no_quote and no_print too; attributed the other way round those two would not
    # move, which is exactly the reorder this test is supposed to police.
    assert narrow.refusals["no_quote"] < wide.refusals["no_quote"]
    assert narrow.refusals["no_print"] < wide.refusals["no_print"]


def test_a_bar_with_no_strike_is_refused_under_its_own_name(synthetic_tape, params):
    """A strikeless bar is refused — and the bucket does not claim it sat anywhere.

    It shipped filed under ``outside_band``, which is a statement about where the
    strike was relative to spot. A bar with no strike was not anywhere. AD-9 as this
    module states it is that *what was refused is named*, so a false name is a
    defect in the tally even though the row was correctly kept out of the fit
    (T-83's review).

    The band mask stays written ``~(<= band)`` rather than ``> band`` so that a NaN
    moneyness would still be refused if one ever reached it — the safe direction for
    a NaN comparison is a property of the code, not of what currently reaches it.
    """
    before = mid_vs_print(synthetic_tape, params)
    victim = before.points.iloc[0]

    bars = synthetic_tape.bars.copy()
    hit = (bars["ric"] == victim["ric"]) & (bars["ts"] == victim["ts"])
    bars.loc[hit, "strike"] = np.nan
    after = mid_vs_print(_retape(synthetic_tape, bars), params)

    assert after.n == before.n - 1
    assert after.refusals["no_strike"] == before.refusals["no_strike"] + 1
    assert after.refusals["outside_band"] == before.refusals["outside_band"]
    assert after.points["strike"].notna().all()


# ==========================================================================
# When there is no fit, there is no fit — AD-9
# ==========================================================================
def _thinned_tape(tape: Tape, params: Params, keep: int) -> Tape:
    """The tape with all but ``keep`` of its eligible prints blanked."""
    evidence = mid_vs_print(tape, params)
    survivors = {(r["ric"], r["ts"]) for r in
                 evidence.points.head(keep).to_dict("records")}
    bars = tape.bars.copy()
    is_option = bars["kind"] == "option"
    doomed = is_option & ~pd.Series(
        [(r, t) in survivors for r, t in zip(bars["ric"], bars["ts"])],
        index=bars.index,
    )
    bars.loc[doomed, "trdprc_1"] = np.nan
    return _retape(tape, bars)


def test_too_few_points_refuse_the_fit_rather_than_drawing_a_line(synthetic_tape,
                                                                  params):
    """Two points fit exactly and report R² = 1 — a fact about arithmetic.

    So below :data:`MIN_FIT_POINTS` the numbers are NaN, ``fitted`` is False,
    ``fit_y`` hands back nothing to draw, and the headline says "No fit" instead of
    a slope. FR-11's refusals, applied to a regression.
    """
    assert MIN_FIT_POINTS == 3, "SPEC §10 pins three; this test's literals assume it"

    thin = mid_vs_print(_thinned_tape(synthetic_tape, params, keep=2), params)
    assert thin.n == 2
    assert not thin.fitted
    assert all(pd.isna(v) for v in (thin.slope, thin.intercept, thin.r2))
    assert thin.fit_y([1.0, 2.0]) is None
    assert "No fit" in thin.headline()
    assert thin.n + sum(thin.refusals.values()) == thin.considered

    # The other side of the boundary, or the comparison operator is unguarded: the
    # first version of this test sized its sample from MIN_FIT_POINTS itself, so
    # setting the constant to 2 passed it, and `<` -> `<=` passed the whole suite.
    just_enough = mid_vs_print(_thinned_tape(synthetic_tape, params, keep=3), params)
    assert just_enough.n == 3
    assert just_enough.points["mid"].nunique() == 3, (
        "the three survivors share a mid — this arm would then refuse for the "
        "degeneracy reason and report on the fixture rather than on the boundary"
    )
    assert just_enough.fitted


def test_a_sample_with_no_spread_in_the_mid_refuses_the_fit(synthetic_tape, params):
    """Every point at one mid: the slope is undefined, not infinite, not zero.

    Vertical data is the classic way an OLS helper returns a confident number from
    a division that never should have happened — and this test caught exactly that
    in the first version of ``_ols``, which refused on ``sxx <= 0``. With 2,251
    identical mids the mean is off by ~1e-15, ``sxx`` lands near 1e-27 rather than
    on zero, and the slope came back as a number. The guard is on ``max == min``
    now. Mutation-checked: restoring ``sxx <= 0`` alone fails here.
    """
    before = mid_vs_print(synthetic_tape, params)
    flat_mid = float(before.points["mid"].iloc[0])

    bars = synthetic_tape.bars.copy()
    keys = {(r["ric"], r["ts"]) for r in before.points.to_dict("records")}
    in_sample = pd.Series([(r, t) in keys for r, t in zip(bars["ric"], bars["ts"])],
                          index=bars.index)
    bars.loc[in_sample, "bid"] = flat_mid - 0.01
    bars.loc[in_sample, "ask"] = flat_mid + 0.01
    ev = mid_vs_print(_retape(synthetic_tape, bars), params)

    assert ev.n >= MIN_FIT_POINTS
    assert ev.points["mid"].nunique() == 1
    assert not ev.fitted
    assert pd.isna(ev.r2)


def test_a_sample_with_too_few_distinct_mids_refuses_even_when_it_has_a_spread():
    """N-1 identical x plus one is not a fit, and ``max != min`` cannot see that.

    The guard this replaced refused only exact equality, so 2,250 copies of one mid
    beside a single different one passed it and reported ``slope = 6.0000,
    R² = 1.0000, fitted = True`` off two distinct points — a confident line through
    a cloud that is one dot and a speck (T-83's review, found by running the public
    API, not by reading the code).

    Driven through ``_ols`` directly because the quantity under test is a property
    of the estimator, not of any tape: three arms, one per side of the rule.
    """
    many_one_other = [12.34] * 40 + [18.0]
    assert len(set(many_one_other)) == 2
    assert all(pd.isna(v) for v in _ols(many_one_other, list(range(41))))

    identical = [12.34] * 40
    assert all(pd.isna(v) for v in _ols(identical, list(range(40))))

    # Three distinct x is the floor, and it must actually fit — otherwise the fix
    # could be "refuse everything" and this file would not notice.
    slope, intercept, r2 = _ols([1.0, 2.0, 3.0], [2.0, 4.0, 6.0])
    assert (slope, intercept) == pytest.approx((2.0, 0.0))
    assert r2 == pytest.approx(1.0)
    # ...and four points with only two distinct x still refuse.
    assert all(pd.isna(v) for v in _ols([1.0, 1.0, 2.0, 2.0], [1.0, 2.0, 3.0, 4.0]))


def test_an_empty_option_tape_reports_nothing_rather_than_failing(synthetic_tape,
                                                                  params):
    """A tape with no option bars is a tape with no evidence, and says so."""
    bars = synthetic_tape.bars[synthetic_tape.bars["kind"] == "stock"].copy()
    ev = mid_vs_print(_retape(synthetic_tape, bars), params)

    assert (ev.considered, ev.n) == (0, 0)
    assert not ev.fitted
    assert list(ev.points.columns) == EVIDENCE_COLUMNS
    assert sum(ev.refusals.values()) == 0
    assert "No fit" in ev.headline()


def test_a_frame_without_a_mid_column_is_refused_at_the_door(synthetic_tape, params):
    """``mid`` is attached at load (SPEC §6.1). A tape built around it is refused.

    Silently recomputing one here would put a second implementation of "a valid
    quote" in the package, which is the drift ``tape.attach_mid``'s own test exists
    to prevent.
    """
    bare = Tape(bars=synthetic_tape.bars.drop(columns=["mid"]),
                meta=dict(synthetic_tape.meta))
    with pytest.raises(ValueError, match="mid"):
        mid_vs_print(bare, params)


# ==========================================================================
# The parameter, the numbers a reader is handed, and determinism
# ==========================================================================
def test_the_band_is_a_printed_parameter_not_a_constant(params):
    """FR-14 prints the whole ``Params``, so the band travels with the R²."""
    assert params.ntm_band == NTM_BAND_DEFAULT
    assert "ntm_band" in Params.__dataclass_fields__
    for bad in (0.0, -0.05, 1.5):
        with pytest.raises(ValueError, match="ntm_band"):
            Params(ntm_band=bad)


def test_an_explicit_band_overrides_the_parameter_and_is_validated(synthetic_tape,
                                                                   params):
    """The notebook sweeps the band; the page always prints the ``Params`` one."""
    swept = mid_vs_print(synthetic_tape, params, band=0.02)
    assert swept.band == 0.02
    assert swept.band != params.ntm_band
    for bad in (0.0, -1.0, 2.0):
        with pytest.raises(ValueError, match="band"):
            mid_vs_print(synthetic_tape, params, band=bad)


def test_the_headline_quotes_the_sample_it_was_measured_on(case):
    """Every number in the sentence, with its denominator and its band.

    T-17's OQ-2 lesson made mechanical: a fit quoted without its row set cannot be
    checked, and this project has already published three vol figures from three
    different subsets.
    """
    _, evidence = case
    line = evidence.headline()
    assert str(evidence.n) in line
    assert str(evidence.considered) in line
    assert f"{evidence.band:.0%}" in line
    assert f"{evidence.r2:.4f}" in line
    assert f"{evidence.median_gap:.3f}" in line
    assert "R" in line and "mid" in line

    described = evidence.describe()
    assert line in described
    for reason in REFUSAL_ORDER:
        assert reason in described
        assert str(evidence.refusals[reason]) in described


def test_the_median_gap_is_the_median_of_the_points_that_are_published(case):
    """Recomputed from ``points``, in dollars and as a percentage of the mid.

    The percentage is the median of the per-row ratios, not the ratio of the
    medians — the two differ, and the one the page prints has to be the one a
    reader can reproduce from the table beside it.
    """
    _, evidence = case
    gaps = (evidence.points["trdprc_1"] - evidence.points["mid"]).abs()
    assert evidence.median_gap == pytest.approx(float(gaps.median()), abs=1e-4)
    pct = (gaps / evidence.points["mid"] * 100.0).median()
    assert evidence.median_gap_pct == pytest.approx(float(pct), abs=1e-3)


def test_the_points_frame_is_the_documented_table(case):
    """Column order is a contract: T-69's figure and T-59's table both read it."""
    _, evidence = case
    assert list(evidence.points.columns) == EVIDENCE_COLUMNS
    assert evidence.points["mid"].gt(0).all()
    assert evidence.points["trdprc_1"].notna().all()
    assert evidence.points["ts"].is_monotonic_increasing


def test_the_same_tape_gives_a_byte_identical_sample(synthetic_tape, params):
    """I-12's posture for the evidence: the page and the notebook agree exactly."""
    first = mid_vs_print(synthetic_tape, params)
    second = mid_vs_print(synthetic_tape, params)
    assert first.points.to_csv(index=False) == second.points.to_csv(index=False)
    assert (first.slope, first.intercept, first.r2) == (
        second.slope, second.intercept, second.r2
    )


def test_fit_y_is_the_line_the_numbers_describe(synthetic_evidence):
    """What T-69 draws must be the fit that was reported, evaluated by hand."""
    ev = synthetic_evidence
    xs = [0.0, 1.0, 12.5]
    assert ev.fit_y(xs) == pytest.approx(
        [ev.intercept + ev.slope * x for x in xs], abs=1e-9
    )


def test_the_caveat_is_stated_once_and_claims_no_simultaneity(real_evidence):
    """SPEC §10's caveat, owned by the transform so both renderings say it.

    It also may not claim the NBBO: that claim was struck from SPEC §6.3 on
    2026-09-14 because the data does not support it for a ``.U`` RIC, and
    ``test_writeup`` already forbids the word in the PO's prose.
    """
    assert "not" in NON_SIMULTANEITY_CAVEAT
    assert "simultaneous" in NON_SIMULTANEITY_CAVEAT
    assert "NBBO" not in NON_SIMULTANEITY_CAVEAT
    assert "hourly" in NON_SIMULTANEITY_CAVEAT


# ==========================================================================
# The committed tape — the numbers the write-up and the page will quote
# ==========================================================================
def test_the_real_tape_is_the_evidence_the_write_up_cites(real_evidence, params):
    """FR-17 on ``covered_call_tape.parquet``, pinned.

    These are the numbers T-60 will quote and T-59 will render, so they are pinned
    here rather than described: if a re-pull moves them, this fails and the docs
    that quote them are updated in the same commit (the lockstep rule), instead of
    the page and the write-up drifting apart in silence.

    Read in words: across the ten-week window, of the **22,262** near-the-money
    regular-session call bars, **74.7%** carried both a valid quote and a print
    (**80.1%** of the quoted ones traded), and on those the mid sat a median **3.5
    cents** from the print — 1.89% of the mid — on a slope within a quarter of a
    percent of one. That is the justification for filling at the mid (DR-1, §6.2).

    Two phrasings were corrected here by T-83's review: 72.1% is the share of *all*
    near-the-money bars, not of the quoted ones, and the two are different numbers;
    and "a slope indistinguishable from one" is an inferential claim this sample
    rejects (t = −5.6 naive, −3.4 clustered by contract). The defensible statement
    is the size of the deviation, not its significance.
    """
    ev = real_evidence
    assert (ev.considered, ev.n) == (37_073, 16_626), ev.describe()
    assert ev.refusals == {
        "not_a_call": 0, "no_strike": 0, "post_close": 4_633, "no_spot": 0,
        "outside_band": 10_178, "no_quote": 1_492, "no_print": 4_144,
    }, ev.describe()
    assert ev.slope == pytest.approx(0.9979, abs=5e-4), ev.headline()
    assert ev.intercept == pytest.approx(0.0104, abs=5e-4), ev.headline()
    assert ev.r2 == pytest.approx(0.9962, abs=5e-4), ev.headline()
    assert ev.median_gap_pct == pytest.approx(1.89, abs=0.01), ev.headline()
    # The dollar median sits on a half-cent grid, and the 50th percentile is only
    # ~60 rows inside its block: a re-pull that moved 0.4% of the sample would step
    # it to $0.030 with nothing wrong. Pinned to the grid, not to the cent (T-83).
    assert ev.median_gap in (0.030, 0.035, 0.040), ev.headline()
    assert not ev.synthetic and ev.underlying == "QQQ.O"
    assert (ev.start, ev.end) == (params.start, params.end)


def test_the_real_tapes_entry_bars_are_in_the_sample(real_tape, real_evidence,
                                                     params):
    """Every call the book wrote is one of the points the fit was measured on.

    FR-17 exists to justify *those ten fills*, so the claim is checked contract by
    contract and bar by bar, not by timestamp: a sample that happened to contain
    some other strike at 15:00 on the same day would satisfy a looser test while
    saying nothing about the trade. All ten are present — each entry bar quoted the
    chosen strike *and* printed on it — which is what lets the write-up cite the
    R² as evidence about its own fills rather than about the chain in general.

    It also pins the couplings that are easy to break silently: nearest-OTM lands
    ~0.1% above spot on QQQ's $1 ladder (T-55), so a band narrower than that, or a
    window that clipped an entry, would empty this list.
    """
    from options_surface_lab.covered_call.engine import run_backtest

    book = run_backtest(real_tape, params)
    sells = book.blotter[(book.blotter["side"] == "SELL")
                         & (book.blotter["instrument"] != params.underlying)]
    assert len(sells) == 10, sells.to_dict("records")

    measured = set(zip(
        real_evidence.points["ric"],
        pd.to_datetime(real_evidence.points["ts"]).dt.strftime("%Y-%m-%d %H:%M"),
    ))
    missing = [(row["instrument"], row["time"]) for row in sells.to_dict("records")
               if (row["instrument"], row["time"]) not in measured]
    assert not missing, (
        f"{len(missing)} of 10 fills are absent from the evidence sample: {missing}"
    )

    # The docstring above promised these were pinned and they were not (T-83): SPEC
    # §10 and the notebook quote all four, and nothing could have caught them moving.
    keys = list(zip(real_evidence.points["ric"],
                    pd.to_datetime(real_evidence.points["ts"]).dt.strftime("%Y-%m-%d %H:%M")))
    at_fills = real_evidence.points[[k in set(zip(sells["instrument"], sells["time"]))
                                     for k in keys]]
    assert len(at_fills) == 10
    gap = at_fills["gap"].abs()
    assert gap.median() == pytest.approx(0.0375, abs=1e-4)
    assert at_fills["gap_pct"].median() == pytest.approx(0.67, abs=0.01)
    assert gap.max() == pytest.approx(0.145, abs=1e-4)
    assert (at_fills["mid"] * 100).median() == pytest.approx(644.50, abs=0.01)


# ==========================================================================
# T-83 — the guards the adversarial review showed were missing
# ==========================================================================
def _module_code_without_docstrings(module) -> str:
    """The module's executable source, docstrings removed.

    A raw-source ban list cannot be used here: ``evidence.py``'s own docstrings
    discuss ``engine`` by name, so the guard below would fail on correct code on its
    first day — which a skeptic pointed out about the obvious version of this test
    before it was written.
    """
    import ast

    tree = ast.parse(pathlib.Path(module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        head = body[0]
        if (isinstance(head, ast.Expr) and isinstance(head.value, ast.Constant)
                and isinstance(head.value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


def test_evidence_holds_no_network_no_clock_and_no_presentation():
    """AD-12's layering for the new module, as a grep over its executable source.

    It was stated in five documents and enforced nowhere. The clock is banned for
    OQ-6's reason — a transform that reads ``today()`` reports on the calendar — and
    the presentation imports because ``evidence`` sits in the transform core.
    """
    from options_surface_lab.covered_call import evidence

    code = _module_code_without_docstrings(evidence)
    for banned in ("lseg", "requests", "plotly", "theme", "read_parquet", "open(",
                   "date.today", "datetime.now", "Timestamp.now", "Timestamp.today",
                   "utcnow", "time.time"):
        assert banned not in code, f"evidence.py reaches for {banned!r}"
    assert "from .rules import" in code


def test_evidence_never_imports_the_engine_or_the_acquisition_modules():
    """The rule AD-12 was amended for, checked structurally.

    A verbatim port of ``test_engine.py``'s ban list would **not** have caught this:
    none of its substrings matches ``from .engine import run_backtest``. So the
    check is on the import graph, not on a string — and it names ``engine``
    explicitly, because that is the one import the amendment exists to forbid.

    Why it matters rather than being bookkeeping: the book is derived from the
    blotter and the evidence from the tape. If the fit could reach the engine it
    could be computed from the book, and it would restate the fill assumption
    instead of checking it.
    """
    import ast

    from options_surface_lab.covered_call import evidence

    tree = ast.parse(pathlib.Path(evidence.__file__).read_text(encoding="utf-8"))
    guarded, runtime = set(), set()
    for node in tree.body:
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Name)
                and node.test.id == "TYPE_CHECKING"):
            targets, children = guarded, node.body
        else:
            targets, children = runtime, [node]
        for child in ast.walk(ast.Module(body=children, type_ignores=[])):
            if isinstance(child, ast.ImportFrom):
                targets.add((child.module or "").lstrip("."))
            elif isinstance(child, ast.Import):
                targets.update(alias.name.lstrip(".") for alias in child.names)

    assert "engine" not in runtime and "engine" not in guarded, (
        "evidence imports engine — the fit must not be able to read the book"
    )
    for acquisition in ("tape", "live"):
        assert acquisition not in runtime, f"evidence imports {acquisition} at runtime"
    assert "tape" in guarded, "the Tape type hint should be a TYPE_CHECKING import"
    assert "rules" in runtime


def test_a_tape_for_another_underlying_is_refused(synthetic_tape, params):
    """The door the engine already stands behind (T-82), one module over.

    A foreign tape produces a complete, plausible, entirely wrong headline — and
    FR-14 prints ``Params.underlying`` on the same panel, naming the instrument the
    evidence was *not* measured on. ``mid_vs_print`` accepted one until T-83.
    """
    bars = synthetic_tape.bars.copy()
    bars.loc[bars["kind"] == "stock", "ric"] = "SPY.P"
    with pytest.raises(ValueError, match="SPY.P"):
        mid_vs_print(_retape(synthetic_tape, bars), params)


def test_a_duplicated_stock_bar_is_refused_rather_than_silently_resolved(
    synthetic_tape, params
):
    """Spot is looked up by timestamp, so a duplicate picks a row by accident.

    ``dict(zip(...))`` keeps the last, which would band the whole sample against
    whichever row the tape happened to carry second — a data-integrity failure
    laundered into ``outside_band``.
    """
    stock = synthetic_tape.bars[synthetic_tape.bars["kind"] == "stock"]
    twin = stock.iloc[[0]].copy()
    twin["trdprc_1"] = float(twin["trdprc_1"].iloc[0]) * 2
    bars = pd.concat([synthetic_tape.bars, twin], ignore_index=True)
    with pytest.raises(ValueError, match="more than one bar"):
        mid_vs_print(_retape(synthetic_tape, bars), params)


def test_a_put_is_refused_under_its_own_name(synthetic_tape, params):
    """SPEC §10 says the sample is **calls**; until T-83 that held by luck.

    Both tapes are calls-only, so no test could fail if one ever carried puts — they
    would simply have been fitted alongside. Now a put is refused into a named
    bucket, so the tally says so and the published table carries ``cp``.
    """
    before = mid_vs_print(synthetic_tape, params)
    victim = before.points.iloc[0]

    bars = synthetic_tape.bars.copy()
    hit = (bars["ric"] == victim["ric"]) & (bars["ts"] == victim["ts"])
    bars.loc[hit, "cp"] = "P"
    after = mid_vs_print(_retape(synthetic_tape, bars), params)

    assert after.n == before.n - 1
    assert after.refusals["not_a_call"] == before.refusals["not_a_call"] + 1
    assert (after.points["cp"] == "C").all()
    assert "cp" in EVIDENCE_COLUMNS


def test_the_post_close_bar_is_refused_the_way_the_rest_of_the_package_refuses_it(
    case, params
):
    """T-62's rule, which this module did not apply: 16:00 ET is after the close.

    ``rules.CLOSING_BAR_HOUR_ET`` is 15, entry and settlement go through the
    calendar helpers, and ``Book.daily_ledger`` filters ``hour <= 15`` — but FR-17's
    sample took every bar the option tape carried. On the committed tape that was
    **9.3%** of the published points, and the *tightest* cohort in it: a post-close
    stub on a fifth of the volume, flattering the number it was offered as evidence
    for. Its spot was worse than thin — the stock tape runs to 19:00 ET, so those
    rows were banded against an extended-hours print.
    """
    tape, evidence = case
    hours = pd.DatetimeIndex(evidence.points["ts"]).hour
    assert hours.max() <= CLOSING_BAR_HOUR_ET, sorted(set(hours))
    assert evidence.refusals["post_close"] > 0, (
        "no post-close bar was refused — this tape cannot exercise the guard"
    )


def test_the_record_carries_its_own_provenance(synthetic_evidence, params):
    """A fit that cannot say where it came from is not evidence.

    With no committed parquet, ``load_tape`` falls back to the seeded generator
    (AD-7) and this transform reports the generator's *planted* relationship —
    ``print = mid + N(0, spread/3)`` — as a **better** headline than the real
    tape's, in a shape nothing could tell apart. SPEC §11's publish guard refuses a
    synthetic page; it needs this bit to do it, and the record dropped it on the
    floor until T-83's completeness critic went looking.
    """
    ev = synthetic_evidence
    assert ev.synthetic is True
    assert "SYNTHETIC" in ev.headline()
    assert ev.underlying == params.underlying
    assert (ev.start, ev.end) == (params.start, params.end)


def test_describe_shows_the_arithmetic_and_refuses_a_missing_bucket(synthetic_evidence):
    """The line an operator reads is the line that must add up.

    §10's stated reason for the tally is that a count which does not add up is
    indistinguishable from a sample quietly dropping rows. The rendered string was
    the one artifact with no arithmetic behind it: ``refusals.get(name, 0)`` printed
    a confident zero for a bucket that did not exist, so a mistyped key rendered as
    a real measurement (T-77's "952 + 150 = 1,102", in a new place).
    """
    ev = synthetic_evidence
    line = ev.describe()
    assert f"= {ev.considered}" in line, line
    assert "!=" not in line, line
    for name in REFUSAL_ORDER:
        assert f"{name} {ev.refusals[name]}" in line

    broken = MidVsPrint(**{**ev.__dict__,
                           "refusals": {k: v for k, v in ev.refusals.items()
                                        if k != "no_print"}})
    with pytest.raises(KeyError):
        broken.describe()


def test_the_published_sample_is_independent_of_the_tape_s_row_order(synthetic_tape,
                                                                     params):
    """Determinism has to survive a shuffled input, or the sort is untested.

    Deleting ``sort_values`` changed nothing in the suite: both tapes already arrive
    ordered, so every assertion about determinism was really an assertion about the
    fixture. Scrambling the bars first is what gives the sort teeth.
    """
    ordered = mid_vs_print(synthetic_tape, params)
    shuffled_bars = synthetic_tape.bars.sample(frac=1.0, random_state=17)
    shuffled = mid_vs_print(_retape(synthetic_tape, shuffled_bars), params)

    assert (shuffled.points.to_csv(index=False, lineterminator="\n")
            == ordered.points.to_csv(index=False, lineterminator="\n"))
    assert shuffled.refusals == ordered.refusals


def test_a_zero_spot_is_refused_and_the_band_boundary_is_inclusive(synthetic_tape,
                                                                   params):
    """Two branches no fixture reaches, so the test builds both (T-57's rule).

    ``spot <= 0`` is half of the ``no_spot`` mask and nothing had ever exercised it;
    SPEC §10 says the sample is strikes *within* ±band, so a strike exactly on the
    boundary is kept, and nothing had exercised that either.
    """
    before = mid_vs_print(synthetic_tape, params)
    victim_ts = before.points["ts"].iloc[0]
    at_ts = int((before.points["ts"] == victim_ts).sum())

    bars = synthetic_tape.bars.copy()
    bars.loc[(bars["kind"] == "stock") & (bars["ts"] == victim_ts), "trdprc_1"] = 0.0
    zeroed = mid_vs_print(_retape(synthetic_tape, bars), params)
    assert zeroed.refusals["no_spot"] >= at_ts
    assert zeroed.refusals["outside_band"] == before.refusals["outside_band"], (
        "a zero spot was filed as 'outside the band' — it has no moneyness at all"
    )

    # ...and the boundary, from both sides. Exact equality is not asserted: a real
    # ladder is $1 steps against a spot with cents, so `|K/S - 1| == band` to the
    # last bit is unreachable, and writing a test that depends on which way
    # `spot * (1 + band) / spot` rounds would be a test about floating point rather
    # than about the rule. What SPEC §10's "within ±band" has to mean is that the
    # two sides are decided the same way every time, and that is what is pinned.
    victim = before.points.iloc[0]
    edge = float(victim["spot"]) * (1.0 + params.ntm_band)
    for factor, expected in ((1.0 - 1e-9, 1), (1.0 + 1e-9, 0)):
        edge_bars = synthetic_tape.bars.copy()
        hit = (edge_bars["ric"] == victim["ric"]) & (edge_bars["ts"] == victim["ts"])
        edge_bars.loc[hit, "strike"] = edge * factor
        edged = mid_vs_print(_retape(synthetic_tape, edge_bars), params)
        kept = edged.points[(edged.points["ric"] == victim["ric"])
                            & (edged.points["ts"] == victim["ts"])]
        assert len(kept) == expected, f"strike at {factor} x the band edge"


def test_the_band_sweep_the_docs_quote_is_pinned(real_evidence, real_tape, params):
    """SPEC §10 and BACKLOG-2 publish the sweep's range; nothing measured it.

    The published floor was **0.9960** and the true one is **0.9948** — a number
    read off the wrong row of the notebook's own five-point grid, in a commit whose
    stored output already printed 0.994843. Four lenses found it independently. It
    is pinned now, with the sweep's saturation point, because "swept ±1%…±25%"
    describes eleven identical rows above ±14% where the band stops binding.
    """
    sweep = [mid_vs_print(real_tape, params, band=i / 100) for i in range(1, 26)]
    slopes = [e.slope for e in sweep]
    r2s = [e.r2 for e in sweep]

    assert min(slopes) == pytest.approx(0.9978, abs=5e-4)
    assert max(slopes) == pytest.approx(1.0020, abs=5e-4)
    assert min(r2s) == pytest.approx(0.9948, abs=5e-4)
    assert max(r2s) == pytest.approx(0.9979, abs=5e-4)
    assert r2s.index(min(r2s)) == 1, "the R-squared floor is the ±2% band"

    saturated = [e.n for e in sweep[13:]]
    assert len(set(saturated)) == 1, "the band stops binding at ±14%"
    assert real_evidence.n < saturated[0]
