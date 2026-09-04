"""
Shared utilities for the options surface lab.

Parses LSEG/Refinitiv expired-option history into a tidy long table, and can
synthesize a realistic sparse panel when the pickle cache / LSEG session is
unavailable.

The mark/print pairing is `MARK` vs `TRDPRC_1`. `MARK` is a *slot*: US listed
equity options have no settlement price (none is published by the exchanges,
OPRA or the OCC), so it is filled by `MARK_FIELD_DEFAULT` — the quoted mid.
See docs/checkpoint_audit.md §3.
"""

from __future__ import annotations

import datetime as dt
import math
import pickle
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import griddata
from scipy.optimize import brentq
from scipy.spatial import QhullError


# OPRA month codes used in the RIC constructor in the original pipeline
CALL_MONTHS = {chr(ord("A") + i): i + 1 for i in range(12)}
PUT_MONTHS = {chr(ord("M") + i): i + 1 for i in range(12)}
MONTH_CODE_TO_CP = {**{k: "C" for k in CALL_MONTHS}, **{k: "P" for k in PUT_MONTHS}}
MONTH_CODE_TO_MONTH = {**CALL_MONTHS, **PUT_MONTHS}

# UUUUA1502600650.U   or   UUUUA1502600650.U^A26
RIC_RE = re.compile(
    r"^(?P<root>[A-Z]+)(?P<code>[A-X])(?P<day>\d{2})(?P<year>\d{2})"
    r"(?P<strike>\d{5})(?:\.U)?(?:\^[A-X]\d{2})?$",
    re.IGNORECASE,
)


def parse_option_ric(ric: str) -> dict | None:
    """Extract root, put/call, expiry, strike from an expired OPRA-style RIC."""
    text = str(ric).strip()
    m = RIC_RE.match(text)
    if not m:
        return None
    code = m.group("code").upper()
    month = MONTH_CODE_TO_MONTH.get(code)
    cp = MONTH_CODE_TO_CP.get(code)
    if month is None or cp is None:
        return None
    year = 2000 + int(m.group("year"))
    day = int(m.group("day"))
    try:
        expiry = dt.date(year, month, day)
    except ValueError:
        return None
    strike = int(m.group("strike")) / 100.0
    return {
        "ric": text,
        "root": m.group("root").upper(),
        "cp": cp,
        "expiry": expiry,
        "strike": strike,
        "month_code": code,
    }


CP_TO_MONTH_CODES = {
    "C": {month: code for code, month in CALL_MONTHS.items()},
    "P": {month: code for code, month in PUT_MONTHS.items()},
}

# The source field that fills the MARK slot. There is no settlement price for US listed
# equity options (checkpoint_audit.md §3), so this is the quoted mid — the "mechanical"
# industry derivation. THEO_VALUE is the "theoretical" alternative, deliberately not the
# default: it duplicates what our interpolated sheet already does (AD-9).
MARK_FIELD_DEFAULT = "MID_PRICE"

# Field names recognised when working out which axis of an LSEG frame holds fields
KNOWN_FIELDS = {
    "TRDPRC_1", "SETTLE", "CLOSE", "BID", "ASK",
    "MID_PRICE", "OPINT_1", "THEO_VALUE", "IMP_VOLT",
}

# Fields to try for the exchange mark, in preference order. TRDPRC_1 is the last
# trade and is never a substitute — it is listed only so a probe can prove the RIC
# is alive when every mark field comes back empty (T-27).
SETTLE_FIELD_CANDIDATES = (
    "SETTLE",
    "SETTLEMENTPRICE",
    "SETTLE_PRC",
    "OFFCL_CLOSE",
    "CF_CLOSE",
    "HST_CLOSE",
    "CLOSE",
)


