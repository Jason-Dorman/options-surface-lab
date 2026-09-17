"""The hourly tape — FR-13. The backtest's data, pulled once and committed.

One long table, one row per (bar, instrument): the stock and the near-the-money
weekly calls of the window, at the same bar size (DR-6). Written to
``covered_call_tape.parquet`` with a JSON sidecar carrying the payload keys
(SPEC-COVERED-CALL §3.1).

Two halves, and the split is the point:

* :func:`fetch_tape` is the **only** network in this module — human-invoked once,
  per RUNBOOK §8, with Workspace running. It refuses to overwrite an existing tape
  and refuses to run at all under ``OSL_OFFLINE=1``.
* :func:`load_tape` never reaches the network under any circumstances. Tests, the
  build and CI use only this half, which is what makes NFR-4 a property of the code
  rather than a promise (AD-1).

``option_pipeline_data.pkl`` — Assignment 1.1's cache — is never read or written
here. The two datasets share nothing but the RIC grammar.

**Three things T-62 measured that this module encodes rather than assumes:**

1. **Bars are tz-naive UTC stamped at the bar's START.** The conversion to exchange
   time goes through :func:`rules.to_exchange_time`, and the stored ``ts`` is
   tz-aware exchange time. A UTC hour is never hardcoded — 15:00 ET is 19:00 UTC
   under EDT and 20:00 under EST.
2. **A contract answers to one of two RIC forms, and which one is not ours to
   predict.** Two days after expiry the 11-Sep QQQ contracts resolved only under the
   *live* form; the 04-Sep ones, nine days out, only under the caret. **Four days
   after expiry they had switched:** T-77's pull on 2026-09-15 got all 952 contracts,
   the 11-Sep week included, under the caret. So the changeover is real, it is a few
   days wide, and the same window pulled on two dates produces two different
   ``ric_form_used`` maps. Every contract is requested in both forms, whichever
   returns rows wins, and the winner is recorded per contract (SPEC §3.3).
3. **The strike step is $1.00 near the money on QQQ** — discovered, not assumed, and
   recorded as ``diagnostics.strike_step_discovered``. The band is generated on it.

What this module does *not* do: pick a bar. Which hourly bar is "the close" belongs
to :mod:`rules` and to nothing else (``max(ts)`` is a post-close stub — see that
module's docstring). The tape carries every bar it was given; the engine chooses.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..option_surface_utils import bs_price, build_option_ric, parse_option_ric
from .rules import (
    EXCHANGE_TZ,
    MIN_SESSIONS_PER_WEEK,
    Params,
    Week,
    entry_bar_ts,
    select_strike,
    to_exchange_time,
    trading_weeks,
    valid_mid,
)

#: The committed tape and its payload sidecar, anchored to ``__file__`` (never the CWD).
TAPE_PATH = Path(__file__).resolve().parents[2] / "covered_call_tape.parquet"
META_PATH = TAPE_PATH.with_name("covered_call_tape.meta.json")

#: What is requested per instrument. The first three are the tape; the rest are
#: present only when a trade printed, and are requested alongside ``TRDPRC_1`` so an
#: absent field comes back empty rather than raising (the T-27 pairing lesson).
FIELDS = ("TRDPRC_1", "BID", "ASK", "OPEN_PRC", "HIGH_1", "LOW_1", "ACVOL_UNS", "NUM_MOVES")

#: LSEG field -> the SPEC §3.1 column it fills.
FIELD_TO_COLUMN = {
    "TRDPRC_1": "trdprc_1", "BID": "bid", "ASK": "ask", "OPEN_PRC": "open",
    "HIGH_1": "high", "LOW_1": "low", "ACVOL_UNS": "volume", "NUM_MOVES": "num_moves",
}

#: The stored schema, in order (SPEC §3.1). ``mid`` is **not** here: it is derived at
#: load from ``bid``/``ask`` so the file cannot carry a mid its own quote contradicts.
BAR_COLUMNS = [
    "ts", "ric", "kind", "expiry", "strike", "cp",
    "bid", "ask", "trdprc_1", "open", "high", "low", "volume", "num_moves",
]
_NUMERIC_COLUMNS = ["strike", "bid", "ask", "trdprc_1", "open", "high", "low",
                    "volume", "num_moves"]
#: Columns holding python values rather than a pandas scalar type: a RIC string, the
#: `stock`/`option` tag, `C`/`P`, and a `datetime.date`. Declared `object`, and **pinned**
#: there by `_normalise_dtypes` — pandas 3 reads a parquet string column back as the new
#: `str` dtype, so without this a tape read off disk has a different schema from the one
#: held in memory, on the same code, purely by pandas version.
_OBJECT_COLUMNS = ["ric", "kind", "cp", "expiry"]
#: The resolution `ts` is stored and compared at. Declared, not inherited: pandas 2 forced
#: every datetime to nanoseconds, pandas 3 infers microseconds from a python `datetime`, so
#: an undeclared unit makes the stored schema a function of the pandas version that happened
#: to write it — the same class of silent, pull-dependent difference as SPEC §3.3's two RIC
#: forms. Nanoseconds because that is what the committed parquet already holds.
TS_UNIT = "ns"

#: T-62, 2026-09-13: every integer strike 710..721 returned data on QQQ weeklies;
#: 712.50 and 717.50 returned none. **Measured once, by the spike — not by the pull.**
#: `fetch_tape` writes this value into `diagnostics.strike_step_discovered` alongside
#: `strike_step_source`, which names where it came from; nothing in the pull re-derives
#: it from the chain that came back (T-81 — the key's name overstated it).
STRIKE_STEP = 1.00
#: Strikes requested either side of the week's own range, on the step above.
BAND_STEPS = 4
#: Universe size per request, with the single-RIC retry on rejection (AD-2).
BATCH_SIZE = 25

#: Recorded in the payload so a reader of the parquet knows what ``ts`` means.
TZ_CONVENTION = (
    "LSEG returns hourly bars tz-naive in UTC, stamped at the bar's START "
    "(T-62: O_SEC_OFST=0, C_SEC_OFST=3599). Stored here converted to exchange time, "
    "tz-aware. A bar labelled 15:00 covers 15:00-16:00 ET."
)


# --------------------------------------------------------------------------
# The record the rest of Assignment 2 is handed
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Tape:
    """The bars plus the payload keys. ``bars`` is the SPEC §3.1 table, exactly."""

    bars: pd.DataFrame
    meta: dict = field(default_factory=dict)

    @property
    def synthetic(self) -> bool:
        """True when the bars were generated rather than pulled (AD-7, SPEC §3.4).

        The page prints a banner and CI refuses to publish when this is set, so it
        defaults to *True* if the payload forgot to say — an unlabelled tape is
        treated as the dangerous case, not the safe one.
        """
        return bool(self.meta.get("synthetic", True))

    @property
    def stock(self) -> pd.DataFrame:
        return self.bars[self.bars["kind"] == "stock"]

    @property
    def options(self) -> pd.DataFrame:
        return self.bars[self.bars["kind"] == "option"]

    @property
    def stock_index(self) -> pd.DatetimeIndex:
        """The stock's bar timestamps — the calendar's only source (SPEC §3.2, DR-7)."""
        return pd.DatetimeIndex(sorted(self.stock["ts"].unique()))

    def weeks(self, params: Params) -> list[Week]:
        """The trading weeks, read off the stock tape. Short weeks included, flagged."""
        return trading_weeks(self.stock_index, params)

    def strikes_for(self, expiry: dt.date) -> list[float]:
        """Every strike *listed* for that expiry, quoted at this bar or not.

        "Listed" means the contract returned at least one bar in the pull. SPEC §5
        wants the whole week's chain here, because "no strike at or above spot" and
        "the chosen strike had no quote" are different skips and must stay apart.
        """
        opts = self.options
        hits = opts[opts["expiry"] == expiry]["strike"].dropna().unique()
        return sorted(float(k) for k in hits)


# --------------------------------------------------------------------------
# load_tape() — cache-first, never the network (AD-1, NFR-4)
# --------------------------------------------------------------------------
def attach_mid(bars: pd.DataFrame) -> pd.DataFrame:
    """Add ``mid``, valid quotes only (SPEC §6.1, DR-1).

    Vectorised for the whole table, but the rule it applies is
    :func:`rules.valid_mid`'s and a test checks the two agree row by row — a
    reimplementation that drifted would put prices in the book that the scalar rule
    would have refused.
    """
    out = bars.copy()
    bid, ask = out["bid"], out["ask"]
    ok = bid.notna() & ask.notna() & (bid > 0) & (ask > 0) & (ask >= bid)
    out["mid"] = np.where(ok, (bid + ask) / 2.0, np.nan)
    return out


def load_tape(
    path: Path | str = TAPE_PATH,
    meta_path: Path | str | None = None,
    *,
    params: Params | None = None,
    fallback: bool = True,
) -> Tape:
    """Read the committed tape, else synthesize one. **Opens no session, imports no LSEG.**

    Cache-first is the graded behaviour (AD-1): this never pulls, whatever
    ``OSL_OFFLINE`` says, so the app, the tests, the build and CI cannot reach the
    network through it even by accident. ``OSL_OFFLINE`` is checked by
    :func:`fetch_tape` alone — it means *never pull*, and emphatically not *ignore the
    committed tape*: CI sets it on every build, so a loader that read it as "use the
    synthetic tape" would publish a fabricated book, which the CI guard would then
    refuse. The committed tape wins whenever it is present.

    The fallback is loud: a warning, and ``Tape.synthetic`` True so the page says so
    and CI refuses to publish it (SPEC §11). ``fallback=False`` demands the real tape
    and raises instead, for callers that would rather stop than render a shape.
    """
    path, meta_path = _target_paths(path, meta_path)
    if not path.exists():
        params = params or Params()
        if not fallback:
            raise FileNotFoundError(
                f"No tape at {path}. Run the one-time pull (RUNBOOK §8) on a machine "
                "with LSEG Workspace, then commit the parquet and its sidecar."
            )
        warnings.warn(
            f"No tape at {path} — using the synthetic tape (SPEC §3.4). It is a shape, "
            "not a market: nothing built on it may be published.", RuntimeWarning,
        )
        return synthesize_tape(params.end, params=params)
    bars = pd.read_parquet(path)
    missing = [c for c in BAR_COLUMNS if c not in bars.columns]
    if missing:
        raise ValueError(f"{path} is not a SPEC §3.1 tape — missing columns {missing}")
    bars = _normalise_dtypes(bars)
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    return Tape(bars=attach_mid(bars), meta=meta)


def _normalise_dtypes(bars: pd.DataFrame, tz: str = EXCHANGE_TZ) -> pd.DataFrame:
    """Put a read-back frame into the stored schema's dtypes, in column order.

    ``ts`` is read through UTC and converted, so a file written by some other tool
    with naive timestamps is treated as UTC — LSEG's convention — rather than being
    quietly relabelled as exchange time, which would move every bar four hours. Its
    **unit** is pinned to :data:`TS_UNIT` and the python-valued columns to `object`,
    for the same reason the timezone is: an inherited dtype is one the pandas version
    decides. Under pandas 3 a `datetime` becomes microseconds and a parquet string
    column reads back as `str`, so without these two lines the synthetic tape and a
    tape off disk carry different schemas — which is exactly what SPEC §3.4 forbids,
    and which CI caught on 2026-09-17 while this machine's pandas 2 could not see it.

    This is the **one** place the stored schema is applied. `load_tape` and
    `synthesize_tape` both pass through here, which is what lets AD-7's fallback be
    indistinguishable from a pull by construction rather than by inspection.
    """
    out = bars.copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True).dt.tz_convert(tz).dt.as_unit(TS_UNIT)
    for column in _NUMERIC_COLUMNS:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out["expiry"] = [None if pd.isna(v) else _as_date(v) for v in out["expiry"]]
    for column in _OBJECT_COLUMNS:
        # `.astype(object)` alone is not enough: pandas 3's string dtype carries `nan`
        # for a missing value, so a stock row's `cp` would come back as a float where
        # the in-memory tape holds `None`. Missing means None here, as `expiry` above.
        values = out[column]
        out[column] = values.astype(object).where(values.notna(), None)
    return out[BAR_COLUMNS].sort_values(["ts", "ric"]).reset_index(drop=True)


def _as_date(value) -> dt.date:
    return value if isinstance(value, dt.date) and not isinstance(value, dt.datetime) \
        else pd.Timestamp(value).date()


def empty_bars() -> pd.DataFrame:
    """An empty table in the stored schema — what a failed pull returns (DR-10)."""
    frame = pd.DataFrame({c: pd.Series(dtype="float64") for c in _NUMERIC_COLUMNS})
    frame["ts"] = pd.Series(dtype=f"datetime64[{TS_UNIT}, {EXCHANGE_TZ}]")
    for column in _OBJECT_COLUMNS:
        frame[column] = pd.Series(dtype="object")
    return frame[BAR_COLUMNS]


# --------------------------------------------------------------------------
# Chain construction — SPEC §3.3
# --------------------------------------------------------------------------
def strike_band(
    low: float, high: float, step: float = STRIKE_STEP, pad: int = BAND_STEPS
) -> list[float]:
    """Listed strikes to request across ``[low, high]``, padded by ``pad`` steps.

    Arithmetic is in integer hundredths, which is how the RIC grammar stores a
    strike: generating the ladder in floats accumulates a drift that eventually
    builds a RIC one cent off a real contract, and that failure is invisible — the
    request simply returns nothing.
    """
    if step <= 0:
        raise ValueError(f"strike step must be positive, got {step}")
    if not np.isfinite(low) or not np.isfinite(high) or high < low:
        raise ValueError(f"strike band needs a finite low <= high, got {low}..{high}")
    step_c = int(round(step * 100))
    lo_c = (int(np.floor(round(low * 100) / step_c)) - pad) * step_c
    hi_c = (int(np.ceil(round(high * 100) / step_c)) + pad) * step_c
    lo_c = lo_c if lo_c >= step_c else step_c      # never below the first listed strike
    return [c / 100.0 for c in range(lo_c, hi_c + step_c, step_c)]


def week_strike_band(
    stock_bars: pd.DataFrame, week: Week, step: float = STRIKE_STEP, pad: int = BAND_STEPS
) -> list[float]:
    """The week's own range, padded — not the whole window's.

    A window-wide ladder would request every strike QQQ visited in ten weeks against
    every expiry, most of which never listed. Per-week keeps the pull to the
    contracts that plausibly exist, which is also what "each contract is requested
    only for its life" means for a weekly.

    **It errs wide on purpose, and T-77's pull showed how wide.** The range comes from
    the bars' own ``LOW_1``/``HIGH_1``, and thin extended-hours bars carry erroneous
    ticks — the 2026-09-11 17:00 ET bar prints a low of 667.36 while the stock traded
    at ~715. One such tick stretches the week's band by tens of strikes, so the real
    pull asked for ~100 strikes a week and about 93% of them answered. That is the
    right failure direction: a band too wide costs requests that fail soft and are
    recorded, while a band too narrow silently omits the strike the rule needed and
    turns a tradable week into a skip. Do not "fix" it by clipping to the traded
    range without measuring what that would have excluded.
    """
    days = set(week.sessions)
    rows = stock_bars[[d in days for d in stock_bars["ts"].dt.date]]
    prices = pd.concat([rows["low"], rows["high"], rows["trdprc_1"]]).dropna()
    if prices.empty:
        return []
    return strike_band(float(prices.min()), float(prices.max()), step=step, pad=pad)


# --------------------------------------------------------------------------
# fetch_tape() — the one-time pull. The only network in this module.
# --------------------------------------------------------------------------
@contextmanager
def lseg_session():
    """Open a Workspace session for the duration of a pull, and always close it.

    The single seam, as in :mod:`live` — the import is local so that merely
    importing this module stays offline, and a test can replace this one function to
    exercise everything around it with no credentials (NFR-4). Each acquisition
    module owns its own seam rather than sharing one, so neither can open a session
    through the other (AD-12).
    """
    import lseg.data as ld

    ld.open_session()
    try:
        # Inside the try, so a refused session is still closed: open_session() can leave
        # a half-open connection behind even when the handshake failed (T-81).
        _require_open_session(ld)
        yield ld
    finally:
        ld.close_session()


def _require_open_session(ld) -> None:
    """Fail here if the session did not actually open, rather than three steps later.

    ``ld.open_session()`` does **not** raise when the handshake fails: it logs, returns,
    and leaves a *closed* session behind. Every request then fails with "Session is not
    opened", which this module would otherwise report as *no data* — the pull blaming the
    tape for what is really a desktop-side problem (2026-09-14, a handshake to a ready
    proxy that never answered). A misattributed cause costs more than the outage.
    """
    state = str(getattr(ld.session.get_default(), "open_state", "unknown"))
    if not state.endswith("Opened"):
        raise RuntimeError(
            f"LSEG session did not open (state {state}). The API proxy can be up and "
            "answering /api/status while the desktop never completes the app-key "
            "handshake — so 'Workspace is running' is not the check. Confirm Workspace "
            "is **signed in** and loading data, restart it if the handshake still hangs, "
            "then re-run. Nothing was requested and nothing was written (RUNBOOK §9)."
        )


def _history(ld, universe, fields, start, end, interval="hourly"):
    """Fail-soft ``get_history``. Returns ``(df_or_None, error_or_None)`` (DR-10)."""
    try:
        return ld.get_history(universe=list(universe), fields=list(fields),
                              start=str(start), end=str(end), interval=interval), None
    except Exception as exc:  # a guessed RIC must fail soft, never crash
        return None, f"{type(exc).__name__}: {exc}"


_EMPTY_LONG = ["ts", "ric", "field", "value"]


def _column_pieces(df: pd.DataFrame, wanted: set[str]) -> list[tuple[str, str, pd.Series]]:
    """Work out which RIC and which field every column of a history frame carries.

    LSEG varies the shape with the request — ``(RIC, field)`` either way round for a
    multi-RIC frame, a flat frame of fields for a single RIC, a flat frame of RICs
    when only one field populated. Getting this wrong loses whole instruments
    silently, which is why the requested RIC set is matched against rather than
    inferred from position.
    """
    if df.columns.nlevels == 2:
        level0 = {str(c) for c in df.columns.get_level_values(0)}
        ric_level = 0 if level0 & wanted else 1
        return [(str(col[ric_level]), str(col[1 - ric_level]), df[col]) for col in df.columns]

    columns = {str(c) for c in df.columns}
    if not columns & set(FIELDS):                      # many RICs, one field
        field_name = str(df.columns.name or "TRDPRC_1")
        return [(str(col), field_name, df[col]) for col in df.columns]
    if len(wanted) != 1:
        # Nothing in the frame says which of the requested RICs answered, and
        # attributing bars to the wrong contract is worse than losing them.
        warnings.warn(
            f"get_history returned bare field columns for {len(wanted)} RICs — "
            "cannot attribute the bars, dropping the frame.", RuntimeWarning,
        )
        return []
    only = str(next(iter(wanted)))
    return [(only, str(col), df[col]) for col in df.columns]


def _long_rows(df: pd.DataFrame | None, rics, params: Params) -> pd.DataFrame:
    """Melt any ``get_history`` shape into ``(ts, ric, field, value)``, in exchange time.

    Empty cells are dropped rather than carried as NaN: an hourly bar for a contract
    that did not quote is not a row, and a table full of empty rows would make a
    quiet week and a dead RIC look the same.
    """
    if df is None or getattr(df, "empty", True):
        return pd.DataFrame(columns=_EMPTY_LONG)

    index = to_exchange_time(df.index, params)
    out = []
    for ric, field_name, series in _column_pieces(df, {str(r) for r in rics}):
        if field_name not in FIELD_TO_COLUMN:
            continue
        values = pd.to_numeric(
            pd.Series(series.to_numpy(), index=index), errors="coerce"
        ).dropna()
        if values.empty:
            continue
        out.append(pd.DataFrame({"ts": values.index, "ric": ric,
                                 "field": field_name, "value": values.to_numpy()}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=_EMPTY_LONG)


def _attach_contract_identity(wide: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Read expiry, strike and right off each option RIC; leave them null for stock.

    The identity comes from the RIC the pull *used*, so a row can never claim a
    contract the request did not ask for — and an unparseable RIC yields nulls rather
    than a guess.
    """
    for column in ("expiry", "strike", "cp"):
        wide[column] = None
    if kind != "option":
        return wide
    parsed = [parse_option_ric(r) for r in wide["ric"]]
    wide["expiry"] = [p["expiry"] if p else None for p in parsed]
    wide["strike"] = [p["strike"] if p else np.nan for p in parsed]
    wide["cp"] = [p["cp"] if p else None for p in parsed]
    return wide


