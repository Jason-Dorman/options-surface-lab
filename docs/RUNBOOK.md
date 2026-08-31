# Runbook — Options Surface Lab

Operational procedures. Commands are **Git Bash** syntax (the PO's terminal).
Items marked *verify on first use* are documented from design, not yet exercised — update
them with what actually happened (lockstep rule).

---

## 1. Environment — the three-Pythons trap

This machine has three `python`s; only one is right:

| Where | What you get | Verdict |
|---|---|---|
| Git Bash `python` / `python3` | WindowsApps store stub → **Permission denied** | ✗ |
| PowerShell `python` | conda `base`, Python **3.8.5** | ✗ wrong version |
| conda env **`algo`** | Python **3.12.13**, reflex 0.9.8, pandas/numpy/scipy/plotly | ✓ use this |

Activate in Git Bash:

```bash
source /c/Users/rjd61/anaconda3/etc/profile.d/conda.sh && conda activate algo
# or call it directly without activating:
/c/Users/rjd61/anaconda3/envs/algo/python --version   # → Python 3.12.13
```

In VS Code: `Ctrl+Shift+P` → **Python: Select Interpreter** → `algo` — fixes the editor's
"package not installed" hints and sets the default notebook kernel.

One-time dev deps for `algo` (nbformat is required for plotly figures to render inline in
notebooks — without it every figure cell throws `Mime type rendering requires nbformat`):

```bash
python -m pip install pytest ipykernel nbformat    # with algo active (tests + notebooks)
# verified present in `algo` on 2026-08-29 (pytest 9.1.1) - re-run only on a fresh env
```

## 2. Everyday commands

Run everything **from the repo root**.

```bash
python build_preview.py    # static HTML preview → options_surface_preview.html (verified)
python -m pytest tests/ -q # test suite - 76 tests, all green (no xfail since 2026-08-30)
reflex run                 # local dev server — see §4 for first-run expectations
```

No real cache present → the app/preview run on the **synthetic panel** and say so in their
banner. That is expected until T-7.

Data exploration: open `notebooks/01_data_exploration.ipynb` in VS Code (kernel: the `algo`
env; needs the `ipykernel` install above). It runs on whatever cache state exists.

## 3. The one-time LSEG pull (FR-2 / T-7) — handle with care

This is the build's only unrepeatable, credential-dependent step. It runs **once**; the
committed pickle serves everyone afterward (AD-1).

**Preconditions**

- [ ] T-6 done: UUUU had **no split** inside the 12-week window (if it did: new root, update
  constants in `options_surface_app.py`, re-check). Splits make the synthetic RICs silently
  miss adjusted contracts.
- [ ] LSEG Workspace desktop app **running and logged in** on this machine.
- [ ] `lseg-data.config.json` present at repo root (holds the app-key — gitignored, never commit).
- [ ] `python -c "import lseg.data"` succeeds in `algo` (install `lseg-data` if not).
- [ ] `option_pipeline_data.pkl` does **not** exist (the loader short-circuits if it does).

**Run** (from repo root, `algo` active):

```bash
python -c "from options_surface_lab.options_surface_app import load_or_fetch_pipeline_data as f; p = f(); print(p['fetched_at'], 'synthetic =', p['synthetic'], p['options'].shape)"
```

Expect **tens of minutes**: ~1–2k candidate RICs in batches of 25, most returning empty
(they never existed — normal), failed batches degrading to single-RIC retries. If it is
painfully slow, the sanctioned optimization is banding strikes per expiry (README hint;
optional code change in the pull function).

**Verify before committing** — all must pass:

```bash
python - <<'EOF'
import pickle
p = pickle.load(open("option_pipeline_data.pkl", "rb"))
assert p.get("synthetic") is False, "pull produced a synthetic payload?!"
print("stock rows:", len(p["stock"]), "| options shape:", p["options"].shape, "| fetched:", p["fetched_at"])
EOF
python build_preview.py    # banner must say 'loaded from option_pipeline_data.pkl', figures must look sane
```

Then eyeball the preview: settles clustered near the money, sparse trade diamonds, dark
heatmap wings. For a richer check, re-run `notebooks/01_data_exploration.ipynb`
top-to-bottom against the new pickle. Only then `git add option_pipeline_data.pkl` (after T-8; confirm
`git status` does NOT list `lseg-data.config.json`).

**Never** delete or re-pull a committed cache on your own judgment — PO approval first,
and rename the old file rather than overwriting (CLAUDE.md hard constraint).
`fetch_from_lseg()` enforces this: it refuses to run when `option_pipeline_data.pkl` exists
unless you pass `overwrite=True`.

**What the next pull answers by itself (T-27).** After the 2026-08-30 pull came back with no
settles and no puts, acquisition now probes instead of assuming:

- Puts: **settled 2026-08-30.** The suffix takes the *call* month letter for both rights
  (`UUUUR122601100.U^F26`), not the README's "repeats the month letter" (`^R26`, which
  returns nothing). That is now the `build_option_ric()` default; the pull still falls back
  to the README form and records which one worked.
- If `SETTLE` is empty, candidate mark fields are probed against RICs *already proven to
  return data*. Each candidate is requested **paired with TRDPRC_1** — an absent field
  raises `LDError` rather than returning empty, so an unpaired probe answers nothing (that
  is exactly how the first attempt failed). If one wins, the universe is re-fetched with it
  and aliased back to `SETTLE`.
