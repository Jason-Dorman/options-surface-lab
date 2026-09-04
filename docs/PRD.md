# PRD — Options Surface Lab (Assignment 1.1)

| Field | Value |
|---|---|
| Owner | Jason Dorman |
| Course | MENG FinTech · Algorithmic Trading II |
| Status | Draft v1 — 2026-08-29 |
| Checkpoint | Start of Class 2 — 3-minute live demo (site need not be published) |
| Due | Friday, Sep 04 2026, midnight — GitHub repo + rendering site, link on Canvas |
| Companion docs | [ENGINEERING-PRINCIPLES.md](ENGINEERING-PRINCIPLES.md), assignment brief in root [README.md](../README.md) |

This is a **build guide**, not a formal product doc. It is written to steer AI-assisted
development sessions: every requirement has an ID, a priority, and acceptance criteria.
Reference requirements by ID (e.g. "implement FR-6") when prompting.

---

## 1. Product vision (semester frame)

One Reflex site that grows all semester. Each homework adds a layer to the same app:

- **1.1 (this PRD):** historical expired-options data, sparsity made visible, `MID_PRICE` (the closing NBBO midpoint) vs `TRDPRC_1` (the last print) — the pairing the revised README names directly.
- **1.2 (next):** volatility surface + simulated fills on strikes that never printed.
- **Later:** unknown, but the pattern is set — each assignment becomes a page or section.

Architectural implications for *this* week:

- Multi-page-ready: `rx.App` + `add_page` per assignment; 1.1 lives at `/` for now and can
  move to its own route later without rework.
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

## 3. Current state (as of 2026-08-29)

What exists — this is instructor starter code plus a synthetic data cache:

| Asset | State |
|---|---|
| [options_surface_app.py](../options_surface_lab/options_surface_app.py) | Reflex page + `State` + cache-first LSEG loader. In the package; imports verified. |
| [option_surface_utils.py](../options_surface_lab/option_surface_utils.py) | `parse_option_ric`, `flatten_lseg_options`, `attach_underlying`, `pivot_trade_settle`, `summarize_sparsity`, `synthesize_demo_payload`, `surface_grid`. Solid; locked by the FR-3 transform suite (40 tests, T-4). |
| [option_surface_plot.py](../options_surface_lab/option_surface_plot.py) | Candlestick, 3D price surface, settle-vs-trade scatter + occupancy bars, coverage + spread heatmaps, the published page's static surface. All styling via `theme.py` (FR-8 landed 2026-09-02). |
| [theme.py](../options_surface_lab/theme.py) | Design tokens — the only file holding a colour or a font name. Direction recorded in [DESIGN-BRIEF.md](DESIGN-BRIEF.md). |
| [build_preview.py](../build_preview.py) | Standalone static HTML preview (no Reflex). Works; useful fallback and export ingredient. |
| `option_pipeline_data.synthetic.pkl` | **Orphaned** — nothing loads it, and it fails to unpickle under the installed pandas. The no-cache fallback is generated in-process by `synthesize_demo_payload()`. |
| `option_pipeline_data.trdprc-only.pkl` | The 2026-08-30 pull: 148 series, TRDPRC_1 only, calls only, no SETTLE. Kept as evidence for [checkpoint_audit.md](checkpoint_audit.md) §3; **not** a usable cache. |
| `option_pipeline_data.pkl` | The real committed LSEG cache (FR-2). **Does not exist yet** — blocked on T-6 and T-27. |
| [docs/ENGINEERING-PRINCIPLES.md](ENGINEERING-PRINCIPLES.md) | Engineering standards this project follows. |

### Known defects / gaps (drive the requirements below)

- **G-1** ✅ *Resolved 2026-08-29* — `rxconfig.py`, package layout, and entry shim in place;
  app import verified in the `algo` env. First full `reflex run` smoke test still pending.
- **G-2** ✅ *Resolved 2026-08-29* — all imports are package-style and cache paths are
  anchored to `__file__` (CWD-independent).
- **G-3** Rubric item 5a: the **percent** of settle-with-no-trade series is computed
  (`State.pct_settle_no_trade`) but never displayed — the page shows only the raw count.