def _shape_bars(long: pd.DataFrame, kind: str) -> pd.DataFrame:
    """``(ts, ric, field, value)`` -> the SPEC §3.1 schema for one instrument kind."""
    if long.empty:
        return empty_bars()
    wide = (
        long.groupby(["ts", "ric", "field"])["value"].last().unstack("field").reset_index()
    )
    wide = wide.rename(columns=FIELD_TO_COLUMN)
    wide["kind"] = kind
    wide = _attach_contract_identity(wide, kind)
    for column in BAR_COLUMNS:
        if column not in wide.columns:
            wide[column] = np.nan
    for column in _NUMERIC_COLUMNS:
        wide[column] = pd.to_numeric(wide[column], errors="coerce")
    return wide[BAR_COLUMNS].sort_values(["ts", "ric"]).reset_index(drop=True)


def _fetch_universe(ld, rics, start, end, params: Params, batch_size: int = BATCH_SIZE):
    """Batched, fail-soft pull of a RIC list. Returns ``(long_rows, errors)``.

    A batch that the API rejects as a whole is retried one RIC at a time (AD-2) —
    one bad guess in a batch of 25 must not cost the other 24.
    """
    rics = list(rics)
    frames, errors = [], []
    for i in range(0, len(rics), batch_size):
        batch = rics[i: i + batch_size]
        df, error = _history(ld, batch, FIELDS, start, end)
        if df is not None:
            frames.append(_long_rows(df, batch, params))
            continue
        errors.append({"universe": batch, "error": error})
        for ric in batch:
            one, one_error = _history(ld, [ric], FIELDS, start, end)
            if one is not None:
                frames.append(_long_rows(one, [ric], params))
            else:
                errors.append({"universe": [ric], "error": one_error})
    long = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["ts", "ric", "field", "value"]
    )
    return long, errors


