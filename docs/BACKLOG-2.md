# Backlog — Assignment 2, Covered Call Backtest

The task board for the second assignment. Same rules as [BACKLOG.md](BACKLOG.md): work
top-down within the current milestone; task IDs are one sequence across both boards and are
never renumbered; update status in the session that does the work; **[PO]** tasks are
scaffolded by sessions, completed by the PO. Requirement-level status lives in
[PRD.md Part B](PRD.md) (§13–§20); behaviour in [SPEC-COVERED-CALL.md](SPEC-COVERED-CALL.md).

**Status:** ✅ done · ◐ in progress · ☐ todo · ⊘ blocked (blocker named)

**Due: Sunday 2026-09-20, 11:59 pm EST. First live entry: Monday 2026-09-14** (PO, 2026-09-12).

**Sequencing — under review.** The PO chose restructure-first before the due date was known.
With eight days left, the session **recommends deferring [BACKLOG.md](BACKLOG.md) M5 until
after the submission** and building this page on the current builder (T-79) — **PO to
confirm**. Either way the tape and the engine are pure Python and start now. The order that
fits the calendar: ~~T-62 spike~~ (✅ 2026-09-13) → ~~SD-2, SD-3, SD-5, SD-6 decided~~ (✅ 2026-09-13, T-55) → **T-65 rules + T-80 live leg, dry-run
by Sunday** → **T-78 Monday's entry, booked by the system** → T-56 pull → T-57 engine + invariants → T-58 → T-79/T-59 page → T-60 write-up →
T-71/T-72 ship by Saturday 09-19.

---

## A2-M0 — Governance and the decisions

