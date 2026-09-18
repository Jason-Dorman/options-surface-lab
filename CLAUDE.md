# CLAUDE.md

Options Surface Lab — Duke MENG FinTech, Algorithmic Trading II, Assignment 1.1. A Reflex
app visualizing expired-options sparsity (SETTLE vs TRDPRC_1) that grows into a
semester-long site. Python 3.12 on Windows; the PO's terminal is **Git Bash** — use POSIX
syntax in any commands written for the PO to run (forward slashes, `$VAR`, `&&`), not
PowerShell.

## Governing documents — read before building

These documents ARE the build. Consult the relevant sections before any non-trivial change
and cite their IDs (FR-x, G-x, AD-x, NFR-x) when explaining decisions.

| Precedence | Document | Authority over |
|---|---|---|
| 1 | [docs/ASSIGNMENT-2-COVERED-CALL.md](docs/ASSIGNMENT-2-COVERED-CALL.md) · *(graded, archived:* [docs/archive/ASSIGNMENT-1.md](docs/archive/ASSIGNMENT-1.md)*)* | The instructor's briefs — the covered-call backtest is the live one (**due Sun 2026-09-20 23:59 EST; first entry booked live Mon 2026-09-14**); 1.1's is kept for the record. Instructor-owned — never edit their assignment content. **Where any note below says "the README" or "the revised README", it means the 1.1 brief**, which lived at the repo root until 2026-09-12. |
| 2 | [docs/PRD.md](docs/PRD.md) | Requirements — Part A (FR-1…FR-12, G-1…G-8) for 1.1; **Part B (§13–§20)** for Assignment 2: domain rules DR-x, the PO's strategy decisions SD-x with recommendations, FR-13…FR-20, NFR-6, its own milestones, OQ-9…OQ-13, definition of done |
| 3 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, module boundaries, decisions (AD-1…AD-9), the "where does my change go" table (§7) |
| 3 | [docs/SYSTEM-SPEC.md](docs/SYSTEM-SPEC.md) · [docs/SPEC-COVERED-CALL.md](docs/SPEC-COVERED-CALL.md) | Schemas, algorithms, edge-case behavior, runtime modes (1.1) · the book: tape schema, the weekly loop, fills, settlement, Reg T, the invariant suite I-1…I-13 (Assignment 2) |
| 4 | [docs/ENGINEERING-PRINCIPLES.md](docs/ENGINEERING-PRINCIPLES.md) | Code quality: SOLID, cohesion/coupling, complexity < 10, tests before refactoring |
| 4 | [docs/DESIGN-BRIEF.md](docs/DESIGN-BRIEF.md) | The graphical identity (FR-8): palette, typography, the rules the restyle may not break. PO-directed — read it before changing any value in `theme.py`. |
| 5 | [docs/BACKLOG.md](docs/BACKLOG.md) · [docs/BACKLOG-2.md](docs/BACKLOG-2.md) · [docs/RUNBOOK.md](docs/RUNBOOK.md) | Operational: the task boards — 1.1 + the semester restructure · Assignment 2 (one T-x sequence across both, work top-down) · procedures (env, LSEG pull, run, deploy) |
| — | [README.md](README.md) | The front door: what the project is, the live URL, what is on the site, how to run. A **living summary** of the documents above, never their authority — keep it current under the lockstep rule. |

*`DEMO-SCRIPT.md` and `checkpoint_audit.md` were deleted 2026-09-06 (PO): both were written
for the Class-2 checkpoint, which has passed. The evidence they carried survives where it was
gathered — the no-settle argument in `notebooks/01_data_exploration.ipynb` §10a/§10b, the
pivot/spot fix in T-35 and its test, the synthetic-panel determinism question in PRD OQ-6.*

If any two of these — or a document and the code — materially contradict, **stop and ask the
PO**. Do not silently pick a winner. Trivial mechanical errors (typos, dead links) may be
fixed directly and mentioned.

## The Product Owner

Jason is the PO. Treat every session as working for the PO:

- **Ask, don't assume.** When requirements are ambiguous, contradictory, or missing
  information, ask targeted questions — with concrete options and a recommendation when
  possible — before building. Batch questions when several arise. Guessing on scope wastes
  the deadline.
- **Always needs PO sign-off:** changing a load-bearing interface (ARCHITECTURE §5),
  deviating from or descoping any FR or AD, deleting/regenerating `option_pipeline_data.pkl`,
  anything that moves the Sep 04 submission risk.
- **Taste belongs to the PO:** FR-8's graphical identity is Jason's call — propose options,
  don't impose one.
- **PO-authored content:** the three-sentence commentary (FR-7) must be written by Jason
  personally. Scaffold the placement, never generate the sentences.
- Report honestly: failing tests, skipped steps, and unverified work get stated plainly.

## Docs stay in lockstep with the code — always

The documents must reflect the **true state of the code** at all times. This is a hard rule,
not a cleanup task for later:

- **Same session, same commit.** Any change that makes a doc stale includes the doc update.
  A task is not done until code, tests, and docs agree.
- **Status lives in the PRD and the backlog.** [docs/PRD.md](docs/PRD.md) §3/§12 track
  requirement-level status; [docs/BACKLOG.md](docs/BACKLOG.md) is the task-level board —
  update both as work lands. Where any doc still says "target" or "pending" for something
  that has shipped, convert it to present tense in the same session.
