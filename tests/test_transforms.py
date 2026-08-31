"""FR-3 transform coverage (T-4) — the gate for every later refactor (NFR-2).

Locks the pure-function chain of SYSTEM-SPEC §7:
    flatten_lseg_options -> attach_underlying -> pivot_trade_settle -> summarize_sparsity
plus `surface_grid`'s no-extrapolation guarantee (§7.4, AD-9).

RIC-grammar parsing itself lives in `test_ric_parsing.py`; here RICs are only inputs.
"""

import numpy as np
import pandas as pd
import pytest

from options_surface_lab.option_surface_utils import (
    attach_underlying,
    flatten_lseg_options,
    pivot_trade_settle,
    summarize_sparsity,
    surface_grid,
    synthesize_demo_payload,
)

CALL = "UUUUA152601250.U^A26"   # UUUU 2026-01-15 call, K = 12.50
PUT = "UUUUM152600650.U^M26"    # UUUU 2026-01-15 put,  K =  6.50

D5 = pd.Timestamp("2026-01-05")
D6 = pd.Timestamp("2026-01-06")


def _lseg_frame() -> pd.DataFrame:
    """Two sessions of an LSEG (RIC, field) panel: one settle-only series, one with both."""
    cols = pd.MultiIndex.from_tuples(
        [(CALL, "SETTLE"), (CALL, "TRDPRC_1"), (PUT, "SETTLE")],
        names=["RIC", "Field"],
    )
    return pd.DataFrame(
        [[1.00, 1.10, 0.50],
         [1.20, np.nan, 0.60]],
        index=pd.to_datetime([D5, D6]),
        columns=cols,
    )


def _sorted(tidy: pd.DataFrame) -> pd.DataFrame:
    return tidy.sort_values(["date", "ric", "field"]).reset_index(drop=True)


# --------------------------------------------------------------------------- flatten


def test_flatten_produces_one_row_per_observation():
    tidy = flatten_lseg_options(_lseg_frame())
    # 3 series x 2 sessions, less the one absent trade print
    assert len(tidy) == 5
    call_settle = tidy[(tidy["ric"] == CALL) & (tidy["field"] == "SETTLE")]
    assert sorted(call_settle["value"]) == [1.00, 1.20]
    assert set(tidy["field"]) == {"SETTLE", "TRDPRC_1"}


def test_flatten_carries_parsed_ric_fields_and_dte():
    tidy = flatten_lseg_options(_lseg_frame())
    row = tidy[(tidy["ric"] == CALL) & (tidy["date"] == D5)].iloc[0]
    assert row["root"] == "UUUU"
    assert row["cp"] == "C"
    assert row["strike"] == 12.50
    assert row["expiry"] == pd.Timestamp("2026-01-15")
    assert row["dte"] == 10  # calendar days, Jan 05 -> Jan 15
    assert tidy[tidy["ric"] == PUT]["cp"].eq("P").all()


def test_flatten_is_identical_for_both_multiindex_orders():
    """FR-3 acceptance: (RIC, field) and (field, RIC) columns flatten the same."""
    frame = _lseg_frame()
    swapped = frame.copy()
    swapped.columns = swapped.columns.swaplevel(0, 1)
    pd.testing.assert_frame_equal(
        _sorted(flatten_lseg_options(frame)),
        _sorted(flatten_lseg_options(swapped)),
    )


def test_flatten_handles_flat_columns():
    """Bare RIC columns default to TRDPRC_1; 'RIC | FIELD' labels split."""
    flat = pd.DataFrame(
        {CALL: [1.0], PUT + " | SETTLE": [0.5]},
        index=pd.to_datetime([D5]),
    )
    tidy = flatten_lseg_options(flat)
    assert len(tidy) == 2
    assert tidy.loc[tidy["ric"] == CALL, "field"].item() == "TRDPRC_1"
    assert tidy.loc[tidy["ric"] == PUT, "field"].item() == "SETTLE"


def test_flatten_coerces_a_non_datetime_index():
    cols = pd.MultiIndex.from_tuples([(CALL, "SETTLE")])
    frame = pd.DataFrame([[1.0]], index=["2026-01-05"], columns=cols)
    assert flatten_lseg_options(frame)["date"].tolist() == [D5]


