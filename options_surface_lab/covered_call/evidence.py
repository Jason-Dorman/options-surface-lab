"""FR-17's evidence — how far the mid the backtest fills at sits from a real print.

One module, one reason to change: this is the only place that makes a *statement
about the tape*. ``rules`` holds what the strategy decides, ``engine`` holds the
book those decisions produce, and neither knows this module exists. It was written
inside ``rules`` and lifted out on the PO's instruction (2026-09-16) — SOLID over
convenience, and AD-12's module list amended to match. The cohesion argument for
leaving it there was real (SPEC §10's sample *is* §6.1's valid quote, and the whole
section exists to justify §6.2's fill) but it made ``rules`` the one module in the
package with two reasons to change: a strategy decision, and a statistic.

Specified by SPEC-COVERED-CALL §10. Pure: no network, no clock, no I/O, no plotly,
no theme (AD-12, NFR-5).

**Layering.** Imports ``rules`` for :class:`~.rules.Params` and the money rounding;
is imported by ``plots``/``page`` and by the notebook. Nothing here may import
``engine`` — the book is derived from the blotter, the evidence from the tape, and
the two must be able to disagree. That is what makes the fit a check on the fill
assumption rather than a restatement of it.

**The refusals are half the claim** (the AD-9 posture FR-11's ``iv_refusal``
established). Every option bar the window holds is either in the sample or in
exactly one named bucket, and the tally reconciles against the bars considered: a
count that does not add up is indistinguishable from a sample quietly dropping
rows, and it reaches a doc as a number an operator then "checks" (T-77).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from .rules import (
    CLOSING_BAR_HOUR_ET,
    MONEY_DP,
    Params,
    require_matching_underlying,
)

if TYPE_CHECKING:  # pragma: no cover - type-only; `tape` imports `rules`, never back
    from .tape import Tape


#: Fewest points that make an OLS line a statement about the market. Two points
#: fit exactly and report R² = 1, which is a fact about arithmetic.
MIN_FIT_POINTS = 3

#: Why an option bar in the window is not in the sample, in **attribution order**:
#: a bar failing several tests is counted once, under the first. That is what lets
#: the counts plus ``n`` reconcile against the bars considered — a test checks the
#: sum, because a refusal tally that does not add up is how a silently dropped
#: sample looks from the outside (T-77).
#:
#: The order is *structure, then market*. A bar that is not a call, has no strike,
#: or is a post-close stub is refused before anything is asked about its quote,
#: because none of those is a fact about the market — and a bucket must never name
#: a fact that is not true of the row it counts. T-83's review found a strikeless
#: bar filed under ``outside_band``, i.e. reported as having sat outside a band it
#: had no position relative to; ``no_strike`` exists so the tally stays honest
#: (AD-9: what was refused is *named*).
#:
#: Among the market buckets the band comes **before** the quote and the print
#: deliberately. It is the sample universe, not a failure: refusing it first makes
#: the tally answer the question FR-17 actually asks — *in the band the strategy
#: writes in, how often is there a print to compare the mid against?* Ordered the
#: other way, ``no_print`` counts every deep-OTM contract nobody was ever going to
#: trade and says nothing.
REFUSAL_ORDER = ("not_a_call", "no_strike", "post_close", "no_spot",
                 "outside_band", "no_quote", "no_print")

#: The columns of :attr:`MidVsPrint.points`, in order. Fixed so the frame the page
#: renders and the frame the notebook reads are the same table.
EVIDENCE_COLUMNS = ["ts", "ric", "expiry", "strike", "cp", "spot", "moneyness",
                    "bid", "ask", "mid", "trdprc_1", "gap", "abs_gap", "gap_pct"]

#: SPEC §10's caveat, in one place so the page and the notebook cannot state it
#: differently. Same posture as ``describe_strike_rule``: prose the transform owns,
#: because it is a statement about the method, not the PO's reading of the result
#: (FR-19's prose is ``writeup.py``'s, and is the PO's alone).
NON_SIMULTANEITY_CAVEAT = (
    "Within an hourly bar the print is the last trade and the quote is the last "
    "bid and ask reported in that bar, so a point is not a simultaneous pair. "
    "This is the honest measure of how far a mid sits from a real print at hourly "
    "resolution — the resolution the backtest fills at — not a claim that the two "
    "were observed at the same instant."
)


@dataclass(frozen=True)
class MidVsPrint:
    """FR-17's evidence: the near-the-money sample, the OLS fit, and what it refused.

    ``points`` is the primary artifact and everything else is computed from it, the
    same way the blotter stands to the ledger (SPEC §1): every number on the page
    has a row behind it. ``refusals`` is not diagnostic residue — it is the other
    half of the claim. "R² = 0.99" means nothing until you know how many bars the
    window held and why the rest are absent; that is the AD-9 posture FR-11's
    ``iv_refusal`` established for the IV surface, applied to a fit.

    A fit that cannot be made is ``NaN``, never a line through two points — see
    :data:`MIN_FIT_POINTS`.
    """

    points: pd.DataFrame
    band: float
    considered: int
    n: int
    slope: float
    intercept: float
    r2: float
    median_gap: float
    median_gap_pct: float
    refusals: dict
    #: Where the numbers came from. A fit carries its provenance or it is not
    #: evidence: on a machine with no committed parquet, ``load_tape`` falls back to
    #: the seeded generator (AD-7) and this transform then reports the generator's
    #: own planted relationship — ``print = mid + N(0, spread/3)`` — as a *better*
    #: headline than the real tape's, in a shape nothing could tell apart. T-83's
    #: completeness critic found the record dropping ``Tape.synthetic`` on the floor.
    #: SPEC §11's publish guard refuses a synthetic page; it needs this bit to do it.
    synthetic: bool = True
    underlying: str = ""
    start: dt.date | None = None
    end: dt.date | None = None

    #: ``median_gap`` measures ``|print - mid|`` — the distance from ``y = x``, which
    #: is the number FR-17 asks for, because that is the error the backtest actually
    #: books when it fills at the mid. It is **not** the fit's residual: a sample
    #: that sat exactly on ``print = 0.6 x mid + 1.25`` would have a perfect R² and a
    #: median gap of over a dollar. The two answer different questions and the page
    #: prints both.

    @property
    def fitted(self) -> bool:
        """True when a line was actually estimated. False means the numbers are NaN."""
        return bool(self.n) and not pd.isna(self.slope)

    def fit_y(self, x):
        """The fitted line at ``x`` — what T-69's figure draws beside ``y = x``.

        ``None`` when there is no fit, so a caller cannot draw a line that was
        never estimated.
        """
        if not self.fitted:
            return None
        return [self.intercept + self.slope * float(value) for value in x]

    def headline(self) -> str:
        """FR-17's numbers in one sentence, with the sample they were measured on.

        The row set travels with the number, every time. T-17 learned that on OQ-2:
        vol shifts quoted from three different subsets landed across the docs and
        the code, and not one of them was checkable.

        **The dollar and the percentage are two medians of two different variables**,
        and the sentence says so rather than writing "$0.035 (1.89% of the mid)" —
        which invites the reader to divide and infer a median mid of $1.85. The real
        median mid is $4.75. T-83's review caught the phrasing in five documents.
        """
        warning = "" if not self.synthetic else (
            "SYNTHETIC TAPE — these numbers are the fixture generator's planted "
            "relationship, not the market's. "
        )
        if not self.fitted:
            return (
                f"{warning}No fit: {self.n} near-the-money bars carried both a valid "
                f"quote and a print, of {self.considered} option bars in the window "
                f"(band ±{self.band:.0%}); {MIN_FIT_POINTS} are needed."
            )
        return (
            f"{warning}n = {self.n} of {self.considered} {self.underlying} option "
            f"bars in the window, near the money (±{self.band:.0%} of spot), "
            f"regular session only: "
            f"print = {self.slope:.4f} × mid + {self.intercept:.4f}, "
            f"R² = {self.r2:.4f}; median |print − mid| = ${self.median_gap:.3f}; "
            f"median of |print − mid| / mid = {self.median_gap_pct:.2f}%."
        )

    def describe(self) -> str:
        """The headline, the refusal tally, and the tally's own arithmetic.

        The line **shows the sum** rather than leaving it to be trusted. §10's stated
        reason for the tally is that a count which does not add up is
        indistinguishable from a sample quietly dropping rows — and the artifact an
        operator actually reads is this string, which until T-83 was the one with no
        arithmetic behind it. It also indexes ``refusals`` directly: the old
        ``.get(name, 0)`` printed a confident zero for a bucket that did not exist,
        so a mistyped key rendered as a real measurement (T-77's "952 + 150 = 1,102"
        in a new place).
        """
        tally = ", ".join(f"{name} {self.refusals[name]}" for name in REFUSAL_ORDER)
        total = self.n + sum(self.refusals.values())
        check = "=" if total == self.considered else "!="
        return (
            f"{self.headline()}\nRefused: {tally}."
            f"\nReconciles: {self.n} + {total - self.n} {check} {self.considered}."
        )


def _ols(x, y) -> tuple[float, float, float]:
    """Slope, intercept and R² of ``y`` on ``x``, or three ``NaN``.

    Written out rather than called from a library so its refusals are visible: too
    few points, or an ``x`` with no spread at all (every bar at one mid), and there
    is no line — not a line with an enormous standard error. R² is
    ``1 - SS_res / SS_tot``, the real quantity rather than the squared correlation
    that happens to equal it for this model; a zero ``SS_tot`` is undefined and
    says so.

    **Degeneracy is caught on the count of distinct ``x``, not on ``sxx <= 0`` and
    not on ``max == min``.** Two guards were wrong here before this one. ``sxx <= 0``
    fails because the mean of N identical floats is not exactly that float — 2,251
    copies of 12.34 leave deviations of ~1e-15, ``sxx`` lands near 1e-27, and the
    division returns a confident number from data that says nothing. ``max == min``
    then fails on its own neighbour: 2,250 identical mids plus **one** different one
    has a spread, passes, and reports ``slope = 6.0000, R² = 1.0000, fitted = True``
    from two distinct x values (T-83). Requiring :data:`MIN_FIT_POINTS` *distinct*
    x values closes both, because it is a guard on the shape of the input rather
    than on a quantity the input produced.

    It is a floor, not a conditioning test: three well-separated points still admit
    high leverage. On the committed tape the question is academic — the tightest
    slice anyone can ask for (±0.01% band, n = 57) still spans $9.76 of mid, and the
    worst single-point leverage share across all ten weeks is 0.86%.

    The distinct count also **subsumes the point count**, since ``unique(x).size`` is
    never greater than ``x.size``. A separate ``x.size < MIN_FIT_POINTS`` guard stood
    above this one until the mutation run showed it could not fail: deleting it left
    the suite green, because every array short enough to trip it trips this line
    first. Dead code that looks like a safety check is worse than no check.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    nan = float("nan")
    if np.unique(x).size < MIN_FIT_POINTS:
        return nan, nan, nan
    dx = x - x.mean()
    sxx = float((dx * dx).sum())
    if sxx <= 0:
        return nan, nan, nan
    dy = y - y.mean()
    slope = float((dx * dy).sum() / sxx)
    intercept = float(y.mean() - slope * x.mean())
    resid = y - (intercept + slope * x)
    sst = float((dy * dy).sum())
    r2 = nan if sst <= 0 else float(1.0 - (resid * resid).sum() / sst)
    return slope, intercept, r2


