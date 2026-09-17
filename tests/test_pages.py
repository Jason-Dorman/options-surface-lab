"""The checks that apply to **every** published page, and to the site that holds them.

From T-79 the site has two pages. The guards that are about being a page at all — self
contained, classes that resolve, reachable from the rest of the site — are parametrized
here rather than restated per builder: two copies of a guard is how the second page quietly
ends up with the weaker one, and a page's worst defects on this project have all been
deploy-only, which is to say invisible to everything except a check over the built file.
"""

from __future__ import annotations

import pytest

from options_surface_lab.page_shell import LOCAL_PATHS, NAV_LABELS, SITE_PATHS, nav_for
from pagelib import WORKFLOW, built_page, external_hosts, nav_hrefs, orphan_classes, read

#: Every page, by its key in `page_shell`. Parametrizing off the shared table rather than a
#: list here means a page added to the site without a guard is impossible.
PAGE_KEYS = sorted(SITE_PATHS)

#: The builder script for each page. The workflow has to run every one of them, or a page
#: is guarded and never built — which the guard would then catch, but only after the fact.
BUILDERS = {
    "index": "build_preview.py",
    "covered-call": "build_covered_call.py",
}


def _html(page: str) -> str:
    path = built_page(LOCAL_PATHS[page])
    if not path.exists():
        pytest.skip(f"{path.name} not built in this working tree")
    return read(path)


@pytest.mark.parametrize("page", PAGE_KEYS)
def test_every_page_is_self_contained(page):
    """Pages serves each file alone — anything it reaches for beyond the CDNs would 404."""
    html = _html(page)
    assert "localhost" not in html, "a backend URL leaked into the published page"
    assert "_event" not in html, "a Reflex websocket endpoint leaked into the published page"
    assert "file://" not in html
    unexpected = external_hosts(html)
    assert not unexpected, f"{page} depends on an unexpected host: {sorted(unexpected)[:3]}"


@pytest.mark.parametrize("page", PAGE_KEYS)
def test_every_class_a_page_uses_is_defined_in_its_own_stylesheet(page):
    """CSS fails open, so an orphan class is a silent layout bug — the exact route by which
    the deployed page shipped with the 3D surface one column wide while `reflex run` looked
    perfect (DESIGN-BRIEF §5)."""
    orphans = orphan_classes(_html(page))
    assert not orphans, (
        f"{page}: these classes are used but never defined, so their styling is silently "
        f"dropped: {orphans}"
    )


@pytest.mark.parametrize("page", PAGE_KEYS)
def test_every_page_links_to_its_siblings(page):
    """A page nothing links to is published and invisible; no render can show that.

    The local artifacts link to each other by filename, so the hrefs are checkable here:
    each one must be a page this repo actually builds.
    """
    hrefs = nav_hrefs(_html(page))
    assert hrefs == [href for href, _ in nav_for(page, site=False)], (
        f"{page}'s nav does not match page_shell.nav_for — the two spellings have drifted"
    )
    for href in hrefs:
        assert href in set(LOCAL_PATHS.values()), f"{page} links to {href!r}, not a page here"


@pytest.mark.parametrize("page", PAGE_KEYS)
def test_every_page_names_itself_in_the_command_bar(page):
    """The wordmark is the site's; the ident line is the page's. Both pages carry both, so
    a reader who lands on either knows what site it is and which book it shows."""
    html = _html(page)
    assert 'class="osl-ident"' in html
    assert NAV_LABELS[page] not in nav_hrefs(html), "a page must not link to itself"


def test_the_workflow_builds_every_page_it_guards():
    """Pin the builders and the routes to `pages.yml`.

    The workflow's guards are plain greps over files at hardcoded paths. If a builder stops
    being run, or a route moves, the guard reads a file that is not there — which `set -e`
    turns into a failed deploy rather than a bad one, but only if the path in the guard is
    the path the builder writes. This is the same coupling `SYNTHETIC_MARKER` already has.
    """
    workflow = read(WORKFLOW)
    for page in PAGE_KEYS:
        assert BUILDERS[page] in workflow, f"{BUILDERS[page]} is never run by the workflow"
        assert f"_site/{SITE_PATHS[page]}" in workflow, (
            f"{page} publishes to _site/{SITE_PATHS[page]}, which the workflow never guards"
        )


def test_the_workflow_passes_the_site_flag_to_every_builder():
    """`--site _site` is what puts a page on its route. Without it a builder writes its root
    artifact and the workflow copies nothing — every guard then fails on a missing file."""
    workflow = read(WORKFLOW)
    for page in PAGE_KEYS:
        assert f"{BUILDERS[page]} --site _site" in workflow, (
            f"{BUILDERS[page]} must be run with `--site _site` or its page never lands"
        )
