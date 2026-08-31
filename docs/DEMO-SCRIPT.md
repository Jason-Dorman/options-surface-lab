# Checkpoint Demo Script — Class 2 (3 minutes)

The brief says: **show progress, ask questions.** The site doesn't need to be published yet.
Date: start of Class 2 (exact date = OQ-1).

Everything in quotes below is meant to be said out loud. Everything else is a stage direction.

## Before you walk in

- [ ] `algo` active, `reflex run` warm
- [ ] **Backup tab open** — `options_surface_preview.html`. Open it even if Reflex is fine.
- [ ] `notebooks/01_data_exploration.ipynb` freshly run. §10 is where you go if they want depth.
- [ ] Know these cold: **21.5%**, **$0.040**, **20% spread**, **148 calls / 148 puts**
- [ ] Decide beforehand which question you want answered most. You will not get through all of them.

---

## The three minutes

### 0:00–0:30 — Open with the finding, not the app

Don't build up to it. Lead with it.

> "The assignment says compare SETTLE to the last trade. There is no SETTLE. Nobody publishes
> a settlement price for US equity options — not the exchanges, not OPRA, not the OCC. So I
> had to derive the mark myself, and I want to check that what I did is right."

That earns the next two and a half minutes. Show the candlestick while you say it, just for
context — one sentence, then move on.

### 0:30–1:30 — The 3D surface

This is the shot. Cyan mark cloud, magenta trade diamonds, far fewer diamonds.

> "Every cyan point is a contract someone was willing to trade. Every magenta diamond is one
> that actually traded. That gap is the whole assignment."

Then **toggle the interpolated sheet off**:

> "That sheet was an assumption I was imposing. Underneath it, this is what the market
> actually gave me."

Say the two numbers:

> "Across the panel, 21.5% of listed contract-days have a mark and no trade behind them —
> 1,601 out of 7,458. Where both exist, the median gap between them is four cents, about 4.6%."

*Careful here — two different numbers, and the screen shows the other one.* **4.6%** is the
whole panel (5,123 paired observations). The metric card on screen reads **4.0%**, because it
is the selected as-of date only. Both are right. If he notices, that is a good moment:
"the card is one day, I quoted the whole panel." If you would rather not manage two figures
under pressure, say **"about four percent"** — true of both.

### 1:30–2:15 — The honest picture

Occupancy heatmaps:

> "Dark cells never had a number. I'm not filling those in."

Mark-vs-trade scatter:

> "Off the diagonal is where the mark and the print disagree."

**The spread heatmap** — this is the one worth your last twenty seconds:

> "Occupancy tells me whether a number exists. This tells me whether to believe it. Green is
> a tight market. Red is where the bid and the ask are so far apart that the midpoint is a
> number nobody would actually trade at."

If you have a spare beat, the open-interest point is a good one:

> "Open interest tells me those contracts were real and people were holding them. They just
> didn't trade that day."

### 2:15–3:00 — Ask your questions

Go to the list below. Lead with #1.

---

## How I'm calculating the mark — in plain English

You will be asked this. The answer is short and it is not "I made something up."

> "I'm not computing anything clever. LSEG publishes a mid price, and it is literally the
> midpoint of the closing bid and ask. I checked every cell where I had both sides — 6,724 of
> them — and bid plus ask over two matched their mid to the limit of floating-point
> precision, about fifteen decimal places. So when I
> say 'the mark', I mean: the best price someone would buy at, plus the best price someone
> would sell at, divided by two. No model, no fitting."

And the part that makes it honest rather than convenient:

> "If either side is missing there's no mark, and I leave it empty. There are 734 cells with
> an ask but no bid — deep out-of-the-money contracts where nobody will bid at all. Those stay
> as holes, because that's the truthful answer."

**Where it happens in the code:**

