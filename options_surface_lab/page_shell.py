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
import re
from html import escape
from typing import Iterable, Sequence, Union

import plotly.graph_objects as go

from options_surface_lab import theme as T

#: The site's name, and the default wordmark for a page that does not name itself.
#:
#: **A page may override it** (PO, 2026-09-18). Every page carried this until then, on the
#: reasoning that the brief's URL example is a course-level site each homework adds a page
#: to — which is true of the *site* and unhelpful on a *page*: a reader landing on
#: `/covered-call/` was told what the site is called and had to read the instrument line to
#: learn what they were looking at. The example page does the same thing the other way
#: round: a small brand in the topbar, and the page's own name as its heading.
WORDMARK = "Options Surface Lab"

#: What each page calls itself, where that differs from the site. `PageShell` falls back to
#: `WORDMARK`, so a page added without an entry here is named after the site rather than
#: rendering blank.
PAGE_WORDMARKS = {
    "covered-call": "Covered Call Blotter",
}

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


def nav_for(page: str, *, site: bool) -> list[tuple[str, str, bool]]:
    """Links to **every** page, spelled for where `page` is being written.

    `(href, label, is_current)`. It returned only the *other* pages until 2026-09-18, which
    meant a two-page site showed one link and a reader had no way to see what else existed
    — the PO could not find the cross-links at all. Listing every page with the current one
    marked is how the example page does it, and it is the only form that stays legible when
    a third assignment lands.

    A page is written twice from the same code — into `_site/<route>/index.html`, and as a
    root artifact — and the two need different hrefs. Getting that wrong produces a dead
    link, which renders perfectly and is only discoverable by clicking: exactly the
    deploy-only class this project keeps paying for.
    """
    if page not in SITE_PATHS:
        raise KeyError(f"unknown page {page!r} — known pages are {sorted(SITE_PATHS)}")
    return [
        (
            _site_href(page, other) if site else LOCAL_PATHS[other],
            NAV_LABELS[other],
            other == page,
        )
        for other in SITE_PATHS
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


#: One table cell: text, or ``(text, css_class)``. A class is how a cell states what it is.
Cell = Union[str, tuple]


class Stacked:
    """A cell with a second, quieter line under it — the blotter's OCC symbol.

    The brief's blotter column is *"Stock or option RIC; **OCC as a subtitle**"*: eight
    columns, with the OCC inside Instrument rather than beside it. A ninth column says the
    same thing and is not what the brief asks for.

    A small type rather than a raw-HTML cell, deliberately. `table()` escapes everything it
    renders, and the moment one cell is allowed to carry markup that guarantee is gone for
    every cell — so the *structure* is declared here and both halves are still escaped.
    """

    __slots__ = ("main", "sub")

    def __init__(self, main, sub) -> None:
        self.main, self.sub = main, sub

    def __str__(self) -> str:  # what a test or a log sees
        return f"{self.main} {self.sub}".strip()


_RUN_OF_SPACES = re.compile(r"  +")


def _cell_text(value) -> str:
    """Escaped, with runs of spaces preserved as non-breaking ones.

    The OCC symbol pads its root to six characters and that padding is part of the grammar
    (SPEC §8). HTML collapses whitespace, so rendering it plainly prints a *different*
    string from the one the engine produced — silently, and in a table whose whole purpose
    is to show exactly what was booked.
    """
    if isinstance(value, Stacked):
        # Both halves go through this function, so the subtitle is escaped and keeps its
        # padding exactly as the main line does.
        return (
            f"{_cell_text(value.main)}"
            f'<div class="osl-subcell">{_cell_text(value.sub)}</div>'
        )
    text = escape(str(value))
    return _RUN_OF_SPACES.sub(lambda m: "&nbsp;" * len(m.group(0)), text)


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

    def __init__(self, title: str, wordmark: str | None = None) -> None:
        self.title = title
        #: What the command bar calls this page. Defaults to the site's name.
        self.wordmark = wordmark or WORDMARK
        self._plotly_included = False

    # ------------------------------------------------------------------ chrome
    def command_bar(self, ident: str, *, nav: Sequence[Sequence] = ()) -> str:
        """Page name left, every page of the site in the middle, instrument identity right.

        `nav` is `(href, label)` or `(href, label, is_current)`. The current page is marked
        rather than omitted: a two-page site that only ever showed the *other* page gave a
        reader nothing to orient by, and the cross-links were invisible enough that the PO
        asked for links that were already there (2026-09-18).

        The hrefs are the *builder's* to decide, not the shell's: the same page is written
        twice — once into `_site/<route>/index.html` where the links are routes, and once as
        a root artifact the PO opens from the filesystem, where they are filenames. A shell
        that hardcoded routes would give the local artifact dead links, which is only
        visible by clicking.
        """
        links = ""
        for item in nav:
            href, label, current = (tuple(item) + (False,))[:3]
            cls = ' class="on"' if current else ""
            links += f'<a{cls} href="{href}">{label}</a>'
        nav_html = f'<div class="osl-nav">{links}</div>' if links else ""
        return (
            '<div class="osl-bar">'
            f'<div class="osl-wordmark">{self.wordmark}</div>'
            f"{nav_html}"
            f'<div class="osl-ident">{ident}</div>'
            "</div>"
        )

    def readouts(self, items: Iterable[Sequence]) -> str:
        """The KPI strip under the command bar.

        An item is `(label, value)` or `(label, value, hint)`. The hint is a line under the
        number saying where it comes from — *"NAV − initial. Room for a new risk."* — which
        is what turns a Reg T card from a figure into a statement a reader can check. The
        two-element form stays because HW1's strip has no hints and should not grow any.

        `data-osl-readout` is a listener's handle on a value: it looks the cells up by
        index and writes the selected date's figures into them (HW1's as-of slider). A page
        with no listener simply never uses them, which costs nothing.
        """
        cells = []
        for i, item in enumerate(items):
            label, value, hint = (tuple(item) + ("",))[:3]
            cells.append(
                '<div class="osl-readout">'
                f'<div class="osl-readout-label">{label}</div>'
                f'<div class="osl-readout-value" data-osl-readout="{i}">{value}</div>'
                + (f'<div class="osl-readout-hint">{hint}</div>' if hint else "")
                + "</div>"
            )
        return '<div class="osl-readouts">' + "".join(cells) + "</div>"

    def table(
        self,
        columns: Sequence[str],
        rows: Iterable[Sequence["Cell"]],
        *,
        kv: bool = False,
    ) -> str:
        """An HTML table in the terminal style — the blotter, the ledger, the skip log.

        A cell is either a string or a ``(text, css_class)`` pair; the class is how a cell
        says what it *is* (``osl-num`` for a figure, ``osl-skip`` for a skip reason,
        ``osl-flag`` for a breached account), so the caller decides meaning and
        `theme.PAGE_CSS` decides appearance. There is no formatting here on purpose: this
        method cannot know that ``cash_delta`` is money and ``reason`` is a label.

        **Everything is escaped**, and a run of spaces is preserved. HTML collapses runs of
        whitespace, and the blotter's OCC symbol is a *fixed-width* field —
        ``QQQ   260918C00710000`` — whose padding is part of the grammar (SPEC §8). Losing
        it would not error and would not look wrong; it would quietly print a different
        string from the one the engine produced.

        `kv` marks a two-column key/value table, which opts out of the 13-column width
        floor — a table that already fits does not need a scrollbar (DESIGN-BRIEF §9).

        The wrapper is not decoration: ``position:sticky`` on a header resolves against its
        nearest scrolling ancestor, so a sticky header with no scroll box of its own simply
        never sticks, and nothing about the render says why.
        """
        head = "".join(f"<th>{escape(str(c))}</th>" for c in columns)
        body = []
        for row in rows:
            cells = []
            for cell in row:
                text, css = cell if isinstance(cell, tuple) else (cell, "")
                klass = f' class="{css}"' if css else ""
                cells.append(f"<td{klass}>{_cell_text(text)}</td>")
            body.append("<tr>" + "".join(cells) + "</tr>")
        klass = "osl-table osl-table-kv" if kv else "osl-table"
        return (
            '<div class="osl-table-scroll">'
            f'<table class="{klass}">'
            f"<thead><tr>{head}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody>"
            "</table></div>"
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
            # No modebar. It floats over the top-right corner of every figure, which is
            # where a legend also wants to be — the two overlapped on the first covered-call
            # render — and it offers a reader of a finished page nothing but a way to break
            # the axes. Hover, which is what FR-16 actually requires, is unaffected.
            config={"displayModeBar": False, "responsive": True},
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
