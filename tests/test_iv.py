"""FR-11's inversion, made mechanical (T-17, SYSTEM-SPEC §12).

Two things are under test here and they pull in opposite directions:

1. **The solver is right.** Black-Scholes a known sigma into a price, invert the price, get
   the sigma back. If that round trip fails, every number the IV panel shows is fiction.
2. **The solver refuses.** FR-11's acceptance criterion is that degenerate inputs produce
   *gaps* rather than errors or absurd vols, so each refusal path is asserted individually —
   the failure mode this guards against is a solver that quietly returns 4.99 for a $0.01
   quote and paints it on the surface as if it meant something.
"""

import math

import numpy as np
import pandas as pd
import pytest

from options_surface_lab.option_surface_utils import (
    DAYS_PER_YEAR,
    IV_BOUNDS,
    RISK_FREE_RATE,
    attach_implied_vol,
    bs_price,
    implied_vol,
    iv_refusal,
)

# (spot, strike, dte, sigma, cp) — spanning ITM / ATM / OTM and both rights, at the tenors
# this panel actually carries (expired weeklies: days, not years).
ROUND_TRIP_CASES = [
    (10.00, 10.00, 30, 0.45, "C"),
    (10.00, 12.50, 30, 0.85, "C"),
    (10.00, 7.50, 7, 1.20, "C"),
    (10.00, 10.00, 30, 0.45, "P"),
    (10.00, 7.50, 45, 0.90, "P"),
    (10.00, 12.50, 3, 1.50, "P"),
    (8.13, 9.00, 60, 0.62, "C"),
    (8.13, 9.00, 60, 0.62, "P"),
]


@pytest.mark.parametrize("spot,strike,dte,sigma,cp", ROUND_TRIP_CASES)
def test_a_priced_vol_inverts_back_to_itself(spot, strike, dte, sigma, cp):
    """The round trip SYSTEM-SPEC §12 asks for: price a known sigma, recover it."""
    t = dte / DAYS_PER_YEAR
    price = bs_price(spot, strike, t, sigma, RISK_FREE_RATE, cp)
    recovered = implied_vol(price, spot, strike, t, RISK_FREE_RATE, cp)
    assert recovered == pytest.approx(sigma, abs=1e-6), (
        f"{cp} S={spot} K={strike} dte={dte}: priced {price:.6f}, inverted to {recovered}"
    )


def test_the_pricer_matches_an_external_reference():
    """The one test in this file that does NOT use our own code on both sides.

    Everything else here is self-referential by design — price with `bs_price`, invert with
    `implied_vol`, check we get back what we put in — which cannot detect an error in
    `bs_price` itself: the inversion would simply undo it. Parity is a partial guard (it is
    blind to any error shared by both branches, e.g. a wrong d1). So pin both branches to
    published values: Hull, *Options, Futures and Other Derivatives*, the standard worked
    example S=42, K=40, r=10%, sigma=20%, T=0.5 -> call 4.76, put 0.81.

    Flagged by adversarial review 2026-09-04, which independently confirmed the pricer against
    scipy.stats.norm to 1.4e-14 — this makes that check permanent instead of a one-off.
    """
    assert bs_price(42.0, 40.0, 0.5, 0.20, 0.10, "C") == pytest.approx(4.76, abs=0.005)
    assert bs_price(42.0, 40.0, 0.5, 0.20, 0.10, "P") == pytest.approx(0.81, abs=0.005)


def test_the_forward_price_satisfies_put_call_parity():
    """If parity fails the pricer is wrong in a way the round trip cannot see — it would
    simply invert its own mistake back out again."""
    spot, strike, t, sigma = 10.0, 11.0, 45 / DAYS_PER_YEAR, 0.7
    call = bs_price(spot, strike, t, sigma, RISK_FREE_RATE, "C")
    put = bs_price(spot, strike, t, sigma, RISK_FREE_RATE, "P")
    assert call - put == pytest.approx(
        spot - strike * math.exp(-RISK_FREE_RATE * t), abs=1e-10
    )


def test_price_rises_monotonically_with_vol():
    """Monotonicity is what makes a single bracketed root exist at all."""
    t = 30 / DAYS_PER_YEAR
    prices = [bs_price(10.0, 10.5, t, s, RISK_FREE_RATE, "C") for s in np.linspace(0.05, 3.0, 40)]
    assert all(b > a for a, b in zip(prices, prices[1:]))


def test_zero_time_or_zero_vol_is_discounted_intrinsic():
    assert bs_price(12.0, 10.0, 0.0, 0.8, RISK_FREE_RATE, "C") == pytest.approx(2.0)
    assert bs_price(9.0, 10.0, 0.0, 0.8, RISK_FREE_RATE, "C") == 0.0
    assert bs_price(9.0, 10.0, 0.5, 0.0, RISK_FREE_RATE, "P") == pytest.approx(
        10.0 * math.exp(-RISK_FREE_RATE * 0.5) - 9.0
    )