- To re-probe without spending a pull: `probe_mark_fields()` is read-only and writes nothing
  (notebook 01 §9 cell B).
- **Settled 2026-08-30: there is no settle.** `SETTLE` is absent from the 22 fields these RICs
  return (one identical field set across 14 RICs, 7 expiries, both rights), and all seven
  settle-ish names come back zero across all 294 series × 53 days. Control: `SETTLE` returns 15 values
  for `CLc1` in the same session — the field works, expired equity options just don't have
  one. The available marks are `MID_PRICE`/`BID` (46.8%), `ASK`/`THEO_VALUE` (50.0%) and
  `OPINT_1` (41.5%) against `TRDPRC_1`'s 36.8%; **121 of 920 contract-days carry a mark with
  no print**, which is the FR-6 thesis on a different field.
- **Checkpoint exhibit: notebook 01 §10.** Runs against the live session when Workspace is up
  and falls back to `notebooks/settle_field_evidence.json` when it isn't, so the proof still
  renders on a dead network. Re-capture the evidence only if the window changes.
- Everything lands in `payload["diagnostics"]`. Read it first:

```bash
python -c "import pickle; print(pickle.load(open('option_pipeline_data.pkl','rb'))['diagnostics'])"
```

Expect `put_suffix_style` ∈ {`right`, `call`, `neither`} and `settle_field_used`. If it says
`neither` / no winning field, that is the FR-2 scope conversation, not a bug to retry.

## 4. First `reflex run` (T-5) — *verified 2026-08-30, with findings*

From repo root with `algo` active: `reflex run`. First run scaffolds `.web/` and downloads
the JS toolchain — allow several minutes and disk noise; subsequent runs are fast. Expect
frontend at `http://localhost:3000` (backend on 8000). Stop with Ctrl+C.

Smoke checklist: page loads · candlestick + 3D surface render · as-of/C-P selects and the
three toggles respond · metrics populated.

**Surprises from the first run — read before the next one:**

1. **The first page load ran the LSEG pull — silently.** Cache-first-then-pull is the
   intended FR-2 behaviour and is retained; the defect was that it was invisible and that it
   ran ahead of the T-6 split pre-flight. T-26 fixes the visibility: the status badge, an
   amber callout and a spinner all announce the pull *before* it blocks, because for ~90 s
   the page read "Ready" with every metric at 0 and an empty as-of select — indistinguishable
   from a failed load. `OSL_OFFLINE=1` forces the synthetic path (CI/export, NFR-4), and
   `fetch_from_lseg()` refuses to overwrite an existing cache.
   **Still do T-6 before letting a pull run.**
2. **RIC construction is not the problem.** Verified offline against README Appendix A: put
   month codes M–X are generated correctly for all twelve months, and the expired-contract
   suffix matches the documented grammar. Both rights were requested. Note the README's
   Appendix A example (`UUUUA1502601250.U^A26`) carries one digit too many and does not
   parse; the nine-digit form does, and matches the RICs the API accepted — raised in
   [checkpoint_audit.md](checkpoint_audit.md), README is instructor-owned so it stands.
3. **That pull had no SETTLE at all** — 148 RICs, TRDPRC_1 only, calls only, 9 weeklies
   2026-06-12…08-21. `fields` *did* request SETTLE; it came back all-NaN and acquisition's
   `dropna(how="all", axis=1)` dropped it, collapsing the column MultiIndex to one level.
   Every settle metric therefore read 0 and the SETTLE occupancy panel was fully dark —
   a data defect, not sparsity. The artifact is kept as
   `option_pipeline_data.trdprc-only.pkl`; diagnosis is T-27 (notebook 01 §9).
   The app now raises an amber callout whenever a panel has no settle side.

Because the option figures were never exercised against a populated panel, **T-5 stays ◐**
until one clean re-run on the synthetic panel confirms the surface, comparison and heatmaps
render with data.

Troubleshooting: port already in use → `reflex run --frontend-port 3001`; toolchain
download blocked by firewall → rerun on a different network; anything importing
`options_surface_lab` fails → you are not at repo root or not in `algo`.

## 5. Export & deploy to GitHub Pages (T-9 / T-19) — *verify on first use*

- `reflex export --frontend-only` produces the static frontend bundle.
- **Base path is the known trap:** project Pages serve under `/<repo>/`; the exact
  mechanism to make the export respect that (config `deploy_url` / post-processing the
  bundle) must be pinned during T-9 — do it with a skeleton deploy days early, not on
  Sep 04. Acceptance is always the same: the Pages URL renders in an **incognito** window
  with working client-side toggles.
- CI shape (T-19): on push → pytest (clean env, no creds — proves NFR-4) → export → deploy
  to Pages.
- **Emergency fallback:** `python build_preview.py` output is a self-contained page;
  publishing it to Pages satisfies "the site renders" if the Reflex export misbehaves near
  the deadline.

## 6. Quick troubleshooting

| Symptom | Cause → fix |
|---|---|
| `Permission denied` running `python` in Git Bash | WindowsApps stub → §1 activation |
| Syntax/typing errors on run | You're on conda base 3.8 → §1 |
| App shows SYNTHETIC banner unexpectedly | `option_pipeline_data.pkl` missing/misnamed at repo root |
| `pytest` can't import the package | Run from repo root (root `conftest.py` provides the path) |
| Empty figures on the deployed site | Base path wrong, or import-time baking (T-14) not in place |
| Pull returns almost nothing | Workspace not running/logged in; or split (T-6); or wrong root |