def test_flatten_drops_columns_whose_ric_does_not_parse():
    """SPEC §6: unparseable RIC columns are silently dropped, not raised on."""
    cols = pd.MultiIndex.from_tuples([(CALL, "SETTLE"), ("not-a-ric", "SETTLE")])
    frame = pd.DataFrame([[1.0, 9.9]], index=pd.to_datetime([D5]), columns=cols)
    tidy = flatten_lseg_options(frame)
    assert list(tidy["ric"]) == [CALL]


def test_flatten_drops_non_numeric_and_non_finite_values():
    cols = pd.MultiIndex.from_tuples([(CALL, "SETTLE"), (CALL, "TRDPRC_1")])
    frame = pd.DataFrame([[np.inf, "n/a"]], index=pd.to_datetime([D5]), columns=cols)
    assert flatten_lseg_options(frame).empty


def test_flatten_drops_observations_after_expiry():
    """dte < 0 rows are dropped (SPEC §7.1)."""
    cols = pd.MultiIndex.from_tuples([(CALL, "SETTLE")])
    frame = pd.DataFrame(
        [[1.0], [2.0]],
        index=pd.to_datetime(["2026-01-20", D5]),  # Jan 20 is past the Jan 15 expiry
        columns=cols,
    )
    tidy = flatten_lseg_options(frame)
    assert tidy["date"].tolist() == [D5]
    assert (tidy["dte"] >= 0).all()


def test_flatten_empty_input_returns_typed_empty_frame():
    tidy = flatten_lseg_options(pd.DataFrame())
    assert tidy.empty
    assert {"date", "ric", "field", "value", "strike", "cp"} <= set(tidy.columns)


# ------------------------------------------------------------------- attach_underlying


def test_attach_underlying_joins_spot_and_moneyness():
    tidy = flatten_lseg_options(_lseg_frame())
    stock = pd.DataFrame({"TRDPRC_1": [8.0, 10.0]}, index=pd.to_datetime([D5, D6]))
    joined = attach_underlying(tidy, stock)
    jan5_call = joined[(joined["date"] == D5) & (joined["ric"] == CALL)].iloc[0]
    assert jan5_call["spot"] == 8.0
    assert jan5_call["moneyness"] == pytest.approx(12.50 / 8.0)
    assert joined[joined["date"] == D6]["spot"].eq(10.0).all()


def test_attach_underlying_falls_back_to_nearest_prior_session():
    """SPEC §7.1: a missing session takes the most recent prior close, never a later one."""
    tidy = flatten_lseg_options(_lseg_frame())
    stock = pd.DataFrame(
        {"TRDPRC_1": [8.0, 99.0]},
        index=pd.to_datetime([D5, "2026-01-09"]),  # Jan 06 absent
    )
    joined = attach_underlying(tidy, stock)
    assert joined[joined["date"] == D6]["spot"].eq(8.0).all()


def test_attach_underlying_leaves_nan_when_no_prior_session_exists():
    tidy = flatten_lseg_options(_lseg_frame())
    stock = pd.DataFrame({"TRDPRC_1": [8.0]}, index=pd.to_datetime(["2026-01-09"]))
    joined = attach_underlying(tidy, stock)
    assert joined["spot"].isna().all()
    assert joined["moneyness"].isna().all()


def test_attach_underlying_tolerates_missing_stock_frame():
    tidy = flatten_lseg_options(_lseg_frame())
    joined = attach_underlying(tidy, pd.DataFrame())
    assert joined["spot"].isna().all()
    assert len(joined) == len(tidy)


def test_attach_underlying_uses_last_column_when_trdprc_absent():
    tidy = flatten_lseg_options(_lseg_frame())
    stock = pd.DataFrame({"OPEN_PRC": [1.0], "CLOSE": [9.0]}, index=pd.to_datetime([D5]))
    joined = attach_underlying(tidy, stock)
    assert joined[joined["date"] == D5]["spot"].eq(9.0).all()


def test_attach_underlying_on_empty_tidy_still_yields_spot_columns():
    empty = flatten_lseg_options(pd.DataFrame())
    joined = attach_underlying(empty, pd.DataFrame({"TRDPRC_1": [8.0]}, index=[D5]))
    assert joined.empty
    assert {"spot", "moneyness"} <= set(joined.columns)


# ----------------------------------------------------------------- pivot_trade_settle


