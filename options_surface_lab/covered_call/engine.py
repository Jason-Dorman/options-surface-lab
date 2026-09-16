"""The backtest — the weekly loop, the blotter, the skip log and the Reg T ledger.

``run_backtest(tape, params) -> Book`` is the whole of FR-15/FR-16. It is pure:
no network, no I/O, no clock, no plotly, no theme (AD-12, NFR-5). Everything it
does is specified:

* the weekly loop and its three states — SPEC-COVERED-CALL §4
* strike selection                     — SPEC §5, via :func:`rules.select_strike`
* fills                                — SPEC §6, via :func:`rules.valid_mid`
* settlement                           — SPEC §7, via :func:`rules.is_itm`
* the blotter and the skip log         — SPEC §8, via the ``rules`` constructors
* the ledger and the Reg T account     — SPEC §9
* the invariants it must satisfy       — SPEC §12, tested in ``test_engine.py``

**A book is a list of trades; everything else is derived from it** (SPEC §1). Cash
moves only through a blotter row's ``cash_delta`` (DR-3), and the ledger is a
projection of the blotter over the tape's bars — never a second place where a
number is decided. The one consequence to keep in mind while reading: the ledger
row *at* the entry bar already has the trade in it, because it counts every
blotter row at or before its timestamp.

**Nothing here picks a bar with ``max``.** Entry and settlement bars come from
:func:`rules.entry_bar_ts` / :func:`rules.closing_bar_ts`, which own SPEC §3.2
item 4's closing-bar rule. See ``rules``' module docstring for what ``max(ts)``
costs.

**The asymmetry between entry and settlement is deliberate.** A missing stock print
at the *entry* bar skips the week (SPEC §4 step 1) — nothing is owed, so nothing is
invented. A missing print at the *settlement* bar cannot skip: the call is already
short and I-7 says every open call resolves, so settlement falls back to the last
stock print in that session at or before the close (S-7's carry-forward posture),
records that it did so in the blotter note, and raises only if the session carries
no print at all. A tape like that is broken, and stopping is the honest answer.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from ..option_surface_utils import occ_symbol, parse_option_ric
from .rules import (
    CLOSING_BAR_HOUR_ET,
    MONEY_DP,
    SKIP_NO_QUOTE,
    SKIP_NO_STOCK_PRINT,
    SKIP_NO_STRIKE,
    SKIP_SHORT_WEEK,
    BlotterRow,
    Params,
    SkipRecord,
    Week,
    assign_rows,
    closing_bar_ts,
    entry_bar_ts,
    entry_stock_row,
    entry_call_row,
    expire_row,
    is_itm,
    select_strike,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to a type checker
    from .tape import Tape

# --- The three position states of SPEC §4 ----------------------------------
#: Only ``FLAT`` and ``STOCK_ONLY`` are ever *recorded* — a week enters and settles
#: inside one pass, so the book is never observed in ``COVERED`` at a week boundary.
#: It is named anyway because SPEC §4's diagram names it, and a reader holding the
#: spec beside the code should find all three words in both.
STATE_FLAT = "FLAT"
STATE_COVERED = "COVERED"
STATE_STOCK_ONLY = "STOCK_ONLY"

# --- Reg T, not portfolio margin (DR-4, SPEC §9) ---------------------------
#: Initial margin on the stock. The covered short call adds **$0**.
IM_RATE = 0.50
#: Maintenance margin on the stock. No naked-option pad — the call is covered.
MM_RATE = 0.25
#: Printed beside an entry the account could not actually have carried (FR-16).
FLAG_NEG_AVAILABLE = "NEG_AVAILABLE"


#: SPEC §8 — the brief's columns, exactly, in the brief's order.
BLOTTER_COLUMNS = ["time", "instrument", "occ", "side", "qty",
                   "limit", "fill", "cash_delta", "note"]
#: SPEC §8.2.
SKIP_COLUMNS = ["week", "reason", "state_at_skip", "detail"]
#: SPEC §9. Lower-case here and title-cased by the page; ``lmv``/``nav``/``im``/``mm``
#: are the spec's LMV/NAV/IM/MM.
LEDGER_COLUMNS = [
    "ts", "week", "entry", "shares", "short_calls", "call_ric", "call_strike",
    "call_expiry", "cash", "stock_mark", "call_mark", "mark_carried",
    "lmv", "option_mv", "nav", "im", "mm", "available", "excess", "flag",
]
#: A per-week projection of the blotter and the skip log — one row per week the
#: engine considered. Derived, never decided: see :func:`_weekly_from_bookings`.
WEEKLY_COLUMNS = ["week", "entry_day", "expiry_day", "outcome", "state_at_entry",
                  "spot", "strike", "mid", "premium", "settle", "detail"]


# --------------------------------------------------------------------------
# The result
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Book:
    """Everything the page and the notebook read: the trades, and what follows.

    ``blotter`` is the primary artifact (SPEC §1). ``skips``, ``ledger`` and
    ``weekly`` are projections of it over the tape — a test pins each of them to
    the blotter so that no number on the page can come from a second source.
    """

    params: Params
    blotter: pd.DataFrame
    skips: pd.DataFrame
    ledger: pd.DataFrame
    weekly: pd.DataFrame
    synthetic: bool = True
    diagnostics: dict = field(default_factory=dict)

    @property
    def final_cash(self) -> float:
        """Cash after the last booked row — the sum of the blotter, by construction."""
        return round(
            self.params.start_cash + float(self.blotter["cash_delta"].sum()), MONEY_DP
        )

    @property
    def final_nav(self) -> float:
        """NAV at the window's **closing bar** — the last 15:00 ET row, not the last row.

        The stock tape runs to a 19:00 ET bar (T-62), so ``ledger.iloc[-1]`` is a
        post-close stub whose thin prints move the headline by tens of dollars. The
        same trap ``rules`` bans ``max(ts)`` for, one layer up: a number a reader
        quotes has to come off the close.
        """
        daily = self.daily_ledger()
        if daily.empty:
            if self.ledger.empty:
                return round(self.params.start_cash, MONEY_DP)
            return float(self.ledger["nav"].iloc[-1])
        return float(daily["nav"].iloc[-1])

    @property
    def total_return(self) -> float:
        """NAV return over the window, as a fraction of the starting cash (SD-3)."""
        return self.final_nav / self.params.start_cash - 1.0

    def daily_ledger(self) -> pd.DataFrame:
        """The ledger at each session's **closing bar** — the table the page prints.

        SPEC §9: the hourly frame is what the chart draws, the daily roll-up is what
        a reader checks a week against by hand. The roll-up is a *selection* of
        hourly rows, not a re-aggregation, so a number in the table is a number in
        the chart.

        **Every session gets a row.** A half session has no 15:00 ET bar at all, and
        selecting on the hour alone made that whole day vanish from the table — no
        row, no note, and `final_nav` then quoting the *previous* session's close as
        the window's. Settlement already had a policy for this bar (§7's
        carry-forward); the roll-up now has the same one, and takes the session's
        last bar at or before the close instead. The substitution needs no flag
        because the row's own ``ts`` shows it: a 12:00 stamp in a column of 15:00s.
        """
        if self.ledger.empty:
            return self.ledger.copy()
        stamps = pd.DatetimeIndex(self.ledger["ts"])
        eligible = self.ledger[stamps.hour <= CLOSING_BAR_HOUR_ET]
        if eligible.empty:
            return eligible.reset_index(drop=True)
        by_day = pd.DatetimeIndex(eligible["ts"]).date
        return eligible.groupby(by_day, sort=True).tail(1).reset_index(drop=True)

    def blotter_csv(self) -> str:
        """The blotter as bytes, for I-12. Same tape + same ``Params`` -> same string."""
        return self.blotter.to_csv(index=False, lineterminator="\n")


# --------------------------------------------------------------------------
# The window — SPEC §3.2 item 3
# --------------------------------------------------------------------------
def _require_matching_underlying(tape: "Tape", params: Params) -> None:
    """Refuse a tape for a different name than ``Params`` describes.

    ``tape.stock`` selects on ``kind == "stock"``, never on the RIC, so handing the
    engine somebody else's tape produces a complete, plausible, entirely wrong book
    — priced off one underlying and written against another's chain. It is exactly
    the failure that renders without erroring, so it is refused at the door.
    """
    stock = tape.stock
    if stock.empty:
        raise ValueError(
            f"the tape carries no stock bars for {params.underlying}; the calendar "
            "(SPEC §3.2) has nothing to come from."
        )
    names = sorted(set(stock["ric"]))
    if names != [params.underlying]:
        raise ValueError(
            f"this tape's stock is {names}, but Params.underlying is "
            f"{params.underlying!r}. Pass the tape pulled for this name (RUNBOOK §8)."
        )


def window_weeks(tape: "Tape", params: Params) -> list[Week]:
    """The tape's trading weeks that lie inside ``[params.start, params.end]``.

    Two refusals, both from SPEC §3.2 item 3:

    * ``end`` must be a **last-session day**, so the final call resolves inside the
      window. A window ending mid-week would leave a short call open at the last
      bar, and the engine would have to invent a close-out to balance the book —
      exactly the kind of invented price DR-1 forbids.
    * a week may not **straddle** a boundary. Silently trading the part of a week
      that happens to be inside the window would book an entry whose expiry session
      the tape does not carry; silently dropping it would break I-10, which says
      every week without an entry is in the skip log with a reason.

    Short weeks are kept (flagged), because they are skips with a reason, not
    absences.
    """
    inside: list[Week] = []
    straddling: list[Week] = []
    for week in tape.weeks(params):
        within = [d for d in week.sessions if params.start <= d <= params.end]
        if not within:
            continue
        (inside if len(within) == len(week.sessions) else straddling).append(week)

    if straddling:
        names = ", ".join(w.label for w in straddling)
        raise ValueError(
            f"week(s) {names} straddle the window {params.start} - {params.end}: the "
            "tape carries only part of them. Set the window to whole weeks of the "
            "tape (SPEC §3.2 item 3) or re-pull the tape for this window."
        )
    if not inside:
        raise ValueError(
            f"no trading weeks on the tape inside {params.start} - {params.end}. "
            "Check the tape's window against `Params.start` / `Params.end`."
        )
    last = inside[-1]
    if last.expiry_day != params.end:
        raise ValueError(
            f"`end` is {params.end}, which is not a last-session day: the tape's final "
            f"week {last.label} ends {last.expiry_day}. The window must end on the "
            "session the last call expires on, so the book never carries an open "
            "position past the last bar (SPEC §3.2 item 3)."
        )
    return inside


# --------------------------------------------------------------------------
# Reading the tape at a bar
# --------------------------------------------------------------------------
def _scalar(value) -> float | None:
    """A float, or ``None`` for anything absent. NaN is absent; 0.0 is a number."""
    if value is None:
        return None
    value = float(value)
    return None if np.isnan(value) else value


def _stock_print(stock_by_ts: dict, ts) -> float | None:
    row = stock_by_ts.get(ts)
    return None if row is None else _scalar(row.get("trdprc_1"))


def settlement_print(
    stock_by_ts: dict, session_bars: list, closing: pd.Timestamp | None
) -> tuple[float | None, pd.Timestamp | None]:
    """The stock print settlement resolves against, and the bar it came from.

    The closing bar (SPEC §7) when it carries a print; otherwise the **last print in
    that session at or before the close** — S-7's carry-forward, applied to the one
    read the engine cannot skip. Bars after the closing bar are never eligible: they
    are the post-close stubs T-62 found, and resolving a contract against one would
    be the ``max(ts)`` defect wearing a different hat.

    ``(None, None)`` when the session carries no print at all before the close. The
    caller raises on that — an open call with nothing to resolve it against is a
    broken tape, not a market fact.
    """
    if closing is not None:
        direct = _stock_print(stock_by_ts, closing)
        if direct is not None:
            return direct, closing
    for ts in reversed(session_bars):
        if closing is not None and ts > closing:
            continue
        if closing is None and ts.hour > CLOSING_BAR_HOUR_ET:
            continue
        price = _stock_print(stock_by_ts, ts)
        if price is not None:
            return price, ts
    return None, None


# --------------------------------------------------------------------------
# The weekly loop — SPEC §4
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class _Booking:
    """One blotter row with the two things the blotter's own columns do not carry:
    the bar it sits on as a timestamp, and the week that booked it."""

    week: str
    ts: pd.Timestamp
    row: BlotterRow


def run_backtest(tape: "Tape", params: Params | None = None) -> Book:
    """Run the covered-call strategy over ``tape`` and return the book (FR-15).

    Pure and deterministic: the same tape and the same ``Params`` produce a
    byte-identical blotter (I-12). Nothing here reads the clock, the network or a
    file.

    The loop is SPEC §4 exactly — per week, at the entry bar of the first session:
    spot, strike, quote, then ``BUY 100`` (only when flat) and ``SELL 1``; at the
    **closing bar** of the last session, ``EXPIRE`` or ``ASSIGN`` + a stock ``SELL``
    at the strike. Any of the three reads failing skips the week *and records why*,
    and in the flat state a missing call quote means no stock is bought either —
    the brief's entry is the combo, and the stock alone is a different strategy.
    """
    params = params or Params()
    _require_matching_underlying(tape, params)
    weeks = window_weeks(tape, params)

    stock = tape.stock
    stock_by_ts = {
        ts: row for ts, row in zip(stock["ts"], stock.to_dict("records"))
    }
    bars_by_day: dict[dt.date, list] = {}
    for ts in tape.stock_index:
        bars_by_day.setdefault(ts.date(), []).append(ts)
    stock_index = tape.stock_index
    option_mid = _option_mid_lookup(tape)
    contract_rics = _contract_rics(tape)

    bookings: list[_Booking] = []
    skips: list[SkipRecord] = []
    entry_bars: dict[pd.Timestamp, str] = {}
    shares = 0

    for week in weeks:
        state = STATE_STOCK_ONLY if shares else STATE_FLAT

        if week.is_short:
            skips.append(SkipRecord(
                week.label, SKIP_SHORT_WEEK, state,
                f"{len(week.sessions)} session(s) on the tape "
                f"({week.entry_day}) — nothing can both enter and expire",
            ))
            continue

        bar = entry_bar_ts(stock_index, week.entry_day, params)
        spot = None if bar is None else _stock_print(stock_by_ts, bar)
        if spot is None:
            hour = params.entry_bar_hour_et
            skips.append(SkipRecord(
                week.label, SKIP_NO_STOCK_PRINT, state,
                f"no stock print at the {hour:02d}:00 ET bar on {week.entry_day}",
            ))
            continue

        chain = tape.strikes_for(week.expiry_day)
        strike = select_strike(chain, spot, params)
        if strike is None:
            top = f"{max(chain):g}" if chain else "none listed"
            skips.append(SkipRecord(
                week.label, SKIP_NO_STRIKE, state,
                f"no listed strike at or above S={spot:.4f} "
                f"(chain of {len(chain)}, highest {top})",
            ))
            continue

        ric = contract_rics[(week.expiry_day, strike)]
        occ = occ_symbol(params.root, week.expiry_day, "C", strike)
        mid = option_mid.get((week.expiry_day, strike, bar))
        if mid is None:
            skips.append(SkipRecord(
                week.label, SKIP_NO_QUOTE, state,
                f"K={strike:g} has no valid quote at {bar:%Y-%m-%d %H:%M}"
                + ("" if shares else " — no stock bought either; the entry is the combo"),
            ))
            continue

        if not shares:
            bookings.append(_Booking(
                week.label, bar, entry_stock_row(bar, params.underlying, spot, params)
            ))
            shares += params.shares
        bookings.append(_Booking(
            week.label, bar,
            entry_call_row(bar, ric, occ, strike, spot, mid, params),
        ))
        entry_bars[bar] = week.label

        # --- settlement, SPEC §7 -------------------------------------------
        closing = closing_bar_ts(stock_index, week.expiry_day, params)
        session_bars = bars_by_day.get(week.expiry_day, [])
        settle, settle_bar = settlement_print(stock_by_ts, session_bars, closing)
        if settle is None:
            raise ValueError(
                f"{week.label}: the book is short {ric} but the expiry session "
                f"{week.expiry_day} carries no stock print at or before the "
                "closing bar, so the call cannot be resolved (I-7). The tape is "
                "incomplete for this week — re-pull it (RUNBOOK §8)."
            )

        if is_itm(settle, strike, params):
            rows = assign_rows(settle_bar, ric, occ, params.underlying,
                               strike, settle, params)
            shares -= params.shares
        else:
            rows = [expire_row(settle_bar, ric, occ, strike, settle, params)]
        if closing is None or settle_bar != closing:
            rows = [_note_carried_settlement(rows[0], closing)] + rows[1:]
        bookings.extend(_Booking(week.label, settle_bar, row) for row in rows)

    blotter = _frame([b.row.as_dict() for b in bookings], BLOTTER_COLUMNS)
    skip_frame = _frame([s.as_dict() for s in skips], SKIP_COLUMNS)
    ledger = build_ledger(tape, params, bookings, entry_bars, option_mid)
    weekly = _weekly_from_bookings(weeks, bookings, skips)
    return Book(
        params=params,
        blotter=blotter,
        skips=skip_frame,
        ledger=ledger,
        weekly=weekly,
        synthetic=tape.synthetic,
        diagnostics={
            "weeks_considered": len(weeks),
            "weeks_entered": len(entry_bars),
            "weeks_skipped": len(skips),
            "window": [str(params.start), str(params.end)],
        },
    )


def _note_carried_settlement(row: BlotterRow, closing) -> BlotterRow:
    """Say in the row itself that the settlement print is not the closing bar's.

    A reader checking a week by hand looks the bar up; if the engine silently read a
    different one, the number would not be there. The note carries the substitution
    rather than a paragraph elsewhere carrying it.
    """
    which = "no closing bar" if closing is None else f"closing bar {closing:%H:%M} had no print"
    return BlotterRow(**{**row.__dict__, "note": f"{row.note} S_exp_carried ({which})"})


def _option_mid_lookup(tape: "Tape") -> dict:
    """``{(expiry, strike, ts): mid}`` for every option bar with a **valid** mid.

    ``mid`` is already NaN wherever SPEC §6.1 refuses the quote (``tape.attach_mid``),
    so dropping the NaNs here is what makes "the engine reads only ``mid``" true: a
    key that is absent from this map is a bar the strategy may not fill on, and
    there is no second path to a price.

    **The key is the contract, never the RIC string.** SPEC §3.3: a contract answers
    under the caret form or the live form depending on how long ago it expired, and
    which one a tape carries depends on the *date of the pull* (T-77 measured the
    same window answering differently two days apart). A mark looked up by RIC
    therefore misses on a perfectly good tape, and misses **silently** — the mark
    simply carries forward. ``(expiry, strike, ts)`` names the contract itself and
    cannot drift with the spelling.
    """
    opts = tape.options
    lookup: dict = {}
    if opts.empty:
        return lookup
    for expiry, strike, ts, mid in zip(
        opts["expiry"], opts["strike"], opts["ts"], opts["mid"]
    ):
        value = _scalar(mid)
        if value is None or strike is None or pd.isna(strike):
            continue
        lookup[(expiry, float(strike), ts)] = value
    return lookup


def _contract_rics(tape: "Tape") -> dict:
    """``{(expiry, strike): ric}`` — the RIC **the tape actually answered under**.

    The blotter must name a contract a reader can find on the tape, so the engine
    reads the spelling rather than rebuilding it: ``build_option_ric(..., expired=True)``
    hard-codes the caret form, and on a tape pulled close to expiry that names a
    contract with no bars (SPEC §3.3). Sorted so a tape carrying a contract under
    both forms still produces a byte-identical blotter (I-12).
    """
    opts = tape.options
    rics: dict = {}
    if opts.empty:
        return rics
    for expiry, strike, ric in sorted(
        {(e, float(k), r) for e, k, r in
         zip(opts["expiry"], opts["strike"], opts["ric"])
         if k is not None and not pd.isna(k)},
        key=lambda row: (str(row[0]), row[1], row[2]),
    ):
        rics.setdefault((expiry, strike), ric)
    return rics


def _frame(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)


# --------------------------------------------------------------------------
# The ledger and the Reg T account — SPEC §9
# --------------------------------------------------------------------------
def build_ledger(
    tape: "Tape",
    params: Params,
    bookings: list[_Booking],
    entry_bars: dict,
    option_mid: dict | None = None,
) -> pd.DataFrame:
    """One row per stock bar in the window, computed from the blotter and the tape.

    Every quantity is a projection: ``cash`` is ``start_cash`` plus the blotter's
    ``cash_delta`` at or before the bar (DR-3), ``shares`` and ``short_calls`` are
    the same running sum over sides, and the marks come off the tape. Nothing is
    decided here — which is why I-1 can reconcile the ledger against the blotter
    alone, and why a defect in the loop shows up as a contradiction rather than as
    two numbers that agree because one copied the other.

    Marks are **carried forward, never interpolated** (S-7), and ``mark_carried``
    says so on any row where either mark came from an earlier bar. While short, at
    and after the expiry session's closing bar the call is marked at **intrinsic**
    ``max(S - K, 0)`` so the mark and the settlement cannot disagree; under normal
    operation settlement clears the position on that same bar, so this is the belt
    to that braces.
    """
    option_mid = option_mid if option_mid is not None else _option_mid_lookup(tape)
    stock = tape.stock
    stock_by_ts = {ts: row for ts, row in zip(stock["ts"], stock.to_dict("records"))}
    bars = [
        ts for ts in tape.stock_index
        if params.start <= ts.date() <= params.end
    ]
    ordered = sorted(bookings, key=lambda b: (b.ts, _SIDE_ORDER.get(b.row.side, 9)))

    cash = float(params.start_cash)
    shares = 0
    short_calls = 0
    call: dict | None = None
    stock_mark: float | None = None
    call_mark: float | None = None
    cursor = 0
    rows = []

    for ts in bars:
        while cursor < len(ordered) and ordered[cursor].ts <= ts:
            booking = ordered[cursor]
            row = booking.row
            cash += row.cash_delta
            if row.side == "BUY":
                shares += row.qty
            elif row.side == "SELL" and row.instrument == params.underlying:
                shares -= row.qty
            elif row.side == "SELL":
                short_calls += row.qty
                call = _call_identity(row)
                call_mark = row.fill
            else:                                    # EXPIRE / ASSIGN
                short_calls -= row.qty
                call = None
                call_mark = None
            cursor += 1

        carried = False
        fresh_stock = _stock_print(stock_by_ts, ts)
        if fresh_stock is None:
            carried = carried or stock_mark is not None
        else:
            stock_mark = fresh_stock

        if short_calls and call is not None:
            fresh_call = _call_mark(call, ts, stock_mark, option_mid, params)
            if fresh_call is None:
                carried = carried or call_mark is not None
            else:
                call_mark = fresh_call

        lmv = 0.0 if shares == 0 or stock_mark is None else shares * stock_mark
        mv = 0.0 if short_calls == 0 or call_mark is None else -short_calls * 100 * call_mark
        nav = cash + lmv + mv
        im, mm = IM_RATE * lmv, MM_RATE * lmv
        available, excess = nav - im, nav - mm
        rows.append({
            "ts": ts,
            "week": f"{ts.isocalendar()[0]}-W{ts.isocalendar()[1]:02d}",
            "entry": ts in entry_bars,
            "shares": shares,
            "short_calls": short_calls,
            "call_ric": "" if call is None else call["ric"],
            "call_strike": np.nan if call is None else call["strike"],
            "call_expiry": None if call is None else call["expiry"],
            "cash": round(cash, MONEY_DP),
            "stock_mark": np.nan if stock_mark is None else stock_mark,
            "call_mark": np.nan if (call_mark is None or not short_calls) else call_mark,
            "mark_carried": bool(carried),
            "lmv": round(lmv, MONEY_DP),
            "option_mv": round(mv, MONEY_DP),
            "nav": round(nav, MONEY_DP),
            "im": round(im, MONEY_DP),
            "mm": round(mm, MONEY_DP),
            "available": round(available, MONEY_DP),
            "excess": round(excess, MONEY_DP),
            "flag": FLAG_NEG_AVAILABLE if (ts in entry_bars and available < 0) else "",
        })
    return _frame(rows, LEDGER_COLUMNS)


#: Within one bar the two settlement rows must fold in the order SPEC §7 books them:
#: the assignment first, then the stock leaving at the strike. A BUY precedes the
#: SELL of the call for the same reason — the entry is one combo, in the brief's order.
_SIDE_ORDER = {"BUY": 0, "ASSIGN": 1, "EXPIRE": 1, "SELL": 2}


def _call_identity(row: BlotterRow) -> dict:
    """The contract a ``SELL`` row put the book short, read back out of the row.

    Parsed from the row rather than remembered from the loop, so the ledger cannot
    be short a contract the blotter does not name.
    """
    parsed = parse_option_ric(row.instrument)
    return {"ric": row.instrument, "strike": float(parsed["strike"]),
            "expiry": parsed["expiry"]}


def _call_mark(call: dict, ts, stock_mark, option_mid: dict, params: Params):
    """The short call's mark at ``ts`` — its mid, or intrinsic once expiry has come.

    SPEC §9: on the expiry bar the mark is ``max(S - K, 0)`` so the mark and the
    settlement agree. ``None`` means "nothing new at this bar", and the caller
    carries the previous mark forward (S-7).
    """
    expiry = call["expiry"]
    if ts.date() > expiry or (ts.date() == expiry and ts.hour >= CLOSING_BAR_HOUR_ET):
        if stock_mark is None:
            return None
        return max(stock_mark - call["strike"], 0.0)
    return option_mid.get((expiry, call["strike"], ts))


# --------------------------------------------------------------------------
# The weekly projection — derived from the blotter, never decided
# --------------------------------------------------------------------------
def _weekly_from_bookings(
    weeks: list[Week], bookings: list[_Booking], skips: list[SkipRecord]
) -> pd.DataFrame:
    """One row per week considered, read back out of the rows that were booked.

    Built from ``bookings`` and ``skips`` only — it holds no number the blotter or
    the skip log does not already hold, so the notebook's week-by-week table and
    the page's blotter cannot disagree (SPEC §1).
    """
    by_week: dict[str, list[BlotterRow]] = {}
    for booking in bookings:
        by_week.setdefault(booking.week, []).append(booking.row)
    skip_by_week = {s.week: s for s in skips}

    rows = []
    for week in weeks:
        booked = by_week.get(week.label, [])
        skip = skip_by_week.get(week.label)
        record = {
            "week": week.label,
            "entry_day": week.entry_day,
            "expiry_day": week.expiry_day,
            "outcome": "", "state_at_entry": "",
            "spot": np.nan, "strike": np.nan, "mid": np.nan,
            "premium": np.nan, "settle": np.nan, "detail": "",
        }
        if skip is not None:
            record.update(outcome=skip.reason, state_at_entry=skip.state_at_skip,
                          detail=skip.detail)
            rows.append(record)
            continue

        entry = next(r for r in booked if r.side == "SELL" and r.occ)
        exit_row = next(r for r in booked if r.side in ("EXPIRE", "ASSIGN"))
        bought = any(r.side == "BUY" for r in booked)
        record.update(
            outcome=exit_row.side,
            state_at_entry=STATE_FLAT if bought else STATE_STOCK_ONLY,
            spot=_note_value(entry.note, "S="),
            strike=_note_value(entry.note, "K="),
            mid=float(entry.fill),
            premium=float(entry.cash_delta),
            settle=_note_value(exit_row.note, "S_exp="),
            detail=exit_row.note,
        )
        rows.append(record)
    return _frame(rows, WEEKLY_COLUMNS)


def _note_value(note: str, key: str) -> float:
    """Pull one ``key=value`` number out of a blotter note (SPEC §8's ``note``).

    The note is where the engine already prints "the one number a reader needs", so
    the weekly table reads it back from there rather than being handed a second copy
    that could drift from what the page shows.
    """
    for token in note.split():
        if token.startswith(key):
            return float(token[len(key):])
    return float("nan")
