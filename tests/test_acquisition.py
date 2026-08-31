"""Shape-normalisation tests for the LSEG acquisition path (T-27).

`get_history` returns four different column shapes depending on the request. The old
code assumed one of them, which silently destroyed data. These tests pin all four.
"""

import numpy as np
import pandas as pd
import pytest

from options_surface_lab.options_surface_app import _fetch_universe, _normalize_history

FIELDS = ("TRDPRC_1", "SETTLE")
IDX = pd.date_range("2026-06-08", periods=3, freq="D", name="Date")
R1, R2 = "UUUUF122601100.U^F26", "UUUUF122601200.U^F26"


def _expect(df, rics):
    assert df is not None
    assert list(df.columns.names) == ["RIC", "Field"]
    assert list(dict.fromkeys(df.columns.get_level_values(0))) == list(rics)
    for r in rics:
        assert list(df[r].columns) == list(FIELDS), "every requested field must survive"


def test_multiindex_ric_field_passes_through():
    cols = pd.MultiIndex.from_product([[R1, R2], FIELDS])
    raw = pd.DataFrame(1.0, index=IDX, columns=cols)
    _expect(_normalize_history(raw, [R1, R2], FIELDS), [R1, R2])


def test_multiindex_field_ric_is_swapped():
    cols = pd.MultiIndex.from_product([FIELDS, [R1, R2]])
    raw = pd.DataFrame(1.0, index=IDX, columns=cols)
    out = _normalize_history(raw, [R1, R2], FIELDS)
    _expect(out, [R1, R2])
    assert out[(R1, "SETTLE")].notna().all()


def test_many_rics_one_field_is_the_shape_that_broke_the_real_pull():
    # what the 2026-08-30 pull actually returned: flat RIC columns, field as axis name
    raw = pd.DataFrame(1.0, index=IDX, columns=pd.Index([R1, R2], name="TRDPRC_1"))
    out = _normalize_history(raw, [R1, R2], FIELDS)
    _expect(out, [R1, R2])
    assert out[(R1, "TRDPRC_1")].notna().all()
    # SETTLE is preserved as an explicit empty column — the evidence is no longer erased
    assert out[(R1, "SETTLE")].isna().all()


def test_single_ric_returns_bare_field_columns_and_keeps_its_identity():
    raw = pd.DataFrame(1.0, index=IDX, columns=pd.Index(list(FIELDS)))
    _expect(_normalize_history(raw, [R1], FIELDS), [R1])


def test_rics_that_never_existed_are_dropped_but_live_ones_survive():
    cols = pd.MultiIndex.from_product([[R1, R2], FIELDS])
    raw = pd.DataFrame(np.nan, index=IDX, columns=cols)
    raw[(R1, "TRDPRC_1")] = 1.0
    out = _normalize_history(raw, [R1, R2], FIELDS)
    _expect(out, [R1])


@pytest.mark.parametrize("empty", [None, pd.DataFrame()])
def test_empty_responses_are_none(empty):
    assert _normalize_history(empty, [R1], FIELDS) is None


class _FakeLd:
    """Rejects any multi-RIC batch, forcing the per-RIC fallback path."""

    def __init__(self):
        self.single_calls = 0

    def get_history(self, universe, fields, **kw):
        if len(universe) > 1:
            raise RuntimeError("batch rejected")
        self.single_calls += 1
        return pd.DataFrame(1.0, index=IDX, columns=pd.Index(list(fields)))


def test_per_ric_fallback_keeps_every_ric():
    """The old code appended identical bare-field frames, then `~columns.duplicated()`
    kept only the first — 1 RIC survived out of N. This is that regression."""
    ld = _FakeLd()
    out = _fetch_universe(ld, [R1, R2], FIELDS, "2026-06-08", "2026-06-10", batch_size=25)
    assert ld.single_calls == 2
    assert set(out.columns.get_level_values(0)) == {R1, R2}, "fallback lost a RIC's identity"
    assert out.shape[1] == 4  # 2 RICs x 2 fields
