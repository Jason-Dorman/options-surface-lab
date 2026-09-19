"""Assignment 2's page — SPEC §11's panels, composed (FR-14, FR-15, FR-16, FR-18, FR-21).

Application layer (AD-12): this module *arranges*. Every number it prints is read off a
``Book``, a ``MidVsPrint`` or the committed live state, and the two figures come from
``plots``. It computes one thing — nothing — which is what makes I-13 checkable: the blotter
rendered into the built page must equal ``run_backtest``'s, and a page that recomputed
anything would be a second source for a number the engine already owns (SPEC §1).

**The shape follows the assignment's own example page** (`jakevestal.github.io/535_fintech/`,
which the brief calls a "non-enabling example"), reworked 2026-09-18 at the PO's direction
after reading the two side by side. What that fixed:

* **The account cards.** The strip carried six numbers *about the backtest* — weeks, entries,
  premium, return. It now carries the **Reg T account** as of the last booked bar: cash,
  stock LMV, short option, NAV, initial, maintenance, available, excess, each with the line
  that says where it comes from. FR-16 is *"used like an account"*, and a strip of summary
  statistics is not an account.
* **The ledger is keyed on events, not sessions** (`Book.event_ledger`), and prints the
  eleven columns the example prints. A reader checks this table against the blotter, so it
  reads straight across from it.
* **The strategy panel is gone as a panel.** Its content — `Params` whole, the stated
  simplifications, the rule ids — folds into the write-up, which is where the example keeps
  its rules. FR-14 still prints every field; it is no longer the first thing on the page,
  ahead of the book it describes.

**Panel order:** the two charts, the blotter, the ledger, the rules and write-up, the
contracts queried, and the live book last (PO, 2026-09-18 — it is FR-21, which the example
has no equivalent for, so it closes the page rather than interrupting it).

The **palette stays ours** (PO, same conversation): the example is a different visual
identity, and a site whose two pages look like different products is a worse outcome than one
that does not copy the sample's colours.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
from dataclasses import dataclass

from options_surface_lab import theme as T
from options_surface_lab.covered_call import live as live_mod
from options_surface_lab.covered_call import plots, writeup
from options_surface_lab.covered_call.engine import (
    BLOTTER_COLUMNS,
    FLAG_NEG_AVAILABLE,
    IM_RATE,
    MM_RATE,
    SKIP_COLUMNS,
    run_backtest,
)
from options_surface_lab.covered_call.evidence import mid_vs_print
from options_surface_lab.covered_call.rules import Params
from options_surface_lab.option_surface_utils import parse_option_ric
from options_surface_lab.page_shell import PageShell, Stacked

#: SPEC §14, printed under the strategy because *"a reader who cannot see them cannot judge
#: the book"*. Held here as the page's rendering of the spec's table; `tests/` pins the id
#: set, so a simplification added to §14 and not to the page fails rather than going quiet.
SIMPLIFICATIONS = (
    ("S-1", "100 shares, 1 contract, always."),
    ("S-2", "Exit is to wait: no buy-backs, no rolls."),
    ("S-3", "Expiry is the week's last session per the stock tape."),
    ("S-4", "No commissions or fees."),
    ("S-5", "No margin interest."),
    ("S-6", "No early assignment; dividends ignored."),
    ("S-7", "Marks: stock at the bar's print, option at the bar's mid, carried forward "
            "when absent; intrinsic on the expiry bar."),
    ("S-8", "Timestamps are exchange time, on LSEG's bar convention."),
    ("S-9", "Skipped weeks are logged, not booked."),
)

#: The rule ids the blotter's `note` column cites, so the table is legible without the spec.
RULE_IDS = (
    ("R-ENTRY-STOCK", "Buy 100 shares at the entry bar's print."),
    ("R-ENTRY-CALL", "Write 1 call at the selected strike, filled at the bar's midpoint."),
    ("R-EXPIRE", "At expiry, out of the money: the call expires, the shares stay."),
    ("R-ASSIGN", "At expiry, in the money: the call is assigned."),
    ("R-ASSIGN-SELL", "The assignment's stock leg — 100 shares delivered at the strike."),
)

#: Columns whose cells are figures: right-aligned and tabular, so a column of dollars lines
#: up at the decimal. Named rather than inferred from dtype — `qty` is an integer and a
#: number, `week` is a string and not one, and `flag` is neither.
_NUMERIC = {
    "qty", "limit", "fill", "cash_delta", "shares", "short_calls", "cash", "stock_mark",
    "call_mark", "lmv", "option_mv", "nav", "im", "mm", "available", "excess",
    "call_strike", "strike", "premium", "spot", "mid", "settle",
}

#: What an absent value prints as. SPEC §8: `limit` is `—` on EXPIRE/ASSIGN and `fill` is 0.
_ABSENT = "—"

#: The ledger as the page prints it: `(ledger column, header)`, in the example's order.
#:
#: Eleven columns, not the engine's twenty. Three of the engine's are folded rather than
#: dropped — `call_strike`/`call_expiry`/`short_calls` become one **Short call** cell, and
#: `flag` rides on **Available**, because FR-16 asks for the flag *beside the trade* and a
#: column that is empty on 19 rows of 20 says it more quietly than a red number does.
#: `excess` leaves the table for the account cards, where the example keeps it.
PAGE_LEDGER_COLUMNS = (
    ("ts", "Date"),
    ("cash", "Cash"),
    ("shares", "Shares"),
    ("short_call", "Short call"),
    ("stock_mark", "Spot"),
    ("lmv", "LMV"),
    ("option_mv", "Opt MV"),
    ("nav", "NAV"),
    ("im", "Initial"),
    ("mm", "Maint"),
    ("available", "Available"),
)

#: Column headers, because a reader is not reading a DataFrame.
#:
#: **The brief names the blotter's columns and calls them non-negotiable** — `Cash Δ`, not
#: `cash_delta`; `Notes`, not `note` — and SPEC §9 says in as many words that the page
#: title-cases the ledger's. The page printed the engine's raw keys until 2026-09-18, which
#: is drift against precedence 1 and precedence 3 at once, found by reading the instructor's
#: own example page beside ours. `tests/` pins the blotter's labels to **the brief file**,
#: not to this dict, so the page is held to the document rather than to itself.
#:
#: Lower case stays in the code, deliberately: `LEDGER_COLUMNS` is the engine's vocabulary
#: and the invariants quote it. This maps one to the other in the single place that renders.
COLUMN_LABELS = {
    # the blotter (SPEC §8, the brief's table)
    "time": "Time",
    "instrument": "Instrument",
    "occ": "OCC",
    "side": "Side",
    "qty": "Qty",
    "limit": "Limit",
    "fill": "Fill",
    "cash_delta": "Cash Δ",
    "note": "Notes",
    # the skip log (SPEC §8.2)
    "reason": "Reason",
    "state_at_skip": "State at skip",
    "detail": "Detail",
    # the ledger (SPEC §9)
    "ts": "Time",
    "week": "Week",
    "entry": "Entry",
    "shares": "Shares",
    "short_calls": "Short calls",
    "call_ric": "Call RIC",
    "call_strike": "Strike",
    "call_expiry": "Expiry",
    "cash": "Cash",
    "stock_mark": "Stock mark",
    "call_mark": "Call mark",
    "mark_carried": "Mark carried",
    "lmv": "LMV",
    "option_mv": "Opt MV",
    "nav": "NAV",
    "im": "Initial",
    "mm": "Maint",
    "available": "Available",
    "excess": "Excess",
    "flag": "Flag",
}


def labels(columns) -> tuple:
    """`columns` as headers. An unmapped name falls back to itself rather than raising.

    Failing soft here is the right trade: a column added to the engine and not to
    `COLUMN_LABELS` should render as its raw key — visibly unfinished — rather than take the
    whole page down. A test names the columns that must be mapped.
    """
    return tuple(COLUMN_LABELS.get(name, name) for name in columns)


@dataclass(frozen=True)
class Page:
    """Everything the builder needs to write the document, plus the records behind it.

    The records travel with the rendering so a test can hold the page to its own sources
    (I-13) without re-running the backtest and hoping it got the same inputs.
    """

    params: Params
    book: object
    evidence: object
    live: dict
    ident: str
    readouts: tuple
    warning_text: str
    panels: tuple

    @property
    def synthetic(self) -> bool:
        return bool(self.book.synthetic)


def build_page(tape, params: Params | None = None, *, shell: PageShell | None = None,
               live: dict | None = None) -> Page:
    """Run the book over `tape` and render SPEC §11's panels.

    `shell` is the builder's own, because a `PageShell` carries the "have I emitted
    plotly.js yet" flag and a second shell would request the library twice — or, worse,
    never (T-79).

    `live` overrides the committed live state, for the tests that need a book in each of
    its states: open, settled, and never run.
    """
    params = params or Params()
    shell = shell or PageShell("Covered call")
    book = run_backtest(tape, params)
    evidence = mid_vs_print(tape, params)
    live = live_mod.load_state(params) if live is None else live

    panels = (
        shell.figure_panel(
            1, "Growth of the book", "FR-16 · NAV, initial, maintenance · hover a date",
            plots.account_figure(book), width=T.W_FULL,
        ),
        shell.figure_panel(
            2, "Midpoint assumption", "FR-17 · TRDPRC_1 vs (BID+ASK)/2",
            plots.mid_vs_print_figure(evidence), width=T.W_FULL,
        ),
        _blotter_panel(shell, book),
        _ledger_panel(shell, book, params),
        _writeup_panel(shell, params),
        _contracts_panel(shell, book, params),
        _live_panel(shell, params, live),
    )

    return Page(
        params=params,
        book=book,
        evidence=evidence,
        live=live,
        ident=_ident(params, book),
        readouts=_headline(book),
        warning_text=_warning_text(book),
        panels=panels,
    )


# --------------------------------------------------------------------------
# The chrome's text
# --------------------------------------------------------------------------
def _ident(params: Params, book) -> str:
    return (
        f"<b>{params.root}</b> covered call &nbsp;·&nbsp; weekly &nbsp;·&nbsp; "
        f"<b>{params.start} → {params.end}</b> &nbsp;·&nbsp; {params.interval} bars "
        f"&nbsp;·&nbsp; {len(book.weekly)} weeks"
    )


def _warning_text(book) -> str:
    """The banner, or "". A synthetic book renders perfectly — ten plausible weeks of a
    market that never happened — so its *absence* of a banner is the dangerous case."""
    return "" if not book.synthetic else (
        f"Built from a {SYNTHETIC_MARKER}, not the LSEG pull — every number below is a "
        "shape, not a market. This must not be published."
    )


#: Grepped by the CI publish guard; distinct from 1.1's "synthetic panel" so one page's
#: fabrication cannot pass the other's check. Lives here with the text that carries it.
SYNTHETIC_MARKER = "synthetic tape"

#: SPEC §11's per-page publish guards, as the literal strings CI greps for. Kept here so the
#: page and the workflow cannot drift apart, and pinned to both by
#: `tests/test_build_covered_call.py` — the coupling that broke when a caption was
#: shortened and left the guard hunting a phrase the page had stopped saying (T-45).
#:
#: **Two kinds, with different rules.** A CAPTION marker is prose that exists *twice* in the
#: built page — as panel HTML and inside the figure's `layout.meta` — so it must be plain
#: ASCII with no `/` and no `·`: Plotly's encoder ships a slash escaped and the separators
#: are `&nbsp;·&nbsp;`, and a guard spanning either silently never matches. A STRUCTURAL
#: marker is markup, never inside figure JSON, so `</td>` is safe there and nowhere else.
CAPTION_MARKERS = (
    "Fill assumption:",   # FR-17's fit line — SPEC §11's "require the R-squared line"
)

#: At least one entry was booked. A blotter side **cell**, not a rule id: the rule ids are
#: also printed with the write-up, so grepping `R-ENTRY-STOCK` would pass on a page whose
#: blotter was empty — the exact failure the guard exists to catch.
#:
#: It matches the cell's *end*, not `<td>BUY</td>`. The opening tag grew a class the day the
#: PO asked for coloured sides (2026-09-18) and the guard stopped matching — it would have
#: failed the deploy, and `tests/test_build_covered_call.py` caught it first, which is the
#: whole reason these live beside the markup instead of only in the workflow (T-45).
BLOTTER_ENTRY_MARKER = ">BUY</td>"

#: ...and at least one week resolved. Either is enough; a window can be all of one.
BLOTTER_SETTLED_MARKERS = (">EXPIRE</td>", ">ASSIGN</td>")


def entries(book) -> int:
    """Weeks the rule actually traded — a week with a settled outcome had an entry."""
    return int(book.weekly["outcome"].isin(("ASSIGN", "EXPIRE")).sum())


def _headline(book) -> tuple:
    """The **Reg T account** as of the last booked bar — FR-16's *"used like an account"*.

    This strip carried six statistics *about the backtest* until 2026-09-18 — weeks,
    entries, premium, return — which is a summary of a study, not an account. The brief
    asks for the account, the example page leads with it, and the rubric gives it 20 points.
    Every card is a cell of the last `event_ledger` row plus the line that defines it: a
    Reg T figure a reader cannot check is a figure they have to take on trust.

    Read off the **event** ledger rather than `ledger.iloc[-1]`: the last hourly row is a
    post-close stub, which is T-62's trap and the reason `final_nav` exists (T-57).
    """
    rows = book.event_ledger()
    if rows.empty:
        return (("Cash", f"${book.params.start_cash:,.2f}", "No week was booked"),)
    last = rows.iloc[-1]

    shares = int(last["shares"])
    spot = float(last["stock_mark"]) if pd.notna(last["stock_mark"]) else None
    lmv_hint = (
        f"{shares} {book.params.root} @ {spot:,.2f}" if shares and spot is not None
        else "flat"
    )
    return (
        ("Cash", _money(last["cash"]), "Settled dollars after fills"),
        ("Stock LMV", _money(last["lmv"]), lmv_hint),
        ("Short option", _money(last["option_mv"]), _short_call(last) or "flat"),
        ("NAV / equity", _money(last["nav"]), "cash + LMV + option MV"),
        ("Initial margin", _money(last["im"]),
         f"Reg T {IM_RATE:.0%} of LMV · covered call adds $0"),
        ("Maintenance", _money(last["mm"]), f"FINRA {MM_RATE:.0%} of LMV"),
        ("Available funds", _money(last["available"]),
         "NAV − initial. Room for a new risk."),
        ("Excess equity", _money(last["excess"]),
         "NAV − maintenance. The margin-call line."),
    )


# --------------------------------------------------------------------------
# [3] The blotter and the skip log — FR-15, SPEC §8
# --------------------------------------------------------------------------
def _blotter_panel(shell: PageShell, book) -> str:
    """The brief's columns exactly — **eight**, with the OCC inside Instrument.

    *"Stock or option RIC; OCC as a subtitle"*: the OCC was a ninth column until
    2026-09-18, which says the same thing in a shape the brief does not ask for and the
    example does not use.

    The skip log shares this panel, and **only appears when there are skips**. It is the
    other half of the same statement — the brief grades the strategy doing what it says,
    and a skipped week is the strategy doing something — but on the committed tape there
    are none, and an empty table under a heading is furniture.
    """
    blotter = shell.table(
        _BLOTTER_HEADERS,
        (_blotter_row(record) for record in book.blotter.to_dict("records")),
    )
    body = (
        f'<div class="osl-note" style="padding-bottom:8px">{len(book.blotter)} booked rows. '
        "Cash moves only here — every other number on this page is a projection of this "
        "table. EXPIRE or ASSIGN on the expiry session; no buy-backs, no rolls."
        "</div>"
        f"{blotter}"
    )
    if len(book.skips):
        body += (
            '<div class="osl-commentary-q" style="padding:14px 0 5px 0">Skip log</div>'
            f'<div class="osl-note" style="padding-bottom:8px">{len(book.skips)} week(s) '
            "the rule declined — no trade was booked, and nothing was invented at a price "
            "that was not quoted.</div>"
            + shell.table(
                labels(SKIP_COLUMNS),
                (
                    _row(record, SKIP_COLUMNS, classes={"reason": "osl-skip"})
                    for record in book.skips.to_dict("records")
                ),
            )
        )
    note = f"FR-15 · {len(book.blotter)} rows"
    if len(book.skips):
        note += f" · {len(book.skips)} skips"
    return shell.panel("Blotter: Executed Trades", note, body, n=3, width=T.W_FULL)


#: The brief's blotter table, in the brief's order. `occ` is not a column — it rides inside
#: `instrument` as a subtitle, which is what the brief's own column description says.
_BLOTTER_RENDERED = ("time", "instrument", "side", "qty", "limit", "fill", "cash_delta",
                     "note")
_BLOTTER_HEADERS = tuple(COLUMN_LABELS[c] for c in _BLOTTER_RENDERED)


#: The two blotter columns that carry a direction, and the class each takes (PO,
#: 2026-09-18). `EXPIRE` and `ASSIGN` are absent on purpose: they move no cash and are not a
#: side anyone took, so colouring them would make "something happened here" mean two
#: different things in one column.
SIDE_CLASS = {"BUY": "osl-up", "SELL": "osl-down"}


def _blotter_row(record: dict) -> list:
    """One blotter row, with the OCC stacked under the RIC and direction in colour."""
    out = []
    for name in _BLOTTER_RENDERED:
        value = _present(record.get(name))
        if name == "instrument":
            occ = str(record.get("occ") or "").strip()
            out.append(Stacked(value, occ) if occ else value)
        elif name == "side":
            out.append((value, SIDE_CLASS[value]) if value in SIDE_CLASS else value)
        elif name in _PRICE_COLUMNS:
            out.append((_price(record.get(name)), "osl-num"))
        elif name == "cash_delta":
            # Signed, so the class is read off the number rather than off the side: an
            # ASSIGN's stock leg is a SELL that pays in, and a row whose cash did not move
            # takes neither colour. Reading it from `side` would have been the same answer
            # on this book and the wrong rule.
            out.append((value, f"osl-num {_sign_class(record.get(name))}".strip()))
        else:
            out.append((value, "osl-num") if name in _NUMERIC else value)
    return out


def _sign_class(value) -> str:
    """`osl-up` / `osl-down` / "" — cash in, cash out, or cash unmoved."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    if amount > 0:
        return "osl-up"
    return "osl-down" if amount < 0 else ""


