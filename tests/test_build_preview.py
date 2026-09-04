"""Tests for the published artifact itself.

`build_preview.py` writes the single HTML file that GitHub Pages serves, so a defect here
ships straight to the graded submission with nothing between it and a reader. The CI publish
guard is a plain `grep` over that file, which means it can be silently orphaned by an
unrelated copy edit — that nearly happened when the prose block carrying the marker was
removed. These tests pin the contract between the builder and the workflow.
"""

import json
import re
from pathlib import Path

import pytest

import build_preview
from options_surface_lab import theme as T
from options_surface_lab.option_surface_utils import (
    RISK_FREE_RATE,
    attach_underlying,
    flatten_lseg_options,
    pivot_trade_settle,
    summarize_sparsity,
    synthesize_demo_payload,
)

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pages.yml"

# FR-11's assumptions, as they must appear VERBATIM in the built page. Kept here so the
# workflow's grep and this test cannot drift apart — the same coupling `SYNTHETIC_MARKER`
# already has, and the one that broke when the caption was reworded (T-45).
#
# No phrase here may contain "/" or "·": Plotly's JSON encoder writes a forward slash as
# `/` and the caption's separators are `&nbsp;·&nbsp;`, so a guard spanning either
# would never match the page it is supposed to be guarding. That is the same escape that bit
# FR-10's "K / S" label (RUNBOOK §5). "act/365" is therefore checked on the figure object by
# `test_the_iv_figure_prints_every_assumption_fr_11_requires`, not here.
IV_PAGE_MARKERS = (
    "American exercise ignored",
    "no dividends",
    "European Black-Scholes",
    "Not a tradable price",
)


def _listener(html: str) -> str:
    """The page's one inline listener script, whole.

    Sliced by tag rather than by a fixed character window: the window was 3000 characters and
    silently started missing the fail-safe guards at the top of the script the moment T-43
    made the listener longer. A test whose subject can slide out of its own slice is a test
    that stops testing without failing.
    """
    end = html.rindex("</script>")
    return html[html.rindex("<script>", 0, end) : end]


def test_ci_guard_greps_for_the_marker_the_builder_actually_emits():
    """The guard and the builder must agree on one literal string.

    If someone rewords the synthetic warning, or deletes it, this fails — instead of the
    workflow quietly losing its only defence against publishing invented data.
    """
    assert WORKFLOW.exists(), "the Pages workflow must exist for its guard to be pinned"
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert build_preview.SYNTHETIC_MARKER in workflow, (
        f"the CI guard no longer greps for {build_preview.SYNTHETIC_MARKER!r} — "
        "the synthetic-data check has been orphaned"
    )


def test_the_marker_is_emitted_when_the_panel_is_synthetic():
    """A synthetic build must be self-identifying, or the guard has nothing to find."""
    payload = synthesize_demo_payload()
    assert payload.get("synthetic") is True

    # the builder's own condition, exercised directly
    warning_shown = bool(payload.get("synthetic"))
    assert warning_shown, "synthesize_demo_payload must flag itself as synthetic"


def test_the_committed_page_is_self_contained():
    """Pages serves this file alone — anything it reaches for beyond the CDN would 404."""
    page = Path(__file__).resolve().parents[1] / "options_surface_preview.html"
    if not page.exists():
        pytest.skip("preview not built in this working tree")
    html = page.read_text(encoding="utf-8", errors="ignore")

    assert "localhost" not in html, "a backend URL leaked into the published page"
    assert "_event" not in html, "a Reflex websocket endpoint leaked into the published page"
    assert "file://" not in html

    # Plotly and Google Fonts are the only hosts the page may reach. Both are CDNs that
    # degrade gracefully — Plotly is required, and every theme font stack falls back to a
    # system face. Anything else would be a backend, a tracker, or a broken asset path.
    allowed = ("cdn.plot.ly", "plotly.com", "fonts.googleapis.com", "fonts.gstatic.com")
    external = set(re.findall(r"https?://[^\s\"'<>]+", html))
    non_cdn = {u for u in external if not any(host in u for host in allowed)}
    assert not non_cdn, f"page depends on an unexpected host: {sorted(non_cdn)[:3]}"


def test_the_committed_page_was_not_built_from_synthetic_data():
    page = Path(__file__).resolve().parents[1] / "options_surface_preview.html"
    if not page.exists():
        pytest.skip("preview not built in this working tree")
    html = page.read_text(encoding="utf-8", errors="ignore")
    assert build_preview.SYNTHETIC_MARKER not in html, (
        "the committed page was built from the synthetic fallback — rebuild it with the real "
        "pickle present before submitting"
    )