def _week_chain(
    ld, week: Week, strikes, params: Params, batch_size: int
) -> tuple[pd.DataFrame, dict, list, list, list]:
    """Pull one week's calls, trying both RIC forms (SPEC §3.3).

    The caret form is asked first because it is the canonical expired one; whatever
    it does not answer for is asked again without the suffix, which is the form a
    recently expired contract still answers to. The winner is recorded per contract:
    a week whose contracts all came back under the live form is a fact about how
    recent it is, and the page and the notebook both say so.
    """
    expiry = week.expiry_day
    start, end = week.entry_day, expiry + dt.timedelta(days=1)
    forms = {"expired": True, "live": False}

    by_ric_form, pending, errors, requested = {}, list(strikes), [], []
    long_frames = []
    for form_name, expired in forms.items():
        if not pending:
            break
        rics = {
            build_option_ric(params.root, expiry, "C", k, expired=expired): k
            for k in pending
        }
        requested.extend(rics)
        long, form_errors = _fetch_universe(ld, list(rics), start, end, params, batch_size)
        errors.extend(form_errors)
        if not long.empty:
            long_frames.append(long)
            answered = {str(r) for r in long["ric"].unique()}
            for ric, strike in rics.items():
                if ric in answered:
                    by_ric_form[ric] = form_name
            pending = [k for ric, k in rics.items() if ric not in answered]
    long = pd.concat(long_frames, ignore_index=True) if long_frames else pd.DataFrame(
        columns=["ts", "ric", "field", "value"]
    )
    # Every *contract* no form answered for, named once, in the canonical caret
    # spelling. A batch that *partly* answers raises no error, so without this the
    # contracts inside it that returned nothing would leave no trace anywhere — and a
    # chain short of a strike nobody knows is missing turns a tradable week into a skip
    # that reads as the market's fault.
    #
    # Derived from `pending`, not from the requested RIC list: a strike asked under both
    # forms is ONE contract, and listing both spellings counted every genuine miss twice
    # while a contract rescued by the second form appeared as answered *and* unanswered
    # at once. That inflation reached the operator's verification line and the RUNBOOK
    # (T-81).
    unanswered = [build_option_ric(params.root, expiry, "C", k, expired=True)
                  for k in pending]
    return long, by_ric_form, errors, requested, unanswered


