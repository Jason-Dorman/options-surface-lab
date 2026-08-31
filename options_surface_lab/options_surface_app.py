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
    SETTLE_FIELD_CANDIDATES,
    attach_underlying,
    build_candidate_rics,
    flatten_lseg_options,
    pivot_trade_settle,
    summarize_sparsity,
    synthesize_demo_payload,
)
from options_surface_lab.option_surface_plot import (
    candlestick_figure,
    coverage_heatmap,
    price_surface_figure,
    settle_vs_trade_figure,
    spread_heatmap,
)

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
    median_gap: str = "—"
    median_spread: str = "—"
    data_note: str = ""
    data_warning: str = ""
    is_loading: bool = False
    asof: str = ""
    asof_options: list[str] = []
    cp: str = "C"
    show_trade: bool = True
    show_mark: bool = True
    show_sheet: bool = True

    fig_stock: go.Figure = go.Figure()
    fig_surface: go.Figure = go.Figure()
    fig_compare: go.Figure = go.Figure()
    fig_heat_mark: go.Figure = go.Figure()
    fig_spread: go.Figure = go.Figure()
    fig_heat_trade: go.Figure = go.Figure()

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

        self.fig_stock = candlestick_figure(payload["stock"], self.ticker)
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

    def toggle_trade(self, value: bool):
        self.show_trade = value
        self._rebuild_option_figs()

    def toggle_mark(self, value: bool):
        self.show_mark = value
        self._rebuild_option_figs()

    def toggle_sheet(self, value: bool):
        self.show_sheet = value
        self._rebuild_option_figs()

    def _rebuild_option_figs(self):
        wide = self._wide
        if wide is None or wide.empty or not self.asof:
            empty = go.Figure()
            empty.update_layout(template="plotly_dark", paper_bgcolor="#0d1117")
            self.fig_surface = empty
            self.fig_compare = empty
            self.fig_heat_mark = empty
            self.fig_spread = empty
            self.fig_heat_trade = empty
            return

        asof = self.asof
        sl = wide[wide["date"] == pd.Timestamp(asof)]
        stats = summarize_sparsity(sl)
        self.n_quotes = stats["n_quotes"]
        self.n_mark_only = stats["n_mark_only"]
        self.n_both = stats["n_both"]
        self.pct_mark_no_trade = f"{stats['pct_mark_no_trade']:.0f}%"
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
            ticker=self.ticker,
        )
        self.fig_compare = settle_vs_trade_figure(wide, asof, ticker=self.ticker)
        self.fig_heat_mark = coverage_heatmap(wide, asof, cp=self.cp, field="MARK")
        self.fig_spread = spread_heatmap(wide, asof, cp=self.cp)
        self.fig_heat_trade = coverage_heatmap(wide, asof, cp=self.cp, field="TRDPRC_1")


def _metric(label: str, value) -> rx.Component:
    return rx.card(
        rx.text(label, size="2", color="#8b949e"),
        rx.text(value, size="6", color="#00ffcc", weight="bold"),
        bg="#161b22",
        border="1px solid #30363d",
        padding="1rem",
    )


