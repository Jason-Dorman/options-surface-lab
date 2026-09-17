# System Spec — Assignment 2, Covered Call Backtest

| Field | Value |
|---|---|
| Status | Draft v1 — 2026-09-12. **§2–§10 and §12 are now the code's behaviour, not a target** (T-65, T-80, T-56, T-63, T-81, T-57 2026-09-15, and **T-58 2026-09-16**: the weekly loop, fills, settlement, the blotter, the skip log, the ledger, the I-1…I-12 suite and the mid-vs-print evidence). §11 and I-13 remain targets until T-79 / T-59 land (lockstep rule). §10 was **corrected 2026-09-16 by T-83's review** — the sample now excludes the post-close bar and the headline moved. |
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
| `entry_bar` | `"first"` \| `"last"` | Which hourly bar of the week's first session carries the entry. **`"last"`** — the closing hour, 15:00–16:00 ET | SD-4 ✅ |
| `strike_rule` | `"nearest_otm"` (P0) \| `"delta"` (P1) | How the strike is chosen (§5) | SD-5 |
| `delta_target` | `float`, P1 only | For `strike_rule == "delta"` | SD-5 |
| `itm_rule` | `"strict"` | ITM iff settlement print `> K`; equality is OTM (§7) | SD-6 |
| `shares`, `contracts` | `100`, `1` | Fixed by the brief | S-1 |
| `ntm_band` | `float`, `0.05` | Half-width of FR-17's near-the-money sample, as a fraction of that bar's spot (§10). A `Params` field rather than a constant so the page prints it — an R² without its sample is not a number a reader can check | §10 |
| `tz` | `"America/New_York"` | Every timestamp on the page is exchange time (§3.1) | S-8 |

## 3. The tape

### 3.1 Schema — `covered_call_tape.parquet`

One long table, one row per (bar, instrument). Parquet, not pickle (AD-11): inspectable, and
the pandas-version fragility that already broke `option_pipeline_data.synthetic.pkl` does not
apply.

| Column | Type | Notes |
|---|---|---|
| `ts` | `datetime64[ns, America/New_York]` | Bar timestamp, tz-aware, **stamped at the bar's START**. LSEG returns it tz-naive in **UTC**, start-stamped (T-62, 2026-09-13: `O_SEC_OFST` = 0 and `C_SEC_OFST` = 3599 on essentially every bar). Localise to UTC, convert to `America/New_York`, store converted. **Never hardcode a UTC hour** — 15:00 ET is 19:00 UTC under EDT and 20:00 UTC under EST, and the A2 window is entirely EDT. |
| `ric` | `str` | Stock RIC, or the option RIC **in whichever form returned data** (§3.3) |
| `kind` | `"stock"` \| `"option"` | |
| `expiry` | `date` \| null | Option only |
| `strike` | `float` \| null | Option only |
| `cp` | `"C"` \| null | Calls only in P0 |
| `bid`, `ask` | `float` \| NaN | The quote at the bar. NaN is "not quoted", never 0. |
| `mid` | `float` \| NaN | `(bid + ask) / 2` **only when the quote is valid** (§6.1); NaN otherwise. Derived at load, not stored twice. |
| `trdprc_1` | `float` \| NaN | Last print in the bar, when someone traded |
| `open`, `high`, `low`, `volume`, `num_moves` | `float` \| NaN | Present when a trade printed; stock always |

### 3.3 Two RIC forms, and the day is zero-padded

T-62 (2026-09-13) settled both, against LSEG:

- **`DAY` is zero-padded.** The brief's rule (*"not zero-padded — `5`, not `05`"*) does not
  resolve: all three of its single-digit-day AAPL examples fail as written and succeed padded
  (`AAPLH72620500.U^H26` → *universe not found*; `AAPLH072620500.U^H26` → 30 rows). The repo's
  `build_option_ric()` already pads. **Open with the instructor** — the brief is precedence 1
  and is not edited here.
- **The caret suffix is not immediate.** Two days after expiry the 11-Sep QQQ contracts still
  resolve only *live* (`QQQI112671500.U` → 24 bars; `….U^I26` → nothing), while the 04-Sep
  contracts, nine days out, resolve only under the caret. So a contract's form depends on how
  long ago it expired, by a boundary we do not control. **The pull requests the live form and
  the caret form, takes whichever returns rows, and records the winner per contract** in
  `diagnostics.ric_form_used` — the same fail-soft posture as Part A's put-suffix probe.

