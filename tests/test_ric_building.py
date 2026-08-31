"""Round-trip tests for the RIC constructor (NFR-2 gate for the T-27 acquisition work)."""

import datetime as dt

import pytest

from options_surface_lab.option_surface_utils import (
    build_candidate_rics,
    build_option_ric,
    parse_option_ric,
)


def test_matches_readme_grammar_for_a_call():
    # README Appendix A, 9-digit form: UUUU 15-Jan-2026 call struck at $12.50
    assert build_option_ric("UUUU", dt.date(2026, 1, 15), "C", 12.50) == "UUUUA152601250.U^A26"


def test_matches_a_ric_the_live_api_accepted():
    # from the 2026-08-30 pull: UUUU 12-Jun-2026 call struck at $11.00
    assert build_option_ric("UUUU", dt.date(2026, 6, 12), "C", 11.00) == "UUUUF122601100.U^F26"


@pytest.mark.parametrize("month,call_code,put_code", list(zip(range(1, 13), "ABCDEFGHIJKL", "MNOPQRSTUVWX")))
def test_month_codes_follow_appendix_a(month, call_code, put_code):
    expiry = dt.date(2026, month, 15)
    assert build_option_ric("UUUU", expiry, "C", 10.0)[4] == call_code
    assert build_option_ric("UUUU", expiry, "P", 10.0)[4] == put_code


@pytest.mark.parametrize("cp", ["C", "P"])
@pytest.mark.parametrize("put_suffix", ["right", "call"])
def test_round_trips_through_the_parser(cp, put_suffix):
    expiry, strike = dt.date(2026, 6, 12), 13.5
    ric = build_option_ric("UUUU", expiry, cp, strike, put_suffix=put_suffix)
    parsed = parse_option_ric(ric)
    assert parsed is not None, f"{ric} does not parse"
    assert (parsed["root"], parsed["cp"], parsed["expiry"], parsed["strike"]) == (
        "UUUU", cp, expiry, strike,
    )


def test_default_put_suffix_is_the_empirically_verified_one():
    """2026-08-30: ^F26 returned 146 puts; the README's ^R26 returned none."""
    assert build_option_ric("UUUU", dt.date(2026, 6, 12), "P", 11.0) == "UUUUR122601100.U^F26"
    rics = build_candidate_rics("UUUU", [dt.date(2026, 6, 12)], [11.0], rights=("P",))
    assert rics == ["UUUUR122601100.U^F26"]


def test_put_suffix_styles_differ_only_in_the_suffix_and_only_for_puts():
    expiry = dt.date(2026, 6, 12)
    call_a = build_option_ric("UUUU", expiry, "C", 11.0, put_suffix="right")
    call_b = build_option_ric("UUUU", expiry, "C", 11.0, put_suffix="call")
    assert call_a == call_b == "UUUUF122601100.U^F26"

    assert build_option_ric("UUUU", expiry, "P", 11.0, put_suffix="right") == "UUUUR122601100.U^R26"
    assert build_option_ric("UUUU", expiry, "P", 11.0, put_suffix="call") == "UUUUR122601100.U^F26"


def test_strike_is_padded_to_five_digits():
    assert build_option_ric("UUUU", dt.date(2026, 6, 12), "C", 6.5).startswith("UUUUF122600650")


def test_rejects_a_bad_right():
    with pytest.raises(ValueError):
        build_option_ric("UUUU", dt.date(2026, 6, 12), "X", 10.0)


def test_candidate_grid_covers_every_combination():
    expiries = [dt.date(2026, 6, 12), dt.date(2026, 6, 19)]
    strikes = [10.0, 10.5, 11.0]
    rics = build_candidate_rics("UUUU", expiries, strikes)
    assert len(rics) == len(expiries) * len(strikes) * 2
    assert len(set(rics)) == len(rics)
    parsed = [parse_option_ric(r) for r in rics]
    assert all(parsed), "every generated RIC must parse"
    assert sum(p["cp"] == "C" for p in parsed) == sum(p["cp"] == "P" for p in parsed)
