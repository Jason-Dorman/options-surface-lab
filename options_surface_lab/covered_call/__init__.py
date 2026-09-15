"""Assignment 2 — the covered-call backtest (AD-12).

Layered inside, exactly as ARCHITECTURE §2 prescribes for the flat modules:
``tape`` (acquisition, the only network), ``rules`` + ``engine`` (the transform
core — no plotly, no theme), then presentation and the page.

Specified in ``docs/SPEC-COVERED-CALL.md``; every constant traces to a PO
decision ``SD-x`` in ``docs/PRD.md`` §15.
"""