# --------------------------------------------------------------------------
# [4] The ledger — SPEC §9
# --------------------------------------------------------------------------
def _ledger_panel(shell: PageShell, book, params: Params) -> str:
    """One row per booked event, in the eleven columns the example prints.

    Keyed on the blotter's own bars, so the two tables read straight across — which is what
    a reader checking the book by hand is actually doing. The hourly frame is still what the
    chart draws; forty-nine rows of a mark drifting between events was volume, not evidence.
    """
    rows = book.event_ledger()
    body = (
        f'<div class="osl-note" style="padding-bottom:8px">'
        f"{len(rows)} rows — one per booked event, selected from the "
        f"{len(book.ledger)} hourly rows the chart above draws, never re-aggregated, so a "
        "number here is a number on that line. <b>Available</b> is NAV − initial and it "
        "carries the flag when it goes negative; <b>Excess</b> is NAV − maintenance and is "
        "on the card above. A mark with no print at its bar is <b>carried forward</b>, "
        "never interpolated (S-7).</div>"
        + shell.table(
            tuple(header for _, header in PAGE_LEDGER_COLUMNS),
            (_ledger_row(record) for record in rows.to_dict("records")),
        )
    )
    return shell.panel(
        "Position, cash, and margin over time",
        f"SPEC §9 · {len(rows)} events · Reg T",
        body,
        n=4,
        width=T.W_FULL,
    )