def build_option_ric(
    root: str,
    expiry: dt.date,
    cp: str,
    strike: float,
    put_suffix: str = "call",
) -> str:
    """Inverse of :func:`parse_option_ric` — README RIC grammar + Appendix A::

        {ROOT}{M}{DD}{YY}{SSSSS}.U^{M}{YY}

    ``put_suffix`` selects the expired-contract suffix for **puts only**. The
    2026-08-30 pull returned 148 calls and zero puts, and the README documents no put
    example, so the suffix convention is an open question (T-27):

    ``"call"`` (default — **empirically verified 2026-08-30**)
        ``^{call letter}{yy}``: the suffix encodes the expiry *month*, so both rights
        share it. A June put is ``UUUUR122601100.U^F26`` — put letter in the body, call
        letter in the suffix. This form returned 146 puts; the README form returned none.
    ``"right"``
        ``^{put letter}{yy}`` — README's "repeats the month letter", i.e.
        ``UUUUR122601100.U^R26``. Kept so the discrepancy stays demonstrable for the
        instructor question; **it returns no data**.

    Calls are byte-identical under both settings.
    """
    cp = str(cp).upper()
    if cp not in CP_TO_MONTH_CODES:
        raise ValueError(f"cp must be 'C' or 'P', got {cp!r}")
    if put_suffix not in ("right", "call"):
        raise ValueError(f"put_suffix must be 'right' or 'call', got {put_suffix!r}")

    code = CP_TO_MONTH_CODES[cp][expiry.month]
    suffix_code = (
        code if (cp == "C" or put_suffix == "right") else CP_TO_MONTH_CODES["C"][expiry.month]
    )
    yy = f"{expiry.year % 100:02d}"
    body = f"{root.upper()}{code}{expiry.day:02d}{yy}{int(round(strike * 100)):05d}"
    return f"{body}.U^{suffix_code}{yy}"


def build_candidate_rics(
    root: str,
    expiries,
    strikes,
    rights=("C", "P"),
    put_suffix: str = "call",
) -> list[str]:
    """Every plausible RIC over the expiry x strike x right grid (AD-2).

    Over-requesting is normal: the API rejects the ones that never existed.
    """
    return [
        build_option_ric(root, expiry, cp, strike, put_suffix=put_suffix)
        for expiry in expiries
        for strike in strikes
        for cp in rights
    ]