def _tidy_rows(*rows) -> pd.DataFrame:
    """Hand-built tidy rows, all on D5, so pivot assertions are exact."""
    base = dict(
        root="UUUU", cp="C", expiry=pd.Timestamp("2026-01-15"),
        strike=12.5, dte=10, spot=8.0, moneyness=1.5625,
    )
    return pd.DataFrame(
        [{"date": D5, "ric": ric, "field": field, "value": value, **base}
         for ric, field, value in rows]
    )


def test_pivot_pairs_settle_and_trade_on_one_row():
    wide = pivot_trade_settle(_tidy_rows(("R1", "SETTLE", 1.0), ("R1", "TRDPRC_1", 1.1)))
    assert len(wide) == 1
    row = wide.iloc[0]
    assert row["MARK"] == 1.0
    assert row["TRDPRC_1"] == 1.1
    assert bool(row["has_mark"]) and bool(row["has_trade"])
    assert row["abs_diff"] == pytest.approx(0.1)
    assert row["rel_diff"] == pytest.approx(0.1)


def test_pivot_marks_settle_only_series():
    wide = pivot_trade_settle(_tidy_rows(("R1", "SETTLE", 1.0)))
    row = wide.iloc[0]
    assert bool(row["has_mark"]) and not bool(row["has_trade"])
    assert np.isnan(row["TRDPRC_1"])
    assert np.isnan(row["abs_diff"])


def test_pivot_folds_close_into_trdprc():
    """SPEC §7.2: CLOSE, when present, is folded into the trade print."""
    wide = pivot_trade_settle(_tidy_rows(("R1", "CLOSE", 3.0)))
    assert wide.iloc[0]["TRDPRC_1"] == 3.0
    assert bool(wide.iloc[0]["has_trade"])


def test_pivot_keeps_the_quote_sides_but_ignores_everything_else():
    """BID/ASK are kept deliberately — the spread is derived from them.

    A contract-day quoted with only one side is still a listed contract-day: it survives as a
    row with no mark and no trade, which is what puts it in the FR-6 denominator without
    letting it into the numerator.
    """
    wide = pivot_trade_settle(
        _tidy_rows(("R1", "SETTLE", 1.0), ("R2", "BID", 7.0), ("R3", "DELTA", 0.4))
    )
    assert sorted(wide["ric"]) == ["R1", "R2"], "DELTA is not a price and must be dropped"
    r2 = wide[wide["ric"] == "R2"].iloc[0]
    assert not r2["has_mark"] and not r2["has_trade"]


def test_pivot_collapses_duplicate_observations_taking_the_last():
    wide = pivot_trade_settle(_tidy_rows(("R1", "SETTLE", 1.0), ("R1", "SETTLE", 2.0)))
    assert len(wide) == 1
    assert wide.iloc[0]["MARK"] == 2.0


def test_pivot_rel_diff_is_nan_when_settle_is_zero():
    wide = pivot_trade_settle(_tidy_rows(("R1", "SETTLE", 0.0), ("R1", "TRDPRC_1", 0.4)))
    row = wide.iloc[0]
    assert row["abs_diff"] == pytest.approx(0.4)
    assert np.isnan(row["rel_diff"])


def test_pivot_empty_input_returns_empty():
    assert pivot_trade_settle(pd.DataFrame()).empty


def test_pivot_keeps_rows_when_spot_is_unknown():
    """Fixed 2026-08-30 (checkpoint_audit §1): an unknown spot must not delete the quote.

    pivot_table drops any row with NaN in its index, so pivoting on `spot` silently deleted
    observations. AD-9: missing data renders as a hole, never as a vanished row.
    """
    tidy = flatten_lseg_options(_lseg_frame())
    tidy = attach_underlying(tidy, pd.DataFrame())  # every spot NaN
    wide = pivot_trade_settle(tidy)
    # 2 series on Jan 05 + 2 on Jan 06
    assert len(wide) == 4
    assert wide["spot"].isna().all(), "spot must survive as NaN, not remove the row"
    assert wide["MARK"].notna().any() or wide["TRDPRC_1"].notna().any()


# ----------------------------------------------------------------- summarize_sparsity


def test_summarize_counts_and_percent():
    tidy = _tidy_rows(
        ("R1", "SETTLE", 1.0), ("R1", "TRDPRC_1", 1.1),   # both
        ("R2", "SETTLE", 0.5),                            # settle only
        ("R3", "SETTLE", 0.8),                            # settle only
        ("R4", "TRDPRC_1", 2.0),                          # print only
    )
    stats = summarize_sparsity(pivot_trade_settle(tidy))
    assert stats["n_quotes"] == 4
    assert stats["n_both"] == 1
    assert stats["n_mark_only"] == 2
    assert stats["n_trade_only"] == 1
    assert stats["pct_mark_no_trade"] == pytest.approx(50.0)
    assert stats["n_series"] == 4
    assert stats["n_dates"] == 1


