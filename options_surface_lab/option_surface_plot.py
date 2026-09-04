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
from options_surface_lab.option_surface_utils import (
    MARK_FIELD_DEFAULT,
    RISK_FREE_RATE,
    attach_implied_vol,
    summarize_sparsity,
    surface_grid,
)

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

# FR-10: the strike axis can be read in dollars or rebased to spot. Two dates of a moving
# underlying are not comparable in K — the same $12.50 strike is 10% out of the money one
# week and at the money the next — but they line up in K / S, where 1.00 is always the money.
#
# The mode changes the *ruler*, never the data: the same points and the same interpolated
# sheet, re-measured. `moneyness` is already on the wide table (`attach_underlying`), so a
# switch reads a different column rather than recomputing anything.
X_MODES = ("strike", "moneyness")
X_AXIS_TITLE = {"strike": "Strike ($)", "moneyness": "Moneyness  K / S"}
X_MODE_LABEL = {"strike": "Strike (K)", "moneyness": "Moneyness (K/S)"}


def _x_values(frame: pd.DataFrame, x_mode: str):
    """The X coordinate of a point cloud under FR-10's axis mode.

    A row whose date has no underlying close has no moneyness, so it plots as a hole in K/S
    mode. That is the correct outcome: drawing its raw strike against a K/S axis would put a
    number on the page that means something other than what the axis says (AD-9).
    """
    if x_mode != "moneyness":
        return frame["strike"]
    if "moneyness" in frame.columns:
        return frame["moneyness"]
    if "spot" in frame.columns:
        return frame["strike"] / frame["spot"]
    return pd.Series(np.nan, index=frame.index)


def _sheet_x(grid: dict, x_mode: str, spot: float | None):
    """The interpolated sheet's X, in the chosen ruler.

    Within one as-of date the spot is a single number, so moneyness is an exact affine
    rescale of the strike axis and the sheet can simply be re-measured. Re-running
    :func:`surface_grid` in K/S space would re-triangulate the cloud and could hand back a
    subtly different surface for what has to be one object — the toggle must move the ruler,
    not the data. No spot that day means no K/S sheet, rather than a wrong one.
    """
    if x_mode != "moneyness":
        return grid["x"]
    if not spot:
        return np.full(len(grid["x"]), np.nan)
    return grid["x"] / spot


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


