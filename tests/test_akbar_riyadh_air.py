"""Riyadh Air: a carrier whose wrapped name left a CITY in the operator field.

Real Akbar booking AS261599740 (RX 863, RUH→KUL, 30 Sep 2026) shipped an
itinerary reading "OPERATED BY: Riyadh" — a city, not an airline. The real
pdfplumber text wraps the cell as:

    Operated by:Riyadh , Sat, 10 Oct 26 (08h:00m) Airport , Sun, 11 Oct 26
    Air

The 2026-08-19 re-join only pulled a continuation line back when it STARTED with
Airline(s) / Airways / Aviation, and Riyadh Air's continuation is the bare word
"Air". Matching "Air" loosely would have re-opened the 2026-08-20 defect, because
the To-column's "Airport , ..." bleed also begins with those letters — so "Air"
counts only when it is the ENTIRE continuation line.
"""
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

import extractors as E  # noqa: E402

WRAPPED = ("Operated by:Riyadh , Sat, 10 Oct 26 (08h:00m) Airport , Sun, 11 Oct 26\n"
           "Air\n"
           "Saudi Arabia, Malaysia,")


def test_riyadh_air_is_rejoined():
    assert E._akbar_airline(WRAPPED) == "Riyadh Air"


def test_an_airport_bleed_is_still_not_rejoined():
    """The guard that stops "Airport ," being read back as part of the name."""
    bleed = ("Operated by:Saudi International Airport , Fri, 02 Oct 26 (01h:45m)\n"
             "Airport , Saudi Arabia,")
    got = E._akbar_airline(bleed)
    assert "Airport" not in got
    assert got == "Saudi"


def test_every_previously_working_shape_is_unchanged():
    cases = {
        "Operated by:Saudi Mon, 24 Aug 26 (02h:45m) Egypt, Mon, 24 Aug 26\n"
        "Airline Saudi Arabia,": "Saudi Airline",
        "Operated by:Air Sial, Thu, 23 Jul 26": "Air Sial",
        "Operated by:Flyadeal Saudi Arabia,": "Flyadeal",
        "Operated by:Saudi Arabian Airlines,": "Saudi Arabian Airlines",
        "nothing here": "",
    }
    for src, want in cases.items():
        assert E._akbar_airline(src) == want, src


def test_a_bare_air_mid_line_is_not_treated_as_the_continuation():
    """"Air" has to be the whole line — not merely the start of one."""
    src = ("Operated by:Riyadh , Sat, 10 Oct 26\n"
           "Airport terminal information follows,")
    assert E._akbar_airline(src) == "Riyadh"