def _ledger_row(record: dict) -> list:
    """One ledger row in the page's eleven columns."""
    out = []
    for name, _ in PAGE_LEDGER_COLUMNS:
        if name == "ts":
            stamp = str(record.get("ts") or "")
            out.append(Stacked(stamp[:10], stamp[11:16]) if len(stamp) >= 16 else stamp)
        elif name == "short_call":
            out.append((_short_call(record) or "flat", "osl-label"))
        elif name == "available":
            flagged = record.get("flag") == FLAG_NEG_AVAILABLE
            text = _money(record.get("available"))
            out.append((f"{text} {FLAG_NEG_AVAILABLE}", "osl-flag") if flagged
                       else (text, "osl-num"))
        elif name in ("cash", "lmv", "option_mv", "nav", "im", "mm"):
            out.append((_money(record.get(name)), "osl-num"))
        else:
            out.append((_present(record.get(name)), "osl-num"))
    return out


def _short_call(record) -> str:
    """`1 723C 07-10`, or "" when flat — three ledger columns folded into one cell."""
    count = record.get("short_calls") or 0
    strike, expiry = record.get("call_strike"), record.get("call_expiry")
    if not count or strike is None or pd.isna(strike):
        return ""
    when = str(expiry)[5:10] if expiry else ""
    return f"{int(count)} × {float(strike):g}C {when}".strip()


