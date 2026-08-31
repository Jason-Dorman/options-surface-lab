"""Shared fixtures for the transform tests (T-4, FR-3/NFR-2).

The seeded synthetic panel (SYSTEM-SPEC §11) is the deterministic fixture, but it is
expensive (~2 s) and anchored to `dt.date.today()`, so it is built once per session and
asserted on structurally rather than by exact value. Hand-built panels in
`test_transforms.py` carry the exact-value assertions.
"""

import pytest

from options_surface_lab.option_surface_utils import (
    attach_underlying,
    flatten_lseg_options,
    pivot_trade_settle,
    synthesize_demo_payload,
)


@pytest.fixture(scope="session")
def synthetic_payload() -> dict:
    """The seeded LSEG-shaped payload — same shape contract as the real pickle."""
    return synthesize_demo_payload(seed=7)


@pytest.fixture(scope="session")
def synthetic_wide(synthetic_payload):
    """The synthetic panel driven through the full pure-function chain (SPEC §7)."""
    tidy = flatten_lseg_options(synthetic_payload["options"])
    tidy = attach_underlying(tidy, synthetic_payload["stock"])
    return pivot_trade_settle(tidy)
