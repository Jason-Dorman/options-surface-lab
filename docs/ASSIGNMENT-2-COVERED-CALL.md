# MENG FinTech · Algorithmic Trading II

# Covered Call Backtest

| Field | Value |
|---|---|
| Due | As posted in Canvas |
| Turn in | Your GitHub Pages URL. Non-enabling example: `jakevestal.github.io/535_fintech/` |
| Graded on | Logical consistency, clarity of presentation, fulfillment of the requirements |

Implement a covered-call strategy, simulate execution, and publish the book.

This is our first backtest assignment, so you will be graded on logical consistency (no
crazy/impossible trades; reasonable fill prices; your strategy does what you say it does),
clarity of presentation, and fulfillment of the requirements. You do not have to be incredibly
fancy yet; it is perfectly fine to backtest and analyze the behavior of a basic covered call
strategy this week.

## What you are building

A covered call backtest: **long 100 shares, short 1 call**. Backtest it on one stock of your
choosing. I advise you to pick an underlying that has liquid, easy-to-price options to make
this easier.

Simulate fills by pulling historical price data and using it to generate a blotter of what
would have happened if your entry conditions were met. See the example page for guidance.

You must have **clear, algorithmic rules for choosing your strike**. A perfectly fine set of
rules that will get full credit for this assignment would be a loop that scrolls through the
historical data and records:

1. **Monday:** if you are flat, buy 100 shares at the stock print (decrease cash by
   shares × price).
2. **Same Monday:** write 1 call expiring that Friday, nearest OTM (or ATM if spot sits on a
   strike). Increase cash by the premium (100 × mid). Limit order at mid = `(BID + ASK) / 2`.
   **No bid/ask → skip the week.**
3. **Friday expiry.**
   - **OTM:** the call expires, keep the shares, keep the premium. Next Monday just write the
     next Friday call (do not buy stock again).
   - **ITM:** you are assigned — shares leave, increase cash by 100 × strike. Next Monday you
     are flat, so start over with the combo (buy 100 + write the new Friday call).

If you go more complex than this, I will not hold you back, but I suggest you at least start
from this simple case (so that you are covered for your HW grade) before adding complexity on
top of it.

## The decisions are the assignment

As you do this, you will need to make all sorts of small but important design and financial
engineering decisions:

- **How** will you choose the strike price at which you write the call?
- Why did you choose the stock that you did?
- Is it better to hold until expiry, or to immediately set a limit order to buy back the call
  at X% profit (and simulate a fill of that happening by writing down the cash payment to buy
  back)?

Write down these decisions on your website; that is your algorithm, and that is the true point
of this assignment — to identify and communicate those decisions that determine the entry and
exit rules of your strategy. You may be surprised how different your HWs will be even though
you are implementing the same strategy. That's because success is all in the execution and the
smart design of the small decisions and rules.

## Pick your underlying

Any U.S. equity (or ETF) you can pull from LSEG. Prefer a name with liquid weeklies so mids are
tight and `TRDPRC_1` actually prints — AAPL, MSFT, NVDA, SPY, QQQ, etc. Thin names make the
midpoint assumption harder to defend (but it is still surprisingly robust for many smaller
equities).

## Making your blotter

- **Default, this assignment:** you get filled at the option mid = `(BID + ASK) / 2` at the
  timestamp of the order. Combined with intraday stock prints, that lets you price the
  covered-call combo any time of day.
- **Optional upgrade:** fit a volatility curve to multiple prints, infer a fair price, and
  assume that fill. If you do this, show the fit.
- **If there is no bid/ask at that bar, you do not fill. Skip. Do not invent a print.** This is
  the worst mistake an algo trader can make and it will cost you money in the long (or short)
  run.

## What LSEG actually gives you (expired options)

Intraday history on expired listed options is available, but the field set is limited. You
should expect:

- `BID` and `ASK` — you have these down to the 1-minute bar even for expired options.
- When a trade happens: `TRDPRC_1`, `OPEN_PRC`, `HIGH_1`, `LOW_1`, `ACVOL_UNS`, `NUM_MOVES`.

That is enough. Mid from `BID`/`ASK` is the fill. Stock OHLC/intraday is the other half of the
combo. Pull the **same bar size** for stock and options (hourly is the right default for a
~10-week window).