def flatten_lseg_options(df_options: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse LSEG get_history output into a tidy table.

    LSEG may return:
      - MultiIndex columns (RIC, field)
      - MultiIndex columns (field, RIC)
      - flat columns that are just RICs (single field — not expected here)
    """
    if df_options is None or df_options.empty:
        return pd.DataFrame(
            columns=["date", "ric", "field", "value", "root", "cp", "expiry", "strike"]
        )

    frame = df_options.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.to_datetime(frame.index)

    rows = []
    cols = frame.columns

    if isinstance(cols, pd.MultiIndex):
        # Detect which level is the field name
        level_values = [set(map(str, cols.get_level_values(i))) for i in range(cols.nlevels)]
        field_level = None
        for i, vals in enumerate(level_values):
            upper = {v.upper() for v in vals}
            if upper & KNOWN_FIELDS:
                field_level = i
                break
        ric_level = 0 if field_level != 0 else 1
        if field_level is None:
            field_level = 1 if cols.nlevels > 1 else 0
            ric_level = 0 if field_level == 1 else 1

        for col in cols:
            ric = str(col[ric_level])
            field = str(col[field_level]).upper()
            series = frame[col].dropna()
            parsed = parse_option_ric(ric)
            if parsed is None:
                continue
            for ts, val in series.items():
                try:
                    num = float(val)
                except (TypeError, ValueError):
                    continue
                if not np.isfinite(num):
                    continue
                rows.append(
                    {
                        "date": pd.Timestamp(ts).normalize(),
                        "ric": ric,
                        "field": field,
                        "value": num,
                        **parsed,
                    }
                )
    else:
        # Flat columns — try "RIC | FIELD" or just RIC
        for col in cols:
            label = str(col)
            field = "TRDPRC_1"
            ric = label
            if "|" in label:
                ric, field = [p.strip() for p in label.split("|", 1)]
            elif "_" in label and label.rsplit("_", 1)[-1].upper() in {
                "TRDPRC_1",
                "SETTLE",
                "CLOSE",
                "MID_PRICE",
            }:
                # unlikely
                pass
            parsed = parse_option_ric(ric)
            if parsed is None:
                continue
            series = frame[col].dropna()
            for ts, val in series.items():
                try:
                    num = float(val)
                except (TypeError, ValueError):
                    continue
                if not np.isfinite(num):
                    continue
                rows.append(
                    {
                        "date": pd.Timestamp(ts).normalize(),
                        "ric": ric,
                        "field": str(field).upper(),
                        "value": num,
                        **parsed,
                    }
                )

    tidy = pd.DataFrame(rows)
    if tidy.empty:
        return tidy
    tidy["date"] = pd.to_datetime(tidy["date"])
    tidy["expiry"] = pd.to_datetime(tidy["expiry"])
    tidy["dte"] = (tidy["expiry"] - tidy["date"]).dt.days
    tidy = tidy[tidy["dte"] >= 0].copy()
    return tidy


def attach_underlying(tidy: pd.DataFrame, df_stock: pd.DataFrame) -> pd.DataFrame:
    """Join each option row to that day's underlying close (TRDPRC_1)."""
    if tidy.empty:
        tidy["spot"] = np.nan
        tidy["moneyness"] = np.nan
        return tidy
    if df_stock is None or df_stock.empty:
        tidy["spot"] = np.nan
        tidy["moneyness"] = np.nan
        return tidy

    stock = df_stock.copy()
    if not isinstance(stock.index, pd.DatetimeIndex):
        stock.index = pd.to_datetime(stock.index)
    close_col = "TRDPRC_1" if "TRDPRC_1" in stock.columns else stock.columns[-1]
    spot = stock[close_col].astype(float)
    spot.index = pd.DatetimeIndex(spot.index).normalize()
    tidy = tidy.copy()
    spot_map = spot.to_dict()
    tidy["spot"] = tidy["date"].map(lambda d: spot_map.get(pd.Timestamp(d).normalize(), np.nan))
    # forward-fill from nearest prior session if exact date missing
    if tidy["spot"].isna().any():
        all_dates = pd.DatetimeIndex(sorted(spot_map.keys()))
        def _nearest_spot(d):
            d = pd.Timestamp(d).normalize()
            if d in spot_map:
                return spot_map[d]
            prior = all_dates[all_dates <= d]
            if len(prior):
                return spot_map[prior[-1]]
            return np.nan
        tidy.loc[tidy["spot"].isna(), "spot"] = tidy.loc[tidy["spot"].isna(), "date"].map(_nearest_spot)

    tidy["moneyness"] = tidy["strike"] / tidy["spot"]
    return tidy


def pivot_trade_settle(tidy: pd.DataFrame, mark_field: str = MARK_FIELD_DEFAULT) -> pd.DataFrame:
    """One row per (date, ric) with TRDPRC_1 and MARK side by side.

    ``MARK`` is the *mark slot*, not a field name. US listed equity options have no official
    settlement price — none is published by the exchanges, OPRA or the OCC — so every mark is
    derived (checkpoint_audit.md §3). ``mark_field`` names which source field fills the slot;
    ``SETTLE`` is still accepted so the synthetic panel and futures-style inputs keep working.

    ``CLOSE`` maps to ``TRDPRC_1``, not to the mark: measured 2026-08-30, LSEG's close for
    these contracts is identical to the last trade in 356 of 356 overlapping observations.
    """
    if tidy.empty:
        return tidy
    to_mark = {mark_field: "MARK", "SETTLE": "MARK", "MARK": "MARK"}
    keep = tidy[tidy["field"].isin(["TRDPRC_1", "CLOSE", "BID", "ASK", *to_mark])].copy()
    keep["field"] = keep["field"].replace({"CLOSE": "TRDPRC_1", **to_mark})

    # Pivot on the true key ONLY. Descriptive columns (notably `spot`) can be NaN when the
    # stock frame does not cover an option date, and pivot_table silently drops any row with
    # NaN in its index — deleting the observation instead of showing it as a hole. That
    # violates SPEC 7.2's one-row-per-(date, ric) promise and AD-9. Re-attach the descriptors
    # by merge afterwards. (checkpoint_audit.md §1)
    values = (
        keep.pivot_table(index=["date", "ric"], columns="field", values="value", aggfunc="last")
        .reset_index()
    )
    values.columns.name = None
    desc_cols = [
        c for c in ["root", "cp", "expiry", "strike", "dte", "spot", "moneyness"]
        if c in keep.columns
    ]
    desc = keep[["date", "ric"] + desc_cols].drop_duplicates(subset=["date", "ric"], keep="last")
    wide = values.merge(desc, on=["date", "ric"], how="left")
    wide = wide[["date", "ric"] + desc_cols + [c for c in wide.columns
                                               if c not in {"date", "ric", *desc_cols}]]
    if "TRDPRC_1" not in wide.columns:
        wide["TRDPRC_1"] = np.nan
    if "MARK" not in wide.columns:
        wide["MARK"] = np.nan
    for side in ("BID", "ASK"):
        if side not in wide.columns:
            wide[side] = np.nan
    wide["has_trade"] = wide["TRDPRC_1"].notna()
    wide["has_mark"] = wide["MARK"].notna()
    wide["abs_diff"] = (wide["MARK"] - wide["TRDPRC_1"]).abs()
    wide["rel_diff"] = wide["abs_diff"] / wide["MARK"].replace(0, np.nan)

    # How far apart the two sides of the market are. This is the real liquidity measure, and
    # it is what says whether the mark is a price you could actually get: with a bid of $0.10
    # and an ask of $2.00 the mid is $1.05 and you can trade at neither. Wide spread = soft
    # mark. Matters directly for 1.2's simulated fills — filling at the mid is optimistic by
    # roughly half the spread.
    wide["spread"] = wide["ASK"] - wide["BID"]
    wide["spread_pct"] = 100.0 * wide["spread"] / wide["MARK"].replace(0, np.nan)
    return wide


def curated_asof_dates(wide: pd.DataFrame, n: int = 5, min_expiries: int = 3) -> list:
    """Pick ~``n`` as-of dates to ship in the static export (AD-5 caps the bundle).

    The published page carries every date it offers, so the count is a real cost. Two rules:
    only dates with at least ``min_expiries`` distinct expiries are eligible — fewer than that
    and the cloud is too flat to interpolate a sheet (see :func:`surface_grid`) — and the picks
    are spread evenly across those, so the dropdown shows the panel evolving over the window
    rather than five neighbouring days.
    """
    if wide is None or wide.empty or "date" not in wide.columns:
        return []

    per_date = wide.groupby(wide["date"].dt.normalize())["expiry"].nunique()
    eligible = sorted(per_date[per_date >= min_expiries].index)
    if not eligible:  # nothing rich enough — fall back to the busiest days available
        eligible = sorted(wide.groupby(wide["date"].dt.normalize()).size().nlargest(n).index)
    if len(eligible) <= n:
        return list(eligible)

    step = (len(eligible) - 1) / (n - 1) if n > 1 else 0
    picks = [eligible[int(round(i * step))] for i in range(n)]
    return sorted(dict.fromkeys(picks))


def surface_grid(points: pd.DataFrame, value_col: str, n_strike: int = 40, n_dte: int = 30):
    """
    Interpolate a sparse cloud onto a regular grid for a Plotly Surface.
    Returns None if there are too few points.
    """
    cloud = points.dropna(subset=["strike", "dte", value_col])
    if len(cloud) < 8:
        return None
    x = cloud["strike"].to_numpy(float)
    y = cloud["dte"].to_numpy(float)
    z = cloud[value_col].to_numpy(float)

    # A triangulation needs a genuinely 2-D cloud. On a single expiry every point shares one
    # DTE (and a single strike collapses the other axis), so the hull is flat and Qhull
    # raises. That is a legitimate slice of this data, not an error — the last date in a
    # weeklies panel always looks like this. Degenerate input yields no sheet, never an
    # exception (AD-9).
    if len(np.unique(x)) < 3 or len(np.unique(y)) < 2:
        return None

    xi = np.linspace(x.min(), x.max(), n_strike)
    yi = np.linspace(max(0, y.min()), y.max(), n_dte)
    XX, YY = np.meshgrid(xi, yi)
    try:
        ZZ = griddata((x, y), z, (XX, YY), method="linear")
    except (QhullError, ValueError):
        return None  # coplanar / collinear cloud that survived the checks above
    # leave holes as None so Plotly does not invent a sheet over empty wings
    return {"x": xi, "y": yi, "z": ZZ}


def summarize_sparsity(wide: pd.DataFrame) -> dict:
    """Classroom-facing counts that make the mark ≠ last-trade point (FR-6)."""
    if wide is None or wide.empty:
        return {
            "n_quotes": 0,
            "n_trade_only": 0,
            "n_mark_only": 0,
            "n_both": 0,
            "pct_mark_no_trade": 0.0,
            "median_abs_diff": None,
            "median_rel_diff_pct": None,
            "median_spread": None,
            "median_spread_pct": None,
            "pct_spread_over_half": None,
            "n_dates": 0,
            "n_series": 0,
        }
    n = len(wide)
    both = wide["has_trade"] & wide["has_mark"]
    mark_only = wide["has_mark"] & ~wide["has_trade"]
    trade_only = wide["has_trade"] & ~wide["has_mark"]
    diffs = wide.loc[both, "abs_diff"].dropna()
    rel = wide.loc[both, "rel_diff"].dropna()
    spread = wide["spread"].dropna() if "spread" in wide.columns else pd.Series(dtype=float)
    spread_pct = (
        wide["spread_pct"].dropna() if "spread_pct" in wide.columns else pd.Series(dtype=float)
    )
    return {
        "n_quotes": int(n),
        "n_trade_only": int(trade_only.sum()),
        "n_mark_only": int(mark_only.sum()),
        "n_both": int(both.sum()),
        "pct_mark_no_trade": float(100.0 * mark_only.mean()) if n else 0.0,
        "median_abs_diff": float(diffs.median()) if len(diffs) else None,
        "median_rel_diff_pct": float(100.0 * rel.median()) if len(rel) else None,
        "median_spread": float(spread.median()) if len(spread) else None,
        "median_spread_pct": float(spread_pct.median()) if len(spread_pct) else None,
        "pct_spread_over_half": (
            float(100.0 * (spread_pct >= 50).mean()) if len(spread_pct) else None
        ),
        "n_dates": int(wide["date"].nunique()),
        "n_series": int(wide["ric"].nunique()),
    }


def synthesize_demo_payload(
    ticker_root: str = "UUUU",
    ticker_stock: str = "UUUU.K",
    weeks_back: int = 12,
    seed: int = 7,
) -> dict:
    """
    Build a fake LSEG-shaped payload so the lab runs without credentials.

    Design goals (these are the teaching points):
      * SETTLE prints on most listed strikes near the money
      * TRDPRC_1 only prints on a sparse subset (ATM, near-dated)
      * When both exist they are close but not equal
    """
    rng = np.random.default_rng(seed)
    end = dt.date.today()
    start = end - dt.timedelta(weeks=weeks_back)
    bdays = pd.bdate_range(start, end)

    # Geometric-ish random walk around a $8 name (UUUU-like)
    rets = rng.normal(0.0005, 0.035, size=len(bdays))
    close = 8.0 * np.exp(np.cumsum(rets))
    close = np.clip(close, 3.5, 16.0)
    high = close * (1 + rng.uniform(0.005, 0.04, size=len(bdays)))
    low = close * (1 - rng.uniform(0.005, 0.04, size=len(bdays)))
    open_ = close * (1 + rng.normal(0, 0.01, size=len(bdays)))
    df_stock = pd.DataFrame(
        {"OPEN_PRC": open_, "HIGH_1": high, "LOW_1": low, "TRDPRC_1": close},
        index=bdays,
    )

    fridays = pd.date_range(start, end + dt.timedelta(days=40), freq="W-FRI")
    # keep a handful of expiries that overlap the window
    expiries = [d.date() for d in fridays if d.date() >= start]

    strike_step = 0.50
    records = {}
    fields = ["TRDPRC_1", "SETTLE"]

    def ric_for(expiry: dt.date, strike: float, cp: str) -> str:
        month_code = chr(ord("A") + expiry.month - 1) if cp == "C" else chr(ord("M") + expiry.month - 1)
        strike_str = f"{int(round(strike * 100)):05d}"
        base = f"{ticker_root}{month_code}{expiry.strftime('%d')}{expiry.strftime('%y')}{strike_str}.U"
        return f"{base}^{month_code}{expiry.strftime('%y')}"

    for expiry in expiries:
        dte_at_start = (expiry - start).days
        if dte_at_start < 0:
            continue
        # strike grid around the path
        path_lo = float(df_stock.loc[df_stock.index.date <= expiry, "LOW_1"].min()) if any(df_stock.index.date <= expiry) else 5.0
        path_hi = float(df_stock.loc[df_stock.index.date <= expiry, "HIGH_1"].max()) if any(df_stock.index.date <= expiry) else 12.0
        lo = np.floor((path_lo - 2) / strike_step) * strike_step
        hi = np.ceil((path_hi + 2) / strike_step) * strike_step
        strikes = np.arange(max(1.0, lo), hi + strike_step, strike_step)

        for strike in strikes:
            for cp in ("C", "P"):
                ric = ric_for(expiry, float(strike), cp)
                for field in fields:
                    records[(ric, field)] = pd.Series(index=bdays, dtype=float)

                for ts, spot in df_stock["TRDPRC_1"].items():
                    dte = (expiry - ts.date()).days
                    if dte < 0:
                        continue
                    # intrinsic + crude time value
                    intrinsic = max(spot - strike, 0.0) if cp == "C" else max(strike - spot, 0.0)
                    t_years = max(dte, 0) / 365.0
                    # rough vol-ish time value, higher when ATM
                    mny = abs(np.log(max(strike, 1e-6) / spot))
                    time_val = spot * 0.55 * np.sqrt(max(t_years, 1 / 365)) * np.exp(-3.2 * mny)
                    settle = max(intrinsic + time_val, 0.01)
                    # exchange settle is a marked price; last trade is noisier / stickier
                    trade = settle * rng.normal(1.0, 0.06) + rng.normal(0, 0.02)
                    trade = max(trade, 0.01)

                    # Liquidity mask: settle almost always exists near the money;
                    # prints only when DTE is short or the strike is close to spot.
                    near_money = mny < 0.25
                    listed = mny < 0.55 or dte < 21
                    if not listed:
                        continue
                    records[(ric, "SETTLE")].loc[ts] = round(settle, 4)

                    p_trade = 0.55 if (near_money and dte <= 21) else 0.18 if near_money else 0.04
                    if dte <= 5 and near_money:
                        p_trade = 0.8
                    if rng.random() < p_trade:
                        records[(ric, "TRDPRC_1")].loc[ts] = round(trade, 4)

    # drop empty series
    live = {k: s.dropna() for k, s in records.items() if s.notna().any()}
    if live:
        df_options = pd.concat(live, axis=1)
        df_options.columns = pd.MultiIndex.from_tuples(df_options.columns, names=["RIC", "Field"])
    else:
        df_options = pd.DataFrame()

    return {
        "stock": df_stock,
        "options": df_options,
        "ticker": ticker_root,
        "fetched_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "synthetic": True,
    }


def load_payload(cache_file: str = "option_pipeline_data.pkl") -> dict:
    """Prefer the real LSEG cache; fall back to a synthetic panel.

    Relative paths resolve against the repo root, not the CWD.
    """
    path = Path(cache_file)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    if path.exists():
        with path.open("rb") as f:
            payload = pickle.load(f)
        payload.setdefault("synthetic", False)
        return payload
    warnings.warn(
        f"{cache_file} not found — using synthetic UUUU-like options so the lab still runs.",
        RuntimeWarning,
    )
    return synthesize_demo_payload()


# ------------------------------------------------------------------ implied vol (FR-11)

# PRD OQ-2, closed by the PO on 2026-09-04: the constant risk-free rate, act/365.
# "~3-month US T-bill, mid-2026" is the citation; the number is deliberately a round one
# because it is an assumption printed on the page, not a measurement.
#
# How much it actually matters, measured on the committed panel rather than assumed.
# Over the 6,229 contract-days invertible at **both** 0% and 4%, moving r from 0% to 4%
# shifts the inverted vol by a median of **1.28 vol points**, p95 **5.69**, max **24.96**,
# on a panel whose median vol is ~86%. (State the row set: a different one — say, rows
# invertible at all of 0/2/4/6% — moves the tail figures, and quoting a number from one
# definition under the sentence of another is how this comment was wrong on first landing.)
# Small in the middle, emphatically not zero in the tails: the large shifts are deep-ITM
# contracts, where the discounted strike moves the intrinsic floor and vega is nearly zero,
# so a tiny price change maps to a huge vol change. That fragility is the point, not a
# footnote — notebook 02 §5 plots the distribution. The choice of rate is defensible; the
# sensitivity to it is a finding.
RISK_FREE_RATE = 0.04

# The bracket the solver searches: 0.01% to 500% annualised. Outside it we return a hole
# rather than a number — a "vol" of 700% on a $0.02 quote is arithmetic, not information.
IV_BOUNDS = (1e-4, 5.0)

DAYS_PER_YEAR = 365.0

# Absolute price tolerance on the no-arbitrage bounds. Quotes here are penny-grained, so
# anything this close to intrinsic carries no time value to invert.
_IV_PRICE_EPS = 1e-8


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via erf — no scipy.stats import for one function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(
    spot: float, strike: float, t_years: float, sigma: float, rate: float = RISK_FREE_RATE,
    cp: str = "C",
) -> float:
    """European Black-Scholes price, no dividends, act/365.

    Deliberately the plainest possible implementation: it exists to be inverted, and the
    round-trip test (`price -> implied_vol -> sigma`) is only meaningful if the forward
    direction is obviously right.
    """
    cp = str(cp).upper()
    disc = math.exp(-rate * t_years)
    if t_years <= 0 or sigma <= 0:
        # zero time or zero vol: the option is worth its discounted intrinsic value
        return max(spot - strike * disc, 0.0) if cp == "C" else max(strike * disc - spot, 0.0)
    vol_t = sigma * math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * t_years) / vol_t
    d2 = d1 - vol_t
    if cp == "C":
        return spot * _norm_cdf(d1) - strike * disc * _norm_cdf(d2)
    return strike * disc * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def iv_refusal(
    price: float, spot: float, strike: float, t_years: float,
    rate: float = RISK_FREE_RATE, cp: str = "C",
) -> str | None:
    """Why this row cannot be inverted, or ``None`` if it can.

    Separated from :func:`implied_vol` so the reason is available as data. The solver has to
    return a bare NaN — a figure cannot plot a sentence — but "how often, and why" is exactly
    the question FR-11's degenerate cases raise, and notebook 02 answers it by applying this
    function to the panel. Every branch here is a *hole* in the IV surface, never a fabricated
    vol (AD-9).
    """
    cp = str(cp).upper()
    # bs_price and the bounds both treat "not a call" as a put, so an unrecognised right
    # would silently come back as a put vol rather than as a hole. Refuse it by name
    # (adversarial review, 2026-09-04) — AD-9 says degrade honestly, and a vol for the wrong
    # right is a fabricated number, not a degraded one.
    if cp not in ("C", "P"):
        return f"unrecognised right {cp!r}"
    if not _finite(t_years) or t_years <= 0:
        return "expiry day — no time left to carry a vol"
    if not _finite(spot) or spot <= 0:
        return "no underlying close for that date"
    if not _finite(strike) or strike <= 0:
        return "no strike"
    if not _finite(price) or price <= 0:
        return "no mark to invert"
    lo, hi = _no_arbitrage_bounds(spot, strike, t_years, rate, cp)
    if price <= lo + _IV_PRICE_EPS:
        return "at or below intrinsic — no time value to explain"
    if price >= hi - _IV_PRICE_EPS:
        return "above the no-arbitrage cap"
    return None