# --------------------------------------------------------------------------
# [5] The rules and the write-up — FR-14, FR-19
# --------------------------------------------------------------------------
def _writeup_panel(shell: PageShell, params: Params) -> str:
    """The rules in prose, then FR-19's five answers, then the record — in that order.

    **Rebuilt 2026-09-18.** It shipped as four side-by-side blocks, each holding its own
    scrolling table: the method, the whole `Params` record, nine simplifications and five
    rule ids, abreast, above the answers. On a real screen that is four columns of chrome
    where the example page has four short paragraphs, and the thing a reader came for — what
    the strategy is, and what the author concluded — was the smallest text on it.

    So prose leads, the answers follow, and the **record folds into a `<details>`**. FR-14's
    acceptance is that the page *prints* every field of `Params` and every S-x; it does,
    behind one disclosure a reader opens when they want to audit rather than read. Nothing
    was removed.

    *Amended 2026-09-18 (PO).* The two generated paragraphs that led the panel — the rule and
    the exit — restated the PO's own first two answers a few lines above them, which is the
    same redundancy that sent the three standalone paragraphs into the answers the same day.
    They are **rows of the parameter table** now, not deletions: both were derived from
    `Params`, and that is the property worth keeping — a hand-written answer can outlive a
    decision it describes, a sentence read off the dataclass cannot.
    """
    param_rows = [
        (name, (str(_present(value)), "osl-num" if name in _NUMERIC else ""))
        for name, value in (
            (f.name, getattr(params, f.name)) for f in dataclasses.fields(params)
        )
    ]
    # The two rules stated in words, **derived** rather than typed, so a sentence and the
    # field it describes cannot come apart — a page that hand-wrote "nearest
    # out-of-the-money" would keep saying it after SD-5 changed. They led the panel as prose
    # until 2026-09-18 (PO: *"get rid of that redundancy"*), where they restated the PO's own
    # first two answers a few lines below them. A table of their own, because the parameter
    # table is `Params` verbatim and a derived row in it would be a field nobody declared.
    in_words = [
        (("Strike rule", "osl-label"), params.describe_strike_rule()),
        (("ITM test", "osl-label"),
         f"At expiry the call is assigned when the settlement print is "
         f"{_itm_words(params)}; otherwise it expires and the shares stay."),
        (("Exit", "osl-label"),
         "Hold to the expiry bar. No buy-backs and no rolls. A week whose quote is invalid "
         "is skipped and logged, never booked at a price nobody quoted."),
    ]
    answers = "".join(
        '<div class="osl-commentary-item">'
        f'<div class="osl-commentary-q">{question}</div>{_answer(answer)}</div>'
        for question, answer in zip(writeup.QUESTIONS, writeup.ANSWERS)
    )
    record = (
        shell.table(
            ("Step", "What was decided"),
            [((label, "osl-label"), text) for label, text in writeup.METHOD],
            kv=True,
        )
        + shell.table(("Rule", "As the parameters state it"), in_words, kv=True)
        + shell.table(("Parameter", "Value"), param_rows, kv=True)
        + shell.table(
            ("Id", "Stated simplification"),
            [((sid, "osl-label"), text) for sid, text in SIMPLIFICATIONS],
            kv=True,
        )
        + shell.table(
            ("Note", "What fired"),
            [((rid, "osl-label"), text) for rid, text in RULE_IDS],
            kv=True,
        )
    )
    body = (
        '<div class="osl-commentary-q" style="padding-top:6px">'
        "FR-19 — the five questions, answered by the PO</div>"
        f'<div class="osl-commentary" style="padding:10px 0 0 0">{answers}</div>'
        "<details class=\"osl-details\"><summary>Parameters, decisions and stated "
        "simplifications — the whole record</summary>"
        f'<div class="osl-details-body">{record}</div></details>'
    )
    return shell.panel(
        "Covered-call rules and write-up",
        f"FR-14, FR-19 · {params.strike_rule} · {params.itm_rule} ITM test",
        body,
        n=5,
        width=T.W_FULL,
    )