def _pull_one_week(
    ld, week: Week, stock: pd.DataFrame, params: Params, diagnostics: dict,
    *, strike_step: float, band_steps: int, batch_size: int,
) -> pd.DataFrame:
    """Pull one week's chain and record what happened, whatever happened.

    A short week and a week whose chain came back empty both leave a record behind:
    the engine has to be able to say *why* a week produced no entry (I-10), and a
    week that silently never appears cannot be explained by anything downstream.
    """
    record = {"week": week.label, "sessions": [str(d) for d in week.sessions],
              "entry_day": str(week.entry_day), "expiry_day": str(week.expiry_day),
              "short_week": week.is_short, "n_strikes": 0, "n_contracts": 0, "n_bars": 0}
    if week.is_short:
        # Recorded, not dropped: the engine logs it as SKIP_SHORT_WEEK (I-10).
        diagnostics["weeks"].append(record)
        return empty_bars()

    strikes = week_strike_band(stock, week, step=strike_step, pad=band_steps)
    record["n_strikes"] = len(strikes)
    long, forms, errors, requested, unanswered = _week_chain(
        ld, week, strikes, params, batch_size
    )
    diagnostics["ric_form_used"].update(forms)
    diagnostics["errors"].extend(errors)
    diagnostics["requested"].extend(requested)
    diagnostics["unanswered"].extend(unanswered)

    options = _shape_bars(long, "option")
    record["n_contracts"] = int(options["ric"].nunique()) if not options.empty else 0
    record["n_bars"] = int(len(options))
    diagnostics["weeks"].append(record)
    return options