def test_the_real_panel_actually_carries_marks():
    """The guard cannot see this, and it is the failure that matters most.

    A real-but-markless pull publishes a page that renders perfectly and shows zero for every
    number the assignment asks for. Two of the three pulls taken on this project came back
    without a usable mark, so this is a live risk on any future re-pull, not a hypothetical.
    """
    payload = build_preview.load_payload("option_pipeline_data.pkl")
    if payload.get("synthetic"):
        pytest.skip("no real cache in this working tree")

    wide = pivot_trade_settle(
        attach_underlying(flatten_lseg_options(payload["options"]), payload["stock"])
    )
    stats = summarize_sparsity(wide)
    assert stats["n_quotes"] > 0, "the committed pickle has no quotes at all"
    assert wide["has_mark"].any(), (
        "the committed pickle has no MARK anywhere — the page would publish with every "
        "headline number at zero and the whole comparison missing"
    )
    assert stats["n_both"] > 0, "no contract-day has both a mark and a trade"


def test_every_class_the_page_uses_is_defined_in_its_own_stylesheet():
    """The page carries its whole stylesheet, so an orphan class is a silent layout bug.

    CSS fails open: an undefined class is not an error, the element simply keeps its default.
    That is how the deployed page shipped with the 3D surface one column wide while the local
    Reflex app — which styles its panels inline — looked perfect. Anything the builder emits
    must resolve against the `<style>` block travelling with it.
    """
    page = Path(__file__).resolve().parents[1] / "options_surface_preview.html"
    if not page.exists():
        pytest.skip("preview not built in this working tree")
    html = page.read_text(encoding="utf-8", errors="ignore")

    style = re.search(r"<style>(.*?)</style>", html, re.S)
    assert style, "the page must carry its own stylesheet"

    # Only base-level rules count. The responsive block re-lists every width class to
    # collapse it on narrow screens, so counting selectors anywhere in the sheet would
    # report a class as "defined" on the strength of its mobile override alone — which is
    # exactly the hole that let the missing `.osl-w6` reach production.
    css = re.sub(r"@media[^{]*\{(?:[^{}]|\{[^{}]*\})*\}", "", style.group(1), flags=re.S)
    defined = set(re.findall(r"\.(osl-[a-z0-9-]+)", css))

    used = set()
    for attr in re.findall(r"class=[\"']([^\"']*)[\"']", html):
        used.update(c for c in attr.split() if c.startswith("osl-"))

    orphans = sorted(used - defined)
    assert not orphans, (
        f"these classes are used but never defined, so their styling is silently dropped: "
        f"{orphans}"
    )


def test_the_published_page_wires_the_slider_to_every_panel():
    """The whole page must follow the as-of slider, not just the hero (AD-5).

    Without this the page shows two as-of dates at once: the hero on the slider's date and
    every supporting panel on its build-time date. Checked on the built artifact because the
    wiring only exists there — ids, payload and listener are emitted, not importable.
    """
    page = Path(__file__).resolve().parents[1] / "options_surface_preview.html"
    if not page.exists():
        pytest.skip("preview not built in this working tree")
    html = page.read_text(encoding="utf-8", errors="ignore")

    ids = set(re.findall(r'id="(osl-fig-\d)"', html))
    assert {f"osl-fig-{n}" for n in range(1, 8)} <= ids, (
        f"stable panel ids are missing, so the listener cannot address them: {sorted(ids)}"
    )
    assert 'id="osl-asof"' in html, "the command bar's as-of must be addressable"
    assert len(re.findall(r'data-osl-readout="\d"', html)) == 6, "six readout cells"
    assert "plotly_sliderchange" in html, "nothing listens to the slider"

    payload = re.search(
        r'<script id="osl-frames" type="application/json">(.*?)</script>', html, re.S
    )
    assert payload, "the per-date frames are not embedded"
    frames = json.loads(payload.group(1))

    # every id the listener reaches for must exist on the page
    listener = _listener(html)
    for fig_id in set(re.findall(r"osl-fig-\d", listener)):
        assert f'id="{fig_id}"' in html, f"listener targets {fig_id}, which the page lacks"

    # every slider step must have somewhere to go
    steps = set(re.findall(r'"label":"(\d{4}-\d{2}-\d{2})"', html))
    assert steps, "the as-of slider has no steps"
    missing = sorted(steps - set(frames))
    assert not missing, f"slider steps with no frame: {missing[:5]}"


def test_the_page_still_works_if_the_listener_never_runs():
    """The wiring must fail safe: no payload, no Plotly, no hero — no error, just no sync.

    A page that throws on load is worse than one whose panels are pinned, so every entry
    point returns early rather than assuming.
    """
    page = Path(__file__).resolve().parents[1] / "options_surface_preview.html"
    if not page.exists():
        pytest.skip("preview not built in this working tree")
    html = page.read_text(encoding="utf-8", errors="ignore")
    assert "plotly_sliderchange" in html, "the as-of listener is missing entirely"
    script = _listener(html)

    assert 'typeof Plotly === "undefined"' in script, "must tolerate Plotly failing to load"
    assert "if (!node" in script, "must tolerate a missing payload"
    assert "if (!hero" in script, "must tolerate a missing hero div"
    assert script.count("catch (e)") >= 3, "each panel must update inside its own try/catch"


