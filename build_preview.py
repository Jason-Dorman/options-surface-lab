"""Build the published page: one self-contained HTML file, no Reflex, no backend.

This is the deliverable (AD-4). CI runs it, copies the output to _site/index.html and
publishes that to GitHub Pages.

Layout is the terminal arrangement from DESIGN-BRIEF §5: a command bar, a strip of readouts,
then numbered panels on a 10-column hairline grid — the 3D surface at 7 columns with the
underlying beside it at 3, then the remaining figures 5+5 beneath. All chrome comes from
`theme.PAGE_CSS`; this module contains no colour, font or measurement of its own
(FR-8 / AD-6).
"""

from pathlib import Path

# Grepped for by the CI publish guard — see .github/workflows/pages.yml.
SYNTHETIC_MARKER = "synthetic panel"

import pandas as pd

from options_surface_lab import theme as T
from options_surface_lab.option_surface_plot import (
    as_panel_figure,
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
    #
    # The hero keeps its own title — the slider rewrites it on every step, so it has to live
    # inside the figure JSON. Every tiled figure hands its title to its panel header instead.
    fig_surface = static_surface_figure(wide, ticker=ticker)
    fig_cmp = as_panel_figure(settle_vs_trade_figure(wide, asof, ticker=ticker))
    # The underlying rides beside the hero at its full height: spot is what makes "near the
    # money" mean anything, and the dense region of the cloud is exactly the near-the-money
    # band. Matching HERO_FIGURE_HEIGHT keeps the row from ending ragged.
    fig_cs = as_panel_figure(
        candlestick_figure(payload["stock"], ticker), height=T.HERO_FIGURE_HEIGHT
    )
    fig_hm_s = as_panel_figure(coverage_heatmap(wide, asof, cp="C", field="MARK"))
    fig_hm_t = as_panel_figure(coverage_heatmap(wide, asof, cp="C", field="TRDPRC_1"))
    fig_spread = as_panel_figure(spread_heatmap(wide, asof, cp="C"))

    out = Path(__file__).resolve().parent / "options_surface_preview.html"

    asof_txt = str(pd.Timestamp(asof).date()) if asof is not None else "n/a"
    mark_label = MARK_FIELD_DEFAULT
    med = stats["median_abs_diff"]
    med_txt = "n/a" if med is None else f"${med:.3f}"
    rel = stats["median_rel_diff_pct"]
    rel_txt = "n/a" if rel is None else f"{rel:.1f}%"
    sp, sp_pct = stats["median_spread"], stats["median_spread_pct"]
    spread_txt = "n/a" if sp is None else f"${sp:.2f} ({sp_pct:.0f}%)"
    n_series = int(wide["ric"].nunique()) if len(wide) else 0

    # Shown ONLY when the build fell back to generated data. The CI guard in
    # .github/workflows/pages.yml greps the page for SYNTHETIC_MARKER and refuses to publish,
    # because a synthetic page renders plausibly and invents marks that do not exist.
    # tests/test_build_preview.py pins the marker to the workflow so the two cannot drift.
    warning = (
        f'<div class="osl-warn">Built from a {SYNTHETIC_MARKER}, not the LSEG pull — '
        f"this must not be published.</div>"
        if payload.get("synthetic")
        else ""
    )

    bar = f"""
    <div class="osl-bar">
      <div class="osl-wordmark">Options Surface Lab</div>
      <div class="osl-ident">
        <b>{ticker}</b> listed options &nbsp;·&nbsp; mark = <b>{mark_label}</b>
        &nbsp;·&nbsp; as-of <b>{asof_txt}</b> &nbsp;·&nbsp; {n_series} series in panel
      </div>
    </div>
    """

    readouts = "".join(
        _readout(label, value)
        for label, value in (
            (f"Series on {asof_txt}", stats["n_quotes"]),
            ("Mark, no print", f"{stats['n_mark_only']} ({stats['pct_mark_no_trade']:.0f}%)"),
            ("Both mark &amp; print", stats["n_both"]),
            ("Median |mark − trade|", med_txt),
            ("Median relative gap", rel_txt),
            ("Median bid-ask spread", spread_txt),
        )
    )

    # The grid, in the reading order of the argument (DESIGN-BRIEF §5):
    #   row 1  the surface, with the underlying beside it as spot context
    #   row 2  the evidence that mark ≠ print, and whether the mark is believable at all
    #   row 3  where the data simply is not there — the two occupancy grids, paired so they
    #          can be compared directly, which is the whole point of showing both
    panels = [
        _panel(1, "Price surface · 3D", "drag the slider · legend toggles puts",
               fig_surface, width=T.W_HERO),
        _panel(2, f"{ticker} underlying", "spot context · close = TRDPRC_1",
               fig_cs, width=T.W_SIDECAR),
        _panel(3, "Mark vs print", f"{mark_label} against TRDPRC_1", fig_cmp),
        _panel(4, "Spread · can you believe the mark?", "bid-ask as % of the mark", fig_spread),
        _panel(5, "Mark occupancy", "lit = a mark exists", fig_hm_s),
        _panel(6, "Print occupancy", "lit = someone traded", fig_hm_t),
    ]

    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>Options Surface Lab</title>",
        T.GOOGLE_FONTS_LINK,
        f"<style>{T.PAGE_CSS}</style></head><body>",
        bar,
        f'<div class="osl-readouts">{readouts}</div>',
        warning,
        '<div class="osl-grid">',
        *panels,
        "</div>",
        "</body></html>",
    ]
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {out}  asof={asof}  quotes={stats['n_quotes']}  synthetic={payload.get('synthetic')}")
    return out


def _readout(label: str, value) -> str:
    """One cell of the readout strip under the command bar. Styling is in theme.PAGE_CSS."""
    return (
        '<div class="osl-readout">'
        f'<div class="osl-readout-label">{label}</div>'
        f'<div class="osl-readout-value">{value}</div>'
        "</div>"
    )


def _panel(n: int, name: str, note: str, fig, width: int = None) -> str:
    """A numbered panel: a header rule carrying `[n] NAME` and a note, then the figure.

    `width` is in grid columns out of `theme.GRID_COLUMNS` (default: half the row).

    Plotly.js is requested from the CDN by the first panel only. Asking six times emitted the
    same `<script src>` six times — harmless in a browser, but it made the page's single
    external dependency six times harder to see when auditing it against NFR-4.
    """
    global _plotly_included
    body = fig.to_html(
        full_html=False, include_plotlyjs=("cdn" if not _plotly_included else False)
    )
    _plotly_included = True
    return (
        f'<div class="osl-panel osl-w{width or T.W_HALF}">'
        '<div class="osl-panel-head">'
        f'<div><span class="osl-panel-n">[{n}]</span>'
        f'<span class="osl-panel-name">{name}</span></div>'
        f'<div class="osl-panel-note">{note}</div>'
        "</div>"
        f'<div class="osl-panel-body">{body}</div>'
        "</div>"
    )


# Module-level so the library is emitted exactly once per page. Kept beside its only writer.
_plotly_included = False


if __name__ == "__main__":
    main()
