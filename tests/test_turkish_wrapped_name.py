"""
Offline regression test: a Turkish Airlines passenger name that WRAPS.

The Passenger-information table is narrow. A long name keeps its first words on
the line that carries the ticket number and drops the rest to the next line,
ahead of the FFP column's lower-case text:

    MUSTAFA BULENT 2352530146363 The Frequent Flyer Program account has not been
    KARAARSLAN logged in for this passenger.

The parser read only the first line, so the document printed "Mustafa Bulent"
with the surname missing (real booking UVLPZR, 2026-10-28). A client's name must
match their passport at the gate, so a dropped surname is a wrong document (§7).

Names and numbers here are synthetic. Pure stdlib.
"""
import pathlib

import extractors as E

FIX = pathlib.Path(__file__).parent / "fixtures" / "turkish_airlines_connecting.txt"
ONE = "TEST PASSENGER 9990000000001 The Frequent Flyer Program account has not been\nlogged in for this passenger."


def _with_block(block):
    t = FIX.read_text(encoding="utf-8")
    assert ONE in t, "fixture layout changed"
    return E.extract_turkish_airlines(t.replace(ONE, block), None)


def _names(d):
    return [(p["name"], p["ticket_no"]) for p in d["passengers"]]


def test_surname_on_the_wrapped_line_is_kept():
    d = _with_block(
        "FIRSTA SECONDA 9990000000001 The Frequent Flyer Program account has not been\n"
        "THIRDA logged in for this passenger.\n"
        "Earn 600 Miles with Miles&Smiles on this flight")
    assert _names(d) == [("Firsta Seconda Thirda", "9990000000001")]


def test_two_passengers_one_wrapped_one_not():
    d = _with_block(
        "FIRSTA SECONDA 9990000000001 The Frequent Flyer Program account has not been\n"
        "THIRDA logged in for this passenger.\n"
        "Earn 600 Miles with Miles&Smiles on this flight\n"
        "FOURTHB FIFTHB 9990000000002 The Frequent Flyer Program account has not been\n"
        "logged in for this passenger.\n"
        "Earn 600 Miles with Miles&Smiles on this flight")
    assert _names(d) == [("Firsta Seconda Thirda", "9990000000001"),
                         ("Fourthb Fifthb", "9990000000002")]


def test_a_name_that_does_not_wrap_is_untouched():
    d = _with_block(ONE)
    assert _names(d) == [("Test Passenger", "9990000000001")]


def test_next_passengers_row_is_never_swallowed_as_a_continuation():
    """No 'Earn' line between rows: the second row carries a ticket number, so it
    must start a new passenger, not extend the first one's name."""
    d = _with_block(
        "FIRSTA SECONDA 9990000000001 The Frequent Flyer Program account has not been\n"
        "FOURTHB FIFTHB 9990000000002 The Frequent Flyer Program account has not been\n"
        "logged in for this passenger.")
    assert _names(d) == [("Firsta Seconda", "9990000000001"),
                         ("Fourthb Fifthb", "9990000000002")]
