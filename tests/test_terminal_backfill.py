"""
Offline regression tests for terminal handling.

Two things are locked in here:

  1. SCHEMA — every portal's flight dicts expose BOTH `terminal` and
     `arr_terminal`. Three portals used to omit `arr_terminal` entirely, so
     those legs could never carry an arrival terminal even when another leg
     in the same booking knew it.

  2. BACKFILL SYMMETRY — `build_html()` propagates a terminal an airline
     stated ONCE for an airport to every other leg touching that same airport,
     in both directions. The departure side was previously never backfilled:
     on a round trip where the hub's terminal appeared only on the outbound
     ARRIVAL, the inbound leg departing that same hub rendered nothing.

Critically, the backfill must never INVENT a terminal (§7) and must never
copy one airport's terminal onto a different airport — both are asserted.

Pure stdlib: build_html() imports Playwright only inside build_pdf(), so
these run with no browser and no network.
"""
import pathlib
import sys

import pytest

import extractors as E
import generate_itinerary_v3 as G

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"
PROJECT_DIR = str(pathlib.Path(__file__).resolve().parent.parent)

# every portal fixture -> its extractor
PORTAL_FIXTURES = [
    ("alhind_oneway.html",              E.extract_alhind),
    ("akbar_oneway.txt",                E.extract_akbar),
    ("akbar_flyadeal_f3.txt",           E.extract_akbar),
    ("ajet_connecting.html",            E.extract_ajet),
    ("pegasus_roundtrip.html",          E.extract_pegasus),
    ("turkish_airlines_connecting.txt", E.extract_turkish_airlines),
]


@pytest.mark.parametrize("fixture,fn", PORTAL_FIXTURES)
def test_every_portal_exposes_both_terminal_keys(fixture, fn):
    data = fn((FIX / fixture).read_text(encoding="utf-8"), {"date": "01 Jan 2026"})
    for seg in data.get("segments", []):
        for f in seg.get("flights", []):
            assert "terminal" in f, f"{fixture}: flight dict missing 'terminal'"
            assert "arr_terminal" in f, f"{fixture}: flight dict missing 'arr_terminal'"


def _leg(dep, arr, terminal="", arr_terminal=""):
    return {"flight_no": "XX 1", "dep_iata": dep, "arr_iata": arr,
            "dep_time": "01:00", "arr_time": "05:00",
            "dep_date": "01 Jan 2026", "arr_date": "01 Jan 2026",
            "dep_airport": "", "arr_airport": "",
            "terminal": terminal, "arr_terminal": arr_terminal}


def _round_trip(outbound, inbound):
    return {"pnr": "TERMTEST", "booked_on": "01 Jan 2026", "journey_type": "Round Trip",
            "passengers": [{"name": "Test", "ticket_no": "1"}],
            "segments": [{"type": "OUTBOUND", "flights": [outbound]},
                         {"type": "INBOUND", "flights": [inbound]}]}


def test_arrival_terminal_backfills_to_departure():
    """IST terminal stated ONLY on the outbound arrival -> the inbound leg
    departing that same IST must inherit it. This is the case that regressed."""
    data = _round_trip(_leg("DMM", "IST", arr_terminal="2"), _leg("IST", "DMM"))
    G.build_html(data, project_dir=PROJECT_DIR)
    assert data["segments"][1]["flights"][0]["terminal"] == "2"


def test_departure_terminal_backfills_to_arrival():
    """Reverse direction — stated only on the inbound departure."""
    data = _round_trip(_leg("DMM", "IST"), _leg("IST", "DMM", terminal="2"))
    G.build_html(data, project_dir=PROJECT_DIR)
    assert data["segments"][0]["flights"][0]["arr_terminal"] == "2"


def test_backfill_never_invents_a_terminal():
    """No terminal anywhere in the document -> everything stays blank (§7)."""
    data = _round_trip(_leg("DMM", "IST"), _leg("IST", "DMM"))
    G.build_html(data, project_dir=PROJECT_DIR)
    for grp in data["segments"]:
        for f in grp["flights"]:
            assert f["terminal"] == ""
            assert f["arr_terminal"] == ""


def test_backfill_does_not_cross_contaminate_airports():
    """DMM=1 and IST=2 must stay bound to their own IATA on every leg."""
    data = _round_trip(_leg("DMM", "IST", terminal="1", arr_terminal="2"),
                       _leg("IST", "DMM"))
    G.build_html(data, project_dir=PROJECT_DIR)
    inbound = data["segments"][1]["flights"][0]
    assert inbound["terminal"] == "2"       # departs IST
    assert inbound["arr_terminal"] == "1"   # arrives DMM


def test_a_terminal_never_crosses_between_separately_ticketed_journeys():
    """One IATA, two tickets, two different terminals (2026-09-30).

    A consolidated document can carry legs sold on different tickets — RX12239
    (Riyadh Air RUH→KUL) then BMGECWP (Spring Airlines KUL→CAN) three days
    later. Spring states KUL Terminal 2; the Akbar ticket states no terminal at
    all. Copying Spring's T2 onto Riyadh Air's KUL arrival asserts a terminal
    the airline never stated, and a full-service carrier into KLIA need not use
    the low-cost terminal — a WRONG fact rather than a missing one (§7).
    """
    def _leg(ref, fno, di, ai, term, arr_term):
        return {"flight_no": fno, "airline": "X", "pnr": ref,
                "dep_iata": di, "arr_iata": ai, "dep_city": di, "arr_city": ai,
                "dep_airport": "", "arr_airport": "",
                "terminal": term, "arr_terminal": arr_term,
                "dep_time": "10:00", "dep_date": "10 Oct 2026",
                "arr_time": "12:00", "arr_date": "10 Oct 2026",
                "cabin": "Economy", "duration": "2H 00M", "pax": []}

    d = {
        "pnr": "RX12239", "pnrs": ["RX12239", "BMGECWP"],
        "booking_ref": "AS000000001", "booked_on": "30 Sep 2026",
        "journey_type": "One-Way", "status": "Confirmed",
        "passengers": [{"name": "Mr. Test Passenger", "ticket_no": "1"}],
        "segments": [
            {"type": "TRIP 1", "layovers": [],
             "flights": [_leg("RX12239", "RX 863", "RUH", "KUL", "", "")]},
            {"type": "TRIP 2", "layovers": [],
             "flights": [_leg("BMGECWP", "9C 6922", "KUL", "CAN", "2", "3")]},
        ],
    }
    G.build_html(d, project_dir=PROJECT_DIR, layout="A")
    leg1, leg2 = d["segments"][0]["flights"][0], d["segments"][1]["flights"][0]
    # Spring's stated terminals survive on Spring's own leg …
    assert (leg2["terminal"], leg2["arr_terminal"]) == ("2", "3")
    # … and do NOT reach the other ticket's leg into the same airport.
    assert leg1["arr_terminal"] == ""
