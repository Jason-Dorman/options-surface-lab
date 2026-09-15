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
python -m pytest tests/ -q # test suite
reflex run                 # local dev server — see §4 for first-run expectations
```

**Editing the three sentences (FR-7).** They live in `options_surface_lab/commentary.py` and
nowhere else — fill in `SENTENCES`, then `python build_preview.py` to see them on the page.
Both the published page and `reflex run` read that module, so there is nothing to keep in
sync. Leave one empty and the page prints `[unwritten]` in red, `pytest` fails, and the
Pages workflow refuses to deploy — on purpose: it is the one graded element with no figure
to prove it is there.

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

Smoke checklist: page loads · candlestick + 3D surface render · as-of / C-P / **X-axis**
selects and the three toggles respond · metrics populated. The X-axis select (FR-10, T-16)
swaps the surface's X between raw strike and `K / S`; everything else about the figure must
stay put when it moves.

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
   parse; the nine-digit form does, and matches the RICs the API accepted — raised with the
   instructor at the Class-2 checkpoint; README is instructor-owned so it stands.
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

## 5. Deploy to GitHub Pages — *live since 2026-09-01*

**https://jason-dorman.github.io/options-surface-lab/** — published by
`.github/workflows/pages.yml` on every push to `main`.

The published site is **one self-contained `index.html`**, written by `build_preview.py`.
Python reads the committed pickle *at build time* in CI, renders the Plotly figures, and
embeds their data as JSON. The browser never reads a pickle; there is no server at run time.
The revised README sanctions this directly: *"you can serve it as an html file … probably
simplest."*

```
push to main
  → pytest in a clean container, no credentials      (proves NFR-4)
  → python build_preview.py → _site/index.html
  → guards: refuse a synthetic build; refuse < 7 figures;
            refuse an IV panel with no assumptions caption;
            refuse an unwritten FR-7 sentence
  → deploy-pages
```

- **`options_surface_preview.html` is a committed artifact — rebuild it in the same commit as
  anything that changes what the page says.** The tests read that file, so a source change
  without a rebuild fails CI on the *old* page. This bit on 2026-09-06: FR-7's three sentences
  were written into `commentary.py` and committed, the page was not rebuilt, and the Actions
  run failed on a page still reading `[unwritten]`. `python build_preview.py`, then commit
  both.

- **`reflex export` is not used.** Its bundle bakes `ws://localhost:8000/_event` and needs a
  live Python backend; on Pages hydration fails and the page renders blank. Measured
  2026-08-31 — see AD-4. The Reflex app stays as the local dev app.
- **The guards matter more than they look.** A build that silently fell back to the synthetic
  panel would deploy a page that renders beautifully and invents settles that do not exist.
  The workflow fails instead. Do not weaken them to get a green run.
- **FR-4/FR-5/FR-10 are met without a backend.** The hero 3D figure carries three controls,
  all of them figure JSON, so they work on a static host:
  * an as-of **slider** over all 53 trading days (T-15), which **drives the whole page** —
    scatter, spread grid, both occupancy grids, the six readouts and the command bar's as-of
    (T-42). The underlying candlestick is the deliberate exception: it is 12 weeks of context,
    not an as-of cut.
  * the **legend**, toggling MID_PRICE / TRDPRC_1 / the interpolated sheet for calls and puts
    (puts start hidden) — and FR-12's **spot plane** at `K = S` (T-18), which opens visible
    and is the seventh entry, so the legend now wraps to two rows.
  * an **X-axis dropdown**, strike ↔ `K / S` (T-16). It composes with the slider because the
    two write disjoint properties — the steps write `visible`, the menu writes `x`.

  Panel **[3]**, FR-11's IV smile, is driven by **both** of those (T-17, T-43): the frames
  payload carries a complete smile per `(date, ruler)` pair, and the listener restyles its
  per-expiry traces by index. It has no menu of its own — it learns the ruler from the hero's
  `plotly_buttonclicked`. The assumptions it renders under are fixed, not chosen: a reader who
  could change the rate would be reading a different figure than the caption describes.

  **Both 3D/2D panels open on Strike (K)**, matching the hero's `updatemenus` `active=0`, so
  the whole page is in dollars at load.
- **The page is ~3.05 MB (≈1.05 MB gzipped) and carries ~370 traces**, in seven panels.
  T-17's IV cloud added ~130 KB of that and FR-12's 48 spot planes ~35 KB (48, not 53: the
  panel's last five days have a single expiry alive, so there is no box for a wall to span —
  see SPEC §12). That is deliberate: the
  PO chose full date coverage over load time (AD-5), and FR-10's second x array per trace adds
  ~205 KB raw / ~70 KB gzipped on top. If it ever needs slimming, pass explicit dates —
  `static_surface_figure(wide, dates=curated_asof_dates(wide, n=10))` — rather than dropping
  figures or controls.