| What | Where |
|---|---|
| The choice of field, one constant | [option_surface_utils.py:79](../options_surface_lab/option_surface_utils.py#L79) — `MARK_FIELD_DEFAULT = "MID_PRICE"` |
| Requesting it from LSEG | [options_surface_app.py:281](../options_surface_lab/options_surface_app.py#L281) — asks for `TRDPRC_1, MID_PRICE, BID, ASK, OPINT_1` |
| Mapping it into the `MARK` column | [option_surface_utils.py:316](../options_surface_lab/option_surface_utils.py#L316) |

If they want a different mark, it is that one constant on line 79. Say that — it shows the
choice is deliberate and reversible, not baked in.

---

## The spread — why "does a price exist" isn't the whole question

This is the part that goes beyond the rubric. Bring it if the conversation has room; it is the
strongest thing you have for showing you understand what the data is for.

> "My first instinct was that this exercise is about finding which contracts are liquid enough
> to trade. But when I checked, that's not what the data says. The contracts that never traded
> had almost exactly the same bid-ask spread as the ones that did — 19.8% versus 20.3%. They
> weren't harder to trade. Nobody just happened to want them that day. What actually separated
> them was open interest: 157 versus 28. It's popularity, not tradability."

Then the part that matters for next week:

> "The thing that *should* worry me is that the median spread is 20% of the mark. A quarter
> wide on a $1.20 option, and 15% of marks have a spread of half the mark or more. So the mark
> exists, but it's soft — if the bid is ten cents and the ask is two dollars, the midpoint is
> $1.05 and I can't trade at $1.05. When I simulate fills next week, filling at the mid is
> optimistic by about half the spread. Do that across a backtest and I'd manufacture profits
> that were never there."

**The four questions I'd been rolling into one**, if they want the structure:

| question | measured by | contract-days |
|---|---|---|
| Does the contract exist, do people hold it? | open interest | 6,634 |
| Could I have traded it? | is there a two-sided quote | 6,724 |
| Could I have traded it *without getting hurt*? | how wide the spread is | median 20% of mark |
| Did anyone actually trade it? | last trade | 5,613 |

Those first three are close together. Only the last one — did somebody bother — separates them.

**Where it happens in the code:**

| What | Where |
|---|---|
| The two derived columns | [option_surface_utils.py:355-356](../options_surface_lab/option_surface_utils.py#L355-L356) — `spread = ASK − BID`, `spread_pct` as a % of the mark |
| The trust map | [option_surface_plot.py:394](../options_surface_lab/option_surface_plot.py#L394) — `spread_heatmap()` |

*One honest footnote if they check your arithmetic:* keeping bid and ask means 244 contract-days
that were quoted on one side only now count as "listed". That moved the denominator from 7,214
to 7,458 and the headline from 22.2% to 21.5%. A contract quoted with an ask but no bid was
still listed that day, so it belongs in the denominator and can't be in the numerator. The
number got slightly smaller, not bigger.

## Why I stopped dropping rows — in plain English

Worth volunteering, because it's the same lesson as the rest of the demo.

> "I had a bug where option quotes were vanishing. When I built the table, I was using the
> underlying stock price as part of the row's identity. Pandas throws away any row whose
> identity has a blank in it. So on a day where I didn't have a stock price, the option quote
> didn't come back empty — it disappeared completely. And it disappeared from my counts too,
> so my sparsity numbers were quietly wrong in the flattering direction."

> "Now I identify a row by date and contract only — the two things that actually make it a
> row — and attach the stock price afterwards by joining. If the stock price is unknown, the
> quote still shows up, with a blank where the spot goes."

Why it matters, if they push:

> "The README says don't drop rows with a missing trade price and then call what's left 'the'
> surface. Deleting the row outright is the same mistake one step earlier. A hole should look
> like a hole."

**Where it happens in the code:**

| What | Where |
|---|---|
| The fix | [option_surface_utils.py:320-335](../options_surface_lab/option_surface_utils.py#L320-L335) — pivot on `(date, ric)` only, re-attach descriptors by merge |
| The test that pins it | [tests/test_transforms.py:259](../tests/test_transforms.py#L259) — was an expected-failure, now passes |

Same instinct, one more place: [option_surface_utils.py:377](../options_surface_lab/option_surface_utils.py#L377).
A single-expiry day is a flat cloud, and the triangulation used to crash on it — it took the
whole preview page down. Now it just draws no sheet. Only mention this if the conversation
goes technical.

---

## Questions for the instructors

**1. The mark substitution — this is the one I actually need.**

> "SETTLE doesn't exist for these contracts. I checked seven different field names across
> every contract in my window, and they're all empty — and SETTLE isn't in the 22 fields these
> contracts do return. To prove it's not me: the same session returns SETTLE fine for a crude
> future. So I used the quoted mid instead. Your commentary prompt asks which field I'd treat
> as the mark, and nothing in the do-not list rules out bid/ask — but two of the graded items
> name SETTLE specifically. Is the substitution right?"

Say *"every expired UUUU contract in my window"*, not "equity options generally" — the wider
claim is an inference and they will catch it. Exhibit: notebook 01 §10.
Full argument: [checkpoint_audit.md](checkpoint_audit.md) §3.

If they ask whether you looked for another route — you did, and both dead-ended:
`TR.SETTLEMENTPRICE` is a futures field, and `TR.CLOSEPRICE` turns out to be the last trade
under another name (identical in 356 of 356 observations once you drop its duplicate rows).
LSEG's own published example for expired options uses bid, ask and last trade — no settle.
Notebook 01 §10a.

**1b. If he blesses the substitution, which derivation does he want?**

Ask this straight after #1 — it's the natural follow-up and you have both options ready.

> "There are two standard ways to derive a mark. The mechanical one is what I used — the
> midpoint of the bid and ask, no model. The other is theoretical: fit a pricing surface to
> the quotes and read the mark off it. LSEG ships that too, as `THEO_VALUE`, and it has
> slightly better coverage — 50% of contract-days versus 47%. I deliberately didn't use it.
> Do you agree, or would you rather I used the theoretical one?"

Your reason for not using it, if he asks — and this is the good answer:

> "My page already draws an interpolated sheet, and that sheet *is* a fitted surface. If I
> also used a fitted surface as the mark, I'd be comparing a model to a model, and the whole
> point of the picture is contrasting what the market gave me against what I assumed. Keeping
> the mark market-derived is what keeps the sheet visibly an assumption."

Switching is one constant — [option_surface_utils.py:79](../options_surface_lab/option_surface_utils.py#L79)
— plus a re-pull. So this is genuinely his call, not a rewrite.

**2. The expired-contract suffix — the README looks wrong.**

> "The README says the suffix repeats the month letter, so a June put should end `^R26`. That
> returns zero rows. Puts only come back when the suffix carries the *call* letter — `^F26`.
> Is the README wrong, or is that a venue quirk?"

One argument in `build_option_ric()`: 0 puts vs 148.

**3. The RIC digit count.**

The README's example has 10 digits where Appendix A's grammar gives 9. The 9-digit form is
what LSEG actually accepted — 296 live series built that way. Almost certainly a typo, but
worth confirming.

**4.** *(answered — ask only if it comes up)* **Did UUUU split in the window?** Checked: no.
Price continuity, an unbroken $0.50 strike grid, and option data on every open-market Friday
all agree. Worth mentioning only as evidence you did the pre-flight — README:129 asks you to
check and switch underlyings if it split, not to write split-handling code.

**5. Deployment — I deployed it and the page is blank. Which way do you want this done?**

Say it plainly, because it is a real blocker and you have the evidence:

> "I got the Pages deploy working — tests, export and publish all green. But the page renders
> blank. Reflex splits into a Python backend and a compiled frontend, and the frontend talks
> to the backend over a websocket. The exported bundle still points at
> `ws://localhost:8000/_event`, so on GitHub Pages it can't connect and the app never
> hydrates. Reflex's own docs say to deploy the frontend statically and run the backend
> separately, pointing at it with `api_url`. Which do you want us to do?"

Then give him the three, because they lead to very different work:

| | what it means | URL |
|---|---|---|
| **a** | Frontend on Pages, backend hosted elsewhere (Reflex Cloud / Railway / Render), `REFLEX_API_URL` baked in at export | stays `github.io` |
| **b** | `reflex deploy` — Reflex Cloud runs both halves | not GitHub |
| **c** | Static Plotly page, no backend, interactivity Plotly-native | stays `github.io` |

*(a) and (b) keep every Reflex widget working. (c) works today but loses the switches until
they are rebuilt as Plotly `updatemenus`.*

**The thing to actually ask:** *"The rubric says the site must render from my GitHub repo —
does a hosted backend still satisfy that, or does it need to be self-contained on Pages?"*
That is the part only he can answer, and it decides the rest.

*If he says Pages can do more than static now — he is right, and it doesn't resolve this.*
Deploy-from-Actions and rich client-side apps are both real. What Pages still won't do is
execute Python at request time, which is what Reflex state needs. Worth agreeing on that
distinction rather than arguing it. And he may have deployed Reflex this way himself and know
a trick — ask.

**6.** *(if time)* Committed sub-MB pickle in the repo — fine, or prefer something else?

**7.** *(if time)* Should an option quote survive when that day's underlying price is unknown?
I made it survive — see above — but I'd rather know your view.

---

## If something breaks

- **Reflex misbehaves** → the preview tab has every figure. Built on the real panel
  (2026-07-10, 216 quotes). Rebuild with `python build_preview.py`.
- **LSEG session dead** → doesn't matter. The app runs off the committed pickle, and
  notebook §10 falls back to captured evidence. Nothing in this demo needs a live session.
- **Projector dies** → say the thesis and the two numbers. That's the substance.

## After class — same day

- [ ] Record the answers in [PRD.md](PRD.md) §11 (OQ-1…6), update [BACKLOG.md](BACKLOG.md)
- [ ] If the mark substitution is blessed, drop the "pending sign-off" notes in FR-6 and AD-9
- [ ] If it isn't, change [option_surface_utils.py:79](../options_surface_lab/option_surface_utils.py#L79) and re-pull
