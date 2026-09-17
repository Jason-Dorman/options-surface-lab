"""Helpers for asserting on a **built** page, shared by every page's test module.

Not a test module. It exists because from T-79 there are two published pages, and the
checks that apply to *any* page — it is self-contained, its classes resolve, it is reachable
from the rest of the site — must be one implementation. Two copies of a guard is how the
second page quietly ends up with the weaker one.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"

#: The only hosts a published page may reach. Both are CDNs that degrade gracefully —
#: Plotly is required and Google Fonts falls back to a system face. Anything else would be
#: a backend, a tracker, or a broken asset path (NFR-4, DESIGN-BRIEF §7).
ALLOWED_HOSTS = ("cdn.plot.ly", "plotly.com", "fonts.googleapis.com", "fonts.gstatic.com")


def built_page(name: str) -> Path:
    """A root artifact by filename. Returns the path whether or not it exists."""
    return ROOT / name


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def external_hosts(html: str) -> set[str]:
    """Every URL in the page that is not on the allow-list."""
    return {
        url
        for url in re.findall(r"https?://[^\s\"'<>]+", html)
        if not any(host in url for host in ALLOWED_HOSTS)
    }


def orphan_classes(html: str) -> list[str]:
    """`osl-` classes the page uses that its own stylesheet never defines.

    CSS fails open: an undefined class is not an error, the element simply keeps its
    default. That is how the deployed page once shipped with the 3D surface one column wide
    while the local Reflex app — which styled its panels inline — looked perfect.

    Only base-level rules count. The responsive block re-lists every width class to collapse
    it on narrow screens, so counting selectors anywhere in the sheet would report a class
    as "defined" on the strength of its mobile override alone — exactly the hole that let
    the missing `.osl-w6` reach production.
    """
    style = re.search(r"<style>(.*?)</style>", html, re.S)
    assert style, "the page must carry its own stylesheet"
    css = re.sub(r"@media[^{]*\{(?:[^{}]|\{[^{}]*\})*\}", "", style.group(1), flags=re.S)
    defined = set(re.findall(r"\.(osl-[a-z0-9-]+)", css))

    used: set[str] = set()
    for attr in re.findall(r"class=[\"']([^\"']*)[\"']", html):
        used.update(c for c in attr.split() if c.startswith("osl-"))
    return sorted(used - defined)


def nav_hrefs(html: str) -> list[str]:
    """The hrefs of the command bar's site navigation, in order."""
    bar = re.search(r'<div class="osl-nav">(.*?)</div>', html, re.S)
    return re.findall(r'href="([^"]*)"', bar.group(1)) if bar else []
