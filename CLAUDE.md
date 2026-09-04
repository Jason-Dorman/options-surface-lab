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

**Next up:** **T-12** (the three PO-authored sentences, FR-7) — the last P0 gap. **144 tests
green, no xfail** (the "90" this paragraph carried was stale — `tests/test_build_preview.py`
was never counted into it). Update this paragraph as things land (lockstep rule).

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

- Small, verifiable steps; run tests after each change; commit frequently — the repo is live
  at `Jason-Dorman/options-surface-lab` (T-8, 2026-08-31). Push auth is the WSL SSH key;
  Git Credential Manager on this machine is broken (needs .NET 7/8, only 5.0.14 present), so
  HTTPS pushes fail silently. Use the SSH remote.
- Route changes via ARCHITECTURE §7's table; if a change fits no row, it's an architecture
  question for the PO.
- Prefer editing existing modules to adding new ones; the module set and their
  responsibilities are specified (ARCHITECTURE §4).
- AI-assisted is fine and expected, but the PO owns every line — keep code small and
  explainable enough for that to stay true (PRD guardrail #6).
