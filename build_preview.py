"""Build the published page: one self-contained HTML file, no Reflex, no backend.

This is the deliverable (AD-4). CI runs it, copies the output to _site/index.html and
publishes that to GitHub Pages.

Layout is the terminal arrangement from DESIGN-BRIEF §5: a command bar, a strip of readouts,
then numbered panels on a 10-column hairline grid — the 3D surface at 6 columns with the
underlying beside it at 4, two 5+5 rows beneath, and the derived IV surface full width at the
foot. All chrome comes from `theme.PAGE_CSS`; this module contains no colour, font or
measurement of its own (FR-8 / AD-6).
"""

import json
from pathlib import Path

# Grepped for by the CI publish guard — see .github/workflows/pages.yml.
SYNTHETIC_MARKER = "synthetic panel"

import pandas as pd

from options_surface_lab import theme as T
from options_surface_lab.option_surface_plot import (
    X_AXIS_TITLE,
    X_MODES,
    X_MODE_LABEL,
    as_panel_figure,
    asof_frames,
    candlestick_figure,
    coverage_heatmap,
    IV_COUNT_ANNOTATION,
    iv_smile_figure,
    spread_heatmap,
    settle_vs_trade_figure,
    static_surface_figure,
)
from options_surface_lab.option_surface_utils import (
    MARK_FIELD_DEFAULT,
    RISK_FREE_RATE,
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
    # Full width: with the smile taking half of row 2, the three remaining panels cannot tile
    # two rows evenly. Spread goes wide (a strike x expiry grid only gains from the room) so
    # the two occupancy grids stay paired, which is the whole reason both are shown
    # (DESIGN-BRIEF section 5).
    fig_spread = as_panel_figure(spread_heatmap(wide, asof, cp="C"))
    # FR-11. A tile beside the mark-vs-print scatter, directly under the surface it is
    # derived from (PO, 2026-09-04): the smile is the same cloud read through a model, so it
    # belongs next to the price rather than at the foot of the page.
    fig_iv = as_panel_figure(iv_smile_figure(wide, asof, ticker=ticker), margin=T.SMILE_MARGIN)

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
    #   row 2  the same cloud read through a model, beside the evidence that mark ≠ print —
    #          the smile sits under the surface it is derived from (PO, 2026-09-04)
    #   row 3  whether the mark is believable at all
    #   row 4  where the data simply is not there — the two occupancy grids, paired so they
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
        # Header kept to one line: the name and note wrapped on the first build, which made
        # this panel 17px taller than the one beside it — visible on a hairline grid, since
        # panels deliberately do not stretch to their row. The rate lives in the figure's
        # own caption, which is what has to stand alone on the static page anyway.
        _panel(3, "Implied vol · derived",
               "one curve per expiry &nbsp;·&nbsp; a break = the solver refusing",
               fig_iv),
        _panel(4, "Mark vs print", f"{mark_label} against TRDPRC_1", fig_cmp),
        _panel(5, "Spread · can you believe the mark?", "bid-ask as % of the mark",
               fig_spread, width=T.W_FULL),
        _panel(6, "Mark occupancy", "lit = a mark exists", fig_hm_s),
        _panel(7, "Print occupancy", "lit = someone traded", fig_hm_t),
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
        _asof_script(asof_frames(wide, cp="C"), asof_txt),
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
_GRID_PANELS = (("spread", 5), ("mark", 6), ("trade", 7))

# The smile follows the slider by trace rather than by grid: `iv_smile_figure` always emits
# one trace per expiry in `panel_expiries`, panel-wide and chronological, so a restyle by
# index is safe and an expiry keeps its colour across every step.
_SMILE_PANELS = (("iv", 3),)


def _asof_script(frames: dict, default_label: str) -> str:
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
    # Belt and braces: a build date missing from its own payload would leave the toggle
    # pointing at nothing. Fall back to the first date rather than to `undefined`.
    default_label = default_label if default_label in frames else next(iter(frames))
    grids = ", ".join(f'["{key}", "{FIG_ID_PREFIX}{n}"]' for key, n in _GRID_PANELS)
    iv_note = IV_COUNT_ANNOTATION
    smiles = ", ".join(f'["{key}", "{FIG_ID_PREFIX}{n}"]' for key, n in _SMILE_PANELS)
    # The hero's axis menu is labelled, not keyed, so the listener maps label -> mode. Both
    # sides come from the same two dicts in the plot module, so a renamed mode cannot leave
    # the map behind.
    mode_by_label = json.dumps({X_MODE_LABEL[m]: m for m in X_MODES})
    mode_titles = json.dumps({m: X_AXIS_TITLE[m] for m in X_MODES})
    default_mode = X_MODES[0]
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
  var SMILES = [{smiles}];
  var CMP = "{FIG_ID_PREFIX}4";

  // The smile's `x` is the one property on this page written by TWO controls: the as-of
  // slider picks the date, the hero's axis menu picks the ruler. T-16's rule — that two
  // Plotly controls must write disjoint properties — is about controls acting on the figure
  // *directly*; here neither one does. Both feed this listener, it holds the (date, mode)
  // pair, and it is the only writer. That is what lets them compose instead of fighting.
  var MODE_BY_LABEL = {mode_by_label};
  var MODE_TITLE = {mode_titles};
  var mode = "{default_mode}";   // must match the hero's updatemenus active index
  // The date the page is currently showing. Seeded with the BUILD date rather than left null:
  // the axis toggle re-reads the current date under the new ruler, and a null here sent it to
  // whichever date happened to be first in the payload — so toggling the ruler before ever
  // touching the slider silently swapped the smile to another date's data. Caught in a real
  // browser, 2026-09-04; nothing in the figure JSON could have shown it.
  var current = "{default_label}";

  function applySmile(f) {{
    if (!f) return;
    for (var c = 0; c < SMILES.length; c++) {{
      var byMode = f[SMILES[c][0]];
      var sm = byMode && byMode[mode];
      if (!sm) continue;                      // a date the model could not invert at all
      try {{
        // One trace per expiry, panel-wide and chronological, so the indices are stable.
        // `showlegend` rides along so the legend stops advertising expiries that are not
        // alive on this date, and so does the caption, which counts THIS date's strikes.
        var idx = [];
        for (var t = 0; t < sm.x.length; t++) idx.push(t);
        Plotly.restyle(SMILES[c][1], {{x: sm.x, y: sm.y, showlegend: sm.show}}, idx);
        var re = {{"xaxis.title.text": MODE_TITLE[mode]}};
        if (sm.note) re["annotations[{iv_note}].text"] = sm.note;
        Plotly.relayout(SMILES[c][1], re);
      }} catch (e) {{}}
    }}
  }}

  function apply(label) {{
    var f = frames[label];
    if (!f) return;
    current = label;

    for (var i = 0; i < GRIDS.length; i++) {{
      var g = f[GRIDS[i][0]];
      if (!g) continue;                       // a date with nothing to draw keeps its panel
      try {{
        Plotly.restyle(GRIDS[i][1], {{x: [g.x], y: [g.y], z: [g.z]}}, [0]);
      }} catch (e) {{}}
    }}

    applySmile(f);

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

  // The hero's axis menu relabels the SURFACE by itself (its buttons carry the x arrays for
  // both rulers). The smile has no menu of its own, so it learns the mode from this event
  // and re-reads the current date under it — which is why the payload carries both rulers.
  hero.on("plotly_buttonclicked", function (e) {{
    try {{
      var label = e && e.button && e.button.label;
      var next = MODE_BY_LABEL[label];
      if (!next || next === mode) return;
      mode = next;
      applySmile(frames[current]);
    }} catch (err) {{}}
  }});
}})();
</script>"""


# Module-level so the library is emitted exactly once per page. Kept beside its only writer.
_plotly_included = False


if __name__ == "__main__":
    main()
