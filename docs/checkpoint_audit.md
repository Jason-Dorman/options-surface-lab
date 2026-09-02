# Checkpoint Audit — things to ask about

Three things turned up that I could not settle on my own — two while writing the FR-3
transform tests (T-4, 2026-08-29), one from the first real LSEG pull (T-5, 2026-08-30). All
three are about how the data pipeline should behave, not about styling or the write-up. The
first two don't block the checkpoint demo. **The third one does affect what the demo can
show**, so it's the one to ask first.

The four questions I already planned to ask in class (the RIC digit count, the UUUU split,
GitHub Pages as the host, committing the data pickle) are in
[DEMO-SCRIPT.md](DEMO-SCRIPT.md) under "questions for the instructors". This file is for the
two new ones.

---

## 1. An option quote disappears when we don't know that day's stock price

**Where:** `pivot_trade_settle()` in
[option_surface_utils.py](../options_surface_lab/option_surface_utils.py)

**What happens:** every option row gets stamped with the underlying stock's closing price for
that day. If there is no stock price for that day and no earlier day to fall back on, that
field is left blank — and then, when we reshape the table from one-row-per-price to
one-row-per-contract-per-day, pandas throws the whole row away. The option quote is gone. No
error, no warning, it is just missing from the counts and the charts.

**How likely is it:** low. It only happens when the stock price history doesn't cover the same
days as the options data. In the real UUUU pull both come from the same date window, so in
practice this should never fire. I found it by feeding the code a deliberately mismatched
panel in a test.

**Why I'm flagging it anyway:** one of my own rules for this project is that missing data
should show up as a hole, not quietly vanish. This is the code doing the opposite.

**What I need answered:** if we can't match a day's underlying price, should the option
observation still appear in the table with a blank stock price, or is it fine to drop it?
Put differently — is silently dropping a row ever acceptable here, or should it always
survive and show as missing?

**FIXED 2026-08-30.** `pivot_trade_settle()` now pivots on `(date, ric)` alone — the true key —
and re-attaches the descriptive columns by merge afterwards. The row survives with `spot = NaN`
instead of being deleted. `test_pivot_keeps_rows_when_spot_is_unknown` is no longer an xfail;
it passes and additionally asserts the spot really is carried as NaN. The README backs this:
*"Do not drop rows with missing `TRDPRC_1` and then claim the remaining cloud is 'the'
surface."* Silently deleting a row is the same sin, one step earlier.

**Still worth asking**, since the fix changes what the numbers count: is carrying an
observation with an unknown spot the behaviour you want, or would you rather it be excluded
explicitly and reported as a count?

---

## 2. The stand-in demo data isn't identical from one day to the next

**Where:** `synthesize_demo_payload()` in
[option_surface_utils.py](../options_surface_lab/option_surface_utils.py)

**What happens:** when the real data file isn't there, the app makes up a realistic 12-week
options panel so it still runs. It uses a fixed random seed, so the random numbers are the
same every time. But the 12 weeks are counted backwards from *today* — so running it tomorrow
produces a panel covering different dates, with different numbers.

**Why it matters:** "same seed, same data" is only true within a single day. My tests
therefore check the shape and the relationships (settles outnumber trades, trades cluster near
the money) instead of checking exact numbers, because exact numbers would break overnight.
That's a weaker test than I'd like.

**What I need answered:** for grading and reproducibility, does the fallback demo data need to
produce the exact same numbers every run — or is it enough that the real committed data file
is what actually gets graded, and the made-up data is only a "runs without credentials"
safety net?

**Either way it's cheap:** the fix is to let the function take an end date instead of always
using today, and pin that date in the tests.

---

## 3. The real pull came back with no settles and no puts — is that the finding, or a mistake?

**Where:** the acquisition function in
[options_surface_app.py](../options_surface_lab/options_surface_app.py), against the real
LSEG API on 2026-08-30. Artifact kept as `option_pipeline_data.trdprc-only.pkl`.

**What happened:** the pull asked for `TRDPRC_1` and `SETTLE`, for both calls and puts, across
every Friday in a 12-week window. What came back was 148 series — **calls only, last-trade
prices only**. Not one settle price, for any contract, on any day. Not one put, ever. The
`SETTLE` columns came back entirely empty and were dropped, which is why the app showed 0%
settle-with-no-print and a completely dark SETTLE panel.

**What I checked before asking:** I rebuilt the identifiers by hand against Appendix A. The
put month letters (M–X for Jan–Dec) are generated correctly for all twelve months, and the
expired-contract suffix matches the documented grammar. Both rights were definitely requested.
So this isn't the identifier builder being wrong — the API accepted the call identifiers and
returned nothing for the same-shaped put ones.

