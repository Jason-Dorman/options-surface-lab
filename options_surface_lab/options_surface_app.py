"""
Options Surface Lab — Reflex app

Paste this in place of the current app module (or run it as the Reflex entry).
It reuses the existing LSEG pickle cache when present, otherwise synthesizes
a sparse UUUU-like panel so students can still plot something tonight.

Teaching targets this week
--------------------------
1. Listed options are a sparse cloud, not a filled sheet.
2. The mark (derived; there is no exchange settle) is not TRDPRC_1 (last trade).
3. An interpolated "surface" is an assumption you are imposing on holes.
"""

from __future__ import annotations

import os
import pickle
import datetime
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import reflex as rx

from options_surface_lab.option_surface_utils import (
    MARK_FIELD_DEFAULT,
    RISK_FREE_RATE,
    SETTLE_FIELD_CANDIDATES,
    attach_underlying,
    build_candidate_rics,
    flatten_lseg_options,
    pivot_trade_settle,
    summarize_sparsity,
    synthesize_demo_payload,
)
from options_surface_lab import theme as T
from options_surface_lab.option_surface_plot import (
    X_MODE_LABEL,
    X_MODES,
    as_panel_figure,
    candlestick_figure,
    coverage_heatmap,
    figure_caption,
    iv_smile_figure,
    price_surface_figure,
    settle_vs_trade_figure,
    spread_heatmap,
)

# FR-10's control, as a select: the label a reader picks, mapped back to the mode the figure
# builder takes. Labels come from the plot module so the dev app and the published page's
# button pair cannot end up calling the same thing two different names.
X_MODE_BY_LABEL = {X_MODE_LABEL[mode]: mode for mode in X_MODES}

warnings.filterwarnings("ignore", category=FutureWarning, module="lseg.data")

# Anchored to the repo root so the cache resolves regardless of CWD (SYSTEM-SPEC §3)
_REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_FILE = str(_REPO_ROOT / "option_pipeline_data.pkl")
ticker_stock = "UUUU.K"
ticker_root = "UUUU"
weeks_back = 12
strike_step = 0.50
batch_size = 25


def lseg_available() -> bool:
    """True when a pull is possible and permitted. Import only — opens no session.

    ``OSL_OFFLINE=1`` forces the synthetic path regardless. CI and `reflex export`
    set it so the NFR-4 "works with no credentials" guarantee is enforced, not hoped for.
    """
    if os.environ.get("OSL_OFFLINE") == "1":
        return False
    try:
        import lseg.data  # noqa: F401
    except Exception:
        return False
    return True


def load_cached_payload() -> dict:
    """Cache-or-synthetic. Never reaches the network — used by preview/tests/export."""
    if os.path.exists(CACHE_FILE):
        print(f"Loading cached dataset from {CACHE_FILE}...")
        with open(CACHE_FILE, "rb") as f:
            payload = pickle.load(f)
        payload.setdefault("synthetic", False)
        return payload

    print(f"No cache at {CACHE_FILE} — using the synthetic panel.")
    return synthesize_demo_payload(ticker_root=ticker_root, ticker_stock=ticker_stock)


def load_or_fetch_pipeline_data() -> dict:
    """Cache-first acquisition (AD-1, FR-2): load the pickle, else pull, else synthesize.

    Never re-pulls when the cache exists — that is the graded behaviour. The pull only
    fires when there is nothing to clobber, so it cannot destroy a committed cache.
    """
    if os.path.exists(CACHE_FILE):
        return load_cached_payload()

    if not lseg_available():
        return load_cached_payload()

    print("No cache and LSEG is available — running the one-time pull...")
    return fetch_from_lseg()