def as_panel_figure(
    fig: go.Figure, height: int | None = None, margin: dict | None = None
) -> go.Figure:
    """Strip a figure's own title and tighten it for a tiled panel (DESIGN-BRIEF §5).

    In the terminal layout each panel carries a header rule with its number and name, so a
    Plotly title inside the plot area would say the same thing twice and eat a third of the
    tile. The caption annotation stays — it is the "how to read this" line, not a label.

    Not applied to the hero surface: its title tracks the as-of slider, so it has to live
    inside the figure JSON where the slider can rewrite it (AD-5).

    ``margin`` overrides the tile default for panels that are not tiles. The tile margin
    reserves 30px above the plot, which is enough for a figure whose whole top band is now
    empty and nowhere near enough for one still carrying a legend and two caption lines —
    and an annotation pushed off the paper does not warn, it just stops drawing.
    """
    return fig.update_layout(
        title_text=None,
        margin=margin or T.PANEL_FIGURE_MARGIN,
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


def _mark_trace(
    frame: pd.DataFrame, cp: str, name: str, x_mode: str = "strike", **overrides
) -> go.Scatter3d:
    st = SERIES_STYLE[(cp, "mark")]
    return go.Scatter3d(
        x=_x_values(frame, x_mode),
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


def _trade_trace(
    frame: pd.DataFrame, cp: str, name: str, x_mode: str = "strike", **overrides
) -> go.Scatter3d:
    st = SERIES_STYLE[(cp, "trade")]
    return go.Scatter3d(
        x=_x_values(frame, x_mode),
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


def _sheet_trace(
    grid: dict, cp: str, name: str, x_mode: str = "strike", spot: float | None = None,
    **overrides,
) -> go.Surface:
    """The interpolated sheet — translucent and label-led, because it is not a market."""
    return go.Surface(
        x=_sheet_x(grid, x_mode, spot),
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


def _surface_scene(x_mode: str = "strike") -> dict:
    # near-dated in front: reverse DTE so 0 sits toward the viewer
    return T.scene(
        xaxis=T.scene_axis(X_AXIS_TITLE[x_mode]),
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
    x_mode: str = "strike",
) -> go.Figure:
    """The hero surface for local dev. ``x_mode`` picks FR-10's ruler (``X_MODES``)."""
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
        fig.add_trace(_mark_trace(s, style_cp, "MARK", x_mode=x_mode))
        if show_interpolated:
            grid = surface_grid(s, "MARK")
            if grid is not None:
                fig.add_trace(
                    _sheet_trace(
                        grid, style_cp, "Interpolated sheet", x_mode=x_mode, spot=spot_val
                    )
                )

    if show_trade and sl["TRDPRC_1"].notna().any():
        t = sl.dropna(subset=["TRDPRC_1"])
        fig.add_trace(_trade_trace(t, style_cp, "TRDPRC_1", x_mode=x_mode))

    fig.update_layout(
        **T.figure_layout(
            title=T.title(f"{ticker}  {cp_label}  ·  {asof_txt}{spot_txt}"),
            scene=_surface_scene(x_mode),
            legend=T.legend(),
            # Same height as the published page's hero, because it sits in the same
            # panel slot. A figure taller than its panel overflows into the row below.
            height=T.HERO_FIGURE_HEIGHT,
            margin=T.HERO_MARGIN,
            annotations=[
                T.caption(
                    "The translucent sheet is interpolated — not a market",
                    y=T.CAPTION_Y_OVER_LEGEND,
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

    * **Strike or moneyness — a button pair** (FR-10 / T-16). The axis toggle *is* a second
      menu, and it composes with the slider for a reason the date/right pair could not: the
      two mutate disjoint properties. Slider steps write only ``visible``; the axis buttons
      write only ``x`` and the scene's X title. Neither can undo the other, so a reader can
      rebase to K/S and then walk the whole window in moneyness.

    Putting the right on the legend rather than a second menu is what makes the first two
    controls compose. Plotly buttons apply a fixed visibility array and cannot read another
    menu's state, so a second *visibility* dropdown would fight the first; the legend is
    orthogonal by construction. Known limitation: moving the slider re-applies visibility, so
    legend choices reset on a date change.

    The axis toggle carries one x array per trace per mode rather than a second set of
    pre-rendered traces. Same behaviour, a fraction of the weight: duplicating 300-odd traces
    would roughly double a 2.4 MB page to change the units on one axis, while duplicating one
    of each trace's three coordinate arrays costs +205 KB raw / ~+70 KB gzipped. (SPEC §12
    originally sketched the trace pair; that sketch was written while the brief still expected
    the published page to lose functionality, and the PO retired it on 2026-09-04.)

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
    # One x array per trace per mode, in trace order — the axis buttons' payload (FR-10).
    xs = {mode: [] for mode in X_MODES}

    def _record_x(source, spot=None):
        """Remember this trace's x under both rulers. Called once per `add_trace`, in order."""
        for mode in X_MODES:
            xs[mode].append(
                _arr(_sheet_x(source, mode, spot) if isinstance(source, dict)
                     else _x_values(source, mode))
            )

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
                _record_x(mk)
                idx[(cp, "mark")] = len(fig.data) - 1

                grid = surface_grid(mk, "MARK")
                if grid is not None:
                    fig.add_trace(
                        _sheet_trace(
                            grid, cp, f"Interpolated sheet · {right}",
                            visible=False, showlegend=True, legendgroup=f"sheet-{cp}",
                        )
                    )
                    _record_x(grid, spots.get(asof))
                    idx[(cp, "sheet")] = len(fig.data) - 1

            tr = sl.dropna(subset=["TRDPRC_1"])
            if len(tr):
                fig.add_trace(
                    _trade_trace(
                        tr, cp, f"TRDPRC_1 · {right}",
                        visible=False, legendgroup=f"trade-{cp}",
                    )
                )
                _record_x(tr)
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

    # Disjoint from the slider by construction: these write `x` and the scene's X title,
    # the steps above write `visible`. That is what lets the two controls be used together.
    axis_buttons = [
        dict(
            method="update",
            label=X_MODE_LABEL[mode],
            args=[{"x": xs[mode]}, {"scene.xaxis.title.text": X_AXIS_TITLE[mode]}],
        )
        for mode in X_MODES
    ]

    fig.update_layout(
        **T.figure_layout(
            title=T.title(_title(per_date[default][0])),
            scene=_surface_scene(),
            legend=T.legend(font=dict(size=T.SIZE_TICK, color=T.TEXT, family=T.FONT_BODY)),
            sliders=[T.slider(active=default, steps=steps)],
            updatemenus=[T.menu(buttons=axis_buttons, active=0)],
            height=T.HERO_FIGURE_HEIGHT,
            margin=T.HERO_MARGIN_WITH_SLIDER,
            annotations=[
                # Short on purpose: the panel header already says "drag the slider · legend
                # toggles puts", and the long version ran the width of the plot and straight
                # into the legend. What is left is the one thing no other chrome says (AD-9).
                T.caption(
                    "The translucent sheet is interpolated — not a market",
                    y=T.CAPTION_Y_OVER_LEGEND,
                )
            ],
        )
    )
    return fig


def diagonal_range(both: pd.DataFrame) -> tuple[float, float]:
    """Padded [lo, hi] covering both series, for the y = x line and the square axes.

    Shared with the as-of update payload so the line and the axis range a slider step
    installs are computed the same way the figure computed them.
    """
    if not len(both):
        return 0.0, 1.0
    lo = float(min(both["TRDPRC_1"].min(), both["MARK"].min()))
    hi = float(max(both["TRDPRC_1"].max(), both["MARK"].max()))
    pad = (hi - lo) * 0.06 if hi > lo else 0.05
    return lo - pad, hi + pad


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

    # One trace per right, not one trace coloured by a mapped array. The array version
    # produced a single unlabelled legend entry, so a reader had no way to confirm the puts
    # were there at all — and with the old put hue sitting next to the call hue, the honest
    # first read was "the puts are missing". Two named traces make the split explicit, and
    # the legend doubles as a filter.
    #
    # Both rights draw the mark, so both are circles; hue alone separates them, which is why
    # the two hues are 83 degrees apart rather than neighbouring shades.
    #
    # All four traces are ALWAYS added, empty ones included, so the trace order is
    # [Calls, Puts, y = x, bars] on every date. The published page restyles this figure by
    # trace index when the as-of slider moves (AD-5); an index that shifts because a date
    # happened to have no puts would put put data into the calls trace.
    for cp, label, colour, symbol in (
        ("C", "Calls", T.MARK, T.SYMBOL_MARK),
        ("P", "Puts", T.MARK_PUT, T.SYMBOL_MARK_PUT),
    ):
        side = both[both["cp"] == cp]
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
                customdata=(
                    np.stack([side["ric"].astype(str), side["strike"], side["dte"]], axis=1)
                    if len(side)
                    else None
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

    lo, hi = diagonal_range(both)
    fig.add_trace(
        go.Scatter(
            x=[lo, hi],
            y=[lo, hi],
            mode="lines",
            line=dict(color=T.TEXT_MUTED, dash="dash", width=1),
            name="y = x",
            showlegend=True,
        ),
        row=1,
        col=1,
    )
    fig.update_xaxes(range=[lo, hi], row=1, col=1)
    fig.update_yaxes(range=[lo, hi], row=1, col=1)

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
                # Default caption band, not 1.10. The raised position cleared this figure's
                # own title, but every call site panelises it — and `as_panel_figure` drops
                # the title and cuts the top margin to the tile default, which put the
                # caption above the paper where it rendered as a row of sheared glyph tops.
                # Shipped that way; found by adversarial review 2026-09-04.
                T.caption(
                    "Green = tight, tradeable · Red = the midpoint is a guess between "
                    "two far-apart quotes",
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


def panel_expiries(wide: pd.DataFrame) -> list:
    """Every expiry in the panel, chronological — the smile's trace ladder.

    Fixed panel-wide rather than per date, for two reasons that both matter. The published
    page restyles this figure by trace index when the as-of slider moves, so a trace list that
    grew or shrank with the date would put one expiry's curve into another's slot (the
    contract `settle_vs_trade_figure` and the IV cloud already live under). And a fixed ladder
    means an expiry keeps the same colour on every step, so the eye can follow one curve
    across the whole window instead of re-reading the legend at each date.
    """
    if wide is None or wide.empty or "expiry" not in wide.columns:
        return []
    return sorted(pd.to_datetime(pd.Series(wide["expiry"].unique())).dt.normalize().unique())


def _smile_points(frame: pd.DataFrame, x_mode: str, spot: float | None):
    """One expiry's curve: x, and IV% with a hole at every strike that refused.

    Built over the strikes **listed** that day, not over the strikes that inverted, so a
    refused strike becomes a `None` in the middle of the line. With `connectgaps=False` that
    draws as a break — the gap is visible *as* a gap rather than being bridged by a segment
    the data does not support (AD-9). Bridging holes is the one thing a line chart does that
    a scatter cannot, so it has to be switched off deliberately.

    Both rights collapse to their median at each strike. Put-call parity says they should
    agree; where they do not, the disagreement is a property of the input (American exercise,
    a stale midpoint), not of the smile, and it belongs in panel [4]'s argument rather than as
    a second tangle of lines here.
    """
    if frame.empty:
        return [], []
    per_strike = frame.groupby("strike")["iv"].median().sort_index()
    strikes = per_strike.index.to_numpy(float)
    if x_mode == "moneyness":
        if not spot:
            return [], []          # no spot that day means no K/S ruler at all (FR-10, AD-9)
        xs = strikes / spot
    else:
        xs = strikes
    ys = [None if v != v else round(float(v) * 100.0, 3) for v in per_strike.to_numpy(float)]
    return [round(float(x), 4) for x in xs], ys


def iv_smile_figure(
    wide: pd.DataFrame,
    asof,
    ticker: str = "UUUU",
    x_mode: str = X_MODES[0],
    rate: float = RISK_FREE_RATE,
    height: int | None = None,
) -> go.Figure:
    """FR-11: the implied-vol smile — one curve per expiry, holes and all.

    Replaced a 3D scatter of the same numbers on 2026-09-04 (PO): over a 2.6:1 panel the cloud
    read as scattered points with no discernible message. In two dimensions the same data has
    a shape you can name — vol rises into the wings, and the near-dated curves are far steeper
    than the far-dated ones. On the committed panel's busiest date the 7-day expiry spans
    63-130% while the 42-day expiry spans 76-83%: that flattening *is* the term structure of
    the smile, and it was invisible in 3D.

    What the figure is still careful to say it is not:

    * Not observed. Every point is a model output three assumptions deep — European exercise
      on American contracts, no dividends, and a mark that is itself a derived midpoint
      (there is no settlement price for these contracts, checkpoint_audit §3).
    * Not tradable. Panel [4] is the companion that says how far apart the two sides of the
      market were when this "price" was struck.

    Trace order and count are a contract: one trace per expiry in :func:`panel_expiries`,
    always, empty ones included, because the published page restyles by index (AD-5, T-42).

    ``x_mode`` defaults to ``X_MODES[0]`` rather than to moneyness — which is the more natural
    ruler for a smile — so that it matches the ruler the hero's axis menu opens on
    (``updatemenus`` ``active=0``). The two panels are driven by one control on the published
    page (T-43) and must therefore agree at load; every other axis on the page is in dollar
    strikes at that point, so opening in dollars keeps the whole page in one unit (PO,
    2026-09-04).
    """
    height = height or T.PANEL_FIGURE_HEIGHT
    expiries = panel_expiries(wide)
    if not expiries:
        return _empty_figure("No quotes", height=height)

    sl = _slice_wide(wide, asof, cp="B")
    if "iv" not in sl.columns and not sl.empty:
        sl = attach_implied_vol(sl, rate=rate)

    spot = sl["spot"].dropna() if not sl.empty else pd.Series(dtype=float)
    spot_val = float(spot.median()) if len(spot) else None
    colors = T.expiry_colors(len(expiries))

    fig = go.Figure()
    # Counted in STRIKES, not contract-days, because a strike is what the reader can see: a
    # call and a put at the same strike share one point (their median), so a caption quoting
    # contract-days invites a count that will never match the dots on screen. The panel-wide
    # contract-day figure lives in the docs; this line has to describe this chart.
    n_drawn = n_strikes = 0
    for expiry, color in zip(expiries, colors):
        side = (
            sl[sl["expiry"].dt.normalize() == expiry]
            if not sl.empty
            else sl
        )
        xs, ys = _smile_points(side, x_mode, spot_val)
        drawn = sum(1 for v in ys if v is not None)
        n_drawn += drawn
        n_strikes += len(xs)
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines+markers",
                name=pd.Timestamp(expiry).strftime("%b %d"),
                connectgaps=False,   # a refused strike is a break, never a bridged segment
                line=dict(color=color, width=T.SMILE_LINE_WIDTH),
                marker=dict(
                    color=color, size=T.SMILE_MARKER_SIZE, symbol=T.SYMBOL_MARK,
                    line=dict(width=0),
                ),
                showlegend=drawn > 0,
                hovertemplate=(
                    "<b>%{fullData.name}</b> expiry<br>"
                    + ("K / S" if x_mode == "moneyness" else "K")
                    + " %{x:.3f}<br>implied vol %{y:.1f}%<extra></extra>"
                ),
            )
        )

    asof_txt = str(pd.Timestamp(asof).date()) if asof is not None else "all dates"
    fig.update_layout(
        **T.figure_layout(
            title=T.title(f"{ticker}  ·  implied vol from {MARK_LABEL}  ·  {asof_txt}"),
            xaxis=T.axis(X_AXIS_TITLE[x_mode]),
            yaxis=T.axis("Implied vol (%)"),
            legend=T.legend(
                yanchor="top", y=T.SMILE_LEGEND_Y, x=0.0, xanchor="left",
                bgcolor=T.TRANSPARENT, bordercolor=T.BORDER,
            ),
            height=height,
            margin=T.SMILE_MARGIN,
            annotations=[
                # ORDER IS A CONTRACT, like the trace order: [0] is date-independent, [1]
                # carries per-date counts and the as-of listener rewrites it by index
                # (IV_COUNT_ANNOTATION). See the T-44 note on `_smile`.
                #
                # Both lines are kept short enough to fit a 5-column tile. The first build
                # ran the assumptions off the right edge, which loses exactly the words FR-11
                # requires to be on the page — the panel header carries the rate too, but the
                # figure has to stand on its own because that is what survives onto the
                # static page.
                T.caption(
                    f"DERIVED &nbsp;·&nbsp; European Black-Scholes on {MARK_LABEL} "
                    f"&nbsp;·&nbsp; r = {rate:.2%} &nbsp;·&nbsp; no dividends &nbsp;·&nbsp; "
                    "act/365 &nbsp;·&nbsp; American exercise ignored",
                    y=T.CAPTION_Y_OVER_LEGEND,
                ),
                T.caption(
                    f"Not a tradable price &nbsp;·&nbsp; {n_drawn} of {n_strikes} listed "
                    "strikes carry a vol &nbsp;·&nbsp; a break = one the solver refused",
                    y=T.CAPTION_Y,
                ),
            ],
        )
    )
    return fig


# --------------------------------------------------------------- as-of frames (AD-5, T-42)


def _arr(values):
    """A Plotly array as plain JSON: numpy out, NaN -> null (JSON has no NaN)."""
    if values is None:
        return []
    out = []
    for v in list(values):
        if isinstance(v, str):
            out.append(v)
        elif v is None or v != v:  # NaN
            out.append(None)
        else:
            out.append(round(float(v), 4))
    return out


def _grid(fig):
    """The (x, y, z) of a heatmap figure, or None when the date had nothing to draw."""
    if not fig.data or fig.data[0].type != "heatmap":
        return None
    hm = fig.data[0]
    return {
        "x": [str(v) for v in hm.x],
        "y": [str(v) for v in hm.y],
        "z": [_arr(row) for row in hm.z],
    }


# Which annotation on the IV figure carries per-date numbers. Lifted per date and rewritten
# by the listener; see `iv_surface_figure`.
IV_COUNT_ANNOTATION = 1


def _smile(fig):
    """Per-trace x / y / legend visibility + the per-date caption of the IV smile.

    Everything the panel asserts about a date travels with the date — geometry, which expiries
    are alive (so the legend does not advertise curves that are not there), and the caption's
    inversion count. Carrying only geometry is what left the caption quoting the build date on
    52 of 53 slider steps in the 3D version of this panel (T-44).
    """
    if not fig.data or fig.data[0].type != "scatter":
        return None
    notes = fig.layout.annotations
    return {
        "x": [_arr(t.x) for t in fig.data],
        "y": [_arr(t.y) for t in fig.data],
        "show": [bool(t.showlegend) for t in fig.data],
        "note": (
            notes[IV_COUNT_ANNOTATION].text if len(notes) > IV_COUNT_ANNOTATION else None
        ),
    }


def asof_frames(wide: pd.DataFrame, cp: str = "C", dates=None) -> dict:
    """Per-date arrays for every supporting panel the as-of slider drives.

    The published page has no backend, so a Plotly slider can only mutate the figure it lives
    in — that is why T-15 put the as-of control inside the hero and left the other panels
    pinned to one representative date. The result was a page showing two as-of dates at once.
    This payload closes that: the builder embeds it, and a small listener restyles the other
    panels when the slider moves (AD-5).

    Built by **running the real figure builders** for each date and lifting their arrays,
    rather than re-deriving the pivots here. Re-deriving would be faster and would drift the
    first time a builder changed its aggregation; this cannot, by construction.

    Trace indices are part of the contract: `settle_vs_trade_figure` always emits
    [Calls, Puts, y = x, bars] and `iv_smile_figure` always emits one trace per
    expiry in `panel_expiries`, which is why both add empty traces rather than skipping.
    """
    if wide is None or wide.empty:
        return {}
    if dates is None:
        dates = sorted(wide["date"].dt.normalize().unique())

    # Invert ONCE for the whole panel. `iv_smile_figure` recomputes only when the frame it is
    # handed has no `iv` column, so pre-attaching here stops the inversion running twice per
    # date (once per ruler) — 106 solves of the same numbers across a 53-date panel.
    wide = attach_implied_vol(wide)

    frames = {}
    for asof in dates:
        sl = wide[wide["date"] == pd.Timestamp(asof).normalize()]
        cmp_fig = settle_vs_trade_figure(wide, asof)
        calls, puts, line, bars = cmp_fig.data
        both = sl.dropna(subset=["TRDPRC_1", "MARK"])
        lo, hi = diagonal_range(both)
        bar_y = [int(v) for v in bars.y]

        frames[str(pd.Timestamp(asof).date())] = {
            "cmp": {
                "x": [_arr(calls.x), _arr(puts.x), [lo, hi]],
                "y": [_arr(calls.y), _arr(puts.y), [lo, hi]],
                "bars": bar_y,
                "range": [lo, hi],
                "barmax": max(bar_y + [1]) * 1.18,
            },
            # Both rulers, because on the published page the smile's `x` is written by two
            # controls — the as-of slider and the hero's axis menu — and the listener has to
            # be able to produce any (date, mode) pair. `y`, `showlegend` and the caption
            # ride inside each mode rather than beside them: a date with no underlying close
            # has no K/S ruler at all, so in that mode the curves, the legend and the count
            # are all legitimately empty while the strike ruler still draws (AD-9, FR-10).
            "iv": {
                mode: _smile(iv_smile_figure(wide, asof, x_mode=mode)) for mode in X_MODES
            },
            "spread": _grid(spread_heatmap(wide, asof, cp=cp)),
            "mark": _grid(coverage_heatmap(wide, asof, cp=cp, field="MARK")),
            "trade": _grid(coverage_heatmap(wide, asof, cp=cp, field="TRDPRC_1")),
            "readouts": asof_readouts(sl),
        }
    return frames


def asof_readouts(sl: pd.DataFrame) -> list[str]:
    """The readout strip's six values for one date, formatted exactly as the builder does.

    Formatted here rather than in the browser so the slider can never produce a number that
    is rounded differently from the one the page was built with.
    """
    stats = summarize_sparsity(sl)
    med, rel = stats["median_abs_diff"], stats["median_rel_diff_pct"]
    sp, sp_pct = stats["median_spread"], stats["median_spread_pct"]
    return [
        f"{stats['n_quotes']}",
        f"{stats['n_mark_only']} ({stats['pct_mark_no_trade']:.0f}%)",
        f"{stats['n_both']}",
        "n/a" if med is None else f"${med:.3f}",
        "n/a" if rel is None else f"{rel:.1f}%",
        "n/a" if sp is None else f"${sp:.2f} ({sp_pct:.0f}%)",
    ]
