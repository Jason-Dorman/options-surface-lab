"""Build the published page: one self-contained HTML file, no Reflex, no backend.

This is the deliverable (AD-4). CI runs it, copies the output to _site/index.html and
publishes that to GitHub Pages.

Layout is the terminal arrangement from DESIGN-BRIEF §5: a command bar, a strip of readouts,
then numbered panels on a 10-column hairline grid — the 3D surface at 7 columns with the
underlying beside it at 3, then the remaining figures 5+5 beneath. All chrome comes from
`theme.PAGE_CSS`; this module contains no colour, font or measurement of its own
(FR-8 / AD-6).
"""

import json
from pathlib import Path

# Grepped for by the CI publish guard — see .github/workflows/pages.yml.
SYNTHETIC_MARKER = "synthetic panel"

import pandas as pd

from options_surface_lab import theme as T
from options_surface_lab.option_surface_plot import (
    as_panel_figure,
    asof_frames,
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
        &nbsp;·&nbsp; as-of <b id="osl-asof">{asof_txt}</b>
        &nbsp;·&nbsp; {n_series} series in panel
      </div>
    </div>
    """

    # Labels carry no date any more — the as-of lives in the command bar and moves with the
    # slider, so a label reading "Series on 2026-07-10" would go stale the moment it moved.
    readouts = "".join(
        _readout(i, label, value)
        for i, (label, value) in enumerate(
            (
                ("Series listed", stats["n_quotes"]),
                ("Mark, no print", f"{stats['n_mark_only']} ({stats['pct_mark_no_trade']:.0f}%)"),
                ("Both mark &amp; print", stats["n_both"]),
                ("Median |mark − trade|", med_txt),
                ("Median relative gap", rel_txt),
                ("Median bid-ask spread", spread_txt),
            )
        )
    )

    # The grid, in the reading order of the argument (DESIGN-BRIEF §5):
    #   row 1  the surface, with the underlying beside it as spot context
    #   row 2  the evidence that mark ≠ print, and whether the mark is believable at all
    #   row 3  where the data simply is not there — the two occupancy grids, paired so they
    #          can be compared directly, which is the whole point of showing both
    panels = [
        # The note is where the hero's two native controls are advertised — the axis toggle
        # is a small button pair in the corner of the plot and nothing else says what the
        # 1.00 on a K/S axis means (FR-10).
        _panel(1, "Price surface · 3D",
               "drag the slider — the whole page follows &nbsp;·&nbsp; "
               "K / S rebases to spot, 1.00 = at the money",
               fig_surface, width=T.W_HERO),
        _panel(2, f"{ticker} underlying", "spot context · 12 weeks · close = TRDPRC_1",
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
        _asof_script(asof_frames(wide, cp="C")),
        "</body></html>",
    ]
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {out}  asof={asof}  quotes={stats['n_quotes']}  synthetic={payload.get('synthetic')}")
    return out


def _readout(index: int, label: str, value) -> str:
    """One cell of the readout strip. Styling is in theme.PAGE_CSS.

    `data-osl-readout` is the slider's handle on the value: the listener looks the cells up by
    index and writes the figures for the selected date into them.
    """
    return (
        '<div class="osl-readout">'
        f'<div class="osl-readout-label">{label}</div>'
        f'<div class="osl-readout-value" data-osl-readout="{index}">{value}</div>'
        "</div>"
    )


def _panel(n: int, name: str, note: str, fig, width: int = None) -> str:
    """A numbered panel: a header rule carrying `[n] NAME` and a note, then the figure.

    `width` is in grid columns out of `theme.GRID_COLUMNS` (default: half the row).

    The plot div takes a stable id (`osl-fig-{n}`) rather than Plotly's random uuid, because
    the as-of listener addresses the panels by id — a uuid regenerated on every build would
    make the wiring unreproducible.

    Plotly.js is requested from the CDN by the first panel only. Asking six times emitted the
    same `<script src>` six times — harmless in a browser, but it made the page's single
    external dependency six times harder to see when auditing it against NFR-4.
    """
    global _plotly_included
    body = fig.to_html(
        full_html=False,
        include_plotlyjs=("cdn" if not _plotly_included else False),
        div_id=f"{FIG_ID_PREFIX}{n}",
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


FIG_ID_PREFIX = "osl-fig-"

# Which panel each frame key updates. Kept beside the script that reads it so a renamed key
# and a stale selector cannot drift apart.
_GRID_PANELS = (("spread", 4), ("mark", 5), ("trade", 6))


def _asof_script(frames: dict) -> str:
    """Embed the per-date frames and the listener that applies them (AD-5).

    A Plotly slider can only mutate the figure it lives in, so without this the hero moved and
    the rest of the page stayed on its build-time date — one page showing two as-of dates.
    This is the published page's only custom JavaScript.

    It fails safe by construction: every branch returns early if the payload, Plotly, or the
    hero div is missing, and each panel updates inside its own try/catch. If any of that
    breaks, the page keeps exactly the behaviour it had before — panels pinned to the default
    date — rather than erroring.
    """
    if not frames:
        return ""
    # `</script>` inside a JSON string would close the tag early; escaping `<` removes the
    # whole class of problem and stays valid JSON.
    payload = json.dumps(frames, separators=(",", ":")).replace("<", "\\u003c")
    grids = ", ".join(f'["{key}", "{FIG_ID_PREFIX}{n}"]' for key, n in _GRID_PANELS)
    return f"""
<script id="osl-frames" type="application/json">{payload}</script>
<script>
(function () {{
  var node = document.getElementById("osl-frames");
  if (!node || typeof Plotly === "undefined") return;
  var frames;
  try {{ frames = JSON.parse(node.textContent); }} catch (e) {{ return; }}
  var hero = document.getElementById("{FIG_ID_PREFIX}1");
  if (!hero || typeof hero.on !== "function") return;

  var GRIDS = [{grids}];
  var CMP = "{FIG_ID_PREFIX}3";

  function apply(label) {{
    var f = frames[label];
    if (!f) return;

    for (var i = 0; i < GRIDS.length; i++) {{
      var g = f[GRIDS[i][0]];
      if (!g) continue;                       // a date with nothing to draw keeps its panel
      try {{
        Plotly.restyle(GRIDS[i][1], {{x: [g.x], y: [g.y], z: [g.z]}}, [0]);
      }} catch (e) {{}}
    }}

    try {{
      // trace order is fixed at [Calls, Puts, y = x, bars] for every date
      Plotly.restyle(CMP, {{x: f.cmp.x, y: f.cmp.y}}, [0, 1, 2]);
      Plotly.restyle(CMP, {{y: [f.cmp.bars], text: [f.cmp.bars]}}, [3]);
      Plotly.relayout(CMP, {{
        "xaxis.range": f.cmp.range,
        "yaxis.range": f.cmp.range,
        "yaxis2.range": [0, f.cmp.barmax]
      }});
    }} catch (e) {{}}

    try {{
      var cells = document.querySelectorAll("[data-osl-readout]");
      for (var j = 0; j < cells.length; j++) {{
        var k = parseInt(cells[j].getAttribute("data-osl-readout"), 10);
        if (f.readouts[k] !== undefined) cells[j].textContent = f.readouts[k];
      }}
      var asof = document.getElementById("osl-asof");
      if (asof) asof.textContent = label;
    }} catch (e) {{}}
  }}

  hero.on("plotly_sliderchange", function (e) {{
    if (e && e.step && e.step.label) apply(e.step.label);
  }});
}})();
</script>"""


# Module-level so the library is emitted exactly once per page. Kept beside its only writer.
_plotly_included = False


if __name__ == "__main__":
    main()