Payload keys alongside the table (SYSTEM-SPEC §5.1 posture — additive only):
`ticker`, `root`, `window`, `interval`, `fetched_at`, `synthetic: bool`, `diagnostics`
(requested RICs, returned RICs, per-week counts, `strike_step_discovered` (**$1.00** near the money on QQQ — T-62), `tz_convention`,
`ric_form_used`).

**Where they live (T-56):** in a JSON sidecar, `covered_call_tape.meta.json`, beside the
parquet — not inside it. A parquet file's own key-value metadata is engine-specific and
invisible to anyone who opens the file in something that is not pandas, and these keys are
exactly what a reader needs in order to trust the bars. `load_tape()` returns both halves as
one frozen record, `Tape(bars, meta)`, with `.stock` / `.options` / `.stock_index` /
`.weeks(params)` / `.strikes_for(expiry)` on it; `.synthetic` defaults to **True** when the
payload does not say, so an unlabelled tape is treated as the dangerous case. That record is
what `run_backtest(tape, params)` and `build_page(tape, params)` are handed.

### 3.2 The calendar comes from the stock tape

Weeks and expiries are **read off the stock bars, never generated from a calendar**:

1. Group stock bars by ISO week. The **first session** of a week is its entry day; the **last
   session** is its expiry day (a Friday holiday makes it Thursday — that contract's RIC
   carries the Thursday date, which is what the exchange listed).
2. A week with fewer than two sessions is not a trading week for the strategy (nothing to
   enter and expire). Logged, skipped.
3. `end` must be a last-session day, so the final call resolves inside the window; the engine
   refuses a window that ends mid-week rather than inventing a close-out.
3b. **The live leg is the one place a date comes from the calendar** (FR-21, `live.coming_friday`).
   Looking *forward*, that week's tape does not exist yet, so the expiry has to be computed.
   It fails soft rather than guessing: a Friday holiday means the RIC does not resolve, the
   chain comes back empty, and the week is logged `SKIP_NO_STRIKE` instead of being booked
   against a contract that was never listed. The *entry day* is still read off the tape —
   `capture()` pulls the week and takes its first session, which is why a Labor Day Monday
   enters on the Tuesday by itself.
4. **The entry and expiry bars are the session's *closing hour*, never its last bar** (T-62).
   Both tapes run past the 16:00 ET equity close and the late bars carry real quotes: an
   option session returns 8 hourly bars, 09:00 ET through 16:00 ET starts; the stock returns
   16, 04:00 ET through 19:00 ET starts. So the **closing bar** is the one whose ET start is
   **15:00**, and `entry_bar = "first"` would mean the 09:00 bar. Taking `max(ts)` of a session
   silently books the post-close stub instead: on 2026-09-08 that moved the 18-Sep 715 call's
   mid from 11.195 to 11.02, $17.50 a contract. Every rule below says *closing bar* and means
   this.

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

**Cache-first, exactly as 1.1 (AD-1):** `load_tape()` reads the parquet when present and
synthesizes only when it is absent; `fetch_tape()` refuses to overwrite one; nothing in CI,
tests or the build ever reaches the network. `option_pipeline_data.pkl` is never touched by
any of this.

> **Corrected 2026-09-15 (T-63).** This section first said "`OSL_OFFLINE=1` forces the
> synthetic tape", carried over from Part A's wording. Taken literally it would break the
> deploy: CI sets `OSL_OFFLINE` on **every** build, so the covered-call page would be rendered
> from a fabricated book — which §11's own publish guard then refuses. What the flag means,
> here and in 1.1's `lseg_available()`, is **never pull**. The committed tape always wins when
> it is present; only `fetch_tape()` reads the variable, and a test pins that.

**Landed 2026-09-14 (T-56)**, with three details the writing above left open:

- The band is generated **per week, from that week's own bar range**, padded four steps either
  side — not from the window's. Two weeks twenty points apart would otherwise each request the
  other's strikes, against an expiry that never listed them.
- The ladder is computed in **integer hundredths**, the unit the RIC grammar stores a strike
  in. A float ladder drifts, and a RIC one cent off a real contract does not error — it
  returns nothing, which reads as "that strike was never listed".
- `load_tape()` **never reaches the network under any circumstances**, whatever `OSL_OFFLINE`
  says; only `fetch_tape()` does, and it refuses to run under it. The offline guarantee is
  therefore a property of which function you called, not of an environment variable.