def _itm_words(params: Params) -> str:
    """SD-6 in words, read off `params` so the sentence cannot outlive the decision."""
    return (
        "strictly above the strike" if params.itm_rule == "strict"
        else "at or above the strike"
    )


def _answer(text: str) -> str:
    if text == writeup.UNWRITTEN:
        return f'<div class="osl-note osl-commentary-todo">{writeup.UNWRITTEN}</div>'
    return f'<div class="osl-note">{text}</div>'


# --------------------------------------------------------------------------
# [6] The contracts the book queried
# --------------------------------------------------------------------------
def _contracts_panel(shell: PageShell, book, params: Params) -> str:
    """Every expired contract this book actually wrote, and the RIC it answered under.

    The example page carries this table and the brief spends a whole section on the RIC
    grammar, which is the part of the assignment most likely to be taken on trust. Reading
    the RIC **off the blotter** rather than rebuilding it is the point: T-82's defect was an
    engine that fabricated the caret form when the tape had answered under the live one, so
    the spelling here is the spelling that returned bars.
    """
    seen, rows = set(), []
    for record in book.blotter.to_dict("records"):
        ric = str(record.get("instrument") or "")
        if ric == params.underlying or ric in seen or not ric:
            continue
        seen.add(ric)
        try:
            parsed = parse_option_ric(ric)
            label = (
                f"{parsed['root']} {parsed['expiry']} {parsed['strike']:g} {parsed['cp']}"
            )
        except Exception:  # a RIC the grammar cannot read is still a RIC that traded
            label = str(record.get("occ") or ric)
        rows.append(((label, "osl-label"), ric))

    body = (
        f'<div class="osl-note" style="padding-bottom:8px">{len(rows)} contracts, each '
        "read off the blotter rather than rebuilt from the strike — which form an expired "
        "contract answers under depends on how long ago it expired, so the spelling here is "
        "the one that actually returned bars.</div>"
        + shell.table(("Contract", "RIC"), rows)
    )
    return shell.panel(
        "Expired contracts this book queried",
        f"FR-13 · {len(rows)} contracts",
        body,
        n=6,
        width=T.W_HALF,
    )


