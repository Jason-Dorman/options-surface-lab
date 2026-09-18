"""Build Assignment 2's published page: the covered-call book, as one self-contained file.

The site's **second** page (T-79, AD-11's interim). CI runs it with `--site _site`, which
writes `_site/covered-call/index.html`; run with no arguments it writes the root artifact
`covered_call_preview.html`, which is what the PO opens locally and what
`tests/test_build_covered_call.py` reads. The chrome is `page_shell.PageShell`, shared with
`build_preview.py`, so the two pages cannot come to disagree about what a panel looks like.

**The panels live in `covered_call/page.py`** (T-59). What is left here is the *destination*
— which directory the page lands in and how its cross-page links are spelled — because that
is the only thing the two renderings differ by. AD-11's registry and templates are T-51,
after the 09-20 submission; until then a page is a builder, and a builder is this thin.

Reads the tape through `load_tape()`, which **opens no session under any circumstances**
(NFR-4) — the offline guarantee is a property of the function called, not of an env var.
"""

import argparse
from pathlib import Path

from options_surface_lab.covered_call.page import SYNTHETIC_MARKER, build_page, entries
from options_surface_lab.covered_call.rules import Params
from options_surface_lab.covered_call.tape import load_tape
from options_surface_lab.page_shell import (
    LOCAL_PATHS,
    SITE_PATHS,
    PageShell,
    nav_for,
)

#: This page's key in `page_shell.SITE_PATHS` / `LOCAL_PATHS`.
PAGE = "covered-call"

# Re-exported: the CI publish guard greps this string and `tests/` pins the two together.
# It is defined beside the text that carries it (`page.py`), not here, so the marker and the
# banner cannot drift apart — but it is named here because this is the module the guard's
# test imports.
__all__ = ["PAGE", "SYNTHETIC_MARKER", "build_covered_call"]


def build_covered_call(
    site: Path | str | None = None,
    *,
    params: Params | None = None,
    tape=None,
    live: dict | None = None,
) -> Path:
    """Render the covered-call page and write it. `site` is the directory to publish into.

    One render, two destinations — the local artifact and the published one differ only in
    where they land and how their nav links are spelled, so the page the PO checks is the
    page CI ships (RUNBOOK §5: check the built page, not the dev app).

    `tape` and `live` are overrides for tests: the committed tape has no skipped week and no
    synthetic banner, so a guard that only ever sees it cannot tell "read off the book" from
    "happens to equal the book here" — the premium summed and the premium retyped are the
    same number on ten traded weeks. The build never uses either; the CLI cannot reach them.
    """
    shell = PageShell("Covered call · Options Surface Lab")
    params = params or Params()
    tape = load_tape(params=params) if tape is None else tape
    page = build_page(tape, params, shell=shell, live=live)

    root = Path(__file__).resolve().parent
    out = (Path(site) / SITE_PATHS[PAGE]) if site else (root / LOCAL_PATHS[PAGE])

    html = shell.document(
        bar=shell.command_bar(page.ident, nav=nav_for(PAGE, site=bool(site))),
        readouts=shell.readouts(page.readouts),
        warning=shell.warning(page.warning_text) if page.warning_text else "",
        panels=page.panels,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    book = page.book
    print(
        f"Wrote {out}  weeks={len(book.weekly)}  entries={entries(book)}  "
        f"nav={book.final_nav}  synthetic={book.synthetic}"
    )
    return out


def _cli() -> Path:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--site",
        metavar="DIR",
        default=None,
        help=(
            f"publish into DIR/{SITE_PATHS[PAGE]} instead of writing the root artifact "
            f"{LOCAL_PATHS[PAGE]}. CI passes `--site _site`."
        ),
    )
    return build_covered_call(parser.parse_args().site)


if __name__ == "__main__":
    _cli()