Fetch near-the-money calls along the chain (same idea as the first homework: strikes from a bit
below the stock's low in the window to a bit above the high). Then graph `TRDPRC_1` on Y against
`MID = (BID + ASK) / 2` on X, fit a line, report **R²**. That is how you justify the midpoint
assumption on your name.

## Entry / exit rules (algorithmic)

Write an entry rule a machine could run. Baseline: Monday open or close, combo, Friday weekly,
strike you specify (ATM, nearest OTM, delta, whatever — **say it**). Really the main choice you
make in this framework is: how to choose the right strike? Too far OTM and you miss out on cash
income. Too close/deep in the money and you lose out on upside — you've locked yourself into a
sell. Be sure to communicate what you choose and why.

Your **exit rule is to wait**. You will either get assigned a short position against your stock,
or not, and the next week you enter again.

## Blotter (non-negotiable)

Submit a clean blotter of trades you **actually booked**: entries and exits.

| Column | Contents |
|---|---|
| Time | Timestamp of the order |
| Instrument | Stock or option RIC; OCC as a subtitle |
| Side | `BUY` / `SELL` / `EXPIRE` / `ASSIGN` |
| Qty | Shares or contracts |
| Limit | Your limit price |
| Fill | The simulated fill |
| Cash Δ | Signed cash movement |
| Notes | Points at the rule that fired |

- Friday **OTM** is `EXPIRE`.
- Friday **ITM** is `ASSIGN` on the call and a stock `SELL` at the strike.
- Working orders do not belong here. A signal chart is not a blotter. **A blotter is a list of
  trades.**

## The ledger and Reg T — what you must track

The ledger is the running position: shares, short calls (strike + expiry), cash, marks.

Use a **Reg T** account, not portfolio margin. Reg T is computable without a broker's PM/SPAN
engine, it is not broker-dependent, and a book that survives Reg T survives PM — not the other
way around.

For a covered call (long 100 shares, short 1 call on those shares):

| Quantity | Definition |
|---|---|
| NAV (equity) | `cash + stock market value + option market value`. A short call is a **negative** MV. |
| Long market value (LMV) | `shares × stock mark` |
| Initial margin | 50% of stock LMV. The covered short call adds **$0** initial. (A naked short call would; you are not naked.) |
| Maintenance margin | 25% of stock LMV (FINRA). Again, the covered call does not add a naked-option maintenance pad. |
| Available funds | `NAV − initial`. Room to put on a new risk. |
| Excess equity | `NAV − maintenance`. The margin-call line. |

Cash moves **only** when the blotter says so (buy stock, collect premium, expire at 0,
assignment at strike).

Plot NAV (and initial / maintenance) over time with mouseover values. **If available funds go
negative, you could not have put the trade on — say so.**

## Option RICs (how to ask LSEG for an expired contract)

US listed equity options on OPRA use this Reuters Instrument Code. The Helios Python
(`helios/python/option_rics.py`) builds it like this:

```
{ROOT}{MONTH}{DAY}{YY}{STRIKE}.U{^MONTHYY if expired}
```

| Element | Meaning |
|---|---|
| `ROOT` | Equity RIC before the dot, upper case. `AAPL.O` → `AAPL`. `UUUU.N` → `UUUU`. |
| `MONTH` | A single letter for the expiry month **and** put/call (table below). |
| `DAY` | Expiry day, **not** zero-padded (`5`, not `05`). Matches the Python: `expiry.day`. |
| `YY` | Two-digit year of the expiry. |
| `STRIKE` | Strike × 100, 5 digits, zero-padded. `14.50` → `01450`. `190` → `19000`. `192.50` → `19250`. |
| `.U` | OPRA / US listed. |
| `^{MONTH}{YY}` | **Expired only**, using the same month letter. Live contracts do not get the caret suffix. |

### Month codes

| | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Call** | A | B | C | D | E | F | G | H | I | J | K | L |
| **Put** | M | N | O | P | Q | R | S | T | U | V | W | X |

### Class example (expired call): 14.5-strike, 21 Aug 2026, UUUU

```
UUUUH212601450.U^H26
```

```python
ld.get_history(universe="UUUUH212601450.U^H26",
               fields=["TRDPRC_1", "BID", "ASK"],
               interval="hourly", start=..., end=...)
```

### AAPL worked-example RICs (expired as of this assignment)

```
AAPLF52619000.U^F26     # AAPL 5 Jun 2026 190 call
AAPLG172620000.U^G26    # AAPL 17 Jul 2026 200 call
AAPLH72620500.U^H26     # AAPL 7 Aug 2026 205 call
```

A put uses the put letter. Same strike/day/year/`.U`/suffix. **Guess-and-check must fail soft**
— an empty series, not a crash.

**Weeklys:** take the last session in each week from the stock tape so you do not invent holiday
expiries, then walk Friday from there.

## Pages vs local Data

| Surface | Role | Graded? |
|---|---|---|
| GitHub Pages | Blotter, ledger, NAV/margin, mid-vs-trade, write-up | **Yes. The assignment.** |
| Local Data | How you pull tape (Workspace) | No. A tool. |

Pages cannot run Workspace. A Data page on `github.io` must show **Data connection required**.
Live LSEG on Pages is a defect.

```bash
python3 helios/python/local_server.py
# http://127.0.0.1:8765/helios/data.html
```

Bake JSON into `book.js` (or equivalent) and push static files. HTML / CSS / JS. Node is not
required. You may use AI; the book and the reasoning are yours.

## What the published site must contain

1. **Blotter** — every entry and exit.
2. **Ledger** — stock, short calls, cash over time.
3. **Reg T** accounts listed above, used correctly.
4. **NAV path** (and margin) with mouseover.
5. **Mid vs trade scatter** for near-the-money calls, with R².
6. **Write-up:** how you chose the strike, wait-through-expiry (OTM expire / ITM assigned →
   flat), fill at mid, why Reg T.

## Rubric (100% the published site)

| Criterion | Pts |
|---|---|
| Algorithmic entry + strike rule; wait through expiry | 20 |
| Clean blotter + ledger that implement those rules; simulated limit fills | 25 |
| Reg T NAV / IM / MM / available funds / cash, used like an account | 20 |
| Mid vs `TRDPRC_1` scatter + R² (justify the fill assumption) | 15 |
| Analysis: what happened, where theory met tape, what you'd change | 20 |
