"""The live leg — FR-21. The strategy run forward, with simulated capital.

Three commands::

    python -m options_surface_lab.covered_call.live capture --expiry 2026-09-18
    python -m options_surface_lab.covered_call.live enter
    python -m options_surface_lab.covered_call.live settle

``capture`` is the only thing here that touches the network. It reads the entry
bar's quotes and writes them into ``covered_call_live.json``; ``enter`` and
``settle`` are pure functions of that captured payload, so what gets booked can be
replayed, tested offline (NFR-4) and audited after the fact.

**This is not a race.** T-62 (2026-09-13) established that LSEG serves hourly
``BID``/``ASK`` *history* for a live, unexpired weekly. So the 15:00-16:00 ET bar
is captured *after it completes* — any time that evening — and the booked trade is
identical whenever the command runs, because the bar is immutable. Nothing after
16:00 enters the decision.

Every rule it applies comes from :mod:`options_surface_lab.covered_call.rules`, the
same module the backtest engine will use, so a live row and a backtested row are
built by one code path (NFR-5).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from ..option_surface_utils import build_option_ric, occ_symbol
from .rules import (
    SKIP_NO_QUOTE,
    SKIP_NO_STOCK_PRINT,
    SKIP_NO_STRIKE,
    BlotterRow,
    Params,
    SkipRecord,
    assign_rows,
    closing_bar_ts,
    entry_bar_ts,
    entry_call_row,
    entry_stock_row,
    expire_row,
    format_bar_time,
    is_itm,
    select_strike,
    to_exchange_time,
    trading_weeks,
    valid_mid,
)

#: State lives beside the code, anchored to ``__file__`` and never to the CWD.
STATE_PATH = Path(__file__).resolve().parents[2] / "covered_call_live.json"

#: How many $1 strikes either side of spot to request. T-62 measured the step at $1.00.
STRIKE_BAND = 12

#: Fields the tape needs from both instruments (SPEC §3.1).
#:
#: The last four are the **synchronisation evidence**. At hourly resolution the two
#: legs cannot be read at one instant, so the gap between them is *measured and
#: recorded* rather than assumed away: `C_SEC_OFST` is the offset of the bar's last
#: **trade**, and `HIGH_1`/`LOW_1` say how far spot travelled inside the bar the
#: strike was chosen from. Note `C_SEC_OFST` times the last *trade*, not the last
#: quote update — LSEG exposes no offset for the quote, so nothing here may claim
#: when the bid and ask last moved.
QUOTE_FIELDS = ["TRDPRC_1", "BID", "ASK", "HIGH_1", "LOW_1", "O_SEC_OFST", "C_SEC_OFST"]


# --------------------------------------------------------------------------
# State — a plain JSON document, committed, rendered by the page
# --------------------------------------------------------------------------
def empty_state(params: Params) -> dict:
    return {
        "params": {
            "underlying": params.underlying, "root": params.root,
            "start_cash": params.start_cash, "entry_bar": params.entry_bar,
            "strike_rule": params.strike_rule, "itm_rule": params.itm_rule,
            "shares": params.shares, "contracts": params.contracts, "tz": params.tz,
            "described": params.describe_strike_rule(),
        },
        "position": {"shares": 0, "short_calls": 0, "call": None},
        "cash": params.start_cash,
        "blotter": [],
        "skips": [],
        "captures": [],
    }


def load_state(params: Params, path: Path = STATE_PATH) -> dict:
    if not path.exists():
        return empty_state(params)
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict, path: Path = STATE_PATH) -> None:
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


# --------------------------------------------------------------------------
# capture() — the only network in this module
# --------------------------------------------------------------------------
@contextmanager
def lseg_session():
    """Open a Workspace session for the duration of a capture, and always close it.

    The desktop app must be running and logged in (RUNBOOK §3). Import is local so
    that merely importing this module stays offline — the tests never reach here
    (NFR-4).
    """
    import lseg.data as ld

    ld.open_session()
    _require_open_session(ld)
    try:
        yield ld
    finally:
        ld.close_session()


def _require_open_session(ld) -> None:
    """Fail here if the session did not actually open, rather than three steps later.

    ``ld.open_session()`` does **not** raise when the handshake fails: it logs, returns,
    and leaves a *closed* session behind. Every request then fails with "Session is not
    opened", which this module would otherwise log as ``SKIP_NO_STOCK_PRINT`` — a
    *skipped week* written into the live book for a desktop-side problem (found 2026-09-14 on
    T-77's pull, where a ready proxy never answered the handshake). I-10 says a week
    appears once, so that skip would then refuse the re-run.
    """
    state = str(getattr(ld.session.get_default(), "open_state", "unknown"))
    if not state.endswith("Opened"):
        raise RuntimeError(
            f"LSEG session did not open (state {state}). The API proxy can be up and "
            "answering /api/status while the desktop never completes the app-key "
            "handshake — so 'Workspace is running' is not the check. Confirm Workspace "
            "is **signed in** and loading data, restart it if the handshake still hangs, "
            "then re-run. Nothing was requested and nothing was written (RUNBOOK §3)."
        )


def _history(ld, universe, fields, start, end, interval="hourly"):
    """Fail-soft ``get_history``. Returns ``(df_or_None, error_or_None)`` (DR-10)."""
    try:
        return ld.get_history(universe=universe, fields=fields,
                              start=str(start), end=str(end), interval=interval), None
    except Exception as exc:  # a guessed RIC must fail soft, never crash
        return None, f"{type(exc).__name__}: {exc}"


def _to_exchange_time(df: pd.DataFrame, params: Params) -> pd.DataFrame:
    """LSEG hands back tz-naive UTC stamped at the bar's START (T-62, SPEC §3.1).

    The conversion itself lives in ``rules`` so that this module and ``tape`` cannot
    apply the OQ-11 convention differently (T-56).
    """
    out = df.copy()
    out.index = to_exchange_time(out.index, params)
    return out


def _row_at(df: pd.DataFrame, ts) -> dict:
    if df is None or ts is None or ts not in df.index:
        return {}
    row = df.loc[ts]
    return {
        str(col).lower(): (None if pd.isna(row[col]) else float(row[col]))
        for col in df.columns
    }


def capture(
    expiry: dt.date,
    params: Params | None = None,
    on: dt.date | None = None,
    band: int = STRIKE_BAND,
) -> dict:
    """Read the entry bar and the near-the-money call chain for ``expiry``.

    ``on`` is the session whose entry bar is read; it defaults to ``expiry``'s
    Monday. Contracts are requested in the **live** RIC form (no caret) because
    the contract has not expired yet — T-62 proved the shape and proved that a
    recently expired one answers only to the live form for some days afterwards.
    """
    params = params or Params()
    week_monday = expiry - dt.timedelta(days=4)

    snapshot = {
        "captured_at": dt.datetime.now().isoformat(timespec="seconds"),
        "expiry": str(expiry), "session": str(on or week_monday), "entry_bar": None,
        "underlying": {"ric": params.underlying}, "chain": [],
        "diagnostics": {"stock_error": None, "option_error": None, "requested": [],
                        "bars_in_session": [], "ric_form": "live",
                        "session_source": "given"
                        if on else "UNRESOLVED — no bars on the tape yet"},
    }

    with lseg_session() as ld:
        stock_df, stock_err = _history(
            ld, params.underlying, QUOTE_FIELDS, week_monday, expiry + dt.timedelta(days=1)
        )
        snapshot["diagnostics"]["stock_error"] = stock_err
        if stock_df is None or len(stock_df) == 0:
            return snapshot

        stock = _to_exchange_time(stock_df, params)
        if on is None:
            # DR-7: the entry day is the week's FIRST SESSION as the tape reports it,
            # never "Monday" by arithmetic. Running with `expiry - 4 days` would have
            # entered on Labor Day 2026-09-07, found no bars, and logged a false skip.
            weeks = trading_weeks(stock.index, params)
            if not weeks:
                return snapshot
            on = weeks[0].entry_day
            snapshot["session"] = str(on)
            snapshot["diagnostics"]["session_source"] = "first session on the tape (DR-7)"

        bar = entry_bar_ts(stock.index, on, params)
        snapshot["diagnostics"]["bars_in_session"] = [
            format_bar_time(t) for t in stock.index if t.date() == on
        ]
        snapshot["entry_bar"] = None if bar is None else format_bar_time(bar)
        under = _row_at(stock, bar)
        snapshot["underlying"] = {"ric": params.underlying, **under}
        spot = under.get("trdprc_1")
        if spot is None:
            return snapshot

        centre = int(round(spot))
        strikes = [float(centre + i) for i in range(-band, band + 1)]
        rics = [build_option_ric(params.root, expiry, "C", k, expired=False) for k in strikes]
        snapshot["diagnostics"]["requested"] = rics

        opt_df, opt_err = _history(ld, rics, QUOTE_FIELDS, on, on + dt.timedelta(days=1))
        snapshot["diagnostics"]["option_error"] = opt_err
        if opt_df is None or len(opt_df) == 0:
            return snapshot

        opts = _to_exchange_time(opt_df, params)
        for strike, ric in zip(strikes, rics):
            quote = _quote_for(opts, ric, bar)
            if quote is None:
                continue
            snapshot["chain"].append({
                "ric": ric, "strike": strike, "ric_form": "live",
                "occ": occ_symbol(params.root, expiry, "C", strike), **quote,
            })
    return snapshot


def _quote_for(opts: pd.DataFrame, ric: str, bar) -> dict | None:
    """Pull one RIC's bid/ask/print at ``bar`` out of a multi-RIC history frame."""
    if bar is None or bar not in opts.index:
        return None
    row = opts.loc[bar]
    out = {}
    for field in QUOTE_FIELDS:
        key = (ric, field)
        value = row.get(key, row.get(field) if opts.columns.nlevels == 1 else None)
        out[field.lower()] = None if value is None or pd.isna(value) else float(value)
    return out if any(v is not None for v in out.values()) else None


# --------------------------------------------------------------------------
# enter() / settle() — pure functions of a captured payload
# --------------------------------------------------------------------------
def sync_gap_seconds(snapshot: dict, contract: dict) -> float | None:
    """Seconds between the two legs' last trades in the entry bar, or ``None``.

    The brief's fill assumption rests on the stock print and the option quote being
    contemporaneous. Hourly bars cannot make them simultaneous, so the residual gap
    is booked alongside the trade instead of being left to a reader's goodwill.
    """
    a = (snapshot.get("underlying") or {}).get("c_sec_ofst")
    b = contract.get("c_sec_ofst")
    if a is None or b is None:
        return None
    return abs(float(a) - float(b))


def plan_entry(
    snapshot: dict, state: dict, params: Params
) -> tuple[list[BlotterRow], SkipRecord | None]:
    """Decide the week's entry from a captured payload. No network, no I/O.

    The combo is **one decision**: in the flat state a missing call quote means no
    stock is bought either, because buying the shares alone would be a different
    strategy (SPEC §4 step 3).
    """
    week = snapshot.get("session", "?")
    holding = state["position"]["shares"] > 0
    state_name = "STOCK_ONLY" if holding else "FLAT"

    bar = snapshot.get("entry_bar")
    spot = (snapshot.get("underlying") or {}).get("trdprc_1")
    if bar is None or spot is None:
        return [], SkipRecord(week, SKIP_NO_STOCK_PRINT, state_name,
                              "no stock print at the entry bar")

    chain = snapshot.get("chain") or []
    strike = select_strike([c["strike"] for c in chain], spot, params)
    if strike is None:
        return [], SkipRecord(week, SKIP_NO_STRIKE, state_name,
                              f"no listed strike at or above S={spot:.4f}")

    contract = next(c for c in chain if c["strike"] == strike)
    mid = valid_mid(contract.get("bid"), contract.get("ask"))
    if mid is None:
        return [], SkipRecord(
            week, SKIP_NO_QUOTE, state_name,
            f"K={strike:g} bid={contract.get('bid')} ask={contract.get('ask')}"
            + ("" if holding else " — no stock bought either; the entry is the combo"),
        )

    rows: list[BlotterRow] = []
    if not holding:
        rows.append(entry_stock_row(bar, params.underlying, spot, params))
    rows.append(
        entry_call_row(bar, contract["ric"], contract["occ"], strike, spot, mid, params,
                       sync_gap_s=sync_gap_seconds(snapshot, contract))
    )
    return rows, None


def plan_settlement(
    snapshot: dict, state: dict, params: Params
) -> tuple[list[BlotterRow], SkipRecord | None]:
    """Resolve the open call at the expiry session's closing bar (SPEC §7).

    Settlement needs no option quote: an ITM call with no bid or ask on the expiry
    bar is still assigned.
    """
    call = state["position"].get("call")
    if not call or state["position"]["short_calls"] == 0:
        return [], None

    bar = snapshot.get("entry_bar")
    settle = (snapshot.get("underlying") or {}).get("trdprc_1")
    if bar is None or settle is None:
        return [], SkipRecord(snapshot.get("session", "?"), SKIP_NO_STOCK_PRINT, "COVERED",
                              "no settlement print at the closing bar")

    strike = float(call["strike"])
    if is_itm(settle, strike, params):
        return assign_rows(bar, call["ric"], call["occ"], params.underlying,
                           strike, settle, params), None
    return [expire_row(bar, call["ric"], call["occ"], strike, settle, params)], None


def apply_rows(state: dict, rows: list[BlotterRow], snapshot: dict, params: Params) -> dict:
    """Fold booked rows into cash, the position and the blotter. DR-3: only rows move cash."""
    for row in rows:
        state["cash"] = round(state["cash"] + row.cash_delta, 4)
        state["blotter"].append(row.as_dict())
        if row.side == "BUY":
            state["position"]["shares"] += row.qty
        elif row.side == "SELL" and row.instrument == params.underlying:
            state["position"]["shares"] -= row.qty
        elif row.side == "SELL":
            state["position"]["short_calls"] += row.qty
            contract = next(c for c in snapshot["chain"] if c["ric"] == row.instrument)
            state["position"]["call"] = {
                "ric": contract["ric"], "occ": contract["occ"],
                "strike": contract["strike"], "expiry": snapshot["expiry"],
            }
        elif row.side in ("EXPIRE", "ASSIGN"):
            state["position"]["short_calls"] -= row.qty
            state["position"]["call"] = None
    return state


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def coming_friday(today: dt.date | None = None) -> dt.date:
    """The current week's Friday — the contract the live leg writes.

    DR-7 takes expiries off the stock tape so a holiday is never invented, but the
    live leg is looking *forward*: that week's tape does not exist yet, so the date
    has to come from the calendar. It fails soft rather than guessing — a Friday
    holiday means the RIC does not resolve, the chain comes back empty, and the
    week is logged as ``SKIP_NO_STRIKE`` instead of being booked against a contract
    that was never listed.
    """
    today = today or dt.date.today()
    return today + dt.timedelta(days=(4 - today.weekday()) % 7)


def already_booked(state: dict, session: str, sides: tuple[str, ...]) -> bool:
    """Has this session already produced one of these sides? Guards a double run."""
    return any(
        row["time"].startswith(session) and row["side"] in sides
        for row in state["blotter"]
    )


def _run(action: str, expiry: dt.date, on: dt.date | None, path: Path, params: Params) -> int:
    state = load_state(params, path)
    sides = ("BUY", "SELL") if action == "enter" else ("EXPIRE", "ASSIGN")

    snapshot = capture(expiry, params, on=on)
    state["captures"].append(snapshot)
    session = snapshot["session"]          # capture may have resolved it off the tape (DR-7)
    if action != "capture" and already_booked(state, session, sides):
        print(f"REFUSED: {session} already has {action} rows in the blotter.")
        return 1
    if action != "capture" and any(s["week"] == session for s in state["skips"]):
        print(f"REFUSED: {session} is already in the skip log.")
        print("I-10: a week appears once. Inspect the state file before re-running.")
        return 1

    if action == "capture":
        save_state(state, path)
        print(f"captured {len(snapshot['chain'])} contracts at bar {snapshot['entry_bar']}")
        return 0

    planner = plan_entry if action == "enter" else plan_settlement
    rows, skip = planner(snapshot, state, params)
    if skip is not None:
        state["skips"].append(skip.as_dict())
        save_state(state, path)
        print(f"SKIPPED {skip.reason}: {skip.detail}")
        print("nothing booked — the rule is the rule on day one.")
        return 0

    if not rows:
        save_state(state, path)
        print("nothing to do: no open call to settle.")
        return 0

    apply_rows(state, rows, snapshot, params)
    save_state(state, path)
    for row in rows:
        print(f"  {row.time}  {row.side:<7} {row.qty:>4} {row.instrument:<24} "
              f"fill={row.fill:<10.4f} cash={row.cash_delta:+.2f}  {row.note}")
    print(f"cash {state['cash']:.2f} | shares {state['position']['shares']} | "
          f"short calls {state['position']['short_calls']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The covered call, run forward (FR-21).")
    parser.add_argument("action", choices=["capture", "enter", "settle"])
    parser.add_argument("--expiry", default=None,
                        help="the contract's expiry, YYYY-MM-DD; defaults to this week's Friday")
    parser.add_argument("--on", default=None,
                        help="session to read; defaults to the Monday before the expiry")
    parser.add_argument("--state", default=str(STATE_PATH))
    args = parser.parse_args(argv)
    expiry = dt.date.fromisoformat(args.expiry) if args.expiry else coming_friday()
    on = dt.date.fromisoformat(args.on) if args.on else None
    if args.action == "settle" and args.on is None:
        on = expiry          # settlement reads the expiry session's own closing bar
    session = str(on) if on else "the week's first session, read off the tape (DR-7)"
    print(f"{args.action}: expiry {expiry}, session {session}, "
          f"entry bar = {params_hour(Params())}")
    return _run(args.action, expiry, on, Path(args.state), Params())


def params_hour(params: Params) -> str:
    """The entry bar in words, so a run says out loud which bar it is about to read."""
    return f"{params.entry_bar_hour_et:02d}:00 ET ({params.entry_bar})"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