# ------------------------------------------------------------------ the refusals (AD-9)

DEGENERATE = [
    ("expiry day", dict(price=0.50, spot=10.0, strike=10.0, t_years=0.0, cp="C")),
    ("negative time", dict(price=0.50, spot=10.0, strike=10.0, t_years=-0.1, cp="C")),
    ("no spot", dict(price=0.50, spot=float("nan"), strike=10.0, t_years=0.1, cp="C")),
    ("zero spot", dict(price=0.50, spot=0.0, strike=10.0, t_years=0.1, cp="C")),
    ("no price", dict(price=float("nan"), spot=10.0, strike=10.0, t_years=0.1, cp="C")),
    ("zero price", dict(price=0.0, spot=10.0, strike=10.0, t_years=0.1, cp="C")),
    ("negative price", dict(price=-0.25, spot=10.0, strike=10.0, t_years=0.1, cp="C")),
    ("sub-intrinsic call", dict(price=1.00, spot=12.0, strike=11.0, t_years=0.1, cp="C")),
    ("sub-intrinsic put", dict(price=0.50, spot=9.0, strike=11.0, t_years=0.1, cp="P")),
    ("call above spot", dict(price=12.50, spot=12.0, strike=11.0, t_years=0.1, cp="C")),
    ("put above strike", dict(price=11.10, spot=9.0, strike=11.0, t_years=0.1, cp="P")),
]


@pytest.mark.parametrize("label,kwargs", DEGENERATE, ids=[d[0] for d in DEGENERATE])
def test_degenerate_inputs_produce_a_hole_not_a_number(label, kwargs):
    """Every one of these is a gap in the surface. None of them may raise (AD-9)."""
    assert iv_refusal(rate=RISK_FREE_RATE, **kwargs) is not None, f"{label} should be refused"
    assert math.isnan(implied_vol(rate=RISK_FREE_RATE, **kwargs)), f"{label} must be NaN"


def test_every_refusal_names_a_reason():
    """The reason is the notebook's raw material — a bare bool would not be worth having."""
    for _label, kwargs in DEGENERATE:
        reason = iv_refusal(rate=RISK_FREE_RATE, **kwargs)
        assert isinstance(reason, str) and reason.strip()


def test_an_invertible_row_is_not_refused():
    t = 30 / DAYS_PER_YEAR
    price = bs_price(10.0, 10.5, t, 0.8, RISK_FREE_RATE, "C")
    assert iv_refusal(price, 10.0, 10.5, t, RISK_FREE_RATE, "C") is None


def test_a_vol_outside_the_bracket_is_a_hole_rather_than_a_pinned_bound():
    """A price only reachable above the bracket must come back NaN, not clamped to 5.0.

    This is the "absurd IV" half of FR-11's criterion: a penny quote on a far-dated wing can
    imply an arbitrarily large vol, and reporting 500% as though it were measured would be
    worse than reporting nothing.
    """
    t = 30 / DAYS_PER_YEAR
    hi = IV_BOUNDS[1]
    unreachable = bs_price(10.0, 10.0, t, hi * 1.5, RISK_FREE_RATE, "C")
    assert unreachable > bs_price(10.0, 10.0, t, hi, RISK_FREE_RATE, "C")
    assert math.isnan(implied_vol(unreachable, 10.0, 10.0, t, RISK_FREE_RATE, "C"))


def test_the_solver_never_raises_on_garbage():
    for bad in (None, "", float("inf"), -float("inf")):
        assert math.isnan(implied_vol(bad, 10.0, 10.0, 0.1, RISK_FREE_RATE, "C"))
        assert math.isnan(implied_vol(0.5, bad, 10.0, 0.1, RISK_FREE_RATE, "C"))


# ------------------------------------------------------------------ the panel-level attach


def test_the_rate_is_the_one_the_po_signed_off():
    """PRD OQ-2, closed 2026-09-04. Pinned because it is printed on the page: if the constant
    moves, the caption and this assertion have to move together."""
    assert RISK_FREE_RATE == 0.04


def test_attach_adds_iv_without_touching_anything_else(synthetic_wide):
    out = attach_implied_vol(synthetic_wide)
    assert "iv" not in synthetic_wide.columns, "attach must not mutate its input"
    assert "iv" in out.columns
    assert list(out.columns[:-1]) == list(synthetic_wide.columns)
    assert len(out) == len(synthetic_wide)