# --------------------------------------------------------------------------
# [7] The live book — FR-21
# --------------------------------------------------------------------------
def _live_panel(shell: PageShell, params: Params, live: dict) -> str:
    """The same rule, run forward on real quotes with simulated capital.

    Last on the page (PO, 2026-09-18): the example has no equivalent, so it closes the page
    rather than interrupting the graded sequence. FR-21 asks the panel to **state what is
    historical and what is live**, because the two books look identical in a table and mean
    entirely different things — one is a window that has already happened, the other is a
    position that is still open.
    """
    blotter_rows = live.get("blotter") or []
    position = live.get("position") or {}
    call = position.get("call")

    if not blotter_rows:
        body = (
            '<div class="osl-note">No live week has been booked yet. The forward run is '
            "one command — <code>python -m options_surface_lab.covered_call.live enter</code>"
            " — and writes nothing until it has a readable bar.</div>"
        )
        note = "FR-21 · not yet run"
    else:
        table = shell.table(
            _BLOTTER_HEADERS, (_blotter_row(record) for record in blotter_rows)
        )
        state = (
            f"Short the <b>{call['strike']:.0f}</b> call expiring <b>{call['expiry']}</b> "
            f"against {position.get('shares', 0)} shares — <b>still open</b>; it resolves "
            "at that session's closing bar."
            if call else
            "Flat — the call resolved and the position is closed."
        )
        body = (
            '<div class="osl-note" style="padding-bottom:8px">'
            "Everything above this panel is <b>historical</b>: a window that has already "
            f"happened, {params.start} → {params.end}. This is the same rule running "
            "<b>forward</b> on quotes as they arrive, with simulated capital, booked by "
            "<code>covered_call/live.py</code> rather than by hand — the same "
            f"<code>select_strike</code> and the same blotter rows. {state}</div>"
            f"{table}"
            + _capture_block(shell, live)
        )
        note = f"FR-21 · {len(blotter_rows)} rows · cash ${live.get('cash', 0):,.2f}"

    return shell.panel("Live book", note, body, n=7, width=T.W_HALF)


