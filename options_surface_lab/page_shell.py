"""The chrome both static builders render: command bar, readout strip, panels, document.

**AD-11's interim (T-79).** `build_preview.py` wrote the site's one page by f-string
assembly, and Assignment 2 needs a second. The registry and the Jinja2 templates AD-11
decided on land with T-51, *after* the 09-20 submission; what moves here is only the
chrome, so that two builders cannot come to disagree about what a panel looks like. That
is this project's most-repeated defect class — one design, two spellings — and it has
already shipped twice from the Reflex app alone (the missing `.osl-w6`, and an app with no
breakpoints at all).

A page owns its **content and its scripts**; the shell owns its **frame**. HW1's as-of
listener stays in `build_preview.py` for that reason (AD-11: "a page owns its script").

No colour, font or measurement lives here — every class resolves against `theme.PAGE_CSS`
(FR-8 / AD-6), and `tests/test_theme.py` greps this module for literals the same way it
greps the builders.
"""

from __future__ import annotations

import posixpath
from typing import Iterable, Sequence

import plotly.graph_objects as go

from options_surface_lab import theme as T

#: The site's wordmark, not a page's. Every page carries it, because the brief's own URL
#: example is a course-level site that each homework adds a page to.
WORDMARK = "Options Surface Lab"

#: Where each page is published. HW1 stays at the site root so the URL already submitted on
#: Canvas keeps working (AD-11); every later assignment takes a route of its own.
#:
#: This is **not** AD-11's registry — that is T-51, with the templates, after 09-20. It is
#: two constants shared by two builders so that neither can be wrong about where the other
#: one lives, which is the only thing a cross-link needs to know. `tests/` pins these to
#: `.github/workflows/pages.yml`, so the build step and the guards cannot drift from them.
SITE_PATHS = {
    "index": "index.html",
    "covered-call": "covered-call/index.html",
}

#: The same pages as root artifacts, which is what a builder writes when it is not writing
#: a site: the PO opens these from the filesystem and `tests/` reads them.
LOCAL_PATHS = {
    "index": "options_surface_preview.html",
    "covered-call": "covered_call_preview.html",
}

#: What a link to each page says. Plain ASCII: these reach the built page, where a CI grep
#: has to be able to find them (T-45's lesson about `·` and `/`).
NAV_LABELS = {
    "index": "Surface lab (1.1)",
    "covered-call": "Covered call (2)",
}


def nav_for(page: str, *, site: bool) -> list[tuple[str, str]]:
    """Links from `page` to every *other* page, spelled for where it is being written.

    A page is written twice from the same code — into `_site/<route>/index.html`, and as a
    root artifact — and the two need different hrefs. Getting that wrong produces a dead
    link, which renders perfectly and is only discoverable by clicking: exactly the
    deploy-only class this project keeps paying for.
    """
    if page not in SITE_PATHS:
        raise KeyError(f"unknown page {page!r} — known pages are {sorted(SITE_PATHS)}")
    return [
        (_site_href(page, other) if site else LOCAL_PATHS[other], NAV_LABELS[other])
        for other in SITE_PATHS
        if other != page
    ]


def _site_href(from_page: str, to_page: str) -> str:
    """A relative URL between two published pages, as a directory so the route is clean.

    Relative, never absolute: an absolute `/covered-call/` is right on a user-site and
    wrong on a project-site served from `/<repo>/`, and this one is served from
    `/options-surface-lab/`.
    """
    from_dir = posixpath.dirname(SITE_PATHS[from_page])
    to_dir = posixpath.dirname(SITE_PATHS[to_page])
    rel = posixpath.relpath(to_dir or ".", from_dir or ".")
    return "./" if rel == "." else rel.rstrip("/") + "/"

# ------------------------------------------------------------------ the figure side
#
# A panel and the figure inside it have a contract: the figure states its caption and
# the height its panel must reserve, and the panel renders both. That contract is the
# shell's, not any one assignment's — it lived in `option_surface_plot` until T-69, when
# Assignment 2's figures needed it and were forbidden to reach into 1.1 (AD-12).

