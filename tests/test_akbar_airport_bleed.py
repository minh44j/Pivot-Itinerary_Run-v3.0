"""
Two defects on real Akbar/Saudia round trip AS261349396 (MED-RUH-MED), both
visible on one flight card: OPERATED BY read "Saudi International Airport
Airline" and CABIN read the bare word "baggage".

  1. AIRPORT NAME IN THE OPERATOR CELL. pdfplumber renders

         Operated by:Saudi International Airport , Fri, 02 Oct 26 (01h:35m) ...
         Airline Saudi Arabia,

     so the From/To column's airport name sits between the carrier and its own
     continuation line. Cutting at the first comma kept the airport, and the
     2026-08-19 continuation re-join then appended "Airline" to it, naming a
     carrier that does not exist (§7 -- wrong, not merely missing). No airline's
     name contains "Airport", so the value is now cut there.
     The INBOUND leg of the same booking happened to parse correctly, because
     its wrap put the weekday rather than the airport next to the carrier -- a
     reminder that one good leg does not mean the cell parsed.

  2. FARE-RULES PROSE MATCHING A BAGGAGE LABEL. The Cabin Baggage column
     contains the sentence "Adult 1 Piece : Short conditions regarding carry-on
     baggage allowance details. - 1pc x 7kg", which pdfplumber wraps across
     lines. `_m` searches case-INSENSITIVELY and the label patterns had an
     optional colon and unanchored position, so "...regarding carry-on baggage"
     satisfied `Carry-On` and captured the next word -- the card shipped reading
     "CABIN: baggage". Labels are now line-anchored and require their colon,
     which also stops a colon-less column HEADER ("Travel Class Check-In
     Baggage Cabin Baggage") being read as a value.

  3. Per-direction baggage is read from the ONWARD/RETURN traveller blocks
     rather than the "Airline Ref :" slice. This layout puts both flight tables
     first and both traveller blocks after them, so the slice gave the outbound
     leg nothing and the inbound leg the OUTBOUND block.
"""
import pathlib

import pytest

import extractors as E
import generate_itinerary_v3 as G

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def bleed():
    return E.extract_akbar((FIX / "akbar_airport_bleed.txt").read_text(encoding="utf-8"),
                           {"date": "20 Aug 2026"})


def test_carrier_is_never_an_airport(bleed):
    for seg in bleed["segments"]:
        for f in seg["flights"]:
            assert f["airline"] == "Saudi Airline", f["airline"]
            assert "Airport" not in f["airline"]


@pytest.mark.parametrize("raw,expected", [
    # the outbound wrap: airport between the carrier and its continuation
    ("Operated by:Saudi International Airport , Fri, 02 Oct 26 (01h:35m) Fri, 02 Oct 26\n"
     "Airline Saudi Arabia,", "Saudi Airline"),
    # the inbound wrap of the SAME booking: weekday instead of airport
    ("Operated by:Saudi Sun, 04 Oct 26 (01h:35m) International Airport , Sun, 04 Oct 26\n"
     "Airline Saudi Arabia,", "Saudi Airline"),
])
def test_airport_bleed_shapes(raw, expected):
    assert E._akbar_airline(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    # every previously-working shape must survive the new airport cut
    ("Operated by:Air Sial", "Air Sial"),
    ("Operated , Thu, 23 Jul 26 (02h:10m)\nby:Flyadeal Saudi Arabia,", "Flyadeal"),
    ("Operated by: Saudi Arabian Airlines", "Saudi Arabian Airlines"),
    ("Operated by : TestAir", "TestAir"),
    ("Operated by:Saudi Mon, 24 Aug 26 (02h:45m) Egypt, Mon, 24 Aug 26\n"
     "Airline Saudi Arabia,\nTerminal 2", "Saudi Airline"),
    ("Operated by:Fly Jinnah Tue, 25 Aug 26", "Fly Jinnah"),
    ("no operator line here", ""),
])
def test_existing_carrier_shapes_unchanged(raw, expected):
    assert E._akbar_airline(raw) == expected


def test_prose_never_becomes_an_allowance(bleed):
    """"baggage" is a word from a sentence, not an allowance."""
    for seg in bleed["segments"]:
        for f in seg["flights"]:
            for x in f["pax"]:
                assert G._norm_bag(x["cabin_bag"]) == "7kg"
                # the source states a piece count and no weight for checked --
                # incomplete is allowed, wrong is not (§7)
                assert G._norm_bag(x["checked_bag"]) == "1Pcs"


def test_both_legs_get_the_allowance(bleed):
    """The traveller blocks sit after BOTH flight tables on this layout, so the
    outbound leg must not come back empty."""
    assert len(bleed["segments"]) == 2
    for seg in bleed["segments"]:
        assert seg["flights"][0]["pax"], seg["type"]


def test_qc_passes(bleed):
    assert E.qc_check(bleed) is None


def test_direction_bags_absent_when_the_layout_has_no_headings():
    """Layouts without ONWARD/RETURN traveller headings fall back to the
    booking-level values, exactly as before this existed."""
    t = (FIX / "akbar_oneway.txt").read_text(encoding="utf-8")
    assert E._akbar_direction_bags(t) == {}


# ── multi-city "TRIP n" layout (2026-08-24, AS261373110) ───────────────────
def test_trip_layout_parses_routes_and_per_trip_baggage():
    import generate_itinerary_v3 as G
    d = E.extract_akbar((FIX / "akbar_multicity_trip.txt").read_text(encoding="utf-8"),
                        {"date": "24 Aug 2026"})
    (a, b) = d["segments"]
    assert (a["flights"][0]["dep_iata"], a["flights"][0]["arr_iata"]) == ("RUH", "HKT")
    assert (b["flights"][0]["dep_iata"], b["flights"][0]["arr_iata"]) == ("BKK", "RUH")
    for seg in d["segments"]:
        assert seg["flights"][0]["airline"] == "Saudi Airline"
    # each TRIP states its own allowance; applying trip 1's two pieces to the
    # one-piece trip 2 would be a wrong fact (§7)
    assert G._norm_bag(a["flights"][0]["pax"][0]["checked_bag"]) == "2Pcs"
    assert G._norm_bag(b["flights"][0]["pax"][0]["checked_bag"]) == "1Pcs"
    assert G._norm_bag(a["flights"][0]["pax"][0]["cabin_bag"]) == "7kg"
    # the PDF genuinely carries no passenger table -> flag, never fabricate
    assert E.qc_check(d) == "Passenger name missing"
