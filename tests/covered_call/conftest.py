"""Fixtures for Assignment 2 (AD-7, T-63).

The synthetic tape is the deterministic fixture for everything that needs *a* tape
rather than *the* tape: the engine's invariants, the evidence fit, the page. It is
built once per session — it is cheap, but it is also one object every test may share
precisely because nothing may mutate it.

**Its window is fixed, not today's.** `FIXTURE_END_DATE` is a literal, which is the
whole point of T-63 and the fix for OQ-6: a fixture anchored to the clock reports on
the calendar, and one already failed CI on a Monday for a reason that had nothing to
do with the code under test (`test_a_refused_strike_breaks_the_line…`, 2026-09-07).

The real tape is *not* a fixture here. Tests that want it should say so explicitly
and skip when it is absent, so the suite still passes on a machine that has not
pulled it.
"""
from __future__ import annotations

import datetime as dt

import pytest

from options_surface_lab.covered_call.rules import Params
from options_surface_lab.covered_call.tape import (
    SYNTHETIC_ROLES,
    TAPE_PATH,
    load_tape,
    synthesize_tape,
)

#: A Friday, and a literal. Never `today()`, never derived from it.
FIXTURE_END_DATE = dt.date(2026, 9, 11)
FIXTURE_SEED = 7


@pytest.fixture(scope="session")
def fixture_end_date() -> dt.date:
    """The literal above, as a fixture — so a test that synthesizes a *second* tape
    (a different seed, say) anchors to the same window as ``synthetic_tape`` instead
    of writing the date out again and drifting from it."""
    return FIXTURE_END_DATE


@pytest.fixture(scope="session")
def params() -> Params:
    """The PO's decisions (SD-1…SD-6), as the engine receives them."""
    return Params()


@pytest.fixture(scope="session")
def synthetic_tape():
    """The seeded synthetic tape — same schema and payload shape as a pulled one."""
    return synthesize_tape(FIXTURE_END_DATE, seed=FIXTURE_SEED)


@pytest.fixture(scope="session")
def role_weeks(synthetic_tape) -> dict:
    """``{role: Week}`` for the fixture's named pathologies (SPEC §3.4).

    A test that needs the no-quote week asks for it by name; hunting for a week that
    happens to have the property is how a fixture change quietly stops testing what
    the test says it tests.
    """
    roles = synthetic_tape.meta["diagnostics"]["synthetic_roles"]
    weeks = {w.entry_day: w for w in synthetic_tape.weeks(Params())}
    out = {}
    for record in roles.values():
        role = record["role"]
        if role is None:
            continue
        first_session = dt.date.fromisoformat(record["sessions"][0])
        out[role] = weeks[first_session]
    assert set(out) == set(SYNTHETIC_ROLES.values()), "a named role has no week"
    return out


@pytest.fixture(scope="session")
def real_tape():
    """The committed tape, or a skip. Never synthesized behind the test's back."""
    if not TAPE_PATH.exists():
        pytest.skip(f"no committed tape at {TAPE_PATH} — run RUNBOOK §8")
    return load_tape(TAPE_PATH, fallback=False)