def _target_paths(path: Path | str, meta_path: Path | str | None) -> tuple[Path, Path]:
    """The parquet and its payload sidecar. The sidecar's name follows the tape's."""
    path = Path(path)
    if meta_path is not None:
        return path, Path(meta_path)
    return path, path.with_name(path.stem + ".meta.json")


def _refuse_an_unsafe_pull(path: Path, overwrite: bool) -> None:
    """The two refusals, before a session is opened or a request is made.

    Both are about not destroying something: the committed tape, and the NFR-4
    guarantee that nothing in CI, the tests or the build reaches the network.
    """
    if os.environ.get("OSL_OFFLINE") == "1":
        raise RuntimeError(
            "OSL_OFFLINE=1 — the pull is refused. Production, tests and CI run offline "
            "(NFR-4); load_tape() reads the committed parquet."
        )
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"{path} already exists. Rename it first, or pass overwrite=True. Caches are "
            "never silently regenerated (CLAUDE.md hard constraint)."
        )


def fetch_tape(
    params: Params | None = None,
    *,
    path: Path | str = TAPE_PATH,
    meta_path: Path | str | None = None,
    overwrite: bool = False,
    strike_step: float = STRIKE_STEP,
    band_steps: int = BAND_STEPS,
    batch_size: int = BATCH_SIZE,
) -> Tape:
    """The one-time hourly pull (FR-13 / T-77). **Human-invoked only** — RUNBOOK §8.

    Needs Workspace running and logged in, takes minutes, and writes the tape plus
    its payload sidecar. It refuses an existing tape (caches are data artifacts, not
    build outputs) and refuses to run under ``OSL_OFFLINE=1``, which is what CI sets.
    """
    params = params or Params()
    path, meta_path = _target_paths(path, meta_path)
    _refuse_an_unsafe_pull(path, overwrite)

    diagnostics: dict = {
        "requested_fields": list(FIELDS),
        "tz_convention": TZ_CONVENTION,
        "strike_step_discovered": strike_step,
        "strike_step_source": "T-62 spike, 2026-09-13 — measured on QQQ weeklies, not "
                              "re-derived by this pull",
        "band_steps": band_steps,
        "stock_error": None,
        "requested": [],
        "returned": [],
        "ric_form_used": {},
        "unanswered": [],
        "weeks": [],
        "errors": [],
    }

    with lseg_session() as ld:
        stock_df, stock_error = _history(
            ld, [params.underlying], FIELDS, params.start,
            params.end + dt.timedelta(days=1),
        )
        diagnostics["stock_error"] = stock_error
        stock = _shape_bars(_long_rows(stock_df, [params.underlying], params), "stock")
        if stock.empty:
            # No stock, no calendar, no chain. Nothing is written: a half-empty tape on
            # disk would block the next attempt (fetch refuses an existing file) and a
            # page built on it would render plausibly with an empty book.
            raise RuntimeError(
                f"No {params.underlying} bars returned for {params.start}..{params.end} "
                f"— nothing written. LSEG said: {stock_error or 'an empty frame'}"
            )

        frames = [stock]
        for week in trading_weeks(pd.DatetimeIndex(stock["ts"]), params):
            options = _pull_one_week(
                ld, week, stock, params, diagnostics,
                strike_step=strike_step, band_steps=band_steps, batch_size=batch_size,
            )
            if not options.empty:
                frames.append(options)

    bars = pd.concat(frames, ignore_index=True).sort_values(["ts", "ric"])
    bars = bars.drop_duplicates(subset=["ts", "ric"], keep="last").reset_index(drop=True)
    diagnostics["returned"] = sorted(str(r) for r in bars["ric"].unique())
    return _write(bars[BAR_COLUMNS], params, diagnostics, path, meta_path)


def _write(bars, params: Params, diagnostics: dict, path: Path, meta_path: Path) -> Tape:
    """Write the parquet and its payload sidecar, then hand back the loaded tape.

    The payload keys live beside the table rather than inside it (SPEC §3.1): a
    parquet file's own metadata is engine-specific and invisible to anyone who opens
    the file in something else, and these keys are exactly what a reader needs in
    order to trust the bars.
    """
    meta = {
        "ticker": params.underlying,
        "root": params.root,
        "window": [str(params.start), str(params.end)],
        "interval": params.interval,
        "fetched_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "synthetic": False,
        "tz": params.tz,
        "n_bars": int(len(bars)),
        "n_contracts": int(bars[bars["kind"] == "option"]["ric"].nunique()),
        "diagnostics": diagnostics,
    }
    bars.to_parquet(path, index=False)
    meta_path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return Tape(bars=attach_mid(_normalise_dtypes(bars)), meta=meta)