- **Direction of change matters.** Code drifting from docs by accident → fix the code.
  A deliberate change of design → get PO approval, then update the doc (including the
  relevant AD's consequences) *and* the code together.
- **Found drift you didn't cause?** Flag it to the PO and reconcile before building on top
  of it.

## Environment & commands

Python is the conda env **`algo`** (Python 3.12, reflex 0.9.8 + sci-stack installed).
Conda `base` is Python 3.8 — the wrong one. In Git Bash: `conda activate algo`, or call
`/c/Users/rjd61/anaconda3/envs/algo/python` directly. pytest 9.1.1 is installed in `algo`
(verified 2026-08-29); the bare `pytest` command works once the env is activated.

```bash
python build_preview.py       # 1.1's page — the static index.html Pages serves at /
python build_covered_call.py  # A2's page — Pages serves it at /covered-call/
pytest                        # 653 tests in tests/ — all green, no xfail
reflex run                    # local dev server (FR-1); not what gets published

# Both take `--site DIR` (CI passes `--site _site`): the page lands at DIR/<route> with its
# cross-page links spelled as routes instead of filenames. Same render either way.
```

`reflex export` is **not** part of the build any more — see AD-4. The published site is one
self-contained page per route, written by `build_preview.py` and `build_covered_call.py` from
the committed pickle and the committed tape at build time by `.github/workflows/pages.yml`.
Both render `options_surface_lab/page_shell.py`'s chrome (T-79).

Current state (2026-09-01): FR-1 package layout landed (`options_surface_lab/` package,
`rxconfig.py`, entry shim, `__file__`-anchored cache paths — imports verified, preview builds
end-to-end). `option_pipeline_data.synthetic.pkl` is **dead weight** — no code reads it and it no longer
unpickles under the installed pandas (`StringDtype` state error); the fallback panel is
generated in-process by `synthesize_demo_payload()`. `option_pipeline_data.pkl`
holds the working panel: **296 series (148 calls + 148 puts)** with
`TRDPRC_1, MID_PRICE, BID, ASK, OPINT_1`. **There is no SETTLE for US listed equity options** —
none is published by the exchanges, OPRA or the OCC — so the mark is derived: `MARK_FIELD_DEFAULT`
= `MID_PRICE` fills a slot the wide table calls `MARK` — named by the revised README (PRD FR-6).
Headline: **1,601 of 7,458 listed contract-days (21.5%) carry a mark with no trade**, median
gap $0.040. Median bid-ask spread is 20% of the mark, so the mark itself is soft — `spread`
and `spread_pct` are on the wide table and drive `spread_heatmap()`.
Puts came from fixing the RIC suffix — it takes the *call* month letter for both rights
(`UUUUR122601100.U^F26`), contradicting the README (T-31). Superseded pulls kept as evidence:
`.trdprc-only.pkl` (first, calls only) and `.trade-only-puts.pkl` (second, no mark). FR-3's transform suite is in
(T-3/T-4): `tests/test_ric_parsing.py` + `tests/test_transforms.py`, plus `test_ric_building.py`
`test_acquisition.py` and `test_app_figures.py` — 83 tests green, no xfail, so the
NFR-2 gate for the FR-8 restyle is satisfied. CI and Pages are live: `Jason-Dorman/options-surface-lab`, deployed at
https://jason-dorman.github.io/options-surface-lab/ — pytest runs in a clean container with no
credentials (NFR-4 proven), then the page is built and published.

T-15 landed 2026-09-01: the published page's 3D figure carries an as-of **slider** over all
53 trading days plus **legend** toggles for calls/puts and each series (`static_surface_figure`),
so FR-4/FR-5 are met without a backend.

T-42 landed 2026-09-03: that slider now drives the **whole page**. A Plotly slider can only
mutate its own figure, so the supporting panels used to stay on their build-time date and the
page showed two as-of dates at once. `asof_frames()` embeds per-date arrays (+34 KB gzipped)
and one inline listener restyles the scatter, the spread and both occupancy grids and rewrites
the readout strip on `plotly_sliderchange`. This is the page's **only custom JavaScript**; it
fails safe to the old behaviour if anything is missing. The payload is built by running the
real figure builders per date, so it cannot drift — and `settle_vs_trade_figure`'s trace order
(`Calls, Puts, y = x, bars`, empty traces included) is now a **contract** the listener depends
on. See AD-5's amendment.

T-13 landed 2026-09-02 (FR-8, closing G-5). The PO's direction: a **deep-navy terminal** —
**amber type** (`ACCENT` = `#FFB000`, headings/metric values/panel numbers/slider), warm
off-white body, Space Grotesk / Inter / JetBrains Mono, and a **numbered-panel grid layout** on 10
columns (command bar → readout strip → hero 3D surface at 6 cols with the underlying
beside it at 4 → the remaining four figures 5+5). The underlying sits next to the
surface because spot is what makes "near the money" mean anything and the dense part
of the cloud is that band; hero and sidecar share `HERO_FIGURE_HEIGHT` so the row ends
level. "Bloomberg" here means the
*arrangement*, not the palette. README-locked cyan mark / magenta print; puts take the hues
furthest from their own call — **violet** for the mark, **green** for the print — and every
marker is filled. The glyph encodes the *role* (circle = mark, diamond = print) for both
rights, so hue alone separates calls from puts. (The first attempt derived puts as near-shades of their calls with
open symbols; both made the puts unreadable, and the scatter's puts looked missing entirely.)
Amber is type and never encodes data. It all lives in `options_surface_lab/theme.py` and is documented in
[docs/DESIGN-BRIEF.md](docs/DESIGN-BRIEF.md) — read that before changing any value.

All colour/font literals are gone from `option_surface_plot.py`, `options_surface_app.py` and
`build_preview.py`; `tests/test_theme.py` greps those three modules, repoints a token to prove
the indirection is real, re-asserts FR-5's mark/print distinction, keeps amber out of the data
channel, and pins WCAG AA on every rendered pairing. `as_panel_figure()` strips a tiled
figure's title (its panel header carries it) — the hero keeps its own, because the as-of
slider rewrites it. **Every figure must declare exactly the height its panel reserves**
(`HERO_FIGURE_HEIGHT` / `PANEL_FIGURE_HEIGHT`): Plotly draws to `layout.height` regardless of
the box, so a taller figure paints over the panel below — the dev app did precisely that
until 2026-09-02. `tests/test_app_figures.py` guards it at the source level. Side effect: the published page now also reaches Google Fonts, so the
self-containment guard in `tests/test_build_preview.py` allows that host pair alongside the
Plotly CDN (DESIGN-BRIEF §7).

**Deploy-only failure mode, learned the hard way (2026-09-02):** the Reflex app styles panels
with inline `grid-column`, the published page uses `.osl-w{n}` CSS classes — so a layout bug
can look perfect under `reflex run` and be broken on Pages. CSS fails open, so a missing class
is silent. The width classes are generated from `GRID_COLUMNS` and two tests guard it, but
**check the built `options_surface_preview.html`, not just the dev app, before pushing.**

**FR-9 is met bar the Canvas post:** the PO verified the deployed page in a fresh incognito
window on 2026-09-03 — six figures, slider driving the whole page, legend toggling series.

T-16 landed 2026-09-04 (FR-10, the first P1 stretch). The hero's X axis switches between raw
strike and **moneyness `K / S`** — a select in the Reflex app, a Plotly **dropdown** inside the
figure on the published page. It composes with the as-of slider where the date/right pair
could not: the buttons write only `x` and the scene's X title, the steps write only `visible`.
The toggle is a change of **ruler, never of data** — same traces, same colours, same symbols,
same prices, and the interpolated sheet is *rescaled* rather than re-interpolated (one date
has one spot, so K/S is an exact affine map). A date with no underlying close gets no K/S
ruler at all rather than strikes mislabelled as ratios. SPEC §12's **"pre-rendered trace
pair" sketch is retired** (PO, 2026-09-04): it dated from the original brief's "you will lose
functionality on the published page", which the revised brief lifted — so the page gets the
real control, one x array per trace per mode, +205 KB raw / ~+70 KB gz rather than doubling a
2.4 MB page. **This retires the pre-rendering strategy only** — the published page still has
no backend (that comes from T-41, not from the old line), so AD-5's Plotly-native rule stands.
**Driven in a real Chromium on the built page**, not just asserted against the figure JSON:
the toggle rebases the points and relabels the axis, the slider still drives the whole page
while in K/S and rebases against the new date's spot, and switching back keeps the slider
position. Zero page/console errors. That check is a throwaway venv, not part of the suite —
`pytest` still cannot see the deployed page. `theme.MENU_ACTIVE_BG` is a new kind
of token: a colour plotly.js hardcodes and we cannot override, recorded so the contrast test
can measure a ground we really do render type against.

T-17 + T-25 landed 2026-09-04 (FR-11, the second P1 stretch). Black-Scholes inverted on the
mark, as **panel [7]** — a full-width 3D cloud of implied vol over (strike or K/S, DTE) —
plus `notebooks/02_iv_surface.ipynb`. The PO closed **OQ-2 at `r = 4.00%`** and chose the
scatter form. Three things worth carrying forward:

- **The refusals are the feature, not the residue.** `iv_refusal` names why a row cannot be
  inverted and `implied_vol` returns NaN for all of them, so 6,275 of 7,458 contract-days
  invert (84.1%) and the other 1,183 are *absent* from the figure rather than filled in —
  586 no mark, 296 expiry day, 293 sub-intrinsic, 8 bracket misses. A vol pinned to the
  bracket would have been the easy defect here (AD-9).
- **The rate is not as free as the PRD assumed.** OQ-2's framing was "the writing-down
  matters more than the number"; measured over the 6,229 contract-days invertible at both
  rates, 0% → 4% moves the median vol by 1.28 points on a ~86% panel but the 95th percentile
  by 5.69 and the worst row by 24.96 — deep ITM, where the discounted strike moves the
  intrinsic floor while vega is ~0. Always quote the row set with the number: the first
  landing mixed figures from two different subsets across the docs and the code comment.
  Notebook 02 §5.
- **FR-11's figure is a 2D smile at panel [3], not a 3D cloud at [7]** (PO, 2026-09-04,
  T-45). The 3D scatter was unreadable — "a bunch of scattered points" — and the 2D form
  makes the term structure obvious: each expiry's smile span collapses 81.8 → 13.4 vol points
  from the 7-day to the 42-day expiry. Layout is now 6+4 / 5+5 / 10 / 5+5, with spread full
  width so the occupancy grids stay paired. Three rules the smile added: the expiry trace
  ladder is fixed **panel-wide** (a per-date ladder breaks restyle-by-index *and* re-colours
  curves), a refused strike is `None` with `connectgaps=False` (a line is the one chart that
  can bridge a hole and invent a vol), and the caption counts **strikes** so its number
  matches the dots on screen.
- **On the published page, a control reaching another panel goes through the listener — and
  the listener must be that property's SOLE writer** (T-43). The hero's K/S chip now drives
  the smile too. T-16's "two controls must write disjoint properties" is about controls acting
  on one figure *directly*; here neither does, so both can write the smile's `x` provided the
  listener holds the `(date, mode)` pair and the payload carries a variant per pair. Both
  panels open on Strike (K), matching the hero's menu, so the page loads in one unit.
- **A grep-based CI guard is orphaned by a copy edit.** Shortening that caption left the
  publish guard looking for "DERIVED, NOT OBSERVED" — it would have failed the deploy. The
  guard's phrases are now pinned to the page by a test, and none may contain "/" or "·":
  Plotly's JSON encoder ships a slash as `/` (the same escape that bit FR-10's "K / S"),
  so a guard spanning one silently never matches what it guards.
- **A browser check that only looks at geometry is not a browser check.** T-44's adversarial
  review found two more defects in the shipped page *after* this session had driven it in
  Chromium and passed 17 assertions: the IV caption still counted the build date's inversions
  on all 52 other slider steps (including the one date where the panel is empty, where it
  described a figure showing nothing), and `customdata` was never restyled, so every hover
  named a build-date contract. Both are T-42's defect class living in the parts of a figure
  that are not its `x/y/z` — **when a panel follows the slider, audit every channel that
  states something about the date: geometry, hover identity, and any annotation carrying a
  number.** It also found `spread_heatmap`'s caption clipped in the shipped page and the new
  caption-fit test certifying it (it modelled the anchor but not the text box).
- **Two defects were visible only in the built page, again.** `as_panel_figure` replaced the
  figure's margin with the 30px tile default and silently clipped FR-11's assumptions caption
  off the canvas — an annotation above the paper does not error, it just stops drawing — and
  the hero's near-cubic scene left the cloud adrift in a 2.6:1 box. Both fixed
  (`WIDE_FIGURE_MARGIN`, `SCENE_ASPECT_WIDE`, `SCENE_CAMERA_WIDE`), and the caption one now
  has a test that does the arithmetic for **every** panelised figure. Driven in a real
  Chromium: panel [7] follows the as-of slider, keeps its `[Calls, Puts]` trace identity, and
  spans all ten columns. Zero page/console errors.