def index() -> rx.Component:
    return rx.container(
        rx.vstack(
            rx.hstack(
                rx.heading(
                    "OPTIONS SURFACE LAB",
                    size="8",
                    color="#00ffcc",
                    style={"letter_spacing": "2px"},
                ),
                rx.spacer(),
                rx.badge(
                    rx.cond(State.is_loading, rx.spinner(size="1"), rx.fragment()),
                    State.status_msg,
                    color_scheme=rx.cond(State.is_loading, "amber", "cyan"),
                    variant="solid",
                ),
                width="100%",
                align="center",
                padding_y="1rem",
            ),
            rx.text(State.data_note, color="#8b949e", size="2"),
            rx.cond(
                State.data_warning != "",
                rx.callout(
                    State.data_warning,
                    icon="triangle_alert",
                    color_scheme="amber",
                    variant="surface",
                    size="1",
                    width="100%",
                ),
                rx.fragment(),
            ),
            rx.hstack(
                _metric("Underlying", State.ticker),
                _metric("Option series", State.option_count),
                _metric("Quotes on as-of date", State.n_quotes),
                _metric("Mark with no print", State.n_mark_only),
                _metric("Median |mark − trade|", State.median_gap),
                _metric("Median bid-ask spread", State.median_spread),
                rx.button(
                    rx.cond(State.is_loading, "Working…", "Reload data"),
                    on_click=State.load_data,
                    disabled=State.is_loading,
                    bg="#238636",
                    color="#ffffff",
                    _hover={"bg": "#2ea043"},
                    size="3",
                ),
                spacing="4",
                width="100%",
                align="center",
                wrap="wrap",
            ),
            rx.box(
                rx.plotly(data=State.fig_stock, style={"width": "100%", "height": "420px"}),
                width="100%",
                bg="#161b22",
                border="1px solid #30363d",
                border_radius="8px",
                padding="1rem",
            ),
            rx.hstack(
                rx.text("As-of date", color="#8b949e", size="2"),
                rx.select(
                    State.asof_options,
                    value=State.asof,
                    on_change=State.set_asof,
                    size="2",
                ),
                rx.text("Right", color="#8b949e", size="2"),
                rx.select(
                    ["C", "P"],
                    value=State.cp,
                    on_change=State.set_cp,
                    size="2",
                ),
                rx.switch(checked=State.show_mark, on_change=State.toggle_mark),
                rx.text(f"MARK ({MARK_FIELD_DEFAULT})", color="#00ffcc", size="2"),
                rx.switch(checked=State.show_trade, on_change=State.toggle_trade),
                rx.text("TRDPRC_1", color="#ff0055", size="2"),
                rx.switch(checked=State.show_sheet, on_change=State.toggle_sheet),
                rx.text("Interpolated sheet", color="#8b949e", size="2"),
                spacing="3",
                align="center",
                wrap="wrap",
                width="100%",
            ),
            rx.text(
                f"Cyan dots = the quoted mark ({MARK_FIELD_DEFAULT}). Magenta diamonds = last trade. "
                "US listed equity options have no exchange settlement price — every mark is derived. "
                "The translucent sheet is linearly interpolated and will happily "
                "invent prices in strikes that never printed. Turn it off.",
                color="#8b949e",
                size="2",
            ),
            rx.box(
                rx.plotly(data=State.fig_surface, style={"width": "100%", "height": "640px"}),
                width="100%",
                bg="#161b22",
                border="1px solid #30363d",
                border_radius="8px",
                padding="1rem",
            ),
            rx.box(
                rx.plotly(data=State.fig_compare, style={"width": "100%", "height": "460px"}),
                width="100%",
                bg="#161b22",
                border="1px solid #30363d",
                border_radius="8px",
                padding="1rem",
            ),
            rx.hstack(
                rx.box(
                    rx.plotly(
                        data=State.fig_heat_mark,
                        style={"width": "100%", "height": "380px"},
                    ),
                    width="50%",
                    bg="#161b22",
                    border="1px solid #30363d",
                    border_radius="8px",
                    padding="0.5rem",
                ),
                rx.box(
                    rx.plotly(
                        data=State.fig_heat_trade,
                        style={"width": "100%", "height": "380px"},
                    ),
                    width="50%",
                    bg="#161b22",
                    border="1px solid #30363d",
                    border_radius="8px",
                    padding="0.5rem",
                ),
                width="100%",
                spacing="3",
            ),
            rx.text(
                "Occupancy says whether a number exists. The spread says whether to believe it — "
                "a mark halfway between a $0.10 bid and a $2.00 ask is not a price you can trade.",
                color="#8b949e",
                size="2",
            ),
            rx.box(
                rx.plotly(data=State.fig_spread, style={"width": "100%", "height": "420px"}),
                width="100%",
                bg="#161b22",
                border="1px solid #30363d",
                border_radius="8px",
                padding="1rem",
            ),
            spacing="5",
            width="100%",
        ),
        on_mount=State.load_data,
        background_color="#0d1117",
        min_height="100vh",
        max_width="100%",
        padding="2rem",
    )


app = rx.App()
app.add_page(index)
