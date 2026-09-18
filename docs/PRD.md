# PRD — Options Surface Lab

**Part A (§1–§12) — Assignment 1.1, the options surface · Part B (§13–§20) — Assignment 2,
the covered-call backtest** (added 2026-09-12). Requirement IDs are one sequence across both.

| Field | Value |
|---|---|
| Owner | Jason Dorman |
| Course | MENG FinTech · Algorithmic Trading II |
| Status | Draft v1 — 2026-08-29 |
| Checkpoint | Start of Class 2 — 3-minute live demo (site need not be published) |
| Due | Friday, Sep 04 2026, midnight — GitHub repo + rendering site, link on Canvas |
| Companion docs | [ENGINEERING-PRINCIPLES.md](ENGINEERING-PRINCIPLES.md); the briefs — [archive/ASSIGNMENT-1.md](archive/ASSIGNMENT-1.md) (Part A's, archived 2026-09-12) and [ASSIGNMENT-2-COVERED-CALL.md](ASSIGNMENT-2-COVERED-CALL.md) (next) — moved here from the repo root on 2026-09-12 |

This is a **build guide**, not a formal product doc. It is written to steer AI-assisted
development sessions: every requirement has an ID, a priority, and acceptance criteria.
Reference requirements by ID (e.g. "implement FR-6") when prompting.

---

## 1. Product vision (semester frame)

One site that grows all semester — static on Pages, one page per homework. *(Was "one
Reflex site". The site has been static since AD-4; AD-10, approved 2026-09-12, retires the
Reflex page that had survived as a second renderer.)* Each homework adds a page:

- **1.1 (this PRD):** historical expired-options data, sparsity made visible, `MID_PRICE` (the closing NBBO midpoint) vs `TRDPRC_1` (the last print) — the pairing the revised README names directly.
- **1.2 (next):** volatility surface + simulated fills on strikes that never printed.
- **Covered call backtest (the brief that arrived, 2026-09-11):**
  [ASSIGNMENT-2-COVERED-CALL.md](ASSIGNMENT-2-COVERED-CALL.md) — blotter, ledger, Reg T
  account, NAV path, mid-vs-print R², write-up. Lands at `/covered-call/` on the same site
  (AD-11). Requirements in Part B (§13–§20); board in [BACKLOG-2.md](BACKLOG-2.md).
- **Later:** unknown, but the pattern is set — each assignment becomes a page or section.

Architectural implications for *this* week:

- Multi-page-ready: ~~`rx.App` + `add_page` per assignment~~ a page registry in the static
  generator (AD-11, approved 2026-09-12); 1.1 stays at `/` so the submitted URL keeps
  working, and each later assignment gets its own route.
- One shared **theme module** (palette, fonts, layout tokens) that every future page and
  figure imports. No hardcoded hex codes scattered through figures (they are today — fix).
- `*utils.py` stays generic data-transform code; nothing UI-aware leaks into it, so 1.2 can
  reuse the tidy table and parser unchanged.

## 2. The domain rules this product must never violate

These come from the assignment brief and are product guardrails, not style preferences:

1. **`SETTLE` ≠ `TRDPRC_1`.** Settle is the exchange mark (exists on most listed series,
   model-ish on illiquid names). TRDPRC_1 is one last print (missing on most strikes).
   The UI must keep them visually and verbally distinct at all times.
2. **The interpolated sheet is an assumption, not a market.** It must be toggleable,
   visually subordinate (translucent), and labeled as interpolation.
3. **Never drop missing-trade rows and present the remainder as "the" surface.**
   Occupancy heatmaps are the honest picture and stay on the page.
4. **`CLOSE` is not a synonym for `SETTLE`.** This pull requested `TRDPRC_1` and `SETTLE` only.
5. **Do not touch the LSEG derivatives-chain endpoint for expired contracts.** Synthetic RIC
   construction only (scheme in README Appendix A).
6. **AI-assisted code is my code.** I review and can explain every line; the three-sentence
   commentary (FR-7) is authored personally, not generated.

## 3. Current state (as of 2026-09-04)

What exists. This began as instructor starter code plus a synthetic cache; it is now a
package with a real committed LSEG panel, a test suite, and a live deployment.

| Asset | State |
|---|---|
| [options_surface_app.py](../options_surface_lab/options_surface_app.py) | Reflex page + `State` + cache-first LSEG loader. **Local dev and the checkpoint demo only** — the published page runs no Reflex code (AD-4). |
| [option_surface_utils.py](../options_surface_lab/option_surface_utils.py) | `parse_option_ric`, `build_option_ric`/`build_candidate_rics`, `flatten_lseg_options`, `attach_underlying`, `pivot_trade_settle`, `summarize_sparsity`, `synthesize_demo_payload`, `surface_grid`, `curated_asof_dates`, and FR-11's inversion — `bs_price`, `iv_refusal`, `implied_vol`, `attach_implied_vol` (T-17). Locked by the FR-3 transform suite (T-4) and `tests/test_iv.py`. |
| [option_surface_plot.py](../options_surface_lab/option_surface_plot.py) | Candlestick, 3D price surface (`x_mode` = strike or K/S, FR-10), settle-vs-trade scatter + occupancy bars, coverage + spread heatmaps, the derived IV smile (`iv_smile_figure`, FR-11), FR-12's spot plane at `K = S`, the published page's static surface + its per-date `asof_frames()` payload. All styling via `theme.py` (FR-8 landed 2026-09-02). |
| [theme.py](../options_surface_lab/theme.py) | Design tokens — the only file holding a colour or a font name — plus the shared figure builders (`figure_layout`, `title`, `caption`, `axis`, `scene`, `legend`, `slider`, `menu`). Direction recorded in [DESIGN-BRIEF.md](DESIGN-BRIEF.md). |
| [build_preview.py](../build_preview.py) | **The deliverable** (AD-4/T-41): builds the single self-contained `index.html` that Pages serves. CI runs it on every push. |
| `option_pipeline_data.synthetic.pkl` | **Orphaned** — nothing loads it, and it fails to unpickle under the installed pandas. The no-cache fallback is generated in-process by `synthesize_demo_payload()`. |
| `option_pipeline_data.trdprc-only.pkl` · `.trade-only-puts.pkl` | The two superseded pulls, gitignored and kept locally as evidence for the mark decision (T-32/T-34, notebook 01 §10a-b). **Not** usable caches. |
| `option_pipeline_data.pkl` | The real committed LSEG cache (FR-2). **Landed 2026-08-31 (T-7):** 296 series (148 calls + 148 puts) × 53 trading days, fields `TRDPRC_1, MID_PRICE, BID, ASK, OPINT_1`. Treated as a frozen artifact — never regenerated without PO approval. |
| [docs/ENGINEERING-PRINCIPLES.md](ENGINEERING-PRINCIPLES.md) | Engineering standards this project follows. |

### Known defects / gaps (drive the requirements below)

- **G-1** ✅ *Resolved 2026-08-29* — `rxconfig.py`, package layout, and entry shim in place;
  app import verified in the `algo` env. First full `reflex run` smoke test still pending.
- **G-2** ✅ *Resolved 2026-08-29* — all imports are package-style and cache paths are
  anchored to `__file__` (CWD-independent).
- **G-3** ✅ *Resolved 2026-09-01 (T-11)* — the "Mark, no print" readout shows the count **and**
  the percent, in both the Reflex app and the published page. It reads from the MARK slot, so
  it re-computes if the mark field ever changes.
- **G-4** ✅ *Resolved 2026-09-06 (T-12)* — the commentary panel sits under the hero row in
  both renderings, and the PO's three sentences are written
  (`options_surface_lab/commentary.py`). The guards that policed its absence stay: an
  unwritten slot would still print `[unwritten]` in red, fail `pytest`, and be refused by the
  Pages workflow.
- **G-5** ✅ *Resolved 2026-09-02* — FR-8 landed (T-13). Deep-navy terminal identity in
  `theme.py`, direction recorded in [DESIGN-BRIEF.md](DESIGN-BRIEF.md); no colour or font
  literal survives outside that module, enforced by `tests/test_theme.py`.
- **G-6** ✅ *Resolved 2026-08-31 → 2026-09-03* — `Jason-Dorman/options-surface-lab` (T-8);
  CI runs pytest in a clean no-credential container then builds and publishes the page (T-19);
  live and PO-verified in incognito at https://jason-dorman.github.io/options-surface-lab/
  (T-9). The app-key was confirmed absent from all history before the first push.
- **G-7** ✅ *Resolved 2026-08-29* — pytest 9.1.1 confirmed in the `algo` env (T-3);
  `tests/test_ric_parsing.py` (6) plus `tests/test_transforms.py` (34) run green — the full
  FR-3 chain is covered, so the FR-8 restyle now has its NFR-2 gate. One `xfail` records a
  known `pivot_trade_settle` gap awaiting a PO call (see §11 OQ-5).
- **G-8** ✅ *Resolved 2026-08-29* — renamed to `option_surface_plot.py` during the restructure.

## 4. Users

- **Me** — builds it, demos it at checkpoint, extends it all semester.
- **Instructors/graders** — open the Canvas link, expect the site to render and the rubric
  items to be findable without hunting.
- **Classmates** — see the 3-minute demo; the sparsity story must land visually in seconds.

## 5. Deployment decision (made)

**A static page built from the pickle → GitHub Pages.** *(revised 2026-09-01 — see OQ-7 / AD-4.)*
CI runs `build_preview.py`, which reads the committed pickle at **build time**, renders the
Plotly figures and embeds their data as JSON in a single self-contained `index.html`. Pages
serves that one file. The Canvas link points at the Pages URL.

> **Superseded:** this section previously read *"Reflex static export → GitHub Pages … Pages
> serves the exported frontend."* A Reflex export ships a client that opens a websocket to a
> Python backend, so on Pages it renders blank (measured 2026-08-31). The revised assignment
> README sanctions serving an HTML file directly. The Reflex app remains the local dev app.

**Hard constraint this creates:** Reflex `State` event handlers execute on a Python backend
over websocket. GitHub Pages hosts static files only — there is no backend. Therefore **every
interactive control on the published site must work client-side**, or be pre-baked:

| Starter control | Static-site strategy |
|---|---|
| SETTLE / TRDPRC_1 / sheet switches | Replace with Plotly **legend toggles** (native, client-side). |
| Calls/Puts select, as-of date select | ~~Plotly `updatemenus` dropdowns toggling pre-rendered trace sets, **or** pre-render a curated set of (date × C/P) figures behind client-only tabs. Curate dates (e.g. last 5 sessions) to cap page size.~~ **Superseded by what shipped:** the right rides the **legend**, the as-of date is a **slider** over every trading day (T-15), and the K vs K/S axis is an `updatemenus` dropdown that swaps x arrays (T-16). No curation cap — the PO chose full coverage (AD-5). |
| "Reload data" button | Meaningless without a backend — omit from the exported page. |
| Full interactivity | Preserved locally via `reflex run` for the checkpoint demo. |

Known risks of this route (see §10): Pages project sites serve under `/<repo>/`, so the export
needs the correct base path; Plotly payloads for many pre-baked dates can bloat the bundle.

## 6. Functional requirements

Priorities: **P0** = graded rubric, blocks submission. **P1** = stretch goals, committed scope,
built after every P0 passes. IDs are stable — do not renumber.

### P0 — graded rubric

**FR-1 — Runnable Reflex project** *(fixes G-1, G-2, G-8)*
Restructure into a standard Reflex layout: `rxconfig.py` at repo root, app code in an
`options_surface_lab/` package (or equivalent that `reflex run` accepts), all imports
consistent with that layout. `build_preview.py` keeps working after the move. Decide the
`*plot.py` rename here.
*Accepted when:* `reflex run` serves the page at localhost with figures rendering from the
synthetic panel; `python build_preview.py` still writes the preview HTML; no import works
only "by accident" from a particular CWD.

**FR-2 — Cache-first real data** *(fixes the missing real pull)*
Load `option_pipeline_data.pkl` when present; never re-pull if it exists. If missing:
LSEG pull when `lseg.data` + credentials are available, synthetic panel otherwise (both
paths already exist). The pull therefore only ever fires with no cache to clobber.

> **Clarified 2026-08-30 (PO-confirmed).** The acceptance criterion below — "re-running the
> app does not hit the network" — describes the *steady state after the cache exists*, not a
> ban on the first-run pull. Cache-first-then-pull is the intended behaviour. Two guards were
> added in T-26 after the pull fired invisibly during the T-5 smoke test: the page now
> announces the pull before it blocks (it looked like a failed load for ~90 s), and
> `OSL_OFFLINE=1` forces the synthetic path so CI and the page build satisfy NFR-4 by
> construction. Sequencing is unchanged: T-6's split check comes before any pull. Execute the real UUUU pull once on a machine with LSEG access and
**commit the pickle** so the deployed site and graders get real data. Before committing:
verify the underlying did not split inside the window (if it did, pick another name — the
synthetic RICs won't find adjusted contracts). Optional if the pull is slow: band strikes
per expiry instead of min/max over the whole window.
*Accepted when:* app renders real (non-synthetic) UUUU data with no LSEG session available;
the data-note banner shows the cache timestamp, not the synthetic warning; re-running the
app does not hit the network.

**FR-3 — RIC parse → tidy long table** ✅ *(locked by tests 2026-08-29)*
`parse_option_ric` handles the `{ROOT}{M}{DD}{YY}{SSSSS}.U^{M}{YY}` scheme (Appendix A month
codes, expired suffix); `flatten_lseg_options` tolerates both MultiIndex column orders and
flat columns; result is one row per contract per date with
`{underlying, expiry, cp, strike, dte, field, value}`.
*Accepted when:* pytest covers — call and put month codes round-trip; strike `01250` → 12.50;
expired-suffix and bare RIC forms both parse; invalid dates/garbage return `None`; both
(RIC, field) and (field, RIC) column orders flatten identically. All green.
*Status:* met — `tests/test_ric_parsing.py` + `tests/test_transforms.py`, 40 tests green,
covering flatten (both MultiIndex orders, flat columns, drops of unparseable RICs / non-finite
values / post-expiry rows), the nearest-prior-spot join, pivot pairing and `CLOSE` folding,
sparsity statistics, and `surface_grid`'s no-extrapolation rule.

**FR-4 — 3D price figure for one as-of date**
Puts *or* calls for a selected as-of date: X strike, Y days-to-expiry (near-dated toward the
viewer), Z option price. SETTLE markers, TRDPRC_1 markers, translucent interpolated sheet.
All three independently toggleable — via Plotly legend on the static site (see §5), via the
existing switches locally.
*Accepted when:* on the published Pages site, a stranger can turn the sheet off and see the
sparse cloud, and switch between C and P, with no backend running.

**FR-5 — SETTLE and TRDPRC_1 both plotted, unmistakably distinct**
Both series appear in the 3D figure and the settle-vs-trade comparison (scatter vs y=x, plus
the settle-only / both / print-only occupancy bars). After the FR-8 restyle they must remain
instantly distinguishable (different color *and* marker shape — do not rely on hue alone).
*Accepted when:* someone who has never seen the app can point at which marks are exchange
settles and which are actual prints, using only the on-page legend/captions.

**FR-6 — The two required numbers, printed on the page** *(fixes G-3)*
For the selected as-of date, display prominently:
(a) **percent** of listed series with a **mid** and **no** trade — the percent, not just the count;
(b) **median absolute `MID_PRICE` minus `TRDPRC_1` gap** across series that have both.

> **Settled 2026-09-01 by the revised README — no longer a substitution.** The assignment now
> names `MID_PRICE` itself: *"the closing NBBO midpoint — (bid + ask) / 2 at the exchange
> close. LSEG does not expose a true exchange settlement price for expired US equity options
> … so MID_PRICE is the closest mark-of-the-close we get."* Our independent finding and the
> brief now agree, and the required numbers are stated in terms of `MID_PRICE`, exactly what
> the code computes. The earlier "pending instructor sign-off" caveat is resolved.

> **Historical note (superseded by the line above).** Written 2026-08-30, before the README
> was revised, when this was still an unsanctioned substitution:
> The README names `SETTLE`, but there is no settlement price for US listed equity options:
> none is published by the exchanges, OPRA or the OCC, and the field is absent from the 22
> these RICs return (measured across 296 series; `SETTLE` works on `CLc1` in the same
> session). Every mark is derived. We use the *mechanical* industry derivation, the quoted
> mid, which LSEG ships as `MID_PRICE`; the *theoretical* alternative `THEO_VALUE` is
> deliberately rejected because it duplicates what our interpolated sheet already does (AD-9).
> The README's own commentary prompt asks which field to treat as the mark, and its Do-not
> list does not restrict `BID`/`ASK`/`MID_PRICE`. Evidence and the full argument:
> `notebooks/01_data_exploration.ipynb` §10a (the alternatives, and why each fails) and §10b
> (why no settle exists to find). **Reverting is one constant
> (`MARK_FIELD_DEFAULT`) if the instructor wants something else.**
*Accepted when:* both numbers are visible without interaction on page load, update with the
as-of date (locally), and match a hand-check against the pickle for one date.

**FR-7 — Three-sentence commentary under the plot** *(fixes G-4)*
Authored by me (not AI), rendered under the 3D figure, answering exactly:
where the cloud is dense vs empty; why interpolating across empty cells is dangerous on a
$0.50 strike grid for a name like UUUU; which field is the mark next week and which is
evidence someone traded.
*Accepted when:* the three sentences are on the page, specific to the actual data shown
(reference real regions/behavior, not generic filler).
**✅ Met 2026-09-06 (T-12).** An unnumbered full-width panel
("Reading the surface") sits directly beneath the hero row in both the published page and the
Reflex app, printing each of the brief's three questions above its answer so a reader who has
never seen the assignment knows what is being answered. The text lives in
`options_surface_lab/commentary.py` and nowhere else; both renderings import it. The
specificity criterion cannot be tested, but the *presence* one is, three times over: a test,
a red `[unwritten]` placeholder on the page, and a CI guard that refuses to publish it.
The sentences are the PO's own, written 2026-09-06.

*Learned in the same session:* the module and the page are two artifacts, and CI grades the
second. Writing the sentences without re-running `python build_preview.py` left the committed
page still saying `[unwritten]`, which failed the Actions run — correctly, but the assertion
introspected a 2.6 MB document into the log. The page tests now reduce to a bool before
asserting, so a stale page reports in one line and names the command that fixes it.

**FR-8 — My graphical identity** *(fixes G-5, G-7's refactor risk)*
Replace the starter cyan-magenta GitHub-dark look with a palette and typography I choose and
like. Mechanically: extract a single theme module (color tokens, font stack, figure layout
defaults) consumed by the page chrome *and* every figure — deleting the per-figure hardcoded
hex values (duplicated-code smell). Constraints: settle/trade distinction survives (FR-5);
the interpolated sheet stays visually subordinate; text meets reasonable contrast on the
chosen background.
*Accepted when:* no color/font literals remain in `*plot.py` or the page outside the theme
module; changing one token restyles everything; the result is distinct from the starter look
and I'd put my name on it.
**✅ Met 2026-09-02 (T-13).** All three acceptance clauses are executable tests rather than
judgements: `test_no_colour_literals_outside_the_theme` /
`test_no_font_literals_outside_the_theme` scan the three consuming modules, and
`test_one_token_restyles_every_figure` repoints a token and asserts the rebuild follows.
The identity itself — deep navy, ice-blue chrome, Space Grotesk + JetBrains Mono — is the
PO's, recorded in [DESIGN-BRIEF.md](DESIGN-BRIEF.md). FR-5's mark/print distinction and
AD-9's subordinate sheet are re-asserted under the new palette.

**FR-9 — Ship it** *(fixes G-6)*
`git init` → GitHub repo → `build_preview.py` static page → GitHub Pages (Actions workflow)
→ Pages URL submitted on Canvas. Repo contains the committed `option_pipeline_data.pkl`, this
docs folder, and a short repo README section (above or alongside the assignment brief) saying
how to run locally and where the live site is.
*Accepted when:* the Pages URL renders in a fresh incognito browser with every figure present
and Plotly-native interactivity working (FR-4) — the as-of slider moves and the legend toggles
series — and the Canvas submission is in.
**◐ 2026-09-03 — incognito verified by the PO.** All six figures present; the as-of slider
moves and now drives the whole page (T-42), the legend toggles calls/puts and each series.
The one clause still open is the Canvas submission.
The repo-README clause was met 2026-09-12 (T-61): the root `README.md` is now the
project's living front door — what it is, the live URL, how to run, where the documents
are — and the 1.1 brief moved, unedited, to `docs/ASSIGNMENT-1.md`.

> The old acceptance criterion said "assets loading under the `/<repo>/` base path". That is
> not merely stale but **unmeetable**: the page is one self-contained file with no relatively
> pathed assets, only an absolute Plotly CDN URL. There is no base path to get wrong.

### P1 — stretch goals (committed, build after all P0 pass)

**FR-10 — Moneyness slicing**
A toggle to switch the 3D figure's strike axis between raw K and moneyness `K / S` (spot
joined per date — `attach_underlying` already computes it), so two as-of dates become
comparable. ~~On the static site this is another pre-rendered variant (see §5).~~
*Accepted when:* switching axes preserves toggles and marker identity, and axis labeling
makes clear which mode is shown.
**✅ Met 2026-09-04 (T-16).** `price_surface_figure(..., x_mode=)` drives a select in the
Reflex app; the published page gets a Plotly dropdown inside the hero figure, because no
event handler runs there (AD-5). Both acceptance clauses are tests:
`test_switching_the_axis_preserves_every_series_and_its_identity` compares the two modes
trace for trace — names, types, colours, symbols, prices and DTE must all be identical — and
`test_the_published_hero_carries_the_axis_toggle` pins the axis relabel to the mode.
UUUU makes the case on its own: the median $14.50 strike is 0.88 in K/S on 2026-06-18 and
1.28 on 2026-07-24, and the near-the-money band walks from $16.00–17.00 to $11.00–11.50
(notebook 01 §6a).

> **The "pre-rendered variant" clause is retired, not deviated from** (PO, 2026-09-04). It
> came from the *original* brief's "I understand you will lose functionality on the published
> page"; the revised brief says use what you want, so the published page gets the real control
> rather than a baked substitute for one. Shipped: one x array per trace per mode, swapped by
> an `updatemenus` dropdown — **+205 KB raw / ~+70 KB gzipped**, against roughly doubling a
> 2.4 MB page to pre-render 308 duplicate traces. SPEC §12 and AD-5 record the mechanism.
>
> This retires the *pre-rendering strategy* only. The published page still has **no backend**
> — that follows from T-41's static-page resolution with the instructor, not from the old
> lost-functionality line — so AD-5's "every published interaction must be Plotly-native"
> stands unchanged. That is precisely why FR-10's control is a Plotly menu.

**✅ Verified in a real browser on the built page, 2026-09-04.** Reasoning about figure JSON
is not the same as clicking the control, and this project's worst defects have all been
deploy-only. Chromium was driven over `options_surface_preview.html`: opening on strike
(K = 11.00, 11.50, …, as-of 2026-07-10, spot $13.58), clicking **Moneyness (K/S)** rebases the
same points to 0.810, 0.847, … (= K / 13.58) and relabels the axis, with `z`, `y` and every
legend state untouched; dragging the as-of slider *while in K/S* moves the whole page to
2026-08-03 and re-bases against **that** date's spot ($12.15) without dropping out of
moneyness; switching back to strike keeps the slider where it is. Zero page errors, zero
console errors.

**FR-11 — Crude IV surface from the mark** — ✅ **met 2026-09-04 (T-17)**
Invert Black–Scholes on the `MARK` slot (European approximation) using a constant rate;
assumptions (rate value, no dividends, act/365, European exercise) written on the page next to
the figure. Rendered as its own figure, visually labeled as derived — with the explicit
caption that this IV is still not a tradable price. Solver must fail gracefully (skip, don't
crash) on sub-intrinsic or near-zero marks.
*Accepted when:* IV figure renders from the real cache; assumptions are printed; degenerate
inputs produce gaps rather than errors or absurd IVs; unit test covers round-tripping a
known BS price back to its vol.

*Acceptance record (2026-09-04):* panel **[3]**, half width in row 2 directly under the price
surface, on both the Reflex app and the published page — a **2D smile** of implied vol against
`K / S`, one curve per expiry. (It shipped first as a full-width 3D scatter at the foot of the
page; the PO reversed both the form and the position the same day — T-45 — because the cloud
was unreadable and sat too far from the surface it derives from.) `RISK_FREE_RATE`
= **4.00%** (OQ-2, PO). The figure's own caption carries every assumption — "DERIVED ·
European Black-Scholes on MID_PRICE · r = 4.00% · no dividends · act/365 · American exercise
ignored" — plus "Not a tradable price" and a count of how many **strikes** carry a vol for the
selected date, counted in strikes rather than contract-days so the number matches the dots a
reader can count; CI greps the built page for it. That count moves with the as-of slider along
with the curves and the legend: it shipped frozen
on the build date and was caught by T-44's adversarial review, not by the suite and not by the
session's own browser check, which had verified only that the geometry moved. **6,275 of 7,458 contract-days
invert (84.1%)** and the 1,183 that do not are absent from the figure rather than filled in
(586 no mark, 296 expiry day, 293 sub-intrinsic, 8 bracket misses) — `iv_refusal` names each
reason and `tests/test_iv.py` asserts every path returns NaN rather than raising or pinning to
the bracket. The round trip (BS-price a known σ, invert, recover it) is parametrised over
eight ITM/ATM/OTM × call/put cases. The panel follows the as-of slider like every other one
(AD-5/T-42). Co-built with `notebooks/02_iv_surface.ipynb` (T-25).

**FR-12 — Spot plane overlay** — ✅ **met 2026-09-04 (T-18)**
In the 3D figure, a translucent vertical plane at `K = S` (as-of date's underlying close),
toggleable like the sheet, so at/in/out-of-the-money reads at a glance.
*Accepted when:* plane sits at the correct spot for the selected date, is obviously not data,
and can be hidden.

*Acceptance record (2026-09-04):* a constant-x `go.Surface` — two columns at one strike, so
the sheet degenerates into an upright rectangle — spanning exactly the slice's own DTE and
price box, in `theme.SPOT_PLANE` at 18% opacity with a flat colour scale, no colorbar and
`hoverinfo="skip"`. **One plane per as-of date that can carry one** (48 of 53), carried by the same
visibility mechanism the slider already drives (AD-5), so the wall follows the date rather
than needing a control that can read the slider's state. Hidden from the legend on the
published page and from a switch in the Reflex app.

Three things the requirement did not say but the figure needs:

- **It composes with FR-10 for free.** `K = S` is the spot in dollars and *exactly 1.00* in
  moneyness, so the axis menu moves the wall onto the tick the ruler already calls the money.
  The plane's x is one number per ruler, which is all the menu's payload carries for it.
- **No spot, no plane** (AD-9). A date with no underlying close gets no wall rather than one
  standing at a neighbouring day's spot — a reader has no way to check a plane, so a wrong
  one is indistinguishable from a right one. Same rule that gives that date no K/S ruler.
- **It spans the box of the rows that are actually DRAWN.** Plotly autoranges a 3D scene
  from traces whose `visible` is exactly `True` and ignores the ones parked on the legend, so
  a wall sized over a cloud the reader cannot see silently sets the axis for the cloud they
  can. **This shipped and was caught by the T-46 review:** sized over both rights while the
  page opens with puts parked, the plane stretched the price axis on 34 of 53 dates — up to
  6.8x — flattening the call surface onto the floor of the box. It is now sized over the
  right that opens lit, and a test walks every slider step comparing the wall against the
  traces that step actually lights.
- **A date with nothing to span draws no wall.** The last five days of this panel have a
  single expiry alive, so the DTE span collapses and the surface's four corners are collinear
  — a zero-area mesh that renders nothing while its legend entry stays lit. `_plane_extents`
  returns `None` for a degenerate box, and the caption drops its plane clause on those dates
  (a caption is an assertion about what is on screen — T-44's lesson, one size smaller).

**Driven in a real Chromium on the built page** (RUNBOOK §5): the wall stands at each date's
own spot as the slider moves, lands on 1.00 under K/S and back on dollars when the ruler
flips, and hides and returns from the legend taking nothing else with it. **One defect was
visible only in the render:** the plane is the hero's *seventh* legend entry, the legend
wrapped to two rows, and the caption at `CAPTION_Y_OVER_LEGEND` printed over it — the
DESIGN-BRIEF §8 defect arriving by a route the token could not see. The clearance a caption
needs is a function of the entry count, so the row count is now derived from the figure's own
legend entries (`LEGEND_ENTRIES_PER_ROW`) instead of typed in.

**Then the T-46 adversarial review found the axis defect that browser check had missed** —
because the check compared the plane's top against the axis range *the plane itself had set*.
A circular check is not a check. The second drive walks all 53 slider steps and compares the
wall against the traces each step lights: 19 checks green, worst plane/cloud ratio 1.000,
5 dates correctly planeless, zero page and console errors.

## 7. Non-functional requirements

- **NFR-1 Engineering standards:** [ENGINEERING-PRINCIPLES.md](ENGINEERING-PRINCIPLES.md)
  applies. Module responsibilities: `*app.py` = state + page composition only; `*utils.py` =
  pure data transforms (no UI, no I/O beyond the cache loader); `*plot.py` = figure builders;
  theme module = tokens. Cyclomatic complexity target < 10 per function.
- **NFR-2 Test before refactor:** the FR-1 restructure and FR-8 restyle land only after FR-3's
  tests exist, since those transforms are what the refactors could silently break. Pure
  functions (`parse_option_ric`, `pivot_trade_settle`, `summarize_sparsity`) are the priority;
  the seeded synthetic generator doubles as a deterministic fixture.
- **NFR-3 Performance:** page interactive within a few seconds from a warm pickle; exported
  Pages bundle kept sane by curating pre-baked date variants; plotly.js may load from CDN.
- **NFR-4 No-credential operation:** everything (app, preview, tests, export) must run on a
  machine without LSEG credentials, off the committed pickle or the synthetic fallback.
- **NFR-5 Framework-free core** *(approved 2026-09-12, AD-10; the guard lands with T-50):* every page is a function of
  `(data, params)` — figure builders, page builders and HW2's backtest engine are pure
  callables, and no module in the package imports a web framework. Guarded by a test
  (T-50). This is what keeps a future live app a thin layer rather than a rewrite.

## 8. Milestones

| # | Milestone | Target | Contents |
|---|---|---|---|
| M1 | Runnable + real data | Before Class 2 checkpoint | FR-1, FR-2, FR-3 tests green. Demo script: show occupancy heatmaps + settle-vs-trade, name the % from FR-6 verbally, list open questions for instructors. |
| M2 | Rubric complete | ~Sep 02 | FR-4–FR-8 done; site content final. |
| M3 | Stretch built | ~Sep 03 | FR-10, FR-11, FR-12. |
| M4 | Shipped | Sep 04, before midnight | FR-9: Pages live, Canvas submitted. |
| M5 | Restructured for the semester | Before HW2 starts — approved 2026-09-12 (T-54) | AD-10 / AD-11: retire the Reflex page, acquisition as a CLI, the `(data, params)` rule + guard, the static builder as a multi-page generator with HW1 at `/`. Sequenced *before* HW2 by the PO (2026-09-12): multi-page is a prerequisite anyway, and refactoring a page with 219 tests is safer than refactoring under a half-built second page. |
| M6 | HW2 — covered call backtest | Due as posted in Canvas | Brief: [ASSIGNMENT-2-COVERED-CALL.md](ASSIGNMENT-2-COVERED-CALL.md). Requirements in Part B (§13–§20); board in [BACKLOG-2.md](BACKLOG-2.md). |

Task-level sequencing for these milestones lives in [BACKLOG.md](BACKLOG.md) (T-x IDs).

If M3 threatens M4, M3 loses — P0 ships first. (Stretch is committed scope, but a rendering
site with the rubric complete outranks it on the deadline.)

## 9. Out of scope (this release)

- Volatility-surface-based simulated fills (Assignment 1.2 — the FR-11 IV surface is the
  bridge, not the destination).
- Answering "what price would I actually get filled at" — deliberately unanswerable this
  week; graded after 1.2.
- LSEG derivatives-chain endpoint work (guardrail #5).
- Live/refreshing data on the deployed site; the published product is a snapshot of the cache.

## 10. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Static export breaks interactivity | Rubric's "widget switches" don't work on Pages | Client-side strategy in §5; verify on a deployed test branch *early* (during M1/M2, not Sep 04); `build_preview.py` static page is the emergency fallback artifact. |
| ~~Pages base-path breaks assets~~ | — | **Retired 2026-09-01:** the page is one self-contained file; there is no base path. The live risk is now a build that publishes a settle-less or synthetic panel — see the workflow guards. |
| LSEG pull slow / batches failing | M1 slips | Single-RIC fallback already exists; band strikes per expiry; pull is one-time — run it early, commit the pickle. |
| UUUU split inside the window | Synthetic RICs miss adjusted contracts; panel is garbage | FR-2 pre-check; switch underlyings if needed (parser/pipeline are root-agnostic). |
| Pre-baked figure bloat | Slow Pages load | Curate as-of dates; drop per-figure plotly.js duplication (one bundle/CDN). |
| Pickle in git | Repo weight / grader friction | Acceptable for one ~small cache this week; revisit (LFS or regenerate-on-clone) if later assignments grow it. |

## 11. Open questions

- **OQ-1:** Exact Class 2 date (checkpoint) — pins M1.
- **OQ-2:** ~~Constant rate for FR-11.~~ **Closed 2026-09-04 — `r = 4.00%`**, cited as a
  short T-bill yield, `RISK_FREE_RATE` in `option_surface_utils.py` and printed on the
  figure. The PRD's framing — "the writing-down matters more than the number" — was then
  *measured* rather than assumed (notebook 02 §5): 0% → 4% moves the median inverted vol by
  1.28 vol points on a ~86% panel, but the 95th percentile by 5.69 and the worst row by
  24.96 — measured over the 6,229 contract-days invertible at both rates. (State the row
  set: the first version of this entry quoted tail figures computed over a different
  subset, which is how a defensible number becomes an indefensible sentence.)
  The tail is deep-ITM contracts, where the discounted strike moves the intrinsic floor while
  vega is nearly zero. So the number is cheap for most rows and emphatically not free for
  some — which is the argument for printing it, not a reason to treat it as arbitrary.
- **OQ-3:** ~~Confirm UUUU has no split in the 12-week window (blocks FR-2 commit).~~
  **Closed 2026-08-31 — no split.** Evidence in BACKLOG T-6: price continuity (max
  overnight move +10.2%), an unbroken $0.50 strike grid across all expiries, and option
  data on every open-market Friday (the two gaps are US market holidays). Note LSEG
  returns split-*adjusted* equity prices, so the price check alone is weak — the strike
  grid and expiry coverage carry the conclusion, and neither is retroactively adjusted.
- **OQ-4:** ~~Pages mechanism: Actions workflow vs `gh-pages` branch.~~ **Actions workflow,
  shipped 2026-08-31** (`.github/workflows/pages.yml`). Superseded by a larger question:
  **OQ-7**.
- **OQ-7:** ~~Deployment model for a Reflex app on Pages.~~ **Closed 2026-09-01 — static
  page.** Pages serves one self-contained `index.html` built from the committed pickle at
  build time. See the revised AD-4. Consequence: T-15 is now on the critical path, because no
  Reflex event handler runs in production.
- **OQ-8:** ~~What stands in for SETTLE as the mark?~~ **Closed 2026-09-01 — `MID_PRICE`,
  named by the revised README.** The brief now states that LSEG exposes no exchange
  settlement price for expired US equity options and that `MID_PRICE` is the mark. No code
  change needed; `MARK_FIELD_DEFAULT` was already `MID_PRICE`.
- **OQ-5:** `pivot_trade_settle` drops rows whose `spot` is NaN (pandas `pivot_table` discards
  NaN index keys), contradicting SPEC §7.2's "one row per (date, ric)". Only reachable when the
  stock frame does not cover the option dates. Recorded as an `xfail` in
  `tests/test_transforms.py`; fix (pivot on `date`/`ric` and merge the descriptors back) or
  accept-and-document? — PO call. **Fixed 2026-08-30 by T-35**; the xfail is gone and the test
  asserts the row survives.
- **OQ-6:** `synthesize_demo_payload` anchors its window to `dt.date.today()`, so SPEC §11's
  "same seed → identical panel; tests may assert on exact derived values" holds only within a
  single day. Add an `end_date` parameter for true determinism (signature change → PO
  sign-off), or soften the SPEC sentence? — PO call.
  **No longer hypothetical: this failed CI on 2026-09-07.** The line above used to read
  "current tests assert structure, not exact values", and that was not true —
  `test_a_refused_strike_breaks_the_line_instead_of_being_bridged` asserted that the panel's
  LAST date refuses at least one strike. Which date that is depends on when the suite runs,
  and 28 of the fixture's 60 dates refuse nothing (a run whose last trading day falls early in
  a week, before an expiry lands). On such a date that assertion fails against correct code — on 2026-09-07,
  a Monday, with `assert 90 < 90`; CI had simply never landed on one of those 28 dates before.
  It was an assertion about the fixture, not about the figure. The test now
  selects a date that refuses something instead of inheriting one — which fixes that test but
  not the fixture: any future test that reads a *value* off this panel inherits the same
  calendar dependence. **Recommendation: take the `end_date` parameter.** Defaulting it to
  `dt.date.today()` keeps every existing call site working, so the sign-off is on a
  signature, not on behaviour.

## 12. Definition of done (submission checklist)

- [ ] All P0 acceptance criteria met (FR-1 … FR-9)
- [x] All P1 acceptance criteria met (FR-10 … FR-12) — FR-10 *(T-16)*, FR-11 *(T-17/T-45)*, FR-12 *(T-18)*, all 2026-09-04
- [x] Tests green on a clean clone with no LSEG credentials *(CI, every push — NFR-4)*
- [◐] Pages URL renders in incognito: figures, toggles, numbers ✅ *(PO-verified 2026-09-03)* — the three sentences landed 2026-09-06 (G-4 / T-12); **re-verify the deployed page once that build publishes**
- [ ] Canvas submission posted with the repo + site link
- [ ] I can explain every line in the repo (guardrail #6)

---

# Part B — Assignment 2: Covered call backtest

*Added 2026-09-12. Brief: [ASSIGNMENT-2-COVERED-CALL.md](ASSIGNMENT-2-COVERED-CALL.md).
Behaviour: [SPEC-COVERED-CALL.md](SPEC-COVERED-CALL.md). Board: [BACKLOG-2.md](BACKLOG-2.md).
IDs continue Part A's sequences (FR-13…, OQ-9…); new families: DR-x domain rules, SD-x
strategy decisions, S-x stated simplifications, I-x invariants.*

## 13. Vision and scope

| Field | Value |
|---|---|
| Due | **Sunday 2026-09-20, 11:59 pm EST** (OQ-9, closed 2026-09-12). **The first entry — 100 shares bought, the Friday call written — was booked live by the system on Monday 2026-09-14** (PO; FR-21): `BUY 100 QQQ @ 709.16` + `SELL 1` of the **710** call at mid **6.045** off the 15:00 ET bar, cash 4,688.50, I-1 reconciling. RUNBOOK §7 is the procedure; **settlement runs Friday 09-18**. |
| Graded | **100% the published site** — the Pages URL |
| Rubric | Algorithmic entry + strike rule, wait through expiry **20** · clean blotter + ledger implementing those rules, simulated limit fills **25** · Reg T NAV / IM / MM / available funds / cash used like an account **20** · mid vs `TRDPRC_1` scatter + R² **15** · analysis **20** |

**What we build:** one page, `/covered-call/`, that is *the book* of a covered-call strategy
— long 100 shares, short 1 weekly call — on one underlying over ~10 weeks of hourly tape:
blotter, ledger, Reg T account, NAV path with margin lines, the mid-vs-print evidence with
R², and the write-up. The baseline is the brief's own loop (Monday combo, Friday resolve);
complexity is P1 and comes after.

**What the instructor says matters, in order:** logical consistency (no crazy or impossible
trades, reasonable fills, the strategy does what it says), clarity of presentation, the
requirements. Part B therefore ranks **correctness invariants (NFR-6) above the page, and the
page above stretch** — a beautiful book with one impossible trade fails the first criterion.

**The brief's thesis** — *"the small decisions are the assignment"* — is why §15 exists:
every choice that shapes the book is named, given options and a recommendation, decided by
the PO, and printed on the page (FR-14).

**Reused from Part A, untouched:** the RIC grammar and builders (FR-3, T-31's suffix rule),
cache-first and offline-everywhere (AD-1, NFR-4), fail-soft acquisition (AD-2), the pure core
(AD-3, NFR-5), the theme (AD-6), honest holes (AD-9), the static generator (AD-11), and the
Black-Scholes inverter for the P1 delta rule (FR-11).

**Out of scope:** portfolio margin; live data on Pages; the brief's optional vol-curve
fair-price fill unless every P0 line is green early; more than one name; any position size
but 100 / 1.

## 14. Domain rules — the book must never violate these

From the brief, verbatim in spirit; each has a test (§17).

1. **DR-1 — No bid/ask at the bar → no fill. Skip the week. Never invent a print.** *"The
   worst mistake an algo trader can make."*
2. **DR-2 — Fill at mid = (BID + ASK) / 2 at the order's timestamp**, limit at mid; the
   stock leg fills at the bar's print.
3. **DR-3 — Cash moves only when the blotter says so:** buy stock, collect premium, expire
   at 0, assignment at strike. Nothing else touches cash.
4. **DR-4 — Reg T, not portfolio margin:** IM = 50% of stock LMV, MM = 25%; the covered
   call adds $0 to either. NAV = cash + stock MV + option MV, the short call negative.
5. **DR-5 — The exit is to wait:** OTM expires, ITM is assigned at the strike and you are
   flat next week. No other exit in P0.
6. **DR-6 — Same bar size for stock and options.** Hourly.
7. **DR-7 — Expiries come from the stock tape's last session per week**, never from a
   calendar that does not know the holidays.
8. **DR-8 — A blotter is a list of trades:** entries and exits only; no working orders, no
   signals. Friday OTM is `EXPIRE`; Friday ITM is `ASSIGN` on the call and a stock `SELL` at
   the strike.
9. **DR-9 — Pages runs no LSEG.** The tape is pulled once, cached, committed; the page is
   baked from the cache. A live pull on the published site is a defect.
10. **DR-10 — Guess-and-check RICs fail soft** — an empty series, never a crash.

## 15. Strategy decisions

The PO's (SD-x): options, a recommendation, and a status. Fixed-by-the-brief or stated
simplifications (S-x) follow; those need no decision, only printing.

| ID | Decision | Options | Recommendation | Status |
|---|---|---|---|---|
| **SD-1** | Underlying | AAPL (the brief's proven RICs) · SPY / QQQ (ETFs, no earnings gap) · MSFT / NVDA | *Was AAPL, for the de-risked pull.* | **✅ QQQ — PO, 2026-09-12.** RIC `QQQ.O`, root `QQQ`. Consequences: no earnings gap; QQQ lists **daily** expiries, so only the Friday contracts are requested and booked; $1 strikes near the money (T-62 confirms); 100 shares ≈ 100 × spot, so SD-3's round figure is set from Monday's print; the quarterly distribution's ex-date (late September in a normal year) sits near the live book and is named (S-6). The brief's proven RICs are AAPL, so **T-62 must prove the QQQ root and format** before the pull. |
| **SD-2** | Window | **Most recent 10 full weeks** ending on the latest Friday whose contracts resolve under the expired RIC form. **Part A's window** (Jun–Aug) for narrative symmetry. | **Most recent, ending 2026-09-11** (`2026-07-06 → 2026-09-11`), so the historical book hands off to the live book that opens 2026-09-14 (FR-21) with no gap. **T-62 (2026-09-13) answered this:** the 09-11 contracts do **not** resolve under the caret form yet, but they do resolve under the *live* form — so 09-11 stays reachable provided the pull tries both forms (SPEC §3.3). No need to fall back to 09-04. The end must be an expiry session (SPEC §3.2). If hourly history is shallower than 10 weeks, the window shrinks and the page says so. | **✅ Most recent 10 weeks — PO, 2026-09-13.** `2026-07-06 → 2026-09-11`. T-62 verified **all 10 entry bars and all 10 expiry bars exist at 15:00 ET**, and that the Labor Day week (W37) correctly opens **Tuesday 09-08** off the stock tape — DR-7 earning its place on the first window we tried. The 09-11 week needs the live RIC form (SPEC §3.3). |
| **SD-3** | Starting cash | **Fully funded:** a round figure just above 100 × the first entry print. T-62 measured QQQ at **714.88** on 2026-09-11, so 100 shares ≈ **$71,500** and the round figure is **$75,000**. **Margin-funded:** ~60% of that, so the account carries a debit and the "available funds" line is live. | **Fully funded.** Logical consistency is 45 points; a debit balance brings margin interest and a decision the brief did not ask for. The Reg T lines are still computed and plotted, the `NEG_AVAILABLE` check is implemented and simply never fires — and the write-up can say what would change at 60%. Margin-funded is a P1 variant if wanted. | **✅ $75,000, fully funded — PO, 2026-09-13.** *(Briefly $100,000 the same day; the PO moved to $75,000 once the cash drag was measured.)* Consequences: the most expensive entry in the window is **$72,982** (2026-08-17, 100 x 729.82 — corrected from $72,984 by T-57, which reads it off the committed tape), so the account is fully invested at the peak with ~**3%** idle, cash never goes negative, Reg T initial margin peaks near **$36,500** against $75,000 of equity, and `NEG_AVAILABLE` is implemented but never fires. Performance is measured on **NAV**, so keeping idle cash near zero is what stops the percentage return from being diluted by an arbitrary cash balance. |
| **SD-4** | Entry bar *(decides the clock time of Monday's live entry)* | **First hourly bar** of the week's first session (the open — wide spreads, worst mids). **Last hourly bar** (the closing hour — tightest spreads, most reliable prints, both legs quoted). | **Last bar of the first session.** The brief allows "Monday open or close"; the close is the bar where a mid is most defensible, which is the whole fill assumption. Holiday Mondays are handled by DR-7, not by this choice. | **✅ Last bar — PO, 2026-09-13.** `entry_bar = "last"`. Consequences: Monday 09-14's live entry is the **15:00–16:00 ET bar** — captured from that bar *after* it completes, not traded at it (T-62 proved LSEG serves the live contract's hourly quotes as history, so any time Monday evening books the identical trade); entry and expiry now read the *same* bar-of-session, since §7 already settles on the expiry session's last bar; **OQ-11 becomes load-bearing** — T-62 must record whether a bar's `ts` is its start or its end, because "last bar" has to resolve to the closing hour and not to one mislabelled by the convention; **OQ-13 is now live** and goes to the next class. Switching to `"first"` later is a `Params` change, not a rebuild. |
| **SD-5** | Strike rule | **Nearest OTM** (ATM if spot sits on a strike) — the brief's baseline, full credit. **Delta-target** (e.g. 30Δ via the 1.1 inverter) — fewer assignments, less premium, needs an IV per strike per entry. **Fixed % OTM.** | **Nearest OTM for P0**, exactly as the brief writes it; if the chosen strike has no valid quote the week is **skipped**, not walked to the next strike (DR-1 — walking would be a different rule). **Delta-30 as the P1 comparison** (FR-20): we already own the inverter, and "too close and you lose the upside" is the tension the brief wants discussed. | **✅ Nearest OTM — PO, 2026-09-13.** Exactly the brief's baseline. **T-62's $1.00 strike step is the consequence to write up:** on a ~$715 underlying the rule lands roughly **0.1% above spot**, i.e. effectively at the money, and on the chosen window **6 of 10 weeks finish ITM and assign**. Maximum premium, almost no upside retained — precisely the tension the brief asks you to discuss. Delta-30 stays the P1 comparison (FR-20). |
| **SD-6** | ITM test at expiry | **Strict** — ITM iff settlement print > K; equal is OTM (OCC auto-exercise is $0.01 in the money). **Inclusive** — ≥ K. | **Strict.** It matches exercise mechanics and it is the rule the code can state in one clause. | **✅ Strict — PO, 2026-09-13.** ITM iff settlement print `> K`; equality expires. No week in the chosen window settles exactly on a strike, so it changes nothing empirically here and is chosen for mechanical correctness. |

| ID | Fixed by the brief / stated simplification | Where it shows |
|---|---|---|
| S-1 | 100 shares, 1 contract, always | Page: strategy panel |
| S-2 | Exit is to wait — no buy-backs, no rolls in P0 | Page; FR-20 may add one variant |
| S-3 | Expiry = the week's last session per the stock tape (DR-7) | SPEC §3.2 |
| S-4 | No commissions or fees | Page |
| S-5 | No margin interest (moot under SD-3 fully funded; stated either way) | Page |
| S-6 | No early assignment; dividends ignored — ex-dividend and earnings dates inside the window are **named** in the write-up | Page + write-up |
| S-7 | Marks: stock at the bar's print, option at the bar's mid, carried forward when absent and flagged, intrinsic on the expiry bar | SPEC §9 |
| S-8 | Timestamps in exchange time; LSEG's bar convention as discovered by T-62 (OQ-11) | SPEC §3.1 |
| S-9 | Skipped weeks are logged on the page, not booked in the blotter (DR-8) | SPEC §8.2 |

## 16. Functional requirements

Priorities as Part A: **P0** is the rubric, **P1** after every P0 passes.

### P0

**FR-13 — The hourly tape, cached.** Stock and near-the-money weekly calls for the window at
the same bar size, `BID / ASK / TRDPRC_1` (+ OHLC / volume where a trade printed), pulled once
by a human with credentials and committed as `covered_call_tape.parquet`; the calendar
(weeks, expiries) derived from the stock bars; the chain per week on the discovered strike
step; loader cache-first and offline, `OSL_OFFLINE` honoured, fetch refuses to overwrite.
Never touches `option_pipeline_data.pkl`.
*Accepted when:* `load_tape()` returns the SPEC §3.1 schema with no credentials present;
`diagnostics` names the fields, the bar convention and the strike step; a synthetic week with
a Friday holiday yields a Thursday expiry; the pull refuses an existing cache.

**FR-14 — An algorithmic entry and strike rule, printed.** `Params` (SPEC §2) fully
determines the book; `select_strike` is a pure function; the page renders the parameters and
the rule in words, and a test pins that sentence to `params` so the page cannot describe a
rule the engine did not run.
*Accepted when:* same tape + same `Params` → byte-identical blotter (I-12); the strategy panel
prints every field of `Params` and every S-x; the sentence test exists and is mutation-checked.

**FR-15 — The engine and the book.** `run_backtest(tape, params) -> Book`: the weekly loop
(SPEC §4), fills (§6), settlement (§7), the blotter with the brief's columns and the rule id
in every note (§8), the skip log (§8.2), the per-bar ledger (§9). Pure (NFR-5).
*Accepted when:* invariants I-1 … I-10 pass on the synthetic tape **and** on the committed
one; one week is hand-checked against raw quotes in a test docstring; the blotter has at
least one `BUY`, one `SELL` call, and one of `EXPIRE` / `ASSIGN` on the real tape.
**✅ 2026-09-15 (T-57, corrected the same day by T-82's adversarial review).** `covered_call/engine.py`, 83 tests, **42 defects injected across T-57 and T-82's review, 41 caught** — the single miss is unreachable by construction and named in place. On the
committed tape: 10 weeks, 10 entries, **no skips**, 6 `ASSIGN` / 4 `EXPIRE`, $6,657.50 of
premium collected, final NAV **$76,243.50** (**+1.66%**). All **four** skip reasons are exercised on the synthetic tape, over five skipped weeks (`SKIP_NO_QUOTE` fires twice).

**FR-16 — The Reg T account, used like an account.** Per bar: NAV, LMV, option MV (negative),
IM = 50% LMV, MM = 25% LMV, available = NAV − IM, excess = NAV − MM; zero when flat; the
`NEG_AVAILABLE` flag at any entry where available < 0, printed beside the trade. Plotted:
NAV, IM, MM on one chart with mouseover values.
*Accepted when:* I-2 and I-11 pass; the chart's hover shows the three values per bar; the page
states, in words, what a negative available-funds entry would mean — the brief's *"say so"*.
**◐ 2026-09-15 (T-57):** the ledger half is in and I-2 / I-11 pass on both tapes; `available`
bottoms at **$38,886.50 at an entry bar** under SD-3 — the only bars the flag is checked on — so `NEG_AVAILABLE` never fires on this book and is instead
proven by a test that funds the account at $1,000 and watches the flag appear beside a trade
that is still booked. **The chart landed 2026-09-17 (T-69)** — `plots.account_figure`, the
hourly ledger on one axis with `hovermode="x unified"` so one hover box carries all three
values at a bar, which is the acceptance criterion read literally. Its caption carries the
**sentence**, derived rather than typed: on a clean book it quotes the available floor *at an
entry bar* and says the flag never fires; on a flagged one it says available went negative and
that the trade was booked anyway. What waits on **T-59** is putting the panel on the page.

**FR-17 — Mid vs `TRDPRC_1`, with R².** For near-the-money call bars carrying both a valid
quote and a print: the scatter, the OLS fit, `y = x`, and `n`, slope, intercept, R², median
|print − mid| in $ and %. The non-simultaneity caveat printed under it (SPEC §10).
*Accepted when:* the numbers on the page equal the transform's output on the committed tape
(I-13); a synthetic tape with planted noise recovers the planted slope within tolerance.
**◐ 2026-09-16 (T-58, corrected the same day by T-83's review):** the transform is in —
`covered_call/evidence.py` — with notebook 03 §5 and **51 tests, 33 of 33 injected defects
caught** (two further mutants are equivalent on every reachable input and are named in the
module rather than left as silent survivors). On the committed tape: **n = 16,626** of 37,073
option bars in the window — 74.7% of the 22,262 near-the-money regular-session call bars —
`print = 0.9979 × mid + 0.0104`, **R² = 0.9962**, median |print − mid| **$0.035**, median of
|print − mid| / mid **1.89%**. All **ten** of the book's fills are in the sample, pinned
contract by contract, and there the median gap is **$0.0375** (0.67%), about $3.75 a contract
against a median premium of $644.50. `ntm_band` (5%) is a `Params` field so FR-14 prints the
sample beside the R².

The planted-slope criterion is met twice over, and the second time is the one that counts: the
fixture's own line is `y = x`, so a slope **hardcoded to 1.0 passes it**. The test with teeth
plants `0.6 × mid + 1.25`, a line the generator never produced.

**The review moved the headline and the framing.** The sample had silently included the 16:00
ET post-close bar (9.3% of the points, the tightest cohort in it) and had never enforced
"calls"; the published band-sweep R² floor was wrong; and six analytical findings now sit in
SPEC §10.2 for FR-19 to use — chiefly that **$0.035 is exactly one median half-spread** (only
30.4% of prints land strictly inside the quoted bid/ask), that the fit adds nothing to `y = x`,
and that the bound worth quoting is the priced worst case: selling all ten calls at the **bid**
instead of the mid costs **$49.50**, moving the window return from 1.658% to 1.592%. The
**figure** (T-69) and the **page** (T-59) are what remain.

**FR-18 — The page at `/covered-call/`.** ◐ **The route is live (T-79, 2026-09-17):**
`build_covered_call.py` publishes `_site/covered-call/index.html`, rendering the chrome
`build_preview.py` renders (`page_shell.PageShell`) and the book's headline read off
`run_backtest` over the committed tape; the two pages link to each other; the publish guards
run per page with a marker each. **The identity the content needs is in (T-68,
2026-09-17)** — `NAV_LINE` / `MARGIN_IM` / `MARGIN_MM` behind `theme.account_line()`,
FR-17's `FIT_LINE` and the shared `IDENTITY_LINE`, and the `.osl-table*` family, recorded in
DESIGN-BRIEF §9. **What remains is the content** — panels in SPEC §11's order, blotter, skip
log and ledger as HTML tables that scroll below `TABLE_MIN_WIDTH` rather than deform
(T-69/T-59). AD-11's registry and templates are deferred past 09-20
(T-51), so the page is assembled in Python by its own builder rather than by a generator.
The per-page CI guards that have landed are the synthetic refusal and a non-empty book; the
`[unwritten]` and R² guards land with the panels they guard — a guard written before its
subject cannot fail for the right reason.
*Accepted when:* the Pages URL renders the page in incognito with every panel present and the
NAV hover working; 14-width audit clean; zero console errors.

**FR-19 — The write-up, PO-authored.** How the strike was chosen; wait-through-expiry (OTM
expire / ITM assigned → flat); fill at mid, citing FR-17's R²; why Reg T; and the analysis —
what happened, where theory met tape, what you would change. The FR-7 mechanism: a prose
module, `[unwritten]` in red, a failing test, a CI refusal.
*Accepted when:* every slot is written by the PO and specific to the book on the page (cites
its own numbers); the guard passes.

**FR-21 — The live book from Monday 2026-09-14.** *(PO, 2026-09-12: "Monday this system
needs to have everything in place to purchase the shares, write the call and fill out the
blotter — not on real capital." **Confirmed the same day:** from Monday the strategy runs on
the tape as it arrives, with simulated capital, and **the system — not a hand — books each
trade**, through the same rule and booking code the backtest uses.)* The same rule, run live: at the entry bar on 09-14 the QQQ
print and the near-the-money Friday-09-18 call quotes are captured from Workspace (live RICs
carry no caret suffix; the chain endpoint that fails for expired contracts works for live
ones), the strike is chosen by `select_strike`, and the `BUY 100` + `SELL 1` rows are booked
at the print and the mid with the raw quotes kept beside them (`covered_call_live.json`,
committed — it is data the page renders). The page carries a **Live book** panel: the live
blotter, its ledger to date, and the first resolution on 09-18 if it lands before the due
date. If the quote at the bar is invalid, the week is skipped and the page says so — the rule
is the rule on day one.
*Accepted when:* the two 09-14 rows are on the page with their raw quotes; they pass I-3 … I-6;
the panel states what is historical and what is live; the live rows were written by
`covered_call/live.py`, not typed.

### P1

**FR-20 — One comparison variant.** Either `strike_rule = "delta"` (30Δ via the Part A
inverter) or a buy-back at 50% of premium — a second `Params`, a second book, one comparison
figure and a write-up paragraph. One, not both.
*Accepted when:* both books pass the invariant suite; the figure names which is which; the
write-up says what the comparison showed.

## 17. Non-functional requirements (Part B additions)

NFR-1 … NFR-5 apply unchanged. Added:

- **NFR-6 — Logical consistency is executable.** SPEC §12's invariants I-1 … I-13 are
  tests, run over the synthetic tape and the committed tape, **written before the engine**
  and mutation-checked (inject the defect, watch the test fail — T-46). "No crazy or
  impossible trades" is the brief's first criterion; this is how it stops being a matter of
  opinion.
  **◐ 2026-09-15 (T-57): I-1 … I-12 are green over both books and mutation-checked; I-13
  waits on the page (T-59).** Three of the four defects the mutation run found first-pass
  were in the *guards*, not the engine: I-11 multiplied by the module's own `IM_RATE` and so
  passed at any rate (T-46's "a check that reads back its own effect"); the combo-skip test
  had picked its week by role rather than by state and was watching a week that was never
  flat; and `S_exp == K` — SD-6's whole decision — occurs on neither tape, so the `itm_rule`
  branch was untested until a test built the case.

## 18. Milestones and risks

| # | Milestone | Depends on | Contents |
|---|---|---|---|
| A2-M0 | Governance and decisions | — | This part; T-62 spike; SD-1…SD-6 decided; ~~AD-12 signed~~ **✅ 2026-09-14, amended (T-74)**. Remaining: FR-14 prints the decisions on the page |
| A2-M1 | The tape | A2-M0 | FR-13, synthetic tape, the one-time pull committed. **complete 2026-09-15**: `tape.py` (T-56), the committed pull (T-77 — 37,857 bars over 10 weeks, verified against T-65's independent run), the synthetic tape and its fixtures (T-63), and the tape suite (T-64) |
| A2-M2 | The engine | A2-M1 | FR-14, FR-15, FR-16, the invariant suite, notebook 03 |
| A2-M3 | The evidence | A2-M1 | FR-17. **◐ 2026-09-16:** the transform and notebook 03 §5 landed (T-58); the figure is T-69 and the panel T-59, both inside A2-M4 |
| A2-M4 | The page | ~~T-79~~ **✅ 2026-09-17** (a second builder sharing the chrome), ~~T-68~~ **✅ 2026-09-17** (the lines and the table rules, DESIGN-BRIEF §9) + A2-M2/M3 | FR-18, FR-21's live panel, theme additions. **Remaining: T-69 (figures), T-59 (the panels), T-70's red rendering** |
| A2-M5 | Write-up and ship | A2-M4 | FR-19, browser drive, incognito, Canvas |
| P1 | Comparison variant | every P0 green | FR-20 |

If P1 threatens A2-M5, P1 loses — as in Part A.

| Risk | Impact | Mitigation |
|---|---|---|
| Hourly history for **expired** contracts is shallower than 10 weeks, or missing | The window shrinks or the bar size changes | **T-62 first**, before any decision or code — one RIC, no cache written |
| Bar timestamp convention (start/end, UTC) misread | "Monday close" becomes the post-close stub; every fill is at the wrong quote | **Closed by T-62 (OQ-11): UTC, start-stamped.** The live trap was not the timezone but `max(ts)` — both tapes run past 16:00 ET with real quotes. SPEC §3.2 item 4 defines the *closing bar*; a test asserts the entry bar's ET clock time is 15:00 |
| Many entry bars have no valid quote → most weeks skipped | A thin book; the strategy "does nothing" | Report it honestly (skip log); if > 50% of weeks skip, revisit SD-4 (bar) before SD-5 (strike) |
| Holiday-week expiry RIC guessed wrong (Thursday date) | A week with no chain | DR-7 derives the date from the tape; T-62 checks one holiday week if the window has one |
| An earnings gap lands a deep ITM assignment | Looks dramatic | It is the strategy working; the write-up discusses it (S-6) |
| Tables break the 14-width audit | Layout defects on the graded page | Tables follow figures: scroll inside the panel below `FIGURE_MIN_WIDTH` (T-47) |
| **Eight days to the due date with M5 (the restructure) queued ahead of A2** | A2 ships late, or the restructure ships half-done under a deadline | **Recommendation (2026-09-12, PO to confirm): defer M5 until after 09-20.** A2 is built on the current builder — T-79 adds a second output file sharing its chrome helpers; the Jinja2 generator (T-51) and the Reflex retirement (T-48) follow the submission. The restructure-first sequencing was decided before the due date was known. |
| The 09-14 entry must be booked **by the system**, two days out | Monday's bar passes with nothing runnable | T-65 (rules) and T-80 (live capture + booking) are the only code that must exist by Monday; they are small, pure, and dry-run against 09-11's expired chain the day before. Workspace must be open **when the command is run**, which T-62 showed need not be at the bar: LSEG serves hourly `BID`/`ASK` history for a live weekly, so the entry is captured from the **completed** 15:00–16:00 ET bar any time that evening, and the booked trade is the same whenever it runs. |

## 19. Open questions

- **OQ-9:** ~~The due date, as posted in Canvas.~~ **Closed 2026-09-12 — Sunday 2026-09-20,
  11:59 pm EST**, with the first entry booked live on Monday 2026-09-14 (FR-21).
- **OQ-14:** ~~What is the Monday-14 entry?~~ **Closed 2026-09-12.** The strategy goes live on
  Monday with simulated capital and the system books it — FR-21 as written; T-65 + T-80 are
  the code that must exist by the bar.
- **OQ-10:** ~~How far back does LSEG serve **hourly** bars for expired listed options?~~
  **Closed 2026-09-13 (T-62) — ample.** `QQQ.O` hourly serves 2026-06-01 onward; an expired
  weekly call serves its whole listed life (the 04-Sep contract from 2026-07-23, 256 bars).
  A 10-week window is comfortably covered.
- **OQ-11:** ~~LSEG's hourly bar timestamp convention?~~ **Closed 2026-09-13 (T-62) — tz-naive
  UTC, stamped at the bar's START** (`O_SEC_OFST` = 0, `C_SEC_OFST` = 3599 throughout).
  **And it does not mean what "last bar" sounds like:** both tapes run past the 16:00 ET close
  with real quotes, so the last bar of a session is a post-close stub. SD-4's closing hour is
  the bar starting **15:00 ET**, 19:00 UTC under EDT. SPEC §3.1 and §3.2 item 4 fix it.
- **OQ-12:** ~~The strike step near the money on the chosen name.~~ **Closed 2026-09-13
  (T-62) — $1.00.** Every integer strike 710…721 returns data on both a live and an expired
  QQQ weekly; 712.50 and 717.50 return none.
- **OQ-15:** *(new, 2026-09-13, T-62)* **The brief's RIC `DAY` rule does not resolve.** It
  says "not zero-padded (`5`, not `05`)", but all three of its own single-digit-day AAPL
  examples fail as written and succeed zero-padded. The repo's `build_option_ric()` already
  pads, and Part A's UUUU pull proves it (the 07-Aug expiry returned 17 series as
  `UUUUH0726…`). The brief is precedence 1 and is **not edited**; this is a question for the
  instructor, and the code follows what LSEG actually resolves. → ask in class.
- **OQ-13:** Does the brief's "Monday open or close" admit the last *hourly* bar (15:00–16:00)
  as "close"? Assumed yes — the brief says the combo can be priced "any time of day".
  **Live since SD-4 chose the last bar (2026-09-13)** — ask at the next class. If the answer
  is no, `entry_bar = "first"` re-runs the backtest unchanged; the already-booked live entry
  would be the one row that cannot be moved, and the page would say so.

## 20. Definition of done — Assignment 2

- [x] ~~SD-1 … SD-6 decided by the PO~~ — **all six closed 2026-09-12/13** (T-55), and ~~AD-12 signed~~ **accepted with two amendments 2026-09-14** (T-74). Still open: **printed on the page** (FR-14)
- [x] ~~`covered_call_tape.parquet` committed; `load_tape()` offline; `option_pipeline_data.pkl` untouched~~ — **pulled 2026-09-15 (T-77):** 37,857 bars, 952 contracts, 10 weeks; reproduces T-65's independently-verified entries and the 6-of-10 assignment count. *Commit both the parquet and its `.meta.json` sidecar.*
- [◐] Invariants **I-1 … I-12 green on both tapes, mutation-checked** *(T-57, 2026-09-15; I-7 widened and eight guards added by T-82's review the same day — 42 injected, 41 caught)*; **I-13 waits on the page** (T-59)
- [◐] Blotter: every entry and exit, the brief's columns, rule ids in the notes; skip log beside it — **the engine emits both** (T-57); rendering them is T-59
- [◐] Ledger + Reg T account per bar **(T-57 — 784 hourly rows, 49 daily)**; NAV / IM / MM chart with hover and the negative-available-funds sentence wait on T-69 / T-59
- [ ] Mid vs `TRDPRC_1` scatter with n, slope, R² on the page
- [ ] Write-up authored by the PO, citing the page's own numbers
- [ ] Live book: the 09-14 entry booked by the system from real quotes and on the page (FR-21) — **booked 2026-09-14** (`covered_call_live.json`); the *on the page* half waits on T-59, and 09-18's settlement on T-78
- [ ] Pages URL renders `/covered-call/` in incognito; 14-width audit clean; zero console errors
- [ ] Docs in lockstep (PRD Part B status, BACKLOG-2, SPEC-COVERED-CALL, RUNBOOK §7 live leg + §8 tape pull)
- [ ] Canvas submission posted
- [ ] I can explain every line (guardrail #6)