def _capture_block(shell: PageShell, live: dict) -> str:
    """The raw quotes behind the live rows — FR-21's *"with their raw quotes"*.

    This is the panel's evidence, not its decoration: a booked fill with no quote beside it
    is a number a reader has to take on trust, and the whole argument for the midpoint is
    that the bid and the ask were what they were.

    **The evidence is pinned to the entry capture and to the contract the blotter names.**
    It read `captures[-1]` and `position["call"]` until 2026-09-18, which was correct while
    a week was open and became wrong the moment one settled: `settle` appends a second
    capture and empties the position, so the panel printed the *settlement* bar under the
    label "Entry bar", the settlement spot beside a fill booked at a different price, and
    an empty bid/ask where FR-21's evidence belongs. Neither was invented — `capture()`
    names its bar `entry_bar` on **both** legs (`diagnostics["bar_kind"]` is what tells them
    apart), so a true label became a false statement when a second snapshot arrived. Reading
    the contract off the blotter is the rule T-82 arrived at from the other direction: the
    row that booked the trade is the only thing that still knows what was booked.
    """
    captures = live.get("captures") or []
    if not captures:
        return ""
    entry = _capture_of(captures, "entry")
    if entry is None:
        return ""

    under = entry.get("underlying") or {}
    booked = _written_call(live)
    quoted = next(
        (c for c in entry.get("chain") or []
         if c.get("ric") == booked.get("instrument")), {}
    )
    rows = [
        (("Entry bar", "osl-label"), str(entry.get("entry_bar", _ABSENT))),
        (("Stock print at that bar", "osl-label"),
         (_present(under.get("trdprc_1")), "osl-num")),
        (("Stock bar high / low", "osl-label"),
         (f"{_present(under.get('high_1'))} / {_present(under.get('low_1'))}", "osl-num")),
        (("Call bid / ask", "osl-label"),
         (f"{_present(quoted.get('bid'))} / {_present(quoted.get('ask'))}", "osl-num")),
        (("Fill, at the midpoint of those two", "osl-label"),
         (_price(booked.get("fill")), "osl-num")),
        (("Last-trade offsets (stock / call)", "osl-label"),
         (f"{_present(under.get('c_sec_ofst'))}s / {_present(quoted.get('c_sec_ofst'))}s",
          "osl-num")),
        (("RIC form", "osl-label"),
         str((entry.get("chain") or [{}])[0].get("ric_form", _ABSENT))),
    ]

    closing = _capture_of(captures, "closing")
    if closing is not None:
        settled = closing.get("underlying") or {}
        rows += [
            (("Expiry bar", "osl-label"), str(closing.get("entry_bar", _ABSENT))),
            (("Settlement print", "osl-label"),
             (_present(settled.get("trdprc_1")), "osl-num")),
        ]

    return (
        '<div class="osl-commentary-q" style="padding:14px 0 5px 0">Raw quotes behind those '
        "rows</div>" + shell.table(("Observation", "Value"), rows, kv=True)
    )