def _normalize_history(df, requested_rics, fields) -> pd.DataFrame | None:
    """Coerce any `get_history` shape into (RIC, Field) columns.

    LSEG varies the shape with the request: many RICs x many fields gives a
    MultiIndex (either order); many RICs x one populated field gives a flat index of
    RICs with the field as the axis *name*; a single RIC gives a flat index of fields
    with no RIC anywhere. That last case is why the previous version lost data — every
    single-RIC fallback frame carried identical bare field columns, and the subsequent
    `~columns.duplicated()` dropped all but the first.

    Every requested field is kept per RIC even when empty, so "asked for SETTLE and got
    nothing" stays visible instead of silently collapsing the frame (T-27).
    """
    if df is None or getattr(df, "empty", True):
        return None

    df = df.copy()
    fields = list(fields)
    field_set, ric_set = set(fields), set(map(str, requested_rics))

    if df.columns.nlevels == 2:
        level0 = set(map(str, df.columns.get_level_values(0)))
        if (level0 & field_set) and not (level0 & ric_set):
            df.columns = df.columns.swaplevel(0, 1)  # (Field, RIC) -> (RIC, Field)
        pairs = [(str(a), str(b)) for a, b in df.columns]
    else:
        cols = [str(c) for c in df.columns]
        if set(cols) <= field_set and len(ric_set) == 1:
            pairs = [(str(requested_rics[0]), c) for c in cols]           # one RIC, fields
        else:
            axis = str(df.columns.name)
            field = axis if axis in field_set else (fields[0] if len(fields) == 1 else axis)
            pairs = [(c, field) for c in cols]                            # many RICs, one field
    df.columns = pd.MultiIndex.from_tuples(pairs, names=["RIC", "Field"])

    rics = list(dict.fromkeys(df.columns.get_level_values(0)))
    df = df.reindex(columns=pd.MultiIndex.from_product([rics, fields], names=["RIC", "Field"]))

    alive = [r for r in rics if df[r].notna().to_numpy().any()]
    if not alive:
        return None
    return df.loc[:, pd.MultiIndex.from_product([alive, fields], names=["RIC", "Field"])]


def _fetch_universe(ld, rics, fields, start, end, batch_size) -> pd.DataFrame:
    """Batched history with a per-RIC fallback that preserves identity (AD-2)."""
    frames = []
    for i in range(0, len(rics), batch_size):
        batch = rics[i : i + batch_size]
        try:
            got = _normalize_history(
                ld.get_history(universe=batch, fields=list(fields),
                               start=start, end=end, interval="daily"),
                batch, fields,
            )
            if got is not None:
                frames.append(got)
            continue
        except Exception:
            pass  # batch rejected as a whole — retry one at a time
        for ric in batch:
            try:
                one = _normalize_history(
                    ld.get_history(universe=[ric], fields=list(fields),
                                   start=start, end=end, interval="daily"),
                    [ric], fields,
                )
            except Exception:
                one = None
            if one is not None:
                frames.append(one)

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, axis=1)
    return out.loc[:, ~out.columns.duplicated()].sort_index()


def _probe_mark_field(ld, sample_rics, start, end) -> tuple[str | None, dict]:
    """Find which field carries the exchange mark for expired contracts (T-27).

    Each candidate is requested **paired with TRDPRC_1**, a field known to return data
    for these RICs. Requesting an absent field on its own raises `LDError` rather than
    returning an empty frame — which is why the first in-pull probe (2026-08-30) came
    back with `error` for all seven candidates including SETTLE itself, and answered
    nothing. Pairing keeps the request valid so an empty column means "field absent".
    """
    base = "TRDPRC_1"
    results, winner = {}, None
    for field in SETTLE_FIELD_CANDIDATES:
        if field == base:
            continue
        try:
            norm = _normalize_history(
                ld.get_history(universe=list(sample_rics), fields=[base, field],
                               start=start, end=end, interval="daily"),
                list(sample_rics), (base, field),
            )
            count = 0 if norm is None else int(
                norm.loc[:, (slice(None), field)].notna().to_numpy().sum()
            )
        except Exception as exc:
            count = f"error: {type(exc).__name__}"
        results[field] = count
        if winner is None and isinstance(count, int) and count > 0:
            winner = field
    return winner, results


