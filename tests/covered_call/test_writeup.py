"""The write-up's prose is held to the rule it describes (FR-19, T-70).

The interesting test here is
:func:`test_the_observation_point_paragraph_is_true_of_the_actual_rule`. The argument
makes a falsifiable claim about what the strategy would have done at two different
prices, so the test re-runs ``select_strike`` on both and fails if the code and the
claim ever drift apart. That is I-13's idea — the page says what the book says —
applied to sentences instead of tables.

The three standalone paragraphs folded into ``ANSWERS`` on 2026-09-18, so the guards
written against them now address the answer that absorbed each one. One was retired
rather than repointed: the midpoint example's ``$4.80``/``$4.81`` left the module with
it, and a guard kept alive against prose that no longer makes its claim is a guard
that cannot fail.
"""
from __future__ import annotations

from options_surface_lab.covered_call import writeup
from options_surface_lab.covered_call.rules import Params, select_strike

#: A $1 ladder spanning both prices the observation-point argument was measured from.
CHAIN = [float(k) for k in range(710, 726)]

#: `ANSWERS` is positional, so the two answers these guards hold are addressed by name
#: rather than by a literal index a reordering would silently repoint.
STRIKE_ANSWER = 0
FILL_ANSWER = 2


def test_the_observation_point_paragraph_is_true_of_the_actual_rule():
    facts = writeup.OBSERVATION_POINT_FACTS
    params = Params()
    assert select_strike(CHAIN, facts["open"], params) == facts["open_selects"]
    assert select_strike(CHAIN, facts["close"], params) == facts["close_selects"]
    assert facts["open_selects"] != facts["close_selects"], (
        "the paragraph's whole point is that the observation point changes the trade"
    )


def test_the_limitation_is_stated_and_not_softened_away():
    """The one sentence that protects the page from a market-data question."""
    limitation = dict(writeup.METHOD)["Limitation"]
    assert "common-bar level" in limitation
    assert "not at the exact quote-event level" in limitation


def test_the_synchronisation_claim_stays_at_the_bar_level():
    """Trade-to-trade, never trade-to-quote. The narrower claim is the provable one.

    Moved onto ``ANSWERS[2]`` on 2026-09-18, when the standalone paragraph folded into the
    answer it qualifies. The phrasing is the PO's and may change; what may not is the shape
    of the claim — the same **bar**, and an acknowledgement that the quote's own timestamp
    is unavailable. Losing that sentence silently widens a bar-level claim into a
    quote-level one, which is the unverifiable version (SPEC §6.3).
    """
    prose = writeup.ANSWERS[FILL_ANSWER]
    assert "same hourly bar" in prose
    assert "timestamp" in prose, (
        "the fill answer no longer says the quote-update timestamp is unavailable — "
        "without it the synchronisation claim reads as quote-level, which it is not"
    )
    assert "NBBO" not in prose, "unverified for a .U RIC — do not claim it"
    assert "national best bid" not in prose


def test_no_document_claims_the_quotes_are_nbbo():
    for prose in (*writeup.ANSWERS, *[t for _, t in writeup.METHOD]):
        assert "NBBO" not in prose and "national best bid" not in prose


def test_the_method_hierarchy_is_complete_and_ordered():
    assert [label for label, _ in writeup.METHOD] == [
        "Rule", "Fill", "Stock", "Audit evidence", "Limitation"
    ]
    assert all(text and text != writeup.UNWRITTEN for _, text in writeup.METHOD)


def test_every_write_up_question_has_a_slot():
    assert len(writeup.QUESTIONS) == len(writeup.ANSWERS)
    assert all(q.endswith("?") for q in writeup.QUESTIONS)


def test_the_unwritten_marker_is_detectable_so_the_page_can_refuse_to_ship():
    """FR-19 has no figure behind it, so nothing about the render fails when it is missing.

    Tightened 2026-09-18, as its own failure message asked: the PO wrote all five, so the
    state to protect flipped from "none written" to "none lost". The marker itself stays
    under test — the page and the workflow both grep for it, and a marker that stopped being
    a distinctive string would disarm both without failing anything.
    """
    assert writeup.UNWRITTEN == "[unwritten]", (
        "the page and .github/workflows/pages.yml both grep this literal"
    )
    unwritten = [i for i, a in enumerate(writeup.ANSWERS) if a == writeup.UNWRITTEN]
    assert unwritten == [], f"answer(s) {unwritten} went back to [unwritten]"


def test_every_answer_is_specific_to_this_book():
    """PRD FR-19's acceptance: *"specific to the book on the page (cites its own numbers)"*.

    A digit is a low bar and deliberately so — it is the difference between an answer about
    *a* covered call and an answer about *this* one, and it is the one part of "specific"
    a test can check without grading prose.
    """
    for index, answer in enumerate(writeup.ANSWERS):
        assert any(c.isdigit() for c in answer), (
            f"answer {index} cites no number of its own: {answer!r}"
        )
        assert len(answer.split()) >= 20, f"answer {index} is a stub: {answer!r}"


def test_the_observation_point_argument_reached_the_answer_that_absorbed_it():
    """The paragraph folded into `ANSWERS[0]` on 2026-09-18; the argument had to survive it.

    Not a phrase match — the wording is the PO's. What is pinned is that the strike answer
    still argues from *where in the bar* the price is read, which is the whole reason the
    rule is algorithmic rather than discretionary (rubric line 1). Deleting that clause
    leaves an answer that names the bar and never says why the point inside it matters.
    """
    prose = writeup.ANSWERS[STRIKE_ANSWER].lower()
    assert "open" in prose and "close" in prose, (
        "the strike answer no longer contrasts the open and the close of the entry bar"
    )
