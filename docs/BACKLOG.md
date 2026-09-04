# Backlog — Options Surface Lab (Assignment 1.1)

The task-level build board. Requirement-level status stays in [PRD.md](PRD.md) §3/§12;
this file is the ordered "what's next" for every session.

**Rules:** work top-down within the current milestone; task IDs are stable (never renumber);
update status in the same session as the work (lockstep rule); PO-owned tasks are marked
**[PO]** — sessions may scaffold them but not complete them.

**Status:** ✅ done · ◐ in progress · ☐ todo · ⊘ blocked (blocker named)

---

## M0 — Foundations

| ID | Task | Maps to | Status |
|---|---|---|---|
| T-1 | Docs suite: PRD, SYSTEM-SPEC, ARCHITECTURE, CLAUDE.md | — | ✅ 2026-08-29 |
| T-2 | FR-1 restructure: package layout, rxconfig, entry shim, anchored paths, .gitignore (incl. app-key), requirements.txt, seed parsing tests | FR-1, G-1/2/7/8 | ✅ 2026-08-29 |
| T-23 | Exploration notebook `notebooks/01_data_exploration.ipynb` — consumes the package only; feeds FR-7 sentences + T-7 verification | AD-3 | ✅ 2026-08-29 |

## M1 — Runnable + real data (before Class 2 checkpoint)