# --------------------------------------------------------------------------
# The synthetic tape — SPEC §3.4, AD-7. No network, no cache, no calendar.
# --------------------------------------------------------------------------
#: Annualised vol the synthetic options are priced at. Not a measurement — the
#: synthetic tape is a *shape*, and the page built from one says so (SPEC §11).
SYNTHETIC_SIGMA = 0.18
#: Where the synthetic stock path starts, near QQQ's real level so the $1 step is
#: the right relative size.
SYNTHETIC_SPOT = 700.0
#: Per-bar lognormal step: ~1% a day over 16 bars, ~2% a week. Enough that the
#: nearest-OTM strike finishes on both sides of spot across a window.
SYNTHETIC_BAR_VOL = 0.0025
SYNTHETIC_WEEKS = 12
#: Strikes either side of the week's entry spot, on ``STRIKE_STEP``.
SYNTHETIC_BAND = 10

#: T-62's real session shapes: the stock runs 04:00-19:00 ET, options 09:00-16:00 ET,
#: both past the 16:00 close. A half session (the day after a holiday) stops early.
STOCK_SESSION_HOURS = tuple(range(4, 20))
OPTION_SESSION_HOURS = tuple(range(9, 17))
HALF_SESSION_HOURS = tuple(range(4, 13))

#: What each week of the synthetic window is *for*, by index from the oldest.
#:
#: Every skip path the engine can take is reachable from this one fixture, and each
#: is addressable by name — a test that wants the no-quote week asks for it rather
#: than hunting for a week that happens to have the property. Weeks not named here
#: are ordinary, and there are always several: a fixture that is all pathology tells
#: you nothing about the normal case.
SYNTHETIC_ROLES = {
    2: "monday_holiday",            # DR-7: the week's first session is the Tuesday
    4: "no_quote_at_entry",         # SKIP_NO_QUOTE: chosen strike, zero bid, entry bar
    5: "no_strike_above_spot",      # SKIP_NO_STRIKE: the chain tops out below spot
    7: "friday_holiday",            # DR-7: the expiry is the Thursday, and the RIC says so
    8: "short_week",                # SKIP_SHORT_WEEK: one session, nothing can expire
    9: "half_session_entry_day",    # SKIP_NO_STOCK_PRINT: no 15:00 bar to enter on
}


def _synthetic_weeks(end_date: dt.date, weeks: int) -> list[tuple[int, str | None, list]]:
    """Mon-Fri sessions for ``weeks`` ISO weeks ending in ``end_date``'s week.

    The calendar is built **backwards from the date the caller gives**, never from
    ``today()``. That is OQ-6's lesson, and it is the reason this function's
    ``end_date`` has no default: a fixture anchored to the clock reports on the
    calendar, and one already failed CI on a Monday for a reason that had nothing to
    do with the code under test.
    """
    if end_date.weekday() > 4:
        raise ValueError(f"end_date must be a weekday (a session), got {end_date:%A}")
    end_monday = end_date - dt.timedelta(days=end_date.weekday())
    out = []
    for index in range(weeks):
        monday = end_monday - dt.timedelta(weeks=weeks - 1 - index)
        # The last week anchors the window and therefore never carries a pathology: a
        # role trimmed its sessions *before* the end_date clip, so `weeks=8` ending on a
        # Friday quietly produced a tape ending on the Thursday, and one combination
        # produced a week with no sessions at all that vanished from the tape (T-81).
        role = None if index == weeks - 1 else SYNTHETIC_ROLES.get(index)
        days = [monday + dt.timedelta(days=offset) for offset in range(5)]
        if role == "monday_holiday":
            days = days[1:]
        elif role == "friday_holiday":
            days = days[:4]
        elif role == "short_week":
            days = days[:1]
        if index == weeks - 1:
            days = [d for d in days if d <= end_date]
        if not days:
            raise ValueError(
                f"week {index} of the synthetic window has no sessions "
                f"(end_date={end_date}, weeks={weeks})"
            )
        out.append((index, role, days))
    return out


def dropped_roles(weeks: int) -> list[str]:
    """Roles a window of ``weeks`` cannot carry — too short, or on the anchor week.

    Recorded in the payload rather than left to be discovered: a caller asking for a
    four-week tape gets no no-quote entry bar, and a test written against it would pass
    for want of the case rather than because the code handles it.
    """
    return [role for index, role in sorted(SYNTHETIC_ROLES.items())
            if index >= weeks - 1]


def _synthetic_stock_bars(calendar, rng, params: Params, spot0: float) -> pd.DataFrame:
    """One random walk through every session's bars, in exchange time."""
    rows, price = [], float(spot0)
    for _, role, days in calendar:
        for day in days:
            half = role == "half_session_entry_day" and day == days[0]
            for hour in (HALF_SESSION_HOURS if half else STOCK_SESSION_HOURS):
                opened = price
                price *= float(np.exp(rng.normal(0.0, SYNTHETIC_BAR_VOL)))
                high = max(opened, price) * (1 + abs(rng.normal(0, 0.0006)))
                low = min(opened, price) * (1 - abs(rng.normal(0, 0.0006)))
                rows.append({
                    "ts": pd.Timestamp(dt.datetime.combine(day, dt.time(hour)),
                                       tz=params.tz),
                    "ric": params.underlying, "kind": "stock",
                    "expiry": None, "strike": np.nan, "cp": None,
                    "bid": round(price - 0.01, 4), "ask": round(price + 0.01, 4),
                    "trdprc_1": round(price, 4), "open": round(opened, 4),
                    "high": round(high, 4), "low": round(low, 4),
                    "volume": float(rng.lognormal(13.5, 0.6)),
                    "num_moves": float(int(rng.lognormal(8.0, 0.5))),
                })
    return pd.DataFrame(rows, columns=BAR_COLUMNS)


def _synthetic_spread(price: float, hour: int) -> float:
    """Wider at the open than at the close — the reason SD-4 chose the closing bar.

    A penny floor, because a quote finer than the tick is not a quote.
    """
    fraction = 0.06 if hour <= 10 else (0.04 if hour <= 13 else 0.02)
    return max(0.02, round(price * fraction, 2))


