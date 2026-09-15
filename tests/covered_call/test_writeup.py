"""The write-up's prose is held to the rule it describes (FR-19, T-70).

The interesting test here is
:func:`test_the_observation_point_paragraph_is_true_of_the_actual_rule`. The
paragraph makes a falsifiable claim about what the strategy would have done at two
different prices, so the test re-runs ``select_strike`` on both and fails if the code
and the prose ever drift apart. That is I-13's idea — the page says what the book
says — applied to sentences instead of tables.
"""
from __future__ import annotations

from options_surface_lab.covered_call import writeup
from options_surface_lab.covered_call.rules import Params, select_strike

#: A $1 ladder spanning both prices the paragraph quotes.
CHAIN = [float(k) for k in range(710, 726)]


def test_the_observation_point_paragraph_is_true_of_the_actual_rule():
    facts = writeup.OBSERVATION_POINT_FACTS
    params = Params()
    assert select_strike(CHAIN, facts["open"], params) == facts["open_selects"]
    assert select_strike(CHAIN, facts["close"], params) == facts["close_selects"]
    assert facts["open_selects"] != facts["close_selects"], (
        "the paragraph's whole point is that the observation point changes the trade"
    )


def test_the_paragraph_quotes_the_numbers_it_was_measured_from():
    facts = writeup.OBSERVATION_POINT_FACTS
    prose = writeup.OBSERVATION_POINT
    for value in (facts["open"], facts["close"]):
        assert f"${value}" in prose
    for strike in (facts["open_selects"], facts["close_selects"]):
        assert f"${strike:g}" in prose


def test_the_limitation_is_stated_and_not_softened_away():
    """The one sentence that protects the page from a market-data question."""
    limitation = dict(writeup.METHOD)["Limitation"]
    assert "common-bar level" in limitation
    assert "not at the exact quote-event level" in limitation


def test_the_synchronisation_claim_stays_at_the_bar_level():
    """Trade-to-trade, never trade-to-quote. The narrower claim is the provable one."""
    prose = writeup.SYNCHRONISATION
    assert "same hourly bar" in prose
    assert "cannot be established more precisely" in prose
    assert "NBBO" not in prose, "unverified for a .U RIC — do not claim it"
    assert "national best bid" not in prose


def test_no_document_claims_the_quotes_are_nbbo():
    for prose in (writeup.OBSERVATION_POINT, writeup.SYNCHRONISATION,
                  writeup.MIDPOINT_EVIDENCE, *[t for _, t in writeup.METHOD]):
        assert "NBBO" not in prose and "national best bid" not in prose


def test_the_midpoint_example_is_offered_as_an_example_not_as_proof():
    prose = writeup.MIDPOINT_EVIDENCE
    assert "$4.80" in prose and "$4.81" in prose
    assert "not evidence by itself" in prose
    assert "R²" in prose


def test_the_method_hierarchy_is_complete_and_ordered():
    assert [label for label, _ in writeup.METHOD] == [
        "Rule", "Fill", "Stock", "Audit evidence", "Limitation"
    ]
    assert all(text and text != writeup.UNWRITTEN for _, text in writeup.METHOD)


def test_every_write_up_question_has_a_slot():
    assert len(writeup.QUESTIONS) == len(writeup.ANSWERS)
    assert all(q.endswith("?") for q in writeup.QUESTIONS)


def test_the_unwritten_marker_is_detectable_so_the_page_can_refuse_to_ship():
    """FR-19 has no figure behind it, so nothing about the render fails when it is missing."""
    unwritten = [i for i, a in enumerate(writeup.ANSWERS) if a == writeup.UNWRITTEN]
    assert unwritten == list(range(len(writeup.ANSWERS))), (
        "expected all five still unwritten; if the PO has answered some, tighten this test "
        "rather than deleting it"
    )
