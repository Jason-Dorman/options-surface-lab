# System Spec — Assignment 2, Covered Call Backtest

| Field | Value |
|---|---|
| Status | Draft v1 — 2026-09-12. Written before any code; every schema and rule here is a target until the task that lands it says otherwise (lockstep rule). |
| Scope | The book: tape → rules → engine → blotter + ledger + Reg T account → page. Schemas, the weekly algorithm, fills, settlement, edge cases, the invariant suite. |
| Companion | Requirements: [PRD.md Part B](PRD.md) (§13–§20) · Board: [BACKLOG-2.md](BACKLOG-2.md) · Brief: [ASSIGNMENT-2-COVERED-CALL.md](ASSIGNMENT-2-COVERED-CALL.md) · Shared machinery: [SYSTEM-SPEC.md](SYSTEM-SPEC.md) §6 (RIC grammar), §5 (cache-first) · Structure: [ARCHITECTURE.md](ARCHITECTURE.md) AD-12 |

Parameters that are the PO's to choose are written as `params.<name>` and cite their decision
id (PRD §15, SD-x). Nothing here picks one for them.

---

## 1. The one idea

**A book is a list of trades; everything else is derived from it.** The blotter is the
primary artifact — the engine *emits* trades, and the ledger, the account and every number on
the page are *computed* from the blotter and the tape. Never the reverse: no ledger row is
written by hand, no cash moves without a blotter row that says why, and no figure carries a
number that the blotter cannot reproduce. This is what makes "logically consistent" — the
brief's first grading criterion — a property that can be tested (§12) rather than argued.

The second idea is inherited from Assignment 1.1 (AD-9): **a hole is a hole.** No bid/ask at
the bar → no fill → the week is skipped and *recorded as skipped*. The book never contains a
price the tape did not carry.

## 2. Parameters

`Params` is a frozen dataclass. Every field cites the decision that sets it; the page prints
the whole thing (FR-14) so the strategy a reader sees is the one the engine ran.

| Field | Type | Meaning | Set by |
|---|---|---|---|
| `underlying` | `str` RIC (`AAPL.O`) | The stock; `root` derived per SYSTEM-SPEC §6 | SD-1 |
| `start`, `end` | `date` | The window; `end` is an expiry Friday so the last call resolves | SD-2 |
| `interval` | `"hourly"` | Same bar size for stock and options — never mixed (DR-6) | brief |
| `start_cash` | `float` | Opening cash; the only equity the account ever receives | SD-3 |
| `entry_bar` | `"first"` \| `"last"` | Which hourly bar of the week's first session carries the entry | SD-4 |
| `strike_rule` | `"nearest_otm"` (P0) \| `"delta"` (P1) | How the strike is chosen (§5) | SD-5 |
| `delta_target` | `float`, P1 only | For `strike_rule == "delta"` | SD-5 |
| `itm_rule` | `"strict"` | ITM iff settlement print `> K`; equality is OTM (§7) | SD-6 |
| `shares`, `contracts` | `100`, `1` | Fixed by the brief | S-1 |
| `tz` | `"America/New_York"` | Every timestamp on the page is exchange time (§3.1) | S-8 |

## 3. The tape

### 3.1 Schema — `covered_call_tape.parquet`

One long table, one row per (bar, instrument). Parquet, not pickle (AD-11): inspectable, and
the pandas-version fragility that already broke `option_pipeline_data.synthetic.pkl` does not
apply.

| Column | Type | Notes |
|---|---|---|
| `ts` | `datetime64[ns, America/New_York]` | Bar timestamp, tz-aware. LSEG's convention (bar start vs end, UTC vs local) is **discovered by T-62**, then fixed here. |
| `ric` | `str` | Stock RIC or option RIC (expired form, with caret suffix) |
| `kind` | `"stock"` \| `"option"` | |
| `expiry` | `date` \| null | Option only |
| `strike` | `float` \| null | Option only |
| `cp` | `"C"` \| null | Calls only in P0 |
| `bid`, `ask` | `float` \| NaN | The quote at the bar. NaN is "not quoted", never 0. |
| `mid` | `float` \| NaN | `(bid + ask) / 2` **only when the quote is valid** (§6.1); NaN otherwise. Derived at load, not stored twice. |
| `trdprc_1` | `float` \| NaN | Last print in the bar, when someone traded |
| `open`, `high`, `low`, `volume`, `num_moves` | `float` \| NaN | Present when a trade printed; stock always |

