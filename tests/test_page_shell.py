"""Tests for the chrome both builders render (`options_surface_lab/page_shell.py`, T-79).

A defect here reaches **every** page at once, which is the reason the module exists and
also the reason it needs its own suite: the failures this project has paid for most are the
ones where two renderings of one design drifted apart, and a shared shell converts that risk
into a single point of failure that has to be guarded rather than reviewed.
"""

from __future__ import annotations

import re

import pytest

from options_surface_lab import theme as T
from options_surface_lab.page_shell import (
    CAP_ID_PREFIX,
    FIG_ID_PREFIX,
    LOCAL_PATHS,
    NAV_LABELS,
    SITE_PATHS,
    PAGE_WORDMARKS,
    WORDMARK,
    PageShell,
    Stacked,
    nav_for,
)


@pytest.fixture
def fig():
    """A trivial Plotly figure — enough to exercise `figure_panel`'s html emission."""
    import plotly.graph_objects as go

    return go.Figure(data=[go.Scatter(x=[1, 2], y=[1, 2])])


# ----------------------------------------------------------------- plotly, once per PAGE
def test_plotly_is_requested_once_per_page(fig):
    """Six panels, one `<script src>`. Asking six times is harmless in a browser but makes
    the page's single external dependency six times harder to see against NFR-4."""
    shell = PageShell("t")
    html = "".join(shell.figure_panel(n, "n", "note", fig) for n in range(1, 7))
    assert html.count("cdn.plot.ly") == 1, "plotly.js must be requested exactly once"


def test_a_second_page_built_in_the_same_process_still_gets_plotly(fig):
    """**The regression the shell was written to make impossible.**

    While there was one builder, "have I emitted plotly yet" was a module global. CI now
    builds both pages in one job, so a global would hand the second page "already included"
    from the first and publish it with no library at all — a column of empty panel frames,
    with nothing in the HTML to say why. The state is per `PageShell`, and this is what
    proves it: two shells, two scripts.
    """
    first = PageShell("one").figure_panel(1, "n", "note", fig)
    second = PageShell("two").figure_panel(1, "n", "note", fig)
    assert first.count("cdn.plot.ly") == 1
    assert second.count("cdn.plot.ly") == 1, (
        "the second page built in this process shipped without plotly.js — the include "
        "flag is leaking across pages"
    )


# ----------------------------------------------------------------------------- the panel
def test_a_figure_panel_carries_the_ids_the_listener_addresses(fig):
    """Stable ids, not Plotly's uuid: a uuid regenerated on every build makes the published
    page's only wiring unreproducible (T-42)."""
    html = PageShell("t").figure_panel(3, "Name", "note", fig)
    assert f'id="{FIG_ID_PREFIX}3"' in html
    assert f"osl-w{T.W_HALF}" in html, "a panel with no width defaults to half a row"


def test_a_caption_is_html_in_the_panel_not_an_annotation_in_the_plot():
    """T-47's rule, structurally. A Plotly caption cannot wrap, so it collides with a
    legend that grows as the figure narrows — and *some width* always arrives."""
    html = PageShell("t").panel("Name", "note", "<i>body</i>", n=2, caption=("one", "two"))
    assert f'id="{CAP_ID_PREFIX}2"' in html
    assert html.count("osl-caption-line") == 2
    assert 'data-osl-cap-line="1"' in html, "the listener addresses caption lines by index"


def test_an_unnumbered_panel_prints_no_index_and_claims_no_caption_id():
    """Prose panels are deliberately unnumbered: the indices name FIGURES and are also the
    published page's addressing scheme, so slotting prose into the sequence would renumber
    five panels for a decoration (T-12)."""
    html = PageShell("t").panel("Reading the surface", "", "<p>x</p>", width=T.W_FULL)
    # Matched as whole class attributes: `osl-panel-n` is a prefix of `osl-panel-name`, and
    # a substring search here passes on the panel's own title.
    assert 'class="osl-panel-n"' not in html, "an unnumbered panel must print no [n]"
    assert CAP_ID_PREFIX not in html
    assert 'class="osl-panel-note"' not in html, "an empty note emits no element to style"
    assert f"osl-w{T.W_FULL}" in html