**Why it matters more than the other two:** the entire point of the assignment is that the
exchange settle is not the last trade. With no settles there is nothing to compare, and the
central exhibit has no data behind it. The demo currently has to run on the stand-in data.

**Update 2026-08-30 — the puts half is answered, and the answer contradicts the README.**
Puts were never missing from the API; our identifiers were wrong. The expired-contract suffix
takes the **call** month letter for *both* rights: a June put is `UUUUR122601100.U^F26` —
put letter `R` in the body, call letter `F` after the `^`. The README's rule ("repeats the
month letter", giving `^R26`) returns zero rows. Re-pulled with the corrected form: 148 calls
**and 146 puts**, 294 series. Both forms are one argument apart in `build_option_ric()`, so
the discrepancy is demonstrable live.

**Settle is still missing** — `SETTLE` comes back as a column with 0 non-null cells across all
294 series. My first probe was invalid: it requested each candidate field on its own, and an
absent field raises `LDError` rather than returning an empty frame, so all seven candidates
reported `error` — including `SETTLE` itself, which the main pull had requested without
complaint. The probe now pairs each candidate with `TRDPRC_1` so the request stays valid.

**Update 2026-08-30 (later) — settled: `SETTLE` does not exist for these contracts.**
Asking LSEG for the history with *no* field list returns the fields these RICs actually carry:

```
TRDPRC_1, OPEN_PRC, HIGH_1, LOW_1, ACVOL_UNS, BID, ASK, OPINT_1, MID_PRICE,
IMP_VOLT(A/B), DELTA, GAMMA, VEGA, RHO, THETA, THEO_VALUE, PCTCHNG, NETCHNG_1
```

No settle, under any name. `SETTLE`, `SETTLEMENTPRICE`, `SETTLE_PRC`, `OFFCL_CLOSE`,
`CF_CLOSE`, `HST_CLOSE` and `CLOSE` return **zero values across all 294 series × 53 days
(15,582 contract-days)** — each paired with `TRDPRC_1` so an absent field returns empty
rather than raising, and every RIC did return data on the paired field. The 22-field list is
identical across 14 RICs spanning 7 expiries and both rights.

Control test, so this is absence and not a broken request: `SETTLE` returns 15 values for
`CLc1` (crude front-month future) in the same session, returns no column for `UUUU.K` (the
equity), and errors with *"No successful response"* when requested alone on an option RIC.
**`SETTLE` is a futures settlement field.** Measured claim: no expired UUUU contract in this
12-week window carries a settle under any of seven names. The step from that to "US listed
equity options generally" is an inference from the instrument class plus the `CLc1` control —
other underlyings and windows were not tested.

**The exhibit still works, using a different mark.** Over 40 RICs × the window (920
contract-days): last trade `TRDPRC_1` covers 36.8%, `MID_PRICE`/`BID` 46.8%,
`ASK`/`THEO_VALUE` 50.0%, and `OPINT_1` 41.5%. **121 contract-days carry a mark with no trade
behind them** — which is the assignment's whole point, just sourced from the quoted mid
instead of a settle. `OPINT_1` independently proves those contracts were real and held.