T-18 landed 2026-09-04 (FR-12, the last P1 — **M3 is complete**), corrected the same day by
T-46's adversarial review. A translucent wall at `K = S` in the hero: a constant-x
`go.Surface`, two columns at one strike, spanning the DTE and price box of **the rows that are
actually drawn**. It is **one plane per as-of date**, lit by the slider's existing visibility
array — the mechanism was already there, so FR-12 needed no new control on the published
page; the legend hides it there and a `show_spot_plane` switch does in the app.
Four things worth carrying:

- **It composes with FR-10 for nothing.** `K = S` is the spot in dollars and *exactly 1.00* in
  moneyness, so the axis menu carries one number per ruler for the plane — and the wall then
  lands on the tick the K/S axis already calls the money. **No spot, no plane** (AD-9), the
  same rule that gives such a date no K/S ruler at all.
- **A new kind of token: `SPOT_PLANE`.** The plane is neither data nor chrome but a *ruler*,
  so it wears neither a series hue (a reader would hunt for its points) nor the amber (it
  would read as chrome bolted onto the chart), and it is fainter than the sheet because it
  stands side-on *through* the cloud rather than lying over it. DESIGN-BRIEF §3, rule 6.
- **The render caught what 25 browser assertions did not.** The plane is the hero's seventh
  legend entry; the legend wrapped to two rows and the caption printed over its panel —
  DESIGN-BRIEF §8's 2026-09-02 defect by a route the token could not see. A caption's
  clearance depends on the legend's **entry count**, so the row count is now derived from the
  figure itself (`LEGEND_ENTRIES_PER_ROW`). **Measure the picture, not only the numbers.**