- A pull that returns no stock bars **writes nothing at all**: a half-written tape would block
  the retry (fetch refuses an existing file) and would render as a plausible empty book.

The procedure is [RUNBOOK](RUNBOOK.md) §8.

### 3.4 The synthetic tape

`synthesize_tape(seed=7, end_date=...)` — the fixture and the no-cache fallback (AD-7). It takes
an explicit `end_date` from day one: OQ-6's calendar-dependent fixture has already failed CI
once and this one will not repeat it. It models the properties the engine must survive: quotes
present on most near-the-money bars and absent on some (including at least one entry bar per
window, so the skip path is always exercised), prints sparse, spreads wider on the first bar
of the day than the last, one holiday-shortened week, and a stock path that produces both OTM
and ITM Fridays. A page built from it says so and the CI guard refuses to publish it (§10).

**Landed 2026-09-15 (T-63)** as `synthesize_tape(end_date, *, seed=7, weeks=12)` in
`tape.py`, returning a `Tape` whose schema, dtypes and payload shape a pulled tape's cannot be
told apart from — only `Tape.synthetic` separates them, and that is what the page prints and
CI refuses to publish.

**`end_date` is required and positional**, a deliberate deviation from the signature sketched
above: a default would be a clock reference waiting to happen, and OQ-6 has already cost one
false CI failure. A test asserts the parameter has no default and that no clock function
appears anywhere in the generator's source.

Each week of the window has a **named role**, so a test asks for the case it needs instead of
hunting for a week that happens to have it (`diagnostics.synthetic_roles`, and the
`role_weeks` fixture):

| Week | Role | What it exercises |
|---|---|---|
| 2 | `monday_holiday` | DR-7 — the week's first session is the Tuesday |
| 4 | `no_quote_at_entry` | `SKIP_NO_QUOTE` — the chosen strike shows a zero bid at the entry bar |
| 5 | `no_strike_above_spot` | `SKIP_NO_STRIKE` — the chain exists but tops out below spot |
| 7 | `friday_holiday` | DR-7 — the expiry is the Thursday, and the RIC carries that date |
| 8 | `short_week` | `SKIP_SHORT_WEEK` — one session, nothing can both enter and expire |
| 9 | `half_session_entry_day` | `SKIP_NO_STOCK_PRINT` — the session exists, the 15:00 bar does not |

The rest are ordinary, and both ITM and OTM Fridays occur among them (a window that never
assigns exercises neither the assignment nor the shares leaving the book). Option prices are
Black-Scholes on **each bar's own spot** at `SYNTHETIC_SIGMA`, so a mid is never inconsistent
with the underlying beside it — a mutation run showed that pricing off one fixed spot passes
every static bound while destroying exactly the relationship T-57 and T-58 read.

`load_tape()` falls back to it with a `RuntimeWarning`, and `fallback=False` demands the real
tape instead for callers that would rather stop than render a shape.

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

At the **closing bar** `b_exp` of the week's last session (§3.2 item 4 — the 15:00 ET bar,
not `max(ts)`), if `COVERED`:

6. **Settle** (§7): `S_exp` = stock `trdprc_1` at `b_exp`. `S_exp > K` (SD-6) → **ASSIGN** the call (cash Δ 0) and **SELL** `shares` at `K` — `cash += shares × K`; state → `FLAT`. *(R-ASSIGN.)* Otherwise **EXPIRE** (cash Δ 0); state → `STOCK_ONLY`. *(R-EXPIRE.)*

That is the brief's loop, with the skip branches the brief only implies made explicit. The
ledger (§9) is then computed for **every bar** in the window from the blotter and the tape.

**Landed 2026-09-15 (T-57)** as `covered_call/engine.py: run_backtest(tape, params) -> Book`,
with two refusals the writing above left implicit. `window_weeks()` enforces §3.2 item 3 —
`end` must be a **last-session day**, so the final call resolves inside the window — and it
also refuses a week the window only **half** covers. Straddling is the silent case: trading
the inside half would book an entry whose expiry session the tape does not carry, and dropping
it would break I-10, which says every week without an entry appears in the skip log with a
reason. Neither is acceptable, so the engine stops and says which weeks straddle.

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