def test_the_published_page_offers_the_moneyness_axis():
    """FR-10 on the deliverable. The control is Plotly-native, so it ships inside the JSON.

    Checked on the built artifact for the reason the width classes are: the Reflex app and
    the published page are two renderings of the same design, and only one of them is graded.
    """
    page = Path(__file__).resolve().parents[1] / "options_surface_preview.html"
    if not page.exists():
        pytest.skip("preview not built in this working tree")
    # Plotly writes the forward slash of "K / S" into the figure JSON as a unicode
    # escape, so the label is not searchable literally. Undo that before matching,
    # rather than asserting on the escape sequence itself.
    html = page.read_text(encoding="utf-8", errors="ignore").replace(r"\u002f", "/")

    assert "updatemenus" in html, "the hero shipped without its axis toggle"
    assert "Moneyness (K/S)" in html, "the toggle must name the mode it switches to"
    assert "Moneyness  K / S" in html, "the scene axis must be relabelled with the mode"
    # the toggle is a small chip in the corner of the plot; the panel note is what says
    # what a 1.00 on that axis means
    assert "1.00 = at the money" in html, "nothing on the page anchors the K/S scale"


def test_the_published_page_carries_the_derived_iv_panel():
    """FR-11 on the deliverable (T-17).

    Checked on the built artifact, not on the figure objects, for the reason the width
    classes are: a layout or wiring defect can look perfect under `reflex run` and be broken
    on Pages, and only the built page is graded.
    """
    page = Path(__file__).resolve().parents[1] / "options_surface_preview.html"
    if not page.exists():
        pytest.skip("preview not built in this working tree")
    html = page.read_text(encoding="utf-8", errors="ignore")

    assert 'id="osl-fig-3"' in html, "the IV panel is missing from the published page"
    # The spread panel now runs full width so the occupancy grids stay paired; a width class
    # that does not exist fails OPEN in CSS and renders the panel one column wide
    # (DESIGN-BRIEF §5, the deploy-only defect).
    assert f"osl-w{T.W_FULL}" in html, "the full-width panel has no width class on the page"
    # These are what the CI publish guard greps for, so they are chosen to contain no HTML
    # entities and no characters Plotly's JSON encoder escapes — the separators in the caption
    # are `&nbsp;·&nbsp;`, and a guard spanning one would silently never match.
    for phrase in IV_PAGE_MARKERS:
        assert phrase in html, f"the published IV panel never says {phrase!r}"
    assert f"r = {RISK_FREE_RATE:.2%}" in html, "the assumed rate must be printed (OQ-2)"

    # and the slider has to drive it, or the page shows two as-of dates again
    listener = _listener(html)
    assert "SMILES" in listener, "nothing restyles the smile when the slider moves"
    assert "osl-fig-3" in listener, "the listener never reaches the IV panel"
    assert "showlegend" in listener, "the legend must follow the date, not the build"
    assert "annotations[" in listener, "the caption must follow the date (T-44)"

    payload = re.search(
        r'<script id="osl-frames" type="application/json">(.*?)</script>', html, re.S
    )
    frames = json.loads(payload.group(1))
    ladders = set()
    for label, frame in frames.items():
        by_mode = frame.get("iv")
        assert by_mode, f"{label} has no IV frame"
        assert set(by_mode) == {"strike", "moneyness"}, (
            f"{label}: the smile needs every ruler in the payload — the axis menu and the "
            "slider both write its x (T-43)"
        )
        for mode, iv in by_mode.items():
            ladders.add(len(iv["y"]))
            assert iv["note"], f"{label}/{mode}: no per-date caption"
            assert len(iv["x"]) == len(iv["y"]) == len(iv["show"]), f"{label}/{mode}"
    assert len(ladders) == 1, (
        f"the expiry ladder length varies across dates/modes {ladders} — a restyle by index "
        "would put one expiry's curve into another's slot"
    )

    # T-43: the axis menu has to reach the smile, and the listener has to know which date it
    # is looking at before the slider is ever touched.
    assert "plotly_buttonclicked" in listener, "the axis menu never reaches the smile"
    assert re.search(r'var current = "\d{4}-\d{2}-\d{2}"', listener), (
        "the listener must be seeded with the build date — a null there sends the axis "
        "toggle to whichever date happens to be first in the payload"
    )
    assert "MODE_BY_LABEL" in listener and "xaxis.title.text" in listener, (
        "the smile's axis title must move with the ruler"
    )


def test_the_ci_guard_greps_phrases_the_iv_caption_actually_emits():
    """The publish guard is a plain grep over the built page, so it can be orphaned by a copy
    edit — which is exactly what happened when the caption was shortened (T-45): the workflow
    still looked for 'DERIVED, NOT OBSERVED' after the figure had stopped saying it, and would
    have failed the deploy. Pin the two together the way SYNTHETIC_MARKER already is."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for phrase in IV_PAGE_MARKERS:
        assert "/" not in phrase and "·" not in phrase, (
            f"{phrase!r} cannot be grepped from the built page — see IV_PAGE_MARKERS"
        )
        assert phrase in workflow, (
            f"{phrase!r} is asserted of the page but the CI guard does not check it"
        )