def test_the_hero_names_itself_as_well_as_its_span(fig):
    """`.osl-hero` exists because the span changes between layout bands and the identity
    does not (DESIGN-BRIEF §5)."""
    html = PageShell("t").figure_panel(1, "n", "note", fig, width=T.W_HERO, hero=True)
    assert "osl-hero" in html and f"osl-w{T.W_HERO}" in html
    assert "osl-figure-hero" in html, "the hero carries its own width floor"


# -------------------------------------------------------------------------- the readouts
def test_readout_cells_are_addressable_by_index():
    """A listener looks them up by index and writes the selected date's figures in."""
    html = PageShell("t").readouts((("A", 1), ("B", 2), ("C", 3)))
    assert re.findall(r'data-osl-readout="(\d)"', html) == ["0", "1", "2"]


# --------------------------------------------------------------------------- the document
def test_the_document_carries_its_own_stylesheet_and_title():
    """Pages serves the file alone, so a stylesheet fetched from anywhere would be one more
    way for the deployed page to differ from the built one."""
    html = PageShell("A Title").document(bar="<b>bar</b>", panels=["<p>p</p>"])
    assert "<title>A Title</title>" in html
    assert T.PAGE_CSS in html
    assert html.rstrip().endswith("</body></html>")


def test_the_document_emits_nothing_for_an_absent_section():
    """No warning, no readouts, no script: the page must not carry empty containers whose
    styling then reserves space for nothing.

    Asked of the BODY, not the document: the stylesheet defines every class in the `<head>`,
    so a substring search over the whole page reports each one as present and the assertion
    is vacuously true. The same trap `test_the_published_page_carries_the_commentary` reads
    its ordering off the markup to avoid.
    """
    html = PageShell("t").document(bar="<b>bar</b>", panels=["<p>p</p>"])
    body = html[html.index("<body>"):]
    assert "osl-warn" not in body and "osl-readouts" not in body


def test_a_page_that_does_not_name_itself_is_named_after_the_site():
    """The default is still the site's wordmark — the brief's URL example is a course-level
    site each homework adds a page to, and a page added without a name must not render
    blank."""
    assert WORDMARK in PageShell("anything").command_bar("ident")


def test_a_page_may_name_itself():
    """PO, 2026-09-18: a reader landing on `/covered-call/` was told what the *site* is
    called and had to read the instrument line to learn what they were looking at.

    Pinned to `PAGE_WORDMARKS` rather than to the string, so the name the builder uses and
    the name asserted here cannot be two different decisions.
    """
    name = PAGE_WORDMARKS["covered-call"]
    html = PageShell(name, wordmark=name).command_bar("ident")
    assert f'<div class="osl-wordmark">{name}</div>' in html
    assert WORDMARK not in html, "the page is still carrying the site's name as well"


# --------------------------------------------------------------------------- the site nav
def test_a_page_links_to_every_page_and_marks_the_one_you_are_on():
    """Every page, not only the others (PO, 2026-09-18).

    A two-page site whose nav omitted the current page showed exactly one link, with
    nothing to say what it was one of — the cross-links had been there since T-79 and the
    PO could not find them. Marking the current page is what makes the nav a map.
    """
    for page in SITE_PATHS:
        entries = nav_for(page, site=True)
        assert {label for _, label, _ in entries} == set(NAV_LABELS.values())
        current = [label for _, label, on in entries if on]
        assert current == [NAV_LABELS[page]], f"{page} does not mark itself: {current}"


def test_the_same_link_is_spelled_differently_on_the_site_and_on_disk():
    """A page is written twice from one render, and the two need different hrefs.

    Getting this wrong produces a dead link, which renders perfectly and is discoverable
    only by clicking — this project's signature failure mode, in a new place.
    """
    def href_to(page, *, site, other):
        return next(h for h, label, _ in nav_for(page, site=site)
                    if label == NAV_LABELS[other])

    assert href_to("index", site=True, other="covered-call") == "covered-call/"
    assert href_to("covered-call", site=True, other="index") == "../"
    assert href_to("index", site=False, other="covered-call") == LOCAL_PATHS["covered-call"]
    assert href_to("covered-call", site=False, other="index") == LOCAL_PATHS["index"]


def test_a_site_href_is_relative_so_a_project_site_still_resolves():
    """An absolute `/covered-call/` is right on a user site and wrong on a project site.
    This one is served from `/options-surface-lab/`."""
    for page in SITE_PATHS:
        for href, _, _ in nav_for(page, site=True):
            assert not href.startswith("/"), f"{page}: {href} breaks on a project site"


