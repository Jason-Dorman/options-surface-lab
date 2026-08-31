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
python build_preview.py    # static HTML preview — verified working from the package layout
pytest                     # 76 tests in tests/ — green (1 xfail records PRD OQ-5)
reflex run                 # local dev server — imports verified; first full run still pending
reflex export              # static bundle for GitHub Pages (FR-9)
```

Current state (2026-08-29): FR-1 package layout landed (`options_surface_lab/` package,
`rxconfig.py`, entry shim, `__file__`-anchored cache paths — imports verified, preview builds
end-to-end). `option_pipeline_data.synthetic.pkl` is **dead weight** — no code reads it and it no longer
unpickles under the installed pandas (`StringDtype` state error); the fallback panel is
generated in-process by `synthesize_demo_payload()`. `option_pipeline_data.pkl`
holds the working panel: **296 series (148 calls + 148 puts)** with
`TRDPRC_1, MID_PRICE, BID, ASK, OPINT_1`. **There is no SETTLE for US listed equity options** —
none is published by the exchanges, OPRA or the OCC — so the mark is derived: `MARK_FIELD_DEFAULT`
= `MID_PRICE` fills a slot the wide table calls `MARK` (pending instructor sign-off, PRD FR-6).
Headline: **1,601 of 7,458 listed contract-days (21.5%) carry a mark with no trade**, median
gap $0.040. Median bid-ask spread is 20% of the mark, so the mark itself is soft — `spread`
and `spread_pct` are on the wide table and drive `spread_heatmap()`.
Puts came from fixing the RIC suffix — it takes the *call* month letter for both rights
(`UUUUR122601100.U^F26`), contradicting the README (T-31). Superseded pulls kept as evidence:
`.trdprc-only.pkl` (first, calls only) and `.trade-only-puts.pkl` (second, no mark). FR-3's transform suite is in
(T-3/T-4): `tests/test_ric_parsing.py` + `tests/test_transforms.py`, plus `test_ric_building.py`
`test_acquisition.py` and `test_app_figures.py` — 76 tests green, no xfail, so the
NFR-2 gate for the FR-8 restyle is satisfied. `theme.py` (FR-8) and CI/Pages (FR-9) still to come; T-5 is ◐ pending one clean
re-run on the synthetic panel. Update this paragraph as things land
(lockstep rule).

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
- **GitHub Pages has no Python backend.** Anything only reachable through a Reflex event
  handler is invisible in production — every published interaction must be Plotly-native, and
  default figures bake at import time (AD-4, AD-5).
- **Mark ≠ TRDPRC_1 is the whole point.** The wide table's mark column is `MARK` (a slot, fed
  by `MARK_FIELD_DEFAULT` = `MID_PRICE`); there is no `SETTLE` for these instruments. Keep mark
  and print distinct in color *and* symbol; keep the mark market-derived, not a model, or the
  interpolated sheet becomes model-vs-model; label interpolation as interpolation; never
  extrapolate; holes render as holes and never vanish (AD-9).
- **No visual literals outside `theme.py`** once FR-8 lands (AD-6).
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