#: `capture()` names its bar `entry_bar` whichever leg ran; `diagnostics["bar_kind"]` is the
#: field that says which. The key arrived with T-81 (2026-09-15), *after* the 09-14 entry was
#: booked, so a snapshot without it is an entry — which is what it meant when it was the only
#: leg that existed.
_ENTRY_KINDS = ("entry", None)


def _capture_of(captures: list, kind: str) -> dict | None:
    """The most recent capture taken at a bar of `kind` — `"entry"` or `"closing"`."""
    for snapshot in reversed(captures):
        found = (snapshot.get("diagnostics") or {}).get("bar_kind")
        if found == kind or (kind == "entry" and found in _ENTRY_KINDS):
            return snapshot
    return None


#: The blotter note that identifies the row on which the call was written.
_ENTRY_CALL_RULE = "R-ENTRY-CALL"


def _written_call(live: dict) -> dict:
    """The blotter row that wrote the call — the only record of it that survives settlement."""
    for record in live.get("blotter") or []:
        if str(record.get("note") or "").startswith(_ENTRY_CALL_RULE):
            return record
    return {}


# --------------------------------------------------------------------------
# Cells
# --------------------------------------------------------------------------
def _row(record: dict, columns, *, classes: dict | None = None) -> list:
    """One table row: every column of `columns`, in order, classed by what the cell is."""
    classes = classes or {}
    out = []
    for name in columns:
        value = _present(record.get(name))
        css = classes.get(name, "") if value not in ("", _ABSENT) else ""
        if not css and name in _NUMERIC:
            css = "osl-num"
        out.append((value, css) if css else value)
    return out


def _money(value) -> str:
    """A dollar figure as the account states it: signed, grouped, two places.

    A minus sign rather than a bracket, and always two decimals — a covered call's premium
    lives in the cents, and a page that rounds them reconciles against nothing.
    """
    text = _present(value)
    if text == _ABSENT:
        return text
    return f"−${text[1:]}" if text.startswith("-") else f"${text}"


#: The blotter columns that carry a contract price rather than a dollar amount. They are
#: the two cells a reader multiplies by `qty` to check `Cash Δ`, so they may not round.
_PRICE_COLUMNS = ("limit", "fill")


def _price(value) -> str:
    """A contract price at the precision it was actually filled at.

    Two places for a whole-cent price, three when it lands on a half-cent — an option
    midpoint does, five weeks in eleven on this book. Printing `6.04` for a 6.045 fill
    beside a `Cash Δ` of `604.50` leaves a reader checking that row by hand with a
    fifty-cent hole, in the one table whose whole purpose is to show exactly what was
    booked. `_money`'s docstring already said it: a covered call's premium lives in the
    cents, and a page that rounds them reconciles against nothing.
    """
    import math

    if isinstance(value, float) and not math.isnan(value):
        text = f"{value:,.3f}"
        return text[:-1] if text.endswith("0") else text
    return _present(value)


def _present(value) -> str:
    """A value as the page prints it — absence as `—`, never as `nan` or `None`.

    `nan` in a table is the AD-9 failure in miniature: it looks like a value, it is not one,
    and a reader cannot tell whether the number was missing or the code was.
    """
    import math

    if value is None:
        return _ABSENT
    if isinstance(value, float):
        if math.isnan(value):
            return _ABSENT
        return f"{value:,.2f}" if abs(value) >= 0.005 or value == 0 else f"{value:g}"
    text = str(value)
    return _ABSENT if text in ("", "None", "NaT", "nan") else text


__all__ = [
    "BLOTTER_ENTRY_MARKER",
    "SIDE_CLASS",
    "BLOTTER_SETTLED_MARKERS",
    "CAPTION_MARKERS",
    "COLUMN_LABELS",
    "PAGE_LEDGER_COLUMNS",
    "Page",
    "RULE_IDS",
    "SIMPLIFICATIONS",
    "SYNTHETIC_MARKER",
    "build_page",
    "entries",
    "labels",
]