def test_attached_vols_are_finite_and_inside_the_bracket(synthetic_wide):
    iv = attach_implied_vol(synthetic_wide)["iv"].dropna()
    assert len(iv), "the synthetic panel must invert at least some rows"
    assert iv.between(IV_BOUNDS[0], IV_BOUNDS[1]).all(), "a solved vol outside its own bracket"


def test_the_refusal_reason_agrees_with_the_solver_row_for_row(synthetic_wide):
    """The holes must be explained, not merely tolerated.

    The first version of this test asserted `named <= len(holes)`, which is true by
    construction for any input — `named` counts booleans over exactly `len(holes)` rows — so
    it verified nothing at all (adversarial review, 2026-09-04). The real contract is an
    equivalence in both directions: a row `iv_refusal` names must have no vol, and a row it
    passes must either have one or have failed to bracket. Anything else means the reason we
    would print and the value we would plot disagree.
    """
    out = attach_implied_vol(synthetic_wide)
    reasons = [
        iv_refusal(r.MARK, r.spot, r.strike, r.dte / DAYS_PER_YEAR, RISK_FREE_RATE, r.cp)
        for r in out.itertuples()
    ]
    named = pd.Series([r is not None for r in reasons], index=out.index)
    solved = out["iv"].notna()

    assert not (named & solved).any(), (
        "a row the refusal logic names as un-invertible still produced a vol — the caption "
        "would explain a hole that is not there"
    )
    assert named.any() and solved.any(), "fixture must exercise both sides"
    # The converse is one-way: passing the analytic checks does not guarantee a bracket.
    bracket_misses = int((~named & ~solved).sum())
    assert bracket_misses < 0.05 * len(out), (
        f"{bracket_misses} unexplained holes — a refusal path is missing from iv_refusal"
    )
    assert out.loc[solved, "MARK"].notna().all(), "a vol was inverted from no price"


def test_an_empty_panel_still_gets_the_column(synthetic_wide):
    out = attach_implied_vol(synthetic_wide.iloc[0:0])
    assert "iv" in out.columns and out.empty


def test_the_rate_shifts_vols_typically_a_little_and_occasionally_a_lot(synthetic_wide):
    """OQ-2's sensitivity, pinned as a *shape* rather than as "it does not matter".

    On the **committed** panel, 0% -> 4% moves the median inverted vol by 1.28 vol points but
    the 95th percentile by 5.69 and the worst row by 24.96, over the 6,229 rows invertible at
    both rates. The tail is deep-ITM contracts, where the discounted strike moves the
    intrinsic floor while vega is nearly zero — the inversion is genuinely fragile there,
    which is a finding worth keeping and not a reason to pretend the constant is free.

    This test runs on the **synthetic** fixture (AD-7: the suite must pass with no pickle), so
    it pins the *shape* — small median, heavy tail — and not those figures. An earlier
    docstring recited the committed panel's numbers here as though they were what ran, which
    read as a pin that did not exist (adversarial review, 2026-09-04). Notebook 02 §5 carries
    the real distribution, with its outputs stored.
    """
    base = attach_implied_vol(synthetic_wide, rate=0.0)["iv"]
    high = attach_implied_vol(synthetic_wide, rate=0.06)["iv"]
    both = base.notna() & high.notna()
    assert both.any()
    shift = (high[both] - base[both]).abs()
    assert shift.median() < 0.05, "the typical row must be insensitive to the rate"
    # `max > median` was the original tail assertion and is vacuous for any non-degenerate
    # sample (adversarial review, 2026-09-04). The claim worth pinning is that the tail is
    # an order of magnitude worse than the middle — that is what makes the rate a finding
    # rather than a rounding error, and it is what would break if the deep-ITM rows ever
    # stopped being inverted.
    assert shift.quantile(0.99) > 5 * shift.median(), (
        "the tail must stay far heavier than the median — that asymmetry IS the finding"
    )


def test_an_unrecognised_right_is_a_hole_not_a_put():
    """bs_price treats anything that is not 'C' as a put, so the refusal layer has to catch a
    bad right before the pricer silently answers the wrong question (adversarial review)."""
    t = 30 / DAYS_PER_YEAR
    for bad in ("X", "", "call", None):
        assert iv_refusal(0.5, 10.0, 10.0, t, RISK_FREE_RATE, bad) is not None, bad
        assert math.isnan(implied_vol(0.5, 10.0, 10.0, t, RISK_FREE_RATE, bad)), bad
    # lowercase is the same right, not a different one — it must still invert
    price = bs_price(10.0, 10.5, t, 0.8, RISK_FREE_RATE, "C")
    assert implied_vol(price, 10.0, 10.5, t, RISK_FREE_RATE, "c") == pytest.approx(0.8, abs=1e-6)