| ID | Task | Maps to | Status |
|---|---|---|---|
| T-3 | Install pytest into `algo` env; confirm `pytest` runs the seed tests green | NFR-2 | ✅ 2026-08-29 — pytest 9.1.1 was already present in `algo`; suite green |
| T-4 | FR-3 transform tests: flatten (both MultiIndex orders), pivot, sparsity stats, nearest-prior-spot join — seeded synthetic panel as fixture. **Gate for all refactors.** | FR-3, NFR-2 | ✅ 2026-08-29 — `tests/test_transforms.py` (34) + `tests/conftest.py` fixtures; 40 green, 1 xfail (PRD OQ-5) |
| T-5 | First `reflex run` smoke test (scaffolds `.web/`, downloads JS toolchain): page loads, figures render, controls work. Completes FR-1 acceptance. | FR-1 | ◐ 2026-08-30 — ran; page + candlestick + controls OK, `.web/` scaffolded. Surfaced two defects (T-26, T-27); the option figures were never exercised against a populated panel. **Re-run once on the synthetic panel to close.** |
| T-26 | Make the cache-first pull *visible*: status badge names the path taken, amber callout + spinner while a pull runs, button disabled mid-load. `OSL_OFFLINE=1` forces synthetic for CI/export (NFR-4); `fetch_from_lseg()` refuses to overwrite an existing cache. Callout also fires when a panel has no settle side. | FR-2, NFR-4, AD-9 | ✅ 2026-08-30 |
| T-27 | Recover SETTLE and puts. **Puts solved 2026-08-30**: suffix takes the *call* month letter for both rights (`UUUUR122601100.U^F26`); 146 puts recovered, now the `build_option_ric()` default. **SETTLE still absent** — 0 non-null across 294 series. | FR-2, FR-6, AD-9 | ◐ |
| T-30 | Re-probe the mark field. **Answered 2026-08-30:** `SETTLE` is absent for expired US equity options under all 7 candidate names and is not in the field list these RICs return; control shows `SETTLE` works for `CLc1` in the same session. Available marks: `MID_PRICE`/`BID` 46.8%, `ASK`/`THEO_VALUE` 50.0%, `OPINT_1` 41.5% vs `TRDPRC_1` 36.8%; **121 of 920 contract-days have a mark and no print**. Exhibit + captured evidence: notebook 01 §10. | FR-2, FR-6 | ✅ 2026-08-30 |
| T-33 | Web/doc search for an alternative settle route — **closed 2026-08-30, no route exists**: `TR.SETTLEMENTPRICE` is futures-only, `TR.OptionSettlementPrice` does not resolve, `TR.CLOSEPRICE` is `TRDPRC_1` re-served (identical 356/356 after dedup; raw rows are padded repeats). LSEG's own expired-options article uses BID/ASK/TRDPRC_1. Notebook 01 §10a. | FR-2, FR-6 | ✅ 2026-08-30 |
| T-34 | Establish *why* no settle exists — **closed 2026-08-30**: no official close/settlement for US listed equity options is published by the exchanges, OPRA or the OCC. Not a data-access problem; every mark is derived (mechanical vs theoretical). Notebook 01 §10b. | FR-6, FR-7 | ✅ 2026-08-30 |
| T-32 | Adopt `MID_PRICE` as the mark. **Done 2026-08-30:** re-pulled with `TRDPRC_1, MID_PRICE, BID, ASK, OPINT_1` (296 series); wide-table slot renamed `SETTLE`→`MARK` with `has_mark`/`n_mark_only`/`pct_mark_no_trade`; plot + app labels name the source field; FR-6, AD-9, SYSTEM-SPEC updated. **Sign-off received 2026-09-01** — the revised README names `MID_PRICE` as the mark. | FR-6, AD-9 | ✅ |
| T-35 | Stop `pivot_trade_settle()` deleting rows with an unknown spot (checkpoint_audit §1) — pivot on `(date, ric)`, re-attach descriptors by merge. xfail removed, test strengthened. | AD-9, FR-3 | ✅ 2026-08-30 |
| T-36 | Default as-of = busiest date, not last. These are expired weeklies: the final date has one expiry alive (33 quotes, 6.1%) vs 216 quotes / 7 expiries mid-window (2026-07-10). Neutral criterion, every date still selectable. | FR-4, FR-6 | ✅ 2026-08-30 |
| T-40 | Adversarial review of the session's changes (15 agents, 37 candidates, 5 verified, 1 survived). Found: the demo script and audit doc quoted the median relative gap as **2.8%** — that was the *superseded* cache's as-of-2026-08-21 slice, carried into a panel-wide sentence. True panel figure is 4.6%; the on-screen card's 4.0% is the as-of slice and is correct. Also corrected an open-interest pair that mixed two row populations (166 vs 28 → 157 vs 28). No code defects survived review. | NFR-2 | ✅ 2026-08-31 |
| T-39 | Bid-ask spread as the trust layer: `spread`/`spread_pct` on the wide table, `median_spread`/`median_spread_pct`/`pct_spread_over_half` in `summarize_sparsity()`, `spread_heatmap()` figure + page slot + preview + metric card. Answers "can I believe this mark?" where occupancy only answers "does a number exist?". Sets up 1.2's fills — filling at mid is optimistic by ~half the spread. Note: keeping BID/ASK adds 244 one-sided quote days to the FR-6 denominator (7,214 → 7,458, 22.2% → 21.5%); a contract quoted with an ask but no bid was still listed. +5 tests. | FR-6, AD-9, FR-11 | ✅ 2026-08-31 |
| T-38 | `surface_grid()` crashed with `QhullError` on a single-expiry slice (flat cloud — the last date of a weeklies panel always is). Degenerate input now returns no sheet instead of raising, per AD-9. This killed `build_preview.py` outright. +3 tests. | AD-9, FR-3 | ✅ 2026-08-30 |
| T-37 | `tests/test_app_figures.py` — smoke tests over the app→plot call sites. Added after a kwarg rename desynced them with no test failing. | NFR-2 | ✅ 2026-08-30 |
| T-31 | **[PO]** Instructor question: the README's expired-contract suffix rule ("repeats the month letter", `^R26` for puts) returns **zero** data; puts require the call letter (`^F26`). Demonstrable live — both forms are one `build_option_ric(..., put_suffix=)` call apart. | — | ☐ |
| T-29 | Acquisition hardening (found while staging T-27): normalise all four `get_history` column shapes to `(RIC, Field)`; stop the per-RIC fallback losing identity and being deduped away; keep requested-but-empty fields instead of collapsing the frame; `build_option_ric`/`build_candidate_rics` in utils as the tested inverse of `parse_option_ric`; additive `diagnostics` payload key. +29 tests (`test_ric_building.py`, `test_acquisition.py`), 69 green. | FR-2, AD-2, AD-3, NFR-2 | ✅ 2026-08-30 |
| T-6 | **[PO]** Pre-flight: confirm UUUU had no split in the 12-week window (OQ-3); if split, pick a new root and update constants | FR-2 | ✅ 2026-08-31 — **no split.** Three checks: largest overnight move +10.2% (a 2:1 split reads ~0.50); strike grid clean on the $0.50 step, $10.50–$18.50, across every expiry (adjusted contracts produce off-grid strikes); and every open-market Friday returned option data — the only gaps are 06-19 (Juneteenth) and 07-03 (Independence Day observed), both market closures. PO closed on this evidence. |
| T-7 | **[PO + session]** One-time LSEG pull per [RUNBOOK.md](RUNBOOK.md) §3; verify payload; do NOT commit until T-8 exists and `.gitignore` is confirmed active | FR-2 | ✅ 2026-08-31 — 296 series (148 calls + 148 puts), `TRDPRC_1, MID_PRICE, BID, ASK, OPINT_1`, committed in `afe99ca`. **Ran out of order:** the first pull fired unsupervised during T-5 *before* T-6's split check; T-6 has since confirmed no split retroactively, so the committed panel is sound. Two superseded pulls kept locally as evidence. |
| T-8 | `git init`, first commit, create GitHub repo, push. Verify `lseg-data.config.json` is untracked **before** the first push. | FR-9 (partial) | ✅ 2026-08-31 — `Jason-Dorman/options-surface-lab`, commit `afe99ca`, 31 files. Secret verified absent from all history. Committed binaries: `option_pipeline_data.pkl` (876 KB) + `.synthetic.pkl` (601 KB) + `options_surface_preview.html`; the two superseded evidence pulls are gitignored and kept locally. |
| T-9 | De-risk deploy early: skeleton `reflex export` + Pages workflow with base-path config; incognito check. (Risk table: do NOT leave this for Sep 04.) | FR-9 | ◐ 2026-08-31 — **plumbing done, page blank.** CI green: pytest in a clean no-credentials container (NFR-4 proven), `reflex export` on Node 22, base path correct, deploy live at https://jason-dorman.github.io/options-surface-lab/. But the bundle bakes `ws://localhost:8000/_event`; on Pages hydration fails and the tree unmounts. **Blocked on the instructor** — DEMO-SCRIPT q5. |
| T-41 | **[PO]** Resolve the deployment model with the instructor. | FR-9, AD-4, AD-5 | ✅ 2026-09-01 — **(c) static page.** Pages serves one self-contained `index.html`, built from the committed pickle at build time; no backend, no run-time pickle read. Workflow reworked to `build_preview.py`. Consequences: T-14 superseded, T-15 promoted to critical path, `frontend_path` removed. |
| T-24 | Checkpoint exhibits in notebook 01 (§8): live RIC-grammar demo + settle-no-print table; notebook is the demo deep-dive tab | AD-3 | ✅ 2026-08-29 |
| T-10 | Checkpoint prep + demo | M1 | ✅ 2026-09-01 — demo delivered. **Instructor conceded SETTLE is not available at the endpoint** (took some convincing; the evidence pack did the work). What replaces it is still outstanding — see T-32/T-42. |