def _synthetic_listing(stock, days, role, params: Params):
    """What a week lists: its entry bar, its strike ladder, and the strike the rule takes.

    ``None`` when the week's first session carries no bars at all — there is nothing
    to centre a chain on, which is different from a chain that exists and disappoints.
    """
    entry_ts = entry_bar_ts(pd.DatetimeIndex(stock["ts"]), days[0], params)
    day_bars = stock[stock["ts"].dt.date == days[0]]
    if entry_ts is not None:
        spot = float(stock.loc[stock["ts"] == entry_ts, "trdprc_1"].iloc[0])
    elif len(day_bars):
        # A half session still lists a chain — the week skips for want of a print at
        # the entry bar, not for want of contracts (SKIP_NO_STOCK_PRINT, not _STRIKE).
        spot = float(day_bars["trdprc_1"].iloc[-1])
    else:
        return None
    strikes = strike_band(spot, spot, step=STRIKE_STEP, pad=SYNTHETIC_BAND)
    if role == "no_strike_above_spot":
        strikes = [k for k in strikes if k < spot]
    return entry_ts, strikes, select_strike(strikes, spot, params)


def _synthetic_chain_bars(stock, calendar, rng, params: Params) -> pd.DataFrame:
    """One week's calls per week, priced off the stock path that week.

    Prices come from Black-Scholes on the bar's own spot, so a mid is never
    inconsistent with the underlying beside it — which matters because T-58's
    mid-vs-print evidence and T-57's invariants both read these two together.
    """
    rows = []
    for _, role, days in calendar:
        if len(days) < MIN_SESSIONS_PER_WEEK:
            continue                      # a one-session week lists nothing to trade
        listing = _synthetic_listing(stock, days, role, params)
        if listing is None:
            continue
        entry_ts, strikes, chosen = listing
        expiry = days[-1]
        expiry_close = pd.Timestamp(dt.datetime.combine(expiry, dt.time(16)), tz=params.tz)

        for day in days:
            for hour in OPTION_SESSION_HOURS:
                ts = pd.Timestamp(dt.datetime.combine(day, dt.time(hour)), tz=params.tz)
                spot_row = stock.loc[stock["ts"] == ts, "trdprc_1"]
                if spot_row.empty:
                    continue
                spot = float(spot_row.iloc[0])
                t_years = max((expiry_close - ts).total_seconds() / (365 * 24 * 3600), 0.0)
                for strike in strikes:
                    rows.append(_synthetic_option_row(
                        ts, hour, spot, strike, t_years, expiry, params, rng,
                        kill_quote=(role == "no_quote_at_entry" and ts == entry_ts
                                    and strike == chosen),
                    ))
    return pd.DataFrame([r for r in rows if r is not None], columns=BAR_COLUMNS)


def _synthetic_option_row(ts, hour, spot, strike, t_years, expiry, params, rng, kill_quote):
    """One contract-bar: a Black-Scholes mid, a spread, and the holes real tapes have."""
    price = bs_price(spot, strike, t_years, SYNTHETIC_SIGMA, cp="C")
    spread = _synthetic_spread(max(price, 0.05), hour)
    bid = round(max(price - spread / 2, 0.01), 2)
    ask = round(max(price + spread / 2, 0.02), 2)

    if rng.random() < 0.08:
        bid = ask = np.nan            # simply not quoted at this bar
    elif rng.random() < 0.01:
        bid, ask = ask, bid           # crossed: a bad print, refused by valid_mid

    # Drawn from the honest quote, and drawn unconditionally so the number of rng calls
    # never depends on the data. A trade printed at half the contract's value would make
    # the fixture's canonical DR-1 bar look like a pricing error rather than a missing
    # bid (T-81), and T-58 fits prints against mids.
    roll, noise = rng.random(), rng.normal(0, max(spread / 3, 0.01))
    printed = roll < 0.35 and not np.isnan(bid)
    mid = (bid + ask) / 2 if not np.isnan(bid) else np.nan
    trade = round(mid + noise, 2) if printed else np.nan

    if kill_quote:
        # SPEC §6.1: a zero bid is "no bid". This is the one case that must be here —
        # every window has to exercise the skip path at an entry bar (SPEC §3.4).
        #
        # It overrides whatever the two holes above drew, and keeps the honest ask: the
        # named case is a *one-sided* quote, and a bar that came out zero-bid AND
        # NaN-ask is the unquoted case wearing a zero bid — a muddier row that would let
        # a T-57 test pass on the wrong skip reason. Applied after the print is drawn,
        # so the bar keeps the trade a real tape would carry beside a one-sided quote.
        bid, ask = 0.0, round(max(price + spread / 2, 0.02), 2)
    return {
        "ts": ts,
        "ric": build_option_ric(params.root, expiry, "C", strike, expired=True),
        "kind": "option", "expiry": expiry, "strike": float(strike), "cp": "C",
        "bid": bid, "ask": ask, "trdprc_1": trade,
        "open": np.nan, "high": np.nan, "low": np.nan,
        "volume": float(int(rng.lognormal(4.0, 1.0))) if printed else np.nan,
        "num_moves": float(int(rng.lognormal(2.0, 0.8))) if printed else np.nan,
    }