def probe_mark_fields(n_rics: int = 5) -> dict:
    """Standalone read-only T-27 probe. Opens a session, writes nothing, no cache touched.

    Run it from the notebook to settle the settle question without spending a pull.
    """
    import lseg.data as ld

    payload = load_cached_payload()
    if payload.get("synthetic"):
        raise RuntimeError(
            "Probe needs RICs already proven to return data; no real cache present."
        )
    options = payload["options"]
    rics = list(dict.fromkeys(options.columns.get_level_values(0)))[:n_rics]
    start, end = str(options.index.min().date()), str(options.index.max().date())

    ld.open_session()
    try:
        winner, results = _probe_mark_field(ld, rics, start, end)
    finally:
        ld.close_session()
    return {"sample_rics": rics, "window": (start, end), "winner": winner, "results": results}


def fetch_from_lseg(
    ticker_stock: str = "UUUU.K",
    ticker_root: str = "UUUU",
    weeks_back: int = 12,
    strike_step: float = 0.50,
    batch_size: int = 25,
    overwrite: bool = False,
) -> dict:
    """The one-shot LSEG acquisition (FR-2 / T-7). **Never called from the app.**

    Human-invoked only, per RUNBOOK §3: it needs Workspace running, it is slow, and
    it writes CACHE_FILE. Requires the T-6 split pre-flight first. Refuses to clobber
    an existing cache unless ``overwrite=True`` (CLAUDE.md: caches are data artifacts).
    """
    if os.path.exists(CACHE_FILE) and not overwrite:
        raise FileExistsError(
            f"{CACHE_FILE} already exists. Rename it first, or pass overwrite=True. "
            "Caches are never silently regenerated (CLAUDE.md hard constraint)."
        )

    import lseg.data as ld

    print("Initializing LSEG data pull...")
    ld.open_session()

    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(weeks=weeks_back)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    df_stock = ld.get_history(
        universe=[ticker_stock],
        fields=["OPEN_PRC", "HIGH_1", "LOW_1", "TRDPRC_1"],
        start=start_str,
        end=end_str,
        interval="daily",
    )

    low_price = float(df_stock["LOW_1"].min())
    high_price = float(df_stock["HIGH_1"].max())

    min_strike = np.floor(low_price / strike_step) * strike_step
    max_strike = np.ceil(high_price / strike_step) * strike_step
    strikes = np.arange(min_strike, max_strike + strike_step, strike_step)
    expiries = [d.date() for d in pd.date_range(start=start_str, end=end_str, freq="W-FRI")]

    fields = ("TRDPRC_1", MARK_FIELD_DEFAULT, "BID", "ASK", "OPINT_1")
    diag: dict = {"requested_fields": list(fields), "n_expiries": len(expiries),
                  "n_strikes": int(len(strikes))}

    def grid(rights, put_suffix="right"):
        return build_candidate_rics(ticker_root, expiries, strikes,
                                    rights=rights, put_suffix=put_suffix)

    print(f"Requesting {len(expiries)} expiries x {len(strikes)} strikes x 2 rights...")
    df_calls = _fetch_universe(ld, grid(("C",)), fields, start_str, end_str, batch_size)
    df_puts = _fetch_universe(ld, grid(("P",)), fields, start_str, end_str, batch_size)
    diag["put_suffix_style"] = "right"

    # T-27 hypothesis 1: the 2026-08-30 pull got zero puts. The README documents no put
    # example, so the expired-contract suffix may encode the expiry month (shared with
    # the call) rather than repeating the put's own letter. Test it rather than guess.
    if df_puts.empty:
        print("No puts under the README suffix (^R26) — retrying with the call suffix (^F26)...")
        df_puts = _fetch_universe(ld, grid(("P",), "call"), fields, start_str, end_str, batch_size)
        diag["put_suffix_style"] = "call" if not df_puts.empty else "neither"

    df_options = pd.concat([f for f in (df_calls, df_puts) if not f.empty], axis=1)         if not (df_calls.empty and df_puts.empty) else pd.DataFrame()

    # T-27/T-34 are answered: there is NO settlement price for US listed equity options —
    # none is published by the exchanges, OPRA or the OCC (checkpoint_audit.md §3). So we no
    # longer request SETTLE or probe for it; MARK_FIELD_DEFAULT is the derived mark we use.
    # `probe_mark_fields()` remains available to re-demonstrate the absence on demand.
    diag["mark_field_used"] = MARK_FIELD_DEFAULT
    if not df_options.empty:
        diag["mark_populated"] = bool(
            df_options.loc[:, (slice(None), MARK_FIELD_DEFAULT)].notna().to_numpy().any()
        )

    ld.close_session()

    n_calls = sum(1 for r in dict.fromkeys(df_options.columns.get_level_values(0))
                  if r[len(ticker_root)] in "ABCDEFGHIJKL") if not df_options.empty else 0
    diag["n_series"] = 0 if df_options.empty else len(set(df_options.columns.get_level_values(0)))
    diag["n_calls"], diag["n_puts"] = n_calls, diag["n_series"] - n_calls

    data_payload = {
        "stock": df_stock,
        "options": df_options,
        "ticker": ticker_root,
        "fetched_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "synthetic": False,
        "diagnostics": diag,
    }
    with open(CACHE_FILE, "wb") as f:
        pickle.dump(data_payload, f)
    print(f"Data pipeline complete: {diag['n_calls']} calls, {diag['n_puts']} puts, "
          f"mark field '{diag['mark_field_used']}'. Cached to {CACHE_FILE}.")
    return data_payload


