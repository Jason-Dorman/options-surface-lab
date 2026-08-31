"""Seed tests for FR-3 (RIC parsing). Full transform coverage lands with FR-3.

Note: the README's printed example RIC (UUUUA1502601250.U^A26) carries an extra
digit vs its own Appendix A grammar ({M}{DD}{YY}{SSSSS} = 9 digits); these tests
use the grammar-correct 9-digit form, which is what the parser and the starter's
RIC generator both implement.
"""

import datetime as dt

from options_surface_lab.option_surface_utils import parse_option_ric


def test_call_with_expired_suffix():
    parsed = parse_option_ric("UUUUA152601250.U^A26")
    assert parsed is not None
    assert parsed["root"] == "UUUU"
    assert parsed["cp"] == "C"
    assert parsed["expiry"] == dt.date(2026, 1, 15)
    assert parsed["strike"] == 12.50
    assert parsed["month_code"] == "A"


def test_put_month_code():
    parsed = parse_option_ric("UUUUM152600650.U^M26")
    assert parsed is not None
    assert parsed["cp"] == "P"
    assert parsed["expiry"] == dt.date(2026, 1, 15)
    assert parsed["strike"] == 6.50


def test_bare_ric_without_expired_suffix():
    parsed = parse_option_ric("UUUUA152601250.U")
    assert parsed is not None
    assert parsed["cp"] == "C"
    assert parsed["strike"] == 12.50


def test_lowercase_ric_normalized():
    parsed = parse_option_ric("uuuua152601250.u")
    assert parsed is not None
    assert parsed["root"] == "UUUU"


def test_invalid_calendar_date_rejected():
    # Feb 31 does not exist
    assert parse_option_ric("UUUUB312601250.U") is None


def test_garbage_rejected():
    assert parse_option_ric("not-a-ric") is None