def mid_vs_print(tape: "Tape", params: Params | None = None, *,
                 band: float | None = None) -> MidVsPrint:
    """SPEC §10 — how close the mid the backtest fills at sits to a real print.

    The sample is every **call** bar of the **regular session** inside
    ``[params.start, params.end]`` that carries a valid quote (§6.1,
    :func:`valid_mid`), a ``trdprc_1``, and a strike within ``±band`` of that bar's
    own spot print. Near-the-money because that is where the strategy writes: a fit
    dominated by deep-OTM contracts quoted in pennies reports a flattering R² about
    bars the rule never touches.

    Every one of those words is now enforced rather than inherited from the tape.
    "Call" was true only because both tapes happen to carry no puts; "regular
    session" was not true at all until T-83 — the 16:00 ET post-close bar was 9.3%
    of the published sample.

    **Spot is the stock's print at that same bar** — not the session's close, not
    an interpolation — so the moneyness test is made of two numbers observed in one
    bar, even though the pair inside that bar is not simultaneous
    (:data:`NON_SIMULTANEITY_CAVEAT`).

    Pure: no network, no clock, no I/O. ``band`` overrides ``params.ntm_band`` for a
    sensitivity sweep in the notebook; the page always prints the ``Params`` one.
    """
    params = params or Params()
    band = params.ntm_band if band is None else float(band)
    if not 0 < band <= 1:
        raise ValueError(f"band is a fraction of spot in (0, 1], got {band!r}")

    # The same door the engine stands behind (T-82), through the same function:
    # a tape for another name yields a complete, plausible, entirely wrong headline,
    # printed beside a ``Params`` naming the underlying it was *not* measured on.
    require_matching_underlying(tape, params)

    stock = tape.stock
    if stock["ts"].duplicated().any():
        dupes = sorted(str(t) for t in stock.loc[stock["ts"].duplicated(), "ts"].unique())
        raise ValueError(
            f"the stock tape carries more than one bar at {dupes[:3]} "
            f"({len(dupes)} timestamps in all). Spot is looked up by timestamp, so a "
            "duplicate would silently band the whole sample against whichever row "
            "happened to be last."
        )

    opts = tape.options
    if "mid" not in opts.columns:
        raise ValueError(
            "this tape has no `mid` column — SPEC §6.1's valid quote is attached at "
            "load (`tape.attach_mid`). Build the Tape through `load_tape` or "
            "`synthesize_tape` rather than from a bare frame."
        )

    if opts.empty:
        sample = opts
    else:
        days = pd.DatetimeIndex(opts["ts"]).date
        sample = opts[(days >= params.start) & (days <= params.end)]
    considered = int(len(sample))

    spot_by_ts = dict(zip(stock["ts"], stock["trdprc_1"])) if not stock.empty else {}

    if considered == 0:
        points = pd.DataFrame(columns=EVIDENCE_COLUMNS)
        refusals = {reason: 0 for reason in REFUSAL_ORDER}
    else:
        spot = sample["ts"].map(spot_by_ts).astype(float)
        mid = sample["mid"].astype(float)
        printed = sample["trdprc_1"].astype(float)
        strike = sample["strike"].astype(float)
        hour = pd.DatetimeIndex(sample["ts"]).hour

        # Attribution order — REFUSAL_ORDER. Each mask excludes the ones before it,
        # so every considered bar lands in exactly one bucket, refused or kept, and
        # the tally reconciles.
        not_a_call = sample["cp"].ne("C")
        no_strike = ~not_a_call & (strike.isna() | (strike <= 0))
        # The bar whose ET start is 16:00 is *after* the option close, and the rest
        # of this package already refuses to read it: `rules.CLOSING_BAR_HOUR_ET` is
        # 15, entry and settlement go through `entry_bar_ts`/`closing_bar_ts`, and
        # `Book.daily_ledger` filters `hour <= 15`. It was 9.3% of the sample and the
        # *tightest* cohort in it — a post-close stub on a fifth of the volume,
        # flattering the number (T-83). Its spot is worse than thin: the stock tape
        # runs to 19:00 ET, so those rows were banded against an extended-hours print.
        post_close = ~not_a_call & ~no_strike & (hour > CLOSING_BAR_HOUR_ET)
        structural = not_a_call | no_strike | post_close

        moneyness = strike / spot
        no_spot = ~structural & (spot.isna() | (spot <= 0))
        # ``~(<= band)`` rather than ``> band``: a NaN moneyness is refused, not
        # kept with a hole in it. **Two known-equivalent mutants live on this line**,
        # and they are named rather than left as silent survivors of the mutation run
        # (T-57's precedent). Since ``no_strike`` now refuses a strikeless bar before
        # the band is asked about, and ``no_spot`` refuses a missing spot, nothing
        # with a NaN moneyness can reach here — so ``~(<= band)`` and ``> band``
        # agree on every reachable input. The form stays because the safe direction
        # for a NaN comparison is a property of the code, not of what happens to
        # reach it today. Likewise ``<=`` against ``<``: ``|K/S - 1|`` landing on the
        # double nearest ``band`` to the last bit is unreachable on a $1 strike
        # ladder priced against a spot with cents, so the boundary's inclusivity is
        # decided by SPEC §10's word "within" and cannot be decided by a test.
        outside_band = ~structural & ~no_spot & ~((moneyness - 1.0).abs() <= band)
        near = ~structural & ~no_spot & ~outside_band
        no_quote = near & mid.isna()
        no_print = near & ~no_quote & printed.isna()
        keep = near & ~no_quote & ~no_print

        refusals = {
            "not_a_call": int(not_a_call.sum()),
            "no_strike": int(no_strike.sum()),
            "post_close": int(post_close.sum()),
            "no_spot": int(no_spot.sum()),
            "outside_band": int(outside_band.sum()),
            "no_quote": int(no_quote.sum()),
            "no_print": int(no_print.sum()),
        }

        points = pd.DataFrame({
            "ts": sample["ts"][keep],
            "ric": sample["ric"][keep],
            "expiry": sample["expiry"][keep],
            "strike": strike[keep],
            "cp": sample["cp"][keep],
            "spot": spot[keep].round(MONEY_DP),
            "moneyness": moneyness[keep].round(6),
            "bid": sample["bid"][keep].astype(float),
            "ask": sample["ask"][keep].astype(float),
            "mid": mid[keep].round(MONEY_DP),
            "trdprc_1": printed[keep].round(MONEY_DP),
        })
        points["gap"] = (points["trdprc_1"] - points["mid"]).round(MONEY_DP)
        points["abs_gap"] = points["gap"].abs()
        points["gap_pct"] = (points["abs_gap"] / points["mid"] * 100.0).round(6)
        points = (points[EVIDENCE_COLUMNS]
                  .sort_values(["ts", "strike", "ric"], kind="mergesort")
                  .reset_index(drop=True))

    slope, intercept, r2 = _ols(points["mid"], points["trdprc_1"])
    nan = float("nan")
    return MidVsPrint(
        points=points,
        band=band,
        considered=considered,
        n=int(len(points)),
        slope=nan if pd.isna(slope) else round(slope, 6),
        intercept=nan if pd.isna(intercept) else round(intercept, 6),
        r2=nan if pd.isna(r2) else round(r2, 6),
        median_gap=round(float(points["abs_gap"].median()), MONEY_DP) if len(points) else nan,
        median_gap_pct=round(float(points["gap_pct"].median()), 4) if len(points) else nan,
        refusals=refusals,
        synthetic=tape.synthetic,
        underlying=params.underlying,
        start=params.start,
        end=params.end,
    )