def _prepare(payload: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    tidy = flatten_lseg_options(payload["options"])
    tidy = attach_underlying(tidy, payload["stock"])
    wide = pivot_trade_settle(tidy)
    return tidy, wide, payload


class State(rx.State):
    ticker: str = "UUUU"
    status_msg: str = "Ready"
    option_count: int = 0
    n_quotes: int = 0
    n_mark_only: int = 0
    n_both: int = 0
    pct_mark_no_trade: str = "—"
    mark_no_print: str = "—"   # FR-6(a): count AND percent
    median_gap: str = "—"
    median_spread: str = "—"
    data_note: str = ""
    data_warning: str = ""
    is_loading: bool = False
    asof: str = ""
    asof_options: list[str] = []
    cp: str = "C"
    x_mode: str = "strike"      # FR-10: raw strike or K / S
    x_mode_label: str = X_MODE_LABEL["strike"]
    show_trade: bool = True
    show_mark: bool = True
    show_sheet: bool = True
    show_spot_plane: bool = True   # FR-12: the K = S wall

    # Panel captions, by panel number (index 0 unused). The page cannot read them off the
    # figures the way `build_preview.py` does: inside a Reflex component a figure is a State
    # *reference*, not the object, so `figure_caption(State.fig_iv)` has nothing to read.
    # They are lifted here whenever the figures are rebuilt, from the same accessor the
    # published page uses, so the two renderings still cannot disagree (T-47).
    captions: list[list[str]] = [[] for _ in range(8)]

    fig_stock: go.Figure = go.Figure()
    fig_surface: go.Figure = go.Figure()
    fig_compare: go.Figure = go.Figure()
    fig_heat_mark: go.Figure = go.Figure()
    fig_spread: go.Figure = go.Figure()
    fig_heat_trade: go.Figure = go.Figure()
    fig_iv: go.Figure = go.Figure()

    _wide: pd.DataFrame | None = None
    _stock: pd.DataFrame | None = None

    def load_data(self):
        # Offline by construction (AD-1/NFR-4). The yield flushes the loading state
        # to the browser before the blocking read, so the page never sits on stale
        # zeros looking like a failure.
        self.is_loading = True
        self.data_warning = ""
        # Name the path *before* the blocking call: the yield flushes this to the
        # browser, so a multi-minute LSEG pull never masquerades as a failed load.
        if os.path.exists(CACHE_FILE):
            self.status_msg = "Loading cached panel..."
        elif lseg_available():
            self.status_msg = "No cache — pulling from LSEG, this takes minutes..."
            self.data_warning = (
                "First run: no local cache, so the one-time LSEG pull is running now "
                "(FR-2/T-7). Leave the tab open — it writes option_pipeline_data.pkl "
                "and will not run again."
            )
        else:
            self.status_msg = "No cache and no LSEG — building synthetic panel..."
        yield

        payload = load_or_fetch_pipeline_data()
        tidy, wide, payload = _prepare(payload)

        self._wide = wide
        self._stock = payload["stock"]
        self.ticker = payload.get("ticker", "UUUU")
        self.option_count = int(wide["ric"].nunique()) if len(wide) else 0
        self.data_note = (
            "SYNTHETIC panel — copy option_pipeline_data.pkl next to the app to use LSEG"
            if payload.get("synthetic")
            else f"LSEG cache from {payload.get('fetched_at', '?')}"
        )

        dates = sorted({d.strftime("%Y-%m-%d") for d in wide["date"]}) if len(wide) else []
        self.asof_options = dates
        # Default to the date with the MOST listed series, not the last one. These are expired
        # weeklies, so the final date has a single expiry still alive and shows the thinnest
        # possible panel. "Most series" is a neutral criterion — it is not chosen to flatter
        # the mark-vs-print gap, and every date stays selectable.
        if len(wide):
            busiest = wide.groupby(wide["date"].dt.normalize()).size().idxmax()
            self.asof = pd.Timestamp(busiest).strftime("%Y-%m-%d")
        else:
            self.asof = ""

        # Panelised exactly as `build_preview` does it: the panel header carries the
        # name, and the figure must declare the height its panel reserves.
        self.fig_stock = as_panel_figure(
            candlestick_figure(payload["stock"], self.ticker),
            height=T.HERO_FIGURE_HEIGHT,
        )
        self._rebuild_option_figs()

        # AD-9: holes render as holes, but a panel with NO settle side at all is a
        # data defect, not sparsity — say so instead of showing honest-looking zeros.
        self.data_warning = ""  # clear the "pulling now" notice; the load is done
        if len(wide) and not wide["has_mark"].any():
            self.data_warning = (
                f"No mark anywhere in this panel — every mark metric below reads 0 for "
                f"that reason, not because the contracts were worth zero. The mark comes "
                f"from {MARK_FIELD_DEFAULT}; if it is empty the comparison this page exists "
                f"to make (AD-9) has no second series."
            )
        elif len(wide) and not wide["has_trade"].any():
            self.data_warning = "No TRDPRC_1 anywhere in this panel — trade-side metrics are unusable."

        self.status_msg = f"Loaded {self.option_count} series"
        self.is_loading = False

    def set_cp(self, value: str):
        self.cp = value
        self._rebuild_option_figs()

    def set_asof(self, value: str):
        self.asof = value
        self._rebuild_option_figs()

    def set_x_mode(self, value: str):
        """FR-10: switch the surface's X between raw strike and moneyness."""
        self.x_mode_label = value
        self.x_mode = X_MODE_BY_LABEL.get(value, "strike")
        self._rebuild_option_figs()

    def toggle_trade(self, value: bool):
        self.show_trade = value
        self._rebuild_option_figs()

    def toggle_mark(self, value: bool):
        self.show_mark = value
        self._rebuild_option_figs()

    def toggle_sheet(self, value: bool):
        self.show_sheet = value
        self._rebuild_option_figs()

    def toggle_spot_plane(self, value: bool):
        """FR-12. The published page does this on the legend; here it is a switch."""
        self.show_spot_plane = value
        self._rebuild_option_figs()

    def _rebuild_option_figs(self):
        wide = self._wide
        if wide is None or wide.empty or not self.asof:
            # Heights are not decoration here: an undeclared height renders at Plotly's
            # 450 default and spills out of a 360px tile.
            self.fig_surface = go.Figure().update_layout(
                **T.figure_layout(height=T.HERO_FIGURE_HEIGHT)
            )
            tile = go.Figure().update_layout(
                **T.figure_layout(height=T.PANEL_FIGURE_HEIGHT)
            )
            self.fig_compare = tile
            self.fig_heat_mark = tile
            self.fig_spread = tile
            self.fig_heat_trade = tile
            self.fig_iv = go.Figure().update_layout(
                **T.figure_layout(height=T.PANEL_FIGURE_HEIGHT)
            )
            self._lift_captions()
            return

        asof = self.asof
        sl = wide[wide["date"] == pd.Timestamp(asof)]
        stats = summarize_sparsity(sl)
        self.n_quotes = stats["n_quotes"]
        self.n_mark_only = stats["n_mark_only"]
        self.n_both = stats["n_both"]
        self.pct_mark_no_trade = f"{stats['pct_mark_no_trade']:.0f}%"
        # FR-6(a) is explicit that the percent must be shown, not just the count.
        self.mark_no_print = f"{stats['n_mark_only']} ({stats['pct_mark_no_trade']:.0f}%)"
        # How believable the mark is. A wide spread means the midpoint is a number nobody
        # would actually trade at — the thing that bites hardest in 1.2's simulated fills.
        if stats.get("median_spread_pct") is None:
            self.median_spread = "—"
        else:
            self.median_spread = (
                f"${stats['median_spread']:.2f} ({stats['median_spread_pct']:.0f}%)"
            )
        if stats["median_abs_diff"] is None:
            self.median_gap = "n/a"
        else:
            rel = stats["median_rel_diff_pct"]
            self.median_gap = f"${stats['median_abs_diff']:.3f}" + (
                f" ({rel:.1f}%)" if rel is not None else ""
            )

        self.fig_surface = price_surface_figure(
            wide,
            asof,
            cp=self.cp,
            show_trade=self.show_trade,
            show_mark=self.show_mark,
            show_interpolated=self.show_sheet,
            show_spot_plane=self.show_spot_plane,
            ticker=self.ticker,
            x_mode=self.x_mode,
        )
        self.fig_compare = as_panel_figure(
            settle_vs_trade_figure(wide, asof, ticker=self.ticker)
        )
        self.fig_heat_mark = as_panel_figure(
            coverage_heatmap(wide, asof, cp=self.cp, field="MARK")
        )
        self.fig_spread = as_panel_figure(spread_heatmap(wide, asof, cp=self.cp))
        self.fig_heat_trade = as_panel_figure(
            coverage_heatmap(wide, asof, cp=self.cp, field="TRDPRC_1")
        )
        # FR-11. Follows the same x_mode as the hero, so the surface and the smile derived
        # from it are always read on the same ruler.
        self.fig_iv = as_panel_figure(
            iv_smile_figure(wide, asof, ticker=self.ticker, x_mode=self.x_mode),
            margin=T.SMILE_MARGIN,
        )
        self._lift_captions()

    def _lift_captions(self):
        """Panel captions, in panel order, from the figures themselves (T-47)."""
        self.captions = [
            figure_caption(f) if f is not None else []
            for f in (
                None,               # index 0: panels are 1-based
                self.fig_surface,   # [1] price surface
                self.fig_stock,     # [2] underlying
                self.fig_iv,        # [3] implied vol
                self.fig_compare,   # [4] mark vs print
                self.fig_spread,    # [5] spread
                self.fig_heat_mark,  # [6] mark occupancy
                self.fig_heat_trade,  # [7] print occupancy
            )
        ]


# Panel figure heights, in CSS units. Derived from the theme so the dev app and the
# published page cannot drift; the hero and its sidecar must match exactly (DESIGN-BRIEF §5).
HERO_H = f"{T.HERO_FIGURE_HEIGHT}px"
TILE_H = f"{T.PANEL_FIGURE_HEIGHT}px"


def _readout(label: str, value) -> rx.Component:
    """One cell of the readout strip: quiet uppercase label, the number in mono amber."""
    return rx.box(
        rx.text(
            label,
            size="1",
            color=T.TEXT_MUTED,
            style={"letter_spacing": "1.2px", "text_transform": "uppercase"},
        ),
        rx.text(
            value,
            size="6",
            color=T.ACCENT,
            weight="bold",
            font_family=T.FONT_MONO,
            style={"line_height": "1.15", "margin_top": "3px"},
        ),
        bg=T.SURFACE,
        padding="9px 12px 10px 12px",
        flex="1 1 158px",
        min_width="0",
    )


def _panel(
    n: int, name: str, note: str, fig, height: str, width: int = T.W_HALF,
    hero: bool = False,
) -> rx.Component:
    """A numbered panel: header rule carrying `[n] NAME`, the caption, then the figure.

    Mirrors `build_preview._panel` deliberately -- the checkpoint demo and the published page
    are the same product, so they wear the same chrome (DESIGN-BRIEF section 5). Since T-47
    they also share the same STYLESHEET: `theme.PAGE_CSS` is injected into this page and the
    panels carry `osl-*` class names rather than inline styles, so a responsive rule cannot
    be right in one rendering and missing in the other. That split is exactly how the
    published page once shipped with the hero one column wide while `reflex run` looked
    perfect (DESIGN-BRIEF section 5, the deploy-only defect).

    The caption is HTML here too, read from the figure itself, so it wraps instead of
    colliding with the figure's own chrome.
    """
    return rx.box(
        # Plain elements carrying the shared classes, mirroring `build_preview._panel` node
        # for node. Radix components with inline styles looked identical at one width and
        # missed every responsive rule the stylesheet added -- including the one that stops a
        # header wrapping and leaving its row ragged.
        rx.el.div(
            rx.el.div(
                rx.el.span(f"[{n}]", class_name="osl-panel-n"),
                rx.el.span(name, class_name="osl-panel-name"),
            ),
            rx.el.div(note, class_name="osl-panel-note"),
            class_name="osl-panel-head",
        ),
        rx.box(
            rx.foreach(
                State.captions[n],
                lambda line: rx.el.span(line, class_name="osl-caption-line"),
            ),
            class_name="osl-caption",
        ),
        rx.box(
            rx.box(
                rx.plotly(data=fig, style={"width": "100%", "height": height}),
                class_name="osl-figure-hero" if hero else "osl-figure",
            ),
            class_name="osl-panel-body",
        ),
        class_name=f"osl-panel osl-w{width}" + (" osl-hero" if hero else ""),
    )


def index() -> rx.Component:
    return rx.box(
        # ONE stylesheet for both renderings (T-47). The panel grid, its three responsive
        # bands, the caption and the figure width floor all live in `theme.PAGE_CSS`; this
        # page and `build_preview.py` render the same class names against it. Before this,
        # the Reflex app styled panels with inline `grid-column` and had no breakpoints at
        # all, so it stayed a 10-column grid at every width while the published page
        # collapsed -- two products wearing one design.
        rx.html(f"<style>{T.PAGE_CSS}</style>"),
        # ---- command bar -------------------------------------------------------------
        rx.hstack(
            rx.heading(
                "Options Surface Lab",
                size="6",
                color=T.ACCENT,
                font_family=T.FONT_DISPLAY,
                style={"letter_spacing": T.TRACKING, "text_transform": "uppercase"},
            ),
            rx.spacer(),
            rx.text(
                State.data_note,
                color=T.TEXT_MUTED,
                font_family=T.FONT_MONO,
                size="1",
            ),
            rx.badge(
                rx.cond(State.is_loading, rx.spinner(size="1"), rx.fragment()),
                State.status_msg,
                color_scheme=rx.cond(State.is_loading, "amber", "gray"),
                variant="solid",
            ),
            rx.button(
                rx.cond(State.is_loading, "Working...", "Reload"),
                on_click=State.load_data,
                disabled=State.is_loading,
                bg=T.ACCENT_DIM,
                color=T.TEXT,
                _hover={"bg": T.ACCENT, "color": T.TEXT_INVERSE},
                size="2",
            ),
            align="center",
            spacing="3",
            wrap="wrap",
            width="100%",
            bg=T.SURFACE,
            border=f"1px solid {T.BORDER}",
            padding="10px 14px",
        ),
        # ---- readout strip -----------------------------------------------------------
        rx.flex(
            _readout("Underlying", State.ticker),
            _readout("Option series", State.option_count),
            _readout("Quotes on as-of date", State.n_quotes),
            _readout("Mark, no print", State.mark_no_print),
            _readout("Median |mark - trade|", State.median_gap),
            _readout("Median bid-ask spread", State.median_spread),
            wrap="wrap",
            spacing="0",
            width="100%",
            bg=T.BORDER,
            border=f"1px solid {T.BORDER}",
            border_top="0",
            gap=T.GUTTER,
            margin_bottom="10px",
        ),
        rx.cond(
            State.data_warning != "",
            rx.callout(
                State.data_warning,
                icon="triangle_alert",
                color_scheme="amber",
                variant="surface",
                size="1",
                width="100%",
                margin_bottom="10px",
            ),
            rx.fragment(),
        ),
        # ---- controls: local dev only. The published page has no backend, so its
        # equivalents are the Plotly slider and legend inside the hero figure (AD-5).
        rx.hstack(
            rx.text("As-of", color=T.TEXT_MUTED, size="1", font_family=T.FONT_MONO),
            rx.select(State.asof_options, value=State.asof, on_change=State.set_asof, size="1"),
            rx.text("Right", color=T.TEXT_MUTED, size="1", font_family=T.FONT_MONO),
            rx.select(["C", "P"], value=State.cp, on_change=State.set_cp, size="1"),
            # FR-10. Rebasing the strike axis to spot is what makes two as-of dates
            # comparable; the published page does the same job with a Plotly button pair.
            rx.text("X axis", color=T.TEXT_MUTED, size="1", font_family=T.FONT_MONO),
            rx.select(
                list(X_MODE_BY_LABEL),
                value=State.x_mode_label,
                on_change=State.set_x_mode,
                size="1",
            ),
            rx.switch(checked=State.show_mark, on_change=State.toggle_mark),
            rx.text(f"MARK ({MARK_FIELD_DEFAULT})", color=T.MARK, size="1"),
            rx.switch(checked=State.show_trade, on_change=State.toggle_trade),
            rx.text("TRDPRC_1", color=T.TRADE, size="1"),
            rx.switch(checked=State.show_sheet, on_change=State.toggle_sheet),
            rx.text("Interpolated sheet", color=T.TEXT_MUTED, size="1"),
            # FR-12. Muted like the sheet, and for the same reason: neither is data.
            rx.switch(checked=State.show_spot_plane, on_change=State.toggle_spot_plane),
            rx.text("Spot plane (K = S)", color=T.TEXT_MUTED, size="1"),
            spacing="3",
            align="center",
            wrap="wrap",
            width="100%",
            bg=T.SURFACE,
            border=f"1px solid {T.BORDER}",
            padding="8px 12px",
            margin_bottom="10px",
        ),
        # ---- the panel grid ----------------------------------------------------------
        rx.box(
            # Row 1: the surface, with the underlying beside it. Spot is what makes "near
            # the money" mean anything, and the dense part of the cloud is exactly that
            # band -- so the two belong side by side. Equal heights keep the row square.
            _panel(
                1, "Price surface - 3D",
                "drag to rotate - legend toggles series",
                State.fig_surface, HERO_H, width=T.W_HERO, hero=True,
            ),
            _panel(2, "Underlying", "spot context - close = TRDPRC_1",
                   State.fig_stock, HERO_H, width=T.W_SIDECAR),
            # Row 2: the same cloud read through a model, beside the evidence that the
            # mark is not the print. The smile sits directly under the surface it comes
            # from (PO, 2026-09-04) -- it is a transform of that price, not new data.
            _panel(3, "Implied vol - derived",
                   "one curve per expiry - a break = the solver refusing",
                   State.fig_iv, TILE_H),
            _panel(4, "Mark vs print", f"{MARK_FIELD_DEFAULT} against TRDPRC_1",
                   State.fig_compare, TILE_H),
            # Row 3: can you believe the mark at all? Full width so the two occupancy
            # grids below stay paired -- comparing them is the reason both are shown.
            _panel(5, "Spread - can you believe the mark?", "bid-ask as % of the mark",
                   State.fig_spread, TILE_H, width=T.W_FULL),
            # Row 4: where the data is not there at all. Paired so they can be compared.
            _panel(6, "Mark occupancy", "lit = a mark exists",
                   State.fig_heat_mark, TILE_H),
            _panel(7, "Print occupancy", "lit = someone traded",
                   State.fig_heat_trade, TILE_H),
            class_name="osl-grid",
            width="100%",
        ),
        on_mount=State.load_data,
        background_color=T.BG,
        color=T.TEXT,
        font_family=T.FONT_BODY,
        min_height="100vh",
        width="100%",
        padding=T.PAGE_PAD,
    )


app = rx.App(
    # The webfonts the identity is built on (FR-8). Reflex injects these into <head>;
    # every stack in theme.py falls back to a system face if they never arrive.
    stylesheets=[T.GOOGLE_FONTS_CSS],
)
app.add_page(index)