**Also ruled out (2026-08-30): the documented alternatives.** LSEG's docs point at two routes
and neither works. `TR.SETTLEMENTPRICE` returns one value on an expired option but **15 on
`CLc1`** — it is a futures field. `TR.OptionSettlementPrice` does not exist. `TR.CLOSEPRICE`
*looks* promising (55 rows for a contract that traded 3 days) but the output is padded with
repeated rows; deduplicated on `(ric, date)` it is **identical to `TRDPRC_1` in 356 of 356
overlapping observations**. It is the last trade re-served — literally the trap README line 143
warns about. And [LSEG's own expired-options
article](https://developers.lseg.com/en/article-catalog/article/finding-expired-options-and-backtesting-a-short-iron-condor-stra)
backtests using `BID`, `ASK` and `TRDPRC_1`, with no settle field anywhere.

**And the reason it is missing: it does not exist.** There is no official closing or
settlement price for US listed equity options — none is published by the options exchanges, by
OPRA, or by the OCC. So this was never a data-access problem and there is no better endpoint to
find. Every end-of-day option mark is *derived*, by two documented industry methods:
**mechanical** (closing bid/ask midpoint or last print — LSEG ships this as `MID_PRICE`) and
**theoretical** (snapshot quotes near the close, fit a pricing surface, read marks off it —
LSEG ships this as `THEO_VALUE`). The OCC's "settlement price" is a different thing: a VWAP of
the *underlying* over the last 30 minutes at expiration, used to decide exercise, not a daily
mark per series.

**This makes `MID_PRICE` the right pick for AD-9.** The theoretical method is exactly what our
interpolated sheet already does — using `THEO_VALUE` as the mark *and* drawing that sheet would
be a model on a model. `MID_PRICE` keeps the mark market-derived so the sheet stays visibly the
assumption, which is the page's whole argument.

> **OUTCOME — Class 2 checkpoint, 2026-09-01.** The instructors accepted that `SETTLE` is not
> available at this endpoint for expired US listed equity options. It took some pushing; what
> carried it was the control (SETTLE returning 15 of 15 rows for `CLc1` in the same session)
> plus the 22-field list, rather than the zero-counts on their own. **What replaces it is
> still open** — see PRD OQ-8 / BACKLOG T-42. The app runs on `MID_PRICE` in the meantime and
> the swap is one constant.

**What I need answered:**
1. `SETTLE` isn't available for expired US equity options — was that the intended discovery,
   or is there an access path I haven't found? If it's the discovery, which mark should stand
   in for the settle: the quoted mid (`MID_PRICE`), or the model value (`THEO_VALUE`)? I lean
   toward `MID_PRICE` because it's market-derived rather than a model, but it's your call how
   literally to read "SETTLE vs TRDPRC_1".
2. Is the README's expired-contract suffix rule wrong, or is `^F26`-for-puts a venue quirk we
   got lucky with? Worth confirming before I rely on it for the whole panel.

**Either way it's cheap** — once I know the field name it's a one-line change. The corrected
probe is in notebook 01 §9 and is *read-only*: it writes nothing and does not spend a pull, so
re-running it costs nothing but a Workspace session.

### Does the README forbid deriving a mark? No — it asks me to choose one

I checked the assignment text before substituting anything.

**Nothing in the "Do not" list touches it.** The four prohibitions are: don't treat the
interpolated sheet as bid or ask; don't drop rows with missing `TRDPRC_1` and call the rest
"the" surface; don't use `CLOSE` and `SETTLE` as synonyms *without checking the field list*;
don't chase the derivatives-chain endpoint. Using `BID`/`ASK`/`MID_PRICE` is not restricted
anywhere. The third one is an instruction to do exactly what I did — and checking the field
list is how I caught `TR.CLOSEPRICE` being `TRDPRC_1` under another name.

**The required commentary explicitly asks which field is the mark.** The third of the three
sentences I have to write is: *"Which field will you treat as the mark next week, and which
field will you treat as evidence that someone traded?"* That frames the mark as a **choice of
field**. `MID_PRICE` is an answer to a question the assignment poses.

**And the README already hedges on it.** Describing `SETTLE`: *"On a name that barely trades it
is still a model-ish number."* That concedes the mark is derived — which the OCC/OPRA finding
says is unavoidably true for these instruments.

**The tension I still need resolved.** Two graded items name the field literally — "plots
**both** `SETTLE` and `TRDPRC_1`" and the two numbers ("a settle and **no** trade", "median
`|SETTLE − TRDPRC_1|`"). Those can't be satisfied as written. And the premise underneath them —
*"`SETTLE` … Exists on far more series than trades"* — is **true of a quoted mark**
(`MID_PRICE` covers 6,724 contract-days vs `TRDPRC_1`'s 5,613) and false only of a field with
that name. So the spirit, the numbers and the exhibit all survive; only the literal field name
doesn't. That is a substitution to bless, not a gap to excuse.

### What I built while waiting for the answer

I did not leave the figure empty. The app now runs on `MID_PRICE` as the mark, re-pulled with
`TRDPRC_1, MID_PRICE, BID, ASK, OPINT_1` across 296 series (148 calls, 148 puts):

| | |
|---|---|
| listed series with a mark and **no** trade | **1,601 of 7,458 (21.5%)** |
| median absolute mark-minus-trade gap, where both exist | **$0.040 (4.6% of the mark)**, 5,123 observations |
| default as-of (2026-07-10) | 216 quotes · 49 mark-no-print (22.7%) · median gap $0.040 |
| median bid-ask spread, where a mark exists | **$0.24 — 20% of the mark**; 15% of marks have a spread of half the mark or more |

The mark is not a model: LSEG's `MID_PRICE` is exactly the midpoint of the closing bid
and ask — checked on all 6,724 cells where both sides exist, `(bid + ask) / 2` matched to
the last decimal every time, max difference 0.0. Where a side is missing there is no mark
and I leave the hole: 734 cells have an ask but no bid, deep out-of-the-money contracts
nobody will bid on. Field choice is one constant,
[option_surface_utils.py:79](../options_surface_lab/option_surface_utils.py#L79).

Those are the assignment's two numbers, on real data, with the word "settle" replaced by
"mark". If you tell me the substitution is wrong, the field name is one constant.

---

## After I get answers

Record them in [PRD.md](PRD.md) §11 (OQ-5, OQ-6) and update the affected tasks in
[BACKLOG.md](BACKLOG.md) the same day, per the lockstep rule.