def test_summarize_medians_use_only_rows_with_both_fields():
    tidy = _tidy_rows(
        ("R1", "SETTLE", 1.0), ("R1", "TRDPRC_1", 1.1),
        ("R2", "SETTLE", 2.0), ("R2", "TRDPRC_1", 2.6),
        ("R3", "SETTLE", 5.0),  # settle only — must not enter the medians
    )
    stats = summarize_sparsity(pivot_trade_settle(tidy))
    assert stats["median_abs_diff"] == pytest.approx(0.35)      # median(0.1, 0.6)
    assert stats["median_rel_diff_pct"] == pytest.approx(20.0)  # median(10%, 30%)


def test_summarize_medians_are_none_without_overlap():
    stats = summarize_sparsity(pivot_trade_settle(_tidy_rows(("R1", "SETTLE", 1.0))))
    assert stats["n_both"] == 0
    assert stats["median_abs_diff"] is None
    assert stats["median_rel_diff_pct"] is None
    assert stats["pct_mark_no_trade"] == pytest.approx(100.0)


def test_summarize_empty_input_returns_zeros_and_never_raises():
    stats = summarize_sparsity(pd.DataFrame())
    assert stats["n_quotes"] == 0
    assert stats["pct_mark_no_trade"] == 0.0
    assert stats["median_abs_diff"] is None
    assert summarize_sparsity(None)["n_quotes"] == 0


# ----------------------------------------------------------------------- surface_grid


def test_surface_grid_returns_none_below_eight_points():
    cloud = pd.DataFrame({"strike": range(7), "dte": range(7), "v": [1.0] * 7})
    assert surface_grid(cloud, "v") is None


def test_surface_grid_interpolates_but_never_extrapolates():
    """AD-9 / SPEC §7.4: cells outside the convex hull stay NaN so holes render as holes."""
    rng = np.random.default_rng(0)
    # An L-shaped cloud: the far corner has no data and must stay empty.
    strike = np.concatenate([rng.uniform(5, 15, 40), rng.uniform(5, 7, 20)])
    dte = np.concatenate([rng.uniform(0, 5, 40), rng.uniform(5, 60, 20)])
    cloud = pd.DataFrame({"strike": strike, "dte": dte})
    cloud["v"] = 0.1 * cloud["strike"] + 0.01 * cloud["dte"]

    grid = surface_grid(cloud, "v", n_strike=40, n_dte=30)
    assert grid["x"].shape == (40,) and grid["y"].shape == (30,)
    assert grid["z"].shape == (30, 40)
    assert np.isnan(grid["z"]).any(), "empty wings must stay NaN, not be filled"
    filled = grid["z"][~np.isnan(grid["z"])]
    # linear interpolation stays inside the cloud's own range — no invented extremes
    assert filled.min() >= cloud["v"].min() - 1e-9
    assert filled.max() <= cloud["v"].max() + 1e-9


# ------------------------------------------------- seeded synthetic panel (SPEC §11)


def test_synthetic_payload_matches_the_lseg_payload_contract(synthetic_payload):
    assert {"stock", "options", "ticker", "fetched_at", "synthetic"} <= set(synthetic_payload)
    assert synthetic_payload["synthetic"] is True
    options = synthetic_payload["options"]
    assert isinstance(options.columns, pd.MultiIndex)
    assert list(options.columns.names) == ["RIC", "Field"]
    assert set(options.columns.get_level_values("Field")) <= {"SETTLE", "TRDPRC_1"}
    assert "TRDPRC_1" in synthetic_payload["stock"].columns


def test_synthetic_panel_is_reproducible_for_a_given_seed():
    """Same seed -> identical panel, so the fixture is a stable refactor gate."""
    a = synthesize_demo_payload(seed=3, weeks_back=2)
    b = synthesize_demo_payload(seed=3, weeks_back=2)
    pd.testing.assert_frame_equal(a["stock"], b["stock"])
    pd.testing.assert_frame_equal(a["options"], b["options"])
    other = synthesize_demo_payload(seed=4, weeks_back=2)
    assert not other["stock"]["TRDPRC_1"].equals(a["stock"]["TRDPRC_1"])


