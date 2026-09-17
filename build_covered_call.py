"""Build Assignment 2's published page: the covered-call book, as one self-contained file.

The site's **second** page (T-79, AD-11's interim). CI runs it with `--site _site`, which
writes `_site/covered-call/index.html`; run with no arguments it writes the root artifact
`covered_call_preview.html`, which is what the PO opens locally and what
`tests/test_build_covered_call.py` reads. The chrome is `page_shell.PageShell`, shared with
`build_preview.py`, so the two pages cannot come to disagree about what a panel looks like.

**This is the frame, not the book.** SPEC §11's panels — the NAV/IM/MM path, the blotter,
the skip log, the ledger, mid-vs-print, and the PO's write-up — arrive with T-69/T-59/T-70,
which is why nothing here draws a figure yet. What it does carry is real: the readouts come
from `run_backtest` over the committed tape, by the same call the panels will make.

Reads the tape through `load_tape()`, which **opens no session under any circumstances**
(NFR-4) — the offline guarantee is a property of the function called, not of an env var.
"""

import argparse
from pathlib import Path

# Grepped for by the CI publish guard — see .github/workflows/pages.yml. Distinct from
# 1.1's "synthetic panel": the pages are guarded separately, and a marker shared between
# them would let one page's fabrication pass the other's check.
SYNTHETIC_MARKER = "synthetic tape"

#: This page's key in `page_shell.SITE_PATHS` / `LOCAL_PATHS`.
PAGE = "covered-call"

from options_surface_lab import theme as T
from options_surface_lab.covered_call.engine import run_backtest
from options_surface_lab.covered_call.rules import Params
from options_surface_lab.covered_call.tape import load_tape
from options_surface_lab.page_shell import (
    LOCAL_PATHS,
    SITE_PATHS,
    PageShell,
    nav_for,
)


def build_covered_call(
    site: Path | str | None = None,
    *,
    params: Params | None = None,
    tape=None,
) -> Path:
    """Render the covered-call page and write it. `site` is the directory to publish into.

    One render, two destinations — the local artifact and the published one differ only in
    where they land and how their nav links are spelled, so the page the PO checks is the
    page CI ships (RUNBOOK §5: check the built page, not the dev app).

    `tape` is an override for tests: the committed tape has no skipped week and no
    synthetic banner, so a guard that only ever sees it cannot tell "read off the book"
    from "happens to equal the book here" — the premium summed and the premium retyped are
    the same number on ten traded weeks. Passing the synthetic tape reaches both branches.
    The build never uses it; the CLI cannot reach it.
    """
    shell = PageShell("Covered call · Options Surface Lab")
    params = params or Params()
    tape = load_tape(params=params) if tape is None else tape
    book = run_backtest(tape, params)

    root = Path(__file__).resolve().parent
    out = (Path(site) / SITE_PATHS[PAGE]) if site else (root / LOCAL_PATHS[PAGE])

    # Shown ONLY when the book was run on a generated tape. A synthetic book renders
    # perfectly — ten plausible weeks of a market that never happened — so its absence of a
    # banner is the dangerous case, and `Tape.synthetic` defaults to True for exactly that
    # reason. The CI guard greps for the marker and refuses to publish (SPEC §11).
    warning = (
        shell.warning(
            f"Built from a {SYNTHETIC_MARKER}, not the LSEG pull — "
            "every number below is a shape, not a market. This must not be published."
        )
        if book.synthetic
        else ""
    )

    bar = shell.command_bar(
        f"<b>{params.root}</b> covered call &nbsp;·&nbsp; weekly &nbsp;·&nbsp; "
        f"<b>{params.start} → {params.end}</b> &nbsp;·&nbsp; {params.interval} bars "
        f"&nbsp;·&nbsp; {len(book.weekly)} weeks",
        nav=nav_for(PAGE, site=bool(site)),
    )

    readouts = shell.readouts(_headline(book))

    panels = [_scope_panel(shell, params, book)]

    html = shell.document(bar=bar, readouts=readouts, warning=warning, panels=panels)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(
        f"Wrote {out}  weeks={len(book.weekly)}  entries={_entries(book)}  "
        f"nav={book.final_nav}  synthetic={book.synthetic}"
    )
    return out


def _entries(book) -> int:
    """Weeks the rule actually traded — a week with a settled outcome had an entry."""
    return int(book.weekly["outcome"].isin(("ASSIGN", "EXPIRE")).sum())


def _headline(book) -> tuple:
    """The six numbers the book leads with.

    Every one is read off `book`, never restated: `final_nav` in particular takes the
    window's **closing** bar rather than the last ledger row, because the stock tape runs
    past the close and a post-close stub moves the headline by tens of dollars (T-57). A
    number retyped here would be the one place on the page that could disagree with the
    engine.
    """
    weekly = book.weekly
    entries = _entries(book)
    assigned = int((weekly["outcome"] == "ASSIGN").sum())
    premium = float(weekly["premium"].fillna(0).sum())
    return (
        ("Weeks in window", len(weekly)),
        ("Entries booked", f"{entries} of {len(weekly)}"),
        ("Assigned at expiry", f"{assigned} of {entries}" if entries else "0"),
        ("Premium collected", f"${premium:,.2f}"),
        ("Final NAV", f"${book.final_nav:,.2f}"),
        ("Return on start cash", f"{book.total_return:+.2%}"),
    )


def _scope_panel(shell: PageShell, params: Params, book) -> str:
    """One prose panel saying what produced the numbers above, and what is still missing.

    It is deliberately **not** FR-14's strategy panel: that prints `Params` whole, beside
    the stated simplifications, and lands with T-59. What this says is only what the page
    can stand behind today — and it says it rather than leaving a reader to infer a missing
    panel is a rendering fault (AD-9's posture: a hole renders as a hole).
    """
    strike_rule = params.describe_strike_rule()
    coming = (
        "the NAV / initial-margin / maintenance-margin path",
        "the blotter and the skip log",
        "the daily ledger",
        "mark-versus-print, with the fit the fill assumption rests on",
        "the write-up",
    )
    body = (
        '<div class="osl-commentary-item">'
        '<div class="osl-commentary-q">What the numbers above are</div>'
        f'<div class="osl-note">One covered call a week on <b>{params.root}</b>, '
        f"bought and written at the {params.interval} bar the rule names, held through "
        f"expiry, over <b>{params.start} → {params.end}</b> on "
        f"<b>${params.start_cash:,.0f}</b> of starting cash. {strike_rule} They come from "
        "the same backtest the panels will draw, run over the committed tape."
        "</div></div>"
        '<div class="osl-commentary-item">'
        '<div class="osl-commentary-q">What is still to come</div>'
        '<div class="osl-note">This page is the site\'s second output and carries its '
        "frame only. Still to land: "
        + ", ".join(coming)
        + ". Assignment 1.1's page is unchanged and linked from the bar above."
        "</div></div>"
    )
    return shell.panel(
        "Covered call · scope",
        "interim — the book's panels follow",
        body,
        width=T.W_FULL,
        body_class="osl-commentary",
    )


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