**The live leg cannot make this distinction, and says so** *(T-82, 2026-09-15)*. The
definition above turns on `chain` being the **listed** strikes — that is what keeps
`SKIP_NO_STRIKE` and `SKIP_NO_QUOTE` apart. The backtest reads the listed set off the tape
(`Tape.strikes_for`). The live leg has no chain to read: `capture()` **guesses** a band of
RICs around spot and keeps whichever answer, so a contract that is listed but returns
nothing at the entry bar is indistinguishable from one that was never listed. It is
therefore absent from `snapshot["chain"]`, and `select_strike` walks past it to the next
strike up instead of the week skipping. Demonstrated: with spot 700.40 and the 701 listed
but unquoted, the backtest logs `SKIP_NO_QUOTE` and the live leg writes the **702**.
This is a property of guess-and-check acquisition (DR-10), not a defect in `select_strike`,
and it cannot be closed by making the live leg treat an unanswered RIC as listed — it would
then skip every week in which any guessed strike was never listed, which is most of them.
**It is a stated limitation for the write-up, and it qualifies NFR-5's "one code path":**
the *rule* is one function, the *chain handed to it* is not the same set. Monday 09-14's
booked entry is unaffected — the 710 it wrote was quoted at the bar (6.01 / 6.08).

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

### 6.3 What the fill actually rests on, measured

All of this was measured on 2026-09-14 against the 09-08 15:00 ET entry bar — the same bar
the T-80 rehearsal booked — and it is stated at exactly the strength the data supports.

**`BID` and `ASK` are the bar's final reported quote**, not its open and not an average.
LSEG returns a four-field family per side (`OPEN_BID`, `BID_LOW_1`, `BID_HIGH_1`, `BID`); on
the 719 call, `BID` = 4.77 against an open of 5.29, inside a 4.29–5.40 range. So the fill is
*the midpoint of the final bid and ask reported in the 15:00–16:00 bar*, and the page says it
that way.

**What we may not say.** Two claims are *not* supported and must not appear on the page:

1. That these are **NBBO** quotes. LSEG's `BID`/`ASK` on a `.U` RIC have not been shown to be
   the OPRA national best bid and offer rather than some other consolidated best quote. The
   1.1 README's "closing NBBO midpoint" describes `MID_PRICE` on *daily* bars, which is a
   different field on a different frequency, and does not transfer.
2. That the **quote** was updated at any particular second. `C_SEC_OFST` times the bar's last
   **trade**: the stock reports `C_SEC_OFST` 3599 with `NUM_MOVES` 59,239 but `BID_NUMMOV`
   135,274, and there is no `BID_SEC_OFST`. At this resolution the last quote update cannot
   be timed, so nothing claims it was.

**Synchronisation, measured rather than assumed** (DR-6 gives both legs the same bar, which is
not the same as the same instant):

| On the 09-08 15:00 ET bar | Stock | 719 call |
|---|---|---|
| last trade offset in the bar | 3599 s (15:59:59) | 3594 s (15:59:54) |
| last print | 718.41 | 4.81 |

The two legs' last trades are **5 seconds apart**, and spot finished at 718.41, below the 719
strike the rule selected. **That is trade-to-trade, not trade-to-quote.** LSEG exposes no
timestamp for the final bid/ask update at this resolution, so the closing quote could in
principle have been established earlier in the hour; quote-level synchronisation **cannot be
established** and is not claimed. Synchronisation is therefore stated at the **common-bar
level**, with the trade offsets given as the sharpest available evidence — and `plan_entry`
books the measured gap into the blotter note (`sync=5s`) so every row carries its own
evidence instead of relying on this paragraph.

**The strike was not obvious all hour, and the page says so.** Inside that same bar the stock
opened at 719.315 and ranged 717.25–719.55. Had the entry been read at the bar's *start*
rather than its close, the nearest-OTM rule would have chosen **720**, not 719. This is the
concrete argument for fixing the observation point rather than merely fixing the bar, and it
is why `capture()` records `HIGH_1`/`LOW_1` for the entry bar.

**The page states this as a hierarchy** (PO, 2026-09-14), and `covered_call/writeup.py` is
its single source: *Rule* — closing observation of the Monday hourly bar, then nearest OTM.
*Fill* — the final bid and ask reported for that same hourly option bar, at the midpoint.
*Stock* — the final observed stock print in that bar. *Audit evidence* — the last-trade
offsets and the intra-bar range, shown for inspection. *Limitation* — the quote-update
timestamp is unavailable, so synchronisation is established at the common-bar level, not at
the exact quote-event level. **Never "the closing price"** for 718.41: it is the last stock
print in the bar, and the official 4 pm auction price is a different number (S-7).

