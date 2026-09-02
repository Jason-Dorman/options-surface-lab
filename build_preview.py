"""Generate a standalone HTML preview of the surface lab (no Reflex required)."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from options_surface_lab.option_surface_plot import (
    candlestick_figure,
    coverage_heatmap,
    spread_heatmap,
    settle_vs_trade_figure,
    static_surface_figure,
)
from options_surface_lab.option_surface_utils import (
    MARK_FIELD_DEFAULT,
    attach_underlying,
    flatten_lseg_options,
    load_payload,
    summarize_sparsity,
    pivot_trade_settle,
)


def main() -> Path:
    payload = load_payload("option_pipeline_data.pkl")
    tidy = flatten_lseg_options(payload["options"])
    tidy = attach_underlying(tidy, payload["stock"])
    wide = pivot_trade_settle(tidy)
    ticker = payload.get("ticker", "UUUU")

    # busiest date, matching the app: the last date of a weeklies panel has a single
    # expiry alive and is the thinnest possible view
    asof = wide.groupby(wide["date"].dt.normalize()).size().idxmax() if len(wide) else None
    stats = summarize_sparsity(wide[wide["date"] == asof] if asof is not None else wide)

    # One figure carrying every (date, right) combination: a date slider plus legend toggles.
    # The published page has no backend, so this is the only interactivity that survives
    # (AD-5 / T-15). Its own as-of selector is independent of `asof` below, which fixes the
    # supporting figures and the headline numbers to a single representative date.
    fig_surface = static_surface_figure(wide, ticker=ticker)
    fig_cmp = settle_vs_trade_figure(wide, asof, ticker=ticker)
    fig_hm_s = coverage_heatmap(wide, asof, cp="C", field="MARK")
    fig_hm_t = coverage_heatmap(wide, asof, cp="C", field="TRDPRC_1")
    fig_spread = spread_heatmap(wide, asof, cp="C")
    fig_cs = candlestick_figure(payload["stock"], ticker)

    out = Path(__file__).resolve().parent / "options_surface_preview.html"

    asof_txt = str(pd.Timestamp(asof).date()) if asof is not None else "n/a"
    mark_label = MARK_FIELD_DEFAULT
    med = stats["median_abs_diff"]
    med_txt = "n/a" if med is None else f"${med:.3f}"
    rel = stats["median_rel_diff_pct"]
    rel_txt = "n/a" if rel is None else f"{rel:.1f}%"
    sp, sp_pct = stats["median_spread"], stats["median_spread_pct"]
    spread_txt = "n/a" if sp is None else f"${sp:.2f} ({sp_pct:.0f}%)"

    banner = f"""
    <div style="font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
                background:#0d1117; color:#e6edf3; padding:28px 32px 8px 32px;">
      <div style="color:#00ffcc; letter-spacing:2px; font-size:22px; font-weight:700;">
        OPTIONS SURFACE LAB — PREVIEW
      </div>
      <p style="color:#8b949e; max-width:820px; line-height:1.5;">
        As-of <span style="color:#e6edf3;">{pd.Timestamp(asof).date() if asof is not None else 'n/a'}</span>
        for <span style="color:#39d353;">{ticker}</span>
        {'(synthetic panel — drop option_pipeline_data.pkl next to this file to use your LSEG pull)'
          if payload.get('synthetic') else '(loaded from option_pipeline_data.pkl)'}.
        Cyan marks are the quoted <b>mark</b> (MID_PRICE). Magenta diamonds are <b>TRDPRC_1</b> prints. US listed equity options have no exchange settlement price — every mark is derived.
        The interpolated sheet is a convenience, not a market.
        <b>Drag the slider under the 3D figure</b> to change the as-of date — every trading day
        in the window is there. Puts start hidden: click <b>{mark_label} · puts</b> or
        <b>TRDPRC_1 · puts</b> in the legend to bring them in, or click any legend entry to hide
        it. The numbers above and the supporting charts below are fixed to {asof_txt}.
      </p>
      <div style="display:flex; gap:16px; flex-wrap:wrap; margin:12px 0 8px 0;">
        {_card('Series on this date', stats['n_quotes'])}
        {_card('Mark, no print', f"{stats['n_mark_only']} ({stats['pct_mark_no_trade']:.0f}%)")}
        {_card('Both mark &amp; print', stats['n_both'])}
        {_card('Median |mark − trade|', med_txt)}
        {_card('Median relative gap', rel_txt)}
        {_card('Median bid-ask spread', spread_txt)}
      </div>
    </div>
    """

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>Options Surface Lab Preview</title>",
        "<style>body{margin:0;background:#0d1117;}</style></head><body>",
        banner,
    ]
    for fig in (fig_cs, fig_surface, fig_cmp, fig_hm_s, fig_hm_t, fig_spread):
        parts.append(fig.to_html(full_html=False, include_plotlyjs="cdn"))
    parts.append("</body></html>")
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {out}  asof={asof}  quotes={stats['n_quotes']}  synthetic={payload.get('synthetic')}")
    return out


def _card(label: str, value) -> str:
    return (
        "<div style='background:#161b22;border:1px solid #30363d;border-radius:8px;"
        "padding:12px 16px;min-width:140px;'>"
        f"<div style='color:#8b949e;font-size:12px;'>{label}</div>"
        f"<div style='color:#00ffcc;font-size:22px;font-weight:700;'>{value}</div>"
        "</div>"
    )


if __name__ == "__main__":
    main()
