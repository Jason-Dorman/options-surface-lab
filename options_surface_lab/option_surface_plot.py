"""Plotly figures for the options surface lab.

Every visual constant comes from :mod:`options_surface_lab.theme` (FR-8 / AD-6). If you
find yourself typing a `#` followed by six hex digits in this file, the token you want is
missing from the theme — add it there.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from options_surface_lab import theme as T
from options_surface_lab.option_surface_utils import MARK_FIELD_DEFAULT, surface_grid

# Labels name the field the mark actually comes from. There is no SETTLE for US
# listed equity options (checkpoint_audit.md §3) — saying so on the axis is the point.
MARK_LABEL = MARK_FIELD_DEFAULT

# FR-5's marker-identity invariant, in one place: the mark and the print differ in colour
# *and* symbol for both rights, so no restyle can collapse them into one another.
SERIES_STYLE = {
    ("C", "mark"): dict(color=T.MARK, symbol=T.SYMBOL_MARK, size=T.SIZE_MARK),
    ("P", "mark"): dict(color=T.MARK_PUT, symbol=T.SYMBOL_MARK_PUT, size=T.SIZE_MARK),
    ("C", "trade"): dict(color=T.TRADE, symbol=T.SYMBOL_TRADE, size=T.SIZE_TRADE),
    ("P", "trade"): dict(color=T.TRADE_PUT, symbol=T.SYMBOL_TRADE_PUT, size=T.SIZE_TRADE),
}
SHEET_SCALE = {"C": T.SHEET_SCALE, "P": T.SHEET_SCALE_PUT}
STYLED_RIGHTS = frozenset(SHEET_SCALE)


def _empty_figure(message: str, height: int | None = None) -> go.Figure:
    """A themed 'nothing to draw' panel. Never raise at a hole (AD-9, SYSTEM-SPEC §11).

    Defaults to the tile height rather than Plotly's 450: an empty figure that does not
    declare a height renders taller than the box reserved for it and spills into the
    panel below.
    """
    return go.Figure().update_layout(
        **T.figure_layout(
            title=T.title(message), height=height or T.PANEL_FIGURE_HEIGHT
        )
    )


def candlestick_figure(df_stock: pd.DataFrame, ticker: str) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df_stock.index,
                open=df_stock["OPEN_PRC"],
                high=df_stock["HIGH_1"],
                low=df_stock["LOW_1"],
                close=df_stock["TRDPRC_1"],
                increasing_line_color=T.POSITIVE,
                increasing_fillcolor=T.POSITIVE,
                decreasing_line_color=T.NEGATIVE,
                decreasing_fillcolor=T.NEGATIVE,
                name=ticker,
            )
        ]
    )
    fig.update_layout(
        **T.figure_layout(
            title=T.title(f"{ticker}  ·  underlying OHLC"),
            xaxis=T.axis(rangeslider=dict(visible=False)),
            yaxis=T.axis("Price ($)"),
            margin=dict(l=48, r=24, t=56, b=40),
            height=420,
            annotations=[
                T.caption("Close field is TRDPRC_1 (last trade) — not an option settle")
            ],
        )
    )
    return fig


def as_panel_figure(fig: go.Figure, height: int | None = None) -> go.Figure:
    """Strip a figure's own title and tighten it for a tiled panel (DESIGN-BRIEF §5).

    In the terminal layout each panel carries a header rule with its number and name, so a
    Plotly title inside the plot area would say the same thing twice and eat a third of the
    tile. The caption annotation stays — it is the "how to read this" line, not a label.

    Not applied to the hero surface: its title tracks the as-of slider, so it has to live
    inside the figure JSON where the slider can rewrite it (AD-5).
    """
    return fig.update_layout(
        title_text=None,
        margin=T.PANEL_FIGURE_MARGIN,
        height=height or T.PANEL_FIGURE_HEIGHT,
    )


def _slice_wide(wide: pd.DataFrame, asof, cp: str) -> pd.DataFrame:
    sl = wide.copy()
    if asof is not None and len(sl):
        asof_ts = pd.Timestamp(asof).normalize()
        sl = sl[sl["date"] == asof_ts]
    if cp in {"C", "P"}:
        sl = sl[sl["cp"] == cp]
    return sl


def _mark_trace(frame: pd.DataFrame, cp: str, name: str, **overrides) -> go.Scatter3d:
    st = SERIES_STYLE[(cp, "mark")]
    return go.Scatter3d(
        x=frame["strike"],
        y=frame["dte"],
        z=frame["MARK"],
        mode="markers",
        name=name,
        marker=dict(
            size=st["size"], color=st["color"], opacity=0.85, symbol=st["symbol"],
            line=dict(width=0),
        ),
        hovertemplate=(
            f"<b>{MARK_LABEL}</b> $%{{z:.3f}}<br>K=%{{x:.2f}}<br>DTE=%{{y}}"
            "<br>%{customdata[0]}<extra></extra>"
        ),
        customdata=np.stack([frame["ric"].astype(str)], axis=1),
        **overrides,
    )


def _trade_trace(frame: pd.DataFrame, cp: str, name: str, **overrides) -> go.Scatter3d:
    st = SERIES_STYLE[(cp, "trade")]
    return go.Scatter3d(
        x=frame["strike"],
        y=frame["dte"],
        z=frame["TRDPRC_1"],
        mode="markers",
        name=name,
        marker=dict(
            size=st["size"], color=st["color"], opacity=1.0, symbol=st["symbol"],
            line=dict(width=0.5, color=T.TRADE_EDGE),
        ),
        hovertemplate=(
            "<b>TRDPRC_1</b> $%{z:.3f}<br>K=%{x:.2f}<br>DTE=%{y}"
            "<br>%{customdata[0]}<extra></extra>"
        ),
        customdata=np.stack([frame["ric"].astype(str)], axis=1),
        **overrides,
    )


def _sheet_trace(grid: dict, cp: str, name: str, **overrides) -> go.Surface:
    """The interpolated sheet — translucent and label-led, because it is not a market."""
    return go.Surface(
        x=grid["x"],
        y=grid["y"],
        z=grid["z"],
        name=name,
        colorscale=SHEET_SCALE[cp],
        opacity=T.SHEET_OPACITY,
        showscale=False,
        hoverinfo="skip",
        contours=dict(x=dict(show=False), y=dict(show=False), z=dict(show=False)),
        **overrides,
    )


def _surface_scene() -> dict:
    # near-dated in front: reverse DTE so 0 sits toward the viewer
    return T.scene(
        xaxis=T.scene_axis("Strike ($)"),
        yaxis=T.scene_axis("Days to expiry", autorange="reversed"),
        zaxis=T.scene_axis("Option price ($)"),
    )


def price_surface_figure(
    wide: pd.DataFrame,
    asof,
    cp: str = "C",
    show_trade: bool = True,
    show_mark: bool = True,
    show_interpolated: bool = True,
    ticker: str = "UUUU",
) -> go.Figure:
    sl = _slice_wide(wide, asof, cp)
    if sl.empty:
        return _empty_figure("No quotes on this date / filter", height=T.HERO_FIGURE_HEIGHT)

    fig = go.Figure()
    spot = sl["spot"].dropna()
    spot_val = float(spot.median()) if len(spot) else None
    cp_label = {"C": "Calls", "P": "Puts", "B": "Puts + Calls"}.get(cp, cp)
    asof_txt = str(pd.Timestamp(asof).date()) if asof is not None else "all dates"
    spot_txt = f"  ·  spot ${spot_val:.2f}" if spot_val is not None else ""
    # "B" draws both rights; the style table is keyed per right, so fall back to calls.
    style_cp = cp if cp in STYLED_RIGHTS else "C"

    if show_mark and sl["MARK"].notna().any():
        s = sl.dropna(subset=["MARK"])
        fig.add_trace(_mark_trace(s, style_cp, "MARK"))
        if show_interpolated:
            grid = surface_grid(s, "MARK")
            if grid is not None:
                fig.add_trace(_sheet_trace(grid, style_cp, "Interpolated sheet"))

    if show_trade and sl["TRDPRC_1"].notna().any():
        t = sl.dropna(subset=["TRDPRC_1"])
        fig.add_trace(_trade_trace(t, style_cp, "TRDPRC_1"))

    fig.update_layout(
        **T.figure_layout(
            title=T.title(f"{ticker}  {cp_label}  ·  {asof_txt}{spot_txt}"),
            scene=_surface_scene(),
            legend=T.legend(),
            # Same height as the published page's hero, because it sits in the same
            # panel slot. A figure taller than its panel overflows into the row below.
            height=T.HERO_FIGURE_HEIGHT,
            margin=dict(l=10, r=10, t=56, b=10),
            annotations=[
                T.caption(
                    "Cyan = quoted mark &nbsp;·&nbsp; Magenta = last trade (TRDPRC_1) "
                    "&nbsp;·&nbsp; Sheet is interpolated, not a market",
                    y=1.0,
                )
            ],
        )
    )
    return fig



def static_surface_figure(wide: pd.DataFrame, dates=None, ticker: str = "UUUU") -> go.Figure:
    """The 3D surface with its controls baked in, for the published page (AD-5, T-15).

    The deployed site is a static HTML file with no backend, so Reflex event handlers never
    run there. Everything the page can do must live inside the figure JSON.

    Two controls, deliberately on different mechanisms:

    * **Date — a slider.** Every trading day in the panel gets a step. A dropdown was tried
      first and is unusable at this length.
    * **Calls / puts and series — the legend.** Each date contributes up to six traces
      (mark / sheet / print, x calls / puts). Puts start as ``legendonly`` so the opening view
      is calls, and one click adds them.

    Putting the right on the legend rather than a second menu is what makes the two controls
    compose. Plotly buttons apply a fixed visibility array and cannot read another menu's
    state, so a second dropdown would fight the first; the legend is orthogonal by
    construction. Known limitation: moving the slider re-applies visibility, so legend
    choices reset on a date change.

    Dates with too few expiries to triangulate simply contribute no sheet
    (:func:`surface_grid` returns ``None``) — they still show their points rather than being
    dropped entirely.
    """
    if wide is None or wide.empty:
        return _empty_figure("No data", height=T.HERO_FIGURE_HEIGHT)

    # Every trading day by default — the PO's call (2026-09-01): render all the data we have
    # and accept the load time. To trim, pass an explicit list; `curated_asof_dates(wide, n)`
    # picks a spread of the richest days and is the intended lever if the page gets too heavy.
    if dates is None:
        dates = sorted(wide["date"].dt.normalize().unique())
    if len(dates) == 0:
        return price_surface_figure(wide, None, ticker=ticker)

    fig = go.Figure()
    per_date, spots = [], {}

    for asof in dates:
        idx = {}
        for cp in ("C", "P"):
            sl = _slice_wide(wide, asof, cp)
            if sl.empty:
                continue
            spot = sl["spot"].dropna()
            if len(spot):
                spots[asof] = float(spot.median())
            right = "calls" if cp == "C" else "puts"

            mk = sl.dropna(subset=["MARK"])
            if len(mk):
                fig.add_trace(
                    _mark_trace(
                        mk, cp, f"{MARK_LABEL} · {right}",
                        visible=False, legendgroup=f"mark-{cp}",
                    )
                )
                idx[(cp, "mark")] = len(fig.data) - 1

                grid = surface_grid(mk, "MARK")
                if grid is not None:
                    fig.add_trace(
                        _sheet_trace(
                            grid, cp, f"Interpolated sheet · {right}",
                            visible=False, showlegend=True, legendgroup=f"sheet-{cp}",
                        )
                    )
                    idx[(cp, "sheet")] = len(fig.data) - 1

            tr = sl.dropna(subset=["TRDPRC_1"])
            if len(tr):
                fig.add_trace(
                    _trade_trace(
                        tr, cp, f"TRDPRC_1 · {right}",
                        visible=False, legendgroup=f"trade-{cp}",
                    )
                )
                idx[(cp, "trade")] = len(fig.data) - 1
        if idx:
            per_date.append((asof, idx))

    if not per_date:
        return price_surface_figure(wide, dates[0], ticker=ticker)

    def _vis_for(idx):
        """Calls visible, puts parked on the legend so the opening view is not a mess."""
        vis = [False] * len(fig.data)
        for (cp, _kind), i in idx.items():
            vis[i] = True if cp == "C" else "legendonly"
        return vis

    def _title(asof):
        spot = spots.get(asof)
        return f"{ticker}  ·  {pd.Timestamp(asof).date()}" + (
            f"  ·  spot ${spot:.2f}" if spot else ""
        )

    # Open on the busiest day, matching the app and the headline numbers. Counting trace
    # *kinds* would tie at six for most dates and silently land on the earliest one.
    counts = wide.groupby(wide["date"].dt.normalize()).size()
    default = max(range(len(per_date)), key=lambda i: int(counts.get(per_date[i][0], 0)))
    for i, v in enumerate(_vis_for(per_date[default][1])):
        if v is not False:
            fig.data[i].visible = v

    steps = [
        dict(
            method="update",
            label=str(pd.Timestamp(asof).date()),
            args=[{"visible": _vis_for(idx)}, {"title.text": _title(asof)}],
        )
        for asof, idx in per_date
    ]

    fig.update_layout(
        **T.figure_layout(
            title=T.title(_title(per_date[default][0])),
            scene=_surface_scene(),
            legend=T.legend(font=dict(size=T.SIZE_TICK, color=T.TEXT, family=T.FONT_BODY)),
            sliders=[T.slider(active=default, steps=steps)],
            height=T.HERO_FIGURE_HEIGHT,
            margin=dict(l=8, r=8, t=88, b=84),
            annotations=[
                T.caption(
                    "Drag the slider to change as-of date &nbsp;·&nbsp; puts start hidden — "
                    "click them in the legend &nbsp;·&nbsp; the sheet is interpolated, "
                    "not a market",
                    y=1.045,
                )
            ],
        )
    )
    return fig


def settle_vs_trade_figure(wide: pd.DataFrame, asof=None, ticker: str = "UUUU") -> go.Figure:
    sl = wide.copy()
    if asof is not None and len(sl):
        sl = sl[sl["date"] == pd.Timestamp(asof).normalize()]
    both = sl.dropna(subset=["TRDPRC_1", "MARK"])
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(f"mark ({MARK_LABEL}) vs TRDPRC_1", "Who actually printed?"),
        horizontal_spacing=0.12,
        vertical_spacing=0.08,
    )

    if len(both):
        # One trace per right, not one trace coloured by a mapped array. The array version
        # produced a single unlabelled legend entry, so a reader had no way to confirm the
        # puts were there at all — and with the old put hue sitting next to the call hue,
        # the honest first read was "the puts are missing". Two named traces make the split
        # explicit, and the legend doubles as a filter.
        #
        # Both rights draw the mark, so both are circles; hue alone separates them, which is
        # why the two hues are 83 degrees apart rather than neighbouring shades.
        for cp, label, colour, symbol in (
            ("C", "Calls", T.MARK, T.SYMBOL_MARK),
            ("P", "Puts", T.MARK_PUT, T.SYMBOL_MARK_PUT),
        ):
            side = both[both["cp"] == cp]
            if not len(side):
                continue
            fig.add_trace(
                go.Scatter(
                    x=side["TRDPRC_1"],
                    y=side["MARK"],
                    mode="markers",
                    name=label,
                    marker=dict(
                        size=7,
                        color=colour,
                        opacity=0.85,
                        symbol=symbol,
                        line=dict(width=0.5, color=T.SURFACE_ALT),
                    ),
                    customdata=np.stack(
                        [side["ric"].astype(str), side["strike"], side["dte"]], axis=1
                    ),
                    hovertemplate=(
                        f"<b>{label[:-1]}</b>  trade $%{{x:.3f}}  mark $%{{y:.3f}}"
                        "<br>K=%{customdata[1]} DTE=%{customdata[2]}"
                        "<br>%{customdata[0]}<extra></extra>"
                    ),
                    showlegend=True,
                ),
                row=1,
                col=1,
            )
        lo = float(min(both["TRDPRC_1"].min(), both["MARK"].min()))
        hi = float(max(both["TRDPRC_1"].max(), both["MARK"].max()))
        pad = (hi - lo) * 0.06 if hi > lo else 0.05
        fig.add_trace(
            go.Scatter(
                x=[lo - pad, hi + pad],
                y=[lo - pad, hi + pad],
                mode="lines",
                line=dict(color=T.TEXT_MUTED, dash="dash", width=1),
                name="y = x",
                showlegend=True,
            ),
            row=1,
            col=1,
        )
        fig.update_xaxes(range=[lo - pad, hi + pad], row=1, col=1)
        fig.update_yaxes(range=[lo - pad, hi + pad], row=1, col=1)

    n_settle_only = int((sl["has_mark"] & ~sl["has_trade"]).sum())
    n_both = int((sl["has_mark"] & sl["has_trade"]).sum())
    n_trade_only = int((sl["has_trade"] & ~sl["has_mark"]).sum())
    ymax = max(n_settle_only, n_both, n_trade_only, 1)
    fig.add_trace(
        go.Bar(
            x=["Settle only", "Both", "Print only"],
            y=[n_settle_only, n_both, n_trade_only],
            marker_color=[T.MARK, T.NEUTRAL, T.TRADE],
            showlegend=False,
            text=[n_settle_only, n_both, n_trade_only],
            textposition="inside",
            textfont=dict(color=T.TEXT_INVERSE, size=12, family=T.FONT_MONO),
            cliponaxis=False,
        ),
        row=1,
        col=2,
    )
    fig.update_yaxes(range=[0, ymax * 1.18], row=1, col=2)

    fig.update_xaxes(T.axis("TRDPRC_1 ($)"), row=1, col=1)
    fig.update_yaxes(T.axis(f"mark — {MARK_LABEL} ($)"), row=1, col=1)
    fig.update_xaxes(T.axis(), row=1, col=2)
    fig.update_yaxes(T.axis("Series count"), row=1, col=2)

    fig.update_layout(
        **T.figure_layout(
            title=T.title(f"{ticker}  ·  last trade is not the settle"),
            height=460,
            margin=dict(l=56, r=24, t=72, b=52),
            legend=T.legend(
                yanchor="top", y=-0.18, x=0.0, xanchor="left",
                bgcolor=T.TRANSPARENT, bordercolor=T.BORDER,
            ),
            annotations=[
                T.caption(
                    "Off-diagonal = mark ≠ print &nbsp;·&nbsp; cyan = calls, violet = puts "
                    "&nbsp;·&nbsp; bars: listed series that day"
                )
            ],
        )
    )
    # subplot titles are annotations too, and update_layout above replaced the list —
    # restyle whatever survived so the two subplot headers take the display face
    fig.update_annotations(font=dict(size=13, family=T.FONT_DISPLAY, color=T.TEXT))
    return fig


def spread_heatmap(wide: pd.DataFrame, asof, cp: str = "C") -> go.Figure:
    """How trustworthy the mark is, cell by cell: bid-ask spread as a % of the mark.

    The occupancy heatmaps answer "is there a number here?". This answers "and can I
    believe it?" — a mark sitting between a $0.10 bid and a $2.00 ask is a midpoint you
    cannot trade at. Dark = tight and believable, bright = wide and soft. Cells with no
    two-sided quote stay empty, because a spread is undefined there (AD-9).
    """
    sl = _slice_wide(wide, asof, cp)
    if sl.empty or "spread_pct" not in sl.columns or not sl["spread_pct"].notna().any():
        return _empty_figure("No two-sided quotes")

    sl = sl.copy()
    sl["expiry_label"] = sl["expiry"].dt.strftime("%b ") + sl["expiry"].dt.day.astype(int).astype(str)
    pivot = sl.pivot_table(index="expiry_label", columns="strike", values="spread_pct", aggfunc="median")
    order = sl.drop_duplicates("expiry_label").sort_values("expiry")["expiry_label"].tolist()
    pivot = pivot.reindex(order, axis=0).reindex(sorted(sl["strike"].unique()), axis=1)

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=[f"{c:.2f}" for c in pivot.columns],
            y=list(pivot.index),
            colorscale=T.SPREAD_SCALE,
            zmin=0,
            zmax=100,
            colorbar=dict(
                title=dict(
                    text="% of mark",
                    font=dict(size=T.SIZE_CAPTION, color=T.TEXT, family=T.FONT_BODY),
                ),
                tickfont=dict(size=T.SIZE_TICK, color=T.TEXT_MUTED, family=T.FONT_MONO),
                outlinecolor=T.BORDER,
            ),
            xgap=2,
            ygap=2,
            hovertemplate="K=%{x}  expiry=%{y}  spread=%{z:.0f}% of mark<extra></extra>",
        )
    )
    fig.update_layout(
        **T.figure_layout(
            title=T.title("How much is the mark worth believing? (bid-ask spread)"),
            xaxis=T.axis("Strike ($)", tickangle=-45),
            yaxis=T.axis("Expiry"),
            height=380,
            margin=dict(l=70, r=20, t=54, b=70),
            annotations=[
                T.caption(
                    "Green = tight, tradeable · Red = the midpoint is a guess between "
                    "two far-apart quotes",
                    y=1.10,
                    x=0.02,
                )
            ],
        )
    )
    return fig


def coverage_heatmap(wide: pd.DataFrame, asof, cp: str = "C", field: str = "TRDPRC_1") -> go.Figure:
    """2D occupancy grid: which (strike, expiry) cells actually have a number."""
    sl = _slice_wide(wide, asof, cp)
    if sl.empty:
        return _empty_figure("No data")

    sl = sl.copy()
    sl["expiry_label"] = sl["expiry"].dt.strftime("%b ") + sl["expiry"].dt.day.astype(int).astype(str)
    val = sl[field] if field in sl.columns else sl["MARK"]
    sl["_hit"] = val.notna().astype(int)
    pivot = sl.pivot_table(index="expiry_label", columns="strike", values="_hit", aggfunc="max")
    # keep expiry order chronological, not alpha on "Oct"/"Sep"
    order = (
        sl.drop_duplicates("expiry_label")
        .sort_values("expiry")["expiry_label"]
        .tolist()
    )
    pivot = pivot.reindex(order, axis=0)
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)

    # A lit cell takes the colour of the series it belongs to, so the two occupancy panels
    # are readable side by side as "the mark grid" and "the print grid".
    accent = T.MARK if field == "MARK" else T.TRADE
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=[f"{c:.2f}" for c in pivot.columns],
            y=list(pivot.index),
            colorscale=[[0, T.SURFACE_ALT], [1, accent]],
            zmin=0,
            zmax=1,
            showscale=False,
            xgap=2,
            ygap=2,
            hovertemplate="K=%{x}  expiry=%{y}  observed=%{z}<extra></extra>",
        )
    )
    fig.update_layout(
        **T.figure_layout(
            title=T.title(f"{field} occupancy"),
            xaxis=T.axis("Strike ($)", tickangle=-45),
            yaxis=T.axis("Expiry"),
            height=380,
            margin=dict(l=72, r=16, t=56, b=56),
            annotations=[
                T.caption("Lit cell = a number exists &nbsp;·&nbsp; Dark cell = no quote that day")
            ],
        )
    )
    return fig
