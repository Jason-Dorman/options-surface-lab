"""The strategy rules — pure functions and the parameter record.

No I/O, no network, no plotly, no theme (AD-12). Everything here is specified:

* ``Params``                          — SPEC-COVERED-CALL §2
* the calendar and the *closing bar*  — SPEC §3.2, and DR-7
* ``select_strike``                   — SPEC §5, SD-5
* ``is_itm``                          — SPEC §7, SD-6
* ``valid_mid``                       — SPEC §6.1, DR-1
* ``BlotterRow`` and its constructors — SPEC §8, DR-3, DR-8

**Why the blotter constructors live here and not in ``live.py``.** T-80 asked for
them in the live module so T-57's engine could reuse them, but that would have the
transform core importing the module that holds the network (AD-12's layering runs
the other way). They are pure functions returning a record, so they belong with the
rules: ``live.py`` and ``engine.py`` both import them, and a live row and a
backtested row come from one code path either way (NFR-5).

**The one trap this module exists to close.** T-62 (2026-09-13) measured LSEG's
hourly bars: they are stamped at the bar's **start**, and both tapes keep running
past the 16:00 ET equity close carrying real quotes — the stock to a 19:00 ET bar,
options to a 16:00 ET bar. So ``max(ts)`` of a session is a *post-close stub*, not
the close. On 2026-09-08 that difference moved the 18-Sep 715 call's mid from
11.195 to 11.02, i.e. $17.50 on one contract. Nothing in this package may pick a
bar with ``max``; it goes through :func:`entry_bar_ts` / :func:`closing_bar_ts`.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable, Literal

import pandas as pd

# --- SPEC §3.2 item 4 — which hourly bar is "the close" ---------------------
#: ET start-hour of the regular session's closing bar (the 15:00-16:00 ET bar).
CLOSING_BAR_HOUR_ET = 15
#: ET start-hour of a session's opening bar, for ``entry_bar == "first"``.
OPENING_BAR_HOUR_ET = 9
#: Every timestamp the engine reasons about is exchange time (S-8).
EXCHANGE_TZ = "America/New_York"
#: A trading week needs an entry session and an expiry session (SPEC §3.2 rule 2).
MIN_SESSIONS_PER_WEEK = 2


@dataclass(frozen=True)
class Params:
    """The strategy, as a record. Defaults are the PO's decisions (PRD §15).

    The page prints this whole object (FR-14), so the strategy a reader sees is
    the one the engine ran.
    """

    underlying: str = "QQQ.O"                                     # SD-1
    start: dt.date = dt.date(2026, 7, 6)                          # SD-2
    end: dt.date = dt.date(2026, 9, 11)                           # SD-2
    interval: Literal["hourly"] = "hourly"                        # DR-6, the brief
    start_cash: float = 75_000.0                                  # SD-3
    entry_bar: Literal["first", "last"] = "last"                  # SD-4
    strike_rule: Literal["nearest_otm", "delta"] = "nearest_otm"   # SD-5
    delta_target: float | None = None                             # SD-5, P1 only
    itm_rule: Literal["strict"] = "strict"                        # SD-6
    shares: int = 100                                             # S-1, the brief
    contracts: int = 1                                            # S-1, the brief
    tz: str = EXCHANGE_TZ                                         # S-8

    def __post_init__(self) -> None:
        if self.entry_bar not in ("first", "last"):
            raise ValueError(f"entry_bar must be 'first' or 'last', got {self.entry_bar!r}")
        if self.strike_rule not in ("nearest_otm", "delta"):
            raise ValueError(
                f"strike_rule must be 'nearest_otm' or 'delta', got {self.strike_rule!r}"
            )
        if self.itm_rule != "strict":
            raise ValueError(f"itm_rule must be 'strict' (SD-6), got {self.itm_rule!r}")
        if self.interval != "hourly":
            raise ValueError(f"interval must be 'hourly' (DR-6), got {self.interval!r}")
        if self.strike_rule == "delta" and self.delta_target is None:
            raise ValueError("strike_rule 'delta' needs a delta_target (SD-5, P1)")
        if self.strike_rule == "nearest_otm" and self.delta_target is not None:
            raise ValueError("delta_target is meaningless under 'nearest_otm' — leave it None")
        if self.start >= self.end:
            raise ValueError(f"start {self.start} must precede end {self.end}")
        if self.shares <= 0 or self.contracts <= 0:
            raise ValueError("shares and contracts must be positive (S-1: 100 and 1)")
        if self.start_cash <= 0:
            raise ValueError("start_cash must be positive (SD-3)")

    @property
    def root(self) -> str:
        """The option root — the equity RIC before the dot. ``QQQ.O`` -> ``QQQ``."""
        return self.underlying.split(".")[0].upper()

    @property
    def entry_bar_hour_et(self) -> int:
        """ET start-hour of the entry bar, per SD-4. Never ``max(ts)`` — see the module docstring."""
        return CLOSING_BAR_HOUR_ET if self.entry_bar == "last" else OPENING_BAR_HOUR_ET

    def describe_strike_rule(self) -> str:
        """The rule in words, for the page (FR-14).

        SPEC §5 requires the printed sentence and ``params`` to be unable to say
        different things, so the page renders this rather than its own prose.
        """
        if self.strike_rule == "nearest_otm":
            return (
                "Write the call at the lowest listed strike at or above the spot print at "
                "the entry bar — at the money if spot sits exactly on a strike."
            )
        return (
            "Write the call at the listed strike whose Black-Scholes delta is nearest "
            f"{self.delta_target:.2f}, inverted from the mid at the entry bar."
        )


# --------------------------------------------------------------------------
# Strike selection — SPEC §5, SD-5
# --------------------------------------------------------------------------
def select_strike(
    chain: Iterable[float | None],
    spot: float | None,
    params: Params,
) -> float | None:
    """The smallest listed strike at or above ``spot``; ``None`` if none is listed.

    ``chain`` is every strike *listed* that week, whether or not it is quoted at
    this bar. Quoting is checked separately (SPEC §4 step 3) so that "no strike"
    and "no quote" stay distinguishable in the skip log.

    ``K == spot`` is at the money and allowed — the brief's "or ATM if spot sits
    on a strike". Strikes arrive as hundredths from the RIC grammar and land on
    $0.50 or $1.00 steps, so they are exactly representable and compared exactly.
    No epsilon is applied: an epsilon would quietly make a strike *below* spot
    eligible, which is a different strategy.

    The rule never walks past the first eligible strike. If that strike turns out
    to be unquoted the week is skipped, not rewritten (SD-5, DR-1).
    """
    if params.strike_rule != "nearest_otm":
        raise NotImplementedError(
            f"strike_rule {params.strike_rule!r} is P1 (FR-20); only 'nearest_otm' is implemented"
        )
    if spot is None or pd.isna(spot):
        return None
    candidates = sorted(float(k) for k in chain if k is not None and not pd.isna(k))
    for strike in candidates:
        if strike >= float(spot):
            return strike
    return None


def is_itm(settlement_print: float | None, strike: float, params: Params) -> bool | None:
    """SD-6, strict: in the money iff the settlement print is *strictly* above the strike.

    Equality expires worthless, matching exercise mechanics — OCC auto-exercise
    triggers a cent in the money. ``None`` when there is no settlement print to
    judge, which the engine must treat as a missing settlement rather than as OTM.
    """
    if settlement_print is None or pd.isna(settlement_print):
        return None
    if params.itm_rule != "strict":  # pragma: no cover — __post_init__ forbids it
        raise NotImplementedError(f"itm_rule {params.itm_rule!r} is not implemented")
    return float(settlement_print) > float(strike)


# --------------------------------------------------------------------------
# The calendar — SPEC §3.2, DR-7
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Week:
    """One ISO week of the stock tape. Sessions are *observed*, never generated."""

    iso_year: int
    iso_week: int
    sessions: tuple[dt.date, ...]

    @property
    def label(self) -> str:
        return f"{self.iso_year}-W{self.iso_week:02d}"

    @property
    def entry_day(self) -> dt.date:
        """The week's first observed session. A Monday holiday makes this Tuesday (DR-7)."""
        return self.sessions[0]

    @property
    def expiry_day(self) -> dt.date:
        """The week's last observed session — that contract's expiry, holidays included (DR-7)."""
        return self.sessions[-1]

    @property
    def is_short(self) -> bool:
        """Fewer than two sessions: nothing can both enter and expire (SKIP_SHORT_WEEK)."""
        return len(self.sessions) < MIN_SESSIONS_PER_WEEK