- Acceptance is unchanged: the Pages URL renders in an **incognito** window with working
  client-side controls.
- **Checking the published page for real.** `pytest` asserts against the figure JSON; it
  cannot click anything, and every bad defect on this project has been deploy-only. To drive
  the built page in a browser, build a **throwaway** venv — do not install Playwright into
  `algo`, it bumps `pyee` past `lseg-data`'s pin and breaks the LSEG import:

  ```bash
  python -m venv /c/Users/rjd61/AppData/Local/Temp/oslpw     # short path: long paths fail here
  /c/Users/rjd61/AppData/Local/Temp/oslpw/Scripts/python -m pip install playwright
  /c/Users/rjd61/AppData/Local/Temp/oslpw/Scripts/python -m playwright install chromium
  ```

  Load `options_surface_preview.html` over `file://`, wait for `window.Plotly`, then read
  `gd._fullData[i].x` — **not** `gd.data[i].x`, which plotly.py may ship as base64 binary
  (`{dtype, bdata}`) rather than a JSON array. Used on 2026-09-04 to verify FR-10 end to end,
  the same day for FR-11's panel following the as-of slider, and again for FR-12's plane.

  Driving the hero's own controls: the as-of slider responds to a real click on
  `rect.slider-rail-touch-rect` (a synthetic `plotly_sliderchange` would test the listener
  and not plotly's own visibility pass), and the X-ruler chip is a *closed dropdown* — click
  `.updatemenu-header-group rect` to open it, then the row in
  `.updatemenu-dropdown-button-group` whose text matches the mode.

  **And take a screenshot, not only measurements.** T-18's assertions were all green while
  the hero's caption was printing over a legend that had just wrapped to two rows; nothing
  short of looking at the picture would have caught it.

  **Audit the WIDTHS, not just one.** `reflex run` and a 1600px browser agree with each
  other and with nothing else. Load the built page, step the viewport through
  1920 / 1600 / 1440 / 1366 / 1280 / 1200 / 1101 / 1099 / 1024 / 900 / 820 / 768 / 600 / 430,
  and at each width check: does the document scroll sideways; does anything overflow its
  panel; do a figure's own title / legend / axis-menu boxes overlap each other or fall
  outside the figure; does a panel header wrap (which leaves its row ragged); are readout
  labels truncated. That sweep found 131 defects on a page that looked perfect at 1600px,
  including one present at every width since T-13 (T-47). The three bands to check either
  side of are `BREAK_TWO_COL` (1400) and `BREAK_ONE_COL` (1100).

  **Never compare a thing against something it produced.** T-18's drive checked that the spot
  plane did not reach past `scene.zaxis.range` — the range plotly had autoranged *from the
  plane*. It passed while the plane was stretching that axis on 34 of 53 dates (T-46). Compare
  against the other traces the step lights, and walk **every** step: three sampled dates hid a
  defect present on two thirds of them.

## 6. Quick troubleshooting

| Symptom | Cause → fix |
|---|---|
| `Permission denied` running `python` in Git Bash | WindowsApps stub → §1 activation |
| Syntax/typing errors on run | You're on conda base 3.8 → §1 |
| App shows SYNTHETIC banner unexpectedly | `option_pipeline_data.pkl` missing/misnamed at repo root |
| `pytest` can't import the package | Run from repo root (root `conftest.py` provides the path) |
| Empty figures on the deployed site | Base path wrong, or import-time baking (T-14) not in place |
| Pull returns almost nothing | Workspace not running/logged in; or split (T-6); or wrong root |

## 7. The live leg — Monday's entry and Friday's settlement (FR-21, T-78/T-80)

The strategy run forward with simulated capital. `options_surface_lab/covered_call/live.py`.

**This is not a race.** T-62 proved LSEG serves hourly `BID`/`ASK` *history* for a live,
unexpired weekly, so the 15:00–16:00 ET bar is read **after it completes**. The bar is
immutable: 16:05 or 21:00 the same evening books the identical trade, and nothing after
16:00 enters the decision. You do not need to be at the desk at the close.

**Preconditions**

- [ ] LSEG Workspace running and logged in (same as §3).
- [ ] The 15:00–16:00 ET bar has closed — so any time after **~16:05 ET**, the same day.
- [ ] `conda activate algo`, run from the repo root.

**Monday — book the entry**

```bash
python -m options_surface_lab.covered_call.live enter
```

It prints the bar it read, then the rows it booked. Defaults are the SD decisions, so no
flags are needed: `--expiry` defaults to this week's Friday and the entry session is read
**off the tape** (DR-7), not computed as "Monday" — on a holiday week it finds Tuesday by
itself.

Expect two rows when flat (`BUY` 100 shares, `SELL` 1 call) or one row when shares are
already held from an OTM week. Expect a **skip** and nothing booked if the chosen strike has
no valid two-sided quote — that is DR-1 and it is correct behaviour, not a failure. **Do not
re-run it to get a different answer.** A second run on the same session is refused, both for
booked rows and for an already-logged skip.

**Friday — settle**

```bash
python -m options_surface_lab.covered_call.live settle
```

Reads the expiry session's closing bar, then books `EXPIRE` (kept shares) or
`ASSIGN` + a stock `SELL` at the strike. Settlement needs no option quote.

**Verify, then hand to the PO**

```bash
python -c "import json; s=json.load(open('covered_call_live.json')); \
print(s['cash'], s['position']); [print(r) for r in s['blotter']]"
pytest tests/covered_call -q
```

`covered_call_live.json` is **data the page renders**, so it is committed. Cash must
reconcile against the blotter alone (I-1): `cash == start_cash + Σ cash_delta`.

**Rehearse without touching the real book** — point it at a scratch file and an expired week:

```bash
python -m options_surface_lab.covered_call.live enter \
  --expiry 2026-09-11 --state /tmp/dryrun.json
```

*(Dry-run 2026-09-13 against the expired 09-11 chain: entered Tue 09-08 15:00 at
S=718.41, wrote the 719 call at mid 4.80, settled 09-11 at 714.87 → `EXPIRE`, shares kept.
Identical to what the rules module produces over the same tape.)*

| Symptom | Cause → fix |
|---|---|
| `SKIP_NO_STOCK_PRINT` | The 15:00 ET bar is not on the tape yet — you ran before ~16:05 ET, or the market was shut. Wait and re-run; nothing was booked. |
| `SKIP_NO_QUOTE` | The strike had no valid two-sided quote at the bar. **Correct behaviour** (DR-1). It is logged, not booked. |
| `SKIP_NO_STRIKE` | The chain came back empty — check `diagnostics.option_error` in the state file, and that the expiry is a real trading Friday. |
| `LSEG session did not open (state OpenState.Closed)`, or a handshake `ReadTimeout` | **Workspace is running but not answering the app-key handshake** — see §9. Nothing was requested and nothing was written. |
| `REFUSED: … already has …` | The week is already booked or already skipped. Working as intended. |

## 8. The one-time tape pull — Assignment 2 (FR-13, T-56/T-77)

The backtest's data: `QQQ.O` and the near-the-money weekly calls of the window, hourly, into
`covered_call_tape.parquet` + `covered_call_tape.meta.json`. Same discipline as §3 — **one
human-invoked pull, committed, never repeated**. `options_surface_lab/covered_call/tape.py`.

**Preconditions**

- [ ] LSEG Workspace running and logged in.
- [ ] `conda activate algo`, run from the repo root. **`pyarrow` must be installed** — it is
      in `requirements.txt`; `python -c "import pyarrow"` is the check.
- [ ] `covered_call_tape.parquet` does **not** exist. The pull refuses an existing one, by
      design; if you mean to replace it, rename the old one first and tell the PO.
- [ ] `OSL_OFFLINE` is not set to `1` (the pull refuses to run under it).

**Pull it**

```bash
python -m options_surface_lab.covered_call.tape fetch
```

Expect **several minutes**. It requests one chain per week, on the $1.00 step T-62 measured,
padded four strikes either side of *that week's* own range — and it asks for each contract
under **both RIC forms**, because a contract's form depends on how long ago it expired and
that boundary is not ours to predict (SPEC §3.3). A batch the API rejects outright is retried
one RIC at a time (AD-2), so a few hundred requests is normal, not a symptom.

**Verify before committing** — the pull prints this, and `… tape inspect` reprints it:

```bash
python -m options_surface_lab.covered_call.tape inspect
```

| Check | What good looks like |
|---|---|
| Weeks | One line per ISO week of the window, each with an entry day and an expiry day. A Friday holiday shows a **Thursday** expiry (DR-7) — that is right, not a bug. |
| Contracts per week | Tens, not zero. A week with 0 contracts means its chain did not resolve; check `diagnostics.errors` in the sidecar before accepting it. |
| RIC forms | Both `expired` and `live` may appear. The most recent weeks answering only `live` is exactly what T-62 predicted. |
| Mids | A large majority of near-the-money option bars should carry a valid mid. A tape where most bars have none makes every week a skip — stop and ask the PO. |
| `synthetic=False` | Anything else and the page will refuse to publish (SPEC §11). |
| Accounting | The `contracts:` line must add up — *answered + refused = requested*. Every RIC that returned nothing is named in `diagnostics.unanswered`; a gap there means contracts went missing inside a batch that answered only partly. |
| Soft failures | Expect hundreds. `LDError … No data` is a strike that never listed. `TypeError: 'UniverseContainer' object is not subscriptable` is a library-side batch failure — harmless, because AD-2's retry re-asks each RIC singly (7 of them on the 2026-09-15 pull, all recovered). |

*(2026-09-15: the pull took ~25 minutes and returned 37,857 bars / 952 contracts. The
band asks for ~100 strikes a week — wider than the week really traded, because thin
extended-hours bars carry erroneous `LOW_1`/`HIGH_1` ticks. That is deliberate: too wide
costs requests that fail soft and are recorded, too narrow silently omits the strike the
rule needed.)*

Then hand it to the PO with the sidecar: **both files are committed together**, and the
sidecar is what a reader uses to trust the bars (fields requested, the `ts` convention, the
discovered strike step, per-week counts, which RIC form answered per contract).

```bash
pytest tests/covered_call -q
```

| Symptom | Cause → fix |
|---|---|
| `FileExistsError` | A tape is already there. That is the guard working — caches are data artifacts (CLAUDE.md). |
| `RuntimeError: OSL_OFFLINE=1` | You are in a shell that sets it (CI does). Unset it for a real pull. |
| `RuntimeError: No QQQ.O bars returned` | Workspace is not logged in, or the window is wrong. **Nothing was written** — fix and re-run. |
| A week with 0 contracts | Its expiry may not be a real listed date. Check the week's `expiry_day` against the stock tape, and `diagnostics.errors`. |
| `LSEG session did not open (state OpenState.Closed)`, or a handshake `ReadTimeout` | **Workspace is running but not answering the app-key handshake** — see §9. Nothing was requested and nothing was written. |
| `ModuleNotFoundError: pyarrow` | `pip install pyarrow` inside `algo`. |

## 9. When Workspace is open and the API still will not connect

*Found 2026-09-14, on T-77's first pull attempt.* **"Workspace is running" is not the
check.** The Data API Proxy is a separate piece: it can be listening, healthy and reporting
`ST_PROXY_READY` while the desktop behind it never completes the app-key handshake. What that
looks like is a 20-second `ReadTimeout` on `http://localhost:9000/api/handshake`, repeated on
every retry, with no error from the desktop at all.

**Diagnose in this order** — each line separates one cause from the next:

```bash
# 1. Is the proxy listening, and which port does Workspace advertise?
cat "$LOCALAPPDATA/../Roaming/Refinitiv/Data API Proxy/.portInUse"   # normally 9000

# 2. Is the proxy healthy? ST_PROXY_READY = the proxy is up. It says nothing about login.
curl -s http://localhost:9000/api/status

# 3. Does a session actually open? open_session() does NOT raise when it fails —
#    it logs and leaves a closed session behind, which is why this prints the state.
python -c "import lseg.data as ld; ld.open_session(); print(ld.session.get_default().open_state); ld.close_session()"
```

| What you see | What it means → do this |
|---|---|
| Step 2 fails / connection refused | The proxy is not running. Start Workspace and wait for it to finish loading. |
| Step 2 says `ST_PROXY_READY`, step 3 says `OpenState.Closed` with a handshake `ReadTimeout` | The proxy is up; the **desktop side is not answering**. Check Workspace is *signed in* (a quote loads in the app, not "Reconnecting"). If it is, **restart Workspace completely** — the proxy outlives sessions, and a stale one keeps its port while answering nothing. Re-run afterwards. |
| Step 3 says `OpenState.Opened` | The session is fine; the failure is elsewhere — re-read the actual error. |
| A handshake error naming the key | The app key in `lseg-data.config.json` is not valid for a desktop session. Regenerate it in APPKEY. Never print or commit the file. |

**Both acquisition modules refuse to continue past a closed session** (`_require_open_session`
in `covered_call/tape.py` and `covered_call/live.py`). That guard exists because without it the
failure is reported as *missing data*: the pull said "No QQQ.O bars returned" and the live leg
would have written a false `SKIP_NO_STOCK_PRINT` into the book — which I-10 then refuses to
re-run. A desktop outage must never be recorded as a fact about the market.