def synthesize_tape(
    end_date: dt.date,
    *,
    seed: int = 7,
    weeks: int = SYNTHETIC_WEEKS,
    params: Params | None = None,
    spot0: float = SYNTHETIC_SPOT,
) -> Tape:
    """A deterministic tape with no LSEG behind it — the fixture and the fallback (AD-7).

    Same schema, same dtypes and same payload shape as a pulled tape, so nothing
    downstream can tell them apart *structurally* — only by ``Tape.synthetic``, which
    the page prints and CI refuses to publish (SPEC §11).

    ``end_date`` is **required and positional**: SPEC §3.4 writes the signature with a
    keyword, but a default would be a clock reference waiting to happen, and OQ-6 has
    already cost one false CI failure. Given the same ``end_date`` and ``seed`` this
    returns byte-identical bars, which is what I-12's determinism test rests on.

    What it models, and why each one is here (SPEC §3.4):

    * **Both sides of the strike at expiry** — a window where every Friday finishes OTM
      exercises neither assignment nor the stock leaving the book.
    * **Quotes missing on some bars, including an entry bar** — DR-1's skip is the path
      most likely to be wrong and least likely to be reached by accident.
    * **Spreads wider at the open than at the close** — the shape behind SD-4.
    * **Sparse prints** — most option bars never trade, which is the whole of 1.1.
    * **A holiday at each end of a week, a one-session week, a half session** — DR-7 and
      three of the four skip reasons, named in :data:`SYNTHETIC_ROLES`.
    """
    params = params or Params()
    rng = np.random.default_rng(seed)
    calendar = _synthetic_weeks(end_date, weeks)

    stock = _synthetic_stock_bars(calendar, rng, params, spot0)
    options = _synthetic_chain_bars(stock, calendar, rng, params)
    bars = pd.concat([stock, options], ignore_index=True)
    bars = bars.sort_values(["ts", "ric"]).reset_index(drop=True)

    sessions = [day for _, _, days in calendar for day in days]
    meta = {
        "ticker": params.underlying,
        "root": params.root,
        "window": [str(min(sessions)), str(max(sessions))],
        "interval": params.interval,
        "fetched_at": "—",
        "synthetic": True,
        "tz": params.tz,
        "n_bars": int(len(bars)),
        "n_contracts": int(options["ric"].nunique()) if len(options) else 0,
        "diagnostics": {
            "requested_fields": list(FIELDS),
            "tz_convention": TZ_CONVENTION,
            "strike_step_discovered": STRIKE_STEP,
            "band_steps": SYNTHETIC_BAND,
            "seed": seed,
            "end_date": str(end_date),
            "sigma": SYNTHETIC_SIGMA,
            "synthetic_roles": {
                f"{index}": {"role": role, "sessions": [str(d) for d in days]}
                for index, role, days in calendar
            },
            "dropped_roles": dropped_roles(weeks),
            "requested": [], "returned": [], "ric_form_used": {}, "unanswered": [],
            "weeks": [], "errors": [],
        },
    }
    return Tape(bars=attach_mid(_normalise_dtypes(bars, params.tz)), meta=meta)


# --------------------------------------------------------------------------
# CLI — `python -m options_surface_lab.covered_call.tape fetch | inspect`
# --------------------------------------------------------------------------
def _contract_key(ric: str):
    """``(expiry, strike)`` — one instrument, whichever RIC form was used to ask for it."""
    parsed = parse_option_ric(ric)
    return None if parsed is None else (parsed["expiry"], parsed["strike"])


def describe(tape: Tape) -> str:
    """What a human checks after the pull, before committing it (RUNBOOK §8)."""
    bars, diag = tape.bars, tape.meta.get("diagnostics", {})
    weeks = diag.get("weeks", [])
    forms = diag.get("ric_form_used", {})
    counts = {form: sum(1 for v in forms.values() if v == form)
              for form in sorted(set(forms.values()))}
    requested_rics = set(diag.get("requested", []))
    answered_rics = set(tape.options["ric"].unique())
    # A contract is (expiry, strike) — one instrument, however many RIC spellings were
    # tried for it. Counting strings made the line above read 2x on every genuine miss.
    requested = {_contract_key(r) for r in requested_rics} - {None}
    answered = {_contract_key(r) for r in answered_rics} - {None}
    options = tape.options
    lines = [
        f"{len(bars)} bars | {tape.stock['ric'].nunique()} stock, "
        f"{options['ric'].nunique()} contracts | synthetic={tape.synthetic}",
        f"window {tape.meta.get('window')} | interval {tape.meta.get('interval')} | "
        f"step {diag.get('strike_step_discovered')}",
        # Option bars only. The stock is quoted on every bar, so counting the whole
        # table against the option count overstates the rate and cannot even be read
        # as a percentage — it came out above 100% the first time a synthetic tape
        # was printed.
        f"quotes: {int(options['mid'].notna().sum())} of {len(options)} option bars "
        f"carry a valid mid "
        f"({100 * options['mid'].notna().mean():.1f}%)" if len(options) else "no options",
    ]
    if tape.synthetic:
        roles = diag.get("synthetic_roles", {})
        lines.insert(1, f"** SYNTHETIC — a shape, not a market. seed={diag.get('seed')}, "
                        f"end_date={diag.get('end_date')}, "
                        f"{sum(1 for v in roles.values() if v.get('role'))} weeks carry a "
                        f"named pathology. Nothing built on this may be published. **")
    else:
        # Every RIC the pull asked for has exactly one outcome — answered, or refused
        # and recorded. If these do not add up, contracts went missing in a batch that
        # failed in a way the retry did not cover, and the tape is short of a chain
        # nobody will notice is absent.
        lines.insert(1, f"contracts: {len(answered)} answered + "
                        f"{len(requested - answered)} refused = {len(requested)} requested"
                        f"  ({len(requested_rics)} RIC requests across both forms)"
                        + ("" if answered <= requested
                           else "  ** UNREQUESTED CONTRACTS IN THE TAPE **"))
        lines.append(f"RIC forms that answered: {counts or '—'}")
    for week in weeks:
        flag = "  SHORT WEEK" if week.get("short_week") else ""
        lines.append(
            f"  {week['week']}  {week['entry_day']} -> {week['expiry_day']}  "
            f"{week['n_contracts']:>3} contracts, {week['n_bars']:>4} bars{flag}"
        )
    if diag.get("errors"):
        lines.append(f"{len(diag['errors'])} soft failures — see diagnostics.errors")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The hourly tape (FR-13).")
    parser.add_argument("action", choices=["fetch", "inspect"])
    parser.add_argument("--path", default=str(TAPE_PATH))
    parser.add_argument("--overwrite", action="store_true",
                        help="replace an existing tape — the PO's call, never a session's")
    args = parser.parse_args(argv)

    if args.action == "fetch":
        params = Params()
        print(f"pulling {params.underlying} {params.interval} "
              f"{params.start} -> {params.end} into {args.path}")
        tape = fetch_tape(params, path=Path(args.path), overwrite=args.overwrite)
    else:
        tape = load_tape(Path(args.path))
    print(describe(tape))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