def with_caption(fig: go.Figure, *lines: str) -> go.Figure:
    """Attach a figure's "how to read this" line(s) — as DATA, not as a drawn annotation.

    The caption is rendered by whichever page holds the figure, in that page's own HTML, and
    both renderings read it from here so they cannot drift (T-47). It travels in
    `layout.meta`, which survives `to_html`/JSON, so the published page finds it in the same
    place the Reflex app does.

    **Why it is not an annotation any more.** A Plotly annotation is one unwrappable line
    pinned to a fraction of a box whose pixel width changes with the viewport, sharing the
    band above the plot with a legend that grows as the figure narrows. That arrangement has
    produced the same defect at five different widths on this project — caption through
    legend, caption clipped off the canvas, caption off the right edge of a tile, caption over
    a wrapped legend, caption escaping the figure below 1440px. HTML text wraps; SVG text
    does not.

    Callers pass one line per caption row; `figure_caption` reads them back.
    """
    fig.layout.meta = dict(fig.layout.meta or {}, caption=[ln for ln in lines if ln])
    return fig


def figure_caption(fig: go.Figure) -> list:
    """The caption lines a page must render under this figure's header. Never None."""
    meta = fig.layout.meta or {}
    return list(meta.get("caption") or [])


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


#: Stable element ids. The published page's listener addresses panels by these rather than
#: by Plotly's random uuid — a uuid regenerated on every build makes the wiring
#: unreproducible — and a caption is HTML now, so it needs an id of its own (T-47).
FIG_ID_PREFIX = "osl-fig-"
CAP_ID_PREFIX = "osl-cap-"