def test_synthetic_panel_survives_the_whole_chain(synthetic_wide):
    wide = synthetic_wide
    assert len(wide) > 1000
    assert (wide["dte"] >= 0).all()
    assert wide["spot"].notna().all()
    assert not wide.duplicated(subset=["date", "ric"]).any()
    assert wide["moneyness"].between(0, 10).all()


def test_synthetic_panel_reproduces_the_teaching_asymmetry(synthetic_wide):
    """PRD §2.2: settles print nearly everywhere, trades only where someone traded."""
    stats = summarize_sparsity(synthetic_wide)
    assert stats["n_mark_only"] > stats["n_both"]
    assert stats["pct_mark_no_trade"] > 50.0
    # a print with no settle is not a shape this generator produces
    assert stats["n_trade_only"] == 0
    assert stats["median_abs_diff"] is not None and stats["median_abs_diff"] > 0


def test_synthetic_prints_concentrate_near_the_money(synthetic_wide):
    """SPEC §11's print-probability ladder must survive the transforms."""
    near = np.log(synthetic_wide["moneyness"]).abs() < 0.25
    assert synthetic_wide.loc[near, "has_trade"].mean() > synthetic_wide.loc[~near, "has_trade"].mean()


# ------------------------------------------------------- surface_grid degenerate inputs


def _cloud(strikes, dtes, value=1.0):
    rows = [{"strike": k, "dte": d, "MARK": value + i * 0.01}
            for i, (k, d) in enumerate((k, d) for d in dtes for k in strikes)]
    return pd.DataFrame(rows)


def test_surface_grid_returns_none_for_a_single_expiry():
    """One expiry = one DTE = a flat cloud. Qhull raises on it; we must not (AD-9).

    The last date of a weeklies panel always looks like this, so this is a normal slice.
    """
    assert surface_grid(_cloud([10, 11, 12, 13, 14, 15, 16, 17, 18], [7]), "MARK") is None


def test_surface_grid_returns_none_for_a_single_strike():
    assert surface_grid(_cloud([12.5], list(range(1, 12))), "MARK") is None


def test_surface_grid_builds_for_a_genuine_two_dimensional_cloud():
    grid = surface_grid(_cloud([10, 11, 12, 13], [3, 10, 17]), "MARK")
    assert grid is not None
    assert grid["z"].shape == (30, 40)


# --------------------------------------------------------------------- bid-ask spread


def test_spread_columns_are_derived_from_the_quote_sides():
    tidy = _tidy_rows(
        ("R1", "BID", 1.00), ("R1", "ASK", 1.40), ("R1", "MID_PRICE", 1.20),
        ("R1", "TRDPRC_1", 1.15),
    )
    row = pivot_trade_settle(tidy).iloc[0]
    assert row["spread"] == pytest.approx(0.40)
    assert row["spread_pct"] == pytest.approx(100 * 0.40 / 1.20)


def test_spread_is_undefined_without_both_sides():
    """No bid means no midpoint and no spread — a hole, not a zero (AD-9)."""
    tidy = _tidy_rows(("R1", "ASK", 2.00), ("R1", "TRDPRC_1", 1.15))
    row = pivot_trade_settle(tidy).iloc[0]
    assert pd.isna(row["spread"])
    assert pd.isna(row["spread_pct"])


def test_sparsity_reports_spread_even_when_absent():
    tidy = _tidy_rows(("R1", "SETTLE", 1.0), ("R1", "TRDPRC_1", 1.1))
    stats = summarize_sparsity(pivot_trade_settle(tidy))
    for key in ("median_spread", "median_spread_pct", "pct_spread_over_half"):
        assert key in stats
        assert stats[key] is None, "no quote sides means no spread, not a fabricated one"


def test_sparsity_flags_marks_you_should_not_believe():
    tidy = _tidy_rows(
        ("R1", "BID", 0.10), ("R1", "ASK", 2.00), ("R1", "MID_PRICE", 1.05),
        ("R2", "BID", 1.18), ("R2", "ASK", 1.22), ("R2", "MID_PRICE", 1.20),
    )
    stats = summarize_sparsity(pivot_trade_settle(tidy))
    # R1's spread is 181% of its mark; R2's is 3%. Exactly half the rows are untrustworthy.
    assert stats["pct_spread_over_half"] == pytest.approx(50.0)