| ID | Task | Maps to | Status |
|---|---|---|---|
| T-76 | Governance docs: PRD Part B (§13–§20), `SPEC-COVERED-CALL.md`, this board, AD-12 proposed, precedence tables updated | all | ✅ 2026-09-12 |
| T-62 | **Spike — what LSEG gives hourly on an expired weekly, on QQQ.** Pull `QQQ.O` daily for the window to band strikes, then one recent expired Friday QQQ call near the money hourly over its life (a `QQQI42657000.U^I26`-shaped RIC — 04-Sep-26 expiry, strike from the band; the brief's proven RICs are AAPL, so this **proves the QQQ root and format**), plus `QQQ.O` hourly for the same days; confirm the 09-11 expiry already resolves under the expired form (SD-2). Record: the fields that return, bar timestamp convention (start/end, UTC/local), how far back hourly history reaches for expired contracts, which strikes around it return data (the step). **Writes no cache.** Closes OQ-10 / OQ-11 / OQ-12 and fixes SPEC §3.1's `ts` convention. Can run today — touches nothing on the board. | FR-13, OQ-10–12 | ✅ **2026-09-13.** Evidence: `notebooks/t62_qqq_hourly_spike.json`. QQQ root and format proven. **Bars are tz-naive UTC stamped at the START**, and both tapes run past the 16:00 ET close with real quotes — so the *closing bar* is the 15:00 ET one and `max(ts)` is a post-close stub (SPEC §3.2 item 4). **Strike step $1.00.** Hourly reaches a contract's whole life. Two surprises: the brief's unpadded-`DAY` RIC rule does not resolve (OQ-15, padded is right), and the caret suffix is **not** immediate — 09-11 is still live-form only, so the pull must try both (SPEC §3.3). |
| T-55 | **[PO]** The strategy decisions SD-1 … SD-6 (PRD §15 — options and a recommendation for each): underlying, window, starting cash, entry bar, strike rule, ITM rule. | FR-14, §15 | ✅ **All six closed.** SD-1 **QQQ** (2026-09-12). 2026-09-13: SD-2 **`2026-07-06 → 2026-09-11`**, SD-3 **$75,000 fully funded**, SD-4 **last bar — the 15:00 ET closing bar**, SD-5 **nearest OTM**, SD-6 **strict (`> K`)**. Consequences measured by T-62 and recorded in PRD §15: nearest OTM on a $1 step lands ~0.1% above spot and **6 of 10 weeks assign**; peak entry cost **$72,984** against $75,000, so the book is ~97% invested at the peak and `NEG_AVAILABLE` never fires. Still to do: **print them on the page** (FR-14). |
| T-74 | **[PO]** Sign off AD-12 — one subpackage per assignment (`options_surface_lab/covered_call/`), layered inside. | AD-12 | ☐ |
| T-78 | **[PO + session] Monday 2026-09-14 — the first entry, booked by the system** (FR-21). *Must exist before the bar:* ~~SD-2…SD-6 decided~~ (✅ T-55); T-65 and T-80 merged and **dry-run against Friday 09-11's expired chain** on Sunday; Workspace open and logged in **when the command is run**. *This is not a race:* T-62 proved LSEG serves hourly `BID`/`ASK` history for a **live** weekly, so the entry is captured from the **completed** 15:00–16:00 ET bar after it closes — the same completed bar the backtest reads. Run it any time from ~16:05 ET Monday onward, the same evening; the bar is immutable, so the booked trade is identical whenever it runs. Nothing about the decision uses post-16:00 information. *At the bar, one command:* `python -m options_surface_lab.covered_call.live enter` — captures the QQQ print and the near-the-money 09-18 call chain (bid / ask / last, timestamps) into `covered_call_live.json`, selects the strike by the rule, books `BUY 100` at the print and `SELL 1` at the mid, and writes the blotter. If the quote at the bar is invalid it books nothing, logs the skip, and says so — the rule is the rule on day one. *Friday 09-18, last bar:* `… live settle` — captures the settlement print, books `EXPIRE` or `ASSIGN` + `SELL`. | FR-21 | ☐ **Monday** |
| T-80 | `covered_call/live.py` — **the live leg, by Sunday.** `capture()` pulls `QQQ.O` and the live-RIC chain for the coming Friday (no caret suffix — **T-62 proved the shape: `QQQI182671500.U` returns hourly `BID`/`ASK`**) into the SPEC §3.1 schema, selecting the **15:00 ET closing bar** and never `max(ts)`; `enter()` / `settle()` call the **same** `select_strike` and the same blotter-row constructors the backtest will use — the constructors land here first and T-57's engine reuses them, so a live row and a backtested row come from one code path (NFR-5). State persists in `covered_call_live.json` (committed — it is data the page renders). Tests: a dry run on 09-11's expired chain produces the rows the rule says it should; an invalid quote produces a logged skip and no rows. | FR-21, NFR-5 | ✅ **2026-09-13.** `capture` / `plan_entry` / `plan_settlement` / `apply_rows` + the CLI; **47 tests, 15 of 15 injected defects caught**; RUNBOOK §7 written. The planners are **pure functions of a captured payload**, so the whole leg is tested offline (NFR-4) by faking the one session seam. Dry run against the expired 09-11 chain: entered **Tue 09-08 15:00** at S=718.41, wrote the **719** call at mid **4.80**, settled 714.87 → `EXPIRE`, shares kept — identical to what `rules.py` produces over the same tape. Two guards the mutation run forced: **a re-run is refused** (booked rows *and* an already-logged skip, I-10), and the entry session is resolved **off the tape** (DR-7) — `expiry - 4 days` would have entered on Labor Day and logged a false skip. |

## A2-M1 — The tape

| ID | Task | Maps to | Status |
|---|---|---|---|
| T-56 | `covered_call/tape.py`: calendar from the stock tape (weeks, first/last sessions, expiries — SPEC §3.2); chain per week on the **$1.00** step T-62 discovered; batched fail-soft pull for each contract's life, **trying the live RIC form and the caret form and recording which won per contract** (SPEC §3.3); `covered_call_tape.parquet` with the SPEC §3.1 schema + payload keys; `load_tape()` cache-first, `fetch_tape()` refuses to overwrite, `OSL_OFFLINE` honoured; **never touches `option_pipeline_data.pkl`**. RUNBOOK §7 written with it. | FR-13, AD-1, AD-2 | ☐ after T-62, T-55 |
| T-63 | `synthesize_tape(seed, end_date)` — explicit `end_date` (OQ-6's lesson), the properties in SPEC §3.4, at least one skip per window, one holiday week, both OTM and ITM Fridays. Fixture in `tests/covered_call/conftest.py`. | AD-7, NFR-4 | ☐ |
| T-64 | Tape tests: schema and dtypes; `mid` NaN on every invalid-quote case (SPEC §6.1); calendar derivation on a synthetic week with a Friday holiday; loader offline; fetch refuses an existing cache. | FR-13, NFR-2 | ☐ |
| T-77 | **[PO + session]** The one-time hourly pull per RUNBOOK §7, verify diagnostics, commit the parquet. Same discipline as T-7. | FR-13 | ☐ after T-56 |

## A2-M2 — The engine

| ID | Task | Maps to | Status |
|---|---|---|---|
| T-65 | `covered_call/rules.py`: `Params` (SPEC §2), `select_strike` for `nearest_otm` (P0), the calendar helpers. Tests incl. the property in I-9 and the ATM tie. | FR-14 | ✅ **2026-09-13.** `Params` frozen, defaulting to the six SD decisions; `select_strike`, `is_itm` (SD-6 strict), `trading_weeks` / `entry_bar_ts` / `closing_bar_ts`. **37 tests, 9 of 9 injected defects caught.** Driven against the real tape: it reproduces all 10 entry bars, strikes and outcomes that an independent throwaway script produced — W37 correctly enters **Tuesday 09-08** (Labor Day, DR-7) and **6 of 10 weeks assign**. `closing_bar_ts` is the only place allowed to decide which bar is "the close"; `max(ts)` is banned in the module docstring and a test injects it. |
| T-57 | `covered_call/engine.py`: `run_backtest(tape, params) -> Book` — the weekly loop (SPEC §4), fills (§6), settlement (§7), blotter + skip log (§8), ledger + Reg T (§9). **Tests before figures:** the I-1 … I-12 invariant suite written first, over the synthetic tape and then the real one; each mutation-checked. One week hand-checked against raw quotes in the test's docstring. | FR-15, FR-16, NFR-6 | ☐ after T-65 |
| T-66 | Notebook `03_covered_call.ipynb` §1–§4 co-built with T-57: one week walked end to end with the raw bars beside the blotter rows; the skip log explained; the NAV identity shown. Stored outputs (T-25's lesson). | AD-3 co-build | ☐ with T-57 |
| T-67 | `occ_symbol()` beside the RIC grammar in `option_surface_utils.py`; round-trips with `parse_option_ric`; test. | FR-15 | ✅ **2026-09-13**, pulled forward because T-80's blotter needs the column. Also added `build_option_ric(..., expired=False)` for the **live** RIC form, and a guard: a strike over **$999.99** no longer builds a RIC that parses back to a *different* contract and returns nothing — it raises. QQQ at ~$715 is well inside, but that failure mode is invisible, which is why it is refused rather than logged. |

## A2-M3 — The evidence

| ID | Task | Maps to | Status |
|---|---|---|---|
| T-58 | `mid_vs_print(tape, band)` + OLS/R² in the transform core (SPEC §10); notebook §5; a test on a synthetic tape with known noise recovers the planted slope. | FR-17 | ☐ after T-56 |

## A2-M4 — The page (waits on T-79 — the interim second output; T-51's generator follows the submission if the PO confirms)

| ID | Task | Maps to | Status |
|---|---|---|---|
| T-79 | **Second output from the current builder** — the interim for AD-11: lift `_panel` / `_readout` / the page shell out of `build_preview.py` into a small shared module both builders import; a `build_covered_call()` writes `_site/covered-call/index.html`; `pages.yml` uploads the directory; the publish guards run per page; `test_build_preview` still green. No registry, no templates — those are T-51, after 09-20. | AD-11 (interim), FR-18 | ☐ |
| T-68 | **[PO taste]** Theme additions: table rules in `PAGE_CSS`; tokens for the NAV / IM / MM lines (amber stays type, never data — DESIGN-BRIEF §3 rule 6); DESIGN-BRIEF §9 records them. | FR-18, AD-6 | ☐ |
| T-69 | `covered_call/plots.py`: NAV/IM/MM path with hover (hero height), the mid-vs-print scatter with fit and `y = x`; captions via `with_caption`; every figure declares its panel height. | FR-16, FR-17 | ☐ after T-68 |
| T-59 | `covered_call/page.py`: `build_page(tape, params) -> Page`, registered at `/covered-call/`; panels in SPEC §11 order; blotter, skip log and ledger as HTML tables; strategy + simplifications printed from `Params`; the FR-14 sentence-pins-params test; CI guards per SPEC §11; I-13; the **Live book** panel (FR-21). | FR-14, FR-18, FR-21 | ☐ after T-79 |
| T-70 | `covered_call/writeup.py` scaffold — the FR-7 mechanism: `[unwritten]` slots for the five write-up questions, red on the page, failing test, CI refusal. | FR-19 | ◐ **module landed 2026-09-14** with the five `[unwritten]` slots and the PO's **methodology block** (written by the PO in the T-80 review): the Rule/Fill/Stock/Audit/Limitation hierarchy, the observation-point paragraph and the midpoint-evidence caveat. `test_writeup.py` **re-runs `select_strike` on the two prices the paragraph quotes** so the prose cannot drift from the rule, and forbids the word NBBO anywhere in it. Still to wire: red rendering + CI refusal, which need the page (T-79/T-59). |

## A2-M5 — Write-up and ship

| ID | Task | Maps to | Status |
|---|---|---|---|
| T-60 | **[PO]** The write-up: strike choice; wait-through-expiry; fill at mid (cite the R²); why Reg T; the analysis — what happened, where theory met tape, what to change. | FR-19 | ☐ |
| T-71 | Browser drive of the built page (RUNBOOK §5 posture): 14 widths, tables scroll rather than deform, hover values on the NAV chart, zero page/console errors; incognito check of the Pages URL. | FR-18 | ☐ after T-59 |
| T-72 | Docs lockstep + PRD §20 definition of done; **[PO]** Canvas submission. | all | ☐ |

## P1 — after every P0 line above is green

| ID | Task | Maps to | Status |
|---|---|---|---|
| T-73 | One comparison variant, not both: `strike_rule = "delta"` (30Δ from the 1.1 inverter) **or** a buy-back at 50% of premium — a second `Params`, a second book, one comparison figure. The write-up gains a paragraph. | FR-20 | ☐ |