def to_exchange_time(index, params: Params) -> pd.DatetimeIndex:
    """Localise LSEG's tz-naive UTC bar index and convert it to exchange time.

    The single place the OQ-11 convention is applied (SPEC §3.1): LSEG returns the
    index tz-naive in **UTC**, stamped at the bar's START. Both acquisition modules
    (:mod:`tape` and :mod:`live`) hand their frames through here so the conversion
    cannot be right in one of them and wrong in the other. An index that is already
    tz-aware is converted, not re-localised.
    """
    index = pd.DatetimeIndex(index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    return index.tz_convert(params.tz)


def _require_exchange_time(index: pd.DatetimeIndex, params: Params) -> pd.DatetimeIndex:
    """Guard the OQ-11 trap: a tz-naive index is almost certainly still UTC."""
    index = pd.DatetimeIndex(index)
    if index.tz is None:
        raise ValueError(
            "bar index is tz-naive. LSEG returns tz-naive UTC stamped at the bar's "
            "START (T-62); localise to UTC and convert to exchange time before calling "
            "the calendar helpers — SPEC §3.1."
        )
    return index.tz_convert(params.tz)


def trading_weeks(index: pd.DatetimeIndex, params: Params) -> list[Week]:
    """Group the stock tape's bars into ISO weeks — SPEC §3.2, DR-7.

    Short weeks are returned too, flagged by :attr:`Week.is_short`, so the engine
    can log them as ``SKIP_SHORT_WEEK`` rather than let them silently vanish
    (I-10: every week without an entry appears in the skip log).
    """
    local = _require_exchange_time(index, params)
    by_week: dict[tuple[int, int], set[dt.date]] = {}
    for ts in local:
        iso_year, iso_week = ts.isocalendar()[0], ts.isocalendar()[1]
        by_week.setdefault((iso_year, iso_week), set()).add(ts.date())
    return [
        Week(iso_year=year, iso_week=week, sessions=tuple(sorted(days)))
        for (year, week), days in sorted(by_week.items())
    ]


def _bar_at_hour(
    index: pd.DatetimeIndex, day: dt.date, hour_et: int, params: Params
) -> pd.Timestamp | None:
    local = _require_exchange_time(index, params)
    hits = [ts for ts in local if ts.date() == day and ts.hour == hour_et]
    return min(hits) if hits else None


def entry_bar_ts(
    index: pd.DatetimeIndex, day: dt.date, params: Params
) -> pd.Timestamp | None:
    """The entry bar for ``day`` under SD-4 — the 15:00 ET bar when ``entry_bar='last'``.

    ``None`` when that bar is absent, on a half-session say, which the engine reads
    as no print at the entry bar and logs as a skip. **Not** ``max(ts)``: see the
    module docstring for what that costs.
    """
    return _bar_at_hour(index, day, params.entry_bar_hour_et, params)


def closing_bar_ts(
    index: pd.DatetimeIndex, day: dt.date, params: Params
) -> pd.Timestamp | None:
    """The regular session's closing bar — always 15:00 ET, whatever SD-4 chose.

    Settlement reads this bar (SPEC §7) even when the entry bar is the open, so
    the asymmetry between entry and exit is explicit rather than implied.
    """
    return _bar_at_hour(index, day, CLOSING_BAR_HOUR_ET, params)


# --------------------------------------------------------------------------
# Fills — SPEC §6.1, DR-1
# --------------------------------------------------------------------------
def valid_mid(bid: float | None, ask: float | None) -> float | None:
    """``(bid + ask) / 2`` when the quote is real, else ``None``.

    Valid iff both sides are present, both are strictly positive, and
    ``ask >= bid``. A zero bid is "no bid" in the brief's words, one side alone
    has no midpoint, and a crossed market is a bad print. Returning ``None``
    rather than a number is DR-1: no quote, no fill, skip the week, and never
    invent a print — *"the worst mistake an algo trader can make"*.
    """
    if bid is None or ask is None or pd.isna(bid) or pd.isna(ask):
        return None
    bid, ask = float(bid), float(ask)
    if bid <= 0 or ask <= 0 or ask < bid:
        return None
    return (bid + ask) / 2.0


# --------------------------------------------------------------------------
# The blotter — SPEC §8. The brief's columns, exactly.
# --------------------------------------------------------------------------
#: What the ``note`` column names: the rule that fired.
RULE_ENTRY_STOCK = "R-ENTRY-STOCK"
RULE_ENTRY_CALL = "R-ENTRY-CALL"
RULE_EXPIRE = "R-EXPIRE"
RULE_ASSIGN = "R-ASSIGN"
RULE_ASSIGN_SELL = "R-ASSIGN-SELL"

#: The skip log's reasons (SPEC §8.2). A week without an entry carries exactly one.
SKIP_NO_STOCK_PRINT = "SKIP_NO_STOCK_PRINT"
SKIP_NO_STRIKE = "SKIP_NO_STRIKE"
SKIP_NO_QUOTE = "SKIP_NO_QUOTE"
SKIP_SHORT_WEEK = "SKIP_SHORT_WEEK"

#: ``limit`` and ``fill`` on a row that is not an order (SPEC §8).
NO_LIMIT = "—"

#: Places every dollar figure in the book is held to — fills, limits, cash deltas,
#: and everything the ledger derives from them.
#:
#: Four, not two: a stock print carries four decimals on this tape (719.0201), so
#: rounding to cents would move a real fill. And **not zero**: ``(6.01 + 6.08) / 2``
#: is not 6.045 in binary, so an unrounded mid reaches the blotter as
#: ``6.130000000000001`` while the same row's note prints ``mid=6.13``. The blotter
#: is a book artifact — it is what I-12 hashes and what the page will render — so a
#: row may not disagree with itself. Rounding happens **once, here**, at the point a
#: row is constructed; the ledger then accumulates rounded numbers.
MONEY_DP = 4


def money(value: float) -> float:
    """A dollar figure, held to :data:`MONEY_DP`. The one place rounding happens."""
    return round(float(value), MONEY_DP)

_TIME_FMT = "%Y-%m-%d %H:%M"


@dataclass(frozen=True)
class BlotterRow:
    """One booked trade. Entries and exits only — no working orders, no signals (DR-8)."""

    time: str
    instrument: str
    occ: str
    side: Literal["BUY", "SELL", "EXPIRE", "ASSIGN"]
    qty: int
    limit: float | str
    fill: float
    cash_delta: float
    note: str

    def as_dict(self) -> dict:
        return {
            "time": self.time, "instrument": self.instrument, "occ": self.occ,
            "side": self.side, "qty": self.qty, "limit": self.limit,
            "fill": self.fill, "cash_delta": self.cash_delta, "note": self.note,
        }


@dataclass(frozen=True)
class SkipRecord:
    """A week the strategy declined to trade (SPEC §8.2). Not a blotter row."""

    week: str
    reason: str
    state_at_skip: str
    detail: str

    def as_dict(self) -> dict:
        return {
            "week": self.week, "reason": self.reason,
            "state_at_skip": self.state_at_skip, "detail": self.detail,
        }


def format_bar_time(ts) -> str:
    """Blotter timestamps are exchange time to the minute (SPEC §8)."""
    return pd.Timestamp(ts).strftime(_TIME_FMT)


def entry_stock_row(ts, ric: str, spot: float, params: Params) -> BlotterRow:
    """R-ENTRY-STOCK — buy the shares at the bar's print (SPEC §4 step 4, §6.2)."""
    spot = money(spot)
    return BlotterRow(
        time=format_bar_time(ts), instrument=ric, occ="", side="BUY",
        qty=params.shares, limit=spot, fill=spot,
        cash_delta=money(-params.shares * spot),
        note=f"{RULE_ENTRY_STOCK} S={spot:.4f}",
    )


def entry_call_row(
    ts, ric: str, occ: str, strike: float, spot: float, mid: float, params: Params,
    sync_gap_s: float | None = None,
) -> BlotterRow:
    """R-ENTRY-CALL — sell the call, limit at mid, filled at mid (SPEC §6.2).

    ``sync_gap_s`` is the measured gap between the two legs' last trades in the entry
    bar. It is printed in the note because the whole fill assumption rests on the
    stock print and the option quote being contemporaneous, and at hourly resolution
    that is a claim to *measure*, not to assert.
    """
    mid, strike, spot = money(mid), float(strike), money(spot)
    note = f"{RULE_ENTRY_CALL} K={strike:g} S={spot:.4f} mid={mid:g}"
    if sync_gap_s is not None:
        note += f" sync={sync_gap_s:g}s"
    return BlotterRow(
        time=format_bar_time(ts), instrument=ric, occ=occ, side="SELL",
        qty=params.contracts, limit=mid, fill=mid,
        cash_delta=money(params.contracts * 100 * mid),
        note=note,
    )


def expire_row(ts, ric: str, occ: str, strike: float, settle: float, params: Params) -> BlotterRow:
    """R-EXPIRE — the call finished at or below the strike. Cash does not move (DR-3)."""
    return BlotterRow(
        time=format_bar_time(ts), instrument=ric, occ=occ, side="EXPIRE",
        qty=params.contracts, limit=NO_LIMIT, fill=0.0, cash_delta=0.0,
        note=f"{RULE_EXPIRE} K={float(strike):g} S_exp={money(settle):.4f}",
    )


def assign_rows(
    ts, call_ric: str, occ: str, stock_ric: str, strike: float, settle: float, params: Params
) -> list[BlotterRow]:
    """R-ASSIGN + R-ASSIGN-SELL — two rows, same timestamp, in that order (SPEC §7).

    The assignment itself moves no cash; the stock leaving at the strike is what
    does. Keeping them as two rows is what lets I-1 reconcile cash against the
    blotter alone.
    """
    strike, settle = float(strike), money(settle)
    return [
        BlotterRow(
            time=format_bar_time(ts), instrument=call_ric, occ=occ, side="ASSIGN",
            qty=params.contracts, limit=NO_LIMIT, fill=0.0, cash_delta=0.0,
            note=f"{RULE_ASSIGN} K={strike:g} S_exp={settle:.4f}",
        ),
        BlotterRow(
            time=format_bar_time(ts), instrument=stock_ric, occ="", side="SELL",
            qty=params.shares, limit=strike, fill=strike,
            cash_delta=money(params.shares * strike),
            note=f"{RULE_ASSIGN_SELL} K={strike:g}",
        ),
    ]
