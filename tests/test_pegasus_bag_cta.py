"""
A Pegasus upsell BUTTON must never be printed as a baggage allowance.

When a fare includes no cabin allowance, Pegasus renders an "Add Baggage"
button in that cell and its template repeats the label — exactly like the
"Seat Selection Seat Selection" CTA that _valid_seat has always filtered.
Nothing filtered the baggage cell, so real booking 2BBTXC went out with a
flight card reading:

    PASSENGER        CABIN                      CHECKED
    Semih Yuksel     Add Baggage Add Baggage    20kg

i.e. a button caption presented to a client as their entitlement. The inbound
legs of the same booking were fine ("1 pc (55x40x23cm)"), which is why it
survived — it only fires on the legs whose fare excludes cabin baggage.

Every genuine allowance names a number, so a value with no digit at all is not
an allowance; the CTA-verb check additionally catches an upsell quoting one.
"""
import pytest

import extractors as E
import generate_itinerary_v3 as G


@pytest.mark.parametrize("raw", [
    "Add Baggage Add Baggage",     # the doubled template label, as shipped
    "Add Baggage",
    "Order Food Order Food",
    "Add 20 kg",                   # an upsell that quotes a number
    "Select Seat",
    "Upgrade Package",
])
def test_call_to_action_is_not_an_allowance(raw):
    assert E._valid_bag(raw) == ""


@pytest.mark.parametrize("raw", [
    "20 kg",
    "1 pc (55x40x23cm)",
    "7kg + 3kg",
    "Adult - 2 Pieces | 1 BAG UP TO 32KG | Infant - 1 Piece | 1 Piece equals 23KG",
    "Adult 1Pc : 1 BAG UP TO 12 KG",
    "1pc x 7kg",
])
def test_a_real_allowance_passes_through_untouched(raw):
    assert E._valid_bag(raw) == raw


def test_the_card_shows_na_not_the_button_text():
    """Rejected -> "Not specified" -> N/A on the card: incomplete, not wrong."""
    html = G._flight_card({
        "flight_no": "PC7655", "airline": "Pegasus", "dep_iata": "JED", "arr_iata": "SAW",
        "dep_city": "Jeddah", "arr_city": "Istanbul", "dep_airport": "", "arr_airport": "",
        "terminal": "", "arr_terminal": "", "dep_date": "17 Aug 2026", "dep_time": "10:40",
        "arr_date": "17 Aug 2026", "arr_time": "14:15", "cabin": "", "duration": "3H 35M",
        "pax": [{"name": "Test Pax", "cabin_bag": "Not specified",
                 "checked_bag": "20 kg", "seat": ""}],
    })
    assert "Add Baggage" not in html
    assert "20kg" in html


def test_existing_pegasus_bookings_keep_their_allowance():
    """The guard must not strip a stated allowance from a normal booking."""
    import pathlib
    fx = pathlib.Path(__file__).resolve().parent / "fixtures" / "pegasus_roundtrip.html"
    d = E.extract_pegasus(fx.read_text(encoding="utf-8"), {"date": "01 Jan 2026"})
    for p in d["passengers"]:
        assert G._norm_bag(p["checked_bag"]) != "N/A", p
