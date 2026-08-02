"""
Airport names on the flight card, and the operating-carrier name (2026-08-02).

Two defects found on a real Akbar booking (PNR A052SF, Air Sial JED->ISB):

  1. The card showed the operating carrier as "Air" — the regex captured a
     single word out of "Operated by:Air Sial". A truncated airline name is a
     factual error on a client document, and it hit every multi-word carrier
     (Air Sial, Air Arabia, Fly Jinnah, Saudi Arabian Airlines). The fix must
     capture multiple words WITHOUT swallowing the neighbouring column's
     country, which pdfplumber linearises onto the same line
     ("by:Flyadeal Saudi Arabia,").

  2. No airport name rendered at all. Only Alhind states airport names in a
     parseable form; the other four portals had `dep_airport`/`arr_airport`
     hardcoded to "". Names now come from the AIRPORT_NAMES reference table as
     a BACKFILL — so anything the document itself stated still wins, and an
     unlisted IATA renders nothing rather than a guess.

The table must never leak into terminals: a terminal varies by carrier, route
and season, which is exactly why the equivalent terminal table stays rejected
(§8, 2026-07-27). Asserted below.
"""
import pathlib

import pytest

import extractors as E
import generate_itinerary_v3 as G

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"
ROOT = str(pathlib.Path(__file__).resolve().parent.parent)


# ── 1. operating carrier ──────────────────────────────────────────────────
# Every string below is a shape confirmed on real pdfplumber output or on the
# real Akbar ticket-copy render, not invented.
AIRLINE_CASES = [
    ("Operated by : TestAir", "TestAir"),
    # the A052SF defect: multi-word carrier truncated to its first word
    ("Operated by:Air Sial", "Air Sial"),
    # pdfplumber splits the label across lines AND bleeds the country in
    ("Operated , Thu, 23 Jul 26 (02h:10m) Thu, 23 Jul 26\nby:Flyadeal Saudi Arabia,",
     "Flyadeal"),
    ("Operated by:Air Sial Pakistan,", "Air Sial"),
    # a carrier whose OWN name starts with a country word must survive intact
    ("Operated by: Saudi Arabian Airlines", "Saudi Arabian Airlines"),
    ("Operated by:Fly Jinnah 15:45", "Fly Jinnah"),
    # nothing parseable -> blank, NOT a default carrier name
    ("no operator line here", ""),
]


@pytest.mark.parametrize("text,expected", AIRLINE_CASES)
def test_operating_carrier(text, expected):
    assert E._akbar_airline(text) == expected


def test_no_default_airline_is_invented():
    """The old code defaulted to 'IndiGo', which stamped a real airline's name
    onto other carriers' tickets. A failed parse must stay blank (§7)."""
    assert E._akbar_airline("Airline Ref : XX1234\nno carrier stated") == ""


def test_real_flyadeal_fixture_keeps_its_carrier():
    data = E.extract_akbar((FIX / "akbar_flyadeal_f3.txt").read_text(encoding="utf-8"),
                           {"date": "01 Jan 2026"})
    airlines = [f["airline"] for s in data["segments"] for f in s["flights"]]
    assert airlines == ["Flyadeal"]


# ── 2. airport names ──────────────────────────────────────────────────────
def _booking(dep, arr, dep_airport="", arr_airport=""):
    return {"pnr": "APTEST", "booked_on": "01 Jan 2026", "journey_type": "One-Way",
            "passengers": [{"name": "Test", "ticket_no": "1"}],
            "segments": [{"type": "OUTBOUND", "flights": [{
                "flight_no": "XX 1", "airline": "A", "dep_iata": dep, "arr_iata": arr,
                "dep_city": "", "arr_city": "", "dep_airport": dep_airport,
                "arr_airport": arr_airport, "terminal": "", "arr_terminal": "",
                "dep_date": "01 Jan 2026", "dep_time": "01:00",
                "arr_date": "01 Jan 2026", "arr_time": "05:00",
                "cabin": "Economy", "duration": ""}]}]}


def test_backfill_names_both_ends():
    """The A052SF case: an Akbar booking that carried no airport name at all."""
    data = _booking("JED", "ISB")
    G.build_html(data, project_dir=ROOT)
    fl = data["segments"][0]["flights"][0]
    assert fl["dep_airport"] == "King Abdulaziz International Airport"
    assert fl["arr_airport"] == "Islamabad International Airport"


def test_document_value_always_wins():
    """The table is a fallback. A name the source actually stated — including a
    variant spelling — must never be overwritten by the reference table."""
    data = _booking("JED", "ISB", dep_airport="Jeddah King Abdulaziz Intl (stated)")
    G.build_html(data, project_dir=ROOT)
    assert data["segments"][0]["flights"][0]["dep_airport"] == "Jeddah King Abdulaziz Intl (stated)"


def test_unknown_iata_renders_no_name():
    """An airport not in the table stays blank rather than getting a guess."""
    data = _booking("ZZZ", "QQQ")
    G.build_html(data, project_dir=ROOT)
    fl = data["segments"][0]["flights"][0]
    assert fl["dep_airport"] == "" and fl["arr_airport"] == ""


def test_reference_table_never_supplies_a_terminal():
    """Names are stable facts; terminals are not. The backfill must touch only
    the name fields — a static terminal map stays rejected (§8)."""
    data = _booking("JED", "ISB")
    G.build_html(data, project_dir=ROOT)
    fl = data["segments"][0]["flights"][0]
    assert fl["terminal"] == "" and fl["arr_terminal"] == ""


def test_table_entries_are_well_formed():
    for code, name in E.AIRPORT_NAMES.items():
        assert len(code) == 3 and code.isupper(), f"bad IATA key {code!r}"
        assert name and name == name.strip(), f"bad name for {code}"
