"""Assignment 2's prose. **Authored by the PO** — this module generates nothing.

Same contract as ``commentary.py`` for 1.1: prose and nothing else, no imports, no
data, no formatting decisions, imported by every rendering so the published page and
the dev app cannot say different things.

``[unwritten]`` marks a slot the PO has not written yet. It renders in red, fails its
test, and the Pages workflow refuses to deploy — three guards, because a missing
rubric item is invisible on a page that otherwise renders perfectly (the FR-7 lesson,
applied to FR-19).

``METHOD`` was written by the PO on 2026-09-14, out of the review that followed
T-80's rehearsal. The three paragraphs that sat beside it folded into the answers on
2026-09-18: two of them restated an answer's own opening sentence, and the midpoint
example was strictly weaker than the R² and the $49.50 bid-versus-mid bound that
``ANSWERS[2]`` now cites. ``OBSERVATION_POINT_FACTS`` outlived its paragraph on
purpose — ``test_writeup.py`` re-runs ``select_strike`` on those two prices, so the
rule stays held to the argument whether or not the prose spells the numbers out.
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


#: The numbers behind the observation-point argument in the first answer, kept as data so a
#: test can re-run ``select_strike`` on them. The paragraph that quoted them folded into
#: ``ANSWERS[0]`` on 2026-09-18; these two prices are what made the argument checkable, and
#: the rule is held to them whether or not the prose spells them out.
OBSERVATION_POINT_FACTS = {
    "bar": "2026-09-08 15:00",
    "open": 719.315,
    "open_selects": 720.0,
    "close": 718.41,
    "close_selects": 719.0,
}


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
    # The observation-point paragraph folded in here on 2026-09-18 (it was a separate block
    # above, restating this answer's own first sentence). The sentences are the PO's,
    # unchanged but for the spaces the literal joins had dropped.
    "I used the nearest out-of-the-money call based on QQQ’s final price in the Monday "
    "15:00–16:00 bar. With $1 strike spacing, that landed almost exactly at-the-money; a "
    "median 0.032% above spot. If that strike had no valid two-sided quote the trade is "
    "skipped. Analysis showed by selecting the strike at the next dollar from the spot can "
    "change the strike selection from the open to the close of the last hourly bar due to "
    "QQQ’s volatility. Using the close keeps the rule consistent.",

    "Hold through Friday’s 15:00 ET bar. If QQQ finishes below the strike, the call "
    "expires and we keep the shares. If it finishes above, the shares are assigned at the "
    "strike and the position closes. No early exit or roll. The goal is to measure the full "
    "covered-call payoff through expiry.",

    # The synchronisation caveat folded in here on the same day: it is the limit of this
    # answer's own claim, and METHOD's "Limitation" row states it behind a <details>, where
    # a reader judging the fill assumption will not necessarily open it.
    "Trades tracked the midpoint closely (R² = 0.9962), with a median gap of $0.035. "
    "Using the bid instead barely changed return, from 1.658% to 1.592%. Spot and option "
    "data come from the same hourly bar, with their final trades executed five seconds "
    "apart. LSEG doesn’t timestamp the final quote update so tighter synchronization "
    "isn’t possible.",

    "We used Reg T with a fully funded $75,000 account, so the covered call added no extra "
    "margin requirement. With less cash the same trades would introduce borrowing and "
    "interest costs.",

    "Over ten weeks, the strategy returned 1.66% versus -1.00% for buy-and-hold, but the "
    "near-ATM strikes gave up meaningful upside - including $528.50 in the live week. Next "
    "I’d test a farther-OTM rule, such as 30-delta.",
)
