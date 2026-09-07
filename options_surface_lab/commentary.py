"""This module is prose and nothing else: no imports, no data, no formatting decisions.

Both renderings import this module — `build_preview.py` (the published page) and
`options_surface_app.py` (the local dev app) — so the graded page and the demo cannot end up
saying different things. Same rule the panel captions have followed since T-47: one source,
two renderings.

**If a slot is left empty** the page prints `UNWRITTEN` in red where the sentence should be,
`tests/test_build_preview.py` fails, and the Pages workflow refuses to deploy. Three guards,
because a missing rubric item is invisible on a page that otherwise renders perfectly — this
is the only requirement on the page with no figure to prove it is there.
"""

# The assignment's three questions
QUESTIONS = (
    "Where is the cloud of price data dense, and where is it empty?",
    "Why is interpolating across empty cells dangerous on a $0.50 strike grid "
    "for a name like UUUU?",
    "Which field will you treat as the mark next week, and which field will you treat "
    "as evidence that someone traded?",
)


SENTENCES = (
    # 1. Where is the cloud dense, and where is it empty?
    "The price cloud is densest around the at-the-money strikes and deteriorates the further out of the money the strike moves.",
    # 2. Why is interpolating across empty cells dangerous here?
    "Interpolating across missing strikes is risky because a $0.50 step is big compared to UUUU's share price. So filling several strikes with a straight line, essentially, would be very different than what the market would have actually quoted.",
    # 3. Which field is the mark, and which field is evidence of a trade?
    "The available mark from the data is MID_PRICE at the endpoint, which is the closing bid/ask midpoint. TRDPRC_1 is evidence that an actual trade occurred.",
)


# What the page prints in place of a sentence that has not been written. ASCII on purpose:
# the Pages workflow greps the built page for it and refuses to publish, and a grep guard
# spanning a character Plotly or HTML escapes silently never matches (T-45).
UNWRITTEN = "[unwritten]"

# The panel's own chrome, here rather than in the two renderers so they cannot drift.
PANEL_NAME = "Reading the surface"
PANEL_NOTE = "author's commentary"


def answers():
    """`(question, text, written)` in page order — the shape both renderers draw.

    The placeholder substitution lives here rather than in each renderer for the reason the
    text does: two spellings of one rule is how this project has repeatedly shipped a page
    that disagreed with its own dev app.
    """
    return tuple(
        (question, sentence.strip() or UNWRITTEN, bool(sentence.strip()))
        for question, sentence in zip(QUESTIONS, SENTENCES)
    )
