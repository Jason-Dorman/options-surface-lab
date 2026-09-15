"""Assignment 2's prose. **Authored by the PO** — this module generates nothing.

Same contract as ``commentary.py`` for 1.1: prose and nothing else, no imports, no
data, no formatting decisions, imported by every rendering so the published page and
the dev app cannot say different things.

``[unwritten]`` marks a slot the PO has not written yet. It renders in red, fails its
test, and the Pages workflow refuses to deploy — three guards, because a missing
rubric item is invisible on a page that otherwise renders perfectly (the FR-7 lesson,
applied to FR-19).

The methodology block below was written by the PO on 2026-09-14, out of the review
that followed T-80's rehearsal. Its numbers are not decorative: ``test_writeup.py``
re-runs ``select_strike`` on the two quoted prices and fails if the rule no longer
does what the paragraph says it does.
"""

UNWRITTEN = "[unwritten]"


# --------------------------------------------------------------------------
# The decision hierarchy, as it appears on the page
# --------------------------------------------------------------------------
METHOD = (
    ("Rule",
     "Closing observation of the Monday hourly bar, then choose the nearest "
     "out-of-the-money strike."),
    ("Fill",
     "The final bid and ask reported for that same hourly option bar, filled at "
     "the midpoint."),
    ("Stock",
     "The final observed stock print in that bar."),
    ("Audit evidence",
     "The stock and option last-trade offsets and the intra-bar range are shown "
     "for inspection."),
    ("Limitation",
     "The quote-update timestamp is unavailable, so synchronization is "
     "established at the common-bar level, not at the exact quote-event level."),
)


# --------------------------------------------------------------------------
# Why the observation point is defined, and not merely the hour
# --------------------------------------------------------------------------
OBSERVATION_POINT = (
    "Strike selection is based on the final stock observation in the Monday entry "
    "bar rather than merely identifying the entry hour. This distinction matters: "
    "on September 8, QQQ opened the 15:00–16:00 bar at $719.315 but finished at "
    "$718.41, meaning an opening observation would have selected the $720 call "
    "while the closing observation selected $719. Fixing the observation point "
    "prevents strike selection from becoming ambiguous or discretionary."
)

#: The numbers ``OBSERVATION_POINT`` asserts, so a test can hold the prose to the rule.
OBSERVATION_POINT_FACTS = {
    "bar": "2026-09-08 15:00",
    "open": 719.315,
    "open_selects": 720.0,
    "close": 718.41,
    "close_selects": 719.0,
}


SYNCHRONISATION = (
    "The stock and option observations come from the same hourly bar. Their final "
    "reported trades occurred five seconds apart, and spot finished at $718.41, "
    "below the $719 strike selected by the rule. LSEG does not expose a timestamp "
    "for the final bid/ask update at this resolution, so quote-level "
    "synchronization cannot be established more precisely."
)


MIDPOINT_EVIDENCE = (
    "For this example, the modeled midpoint fill was $4.80 versus an actual trade "
    "price of $4.81. This single observation is encouraging but not evidence by "
    "itself; the chain-wide midpoint-versus-trade regression and R² test whether "
    "midpoint fills are generally a reasonable execution assumption."
)


# --------------------------------------------------------------------------
# FR-19's write-up questions — T-60, the PO's to answer
# --------------------------------------------------------------------------
QUESTIONS = (
    "How did you choose the strike?",
    "What is the exit rule, and why wait through expiry?",
    "Why is the midpoint a defensible fill, and what does the R² show?",
    "Why Reg T, and what would change under a margin-funded account?",
    "What happened over the ten weeks, where did theory meet the tape, and what "
    "would you change?",
)

ANSWERS = (
    UNWRITTEN,
    UNWRITTEN,
    UNWRITTEN,
    UNWRITTEN,
    UNWRITTEN,
)
