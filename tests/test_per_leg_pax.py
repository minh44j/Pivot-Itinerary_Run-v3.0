"""
Per-leg passenger baggage / seat (approved design change, 2026-07-30).

Baggage and seat are per-SEGMENT facts, not per-passenger ones: a passenger can
buy extra baggage on the return leg only, or hold a different seat on each leg.
They now render as per-passenger rows inside each FLIGHT card instead of on the
passenger card.

Locked in here:
  1. Every portal that HAS per-segment data in its source emits flight["pax"].
     Verified against real-email structure per portal:
       Alhind   — passenger table has one ROW PER SEGMENT      -> per-segment
       aJet     — Passenger-Information block repeats per leg  -> per-leg
       Pegasus  — whole block repeats per DIRECTION            -> per-direction
       Turkish  — Fare-Rules block per DIRECTION, no seats     -> per-direction
       Akbar    — booking-level only                           -> generator fallback
  2. build_html() falls back to booking-level passengers[] for any leg with no
     per-leg data, so no portal regresses while the data catches up.
  3. The passenger card no longer carries baggage/seat.
  4. A column is OMITTED when no passenger on that leg has a value (approved),
     rather than padded with N/A.
"""
import pathlib

import pytest

import extractors as E
import generate_itinerary_v3 as G

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"
ROOT = str(pathlib.Path(__file__).resolve().parent.parent)

# portals whose real source genuinely carries per-segment/per-direction data
PER_LEG_PORTALS = [
    ("alhind_oneway.html",              E.extract_alhind),
    ("ajet_connecting.html",            E.extract_ajet),
    ("pegasus_roundtrip.html",          E.extract_pegasus),
    ("turkish_airlines_connecting.txt", E.extract_turkish_airlines),
]


@pytest.mark.parametrize("fixture,fn", PER_LEG_PORTALS)
def test_portal_emits_per_leg_pax(fixture, fn):
    data = fn((FIX / fixture).read_text(encoding="utf-8"), {"date": "01 Jan 2026"})
    for seg in data["segments"]:
        for f in seg["flights"]:
            assert f.get("pax"), f"{fixture}: {f.get('flight_no')} has no per-leg pax"
            for p in f["pax"]:
                # each per-leg record must carry the full shape
                for k in ("name", "cabin_bag", "checked_bag", "seat"):
                    assert k in p, f"{fixture}: per-leg pax missing {k!r}"


def test_akbar_has_no_per_leg_data_but_generator_fills_it():
    """Akbar's source is booking-level only, so the extractor emits no per-leg
    pax — build_html() must backfill from passengers[] so the card still shows
    the allowance that genuinely applies to every leg."""
    data = E.extract_akbar((FIX / "akbar_oneway.txt").read_text(encoding="utf-8"),
                           {"date": "01 Jan 2026"})
    G.build_html(data, project_dir=ROOT)      # mutates in place
    for seg in data["segments"]:
        for f in seg["flights"]:
            assert f["pax"], "generator fallback did not populate per-leg pax"
            assert f["pax"][0]["name"] == data["passengers"][0]["name"]


def test_passenger_card_no_longer_shows_baggage_or_seat():
    html = G._pax_card({"name": "Mr. Test Pax", "ticket_no": "123",
                        "cabin_bag": "8kg", "checked_bag": "23kg", "seat": "10J"})
    assert "TICKET NO." in html and "PASSENGER NAME" in html
    for gone in ("CABIN BAGGAGE", "CHECKED BAGGAGE", "SEAT", "8kg", "23kg", "10J"):
        assert gone not in html, f"{gone!r} should have moved to the flight card"


def _leg(pax):
    return {"flight_no": "XX 1", "airline": "A", "dep_iata": "AAA", "arr_iata": "BBB",
            "dep_city": "", "arr_city": "", "dep_airport": "", "arr_airport": "",
            "terminal": "", "arr_terminal": "", "dep_date": "01 Jan 2026",
            "dep_time": "01:00", "arr_date": "01 Jan 2026", "arr_time": "05:00",
            "cabin": "Economy", "duration": "", "pax": pax}


def test_seat_column_omitted_when_no_leg_has_a_seat():
    """Turkish Airlines / Akbar send no seats — the column must vanish, not
    render a row of N/A."""
    html = G._flight_card(_leg([{"name": "A B", "cabin_bag": "8kg",
                                "checked_bag": "23kg", "seat": ""}]))
    assert "CHECKED" in html
    assert "SEAT" not in html


def test_per_leg_values_render_independently():
    """The whole point: extra baggage on ONE leg shows only on that leg."""
    a = G._flight_card(_leg([{"name": "A B", "cabin_bag": "8kg",
                              "checked_bag": "23kg", "seat": "10J"}]))
    b = G._flight_card(_leg([{"name": "A B", "cabin_bag": "8kg",
                              "checked_bag": "23kg + 10kg", "seat": "28A"}]))
    assert "23kg" in a and "10J" in a and "28A" not in a
    assert "23kg + 10kg" in b and "28A" in b and "10J" not in b