- **G-4** Rubric "three sentences under the plot" — missing entirely.
- **G-5** ✅ *Resolved 2026-09-02* — FR-8 landed (T-13). Deep-navy terminal identity in
  `theme.py`, direction recorded in [DESIGN-BRIEF.md](DESIGN-BRIEF.md); no colour or font
  literal survives outside that module, enforced by `tests/test_theme.py`.
- **G-6** Not a git repository; nothing on GitHub; no deployment.
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
| Calls/Puts select, as-of date select | Plotly `updatemenus` dropdowns toggling pre-rendered trace sets, **or** pre-render a curated set of (date × C/P) figures behind client-only tabs. Curate dates (e.g. last 5 sessions) to cap page size. |
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
> [checkpoint_audit.md](checkpoint_audit.md) §3. **Reverting is one constant
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

> The old acceptance criterion said "assets loading under the `/<repo>/` base path". That is
> not merely stale but **unmeetable**: the page is one self-contained file with no relatively
> pathed assets, only an absolute Plotly CDN URL. There is no base path to get wrong.

### P1 — stretch goals (committed, build after all P0 pass)

**FR-10 — Moneyness slicing**
A toggle to switch the 3D figure's strike axis between raw K and moneyness `K / S` (spot
joined per date — `attach_underlying` already computes it), so two as-of dates become
comparable. On the static site this is another pre-rendered variant (see §5).
*Accepted when:* switching axes preserves toggles and marker identity, and axis labeling
makes clear which mode is shown.

**FR-11 — Crude IV surface from settles**
Invert Black–Scholes on SETTLE (European approximation) using a constant rate; assumptions
(rate value, no dividends, act/365, European exercise) written on the page next to the
figure. Rendered as its own figure/tab, visually labeled as derived — with the explicit
caption that this IV is still not a tradable price. Solver must fail gracefully (skip, don't
crash) on sub-intrinsic or near-zero settles.
*Accepted when:* IV figure renders from the real cache; assumptions are printed; degenerate
inputs produce gaps rather than errors or absurd IVs; unit test covers round-tripping a
known BS price back to its vol.

**FR-12 — Spot plane overlay**
In the 3D figure, a translucent vertical plane at `K = S` (as-of date's underlying close),
toggleable like the sheet, so at/in/out-of-the-money reads at a glance.
*Accepted when:* plane sits at the correct spot for the selected date, is obviously not data,
and can be hidden.

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

## 8. Milestones

| # | Milestone | Target | Contents |
|---|---|---|---|
| M1 | Runnable + real data | Before Class 2 checkpoint | FR-1, FR-2, FR-3 tests green. Demo script: show occupancy heatmaps + settle-vs-trade, name the % from FR-6 verbally, list open questions for instructors. |
| M2 | Rubric complete | ~Sep 02 | FR-4–FR-8 done; site content final. |
| M3 | Stretch built | ~Sep 03 | FR-10, FR-11, FR-12. |
| M4 | Shipped | Sep 04, before midnight | FR-9: Pages live, Canvas submitted. |

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
- **OQ-2:** Constant rate for FR-11 (pick something defensible, e.g. a current short T-bill
  yield, and write it down — the writing-down matters more than the number).
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
  accept-and-document? — PO call. Plain-English write-up for the instructor:
  [checkpoint_audit.md](checkpoint_audit.md) §1.
- **OQ-6:** `synthesize_demo_payload` anchors its window to `dt.date.today()`, so SPEC §11's
  "same seed → identical panel; tests may assert on exact derived values" holds only within a
  single day. Current tests assert structure, not exact values. Add an `end_date` parameter for
  true determinism (signature change → PO sign-off), or soften the SPEC sentence? — PO call.
  Plain-English write-up for the instructor: [checkpoint_audit.md](checkpoint_audit.md) §2.

## 12. Definition of done (submission checklist)

- [ ] All P0 acceptance criteria met (FR-1 … FR-9)
- [ ] All P1 acceptance criteria met (FR-10 … FR-12) — or consciously cut per §8
- [ ] Tests green on a clean clone with no LSEG credentials
- [ ] Pages URL renders in incognito: figures, toggles, numbers, three sentences
- [ ] Canvas submission posted with the repo + site link
- [ ] I can explain every line in the repo (guardrail #6)