def _finite(value) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _no_arbitrage_bounds(
    spot: float, strike: float, t_years: float, rate: float, cp: str
) -> tuple[float, float]:
    """(floor, cap) a European price must sit strictly inside for a vol to exist.

    Floor is the discounted intrinsic (sigma -> 0); cap is the sigma -> infinity limit: a call
    is never worth more than the stock, a put never more than its discounted strike.
    """
    disc = math.exp(-rate * t_years)
    if cp == "C":
        return max(spot - strike * disc, 0.0), spot
    return max(strike * disc - spot, 0.0), strike * disc


def implied_vol(
    price: float, spot: float, strike: float, t_years: float,
    rate: float = RISK_FREE_RATE, cp: str = "C", bounds: tuple = IV_BOUNDS,
) -> float:
    """Invert Black-Scholes for sigma, or return NaN (SYSTEM-SPEC §12).

    NaN is the whole design: a degenerate input must produce a gap in the surface, never a
    crash and never an absurd vol. :func:`iv_refusal` names the reason for the cases we can
    describe analytically; a bracket that still fails to straddle zero — or a solver that
    does not converge — falls through to the same NaN.
    """
    if iv_refusal(price, spot, strike, t_years, rate, cp) is not None:
        return float("nan")
    lo_sigma, hi_sigma = bounds

    def gap(sigma: float) -> float:
        return bs_price(spot, strike, t_years, sigma, rate, cp) - price

    try:
        if gap(lo_sigma) * gap(hi_sigma) > 0:
            return float("nan")  # the price is not reachable anywhere in the bracket
        return float(brentq(gap, lo_sigma, hi_sigma, xtol=1e-8, maxiter=100))
    except (ValueError, RuntimeError):
        return float("nan")


def attach_implied_vol(
    wide: pd.DataFrame, rate: float = RISK_FREE_RATE, price_col: str = "MARK"
) -> pd.DataFrame:
    """Add an ``iv`` column (decimal, e.g. 0.62 = 62%) to the wide table.

    Inverted on the MARK slot, because that is the price that exists on most contract-days —
    inverting the last trade would produce a vol surface as sparse as the print grid and
    would be measuring liquidity, not volatility. Rows that cannot be inverted carry NaN.
    """
    out = wide.copy()
    if out.empty:
        out["iv"] = pd.Series(dtype=float)
        return out
    t_years = out["dte"].astype(float) / DAYS_PER_YEAR
    out["iv"] = [
        implied_vol(p, s, k, t, rate, cp)
        for p, s, k, t, cp in zip(
            out[price_col], out["spot"], out["strike"], t_years, out["cp"]
        )
    ]
    return out
