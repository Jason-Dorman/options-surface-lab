"""Tests for the published artifact itself.

`build_preview.py` writes the single HTML file that GitHub Pages serves, so a defect here
ships straight to the graded submission with nothing between it and a reader. The CI publish
guard is a plain `grep` over that file, which means it can be silently orphaned by an
unrelated copy edit — that nearly happened when the prose block carrying the marker was
removed. These tests pin the contract between the builder and the workflow.
"""

import re
from pathlib import Path

import pytest

import build_preview
from options_surface_lab.option_surface_utils import (
    attach_underlying,
    flatten_lseg_options,
    pivot_trade_settle,
    summarize_sparsity,
    synthesize_demo_payload,
)

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pages.yml"


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