class PageShell:
    """One document's chrome. **State is per page, never per process.**

    The only state is whether plotly.js has been emitted yet, and it is an instance
    attribute for a reason that would otherwise be a deploy-only defect: as a module
    global — which is where it lived while there was one builder — the *second* page built
    in a process would inherit "already included" from the first and ship with no plotly.js
    at all. CI builds both pages in one job. A page with no library renders as a column of
    empty panel frames, with nothing in the HTML to say why.
    """

    def __init__(self, title: str) -> None:
        self.title = title
        self._plotly_included = False

    # ------------------------------------------------------------------ chrome
    def command_bar(self, ident: str, *, nav: Sequence[tuple[str, str]] = ()) -> str:
        """Wordmark left, the site's other pages in the middle, instrument identity right.

        `nav` is `(href, label)` pairs. The hrefs are the *builder's* to decide, not the
        shell's: the same page is written twice — once into `_site/<route>/index.html`
        where the links are routes, and once as a root artifact the PO opens from the
        filesystem, where they are filenames. A shell that hardcoded routes would give the
        local artifact two dead links, which is only visible by clicking.
        """
        links = "".join(f'<a href="{href}">{label}</a>' for href, label in nav)
        nav_html = f'<div class="osl-nav">{links}</div>' if links else ""
        return (
            '<div class="osl-bar">'
            f'<div class="osl-wordmark">{WORDMARK}</div>'
            f"{nav_html}"
            f'<div class="osl-ident">{ident}</div>'
            "</div>"
        )

    def readouts(self, items: Iterable[tuple[str, object]]) -> str:
        """The KPI strip under the command bar.

        `data-osl-readout` is a listener's handle on a value: it looks the cells up by
        index and writes the selected date's figures into them (HW1's as-of slider). A page
        with no listener simply never uses them, which costs nothing.
        """
        return (
            '<div class="osl-readouts">'
            + "".join(
                '<div class="osl-readout">'
                f'<div class="osl-readout-label">{label}</div>'
                f'<div class="osl-readout-value" data-osl-readout="{i}">{value}</div>'
                "</div>"
                for i, (label, value) in enumerate(items)
            )
            + "</div>"
        )

    def warning(self, text: str) -> str:
        """A loud banner — for the one thing that must never publish quietly: a page built
        from generated data, which renders perfectly and is a fabrication."""
        return f'<div class="osl-warn">{text}</div>'

    def panel(
        self,
        name: str,
        note: str,
        body: str,
        *,
        n: int | None = None,
        width: int | None = None,
        caption: Sequence[str] = (),
        hero: bool = False,
        body_class: str = "osl-panel-body",
    ) -> str:
        """A panel: a header rule, an optional HTML caption, then whatever `body` is.

        `n` numbers the panel; omit it for prose panels. The indices name **figures** and
        are also the published page's addressing scheme, so renumbering them to slot prose
        into the sequence would churn the page's only wiring for a decoration (T-12).

        `width` is in grid columns out of `theme.GRID_COLUMNS`; `hero` marks the panel that
        goes full width in the two-column band (`theme.BREAK_TWO_COL`).

        **The caption is HTML, not an annotation inside the plot** (T-47). It therefore
        wraps, and can neither collide with the figure's own chrome nor be clipped by its
        margins — two failure modes this project shipped four times between them.
        """
        lines = "".join(
            f'<span class="osl-caption-line" data-osl-cap-line="{i}">{line}</span>'
            for i, line in enumerate(caption)
        )
        cap_id = f' id="{CAP_ID_PREFIX}{n}"' if n is not None else ""
        caption_html = f'<div class="osl-caption"{cap_id}>{lines}</div>' if lines else ""
        number = f'<span class="osl-panel-n">[{n}]</span>' if n is not None else ""
        note_html = f'<div class="osl-panel-note">{note}</div>' if note else ""
        hero_class = " osl-hero" if hero else ""
        return (
            f'<div class="osl-panel osl-w{width or T.W_HALF}{hero_class}">'
            '<div class="osl-panel-head">'
            f"<div>{number}"
            f'<span class="osl-panel-name">{name}</span></div>'
            f"{note_html}"
            "</div>"
            f"{caption_html}"
            f'<div class="{body_class}">{body}</div>'
            "</div>"
        )

    def figure_panel(
        self,
        n: int,
        name: str,
        note: str,
        fig,
        *,
        width: int | None = None,
        hero: bool = False,
    ) -> str:
        """A numbered panel whose body is a Plotly figure.

        The caption text comes from the figure itself (`figure_caption` -> `layout.meta`),
        so the published page and the Reflex app cannot disagree about what a panel says.

        Plotly.js is requested from the CDN by the first figure panel of the page only.
        Asking six times emitted the same `<script src>` six times — harmless in a browser,
        but it made the page's single external dependency six times harder to see when
        auditing it against NFR-4.
        """
        body = fig.to_html(
            full_html=False,
            include_plotlyjs=("cdn" if not self._plotly_included else False),
            div_id=f"{FIG_ID_PREFIX}{n}",
        )
        self._plotly_included = True
        fig_class = "osl-figure osl-figure-hero" if hero else "osl-figure"
        return self.panel(
            name,
            note,
            f'<div class="{fig_class}">{body}</div>',
            n=n,
            width=width,
            hero=hero,
            caption=figure_caption(fig),
        )

    # ------------------------------------------------------------------ document
    def document(
        self,
        *,
        bar: str,
        readouts: str = "",
        warning: str = "",
        panels: Iterable[str] = (),
        scripts: Iterable[str] = (),
    ) -> str:
        """The whole page, as one self-contained string (AD-4).

        The stylesheet travels *inside* the file: Pages serves the page alone, so a
        stylesheet fetched from anywhere would be one more way for the deployed page to
        differ from the built one.
        """
        parts = [
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1'>",
            f"<title>{self.title}</title>",
            T.GOOGLE_FONTS_LINK,
            f"<style>{T.PAGE_CSS}</style></head><body>",
            bar,
            readouts,
            warning,
            '<div class="osl-grid">',
            *panels,
            "</div>",
            *scripts,
            "</body></html>",
        ]
        return "\n".join(p for p in parts if p)