**One observation is not the evidence.** On that bar the mid was 4.80 against a last print of
4.81. Encouraging, not probative: the chain-wide midpoint-versus-print regression and its R²
(FR-19) are what test whether midpoint fills are a reasonable execution assumption, and this
single row only introduces them.

## 7. Expiry settlement

- The settlement print is the stock's `trdprc_1` at the **closing bar** of the expiry session.
  *(S-7. The official 4 pm close can differ by cents from the last hourly bar's last trade;
  using the tape's own bar keeps every number on the page reproducible from the tape.)*
- **If that bar carries no print, settlement falls back to the last print in the same session
  at or *before* the close, and the blotter row says so** (`S_exp_carried`). *(Added by T-57,
  2026-09-15 — the specification had no answer here and the engine needed one.* **Entry and
  settlement are deliberately asymmetric:** a missing print at the *entry* bar skips the week,
  because nothing is owed yet and DR-1 forbids inventing one; a missing print at the
  *settlement* bar may not skip, because the call is already short and I-7 says every open call
  resolves — a skipped settlement would leave the book carrying that call forever. The fallback
  searches **backwards** only: a bar after the close is T-62's post-close stub, and resolving a
  contract against one is the `max(ts)` defect wearing a different hat. A session with no print
  at all before the close **raises** — that is a broken tape, not a market fact. Neither tape
  exercises this today, so the path is driven by a test that blanks the bar on a copy of the
  synthetic tape.*)
- **This carry-forward is the backtest's rule. The live leg (FR-21) does not carry forward**,
  and logs `SKIP_NO_STOCK_PRINT` instead. It reads **one bar**, not a session, so it has
  nothing to carry from; the ways a bar can be unreachable — an LSEG timeout, an early
  close, a run before the 15:00 bar has closed — are intercepted upstream by
  `live.unreadable_reason()`, which writes **nothing** and exits 2 (T-81). What is left is a
  15:00–16:00 ET bar that exists and carries quotes but no trade at all, which is not a
  reachable input for QQQ. *(Scoped 2026-09-15 by T-82: §7's paragraph above was written for
  the engine and read as though it bound both legs, leaving the spec and `live.py`
  asserting opposite rules over Friday's settlement. If the PO would rather the live leg
  carried forward too, `capture()` already records `bars_in_session` and the change is
  small — but it would be a change made days before that leg runs for real.)*
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

One row per **stock** bar in the window, computed from the blotter and the tape. Column names
are lower case in the code (`lmv`, `option_mv`, `nav`, `im`, `mm`); the page title-cases them.
Two more columns carry what a reader needs to place a row: `week` (the bar's own ISO label)
and `entry` (true on a bar that booked an entry, which is what `flag` keys on).

**The row at an entry bar already contains the trade.** `cash` counts every blotter row at or
*before* the bar, so an entry bar shows the position on, not the position about to go on. A
reader checking NAV by hand against the chart depends on knowing which.

| Column | Formula |
|---|---|
| `shares` | Cumulative from blotter `BUY`/`SELL` |
| `short_calls` | `0` or `1`; with `strike`, `expiry` when `1` |
| `cash` | `start_cash + Σ cash_delta` over blotter rows at or before `ts` |
| `stock_mark` | Stock `trdprc_1` at the bar; **carried forward** from the last bar that had one (S-7). `mark_carried` is True on a row where **either** mark came from an earlier bar |
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
with hover, and the ledger table below it is the **daily** roll-up (the **closing bar** of each
session) so a reader can check a week by hand; the hourly frame is what the chart draws. The
roll-up is a *selection* of hourly rows, never a re-aggregation, so a number in the table is a
number in the chart.

**A headline figure comes off the close, never off the last row** (T-57). The stock tape runs
to a 19:00 ET bar, so `ledger.iloc[-1]` is a thin post-close stub — `Book.final_nav` reads the
last **15:00** row instead. This is T-62's `max(ts)` trap one layer up, and on the committed
tape the two numbers differ, which is what makes the test that pins it a check.

Margin interest on a debit balance is not modelled (S-5); if SD-3 funds the account fully it
never arises, and if it does not, the write-up says so.

## 10. Mid-vs-print evidence (FR-17)

The justification for filling at mid, done the way the brief prescribes. **Landed 2026-09-16
(T-58)** as `covered_call/evidence.py` — `mid_vs_print(tape, params, *, band=None) ->
MidVsPrint` — with `notebooks/03_covered_call.ipynb` §5 as its companion, and **corrected the
same day by T-83's adversarial review**, which moved the headline. It is **its own module**
(AD-12, amended by the PO): `rules` decides, `engine` books, `evidence` measures, and
`evidence` may not import `engine` — a fit computed from the book would restate the fill
assumption rather than check it. Only the *parameter* stays in `rules`: `Params.ntm_band`,
because FR-14 prints the strategy record whole.

- **Sample:** every **call** bar of the **regular session** (ET start ≤ `CLOSING_BAR_HOUR_ET`)
  in the window that carries a valid quote (§6.1) **and** a `trdprc_1`, with a strike within
  `±band` of that bar's spot (default `params.ntm_band = 5%`; printed). Spot is the stock's
  print **at that same bar**, never interpolated: a bar whose underlying did not print has no
  moneyness, so it is refused rather than banded against a spot borrowed from elsewhere
  (AD-9, DR-1).
- **Fit:** OLS of `trdprc_1` on `mid`. Report `n`, slope, intercept, **R²**, and the median
  `|trdprc_1 − mid|` in dollars **and**, as a separate statistic, the median of
  `|trdprc_1 − mid| / mid`. The figure draws the points, the fit, and `y = x`.
- **Stated caveat on the page:** within an hourly bar the print is the *last* trade and the
  quote is the last bid and ask reported in it, so the pair is not simultaneous; the scatter is
  the honest measure of how far a mid can be from a real print at hourly resolution, which is
  the resolution the backtest fills at. The wording lives in
  `evidence.NON_SIMULTANEITY_CAVEAT` so the page and the notebook cannot state it differently.

**Every word of "near-the-money regular-session calls" is enforced, not inherited.** T-83 found
three of them true only by accident of the tape: nothing filtered `cp`, nothing excluded the
**16:00 ET post-close bar** (9.3% of the published sample, and the *tightest* cohort in it — a
stub on a fifth of the volume, banded against an extended-hours spot, flattering the number it
was offered as evidence for), and nothing refused a tape pulled for another underlying — the
guard `engine` has had since T-82, which now lives in `rules.require_matching_underlying` and
is called by both.

**The refusals are half the claim.** Every option bar the window holds is either in the sample
or in exactly one named bucket, and `n` plus the buckets reconciles against the bars
considered — a count that does not add up is indistinguishable from a sample quietly dropping
rows, and it reaches a doc as a number an operator then "checks" (T-77). Attribution order is
**structure, then market**: `not_a_call → no_strike → post_close → no_spot → outside_band →
no_quote → no_print`. Structure first because a bucket must never name a fact that is not true
of the row it counts — a strikeless bar was filed under `outside_band`, i.e. reported as having
sat outside a band it had no position relative to. Among the market buckets the band comes
first because it is the sample *universe*: ordered the other way, `no_print` counts every
deep-OTM contract nobody was ever going to trade and answers nothing.

**No fit is a valid answer.** Below `MIN_FIT_POINTS = 3` **distinct** mids, slope, intercept
and R² are `NaN`, `fitted` is False and `fit_y` returns nothing to draw — FR-11's `iv_refusal`
posture applied to a regression. Three guards were written here before one was right:
`sxx <= 0` fails because the mean of N identical floats is not exactly that float (2,251 copies
of 12.34 leave `sxx` ≈ 1e-27 and a confident garbage slope); `x.max() == x.min()` then fails on
its own neighbour (2,250 identical mids plus **one** other has a spread, passes, and reports
`slope = 6.0000, R² = 1.0000` off two points); the distinct count closes both, and subsumes a
separate point-count guard that the mutation run showed could never fire.

**`median_gap` is not the fit's residual.** It measures `|print − mid|`, the distance from
`y = x`, because that is the error the book books when it fills at the mid. A sample sitting
exactly on `print = 0.6 × mid + 1.25` would have R² = 1 and a median gap over a dollar.

**The dollar and the percentage are two medians of two different variables.** The page prints
them as separate statistics rather than "$0.035 (1.89% of the mid)", which invites the reader
to divide and infer a median mid of $1.85. The real median mid is **$4.75**.

### 10.1 What the committed tape says

`covered_call_tape.parquet`, pulled 2026-09-15. Of **37,073** option bars in the window:

| Bucket | Bars |
|---|---|
| `not_a_call` | 0 |
| `no_strike` | 0 |
| `post_close` (16:00 ET stub) | 4,633 |
| `no_spot` | 0 |
| `outside_band` (beyond ±5%) | 10,178 |
| `no_quote` (§6.1 refuses it) | 1,492 |
| `no_print` (quoted, nobody traded) | 4,144 |
| **in the sample** | **16,626** |

So of the **22,262** near-the-money regular-session call bars, **74.7%** carried both a valid
quote and a print; of the quoted ones, **80.1%** traded. On that sample:

**`print = 0.9979 × mid + 0.0104`, R² = 0.9962, median `|print − mid|` = $0.035, median
`|print − mid| / mid` = 1.89%.**

**Robustness.** Swept from ±1% to ±25% of spot, the slope stays within **0.9978 – 1.0020** and
R² within **0.9948 – 0.9979**, dipping to its floor at **±2%** rather than moving monotonically.
Above **±14%** the band stops binding — the sample saturates at n = 18,712 — so the top of that
range is the same measurement repeated. *(The floor was published as 0.9960 until T-83: a
number read off the wrong row of the notebook's own five-point grid, in a commit whose stored
output already printed 0.994843. Four review lenses found it independently. The sweep's
min, max and saturation point are pinned by a test now.)*

**The ten fills.** All ten calls the book wrote are in the sample — pinned contract by
contract, not by timestamp, so a band or a window that quietly excluded a fill fails rather
than flatters. At those bars the median `|print − mid|` is **$0.0375**, 0.67% of the mid, worst
case $0.145: about **$3.75 a contract** against a median premium of $644.50.

### 10.2 What the evidence will not support — read before writing FR-19

T-83's review produced six findings that change how this number should be described. They
belong in the write-up rather than in a reader's discovery.

1. **$0.035 is exactly one half-spread.** Measured per row, the median `|print − mid|` divided
   by that bar's own half-spread is **1.000** — at the fills too. Only **30.4%** of prints land
   strictly inside the quoted bid/ask; **28.3%** land exactly on an edge and **41.3%** outside
   it. So the honest statement is not "the print is near the mid" but *the print is typically a
   full half-spread away, i.e. at a quote edge* — which is what makes the spread, not the gap,
   the scale that matters. The mid is unbiased, not accurate.
2. **The fit adds nothing to the identity line.** The fitted R² is 0.996214; the R² of `y = x`
   with no fitting at all is 0.996209. They differ in the sixth decimal. The OLS is worth
   reporting because the brief asks for it, but the claim it supports is "the print is centred
   on the mid", and the slope and the median gap say that better than R² does. R² over an `x`
   spanning two orders of magnitude is easy to make large — ±5% of a $720 underlying is ±$36,
   so the sample reaches contracts more than thirty dollars in the money whose mid is nearly
   all intrinsic.
3. **The fit is carried by contracts the book never writes.** Bars with mid > $10 are **34.1%**
   of the sample and **68.5%** of the regression's leverage; the $5.00–$9.50 band where all ten
   fills actually sat is 13.6% of the rows and **0.5%** of the leverage.
4. **The entry bar is the worst hour of the session, not the average.** Pooled over the day the
   median gap is $0.035 (1.89%); at the 15:00 ET bar the rule fills at it is **$0.060 (2.25%)**.
   Split further: the 1,937 entry-session 15:00 bars run $0.045 (2.19%), and the 294
   **expiry-session** 15:00 bars run **$0.305** — 8.7× the sample, and a bar no entry ever
   reads, because settlement takes the *stock* print.
5. **Selection bias is real but concentrated where the rule does not write.** The 4,144
   unprinted bars are **95.4% in the money**, median mid $26.68, median half-spread $0.310
   against $0.025 for the bars that printed — so the censoring is a deep-ITM phenomenon, not a
   general "the quiet ones are missing". In the ±1% band the rule actually writes in, **99.9%**
   of quoted bars printed. The measured gap is a floor on the error *for deep-ITM contracts*
   and very nearly the whole truth near the money.
6. **`n` is not 16,626 independent observations.** The sample is a panel: **766 contracts**
   across **343 bars**, the same contract reappearing dozens of times and every contract in one
   bar sharing one spot and one market state. Quote R² accordingly; "a slope indistinguishable
   from one" is an inferential claim this sample rejects (t = −5.6 naive, −3.4 clustered by
   contract). The defensible statement is the *size* of the deviation — 0.21%, under a cent
   near the money — not its significance.

**The bound that actually matters, and it is small.** The signed gap has mean −$0.0078 and
median $0.000 (t = −1.72): no economically meaningful bias against the seller. And the
worst case can be priced outright — selling all ten calls at the **bid** instead of the mid
costs **$49.50** over the window, moving the return from **1.658% to 1.592%**. Whatever moves
this backtest's result, it is not the fill rule. That sentence is the one FR-19 should make,
and it rests on the $49.50, not on the R².

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

**Landed 2026-09-15 (T-57):** I-1 … I-12 are in `tests/covered_call/test_engine.py`, each one
running over **both** books — the seeded synthetic tape and the committed real one — and each
mutation-checked. They recompute from the *blotter's own rendered columns* and from
`tape.bars`, never from something `run_backtest` handed back on the side (T-46's rule). I-13
waits on the page (T-59).

| ID | Invariant |
|---|---|
| I-1 | **Cash reconciles:** for every bar, `cash == start_cash + Σ cash_delta` of blotter rows at or before it; the final cash equals the sum of the blotter, to the cent. |
| I-2 | **NAV identity:** `NAV == cash + LMV + option_mv` on every ledger row. |
| I-3 | **No fill without a quote:** every `SELL` of a call sits on a bar whose `mid` is valid; every stock `BUY` on a bar with a stock print. |
| I-4 | **Fill within the market:** every option fill satisfies `bid ≤ fill ≤ ask` at its bar (with mid, equality to mid). |
| I-5 | **Never naked, never short stock:** `short_calls ≤ 1`, `short_calls == 1 ⇒ shares == 100`, `shares ∈ {0, 100}`, on every row. |
| I-6 | **Every trade is on the tape:** every blotter `time` is a bar timestamp of its instrument. |
| I-7 | **Every open call resolves:** for every week with a `SELL` call, the bar the settlement print came from — the expiry session's **closing bar**, or, when that bar carries no print, the earlier bar §7's carry-forward read (`S_exp_carried` in the note) — carries exactly one `EXPIRE` or one `ASSIGN` + one stock `SELL` at `fill == K`. Nothing resolves after the close, nothing off the expiry session, and no substitution is silent; no other exits exist. *(Widened 2026-09-15 by T-82: as first written, I-7 contradicted §7's carry-forward, which the same session had added — the suite NFR-6 calls the executable definition of "logically consistent" would have gone red against behaviour the spec calls correct.)* |
| I-8 | **Settlement is right:** `ASSIGN ⇔ S_exp > K` under `itm_rule`; `EXPIRE ⇔ S_exp ≤ K`. |
| I-9 | **The rule chose the strike it says it chose:** for every entry, re-running `select_strike` on that bar's chain and spot reproduces `K`; under `nearest_otm`, no listed strike lies in `[S, K)`. |
| I-10 | **Skips are real:** every week without an entry appears in the skip log with a reason the tape supports (no print / no strike / no valid quote / short week), and no week appears in both. |
| I-11 | **Reg T arithmetic:** `IM == 0.5 × LMV`, `MM == 0.25 × LMV`, `available == NAV − IM`, `excess == NAV − MM`; all zero when flat. |
| I-12 | **Determinism:** the same tape and `Params` produce a byte-identical blotter. |
| I-13 | **The page says what its sources say:** the blotter rendered into the built page equals `run_backtest`'s output for the committed tape, and the R² equals `evidence.mid_vs_print`'s (the T-44 lesson, applied to tables). *Corrected 2026-09-16 (T-83): this said "the engine's outputs" for both, written before T-58 moved the R² out of the engine's reach — and `evidence` may not import `engine`, so taken literally it asked for a comparison the package's own layering forbids. Amending a spec means re-reading the invariants that quote it; T-82 recorded that lesson eight lines above the section T-58 edited.* |

## 13. Edge cases (AD-9 applied)

| Situation | Behaviour |
|---|---|
| No bid or no ask at the entry bar | Skip the week (`SKIP_NO_QUOTE`); in `FLAT`, buy nothing |
| Bid = 0, or ask < bid | Not a valid quote (§6.1) — same as above |
| Stock print missing at the entry bar | `SKIP_NO_STOCK_PRINT` |
| Stock print missing at the **expiry closing bar** | Settlement carries the last print in that session at or before the close; the blotter note says `S_exp_carried`. No print in the session at all → the engine raises (§7) |
| A week the window only half covers | Refused at load — the engine will neither trade half a week nor drop it (§4) |
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