def test_an_unknown_page_is_refused_rather_than_linked_nowhere():
    with pytest.raises(KeyError):
        nav_for("assignment-3", site=True)


def test_every_page_has_both_a_route_and_a_local_artifact_and_a_label():
    """Three dicts, one key set. A page missing from one of them is a page that builds and
    cannot be linked, or links and cannot be built."""
    assert set(SITE_PATHS) == set(LOCAL_PATHS) == set(NAV_LABELS)


def test_nav_labels_survive_a_grep_over_the_built_page():
    """Plain ASCII, like every other string a CI guard has to find. Plotly's JSON encoder
    ships a `/` as `\\u002f` and the page's separators are `&nbsp;·&nbsp;`, so a marker
    spanning either silently never matches what it guards (T-45)."""
    for label in NAV_LABELS.values():
        assert label.isascii(), f"{label!r} cannot be grepped from the built page"


def test_hw1_publishes_at_the_site_root():
    """The URL already submitted on Canvas keeps working (AD-11). Moving 1.1 off `/` is a
    PO decision, not a refactor."""
    assert SITE_PATHS["index"] == "index.html"


# ------------------------------------------------------------------ tables (T-68 / T-59)
def test_a_table_preserves_a_run_of_spaces():
    """The OCC symbol pads its root to six characters and that padding is grammar (SPEC §8).

    HTML collapses runs of whitespace, so rendering it plainly prints a *different* string
    from the one the engine produced — silently, in the one table whose whole purpose is to
    show exactly what was booked.
    """
    markup = PageShell("t").table(("occ",), [["QQQ   260918C00710000"]])
    assert "QQQ&nbsp;&nbsp;&nbsp;260918C00710000" in markup
    assert "QQQ   260918C00710000" not in markup, "the padding will collapse in a browser"


def test_a_table_escapes_its_cells():
    """A blotter note is data, not markup. Nothing here is user input today, which is the
    reason to escape now rather than the reason not to: the first cell that carries a `<`
    would otherwise break the table and nothing would say why."""
    markup = PageShell("t").table(("note",), [["<b>R-ENTRY</b> & more"]])
    assert "&lt;b&gt;R-ENTRY&lt;/b&gt; &amp; more" in markup
    assert "<b>R-ENTRY</b>" not in markup


def test_a_stacked_cell_escapes_both_of_its_lines():
    """`Stacked` exists so the blotter's OCC can be a subtitle without opening a raw-HTML
    hole in `table()`. The moment one line of it is unescaped, that is exactly what it is —
    and a mutation run found the subtitle going through unescaped while the main line stayed
    safe, which no test noticed.
    """
    markup = PageShell("t").table(("Instrument",), [[Stacked("<b>RIC</b>", "<i>OCC</i>")]])
    assert "&lt;b&gt;RIC&lt;/b&gt;" in markup
    assert "&lt;i&gt;OCC&lt;/i&gt;" in markup
    assert "<b>" not in markup and "<i>" not in markup


def test_a_stacked_cell_keeps_the_occ_padding():
    """Both halves go through the same escaping, so the subtitle keeps its runs of spaces
    for the same reason the main line does (SPEC §8's fixed-width OCC)."""
    markup = PageShell("t").table(("x",), [[Stacked("QQQ.O", "QQQ   260918C00710000")]])
    assert "QQQ&nbsp;&nbsp;&nbsp;260918C00710000" in markup


def test_a_table_carries_its_scroll_box():
    """`position:sticky` resolves against the nearest scrolling ancestor, so a sticky header
    with no scroll box of its own simply never sticks — and nothing about the render says
    why. The wrapper is also what makes a 20-column ledger scroll instead of deforming."""
    markup = PageShell("t").table(("a", "b"), [["1", "2"]])
    assert markup.startswith('<div class="osl-table-scroll">')
    assert 'class="osl-table"' in markup


def test_a_table_cell_can_say_what_it_is():
    """A `(text, class)` cell is how the page marks a number, a skip reason or a breached
    account — the caller decides meaning, `theme.PAGE_CSS` decides appearance (§9)."""
    markup = PageShell("t").table(("x",), [[("SKIP_NO_QUOTE", "osl-skip")]])
    assert '<td class="osl-skip">SKIP_NO_QUOTE</td>' in markup
    assert "osl-table-kv" not in markup
    assert "osl-table-kv" in PageShell("t").table(("k", "v"), [["a", "b"]], kv=True)
