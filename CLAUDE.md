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
| 1 | [README.md](README.md) | The assignment: rubric, deadlines, domain rules. Instructor-owned — never edit its assignment content. |
| 2 | [docs/PRD.md](docs/PRD.md) | Requirements (FR-1…FR-12), priorities, acceptance criteria, gap list (G-1…G-8), milestones |
| 3 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, module boundaries, decisions (AD-1…AD-9), the "where does my change go" table (§7) |
| 3 | [docs/SYSTEM-SPEC.md](docs/SYSTEM-SPEC.md) | Schemas, algorithms, edge-case behavior, runtime modes |
| 4 | [docs/ENGINEERING-PRINCIPLES.md](docs/ENGINEERING-PRINCIPLES.md) | Code quality: SOLID, cohesion/coupling, complexity < 10, tests before refactoring |
| 4 | [docs/DESIGN-BRIEF.md](docs/DESIGN-BRIEF.md) | The graphical identity (FR-8): palette, typography, the rules the restyle may not break. PO-directed — read it before changing any value in `theme.py`. |
| 5 | [docs/BACKLOG.md](docs/BACKLOG.md) · [docs/RUNBOOK.md](docs/RUNBOOK.md) · [docs/DEMO-SCRIPT.md](docs/DEMO-SCRIPT.md) · [docs/checkpoint_audit.md](docs/checkpoint_audit.md) | Operational: the task board (work top-down, T-x IDs) · procedures (env, LSEG pull, run, deploy) · checkpoint demo plan · open questions for the instructor |

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
python build_preview.py    # THE DELIVERABLE — builds the static index.html that Pages serves
pytest                     # 90 tests in tests/ — all green, no xfail
reflex run                 # local dev server (FR-1); not what gets published
```

`reflex export` is **not** part of the build any more — see AD-4. The published site is the
single self-contained page `build_preview.py` writes, rendered from the committed pickle at
build time by `.github/workflows/pages.yml`.

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

**Next up:** **T-12** (the three PO-authored sentences, FR-7) — the last P0 gap, and the only
rubric item with nothing on the page at all. Then M4: T-19/T-20/T-21/T-22. **213 tests
green, no xfail.** Update this paragraph as things land (lockstep rule).

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
- **The published site is one static `index.html`.** Built by `build_preview.py` in CI from
  the committed pickle at *build* time; no backend, no run-time pickle read. The revised README
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
  `tests/test_theme.py`, not by review. Read [docs/DESIGN-BRIEF.md](docs/DESIGN-BRIEF.md)
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
