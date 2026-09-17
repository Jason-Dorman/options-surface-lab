"""Assignment 2 — the covered-call backtest (AD-12).

Layered inside, exactly as ARCHITECTURE §2 prescribes for the flat modules:
``tape`` and ``live`` (acquisition — the only two modules that reach the
network, and in each it is a single seam), ``rules`` + ``engine`` + ``evidence``
(the transform core — no plotly, no theme), then presentation and the page.
The three have one responsibility each: ``rules`` is what the strategy *decides*,
``engine`` is the book those decisions *produce*, and ``evidence`` is what the
tape *says* — which is why ``evidence`` never imports ``engine``, and the fit is a
check on the fill assumption rather than a restatement of it.  The blotter-row
constructors sit in ``rules`` rather than in whichever module books first, so
that ``engine`` never imports a module holding the network (AD-12, NFR-5).

Specified in ``docs/SPEC-COVERED-CALL.md``; every constant traces to a PO
decision ``SD-x`` in ``docs/PRD.md`` §15.
"""