- **A CHECK THAT READS BACK ITS OWN EFFECT IS NOT A CHECK** (T-46, the review's headline).
  The plane shipped sized over *both* rights while the published page opens with puts parked
  on the legend — and plotly's 3D bounds ignore a parked trace, so the wall alone stretched
  the price axis on **34 of 53 dates, up to 6.8x**, flattening the call cloud. Both the test
  and the browser drive certified it: the test compared the plane against the same slice it
  fed the figure, and the drive compared the plane's top against the axis range *the plane
  had just set*. **Compare a thing against something it did not produce** — here, the traces
  the step actually lights. `OPENING_RIGHT` now names the coupling between what opens lit and
  what the plane is sized over. And when a guard is written for a defect, **mutate the code
  and watch it fail**: 8 of 8 injected defects are caught now, 5 of 8 were before.

T-47 landed 2026-09-04 (PO: *"make all the elements dynamic so they don't shift around on
different screen sizes, both pages"*). A 14-viewport audit of the built page found **131
layout defects**, one of them at every width since T-13: panel [4] drew its caption **twice,
on top of itself** — `update_layout(annotations=[...])` **broadcasts** a one-element list
across every existing annotation, so the caption had silently overwritten both subplot
titles. Three things worth carrying:

- **A Plotly caption cannot wrap, so it will collide eventually.** It is one line of SVG text
  pinned to a fraction of a box whose pixel width changes with the viewport, sharing the band
  above the plot with a legend that GROWS as the figure narrows. That arrangement produced
  the same defect five times here at five different widths. **Captions are HTML now**
  (`with_caption` / `figure_caption` → `layout.meta` → both pages render it), and the rule
  that replaced three tokens and two arithmetic tests is: *the band above a plot is empty*.
  A guard with no arithmetic in it cannot have the arithmetic wrong.
- **A width floor beats a squeeze.** A 53-step slider and a seven-entry legend do not fit a
  phone however carefully they are placed, so below `FIGURE_MIN_WIDTH` the panel scrolls
  rather than the figure deforming. "The chart scrolls" is honest; "the chart is broken" is
  not (AD-9's posture, applied to layout).
- **One stylesheet, both renderings.** The Reflex app had restated the panel chrome as inline
  component props and therefore had **no breakpoints at all** — it stayed a 10-column grid at
  every width while the published page collapsed. It now renders `theme.PAGE_CSS` and the
  same `osl-*` class names, so a responsive rule cannot be right in one product and missing
  in the other. `PANEL_STYLE` / `PANEL_HEADER_STYLE` deleted. Verified in a real Chromium:
  **0 defects across all 14 widths**, and Reflex switching 10 → 2 → 1 columns.

T-12's scaffold landed 2026-09-06 (FR-7). An unnumbered full-width panel, "Reading the
surface", sits directly under the hero row in **both** renderings and prints each of the
brief's three questions above its answer. The text lives in
`options_surface_lab/commentary.py` — prose, no imports, no logic — which both
`build_preview.py` and the app import, so the graded page and the dev app cannot say
different things. It is unnumbered because the indices name *figures* and are also the
published page's listener addressing scheme (`osl-fig-{n}`); renumbering five panels to slot
prose into the sequence would churn the page's only wiring for a decoration.

**The PO wrote the three sentences the same day**, closing G-4 and the last P0 gap. The
guards that policed their absence stay: an empty slot prints `[unwritten]` in red, fails
`test_the_three_sentences_are_written`, and is refused by the Pages workflow — FR-7 is the
only graded element with no figure behind it, so nothing about the render fails when it is
missing.

**The module and the page are two artifacts, and CI grades the second.** The prose was
committed without re-running `python build_preview.py`, so the committed page still said
`[unwritten]` and the Actions run failed — correctly, but pytest introspected the 2.6 MB
document into the log and buried a one-line cause in tens of thousands of lines. Two rules
came out of it: **anything that changes what the page SAYS needs a rebuild in the same
commit** (the same lockstep the docs have), and **a test that asserts against the built page
reduces to a bool first** — `stale = MARKER in html; assert not stale, "…"` — so the failure
names the fix instead of printing the artifact.

**A test whose subject depends on the calendar reports on the calendar** (2026-09-07, PRD
OQ-6, found by CI). `synthesize_demo_payload` anchors its window to `today()`, so the module
fixture's LAST date moves with the run — and 28 of its 60 dates refuse no strike at all.
`test_a_refused_strike_breaks_the_line_instead_of_being_bridged` asserted the last date has a
hole; on a Monday, when the window ends before an expiry lands, it failed with
`assert 90 < 90` — a false failure against correct code, on a date CI had simply never landed
on before. The assertion was about the fixture, not the figure. It now *finds* a date that
refuses a strike, and fails only if the fixture has none anywhere. The fixture itself
is still calendar-dependent — OQ-6's `end_date` parameter is the root fix and needs PO
sign-off.

**Next up (2026-09-17):** **Assignment 2 is due Sunday 2026-09-20 23:59 EST.** The first live
entry is **booked** — see T-78 below. ~~T-56~~, ~~T-77~~, ~~T-57~~, ~~T-58~~, ~~T-79~~, ~~T-68~~ and ~~T-69~~ are done — **the
tape is pulled, the book runs, the fill assumption is measured, the page has a route, and both
figures exist** — so the critical path is now **T-59** (put the panels on the page), T-60 (the
PO's write-up), then T-71/T-72 to ship. **T-66 (notebook 03
§1–§4) is still open**: it was meant to be co-built with T-57 and was not; T-58 created the
notebook and wrote §5 into it, so T-66 is now a matter of filling in the sections above its own.
The PO chose **QQQ** (SD-1, 2026-09-12) and the **last
hourly bar of the week's first session** as the entry bar (SD-4, 2026-09-13). The close is where
the mid is most defensible, which is the whole fill assumption; it also makes OQ-11 load-bearing
(a bar's `ts` convention decides which bar "last" is) and OQ-13 live (does the brief's "Monday
close" admit the last hourly bar — ask in class).

**T-78's entry leg ran 2026-09-14 (FR-21) — the system booked the first week, and the second
half of T-78 is Friday 09-18's `… live settle`.** One run of `python -m
options_surface_lab.covered_call.live enter` read the **15:00 ET** bar (the tape ran to 18:00, so
`max(ts)` would have taken a post-close stub), saw spot **709.16**, selected the nearest OTM
strike **710**, and booked `BUY 100 QQQ @ 709.16` + `SELL 1 QQQI182671000.U @ 6.045` — the mid of
6.01/6.08 — leaving cash **4,688.50**. **I-1 reconciles against the blotter alone**
(75,000 − 70,916 + 604.50); no skips, `ric_form: live`, no diagnostics errors, 97 covered-call
tests green. `covered_call_live.json` is committed — it is data the page renders (FR-21's panel
is T-59). Two things to carry:

- **The legs are `sync=5s` apart** (stock `c_sec_ofst` 3599, call 3594) — trade-to-trade, not
  trade-to-quote, exactly as SPEC §6.3 already qualifies it. The live week measures the same
  residual the 09-08 dry run did rather than assuming it away.
- **The observation point is load-bearing, and now there are two weeks of evidence for it.** The
  entry bar's high was **711.96** against its 709.16 close, so reading the bar's *start* would
  have written the **712** call, not 710 — the 09-08 rehearsal said the same thing (719 at the
  close, 720 at the open). SD-4 fixes the *bar*; what this pair argues is that the rule must fix
  the **observation point within it**. It belongs in the write-up (T-60), not in a reader's
  discovery.

**T-55 closed 2026-09-13 — all six strategy decisions are made** (PRD §15): window
**`2026-07-06 → 2026-09-11`** (SD-2), **$75,000 fully funded** (SD-3), **nearest OTM** (SD-5),
**strict `> K`** at expiry (SD-6). Two consequences T-62 measured, both of which belong in the
write-up rather than being discovered by a reader: nearest OTM on QQQ's **$1 strike step**
lands ~0.1% above spot, so the rule is effectively at-the-money and **6 of the 10 weeks assign**;
and the $75,000 base sits just above the peak entry cost of **$72,982**, so the book is ~97%
invested and a **NAV**-measured return is not diluted by idle cash. `NEG_AVAILABLE` is
implemented and never fires. What remains of A2-M0 is printing the decisions on the page (FR-14) and signing AD-12.

**T-65 landed 2026-09-13** — `options_surface_lab/covered_call/rules.py`, the first code of
Assignment 2 and the first module of the AD-12 subpackage. **AD-12 was signed 2026-09-14
(T-74)**, amended on the two points T-80 established after the proposal was written: `live.py`
joins the module list, and the **blotter-row constructors are pinned to `rules.py`** so
`engine.py` never imports the module holding the network (NFR-5 — a live row and a backtested
row come from one code path). The audit behind the signature: `rules.py` is pandas + stdlib
only, `live.py`'s sole network seam is `lseg_session()`, `writeup.py` has no imports, and
nothing in 1.1 imports `covered_call`. It holds `Params` (frozen, defaulting to all six SD
decisions, printed whole by FR-14), `select_strike`, `is_itm` and the calendar helpers.
**37 tests, 9 of 9 injected defects caught.** Two things worth carrying:

- **`max(ts)` is banned in this package, and a test injects it.** It is the T-62 trap made
  mechanical: `entry_bar_ts` / `closing_bar_ts` are the only functions allowed to say which
  hourly bar is "the close", and settlement always reads the **closing** bar even when SD-4
  picks the open, so the asymmetry is explicit rather than implied. A tz-naive index is
  **refused**, not assumed to be exchange time — silently treating LSEG's UTC as ET moves
  every bar four hours.
- **Verified against something it did not produce** (the T-46 rule). Run over the real tape,
  the module reproduces all 10 entry bars, spots, strikes and outcomes that an independent
  throwaway script had produced: W37 enters **Tuesday 09-08** off the tape (Labor Day, DR-7),
  and **6 of 10 weeks assign**.

**T-80 landed 2026-09-13 — `covered_call/live.py`, so Monday's entry is runnable** (FR-21).
`capture()` is the module's only network; `plan_entry` / `plan_settlement` are **pure functions
of a captured payload**, which is why the leg that books a real trade is tested with no
credentials (NFR-4) by faking the single session seam. **302 tests green, 15 of 15 injected
defects caught.** The procedure is **RUNBOOK §7**; one command, `python -m
options_surface_lab.covered_call.live enter`, any time after ~16:05 ET. T-67 came along for the
ride (`occ_symbol`, plus `build_option_ric(..., expired=False)` for the live RIC form). Four
things worth carrying:

- **The mutation run found the two defects the offline tests could not reach**, both in the
  parts only the CLI and the network path enter: the **re-run guard** and the **DR-7 session
  resolution**. Faking `lseg_session` — one seam — brought both under test. *A guard that only
  the live path executes is a guard no offline suite has ever run.*
- **`expiry - 4 days` is not Monday.** The first CLI run entered on **2026-09-07, Labor Day**,
  found no bars and logged a *false* `SKIP_NO_STOCK_PRINT`. `capture()` now pulls the week and
  takes its first session off the tape, exactly as the backtest does. The live leg still needs
  the calendar for the **expiry** (that week has not happened yet, SPEC §3.2 item 3b) and fails
  soft when it is wrong.
- **A re-run is refused**, for booked rows *and* for an already-logged skip (I-10: a week
  appears once). The failure mode this guards is a nervous second run on Monday evening.
- **The fill assumption is measured now, not asserted** (PO review, 2026-09-14, SPEC §6.3).
  Two claims were written down that the data did not support and are now struck: that
  `BID`/`ASK` are the **NBBO** (unverified for a `.U` RIC — the 1.1 README's "closing NBBO
  midpoint" is `MID_PRICE` on *daily* bars, a different field at a different frequency), and
  that the **quote** updated at a given second (`C_SEC_OFST` times the last **trade**; the
  stock shows 59,239 trades against 135,274 bid moves and there is no `BID_SEC_OFST`). What
  *is* supported: the fill is the midpoint of the **final bid and ask reported in the bar**.
  DR-6 puts both legs in the same bar, which is not the same instant, so the residual gap is
  now **measured and booked**: `capture()` pulls `C_SEC_OFST`/`HIGH_1`/`LOW_1` for both legs
  and the entry note carries `sync=5s`. On the 09-08 entry bar the legs' last trades were 5
  seconds apart with spot at 718.41, below the 719 strike. **That is trade-to-trade, not
  trade-to-quote** (PO, second pass): with no timestamp for the final bid/ask update, the
  closing quote could have been set earlier in the hour, so synchronisation is claimed at the
  **common-bar level** only and the gap is offered as the sharpest available evidence, not as
  proof. **And the strike was not obvious all
  hour:** spot opened that bar at 719.315 and ranged 717.25–719.55, so reading the bar's
  *start* would have picked **720**. That is the argument for fixing the observation point
  rather than merely the bar, and it belongs in the write-up.
- **A strike over $999.99 now raises.** It used to build a RIC that parses back to a
  *different* contract and returns nothing — an invisible skipped week. QQQ at ~$715 is well
  inside the range; the point is that the failure is silent, so it is refused rather than
  logged.

**T-81 — the adversarial review of this session (2026-09-15). 31 findings ruled on, 23
confirmed, and the two high ones were both on Friday's settlement leg.** Six lenses hunted
`tape.py`, `rules.py`, `live.py` and the new tests; a skeptic then tried to refute each
finding by running code against the committed tape rather than by reasoning. Four things to
carry:

- **The settlement leg could have resolved the wrong week.** `--expiry` defaults to
  `coming_friday()`, which from the Saturday onward is the *next* Friday, and every downstream
  guard keys on the **session** — so a settle run that slipped a day booked an `ASSIGN` against
  the 25-Sep close for a contract that expired 18-Sep, and passed every check. Reproduced on a
  copy of the real book. `plan_settlement` now **raises** on a mismatched expiry (not a skip —
  a skip is a false market fact and I-10 would then refuse the correct re-run), and `settle`
  defaults to the contract the book is short.
- **An outage was being written into the book as a fact about the market.** An LSEG timeout,
  or running before the 15:00 bar closed, wrote `SKIP_NO_STOCK_PRINT` and exited 0 — and I-10
  then refused the re-run, leaving the call open forever (I-7). `capture()` had been recording
  `stock_error` and `bars_in_session` all along and **nothing read them**. `unreadable_reason()`
  now does, and writes nothing. *The guard I had added that morning closed only the handshake
  door; every other way the bar is unreachable walked straight through it.*
- **"Compare a thing against something it did not produce" applies to counting, too.** The
  contract accounting counted RIC *strings*, so a strike asked under both RIC forms was counted
  twice as a miss and a contract rescued by the second form read as answered *and* unanswered.
  The real figure is **952 answered + 75 refused = 1,027 contracts** over 1,102 RIC requests —
  the "952 + 150 = 1,102" reported earlier was inflated, and it had reached the RUNBOOK's
  verification row, where an operator would have checked it and seen it "add up".
- **Three of my own new guards could not fail.** The OQ-6 clock test sanitised docstrings by
  replacing the literal `today()` — which deleted the exact substring its main arm then
  searched for, so a plain `dt.date.today()` was undetectable. Nothing proved `lseg_session()`
  *calls* the session guard (deleting the call left the suite green). And a test of the killed
  quote's print asserted nothing whenever that bar happened not to print. A test written for a
  defect must be watched to fail on it — **including the tests written in the same pass as the
  fix**.

**T-63 landed 2026-09-15 — the synthetic tape, so A2 runs with no tape at all** (AD-7,
SPEC §3.4). `synthesize_tape(end_date, *, seed=7, weeks=12)` in `tape.py`, plus
`tests/covered_call/conftest.py` (`synthetic_tape`, `role_weeks`, `params`, and a `real_tape`
that **skips** rather than quietly synthesizing). **29 tests, 17 of 17 injected defects
caught.** Four things worth carrying:

- **`end_date` is required and positional — OQ-6 made mechanical.** A default would be a clock
  reference waiting to happen, and the calendar-dependent fixture has already cost one false CI
  failure. One test asserts the parameter has no default; another greps the generator's own
  source for `date.today` / `datetime.now` and fails if either appears.
- **Every skip the engine can log has a named week** (`SYNTHETIC_ROLES`): Monday holiday,
  Friday holiday (Thursday expiry, and the RIC says so), a one-session week, a half-session
  entry day, a zero bid on the chosen strike at an entry bar, and a chain that tops out below
  spot. A test asks for the case **by name**; hunting for a week that happens to have the
  property is how a fixture change quietly stops testing what its test claims. Each is
  verified by reading it back through `rules.py`, not against the generator's intent.
- **A fixture priced off one fixed spot passes every static bound.** The mutation run found it:
  intrinsic below, the stock above, each number individually plausible — and the mid↔spot
  *relationship* destroyed, which is precisely what T-57's fills and T-58's fit read. The guard
  recomputes Black-Scholes from the tape's **own stock column** and demands a cent-level match.
  Correlation was the first attempt and was too blunt (0.68 on a deep-OTM contract behaving
  perfectly).
- **SPEC §3.3 said something that would have broken the deploy**, and is corrected:
  "`OSL_OFFLINE=1` forces the synthetic tape" was carried over from Part A's wording, but CI
  sets that variable on **every** build — taken literally the covered-call page would be
  rendered from a fabricated book, which §11's own publish guard then refuses. The flag means
  **never pull**, here and in 1.1; the committed tape always wins when present. A test pins it.

**T-77's tape is in (2026-09-15): 37,857 bars, 952 contracts, 10 weeks, `synthetic=False`.**
`covered_call_tape.parquet` + `covered_call_tape.meta.json`. **Verified against something it
did not produce** (the T-46 rule): driven through `rules.py`, the tape reproduces all ten
15:00 ET entry bars, W37 entering **Tuesday 09-08** off the tape, and **6 of 10 weeks
assigning** — the numbers an independent script produced for T-65 — while W37's entry
(S=718.41 → K=719 @ mid 4.80) is identical to T-80's dry run, which reached LSEG by the
*other* code path. 98.5% of option bars at the ten entry bars carry a valid mid. Three
findings:

- **The caret changeover is a few days wide, and now measured twice.** On 09-13 the 09-11
  contracts answered only under the *live* form; on 09-15 all 952 came back under the
  **caret**. So the same window pulled on two dates yields two different `ric_form_used`
  maps — which is exactly why the pull asks under both forms rather than choosing.
- **Thin extended-hours bars carry erroneous `LOW_1`/`HIGH_1` ticks.** The 09-11 17:00 ET
  stock bar prints a low of **667.36** while the tape traded at ~715. One such tick widens a
  week's strike band by tens of strikes, so the pull asked ~100 strikes a week and ~93%
  answered. Left as is: too wide costs soft failures that are recorded; too narrow silently
  omits the strike the rule needed and turns a tradable week into a skip. **Anything that
  plots the stock's high/low must expect these ticks.**
- **The accounting held by luck, and the first version of it counted the wrong thing.** The
  reconciliation is **952 answered + 75 refused = 1,027 contracts**, asked over **1,102 RIC
  requests** across the two forms. "952 + 150 = 1,102", reported here first, counted RIC
  *strings*: a strike asked under both forms is ONE contract, so every genuine miss was
  counted twice and a contract rescued by the second form could read as answered *and*
  unanswered at once (T-81). It also reconciled at all only because every leftover happened
  to land in a batch that failed *whole* and was retried one RIC at a time (AD-2) — a batch
  that answers **partially** raises nothing, so contracts inside it that returned nothing
  left no trace. `diagnostics.unanswered` now names every *contract* nothing answered for,
  `describe()` prints both counts, and the test reconciles `(expiry, strike)` pairs. *(The committed
  sidecar predates the key; the same sum is derivable from `requested` minus the tape's own
  RICs, which is what the printed line does.)*

**T-56 landed 2026-09-14 — `covered_call/tape.py`, so the pull is one command** (FR-13).

**The first attempt at T-77's pull failed on the desktop, not the data (2026-09-14), and that
found a defect in both acquisition modules.** `ld.open_session()` **does not raise when the
handshake fails** — it logs, returns, and leaves a *closed* session behind. So the pull ran its
stock request against a dead session and reported `No QQQ.O bars returned`: a desktop outage
misattributed as an empty tape. Worse on the live side, where the same path would have written
a false `SKIP_NO_STOCK_PRINT` into the book — and **I-10's "a week appears once" would then
refuse the re-run that would have booked it correctly**, which is Friday 09-18's settlement.
`_require_open_session()` now fails at the seam in both modules, with a test each. The symptom
to recognise: `/api/status` answers **`ST_PROXY_READY`** in ~2s while `POST /api/handshake`
hangs past 20s and retries forever — the proxy is up, the desktop behind it is not answering.
**"Workspace is running" is not the check**; RUNBOOK §9 is the procedure.
`fetch_tape()` holds the module's only network and is human-invoked once (**RUNBOOK §8**;
§7 is the live leg); `load_tape()` reaches it under **no** circumstances and hands back a frozen
`Tape(bars, meta)` — the SPEC §3.1 table plus the payload keys, which live in a JSON **sidecar**
beside the parquet and are committed with it. **31 tests, 16 of 16 injected defects caught**;
the whole pull path runs offline by faking `lseg_session`, the one seam. `pyarrow` is now in
`requirements.txt`. Four things worth carrying:

- **The offline guarantee is a property of which function you called, not of an env var.**
  `load_tape()` never pulls whatever `OSL_OFFLINE` says; `fetch_tape()` refuses to run under it
  *and* refuses to overwrite an existing tape. And a pull that finds no stock bars **writes
  nothing** — a half-written tape would block its own retry (fetch refuses an existing file) and
  would render as a perfectly plausible empty book.
- **A strike ladder computed in floats is a silent defect.** The RIC grammar stores a strike as
  five digits of hundredths; a drifting ladder builds a RIC one cent off a real contract, and
  that does not error — it returns nothing, which reads as "never listed". The band is integer
  arithmetic in hundredths, and a test round-trips every strike it generates through
  `build_option_ric` → `parse_option_ric`.
- **The band is per week's own range, not the window's.** Ten weeks of QQQ span more than any
  one week's chain; a window-wide ladder asks every expiry for strikes it never listed, which is
  slow and fills the diagnostics with failures that mean nothing.
- **The two RIC forms are asked per contract, not per week** (SPEC §3.3): the caret form first,
  then the live form for whatever did not answer, and the winner is recorded in
  `diagnostics.ric_form_used`. The most recent weeks answering only `live` is T-62's finding,
  not a fault. **Still open:** the synthetic tape is T-63, so `load_tape()` with no parquet
  **raises and says what to do** rather than inventing bars. *(Superseded the next day by
  T-63: it now falls back to the synthetic tape with a `RuntimeWarning`; `fallback=False`
  raises instead.)*

**T-62 landed 2026-09-13** — the LSEG hourly spike, evidence in `notebooks/t62_qqq_hourly_spike.json`.
QQQ's root and RIC format are proven, hourly reaches a contract's whole listed life, and the
**strike step is $1.00**. Four things worth carrying:

- **"The last bar of the session" is not the close.** Bars are tz-naive **UTC stamped at the
  START** (`O_SEC_OFST` = 0, `C_SEC_OFST` = 3599 throughout), and *both* tapes run past the
  16:00 ET close carrying real quotes — the stock to 19:00 ET, options to 16:00 ET. So
  `max(ts)` of a session is a post-close stub, and on 2026-09-08 it moved the 18-Sep 715
  call's mid from 11.195 to 11.02. SD-4's closing hour is the bar whose **ET start is 15:00**
  (19:00 UTC under EDT, 20:00 under EST — convert, never hardcode). SPEC §3.2 item 4.
- **The live entry is not a race.** LSEG serves hourly `BID`/`ASK` *history* for a live,
  unexpired weekly, so Monday's entry is captured from the **completed** 15:00–16:00 ET bar
  that evening, through the same code path the backtest uses. Nothing post-16:00 enters the
  decision.
- **The brief's RIC `DAY` rule does not resolve** (OQ-15). It says "not zero-padded (`5`, not
  `05`)", yet all three of its single-digit-day AAPL examples fail as written and succeed
  padded; `build_option_ric()` already pads, and Part A's UUUU 07-Aug expiry proves it. The
  brief is precedence 1 and is **not edited** — ask the instructor.
- **The caret suffix is not immediate.** Two days after expiry the 09-11 contracts resolve
  only under the *live* form; the 09-04 ones, nine days out, only under the caret. The pull
  must try both and record the winner (SPEC §3.3) — otherwise recently-expired weeks
  silently log as "no quote".
**T-84 — CI was red on three consecutive commits while the suite was green here every time
(2026-09-17).** Two causes. **`requirements.txt` was unpinned**, so CI resolved whatever PyPI
held that morning — **pandas 3.0.5** — while `algo` kept August's **2.3.3**; every version is
pinned now, to what `algo` runs. And **the tape's stored schema was inherited rather than
declared**, which pandas 3 decided differently: `ts` came out `datetime64[us]` from a python
`datetime` where pandas 2 forces `ns`, and a parquet string column read back as the new `str`
dtype rather than `object` — so the synthetic tape and a tape off disk carried different
schemas on the same code, which SPEC §3.4 forbids. `TS_UNIT` and `_OBJECT_COLUMNS` are pinned
by `_normalise_dtypes`, the one place `load_tape` and `synthesize_tape` both pass through.
Verified in a clean Linux venv **both ways — 588 green on pandas 2.3.3 and on 3.0.5** — so the
fix is version-agnostic and the pin is for reproducibility, not for hiding. Three things to
carry:

- **The guard that failed had been exempting the columns that broke.** The schema test did
  `continue` past `ric`/`kind`/`cp`/`expiry` — "object columns carry python values, not
  dtypes" — and that exemption is exactly where the schema drifted. *A column a schema test
  skips is a column with no schema test.*
- **Its reference could only ever catch half the failure.** It compared the generator against
  `empty_bars()`, which the generator was written against; the drift that reached CI was on
  the **loader** side. The new test's reference is a tape that has actually been through a
  file — T-46's rule, applied to a schema.
- **A green local suite says nothing about CI while the two environments are not pinned to
  each other.** Three commits' worth of "it passes here" was true and irrelevant. Reproducing
  it took a clean Linux venv built from `requirements.txt`, which is the only thing that ever
  ran what CI runs.

**T-69 landed 2026-09-17 (FR-16, FR-17) — `covered_call/plots.py`, so both of A2's
figures exist.** `account_figure(book)` and `mid_vs_print_figure(evidence)`. **23 tests,
24 of 24 injected defects caught; 653 green, no xfail.** The module is presentation and
recomputes nothing, which makes almost every test one shape: *the figure says what the `Book`
or the `MidVsPrint` says, and nothing it derived itself* — T-46's rule applied to a plot,
because a test that reads a number back out of the trace it just set proves only that Plotly
stores what it is given. Six things worth carrying:

- **T-69's own spec forced an AD-12 question.** "Captions via `with_caption`" — and
  `with_caption` lived in 1.1's `option_surface_plot.py`, which A2 may not reach into. They
  are the figure side of the *panel* contract rather than 1.1 content, so `with_caption` /
  `figure_caption` / `as_panel_figure` now live in **`page_shell.py`**, the module that exists
  to hold what both pages share. The move **removes** a dependency instead of adding one:
  `page_shell` had been importing `figure_caption` back out of `option_surface_plot` through a
  deferred local import, to dodge the cycle that arrangement created. `option_surface_plot`
  re-exports all three, so every existing call site is untouched.
- **Figures are born panel-ready here.** 1.1 emits a titled figure and the builder calls
  `as_panel_figure` to strip it, because those figures are also shown standalone by the Reflex
  app. This page is their only consumer, so the two-step is gone — and with it the defect it
  invites, which this project has already shipped once (a figure whose declared height
  overflowed the box reserved for it, DESIGN-BRIEF §8).
- **One axis, shared with zero, and that costs something on purpose.** FR-16's panel asks
  *does NAV stay above the requirement*, which is only meaningful on a common scale — so a
  secondary axis for NAV is wrong here however much flatter it makes the line look. The price
  is that NAV's own path is a ~2% band near the top of a chart that reaches to zero; the return
  is the readout strip's job, and the caption points instead at the number that *does* answer
  this panel: the available floor **at an entry bar**, derived from the ledger, never typed.
- **`y = x` is drawn at 45 degrees or it lies about its own slope.** Both axes carry one
  range; a reader's whole reading of that cloud — is the print above or below the mid — is
  read off that angle. Two mutants (unshared axes, a range that crops the sample) are caught.
- **The R² publish guard needs an anchor a grep can find.** SPEC §11 requires "the R² line",
  and that line carries `R²`, `×` and `−` and exists **twice** in the built page — as panel
  HTML and inside `layout.meta`, where Plotly's encoder ships a slash as `\/`. So
  `plots.FIT_CAPTION_PREFIX` is a constant, and a test pins it ASCII and free of `/` and `·`
  rather than trusting the next person who shortens a caption (T-45's defect, pre-empted).
- **Deferred on purpose, and it is the best thing not on that panel:** marking the book's
  **ten fills** on the cloud. SPEC §10.2 measures the fill error there at **$0.0375** against
  $0.035 over the whole sample, and it is the assumption at the points where it actually cost
  money. It is not what T-69 specifies and it is one call away — worth raising with T-59/T-60
  rather than deciding here.

**T-68 landed 2026-09-17 (FR-18, AD-6) — Assignment 2's lines and table rules**, in
`theme.py` and recorded in **DESIGN-BRIEF §9**: `NAV_LINE` / `MARGIN_IM` / `MARGIN_MM` behind
`account_line()`, `FIT_LINE` / `IDENTITY_LINE` for FR-17's panel, the `.osl-table*` family and
four table metrics. Three PO decisions, taken with the measurements in front of them.
**17 of 17 injected defects caught; 628 green at the time, no xfail.** Five things worth carrying:

- **The palette had no room left, and that is a finding rather than an excuse.** Every hue the
  wheel still has free sits within ~35 deg of the amber — which is *type*, not data — or within
  ~40 deg of a locked series hue (orange 24 deg from `ACCENT`, azure 3 deg from `NEUTRAL`,
  straw 6 deg). So reuse was the principled answer here, not the lazy one, and the section says
  so with the numbers rather than asserting taste.
- **"A reference is not a series" earned its second application.** IM and MM are *requirements*
  computed off LMV, not measurements of the strategy — the reader's question is "does NAV stay
  above them" — so DESIGN-BRIEF §6 rule 6 binds them exactly as it binds FR-12's spot plane.
  Subordinate by **weight and dash, not opacity**: a line has no area to fog what is behind it,
  which is the one thing the plane's rule does *not* carry over.
- **NAV is violet, not the cyan its 10.3:1 would argue for** (PO). Panel [5] of the same page is
  the mid-vs-print scatter, so cyan and magenta are spoken for *there* by the README — a hue
  that means "the mark" in one panel must not mean "the account" two panels up. Violet has no
  job on a page with no puts in it. Tables get **hairline rules, no zebra** and **only the
  exceptions coloured** (skip reason amber, `NEG_AVAILABLE` red, every blotter side left as
  TEXT — colouring every side turns a record into a dashboard).
- **My first base-level CSS guard measured text position, not nesting.** It took
  `PAGE_CSS.split("@media")[0]` and declared seven perfectly unconditional rules missing,
  because most of the stylesheet is written *after* the two breakpoint blocks. It matches
  braces now and strips CSS comments, since a selector merely *named* in a note otherwise
  counts as a rule that exists. It did, however, catch the real thing first: the table rules
  had been inserted after the breakpoints, and a rule hidden inside one renders at some widths
  and not at others — verified by hiding `.osl-table-kv` in a `@media` and watching it fail.
- **`THEMED_SOURCES` is discovered now, not hand-listed.** §6 rule 5 had been stating its own
  hole for weeks — *"a module that emits markup and is not on this list is a module free to
  hold a colour"* — and T-69/T-59 are about to add two modules that render. A mutant hex in
  `covered_call/rules.py`, which the old five-entry list never covered, is caught. A companion
  test names the five renderers, so a glob that silently matched nothing cannot leave every
  literal check passing over an empty parametrisation.
- **The stylesheet change stale-failed the committed artifact**, exactly as the FR-7 prose did:
  `test_the_local_artifact_and_the_published_page_are_one_render` went red until both pages
  were rebuilt. Anything that changes what a page *renders* — not only what it says — needs the
  rebuild in the same commit.

**T-79 landed 2026-09-17 (FR-18, AD-11's interim) — the site has a second page.**
`options_surface_lab/page_shell.py` holds the chrome both builders render (`PageShell` —
command bar, readout strip, panel, document — plus the routes and the cross-page links), and
`build_covered_call.py` publishes `/covered-call/`, carrying the book's six headline numbers
read off `run_backtest` over the committed tape. Each builder now takes `--site DIR` and
writes its own route, so CI copies nothing. **38 new tests, 13 of 13 injected defects caught;
588 green, no xfail.** Driven in a real Chromium: **0 defects across 2 pages x 14 widths**,
zero console errors. **There is still no registry and no template engine** — a third
assignment would mean a third builder, which is exactly what T-51 is for. Five things worth
carrying:

- **"Emitted plotly.js yet?" could not stay a module global.** CI builds both pages in one
  job, so a process-wide flag hands the **second** page "already included" from the first and
  publishes it with no library at all — and CSS and JS both fail open, so it renders as a
  column of empty panel frames with nothing in the HTML to say why. It is a `PageShell`
  attribute now, and a test builds two pages in one process to prove it. *Lifting shared code
  out of a single-consumer module turns its module state into a cross-consumer bug.*
- **A cross-page link is spelled twice, from one render.** The same page is written into
  `_site/<route>/index.html` and as a root artifact opened from the filesystem; a shell that
  hardcoded routes would give the local copy dead links, which nothing but clicking reveals.
  `nav_for(page, site=)` owns both spellings, and the site one is **relative** — an absolute
  `/covered-call/` is right on a user site and wrong on a project site served from
  `/options-surface-lab/`.
- **The committed tape cannot tell a read-off number from a lucky one.** All ten of its weeks
  trade, so `entries` and `weeks` are the same integer and the premium sum equals any literal
  someone types — two mutants survived the headline guard for precisely that reason, and the
  guard looked airtight. The synthetic tape skips five weeks, which separates them. T-57's
  rule met again in a new place: *a fixture that never reaches a branch is a branch with no
  test, however many tests name it.*
- **One synthetic marker per page** (`synthetic panel` / `synthetic tape`). Shared, one page's
  fabrication passes the other's check — and 1.1's fallback panel and a synthetic covered-call
  tape are different fabrications. The routes and every builder invocation are pinned to
  `pages.yml` by a test, because the guards are greps at hardcoded paths: a builder that stops
  running leaves its guard reading a file that is not there.
- **A guard written before its subject cannot fail for the right reason.** SPEC §11's
  remaining per-page guards — `[unwritten]`, the R² line, a non-empty blotter — are *not* in
  the workflow yet; they land with the panels they guard (T-59/T-70), and the workflow says so
  where they will go. Each guard that did land was mutation-checked against the built site
  before being trusted.

T-58 landed 2026-09-16 (FR-17, **A2-M3**) — **`covered_call/evidence.py`**, plus
`notebooks/03_covered_call.ipynb` §5 and `Params.ntm_band` (5%) in `rules`, so FR-14 prints
the sample the R² was measured on. It shipped inside `rules.py` — beside the `valid_mid` it
justifies — and **the PO had it split out the same day**: *"we're following best engineering
SOLID practices, not what CLAUDE.md prefers."* The cohesion argument was real and still lost,
because it gave `rules` two reasons to change. **AD-12 is amended**: the transform core is
`rules` (what the strategy *decides*) + `engine` (the book those decisions *produce*) +
`evidence` (what the tape *says*), and `evidence` may never import `engine` — a fit computed
from the book would restate the fill assumption instead of checking it. *The standing lesson:
"prefer editing existing modules" is a tie-breaker, not a reason to give a module a second
responsibility.*

**T-83 reviewed it the same day (13-agent workflow): 39 rulings — 32 confirmed, 7 partial,
0 refuted — plus ~20 defects the skeptics hit while attacking and 7 from a completeness
critic. Two moved a published number.** The corrected headline on the committed tape is
**n = 16,626 of 37,073** option bars (74.7% of the 22,262 near-the-money regular-session call
bars), `print = 0.9979 × mid + 0.0104`, **R² = 0.9962**, median |print − mid| **$0.035**,
median ratio 1.89%; at the book's ten fills **$0.0375** (0.67%, worst $0.145). **51 evidence
tests, 33 of 33 injected defects caught; 547 green, no xfail.** What to carry:

- **Three of the words in "near-the-money regular-session calls" were true only by accident of
  the tape.** Nothing filtered `cp`; nothing refused a tape pulled for another underlying (the
  guard `engine` has had since T-82 — now shared as `rules.require_matching_underlying`); and
  nothing excluded the **16:00 ET post-close bar**, which was 9.3% of the sample and the
  *tightest* cohort in it — a stub on a fifth of the volume, banded against an extended-hours
  spot, flattering the number it was offered as evidence for. `rules.CLOSING_BAR_HOUR_ET`
  exists for exactly this and `Book.daily_ledger` already filtered on it. **A rule the package
  has decided is not applied until every module applies it.**
- **A number can be wrong in a commit whose own artifact prints the right one.** The published
  band-sweep floor was R² 0.9960; the true floor is **0.9948** at ±2%, and the notebook's
  stored output in the same commit already printed 0.994843. It came from reading the wrong row
  of a five-point grid. Four lenses found it independently. *The lockstep rule is not only
  "update the doc" — it is "derive the doc's number from the artifact, then pin it."*
- **`$0.035` is exactly one median half-spread**, per row, at the fills too. Only **30.4%** of
  prints land strictly inside the quoted bid/ask; 28.3% land on an edge and **41.3%** outside.
  So the mid is *unbiased*, not *accurate*, and the scale that makes the gap meaningful is the
  spread — which nothing had quoted. The fitted R² also differs from `y = x`'s in the **sixth
  decimal**, so the fit adds nothing to the identity line. Six findings of this kind are in
  SPEC §10.2 for T-60, including the one number that actually bounds the result: selling all
  ten calls at the **bid** instead of the mid costs **$49.50** — 1.658% → 1.592%.
- **A degeneracy guard took three attempts, and each failed for a different reason.**
  `sxx <= 0` (the mean of N identical floats is not that float: `sxx` ≈ 1e-27 and a confident
  garbage slope) → `x.max() == x.min()` (N−1 identical plus **one** other has a spread, passes,
  and reports slope 6.0000, R² 1.0000 off two points) → the count of **distinct** x, which also
  subsumed a point-count guard the mutation run proved could never fire. *Dead code that looks
  like a safety check is worse than no check.*
- **A guard copied from a sibling can be blind to the thing it was copied for.** The obvious
  way to enforce "evidence never imports engine" is to port `test_engine.py`'s substring ban
  list — which matches none of `from .engine import run_backtest`. One of the skeptics found
  that in the *proposed fix* before it was written. The guard is structural (AST) and names
  `engine` explicitly.
- **My mutation harness was worthless twice before it was right, and neither time was about the
  code.** A killed run left an injected defect (`spot = spot.ffill().bfill()`) in the tree and
  the next run read the poisoned file as its **baseline**, reporting a meaningless 22/22 — my
  integrity check had grepped for the correct line and found it, confirming the presence of
  right code rather than the absence of wrong code. Then a review subagent, told to use "the
  system temp directory", overwrote the harness itself in the shared scratchpad. The harness now
  rewrites both files from its snapshot and verifies before **every** mutant, and lives in its
  own directory. *A harness that cannot prove its own baseline is measuring nothing.*
- **Two mutants are equivalent on every reachable input** (`~(<= band)` vs `> band`, now that
  `no_strike` refuses a NaN moneyness upstream; and `<=` vs `<` on the band edge, which no $1
  strike ladder can land on to the last bit). They are **named in the module** rather than left
  to reappear as survivors — T-57's precedent.

AD-10 is approved and **not landed**; **AD-11's interim landed 2026-09-17 (T-79)** while its
registry and templates stay deferred. The whole M5 restructure is deferred until after the
submission — PO to confirm the standing recommendation. The order that fits the calendar is at
the top of `docs/BACKLOG-2.md`: ~~T-62 spike → decisions → T-78's entry → T-56 → T-57 → T-58 →
T-79 → T-68 → T-69~~ (all landed) → **T-59** → T-60 → ship, with T-78's settlement leg on
Friday 09-18. 1.1's brief is archived at `docs/archive/ASSIGNMENT-1.md`. M4's T-20/T-22 remain open.
**653 tests green, no xfail** (2026-09-17, full run; the 588 that preceded T-68 were verified in a clean Linux venv on the pinned versions *and* on pandas 3).
Update this paragraph as things land (lockstep rule).

**T-57 landed 2026-09-15 — `covered_call/engine.py`, so the book runs** (FR-15, FR-16, NFR-6).
`run_backtest(tape, params) -> Book`: the weekly loop, fills, settlement, the blotter, the skip
log and the per-bar Reg T ledger, plus `window_weeks` / `build_ledger` / `settlement_print`.
**83 tests; 42 defects injected across T-57 and T-82's review, 41 caught** — the single miss is unreachable by construction and named in place. On the committed tape: **10 weeks, 10 entries,
no skips, 6 ASSIGN / 4 EXPIRE, $6,657.50 of premium, final NAV $76,243.50 (+1.66%)** on $75,000;
`available` bottoms at **$38,886.50 at an entry bar** — the only bars the flag is checked on — so
`NEG_AVAILABLE` never fires. (The all-bars minimum, $38,236, sits on a thin **05:00 pre-market**
bar; quoting it would have been this package's own `max(ts)` mistake in a new place.) All **four**
skip reasons fire on the synthetic tape, over five skipped weeks — `SKIP_NO_QUOTE` fires twice. The week 2026-09-08 → 09-11 is **hand-checked in a test docstring** against the
raw bars and reproduces T-80's live rehearsal, which reached the same entry by the other code
path. Five things worth carrying:

- **Everything except the blotter is a projection of it.** The skip log, the ledger and the
  weekly table hold no number the blotter and the tape do not already hold, which is what lets
  I-1 reconcile cash against the blotter *alone* and stops a defect in the loop from showing up
  as two numbers that agree because one copied the other (SPEC §1).
- **The spec had no answer for a missing print at the *expiry* closing bar, and the engine
  needed one.** Entry and settlement are deliberately asymmetric: a missing print at the entry
  bar skips the week (nothing is owed, DR-1 forbids inventing one), but settlement *may not*
  skip — the call is already short and I-7 says every open call resolves, so a skipped
  settlement leaves the book carrying that call forever. Settlement now carries the last print
  in that session at or **before** the close and the row says `S_exp_carried`. It never reaches
  *forward*: a bar after the close is T-62's post-close stub. SPEC §7 and §13 record it; neither
  tape exercises it, so a test blanks the bar on a copy of the synthetic tape.
- **`max(ts)` has a second hiding place: the headline.** `Book.final_nav` reads the last
  **15:00** ledger row, not `ledger.iloc[-1]` — the stock tape runs to a 19:00 ET bar, and on
  this tape the stub and the close differ by $10.65. The rule `rules.py` enforces for bars
  applies just as much to the number a reader quotes.
- **All four first-pass mutation survivors were defects in the *guards*, not the engine.** I-11
  multiplied by the module's own `IM_RATE`, so it passed at any rate — T-46's "a check that
  reads back its own effect", landed on again. The combo-skip test picked its week by *role*
  and happened to watch one that was never flat, so a mutant that bought stock on a flat
  no-quote week survived. And **`S_exp == K` occurs on neither tape**, so SD-6 — the whole ITM
  decision — was untested until a test *built* the case by pinning a settlement print onto a
  strike. A fixture that never reaches a branch is a branch with no test, however many tests
  name it. The fourth was a skip log with every `detail` blanked, which nothing noticed.
- **$72,982, not $72,984.** T-55/T-62's peak entry cost was $2 out; the 2026-08-17 15:00 bar
  prints 729.82. Corrected in PRD §15 and BACKLOG-2.

**T-82 — the adversarial review of T-57 (2026-09-15), run as a 13-agent workflow.** Six lenses
(the weekly loop, money and the ledger, time and bars, test quality, claims-versus-reality,
layering) each hunted the change; a skeptic then attacked that lens's findings **in an isolated
worktree, required to run code rather than reason**; a completeness critic asked what nobody had
covered. **37 rulings + 6 completeness findings — 33 confirmed, 4 partial, 0 refuted** — which
collapse to roughly 25 distinct issues, because the serious ones were found independently by
three to five lenses each. The top five were reproduced by hand before anything was changed.
Zero refutations is worth noticing rather than celebrating: it means the lenses were
conservative, not that the skeptics were rigorous.

- **The one *high*: the engine fabricated the contract's RIC instead of reading it off the tape.**
  `build_option_ric(..., expired=True)` hard-codes the **caret** form, but SPEC §3.3 says which
  form a contract answers under depends on how long ago it expired — so which one a tape carries
  depends on **the date of the pull** (T-77 measured the same window answering differently two
  days apart). On a live-form tape the blotter named a contract with no bars, and every per-bar
  call mark then missed and **carried forward silently**: 624 of 624 covered bars frozen, NAV
  wrong on 614 of 784 bars by up to **$2,201**. I-3/I-4/I-6 would have gone red at the blotter
  level — but **the ledger half had no invariant at all**, and the ledger is what FR-16's NAV
  chart draws. The engine now reads the RIC the tape answered under and keys every mark on
  `(expiry, strike, ts)`. *The committed tape is 952/952 caret, so nothing shipped wrong — the
  defect was one re-pull away.*
- **The guard written to enforce S-7 was itself the T-46 defect.** `test_marks_are_carried_forward…`
  looked each mark up by `row["call_ric"]` — the same fabricated key the ledger had used — so it
  passed with all 624 marks frozen. *A guard that addresses its subject by the key under test is
  not a guard.* The replacement addresses the bar by `(expiry, strike, ts)` out of `tape.bars`.
- **I-7 contradicted a rule the same session had written.** T-57 added §7's settlement
  carry-forward, which *moves* the resolution to an earlier bar — and left I-7 asserting the
  resolution sits on `closing_bar_ts`. The suite NFR-6 calls the executable definition of
  "logically consistent" would have gone red against behaviour the spec calls correct. I-7 is
  widened; it keeps its teeth (nothing after the close, nothing off-session, no silent
  substitution). **Amending a spec means re-reading the invariants that quote it.**
- **`daily_ledger()` deleted a whole session.** Selecting `hour == 15` drops a half session
  entirely — no row, no note — and `final_nav` then quotes the *previous* session's close as the
  window's. Live on the synthetic fixture (2026-08-24 vanished); latent on the real tape only
  because this window happens to have no early close. Same fallback as §7 now, and the row's own
  `ts` is the marker.
- **My own new guard let the mutation through.** `test_the_book_is_identical_on_a_live_form_tape`
  first checked the blotter's RICs against the **union** of both tapes' spellings — which
  contains the caret form, i.e. the defect. Caught only because the fix was mutation-checked in
  turn. *Mutation-check the repair, not just the original.*
- **Three numbers this session wrote down were wrong, and one was wrong in a way the package has
  a rule about.** `$38,236` for the available floor came off a thin **05:00 pre-market** bar —
  `max(ts)`'s mistake in a new place; the flag is only checked at entry bars, where the floor is
  **$38,886.50**. "All five skip paths" is **four reasons over five skipped weeks**. And the
  blotter carried `6.130000000000001` in `fill` while the same row's note said `mid=6.13` —
  rounding now happens once, in `rules.money()`.
- **NFR-5's "one code path" is narrower than it reads, and that belongs in the write-up.** The
  live leg guesses a band of RICs rather than reading a chain, so it cannot tell *listed but
  unquoted* from *never listed*: given spot 700.40 with the 701 listed and unquoted, the backtest
  logs `SKIP_NO_QUOTE` and the live leg writes the **702**. The *rule* is one function; the
  *chain handed to it* is not the same set. Inherent to guess-and-check acquisition (DR-10) and
  **not fixable by making the live leg treat an unanswered RIC as listed** — it would then skip
  almost every week. Recorded in SPEC §5 as a stated limitation. **PO decision:** whether §7's
  carry-forward should also bind the live leg (it currently does not, and §7 now says so).

**Secrets:** `lseg-data.config.json` (repo root) holds the LSEG app-key. It is gitignored —
never commit it, never print its contents, never copy it into anything that ships.

## Hard constraints — violations waste the deadline

- **Never re-pull data when `option_pipeline_data.pkl` exists.** Cache-first is graded (AD-1).
- **Never touch the LSEG derivatives-chain endpoint** for expired contracts — known dead end.
- **Production runs offline.** No network at render; app, tests, preview, and export must all
  work on a machine with no LSEG credentials (NFR-4).
- **A pull must never be silent.** Cache-first-then-pull is correct (FR-2), but the app
  announces the pull before it blocks — an invisible one read as a failed load for ~90 s on
  2026-08-30 (RUNBOOK §4). `OSL_OFFLINE=1` forces the synthetic path for CI/export (NFR-4).
  `fetch_from_lseg()` refuses to overwrite an existing cache.
- **The published site is one static HTML file per page.** Built in CI from the committed
  pickle and tape at *build* time; no backend, no run-time pickle read. The revised README
  sanctions this ("you can serve it as an html file … probably simplest"). Consequence: no
  Reflex event handler runs in production, so **every published interaction must be
  Plotly-native** (AD-5, T-15 — currently unmet and on the critical path).
- **`MID_PRICE` ≠ `TRDPRC_1` is the whole point.** The revised README (2026-09-01) names
  `MID_PRICE` — the closing NBBO midpoint — as the mark, and states LSEG exposes no exchange
  settlement price for expired US equity options. The wide table's column is `MARK`, a slot fed
  by `MARK_FIELD_DEFAULT` = `MID_PRICE`. Keep mid and print distinct in color *and* symbol;
  label interpolation as interpolation; never extrapolate; holes render as holes and never
  vanish (AD-9).
- **No visual literals outside `theme.py`** (AD-6, FR-8 — landed 2026-09-02). Enforced by
  `tests/test_theme.py`'s `THEMED_SOURCES`, not by review — and a module that emits markup
  and is not on that list is a module free to hold a colour. Read [docs/DESIGN-BRIEF.md](docs/DESIGN-BRIEF.md)
  before re-toning anything; the cyan-mark / magenta-print encoding is fixed by the README.
- **Anchor paths to `__file__`, never CWD.**
- **Tests before refactoring** (NFR-2, ENGINEERING-PRINCIPLES) — the pure functions in
  `*utils.py` are the priority.
- Treat the pickle caches as data artifacts: never overwrite, "clean up", or regenerate them
  without PO approval.

## Working style

- **Git is the PO's, entirely. Sessions never `commit`, `push`, or create branches** — nor
  `add`, `reset`, `revert`, `merge`, `rebase`, `stash` or `tag`. Reading is fine (`status`,
  `diff`, `log`, `show`). Finish the work, leave it in the working tree, and report which
  files changed; Jason takes it from there. He owns every line in the repo (PRD guardrail #6),
  and that includes the history — nothing lands in it that he has not read. If a step
  genuinely needs a commit to proceed (CI must see it, say), name that and stop.
  *(Set 2026-09-04, replacing "commit frequently" — which a session had followed on T-16.)*
- Small, verifiable steps; run tests after each change — the repo is live at
  `Jason-Dorman/options-surface-lab` (T-8, 2026-08-31). For the PO's own pushes: auth is the
  WSL SSH key; Git Credential Manager on this machine is broken (needs .NET 7/8, only 5.0.14
  present), so HTTPS pushes fail silently. Use the SSH remote.
- Route changes via ARCHITECTURE §7's table; if a change fits no row, it's an architecture
  question for the PO.
- Prefer editing existing modules to adding new ones; the module set and their
  responsibilities are specified (ARCHITECTURE §4).
- AI-assisted is fine and expected, but the PO owns every line — keep code small and
  explainable enough for that to stay true (PRD guardrail #6).
