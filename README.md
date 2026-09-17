# Options Surface Lab

**MENG FinTech · Algorithmic Trading II — the semester's site.** One static site on GitHub
Pages that gains a page per assignment, built from Python and committed market data, with no
server behind it.

**Live:** https://jason-dorman.github.io/options-surface-lab/

*This file is the front door: what the project is, what is on the site, how to run it, and
where the real documents are. It is a living summary and never the authority — the documents
under [docs/](docs/) are. Keep it current (the lockstep rule in [CLAUDE.md](CLAUDE.md)).*

## What is on the site

| Page | Assignment | State |
|---|---|---|
| `/` — **the options surface** | [Assignment 1.1](docs/archive/ASSIGNMENT-1.md): expired-options sparsity on UUUU, the mark (`MID_PRICE`) against the print (`TRDPRC_1`) | **Live.** Seven panels: a 3D price surface with an as-of slider over 53 trading days that drives the whole page, the underlying, an implied-vol smile, mark-vs-print, spread, and two occupancy grids. Headline: **1,601 of 7,458 listed contract-days (21.5%) carry a mark with no trade.** |
| `/covered-call/` — **covered call backtest** | [Assignment 2](docs/ASSIGNMENT-2-COVERED-CALL.md): long 100 shares, short 1 weekly call; blotter, ledger, Reg T account, NAV path, mid-vs-print R², write-up | **Live, and filling in — due Sunday 2026-09-20.** Underlying QQQ; the first live entry is booked Monday 2026-09-14. The tape and the **backtest engine** are in (2026-09-15): 10 weeks, 6 assigned, final NAV $76,243.50 on $75,000. The **mid-vs-print evidence** followed (2026-09-16): across the window the print is centred on the mid (`0.9979 × mid + 0.0104`, **R² = 0.9962**), and at the ten bars the book actually filled on the median gap is **3.75 cents** — about one half-spread, and worth **$49.50** over the whole window if every call had been sold at the bid instead. The **route went live 2026-09-17**, carrying the book's headline; its panels — NAV path, blotter, ledger, mid-vs-print, write-up — are next. Board: [BACKLOG-2](docs/BACKLOG-2.md). |

## How it works

Market data is pulled from LSEG **once**, at development time, and committed as a cache
(`option_pipeline_data.pkl`). Everything downstream is pure Python: pandas transforms → Plotly
figures → one self-contained HTML page **per route**, rendered **at build time** by
`build_preview.py` and `build_covered_call.py` in CI and published to Pages. The browser never
reads the cache and there is no backend, so every published interaction is Plotly-native —
slider, legend, axis menu — plus one small inline listener that lets the hero's slider drive
the other panels.

Two things about the tree as it stands (2026-09-17):

- A Reflex app (`options_surface_lab/options_surface_app.py`, `reflex run`) still exists as a
  local viewer. **Its retirement is approved** — it was a second renderer of a page the static
  builder already produces — and lands with [BACKLOG M5](docs/BACKLOG.md) (ARCHITECTURE
  AD-10). Until then it runs, but nothing on the published site depends on it.
- Each page has its own builder, sharing the chrome in `options_surface_lab/page_shell.py`
  and the routes in its page table. That is AD-11's **interim** (T-79): the registry and the
  Jinja2 templates the decision actually calls for land with M5, after the submission, at
  which point a third assignment stops meaning a third builder.

## Run it

Python is the conda env **`algo`** (3.12). Commands are Git Bash syntax, from the repo root.

```bash
source /c/Users/rjd61/anaconda3/etc/profile.d/conda.sh && conda activate algo

python build_preview.py        # 1.1's page  → options_surface_preview.html (~32 s)
python build_covered_call.py   # A2's page   → covered_call_preview.html
python -m pytest tests/ -q     # 588 tests, all green, no xfail
reflex run                     # local Reflex viewer (being retired — AD-10)

# Both builders take `--site DIR`, which is what CI passes: the page lands at DIR/<route>
# with its cross-page links spelled as routes. Rebuild and commit every page a change
# reaches — page_shell.py and theme.PAGE_CSS reach all of them.
```

Everything runs **offline** off the committed cache; with no cache present, a seeded synthetic
panel stands in and the page says so. Pulling data is a one-time, credential-dependent,
human-run step — [RUNBOOK §3](docs/RUNBOOK.md). **Never re-pull when the cache exists**, and
never commit `lseg-data.config.json` (the app-key; gitignored).

## Where things are

| Path | What |
|---|---|
| `options_surface_lab/option_surface_utils.py` | The transform core — RIC grammar, flatten / attach / pivot, sparsity stats, Black-Scholes inversion. Pure functions, no UI imports. |
| `options_surface_lab/option_surface_plot.py` | One builder per figure, plus the published page's per-date payload. |
| `options_surface_lab/theme.py` | Every colour, font and layout token; the one stylesheet. No visual literal lives anywhere else (tested). |
| `options_surface_lab/commentary.py` | The PO's three sentences (FR-7) — prose only. |
| `options_surface_lab/page_shell.py` | The chrome both page builders render — command bar, readouts, panels, document — and the site's routes. |
| `build_preview.py` · `build_covered_call.py` | One static page builder per route. CI runs both. |
| `option_pipeline_data.pkl` | The committed LSEG cache: 296 series × 53 days. A frozen artifact. |
| `tests/` | 588 tests; the pure functions first, then everything a defect could reach a page through. |
| `notebooks/` | Exploration and evidence, numbered by assignment. Consume the package; never a dependency. |
| `.github/workflows/pages.yml` | pytest in a clean container with no credentials → build → guards → Pages. |

## The documents

Read in this order; the higher one wins on a conflict.

| | Document | Holds |
|---|---|---|
| 1 | [docs/ASSIGNMENT-2-COVERED-CALL.md](docs/ASSIGNMENT-2-COVERED-CALL.md) · [docs/archive/](docs/archive/) | The instructor's briefs — rubric, deadlines, domain rules. Never edited. Finished assignments' briefs live in the archive. |
| 2 | [docs/PRD.md](docs/PRD.md) | Requirements (FR-x), priorities, acceptance criteria, gaps, milestones, open questions — Part A is 1.1, Part B is the covered call |
| 3 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/SYSTEM-SPEC.md](docs/SYSTEM-SPEC.md) · [docs/SPEC-COVERED-CALL.md](docs/SPEC-COVERED-CALL.md) | Layers, decisions (AD-x), the "where does my change go" table · schemas, algorithms, edge cases (1.1) · the book: tape, loop, fills, Reg T, invariants (covered call) |
| 4 | [docs/ENGINEERING-PRINCIPLES.md](docs/ENGINEERING-PRINCIPLES.md) · [docs/DESIGN-BRIEF.md](docs/DESIGN-BRIEF.md) | Code standards · the graphical identity and the rules it may not break |
| 5 | [docs/BACKLOG.md](docs/BACKLOG.md) · [docs/BACKLOG-2.md](docs/BACKLOG-2.md) · [docs/RUNBOOK.md](docs/RUNBOOK.md) | The task boards — 1.1 + restructure · covered call (one T-x sequence) · procedures |
| — | [CLAUDE.md](CLAUDE.md) | Working agreement for AI-assisted sessions: constraints, the PO's role, what has been learned |

AI-assisted throughout; every line is owned and explainable by the PO (PRD guardrail #6).