Payload keys alongside the table (SYSTEM-SPEC §5.1 posture — additive only):
`ticker`, `root`, `window`, `interval`, `fetched_at`, `synthetic: bool`, `diagnostics`
(requested RICs, returned RICs, per-week counts, `strike_step_discovered`, `tz_convention`).

### 3.2 The calendar comes from the stock tape

Weeks and expiries are **read off the stock bars, never generated from a calendar**:

1. Group stock bars by ISO week. The **first session** of a week is its entry day; the **last
   session** is its expiry day (a Friday holiday makes it Thursday — that contract's RIC
   carries the Thursday date, which is what the exchange listed).
2. A week with fewer than two sessions is not a trading week for the strategy (nothing to
   enter and expire). Logged, skipped.
3. `end` must be a last-session day, so the final call resolves inside the window; the engine
   refuses a window that ends mid-week rather than inventing a close-out.

This is the brief's *"take the last session in each week from the stock tape so you do not
invent holiday expiries"*, made mechanical.

### 3.3 Chain construction and the pull

Per week, candidate calls are built with `build_candidate_rics` (SYSTEM-SPEC §6, T-31's suffix
rule applies) for strikes from a little below the window's stock low to a little above its high
— the same idea as 1.1. **The strike step is not assumed**: T-62 discovers which strikes return
data on the chosen name and records `strike_step_discovered`; the band is then generated on
that step. Requests are batched with the single-RIC fallback (AD-2), every failure is soft
(empty series, never a crash — the brief's own words), and each contract is requested only for
its life (from listing to expiry) rather than the whole window.

**Cache-first, exactly as 1.1 (AD-1):** `load_tape()` reads the parquet when present;
`fetch_tape()` refuses to overwrite one; `OSL_OFFLINE=1` forces the synthetic tape; nothing in
CI, tests or the build ever reaches the network. `option_pipeline_data.pkl` is never touched
by any of this.

### 3.4 The synthetic tape

`synthesize_tape(seed=7, end_date=...)` — the fixture and the no-cache fallback (AD-7). It takes
an explicit `end_date` from day one: OQ-6's calendar-dependent fixture has already failed CI
once and this one will not repeat it. It models the properties the engine must survive: quotes
present on most near-the-money bars and absent on some (including at least one entry bar per
window, so the skip path is always exercised), prints sparse, spreads wider on the first bar
of the day than the last, one holiday-shortened week, and a stock path that produces both OTM
and ITM Fridays. A page built from it says so and the CI guard refuses to publish it (§10).

## 4. The weekly loop

The engine is one pass over the calendar (§3.2) with three position states:

```
FLAT ──(entry: BUY 100 + SELL 1 call)──▶ COVERED ──(Friday OTM: EXPIRE)──▶ STOCK_ONLY
  ▲                                         │                                   │
  │                                         └──(Friday ITM: ASSIGN + SELL @K)───┤
  │                                                                             │
  └──────────────────────────(ITM resolution leaves you flat)────────────────────┘
STOCK_ONLY ──(next entry: SELL 1 call only)──▶ COVERED
STOCK_ONLY ──(no valid call quote: skip)─────▶ STOCK_ONLY   (shares held, uncovered, logged)
FLAT       ──(no valid call quote: skip)─────▶ FLAT         (nothing bought — the combo is one order)
```

Per week `w`, at the entry bar `b_entry` of the first session:

1. **Spot** `S` = the stock's `trdprc_1` at `b_entry`. Missing → skip the week (`SKIP_NO_STOCK_PRINT`).
2. **Strike** `K` = `select_strike(chain_w, S, params)` (§5). No strike satisfies the rule → skip (`SKIP_NO_STRIKE`).
3. **Quote** = the call `(w, K)` at `b_entry`. Not valid (§6.1) → skip (`SKIP_NO_QUOTE`). In state `FLAT` the skip means **no stock is bought either** — the brief's entry is the combo, and buying stock without the call would be a different strategy.
4. If `FLAT`: **BUY** `shares` at `S` — `cash -= shares × S`. *(Rule R-ENTRY-STOCK.)*
5. **SELL** `contracts` call at `mid` — limit at mid, fill at mid, `cash += contracts × 100 × mid`. *(R-ENTRY-CALL.)* State → `COVERED`.

At the last bar `b_exp` of the week's last session, if `COVERED`:

6. **Settle** (§7): `S_exp` = stock `trdprc_1` at `b_exp`. `S_exp > K` (SD-6) → **ASSIGN** the call (cash Δ 0) and **SELL** `shares` at `K` — `cash += shares × K`; state → `FLAT`. *(R-ASSIGN.)* Otherwise **EXPIRE** (cash Δ 0); state → `STOCK_ONLY`. *(R-EXPIRE.)*

That is the brief's loop, with the skip branches the brief only implies made explicit. The
ledger (§8) is then computed for **every bar** in the window from the blotter and the tape.

## 5. Strike selection

`select_strike(chain, S, params) -> float | None`, pure. `chain` is the set of strikes with any
row that week (listed, whether or not quoted at this bar — quoting is checked in step 3, not
here, so "no quote" and "no strike" are distinguishable in the skip log).

- `nearest_otm` (P0, SD-5): the smallest listed `K ≥ S`; `K == S` is ATM and allowed (the
  brief: "or ATM if spot sits on a strike"). None listed above `S` → `None`.
- `delta` (P1, SD-5): invert the mid at the entry bar with the 1.1 solver (`implied_vol`,
  `RISK_FREE_RATE`, act/365, DTE from `b_entry` to expiry) for every quoted strike above `S`,
  compute the BS delta, take the strike whose delta is nearest `params.delta_target`. A strike
  the solver refuses (`iv_refusal`) is not a candidate. Nothing to invert → `None`.

The rule and its parameters are printed on the page in words, and a test pins the printed
sentence to `params` so the two cannot say different things (FR-14).

## 6. Fills

### 6.1 A valid quote

A bar's option quote is valid iff `bid` and `ask` are both present, `bid > 0`, `ask > 0`, and
`ask ≥ bid`. A zero bid is "no bid" (the brief's words), a crossed market is a bad print, one
side alone has no mid. `mid` is NaN for anything else, and the engine reads only `mid`.

### 6.2 The fill

Default for this assignment, per the brief: **limit at mid, filled at mid, at the bar's
timestamp.** `limit == fill == mid` on every option row of the blotter — the column pair is
kept because the brief asks for both and because a future variant (the vol-curve fair price,
FR-20) would separate them. The stock leg fills at the bar's `trdprc_1` — the print — with
`limit == fill` there too.

Nothing is ever filled between bars, at a price not on the tape, or on a bar with no valid
quote. §12's I-3 and I-6 test exactly this.

## 7. Expiry settlement

- The settlement print is the stock's `trdprc_1` at the last bar of the expiry session.
  *(S-7. The official 4 pm close can differ by cents from the last hourly bar's last trade;
  using the tape's own bar keeps every number on the page reproducible from the tape.)*
- **ITM iff `S_exp > K`** (SD-6, `itm_rule == "strict"`). Equality is OTM: the OCC's
  auto-exercise threshold is $0.01 in the money, and a call exactly at the strike is not.
- ITM → `ASSIGN` on the option (`qty 1, limit —, fill 0, cash Δ 0`) **and** `SELL` on the
  stock (`qty 100, limit K, fill K, cash Δ +100 × K`). Two rows, same timestamp, in that order.
- OTM → `EXPIRE` on the option (`qty 1, fill 0, cash Δ 0`). One row.
- Settlement needs **no option quote** — an ITM call with no bid/ask on the expiry bar is
  still assigned. Only entries need quotes.
- Early assignment is not modelled (S-6). Ex-dividend dates inside the window are named in
  the write-up as the one place this matters.

## 8. The blotter

The brief's columns, exactly; one row per booked trade; **no working orders, no signals, no
skips** — those go to the skip log (§8.2).

| Column | Content |
|---|---|
| `time` | Bar timestamp, `America/New_York`, `YYYY-MM-DD HH:MM` |
| `instrument` | The RIC (`AAPL.O` / `AAPLH72620500.U^H26`) |
| `occ` | The OCC symbol as a subtitle: `{ROOT:<6}{YYMMDD}{C|P}{strike×1000:08d}` → `AAPL  260807C00205000`. `occ_symbol()` lives beside the RIC grammar in `option_surface_utils.py` and round-trips with `parse_option_ric` (T-67). |
| `side` | `BUY` · `SELL` · `EXPIRE` · `ASSIGN` |
| `qty` | `100` shares or `1` contract |
| `limit` | The order's limit; `—` on EXPIRE/ASSIGN |
| `fill` | The simulated fill; `0` on EXPIRE/ASSIGN |
| `cash_delta` | Signed, in dollars, **the only thing that ever moves cash** |
| `note` | The rule that fired: `R-ENTRY-STOCK` · `R-ENTRY-CALL` · `R-EXPIRE` · `R-ASSIGN` · `R-ASSIGN-SELL`, plus the one number a reader needs (`K=205 S=204.31 mid=1.325`) |

### 8.2 The skip log

A separate table on the page: `week, reason ∈ {SKIP_NO_STOCK_PRINT, SKIP_NO_STRIKE,
SKIP_NO_QUOTE, SKIP_SHORT_WEEK}, state_at_skip, detail`. It is not the blotter ("a blotter is a
list of trades") but it is how the page says *"no bid/ask → skip"* actually happened — the
brief grades the strategy doing what it says, and a skipped week is the strategy doing
something.

## 9. The ledger and the Reg T account

One row per bar in the window, computed from the blotter and the tape:

| Column | Formula |
|---|---|
| `shares` | Cumulative from blotter `BUY`/`SELL` |
| `short_calls` | `0` or `1`; with `strike`, `expiry` when `1` |
| `cash` | `start_cash + Σ cash_delta` over blotter rows at or before `ts` |
| `stock_mark` | Stock `trdprc_1` at the bar; **carried forward** from the last bar that had one, `mark_carried = True` on such rows (S-7) |
| `call_mark` | The short call's `mid` at the bar; carried forward likewise; on the expiry bar it is **intrinsic** `max(S_exp − K, 0)` so the mark and the settlement agree |
| `LMV` | `shares × stock_mark` |
| `option_mv` | `− short_calls × 100 × call_mark` (a short call is a negative MV) |
| `NAV` | `cash + LMV + option_mv` |
| `IM` | `0.50 × LMV` — the covered short call adds **$0** |
| `MM` | `0.25 × LMV` — no naked-option pad, the call is covered |
| `available` | `NAV − IM` — room to put on new risk |
| `excess` | `NAV − MM` — the margin-call line |
| `flag` | `NEG_AVAILABLE` when `available < 0` at an entry bar — the brief: *"you could not have put the trade on — say so"*. The trade is still booked (the backtest reports what the rule did) and the page prints the flag beside it. |

When flat, `LMV = IM = MM = 0` and `NAV = cash`. The page plots `NAV`, `IM`, `MM` on one axis
with hover, and the ledger table below it is the **daily** roll-up (the last bar of each
session) so a reader can check a week by hand; the hourly frame is what the chart draws.

Margin interest on a debit balance is not modelled (S-5); if SD-3 funds the account fully it
never arises, and if it does not, the write-up says so.

## 10. Mid-vs-print evidence (FR-17)

The justification for filling at mid, done the way the brief prescribes:

- **Sample:** every option bar in the window with a valid quote (§6.1) **and** a `trdprc_1`,
  restricted to near-the-money calls — strikes within `±band` of that bar's spot (default
  band `params.ntm_band = 5%`; printed).
- **Fit:** OLS of `trdprc_1` on `mid`. Report `n`, slope, intercept, **R²**, and the median
  `|trdprc_1 − mid|` in dollars and as a percentage of the mid. The figure draws the points,
  the fit, and `y = x`.
- **Stated caveat on the page:** within an hourly bar the print is the *last* trade and the
  quote is the bar's snapshot, so the pair is not simultaneous; the scatter is the honest
  measure of how far a mid can be from a real print at hourly resolution, which is the
  resolution the backtest fills at.

## 11. The page

Registered at `/covered-call/` with the generator (AD-11); built by
`covered_call/page.py: build_page(tape, params) -> Page` (NFR-5). Panels, in reading order:

1. **The strategy** — `Params` rendered as prose + a table (FR-14), and the rule ids the
   blotter's notes cite.
2. **NAV, IM, MM** over the window with hover (FR-16) — the hero.
3. **Blotter** (FR-15) — the full table; below it the **skip log** (§8.2).
4. **Ledger** — daily roll-up (§9).
5. **Mid vs print** — scatter, fit, R² (FR-17).
6. **Write-up** — the PO's prose (FR-19), the FR-7 mechanism: a prose module, `[unwritten]`
   in red, a test, and a CI guard.

No listener is needed: nothing cross-filters. Tables are HTML rendered by the generator's
templates, styled by `theme.PAGE_CSS` (the table rules are new — T-68, PO taste); below
`FIGURE_MIN_WIDTH` a table scrolls inside its panel like a figure does (T-47's posture).

**CI guards, per page:** refuse a page built from the synthetic tape; refuse `[unwritten]`;
require the R² line; require at least one `BUY` and one `EXPIRE`/`ASSIGN` in the blotter (a
page with an empty book renders plausibly and is wrong).

## 12. Invariants — the executable definition of "logically consistent" (NFR-6)

Each is a test over the **real** tape's book as well as the synthetic one. Written before the
engine; the engine is done when they pass. Mutation-check them (T-46's rule): inject the
defect and watch the test fail.

| ID | Invariant |
|---|---|
| I-1 | **Cash reconciles:** for every bar, `cash == start_cash + Σ cash_delta` of blotter rows at or before it; the final cash equals the sum of the blotter, to the cent. |
| I-2 | **NAV identity:** `NAV == cash + LMV + option_mv` on every ledger row. |
| I-3 | **No fill without a quote:** every `SELL` of a call sits on a bar whose `mid` is valid; every stock `BUY` on a bar with a stock print. |
| I-4 | **Fill within the market:** every option fill satisfies `bid ≤ fill ≤ ask` at its bar (with mid, equality to mid). |
| I-5 | **Never naked, never short stock:** `short_calls ≤ 1`, `short_calls == 1 ⇒ shares == 100`, `shares ∈ {0, 100}`, on every row. |
| I-6 | **Every trade is on the tape:** every blotter `time` is a bar timestamp of its instrument. |
| I-7 | **Every open call resolves:** for every week with a `SELL` call, the expiry session's last bar carries exactly one `EXPIRE` or one `ASSIGN` + one stock `SELL` at `fill == K`; no other exits exist. |
| I-8 | **Settlement is right:** `ASSIGN ⇔ S_exp > K` under `itm_rule`; `EXPIRE ⇔ S_exp ≤ K`. |
| I-9 | **The rule chose the strike it says it chose:** for every entry, re-running `select_strike` on that bar's chain and spot reproduces `K`; under `nearest_otm`, no listed strike lies in `[S, K)`. |
| I-10 | **Skips are real:** every week without an entry appears in the skip log with a reason the tape supports (no print / no strike / no valid quote / short week), and no week appears in both. |
| I-11 | **Reg T arithmetic:** `IM == 0.5 × LMV`, `MM == 0.25 × LMV`, `available == NAV − IM`, `excess == NAV − MM`; all zero when flat. |
| I-12 | **Determinism:** the same tape and `Params` produce a byte-identical blotter. |
| I-13 | **The page says what the book says:** the blotter and the R² rendered into the built page equal the engine's outputs for the committed tape (the T-44 lesson, applied to tables). |

## 13. Edge cases (AD-9 applied)

| Situation | Behaviour |
|---|---|
| No bid or no ask at the entry bar | Skip the week (`SKIP_NO_QUOTE`); in `FLAT`, buy nothing |
| Bid = 0, or ask < bid | Not a valid quote (§6.1) — same as above |
| Stock print missing at the entry bar | `SKIP_NO_STOCK_PRINT` |
| No listed strike ≥ spot | `SKIP_NO_STRIKE` |
| Monday holiday | The week's first session is the entry day (§3.2) |
| Friday holiday | The week's last session is the expiry day; the RIC carries that date |
| Week with one session | `SKIP_SHORT_WEEK` |
| ITM at expiry with no option quote | Assigned anyway — settlement needs no quote (§7) |
| `S_exp == K` | OTM, `EXPIRE` (SD-6) |
| Shares held into a skipped week | `STOCK_ONLY`: uncovered, ledger shows LMV with no option; nothing invented |
| Stock or option mark missing at a ledger bar | Carried forward, `mark_carried = True`, never interpolated |
| `available < 0` at an entry | Booked and flagged `NEG_AVAILABLE`; the page says so |
| Window ends before the last call resolves | Refused at load — `end` must be a last-session day |
| The RIC guess for a week returns nothing | That week has no chain → `SKIP_NO_STRIKE`; recorded in diagnostics |
| Tape is synthetic | Page banner + CI refusal (§11) |

## 14. Stated simplifications

Printed on the page under the strategy (FR-14), because a reader who cannot see them cannot
judge the book:

| ID | Simplification |
|---|---|
| S-1 | 100 shares, 1 contract, always |
| S-2 | Exit is to wait: no buy-backs, no rolls (FR-20 may add one variant after P0) |
| S-3 | Expiry is the week's last session per the stock tape |
| S-4 | No commissions or fees |
| S-5 | No margin interest |
| S-6 | No early assignment; dividends ignored (ex-dates named) |
| S-7 | Marks: stock at the bar's print, option at the bar's mid, carried forward when absent; intrinsic on the expiry bar |
| S-8 | Timestamps are exchange time; LSEG's bar convention as discovered by T-62 |
| S-9 | Skipped weeks are logged, not booked |