> **Note 2026-09-01 — provenance of four constraints.** The revised README (Canvas only, no
> `.md` provided) dropped its "What the 3D plot is doing", "Files in this lab", "Stretch (not
> required)" and "Do not" sections. **[PO] elected to keep them as build constraints anyway.**
> They are therefore *our* standards now, not the instructor's: the `*app.py` / `*utils.py` /
> `*plot.py` layout, the interpolation warnings, and the do-not list all still bind, but cite
> them as project decisions rather than as assignment requirements.

## M2 — Rubric complete (~Sep 02)

| ID | Task | Maps to | Status |
|---|---|---|---|
| T-42 | With SETTLE confirmed unavailable, what fills the mark slot? | FR-6, AD-9 | ✅ 2026-09-01 — **`MID_PRICE`, named by the revised README.** The brief now defines it as the closing NBBO midpoint and states LSEG exposes no settlement price for these contracts. No code change: `MARK_FIELD_DEFAULT` was already `MID_PRICE`. Labels that still say "mark" may now say "mid". |
| T-11 | Display the settle-no-trade **percent** on the page (currently computed, not shown) | FR-6, G-3 | ✅ 2026-09-01 — "Mark, no print" card now shows count **and** percent in both the Reflex app and the published page. Field-agnostic: it reads from the MARK slot, so it re-computes if the mark field changes. |
| T-12 | Commentary block under the 3D figure; **[PO]** writes the three sentences (sessions scaffold placement only) | FR-7, G-4 | ☐ |
| T-13 | **[PO decision]** Pick graphical-identity direction (create DESIGN-BRIEF.md at that point); then build `theme.py`, strip all hardcoded hex/fonts from plot + app, verify settle/trade stay distinct | FR-8, G-5 | ✅ 2026-09-02 — **[PO] chose a deep-navy terminal: amber type, Space Grotesk + JetBrains Mono, and a numbered-panel grid layout.** [DESIGN-BRIEF.md](DESIGN-BRIEF.md) records it; `theme.py` implements it. All 138 hex/font literals gone from `option_surface_plot.py`, `options_surface_app.py` and `build_preview.py` — `tests/test_theme.py` greps for them, so the acceptance criterion is executable rather than eyeballed. README's cyan-mark / magenta-print encoding kept and asserted by hue; puts take the hues furthest from their own call (violet for the mark, green for the print) with the glyph encoding role not right (circle = mark, diamond = print), all markers filled; the mark-vs-print scatter draws named Calls/Puts traces with a legend rather than one array-coloured trace. Amber is type only, never data — asserted. Layout replaced the single scroll of full-width cards with a command bar, a readout strip and numbered panels on a hairline grid, 10-column grid — hero surface at 6 cols with the underlying beside it at 4 for spot context (PO's call, 2026-09-02; started 7/3, widened to 6/4 the same day), remaining four figures 5+5 (`as_panel_figure()` hands each tiled figure's title to its panel header). Reflex app and published page render the same chrome. **First pass was corrected by the PO on both counts** — "Bloomberg" meant layout, not palette, and the ice-blue type had to go; see DESIGN-BRIEF §8. WCAG AA measured and asserted on every rendered pairing. **Consequence:** the published page now reaches Google Fonts as well as the Plotly CDN — the self-containment guard was widened to those two hosts (DESIGN-BRIEF §7). +42 tests, suite now 138 green. **PO review 2026-09-02 caught three defects** — unreadable put markers, puts that read as missing on the scatter, and dead vertical space in the hero row; all three fixed and pinned by tests (DESIGN-BRIEF §8). |
| T-14 | ~~Import-time baking into State defaults~~ | AD-4 | ⊘ **superseded 2026-09-01.** Existed only to populate Reflex State for the static export. The published artifact is now a build-time-rendered HTML page with no Reflex runtime, so there is no State to bake. No work required. |
| T-15 | Static interactivity for the published page | FR-4/5, AD-5 | ✅ 2026-09-01 — `static_surface_figure()`: **an as-of slider over all 53 trading days** (308 pre-built traces) plus legend toggles for MID_PRICE / TRDPRC_1 / the interpolated sheet, calls and puts. Puts open as `legendonly`. Date is a slider and the right is on the legend *because* Plotly buttons apply a fixed visibility array and cannot read another menu's state — two menus would fight; the legend is orthogonal. **[PO] chose full coverage over page weight: 2.4 MB, ~308 traces.** `curated_asof_dates()` remains the trim lever if that proves too slow. +8 tests. |

## M3 — Stretch (committed; ~Sep 03; cut before M4 slips)

| ID | Task | Maps to | Status |
|---|---|---|---|
| T-16 | Moneyness axis toggle (K ↔ K/S) incl. static variant; add a moneyness section to notebook 01 (co-build policy) | FR-10 | ☐ |
| T-17 | IV inversion in utils (+ round-trip test) + IV figure with assumptions caption; **[PO]** picks the constant rate (OQ-2) | FR-11 | ☐ |
| T-25 | `02_iv_surface.ipynb` co-built with T-17: where inversion degenerates (sub-intrinsic, near-expiry), rate sensitivity | FR-11, AD-3 | ☐ |
| T-18 | Spot plane overlay at K = S, toggleable | FR-12 | ☐ |

## M4 — Ship (Sep 04, before midnight)

| ID | Task | Maps to | Status |
|---|---|---|---|
| T-19 | Finalize CI: pytest → `build_preview.py` → Pages on push; green on clean clone | FR-9, NFR-4 | ◐ shipped 2026-08-31, verify once more before submission |
| T-20 | Incognito verification of the live Pages URL (figures, toggles, numbers, sentences) | FR-9 | ☐ |
| T-21 | README how-to-run section (alongside, never replacing, the assignment brief) + Canvas submission | FR-9 | ☐ |
| T-22 | Final sweep: PRD §12 definition-of-done + docs-lockstep audit | all | ☐ |
